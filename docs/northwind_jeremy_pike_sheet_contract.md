# Northwind `Jeremy Pike` sheet contract

Version: **1.0.0**

Established and live-verified: **2026-07-22**

Canonical machine-readable contract:
[`northwind_jeremy_pike_sheet_contract.v1.json`](northwind_jeremy_pike_sheet_contract.v1.json)

Parent workbook contract:
[`northwind_warm_paths_sheet_contract.md`](northwind_warm_paths_sheet_contract.md)

This is the mandatory schema and formatting contract for the `Jeremy Pike`
tab in the Google Sheet `Northwind CRM Warm Paths Tracker`. It describes the
current live tab exactly and defines how future agents and people must edit it.
The machine-readable JSON is normative where a colour, width, cell value, range,
or validation rule needs exact representation.

## Purpose and boundary

The tab is a separate company-grouped relationship tracker for the **60**
CTO-type contacts returned by the live Sales Navigator filter **Connections of
Jeremy Pike** in Paul Fryer's verified LinkedIn session.

- Spreadsheet ID: `1nikwNWJ3N5622S_a8l9YQsP_pTLxCLtmezgNmBq4abs`
- Tab: `Jeremy Pike`
- Sheet ID: `959287179`
- Tab index: `3`
- Grid: `1,294` rows × `26` columns (`A:Z`)
- Controlled structure: `A1:Y129`
- Company data: `A6:Y113`
- Reserved blank column: `Z`
- Native structural template: `Sam Dharmasiri` (sheet ID `1390832825`)
- The tab is independent of `Search`, `Warm Paths`, and `Sam Dharmasiri`.
- It is not included in the `Search!A8` formula.

## Non-negotiable rules

1. Keep every company in one contiguous row block. Never scatter one company
   across separate parts of the tab.
2. Each company block contains all target-person rows first and exactly one
   company-summary row last.
3. Every target person is unique by stable LinkedIn lead ID, not merely by
   display name or result position.
4. `Mutual 1` is always exactly `Jeremy Pike`. Up to four additional named
   mutuals may follow in Mutuals 2–5.
5. Record an additional mutual only when the person's name was visible in
   Paul Fryer's live Sales Navigator session. A mutual-count badge is not a
   named route.
6. Never infer a hidden employer, title, location, name, route, or other field.
   Use the explicit privacy sentinel when LinkedIn hides the employer.
7. Every target row has the exact Current Stage dropdown. Company-summary rows
   have no dropdown and are blank from `D:Y`.
8. Source/provenance in `X` is mandatory and remains plain text. Names and
   source text are never hyperlink-underlined.
9. Every populated row is wrapped and top-aligned. Rows `6:129` are fitted to
   their content; taller readable rows are preferred to clipping.
10. Never force populated rows to `21 px`, and never autofit or restyle the
    complete sheet.
11. The permanent new-company marker remains directly below the final company
    block. Never overwrite, delete, or place company data below it.
12. A data-boundary change must update the marker, summary, banding, conditional
    formatting, snapshot counts, metrics, and both contracts together.
13. Create a dated complete-workbook backup before any value, format, formula,
    validation, row, column, banding, merge, or dimension edit.
14. Preserve all user-entered notes, comments, and CRM progress exactly unless
    the user explicitly asks to change them.
15. `Search`, `Warm Paths`, and `Sam Dharmasiri` must remain unchanged
    during a Jeremy-tab edit.

## Current controlled snapshot

| Measure | Required current value |
| --- | ---: |
| Unique target people / stable lead IDs | 60 |
| Company blocks | 48 |
| Target rows | 60 |
| Company-summary rows | 48 |
| Total data rows | 108 |
| Primary Jeremy routes | 60 |
| Additional named-mutual placements | 132 |
| Total named-route placements | 192 |
| Distinct additional mutuals | 66 |
| Targets with an additional mutual | 33 |
| Privacy-limited targets | 3 |
| Duplicate lead IDs | 0 |
| Company-block violations | 0 |

