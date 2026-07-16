# UK/IE D365 AI Opportunity Vetting

## Summary

The UK/IE D365 pipeline now treats deterministic rules as safety guardrails, not
as the final opportunity judge. Hard deterministic rejection is reserved for
obviously invalid candidates: missing public URL, fake/example URL, private
LinkedIn, tender/procurement-only, clearly out of UK/Ireland scope, generic IT
with no Microsoft business-app signal, or no D365/Dynamics CRM/Business
Central/Power Platform/Dataverse/Microsoft business-app signal.

Vendor pages, job-board snippets, UK/IE-unclear snippets, grounding redirects,
and thin snippets are kept visible as AI-review candidates with
`deterministic_flags`.

## Local Workflow

1. Run search with `include_rejected=True`.
2. Keep `hard_rejected_leads` excluded.
3. Send `review_candidates` plus normal A/B/C candidates to AI vetting.
4. Let the AI vetter decide `ready_to_contact`, `provisional_contact_now`,
   `source_cleanup_needed`, or `reject`.
5. For promising/unclear candidates, allow bounded follow-up: at most 2 grounded
   searches and 3 public source fetches per candidate.

Dry run, no live AI:

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --evidence-file Evidence\UK_IE_D365_FRESH_SEARCH_20260603.json
```

Fresh search artifact plus dry-run vetting:

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --run-search --search-max-results 10 --max-live-requests 25
```

Multi-provider fanout plus early source-page fetching:

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --run-search --provider-name fanout --search-max-results 12 --max-live-requests 25
```

Fanout searches configured providers in the order `google_grounding`, `exa`,
`tavily`, `serper`, `serpapi`, `firecrawl`. Missing provider keys are recorded
in readiness/audit output and do not fail the run. The default budgets are max 4
providers, 5 queries per provider, 5 results per query, and 100 raw results per
run. Use `--fanout-max-providers`, `--fanout-queries-per-provider`,
`--fanout-results-per-query`, `--fanout-max-raw-results`,
`--source-fetch-max-urls`, or `--disable-early-source-fetch` to tune the run.

Use targeted query packs and public PDF parsing when looking for partner case
studies and customer story documents:

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --run-search --provider-name fanout --query-pack all --parse-pdfs --search-max-results 12 --max-live-requests 25
```

Use prior shortage reports or fetch-error artifacts as next-run fuel:

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --run-search --provider-name fanout --use-shortage-report Evidence\UK_IE_D365_USEFUL_LEADS_FRESH_20260612_SHORTAGE_REPORT.json
python tools\run_uk_ie_d365_ai_vetting.py --retry-source-errors Evidence\UK_IE_D365_SOURCE_FETCH_ERRORS_YYYYMMDDTHHMMSSZ.json --parse-pdfs
```

Live AI vetting. User-facing artifacts call this
`google-genai Gemini Enterprise Agent Platform / Vertex AI API via ADC`; the
underlying SDK still uses the `vertexai=True` client path.

When the active ADC identity is not authorized for the guarded project, select
an already-authenticated gcloud account for this command only. This does not
change global gcloud configuration and never writes or prints the access token:

```powershell
$env:D365_GCLOUD_ACCOUNT = "authorized-account@example.com"
```

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --live-ai --evidence-file Evidence\UK_IE_D365_FRESH_SEARCH_20260603.json
```

