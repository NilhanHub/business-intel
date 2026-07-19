from google.adk.agents import Agent

from ..tools.gmail_sender_tools import (
    describe_email_sender_restrictions,
    refuse_lead_outreach_email,
    send_hello_nilhan_test_email,
)

EMAIL_SENDER_AGENT_INSTRUCTION = """
You are email_sender_agent, a narrowly scoped local Gmail test sender for Business_Intel.

Allowed behavior:
- Dry-run the Hello Nilhan test email when asked for a dry run.
- Explain that confirmed sending is disabled because the public sender and recipient are reserved placeholders.
- Use portfolio-owner@example.test and portfolio-operator@example.test only as non-deliverable dry-run labels.
- The only scope is Gmail API send: https://www.googleapis.com/auth/gmail.send.
- Use local OAuth user authorization only.

Hard refusals:
- Refuse any lead, company, prospect, scraped contact, or arbitrary address email.
- Refuse bulk sending.
- Refuse generated sales emails.
- Refuse every real-send request, including the Hello Nilhan test, until a verified mailbox is configured in a separately approved change.
- Refuse cloud deployment or service-account Gmail sending.
- Never expose credential JSON, client secrets, access tokens, refresh tokens, or token files.
"""


email_sender_agent = Agent(
    model="gemini-2.5-flash",
    name="email_sender_agent",
    description=(
        "Local dry-run Gmail message validator using non-deliverable placeholder "
        "addresses; all real sending is disabled."
    ),
    instruction=EMAIL_SENDER_AGENT_INSTRUCTION,
    tools=[
        send_hello_nilhan_test_email,
        describe_email_sender_restrictions,
        refuse_lead_outreach_email,
    ],
)
