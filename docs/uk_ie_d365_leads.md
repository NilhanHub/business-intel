# UK & Ireland Dynamics 365 Lead Agent

`uk_ie_d365_leads` is a local Google ADK agent for finding public evidence that UK and Ireland companies may need Microsoft Dynamics 365 support, augmentation, rescue, upgrade, migration, managed services, or specialist help.

## Local Agent

- Package: `uk_ie_d365_leads`
- Root agent: `uk_ie_d365_leads.agent.root_agent`
- ADK app: `uk_ie_d365_leads.agent.app`
- Search-only sub-agent: `uk_ie_d365_leads.agents.search_agent.d365_search_agent`
- Audit reviewer sub-agent: `uk_ie_d365_leads.agents.classification_reviewer_agent.d365_classification_reviewer_agent`
- Production opportunity vetter sub-agent: `uk_ie_d365_leads.agents.opportunity_vetter_agent.d365_opportunity_vetter_agent`

The agent is separate from `sl_trigger_leads` and `hello_cloud_agent`.

## Search Architecture

The root agent orchestrates lead discovery through `find_uk_ie_d365_leads`. Search is provider-agnostic and credential-gated. The preferred broad-discovery mode is `provider_name="fanout"`, which tries all configured high-value providers in this order:

1. `google_grounding`: direct `google-genai` Google Search grounding; uses local Gemini API key or ADC/project credentials when available. The ADK `d365_search_agent` remains search-only for routing/future ADK use, but the live provider path avoids the failed ADK-wrapper multi-tool route.
2. `exa`: requires `EXA_API_KEY`.
3. `tavily`: requires `TAVILY_API_KEY`.
4. `serper`: requires `SERPER_API_KEY`.
5. `serpapi`: requires `SERPAPI_API_KEY`.
6. `firecrawl`: requires `FIRECRAWL_API_KEY`.

`custom_search_api` still exists as a disabled-by-default named fallback when `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_CX` are present, but it is not part of the normal fanout set.

If no provider is configured, the tool returns `status: blocked`, no leads, and a setup error. It does not create sample, demo, mock, or simulated leads.

Fanout defaults are deliberately bounded: max 4 providers, max 5 queries per
provider, max 5 results per query, and max 100 raw results per run. Missing API
keys do not fail the run; they appear in `provider_readiness`, while configured
providers record attempts, successes, failures, timeouts, and raw result counts
in `provider_budget`.

The default query plan is grouped by signal class:

- `hiring_pain`
- `direct_company_career_site_searches`
- `commercial_non_tender_buying_signals`
- `implementation_migration_upgrade_rescue`
- `installed_base_discovery`
- `transformation_trigger`

Before the default web search, `find_uk_ie_d365_leads` now builds a read-only
Google ecosystem discovery preflight. That preflight scans local Evidence
artifacts for prior companies, opportunity fingerprints, source fingerprints,
known-good domains, rejected patterns, and prior query/source patterns. The
default query plan is then augmented with targeted `site:` revisits of known-good
domains. A custom user query is left unchanged.

The same preflight is exposed to the ADK root agent through
`inspect_d365_discovery_backbone`. It is local/dry-run only: it does not create
Agent Search, Memory Bank, BigQuery, GCS, Document AI, Scheduler, or Runtime
resources.

Tender/procurement discovery is out of scope. The agent must not search Find a Tender, Contracts Finder, eTenders, council tenders, NHS tenders, university tenders, RFPs, or formal procurement notices. If such a candidate appears in search results, it is rejected with `tender_or_procurement_out_of_scope`.

Candidates are still grouped into compatibility tiers:

- Tier A: accepted commercial lead with UK/Ireland, evidence URL, explicit Dynamics 365 or Microsoft business app evidence, and a clear commercial signal.
- Tier B: provisional lead that looks useful but needs one or more verification points resolved.
- Tier C: watchlist or installed-base evidence with weak urgency.
- Tier D: hard-rejected candidate with `rejection_reason`/`hard_rejection_reason`.

Tier B and Tier C candidates remain visible. Vendor/service-provider pages,
job-board snippets, UK/Ireland-unclear snippets, grounding redirects, and thin
snippets are no longer hard rejected by default; they carry
`deterministic_flags` and `needs_ai_review`. When `include_rejected` is enabled,
the response also includes `review_candidates` and `hard_rejected_leads`.

## Decision Auditability

Every candidate now carries a `source_channel`:

- `public_web`: live public evidence from Google Search grounding or other web search providers.
- `agent_search`: private evidence-index/search result from Discovery Engine or Agent Search.
- `workspace_hint`: Drive, Gmail, Chat, Calendar, or other Workspace clue.
- `crm_hint`: CRM or sales-system clue.
- `custom_mcp`: local/helper-tool clue exposed through MCP or API Registry.

Only `public_web` candidates may become final PDF/report leads, and only after
the evidence is verified. Hint channels can create candidates and next actions,
but they must be converted into verified public-web evidence first.

Fresh search now fetches source pages before scoring whenever source fetching is
enabled. The reusable `SourceFetcher` follows redirects, records `final_url`,
status code, content type, canonical link, title, visible text excerpt, and
fetch errors. Private LinkedIn, tender/procurement portals, fake/example hosts,
non-HTTP URLs, and obvious binary files are skipped and logged instead of
silently disappearing. With `--parse-pdfs`, public PDF sources are parsed with
`pypdf`; text-bearing PDFs can become verified evidence, while image-heavy or
unparseable PDFs remain cleanup items. End-customer extraction runs against
fetched page/PDF text, so partner/vendor pages can provide evidence for the
named customer without the partner being mistaken for the buyer.

The search step is AI/model generated: direct `google-genai` Google Search grounding returns public-web `title`, `url`, and `snippet` JSON. The default model for that search path is `gemini-2.5-flash` unless `D365_GOOGLE_MODEL` is set.

The final candidate normalization and hard safety exclusions are deterministic
Python rules in `uk_ie_d365_leads.tools.lead_tools`. The deterministic layer is
intentionally thin: it rejects only obviously invalid candidates and leaves
opportunity judgement to the AI vetting workflow in
`uk_ie_d365_leads.tools.opportunity_vetting_tools`.

Future live outputs and offline replay outputs include:

- `audit_metadata`: schema/classifier/query/prompt versions, provider path, effective model name, model source, provider client mode, masked/project-present Google metadata, location, live-run flag, request count, timestamps, and local code-version hint.
- `audit_trace`: raw grounded result fields, normalized fields, extracted evidence, source query/group when known, and per-rule results.
- `final_decision`: final tier, accepted/rejected flag, rejection or promotion reason, scores, missing verification points, human-review recommendation, and deterministic decision summary.
- `deterministic_flags`, `needs_ai_review`, and `hard_rejection_reason`: explicit fields separating review-worthy uncertainty from hard exclusion.

To inspect a candidate, open the JSON output and review `deterministic_flags`,
`missing_verification_points`, `audit_trace.rule_results`, and
`final_decision.decision_rule_summary`. For production qualification, run the AI
vetter over `review_candidates` and surfaced A/B/C candidates. The old
`d365_classification_reviewer_agent` remains audit/proposal-only and should not
be used as the production opportunity judge.

For security, audit metadata deliberately does not log API keys, raw ADC credentials, or unmasked project identifiers. Project identity is represented only as present/absent plus a masked project-id hint when available.

## Human Review Shortlist

`tools\review_uk_ie_d365_candidates.py` is a local evidence-review exporter. It reads `Evidence\UK_IE_D365_AUDIT_REPLAY.json`, preserves the existing Tier A/B/C/D decisions, and writes:

- `Evidence\UK_IE_D365_HUMAN_REVIEW_SHORTLIST.json`
- `Evidence\UK_IE_D365_HUMAN_REVIEW_SHORTLIST.md`

The utility exists to help Nilhan quickly review likely false negatives and commercially useful provisional/watchlist candidates without changing search or classification behavior. It makes no live calls: no Google/Gemini/Vertex call, no `gcloud`, no browser, and no third-party search API.

Run it locally with:

```powershell
python tools\review_uk_ie_d365_candidates.py
```

Read the Markdown from the top down: the executive summary shows input counts and shortlist size, the table gives the fastest triage view, the Tier B/C section preserves all provisional/watchlist candidates, and the Tier D section highlights rejected candidates worth manual checking.

Use `false_negative_risk` as a review priority, not as a classification override. Use `commercial_usefulness` to decide whether a manual check is worth time. `promote_candidate` means “worth checking for promotion”; it does not update the underlying tier. Keep candidates provisional/watchlist/rejected unless public evidence resolves the missing verification points or failed blocking rules.

## Run Locally

```powershell
python -m unittest discover -s uk_ie_d365_leads/tests -v
python tools/run_uk_ie_d365_leads_smoke.py
python -c "from uk_ie_d365_leads.agent import root_agent; print(root_agent.name)"
```

