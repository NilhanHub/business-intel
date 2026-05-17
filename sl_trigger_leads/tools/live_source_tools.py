from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .signal_extractor import extract_public_signals as _extract_public_signals
from .signal_extractor import extract_public_signals_from_source
from .signal_tools import assert_no_simulation_data, clean_text, score_public_lead
from .source_fetcher import fetch_live_sources as _fetch_live_sources
from .source_registry import list_configured_sources


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "outputs"
LIVE_RUN_DIR = Path(__file__).resolve().parents[1] / "data" / "live_runs"


def fetch_live_sources(source_limit: int = 4) -> dict[str, Any]:
    """Fetch configured live public sources and report failures transparently."""
    return _fetch_live_sources(source_limit=source_limit)


def extract_public_signals(html_or_text: str, source_meta: dict[str, Any]) -> dict[str, Any]:
    """ADK wrapper for extracting candidate signals from provided live-source text."""
    leads = _extract_public_signals(html_or_text, source_meta)
    if leads:
        assert_no_simulation_data(leads)
    return {"count": len(leads), "candidates": leads}


def score_live_lead(lead: dict[str, Any]) -> dict[str, Any]:
    """Score one verified live lead and return the lead with a conservative score object."""
    assert_no_simulation_data([lead])
    scored = dict(lead)
    scored["score"] = score_public_lead(scored)
    scored["outreach_angle"] = _outreach_angle(scored)
    assert_no_simulation_data([scored])
    return scored


def find_live_leads(max_results: int = 10, source_limit: int = 4, write_outputs: bool = True) -> dict[str, Any]:
    """Fetch live public sources, extract verified leads, and never fall back to sample data."""
    max_results = max(1, min(int(max_results), 25))
    fetched = fetch_live_sources(source_limit=source_limit)
    candidates = []
    for source in fetched["sources"]:
        candidates.extend(extract_public_signals_from_source(source))

    verified = []
    rejected = []
    for candidate in candidates:
        try:
            scored = score_live_lead(candidate)
            if scored["score"]["verdict"] == "Park" and scored["trigger_type"] == "tender_or_procurement":
                rejected.append({"company": scored.get("company"), "reason": "Tender/procurement-only signal"})
                continue
            verified.append(scored)
        except ValueError as exc:
            rejected.append({"company": candidate.get("company", ""), "reason": str(exc)})

    verified.sort(key=lambda item: item["score"]["total"], reverse=True)
    verified = verified[:max_results]
    if verified:
        assert_no_simulation_data(verified)

    message = (
        f"Found {len(verified)} verified live leads from configured public sources."
        if verified
        else "No verified live leads found from the configured sources in this run."
    )
    result = {
        "message": message,
        "fetched_at": fetched["fetched_at"],
        "source_count": fetched["source_count"],
        "source_coverage": fetched.get("source_coverage", []),
        "sources_fetched": [
            {
                "source_id": item["source_meta"]["source_id"],
                "source_name": item["source_meta"]["source_name"],
                "source_type": item["source_meta"].get("type", ""),
                "ok": item["ok"],
                "status_code": item.get("status_code"),
                "configured_url": item.get("configured_url") or item["source_meta"].get("base_url"),
                "url": item.get("effective_url") or item["source_meta"].get("base_url"),
                "fetch_status": item.get("fetch_status"),
                "recovery_attempted": item.get("recovery_attempted", False),
                "recovered_url": item.get("recovered_url"),
                "recovery_note": item.get("recovery_note", ""),
            }
            for item in fetched["sources"]
        ],
        "source_failures": fetched["failures"],
        "source_notes": _source_notes(fetched.get("source_coverage", [])),
        "source_coverage_summary": _coverage_summary(fetched.get("source_coverage", [])),
        "rejected_candidates": rejected[:20],
        "leads": verified,
    }
    if write_outputs:
        _write_live_run(result)
    return result


def create_live_account_pack(lead: dict[str, Any]) -> dict[str, Any]:
    """Create a source-backed account pack for one verified live lead."""
    scored = score_live_lead(lead) if "score" not in lead else dict(lead)
    assert_no_simulation_data([scored])
    return {
        "company": scored["company"],
        "country": scored["country"],
        "sector": scored["sector"],
        "trigger": {
            "type": scored["trigger_type"],
            "summary": scored["trigger_summary"],
            "evidence_url": scored["evidence_url"],
            "evidence_excerpt": scored["evidence_excerpt"],
            "source_name": scored["source_name"],
            "published_or_seen_date": scored["published_or_seen_date"],
            "fetched_at": scored["fetched_at"],
        },
        "score": scored["score"],
        "1bt_fit": scored.get("1bt_fit", []),
        "outreach_angle": scored.get("outreach_angle") or _outreach_angle(scored),
        "limits": scored["limits"],
        "verified_live": True,
    }


