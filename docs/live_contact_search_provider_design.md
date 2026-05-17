# Live Contact Search Provider Design

## Purpose

PROMPT#11 upgrades the Contact Resolver Agent from dry-run contact route planning to live public-web contact resolution. The goal is practical: find the best defensible buyer/contact route quickly, preserve evidence URLs, and return a route that can later feed draft-only outreach workflows.

The resolver still never sends email and does not change the Gmail sender allowlist.

## Provider Architecture

Live search code lives in `sl_trigger_leads/tools/live_contact_search_tools.py`.

Core types:

- `SearchResult`: public search title, URL, snippet, and provider source.
- `PageFetchResult`: fetched URL, HTTP status, extracted page text, and error if any.
- `LiveSearchProvider`: protocol for `search_web(query, limit)`.
- `ADKGoogleSearchProvider`: default provider when ADK `google_search` imports successfully.
- `GoogleCSESearchProvider`: optional future fallback using `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_CX`.
- `SerpAPISearchProvider`: optional future fallback using `SERPAPI_API_KEY`.
- `RequestsPageFetcher`: public page fetcher with a contact-resolver user agent.
- `EmailExtractor`: visible email extraction only.
- `PeopleRoleExtractor`: lightweight public text role/person extraction.
- `ContactRouteResolver`: confidence-first route selector.

## ADK Google Search Pattern

The installed ADK stack supports:

```python
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
```

The repo includes `sl_trigger_leads/agents/contact_search_agent.py`, a dedicated search-only specialist agent using `google_search`. The live provider creates a fresh search-only runtime agent internally for each search call. This keeps Google Search isolated from unrelated resolver tools and avoids the ADK mixed-tool restriction observed when a search sub-agent is attached under a larger tool-using agent.

The local ADK `.env` loader strips a UTF-8 BOM and normalizes `GOOGLE_GENAI_USE_VERTEXAI=TRUE` to `true`, which was required for the live ADK search path to run cleanly.

## Search Layers

Per lead, the resolver attempts:

1. Seed fetch of the lead evidence URL.
2. Company/domain search, starting with `"<company>" official website`.
3. Role-targeted searches based on the bucket/persona map.
4. Public official-page fetches such as home, contact, careers, about, team, leadership, and news.
5. Public professional snippets/URLs from search results.

The resolver does not bypass login walls, CAPTCHAs, paywalls, robots controls, or private sources.

## Route Priority

Best route preference:

1. Named role-relevant buyer with public named business email.
2. Named role-relevant buyer with strong public contact/profile route.
3. Role or department contact route.
4. Official generic company inbox.
5. Job-post apply/contact route.
6. Official contact form.
7. `no_contact_found` only after real attempts.

Generic inboxes are allowed because they are sometimes the only visible public route, but they remain low confidence and are marked as fallback.

## Confidence

The PROMPT#10 scoring model remains active:

- Named relevant person and exact persona match increase score.
- Official company evidence increases score.
- Public named email is strongest.
- Generic official inbox is capped at low confidence.
- Inferred emails are labelled `inferred_pattern`, never verified.
- Ambiguous company identity and stale evidence reduce confidence.

## Stopping Rules

Default live budget:

- 3 leads by default, 10 hard cap.
- 10 targeted queries per lead.
- 8 fetched/inspected public URLs per lead.
- 120 seconds per lead.

The resolver stops early when a high-confidence named route is found, when the runtime/page/query budget is reached, when searches stop producing new evidence, or when only a generic practical route is available inside the budget.

## Fallback Providers

Fallback hooks are present but disabled unless environment variables are configured:

- Google Programmable Search / Custom Search JSON API: `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX`.
- SerpAPI-style provider: `SERPAPI_API_KEY`.

If ADK Google Search is unavailable and no fallback is configured, the resolver returns:

`ADK google_search unavailable in this install. Configure GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX or approve another provider.`

The missing import/error is also exposed in provider discovery and logs.

## Safety

The Contact Resolver Agent:

- Does not send email.
- Does not invoke Gmail sender tools.
- Does not unlock lead outreach.
- Does not accept arbitrary recipient input.
- Does not invent people, roles, URLs, emails, or confidence.
- Does not package local secrets or OAuth files in evidence.

The output remains draft-ready only: `Ready for draft only. Sending remains locked.`
