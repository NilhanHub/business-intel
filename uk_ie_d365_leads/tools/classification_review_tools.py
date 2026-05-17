"""Dry-run utilities for the UK/Ireland D365 classification review harness."""

from __future__ import annotations

import json
import os
import re
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REVIEW_SCHEMA_VERSION = "2026-05-17.llm-classification-review-dry-run-v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "Evidence"
DEFAULT_EVIDENCE_FILE = EVIDENCE_DIR / "UK_IE_D365_AUDIT_REPLAY.json"

OUTPUT_BASENAME = "UK_IE_D365_LLM_CLASSIFICATION_REVIEW"
INPUT_BATCH_PATH = EVIDENCE_DIR / f"{OUTPUT_BASENAME}_INPUT_BATCH.json"
REVIEW_JSON_PATH = EVIDENCE_DIR / f"{OUTPUT_BASENAME}.json"
REVIEW_MD_PATH = EVIDENCE_DIR / f"{OUTPUT_BASENAME}.md"
RULE_PLAN_PATH = EVIDENCE_DIR / f"{OUTPUT_BASENAME}_RULE_CHANGE_PLAN.md"
REPORT_PATH = EVIDENCE_DIR / f"{OUTPUT_BASENAME}_REPORT.md"
SECRET_SCAN_PATH = EVIDENCE_DIR / f"{OUTPUT_BASENAME}_SECRET_SCAN.json"
MANIFEST_PATH = EVIDENCE_DIR / f"{OUTPUT_BASENAME}_EVIDENCE_MANIFEST.json"
ZIP_PATH = EVIDENCE_DIR / f"{OUTPUT_BASENAME}_EVIDENCE.zip"

PHASE2_OUTPUT_BASENAME = "UK_IE_D365_LLM_CLASSIFICATION_REVIEW_PHASE2"
PHASE2_REVIEW_JSON_PATH = EVIDENCE_DIR / f"{PHASE2_OUTPUT_BASENAME}.json"
PHASE2_REVIEW_MD_PATH = EVIDENCE_DIR / f"{PHASE2_OUTPUT_BASENAME}.md"
PHASE2_REPORT_PATH = EVIDENCE_DIR / f"{PHASE2_OUTPUT_BASENAME}_REPORT.md"
PHASE2_SECRET_SCAN_PATH = EVIDENCE_DIR / f"{PHASE2_OUTPUT_BASENAME}_SECRET_SCAN.json"
PHASE2_MANIFEST_PATH = EVIDENCE_DIR / f"{PHASE2_OUTPUT_BASENAME}_EVIDENCE_MANIFEST.json"
PHASE2_ZIP_PATH = EVIDENCE_DIR / f"{PHASE2_OUTPUT_BASENAME}_EVIDENCE.zip"
RULE_PROPOSAL_V1_JSON_PATH = EVIDENCE_DIR / "UK_IE_D365_LLM_CLASSIFICATION_RULE_PROPOSAL_V1.json"
RULE_PROPOSAL_V1_MD_PATH = EVIDENCE_DIR / "UK_IE_D365_LLM_CLASSIFICATION_RULE_PROPOSAL_V1.md"

SOURCE_OF_TRUTH_FIELDS = (
    "final_decision",
    "signal_tier",
    "rejection_reason",
    "confidence_score",
    "urgency_score",
    "audit_trace",
)
REQUIRED_REVIEW_FIELDS = (
    "candidate_id",
    "company_name",
    "source_url_or_redirect_url",
    "deterministic_decision",
    "deterministic_score_or_tier",
    "deterministic_rejection_reason",
    "deterministic_confidence_score",
    "deterministic_urgency_score",
    "deterministic_audit_trace",
    "llm_review_decision",
    "llm_confidence",
    "discrepancy_type",
    "evidence_used",
    "missing_evidence",
    "deterministic_rule_likely_at_fault",
    "recommended_rule_change",
    "should_promote_to_human_review",
    "should_remain_rejected",
    "notes",
    "invented_candidate_facts_detected",
    "live_llm_used",
)
FACTUAL_FIELDS = (
    "candidate_id",
    "company_name",
    "source_url_or_redirect_url",
    "deterministic_decision",
    "deterministic_score_or_tier",
    "deterministic_rejection_reason",
    "deterministic_confidence_score",
    "deterministic_urgency_score",
    "deterministic_audit_trace",
    "evidence_used",
)
LIVE_REVIEW_DECISIONS = {"accept", "provisional", "reject"}
LIVE_DISCREPANCY_TYPES = {
    "false_negative_risk",
    "false_positive_risk",
    "tier_mismatch",
    "reason_mismatch",
    "no_discrepancy",
}
PROPOSAL_IMPACTS = {
    "supports_existing_rule",
    "suggests_rule_loosen",
    "suggests_rule_tighten",
    "suggests_tier_shift",
    "needs_more_samples",
}
SECRET_PATTERNS = {
    "AIza": re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),
    "sk-": re.compile(r"\bsk-[0-9A-Za-z_\-]{8,}"),
    "ya29.": re.compile(r"ya29\.[0-9A-Za-z_\-\.]+"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    "private_key": re.compile(r"\bprivate_key\b", re.IGNORECASE),
    "client_secret": re.compile(r"\bclient_secret\b", re.IGNORECASE),
    "refresh_token": re.compile(r"\brefresh_token\b", re.IGNORECASE),
    "access_token": re.compile(r"\baccess_token\b", re.IGNORECASE),
    "GEMINI_API_KEY": re.compile(r"\bGEMINI_API_KEY\b"),
    "GOOGLE_API_KEY": re.compile(r"\bGOOGLE_API_KEY\b"),
    "SERPER_API_KEY": re.compile(r"\bSERPER_API_KEY\b"),
    "TAVILY_API_KEY": re.compile(r"\bTAVILY_API_KEY\b"),
    "HUNTER_API_KEY": re.compile(r"\bHUNTER_API_KEY\b"),
    "api_key": re.compile(r"\bapi_key\b", re.IGNORECASE),
    "password_equals": re.compile(r"password\s*=", re.IGNORECASE),
    "password_colon": re.compile(r"password\s*:", re.IGNORECASE),
    "bearer_token": re.compile(r"bearer\s+[0-9A-Za-z_\-\.]{8,}", re.IGNORECASE),
    "email_password_assignment": re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}[^.\n]{0,80}password\s*[:=]", re.IGNORECASE),
}


def load_saved_evidence(evidence_file: Path | str = DEFAULT_EVIDENCE_FILE) -> dict[str, Any]:
    return json.loads(Path(evidence_file).read_text(encoding="utf-8"))


def all_candidates(data: dict[str, Any]) -> list[dict[str, Any]]:
    return list(data.get("leads") or []) + list(data.get("rejected_leads") or [])


