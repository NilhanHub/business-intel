# REAL_DATA_POLICY

## Runtime Rule

`sl_trigger_leads` must only return leads backed by live public-source evidence.

Runtime output must not include:

- synthetic leads
- fake companies
- fake URLs
- `example.test` URLs
- simulated evidence
- sample/demo records presented as leads

If no live evidence is available, the app must say:

```text
No verified live leads found.
```

## Lead Evidence Requirements

Every returned lead must include:

- `company`
- `country`
- `trigger_type`
- `trigger_summary`
- `evidence_url`
- `evidence_excerpt`
- `source_name`
- `source_type`
- `published_or_seen_date`
- `fetched_at`
- `verified_live: true`
- conservative score and verdict
- limits describing what is not yet verified

## Sample/Demo Data

Sample or demo data may only live in archived docs/tests if clearly marked and blocked from runtime. It must not be loaded by the ADK app and must not be exposed as a normal tool path.

Archived sample-mode files from PROMPT#02 are under:

`D:\gaps\Business_Intel\archive\PROMPT#04_removed_sample_mode`

## Guardrails

The runtime guard `assert_no_simulation_data(records)` must block records with:

- `example.test` or simulation markers
- missing `evidence_url`
- missing `evidence_excerpt`
- missing `company`
- `verified_live` not set to true

Every lead must trace to public evidence. Source fetch failures must be reported transparently.
