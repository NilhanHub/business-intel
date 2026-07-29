# Northwind `Former Clients` sheet contract

Version: **2.0.0**

Established: **2026-07-28**

Last verified: **2026-07-28**

This document and
`docs/northwind_former_clients_sheet_contract.v1.json` are the normative schema
for the `Former Clients` tab in the **Northwind CRM Warm Paths Tracker**. The
machine contract controls exact cells, dimensions, colours, row boundaries,
counts and evidence artifacts. This document explains the rules humans and
agents must preserve.

## Purpose and truth boundary

The tab is deliberately one workspace with two independent tables placed
side-by-side:

1. the former-client-adjacent warm-route tracker in `A:Y`; and
2. the published 1BT relationship register in `AC:AN`.

Columns `Z:AB` are a permanent blank visual gutter. The two tables may have
independent column widths and headings. The register supports the prospect
research; it is not a second prospect list.

This is **propensity-based prospecting**. A score, current role, company change
proxy or warm route is not proof of a current buying project. The phrases
`confirmed opportunity`, `active opportunity` and `verified opportunity` are
forbidden unless a later source directly proves that status and the contract is
deliberately revised.

The verified 2.0.0 snapshot contains:

- 21 published relationship records;
- seven named seed clients;
- eight anonymized archetypes;
- 11 UK/Ireland prospect companies;
- 25 current senior target people, all with at least one named route;
- 41 target-to-mutual route placements;
- 34 distinct mutual introducers;
- three companies with five distinct introducers;
- zero cross-tab company matches; and
- scores from 61 to 95.

The tracker is expandable. It is not capped at ten companies. The deterministic
builder accepts one to 100 complete prospect blocks and derives all row
boundaries and summary totals from the validated evidence.

## Published relationship register

Every published 1BT item is consolidated into one stable record. The register
uses `AC:AN`:

| Column | Field |
| --- | --- |
| AC | Stable record ID |
| AD | Published client or case label |
| AE | Relationship type |
| AF | Identity confidence |
| AG | Seed eligible (`Yes` or `No`) |
| AH | Industry |
| AI | Geography |
| AJ | Delivered services |
| AK | Technologies |
| AL | Published engagement evidence |
| AM | Aliases or identity notes |
| AN | Every retained source URL |

Allowed relationship types are `direct client`, `testimonial client`,
`delivery partner`, `1BT product`, `anonymized case`, `non-direct/PoC`, and
`ambiguous`.

Only a high-confidence `direct client` or `testimonial client` may be a named
former-client seed. Products such as MillionSpaces, delivery partners,
ambiguous items, PoCs and anonymized cases are not former clients. Anonymous
case identities must never be guessed. They remain service/industry archetypes
only.

Duplicate client names and aliases must be consolidated while retaining every
published source URL. A build with any unresolved named-identity duplicate
must fail before a sheet write.

## Prospect selection contract

Every selected account must:

- be a current UK or Ireland company and not itself a former client or a
  former-client subsidiary/group account;
- have a defensible current-employee link to one named seed-eligible former
  client;
- have official service-fit evidence;
- score at least 55 out of 100 under the fixed four-part model;
- contain one to five current eligible senior target people;
- give every retained target at least one named, target-specific mutual route
  visibly proven in Paul Fryer's live LinkedIn session; and
- retain no more than five distinct named introducers across its complete
  company block.

The account territory, alumnus anchor and current operating link must support a
UK or Ireland route. A global executive may be retained when that person owns a
company-wide product, technology, delivery or operational function affecting
the UK/Ireland account. The person's actual location remains explicit; no local
location is inferred.

The score is fixed:

- service/industry similarity: 35;
- former-client people link: 30;
- verified warm-route depth: 20; and
- buying-committee quality and observable change proxies: 15.

The four components must add exactly to the stored total. A vague mutual count
is never a name. A person appears in a mutual column only when a live
introducer panel, shared-connection result, or explicit `Connections of
<name>` result visibly proves the route for that exact target.

