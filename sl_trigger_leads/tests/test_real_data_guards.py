import unittest
from unittest.mock import patch

from sl_trigger_leads.agent import ROOT_INSTRUCTION
from sl_trigger_leads.tools.live_source_tools import (
    find_live_leads,
    report_source_failures,
    score_live_lead,
)
from sl_trigger_leads.tools.signal_extractor import extract_public_signals_from_source
from sl_trigger_leads.tools.signal_tools import assert_no_simulation_data
from sl_trigger_leads.tools.source_recovery import recover_source_url
from sl_trigger_leads.tools.source_registry import list_configured_sources


class RealDataGuardTest(unittest.TestCase):
    def test_example_test_urls_are_blocked(self):
        with self.assertRaises(ValueError):
            assert_no_simulation_data(
                [
                    {
                        "company": "Fake Co",
                        "evidence_url": "https://example.test/fake",
                        "evidence_excerpt": "Fake excerpt",
                        "verified_live": True,
                    }
                ]
            )

    def test_missing_evidence_url_is_blocked(self):
        with self.assertRaises(ValueError):
            assert_no_simulation_data(
                [
                    {
                        "company": "Real Co",
                        "evidence_excerpt": "Live excerpt",
                        "verified_live": True,
                    }
                ]
            )

    def test_missing_verified_live_true_is_blocked(self):
        with self.assertRaises(ValueError):
            assert_no_simulation_data(
                [
                    {
                        "company": "Real Co",
                        "evidence_url": "https://www.ft.lk/it-telecom-tech/50",
                        "evidence_excerpt": "Live excerpt",
                        "verified_live": False,
                    }
                ]
            )

    def test_sample_markers_are_blocked(self):
        with self.assertRaises(ValueError):
            assert_no_simulation_data(
                [
                    {
                        "company": "Sample Co",
                        "evidence_url": "https://www.ft.lk/it-telecom-tech/50",
                        "evidence_excerpt": "SAMPLE DATA should never be returned",
                        "verified_live": True,
                    }
                ]
            )


