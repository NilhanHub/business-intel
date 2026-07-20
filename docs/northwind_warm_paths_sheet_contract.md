# Northwind Warm Paths spreadsheet contract

Version: **1.1.0**

Captured and repaired: **2026-07-20**

Canonical machine-readable contract: [`northwind_warm_paths_sheet_contract.v1.json`](northwind_warm_paths_sheet_contract.v1.json)

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
   formatting, Search formula coverage, Search spill capacity, footer position,
   and displayed totals together.
9. Column `Z` on `Warm Paths` is reserved and must remain blank.
10. After every edit, prove that unrelated values and user-entered formats are
    unchanged and all counts reconcile.
11. Every populated cell in `Warm Paths!A6:Y375` is vertically top-aligned.
    Populated rows are fitted to their wrapped content; clarity takes priority,
    and taller rows are preferred to clipped or compressed text.

## Workbook structure

The workbook ID is `1nikwNWJ3N5622S_a8l9YQsP_pTLxCLtmezgNmBq4abs`. Its tab
order is fixed: `Search`, then `Warm Paths`. Locale is `en_GB`; timezone is
`America/Los_Angeles`.

Current controlled snapshot:

- 70 companies in 70 contiguous blocks.
- 52 companies have target people; 18 currently have none.
- 300 unique company/target-person pairs.
- 70 company-summary rows.
- 434 target-to-mutual placements representing 194 distinct mutual people.
- 10 explicit Paul-feedback cells.

These totals describe the current version. A future authorized data addition
may change them, but every mirrored total and footer position must be updated
atomically and the contract version must be reviewed.

## `Warm Paths` layout

| Rows | Role | Required treatment |
| --- | --- | --- |
| 1 | Title | `A1:Y1` merged; Carlito 16 bold |
| 2 | Usage instruction | `A2:Y2` merged; Carlito 10 italic |
| 3 | Snapshot line | `A3:Y3` merged; Carlito 10 bold |
| 4 | Spacer | Blank |
| 5 | Headers | `A5:Y5`, effective teal `#156082`, white Carlito 11 bold, centred, wrapped, 42 px |
| 6–375 | Company blocks | Alternating blue `#C1E4F5` and white; wrapped, top-aligned, and fitted to content |
| 376–378 | Portfolio footer | Fixed dark/light summary treatment; not part of table banding |
| 379 | Preserved blank row | Blank; custom 38 px height |
| 380–1294 | Unused grid | Blank; 21 px height |

Rows 1–4 are fixed at 20 px and row 5 is fixed at 42 px. Rows 6–375 do not
have one fixed height: each row must fit its longest wrapped cell. Always use
top vertical alignment across `A:Y`, and prefer a taller readable row to clipped
or compressed content. After changing content, auto-resize only the affected
populated rows and inspect them in native Google Sheets. Never force the data
region to a blanket 21 px. Footer rows 376–378 remain 21 px, blank row 379 is
38 px, and unused rows 380–1294 remain 21 px.

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
and overflow-cell text. The portfolio footer uses dark `#1F2937` with white
text on rows 376 and 378; row 377 uses `#F8F3EF`, with a bold burgundy
`#771630` label in `A` and italic grey `#444F59` detail in `B:C`.

Exact column widths, footer cell text, colours, merged ranges, and cell-level
format rules are normative in the JSON contract.

## `Search` layout

- Grid: 400 rows × 25 columns; rows 1–7 frozen.
- Merges: `A1:Y1`, `A2:Y2`, `C3:K3`, and `C4:K4`.
- Search input: merged `C3:K3`, white with a thick `#8C1433` border.
- Header: `A7:Y7`, `#8C1433` with white bold text.
- Result area: `A8:Y400`, alternating white and `#F9F7EF`.
- `A8` is the only result formula. It must search the complete current data
  region, presently `Warm Paths!A6:Y375`.
- Search formula output must preserve all 25 source columns and must never be
  allowed to spill beyond the Search grid.

`C3` is user input and is intentionally mutable. All other labels and the `A8`
formula are controlled structure.

## Safe edit procedure

1. Read the JSON contract and this document.
2. Create a dated copy of the entire workbook.
3. Read current spreadsheet metadata and exact affected cells.
4. Build one narrowly scoped, atomic batch.
5. Move or add complete company blocks only.
6. Update dependent ranges and totals when the data boundary changes.
7. Re-read the full affected area and compare values, formulas, validation,
   user-entered formats, row/column dimensions, banding, and conditional rules.
8. Verify that the current company count (70 in version 1.1.0) is represented by
   contiguous blocks, each summary count matches, company/person pairs and
   per-row mutuals are unique, and every `PF...` value is unchanged.
9. Auto-resize only rows whose wrapped content changed; every populated row
   must show its complete content and remain vertically top-aligned.
10. Inspect the native Google-rendered sheet at normal zoom.
11. Record evidence and update the contract version only for an intentional
    schema change.

## Prohibited shortcuts

- Whole-sheet restyling or autofit.
- Forcing populated data rows to a blanket 21 px or another uniform height.
- Sorting the complete row set without company-block semantics.
- Appending values without native formats and validation.
- Copying a summary row as a target row, or vice versa.
- Editing Paul feedback for spelling, tone, punctuation, or normalization.
- Extending `Warm Paths` without extending Search and formatting dependencies.
- Replacing native formulas or dropdowns with displayed text.