The privacy-limited targets are valerie wragg, Kelvin Forrester, and Tony
Coleman. Their employers were not displayed, so the company value is `Company
not shown on Sales Navigator`; no employer was inferred.

These are snapshot values, not permanent business limits. An authorized data
addition may change them, but all derived text, row boundaries, and contract
values must be updated in the same controlled change.

## Row layout

| Rows | Role | Required treatment |
| --- | --- | --- |
| 1 | Title | `A1:Y1` merged |
| 2 | Usage instruction | `A2:Y2` merged |
| 3 | Snapshot line | `A3:Y3` merged |
| 4 | Spacer | Blank |
| 5 | Headers | `A5:Y5`; premium teal rendered header |
| 6–113 | Company blocks | 60 target rows plus 48 final summary rows |
| 114 | Permanent insertion marker | `A114:Y114` merged; add complete new blocks immediately above |
| 115 | Spacer | Blank |
| 116 | Network-summary title | `A116:C116` merged |
| 117 | Executive summary | `A117:C117` merged |
| 118 | Summary headers | `A118:C118` |
| 119–128 | Ten summary metrics | `A:C` only |
| 129 | Usage guidance | `A129:C129` merged |
| 130–1294 | Unused grid | Blank, white, `21 px` |

The only allowed merged ranges are:

- `A1:Y1`
- `A2:Y2`
- `A3:Y3`
- `A114:Y114`
- `A116:C116`
- `A117:C117`
- `A129:C129`

## Row-height rules

| Rows | Height rule |
| --- | --- |
| 1–4 | Fixed at `20 px` |
| 5 | Fixed at `42 px` |
| 6–129 | `FIT_TO_DATA`; wrapped content determines height |
| 130–1294 | Fixed at `21 px` because these rows are unused and blank |

After changing wrapped text, run `autoResizeDimensions` only on the affected
populated rows. Inspect the native Google-rendered result. Do not assign one
fixed height across the data or summary regions.

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

Do not autofit these columns. Changing a width requires a reviewed schema
version because it affects the deliberately balanced premium layout.

## Header and column schema

The headers in `A5:Y5`, in order, are:

| Column | Exact header | Target-person rule | Company-summary rule |
| --- | --- | --- | --- |
| A | Company | Required live employer, or the exact privacy sentinel | Same company as the block |
| B | Target Person | Required live display name | Positive integer target count |
| C | Target Role | Required source-bound role, company, location, tenure and visible context | Block-level target and route summary |
| D | Mutual 1 | Required exact value `Jeremy Pike` | Blank |
| E | Mutual 1 Notes | Required Jeremy-route evidence note | Blank |
| F | Mutual 2 | Optional named live mutual | Blank |
| G | Mutual 2 Notes | Required if F is populated; otherwise blank | Blank |
| H | Mutual 3 | Optional named live mutual | Blank |
| I | Mutual 3 Notes | Required if H is populated; otherwise blank | Blank |
| J | Mutual 4 | Optional named live mutual | Blank |
| K | Mutual 4 Notes | Required if J is populated; otherwise blank | Blank |
| L | Mutual 5 | Optional named live mutual | Blank |
| M | Mutual 5 Notes | Required if L is populated; otherwise blank | Blank |
| N | Current Stage | Required validated dropdown | Blank and unvalidated |
| O | Found Route Notes | Required current route-depth note | Blank |
| P | Mutual Friend Contact Notes | Optional workflow note | Blank |
| Q | Intro Requested Notes | Optional workflow note | Blank |
| R | Intro Agreed Notes | Optional workflow note | Blank |
| S | Target Contacted Notes | Optional workflow note | Blank |
| T | Meeting / Reply Notes | Optional workflow note | Blank |
| U | Won Notes | Optional workflow note | Blank |
| V | Dead / No Route Notes | Optional workflow note | Blank |
| W | Final Notes | Optional; preserve user text exactly | Blank |
| X | Source / Profile | Required live-DOM provenance, Sales Navigator HTTPS lead URL and capture time | Blank |
| Y | CRM Status | Optional status text | Blank |
| Z | Reserved blank spacer | Always blank | Always blank |

