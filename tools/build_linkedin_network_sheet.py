"""Build validated Google Sheets batch requests for a LinkedIn network tab.

The input is the atomic Sales Navigator checkpoint produced by the
linkedin-mutual-contact-routes workflow.  The script never talks to Google or
LinkedIn; it only validates evidence and writes deterministic request plans.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

EXPECTED_STAGE_VALUES = (
    "Found route",
    "Mutual friend to contact",
    "Intro requested",
    "Intro agreed",
    "Target contacted",
    "Meeting / reply",
    "Won",
    "Dead / no route",
)
PRIVACY_SENTINEL = "Company not shown on Sales Navigator"
SHEET_COLUMNS = 25


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _normal(value: str) -> str:
    return " ".join(value.split()).casefold()


def _cell(value: str | int | float | None = None) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, bool):
        raise TypeError("Boolean values are not valid network-sheet cells")
    if isinstance(value, (int, float)):
        return {"userEnteredValue": {"numberValue": value}}
    return {"userEnteredValue": {"stringValue": value}}


def _row(values: list[str | int | float | None]) -> dict[str, Any]:
    if len(values) != SHEET_COLUMNS:
        raise ValueError(f"Expected {SHEET_COLUMNS} values, got {len(values)}")
    return {"values": [_cell(value) for value in values]}


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def _role_text(record: dict[str, Any]) -> str:
    pieces: list[str] = []
    title = record["title"]
    company = record["company"]
    if company == PRIVACY_SENTINEL:
        pieces.append(title)
    else:
        pieces.append(f"{title} at {company}")
    if record.get("location"):
        pieces.append(f"Location: {record['location']}")
    if record.get("tenure"):
        pieces.append(record["tenure"])
    if record.get("about"):
        pieces.append(f"Profile context: {record['about']}")
    if company == PRIVACY_SENTINEL:
        pieces.append(
            "Data note: Current employer was not displayed in the visible Sales "
            "Navigator result card; no company was inferred."
        )
    return " / ".join(pieces)


def _primary_note(primary_name: str, visible: bool) -> str:
    note = (
        "Primary named route. This target appears in the live Sales Navigator "
        f"filter “Connections of {primary_name}”."
    )
    if not visible:
        note += (
            f" {primary_name.split()[0]} was not in the first visible slice of "
            "the mutuals panel, so the filtered result set is the route evidence."
        )
    return note


def _found_route_note(record: dict[str, Any], primary_name: str) -> str:
    count = int(record.get("mutualCount", 0))
    if count:
        noun = _plural(count, "mutual connection")
        return (
            f"{primary_name} is the primary route. Sales Navigator showed "
            f"{count} {noun}; this sheet retains {primary_name.split()[0]} plus "
            "up to four additional named mutuals."
        )
    return (
        f"The filtered result set establishes {primary_name} as the primary "
        "route. Sales Navigator did not display a mutual-count button for this "
        "first-degree result, so no additional named mutuals were recorded."
    )


def _target_values(record: dict[str, Any], primary_name: str) -> list[Any]:
    mutuals = list(record["mutuals"])
    additional = mutuals[1:5]
    values: list[Any] = [
        record["company"],
        record["name"],
        _role_text(record),
        primary_name,
        _primary_note(primary_name, bool(record.get("primaryVisibleInPanel"))),
    ]
    for index in range(4):
        if index < len(additional):
            values.extend(
                [
                    additional[index],
                    "Additional named mutual connection visible to Paul Fryer.",
                ]
            )
        else:
            values.extend(["", ""])
    values.extend(
        [
            "Found route",
            _found_route_note(record, primary_name),
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            f"LinkedIn Sales Navigator live DOM | {record['profileUrl']} | "
            f"captured {record['capturedAt']}",
            "",
        ]
    )
    return values


def _summary_values(
    company: str, records: list[dict[str, Any]], primary_name: str
) -> list[Any]:
    target_count = len(records)
    if company == PRIVACY_SENTINEL:
        summary = (
            f"{target_count} privacy-limited {_plural(target_count, 'result')} "
            "did not display a current employer. Keep this block separate until "
            "a verified employer is available; no company was inferred."
        )
    else:
        additional_count = sum(len(record["mutuals"][1:5]) for record in records)
        summary = (
            f"{target_count} {primary_name.split()[0]}-connected CTO-type "
            f"{_plural(target_count, 'contact')} captured from the live result "
            f"set. Mutual 1 is {primary_name} on every target row; "
            f"{additional_count} additional named route "
            f"{_plural(additional_count, 'placement')} retained."
        )
    return [company, target_count, summary, *("" for _ in range(22))]


def _validate_checkpoint(
    checkpoint: dict[str, Any], primary_name: str
) -> list[dict[str, Any]]:
    if not primary_name.strip():
        raise ValueError("Primary route name must not be blank")
    records_by_id = checkpoint.get("records")
    if not isinstance(records_by_id, dict):
        raise ValueError("Checkpoint records must be an object keyed by lead ID")
    source = checkpoint.get("source", {})
    if not isinstance(source, dict):
        raise ValueError("Checkpoint source must be an object")
    filters = source.get("filters")
    required_filter = f"Connections of {primary_name}"
    if not isinstance(filters, list) or required_filter not in filters:
        raise ValueError(f"Checkpoint does not prove the {required_filter} filter")
    if source.get("signedInIdentity") != "Paul Fryer":
        raise ValueError("Checkpoint does not prove the verified Paul Fryer identity")
    if not records_by_id:
        raise ValueError("Checkpoint contains no lead records")
    records: list[dict[str, Any]] = []
    expected = int(source.get("reportedResultCount", 0))

    seen_ids: set[str] = set()
    required = ("leadId", "name", "company", "title", "profileUrl", "capturedAt")
    for checkpoint_id, source_record in records_by_id.items():
        if not isinstance(source_record, dict):
            raise ValueError(f"Checkpoint entry {checkpoint_id!r} must be an object")
        record = dict(source_record)
        missing = [
            key
            for key in required
            if not isinstance(record.get(key), str) or not record[key].strip()
        ]
        if missing:
            raise ValueError(f"Record is missing required fields {missing}: {record!r}")
        lead_id = str(record["leadId"])
        if str(checkpoint_id) != lead_id:
            raise ValueError(
                f"Checkpoint key {checkpoint_id!r} does not match lead ID {lead_id!r}"
            )
        if lead_id in seen_ids:
            raise ValueError(f"Duplicate lead ID: {lead_id}")
        seen_ids.add(lead_id)
        mutuals = record.get("mutuals")
        if not isinstance(mutuals, list) or not mutuals or mutuals[0] != primary_name:
            raise ValueError(
                f"{lead_id} does not start with primary route {primary_name}"
            )
        if any(not isinstance(name, str) or not name.strip() for name in mutuals):
            raise ValueError(f"{lead_id} contains a blank or non-text mutual name")
        if len(mutuals) > 5:
            raise ValueError(f"{lead_id} has more than five retained mutuals")
        if len({_normal(name) for name in mutuals}) != len(mutuals):
            raise ValueError(f"{lead_id} repeats a mutual name")
        profile_url = record["profileUrl"]
        parsed_url = urlsplit(profile_url)
        lead_path = parsed_url.path.removeprefix("/sales/lead/")
        url_lead_id = lead_path.split(",", 1)[0]
        if (
            parsed_url.scheme != "https"
            or parsed_url.netloc != "www.linkedin.com"
            or not parsed_url.path.startswith("/sales/lead/")
            or url_lead_id != lead_id
        ):
            raise ValueError(f"{lead_id} has an invalid Sales Navigator URL")
        try:
            captured_at = datetime.fromisoformat(
                record["capturedAt"].replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError(f"{lead_id} has an invalid capture timestamp") from exc
        if captured_at.tzinfo is None:
            raise ValueError(f"{lead_id} has a timezone-naive capture timestamp")
        mutual_count = record.get("mutualCount", 0)
        if (
            isinstance(mutual_count, bool)
            or not isinstance(mutual_count, int)
            or mutual_count < 0
        ):
            raise ValueError(f"{lead_id} has an invalid mutual count")
        legacy_visibility_key = f"{primary_name.split()[0].casefold()}VisibleInPanel"
        record["primaryVisibleInPanel"] = bool(
            record.get(
                "primaryVisibleInPanel",
                record.get(
                    legacy_visibility_key, record.get("jeremyVisibleInPanel", False)
                ),
            )
        )
        records.append(record)
    if expected and len(records) != expected:
        raise ValueError(f"Checkpoint has {len(records)} records; expected {expected}")
    return records


def _build_data(
    records: list[dict[str, Any]], primary_name: str
) -> tuple[list[list[Any]], list[int], dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[record["company"]].append(record)
    ordered_companies = sorted(
        groups,
        key=lambda company: (company == PRIVACY_SENTINEL, _normal(company)),
    )

    rows: list[list[Any]] = []
    summary_row_numbers: list[int] = []
    current_row = 6
    for company in ordered_companies:
        company_records = sorted(
            groups[company], key=lambda item: _normal(item["name"])
        )
        rows.extend(_target_values(record, primary_name) for record in company_records)
        current_row += len(company_records)
        rows.append(_summary_values(company, company_records, primary_name))
        summary_row_numbers.append(current_row)
        current_row += 1

    additional = [name for record in records for name in list(record["mutuals"])[1:5]]
    privacy_records = [
        record for record in records if record["company"] == PRIVACY_SENTINEL
    ]
    stats = {
        "contact_count": len(records),
        "unique_lead_id_count": len({record["leadId"] for record in records}),
        "company_block_count": len(ordered_companies),
        "company_summary_row_count": len(ordered_companies),
        "data_row_count": len(rows),
        "primary_route_count": len(records),
        "additional_mutual_placement_count": len(additional),
        "distinct_additional_mutual_count": len({_normal(name) for name in additional}),
        "total_named_route_placement_count": len(records) + len(additional),
        "contacts_with_additional_mutuals": sum(
            bool(record["mutuals"][1:5]) for record in records
        ),
        "privacy_limited_contact_count": len(privacy_records),
        "privacy_limited_names": [record["name"] for record in privacy_records],
        "duplicate_lead_id_count": 0,
        "duplicate_name_count": len(records)
        - len({_normal(record["name"]) for record in records}),
        "blank_company_count": 0,
        "blank_target_count": 0,
        "blank_role_count": 0,
        "company_block_violation_count": 0,
    }
    return rows, summary_row_numbers, stats


def _structural_requests(
    sheet_id: int,
    template_sheet_id: int,
    summary_rows: list[int],
    data_last_row: int,
    old_data_last_row: int,
    total_grid_rows: int,
) -> list[dict[str, Any]]:
    if not 5 <= data_last_row <= old_data_last_row < total_grid_rows:
        raise ValueError(
            "Expected 5 <= data_last_row <= old_data_last_row < total_grid_rows"
        )
    removed = old_data_last_row - data_last_row
    requests: list[dict[str, Any]] = []
    if removed < 0:
        raise ValueError(
            "This builder currently expects the new network tab to be smaller"
        )
    if removed:
        requests.extend(
            [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": data_last_row,
                            "endIndex": old_data_last_row,
                        }
                    }
                },
                {
                    "appendDimension": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "length": removed,
                    }
                },
            ]
        )
    requests.extend(
        [
            {
                "copyPaste": {
                    "source": {
                        "sheetId": template_sheet_id,
                        "startRowIndex": 5,
                        "endRowIndex": 6,
                        "startColumnIndex": 0,
                        "endColumnIndex": SHEET_COLUMNS,
                    },
                    "destination": {
                        "sheetId": sheet_id,
                        "startRowIndex": 5,
                        "endRowIndex": data_last_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": SHEET_COLUMNS,
                    },
                    "pasteType": "PASTE_FORMAT",
                    "pasteOrientation": "NORMAL",
                }
            },
            {
                "copyPaste": {
                    "source": {
                        "sheetId": template_sheet_id,
                        "startRowIndex": 5,
                        "endRowIndex": 6,
                        "startColumnIndex": 0,
                        "endColumnIndex": SHEET_COLUMNS,
                    },
                    "destination": {
                        "sheetId": sheet_id,
                        "startRowIndex": 5,
                        "endRowIndex": data_last_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": SHEET_COLUMNS,
                    },
                    "pasteType": "PASTE_DATA_VALIDATION",
                    "pasteOrientation": "NORMAL",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 5,
                        "endRowIndex": data_last_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": SHEET_COLUMNS,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "verticalAlignment": "TOP",
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": (
                        "userEnteredFormat.verticalAlignment,"
                        "userEnteredFormat.wrapStrategy"
                    ),
                }
            },
        ]
    )
    for row_number in summary_rows:
        row_index = row_number - 1
        requests.extend(
            [
                {
                    "copyPaste": {
                        "source": {
                            "sheetId": template_sheet_id,
                            "startRowIndex": 8,
                            "endRowIndex": 9,
                            "startColumnIndex": 0,
                            "endColumnIndex": SHEET_COLUMNS,
                        },
                        "destination": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_index,
                            "endRowIndex": row_index + 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": SHEET_COLUMNS,
                        },
                        "pasteType": "PASTE_FORMAT",
                        "pasteOrientation": "NORMAL",
                    }
                },
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_index,
                            "endRowIndex": row_index + 1,
                            "startColumnIndex": 13,
                            "endColumnIndex": 14,
                        }
                    }
                },
            ]
        )
    return requests


def _content_requests(
    sheet_id: int,
    data_rows: list[list[Any]],
    stats: dict[str, Any],
    primary_name: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    data_last = 5 + len(data_rows)
    marker = data_last + 1
    spacer = marker + 1
    summary_title = spacer + 1
    executive = summary_title + 1
    summary_header = executive + 1
    first_metric = summary_header + 1
    final_metric = first_metric + 9
    guidance = final_metric + 1

    first = primary_name.split()[0]
    average_routes = stats["total_named_route_placement_count"] / stats["contact_count"]
    density = stats["contact_count"] / stats["company_block_count"]
    privacy_names = ", ".join(stats["privacy_limited_names"])
    duplicate_name_count = stats["duplicate_name_count"]
    data_quality_meaning = (
        "Zero duplicate lead IDs, duplicate names, blank titles, or blank company "
        "labels."
        if duplicate_name_count == 0
        else (
            f"{duplicate_name_count} repeated display-name labels were retained "
            "because their stable LinkedIn lead IDs are distinct; required fields "
            "and company blocks still reconcile."
        )
    )
    metrics = [
        [
            "Portfolio coverage",
            f"{stats['company_block_count']} companies",
            (
                "Every company is represented by one contiguous block; the "
                "privacy-limited profiles are kept in one explicit "
                "company-not-shown block."
            ),
        ],
        [
            "Target people",
            f"{stats['contact_count']} people",
            (
                f"All {stats['contact_count']} live Sales Navigator results are "
                "retained once, keyed by unique LinkedIn lead ID."
            ),
        ],
        [
            "Primary warm route",
            f"{stats['primary_route_count']} of {stats['contact_count']}",
            f"{primary_name} is Mutual 1 for every target contact.",
        ],
        [
            "Additional route depth",
            f"{stats['additional_mutual_placement_count']} links",
            (
                f"Named mutual-route placements beyond {first}, retained up to "
                "the five-column sheet limit."
            ),
        ],
        [
            "Network breadth",
            f"{stats['distinct_additional_mutual_count']} people",
            (
                "Distinct additional mutual contacts visible to Paul Fryer, "
                f"excluding {first}."
            ),
        ],
        [
            "Multi-route coverage",
            f"{stats['contacts_with_additional_mutuals']} contacts",
            (
                f"{stats['contacts_with_additional_mutuals']} targets have at "
                f"least one additional named mutual beyond {first}."
            ),
        ],
        [
            "Relationship volume",
            f"{stats['total_named_route_placement_count']} links",
            (
                f"Average {average_routes:.2f} named route placements per "
                f"target, including {first}."
            ),
        ],
        [
            "Contact density",
            f"{density:.2f} per company",
            (
                f"{stats['contact_count']} target people across "
                f"{stats['company_block_count']} company blocks."
            ),
        ],
        [
            "Data quality",
            f"{stats['unique_lead_id_count']} unique IDs",
            data_quality_meaning,
        ],
        [
            "Research caveat",
            f"{stats['privacy_limited_contact_count']} profiles",
            (
                f"Employer was not displayed for {privacy_names}; the sheet "
                "records that limitation instead of inferring a company."
            ),
        ],
    ]

    top_values = [
        f"Northwind CRM Warm Paths Tracker — {primary_name}",
        (
            "One row per target person. Companies stay in contiguous blocks; "
            f"Mutual 1 is always {primary_name}, followed by up to four "
            "additional named mutuals visible to Paul Fryer."
        ),
        (
            f"Current {first} network tracker: {stats['company_block_count']} "
            f"companies | {stats['contact_count']} target people | "
            f"{stats['total_named_route_placement_count']} named route "
            "placements | live Sales Navigator DOM research"
        ),
    ]
    marker_text = (
        "NEW COMPANY INSERTION POINT — Insert every complete new "
        f"{first}-connected company block immediately above this row. Keep each "
        "company contiguous; never overwrite or delete this marker."
    )
    marker_note = (
        "Permanent insertion marker. Add each new company as one complete "
        "contiguous block immediately above this row, then update the data "
        "boundary, banding, conditional formatting, summary positions, totals, "
        "and contracts together."
    )
    executive_text = (
        f"{stats['contact_count']} unique CTO-type contacts are grouped into "
        f"{stats['company_block_count']} contiguous company blocks. {first} is "
        "the primary warm route on every target row, with "
        f"{stats['additional_mutual_placement_count']} additional named route "
        "placements retained for wider introduction options."
    )

    requests: list[dict[str, Any]] = [
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 3,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "rows": [
                    {"values": [_cell(top_values[0])]},
                    {"values": [_cell(top_values[1])]},
                    {"values": [_cell(top_values[2])]},
                ],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 5,
                    "endRowIndex": data_last,
                    "startColumnIndex": 0,
                    "endColumnIndex": SHEET_COLUMNS,
                },
                "rows": [_row(values) for values in data_rows],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": marker - 1,
                    "endRowIndex": marker,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "rows": [
                    {
                        "values": [
                            {
                                "userEnteredValue": {"stringValue": marker_text},
                                "note": marker_note,
                            }
                        ]
                    }
                ],
                "fields": "userEnteredValue,note",
            }
        },
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": summary_title - 1,
                    "endRowIndex": summary_title,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "rows": [{"values": [_cell(f"{primary_name} Network Summary")]}],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": executive - 1,
                    "endRowIndex": executive,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "rows": [{"values": [_cell(executive_text)]}],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": summary_header - 1,
                    "endRowIndex": final_metric,
                    "startColumnIndex": 0,
                    "endColumnIndex": 3,
                },
                "rows": [
                    {
                        "values": [
                            _cell("Metric"),
                            _cell("Value"),
                            _cell("Commercial meaning"),
                        ]
                    },
                    *[
                        {"values": [_cell(name), _cell(value), _cell(meaning)]}
                        for name, value, meaning in metrics
                    ],
                ],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": guidance - 1,
                    "endRowIndex": guidance,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "rows": [
                    {
                        "values": [
                            _cell(
                                "How to use: prioritise the strongest role fit "
                                "and warmest route, update Current Stage as "
                                "outreach progresses, and keep route-specific "
                                "notes beside the corresponding named mutual."
                            )
                        ]
                    }
                ],
                "fields": "userEnteredValue",
            }
        },
        {
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 5,
                    "endIndex": guidance,
                }
            }
        },
    ]
    boundaries = {
        "data_start_row": 6,
        "data_last_row": data_last,
        "marker_row": marker,
        "spacer_row": spacer,
        "summary_title_row": summary_title,
        "executive_row": executive,
        "summary_header_row": summary_header,
        "first_metric_row": first_metric,
        "final_metric_row": final_metric,
        "guidance_row": guidance,
        "unused_start_row": guidance + 1,
    }
    return requests, boundaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--primary-name", required=True)
    parser.add_argument("--sheet-id", type=int, required=True)
    parser.add_argument("--template-sheet-id", type=int, default=1390832825)
    parser.add_argument("--old-data-last-row", type=int, default=280)
    parser.add_argument("--total-grid-rows", type=int, default=1294)
    args = parser.parse_args()

    checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    records = _validate_checkpoint(checkpoint, args.primary_name)
    matrix, summary_rows, stats = _build_data(records, args.primary_name)
    data_last_row = 5 + len(matrix)
    structural = _structural_requests(
        args.sheet_id,
        args.template_sheet_id,
        summary_rows,
        data_last_row,
        args.old_data_last_row,
        args.total_grid_rows,
    )
    content, boundaries = _content_requests(
        args.sheet_id, matrix, stats, args.primary_name
    )

    if len(matrix) != stats["contact_count"] + stats["company_block_count"]:
        raise AssertionError("Data row count does not reconcile")
    if boundaries["data_last_row"] != data_last_row:
        raise AssertionError("Computed data boundary does not reconcile")

    output = args.output_dir
    _atomic_json(output / "sales-navigator-dom-evidence.json", checkpoint)
    _atomic_json(output / "sales-navigator-validation.json", stats)
    _atomic_json(output / "expected-data-matrix.compact.json", matrix)
    _atomic_json(output / "sheet-structural-requests.json", {"requests": structural})
    _atomic_json(output / "sheet-content-requests.compact.json", {"requests": content})
    _atomic_json(
        output / "sheet-plan.json",
        {
            "primary_name": args.primary_name,
            "sheet_id": args.sheet_id,
            "template_sheet_id": args.template_sheet_id,
            "stats": stats,
            "boundaries": boundaries,
            "summary_row_numbers": summary_rows,
            "stage_values": list(EXPECTED_STAGE_VALUES),
            "structural_request_count": len(structural),
            "content_request_count": len(content),
        },
    )

    for path in sorted(output.glob("*.json")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{digest}  {path.name}")


if __name__ == "__main__":
    main()
