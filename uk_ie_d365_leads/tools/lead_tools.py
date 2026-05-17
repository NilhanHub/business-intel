"""Evidence-first UK and Ireland Dynamics 365 lead discovery tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol

import requests


AUDIT_SCHEMA_VERSION = "1.0"
CLASSIFIER_VERSION = "2026-05-17.deterministic-rules-v1"
QUERY_MATRIX_VERSION = "2026-05-17.commercial-non-tender-v1"
SEARCH_PROMPT_VERSION = "2026-05-17.google-grounding-json-v1"
GOOGLE_GROUNDING_DEFAULT_MODEL = "gemini-2.5-flash"
GOOGLE_GROUNDING_PROVIDER_PATH = "direct google-genai Google Search grounding"

COUNTRY_TERMS = {
    "United Kingdom": [
        "united kingdom",
        "uk",
        "england",
        "scotland",
        "wales",
        "northern ireland",
        "london",
        "manchester",
        "birmingham",
        "leeds",
        "glasgow",
        "edinburgh",
        "belfast",
        "cardiff",
    ],
    "Ireland": [
        "ireland",
        "republic of ireland",
        "dublin",
        "cork",
        "galway",
        "limerick",
    ],
}

D365_PRODUCTS = {
    "Dynamics 365 CE / Customer Engagement": [
        "dynamics 365 ce",
        "customer engagement",
        "d365 ce",
        "dynamics crm",
        "crm support",
    ],
    "Dynamics 365 Sales": ["dynamics 365 sales", "d365 sales"],
    "Dynamics 365 Customer Service": [
        "dynamics 365 customer service",
        "d365 customer service",
    ],
    "Dynamics 365 Field Service": ["dynamics 365 field service", "d365 field service"],
    "Dynamics 365 Finance": ["dynamics 365 finance", "d365 finance", "d365 f&o"],
    "Dynamics 365 Supply Chain Management": [
        "dynamics 365 supply chain",
        "supply chain management",
        "d365 scm",
    ],
    "Dynamics 365 Business Central": [
        "dynamics 365 business central",
        "business central",
        "d365 bc",
    ],
    "Dataverse / Power Platform connected to Dynamics 365": [
        "dataverse",
        "power platform",
        "power apps",
    ],
}

SIGNAL_CLASSES = {
    "hiring_pain": {
        "source_type": "job_posting",
        "queries": [
            '"Dynamics 365 Administrator" "United Kingdom" careers',
            '"D365 Support Analyst" "United Kingdom" careers',
            '"Dynamics 365 CE" "Support Analyst" UK',
            '"D365 F&O" "Application Support" UK',
            '"Dynamics 365 Business Central" "Support" Ireland careers',
            '"Dynamics 365 Functional Consultant" "in-house" UK',
            '"CRM Manager" "Dynamics 365" "United Kingdom"',
            '"Business Systems Manager" "Dynamics 365" Ireland',
            '"ERP Manager" "Dynamics 365" UK',
        ],
        "terms": [
            "hiring",
            "job",
            "vacancy",
            "careers",
            "administrator",
            "functional consultant",
            "support analyst",
            "application support",
            "crm support",
            "erp support",
            "in-house",
            "business systems manager",
            "erp manager",
        ],
    },
    "direct_company_career_site_searches": {
        "source_type": "job_posting",
        "queries": [
            'site:greenhouse.io "Dynamics 365" "United Kingdom"',
            'site:lever.co "Dynamics 365" UK',
            'site:workable.com "Dynamics 365" Ireland',
            'site:jobs.ashbyhq.com "Dynamics 365" UK',
            '"Dynamics 365" "UK" "careers" "apply"',
            '"Dynamics 365" "Ireland" "careers" "apply"',
        ],
        "terms": [
            "greenhouse",
            "lever",
            "workable",
            "ashby",
            "careers",
            "apply",
            "job",
            "vacancy",
        ],
    },
    "commercial_non_tender_buying_signals": {
        "source_type": "commercial_signal",
        "queries": [
            '"Dynamics 365" ("support needs" OR "support partner" OR "application support") ("United Kingdom" OR UK OR Ireland)',
            '"Dynamics 365" ("growth" OR "expansion" OR "new sites" OR "acquisition") ("United Kingdom" OR UK OR Ireland)',
            '"Dynamics 365" ("integration" OR "rollout" OR "implementation") ("United Kingdom" OR UK OR Ireland)',
            '"Microsoft business applications" ("ERP" OR "CRM") transformation ("United Kingdom" OR UK OR Ireland)',
            '"Power Platform" Dataverse "Dynamics 365" ("support" OR "transformation") ("United Kingdom" OR UK OR Ireland)',
            '"Dynamics 365" "case study" ("customer" OR "client") ("United Kingdom" OR UK OR Ireland)',
        ],
        "terms": [
            "support needs",
            "support partner",
            "application support",
            "growth",
            "expansion",
            "acquisition",
            "integration",
            "rollout",
            "implementation",
            "microsoft business applications",
            "erp transformation",
            "crm transformation",
            "case study",
            "customer story",
        ],
    },
    "implementation_migration_upgrade_rescue": {
        "source_type": "implementation_signal",
        "queries": [
            '"we are implementing Dynamics 365" UK',
            '"implemented Dynamics 365" "United Kingdom" company',
            '"migrating to Dynamics 365" UK company',
            '"Dynamics 365 rollout" Ireland company',
            '"Business Central migration" UK company',
            '"Dynamics 365 upgrade" "United Kingdom" "case study"',
            '"Dynamics 365 customer story" UK',
            '"Dynamics 365 case study" Ireland',
            '"Dynamics CRM replacement" "United Kingdom" company',
            '"Finance and Operations rollout" "Dynamics 365" UK company',
            '"Dynamics 365" ("failed implementation" OR rescue OR backlog) UK',
        ],
        "terms": [
            "failed",
            "struggling",
            "rescue",
            "backlog",
            "issue",
            "stabilise",
            "stabilize",
            "remediation",
            "upgrade",
            "migration",
            "migrate",
            "rollout",
            "replacement",
            "implementation",
            "integration",
        ],
    },
    "installed_base_discovery": {
        "source_type": "installed_base",
        "queries": [
            '"uses Dynamics 365" UK company',
            '"Dynamics 365 customer" "United Kingdom"',
            '"Dynamics 365 Business Central customer" Ireland',
            '"Dynamics 365 Field Service" UK company',
            '"Dynamics 365 Finance" UK company',
            'site:microsoft.com "Dynamics 365" "United Kingdom" "customer story"',
            '"Dynamics 365" "case study" Ireland customer',
        ],
        "terms": [
            "case study",
            "customer story",
            "transformation",
            "roll-out",
            "roll out",
            "go-live",
            "uses dynamics 365",
            "implemented dynamics 365",
        ],
    },
    "transformation_trigger": {
        "source_type": "transformation_trigger",
        "queries": [
            '"Dynamics 365" "digital transformation" UK company',
            '"Dynamics 365" "new CIO" UK',
            '"Dynamics 365" "ERP transformation" Ireland',
            '"Microsoft business applications" "digital transformation" UK company',
            '"Power Platform" Dataverse "Dynamics 365" "ERP transformation" Ireland',
        ],
        "terms": [
            "new cio",
            "new cto",
            "digital transformation",
            "erp transformation",
            "crm transformation",
            "microsoft business applications",
        ],
    },
}

SIGNAL_TYPES = {
    "hiring_support_or_augmentation": [
        "hiring",
        "job",
        "vacancy",
        "administrator",
        "functional consultant",
        "support analyst",
        "crm support",
        "erp support",
        "contract",
    ],
    "implementation_rescue_or_backlog": [
        "failed",
        "struggling",
        "rescue",
        "backlog",
        "issue",
        "stabilise",
        "stabilize",
        "remediation",
    ],
    "upgrade_or_migration": [
        "upgrade",
        "migration",
        "migrate",
        "rollout",
        "replacement",
        "implementation",
        "integration",
    ],
    "managed_services_or_support": [
        "managed services",
        "support services",
        "application support",
        "support partner",
        "maintenance",
    ],
    "customer_story_or_scale_signal": [
        "case study",
        "customer story",
        "transformation",
        "roll-out",
        "roll out",
        "go-live",
    ],
}

TENDER_DOMAINS = (
    "find-tender.service.gov.uk",
    "contracts.service.gov.uk",
    "etenders.gov.ie",
)
TENDER_TERMS = (
    "tender",
    "rfp",
    "procurement notice",
    "procurement portal",
    "procurement opportunity",
    "public procurement",
    "contract notice",
    "invitation to tender",
    "bid opportunity",
    "public-sector procurement",
    "public sector procurement",
)
VENDOR_TERMS = (
    "we provide",
    "we implement",
    "we support",
    "we offer",
    "we specialise",
    "specialise in providing",
    "design and implement",
    "designed and implemented",
    "helps business organisations",
    "offers assessment",
    "advisory",
    "project governance services",
    "our dynamics 365 services",
    "business central services",
    "support services",
    "migration services",
    "consulting",
    "hire microsoft dynamics",
    "dynamics 365 partner",
    "business central partner",
    "d365 partner",
    "dynamics partner",
    "erp partner",
    "crm partner",
    "migration partners",
    "certified microsoft solutions partner",
    "microsoft partner",
    "solutions partner",
    "implementation partner",
    "as a partner",
    "as an erp partner",
    "partner in the uk",
    "partner in ireland",
    "our customers",
    "our clients",
    "partner network",
    "growth announcement",
    "book a demo",
    "contact us for dynamics",
)
TARGET_CUSTOMER_TERMS = (
    "case study",
    "customer story",
    "client:",
    "customer:",
    "implemented for",
    "using dynamics 365 at",
    "selected by",
    "deployed at",
    "worked with",
    "helped",
    "for its",
    "for their",
)
AGENCY_TERMS = ("recruitment", "recruiter", "staffing agency", "job board")
DEFENSIBLE_HIRING_COMPANY_TERMS = (
    "hiring company",
    "direct employer",
    "company:",
    "employer:",
)
DIRECT_EMPLOYER_TERMS = (
    "careers",
    "our team",
    "join us",
    "we are hiring",
    "direct employer",
    "company:",
    "employer:",
    "business systems manager",
    "crm manager",
    "erp manager",
)
COMMERCIAL_SIGNAL_TERMS = (
    "hiring",
    "careers",
    "support",
    "migration",
    "upgrade",
    "rollout",
    "implementation",
    "integration",
    "backlog",
    "rescue",
    "digital transformation",
    "erp transformation",
    "crm transformation",
)

DEFAULT_QUERIES = [
    query
    for signal_class in SIGNAL_CLASSES.values()
    for query in signal_class["queries"]
]

NO_PROVIDER_MESSAGE = (
    "No local live search provider is configured. Configure one of: "
    "D365_ENABLE_GOOGLE_GROUNDING=true with local ADK Google Search auth, "
    "TAVILY_API_KEY, EXA_API_KEY, SERPER_API_KEY, SERPAPI_API_KEY, "
    "FIRECRAWL_API_KEY, or GOOGLE_CSE_API_KEY plus GOOGLE_CSE_CX."
)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str
    published_date: str | None = None
    signal_class: str | None = None
    source_url_type: str = "clean_public_url"
    source_query: str | None = None
    source_query_group: str | None = None


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    configured: bool
    unavailable_reason: str | None


@dataclass(frozen=True)
class HttpText:
    url: str
    status_code: int | None
    text: str
    error: str | None = None


class SearchProvider(Protocol):
    name: str
    configured: bool
    unavailable_reason: str | None

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Return real public web search results or an empty list."""


