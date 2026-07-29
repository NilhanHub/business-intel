from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
BUILDER_PATH = ROOT / "tools" / "build_former_client_adjacency_sheet.py"
CHECKPOINT_PATH = ROOT / "tools" / "former_client_adjacency_checkpoint.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER = _load(BUILDER_PATH, "build_former_client_adjacency_sheet")
CHECKPOINT = _load(CHECKPOINT_PATH, "former_client_adjacency_checkpoint")


def _register() -> dict[str, object]:
    return {
        "records": [
            {
                "record_id": "fc-001",
                "label": "Named Client",
                "relationship_type": "direct client",
                "identity_confidence": "high",
                "seed_eligible": True,
                "industry": ["Technology"],
                "geography": ["United States"],
                "services": ["Full-stack development"],
                "technologies": ["Microsoft"],
                "engagement_evidence": "A published delivery case.",
                "aliases": ["Named Client Inc."],
                "source_urls": ["https://1billiontech.com/case_studies.php"],
            },
            {
                "record_id": "fc-002",
                "label": "Anonymous regulated company",
                "relationship_type": "anonymized case",
                "identity_confidence": "anonymous",
                "seed_eligible": False,
                "industry": ["Regulated services"],
                "geography": ["Unknown"],
                "services": ["Application modernization"],
                "technologies": ["Cloud"],
                "engagement_evidence": "The published case withholds identity.",
                "aliases": [],
                "source_urls": ["https://1billiontech.com/case_studies.php"],
            },
        ]
    }


def _target(company: str, lead_id: str, index: int) -> dict[str, object]:
    return {
        "lead_id": lead_id,
        "name": f"Target {index}",
        "title": (
            "Chief Technology Officer"
            if index == 1
            else "Director of Digital Technology"
        ),
        "current_company": company,
        "location": "London, England, United Kingdom",
        "tenure": "2 years in role",
        "role_evidence": "Current role visible on the result card.",
        "change_proxy": "Recently hired marker visible on the result card.",
        "profile_url": (
            f"https://www.linkedin.com/sales/lead/{lead_id},NAME_SEARCH,test"
        ),
        "captured_at": "2026-07-28T10:00:00Z",
        "mutuals": [
            {
                "name": "Named Mutual" if index == 1 else "Second Mutual",
                "evidence": (
                    "Visible in the live Sales Navigator introducer panel "
                    "for this target."
                ),
            }
        ],
    }


def _checkpoint() -> dict[str, object]:
    prospects: list[dict[str, object]] = []
    for index in range(1, 11):
        company = f"Company {index:02d}"
        prospects.append(
            {
                "company": company,
                "territory": "United Kingdom",
                "is_former_client": False,
                "former_client_anchor": {
                    "record_id": "fc-001",
                    "former_client": "Named Client",
                    "alumni_name": f"Alumni {index}",
                    "alumni_lead_id": f"alumni-{index}",
                    "former_role": "Senior Engineer",
                    "profile_url": (
                        "https://www.linkedin.com/sales/lead/"
                        f"alumni-{index},NAME_SEARCH,test"
                    ),
                    "relationship_evidence": (
                        "Past role and current employer were visible in the "
                        "live Sales Navigator DOM."
                    ),
                },
                "service_fit": {
                    "summary": (
                        "Official company evidence shows a relevant technology "
                        "and transformation operating model."
                    ),
                    "source_url": f"https://example.com/company-{index}",
                },
                "score": {
                    "service_similarity": 30,
                    "former_client_link": 20,
                    "warm_route_depth": 10,
                    "buying_committee_quality": 10,
                    "total": 70,
                },
                "cross_tab": {
                    "match": index == 1,
                    "tabs": ["Prasath Nanayakkara"] if index == 1 else [],
                },
                "targets": [
                    _target(company, f"lead-{index}-1", 1),
                    _target(company, f"lead-{index}-2", 2),
                ],
            }
        )
    return {
        "source": {
            "signed_in_identity": "Paul Fryer",
            "collection_method": "LinkedIn Sales Navigator live DOM",
            "territory": ["United Kingdom", "Ireland"],
        },
        "prospects": prospects,
    }


