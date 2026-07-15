import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sl_trigger_leads.tools.live_source_tools import find_live_leads
from sl_trigger_leads.tools.signal_tools import assert_no_simulation_data

OUTPUT_DIR = ROOT / "outputs"
LOG_PATH = ROOT / "logs" / "PROMPT#04_live_smoke.log"
JSON_PATH = OUTPUT_DIR / "PROMPT#04_live_leads.json"
CSV_PATH = OUTPUT_DIR / "PROMPT#04_live_leads.csv"


def write_csv(leads: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "company",
        "country",
        "sector",
        "trigger_type",
        "evidence_url",
        "source_name",
        "source_type",
        "published_or_seen_date",
        "fetched_at",
        "score_total",
        "verdict",
        "outreach_angle",
        "limits",
    ]
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for lead in leads:
            score = lead.get("score") or {}
            writer.writerow(
                {
                    "company": lead.get("company"),
                    "country": lead.get("country"),
                    "sector": lead.get("sector"),
                    "trigger_type": lead.get("trigger_type"),
                    "evidence_url": lead.get("evidence_url"),
                    "source_name": lead.get("source_name"),
                    "source_type": lead.get("source_type"),
                    "published_or_seen_date": lead.get("published_or_seen_date"),
                    "fetched_at": lead.get("fetched_at"),
                    "score_total": score.get("total"),
                    "verdict": score.get("verdict"),
                    "outreach_angle": lead.get("outreach_angle"),
                    "limits": lead.get("limits"),
                }
            )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = find_live_leads(max_results=10, source_limit=4)
    leads = result.get("leads", [])
    if leads:
        assert_no_simulation_data(leads)
    JSON_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(leads)

    lines = [
        "# PROMPT#04 live smoke test",
        f"message={result.get('message')}",
        f"sources_fetched={result.get('source_count')}",
        f"source_failures={len(result.get('source_failures', []))}",
        f"verified_live_leads={len(leads)}",
        f"json_output={JSON_PATH}",
        f"csv_output={CSV_PATH}",
    ]
    if not leads:
        lines.append("No verified live leads found from the configured sources in this run.")
    else:
        for index, lead in enumerate(leads, start=1):
            lines.append(
                f"{index}. {lead['company']} | {lead['trigger_type']} | "
                f"{lead['score']['total']} | {lead['score']['verdict']} | {lead['evidence_url']}"
            )
    if result.get("source_failures"):
        lines.append("Source failures:")
        for failure in result["source_failures"]:
            lines.append(f"- {failure.get('source_name')}: {failure.get('error')}")
    lines.append("Overall: PASS")
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