def export_live_leads_csv(output_json_path: str = "", output_csv_path: str = "") -> dict[str, Any]:
    """Export the most recent live leads JSON to CSV."""
    json_path = Path(output_json_path) if output_json_path else OUTPUT_DIR / "PROMPT#04_live_leads.json"
    csv_path = Path(output_csv_path) if output_csv_path else OUTPUT_DIR / "PROMPT#04_live_leads.csv"
    if not json_path.exists():
        return {"ok": False, "error": f"JSON output not found: {json_path}"}
    data = json.loads(json_path.read_text(encoding="utf-8"))
    leads = data.get("leads", [])
    if leads:
        assert_no_simulation_data(leads)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "company",
        "country",
        "sector",
        "trigger_type",
        "evidence_url",
        "source_name",
        "published_or_seen_date",
        "score_total",
        "verdict",
        "outreach_angle",
        "limits",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for lead in leads:
            writer.writerow(
                {
                    "company": lead.get("company"),
                    "country": lead.get("country"),
                    "sector": lead.get("sector"),
                    "trigger_type": lead.get("trigger_type"),
                    "evidence_url": lead.get("evidence_url"),
                    "source_name": lead.get("source_name"),
                    "published_or_seen_date": lead.get("published_or_seen_date"),
                    "score_total": (lead.get("score") or {}).get("total"),
                    "verdict": (lead.get("score") or {}).get("verdict"),
                    "outreach_angle": lead.get("outreach_angle"),
                    "limits": lead.get("limits"),
                }
            )
    return {"ok": True, "csv_path": str(csv_path), "row_count": len(leads)}


def report_source_failures(live_result: dict[str, Any]) -> dict[str, Any]:
    """Summarize live source fetch failures for transparent ADK Web output."""
    failures = live_result.get("source_failures", [])
    if not failures:
        return {"failure_count": 0, "message": "No source fetch failures reported."}
    return {
        "failure_count": len(failures),
        "failures": failures,
        "message": "Some live sources failed; results are partial and should be interpreted accordingly.",
    }


def _coverage_summary(coverage: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "sources_checked": len(coverage),
        "sources_succeeded": sum(1 for item in coverage if item.get("fetch_status") == "success"),
        "sources_recovered": sum(1 for item in coverage if item.get("fetch_status") == "recovered"),
        "sources_failed": sum(1 for item in coverage if item.get("fetch_status") == "failed"),
    }


def _source_notes(coverage: list[dict[str, Any]]) -> list[str]:
    notes = []
    for item in coverage:
        if item.get("fetch_status") == "recovered":
            notes.append(
                f"Source note: {item.get('source_name')} failed at {item.get('configured_url')} and recovery used {item.get('recovered_url')}."
            )
        elif item.get("fetch_status") == "failed":
            if item.get("recovery_attempted"):
                notes.append(
                    f"Source note: {item.get('source_name')} failed at {item.get('configured_url')} and recovery did not find a usable replacement in this run."
                )
            else:
                notes.append(
                    f"Source note: {item.get('source_name')} failed at {item.get('configured_url')}: {item.get('failure_reason')}"
                )
    return notes


def _outreach_angle(lead: dict[str, Any]) -> str:
    if not lead.get("1bt_fit"):
        return "Do not outreach yet; verify stronger IT/AI/CRM/data/support relevance first."
    fit = ", ".join(lead["1bt_fit"][:3])
    return (
        f"Use the public signal from {lead['source_name']} to ask whether {lead['company']} "
        f"needs help with {fit}. Cite {lead['evidence_url']} and verify the right contact before emailing."
    )


def _write_live_run(result: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_RUN_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    (OUTPUT_DIR / "PROMPT#04_live_leads.json").write_text(payload, encoding="utf-8")
    safe_ts = result["fetched_at"].replace(":", "-")
    (LIVE_RUN_DIR / f"{safe_ts}_live_leads.json").write_text(payload, encoding="utf-8")