def test_plan_has_ten_contiguous_blocks_and_is_idempotent() -> None:
    register = _register()
    checkpoint = _checkpoint()

    first = BUILDER.build_plan(register, checkpoint, 12345)
    second = BUILDER.build_plan(register, checkpoint, 12345)

    assert first == second
    assert first["stats"]["prospect_company_count"] == 10
    assert first["stats"]["target_person_count"] == 20
    assert first["stats"]["company_summary_row_count"] == 10
    assert len(first["summary_row_numbers"]) == 10
    assert len(first["tracker_rows"]) == 30
    assert all(len(row) == 25 for row in first["tracker_rows"])
    assert first["grid"]["columns"] == 40
    assert first["boundaries"]["tracker_start_row"] == 6
    assert first["boundaries"]["register_start_row"] == 6
    assert first["boundaries"]["marker_row"] == 36
    assert not any("Search" in json.dumps(request) for request in first["requests"])


def test_plan_expands_to_an_eleventh_company_without_fixed_row_assumptions() -> None:
    checkpoint = _checkpoint()
    extra = deepcopy(checkpoint["prospects"][-1])
    extra["company"] = "Company 11"
    extra["former_client_anchor"]["alumni_name"] = "Alumni 11"
    extra["former_client_anchor"]["alumni_lead_id"] = "alumni-11"
    extra["former_client_anchor"]["profile_url"] = (
        "https://www.linkedin.com/sales/lead/alumni-11,NAME_SEARCH,test"
    )
    extra["service_fit"]["source_url"] = "https://example.com/company-11"
    for index, target in enumerate(extra["targets"], start=1):
        target["lead_id"] = f"lead-11-{index}"
        target["current_company"] = "Company 11"
        target["profile_url"] = (
            "https://www.linkedin.com/sales/lead/"
            f"lead-11-{index},NAME_SEARCH,test"
        )
    checkpoint["prospects"].append(extra)

    plan = BUILDER.build_plan(_register(), checkpoint, 12345)

    assert plan["stats"]["prospect_company_count"] == 11
    assert plan["stats"]["target_person_count"] == 22
    assert plan["stats"]["company_summary_row_count"] == 11
    assert len(plan["summary_row_numbers"]) == 11
    assert len(plan["tracker_rows"]) == 33
    assert plan["boundaries"]["marker_row"] == 39


def test_side_by_side_layout_separates_tracker_register_and_spacer() -> None:
    plan = BUILDER.build_plan(_register(), _checkpoint(), 12345)
    requests = plan["requests"]

    assert requests[0]["updateSheetProperties"]["properties"]["gridProperties"] == {
        "rowCount": 1294,
        "columnCount": 40,
        "frozenRowCount": 5,
    }
    assert "unmergeCells" in requests[1]
    assert requests[2]["deleteConditionalFormatRule"]["index"] == 1
    assert requests[3]["deleteConditionalFormatRule"]["index"] == 0
    assert requests[4]["repeatCell"]["fields"] == (
        "userEnteredValue,note,dataValidation"
    )

    content_ranges = [
        request["updateCells"]["range"]
        for request in requests
        if "updateCells" in request
    ]
    assert any(
        item["startRowIndex"] == 4
        and item["startColumnIndex"] == 0
        and item["endColumnIndex"] == 25
        for item in content_ranges
    )
    assert any(
        item["startRowIndex"] == 4
        and item["startColumnIndex"] == 28
        and item["endColumnIndex"] == 40
        for item in content_ranges
    )
    assert not any(item["startColumnIndex"] in {25, 26, 27} for item in content_ranges)


def test_tracker_uses_established_blue_white_row_banding() -> None:
    plan = BUILDER.build_plan(_register(), _checkpoint(), 12345)
    tracker_start = plan["boundaries"]["tracker_start_row"]
    tracker_last = plan["boundaries"]["tracker_last_row"]

    row_band_requests = {}
    for request in plan["requests"]:
        repeat = request.get("repeatCell")
        if not repeat:
            continue
        cell_range = repeat["range"]
        if (
            cell_range.get("startColumnIndex") == 0
            and cell_range.get("endColumnIndex") == 25
            and cell_range["endRowIndex"] == cell_range["startRowIndex"] + 1
        ):
            background = repeat["cell"]["userEnteredFormat"].get("backgroundColor")
            if background is not None:
                row_band_requests[cell_range["startRowIndex"] + 1] = background

    assert set(range(tracker_start, tracker_last + 1)) <= set(row_band_requests)
    for row_number in range(tracker_start, tracker_last + 1):
        expected = BUILDER.BLUE if row_number % 2 == 0 else BUILDER.WHITE
        assert row_band_requests[row_number] == expected

    for summary_row in plan["summary_row_numbers"]:
        summary_format = next(
            request["repeatCell"]["cell"]["userEnteredFormat"]
            for request in plan["requests"]
            if "repeatCell" in request
            and request["repeatCell"]["range"]["startRowIndex"] == summary_row - 1
            and request["repeatCell"]["range"]["endRowIndex"] == summary_row
            and request["repeatCell"]["range"]["startColumnIndex"] == 0
            and request["repeatCell"]["range"]["endColumnIndex"] == 1
            and "borders" in request["repeatCell"]["cell"]["userEnteredFormat"]
        )
        expected = BUILDER.BLUE if summary_row % 2 == 0 else BUILDER.WHITE
        assert summary_format["backgroundColor"] == expected
        assert summary_format["borders"]["bottom"]["style"] == "SOLID"


