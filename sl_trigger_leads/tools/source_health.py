from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from typing import Any


USER_AGENT = "Business_Intel/0.5 (+source health check; polite public fetch)"


def classify_failure(fetch_result: dict[str, Any]) -> str:
    status = fetch_result.get("status_code")
    error = str(fetch_result.get("error", "")).lower()
    if status == 404:
        return "http_404"
    if status == 403:
        return "http_403"
    if "timeout" in error:
        return "timeout"
    if "dns" in error or "getaddrinfo" in error or "name or service" in error:
        return "dns_error"
    if "ssl" in error or "certificate" in error:
        return "ssl_error"
    if "parse" in error:
        return "parse_error"
    return "unknown"


def test_source_url(url: str, search_terms: list[str] | None = None, timeout_seconds: int = 10) -> dict[str, Any]:
    """Fetch a candidate URL and return status plus a small relevance check."""
    started = time.perf_counter()
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/rss+xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(500_000)
            content_type = response.headers.get("Content-Type", "")
            text = _decode(body, content_type)
            plain = _strip_html(text)
            relevant = _is_relevant(plain, search_terms or [], url)
            return {
                "url": response.geturl(),
                "ok": True,
                "status_code": getattr(response, "status", 200),
                "content_type": content_type,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "relevant_content": relevant,
                "content_excerpt": plain[:240],
            }
    except urllib.error.HTTPError as exc:
        return {
            "url": url,
            "ok": False,
            "status_code": exc.code,
            "error": f"HTTPError: {exc.reason}",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "relevant_content": False,
            "content_excerpt": "",
        }
    except Exception as exc:
        return {
            "url": url,
            "ok": False,
            "status_code": None,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "relevant_content": False,
            "content_excerpt": "",
        }


def _decode(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w.-]+)", content_type or "", re.I)
    encoding = match.group(1) if match else "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_relevant(text: str, search_terms: list[str], url: str) -> bool:
    lowered = f" {text.lower()} "
    if any(term.lower() in lowered for term in search_terms):
        return True
    if "cse.lk" in url.lower() and any(term in lowered for term in ["announcements", "corporate disclosure", "listed companies", "cse"]):
        return True
    if "itpro.lk" in url.lower() and any(term in lowered for term in ["jobs", "developer", "engineer", "vacancy"]):
        return True
    if "ft.lk" in url.lower() and any(term in lowered for term in ["business", "technology", "daily ft", "sri lanka"]):
        return True
    return False
