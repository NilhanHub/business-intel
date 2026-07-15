import json
import os
import unittest

from sl_trigger_leads.agent import ROOT_INSTRUCTION, root_agent
from sl_trigger_leads.tools import cloud_ops_tools as ops
from sl_trigger_leads.tools.contact_resolver_tools import (
    resolve_contact_routes_from_text,
)
from sl_trigger_leads.tools.live_contact_search_tools import (
    HunterContactEnrichmentProvider,
)

WSO2_LEAD_TEXT = """Lead 1:
company_name: WSO2
signal_summary: Enterprise software company; test Hunter/domain/contact route behavior.
signal_source_url: https://wso2.com/contact/
service_bucket: Software Development
country: Sri Lanka
"""


class CloudOpsToolsTest(unittest.TestCase):
    def test_agent_exposes_cloud_ops_tools(self):
        tool_names = [getattr(tool, "__name__", "") for tool in root_agent.tools]
        self.assertIn("diagnose_hunter_runtime", tool_names)
        self.assertIn("run_single_company_hunter_probe", tool_names)
        self.assertIn("run_contact_resolver_smoke", tool_names)
        self.assertIn("cloud_ops_readiness_report", tool_names)
        self.assertIn("diagnose_hunter_runtime", ROOT_INSTRUCTION)

    def test_diagnose_hunter_runtime_with_no_key(self):
        old_key = os.environ.pop("HUNTER_API_KEY", None)
        try:
            result = ops.diagnose_hunter_runtime()
        finally:
            if old_key is not None:
                os.environ["HUNTER_API_KEY"] = old_key
        self.assertFalse(result["hunter_env_present"])
        self.assertEqual(result["hunter_env_length"], 0)
        self.assertEqual(result["hunter_account_check_status"], "NOT_CONFIGURED")
        self.assertEqual(result["hunter_domain_search_status"], "NOT_CONFIGURED")
        self.assertNotIn("api_key=", json.dumps(result).lower())

    def test_hunter_provider_strips_env_key(self):
        old_key = os.environ.get("HUNTER_API_KEY")
        os.environ["HUNTER_API_KEY"] = "  local-test-key  \n"
        try:
            provider = HunterContactEnrichmentProvider.from_env()
        finally:
            if old_key is None:
                os.environ.pop("HUNTER_API_KEY", None)
            else:
                os.environ["HUNTER_API_KEY"] = old_key
        self.assertEqual(provider.api_key, "local-test-key")

    @unittest.skipUnless(os.environ.get("HUNTER_API_KEY"), "HUNTER_API_KEY not available for live Hunter test")
    def test_diagnose_hunter_runtime_with_real_key(self):
        result = ops.diagnose_hunter_runtime()
        self.assertTrue(result["hunter_env_present"])
        self.assertGreater(result["hunter_env_length"], 5)
        self.assertEqual(result["hunter_account_check_status"], "OK")
        self.assertEqual(result["hunter_domain_search_status"], "OK")
        self.assertGreaterEqual(result["hunter_domain_search_result_count"], 1)
        self.assertNotIn(os.environ["HUNTER_API_KEY"].strip(), json.dumps(result))

    @unittest.skipUnless(os.environ.get("HUNTER_API_KEY"), "HUNTER_API_KEY not available for live Hunter test")
    def test_wso2_hunter_direct_probe(self):
        result = ops.run_single_company_hunter_probe("wso2.com")
        self.assertEqual(result["status"], "OK")
        self.assertGreaterEqual(result["result_count"], 1)
        self.assertLessEqual(len(result["top_safe_summaries"]), 5)
        self.assertNotIn(os.environ["HUNTER_API_KEY"].strip(), json.dumps(result))

    @unittest.skipUnless(os.environ.get("HUNTER_API_KEY"), "HUNTER_API_KEY not available for live Hunter test")
    def test_resolve_contact_routes_from_text_uses_hunter_when_key_exists(self):
        result = resolve_contact_routes_from_text(WSO2_LEAD_TEXT, max_leads=1, dry_run=False)
        item = result["results"][0]
        summary = item["search_summary"]
        self.assertNotEqual(summary["hunter_status"], "HUNTER_NOT_CONFIGURED")
        self.assertTrue(summary["hunter_domain_search_attempted"])
        self.assertIn("wso2.com", summary["hunter_domains_attempted"])
        self.assertNotIn(os.environ["HUNTER_API_KEY"].strip(), json.dumps(result))

    def test_no_secret_value_appears_in_diagnostic_output_without_key(self):
        result = {
            "diagnose": ops.diagnose_hunter_runtime(),
            "probe": ops.run_single_company_hunter_probe("wso2.com"),
        }
        serialized = json.dumps(result).lower()
        self.assertNotIn("access_token", serialized)
        self.assertNotIn("refresh_token", serialized)
        self.assertNotIn("client_secret", serialized)


if __name__ == "__main__":
    unittest.main()