class RealLeadWorkflowTest(unittest.TestCase):
    def test_list_configured_sources_returns_public_urls(self):
        result = list_configured_sources(include_urls=True)
        urls = [source.get("base_url") for source in result["sources"]]
        self.assertIn("https://www.ft.lk/it-telecom-tech/50", urls)
        self.assertIn("https://www.cse.lk/announcements", urls)
        self.assertTrue(result["public_url_policy"].startswith("Configured public source names and URLs are not confidential"))

    def test_agent_instruction_does_not_claim_source_urls_confidential(self):
        lowered = ROOT_INSTRUCTION.lower()
        self.assertIn("configured public source names and urls are not confidential", lowered)
        self.assertNotIn("cannot disclose", lowered)
        self.assertNotIn("source secrecy", lowered.replace("do not claim source secrecy", ""))

    def test_cse_old_404_url_recovers_to_announcements(self):
        failed_source = {
            "source_id": "cse_announcements",
            "source_name": "Colombo Stock Exchange - Company Announcements",
            "base_url": "https://www.cse.lk/pages/company-announcements/company-announcements.component.html",
            "type": "announcements",
            "search_terms": ["announcement", "corporate disclosure", "cse"],
            "recovery_candidates": [
                "https://www.cse.lk/",
                "https://www.cse.lk/announcements",
                "https://www.cse.lk/announcements/?category=CORPORATE+DISCLOSURE",
                "https://www.cse.lk/general-announcements",
            ],
        }
        result = recover_source_url(
            failed_source,
            {
                "failed_url": failed_source["base_url"],
                "failure_type": "http_404",
                "status_code": 404,
                "original_source_type": "announcements",
            },
        )
        self.assertTrue(result["recovery_attempted"])
        self.assertIn(result["recovery_status"], {"recovered", "candidate_found"})
        self.assertTrue(result["note_for_user"])
        candidate_urls = [item["url"] for item in result["candidate_urls"]]
        self.assertIn("https://www.cse.lk/announcements", candidate_urls)
        if result["recovery_status"] == "recovered":
            self.assertIn("cse.lk", result["selected_replacement_url"])

    def test_scoring_works_on_source_backed_fixture(self):
        lead = {
            "company": "Dialog Enterprise",
            "country": "Sri Lanka",
            "sector": "software/IT services",
            "trigger_type": "ai_or_digital_initiative",
            "trigger_summary": "Dialog Enterprise partners Star Garments: Pioneering 5G innovation in Sri Lanka's apparel industry",
            "evidence_url": "https://www.ft.lk/it-telecom-tech/50",
            "evidence_excerpt": "Dialog Enterprise partners Star Garments: Pioneering 5G innovation in Sri Lanka's apparel industry Friday, 24 April 2026 04:49",
            "source_name": "Daily FT - IT / Telecom / Tech",
            "source_type": "news",
            "published_or_seen_date": "Friday, 24 April 2026",
            "fetched_at": "2026-04-28T00:00:00+00:00",
            "verified_live": True,
            "1bt_fit": ["integrations", "backend/software delivery support"],
            "limits": "Fixture uses a real public source URL; details still need manual verification.",
        }
        scored = score_live_lead(lead)
        self.assertTrue(scored["verified_live"])
        self.assertIn("score", scored)
        self.assertGreaterEqual(scored["score"]["total"], 40)
        self.assertLessEqual(scored["score"]["total"], 100)

    def test_extract_public_signals_from_real_source_shape(self):
        source_result = {
            "ok": True,
            "fetched_at": "2026-04-28T00:00:00+00:00",
            "resolved_url": "https://www.ft.lk/it-telecom-tech/50",
            "source_meta": {
                "source_id": "dailyft_it_telecom_tech",
                "source_name": "Daily FT - IT / Telecom / Tech",
                "base_url": "https://www.ft.lk/it-telecom-tech/50",
                "type": "news",
                "search_terms": ["digital", "partners", "AI", "automation"],
            },
            "links": [
                {
                    "url": "https://www.ft.lk/it-telecom-tech/50",
                    "text": "Dialog Enterprise partners Star Garments: Pioneering 5G innovation in Sri Lanka's apparel industry Friday, 24 April 2026 04:49",
                }
            ],
            "text": "",
        }
        leads = extract_public_signals_from_source(source_result)
        self.assertGreaterEqual(len(leads), 1)
        assert_no_simulation_data(leads)

    def test_live_fetch_failures_are_reported(self):
        result = report_source_failures(
            {
                "source_failures": [
                    {
                        "source_id": "bad_source",
                        "source_name": "Bad Source",
                        "url": "https://www.ft.lk/it-telecom-tech/50",
                        "error": "TimeoutError",
                    }
                ]
            }
        )
        self.assertEqual(result["failure_count"], 1)

    @patch("sl_trigger_leads.tools.live_source_tools.fetch_live_sources")
    def test_find_live_leads_returns_verified_or_no_results_message(self, mocked_fetch):
        mocked_fetch.return_value = {
            "fetched_at": "2026-04-28T00:00:00+00:00",
            "source_count": 1,
            "failures": [],
            "source_coverage": [
                {
                    "source_id": "dailyft_it_telecom_tech",
                    "source_name": "Daily FT - IT / Telecom / Tech",
                    "source_type": "news",
                    "configured_url": "https://www.ft.lk/it-telecom-tech/50",
                    "fetch_status": "success",
                    "failure_reason": "",
                    "recovery_attempted": False,
                    "recovered_url": None,
                    "recovery_note": "",
                    "fetched_at": "2026-04-28T00:00:00+00:00",
                }
            ],
            "sources": [
                {
                    "ok": True,
                    "fetched_at": "2026-04-28T00:00:00+00:00",
                    "resolved_url": "https://www.ft.lk/it-telecom-tech/50",
                    "status_code": 200,
                    "source_meta": {
                        "source_id": "dailyft_it_telecom_tech",
                        "source_name": "Daily FT - IT / Telecom / Tech",
                        "base_url": "https://www.ft.lk/it-telecom-tech/50",
                        "type": "news",
                        "search_terms": ["digital", "partners", "AI"],
                    },
                    "links": [
                        {
                            "url": "https://www.ft.lk/it-telecom-tech/50",
                            "text": "Dialog Enterprise partners Star Garments: Pioneering 5G innovation in Sri Lanka's apparel industry Friday, 24 April 2026 04:49",
                        }
                    ],
                    "text": "",
                }
            ],
        }
        result = find_live_leads(max_results=5, source_limit=1, write_outputs=False)
        self.assertIn("leads", result)
        self.assertIn("source_coverage", result)
        self.assertIn("source_coverage_summary", result)
        self.assertEqual(result["source_coverage_summary"]["sources_checked"], 1)
        if result["leads"]:
            assert_no_simulation_data(result["leads"])
        else:
            self.assertEqual(result["message"], "No verified live leads found from the configured sources in this run.")


if __name__ == "__main__":
    unittest.main()