### Target-role rule

Column `C` records only visible source data. Its preferred sequence is:

`Current title at current company / Location / role and company tenure / visible profile context`

Omit a missing component rather than inventing it. Do not rewrite a source-bound
role into a more commercially attractive title.

### Company-summary rule

The last row of each company block uses:

- `A`: exact company name;
- `B`: count of target rows immediately above it in that block;
- `C`: count of Jeremy-connected CTO-type contacts, statement that Jeremy is Mutual 1
  for every target, and the total additional named-route placements retained;
- `D:Y`: blank;
- no dropdown validation.

Singular and plural wording must be grammatically correct. The summary count
must reconcile with the target rows; it is not an approximate label.

## Company ordering and insertion

The version 1.0.0 snapshot is alphabetical by normalized company display name,
with `Company not shown on Sales Navigator` last. Target people are alphabetical
within each company.

The permanent marker is the controlled entry point for a genuinely new company:

1. Insert enough rows immediately above the marker for every target person plus
   exactly one summary row.
2. Copy a native target row for each target and a native company-summary row for
   the final row; never use a values-only append.
3. Clear all copied row-specific values before populating the intended fields.
4. Keep the block complete and contiguous.
5. Existing blocks are never split. Any later reordering must move complete
   blocks and be reviewed separately.

For a new target at an existing company, insert the target row immediately
before that company's summary row, then update that summary.

## Mutual-route schema

- `D/E` is the required Jeremy route and its evidence note.
- `F/G`, `H/I`, `J/K`, and `L/M` are optional additional named routes and notes.
- Maximum named routes per target: **5**, including Jeremy.
- A mutual name must not repeat within one target row.
- A note must not exist without its paired name.
- The same named mutual may legitimately route to multiple targets.
- A badge such as “83 mutual connections” does not authorize 83 route names.
- If Jeremy is not in the first visible mutuals-panel slice, the active
  `Connections of Jeremy Pike` filter remains the primary route evidence and
  that exact limitation is stated in `E`.

## Source and checkpoint schema

Every target row has a plain-text `X` value containing:

1. `LinkedIn Sales Navigator live DOM`;
2. an `https://www.linkedin.com/sales/lead/...` URL containing the stable lead
   ID;
3. an ISO-8601 capture timestamp.

Long collections are recoverable by design:

- write every completed contact, or a very small bounded batch, atomically to
  the local evidence checkpoint;
- key entries by stable LinkedIn lead ID;
- persist the source filter/page context and extracted mutual-route payload;
- treat browser memory and page numbering as disposable;
- after interruption, validate the disk checkpoint and collect only missing
  stable IDs because LinkedIn may reorder results between page loads.

The version 1.0.0 evidence is stored in
`Evidence/2026-07-22_jeremy-pike-60`. The complete pre-edit workbook backup is
Google Sheet `1aG3MH2UUnCfh6x6HyNla91hdap5Pnt83R0CYmg9tc-8`. This backup is
the comparison authority for `Search`, `Warm Paths`, and `Sam Dharmasiri`.

## Current Stage validation

Column `N` on all and only target-person rows uses one native dropdown with
`showCustomUi: true`. The allowed values and spelling are fixed:

1. `Found route`
2. `Mutual friend to contact`
3. `Intro requested`
4. `Intro agreed`
5. `Target contacted`
6. `Meeting / reply`
7. `Won`
8. `Dead / no route`

The current default is `Found route`. Summary rows, the insertion marker, the
summary table, and blank rows must not carry this validation.

## Formula rule

The tab currently has **zero formula cells**. Target data, company summaries,
the snapshot line, and the network-summary values are reviewed literal
snapshots. Do not introduce a formula without a deliberate schema-version and
dependency review. When data changes, recalculate every affected literal metric
and explanatory sentence in the same controlled batch.

## Formatting rules