def build_review_package(
    *,
    evidence_file: Path | str = DEFAULT_EVIDENCE_FILE,
    output_dir: Path | str = EVIDENCE_DIR,
    command_log: list[str] | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    data = load_saved_evidence(evidence_file)
    candidates = all_candidates(data)
    review_records = []
    input_candidates = []
    reconstruction_records = []
    for index, candidate in enumerate(candidates, start=1):
        prepared = prepare_candidate(candidate, index=index)
        review_records.append(prepared["review_record"])
        input_candidates.append(prepared["input_record"])
        reconstruction_records.extend(prepared["reconstruction_records"])

    validation = validate_review_records(review_records)
    invented_check = invented_candidate_facts_check(review_records)
    risk_patterns = dry_run_risk_patterns(review_records)
    counts = review_counts(data, review_records)
    metadata = build_metadata(data, evidence_file, counts, reconstruction_records, validation, invented_check)
    input_batch = {
        "metadata": {
            **metadata,
            "artifact_type": "future_llm_review_input_batch",
            "instructions": [
                "Future live review must use only provided candidate evidence.",
                "Do not invent companies, URLs, Dynamics 365 evidence, contacts, emails, or source facts.",
                "Phase 1 generated this batch without live LLM calls.",
            ],
        },
        "candidates": input_candidates,
    }
    review_output = {
        "metadata": metadata,
        "counts": counts,
        "source_of_truth_fields": list(SOURCE_OF_TRUTH_FIELDS),
        "schema_validation": validation,
        "invented_candidate_facts_check": invented_check,
        "reconstruction_records": reconstruction_records,
        "dry_run_risk_ranked_rule_patterns": risk_patterns,
        "review_records": review_records,
        "notes": [
            "Dry-run only: live_llm_used is false and live_request_count is 0.",
            "No LLM discrepancies are claimed in Phase 1.",
            "Deterministic classifier rules were not changed.",
        ],
    }
    artifacts = write_phase1_artifacts(
        output_dir=output_dir,
        input_batch=input_batch,
        review_output=review_output,
        command_log=command_log or [],
    )
    return {
        "input_batch": input_batch,
        "review_output": review_output,
        "artifacts": artifacts,
    }


def prepare_candidate(candidate: dict[str, Any], *, index: int) -> dict[str, Any]:
    reconstruction_records = reconstruction_records_for_candidate(candidate, index=index)
    trace = candidate.get("audit_trace") or {}
    candidate_id = trace.get("candidate_id") or f"saved_candidate_{index}"
    evidence_urls = list(candidate.get("evidence_urls") or [])
    evidence_snippets = list(candidate.get("evidence_snippets") or [])
    source_url = evidence_urls[0] if evidence_urls else None
    final_decision = candidate.get("final_decision") or {}
    tier = candidate.get("signal_tier") or final_decision.get("final_tier")
    deterministic_decision = deterministic_decision_label(candidate, final_decision, tier)
    missing_evidence = missing_evidence_for_candidate(candidate, source_url)
    evidence_used = {
        "urls": evidence_urls,
        "snippets": evidence_snippets,
        "source_url_type": candidate.get("source_url_type"),
        "source_provider": candidate.get("source_provider"),
    }
    review_record = {
        "candidate_id": candidate_id,
        "company_name": candidate.get("company_name"),
        "source_url_or_redirect_url": source_url,
        "deterministic_decision": deterministic_decision,
        "deterministic_score_or_tier": tier,
        "deterministic_rejection_reason": candidate.get("rejection_reason") or final_decision.get("rejection_reason"),
        "deterministic_confidence_score": candidate.get("confidence_score"),
        "deterministic_urgency_score": candidate.get("urgency_score"),
        "deterministic_audit_trace": trace,
        "llm_review_decision": "dry_run_unreviewed",
        "llm_confidence": None,
        "discrepancy_type": "dry_run_unreviewed",
        "evidence_used": evidence_used,
        "missing_evidence": missing_evidence,
        "deterministic_rule_likely_at_fault": None,
        "recommended_rule_change": None,
        "should_promote_to_human_review": None,
        "should_remain_rejected": None,
        "notes": dry_run_notes(candidate, final_decision),
        "invented_candidate_facts_detected": False,
        "live_llm_used": False,
        "schema_validation_status": "pending",
        "review_metadata": {
            "source_record_index": index,
            "source_of_truth_fields_used": [field for field in SOURCE_OF_TRUTH_FIELDS if field in candidate],
            "reconstruction_required": bool(reconstruction_records),
        },
    }
    input_record = {
        key: review_record[key]
        for key in (
            "candidate_id",
            "company_name",
            "source_url_or_redirect_url",
            "deterministic_decision",
            "deterministic_score_or_tier",
            "deterministic_rejection_reason",
            "deterministic_confidence_score",
            "deterministic_urgency_score",
            "deterministic_audit_trace",
            "evidence_used",
            "missing_evidence",
            "notes",
        )
    }
    return {
        "review_record": review_record,
        "input_record": input_record,
        "reconstruction_records": reconstruction_records,
    }


def deterministic_decision_label(candidate: dict[str, Any], final_decision: dict[str, Any], tier: str | None) -> str:
    if tier == "D":
        return "reject"
    if final_decision.get("accepted") is True:
        return "accept"
    if tier in {"B", "C"}:
        return "provisional"
    return "unknown"


def missing_evidence_for_candidate(candidate: dict[str, Any], source_url: str | None) -> list[str]:
    missing = []
    if not candidate.get("company_name"):
        missing.append("company_name")
    if not source_url:
        missing.append("source_url_or_redirect_url")
    if not candidate.get("evidence_snippets"):
        missing.append("evidence_snippets")
    if not candidate.get("audit_trace"):
        missing.append("audit_trace")
    for field in SOURCE_OF_TRUTH_FIELDS:
        if field not in candidate:
            missing.append(field)
    return sorted(set(missing))


def reconstruction_records_for_candidate(candidate: dict[str, Any], *, index: int) -> list[dict[str, Any]]:
    trace = candidate.get("audit_trace") or {}
    candidate_id = trace.get("candidate_id") or f"saved_candidate_{index}"
    records = []
    for field in SOURCE_OF_TRUTH_FIELDS:
        if field not in candidate:
            records.append(
                {
                    "candidate_id": candidate_id,
                    "field": field,
                    "reason": "required saved source-of-truth field missing from candidate; dry-run left factual value null or derived only from existing saved fields",
                }
            )
    return records


def dry_run_notes(candidate: dict[str, Any], final_decision: dict[str, Any]) -> list[str]:
    notes = ["Prepared for future LLM review; no live LLM call was made."]
    if candidate.get("signal_tier") == "D":
        notes.append("Rejected candidate preserved for future false-negative audit.")
    if final_decision.get("human_review_recommended"):
        notes.append("Saved deterministic final_decision already recommends human review.")
    if candidate.get("source_url_type") == "grounding_redirect":
        notes.append("Saved evidence URL is a grounding redirect; clean source URL may need later verification.")
    return notes


def validate_review_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors = []
    for index, record in enumerate(records, start=1):
        missing = [field for field in REQUIRED_REVIEW_FIELDS if field not in record]
        if missing:
            errors.append({"record_index": index, "missing_fields": missing})
        if record.get("llm_review_decision") != "dry_run_unreviewed":
            errors.append({"record_index": index, "error": "llm_review_decision must be dry_run_unreviewed in Phase 1"})
        if record.get("live_llm_used") is not False:
            errors.append({"record_index": index, "error": "live_llm_used must be false in Phase 1"})
        record["schema_validation_status"] = "valid" if not missing else "invalid"
    return {
        "valid": not errors,
        "record_count": len(records),
        "errors": errors,
        "schema_version": REVIEW_SCHEMA_VERSION,
    }


def invented_candidate_facts_check(records: list[dict[str, Any]]) -> dict[str, Any]:
    flagged = [
        record.get("candidate_id")
        for record in records
        if record.get("invented_candidate_facts_detected") is True
    ]
    return {
        "passed": not flagged,
        "invented_candidate_facts_detected": bool(flagged),
        "flagged_candidate_ids": flagged,
        "allowed_new_fields": [
            "review metadata",
            "schema validation status",
            "missing_evidence",
            "discrepancy placeholders",
            "dry-run status",
            "future review placeholders",
        ],
        "factual_fields_checked": list(FACTUAL_FIELDS),
    }


def dry_run_risk_patterns(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failed_rules = Counter()
    rejection_reasons = Counter()
    human_review_reasons = Counter()
    for record in records:
        trace = record.get("deterministic_audit_trace") or {}
        for rule in trace.get("rule_results") or []:
            if rule.get("severity") == "blocking" and rule.get("passed") is False:
                failed_rules[str(rule.get("rule_id") or "unknown")] += 1
        reason = record.get("deterministic_rejection_reason")
        if reason:
            rejection_reasons[str(reason)] += 1
        final_decision = (trace.get("final_decision") or {})
        human_reason = final_decision.get("human_review_reason")
        if human_reason:
            human_review_reasons[str(human_reason)] += 1

    patterns = []
    for name, count in failed_rules.most_common():
        patterns.append(
            {
                "pattern_type": "failed_blocking_rule",
                "pattern": name,
                "candidate_count": count,
                "phase1_status": "risk-ranked_from_saved_audit_trace",
            }
        )
    for name, count in rejection_reasons.most_common():
        patterns.append(
            {
                "pattern_type": "rejection_reason",
                "pattern": name,
                "candidate_count": count,
                "phase1_status": "found_in_saved_deterministic_output",
            }
        )
    return patterns[:12]


def review_counts(data: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    tier_counts = data.get("tier_counts") or dict(Counter(record.get("deterministic_score_or_tier") for record in records))
    deterministic_accept_count = sum(1 for record in records if record.get("deterministic_decision") == "accept")
    deterministic_reject_count = sum(1 for record in records if record.get("deterministic_decision") == "reject")
    deterministic_provisional_count = sum(1 for record in records if record.get("deterministic_decision") == "provisional")
    return {
        "candidates_loaded": len(records),
        "candidates_prepared_for_review": len(records),
        "candidates_reviewed_by_llm": 0,
        "live_request_count": 0,
        "token_usage": None,
        "deterministic_accept_count": deterministic_accept_count,
        "deterministic_reject_count": deterministic_reject_count,
        "deterministic_provisional_or_human_review_count": deterministic_provisional_count,
        "llm_accept_count": 0,
        "llm_provisional_count": 0,
        "llm_reject_count": 0,
        "llm_discrepancy_count": 0,
        "suspected_false_negative_count": 0,
        "suspected_false_positive_count": 0,
        "tier_counts": tier_counts,
    }


def build_metadata(
    data: dict[str, Any],
    evidence_file: Path | str,
    counts: dict[str, Any],
    reconstruction_records: list[dict[str, Any]],
    validation: dict[str, Any],
    invented_check: dict[str, Any],
) -> dict[str, Any]:
    audit = data.get("audit_metadata") or {}
    return {
        "review_schema_version": REVIEW_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "phase": "Phase 1 dry run only",
        "input_file": str(Path(evidence_file)),
        "source_provider": data.get("provider") or audit.get("search_provider"),
        "source_model": audit.get("effective_model_name"),
        "dry_run_mode_executed": True,
        "live_llm_mode_executed": False,
        "live_llm_used": False,
        "live_request_count": counts["live_request_count"],
        "token_usage": None,
        "deterministic_rules_changed": False,
        "deployment_attempted": False,
        "gcloud_called": False,
        "agents_cli_deploy_called": False,
        "source_of_truth_fields": list(SOURCE_OF_TRUTH_FIELDS),
        "reconstruction_count": len(reconstruction_records),
        "schema_validation_result": "PASS" if validation["valid"] else "FAIL",
        "invented_candidate_facts_check_result": "PASS" if invented_check["passed"] else "FAIL",
    }


def write_phase1_artifacts(
    *,
    output_dir: Path,
    input_batch: dict[str, Any],
    review_output: dict[str, Any],
    command_log: list[str],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = artifact_paths(output_dir)
    write_json(paths["input_batch"], input_batch)
    write_json(paths["review_json"], review_output)
    paths["review_md"].write_text(render_review_markdown(review_output), encoding="utf-8")
    paths["rule_plan"].write_text(render_rule_change_plan(review_output), encoding="utf-8")
    paths["report"].write_text(render_report(review_output, command_log, paths), encoding="utf-8")
    scan = scan_secret_patterns([paths["input_batch"], paths["review_json"], paths["review_md"], paths["rule_plan"], paths["report"]])
    write_json(paths["secret_scan"], scan)
    manifest = build_manifest(paths, scan)
    write_json(paths["manifest"], manifest)
    manifest = build_manifest(paths, scan)
    write_json(paths["manifest"], manifest)
    create_evidence_zip(paths, manifest)
    return {name: str(path) for name, path in paths.items()}


def artifact_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "input_batch": output_dir / f"{OUTPUT_BASENAME}_INPUT_BATCH.json",
        "review_json": output_dir / f"{OUTPUT_BASENAME}.json",
        "review_md": output_dir / f"{OUTPUT_BASENAME}.md",
        "rule_plan": output_dir / f"{OUTPUT_BASENAME}_RULE_CHANGE_PLAN.md",
        "report": output_dir / f"{OUTPUT_BASENAME}_REPORT.md",
        "secret_scan": output_dir / f"{OUTPUT_BASENAME}_SECRET_SCAN.json",
        "manifest": output_dir / f"{OUTPUT_BASENAME}_EVIDENCE_MANIFEST.json",
        "zip": output_dir / f"{OUTPUT_BASENAME}_EVIDENCE.zip",
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True), encoding="utf-8")


def render_review_markdown(output: dict[str, Any]) -> str:
    metadata = output["metadata"]
    counts = output["counts"]
    patterns = output["dry_run_risk_ranked_rule_patterns"]
    lines = [
        "# UK/IE D365 LLM Classification Review - Phase 1 Dry Run",
        "",
        "## Summary",
        f"- Live LLM used: `{metadata['live_llm_used']}`",
        f"- Live request count: `{metadata['live_request_count']}`",
        f"- Candidates loaded: {counts['candidates_loaded']}",
        f"- Candidates prepared for future review: {counts['candidates_prepared_for_review']}",
        f"- Candidates actually reviewed by LLM: {counts['candidates_reviewed_by_llm']}",
        "- LLM discrepancies claimed: 0",
        "- Deterministic rules changed: no",
        "",
        "## Dry-Run Risk-Ranked Patterns",
        "",
    ]
    for pattern in patterns:
        lines.append(f"- `{pattern['pattern']}` ({pattern['pattern_type']}): {pattern['candidate_count']}")
    lines.extend(
        [
            "",
            "## Measurement Note",
            "",
            "The <0.9% classifier-error target is not claimed from this saved replay. A labeled gold set large enough to support that claim is required before the target can be honestly measured.",
            "",
        ]
    )
    return "\n".join(lines)


def render_rule_change_plan(output: dict[str, Any]) -> str:
    counts = output["counts"]
    patterns = output["dry_run_risk_ranked_rule_patterns"]
    lines = [
        "# UK/IE D365 LLM Classification Review Rule-Change Plan",
        "",
        "Phase 1 is dry-run only. No live LLM review was used, so this plan does not claim LLM-found discrepancies.",
        "",
        "## Current Evidence",
        f"- Candidates loaded: {counts['candidates_loaded']}",
        f"- Candidates prepared for review: {counts['candidates_prepared_for_review']}",
        "- Candidates reviewed by LLM: 0",
        "- Live request count: 0",
        "- Deterministic rules changed: no",
        "",
        "## Risk-Ranked Or Expected Rule-Failure Patterns",
        "",
    ]
    for pattern in patterns:
        label = "found" if pattern["phase1_status"] == "found_in_saved_deterministic_output" else "risk-ranked"
        lines.append(f"- {label}: `{pattern['pattern']}` affected {pattern['candidate_count']} saved candidates.")
    lines.extend(
        [
            "",
            "## Preservation Rules",
            "- Preserve tender/procurement exclusion as a hard out-of-scope guardrail.",
            "- Preserve the no-fake/no-invented-evidence rule: missing factual evidence must stay missing until live public evidence supports it.",
            "- Treat weak real candidates as possible future provisional/human-review candidates, not verified leads.",
            "",
            "## Expected Impact If Later Rule Changes Are Made",
            "- Recall may improve if high-risk Tier D cases with defensible saved evidence become provisional instead of hard rejected.",
            "- Precision may drop if weak candidates are surfaced too aggressively, so provisional labeling and human review must remain explicit.",
            "",
            "## Measurement Requirement",
            "The <0.9% classifier-error target cannot be proven from the current saved replay. A labeled gold set should include accepted, rejected, provisional, tender/procurement, vendor, recruitment, UK/Ireland ambiguity, and clean-source examples with human labels.",
            "",
        ]
    )
    return "\n".join(lines)


def render_report(output: dict[str, Any], command_log: list[str], paths: dict[str, Path]) -> str:
    metadata = output["metadata"]
    counts = output["counts"]
    validation = output["schema_validation"]
    invented = output["invented_candidate_facts_check"]
    recon = output["reconstruction_records"]
    patterns = output["dry_run_risk_ranked_rule_patterns"]
    lines = [
        "# UK/IE D365 LLM Classification Review Phase 1 Report",
        "",
        "## Files Inspected",
        "- `uk_ie_d365_leads/tools/lead_tools.py`",
        "- `uk_ie_d365_leads/agent.py`",
        "- `uk_ie_d365_leads/agents/search_agent.py`",
        "- `tools/review_uk_ie_d365_candidates.py`",
        "- `Evidence/UK_IE_D365_COMMERCIAL_SEARCH_RUN.json`",
        "- `Evidence/UK_IE_D365_5_COMPANY_LIVE_SEARCH_EVIDENCE.json`",
        "- `Evidence/UK_IE_D365_AUDIT_REPLAY.json`",
        "- `Evidence/UK_IE_D365_HUMAN_REVIEW_SHORTLIST.json`",
        "- `uk_ie_d365_leads/tests/test_uk_ie_d365_leads.py`",
        "",
        "## Files Changed",
        "- `uk_ie_d365_leads/agents/classification_reviewer_agent.py`",
        "- `uk_ie_d365_leads/tools/classification_review_tools.py`",
        "- `tools/run_uk_ie_d365_llm_classification_review.py`",
        "- `uk_ie_d365_leads/tests/test_uk_ie_d365_leads.py`",
        "- Phase 1 evidence artifacts listed in the manifest",
        "",
        "## Commands Run",
        "",
    ]
    lines.extend([f"- `{command}`" for command in command_log] or ["- Command log is captured by the runner and final verification commands."])
    lines.extend(
        [
            "",
            "## Execution Summary",
            f"- Dry-run mode executed: {'yes' if metadata['dry_run_mode_executed'] else 'no'}",
            "- Live LLM mode executed: no",
            "- Live request count: 0",
            "- Token usage: none / not applicable",
            f"- Number of candidates loaded: {counts['candidates_loaded']}",
            f"- Number of candidates prepared for review: {counts['candidates_prepared_for_review']}",
            "- Number of candidates actually reviewed by LLM: 0",
            f"- Deterministic accept count: {counts['deterministic_accept_count']}",
            f"- Deterministic reject count: {counts['deterministic_reject_count']}",
            f"- Deterministic provisional/human-review count if present: {counts['deterministic_provisional_or_human_review_count']}",
            f"- Schema validation result: {metadata['schema_validation_result']}",
            f"- Invented candidate facts check result: {metadata['invented_candidate_facts_check_result']}",
            f"- Reconstruction count: {len(recon)}",
            "- Deterministic rules changed: no",
            "- Deployment attempted: no",
            "- gcloud called: no",
            "- agents-cli deploy called: no",
            "",
            "## Reconstructed Fields",
        ]
    )
    if recon:
        lines.extend([f"- `{item['candidate_id']}`: `{item['field']}` - {item['reason']}" for item in recon])
    else:
        lines.append("- None")
    lines.extend(["", "## Dry-Run Risk-Ranked Rule Patterns"])
    lines.extend([f"- `{item['pattern']}` ({item['pattern_type']}): {item['candidate_count']}" for item in patterns] or ["- None"])
    lines.extend(
        [
            "",
            "## Validation",
            f"- Schema records valid: {validation['valid']}",
            f"- Invented candidate facts detected: {invented['invented_candidate_facts_detected']}",
            "- Secret scan result: see secret scan artifact",
            f"- Rule-change plan path: `{paths['rule_plan']}`",
            f"- Evidence ZIP path: `{paths['zip']}`",
            "",
            "## Remaining Uncertainty",
            "- No live LLM review was run in Phase 1, so no deterministic/LLM discrepancy count is claimed.",
            "- The current saved replay cannot prove the <0.9% classifier-error target without a sufficiently large labeled gold set.",
            "",
            "## Recommendation",
            "Phase 2 live LLM review is recommended after evidence review, using `--live-llm --max-candidates 20` only with separate authorization.",
            "",
        ]
    )
    return "\n".join(lines)


def scan_secret_patterns(paths: list[Path]) -> dict[str, Any]:
    findings = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern_name, regex in SECRET_PATTERNS.items():
            for match in regex.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    {
                        "file": str(path),
                        "pattern": pattern_name,
                        "line": line,
                        "redacted": True,
                    }
                )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "files_scanned": [str(path) for path in paths],
        "findings_count": len(findings),
        "findings": findings,
        "secret_values_printed": False,
        "result": "PASS" if not findings else "REDACTION_REQUIRED",
    }


