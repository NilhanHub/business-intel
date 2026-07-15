import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from hello_cloud_agent.hello_cloud_agent.agent import root_agent as hello_root_agent
from sl_trigger_leads.agent import root_agent as sl_root_agent
from uk_ie_d365_leads.agent import app, root_agent
from uk_ie_d365_leads.agents.classification_reviewer_agent import (
    classification_reviewer_agent,
    d365_classification_reviewer_agent,
)
from uk_ie_d365_leads.agents.end_customer_extractor_agent import (
    d365_end_customer_extractor_agent,
    end_customer_extractor_agent,
)
from uk_ie_d365_leads.agents.opportunity_vetter_agent import (
    d365_opportunity_vetter_agent,
    opportunity_vetter_agent,
)
from uk_ie_d365_leads.agents.report_composer_agent import (
    d365_report_composer_agent,
    report_composer_agent,
)
from uk_ie_d365_leads.tools import (
    classification_review_tools,
    discovery_backbone_tools,
    lead_tools,
    opportunity_vetting_tools,
    report_composer_tools,
)


class UkIeD365LeadsTest(unittest.TestCase):
    evidence_run_path = Path(__file__).resolve().parents[2] / "Evidence" / "UK_IE_D365_COMMERCIAL_SEARCH_RUN.json"
    audit_replay_path = Path(__file__).resolve().parents[2] / "Evidence" / "UK_IE_D365_AUDIT_REPLAY.json"
    review_script_path = Path(__file__).resolve().parents[2] / "tools" / "review_uk_ie_d365_candidates.py"
    vetter_check_script_path = Path(__file__).resolve().parents[2] / "tools" / "check_uk_ie_d365_vetter_agent.py"
    report_composer_script_path = Path(__file__).resolve().parents[2] / "tools" / "run_uk_ie_d365_report_composer.py"

    @classmethod
    def review_module(cls):
        spec = importlib.util.spec_from_file_location("review_uk_ie_d365_candidates", cls.review_script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @classmethod
    def vetter_check_module(cls):
        spec = importlib.util.spec_from_file_location("check_uk_ie_d365_vetter_agent", cls.vetter_check_script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @classmethod
    def report_composer_module(cls):
        spec = importlib.util.spec_from_file_location("run_uk_ie_d365_report_composer", cls.report_composer_script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_agent_import_and_shape(self):
        self.assertEqual(root_agent.name, "uk_ie_d365_leads")
        self.assertEqual(app.name, "uk_ie_d365_leads")
        self.assertIn("d365_search_agent", [agent.name for agent in root_agent.sub_agents])
        self.assertIn("d365_classification_reviewer_agent", [agent.name for agent in root_agent.sub_agents])
        self.assertIn("d365_end_customer_extractor_agent", [agent.name for agent in root_agent.sub_agents])
        self.assertIn("d365_opportunity_vetter_agent", [agent.name for agent in root_agent.sub_agents])
        self.assertIn("d365_report_composer_agent", [agent.name for agent in root_agent.sub_agents])
        self.assertGreaterEqual(len(root_agent.tools), 3)
        self.assertIn("run_uk_ie_d365_report_composer.py", root_agent.instruction)
        self.assertIn("UK_IE_D365_USEFUL_LEADS_FRESH_20260612.json", root_agent.instruction)

    def test_end_customer_extractor_agent_contract(self):
        self.assertIs(end_customer_extractor_agent, d365_end_customer_extractor_agent)
        self.assertEqual(d365_end_customer_extractor_agent.name, "d365_end_customer_extractor_agent")
        self.assertEqual(list(d365_end_customer_extractor_agent.tools), [])
        instruction = d365_end_customer_extractor_agent.instruction.lower()
        self.assertIn("source company separately", instruction)
        self.assertIn("never invent companies", instruction)

    def test_report_composer_agent_contract(self):
        self.assertIs(report_composer_agent, d365_report_composer_agent)
        self.assertEqual(d365_report_composer_agent.name, "d365_report_composer_agent")
        instruction = d365_report_composer_agent.instruction.lower()
        for phrase in (
            "strict json",
            "only the supplied evidence",
            "do not invent companies",
            "no gmail",
            "private or authenticated linkedin",
            "tender/procurement-only",
            "fake/sample/demo",
        ):
            self.assertIn(phrase, instruction)

    def test_provider_unavailable_does_not_generate_fake_leads(self):
        provider = lead_tools.ProviderUnavailable("missing credentials")
        self.assertFalse(provider.configured)
        self.assertEqual(provider.search_web("Dynamics 365 support UK", limit=5), [])

    def test_fanout_skips_unavailable_providers_and_records_readiness(self):
        google = self._fake_provider(
            "google_grounding",
            [
                lead_tools.SearchResult(
                    title="Northstar Components implements Dynamics 365 Business Central",
                    url="https://northstar-components.co.uk/news/dynamics-365-business-central",
                    snippet="UK manufacturer Northstar Components implemented Dynamics 365 Business Central for finance operations.",
                    source="google_grounding",
                )
            ],
        )
        exa = self._fake_provider("exa", [], configured=False, unavailable_reason="EXA_API_KEY is not set")
        with patch.object(lead_tools, "_provider_candidates", return_value=[google, exa]):
            result = lead_tools.find_uk_ie_d365_leads(
                provider_name="fanout",
                max_results=5,
                max_live_requests=5,
                include_rejected=True,
                source_fetch=False,
                fanout_queries_per_provider=1,
            )
        self.assertEqual(result["provider"], "fanout")
        self.assertEqual(result["provider_budget"]["google_grounding"]["requests_attempted"], 1)
        readiness = {item["name"]: item for item in result["provider_readiness"]["providers"]}
        self.assertFalse(readiness["exa"]["configured"])
        self.assertIn("EXA_API_KEY", readiness["exa"]["unavailable_reason"])

    def test_fanout_dedupes_same_url_across_providers(self):
        shared = lead_tools.SearchResult(
            title="Northstar Components implements Dynamics 365 Business Central",
            url="https://northstar-components.co.uk/news/dynamics-365-business-central?utm_source=google",
            snippet="UK manufacturer Northstar Components implemented Dynamics 365 Business Central for finance operations.",
            source="google_grounding",
        )
        duplicate = lead_tools.SearchResult(
            title="Northstar Components Dynamics 365 case study",
            url="https://www.northstar-components.co.uk/news/dynamics-365-business-central",
            snippet="Northstar Components in the UK implemented Dynamics 365 Business Central.",
            source="exa",
        )
        providers = [
            self._fake_provider("google_grounding", [shared]),
            self._fake_provider("exa", [duplicate]),
        ]
        with patch.object(lead_tools, "_provider_candidates", return_value=providers):
            result = lead_tools.find_uk_ie_d365_leads(
                provider_name="fanout",
                max_results=5,
                max_live_requests=5,
                include_rejected=True,
                source_fetch=False,
                fanout_queries_per_provider=1,
            )
        self.assertEqual(result["raw_result_count"], 2)
        self.assertEqual(result["deduped_raw_result_count"], 1)
        self.assertEqual(result["duplicate_raw_result_count"], 1)

    def test_fanout_provider_failure_keeps_partial_results(self):
        google = self._fake_provider("google_grounding", [], error=TimeoutError("search timed out"))
        exa = self._fake_provider(
            "exa",
            [
                lead_tools.SearchResult(
                    title="Glenveagh rolls out Dynamics 365 Customer Service in Ireland",
                    url="https://www.glenveagh.ie/news/dynamics-365-customer-service",
                    snippet="Ireland housebuilder Glenveagh is rolling out Dynamics 365 Customer Service for customer communications.",
                    source="exa",
                )
            ],
        )
        with patch.object(lead_tools, "_provider_candidates", return_value=[google, exa]):
            result = lead_tools.find_uk_ie_d365_leads(
                provider_name="fanout",
                max_results=5,
                max_live_requests=5,
                include_rejected=True,
                source_fetch=False,
                fanout_queries_per_provider=1,
            )
        self.assertEqual(result["provider_budget"]["google_grounding"]["failures"], 1)
        self.assertEqual(result["provider_budget"]["google_grounding"]["timeouts"], 1)
        self.assertGreaterEqual(result["lead_count"], 1)
        self.assertTrue(result["provider_errors"])

    def test_source_fetcher_follows_redirect_and_records_final_url(self):
        class FakeResponse:
            url = "https://customer.example.co.uk/canonical-d365"
            status_code = 200
            ok = True
            headers: ClassVar[dict[str, str]] = {"content-type": "text/html; charset=utf-8"}
            encoding = "utf-8"
            apparent_encoding = "utf-8"
            content = (
                b"<html><head><title>Customer D365 story</title>"
                b"<link rel=\"canonical\" href=\"/canonical-d365\"></head>"
                b"<body>UK customer implemented Dynamics 365 Business Central.</body></html>"
            )

        with patch.object(lead_tools.requests, "get", return_value=FakeResponse()):
            fetched = lead_tools.SourceFetcher().fetch("https://redirect.example.co.uk/story", provider="unit")
        self.assertEqual(fetched["source_fetch_status"], "fetched")
        self.assertEqual(fetched["final_url"], "https://customer.example.co.uk/canonical-d365")
        self.assertEqual(fetched["canonical_url"], "https://customer.example.co.uk/canonical-d365")
        self.assertEqual(fetched["page_title"], "Customer D365 story")
        self.assertTrue(fetched["verified_live"])

    def test_source_fetcher_blocks_private_tender_fake_and_binary_urls(self):
        cases = {
            "https://www.linkedin.com/company/private": "skipped_private_linkedin_source",
            "https://www.find-tender.service.gov.uk/Notice/123": "skipped_tender_or_procurement_source",
            "https://example.com/dynamics-365": "skipped_fake_or_example_source",
            "https://customer.co.uk/case-study.pdf": "skipped_binary_source",
        }
        fetcher = lead_tools.SourceFetcher()
        for url, expected in cases.items():
            with self.subTest(url=url):
                fetched = fetcher.fetch(url, provider="unit")
                self.assertEqual(fetched["source_fetch_status"], expected)
                self.assertFalse(fetched["verified_live"])

    def test_source_fetcher_parses_public_text_pdf_when_enabled(self):
        class FakeResponse:
            url = "https://customer.co.uk/case-study.pdf"
            status_code = 200
            ok = True
            headers: ClassVar[dict[str, str]] = {"content-type": "application/pdf"}
            encoding = None
            apparent_encoding = None
            content = None

        FakeResponse.content = self._minimal_text_pdf(
            "Contoso Retail Ltd implemented Dynamics 365 Business Central for UK finance operations."
        )
        with patch.object(lead_tools.requests, "get", return_value=FakeResponse()):
            fetched = lead_tools.SourceFetcher(parse_pdfs=True).fetch(
                "https://customer.co.uk/case-study.pdf",
                provider="unit",
            )
        self.assertEqual(fetched["source_fetch_status"], "fetched")
        self.assertTrue(fetched["verified_live"])
        self.assertIn("Contoso Retail Ltd", fetched["text_excerpt"])
        self.assertIn("pdf_", fetched["pdf_parser_status"])

    def test_source_fetcher_keeps_image_heavy_pdf_for_cleanup(self):
        class FakeResponse:
            url = "https://customer.co.uk/image-only-case-study.pdf"
            status_code = 200
            ok = True
            headers: ClassVar[dict[str, str]] = {"content-type": "application/pdf"}
            encoding = None
            apparent_encoding = None
            content = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"

        with patch.object(lead_tools.requests, "get", return_value=FakeResponse()):
            fetched = lead_tools.SourceFetcher(parse_pdfs=True).fetch(
                "https://customer.co.uk/image-only-case-study.pdf",
                provider="unit",
            )
        self.assertFalse(fetched["verified_live"])
        self.assertNotEqual(fetched["source_fetch_status"], "fetched")
        self.assertIn(fetched["pdf_parser_status"], {"pdf_no_text_extracted", "pdf_parse_error", "pdf_invalid_or_truncated"})

    def test_query_pack_and_known_good_domains_generate_targeted_queries(self):
        preflight = {
            "memory_preflight": {
                "known_good_domains": ["partner-services.co.uk"],
            }
        }
        plan = lead_tools.build_query_plan(
            cloud_preflight=preflight,
            query_pack="pdf",
        )
        queries = [item["query"] for item in plan]
        self.assertTrue(any(query.startswith("site:partner-services.co.uk") for query in queries))
        self.assertTrue(any("filetype:pdf" in query for query in queries))

    def test_shortage_report_seeds_cleanup_queries(self):
        plan = lead_tools.build_query_plan(
            query_pack="default",
            shortage_report={
                "shortage_count": 2,
                "queue_counts": {"source_cleanup_queue": 1, "identity_resolution_queue": 1},
                "next_actions": ["Resolve end-customer identity.", "Fetch or replace source URLs."],
                "selection_exclusions": [{"company_name": "Northstar Components"}],
            },
        )
        queries = [item["query"] for item in plan]
        self.assertTrue(any("customer story" in query.lower() for query in queries))
        self.assertTrue(any('"Northstar Components"' in query for query in queries))

    def test_retry_source_fetches_filters_hard_skips_and_retries_timeouts(self):
        payload = [
            {"url": "https://customer.co.uk/timeout", "source_fetch_status": "timeout", "provider": "unit"},
            {"url": "https://www.linkedin.com/company/private", "source_fetch_status": "skipped_private_linkedin_source"},
            {"url": "https://customer.co.uk/case-study.pdf", "source_fetch_status": "skipped_binary_source"},
        ]
        candidates_without_pdf = lead_tools.source_retry_candidates(payload, parse_pdfs=False)
        self.assertEqual([item["url"] for item in candidates_without_pdf], ["https://customer.co.uk/timeout"])
        candidates_with_pdf = lead_tools.source_retry_candidates(payload, parse_pdfs=True)
        self.assertEqual(
            [item["url"] for item in candidates_with_pdf],
            ["https://customer.co.uk/timeout", "https://customer.co.uk/case-study.pdf"],
        )

    def test_provider_scorecard_records_outcomes(self):
        raw_search = {
            "provider": "fanout",
            "run_id": "run_unit",
            "raw_result_ledger": [
                {
                    "provider": "google_grounding",
                    "url": "https://northstar-components.co.uk/d365",
                    "normalized_url": "https://northstar-components.co.uk/d365",
                    "source_query": "unit query",
                }
            ],
            "candidate_ledger": [
                {
                    "candidate_id": "cand_1",
                    "company_name": "Northstar Components",
                    "retention_status": "final_ready",
                    "source_provider": "google_grounding",
                    "source_query": "unit query",
                    "evidence_urls": ["https://northstar-components.co.uk/d365"],
                },
                {
                    "candidate_id": "cand_2",
                    "company_name": "Generic Jobs",
                    "retention_status": "hard_reject",
                    "source_provider": "exa",
                    "evidence_urls": ["https://jobs.example.co.uk/d365"],
                },
            ],
        }
        scorecard = lead_tools.build_provider_scorecard(
            raw_search,
            final_output={"leads": [{"candidate_id": "cand_1"}]},
        )
        providers = {item["key"]: item for item in scorecard["provider_scores"]}
        self.assertEqual(providers["google_grounding"]["counts"]["final_selected"], 1)
        self.assertEqual(providers["exa"]["hard_reject_count"], 1)

    def test_local_discovery_memory_collects_prior_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir)
            payload = {
                "leads": [
                    {
                        "candidate_id": "cand_final",
                        "company_name": "Northstar Components",
                        "retention_status": "final_ready",
                        "source_provider": "google_grounding",
                        "opportunity_fingerprint": "opp_final",
                        "evidence_urls": ["https://northstar-components.co.uk/d365"],
                    }
                ],
                "selection_exclusions": [
                    {
                        "candidate_id": "cand_dup",
                        "company_name": "Glenveagh",
                        "retention_status": "duplicate_same_opportunity",
                        "opportunity_fingerprint": "opp_dup",
                        "evidence_url": "https://www.glenveagh.ie/d365",
                    }
                ],
                "source_fetch_errors": [
                    {
                        "url": "https://customer.co.uk/source",
                        "source_fetch_status": "timeout",
                    }
                ],
                "hard_rejected_leads": [
                    {
                        "company_name": "Generic Jobs",
                        "retention_status": "hard_reject",
                        "rejection_reason": "generic_it_support_without_dynamics_365_evidence",
                    }
                ],
            }
            (evidence_dir / "UK_IE_D365_UNIT_MEMORY.json").write_text(json.dumps(payload), encoding="utf-8")
            memory = lead_tools.build_local_discovery_memory(evidence_dir)
        self.assertEqual(memory["prior_final_leads"][0]["company_name"], "Northstar Components")
        self.assertTrue(memory["prior_duplicate_opportunities"])
        self.assertEqual(memory["rejected_generic_patterns"]["generic_it_support_without_dynamics_365_evidence"], 1)
        self.assertEqual(memory["retryable_fetch_failures"][0]["source_fetch_status"], "timeout")

    def test_fetched_partner_page_resolves_end_customer_not_partner(self):
        result = lead_tools.SearchResult(
            title="Dynamics 365 customer story",
            url="https://partner-services.co.uk/case-studies/contoso-d365",
            snippet="Case study for a UK customer.",
            source="unit",
        )
        fetches = [
            {
                "url": result.url,
                "final_url": result.url,
                "source_name": "partner-services.co.uk",
                "source_fetch_status": "fetched",
                "verified_live": True,
                "text_excerpt": (
                    "Contoso Retail Ltd implemented Dynamics 365 Customer Service "
                    "for its UK contact centre with help from a Microsoft partner."
                ),
            }
        ]
        enriched = lead_tools.enrich_results_with_source_fetches([result], fetches)
        extraction = lead_tools.extract_d365_leads(enriched, max_results=5, include_rejected=True)
        lead = extraction["surfaced_leads"][0]
        self.assertEqual(lead["company_name"], "Contoso Retail Ltd")
        self.assertEqual(lead["source_company"], "Partner Services")
        self.assertEqual(lead["source_role"], "partner")
        self.assertTrue(lead["verified_live"])

    def test_partner_helped_pattern_resolves_named_end_customer(self):
        company = lead_tools.extract_named_target_company(
            "Partner Services helped Contoso Retail Ltd implement Dynamics 365 Customer Service across its UK contact centre."
        )
        self.assertEqual(company, "Contoso Retail Ltd")

    def test_blocked_without_named_provider_does_not_emit_leads(self):
        result = lead_tools.find_uk_ie_d365_leads(
            query="Dynamics 365 support UK",
            max_results=3,
            provider_name="definitely_missing_provider",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["leads"], [])
        self.assertIn("Unknown D365_SEARCH_PROVIDER", result["setup_error"])
        self.assertIn("audit_metadata", result)
        self.assertFalse(result["audit_metadata"]["live_search_run"])
        self.assertIn("cloud_discovery_preflight", result)
        self.assertEqual(result["source_channel_policy"]["hint_channels"], ["agent_search", "workspace_hint", "crm_hint", "custom_mcp"])

    def test_source_channel_policy_blocks_hint_channels_from_final_pdf(self):
        cases = {
            "google_grounding": "public_web",
            "Discovery Engine Agent Search": "agent_search",
            "Gmail alert": "workspace_hint",
            "Salesforce account clue": "crm_hint",
            "custom_mcp evidence resolver": "custom_mcp",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                channel = discovery_backbone_tools.classify_source_channel(source=source)
                self.assertEqual(channel, expected)
                self.assertEqual(
                    discovery_backbone_tools.final_pdf_eligible_from_channel(channel),
                    expected == "public_web",
                )

    def test_discovery_backbone_writes_local_agent_search_and_ledger_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir) / "Evidence"
            evidence_dir.mkdir()
            sample = {
                "artifact_type": "unit_pack",
                "run_id": "run_unit",
                "leads": [
                    {
                        "candidate_id": "cand_unit",
                        "company_name": "Northstar Components",
                        "retention_status": "final_ready",
                        "company_fingerprint": "company_unit",
                        "opportunity_fingerprint": "opp_unit",
                        "source_fingerprint": "source_unit",
                        "evidence_urls": ["https://northstar-components.co.uk/news/dynamics-365"],
                        "source_provider": "google_grounding",
                        "verified_live": True,
                    }
                ],
            }
            (evidence_dir / "UK_IE_D365_UNIT_PACK.json").write_text(json.dumps(sample), encoding="utf-8")
            paths = discovery_backbone_tools.write_local_backbone_artifacts(
                evidence_dir=evidence_dir,
                output_dir=evidence_dir,
                timestamp="20260625T000000Z",
            )
            for path in paths.values():
                self.assertTrue(Path(path).exists(), path)
            preflight = json.loads(Path(paths["preflight_json"]).read_text(encoding="utf-8"))
            self.assertEqual(preflight["memory_preflight"]["prior_company_count"], 1)
            self.assertIn("northstar-components.co.uk", preflight["memory_preflight"]["known_good_domains"])
            manifest = Path(paths["agent_search_import_manifest"]).read_text(encoding="utf-8")
            self.assertIn("gs://business-intel-123-business-intel-evidence/Evidence/UK_IE_D365_UNIT_PACK.json", manifest)
            ledger = json.loads(Path(paths["bigquery_ledger_mirror"]).read_text(encoding="utf-8"))
            self.assertEqual(ledger["table_counts"]["candidates"], 1)
            self.assertTrue(ledger["tables"]["candidates"][0]["final_pdf_eligible"])

    def test_extract_real_search_results_requires_d365_and_country(self):
        rows = [
            lead_tools.SearchResult(
                title="NHS Dynamics 365 support analyst",
                url="https://www.jobs.nhs.uk/candidate/jobadvert/d365-support",
                snippet=(
                    "UK NHS team hiring a Dynamics 365 Customer Service support "
                    "analyst for CRM backlog and managed support."
                ),
                source="unit",
            ),
            lead_tools.SearchResult(
                title="Generic IT support",
                url="https://example.com/support",
                snippet="Generic IT support with no Microsoft business application evidence.",
                source="unit",
            ),
        ]
        extraction = lead_tools.extract_d365_leads(rows, max_results=5, include_rejected=True)
        leads = extraction["surfaced_leads"]
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["country"], "United Kingdom")
        self.assertIn("Dynamics 365", leads[0]["dynamics_product"])
        self.assertIn(leads[0]["signal_tier"], {"A", "B"})
        self.assertTrue(leads[0]["evidence_urls"])
        self.assertTrue(leads[0]["evidence_snippets"])
        self.assertIn("company_website", leads[0])
        self.assertIn("source_type", leads[0])
        self.assertIn("missing_verification_points", leads[0])
        self.assertEqual(leads[0]["contact_route_status"], "not_resolved_by_this_agent")
        self.assertNotIn("example.test", json.dumps(leads))
        self.assertGreaterEqual(len(extraction["rejected_leads"]), 1)
        self.assertTrue(extraction["rejected_leads"][0]["rejection_reason"])
        self.assertIn("audit_trace", leads[0])
        self.assertIn("final_decision", leads[0])
        self.assertEqual(leads[0]["source_channel"], "public_web")
        self.assertTrue(leads[0]["final_pdf_eligible"])
        self.assertEqual(leads[0]["audit_trace"]["source_channel"], "public_web")

    def test_sri_lanka_only_context_is_excluded(self):
        rows = [
            lead_tools.SearchResult(
                title="Sri Lanka Dynamics 365 support role",
                url="https://example.lk/jobs/d365",
                snippet="Sri Lanka company hiring for Dynamics 365 support.",
                source="unit",
            )
        ]
        self.assertEqual(lead_tools.extract_d365_leads(rows), [])

    def test_missing_evidence_url_is_rejected(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="UK Dynamics 365 support analyst",
                url="",
                snippet="UK employer hiring for Dynamics 365 support.",
                source="unit",
            )
        )
        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["lead"]["rejection_reason"], "missing_evidence_url")

    def test_missing_d365_evidence_is_rejected(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="UK finance systems analyst",
                url="https://www.jobs.nhs.uk/candidate/jobadvert/finance-systems",
                snippet="UK employer hiring a finance systems analyst.",
                source="unit",
            )
        )
        self.assertFalse(decision["accepted"])
        self.assertEqual(
            decision["lead"]["rejection_reason"],
            "missing_explicit_dynamics_365_or_business_app_evidence",
        )

    def test_tender_procurement_results_are_rejected(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Dynamics 365 support contract notice",
                url="https://www.find-tender.service.gov.uk/Notice/123",
                snippet="UK public procurement tender for Dynamics 365 support services.",
                source="unit",
            )
        )
        self.assertFalse(decision["accepted"])
        self.assertEqual(
            decision["lead"]["rejection_reason"],
            "tender_or_procurement_out_of_scope",
        )

    def test_private_linkedin_source_is_hard_rejected(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="UK Dynamics 365 support analyst",
                url="https://www.linkedin.com/jobs/view/123",
                snippet="UK employer hiring for Dynamics 365 support.",
                source="unit",
            )
        )
        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["lead"]["signal_tier"], "D")
        self.assertEqual(decision["lead"]["hard_rejection_reason"], "private_or_linkedin_source_excluded")

    def test_fake_example_url_is_hard_rejected(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="UK Dynamics 365 support analyst",
                url="https://example.com/jobs/d365-support",
                snippet="UK employer hiring for Dynamics 365 support.",
                source="unit",
            )
        )
        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["lead"]["hard_rejection_reason"], "fake_or_example_url")

    def test_default_query_plan_excludes_procurement_portals(self):
        queries = " ".join(lead_tools.build_queries()).lower()
        self.assertNotIn("find-tender.service.gov.uk", queries)
        self.assertNotIn("contracts.service.gov.uk", queries)
        self.assertNotIn("etenders.gov.ie", queries)
        self.assertNotIn("tender", queries)
        self.assertIn("commercial", json.dumps(lead_tools.SIGNAL_CLASSES))

    def test_vendor_pages_without_named_target_customer_are_ai_review_candidates(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Dynamics 365 support services from a Microsoft partner",
                url="https://partner-services.co.uk/services/dynamics-365-support",
                snippet="We provide Dynamics 365 support services for UK organisations. Book a demo.",
                source="unit",
            )
        )
        self.assertTrue(decision["accepted"])
        self.assertIsNone(decision["lead"]["rejection_reason"])
        self.assertTrue(decision["lead"]["needs_ai_review"])
        self.assertIn(
            "vendor_or_service_provider_page_without_defensible_target_customer",
            decision["lead"]["deterministic_flags"],
        )

    def test_partner_case_study_with_named_customer_is_not_vendor_rejected(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Contoso Retail Dynamics 365 customer story",
                url="https://partner-services.co.uk/case-studies/contoso-retail-dynamics-365",
                snippet="Case study customer: Contoso Retail in the UK implemented Dynamics 365 Customer Service.",
                source="unit",
                signal_class="installed_base_discovery",
            )
        )
        self.assertIn(decision["lead"]["signal_tier"], {"B", "C"})
        self.assertIsNone(decision["lead"]["rejection_reason"])

    def test_direct_employer_hiring_candidate_can_be_tier_a_or_b(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="CRM Manager Dynamics 365 - Example Manufacturing Careers",
                url="https://careers.example-manufacturing.co.uk/jobs/crm-manager-dynamics-365",
                snippet="UK careers page. We are hiring a CRM Manager for Dynamics 365 Customer Engagement support.",
                source="unit",
                signal_class="hiring_pain",
            )
        )
        self.assertTrue(decision["accepted"])
        self.assertIn(decision["lead"]["signal_tier"], {"A", "B"})

    def test_recruitment_job_board_without_clear_employer_is_ai_review_candidate(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Dynamics 365 Support Analyst - job board listing",
                url="https://jobs-board.co.uk/d365-support-analyst",
                snippet="Recruitment job board listing for a UK Dynamics 365 Support Analyst.",
                source="unit",
                signal_class="hiring_pain",
                source_query='"D365 Support Analyst" "United Kingdom" careers',
            )
        )
        self.assertTrue(decision["accepted"])
        self.assertIsNone(decision["lead"]["rejection_reason"])
        self.assertIn(
            "recruitment_agency_post_without_defensible_hiring_company",
            decision["lead"]["deterministic_flags"],
        )
        self.assertTrue(decision["lead"]["needs_ai_review"])

    def test_uk_ie_missing_from_snippet_becomes_review_flag_when_query_has_market(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Dynamics 365 Business Central rollout",
                url="https://company-systems.com/case-study/business-central",
                snippet="Business Central rollout with reporting and training outcomes.",
                source="unit",
                signal_class="implementation_migration_upgrade_rescue",
                source_query='"Business Central rollout" Ireland company',
            )
        )
        self.assertTrue(decision["accepted"])
        self.assertIsNone(decision["lead"]["rejection_reason"])
        self.assertIn("uk_ireland_not_evidenced_in_snippet", decision["lead"]["deterministic_flags"])

    def test_june3_style_promising_thin_candidates_stay_reviewable(self):
        rows = [
            lead_tools.SearchResult(
                title="Mental Health Commission Ireland portal",
                url="https://www.codec.ie/client-success-stories/mental-health-commission-irl",
                snippet="Power Pages portal replacing legacy process.",
                source="unit",
                signal_class="implementation_migration_upgrade_rescue",
                source_query='"Mental Health Commission Ireland" "Dynamics 365" "Power Pages"',
            ),
            lead_tools.SearchResult(
                title="Net Zero Group Ireland case study",
                url="https://bpf.ie/case-studies/",
                snippet="Business Central and 4PS rollout with reporting and training.",
                source="unit",
                signal_class="implementation_migration_upgrade_rescue",
                source_query='"Net Zero Group Ireland" "Dynamics 365 Business Central" 4PS',
            ),
        ]
        extraction = lead_tools.extract_d365_leads(rows, max_results=5, include_rejected=True)
        names = {candidate["company_name"] for candidate in extraction["review_candidates"]}
        self.assertIn("Mental Health Commission Ireland", names)
        self.assertIn("Net Zero Group", names)
        self.assertEqual(extraction["tier_counts"]["D"], 0)

    def test_installed_base_only_candidate_becomes_tier_c(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Example Foods uses Dynamics 365",
                url="https://www.examplefoods.co.uk/news/dynamics-365",
                snippet="UK company Example Foods uses Dynamics 365 Finance across its operations.",
                source="unit",
                signal_class="installed_base_discovery",
            )
        )
        self.assertTrue(decision["accepted"])
        self.assertEqual(decision["lead"]["signal_tier"], "C")

    def test_tier_b_and_tier_c_candidates_remain_visible(self):
        rows = [
            lead_tools.SearchResult(
                title="Dynamics 365 support role Ireland",
                url="https://jobs.example.ie/business-systems-manager",
                snippet="Ireland role with Dynamics 365 support duties. Verify actual direct employer.",
                source="unit",
                signal_class="hiring_pain",
            ),
            lead_tools.SearchResult(
                title="Example Logistics uses Dynamics 365",
                url="https://www.examplelogistics.co.uk/dynamics-365",
                snippet="UK company uses Dynamics 365 Field Service.",
                source="unit",
                signal_class="installed_base_discovery",
            ),
        ]
        extraction = lead_tools.extract_d365_leads(rows, max_results=5, include_rejected=True)
        tiers = {lead["signal_tier"] for lead in extraction["surfaced_leads"]}
        self.assertIn("B", tiers)
        self.assertIn("C", tiers)
        self.assertIn("review_candidates", extraction)
        self.assertIn("hard_rejected_leads", extraction)

    def test_tier_a_requires_evidence_url(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="UK careers Dynamics 365 support analyst",
                url="",
                snippet="UK careers page hiring Dynamics 365 support analyst.",
                source="unit",
                signal_class="hiring_pain",
            )
        )
        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["lead"]["signal_tier"], "D")

    def test_tier_a_requires_explicit_d365_or_business_app_evidence(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="UK careers CRM support analyst",
                url="https://careers.example.co.uk/jobs/crm-support",
                snippet="UK careers page hiring generic CRM support analyst.",
                source="unit",
                signal_class="hiring_pain",
            )
        )
        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["lead"]["signal_tier"], "D")

    def test_tier_d_requires_rejection_reason(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Generic IT support UK",
                url="https://www.example.co.uk/it-support",
                snippet="Generic IT support for UK offices.",
                source="unit",
            )
        )
        self.assertEqual(decision["lead"]["signal_tier"], "D")
        self.assertTrue(decision["lead"]["rejection_reason"])
        self.assertIn("audit_trace", decision["lead"])
        self.assertIn("final_decision", decision["lead"])
        self.assertFalse(decision["lead"]["final_decision"]["accepted"])

    def test_audit_metadata_captures_model_and_provider_without_secrets(self):
        old_secret = os.environ.get("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = "unit-secret-value"
        try:
            metadata = lead_tools.audit_metadata(
                search_provider="google_grounding",
                live_search_run=False,
                live_request_count=0,
                run_started_at="2026-05-17T00:00:00+00:00",
                run_finished_at="2026-05-17T00:00:01+00:00",
            )
        finally:
            if old_secret is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = old_secret
        self.assertEqual(metadata["audit_schema_version"], lead_tools.AUDIT_SCHEMA_VERSION)
        self.assertEqual(metadata["classifier_version"], lead_tools.CLASSIFIER_VERSION)
        self.assertTrue(metadata["effective_model_name"])
        self.assertIn(metadata["model_source"], {"env:D365_GOOGLE_MODEL", "default", "unknown"})
        self.assertIn(metadata["provider_client_mode"], {"ADC", "API_KEY", "unknown"})
        self.assertNotIn("unit-secret-value", json.dumps(metadata))

    def test_replay_adds_audit_without_live_search_and_preserves_counts(self):
        original_search = lead_tools.ADKGoogleGroundingProvider.search_web

        def fail_if_called(self, query, limit=5):
            raise AssertionError("Replay must not call live search")

        lead_tools.ADKGoogleGroundingProvider.search_web = fail_if_called
        try:
            replay = lead_tools.replay_uk_ie_d365_audit(str(self.evidence_run_path))
        finally:
            lead_tools.ADKGoogleGroundingProvider.search_web = original_search
        self.assertFalse(replay["audit_metadata"]["live_search_run"])
        self.assertEqual(replay["audit_metadata"]["live_request_count"], 0)
        self.assertEqual(replay["tier_counts"], {"A": 0, "B": 4, "C": 1, "D": 42})
        self.assertTrue(replay["replay_counts_match_expected"])
        self.assertEqual(len(replay["tier_b_provisional_leads"]), 4)
        self.assertEqual(len(replay["tier_c_watchlist_leads"]), 1)

    def test_every_replay_candidate_has_audit_trace_and_final_decision(self):
        replay = lead_tools.replay_uk_ie_d365_audit(str(self.evidence_run_path))
        candidates = replay["leads"] + replay["rejected_leads"]
        self.assertTrue(candidates)
        for candidate in candidates:
            self.assertIn("audit_trace", candidate)
            self.assertIn("final_decision", candidate)
            if candidate["signal_tier"] == "D":
                self.assertTrue(candidate["final_decision"]["rejection_reason"])
            rule_results = candidate["audit_trace"]["rule_results"]
            self.assertTrue(rule_results)
            for rule in rule_results:
                self.assertIn("rule_id", rule)
                self.assertIn("passed", rule)
                self.assertIn(rule["severity"], {"blocking", "scoring", "informational"})
                self.assertIn("explanation", rule)

    def test_provider_discovery_does_not_leak_secret_values(self):
        old_value = os.environ.get("TAVILY_API_KEY")
        os.environ["TAVILY_API_KEY"] = "unit-secret-value"
        try:
            status = lead_tools.discover_d365_search_providers()
        finally:
            if old_value is None:
                os.environ.pop("TAVILY_API_KEY", None)
            else:
                os.environ["TAVILY_API_KEY"] = old_value
        serialized = json.dumps(status)
        self.assertNotIn("unit-secret-value", serialized)
        self.assertIn("tavily", serialized)

    def test_existing_agents_still_import(self):
        self.assertEqual(sl_root_agent.name, "sl_trigger_leads")
        self.assertEqual(hello_root_agent.name, "root_agent")

    def test_refuses_email_sending(self):
        result = lead_tools.refuse_d365_email_sending("send emails")
        self.assertFalse(result["sending_enabled"])

    def test_human_review_utility_parses_replay_without_live_calls(self):
        review = self.review_module()
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_json = Path(tmp_dir) / "shortlist.json"
            output_md = Path(tmp_dir) / "shortlist.md"
            result = review.build_human_review_shortlist(
                input_file=self.audit_replay_path,
                json_output=output_json,
                markdown_output=output_md,
            )
        self.assertTrue(result["metadata"]["no_live_calls"])
        self.assertEqual(result["input_counts"]["tier_counts"], {"A": 0, "B": 4, "C": 1, "D": 42})
        self.assertEqual(result["output_counts"]["tier_b"], 4)
        self.assertEqual(result["output_counts"]["tier_c"], 1)

    def test_human_review_includes_tier_b_and_c_candidates(self):
        review = self.review_module()
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = review.build_human_review_shortlist(
                input_file=self.audit_replay_path,
                json_output=Path(tmp_dir) / "shortlist.json",
                markdown_output=Path(tmp_dir) / "shortlist.md",
            )
        replay = json.loads(self.audit_replay_path.read_text(encoding="utf-8"))
        expected_names = {
            item["company_name"]
            for item in replay["leads"]
            if item.get("signal_tier") in {"B", "C"}
        }
        actual_names = {
            item["company_name"]
            for item in result["shortlist"]
            if item.get("current_tier") in {"B", "C"}
        }
        self.assertTrue(expected_names.issubset(actual_names))

    def test_human_review_surfaces_risky_tier_d_and_preserves_tender_rejections(self):
        review = self.review_module()
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = review.build_human_review_shortlist(
                input_file=self.audit_replay_path,
                json_output=Path(tmp_dir) / "shortlist.json",
                markdown_output=Path(tmp_dir) / "shortlist.md",
            )
        risky_reasons = {
            "vendor_or_service_provider_page_without_defensible_target_customer",
            "recruitment_agency_post_without_defensible_hiring_company",
            "uk_ireland_not_evidenced",
            "missing_explicit_dynamics_365_or_business_app_evidence",
        }
        tier_d_items = [item for item in result["shortlist"] if item["current_tier"] == "D"]
        self.assertTrue(any(item["original_rejection_reason"] in risky_reasons for item in tier_d_items))
        tender_items = [
            item for item in result["shortlist"]
            if item.get("original_rejection_reason") == "tender_or_procurement_out_of_scope"
        ]
        self.assertTrue(all(item["recommended_review_action"] == "keep_rejected" for item in tender_items))

    def test_human_review_outputs_metadata_markdown_breakdowns_and_no_secrets(self):
        review = self.review_module()
        old_secret = os.environ.get("SERPER_API_KEY")
        os.environ["SERPER_API_KEY"] = "unit-secret-value"
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_json = Path(tmp_dir) / "shortlist.json"
                output_md = Path(tmp_dir) / "shortlist.md"
                result = review.build_human_review_shortlist(
                    input_file=self.audit_replay_path,
                    json_output=output_json,
                    markdown_output=output_md,
                )
                serialized = output_json.read_text(encoding="utf-8") + output_md.read_text(encoding="utf-8")
                self.assertTrue(output_md.is_file())
        finally:
            if old_secret is None:
                os.environ.pop("SERPER_API_KEY", None)
            else:
                os.environ["SERPER_API_KEY"] = old_secret
        self.assertIn("metadata", result)
        self.assertIn("rejection_breakdown", result)
        self.assertIn("tier_breakdown", result)
        self.assertEqual(result["metadata"]["review_schema_version"], review.REVIEW_SCHEMA_VERSION)
        self.assertNotIn("unit-secret-value", serialized)

    def test_classification_reviewer_agent_wrapper_imports_without_tools(self):
        self.assertEqual(classification_reviewer_agent.name, "d365_classification_reviewer_agent")
        self.assertIs(classification_reviewer_agent, d365_classification_reviewer_agent)
        self.assertEqual(list(classification_reviewer_agent.tools), [])
        self.assertIn("candidate evidence provided in the input payload", classification_reviewer_agent.instruction)
        self.assertIn("proposes future deterministic rule changes only", classification_reviewer_agent.instruction)

    def test_classification_reviewer_is_opt_in_and_toolless_sub_agent(self):
        reviewer_names = [agent.name for agent in root_agent.sub_agents]
        self.assertIn("d365_classification_reviewer_agent", reviewer_names)
        self.assertNotIn(classification_reviewer_agent, list(root_agent.tools))
        self.assertEqual(list(classification_reviewer_agent.tools), [])
        self.assertIn("Do not automatically invoke it", root_agent.instruction)

    def test_opportunity_vetter_agent_is_separate_toolless_sub_agent(self):
        sub_agent_names = [agent.name for agent in root_agent.sub_agents]
        self.assertIn("d365_opportunity_vetter_agent", sub_agent_names)
        self.assertEqual(opportunity_vetter_agent.name, "d365_opportunity_vetter_agent")
        self.assertIs(opportunity_vetter_agent, d365_opportunity_vetter_agent)
        self.assertEqual(list(opportunity_vetter_agent.tools), [])
        self.assertIn("production AI vetter", opportunity_vetter_agent.instruction)
        self.assertIn("The deterministic layer is only a guardrail layer", opportunity_vetter_agent.instruction)

    def test_classification_review_tools_build_dry_run_package(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            package = classification_review_tools.build_review_package(
                evidence_file=self.audit_replay_path,
                output_dir=Path(tmp_dir),
                command_log=["unit dry run"],
            )
        output = package["review_output"]
        self.assertTrue(output["metadata"]["dry_run_mode_executed"])
        self.assertFalse(output["metadata"]["live_llm_mode_executed"])
        self.assertEqual(output["metadata"]["live_request_count"], 0)
        self.assertEqual(output["counts"]["candidates_loaded"], 47)
        self.assertEqual(output["counts"]["candidates_prepared_for_review"], 47)
        self.assertEqual(output["counts"]["candidates_reviewed_by_llm"], 0)
        self.assertEqual(output["metadata"]["schema_validation_result"], "PASS")
        self.assertEqual(output["metadata"]["invented_candidate_facts_check_result"], "PASS")
        self.assertTrue(output["dry_run_risk_ranked_rule_patterns"])

    def test_classification_review_uses_saved_deterministic_fields(self):
        data = classification_review_tools.load_saved_evidence(self.audit_replay_path)
        first = classification_review_tools.all_candidates(data)[0]
        prepared = classification_review_tools.prepare_candidate(first, index=1)
        record = prepared["review_record"]
        self.assertEqual(
            record["review_metadata"]["source_of_truth_fields_used"],
            [field for field in classification_review_tools.SOURCE_OF_TRUTH_FIELDS if field in first],
        )
        self.assertEqual(record["deterministic_score_or_tier"], first["signal_tier"])
        self.assertEqual(record["deterministic_confidence_score"], first["confidence_score"])
        self.assertEqual(record["deterministic_urgency_score"], first["urgency_score"])
        self.assertEqual(record["deterministic_audit_trace"], first["audit_trace"])
        self.assertEqual(prepared["reconstruction_records"], [])

    def test_classification_review_records_reconstruction_for_missing_fields_only(self):
        candidate = {
            "company_name": "Saved Candidate",
            "evidence_urls": ["https://example.co.uk/d365"],
            "evidence_snippets": ["UK Dynamics 365 evidence"],
            "signal_tier": "B",
        }
        prepared = classification_review_tools.prepare_candidate(candidate, index=3)
        fields = {item["field"] for item in prepared["reconstruction_records"]}
        self.assertIn("final_decision", fields)
        self.assertIn("audit_trace", fields)
        self.assertNotIn("signal_tier", fields)

    def test_classification_review_schema_and_no_invented_facts(self):
        data = classification_review_tools.load_saved_evidence(self.audit_replay_path)
        records = [
            classification_review_tools.prepare_candidate(candidate, index=index)["review_record"]
            for index, candidate in enumerate(classification_review_tools.all_candidates(data), start=1)
        ]
        validation = classification_review_tools.validate_review_records(records)
        invented = classification_review_tools.invented_candidate_facts_check(records)
        self.assertTrue(validation["valid"])
        self.assertTrue(invented["passed"])
        self.assertFalse(any(record["invented_candidate_facts_detected"] for record in records))
        self.assertTrue(all(record["llm_review_decision"] == "dry_run_unreviewed" for record in records))
        self.assertTrue(all(record["live_llm_used"] is False for record in records))

    def test_classification_review_runner_default_is_dry_run_and_live_mode_refuses(self):
        runner_path = Path(__file__).resolve().parents[2] / "tools" / "run_uk_ie_d365_llm_classification_review.py"
        spec = importlib.util.spec_from_file_location("run_uk_ie_d365_llm_classification_review", runner_path)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as tmp_dir:
            exit_code = runner.main([
                "--evidence-file",
                str(self.audit_replay_path),
                "--output-dir",
                tmp_dir,
            ])
            output_json = Path(tmp_dir) / "UK_IE_D365_LLM_CLASSIFICATION_REVIEW.json"
            self.assertEqual(exit_code, 0)
            self.assertTrue(output_json.is_file())
            output = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(output["metadata"]["live_request_count"], 0)
            self.assertFalse(output["metadata"]["gcloud_called"])
            self.assertFalse(output["metadata"]["agents_cli_deploy_called"])

    def test_live_review_package_uses_injected_reviewer_and_enforces_cap(self):
        def fake_reviewer(record, request_index):
            return (
                json.dumps(
                    {
                        "llm_review_decision": "provisional",
                        "llm_confidence": 0.73,
                        "discrepancy_type": "false_negative_risk"
                        if record["deterministic_decision"] == "reject"
                        else "tier_mismatch",
                        "evidence_used": record["evidence_used"],
                        "missing_evidence": [],
                        "deterministic_rule_likely_at_fault": "unit_test_rule",
                        "recommended_rule_change": "Consider provisional review in matching evidence patterns.",
                        "should_promote_to_human_review": True,
                        "should_remain_rejected": False,
                        "notes": ["Unit injected review only."],
                        "proposal_impact": "needs_more_samples",
                    }
                ),
                {"prompt_token_count": 1, "candidates_token_count": 2, "total_token_count": 3},
                "unit-model",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            package = classification_review_tools.build_live_review_package(
                evidence_file=self.audit_replay_path,
                output_dir=Path(tmp_dir),
                max_candidates=3,
                command_log=["unit live review"],
                reviewer_call=fake_reviewer,
            )
            output = package["review_output"]
            phase2_json = Path(tmp_dir) / "UK_IE_D365_LLM_CLASSIFICATION_REVIEW_PHASE2.json"
            proposal_json = Path(tmp_dir) / "UK_IE_D365_LLM_CLASSIFICATION_RULE_PROPOSAL_V1.json"
            self.assertTrue(phase2_json.is_file())
            self.assertTrue(proposal_json.is_file())
        self.assertTrue(output["metadata"]["live_llm_mode_executed"])
        self.assertEqual(output["counts"]["candidates_reviewed_by_llm"], 3)
        self.assertEqual(output["counts"]["live_request_count"], 3)
        self.assertEqual(output["counts"]["token_usage"]["total_token_count"], 9)
        self.assertTrue(output["schema_validation"]["valid"])
        self.assertEqual(output["metadata"]["invented_candidate_facts_check_result"], "PASS")

    def test_select_review_candidates_rejects_invalid_cap(self):
        with self.assertRaises(ValueError):
            classification_review_tools.select_review_candidates([], 0)

    def test_ai_vetting_uses_injected_reviewer_and_followup(self):
        candidate = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Dynamics 365 support services from a Microsoft partner",
                url="https://partner-services.co.uk/services/dynamics-365-support",
                snippet="We provide Dynamics 365 support services for UK organisations. Book a demo.",
                source="unit",
            )
        )["lead"]
        evidence = {"review_candidates": [candidate], "hard_rejected_leads": []}

        def fake_vetter(record, stage, request_index):
            response = {
                "lead_status": "source_cleanup_needed" if stage == "initial" else "ready_to_contact",
                "signal_strength": "emerging" if stage == "initial" else "strong",
                "signal_type": record.get("signal_type"),
                "evidence_used": record.get("evidence_snippets") + [item.get("snippet") for item in record.get("follow_up_evidence", []) if item.get("snippet")],
                "evidence_gaps": ["resolve target customer"] if stage == "initial" else [],
                "opportunity_signal": "Public D365 support signal with follow-up evidence.",
                "why_this_matters_to_1bt": "The account may need D365 support capacity.",
                "commercial_opening": "Open with D365 support optimisation.",
                "value_of_signal": "Useful once the target customer is clear.",
                "intelligence_reading": "AI-reviewed evidence only.",
                "board_relevance": "Operational support capacity.",
                "contact_target_roles": ["Head of IT"],
                "do_not_claim_notes": ["Do not claim budget."],
                "remaining_uncertainty": [],
                "final_rejection_reason": "",
                "needs_follow_up": stage == "initial",
            }
            return json.dumps(response), {"total_token_count": 1}, "unit-vetter"

        def fake_followup(query, candidate_record, review_record):
            return [
                {
                    "title": "Northstar Components Dynamics 365 case study",
                    "url": "https://customer.co.uk/case-study/dynamics-365",
                    "snippet": "Customer: Northstar Components. UK customer case study confirms Dynamics 365 support and implementation.",
                    "source": "unit",
                }
            ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            evidence_path = Path(tmp_dir) / "evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            package = opportunity_vetting_tools.build_vetting_package(
                evidence_file=evidence_path,
                output_dir=Path(tmp_dir),
                max_candidates=5,
                reviewer_call=fake_vetter,
                followup_search_call=fake_followup,
            )
            output = package["vetting_output"]
            self.assertTrue(Path(package["artifacts"]["json"]).is_file())
            self.assertTrue(Path(package["artifacts"]["secret_scan"]).is_file())
        self.assertEqual(output["counts"]["candidates_loaded_for_vetting"], 1)
        self.assertEqual(output["counts"]["follow_up_candidate_count"], 1)
        self.assertEqual(output["records"][0]["final_review"]["lead_status"], "ready_to_contact")
        self.assertEqual(output["records"][0]["final_review"]["signal_strength"], "strong")
        self.assertEqual(len(output["useful_leads"]), 1)
        self.assertEqual(output["reject_review_summary"]["rejected_count"], 0)

    def test_ai_vetting_package_honors_custom_basename(self):
        candidate = {
            "company_name": "Northstar Components",
            "signal_type": "business_central_rollout",
            "evidence_urls": ["https://northstar-components.co.uk/news/dynamics-365-business-central"],
            "evidence_snippets": ["Northstar selected Dynamics 365 Business Central."],
        }
        evidence = {"review_candidates": [candidate], "hard_rejected_leads": []}

        def fake_vetter(record, stage, request_index):
            return json.dumps(
                {
                    "lead_status": "ready_to_contact",
                    "signal_strength": "strong",
                    "signal_type": record.get("signal_type"),
                    "evidence_used": record.get("evidence_urls") + record.get("evidence_snippets"),
                    "evidence_gaps": [],
                    "opportunity_signal": "Public Dynamics 365 Business Central rollout.",
                    "why_this_matters_to_1bt": "Named account with public Microsoft business-app evidence.",
                    "commercial_opening": "Open with post-rollout support.",
                    "value_of_signal": "Direct D365 evidence.",
                    "intelligence_reading": "AI-reviewed supplied evidence only.",
                    "board_relevance": "Finance operations platform.",
                    "contact_target_roles": ["Head of IT"],
                    "do_not_claim_notes": ["Do not claim budget."],
                    "remaining_uncertainty": [],
                    "final_rejection_reason": "",
                    "needs_follow_up": False,
                }
            ), {"total_token_count": 1}, "unit-vetter"

        with tempfile.TemporaryDirectory() as tmp_dir:
            evidence_path = Path(tmp_dir) / "evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            package = opportunity_vetting_tools.build_vetting_package(
                evidence_file=evidence_path,
                output_dir=Path(tmp_dir),
                output_basename="UNIT_AI_VETTING",
                reviewer_call=fake_vetter,
            )
            self.assertTrue((Path(tmp_dir) / "UNIT_AI_VETTING.json").is_file())
            self.assertTrue((Path(tmp_dir) / "UNIT_AI_VETTING_SECRET_SCAN.json").is_file())
        self.assertEqual(Path(package["artifacts"]["json"]).name, "UNIT_AI_VETTING.json")

    def test_ai_vetter_provider_label_uses_agent_platform_branding(self):
        def fake_factory(model_override=None):
            return object(), {
                "model": "unit-model",
                "provider_path": opportunity_vetting_tools.GEMINI_AGENT_PLATFORM_PROVIDER_PATH,
                "project": "business-intel-123",
                "location": "global",
                "auth_mode": "ADC",
            }

        candidate = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="UK manufacturer uses Dynamics 365 Business Central",
                url="https://customer.co.uk/d365-business-central",
                snippet="UK manufacturer uses Dynamics 365 Business Central.",
                source="unit",
            )
        )["lead"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            evidence_path = Path(tmp_dir) / "evidence.json"
            evidence_path.write_text(json.dumps({"review_candidates": [candidate]}), encoding="utf-8")
            package = opportunity_vetting_tools.build_vetting_package(
                evidence_file=evidence_path,
                output_dir=Path(tmp_dir),
                client_factory=fake_factory,
            )
        self.assertEqual(
            package["vetting_output"]["metadata"]["provider_path"],
            "google-genai Gemini Enterprise Agent Platform / Vertex AI API via ADC",
        )

    def test_ai_vetter_prompt_contains_strict_evidence_contract(self):
        prompt = opportunity_vetting_tools.build_vetting_prompt(
            {
                "company_name": "Northstar Components",
                "evidence_urls": ["https://northstar-components.co.uk/d365"],
                "evidence_snippets": ["Northstar uses Dynamics 365 Business Central."],
            }
        )
        payload = json.loads(prompt)
        rules = " ".join(payload["hard_rules"])
        self.assertIn("Every non-reject output must cite at least one supplied public evidence URL", rules)
        self.assertIn("clean evidence URL", rules)
        self.assertIn("Google grounding redirect", rules)
        self.assertIn("blank required write-up fields", rules)

    def test_ai_vetting_downgrades_blank_non_reject_writeup_fields(self):
        source_record = {
            "candidate_id": "unit",
            "candidate_index": 1,
            "company_name": "Northstar Components",
            "evidence_urls": ["https://northstar-components.co.uk/d365"],
            "evidence_snippets": ["Northstar uses Dynamics 365 Business Central."],
        }
        raw = {
            "lead_status": "ready_to_contact",
            "signal_strength": "strong",
            "signal_type": "business_central_rollout",
            "evidence_used": ["https://northstar-components.co.uk/d365"],
            "evidence_gaps": [],
            "opportunity_signal": "Uses Dynamics 365 Business Central.",
            "why_this_matters_to_1bt": "",
            "commercial_opening": "",
            "value_of_signal": "Strong.",
            "intelligence_reading": "Evidence-led.",
            "board_relevance": "Operational.",
            "contact_target_roles": ["Head of IT"],
            "do_not_claim_notes": [],
            "remaining_uncertainty": [],
            "final_rejection_reason": "",
        }
        review = opportunity_vetting_tools.normalize_vetting_record(
            source_record,
            raw,
            {"request_index": 1},
        )
        self.assertEqual(review["lead_status"], "source_cleanup_needed")
        self.assertIn("why_this_matters_to_1bt", " ".join(review["evidence_gaps"]))
        self.assertIn("commercial_opening", " ".join(review["evidence_gaps"]))

    def test_ai_vetting_pool_includes_unflagged_non_hard_candidates(self):
        flagged = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Dynamics 365 support services from a Microsoft partner",
                url="https://partner-services.co.uk/services/dynamics-365-support",
                snippet="We provide Dynamics 365 support services for UK organisations. Book a demo.",
                source="unit",
            )
        )["lead"]
        unflagged = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Glenveagh rolls out Dynamics 365 Customer Service in Ireland",
                url="https://www.glenveagh.ie/news/dynamics-365-customer-service",
                snippet="Ireland housebuilder Glenveagh is rolling out Dynamics 365 Customer Service for case resolution and customer communications.",
                source="unit",
            )
        )["lead"]
        pool = opportunity_vetting_tools.all_reviewable_candidates(
            {"review_candidates": [flagged], "leads": [unflagged]}
        )
        names = {item["company_name"] for item in pool}
        self.assertIn(flagged["company_name"], names)
        self.assertIn(unflagged["company_name"], names)

    def test_ai_vetting_excludes_hard_rejected_candidates(self):
        hard = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Dynamics 365 tender",
                url="https://www.contracts.service.gov.uk/notice/abc",
                snippet="Public procurement contract notice for Dynamics 365 support.",
                source="unit",
            )
        )["lead"]
        with tempfile.TemporaryDirectory() as tmp_dir:
            evidence_path = Path(tmp_dir) / "evidence.json"
            evidence_path.write_text(json.dumps({"review_candidates": [hard], "hard_rejected_leads": [hard]}), encoding="utf-8")
            package = opportunity_vetting_tools.build_vetting_package(
                evidence_file=evidence_path,
                output_dir=Path(tmp_dir),
                reviewer_call=lambda record, stage, request_index: (_ for _ in ()).throw(AssertionError("hard rejects must not be vetted")),
            )
        self.assertEqual(package["vetting_output"]["counts"]["candidates_loaded_for_vetting"], 0)

    def test_ai_vetting_downgrades_invented_urls_to_source_cleanup(self):
        candidate = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="UK Dynamics 365 case study",
                url="https://customer.co.uk/dynamics-365",
                snippet="UK customer uses Dynamics 365 Customer Service.",
                source="unit",
            )
        )["lead"]

        def inventing_vetter(record, stage, request_index):
            return (
                json.dumps(
                    {
                        "lead_status": "ready_to_contact",
                        "signal_strength": "strong",
                        "signal_type": "customer_story_or_scale_signal",
                        "evidence_used": ["https://invented.example.com/fake"],
                        "evidence_gaps": [],
                        "opportunity_signal": "Uses D365.",
                        "why_this_matters_to_1bt": "Useful.",
                        "commercial_opening": "Open carefully.",
                        "value_of_signal": "Strong.",
                        "intelligence_reading": "Evidence-led.",
                        "board_relevance": "Operational.",
                        "contact_target_roles": ["Head of IT"],
                        "do_not_claim_notes": [],
                        "remaining_uncertainty": [],
                        "final_rejection_reason": "",
                    }
                ),
                {"total_token_count": 1},
                "unit-vetter",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            evidence_path = Path(tmp_dir) / "evidence.json"
            evidence_path.write_text(json.dumps({"review_candidates": [candidate]}), encoding="utf-8")
            package = opportunity_vetting_tools.build_vetting_package(
                evidence_file=evidence_path,
                output_dir=Path(tmp_dir),
                reviewer_call=inventing_vetter,
            )
        final = package["vetting_output"]["records"][0]["final_review"]
        self.assertEqual(final["lead_status"], "source_cleanup_needed")
        self.assertTrue(final["invented_candidate_facts_detected"])

    def test_fresh_curation_excludes_vendor_only_final_candidates(self):
        vendor_record = self._vetting_record(
            company_name="Dynamics Square UK",
            url="https://dynamicssquare.co.uk/services/dynamics-365-support/",
        )
        vendor_record["candidate"]["source_type"] = "vendor_service_page"
        vendor_record["candidate"]["deterministic_flags"] = ["vendor_page_without_named_customer"]
        good_record = self._vetting_record(
            company_name="Northstar Components",
            url="https://northstar-components.co.uk/news/dynamics-365-business-central",
        )
        vetting_output = {
            "metadata": {
                "provider_path": opportunity_vetting_tools.GEMINI_AGENT_PLATFORM_PROVIDER_PATH,
                "project": "business-intel-123",
                "location": "global",
            },
            "counts": {"ai_request_count": 2, "follow_up_candidate_count": 0},
            "records": [vendor_record, good_record],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            package = opportunity_vetting_tools.build_fresh_leads_outputs(
                vetting_output=vetting_output,
                raw_search={"hard_rejected_leads": []},
                output_dir=Path(tmp_dir),
                final_count=1,
            )
        self.assertEqual(package["final_output"]["leads"][0]["company_name"], "Northstar Components")
        self.assertTrue(
            any(
                item["company_name"] == "Dynamics Square UK"
                and item["reason"] == "vendor_only_without_target_customer"
                and item["retention_status"] == "needs_identity_resolution"
                for item in package["final_output"]["selection_exclusions"]
            )
        )

    def test_vetter_check_script_writes_comparison_artifacts(self):
        module = self.vetter_check_module()
        lead = self._final_pack_lead(
            company_name="Northstar Components",
            evidence_url="https://northstar-components.co.uk/news/dynamics-365-business-central",
        )
        pack = {"metadata": {"artifact_type": "unit_pack"}, "leads": [lead]}
        source_checks = {
            "records": [
                {
                    "company_name": "Northstar Components",
                    "verified_live": True,
                    "raw_artifact_hits": ["raw.json"],
                    "supplemental_live_check_required": False,
                }
            ]
        }

        def fake_reviewer(record, stage, request_index):
            response = {
                "lead_status": "ready_to_contact",
                "signal_strength": "strong",
                "signal_type": "business_central_rollout",
                "evidence_used": record["evidence_urls"] + record["evidence_snippets"],
                "evidence_gaps": [],
                "opportunity_signal": "Dynamics 365 Business Central rollout signal.",
                "why_this_matters_to_1bt": "Clear Microsoft business-app evidence.",
                "commercial_opening": "Open with post-rollout support.",
                "value_of_signal": "Strong named-account signal.",
                "intelligence_reading": "Supplied evidence only.",
                "board_relevance": "Operational finance platform stability.",
                "contact_target_roles": ["Head of IT"],
                "do_not_claim_notes": ["Do not claim budget."],
                "remaining_uncertainty": ["Current support model is not public."],
                "final_rejection_reason": "",
            }
            return json.dumps(response), {"total_token_count": 1}, "unit-vetter"

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_pack = Path(tmp_dir) / "pack.json"
            source_path = Path(tmp_dir) / "source_checks.json"
            input_pack.write_text(json.dumps(pack), encoding="utf-8")
            source_path.write_text(json.dumps(source_checks), encoding="utf-8")
            result = module.run_check(
                input_pack=input_pack,
                source_checks=source_path,
                output_dir=Path(tmp_dir),
                live_ai=False,
                reviewer_call=fake_reviewer,
                timestamp="20260613T000000Z",
            )
            output = json.loads(Path(result["json"]).read_text(encoding="utf-8"))
            secret = json.loads(Path(result["secret_scan"]).read_text(encoding="utf-8"))
            self.assertTrue(Path(result["markdown"]).is_file())

        self.assertEqual(output["summary"]["baseline_lead_count"], 1)
        self.assertEqual(output["summary"]["agent_request_failures"], 0)
        self.assertEqual(output["summary"]["material_issue_count"], 0)
        self.assertEqual(output["summary"]["readiness_conclusion"], "ready_for_future_final_curation")
        self.assertTrue(secret["passed"])
        self.assertIn(result["json"], secret["scanned_files"])

    def _final_pack_lead(
        self,
        *,
        company_name: str = "Northstar Components",
        evidence_url: str = "https://northstar-components.co.uk/news/dynamics-365-business-central",
    ):
        return {
            "company_name": company_name,
            "lead_status": "ready_to_contact",
            "signal_strength": "strong",
            "signal_type": "business_central_rollout",
            "evidence_url": evidence_url,
            "evidence_excerpt": "UK manufacturer selected Dynamics 365 Business Central for finance and operations.",
            "opportunity_signal": "Dynamics 365 Business Central rollout signal.",
            "why_this_matters_to_1bt": "Clear Microsoft business-app change creates support and optimisation needs.",
            "commercial_opening": "Open with post-rollout Business Central support and reporting help.",
            "value_of_signal": "Named UK account with public D365 evidence.",
            "intelligence_reading": "AI-reviewed public evidence.",
            "board_relevance": "Operational finance platform stability.",
            "contact_target_roles": ["Head of IT", "Finance Systems Manager"],
            "do_not_claim_notes": ["Do not claim budget or dissatisfaction."],
            "remaining_uncertainty": ["Current incumbent support partner is not public."],
        }

    def test_report_composer_prompt_contains_evidence_and_safety_contract(self):
        inventory = report_composer_tools.build_evidence_inventory(
            input_pack={"leads": [self._final_pack_lead()]},
            source_checks={},
        )
        request = report_composer_tools.build_document_request(
            requirement="Create an executive PDF for the saved leads.",
            output_basename="UNIT_REPORT",
        )
        prompt = report_composer_tools.build_blueprint_prompt(request, inventory).lower()
        for phrase in (
            "use only supplied evidence",
            "do not invent companies",
            "do not invent urls",
            "no email sending",
            "private/authenticated linkedin",
            "tender/procurement-only",
            "fake/sample/demo",
            "return json only",
        ):
            self.assertIn(phrase, prompt)

    def test_report_blueprint_parser_rejects_malformed_or_missing_fields(self):
        with self.assertRaises(report_composer_tools.SchemaValidationError):
            report_composer_tools.parse_report_blueprint("not json")
        with self.assertRaises(report_composer_tools.SchemaValidationError):
            report_composer_tools.parse_report_blueprint(json.dumps({"title": "Missing fields"}))

    def test_report_blueprint_allows_empty_missing_info_requests(self):
        request = report_composer_tools.build_document_request(
            requirement="Create a dry-run report.",
            output_basename="UNIT_REPORT",
        )
        blueprint = report_composer_tools.default_blueprint(
            request,
            {"account_count": 1, "accounts": [], "allowed_evidence_urls": []},
        )
        parsed = report_composer_tools.parse_report_blueprint(json.dumps(blueprint))
        self.assertEqual(parsed["missing_info_requests"], [])

    def test_report_spec_rejects_invented_urls_and_missing_evidence_references(self):
        inventory = report_composer_tools.build_evidence_inventory(
            input_pack={"leads": [self._final_pack_lead()]},
            source_checks={},
        )
        spec = self._composer_report_spec()
        spec["accounts"][0]["evidence_refs"] = []
        with self.assertRaises(report_composer_tools.UnsafeReportSpecError):
            report_composer_tools.validate_report_spec(spec, inventory)
        spec = self._composer_report_spec()
        spec["accounts"][0]["evidence_refs"] = ["https://invented.example.test/source"]
        with self.assertRaises(report_composer_tools.UnsafeReportSpecError):
            report_composer_tools.validate_report_spec(spec, inventory)

    def test_partial_live_report_spec_is_completed_from_blueprint_defaults(self):
        inventory = report_composer_tools.build_evidence_inventory(
            input_pack={"leads": [self._final_pack_lead()]},
            source_checks={},
        )
        request = report_composer_tools.build_document_request(
            requirement="Create a concise executive report.",
            output_basename="UNIT_REPORT",
        )
        blueprint = report_composer_tools.default_blueprint(
            request,
            report_composer_tools.inventory_summary_for_prompt(inventory),
        )
        partial = {
            "executive_snapshot": "A concise partial spec from a live model.",
            "signal_themes": ["Business Central operational support"],
            "at_a_glance": [
                {
                    "account": "Northstar Components",
                    "signal_type": "business_central_rollout",
                    "strength": "strong",
                    "pitch_lane": "Post-rollout support",
                    "evidence_refs": ["https://northstar-components.co.uk/news/dynamics-365-business-central"],
                }
            ],
            "accounts": [self._composer_report_spec()["accounts"][0]],
            "appendix": ["Evidence references supplied."],
        }
        spec = report_composer_tools.parse_report_spec_with_defaults(
            json.dumps(partial),
            request=request,
            blueprint=blueprint,
            inventory=inventory,
        )
        self.assertEqual(spec["title"], blueprint["title"])
        self.assertEqual(spec["style_preset"], blueprint["style_preset"])
        report_composer_tools.validate_report_spec(spec, inventory)

    def test_malformed_live_account_blocks_fall_back_to_inventory_accounts(self):
        inventory = report_composer_tools.build_evidence_inventory(
            input_pack={"leads": [self._final_pack_lead()]},
            source_checks={},
        )
        request = report_composer_tools.build_document_request(
            requirement="Create a concise executive report.",
            output_basename="UNIT_REPORT",
        )
        blueprint = report_composer_tools.default_blueprint(
            request,
            report_composer_tools.inventory_summary_for_prompt(inventory),
        )
        malformed = {
            "title": "Live Partial",
            "subtitle": "Malformed account block",
            "style_preset": "executive_landscape",
            "executive_snapshot": "A live model emitted unusable account rows.",
            "signal_themes": ["Business Central"],
            "at_a_glance": [],
            "accounts": [{"name": "Northstar Components"}],
            "caveats": ["Keep caveats visible."],
            "appendix": ["Evidence references supplied."],
        }
        spec = report_composer_tools.parse_report_spec_with_defaults(
            json.dumps(malformed),
            request=request,
            blueprint=blueprint,
            inventory=inventory,
        )
        self.assertEqual(spec["accounts"][0]["account"], "Northstar Components")
        self.assertTrue(spec["accounts"][0]["evidence_refs"])
        report_composer_tools.validate_report_spec(spec, inventory)

    def test_report_renderer_writes_artifacts_and_secret_scan(self):
        inventory = report_composer_tools.build_evidence_inventory(
            input_pack={"leads": [self._final_pack_lead()]},
            source_checks={},
        )
        spec = report_composer_tools.validate_report_spec(self._composer_report_spec(), inventory)
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifacts = report_composer_tools.render_report_artifacts(
                report_spec=spec,
                inventory=inventory,
                output_dir=Path(tmp_dir),
                output_basename="UNIT_REPORT",
                browse_log=[{"kind": "unit", "status": "not_live"}],
            )
            secret_text = Path(artifacts["markdown"]).read_text(encoding="utf-8")
            Path(artifacts["markdown"]).write_text(secret_text + "\nTest secret sk-unitsecret1234567890\n", encoding="utf-8")
            secret_scan = report_composer_tools.scan_report_secrets(
                [Path(artifacts["markdown"])]
            )
            html_exists = Path(artifacts["html"]).is_file()
            pdf_exists = Path(artifacts["pdf"]).is_file()
            pdf_size = Path(artifacts["pdf"]).stat().st_size
            qa_passed = json.loads(Path(artifacts["qa"]).read_text(encoding="utf-8"))["passed"]
            source_map = json.loads(Path(artifacts["source_map"]).read_text(encoding="utf-8"))
        self.assertTrue(html_exists)
        self.assertTrue(pdf_exists)
        self.assertGreater(pdf_size, 500)
        self.assertTrue(qa_passed)
        self.assertEqual(source_map["account_count"], 1)
        self.assertTrue(source_map["accounts"][0]["evidence"])
        self.assertEqual(secret_scan["findings_count"], 1)
        self.assertNotIn("unitsecret", json.dumps(secret_scan))

    def test_report_composer_project_guard_aborts_wrong_project(self):
        with patch.dict(
            os.environ,
            {"D365_GOOGLE_PROJECT": "wrong-project", "GOOGLE_CLOUD_PROJECT": "wrong-project"},
            clear=False,
        ):
            with self.assertRaises(report_composer_tools.ProjectGuardError):
                report_composer_tools.enforce_report_project("business-intel-123")

    def test_report_composer_workflow_with_stubbed_ai_and_followup(self):
        def fake_composer(prompt, stage, request_index):
            if stage == "blueprint":
                return json.dumps(
                    {
                        "title": "Unit D365 Opportunity Report",
                        "subtitle": "Evidence-led board brief",
                        "audience": "1BT board and sales leadership",
                        "board_purpose": "Prioritise named D365 opportunities.",
                        "style_preset": "executive_landscape",
                        "tone": "board-friendly and evidence-led",
                        "section_plan": [
                            "cover",
                            "executive_snapshot",
                            "at_a_glance_grid",
                            "account_details",
                            "evidence_notes",
                        ],
                        "account_detail_fields": [
                            "opportunity_signal",
                            "why_this_matters_to_1bt",
                            "commercial_opening",
                            "value_of_signal",
                            "intelligence_reading",
                            "board_relevance",
                        ],
                        "missing_info_requests": [
                            {
                                "target": "Northstar Components",
                                "reason": "Confirm current public source availability.",
                                "queries": ['"Northstar Components" "Dynamics 365"'],
                                "max_searches": 1,
                                "max_source_fetches": 1,
                            }
                        ],
                        "caveats": ["Use as public-signal hypotheses only."],
                        "do_not_claim_rules": ["Do not claim budget or dissatisfaction."],
                    }
                ), {"total_token_count": 10}, "unit"
            return json.dumps(self._composer_report_spec()), {"total_token_count": 20}, "unit"

        def fake_source_fetch(url, request):
            return {
                "kind": "source_fetch",
                "url": url,
                "final_url": url,
                "source_name": "Northstar Components public news",
                "verified_live": True,
                "fetched_at": "2026-06-14T00:00:00+00:00",
                "text_excerpt": "Northstar selected Dynamics 365 Business Central for finance and operations.",
            }

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_pack = Path(tmp_dir) / "pack.json"
            input_pack.write_text(json.dumps({"leads": [self._final_pack_lead()]}), encoding="utf-8")
            package = report_composer_tools.build_report_composer_package(
                requirement="Create a board PDF for this saved lead pack.",
                input_pack=input_pack,
                output_basename="UNIT_COMPOSER",
                output_dir=Path(tmp_dir),
                live_ai=False,
                live_browse=True,
                composer_call=fake_composer,
                source_fetch_call=fake_source_fetch,
            )
            pdf_exists = Path(package["artifacts"]["pdf"]).is_file()
            secret_scan_exists = Path(package["artifacts"]["secret_scan"]).is_file()
        self.assertTrue(pdf_exists)
        self.assertTrue(secret_scan_exists)
        self.assertEqual(package["output"]["metadata"]["account_count"], 1)
        self.assertEqual(package["output"]["metadata"]["style_preset"], "executive_landscape")
        self.assertGreaterEqual(package["output"]["metadata"]["follow_up_record_count"], 1)

    def test_report_composer_runner_imports_and_exposes_parser(self):
        module = self.report_composer_module()
        parser = module.parser()
        args = parser.parse_args(
            [
                "--requirement",
                "Create a report",
                "--input-pack",
                "Evidence\\UK_IE_D365_USEFUL_LEADS_FRESH_20260612.json",
                "--output-basename",
                "UNIT",
            ]
        )
        self.assertEqual(args.output_basename, "UNIT")

    def test_vetting_json_parser_accepts_trailing_model_text(self):
        parsed = opportunity_vetting_tools.parse_vetting_json('{"lead_status":"ready_to_contact"}\n\nExtra notes')
        self.assertEqual(parsed["lead_status"], "ready_to_contact")

    def test_followup_search_errors_are_attached_not_raised(self):
        candidate = {"company_name": "Northstar Components", "evidence_urls": []}
        review = {"lead_status": "source_cleanup_needed", "follow_up_queries": ["northstar dynamics 365"]}

        def failing_search(query, candidate_record, review_record):
            raise RuntimeError("quota exhausted")

        evidence = opportunity_vetting_tools.collect_follow_up_evidence(
            candidate,
            review,
            followup_search_call=failing_search,
        )
        self.assertEqual(evidence[0]["kind"], "search_error")
        self.assertIn("quota exhausted", evidence[0]["error"])

    def test_vetter_request_failure_marks_candidate_unresolved(self):
        record = {
            "candidate_id": "unit",
            "company_name": "Northstar Components",
            "signal_summary": "Dynamics 365 signal.",
            "evidence_urls": ["https://northstar-components.co.uk/d365"],
            "evidence_snippets": ["Dynamics 365 signal."],
        }

        def failing_reviewer(record, stage, request_index):
            raise RuntimeError("quota exhausted https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429")

        review, meta = opportunity_vetting_tools.run_vetter_request(
            record,
            stage="initial",
            request_index=1,
            client=None,
            client_info={"model": "unit"},
            reviewer_call=failing_reviewer,
        )
        self.assertEqual(review["lead_status"], "source_cleanup_needed")
        self.assertEqual(review["signal_strength"], "weak")
        self.assertEqual(meta["request_error_type"], "RuntimeError")
        self.assertFalse(review["invented_candidate_facts_detected"])
        self.assertIn("https://northstar-components.co.uk/d365", review["evidence_used"])

    def test_extract_urls_stops_at_json_escaped_newline(self):
        urls = opportunity_vetting_tools.extract_urls(
            "Evidence URL: https://www.avanade.com/en-us/insights/clients/ireland-dept-of-health-azure-dynamics-365\nEvidence Excerpt: Dynamics 365"
        )
        self.assertEqual(
            urls,
            ["https://www.avanade.com/en-us/insights/clients/ireland-dept-of-health-azure-dynamics-365"],
        )

    def test_effective_google_project_prefers_d365_override(self):
        with patch.dict(
            os.environ,
            {
                "D365_GOOGLE_PROJECT": "business-intel-123",
                "GOOGLE_CLOUD_PROJECT": "other-project",
            },
            clear=False,
        ):
            project = lead_tools.effective_google_project({"project": "adc-project"})
        self.assertEqual(project, "business-intel-123")

    def test_fresh_curation_excludes_prior_accounts_and_writes_audit(self):
        new_record = self._vetting_record(
            company_name="Northstar Components",
            url="https://northstar-components.co.uk/news/dynamics-365-business-central",
        )
        duplicate_record = self._vetting_record(
            company_name="Glenveagh",
            url="https://www.glenveagh.ie/news/dynamics-365-customer-service",
        )
        vetting_output = {
            "metadata": {
                "artifact_type": "unit",
                "model": "unit-model",
                "provider_path": "google-genai Vertex AI via ADC",
                "project": "business-intel-123",
                "location": "global",
                "finished_at": "2026-06-12T00:00:00+00:00",
            },
            "counts": {"ai_request_count": 2, "follow_up_candidate_count": 0},
            "records": [duplicate_record, new_record],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            package = opportunity_vetting_tools.build_fresh_leads_outputs(
                vetting_output=vetting_output,
                raw_search={"hard_rejected_leads": []},
                output_dir=Path(tmp_dir),
                final_count=1,
            )
            final_output = package["final_output"]
            self.assertTrue(Path(package["artifacts"]["secret_scan"]).is_file())
            self.assertTrue(Path(package["artifacts"]["deterministic_audit_json"]).is_file())
        self.assertEqual(final_output["leads"][0]["company_name"], "Northstar Components")
        self.assertTrue(final_output["metadata"]["deterministic_reject_audit_passed"])
        self.assertTrue(
            any(
                item["company_name"] == "Glenveagh"
                and item["reason"] == "prior_or_parked_account_duplicate"
                and item["retention_status"] == "duplicate_same_opportunity"
                for item in final_output["selection_exclusions"]
            )
        )

    def test_fresh_outputs_honor_custom_basenames(self):
        vetting_output = {
            "metadata": {
                "provider_path": "google-genai Vertex AI via ADC",
                "project": "business-intel-123",
                "location": "global",
            },
            "counts": {"ai_request_count": 1, "follow_up_candidate_count": 0},
            "records": [self._vetting_record()],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            package = opportunity_vetting_tools.build_fresh_leads_outputs(
                vetting_output=vetting_output,
                raw_search={"hard_rejected_leads": []},
                output_dir=Path(tmp_dir),
                final_count=1,
                output_basename="UNIT_FRESH_FINAL",
                deterministic_audit_basename="UNIT_DETERMINISTIC_AUDIT",
            )
            self.assertTrue((Path(tmp_dir) / "UNIT_FRESH_FINAL.json").is_file())
            self.assertTrue((Path(tmp_dir) / "UNIT_DETERMINISTIC_AUDIT.json").is_file())
            self.assertTrue((Path(tmp_dir) / "UNIT_FRESH_FINAL_CANDIDATE_LEDGER.json").is_file())
            self.assertTrue((Path(tmp_dir) / "UNIT_FRESH_FINAL_SOURCE_CLEANUP_QUEUE.json").is_file())
            self.assertTrue((Path(tmp_dir) / "UNIT_FRESH_FINAL_IDENTITY_RESOLUTION.json").is_file())
            self.assertTrue((Path(tmp_dir) / "UNIT_FRESH_FINAL_DUPLICATE_AUDIT.json").is_file())
            self.assertTrue((Path(tmp_dir) / "UNIT_FRESH_FINAL_SHORTAGE_REPORT.json").is_file())
        self.assertEqual(Path(package["artifacts"]["json"]).name, "UNIT_FRESH_FINAL.json")
        self.assertEqual(Path(package["artifacts"]["candidate_ledger"]).name, "UNIT_FRESH_FINAL_CANDIDATE_LEDGER.json")
        self.assertEqual(
            Path(package["artifacts"]["deterministic_audit_json"]).name,
            "UNIT_DETERMINISTIC_AUDIT.json",
        )

    def test_fresh_outputs_write_shortage_report_without_throwing(self):
        vetting_output = {
            "metadata": {
                "provider_path": "google-genai Vertex AI via ADC",
                "project": "business-intel-123",
                "location": "global",
            },
            "counts": {"ai_request_count": 1, "follow_up_candidate_count": 0},
            "records": [self._vetting_record()],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            package = opportunity_vetting_tools.build_fresh_leads_outputs(
                vetting_output=vetting_output,
                raw_search={"hard_rejected_leads": []},
                output_dir=Path(tmp_dir),
                final_count=2,
                output_basename="UNIT_SHORTAGE",
            )
            shortage = json.loads(Path(package["artifacts"]["shortage_report_json"]).read_text(encoding="utf-8"))
        self.assertEqual(package["final_output"]["metadata"]["completion_status"], "insufficient_quality_new_leads")
        self.assertEqual(shortage["shortage_count"], 1)

    def test_followup_final_url_is_valid_selection_evidence(self):
        record = self._vetting_record(
            company_name="Northstar Components",
            url="https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc",
        )
        final_url = "https://northstar-components.co.uk/news/dynamics-365-business-central"
        record["candidate"]["evidence_urls"] = ["https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"]
        record["final_review"]["evidence_used"] = [final_url, "UK manufacturer selected Dynamics 365 Business Central."]
        record["follow_up_evidence"] = [
            {
                "kind": "source_fetch",
                "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc",
                "final_url": final_url,
                "source_name": "Northstar Components",
                "verified_live": True,
                "fetched_at": "2026-06-24T00:00:00+00:00",
                "text_excerpt": "UK manufacturer selected Dynamics 365 Business Central.",
            }
        ]
        reason = opportunity_vetting_tools.exclusion_reason_for_review(
            record["final_review"],
            record["candidate"],
            "Northstar Components",
            duplicate_blocklist=set(),
            follow_up=record["follow_up_evidence"],
        )
        self.assertIsNone(reason)

    def test_fresh_curation_excludes_generic_job_board_names(self):
        generic_record = self._vetting_record(
            company_name="Dynamics 365 Support Analyst jobs",
            url="https://jobs-board.co.uk/dynamics-365-support-analyst",
        )
        good_record = self._vetting_record(
            company_name="Northstar Components",
            url="https://northstar-components.co.uk/news/dynamics-365-business-central",
        )
        vetting_output = {
            "metadata": {
                "provider_path": opportunity_vetting_tools.GEMINI_AGENT_PLATFORM_PROVIDER_PATH,
                "project": "business-intel-123",
                "location": "global",
            },
            "counts": {"ai_request_count": 2, "follow_up_candidate_count": 0},
            "records": [generic_record, good_record],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            package = opportunity_vetting_tools.build_fresh_leads_outputs(
                vetting_output=vetting_output,
                raw_search={"hard_rejected_leads": []},
                output_dir=Path(tmp_dir),
                final_count=1,
            )
        self.assertEqual(package["final_output"]["leads"][0]["company_name"], "Northstar Components")
        self.assertTrue(
            any(
                item["company_name"] == "Dynamics 365 Support Analyst jobs"
                and item["reason"] == "generic_or_job_board_account_name"
                and item["retention_status"] == "needs_identity_resolution"
                for item in package["final_output"]["selection_exclusions"]
            )
        )

    def test_fresh_curation_fails_on_suspicious_hard_reject(self):
        raw_search = {
            "hard_rejected_leads": [
                {
                    "company_name": "Suspicious UK D365 Account",
                    "hard_rejection_reason": "missing_explicit_dynamics_365_or_business_app_evidence",
                    "country": "United Kingdom",
                    "evidence_urls": ["https://suspicious.example.co.uk/dynamics-365"],
                    "evidence_snippets": ["United Kingdom company uses Dynamics 365 Business Central."],
                }
            ]
        }
        vetting_output = {
            "metadata": {
                "provider_path": "google-genai Vertex AI via ADC",
                "project": "business-intel-123",
                "location": "global",
            },
            "counts": {"ai_request_count": 1, "follow_up_candidate_count": 0},
            "records": [self._vetting_record()],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(RuntimeError):
                opportunity_vetting_tools.build_fresh_leads_outputs(
                    vetting_output=vetting_output,
                    raw_search=raw_search,
                    output_dir=Path(tmp_dir),
                    final_count=1,
                )
            audit = json.loads(
                (Path(tmp_dir) / "UK_IE_D365_DETERMINISTIC_REJECT_AUDIT_20260612.json").read_text(encoding="utf-8")
            )
        self.assertFalse(audit["passed"])
        self.assertEqual(audit["suspicious_hard_reject_count"], 1)

    def test_hint_channel_candidate_is_retained_for_cleanup_not_final_pdf(self):
        hint_record = self._vetting_record(
            company_name="Workspace Hint Ltd",
            url="https://workspace-hint.example/news/dynamics-365",
            source_channel="workspace_hint",
        )
        vetting_output = {
            "metadata": {
                "provider_path": opportunity_vetting_tools.GEMINI_AGENT_PLATFORM_PROVIDER_PATH,
                "project": "business-intel-123",
                "location": "global",
            },
            "counts": {"ai_request_count": 1, "follow_up_candidate_count": 0},
            "records": [hint_record],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            package = opportunity_vetting_tools.build_fresh_leads_outputs(
                vetting_output=vetting_output,
                raw_search={"hard_rejected_leads": []},
                output_dir=Path(tmp_dir),
                final_count=1,
            )
        self.assertEqual(package["final_output"]["leads"], [])
        self.assertTrue(
            any(
                item["company_name"] == "Workspace Hint Ltd"
                and item["reason"] == "hint_channel_requires_public_web_evidence"
                and item["retention_status"] == "needs_source_cleanup"
                for item in package["retention_queues"]["source_cleanup_queue"]
            )
        )

    def test_final_selection_requires_verified_live_public_evidence(self):
        record = self._vetting_record()
        record["candidate"]["verified_live"] = False
        record["final_review"]["verified_live"] = False
        reason = opportunity_vetting_tools.exclusion_reason_for_review(
            record["final_review"],
            record["candidate"],
            record["candidate"]["company_name"],
            duplicate_blocklist=set(),
            follow_up=[],
        )
        self.assertEqual(reason, "missing_verified_live_public_evidence")

    def _minimal_text_pdf(self, text: str) -> bytes:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        return (
            "%PDF-1.4\n"
            "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
            "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
            f"5 0 obj << /Length {len(stream)} >> stream\n{stream}\nendstream endobj\n"
            "trailer << /Root 1 0 R >>\n%%EOF\n"
        ).encode("latin-1")

    def _fake_provider(
        self,
        name: str,
        results: list[lead_tools.SearchResult],
        *,
        configured: bool = True,
        unavailable_reason: str | None = None,
        error: BaseException | None = None,
    ):
        class FakeProvider:
            def __init__(self):
                self.name = name
                self.configured = configured
                self.unavailable_reason = unavailable_reason

            def search_web(self, query: str, limit: int = 5):
                if error:
                    raise error
                return results[:limit]

        return FakeProvider()

    def _vetting_record(
        self,
        *,
        company_name: str = "Northstar Components",
        url: str = "https://northstar-components.co.uk/news/dynamics-365-business-central",
        source_channel: str = "public_web",
    ):
        candidate = {
            "company_name": company_name,
            "evidence_urls": [url],
            "evidence_snippets": ["UK manufacturer selected Dynamics 365 Business Central for finance and operations."],
            "source_channel": source_channel,
            "verified_live": source_channel == "public_web",
            "final_pdf_eligible": source_channel == "public_web",
        }
        final_review = {
            "company_name": company_name,
            "source_channel": source_channel,
            "verified_live": source_channel == "public_web",
            "final_pdf_eligible": source_channel == "public_web",
            "lead_status": "ready_to_contact",
            "signal_strength": "strong",
            "signal_type": "business_central_rollout",
            "evidence_used": [url, "UK manufacturer selected Dynamics 365 Business Central."],
            "evidence_gaps": [],
            "opportunity_signal": "Dynamics 365 Business Central rollout signal.",
            "why_this_matters_to_1bt": "Clear Microsoft business-app change creates support and optimisation needs.",
            "commercial_opening": "Open with post-rollout Business Central support and reporting help.",
            "value_of_signal": "Named UK account with public D365 evidence.",
            "intelligence_reading": "AI-reviewed public evidence.",
            "board_relevance": "Operational finance platform stability.",
            "contact_target_roles": ["Head of IT", "Finance Systems Manager"],
            "do_not_claim_notes": ["Do not claim budget or dissatisfaction."],
            "remaining_uncertainty": ["Current incumbent support partner is not public."],
            "final_rejection_reason": "",
            "deterministic_flags": [],
        }
        return {"candidate": candidate, "final_review": final_review, "follow_up_evidence": []}

    def _composer_report_spec(self):
        evidence_url = "https://northstar-components.co.uk/news/dynamics-365-business-central"
        return {
            "title": "Unit D365 Opportunity Report",
            "subtitle": "Evidence-led board brief",
            "style_preset": "executive_landscape",
            "executive_snapshot": "One strong public D365 opportunity signal is ready for board review.",
            "signal_themes": ["Business Central operational support"],
            "at_a_glance": [
                {
                    "account": "Northstar Components",
                    "signal_type": "business_central_rollout",
                    "strength": "strong",
                    "pitch_lane": "Post-rollout Business Central support",
                    "evidence_refs": [evidence_url],
                }
            ],
            "accounts": [
                {
                    "account": "Northstar Components",
                    "signal_strength": "strong",
                    "signal_type": "business_central_rollout",
                    "evidence_refs": [evidence_url],
                    "opportunity_signal": "Dynamics 365 Business Central rollout signal.",
                    "why_this_matters_to_1bt": "Clear Microsoft business-app change creates support and optimisation needs.",
                    "commercial_opening": "Open with post-rollout Business Central support and reporting help.",
                    "value_of_signal": "Named UK account with public D365 evidence.",
                    "intelligence_reading": "Use supplied public evidence only.",
                    "board_relevance": "Operational finance platform stability.",
                    "do_not_claim_notes": ["Do not claim budget or dissatisfaction."],
                    "remaining_uncertainty": ["Current incumbent support partner is not public."],
                }
            ],
            "caveats": ["Use as a public-signal hypothesis, not a buying-intent claim."],
            "appendix": ["Source map contains the evidence URL and excerpt."],
        }

    def test_classification_review_secret_scan_redacts_findings(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "artifact.txt"
            path.write_text("placeholder sk-unitsecret1234567890", encoding="utf-8")
            scan = classification_review_tools.scan_secret_patterns([path])
        self.assertEqual(scan["findings_count"], 1)
        self.assertTrue(scan["findings"][0]["redacted"])
        self.assertNotIn("unitsecret", json.dumps(scan))

    def test_tender_procurement_exclusion_still_untouched_after_review_tools_import(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Dynamics 365 managed services tender",
                url="https://www.contracts.service.gov.uk/notice/abc",
                snippet="Public procurement contract notice for Dynamics 365 support.",
                source="unit",
            )
        )
        self.assertEqual(decision["lead"]["signal_tier"], "D")
        self.assertEqual(decision["lead"]["rejection_reason"], "tender_or_procurement_out_of_scope")


if __name__ == "__main__":
    unittest.main()