Inspect the read-only Google ecosystem discovery backbone and write local dry-run
artifacts for Agent Search import, BigQuery ledger mirroring, and evidence-lake
planning:

```powershell
uv run python tools\setup_uk_ie_d365_cloud_backbone.py
```

That command writes files under `Evidence`, including:

- `UK_IE_D365_DISCOVERY_PREFLIGHT_<timestamp>.json/.md`
- `UK_IE_D365_AGENT_SEARCH_IMPORT_<timestamp>.ndjson`
- `UK_IE_D365_BIGQUERY_LEDGER_MIRROR_<timestamp>.json`
- `UK_IE_D365_GOOGLE_ECOSYSTEM_BACKBONE_<timestamp>.md`
- `UK_IE_D365_CLOUD_BACKBONE_SETUP_<timestamp>.json/.md`

Use `--apply` only after explicit IAM/billing/provisioning approval. Default
mode is read-only and creates no cloud resources.

With Google-native credentials configured:

```powershell
$env:D365_SEARCH_PROVIDER = "google_grounding"
python -c "from uk_ie_d365_leads.tools.lead_tools import find_uk_ie_d365_leads; import json; print(json.dumps(find_uk_ie_d365_leads(max_results=5), indent=2))"
```

Broad fanout with early source-page fetching:

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --run-search --provider-name fanout --search-max-results 12 --max-live-requests 25
```

Fanout plus targeted query packs and PDF parsing:

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --run-search --provider-name fanout --query-pack all --parse-pdfs --search-max-results 12 --max-live-requests 25
```

Replay a prior shortage report into the next query plan:

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --run-search --provider-name fanout --use-shortage-report Evidence\UK_IE_D365_USEFUL_LEADS_FRESH_20260612_SHORTAGE_REPORT.json
```

Retry prior source-fetch failures or cleanup queues:

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --retry-source-errors Evidence\UK_IE_D365_SOURCE_FETCH_ERRORS_YYYYMMDDTHHMMSSZ.json --parse-pdfs
```

That writes the raw run plus provider/source artifacts under `Evidence`:

- `UK_IE_D365_FANOUT_SEARCH_RUN_<timestamp>.json`
- `UK_IE_D365_PROVIDER_AUDIT_<timestamp>.json`
- `UK_IE_D365_PROVIDER_SCORECARD_<timestamp>.json`
- `UK_IE_D365_DISCOVERY_MEMORY_<timestamp>.json`
- `UK_IE_D365_QUERY_PLAN_<timestamp>.json`
- `UK_IE_D365_SOURCE_FETCHES_<timestamp>.json`
- `UK_IE_D365_SOURCE_FETCH_ERRORS_<timestamp>.json`
- `UK_IE_D365_SOURCE_RETRY_RUN_<timestamp>.json` when `--retry-source-errors` is used

Optional knobs are `--fanout-max-providers`,
`--fanout-queries-per-provider`, `--fanout-results-per-query`,
`--fanout-max-raw-results`, `--source-fetch-max-urls`, `--query-pack`,
`--parse-pdfs`, `--use-shortage-report`, `--retry-source-errors`, and
`--disable-early-source-fetch`. Exa, Tavily, Serper, SerpAPI, and Firecrawl are
used only when their API keys already exist in the environment.

AI vetting over saved evidence:

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --evidence-file Evidence\UK_IE_D365_FRESH_SEARCH_20260603.json
python tools\run_uk_ie_d365_ai_vetting.py --run-search --search-max-results 10 --max-live-requests 25
python tools\run_uk_ie_d365_ai_vetting.py --run-search --live-ai --live-followup --max-followup-searches 2 --max-source-fetches 3
```

Regression-check the production opportunity vetter against the saved 12-lead
baseline:

```powershell
uv run python tools\check_uk_ie_d365_vetter_agent.py --input-pack Evidence\UK_IE_D365_USEFUL_LEADS_FRESH_20260612.json --source-checks Evidence\UK_IE_D365_USEFUL_LEADS_FRESH_20260612_SOURCE_CHECKS.json --required-project business-intel-123 --live-ai
```

The check uses `google-genai Gemini Enterprise Agent Platform / Vertex AI API
via ADC` in user-facing metadata while preserving the existing SDK client path.

Do not use private/authenticated LinkedIn pages, logged-in browser sessions, or fake search data.
