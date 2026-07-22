# Northwind Warm Paths spreadsheet contract

Version: **1.5.0**

Captured and repaired: **2026-07-20**

Last amended: **2026-07-22**

Canonical machine-readable contract: [`northwind_warm_paths_sheet_contract.v1.json`](northwind_warm_paths_sheet_contract.v1.json)

Dedicated `Sam Dharmasiri` contract:
[`northwind_sam_dharmasiri_sheet_contract.md`](northwind_sam_dharmasiri_sheet_contract.md)
and
[`northwind_sam_dharmasiri_sheet_contract.v1.json`](northwind_sam_dharmasiri_sheet_contract.v1.json)

This document is the mandatory change-control contract for the Google Sheet
`Northwind CRM Warm Paths Tracker`. Future edits must preserve this structure
unless a deliberate schema-version change is reviewed and recorded.

## Non-negotiable rules

1. Never make an unplanned value, format, formula, validation, colour, width, or
   row-height change.
2. Make a dated Drive copy of the complete workbook before every structural or
   formatting edit.
3. Keep every company in exactly one contiguous block. Never sort individual
   rows across company boundaries.
4. A company block contains all target-person rows first and exactly one company
   intelligence-summary row last.
5. Within a company carrying explicit `PF...` feedback, feedback-bearing rows
   come first. Preserve the feedback text verbatim.
6. The six feedback companies remain first, in this order: Glenveagh Properties
   plc, Audio-Technica, Uniphar Medtech, Moneypenny, Weetabix Food Company, and
   London Borough of Harrow. Remaining companies are alphabetical.
7. Do not use a values-only append. Copy complete native row structure, then
   overwrite only the intended row-specific cells.
8. Any change to the data-region boundary must update banding, conditional
   formatting, Search formula coverage, Search spill capacity, insertion-marker
   and summary positions, and displayed totals together.
9. The permanent `NEW COMPANY INSERTION POINT` marker must remain immediately
   below the final company-summary row. Insert every complete new company block
   above the marker; never overwrite, delete, or place data below it.
10. Column `Z` on `Warm Paths` is reserved and must remain blank.
11. After every edit, prove that unrelated values and user-entered formats are
    unchanged and all counts reconcile.
12. Every populated cell in `Warm Paths!A6:Y375` is vertically top-aligned.
    Populated rows are fitted to their wrapped content; clarity takes priority,
    and taller rows are preferred to clipped or compressed text.
13. `Sam Dharmasiri` is an independent network tab. It must retain exactly one
    contiguous block per company, with target rows first and exactly one summary
    row last. It must not alter `Search` or `Warm Paths`.
14. Every target row on `Sam Dharmasiri` must contain `Sam Dharmasiri` in Mutual
    1 (`D`), followed by no more than four additional named mutuals in
    `F`, `H`, `J`, and `L`. Never infer a name that was not visible in the live
    Sales Navigator evidence.
15. Sales Navigator collection must be recoverable: write each completed contact
    immediately to an atomic local evidence checkpoint keyed by stable LinkedIn
    lead ID. Treat browser memory and page numbering as disposable; after a
    pause or restart, validate the checkpoint and resume by missing stable IDs
    rather than recollecting completed contacts.
16. Before editing the `Sam Dharmasiri` tab, read and follow its dedicated human
    and machine contracts. They are normative for its exact fields, values,
    formatting, dimensions, evidence, insertion procedure, and verification.

## Workbook structure

The workbook ID is `1nikwNWJ3N5622S_a8l9YQsP_pTLxCLtmezgNmBq4abs`. Its tab
order is fixed: `Search`, `Warm Paths`, then `Sam Dharmasiri`. Locale is
`en_GB`; timezone is `America/Los_Angeles`.

Current controlled snapshot:

- 70 companies in 70 contiguous blocks.
- 52 companies have target people; 18 currently have none.
- 300 unique company/target-person pairs.
- 70 company-summary rows.
- 434 target-to-mutual placements representing 194 distinct mutual people.
- 10 explicit Paul-feedback cells.

