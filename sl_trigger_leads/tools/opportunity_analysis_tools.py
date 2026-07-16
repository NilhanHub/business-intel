from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .signal_tools import assert_no_simulation_data, clean_text

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "data" / "onebt_service_taxonomy.json"


BUCKET_ORDER = [
    "staff_augmentation_delivery_capacity",
    "custom_software_development",
    "ai_apps_workflow_automation",
    "ai_strategy_consulting",
    "data_analytics_ai",
    "microsoft_dynamics_365_crm_power_platform",
    "integrations_api_middleware",
    "managed_application_it_support",
    "cloud_product_development",
    "qa_test_automation",
    "low_fit_or_watch",
]


KEYWORD_RULES: dict[str, list[tuple[str, int]]] = {
    "staff_augmentation_delivery_capacity": [
        ("hiring", 5),
        ("vacancy", 4),
        ("vacancies", 4),
        ("job", 3),
        ("jobs", 3),
        ("role", 3),
        ("roles", 3),
        ("engineer", 3),
        ("developer", 3),
        ("qe", 4),
        ("qa", 3),
        ("api", 2),
        ("integration", 2),
        ("backend", 2),
        ("data engineer", 4),
        ("data analyst", 3),
        ("support engineer", 4),
        ("delivery", 3),
    ],
    "custom_software_development": [
        ("software engineer", 6),
        ("software development", 6),
        (".net", 6),
        ("backend", 5),
        ("developer", 4),
        ("platform", 3),
        ("product launch", 5),
        ("portal", 4),
        ("web developer", 5),
        ("mobile development", 5),
        ("api engineer", 3),
        ("api integration", 3),
    ],
    "ai_apps_workflow_automation": [
        ("ai developer", 10),
        ("ai engineer", 10),
        ("ai", 5),
        ("artificial intelligence", 6),
        ("ml", 5),
        ("machine learning", 6),
        ("mlops", 7),
        ("automation", 5),
        ("workflow", 4),
        ("agentic", 5),
        ("intelligent process", 6),
    ],
    "ai_strategy_consulting": [
        ("ai strategy", 9),
        ("ai roadmap", 8),
        ("roadmap", 5),
        ("board", 3),
        ("executive", 3),
        ("digital transformation agenda", 6),
        ("transformation agenda", 5),
        ("exploratory ai", 6),
    ],
    "data_analytics_ai": [
        ("dashboard", 7),
        ("dashboards", 7),
        ("analytics", 7),
        ("data analyst", 8),
        ("data engineer", 7),
        ("reporting", 6),
        ("business intelligence", 8),
        ("bi", 4),
        ("data workflow", 6),
        ("data platform", 7),
        ("customer analytics", 7),
        ("insights", 5),
    ],
    "microsoft_dynamics_365_crm_power_platform": [
        ("crm", 8),
        ("dynamics", 10),
        ("dynamics 365", 12),
        ("power platform", 12),
        ("customer service", 6),
        ("claims automation", 10),
        ("claims", 4),
        ("field service", 6),
        ("customer data", 6),
        ("erp", 4),
        ("finance operations", 5),
        ("sales process", 5),
    ],
    "integrations_api_middleware": [
        ("api", 6),
        ("apis", 6),
        ("integration", 7),
        ("integrations", 7),
        ("middleware", 7),
        ("erp integration", 6),
        ("crm integration", 6),
        ("data exchange", 5),
        ("system connectivity", 5),
        ("payment integration", 5),
    ],
    "managed_application_it_support": [
        ("application support", 8),
        ("support engineer", 7),
        ("production support", 8),
        ("operations support", 6),
        ("managed support", 8),
        ("managed it", 7),
        ("support load", 5),
        ("customer support tooling", 6),
        ("platform management", 6),
    ],
    "cloud_product_development": [
        ("aws", 8),
        ("azure", 8),
        ("cloud", 6),
        ("serverless", 7),
        ("saas", 4),
        ("deployment modernization", 7),
        ("cloud platform", 7),
        ("cloud product", 7),
        ("devops", 6),
    ],
    "qa_test_automation": [
        ("qe", 7),
        ("qa", 7),
        ("quality engineering", 7),
        ("quality assurance", 7),
        ("test automation", 8),
        ("api testing", 8),
        ("testing", 4),
        ("bdd", 5),
        ("performance testing", 6),
        ("regression testing", 6),
        ("release confidence", 5),
    ],
    "low_fit_or_watch": [
        ("award", 4),
        ("csr", 4),
        ("anniversary", 4),
        ("sponsorship", 4),
        ("celebrates", 4),
        ("recognised", 4),
        ("recognized", 4),
        ("generic", 3),
        ("vague", 3),
    ],
}


