"""Check the D365 opportunity vetter against the saved 12-lead baseline.

This command is local/evidence-only. It does not run new lead discovery, send
email, use Gmail, deploy, use private LinkedIn, or build tender intelligence.
Live AI calls are allowed only when --live-ai is supplied and the Google project
guard passes.
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
from uk_ie_d365_leads.tools import opportunity_vetting_tools as vetting

DEFAULT_INPUT_PACK = vetting.EVIDENCE_DIR / "UK_IE_D365_USEFUL_LEADS_FRESH_20260612.json"
DEFAULT_SOURCE_CHECKS = vetting.EVIDENCE_DIR / "UK_IE_D365_USEFUL_LEADS_FRESH_20260612_SOURCE_CHECKS.json"
OUTPUT_PREFIX = "UK_IE_D365_VETTER_AGENT_CHECK"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-pack", default=str(DEFAULT_INPUT_PACK))
    p.add_argument("--source-checks", default=str(DEFAULT_SOURCE_CHECKS))
    p.add_argument("--output-dir", default=str(vetting.EVIDENCE_DIR))
    p.add_argument("--required-project", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--live-ai", action="store_true")
    return p


def now_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def enforce_required_project(required_project: str | None) -> dict[str, Any]:
    if required_project:
        existing = os.environ.get("D365_GOOGLE_PROJECT")
        if existing and existing != required_project:
            raise SystemExit(
                f"D365_GOOGLE_PROJECT is {existing!r}, but --required-project is {required_project!r}."
            )
        os.environ["D365_GOOGLE_PROJECT"] = required_project
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", required_project)
    readiness = lead_tools.require_google_project(required_project)
    if required_project and readiness.get("effective_project") != required_project:
        raise SystemExit(
            f"Effective Google project is {readiness.get('effective_project')!r}, "
            f"not required project {required_project!r}."
        )
    return readiness


def source_checks_by_company(source_checks: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(record.get("company_name")): record
        for record in source_checks.get("records") or []
        if record.get("company_name")
    }


def lead_to_candidate(lead: dict[str, Any], source_check: dict[str, Any] | None) -> dict[str, Any]:
    snippets = [str(lead.get("evidence_excerpt") or "")]
    if source_check:
        if source_check.get("manual_visual_source_note"):
            snippets.append(str(source_check["manual_visual_source_note"]))
        matched_terms = source_check.get("matched_source_terms") or []
        if matched_terms:
            snippets.append("Matched source terms: " + ", ".join(str(item) for item in matched_terms))
    return {
        "company_name": lead.get("company_name"),
        "country": lead.get("country"),
        "signal_type": lead.get("signal_type"),
        "signal_tier": lead.get("signal_strength"),
        "dynamics_product": lead.get("dynamics_product"),
        "signal_summary": lead.get("opportunity_signal"),
        "evidence_urls": [lead.get("evidence_url")] if lead.get("evidence_url") else [],
        "evidence_snippets": [item for item in snippets if item],
        "source_type": lead.get("source_type"),
        "source_url_type": lead.get("source_url_type"),
        "suggested_contact_roles": lead.get("contact_target_roles") or [],
        "missing_verification_points": lead.get("remaining_uncertainty") or [],
        "deterministic_flags": lead.get("deterministic_flags") or [],
        "baseline_lead": lead,
        "source_check": source_check or {},
    }


def source_check_follow_up(lead: dict[str, Any], source_check: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not source_check:
        return []
    return [
        {
            "kind": "source_fetch",
            "url": lead.get("evidence_url"),
            "final_url": source_check.get("final_url") or lead.get("final_evidence_url_after_redirect") or lead.get("evidence_url"),
            "source_name": lead.get("source_name"),
            "verified_live": bool(source_check.get("verified_live")),
            "fetched_at": source_check.get("fetched_at"),
            "text_excerpt": lead.get("evidence_excerpt"),
            "manual_visual_source_note": source_check.get("manual_visual_source_note"),
            "raw_artifact_hits": source_check.get("raw_artifact_hits") or [],
            "supplemental_live_check_required": bool(source_check.get("supplemental_live_check_required")),
        }
    ]


def dry_run_reviewer(record: dict[str, Any], stage: str, request_index: int):
    baseline = record.get("baseline_lead") or {}
    response = {
        "lead_status": baseline.get("lead_status") or "source_cleanup_needed",
        "signal_strength": baseline.get("signal_strength") or "promising",
        "signal_type": baseline.get("signal_type") or record.get("signal_type"),
        "evidence_used": record.get("evidence_urls", []) + record.get("evidence_snippets", []),
        "evidence_gaps": [],
        "opportunity_signal": baseline.get("opportunity_signal") or record.get("signal_summary"),
        "why_this_matters_to_1bt": baseline.get("why_this_matters_to_1bt"),
        "commercial_opening": baseline.get("commercial_opening"),
        "value_of_signal": baseline.get("value_of_signal"),
        "intelligence_reading": baseline.get("intelligence_reading"),
        "board_relevance": baseline.get("board_relevance"),
        "contact_target_roles": baseline.get("contact_target_roles") or [],
        "do_not_claim_notes": baseline.get("do_not_claim_notes") or vetting.DEFAULT_DO_NOT_CLAIM_NOTES,
        "remaining_uncertainty": baseline.get("remaining_uncertainty") or ["Dry-run baseline echo."],
        "final_rejection_reason": "",
    }
    return json.dumps(response), {"prompt_token_count": 0, "candidates_token_count": 0, "total_token_count": 0}, "dry-run"


def run_check(
    *,
    input_pack: Path | str = DEFAULT_INPUT_PACK,
    source_checks: Path | str = DEFAULT_SOURCE_CHECKS,
    output_dir: Path | str = vetting.EVIDENCE_DIR,
    required_project: str | None = None,
    live_ai: bool = False,
    model: str | None = None,
    reviewer_call: Any | None = None,
    timestamp: str | None = None,
) -> dict[str, str]:
    input_pack = Path(input_pack)
    source_checks = Path(source_checks)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pack = load_json(input_pack)
    source_data = load_json(source_checks)
    source_map = source_checks_by_company(source_data)
    leads = list(pack.get("leads") or [])
    if not leads:
        raise SystemExit(f"No leads found in {input_pack}")

    client = None
    if live_ai:
        enforce_required_project(required_project)
        client, client_info = vetting.make_vertex_vetter_client(model)
    else:
        client_info = {
            "model": vetting.vetter_model_name(model),
            "provider_path": "injected reviewer_call" if reviewer_call else "dry-run baseline echo",
            "project": "unit-test" if reviewer_call else "local",
            "location": "local",
            "auth_mode": "test" if reviewer_call else "dry-run",
        }
        reviewer_call = reviewer_call or dry_run_reviewer

    records = []
    requests = []
    for index, lead in enumerate(leads, start=1):
        source_check = source_map.get(str(lead.get("company_name")))
        candidate = lead_to_candidate(lead, source_check)
        record = vetting.prepare_vetting_record(
            candidate,
            index=index,
            stage="regression_check",
            follow_up_evidence=source_check_follow_up(lead, source_check),
        )
        record["baseline_lead"] = lead
        review, meta = vetting.run_vetter_request(
            record,
            stage="regression_check",
            request_index=index,
            client=client,
            client_info=client_info,
            reviewer_call=reviewer_call,
        )
        requests.append(meta)
        records.append(
            {
                "baseline_lead": lead,
                "source_check": source_check or {},
                "vetter_review": review,
                "request_metadata": meta,
                "comparison": compare_review_to_baseline(lead, review, meta),
            }
        )

    output = build_check_output(
        input_pack=input_pack,
        source_checks=source_checks,
        client_info=client_info,
        records=records,
        requests=requests,
    )
    stamp = timestamp or now_timestamp()
    json_path = output_dir / f"{OUTPUT_PREFIX}_{stamp}.json"
    md_path = output_dir / f"{OUTPUT_PREFIX}_{stamp}.md"
    secret_path = output_dir / f"{OUTPUT_PREFIX}_{stamp}_SECRET_SCAN.json"
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(output), encoding="utf-8")
    secret_scan = vetting.scan_secret_patterns([json_path, md_path])
    secret_path.write_text(json.dumps(secret_scan, indent=2), encoding="utf-8")
    if not secret_scan["passed"]:
        raise RuntimeError(f"Secret scan failed: {secret_path}")
    return {"json": str(json_path), "markdown": str(md_path), "secret_scan": str(secret_path)}


def compare_review_to_baseline(
    baseline: dict[str, Any],
    review: dict[str, Any],
    request_meta: dict[str, Any],
) -> dict[str, Any]:
    disagreements = []
    material_issues = []
    if baseline.get("lead_status") != review.get("lead_status"):
        disagreements.append(
            {
                "field": "lead_status",
                "baseline": baseline.get("lead_status"),
                "vetter": review.get("lead_status"),
            }
        )
    if baseline.get("signal_strength") != review.get("signal_strength"):
        disagreements.append(
            {
                "field": "signal_strength",
                "baseline": baseline.get("signal_strength"),
                "vetter": review.get("signal_strength"),
            }
        )
    if request_meta.get("request_error_type"):
        material_issues.append("ai_request_failed")
    if review.get("invented_candidate_facts_detected"):
        material_issues.append("invented_candidate_facts_detected")
    if review.get("lead_status") == "reject":
        material_issues.append("baseline_lead_rejected_by_vetter")
    if review.get("lead_status") != "reject":
        missing = vetting.missing_non_reject_writeup_fields(
            review,
            vetting.normalize_list(review.get("evidence_used")),
        )
        if missing:
            material_issues.append("missing_required_writeup_fields:" + ",".join(missing))
        supplied_url = str(baseline.get("evidence_url") or "")
        review_urls = vetting.extract_urls(review.get("evidence_used"))
        if supplied_url and supplied_url not in review_urls:
            material_issues.append("supplied_evidence_url_not_cited")
    if unsupported_overclaim_detected(review):
        material_issues.append("unsupported_commercial_overclaim")
    return {
        "disagreements": disagreements,
        "material_issues": material_issues,
        "material_issue_count": len(material_issues),
    }


def unsupported_overclaim_detected(review: dict[str, Any]) -> bool:
    positive_text = " ".join(
        str(review.get(field) or "")
        for field in (
            "opportunity_signal",
            "why_this_matters_to_1bt",
            "commercial_opening",
            "value_of_signal",
            "intelligence_reading",
            "board_relevance",
        )
    ).lower()
    overclaims = (
        "has budget",
        "budget approved",
        "dissatisfied",
        "incumbent failed",
        "ready to buy",
        "active buying process",
    )
    return any(term in positive_text for term in overclaims)


def build_check_output(
    *,
    input_pack: Path,
    source_checks: Path,
    client_info: dict[str, Any],
    records: list[dict[str, Any]],
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    request_failures = sum(1 for item in requests if item.get("request_error_type"))
    material_issue_count = sum(item["comparison"]["material_issue_count"] for item in records)
    disagreement_count = sum(len(item["comparison"]["disagreements"]) for item in records)
    return {
        "metadata": {
            "artifact_type": "uk_ie_d365_vetter_agent_check",
            "generated_at": datetime.now(UTC).isoformat(),
            "input_pack": str(input_pack),
            "source_checks": str(source_checks),
            "model": client_info.get("model"),
            "provider_path": client_info.get("provider_path"),
            "project": client_info.get("project"),
            "location": client_info.get("location"),
            "auth_mode": client_info.get("auth_mode"),
        },
        "summary": {
            "baseline_lead_count": len(records),
            "agent_request_count": len(requests),
            "agent_request_failures": request_failures,
            "comparison_disagreement_count": disagreement_count,
            "material_issue_count": material_issue_count,
            "readiness_conclusion": (
                "ready_for_future_final_curation"
                if request_failures == 0 and material_issue_count == 0
                else "needs_manual_review_before_replacing_codex"
            ),
        },
        "records": records,
    }


def render_markdown(output: dict[str, Any]) -> str:
    lines = [
        "# UK/IE D365 Vetter Agent Check",
        "",
        f"- Baseline leads checked: {output['summary']['baseline_lead_count']}",
        f"- Agent requests: {output['summary']['agent_request_count']}",
        f"- Request failures: {output['summary']['agent_request_failures']}",
        f"- Comparison disagreements: {output['summary']['comparison_disagreement_count']}",
        f"- Material issues: {output['summary']['material_issue_count']}",
        f"- Readiness conclusion: {output['summary']['readiness_conclusion']}",
        f"- Model/provider/project: {output['metadata']['model']} / {output['metadata']['provider_path']} / {output['metadata']['project']}",
        "",
    ]
    for record in output["records"]:
        baseline = record["baseline_lead"]
        review = record["vetter_review"]
        comparison = record["comparison"]
        lines.extend(
            [
                f"## {baseline.get('company_name')}",
                "",
                f"- Baseline: {baseline.get('lead_status')} / {baseline.get('signal_strength')}",
                f"- Vetter: {review.get('lead_status')} / {review.get('signal_strength')}",
                f"- Material issues: {', '.join(comparison['material_issues']) if comparison['material_issues'] else 'none'}",
                f"- Disagreements: {len(comparison['disagreements'])}",
                "",
            ]
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.live_ai:
        raise SystemExit("Use --live-ai for the production vetter check.")
    artifacts = run_check(
        input_pack=args.input_pack,
        source_checks=args.source_checks,
        output_dir=args.output_dir,
        required_project=args.required_project,
        live_ai=args.live_ai,
        model=args.model,
    )
    print(json.dumps(artifacts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
