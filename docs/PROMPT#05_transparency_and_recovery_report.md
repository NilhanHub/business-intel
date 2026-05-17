# PROMPT#05 Transparency And Recovery Report

Run date: 2026-04-28  
Project root: `D:\gaps\Business_Intel`  
Target app: `D:\gaps\Business_Intel\sl_trigger_leads`

## Summary

PASS. The `sl_trigger_leads` ADK app now discloses configured public source names and URLs, exposes `list_configured_sources(include_urls=True)`, attempts best-effort source recovery on fetch failure, and reports source coverage metadata in live lead results.

Sample/simulation mode was not restored. Runtime guards still block missing evidence URLs, missing `verified_live: true`, `example.test`, and sample/simulation markers.

## Chosen Skills And Weapons

- `google-agents-cli-workflow` from `C:\Users\Nilhan.dev\.agents\skills\google-agents-cli-workflow\SKILL.md`
- `google-agents-cli-adk-code` from `C:\Users\Nilhan.dev\.agents\skills\google-agents-cli-adk-code\SKILL.md`
- Local deterministic tools in `sl_trigger_leads/tools`
- `python -m unittest`
- `adk web`
- `rg`

No broad Drive D TAC or skill scan was performed.

## Public Sources Now Disclosed

`list_configured_sources(include_urls=True)` returns the actual registry URLs:

- Daily FT - IT / Telecom / Tech: `https://www.ft.lk/it-telecom-tech/50`
- Daily FT - Business: `https://www.ft.lk/business/34`
- ITPro.lk Jobs: `https://itpro.lk/jobs`
- Colombo Stock Exchange - Company Announcements: `https://www.cse.lk/announcements`

The registry version is `PROMPT#05-transparency-recovery-v1`.

## Code Changes

- Updated `sl_trigger_leads/agent.py` so public configured source names and URLs are explicitly non-confidential.
- Added `list_configured_sources(include_urls=True)` in `sl_trigger_leads/tools/source_registry.py`.
- Added `sl_trigger_leads/tools/source_health.py`.
- Added `sl_trigger_leads/tools/source_recovery.py`.
- Updated `sl_trigger_leads/tools/source_fetcher.py` to invoke recovery after failed source fetches.
- Updated `sl_trigger_leads/tools/live_source_tools.py` to return `source_coverage`, `source_coverage_summary`, and `source_notes`.
- Updated `sl_trigger_leads/tools/__init__.py` exports.
- Updated `sl_trigger_leads/data/source_registry.json` with public disclosure policy, recovery candidates, and corrected CSE route.
- Updated `sl_trigger_leads/tests/test_real_data_guards.py`.
- Added `tools/run_prompt05_source_recovery_smoke.py`.

## CSE Fix And Recovery

The CSE configured route is now:

`https://www.cse.lk/announcements`

The old route:

`https://www.cse.lk/pages/company-announcements/company-announcements.component.html`

is retained in `previous_urls` and is tested through recovery. The recovery smoke selected `https://www.cse.lk/announcements` with status `recovered`.

## Validation Commands

Commands run:

- `adk web --help`
- `adk web --port 43155 --no-reload .`
- `python -m compileall sl_trigger_leads tools`
- `python -m unittest discover -s sl_trigger_leads/tests -v`
- `python tools/run_prompt04_live_smoke.py`
- `python tools/run_prompt05_source_recovery_smoke.py`
- `rg -n "find_top_sample|sample_signals|example\.test|SAMPLE DATA|synthetic|simulation" sl_trigger_leads tools AGENTS.md DESIGN_SPEC.md REAL_DATA_POLICY.md docs -g "!**/__pycache__/**"`

## Validation Results

- Unit tests: PASS, 11 tests.
- PROMPT#04 live smoke rerun: PASS.
- PROMPT#05 source recovery smoke: PASS.
- ADK Web app-info check: PASS, `sl_trigger_leads` was discovered and exposes `list_configured_sources` and `recover_source_url`.
- Runtime sample fallback scan: no runtime sample-loading tool or sample data file usage found; hits were policy, tests, and guard code.

## Smoke Result

`logs\PROMPT#05_source_recovery_smoke.log` reports:

- configured source count: 4
- configured URLs visible: true
- old CSE recovery status: recovered
- selected CSE replacement: `https://www.cse.lk/announcements`
- live sources checked: 4
- live sources succeeded: 4
- live sources recovered in normal run: 0
- live sources failed in normal run: 0
- verified live leads found: 5

## Outputs

- `outputs\PROMPT#05_source_coverage.json`
- `outputs\PROMPT#05_live_leads_with_source_notes.json`
- `outputs\PROMPT#05_adk_app_info.json`

## Evidence Pack

Evidence ZIP:

`D:\gaps\Business_Intel\Evidence\PROMPT#05.zip`

## Blockers

None for PROMPT#05 acceptance.

## Final Verdict

PASS.
