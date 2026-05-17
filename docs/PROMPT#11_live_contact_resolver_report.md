# PROMPT#11 Live Contact Resolver Report

## What Was Built

PROMPT#11 upgrades the Contact Resolver Agent to live public-web mode.

Created:

- `sl_trigger_leads/agents/contact_search_agent.py`
- `sl_trigger_leads/tools/live_contact_search_tools.py`
- `sl_trigger_leads/tests/test_contact_live_search_tools.py`
- `sl_trigger_leads/tests/test_contact_resolver_live_mode.py`
- `tools/run_prompt11_live_contact_resolver_smoke.py`
- `docs/live_contact_search_provider_design.md`

Updated:

- `sl_trigger_leads/agent.py`
- `sl_trigger_leads/agents/__init__.py`
- `sl_trigger_leads/agents/contact_resolver_agent.py`
- `sl_trigger_leads/tools/__init__.py`
- `sl_trigger_leads/tools/contact_resolver_tools.py`
- `sl_trigger_leads/tests/test_contact_resolver_tools.py`

Live contact resolution now defaults to live mode for contact-resolution prompts. Dry-run is still available only when explicitly requested.

## Provider Status

Live web search is enabled through ADK Google Search.

- Provider: `adk_google_search`
- Search specialist: `contact_search_agent`
- Runtime implementation: search-only ADK agent using `google_search`
- Fallback hooks: Google CSE and SerpAPI-style providers, disabled unless env vars are configured

The `.env` loader strips a UTF-8 BOM and normalizes `GOOGLE_GENAI_USE_VERTEXAI=TRUE` to `true` so the local ADK/Vertex path can run.

## Live Smoke Result

Command:

```powershell
python tools\run_prompt11_live_contact_resolver_smoke.py --live --company "Vs One World (Pvt) Ltd" --lead-url "https://itpro.lk/job/13609/qe-engineer-api-integration-at-vs-one-world-pvt-ltd/"
```

Result:

- Live web search enabled: yes
- Provider used: `adk_google_search`
- Company tested: `Vs One World (Pvt) Ltd`
- Lead evidence URL fetched: yes
- Search result returned by ADK Google Search: yes
- Public URLs inspected: 8
- Best route type: `generic_company`
- Best route: `info@vsoneworld.com` from `https://www.vsoneworld.com/`
- Confidence: 45, Low
- Fallback route: official contact page `https://www.vsoneworld.com/contact`

No named role-relevant buyer was found within the budget, so the resolver returned the best practical public route and clearly labelled it as a fallback.

## What Was Tested

Validation commands:

```powershell
python -m unittest discover -s sl_trigger_leads/tests -v
python tools\run_prompt11_live_contact_resolver_smoke.py --live --company "Vs One World (Pvt) Ltd" --lead-url "https://itpro.lk/job/13609/qe-engineer-api-integration-at-vs-one-world-pvt-ltd/"
```

Coverage added or preserved:

- ADK Google Search provider discovery.
- Explicit provider-unavailable setup message.
- Live mode no longer defaults to dry-run.
- `no_contact_found` only after real attempts.
- Generic inbox fallback is allowed but low confidence.
- Job-post apply/contact route is allowed as fallback.
- Named relevant person outranks generic inbox.
- Contact form fallback route is allowed.
- Search budget stopping behavior.
- Existing Contact Resolver tests.
- Existing Gmail sender tests.
- Existing lead finder tests.
- No sending behavior added.
- Search trace output created.

## Still Disabled

- Lead outreach sending.
- Bulk contact.
- Gmail sender changes.
- Arbitrary recipient email sending.
- Paid enrichment providers.
- Email verification providers.
- Cloud deployment.

## ADK Web Prompts To Test

1. `Resolve contacts for the latest 3 leads.`
2. `Resolve contact route for lead 1.`
3. `Find the best contact route for Vs One World.`
4. `Show contact resolver dry run.`
5. `Can you send the email now?`

Expected answer to prompt 5:

`No. Contact Resolver only resolves contact routes. Sending to leads is still locked.`

## Evidence

Primary outputs:

- `outputs/PROMPT#11_live_contact_resolver_results.json`
- `outputs/PROMPT#11_live_contact_resolver_search_trace.json`
- `logs/PROMPT#11_live_contact_resolver.log`

Evidence ZIP:

- `D:\gaps\Business_Intel\Evidence\PROMPT#11_LIVE_CONTACT_RESOLVER.zip`

The evidence ZIP excludes `.local_secrets`, Gmail credentials, Gmail tokens, OAuth client secrets, access tokens, refresh tokens, API key values, and full credential JSON.