### Global typography and alignment

- Font family: `Carlito` throughout the controlled region.
- Normal body size: `11 pt`.
- Names, target text and source text: never underlined.
- Hyperlink display: plain text; do not restore browser-like link styling.
- Data cells: wrap, top-align and use `3 px` left/right padding as rendered.
- Horizontal body alignment: left, except summary counts and metric values.

### Colour palette

| Use | Colour |
| --- | --- |
| Navy summary title / key text | `#1F2937` |
| Burgundy header / labels | `#7A1730` |
| Marker burgundy | `#771630` |
| Effective themed header teal | `#156082` |
| Alternating data blue | `#C1E4F5` |
| White | `#FFFFFF` |
| Insertion-marker gold | `#F3E8D5` |
| Warm summary grey | `#F8F3EF` |
| Body grey | `#444F59` |
| Standard summary border | `#D7DCE1` |
| Company-summary bottom border | `#E0DBD6` |
| Emphasis blue | `#EAF3F8` |
| Guidance grey | `#F5F7F8` |
| Guidance top border | `#AEB6BF` |
| “Already” status green | `#E8F5E9` |
| “needs” status orange | `#FFF7ED` |

### Title and header rows

- `A1:Y1`: merged; white; Carlito 16 bold; black; left; bottom; overflow.
- `A2:Y2`: merged; white; Carlito 10 italic; black; left; bottom; overflow.
- `A3:Y3`: merged; white; Carlito 10 bold; black; left; bottom; overflow.
- `A4:Y4`: blank white spacer.
- `A5:Y5`: Carlito 11 white bold; centred; middle-aligned; wrapped.
  The underlying user-entered fill is burgundy `#7A1730`; the live themed
  effective header is teal `#156082`. Preserve both layers.

### Data rows

- Banding range: exactly `A5:Y113`.
- Banded range ID at capture: `388272600`.
- First band: blue `#C1E4F5`.
- Second band: white `#FFFFFF`.
- Target rows: Carlito 11 regular; left; top; wrapped; no underline.
- Company-summary `A`: bold navy, left, top, wrapped.
- Company-summary `B`: bold burgundy, centred, top, wrapped.
- Company-summary `C`: grey, left, top, wrapped.
- Company-summary `A:C`: bottom border `#E0DBD6`.
- Company-summary `D:Y`: blank and unvalidated.

### CRM-status conditional formatting

Two rules, in this order, cover exactly `Y6:Y113`:

1. `=ISNUMBER(SEARCH("Already",Y6))` → `#E8F5E9`
2. `=ISNUMBER(SEARCH("needs",Y6))` → `#FFF7ED`

When the data region grows, both rule ranges end at the new final company-data
row. Do not add a whole-column rule.

### Permanent insertion marker

`A114:Y114` is merged, gold `#F3E8D5`, Carlito 11 bold, burgundy
`#771630`, left-aligned, middle-aligned and wrapped. It has thick burgundy top
and bottom borders. Its visible text and cell note are controlled structure.

### Premium network summary

- `A116:C116`: merged navy `#1F2937`; white Carlito 16 bold; left; middle.
- `A117:C117`: merged warm grey `#F8F3EF`; grey Carlito 11 italic; left; top.
- `A118:C118`: burgundy `#7A1730`; white Carlito 11 bold; centred; middle.
- `A119:C127`: alternating white and `#F8F3EF`; grey borders; top; wrapped.
- `A119:A128`: bold burgundy metric names, left.
- `B119:B128`: bold navy values, centred.
- `C119:C128`: grey explanations, left.
- `A128:C128`: emphasis blue `#EAF3F8` with a thick burgundy bottom border.
- `A129:C129`: merged guidance grey `#F5F7F8`; Carlito 10 italic; grey;
  thick `#AEB6BF` top border.
- `D116:Y129`: blank white cells.

All rows `116:129` remain content-fitted rather than using copied fixed pixel
heights.

## Fixed text and summary metrics

