# PROMPT#09 Email Sender Agent Report

## Result

Status: PASS (dry-run and refusal contract)

PROMPT#09 created a safe, local-only ADK Gmail sender sub-agent and tool inside
the existing `sl_trigger_leads` app. The implementation keeps Gmail sending
separate from lead finding and opportunity analysis.

## Files Created Or Updated

- `sl_trigger_leads/tools/gmail_sender_tools.py`
- `sl_trigger_leads/agents/email_sender_agent.py`
- `sl_trigger_leads/agents/__init__.py`
- `sl_trigger_leads/agent.py`
- `sl_trigger_leads/tests/test_gmail_sender_tools.py`
- `sl_trigger_leads/tests/test_email_sender_agent.py`
- `tools/gmail_sender_smoke.py`
- `tools/run_prompt09_email_agent_smoke.py`
- `docs/email_sender_agent_design.md`
- `docs/PROMPT#09_email_sender_agent_report.md`
- `logs/PROMPT#09_email_agent.log`
- `outputs/PROMPT#09_email_agent_dry_run.json`
- `outputs/PROMPT#09_email_agent_send_result.json`

## Validation

Command:

```powershell
python -m unittest discover -s sl_trigger_leads/tests -v
```

Result: PASS, 36 tests passed.

Command:

```powershell
python tools\run_prompt09_email_agent_smoke.py --dry-run
```

Result: PASS. No email was sent. Dry-run output was written to
`outputs/PROMPT#09_email_agent_dry_run.json`.

Command:

```powershell
"SEND_TO_NILHAN_ADK" | python tools\run_prompt09_email_agent_smoke.py --send
```

Result: REFUSED AS DESIGNED. The public mailbox values are reserved `example.test`
placeholders, so the current component cannot make a Gmail API send.

Historical private-workspace delivery metadata has been removed from this public report.

## Safety Verification

- Preview recipient allowlist enforced: yes, only the non-deliverable `portfolio-owner@example.test` label is allowed.
- Lead outreach blocked: yes.
- Arbitrary recipient input accepted: no.
- Bulk sending supported: no.
- Default behavior: dry-run.
- Real send enabled: no; confirmed calls fail closed before OAuth or Gmail access.
- OAuth scope: `https://www.googleapis.com/auth/gmail.send`
- Cloud deployment performed: no.
- Compute default service account used: no.
- Secrets printed or copied: no.

## Evidence

Evidence ZIP target:

`D:\gaps\Business_Intel\Evidence\PROMPT#09_EMAIL_SENDER_ADK_AGENT.zip`

The evidence bundle is intended to include changed source files, tests, docs,
safe logs, dry-run output, safe send-result output, a file tree snapshot, and
`.gitignore`.

The evidence bundle must exclude:

- `.local_secrets`
- `gmail_sender_credentials.json`
- `gmail_sender_token.json`
- `client_secret*.json`
- access tokens
- refresh tokens
- full OAuth credential JSON

## ADK Web Prompts

- `Show me the Hello Nilhan email dry run.`
- `Send the Hello Nilhan test email.`
- `What email sending restrictions are currently active?`
- `Can you send an email to a lead?`

