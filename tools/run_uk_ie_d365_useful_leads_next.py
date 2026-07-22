"""Run a fresh UK/IE D365 search and curate the next 12 useful leads.

This utility is evidence-only: it does not deploy, send email, browse private
sessions, or change deterministic classifier rules.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uk_ie_d365_leads.agent import root_agent
from uk_ie_d365_leads.tools.classification_review_tools import (
    call_vertex_reviewer,
    make_vertex_reviewer_client,
    parse_review_json,
    prepare_candidate,
)
from uk_ie_d365_leads.tools.lead_tools import (
    discover_d365_search_providers,
    effective_google_model,
    find_uk_ie_d365_leads,
    google_native_readiness,
)

EVIDENCE_DIR = PROJECT_ROOT / "Evidence"
DEFAULT_BASENAME = "UK_IE_D365_USEFUL_LEADS_NEXT"
FRESH_SEARCH_NAME = "UK_IE_D365_FRESH_SEARCH"
DEFAULT_PROJECT = "business-intel-123"
DEFAULT_LOCATION = "global"

SEARCH_QUERIES = [
    {
        "signal_class": "hiring_pain",
        "query": '"Dynamics 365 Administrator" "United Kingdom" careers',
    },
    {
        "signal_class": "hiring_pain",
        "query": '"D365 Support Analyst" "United Kingdom" careers',
    },
    {
        "signal_class": "hiring_pain",
        "query": '"D365 F&O" "Application Support" UK',
    },
    {
        "signal_class": "hiring_pain",
        "query": '"Dynamics 365 CE" "Support Analyst" UK',
    },
    {
        "signal_class": "hiring_pain",
        "query": '"Dynamics 365 Business Central" "Support" Ireland careers',
    },
    {
        "signal_class": "direct_employer_hiring",
        "query": '"CRM Manager" "Dynamics 365" "United Kingdom"',
    },
    {
        "signal_class": "direct_employer_hiring",
        "query": '"ERP Manager" "Dynamics 365" Ireland',
    },
    {
        "signal_class": "direct_company_career_site_searches",
        "query": 'site:greenhouse.io "Dynamics 365" "United Kingdom"',
    },
    {
        "signal_class": "direct_company_career_site_searches",
        "query": 'site:lever.co "Dynamics 365" UK',
    },
    {
        "signal_class": "direct_company_career_site_searches",
        "query": '"Dynamics 365" "Ireland" "careers" "apply"',
    },
    {
        "signal_class": "commercial_non_tender_buying_signals",
        "query": '"Dynamics 365" ("support needs" OR "support partner" OR "application support") ("United Kingdom" OR UK OR Ireland)',
    },
    {
        "signal_class": "commercial_non_tender_buying_signals",
        "query": '"Dynamics 365" ("integration" OR "rollout" OR "implementation") ("United Kingdom" OR UK OR Ireland)',
    },
    {
        "signal_class": "commercial_non_tender_buying_signals",
        "query": '"Power Platform" Dataverse "Dynamics 365" ("support" OR "transformation") ("United Kingdom" OR UK OR Ireland)',
    },
    {
        "signal_class": "commercial_non_tender_buying_signals",
        "query": '"Dynamics 365" "case study" ("customer" OR "client") ("United Kingdom" OR UK OR Ireland)',
    },
    {
        "signal_class": "implementation_migration_upgrade_rescue",
        "query": '"Dynamics 365" ("failed implementation" OR rescue OR backlog) UK',
    },
    {
        "signal_class": "implementation_migration_upgrade_rescue",
        "query": '"Dynamics 365 upgrade" "United Kingdom" "case study"',
    },
    {
        "signal_class": "implementation_migration_upgrade_rescue",
        "query": '"migrating to Dynamics 365" UK company',
    },
    {
        "signal_class": "implementation_migration_upgrade_rescue",
        "query": '"Business Central migration" UK company',
    },
    {
        "signal_class": "implementation_migration_upgrade_rescue",
        "query": '"Finance and Operations rollout" "Dynamics 365" UK company',
    },
    {
        "signal_class": "implementation_migration_upgrade_rescue",
        "query": '"Dynamics CRM replacement" "United Kingdom" company',
    },
    {
        "signal_class": "installed_base_discovery",
        "query": '"uses Dynamics 365" UK company',
    },
    {
        "signal_class": "installed_base_discovery",
        "query": '"Dynamics 365 customer" "United Kingdom"',
    },
    {
        "signal_class": "installed_base_discovery",
        "query": 'site:microsoft.com "Dynamics 365" "United Kingdom" "customer story"',
    },
    {
        "signal_class": "transformation_trigger",
        "query": '"Dynamics 365" "digital transformation" UK company',
    },
    {
        "signal_class": "transformation_trigger",
        "query": '"Microsoft business applications" ("ERP" OR "CRM") transformation ("United Kingdom" OR UK OR Ireland)',
    },
]

VALID_STATUSES = {
    "ready_to_contact",
    "provisional_contact_now",
    "source_cleanup_needed",
    "reject",
}
STATUS_PRIORITY = {
    "ready_to_contact": 0,
    "provisional_contact_now": 1,
    "source_cleanup_needed": 2,
    "reject": 9,
}
TARGET_ROLES = [
    "Head of IT",
    "IT Director",
    "Business Systems Manager",
    "ERP Manager",
    "CRM Manager",
    "Finance Systems Manager",
]
DO_NOT_CLAIM = [
    "Do not claim they need help, budget, outsourcing, or rescue unless the public evidence says so.",
    "Do not claim named contacts or email addresses beyond current evidence.",
    "Do not mention AI classification or internal scoring.",
]
TENDER_TERMS = (
    "find-tender.service.gov.uk",
    "contracts.service.gov.uk",
    "etenders.gov.ie",
    "tender",
    "rfp",
    "procurement notice",
    "contract notice",
)
SECRET_PATTERNS = {
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    "oauth_token": re.compile(r"ya29\.[0-9A-Za-z_\-.]+"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    "openai_like_key": re.compile(r"\bsk-[0-9A-Za-z_\-]{16,}"),
    "bearer_token": re.compile(r"bearer\s+[0-9A-Za-z_\-.]{16,}", re.IGNORECASE),
}


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(value: Any, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit and len(text) > limit:
        return text[: max(0, limit - 3)].rstrip() + "..."
    return text


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def first_url(candidate: dict[str, Any]) -> str:
    urls = as_list(candidate.get("evidence_urls"))
    return str(urls[0]).strip() if urls else ""


def first_snippet(candidate: dict[str, Any], limit: int = 700) -> str:
    snippets = [clean_text(item) for item in as_list(candidate.get("evidence_snippets")) if clean_text(item)]
    if snippets:
        return clean_text(snippets[0], limit)
    return clean_text(candidate.get("signal_summary"), limit)


def candidate_id(candidate: dict[str, Any], index: int) -> str:
    trace = candidate.get("audit_trace") or {}
    return str(trace.get("candidate_id") or candidate.get("candidate_id") or f"fresh_candidate_{index}")


def candidate_key(candidate: dict[str, Any]) -> str:
    company = clean_text(candidate.get("company_name")).lower()
    url = first_url(candidate).rstrip("/").lower()
    title = clean_text(candidate.get("signal_summary")).lower()
    return "|".join([company, url, title])


def candidate_text(candidate: dict[str, Any]) -> str:
    return " ".join(
        clean_text(part)
        for part in [
            candidate.get("company_name"),
            candidate.get("signal_summary"),
            candidate.get("signal_type"),
            candidate.get("dynamics_product"),
            candidate.get("country"),
            candidate.get("rejection_reason"),
            " ".join(str(item) for item in as_list(candidate.get("evidence_snippets"))),
            " ".join(str(item) for item in as_list(candidate.get("evidence_urls"))),
        ]
    ).lower()


def hard_exclusion_reason(candidate: dict[str, Any]) -> str | None:
    text = candidate_text(candidate)
    url = first_url(candidate).lower()
    reason = str(candidate.get("rejection_reason") or "").lower()
    if not url:
        return "missing_evidence_url"
    if "example.test" in url or "example.test" in text:
        return "fake_or_example_url"
    if "linkedin.com" in url:
        return "private_or_linkedin_source_excluded"
    if "tender_or_procurement" in reason or any(term in text or term in url for term in TENDER_TERMS):
        return "tender_or_procurement_out_of_scope"
    if not has_matching_fetch_proof(candidate):
        return "missing_verified_live_public_evidence"
    if "missing_explicit_dynamics_365_or_business_app_evidence" == reason and not any(
        term in text
        for term in (
            "dynamics 365",
            "d365",
            "business central",
            "dataverse",
            "power platform",
            "dynamics crm",
            "microsoft business applications",
        )
    ):
        return "missing_d365_or_microsoft_business_app_evidence"
    return None


def has_matching_fetch_proof(candidate: dict[str, Any]) -> bool:
    """Accept only a successful fetch record bound to the selected evidence URL."""
    url = first_url(candidate)
    fetch = candidate.get("source_fetch") or {}
    return bool(
        url
        and fetch.get("verified_live") is True
        and fetch.get("source_fetch_status") in {"fetched", "success", "recovered"}
        and clean_text(fetch.get("fetched_at"))
        and clean_text(fetch.get("source_name"))
        and url in {str(fetch.get("url") or ""), str(fetch.get("final_url") or "")}
    )


def candidate_score(candidate: dict[str, Any]) -> int:
    tier = str(candidate.get("signal_tier") or "D")
    reason = str(candidate.get("rejection_reason") or "")
    text = candidate_text(candidate)
    base = {"A": 130, "B": 112, "C": 78}.get(tier, 20)
    if tier == "D":
        base = {
            "vendor_or_service_provider_page_without_defensible_target_customer": 72,
            "recruitment_agency_post_without_defensible_hiring_company": 68,
            "uk_ireland_not_evidenced": 62,
            "missing_explicit_dynamics_365_or_business_app_evidence": 35,
            "generic_it_support_without_dynamics_365_evidence": 5,
            "tender_or_procurement_out_of_scope": -100,
        }.get(reason, 20)
    for term in ("rescue", "failed implementation", "backlog", "support analyst", "application support"):
        if term in text:
            base += 18
    for term in ("migration", "upgrade", "rollout", "implementation", "business central", "f&o"):
        if term in text:
            base += 12
    for term in ("case study", "customer story", "implemented dynamics 365", "uses dynamics 365"):
        if term in text:
            base += 8
    if str(candidate.get("source_url_type")) == "grounding_redirect":
        base -= 4
    if hard_exclusion_reason(candidate):
        base -= 200
    return base + int(candidate.get("confidence_score") or 0) + int(candidate.get("urgency_score") or 0)


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(candidates, start=1):
        key = candidate_key(candidate) or candidate_id(candidate, index)
        current = best.get(key)
        if current is None or candidate_score(candidate) > candidate_score(current):
            best[key] = candidate
    return sorted(best.values(), key=lambda item: (-candidate_score(item), clean_text(item.get("company_name"))))


def preflight() -> dict[str, Any]:
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", DEFAULT_PROJECT)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION)
    providers = discover_d365_search_providers()
    readiness = google_native_readiness()
    model_name, model_source = effective_google_model()
    return {
        "agent_name": root_agent.name,
        "sub_agents": [agent.name for agent in root_agent.sub_agents],
        "providers": providers,
        "google_native_readiness": readiness,
        "model": model_name,
        "model_source": model_source,
        "env_project": os.environ.get("GOOGLE_CLOUD_PROJECT"),
        "env_location": os.environ.get("GOOGLE_CLOUD_LOCATION"),
    }


def run_fresh_search(*, max_live_requests: int, max_results: int) -> dict[str, Any]:
    started = now_utc()
    all_leads: list[dict[str, Any]] = []
    all_rejected: list[dict[str, Any]] = []
    query_runs = []
    live_requests = 0
    for index, item in enumerate(SEARCH_QUERIES[:max_live_requests], start=1):
        print(
            f"[fresh-search] {index}/{max_live_requests} {item['signal_class']}: {item['query']}",
            flush=True,
        )
        result = find_uk_ie_d365_leads(
            query=item["query"],
            max_results=max_results,
            max_live_requests=1,
            include_rejected=True,
            provider_name="google_grounding",
        )
        live_requests += int(result.get("live_requests_made") or 0)
        all_leads.extend(result.get("leads") or [])
        all_rejected.extend(result.get("rejected_leads") or [])
        query_runs.append(
            {
                "signal_class": item["signal_class"],
                "query": item["query"],
                "status": result.get("status"),
                "provider": result.get("provider"),
                "live_requests_made": result.get("live_requests_made"),
                "lead_count": result.get("lead_count"),
                "rejected_count": result.get("rejected_count"),
                "tier_counts": result.get("tier_counts"),
                "provider_errors": result.get("provider_errors") or [],
            }
        )
        print(
            "[fresh-search] "
            f"{index}/{max_live_requests} status={result.get('status')} "
            f"leads={result.get('lead_count')} rejected={result.get('rejected_count')} "
            f"requests={result.get('live_requests_made')}",
            flush=True,
        )
    leads = dedupe_candidates(all_leads)
    rejected = dedupe_candidates(all_rejected)
    tier_counts = Counter(str(candidate.get("signal_tier") or "D") for candidate in leads + rejected)
    return {
        "metadata": {
            "artifact_type": "fresh_uk_ie_d365_grounded_search",
            "generated_at": now_utc(),
            "started_at": started,
            "finished_at": now_utc(),
            "fresh_search_used": True,
            "browser_used": False,
            "gmail_used": False,
            "emails_sent": False,
            "deployment_attempted": False,
            "query_count_planned": len(SEARCH_QUERIES[:max_live_requests]),
            "live_search_request_count": live_requests,
            "max_results_per_query": max_results,
            "query_strategy": "25 bounded strong-signal UK/IE D365 public search prompts distilled from the default query matrix.",
            "model": effective_google_model()[0],
            "provider": "google_grounding",
            "project": os.environ.get("GOOGLE_CLOUD_PROJECT"),
            "location": os.environ.get("GOOGLE_CLOUD_LOCATION"),
        },
        "provider": "google_grounding",
        "status": "ok" if leads or rejected else "no_verified_leads_found",
        "queries_run": query_runs,
        "leads": leads,
        "rejected_leads": rejected,
        "lead_count": len(leads),
        "rejected_count": len(rejected),
        "tier_counts": dict(tier_counts),
        "fetched_at": started,
        "run_finished_at": now_utc(),
    }


def review_prompt(candidate: dict[str, Any], prepared_record: dict[str, Any]) -> str:
    payload = {
        "task": "Curate a UK/IE Microsoft Dynamics 365 lead candidate for a second 12-lead pack.",
        "operator_instruction": (
            "The last 12-lead pack was good. Find another 12 like that. "
            "Do not hard-rule-out useful candidates just because deterministic rules rejected them. "
            "Use AI judgement over the saved public evidence. Preserve tender/procurement exclusion "
            "and no-fake-evidence rules."
        ),
        "quality_bar": [
            "Prefer support pain, rescue/backlog, direct employer hiring, implementation/rollout, migration/upgrade, and Business Central/F&O/CE support signals.",
            "Installed-base leads can be useful only when the public evidence gives a plausible D365 support or optimization angle.",
            "Weak real candidates should be source_cleanup_needed, not overclaimed.",
            "Reject tender/procurement-only, fake, private LinkedIn, and no-D365 candidates.",
        ],
        "allowed_values": {
            "llm_decision": ["accept", "provisional", "reject"],
            "lead_status": ["ready_to_contact", "provisional_contact_now", "source_cleanup_needed", "reject"],
            "confidence": ["high", "medium", "low"],
        },
        "required_output_fields": [
            "llm_decision",
            "lead_status",
            "confidence",
            "trigger_type",
            "d365_microsoft_business_app_evidence",
            "why_useful",
            "source_excerpt",
            "suggested_contact_target_roles",
            "suggested_first_outreach_angle",
            "remaining_uncertainty",
            "what_not_to_claim",
            "notes",
        ],
        "hard_rules": [
            "Use only the candidate evidence provided in this prompt.",
            "Do not invent companies, URLs, contacts, emails, dates, source titles, or product usage claims.",
            "Do not include new URLs or email addresses in your answer.",
            "If useful but unresolved, choose source_cleanup_needed.",
        ],
        "candidate_record": prepared_record,
        "source_candidate": {
            "company_name": candidate.get("company_name"),
            "signal_tier": candidate.get("signal_tier"),
            "signal_type": candidate.get("signal_type"),
            "dynamics_product": candidate.get("dynamics_product"),
            "country": candidate.get("country"),
            "source_url_type": candidate.get("source_url_type"),
            "rejection_reason": candidate.get("rejection_reason"),
            "recommended_outreach_angle": candidate.get("recommended_outreach_angle"),
            "suggested_contact_roles": candidate.get("suggested_contact_roles"),
        },
    }
    return (
        "Return JSON only. Do not wrap in markdown. The JSON must contain one object.\n\n"
        + json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True)
    )


def detect_invented_values(raw: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    text = json.dumps(raw, sort_keys=True, ensure_ascii=True)
    allowed_urls = {url.rstrip("/").lower() for url in as_list(candidate.get("evidence_urls"))}
    findings = []
    for url in re.findall(r"https?://[^\s\"'<>]+", text):
        if url.rstrip(".,;)]").rstrip("/").lower() not in allowed_urls:
            findings.append("new_url")
    if re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", text, re.I):
        findings.append("email_like_value")
    return sorted(set(findings))


def call_ai_reviewer(
    candidates: list[dict[str, Any]],
    *,
    max_review_candidates: int,
    model: str | None,
) -> dict[str, Any]:
    client, client_info = make_vertex_reviewer_client(model)
    selected = candidates[:max_review_candidates]
    records = []
    requests = []
    started = now_utc()
    for index, candidate in enumerate(selected, start=1):
        prepared = prepare_candidate(candidate, index=index)["review_record"]
        prompt = review_prompt(candidate, prepared)
        print(
            f"[ai-review] {index}/{len(selected)} {clean_text(candidate.get('company_name'))}",
            flush=True,
        )
        response_text, usage, model_version = call_vertex_reviewer(
            client=client,
            model=client_info["model"],
            prompt=prompt,
        )
        try:
            raw = parse_review_json(response_text)
            parse_error = None
        except Exception as exc:
            raw = {
                "llm_decision": "reject",
                "lead_status": "reject",
                "confidence": "low",
                "notes": [f"Review parse failed: {type(exc).__name__}"],
            }
            parse_error = str(exc)[:300]
        invented = detect_invented_values(raw, candidate)
        records.append(
            {
                "candidate": candidate,
                "prepared_record": prepared,
                "raw_review": raw,
                "parse_error": parse_error,
                "invented_candidate_facts_detected": bool(invented),
                "invented_fact_findings": invented,
                "request_index": index,
                "candidate_id": candidate_id(candidate, index),
            }
        )
        requests.append(
            {
                "request_index": index,
                "candidate_id": candidate_id(candidate, index),
                "usage_metadata": usage,
                "model_version": model_version,
            }
        )
        print(
            "[ai-review] "
            f"{index}/{len(selected)} decision={review_decision(raw)} "
            f"status={clean_text(raw.get('lead_status')).lower() or 'missing'}",
            flush=True,
        )
    return {
        "metadata": {
            "artifact_type": "fresh_candidate_ai_review",
            "started_at": started,
            "finished_at": now_utc(),
            "live_llm_used": True,
            "reviewed_candidate_count": len(records),
            "model": client_info.get("model"),
            "provider_path": client_info.get("provider_path"),
            "project": client_info.get("project"),
            "location": client_info.get("location"),
            "auth_mode": client_info.get("auth_mode"),
        },
        "records": records,
        "requests": requests,
    }


def safe_review_text(raw: dict[str, Any], key: str, fallback: Any = "") -> Any:
    value = raw.get(key)
    if value in (None, "", []):
        return fallback
    return value


def normalize_status(candidate: dict[str, Any], raw: dict[str, Any]) -> str:
    status = clean_text(raw.get("lead_status")).lower()
    if status not in VALID_STATUSES:
        decision = clean_text(raw.get("llm_decision")).lower()
        status = "provisional_contact_now" if decision in {"accept", "provisional"} else "reject"
    if status != "reject" and hard_exclusion_reason(candidate):
        return "reject"
    if status == "ready_to_contact" and str(candidate.get("source_url_type")) == "grounding_redirect":
        return "source_cleanup_needed"
    return status


def review_decision(raw: dict[str, Any]) -> str:
    decision = clean_text(raw.get("llm_decision")).lower()
    return decision if decision in {"accept", "provisional", "reject"} else "reject"


def final_score(review_record: dict[str, Any]) -> int:
    candidate = review_record["candidate"]
    raw = review_record["raw_review"]
    status = normalize_status(candidate, raw)
    score = candidate_score(candidate)
    score += {"ready_to_contact": 90, "provisional_contact_now": 65, "source_cleanup_needed": 35, "reject": -500}.get(status, 0)
    score += {"high": 30, "medium": 15, "low": 0}.get(clean_text(raw.get("confidence")).lower(), 0)
    if review_decision(raw) == "accept":
        score += 35
    elif review_decision(raw) == "provisional":
        score += 20
    if review_record.get("invented_candidate_facts_detected"):
        score -= 120
    return score


def final_lead_from_review(review_record: dict[str, Any], rank: int) -> dict[str, Any]:
    candidate = review_record["candidate"]
    source_fetch = candidate.get("source_fetch") or {}
    raw = review_record["raw_review"]
    status = normalize_status(candidate, raw)
    url = first_url(candidate)
    excerpt = first_snippet(candidate)
    roles = as_list(safe_review_text(raw, "suggested_contact_target_roles", candidate.get("suggested_contact_roles") or TARGET_ROLES))
    if not roles:
        roles = TARGET_ROLES
    uncertainty = [
        clean_text(item)
        for item in as_list(safe_review_text(raw, "remaining_uncertainty", candidate.get("missing_verification_points") or []))
        if clean_text(item)
    ]
    if str(candidate.get("source_url_type")) == "grounding_redirect" and not any("clean source" in item.lower() for item in uncertainty):
        uncertainty.append("source URL is a Google grounding redirect; clean source URL should be verified before outreach")
    if review_record.get("invented_candidate_facts_detected"):
        uncertainty.append("AI review attempted to add facts outside the source candidate; extra facts were ignored")
    return {
        "rank": rank,
        "candidate_id": review_record["candidate_id"],
        "company_name": clean_text(candidate.get("company_name")),
        "lead_status": status,
        "confidence": clean_text(raw.get("confidence") or "medium").lower(),
        "trigger_type": clean_text(safe_review_text(raw, "trigger_type", candidate.get("signal_type") or "D365 signal")),
        "d365_microsoft_business_app_evidence": clean_text(
            safe_review_text(raw, "d365_microsoft_business_app_evidence", excerpt),
            900,
        ),
        "source_url": url,
        "source_url_type": candidate.get("source_url_type"),
        "source_excerpt": clean_text(safe_review_text(raw, "source_excerpt", excerpt), 900),
        "source_provider": candidate.get("source_provider") or "google_grounding",
        "source_query_group": (candidate.get("audit_trace") or {}).get("source_query_group"),
        "source_query": (candidate.get("audit_trace") or {}).get("source_query"),
        "why_useful": clean_text(safe_review_text(raw, "why_useful", candidate.get("recommended_outreach_angle")), 900),
        "deterministic_decision": "reject" if candidate.get("signal_tier") == "D" else "accept",
        "deterministic_tier": candidate.get("signal_tier"),
        "deterministic_rejection_reason": candidate.get("rejection_reason"),
        "llm_decision": review_decision(raw),
        "suggested_contact_target_roles": [clean_text(role, 120) for role in roles[:8]],
        "suggested_first_outreach_angle": clean_text(
            safe_review_text(raw, "suggested_first_outreach_angle", candidate.get("recommended_outreach_angle")),
            900,
        ),
        "remaining_uncertainty": uncertainty or ["verify current ownership and best contact route before outreach"],
        "what_not_to_claim": [
            clean_text(item)
            for item in as_list(safe_review_text(raw, "what_not_to_claim", DO_NOT_CLAIM))
            if clean_text(item)
        ]
        or DO_NOT_CLAIM,
        "verified_live": has_matching_fetch_proof(candidate),
        "source_name": clean_text(source_fetch.get("source_name")),
        "fetched_at": clean_text(source_fetch.get("fetched_at")),
        "final_score": final_score(review_record),
    }


def curate_final_leads(review_output: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    eligible = []
    for record in review_output["records"]:
        candidate = record["candidate"]
        raw = record["raw_review"]
        status = normalize_status(candidate, raw)
        if status == "reject" or review_decision(raw) == "reject":
            continue
        if hard_exclusion_reason(candidate):
            continue
        eligible.append(record)
    eligible.sort(
        key=lambda record: (
            STATUS_PRIORITY[normalize_status(record["candidate"], record["raw_review"])],
            -final_score(record),
            clean_text(record["candidate"].get("company_name")),
        )
    )
    final = [final_lead_from_review(record, rank=index) for index, record in enumerate(eligible[:limit], start=1)]
    return final


def render_markdown(data: dict[str, Any]) -> str:
    metadata = data["metadata"]
    leads = data["leads"]
    lines = [
        "# UK/IE D365 Useful Leads Next",
        "",
        f"Generated: `{metadata['generated_at']}`",
        "",
        "## Immediate Counts",
        "",
        f"- Total useful leads: {len(leads)}",
        f"- Ready to contact: {metadata['ready_to_contact_count']}",
        f"- Provisional contact now: {metadata['provisional_contact_now_count']}",
        f"- Source cleanup needed: {metadata['source_cleanup_needed_count']}",
        f"- Fresh search used: {str(metadata['fresh_search_used']).lower()}",
        f"- Fresh grounded search requests: {metadata['fresh_live_search_request_count']}",
        f"- AI-reviewed candidates: {metadata['ai_reviewed_candidate_count']}",
        "",
        "## Best Leads First",
        "",
    ]
    for lead in leads:
        lines.extend(
            [
                f"### {lead['rank']}. {lead['company_name']} - {lead['lead_status']} ({lead['confidence']})",
                "",
                f"- Signal: {lead['trigger_type']}",
                f"- Source URL: {lead['source_url']}",
                f"- Evidence: {lead['source_excerpt']}",
                f"- Why useful: {lead['why_useful']}",
                f"- Deterministic: {lead['deterministic_decision']}; tier: {lead['deterministic_tier']}; rejection: {lead['deterministic_rejection_reason'] or 'none'}",
                f"- LLM decision: {lead['llm_decision']}",
                "- Target roles: " + ", ".join(lead["suggested_contact_target_roles"]),
                f"- Outreach angle: {lead['suggested_first_outreach_angle']}",
                "- Do not claim: " + "; ".join(lead["what_not_to_claim"]),
                "- Remaining uncertainty: " + "; ".join(lead["remaining_uncertainty"]),
                "",
            ]
        )
    return "\n".join(lines)


def render_report(data: dict[str, Any], paths: dict[str, Path]) -> str:
    metadata = data["metadata"]
    return "\n".join(
        [
            "# UK/IE D365 Useful Leads Next Report",
            "",
            f"Generated: `{metadata['generated_at']}`",
            "",
            "## Execution Summary",
            "",
            f"- Total useful leads found: {metadata['total_useful_leads_found']}",
            f"- Ready to contact: {metadata['ready_to_contact_count']}",
            f"- Provisional contact now: {metadata['provisional_contact_now_count']}",
            f"- Source cleanup needed: {metadata['source_cleanup_needed_count']}",
            f"- Fresh search used: {str(metadata['fresh_search_used']).lower()}",
            f"- Browser used: {str(metadata['browser_used']).lower()}",
            f"- Emails/Gmail used: {str(metadata['gmail_used']).lower()}",
            f"- Deployment attempted: {str(metadata['deployment_attempted']).lower()}",
            f"- Fresh grounded search requests: {metadata['fresh_live_search_request_count']}",
            f"- AI review requests: {metadata['ai_reviewed_candidate_count']}",
            f"- Model/provider/project/location: `{json.dumps(metadata['model_provider_project_location'], sort_keys=True)}`",
            "",
            "## Files Written",
            "",
            *[f"- `{path}`" for path in paths.values()],
            "",
            "## Caveats",
            "",
            "- Source cleanup candidates should have clean source URLs or official pages verified before outreach.",
            "- Google grounding redirects were preserved when the clean source URL was not available from the run.",
            "- Deterministic classifier rules were not changed.",
            "- Secret scan is written separately and should be PASS before use.",
            "",
        ]
    )


def scan_secret_patterns(paths: list[Path]) -> dict[str, Any]:
    findings = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern_name, regex in SECRET_PATTERNS.items():
            for match in regex.finditer(text):
                findings.append(
                    {
                        "path": str(path),
                        "pattern": pattern_name,
                        "line": text.count("\n", 0, match.start()) + 1,
                        "value_redacted": True,
                    }
                )
    return {
        "generated_at": now_utc(),
        "passed": not findings,
        "finding_count": len(findings),
        "findings": findings,
    }


def zip_artifacts(zip_path: Path, paths: list[Path]) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.name)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-live-requests", type=int, default=25)
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--max-review-candidates", type=int, default=40)
    parser.add_argument("--model", default=None)
    parser.add_argument("--basename", default=DEFAULT_BASENAME)
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_live_requests < 1 or args.max_live_requests > len(SEARCH_QUERIES):
        raise SystemExit(f"--max-live-requests must be between 1 and {len(SEARCH_QUERIES)}")
    if args.max_review_candidates < 12:
        raise SystemExit("--max-review-candidates must be at least 12")

    print("[start] UK/IE D365 useful-leads-next run", flush=True)
    preflight_data = preflight()
    print(
        "[preflight] "
        f"agent={root_agent.name} provider={preflight_data['providers'].get('chosen_provider')} "
        f"ready={preflight_data['google_native_readiness'].get('ready')} "
        f"project={preflight_data['google_native_readiness'].get('adc', {}).get('project')}",
        flush=True,
    )
    chosen_provider = preflight_data["providers"].get("chosen_provider")
    if root_agent.name != "uk_ie_d365_leads":
        raise SystemExit(f"Unexpected UK agent name: {root_agent.name}")
    if chosen_provider != "google_grounding":
        raise SystemExit(f"Refusing to run: chosen provider is {chosen_provider!r}, not google_grounding.")
    if not preflight_data["google_native_readiness"].get("ready"):
        raise SystemExit("Refusing to run: Google-native readiness is false.")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now(UTC).strftime("%Y%m%d")
    fresh_path = output_dir / f"{FRESH_SEARCH_NAME}_{date_tag}.json"
    review_path = output_dir / f"{args.basename}_AI_REVIEW.json"
    json_path = output_dir / f"{args.basename}.json"
    md_path = output_dir / f"{args.basename}.md"
    report_path = output_dir / f"{args.basename}_REPORT.md"
    secret_scan_path = output_dir / f"{args.basename}_SECRET_SCAN.json"
    zip_path = output_dir / f"{args.basename}_EVIDENCE.zip"

    fresh = run_fresh_search(max_live_requests=args.max_live_requests, max_results=args.max_results)
    write_json(fresh_path, fresh)
    print(
        f"[fresh-search] wrote {fresh_path} leads={fresh['lead_count']} rejected={fresh['rejected_count']}",
        flush=True,
    )

    candidates = dedupe_candidates(list(fresh.get("leads") or []) + list(fresh.get("rejected_leads") or []))
    review = call_ai_reviewer(
        candidates,
        max_review_candidates=args.max_review_candidates,
        model=args.model,
    )
    review_serializable = {
        "metadata": review["metadata"],
        "requests": review["requests"],
        "records": [
            {
                "candidate_id": record["candidate_id"],
                "company_name": record["candidate"].get("company_name"),
                "candidate": record["candidate"],
                "raw_review": record["raw_review"],
                "parse_error": record["parse_error"],
                "invented_candidate_facts_detected": record["invented_candidate_facts_detected"],
                "invented_fact_findings": record["invented_fact_findings"],
            }
            for record in review["records"]
        ],
    }
    write_json(review_path, review_serializable)
    print(f"[ai-review] wrote {review_path}", flush=True)

    final_leads = curate_final_leads(review, limit=12)
    print(f"[curation] selected {len(final_leads)} final leads", flush=True)
    if len(final_leads) != 12:
        raise SystemExit(f"Expected exactly 12 useful leads, got {len(final_leads)}.")

    status_counts = Counter(lead["lead_status"] for lead in final_leads)
    final_data = {
        "metadata": {
            "generated_at": now_utc(),
            "artifact_type": "fresh_uk_ie_d365_useful_leads_next",
            "total_useful_leads_found": len(final_leads),
            "ready_to_contact_count": status_counts.get("ready_to_contact", 0),
            "provisional_contact_now_count": status_counts.get("provisional_contact_now", 0),
            "source_cleanup_needed_count": status_counts.get("source_cleanup_needed", 0),
            "fresh_search_used": True,
            "browser_used": False,
            "gmail_used": False,
            "emails_sent": False,
            "deployment_attempted": False,
            "fresh_live_search_request_count": fresh["metadata"]["live_search_request_count"],
            "ai_reviewed_candidate_count": review["metadata"]["reviewed_candidate_count"],
            "deterministic_rules_changed": False,
            "model_provider_project_location": {
                "search_model": fresh["metadata"]["model"],
                "review_model": review["metadata"]["model"],
                "provider": "google_grounding + google-genai Vertex AI via ADC",
                "project": review["metadata"]["project"],
                "location": review["metadata"]["location"],
            },
            "source_files": {
                "fresh_search": str(fresh_path),
                "ai_review": str(review_path),
            },
        },
        "excluded_policy": {
            "excluded": [
                "tenders/procurement portals",
                "private/authenticated LinkedIn sources",
                "synthetic/sample/demo/fake companies or URLs",
                "no D365/Microsoft business-app evidence",
            ],
            "no_invention_policy": "No companies, emails, people, URLs, or source facts were invented for the final leads.",
        },
        "leads": final_leads,
    }
    write_json(json_path, final_data)
    md_path.write_text(render_markdown(final_data), encoding="utf-8")
    report_path.write_text(
        render_report(
            final_data,
            {
                "fresh_search": fresh_path,
                "ai_review": review_path,
                "json": json_path,
                "markdown": md_path,
                "report": report_path,
                "secret_scan": secret_scan_path,
                "zip": zip_path,
            },
        ),
        encoding="utf-8",
    )
    secret_scan = scan_secret_patterns([fresh_path, review_path, json_path, md_path, report_path])
    write_json(secret_scan_path, secret_scan)
    if not secret_scan["passed"]:
        raise SystemExit(f"Secret scan failed with {secret_scan['finding_count']} findings.")
    zip_artifacts(zip_path, [fresh_path, review_path, json_path, md_path, report_path, secret_scan_path])

    print(
        json.dumps(
            {
                "status": "ok",
                "lead_count": len(final_leads),
                "status_counts": dict(status_counts),
                "fresh_search": str(fresh_path),
                "ai_review": str(review_path),
                "json": str(json_path),
                "markdown": str(md_path),
                "report": str(report_path),
                "secret_scan": str(secret_scan_path),
                "zip": str(zip_path),
                "fresh_live_search_request_count": fresh["metadata"]["live_search_request_count"],
                "ai_reviewed_candidate_count": review["metadata"]["reviewed_candidate_count"],
                "model_provider_project_location": final_data["metadata"]["model_provider_project_location"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
