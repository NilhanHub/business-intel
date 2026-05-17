import unittest

from sl_trigger_leads.agent import ROOT_INSTRUCTION, root_agent
from sl_trigger_leads.agents.contact_resolver_agent import contact_resolver_agent
from sl_trigger_leads.tools.contact_resolver_tools import (
    refuse_contact_resolver_sending,
    show_contact_resolver_dry_run,
)


class ContactResolverAgentTest(unittest.TestCase):
    def test_root_agent_exposes_contact_resolver_sub_agent(self):
        sub_agent_names = [agent.name for agent in root_agent.sub_agents]
        self.assertIn("contact_resolver_agent", sub_agent_names)
        self.assertEqual(contact_resolver_agent.name, "contact_resolver_agent")

    def test_root_agent_exposes_contact_resolver_tools(self):
        tool_names = [getattr(tool, "__name__", "") for tool in root_agent.tools]
        self.assertIn("resolve_latest_contact_routes", tool_names)
        self.assertIn("resolve_contact_routes_from_text", tool_names)
        self.assertIn("find_contact_route_for_company", tool_names)
        self.assertIn("show_contact_resolver_dry_run", tool_names)
        self.assertIn("refuse_contact_resolver_sending", tool_names)

    def test_contact_resolver_agent_exposes_no_send_tool(self):
        tool_names = [getattr(tool, "__name__", "") for tool in contact_resolver_agent.tools]
        self.assertIn("resolve_contact_route_for_lead", tool_names)
        self.assertIn("resolve_contacts_for_leads", tool_names)
        self.assertIn("resolve_contact_routes_from_text", tool_names)
        self.assertNotIn("send_hello_nilhan_test_email", tool_names)
        self.assertTrue(all("send" not in name or name == "refuse_contact_resolver_sending" for name in tool_names))

    def test_root_instruction_has_required_contact_prompts(self):
        self.assertIn("Resolve contacts for the latest 3 leads", ROOT_INSTRUCTION)
        self.assertIn("get the email address for these", ROOT_INSTRUCTION)
        self.assertIn("show search trace for Vs One World", ROOT_INSTRUCTION)
        self.assertIn("Find the best contact route for Vs One World", ROOT_INSTRUCTION)
        self.assertIn("Show contact resolver dry run", ROOT_INSTRUCTION)
        self.assertIn("Contact Resolver only resolves contact routes", ROOT_INSTRUCTION)
        self.assertIn("compact_output", ROOT_INSTRUCTION)
        self.assertIn("company_name -> company", ROOT_INSTRUCTION)
        self.assertIn("resolve_contact_routes_from_text", ROOT_INSTRUCTION)

    def test_sending_question_is_refused(self):
        refusal = refuse_contact_resolver_sending("Can you send the email now?")
        self.assertFalse(refusal["sending_enabled"])
        self.assertEqual(
            refusal["refusal_reason"],
            "No. Contact Resolver only resolves contact routes. Sending to leads is still locked.",
        )

    def test_dry_run_sample_result_is_discoverable(self):
        result = show_contact_resolver_dry_run()
        self.assertEqual(result["agent"], "Contact Resolver Agent")
        self.assertFalse(result["live_web_search_enabled"])


if __name__ == "__main__":
    unittest.main()
