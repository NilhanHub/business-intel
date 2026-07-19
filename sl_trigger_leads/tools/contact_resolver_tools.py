"""Contact Resolver Agent tools.

The resolver is role-first and evidence-led. It does not send email, draft
sales copy, or unlock lead outreach. Live public search is pluggable and is the
default in PROMPT#11 unless the caller explicitly asks for a dry run.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from .live_contact_search_tools import (
    HUNTER_FOUND,
    HUNTER_NOT_CONFIGURED,
    HUNTER_NOT_FOUND,
    HUNTER_VERIFIED,
    EmailExtractor,
    HunterContactEnrichmentProvider,
    HunterEmailRecord,
    PeopleRoleExtractor,
    RequestsPageFetcher,
    adk_google_search_discovery,
    get_default_live_search_provider,
    normalize_company_domain,
    normalize_public_url,
    split_person_name,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
PROMPT10_SAMPLE_INPUT_PATH = OUTPUTS_DIR / "PROMPT#10_contact_resolver_sample_input.json"
LATEST_OPPORTUNITY_ANALYSIS_PATH = OUTPUTS_DIR / "PROMPT#06_opportunity_analysis.json"

MAX_LEADS_DEFAULT = 3
MAX_LEADS_HARD_CAP = 10
DEFAULT_SEARCH_BUDGET = {
    "max_search_queries": 10,
    "max_pages_to_fetch": 8,
    "max_candidate_contacts": 5,
    "max_runtime_seconds": 120,
}

COMPLIANCE_NOTES = [
    "Use only for targeted B2B outreach.",
    "Do not bulk send.",
    "Use truthful subject and sender.",
    "Include opt-out/unsubscribe wording where applicable.",
    "Respect suppression list once implemented.",
    "Do not contact personal/private emails.",
    "Named work contacts can still be personal data; approval is required before outreach.",
]

DEFAULT_DO_NOT_CLAIM = [
    "Do not claim an email address is verified unless public evidence supports it.",
    "Do not claim a named decision maker unless the person and role are evidenced.",
    "Do not claim the company wants outsourcing, budget, AI, Dynamics 365, or support unless the lead evidence says so.",
    "Do not use guessed emails as confirmed contact details.",
    "Do not send outreach from the Contact Resolver Agent.",
]

PERSONAL_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "icloud.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
}

GENERIC_EMAIL_LOCAL_PARTS = {
    "admin",
    "careers",
    "contact",
    "hello",
    "hr",
    "info",
    "inquiries",
    "jobs",
    "recruitment",
    "recruiting",
    "sales",
    "support",
}

SECRET_PATTERNS = (
    "access_" + "token",
    "refresh_" + "token",
    "client_" + "secret",
    "private_" + "key",
    "author" + "ization:",
    "bear" + "er ",
    "ya" + "29.",
)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True)
class PageText:
    url: str
    text: str
    source: str = "public_web"
    fetched_at: str | None = None


@dataclass
class CandidatePerson:
    name: str | None
    role: str | None
    company: str
    email: str | None = None
    email_type: str = "unknown"
    contact_url: str | None = None
    linkedin_url: str | None = None
    source_urls: list[str] = field(default_factory=list)
    evidence_summary: str = ""
    source_kind: str = "public_web"
    stale_evidence: bool = False
    ambiguous_company: bool = False
    risk_notes: list[str] = field(default_factory=list)


class ContactSearchProvider(Protocol):
    name: str
    configured: bool

    def search_web(self, query: str, limit: int) -> list[SearchResult]:
        """Return public search results for a query."""

    def fetch_page(self, url: str) -> PageText:
        """Return public page text for a result URL."""

    def extract_emails(self, text: str) -> list[str]:
        """Extract public email addresses from text."""

    def extract_people_roles(
        self,
        text: str,
        company: str,
        target_personas: list[str],
    ) -> list[CandidatePerson]:
        """Extract possible people and roles from public text."""


class NoConfiguredSearchProvider:
    """Provider stub used when no live search API is configured."""

    name = "not_configured"
    configured = False
    unavailable_reason = "Dry-run mode or no live provider configured."

    def search_web(self, query: str, limit: int) -> list[SearchResult]:
        return []

    def fetch_page(self, url: str) -> PageText:
        return PageText(url=url, text="", source=self.name)

    def extract_emails(self, text: str) -> list[str]:
        return extract_emails(text)

    def extract_people_roles(
        self,
        text: str,
        company: str,
        target_personas: list[str],
    ) -> list[CandidatePerson]:
        return extract_people_roles(text, company, target_personas)


class LiveContactSearchProviderAdapter:
    """Adapter from PROMPT#11 live search provider to PROMPT#10 resolver protocol."""

    def __init__(self, live_provider: Any | None = None) -> None:
        self.live_provider = live_provider or get_default_live_search_provider()
        self.name = self.live_provider.name
        self.configured = bool(self.live_provider.configured)
        self.unavailable_reason = getattr(self.live_provider, "unavailable_reason", None)
        self.fetcher = RequestsPageFetcher(timeout_seconds=15)
        self.email_extractor = EmailExtractor()
        self.people_extractor = PeopleRoleExtractor()
        self.search_errors: list[str] = []
        self.page_errors: list[str] = []

    def search_web(self, query: str, limit: int) -> list[SearchResult]:
        try:
            results = self.live_provider.search_web(query, limit=limit)
        except Exception as exc:
            self.search_errors.append(f"{type(exc).__name__}: {exc}")
            return []
        return [
            SearchResult(title=result.title, url=result.url, snippet=result.snippet)
            for result in results
            if result.url
        ]

    def fetch_page(self, url: str) -> PageText:
        normalized_url = normalize_public_url(url)
        if not normalized_url:
            self.page_errors.append(f"{url}: rejected_malformed_url")
            return PageText(url=url, text="", source=self.name, fetched_at=None)
        page = self.fetcher.fetch_page(normalized_url)
        if page.error:
            self.page_errors.append(f"{page.url}: {page.error}")
        return PageText(
            url=page.url,
            text=page.text,
            source=self.name,
            fetched_at=str(page.status_code) if page.status_code is not None else None,
        )

    def extract_emails(self, text: str) -> list[str]:
        return self.email_extractor.extract(text)

    def extract_people_roles(
        self,
        text: str,
        company: str,
        target_personas: list[str],
    ) -> list[CandidatePerson]:
        people = []
        for item in self.people_extractor.extract(text, company, target_personas):
            people.append(
                CandidatePerson(
                    name=item.get("name"),
                    role=item.get("role"),
                    company=company,
                    evidence_summary=item.get("evidence_summary", ""),
                )
            )
        people.extend(extract_people_roles(text, company, target_personas))
        return people


OPTIONAL_PROVIDER_HOOKS = {
    "hunter": {"enabled": False, "requires_api_key": True, "env": ["HUNTER_API_KEY"]},
    "google_programmable_search": {"enabled": False, "requires_api_key": True},
    "serpapi_like_provider": {"enabled": False, "requires_api_key": True},
    "apollo_rocketreach_cognism_dropcontact": {
        "enabled": False,
        "requires_api_key": True,
    },
    "email_verifier_provider": {"enabled": False, "requires_api_key": True},
}

BUCKET_ALIASES = {
    "staff augmentation / delivery capacity": "staff_augmentation_delivery_capacity",
    "staff_augmentation_delivery_capacity": "staff_augmentation_delivery_capacity",
    "custom software development": "custom_software_development",
    "custom_software_development": "custom_software_development",
    "ai apps / ai workflow automation": "ai_apps_workflow_automation",
    "ai_apps_workflow_automation": "ai_apps_workflow_automation",
    "ai strategy consulting": "ai_strategy_consulting",
    "ai_strategy_consulting": "ai_strategy_consulting",
    "data analytics & ai": "data_analytics_ai",
    "data analytics and ai": "data_analytics_ai",
    "data_analytics_ai": "data_analytics_ai",
    "microsoft dynamics 365 / crm / power platform": "microsoft_dynamics_365_crm_power_platform",
    "microsoft_dynamics_365_crm_power_platform": "microsoft_dynamics_365_crm_power_platform",
    "integrations / api / middleware": "integrations_api_middleware",
    "integrations_api_middleware": "integrations_api_middleware",
    "qa / test automation": "qa_test_automation",
    "qa_test_automation": "qa_test_automation",
    "managed it / application support": "managed_application_it_support",
    "managed it / application support / support operations": "managed_application_it_support",
    "managed_application_it_support": "managed_application_it_support",
    "custom software": "custom_software_development",
}

BUCKET_DISPLAY = {
    "staff_augmentation_delivery_capacity": "Staff Augmentation / Delivery Capacity",
    "custom_software_development": "Custom Software Development",
    "ai_apps_workflow_automation": "AI Apps / AI Workflow Automation",
    "ai_strategy_consulting": "AI Strategy Consulting",
    "data_analytics_ai": "Data Analytics & AI",
    "microsoft_dynamics_365_crm_power_platform": "Microsoft Dynamics 365 / CRM / Power Platform",
    "integrations_api_middleware": "Integrations / API / Middleware",
    "qa_test_automation": "QA / Test Automation",
    "managed_application_it_support": "Managed IT / Application Support",
    "cloud_product_development": "Custom Software Development",
}

STATUS_BUCKET_VALUES = {
    "contact now",
    "verify contact first",
    "watch",
    "watch list",
    "park",
    "low fit",
    "low fit / watch",
    "unknown",
}

PERSONA_MAP = {
    "staff_augmentation_delivery_capacity": [
        ("CTO", "Hiring pressure suggests delivery capacity pain owned by technical leadership."),
        ("Head of Engineering", "Engineering leadership owns delivery throughput and team capacity."),
        ("Engineering Manager", "Engineering managers feel delivery bottlenecks and role gaps."),
        ("Delivery Manager", "Delivery management owns staffing and execution risk."),
        ("Talent Acquisition Lead / HR Manager", "HR may own the job post, but is secondary to the technical buyer."),
    ],
    "integrations_api_middleware": [
        ("CTO", "Integration pressure is usually a technical-platform priority."),
        ("Head of Engineering", "Engineering leadership owns API and middleware delivery."),
        ("Integration Lead", "Directly owns integration architecture and delivery."),
        ("API Platform Lead", "Owns API platform quality, scale, and roadmap."),
        ("Solutions Architect", "Owns cross-system design and implementation choices."),
        ("Product Manager", "May own product integration requirements."),
        ("IT Manager", "May own internal integration operations."),
    ],
    "qa_test_automation": [
        ("QA Manager", "Owns quality process, test coverage, and automation gaps."),
        ("Head of Quality Engineering", "Owns quality-engineering strategy and tooling."),
        ("Engineering Manager", "Owns release quality and delivery risk."),
        ("CTO", "Owns technical risk and quality outcomes."),
        ("Delivery Manager", "Secondary owner for release and delivery reliability."),
    ],
    "ai_apps_workflow_automation": [
        ("CTO", "Owns technical feasibility and implementation risk."),
        ("Head of AI", "Owns AI delivery and governance if the function exists."),
        ("Head of Product", "Owns AI-enabled product and workflow outcomes."),
        ("Innovation Lead", "Owns new workflow and automation initiatives."),
        ("Data/ML Lead", "Owns model, data, and automation implementation."),
        ("CEO / Founder", "For small companies, the executive sponsor may be the practical buyer."),
    ],
    "ai_strategy_consulting": [
        ("CEO / Founder", "Executive sponsorship is often needed for AI strategy."),
        ("CTO", "Owns technical direction and feasibility."),
        ("CIO", "Owns enterprise technology and governance."),
        ("Innovation Lead", "Owns transformation themes and experiments."),
        ("Digital Transformation Lead", "Owns AI adoption roadmap and change management."),
    ],
    "microsoft_dynamics_365_crm_power_platform": [
        ("CIO", "Owns enterprise systems and business applications."),
        ("Head of IT", "Owns CRM, ERP, and platform operations."),
        ("CRM Manager", "Owns CRM process and adoption."),
        ("Business Applications Manager", "Owns Microsoft business-app stack delivery."),
        ("Operations Head", "Owns process efficiency and reporting outcomes."),
        ("CFO", "Secondary buyer for ERP, reporting, or financial-process signals."),
    ],
    "data_analytics_ai": [
        ("Head of Data", "Owns data strategy and analytics capability."),
        ("Analytics Lead", "Owns analytics delivery and reporting workflows."),
        ("BI Manager", "Owns dashboarding, BI governance, and reporting."),
        ("CTO / CIO", "Owns data-platform and analytics investment decisions."),
        ("Operations Head", "Secondary buyer when analytics supports operations improvement."),
    ],
    "managed_application_it_support": [
        ("Head of IT", "Owns IT and application-support reliability."),
        ("IT Manager", "Owns support operations and vendor coordination."),
        ("Application Support Manager", "Owns application incident and support workflows."),
        ("Operations Manager", "Owns service reliability and operational continuity."),
        ("CTO / CIO", "Secondary executive buyer for support operations."),
    ],
    "custom_software_development": [
        ("CTO", "Owns technical delivery and build-versus-partner choices."),
        ("Head of Product", "Owns product roadmap and software outcomes."),
        ("Engineering Manager", "Owns engineering delivery constraints."),
        ("Founder / CEO", "For small firms, may own product-build decisions."),
        ("Operations Manager", "Secondary buyer for internal software workflow needs."),
    ],
    "low_fit_or_watch": [
        ("CTO", "Verify whether the weak signal has a real technical owner."),
        ("Operations Manager", "Verify whether the weak signal maps to an operational pain."),
    ],
}


