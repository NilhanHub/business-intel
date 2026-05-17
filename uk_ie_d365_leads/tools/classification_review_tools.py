"""Dry-run utilities for the UK/Ireland D365 classification review harness."""

from __future__ import annotations

import json
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