def build_manifest(paths: dict[str, Path], scan: dict[str, Any]) -> dict[str, Any]:
    included_keys = ["input_batch", "review_json", "review_md", "rule_plan", "report", "secret_scan", "manifest"]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "zip_path": str(paths["zip"]),
        "included_files": [
            {"name": key, "path": str(paths[key]), "size_bytes": paths[key].stat().st_size if paths[key].exists() else 0}
            for key in included_keys
        ],
        "excluded_patterns": [
            ".env",
            ".local_secrets",
            "ADC files",
            "service account keys",
            "caches",
            "unrelated Evidence files",
            "unrelated logs",
            "unrelated ZIPs",
            "secret-bearing files",
        ],
        "secret_scan_result": scan.get("result"),
        "secret_findings_count": scan.get("findings_count"),
    }


def create_evidence_zip(paths: dict[str, Path], manifest: dict[str, Any]) -> None:
    include_keys = ["input_batch", "review_json", "review_md", "rule_plan", "report", "secret_scan", "manifest"]
    with zipfile.ZipFile(paths["zip"], "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for key in include_keys:
            archive.write(paths[key], arcname=paths[key].name)


def live_llm_refusal() -> dict[str, Any]:
    return {
        "status": "refused",
        "reason": "Phase 1 implements the --live-llm flag but does not execute live Gemini/Vertex review without separate user authorization.",
        "live_request_count": 0,
    }


def live_review_model_name(model_override: str | None = None) -> str:
    return (
        model_override
        or os.environ.get("D365_REVIEW_MODEL")
        or os.environ.get("D365_GOOGLE_MODEL")
        or "gemini-2.5-flash"
    )


def select_review_candidates(records: list[dict[str, Any]], max_candidates: int) -> list[dict[str, Any]]:
    if max_candidates <= 0:
        raise ValueError("--max-candidates must be greater than 0")
    return records[:max_candidates]


def make_vertex_reviewer_client(model_override: str | None = None) -> tuple[Any, dict[str, Any]]:
    """Create a Google-native Vertex client for review without exposing secrets."""
    from google import genai

    from uk_ie_d365_leads.tools import lead_tools

    prepare = getattr(lead_tools, "_prepare_google_native_env", None)
    if prepare:
        prepare()
    readiness = lead_tools.google_native_readiness()
    project = readiness.get("adc", {}).get("project") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
    model = live_review_model_name(model_override)
    if not project:
        raise RuntimeError("Vertex/ADC project is unclear; refusing live review.")
    client = genai.Client(vertexai=True, project=project, location=location)
    return client, {
        "model": model,
        "provider_path": "google-genai Vertex AI via ADC",
        "project": project,
        "location": location,
        "auth_mode": "ADC",
        "client_constructor": "genai.Client(vertexai=True, project=project, location=location)",
    }


def build_live_review_package(
    *,
    evidence_file: Path | str = DEFAULT_EVIDENCE_FILE,
    output_dir: Path | str = EVIDENCE_DIR,
    max_candidates: int = 20,
    model: str | None = None,
    command_log: list[str] | None = None,
    reviewer_call: Any | None = None,
    client_factory: Any | None = None,
    git_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    data = load_saved_evidence(evidence_file)
    candidates = all_candidates(data)
    prepared_all = [prepare_candidate(candidate, index=index) for index, candidate in enumerate(candidates, start=1)]
    review_inputs = [item["review_record"] for item in prepared_all]
    selected_records = select_review_candidates(review_inputs, max_candidates)
    reconstruction_records = [
        reconstruction
        for item in prepared_all
        for reconstruction in item["reconstruction_records"]
    ]

    client = None
    client_info: dict[str, Any]
    if reviewer_call is None:
        client_factory = client_factory or make_vertex_reviewer_client
        client, client_info = client_factory(model)
    else:
        client_info = {
            "model": live_review_model_name(model),
            "provider_path": "injected reviewer_call",
            "project": "unit-test",
            "location": "local",
            "auth_mode": "test",
        }

    started_at = datetime.now(UTC).isoformat()
    live_records = []
    requests = []
    for request_index, record in enumerate(selected_records, start=1):
        prompt = build_live_review_prompt(record)
        if reviewer_call is None:
            response_text, usage, model_version = call_vertex_reviewer(
                client=client,
                model=client_info["model"],
                prompt=prompt,
            )
        else:
            response_text, usage, model_version = reviewer_call(record, request_index)
        raw = parse_review_json(response_text)
        request_meta = {
            "request_index": request_index,
            "candidate_id": record.get("candidate_id"),
            "usage_metadata": usage,
            "model_version": model_version,
        }
        live_records.append(normalize_live_review_record(record, raw, request_meta))
        requests.append(request_meta)
    finished_at = datetime.now(UTC).isoformat()

    validation = validate_live_review_records(live_records)
    invented_check = invented_candidate_facts_check(live_records)
    counts = live_review_counts(data, selected_records, live_records, requests)
    proposal = build_rule_proposal_v1(live_records, counts)
    metadata = build_phase2_metadata(
        data=data,
        evidence_file=evidence_file,
        counts=counts,
        reconstruction_records=reconstruction_records,
        validation=validation,
        invented_check=invented_check,
        client_info=client_info,
        started_at=started_at,
        finished_at=finished_at,
        git_metadata=git_metadata or {},
    )
    review_output = {
        "metadata": metadata,
        "counts": counts,
        "source_of_truth_fields": list(SOURCE_OF_TRUTH_FIELDS),
        "schema_validation": validation,
        "invented_candidate_facts_check": invented_check,
        "reconstruction_records": reconstruction_records,
        "llm_request_records": requests,
        "review_records": live_records,
        "rule_proposal_v1_summary": proposal["summary"],
        "notes": [
            "Phase 2 live LLM review used existing saved evidence only.",
            "Deterministic classifier rules were not changed.",
            "Rule Proposal v1 is proposal-only and requires convergence across later runs before implementation.",
        ],
    }
    artifacts = write_phase2_artifacts(
        output_dir=output_dir,
        review_output=review_output,
        proposal=proposal,
        command_log=command_log or [],
    )
    return {
        "review_output": review_output,
        "rule_proposal_v1": proposal,
        "artifacts": artifacts,
    }


def build_live_review_prompt(record: dict[str, Any]) -> str:
    payload = {
        "task": "Review one saved uk_ie_d365_leads deterministic classification decision.",
        "hard_rules": [
            "Use only the provided candidate evidence.",
            "Do not invent companies, URLs, D365 evidence, contacts, emails, source facts, or product usage claims.",
            "Do not run search, browse, resolve contacts, send emails, deploy, or mutate deterministic rules.",
            "This is audit/proposal-only. The LLM reviewer is not the production classifier.",
            "Weak real candidates should be provisional/human-review rather than hard accepted.",
            "Preserve tender/procurement exclusion and no-fake/no-invented-evidence rules.",
        ],
        "allowed_values": {
            "llm_review_decision": sorted(LIVE_REVIEW_DECISIONS),
            "discrepancy_type": sorted(LIVE_DISCREPANCY_TYPES),
            "proposal_impact": sorted(PROPOSAL_IMPACTS),
        },
        "required_output_fields": [
            "llm_review_decision",
            "llm_confidence",
            "discrepancy_type",
            "evidence_used",
            "missing_evidence",
            "deterministic_rule_likely_at_fault",
            "recommended_rule_change",
            "should_promote_to_human_review",
            "should_remain_rejected",
            "notes",
            "proposal_impact",
        ],
        "candidate_record": record,
    }
    return (
        "Return JSON only. Do not wrap in markdown. The JSON must contain exactly "
        "one review object for the provided candidate.\n\n"
        + json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    )


def call_vertex_reviewer(*, client: Any, model: str, prompt: str) -> tuple[str, dict[str, Any], str | None]:
    from google.genai import types

    config = types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=4096,
        response_mime_type="application/json",
    )
    response = client.models.generate_content(model=model, contents=prompt, config=config)
    return getattr(response, "text", "") or "", usage_summary(response), model_version(response)


def parse_review_json(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    if isinstance(value, list):
        if not value or not isinstance(value[0], dict):
            raise ValueError("LLM review returned a list without a review object")
        value = value[0]
    if not isinstance(value, dict):
        raise ValueError("LLM review did not return a JSON object")
    return value


def normalize_live_review_record(
    source_record: dict[str, Any],
    raw: dict[str, Any],
    request_meta: dict[str, Any],
) -> dict[str, Any]:
    decision = str(raw.get("llm_review_decision") or "").strip().lower()
    if decision not in LIVE_REVIEW_DECISIONS:
        decision = "provisional"
    discrepancy = str(raw.get("discrepancy_type") or "").strip().lower()
    if discrepancy not in LIVE_DISCREPANCY_TYPES:
        discrepancy = derive_discrepancy_type(source_record.get("deterministic_decision"), decision)
    proposal_impact = str(raw.get("proposal_impact") or "").strip().lower()
    if proposal_impact not in PROPOSAL_IMPACTS:
        proposal_impact = derive_proposal_impact(discrepancy)

    notes = coerce_list(raw.get("notes"))
    if raw.get("discrepancy_type") not in LIVE_DISCREPANCY_TYPES:
        notes.append("Reviewer discrepancy_type was normalized by the runner.")
    invented = detect_invented_candidate_facts(source_record, raw)
    if invented["invented_candidate_facts_detected"]:
        notes.append("Runner flagged possible invented candidate facts in reviewer output.")

    record = {
        **{field: source_record.get(field) for field in FACTUAL_FIELDS if field in source_record},
        "candidate_id": source_record.get("candidate_id"),
        "company_name": source_record.get("company_name"),
        "source_url_or_redirect_url": source_record.get("source_url_or_redirect_url"),
        "deterministic_decision": source_record.get("deterministic_decision"),
        "deterministic_score_or_tier": source_record.get("deterministic_score_or_tier"),
        "deterministic_rejection_reason": source_record.get("deterministic_rejection_reason"),
        "deterministic_confidence_score": source_record.get("deterministic_confidence_score"),
        "deterministic_urgency_score": source_record.get("deterministic_urgency_score"),
        "deterministic_audit_trace": source_record.get("deterministic_audit_trace"),
        "llm_review_decision": decision,
        "llm_confidence": coerce_confidence(raw.get("llm_confidence")),
        "discrepancy_type": discrepancy,
        "evidence_used": source_record.get("evidence_used"),
        "missing_evidence": sorted(set(coerce_list(source_record.get("missing_evidence")) + coerce_list(raw.get("missing_evidence")))),
        "deterministic_rule_likely_at_fault": nullable_string(raw.get("deterministic_rule_likely_at_fault")),
        "recommended_rule_change": nullable_string(raw.get("recommended_rule_change")),
        "should_promote_to_human_review": coerce_optional_bool(raw.get("should_promote_to_human_review")),
        "should_remain_rejected": coerce_optional_bool(raw.get("should_remain_rejected")),
        "notes": notes,
        "invented_candidate_facts_detected": invented["invented_candidate_facts_detected"],
        "live_llm_used": True,
        "proposal_impact": proposal_impact,
        "schema_validation_status": "pending",
        "review_metadata": {
            **(source_record.get("review_metadata") or {}),
            "live_request_index": request_meta.get("request_index"),
            "model_version": request_meta.get("model_version"),
            "invented_fact_findings": invented["findings"],
        },
    }
    return record


def derive_discrepancy_type(deterministic_decision: str | None, llm_decision: str) -> str:
    if deterministic_decision == "reject" and llm_decision in {"accept", "provisional"}:
        return "false_negative_risk"
    if deterministic_decision in {"accept", "provisional"} and llm_decision == "reject":
        return "false_positive_risk"
    if deterministic_decision == "provisional" and llm_decision == "accept":
        return "tier_mismatch"
    return "no_discrepancy"


def derive_proposal_impact(discrepancy: str) -> str:
    if discrepancy == "false_negative_risk":
        return "suggests_rule_loosen"
    if discrepancy == "false_positive_risk":
        return "suggests_rule_tighten"
    if discrepancy == "tier_mismatch":
        return "suggests_tier_shift"
    if discrepancy == "no_discrepancy":
        return "supports_existing_rule"
    return "needs_more_samples"


def coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [json.dumps(value, sort_keys=True, ensure_ascii=True)]
    text = str(value).strip()
    return [text] if text else []


def nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def coerce_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return None


def coerce_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    return None


def detect_invented_candidate_facts(source_record: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    allowed_urls = set(source_record.get("evidence_used", {}).get("urls") or [])
    if source_record.get("source_url_or_redirect_url"):
        allowed_urls.add(str(source_record["source_url_or_redirect_url"]))
    normalized_allowed_urls = {url.rstrip("/").lower() for url in allowed_urls}
    raw_text = json.dumps(raw, sort_keys=True, ensure_ascii=True)
    findings = []
    for url in re.findall(r"https?://[^\s\"'<>]+", raw_text):
        cleaned = url.rstrip(").,;]")
        if cleaned.rstrip("/").lower() not in normalized_allowed_urls:
            findings.append({"type": "new_url", "value_redacted": True})
    if re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", raw_text, flags=re.IGNORECASE):
        findings.append({"type": "email_like_value", "value_redacted": True})
    return {
        "invented_candidate_facts_detected": bool(findings),
        "findings": findings,
    }


def validate_live_review_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors = []
    required = list(REQUIRED_REVIEW_FIELDS) + ["proposal_impact"]
    for index, record in enumerate(records, start=1):
        missing = [field for field in required if field not in record]
        if missing:
            errors.append({"record_index": index, "missing_fields": missing})
        if record.get("llm_review_decision") not in LIVE_REVIEW_DECISIONS:
            errors.append({"record_index": index, "error": "invalid llm_review_decision"})
        if record.get("discrepancy_type") not in LIVE_DISCREPANCY_TYPES:
            errors.append({"record_index": index, "error": "invalid discrepancy_type"})
        if record.get("proposal_impact") not in PROPOSAL_IMPACTS:
            errors.append({"record_index": index, "error": "invalid proposal_impact"})
        if record.get("live_llm_used") is not True:
            errors.append({"record_index": index, "error": "live_llm_used must be true in Phase 2 live review"})
        record["schema_validation_status"] = "valid" if not missing else "invalid"
    return {
        "valid": not errors,
        "record_count": len(records),
        "errors": errors,
        "schema_version": "2026-05-17.llm-classification-review-live-v1",
    }


def plain(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if hasattr(value, "to_dict"):
        return plain(value.to_dict())
    if hasattr(value, "model_dump"):
        return plain(value.model_dump())
    if hasattr(value, "__dict__"):
        return {
            key: plain(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return str(value)


def int_metric(data: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
    return 0


def usage_summary(response: Any) -> dict[str, Any]:
    usage = plain(getattr(response, "usage_metadata", None) or getattr(response, "usageMetadata", None)) or {}
    prompt_tokens = int_metric(usage, "prompt_token_count", "promptTokenCount")
    candidates_tokens = int_metric(usage, "candidates_token_count", "candidatesTokenCount")
    thoughts_tokens = int_metric(usage, "thoughts_token_count", "thoughtsTokenCount")
    total_tokens = int_metric(usage, "total_token_count", "totalTokenCount")
    cached_tokens = int_metric(usage, "cached_content_token_count", "cachedContentTokenCount")
    tool_tokens = int_metric(usage, "tool_use_prompt_token_count", "toolUsePromptTokenCount")
    return {
        "raw_usage_metadata": usage,
        "prompt_token_count": prompt_tokens,
        "candidates_token_count": candidates_tokens,
        "thoughts_token_count": thoughts_tokens,
        "total_token_count": total_tokens,
        "cached_content_token_count": cached_tokens,
        "tool_use_prompt_token_count": tool_tokens,
        "input_tokens_for_cost": prompt_tokens + tool_tokens,
        "output_tokens_for_cost": candidates_tokens + thoughts_tokens,
    }


def model_version(response: Any) -> str | None:
    value = getattr(response, "model_version", None) or getattr(response, "modelVersion", None)
    return str(value) if value else None


def sum_token_usage(requests: list[dict[str, Any]]) -> dict[str, int]:
    fields = [
        "prompt_token_count",
        "candidates_token_count",
        "thoughts_token_count",
        "total_token_count",
        "cached_content_token_count",
        "tool_use_prompt_token_count",
        "input_tokens_for_cost",
        "output_tokens_for_cost",
    ]
    return {
        field: sum(int((request.get("usage_metadata") or {}).get(field) or 0) for request in requests)
        for field in fields
    }


def live_review_counts(
    data: dict[str, Any],
    selected_source_records: list[dict[str, Any]],
    records: list[dict[str, Any]],
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    deterministic_accept_count = sum(1 for record in records if record.get("deterministic_decision") == "accept")
    deterministic_reject_count = sum(1 for record in records if record.get("deterministic_decision") == "reject")
    deterministic_provisional_count = sum(1 for record in records if record.get("deterministic_decision") == "provisional")
    discrepancy_counts = Counter(record.get("discrepancy_type") for record in records)
    llm_counts = Counter(record.get("llm_review_decision") for record in records)
    return {
        "candidates_loaded": len(all_candidates(data)),
        "candidates_prepared_for_review": len(selected_source_records),
        "candidates_reviewed_by_llm": len(records),
        "live_request_count": len(requests),
        "token_usage": sum_token_usage(requests),
        "deterministic_accept_count": deterministic_accept_count,
        "deterministic_reject_count": deterministic_reject_count,
        "deterministic_provisional_or_human_review_count": deterministic_provisional_count,
        "llm_accept_count": llm_counts.get("accept", 0),
        "llm_provisional_count": llm_counts.get("provisional", 0),
        "llm_reject_count": llm_counts.get("reject", 0),
        "llm_discrepancy_count": sum(count for key, count in discrepancy_counts.items() if key != "no_discrepancy"),
        "suspected_false_negative_count": discrepancy_counts.get("false_negative_risk", 0),
        "suspected_false_positive_count": discrepancy_counts.get("false_positive_risk", 0),
        "tier_mismatch_count": discrepancy_counts.get("tier_mismatch", 0),
        "reason_mismatch_count": discrepancy_counts.get("reason_mismatch", 0),
        "no_discrepancy_count": discrepancy_counts.get("no_discrepancy", 0),
    }


def build_phase2_metadata(
    *,
    data: dict[str, Any],
    evidence_file: Path | str,
    counts: dict[str, Any],
    reconstruction_records: list[dict[str, Any]],
    validation: dict[str, Any],
    invented_check: dict[str, Any],
    client_info: dict[str, Any],
    started_at: str,
    finished_at: str,
    git_metadata: dict[str, Any],
) -> dict[str, Any]:
    audit = data.get("audit_metadata") or {}
    return {
        "review_schema_version": validation["schema_version"],
        "generated_at": datetime.now(UTC).isoformat(),
        "phase": "Phase 2 live LLM review",
        "input_file": str(Path(evidence_file)),
        "source_provider": data.get("provider") or audit.get("search_provider"),
        "source_model": audit.get("effective_model_name"),
        "dry_run_mode_executed": False,
        "live_llm_mode_executed": True,
        "live_llm_used": True,
        "live_request_count": counts["live_request_count"],
        "token_usage": counts["token_usage"],
        "reviewer_is_real_adk_agent": True,
        "reviewer_attached_to_root_as_sub_agent": True,
        "reviewer_attach_reason": "Opt-in local audit specialist; no lead-discovery tools or rule-mutation tools were added.",
        "normal_discovery_behavior_impact": "unchanged; root tools and deterministic classifier behavior were not changed.",
        "model_used": client_info.get("model"),
        "provider_path": client_info.get("provider_path"),
        "project": client_info.get("project"),
        "location": client_info.get("location"),
        "auth_mode": client_info.get("auth_mode"),
        "client_constructor": client_info.get("client_constructor"),
        "run_started_at": started_at,
        "run_finished_at": finished_at,
        "deterministic_rules_changed": False,
        "deployment_attempted": False,
        "gcloud_called": False,
        "agents_cli_deploy_called": False,
        "source_of_truth_fields": list(SOURCE_OF_TRUTH_FIELDS),
        "reconstruction_count": len(reconstruction_records),
        "schema_validation_result": "PASS" if validation["valid"] else "FAIL",
        "invented_candidate_facts_check_result": "PASS" if invented_check["passed"] else "FAIL",
        "git_metadata": git_metadata,
    }


def build_rule_proposal_v1(records: list[dict[str, Any]], counts: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        key = "|".join(
            [
                str(record.get("discrepancy_type")),
                str(record.get("proposal_impact")),
                str(record.get("deterministic_rule_likely_at_fault") or "unspecified_rule"),
                str(record.get("recommended_rule_change") or "no_change_recommended"),
            ]
        )
        group = grouped.setdefault(
            key,
            {
                "discrepancy_type": record.get("discrepancy_type"),
                "proposal_impact": record.get("proposal_impact"),
                "deterministic_rule_likely_at_fault": record.get("deterministic_rule_likely_at_fault"),
                "recommended_rule_change": record.get("recommended_rule_change"),
                "candidate_count": 0,
                "candidate_ids": [],
                "company_names": [],
            },
        )
        group["candidate_count"] += 1
        group["candidate_ids"].append(record.get("candidate_id"))
        group["company_names"].append(record.get("company_name"))

    proposals = []
    for group in sorted(grouped.values(), key=lambda item: item["candidate_count"], reverse=True):
        count = group["candidate_count"]
        if count >= 3:
            confidence = "high-confidence repeated pattern"
        elif count == 2:
            confidence = "medium-confidence pattern"
        else:
            confidence = "low-confidence / needs more runs"
        proposals.append({**group, "proposal_confidence": confidence})

    summary = {
        "proposal_version": "v1",
        "candidate_count": len(records),
        "discrepancy_count": counts["llm_discrepancy_count"],
        "suspected_false_negative_count": counts["suspected_false_negative_count"],
        "suspected_false_positive_count": counts["suspected_false_positive_count"],
        "proposal_count": len(proposals),
        "top_patterns": proposals[:8],
        "deterministic_rules_changed": False,
    }
    return {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "proposal_version": "v1",
            "policy": "Proposal only; no deterministic rule changes were made.",
            "convergence_definition": [
                "The same failure pattern appears across multiple review runs or labeled batches.",
                "Later LLM review runs stop creating significant new rule-change categories.",
                "The change can be expressed deterministically.",
                "Tests can be written for the rule.",
                "The change does not create fake/invented evidence.",
                "The change does not weaken tender/procurement exclusion.",
                "The change improves recall without unacceptable precision loss.",
            ],
        },
        "summary": summary,
        "proposals": proposals,
        "preservation_rules": [
            "Preserve tender/procurement exclusion.",
            "Preserve no-fake/no-invented-evidence.",
            "Weak real candidates should become provisional/human-review rather than hard accepted.",
            "False negatives are worse than low-confidence real false positives.",
        ],
    }


def write_phase2_artifacts(
    *,
    output_dir: Path,
    review_output: dict[str, Any],
    proposal: dict[str, Any],
    command_log: list[str],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = phase2_artifact_paths(output_dir)
    write_json(paths["review_json"], review_output)
    paths["review_md"].write_text(render_phase2_review_markdown(review_output), encoding="utf-8")
    write_json(paths["rule_proposal_json"], proposal)
    paths["rule_proposal_md"].write_text(render_rule_proposal_markdown(proposal), encoding="utf-8")
    paths["report"].write_text(render_phase2_report(review_output, proposal, command_log, paths), encoding="utf-8")
    scan = scan_secret_patterns(
        [
            paths["review_json"],
            paths["review_md"],
            paths["rule_proposal_json"],
            paths["rule_proposal_md"],
            paths["report"],
        ]
    )
    write_json(paths["secret_scan"], scan)
    manifest = build_phase2_manifest(paths, scan)
    write_json(paths["manifest"], manifest)
    create_phase2_evidence_zip(paths)
    return {name: str(path) for name, path in paths.items()}


def phase2_artifact_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "review_json": output_dir / f"{PHASE2_OUTPUT_BASENAME}.json",
        "review_md": output_dir / f"{PHASE2_OUTPUT_BASENAME}.md",
        "report": output_dir / f"{PHASE2_OUTPUT_BASENAME}_REPORT.md",
        "rule_proposal_json": output_dir / "UK_IE_D365_LLM_CLASSIFICATION_RULE_PROPOSAL_V1.json",
        "rule_proposal_md": output_dir / "UK_IE_D365_LLM_CLASSIFICATION_RULE_PROPOSAL_V1.md",
        "secret_scan": output_dir / f"{PHASE2_OUTPUT_BASENAME}_SECRET_SCAN.json",
        "manifest": output_dir / f"{PHASE2_OUTPUT_BASENAME}_EVIDENCE_MANIFEST.json",
        "zip": output_dir / f"{PHASE2_OUTPUT_BASENAME}_EVIDENCE.zip",
    }


def render_phase2_review_markdown(output: dict[str, Any]) -> str:
    metadata = output["metadata"]
    counts = output["counts"]
    lines = [
        "# UK/IE D365 LLM Classification Review - Phase 2",
        "",
        "## Summary",
        f"- Live LLM used: `{metadata['live_llm_used']}`",
        f"- Model: `{metadata['model_used']}`",
        f"- Provider path: `{metadata['provider_path']}`",
        f"- Project: `{metadata['project']}`",
        f"- Location: `{metadata['location']}`",
        f"- Live request count: `{metadata['live_request_count']}`",
        f"- Candidates reviewed by LLM: {counts['candidates_reviewed_by_llm']}",
        f"- LLM accept/provisional/reject: {counts['llm_accept_count']}/{counts['llm_provisional_count']}/{counts['llm_reject_count']}",
        f"- Discrepancies: {counts['llm_discrepancy_count']}",
        f"- Suspected false negatives: {counts['suspected_false_negative_count']}",
        f"- Suspected false positives: {counts['suspected_false_positive_count']}",
        "- Deterministic rules changed: no",
        "",
        "## Reviewed Candidates",
        "",
    ]
    for record in output["review_records"]:
        lines.append(
            f"- `{record['candidate_id']}` {record.get('company_name')}: "
            f"deterministic `{record.get('deterministic_decision')}` -> "
            f"LLM `{record.get('llm_review_decision')}` "
            f"({record.get('discrepancy_type')})"
        )
    return "\n".join(lines) + "\n"


def render_rule_proposal_markdown(proposal: dict[str, Any]) -> str:
    lines = [
        "# UK/IE D365 LLM Classification Rule Proposal v1",
        "",
        "This is proposal-only. No deterministic rules were changed.",
        "",
        "## Summary",
        f"- Candidates reviewed: {proposal['summary']['candidate_count']}",
        f"- Discrepancies: {proposal['summary']['discrepancy_count']}",
        f"- Suspected false negatives: {proposal['summary']['suspected_false_negative_count']}",
        f"- Suspected false positives: {proposal['summary']['suspected_false_positive_count']}",
        "",
        "## Proposal Patterns",
        "",
    ]
    for item in proposal["proposals"]:
        lines.append(
            f"- {item['proposal_confidence']}: `{item['discrepancy_type']}` / "
            f"`{item['proposal_impact']}` / `{item.get('deterministic_rule_likely_at_fault')}` "
            f"({item['candidate_count']} candidates)"
        )
        if item.get("recommended_rule_change"):
            lines.append(f"  Recommendation: {item['recommended_rule_change']}")
    lines.extend(
        [
            "",
            "## Preservation Rules",
            "- Preserve tender/procurement exclusion.",
            "- Preserve no-fake/no-invented-evidence.",
            "- Weak real candidates should become provisional/human-review rather than hard accepted.",
            "- False negatives are worse than low-confidence real false positives.",
            "",
            "## Why No Rule Change Yet",
            "This single bounded run is not enough to change deterministic classifier rules. Future changes should wait for proposal convergence across multiple runs or labeled batches.",
            "",
            "## Proposal Convergence",
        ]
    )
    lines.extend([f"- {item}" for item in proposal["metadata"]["convergence_definition"]])
    return "\n".join(lines) + "\n"


def render_phase2_report(
    output: dict[str, Any],
    proposal: dict[str, Any],
    command_log: list[str],
    paths: dict[str, Path],
) -> str:
    metadata = output["metadata"]
    counts = output["counts"]
    lines = [
        "# UK/IE D365 LLM Classification Review Phase 2 Report",
        "",
        "## Files Inspected",
        "- `uk_ie_d365_leads/agents/classification_reviewer_agent.py`",
        "- `uk_ie_d365_leads/tools/classification_review_tools.py`",
        "- `tools/run_uk_ie_d365_llm_classification_review.py`",
        "- `uk_ie_d365_leads/agent.py`",
        "- `uk_ie_d365_leads/agents/search_agent.py`",
        "- `uk_ie_d365_leads/tools/lead_tools.py`",
        "- `uk_ie_d365_leads/tests/test_uk_ie_d365_leads.py`",
        "- `Evidence/UK_IE_D365_LLM_CLASSIFICATION_REVIEW_INPUT_BATCH.json`",
        "- `Evidence/UK_IE_D365_LLM_CLASSIFICATION_REVIEW_REPORT.md`",
        "- `Evidence/UK_IE_D365_LLM_CLASSIFICATION_REVIEW_RULE_CHANGE_PLAN.md`",
        "",
        "## Files Changed",
        "- `uk_ie_d365_leads/agents/classification_reviewer_agent.py`",
        "- `uk_ie_d365_leads/tools/classification_review_tools.py`",
        "- `tools/run_uk_ie_d365_llm_classification_review.py`",
        "- `uk_ie_d365_leads/agent.py`",
        "- `uk_ie_d365_leads/tests/test_uk_ie_d365_leads.py`",
        "- Phase 2 evidence artifacts listed in the manifest",
        "",
        "## Commands Run",
    ]
    lines.extend([f"- `{command}`" for command in command_log])
    lines.extend(
        [
            "",
            "## Execution",
            f"- Reviewer is real ADK agent: {metadata['reviewer_is_real_adk_agent']}",
            f"- Reviewer attached to root as sub-agent: {metadata['reviewer_attached_to_root_as_sub_agent']}",
            f"- Attach/not-attach reason: {metadata['reviewer_attach_reason']}",
            f"- Normal discovery behavior impact: {metadata['normal_discovery_behavior_impact']}",
            f"- Model used: {metadata['model_used']}",
            f"- Provider path: {metadata['provider_path']}",
            f"- Project: {metadata['project']}",
            f"- Location: {metadata['location']}",
            f"- Live request count: {metadata['live_request_count']}",
            f"- Token usage: {json.dumps(metadata['token_usage'], sort_keys=True)}",
            f"- Candidates loaded: {counts['candidates_loaded']}",
            f"- Candidates reviewed by LLM: {counts['candidates_reviewed_by_llm']}",
            f"- Deterministic accept/reject/provisional counts: {counts['deterministic_accept_count']}/{counts['deterministic_reject_count']}/{counts['deterministic_provisional_or_human_review_count']}",
            f"- LLM accept/provisional/reject counts: {counts['llm_accept_count']}/{counts['llm_provisional_count']}/{counts['llm_reject_count']}",
            f"- Discrepancy count: {counts['llm_discrepancy_count']}",
            f"- Suspected false negatives: {counts['suspected_false_negative_count']}",
            f"- Suspected false positives: {counts['suspected_false_positive_count']}",
            f"- Tier mismatches: {counts['tier_mismatch_count']}",
            f"- Reason mismatches: {counts['reason_mismatch_count']}",
            f"- No-discrepancy count: {counts['no_discrepancy_count']}",
            f"- Invented candidate facts check: {metadata['invented_candidate_facts_check_result']}",
            "- Deterministic rules changed: no",
            "- Deployment/register/push attempted: no",
            "",
            "## Rule Proposal v1 Summary",
            f"- Proposal path: `{paths['rule_proposal_md']}`",
            f"- Proposal patterns: {proposal['summary']['proposal_count']}",
            "",
            "## Tests And Safety",
            "- Tests run are recorded in the command log and final verification.",
            "- Secret scan result: see secret scan artifact.",
            f"- Git status before/after: {json.dumps(metadata.get('git_metadata', {}), sort_keys=True)}",
            f"- Evidence ZIP path: `{paths['zip']}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_phase2_manifest(paths: dict[str, Path], scan: dict[str, Any]) -> dict[str, Any]:
    included_keys = [
        "review_json",
        "review_md",
        "report",
        "rule_proposal_json",
        "rule_proposal_md",
        "secret_scan",
        "manifest",
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "zip_path": str(paths["zip"]),
        "included_files": [
            {"name": key, "path": str(paths[key]), "size_bytes": paths[key].stat().st_size if paths[key].exists() else 0}
            for key in included_keys
        ],
        "excluded_patterns": [
            ".git",
            ".env",
            ".local_secrets",
            "ADC files",
            "service account keys",
            "caches",
            "unrelated Evidence files",
            "older Evidence ZIPs",
        ],
        "secret_scan_result": scan.get("result"),
        "secret_findings_count": scan.get("findings_count"),
    }


def create_phase2_evidence_zip(paths: dict[str, Path]) -> None:
    include_keys = [
        "review_json",
        "review_md",
        "report",
        "rule_proposal_json",
        "rule_proposal_md",
        "secret_scan",
        "manifest",
    ]
    with zipfile.ZipFile(paths["zip"], "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for key in include_keys:
            archive.write(paths[key], arcname=paths[key].name)
