"""Evidence-safe report composition workflow for UK/IE D365 opportunity packs."""

from __future__ import annotations

import html
import json
import os
import re
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uk_ie_d365_leads.tools import lead_tools
from uk_ie_d365_leads.tools import opportunity_vetting_tools as vetting

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = PROJECT_ROOT / "Evidence"
DEFAULT_PROVIDER_PATH = vetting.GEMINI_AGENT_PLATFORM_PROVIDER_PATH

ALLOWED_STYLE_PRESETS = {
    "executive_landscape",
    "board_brief_portrait",
    "dense_pipeline_review",
}
FORBIDDEN_FINAL_URL_TERMS = (
    *vetting.FORBIDDEN_FINAL_URL_TERMS,
    "find-tender.service.gov.uk",
    "contracts.service.gov.uk",
    "etenders.gov.ie",
)
REQUIRED_BLUEPRINT_FIELDS = [
    "title",
    "subtitle",
    "audience",
    "board_purpose",
    "style_preset",
    "tone",
    "section_plan",
    "account_detail_fields",
    "missing_info_requests",
    "caveats",
    "do_not_claim_rules",
]
REQUIRED_REPORT_SPEC_FIELDS = [
    "title",
    "subtitle",
    "style_preset",
    "executive_snapshot",
    "signal_themes",
    "at_a_glance",
    "accounts",
    "caveats",
    "appendix",
]
REQUIRED_ACCOUNT_FIELDS = [
    "account",
    "signal_strength",
    "signal_type",
    "evidence_refs",
    "opportunity_signal",
    "why_this_matters_to_1bt",
    "commercial_opening",
    "value_of_signal",
    "intelligence_reading",
    "board_relevance",
    "do_not_claim_notes",
    "remaining_uncertainty",
]
REPORT_BLUEPRINT_SCHEMA = {
    "required_fields": REQUIRED_BLUEPRINT_FIELDS,
    "style_presets": sorted(ALLOWED_STYLE_PRESETS),
}
REPORT_SPEC_SCHEMA = {
    "required_fields": REQUIRED_REPORT_SPEC_FIELDS,
    "account_required_fields": REQUIRED_ACCOUNT_FIELDS,
    "style_presets": sorted(ALLOWED_STYLE_PRESETS),
}


class SchemaValidationError(ValueError):
    """Raised when an AI report blueprint/spec does not match the local schema."""


class UnsafeReportSpecError(ValueError):
    """Raised when a report spec violates evidence or source-safety rules."""


class ProjectGuardError(RuntimeError):
    """Raised when a live report workflow would use the wrong Google project."""


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def build_document_request(
    *,
    requirement: str,
    output_basename: str,
    style_reference_pdf: str | None = None,
    output_formats: list[str] | None = None,
) -> dict[str, Any]:
    if not str(requirement or "").strip():
        raise SchemaValidationError("requirement is required")
    if not str(output_basename or "").strip():
        raise SchemaValidationError("output_basename is required")
    return {
        "requirement": str(requirement).strip(),
        "output_basename": safe_basename(output_basename),
        "style_reference_pdf": style_reference_pdf,
        "output_formats": output_formats or ["json", "markdown", "html", "pdf"],
        "generated_at": now_utc(),
    }


def safe_basename(value: str) -> str:
    basename = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    basename = basename.strip("._")
    if not basename:
        raise SchemaValidationError("output_basename is empty after sanitization")
    return basename