class ProviderUnavailable:
    name = "none"
    configured = False

    def __init__(self, reason: str = NO_PROVIDER_MESSAGE) -> None:
        self.unavailable_reason = reason

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        return []


class ADKGoogleGroundingProvider:
    name = "google_grounding"

    def __init__(self) -> None:
        discovery = _adk_google_search_discovery()
        readiness = google_native_readiness()
        self.enabled = readiness["ready"]
        self.configured = bool(discovery["available"] and self.enabled)
        if self.configured:
            self.unavailable_reason = None
        elif not discovery["available"]:
            self.unavailable_reason = discovery["error"]
        else:
            self.unavailable_reason = readiness["reason"]

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        _prepare_google_native_env()
        return _run_google_genai_grounded_search_results(query, limit=limit, source=self.name)


class GoogleCustomSearchProvider:
    name = "custom_search_api"

    def __init__(self) -> None:
        self.api_key = os.environ.get("GOOGLE_CSE_API_KEY")
        self.cx = os.environ.get("GOOGLE_CSE_CX")
        self.configured = bool(self.api_key and self.cx)
        self.unavailable_reason = None if self.configured else (
            "Configure GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX."
        )

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "num": max(1, min(int(limit or 5), 10)),
        }
        payload = _request_json(
            "GET",
            f"https://www.googleapis.com/customsearch/v1?{urllib.parse.urlencode(params)}",
        )
        return [
            SearchResult(
                title=item.get("title") or "",
                url=item.get("link") or "",
                snippet=item.get("snippet") or "",
                source=self.name,
            )
            for item in payload.get("items", [])[:limit]
            if item.get("link")
        ]


class SerpApiSearchProvider:
    name = "serpapi"

    def __init__(self) -> None:
        self.api_key = os.environ.get("SERPAPI_API_KEY")
        self.configured = bool(self.api_key)
        self.unavailable_reason = None if self.configured else "Configure SERPAPI_API_KEY."

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        params = {
            "api_key": self.api_key,
            "engine": "google",
            "q": query,
            "num": max(1, min(int(limit or 5), 10)),
            "gl": "uk",
        }
        payload = _request_json("GET", f"https://serpapi.com/search.json?{urllib.parse.urlencode(params)}")
        return _organic_results(payload.get("organic_results", []), self.name, limit)


class SerperSearchProvider:
    name = "serper"

    def __init__(self) -> None:
        self.api_key = os.environ.get("SERPER_API_KEY")
        self.configured = bool(self.api_key)
        self.unavailable_reason = None if self.configured else "Configure SERPER_API_KEY."

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        payload = _request_json(
            "POST",
            "https://google.serper.dev/search",
            headers={"X-API-KEY": self.api_key or "", "Content-Type": "application/json"},
            json_body={"q": query, "num": max(1, min(int(limit or 5), 10)), "gl": "gb"},
        )
        return _organic_results(payload.get("organic", []), self.name, limit)


class TavilySearchProvider:
    name = "tavily"

    def __init__(self) -> None:
        self.api_key = os.environ.get("TAVILY_API_KEY")
        self.configured = bool(self.api_key)
        self.unavailable_reason = None if self.configured else "Configure TAVILY_API_KEY."

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        payload = _request_json(
            "POST",
            "https://api.tavily.com/search",
            json_body={
                "api_key": self.api_key,
                "query": query,
                "max_results": max(1, min(int(limit or 5), 10)),
                "search_depth": "basic",
            },
        )
        return [
            SearchResult(
                title=item.get("title") or "",
                url=item.get("url") or "",
                snippet=item.get("content") or "",
                source=self.name,
                published_date=item.get("published_date"),
            )
            for item in payload.get("results", [])[:limit]
            if item.get("url")
        ]


class ExaSearchProvider:
    name = "exa"

    def __init__(self) -> None:
        self.api_key = os.environ.get("EXA_API_KEY")
        self.configured = bool(self.api_key)
        self.unavailable_reason = None if self.configured else "Configure EXA_API_KEY."

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        payload = _request_json(
            "POST",
            "https://api.exa.ai/search",
            headers={"x-api-key": self.api_key or "", "Content-Type": "application/json"},
            json_body={"query": query, "numResults": max(1, min(int(limit or 5), 10))},
        )
        return [
            SearchResult(
                title=item.get("title") or "",
                url=item.get("url") or "",
                snippet=item.get("text") or item.get("summary") or "",
                source=self.name,
                published_date=item.get("publishedDate"),
            )
            for item in payload.get("results", [])[:limit]
            if item.get("url")
        ]