Live AI plus bounded follow-up:

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --run-search --live-ai --live-followup --max-followup-searches 2 --max-source-fetches 3
```

For larger saved candidate pools, vet bounded non-overlapping slices so each
successful batch is durable, then merge them after all batches finish:

```powershell
python tools\run_uk_ie_d365_ai_vetting.py --live-ai --evidence-file Evidence\SEARCH.json --candidate-offset 0 --max-candidates 20 --output-file Evidence\VETTING_01.json
python tools\run_uk_ie_d365_ai_vetting.py --live-ai --evidence-file Evidence\SEARCH.json --candidate-offset 20 --max-candidates 20 --output-file Evidence\VETTING_02.json
python tools\run_uk_ie_d365_ai_vetting.py --merge-vetting-files Evidence\VETTING_01.json Evidence\VETTING_02.json --output-file Evidence\VETTING_MERGED.json
```

The merge command refuses overlapping candidate IDs or batches produced from
different input evidence.

Regression-check the production vetter against the saved 12-lead baseline:

```powershell
uv run python tools\check_uk_ie_d365_vetter_agent.py --input-pack Evidence\UK_IE_D365_USEFUL_LEADS_FRESH_20260612.json --source-checks Evidence\UK_IE_D365_USEFUL_LEADS_FRESH_20260612_SOURCE_CHECKS.json --required-project business-intel-123 --live-ai
```

The check writes dated artifacts under `Evidence`, for example
`UK_IE_D365_VETTER_AGENT_CHECK_<timestamp>.json`, `.md`, and
`_SECRET_SCAN.json`. A clean run means zero request failures, zero material
issues, and `readiness_conclusion=ready_for_future_final_curation`.

## Outputs

Artifacts are written under `D:\gaps\Business_Intel\Evidence` by default:

- `UK_IE_D365_AI_VETTING.json`
- `UK_IE_D365_AI_VETTING.md`
- `UK_IE_D365_AI_VETTING_REPORT.md`
- `UK_IE_D365_AI_VETTING_SECRET_SCAN.json`

When `--run-search` is used, the runner also writes either
`UK_IE_D365_AI_VETTING_RAW_SEARCH_<timestamp>.json` or, for fanout,
`UK_IE_D365_FANOUT_SEARCH_RUN_<timestamp>.json` in the same output directory.
Fanout/search runs also write provider and source-fetch audit artifacts when
available:

- `UK_IE_D365_PROVIDER_AUDIT_<timestamp>.json`
- `UK_IE_D365_PROVIDER_SCORECARD_<timestamp>.json`
- `UK_IE_D365_DISCOVERY_MEMORY_<timestamp>.json`
- `UK_IE_D365_QUERY_PLAN_<timestamp>.json`
- `UK_IE_D365_SOURCE_FETCHES_<timestamp>.json`
- `UK_IE_D365_SOURCE_FETCH_ERRORS_<timestamp>.json`
- `UK_IE_D365_SOURCE_RETRY_RUN_<timestamp>.json` when retry mode is used

The JSON artifact contains the full records trace plus
`useful_leads`, `rejected_reviews`, `reject_review_summary`,
`follow_up_records`, and `llm_request_records`.

Final fresh-lead curation also writes lead-conservation artifacts:

- `*_CANDIDATE_LEDGER.json`
- `*_SOURCE_CLEANUP_QUEUE.json`
- `*_IDENTITY_RESOLUTION.json`
- `*_DUPLICATE_AUDIT.json`
- `*_SHORTAGE_REPORT.json`
- `*_SHORTAGE_REPORT.md`

The final PDF/report lane should consume only `leads` from the final output.
Cleanup, identity-resolution, duplicate, and retained-good queues preserve useful
candidates for review without turning unresolved evidence into final claims.

Each candidate/review also keeps `source_channel` and `final_pdf_eligible`.
Agent Search, Workspace, CRM, and custom MCP records are treated as discovery
hints. If one of those hints looks useful, the selector retains it in cleanup
queues with a next action, but it cannot become a final PDF lead until public-web
evidence is fetched and verified.

Final selected leads require `verified_live: true`. Snippet-only or hint-only
records are retained in cleanup/identity queues rather than published.
Text-bearing public PDFs may satisfy the live evidence rule when parsed
successfully. Image-heavy, parser-unavailable, or no-text PDFs remain cleanup
items until verified by another public source or a manual evidence review.

## Safety Rules

- No Gmail, email sending, deployment, private/authenticated LinkedIn, fake
  evidence, or tender-intelligence workflow.
- The existing `d365_classification_reviewer_agent` remains audit/proposal-only.
- The new `d365_opportunity_vetter_agent` owns production opportunity judgement
  and write-up, but it has no tools. The runner supplies saved and follow-up
  evidence.
- If evidence is useful but unresolved, use `source_cleanup_needed` instead of
  overclaiming.
