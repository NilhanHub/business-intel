# Source Transparency Policy

Project: Business_Intel / sl_trigger_leads  
Scope: PROMPT#05 public-source lead intelligence behavior

## Policy

Configured public source names and URLs are discloseable.

When a user asks where the app looks, which websites it scans, which URLs it checks, or asks to show configured sources, the agent must use `list_configured_sources(include_urls=True)` and show the public registry entries.

The agent must not say that public source URLs are confidential. It may only withhold a source detail if a future registry entry contains credentials, private configuration, or a non-public endpoint. The current registry contains only public web sources.

## Required Source Fields

Each configured source should expose:

- `source_name`
- `source_type`
- `base_url` or `fetch_url`
- `enabled`
- `notes`
- `limitations`
- `last_fetch_status` when available

## Runtime Lead Rule

Every returned lead must remain traceable to public evidence:

- `evidence_url`
- `evidence_excerpt`
- `source_name`
- `fetched_at`
- `verified_live: true`

If those fields are missing, the record must be blocked and not returned as a lead.

## No Simulation Fallback

The app must not fall back to synthetic leads, sample companies, fake URLs, `example.test`, or simulated evidence. If no live evidence is found, the correct response is:

`No verified live leads found.`

## Failure Disclosure

Source fetch failures, partial runs, and recovery attempts must be shown to the user instead of hidden. A 404 means the configured resource was not found; it may be a moved path, typo, changed site route, or dead page.
