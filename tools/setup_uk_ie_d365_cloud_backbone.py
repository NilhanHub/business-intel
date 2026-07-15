"""Provision or preflight the UK/IE D365 lead-conservation cloud backbone.

Default mode is read-only preflight. Use --apply to create the BigQuery dataset,
BigQuery tables, and Cloud Storage evidence bucket with gcloud/bq if available.
Memory Bank and Agent Search readiness are reported, but not force-created by
this script because their exact Agent Platform binding depends on the deployed
Reasoning Engine and Gemini Enterprise app configuration.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uk_ie_d365_leads.tools import discovery_backbone_tools

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = PROJECT_ROOT / "Evidence"
DEFAULT_PROJECT = "business-intel-123"
DEFAULT_LOCATION = "us-central1"
DEFAULT_BQ_LOCATION = "US"
DEFAULT_DATASET = "business_intel_leads"
DEFAULT_BUCKET = "business-intel-123-business-intel-evidence"

TABLE_SCHEMAS = {
    "runs": "run_id:STRING,started_at:TIMESTAMP,finished_at:TIMESTAMP,provider_path:STRING,project:STRING,location:STRING,completion_status:STRING",
    "candidates": "run_id:STRING,candidate_id:STRING,company_name:STRING,retention_status:STRING,company_fingerprint:STRING,opportunity_fingerprint:STRING,source_fingerprint:STRING,evidence_url:STRING,reason:STRING,source_channel:STRING,final_pdf_eligible:BOOLEAN",
    "sources": "run_id:STRING,candidate_id:STRING,url:STRING,final_url:STRING,source_name:STRING,verified_live:BOOLEAN,http_status:INTEGER,fetched_at:TIMESTAMP,source_channel:STRING",
    "identity_resolution": "run_id:STRING,candidate_id:STRING,company_name:STRING,source_company:STRING,source_role:STRING,account_identity_status:STRING,identity_resolution_required:BOOLEAN",
    "vetting_decisions": "run_id:STRING,candidate_id:STRING,lead_status:STRING,signal_strength:STRING,signal_type:STRING,final_rejection_reason:STRING",
    "duplicate_fingerprints": "company_fingerprint:STRING,opportunity_fingerprint:STRING,company_name:STRING,reason:STRING,observed_at:TIMESTAMP",
    "final_leads": "run_id:STRING,candidate_id:STRING,rank:INTEGER,company_name:STRING,evidence_url:STRING,verified_live:BOOLEAN,signal_strength:STRING,lead_status:STRING,source_channel:STRING,final_pdf_eligible:BOOLEAN",
    "eval_results": "eval_id:STRING,run_id:STRING,passed:BOOLEAN,score:FLOAT,created_at:TIMESTAMP,notes:STRING",
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", default=DEFAULT_PROJECT)
    p.add_argument("--location", default=DEFAULT_LOCATION)
    p.add_argument("--bq-location", default=DEFAULT_BQ_LOCATION)
    p.add_argument("--dataset", default=DEFAULT_DATASET)
    p.add_argument("--bucket", default=DEFAULT_BUCKET)
    p.add_argument("--apply", action="store_true", help="Create BigQuery/GCS resources if missing.")
    p.add_argument("--mirror-evidence", action="store_true", help="Copy local Evidence JSON/MD/PDF artifacts to GCS. Requires --apply.")
    p.add_argument("--skip-local-artifacts", action="store_true", help="Skip writing local Agent Search/BigQuery mirror inputs.")
    p.add_argument("--evidence-dir", default=str(EVIDENCE_DIR))
    return p


def run_command(args: list[str], *, timeout: int = 120) -> dict[str, Any]:
    executable = shutil.which(args[0]) or args[0]
    resolved_args = [executable, *args[1:]]
    try:
        completed = subprocess.run(
            resolved_args,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": redact_command(args),
            "resolved_executable": executable,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "ok": completed.returncode == 0,
        }
    except FileNotFoundError as exc:
        return {"command": redact_command(args), "resolved_executable": executable, "ok": False, "returncode": None, "stderr": str(exc), "stdout": ""}
    except subprocess.TimeoutExpired as exc:
        return {"command": redact_command(args), "resolved_executable": executable, "ok": False, "returncode": None, "stderr": f"timed out after {exc.timeout}s", "stdout": ""}


def redact_command(args: list[str]) -> list[str]:
    redacted = []
    for item in args:
        if "key" in item.lower() or "token" in item.lower() or "secret" in item.lower():
            redacted.append("***")
        else:
            redacted.append(item)
    return redacted


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def preflight(project: str, bucket: str, dataset: str) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "gcloud_available": command_exists("gcloud"),
        "bq_available": command_exists("bq"),
        "project": project,
        "bucket": bucket,
        "dataset": dataset,
        "commands": [],
    }
    if checks["gcloud_available"]:
        checks["commands"].append(run_command(["gcloud", "config", "get-value", "account"]))
        checks["commands"].append(run_command(["gcloud", "config", "get-value", "project"]))
        checks["commands"].append(run_command(["gcloud", "services", "list", "--enabled", "--project", project, "--format=json"], timeout=180))
        checks["commands"].append(run_command(["gcloud", "storage", "buckets", "describe", f"gs://{bucket}", "--project", project, "--format=json"]))
    if checks["bq_available"]:
        checks["commands"].append(run_command(["bq", "--project_id", project, "show", f"{project}:{dataset}"]))
    return checks


def apply_resources(project: str, bucket: str, dataset: str, bq_location: str) -> list[dict[str, Any]]:
    results = []
    if command_exists("bq"):
        results.append(run_command(["bq", "--project_id", project, "mk", "--location", bq_location, "--dataset", f"{project}:{dataset}"]))
        for table, schema in TABLE_SCHEMAS.items():
            results.append(run_command(["bq", "--project_id", project, "mk", "--table", f"{project}:{dataset}.{table}", schema]))
    else:
        results.append({"command": ["bq"], "ok": False, "stderr": "bq CLI not found", "stdout": "", "returncode": None})

    if command_exists("gcloud"):
        results.append(
            run_command(
                [
                    "gcloud",
                    "storage",
                    "buckets",
                    "create",
                    f"gs://{bucket}",
                    "--project",
                    project,
                    "--location",
                    bq_location,
                    "--uniform-bucket-level-access",
                ]
            )
        )
    else:
        results.append({"command": ["gcloud"], "ok": False, "stderr": "gcloud CLI not found", "stdout": "", "returncode": None})
    return results


def mirror_evidence(evidence_dir: Path, bucket: str) -> list[dict[str, Any]]:
    if not command_exists("gcloud"):
        return [{"command": ["gcloud"], "ok": False, "stderr": "gcloud CLI not found", "stdout": "", "returncode": None}]
    results = []
    for path in sorted(evidence_dir.glob("*")):
        if path.suffix.lower() not in {".json", ".md", ".pdf"} or not path.is_file():
            continue
        results.append(run_command(["gcloud", "storage", "cp", str(path), f"gs://{bucket}/Evidence/{path.name}"], timeout=240))
    return results


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# UK/IE D365 Cloud Backbone Setup",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Project: `{report['project']}`",
        f"- Region: `{report['location']}`",
        f"- Apply mode: `{str(report['apply']).lower()}`",
        f"- Dataset: `{report['dataset']}`",
        f"- Bucket: `gs://{report['bucket']}`",
        "",
        "## Status",
        "",
        f"- BigQuery/GCS command attempts: {len(report.get('apply_results') or [])}",
        f"- Evidence mirror attempts: {len(report.get('mirror_results') or [])}",
        "- Memory Bank: recorded as required Agent Platform binding; no memory mutation performed by this script.",
        "- Agent Search / Discovery Engine: recorded as required evidence-index binding; no datastore mutation performed by this script.",
        "- Cloud Trace/Logging: expected through Agent Platform/runtime instrumentation; no runtime deployment performed by this script.",
        "",
        "## Local Backbone Artifacts",
        "",
    ]
    local_artifacts = report.get("local_backbone_artifacts") or {}
    if local_artifacts:
        for key, value in local_artifacts.items():
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("- Skipped.")
    lines.extend(
        [
            "",
            "## Failed Commands",
            "",
        ]
    )
    failed = [
        item
        for group in ("preflight", "apply_results", "mirror_results")
        for item in (report.get(group, {}).get("commands", []) if group == "preflight" else report.get(group, []) or [])
        if not item.get("ok")
    ]
    if not failed:
        lines.append("- None")
    else:
        for item in failed:
            lines.append(f"- `{item.get('command')}` -> {item.get('stderr') or item.get('stdout')}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    evidence_dir = Path(args.evidence_dir)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    report: dict[str, Any] = {
        "artifact_type": "uk_ie_d365_cloud_backbone_setup",
        "generated_at": generated_at,
        "project": args.project,
        "location": args.location,
        "dataset": args.dataset,
        "bucket": args.bucket,
        "apply": bool(args.apply),
        "mirror_evidence": bool(args.mirror_evidence),
        "table_schemas": TABLE_SCHEMAS,
        "preflight": preflight(args.project, args.bucket, args.dataset),
        "agent_platform_hooks": {
            "memory_bank": "Store prior companies, opportunity fingerprints, rejected patterns, and query/source patterns once Agent Platform binding is configured.",
            "agent_platform_sessions": "Use deployed Agent Runtime sessions to preserve discovery/vetting traces across runs.",
            "agent_search": "Index Evidence artifacts, PDFs, source maps, final leads, rejected candidates, and cleanup queues in a dedicated Discovery Engine data store.",
            "cloud_trace_logging": "Trace search, candidate creation, identity resolution, URL cleanup, vetting, duplicate decisions, and final selection.",
        },
    }
    report["local_backbone_artifacts"] = (
        {}
        if args.skip_local_artifacts
        else discovery_backbone_tools.write_local_backbone_artifacts(
            evidence_dir=evidence_dir,
            output_dir=EVIDENCE_DIR,
            project=args.project,
            location=args.location,
            dataset=args.dataset,
            bucket=args.bucket,
            timestamp=timestamp,
        )
    )
    if report["local_backbone_artifacts"]:
        report["local_backbone_artifact_note"] = (
            "These files are local dry-run inputs for Agent Search import, Memory Bank preflight, "
            "BigQuery ledger mirroring, and evidence-lake planning. They do not create cloud resources."
        )
    report["apply_results"] = apply_resources(args.project, args.bucket, args.dataset, args.bq_location) if args.apply else []
    report["mirror_results"] = mirror_evidence(evidence_dir, args.bucket) if args.apply and args.mirror_evidence else []

    json_path = EVIDENCE_DIR / f"UK_IE_D365_CLOUD_BACKBONE_SETUP_{timestamp}.json"
    md_path = EVIDENCE_DIR / f"UK_IE_D365_CLOUD_BACKBONE_SETUP_{timestamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
