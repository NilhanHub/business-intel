from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "sync_uk_ie_d365_leads_to_northwind.py"
SPEC = importlib.util.spec_from_file_location("sync_uk_ie_d365_leads_to_northwind", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def lead() -> dict:
    return {
        "company_name": "Northstar Components",
        "country": "United Kingdom",
        "sector": "Manufacturing",
        "signal_type": "business_central_rollout",
        "opportunity_signal": "Named Business Central rollout.",
        "why_this_matters_to_1bt": "Clear Microsoft business-app workload.",
        "commercial_opening": "Discuss post-go-live support.",
        "evidence_url": "https://northstar.example.org/dynamics-365",
        "evidence_excerpt": "Northstar uses Dynamics 365 Business Central.",
        "fetched_at": "2026-07-16T00:00:00Z",
        "verified_live": True,
        "source_channel": "public_web",
        "signal_strength": "strong",
        "remaining_uncertainty": ["Buying timing is not public."],
        "do_not_claim_notes": ["Do not claim budget."],
    }


def test_pack_validation_and_existing_company_shape() -> None:
    leads = MODULE.validate_pack({"leads": [lead()]}, expected_count=1)
    payload = MODULE.company_payload(leads[0], timestamp="2026-07-16T00:00:00.000Z")
    assert payload["name"] == "Northstar Components"
    assert payload["createdBy"] == "agent:Intel-Pipeline"
    assert payload["status"] == "New"
    assert payload["activity"] == []
    assert payload["intel"]["evidenceUrl"].startswith("https://")


def test_target_guard_refuses_drift() -> None:
    with pytest.raises(RuntimeError, match="target drift"):
        MODULE.enforce_target("wrong-project", "(default)", "default")


def test_pack_validation_rejects_duplicate_and_unverified_rows() -> None:
    duplicate = dict(lead())
    with pytest.raises(RuntimeError, match="duplicate company"):
        MODULE.validate_pack({"leads": [lead(), duplicate]}, expected_count=2)
    invalid = dict(lead(), verified_live=False)
    with pytest.raises(RuntimeError, match="not verified"):
        MODULE.validate_pack({"leads": [invalid]}, expected_count=1)
