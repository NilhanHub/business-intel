"""Local smoke for explicit multi-company Contact Resolver prompts."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sl_trigger_leads.tools.contact_resolver_tools import resolve_contact_routes_from_text  # noqa: E402

EVIDENCE_DIR = ROOT / "Evidence"
LOG_PATH = EVIDENCE_DIR / "CONTACT_RESOLVER_EXPLICIT_LEADS_LOCAL_TEST.log"
OUTPUT_PATH = EVIDENCE_DIR / "CONTACT_RESOLVER_EXPLICIT_LEADS_OUTPUT.json"
TRACE_PATH = EVIDENCE_DIR / "CONTACT_RESOLVER_EXPLICIT_LEADS_TRACE.json"
REPORT_PATH = EVIDENCE_DIR / "CONTACT_RESOLVER_EXPLICIT_LEADS_BUG_REPORT.md"

EXPLICIT_LEADS_TEXT = """Lead 1:
company_name: Vs One World (Pvt) Ltd
signal_summary: QE Engineer - API & Integration hiring signal
signal_source_url: https://itpro.lk/job/13609/qe-engineer-api-integration-at-vs-one-world-pvt-ltd/
service_bucket: Software Development
country: Sri Lanka

Lead 2:
company_name: WSO2
signal_summary: Enterprise software company; test whether resolver can find public/company contact routes.
signal_source_url: https://wso2.com/contact/
service_bucket: Software Development
country: Sri Lanka

Lead 3:
company_name: Microsoft
signal_summary: Large public technology company; test Hunter/domain/contact route behavior.
signal_source_url: https://www.microsoft.com/en-us/contactus
service_bucket: MS 365D
country: United States
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def log_safe(event: str, **fields: Any) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": utc_now(), "event": event, **fields}, sort_keys=True) + "\n")


def build_trace(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "created_at": utc_now(),
        "input_kind": "explicit_three_lead_text",
        "live_web_search_enabled": result.get("live_web_search_enabled"),
        "search_provider": result.get("search_provider"),
        "hunter_configured": result.get("hunter_configured"),
        "hunter_status": result.get("hunter_status"),
        "compact_output": result.get("compact_output"),
        "companies": [
            {
                "company": item.get("company"),
                "lead_evidence_url": item.get("lead_evidence_url"),
                "best_contact_route": item.get("best_contact_route"),
                "hunter_status": (item.get("search_summary") or {}).get("hunter_status"),
                "queries_attempted": (item.get("search_summary") or {}).get("queries_attempted"),
                "sources_checked": (item.get("search_summary") or {}).get("sources_checked"),
                "search_trace": item.get("search_trace"),
            }
            for item in result.get("results", [])
        ],
    }


def write_report(result: dict[str, Any], checks: dict[str, bool]) -> None:
    route_summaries = []
    for item in result.get("results", []):
        route = item.get("best_contact_route") or {}
        summary = item.get("search_summary") or {}
        route_summaries.append(
            f"- {item.get('company')}: route={route.get('type')} "
            f"confidence={route.get('confidence')} hunter={summary.get('hunter_status')} "
            f"evidence={route.get('evidence_urls') or [route.get('url')]}"
        )
    REPORT_PATH.write_text(
        "\n".join(
            [
                "# Contact Resolver Explicit Leads Bug Report",
                "",
                f"Created: {utc_now()}",
                "",
                "## Root Cause",
                "",
                "The Agent Runtime prompt contained explicit lead rows with field names such as "
                "`company_name`, `signal_summary`, and `signal_source_url`, while the resolver tools "
                "expected structured dictionaries with `company`, `trigger`, and `evidence_url`. "
                "Without an explicit text-ingestion tool or alias normalization, the model could pass "
                "a malformed single lead object and `normalize_lead()` fell back to `unknown`.",
                "",
                "## Fix",
                "",
                "- Added `resolve_contact_routes_from_text` for pasted lead blocks.",
                "- Added explicit field alias normalization for `company_name`, `signal_summary`, "
                "`signal_source_url`, and `service_bucket`.",
                "- Updated root and Contact Resolver instructions to route pasted lead rows to the wrapper.",
                "",
                "## Local Validation",
                "",
                f"- Checks passed: {all(checks.values())}",
                f"- Resolved count: {result.get('resolved_count')}",
                f"- Search provider: {result.get('search_provider')}",
                f"- Hunter configured: {result.get('hunter_configured')}",
                "",
                "## Routes",
                "",
                *route_summaries,
                "",
                "## Ready To Redeploy",
                "",
                "Yes, after reviewing these local validation artifacts. Deployment was not run.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    if LOG_PATH.exists():
        LOG_PATH.unlink()

    log_safe("explicit_leads_smoke_start")
    result = resolve_contact_routes_from_text(EXPLICIT_LEADS_TEXT, max_leads=3, dry_run=False)
    trace = build_trace(result)

    write_json(OUTPUT_PATH, result)
    write_json(TRACE_PATH, trace)

    companies = [item.get("company") for item in result.get("results", [])]
    checks = {
        "three_rows": result.get("resolved_count") == 3 and len(result.get("results", [])) == 3,
        "companies_preserved": companies == ["Vs One World (Pvt) Ltd", "WSO2", "Microsoft"],
        "no_unknown_company": all(str(company or "").lower() != "unknown" for company in companies),
        "hunter_status_per_row": all((item.get("search_summary") or {}).get("hunter_status") for item in result.get("results", [])),
        "best_route_or_not_found_per_row": all((item.get("best_contact_route") or {}).get("type") for item in result.get("results", [])),
        "confidence_per_row": all((item.get("best_contact_route") or {}).get("confidence") is not None for item in result.get("results", [])),
        "evidence_per_row": all(
            (item.get("best_contact_route") or {}).get("evidence_urls")
            or (item.get("best_contact_route") or {}).get("url")
            or item.get("lead_evidence_url")
            for item in result.get("results", [])
        ),
        "sending_locked": result.get("sending_enabled") is False,
        "no_guessed_emails": "inferred_pattern" not in json.dumps(result).lower(),
    }
    write_report(result, checks)
    log_safe(
        "explicit_leads_smoke_complete",
        passed=all(checks.values()),
        checks=checks,
        companies=companies,
        output=str(OUTPUT_PATH),
        trace=str(TRACE_PATH),
        report=str(REPORT_PATH),
        search_provider=result.get("search_provider"),
        hunter_configured=result.get("hunter_configured"),
        hunter_status=result.get("hunter_status"),
    )
    print(result.get("compact_output") or "NO COMPACT OUTPUT")
    print(f"checks={json.dumps(checks, sort_keys=True)}")
    print(f"output={OUTPUT_PATH}")
    print(f"trace={TRACE_PATH}")
    print(f"report={REPORT_PATH}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
