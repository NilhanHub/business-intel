from __future__ import annotations

import importlib.util
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "run_uk_ie_d365_run5_contact_resolution.py"
SPEC = importlib.util.spec_from_file_location("run5_contacts", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_resolver_lead_preserves_explicit_roles_and_evidence() -> None:
    mapped = MODULE.resolver_lead(
        {
            "company_name": "Northstar Housing",
            "country": "United Kingdom",
            "opportunity_signal": "Dynamics 365 rollout",
            "evidence_url": "https://northstar.example.org/story",
            "evidence_excerpt": "Named rollout evidence.",
            "source_name": "Northstar public story",
            "fetched_at": "2026-07-19T00:00:00Z",
            "verified_live": True,
            "contact_target_roles": ["CIO", "Head of Business Applications"],
        }
    )
    assert mapped["company"] == "Northstar Housing"
    assert mapped["contact_target_roles"] == ["CIO", "Head of Business Applications"]
    assert mapped["evidence_url"].startswith("https://")
    assert mapped["source_name"] == "Northstar public story"
    assert mapped["verified_live"] is True


def test_merge_refuses_overlap(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(MODULE, "EVIDENCE_ROOT", tmp_path.resolve())
    batch = {
        "input_sha256": "a" * 64,
        "results": [{"company": "Northstar", "summary": {"name": "A"}}],
    }
    paths = []
    for index in range(2):
        path = tmp_path / f"batch-{index}.json"
        MODULE.atomic_write_json(path, batch)
        paths.append(str(path))
    with pytest.raises(RuntimeError, match="overlapping"):
        MODULE.merge_batches(paths, tmp_path / "merged.json")


def test_merge_can_replace_one_completed_company_result(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(MODULE, "EVIDENCE_ROOT", tmp_path.resolve())
    digest = "b" * 64
    base_paths = []
    for batch_index in range(4):
        results = [
            {
                "company": f"Company {batch_index * 5 + item_index}",
                "summary": {"name": None, "route_type": "contact_form"},
            }
            for item_index in range(5)
        ]
        path = tmp_path / f"base-{batch_index}.json"
        MODULE.atomic_write_json(path, {"input_sha256": digest, "results": results})
        base_paths.append(str(path))
    replacement = tmp_path / "replacement.json"
    MODULE.atomic_write_json(
        replacement,
        {
            "input_sha256": digest,
            "results": [
                {
                    "company": "Company 7",
                    "summary": {"name": "Verified Person", "route_type": "named_person"},
                }
            ],
        },
    )

    merged = MODULE.merge_batches(base_paths, tmp_path / "merged.json", [str(replacement)])

    assert merged["result_count"] == 20
    assert merged["named_contact_count"] == 1
    assert merged["replaced_companies"] == ["Company 7"]


def test_load_leads_requires_complete_public_provenance(tmp_path: Path) -> None:
    path = tmp_path / "leads.json"
    leads = [
        {
            "company_name": f"Company {index}",
            "country": "Ireland",
            "opportunity_signal": "D365 rollout",
            "evidence_url": "https://example.org/story",
            "evidence_excerpt": "Named public evidence.",
            "source_name": "Example public story",
            "fetched_at": "2026-07-19T00:00:00Z",
            "verified_live": True,
            "source_channel": "public_web",
        }
        for index in range(20)
    ]
    leads[4]["source_name"] = ""
    path.write_text(MODULE.json.dumps({"leads": leads}), encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"lead 5.*source_name"):
        MODULE.load_leads(path)


def test_resume_refuses_a_different_slice(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(MODULE, "EVIDENCE_ROOT", tmp_path.resolve())
    leads = [
        {
            "company_name": f"Company {index}",
            "country": "Ireland",
            "opportunity_signal": "D365 rollout",
            "evidence_url": "https://example.org/story",
            "evidence_excerpt": "Named public evidence.",
            "source_name": "Example public story",
            "fetched_at": "2026-07-19T00:00:00Z",
            "verified_live": True,
            "source_channel": "public_web",
        }
        for index in range(20)
    ]
    input_path = tmp_path / "leads.json"
    input_path.write_text(MODULE.json.dumps({"leads": leads}), encoding="utf-8")
    output_path = tmp_path / "batch.json"
    MODULE.atomic_write_json(
        output_path,
        {
            "input_sha256": MODULE.input_hash(input_path),
            "offset": 5,
            "limit": 5,
            "requested_companies": [f"Company {index}" for index in range(5, 10)],
            "results": [],
        },
    )
    args = Namespace(
        input=input_path,
        output=output_path,
        offset=0,
        limit=5,
        max_search_queries=1,
        max_pages_to_fetch=1,
        max_runtime_seconds=1,
    )
    with pytest.raises(RuntimeError, match="different requested slice"):
        MODULE.run_batch(args)


def test_output_path_is_confined_to_evidence(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="must stay within"):
        MODULE.evidence_path(tmp_path / "outside.json", label="test output")
