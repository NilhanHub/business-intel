from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "refresh_uk_ie_d365_70_company_intel.py"
SPEC = importlib.util.spec_from_file_location("refresh_70_company_intel", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_query_overrides_cover_guarded_refresh_queue() -> None:
    if not MODULE.DEFAULT_QUEUE.is_file():
        pytest.skip("requires ignored private UK/IE Evidence fixtures")
    queue = MODULE.json.loads(MODULE.DEFAULT_QUEUE.read_text(encoding="utf-8"))
    names = {row["canonical_company_name"] for row in queue["companies"]}
    assert names == set(MODULE.QUERY_OVERRIDES)


def test_source_score_prefers_direct_verified_specific_evidence() -> None:
    direct = {
        "final_url": "https://www.microsoft.com/customer-story/biffa",
        "title": "Biffa Dynamics 365 Finance implementation",
        "snippet": "Biffa implemented Dynamics 365 Finance for procurement automation.",
        "text_excerpt": "Biffa processes 250,000 invoice lines per month.",
        "source_fetch_status": "fetched",
        "verified_live": True,
    }
    redirect = {
        "final_url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc",
        "title": "Biffa",
        "snippet": "Dynamics 365",
        "text_excerpt": "",
        "source_fetch_status": "http_error",
        "verified_live": False,
    }
    assert MODULE.source_score("Biffa Group", direct) > MODULE.source_score(
        "Biffa Group", redirect
    )


def test_refresh_has_one_operation_and_no_retry_loop() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "max_live_requests=1" in source
    assert "for attempt" not in source
    assert (
        "retry" not in MODULE.refresh_company.__doc__.lower()
        if MODULE.refresh_company.__doc__
        else True
    )


def test_supplement_fetches_only_rows_without_a_live_source(monkeypatch) -> None:
    calls = []

    def fake_fetch(results, *, max_urls, parse_pdfs):
        calls.append((results, max_urls, parse_pdfs))
        return [
            {
                "url": results[0].url,
                "final_url": "https://example.org/direct",
                "status_code": 200,
                "source_fetch_status": "fetched",
                "verified_live": True,
            }
        ]

    monkeypatch.setattr(MODULE, "fetch_sources_for_results", fake_fetch)
    output = MODULE.supplement_missing_sources(
        {
            "companies": [
                {
                    "canonical_company_name": "Missing Co",
                    "previous_evidence_url": "https://redirect.example/a",
                    "previous_evidence": "Dynamics 365 rollout",
                    "live_sources": [],
                    "best_live_source": None,
                },
                {
                    "canonical_company_name": "Ready Co",
                    "previous_evidence_url": "https://redirect.example/b",
                    "best_live_source": {"verified_live": True},
                },
            ]
        }
    )
    assert len(calls) == 1
    assert calls[0][1:] == (1, True)
    assert output["best_direct_live_source_count"] == 2


def test_refresh_company_selects_the_first_verified_source(monkeypatch) -> None:
    monkeypatch.setattr(
        MODULE, "find_uk_ie_d365_leads", lambda **_kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(
        MODULE,
        "live_sources",
        lambda _result, _company: [
            {"verified_live": False, "source_score": 999},
            {
                "verified_live": True,
                "source_score": 10,
                "final_url": "https://example.org/live",
            },
        ],
    )
    row = MODULE.refresh_company(
        {"canonical_company_name": "Biffa Group"}, max_results=3
    )
    assert row["best_live_source"]["final_url"] == "https://example.org/live"


def test_refresh_batch_keeps_processing_after_one_company_fails(monkeypatch) -> None:
    def fake_refresh(row, *, max_results):
        if row["canonical_company_name"] == "Broken Co":
            raise RuntimeError("temporary provider failure")
        return {
            "canonical_company_name": row["canonical_company_name"],
            "best_live_source": {"verified_live": True},
            "max_results": max_results,
        }

    monkeypatch.setattr(MODULE, "refresh_company", fake_refresh)
    rows = MODULE.refresh_companies(
        [
            {"canonical_company_name": "Broken Co"},
            {"canonical_company_name": "Ready Co"},
        ],
        max_results=4,
    )
    assert [row["canonical_company_name"] for row in rows] == ["Broken Co", "Ready Co"]
    assert rows[0]["search_status"] == "refresh_error"
    assert rows[0]["error"]["type"] == "RuntimeError"
    assert rows[1]["max_results"] == 4


def test_supplement_isolates_fetch_errors_and_uses_direct_override(monkeypatch) -> None:
    calls = []

    def fake_fetch(results, *, max_urls, parse_pdfs):
        del max_urls, parse_pdfs
        calls.append(results[0].url)
        if "medius.com" in results[0].url:
            raise TimeoutError("slow source")
        return [
            {
                "url": results[0].url,
                "final_url": results[0].url,
                "source_fetch_status": "fetched",
                "verified_live": True,
                "fetched_at": "2026-07-19T12:00:00Z",
                "text_excerpt": "Verified Dynamics 365 evidence",
            }
        ]

    monkeypatch.setattr(MODULE, "fetch_sources_for_results", fake_fetch)
    output = MODULE.supplement_missing_sources(
        {
            "companies": [
                {
                    "canonical_company_name": "Charterhouse Holdings",
                    "previous_evidence_url": "https://redirect.invalid/old",
                    "previous_evidence": "D365 evidence",
                    "best_live_source": {"verified_live": False},
                },
                {
                    "canonical_company_name": "Uniphar Medtech",
                    "previous_evidence_url": "https://example.org/uniphar",
                    "previous_evidence": "Business Central evidence",
                    "best_live_source": None,
                },
            ]
        }
    )
    assert calls[0] == MODULE.SOURCE_URL_OVERRIDES["Charterhouse Holdings"]
    assert output["companies"][0]["supplement_status"] == "fetch_error"
    assert output["companies"][1]["supplement_status"] == "verified"
    assert output["best_direct_live_source_count"] == 1


def test_model_metadata_uses_effective_environment_value(monkeypatch) -> None:
    monkeypatch.setenv("D365_GOOGLE_MODEL", "gemini-custom-model")
    assert MODULE.effective_model_name() == "gemini-custom-model"
    monkeypatch.setenv("D365_GOOGLE_MODEL", "  ")
    assert MODULE.effective_model_name() == "gemini-2.5-flash"


def test_refresh_paths_must_stay_under_evidence(tmp_path, monkeypatch) -> None:
    evidence = (tmp_path / "Evidence").resolve()
    evidence.mkdir()
    monkeypatch.setattr(MODULE, "EVIDENCE_ROOT", evidence)
    assert (
        MODULE.evidence_path(evidence / "proof.json", label="Proof")
        == evidence / "proof.json"
    )
    with pytest.raises(RuntimeError, match="must stay within"):
        MODULE.evidence_path(tmp_path / "outside.json", label="Output")
