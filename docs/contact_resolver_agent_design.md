# Contact Resolver Agent Design

## 1. Role-First Contact Resolution

The Contact Resolver Agent resolves the best defensible outreach route for a
specific verified lead or opportunity. It is not an "email finder." It starts
with the likely buyer/persona for the 1BT service bucket, then looks for a
reachable public contact route.

For example, a QE/API hiring signal maps first to engineering, QA, integration,
delivery, and CTO personas. A generic inbox is only a fallback after the likely
buyer route is identified.

## 2. Search Layers

The resolver is built around a pluggable public search provider interface:

- `search_web(query, limit)`
- `fetch_page(url)`
- `extract_emails(text)`
- `extract_people_roles(text, company, target_personas)`

The intended search layers are:

- Company identity normalization.
- Official company pages: website, about, team, leadership, contact, careers,
  press/news, footer contact details, and domain email hints.
- Public professional evidence available without login, including search
  snippets and public URLs.
- Email discovery from public official pages, public job posts, public press
  releases, and public professional pages.

For PROMPT#10, live web search is disabled by default. If no provider is
configured, the resolver reports `search_provider_not_configured` and does not
invent contacts.

## 3. Persona Mapping

The deterministic persona map covers these 1BT buckets:

- Staff Augmentation / Delivery Capacity
- Custom Software Development
- AI Apps / AI Workflow Automation
- AI Strategy Consulting
- Data Analytics & AI
- Microsoft Dynamics 365 / CRM / Power Platform
- Integrations / API / Middleware
- QA / Test Automation
- Managed IT / Application Support

Each bucket maps to prioritized buyer personas with explicit relevance notes.
The resolver merges primary and secondary bucket personas while preserving
priority order.

## 4. Confidence Scoring

The resolver uses a transparent 100-point score:

- Named person with relevant role: +30
- Exact bucket/persona match: +20
- Official company source confirms person/role: +20
- Public professional source confirms person/company: +10
- Public named email: +20
- Generic company inbox: capped at 45
- Inferred email pattern: capped at 70
- Role mismatch: -20
- Evidence over 24 months old: -15
- Ambiguous company identity: -30
- No email but strong named route: capped at 75
- No named person: capped at 45

Confidence labels are High for 80-100, Medium for 55-79, Low for 1-54, and
No usable contact for 0.

## 5. Stopping Rules

The resolver is timeboxed per lead:

- Stop after a named role-relevant contact with public named email and
  confidence >= 80.
- Stop after a named role-relevant contact route and confidence >= 70.
- Stop after 8 targeted queries and 5 pages.
- Stop after 90 seconds.
- Stop after 3 consecutive credible searches produce no new evidence.
- Stop when only a generic route is available after the budget.

The output returns the best available route instead of looping forever.

## 6. Compliance Guardrails

Every result includes:

- Use only for targeted B2B outreach.
- Do not bulk send.
- Use truthful subject and sender.
- Include opt-out/unsubscribe wording where applicable.
- Respect suppression list once implemented.
- Do not contact personal/private emails.

Named work contacts can still be personal data in many privacy regimes. Generic
department inboxes are different from named individual contact data. Any future
outreach must be approval-gated.

## 7. Generic Emails Are Fallback Only

Generic inboxes like `info@`, `contact@`, `careers@`, or `hr@` can be useful
when no named buyer route is found, but they are not the preferred route. The
resolver caps generic inbox confidence at 45 and labels them as fallback routes.

## 8. Future Draft Writer Connection

The next component should be a draft-only writer that consumes:

- Lead evidence URL
- 1BT service bucket
- Buyer persona
- Best contact route
- Do-not-claim guardrails

It should create a draft for human approval only. It should not send.

## 9. Sending Remains Locked

The Contact Resolver Agent does not import or call the Gmail sender. It cannot
send emails, cannot unlock lead outreach, and cannot bulk contact anyone. If
asked to send, it returns:

`No. Contact Resolver only resolves contact routes. Sending to leads is still locked.`

## 10. Future Paid Enrichment Options

Optional provider hooks are present but disabled by default:

- Google Programmable Search / Custom Search style provider
- SerpAPI-like provider
- Hunter/Apollo/RocketReach/Cognism/Dropcontact style enrichment provider
- Email verifier provider

These require explicit configuration and should remain off unless approved.

