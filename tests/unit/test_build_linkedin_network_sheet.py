from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "tools" / "build_linkedin_network_sheet.py"
SPEC = importlib.util.spec_from_file_location("build_linkedin_network_sheet", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _record(
    lead_id: str,
    *,
    name: str,
    company: str,
    mutuals: list[str],
    **extra: object,
) -> dict[str, object]:
    return {
        "leadId": lead_id,
        "name": name,
        "company": company,
        "title": "Chief Technology Officer",
        "location": "London, United Kingdom",
        "tenure": "2 years in role",
        "about": "Visible profile context",
        "profileUrl": f"https://www.linkedin.com/sales/lead/{lead_id},NAME",
        "capturedAt": "2026-07-22T10:00:00Z",
        "mutualCount": len(mutuals),
        "mutuals": mutuals,
        **extra,
    }


def _checkpoint(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "source": {
            "reportedResultCount": len(records),
            "signedInIdentity": "Paul Fryer",
            "filters": ["Connections of Jeremy Pike", "CTO Type"],
        },
        "records": {str(record["leadId"]): record for record in records},
    }


def test_generic_primary_visibility_and_company_blocks() -> None:
    checkpoint = _checkpoint(
        [
            _record(
                "lead-b",
                name="Beta Person",
                company="Beta Ltd",
                mutuals=["Sam Dharmasiri", "Paul Fryer"],
                samVisibleInPanel=True,
            ),
            _record(
                "lead-a",
                name="Alpha Person",
                company="Alpha Ltd",
                mutuals=["Sam Dharmasiri"],
                samVisibleInPanel=False,
            ),
        ]
    )
    checkpoint["source"]["filters"] = ["Connections of Sam Dharmasiri", "CTO Type"]

    records = MODULE._validate_checkpoint(checkpoint, "Sam Dharmasiri")
    rows, summary_rows, stats = MODULE._build_data(records, "Sam Dharmasiri")

    assert [row[0] for row in rows] == [
        "Alpha Ltd",
        "Alpha Ltd",
        "Beta Ltd",
        "Beta Ltd",
    ]
    assert summary_rows == [7, 9]
    assert rows[0][3] == "Sam Dharmasiri"
    assert "first visible slice" in rows[0][4]
    assert "first visible slice" not in rows[2][4]
    assert stats["contact_count"] == 2
    assert stats["company_block_count"] == 2
    assert stats["additional_mutual_placement_count"] == 1
    assert stats["total_named_route_placement_count"] == 3


def test_validation_does_not_mutate_checkpoint_and_accepts_distinct_same_names() -> (
    None
):
    records = [
        _record(
            "lead-1",
            name="Alex Smith",
            company="One Ltd",
            mutuals=["Jeremy Pike"],
            primaryVisibleInPanel=True,
        ),
        _record(
            "lead-2",
            name="Alex Smith",
            company="Two Ltd",
            mutuals=["Jeremy Pike"],
            primaryVisibleInPanel=False,
        ),
    ]
    checkpoint = _checkpoint(records)
    original = deepcopy(checkpoint)

    validated = MODULE._validate_checkpoint(checkpoint, "Jeremy Pike")
    _, _, stats = MODULE._build_data(validated, "Jeremy Pike")

    assert checkpoint == original
    assert stats["unique_lead_id_count"] == 2
    assert stats["duplicate_name_count"] == 1


def test_prasath_primary_name_generates_prasath_first_rows_and_summary() -> None:
    record = _record(
        "lead-prasath",
        name="Target Person",
        company="Target Ltd",
        mutuals=["Prasath Nanayakkara", "Second Route"],
        primaryVisibleInPanel=True,
    )
    checkpoint = _checkpoint([record])
    checkpoint["source"]["filters"] = [
        "Connections of Prasath Nanayakkara",
        "CTO Type",
    ]

    validated = MODULE._validate_checkpoint(checkpoint, "Prasath Nanayakkara")
    rows, _, stats = MODULE._build_data(validated, "Prasath Nanayakkara")
    requests, _ = MODULE._content_requests(
        2114113563,
        rows,
        stats,
        "Prasath Nanayakkara",
    )

    assert rows[0][3] == "Prasath Nanayakkara"
    assert rows[0][5] == "Second Route"
    assert requests[0]["updateCells"]["rows"][0]["values"][0][
        "userEnteredValue"
    ]["stringValue"] == "Northwind CRM Warm Paths Tracker — Prasath Nanayakkara"
    assert requests[3]["updateCells"]["rows"][0]["values"][0][
        "userEnteredValue"
    ]["stringValue"] == "Prasath Nanayakkara Network Summary"


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda checkpoint: checkpoint["records"].update(
                {"wrong-key": checkpoint["records"].pop("lead-1")}
            ),
            "does not match lead ID",
        ),
        (
            lambda checkpoint: checkpoint["records"]["lead-1"].update(
                {"mutuals": ["Someone Else"]}
            ),
            "does not start with primary route",
        ),
        (
            lambda checkpoint: checkpoint["records"]["lead-1"].update(
                {"profileUrl": "https://example.test/fake"}
            ),
            "invalid Sales Navigator URL",
        ),
        (
            lambda checkpoint: checkpoint["records"]["lead-1"].update(
                {"mutuals": ["Jeremy Pike", ""]}
            ),
            "blank or non-text mutual",
        ),
        (
            lambda checkpoint: checkpoint["records"]["lead-1"].update(
                {"capturedAt": "not-a-time"}
            ),
            "invalid capture timestamp",
        ),
        (
            lambda checkpoint: checkpoint["records"]["lead-1"].update(
                {"mutualCount": -1}
            ),
            "invalid mutual count",
        ),
    ],
)
def test_checkpoint_rejects_invalid_evidence(mutator, message: str) -> None:
    checkpoint = _checkpoint(
        [
            _record(
                "lead-1",
                name="Target Person",
                company="Target Ltd",
                mutuals=["Jeremy Pike"],
            )
        ]
    )
    mutator(checkpoint)

    with pytest.raises(ValueError, match=message):
        MODULE._validate_checkpoint(checkpoint, "Jeremy Pike")