def test_single_routed_target_is_preserved_without_padding() -> None:
    checkpoint = _checkpoint()
    checkpoint["prospects"][0]["targets"] = [checkpoint["prospects"][0]["targets"][0]]

    plan = BUILDER.build_plan(_register(), checkpoint, 12345)

    assert plan["stats"]["target_person_count"] == 19
    assert plan["tracker_rows"][0][3] == "Named Mutual"
    assert plan["tracker_rows"][1][0] == "Company 01"
    assert plan["tracker_rows"][1][1] == 1


def test_target_mutuals_are_target_specific_and_summary_is_propensity_only() -> None:
    plan = BUILDER.build_plan(_register(), _checkpoint(), 12345)
    first_target = plan["tracker_rows"][0]
    second_target = plan["tracker_rows"][1]
    summary = plan["tracker_rows"][2]

    assert first_target[3] == "Named Mutual"
    assert first_target[13] == "Found route"
    assert first_target[14].endswith("live Sales Navigator introducer panel.")
    assert first_target[23].startswith("LinkedIn Sales Navigator live DOM")
    assert second_target[3] == "Second Mutual"
    assert second_target[13] == "Found route"
    assert second_target[14].endswith("live Sales Navigator introducer panel.")
    assert "not a confirmed opportunity" in summary[2]


def test_verified_linkedin_dom_recovery_method_is_explicitly_supported() -> None:
    checkpoint = _checkpoint()
    checkpoint["source"]["collection_method"] = (
        "LinkedIn Sales Navigator and standard LinkedIn live DOM in Paul "
        "Fryer's verified session"
    )

    plan = BUILDER.build_plan(_register(), checkpoint, 12345)
    assert plan["stats"]["prospect_company_count"] == 10

    checkpoint["source"]["collection_method"] = "Unverified export"
    with pytest.raises(ValueError, match="does not prove live DOM"):
        BUILDER.build_plan(_register(), checkpoint, 12345)


def test_president_is_treated_as_c_suite_authority() -> None:
    checkpoint = _checkpoint()
    checkpoint["prospects"][0]["targets"][1]["title"] = "President"

    plan = BUILDER.build_plan(_register(), checkpoint, 12345)
    assert plan["tracker_rows"][1][2].startswith("President at Company 01")


def test_global_function_owner_is_allowed_for_uk_account() -> None:
    checkpoint = _checkpoint()
    checkpoint["prospects"][0]["targets"][1]["location"] = (
        "Orlando, Florida, United States"
    )

    plan = BUILDER.build_plan(_register(), checkpoint, 12345)
    assert "United States" in plan["tracker_rows"][1][2]