The exact title, instruction, snapshot, marker, summary heading, executive
statement, ten metric rows, and usage guidance are controlled in the JSON
contract. The summary metric order is fixed:

1. Portfolio coverage
2. Target people
3. Primary warm route
4. Additional route depth
5. Network breadth
6. Multi-route coverage
7. Relationship volume
8. Contact density
9. Data quality
10. Research caveat

Current calculations:

- Relationship volume: `60 + 132 = 192` named route placements.
- Average relationship volume: `192 / 60 = 3.20` per target.
- Contact density: `60 / 48 = 1.25` targets per company.
- Multi-route coverage: target rows with at least one name in `F/H/J/L`.
- Network breadth: distinct normalized names in `F/H/J/L`, excluding Jeremy.

The summary is not a manually worded approximation. It must reconcile with the
validated target rows after every data change.

## Safe edit procedure

1. Read this document, its JSON contract, and both parent Warm Paths contracts.
2. Create a dated Drive copy of the complete workbook.
3. Read live metadata and the exact affected CellData, including formats and
   data validation.
4. If collecting LinkedIn data, validate the stable-ID checkpoint before the
   first write.
5. Plan the complete company-block change, including the summary row.
6. Insert rows; do not overwrite the marker or append below it.
7. Copy native target and summary structures separately, then clear stale values
   and write only planned content.
8. Update validation on target rows only.
9. Move the data boundary, banding, conditional ranges, marker, spacer and
   network summary together.
10. Recalculate `A3`, the executive statement and all ten metrics.
11. Auto-resize only affected populated rows.
12. Re-read values, formats, validation, dimensions, merges, banding and
    conditional rules.
13. Verify stable-ID uniqueness, contiguous blocks, summary counts, Jeremy-first
    routes, paired notes, source provenance and blank reserved regions.
14. Compare non-targeted tabs and cells with the pre-edit backup.
15. Inspect the native Google-rendered tab at normal zoom.
16. Save verification evidence and hashes under `Evidence`, then version both
    the dedicated and parent contracts if the snapshot or structure changed.

## Prohibited shortcuts

- Values-only append.
- Whole-sheet sort, autofit, restyle, or format normalization.
- Sorting people without company-block semantics.
- Splitting a company block.
- Copying a summary row as a target row or vice versa.
- Data below the insertion marker.
- Dropdown validation on summary rows.
- Mutual notes without their mutual names.
- Mutual names inferred from counts, initials, images, or other ambiguous cues.
- Synthetic or guessed profile details.
- Resume from a stale page number without reconciling stable IDs.
- Browser-memory-only progress tracking.
- Hyperlink-style underlining.
- Uniform `21 px` populated rows.
- Formulas, native tables, filters, charts, protected ranges, or smart chips
  without a reviewed schema change.
- Incidental changes to `Search`, `Warm Paths`, or `Sam Dharmasiri`.

## Completion checklist

An edit is complete only when all of these pass:

- live metadata still resolves sheet ID `959287179`, title `Jeremy Pike`,
  `1,294` rows and `26` columns;
- every stable lead ID is unique;
- each company is one contiguous block ending in one reconciling summary row;
- every target has Jeremy in `D`, a valid stage in `N`, route notes in `O`, and
  source proof in `X`;
- mutual-name/note pairs are valid and unique per row;
- summary rows are blank and unvalidated from `D:Y`;
- the banding, conditional rules, merges, widths and height policies match;
- there are no formula cells;
- the insertion marker and summary remain immediately after company data;
- no text is clipped or unintentionally underlined in native rendering;
- non-targeted workbook content matches the dated backup;
- the verification report and hashes are stored under `Evidence`.

## Unsupported structures

The tab intentionally has no native table, basic filter, chart, protected
range, smart chip, or spreadsheet formula. Adding any of these is a schema
change, not a routine content edit.

## Schema history

- **1.0.0 — 2026-07-22:** Established the standalone complete schema and
  formatting contract from live metadata, live CellData, the verified
  60-contact evidence set, and the exact construction requests.