TRIGGER_BONUSES: dict[str, dict[str, int]] = {
    "hiring_spike": {
        "staff_augmentation_delivery_capacity": 6,
    },
    "system_integration_pressure": {
        "integrations_api_middleware": 8,
        "staff_augmentation_delivery_capacity": 4,
        "custom_software_development": 3,
    },
    "ai_or_digital_initiative": {
        "ai_apps_workflow_automation": 7,
        "ai_strategy_consulting": 3,
        "data_analytics_ai": 2,
    },
    "product_launch": {
        "custom_software_development": 6,
        "cloud_product_development": 2,
    },
    "generic_pr_fluff": {
        "low_fit_or_watch": 10,
    },
    "irrelevant": {
        "low_fit_or_watch": 10,
    },
    "tender_or_procurement": {
        "low_fit_or_watch": 12,
    },
}


BASE_DO_NOT_CLAIM = [
    "Do not claim they are definitely understaffed.",
    "Do not claim they have budget.",
    "Do not claim they want outsourcing.",
    "Do not claim they use Dynamics 365 unless evidence says so.",
    "Do not claim they need AI unless evidence says so.",
    "Do not claim a named decision maker unless one is verified.",
]


def load_onebt_service_taxonomy() -> dict[str, Any]:
    """Load the local 1BT service taxonomy used for deterministic opportunity analysis."""
    with TAXONOMY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def classify_opportunity_bucket(lead: dict[str, Any]) -> dict[str, Any]:
    """Classify one verified live lead into 1BT service buckets using deterministic evidence rules."""
    assert_no_simulation_data([lead])
    taxonomy = load_onebt_service_taxonomy()
    bucket_lookup = _bucket_lookup(taxonomy)
    text = _lead_text(lead)
    lowered = f" {text.lower()} "
    scores = dict.fromkeys(BUCKET_ORDER, 0)
    evidence_hits: dict[str, list[str]] = {bucket_id: [] for bucket_id in BUCKET_ORDER}

    for bucket_id, rules in KEYWORD_RULES.items():
        for phrase, weight in rules:
            if _contains_phrase(lowered, phrase):
                scores[bucket_id] += weight
                evidence_hits[bucket_id].append(phrase)

    trigger_type = clean_text(lead.get("trigger_type"))
    for bucket_id, bonus in TRIGGER_BONUSES.get(trigger_type, {}).items():
        scores[bucket_id] += bonus
        evidence_hits[bucket_id].append(f"trigger:{trigger_type}")

    source_type = clean_text(lead.get("source_type")).lower()
    source_name = clean_text(lead.get("source_name")).lower()
    if source_type == "job_board" or "jobs" in source_name:
        scores["staff_augmentation_delivery_capacity"] += 8
        evidence_hits["staff_augmentation_delivery_capacity"].append("source:job_board")

    if _contains_phrase(lowered, "ai developer") or _contains_phrase(lowered, "ai engineer"):
        scores["ai_apps_workflow_automation"] += 7
        evidence_hits["ai_apps_workflow_automation"].append("role:ai_implementation")

    if _contains_phrase(lowered, "qe") and _contains_phrase(lowered, "api"):
        scores["staff_augmentation_delivery_capacity"] += 4
        evidence_hits["staff_augmentation_delivery_capacity"].append("qe_api_delivery_role")

    primary_bucket, ranked = _select_primary(scores, trigger_type)
    secondary_buckets = [
        bucket_id
        for bucket_id, score in ranked
        if bucket_id != primary_bucket and bucket_id != "low_fit_or_watch" and score >= 3
    ][:4]
    if primary_bucket == "staff_augmentation_delivery_capacity":
        secondary_buckets = _ensure_vs_one_world_secondaries(secondary_buckets, lowered, scores)

    confidence = _confidence(primary_bucket, ranked)
    return {
        "primary_bucket": primary_bucket,
        "primary_bucket_display": bucket_lookup[primary_bucket]["display_name"],
        "secondary_buckets": secondary_buckets,
        "secondary_bucket_displays": [bucket_lookup[bucket_id]["display_name"] for bucket_id in secondary_buckets],
        "bucket_confidence": confidence,
        "bucket_scores": {bucket_id: score for bucket_id, score in ranked if score > 0},
        "evidence_hits": {bucket_id: hits for bucket_id, hits in evidence_hits.items() if hits},
        "classification_note": _classification_note(primary_bucket, confidence, bucket_lookup),
    }


