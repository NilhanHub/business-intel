# Source Recovery Design

Project: Business_Intel / sl_trigger_leads  
Scope: PROMPT#05 source recovery for public-source lead intelligence

## Purpose

Source recovery is a best-effort component for configured public sources that return 404, 403, timeout, DNS failure, SSL error, parse error, or an unknown fetch failure.

It is not magic and it does not create leads. A recovered URL can only be used for a live run if it fetches successfully and appears relevant to the configured source.

## Components

- `sl_trigger_leads/tools/source_health.py`
  - `classify_failure(fetch_result)` maps fetch failures to stable failure types.
  - `test_source_url(url, search_terms, timeout_seconds)` politely checks candidate URLs and returns status plus relevance.

- `sl_trigger_leads/tools/source_recovery.py`
  - `recover_source_url(failed_source, failure_context)` tests candidate public URLs and returns a transparent recovery result.

- `sl_trigger_leads/tools/source_fetcher.py`
  - Integrates recovery into the live fetch flow.
  - Records configured URL, effective URL, fetch status, failure reason, recovery attempt, recovered URL, and recovery note.

## Recovery Strategy

For a failed source, recovery tries:

1. Known canonical candidates from the registry.
2. Source-specific candidates, including CSE announcements routes.
3. Domain root and progressively stripped path candidates.
4. `sitemap.xml` and `robots.txt` as diagnostic public resources.

For CSE, the current preferred route is:

`https://www.cse.lk/announcements`

The previous known-bad route is retained only as history and test input:

`https://www.cse.lk/pages/company-announcements/company-announcements.component.html`

## Recovery Result Shape

`recover_source_url` returns:

- `source_id`
- `source_name`
- `failed_url`
- `failure_type`
- `recovery_attempted`
- `candidate_urls`
- `selected_replacement_url`
- `recovery_status`
- `note_for_user`

## Safety Rules

- Do not silently replace registry URLs.
- Do not treat a candidate as usable unless it returns HTTP 200 and has relevant content.
- Do not scrape LinkedIn.
- Do not require paid APIs.
- Do not invent leads from recovery diagnostics.
- Show failures and recovery notes in source coverage metadata.
