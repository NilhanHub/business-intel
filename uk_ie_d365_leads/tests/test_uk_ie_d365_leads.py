import json
import os
import tempfile
import unittest
import importlib.util
from pathlib import Path

from hello_cloud_agent.hello_cloud_agent.agent import root_agent as hello_root_agent
from sl_trigger_leads.agent import root_agent as sl_root_agent
from uk_ie_d365_leads.agent import app, root_agent
from uk_ie_d365_leads.agents.classification_reviewer_agent import (
    classification_reviewer_agent,
    d365_classification_reviewer_agent,
)
from uk_ie_d365_leads.tools import classification_review_tools
from uk_ie_d365_leads.tools import lead_tools


class UkIeD365LeadsTest(unittest.TestCase):
    evidence_run_path = Path(__file__).resolve().parents[2] / "Evidence" / "UK_IE_D365_COMMERCIAL_SEARCH_RUN.json"
    audit_replay_path = Path(__file__).resolve().parents[2] / "Evidence" / "UK_IE_D365_AUDIT_REPLAY.json"
    review_script_path = Path(__file__).resolve().parents[2] / "tools" / "review_uk_ie_d365_candidates.py"

    @classmethod
    def review_module(cls):
        spec = importlib.util.spec_from_file_location("review_uk_ie_d365_candidates", cls.review_script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_agent_import_and_shape(self):
        self.assertEqual(root_agent.name, "uk_ie_d365_leads")
        self.assertEqual(app.name, "uk_ie_d365_leads")
        self.assertIn("d365_search_agent", [agent.name for agent in root_agent.sub_agents])
        self.assertIn("d365_classification_reviewer_agent", [agent.name for agent in root_agent.sub_agents])
        self.assertGreaterEqual(len(root_agent.tools), 3)

    def test_provider_unavailable_does_not_generate_fake_leads(self):
        provider = lead_tools.ProviderUnavailable("missing credentials")
        self.assertFalse(provider.configured)
        self.assertEqual(provider.search_web("Dynamics 365 support UK", limit=5), [])

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
                title="UK IT support analyst",
                url="https://www.jobs.nhs.uk/candidate/jobadvert/it-support",
                snippet="UK employer hiring generic IT support.",
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

    def test_default_query_plan_excludes_procurement_portals(self):
        queries = " ".join(lead_tools.build_queries()).lower()
        self.assertNotIn("find-tender.service.gov.uk", queries)
        self.assertNotIn("contracts.service.gov.uk", queries)
        self.assertNotIn("etenders.gov.ie", queries)
        self.assertNotIn("tender", queries)
        self.assertIn("commercial", json.dumps(lead_tools.SIGNAL_CLASSES))

    def test_vendor_pages_are_tier_d_without_named_target_customer(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Dynamics 365 support services from a Microsoft partner",
                url="https://partner.example/services/dynamics-365-support",
                snippet="We provide Dynamics 365 support services for UK organisations. Book a demo.",
                source="unit",
            )
        )
        self.assertEqual(decision["lead"]["signal_tier"], "D")
        self.assertEqual(
            decision["lead"]["rejection_reason"],
            "vendor_or_service_provider_page_without_defensible_target_customer",
        )

    def test_partner_case_study_with_named_customer_is_not_vendor_rejected(self):
        decision = lead_tools.evaluate_search_result(
            lead_tools.SearchResult(
                title="Contoso Retail Dynamics 365 customer story",
                url="https://partner.example/case-studies/contoso-retail-dynamics-365",
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

        def fail_if_called(self, query, limit=5):  # noqa: ARG001
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
        def fake_reviewer(record, request_index):  # noqa: ARG001
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