def load_json_maybe(value: Path | str | dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    path = Path(value)
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def build_evidence_inventory(
    *,
    input_pack: Path | str | dict[str, Any],
    source_checks: Path | str | dict[str, Any] | None = None,
    extra_evidence: list[Path | str | dict[str, Any]] | None = None,
    style_reference_pdf: str | None = None,
) -> dict[str, Any]:
    pack_data = load_json_maybe(input_pack)
    source_data = load_json_maybe(source_checks)
    extra_data = [load_json_maybe(item) for item in (extra_evidence or [])]
    source_by_company = source_checks_by_company(source_data)
    accounts = []
    for lead in extract_lead_records(pack_data):
        account = evidence_account_from_lead(lead, source_by_company.get(str(lead.get("company_name"))))
        if account["evidence"]:
            accounts.append(account)
    for item in extra_data:
        for lead in extract_lead_records(item):
            account = evidence_account_from_lead(lead, source_by_company.get(str(lead.get("company_name"))))
            if account["evidence"]:
                accounts.append(account)
    accounts = dedupe_accounts(accounts)
    allowed_urls = sorted(
        {
            evidence["url"]
            for account in accounts
            for evidence in account.get("evidence") or []
            if evidence.get("url")
        }
    )
    return {
        "artifact_type": "uk_ie_d365_report_evidence_inventory",
        "generated_at": now_utc(),
        "source_pack_summary": {
            "lead_count": len(accounts),
            "input_pack": str(input_pack) if not isinstance(input_pack, dict) else "inline",
            "source_checks": str(source_checks) if source_checks and not isinstance(source_checks, dict) else None,
            "extra_evidence_count": len(extra_evidence or []),
            "style_reference_pdf": style_reference_pdf,
        },
        "accounts": accounts,
        "allowed_evidence_urls": allowed_urls,
        "evidence_by_url": {
            evidence["url"]: evidence
            for account in accounts
            for evidence in account.get("evidence") or []
            if evidence.get("url")
        },
    }


def extract_lead_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("leads", "useful_leads", "accounts"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        if value.get("company_name") or value.get("account"):
            return [value]
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return []


def source_checks_by_company(source_checks: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(source_checks.get("records"), list):
        rows.extend(source_checks["records"])
    for key in ("current_leads", "alternative_candidates", "accounts"):
        if isinstance(source_checks.get(key), list):
            rows.extend(source_checks[key])
    return {
        str(row.get("company_name") or row.get("account") or row.get("account_name")): row
        for row in rows
        if row.get("company_name") or row.get("account") or row.get("account_name")
    }


def evidence_account_from_lead(lead: dict[str, Any], source_check: dict[str, Any] | None) -> dict[str, Any]:
    company = clean_text(lead.get("company_name") or lead.get("account") or lead.get("name"))
    evidence_url = clean_text(lead.get("evidence_url") or lead.get("source_url"))
    evidence_urls = [evidence_url] if evidence_url else []
    evidence_urls.extend(str(url) for url in lead.get("evidence_urls") or [] if url)
    evidence = []
    for url in dict.fromkeys(evidence_urls):
        if not url or forbidden_report_url(url, lead.get("evidence_excerpt") or ""):
            continue
        final_url = clean_text((source_check or {}).get("final_url") or lead.get("final_evidence_url_after_redirect") or url)
        if forbidden_report_url(final_url, lead.get("evidence_excerpt") or ""):
            continue
        evidence.append(
            {
                "url": final_url,
                "original_url": url,
                "source_name": clean_text(lead.get("source_name") or (source_check or {}).get("source_name") or source_name_from_url(final_url)),
                "excerpt": clean_text(lead.get("evidence_excerpt") or first_text(lead.get("evidence_snippets"))),
                "fetched_at": clean_text(lead.get("fetched_at") or (source_check or {}).get("fetched_at")),
                "verified_live": bool(lead.get("verified_live") or (source_check or {}).get("verified_live")),
                "source_cleanup_needed": bool(
                    lead.get("lead_status") == "source_cleanup_needed"
                    or (source_check or {}).get("supplemental_live_check_required")
                ),
                "allowed_claims": [
                    clean_text(lead.get("opportunity_signal")),
                    clean_text(lead.get("signal_type")),
                    clean_text(lead.get("why_this_matters_to_1bt")),
                ],
            }
        )
    return {
        "account": company,
        "lead_status": lead.get("lead_status"),
        "signal_strength": lead.get("signal_strength"),
        "signal_type": lead.get("signal_type"),
        "opportunity_signal": lead.get("opportunity_signal"),
        "why_this_matters_to_1bt": lead.get("why_this_matters_to_1bt"),
        "commercial_opening": lead.get("commercial_opening"),
        "value_of_signal": lead.get("value_of_signal"),
        "intelligence_reading": lead.get("intelligence_reading"),
        "board_relevance": lead.get("board_relevance"),
        "contact_target_roles": lead.get("contact_target_roles") or [],
        "do_not_claim_notes": lead.get("do_not_claim_notes") or [],
        "remaining_uncertainty": lead.get("remaining_uncertainty") or [],
        "evidence": evidence,
    }


def dedupe_accounts(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for account in accounts:
        key = vetting.normalize_company_for_match(account.get("account"))
        if not key:
            continue
        if key not in merged:
            merged[key] = account
            continue
        seen_urls = {item["url"] for item in merged[key].get("evidence") or [] if item.get("url")}
        for evidence in account.get("evidence") or []:
            if evidence.get("url") not in seen_urls:
                merged[key].setdefault("evidence", []).append(evidence)
    return list(merged.values())


def build_blueprint_prompt(request: dict[str, Any], inventory: dict[str, Any]) -> str:
    payload = {
        "task": "Create a report blueprint for an evidence-safe UK/Ireland D365 opportunity document.",
        "contract": [
            "Use only supplied evidence.",
            "Do not invent companies.",
            "Do not invent URLs.",
            "Do not invent contacts, emails, budgets, dissatisfaction, buying intent, product claims, or source facts.",
            "No email sending, Gmail, deployment, private/authenticated LinkedIn, tender/procurement-only sources, fake/sample/demo sources, or browser sessions.",
            "Missing information must be requested as bounded public follow-up, not invented.",
            "Return JSON only.",
        ],
        "schema": REPORT_BLUEPRINT_SCHEMA,
        "document_request": request,
        "evidence_inventory": inventory_summary_for_prompt(inventory),
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


def build_final_report_prompt(
    request: dict[str, Any],
    inventory: dict[str, Any],
    blueprint: dict[str, Any],
    follow_up_evidence: list[dict[str, Any]],
) -> str:
    payload = {
        "task": "Create the final structured report spec for deterministic Markdown/HTML/PDF rendering.",
        "contract": [
            "Use only supplied evidence and runner-supplied follow-up evidence.",
            "Every account must include at least one evidence_refs URL from allowed_evidence_urls.",
            "Do not invent companies, URLs, contacts, budgets, dissatisfaction, source facts, or buying intent.",
            "Keep public-sector, source-cleanup, installed-base-only, and image-only caveats visible.",
            "Return JSON only.",
        ],
        "schema": REPORT_SPEC_SCHEMA,
        "allowed_evidence_urls": inventory.get("allowed_evidence_urls") or [],
        "document_request": request,
        "blueprint": blueprint,
        "evidence_inventory": inventory_summary_for_prompt(inventory, include_excerpts=True),
        "follow_up_evidence": follow_up_evidence,
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


def inventory_summary_for_prompt(inventory: dict[str, Any], include_excerpts: bool = False) -> dict[str, Any]:
    accounts = []
    for account in inventory.get("accounts") or []:
        row = {
            "account": account.get("account"),
            "lead_status": account.get("lead_status"),
            "signal_strength": account.get("signal_strength"),
            "signal_type": account.get("signal_type"),
            "opportunity_signal": account.get("opportunity_signal"),
            "evidence_urls": [item.get("url") for item in account.get("evidence") or []],
            "do_not_claim_notes": account.get("do_not_claim_notes") or [],
            "remaining_uncertainty": account.get("remaining_uncertainty") or [],
        }
        if include_excerpts:
            row["evidence"] = account.get("evidence") or []
            row["why_this_matters_to_1bt"] = account.get("why_this_matters_to_1bt")
            row["commercial_opening"] = account.get("commercial_opening")
            row["value_of_signal"] = account.get("value_of_signal")
            row["intelligence_reading"] = account.get("intelligence_reading")
            row["board_relevance"] = account.get("board_relevance")
        accounts.append(row)
    return {
        "account_count": len(accounts),
        "accounts": accounts,
        "allowed_evidence_urls": inventory.get("allowed_evidence_urls") or [],
    }


def parse_report_blueprint(text: str) -> dict[str, Any]:
    data = parse_json_object(text)
    require_blueprint_fields(data)
    if data.get("style_preset") not in ALLOWED_STYLE_PRESETS:
        raise SchemaValidationError(f"unsupported style_preset: {data.get('style_preset')}")
    if not isinstance(data.get("section_plan"), list) or not data["section_plan"]:
        raise SchemaValidationError("report blueprint section_plan must be a non-empty list")
    if not isinstance(data.get("account_detail_fields"), list) or not data["account_detail_fields"]:
        raise SchemaValidationError("report blueprint account_detail_fields must be a non-empty list")
    data["missing_info_requests"] = normalize_missing_info_requests(data.get("missing_info_requests"))
    data["caveats"] = normalize_list(data.get("caveats"))
    data["do_not_claim_rules"] = normalize_list(data.get("do_not_claim_rules"))
    return data


def parse_report_spec(text: str) -> dict[str, Any]:
    data = parse_json_object(text)
    data = unwrap_report_spec(data)
    require_fields(data, REQUIRED_REPORT_SPEC_FIELDS, "report spec")
    if data.get("style_preset") not in ALLOWED_STYLE_PRESETS:
        raise SchemaValidationError(f"unsupported style_preset: {data.get('style_preset')}")
    if not isinstance(data.get("accounts"), list) or not data["accounts"]:
        raise SchemaValidationError("report spec accounts must be a non-empty list")
    for account in data.get("accounts") or []:
        require_account_fields(account)
    return data


def parse_report_spec_with_defaults(
    text: str,
    *,
    request: dict[str, Any],
    blueprint: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    data = unwrap_report_spec(parse_json_object(text))
    inventory_summary = inventory_summary_for_prompt(inventory, include_excerpts=True)
    fallback = default_report_spec(request, blueprint, inventory_summary)
    for field in ("title", "subtitle", "style_preset", "executive_snapshot", "signal_themes", "at_a_glance", "caveats", "appendix"):
        if not has_value(data.get(field)):
            data[field] = fallback[field]
    if not valid_account_blocks(data.get("accounts")):
        data["accounts"] = fallback["accounts"]
    if not valid_glance_blocks(data.get("at_a_glance")):
        data["at_a_glance"] = fallback["at_a_glance"]
    return parse_report_spec(json.dumps(data, ensure_ascii=True))


def unwrap_report_spec(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("report_spec", "final_report_spec", "report", "document"):
        nested = data.get(key)
        if isinstance(nested, dict):
            return nested
    return data


def valid_account_blocks(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for account in value:
        if not isinstance(account, dict):
            return False
        for field in REQUIRED_ACCOUNT_FIELDS:
            if field not in account or not has_value(account[field]):
                return False
    return True


def valid_glance_blocks(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    required = {"account", "signal_type", "strength", "pitch_lane", "evidence_refs"}
    for row in value:
        if not isinstance(row, dict):
            return False
        if any(not has_value(row.get(field)) for field in required):
            return False
    return True


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            data = vetting.parse_first_json_object(cleaned)
        except ValueError as exc:
            raise SchemaValidationError(str(exc)) from exc
    if not isinstance(data, dict):
        raise SchemaValidationError("expected JSON object")
    return data


def require_fields(data: dict[str, Any], fields: list[str], label: str) -> None:
    missing = [field for field in fields if field not in data or not has_value(data[field])]
    if missing:
        raise SchemaValidationError(f"{label} missing required fields: {', '.join(missing)}")


def require_blueprint_fields(data: dict[str, Any]) -> None:
    missing = []
    for field in REQUIRED_BLUEPRINT_FIELDS:
        if field not in data:
            missing.append(field)
        elif field != "missing_info_requests" and not has_value(data[field]):
            missing.append(field)
    if missing:
        raise SchemaValidationError(f"report blueprint missing required fields: {', '.join(missing)}")


def require_account_fields(account: dict[str, Any]) -> None:
    missing = []
    for field in REQUIRED_ACCOUNT_FIELDS:
        if field not in account:
            missing.append(field)
        elif field != "evidence_refs" and not has_value(account[field]):
            missing.append(field)
    if missing:
        raise SchemaValidationError(f"report account missing required fields: {', '.join(missing)}")


def normalize_missing_info_requests(value: Any) -> list[dict[str, Any]]:
    rows = []
    for item in normalize_list(value):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "target": clean_text(item.get("target")),
                "reason": clean_text(item.get("reason")),
                "queries": [clean_text(query) for query in normalize_list(item.get("queries")) if clean_text(query)],
                "max_searches": max(0, min(int(item.get("max_searches") or 2), 2)),
                "max_source_fetches": max(0, min(int(item.get("max_source_fetches") or 3), 3)),
            }
        )
    return rows


def validate_report_spec(spec: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    spec = parse_report_spec(json.dumps(spec, ensure_ascii=True))
    allowed = set(inventory.get("allowed_evidence_urls") or [])
    if not allowed:
        raise UnsafeReportSpecError("source map would have no allowed evidence URLs")
    for url in vetting.extract_urls(spec):
        if forbidden_report_url(url, ""):
            raise UnsafeReportSpecError(f"forbidden URL in report spec: {url}")
    for row in spec.get("at_a_glance") or []:
        validate_evidence_refs(row.get("evidence_refs") or [], allowed, "at_a_glance")
    for account in spec.get("accounts") or []:
        validate_evidence_refs(account.get("evidence_refs") or [], allowed, str(account.get("account") or "account"))
    return spec


def validate_evidence_refs(refs: list[str], allowed: set[str], label: str) -> None:
    if not refs:
        raise UnsafeReportSpecError(f"{label} has no evidence references")
    for ref in refs:
        ref_text = clean_text(ref)
        if ref_text not in allowed:
            raise UnsafeReportSpecError(f"{label} cites unsupported evidence reference: {ref_text}")
        if forbidden_report_url(ref_text, ""):
            raise UnsafeReportSpecError(f"{label} cites forbidden evidence reference: {ref_text}")


def build_report_composer_package(
    *,
    requirement: str,
    input_pack: Path | str,
    output_basename: str,
    output_dir: Path | str = EVIDENCE_DIR,
    source_checks: Path | str | None = None,
    style_reference_pdf: str | None = None,
    extra_evidence: list[Path | str] | None = None,
    live_ai: bool = False,
    live_browse: bool = False,
    required_project: str | None = None,
    model: str | None = None,
    composer_call: Any | None = None,
    followup_search_call: Any | None = None,
    source_fetch_call: Any | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    request = build_document_request(
        requirement=requirement,
        output_basename=output_basename,
        style_reference_pdf=style_reference_pdf,
    )
    inventory = build_evidence_inventory(
        input_pack=input_pack,
        source_checks=source_checks,
        extra_evidence=extra_evidence,
        style_reference_pdf=style_reference_pdf,
    )
    if not inventory.get("accounts"):
        raise SchemaValidationError("input pack contains no accounts with safe public evidence")

    client = None
    if live_ai or live_browse:
        enforce_report_project(required_project)
    if live_ai:
        client, client_info = make_report_client(model)
    else:
        client_info = {
            "model": report_model_name(model),
            "provider_path": "injected composer_call" if composer_call else "deterministic dry-run composer",
            "project": "local",
            "location": "local",
            "auth_mode": "dry-run",
        }
        composer_call = composer_call or deterministic_composer_call

    blueprint, blueprint_meta = run_composer_request(
        build_blueprint_prompt(request, inventory),
        stage="blueprint",
        request_index=1,
        client=client,
        client_info=client_info,
        composer_call=composer_call,
        parser=parse_report_blueprint,
    )
    follow_up_evidence = collect_missing_info_follow_up(
        blueprint=blueprint,
        inventory=inventory,
        live_browse=live_browse,
        followup_search_call=followup_search_call,
        source_fetch_call=source_fetch_call,
    )
    inventory = attach_follow_up_evidence(inventory, follow_up_evidence)
    report_spec, final_meta = run_composer_request(
        build_final_report_prompt(request, inventory, blueprint, follow_up_evidence),
        stage="final_report",
        request_index=2,
        client=client,
        client_info=client_info,
        composer_call=composer_call,
        parser=lambda text: parse_report_spec_with_defaults(
            text,
            request=request,
            blueprint=blueprint,
            inventory=inventory,
        ),
    )
    report_spec = validate_report_spec(report_spec, inventory)
    artifacts = render_report_artifacts(
        report_spec=report_spec,
        inventory=inventory,
        output_dir=output_dir,
        output_basename=request["output_basename"],
        browse_log=follow_up_evidence,
        request=request,
        blueprint=blueprint,
        request_records=[blueprint_meta, final_meta],
    )
    output = {
        "metadata": {
            "artifact_type": "uk_ie_d365_report_composer_output",
            "generated_at": now_utc(),
            "requirement": requirement,
            "output_basename": request["output_basename"],
            "style_preset": report_spec.get("style_preset"),
            "account_count": len(report_spec.get("accounts") or []),
            "follow_up_record_count": len(follow_up_evidence),
            "model": client_info.get("model"),
            "provider_path": client_info.get("provider_path"),
            "project": client_info.get("project"),
            "location": client_info.get("location"),
        },
        "document_request": request,
        "blueprint": blueprint,
        "report_spec": report_spec,
        "source_map": build_source_map(report_spec, inventory),
        "browse_log": follow_up_evidence,
        "request_records": [blueprint_meta, final_meta],
    }
    write_json(Path(artifacts["json"]), output)
    secret_scan = scan_report_secrets([Path(path) for key, path in artifacts.items() if key not in {"secret_scan"}])
    write_json(Path(artifacts["secret_scan"]), secret_scan)
    if not secret_scan["passed"]:
        raise RuntimeError(f"Secret scan failed: {artifacts['secret_scan']}")
    return {"output": output, "artifacts": artifacts}


def run_composer_request(
    prompt: str,
    *,
    stage: str,
    request_index: int,
    client: Any | None,
    client_info: dict[str, Any],
    composer_call: Any | None,
    parser: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    meta: dict[str, Any] = {"stage": stage, "request_index": request_index}
    try:
        if composer_call:
            response_text, usage, model_version = composer_call(prompt, stage, request_index)
        else:
            response_text, usage, model_version = call_report_model(
                client=client,
                model=client_info["model"],
                prompt=prompt,
            )
        meta.update({"usage_metadata": usage, "model_version": model_version})
        return parser(response_text), meta
    except Exception as exc:
        meta.update({"request_error_type": type(exc).__name__, "request_error": str(exc)[:500]})
        raise


def report_model_name(model_override: str | None = None) -> str:
    return (
        model_override
        or os.environ.get("D365_REPORT_MODEL")
        or os.environ.get("D365_REVIEW_MODEL")
        or os.environ.get("D365_GOOGLE_MODEL")
        or "gemini-2.5-flash"
    )


def make_report_client(model_override: str | None = None) -> tuple[Any, dict[str, Any]]:
    from google import genai

    prepare = getattr(lead_tools, "_prepare_google_native_env", None)
    if prepare:
        prepare()
    readiness = lead_tools.google_native_readiness()
    project = readiness.get("effective_project")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
    if not project:
        raise ProjectGuardError("Google project is unclear; refusing live report composition.")
    credentials = lead_tools.gcloud_account_credentials()
    client = genai.Client(
        vertexai=True,
        project=project,
        location=location,
        **({"credentials": credentials} if credentials else {}),
    )
    return client, {
        "model": report_model_name(model_override),
        "provider_path": DEFAULT_PROVIDER_PATH,
        "project": project,
        "location": location,
        "auth_mode": "gcloud_short_lived_access_token" if credentials else "ADC",
    }


def call_report_model(*, client: Any, model: str, prompt: str) -> tuple[str, dict[str, Any], str | None]:
    response = client.models.generate_content(model=model, contents=prompt)
    usage = getattr(response, "usage_metadata", None)
    usage_dict = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage or {})
    return str(getattr(response, "text", "") or ""), usage_dict, getattr(response, "model_version", None)


def deterministic_composer_call(prompt: str, stage: str, request_index: int):
    payload = json.loads(prompt)
    if stage == "blueprint":
        inventory = payload["evidence_inventory"]
        response = default_blueprint(payload["document_request"], inventory)
    else:
        response = default_report_spec(
            payload["document_request"],
            payload["blueprint"],
            payload["evidence_inventory"],
        )
    return json.dumps(response, ensure_ascii=True), {"total_token_count": 0}, "deterministic"


def default_blueprint(request: dict[str, Any], inventory_summary: dict[str, Any]) -> dict[str, Any]:
    account_count = int(inventory_summary.get("account_count") or 0)
    return {
        "title": "AI-Driven Opportunity Intelligence",
        "subtitle": f"{account_count} public-signal UK & Ireland Dynamics 365 opportunities",
        "audience": "1BT board and sales leadership",
        "board_purpose": clean_text(request.get("requirement")),
        "style_preset": "executive_landscape",
        "tone": "board-friendly, concise, and evidence-led",
        "section_plan": [
            "cover",
            "executive_snapshot",
            "at_a_glance_grid",
            "signal_themes",
            "account_details",
            "evidence_notes",
        ],
        "account_detail_fields": [
            "opportunity_signal",
            "why_this_matters_to_1bt",
            "commercial_opening",
            "value_of_signal",
            "intelligence_reading",
            "board_relevance",
        ],
        "missing_info_requests": [],
        "caveats": [
            "These are public-signal opportunity hypotheses, not claims of buying intent.",
            "Do not claim budget, dissatisfaction, incumbent displacement, or private information.",
        ],
        "do_not_claim_rules": [
            "Do not claim budget or active procurement intent.",
            "Do not claim current dissatisfaction unless public evidence explicitly says so.",
        ],
    }


def default_report_spec(
    request: dict[str, Any],
    blueprint: dict[str, Any],
    inventory_summary: dict[str, Any],
) -> dict[str, Any]:
    accounts = []
    glance = []
    for row in inventory_summary.get("accounts") or []:
        evidence_urls = [url for url in row.get("evidence_urls") or [] if url]
        if not evidence_urls:
            continue
        account = clean_text(row.get("account"))
        detail = {
            "account": account,
            "signal_strength": clean_text(row.get("signal_strength") or "promising"),
            "signal_type": clean_text(row.get("signal_type") or "d365_opportunity_signal"),
            "evidence_refs": [evidence_urls[0]],
            "opportunity_signal": clean_text(row.get("opportunity_signal") or "Public Microsoft business-app signal."),
            "why_this_matters_to_1bt": clean_text(
                row.get("why_this_matters_to_1bt")
                or "The signal creates a credible support, optimisation, reporting, or adoption conversation."
            ),
            "commercial_opening": clean_text(
                row.get("commercial_opening")
                or "Open with a careful evidence-led conversation about D365 support and optimisation."
            ),
            "value_of_signal": clean_text(
                row.get("value_of_signal")
                or "Named public evidence supports a practical 1BT sales hypothesis."
            ),
            "intelligence_reading": clean_text(
                row.get("intelligence_reading")
                or "Use this as a public-signal hypothesis and verify current state before outreach."
            ),
            "board_relevance": clean_text(
                row.get("board_relevance")
                or "Relevant to operational resilience, reporting, process performance, and platform value."
            ),
            "do_not_claim_notes": row.get("do_not_claim_notes") or blueprint.get("do_not_claim_rules") or [],
            "remaining_uncertainty": row.get("remaining_uncertainty") or ["Current support ownership is not public."],
        }
        accounts.append(detail)
        glance.append(
            {
                "account": account,
                "signal_type": detail["signal_type"],
                "strength": detail["signal_strength"],
                "pitch_lane": detail["commercial_opening"],
                "evidence_refs": [evidence_urls[0]],
            }
        )
    return {
        "title": blueprint.get("title") or "AI-Driven Opportunity Intelligence",
        "subtitle": blueprint.get("subtitle") or clean_text(request.get("requirement")),
        "style_preset": blueprint.get("style_preset") or "executive_landscape",
        "executive_snapshot": (
            f"This report turns {len(accounts)} public-source Dynamics 365 signals into "
            "evidence-led 1BT opportunity hypotheses."
        ),
        "signal_themes": sorted({account["signal_type"] for account in accounts}) or ["Dynamics 365 opportunity signals"],
        "at_a_glance": glance,
        "accounts": accounts,
        "caveats": blueprint.get("caveats") or [],
        "appendix": [
            "Source map stores evidence references, excerpts, verification status, and caveats.",
            "No Gmail, email sending, private LinkedIn, deployment, fake evidence, or tender-only sources were used.",
        ],
    }


def collect_missing_info_follow_up(
    *,
    blueprint: dict[str, Any],
    inventory: dict[str, Any],
    live_browse: bool,
    followup_search_call: Any | None,
    source_fetch_call: Any | None,
) -> list[dict[str, Any]]:
    if not live_browse:
        return []
    source_fetch_call = source_fetch_call or fetch_public_source
    evidence = []
    for request in blueprint.get("missing_info_requests") or []:
        target = clean_text(request.get("target"))
        search_results = []
        if followup_search_call:
            for query in (request.get("queries") or [])[: request.get("max_searches", 2)]:
                for item in followup_search_call(query, request) or []:
                    normalized = normalize_followup_item(item, request=request, query=query)
                    if normalized.get("url") and not forbidden_report_url(normalized["url"], normalized.get("snippet") or ""):
                        search_results.append(normalized)
                        evidence.append(normalized)
        urls = [item.get("url") for item in search_results if item.get("url")]
        urls.extend(evidence_urls_for_target(inventory, target))
        for url in list(dict.fromkeys(url for url in urls if url))[: request.get("max_source_fetches", 3)]:
            fetched = source_fetch_call(url, request)
            if fetched:
                normalized = normalize_followup_item(fetched, request=request, query=None, kind="source_fetch")
                if normalized.get("url") and not forbidden_report_url(normalized["url"], normalized.get("text_excerpt") or ""):
                    evidence.append(normalized)
    return evidence


def normalize_followup_item(
    item: Any,
    *,
    request: dict[str, Any],
    query: str | None,
    kind: str = "search_result",
) -> dict[str, Any]:
    if isinstance(item, lead_tools.SearchResult):
        return {
            "kind": kind,
            "target": request.get("target"),
            "query": query,
            "title": item.title,
            "url": item.url,
            "snippet": item.snippet,
            "source_name": item.source,
            "verified_live": False,
        }
    if isinstance(item, dict):
        row = dict(item)
        row.setdefault("kind", kind)
        row.setdefault("target", request.get("target"))
        row.setdefault("query", query)
        if row.get("final_url") and not row.get("url"):
            row["url"] = row["final_url"]
        return row
    return {"kind": kind, "target": request.get("target"), "query": query, "text": str(item)}


def fetch_public_source(url: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
    if forbidden_report_url(url, ""):
        return {"kind": "source_fetch", "url": url, "verified_live": False, "fetch_error": "forbidden_url"}
    started = now_utc()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Business_Intel/1.0 report-composer public-source check",
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.8,*/*;q=0.5",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            body = response.read(250_000)
            charset = response.headers.get_content_charset() or "utf-8"
            text = body.decode(charset, errors="replace")
            final_url = response.geturl()
            status = response.status
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {
            "kind": "source_fetch",
            "url": url,
            "source_name": source_name_from_url(url),
            "verified_live": False,
            "fetched_at": started,
            "fetch_error": str(exc)[:500],
        }
    return {
        "kind": "source_fetch",
        "url": url,
        "final_url": final_url,
        "source_name": source_name_from_url(final_url),
        "verified_live": 200 <= int(status or 0) < 400,
        "http_status": status,
        "fetched_at": now_utc(),
        "text_excerpt": clean_text(strip_html(text))[:1200],
    }


def attach_follow_up_evidence(inventory: dict[str, Any], follow_up_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    if not follow_up_evidence:
        return inventory
    inventory = json.loads(json.dumps(inventory))
    for item in follow_up_evidence:
        url = clean_text(item.get("final_url") or item.get("url"))
        target = clean_text(item.get("target"))
        if not url or forbidden_report_url(url, item.get("text_excerpt") or item.get("snippet") or ""):
            continue
        for account in inventory.get("accounts") or []:
            if target and vetting.normalize_company_for_match(target) not in vetting.normalize_company_for_match(account.get("account")):
                continue
            evidence = {
                "url": url,
                "original_url": clean_text(item.get("url")),
                "source_name": clean_text(item.get("source_name") or source_name_from_url(url)),
                "excerpt": clean_text(item.get("text_excerpt") or item.get("snippet")),
                "fetched_at": clean_text(item.get("fetched_at") or now_utc()),
                "verified_live": bool(item.get("verified_live")),
                "source_cleanup_needed": bool(item.get("fetch_error")),
                "allowed_claims": [clean_text(item.get("text_excerpt") or item.get("snippet"))],
            }
            if url not in {row.get("url") for row in account.get("evidence") or []}:
                account.setdefault("evidence", []).append(evidence)
            break
    inventory["allowed_evidence_urls"] = sorted(
        {
            evidence["url"]
            for account in inventory.get("accounts") or []
            for evidence in account.get("evidence") or []
            if evidence.get("url")
        }
    )
    inventory["evidence_by_url"] = {
        evidence["url"]: evidence
        for account in inventory.get("accounts") or []
        for evidence in account.get("evidence") or []
        if evidence.get("url")
    }
    return inventory


def evidence_urls_for_target(inventory: dict[str, Any], target: str) -> list[str]:
    normalized_target = vetting.normalize_company_for_match(target)
    urls = []
    for account in inventory.get("accounts") or []:
        normalized_account = vetting.normalize_company_for_match(account.get("account"))
        if normalized_target and normalized_target not in normalized_account and normalized_account not in normalized_target:
            continue
        urls.extend(item.get("url") for item in account.get("evidence") or [] if item.get("url"))
    return urls


def render_report_artifacts(
    *,
    report_spec: dict[str, Any],
    inventory: dict[str, Any],
    output_dir: Path | str,
    output_basename: str,
    browse_log: list[dict[str, Any]] | None = None,
    request: dict[str, Any] | None = None,
    blueprint: dict[str, Any] | None = None,
    request_records: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    basename = safe_basename(output_basename)
    report_spec = validate_report_spec(report_spec, inventory)
    paths = {
        "json": output_dir / f"{basename}.json",
        "markdown": output_dir / f"{basename}.md",
        "html": output_dir / f"{basename}.html",
        "pdf": output_dir / f"{basename}.pdf",
        "source_map": output_dir / f"{basename}_SOURCE_MAP.json",
        "browse_log": output_dir / f"{basename}_BROWSE_LOG.json",
        "qa": output_dir / f"{basename}_QA.json",
        "secret_scan": output_dir / f"{basename}_SECRET_SCAN.json",
    }
    source_map = build_source_map(report_spec, inventory)
    markdown = render_markdown(report_spec, source_map)
    html_text = render_html(report_spec, source_map)
    paths["markdown"].write_text(markdown, encoding="utf-8")
    paths["html"].write_text(html_text, encoding="utf-8")
    try:
        from uk_ie_d365_leads.tools.styled_pdf_tools import write_styled_report_pdf

        write_styled_report_pdf(
            paths["pdf"],
            report_spec,
            source_map,
            landscape=report_spec.get("style_preset") != "board_brief_portrait",
        )
    except ImportError:
        pdf_lines = pdf_lines_from_report(report_spec, source_map)
        write_simple_pdf(
            paths["pdf"],
            pdf_lines,
            landscape=report_spec.get("style_preset") != "board_brief_portrait",
        )
    write_json(paths["source_map"], source_map)
    write_json(paths["browse_log"], {"generated_at": now_utc(), "records": browse_log or []})
    qa = qa_rendered_artifacts(paths, report_spec=report_spec, source_map=source_map)
    write_json(paths["qa"], qa)
    if not qa["passed"]:
        raise RuntimeError(f"Report render QA failed: {paths['qa']}")
    return {key: str(path) for key, path in paths.items()}


def build_source_map(report_spec: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    evidence_by_url = inventory.get("evidence_by_url") or {}
    accounts = []
    for account in report_spec.get("accounts") or []:
        evidence_rows = []
        for ref in account.get("evidence_refs") or []:
            source = evidence_by_url.get(ref)
            if not source:
                raise UnsafeReportSpecError(f"missing source-map reference: {ref}")
            evidence_rows.append(
                {
                    "evidence_url": ref,
                    "source_name": source.get("source_name"),
                    "evidence_excerpt": source.get("excerpt"),
                    "fetched_at": source.get("fetched_at"),
                    "verified_live": bool(source.get("verified_live")),
                    "source_cleanup_needed": bool(source.get("source_cleanup_needed")),
                }
            )
        if not evidence_rows:
            raise UnsafeReportSpecError(f"{account.get('account')} has no evidence rows")
        accounts.append(
            {
                "account": account.get("account"),
                "signal_strength": account.get("signal_strength"),
                "signal_type": account.get("signal_type"),
                "evidence": evidence_rows,
                "do_not_claim_notes": account.get("do_not_claim_notes") or [],
                "remaining_uncertainty": account.get("remaining_uncertainty") or [],
            }
        )
    return {
        "artifact_type": "uk_ie_d365_report_composer_source_map",
        "generated_at": now_utc(),
        "title": report_spec.get("title"),
        "style_preset": report_spec.get("style_preset"),
        "account_count": len(accounts),
        "accounts": accounts,
    }


def render_markdown(report_spec: dict[str, Any], source_map: dict[str, Any]) -> str:
    lines = [
        f"# {report_spec['title']}",
        "",
        f"**{report_spec['subtitle']}**",
        "",
        report_spec["executive_snapshot"],
        "",
        "## Signal Themes",
        "",
    ]
    lines.extend(f"- {theme}" for theme in report_spec.get("signal_themes") or [])
    lines.extend(["", "## At A Glance", "", "| Account | Signal | Strength | Pitch lane |", "|---|---|---|---|"])
    for item in report_spec.get("at_a_glance") or []:
        lines.append(
            f"| {item.get('account')} | {item.get('signal_type')} | {item.get('strength')} | {clean_text(item.get('pitch_lane'))} |"
        )
    for account in report_spec.get("accounts") or []:
        lines.extend(
            [
                "",
                f"## {account.get('account')} - {account.get('signal_strength')}",
                "",
                f"- Signal type: {account.get('signal_type')}",
                f"- Opportunity signal: {account.get('opportunity_signal')}",
                f"- Why this matters to 1BT: {account.get('why_this_matters_to_1bt')}",
                f"- Commercial opening: {account.get('commercial_opening')}",
                f"- Value of signal: {account.get('value_of_signal')}",
                f"- Intelligence reading: {account.get('intelligence_reading')}",
                f"- Board relevance: {account.get('board_relevance')}",
                f"- Evidence: {', '.join(account.get('evidence_refs') or [])}",
                f"- Do not claim: {'; '.join(account.get('do_not_claim_notes') or [])}",
                f"- Remaining uncertainty: {'; '.join(account.get('remaining_uncertainty') or [])}",
            ]
        )
    lines.extend(["", "## Caveats", ""])
    lines.extend(f"- {item}" for item in report_spec.get("caveats") or [])
    lines.extend(["", "## Evidence Appendix", ""])
    for account in source_map.get("accounts") or []:
        lines.append(f"- {account['account']}: {', '.join(item['evidence_url'] for item in account['evidence'])}")
    return "\n".join(lines) + "\n"


def render_html(report_spec: dict[str, Any], source_map: dict[str, Any]) -> str:
    preset = report_spec.get("style_preset")
    css = css_for_preset(preset)
    account_cards = []
    for account in report_spec.get("accounts") or []:
        account_cards.append(
            f"""
<section class="account">
  <div class="account-head">
    <h2>{esc(account.get('account'))}</h2>
    <span class="badge">{esc(account.get('signal_strength'))}</span>
  </div>
  <p class="signal">{esc(account.get('signal_type'))}</p>
  <div class="grid">
    {html_field('Opportunity signal', account.get('opportunity_signal'))}
    {html_field('Why this matters to 1BT', account.get('why_this_matters_to_1bt'))}
    {html_field('Commercial opening', account.get('commercial_opening'))}
    {html_field('Value of the signal', account.get('value_of_signal'))}
    {html_field('Intelligence reading', account.get('intelligence_reading'))}
    {html_field('Board relevance', account.get('board_relevance'))}
  </div>
  <div class="notes">
    <p><strong>Evidence:</strong> {esc(', '.join(account.get('evidence_refs') or []))}</p>
    <p><strong>Do not claim:</strong> {esc('; '.join(account.get('do_not_claim_notes') or []))}</p>
    <p><strong>Remaining uncertainty:</strong> {esc('; '.join(account.get('remaining_uncertainty') or []))}</p>
  </div>
</section>
"""
        )
    glance = "".join(
        f"<tr><td>{esc(item.get('account'))}</td><td>{esc(item.get('signal_type'))}</td><td>{esc(item.get('strength'))}</td><td>{esc(item.get('pitch_lane'))}</td></tr>"
        for item in report_spec.get("at_a_glance") or []
    )
    themes = "".join(f"<li>{esc(theme)}</li>" for theme in report_spec.get("signal_themes") or [])
    caveats = "".join(f"<li>{esc(item)}</li>" for item in report_spec.get("caveats") or [])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{esc(report_spec.get('title'))}</title>
<style>{css}</style>
</head>
<body class="{esc(preset)}">
<section class="cover">
  <div class="kicker">1BT Sales Intelligence</div>
  <h1>{esc(report_spec.get('title'))}</h1>
  <p class="subtitle">{esc(report_spec.get('subtitle'))}</p>
  <p>{esc(report_spec.get('executive_snapshot'))}</p>
</section>
<section class="page">
  <h2>Signal Themes</h2>
  <ul class="themes">{themes}</ul>
  <h2>At A Glance</h2>
  <table><thead><tr><th>Account</th><th>Signal</th><th>Strength</th><th>Pitch lane</th></tr></thead><tbody>{glance}</tbody></table>
</section>
{''.join(account_cards)}
<section class="page">
  <h2>Caveats</h2>
  <ul>{caveats}</ul>
</section>
</body>
</html>
"""


def css_for_preset(preset: str) -> str:
    orientation = "landscape" if preset != "board_brief_portrait" else "portrait"
    density = "10.8px" if preset == "dense_pipeline_review" else "12px"
    return f"""
@page {{ size: A4 {orientation}; margin: 14mm; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: Aptos, Segoe UI, Arial, sans-serif; color: #172033; background: #f3f6f8; }}
.cover, .page, .account {{ page-break-after: always; background: #fff; padding: 18mm; min-height: 180mm; }}
.cover {{ background: linear-gradient(135deg, #0b2239, #35566a); color: white; }}
.kicker {{ color: #f2c15f; text-transform: uppercase; font-weight: 800; font-size: 12px; }}
h1 {{ font-size: 40px; line-height: 1.05; margin: 12mm 0 6mm; letter-spacing: 0; }}
h2 {{ color: #0b2a42; font-size: 22px; margin: 0 0 5mm; letter-spacing: 0; }}
.cover h1, .cover h2 {{ color: white; }}
.subtitle {{ font-size: 18px; color: #e9f1f7; max-width: 220mm; }}
p, li, td, th {{ font-size: {density}; line-height: 1.4; }}
table {{ width: 100%; border-collapse: collapse; margin: 4mm 0 9mm; }}
th {{ background: #12395b; color: white; text-align: left; padding: 3mm; }}
td {{ border-bottom: 1px solid #dce4ec; padding: 3mm; vertical-align: top; }}
.account-head {{ display: flex; justify-content: space-between; gap: 10mm; align-items: start; }}
.badge {{ background: #eaf6ef; color: #1f7a48; border-radius: 999px; padding: 2mm 4mm; font-weight: 800; white-space: nowrap; }}
.signal {{ color: #526070; font-weight: 700; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 4mm; }}
.field {{ border: 1px solid #dde6ee; border-left: 4px solid #e7ad3f; background: #f8fafc; padding: 4mm; min-height: 28mm; }}
.field h3 {{ margin: 0 0 2mm; color: #0b2a42; font-size: 12px; text-transform: uppercase; }}
.notes {{ margin-top: 5mm; background: #fff8eb; border: 1px solid #f1d79f; padding: 4mm; }}
"""


def html_field(label: str, body: Any) -> str:
    return f'<div class="field"><h3>{esc(label)}</h3><p>{esc(body)}</p></div>'


def pdf_lines_from_report(report_spec: dict[str, Any], source_map: dict[str, Any]) -> list[str]:
    lines = [
        report_spec.get("title") or "",
        report_spec.get("subtitle") or "",
        "",
        report_spec.get("executive_snapshot") or "",
        "",
        "Signal Themes:",
    ]
    lines.extend(f"- {theme}" for theme in report_spec.get("signal_themes") or [])
    lines.extend(["", "At A Glance:"])
    for item in report_spec.get("at_a_glance") or []:
        lines.append(f"- {item.get('account')}: {item.get('signal_type')} ({item.get('strength')})")
    for account in report_spec.get("accounts") or []:
        lines.extend(
            [
                "",
                f"{account.get('account')} - {account.get('signal_strength')}",
                f"Signal: {account.get('opportunity_signal')}",
                f"Why it matters: {account.get('why_this_matters_to_1bt')}",
                f"Commercial opening: {account.get('commercial_opening')}",
                f"Value: {account.get('value_of_signal')}",
                f"Reading: {account.get('intelligence_reading')}",
                f"Board relevance: {account.get('board_relevance')}",
                f"Evidence: {', '.join(account.get('evidence_refs') or [])}",
                f"Do not claim: {'; '.join(account.get('do_not_claim_notes') or [])}",
                f"Remaining uncertainty: {'; '.join(account.get('remaining_uncertainty') or [])}",
            ]
        )
    lines.extend(["", "Caveats:"])
    lines.extend(f"- {item}" for item in report_spec.get("caveats") or [])
    lines.extend(["", f"Source map accounts: {source_map.get('account_count')}"])
    return wrapped_lines(lines, width=105)


def write_simple_pdf(path: Path, lines: list[str], *, landscape: bool = True) -> None:
    width, height = (842, 595) if landscape else (595, 842)
    max_lines = 34 if landscape else 48
    pages = [lines[index:index + max_lines] for index in range(0, len(lines), max_lines)] or [[]]
    objects: list[bytes] = []
    page_ids = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    next_id = 4
    for page_lines in pages:
        page_id = next_id
        content_id = next_id + 1
        page_ids.append(page_id)
        content = pdf_content_stream(page_lines, width=width, height=height)
        page_obj = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("latin-1")
        content_obj = b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream"
        objects.append(page_obj)
        objects.append(content_obj)
        next_id += 2
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")
    write_pdf_objects(path, objects)


def pdf_content_stream(lines: list[str], *, width: int, height: int) -> bytes:
    commands = ["BT", "/F1 10 Tf", "48 548 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -14 Td")
        commands.append(f"({pdf_escape(line)}) Tj")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", errors="replace")


def write_pdf_objects(path: Path, objects: list[bytes]) -> None:
    chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    current = len(chunks[0])
    for index, obj in enumerate(objects, start=1):
        offsets.append(current)
        chunk = f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
        chunks.append(chunk)
        current += len(chunk)
    xref_offset = current
    xref = [f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    path.write_bytes(b"".join(chunks + xref + [trailer]))


def pdf_escape(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def qa_rendered_artifacts(paths: dict[str, Path], *, report_spec: dict[str, Any], source_map: dict[str, Any]) -> dict[str, Any]:
    findings = []
    for key in ("markdown", "html", "pdf", "source_map", "browse_log"):
        path = paths[key]
        if not path.exists() or path.stat().st_size <= 0:
            findings.append(f"{key}_missing_or_empty")
    pdf_bytes = paths["pdf"].read_bytes() if paths["pdf"].exists() else b""
    if not pdf_bytes.startswith(b"%PDF"):
        findings.append("pdf_header_missing")
    page_count = len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))
    if page_count < 1:
        findings.append("pdf_page_count_zero")
    if len(report_spec.get("accounts") or []) != source_map.get("account_count"):
        findings.append("source_map_account_count_mismatch")
    return {
        "artifact_type": "uk_ie_d365_report_composer_qa",
        "generated_at": now_utc(),
        "passed": not findings,
        "findings": findings,
        "pdf_page_count": page_count,
        "pdf_size_bytes": len(pdf_bytes),
        "account_count": len(report_spec.get("accounts") or []),
    }


def scan_report_secrets(paths: list[Path]) -> dict[str, Any]:
    scan = vetting.scan_secret_patterns(paths)
    scan["artifact_type"] = "uk_ie_d365_report_composer_secret_scan"
    return scan


def enforce_report_project(required_project: str | None) -> dict[str, Any]:
    if required_project:
        os.environ.setdefault("D365_GOOGLE_PROJECT", required_project)
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", required_project)
    try:
        return lead_tools.require_google_project(required_project)
    except RuntimeError as exc:
        raise ProjectGuardError(str(exc)) from exc


def forbidden_report_url(url: str, text: str) -> bool:
    value = clean_text(url)
    lower = value.lower()
    if not value.startswith("http"):
        return True
    if any(term in lower for term in FORBIDDEN_FINAL_URL_TERMS):
        return True
    if lead_tools.private_linkedin_source(value):
        return True
    if lead_tools.fake_or_example_source(text, value):
        return True
    if lead_tools.tender_or_procurement_source(text, value):
        return True
    return False


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | tuple | set):
        return bool(value)
    if isinstance(value, dict):
        return bool(value)
    return True


def normalize_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def first_text(value: Any) -> str:
    for item in normalize_list(value):
        text = clean_text(item)
        if text:
            return text
    return ""


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def source_name_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc or parsed.path.split("/")[0]
    return re.sub(r"^www\.", "", host)


def strip_html(value: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", value, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def wrapped_lines(lines: list[str], width: int) -> list[str]:
    output = []
    for line in lines:
        if not clean_text(line):
            output.append("")
            continue
        output.extend(textwrap.wrap(clean_text(line), width=width) or [""])
    return output


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
