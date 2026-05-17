import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sl_trigger_leads.tools.live_source_tools import find_live_leads
from sl_trigger_leads.tools.opportunity_analysis_tools import (
    analyze_leads_for_1bt,
    export_opportunity_analyses_csv,
)
from sl_trigger_leads.tools.signal_tools import assert_no_simulation_data


LOG_PATH = ROOT / "logs" / "PROMPT#06_opportunity_analysis_smoke.log"
JSON_OUTPUT = ROOT / "outputs" / "PROMPT#06_opportunity_analysis.json"
CSV_OUTPUT = ROOT / "outputs" / "PROMPT#06_opportunity_analysis.csv"


def _load_live_leads() -> tuple[list[dict], str]:
    candidates = [
        ROOT / "outputs" / "PROMPT#05_live_leads_with_source_notes.json",
        ROOT / "outputs" / "PROMPT#04_live_leads.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        leads = data.get("leads", [])
        if leads:
            assert_no_simulation_data(leads)
            return leads, str(path)
    live = find_live_leads(max_results=5, source_limit=4, write_outputs=True)
    leads = live.get("leads", [])
    if leads:
        assert_no_simulation_data(leads)
    return leads, "live_finder_run"


def main() -> int:
    leads, source = _load_live_leads()
    selected = leads[: max(3, min(len(leads), 5))]
    result = analyze_leads_for_1bt(selected, max_results=5)
    analyses = result.get("analyses", [])
    export_opportunity_analyses_csv(analyses, str(CSV_OUTPUT))
    payload = {
        "source_live_leads_path": source,
        "input_lead_count": len(leads),
        "analyzed_count": len(analyses),
        "message": result.get("message"),
        "analyses": analyses,
    }
    JSON_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    vs_one_world = next((item for item in analyses if item.get("company") == "Vs One World (Pvt) Ltd"), {})
    lines = [
        "# PROMPT#06 opportunity analysis smoke",
        f"source_live_leads_path={source}",
        f"input_lead_count={len(leads)}",
        f"analyzed_count={len(analyses)}",
        f"json_output={JSON_OUTPUT}",
        f"csv_output={CSV_OUTPUT}",
    ]
    if vs_one_world:
        lines.extend(
            [
                f"vs_one_world_primary_bucket={vs_one_world.get('primary_bucket')}",
                f"vs_one_world_secondary_buckets={','.join(vs_one_world.get('secondary_buckets', []))}",
                f"vs_one_world_bucket_confidence={vs_one_world.get('bucket_confidence')}",
            ]
        )
    for index, item in enumerate(analyses, start=1):
        lines.append(
            f"{index}. {item.get('company')} | {item.get('primary_bucket')} | {item.get('bucket_confidence')} | {item.get('verdict')} | {item.get('evidence_url')}"
        )
    status = 0
    if len(analyses) < 3:
        lines.append("Overall: FAIL - fewer than 3 verified live leads analyzed")
        status = 1
    elif vs_one_world.get("primary_bucket") != "staff_augmentation_delivery_capacity":
        lines.append("Overall: FAIL - VS One World did not map to staff augmentation")
        status = 1
    else:
        lines.append("Overall: PASS")
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
