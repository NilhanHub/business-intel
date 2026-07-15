"""PROMPT#10 Contact Resolver Agent smoke runner."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sl_trigger_leads.tools.contact_resolver_tools import (
    PROMPT10_SAMPLE_INPUT_PATH,
    resolve_contacts_for_leads,
)

LOG_PATH = ROOT / "logs" / "PROMPT#10_contact_resolver.log"
DRY_RUN_OUTPUT_PATH = ROOT / "outputs" / "PROMPT#10_contact_resolver_dry_run.json"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def log_safe(event: str, **fields: Any) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": utc_now(), "event": event, **fields}
    LOG_PATH.open("a", encoding="utf-8").write(json.dumps(record, sort_keys=True) + "\n")


def load_leads(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return list(data.get("leads", []))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PROMPT#10 Contact Resolver smoke")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run without live search")
    parser.add_argument("--lead-json", type=Path, default=PROMPT10_SAMPLE_INPUT_PATH)
    parser.add_argument("--max-leads", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    leads = load_leads(args.lead_json)
    result = resolve_contacts_for_leads(
        leads,
        max_leads=args.max_leads,
        dry_run=True,
    )
    result["input_source_path"] = str(args.lead_json)
    result["input_source_kind"] = "prompt10_dry_run_fixture"
    write_json(DRY_RUN_OUTPUT_PATH, result)
    log_safe(
        "dry_run",
        input=str(args.lead_json),
        output=str(DRY_RUN_OUTPUT_PATH),
        requested_leads=result["requested_leads"],
        resolved_count=result["resolved_count"],
        live_web_search_enabled=result["live_web_search_enabled"],
        sending_enabled=result["sending_enabled"],
    )
    if result["sending_enabled"]:
        print("ERROR: Contact Resolver smoke unexpectedly enabled sending.", file=sys.stderr)
        return 1
    print(f"DRY-RUN OK: wrote {DRY_RUN_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

