from __future__ import annotations

from pathlib import Path

import pytest

from sl_trigger_leads.tools.signal_extractor import (
    extract_public_signals,
    extract_public_signals_from_source,
)
from sl_trigger_leads.tools.signal_tools import assert_no_simulation_data
from tools.run_uk_ie_d365_useful_leads_next import has_matching_fetch_proof
from tools.sync_uk_ie_d365_leads_to_northwind import validate_pack
from uk_ie_d365_leads.tools import (
    classification_review_tools,
    discovery_backbone_tools,
    lead_tools,
    opportunity_vetting_tools,
    report_composer_tools,
)


def test_link_text_is_attributed_to_fetched_page_not_unfetched_destination() -> None:
    source_url = "https://news.example.org/technology"
    leads = extract_public_signals_from_source(
        {
            "ok": True,
            "fetch_status": "success",
            "fetched_at": "2026-07-22T00:00:00+00:00",
            "resolved_url": source_url,
            "source_meta": {
                "source_name": "Public News",
                "base_url": source_url,
                "type": "news",
                "search_terms": ["digital"],
            },
            "links": [
                {
                    "url": "javascript:alert(1)",
                    "text": "Acme launches a major digital transformation and enterprise integration programme",
                }
            ],
            "text": "",
        }
    )

    assert leads
    assert leads[0]["evidence_url"] == source_url
    assert leads[0]["source_fetch_url"] == source_url


def test_model_facing_extractor_uses_refetched_source_not_supplied_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sl_trigger_leads.tools import source_fetcher

    source_url = "https://news.example.org/technology"
    monkeypatch.setattr(
        source_fetcher,
        "fetch_url",
        lambda _url: {
            "ok": True,
            "url": source_url,
            "fetched_at": "2026-07-22T00:00:00+00:00",
            "text": (
                '<a href="/acme">Acme launches a major digital transformation '
                "and enterprise integration programme</a>"
            ),
        },
    )

    leads = extract_public_signals(
        "Fabricated Company announces a fake digital programme",
        {
            "source_name": "Public News",
            "base_url": source_url,
            "type": "news",
            "search_terms": ["digital"],
        },
    )

    assert leads
    assert leads[0]["company"] != "Fabricated Company"
    assert "Fabricated Company" not in leads[0]["evidence_excerpt"]


def test_fetch_proof_requires_exact_evidence_url() -> None:
    lead = {
        "company": "Acme",
        "evidence_url": "https://news.example.org/acme",
        "evidence_excerpt": "Acme is expanding its digital delivery team.",
        "verified_live": True,
        "source_fetch_status": "fetched",
        "source_fetch_url": "https://news.example.org/another-company",
    }

    with pytest.raises(ValueError, match="does not match"):
        assert_no_simulation_data([lead], require_fetch_proof=True)


def test_unknown_source_provenance_fails_closed() -> None:
    channel = discovery_backbone_tools.classify_source_channel(
        source="mystery-provider", url="https://unknown.example.org/result"
    )

    assert channel == "unknown"
    assert discovery_backbone_tools.final_pdf_eligible_from_channel(channel) is False
    assert discovery_backbone_tools.final_pdf_eligible_from_channel(None) is False


def test_model_payload_secret_scan_runs_before_external_call() -> None:
    with pytest.raises(RuntimeError, match="external model call refused"):
        classification_review_tools.assert_secret_free_payload(
            {"evidence": "Authorization: Bearer abcdefghijklmnop"},
            context="test",
        )

    with pytest.raises(RuntimeError, match="external model call refused"):
        report_composer_tools.assert_secret_free_model_payload(
            {"evidence": "Authorization: Bearer abcdefghijklmnop"},
            context="test",
        )


def test_discovery_inspection_rejects_paths_outside_evidence() -> None:
    with pytest.raises(ValueError, match="restricted"):
        lead_tools._approved_evidence_root(Path(__file__).resolve().parents[2])


def test_report_inventory_requires_url_bound_successful_fetch_proof() -> None:
    lead = {
        "company_name": "Acme",
        "evidence_url": "https://news.example.org/acme",
        "evidence_excerpt": "Acme launched a transformation programme.",
        "verified_live": True,
    }
    unproven = report_composer_tools.evidence_account_from_lead(lead, None)
    mismatched = report_composer_tools.evidence_account_from_lead(
        lead,
        {
            "url": "https://news.example.org/other",
            "final_url": "https://news.example.org/other",
            "source_fetch_status": "fetched",
            "verified_live": True,
        },
    )
    proven = report_composer_tools.evidence_account_from_lead(
        lead,
        {
            "url": lead["evidence_url"],
            "final_url": lead["evidence_url"],
            "source_fetch_status": "fetched",
            "verified_live": True,
        },
    )

    assert unproven["evidence"] == []
    assert mismatched["evidence"] == []
    assert proven["evidence"][0]["verified_live"] is True


def test_report_follow_up_ignores_unfetched_search_results() -> None:
    inventory = {
        "accounts": [{"account": "Acme", "evidence": []}],
        "allowed_evidence_urls": [],
        "evidence_by_url": {},
    }
    updated = report_composer_tools.attach_follow_up_evidence(
        inventory,
        [
            {
                "kind": "search_result",
                "target": "Acme",
                "url": "https://news.example.org/acme",
                "verified_live": True,
                "snippet": "Unfetched search snippet.",
            }
        ],
    )

    assert updated["accounts"][0]["evidence"] == []
    assert updated["allowed_evidence_urls"] == []