class FirecrawlSearchProvider:
    name = "firecrawl"

    def __init__(self) -> None:
        self.api_key = os.environ.get("FIRECRAWL_API_KEY")
        self.configured = bool(self.api_key)
        self.unavailable_reason = None if self.configured else "Configure FIRECRAWL_API_KEY."

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        payload = _request_json(
            "POST",
            "https://api.firecrawl.dev/v1/search",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json_body={"query": query, "limit": max(1, min(int(limit or 5), 10))},
        )
        rows = payload.get("data") or payload.get("results") or []
        return [
            SearchResult(
                title=item.get("title") or "",
                url=item.get("url") or "",
                snippet=item.get("description") or item.get("content") or "",
                source=self.name,
            )
            for item in rows[:limit]
            if item.get("url")
        ]


def discover_d365_search_providers() -> dict[str, Any]:
    """Report local provider readiness without making outbound calls."""
    providers = _provider_candidates()
    statuses = [
        asdict(ProviderStatus(p.name, bool(p.configured), p.unavailable_reason))
        for p in providers
    ]
    chosen = next((status["name"] for status in statuses if status["configured"]), None)
    return {
        "chosen_provider": chosen,
        "providers": statuses,
        "adk": _adk_google_search_discovery(),
        "google_native_readiness": google_native_readiness(),
        "missing_env_vars": missing_provider_env_vars(),
        "notes": [
            "Search providers are real adapters only; missing credentials produce no leads.",
            "Google-native live search uses google-genai grounding directly; d365_search_agent remains search-only for ADK routing.",
        ],
    }


def audit_metadata(
    *,
    search_provider: str | None,
    live_search_run: bool,
    live_request_count: int,
    run_started_at: str | None,
    run_finished_at: str | None,
) -> dict[str, Any]:
    model_name, model_source = effective_google_model()
    adc = _adc_status()
    api_key_present = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if api_key_present:
        provider_client_mode = "API_KEY"
    elif adc.get("available") and adc.get("project_present"):
        provider_client_mode = "ADC"
    else:
        provider_client_mode = "unknown"
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
    return {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "classifier_version": CLASSIFIER_VERSION,
        "query_matrix_version": QUERY_MATRIX_VERSION,
        "prompt_version": SEARCH_PROMPT_VERSION,
        "search_provider": search_provider or "unknown",
        "search_provider_path": (
            GOOGLE_GROUNDING_PROVIDER_PATH
            if (search_provider or "") == "google_grounding"
            else "provider adapter"
        ),
        "effective_model_name": model_name,
        "model_source": model_source,
        "provider_client_mode": provider_client_mode,
        "google_project_present": bool(adc.get("project_present")),
        "google_project_id_masked": mask_identifier(str(adc.get("project") or "")) if adc.get("project") else None,
        "project_id_present": bool(adc.get("project")),
        "google_location": location,
        "live_search_run": bool(live_search_run),
        "live_request_count": int(live_request_count or 0),
        "run_started_at": run_started_at,
        "run_finished_at": run_finished_at,
        "code_version_hint": code_version_hint(),
    }


def effective_google_model() -> tuple[str, str]:
    configured = os.environ.get("D365_GOOGLE_MODEL")
    if configured:
        return configured, "env:D365_GOOGLE_MODEL"
    return GOOGLE_GROUNDING_DEFAULT_MODEL, "default"