These totals describe the current version. A future authorized data addition
may change them, but every mirrored total and insertion-marker/summary position
must be updated atomically and the contract version must be reviewed.

The independent `Sam Dharmasiri` snapshot contains:

- 149 unique Sales Navigator contacts keyed by stable LinkedIn lead ID.
- 126 companies in 126 contiguous blocks.
- 149 target rows and 126 company-summary rows, totalling 275 data rows.
- 149 primary Sam routes, 511 additional named-mutual placements, and 660 total
  named route placements.
- 207 distinct additional mutuals; 141 contacts have at least one additional
  named mutual.
- One privacy-limited contact whose employer was not visible. The tab records
  that limitation explicitly and does not infer an employer.

## `Warm Paths` layout

| Rows | Role | Required treatment |
| --- | --- | --- |
| 1 | Title | `A1:Y1` merged; Carlito 16 bold |
| 2 | Usage instruction | `A2:Y2` merged; Carlito 10 italic |
| 3 | Snapshot line | `A3:Y3` merged; Carlito 10 bold |
| 4 | Spacer | Blank |
| 5 | Headers | `A5:Y5`, effective teal `#156082`, white Carlito 11 bold, centred, wrapped, 42 px |
| 6–375 | Company blocks | Alternating blue `#C1E4F5` and white; wrapped, top-aligned, and fitted to content |
| 376 | Permanent insertion marker | `A376:Y376` merged; every new complete company block is inserted immediately above it |
| 377 | Spacer | Blank; separates company data from the executive summary |
| 378 | Summary title | `A378:C378` merged; premium dark title treatment |
| 379 | Executive summary | `A379:C379` merged; concise current portfolio position |
| 380 | Summary headers | `A380:C380`: Metric, Value, Commercial meaning |
| 381–390 | Portfolio metric table | Ten fixed current-snapshot metrics; alternating premium body treatment |
| 391 | Usage guidance | `A391:C391` merged; preserved workflow instruction |
| 392–1294 | Unused grid | Blank; 21 px height |

Rows 1–4 are fixed at 20 px and row 5 is fixed at 42 px. Rows 6–375 do not
have one fixed height: each row must fit its longest wrapped cell. Always use
top vertical alignment across `A:Y`, and prefer a taller readable row to clipped
or compressed content. After changing content, auto-resize only the affected
populated rows and inspect them in native Google Sheets. Never force the data
region to a blanket 21 px.

The insertion/summary region introduced in version 1.2.0 and retained in
version 1.3.0 uses deliberate presentation heights:
row 376 is 48 px; row 377 is 14 px; row 378 is 42 px; row 379 is 62 px;
row 380 is 36 px; rows 381–390 are 56 px; and row 391 is 56 px. Unused rows
392–1294 remain 21 px. These heights are fixed presentation rules rather than
data-row autofit rules.

The table banding range is exactly `A5:Y375`. Its active header treatment
renders teal `#156082`; the underlying user-entered header fill remains burgundy
`#7A1730`. Preserve both layers unless a reviewed schema change deliberately
replaces them. Rows alternate blue `#C1E4F5` and white. The two CRM-status
conditional rules cover `Y6:Y375`:

- text containing `Already` uses `#E8F5E9`;
- text containing `needs` uses `#FFF7ED`.

### Column contract

| Column(s) | Purpose |
| --- | --- |
| A | Company |
| B | Target Person; on a summary row, the integer target count |
| C | Target Role/context; on a summary row, evidence-grounded company intelligence |
| D/F/H/J/L | Mutual contacts 1–5 |
| E/G/I/K/M | Notes paired with mutuals 1–5 |
| N | Current Stage dropdown on all and only target-person rows |
| O–W | Stage-specific notes and final notes |
| X | Source-email or provenance text |
| Y | CRM Status |
| Z | Reserved blank spacer |

