# UK/IE D365 Northwind Sync

Google Sheet changes are governed separately by
[`northwind_warm_paths_sheet_contract.md`](northwind_warm_paths_sheet_contract.md)
and its canonical machine-readable contract. Read them before changing the
`Northwind CRM Warm Paths Tracker` workbook.

`tools/sync_uk_ie_d365_leads_to_northwind.py` imports a completed UK/Ireland
lead pack into the existing Northwind CRM company collection. It does not
create contacts, activities, routes, schemas, or outreach.

The command is intentionally pinned to project `globalapps-northwind-crm`,
database `(default)`, and workspace `default`. It requires exactly 20 unique,
verified public-web leads, refuses existing normalized company names, and
writes all companies plus one workspace revision increment in one Firestore
transaction.

Always preview first:

```powershell
uv run python tools\sync_uk_ie_d365_leads_to_northwind.py `
  --input-pack Evidence\UK_IE_D365_RUN5_20260716_20_LEADS_FINAL.json `
  --output Evidence\UK_IE_D365_RUN5_NORTHWIND_DRYRUN.json
```

Apply only after the dry run reports 20 prepared records and zero duplicates:

```powershell
uv run python tools\sync_uk_ie_d365_leads_to_northwind.py `
  --input-pack Evidence\UK_IE_D365_RUN5_20260716_20_LEADS_FINAL.json `
  --output Evidence\UK_IE_D365_RUN5_NORTHWIND_APPLIED.json `
  --apply
```

The applied audit records the before/after company counts and verifies every
inserted document. A failed transaction does not partially import the batch.

To enrich an already-imported exact batch with the complete evidence excerpt,
source verification, target roles, board relevance, caveats, and report/evidence
references, preview and then apply `--enrich-existing`:

```powershell
uv run --with google-cloud-firestore python tools\sync_uk_ie_d365_leads_to_northwind.py `
  --input-pack Evidence\UK_IE_D365_RUN5_20260716_20_LEADS_FINAL.json `
  --output Evidence\UK_IE_D365_RUN5_NORTHWIND_ENRICH_DRYRUN.json `
  --enrich-existing

uv run --with google-cloud-firestore python tools\sync_uk_ie_d365_leads_to_northwind.py `
  --input-pack Evidence\UK_IE_D365_RUN5_20260716_20_LEADS_FINAL.json `
  --output Evidence\UK_IE_D365_RUN5_NORTHWIND_ENRICH_APPLIED.json `
  --enrich-existing --apply
```

This mode requires exactly one existing CRM company per lead, updates only the
company `intel`, `updatedAt`, and `version` fields, and keeps the company count
unchanged.
