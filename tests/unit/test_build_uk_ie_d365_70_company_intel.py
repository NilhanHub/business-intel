from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "build_uk_ie_d365_70_company_intel.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_uk_ie_d365_70_company_intel", SCRIPT
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_five_packs_cover_the_canonical_70_without_duplicates() -> None:
    records = MODULE.load_records(MODULE.EVIDENCE_DIR)
    research = MODULE.json.loads(
        MODULE.DEFAULT_CANONICAL_RESEARCH.read_text(encoding="utf-8")
    )
    canonical = [item["company"] for item in research["companies"]]
    MODULE.validate(records, canonical)
    assert len(records) == 70
    assert len({record["canonical_company_name"] for record in records}) == 70


def test_known_pdf_aliases_resolve_to_crm_names() -> None:
    assert MODULE.canonical_name("Glenveagh") == "Glenveagh Properties plc"
    assert MODULE.canonical_name("Littlefish UK Ltd") == "Littlefish Group"
    assert (
        MODULE.canonical_name("Ireland Department of Health / HSE")
        == "Health Service Executive"
    )
    assert MODULE.canonical_name("Uniphar Medtech Limited") == "Uniphar Medtech"


def test_sheet_summary_retains_fact_and_action() -> None:
    pack = MODULE.PACKS[-1]
    record = {
        "company_name": "Northstar",
        "evidence_excerpt": (
            "Northstar rolled out Dynamics 365 Field Service to 2,000 engineers, replacing paper work "
            "orders with mobile scheduling and automated dispatch."
        ),
        "commercial_opening": "Discuss mobile workflow optimisation and managed release support.",
        "verified_live": True,
        "evidence_url": "https://northstar.example/case-study",
        "fetched_at": "2026-07-19T00:00:00Z",
    }
    normalized = MODULE.normalize_record(pack, record, {})
    assert "2,000 engineers" in normalized["sheet_summary"]
    assert "1BT opportunity:" in normalized["sheet_summary"]
    assert normalized["needs_adk_refresh"] is False


def test_validate_rejects_duplicate_canonical_research_names() -> None:
    records = MODULE.load_records(MODULE.EVIDENCE_DIR)
    canonical = [record["canonical_company_name"] for record in records]
    canonical[-1] = canonical[0]
    with pytest.raises(RuntimeError, match="Duplicate canonical research companies"):
        MODULE.validate(records, canonical)


def test_payload_metrics_are_derived_from_ordered_records(
    monkeypatch, tmp_path: Path
) -> None:
    records = MODULE.load_records(MODULE.EVIDENCE_DIR)
    canonical = [record["canonical_company_name"] for record in records]
    research = tmp_path / "research.json"
    research.write_text(
        MODULE.json.dumps({"companies": [{"company": name} for name in canonical]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(MODULE, "load_records", lambda _path: records)
    payload = MODULE.run(
        Namespace(
            canonical_research=research,
            evidence_dir=MODULE.EVIDENCE_DIR,
            output_prefix=tmp_path / "pack",
        )
    )
    assert payload["duplicate_company_count"] == 0
    assert payload["canonical_order_matches_crm_research"] is True