def test_standard_profile_requires_same_dom_stable_id_evidence() -> None:
    checkpoint = _checkpoint()
    target = checkpoint["prospects"][0]["targets"][0]
    target["lead_id"] = "ACoAAATestStableIdentifier"
    target["profile_url"] = "https://www.linkedin.com/in/verified-target/"
    target["profile_identifier_source"] = (
        "Visible LinkedIn shared-connection search URL on the same live profile DOM"
    )

    plan = BUILDER.build_plan(_register(), checkpoint, 12345)
    assert plan["stats"]["target_person_count"] == 20
    assert plan["tracker_rows"][0][23].startswith(
        "Standard LinkedIn live DOM in Paul Fryer's verified session"
    )
    assert plan["tracker_rows"][0][14].endswith(
        "live LinkedIn DOM in Paul Fryer's verified session."
    )

    del target["profile_identifier_source"]
    with pytest.raises(ValueError, match="does not preserve stable ID"):
        BUILDER.build_plan(_register(), checkpoint, 12345)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda data: data["prospects"].clear(),
            "Expected 1-100 prospects",
        ),
        (
            lambda data: data["prospects"][0]["score"].update({"total": 99}),
            "score does not meet",
        ),
        (
            lambda data: data["prospects"][0].update({"is_former_client": True}),
            "must not itself",
        ),
        (
            lambda data: data["prospects"][0]["targets"][0].update(
                {"title": "Junior Developer"}
            ),
            "eligible senior",
        ),
        (
            lambda data: data["prospects"][0]["targets"][0].update({"mutuals": []}),
            "no named mutual route",
        ),
        (
            lambda data: data["prospects"][0]["targets"][0]["mutuals"][0].update(
                {"evidence": "A count was shown"}
            ),
            "not explicitly visible",
        ),
        (
            lambda data: data["prospects"][0]["service_fit"].update(
                {"summary": "This is a confirmed opportunity."}
            ),
            "prohibited claim",
        ),
    ],
)
def test_prospect_validation_rejects_unsafe_or_incomplete_data(
    mutator, message: str
) -> None:
    checkpoint = _checkpoint()
    mutator(checkpoint)
    with pytest.raises(ValueError, match=message):
        BUILDER.build_plan(_register(), checkpoint, 12345)


def test_register_rejects_anonymous_seed_and_duplicate_alias() -> None:
    register = _register()
    register["records"][1]["seed_eligible"] = True
    with pytest.raises(ValueError, match="not safe to use"):
        BUILDER.build_plan(register, _checkpoint(), 12345)

    register = _register()
    register["records"].append(
        {
            **deepcopy(register["records"][0]),
            "record_id": "fc-003",
            "label": "Named Client Inc.",
            "aliases": [],
        }
    )
    with pytest.raises(ValueError, match="unresolved duplicate identity"):
        BUILDER.build_plan(register, _checkpoint(), 12345)


def test_atomic_checkpoint_upserts_by_stable_id(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    record = {
        "lead_id": "stable-1",
        "verified_live": True,
        "name": "Target",
    }
    CHECKPOINT.upsert_record(path, "target_records", "stable-1", record)
    first = json.loads(path.read_text(encoding="utf-8"))
    assert first["target_records"]["stable-1"]["name"] == "Target"

    updated = {**record, "name": "Updated Target"}
    CHECKPOINT.upsert_record(path, "target_records", "stable-1", updated)
    second = json.loads(path.read_text(encoding="utf-8"))
    assert list(second["target_records"]) == ["stable-1"]
    assert second["target_records"]["stable-1"]["name"] == "Updated Target"


def test_checkpoint_refuses_mismatched_or_unverified_record(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    with pytest.raises(ValueError, match="must match"):
        CHECKPOINT.upsert_record(
            path,
            "target_records",
            "stable-1",
            {"lead_id": "other", "verified_live": True},
        )
    with pytest.raises(ValueError, match="verified_live"):
        CHECKPOINT.upsert_record(
            path,
            "target_records",
            "stable-1",
            {"lead_id": "stable-1", "verified_live": False},
        )


def test_checkpoint_syncs_final_prospect_targets_atomically(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps(
            {
                "source": {"status": "in_progress"},
                "alumni_records": {"alumni-1": {"lead_id": "alumni-1"}},
                "target_records": {},
            }
        ),
        encoding="utf-8",
    )

    result = CHECKPOINT.sync_prospect_targets(path, _checkpoint())

    assert result["source"]["status"] == "complete"
    assert result["source"]["target_record_count"] == 20
    assert len(result["target_records"]) == 20
    assert result["target_records"]["lead-1-1"]["company"] == "Company 01"
    assert result["target_records"]["lead-1-1"]["verified_live"] is True
    assert "alumni-1" in result["alumni_records"]


def test_cli_hash_manifest_is_stable_when_output_directory_is_reused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_path = tmp_path / "register.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    output = tmp_path / "output"
    register_path.write_text(json.dumps(_register()), encoding="utf-8")
    checkpoint_path.write_text(json.dumps(_checkpoint()), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(BUILDER_PATH),
            "--register",
            str(register_path),
            "--checkpoint",
            str(checkpoint_path),
            "--sheet-id",
            "12345",
            "--output-dir",
            str(output),
        ],
    )

    BUILDER.main()
    first = (output / "sha256.json").read_bytes()
    BUILDER.main()
    second = (output / "sha256.json").read_bytes()

    assert first == second
    assert "sha256.json" not in json.loads(second)