The Current Stage dropdown values are fixed: `Found route`, `Mutual friend to
contact`, `Intro requested`, `Intro agreed`, `Target contacted`, `Meeting / reply`,
`Won`, and `Dead / no route`.

All data cells `A6:Y375`, including empty cells inside a populated row, use top
vertical alignment and wrapping. Target-person rows use Carlito 11. Summary
rows use a bold dark `A`, centred bold burgundy count in `B`, grey intelligence
text in `C`, and a `#E0DBD6` bottom border. Columns `D:Y` must be blank on
summary rows.

Rows 1–3 have a white background, left alignment, bottom vertical alignment,
and overflow-cell text. The permanent insertion marker at `A376:Y376` uses
muted gold `#F3E8D5`, bold burgundy `#771630`, and thick burgundy top and bottom
borders. Its visible text is left-aligned so it remains visible at the left side
of the very wide table; the text and cell note are controlled structure.

The premium portfolio summary is confined to `A378:C391` so it remains readable
without horizontal scrolling. Row 378 uses dark navy `#1F2937` with white
Carlito 16 bold text. Row 379 uses `#F8F3EF` with italic grey `#444F59` text.
Row 380 uses burgundy `#7A1730` with centred white bold headers. Rows 381–389
alternate white and `#F8F3EF`; row 390 uses emphasis blue `#EAF3F8` and a thick
burgundy bottom border. In every metric row, column A is bold burgundy, column B
is centred bold navy, and column C is grey body text. All cells are wrapped and
top-aligned. Row 391 preserves the existing How-to-use guidance on `#F5F7F8`.
Columns `D:Y` are blank throughout the summary table.

Exact column widths, insertion/summary cell text, colours, merged ranges, and
cell-level format rules are normative in the JSON contract.

## `Sam Dharmasiri` layout

The dedicated
[`northwind_sam_dharmasiri_sheet_contract.md`](northwind_sam_dharmasiri_sheet_contract.md)
and
[`northwind_sam_dharmasiri_sheet_contract.v1.json`](northwind_sam_dharmasiri_sheet_contract.v1.json)
are the complete normative schema for this tab. The summary below is retained
only for workbook-level orientation.

This tab is a purpose-built duplicate of the `Warm Paths` native-cell template,
not an extension of the main 70-company tracker and not a source for `Search`.
Its company blocks are alphabetical; target people are alphabetical within each
block. The explicit privacy-limited company block appears last.

| Rows | Role | Required treatment |
| --- | --- | --- |
| 1 | Title | `A1:Y1` merged; names the Sam Dharmasiri tracker |
| 2 | Usage instruction | `A2:Y2` merged; defines contiguous blocks and mutual ordering |
| 3 | Snapshot line | `A3:Y3` merged; records the current live-evidence totals |
| 4 | Spacer | Blank |
| 5 | Headers | Same premium native header treatment as `Warm Paths`; `X5` is `Source / Profile` |
| 6–280 | Company blocks | 149 target rows and 126 final summary rows in 126 contiguous blocks |
| 281 | Permanent insertion marker | Add each complete future company block immediately above it |
| 282 | Spacer | Blank |
| 283 | Summary title | `A283:C283` merged; premium dark title treatment |
| 284 | Executive summary | `A284:C284` merged |
| 285 | Summary headers | `A285:C285` |
| 286–295 | Network metric table | Ten current-snapshot metrics |
| 296 | Usage guidance | `A296:C296` merged |
| 297–1294 | Unused grid | Blank |

The data banding range is exactly `A5:Y280`, alternating blue `#C1E4F5` and
white. Conditional CRM-status formatting covers `Y6:Y280`. Every populated
data-row cell is wrapped and top-aligned, and rows are fitted to their content.
Target rows alone carry the inherited Current Stage dropdown in `N`, with
`Found route` as the current value. Summary rows keep `D:Y` blank.