def test_northwind_sync_rejects_mismatched_fetch_proof() -> None:
    lead = {
        "candidate_id": "candidate-1",
        "company_name": "Acme",
        "country": "United Kingdom",
        "sector": "Manufacturing",
        "signal_type": "d365_rollout",
        "opportunity_signal": "Acme is rolling out Dynamics 365.",
        "why_this_matters_to_1bt": "A delivery and integration opportunity.",
        "commercial_opening": "Discuss delivery capacity.",
        "evidence_url": "https://news.example.org/acme",
        "evidence_excerpt": "Acme is rolling out Dynamics 365.",
        "fetched_at": "2026-07-22T00:00:00Z",
        "verified_live": True,
        "source_channel": "public_web",
        "source_name": "Acme public news",
    }

    with pytest.raises(RuntimeError, match="does not match"):
        validate_pack(
            {"leads": [lead]},
            expected_count=1,
            fetch_proofs={
                "candidate-1": {
                    "candidate_id": "candidate-1",
                    "company_name": "Other Company",
                    "evidence_url": lead["evidence_url"],
                    "source_fetch_status": "fetched",
                    "verified_live": True,
                }
            },
        )


def test_legacy_curator_requires_url_bound_fetch_proof() -> None:
    evidence_url = "https://news.example.org/acme"
    candidate = {
        "evidence_urls": [evidence_url],
        "verified_live": True,
        "source_fetch": {
            "url": "https://news.example.org/other",
            "final_url": "https://news.example.org/other",
            "verified_live": True,
            "source_fetch_status": "fetched",
        },
    }

    assert has_matching_fetch_proof(candidate) is False
    candidate["source_fetch"]["final_url"] = evidence_url
    assert has_matching_fetch_proof(candidate) is False
    candidate["source_fetch"].update(
        {
            "source_name": "Acme public news",
            "fetched_at": "2026-07-22T00:00:00Z",
        }
    )
    assert has_matching_fetch_proof(candidate) is True


def test_opportunity_vetting_rejects_mismatched_fetch_and_tender_evidence() -> None:
    evidence_url = "https://news.example.org/acme-dynamics-365"
    candidate = {
        "company_name": "Acme",
        "evidence_urls": [evidence_url],
        "evidence_snippets": ["Acme is rolling out Dynamics 365."],
        "source_channel": "public_web",
        "verified_live": True,
        "source_fetch": {
            "url": "https://news.example.org/other",
            "final_url": "https://news.example.org/other",
            "verified_live": True,
            "source_fetch_status": "fetched",
        },
    }
    review = {
        "company_name": "Acme",
        "source_channel": "public_web",
        "lead_status": "ready_to_contact",
        "signal_strength": "strong",
        "evidence_used": [evidence_url, "Acme is rolling out Dynamics 365."],
    }

    reason = opportunity_vetting_tools.exclusion_reason_for_review(
        review,
        candidate,
        "Acme",
        duplicate_blocklist=set(),
        follow_up=[],
    )
    assert reason == "missing_verified_live_public_evidence"

    tender_url = "https://www.find-tender.service.gov.uk/Notice/123"
    candidate["evidence_urls"] = [tender_url]
    candidate["evidence_snippets"] = ["Dynamics 365 support tender notice."]
    candidate["source_fetch"] = {
        "url": tender_url,
        "final_url": tender_url,
        "verified_live": True,
        "source_fetch_status": "fetched",
    }
    review["evidence_used"] = [tender_url, "Dynamics 365 support tender notice."]
    reason = opportunity_vetting_tools.exclusion_reason_for_review(
        review,
        candidate,
        "Acme",
        duplicate_blocklist=set(),
        follow_up=[],
    )
    assert reason == "tender_or_procurement_out_of_scope"


def test_opportunity_vetting_reports_forbidden_declared_url() -> None:
    evidence_url = "https://www.linkedin.com/company/acme"
    candidate = {
        "company_name": "Acme",
        "evidence_urls": [evidence_url],
        "evidence_snippets": ["Acme uses Dynamics 365."],
        "source_channel": "public_web",
        "source_fetch": {
            "url": evidence_url,
            "final_url": evidence_url,
            "verified_live": True,
            "source_fetch_status": "fetched",
        },
    }
    review = {
        "company_name": "Acme",
        "source_channel": "public_web",
        "lead_status": "ready_to_contact",
        "signal_strength": "strong",
        "evidence_used": [evidence_url, "Acme uses Dynamics 365."],
    }

    reason = opportunity_vetting_tools.exclusion_reason_for_review(
        review,
        candidate,
        "Acme",
        duplicate_blocklist=set(),
        follow_up=[],
    )
    assert reason == "forbidden_source_url"


def test_new_opportunity_flag_does_not_bypass_evidence_verification() -> None:
    evidence_url = "https://news.example.org/acme-new-opportunity"
    candidate = {
        "company_name": "Acme",
        "evidence_urls": [evidence_url],
        "evidence_snippets": ["Acme announced a new Dynamics 365 programme."],
        "source_channel": "public_web",
        "same_company_new_opportunity_evidenced": True,
    }
    review = {
        "company_name": "Acme",
        "source_channel": "public_web",
        "lead_status": "ready_to_contact",
        "signal_strength": "strong",
        "evidence_used": [evidence_url],
        "same_company_new_opportunity_evidenced": True,
    }

    reason = opportunity_vetting_tools.exclusion_reason_for_review(
        review,
        candidate,
        "Acme",
        duplicate_blocklist={"acme"},
        follow_up=[],
    )
    assert reason == "missing_verified_live_public_evidence"
