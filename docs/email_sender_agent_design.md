# Email Sender Agent Design

PROMPT#09 adds a local-only, test-mode Gmail sender component to the existing
`sl_trigger_leads` ADK app. It is intentionally separate from the lead finder
and opportunity-analysis code.

## Component Boundary

- `sl_trigger_leads/tools/gmail_sender_tools.py` contains the shared safe Gmail
  sender helpers and the ADK-callable tool function.
- `sl_trigger_leads/agents/email_sender_agent.py` defines a separate ADK
  sub-agent for locked test Gmail behavior.
- `sl_trigger_leads/agent.py` registers the email sender sub-agent and exposes
  only the fixed test-mode tools at the root.
- `tools/gmail_sender_smoke.py` still works and now reuses the shared safe
  Gmail helpers.
- `tools/run_prompt09_email_agent_smoke.py` validates the ADK email sender tool
  from the command line.

## Locked Test Email

The only real email that this component can send is:

- From: `portfolio-operator@example.test`
- To: `portfolio-owner@example.test`
- Subject: `Hello Nilhan from Business Intel`
- Body: `Hello Nilhan, this is a test email from the Business_Intel ADK email sender agent.`

The ADK tool signature is:

```python
send_hello_nilhan_test_email(dry_run: bool = True, confirm_send: bool = False)
```

Default behavior is dry-run. A real send requires `dry_run=False` and
`confirm_send=True`. The CLI smoke runner also requires the exact terminal
confirmation phrase `SEND_TO_NILHAN_ADK`.

## Safety Rules

- Test mode only.
- The only allowed recipient is `portfolio-owner@example.test`.
- Arbitrary recipient input is not accepted by the ADK tool.
- Lead, company, prospect, bulk, and generated-sales-email outreach is refused.
- No cloud deployment is configured for Gmail sending.
- The Gmail send path uses local OAuth user credentials only.
- OAuth client files and token files stay outside the source tree under `BT_SECRETS_DIR`.
- Returned results and logs include only safe metadata, never token or client
  secret values.

## OAuth Files

The local sender uses these private files at runtime:

- `%LOCALAPPDATA%\1BT\Business_Intel\secrets\gmail_sender_credentials.json`
- `%LOCALAPPDATA%\1BT\Business_Intel\secrets\gmail_sender_token.json`

These files are not copied into source files, docs, logs, outputs, or evidence
ZIPs.

## ADK Web Prompts

- `Show me the Hello Nilhan email dry run.`
- `Send the Hello Nilhan test email.`
- `What email sending restrictions are currently active?`
- `Can you send an email to a lead?`
