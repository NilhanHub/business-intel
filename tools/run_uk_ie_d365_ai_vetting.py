"""Run AI opportunity vetting over saved UK/IE D365 search evidence.

This command is local/evidence-only. It does not send email, use Gmail, deploy,
or mutate deterministic classifier rules. Live AI requires --live-ai.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uk_ie_d365_leads.tools import lead_tools
from uk_ie_d365_leads.tools.opportunity_vetting_tools import (
    DEFAULT_OUTPUT_BASENAME,
    DETERMINISTIC_AUDIT_BASENAME,
    EVIDENCE_DIR,
    FRESH_LEADS_BASENAME,
    build_fresh_leads_outputs,
    build_vetting_package,
    merge_vetting_outputs,
    require_live_vetting_for_final_pack,
)

TARGETED_SECOND_PASS_QUERIES = [
    {"signal_class": "named_customer_case_study", "query": '"Dynamics 365" "case study" "United Kingdom" -jobs -careers -tender'},
    {"signal_class": "named_customer_case_study", "query": '"Business Central" "case study" "United Kingdom" -jobs -careers -tender'},
    {"signal_class": "named_customer_case_study", "query": '"Dynamics 365 Finance" "case study" UK company -jobs -careers'},
    {"signal_class": "named_customer_case_study", "query": '"Dynamics 365 Supply Chain" "case study" UK manufacturer -jobs -careers'},
    {"signal_class": "named_customer_case_study", "query": '"Dynamics 365 Customer Service" "case study" Ireland -jobs -careers'},
    {"signal_class": "implementation_rollout", "query": '"implemented Dynamics 365" "UK" "customer" -jobs -careers -tender'},
    {"signal_class": "implementation_rollout", "query": '"selected Microsoft Dynamics 365" "United Kingdom" company -jobs -careers'},
    {"signal_class": "implementation_rollout", "query": '"rolled out Dynamics 365" UK company -jobs -careers'},
    {"signal_class": "migration_upgrade", "query": '"migrated to Dynamics 365" UK company -jobs -careers'},
    {"signal_class": "migration_upgrade", "query": '"Dynamics 365 upgrade" UK "case study" -jobs -careers'},
    {"signal_class": "support_pain", "query": '"Dynamics 365" "support partner" UK company -jobs -careers'},
    {"signal_class": "support_pain", "query": '"Dynamics 365" "post go-live" UK company -jobs -careers'},
    {"signal_class": "power_platform_d365", "query": '"Power Platform" "Dynamics 365" "case study" UK company -jobs -careers'},
    {"signal_class": "direct_employer_hiring", "query": 'site:*.co.uk/careers "Dynamics 365" "Business Central" -recruiter -agency'},
    {"signal_class": "direct_employer_hiring", "query": 'site:*.ie/careers "Dynamics 365" "Business Central" -recruiter -agency'},
]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--evidence-file",
        default=str(EVIDENCE_DIR / "UK_IE_D365_FRESH_SEARCH_20260603.json"),
        help="Saved search evidence JSON to vet.",
    )
    p.add_argument("--output-dir", default=str(EVIDENCE_DIR), help="Directory for vetting artifacts.")
    p.add_argument("--run-search", action="store_true", help="Run a fresh include_rejected=True search before vetting.")
    p.add_argument("--targeted-second-pass", action="store_true", help="Use named-account second-pass queries for fresh search.")
    p.add_argument("--search-max-results", type=int, default=10)
    p.add_argument("--max-live-requests", type=int, default=25)
    p.add_argument("--max-candidates", type=int, default=40)
    p.add_argument("--candidate-offset", type=int, default=0)
    p.add_argument("--max-followup-searches", type=int, default=2)
    p.add_argument("--max-source-fetches", type=int, default=3)
    p.add_argument("--source-fetch-max-urls", type=int, default=lead_tools.SOURCE_FETCH_DEFAULT_MAX_URLS)
    p.add_argument("--disable-early-source-fetch", action="store_true", help="Skip source-page fetching during fresh search.")
    p.add_argument("--parse-pdfs", action="store_true", help="Fetch and parse public PDF sources instead of skipping PDF URLs.")
    p.add_argument("--retry-source-errors", default=None, help="Retry a SOURCE_FETCH_ERRORS, cleanup queue, or shortage JSON artifact, then exit.")
    p.add_argument("--use-shortage-report", default=None, help="Use a previous shortage report JSON to seed the next query plan.")
    p.add_argument("--query-pack", choices=["default", "support", "migration", "case-study", "pdf", "all"], default="default")
    p.add_argument("--fanout-max-providers", type=int, default=lead_tools.FANOUT_DEFAULT_MAX_PROVIDERS)
    p.add_argument("--fanout-queries-per-provider", type=int, default=lead_tools.FANOUT_DEFAULT_QUERIES_PER_PROVIDER)
    p.add_argument("--fanout-results-per-query", type=int, default=lead_tools.FANOUT_DEFAULT_RESULTS_PER_QUERY)
    p.add_argument("--fanout-max-raw-results", type=int, default=lead_tools.FANOUT_DEFAULT_MAX_RAW_RESULTS)
    p.add_argument("--model", default=None)
    p.add_argument("--live-ai", action="store_true", help="Call Gemini/Agent Platform via the Vertex AI API path for vetting.")
    p.add_argument("--live-followup", action="store_true", help="Run bounded Google grounding follow-up searches.")
    p.add_argument("--provider-name", default="google_grounding")
    p.add_argument("--required-project", default=None, help="Abort live Google work unless this is the effective project.")
    p.add_argument("--vetting-output-basename", default=None, help="Basename for raw AI vetting artifacts.")
    p.add_argument("--final-lead-count", type=int, default=12)
    p.add_argument("--final-output-basename", default=None, help="Basename for final fresh-leads artifacts.")
    p.add_argument("--deterministic-audit-basename", default=None, help="Basename for deterministic reject audit artifacts.")
    p.add_argument("--skip-final-pack", action="store_true", help="Only write raw vetting artifacts.")
    p.add_argument(
        "--merge-vetting-files",
        nargs="+",
        default=None,
        help="Merge completed non-overlapping vetting JSON batches before final curation.",
    )
    return p


def dry_run_reviewer(record: dict[str, Any], stage: str, request_index: int):
    status = "source_cleanup_needed" if record.get("deterministic_flags") or record.get("missing_verification_points") else "provisional_contact_now"
    response = {
        "lead_status": status,
        "signal_strength": "emerging" if status == "source_cleanup_needed" else "promising",
        "signal_type": record.get("signal_type") or "d365_public_evidence",
        "evidence_used": record.get("evidence_snippets") or record.get("evidence_urls") or [],
        "evidence_gaps": record.get("missing_verification_points") or record.get("deterministic_flags") or [],
        "opportunity_signal": record.get("signal_summary") or "Saved D365 candidate requires AI vetting.",
        "why_this_matters_to_1bt": "Dry-run placeholder: live AI was not enabled.",
        "commercial_opening": "Dry-run placeholder: rerun with --live-ai for production wording.",
        "value_of_signal": "Dry-run placeholder.",
        "intelligence_reading": "Dry-run placeholder.",
        "board_relevance": "Dry-run placeholder.",
        "contact_target_roles": record.get("suggested_contact_roles") or [],
        "do_not_claim_notes": [
            "Do not claim live AI approval from dry-run output.",
            "Do not claim facts beyond saved evidence.",
        ],
        "remaining_uncertainty": record.get("missing_verification_points") or [],
        "final_rejection_reason": "",
        "needs_follow_up": status == "source_cleanup_needed",
    }
    return json.dumps(response), {"prompt_token_count": 0, "candidates_token_count": 0, "total_token_count": 0}, "dry-run"


def make_followup_search(provider_name: str):
    provider = lead_tools.get_search_provider(provider_name)
    if not provider.configured:
        raise SystemExit(provider.unavailable_reason or "Search provider is not configured.")

    def search(query: str, candidate: dict[str, Any], review: dict[str, Any]):
        return provider.search_web(query, limit=3)

    return search


def make_source_fetch(*, parse_pdfs: bool = False):
    fetcher = lead_tools.SourceFetcher(parse_pdfs=parse_pdfs)

    def fetch_public_source(url: str, candidate: dict[str, Any], review: dict[str, Any]):
        return fetcher.fetch(
            url,
            provider=str(candidate.get("source_provider") or "followup_source_fetch"),
            source_query=None,
        )

    return fetch_public_source


def run_fresh_search(args: argparse.Namespace) -> Path:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    shortage_report = load_json_file(args.use_shortage_report) if args.use_shortage_report else None
    if args.targeted_second_pass:
        artifact = run_targeted_search(args)
    else:
        artifact = lead_tools.find_uk_ie_d365_leads(
            max_results=args.search_max_results,
            max_live_requests=args.max_live_requests,
            include_rejected=True,
            provider_name=args.provider_name,
            source_fetch=not args.disable_early_source_fetch,
            fanout_max_providers=args.fanout_max_providers,
            fanout_queries_per_provider=args.fanout_queries_per_provider,
            fanout_results_per_query=args.fanout_results_per_query,
            fanout_max_raw_results=args.fanout_max_raw_results,
            source_fetch_max_urls=args.source_fetch_max_urls,
            parse_pdfs=args.parse_pdfs,
            query_pack=args.query_pack,
            shortage_report=shortage_report,
        )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    prefix = (
        "UK_IE_D365_FANOUT_SEARCH_RUN"
        if str(artifact.get("provider") or "").lower() == lead_tools.FANOUT_PROVIDER_NAME
        else "UK_IE_D365_AI_VETTING_RAW_SEARCH"
    )
    path = output_dir / f"{prefix}_{timestamp}.json"
    path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    write_query_plan_artifact(artifact, output_dir=output_dir, timestamp=timestamp, args=args)
    if artifact.get("provider_budget") or artifact.get("provider_readiness"):
        provider_audit = {
            "artifact_type": "uk_ie_d365_provider_audit",
            "generated_at": datetime.now(UTC).isoformat(),
            "provider": artifact.get("provider"),
            "run_id": artifact.get("run_id"),
            "provider_budget": artifact.get("provider_budget") or {},
            "provider_readiness": artifact.get("provider_readiness") or {},
            "provider_errors": artifact.get("provider_errors") or [],
            "duplicate_raw_result_count": artifact.get("duplicate_raw_result_count", 0),
        }
        (output_dir / f"UK_IE_D365_PROVIDER_AUDIT_{timestamp}.json").write_text(
            json.dumps(provider_audit, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if artifact.get("source_fetches"):
        (output_dir / f"UK_IE_D365_SOURCE_FETCHES_{timestamp}.json").write_text(
            json.dumps(artifact.get("source_fetches"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if artifact.get("source_fetch_errors"):
        (output_dir / f"UK_IE_D365_SOURCE_FETCH_ERRORS_{timestamp}.json").write_text(
            json.dumps(artifact.get("source_fetch_errors"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    memory = lead_tools.build_local_discovery_memory(output_dir)
    (output_dir / f"UK_IE_D365_DISCOVERY_MEMORY_{timestamp}.json").write_text(
        json.dumps(memory, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def write_query_plan_artifact(
    artifact: dict[str, Any],
    *,
    output_dir: Path,
    timestamp: str,
    args: argparse.Namespace,
) -> Path:
    query_plan = {
        "artifact_type": "uk_ie_d365_query_plan",
        "version": lead_tools.QUERY_PACK_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": artifact.get("run_id"),
        "provider": artifact.get("provider"),
        "query_pack": args.query_pack,
        "shortage_report_source": args.use_shortage_report,
        "parse_pdfs": bool(args.parse_pdfs),
        "queries_planned": artifact.get("queries_planned") or [],
        "query_plan": artifact.get("query_plan") or [],
        "queries_run": artifact.get("queries_run") or [],
    }
    path = output_dir / f"UK_IE_D365_QUERY_PLAN_{timestamp}.json"
    path.write_text(json.dumps(query_plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_json_file(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_source_retry(args: argparse.Namespace) -> dict[str, str]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = load_json_file(args.retry_source_errors)
    retry = lead_tools.retry_source_fetches_from_payload(
        payload,
        parse_pdfs=args.parse_pdfs,
        max_urls=args.source_fetch_max_urls,
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"UK_IE_D365_SOURCE_RETRY_RUN_{timestamp}.json"
    path.write_text(json.dumps(retry, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"source_retry_run": str(path)}


def write_provider_scorecard_artifact(
    *,
    raw_search: dict[str, Any],
    output_dir: Path,
    final_output: dict[str, Any] | None = None,
) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    scorecard = lead_tools.build_provider_scorecard(raw_search, final_output=final_output)
    path = output_dir / f"UK_IE_D365_PROVIDER_SCORECARD_{timestamp}.json"
    path.write_text(json.dumps(scorecard, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def run_targeted_search(args: argparse.Namespace) -> dict[str, Any]:
    provider = lead_tools.get_search_provider(args.provider_name)
    if not provider.configured:
        raise SystemExit(provider.unavailable_reason or "Search provider is not configured.")
    started = datetime.now(UTC).isoformat()
    raw_results: list[lead_tools.SearchResult] = []
    errors = []
    live_requests_made = 0
    max_requests = max(1, min(int(args.max_live_requests or 5), len(TARGETED_SECOND_PASS_QUERIES)))
    per_query_limit = max(1, min(int(args.search_max_results or 10), 10))
    for query_item in TARGETED_SECOND_PASS_QUERIES[:max_requests]:
        try:
            live_requests_made += 1
            results = provider.search_web(query_item["query"], limit=per_query_limit)
            raw_results.extend(
                lead_tools.SearchResult(
                    title=result.title,
                    url=result.url,
                    snippet=result.snippet,
                    source=result.source,
                    published_date=result.published_date,
                    signal_class=query_item["signal_class"],
                    source_url_type=result.source_url_type,
                    source_query=query_item["query"],
                    source_query_group=query_item["signal_class"],
                )
                for result in results
            )
        except Exception as exc:
            errors.append({"query": query_item["query"], "error": str(exc)[:500]})
    extraction = lead_tools.extract_d365_leads(
        raw_results,
        max_results=max(1, min(int(args.search_max_results or 24), 50)),
        include_rejected=True,
    )
    finished = datetime.now(UTC).isoformat()
    return {
        "status": "ok" if extraction["surfaced_leads"] else "no_verified_leads_found",
        "provider": provider.name,
        "audit_metadata": lead_tools.audit_metadata(
            search_provider=provider.name,
            live_search_run=live_requests_made > 0,
            live_request_count=live_requests_made,
            run_started_at=started,
            run_finished_at=finished,
        ),
        "queries_run": [item["query"] for item in TARGETED_SECOND_PASS_QUERIES[:live_requests_made]],
        "query_groups_run": [item["signal_class"] for item in TARGETED_SECOND_PASS_QUERIES[:live_requests_made]],
        "live_requests_made": live_requests_made,
        "provider_errors": errors,
        "leads": extraction["surfaced_leads"],
        "lead_count": len(extraction["surfaced_leads"]),
        "tier_counts": extraction["tier_counts"],
        "tier_a_leads": extraction["tier_a_leads"],
        "tier_b_provisional_leads": extraction["tier_b_provisional_leads"],
        "tier_c_watchlist_leads": extraction["tier_c_watchlist_leads"],
        "tier_d_rejected": extraction["tier_d_rejected"],
        "rejected_leads": extraction["rejected_leads"],
        "rejected_count": len(extraction["rejected_leads"]),
        "review_candidates": extraction.get("review_candidates", []),
        "hard_rejected_leads": extraction.get("hard_rejected_leads", []),
        "hard_rejected_count": len(extraction.get("hard_rejected_leads", [])),
        "fetched_at": started,
        "run_finished_at": finished,
    }


def enforce_required_project(args: argparse.Namespace) -> dict[str, Any]:
    if args.required_project:
        existing = os.environ.get("D365_GOOGLE_PROJECT")
        if existing and existing != args.required_project:
            raise SystemExit(
                f"D365_GOOGLE_PROJECT is {existing!r}, but --required-project is {args.required_project!r}."
            )
        os.environ["D365_GOOGLE_PROJECT"] = args.required_project
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", args.required_project)
    if args.live_ai or args.live_followup or args.run_search:
        try:
            return lead_tools.require_google_project(args.required_project)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
    return lead_tools.google_native_readiness()


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.retry_source_errors:
        print(json.dumps(run_source_retry(args), indent=2))
        return 0
    if args.live_followup and not args.live_ai:
        raise SystemExit("--live-followup requires --live-ai so follow-up evidence is re-vetted.")
    readiness = enforce_required_project(args)
    evidence_file = run_fresh_search(args) if args.run_search else Path(args.evidence_file)
    if args.merge_vetting_files:
        outputs = [load_json_file(path) for path in args.merge_vetting_files]
        package = merge_vetting_outputs(
            outputs,
            output_dir=Path(args.output_dir),
            output_basename=args.vetting_output_basename or DEFAULT_OUTPUT_BASENAME,
        )
    else:
        reviewer = None if args.live_ai else dry_run_reviewer
        followup_search = make_followup_search(args.provider_name) if args.live_followup else None
        source_fetch = make_source_fetch(parse_pdfs=args.parse_pdfs) if args.live_followup else None
        package = build_vetting_package(
            evidence_file=evidence_file,
            output_dir=Path(args.output_dir),
            output_basename=args.vetting_output_basename or DEFAULT_OUTPUT_BASENAME,
            candidate_offset=args.candidate_offset,
            max_candidates=args.max_candidates,
            max_followup_searches=args.max_followup_searches,
            max_source_fetches=args.max_source_fetches,
            model=args.model,
            reviewer_call=reviewer,
            followup_search_call=followup_search,
            source_fetch_call=source_fetch,
            command_log=[" ".join(sys.argv)],
        )
    artifacts = dict(package["artifacts"])
    if not args.skip_final_pack:
        try:
            require_live_vetting_for_final_pack(package["vetting_output"])
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        raw_search = json.loads(evidence_file.read_text(encoding="utf-8"))
        fresh_package = build_fresh_leads_outputs(
            vetting_output=package["vetting_output"],
            raw_search=raw_search,
            output_dir=Path(args.output_dir),
            final_count=args.final_lead_count,
            output_basename=args.final_output_basename or FRESH_LEADS_BASENAME,
            deterministic_audit_basename=args.deterministic_audit_basename or DETERMINISTIC_AUDIT_BASENAME,
            command_log=[" ".join(sys.argv), f"effective_project={readiness.get('effective_project')}"],
        )
        artifacts.update(fresh_package["artifacts"])
        scorecard_path = write_provider_scorecard_artifact(
            raw_search=raw_search,
            output_dir=Path(args.output_dir),
            final_output=fresh_package["final_output"],
        )
        artifacts["provider_scorecard"] = str(scorecard_path)
    else:
        raw_search = json.loads(evidence_file.read_text(encoding="utf-8"))
        scorecard_path = write_provider_scorecard_artifact(
            raw_search=raw_search,
            output_dir=Path(args.output_dir),
        )
        artifacts["provider_scorecard"] = str(scorecard_path)
    print(json.dumps(artifacts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