def analyze_opportunity_for_1bt(lead: dict[str, Any]) -> dict[str, Any]:
    """Create a compact 1BT opportunity analysis for one verified live lead."""
    assert_no_simulation_data([lead])
    taxonomy = load_onebt_service_taxonomy()
    bucket_lookup = _bucket_lookup(taxonomy)
    classification = classify_opportunity_bucket(lead)
    primary = classification["primary_bucket"]
    primary_meta = bucket_lookup[primary]
    score = lead.get("score") or {}
    verdict = _normalize_verdict(clean_text(score.get("verdict")) or "Verify first", primary)
    reasoning = _reasoning(lead, classification, primary_meta)
    offer = _recommended_offer(primary, primary_meta)
    strategy = create_response_strategy(
        {
            "company": lead.get("company"),
            "evidence_url": lead.get("evidence_url"),
            "trigger_type": lead.get("trigger_type"),
            "trigger_summary": lead.get("trigger_summary"),
            "primary_bucket": primary,
            "secondary_buckets": classification["secondary_buckets"],
            "bucket_confidence": classification["bucket_confidence"],
            "evidence_excerpt": lead.get("evidence_excerpt"),
            "recommended_1bt_offer": offer,
            "verdict": verdict,
        }
    )
    analysis = {
        "company": lead.get("company", ""),
        "evidence_url": lead.get("evidence_url", ""),
        "trigger_type": lead.get("trigger_type", ""),
        "trigger_summary": lead.get("trigger_summary", ""),
        "primary_bucket": primary,
        "primary_bucket_display": primary_meta["display_name"],
        "secondary_buckets": classification["secondary_buckets"],
        "secondary_bucket_displays": classification["secondary_bucket_displays"],
        "bucket_confidence": classification["bucket_confidence"],
        "reasoning": reasoning,
        "evidence_excerpt": lead.get("evidence_excerpt", ""),
        "recommended_1bt_offer": offer,
        "recommended_outreach_theme": strategy["recommended_outreach_theme"],
        "email_positioning": strategy["email_positioning"],
        "who_to_contact": strategy["who_to_contact"],
        "what_to_verify_next": strategy["what_to_verify_next"],
        "do_not_claim": strategy["do_not_claim"],
        "verdict": verdict,
        "bucket_scores": classification["bucket_scores"],
        "evidence_hits": classification["evidence_hits"],
    }
    assert_no_simulation_data([_analysis_guard_record(analysis)])
    return analysis


