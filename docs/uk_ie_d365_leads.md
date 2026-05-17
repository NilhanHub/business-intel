# UK & Ireland Dynamics 365 Lead Agent

`uk_ie_d365_leads` is a local Google ADK agent for finding public evidence that UK and Ireland companies may need Microsoft Dynamics 365 support, augmentation, rescue, upgrade, migration, managed services, or specialist help.

## Local Agent

- Package: `uk_ie_d365_leads`
- Root agent: `uk_ie_d365_leads.agent.root_agent`
- ADK app: `uk_ie_d365_leads.agent.app`
- Search-only sub-agent: `uk_ie_d365_leads.agents.search_agent.d365_search_agent`

The agent is separate from `sl_trigger_leads` and `hello_cloud_agent`.

## Search Architecture

The root agent orchestrates lead discovery through `find_uk_ie_d365_leads`. Search is provider-agnostic and credential-gated. The current adapter order is:

1. `google_grounding`: direct `google-genai` Google Search grounding; uses local Gemini API key or ADC/project credentials when available. The ADK `d365_search_agent` remains search-only for routing/future ADK use, but the live provider path avoids the failed ADK-wrapper multi-tool route.
2. `tavily`: requires `TAVILY_API_KEY`.
3. `exa`: requires `EXA_API_KEY`.
4. `serper`: requires `SERPER_API_KEY`.
5. `serpapi`: requires `SERPAPI_API_KEY`.
6. `firecrawl`: requires `FIRECRAWL_API_KEY`.
7. `custom_search_api`: requires `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_CX`.

If no provider is configured, the tool returns `status: blocked`, no leads, and a setup error. It does not create sample, demo, mock, or simulated leads.

The default query plan is grouped by signal class:

- `hiring_pain`
- `direct_company_career_site_searches`
- `commercial_non_tender_buying_signals`
- `implementation_migration_upgrade_rescue`
- `installed_base_discovery`
- `transformation_trigger`

Tender/procurement discovery is out of scope. The agent must not search Find a Tender, Contracts Finder, eTenders, council tenders, NHS tenders, university tenders, RFPs, or formal procurement notices. If such a candidate appears in search results, it is rejected with `tender_or_procurement_out_of_scope`.

Candidates are classified into commercial tiers:

- Tier A: accepted commercial lead with UK/Ireland, evidence URL, explicit Dynamics 365 or Microsoft business app evidence, and a clear commercial signal.
- Tier B: provisional lead that looks useful but needs one or more verification points resolved.
- Tier C: watchlist or installed-base evidence with weak urgency.
- Tier D: rejected candidate with `rejection_reason`.

Tier B and Tier C candidates remain visible. Rejected candidates are returned with `rejection_reason` when `include_rejected` is enabled.

## Decision Auditability

The search step is AI/model generated: direct `google-genai` Google Search grounding returns public-web `title`, `url`, and `snippet` JSON. The default model for that search path is `gemini-2.5-flash` unless `D365_GOOGLE_MODEL` is set.

The final candidate normalization, rejection, scoring, and Tier A/B/C/D classification are deterministic Python rules in `uk_ie_d365_leads.tools.lead_tools`. There is not yet a second-pass LLM reviewer for final reject/promote judgement.

Future live outputs and offline replay outputs include:

- `audit_metadata`: schema/classifier/query/prompt versions, provider path, effective model name, model source, provider client mode, masked/project-present Google metadata, location, live-run flag, request count, timestamps, and local code-version hint.
- `audit_trace`: raw grounded result fields, normalized fields, extracted evidence, source query/group when known, and per-rule results.
- `final_decision`: final tier, accepted/rejected flag, rejection or promotion reason, scores, missing verification points, human-review recommendation, and deterministic decision summary.

To inspect why a lead was rejected, open the JSON output and review `audit_trace.rule_results` for failed blocking rules, then check `final_decision.decision_rule_summary`. To identify possible false negatives, prioritize Tier D items where `final_decision.human_review_recommended` is `true`, especially vendor/case-study pages, recruitment/job-board snippets, UK/Ireland-missing snippets, unresolved `grounding_redirect` URLs, and installed-base results with weak urgency.

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

With Google-native credentials configured:

```powershell
$env:D365_SEARCH_PROVIDER = "google_grounding"
python -c "from uk_ie_d365_leads.tools.lead_tools import find_uk_ie_d365_leads; import json; print(json.dumps(find_uk_ie_d365_leads(max_results=5), indent=2))"
```

Do not use private/authenticated LinkedIn pages, logged-in browser sessions, or fake search data.