def canonical_bucket_key(bucket: str | None) -> str:
    if not bucket or is_status_bucket(bucket):
        return "low_fit_or_watch"
    normalized = re.sub(r"\s+", " ", str(bucket).strip().lower())
    return BUCKET_ALIASES.get(normalized, normalized.replace(" ", "_").replace("/", "_"))


def bucket_display_name(bucket: str | None) -> str:
    if not bucket or is_status_bucket(bucket):
        return "unknown"
    key = canonical_bucket_key(bucket)
    return BUCKET_DISPLAY.get(key, str(bucket or "unknown"))


def is_status_bucket(value: str | None) -> bool:
    normalized = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return normalized in STATUS_BUCKET_VALUES


def is_service_bucket(value: str | None) -> bool:
    if not value or is_status_bucket(value):
        return False
    return canonical_bucket_key(value) in BUCKET_DISPLAY


def map_personas_for_bucket(bucket: str | None) -> list[dict[str, Any]]:
    key = canonical_bucket_key(bucket)
    personas = PERSONA_MAP.get(key, PERSONA_MAP["low_fit_or_watch"])
    return [
        {"persona": persona, "why_relevant": why, "priority": index + 1}
        for index, (persona, why) in enumerate(personas)
    ]


def merge_personas_for_lead(lead: dict[str, Any]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    explicit_roles = (
        lead.get("contact_target_roles")
        or lead.get("contactTargetRoles")
        or lead.get("target_roles")
        or []
    )
    if isinstance(explicit_roles, str):
        explicit_roles = [part.strip() for part in explicit_roles.split(",") if part.strip()]
    for role in explicit_roles if isinstance(explicit_roles, list) else []:
        clean_role = re.sub(r"\s+", " ", str(role or "").strip())
        key = clean_role.lower()
        if not clean_role or key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "persona": clean_role,
                "why_relevant": "Explicit buyer role from the verified lead evidence pack.",
                "priority": len(merged) + 1,
            }
        )
        if len(merged) >= 8:
            return merged
    buckets = _lead_buckets(lead)
    for bucket in buckets:
        for persona in map_personas_for_bucket(bucket):
            key = persona["persona"].lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append({**persona, "priority": len(merged) + 1})
    return merged[:8] or map_personas_for_bucket(None)


def normalize_company_name(company: str | None) -> str:
    value = re.sub(r"\s+", " ", str(company or "").strip())
    return value or "unknown"


def infer_service_buckets_from_signal(lead: dict[str, Any]) -> list[str]:
    """Infer service buckets from trigger text when the lead lacks a real bucket."""
    text = " ".join(
        str(lead.get(key) or "")
        for key in (
            "trigger",
            "trigger_summary",
            "outreach_angle",
            "evidence_excerpt",
            "recommended_outreach_theme",
        )
    ).lower()
    buckets: list[str] = []

    def add(bucket: str) -> None:
        if bucket not in buckets:
            buckets.append(bucket)

    if re.search(r"\b(qe|qa|quality|test automation|tester|testing)\b", text):
        add("QA / Test Automation")
        add("Staff Augmentation / Delivery Capacity")
    if re.search(r"\b(api|middleware|integration|integrations)\b", text):
        add("Integrations / API / Middleware")
        add("Staff Augmentation / Delivery Capacity")
    if re.search(r"\b(ai developer|ai engineer|machine learning|mlops|ml lead|ai lead|ai\b)\b", text):
        add("AI Apps / AI Workflow Automation")
        add("Staff Augmentation / Delivery Capacity")
    if re.search(r"(\.net|\bdotnet\b|\bbackend\b|\bsoftware engineer\b|\bdeveloper\b|\bsoftware developer\b)", text):
        add("Custom Software Development")
        add("Staff Augmentation / Delivery Capacity")
    return buckets


def extract_emails(text: str) -> list[str]:
    matches = re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text or "", re.I)
    cleaned: list[str] = []
    for match in matches:
        email = match.strip(".,;:()[]<>").lower()
        if not is_secret_like(email) and email not in cleaned:
            cleaned.append(email)
    return cleaned


def is_secret_like(value: str | None) -> bool:
    lowered = str(value or "").lower()
    return any(pattern in lowered for pattern in SECRET_PATTERNS)


def email_domain(email: str | None) -> str:
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].lower()


def email_local_part(email: str | None) -> str:
    if not email or "@" not in email:
        return ""
    return email.split("@", 1)[0].lower()


def is_personal_email_domain(email: str | None) -> bool:
    return email_domain(email) in PERSONAL_EMAIL_DOMAINS


def is_generic_email(email: str | None) -> bool:
    local = email_local_part(email)
    return local in GENERIC_EMAIL_LOCAL_PARTS or any(
        local.startswith(prefix + ".") for prefix in GENERIC_EMAIL_LOCAL_PARTS
    )


def filter_public_email(
    email: str,
    *,
    official_context: bool = False,
) -> tuple[str | None, list[str]]:
    risk_notes: list[str] = []
    if is_secret_like(email):
        return None, ["Secret-like value rejected from contact output."]
    if is_personal_email_domain(email):
        if not official_context:
            return None, ["Personal/private email domain rejected."]
        risk_notes.append(
            "Personal-domain email appears in an official context; verify before use."
        )
    return email.lower(), risk_notes


def classify_email_type(email: str | None, name: str | None = None) -> str:
    if not email:
        return "unknown"
    if is_generic_email(email) or is_personal_email_domain(email):
        return "public_generic"
    if name:
        local = email_local_part(email).replace("_", ".").replace("-", ".")
        parts = [part.lower() for part in re.split(r"\s+", name) if part]
        if parts and any(part in local for part in parts):
            return "public_named"
    return "public_generic"


def extract_people_roles(
    text: str,
    company: str,
    target_personas: list[str],
) -> list[CandidatePerson]:
    """Small deterministic extractor for public snippets/pages.

    This is intentionally conservative. It only returns a person when a line
    contains a target persona phrase and a plausible capitalized name.
    """
    people: list[CandidatePerson] = []
    persona_terms = sorted(set(target_personas), key=len, reverse=True)
    for line in (text or "").splitlines():
        clean_line = re.sub(r"\s+", " ", line).strip()
        if not clean_line:
            continue
        lowered = clean_line.lower()
        matched_role = next(
            (persona for persona in persona_terms if persona.lower() in lowered),
            None,
        )
        if not matched_role:
            continue
        if re.search(rf"\bformer\s+{re.escape(matched_role)}\b", clean_line, flags=re.I):
            continue
        name = _extract_name_near_role(clean_line, matched_role)
        if not name or _is_company_like_name(name, company):
            continue
        emails = extract_emails(clean_line)
        email = emails[0] if emails else None
        people.append(
            CandidatePerson(
                name=name,
                role=matched_role,
                company=company,
                email=email,
                email_type=classify_email_type(email, name),
                evidence_summary=clean_line[:240],
            )
        )
    return people


def _extract_name_near_role(line: str, role: str) -> str | None:
    name_pattern = r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})"
    role_pattern = re.escape(role)
    patterns = [
        rf"{name_pattern}\s*[-|,]\s*{role_pattern}",
        rf"{role_pattern}\s*[:|-]\s*{name_pattern}",
        rf"{name_pattern}.{{0,80}}{role_pattern}",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            groups = [group for group in match.groups() if group and group != role]
            if groups:
                name = re.sub(
                    r"^(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+",
                    "",
                    groups[-1].strip(),
                    flags=re.I,
                )
                return name if _is_plausible_person_name(name) else None
    return None


PERSON_NAME_STOPWORDS = {
    "architect",
    "article",
    "blog",
    "business",
    "career",
    "careers",
    "contact",
    "customer",
    "cto",
    "cio",
    "ceo",
    "developer",
    "director",
    "engineer",
    "manager",
    "lead",
    "head",
    "engineering",
    "quality",
    "solutions",
    "solution",
    "software",
    "enterprise",
    "five",
    "former",
    "founder",
    "leaders",
    "leadership",
    "management",
    "executive",
    "news",
    "practical",
    "report",
    "company",
    "team",
    "ways",
}


def _is_plausible_person_name(name: str | None) -> bool:
    clean = re.sub(r"[^A-Za-z.' -]", " ", str(name or "")).strip(" .'-")
    parts = [part.strip(" .'") for part in clean.split() if part.strip(" .'")]
    if len(parts) < 2 or len(parts) > 4:
        return False
    if sum(1 for part in parts if part.isupper()) >= 2:
        return False
    lowered = {part.lower() for part in parts}
    if lowered & PERSON_NAME_STOPWORDS:
        return False
    return all(part[:1].isupper() and re.match(r"^[A-Za-z.'-]+$", part) for part in parts)


def _is_company_like_name(name: str, company: str) -> bool:
    name_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", name.lower())
        if token not in {"pvt", "ltd", "limited", "private"}
    }
    company_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", company.lower())
        if token not in {"pvt", "ltd", "limited", "private"}
    }
    return bool(name_tokens and name_tokens.issubset(company_tokens))


def infer_email_pattern(
    *,
    name: str,
    domain: str,
    observed_emails: list[str],
) -> dict[str, str | None]:
    """Email guessing is disabled; keep the legacy shape for safe callers."""
    return {"email": None, "email_type": "unknown", "pattern": None}


def score_candidate_contact(
    candidate: dict[str, Any] | CandidatePerson,
    *,
    target_personas: list[str],
    ambiguous_company: bool = False,
    stale_evidence: bool = False,
) -> dict[str, Any]:
    data = _candidate_to_dict(candidate)
    score = 0
    name = data.get("name")
    role = data.get("role")
    email = data.get("email")
    email_type = data.get("email_type") or "unknown"
    source_urls = data.get("source_urls") or []
    source_kind = data.get("source_kind") or "public_web"

    role_match = role_matches_persona(role, target_personas)
    if name:
        score += 30
    if role_match:
        score += 20
    elif role:
        score -= 20
    if source_kind == "official_company":
        score += 20
    if any("linkedin.com" in url.lower() for url in source_urls) or data.get("linkedin_url"):
        score += 10
    if email and email_type == "public_named":
        score += 20
    elif email and email_type == "public_generic":
        score = max(score, 35)
    elif email and email_type == "inferred_pattern":
        score += 10

    if stale_evidence or data.get("stale_evidence"):
        score -= 15
    if ambiguous_company or data.get("ambiguous_company"):
        score -= 30

    if email_type == "public_generic" and not name:
        score = min(score, 45)
    if email_type == "inferred_pattern":
        score = min(score, 70)
    if name and not email:
        score = min(score, 75)
    if not name:
        score = min(score, 45)

    score = max(0, min(100, score))
    data["confidence"] = score
    data["confidence_label"] = confidence_label(score)
    return data


def confidence_label(score: int) -> str:
    if score >= 80:
        return "High"
    if score >= 55:
        return "Medium"
    if score > 0:
        return "Low"
    return "No usable contact"


def role_matches_persona(role: str | None, target_personas: list[str]) -> bool:
    if not role:
        return False
    role_tokens = _role_tokens(role)
    for persona in target_personas:
        persona_tokens = _role_tokens(persona)
        if role_tokens & persona_tokens:
            return True
    return False


def _role_tokens(value: str) -> set[str]:
    synonyms = {
        "cto": "cto",
        "cio": "cio",
        "ceo": "ceo",
        "qa": "quality",
        "quality": "quality",
        "engineering": "engineering",
        "engineer": "engineering",
        "delivery": "delivery",
        "integration": "integration",
        "api": "integration",
        "architect": "architect",
        "product": "product",
        "data": "data",
        "analytics": "data",
        "bi": "data",
        "it": "it",
        "applications": "applications",
        "crm": "crm",
        "operations": "operations",
        "innovation": "innovation",
        "ai": "ai",
        "founder": "founder",
    }
    tokens = set(re.findall(r"[a-z0-9]+", value.lower()))
    return {synonyms.get(token, token) for token in tokens}


def build_search_queries(
    lead: dict[str, Any],
    personas: list[dict[str, Any]],
    *,
    max_search_queries: int = 8,
) -> list[str]:
    company = normalize_company_name(lead.get("company"))
    primary_personas = [item["persona"] for item in personas[:5]]
    base_queries = [
        f'"{company}" CTO Sri Lanka',
        f'"{company}" "Head of Engineering"',
        f'"{company}" "QA Manager"',
        f'"{company}" "Integration Lead"',
        f'site:linkedin.com/in "{company}" "Head of Engineering"',
        f'site:linkedin.com/company "{company}"',
        f'"{company}" "careers" "email"',
        f'"{company}" "contact" "Sri Lanka"',
        f'"{company}" "press release" "CTO"',
        f'"{company}" "management team"',
    ]
    persona_queries = [f'"{company}" "{persona}"' for persona in primary_personas]
    queries: list[str] = []
    for query in persona_queries + base_queries:
        if query not in queries:
            queries.append(query)
        if len(queries) >= max_search_queries:
            break
    return queries


