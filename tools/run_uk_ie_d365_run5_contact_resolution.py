"""Resolve evidence-backed contacts for the 20-account UK/IE Round 5 pack."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sl_trigger_leads.tools.contact_resolver_tools import resolve_contact_route_for_lead

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = (ROOT / "Evidence").resolve()
DEFAULT_INPUT = EVIDENCE_ROOT / "UK_IE_D365_RUN5_20260716_20_LEADS_FINAL.json"


def evidence_path(path: str | Path, *, label: str) -> Path:
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(EVIDENCE_ROOT)
    except ValueError as exc:
        raise RuntimeError(f"{label} must stay within {EVIDENCE_ROOT}: {resolved}") from exc
    return resolved


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def input_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def resolver_lead(lead: dict[str, Any]) -> dict[str, Any]:
    return {
        "company": str(lead["company_name"]),
        "country": str(lead["country"]),
        "trigger": str(lead["opportunity_signal"]),
        "evidence_url": str(lead["evidence_url"]),
        "evidence_excerpt": str(lead["evidence_excerpt"]),
        "source_name": str(lead["source_name"]),
        "fetched_at": str(lead["fetched_at"]),
        "verified_live": lead["verified_live"] is True,
        "contact_target_roles": [str(role) for role in lead.get("contact_target_roles") or []],
        "opportunity_bucket_primary": "MS 365D",
        "onebt_fit": ["MS 365D"],
    }


def route_summary(result: dict[str, Any]) -> dict[str, Any]:
    route = result.get("best_contact_route") or {}
    search = result.get("search_summary") or {}
    return {
        "company": str(result.get("company") or ""),
        "name": route.get("name"),
        "role": route.get("role"),
        "route_type": route.get("type"),
        "confidence": route.get("confidence"),
        "email": route.get("email"),
        "url": route.get("url"),
        "linkedin_url": route.get("linkedin_url"),
        "evidence_urls": route.get("evidence_urls") or [],
        "search_provider": search.get("search_provider"),
        "queries_attempted": len(search.get("queries_attempted") or []),
        "sources_checked": len(search.get("sources_checked") or []),
        "stopped_reason": search.get("stopped_reason"),
    }


def load_leads(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    leads = list(payload.get("leads") or [])
    if len(leads) != 20:
        raise RuntimeError(f"Expected the exact 20-account Round 5 pack; found {len(leads)} leads.")
    if len({str(lead.get("company_name") or "").casefold() for lead in leads}) != 20:
        raise RuntimeError("Round 5 contact input contains duplicate or missing company names.")
    for index, lead in enumerate(leads, start=1):
        missing_evidence = [
            field
            for field in ("evidence_url", "evidence_excerpt", "source_name", "fetched_at")
            if not isinstance(lead.get(field), str) or not lead[field].strip()
        ]
        if missing_evidence:
            raise RuntimeError(
                f"Round 5 lead {index} is missing required public evidence fields: {missing_evidence}"
            )
        if lead.get("verified_live") is not True or lead.get("source_channel") != "public_web":
            raise RuntimeError(f"Contact resolution requires verified public evidence: {lead.get('company_name')}")
        if not str(lead.get("evidence_url") or "").startswith(("https://", "http://")):
            raise RuntimeError(f"Contact resolution refused an unsafe evidence URL: {lead.get('company_name')}")
    return leads


def run_batch(args: argparse.Namespace) -> dict[str, Any]:
    input_path = evidence_path(args.input, label="Contact-resolution input")
    leads = load_leads(input_path)
    if args.offset < 0 or args.limit <= 0:
        raise RuntimeError("Contact-resolution offset must be non-negative and limit must be positive.")
    selected = leads[args.offset : args.offset + args.limit]
    if not selected:
        raise RuntimeError("The requested contact-resolution slice is empty.")
    output_path = evidence_path(args.output, label="Contact-resolution output")
    digest = input_hash(input_path)
    selected_names = [str(item["company_name"]) for item in selected]
    existing: dict[str, Any] = {}
    if output_path.is_file():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if existing.get("input_sha256") != digest:
            raise RuntimeError("Refusing to resume a contact batch against different lead evidence.")
        if existing.get("offset") != args.offset or existing.get("limit") != args.limit:
            raise RuntimeError("Refusing to resume a contact batch with a different requested slice.")
        if existing.get("requested_companies") != selected_names:
            raise RuntimeError("Refusing to resume a contact batch with different selected companies.")
    existing_results = list(existing.get("results") or [])
    completed = {str(item.get("company") or ""): item for item in existing_results}
    if len(completed) != len(existing_results) or not set(completed) <= set(selected_names):
        raise RuntimeError("Existing contact results do not belong uniquely to the requested slice.")
    started_at = str(existing.get("started_at") or now_utc())
    for lead in selected:
        company = str(lead["company_name"])
        if company in completed:
            continue
        try:
            result = resolve_contact_route_for_lead(
                resolver_lead(lead),
                dry_run=False,
                max_search_queries=args.max_search_queries,
                max_pages_to_fetch=args.max_pages_to_fetch,
                max_candidate_contacts=5,
                max_runtime_seconds=args.max_runtime_seconds,
                audit_mode=True,
            )
            record = {
                "company": company,
                "input": resolver_lead(lead),
                "summary": route_summary(result),
                "result": result,
                "resolved_at": now_utc(),
            }
        except Exception as exc:  # preserve the completed batch and make failure explicit
            record = {
                "company": company,
                "input": resolver_lead(lead),
                "summary": {"company": company, "route_type": "resolver_error"},
                "error": {"type": type(exc).__name__, "message": str(exc)[:500]},
                "resolved_at": now_utc(),
            }
        completed[company] = record
        payload = {
            "artifact_type": "uk_ie_d365_run5_contact_resolution_batch",
            "started_at": started_at,
            "updated_at": now_utc(),
            "input_file": str(input_path),
            "input_sha256": digest,
            "offset": args.offset,
            "limit": args.limit,
            "requested_companies": selected_names,
            "completed_count": len(completed),
            "results": list(completed.values()),
            "sending_enabled": False,
        }
        atomic_write_json(output_path, payload)
        print(
            "RUN5_CONTACT_PROGRESS="
            + json.dumps(
                {
                    "company": company,
                    "route_type": record["summary"].get("route_type"),
                    "named": bool(record["summary"].get("name")),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    return json.loads(output_path.read_text(encoding="utf-8"))


def merge_batches(
    paths: list[str],
    output: Path,
    replacement_paths: list[str] | None = None,
) -> dict[str, Any]:
    batch_paths = [evidence_path(path, label="Contact batch") for path in paths]
    replacement_batch_paths = [
        evidence_path(path, label="Replacement contact batch")
        for path in (replacement_paths or [])
    ]
    output = evidence_path(output, label="Merged contact output")
    batches = [json.loads(path.read_text(encoding="utf-8")) for path in batch_paths]
    replacements = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in replacement_batch_paths
    ]
    hashes = {
        str(batch.get("input_sha256") or "")
        for batch in [*batches, *replacements]
    }
    if len(hashes) != 1 or not next(iter(hashes)):
        raise RuntimeError("Contact batches do not share one input evidence hash.")
    records: dict[str, dict[str, Any]] = {}
    for batch in batches:
        for record in batch.get("results") or []:
            company = str(record.get("company") or "")
            if not company or company in records:
                raise RuntimeError(f"Contact batches contain a missing or overlapping company: {company!r}")
            records[company] = record
    if len(records) != 20:
        raise RuntimeError(f"Expected 20 contact results after merge; found {len(records)}.")
    replaced_companies: list[str] = []
    replacement_records: dict[str, dict[str, Any]] = {}
    for batch in replacements:
        for record in batch.get("results") or []:
            company = str(record.get("company") or "")
            if not company or company in replacement_records:
                raise RuntimeError(f"Replacement batches contain a missing or overlapping company: {company!r}")
            if company not in records:
                raise RuntimeError(f"Replacement company is absent from the complete base merge: {company!r}")
            replacement_records[company] = record
    for company, record in replacement_records.items():
        records[company] = record
        replaced_companies.append(company)
    summaries = [record["summary"] for record in records.values()]
    payload = {
        "artifact_type": "uk_ie_d365_run5_contact_resolution_final",
        "generated_at": now_utc(),
        "input_sha256": next(iter(hashes)),
        "batch_files": [str(path) for path in batch_paths],
        "replacement_files": [str(path) for path in replacement_batch_paths],
        "replaced_companies": replaced_companies,
        "result_count": len(records),
        "named_contact_count": sum(bool(item.get("name")) for item in summaries),
        "resolver_error_count": sum(item.get("route_type") == "resolver_error" for item in summaries),
        "summaries": summaries,
        "results": list(records.values()),
        "sending_enabled": False,
    }
    atomic_write_json(output, payload)
    return payload


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--max-search-queries", type=int, default=5)
    p.add_argument("--max-pages-to-fetch", type=int, default=5)
    p.add_argument("--max-runtime-seconds", type=int, default=90)
    p.add_argument("--merge-files", nargs="+")
    p.add_argument("--replacement-files", nargs="+")
    return p


def main() -> int:
    args = parser().parse_args()
    if args.merge_files:
        payload = merge_batches(
            args.merge_files,
            args.output,
            args.replacement_files,
        )
        print(json.dumps({key: payload[key] for key in ("result_count", "named_contact_count", "resolver_error_count")}))
    else:
        payload = run_batch(args)
        print(json.dumps({"completed_count": payload["completed_count"], "output": str(evidence_path(args.output, label="Contact-resolution output"))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
