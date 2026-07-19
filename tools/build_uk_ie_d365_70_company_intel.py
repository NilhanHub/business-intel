"""Build one evidence-preserving intelligence pack from the five UK/IE D365 PDFs.

The PDFs are presentation artifacts. Their adjacent JSON evidence packs remain the
machine-readable source of truth, so this tool keeps every summary traceable to
the exact PDF, public source, evidence excerpt, uncertainty, and pitch lane.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = PROJECT_ROOT / "Evidence"
DEFAULT_CANONICAL_RESEARCH = (
    EVIDENCE_DIR / "UK_IE_D365_70_COMPANY_CANONICAL_RESEARCH_20260719.json"
)


@dataclass(frozen=True)
class Pack:
    batch: int
    pdf_filename: str
    source_filename: str
    collection: str
    name_field: str
    title: str


PACKS = (
    Pack(
        1,
        "2026-06-04__uk-ie-d365__ai-opportunity-intelligence__final__14-accounts.pdf",
        "UK_IE_D365_AI_Opportunity_Intelligence_14_SOURCE_MAP.json",
        "accounts",
        "account",
        "AI-Driven Opportunity Intelligence - 14 Accounts",
    ),
    Pack(
        2,
        "2026-06-14__uk-ie-d365__report-composer__live-smoke__12-accounts.pdf",
        "UK_IE_D365_USEFUL_LEADS_FRESH_20260612.json",
        "leads",
        "company_name",
        "UK/IE D365 Executive Smoke Report - 12 Accounts",
    ),
    Pack(
        3,
        "2026-06-24__uk-ie-d365__ai-opportunity-intelligence__executive-brief__12-opportunity-signals.pdf",
        "UK_IE_D365_USEFUL_LEADS_NOW.json",
        "leads",
        "company_name",
        "AI-Driven Opportunity Intelligence - 12 Opportunity Signals",
    ),
    Pack(
        4,
        "2026-06-29__uk-ie-d365__useful-leads-next__curated__12-accounts.pdf",
        "UK_IE_D365_USEFUL_LEADS_NEXT_20260624_CURATED.json",
        "leads",
        "company_name",
        "UK & Ireland Dynamics 365 - Curated Opportunity Pack",
    ),
    Pack(
        5,
        "2026-07-16__uk-ie-d365__round-5__20-new-accounts.pdf",
        "UK_IE_D365_RUN5_20260716_20_LEADS_FINAL.json",
        "leads",
        "company_name",
        "UK & Ireland Dynamics 365 Opportunity Intelligence - Round 5",
    ),
)


CANONICAL_ALIASES = {
    "Glenveagh": "Glenveagh Properties plc",
    "Littlefish UK Ltd": "Littlefish Group",
    "Ireland Department of Health / HSE": "Health Service Executive",
    "Simply Dynamics 365 Growth Announcement- D365 Partner": "Simply Dynamics 365",
    "Uniphar Medtech Limited": "Uniphar Medtech",
    "The Royal Society / Subscribe360 case-study source": "The Royal Society / Subscribe360",
    "UK defence apparel manufacturer (unnamed in saved evidence)": (
        "UK defence apparel manufacturer (unnamed in source)"
    ),
}


PRODUCT_TERMS = (
    "dynamics 365",
    "d365",
    "business central",
    "power platform",
    "power pages",
    "customer insights",
    "customer service",
    "field service",
    "finance and operations",
    "finance & operations",
    "f&scm",
    "supply chain",
    "dynamics crm",
    "dynamics nav",
    "dynamics ax",
    "microsoft dynamics",
)

CONCRETE_TERMS = (
    "implemented",
    "implementing",
    "rollout",
    "rolled out",
    "migrat",
    "replac",
    "integrat",  # codespell:ignore - intentional stem for integrate/integration
    "autom",
    "upgrade",
    "go-live",
    "go live",
    "hiring",
    "support",
    "portal",
    "warehouse",
    "reporting",
    "case management",
    "contact centre",
    "field service",
    "training",
    "adoption",
    "uses",
    "used",
    "selected",
    "built",
    "moved",
    "asked",
    "transformed",
    "engaged",
    "connects",
    "ties",
    "states",
    "adverts",
    "advertised",
)


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(clean(item) for item in value if clean(item))
    return re.sub(r"\s+", " ", str(value)).strip()


def clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [text for item in value if (text := clean(item))]
    text = clean(value)
    return [text] if text else []


def canonical_name(raw_name: str) -> str:
    return CANONICAL_ALIASES.get(raw_name, raw_name)


def sentence_clip(value: str, limit: int) -> str:
    text = clean(value)
    if len(text) <= limit:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    selected: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*selected, sentence]).strip()
        if selected and len(candidate) > limit:
            break
        selected.append(sentence)
        if len(candidate) >= limit * 0.7:
            break
    clipped = " ".join(selected).strip()
    if clipped and len(clipped) <= limit:
        return clipped
    return text[: limit - 1].rstrip(" ,;:-") + "…"


def first_evidence(record: dict[str, Any]) -> dict[str, Any]:
    evidence = record.get("evidence")
    if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict):
        return evidence[0]
    return {}


def evidence_fact(record: dict[str, Any]) -> str:
    source = first_evidence(record)
    return clean(
        record.get("evidence_excerpt")
        or record.get("d365_microsoft_business_app_evidence")
        or record.get("source_excerpt")
        or source.get("evidence_summary")
        or source.get("evidence_excerpt")
        or record.get("opportunity_signal")
    )


def evidence_url(record: dict[str, Any]) -> str:
    source = first_evidence(record)
    return clean(
        record.get("evidence_url")
        or record.get("final_evidence_url_after_redirect")
        or record.get("source_url")
        or source.get("final_url")
        or source.get("evidence_url")
    )


def source_name(record: dict[str, Any]) -> str:
    source = first_evidence(record)
    return clean(
        record.get("source_name")
        or record.get("source_label")
        or record.get("source_title")
        or source.get("source_name")
    )


def fetched_at(record: dict[str, Any], metadata: dict[str, Any]) -> str:
    source = first_evidence(record)
    return clean(
        record.get("fetched_at")
        or source.get("checked_at")
        or metadata.get("generated_at")
        or metadata.get("generatedAt")
        or metadata.get("created_at")
    )


def is_verified(record: dict[str, Any]) -> bool:
    source = first_evidence(record)
    return bool(
        record.get("verified_live") is True
        or record.get("source_check_verified_live") is True
        or source.get("verified_live") is True
    )


def opportunity_opening(record: dict[str, Any]) -> str:
    return clean(
        record.get("commercial_opening") or record.get("suggested_first_outreach_angle")
    )


def specificity_reasons(
    *, company: str, fact: str, url: str, verified: bool, record: dict[str, Any]
) -> list[str]:
    lowered = fact.casefold()
    reasons: list[str] = []
    if not verified:
        reasons.append(
            "live public source is not explicitly verified in the saved pack"
        )
    if "vertexaisearch.cloud.google.com/grounding-api-redirect" in url:
        reasons.append("source is still a Google grounding redirect")
    if "unnamed" in company.casefold():
        reasons.append("end-customer identity is unresolved")
    if len(fact) < 90:
        reasons.append("evidence fact is too brief")
    if not any(term in lowered for term in PRODUCT_TERMS):
        reasons.append("evidence fact does not name a Microsoft business application")
    if not any(term in lowered for term in CONCRETE_TERMS):
        reasons.append(
            "evidence fact lacks a concrete project, workflow, or operating trigger"
        )
    status = clean(record.get("lead_status")).casefold()
    direct_public_source = (
        bool(url.startswith(("https://", "http://")))
        and "grounding-api-redirect" not in url
    )
    if ("cleanup" in status or "provisional" in status) and (
        not verified or not direct_public_source
    ):
        reasons.append(f"saved lead status is {status}")
    uncertainty = clean(record.get("remaining_uncertainty")).casefold()
    if "source cleanup" in uncertainty or "account-name" in uncertainty:
        reasons.append("saved uncertainty requires source or identity cleanup")
    return reasons


def normalize_record(
    pack: Pack, record: dict[str, Any], metadata: dict[str, Any]
) -> dict[str, Any]:
    raw_name = clean(record.get(pack.name_field))
    company = canonical_name(raw_name)
    source = first_evidence(record)
    fact = evidence_fact(record)
    opening = opportunity_opening(record)
    verified = is_verified(record)
    url = evidence_url(record)
    reasons = specificity_reasons(
        company=company,
        fact=fact,
        url=url,
        verified=verified,
        record=record,
    )
    concise_fact = sentence_clip(fact, 290)
    concise_opening = sentence_clip(opening, 210)
    sheet_summary = concise_fact
    if concise_opening:
        sheet_summary = f"{concise_fact} 1BT opportunity: {concise_opening}"

    opportunity_signal = clean(
        record.get("opportunity_signal") or record.get("why_useful") or fact
    )
    why_it_matters = clean(
        record.get("why_this_matters_to_1bt")
        or record.get("why_useful")
        or opportunity_signal
    )
    signal_strength = clean(
        record.get("signal_strength") or record.get("confidence") or "unrated"
    )
    signal_type = clean(
        record.get("signal_type")
        or record.get("trigger_type")
        or record.get("signal_title")
    )
    evidence_date = fetched_at(record, metadata)
    direct_public_source = (
        bool(url.startswith(("https://", "http://")))
        and "grounding-api-redirect" not in url
    )

    return {
        "canonical_company_name": company,
        "source_company_name": raw_name,
        "batch": pack.batch,
        "rank_in_pdf": int(record.get("rank") or 0),
        "pdf_filename": pack.pdf_filename,
        "report_title": pack.title,
        "source_pack_filename": pack.source_filename,
        "country": clean(record.get("country") or record.get("market")),
        "sector": clean(record.get("sector") or record.get("industry")),
        "signal_strength": signal_strength,
        "signal_type": signal_type,
        "dynamics_product": clean(
            record.get("dynamics_product") or record.get("signal_title")
        ),
        "specific_evidence": fact,
        "opportunity_signal": opportunity_signal,
        "why_this_matters_to_1bt": why_it_matters,
        "commercial_opening": opening,
        "value_of_signal": clean(
            record.get("value_of_signal") or record.get("value_of_the_signal")
        ),
        "intelligence_reading": clean(record.get("intelligence_reading")),
        "board_relevance": clean(record.get("board_relevance")),
        "contact_target_roles": clean_list(
            record.get("contact_target_roles")
            or record.get("suggested_contact_target_roles")
        ),
        "known_contact_person": clean(record.get("known_contact_person")),
        "remaining_uncertainty": clean_list(record.get("remaining_uncertainty")),
        "do_not_claim_notes": clean_list(
            record.get("do_not_claim_notes") or record.get("what_not_to_claim")
        ),
        "evidence_url": url,
        "source_name": source_name(record),
        "evidence_date": evidence_date,
        "verified_live": verified,
        "direct_public_source": direct_public_source,
        "sheet_summary": sheet_summary,
        "needs_adk_refresh": bool(reasons),
        "refresh_reasons": reasons,
        "source_metadata": {
            "lead_status": clean(record.get("lead_status")),
            "supplemental_live_check_required": bool(
                record.get("supplemental_live_check_required")
            ),
            "source_http_status": source.get("http_status"),
        },
    }


def load_records(evidence_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for pack in PACKS:
        path = evidence_dir / pack.source_filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_records = list(payload.get(pack.collection) or [])
        metadata = dict(payload.get("metadata") or {})
        expected = {1: 14, 2: 12, 3: 12, 4: 12, 5: 20}[pack.batch]
        if len(raw_records) != expected:
            raise RuntimeError(
                f"{path.name}: expected {expected} records, found {len(raw_records)}"
            )
        records.extend(
            normalize_record(pack, record, metadata) for record in raw_records
        )
    return records


def validate(records: list[dict[str, Any]], canonical_names: list[str]) -> None:
    names = [record["canonical_company_name"] for record in records]
    canonical_duplicates = sorted(
        name for name in set(canonical_names) if canonical_names.count(name) > 1
    )
    if canonical_duplicates:
        raise RuntimeError(
            f"Duplicate canonical research companies: {canonical_duplicates}"
        )
    if len(records) != 70:
        raise RuntimeError(f"Expected 70 total records, found {len(records)}")
    if len(set(names)) != 70:
        duplicates = sorted(name for name in set(names) if names.count(name) > 1)
        raise RuntimeError(f"Duplicate canonical companies: {duplicates}")
    if set(names) != set(canonical_names):
        missing = sorted(set(canonical_names) - set(names))
        unexpected = sorted(set(names) - set(canonical_names))
        raise RuntimeError(
            f"Canonical mismatch; missing={missing}, unexpected={unexpected}"
        )
    for record in records:
        if not record["specific_evidence"]:
            raise RuntimeError(
                f"{record['canonical_company_name']}: missing evidence fact"
            )
        if not record["sheet_summary"]:
            raise RuntimeError(
                f"{record['canonical_company_name']}: missing sheet summary"
            )


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# UK and Ireland Dynamics 365 - 70 Company Intelligence",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "This crosswalk consolidates the five verified PDF batches. Each account keeps the factual public-signal evidence separate from the proposed 1BT commercial opening.",
        "",
    ]
    for record in payload["companies"]:
        lines.extend(
            [
                f"## {record['canonical_company_name']}",
                "",
                f"- PDF: `{record['pdf_filename']}` (batch {record['batch']})",
                f"- Signal: {record['specific_evidence']}",
                f"- 1BT opportunity: {record['commercial_opening'] or record['opportunity_signal']}",
                f"- Source: {record['source_name']} - {record['evidence_url']}",
                f"- Evidence date: {record['evidence_date'] or 'Not recorded'}",
                f"- Target roles: {', '.join(record['contact_target_roles']) or 'Not recorded'}",
                f"- Uncertainty: {'; '.join(record['remaining_uncertainty']) or 'No additional uncertainty recorded'}",
                f"- ADK refresh: {'required' if record['needs_adk_refresh'] else 'not required'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence-dir", type=Path, default=EVIDENCE_DIR)
    p.add_argument(
        "--canonical-research",
        type=Path,
        default=DEFAULT_CANONICAL_RESEARCH,
    )
    p.add_argument(
        "--output-prefix",
        type=Path,
        default=EVIDENCE_DIR / "UK_IE_D365_70_COMPANY_INTELLIGENCE_20260719",
    )
    return p


def run(args: argparse.Namespace) -> dict[str, Any]:
    research = json.loads(args.canonical_research.read_text(encoding="utf-8"))
    canonical_names = [
        clean(item.get("company")) for item in research.get("companies") or []
    ]
    records = load_records(args.evidence_dir)
    validate(records, canonical_names)
    by_name = {record["canonical_company_name"]: record for record in records}
    ordered = [by_name[name] for name in canonical_names]
    ordered_names = [record["canonical_company_name"] for record in ordered]
    payload = {
        "artifact_type": "uk_ie_d365_70_company_intelligence_crosswalk",
        "generated_at": now_utc(),
        "company_count": len(ordered),
        "pdf_count": len(PACKS),
        "pdf_company_counts": {
            pack.pdf_filename: {1: 14, 2: 12, 3: 12, 4: 12, 5: 20}[pack.batch]
            for pack in PACKS
        },
        "duplicate_company_count": len(ordered_names) - len(set(ordered_names)),
        "canonical_order_matches_crm_research": ordered_names == canonical_names,
        "adk_refresh_count": sum(record["needs_adk_refresh"] for record in ordered),
        "companies": ordered,
    }
    output_prefix = args.output_prefix.resolve()
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    output_prefix.with_suffix(".json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    output_prefix.with_suffix(".md").write_text(markdown(payload), encoding="utf-8")
    refresh_payload = {
        "artifact_type": "uk_ie_d365_70_company_adk_refresh_queue",
        "generated_at": payload["generated_at"],
        "company_count": payload["adk_refresh_count"],
        "companies": [record for record in ordered if record["needs_adk_refresh"]],
    }
    refresh_path = output_prefix.parent / f"{output_prefix.name}_ADK_REFRESH_QUEUE.json"
    refresh_path.write_text(
        json.dumps(refresh_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "company_count": payload["company_count"],
                "pdf_count": payload["pdf_count"],
                "adk_refresh_count": payload["adk_refresh_count"],
                "output_json": str(output_prefix.with_suffix(".json")),
                "output_markdown": str(output_prefix.with_suffix(".md")),
                "refresh_queue": str(refresh_path),
            },
            indent=2,
        )
    )
    return payload


if __name__ == "__main__":
    run(parser().parse_args())
