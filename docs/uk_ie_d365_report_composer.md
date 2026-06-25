# UK/IE D365 Report Composer

## Summary

`d365_report_composer_agent` is the local document-planning specialist for the
UK/Ireland Dynamics 365 evidence workflow. It turns a changing user requirement
and a vetted evidence pack into a structured report specification. The local
runner then renders that specification into Markdown, HTML, PDF, a source map,
a browse log, QA metadata, and a secret scan under `D:\gaps\Business_Intel\Evidence`.

The composer is separate from the vetter:

- `d365_opportunity_vetter_agent` decides whether a candidate is a real 1BT
  sales opportunity.
- `d365_report_composer_agent` decides how to explain already-vetted evidence
  in a useful, board-friendly document.

## Safety Model

The composer has no tools. It cannot browse, email, deploy, use Gmail, mutate
rules, or resolve contacts. It receives only:

- the live user requirement,
- saved evidence packs,
- source-check artifacts,
- optional style-reference metadata,
- bounded public follow-up evidence supplied by the runner.

The deterministic runner enforces source hygiene:

- no fake/sample/demo URLs,
- no private or authenticated LinkedIn,
- no tender/procurement-only sources,
- no Google grounding redirects as final evidence,
- no invented companies, contacts, URLs, D365 claims, budgets, dissatisfaction,
  buying intent, or source facts.

If evidence is useful but unresolved, the report must keep a visible
source-cleanup caveat instead of overclaiming.

## Local Commands

Dry-run from a vetted pack, no live AI and no live browsing:

```powershell
uv run python tools\run_uk_ie_d365_report_composer.py `
  --requirement "Create a board-friendly PDF report for the saved 12 UK/IE D365 leads." `
  --input-pack Evidence\UK_IE_D365_USEFUL_LEADS_FRESH_20260612.json `
  --source-checks Evidence\UK_IE_D365_USEFUL_LEADS_FRESH_20260612_SOURCE_CHECKS.json `
  --output-basename UK_IE_D365_REPORT_COMPOSER_DRYRUN_20260614
```

Live AI composition with the Google project guard:

```powershell
uv run python tools\run_uk_ie_d365_report_composer.py `
  --requirement "Create an executive opportunity intelligence PDF with strongest signals first." `
  --input-pack Evidence\UK_IE_D365_USEFUL_LEADS_FRESH_20260612.json `
  --source-checks Evidence\UK_IE_D365_USEFUL_LEADS_FRESH_20260612_SOURCE_CHECKS.json `
  --output-basename UK_IE_D365_REPORT_COMPOSER_LIVE_20260614 `
  --required-project business-intel-123 `
  --live-ai
```

Live AI plus bounded public browsing:

```powershell
uv run python tools\run_uk_ie_d365_report_composer.py `
  --requirement "Create a source-checked sales leadership report and refresh any thin public evidence." `
  --input-pack Evidence\UK_IE_D365_USEFUL_LEADS_FRESH_20260612.json `
  --source-checks Evidence\UK_IE_D365_USEFUL_LEADS_FRESH_20260612_SOURCE_CHECKS.json `
  --output-basename UK_IE_D365_REPORT_COMPOSER_LIVE_BROWSE_20260614 `
  --required-project business-intel-123 `
  --live-ai `
  --live-browse
```

## Outputs

For basename `UK_IE_D365_REPORT_COMPOSER_DRYRUN_20260614`, the runner writes:

- `UK_IE_D365_REPORT_COMPOSER_DRYRUN_20260614.json`
- `UK_IE_D365_REPORT_COMPOSER_DRYRUN_20260614.md`
- `UK_IE_D365_REPORT_COMPOSER_DRYRUN_20260614.html`
- `Evidence\PDFs\2026-06-14__uk-ie-d365__report-composer__live-smoke__12-accounts.pdf`
- `UK_IE_D365_REPORT_COMPOSER_DRYRUN_20260614_SOURCE_MAP.json`
- `UK_IE_D365_REPORT_COMPOSER_DRYRUN_20260614_BROWSE_LOG.json`
- `UK_IE_D365_REPORT_COMPOSER_DRYRUN_20260614_QA.json`
- `UK_IE_D365_REPORT_COMPOSER_DRYRUN_20260614_SECRET_SCAN.json`

The PDF is generated deterministically from the structured report spec. The
HTML is the richer visual template output and is useful for reviewing layout
style. The source map is the evidence trace that should be checked before using
the report for outreach planning.

## Style Presets

V1 supports three style presets:

- `executive_landscape`: board-friendly opportunity intelligence.
- `board_brief_portrait`: formal memo-style reports.
- `dense_pipeline_review`: compact pipeline and account-review packs.

The composer chooses the preset; renderer code owns safe CSS, PDF output, and
QA.

## Verification

Focused deterministic tests:

```powershell
uv run python -m pytest uk_ie_d365_leads/tests/test_uk_ie_d365_leads.py -q
```

Behavior eval scaffold:

```powershell
$env:GOOGLE_GENAI_USE_VERTEXAI = "true"
$env:GOOGLE_CLOUD_PROJECT = "business-intel-123"
$env:D365_GOOGLE_PROJECT = "business-intel-123"
$env:GOOGLE_CLOUD_LOCATION = "global"
uv run adk eval ./uk_ie_d365_leads tests/eval/evalsets/uk_ie_d365_report_composer.evalset.json --config_file_path tests/eval/eval_config.json
```

`agents-cli eval run` currently uses the repo-level `sl_trigger_leads` agent
directory from `pyproject.toml`. Use the direct `adk eval ./uk_ie_d365_leads`
form above for this composer-specific eval.

Do not use full-repo pytest as the acceptance gate for this lane because
`hello_cloud_agent` is an unrelated old experiment.