Eligible target authority is C-suite, President, VP, Director, Head, Partner,
Owner or equivalent founding leadership for technology, engineering, digital,
enterprise applications, Dynamics/ERP/CRM, security, infrastructure,
operations or relevant procurement. Junior staff, recruiters, unrelated sales
roles, former employees and unverified employers are excluded.

Reliable saved evidence may be cross-referenced with the live session, company
website, earlier workbook tabs, CRM, email or reputable public sources. Every
fact must retain its provenance. Saved evidence never substitutes for live
verification of a target's current role and named route.

## Prospect row schema

The tracker uses the established `A:Y` company-block schema:

| Columns | Purpose |
| --- | --- |
| A | Company |
| B | Target person; integer target count on company-summary row |
| C | Current role/context; full anchor, score and service-fit narrative on summary row |
| D/F/H/J/L | Target-specific named mutuals 1–5 |
| E/G/I/K/M | Evidence note paired with the preceding mutual |
| N | Current Stage dropdown on every target row |
| O–W | Route, relationship and stage notes |
| X | Live source/profile provenance |
| Y | CRM status |

Each company is one contiguous block. Target rows come first and exactly one
company-summary row comes last. Columns `D:Y` are blank on a company-summary
row. The summary narrative must contain:

- the former-client anchor and alumnus relationship;
- the exact four-component score;
- concise official service-fit reasoning;
- the explicit `not a confirmed opportunity` boundary; and
- the cross-tab match status.

Target rows carry the current employer, title, location, visible current-role
evidence, stable LinkedIn identifier, live profile URL, capture timestamp,
change proxy and only the named routes visible for that exact target. Unrouted
target rows are prohibited.

## Exact current layout

| Region | Role |
| --- | --- |
| `A1:Y3` | Tracker title, route-first instruction and live snapshot |
| `AC1:AN3` | Register title, classification instruction and live snapshot |
| Row 4 | Blank spacer |
| `A5:Y5` | Tracker headers |
| `AC5:AN5` | Register headers |
| `A6:Y41` | Eleven contiguous company blocks: 25 targets and 11 summaries |
| `AC6:AN26` | Twenty-one consolidated published relationship records |
| `A42:Y42` | Permanent new-prospect insertion marker |
| Row 43 | Blank spacer |
| `A44:Y58` | Premium summary: title, statement, headers, eleven metrics and guidance |
| Rows 59–1294 | Blank 21-pixel grid |
| `Z:AB` | Permanently blank visual gutter |

Current company-summary rows are `8, 12, 17, 21, 25, 27, 29, 31, 35, 38,
41`. They are derived output, not hard-coded insertion addresses.

Future complete company blocks are inserted immediately above the marker. The
builder recalculates the marker, summary, validations, conditional formats and
unused-grid start. No manual append below the marker is allowed.

## Exact presentation rules

- Grid: 1,294 rows × 40 columns; rows 1–5 frozen.
- Carlito throughout.
- Tracker title is burgundy; tracker header is teal.
- Register title is navy; register header is dark burgundy.
- Populated tracker and register rows alternate **blue, white, blue, white by
  worksheet row**. This is a row pattern, not an account-block pattern.
- All populated cells are wrapped and vertically top-aligned, except title and
  header rows that are deliberately middle-aligned.
- Populated tracker and register rows are fitted to visible wrapped content.
  Taller rows are preferred to clipped or compressed text.
- Unused rows 59–1294 are exactly 21 pixels.
- No hyperlink-style underlining is allowed anywhere.
- The target stage dropdown appears only on target rows.
- Conditional CRM-status colours apply only to `Y6:Y41`.
- Columns `Z:AB` are white, blank and 32 pixels each.
- The insertion marker uses restrained gold; the summary uses navy, burgundy,
  cream, pale blue and white.
