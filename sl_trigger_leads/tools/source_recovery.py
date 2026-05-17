from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .source_health import test_source_url


def recover_source_url(failed_source: dict[str, Any], failure_context: dict[str, Any]) -> dict[str, Any]:
    """Best-effort recovery for public source URLs that fail to fetch."""
    source_id = failed_source.get("source_id", "")
    source_name = failed_source.get("source_name", "")
    failed_url = failure_context.get("failed_url") or failed_source.get("base_url", "")
    failure_type = failure_context.get("failure_type", "unknown")
    status_code = failure_context.get("status_code")
    search_terms = failed_source.get("search_terms", [])

    candidates = _candidate_urls(failed_source, failed_url, failure_type)
    checked = []
    selected = None
    for candidate in candidates:
        health = test_source_url(candidate["url"], search_terms=search_terms)
        item = {
            "url": health.get("url") or candidate["url"],
            "reason": candidate["reason"],
            "status_code": health.get("status_code"),
            "confidence": _confidence(health, candidate),
            "relevant_content": health.get("relevant_content", False),
        }
        if health.get("error"):
            item["error"] = health["error"]
        checked.append(item)
        if selected is None and health.get("ok") and health.get("relevant_content"):
            selected = item

    if selected:
        status = "recovered"
        selected_url = selected["url"]
        note = f"{source_name} failed at {failed_url}; recovered with {selected_url}."
    elif any(item.get("status_code") == 200 for item in checked):
        status = "candidate_found"
        selected_url = None
        note = f"{source_name} failed at {failed_url}; candidates responded but need manual review before use."
    else:
        status = "not_recovered"
        selected_url = None
        note = f"{source_name} failed at {failed_url}; recovery did not find a usable public replacement."

    return {
        "source_id": source_id,
        "source_name": source_name,
        "failed_url": failed_url,
        "failure_type": failure_type,
        "status_code": status_code,
        "original_source_type": failure_context.get("original_source_type") or failed_source.get("type", ""),
        "recovery_attempted": True,
        "candidate_urls": checked,
        "selected_replacement_url": selected_url,
        "recovery_status": status,
        "note_for_user": note,
    }


def _candidate_urls(source: dict[str, Any], failed_url: str, failure_type: str) -> list[dict[str, str]]:
    seen = set()
    candidates: list[dict[str, str]] = []

    def add(url: str, reason: str) -> None:
        if not url or url in seen:
            return
        seen.add(url)
        candidates.append({"url": url, "reason": reason})

    if source.get("source_id") == "cse_announcements" or "cse.lk" in failed_url:
        add("https://www.cse.lk/announcements", "Known current CSE announcements route")
        add("https://www.cse.lk/announcements/?category=CORPORATE+DISCLOSURE", "CSE corporate disclosure category route")
        add("https://www.cse.lk/general-announcements", "CSE general announcements route")
        add("https://www.cse.lk/", "CSE domain root")

    for url in source.get("recovery_candidates", []):
        add(url, "Configured recovery candidate")

    parsed = urlparse(failed_url)
    if parsed.scheme and parsed.netloc:
        root = f"{parsed.scheme}://{parsed.netloc}/"
        add(root, "Domain root")
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            add(f"{parsed.scheme}://{parsed.netloc}/{parts[0]}", "Top-level section root")
            for index in range(1, len(parts)):
                add(f"{parsed.scheme}://{parsed.netloc}/{'/'.join(parts[:index])}", "Progressively stripped path")
        add(f"{root.rstrip('/')}/sitemap.xml", "Public sitemap")
        add(f"{root.rstrip('/')}/robots.txt", "Public robots.txt")

    # For non-404 failures, still try configured candidates and root but avoid aggressive guessing.
    if failure_type != "http_404":
        return candidates[:8]
    return candidates[:12]


def _confidence(health: dict[str, Any], candidate: dict[str, str]) -> str:
    if health.get("ok") and health.get("relevant_content") and "Known current" in candidate.get("reason", ""):
        return "high"
    if health.get("ok") and health.get("relevant_content"):
        return "medium"
    if health.get("status_code") == 200:
        return "low"
    return "low"
