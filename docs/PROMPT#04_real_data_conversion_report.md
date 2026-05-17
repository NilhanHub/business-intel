# PROMPT#04 Real Data Conversion Report

## Summary

Converted `sl_trigger_leads` from sample/simulation mode to a real public-source lead intelligence app.

Final verdict: PASS.

## What Changed

- Runtime sample path removed from ADK tools.
- `sample_signals.json`, PROMPT#02 sample smoke cases, and the PROMPT#02 sample smoke runner were moved to `archive\PROMPT#04_removed_sample_mode`.
- Historical PROMPT#02 sample-mode build report was moved to the same archive.
- Added `REAL_DATA_POLICY.md`.
- Added a real public source registry at `sl_trigger_leads\data\source_registry.json`.
- Added live source adapter modules:
  - `sl_trigger_leads\tools\source_registry.py`
  - `sl_trigger_leads\tools\source_fetcher.py`
  - `sl_trigger_leads\tools\signal_extractor.py`
  - `sl_trigger_leads\tools\live_source_tools.py`
- Replaced scoring/guard code in `sl_trigger_leads\tools\signal_tools.py`.
- Updated `sl_trigger_leads\agent.py` so ADK Web uses live-source tools and forbids synthetic/sample fallback.
- Added `tools\run_prompt04_live_smoke.py`.
- Replaced tests with real-data guard and live workflow tests.

## Live Sources Implemented

Configured enabled public sources:

1. Daily FT - IT / Telecom / Tech: `https://www.ft.lk/it-telecom-tech/50`
2. Daily FT - Business: `https://www.ft.lk/business/34`
3. ITPro.lk Jobs: `https://itpro.lk/jobs`
4. Colombo Stock Exchange - Company Announcements: `https://www.cse.lk/pages/company-announcements/company-announcements.component.html`

Fetch methods are simple HTTP with a local user-agent and timeout. No paid APIs, browser automation, LinkedIn scraping, billing, IAM, or cloud deployment were added.

## Runtime Anti-Simulation Guard

Added `assert_no_simulation_data(records)`.

It blocks runtime lead records with:

- `example.test` URLs
- missing `evidence_url`
- missing `evidence_excerpt`
- missing `company`
- `verified_live` not true
- sample/synthetic/simulated markers

Every returned live lead must include source URL, source name, fetched timestamp, evidence excerpt, and `verified_live: true`.

## ADK Web Behavior

The root agent now instructs the model to:

- use verified live public-source evidence only
- never invent leads
- never use synthetic/sample/demo data
- report source failures
- say "No verified live leads found" when no evidence exists
- cite evidence URLs for every lead
- return partial results only with transparent source failures

ADK Web discoverability check: PASS.

## Validation

Commands run:

- `python -m compileall sl_trigger_leads tools`
- `python -m unittest discover -s sl_trigger_leads/tests -v`
- `python tools/run_prompt04_live_smoke.py`
- ADK Web check on local port 43129:
  - `/list-apps`
  - `/apps/sl_trigger_leads/app-info`

Results:

- Unit tests: PASS, 8 tests.
- Live smoke test: PASS.
- ADK Web app-info: PASS.
- Configured sources attempted: 4.
- Sources fetched successfully: 3.
- Source failures: 1.
- Verified live leads found: 10.

Transparent source failure:

- Colombo Stock Exchange - Company Announcements returned HTTP 404 for the configured public page. This is reported in live output and does not block the run because at least three other public sources fetched successfully.

## Live Output Files

- `outputs\PROMPT#04_live_leads.json`
- `outputs\PROMPT#04_live_leads.csv`
- `logs\PROMPT#04_live_smoke.log`

The latest smoke run found 10 verified live leads, mostly ITPro.lk hiring signals with evidence URLs.

## Current Limits

- Extraction is conservative and rule-based.
- Company extraction from job-board titles is heuristic and should be manually verified before outbound email.
- CSE announcements source needs a corrected public endpoint in a later prompt.
- Live leads are evidence-backed public signals, not fully enriched CRM records.
- No email addresses are inferred unless public evidence provides them.

## How To Run

From `D:\gaps\Business_Intel`:

```powershell
python -m unittest discover -s sl_trigger_leads/tests -v
python tools/run_prompt04_live_smoke.py
adk web
```

ADK Web prompt:

```text
Find live Sri Lankan public-signal leads for 1BT.
```

## Final Verdict

PASS.