- Summary rows preserve their normal blue/white row band and add a bottom
  border across `A:C`.

Column widths in pixels:

| Columns | Widths |
| --- | --- |
| `A:Y` | 191, 191, 335, 175, 191, 175, 191, 175, 191, 175, 191, 175, 191, 159, 223, 223, 223, 223, 223, 223, 175, 66, 271, 239, 223 |
| `Z:AB` | 32, 32, 32 |
| `AC:AN` | 90, 190, 135, 115, 95, 165, 155, 220, 200, 280, 200, 280 |

Fixed row heights in pixels:

- row 1: 42;
- row 2: 48;
- row 3: 34;
- row 4: 14;
- row 5: 42;
- marker row: 48;
- marker spacer: 14;
- summary title: 42;
- executive statement: 62;
- summary header: 36;
- each metric row: 56;
- guidance row: 62; and
- every unused row: 21.

## Recoverable evidence

Website evidence and LinkedIn work use separate local ledgers under a dated
`Evidence` folder. Collection normally uses Sales Navigator. If that surface
rate-limits a precise recovery query, standard LinkedIn in the same freshly
verified Paul Fryer session may be used for exact profiles, current employment
and named shared-connection panels.

Records are keyed by stable LinkedIn identifier and written atomically after
each completed contact. Browser memory, page number and result ordering are
disposable. A resumed run reconciles the checkpoint and collects only missing
stable IDs.

Each published record retains every source URL. Each alumni anchor and target
retains a live LinkedIn URL and timestamp. Each named target-to-mutual placement
retains visible-DOM evidence. The evidence pack contains validated inputs,
candidate decisions, expected matrices, exact batch requests, hashes,
preservation comparison and rendered inspection.

## Safe edit procedure

1. Read this contract, the machine contract and the parent workbook contract.
2. Create a dated copy of the entire workbook.
3. Reconcile website and LinkedIn ledgers by stable IDs.
4. Verify Paul Fryer's current visible LinkedIn identity.
5. Run the offline builder twice and require byte-equivalent plans.
6. Reject invalid seeds, duplicate identities, non-senior or unrouted targets,
   score mismatches, unnamed routes, former-client-family accounts and
   opportunity claims.
7. Apply one scoped batch to `Former Clients` only. Do not change `Search`.
8. Re-read the tab and reconcile every register record, target, company
   summary, route placement, score and summary metric.
9. Compare every pre-existing tab with the dated backup across values,
   formulas, notes, validations, hyperlinks, formats, dimensions, comments and
   structure.
10. Inspect the native Google Sheets renderer at normal zoom for clipping,
    banding, dropdowns, alignment, marker placement and summary quality.
11. Save exact verification results and hashes under `Evidence`.

## Prohibited shortcuts

- Using a product, partner, PoC, ambiguous item or anonymized case as a named
  former-client seed.
- Guessing an anonymized client identity.
- Treating a former-client group/subsidiary as a clean adjacent prospect.
- Treating a current role, hiring marker, investment or programme as a
  confirmed opportunity.
- Recording a mutual-count badge as a person.
- Placing a mutual name on a target for whom the route was not visible.
- Retaining any target without a named route.
- Keeping more than five distinct mutuals in one company block.
- Splitting one company across non-contiguous rows.
- Adding the tab to the existing `Search` formula.
- Writing into `Z:AB`.
- Whole-workbook formatting, autofit or opportunistic cleanup.
- Resuming from a remembered result page without reconciling the stable-ID
  checkpoint.

## Change history

- **2.0.0 — 2026-07-28:** Rebuilt the tab as a route-first side-by-side
  workspace, moved the register to `AC:AN`, required a named route on every
  target, made prospect count expandable, verified the first careful expansion
  to 11 companies, and added Olivine Development Company with one current
  senior target and three visibly named routes.
- **1.0.0 — 2026-07-28:** Established the initial vertically arranged
  relationship register and ten-company prospect tracker.
