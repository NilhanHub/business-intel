"""PROMPT#11 live Contact Resolver smoke runner."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sl_trigger_leads.tools.contact_resolver_tools import (  # noqa: E402
    DEFAULT_SEARCH_BUDGET,
    resolve_contacts_for_leads,
)

LOG_PATH = ROOT / "logs" / "PROMPT#11_live_contact_resolver.log"
RESULTS_PATH = ROOT / "outputs" / "PROMPT#11_live_contact_resolver_results.json"
TRACE_PATH = ROOT / "outputs" / "PROMPT#11_live_contact_resolver_search_trace.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_safe(event: str, **fields: Any) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": utc_now(), "event": event, **fields}
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_lead(company: str, lead_url: str) -> dict[str, Any]:
    return {
        "company": company,
        "trigger": "QE Engineer - API & Integration",
        "evidence_url": lead_url,
        "source": "itpro.lk",
        "fetched_at": "2026-04-26",
        "score": None,
        "verdict": "Contact now",
        "onebt_fit": [
            "Staff Augmentation / Delivery Capacity",
            "Integrations / API / Middleware",
            "QA / Test Automation",
        ],
        "opportunity_bucket_primary": "Staff Augmentation / Delivery Capacity",
        "opportunity_bucket_secondary": [
            "Integrations / API / Middleware",
            "QA / Test Automation",
        ],
        "outreach_angle": "Resolve the best engineering or QA buyer/contact route for this hiring signal.",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PROMPT#11 live Contact Resolver smoke")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Run live public search mode")
    mode.add_argument("--dry-run", action="store_true", help="Run dry-run mode")
    parser.add_argument("--company", default="Vs One World (Pvt) Ltd")
    parser.add_argument(
        "--lead-url",
        default="https://itpro.lk/job/13609/qe-engineer-api-integration-at-vs-one-world-pvt-ltd/",
    )
    parser.add_argument("--max-leads", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    dry_run = bool(args.dry_run)
    lead = build_lead(args.company, args.lead_url)
    result = resolve_contacts_for_leads(
        [lead],
        max_leads=args.max_leads,
        dry_run=dry_run,
    )
    result["smoke_mode"] = "dry-run" if dry_run else "live"
    result["company_tested"] = args.company
    write_json(RESULTS_PATH, result)

    trace = {
        "created_at": utc_now(),
        "company_tested": args.company,
        "live_web_search_enabled": result.get("live_web_search_enabled"),
        "search_provider": result.get("search_provider"),
        "compact_output": result.get("compact_output"),
        "budgets": DEFAULT_SEARCH_BUDGET,
        "results": [
            {
                "company": item.get("company"),
                "best_contact_route": item.get("best_contact_route"),
                "search_summary": item.get("search_summary"),
                "search_trace": item.get("search_trace"),
            }
            for item in result.get("results", [])
        ],
    }
    write_json(TRACE_PATH, trace)

    best_route = None
    if result.get("results"):
        best_route = result["results"][0].get("best_contact_route")
    log_safe(
        "live_smoke" if not dry_run else "dry_run_smoke",
        company=args.company,
        output=str(RESULTS_PATH),
        trace=str(TRACE_PATH),
        live_web_search_enabled=result.get("live_web_search_enabled"),
        search_provider=result.get("search_provider"),
        best_route_type=best_route.get("type") if best_route else None,
        best_route_confidence=best_route.get("confidence") if best_route else None,
        sending_enabled=result.get("sending_enabled"),
    )

    if not dry_run and not result.get("live_web_search_enabled"):
        print("LIVE SMOKE FAILED: live web search was not enabled.", file=sys.stderr)
        return 1
    if not best_route or best_route.get("type") == "no_contact_found":
        print("LIVE SMOKE FAILED: no practical contact route found.", file=sys.stderr)
        return 1
    print(
        "LIVE SMOKE OK: "
        f"provider={result.get('search_provider')} "
        f"route={best_route.get('type')} "
        f"confidence={best_route.get('confidence')} "
        f"wrote={RESULTS_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
