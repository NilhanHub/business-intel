"""Atomically checkpoint Former Clients Sales Navigator records by stable ID."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

SECTIONS = {"alumni_records", "target_records"}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def upsert_record(
    path: Path,
    section: str,
    stable_id: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    if section not in SECTIONS:
        raise ValueError(f"Unsupported checkpoint section: {section}")
    if not stable_id.strip():
        raise ValueError("Stable ID must not be blank")
    if record.get("lead_id") != stable_id:
        raise ValueError("Record lead_id must match the checkpoint stable ID")
    if record.get("verified_live") is not True:
        raise ValueError("Checkpoint records must be verified_live")

    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {
            "source": {
                "signed_in_identity": "Paul Fryer",
                "collection_method": "LinkedIn Sales Navigator live DOM",
                "status": "in_progress",
            },
            "alumni_records": {},
            "target_records": {},
        }
    if not isinstance(payload, dict):
        raise ValueError("Checkpoint root must be an object")
    records = payload.setdefault(section, {})
    if not isinstance(records, dict):
        raise ValueError(f"Checkpoint {section} must be an object")
    records[stable_id] = record
    _atomic_json(path, payload)
    return payload


def sync_prospect_targets(
    path: Path,
    prospect_payload: dict[str, Any],
) -> dict[str, Any]:
    prospects = prospect_payload.get("prospects")
    if not isinstance(prospects, list):
        raise ValueError("Prospect payload must contain a prospects list")
    records: dict[str, dict[str, Any]] = {}
    for prospect in prospects:
        if not isinstance(prospect, dict):
            raise ValueError("Every prospect must be an object")
        company = prospect.get("company")
        targets = prospect.get("targets")
        if not isinstance(company, str) or not company.strip():
            raise ValueError("Every prospect requires a company")
        if not isinstance(targets, list):
            raise ValueError(f"{company} targets must be a list")
        for target in targets:
            if not isinstance(target, dict):
                raise ValueError(f"{company} target must be an object")
            lead_id = target.get("lead_id")
            if not isinstance(lead_id, str) or not lead_id.strip():
                raise ValueError(f"{company} target requires a stable lead_id")
            if lead_id in records:
                raise ValueError(f"Duplicate target lead ID: {lead_id}")
            records[lead_id] = {
                **target,
                "company": company,
                "verified_live": True,
            }

    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("Checkpoint root must be an object")
    payload["target_records"] = records
    source = payload.setdefault("source", {})
    if not isinstance(source, dict):
        raise ValueError("Checkpoint source must be an object")
    source["target_record_count"] = len(records)
    source["status"] = "complete"
    _atomic_json(path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--section", choices=sorted(SECTIONS))
    parser.add_argument("--stable-id")
    parser.add_argument("--record", type=Path)
    parser.add_argument("--sync-prospects", type=Path)
    args = parser.parse_args()
    if args.sync_prospects is not None:
        prospect_payload = json.loads(
            args.sync_prospects.read_text(encoding="utf-8")
        )
        result = sync_prospect_targets(args.checkpoint, prospect_payload)
        print(len(result["target_records"]))
        return
    if not args.section or not args.stable_id or args.record is None:
        parser.error(
            "--section, --stable-id and --record are required for an upsert"
        )
    record = json.loads(args.record.read_text(encoding="utf-8"))
    result = upsert_record(
        args.checkpoint, args.section, args.stable_id, record
    )
    print(len(result[args.section]))


if __name__ == "__main__":
    main()
