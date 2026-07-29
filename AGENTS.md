# Business_Intel

Purpose: Sri Lanka Public-Signal Lead Intelligence Engine for 1BT outbound sales intelligence.

Current phase: real public-source ADK app for PROMPT#04. Keep the build local-only unless a later prompt explicitly asks for deployment.

Evidence rule: all setup and verification evidence for this project belongs under `D:\gaps\Business_Intel\Evidence`.

Before ADK, agents-cli, repo setup, or agent-building work, consult relevant known skills only. Do not run broad Drive D scans unless a later prompt explicitly asks for one.

Use the installed Google agents-cli skills from `C:\Users\Nilhan.dev\.agents\skills` when future work involves ADK, scaffolding, evaluation, deployment, publishing, or observability.

Do not build tender intelligence unless explicitly requested. Tender/procurement-only signals should be parked or rejected by default.

Runtime real-data rule: never return synthetic/sample/demo companies, fake URLs, `example.test` URLs, or simulated evidence as leads. Every runtime lead must trace to live public evidence with `evidence_url`, `evidence_excerpt`, `source_name`, `fetched_at`, and `verified_live: true`.

Repository capability catalog rule: before adding, removing, renaming, or retiring
an application, website, exported ADK agent/app, service, workflow, deployment,
integration, data store, public endpoint, or test lane, update
`catalog/repository.catalog.v1.json`, regenerate `docs/REPOSITORY_CATALOG.md`, and
run `uv run python tools/check_repository_catalog.py`. Discovery produces
candidates only; canonical changes require review.

Before any edit to the `Northwind CRM Warm Paths Tracker` Google Sheet, read and
follow `docs/northwind_warm_paths_sheet_contract.md` and the canonical machine
contract `docs/northwind_warm_paths_sheet_contract.v1.json`. Preserve complete
company blocks, formatting, dimensions, validation, formulas, and all `PF...`
feedback; create a dated workbook backup and verify the contract after writing.

Before any edit to the `Sam Dharmasiri` tab, also read and follow the dedicated
human contract `docs/northwind_sam_dharmasiri_sheet_contract.md` and canonical
machine contract `docs/northwind_sam_dharmasiri_sheet_contract.v1.json`. Preserve
Sam-first route ordering, stable-ID evidence, atomic checkpoint recovery,
complete company blocks, source provenance, and all exact formatting rules.

Before any edit to the `Jeremy Pike` tab, also read and follow the dedicated
human contract `docs/northwind_jeremy_pike_sheet_contract.md` and canonical
machine contract `docs/northwind_jeremy_pike_sheet_contract.v1.json`. Preserve
Jeremy-first route ordering, stable-ID evidence, atomic checkpoint recovery,
complete company blocks, source provenance, and all exact formatting rules.

Before any edit to the `Prasath Nanayakkara` tab, also read and follow the
dedicated human contract
`docs/northwind_prasath_nanayakkara_sheet_contract.md` and canonical machine
contract `docs/northwind_prasath_nanayakkara_sheet_contract.v1.json`. Preserve
Prasath-first route ordering, stable-ID evidence, atomic checkpoint recovery,
complete company blocks, source provenance, and all exact formatting rules.

Before any edit to the `Former Clients` tab, also read and follow the dedicated
human contract `docs/northwind_former_clients_sheet_contract.md` and canonical
machine contract `docs/northwind_former_clients_sheet_contract.v1.json`.
Preserve the published 1BT relationship register, named-seed restrictions,
propensity-only language, target-specific mutual-route evidence, complete
company blocks, stable-ID checkpoints, source provenance, insertion marker,
premium summary, and all exact formatting rules. The tab is not a source for
the existing `Search` formula.
