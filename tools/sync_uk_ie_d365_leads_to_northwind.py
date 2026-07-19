"""Dry-run or atomically add a vetted UK/IE lead pack to Northwind CRM."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uk_ie_d365_leads.tools.opportunity_vetting_tools import (
    is_prior_or_parked_account,
    normalize_company_for_match,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = PROJECT_ROOT / "Evidence"
APPROVED_PROJECT = "globalapps-northwind-crm"
APPROVED_DATABASE = "(default)"
APPROVED_WORKSPACE = "default"
CREATED_BY = "agent:Intel-Pipeline"
RUN5_REPORT_TITLE = "UK/IE Dynamics 365 Opportunity Intelligence - Round 5"
RUN5_REPORT_PDF = "2026-07-16__uk-ie-d365__round-5__20-new-accounts.pdf"
RUN5_EVIDENCE_PACK = "UK_IE_D365_RUN5_20260716_20_LEADS_FINAL.json"


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-pack", required=True)
    p.add_argument("--project", default=APPROVED_PROJECT)
    p.add_argument("--database", default=APPROVED_DATABASE)
    p.add_argument("--workspace", default=APPROVED_WORKSPACE)
    p.add_argument("--expected-count", type=int, default=20)
    p.add_argument(
        "--output",
        default=str(EVIDENCE_DIR / "UK_IE_D365_RUN5_20260716_NORTHWIND_SYNC.json"),
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Apply one atomic Firestore transaction after preflight.",
    )
    p.add_argument(
        "--enrich-existing",
        action="store_true",
        help="Update the exact existing companies with the complete lead intelligence instead of creating records.",
    )
    return p


def enforce_target(project: str, database: str, workspace: str) -> None:
    expected = (APPROVED_PROJECT, APPROVED_DATABASE, APPROVED_WORKSPACE)
    actual = (project, database, workspace)
    if actual != expected:
        raise RuntimeError(
            f"Refusing Northwind target drift: expected {expected!r}, received {actual!r}."
        )


def crm_normalized_name(name: Any) -> str:
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(
        character for character in text if not unicodedata.combining(character)
    )
    text = re.sub(r"[\u2019'`]", "", text).replace("&", " and ")
    text = "".join(character if character.isalnum() else " " for character in text)
    return re.sub(r"\s+", " ", text).strip().lower()


def company_document_id(name: str) -> str:
    normalized = crm_normalized_name(name)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:48] or "company"
    suffix = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:4]
    return f"{slug}-{suffix}"


def validate_pack(
    payload: dict[str, Any], *, expected_count: int
) -> list[dict[str, Any]]:
    leads = list(payload.get("leads") or [])
    if len(leads) != expected_count:
        raise RuntimeError(
            f"Expected exactly {expected_count} leads, found {len(leads)}."
        )
    required = (
        "company_name",
        "country",
        "sector",
        "signal_type",
        "opportunity_signal",
        "why_this_matters_to_1bt",
        "commercial_opening",
        "evidence_url",
        "evidence_excerpt",
        "fetched_at",
    )
    names: set[str] = set()
    for index, lead in enumerate(leads, start=1):
        missing = [field for field in required if not lead.get(field)]
        if missing:
            raise RuntimeError(f"Lead {index} is missing required fields: {missing}")
        normalized = normalize_company_for_match(lead["company_name"])
        if not normalized or normalized in names:
            raise RuntimeError(
                f"Lead {index} has a missing or duplicate company identity."
            )
        names.add(normalized)
        if (
            lead.get("verified_live") is not True
            or lead.get("source_channel") != "public_web"
        ):
            raise RuntimeError(f"Lead {index} is not verified public-web evidence.")
        if not str(lead["evidence_url"]).lower().startswith(("https://", "http://")):
            raise RuntimeError(f"Lead {index} has an unsafe evidence URL.")
        supplied_report = lead.get("report")
        if supplied_report is not None and not isinstance(supplied_report, dict):
            raise RuntimeError(f"Lead {index} has a malformed report object.")
        if supplied_report:
            for field in ("round", "leadCount"):
                value = supplied_report.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    raise RuntimeError(
                        f"Lead {index} has a malformed report.{field} value."
                    )
    return leads


def intel_payload(lead: dict[str, Any]) -> dict[str, Any]:
    remaining_uncertainty = [
        str(item) for item in lead.get("remaining_uncertainty") or []
    ]
    uncertainty = "; ".join(remaining_uncertainty)
    do_not_claim = [str(item) for item in lead.get("do_not_claim_notes") or []]
    supplied_report = lead.get("report") or {}
    report = {
        "evidencePackFilename": str(
            supplied_report.get("evidencePackFilename") or RUN5_EVIDENCE_PACK
        ),
        "leadCount": int(supplied_report.get("leadCount") or 20),
        "pdfFilename": str(supplied_report.get("pdfFilename") or RUN5_REPORT_PDF),
        "round": int(supplied_report.get("round") or 5),
        "title": str(supplied_report.get("title") or RUN5_REPORT_TITLE),
    }
    return {
        "boardRelevance": str(lead.get("board_relevance") or ""),
        "commercialOpening": str(lead.get("commercial_opening") or ""),
        "contactTargetRoles": [
            str(item) for item in lead.get("contact_target_roles") or []
        ],
        "doNotClaim": do_not_claim,
        "evidenceExcerpt": str(lead.get("evidence_excerpt") or ""),
        "evidenceUrl": str(lead.get("evidence_url") or ""),
        "fetchedAt": str(lead.get("fetched_at") or ""),
        "intelligenceReading": str(lead.get("intelligence_reading") or ""),
        "opportunityStatus": str(
            lead.get("opportunity_status") or "actionable_hypothesis"
        ),
        "remainingUncertainty": remaining_uncertainty,
        "report": report,
        "sheetSummary": str(lead.get("sheet_summary") or ""),
        "signal": str(lead.get("opportunity_signal") or ""),
        "signalTier": str(lead.get("signal_strength") or "").title(),
        "signalType": str(lead.get("signal_type") or ""),
        "sourceChannel": str(lead.get("source_channel") or ""),
        "sourceName": str(lead.get("source_name") or ""),
        "specificEvidence": str(
            lead.get("specific_evidence") or lead.get("opportunity_signal") or ""
        ),
        "uncertainty": uncertainty,
        "valueOfSignal": str(lead.get("value_of_signal") or ""),
        "verifiedLive": lead.get("verified_live") is True,
        "whyItMatters": str(lead.get("why_this_matters_to_1bt") or ""),
    }


def company_payload(lead: dict[str, Any], *, timestamp: str) -> dict[str, Any]:
    name = str(lead["company_name"])
    doc_id = company_document_id(name)
    return {
        "activity": [],
        "contactName": "",
        "contacted": False,
        "country": str(lead.get("country") or ""),
        "createdAt": timestamp,
        "createdBy": CREATED_BY,
        "email": "",
        "id": doc_id,
        "industry": "",
        "intel": intel_payload(lead),
        "lastContactAt": "",
        "name": name,
        "nextStep": {"type": "email", "note": ""},
        "normalizedName": crm_normalized_name(name),
        "phone": "",
        "sector": str(lead.get("sector") or ""),
        "size": None,
        "status": "New",
        "updatedAt": timestamp,
        "version": 1,
        "workspaceId": APPROVED_WORKSPACE,
    }


def find_duplicates(leads: list[dict[str, Any]], existing_docs: list[Any]) -> list[str]:
    existing_names = {
        normalize_company_for_match((doc.to_dict() or {}).get("name") or "")
        for doc in existing_docs
    }
    return [
        str(lead["company_name"])
        for lead in leads
        if is_prior_or_parked_account(str(lead["company_name"]), existing_names)
    ]


def match_existing_docs(
    leads: list[dict[str, Any]], existing_docs: list[Any]
) -> dict[str, Any]:
    by_name: dict[str, list[Any]] = {}
    for doc in existing_docs:
        normalized = normalize_company_for_match(
            (doc.to_dict() or {}).get("name") or ""
        )
        if normalized:
            by_name.setdefault(normalized, []).append(doc)
    matched: dict[str, Any] = {}
    for lead in leads:
        company_name = str(lead["company_name"])
        candidates = by_name.get(normalize_company_for_match(company_name), [])
        if len(candidates) != 1:
            raise RuntimeError(
                f"Expected exactly one existing Northwind company for {company_name!r}; found {len(candidates)}."
            )
        matched[company_name] = candidates[0]
    return matched


def run(args: argparse.Namespace) -> dict[str, Any]:
    enforce_target(args.project, args.database, args.workspace)
    try:
        from google.cloud import firestore
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-firestore is required; run with `uv run --with google-cloud-firestore`."
        ) from exc

    input_path = Path(args.input_pack).resolve()
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    leads = validate_pack(payload, expected_count=args.expected_count)
    client = firestore.Client(project=args.project, database=args.database)
    workspace_ref = client.collection("workspaces").document(args.workspace)
    companies_ref = workspace_ref.collection("companies")
    existing_before = list(companies_ref.stream())
    duplicates = find_duplicates(leads, existing_before)
    existing_matches = (
        match_existing_docs(leads, existing_before) if args.enrich_existing else {}
    )
    if duplicates and not args.enrich_existing:
        raise RuntimeError(
            f"Northwind already contains matching companies: {duplicates}"
        )

    timestamp = now_utc()
    prepared = [company_payload(lead, timestamp=timestamp) for lead in leads]
    existing_ids = {doc.id for doc in existing_before}
    collisions = [item["id"] for item in prepared if item["id"] in existing_ids]
    if collisions and not args.enrich_existing:
        raise RuntimeError(f"Northwind document ID collision: {collisions}")

    applied = False
    if args.apply:
        transaction = client.transaction(max_attempts=3)

        @firestore.transactional
        def apply_once(txn: Any) -> None:
            workspace_snapshot = workspace_ref.get(transaction=txn)
            live_docs = list(txn.get(companies_ref.limit(1000)))
            if args.enrich_existing:
                live_matches = match_existing_docs(leads, live_docs)
                for lead in leads:
                    doc = live_matches[str(lead["company_name"])]
                    current = doc.to_dict() or {}
                    txn.update(
                        doc.reference,
                        {
                            "intel": intel_payload(lead),
                            "updatedAt": timestamp,
                            "version": int(current.get("version") or 0) + 1,
                        },
                    )
            else:
                live_duplicates = find_duplicates(leads, live_docs)
                if live_duplicates:
                    raise RuntimeError(
                        f"Northwind changed after preflight; duplicate companies: {live_duplicates}"
                    )
                live_ids = {doc.id for doc in live_docs}
                live_collisions = [
                    item["id"] for item in prepared if item["id"] in live_ids
                ]
                if live_collisions:
                    raise RuntimeError(
                        f"Northwind changed after preflight; document ID collision: {live_collisions}"
                    )
                for item in prepared:
                    txn.create(companies_ref.document(item["id"]), item)
            workspace_data = workspace_snapshot.to_dict() or {}
            txn.update(
                workspace_ref,
                {
                    "revision": int(workspace_data.get("revision") or 0) + 1,
                    "updatedAt": timestamp,
                },
            )

        apply_once(transaction)
        applied = True

    existing_after = list(companies_ref.stream())
    after_by_id = {doc.id: doc.to_dict() or {} for doc in existing_after}
    if args.enrich_existing:
        verified_ids = [
            existing_matches[str(lead["company_name"])].id
            for lead in leads
            if after_by_id.get(existing_matches[str(lead["company_name"])].id, {}).get(
                "intel"
            )
            == intel_payload(lead)
        ]
    else:
        verified_ids = [
            item["id"]
            for item in prepared
            if after_by_id.get(item["id"], {}).get("name") == item["name"]
        ]
    expected_after = len(existing_before) + (
        len(prepared) if applied and not args.enrich_existing else 0
    )
    if len(existing_after) != expected_after:
        raise RuntimeError(
            f"Northwind count verification failed: expected {expected_after}, found {len(existing_after)}."
        )
    if applied and len(verified_ids) != len(prepared):
        raise RuntimeError(
            "Northwind post-write verification did not find every inserted company."
        )

    result = {
        "artifact_type": "uk_ie_d365_northwind_crm_sync",
        "generated_at": now_utc(),
        "mode": ("apply" if applied else "dry_run")
        + ("_enrich_existing" if args.enrich_existing else ""),
        "target": {
            "project": args.project,
            "database": args.database,
            "workspace": args.workspace,
            "collection": "workspaces/default/companies",
        },
        "input_pack": str(input_path),
        "input_lead_count": len(leads),
        "company_count_before": len(existing_before),
        "company_count_after": len(existing_after),
        "duplicate_count": 0 if args.enrich_existing else len(duplicates),
        "existing_match_count": len(existing_matches),
        "inserted_count": 0 if args.enrich_existing else len(verified_ids),
        "enriched_count": len(verified_ids) if args.enrich_existing else 0,
        "prepared_companies": [
            {
                "id": item["id"],
                "name": item["name"],
                "country": item["country"],
                "sector": item["sector"],
            }
            for item in prepared
        ],
        "verified_inserted_ids": [] if args.enrich_existing else verified_ids,
        "verified_enriched_ids": verified_ids if args.enrich_existing else [],
        "created_contacts": 0,
        "created_routes": 0,
        "created_activities": 0,
        "schema_note": "Used the existing companies/intel document shape; no collection schema was created.",
    }
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    run(parser().parse_args())
