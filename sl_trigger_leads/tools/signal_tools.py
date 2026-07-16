from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

TRIGGER_TYPES = [
    "hiring_spike",
    "leadership_change",
    "expansion",
    "acquisition_or_merger",
    "product_launch",
    "ai_or_digital_initiative",
    "compliance_or_regulatory_pressure",
    "system_integration_pressure",
    "generic_pr_fluff",
    "tender_or_procurement",
    "irrelevant",
]

VERDICT_BANDS = {
    "contact_now": "Contact now",
    "verify_first": "Verify contact first",
    "watch_list": "Watch list",
    "park": "Park",
}

SIMULATION_MARKERS = [
    "example.test",
    "sample data",
    "synthetic",
    "simulated",
    "fake source",
    "sample-",
]

TRIGGER_KEYWORDS = {
    "tender_or_procurement": ["tender", "rfp", "request for proposal", "procurement", "bid invitation", "quotation"],
    "hiring_spike": ["hiring", "vacancy", "vacancies", "career", "careers", "job", "jobs", "recruiting", "engineer", "developer"],
    "leadership_change": ["appoint", "appointed", "joins as", "new ceo", "new cio", "new cto", "chief digital", "head of it"],
    "expansion": ["expansion", "expanded", "opens", "opened", "new branch", "new facility", "regional office", "capacity"],
    "acquisition_or_merger": ["acquisition", "merger", "merged", "acquired", "strategic investment"],
    "product_launch": ["launch", "launched", "new product", "new app", "platform"],
    "ai_or_digital_initiative": ["ai", "artificial intelligence", "automation", "digital transformation", "data platform", "analytics"],
    "compliance_or_regulatory_pressure": ["regulatory", "compliance", "audit", "risk", "data protection"],
    "system_integration_pressure": ["integration", "api", "erp", "core banking", "migration", "middleware", "omnichannel"],
    "generic_pr_fluff": ["award", "celebrates", "anniversary", "csr", "sponsorship", "recognised"],
}

SERVICE_KEYWORDS = {
    "AI apps / workflow automation": [" ai ", "artificial intelligence", "automation", "workflow", "machine learning", "mlops"],
    "Dynamics 365 / CRM / Power Platform": ["crm", "customer relationship", "dynamics 365", "power platform", "customer service"],
    "managed IT/application support": ["application support", "managed it", "technical support", "it support", "support engineer"],
    "data workflows": ["data", "analytics", "reporting", "dashboard", "business intelligence", "bi ", "data engineer"],
    "integrations": ["integration", " api ", " erp ", "middleware", "core banking", "migration"],
    "backend/software delivery support": ["software", "developer", "engineer", "backend", ".net", "java", "python"],
}


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def clean_text(text: Any) -> str:
    if text is None:
        return ""
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    return cleaned


def contains_simulation_marker(value: Any) -> bool:
    text = clean_text(value).lower()
    return any(marker in text for marker in SIMULATION_MARKERS)


def assert_no_simulation_data(records: list[dict[str, Any]]) -> None:
    """Fail loudly when runtime lead records contain sample/simulation data or unverifiable evidence."""
    for index, record in enumerate(records):
        evidence_url = clean_text(record.get("evidence_url") or record.get("source_url"))
        excerpt = clean_text(record.get("evidence_excerpt"))
        company = clean_text(record.get("company") or record.get("account"))
        verified_live = record.get("verified_live") is True
        searchable = " ".join(clean_text(v) for v in record.values() if isinstance(v, (str, int, float, bool)))

        problems = []
        if not evidence_url:
            problems.append("missing evidence_url")
        if "example.test" in evidence_url.lower():
            problems.append("example.test source URL")
        if not verified_live:
            problems.append("verified_live is not true")
        if not excerpt:
            problems.append("missing evidence_excerpt")
        if not company:
            problems.append("missing company")
        if contains_simulation_marker(searchable):
            problems.append("simulation/sample marker present")
        if problems:
            raise ValueError(f"Runtime lead {index} blocked: {', '.join(problems)}")


