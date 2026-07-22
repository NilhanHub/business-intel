"""Local Google ecosystem backbone helpers for UK/IE D365 discovery.

The functions in this module are intentionally local and dry-run by default.
They prepare the artifacts needed by Agent Search, Memory Bank, Sessions,
BigQuery, GCS, and observability without creating or mutating cloud resources.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import urllib.parse
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = PROJECT_ROOT / "Evidence"
DEFAULT_PROJECT = "business-intel-123"
DEFAULT_LOCATION = "us-central1"
DEFAULT_DATASET = "business_intel_leads"
DEFAULT_BUCKET = "business-intel-123-business-intel-evidence"
DISCOVERY_BACKBONE_VERSION = "2026-06-25.google-ecosystem-lead-discovery-v1"

SOURCE_CHANNELS = {
    "public_web",
    "agent_search",
    "workspace_hint",
    "crm_hint",
    "custom_mcp",
    "unknown",
}

PUBLIC_WEB_PROVIDERS = {
    "google_grounding",
    "adk_google_search",
    "custom_search_api",
    "tavily",
    "exa",
    "serper",
    "serpapi",
    "firecrawl",
    "unit",
    "saved_replay",
}

TABLE_NAMES = (
    "runs",
    "candidates",
    "sources",
    "identity_resolution",
    "vetting_decisions",
    "duplicate_fingerprints",
    "final_leads",
    "eval_results",
)

GENERIC_OR_BLOCKED_DOMAINS = {
    "google.com",
    "cloud.google.com",
    "vertexaisearch.cloud.google.com",
    "linkedin.com",
    "example.com",
    "example.org",
    "example.net",
    "example.test",
}


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def classify_source_channel(
    *,
    source: str | None = None,
    provider_path: str | None = None,
    url: str | None = None,
    explicit: str | None = None,
) -> str:
    """Classify how a candidate entered the pipeline."""
    if explicit in SOURCE_CHANNELS:
        return str(explicit)
    text = " ".join(str(value or "").lower() for value in (source, provider_path, url))
    provider = str(source or provider_path or "").strip().lower()
    if provider in PUBLIC_WEB_PROVIDERS:
        return "public_web"
    if any(token in text for token in ("agent_search", "discovery engine", "vertex_ai_search", "vertex ai search")):
        return "agent_search"
    if any(token in text for token in ("gmail", "google_mail", "google drive", "googledrive", "google_chat", "workspace")):
        return "workspace_hint"
    if any(token in text for token in ("salesforce", "hubspot", "dynamics365 connector", "crm_hint")):
        return "crm_hint"
    if any(token in text for token in ("custom_mcp", "mcp", "api registry", "api_registry")):
        return "custom_mcp"
    return "unknown"


def source_channel_policy() -> dict[str, Any]:
    return {
        "allowed_channels": sorted(SOURCE_CHANNELS),
        "final_pdf_rule": "Only public_web candidates with verified public evidence may be included in final PDFs.",
        "hint_channels": ["agent_search", "workspace_hint", "crm_hint", "custom_mcp"],
        "hint_rule": "Hint channels may create candidates and next actions, but must be backed by public_web evidence before final publication.",
    }


def final_pdf_eligible_from_channel(source_channel: str | None) -> bool:
    return source_channel == "public_web"


def build_discovery_preflight(
    *,
    evidence_dir: Path | str = EVIDENCE_DIR,
    project: str = DEFAULT_PROJECT,
    location: str = DEFAULT_LOCATION,
    dataset: str = DEFAULT_DATASET,
    bucket: str = DEFAULT_BUCKET,
) -> dict[str, Any]:
    evidence_path = Path(evidence_dir)
    inventory = build_evidence_inventory(evidence_path, bucket=bucket)
    memory = build_memory_preflight(evidence_path)
    return {
        "artifact_type": "uk_ie_d365_cloud_discovery_preflight",
        "generated_at": now_utc(),
        "version": DISCOVERY_BACKBONE_VERSION,
        "project": project,
        "location": location,
        "dataset": dataset,
        "bucket": bucket,
        "mutation_mode": "read_only_preflight",
        "source_channel_policy": source_channel_policy(),
        "memory_preflight": memory,
        "evidence_inventory": {
            "document_count": len(inventory),
            "documents": inventory[:200],
        },
        "service_plan": service_plan(project=project, location=location, dataset=dataset, bucket=bucket),
        "local_readiness": local_readiness(),
    }


def service_plan(*, project: str, location: str, dataset: str, bucket: str) -> dict[str, Any]:
    return {
        "agent_search": {
            "status": "planned_requires_cloud_binding",
            "input": f"gs://{bucket}/Evidence plus metadata manifest",
            "purpose": "Search prior PDFs, source maps, final leads, rejects, cleanup queues, and known-good source domains before web search.",
        },
        "memory_bank": {
            "status": "planned_requires_agent_platform_memory_bank",
            "scope": "uk_ie_d365_leads",
            "purpose": "Remember prior companies, opportunity fingerprints, rejected patterns, and successful search/source patterns.",
        },
        "agent_platform_sessions": {
            "status": "planned_requires_agent_runtime_binding",
            "location": location,
            "purpose": "Preserve discovery, vetting, cleanup, and selection traces across runs.",
        },
        "bigquery": {
            "status": "planned_or_preflighted",
            "dataset": f"{project}.{dataset}",
            "tables": list(TABLE_NAMES),
        },
        "gcs": {
            "status": "planned_or_preflighted",
            "bucket": f"gs://{bucket}",
            "purpose": "Durable evidence lake and Agent Search import source.",
        },
        "document_ai_layout_parser": {
            "status": "planned_optional",
            "purpose": "Parse partner PDFs, case studies, and image-heavy PDFs before identity resolution.",
        },
        "scheduler_cloud_run": {
            "status": "planned_optional",
            "purpose": "Run bounded discovery sweeps and write shortage reports on a schedule.",
        },
        "observability": {
            "status": "planned_or_runtime_default",
            "purpose": "Trace search, identity, URL cleanup, vetting, duplicate decisions, and final selection.",
        },
    }


def local_readiness() -> dict[str, Any]:
    return {
        "gcloud_available": shutil.which("gcloud") is not None,
        "bq_available": shutil.which("bq") is not None,
        "env_presence": {
            name: "present" if os.environ.get(name) else "missing"
            for name in (
                "GOOGLE_GENAI_USE_VERTEXAI",
                "GOOGLE_CLOUD_PROJECT",
                "GOOGLE_CLOUD_LOCATION",
                "D365_AGENT_SEARCH_DATASTORE_ID",
                "D365_MEMORY_BANK_RESOURCE",
                "D365_AGENT_PLATFORM_SESSION_RESOURCE",
                "D365_EVIDENCE_BUCKET",
                "D365_DOCUMENT_AI_PROCESSOR",
            )
        },
    }


def build_evidence_inventory(evidence_dir: Path, *, bucket: str | None = None) -> list[dict[str, Any]]:
    if not evidence_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(evidence_dir.rglob("*")):
        if not path.is_file() or not is_indexable_evidence_file(path):
            continue
        rel = path.relative_to(evidence_dir).as_posix()
        stat = path.stat()
        artifact_type = ""
        if path.suffix.lower() == ".json" and stat.st_size <= 5_000_000:
            payload = safe_read_json(path)
            artifact_type = artifact_type_from_json(payload)
        rows.append(
            {
                "document_id": stable_id("doc", rel),
                "file_name": path.name,
                "relative_path": rel,
                "suffix": path.suffix.lower(),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                "artifact_type": artifact_type,
                "mime_type": mime_type_for_path(path),
                "gcs_uri": f"gs://{bucket}/Evidence/{rel}" if bucket else None,
                "source_channel": "agent_search",
            }
        )
    return rows


def is_indexable_evidence_file(path: Path) -> bool:
    if path.suffix.lower() not in {".json", ".jsonl", ".ndjson", ".md", ".pdf", ".html", ".txt"}:
        return False
    return path.name.startswith("UK_IE_D365") or path.parent.name == "PDFs"


def mime_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".json": "application/json",
        ".jsonl": "application/json",
        ".ndjson": "application/json",
        ".md": "text/markdown",
        ".pdf": "application/pdf",
        ".html": "text/html",
        ".txt": "text/plain",
    }.get(suffix, "application/octet-stream")


def safe_read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def artifact_type_from_json(payload: Any) -> str:
    if isinstance(payload, dict):
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        return str(payload.get("artifact_type") or metadata.get("artifact_type") or "")
    return ""


def build_memory_preflight(evidence_dir: Path) -> dict[str, Any]:
    companies: set[str] = set()
    company_fingerprints: set[str] = set()
    opportunity_fingerprints: set[str] = set()
    source_fingerprints: set[str] = set()
    domains: Counter[str] = Counter()
    rejected_patterns: Counter[str] = Counter()
    query_patterns: Counter[str] = Counter()

    for payload in iter_evidence_json_payloads(evidence_dir):
        for record in walk_records(payload):
            company = clean_text(record.get("company_name") or "")
            if company:
                companies.add(company)
            for key, target in (
                ("company_fingerprint", company_fingerprints),
                ("opportunity_fingerprint", opportunity_fingerprints),
                ("source_fingerprint", source_fingerprints),
            ):
                value = clean_text(record.get(key) or "")
                if value:
                    target.add(value)
            reason = clean_text(record.get("reason") or record.get("rejection_reason") or record.get("final_rejection_reason") or "")
            if reason:
                rejected_patterns[reason] += 1
            query = clean_text(record.get("source_query") or record.get("query") or "")
            if query:
                query_patterns[query] += 1
            for url in urls_from_record(record):
                domain = domain_from_url(url)
                if domain and domain not in GENERIC_OR_BLOCKED_DOMAINS:
                    domains[domain] += 1

    return {
        "prior_company_count": len(companies),
        "prior_companies": sorted(companies)[:250],
        "company_fingerprint_count": len(company_fingerprints),
        "company_fingerprints": sorted(company_fingerprints)[:250],
        "opportunity_fingerprint_count": len(opportunity_fingerprints),
        "opportunity_fingerprints": sorted(opportunity_fingerprints)[:250],
        "source_fingerprint_count": len(source_fingerprints),
        "known_good_domains": [domain for domain, _ in domains.most_common(75)],
        "rejected_patterns": dict(rejected_patterns.most_common(50)),
        "successful_query_patterns": dict(query_patterns.most_common(50)),
        "memory_sources": "local Evidence artifacts; cloud Memory Bank not mutated by this helper",
    }


def iter_evidence_json_payloads(evidence_dir: Path) -> list[Any]:
    if not evidence_dir.exists():
        return []
    payloads = []
    for path in sorted(evidence_dir.rglob("UK_IE_D365*.json")):
        if path.is_file() and path.stat().st_size <= 10_000_000:
            payload = safe_read_json(path)
            if payload is not None:
                payloads.append(payload)
    return payloads


def walk_records(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if any(key in value for key in ("company_name", "candidate_id", "opportunity_fingerprint", "evidence_url", "evidence_urls")):
            rows.append(value)
        for child in value.values():
            rows.extend(walk_records(child))
    elif isinstance(value, list):
        for child in value:
            rows.extend(walk_records(child))
    return rows


def urls_from_record(record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("evidence_url", "source_url", "url", "final_url"):
        if record.get(key):
            values.append(record[key])
    raw_urls = record.get("evidence_urls")
    if isinstance(raw_urls, list):
        values.extend(raw_urls)
    return [str(value) for value in values if isinstance(value, str) and value.startswith(("http://", "https://"))]


def domain_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or ""))
    host = parsed.netloc.lower().split(":")[0]
    return re.sub(r"^www\.", "", host)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_id(prefix: str, value: str) -> str:
    import hashlib

    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def augment_query_plan_with_memory(
    query_plan: list[dict[str, str]],
    preflight: dict[str, Any] | None,
    *,
    custom_query: bool = False,
    max_domain_queries: int = 6,
) -> list[dict[str, str]]:
    if custom_query or not preflight:
        return query_plan
    memory = preflight.get("memory_preflight") or {}
    domains = [
        domain
        for domain in memory.get("known_good_domains") or []
        if domain and domain not in GENERIC_OR_BLOCKED_DOMAINS
    ][:max_domain_queries]
    memory_queries = [
        {
            "signal_class": "memory_domain_revisit",
            "query": f'site:{domain} ("Dynamics 365" OR "Business Central" OR Dataverse) (UK OR Ireland) (case study OR support OR migration OR upgrade OR implementation)',
        }
        for domain in domains
    ]
    seen = set()
    combined = [*memory_queries, *query_plan]
    unique: list[dict[str, str]] = []
    for item in combined:
        query = item["query"]
        if query in seen:
            continue
        seen.add(query)
        unique.append(item)
    return unique


def build_agent_search_import_rows(evidence_dir: Path, *, bucket: str = DEFAULT_BUCKET) -> list[dict[str, Any]]:
    rows = []
    for doc in build_evidence_inventory(evidence_dir, bucket=bucket):
        rows.append(
            {
                "id": doc["document_id"],
                "jsonData": json.dumps(
                    {
                        "file_name": doc["file_name"],
                        "relative_path": doc["relative_path"],
                        "artifact_type": doc.get("artifact_type"),
                        "source_channel": doc["source_channel"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "content": {
                    "mimeType": doc["mime_type"],
                    "uri": doc["gcs_uri"],
                },
            }
        )
    return rows


def build_bigquery_ledger_mirror(evidence_dir: Path) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {name: [] for name in TABLE_NAMES}
    seen_candidates: set[str] = set()
    seen_sources: set[str] = set()
    seen_duplicates: set[str] = set()

    for payload in iter_evidence_json_payloads(evidence_dir):
        metadata = payload.get("metadata") if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict) else {}
        payload_run_id = payload.get("run_id") if isinstance(payload, dict) else ""
        run_id = clean_text(metadata.get("run_id") or payload_run_id)
        if isinstance(payload, dict) and (run_id or metadata):
            tables["runs"].append(
                {
                    "run_id": run_id or stable_id("run", json.dumps(metadata, sort_keys=True, default=str)),
                    "started_at": metadata.get("started_at") or payload.get("fetched_at"),
                    "finished_at": metadata.get("finished_at") or payload.get("run_finished_at"),
                    "provider_path": metadata.get("provider_path") or metadata.get("provider"),
                    "project": metadata.get("project"),
                    "location": metadata.get("location"),
                    "completion_status": metadata.get("completion_status") or payload.get("status"),
                }
            )
        for record in walk_records(payload):
            candidate_id = clean_text(record.get("candidate_id") or "")
            company = clean_text(record.get("company_name") or "")
            source_channel = classify_source_channel(
                source=record.get("source_provider"),
                provider_path=metadata.get("provider_path"),
                url=record.get("evidence_url") or "",
                explicit=record.get("source_channel"),
            )
            if candidate_id or company:
                key = candidate_id or stable_id("cand", company + json.dumps(urls_from_record(record), sort_keys=True))
                if key not in seen_candidates:
                    seen_candidates.add(key)
                    tables["candidates"].append(
                        {
                            "run_id": record.get("run_id") or run_id,
                            "candidate_id": candidate_id or key,
                            "company_name": company,
                            "retention_status": record.get("retention_status"),
                            "company_fingerprint": record.get("company_fingerprint"),
                            "opportunity_fingerprint": record.get("opportunity_fingerprint"),
                            "source_fingerprint": record.get("source_fingerprint"),
                            "evidence_url": record.get("evidence_url") or first_url(urls_from_record(record)),
                            "reason": record.get("reason") or record.get("rejection_reason"),
                            "source_channel": source_channel,
                            "final_pdf_eligible": final_pdf_eligible_from_channel(source_channel),
                        }
                    )
                    tables["identity_resolution"].append(
                        {
                            "run_id": record.get("run_id") or run_id,
                            "candidate_id": candidate_id or key,
                            "company_name": company,
                            "source_company": record.get("source_company"),
                            "source_role": record.get("source_role"),
                            "account_identity_status": record.get("account_identity_status"),
                            "identity_resolution_required": bool(record.get("identity_resolution_required")),
                        }
                    )
                    if record.get("lead_status") or record.get("signal_strength"):
                        tables["vetting_decisions"].append(
                            {
                                "run_id": record.get("run_id") or run_id,
                                "candidate_id": candidate_id or key,
                                "lead_status": record.get("lead_status"),
                                "signal_strength": record.get("signal_strength"),
                                "signal_type": record.get("signal_type"),
                                "final_rejection_reason": record.get("final_rejection_reason") or record.get("reason"),
                            }
                        )
                    if record.get("rank") or record.get("verified_live"):
                        tables["final_leads"].append(
                            {
                                "run_id": record.get("run_id") or run_id,
                                "candidate_id": candidate_id or key,
                                "rank": record.get("rank"),
                                "company_name": company,
                                "evidence_url": record.get("evidence_url") or first_url(urls_from_record(record)),
                                "verified_live": bool(record.get("verified_live")),
                                "signal_strength": record.get("signal_strength"),
                                "lead_status": record.get("lead_status"),
                                "source_channel": source_channel,
                                "final_pdf_eligible": final_pdf_eligible_from_channel(source_channel),
                            }
                        )
            for url in urls_from_record(record):
                source_key = f"{candidate_id}:{url}"
                if source_key in seen_sources:
                    continue
                seen_sources.add(source_key)
                tables["sources"].append(
                    {
                        "run_id": record.get("run_id") or run_id,
                        "candidate_id": candidate_id,
                        "url": url,
                        "final_url": record.get("final_url"),
                        "source_name": record.get("source_name") or domain_from_url(url),
                        "verified_live": bool(record.get("verified_live")),
                        "http_status": record.get("http_status"),
                        "fetched_at": record.get("fetched_at"),
                        "source_channel": source_channel,
                    }
                )
            opp = clean_text(record.get("opportunity_fingerprint") or "")
            company_fp = clean_text(record.get("company_fingerprint") or "")
            if opp or company_fp:
                dup_key = f"{company_fp}:{opp}"
                if dup_key not in seen_duplicates:
                    seen_duplicates.add(dup_key)
                    tables["duplicate_fingerprints"].append(
                        {
                            "company_fingerprint": company_fp,
                            "opportunity_fingerprint": opp,
                            "company_name": company,
                            "reason": record.get("retention_status") or record.get("reason"),
                            "observed_at": now_utc(),
                        }
                    )
    return tables


def first_url(values: list[str]) -> str:
    return values[0] if values else ""


def write_local_backbone_artifacts(
    *,
    evidence_dir: Path | str = EVIDENCE_DIR,
    output_dir: Path | str = EVIDENCE_DIR,
    project: str = DEFAULT_PROJECT,
    location: str = DEFAULT_LOCATION,
    dataset: str = DEFAULT_DATASET,
    bucket: str = DEFAULT_BUCKET,
    timestamp: str | None = None,
) -> dict[str, str]:
    evidence_path = Path(evidence_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    preflight = build_discovery_preflight(
        evidence_dir=evidence_path,
        project=project,
        location=location,
        dataset=dataset,
        bucket=bucket,
    )
    agent_search_rows = build_agent_search_import_rows(evidence_path, bucket=bucket)
    ledger_mirror = build_bigquery_ledger_mirror(evidence_path)
    ledger_counts = {name: len(rows) for name, rows in ledger_mirror.items()}

    preflight_json = output_path / f"UK_IE_D365_DISCOVERY_PREFLIGHT_{stamp}.json"
    preflight_md = output_path / f"UK_IE_D365_DISCOVERY_PREFLIGHT_{stamp}.md"
    agent_search_manifest = output_path / f"UK_IE_D365_AGENT_SEARCH_IMPORT_{stamp}.ndjson"
    ledger_json = output_path / f"UK_IE_D365_BIGQUERY_LEDGER_MIRROR_{stamp}.json"
    summary_md = output_path / f"UK_IE_D365_GOOGLE_ECOSYSTEM_BACKBONE_{stamp}.md"

    preflight_json.write_text(json.dumps(preflight, indent=2, ensure_ascii=False), encoding="utf-8")
    preflight_md.write_text(render_preflight_markdown(preflight), encoding="utf-8")
    agent_search_manifest.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in agent_search_rows) + ("\n" if agent_search_rows else ""),
        encoding="utf-8",
    )
    ledger_json.write_text(
        json.dumps({"artifact_type": "uk_ie_d365_bigquery_ledger_mirror", "generated_at": now_utc(), "table_counts": ledger_counts, "tables": ledger_mirror}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    summary_md.write_text(
        render_backbone_summary(preflight, agent_search_rows, ledger_counts),
        encoding="utf-8",
    )
    return {
        "preflight_json": str(preflight_json),
        "preflight_markdown": str(preflight_md),
        "agent_search_import_manifest": str(agent_search_manifest),
        "bigquery_ledger_mirror": str(ledger_json),
        "summary_markdown": str(summary_md),
    }


def render_preflight_markdown(preflight: dict[str, Any]) -> str:
    memory = preflight.get("memory_preflight") or {}
    readiness = preflight.get("local_readiness") or {}
    lines = [
        "# UK/IE D365 Discovery Preflight",
        "",
        f"- Generated: `{preflight.get('generated_at')}`",
        f"- Version: `{preflight.get('version')}`",
        f"- Mutation mode: `{preflight.get('mutation_mode')}`",
        f"- Evidence documents indexed locally: {preflight.get('evidence_inventory', {}).get('document_count', 0)}",
        f"- Prior companies found locally: {memory.get('prior_company_count', 0)}",
        f"- Prior opportunity fingerprints found locally: {memory.get('opportunity_fingerprint_count', 0)}",
        f"- Known-good domains found locally: {len(memory.get('known_good_domains') or [])}",
        f"- gcloud available: {readiness.get('gcloud_available')}",
        f"- bq available: {readiness.get('bq_available')}",
        "",
        "## Final Publication Rule",
        "",
        f"- {source_channel_policy()['final_pdf_rule']}",
        f"- {source_channel_policy()['hint_rule']}",
    ]
    return "\n".join(lines) + "\n"


def render_backbone_summary(
    preflight: dict[str, Any],
    agent_search_rows: list[dict[str, Any]],
    ledger_counts: dict[str, int],
) -> str:
    lines = [
        "# UK/IE D365 Google Ecosystem Backbone",
        "",
        "Local artifacts were prepared for cloud-backed lead discovery. No cloud resource was created by this artifact builder.",
        "",
        "## Prepared Inputs",
        "",
        f"- Agent Search import rows: {len(agent_search_rows)}",
        f"- Evidence inventory documents: {preflight.get('evidence_inventory', {}).get('document_count', 0)}",
        f"- Memory prior companies: {preflight.get('memory_preflight', {}).get('prior_company_count', 0)}",
        "",
        "## BigQuery Mirror Row Counts",
        "",
    ]
    for table, count in sorted(ledger_counts.items()):
        lines.append(f"- {table}: {count}")
    lines.extend(
        [
            "",
            "## Cloud Mutation Status",
            "",
            "- Not attempted by default.",
            "- Use the setup script with `--apply` only after IAM and billing are approved.",
        ]
    )
    return "\n".join(lines) + "\n"
