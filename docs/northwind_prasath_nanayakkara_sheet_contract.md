# Northwind `Prasath Nanayakkara` sheet contract

Version: **1.0.0**

Established and live-verified: **2026-07-23**

Canonical machine-readable contract:
[`northwind_prasath_nanayakkara_sheet_contract.v1.json`](northwind_prasath_nanayakkara_sheet_contract.v1.json)

Parent workbook contract:
[`northwind_warm_paths_sheet_contract.md`](northwind_warm_paths_sheet_contract.md)

This is the mandatory schema and formatting contract for the
`Prasath Nanayakkara` tab in `Northwind CRM Warm Paths Tracker`. The JSON
contract is normative for exact values, ranges, colours, widths, validation,
evidence and verification requirements.

## Purpose and boundary

The tab is a separate, company-grouped relationship tracker for the **20**
CTO-type contacts returned by the live Sales Navigator filters
**Connections of Prasath Nanayakkara** and **CTO Type** in Paul Fryer's
verified LinkedIn session.

- Spreadsheet ID: `1nikwNWJ3N5622S_a8l9YQsP_pTLxCLtmezgNmBq4abs`
- Tab: `Prasath Nanayakkara`
- Sheet ID: `2114113563`
- Tab index: `4`
- Grid: `1,294` rows × `26` columns (`A:Z`)
- Controlled structure: `A1:Y60`
- Company data: `A6:Y44`
- Reserved blank column: `Z`
- Native structural template: `Sam Dharmasiri` (sheet ID `1390832825`)
- The tab is independent of `Search`, `Warm Paths`, `Sam Dharmasiri`, and
  `Jeremy Pike`.
- It is not included in the `Search!A8` formula.

## Non-negotiable rules

1. Keep every company in one contiguous block. Never scatter one company.
2. Each block contains all target rows first and exactly one company-summary
   row last.
3. Identify targets by stable LinkedIn lead ID, not display name or result
   position.
4. `Mutual 1` is always exactly `Prasath Nanayakkara`.
5. Up to four additional mutuals may follow only when their names were visible
   in Paul Fryer's live Sales Navigator panel.
6. Never infer a hidden employer, role, location, mutual name or other fact.
7. Every target row has the exact Current Stage dropdown. Summary rows have no
   dropdown and are blank from `D:Y`.
8. `X` must retain plain-text live-DOM provenance, Sales Navigator lead URL,
   and capture time. Do not display names or sources as underlined hyperlinks.
9. Every populated row is wrapped, vertically top-aligned and fitted to its
   content. Taller readable rows are preferred to clipping.
10. Never force populated rows to `21 px`; unused blank rows may remain `21 px`.
11. The permanent insertion marker remains directly below the final company
    block. Insert complete future company blocks immediately above it.
12. A boundary change must update banding, conditional formatting, marker,
    summary positions, counts, metrics and both contracts together.
13. Create a dated complete-workbook backup before every sheet edit.
14. Preserve user notes, comments and CRM progress exactly unless the user
    explicitly asks to change them.
15. A Prasath-tab edit must not alter any earlier tab.
16. Write every completed LinkedIn contact immediately to an atomic local
    checkpoint keyed by stable lead ID. Resume from missing IDs, never a
    remembered page number.

## Current controlled snapshot

| Measure | Required current value |
| --- | ---: |
| Unique target people / stable lead IDs | 20 |
| Company blocks | 19 |
| Target rows | 20 |
| Company-summary rows | 19 |
| Total data rows | 39 |
| Primary Prasath routes | 20 |
| Additional named-mutual placements | 44 |
| Total named-route placements | 64 |
| Distinct additional mutuals | 25 |
| Targets with an additional mutual | 17 |
| Privacy-limited targets | 0 |
| Duplicate lead IDs | 0 |
| Duplicate display names | 0 |
| Company-block violations | 0 |

These are controlled snapshot values, not permanent business limits. An
authorized addition may change them only when every dependent value, range and
contract is updated in the same controlled change.

## Row layout

| Rows | Role | Required treatment |
| --- | --- | --- |
| 1 | Title | `A1:Y1` merged |
| 2 | Usage instruction | `A2:Y2` merged |
| 3 | Snapshot line | `A3:Y3` merged |
| 4 | Spacer | Blank |
| 5 | Headers | `A5:Y5`; premium rendered header |
| 6–44 | Company blocks | 20 target rows plus 19 final summary rows |
| 45 | Permanent insertion marker | `A45:Y45` merged |
| 46 | Spacer | Blank |
| 47 | Network-summary title | `A47:C47` merged |
| 48 | Executive summary | `A48:C48` merged |
| 49 | Summary headers | `A49:C49` |
| 50–59 | Ten summary metrics | `A:C` only |
| 60 | Usage guidance | `A60:C60` merged |
| 61–1294 | Unused grid | Blank |

The only allowed merged ranges are `A1:Y1`, `A2:Y2`, `A3:Y3`, `A45:Y45`,
`A47:C47`, `A48:C48`, and `A60:C60`.

## Row-height rules

