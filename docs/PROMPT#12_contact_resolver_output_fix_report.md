# PROMPT#12 Contact Resolver Output Fix Report

## What Changed

PROMPT#12 makes Contact Resolver output contact-first and sales-usable in ADK Web.

The default resolver output now exposes a compact table through `compact_output` and per-result `adk_display`. It avoids long do-not-claim lists, compliance theory, raw schema dumps, and raw search traces unless the user explicitly asks for trace/evidence.

## Core Fixes

- Compact contact-first table for email/contact prompts.
- Live search remains the runtime default; dry-run is explicit only.
- URL normalization now handles `www.innovay.com/`, `vsoneworld.com/contact`, and already valid `https://...` URLs.
- Malformed URLs are rejected safely and logged in trace/fetch errors.
- `Low Fit / Watch`, `Watch`, `Park`, and similar verdict/status values are no longer treated as 1BT service buckets.
- Missing service buckets are inferred from signal text for QE/QA, API/middleware, AI, .NET/backend, and software-engineering roles.
- Duplicate companies are grouped into one company row with signal count.
- Search order now fetches the lead source, checks official pages, then records named-role/person search before allowing generic fallback.
- Named-person extraction rejects company-name snippets and "former CTO" style references so the table does not overclaim current decision makers.
- Generic company emails remain allowed, but only as labelled fallback routes after named search attempts.

## Live Smoke Result

Command:

```powershell
python tools\run_prompt12_contact_output_smoke.py
```

Result:

- Live web search enabled: yes
- Search provider: `adk_google_search`
- Compact output lines: 7
- Duplicate company grouping: yes
- URL normalization: yes
- Named-person search attempts recorded: yes
- Generic fallback after named search: yes
- Sending remains locked: yes

Compact output produced:

```text
Contact routes found:
| Company | Best contact | Type | Confidence | Evidence |
|---|---|---|---:|---|
| Vs One World (Pvt) Ltd (2 signals) | info@vsoneworld.com | generic fallback | 45 | https://www.vsoneworld.com/ |
| Innovay | info@innovay.com | generic fallback | 45 | https://www.innovay.com/contact_us.html |
Named contact search: Vs One World (Pvt) Ltd: no named CTO / Head of Engineering / Engineering Manager found within search budget.; Innovay: no named CTO / Head of AI / Head of Product found within search budget.
Next: Ready for draft only. Sending remains locked.
```

## Validation

Commands:

```powershell
python -m unittest discover -s sl_trigger_leads/tests -v
python tools\run_prompt12_contact_output_smoke.py
```

Unit test result:

- 84 tests passed.

Smoke result:

- PASS.

## ADK Web Prompts To Test

1. `get the email address for these`
2. `find emails for the latest leads`
3. `resolve contacts for the latest 3 leads`
4. `find the best contact route for Vs One World`
5. `show search trace for Vs One World`
6. `show evidence for Innovay`
7. `can you send these emails?`

Expected answer to prompt 7:

`No. Contact Resolver only finds contact routes. Sending to leads is still locked.`

## Outputs

- `outputs/PROMPT#12_contact_resolver_compact_output.json`
- `outputs/PROMPT#12_contact_resolver_search_trace.json`
- `logs/PROMPT#12_contact_resolver_output_fix.log`

## Still Locked

- No email sending.
- No lead outreach.
- No Gmail sender safety changes.
- No fake runtime contacts.
- No paid enrichment providers.

Evidence ZIP:

- `D:\gaps\Business_Intel\Evidence\PROMPT#12_CONTACT_RESOLVER_OUTPUT_FIX.zip`
