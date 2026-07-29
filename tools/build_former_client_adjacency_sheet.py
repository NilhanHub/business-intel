"""Build a deterministic Google Sheets plan for the Former Clients tab.

The script is deliberately offline.  It validates the website register and the
Sales Navigator checkpoint, then emits exact batchUpdate requests and compact
verification artifacts.  A separate, explicitly authorised caller applies the
requests to Google Sheets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SHEET_COLUMNS = 25
SPACER_START_COLUMN = 25
REGISTER_START_COLUMN = 28
GRID_COLUMNS = 40
GRID_ROWS = 1294
MIN_PROSPECT_COUNT = 1
MAX_PROSPECT_COUNT = 100
MIN_SCORE = 55

RELATIONSHIP_TYPES = {
    "direct client",
    "testimonial client",
    "delivery partner",
    "1BT product",
    "anonymized case",
    "non-direct/PoC",
    "ambiguous",
}
SEED_RELATIONSHIP_TYPES = {"direct client", "testimonial client"}
STAGE_VALUES = (
    "Found route",
    "Mutual friend to contact",
    "Intro requested",
    "Intro agreed",
    "Target contacted",
    "Meeting / reply",
    "Won",
    "Dead / no route",
)
HEADERS = (
    "Company",
    "Target Person",
    "Target Role",
    "Mutual 1",
    "Mutual 1 Notes",
    "Mutual 2",
    "Mutual 2 Notes",
    "Mutual 3",
    "Mutual 3 Notes",
    "Mutual 4",
    "Mutual 4 Notes",
    "Mutual 5",
    "Mutual 5 Notes",
    "Current Stage",
    "Found Route Notes",
    "Mutual Friend Contact Notes",
    "Intro Requested Notes",
    "Intro Agreed Notes",
    "Target Contacted Notes",
    "Meeting / Reply Notes",
    "Won Notes",
    "Dead / No Route Notes",
    "Final Notes",
    "Source / Profile",
    "CRM Status",
)
REGISTER_HEADERS = (
    "Record ID",
    "Published client / case",
    "Relationship type",
    "Identity confidence",
    "Seed eligible",
    "Industry",
    "Geography",
    "Services",
    "Technologies",
    "Published engagement evidence",
    "Aliases / identity notes",
    "Source URLs",
)
SENIOR_TITLE = re.compile(
    r"\b(chief|president|ceo|cto|cio|ciso|coo|cfo|vp|vice president|"  # codespell:ignore coo
    r"director|head|partner|owner|founding team)\b",
    re.IGNORECASE,
)
FORBIDDEN_OPPORTUNITY_CLAIMS = (
    "confirmed opportunity",
    "active opportunity",
    "verified opportunity",
)
LIVE_DOM_COLLECTION_METHODS = {
    "LinkedIn Sales Navigator live DOM",
    (
        "LinkedIn Sales Navigator and standard LinkedIn live DOM in Paul "
        "Fryer's verified session"
    ),
}
STANDARD_PROFILE_ID_EVIDENCE = {
    "Visible fsd_profile URN on the same live LinkedIn profile DOM",
    "Visible LinkedIn shared-connection search URL on the same live profile DOM",
}

BURGUNDY = {"red": 0.478, "green": 0.090, "blue": 0.188}
BURGUNDY_DARK = {"red": 0.467, "green": 0.086, "blue": 0.188}
TEAL = {"red": 0.082, "green": 0.376, "blue": 0.510}
NAVY = {"red": 0.122, "green": 0.161, "blue": 0.216}
BLUE = {"red": 193 / 255, "green": 228 / 255, "blue": 245 / 255}
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}
GOLD = {"red": 0.953, "green": 0.910, "blue": 0.835}
BODY = {"red": 0.973, "green": 0.953, "blue": 0.937}
EMPHASIS = {"red": 0.918, "green": 0.953, "blue": 0.973}
LIGHT_GREY = {"red": 0.961, "green": 0.969, "blue": 0.973}
TEXT_GREY = {"red": 0.267, "green": 0.310, "blue": 0.349}
BORDER = {"red": 0.847, "green": 0.863, "blue": 0.882}
SUMMARY_BORDER = {"red": 224 / 255, "green": 219 / 255, "blue": 214 / 255}


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
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


def _required_text(record: dict[str, Any], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} requires non-blank {key}")
    return value.strip()


def _https_url(value: str, context: str, *, linkedin: bool = False) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{context} is not an HTTPS URL")
    if linkedin and parsed.netloc != "www.linkedin.com":
        raise ValueError(f"{context} is not a LinkedIn URL")


def _assert_no_opportunity_claim(text: str, context: str) -> None:
    lowered = text.casefold()
    for claim in FORBIDDEN_OPPORTUNITY_CLAIMS:
        if claim in lowered:
            raise ValueError(f"{context} contains prohibited claim: {claim}")


def _validate_register(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("Former-client register must contain records")

    seen_ids: set[str] = set()
    seen_named_identities: set[str] = set()
    validated: list[dict[str, Any]] = []
    for raw in records:
        if not isinstance(raw, dict):
            raise ValueError("Every register record must be an object")
        record = dict(raw)
        record_id = _required_text(record, "record_id", "register record")
        label = _required_text(record, "label", record_id)
        relationship_type = _required_text(record, "relationship_type", record_id)
        identity_confidence = _required_text(record, "identity_confidence", record_id)
        if record_id in seen_ids:
            raise ValueError(f"Duplicate register record ID: {record_id}")
        seen_ids.add(record_id)
        if relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError(f"{record_id} has unsupported relationship type")

        seed_eligible = record.get("seed_eligible")
        if not isinstance(seed_eligible, bool):
            raise ValueError(f"{record_id} requires boolean seed_eligible")
        if seed_eligible and (
            relationship_type not in SEED_RELATIONSHIP_TYPES
            or identity_confidence != "high"
        ):
            raise ValueError(f"{record_id} is not safe to use as a named seed")
        if relationship_type == "anonymized case" and seed_eligible:
            raise ValueError(f"{record_id} anonymized case cannot be a seed")

        source_urls = record.get("source_urls")
        if not isinstance(source_urls, list) or not source_urls:
            raise ValueError(f"{record_id} requires source URLs")
        for index, url in enumerate(source_urls):
            if not isinstance(url, str):
                raise ValueError(f"{record_id} source URL {index} is not text")
            _https_url(url, f"{record_id} source URL {index}")

        aliases = record.get("aliases", [])
        if not isinstance(aliases, list) or any(
            not isinstance(alias, str) or not alias.strip() for alias in aliases
        ):
            raise ValueError(f"{record_id} has invalid aliases")
        if identity_confidence != "anonymous":
            normalized_aliases = {
                _normal(label),
                *(_normal(alias) for alias in aliases),
            }
            overlap = normalized_aliases & seen_named_identities
            if overlap:
                raise ValueError(
                    f"{record_id} has an unresolved duplicate identity: {sorted(overlap)}"
                )
            seen_named_identities.update(normalized_aliases)

        evidence = _required_text(record, "engagement_evidence", record_id)
        _assert_no_opportunity_claim(evidence, record_id)
        validated.append(record)
    return validated


def _validate_target(
    target: dict[str, Any],
    company: str,
    seen_lead_ids: set[str],
) -> dict[str, Any]:
    lead_id = _required_text(target, "lead_id", company)
    name = _required_text(target, "name", lead_id)
    title = _required_text(target, "title", lead_id)
    current_company = _required_text(target, "current_company", lead_id)
    _required_text(target, "location", lead_id)
    profile_url = _required_text(target, "profile_url", lead_id)
    captured_at = _required_text(target, "captured_at", lead_id)

    if lead_id in seen_lead_ids:
        raise ValueError(f"Duplicate target lead ID: {lead_id}")
    seen_lead_ids.add(lead_id)
    if _normal(current_company) != _normal(company):
        raise ValueError(f"{lead_id} current employer does not match {company}")
    if not SENIOR_TITLE.search(title):
        raise ValueError(f"{lead_id} is not an eligible senior target")
    _https_url(profile_url, f"{lead_id} profile URL", linkedin=True)
    parsed_profile = urlsplit(profile_url)
    sales_profile_preserves_id = f"/sales/lead/{lead_id}," in profile_url
    standard_profile_preserves_id = (
        parsed_profile.path.startswith("/in/")
        and lead_id.startswith("ACo")
        and target.get("profile_identifier_source") in STANDARD_PROFILE_ID_EVIDENCE
    )
    if not sales_profile_preserves_id and not standard_profile_preserves_id:
        raise ValueError(f"{lead_id} profile URL does not preserve stable ID")
    if "T" not in captured_at or not captured_at.endswith("Z"):
        raise ValueError(f"{lead_id} has an invalid capture timestamp")

    mutuals = target.get("mutuals")
    if not isinstance(mutuals, list):
        raise ValueError(f"{lead_id} mutuals must be a list")
    if not mutuals:
        raise ValueError(f"{lead_id} has no named mutual route")
    if len(mutuals) > 5:
        raise ValueError(f"{lead_id} retains more than five mutuals")
    seen_mutuals: set[str] = set()
    clean_mutuals: list[dict[str, str]] = []
    for mutual in mutuals:
        if not isinstance(mutual, dict):
            raise ValueError(f"{lead_id} mutual must be an object")
        mutual_name = _required_text(mutual, "name", lead_id)
        evidence = _required_text(mutual, "evidence", lead_id)
        normalized = _normal(mutual_name)
        if normalized in seen_mutuals:
            raise ValueError(f"{lead_id} repeats mutual {mutual_name}")
        seen_mutuals.add(normalized)
        if "visible" not in evidence.casefold():
            raise ValueError(f"{lead_id} mutual evidence is not explicitly visible")
        clean_mutuals.append({"name": mutual_name, "evidence": evidence})

    for field in ("role_evidence", "change_proxy"):
        text = _required_text(target, field, lead_id)
        _assert_no_opportunity_claim(text, lead_id)
    clean = dict(target)
    clean["name"] = name
    clean["title"] = title
    clean["mutuals"] = clean_mutuals
    return clean


def _validate_prospects(
    checkpoint: dict[str, Any],
    register: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source = checkpoint.get("source")
    if not isinstance(source, dict):
        raise ValueError("Prospect checkpoint requires source metadata")
    if source.get("signed_in_identity") != "Paul Fryer":
        raise ValueError("Checkpoint does not prove the Paul Fryer session")
    if source.get("collection_method") not in LIVE_DOM_COLLECTION_METHODS:
        raise ValueError("Checkpoint does not prove live DOM collection")

    register_by_id = {record["record_id"]: record for record in register}
    prospects = checkpoint.get("prospects")
    if not isinstance(prospects, list):
        raise ValueError("Prospects must be a list")
    if not MIN_PROSPECT_COUNT <= len(prospects) <= MAX_PROSPECT_COUNT:
        raise ValueError(
            f"Expected {MIN_PROSPECT_COUNT}-{MAX_PROSPECT_COUNT} prospects"
        )

    seen_companies: set[str] = set()
    seen_lead_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    for raw in prospects:
        if not isinstance(raw, dict):
            raise ValueError("Every prospect must be an object")
        prospect = dict(raw)
        company = _required_text(prospect, "company", "prospect")
        normalized_company = _normal(company)
        if normalized_company in seen_companies:
            raise ValueError(f"Duplicate prospect company: {company}")
        seen_companies.add(normalized_company)

        territory = prospect.get("territory")
        if territory not in {"United Kingdom", "Ireland", "United Kingdom & Ireland"}:
            raise ValueError(f"{company} is outside the target territory")
        if prospect.get("is_former_client") is not False:
            raise ValueError(f"{company} must not itself be a former client")

        anchor = prospect.get("former_client_anchor")
        if not isinstance(anchor, dict):
            raise ValueError(f"{company} requires a former-client anchor")
        anchor_id = _required_text(anchor, "record_id", company)
        anchor_record = register_by_id.get(anchor_id)
        if not anchor_record or not anchor_record["seed_eligible"]:
            raise ValueError(f"{company} anchor is not a seed-eligible client")
        for key in (
            "alumni_name",
            "alumni_lead_id",
            "former_role",
            "profile_url",
            "relationship_evidence",
        ):
            _required_text(anchor, key, company)
        _https_url(anchor["profile_url"], f"{company} alumni URL", linkedin=True)

        service_fit = prospect.get("service_fit")
        if not isinstance(service_fit, dict):
            raise ValueError(f"{company} requires service-fit evidence")
        fit_summary = _required_text(service_fit, "summary", company)
        fit_url = _required_text(service_fit, "source_url", company)
        _https_url(fit_url, f"{company} service-fit URL")
        _assert_no_opportunity_claim(fit_summary, company)

        score = prospect.get("score")
        if not isinstance(score, dict):
            raise ValueError(f"{company} requires a score breakdown")
        limits = {
            "service_similarity": 35,
            "former_client_link": 30,
            "warm_route_depth": 20,
            "buying_committee_quality": 15,
        }
        total = 0
        for key, maximum in limits.items():
            value = score.get(key)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= maximum
            ):
                raise ValueError(f"{company} has invalid {key} score")
            total += value
        if score.get("total") != total or total < MIN_SCORE:
            raise ValueError(f"{company} score does not meet the hybrid threshold")

        targets = prospect.get("targets")
        if not isinstance(targets, list) or not 1 <= len(targets) <= 5:
            raise ValueError(f"{company} must contain one to five routed targets")
        clean_targets = [
            _validate_target(target, company, seen_lead_ids) for target in targets
        ]
        company_mutuals = {
            _normal(mutual["name"])
            for target in clean_targets
            for mutual in target["mutuals"]
        }
        if not company_mutuals:
            raise ValueError(f"{company} has no named mutual route")
        if len(company_mutuals) > 5:
            raise ValueError(f"{company} has more than five distinct mutuals")

        cross_tab = prospect.get("cross_tab")
        if not isinstance(cross_tab, dict) or not isinstance(
            cross_tab.get("match"), bool
        ):
            raise ValueError(f"{company} requires explicit cross-tab status")
        tabs = cross_tab.get("tabs", [])
        if not isinstance(tabs, list) or any(not isinstance(tab, str) for tab in tabs):
            raise ValueError(f"{company} has invalid cross-tab names")
        if cross_tab["match"] != bool(tabs):
            raise ValueError(f"{company} cross-tab flag does not match tab list")

        prospect["targets"] = clean_targets
        validated.append(prospect)
    return sorted(
        validated, key=lambda item: (-item["score"]["total"], _normal(item["company"]))
    )


def _cell(value: str | int | float | bool | None = None) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, bool):
        return {"userEnteredValue": {"boolValue": value}}
    if isinstance(value, (int, float)):
        return {"userEnteredValue": {"numberValue": value}}
    return {"userEnteredValue": {"stringValue": value}}


def _row(values: list[Any], expected: int = SHEET_COLUMNS) -> dict[str, Any]:
    if len(values) != expected:
        raise ValueError(f"Expected {expected} cells, got {len(values)}")
    return {"values": [_cell(value) for value in values]}


def _join_list(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _register_values(record: dict[str, Any]) -> list[Any]:
    seed = "Yes" if record["seed_eligible"] else "No"
    return [
        record["record_id"],
        record["label"],
        record["relationship_type"],
        record["identity_confidence"],
        seed,
        _join_list(record.get("industry")),
        _join_list(record.get("geography")),
        _join_list(record.get("services")),
        _join_list(record.get("technologies")),
        record["engagement_evidence"],
        _join_list(record.get("aliases")) or _join_list(record.get("identity_notes")),
        "\n".join(record["source_urls"]),
    ]


def _target_values(company: str, target: dict[str, Any]) -> list[Any]:
    profile_url = target["profile_url"]
    is_sales_navigator_profile = "/sales/lead/" in urlsplit(profile_url).path
    source_label = (
        "LinkedIn Sales Navigator live DOM"
        if is_sales_navigator_profile
        else "Standard LinkedIn live DOM in Paul Fryer's verified session"
    )
    route_source = (
        "live Sales Navigator introducer panel"
        if is_sales_navigator_profile
        else "live LinkedIn DOM in Paul Fryer's verified session"
    )
    role_parts = [
        f"{target['title']} at {company}",
        f"Location: {target['location']}",
        target["role_evidence"],
    ]
    if target.get("tenure"):
        role_parts.append(str(target["tenure"]))
    if target.get("change_proxy"):
        role_parts.append(f"Observable proxy: {target['change_proxy']}")

    values: list[Any] = [company, target["name"], " / ".join(role_parts)]
    mutuals = target["mutuals"]
    for index in range(5):
        if index < len(mutuals):
            values.extend([mutuals[index]["name"], mutuals[index]["evidence"]])
        else:
            values.extend(["", ""])
    if mutuals:
        route_note = (
            f"{len(mutuals)} target-specific named "
            f"{'route' if len(mutuals) == 1 else 'routes'} verified in the "
            f"{route_source}."
        )
        stage = "Found route"
    else:
        route_note = (
            "No named mutual was visible for this target. The company-level warm "
            "path is held on another target row in this same block."
        )
        stage = ""
    values.extend(
        [
            stage,
            route_note,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            (f"{source_label} | {profile_url} | captured {target['captured_at']}"),
            "",
        ]
    )
    return values


def _summary_values(prospect: dict[str, Any]) -> list[Any]:
    anchor = prospect["former_client_anchor"]
    score = prospect["score"]
    cross_tab = prospect["cross_tab"]
    overlap = (
        f"Cross-tab match: {', '.join(cross_tab['tabs'])}."
        if cross_tab["match"]
        else "No existing workbook company match."
    )
    summary = (
        "Propensity-based fit only — not a confirmed opportunity. "
        f"Former-client anchor: {anchor['alumni_name']} worked at "
        f"{anchor['former_client']} as {anchor['former_role']}; "
        f"{anchor['relationship_evidence']} "
        f"Score {score['total']}/100 "
        f"(service {score['service_similarity']}/35; people link "
        f"{score['former_client_link']}/30; warm routes "
        f"{score['warm_route_depth']}/20; committee "
        f"{score['buying_committee_quality']}/15). "
        f"Service fit: {prospect['service_fit']['summary']} "
        f"{overlap}"
    )
    return [
        prospect["company"],
        len(prospect["targets"]),
        summary,
        *("" for _ in range(22)),
    ]


def _build_data(
    register: list[dict[str, Any]],
    prospects: list[dict[str, Any]],
) -> tuple[list[list[Any]], list[list[Any]], list[int], dict[str, Any]]:
    register_rows = [_register_values(record) for record in register]
    tracker_rows: list[list[Any]] = []
    summary_row_numbers: list[int] = []
    row_number = 6
    for prospect in prospects:
        for target in prospect["targets"]:
            tracker_rows.append(_target_values(prospect["company"], target))
            row_number += 1
        tracker_rows.append(_summary_values(prospect))
        summary_row_numbers.append(row_number)
        row_number += 1

    targets = [target for prospect in prospects for target in prospect["targets"]]
    route_placements = [mutual for target in targets for mutual in target["mutuals"]]
    distinct_mutuals = {_normal(mutual["name"]) for mutual in route_placements}
    stats = {
        "former_client_record_count": len(register),
        "named_seed_client_count": sum(
            bool(record["seed_eligible"]) for record in register
        ),
        "anonymized_archetype_count": sum(
            record["relationship_type"] == "anonymized case" for record in register
        ),
        "prospect_company_count": len(prospects),
        "target_person_count": len(targets),
        "company_summary_row_count": len(prospects),
        "companies_with_five_distinct_mutuals": sum(
            len(
                {
                    _normal(mutual["name"])
                    for target in prospect["targets"]
                    for mutual in target["mutuals"]
                }
            )
            == 5
            for prospect in prospects
        ),
        "distinct_mutual_count": len(distinct_mutuals),
        "route_placement_count": len(route_placements),
        "cross_tab_match_count": sum(
            prospect["cross_tab"]["match"] for prospect in prospects
        ),
        "minimum_score": min(prospect["score"]["total"] for prospect in prospects),
        "maximum_score": max(prospect["score"]["total"] for prospect in prospects),
        "duplicate_company_count": 0,
        "duplicate_target_lead_id_count": 0,
        "unresolved_register_duplicate_count": 0,
    }
    return register_rows, tracker_rows, summary_row_numbers, stats


def _range(
    sheet_id: int, start_row: int, end_row: int, start_col: int, end_col: int
) -> dict[str, int]:
    return {
        "sheetId": sheet_id,
        "startRowIndex": start_row,
        "endRowIndex": end_row,
        "startColumnIndex": start_col,
        "endColumnIndex": end_col,
    }


def _format(
    *,
    background: dict[str, float] | None = None,
    foreground: dict[str, float] | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    size: int | None = None,
    horizontal: str | None = None,
    vertical: str = "TOP",
    bottom_border: dict[str, float] | None = None,
) -> dict[str, Any]:
    text: dict[str, Any] = {"fontFamily": "Carlito", "underline": False}
    if foreground is not None:
        text["foregroundColor"] = foreground
    if bold is not None:
        text["bold"] = bold
    if italic is not None:
        text["italic"] = italic
    if size is not None:
        text["fontSize"] = size
    result: dict[str, Any] = {
        "textFormat": text,
        "verticalAlignment": vertical,
        "wrapStrategy": "WRAP",
    }
    if background is not None:
        result["backgroundColor"] = background
    if horizontal is not None:
        result["horizontalAlignment"] = horizontal
    if bottom_border is not None:
        result["borders"] = {
            "bottom": {
                "style": "SOLID",
                "color": bottom_border,
            }
        }
    return result


def _repeat(
    sheet_id: int,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
    user_format: dict[str, Any],
) -> dict[str, Any]:
    return {
        "repeatCell": {
            "range": _range(sheet_id, start_row, end_row, start_col, end_col),
            "cell": {"userEnteredFormat": user_format},
            "fields": "userEnteredFormat",
        }
    }


def _merge(
    sheet_id: int, row_index: int, end_col: int = SHEET_COLUMNS
) -> dict[str, Any]:
    return {
        "mergeCells": {
            "range": _range(sheet_id, row_index, row_index + 1, 0, end_col),
            "mergeType": "MERGE_ALL",
        }
    }


def _dimension(
    sheet_id: int,
    dimension: str,
    start: int,
    end: int,
    pixels: int,
) -> dict[str, Any]:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": dimension,
                "startIndex": start,
                "endIndex": end,
            },
            "properties": {"pixelSize": pixels},
            "fields": "pixelSize",
        }
    }


def _content_requests(
    sheet_id: int,
    register_rows: list[list[Any]],
    tracker_rows: list[list[Any]],
    prospects: list[dict[str, Any]],
    stats: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    register_start = 6
    register_last = register_start + len(register_rows) - 1
    tracker_start = 6
    tracker_last = tracker_start + len(tracker_rows) - 1
    marker = tracker_last + 1
    spacer = marker + 1
    summary_title = spacer + 1
    executive = summary_title + 1
    summary_header = executive + 1
    metric_first = summary_header + 1
    metric_last = metric_first + 10
    guidance = metric_last + 1

    metrics = [
        (
            "Published relationship register",
            f"{stats['former_client_record_count']} records",
            "Every published named relationship and anonymized case was reconciled.",
        ),
        (
            "Named seed clients",
            f"{stats['named_seed_client_count']} clients",
            "Only high-confidence direct or testimonial clients were used as alumni seeds.",
        ),
        (
            "Anonymous archetypes",
            f"{stats['anonymized_archetype_count']} cases",
            "Service patterns retained without guessing client identities.",
        ),
        (
            "Selected accounts",
            f"{stats['prospect_company_count']} companies",
            "Top-scoring UK/Ireland accounts passing every hybrid evidence gate.",
        ),
        (
            "Buying-committee reach",
            f"{stats['target_person_count']} people",
            "Current senior targets spanning technology, digital, operations and risk roles.",
        ),
        (
            "Five-route coverage",
            f"{stats['companies_with_five_distinct_mutuals']} companies",
            "Accounts where the retained company-level introducer union reaches five people.",
        ),
        (
            "Network breadth",
            f"{stats['distinct_mutual_count']} people",
            "Distinct named introducers visible to Paul across the selected targets.",
        ),
        (
            "Relationship volume",
            f"{stats['route_placement_count']} routes",
            "Target-specific introducer placements; vague mutual counts were excluded.",
        ),
        (
            "Cross-tab overlap",
            f"{stats['cross_tab_match_count']} companies",
            "Existing workbook matches are retained and explicitly flagged, not duplicated silently.",
        ),
        (
            "Selection threshold",
            f"{stats['minimum_score']}-{stats['maximum_score']} / 100",
            f"Every selected account clears the documented {MIN_SCORE}-point minimum.",
        ),
        (
            "Research posture",
            "Propensity, not pipeline",
            "No row asserts a confirmed opportunity; visible route shortfalls remain explicit.",
        ),
    ]
    executive_text = (
        f"{stats['former_client_record_count']} published 1BT relationships and "
        f"case archetypes support {stats['prospect_company_count']} selected "
        f"UK/Ireland accounts, {stats['target_person_count']} senior targets and "
        f"{stats['route_placement_count']} target-specific named introducer "
        "routes. This is propensity-based prospecting, not confirmed pipeline."
    )
    tracker_top_rows = [
        "Former-Client Adjacency — Warm Route Tracker",
        (
            "Route-first research: only current UK/Ireland senior people with a "
            "visible named route to Paul are retained."
        ),
        (
            f"{stats['prospect_company_count']} prospect accounts | "
            f"{stats['target_person_count']} routed senior targets | "
            f"{stats['distinct_mutual_count']} distinct named introducers"
        ),
    ]
    register_top_rows = [
        "1BT Client, Partner & Published Relationship Register",
        (
            "Source-backed 1BT relationships are classified explicitly; products, "
            "partners and anonymized cases are not mislabeled as former clients."
        ),
        (
            f"{stats['former_client_record_count']} published records | "
            f"{stats['named_seed_client_count']} seed-eligible named clients | "
            f"{stats['anonymized_archetype_count']} anonymized case archetypes"
        ),
    ]
    marker_text = (
        "NEW PROSPECT COMPANY INSERTION POINT — Insert every complete new "
        "former-client-adjacent company block immediately above this row. Keep "
        "targets first and exactly one company-summary row last."
    )
    requests: list[dict[str, Any]] = [
        {
            "updateCells": {
                "range": _range(sheet_id, 0, 3, 0, 1),
                "rows": [{"values": [_cell(value)]} for value in tracker_top_rows],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": _range(
                    sheet_id,
                    0,
                    3,
                    REGISTER_START_COLUMN,
                    REGISTER_START_COLUMN + 1,
                ),
                "rows": [{"values": [_cell(value)]} for value in register_top_rows],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": _range(sheet_id, 4, 5, 0, SHEET_COLUMNS),
                "rows": [_row(list(HEADERS))],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": _range(
                    sheet_id,
                    tracker_start - 1,
                    tracker_last,
                    0,
                    SHEET_COLUMNS,
                ),
                "rows": [_row(values) for values in tracker_rows],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": _range(
                    sheet_id,
                    4,
                    5,
                    REGISTER_START_COLUMN,
                    REGISTER_START_COLUMN + len(REGISTER_HEADERS),
                ),
                "rows": [_row(list(REGISTER_HEADERS), len(REGISTER_HEADERS))],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": _range(
                    sheet_id,
                    register_start - 1,
                    register_last,
                    REGISTER_START_COLUMN,
                    REGISTER_START_COLUMN + len(REGISTER_HEADERS),
                ),
                "rows": [
                    _row(values, len(REGISTER_HEADERS)) for values in register_rows
                ],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": _range(sheet_id, marker - 1, marker, 0, 1),
                "rows": [
                    {
                        "values": [
                            {
                                "userEnteredValue": {"stringValue": marker_text},
                                "note": (
                                    "Permanent prospect insertion marker. Add "
                                    "complete company blocks above this row and "
                                    "regenerate the tab through the validated "
                                    "builder."
                                ),
                            }
                        ]
                    }
                ],
                "fields": "userEnteredValue,note",
            }
        },
        {
            "updateCells": {
                "range": _range(sheet_id, summary_title - 1, executive, 0, 1),
                "rows": [
                    {"values": [_cell("Former-Client Adjacency Summary")]},
                    {"values": [_cell(executive_text)]},
                ],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": _range(
                    sheet_id,
                    summary_header - 1,
                    metric_last,
                    0,
                    3,
                ),
                "rows": [
                    {
                        "values": [
                            _cell("Metric"),
                            _cell("Value"),
                            _cell("Commercial meaning"),
                        ]
                    },
                    *[
                        {
                            "values": [
                                _cell(label),
                                _cell(value),
                                _cell(meaning),
                            ]
                        }
                        for label, value, meaning in metrics
                    ],
                ],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": _range(sheet_id, guidance - 1, guidance, 0, 1),
                "rows": [
                    {
                        "values": [
                            _cell(
                                "How to use: prioritise the strongest score and "
                                "best target-specific route, validate the "
                                "relationship before outreach, and update stage "
                                "notes without converting propensity into an "
                                "opportunity claim."
                            )
                        ]
                    }
                ],
                "fields": "userEnteredValue",
            }
        },
    ]
    boundaries = {
        "register_header_row": 5,
        "register_start_row": register_start,
        "register_last_row": register_last,
        "tracker_header_row": 5,
        "tracker_start_row": tracker_start,
        "tracker_last_row": tracker_last,
        "marker_row": marker,
        "spacer_row": spacer,
        "summary_title_row": summary_title,
        "executive_row": executive,
        "summary_header_row": summary_header,
        "metric_first_row": metric_first,
        "metric_last_row": metric_last,
        "guidance_row": guidance,
        "unused_start_row": guidance + 1,
    }
    return requests, boundaries


def _format_requests(
    sheet_id: int,
    boundaries: dict[str, int],
    prospects: list[dict[str, Any]],
    summary_rows: list[int],
) -> list[dict[str, Any]]:
    marker = boundaries["marker_row"]
    summary_title = boundaries["summary_title_row"]
    executive = boundaries["executive_row"]
    summary_header = boundaries["summary_header_row"]
    metric_first = boundaries["metric_first_row"]
    metric_last = boundaries["metric_last_row"]
    guidance = boundaries["guidance_row"]
    tracker_last = boundaries["tracker_last_row"]

    requests: list[dict[str, Any]] = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {
                        "rowCount": GRID_ROWS,
                        "columnCount": GRID_COLUMNS,
                        "frozenRowCount": 6,
                    },
                    "tabColor": BURGUNDY,
                },
                "fields": (
                    "gridProperties.rowCount,gridProperties.columnCount,"
                    "gridProperties.frozenRowCount,tabColor"
                ),
            }
        },
        _repeat(
            sheet_id,
            0,
            GRID_ROWS,
            0,
            GRID_COLUMNS,
            _format(background=WHITE, foreground={"red": 0, "green": 0, "blue": 0}),
        ),
    ]
    for row_index in (
        0,
        1,
        2,
        4,
        28,
        29,
        marker - 1,
        summary_title - 1,
        executive - 1,
        guidance - 1,
    ):
        requests.append(_merge(sheet_id, row_index))

    requests.extend(
        [
            _repeat(
                sheet_id,
                0,
                1,
                0,
                SHEET_COLUMNS,
                _format(
                    background=WHITE,
                    bold=True,
                    size=16,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                1,
                2,
                0,
                SHEET_COLUMNS,
                _format(
                    background=WHITE,
                    foreground=TEXT_GREY,
                    italic=True,
                    size=10,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                2,
                3,
                0,
                SHEET_COLUMNS,
                _format(
                    background=WHITE,
                    bold=True,
                    size=10,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                4,
                5,
                0,
                SHEET_COLUMNS,
                _format(
                    background=BURGUNDY,
                    foreground=WHITE,
                    bold=True,
                    size=13,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                5,
                6,
                0,
                len(REGISTER_HEADERS),
                _format(
                    background=TEAL,
                    foreground=WHITE,
                    bold=True,
                    size=10,
                    horizontal="CENTER",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                28,
                29,
                0,
                SHEET_COLUMNS,
                _format(
                    background=BURGUNDY,
                    foreground=WHITE,
                    bold=True,
                    size=13,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                29,
                30,
                0,
                SHEET_COLUMNS,
                _format(
                    background=BODY,
                    foreground=TEXT_GREY,
                    italic=True,
                    size=10,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                30,
                31,
                0,
                SHEET_COLUMNS,
                _format(
                    background=TEAL,
                    foreground=WHITE,
                    bold=True,
                    size=11,
                    horizontal="CENTER",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                marker - 1,
                marker,
                0,
                SHEET_COLUMNS,
                _format(
                    background=GOLD,
                    foreground=BURGUNDY_DARK,
                    bold=True,
                    size=11,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                summary_title - 1,
                summary_title,
                0,
                3,
                _format(
                    background=NAVY,
                    foreground=WHITE,
                    bold=True,
                    size=16,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                executive - 1,
                executive,
                0,
                3,
                _format(
                    background=BODY,
                    foreground=TEXT_GREY,
                    italic=True,
                    size=11,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                summary_header - 1,
                summary_header,
                0,
                3,
                _format(
                    background=BURGUNDY,
                    foreground=WHITE,
                    bold=True,
                    size=11,
                    horizontal="CENTER",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                guidance - 1,
                guidance,
                0,
                3,
                _format(
                    background=LIGHT_GREY,
                    foreground=TEXT_GREY,
                    italic=True,
                    size=10,
                    horizontal="LEFT",
                    vertical="TOP",
                ),
            ),
        ]
    )

    for row_number in range(
        boundaries["register_start_row"], boundaries["register_last_row"] + 1
    ):
        color = BLUE if row_number % 2 else WHITE
        requests.append(
            _repeat(
                sheet_id,
                row_number - 1,
                row_number,
                0,
                len(REGISTER_HEADERS),
                _format(background=color, size=10),
            )
        )

    row_number = boundaries["tracker_start_row"]
    target_row_numbers: list[int] = []
    for prospect in prospects:
        target_count = len(prospect["targets"])
        target_row_numbers.extend(range(row_number, row_number + target_count))
        row_number += target_count + 1

    for row_number in range(
        boundaries["tracker_start_row"],
        tracker_last + 1,
    ):
        color = BLUE if row_number % 2 == 0 else WHITE
        requests.append(
            _repeat(
                sheet_id,
                row_number - 1,
                row_number,
                0,
                SHEET_COLUMNS,
                _format(background=color, size=11),
            )
        )

    for summary_row in summary_rows:
        summary_background = BLUE if summary_row % 2 == 0 else WHITE
        requests.extend(
            [
                _repeat(
                    sheet_id,
                    summary_row - 1,
                    summary_row,
                    0,
                    1,
                    _format(
                        background=summary_background,
                        foreground=NAVY,
                        bold=True,
                        size=11,
                        bottom_border=SUMMARY_BORDER,
                    ),
                ),
                _repeat(
                    sheet_id,
                    summary_row - 1,
                    summary_row,
                    1,
                    2,
                    _format(
                        background=summary_background,
                        foreground=BURGUNDY_DARK,
                        bold=True,
                        size=11,
                        horizontal="CENTER",
                        bottom_border=SUMMARY_BORDER,
                    ),
                ),
                _repeat(
                    sheet_id,
                    summary_row - 1,
                    summary_row,
                    2,
                    3,
                    _format(
                        background=summary_background,
                        foreground=TEXT_GREY,
                        size=11,
                        bottom_border=SUMMARY_BORDER,
                    ),
                ),
            ]
        )

    for row_number in range(metric_first, metric_last + 1):
        color = (
            EMPHASIS
            if row_number == metric_last
            else (BODY if row_number % 2 == 0 else WHITE)
        )
        requests.extend(
            [
                _repeat(
                    sheet_id,
                    row_number - 1,
                    row_number,
                    0,
                    1,
                    _format(
                        background=color,
                        foreground=BURGUNDY_DARK,
                        bold=True,
                        size=11,
                    ),
                ),
                _repeat(
                    sheet_id,
                    row_number - 1,
                    row_number,
                    1,
                    2,
                    _format(
                        background=color,
                        foreground=NAVY,
                        bold=True,
                        size=11,
                        horizontal="CENTER",
                    ),
                ),
                _repeat(
                    sheet_id,
                    row_number - 1,
                    row_number,
                    2,
                    3,
                    _format(
                        background=color,
                        foreground=TEXT_GREY,
                        size=11,
                    ),
                ),
            ]
        )

    requests.append(
        {
            "setDataValidation": {
                "range": _range(
                    sheet_id,
                    boundaries["tracker_start_row"] - 1,
                    tracker_last,
                    13,
                    14,
                ),
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [
                            {"userEnteredValue": value} for value in STAGE_VALUES
                        ],
                    },
                    "strict": True,
                    "showCustomUi": True,
                },
            }
        }
    )
    for summary_row in summary_rows:
        requests.append(
            {
                "setDataValidation": {
                    "range": _range(
                        sheet_id,
                        summary_row - 1,
                        summary_row,
                        13,
                        14,
                    )
                }
            }
        )
    requests.extend(
        [
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            _range(
                                sheet_id,
                                boundaries["tracker_start_row"] - 1,
                                tracker_last,
                                24,
                                25,
                            )
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [
                                    {
                                        "userEnteredValue": (
                                            '=ISNUMBER(SEARCH("Already",Y32))'
                                        )
                                    }
                                ],
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 0.910,
                                    "green": 0.961,
                                    "blue": 0.914,
                                }
                            },
                        },
                    },
                    "index": 0,
                }
            },
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            _range(
                                sheet_id,
                                boundaries["tracker_start_row"] - 1,
                                tracker_last,
                                24,
                                25,
                            )
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [
                                    {
                                        "userEnteredValue": (
                                            '=ISNUMBER(SEARCH("needs",Y32))'
                                        )
                                    }
                                ],
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 1.0,
                                    "green": 0.969,
                                    "blue": 0.929,
                                }
                            },
                        },
                    },
                    "index": 1,
                }
            },
        ]
    )

    widths = [
        191,
        191,
        335,
        175,
        191,
        175,
        191,
        175,
        191,
        175,
        191,
        175,
        191,
        159,
        223,
        223,
        223,
        223,
        223,
        223,
        175,
        66,
        271,
        239,
        223,
        68,
    ]
    requests.extend(
        _dimension(sheet_id, "COLUMNS", index, index + 1, width)
        for index, width in enumerate(widths)
    )
    requests.extend(
        [
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": boundaries["register_start_row"] - 1,
                        "endIndex": boundaries["register_last_row"],
                    }
                }
            },
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": boundaries["tracker_start_row"] - 1,
                        "endIndex": tracker_last,
                    }
                }
            },
            _dimension(sheet_id, "ROWS", 0, 1, 42),
            _dimension(sheet_id, "ROWS", 1, 2, 36),
            _dimension(sheet_id, "ROWS", 2, 3, 32),
            _dimension(sheet_id, "ROWS", 3, 4, 14),
            _dimension(sheet_id, "ROWS", 4, 5, 34),
            _dimension(sheet_id, "ROWS", 5, 6, 42),
            _dimension(sheet_id, "ROWS", 27, 28, 14),
            _dimension(sheet_id, "ROWS", 28, 29, 34),
            _dimension(sheet_id, "ROWS", 29, 30, 44),
            _dimension(sheet_id, "ROWS", 30, 31, 42),
            _dimension(sheet_id, "ROWS", marker - 1, marker, 48),
            _dimension(sheet_id, "ROWS", marker, marker + 1, 14),
            _dimension(
                sheet_id,
                "ROWS",
                summary_title - 1,
                summary_title,
                42,
            ),
            _dimension(sheet_id, "ROWS", executive - 1, executive, 62),
            _dimension(
                sheet_id,
                "ROWS",
                summary_header - 1,
                summary_header,
                36,
            ),
            _dimension(
                sheet_id,
                "ROWS",
                metric_first - 1,
                metric_last,
                56,
            ),
            _dimension(sheet_id, "ROWS", guidance - 1, guidance, 62),
            _dimension(
                sheet_id,
                "ROWS",
                guidance,
                GRID_ROWS,
                21,
            ),
        ]
    )
    return requests


def _side_by_side_format_requests(
    sheet_id: int,
    boundaries: dict[str, int],
    prospects: list[dict[str, Any]],
    summary_rows: list[int],
) -> list[dict[str, Any]]:
    """Format the route tracker and relationship register as parallel tables."""

    marker = boundaries["marker_row"]
    summary_title = boundaries["summary_title_row"]
    executive = boundaries["executive_row"]
    summary_header = boundaries["summary_header_row"]
    metric_first = boundaries["metric_first_row"]
    metric_last = boundaries["metric_last_row"]
    guidance = boundaries["guidance_row"]
    tracker_last = boundaries["tracker_last_row"]
    register_end_column = REGISTER_START_COLUMN + len(REGISTER_HEADERS)

    requests: list[dict[str, Any]] = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {
                        "rowCount": GRID_ROWS,
                        "columnCount": GRID_COLUMNS,
                        "frozenRowCount": 5,
                    },
                    "tabColor": BURGUNDY,
                },
                "fields": (
                    "gridProperties.rowCount,gridProperties.columnCount,"
                    "gridProperties.frozenRowCount,tabColor"
                ),
            }
        },
        _repeat(
            sheet_id,
            0,
            GRID_ROWS,
            0,
            GRID_COLUMNS,
            _format(
                background=WHITE,
                foreground={"red": 0, "green": 0, "blue": 0},
            ),
        ),
    ]

    for row_index in (0, 1, 2):
        requests.extend(
            [
                _merge(sheet_id, row_index),
                {
                    "mergeCells": {
                        "range": _range(
                            sheet_id,
                            row_index,
                            row_index + 1,
                            REGISTER_START_COLUMN,
                            register_end_column,
                        ),
                        "mergeType": "MERGE_ALL",
                    }
                },
            ]
        )
    for row_index in (
        marker - 1,
        summary_title - 1,
        executive - 1,
        guidance - 1,
    ):
        requests.append(_merge(sheet_id, row_index))

    requests.extend(
        [
            _repeat(
                sheet_id,
                0,
                1,
                0,
                SHEET_COLUMNS,
                _format(
                    background=BURGUNDY,
                    foreground=WHITE,
                    bold=True,
                    size=16,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                1,
                2,
                0,
                SHEET_COLUMNS,
                _format(
                    background=BODY,
                    foreground=TEXT_GREY,
                    italic=True,
                    size=10,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                2,
                3,
                0,
                SHEET_COLUMNS,
                _format(
                    background=EMPHASIS,
                    foreground=NAVY,
                    bold=True,
                    size=10,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                0,
                1,
                REGISTER_START_COLUMN,
                register_end_column,
                _format(
                    background=NAVY,
                    foreground=WHITE,
                    bold=True,
                    size=15,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                1,
                2,
                REGISTER_START_COLUMN,
                register_end_column,
                _format(
                    background=BODY,
                    foreground=TEXT_GREY,
                    italic=True,
                    size=10,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                2,
                3,
                REGISTER_START_COLUMN,
                register_end_column,
                _format(
                    background=EMPHASIS,
                    foreground=NAVY,
                    bold=True,
                    size=10,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                4,
                5,
                0,
                SHEET_COLUMNS,
                _format(
                    background=TEAL,
                    foreground=WHITE,
                    bold=True,
                    size=11,
                    horizontal="CENTER",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                4,
                5,
                REGISTER_START_COLUMN,
                register_end_column,
                _format(
                    background=BURGUNDY_DARK,
                    foreground=WHITE,
                    bold=True,
                    size=10,
                    horizontal="CENTER",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                0,
                GRID_ROWS,
                SPACER_START_COLUMN,
                REGISTER_START_COLUMN,
                _format(background=WHITE),
            ),
            _repeat(
                sheet_id,
                marker - 1,
                marker,
                0,
                SHEET_COLUMNS,
                _format(
                    background=GOLD,
                    foreground=BURGUNDY_DARK,
                    bold=True,
                    size=11,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                summary_title - 1,
                summary_title,
                0,
                SHEET_COLUMNS,
                _format(
                    background=NAVY,
                    foreground=WHITE,
                    bold=True,
                    size=15,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                executive - 1,
                executive,
                0,
                SHEET_COLUMNS,
                _format(
                    background=BODY,
                    foreground=TEXT_GREY,
                    italic=True,
                    size=11,
                    horizontal="LEFT",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                summary_header - 1,
                summary_header,
                0,
                3,
                _format(
                    background=BURGUNDY,
                    foreground=WHITE,
                    bold=True,
                    size=11,
                    horizontal="CENTER",
                    vertical="MIDDLE",
                ),
            ),
            _repeat(
                sheet_id,
                guidance - 1,
                guidance,
                0,
                SHEET_COLUMNS,
                _format(
                    background=LIGHT_GREY,
                    foreground=TEXT_GREY,
                    italic=True,
                    size=10,
                    horizontal="LEFT",
                    vertical="TOP",
                ),
            ),
        ]
    )

    for row_number in range(
        boundaries["register_start_row"],
        boundaries["register_last_row"] + 1,
    ):
        color = BLUE if row_number % 2 == 0 else WHITE
        requests.append(
            _repeat(
                sheet_id,
                row_number - 1,
                row_number,
                REGISTER_START_COLUMN,
                register_end_column,
                _format(background=color, size=10),
            )
        )

    for row_number in range(
        boundaries["tracker_start_row"],
        tracker_last + 1,
    ):
        color = BLUE if row_number % 2 == 0 else WHITE
        requests.append(
            _repeat(
                sheet_id,
                row_number - 1,
                row_number,
                0,
                SHEET_COLUMNS,
                _format(background=color, size=11),
            )
        )

    for summary_row in summary_rows:
        summary_background = BLUE if summary_row % 2 == 0 else WHITE
        requests.extend(
            [
                _repeat(
                    sheet_id,
                    summary_row - 1,
                    summary_row,
                    0,
                    1,
                    _format(
                        background=summary_background,
                        foreground=NAVY,
                        bold=True,
                        size=11,
                        bottom_border=SUMMARY_BORDER,
                    ),
                ),
                _repeat(
                    sheet_id,
                    summary_row - 1,
                    summary_row,
                    1,
                    2,
                    _format(
                        background=summary_background,
                        foreground=BURGUNDY_DARK,
                        bold=True,
                        size=11,
                        horizontal="CENTER",
                        bottom_border=SUMMARY_BORDER,
                    ),
                ),
                _repeat(
                    sheet_id,
                    summary_row - 1,
                    summary_row,
                    2,
                    3,
                    _format(
                        background=summary_background,
                        foreground=TEXT_GREY,
                        size=11,
                        bottom_border=SUMMARY_BORDER,
                    ),
                ),
            ]
        )

    for row_number in range(metric_first, metric_last + 1):
        color = (
            EMPHASIS
            if row_number == metric_last
            else (BODY if row_number % 2 == 0 else WHITE)
        )
        requests.extend(
            [
                _repeat(
                    sheet_id,
                    row_number - 1,
                    row_number,
                    0,
                    1,
                    _format(
                        background=color,
                        foreground=BURGUNDY_DARK,
                        bold=True,
                        size=11,
                    ),
                ),
                _repeat(
                    sheet_id,
                    row_number - 1,
                    row_number,
                    1,
                    2,
                    _format(
                        background=color,
                        foreground=NAVY,
                        bold=True,
                        size=11,
                        horizontal="CENTER",
                    ),
                ),
                _repeat(
                    sheet_id,
                    row_number - 1,
                    row_number,
                    2,
                    3,
                    _format(
                        background=color,
                        foreground=TEXT_GREY,
                        size=11,
                    ),
                ),
            ]
        )

    requests.append(
        {
            "setDataValidation": {
                "range": _range(
                    sheet_id,
                    boundaries["tracker_start_row"] - 1,
                    tracker_last,
                    13,
                    14,
                ),
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [
                            {"userEnteredValue": value} for value in STAGE_VALUES
                        ],
                    },
                    "strict": True,
                    "showCustomUi": True,
                },
            }
        }
    )
    for summary_row in summary_rows:
        requests.append(
            {
                "setDataValidation": {
                    "range": _range(
                        sheet_id,
                        summary_row - 1,
                        summary_row,
                        13,
                        14,
                    )
                }
            }
        )

    first_tracker_row = boundaries["tracker_start_row"]
    requests.extend(
        [
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            _range(
                                sheet_id,
                                first_tracker_row - 1,
                                tracker_last,
                                24,
                                25,
                            )
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [
                                    {
                                        "userEnteredValue": (
                                            '=ISNUMBER(SEARCH("Already",'
                                            f"Y{first_tracker_row}))"
                                        )
                                    }
                                ],
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 0.910,
                                    "green": 0.961,
                                    "blue": 0.914,
                                }
                            },
                        },
                    },
                    "index": 0,
                }
            },
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            _range(
                                sheet_id,
                                first_tracker_row - 1,
                                tracker_last,
                                24,
                                25,
                            )
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [
                                    {
                                        "userEnteredValue": (
                                            '=ISNUMBER(SEARCH("needs",'
                                            f"Y{first_tracker_row}))"
                                        )
                                    }
                                ],
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 1.0,
                                    "green": 0.969,
                                    "blue": 0.929,
                                }
                            },
                        },
                    },
                    "index": 1,
                }
            },
        ]
    )

    widths = [
        191,
        191,
        335,
        175,
        191,
        175,
        191,
        175,
        191,
        175,
        191,
        175,
        191,
        159,
        223,
        223,
        223,
        223,
        223,
        223,
        175,
        66,
        271,
        239,
        223,
        32,
        32,
        32,
        90,
        190,
        135,
        115,
        95,
        165,
        155,
        220,
        200,
        280,
        200,
        280,
    ]
    if len(widths) != GRID_COLUMNS:
        raise ValueError("Side-by-side width plan does not match grid")
    requests.extend(
        _dimension(sheet_id, "COLUMNS", index, index + 1, width)
        for index, width in enumerate(widths)
    )

    requests.extend(
        [
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": boundaries["tracker_start_row"] - 1,
                        "endIndex": tracker_last,
                    }
                }
            },
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": boundaries["register_start_row"] - 1,
                        "endIndex": boundaries["register_last_row"],
                    }
                }
            },
            _dimension(sheet_id, "ROWS", 0, 1, 42),
            _dimension(sheet_id, "ROWS", 1, 2, 48),
            _dimension(sheet_id, "ROWS", 2, 3, 34),
            _dimension(sheet_id, "ROWS", 3, 4, 14),
            _dimension(sheet_id, "ROWS", 4, 5, 42),
            _dimension(sheet_id, "ROWS", marker - 1, marker, 48),
            _dimension(sheet_id, "ROWS", marker, marker + 1, 14),
            _dimension(sheet_id, "ROWS", summary_title - 1, summary_title, 42),
            _dimension(sheet_id, "ROWS", executive - 1, executive, 62),
            _dimension(sheet_id, "ROWS", summary_header - 1, summary_header, 36),
            _dimension(sheet_id, "ROWS", metric_first - 1, metric_last, 56),
            _dimension(sheet_id, "ROWS", guidance - 1, guidance, 62),
            _dimension(sheet_id, "ROWS", guidance, GRID_ROWS, 21),
        ]
    )
    return requests


def build_plan(
    register_payload: dict[str, Any],
    checkpoint: dict[str, Any],
    sheet_id: int,
) -> dict[str, Any]:
    register = _validate_register(register_payload)
    prospects = _validate_prospects(checkpoint, register)
    register_rows, tracker_rows, summary_rows, stats = _build_data(register, prospects)
    content, boundaries = _content_requests(
        sheet_id,
        register_rows,
        tracker_rows,
        prospects,
        stats,
    )
    formatting = _side_by_side_format_requests(
        sheet_id, boundaries, prospects, summary_rows
    )
    preparation = [
        {
            "unmergeCells": {
                "range": _range(
                    sheet_id,
                    0,
                    GRID_ROWS,
                    0,
                    GRID_COLUMNS,
                )
            }
        },
        {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 1}},
        {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}},
        {
            "repeatCell": {
                "range": _range(
                    sheet_id,
                    0,
                    GRID_ROWS,
                    0,
                    GRID_COLUMNS,
                ),
                "cell": {},
                "fields": "userEnteredValue,note,dataValidation",
            }
        },
    ]
    return {
        "sheet_id": sheet_id,
        "sheet_title": "Former Clients",
        "grid": {"rows": GRID_ROWS, "columns": GRID_COLUMNS},
        "stats": stats,
        "boundaries": boundaries,
        "summary_row_numbers": summary_rows,
        "stage_values": list(STAGE_VALUES),
        "register_rows": register_rows,
        "tracker_rows": tracker_rows,
        "requests": [
            formatting[0],
            *preparation,
            *content,
            *formatting[1:],
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--register", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--sheet-id", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    register_payload = json.loads(args.register.read_text(encoding="utf-8"))
    checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    plan = build_plan(register_payload, checkpoint, args.sheet_id)
    output = args.output_dir

    _atomic_json(output / "former-client-register.validated.json", register_payload)
    _atomic_json(output / "sales-navigator-prospects.validated.json", checkpoint)
    _atomic_json(
        output / "expected-register-matrix.compact.json",
        plan["register_rows"],
    )
    _atomic_json(
        output / "expected-prospect-matrix.compact.json",
        plan["tracker_rows"],
    )
    _atomic_json(
        output / "former-clients-sheet-plan.json",
        {
            key: value
            for key, value in plan.items()
            if key not in {"register_rows", "tracker_rows", "requests"}
        },
    )
    _atomic_json(
        output / "former-clients-sheet-requests.json",
        {"requests": plan["requests"]},
    )
    hashes: dict[str, str] = {}
    for path in sorted(output.glob("*.json")):
        if path.name == "sha256.json":
            continue
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    _atomic_json(output / "sha256.json", hashes)
    print(json.dumps(plan["stats"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
