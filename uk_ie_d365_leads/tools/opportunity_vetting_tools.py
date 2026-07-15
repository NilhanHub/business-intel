"""AI opportunity-vetting workflow for UK/Ireland D365 lead candidates."""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uk_ie_d365_leads.tools import discovery_backbone_tools, lead_tools

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = PROJECT_ROOT / "Evidence"
DEFAULT_OUTPUT_BASENAME = "UK_IE_D365_AI_VETTING"
FRESH_LEADS_BASENAME = "UK_IE_D365_USEFUL_LEADS_FRESH_20260612"
DETERMINISTIC_AUDIT_BASENAME = "UK_IE_D365_DETERMINISTIC_REJECT_AUDIT_20260612"
GEMINI_AGENT_PLATFORM_PROVIDER_PATH = "google-genai Gemini Enterprise Agent Platform / Vertex AI API via ADC"

VALID_LEAD_STATUSES = {
    "ready_to_contact",
    "provisional_contact_now",
    "source_cleanup_needed",
    "reject",
}
VALID_SIGNAL_STRENGTHS = {"strong", "promising", "emerging", "weak"}
REQUIRED_VETTING_FIELDS = [
    "lead_status",
    "signal_strength",
    "signal_type",
    "evidence_used",
    "evidence_gaps",
    "opportunity_signal",
    "why_this_matters_to_1bt",
    "commercial_opening",
    "value_of_signal",
    "intelligence_reading",
    "board_relevance",
    "contact_target_roles",
    "do_not_claim_notes",
    "remaining_uncertainty",
    "final_rejection_reason",
]
NON_REJECT_REQUIRED_WRITEUP_FIELDS = [
    "signal_type",
    "evidence_used",
    "opportunity_signal",
    "why_this_matters_to_1bt",
    "commercial_opening",
    "value_of_signal",
    "intelligence_reading",
    "board_relevance",
    "contact_target_roles",
]
DEFAULT_DO_NOT_CLAIM_NOTES = [
    "Do not claim budget, dissatisfaction, incumbent displacement, or an active buying process.",
    "Do not claim facts beyond the supplied public evidence.",
]
SECRET_PATTERNS = {
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    "oauth_token": re.compile(r"ya29\.[0-9A-Za-z_\-.]+"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    "openai_like_key": re.compile(r"\bsk-[0-9A-Za-z_\-]{16,}"),
    "bearer_token": re.compile(r"bearer\s+[0-9A-Za-z_\-.]{16,}", re.IGNORECASE),
}
PRIOR_ACCOUNT_ARTIFACTS = [
    "UK_IE_D365_USEFUL_LEADS_NOW.json",
    "UK_IE_D365_USEFUL_LEADS_NEXT.json",
    "UK_IE_D365_AI_Opportunity_Intelligence_14_SOURCE_MAP.json",
]
ADDITIONAL_PRIOR_OR_PARKED_ACCOUNTS = {
    "Biffa Group",
    "Charterhouse Holdings",
    "Clariness",
    "Hadley Group",
    "Kepak Group",
    "Simply Dynamics 365 Growth Announcement- D365 Partner",
    "Simply Dynamics",
    "Synergy Technology",
    "The Royal Society",
    "The Royal Society / Subscribe360 case-study source",
    "Tourism NI",
    "UK defence apparel manufacturer",
    "UK defence apparel manufacturer (unnamed in saved evidence)",
    "Uniphar Medtech Limited",
    "Willmott Dixon",
    "Glenveagh",
    "Mental Health Commission Ireland",
    "Weetabix Food Company",
    "Net Zero Group Ireland",
    "Jackson's Bakery",
    "Littlefish UK Ltd",
    "London Borough of Harrow",
    "Harrow",
    "Sustainable Energy Authority of Ireland",
    "Sustainable Energy Authority of Ireland (SEAI)",
    "SEAI",
    "Alzheimer's Research UK",
    "Lewisham Council",
    "Wesleyan",
    "Midland Systems",
    "The Felix Project",
    "Colorlites",
    "Colorlites (THF Group)",
    "Colorlites / THF Group",
    "THF Group",
    "Aurivo",
    "Aurivo Co-operative Society Limited",
    "RHealthcare",
    "ADEGA manufacturer",
    "Teachers Union of Ireland",
}
FORBIDDEN_FINAL_URL_TERMS = (
    "example.test",
    "example.com",
    "linkedin.com",
    "vertexaisearch.cloud.google.com",
    "find-tender.service.gov.uk",
    "contracts.service.gov.uk",
    "etenders.gov.ie",
)
GENERIC_FINAL_COMPANY_TERMS = (
    "jobs",
    "with salaries",
    "browse it",
    "application support",
    "support consultant",
    "support analyst",
    "system analyst",
    "nigel frank",
    "akkodis",
    "vertexaisearch",
    "d365 jobs",
    "dynamics support jobs",
)


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def vetter_model_name(model_override: str | None = None) -> str:
    return (
        model_override
        or os.environ.get("D365_VETTER_MODEL")
        or os.environ.get("D365_REVIEW_MODEL")
        or os.environ.get("D365_GOOGLE_MODEL")
        or "gemini-2.5-flash"
    )


def load_saved_evidence(evidence_file: Path | str) -> dict[str, Any]:
    return json.loads(Path(evidence_file).read_text(encoding="utf-8"))


def all_reviewable_candidates(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the non-hard-rejected pool for AI vetting."""
    pool = []
    for key in (
        "review_candidates",
        "leads",
        "accepted_leads",
        "tier_a_ready_leads",
        "tier_b_provisional_leads",
        "tier_c_watchlist_leads",
        "rejected_leads",
    ):
        pool.extend(list(data.get(key) or []))
    reviewable = []
    seen: set[str] = set()
    for candidate in pool:
        hard_reason = candidate.get("hard_rejection_reason")
        rejection_reason = candidate.get("rejection_reason")
        if hard_reason or rejection_reason in lead_tools.HARD_REJECTION_REASONS:
            continue
        candidate_key = lead_tools.candidate_id(
            str(candidate.get("company_name") or ""),
            " ".join(str(url) for url in candidate.get("evidence_urls") or []),
            " ".join(str(snippet) for snippet in candidate.get("evidence_snippets") or []),
        )
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        reviewable.append(candidate)
    return reviewable


def select_vetting_candidates(candidates: list[dict[str, Any]], max_candidates: int) -> list[dict[str, Any]]:
    if max_candidates <= 0:
        raise ValueError("--max-candidates must be greater than 0")
    return candidates[:max_candidates]


def prepare_vetting_record(
    candidate: dict[str, Any],
    *,
    index: int,
    follow_up_evidence: list[dict[str, Any]] | None = None,
    stage: str = "initial",
) -> dict[str, Any]:
    evidence_urls = [str(url) for url in candidate.get("evidence_urls") or [] if url]
    evidence_snippets = [str(item) for item in candidate.get("evidence_snippets") or [] if item]
    source_channel = discovery_backbone_tools.classify_source_channel(
        source=candidate.get("source_provider"),
        url=evidence_urls[0] if evidence_urls else None,
        explicit=candidate.get("source_channel"),
    )
    return {
        "candidate_index": index,
        "candidate_id": candidate.get("candidate_id")
        or lead_tools.candidate_id(
            str(candidate.get("company_name") or ""),
            " ".join(evidence_urls),
            " ".join(evidence_snippets),
        ),
        "stage": stage,
        "company_name": candidate.get("company_name"),
        "source_company": candidate.get("source_company"),
        "source_role": candidate.get("source_role"),
        "account_identity_status": candidate.get("account_identity_status"),
        "end_customer_candidates": candidate.get("end_customer_candidates") or [],
        "identity_evidence_excerpt": candidate.get("identity_evidence_excerpt"),
        "identity_confidence": candidate.get("identity_confidence"),
        "identity_notes": candidate.get("identity_notes") or [],
        "identity_resolution_required": bool(candidate.get("identity_resolution_required")),
        "country": candidate.get("country"),
        "signal_type": candidate.get("signal_type"),
        "signal_tier": candidate.get("signal_tier"),
        "dynamics_product": candidate.get("dynamics_product"),
        "signal_summary": candidate.get("signal_summary"),
        "evidence_urls": evidence_urls,
        "evidence_snippets": evidence_snippets,
        "source_provider": candidate.get("source_provider"),
        "source_type": candidate.get("source_type"),
        "source_url_type": candidate.get("source_url_type"),
        "source_channel": source_channel,
        "original_url": candidate.get("original_url"),
        "final_url": candidate.get("final_url"),
        "source_fetch_status": candidate.get("source_fetch_status"),
        "source_fetch": candidate.get("source_fetch") or {},
        "verified_live": bool(candidate.get("verified_live")),
        "final_pdf_eligible": discovery_backbone_tools.final_pdf_eligible_from_channel(source_channel),
        "confidence_score": candidate.get("confidence_score"),
        "urgency_score": candidate.get("urgency_score"),
        "fit_for_1BT": candidate.get("fit_for_1BT"),
        "recommended_outreach_angle": candidate.get("recommended_outreach_angle"),
        "suggested_contact_roles": candidate.get("suggested_contact_roles") or [],
        "missing_verification_points": candidate.get("missing_verification_points") or [],
        "deterministic_flags": candidate.get("deterministic_flags") or [],
        "retention_status": candidate.get("retention_status"),
        "run_id": candidate.get("run_id"),
        "company_fingerprint": candidate.get("company_fingerprint"),
        "opportunity_fingerprint": candidate.get("opportunity_fingerprint"),
        "source_fingerprint": candidate.get("source_fingerprint"),
        "hard_rejection_reason": candidate.get("hard_rejection_reason"),
        "rejection_reason": candidate.get("rejection_reason"),
        "audit_trace": candidate.get("audit_trace"),
        "final_decision": candidate.get("final_decision"),
        "follow_up_evidence": follow_up_evidence or [],
    }


def build_vetting_prompt(record: dict[str, Any]) -> str:
    payload = {
        "task": "Vet one UK/Ireland D365 candidate for 1BT sales opportunity intelligence.",
        "hard_rules": [
            "Use only the candidate and follow-up evidence in this payload.",
            "Do not invent companies, URLs, D365 evidence, contacts, emails, dates, source facts, or product usage claims.",
            "Reject tender/procurement-only, fake/sample/demo URLs, private LinkedIn, and candidates with no D365/Microsoft business-app evidence.",
            "Every non-reject output must cite at least one supplied public evidence URL or supplied evidence excerpt.",
            "Every non-reject output must include a clean evidence URL, evidence excerpt, signal strength, lead status, 1BT commercial opening, do-not-claim notes, and remaining uncertainty.",
            "Do not use private LinkedIn, tender/procurement-only pages, fake/example URLs, or Google grounding redirect URLs as final evidence.",
            "Agent Search, Workspace, CRM, and custom MCP records are hints only; they need public-web evidence before final publication.",
            "If required evidence or blank required write-up fields make the candidate unresolved, choose source_cleanup_needed.",
            "If the candidate is useful but unresolved, choose source_cleanup_needed.",
            "Return JSON only.",
        ],
        "allowed_values": {
            "lead_status": sorted(VALID_LEAD_STATUSES),
            "signal_strength": sorted(VALID_SIGNAL_STRENGTHS),
        },
        "optional_control_fields": ["needs_follow_up", "follow_up_queries"],
        "required_output_fields": REQUIRED_VETTING_FIELDS,
        "non_reject_required_writeup_fields": NON_REJECT_REQUIRED_WRITEUP_FIELDS,
        "candidate_record": record,
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


def make_vertex_vetter_client(model_override: str | None = None) -> tuple[Any, dict[str, Any]]:
    from google import genai

    prepare = getattr(lead_tools, "_prepare_google_native_env", None)
    if prepare:
        prepare()
    readiness = lead_tools.google_native_readiness()
    project = readiness.get("effective_project")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
    model = vetter_model_name(model_override)
    if not project:
        raise RuntimeError("Vertex/ADC project is unclear; refusing live vetting.")
    client = genai.Client(vertexai=True, project=project, location=location)
    return client, {
        "model": model,
        "provider_path": GEMINI_AGENT_PLATFORM_PROVIDER_PATH,
        "project": project,
        "location": location,
        "auth_mode": "ADC",
    }


def call_vertex_vetter(*, client: Any, model: str, prompt: str) -> tuple[str, dict[str, Any], str | None]:
    response = client.models.generate_content(model=model, contents=prompt)
    usage = getattr(response, "usage_metadata", None)
    usage_dict = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage or {})
    model_version = getattr(response, "model_version", None)
    return str(getattr(response, "text", "") or ""), usage_dict, model_version


def parse_vetting_json(text: str) -> dict[str, Any]:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = parse_first_json_object(cleaned)
    if not isinstance(data, dict):
        raise ValueError("AI vetter did not return a JSON object")
    return data


def parse_first_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            data, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise ValueError("AI vetter response did not contain a JSON object")


def normalize_vetting_record(
    source_record: dict[str, Any],
    raw: dict[str, Any],
    request_meta: dict[str, Any],
) -> dict[str, Any]:
    candidate_urls = set(source_record.get("evidence_urls") or [])
    for item in source_record.get("follow_up_evidence") or []:
        if item.get("url"):
            candidate_urls.add(str(item["url"]))
        if item.get("final_url"):
            candidate_urls.add(str(item["final_url"]))
    ai_claim_url_fields = {
        "evidence_used": raw.get("evidence_used"),
        "opportunity_signal": raw.get("opportunity_signal"),
        "why_this_matters_to_1bt": raw.get("why_this_matters_to_1bt"),
        "commercial_opening": raw.get("commercial_opening"),
        "value_of_signal": raw.get("value_of_signal"),
        "intelligence_reading": raw.get("intelligence_reading"),
        "board_relevance": raw.get("board_relevance"),
    }
    invented_urls = sorted(set(extract_urls(ai_claim_url_fields)) - candidate_urls)

    status = str(raw.get("lead_status") or "").strip().lower()
    strength = str(raw.get("signal_strength") or "").strip().lower()
    source_channel = discovery_backbone_tools.classify_source_channel(
        source=source_record.get("source_provider"),
        url=next(iter(candidate_urls), None),
        explicit=source_record.get("source_channel"),
    )
    if status not in VALID_LEAD_STATUSES:
        status = "reject"
    if strength not in VALID_SIGNAL_STRENGTHS:
        strength = "weak"

    hard_reason = source_record.get("hard_rejection_reason")
    if hard_reason:
        status = "reject"
        raw["final_rejection_reason"] = hard_reason

    evidence_used = normalize_list(raw.get("evidence_used"))
    if invented_urls:
        evidence_used = [
            item for item in evidence_used
            if not any(url in str(item) for url in invented_urls)
        ]
        if status != "reject":
            status = "source_cleanup_needed"
    if status != "reject" and not evidence_used:
        evidence_used = safe_evidence_used_from_source(source_record)

    evidence_gaps = normalize_list(raw.get("evidence_gaps"))
    do_not_claim_notes = normalize_list(raw.get("do_not_claim_notes"))
    remaining_uncertainty = normalize_list(raw.get("remaining_uncertainty"))
    identity_override = identity_from_follow_up_evidence(source_record)
    identity_resolution_required = bool(source_record.get("identity_resolution_required")) and not identity_override
    if identity_resolution_required and status != "reject":
        status = "source_cleanup_needed"
        evidence_gaps.append("End-customer identity still needs resolution before final publication.")
    if status != "reject":
        if not discovery_backbone_tools.final_pdf_eligible_from_channel(source_channel):
            status = "source_cleanup_needed"
            evidence_gaps.append(
                "Candidate came from a hint channel and needs public-web evidence before final publication."
            )
        missing_writeup_fields = missing_non_reject_writeup_fields(raw, evidence_used)
        if missing_writeup_fields:
            status = "source_cleanup_needed"
            evidence_gaps.append(
                "AI vetter returned blank required write-up fields: "
                + ", ".join(missing_writeup_fields)
            )
        for note in DEFAULT_DO_NOT_CLAIM_NOTES:
            if note not in do_not_claim_notes:
                do_not_claim_notes.append(note)
        if not remaining_uncertainty:
            remaining_uncertainty.append("AI vetter did not supply specific remaining uncertainty.")

    normalized = {
        "candidate_id": source_record.get("candidate_id"),
        "candidate_index": source_record.get("candidate_index"),
        "company_name": identity_override or source_record.get("company_name"),
        "source_company": source_record.get("source_company"),
        "source_role": source_record.get("source_role"),
        "source_provider": source_record.get("source_provider"),
        "source_channel": source_channel,
        "original_url": source_record.get("original_url"),
        "final_url": source_record.get("final_url"),
        "source_fetch_status": source_record.get("source_fetch_status"),
        "source_fetch": source_record.get("source_fetch") or {},
        "verified_live": bool(source_record.get("verified_live")),
        "final_pdf_eligible": discovery_backbone_tools.final_pdf_eligible_from_channel(source_channel),
        "account_identity_status": "resolved_end_customer" if identity_override else source_record.get("account_identity_status"),
        "end_customer_candidates": list(dict.fromkeys([*(source_record.get("end_customer_candidates") or []), *([identity_override] if identity_override else [])])),
        "identity_resolution_required": identity_resolution_required,
        "identity_evidence_excerpt": identity_override or source_record.get("identity_evidence_excerpt"),
        "identity_confidence": "high" if identity_override else source_record.get("identity_confidence"),
        "identity_notes": [*(source_record.get("identity_notes") or []), *(["End-customer identity resolved from follow-up evidence."] if identity_override else [])],
        "lead_status": status,
        "signal_strength": strength,
        "signal_type": clean_text(raw.get("signal_type") or source_record.get("signal_type")),
        "evidence_used": evidence_used,
        "evidence_gaps": evidence_gaps,
        "opportunity_signal": clean_text(raw.get("opportunity_signal")),
        "why_this_matters_to_1bt": clean_text(raw.get("why_this_matters_to_1bt")),
        "commercial_opening": clean_text(raw.get("commercial_opening")),
        "value_of_signal": clean_text(raw.get("value_of_signal")),
        "intelligence_reading": clean_text(raw.get("intelligence_reading")),
        "board_relevance": clean_text(raw.get("board_relevance")),
        "contact_target_roles": normalize_list(raw.get("contact_target_roles")),
        "do_not_claim_notes": do_not_claim_notes,
        "remaining_uncertainty": remaining_uncertainty,
        "final_rejection_reason": clean_text(raw.get("final_rejection_reason")),
        "needs_follow_up": bool(raw.get("needs_follow_up")),
        "follow_up_queries": normalize_list(raw.get("follow_up_queries")),
        "deterministic_flags": source_record.get("deterministic_flags") or [],
        "missing_verification_points": source_record.get("missing_verification_points") or [],
        "retention_status": source_record.get("retention_status"),
        "run_id": source_record.get("run_id"),
        "company_fingerprint": source_record.get("company_fingerprint"),
        "opportunity_fingerprint": source_record.get("opportunity_fingerprint"),
        "source_fingerprint": source_record.get("source_fingerprint"),
        "follow_up_evidence": source_record.get("follow_up_evidence") or [],
        "invented_candidate_facts_detected": bool(invented_urls),
        "invented_fact_findings": [{"type": "url", "value": url} for url in invented_urls],
        "request_metadata": request_meta,
    }
    for field in REQUIRED_VETTING_FIELDS:
        normalized.setdefault(field, [] if field.endswith("s") or field in {"evidence_used", "evidence_gaps", "contact_target_roles", "do_not_claim_notes", "remaining_uncertainty"} else "")
    return normalized


def missing_non_reject_writeup_fields(raw: dict[str, Any], evidence_used: list[str]) -> list[str]:
    missing = []
    for field in NON_REJECT_REQUIRED_WRITEUP_FIELDS:
        value = evidence_used if field == "evidence_used" else raw.get(field)
        if not has_meaningful_value(value):
            missing.append(field)
    return missing


def safe_evidence_used_from_source(source_record: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    evidence.extend(str(url) for url in source_record.get("evidence_urls") or [] if url)
    evidence.extend(str(item) for item in source_record.get("evidence_snippets") or [] if item)
    for item in source_record.get("follow_up_evidence") or []:
        for key in ("final_url", "url", "text_excerpt", "snippet"):
            value = item.get(key)
            if value:
                evidence.append(str(value))
    return list(dict.fromkeys(evidence))


def identity_from_follow_up_evidence(source_record: dict[str, Any]) -> str:
    for item in source_record.get("follow_up_evidence") or []:
        text = "\n".join(
            str(item.get(key) or "")
            for key in ("title", "snippet", "text_excerpt", "text")
        )
        extracted = lead_tools.extract_named_target_company(text)
        if extracted:
            return extracted
    return ""


def has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(has_meaningful_value(item) for item in value)
    if isinstance(value, dict):
        return any(has_meaningful_value(item) for item in value.values())
    return True


def should_run_follow_up(record: dict[str, Any]) -> bool:
    if record.get("lead_status") == "reject":
        return False
    if record.get("identity_resolution_required") or record.get("account_identity_status") in {"ambiguous", "generic_title"}:
        return True
    if record.get("needs_follow_up"):
        return True
    return record.get("lead_status") == "source_cleanup_needed" or bool(record.get("evidence_gaps"))


def build_follow_up_queries(candidate_record: dict[str, Any], review_record: dict[str, Any], max_queries: int = 2) -> list[str]:
    explicit = [str(item) for item in review_record.get("follow_up_queries") or [] if item]
    if explicit:
        return explicit[:max_queries]
    company = str(candidate_record.get("company_name") or "").strip()
    if not company:
        company = "Dynamics 365 UK Ireland"
    candidates = [company]
    candidates.extend(str(item) for item in candidate_record.get("end_customer_candidates") or [] if item)
    if candidate_record.get("source_company"):
        candidates.append(str(candidate_record["source_company"]))
    search_name = next((item for item in candidates if item and not generic_or_job_board_company_name(item)), company)
    return [
        f'"{search_name}" "Dynamics 365" ("case study" OR implementation OR support)',
        f'"{search_name}" ("Business Central" OR "Power Platform" OR Dataverse OR "Dynamics CRM")',
    ][:max_queries]


def collect_follow_up_evidence(
    candidate_record: dict[str, Any],
    review_record: dict[str, Any],
    *,
    followup_search_call: Any | None = None,
    source_fetch_call: Any | None = None,
    max_searches: int = 2,
    max_source_fetches: int = 3,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    if followup_search_call:
        for query in build_follow_up_queries(candidate_record, review_record, max_searches):
            try:
                follow_up_items = followup_search_call(query, candidate_record, review_record) or []
            except Exception as exc:
                evidence.append(
                    {
                        "kind": "search_error",
                        "query": query,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:500],
                    }
                )
                continue
            for item in follow_up_items:
                evidence.append(normalize_followup_item(item, query=query, kind="search_result"))
    if source_fetch_call:
        urls = list(candidate_record.get("evidence_urls") or [])
        urls.extend(item.get("url") for item in evidence if item.get("url"))
        for url in list(dict.fromkeys(str(item) for item in urls if item))[:max_source_fetches]:
            fetched = source_fetch_call(url, candidate_record, review_record)
            if fetched:
                evidence.append(normalize_followup_item(fetched, query=None, kind="source_fetch"))
    return evidence[: max_searches + max_source_fetches]


def build_vetting_package(
    *,
    evidence_file: Path | str,
    output_dir: Path | str = EVIDENCE_DIR,
    output_basename: str = DEFAULT_OUTPUT_BASENAME,
    max_candidates: int = 40,
    max_followup_searches: int = 2,
    max_source_fetches: int = 3,
    model: str | None = None,
    reviewer_call: Any | None = None,
    followup_search_call: Any | None = None,
    source_fetch_call: Any | None = None,
    client_factory: Any | None = None,
    command_log: list[str] | None = None,
) -> dict[str, Any]:
    data = load_saved_evidence(evidence_file)
    candidates = select_vetting_candidates(all_reviewable_candidates(data), max_candidates)
    output_dir = Path(output_dir)
    client = None
    if reviewer_call is None:
        client_factory = client_factory or make_vertex_vetter_client
        client, client_info = client_factory(model)
    else:
        client_info = {
            "model": vetter_model_name(model),
            "provider_path": "injected reviewer_call",
            "project": "unit-test",
            "location": "local",
            "auth_mode": "test",
        }

    started_at = now_utc()
    records = []
    requests = []
    follow_up_records = []
    for index, candidate in enumerate(candidates, start=1):
        initial_record = prepare_vetting_record(candidate, index=index, stage="initial")
        initial_review, request_meta = run_vetter_request(
            initial_record,
            stage="initial",
            request_index=len(requests) + 1,
            client=client,
            client_info=client_info,
            reviewer_call=reviewer_call,
        )
        requests.append(request_meta)
        final_review = initial_review
        follow_up_evidence: list[dict[str, Any]] = []
        if should_run_follow_up(initial_review):
            follow_up_evidence = collect_follow_up_evidence(
                initial_record,
                initial_review,
                followup_search_call=followup_search_call,
                source_fetch_call=source_fetch_call,
                max_searches=max_followup_searches,
                max_source_fetches=max_source_fetches,
            )
            follow_up_records.append(
                {
                    "candidate_id": initial_record["candidate_id"],
                    "company_name": initial_record.get("company_name"),
                    "evidence_count": len(follow_up_evidence),
                    "max_followup_searches": max_followup_searches,
                    "max_source_fetches": max_source_fetches,
                }
            )
            if follow_up_evidence:
                final_record = prepare_vetting_record(
                    candidate,
                    index=index,
                    follow_up_evidence=follow_up_evidence,
                    stage="final",
                )
                final_review, request_meta = run_vetter_request(
                    final_record,
                    stage="final",
                    request_index=len(requests) + 1,
                    client=client,
                    client_info=client_info,
                    reviewer_call=reviewer_call,
                )
                requests.append(request_meta)
        records.append(
            {
                "candidate": initial_record,
                "initial_review": initial_review,
                "final_review": final_review,
                "follow_up_evidence": follow_up_evidence,
            }
        )
    finished_at = now_utc()
    counts = vetting_counts(records, requests)
    final_reviews = [item["final_review"] for item in records]
    useful_statuses = {"ready_to_contact", "provisional_contact_now", "source_cleanup_needed"}
    useful_leads = [item for item in final_reviews if item.get("lead_status") in useful_statuses]
    rejected_reviews = [item for item in final_reviews if item.get("lead_status") == "reject"]
    output = {
        "metadata": {
            "artifact_type": "uk_ie_d365_ai_opportunity_vetting",
            "started_at": started_at,
            "finished_at": finished_at,
            "input_evidence_file": str(evidence_file),
            "model": client_info["model"],
            "provider_path": client_info["provider_path"],
            "project": client_info["project"],
            "location": client_info["location"],
            "auth_mode": client_info["auth_mode"],
            "max_candidates": max_candidates,
            "max_followup_searches_per_candidate": max_followup_searches,
            "max_source_fetches_per_candidate": max_source_fetches,
            "hard_rejected_input_count": len(data.get("hard_rejected_leads") or []),
            "command_log": command_log or [],
        },
        "required_output_fields": REQUIRED_VETTING_FIELDS,
        "counts": counts,
        "useful_leads": useful_leads,
        "rejected_reviews": rejected_reviews,
        "reject_review_summary": {
            "rejected_count": len(rejected_reviews),
            "final_rejection_reasons": dict(Counter(item.get("final_rejection_reason") or "unspecified" for item in rejected_reviews)),
        },
        "llm_request_records": requests,
        "follow_up_records": follow_up_records,
        "records": records,
        "notes": [
            "Deterministic rules act as guardrails only; AI vetting owns opportunity judgement.",
            "Follow-up evidence is runner-supplied. The vetter agent has no browsing, email, deployment, or rule-mutation tools.",
        ],
    }
    artifacts = write_vetting_artifacts(output, output_dir=output_dir, output_basename=output_basename)
    return {"vetting_output": output, "artifacts": artifacts}


def run_vetter_request(
    record: dict[str, Any],
    *,
    stage: str,
    request_index: int,
    client: Any | None,
    client_info: dict[str, Any],
    reviewer_call: Any | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    prompt = build_vetting_prompt(record)
    request_meta = {
        "request_index": request_index,
        "candidate_id": record.get("candidate_id"),
        "stage": stage,
    }
    max_attempts = 2 if reviewer_call is None else 1
    for attempt in range(1, max_attempts + 1):
        try:
            if reviewer_call is None:
                response_text, usage, model_version = call_vertex_vetter(
                    client=client,
                    model=client_info["model"],
                    prompt=prompt,
                )
            else:
                response_text, usage, model_version = reviewer_call(record, stage, request_index)
            raw = parse_vetting_json(response_text)
            request_meta.update(
                {
                    "usage_metadata": usage,
                    "model_version": model_version,
                    "attempt_count": attempt,
                }
            )
            break
        except Exception as exc:
            if reviewer_call is None and attempt < max_attempts and retryable_vetter_error(exc):
                request_meta["retry_after_error_type"] = type(exc).__name__
                request_meta["retry_after_error"] = str(exc)[:500]
                time.sleep(15)
                continue
            raw = fallback_vetter_record(record, exc)
            request_meta.update(
                {
                    "usage_metadata": {},
                    "model_version": None,
                    "request_error_type": type(exc).__name__,
                    "request_error": str(exc)[:500],
                    "attempt_count": attempt,
                }
            )
            break
    return normalize_vetting_record(record, raw, request_meta), request_meta


def retryable_vetter_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "temporarily unavailable" in text


def fallback_vetter_record(record: dict[str, Any], exc: Exception) -> dict[str, Any]:
    evidence_used = []
    evidence_used.extend(record.get("evidence_urls") or [])
    evidence_used.extend(record.get("evidence_snippets") or [])
    return {
        "lead_status": "source_cleanup_needed",
        "signal_strength": "weak",
        "signal_type": record.get("signal_type") or "unresolved_ai_vetting",
        "evidence_used": evidence_used,
        "evidence_gaps": [f"AI vetter request failed: {type(exc).__name__}: {str(exc)[:300]}"],
        "opportunity_signal": record.get("signal_summary") or "Candidate could not be fully AI-vetted.",
        "why_this_matters_to_1bt": "AI vetting did not complete, so this candidate must not be promoted without review.",
        "commercial_opening": "Do not use for outreach until AI vetting or manual review is completed.",
        "value_of_signal": "Unresolved.",
        "intelligence_reading": "AI request failed; saved evidence only.",
        "board_relevance": "Not board-ready until reviewed.",
        "contact_target_roles": record.get("suggested_contact_roles") or [],
        "do_not_claim_notes": ["Do not claim this is a qualified opportunity."],
        "remaining_uncertainty": ["AI vetting request failed."],
        "final_rejection_reason": "",
        "needs_follow_up": False,
    }


def vetting_counts(records: list[dict[str, Any]], requests: list[dict[str, Any]]) -> dict[str, Any]:
    final_reviews = [item["final_review"] for item in records]
    token_usage = Counter()
    for request in requests:
        for key, value in (request.get("usage_metadata") or {}).items():
            if isinstance(value, int | float):
                token_usage[key] += value
    return {
        "candidates_loaded_for_vetting": len(records),
        "ai_request_count": len(requests),
        "lead_status_counts": dict(Counter(item.get("lead_status") for item in final_reviews)),
        "signal_strength_counts": dict(Counter(item.get("signal_strength") for item in final_reviews)),
        "follow_up_candidate_count": sum(1 for item in records if item.get("follow_up_evidence")),
        "invented_candidate_facts_count": sum(1 for item in final_reviews if item.get("invented_candidate_facts_detected")),
        "token_usage": dict(token_usage),
    }


def write_vetting_artifacts(
    output: dict[str, Any],
    *,
    output_dir: Path,
    output_basename: str = DEFAULT_OUTPUT_BASENAME,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{output_basename}.json"
    md_path = output_dir / f"{output_basename}.md"
    report_path = output_dir / f"{output_basename}_REPORT.md"
    secret_path = output_dir / f"{output_basename}_SECRET_SCAN.json"
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_vetting_markdown(output), encoding="utf-8")
    report_path.write_text(render_vetting_report(output), encoding="utf-8")
    secret_scan = scan_secret_patterns([json_path, md_path, report_path])
    secret_path.write_text(json.dumps(secret_scan, indent=2), encoding="utf-8")
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "report": str(report_path),
        "secret_scan": str(secret_path),
    }


def render_vetting_markdown(output: dict[str, Any]) -> str:
    lines = [
        "# UK/IE D365 AI Opportunity Vetting",
        "",
        f"- Candidates vetted: {output['counts']['candidates_loaded_for_vetting']}",
        f"- Useful/non-rejected leads: {len(output.get('useful_leads') or [])}",
        f"- AI requests: {output['counts']['ai_request_count']}",
        f"- Status counts: {json.dumps(output['counts']['lead_status_counts'], sort_keys=True)}",
        "",
    ]
    for item in output["records"]:
        review = item["final_review"]
        lines.extend(
            [
                f"## {review.get('company_name') or 'Unnamed candidate'}",
                "",
                f"- Status: {review.get('lead_status')}",
                f"- Strength: {review.get('signal_strength')}",
                f"- Signal: {review.get('opportunity_signal')}",
                f"- Commercial opening: {review.get('commercial_opening')}",
                f"- Uncertainty: {'; '.join(review.get('remaining_uncertainty') or [])}",
                "",
            ]
        )
    return "\n".join(lines)


def render_vetting_report(output: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# UK/IE D365 AI Vetting Report",
            "",
            f"- Input evidence: `{output['metadata']['input_evidence_file']}`",
            f"- Model/provider: `{output['metadata']['model']}` / `{output['metadata']['provider_path']}`",
            f"- AI requests: {output['counts']['ai_request_count']}",
            f"- Useful/non-rejected leads: {len(output.get('useful_leads') or [])}",
            f"- AI rejected reviews: {len(output.get('rejected_reviews') or [])}",
            f"- Follow-up candidates: {output['counts']['follow_up_candidate_count']}",
            f"- Invented fact findings: {output['counts']['invented_candidate_facts_count']}",
            "",
            "Deterministic hard rejects stay excluded. All non-hard candidates are eligible for AI vetting.",
            "",
        ]
    )


def build_fresh_leads_outputs(
    *,
    vetting_output: dict[str, Any],
    raw_search: dict[str, Any],
    output_dir: Path | str = EVIDENCE_DIR,
    final_count: int = 12,
    output_basename: str = FRESH_LEADS_BASENAME,
    deterministic_audit_basename: str = DETERMINISTIC_AUDIT_BASENAME,
    command_log: list[str] | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    duplicate_blocklist = build_prior_account_blocklist(output_dir)
    duplicate_opportunity_fingerprints = build_prior_opportunity_fingerprint_set(output_dir)
    deterministic_audit = audit_hard_rejections(raw_search)
    audit_json_path = output_dir / f"{deterministic_audit_basename}.json"
    audit_md_path = output_dir / f"{deterministic_audit_basename}.md"
    audit_json_path.write_text(json.dumps(deterministic_audit, indent=2, ensure_ascii=False), encoding="utf-8")
    audit_md_path.write_text(render_deterministic_audit_markdown(deterministic_audit), encoding="utf-8")
    if not deterministic_audit["passed"]:
        raise RuntimeError(
            "Suspicious deterministic hard rejects found. Review "
            f"{audit_json_path} before final curation."
        )

    selected, excluded = select_final_fresh_leads(
        vetting_output,
        duplicate_blocklist=duplicate_blocklist,
        duplicate_opportunity_fingerprints=duplicate_opportunity_fingerprints,
        final_count=final_count,
    )
    queues = build_retention_queues(
        vetting_output=vetting_output,
        selected=selected,
        excluded=excluded,
        raw_search=raw_search,
    )
    metadata = {
        "artifact_type": "uk_ie_d365_useful_leads_fresh",
        "generated_at": now_utc(),
        "total_useful_leads_found": len(selected),
        "target_useful_leads": final_count,
        "lead_conservation_version": lead_tools.LEAD_CONSERVATION_VERSION,
        "discovery_backbone_version": discovery_backbone_tools.DISCOVERY_BACKBONE_VERSION,
        "source_channel_policy": raw_search.get("source_channel_policy")
        or discovery_backbone_tools.source_channel_policy(),
        "cloud_discovery_preflight": raw_search.get("cloud_discovery_preflight"),
        "source_vetting_artifact_type": vetting_output.get("metadata", {}).get("artifact_type"),
        "model": vetting_output.get("metadata", {}).get("model"),
        "provider_path": vetting_output.get("metadata", {}).get("provider_path"),
        "project": vetting_output.get("metadata", {}).get("project"),
        "location": vetting_output.get("metadata", {}).get("location"),
        "raw_search_finished_at": raw_search.get("run_finished_at") or raw_search.get("fetched_at"),
        "deterministic_reject_audit_passed": deterministic_audit["passed"],
        "retained_candidate_count": len(queues["candidate_ledger"]),
        "source_cleanup_queue_count": len(queues["source_cleanup_queue"]),
        "identity_resolution_queue_count": len(queues["identity_resolution_queue"]),
        "duplicate_queue_count": len(queues["duplicate_queue"]),
        "hard_reject_queue_count": len(queues["hard_reject_queue"]),
        "command_log": command_log or [],
    }
    final_output = {
        "metadata": metadata,
        "lead_conservation": {
            "policy": "Every non-hard candidate is retained as final-ready, cleanup, identity-resolution, duplicate review, or shortage context.",
            "statuses": sorted(lead_tools.RETENTION_STATUSES),
        },
        "duplicate_policy": {
            "excluded_prior_or_parked_accounts": sorted(duplicate_blocklist),
            "excluded_count": len(duplicate_blocklist),
            "duplicate_opportunity_fingerprint_count": len(duplicate_opportunity_fingerprints),
            "same_company_new_opportunity_rule": "Block same opportunity; same company can pass when a distinct prior opportunity fingerprint does not match and evidence is final-ready.",
        },
        "selection_exclusions": excluded,
        "retention_queues": {
            "source_cleanup_queue": queues["source_cleanup_queue"],
            "identity_resolution_queue": queues["identity_resolution_queue"],
            "duplicate_queue": queues["duplicate_queue"],
            "hard_reject_queue": queues["hard_reject_queue"],
            "retained_good_candidates": queues["retained_good_candidates"],
        },
        "leads": selected,
    }
    if len(selected) != final_count:
        final_output["metadata"]["completion_status"] = "insufficient_quality_new_leads"
    else:
        final_output["metadata"]["completion_status"] = "complete"

    json_path = output_dir / f"{output_basename}.json"
    md_path = output_dir / f"{output_basename}.md"
    report_path = output_dir / f"{output_basename}_REPORT.md"
    secret_path = output_dir / f"{output_basename}_SECRET_SCAN.json"
    ledger_path = output_dir / f"{output_basename}_CANDIDATE_LEDGER.json"
    cleanup_path = output_dir / f"{output_basename}_SOURCE_CLEANUP_QUEUE.json"
    identity_path = output_dir / f"{output_basename}_IDENTITY_RESOLUTION.json"
    duplicate_path = output_dir / f"{output_basename}_DUPLICATE_AUDIT.json"
    shortage_json_path = output_dir / f"{output_basename}_SHORTAGE_REPORT.json"
    shortage_md_path = output_dir / f"{output_basename}_SHORTAGE_REPORT.md"
    json_path.write_text(json.dumps(final_output, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_fresh_leads_markdown(final_output), encoding="utf-8")
    report_path.write_text(render_fresh_leads_report(final_output, deterministic_audit, vetting_output), encoding="utf-8")
    ledger_path.write_text(json.dumps(queues["candidate_ledger"], indent=2, ensure_ascii=False), encoding="utf-8")
    cleanup_path.write_text(json.dumps(queues["source_cleanup_queue"], indent=2, ensure_ascii=False), encoding="utf-8")
    identity_path.write_text(json.dumps(queues["identity_resolution_queue"], indent=2, ensure_ascii=False), encoding="utf-8")
    duplicate_audit = {
        "artifact_type": "uk_ie_d365_duplicate_audit",
        "generated_at": now_utc(),
        "prior_account_count": len(duplicate_blocklist),
        "prior_opportunity_fingerprint_count": len(duplicate_opportunity_fingerprints),
        "duplicate_queue": queues["duplicate_queue"],
        "selection_exclusions": [item for item in excluded if "duplicate" in item.get("reason", "") or item.get("reason") == "prior_or_parked_account_duplicate"],
    }
    duplicate_path.write_text(json.dumps(duplicate_audit, indent=2, ensure_ascii=False), encoding="utf-8")
    shortage_report = build_shortage_report(final_output, queues, final_count)
    shortage_json_path.write_text(json.dumps(shortage_report, indent=2, ensure_ascii=False), encoding="utf-8")
    shortage_md_path.write_text(render_shortage_report_markdown(shortage_report), encoding="utf-8")
    secret_scan = scan_secret_patterns([
        json_path,
        md_path,
        report_path,
        audit_json_path,
        audit_md_path,
        ledger_path,
        cleanup_path,
        identity_path,
        duplicate_path,
        shortage_json_path,
        shortage_md_path,
    ])
    secret_path.write_text(json.dumps(secret_scan, indent=2), encoding="utf-8")
    if not secret_scan["passed"]:
        raise RuntimeError(f"Secret scan failed: {secret_path}")
    return {
        "final_output": final_output,
        "deterministic_audit": deterministic_audit,
        "retention_queues": queues,
        "shortage_report": shortage_report,
        "artifacts": {
            "json": str(json_path),
            "markdown": str(md_path),
            "report": str(report_path),
            "candidate_ledger": str(ledger_path),
            "source_cleanup_queue": str(cleanup_path),
            "identity_resolution": str(identity_path),
            "duplicate_audit": str(duplicate_path),
            "shortage_report_json": str(shortage_json_path),
            "shortage_report_markdown": str(shortage_md_path),
            "deterministic_audit_json": str(audit_json_path),
            "deterministic_audit_markdown": str(audit_md_path),
            "secret_scan": str(secret_path),
        },
    }


def build_prior_account_blocklist(evidence_dir: Path | str = EVIDENCE_DIR) -> set[str]:
    evidence_dir = Path(evidence_dir)
    names = set(ADDITIONAL_PRIOR_OR_PARKED_ACCOUNTS)
    for artifact_name in PRIOR_ACCOUNT_ARTIFACTS:
        path = evidence_dir / artifact_name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        names.update(extract_account_names(data))
    return {normalize_company_for_match(name) for name in names if normalize_company_for_match(name)}


def build_prior_opportunity_fingerprint_set(evidence_dir: Path | str = EVIDENCE_DIR) -> set[str]:
    evidence_dir = Path(evidence_dir)
    fingerprints: set[str] = set()
    for artifact_name in PRIOR_ACCOUNT_ARTIFACTS:
        path = evidence_dir / artifact_name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        fingerprints.update(extract_opportunity_fingerprints(data))
    return fingerprints


def extract_opportunity_fingerprints(value: Any) -> set[str]:
    fingerprints: set[str] = set()
    if isinstance(value, dict):
        if value.get("opportunity_fingerprint"):
            fingerprints.add(str(value["opportunity_fingerprint"]))
        company = value.get("company_name") or value.get("company") or value.get("account") or value.get("account_name")
        url = value.get("evidence_url") or value.get("source_url") or first_url(value.get("evidence_urls") or [])
        signal = value.get("signal_type") or value.get("trigger_type") or value.get("signal")
        product = value.get("dynamics_product") or value.get("product")
        summary = value.get("opportunity_signal") or value.get("signal_summary") or value.get("evidence_excerpt")
        if company and url:
            fingerprints.add(lead_tools.stable_fingerprint("opp", company, product, signal, url, summary))
        for item in value.values():
            fingerprints.update(extract_opportunity_fingerprints(item))
    elif isinstance(value, list):
        for item in value:
            fingerprints.update(extract_opportunity_fingerprints(item))
    return fingerprints


def extract_account_names(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"company_name", "company", "account", "account_name", "name"} and isinstance(item, str):
                if 1 < len(item) < 120:
                    names.add(item)
            names.update(extract_account_names(item))
    elif isinstance(value, list):
        for item in value:
            names.update(extract_account_names(item))
    return names


def normalize_company_for_match(name: Any) -> str:
    text = str(name or "").lower()
    text = re.sub(r"&", " and ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[/|]", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\b(limited|ltd|plc|group|company|co operative|co|uk|ireland)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_prior_or_parked_account(company_name: str, blocklist: set[str]) -> bool:
    normalized = normalize_company_for_match(company_name)
    if not normalized:
        return True
    if normalized in blocklist:
        return True
    return any(len(item) >= 5 and (normalized in item or item in normalized) for item in blocklist)


def audit_hard_rejections(raw_search: dict[str, Any]) -> dict[str, Any]:
    hard_rejected = list(raw_search.get("hard_rejected_leads") or [])
    suspicious = []
    reason_counts = Counter()
    for lead in hard_rejected:
        reason = lead.get("hard_rejection_reason") or lead.get("rejection_reason") or "unknown"
        reason_counts[reason] += 1
        text = candidate_text_for_audit(lead)
        url = first_url(lead.get("evidence_urls") or [lead.get("evidence_url")])
        d365_signal = lead_tools.has_dynamics_evidence(f"{text}\n{url or ''}")
        market_signal = bool(lead.get("country") or lead_tools.infer_country(text, url or ""))
        suspicious_reason = None
        if reason not in lead_tools.HARD_REJECTION_REASONS:
            suspicious_reason = "hard rejection reason is not in the approved guardrail set"
        elif reason == "missing_explicit_dynamics_365_or_business_app_evidence" and d365_signal:
            suspicious_reason = "candidate appears to contain Microsoft business-app evidence"
        elif reason == "generic_it_support_without_dynamics_365_evidence" and d365_signal:
            suspicious_reason = "candidate appears generic but also contains D365 evidence"
        elif reason == "uk_ireland_not_evidenced" and market_signal:
            suspicious_reason = "candidate appears to contain UK/Ireland evidence"
        elif (
            d365_signal
            and market_signal
            and reason
            not in {
                "private_or_linkedin_source_excluded",
                "tender_or_procurement_out_of_scope",
                "fake_or_example_url",
                "missing_evidence_url",
            }
        ):
            suspicious_reason = "candidate has both D365 and UK/Ireland signals despite hard rejection"
        if suspicious_reason:
            suspicious.append(
                {
                    "company_name": lead.get("company_name"),
                    "reason": reason,
                    "suspicious_reason": suspicious_reason,
                    "evidence_urls": lead.get("evidence_urls") or [],
                    "evidence_snippets": lead.get("evidence_snippets") or [],
                    "deterministic_flags": lead.get("deterministic_flags") or [],
                }
            )
    return {
        "artifact_type": "uk_ie_d365_deterministic_reject_audit",
        "generated_at": now_utc(),
        "passed": not suspicious,
        "success_statement": (
            "No good lead was deterministically rejected based on the evidence available to the pipeline."
            if not suspicious
            else "Manual review required before claiming deterministic rejection safety."
        ),
        "hard_rejected_count": len(hard_rejected),
        "rejection_reason_counts": dict(reason_counts),
        "suspicious_hard_reject_count": len(suspicious),
        "suspicious_hard_rejects": suspicious,
        "approved_hard_rejection_reasons": sorted(lead_tools.HARD_REJECTION_REASONS),
    }


def select_final_fresh_leads(
    vetting_output: dict[str, Any],
    *,
    duplicate_blocklist: set[str],
    duplicate_opportunity_fingerprints: set[str] | None = None,
    final_count: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    duplicate_opportunity_fingerprints = duplicate_opportunity_fingerprints or set()
    candidates = []
    excluded = []
    for record in vetting_output.get("records") or []:
        review = record.get("final_review") or {}
        candidate = record.get("candidate") or {}
        company = str(review.get("company_name") or candidate.get("company_name") or "").strip()
        follow_up = record.get("follow_up_evidence") or review.get("follow_up_evidence") or []
        exclusion = exclusion_reason_for_review(
            review,
            candidate,
            company,
            duplicate_blocklist,
            follow_up,
            duplicate_opportunity_fingerprints=duplicate_opportunity_fingerprints,
        )
        if exclusion:
            excluded.append(selection_exclusion_row(record, company, exclusion))
            continue
        candidates.append((fresh_lead_score(review), record))
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = []
    seen_names: set[str] = set()
    for _, record in candidates:
        lead = final_lead_from_vetting_record(record, rank=len(selected) + 1, metadata=vetting_output.get("metadata") or {})
        normalized = normalize_company_for_match(lead["company_name"])
        if normalized in seen_names:
            excluded.append(selection_exclusion_row(record, lead["company_name"], "duplicate_within_fresh_selection"))
            continue
        seen_names.add(normalized)
        if len(selected) >= final_count:
            excluded.append(selection_exclusion_row(record, lead["company_name"], "retained_good_candidate_over_final_count"))
            continue
        selected.append(lead)
    return selected, excluded


def exclusion_reason_for_review(
    review: dict[str, Any],
    candidate: dict[str, Any],
    company: str,
    duplicate_blocklist: set[str],
    follow_up: list[dict[str, Any]] | None = None,
    *,
    duplicate_opportunity_fingerprints: set[str] | None = None,
) -> str | None:
    follow_up = follow_up or []
    duplicate_opportunity_fingerprints = duplicate_opportunity_fingerprints or set()
    status = review.get("lead_status")
    strength = review.get("signal_strength")
    if status == "reject":
        return "ai_rejected"
    if status not in {"ready_to_contact", "provisional_contact_now", "source_cleanup_needed"}:
        return "not_useful_status"
    if status == "source_cleanup_needed" and strength != "strong":
        return "source_cleanup_not_strong_enough"
    if review.get("invented_candidate_facts_detected"):
        return "invented_candidate_facts_detected"
    source_channel = review.get("source_channel") or candidate.get("source_channel") or "public_web"
    if not discovery_backbone_tools.final_pdf_eligible_from_channel(source_channel):
        return "hint_channel_requires_public_web_evidence"
    if generic_or_job_board_company_name(company):
        return "generic_or_job_board_account_name"
    if vendor_only_without_target_customer(review, candidate):
        return "vendor_only_without_target_customer"
    if is_prior_or_parked_account(company, duplicate_blocklist):
        fingerprint = review.get("opportunity_fingerprint") or candidate.get("opportunity_fingerprint") or current_opportunity_fingerprint(review, candidate, follow_up)
        if fingerprint in duplicate_opportunity_fingerprints:
            return "duplicate_same_opportunity"
        if review.get("same_company_new_opportunity_evidenced") or candidate.get("same_company_new_opportunity_evidenced"):
            return None
        return "prior_or_parked_account_duplicate"
    url = best_evidence_url(review, candidate, follow_up)
    if not url:
        return "missing_public_evidence_url"
    if any(term in url.lower() for term in FORBIDDEN_FINAL_URL_TERMS):
        return "forbidden_source_url"
    if not has_verified_public_evidence(review, candidate, follow_up):
        return "missing_verified_live_public_evidence"
    return None


def selection_exclusion_row(record: dict[str, Any], company: str, reason: str) -> dict[str, Any]:
    review = record.get("final_review") or {}
    candidate = record.get("candidate") or {}
    follow_up = record.get("follow_up_evidence") or review.get("follow_up_evidence") or []
    return {
        "company_name": company,
        "reason": reason,
        "candidate_id": review.get("candidate_id") or candidate.get("candidate_id"),
        "run_id": review.get("run_id") or candidate.get("run_id"),
        "retention_status": retention_status_from_selection_reason(reason, review, candidate),
        "source_channel": review.get("source_channel") or candidate.get("source_channel") or "public_web",
        "final_pdf_eligible": bool(
            review.get("final_pdf_eligible")
            if "final_pdf_eligible" in review
            else candidate.get("final_pdf_eligible", True)
        ),
        "verified_live": has_verified_public_evidence(review, candidate, follow_up),
        "source_fetch_status": review.get("source_fetch_status") or candidate.get("source_fetch_status"),
        "company_fingerprint": review.get("company_fingerprint") or candidate.get("company_fingerprint"),
        "opportunity_fingerprint": review.get("opportunity_fingerprint") or candidate.get("opportunity_fingerprint") or current_opportunity_fingerprint(review, candidate, follow_up),
        "evidence_url": best_evidence_url(review, candidate, follow_up),
    }


def retention_status_from_selection_reason(
    reason: str,
    review: dict[str, Any],
    candidate: dict[str, Any],
) -> str:
    if reason in {"ai_rejected", "forbidden_source_url"}:
        return "hard_reject"
    if reason in {"generic_or_job_board_account_name", "vendor_only_without_target_customer"}:
        return "needs_identity_resolution"
    if reason in {"hint_channel_requires_public_web_evidence", "missing_verified_live_public_evidence"}:
        return "needs_source_cleanup"
    if "duplicate" in reason or reason == "prior_or_parked_account_duplicate":
        return "duplicate_same_opportunity"
    if reason == "retained_good_candidate_over_final_count":
        return review.get("retention_status") or candidate.get("retention_status") or "final_ready"
    return "needs_source_cleanup"


def current_opportunity_fingerprint(
    review: dict[str, Any],
    candidate: dict[str, Any],
    follow_up: list[dict[str, Any]],
) -> str:
    return lead_tools.stable_fingerprint(
        "opp",
        review.get("company_name") or candidate.get("company_name"),
        review.get("signal_type") or candidate.get("signal_type"),
        candidate.get("dynamics_product"),
        best_evidence_url(review, candidate, follow_up),
        review.get("opportunity_signal") or candidate.get("signal_summary"),
    )


def build_retention_queues(
    *,
    vetting_output: dict[str, Any],
    selected: list[dict[str, Any]],
    excluded: list[dict[str, Any]],
    raw_search: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    selected_ids = {str(item.get("candidate_id") or "") for item in selected if item.get("candidate_id")}
    excluded_by_id = {
        str(item.get("candidate_id") or ""): item
        for item in excluded
        if item.get("candidate_id")
    }
    candidate_ledger: list[dict[str, Any]] = []
    source_cleanup_queue: list[dict[str, Any]] = []
    identity_resolution_queue: list[dict[str, Any]] = []
    duplicate_queue: list[dict[str, Any]] = []
    retained_good_candidates: list[dict[str, Any]] = []

    for record in vetting_output.get("records") or []:
        row = retention_row_from_record(record, excluded_by_id)
        candidate_ledger.append(row)
        status = row["retention_status"]
        if row.get("candidate_id") in selected_ids:
            continue
        if status == "needs_identity_resolution":
            identity_resolution_queue.append(row)
        elif status == "duplicate_same_opportunity":
            duplicate_queue.append(row)
        elif status == "needs_source_cleanup":
            source_cleanup_queue.append(row)
        elif status in {"final_ready", "same_company_new_opportunity_review"}:
            retained_good_candidates.append(row)

    hard_reject_queue = []
    for lead in raw_search.get("hard_rejected_leads") or []:
        hard_reject_queue.append(
            {
                "candidate_id": lead.get("candidate_id") or (lead.get("audit_trace") or {}).get("candidate_id"),
                "company_name": lead.get("company_name"),
                "retention_status": "hard_reject",
                "reason": lead.get("hard_rejection_reason") or lead.get("rejection_reason"),
                "evidence_urls": lead.get("evidence_urls") or [],
            }
        )

    return {
        "candidate_ledger": candidate_ledger,
        "source_cleanup_queue": source_cleanup_queue,
        "identity_resolution_queue": identity_resolution_queue,
        "duplicate_queue": duplicate_queue,
        "hard_reject_queue": hard_reject_queue,
        "retained_good_candidates": retained_good_candidates,
    }


def retention_row_from_record(
    record: dict[str, Any],
    excluded_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    review = record.get("final_review") or {}
    candidate = record.get("candidate") or {}
    follow_up = record.get("follow_up_evidence") or review.get("follow_up_evidence") or []
    candidate_id = review.get("candidate_id") or candidate.get("candidate_id")
    exclusion = excluded_by_id.get(str(candidate_id or ""), {})
    reason = exclusion.get("reason") or retention_reason_from_review(review, candidate, follow_up)
    status = exclusion.get("retention_status") or retention_status_from_review(reason, review, candidate)
    return {
        "run_id": review.get("run_id") or candidate.get("run_id"),
        "candidate_id": candidate_id,
        "company_name": review.get("company_name") or candidate.get("company_name"),
        "source_company": review.get("source_company") or candidate.get("source_company"),
        "source_role": review.get("source_role") or candidate.get("source_role"),
        "account_identity_status": review.get("account_identity_status") or candidate.get("account_identity_status"),
        "retention_status": status,
        "reason": reason,
        "source_channel": review.get("source_channel") or candidate.get("source_channel") or "public_web",
        "final_pdf_eligible": bool(
            review.get("final_pdf_eligible")
            if "final_pdf_eligible" in review
            else candidate.get("final_pdf_eligible", True)
        ),
        "verified_live": has_verified_public_evidence(review, candidate, follow_up),
        "source_fetch_status": review.get("source_fetch_status") or candidate.get("source_fetch_status"),
        "lead_status": review.get("lead_status"),
        "signal_strength": review.get("signal_strength"),
        "signal_type": review.get("signal_type") or candidate.get("signal_type"),
        "company_fingerprint": review.get("company_fingerprint") or candidate.get("company_fingerprint"),
        "opportunity_fingerprint": review.get("opportunity_fingerprint") or candidate.get("opportunity_fingerprint") or current_opportunity_fingerprint(review, candidate, follow_up),
        "source_fingerprint": review.get("source_fingerprint") or candidate.get("source_fingerprint"),
        "evidence_url": best_evidence_url(review, candidate, follow_up),
        "evidence_gaps": review.get("evidence_gaps") or candidate.get("missing_verification_points") or [],
        "deterministic_flags": review.get("deterministic_flags") or candidate.get("deterministic_flags") or [],
        "identity_resolution_required": bool(review.get("identity_resolution_required") or candidate.get("identity_resolution_required")),
        "follow_up_evidence_count": len(follow_up),
    }


def retention_reason_from_review(
    review: dict[str, Any],
    candidate: dict[str, Any],
    follow_up: list[dict[str, Any]],
) -> str:
    if review.get("lead_status") == "reject":
        return review.get("final_rejection_reason") or "ai_rejected"
    if review.get("invented_candidate_facts_detected"):
        return "invented_candidate_facts_detected"
    if review.get("identity_resolution_required") or candidate.get("identity_resolution_required"):
        return "identity_resolution_required"
    source_channel = review.get("source_channel") or candidate.get("source_channel") or "public_web"
    if not discovery_backbone_tools.final_pdf_eligible_from_channel(source_channel):
        return "hint_channel_requires_public_web_evidence"
    if not best_evidence_url(review, candidate, follow_up):
        return "missing_public_evidence_url"
    if not has_verified_public_evidence(review, candidate, follow_up):
        return "missing_verified_live_public_evidence"
    if review.get("lead_status") == "source_cleanup_needed":
        return "source_cleanup_needed"
    return "retained_for_final_or_future_selection"


def retention_status_from_review(
    reason: str,
    review: dict[str, Any],
    candidate: dict[str, Any],
) -> str:
    if reason in {"ai_rejected", "forbidden_source_url"} or review.get("lead_status") == "reject":
        return "hard_reject"
    if reason in {"identity_resolution_required", "generic_or_job_board_account_name", "vendor_only_without_target_customer"}:
        return "needs_identity_resolution"
    if reason in {"hint_channel_requires_public_web_evidence", "missing_verified_live_public_evidence"}:
        return "needs_source_cleanup"
    if "duplicate" in reason or reason == "prior_or_parked_account_duplicate":
        return "duplicate_same_opportunity"
    if reason == "retained_for_final_or_future_selection":
        return review.get("retention_status") or candidate.get("retention_status") or "final_ready"
    return "needs_source_cleanup"


def build_shortage_report(
    final_output: dict[str, Any],
    queues: dict[str, list[dict[str, Any]]],
    final_count: int,
) -> dict[str, Any]:
    leads = final_output.get("leads") or []
    shortage = max(0, final_count - len(leads))
    return {
        "artifact_type": "uk_ie_d365_shortage_report",
        "generated_at": now_utc(),
        "target_final_leads": final_count,
        "final_ready_leads": len(leads),
        "shortage_count": shortage,
        "completion_status": final_output.get("metadata", {}).get("completion_status"),
        "queue_counts": {
            "source_cleanup_queue": len(queues["source_cleanup_queue"]),
            "identity_resolution_queue": len(queues["identity_resolution_queue"]),
            "duplicate_queue": len(queues["duplicate_queue"]),
            "hard_reject_queue": len(queues["hard_reject_queue"]),
            "retained_good_candidates": len(queues["retained_good_candidates"]),
        },
        "next_actions": shortage_next_actions(queues, shortage),
        "selection_exclusions": final_output.get("selection_exclusions") or [],
    }


def shortage_next_actions(queues: dict[str, list[dict[str, Any]]], shortage: int) -> list[str]:
    actions = []
    if shortage <= 0:
        actions.append("No shortage; preserve queued candidates for future opportunities and audit.")
    if queues["identity_resolution_queue"]:
        actions.append("Resolve end-customer identity for partner/vendor/generic-title candidates.")
    if queues["source_cleanup_queue"]:
        actions.append("Fetch or replace source URLs for cleanup-needed candidates, especially grounding redirects and blocked pages.")
        if any(row.get("reason") == "hint_channel_requires_public_web_evidence" for row in queues["source_cleanup_queue"]):
            actions.append("Convert Agent Search, Workspace, CRM, or MCP hints into verified public-web evidence before report/PDF use.")
    if queues["retained_good_candidates"]:
        actions.append("Review retained good candidates over the final-count cap before starting a new search.")
    if not actions:
        actions.append("Run a new bounded search pass with memory preflight and targeted non-duplicate queries.")
    return actions


def render_shortage_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# UK/IE D365 Shortage Report",
        "",
        f"- Target final leads: {report['target_final_leads']}",
        f"- Final-ready leads: {report['final_ready_leads']}",
        f"- Shortage count: {report['shortage_count']}",
        f"- Completion status: {report.get('completion_status')}",
        "",
        "## Queue Counts",
        "",
    ]
    for key, count in report["queue_counts"].items():
        lines.append(f"- {key}: {count}")
    lines.extend(["", "## Next Actions", ""])
    lines.extend(f"- {item}" for item in report["next_actions"])
    if report.get("selection_exclusions"):
        lines.extend(["", "## Selection Exclusions", ""])
        for item in report["selection_exclusions"]:
            lines.append(f"- {item.get('company_name')}: {item.get('reason')}")
    return "\n".join(lines) + "\n"


def generic_or_job_board_company_name(company_name: str) -> bool:
    normalized = str(company_name or "").lower()
    return any(term in normalized for term in GENERIC_FINAL_COMPANY_TERMS)


def vendor_only_without_target_customer(review: dict[str, Any], candidate: dict[str, Any]) -> bool:
    flags = [str(item).lower() for item in candidate.get("deterministic_flags") or review.get("deterministic_flags") or []]
    source_type = str(candidate.get("source_type") or "").lower()
    source_url_type = str(candidate.get("source_url_type") or "").lower()
    evidence_text = " ".join(
        [
            str(review.get("evidence_used") or ""),
            str(candidate.get("evidence_snippets") or ""),
            str(review.get("opportunity_signal") or ""),
        ]
    ).lower()
    vendor_signal = (
        "vendor_page_without_named_customer" in flags
        or "vendor" in source_type
        or "vendor" in source_url_type
    )
    if not vendor_signal:
        return False
    if "vendor_page_without_named_customer" in flags:
        return True
    target_customer_terms = (
        "case study",
        "customer",
        "selected",
        "implemented",
        "rolled out",
        "replaced",
        "migrated",
        "support for microsoft dynamics",
    )
    return not any(term in evidence_text for term in target_customer_terms)


def fresh_lead_score(review: dict[str, Any]) -> int:
    lead_status = str(review.get("lead_status") or "")
    signal_strength = str(review.get("signal_strength") or "")
    status_score = {
        "ready_to_contact": 300,
        "provisional_contact_now": 200,
        "source_cleanup_needed": 100,
    }.get(lead_status, 0)
    strength_score = {
        "strong": 40,
        "promising": 25,
        "emerging": 10,
        "weak": 0,
    }.get(signal_strength, 0)
    text = " ".join(
        str(review.get(key) or "")
        for key in (
            "signal_type",
            "opportunity_signal",
            "why_this_matters_to_1bt",
            "commercial_opening",
            "value_of_signal",
        )
    ).lower()
    direct_terms = (
        "support",
        "rescue",
        "backlog",
        "rollout",
        "migration",
        "upgrade",
        "hiring",
        "business central",
        "finance",
        "supply chain",
        "customer service",
        "power platform",
        "dataverse",
    )
    return status_score + strength_score + sum(5 for term in direct_terms if term in text)


def final_lead_from_vetting_record(record: dict[str, Any], *, rank: int, metadata: dict[str, Any]) -> dict[str, Any]:
    review = record.get("final_review") or {}
    candidate = record.get("candidate") or {}
    follow_up = record.get("follow_up_evidence") or review.get("follow_up_evidence") or []
    url = best_evidence_url(review, candidate, follow_up)
    fetched = best_source_fetch(url, follow_up) or source_fetch_from_record(review, candidate, url)
    source_name = fetched.get("source_name") if fetched else source_name_from_url(url)
    excerpt = best_evidence_excerpt(review, candidate, follow_up, fetched)
    return {
        "rank": rank,
        "run_id": review.get("run_id") or candidate.get("run_id"),
        "candidate_id": review.get("candidate_id") or candidate.get("candidate_id"),
        "company_fingerprint": review.get("company_fingerprint") or candidate.get("company_fingerprint"),
        "opportunity_fingerprint": review.get("opportunity_fingerprint") or candidate.get("opportunity_fingerprint") or current_opportunity_fingerprint(review, candidate, follow_up),
        "source_fingerprint": review.get("source_fingerprint") or candidate.get("source_fingerprint"),
        "company_name": review.get("company_name") or candidate.get("company_name"),
        "source_company": review.get("source_company") or candidate.get("source_company"),
        "source_role": review.get("source_role") or candidate.get("source_role"),
        "account_identity_status": review.get("account_identity_status") or candidate.get("account_identity_status"),
        "source_channel": review.get("source_channel") or candidate.get("source_channel") or "public_web",
        "final_pdf_eligible": True,
        "retention_status": "final_ready",
        "lead_status": review.get("lead_status"),
        "signal_strength": review.get("signal_strength"),
        "signal_type": review.get("signal_type"),
        "opportunity_signal": review.get("opportunity_signal"),
        "why_this_matters_to_1bt": review.get("why_this_matters_to_1bt"),
        "commercial_opening": review.get("commercial_opening"),
        "value_of_signal": review.get("value_of_signal"),
        "intelligence_reading": review.get("intelligence_reading"),
        "board_relevance": review.get("board_relevance"),
        "contact_target_roles": review.get("contact_target_roles") or [],
        "do_not_claim_notes": review.get("do_not_claim_notes") or [],
        "remaining_uncertainty": review.get("remaining_uncertainty") or [],
        "evidence_url": url,
        "evidence_excerpt": excerpt,
        "source_name": source_name,
        "fetched_at": (fetched.get("fetched_at") if fetched else metadata.get("finished_at") or now_utc()),
        "verified_live": bool(fetched.get("verified_live")) if fetched else bool(review.get("verified_live") or candidate.get("verified_live")),
        "source_provider": metadata.get("provider_path"),
        "project": metadata.get("project"),
        "deterministic_flags": review.get("deterministic_flags") or [],
        "evidence_gaps": review.get("evidence_gaps") or [],
    }


def best_evidence_url(review: dict[str, Any], candidate: dict[str, Any], follow_up: list[dict[str, Any]]) -> str:
    values: list[Any] = []
    values.extend(item.get("final_url") for item in follow_up if item.get("final_url"))
    values.append(review.get("final_url"))
    values.append(candidate.get("final_url"))
    values.append((review.get("source_fetch") or {}).get("final_url"))
    values.append((candidate.get("source_fetch") or {}).get("final_url"))
    values.extend(candidate.get("evidence_urls") or [])
    values.extend(item.get("url") for item in follow_up if item.get("url"))
    values.extend(extract_urls(review.get("evidence_used")))
    for value in values:
        url = str(value or "")
        if url.startswith("http") and not any(term in url.lower() for term in FORBIDDEN_FINAL_URL_TERMS):
            return url
    return ""


def best_source_fetch(url: str, follow_up: list[dict[str, Any]]) -> dict[str, Any]:
    for item in follow_up:
        if item.get("kind") == "source_fetch" and (item.get("url") == url or item.get("final_url") == url):
            return item
    for item in follow_up:
        if item.get("kind") == "source_fetch" and item.get("verified_live"):
            return item
    return {}


def source_fetch_from_record(review: dict[str, Any], candidate: dict[str, Any], url: str) -> dict[str, Any]:
    for item in (review.get("source_fetch") or {}, candidate.get("source_fetch") or {}):
        if item and (item.get("url") == url or item.get("final_url") == url or item.get("verified_live")):
            return item
    return {}


def has_verified_public_evidence(
    review: dict[str, Any],
    candidate: dict[str, Any],
    follow_up: list[dict[str, Any]],
) -> bool:
    url = best_evidence_url(review, candidate, follow_up)
    fetched = best_source_fetch(url, follow_up) or source_fetch_from_record(review, candidate, url)
    return bool(
        review.get("verified_live")
        or candidate.get("verified_live")
        or (fetched and fetched.get("verified_live"))
    )


def best_evidence_excerpt(
    review: dict[str, Any],
    candidate: dict[str, Any],
    follow_up: list[dict[str, Any]],
    fetched: dict[str, Any],
) -> str:
    if fetched.get("text_excerpt"):
        return clean_text(fetched["text_excerpt"])[:1000]
    for item in normalize_list(review.get("evidence_used")):
        text = clean_text(item)
        if text and not text.startswith("http"):
            return text[:1000]
    for item in follow_up:
        text = clean_text(item.get("snippet") or item.get("text_excerpt") or item.get("text"))
        if text:
            return text[:1000]
    snippets = candidate.get("evidence_snippets") or []
    return clean_text(snippets[0] if snippets else review.get("opportunity_signal"))[:1000]


def source_name_from_url(url: str) -> str:
    if not url:
        return ""
    return re.sub(r"^www\.", "", re.sub(r"^https?://", "", url).split("/")[0])


def first_url(values: list[Any]) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def candidate_text_for_audit(lead: dict[str, Any]) -> str:
    parts = [
        lead.get("company_name"),
        lead.get("signal_summary"),
        lead.get("source_query"),
        lead.get("source_query_group"),
        lead.get("signal_type"),
        " ".join(str(item) for item in lead.get("evidence_snippets") or []),
    ]
    return "\n".join(str(item or "") for item in parts)


def render_deterministic_audit_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# UK/IE D365 Deterministic Reject Audit",
        "",
        f"- Passed: {audit['passed']}",
        f"- Hard rejected count: {audit['hard_rejected_count']}",
        f"- Suspicious hard rejects: {audit['suspicious_hard_reject_count']}",
        f"- Result: {audit['success_statement']}",
        "",
        "## Reason Counts",
        "",
    ]
    for reason, count in sorted(audit["rejection_reason_counts"].items()):
        lines.append(f"- {reason}: {count}")
    if audit["suspicious_hard_rejects"]:
        lines.extend(["", "## Suspicious Hard Rejects", ""])
        for item in audit["suspicious_hard_rejects"]:
            lines.append(f"- {item.get('company_name')}: {item.get('suspicious_reason')} ({item.get('reason')})")
    return "\n".join(lines) + "\n"


def render_fresh_leads_markdown(output: dict[str, Any]) -> str:
    lines = [
        "# UK/IE D365 Fresh Useful Leads",
        "",
        f"- Total useful leads: {len(output.get('leads') or [])}",
        f"- Completion status: {output['metadata'].get('completion_status')}",
        f"- Project: {output['metadata'].get('project')}",
        f"- Deterministic reject audit passed: {output['metadata'].get('deterministic_reject_audit_passed')}",
        "",
        "## Best Leads First",
        "",
    ]
    for lead in output.get("leads") or []:
        lines.extend(
            [
                f"## {lead['rank']}. {lead.get('company_name')} - {lead.get('signal_strength')}",
                "",
                f"- Status: {lead.get('lead_status')}",
                f"- Signal: {lead.get('opportunity_signal')}",
                f"- Why this matters to 1BT: {lead.get('why_this_matters_to_1bt')}",
                f"- Commercial opening: {lead.get('commercial_opening')}",
                f"- Evidence: {lead.get('evidence_url')}",
                f"- Excerpt: {lead.get('evidence_excerpt')}",
                f"- Contact roles: {', '.join(lead.get('contact_target_roles') or [])}",
                f"- Do not claim: {'; '.join(lead.get('do_not_claim_notes') or [])}",
                f"- Remaining uncertainty: {'; '.join(lead.get('remaining_uncertainty') or [])}",
                "",
            ]
        )
    return "\n".join(lines)


def render_fresh_leads_report(
    output: dict[str, Any],
    audit: dict[str, Any],
    vetting_output: dict[str, Any],
) -> str:
    status_counts = Counter(lead.get("lead_status") for lead in output.get("leads") or [])
    strength_counts = Counter(lead.get("signal_strength") for lead in output.get("leads") or [])
    return "\n".join(
        [
            "# UK/IE D365 Fresh Lead Batch Report",
            "",
            f"- Final useful leads: {len(output.get('leads') or [])}",
            f"- Status counts: {dict(status_counts)}",
            f"- Strength counts: {dict(strength_counts)}",
            f"- Model/provider/project/location: {output['metadata'].get('model')} / {output['metadata'].get('provider_path')} / {output['metadata'].get('project')} / {output['metadata'].get('location')}",
            f"- AI requests: {vetting_output.get('counts', {}).get('ai_request_count')}",
            f"- Follow-up candidates: {vetting_output.get('counts', {}).get('follow_up_candidate_count')}",
            f"- Deterministic hard rejects audited: {audit['hard_rejected_count']}",
            f"- Suspicious hard rejects: {audit['suspicious_hard_reject_count']}",
            f"- Deterministic conclusion: {audit['success_statement']}",
            "",
            "The final set excludes prior 12-pack accounts, prior 14-report accounts, parked non-final accounts, private LinkedIn, fake/sample URLs, and tender/procurement-only sources.",
            "",
        ]
    )


def scan_secret_patterns(paths: list[Path]) -> dict[str, Any]:
    findings = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append({"file": str(path), "pattern": name, "redacted": True})
    return {
        "artifact_type": "uk_ie_d365_ai_vetting_secret_scan",
        "generated_at": now_utc(),
        "passed": not findings,
        "findings_count": len(findings),
        "findings": findings,
        "scanned_files": [str(path) for path in paths],
    }


def normalize_followup_item(item: Any, *, query: str | None, kind: str) -> dict[str, Any]:
    if isinstance(item, lead_tools.SearchResult):
        return {
            "kind": kind,
            "query": query,
            "title": item.title,
            "url": item.url,
            "snippet": item.snippet,
            "source": item.source,
        }
    if isinstance(item, dict):
        normalized = dict(item)
        normalized.setdefault("kind", kind)
        normalized.setdefault("query", query)
        return normalized
    return {"kind": kind, "query": query, "text": str(item)}


def extract_urls(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False)
    urls = re.findall(r"https?://[^\s\\\\\"')>,;]+", text)
    return [url.rstrip(".,:;") for url in urls]


def normalize_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
