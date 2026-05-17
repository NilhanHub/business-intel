from __future__ import annotations

import html
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from .source_health import classify_failure
from .source_recovery import recover_source_url
from .source_registry import load_source_registry


USER_AGENT = "Business_Intel/0.4 (+local ADK public-source lead intelligence; polite fetch)"
TIMEOUT_SECONDS = 12


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _decode(body: bytes, headers: Any) -> str:
    content_type = headers.get("Content-Type", "") if headers else ""
    match = re.search(r"charset=([\w.-]+)", content_type, re.I)
    encoding = match.group(1) if match else "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def fetch_url(url: str, timeout_seconds: int = TIMEOUT_SECONDS) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/rss+xml;q=0.9,*/*;q=0.8"})
    started = time.perf_counter()
    fetched_at = _now()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(1_500_000)
            return {
                "ok": True,
                "url": response.geturl(),
                "status_code": getattr(response, "status", 200),
                "content_type": response.headers.get("Content-Type", ""),
                "text": _decode(body, response.headers),
                "fetched_at": fetched_at,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "url": url,
            "status_code": exc.code,
            "error": f"HTTPError: {exc.reason}",
            "text": "",
            "fetched_at": fetched_at,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": url,
            "status_code": None,
            "error": f"{type(exc).__name__}: {exc}",
            "text": "",
            "fetched_at": fetched_at,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }


def strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h1|h2|h3|a)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t\r\f\v]+", " ", text)


def extract_links(raw: str, base_url: str) -> list[dict[str, str]]:
    links = []
    for match in re.finditer(r'(?is)<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', raw):
        href = html.unescape(match.group(1)).strip()
        label = strip_html(match.group(2)).strip()
        if not href or href.startswith("#") or not label:
            continue
        links.append({"url": urljoin(base_url, href), "text": re.sub(r"\s+", " ", label)})
    return links


def fetch_live_sources(source_limit: int = 4) -> dict[str, Any]:
    """Fetch enabled live public sources from the local registry with polite timeouts."""
    source_limit = max(1, min(int(source_limit), 10))
    results = []
    failures = []
    for source in load_source_registry(enabled_only=True)[:source_limit]:
        configured_url = source["base_url"]
        fetched = fetch_url(configured_url)
        record = _record_from_fetch(source, fetched, configured_url, configured_url)
        if fetched["ok"]:
            record["fetch_status"] = "success"
        else:
            failure_type = classify_failure(fetched)
            recovery = recover_source_url(
                source,
                {
                    "failed_url": configured_url,
                    "failure_type": failure_type,
                    "status_code": fetched.get("status_code"),
                    "original_source_type": source.get("type", ""),
                    "search_hint": source.get("notes", ""),
                },
            )
            record["error"] = fetched.get("error", "Unknown fetch error")
            record["failure_type"] = failure_type
            record["fetch_status"] = "failed"
            record["recovery_attempted"] = True
            record["recovery_result"] = recovery
            record["recovery_note"] = recovery["note_for_user"]
            record["recovered_url"] = recovery.get("selected_replacement_url")
            if recovery.get("recovery_status") == "recovered" and recovery.get("selected_replacement_url"):
                recovered_fetch = fetch_url(recovery["selected_replacement_url"])
                if recovered_fetch["ok"]:
                    record = _record_from_fetch(
                        source,
                        recovered_fetch,
                        configured_url,
                        recovery["selected_replacement_url"],
                    )
                    record["fetch_status"] = "recovered"
                    record["failure_reason"] = fetched.get("error", "Unknown fetch error")
                    record["failure_type"] = failure_type
                    record["recovery_attempted"] = True
                    record["recovery_result"] = recovery
                    record["recovery_note"] = recovery["note_for_user"]
                    record["recovered_url"] = recovery["selected_replacement_url"]
                else:
                    record["fetch_status"] = "failed"
                    record["failure_reason"] = recovered_fetch.get("error", "Recovered URL fetch failed")
            if not record.get("ok"):
                failures.append(_failure_from_record(record, source))
        results.append(record)
    coverage = [_coverage_from_record(item) for item in results]
    return {
        "fetched_at": _now(),
        "source_count": len(results),
        "sources": results,
        "failures": failures,
        "source_coverage": coverage,
    }


def _record_from_fetch(
    source: dict[str, Any],
    fetched: dict[str, Any],
    configured_url: str,
    effective_url: str,
) -> dict[str, Any]:
    meta = dict(source)
    meta["configured_url"] = configured_url
    meta["effective_url"] = effective_url
    return {
        "source_meta": meta,
        "configured_url": configured_url,
        "effective_url": effective_url,
        "fetched_at": fetched["fetched_at"],
        "ok": fetched["ok"],
        "status_code": fetched.get("status_code"),
        "resolved_url": fetched.get("url"),
        "elapsed_seconds": fetched.get("elapsed_seconds"),
        "content_type": fetched.get("content_type", ""),
        "text": strip_html(fetched.get("text", "")),
        "raw_text": fetched.get("text", ""),
        "links": extract_links(fetched.get("text", ""), fetched.get("url") or effective_url)[:80],
        "fetch_status": "success" if fetched["ok"] else "failed",
        "failure_reason": fetched.get("error", "") if not fetched["ok"] else "",
        "failure_type": classify_failure(fetched) if not fetched["ok"] else "",
        "recovery_attempted": False,
        "recovered_url": None,
        "recovery_note": "",
        "recovery_result": None,
    }


def _coverage_from_record(record: dict[str, Any]) -> dict[str, Any]:
    source = record["source_meta"]
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_type": source.get("type"),
        "configured_url": record.get("configured_url") or source.get("base_url"),
        "fetch_status": record.get("fetch_status"),
        "failure_reason": record.get("failure_reason", ""),
        "failure_type": record.get("failure_type", ""),
        "recovery_attempted": bool(record.get("recovery_attempted")),
        "recovered_url": record.get("recovered_url"),
        "recovery_note": record.get("recovery_note", ""),
        "status_code": record.get("status_code"),
        "fetched_at": record.get("fetched_at"),
    }


def _failure_from_record(record: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": source["source_id"],
        "source_name": source["source_name"],
        "configured_url": record.get("configured_url") or source["base_url"],
        "url": record.get("configured_url") or source["base_url"],
        "error": record.get("failure_reason") or record.get("error") or "Unknown fetch error",
        "failure_type": record.get("failure_type", "unknown"),
        "recovery_attempted": bool(record.get("recovery_attempted")),
        "recovered_url": record.get("recovered_url"),
        "recovery_note": record.get("recovery_note", ""),
        "recovery_result": record.get("recovery_result"),
        "fetched_at": record.get("fetched_at"),
    }