Mutual columns use the same pairs as `Warm Paths`: names in `D/F/H/J/L` and
paired notes in `E/G/I/K/M`. `D` is always `Sam Dharmasiri`. Each additional
mutual must be a named, live-observed Sales Navigator route; the visible mutual
count alone is not a substitute for a name.

The source proof for every target belongs in `X`. The permanent insertion
marker and compact premium summary are controlled structure. Exact fixed text,
counts, formats, conditional rules, provenance, and backup ID are normative in
the JSON contract.

## `Search` layout

- Grid: 2,000 rows × 25 columns; rows 1–7 frozen.
- Merges: `A1:Y1`, `A2:Y2`, `C3:K3`, and `C4:K4`.
- Search input: merged `C3:K3`, white with a thick `#8C1433` border.
- Header: `A7:Y7`, `#8C1433` with white bold text.
- Result area: `A8:Y2000`, alternating white and `#F9F7EF`.
- `A8` is the only result formula. It must search the complete current data
  region, presently `Warm Paths!A6:Y375`.
- Search formula output must preserve all 25 source columns and must never be
  allowed to spill beyond the Search grid. The result area has capacity for
  1,993 rows; at the version 1.3.0 snapshot of 370 data rows, 1,623 rows remain
  available for growth.

`C3` is user input and is intentionally mutable. All other labels and the `A8`
formula are controlled structure.

## Safe edit procedure

1. Read the JSON contract and this document.
   For a `Sam Dharmasiri` edit, also read both dedicated Sam contracts before
   inspecting or changing the live tab.
2. Create a dated copy of the entire workbook.
3. Read current spreadsheet metadata and exact affected cells.
4. Build one narrowly scoped, atomic batch.
5. Insert each complete new company block immediately above the permanent
   insertion marker. Move or add complete company blocks only.
6. Update dependent ranges and totals when the data boundary changes.
7. Re-read the full affected area and compare values, formulas, validation,
   user-entered formats, row/column dimensions, banding, and conditional rules.
8. Verify that the current company count (70 in version 1.3.0) is represented by
   contiguous blocks, each summary count matches, company/person pairs and
   per-row mutuals are unique, and every `PF...` value is unchanged.
9. Auto-resize only rows whose wrapped content changed; every populated row
   must show its complete content and remain vertically top-aligned.
10. Inspect the native Google-rendered sheet at normal zoom.
11. Record evidence and update the contract version only for an intentional
    schema change.

For a Sales Navigator network tab, checkpoint each completed contact atomically
before continuing. On restart, reconcile stable lead IDs against the validated
checkpoint, because live result ordering and page membership may change.

## Prohibited shortcuts

- Whole-sheet restyling or autofit.
- Forcing populated data rows to a blanket 21 px or another uniform height.
- Sorting the complete row set without company-block semantics.
- Appending values without native formats and validation.
- Copying a summary row as a target row, or vice versa.
- Editing Paul feedback for spelling, tone, punctuation, or normalization.
- Extending `Warm Paths` without extending Search and formatting dependencies.
- Overwriting, deleting, moving data below, or otherwise bypassing the permanent
  insertion marker.
- Replacing native formulas or dropdowns with displayed text.
- Resuming a Sales Navigator run from a remembered page number without first
  reconciling the validated stable-ID checkpoint.
- Treating browser memory as the authoritative collection ledger.

## Schema history

- **1.5.0 — 2026-07-22:** Added and linked the standalone complete human and
  machine schema for the `Sam Dharmasiri` tab. No live sheet values or formats
  changed.
- **1.4.0 — 2026-07-22:** Added the independent `Sam Dharmasiri` tab contract,
  its 149-contact/126-company snapshot, live-evidence mutual-route rules, and
  atomic stable-ID checkpoint/resume procedure. `Search` and `Warm Paths`
  remain unchanged.
- **1.3.0 — 2026-07-22:** Expanded Search to 2,000 rows and documented the
  content-fitted, top-aligned data-row policy.
- **1.2.0 — 2026-07-20:** Added the permanent insertion marker and premium
  portfolio summary.
