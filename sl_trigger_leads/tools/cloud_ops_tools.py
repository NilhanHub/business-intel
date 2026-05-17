"""Safe cloud/runtime diagnostics for the Business_Intel ADK agent.

These tools are intentionally read-only from inside Agent Runtime. They never
return secret values, API keys, access tokens, or raw bulk Hunter email lists.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .contact_resolver_tools import (
    discover_contact_live_search_provider,
    resolve_contact_routes_from_text,
)
from .live_contact_search_tools import normalize_company_domain

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or "business-intel-123"
PROJECT_NUMBER = os.environ.get("GOOGLE_CLOUD_PROJECT_NUMBER") or "44345068412"
REGION = os.environ.get("GOOGLE_CLOUD_REGION") or "us-central1"
REASONING_ENGINE_ID = (
    os.environ.get("BUSINESS_INTEL_REASONING_ENGINE_ID") or "3155700076542689280"
)
RUNTIME_SERVICE_ACCOUNT = (
    os.environ.get("BUSINESS_INTEL_EFFECTIVE_IDENTITY")
    or "agents.global.org-785760668571.system.id.goog/resources/aiplatform/projects/44345068412/locations/us-central1/reasoningEngines/3155700076542689280"
)
HUNTER_SECRET_NAME = "HUNTER_API_KEY"
HUNTER_BASE_URL = "https://api.hunter.io/v2"

SECRET_MARKERS = (
    "access_" + "token",
    "refresh_" + "token",
    "client_" + "secret",
    "api_" + "key=",
    "bear" + "er ",
)


def diagnose_hunter_runtime() -> dict[str, Any]:
    """Diagnose Hunter from inside the current runtime without exposing the key."""
    key = _hunter_key()
    result: dict[str, Any] = {
        "tool": "diagnose_hunter_runtime",
        "checked_at": _now(),
        "hunter_env_present": bool(key),
        "hunter_env_length": len(key),
        "hunter_env_sha256_prefix": _sha256_prefix(key),
        "hunter_account_check_status": "NOT_CONFIGURED",
        "hunter_account_email_domain": None,
        "hunter_domain_search_test_domain": "wso2.com",
        "hunter_domain_search_status": "NOT_CONFIGURED",
        "hunter_domain_search_result_count": 0,
        "hunter_first_result_safe_summary": None,
        "sanitized_exception_class": None,
        "sanitized_exception_message": None,
        "secrets_exposed": False,
    }
    if not key:
        return _assert_no_secret_output(result)

    account = _hunter_api_get("account", {"api_key": key})
    result["hunter_account_check_status"] = account["status"]
    result["sanitized_exception_class"] = account.get("exception_class")
    result["sanitized_exception_message"] = account.get("message")
    if account["status"] == "OK":
        email = ((account.get("payload") or {}).get("data") or {}).get("email") or ""
        result["hunter_account_email_domain"] = email.split("@")[-1] if "@" in email else None

    domain = run_single_company_hunter_probe("wso2.com")
    result["hunter_domain_search_status"] = domain["status"]
    result["hunter_domain_search_result_count"] = domain["result_count"]
    result["hunter_first_result_safe_summary"] = (
        domain["top_safe_summaries"][0] if domain.get("top_safe_summaries") else None
    )
    if domain.get("sanitized_exception_class"):
        result["sanitized_exception_class"] = domain["sanitized_exception_class"]
        result["sanitized_exception_message"] = domain["sanitized_exception_message"]
    return _assert_no_secret_output(result)


def check_runtime_self_identity() -> dict[str, Any]:
    """Return safe runtime identity/context signals available from the process."""
    metadata_email = _metadata_get(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
    )
    metadata_project = _metadata_get(
        "http://metadata.google.internal/computeMetadata/v1/project/project-id"
    )
    result = {
        "tool": "check_runtime_self_identity",
        "checked_at": _now(),
        "expected_project_id": PROJECT_ID,
        "expected_project_number": PROJECT_NUMBER,
        "expected_region": REGION,
        "expected_reasoning_engine_id": REASONING_ENGINE_ID,
        "expected_runtime_service_account": RUNTIME_SERVICE_ACCOUNT,
        "metadata_service_account_email": metadata_email.get("value"),
        "metadata_project_id": metadata_project.get("value"),
        "metadata_status": "OK"
        if metadata_email.get("value") or metadata_project.get("value")
        else "UNAVAILABLE",
        "metadata_error": metadata_email.get("error") or metadata_project.get("error"),
        "env_context": {
            key: os.environ.get(key)
            for key in (
                "GOOGLE_CLOUD_PROJECT",
                "GOOGLE_CLOUD_REGION",
                "GOOGLE_CLOUD_LOCATION",
                "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY",
                "BUSINESS_INTEL_REASONING_ENGINE_ID",
                "BUSINESS_INTEL_EFFECTIVE_IDENTITY",
                "K_SERVICE",
                "K_REVISION",
                "AGENT_VERSION",
            )
            if os.environ.get(key)
        },
    }
    return _assert_no_secret_output(result)


def check_contact_resolver_provider_status() -> dict[str, Any]:
    """Explain current resolver/search/Hunter provider status."""
    status = discover_contact_live_search_provider()
    hunter_configured = bool(status.get("hunter_configured"))
    why = (
        "Hunter key is present. Domain Search runs only after the resolver finds a real company domain."
        if hunter_configured
        else "HUNTER_API_KEY is not present in this runtime environment."
    )
    return _assert_no_secret_output(
        {
            "tool": "check_contact_resolver_provider_status",
            "checked_at": _now(),
            "selected_provider": status.get("selected_provider"),
            "adk_google_search_available": status.get("adk_google_search_available"),
            "hunter_enabled": bool((status.get("fallback_hooks") or {}).get("hunter", {}).get("enabled")),
            "hunter_configured": hunter_configured,
            "hunter_status": status.get("hunter_status"),
            "why_hunter_is_or_is_not_being_used": why,
            "live_web_search_enabled": status.get("live_web_search_enabled"),
            "setup_message": status.get("setup_message"),
        }
    )


def run_single_company_hunter_probe(domain: str = "wso2.com") -> dict[str, Any]:
    """Run a sanitized Hunter Domain Search probe for one real domain."""
    clean_domain = normalize_company_domain(domain) or "wso2.com"
    key = _hunter_key()
    result: dict[str, Any] = {
        "tool": "run_single_company_hunter_probe",
        "domain": clean_domain,
        "status": "NOT_CONFIGURED",
        "result_count": 0,
        "top_safe_summaries": [],
        "sanitized_exception_class": None,
        "sanitized_exception_message": None,
        "secrets_exposed": False,
    }
    if not key:
        return _assert_no_secret_output(result)
    response = _hunter_api_get(
        "domain-search",
        {"domain": clean_domain, "limit": 5, "api_key": key},
    )
    result["status"] = response["status"]
    if response["status"] != "OK":
        result["sanitized_exception_class"] = response.get("exception_class")
        result["sanitized_exception_message"] = response.get("message")
        return _assert_no_secret_output(result)
    emails = ((response.get("payload") or {}).get("data") or {}).get("emails") or []
    result["result_count"] = len(emails)
    result["top_safe_summaries"] = [_safe_hunter_email_summary(item) for item in emails[:5]]
    return _assert_no_secret_output(result)


def run_contact_resolver_smoke(lead_text: str | None = None) -> dict[str, Any]:
    """Run the same explicit-text Contact Resolver path used by Gemini Enterprise."""
    text = lead_text or (
        "Lead 1:\n"
        "company_name: WSO2\n"
        "signal_summary: Enterprise software company; test Hunter/domain/contact route behavior.\n"
        "signal_source_url: https://wso2.com/contact/\n"
        "service_bucket: Software Development\n"
        "country: Sri Lanka\n"
    )
    result = resolve_contact_routes_from_text(text, max_leads=1, dry_run=False)
    item = (result.get("results") or [{}])[0]
    summary = item.get("search_summary") or {}
    route = item.get("best_contact_route") or {}
    smoke = {
        "tool": "run_contact_resolver_smoke",
        "checked_at": _now(),
        "resolved_count": result.get("resolved_count"),
        "company": item.get("company"),
        "hunter_participated": bool(
            summary.get("hunter_domain_search_attempted")
            or summary.get("hunter_email_finder_attempted")
        ),
        "hunter_status": summary.get("hunter_status"),
        "hunter_domain_search_attempted": summary.get("hunter_domain_search_attempted"),
        "hunter_email_finder_attempted": summary.get("hunter_email_finder_attempted"),
        "hunter_domains_attempted": summary.get("hunter_domains_attempted"),
        "chosen_route": {
            "type": route.get("type"),
            "name": route.get("name"),
            "role": route.get("role"),
            "email_domain": _email_domain(route.get("email")),
            "url": route.get("url"),
            "confidence": route.get("confidence"),
            "hunter_status": route.get("hunter_status"),
            "reason": route.get("reason"),
            "evidence_urls": route.get("evidence_urls"),
        },
        "compact_output": result.get("compact_output"),
        "sending_enabled": result.get("sending_enabled"),
    }
    return _assert_no_secret_output(smoke)


def search_runtime_logs(query: str = "HUNTER", limit: int = 20) -> dict[str, Any]:
    """Search Cloud Logging from runtime credentials when permitted."""
    token_result = _google_access_token("https://www.googleapis.com/auth/cloud-platform")
    if token_result["status"] != "OK":
        return {
            "tool": "search_runtime_logs",
            "status": "BLOCKED",
            "reason": "BLOCKED: no tool/action available for this check",
            "detail": token_result.get("message"),
        }
    filter_text = _safe_log_query(query)
    body = {
        "resourceNames": [f"projects/{PROJECT_ID}"],
        "filter": filter_text,
        "orderBy": "timestamp desc",
        "pageSize": max(1, min(int(limit or 20), 50)),
    }
    response = _google_json_post(
        "https://logging.googleapis.com/v2/entries:list",
        token_result["token"],
        body,
    )
    if response["status"] != "OK":
        return {
            "tool": "search_runtime_logs",
            "status": "BLOCKED",
            "reason": "BLOCKED: no tool/action available for this check",
            "detail": response.get("message"),
            "exception_class": response.get("exception_class"),
        }
    entries = (response.get("payload") or {}).get("entries") or []
    safe_entries = []
    for entry in entries[: max(1, min(int(limit or 20), 50))]:
        safe_entries.append(
            {
                "timestamp": entry.get("timestamp"),
                "logName": entry.get("logName"),
                "resource_type": (entry.get("resource") or {}).get("type"),
                "text_preview": _sanitize_text(json.dumps(entry.get("jsonPayload") or entry.get("textPayload") or ""))[:500],
            }
        )
    return _assert_no_secret_output(
        {
            "tool": "search_runtime_logs",
            "status": "OK",
            "query": query,
            "result_count": len(entries),
            "entries": safe_entries,
        }
    )


def check_secret_manager_access() -> dict[str, Any]:
    """Check Secret Manager access to HUNTER_API_KEY without returning the value."""
    token_result = _google_access_token("https://www.googleapis.com/auth/cloud-platform")
    response = {"status": "BLOCKED", "message": token_result.get("message")}
    if token_result["status"] == "OK":
        url = (
            f"https://secretmanager.googleapis.com/v1/projects/{PROJECT_ID}/secrets/"
            f"{HUNTER_SECRET_NAME}/versions/latest:access"
        )
        response = _google_json_get(url, token_result["token"])
    if response["status"] != "OK":
        response = _secret_manager_access_via_adc()
    result = {
        "tool": "check_secret_manager_access",
        "secret": HUNTER_SECRET_NAME,
        "status": response["status"],
        "value_present": False,
        "value_length": 0,
        "value_sha256_prefix": None,
        "sanitized_exception_class": response.get("exception_class"),
        "sanitized_exception_message": response.get("message"),
    }
    if response["status"] == "OK":
        data = ((response.get("payload") or {}).get("payload") or {}).get("data")
        value = _decode_secret_payload(data)
        result.update(
            {
                "value_present": bool(value),
                "value_length": len(value),
                "value_sha256_prefix": _sha256_prefix(value),
                "sanitized_exception_class": None,
                "sanitized_exception_message": None,
            }
        )
    return _assert_no_secret_output(result)


def _secret_manager_access_via_adc() -> dict[str, Any]:
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{PROJECT_ID}/secrets/{HUNTER_SECRET_NAME}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return {
            "status": "OK",
            "payload": {"payload": {"data": response.payload.data}},
        }
    except Exception as exc:  # noqa: BLE001 - diagnostics must stay safe.
        return {
            "status": "BLOCKED",
            "message": str(exc),
            "exception_class": exc.__class__.__name__,
        }


def cloud_ops_readiness_report() -> dict[str, Any]:
    """Run the core safe diagnostics and return a compact readiness table."""
    hunter = diagnose_hunter_runtime()
    identity = check_runtime_self_identity()
    provider = check_contact_resolver_provider_status()
    secret = check_secret_manager_access()
    logs = search_runtime_logs("HUNTER OR NOT_CONFIGURED OR AUTH_FAILED", limit=5)
    rows = [
        {
            "check": "Hunter env/account",
            "status": hunter.get("hunter_account_check_status"),
            "detail": f"env={hunter.get('hunter_env_present')} domain={hunter.get('hunter_account_email_domain')}",
        },
        {
            "check": "Hunter WSO2 domain search",
            "status": hunter.get("hunter_domain_search_status"),
            "detail": f"count={hunter.get('hunter_domain_search_result_count')}",
        },
        {
            "check": "Runtime identity",
            "status": identity.get("metadata_status"),
            "detail": identity.get("metadata_service_account_email") or identity.get("metadata_error"),
        },
        {
            "check": "Contact Resolver providers",
            "status": "OK" if provider.get("live_web_search_enabled") else "NOT_CONFIGURED",
            "detail": provider.get("why_hunter_is_or_is_not_being_used"),
        },
        {
            "check": "Secret Manager access",
            "status": secret.get("status"),
            "detail": f"present={secret.get('value_present')} hash={secret.get('value_sha256_prefix')}",
        },
        {
            "check": "Cloud Logging access",
            "status": logs.get("status"),
            "detail": f"count={logs.get('result_count')}" if logs.get("status") == "OK" else logs.get("reason"),
        },
    ]
    return _assert_no_secret_output(
        {
            "tool": "cloud_ops_readiness_report",
            "checked_at": _now(),
            "project_id": PROJECT_ID,
            "reasoning_engine": f"projects/{PROJECT_NUMBER}/locations/{REGION}/reasoningEngines/{REASONING_ENGINE_ID}",
            "rows": rows,
            "ready_for_hunter_runtime": (
                hunter.get("hunter_account_check_status") == "OK"
                and hunter.get("hunter_domain_search_status") == "OK"
            ),
        }
    )


def _hunter_key() -> str:
    return str(os.environ.get(HUNTER_SECRET_NAME) or "").strip()


def _hunter_api_get(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        url = f"{HUNTER_BASE_URL}/{endpoint}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Business_Intel_Runtime_Diagnostics/1.0"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"status": "OK", "payload": payload}
    except Exception as exc:
        message = _sanitize_text(str(exc))[:240]
        status = "AUTH_FAILED" if "401" in message or "403" in message else "REQUEST_FAILED"
        return {
            "status": status,
            "exception_class": type(exc).__name__,
            "message": message,
        }


def _safe_hunter_email_summary(item: dict[str, Any]) -> dict[str, Any]:
    value = str(item.get("value") or item.get("email") or "")
    verification = item.get("verification") if isinstance(item.get("verification"), dict) else {}
    return {
        "name": " ".join(part for part in (item.get("first_name"), item.get("last_name")) if part) or None,
        "role": item.get("position"),
        "domain": _email_domain(value) or normalize_company_domain(value),
        "verification_status": verification.get("status"),
        "confidence": item.get("confidence"),
        "sources_count": len(item.get("sources") or []),
    }


def _google_access_token(scope: str) -> dict[str, Any]:
    try:
        import google.auth
        from google.auth.transport.requests import Request

        credentials, _ = google.auth.default(scopes=[scope])
        credentials.refresh(Request())
        return {"status": "OK", "token": credentials.token}
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "exception_class": type(exc).__name__,
            "message": _sanitize_text(str(exc))[:240],
        }


def _google_json_get(url: str, token: str) -> dict[str, Any]:
    return _google_request("GET", url, token)


def _google_json_post(url: str, token: str, body: dict[str, Any]) -> dict[str, Any]:
    return _google_request("POST", url, token, body)


def _google_request(
    method: str,
    url: str,
    token: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8")
        return {"status": "OK", "payload": json.loads(text) if text else {}}
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "exception_class": type(exc).__name__,
            "message": _sanitize_text(str(exc))[:240],
        }


def _metadata_get(url: str) -> dict[str, Any]:
    try:
        request = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
        with urllib.request.urlopen(request, timeout=1.5) as response:
            return {"value": response.read().decode("utf-8"), "error": None}
    except Exception as exc:
        return {"value": None, "error": f"{type(exc).__name__}: {_sanitize_text(str(exc))[:160]}"}


def _decode_secret_payload(data: str | bytes | None) -> str:
    if not data:
        return ""
    import base64

    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace").strip()
    return base64.b64decode(data.encode("utf-8")).decode("utf-8", errors="replace").strip()


def _safe_log_query(query: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_ .:/@=-]+", " ", str(query or "HUNTER")).strip()
    terms = [term for term in clean.split()[:8] if term.upper() not in {"OR", "AND"}]
    if not terms:
        terms = ["HUNTER"]
    return " OR ".join(f'"{term}"' for term in terms)


def _email_domain(email: str | None) -> str | None:
    value = str(email or "")
    return value.rsplit("@", 1)[1].lower() if "@" in value else None


def _sha256_prefix(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_text(value: str) -> str:
    text = str(value or "")
    key = _hunter_key()
    if key:
        text = text.replace(key, "REDACTED")
    text = re.sub(r"api_key=[^&\\s]+", "api_key=REDACTED", text, flags=re.I)
    text = re.sub(r"key=[^&\\s]+", "key=REDACTED", text, flags=re.I)
    return text


def _assert_no_secret_output(result: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(result, sort_keys=True).lower()
    for marker in SECRET_MARKERS:
        if marker in serialized:
            raise ValueError("Secret-like marker detected in cloud ops diagnostic output.")
    return result
