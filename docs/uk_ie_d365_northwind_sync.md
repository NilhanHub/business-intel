# UK/IE D365 Northwind Sync

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