def test_checkpoint_requires_primary_filter_and_verified_identity() -> None:
    checkpoint = _checkpoint(
        [
            _record(
                "lead-1",
                name="Target Person",
                company="Target Ltd",
                mutuals=["Jeremy Pike"],
            )
        ]
    )
    checkpoint["source"]["filters"] = ["CTO Type"]
    with pytest.raises(ValueError, match="does not prove the Connections"):
        MODULE._validate_checkpoint(checkpoint, "Jeremy Pike")

    checkpoint["source"]["filters"] = ["Connections of Jeremy Pike", "CTO Type"]
    checkpoint["source"]["signedInIdentity"] = "Someone Else"
    with pytest.raises(ValueError, match="verified Paul Fryer"):
        MODULE._validate_checkpoint(checkpoint, "Jeremy Pike")


def test_checkpoint_rejects_empty_record_set() -> None:
    checkpoint = _checkpoint([])
    with pytest.raises(ValueError, match="no lead records"):
        MODULE._validate_checkpoint(checkpoint, "Jeremy Pike")


def test_request_boundaries_and_summary_copy_are_guarded() -> None:
    requests = MODULE._structural_requests(
        sheet_id=10,
        template_sheet_id=20,
        summary_rows=[7],
        data_last_row=7,
        old_data_last_row=280,
        total_grid_rows=1294,
    )

    assert requests[0]["deleteDimension"]["range"]["startIndex"] == 7
    assert requests[1]["appendDimension"]["length"] == 273
    summary_validations = [
        request["setDataValidation"]["range"]
        for request in requests
        if "setDataValidation" in request
    ]
    assert summary_validations == [
        {
            "sheetId": 10,
            "startRowIndex": 6,
            "endRowIndex": 7,
            "startColumnIndex": 13,
            "endColumnIndex": 14,
        }
    ]

    with pytest.raises(ValueError, match="Expected 5"):
        MODULE._structural_requests(10, 20, [7], 281, 280, 1294)


def test_content_plan_places_marker_and_ten_metrics_after_data() -> None:
    record = _record(
        "lead-1",
        name="Target Person",
        company="Target Ltd",
        mutuals=["Jeremy Pike", "Paul Fryer"],
        primaryVisibleInPanel=True,
    )
    validated = MODULE._validate_checkpoint(_checkpoint([record]), "Jeremy Pike")
    rows, _, stats = MODULE._build_data(validated, "Jeremy Pike")

    requests, boundaries = MODULE._content_requests(99, rows, stats, "Jeremy Pike")

    assert boundaries == {
        "data_start_row": 6,
        "data_last_row": 7,
        "marker_row": 8,
        "spacer_row": 9,
        "summary_title_row": 10,
        "executive_row": 11,
        "summary_header_row": 12,
        "first_metric_row": 13,
        "final_metric_row": 22,
        "guidance_row": 23,
        "unused_start_row": 24,
    }
    metric_request = requests[5]["updateCells"]
    assert len(metric_request["rows"]) == 11
    assert requests[2]["updateCells"]["rows"][0]["values"][0]["userEnteredValue"][
        "stringValue"
    ].startswith("NEW COMPANY INSERTION POINT")
    metric_rows = requests[5]["updateCells"]["rows"]
    assert metric_rows[1]["values"][2]["userEnteredValue"]["stringValue"] == (
        "Every company is represented by one complete contiguous block."
    )
    assert metric_rows[10]["values"][2]["userEnteredValue"]["stringValue"] == (
        "No employer names were privacy-limited in this result set."
    )
