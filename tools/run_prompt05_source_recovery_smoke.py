import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sl_trigger_leads.tools.live_source_tools import find_live_leads
from sl_trigger_leads.tools.signal_tools import assert_no_simulation_data
from sl_trigger_leads.tools.source_recovery import recover_source_url
from sl_trigger_leads.tools.source_registry import list_configured_sources


LOG_PATH = ROOT / "logs" / "PROMPT#05_source_recovery_smoke.log"
COVERAGE_PATH = ROOT / "outputs" / "PROMPT#05_source_coverage.json"
LIVE_NOTES_PATH = ROOT / "outputs" / "PROMPT#05_live_leads_with_source_notes.json"


def main() -> int:
    sources = list_configured_sources(include_urls=True)
    old_cse = {
        "source_id": "cse_announcements",
        "source_name": "Colombo Stock Exchange - Company Announcements",
        "base_url": "https://www.cse.lk/pages/company-announcements/company-announcements.component.html",
        "type": "announcements",
        "search_terms": ["announcement", "corporate disclosure", "cse"],
        "recovery_candidates": [
            "https://www.cse.lk/",
            "https://www.cse.lk/announcements",
            "https://www.cse.lk/announcements/?category=CORPORATE+DISCLOSURE",
            "https://www.cse.lk/general-announcements",
        ],
    }
    recovery = recover_source_url(
        old_cse,
        {
            "failed_url": old_cse["base_url"],
            "failure_type": "http_404",
            "status_code": 404,
            "original_source_type": "announcements",
        },
    )
    live = find_live_leads(max_results=5, source_limit=4, write_outputs=False)
    leads = live.get("leads", [])
    if leads:
        assert_no_simulation_data(leads)

    coverage_payload = {
        "configured_sources": sources,
        "old_cse_recovery": recovery,
        "live_source_coverage": live.get("source_coverage", []),
        "source_coverage_summary": live.get("source_coverage_summary", {}),
        "source_notes": live.get("source_notes", []),
    }
    COVERAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_PATH.write_text(json.dumps(coverage_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    LIVE_NOTES_PATH.write_text(json.dumps(live, indent=2, ensure_ascii=False), encoding="utf-8")

    source_urls = [source.get("base_url") for source in sources["sources"]]
    cse_recovered = recovery.get("recovery_status") == "recovered" and recovery.get("selected_replacement_url")
    lines = [
        "# PROMPT#05 source recovery smoke",
        f"configured_source_count={sources['source_count']}",
        f"configured_urls_visible={all(bool(url) for url in source_urls)}",
        f"old_cse_recovery_status={recovery.get('recovery_status')}",
        f"old_cse_selected_replacement={recovery.get('selected_replacement_url')}",
        f"live_sources_checked={live.get('source_coverage_summary', {}).get('sources_checked')}",
        f"live_sources_succeeded={live.get('source_coverage_summary', {}).get('sources_succeeded')}",
        f"live_sources_recovered={live.get('source_coverage_summary', {}).get('sources_recovered')}",
        f"live_sources_failed={live.get('source_coverage_summary', {}).get('sources_failed')}",
        f"verified_live_leads={len(leads)}",
        f"coverage_output={COVERAGE_PATH}",
        f"live_notes_output={LIVE_NOTES_PATH}",
    ]
    for source in sources["sources"]:
        lines.append(f"source={source['source_name']} | {source['source_type']} | {source.get('base_url')}")
    if live.get("source_notes"):
        lines.append("Source notes:")
        lines.extend(f"- {note}" for note in live["source_notes"])
    if not all(bool(url) for url in source_urls):
        lines.append("Overall: FAIL")
        status = 1
    elif not cse_recovered:
        lines.append("Overall: FAIL")
        status = 1
    else:
        lines.append("Overall: PASS")
        status = 0
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