def analyze_leads_for_1bt(leads: list[dict[str, Any]], max_results: int = 5) -> dict[str, Any]:
    """Analyze multiple verified live leads for 1BT service-bucket fit."""
    max_results = max(1, min(int(max_results), 25))
    selected = list(leads or [])[:max_results]
    if selected:
        assert_no_simulation_data(selected)
    analyses = [analyze_opportunity_for_1bt(lead) for lead in selected]
    return {
        "analysis_count": len(analyses),
        "message": (
            f"Analyzed {len(analyses)} verified live leads for 1BT opportunity fit."
            if analyses
            else "No verified live leads supplied for opportunity analysis."
        ),
        "analyses": analyses,
    }


def create_response_strategy(opportunity_analysis: dict[str, Any]) -> dict[str, Any]:
    """Create a response strategy from an opportunity analysis object."""
    taxonomy = load_onebt_service_taxonomy()
    bucket_lookup = _bucket_lookup(taxonomy)
    primary = clean_text(opportunity_analysis.get("primary_bucket")) or "low_fit_or_watch"
    if primary not in bucket_lookup:
        primary = "low_fit_or_watch"
    meta = bucket_lookup[primary]
    company = clean_text(opportunity_analysis.get("company")) or "the company"
    evidence_url = clean_text(opportunity_analysis.get("evidence_url"))
    excerpt = clean_text(opportunity_analysis.get("evidence_excerpt"))
    theme = _theme_for_bucket(primary, meta)
    return {
        "recommended_outreach_theme": theme,
        "email_positioning": _email_positioning(company, primary, meta, evidence_url, excerpt),
        "who_to_contact": _who_to_contact(primary),
        "what_to_verify_next": _verify_next(primary),
        "do_not_claim": _do_not_claim(primary),
    }