def build_live_search_queries(
    lead: dict[str, Any],
    personas: list[dict[str, Any]],
    *,
    max_search_queries: int = 10,
) -> list[str]:
    company = normalize_company_name(lead.get("company"))
    layer_1 = [
        f'"{company}" official website',
        f'"{company}" contact',
        f'"{company}" careers',
    ]
    role_terms = persona_search_terms([item["persona"] for item in personas])
    primary_roles = role_terms[:3]
    secondary_roles = role_terms[3:6]
    role_queries = []
    if primary_roles:
        role_queries.append(f'"{company}" {_or_query(primary_roles)}')
    if secondary_roles:
        role_queries.append(f'"{company}" {_or_query(secondary_roles)}')
    professional = [
        f'site:linkedin.com/in "{company}" {_or_query(primary_roles or ["CTO"])}',
        f'"{company}" LinkedIn company',
        f'site:linkedin.com/company "{company}"',
        f'"{company}" management team',
    ]
    queries: list[str] = []
    for query in layer_1 + role_queries + professional:
        if query not in queries:
            queries.append(query)
        if len(queries) >= max_search_queries:
            break
    return queries


def persona_search_terms(personas: list[str]) -> list[str]:
    terms: list[str] = []
    for persona in personas:
        for part in re.split(r"\s*/\s*|\s+or\s+", persona):
            clean = re.sub(r"\s+", " ", part.strip())
            if clean and clean not in terms:
                terms.append(clean)
    return terms


def _or_query(terms: list[str]) -> str:
    return "(" + " OR ".join(f'"{term}"' for term in terms if term) + ")"


def named_roles_for_trace(personas: list[dict[str, Any]]) -> list[str]:
    return persona_search_terms([item["persona"] for item in personas])[:6]


def named_role_terms_in_query(query: str, role_terms: list[str]) -> list[str]:
    lowered = query.lower()
    return [term for term in role_terms if term.lower() in lowered]


def discover_contact_live_search_provider() -> dict[str, Any]:
    discovery = adk_google_search_discovery()
    provider = get_default_contact_search_provider(dry_run=False)
    hunter = HunterContactEnrichmentProvider.from_env()
    hunter_status = HUNTER_NOT_FOUND if hunter.configured else HUNTER_NOT_CONFIGURED
    return {
        "adk_google_search_available": discovery["available"],
        "adk_google_search_error_type": discovery["error_type"],
        "adk_google_search_error": discovery["error"],
        "selected_provider": provider.name,
        "live_web_search_enabled": bool(provider.configured),
        "setup_message": getattr(provider, "unavailable_reason", None),
        "hunter_configured": bool(hunter.configured),
        "hunter_status": hunter_status,
        "hunter_setup_message": hunter.unavailable_reason,
        "fallback_hooks": {
            "hunter": {
                "enabled": bool(hunter.configured),
                "env": ["HUNTER_API_KEY"],
            },
            "google_cse": {
                "enabled": provider.name == "google_cse",
                "env": ["GOOGLE_CSE_API_KEY", "GOOGLE_CSE_CX"],
            },
            "serpapi": {
                "enabled": provider.name == "serpapi",
                "env": ["SERPAPI_API_KEY"],
            },
        },
    }


def get_default_contact_search_provider(*, dry_run: bool) -> ContactSearchProvider:
    if dry_run:
        return NoConfiguredSearchProvider()
    return LiveContactSearchProviderAdapter()


def resolve_contact_route_for_lead(
    lead: dict[str, Any],
    dry_run: bool = False,
    max_search_queries: int = 10,
    max_pages_to_fetch: int = 8,
    max_candidate_contacts: int = 5,
    max_runtime_seconds: int = 120,
    audit_mode: bool = False,
) -> dict[str, Any]:
    """ADK-safe tool: resolve one lead. Live public search is default."""
    return _resolve_contact_route_for_lead(
        lead,
        provider=get_default_contact_search_provider(dry_run=dry_run),
        dry_run=dry_run,
        max_search_queries=max_search_queries,
        max_pages_to_fetch=max_pages_to_fetch,
        max_candidate_contacts=max_candidate_contacts,
        max_runtime_seconds=max_runtime_seconds,
        audit_mode=audit_mode,
    )


def resolve_contacts_for_leads(
    leads: list[dict[str, Any]] | dict[str, Any] | str,
    max_leads: int = MAX_LEADS_DEFAULT,
    dry_run: bool = False,
    audit_mode: bool = False,
) -> dict[str, Any]:
    """Resolve a bounded batch of leads without sending email."""
    safe_max = min(max(1, int(max_leads or MAX_LEADS_DEFAULT)), MAX_LEADS_HARD_CAP)
    coerced_leads = coerce_explicit_leads(leads)
    selected = coerced_leads[:safe_max]
    grouped = group_leads_by_company(selected)
    provider_status = discover_contact_live_search_provider() if not dry_run else {
        "selected_provider": "not_configured",
        "live_web_search_enabled": False,
        "hunter_configured": False,
        "hunter_status": HUNTER_NOT_CONFIGURED,
    }
    results = [
        resolve_contact_route_for_lead(lead, dry_run=dry_run, audit_mode=audit_mode)
        for lead in grouped
    ]
    return {
        "agent": "Contact Resolver Agent",
        "dry_run": dry_run,
        "live_web_search_enabled": bool(provider_status["live_web_search_enabled"]),
        "search_provider": provider_status["selected_provider"],
        "hunter_configured": bool(provider_status.get("hunter_configured")),
        "hunter_status": provider_status.get("hunter_status"),
        "requested_leads": len(coerced_leads),
        "resolved_count": len(results),
        "company_group_count": len(grouped),
        "max_leads": safe_max,
        "max_leads_hard_cap": MAX_LEADS_HARD_CAP,
        "results": results,
        "compact_output": format_contact_routes_table(results),
        "sending_enabled": False,
        "compliance_notes": COMPLIANCE_NOTES,
    }


def resolve_contact_routes_from_text(
    lead_text: str,
    max_leads: int = MAX_LEADS_DEFAULT,
    dry_run: bool = False,
    audit_mode: bool = False,
) -> dict[str, Any]:
    """Resolve contact routes from explicit pasted lead rows or lead blocks.

    This tool exists for ADK Web/Agent Runtime prompts where the user pastes
    human-readable rows instead of JSON. It maps only explicit fields supplied
    by the user and does not invent companies, URLs, contacts, or emails.
    """
    parsed_leads = parse_explicit_leads_text(lead_text)
    result = resolve_contacts_for_leads(
        parsed_leads,
        max_leads=max_leads,
        dry_run=dry_run,
        audit_mode=audit_mode,
    )
    result["input_source_kind"] = "explicit_lead_text"
    result["parsed_leads_count"] = len(parsed_leads)
    result["parser_warnings"] = _explicit_lead_parser_warnings(parsed_leads, lead_text)
    return result


def coerce_explicit_leads(leads: list[dict[str, Any]] | dict[str, Any] | str | None) -> list[dict[str, Any]]:
    if leads is None:
        return []
    if isinstance(leads, str):
        return parse_explicit_leads_text(leads)
    if isinstance(leads, dict):
        for key in ("leads", "explicit_leads", "lead_rows", "items"):
            value = leads.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, str):
                return parse_explicit_leads_text(value)
        if "lead_text" in leads or "text" in leads:
            return parse_explicit_leads_text(str(leads.get("lead_text") or leads.get("text") or ""))
        return [leads]
    if isinstance(leads, list):
        coerced: list[dict[str, Any]] = []
        for item in leads:
            if isinstance(item, dict):
                coerced.append(item)
            elif isinstance(item, str):
                coerced.extend(parse_explicit_leads_text(item))
        return coerced
    return []


def parse_explicit_leads_text(lead_text: str) -> list[dict[str, Any]]:
    """Parse explicit user-supplied lead blocks into resolver input dicts."""
    text = str(lead_text or "").strip()
    if not text:
        return []
    blocks = [
        block.strip()
        for block in re.split(r"(?im)^\s*Lead\s+\d+\s*:\s*$", text)
        if block.strip()
    ]
    if not blocks:
        blocks = [text]

    parsed: list[dict[str, Any]] = []
    for block in blocks:
        lead: dict[str, Any] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            raw_key, raw_value = line.split(":", 1)
            key = _canonical_explicit_lead_key(raw_key)
            value = raw_value.strip()
            if key and value:
                lead[key] = value
        if lead:
            normalized = normalize_lead_aliases(lead)
            if normalized.get("company") or normalized.get("evidence_url") or normalized.get("trigger"):
                parsed.append(normalized)
    return parsed


def _canonical_explicit_lead_key(raw_key: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(raw_key or "").strip().lower()).strip("_")
    aliases = {
        "company": "company",
        "company_name": "company",
        "name": "company",
        "signal": "trigger",
        "signal_summary": "trigger",
        "trigger": "trigger",
        "trigger_summary": "trigger",
        "signal_source_url": "evidence_url",
        "source_url": "evidence_url",
        "evidence_url": "evidence_url",
        "lead_evidence_url": "evidence_url",
        "service_bucket": "opportunity_bucket_primary",
        "bucket": "opportunity_bucket_primary",
        "primary_bucket": "opportunity_bucket_primary",
        "opportunity_bucket_primary": "opportunity_bucket_primary",
        "country": "country",
        "source": "source",
        "fetched_at": "fetched_at",
        "verdict": "verdict",
    }
    return aliases.get(normalized)


