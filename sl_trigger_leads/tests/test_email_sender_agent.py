import unittest

from sl_trigger_leads.agent import ROOT_INSTRUCTION, root_agent
from sl_trigger_leads.agents.email_sender_agent import email_sender_agent
from sl_trigger_leads.tools.gmail_sender_tools import (
    describe_email_sender_restrictions,
    refuse_lead_outreach_email,
    send_hello_nilhan_test_email,
)


class EmailSenderAgentTest(unittest.TestCase):
    def test_root_agent_exposes_email_sender_sub_agent(self):
        sub_agent_names = [agent.name for agent in root_agent.sub_agents]
        self.assertIn("email_sender_agent", sub_agent_names)
        self.assertEqual(email_sender_agent.name, "email_sender_agent")

    def test_root_agent_exposes_email_sender_tools(self):
        tool_names = [getattr(tool, "__name__", "") for tool in root_agent.tools]
        self.assertIn("send_hello_nilhan_test_email", tool_names)
        self.assertIn("describe_email_sender_restrictions", tool_names)
        self.assertIn("refuse_lead_outreach_email", tool_names)

    def test_email_sender_agent_exposes_tools(self):
        tool_names = [getattr(tool, "__name__", "") for tool in email_sender_agent.tools]
        self.assertIn("send_hello_nilhan_test_email", tool_names)
        self.assertIn("describe_email_sender_restrictions", tool_names)

    def test_restrictions_report_lead_outreach_blocked(self):
        restrictions = describe_email_sender_restrictions()
        self.assertEqual(restrictions["allowed_recipient"], "portfolio-owner@example.test")
        self.assertFalse(restrictions["lead_outreach_enabled"])
        self.assertFalse(restrictions["bulk_send_enabled"])
        self.assertFalse(restrictions["secrets_are_returned"])

    def test_lead_outreach_is_refused(self):
        result = refuse_lead_outreach_email("Send email to a lead")
        self.assertFalse(result["sent"])
        self.assertIn("Lead outreach is not unlocked yet", result["refusal_reason"])

    def test_root_instruction_has_required_routing_phrases(self):
        self.assertIn("Show me the Hello Nilhan email dry run", ROOT_INSTRUCTION)
        self.assertIn("Send the Hello Nilhan test email", ROOT_INSTRUCTION)
        self.assertIn("Lead outreach is not unlocked yet", ROOT_INSTRUCTION)

    def test_adk_tool_defaults_to_dry_run(self):
        result = send_hello_nilhan_test_email()
        self.assertFalse(result["sent"])
        self.assertTrue(result["dry_run"])


if __name__ == "__main__":
    unittest.main()