| Rows | Height rule |
| --- | --- |
| 1–4 | Fixed at `20 px` |
| 5 | Fixed at `42 px` |
| 6–60 | `FIT_TO_DATA`; wrapped content determines height |
| 61–1294 | Fixed at `21 px` because the rows are blank and unused |

After changing wrapped text, auto-resize only affected populated rows and
inspect the native rendered result. Do not assign one fixed height to the data
or summary regions.

## Column widths

| Column(s) | Width |
| --- | ---: |
| A | 191 px |
| B | 191 px |
| C | 335 px |
| D | 175 px |
| E | 191 px |
| F | 175 px |
| G | 191 px |
| H | 175 px |
| I | 191 px |
| J | 175 px |
| K | 191 px |
| L | 175 px |
| M | 191 px |
| N | 159 px |
| O–T | 223 px each |
| U | 175 px |
| V | 66 px |
| W | 271 px |
| X | 239 px |
| Y | 223 px |
| Z | 68 px; reserved blank spacer |

Never autofit these columns. Width changes require a reviewed schema version.

## Header and column schema

The exact headers in `A5:Y5` are:

| Column | Exact header | Target-person rule | Company-summary rule |
| --- | --- | --- | --- |
| A | Company | Required visible employer | Same company as the block |
| B | Target Person | Required visible display name | Positive integer target count |
| C | Target Role | Visible role, company, location, tenure and context only | Reconciled block summary |
| D | Mutual 1 | Exact value `Prasath Nanayakkara` | Blank |
| E | Mutual 1 Notes | Required primary-route evidence | Blank |
| F | Mutual 2 | Optional named live mutual | Blank |
| G | Mutual 2 Notes | Required iff F is populated | Blank |
| H | Mutual 3 | Optional named live mutual | Blank |
| I | Mutual 3 Notes | Required iff H is populated | Blank |
| J | Mutual 4 | Optional named live mutual | Blank |
| K | Mutual 4 Notes | Required iff J is populated | Blank |
| L | Mutual 5 | Optional named live mutual | Blank |
| M | Mutual 5 Notes | Required iff L is populated | Blank |
| N | Current Stage | Required native dropdown | Blank and unvalidated |
| O | Found Route Notes | Required current route-depth note | Blank |
| P | Mutual Friend Contact Notes | Optional workflow note | Blank |
| Q | Intro Requested Notes | Optional workflow note | Blank |
| R | Intro Agreed Notes | Optional workflow note | Blank |
| S | Target Contacted Notes | Optional workflow note | Blank |
| T | Meeting / Reply Notes | Optional workflow note | Blank |
| U | Won Notes | Optional workflow note | Blank |
| V | Dead / No Route Notes | Optional workflow note | Blank |
| W | Final Notes | Optional; preserve user text exactly | Blank |
| X | Source / Profile | Required live-DOM provenance, HTTPS lead URL and capture time | Blank |
| Y | CRM Status | Optional status text | Blank |
| Z | Reserved blank spacer | Always blank | Always blank |

Column `C` omits missing components instead of inventing them. A company-summary
row uses the company in `A`, the target count in `B`, a reconciled block
statement in `C`, blanks in `D:Y`, and no validation.

## Company ordering and insertion

Companies are alphabetical by normalized display name. Targets are alphabetical
within a company. The current ranges are:

| Company | Rows |
| --- | --- |
| 1218 Global | 6–7 |
| Asha Securities Ltd | 8–9 |
| Ashfords LLP | 10–11 |
| Aurora Energy Research | 12–13 |
| CloudTech24 | 14–15 |
| E-Designers Pvt Ltd | 16–17 |
| Eutech | 18–19 |
| experienz | 20–21 |
| Fiyorla | 22–23 |
| London Technology Club | 24–25 |
| LSEG | 26–27 |
| Platned | 28–29 |
| Salocin Group | 30–31 |
| Saïd Business School, University of Oxford | 32–33 |
| Seer 365 | 34–36 |
| Tech Mahindra | 37–38 |
| Uniphar Group | 39–40 |
| VirtusaPolaris | 41–42 |
| ZeroBeta | 43–44 |

For a new company, insert all target rows plus one summary row immediately above
row 45, copy native target and summary structures separately, clear copied
row-specific data, populate the complete block, and then reposition all
dependent controlled regions. For an existing company, insert a target directly
before that company's summary row.

## Mutual-route and source schema

- `D/E` is the required Prasath route and evidence note.
- `F/G`, `H/I`, `J/K`, and `L/M` are optional named routes and paired notes.
- Maximum named routes per target: **5**, including Prasath.
- A name cannot repeat within one target row.
- A note cannot exist without its paired name.
- A visible mutual-count badge does not authorize unnamed routes.
- If Prasath is not in the first loaded mutual-panel slice, the active
  `Connections of Prasath Nanayakkara` filter is the primary evidence and `E`
  records that limitation.

Every target row's plain-text `X` value contains:

1. `LinkedIn Sales Navigator live DOM`;
2. an `https://www.linkedin.com/sales/lead/...` URL with the stable lead ID;
3. an ISO-8601 capture timestamp.