def normalize_lead_aliases(lead: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(lead or {})
    alias_map = {
        "company_name": "company",
        "signal_summary": "trigger",
        "signal": "trigger",
        "signal_source_url": "evidence_url",
        "source_url": "evidence_url",
        "service_bucket": "opportunity_bucket_primary",
        "bucket": "opportunity_bucket_primary",
    }
    for old_key, new_key in alias_map.items():
        if normalized.get(old_key) and not normalized.get(new_key):
            normalized[new_key] = normalized[old_key]
    if normalized.get("opportunity_bucket_primary") and not normalized.get("onebt_fit"):
        normalized["onebt_fit"] = [normalized["opportunity_bucket_primary"]]
    return normalized


def _explicit_lead_parser_warnings(parsed_leads: list[dict[str, Any]], lead_text: str) -> list[str]:
    warnings: list[str] = []
    if not parsed_leads:
        warnings.append("No explicit leads were parsed from the supplied text.")
    for index, lead in enumerate(parsed_leads, start=1):
        if not lead.get("company"):
            warnings.append(f"Lead {index} did not include company_name/company.")
        if not lead.get("evidence_url"):
            warnings.append(f"Lead {index} did not include signal_source_url/evidence_url.")
    if "Lead 2" in str(lead_text) and len(parsed_leads) < 2:
        warnings.append("Input appeared to contain multiple lead blocks, but fewer were parsed.")
    return warnings


def group_leads_by_company(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for lead in leads:
        normalized = normalize_lead(lead)
        key = normalized["company"].lower()
        signal = normalized.get("trigger") or normalized.get("trigger_summary") or ""
        if key not in grouped:
            grouped[key] = {
                **normalized,
                "signals": [signal] if signal else [],
                "signal_count": 1,
                "lead_evidence_urls": [normalized["evidence_url"]] if normalized.get("evidence_url") else [],
            }
            continue
        existing = grouped[key]
        if signal and signal not in existing["signals"]:
            existing["signals"].append(signal)
        existing["signal_count"] = int(existing.get("signal_count") or 1) + 1
        if normalized.get("evidence_url") and normalized["evidence_url"] not in existing["lead_evidence_urls"]:
            existing["lead_evidence_urls"].append(normalized["evidence_url"])
        buckets = _lead_buckets(existing) + _lead_buckets(normalized)
        clean_buckets: list[str] = []
        for bucket in buckets:
            display = bucket_display_name(bucket)
            if display != "unknown" and display not in clean_buckets:
                clean_buckets.append(display)
        if clean_buckets:
            existing["opportunity_bucket_primary"] = clean_buckets[0]
            existing["opportunity_bucket_secondary"] = clean_buckets[1:]
            existing["onebt_fit"] = clean_buckets
    return list(grouped.values())


def resolve_latest_contact_routes(
    max_leads: int = MAX_LEADS_DEFAULT,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Resolve latest opportunity-analysis leads. Dry-run is explicit only."""
    leads, source_path, source_kind = load_latest_or_sample_leads(
        max_leads=max_leads,
        allow_sample=dry_run,
    )
    if not leads and not dry_run:
        return {
            "agent": "Contact Resolver Agent",
            "dry_run": False,
            "live_web_search_enabled": False,
            "search_provider": "none",
            "requested_leads": 0,
            "resolved_count": 0,
            "results": [],
            "compact_output": "Contact routes found:\nNo verified latest live leads found.\nNext: Ready for draft only. Sending remains locked.",
            "error": "No latest verified live leads were available. Runtime contact resolution will not use sample contacts.",
            "input_source_path": str(source_path),
            "input_source_kind": source_kind,
            "sending_enabled": False,
        }
    result = resolve_contacts_for_leads(leads, max_leads=max_leads, dry_run=dry_run)
    result["input_source_path"] = str(source_path)
    result["input_source_kind"] = source_kind
    return result


def find_contact_route_for_company(
    company: str,
    max_leads: int = MAX_LEADS_DEFAULT,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Find a contact route for a named company from latest live leads unless dry-run is explicit."""
    leads, source_path, source_kind = load_latest_or_sample_leads(
        max_leads=MAX_LEADS_HARD_CAP,
        allow_sample=dry_run,
    )
    company_norm = normalize_company_name(company).lower()
    matches = [
        lead for lead in leads if company_norm in normalize_company_name(lead.get("company")).lower()
    ]
    selected = matches if matches else []
    if not selected:
        return {
            "agent": "Contact Resolver Agent",
            "dry_run": dry_run,
            "live_web_search_enabled": False,
            "company": company,
            "resolved_count": 0,
            "results": [],
            "compact_output": (
                "Contact routes found:\n"
                f"No verified latest live lead matched {company}.\n"
                "Next: Ready for draft only. Sending remains locked."
            ),
            "error": "No matching lead found in latest live lead context.",
            "input_source_path": str(source_path),
            "input_source_kind": source_kind,
            "sending_enabled": False,
        }
    result = resolve_contacts_for_leads(selected, max_leads=max_leads, dry_run=dry_run)
    result["input_source_path"] = str(source_path)
    result["input_source_kind"] = source_kind
    return result


def show_contact_resolver_dry_run(max_leads: int = MAX_LEADS_DEFAULT) -> dict[str, Any]:
    """Run the PROMPT#10 dry-run sample without live web search."""
    leads = load_prompt10_sample_leads()
    result = resolve_contacts_for_leads(leads, max_leads=max_leads, dry_run=True)
    result["input_source_path"] = str(PROMPT10_SAMPLE_INPUT_PATH)
    result["input_source_kind"] = "prompt10_dry_run_fixture"
    return result


def refuse_contact_resolver_sending(request_summary: str = "") -> dict[str, Any]:
    """Refuse sending from the Contact Resolver Agent."""
    return {
        "agent": "Contact Resolver Agent",
        "sent": False,
        "sending_enabled": False,
        "request_summary": request_summary,
        "refusal_reason": (
            "No. Contact Resolver only resolves contact routes. Sending to leads is still locked."
        ),
        "compliance_notes": COMPLIANCE_NOTES,
    }


def run_hunter_candidate_loss_audit(
    domain: str = "wso2.com",
    company_name: str | None = None,
    service_bucket: str | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    """Diagnostic tool: show safe Hunter candidate filtering before/after selection."""
    clean_domain = normalize_company_domain(domain)
    hunter = HunterContactEnrichmentProvider.from_env()
    company = company_name or clean_domain or str(domain or "unknown")
    normalized = normalize_lead(
        {
            "company": company,
            "evidence_url": f"https://{clean_domain}" if clean_domain else None,
            "opportunity_bucket_primary": service_bucket or "Custom Software Development",
            "onebt_fit": [service_bucket] if service_bucket else ["Custom Software Development"],
        }
    )
    personas = merge_personas_for_lead(normalized)
    target_personas = [item["persona"] for item in personas]
    hunter_state = _new_hunter_state(hunter, audit_mode=True)
    if not clean_domain:
        result = {
            "tool": "run_hunter_candidate_loss_audit",
            "domain": domain,
            "company": company,
            "hunter_configured": bool(hunter.configured),
            "hunter_status": HUNTER_NOT_FOUND,
            "error": "valid_company_domain_required",
            "candidate_loss_audit": _build_candidate_loss_audit(
                hunter_state,
                final_candidates=[],
                best_route={"reason": "No valid domain was supplied.", "type": "no_contact_found"},
            ),
            "sending_enabled": False,
        }
        return assert_no_secret_patterns(result)
    if not hunter.configured:
        best_route = {
            "type": "no_contact_found",
            "email": None,
            "url": f"https://{clean_domain}",
            "confidence": 0,
            "reason": "Hunter is not configured; normal public search behavior remains available.",
        }
        audit = _build_candidate_loss_audit(hunter_state, final_candidates=[], best_route=best_route)
        result = {
            "tool": "run_hunter_candidate_loss_audit",
            "domain": clean_domain,
            "company": company,
            "hunter_configured": False,
            "hunter_status": HUNTER_NOT_CONFIGURED,
            "compact_candidate_audit_table": _format_hunter_audit_table(audit),
            "selected_route": best_route,
            "top_rejected_candidates": [],
            "high_confidence_candidate_rejected": False,
            "filters_appear_too_strict": False,
            "candidate_loss_audit": audit,
            "sending_enabled": False,
        }
        return assert_no_secret_patterns(result)

    hunter_state["domain_search_attempted"] = True
    hunter_state["domains_attempted"].append(clean_domain)
    lookup = hunter.domain_search(clean_domain, limit=max(1, min(int(top_n or 10), 10)))
    _merge_hunter_lookup_result(hunter_state, lookup)
    candidates: list[dict[str, Any]] = []
    for record in lookup.emails:
        candidate = _hunter_record_to_candidate(
            record,
            normalized=normalized,
            target_personas=target_personas,
            endpoint="domain_search",
        )
        _record_hunter_candidate_audit(
            hunter_state,
            record,
            normalized=normalized,
            endpoint="domain_search",
            candidate=candidate,
        )
        if candidate:
            candidates.append(candidate)
    final_candidates = _sort_candidates(_dedupe_candidates(candidates))[: max(1, min(int(top_n or 10), 10))]
    for index, candidate in enumerate(final_candidates):
        candidate["recommended"] = index == 0
        _strip_internal_candidate_fields(candidate)
    best_route = build_best_contact_route(final_candidates, normalized)
    audit = _build_candidate_loss_audit(hunter_state, final_candidates=final_candidates, best_route=best_route)
    result = {
        "tool": "run_hunter_candidate_loss_audit",
        "domain": clean_domain,
        "company": normalized["company"],
        "service_bucket": normalized["opportunity_bucket_primary"],
        "hunter_configured": True,
        "hunter_status": lookup.status,
        "raw_hunter_results_count": len(lookup.emails),
        "compact_candidate_audit_table": _format_hunter_audit_table(audit),
        "selected_route": best_route,
        "top_rejected_candidates": audit["top_rejected_candidates"],
        "high_confidence_candidate_rejected": audit["high_confidence_candidate_rejected"],
        "filters_appear_too_strict": audit["filters_appear_too_strict"],
        "candidate_loss_audit": audit,
        "sending_enabled": False,
    }
    return assert_no_secret_patterns(result)


def _resolve_contact_route_for_lead(
    lead: dict[str, Any],
    *,
    provider: ContactSearchProvider,
    dry_run: bool,
    max_search_queries: int,
    max_pages_to_fetch: int,
    max_candidate_contacts: int,
    max_runtime_seconds: int,
    audit_mode: bool = False,
) -> dict[str, Any]:
    start = time.monotonic()
    normalized = normalize_lead(lead)
    personas = merge_personas_for_lead(normalized)
    target_personas = [item["persona"] for item in personas]
    role_terms_to_attempt = named_roles_for_trace(personas)
    queries = (
        build_search_queries(normalized, personas, max_search_queries=max_search_queries)
        if dry_run
        else build_live_search_queries(normalized, personas, max_search_queries=max_search_queries)
    )
    candidates: list[dict[str, Any]] = []
    queries_attempted: list[str] = []
    sources_checked: list[str] = []
    search_trace: list[dict[str, Any]] = []
    pages_checked = 0
    consecutive_no_new = 0
    stopped_reason = "search_provider_not_configured" if dry_run else "live_provider_unavailable"
    setup_message = None
    observed_emails: list[str] = []
    named_roles_attempted: list[str] = []
    hunter = (
        HunterContactEnrichmentProvider.from_env()
        if _should_use_hunter_enrichment(provider=provider, dry_run=dry_run)
        else HunterContactEnrichmentProvider(api_key="")
    )
    hunter_state = _new_hunter_state(hunter, audit_mode=audit_mode)

    if provider.configured:
        stopped_reason = "search_budget_exhausted"
        seed_urls = []
        if normalized.get("evidence_url"):
            seed_urls.append(normalized["evidence_url"])

        for seed_url in seed_urls:
            if pages_checked >= max_pages_to_fetch:
                break
            page = provider.fetch_page(seed_url)
            pages_checked += 1
            sources_checked.append(page.url)
            search_trace.append(
                {
                    "type": "seed_fetch",
                    "url": page.url,
                    "status_code": page.fetched_at,
                    "text_chars": len(page.text or ""),
                }
            )
            _inspect_public_text_for_candidates(
                candidates=candidates,
                observed_emails=observed_emails,
                text=page.text,
                url=page.url,
                normalized=normalized,
                target_personas=target_personas,
                provider=provider,
                route_hint=_route_hint_for_url(page.url),
                source_kind=(
                    "job_post"
                    if _route_hint_for_url(page.url) == "job_post_apply"
                    else "public_web"
                ),
            )
            _apply_hunter_enrichment(
                candidates=candidates,
                observed_emails=observed_emails,
                sources_checked=sources_checked,
                search_trace=search_trace,
                normalized=normalized,
                target_personas=target_personas,
                hunter=hunter,
                hunter_state=hunter_state,
            )

        for query in queries:
            if len(queries_attempted) >= max_search_queries:
                break
            if time.monotonic() - start >= max_runtime_seconds:
                stopped_reason = "runtime_budget_exhausted"
                break
            queries_attempted.append(query)
            role_terms_in_query = named_role_terms_in_query(query, role_terms_to_attempt)
            for role_term in role_terms_in_query:
                if role_term not in named_roles_attempted:
                    named_roles_attempted.append(role_term)
            before_count = len(candidates)
            results = provider.search_web(query, limit=5)
            search_trace.append(
                {
                    "type": "search",
                    "query": query,
                    "result_count": len(results),
                    "provider": provider.name,
                    "named_role_terms": role_terms_in_query,
                }
            )
            for result in results:
                _inspect_public_text_for_candidates(
                    candidates=candidates,
                    observed_emails=observed_emails,
                    text=f"{result.title}\n{result.snippet}",
                    url=result.url,
                    normalized=normalized,
                    target_personas=target_personas,
                    provider=provider,
                    route_hint=_route_hint_for_url(result.url),
                    source_kind="public_professional" if "linkedin.com" in result.url.lower() else "public_web",
                )
                if pages_checked >= max_pages_to_fetch:
                    break
                if time.monotonic() - start >= max_runtime_seconds:
                    stopped_reason = "runtime_budget_exhausted"
                    break
                page = provider.fetch_page(result.url)
                pages_checked += 1
                sources_checked.append(page.url)
                search_trace.append(
                    {
                        "type": "page_fetch",
                        "url": page.url,
                        "status_code": page.fetched_at,
                        "text_chars": len(page.text or ""),
                    }
                )
                _inspect_public_text_for_candidates(
                    candidates=candidates,
                    observed_emails=observed_emails,
                    text=page.text,
                    url=page.url,
                    normalized=normalized,
                    target_personas=target_personas,
                    provider=provider,
                    route_hint=_route_hint_for_url(page.url),
                    source_kind=(
                        "official_company"
                        if is_likely_official_company_url(page.url, normalized["company"])
                        else "public_web"
                    ),
                )
                for likely_url in likely_official_child_urls(page.url, normalized["company"]):
                    if pages_checked >= max_pages_to_fetch:
                        break
                    if likely_url in sources_checked:
                        continue
                    likely_page = provider.fetch_page(likely_url)
                    pages_checked += 1
                    sources_checked.append(likely_page.url)
                    search_trace.append(
                        {
                            "type": "likely_page_fetch",
                            "url": likely_page.url,
                            "status_code": likely_page.fetched_at,
                            "text_chars": len(likely_page.text or ""),
                        }
                    )
                    _inspect_public_text_for_candidates(
                        candidates=candidates,
                        observed_emails=observed_emails,
                        text=likely_page.text,
                        url=likely_page.url,
                        normalized=normalized,
                        target_personas=target_personas,
                        provider=provider,
                        route_hint=_route_hint_for_url(likely_page.url),
                        source_kind="official_company",
                    )

            if len(candidates) == before_count:
                consecutive_no_new += 1
            else:
                consecutive_no_new = 0
            candidates = _dedupe_candidates(candidates)
            _apply_hunter_enrichment(
                candidates=candidates,
                observed_emails=observed_emails,
                sources_checked=sources_checked,
                search_trace=search_trace,
                normalized=normalized,
                target_personas=target_personas,
                hunter=hunter,
                hunter_state=hunter_state,
            )
            candidates = _sort_candidates(candidates)[:max_candidate_contacts]
            if candidates:
                top = candidates[0]
                if (
                    top.get("name")
                    and top.get("email_type") == "public_named"
                    and top.get("confidence", 0) >= 80
                ):
                    stopped_reason = "found_high_confidence_named_email"
                    break
                if top.get("name") and top.get("confidence", 0) >= 70:
                    stopped_reason = "found_strong_named_contact_route"
                    break
            if consecutive_no_new >= 3:
                if len(named_roles_attempted) >= 3 or dry_run:
                    stopped_reason = "no_new_evidence_three_queries"
                    break
            if pages_checked >= max_pages_to_fetch and len(named_roles_attempted) >= 3:
                break
        if candidates and not any(candidate.get("name") for candidate in candidates) and named_roles_attempted:
            stopped_reason = "only_generic_contact_route_available_after_budget"
    else:
        setup_message = getattr(provider, "unavailable_reason", None)
        search_trace.append(
            {
                "type": "provider_unavailable",
                "provider": provider.name,
                "message": setup_message,
            }
        )

    _apply_hunter_enrichment(
        candidates=candidates,
        observed_emails=observed_emails,
        sources_checked=sources_checked,
        search_trace=search_trace,
        normalized=normalized,
        target_personas=target_personas,
        hunter=hunter,
        hunter_state=hunter_state,
    )

    candidates = _sort_candidates(_dedupe_candidates(candidates))[:max_candidate_contacts]
    for index, candidate in enumerate(candidates):
        candidate["recommended"] = index == 0
        candidate.setdefault("risk_notes", [])
        _strip_internal_candidate_fields(candidate)

    best_route = build_best_contact_route(candidates, normalized)
    fallback_route = build_fallback_contact_route(candidates, normalized)
    candidate_loss_audit = _build_candidate_loss_audit(
        hunter_state,
        final_candidates=candidates,
        best_route=best_route,
    )
    generic_fallback_used = best_route.get("type") == "generic_company"
    search_trace.append(
        {
            "type": "resolution_summary",
            "emails_extracted": observed_emails,
            "named_roles_attempted": named_roles_attempted,
            "named_person_search_attempted": bool(named_roles_attempted),
            "final_route_type": best_route.get("type"),
            "final_route_confidence": best_route.get("confidence"),
            "why_final_route_chosen": best_route.get("reason"),
            "generic_fallback_used": generic_fallback_used,
            "generic_fallback_reason": (
                "No named role-relevant buyer was found within the search budget."
                if generic_fallback_used
                else None
            ),
            "hunter_status": hunter_state["status"],
            "hunter_domains_attempted": hunter_state["domains_attempted"],
            "hunter_sources": hunter_state["source_urls"],
        }
    )
    result = {
        "company": normalized["company"],
        "lead_evidence_url": normalized["evidence_url"],
        "opportunity_bucket_primary": normalized["opportunity_bucket_primary"],
        "verdict": normalized.get("verdict") or "unknown",
        "signal_count": int(normalized.get("signal_count") or 1),
        "signals": normalized.get("signals") or [normalized.get("trigger") or normalized.get("trigger_summary")],
        "ideal_buyer_personas": personas,
        "candidate_contacts": candidates,
        "best_contact_route": best_route,
        "fallback_contact_route": fallback_route,
        "do_not_claim": DEFAULT_DO_NOT_CLAIM,
        "compliance_notes": COMPLIANCE_NOTES,
        "search_summary": {
            "queries_attempted": queries_attempted,
            "sources_checked": sources_checked,
            "timeboxed": True,
            "stopped_reason": stopped_reason,
            "search_provider": provider.name,
            "live_web_search_enabled": bool(provider.configured),
            "dry_run": dry_run,
            "setup_message": setup_message,
            "named_person_search_attempted": bool(named_roles_attempted),
            "named_roles_attempted": named_roles_attempted,
            "generic_fallback_after_named_search": generic_fallback_used and bool(named_roles_attempted),
            "hunter_configured": hunter_state["configured"],
            "hunter_status": hunter_state["status"],
            "hunter_domain_search_attempted": hunter_state["domain_search_attempted"],
            "hunter_email_finder_attempted": hunter_state["email_finder_attempted"],
            "hunter_domains_attempted": hunter_state["domains_attempted"],
            "hunter_sources": hunter_state["source_urls"],
            "hunter_errors": hunter_state["errors"],
            "budgets": {
                "max_search_queries": max_search_queries,
                "max_pages_to_fetch": max_pages_to_fetch,
                "max_candidate_contacts": max_candidate_contacts,
                "max_runtime_seconds": max_runtime_seconds,
            },
        },
        "search_trace": search_trace,
        "adk_display": format_compact_contact_resolution(
            normalized,
            personas,
            best_route,
            fallback_route,
            queries_attempted=queries_attempted,
            sources_checked=sources_checked,
        ),
    }
    if audit_mode:
        result["candidate_loss_audit"] = candidate_loss_audit
    return assert_no_secret_patterns(result)


def _new_hunter_state(
    hunter: HunterContactEnrichmentProvider,
    *,
    audit_mode: bool = False,
) -> dict[str, Any]:
    return {
        "configured": bool(hunter.configured),
        "status": HUNTER_NOT_FOUND if hunter.configured else HUNTER_NOT_CONFIGURED,
        "domain_search_attempted": False,
        "email_finder_attempted": False,
        "domains_attempted": [],
        "email_finder_names_attempted": [],
        "source_urls": [],
        "errors": [],
        "audit_mode": bool(audit_mode),
        "candidate_audit_entries": [],
    }


def _should_use_hunter_enrichment(
    *,
    provider: ContactSearchProvider,
    dry_run: bool,
) -> bool:
    if dry_run:
        return False
    return isinstance(provider, LiveContactSearchProviderAdapter)


def _apply_hunter_enrichment(
    *,
    candidates: list[dict[str, Any]],
    observed_emails: list[str],
    sources_checked: list[str],
    search_trace: list[dict[str, Any]],
    normalized: dict[str, Any],
    target_personas: list[str],
    hunter: HunterContactEnrichmentProvider,
    hunter_state: dict[str, Any],
) -> None:
    if not hunter.configured:
        return
    domain = _select_company_domain(
        normalized=normalized,
        sources_checked=sources_checked,
        observed_emails=observed_emails,
        candidates=candidates,
    )
    if not domain:
        return

    if domain not in hunter_state["domains_attempted"]:
        hunter_state["domain_search_attempted"] = True
        hunter_state["domains_attempted"].append(domain)
        result = hunter.domain_search(domain, limit=10)
        _merge_hunter_lookup_result(hunter_state, result)
        search_trace.append(
            {
                "type": "hunter_domain_search",
                "domain": domain,
                "status": result.status,
                "email_count": len(result.emails),
                "source_urls": _hunter_lookup_source_urls(result),
                "error": result.error,
            }
        )
        for record in result.emails:
            candidate = _hunter_record_to_candidate(
                record,
                normalized=normalized,
                target_personas=target_personas,
                endpoint="domain_search",
            )
            _record_hunter_candidate_audit(
                hunter_state,
                record,
                normalized=normalized,
                endpoint="domain_search",
                candidate=candidate,
            )
            if candidate:
                candidates.append(candidate)
                if candidate.get("email") and candidate["email"] not in observed_emails:
                    observed_emails.append(candidate["email"])

    _apply_hunter_email_finder(
        candidates=candidates,
        observed_emails=observed_emails,
        search_trace=search_trace,
        normalized=normalized,
        target_personas=target_personas,
        hunter=hunter,
        hunter_state=hunter_state,
        domain=domain,
    )


def _apply_hunter_email_finder(
    *,
    candidates: list[dict[str, Any]],
    observed_emails: list[str],
    search_trace: list[dict[str, Any]],
    normalized: dict[str, Any],
    target_personas: list[str],
    hunter: HunterContactEnrichmentProvider,
    hunter_state: dict[str, Any],
    domain: str,
) -> None:
    for candidate in list(candidates):
        name = str(candidate.get("name") or "").strip()
        if not name or candidate.get("email_type") == "public_named":
            continue
        if candidate.get("source_kind") == "hunter":
            continue
        first_name, last_name = split_person_name(name)
        if not first_name or not last_name:
            continue
        attempt_key = f"{domain}:{name.lower()}"
        if attempt_key in hunter_state["email_finder_names_attempted"]:
            continue
        hunter_state["email_finder_attempted"] = True
        hunter_state["email_finder_names_attempted"].append(attempt_key)
        result = hunter.email_finder(
            domain=domain,
            first_name=first_name,
            last_name=last_name,
            max_duration=3,
        )
        _merge_hunter_lookup_result(hunter_state, result)
        search_trace.append(
            {
                "type": "hunter_email_finder",
                "domain": domain,
                "name": name,
                "status": result.status,
                "email_found": bool(result.emails),
                "source_urls": _hunter_lookup_source_urls(result),
                "error": result.error,
            }
        )
        if not result.emails:
            continue
        record = result.emails[0]
        rejection_reason = _hunter_record_rejection_reason(
            record,
            normalized=normalized,
            name=name,
            role=str(candidate.get("role") or record.position or record.department or ""),
        )
        if _is_explicitly_invalid_hunter_record(record):
            _record_hunter_candidate_audit(
                hunter_state,
                record,
                normalized=normalized,
                endpoint="email_finder",
                candidate=None,
                rejection_reason=rejection_reason,
            )
            continue
        filtered, risk_notes = filter_public_email(record.email, official_context=True)
        if not filtered:
            candidate.setdefault("risk_notes", []).extend(risk_notes)
            _record_hunter_candidate_audit(
                hunter_state,
                record,
                normalized=normalized,
                endpoint="email_finder",
                candidate=None,
                rejection_reason="email_rejected",
            )
            continue
        source_urls = list(
            dict.fromkeys(
                (candidate.get("source_urls") or [])
                + record.source_urls
                + ([record.linkedin_url] if record.linkedin_url else [])
            )
        )
        hunter_evidence_urls = list(
            dict.fromkeys(record.source_urls + ([record.linkedin_url] if record.linkedin_url else []))
        )
        if record.hunter_status == HUNTER_FOUND and not _is_acceptable_unverified_hunter_record(
            record,
            filtered_email=filtered,
            name=name,
            role=str(candidate.get("role") or record.position or record.department or ""),
            evidence_urls=hunter_evidence_urls,
        ):
            _record_hunter_candidate_audit(
                hunter_state,
                record,
                normalized=normalized,
                endpoint="email_finder",
                candidate=None,
                rejection_reason=rejection_reason,
            )
            continue
        candidate.update(
            {
                "email": filtered,
                "email_type": "public_named",
                "contact_url": candidate.get("contact_url") or (source_urls[0] if source_urls else None),
                "source_urls": source_urls or candidate.get("source_urls") or [],
                "hunter_status": record.hunter_status,
                "hunter_verification_status": record.verification_status,
                "hunter_confidence": record.confidence,
                "hunter_sources": record.source_urls,
                "hunter_endpoint": "email_finder",
                "source_kind": "hunter",
            }
        )
        candidate.setdefault("risk_notes", []).extend(risk_notes)
        scored = _score_hunter_candidate(
            candidate,
            target_personas=target_personas,
            ambiguous_company=normalized["ambiguous_company"],
            stale_evidence=normalized["stale_evidence"],
        )
        candidate.update(scored)
        _record_hunter_candidate_audit(
            hunter_state,
            record,
            normalized=normalized,
            endpoint="email_finder",
            candidate=candidate,
        )
        if filtered not in observed_emails:
            observed_emails.append(filtered)


def _select_company_domain(
    *,
    normalized: dict[str, Any],
    sources_checked: list[str],
    observed_emails: list[str],
    candidates: list[dict[str, Any]],
) -> str | None:
    domains: list[str] = []

    def add_domain(value: Any) -> None:
        domain = normalize_company_domain(value)
        if not domain or domain in PERSONAL_EMAIL_DOMAINS:
            return
        if domain not in domains:
            domains.append(domain)

    for email in observed_emails:
        if email_domain(email) and not is_personal_email_domain(email):
            add_domain(email_domain(email))
    for candidate in candidates:
        if candidate.get("email") and not is_personal_email_domain(candidate.get("email")):
            add_domain(email_domain(candidate.get("email")))
        for url in [*(candidate.get("source_urls") or []), candidate.get("contact_url")]:
            if url and is_likely_official_company_url(str(url), normalized["company"]):
                add_domain(url)
    for url in sources_checked:
        if url and is_likely_official_company_url(str(url), normalized["company"]):
            add_domain(url)
    return domains[0] if domains else None


def _hunter_record_to_candidate(
    record: HunterEmailRecord,
    *,
    normalized: dict[str, Any],
    target_personas: list[str],
    endpoint: str,
) -> dict[str, Any] | None:
    if _is_explicitly_invalid_hunter_record(record):
        return None
    filtered, risk_notes = filter_public_email(record.email, official_context=True)
    if not filtered:
        return None
    record_domain = normalize_company_domain(record.domain or filtered)
    email_record_domain = normalize_company_domain(filtered)
    if record_domain and email_record_domain and record_domain != email_record_domain:
        return None
    name = record.full_name if record.full_name and _is_plausible_person_name(record.full_name) else None
    role = record.position or record.department
    hunter_evidence_urls = list(
        dict.fromkeys(record.source_urls + ([record.linkedin_url] if record.linkedin_url else []))
    )
    if record.hunter_status == HUNTER_FOUND and not _is_acceptable_unverified_hunter_record(
        record,
        filtered_email=filtered,
        name=name,
        role=role,
        evidence_urls=hunter_evidence_urls,
    ):
        return None
    source_urls = list(hunter_evidence_urls)
    if not source_urls and record.domain:
        source_urls = [f"https://{record.domain}"]
    route_type = "named_person" if name else "generic_company"
    email_type = "public_named" if name and record.email_kind != "generic" else "public_generic"
    if not name and (
        record.email_kind == "generic"
        or email_local_part(filtered) in {"careers", "hr", "jobs", "recruitment", "recruiting"}
    ):
        route_type = (
            "role_department"
            if email_local_part(filtered) in {"careers", "hr", "jobs", "recruitment", "recruiting"}
            else "generic_company"
        )
        role = role or "Hunter domain search company route"
    candidate = {
        "name": name,
        "role": role or ("Hunter named contact" if name else "Hunter company contact route"),
        "company": normalized["company"],
        "email": filtered,
        "email_type": email_type,
        "contact_url": source_urls[0] if source_urls else None,
        "linkedin_url": record.linkedin_url,
        "source_urls": source_urls,
        "evidence_summary": (
            "Hunter returned this contact route from Domain Search."
            if endpoint == "domain_search"
            else "Hunter returned this contact route from Email Finder."
        ),
        "recommended": False,
        "risk_notes": risk_notes,
        "route_type": route_type,
        "source_kind": "hunter",
        "hunter_status": record.hunter_status,
        "hunter_verification_status": record.verification_status,
        "hunter_confidence": record.confidence,
        "hunter_sources": record.source_urls,
        "hunter_endpoint": endpoint,
    }
    return _score_hunter_candidate(
        candidate,
        target_personas=target_personas,
        ambiguous_company=normalized["ambiguous_company"],
        stale_evidence=normalized["stale_evidence"],
    )


def _record_hunter_candidate_audit(
    hunter_state: dict[str, Any],
    record: HunterEmailRecord,
    *,
    normalized: dict[str, Any],
    endpoint: str,
    candidate: dict[str, Any] | None,
    rejection_reason: str | None = None,
) -> None:
    if not hunter_state.get("audit_mode"):
        return
    accepted = bool(candidate)
    reason = "accepted" if accepted else (
        rejection_reason
        or _hunter_record_rejection_reason(
            record,
            normalized=normalized,
            name=record.full_name,
            role=record.position or record.department,
        )
    )
    hunter_state.setdefault("candidate_audit_entries", []).append(
        _hunter_candidate_audit_entry(
            record,
            normalized=normalized,
            endpoint=endpoint,
            accepted=accepted,
            rejection_reason=reason,
            candidate=candidate,
        )
    )


def _hunter_candidate_audit_entry(
    record: HunterEmailRecord,
    *,
    normalized: dict[str, Any],
    endpoint: str,
    accepted: bool,
    rejection_reason: str,
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    email = str(record.email or "").strip().lower()
    sources = _hunter_record_evidence_urls(record)
    return {
        "company": normalized.get("company") or "unknown",
        "email_domain": email_domain(email) or normalize_company_domain(record.domain),
        "email_masked": mask_email_for_audit(email),
        "email": None,
        "name": (candidate or {}).get("name") or record.full_name,
        "role": (candidate or {}).get("role") or record.position or record.department,
        "hunter_confidence": record.confidence,
        "verification_status": record.verification_status,
        "hunter_status": record.hunter_status,
        "source_count": len(sources),
        "source_domains": source_domains_for_audit(sources),
        "accepted": accepted,
        "rejected": not accepted,
        "rejection_reason": None if accepted else rejection_reason,
        "final_rank": None,
        "endpoint": endpoint,
    }


def _hunter_record_rejection_reason(
    record: HunterEmailRecord,
    *,
    normalized: dict[str, Any],
    name: str | None,
    role: str | None,
) -> str:
    if _is_explicitly_invalid_hunter_record(record):
        return "invalid_verification"
    filtered, _risk_notes = filter_public_email(record.email, official_context=True)
    if not filtered:
        return "email_rejected"
    record_domain = normalize_company_domain(record.domain or filtered)
    email_record_domain = normalize_company_domain(filtered)
    if record_domain and email_record_domain and record_domain != email_record_domain:
        return "domain_mismatch"
    if record.hunter_status == HUNTER_FOUND:
        if not name or not _is_plausible_person_name(str(name)):
            return "no_name"
        if not role:
            return "no_role"
        if record.confidence is None or int(record.confidence) < 90:
            return "unknown_low_confidence"
        if not _hunter_record_evidence_urls(record):
            return "no_evidence"
    return "not_selected"


def _build_candidate_loss_audit(
    hunter_state: dict[str, Any],
    *,
    final_candidates: list[dict[str, Any]],
    best_route: dict[str, Any],
) -> dict[str, Any]:
    entries = [dict(entry) for entry in hunter_state.get("candidate_audit_entries", [])]
    final_email_ranks = {
        str(candidate.get("email") or "").lower(): index + 1
        for index, candidate in enumerate(final_candidates)
        if candidate.get("email")
    }
    final_output_emails = set(final_email_ranks)
    for entry in entries:
        masked = entry.get("email_masked") or ""
        domain = entry.get("email_domain") or ""
        matching_email = next(
            (
                email
                for email in final_output_emails
                if email_domain(email) == domain and mask_email_for_audit(email) == masked
            ),
            None,
        )
        if matching_email:
            entry["final_rank"] = final_email_ranks[matching_email]
            entry["email"] = matching_email
    raw_count = len(entries)
    invalid_rejected = sum(1 for item in entries if item.get("rejection_reason") == "invalid_verification")
    unknown_rejected = sum(
        1
        for item in entries
        if not item.get("accepted")
        and str(item.get("verification_status") or "").strip().lower() in {"", "unknown", "none"}
    )
    unknown_accepted = sum(
        1
        for item in entries
        if item.get("accepted")
        and str(item.get("verification_status") or "").strip().lower() in {"", "unknown", "none"}
    )
    valid_accepted = sum(
        1
        for item in entries
        if item.get("accepted") and str(item.get("verification_status") or "").strip().lower() == "valid"
    )
    high_confidence_rejected = [
        item
        for item in entries
        if not item.get("accepted") and int(item.get("hunter_confidence") or 0) >= 90
    ]
    chosen_reason = best_route.get("reason") or "No final route selected."
    return {
        "enabled": bool(hunter_state.get("audit_mode")),
        "raw_hunter_results_count": raw_count,
        "invalid_rejected_count": invalid_rejected,
        "unknown_rejected_count": unknown_rejected,
        "unknown_accepted_count": unknown_accepted,
        "valid_accepted_count": valid_accepted,
        "no_role_rejected_count": sum(1 for item in entries if item.get("rejection_reason") == "no_role"),
        "no_evidence_rejected_count": sum(1 for item in entries if item.get("rejection_reason") == "no_evidence"),
        "domain_mismatch_rejected_count": sum(1 for item in entries if item.get("rejection_reason") == "domain_mismatch"),
        "final_candidate_count": len([candidate for candidate in final_candidates if candidate.get("source_kind") == "hunter"]),
        "chosen_candidate_reason": chosen_reason,
        "high_confidence_candidate_rejected": bool(high_confidence_rejected),
        "filters_appear_too_strict": _filters_appear_too_strict(high_confidence_rejected),
        "candidates": entries,
        "top_rejected_candidates": high_confidence_rejected[:5]
        or [item for item in entries if not item.get("accepted")][:5],
    }


def _filters_appear_too_strict(high_confidence_rejected: list[dict[str, Any]]) -> bool:
    useful_reasons = {"no_role", "no_evidence", "unknown_low_confidence"}
    return any(item.get("rejection_reason") in useful_reasons for item in high_confidence_rejected)


def _hunter_record_evidence_urls(record: HunterEmailRecord) -> list[str]:
    return list(dict.fromkeys(record.source_urls + ([record.linkedin_url] if record.linkedin_url else [])))


def source_domains_for_audit(urls: list[str]) -> list[str]:
    domains: list[str] = []
    for url in urls:
        domain = normalize_company_domain(url)
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def mask_email_for_audit(email: str | None) -> str | None:
    value = str(email or "").strip().lower()
    if "@" not in value:
        return None
    local, domain = value.split("@", 1)
    if not local:
        return f"*@{domain}"
    if len(local) <= 2:
        masked = local[0] + "*"
    else:
        masked = local[0] + "***" + local[-1]
    return f"{masked}@{domain}"


def _format_hunter_audit_table(audit: dict[str, Any]) -> str:
    entries = audit.get("candidates") or []
    lines = [
        "Hunter candidate loss audit:",
        "| Company | Candidate | Role | Verification | Confidence | Sources | Decision | Reason | Rank |",
        "|---|---|---|---|---:|---:|---|---|---:|",
    ]
    for entry in entries[:10]:
        decision = "accepted" if entry.get("accepted") else "rejected"
        lines.append(
            "| {company} | {email} | {role} | {verification} | {confidence} | {sources} | {decision} | {reason} | {rank} |".format(
                company=_table_cell(entry.get("company")),
                email=_table_cell(entry.get("email") or entry.get("email_masked") or entry.get("email_domain")),
                role=_table_cell(entry.get("role") or "unknown"),
                verification=_table_cell(entry.get("verification_status") or "unknown"),
                confidence=int(entry.get("hunter_confidence") or 0),
                sources=int(entry.get("source_count") or 0),
                decision=decision,
                reason=_table_cell(entry.get("rejection_reason") or "selected"),
                rank=entry.get("final_rank") or "",
            )
        )
    if not entries:
        lines.append("| none | none | none | unknown | 0 | 0 | none | no Hunter candidates returned | |")
    lines.append(
        "Summary: raw={raw}, invalid_rejected={invalid}, unknown_accepted={unknown_ok}, "
        "unknown_rejected={unknown_bad}, valid_accepted={valid_ok}, final={final}.".format(
            raw=audit.get("raw_hunter_results_count", 0),
            invalid=audit.get("invalid_rejected_count", 0),
            unknown_ok=audit.get("unknown_accepted_count", 0),
            unknown_bad=audit.get("unknown_rejected_count", 0),
            valid_ok=audit.get("valid_accepted_count", 0),
            final=audit.get("final_candidate_count", 0),
        )
    )
    return "\n".join(lines)


def _is_explicitly_invalid_hunter_record(record: HunterEmailRecord) -> bool:
    return str(record.verification_status or "").strip().lower() == "invalid"


def _is_acceptable_unverified_hunter_record(
    record: HunterEmailRecord,
    *,
    filtered_email: str,
    name: str | None,
    role: str | None,
    evidence_urls: list[str],
) -> bool:
    if not filtered_email or not name or not role:
        return False
    if record.confidence is None or int(record.confidence) < 90:
        return False
    record_domain = normalize_company_domain(record.domain or filtered_email)
    email_record_domain = normalize_company_domain(filtered_email)
    if not record_domain or not email_record_domain or record_domain != email_record_domain:
        return False
    return bool(evidence_urls)


def _score_hunter_candidate(
    candidate: dict[str, Any],
    *,
    target_personas: list[str],
    ambiguous_company: bool,
    stale_evidence: bool,
) -> dict[str, Any]:
    scored = score_candidate_contact(
        candidate,
        target_personas=target_personas,
        ambiguous_company=ambiguous_company,
        stale_evidence=stale_evidence,
    )
    score = int(scored.get("confidence") or 0)
    role_match = role_matches_persona(scored.get("role"), target_personas)
    hunter_confidence = scored.get("hunter_confidence")
    if scored.get("route_type") == "named_person":
        if scored.get("hunter_status") == HUNTER_VERIFIED and role_match:
            score = max(score, 80)
        elif scored.get("hunter_status") == HUNTER_FOUND and role_match:
            score = max(score, 70)
        elif scored.get("hunter_status") == HUNTER_VERIFIED:
            score = max(score, 60)
        if isinstance(hunter_confidence, int):
            score = max(score, min(95 if role_match else 65, hunter_confidence))
        score = min(score, 95)
    else:
        score = min(max(score, 45 if scored.get("email") else 0), 45)
    scored["confidence"] = max(0, min(100, score))
    scored["confidence_label"] = confidence_label(scored["confidence"])
    return scored


def _merge_hunter_lookup_result(
    hunter_state: dict[str, Any],
    result: Any,
) -> None:
    hunter_state["status"] = _stronger_hunter_status(hunter_state["status"], result.status)
    if result.error and result.error not in hunter_state["errors"]:
        hunter_state["errors"].append(result.error)
    for url in _hunter_lookup_source_urls(result):
        if url not in hunter_state["source_urls"]:
            hunter_state["source_urls"].append(url)


def _hunter_lookup_source_urls(result: Any) -> list[str]:
    urls: list[str] = []
    for record in getattr(result, "emails", []) or []:
        for url in record.source_urls:
            if url not in urls:
                urls.append(url)
    return urls


def _stronger_hunter_status(current: str, new: str) -> str:
    priority = {
        HUNTER_NOT_CONFIGURED: 0,
        HUNTER_NOT_FOUND: 1,
        HUNTER_FOUND: 2,
        HUNTER_VERIFIED: 3,
    }
    return new if priority.get(new, 0) > priority.get(current, 0) else current


def _inspect_public_text_for_candidates(
    *,
    candidates: list[dict[str, Any]],
    observed_emails: list[str],
    text: str,
    url: str,
    normalized: dict[str, Any],
    target_personas: list[str],
    provider: ContactSearchProvider,
    route_hint: str,
    source_kind: str,
) -> None:
    if not text and route_hint not in {"contact_form", "job_post_apply"}:
        return
    page_is_official = source_kind == "official_company" or is_likely_official_company_url(
        url,
        normalized["company"],
    )
    emails = provider.extract_emails(text)
    observed_emails.extend(email for email in emails if email not in observed_emails)
    people = provider.extract_people_roles(text, normalized["company"], target_personas)
    for person in people:
        person.source_urls = list(dict.fromkeys([*person.source_urls, url]))
        person.contact_url = person.contact_url or url
        if "linkedin.com/in" in url.lower():
            person.linkedin_url = person.linkedin_url or url
        person.source_kind = "official_company" if page_is_official else source_kind
        person.stale_evidence = normalized["stale_evidence"]
        person.ambiguous_company = normalized["ambiguous_company"]
        if person.email:
            filtered, risk_notes = filter_public_email(
                person.email,
                official_context=page_is_official,
            )
            person.email = filtered
            person.risk_notes.extend(risk_notes)
            person.email_type = classify_email_type(filtered, person.name)
        scored = score_candidate_contact(
            person,
            target_personas=target_personas,
            ambiguous_company=normalized["ambiguous_company"],
            stale_evidence=normalized["stale_evidence"],
        )
        scored["route_type"] = "named_person"
        candidates.append(scored)

    for email in emails:
        # A public page can mention a partner, implementation vendor, recruiter,
        # or similarly named business. Do not turn those addresses into the
        # target company's contact route unless the page belongs to the target.
        if not page_is_official:
            continue
        filtered, risk_notes = filter_public_email(email, official_context=page_is_official)
        if not filtered:
            continue
        local = email_local_part(filtered)
        if local in {"careers", "hr", "jobs", "recruitment", "recruiting"}:
            route_type = "role_department"
            role = "Talent Acquisition / careers route"
            confidence = 55 if page_is_official else 40
            risk = ["Role-department inbox is a practical fallback, not a named buyer."]
        else:
            route_type = "generic_company"
            role = "Company contact inbox"
            confidence = 45 if page_is_official else 35
            risk = ["Generic inbox is a fallback, not an ideal buyer."]
        candidate = {
            "name": None,
            "role": role,
            "company": normalized["company"],
            "email": filtered,
            "email_type": classify_email_type(filtered),
            "contact_url": url,
            "linkedin_url": None,
            "source_urls": [url],
            "evidence_summary": "Public email observed on a checked public page.",
            "confidence": confidence,
            "confidence_label": confidence_label(confidence),
            "recommended": False,
            "risk_notes": risk_notes + risk,
            "route_type": route_type,
        }
        candidates.append(candidate)

    lowered = f"{url}\n{text}".lower()
    if route_hint == "contact_form" and page_is_official:
        _append_route_candidate(
            candidates,
            normalized=normalized,
            route_type="contact_form",
            role="Official contact page",
            url=url,
            confidence=40,
            evidence_summary="Official contact page or contact form route found.",
            risk_notes=["Contact form only; no named buyer found yet."],
        )
    if route_hint == "job_post_apply" and ("apply" in lowered or "job" in lowered):
        _append_route_candidate(
            candidates,
            normalized=normalized,
            route_type="job_post_apply",
            role="Job post apply/contact route",
            url=url,
            confidence=35,
            evidence_summary="Lead source job post provides an apply/contact route.",
            risk_notes=["Job-post apply route is a fallback, not a buyer contact."],
        )


def _append_route_candidate(
    candidates: list[dict[str, Any]],
    *,
    normalized: dict[str, Any],
    route_type: str,
    role: str,
    url: str,
    confidence: int,
    evidence_summary: str,
    risk_notes: list[str],
) -> None:
    candidates.append(
        {
            "name": None,
            "role": role,
            "company": normalized["company"],
            "email": None,
            "email_type": "unknown",
            "contact_url": url,
            "linkedin_url": None,
            "source_urls": [url],
            "evidence_summary": evidence_summary,
            "confidence": confidence,
            "confidence_label": confidence_label(confidence),
            "recommended": False,
            "risk_notes": risk_notes,
            "route_type": route_type,
        }
    )


def _route_hint_for_url(url: str) -> str:
    lowered = (url or "").lower()
    if any(token in lowered for token in ("/contact", "contact-us", "contactus")):
        return "contact_form"
    if any(token in lowered for token in ("career", "job", "vacanc", "apply")):
        return "job_post_apply"
    return "public_page"


def likely_official_child_urls(url: str, company: str) -> list[str]:
    normalized_url = normalize_public_url(url)
    if not normalized_url or not is_likely_official_company_url(normalized_url, company):
        return []
    parsed = urlparse(normalized_url)
    if not parsed.scheme or not parsed.netloc:
        return []
    root = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    paths = ["contact", "contact_us.html", "contact-us", "careers", "about", "team", "leadership"]
    return [f"{root}/{path}" for path in paths]


def normalize_lead(lead: dict[str, Any]) -> dict[str, Any]:
    lead = normalize_lead_aliases(lead if isinstance(lead, dict) else {})
    company = normalize_company_name(lead.get("company"))
    buckets = _lead_buckets(lead)
    primary_bucket = buckets[0] if buckets else "unknown"
    secondary_buckets = [bucket for bucket in buckets[1:] if bucket != primary_bucket]
    evidence_url = normalize_public_url(lead.get("evidence_url") or lead.get("lead_evidence_url") or "") or ""
    fetched_at = lead.get("fetched_at") or lead.get("created_at") or ""
    return {
        **lead,
        "company": company,
        "evidence_url": evidence_url,
        "opportunity_bucket_primary": bucket_display_name(primary_bucket),
        "opportunity_bucket_secondary": [bucket_display_name(bucket) for bucket in secondary_buckets],
        "stale_evidence": is_stale_date(fetched_at),
        "ambiguous_company": bool(
            lead.get("company_identity_ambiguous")
            or lead.get("ambiguous_company_identity")
            or lead.get("ambiguous_company")
        ),
    }


def _lead_buckets(lead: dict[str, Any]) -> list[str]:
    buckets: list[str] = []
    for key in (
        "opportunity_bucket_primary",
        "primary_bucket_display",
        "primary_bucket",
    ):
        if lead.get(key):
            buckets.append(str(lead[key]))
    for key in ("opportunity_bucket_secondary", "secondary_bucket_displays", "secondary_buckets", "onebt_fit"):
        value = lead.get(key) or []
        if isinstance(value, str):
            value = [value]
        buckets.extend(str(item) for item in value if item)
    clean: list[str] = []
    for bucket in buckets:
        if not is_service_bucket(bucket):
            continue
        display = bucket_display_name(bucket)
        if display not in clean:
            clean.append(display)
    if clean:
        return clean
    inferred = infer_service_buckets_from_signal(lead)
    return inferred or []


def is_stale_date(value: str | None, *, today: date | None = None) -> bool:
    if not value:
        return False
    today = today or date.today()
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    if not match:
        return False
    fetched = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return (today - fetched).days > 730


def is_likely_official_company_url(url: str, company: str) -> bool:
    normalized_url = normalize_public_url(url)
    if not normalized_url:
        return False
    host = urlparse(normalized_url).netloc.lower().removeprefix("www.")
    if not host:
        return False
    if any(
        blocked in host
        for blocked in (
            "facebook.com",
            "google.com",
            "linkedin.com",
            "microsoft.com",
        )
    ):
        return False
    host_parts = host.split(".")
    second_level_suffixes = {
        "ie": {"ac", "co", "edu", "gov", "org"},
        "uk": {"ac", "co", "gov", "org"},
    }
    if (
        len(host_parts) >= 3
        and host_parts[-1] in second_level_suffixes
        and host_parts[-2] in second_level_suffixes[host_parts[-1]]
    ):
        host_label = host_parts[-3]
    elif len(host_parts) >= 2:
        host_label = host_parts[-2]
    else:
        host_label = host_parts[0]
    host_label = re.sub(r"[^a-z0-9]", "", host_label)
    if not host_label:
        return False

    company_stopwords = {
        "and",
        "group",
        "homes",
        "housing",
        "ireland",
        "limited",
        "ltd",
        "mutual",
        "plc",
        "private",
        "pvt",
        "the",
        "uk",
        "university",
    }
    company_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", company.lower())
        if token not in company_stopwords
    ]
    first_word = re.split(r"\s+", company.strip(), maxsplit=1)[0] if company.strip() else ""
    first_word_flat = re.sub(r"[^a-z0-9]", "", first_word.lower())
    acronym = "".join(token[0] for token in company_tokens if token)
    parenthetical_brands = {
        re.sub(r"[^a-z0-9]", "", value.lower())
        for value in re.findall(r"\(([^)]+)\)", company)
    }
    brand_candidates = {
        token for token in company_tokens if len(token) >= 3
    }
    if len(first_word_flat) >= 2 and first_word.lower() not in company_stopwords:
        brand_candidates.add(first_word_flat)
    if len(acronym) >= 2:
        brand_candidates.add(acronym)
    brand_candidates.update(value for value in parenthetical_brands if len(value) >= 2)

    matched = next(
        (brand for brand in sorted(brand_candidates, key=len, reverse=True) if host_label.startswith(brand)),
        None,
    )
    if not matched:
        return False
    # These suffixes strongly indicate a different regional/legal entity when
    # they are absent from the requested company identity.
    company_flat = re.sub(r"[^a-z0-9]", "", company.lower())
    if host_label.endswith("llc") and "llc" not in company_flat:
        return False
    if host_label.endswith("nw") and not company_flat.endswith("nw"):
        return False
    return True


def _candidate_to_dict(candidate: dict[str, Any] | CandidatePerson) -> dict[str, Any]:
    if isinstance(candidate, CandidatePerson):
        return {
            "name": candidate.name,
            "role": candidate.role,
            "company": candidate.company,
            "email": candidate.email,
            "email_type": candidate.email_type,
            "contact_url": candidate.contact_url,
            "linkedin_url": candidate.linkedin_url,
            "source_urls": list(candidate.source_urls),
            "evidence_summary": candidate.evidence_summary,
            "confidence": 0,
            "confidence_label": "No usable contact",
            "recommended": False,
            "risk_notes": list(candidate.risk_notes),
            "source_kind": candidate.source_kind,
            "stale_evidence": candidate.stale_evidence,
            "ambiguous_company": candidate.ambiguous_company,
        }
    data = dict(candidate)
    data.setdefault("source_urls", [])
    data.setdefault("risk_notes", [])
    data.setdefault("recommended", False)
    data.setdefault("confidence", 0)
    data.setdefault("confidence_label", "No usable contact")
    return data


def _strip_internal_candidate_fields(candidate: dict[str, Any]) -> None:
    for key in ("stale_evidence", "ambiguous_company"):
        candidate.pop(key, None)


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        key = (
            str(candidate.get("name") or "").lower(),
            str(candidate.get("role") or "").lower(),
            str(candidate.get("email") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _sort_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=_candidate_sort_key,
    )


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
    return (
        _contact_route_priority(candidate),
        _hunter_verification_rank(candidate),
        -_sort_role_relevance(candidate),
        -int(candidate.get("hunter_confidence") or 0),
        -_executive_technology_relevance(candidate),
        -len(candidate.get("source_urls") or []),
    )


def _hunter_verification_rank(candidate: dict[str, Any]) -> int:
    status = candidate.get("hunter_status")
    verification = str(candidate.get("hunter_verification_status") or "").strip().lower()
    if status == HUNTER_VERIFIED or verification == "valid":
        return 0
    if status == HUNTER_FOUND:
        return 1
    if candidate.get("source_kind") == "hunter":
        return 2
    return 3


def _sort_role_relevance(candidate: dict[str, Any]) -> int:
    role = str(candidate.get("role") or "").lower()
    if not role:
        return 0
    if any(term in role for term in ("cto", "chief technology", "engineering", "architect", "technology")):
        return 4
    if any(term in role for term in ("customer success", "delivery", "integration", "api", "product")):
        return 3
    if any(term in role for term in ("director", "vp", "vice president", "head", "lead")):
        return 2
    if any(term in role for term in ("manager", "qa", "quality")):
        return 1
    return 0


def _executive_technology_relevance(candidate: dict[str, Any]) -> int:
    text = " ".join(
        str(candidate.get(key) or "")
        for key in ("role", "evidence_summary", "name")
    ).lower()
    score = 0
    if any(term in text for term in ("cto", "chief technology", "vp", "vice president", "director", "head")):
        score += 3
    if any(term in text for term in ("engineering", "technology", "architect", "software", "integration", "api")):
        score += 3
    if "customer success" in text:
        score += 2
    return score


def _contact_route_priority(candidate: dict[str, Any]) -> int:
    route_type = candidate.get("route_type") or ""
    if route_type == "named_person" and candidate.get("email_type") == "public_named":
        return 1
    if route_type == "named_person":
        return 2
    if route_type == "role_department":
        return 3
    if route_type == "job_post_apply" and _is_official_route(candidate):
        return 4
    if route_type == "generic_company":
        return 5
    if route_type == "contact_form":
        return 6
    if route_type == "job_post_apply":
        return 7
    return 8


def _is_official_route(candidate: dict[str, Any]) -> bool:
    urls = candidate.get("source_urls") or []
    url = candidate.get("contact_url") or (urls[0] if urls else "")
    company = candidate.get("company") or ""
    return bool(url and company and is_likely_official_company_url(str(url), str(company)))


def _apply_inferred_patterns(
    candidates: list[dict[str, Any]],
    observed_emails: list[str],
    target_personas: list[str],
) -> None:
    domains = [
        email_domain(email)
        for email in observed_emails
        if email_domain(email) and email_domain(email) not in PERSONAL_EMAIL_DOMAINS
    ]
    if not domains:
        return
    domain = domains[0]
    for candidate in candidates:
        if candidate.get("email") or not candidate.get("name"):
            continue
        inferred = infer_email_pattern(
            name=str(candidate["name"]),
            domain=domain,
            observed_emails=observed_emails,
        )
        if not inferred["email"]:
            continue
        candidate["email"] = inferred["email"]
        candidate["email_type"] = "inferred_pattern"
        candidate.setdefault("risk_notes", []).append(
            "Email is inferred from a public company pattern, not verified."
        )
        scored = score_candidate_contact(candidate, target_personas=target_personas)
        candidate.update(scored)


def build_best_contact_route(
    candidates: list[dict[str, Any]],
    lead: dict[str, Any],
) -> dict[str, Any]:
    if not candidates:
        return {
            "type": "no_contact_found",
            "name": None,
            "role": None,
            "email": None,
            "url": lead.get("evidence_url") or None,
            "reason": (
                "No public contact route was found because live search is unavailable or the search budget returned no contact evidence."
            ),
            "confidence": 0,
        }
    best = candidates[0]
    route_type = best.get("route_type")
    if not route_type:
        if best.get("name"):
            route_type = "named_person"
        elif best.get("email"):
            route_type = "generic_company"
        else:
            route_type = "role_department"
    return {
        "type": route_type,
        "route_type": route_type,
        "name": best.get("name"),
        "role": best.get("role"),
        "email": best.get("email"),
        "url": best.get("contact_url") or best.get("linkedin_url") or (best.get("source_urls") or [None])[0],
        "evidence_urls": best.get("source_urls") or [],
        "source": best.get("source_kind") or best.get("hunter_endpoint") or "public_web",
        "hunter_status": best.get("hunter_status"),
        "hunter_verification_status": best.get("hunter_verification_status"),
        "hunter_confidence": best.get("hunter_confidence"),
        "reason": _route_reason(best),
        "confidence": best.get("confidence", 0),
    }


def build_fallback_contact_route(
    candidates: list[dict[str, Any]],
    lead: dict[str, Any],
) -> dict[str, Any]:
    fallback = next((candidate for candidate in candidates[1:] if candidate.get("email") or candidate.get("contact_url")), None)
    if fallback:
        return {
            "type": "fallback_candidate",
            "email": fallback.get("email"),
            "url": fallback.get("contact_url") or (fallback.get("source_urls") or [None])[0],
            "reason": "Secondary public contact route found within the search budget.",
        }
    return {
        "type": "manual_verify_official_company_contact",
        "email": None,
        "url": lead.get("evidence_url") or None,
        "reason": "Verify the company website, contact page, careers page, or source job post before any outreach.",
    }


def _route_reason(candidate: dict[str, Any]) -> str:
    route_type = candidate.get("route_type")
    if candidate.get("hunter_status") == HUNTER_VERIFIED:
        return "Hunter returned this contact route with valid verification status and source-backed evidence where available."
    if candidate.get("hunter_status") == HUNTER_FOUND:
        return "Hunter returned this contact route; use the attached evidence sources where available."
    if candidate.get("name") and candidate.get("email_type") == "public_named":
        return "Named role-relevant contact with a public named business email."
    if candidate.get("name") and candidate.get("email_type") == "inferred_pattern":
        return "Named role-relevant contact with only an inferred business email pattern."
    if candidate.get("name"):
        return "Named role-relevant contact route found; verify before outreach."
    if route_type == "role_department":
        return "Role or department route found for the opportunity signal."
    if route_type == "contact_form":
        return "Official contact page or contact form found as a practical fallback."
    if route_type == "job_post_apply":
        return "Source job post apply/contact route found as a practical fallback."
    if candidate.get("email"):
        return "Generic company inbox found; use only as a fallback after buyer verification."
    return "Role or department route found without direct email."


def load_latest_or_sample_leads(
    *,
    max_leads: int = MAX_LEADS_DEFAULT,
    allow_sample: bool = False,
) -> tuple[list[dict[str, Any]], Path, str]:
    if LATEST_OPPORTUNITY_ANALYSIS_PATH.is_file():
        data = json.loads(LATEST_OPPORTUNITY_ANALYSIS_PATH.read_text(encoding="utf-8"))
        analyses = data.get("analyses") or []
        leads = [_analysis_to_contact_input(item) for item in analyses]
        return leads[: min(max_leads, MAX_LEADS_HARD_CAP)], LATEST_OPPORTUNITY_ANALYSIS_PATH, "latest_opportunity_analysis"
    if allow_sample:
        return load_prompt10_sample_leads()[:max_leads], PROMPT10_SAMPLE_INPUT_PATH, "prompt10_dry_run_fixture"
    return [], LATEST_OPPORTUNITY_ANALYSIS_PATH, "latest_opportunity_analysis_missing"


def load_prompt10_sample_leads() -> list[dict[str, Any]]:
    if PROMPT10_SAMPLE_INPUT_PATH.is_file():
        data = json.loads(PROMPT10_SAMPLE_INPUT_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return data.get("leads", [])
    return [prompt10_sample_lead()]


def prompt10_sample_lead() -> dict[str, Any]:
    return {
        "fixture_note": (
            "PROMPT#10 dry-run fixture derived from existing verified lead structure; "
            "contact resolution does not claim any live contact unless evidence is retrieved."
        ),
        "company": "Vs One World (Pvt) Ltd",
        "trigger": "QE Engineer - API & Integration",
        "evidence_url": "https://itpro.lk/job/13609/qe-engineer-api-integration-at-vs-one-world-pvt-ltd/",
        "source": "itpro.lk",
        "fetched_at": "2026-04-26",
        "score": None,
        "verdict": "Contact now",
        "onebt_fit": [
            "Staff Augmentation / Delivery Capacity",
            "Integrations / API / Middleware",
            "QA / Test Automation",
        ],
        "opportunity_bucket_primary": "Staff Augmentation / Delivery Capacity",
        "opportunity_bucket_secondary": [
            "Integrations / API / Middleware",
            "QA / Test Automation",
        ],
        "outreach_angle": (
            "Resolve the engineering or quality owner for a QE/API integration hiring signal."
        ),
    }


def _analysis_to_contact_input(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "company": analysis.get("company"),
        "trigger": analysis.get("trigger_summary") or analysis.get("trigger_type"),
        "evidence_url": analysis.get("evidence_url"),
        "source": analysis.get("source") or "opportunity_analysis",
        "fetched_at": analysis.get("fetched_at") or "",
        "score": analysis.get("bucket_scores"),
        "verdict": analysis.get("verdict") or "unknown",
        "onebt_fit": analysis.get("secondary_bucket_displays") or analysis.get("secondary_buckets") or [],
        "opportunity_bucket_primary": analysis.get("primary_bucket_display") or analysis.get("primary_bucket"),
        "opportunity_bucket_secondary": analysis.get("secondary_bucket_displays") or analysis.get("secondary_buckets") or [],
        "outreach_angle": analysis.get("recommended_outreach_theme") or analysis.get("email_positioning") or "",
    }


def format_compact_contact_resolution(
    lead: dict[str, Any],
    personas: list[dict[str, Any]],
    best_route: dict[str, Any],
    fallback_route: dict[str, Any],
    queries_attempted: list[str] | None = None,
    sources_checked: list[str] | None = None,
) -> str:
    result = {
        "company": lead.get("company"),
        "signal_count": int(lead.get("signal_count") or 1),
        "ideal_buyer_personas": personas,
        "best_contact_route": best_route,
        "fallback_contact_route": fallback_route,
        "search_summary": {
            "queries_attempted": queries_attempted or [],
            "sources_checked": sources_checked or [],
            "named_person_search_attempted": True,
            "named_roles_attempted": named_roles_for_trace(personas),
        },
    }
    return format_contact_routes_table([result])


def format_contact_routes_table(results: list[dict[str, Any]]) -> str:
    if not results:
        return (
            "Contact routes found:\n"
            "No usable contact routes found.\n"
            "Next: Ready for draft only. Sending remains locked."
        )
    any_named = any((item.get("best_contact_route") or {}).get("type") == "named_person" for item in results)
    lines = ["Contact routes found:"]
    if any_named:
        lines.extend(
            [
                "| Company | Best contact | Role | Email/route | Confidence | Evidence |",
                "|---|---|---|---|---:|---|",
            ]
        )
        for item in results:
            route = item.get("best_contact_route") or {}
            lines.append(
                "| {company} | {contact} | {role} | {route_value} | {confidence} | {evidence} |".format(
                    company=_table_cell(_company_label(item)),
                    contact=_table_cell(route.get("name") or route.get("email") or route.get("url") or "not found"),
                    role=_table_cell(route.get("role") or _route_type_label(route.get("type"))),
                    route_value=_table_cell(route.get("email") or route.get("url") or "none"),
                    confidence=int(route.get("confidence") or 0),
                    evidence=_table_cell(route.get("url") or item.get("lead_evidence_url") or "missing"),
                )
            )
    else:
        lines.extend(
            [
                "| Company | Best contact | Type | Confidence | Evidence |",
                "|---|---|---|---:|---|",
            ]
        )
        for item in results:
            route = item.get("best_contact_route") or {}
            lines.append(
                "| {company} | {contact} | {route_type} | {confidence} | {evidence} |".format(
                    company=_table_cell(_company_label(item)),
                    contact=_table_cell(route.get("email") or route.get("url") or "not found"),
                    route_type=_table_cell(_route_type_label(route.get("type"))),
                    confidence=int(route.get("confidence") or 0),
                    evidence=_table_cell(route.get("url") or item.get("lead_evidence_url") or "missing"),
                )
            )

    notes = _named_contact_notes(results)
    if notes:
        note_text = "; ".join(note.removeprefix("- ") for note in notes)
        lines.append(f"Named contact search: {note_text}")
    lines.append("Next: Ready for draft only. Sending remains locked.")
    return "\n".join(lines)


def _company_label(result: dict[str, Any]) -> str:
    company = result.get("company") or "unknown"
    signal_count = int(result.get("signal_count") or 1)
    if signal_count > 1:
        return f"{company} ({signal_count} signals)"
    return str(company)


def _route_type_label(route_type: str | None) -> str:
    labels = {
        "named_person": "named person",
        "role_department": "department route",
        "generic_company": "generic fallback",
        "contact_form": "contact form",
        "job_post_apply": "job/apply fallback",
        "no_contact_found": "no usable contact",
    }
    return labels.get(str(route_type or ""), str(route_type or "unknown"))


def _named_contact_notes(results: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for item in results:
        route = item.get("best_contact_route") or {}
        if route.get("type") == "named_person":
            continue
        summary = item.get("search_summary") or {}
        roles = summary.get("named_roles_attempted") or [
            persona["persona"] for persona in (item.get("ideal_buyer_personas") or [])[:3]
        ]
        role_text = " / ".join(str(role) for role in roles[:3]) or "named buyer"
        suffix = (
            f"no named {role_text} found within search budget."
            if summary.get("named_person_search_attempted")
            else "named-person search not completed."
        )
        notes.append(f"- {item.get('company')}: {suffix}")
    return notes


def _table_cell(value: Any) -> str:
    return str(value or "").replace("|", "/").replace("\n", " ").strip()


def assert_no_secret_patterns(result: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(result, sort_keys=True).lower()
    for pattern in SECRET_PATTERNS:
        if pattern in serialized:
            raise ValueError("Secret-like pattern detected in contact resolver output.")
    return result
