"""PROMPT#12 Contact Resolver compact-output smoke.

This smoke uses the real latest opportunity-analysis leads and live resolver
mode. Static strings are used only for pure URL-normalization checks.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sl_trigger_leads.tools.contact_resolver_tools import (  # noqa: E402
    refuse_contact_resolver_sending,
    resolve_latest_contact_routes,
)
from sl_trigger_leads.tools.live_contact_search_tools import normalize_public_url  # noqa: E402

LOG_PATH = ROOT / "logs" / "PROMPT#12_contact_resolver_output_fix.log"
COMPACT_OUTPUT_PATH = ROOT / "outputs" / "PROMPT#12_contact_resolver_compact_output.json"
TRACE_PATH = ROOT / "outputs" / "PROMPT#12_contact_resolver_search_trace.json"


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


def flatten_trace(result: dict[str, Any]) -> dict[str, Any]:
    companies: list[dict[str, Any]] = []
    for item in result.get("results", []):
        summary = item.get("search_summary") or {}
        trace = item.get("search_trace") or []
        resolution = next((entry for entry in trace if entry.get("type") == "resolution_summary"), {})
        companies.append(
            {
                "company": item.get("company"),
                "signal_count": item.get("signal_count"),
                "primary_bucket": item.get("opportunity_bucket_primary"),
                "best_route": item.get("best_contact_route"),
                "queries_attempted": summary.get("queries_attempted", []),
                "urls_fetched": summary.get("sources_checked", []),
                "emails_extracted": resolution.get("emails_extracted", []),
                "named_roles_attempted": summary.get("named_roles_attempted", []),
                "named_person_search_attempted": summary.get("named_person_search_attempted"),
                "why_final_route_chosen": resolution.get("why_final_route_chosen"),
                "generic_fallback_used": resolution.get("generic_fallback_used"),
                "generic_fallback_reason": resolution.get("generic_fallback_reason"),
            }
        )
    return {
        "created_at": utc_now(),
        "live_web_search_enabled": result.get("live_web_search_enabled"),
        "search_provider": result.get("search_provider"),
        "companies": companies,
    }


def run_checks(result: dict[str, Any], url_checks: dict[str, str | None]) -> dict[str, bool]:
    compact_output = result.get("compact_output") or ""
    results = result.get("results") or []
    generic_routes = [
        item
        for item in results
        if (item.get("best_contact_route") or {}).get("type") == "generic_company"
    ]
    return {
        "url_normalization_works": url_checks == {
            "www.innovay.com/": "https://www.innovay.com/",
            "vsoneworld.com/contact": "https://vsoneworld.com/contact",
            "https://www.vsoneworld.com/contact": "https://www.vsoneworld.com/contact",
        },
        "compact_output_produced": compact_output.startswith("Contact routes found:")
        and "| Company |" in compact_output
        and "Do-not-claim" not in compact_output
        and len(compact_output.splitlines()) <= 12,
        "duplicate_companies_grouped": any(int(item.get("signal_count") or 1) > 1 for item in results),
        "generic_email_only_as_fallback": all(
            (item.get("search_summary") or {}).get("generic_fallback_after_named_search")
            for item in generic_routes
        ),
        "named_person_search_attempts_recorded": all(
            (item.get("search_summary") or {}).get("named_person_search_attempted")
            and (item.get("search_summary") or {}).get("named_roles_attempted")
            for item in results
        ),
        "low_fit_watch_not_primary_bucket": all(
            item.get("opportunity_bucket_primary") != "Low Fit / Watch"
            for item in results
        ),
        "no_fake_contact_result_emitted": not result.get("dry_run")
        and result.get("input_source_kind") == "latest_opportunity_analysis"
        and "fixture_note" not in json.dumps(result).lower()
        and "prompt10_dry_run_fixture" not in json.dumps(result).lower(),
        "sending_remains_locked": result.get("sending_enabled") is False
        and refuse_contact_resolver_sending("can you send these emails?")["sending_enabled"] is False,
        "detailed_trace_written": TRACE_PATH.is_file(),
        "adk_web_default_not_verbose": "compliance_notes" not in compact_output
        and "do_not_claim" not in compact_output.lower()
        and len(compact_output.splitlines()) <= 12,
    }


def main() -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOG_PATH.exists():
        LOG_PATH.unlink()

    url_checks = {
        "www.innovay.com/": normalize_public_url("www.innovay.com/"),
        "vsoneworld.com/contact": normalize_public_url("vsoneworld.com/contact"),
        "https://www.vsoneworld.com/contact": normalize_public_url("https://www.vsoneworld.com/contact"),
    }
    log_safe("url_normalization", checks=url_checks)

    result = resolve_latest_contact_routes(max_leads=3, dry_run=False)
    trace = flatten_trace(result)
    write_json(TRACE_PATH, trace)
    checks = run_checks(result, url_checks)
    payload = {
        "created_at": utc_now(),
        "checks": checks,
        "url_normalization": url_checks,
        "compact_output": result.get("compact_output"),
        "result": result,
        "sending_refusal": refuse_contact_resolver_sending("can you send these emails?"),
    }
    write_json(COMPACT_OUTPUT_PATH, payload)

    passed = all(checks.values())
    log_safe(
        "prompt12_smoke",
        passed=passed,
        live_web_search_enabled=result.get("live_web_search_enabled"),
        search_provider=result.get("search_provider"),
        resolved_count=result.get("resolved_count"),
        company_group_count=result.get("company_group_count"),
        compact_output_lines=len((result.get("compact_output") or "").splitlines()),
        output=str(COMPACT_OUTPUT_PATH),
        trace=str(TRACE_PATH),
        failed_checks=[key for key, value in checks.items() if not value],
    )
    print(result.get("compact_output") or "NO COMPACT OUTPUT")
    if not passed:
        print("PROMPT#12 SMOKE FAILED: " + ", ".join(key for key, value in checks.items() if not value), file=sys.stderr)
        return 1
    print(f"PROMPT#12 SMOKE OK: wrote={COMPACT_OUTPUT_PATH} trace={TRACE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