def export_opportunity_analyses_csv(analyses: list[dict[str, Any]], output_csv_path: str) -> dict[str, Any]:
    """Export opportunity analyses to CSV for evidence and review."""
    path = Path(output_csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "company",
        "evidence_url",
        "trigger_type",
        "primary_bucket",
        "primary_bucket_display",
        "secondary_buckets",
        "bucket_confidence",
        "verdict",
        "recommended_1bt_offer",
        "recommended_outreach_theme",
        "who_to_contact",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in analyses:
            writer.writerow(
                {
                    "company": item.get("company", ""),
                    "evidence_url": item.get("evidence_url", ""),
                    "trigger_type": item.get("trigger_type", ""),
                    "primary_bucket": item.get("primary_bucket", ""),
                    "primary_bucket_display": item.get("primary_bucket_display", ""),
                    "secondary_buckets": ";".join(item.get("secondary_buckets", [])),
                    "bucket_confidence": item.get("bucket_confidence", ""),
                    "verdict": item.get("verdict", ""),
                    "recommended_1bt_offer": item.get("recommended_1bt_offer", ""),
                    "recommended_outreach_theme": item.get("recommended_outreach_theme", ""),
                    "who_to_contact": item.get("who_to_contact", ""),
                }
            )
    return {"ok": True, "csv_path": str(path), "row_count": len(analyses)}


def _bucket_lookup(taxonomy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {bucket["bucket_id"]: bucket for bucket in taxonomy.get("buckets", [])}


def _lead_text(lead: dict[str, Any]) -> str:
    parts = [
        lead.get("company"),
        lead.get("sector"),
        lead.get("trigger_type"),
        lead.get("trigger_summary"),
        lead.get("evidence_excerpt"),
        lead.get("source_name"),
        lead.get("source_type"),
        " ".join(lead.get("1bt_fit", []) if isinstance(lead.get("1bt_fit"), list) else []),
    ]
    return clean_text(" ".join(clean_text(part) for part in parts))


def _contains_phrase(lowered_text: str, phrase: str) -> bool:
    phrase = phrase.lower()
    if phrase in {".net"}:
        return phrase in lowered_text
    if re.fullmatch(r"[a-z0-9]+", phrase):
        return re.search(rf"\b{re.escape(phrase)}\b", lowered_text) is not None
    return phrase in lowered_text


def _select_primary(scores: dict[str, int], trigger_type: str) -> tuple[str, list[tuple[str, int]]]:
    ranked = sorted(
        scores.items(),
        key=lambda item: (item[1], -BUCKET_ORDER.index(item[0])),
        reverse=True,
    )
    non_low = [(bucket_id, score) for bucket_id, score in ranked if bucket_id != "low_fit_or_watch"]
    top_bucket, top_score = non_low[0]
    low_score = scores.get("low_fit_or_watch", 0)
    if top_score < 4 or (trigger_type in {"generic_pr_fluff", "irrelevant"} and top_score < 8):
        return "low_fit_or_watch", ranked
    if low_score >= top_score and top_score < 10:
        return "low_fit_or_watch", ranked
    return top_bucket, ranked


def _ensure_vs_one_world_secondaries(
    secondary_buckets: list[str],
    lowered: str,
    scores: dict[str, int],
) -> list[str]:
    desired = []
    if _contains_phrase(lowered, "api") or _contains_phrase(lowered, "integration"):
        desired.append("integrations_api_middleware")
    if _contains_phrase(lowered, "qe") or _contains_phrase(lowered, "qa") or _contains_phrase(lowered, "testing"):
        desired.append("qa_test_automation")
    if _contains_phrase(lowered, "engineer") or _contains_phrase(lowered, "developer") or _contains_phrase(lowered, ".net"):
        desired.append("custom_software_development")
    merged = []
    for bucket_id in desired + secondary_buckets:
        if bucket_id != "staff_augmentation_delivery_capacity" and bucket_id not in merged and scores.get(bucket_id, 0) >= 0:
            merged.append(bucket_id)
    return merged[:4]


def _confidence(primary_bucket: str, ranked: list[tuple[str, int]]) -> str:
    if primary_bucket == "low_fit_or_watch":
        return "low"
    top_score = dict(ranked).get(primary_bucket, 0)
    next_score = max((score for bucket_id, score in ranked if bucket_id not in {primary_bucket, "low_fit_or_watch"}), default=0)
    margin = top_score - next_score
    if top_score >= 18 and margin >= 3:
        return "high"
    if top_score >= 9:
        return "medium"
    return "low"


def _classification_note(primary_bucket: str, confidence: str, bucket_lookup: dict[str, dict[str, Any]]) -> str:
    label = bucket_lookup[primary_bucket]["display_name"]
    if confidence == "high":
        return f"Strong evidence for {label}."
    if confidence == "medium":
        return f"Useful but still verify before positioning {label}."
    return f"Weak or uncertain evidence; treat as {label} until more is verified."


def _reasoning(lead: dict[str, Any], classification: dict[str, Any], primary_meta: dict[str, Any]) -> str:
    excerpt = clean_text(lead.get("evidence_excerpt"))
    hits = classification.get("evidence_hits", {}).get(classification["primary_bucket"], [])
    hit_text = ", ".join(hits[:4]) if hits else "the verified live evidence"
    if classification["primary_bucket"] == "staff_augmentation_delivery_capacity":
        return (
            f"The live evidence points to a delivery-capacity opening: {excerpt}. "
            f"Signals matched {hit_text}, so this is better positioned as {primary_meta['display_name']} than a generic software pitch."
        )
    if classification["primary_bucket"] == "low_fit_or_watch":
        return (
            f"The evidence is real but weak for 1BT services: {excerpt}. "
            "Use Watch/Park until a concrete IT, AI, CRM, data, support, or delivery signal appears."
        )
    return (
        f"The live evidence supports {primary_meta['display_name']}: {excerpt}. "
        f"Signals matched {hit_text}; keep the claim limited to what the source shows."
    )


def _recommended_offer(primary_bucket: str, primary_meta: dict[str, Any]) -> str:
    if primary_bucket == "staff_augmentation_delivery_capacity":
        return "Delivery-capacity and staff-augmentation support for near-term engineering, QA, integration, backend, data, AI, or support roles."
    if primary_bucket == "low_fit_or_watch":
        return "Do not pitch yet; monitor for stronger public evidence."
    return primary_meta["example_angle"]


def _theme_for_bucket(primary_bucket: str, meta: dict[str, Any]) -> str:
    if primary_bucket == "low_fit_or_watch":
        return "Watch until stronger evidence appears"
    return f"{meta['display_name']} response"


def _email_positioning(company: str, primary_bucket: str, meta: dict[str, Any], evidence_url: str, excerpt: str) -> str:
    if primary_bucket == "low_fit_or_watch":
        return "Do not email yet from this evidence alone; verify a stronger business or IT trigger first."
    opener = f"Reference the public signal for {company}"
    if evidence_url:
        opener += f" at {evidence_url}"
    if primary_bucket == "staff_augmentation_delivery_capacity":
        return (
            f"{opener}. Position 1BT as a delivery-capacity partner that can help with the specific roles or delivery pressure shown in the evidence: {excerpt}."
        )
    return f"{opener}. Position 1BT around {meta['display_name']} using only the evidence shown: {excerpt}."


def _who_to_contact(primary_bucket: str) -> str:
    if primary_bucket in {"staff_augmentation_delivery_capacity", "custom_software_development", "integrations_api_middleware", "qa_test_automation", "cloud_product_development"}:
        return "Engineering, delivery, product, CTO, or hiring owner; verify the correct person manually before outreach."
    if primary_bucket == "microsoft_dynamics_365_crm_power_platform":
        return "CRM, customer operations, sales operations, IT systems, or business applications owner; verify manually."
    if primary_bucket == "data_analytics_ai":
        return "Data, BI, analytics, operations, or finance reporting owner; verify manually."
    if primary_bucket in {"ai_apps_workflow_automation", "ai_strategy_consulting"}:
        return "Digital transformation, AI, operations, product, or engineering owner; verify manually."
    if primary_bucket == "managed_application_it_support":
        return "Application owner, IT operations, support, or platform management owner; verify manually."
    return "Do not contact yet unless a stronger verified owner or signal appears."


def _verify_next(primary_bucket: str) -> list[str]:
    base = [
        "Confirm the public signal is still current.",
        "Verify the right company contact manually.",
        "Check whether the evidence reflects a current business priority.",
    ]
    if primary_bucket == "staff_augmentation_delivery_capacity":
        return [
            *base,
            "Verify whether the open role is still active.",
            "Check whether there are multiple related technical roles.",
        ]
    if primary_bucket == "microsoft_dynamics_365_crm_power_platform":
        return [
            *base,
            "Verify whether CRM, customer service, claims, Microsoft stack, or ERP language appears in additional public evidence.",
        ]
    if primary_bucket == "low_fit_or_watch":
        return [*base, "Find stronger IT, AI, CRM, data, integration, support, or delivery evidence before outreach."]
    return [*base, "Look for corroborating public evidence before making a specific service claim."]


def _do_not_claim(primary_bucket: str) -> list[str]:
    claims = list(BASE_DO_NOT_CLAIM)
    if primary_bucket != "microsoft_dynamics_365_crm_power_platform":
        claims.append("Do not position Dynamics 365/CRM unless the evidence supports it.")
    if primary_bucket not in {"ai_apps_workflow_automation", "ai_strategy_consulting", "data_analytics_ai"}:
        claims.append("Do not position AI unless the evidence supports it.")
    if primary_bucket == "low_fit_or_watch":
        claims.append("Do not pitch a service bucket as confirmed.")
    return claims


def _normalize_verdict(value: str, primary_bucket: str) -> str:
    if primary_bucket == "low_fit_or_watch":
        return "Watch list" if value not in {"Park"} else "Park"
    if value == "Verify contact first":
        return "Verify first"
    if value in {"Contact now", "Verify first", "Watch list", "Park"}:
        return value
    return "Verify first"


def _analysis_guard_record(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "company": analysis.get("company"),
        "evidence_url": analysis.get("evidence_url"),
        "evidence_excerpt": analysis.get("evidence_excerpt"),
        "verified_live": True,
    }
