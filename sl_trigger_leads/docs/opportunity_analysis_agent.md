# opportunity_analyst

`opportunity_analyst` is a separate ADK sub-agent for 1BT opportunity analysis.

It does not fetch live sources. It receives verified live leads from `sl_trigger_leads`, checks that each lead has live evidence fields, maps the lead to the local 1BT service taxonomy, and recommends a cautious outreach response.

## Inputs

Each lead must include:

- `company`
- `evidence_url`
- `evidence_excerpt`
- `source_name`
- `fetched_at`
- `verified_live: true`

The agent rejects missing evidence, `example.test`, sample markers, and unverified records through `assert_no_simulation_data`.

## Tools

- `load_onebt_service_taxonomy`
- `classify_opportunity_bucket`
- `analyze_opportunity_for_1bt`
- `analyze_leads_for_1bt`
- `create_response_strategy`

## Output

The analysis returns primary bucket, secondary buckets, confidence, evidence-grounded reasoning, recommended 1BT offer, outreach theme, who to contact, what to verify next, and do-not-claim guardrails.

## Boundaries

- No sample leads.
- No invented evidence.
- No LinkedIn scraping.
- No 1BT website reads at runtime.
- No email sending or Gmail drafts.
- No deployment.