def classify_signal(text: str) -> dict[str, Any]:
    """Classify public-source text into a supported 1BT lead trigger type."""
    signal_text = clean_text(text)
    lowered = f" {signal_text.lower()} "
    if not signal_text:
        return {"trigger_type": "irrelevant", "confidence": 0.0, "reason": "No text supplied."}

    hit_counts = {
        trigger: sum(1 for keyword in keywords if keyword.lower() in lowered)
        for trigger, keywords in TRIGGER_KEYWORDS.items()
    }
    if hit_counts["tender_or_procurement"]:
        return {
            "trigger_type": "tender_or_procurement",
            "confidence": 0.9,
            "reason": "Tender/procurement language was detected; outside this app's non-tender scope.",
        }

    ranked = sorted(
        ((trigger, count) for trigger, count in hit_counts.items() if trigger != "tender_or_procurement"),
        key=lambda item: item[1],
        reverse=True,
    )
    trigger_type, count = ranked[0] if ranked else ("irrelevant", 0)
    if count == 0:
        return {"trigger_type": "irrelevant", "confidence": 0.25, "reason": "No supported live buying signal found."}

    fit = detect_1bt_fit(signal_text)
    if trigger_type == "generic_pr_fluff" and not fit:
        return {
            "trigger_type": "generic_pr_fluff",
            "confidence": 0.8,
            "reason": "PR-style wording found without concrete IT/AI/CRM/data/support relevance.",
        }
    confidence = min(0.95, 0.5 + (0.1 * count) + (0.08 * len(fit)))
    return {
        "trigger_type": trigger_type,
        "confidence": round(confidence, 2),
        "reason": f"Detected {trigger_type} language with {len(fit)} 1BT-fit service areas.",
    }


def detect_1bt_fit(text: str) -> list[str]:
    lowered = f" {clean_text(text).lower()} "
    return [
        label
        for label, keywords in SERVICE_KEYWORDS.items()
        if any(keyword.lower() in lowered for keyword in keywords)
    ]


def verdict_for_score(total: int) -> str:
    if total >= 80:
        return VERDICT_BANDS["contact_now"]
    if total >= 60:
        return VERDICT_BANDS["verify_first"]
    if total >= 40:
        return VERDICT_BANDS["watch_list"]
    return VERDICT_BANDS["park"]


def parse_seen_date(value: Any) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%A, %d %B %Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def _recency_score(value: Any) -> tuple[int, str]:
    parsed = parse_seen_date(value)
    if not parsed:
        return 8, "No published date parsed; using low recency credit for seen-live evidence."
    age = (date.today() - parsed).days
    if age < 0:
        return 12, f"Published date appears future-dated by {abs(age)} days; verify manually."
    if age <= 30:
        return 25, f"Recent public signal, {age} days old."
    if age <= 60:
        return 18, f"Moderately recent public signal, {age} days old."
    if age <= 90:
        return 12, f"Aging public signal, {age} days old."
    return 0, f"Stale public signal, {age} days old."


def score_public_lead(lead: dict[str, Any]) -> dict[str, Any]:
    """Conservatively score one verified live-source lead candidate."""
    assert_no_simulation_data([lead])
    text = " ".join(
        clean_text(lead.get(key))
        for key in ["company", "sector", "trigger_summary", "evidence_excerpt", "source_name"]
    )
    classification = classify_signal(text)
    fit = detect_1bt_fit(text)
    recency, recency_reason = _recency_score(lead.get("published_or_seen_date"))
    service_fit = min(25, 8 * len(fit))
    if classification["trigger_type"] in {"tender_or_procurement", "irrelevant"}:
        service_fit = 0

    reachable = 0
    if "sri lanka" in text.lower() or ".lk" in clean_text(lead.get("evidence_url")).lower():
        reachable += 10
    if re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b", clean_text(lead.get("evidence_excerpt"))):
        reachable += 5
    if lead.get("evidence_url"):
        reachable += 5
    reachable = min(20, reachable)

    named_person = 0
    if re.search(r"\b(appointed|chief|ceo|cio|cto|director|head of|manager)\b", text, re.I):
        named_person = 8
    if re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", clean_text(lead.get("evidence_excerpt"))):
        named_person = max(named_person, 10)
    if "appointed" in text.lower() and named_person:
        named_person = 15

    evidence_quality = 0
    if lead.get("evidence_url"):
        evidence_quality += 3
    if len(clean_text(lead.get("evidence_excerpt"))) >= 80:
        evidence_quality += 3
    if lead.get("source_name"):
        evidence_quality += 2
    if classification["confidence"] >= 0.65:
        evidence_quality += 2
    evidence_quality = min(10, evidence_quality)

    deal_size = 3 if service_fit else 0
    if any(term in text.lower() for term in ["bank", "plc", "group", "enterprise", "dialog", "slt", "hospital", "apparel"]):
        deal_size = 5

    breakdown = {
        "recent_public_trigger": recency,
        "1bt_service_fit": service_fit,
        "local_reachability": reachable,
        "named_person_found": named_person,
        "evidence_quality": evidence_quality,
        "deal_size_likelihood": deal_size,
    }
    total = min(100, sum(breakdown.values()))
    verdict = verdict_for_score(total)
    if classification["trigger_type"] in {"tender_or_procurement", "irrelevant", "generic_pr_fluff"} and service_fit == 0:
        verdict = VERDICT_BANDS["park"]

    return {
        "total": total,
        "breakdown": breakdown,
        "verdict": verdict,
        "scoring_notes": [classification["reason"], recency_reason],
    }