def mask_identifier(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return f"{value[:1]}***{value[-1:]}"
    return f"{value[:3]}***{value[-3:]}"


def code_version_hint() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return "not_git_repository"
    except Exception:  # noqa: BLE001 - audit metadata should never block lead extraction.
        return "unknown"


def find_uk_ie_d365_leads(
    query: str | None = None,
    max_results: int = 5,
    provider_name: str | None = None,
    max_live_requests: int = 5,
    include_rejected: bool = True,
) -> dict[str, Any]:
    """Find evidence-backed UK/Ireland Dynamics 365 lead signals."""
    max_results = max(1, min(int(max_results or 5), 10))
    provider = get_search_provider(provider_name)
    started = datetime.now(UTC).isoformat()
    query_plan = build_query_plan(query)
    queries = [item["query"] for item in query_plan]
    if not provider.configured:
        finished = datetime.now(UTC).isoformat()
        return {
            "status": "blocked",
            "provider": provider.name,
            "audit_metadata": audit_metadata(
                search_provider=provider.name,
                live_search_run=False,
                live_request_count=0,
                run_started_at=started,
                run_finished_at=finished,
            ),
            "setup_error": provider.unavailable_reason or NO_PROVIDER_MESSAGE,
            "missing_env_vars": missing_provider_env_vars(),
            "queries_planned": queries,
            "leads": [],
            "lead_count": 0,
            "tier_counts": {"A": 0, "B": 0, "C": 0, "D": 0},
            "tier_a_leads": [],
            "tier_b_provisional_leads": [],
            "tier_c_watchlist_leads": [],
            "tier_d_rejected": [],
            "fetched_at": started,
        }

    raw_results: list[SearchResult] = []
    errors: list[dict[str, str]] = []
    live_requests_made = 0
    for query_item in query_plan[: max(1, min(int(max_live_requests or 5), 25))]:
        search_query = query_item["query"]
        try:
            live_requests_made += 1
            results = provider.search_web(search_query, limit=max_results)
            raw_results.extend(
                SearchResult(
                    title=result.title,
                    url=result.url,
                    snippet=result.snippet,
                    source=result.source,
                    published_date=result.published_date,
                    signal_class=query_item["signal_class"],
                    source_url_type=result.source_url_type,
                    source_query=search_query,
                    source_query_group=query_item["signal_class"],
                )
                for result in results
            )
        except Exception as exc:  # noqa: BLE001 - return actionable provider error.
            errors.append({"query": search_query, "error": _safe_error(exc)})
            break

    extraction = extract_d365_leads(raw_results, max_results=max_results, include_rejected=include_rejected)
    leads = extraction["surfaced_leads"]
    tier_counts = extraction["tier_counts"]
    finished = datetime.now(UTC).isoformat()
    return {
        "status": "ok" if leads else "no_verified_leads_found",
        "provider": provider.name,
        "audit_metadata": audit_metadata(
            search_provider=provider.name,
            live_search_run=live_requests_made > 0,
            live_request_count=live_requests_made,
            run_started_at=started,
            run_finished_at=finished,
        ),
        "queries_run": [item["query"] for item in query_plan[:live_requests_made]],
        "query_groups_run": [item["signal_class"] for item in query_plan[:live_requests_made]],
        "live_requests_made": live_requests_made,
        "cost_risk": (
            "Google-native grounding may incur normal model/search API cost when configured."
            if provider.name == "google_grounding"
            else "No Google-native cost risk from this provider."
        ),
        "provider_errors": errors,
        "leads": leads,
        "lead_count": len(leads),
        "tier_counts": tier_counts,
        "tier_a_leads": extraction["tier_a_leads"],
        "tier_b_provisional_leads": extraction["tier_b_provisional_leads"],
        "tier_c_watchlist_leads": extraction["tier_c_watchlist_leads"],
        "tier_d_rejected": extraction["tier_d_rejected"] if include_rejected else [],
        "rejected_leads": extraction["rejected_leads"] if include_rejected else [],
        "rejected_count": len(extraction["rejected_leads"]),
        "fetched_at": started,
        "run_finished_at": finished,
    }


def refuse_d365_email_sending(request: str = "") -> dict[str, Any]:
    """Refuse any email sending or outreach delivery request."""
    return {
        "sending_enabled": False,
        "request": request,
        "message": (
            "No. uk_ie_d365_leads only discovers evidence-backed lead signals. "
            "It does not send emails or unlock outreach delivery."
        ),
    }


def get_search_provider(provider_name: str | None = None) -> SearchProvider:
    requested = (provider_name or os.environ.get("D365_SEARCH_PROVIDER") or "").strip().lower()
    candidates = _provider_candidates()
    if requested:
        aliases = {p.name.lower(): p for p in candidates}
        if requested in {"google_grounding", "google", "adk_google_search"}:
            requested = "google_grounding"
        provider = aliases.get(requested)
        if provider:
            return provider if provider.configured else ProviderUnavailable(
                provider.unavailable_reason or f"{provider.name} is not configured."
            )
        return ProviderUnavailable(f"Unknown D365_SEARCH_PROVIDER: {provider_name}")
    for provider in candidates:
        if provider.configured:
            return provider
    return ProviderUnavailable()


def build_queries(query: str | None = None) -> list[str]:
    return [item["query"] for item in build_query_plan(query)]


def build_query_plan(query: str | None = None) -> list[dict[str, str]]:
    if query and query.strip():
        return [{"signal_class": "custom", "query": query.strip()}]
    return [
        {"signal_class": signal_class, "query": query_text}
        for signal_class, config in SIGNAL_CLASSES.items()
        for query_text in config["queries"]
    ]


def extract_d365_leads(
    results: list[SearchResult],
    max_results: int = 5,
    include_rejected: bool = False,
) -> dict[str, list[dict[str, Any]]] | list[dict[str, Any]]:
    tier_a: list[dict[str, Any]] = []
    tier_b: list[dict[str, Any]] = []
    tier_c: list[dict[str, Any]] = []
    tier_d: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for result in results:
        decision = evaluate_search_result(result)
        lead = decision["lead"]
        urls = lead.get("evidence_urls") or []
        url = urls[0] if urls else f"no-url:{lead.get('company_name')}:{lead.get('signal_summary')}"
        if url in seen_urls and lead.get("signal_tier") != "D":
            continue
        seen_urls.add(url)
        tier = lead.get("signal_tier")
        if tier == "A":
            tier_a.append(lead)
        elif tier == "B":
            tier_b.append(lead)
        elif tier == "C":
            tier_c.append(lead)
        else:
            tier_d.append(lead)
        if len(tier_a) + len(tier_b) + len(tier_c) >= max_results:
            break
    surfaced = tier_a + tier_b + tier_c
    if include_rejected:
        return {
            "accepted_leads": tier_a,
            "surfaced_leads": surfaced,
            "tier_a_leads": tier_a,
            "tier_b_provisional_leads": tier_b,
            "tier_c_watchlist_leads": tier_c,
            "tier_d_rejected": tier_d,
            "rejected_leads": tier_d,
            "tier_counts": {
                "A": len(tier_a),
                "B": len(tier_b),
                "C": len(tier_c),
                "D": len(tier_d),
            },
        }
    return surfaced


def replay_uk_ie_d365_audit(
    input_path: str,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Add audit traces to a saved run without making live search calls."""
    started = datetime.now(UTC).isoformat()
    source = Path(input_path)
    data = json.loads(source.read_text(encoding="utf-8"))
    replay = dict(data)
    leads = [augment_saved_candidate_audit(item, index=i) for i, item in enumerate(data.get("leads", []), start=1)]
    rejected = [
        augment_saved_candidate_audit(item, index=i)
        for i, item in enumerate(data.get("rejected_leads", []), start=len(leads) + 1)
    ]
    tier_a = [item for item in leads if item.get("signal_tier") == "A"]
    tier_b = [item for item in leads if item.get("signal_tier") == "B"]
    tier_c = [item for item in leads if item.get("signal_tier") == "C"]
    tier_d = [item for item in rejected if item.get("signal_tier") == "D"]
    finished = datetime.now(UTC).isoformat()
    replay.update(
        {
            "audit_metadata": audit_metadata(
                search_provider=data.get("provider") or "google_grounding",
                live_search_run=False,
                live_request_count=0,
                run_started_at=started,
                run_finished_at=finished,
            ),
            "audit_replay": True,
            "audit_replay_source_path": str(source),
            "audit_replay_note": "Offline replay over saved evidence; no provider.search_web call is made.",
            "live_search_run": False,
            "live_request_count": 0,
            "leads": leads,
            "tier_a_leads": tier_a,
            "tier_b_provisional_leads": tier_b,
            "tier_c_watchlist_leads": tier_c,
            "tier_d_rejected": tier_d,
            "rejected_leads": rejected,
            "lead_count": len(leads),
            "rejected_count": len(rejected),
            "tier_counts": {
                "A": len(tier_a),
                "B": len(tier_b),
                "C": len(tier_c),
                "D": len(tier_d),
            },
            "previous_tier_counts": data.get("tier_counts"),
            "expected_previous_tier_counts": {"A": 0, "B": 4, "C": 1, "D": 42},
        }
    )
    replay["replay_counts_match_previous"] = replay["tier_counts"] == data.get("tier_counts")
    replay["replay_counts_match_expected"] = replay["tier_counts"] == replay["expected_previous_tier_counts"]
    if output_path:
        Path(output_path).write_text(json.dumps(replay, indent=2, ensure_ascii=False), encoding="utf-8")
    return replay


def augment_saved_candidate_audit(candidate: dict[str, Any], *, index: int) -> dict[str, Any]:
    item = dict(candidate)
    evidence_urls = item.get("evidence_urls") or []
    evidence_snippets = item.get("evidence_snippets") or []
    raw_url = evidence_urls[0] if evidence_urls else ""
    raw_snippet = evidence_snippets[0] if evidence_snippets else item.get("signal_summary") or ""
    raw_title = item.get("company_name") or item.get("signal_summary") or f"saved_candidate_{index}"
    result = SearchResult(
        title=str(raw_title),
        url=str(raw_url),
        snippet=str(raw_snippet),
        source=str(item.get("source_provider") or "saved_replay"),
        published_date=item.get("evidence_date_if_available"),
        signal_class=item.get("signal_type"),
        source_url_type=item.get("source_url_type") or source_url_type(str(raw_url)),
        source_query=item.get("source_query"),
        source_query_group=item.get("source_query_group"),
    )
    text = f"{result.title}\n{result.snippet}"
    item.setdefault("source_url_type", result.source_url_type)
    item.setdefault("missing_verification_points", missing_verification_points(item, text, raw_url))
    item.setdefault("signal_tier", "D" if item.get("rejection_reason") else "B")
    add_candidate_audit(item, result, text, accepted=item.get("signal_tier") != "D")
    return item


def evaluate_search_result(result: SearchResult) -> dict[str, Any]:
    url = normalize_public_url(result.url)
    text = f"{result.title}\n{result.snippet}"
    base = {
        "company_name": infer_company_name(result.title, url or result.url, text),
        "country": infer_country(text, url or ""),
        "company_website": company_website_from_url(url) if url else None,
        "signal_type": infer_signal_type(text),
        "dynamics_product": infer_dynamics_product(text),
        "signal_summary": summarize_signal(text),
        "evidence_urls": [url] if url else [],
        "evidence_snippets": [clean_snippet(result.snippet or result.title)] if (result.snippet or result.title) else [],
        "evidence_date_if_available": result.published_date,
        "source_type": infer_source_type(text, url or "", result.signal_class),
        "source_url_type": result.source_url_type if url else None,
        "confidence_score": 0,
        "urgency_score": 0,
        "fit_for_1BT": "rejected",
        "recommended_outreach_angle": "",
        "suggested_contact_roles": [],
        "contact_route_status": "not_resolved_by_this_agent",
        "missing_verification_points": [],
        "signal_tier": "D",
        "source_provider": result.source,
        "rejection_reason": None,
    }
    rejection_reason = rejection_reason_for_result(result, text=text, url=url)
    if rejection_reason:
        base["rejection_reason"] = rejection_reason
        base["missing_verification_points"] = missing_verification_points(base, text, url)
        add_candidate_audit(base, result, text, accepted=False)
        return {"accepted": False, "lead": base}

    country = str(base["country"])
    product = str(base["dynamics_product"])
    signal_type = str(base["signal_type"])
    confidence = confidence_score(text, country, product, signal_type)
    urgency = urgency_score(text, signal_type)
    tier = classify_signal_tier(
        text=text,
        source_type=str(base["source_type"]),
        signal_type=signal_type,
        confidence=confidence,
        urgency=urgency,
        source_url_type=str(base["source_url_type"] or ""),
    )
    missing = missing_verification_points(base, text, url)
    base.update(
        {
            "confidence_score": confidence,
            "urgency_score": urgency,
            "fit_for_1BT": fit_for_1bt(confidence, urgency, product, signal_type),
            "recommended_outreach_angle": outreach_angle(product, signal_type),
            "suggested_contact_roles": suggested_contact_roles(product, signal_type),
            "missing_verification_points": missing,
            "signal_tier": tier,
            "rejection_reason": None,
        }
    )
    add_candidate_audit(base, result, text, accepted=True)
    return {"accepted": True, "lead": base}


def add_candidate_audit(
    lead: dict[str, Any],
    result: SearchResult,
    text: str,
    *,
    accepted: bool,
) -> None:
    rule_results = build_rule_results(lead, result, text)
    lead["audit_trace"] = {
        "candidate_id": candidate_id(result.title, result.url, result.snippet),
        "source_query": result.source_query,
        "source_query_group": result.source_query_group or result.signal_class,
        "raw_title": result.title,
        "raw_url": result.url,
        "raw_snippet": result.snippet,
        "normalized_company_name": lead.get("company_name"),
        "normalized_country": lead.get("country"),
        "normalized_dynamics_product": lead.get("dynamics_product"),
        "normalized_signal_type": lead.get("signal_type"),
        "extracted_evidence_urls": lead.get("evidence_urls") or [],
        "extracted_evidence_snippets": lead.get("evidence_snippets") or [],
        "rule_results": rule_results,
    }
    lead["final_decision"] = final_decision(lead, accepted=accepted, rule_results=rule_results)


def candidate_id(title: str, url: str, snippet: str) -> str:
    digest = hashlib.sha256(f"{title}\n{url}\n{snippet}".encode("utf-8", errors="ignore")).hexdigest()
    return f"cand_{digest[:16]}"


def build_rule_results(lead: dict[str, Any], result: SearchResult, text: str) -> list[dict[str, Any]]:
    url = normalize_public_url(result.url)
    combined = f"{result.title}\n{result.url}\n{result.snippet}"
    source_type = str(lead.get("source_type") or "")
    signal_type = str(lead.get("signal_type") or "")
    source_url = str(lead.get("source_url_type") or source_url_type(url))
    has_evidence = bool(url)
    has_d365 = has_dynamics_evidence(text)
    country = bool(lead.get("country"))
    tender_terms = matched_terms(combined, [*TENDER_DOMAINS, *TENDER_TERMS])
    generic_it = generic_it_support_only(text)
    vendor_terms = matched_terms(combined, VENDOR_TERMS)
    target_terms = matched_terms(combined, TARGET_CUSTOMER_TERMS)
    agency_terms = matched_terms(combined, AGENCY_TERMS)
    hiring_company_terms = matched_terms(combined, DEFENSIBLE_HIRING_COMPANY_TERMS)
    direct_terms = matched_terms(combined, DIRECT_EMPLOYER_TERMS)
    commercial_terms = matched_terms(combined, COMMERCIAL_SIGNAL_TERMS)
    installed_base = source_type == "installed_base"
    grounding_redirect = source_url == "grounding_redirect"
    clean_url = source_url == "clean_public_url"
    return [
        rule_result(
            "has_evidence_url",
            "Has evidence URL",
            has_evidence,
            "blocking",
            [url] if url else [],
            result,
            "url",
            "Candidate has at least one normalized public evidence URL." if has_evidence else "Candidate has no usable public evidence URL.",
        ),
        rule_result(
            "has_explicit_d365_or_business_app_evidence",
            "Has explicit Dynamics 365 or Microsoft business app evidence",
            has_d365,
            "blocking",
            matched_d365_terms(text),
            result,
            "combined_text",
            "Title/snippet contains explicit Dynamics 365 or connected Microsoft business app evidence." if has_d365 else "Title/snippet lacks explicit Dynamics 365 or connected Microsoft business app evidence.",
        ),
        rule_result(
            "uk_or_ireland_evidenced",
            "UK or Ireland evidenced",
            country,
            "blocking",
            matched_country_terms(combined),
            result,
            "combined_text",
            "Candidate text or URL evidences UK/Ireland scope." if country else "Candidate text and URL do not evidence UK/Ireland scope.",
        ),
        rule_result(
            "tender_or_procurement_out_of_scope",
            "Tender/procurement out of scope",
            not bool(tender_terms),
            "blocking",
            tender_terms,
            result,
            "combined_text",
            "No tender/procurement exclusion term was found." if not tender_terms else "Tender/procurement exclusion term was found.",
        ),
        rule_result(
            "generic_it_support_only",
            "Generic IT support only",
            not generic_it,
            "blocking",
            ["it support"] if generic_it else [],
            result,
            "combined_text",
            "Candidate is not generic IT support without Dynamics evidence." if not generic_it else "Candidate appears to be generic IT support without Dynamics evidence.",
        ),
        rule_result(
            "vendor_or_service_provider_without_target_customer",
            "Vendor/service-provider without target customer",
            not (vendor_terms and not target_terms),
            "blocking",
            vendor_terms if vendor_terms and not target_terms else target_terms,
            result,
            "combined_text",
            "Candidate is not a vendor page without a defensible target customer." if not (vendor_terms and not target_terms) else "Vendor/service-provider terms were found and no target-customer term was found.",
        ),
        rule_result(
            "recruitment_agency_without_defensible_hiring_company",
            "Recruitment agency without defensible hiring company",
            not (agency_terms and not hiring_company_terms),
            "blocking",
            agency_terms if agency_terms and not hiring_company_terms else hiring_company_terms,
            result,
            "combined_text",
            "Candidate is not an unsupported recruitment-agency/job-board item." if not (agency_terms and not hiring_company_terms) else "Recruitment/job-board terms were found and no defensible hiring-company term was found.",
        ),
        rule_result(
            "installed_base_only",
            "Installed base only",
            not installed_base,
            "scoring",
            ["installed_base"] if installed_base else [],
            result,
            "combined_text",
            "Candidate is not classified as installed-base only." if not installed_base else "Candidate is classified as installed-base/watchlist evidence.",
        ),
        rule_result(
            "commercial_signal_present",
            "Commercial signal present",
            bool(commercial_terms) or signal_type in SIGNAL_CLASSES,
            "scoring",
            commercial_terms,
            result,
            "combined_text",
            "Candidate has a commercial/change/hiring signal." if (commercial_terms or signal_type in SIGNAL_CLASSES) else "No commercial/change/hiring signal was found.",
        ),
        rule_result(
            "direct_employer_hiring_signal",
            "Direct employer hiring signal",
            direct_employer_signal(text),
            "scoring",
            direct_terms,
            result,
            "combined_text",
            "Direct employer hiring terms were found." if direct_terms else "No direct employer hiring terms were found.",
        ),
        rule_result(
            "target_customer_extractable_from_case_study",
            "Target customer extractable from case study",
            bool(target_terms or extract_named_target_company(text)),
            "scoring",
            target_terms or ([extract_named_target_company(text)] if extract_named_target_company(text) else []),
            result,
            "combined_text",
            "Target customer evidence is extractable." if (target_terms or extract_named_target_company(text)) else "No target customer evidence was extractable.",
        ),
        rule_result(
            "grounding_redirect_url_detected",
            "Grounding redirect URL detected",
            grounding_redirect,
            "informational",
            ["vertexaisearch.cloud.google.com/grounding-api-redirect"] if grounding_redirect else [],
            result,
            "url",
            "Evidence URL is a Google grounding redirect." if grounding_redirect else "Evidence URL is not a Google grounding redirect.",
        ),
        rule_result(
            "clean_public_url_detected",
            "Clean public URL detected",
            clean_url,
            "informational",
            [url] if clean_url and url else [],
            result,
            "url",
            "Evidence URL is a clean public URL." if clean_url else "Evidence URL is not a clean public URL.",
        ),
    ]


def rule_result(
    rule_id: str,
    rule_name: str,
    passed: bool,
    severity: str,
    terms: list[str],
    result: SearchResult,
    evidence_field_used: str,
    explanation: str,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "rule_name": rule_name,
        "passed": bool(passed),
        "severity": severity,
        "matched_terms": terms,
        "matched_text_excerpt": matched_excerpt(result, terms),
        "evidence_field_used": evidence_field_used,
        "explanation": explanation,
    }


def matched_terms(text: str, terms: Any) -> list[str]:
    lower = str(text or "").lower()
    return [term for term in terms if term and str(term).lower() in lower]


def matched_excerpt(result: SearchResult, terms: list[str]) -> str:
    if not terms:
        return ""
    fields = [result.title, result.url, result.snippet]
    combined = "\n".join(str(field or "") for field in fields)
    lower = combined.lower()
    for term in terms:
        idx = lower.find(str(term).lower())
        if idx >= 0:
            start = max(0, idx - 70)
            end = min(len(combined), idx + len(str(term)) + 110)
            return clean_snippet(combined[start:end])
    return ""


def matched_d365_terms(text: str) -> list[str]:
    terms = ["dynamics 365", "d365", "dynamics crm", "microsoft business applications", "microsoft business apps", "microsoft business app", "business central", "dataverse", "power platform", "power apps"]
    return matched_terms(text, terms)


def matched_country_terms(text: str) -> list[str]:
    terms: list[str] = []
    for country_terms in COUNTRY_TERMS.values():
        terms.extend(country_terms)
    return matched_terms(text, terms)


def final_decision(
    lead: dict[str, Any],
    *,
    accepted: bool,
    rule_results: list[dict[str, Any]],
) -> dict[str, Any]:
    tier = str(lead.get("signal_tier") or "D")
    rejection_reason = lead.get("rejection_reason") if tier == "D" else None
    return {
        "final_tier": tier,
        "accepted": bool(accepted and tier != "D"),
        "rejection_reason": rejection_reason,
        "promotion_reason": promotion_reason(lead, rule_results) if tier != "D" else None,
        "confidence_score": lead.get("confidence_score", 0),
        "urgency_score": lead.get("urgency_score", 0),
        "fit_for_1BT": lead.get("fit_for_1BT"),
        "missing_verification_points": lead.get("missing_verification_points") or [],
        "human_review_recommended": human_review_recommended(lead, rule_results),
        "human_review_reason": human_review_reason(lead, rule_results),
        "decision_rule_summary": decision_rule_summary(lead, rule_results),
    }


def promotion_reason(lead: dict[str, Any], rule_results: list[dict[str, Any]]) -> str:
    tier = str(lead.get("signal_tier") or "")
    if tier == "A":
        return "Deterministic rules found evidence URL, Dynamics evidence, UK/Ireland evidence, and a strong commercial signal."
    if tier == "B":
        return "Deterministic rules found a useful commercial signal but one or more verification points remain."
    if tier == "C":
        return "Deterministic rules found installed-base or weak-urgency evidence, so the candidate remains visible as watchlist."
    return ""


def human_review_recommended(lead: dict[str, Any], rule_results: list[dict[str, Any]]) -> bool:
    if lead.get("missing_verification_points"):
        return True
    if lead.get("signal_tier") in {"B", "C"}:
        return True
    risk_reasons = {
        "vendor_or_service_provider_page_without_defensible_target_customer",
        "recruitment_agency_post_without_defensible_hiring_company",
        "uk_ireland_not_evidenced",
    }
    return lead.get("rejection_reason") in risk_reasons or any(
        rule["rule_id"] == "grounding_redirect_url_detected" and rule["passed"]
        for rule in rule_results
    )


def human_review_reason(lead: dict[str, Any], rule_results: list[dict[str, Any]]) -> str:
    if lead.get("missing_verification_points"):
        return "Candidate has unresolved verification points."
    if lead.get("signal_tier") == "C":
        return "Installed-base or weak-urgency candidate may become useful if a current change/support trigger is found."
    reason = lead.get("rejection_reason")
    if reason == "vendor_or_service_provider_page_without_defensible_target_customer":
        return "Vendor/case-study pages can hide a target customer if extraction is weak."
    if reason == "recruitment_agency_post_without_defensible_hiring_company":
        return "Recruitment/job-board snippets can hide the actual employer."
    if reason == "uk_ireland_not_evidenced":
        return "UK/Ireland evidence may exist on the source page but be absent from the snippet."
    if any(rule["rule_id"] == "grounding_redirect_url_detected" and rule["passed"] for rule in rule_results):
        return "Clean source URL is not resolved from the grounding redirect."
    return "No special human-review risk was identified."


def decision_rule_summary(lead: dict[str, Any], rule_results: list[dict[str, Any]]) -> list[str]:
    if lead.get("signal_tier") == "D":
        reason = lead.get("rejection_reason") or "unknown"
        failed = [rule["rule_id"] for rule in rule_results if rule["severity"] == "blocking" and not rule["passed"]]
        return [f"Tier D because {reason}.", f"Failed blocking rules: {', '.join(failed) or 'none recorded'}."]
    tier = lead.get("signal_tier")
    source_type = lead.get("source_type")
    if tier == "A":
        return [f"Tier A from source_type={source_type}, confidence={lead.get('confidence_score')}, urgency={lead.get('urgency_score')}."]
    if tier == "B":
        return [f"Tier B from source_type={source_type}; missing verification: {', '.join(lead.get('missing_verification_points') or []) or 'none'}."]
    return [f"Tier C from source_type={source_type}; watchlist/installed-base or weak urgency."]


def rejection_reason_for_result(result: SearchResult, *, text: str, url: str | None) -> str | None:
    if not url:
        return "missing_evidence_url"
    if tender_or_procurement_source(text, url):
        return "tender_or_procurement_out_of_scope"
    if not has_dynamics_evidence(text):
        return "missing_explicit_dynamics_365_or_business_app_evidence"
    if generic_it_support_only(text):
        return "generic_it_support_without_dynamics_365_evidence"
    if vendor_page_without_target_customer(text, url):
        return "vendor_or_service_provider_page_without_defensible_target_customer"
    if recruitment_agency_without_hiring_company(text, url):
        return "recruitment_agency_post_without_defensible_hiring_company"
    country = infer_country(text, url)
    if not country:
        return "uk_ireland_not_evidenced"
    return None


def classify_signal_tier(
    *,
    text: str,
    source_type: str,
    signal_type: str,
    confidence: int,
    urgency: int,
    source_url_type: str,
) -> str:
    lower = text.lower()
    if source_type == "installed_base":
        if any(term in lower for term in ("hiring", "support", "migration", "upgrade", "rollout", "implementation")):
            return "B" if source_url_type == "grounding_redirect" else "A"
        return "C"
    if source_type == "job_posting":
        if direct_employer_signal(text) and confidence >= 65:
            return "A"
        return "B"
    if any(term in lower for term in ("migration", "upgrade", "rollout", "implementation", "integration", "support", "backlog", "rescue")):
        if confidence >= 70 and urgency >= 55 and source_url_type != "grounding_redirect":
            return "A"
        return "B"
    if signal_type == "transformation_trigger":
        return "B"
    return "C"


def missing_verification_points(base: dict[str, Any], text: str, url: str | None) -> list[str]:
    missing: list[str] = []
    if not url:
        missing.append("find_public_evidence_url")
    if not base.get("country"):
        missing.append("verify_uk_or_ireland_scope")
    if not has_dynamics_evidence(text):
        missing.append("verify_explicit_dynamics_365_or_microsoft_business_app_evidence")
    if base.get("source_url_type") == "grounding_redirect":
        missing.append("resolve_clean_public_source_url_if_available")
    if base.get("source_type") == "job_posting" and not direct_employer_signal(text):
        missing.append("verify_actual_direct_employer")
    if base.get("source_type") == "installed_base":
        missing.append("verify_current_support_change_or_augmentation_trigger")
    return missing


def direct_employer_signal(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in DIRECT_EMPLOYER_TERMS) and not recruitment_agency_without_hiring_company(text, "")


def has_dynamics_evidence(text: str) -> bool:
    lower = text.lower()
    d365 = "dynamics 365" in lower or "d365" in lower or "dynamics crm" in lower
    microsoft_business_apps = (
        "microsoft business applications" in lower
        or "microsoft business apps" in lower
        or "microsoft business app" in lower
    )
    business_apps = any(
        token in lower
        for token in ("business central", "dataverse", "power platform", "power apps")
    )
    return d365 or microsoft_business_apps or (
        business_apps and ("dynamics" in lower or "crm" in lower or "erp" in lower or "business application" in lower)
    )


def generic_it_support_only(text: str) -> bool:
    lower = text.lower()
    return "it support" in lower and not has_dynamics_evidence(lower)


def tender_or_procurement_source(text: str, url: str) -> bool:
    lower = f"{text} {url}".lower()
    return any(domain in lower for domain in TENDER_DOMAINS) or any(term in lower for term in TENDER_TERMS)


def vendor_page_without_target_customer(text: str, url: str) -> bool:
    lower = f"{text} {url}".lower()
    return any(term in lower for term in VENDOR_TERMS) and not any(term in lower for term in TARGET_CUSTOMER_TERMS)


def recruitment_agency_without_hiring_company(text: str, url: str) -> bool:
    lower = f"{text} {url}".lower()
    return any(term in lower for term in AGENCY_TERMS) and not any(term in lower for term in DEFENSIBLE_HIRING_COMPANY_TERMS)


def infer_country(text: str, url: str = "") -> str | None:
    lower = f"{text} {url}".lower()
    if "sri lanka" in lower and not any(t in lower for t in COUNTRY_TERMS["United Kingdom"] + COUNTRY_TERMS["Ireland"]):
        return None
    uk_hit = any(term in lower for term in COUNTRY_TERMS["United Kingdom"]) or url.endswith(".uk")
    ie_hit = any(term in lower for term in COUNTRY_TERMS["Ireland"]) or url.endswith(".ie")
    if uk_hit and "northern ireland" in lower:
        return "United Kingdom"
    if uk_hit:
        return "United Kingdom"
    if ie_hit:
        return "Ireland"
    return None


def infer_dynamics_product(text: str) -> str:
    lower = text.lower()
    for product, terms in D365_PRODUCTS.items():
        if any(term in lower for term in terms):
            return product
    return "Microsoft Dynamics 365"


def infer_signal_type(text: str) -> str:
    lower = text.lower()
    for signal_class, config in SIGNAL_CLASSES.items():
        if any(term in lower for term in config["terms"]):
            return signal_class
    for signal_type, terms in SIGNAL_TYPES.items():
        if any(term in lower for term in terms):
            return signal_type
    return "d365_public_evidence"


def infer_source_type(text: str, url: str, signal_class: str | None) -> str:
    if signal_class and signal_class in SIGNAL_CLASSES:
        return str(SIGNAL_CLASSES[signal_class]["source_type"])
    signal_type = infer_signal_type(text)
    if signal_type in SIGNAL_CLASSES:
        return str(SIGNAL_CLASSES[signal_type]["source_type"])
    lower = f"{text} {url}".lower()
    if any(term in lower for term in ("job", "vacancy", "hiring")):
        return "job_posting"
    if any(term in lower for term in ("case study", "customer story")):
        return "installed_base"
    return "public_web"


def confidence_score(text: str, country: str, product: str, signal_type: str) -> int:
    score = 35
    if country:
        score += 15
    if product != "Microsoft Dynamics 365":
        score += 15
    if signal_type != "d365_public_evidence":
        score += 20
    if re.search(r"\b(company|council|nhs|university|limited|ltd|plc)\b", text, re.I):
        score += 5
    if any(term in text.lower() for term in ("failed", "urgent", "backlog", "support", "rescue")):
        score += 10
    return min(score, 95)


def urgency_score(text: str, signal_type: str) -> int:
    lower = text.lower()
    score = 30
    if signal_type in {"hiring_support_or_augmentation", "hiring_pain"}:
        score += 25
    if signal_type in {"implementation_rescue_or_backlog", "managed_services_or_support"}:
        score += 35
    if any(term in lower for term in ("urgent", "immediate", "asap", "backlog", "failed", "rescue")):
        score += 20
    return min(score, 95)


def fit_for_1bt(confidence: int, urgency: int, product: str, signal_type: str) -> str:
    average = (confidence + urgency) // 2
    if average >= 75:
        return "high"
    if average >= 55:
        return "medium"
    return "watch"


def outreach_angle(product: str, signal_type: str) -> str:
    if signal_type == "implementation_rescue_or_backlog":
        return f"Offer a low-risk {product} rescue/stabilisation assessment with evidence-led next steps."
    if signal_type == "upgrade_or_migration":
        return f"Position 1BT around {product} migration, integration, and rollout support capacity."
    if signal_type == "hiring_support_or_augmentation":
        return f"Offer specialist {product} delivery/support augmentation to reduce hiring pressure."
    return f"Open with the public {product} signal and ask whether specialist support capacity would help."


def suggested_contact_roles(product: str, signal_type: str) -> list[str]:
    roles = ["Head of IT", "IT Director", "Business Systems Manager"]
    if "Customer" in product or "Sales" in product or "CE" in product:
        roles.extend(["CRM Manager", "Customer Operations Director"])
    if "Finance" in product or "Business Central" in product:
        roles.extend(["Finance Systems Manager", "ERP Manager"])
    return roles


def missing_provider_env_vars() -> dict[str, list[str]]:
    return {
        "google_grounding": [
            "D365_ENABLE_GOOGLE_GROUNDING=true",
            "GOOGLE_GENAI_USE_VERTEXAI or ADK local Google Search auth",
        ],
        "tavily": ["TAVILY_API_KEY"],
        "exa": ["EXA_API_KEY"],
        "serper": ["SERPER_API_KEY"],
        "serpapi": ["SERPAPI_API_KEY"],
        "firecrawl": ["FIRECRAWL_API_KEY"],
        "custom_search_api": ["GOOGLE_CSE_API_KEY", "GOOGLE_CSE_CX"],
    }


def google_native_readiness() -> dict[str, Any]:
    env = {
        "GOOGLE_GENAI_USE_VERTEXAI": _presence("GOOGLE_GENAI_USE_VERTEXAI"),
        "GOOGLE_CLOUD_PROJECT": _presence("GOOGLE_CLOUD_PROJECT"),
        "GOOGLE_CLOUD_LOCATION": _presence("GOOGLE_CLOUD_LOCATION"),
        "GEMINI_API_KEY": _presence("GEMINI_API_KEY"),
        "GOOGLE_API_KEY": _presence("GOOGLE_API_KEY"),
        "D365_ENABLE_GOOGLE_GROUNDING": _presence("D365_ENABLE_GOOGLE_GROUNDING"),
    }
    adc = _adc_status()
    api_key_ready = env["GEMINI_API_KEY"] == "present" or env["GOOGLE_API_KEY"] == "present"
    vertex_ready = bool(adc["available"] and adc["project_present"])
    ready = api_key_ready or vertex_ready
    if ready:
        reason = "Google-native credentials appear available locally."
    else:
        reason = "No Gemini API key and no ADC project were available."
    return {
        "ready": ready,
        "reason": reason,
        "env": env,
        "adc": adc,
        "cost_risk": (
            "Live grounded search uses remote Google model/search services and may incur project/API cost."
        ),
    }


def _prepare_google_native_env() -> None:
    readiness = google_native_readiness()
    adc = readiness["adc"]
    if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("GEMINI_API_KEY") and adc.get("available"):
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
        if adc.get("project"):
            os.environ.setdefault("GOOGLE_CLOUD_PROJECT", str(adc["project"]))
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")


def _presence(name: str) -> str:
    return "present" if os.environ.get(name) else "missing"


def _adc_status() -> dict[str, Any]:
    try:
        import google.auth

        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return {
            "available": True,
            "project_present": bool(project),
            "project": project or None,
            "credential_type": type(credentials).__name__,
        }
    except Exception as exc:  # noqa: BLE001 - readiness only.
        return {
            "available": False,
            "project_present": False,
            "project": None,
            "error_type": type(exc).__name__,
            "error": str(exc)[:200],
        }


def parse_search_results(text: str, *, source: str, limit: int = 5) -> list[SearchResult]:
    raw = _extract_json(text)
    if raw is None:
        return []
    rows = raw if isinstance(raw, list) else [raw]
    results = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("link") or item.get("href")
        normalized = normalize_public_url(url)
        if not normalized:
            continue
        results.append(
            SearchResult(
                title=str(item.get("title") or item.get("name") or ""),
                url=normalized,
                snippet=str(item.get("snippet") or item.get("description") or item.get("content") or ""),
                source=source,
                published_date=item.get("published_date") or item.get("date"),
                source_url_type=source_url_type(normalized),
            )
        )
        if len(results) >= limit:
            break
    return results


def normalize_public_url(url: Any) -> str | None:
    raw = str(url or "").strip()
    if not raw or raw.startswith(("mailto:", "javascript:", "#")):
        return None
    if not re.match(r"^https?://", raw, flags=re.I):
        raw = f"https://{raw}"
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or "." not in parsed.netloc:
        return None
    if parsed.hostname and parsed.hostname.lower() in {"localhost", "127.0.0.1"}:
        return None
    return urllib.parse.urlunparse(parsed)


def source_url_type(url: str | None) -> str:
    lower = str(url or "").lower()
    if not lower:
        return "unknown"
    if "vertexaisearch.cloud.google.com/grounding-api-redirect" in lower:
        return "grounding_redirect"
    return "clean_public_url"


def company_website_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else url


def infer_company_name(title: str, url: str, text: str = "") -> str:
    clean = clean_snippet(re.split(r"\s[-|]\s", title or "")[0])
    generic_titles = (
        "news",
        "22 dynamics",
        "dynamics 365 business central jobs",
        "microsoft dynamics 365",
        "microsoft dynamics erp",
        "dynamics 365 case studies",
    )
    if clean and len(clean) >= 2 and clean.lower() not in {"uk", "ireland"} and not clean.lower().startswith(("uk ", "ireland ")) and not any(clean.lower().startswith(term) for term in generic_titles):
        return clean[:120]
    extracted = extract_named_target_company(text)
    if extracted:
        return extracted[:120]
    host = urllib.parse.urlparse(url).netloc.removeprefix("www.")
    return host.split(".")[0].replace("-", " ").title()


def extract_named_target_company(text: str) -> str | None:
    patterns = (
        r"\b([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,4}\s+(?:Limited|Ltd|plc|PLC|Group|NI))\b",
        r"\b([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,4})\s+(?:has completed|implemented|uses|were facing|is implementing|migrating to|upgraded to|selected|onboarded)",
        r"\b(?:customer|client):\s*([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,4})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = clean_snippet(match.group(1).strip(" -:|"))
            candidate = re.sub(r"^(UK|Ireland)\s+", "", candidate).strip()
            words = candidate.split()
            if len(words) >= 2 and len(words) % 2 == 0 and words[: len(words) // 2] == words[len(words) // 2 :]:
                candidate = " ".join(words[: len(words) // 2])
            if candidate.lower() not in {"microsoft dynamics", "dynamics"}:
                return candidate
    return None


def summarize_signal(text: str) -> str:
    return clean_snippet(text)[:280]


def clean_snippet(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(str(text or ""))).strip()


def _provider_candidates() -> list[SearchProvider]:
    return [
        ADKGoogleGroundingProvider(),
        TavilySearchProvider(),
        ExaSearchProvider(),
        SerperSearchProvider(),
        SerpApiSearchProvider(),
        FirecrawlSearchProvider(),
        GoogleCustomSearchProvider(),
    ]


def _adk_google_search_discovery() -> dict[str, Any]:
    try:
        from google.adk.tools import google_search  # noqa: F401
        from google.adk.tools.agent_tool import AgentTool  # noqa: F401
    except Exception as exc:
        return {
            "available": False,
            "provider": "none",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    return {
        "available": True,
        "provider": "google_grounding",
        "error_type": None,
        "error": None,
    }


async def _run_adk_search_agent(prompt: str) -> str:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from uk_ie_d365_leads.agents.search_agent import d365_search_agent

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="uk_ie_d365_leads_search",
        user_id="uk_ie_d365_leads",
        session_id=f"search-{abs(hash(prompt))}",
    )
    runner = Runner(
        app_name="uk_ie_d365_leads_search",
        agent=d365_search_agent,
        session_service=session_service,
    )
    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    texts: list[str] = []
    async for event in runner.run_async(
        user_id="uk_ie_d365_leads",
        session_id=session.id,
        new_message=message,
    ):
        content = getattr(event, "content", None)
        if not content or not content.parts:
            continue
        for part in content.parts:
            text = getattr(part, "text", None)
            if text:
                texts.append(text)
    return "\n".join(texts)


def _run_google_genai_grounded_search_results(query: str, limit: int = 5, source: str = "google_grounding") -> list[SearchResult]:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        client = genai.Client(api_key=api_key)
    else:
        readiness = google_native_readiness()
        project = readiness["adc"].get("project") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
        client = genai.Client(vertexai=True, project=project, location=location)
    prompt = (
        "Search the public web for the query below. Return JSON only: "
        "[{\"title\":\"...\",\"url\":\"https://...\",\"snippet\":\"...\"}]. "
        f"Return at most {max(1, min(int(limit or 5), 10))} results. "
        "Only include public web evidence for UK/Ireland Microsoft Dynamics 365 lead intelligence. "
        "Do not invent companies, URLs, or snippets.\n\n"
        f"Query: {query}"
    )
    response = client.models.generate_content(
        model=effective_google_model()[0],
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(googleSearch=types.GoogleSearch())],
            temperature=0,
            maxOutputTokens=2048,
        ),
    )
    text_results = parse_search_results(getattr(response, "text", "") or "", source=source, limit=limit)
    metadata_results = _grounding_metadata_results(response, source=source, limit=limit)
    merged: list[SearchResult] = []
    seen: set[str] = set()
    for result in text_results + metadata_results:
        normalized = normalize_public_url(result.url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(
            SearchResult(
                title=result.title,
                url=normalized,
                snippet=result.snippet,
                source=result.source,
                published_date=result.published_date,
                signal_class=result.signal_class,
                source_url_type=source_url_type(normalized),
            )
        )
        if len(merged) >= limit:
            break
    return merged


def _grounding_metadata_results(response: Any, *, source: str, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        metadata = (
            getattr(candidate, "grounding_metadata", None)
            or getattr(candidate, "groundingMetadata", None)
        )
        chunks = (
            getattr(metadata, "grounding_chunks", None)
            or getattr(metadata, "groundingChunks", None)
            or []
        )
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if web is None and isinstance(chunk, dict):
                web = chunk.get("web")
            title = _attr_or_key(web, "title") or ""
            uri = _attr_or_key(web, "uri") or _attr_or_key(web, "url") or ""
            normalized = normalize_public_url(uri)
            if not normalized:
                continue
            results.append(
                SearchResult(
                    title=str(title),
                    url=normalized,
                    snippet=str(title),
                    source=source,
                    source_url_type=source_url_type(normalized),
                )
            )
            if len(results) >= limit:
                return results
    return results


def _attr_or_key(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _run_coro_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("ADK search provider cannot run inside an active event loop.")


def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    response = requests.request(
        method,
        url,
        headers=headers,
        json=json_body,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _organic_results(rows: list[dict[str, Any]], source: str, limit: int) -> list[SearchResult]:
    return [
        SearchResult(
            title=item.get("title") or "",
            url=item.get("link") or item.get("url") or "",
            snippet=item.get("snippet") or item.get("description") or "",
            source=source,
            published_date=item.get("date"),
        )
        for item in rows[:limit]
        if item.get("link") or item.get("url")
    ]


def _extract_json(text: str) -> Any:
    clean = (text or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?", "", clean, flags=re.I).strip()
        clean = re.sub(r"```$", "", clean).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", clean)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _safe_error(exc: BaseException) -> str:
    text = str(exc)
    text = re.sub(r"(api[_-]?key=)[^&\s]+", r"\1REDACTED", text, flags=re.I)
    text = re.sub(r"(Authorization:\s*Bearer\s+)[A-Za-z0-9._-]+", r"\1REDACTED", text, flags=re.I)
    return text[:300]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        clean = data.strip()
        if clean:
            self.parts.append(clean)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html or "")
    return clean_snippet(" ".join(parser.parts))
