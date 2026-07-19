from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "finalize_uk_ie_d365_70_company_intel.py"
SPEC = importlib.util.spec_from_file_location("finalize_70_company_intel", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def base_companies():
    return json.loads(MODULE.DEFAULT_BASE.read_text(encoding="utf-8"))["companies"]


def test_live_overrides_cover_every_old_unverified_record() -> None:
    unverified = {
        row["canonical_company_name"]
        for row in base_companies()
        if not row["verified_live"]
    }
    assert unverified <= set(MODULE.INTEL_OVERRIDES)


def test_country_fallbacks_cover_blank_crm_countries() -> None:
    expected = {
        "Biffa Group",
        "Charterhouse Holdings",
        "Clariness",
        "Hadley Group",
        "Kepak Group",
        "Simply Dynamics 365",
        "Synergy Technology",
        "The Royal Society / Subscribe360",
        "Tourism NI",
        "UK defence apparel manufacturer (unnamed in source)",
        "Uniphar Medtech",
        "Willmott Dixon",
    }
    assert expected == set(MODULE.COUNTRY_FALLBACKS)


def test_compact_summary_has_a_hard_length_limit() -> None:
    value = MODULE.compact_summary("evidence " * 100, "opening " * 100, limit=200)
    assert len(value) <= 200
    assert value.endswith("…")


def test_report_metadata_preserves_each_pdf_batch() -> None:
    rows = base_companies()
    assert Counter(MODULE.report_metadata(row)["round"] for row in rows) == Counter(
        {1: 14, 2: 12, 3: 12, 4: 12, 5: 20}
    )


def test_refresh_proof_replaces_base_provenance_without_replacing_curated_intel() -> (
    None
):
    base = next(
        row
        for row in base_companies()
        if row["canonical_company_name"] == "Biffa Group"
    )
    refresh = {
        "run_id": "run-proof",
        "query": "Biffa Dynamics 365",
        "live_sources": [{"verified_live": False}, {"verified_live": True}],
        "best_live_source": {
            "verified_live": True,
            "source_fetch_status": "fetched",
            "final_url": "https://www.microsoft.com/customer-stories/biffa",
            "text_excerpt": "Biffa processes 250,000 invoice lines with Dynamics 365 Finance.",
            "title": "Microsoft Customer Stories",
            "fetched_at": "2026-07-19T18:58:47.238363+05:30",
        },
    }
    record = MODULE.merge_record(
        base,
        {"country": "United Kingdom", "sector": "Waste management"},
        refresh,
    )
    assert "200,000-250,000" in record["specific_evidence"]
    assert record["evidence_url"] == refresh["best_live_source"]["final_url"]
    assert record["evidence_excerpt"].startswith("Biffa processes 250,000")
    assert record["source_name"] == "Microsoft Customer Stories"
    assert record["fetched_at"] == "2026-07-19T13:28:47.238363Z"
    assert record["evidence_proof"] == "targeted_live_refresh"


def test_merge_rejects_a_record_without_valid_evidence_proof() -> None:
    base = dict(base_companies()[0])
    base.update(
        {
            "verified_live": False,
            "direct_public_source": False,
            "evidence_url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/x",
        }
    )
    with pytest.raises(RuntimeError, match="no validated direct public evidence"):
        MODULE.merge_record(base, {}, None)


def test_verified_base_proof_normalizes_legacy_timestamp() -> None:
    base = next(
        dict(row)
        for row in base_companies()
        if row["verified_live"] and row["direct_public_source"]
    )
    base["evidence_date"] = "19/07/2026 12:34:56"
    proof = MODULE.base_evidence(base)
    assert proof is not None
    assert proof["fetched_at"] == "2026-07-19T12:34:56Z"
    assert proof["evidence_proof"] == "verified_base_record"


def test_finalizer_paths_must_stay_under_evidence(tmp_path, monkeypatch) -> None:
    evidence = (tmp_path / "Evidence").resolve()
    evidence.mkdir()
    monkeypatch.setattr(MODULE, "EVIDENCE_ROOT", evidence)
    assert (
        MODULE.evidence_path(evidence / "output", label="Output") == evidence / "output"
    )
    with pytest.raises(RuntimeError, match="must stay within"):
        MODULE.evidence_path(tmp_path / "outside.json", label="Input")


def test_merge_supplies_actionable_role_and_board_fallbacks() -> None:
    base = next(
        dict(row)
        for row in base_companies()
        if row["verified_live"] and row["direct_public_source"]
    )
    base["board_relevance"] = ""
    base["contact_target_roles"] = []
    record = MODULE.merge_record(
        base, {"country": "United Kingdom", "sector": "Other"}, None
    )
    assert record["board_relevance"] == record["why_this_matters_to_1bt"]
    assert record["contact_target_roles"] == [
        "CIO",
        "IT Director",
        "Head of Business Systems",
        "ERP/CRM Manager",
    ]


def test_validation_allows_explicitly_empty_remaining_uncertainty() -> None:
    payload = json.loads(
        MODULE.DEFAULT_PREFIX.with_suffix(".json").read_text(encoding="utf-8")
    )
    records = payload["companies"]
    records[0]["remaining_uncertainty"] = []
    profile_payload = json.loads(MODULE.DEFAULT_CRM_PROFILE.read_text(encoding="utf-8"))
    MODULE.validate(records, profile_payload["profiles"])
