# Business_Intel

Purpose: Sri Lanka Public-Signal Lead Intelligence Engine for 1BT outbound sales intelligence.

Current phase: real public-source ADK app for PROMPT#04. Keep the build local-only unless a later prompt explicitly asks for deployment.

Evidence rule: all setup and verification evidence for this project belongs under `D:\gaps\Business_Intel\Evidence`.

Before ADK, agents-cli, repo setup, or agent-building work, consult relevant known skills only. Do not run broad Drive D scans unless a later prompt explicitly asks for one.

Use the installed Google agents-cli skills from `C:\Users\Nilhan.dev\.agents\skills` when future work involves ADK, scaffolding, evaluation, deployment, publishing, or observability.

Do not build tender intelligence unless explicitly requested. Tender/procurement-only signals should be parked or rejected by default.

Runtime real-data rule: never return synthetic/sample/demo companies, fake URLs, `example.test` URLs, or simulated evidence as leads. Every runtime lead must trace to live public evidence with `evidence_url`, `evidence_excerpt`, `source_name`, `fetched_at`, and `verified_live: true`.

Before any edit to the `Northwind CRM Warm Paths Tracker` Google Sheet, read and
follow `docs/northwind_warm_paths_sheet_contract.md` and the canonical machine
contract `docs/northwind_warm_paths_sheet_contract.v1.json`. Preserve complete
company blocks, formatting, dimensions, validation, formulas, and all `PF...`
feedback; create a dated workbook backup and verify the contract after writing.