Collection evidence is stored under
`Evidence/2026-07-23_prasath-nanayakkara-20`. Each completed contact was written
atomically to `sales-navigator-checkpoint.json`. The pre-edit comparison
authority is Google Sheet
`16Ng7KRnZL1Ti2vbKBLt0bxnxeh4pkQwnYHkztep0ByA`.

## Current Stage validation and formulas

All and only target rows use one native dropdown in `N`, with
`showCustomUi: true` and this exact order:

1. `Found route`
2. `Mutual friend to contact`
3. `Intro requested`
4. `Intro agreed`
5. `Target contacted`
6. `Meeting / reply`
7. `Won`
8. `Dead / no route`

The current default is `Found route`. The tab has **zero formula cells**. All
snapshot values are reviewed literals and must be recalculated together after a
data change.

## Formatting rules

- Font: Carlito throughout; normal body size `11 pt`.
- Data cells: left, top, wrapped; no hyperlink-style underlining.
- Header `A5:Y5`: white bold centred Carlito 11, middle-aligned and wrapped;
  preserve both the burgundy user-entered layer `#7A1730` and teal themed
  effective layer `#156082`.
- Data banding: exactly `A5:Y44`, first band `#C1E4F5`, second band white.
- Target rows: Carlito 11 regular; company-summary `A` is bold navy, `B` bold
  burgundy and centred, `C` grey, with `D:Y` blank.
- Conditional rules cover exactly `Y6:Y44`, in this order:
  `=ISNUMBER(SEARCH("Already",Y6))` → `#E8F5E9`;
  `=ISNUMBER(SEARCH("needs",Y6))` → `#FFF7ED`.
- Marker `A45:Y45`: gold `#F3E8D5`, burgundy bold text, wrapped, middle,
  with thick burgundy top and bottom borders and the controlled cell note.
- Summary `A47:C47`: navy `#1F2937`, white Carlito 16 bold.
- Executive row `A48:C48`: warm grey `#F8F3EF`, grey italic Carlito 11.
- Headers `A49:C49`: burgundy, white bold centred Carlito 11.
- Metrics `A50:C59`: alternating white/warm grey; burgundy bold labels, navy
  bold centred values, grey meanings; row 59 uses blue emphasis and a thick
  burgundy bottom border.
- Guidance `A60:C60`: grey `#F5F7F8`, Carlito 10 italic, thick grey top border.
- `D47:Y60` is blank white.

## Fixed summary

The exact order is Portfolio coverage, Target people, Primary warm route,
Additional route depth, Network breadth, Multi-route coverage, Relationship
volume, Contact density, Data quality, Research caveat.

Current calculations:

- Relationship volume: `20 + 44 = 64` named route placements.
- Average route volume: `64 / 20 = 3.20` per target.
- Contact density: `20 / 19 = 1.05` targets per company.
- Research caveat: `0 profiles`; no employer names were privacy-limited.

The summary must reconcile with validated target rows; it is not approximate
free text.

## Safe edit procedure

1. Read this contract, its JSON contract and both parent contracts.
2. Create a dated complete-workbook Drive copy.
3. Read live metadata and exact affected CellData.
4. Validate the stable-ID evidence checkpoint before any write.
5. Plan complete company blocks and dependent controlled ranges.
6. Insert above the marker; never overwrite it or append below it.
7. Copy native target and summary structures separately and write only planned
   values.
8. Keep validation on target rows only.
9. Move data boundary, banding, conditional rules, marker, spacer and summary
   together.
10. Recalculate the snapshot, executive statement and all ten metrics.
11. Auto-resize only affected populated rows.
12. Re-read values, formats, validation, dimensions, merges, banding and rules.
13. Verify stable IDs, contiguous blocks, summary counts, Prasath-first routes,
    paired notes, source provenance and blank reserved regions.
14. Compare every non-targeted tab with the dated backup.
15. Inspect the native Google-rendered tab at normal zoom.
16. Save verification evidence and update both contract versions.

## Prohibited shortcuts

No values-only append; whole-sheet sort, autofit or restyle; split company
blocks; copied summary rows used as target rows; data below the marker;
validation on summary rows; notes without paired names; inferred mutuals or
profile facts; resume by remembered page; browser-memory-only progress;
underlined names; uniform `21 px` populated rows; formulas, native tables,
filters, charts, protected ranges or smart chips without a reviewed schema
change; or incidental edits to earlier tabs.

## Completion checklist

An edit is complete only when sheet ID `2114113563`, title, index, grid size,
unique lead IDs, company blocks, summary counts, Prasath-first routes, dropdowns,
route notes, source proof, blank summary cells, blank `Z`, marker, premium
summary, banding, conditional rules, widths, height policy and native rendering
all pass; non-targeted workbook content matches the dated backup; and evidence
plus hashes are stored under `Evidence`.

## Unsupported structures

The tab intentionally has no native table, basic filter, chart, protected
range, smart chip or spreadsheet formula.

## Schema history

- **1.0.0 — 2026-07-23:** Established the complete schema from the verified
  20-contact Sales Navigator evidence, exact construction requests, live
  CellData, native rendering, and full non-targeted-tab backup comparison.
