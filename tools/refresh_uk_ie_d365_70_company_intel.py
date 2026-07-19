"""Refresh weak UK/IE D365 company evidence with the existing live search lane.

This command is deliberately narrow: it reads the consolidation refresh queue,
runs exactly one grounded search per queued company, follows public source links,
and records direct, live source candidates.  It does not discover new accounts,
send outreach, or mutate CRM/Sheets.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from uk_ie_d365_leads.tools.lead_tools import (
    SearchResult,
    fetch_sources_for_results,
    find_uk_ie_d365_leads,
    require_google_project,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = (ROOT / "Evidence").resolve()
DEFAULT_QUEUE = (
    EVIDENCE_ROOT / "UK_IE_D365_70_COMPANY_INTELLIGENCE_20260719_ADK_REFRESH_QUEUE.json"
)
DEFAULT_PROJECT = "business-intel-123"
DEFAULT_ACCOUNT = "codex-key-power-proof-sa@business-intel-123.iam.gserviceaccount.com"

SOURCE_URL_OVERRIDES = {
    "Charterhouse Holdings": "https://www.medius.com/resources/case-studies/charterhouse-holdings/",
    "Synergy Technology": "https://synergytechnology.co.uk/solutions/microsoft-dynamics-365-business-central/",
    "Tourism NI": "https://www.codec.uk/client-success-stories/tourism-northern-ireland",
}

QUERY_OVERRIDES = {
    "Biffa Group": "Biffa Dynamics 365",
    "Charterhouse Holdings": "Charterhouse Holdings Microsoft D365 ecommerce",
    "Clariness": "Clariness Microsoft Dynamics 365 sales marketing pharmaceutical",
    "Colorlites / THF Group": "Colorlites THF Group Dynamics 365 Business Central distribution manufacturing",
    "Hadley Group": "Hadley Group Microsoft Dynamics CRM rescue Xpedition",
    "Kepak Group": "Kepak Microsoft Dynamics 365 ERP rollout Ireland UK",
    "Simply Dynamics 365": "Simply Dynamics 365 Ireland growth hiring Business Solution talent",
    "Synergy Technology": "Synergy Technology Microsoft Dynamics 365 Business Central UK implementation support migration",
    "The Royal Society / Subscribe360": "Royal Society Subscribe360 Microsoft Dynamics 365 membership events",
    "Tourism NI": "Tourism NI Microsoft Dynamics 365 Customer Engagement Codec",
    "UK defence apparel manufacturer (unnamed in source)": (
        '"defence apparel manufacturer" "Dynamics 365 Business Central" "50%"'
    ),
    "Uniphar Medtech": "Uniphar Medtech Dynamics 365 Business Central ERP Support Specialist Dublin",
    "Willmott Dixon": "Willmott Dixon Dynamics 365 Sales Finance payment proposals bank reconciliations",
}

MICROSOFT_TERMS = (
    "dynamics 365",
    "d365",
    "business central",
    "dynamics crm",
    "power platform",
    "dataverse",
)
CONCRETE_TERMS = (
    "implement",
    "rollout",
    "rolling out",
    "migrat",
    "upgrade",
    "support",
    "hiring",
    "recruit",
    "automate",
    "integrat",  # codespell:ignore - intentional stem for integrate/integration
    "rescue",
    "roadmap",
    "payment",
    "procurement",
    "finance",
    "manufactur",
    "customer engagement",
)


def evidence_path(path: str | Path, *, label: str) -> Path:
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(EVIDENCE_ROOT)
    except ValueError as exc:
        raise RuntimeError(
            f"{label} must stay within {EVIDENCE_ROOT}: {resolved}"
        ) from exc
    return resolved


def effective_model_name() -> str:
    return (
        os.environ.get("D365_GOOGLE_MODEL", "gemini-2.5-flash").strip()
        or "gemini-2.5-flash"
    )


def error_details(exc: Exception) -> dict[str, str]:
    return {"type": type(exc).__name__, "message": str(exc)[:500]}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--required-project", default=DEFAULT_PROJECT)
    p.add_argument("--gcloud-account", default=DEFAULT_ACCOUNT)
    p.add_argument("--max-results", type=int, default=10)
    p.add_argument(
        "--supplement-existing",
        type=Path,
        default=None,
        help="Fetch only saved source URLs for rows without a direct live source; makes no model call.",
    )
    return p


def normalized_company_tokens(company_name: str) -> list[str]:
    ignored = {
        "group",
        "holdings",
        "limited",
        "ltd",
        "plc",
        "the",
        "source",
        "unnamed",
        "in",
    }
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in company_name)
    return [
        token for token in cleaned.split() if len(token) > 2 and token not in ignored
    ]


def source_score(company_name: str, source: dict[str, Any]) -> int:
    final_url = str(source.get("final_url") or "")
    host = urlparse(final_url).netloc.lower()
    text = " ".join(
        str(source.get(key) or "")
        for key in ("title", "snippet", "text_excerpt", "final_url")
    ).lower()
    score = 0
    if source.get("verified_live") and source.get("source_fetch_status") == "fetched":
        score += 50
    if final_url and "grounding-api-redirect" not in final_url:
        score += 25
    if "microsoft.com" in host:
        score += 20
    if any(term in text for term in MICROSOFT_TERMS):
        score += 25
    score += min(20, 4 * sum(term in text for term in CONCRETE_TERMS))
    tokens = normalized_company_tokens(company_name)
    score += min(20, 10 * sum(token in text for token in tokens))
    if any(
        host.endswith(domain)
        for domain in ("linkedin.com", "facebook.com", "instagram.com")
    ):
        score -= 50
    return score


def live_sources(result: dict[str, Any], company_name: str) -> list[dict[str, Any]]:
    ledger = {
        str(item.get("url") or ""): item
        for item in result.get("raw_result_ledger") or []
    }
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fetch in result.get("source_fetches") or []:
        final_url = str(fetch.get("final_url") or "")
        if not final_url or final_url in seen:
            continue
        seen.add(final_url)
        raw = ledger.get(str(fetch.get("url") or ""), {})
        row = {
            "title": raw.get("title"),
            "snippet": raw.get("snippet"),
            "original_url": fetch.get("url"),
            "final_url": final_url,
            "status_code": fetch.get("status_code"),
            "content_type": fetch.get("content_type"),
            "source_fetch_status": fetch.get("source_fetch_status"),
            "verified_live": bool(fetch.get("verified_live")),
            "fetched_at": fetch.get("fetched_at"),
            "text_excerpt": fetch.get("text_excerpt"),
            "error": fetch.get("error"),
        }
        row["source_score"] = source_score(company_name, row)
        rows.append(row)
    return sorted(rows, key=lambda item: item["source_score"], reverse=True)


def refresh_company(row: dict[str, Any], *, max_results: int) -> dict[str, Any]:
    company_name = str(row["canonical_company_name"])
    query = QUERY_OVERRIDES.get(company_name, f"{company_name} Microsoft Dynamics 365")
    result = find_uk_ie_d365_leads(
        query=query,
        max_results=max_results,
        provider_name="google_grounding",
        max_live_requests=1,
        include_rejected=True,
        source_fetch=True,
        source_fetch_max_urls=max_results,
        parse_pdfs=True,
    )
    sources = live_sources(result, company_name)
    best_live_source = next(
        (source for source in sources if source.get("verified_live") is True), None
    )
    return {
        "canonical_company_name": company_name,
        "query": query,
        "previous_evidence": row.get("specific_evidence"),
        "previous_evidence_url": row.get("evidence_url"),
        "previous_refresh_reasons": row.get("refresh_reasons") or [],
        "search_status": result.get("status"),
        "run_id": result.get("run_id"),
        "provider": result.get("provider"),
        "provider_errors": result.get("provider_errors") or [],
        "live_sources": sources,
        "best_live_source": best_live_source,
        "raw_search_result": result,
    }


def refresh_companies(
    companies: list[dict[str, Any]], *, max_results: int
) -> list[dict[str, Any]]:
    refreshed: list[dict[str, Any]] = []
    for row in companies:
        try:
            refreshed.append(refresh_company(row, max_results=max_results))
        except Exception as exc:
            company_name = str(row.get("canonical_company_name") or "")
            refreshed.append(
                {
                    "canonical_company_name": company_name,
                    "query": QUERY_OVERRIDES.get(
                        company_name, f"{company_name} Microsoft Dynamics 365"
                    ),
                    "previous_evidence": row.get("specific_evidence"),
                    "previous_evidence_url": row.get("evidence_url"),
                    "previous_refresh_reasons": row.get("refresh_reasons") or [],
                    "search_status": "refresh_error",
                    "live_sources": [],
                    "best_live_source": None,
                    "error": error_details(exc),
                }
            )
    return refreshed


def supplement_missing_sources(existing: dict[str, Any]) -> dict[str, Any]:
    """Follow the already-saved evidence URL for unresolved rows without searching again."""
    supplemented = json.loads(json.dumps(existing))
    for row in supplemented.get("companies") or []:
        best_existing = row.get("best_live_source")
        if (
            isinstance(best_existing, dict)
            and best_existing.get("verified_live") is True
        ):
            continue
        company_name = str(row.get("canonical_company_name") or "")
        previous_url = SOURCE_URL_OVERRIDES.get(
            company_name, str(row.get("previous_evidence_url") or "")
        )
        if not previous_url:
            continue
        search_result = SearchResult(
            title=str(row.get("canonical_company_name") or ""),
            url=previous_url,
            snippet=str(row.get("previous_evidence") or ""),
            source="saved_evidence_fallback",
        )
        sources = []
        try:
            for fetch in fetch_sources_for_results(
                [search_result], max_urls=1, parse_pdfs=True
            ):
                source = {
                    "title": search_result.title,
                    "snippet": search_result.snippet,
                    "original_url": fetch.get("url"),
                    "final_url": fetch.get("final_url"),
                    "status_code": fetch.get("status_code"),
                    "content_type": fetch.get("content_type"),
                    "source_fetch_status": fetch.get("source_fetch_status"),
                    "verified_live": bool(fetch.get("verified_live")),
                    "fetched_at": fetch.get("fetched_at"),
                    "text_excerpt": fetch.get("text_excerpt"),
                    "error": fetch.get("error"),
                    "fallback_fetch": True,
                }
                source["source_score"] = source_score(
                    row["canonical_company_name"], source
                )
                sources.append(source)
        except Exception as exc:
            row["fallback_live_sources"] = []
            row["supplement_status"] = "fetch_error"
            row["supplement_error"] = error_details(exc)
            continue
        row["fallback_live_sources"] = sources
        if sources:
            row["live_sources"] = sorted(
                [*(row.get("live_sources") or []), *sources],
                key=lambda item: item["source_score"],
                reverse=True,
            )
            row["best_live_source"] = next(
                (
                    source
                    for source in row["live_sources"]
                    if source.get("verified_live") is True
                ),
                None,
            )
            row["supplement_status"] = (
                "verified" if row["best_live_source"] else "unverified"
            )
    supplemented["supplemented_at"] = (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    supplemented["supplement_policy"] = (
        "one direct fetch of the previously saved source URL; no model call and no retry"
    )
    supplemented["best_direct_live_source_count"] = sum(
        1
        for row in supplemented.get("companies") or []
        if row.get("best_live_source") and row["best_live_source"].get("verified_live")
    )
    return supplemented


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.supplement_existing:
        supplement_path = evidence_path(
            args.supplement_existing, label="Existing refresh artifact"
        )
        existing = json.loads(supplement_path.read_text(encoding="utf-8"))
        output = supplement_missing_sources(existing)
        refreshed = output.get("companies") or []
        direct_count = int(output.get("best_direct_live_source_count") or 0)
    else:
        queue_path = evidence_path(args.queue, label="Refresh queue")
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        companies = queue.get("companies") or []
        names = [str(item.get("canonical_company_name") or "") for item in companies]
        missing_queries = sorted(set(names) - set(QUERY_OVERRIDES))
        if missing_queries:
            raise RuntimeError(f"Missing guarded query overrides: {missing_queries}")

        os.environ["D365_GOOGLE_PROJECT"] = args.required_project
        os.environ["GOOGLE_CLOUD_PROJECT"] = args.required_project
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
        if args.gcloud_account:
            os.environ["D365_GCLOUD_ACCOUNT"] = args.gcloud_account
        readiness = require_google_project(args.required_project)

        started_at = (
            datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        refreshed = refresh_companies(companies, max_results=args.max_results)
        finished_at = (
            datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        direct_count = sum(
            1
            for row in refreshed
            if row.get("best_live_source")
            and row["best_live_source"].get("verified_live")
        )
        output = {
            "artifact_type": "uk_ie_d365_70_company_targeted_adk_refresh",
            "started_at": started_at,
            "finished_at": finished_at,
            "required_project": args.required_project,
            "provider": "google_grounding",
            "model": effective_model_name(),
            "request_policy": "exactly one grounded search per queued company; no automatic retry",
            "credential_mode": "existing gcloud account via short-lived access token",
            "credential_account": args.gcloud_account,
            "readiness": readiness,
            "company_count": len(refreshed),
            "best_direct_live_source_count": direct_count,
            "companies": refreshed,
        }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = (
        args.output or EVIDENCE_ROOT / f"UK_IE_D365_70_COMPANY_ADK_REFRESH_{stamp}.json"
    )
    output_path = evidence_path(output_path, label="Refresh output")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(output_path),
                "company_count": len(refreshed),
                "best_direct_live_source_count": direct_count,
                "companies_without_live_source": [
                    row["canonical_company_name"]
                    for row in refreshed
                    if not row.get("best_live_source")
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
