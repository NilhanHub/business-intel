import unittest

from sl_trigger_leads.agent import root_agent
from sl_trigger_leads.agents.opportunity_analyst import opportunity_analyst
from sl_trigger_leads.tools.opportunity_analysis_tools import (
    analyze_leads_for_1bt,
    analyze_opportunity_for_1bt,
    classify_opportunity_bucket,
    load_onebt_service_taxonomy,
)


def _lead(**overrides):
    base = {
        "company": "Vs One World (Pvt) Ltd",
        "country": "Sri Lanka",
        "sector": "software/IT services",
        "trigger_type": "system_integration_pressure",
        "trigger_summary": "QE Engineer - API & Integration VS ONE WORLD (Pvt) Ltd Colombo 26 Apr 2026 26 Apr",
        "evidence_url": "https://itpro.lk/job/13609/qe-engineer-api-integration-at-vs-one-world-pvt-ltd/",
        "evidence_excerpt": "QE Engineer - API & Integration VS ONE WORLD (Pvt) Ltd Colombo 26 Apr 2026 26 Apr",
        "source_name": "ITPro.lk Jobs",
        "source_type": "job_board",
        "published_or_seen_date": "26 Apr 2026",
        "fetched_at": "2026-04-28T14:04:26+00:00",
        "verified_live": True,
        "score": {"verdict": "Contact now"},
    }
    base.update(overrides)
    return base


class OpportunityAnalysisTest(unittest.TestCase):
    def test_taxonomy_loads_all_buckets(self):
        taxonomy = load_onebt_service_taxonomy()
        bucket_ids = [bucket["bucket_id"] for bucket in taxonomy["buckets"]]
        self.assertEqual(len(bucket_ids), 11)
        self.assertIn("staff_augmentation_delivery_capacity", bucket_ids)
        self.assertIn("microsoft_dynamics_365_crm_power_platform", bucket_ids)

    def test_qe_api_integration_maps_to_staff_aug_primary(self):
        result = analyze_opportunity_for_1bt(_lead())
        self.assertEqual(result["primary_bucket"], "staff_augmentation_delivery_capacity")
        self.assertIn("integrations_api_middleware", result["secondary_buckets"])
        self.assertIn("qa_test_automation", result["secondary_buckets"])
        self.assertIn("custom_software_development", result["secondary_buckets"])
        self.assertEqual(result["bucket_confidence"], "high")

    def test_ai_developer_maps_to_ai_apps(self):
        result = classify_opportunity_bucket(
            _lead(
                company="Innovay",
                trigger_type="hiring_spike",
                trigger_summary="AI Developer Innovay Jaffna 26 Apr 2026 26 Apr",
                evidence_url="https://itpro.lk/job/13601/ai-developer-at-innovay/",
                evidence_excerpt="AI Developer Innovay Jaffna 26 Apr 2026 26 Apr",
                score={"verdict": "Contact now"},
            )
        )
        self.assertEqual(result["primary_bucket"], "ai_apps_workflow_automation")

    def test_crm_claims_automation_maps_to_dynamics_bucket(self):
        result = classify_opportunity_bucket(
            _lead(
                company="Union Assurance PLC",
                trigger_type="ai_or_digital_initiative",
                trigger_summary="Claims automation and CRM customer service workflow modernization",
                evidence_url="https://www.ft.lk/business/34",
                evidence_excerpt="Claims automation and CRM customer service workflow modernization for customer operations",
                source_name="Daily FT - Business",
                source_type="news",
                score={"verdict": "Verify contact first"},
            )
        )
        self.assertEqual(result["primary_bucket"], "microsoft_dynamics_365_crm_power_platform")

    def test_data_dashboard_signal_maps_to_data_analytics(self):
        result = classify_opportunity_bucket(
            _lead(
                company="Dialog Axiata PLC",
                trigger_type="ai_or_digital_initiative",
                trigger_summary="Data analyst dashboard reporting and analytics workflow",
                evidence_url="https://www.ft.lk/it-telecom-tech/50",
                evidence_excerpt="Data analyst dashboard reporting and analytics workflow for operational insights",
                source_name="Daily FT - IT / Telecom / Tech",
                source_type="news",
                score={"verdict": "Verify contact first"},
            )
        )
        self.assertEqual(result["primary_bucket"], "data_analytics_ai")

    def test_generic_weak_pr_maps_to_low_fit_watch(self):
        result = analyze_opportunity_for_1bt(
            _lead(
                company="Commercial Bank of Ceylon PLC",
                trigger_type="generic_pr_fluff",
                trigger_summary="Commercial Bank celebrates anniversary with awards ceremony",
                evidence_url="https://www.ft.lk/business/34",
                evidence_excerpt="Commercial Bank celebrates anniversary with awards ceremony and community recognition",
                source_name="Daily FT - Business",
                source_type="news",
                score={"verdict": "Watch list"},
            )
        )
        self.assertEqual(result["primary_bucket"], "low_fit_or_watch")
        self.assertIn(result["verdict"], {"Watch list", "Park"})

    def test_missing_evidence_url_is_rejected(self):
        lead = _lead()
        lead.pop("evidence_url")
        with self.assertRaises(ValueError):
            analyze_opportunity_for_1bt(lead)

    def test_example_test_url_is_rejected(self):
        with self.assertRaises(ValueError):
            analyze_opportunity_for_1bt(_lead(evidence_url="https://example.test/not-real"))

    def test_analysis_includes_do_not_claim_guardrails(self):
        result = analyze_opportunity_for_1bt(_lead())
        self.assertIn("do_not_claim", result)
        joined = " ".join(result["do_not_claim"]).lower()
        self.assertIn("budget", joined)
        self.assertIn("dynamics 365", joined)
        self.assertIn("ai", joined)

    def test_multiple_leads_analysis_shape(self):
        result = analyze_leads_for_1bt([_lead()], max_results=3)
        self.assertEqual(result["analysis_count"], 1)
        self.assertEqual(result["analyses"][0]["primary_bucket"], "staff_augmentation_delivery_capacity")

    def test_root_agent_exposes_opportunity_analyst(self):
        sub_agent_names = [agent.name for agent in root_agent.sub_agents]
        self.assertIn("opportunity_analyst", sub_agent_names)
        self.assertEqual(opportunity_analyst.name, "opportunity_analyst")


if __name__ == "__main__":
    unittest.main()
