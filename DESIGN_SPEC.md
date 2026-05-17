# Business_Intel DESIGN_SPEC

## Purpose

Build a local ADK app named `sl_trigger_leads` that helps 1 Billion Tech / 1BT discover, classify, score, and act on Sri Lankan public change signals that create non-tender outbound-sales reasons.

PROMPT#04 converts the app to real public-source mode. Runtime lead output must come from live fetched public evidence only.

## Non-Goals

- Tender or procurement intelligence.
- Full CRM, pipeline management, or email sending.
- Cloud deployment, billing, IAM, or GCP project setup.
- Paid API dependencies.
- Aggressive LinkedIn scraping or any behavior that violates site terms.
- A large platform architecture before the first local bot proves the workflow.
- Synthetic/sample/demo lead generation in runtime.
- Fake companies, fake source URLs, `example.test`, or simulated public evidence.

## Target User

1BT sales, delivery, or leadership users who want a fast way to turn public business changes into practical outbound angles for AI apps, Dynamics 365/CRM/Power Platform, managed IT/application support, data workflows, integrations, backend delivery, and business automation services.

## Target Leads

Sri Lankan companies with public evidence of change, urgency, or operational pressure. Preferred sectors include finance/insurance, apparel/manufacturing/export, hospitality/tourism, logistics, healthcare, retail/FMCG, and software/IT services.

## Supported Signal Types

- `hiring_spike`
- `leadership_change`
- `expansion`
- `acquisition_or_merger`
- `product_launch`
- `ai_or_digital_initiative`
- `compliance_or_regulatory_pressure`
- `system_integration_pressure`
- `generic_pr_fluff`
- `tender_or_procurement`
- `irrelevant`

## Scoring Model

Total score: 100.

- Recent public trigger: 25
- 1BT service fit: 25
- Local reachability: 20
- Named person found: 15
- Evidence quality: 10
- Deal size likelihood: 5

Verdict bands:

- 80-100: Contact now
- 60-79: Verify contact first
- 40-59: Watch list
- Below 40: Park

Auto-reject or park rules:

- Tender/procurement-only signals.
- Vague AI or PR fluff with no real action.
- Internship-only hiring.
- No IT/software/AI/CRM/data/support relevance.
- Stale signals older than 90 days unless strategically important.
- No reachable company/person signal.

## App Architecture

`sl_trigger_leads` is a local ADK package discoverable by `adk web` from `D:\gaps\Business_Intel`.

Current implementation:

- `root_agent` in `sl_trigger_leads/agent.py` orchestrates live-source fetching, extraction, scoring, and account packs.
- `sl_trigger_leads/tools/source_registry.py` loads configured public sources.
- `sl_trigger_leads/tools/source_fetcher.py` fetches public pages with polite timeouts and a local user-agent.
- `sl_trigger_leads/tools/signal_extractor.py` extracts candidate public signals.
- `sl_trigger_leads/tools/live_source_tools.py` exposes ADK-facing live tools:
  - `fetch_live_sources(source_limit)`
  - `extract_public_signals(html_or_text, source_meta)`
  - `find_live_leads(max_results, source_limit)`
  - `score_live_lead(lead)`
  - `create_live_account_pack(lead)`
  - `export_live_leads_csv(...)`
  - `report_source_failures(...)`
- `sl_trigger_leads/tools/signal_tools.py` contains shared classification, scoring, and anti-simulation guards.
- `sl_trigger_leads/data/source_registry.json` contains real public source configuration.
- `sl_trigger_leads/data/live_runs/` stores run-scoped live-source output snapshots.
- `sl_trigger_leads/tests` contains anti-simulation and live workflow tests.

Planned multi-agent split:

- `signal_classifier`: classify trigger type and confidence.
- `fit_scorer`: score 1BT fit and verdict band.
- `outreach_writer`: create concise outbound angle.
- `evidence_checker`: reject, park, watch, or keep based on evidence.

For PROMPT#04 these roles remain implemented as tools to keep the real-source reset small and auditable.

## Current Limitations

- The app fetches a small configured set of public pages only; it is not a broad web crawler.
- The app does not send emails or write to a CRM.
- The deterministic classifier is keyword/rule based; it is intentionally transparent but not exhaustive.
- ADK Web interaction requires local ADK model credentials or environment already configured on the machine.
- Source pages can fail or produce no verified leads; the app must report that instead of inventing leads.

## Next Wave Plan

1. Add a safe public-source ingestion path for user-supplied URLs or exported search results.
2. Add source citation capture and freshness checks for live public evidence.
3. Split tool roles into ADK sub-agents if orchestration complexity grows.
4. Add richer eval sets for sectors, false positives, and outreach quality.
5. Add optional CRM/email handoff artifacts only after the lead-intelligence workflow is proven.
