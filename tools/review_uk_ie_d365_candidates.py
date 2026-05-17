"""Create a no-live-call human-review shortlist for UK/Ireland D365 candidates."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REVIEW_SCHEMA_VERSION = "2026-05-17.human-review-shortlist-v1"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "Evidence" / "UK_IE_D365_AUDIT_REPLAY.json"
DEFAULT_JSON_OUTPUT = REPO_ROOT / "Evidence" / "UK_IE_D365_HUMAN_REVIEW_SHORTLIST.json"
DEFAULT_MARKDOWN_OUTPUT = REPO_ROOT / "Evidence" / "UK_IE_D365_HUMAN_REVIEW_SHORTLIST.md"

RISKY_REJECTION_REASONS = {
    "vendor_or_service_provider_page_without_defensible_target_customer",
    "recruitment_agency_post_without_defensible_hiring_company",
    "uk_ireland_not_evidenced",
    "missing_explicit_dynamics_365_or_business_app_evidence",
}
INDIRECT_BUSINESS_APP_TERMS = (
    "crm",
    "erp",
    "business central",
    "dataverse",
    "power platform",
    "microsoft business apps",
    "microsoft business applications",
    "dynamics",
    "dynamics ax",
    "dynamics nav",
    "dynamics gp",
    " ce ",
    "f&o",
    "field service",
    "sales",
    "customer service",
)
CASE_STUDY_TERMS = (
    "case study",
    "customer story",
    "client",
    "customer",
    "implemented",
    "rollout",
    "upgrade",
    "migration",
    "rescue",
)
ROLE_TERMS = (
    "support analyst",
    "administrator",
    "functional consultant",
    "application support",
    "crm manager",
    "erp manager",
    "business systems manager",
)
UK_IE_TERMS = (
    "uk",
    "united kingdom",
    "ireland",
    "northern ireland",
    "dublin",
    "belfast",
    ".co.uk",
    ".ie",
)
LOW_VALUE_TERMS = (
    "book a demo",
    "contact us",
    "we provide",
    "we offer",
    "partner in the uk",
    "dynamics 365 partner",
)
TENDER_TERMS = (
    "rfp",
    "tender notice",
    "find a tender",
    "invitation to tender",
    "public procurement",
    "contract notice",
)


def main() -> int:
    result = build_human_review_shortlist(
        input_file=DEFAULT_INPUT,
        json_output=DEFAULT_JSON_OUTPUT,
        markdown_output=DEFAULT_MARKDOWN_OUTPUT,
    )
    print(json.dumps({
        "input_counts": result["input_counts"],
        "output_counts": result["output_counts"],
        "json_output": str(DEFAULT_JSON_OUTPUT),
        "markdown_output": str(DEFAULT_MARKDOWN_OUTPUT),
        "no_live_calls": True,
    }, indent=2))
    return 0


def build_human_review_shortlist(
    *,
    input_file: Path = DEFAULT_INPUT,
    json_output: Path = DEFAULT_JSON_OUTPUT,
    markdown_output: Path = DEFAULT_MARKDOWN_OUTPUT,
    max_tier_d: int = 15,
) -> dict[str, Any]:
    data = json.loads(Path(input_file).read_text(encoding="utf-8"))
    candidates = all_candidates(data)
    reviewed = [review_item(candidate) for candidate in candidates]
    tier_bc = [item for item in reviewed if item["current_tier"] in {"B", "C"}]
    tier_d_risky = [
        item for item in reviewed
        if item["current_tier"] == "D"
        and item.get("original_rejection_reason") in RISKY_REJECTION_REASONS
        and item["recommended_review_action"] != "keep_rejected"
    ]
    tier_d_risky.sort(key=sort_key)
    shortlist = sorted(tier_bc, key=sort_key) + tier_d_risky[:max_tier_d]
    for index, item in enumerate(shortlist, start=1):
        item["review_rank"] = index

    rejection_breakdown = dict(Counter(
        candidate.get("rejection_reason") or "none"
        for candidate in data.get("rejected_leads", [])
    ))
    tier_breakdown = data.get("tier_counts") or dict(Counter(
        candidate.get("signal_tier") or "unknown" for candidate in candidates
    ))
    output = {
        "metadata": metadata(data, input_file),
        "input_counts": {
            "tier_counts": data.get("tier_counts"),
            "lead_count": data.get("lead_count"),
            "rejected_count": data.get("rejected_count"),
        },
        "output_counts": {
            "shortlisted": len(shortlist),
            "high_false_negative_risk": sum(1 for item in shortlist if item["false_negative_risk"] == "high"),
            "medium_false_negative_risk": sum(1 for item in shortlist if item["false_negative_risk"] == "medium"),
            "low_false_negative_risk": sum(1 for item in shortlist if item["false_negative_risk"] == "low"),
            "tier_b": sum(1 for item in shortlist if item["current_tier"] == "B"),
            "tier_c": sum(1 for item in shortlist if item["current_tier"] == "C"),
            "tier_d": sum(1 for item in shortlist if item["current_tier"] == "D"),
        },
        "shortlist": shortlist,
        "rejection_breakdown": rejection_breakdown,
        "tier_breakdown": tier_breakdown,
        "notes": [
            "This is an offline review/export utility over an existing audit replay file.",
            "No live search, Google, Gemini, Vertex, gcloud, browser, or third-party API call is made.",
            "Review actions do not change the underlying Tier A/B/C/D classification.",
        ],
    }
    json_output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_output.write_text(render_markdown(output), encoding="utf-8")
    return output


def metadata(data: dict[str, Any], input_file: Path) -> dict[str, Any]:
    audit = data.get("audit_metadata") or {}
    return {
        "no_live_calls": True,
        "input_file": str(input_file),
        "generated_at": datetime.now(UTC).isoformat(),
        "review_schema_version": REVIEW_SCHEMA_VERSION,
        "classifier_version": audit.get("classifier_version"),
        "audit_schema_version": audit.get("audit_schema_version"),
        "source_run_model": audit.get("effective_model_name"),
        "provider": data.get("provider") or audit.get("search_provider"),
    }


def all_candidates(data: dict[str, Any]) -> list[dict[str, Any]]:
    return list(data.get("leads", [])) + list(data.get("rejected_leads", []))


def review_item(candidate: dict[str, Any]) -> dict[str, Any]:
    score = review_score(candidate)
    current_tier = candidate.get("signal_tier") or "unknown"
    false_negative_risk = risk_label(score)
    commercial_usefulness = usefulness_label(candidate, score)
    return {
        "review_rank": 0,
        "company_name": candidate.get("company_name"),
        "current_tier": current_tier,
        "recommended_review_action": recommended_action(candidate, false_negative_risk, commercial_usefulness),
        "false_negative_risk": false_negative_risk,
        "commercial_usefulness": commercial_usefulness,
        "signal_type": candidate.get("signal_type"),
        "dynamics_product": candidate.get("dynamics_product"),
        "country": candidate.get("country"),
        "evidence_urls": candidate.get("evidence_urls") or [],
        "source_url_type": candidate.get("source_url_type") or "unknown",
        "evidence_snippets": candidate.get("evidence_snippets") or [],
        "original_rejection_reason": candidate.get("rejection_reason"),
        "why_it_was_surfaced": surfaced_reason(candidate, score),
        "why_it_might_be_wrongly_rejected": false_negative_reason(candidate),
        "what_to_check_next": next_check(candidate),
        "suggested_contact_roles": candidate.get("suggested_contact_roles") or [],
        "recommended_outreach_angle": candidate.get("recommended_outreach_angle"),
        "audit_trace_summary": audit_trace_summary(candidate),
        "final_decision_summary": final_decision_summary(candidate),
        "_sort_score": score,
    }


def review_score(candidate: dict[str, Any]) -> int:
    tier = candidate.get("signal_tier")
    reason = candidate.get("rejection_reason")
    text = candidate_text(candidate)
    score = 0
    if tier == "B":
        score += 100
    elif tier == "C":
        score += 82
    elif tier == "D":
        score += {
            "recruitment_agency_post_without_defensible_hiring_company": 74,
            "vendor_or_service_provider_page_without_defensible_target_customer": 68,
            "uk_ireland_not_evidenced": 58,
            "missing_explicit_dynamics_365_or_business_app_evidence": 38,
            "tender_or_procurement_out_of_scope": -80,
            "generic_it_support_without_dynamics_365_evidence": -30,
        }.get(str(reason), 10)
    if contains_any(text, CASE_STUDY_TERMS):
        score += 12
    if contains_any(text, ROLE_TERMS):
        score += 14
    if contains_any(text, UK_IE_TERMS):
        score += 8
    if contains_any(text, INDIRECT_BUSINESS_APP_TERMS):
        score += 12
    if candidate.get("source_url_type") == "grounding_redirect":
        score += 4
    if contains_any(text, LOW_VALUE_TERMS):
        score -= 16
    if is_tender_candidate(candidate):
        score -= 100
    if not candidate.get("company_name") or str(candidate.get("company_name")).lower() == "vertexaisearch":
        score -= 10
    return max(0, min(score, 130))


def sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    tier_priority = {"B": 0, "C": 1, "D": 2}.get(item["current_tier"], 9)
    return (tier_priority, -int(item.get("_sort_score") or 0), str(item.get("company_name") or ""))


def risk_label(score: int) -> str:
    if score >= 85:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def usefulness_label(candidate: dict[str, Any], score: int) -> str:
    tier = candidate.get("signal_tier")
    text = candidate_text(candidate)
    if tier == "B" and (score >= 100 or contains_any(text, ("rescue", "support", "rollout", "hiring", "migration"))):
        return "high"
    if tier in {"B", "C"} or score >= 65:
        return "medium"
    return "low"


def recommended_action(candidate: dict[str, Any], risk: str, usefulness: str) -> str:
    tier = candidate.get("signal_tier")
    reason = candidate.get("rejection_reason")
    text = candidate_text(candidate)
    if is_tender_candidate(candidate):
        return "keep_rejected"
    if tier == "B" and usefulness == "high":
        return "promote_candidate"
    if tier == "B":
        return "keep_provisional"
    if tier == "C":
        return "keep_watchlist"
    if reason in RISKY_REJECTION_REASONS and risk in {"high", "medium"}:
        return "verify_source"
    return "keep_rejected"


def surfaced_reason(candidate: dict[str, Any], score: int) -> str:
    tier = candidate.get("signal_tier")
    reason = candidate.get("rejection_reason")
    if tier == "B":
        return "Tier B provisional candidate is always included for human review."
    if tier == "C":
        return "Tier C watchlist/installed-base candidate is always included for human review."
    if reason in RISKY_REJECTION_REASONS:
        return f"Tier D rejection reason `{reason}` can hide useful commercial leads; review score {score}."
    return "Candidate was not a priority review item."


def false_negative_reason(candidate: dict[str, Any]) -> str:
    reason = candidate.get("rejection_reason")
    text = candidate_text(candidate)
    if not reason:
        return "Not rejected; review checks whether this should stay provisional/watchlist or be promoted."
    if reason == "vendor_or_service_provider_page_without_defensible_target_customer":
        return "Vendor or partner page may contain a target customer or customer story that the deterministic extractor did not defend strongly enough."
    if reason == "recruitment_agency_post_without_defensible_hiring_company":
        return "The job snippet is relevant, but the actual employer may be hidden behind a recruiter or job board."
    if reason == "uk_ireland_not_evidenced":
        return "The source page may contain UK/Ireland evidence missing from the saved snippet."
    if reason == "missing_explicit_dynamics_365_or_business_app_evidence" and contains_any(text, INDIRECT_BUSINESS_APP_TERMS):
        return "The snippet has indirect Microsoft business-app language that may need source-page verification."
    if reason == "missing_explicit_dynamics_365_or_business_app_evidence":
        return "The saved snippet lacks explicit D365 evidence; the source page may still contain it."
    return "The deterministic rejection looks likely correct unless new source evidence is found."


def next_check(candidate: dict[str, Any]) -> str:
    reason = candidate.get("rejection_reason")
    tier = candidate.get("signal_tier")
    if tier == "B":
        return "Resolve clean source URL and verify direct employer/customer context before promotion."
    if tier == "C":
        return "Look for a current support, hiring, migration, upgrade, or rollout trigger."
    if reason == "vendor_or_service_provider_page_without_defensible_target_customer":
        return "Check whether the source names a target customer using or changing Dynamics 365."
    if reason == "recruitment_agency_post_without_defensible_hiring_company":
        return "Verify the direct employer from public, non-authenticated evidence."
    if reason == "uk_ireland_not_evidenced":
        return "Verify UK/Ireland scope from source-page text or company site."
    if reason == "missing_explicit_dynamics_365_or_business_app_evidence":
        return "Verify explicit Dynamics 365 or Microsoft business-app evidence on the source page."
    return "Keep rejected unless new public evidence addresses the blocking rule."


def audit_trace_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    trace = candidate.get("audit_trace") or {}
    rules = trace.get("rule_results") or []
    failed_blocking = [
        rule.get("rule_id") for rule in rules
        if rule.get("severity") == "blocking" and not rule.get("passed")
    ]
    matched_rules = [
        rule.get("rule_id") for rule in rules
        if rule.get("matched_terms")
    ]
    return {
        "candidate_id": trace.get("candidate_id"),
        "source_query": trace.get("source_query"),
        "source_query_group": trace.get("source_query_group"),
        "failed_blocking_rules": failed_blocking,
        "matched_rule_ids": matched_rules[:8],
    }


def final_decision_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    decision = candidate.get("final_decision") or {}
    return {
        "final_tier": decision.get("final_tier") or candidate.get("signal_tier"),
        "accepted": decision.get("accepted"),
        "rejection_reason": decision.get("rejection_reason") or candidate.get("rejection_reason"),
        "promotion_reason": decision.get("promotion_reason"),
        "human_review_recommended": decision.get("human_review_recommended"),
        "human_review_reason": decision.get("human_review_reason"),
    }


def render_markdown(output: dict[str, Any]) -> str:
    metadata = output["metadata"]
    counts = output["input_counts"]["tier_counts"]
    shortlist = output["shortlist"]
    high_risk = [item for item in shortlist if item["false_negative_risk"] == "high"]
    top_commercial = [item for item in shortlist if item["commercial_usefulness"] == "high"][:5]
    lines = [
        "# UK/Ireland D365 Human Review Shortlist",
        "",
        "## Executive Summary",
        f"- Input file: `{metadata['input_file']}`",
        f"- Generated time: `{metadata['generated_at']}`",
        "- No live calls made: yes",
        f"- Previous counts: `{counts}`",
        f"- Number shortlisted: {output['output_counts']['shortlisted']}",
        f"- High-risk false negatives: {len(high_risk)}",
        "- Top commercial candidates: " + (", ".join(item["company_name"] for item in top_commercial) if top_commercial else "none"),
        "",
        "## Top Review Candidates",
        "",
        "Rank | Company | Current Tier | Risk | Usefulness | Why Review | Next Check",
        "--- | --- | --- | --- | --- | --- | ---",
    ]
    for item in shortlist[:10]:
        lines.append(
            f"{item['review_rank']} | {escape_md(item['company_name'])} | {item['current_tier']} | "
            f"{item['false_negative_risk']} | {item['commercial_usefulness']} | "
            f"{escape_md(item['why_it_was_surfaced'])} | {escape_md(item['what_to_check_next'])}"
        )
    lines.extend(["", "## Tier B/C Candidates", ""])
    for item in [row for row in shortlist if row["current_tier"] in {"B", "C"}]:
        lines.extend([
            f"### {item['review_rank']}. {item['company_name']} - Tier {item['current_tier']}",
            f"- Risk/usefulness: {item['false_negative_risk']} / {item['commercial_usefulness']}",
            f"- Signal: {item['signal_type']} | {item['dynamics_product']}",
            f"- Next check: {item['what_to_check_next']}",
            f"- Evidence URL type: `{item['source_url_type']}`",
            "",
        ])
    lines.extend(["## Possible False Negatives from Tier D", ""])
    for item in [row for row in shortlist if row["current_tier"] == "D"][:10]:
        lines.extend([
            f"### {item['review_rank']}. {item['company_name']}",
            f"- Rejection: `{item['original_rejection_reason']}`",
            f"- Risk/usefulness: {item['false_negative_risk']} / {item['commercial_usefulness']}",
            f"- Why it might be wrong: {item['why_it_might_be_wrongly_rejected']}",
            f"- Next check: {item['what_to_check_next']}",
            "",
        ])
    lines.extend(["## Rejection Breakdown", ""])
    for reason, count in sorted(output["rejection_breakdown"].items(), key=lambda row: (-row[1], row[0])):
        lines.append(f"- `{reason}`: {count}")
    lines.extend([
        "",
        "## Recommended Next Actions",
        "",
        "Resolve clean source URLs and verify the top Tier B candidates first, then review the highest-risk Tier D vendor/case-study and recruitment items for defensible target-company evidence.",
        "",
    ])
    return "\n".join(lines)


def candidate_text(candidate: dict[str, Any]) -> str:
    parts = [
        candidate.get("company_name"),
        candidate.get("signal_summary"),
        candidate.get("signal_type"),
        candidate.get("dynamics_product"),
        candidate.get("country"),
        candidate.get("rejection_reason"),
        " ".join(candidate.get("evidence_snippets") or []),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def is_tender_candidate(candidate: dict[str, Any]) -> bool:
    if candidate.get("rejection_reason") == "tender_or_procurement_out_of_scope":
        return True
    text = candidate_text(candidate)
    urls = " ".join(candidate.get("evidence_urls") or []).lower()
    tender_domains = ("find-tender.service.gov.uk", "contracts.service.gov.uk", "etenders.gov.ie")
    return any(domain in urls for domain in tender_domains) or contains_any(text, TENDER_TERMS)


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(term in lower for term in terms)


def escape_md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
