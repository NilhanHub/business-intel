from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "source_registry.json"
ROOT = Path(__file__).resolve().parents[2]


def load_source_registry(enabled_only: bool = True) -> list[dict[str, Any]]:
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    sources = data.get("sources", [])
    if enabled_only:
        sources = [source for source in sources if source.get("enabled") is True]
    return sources


def get_registry_metadata() -> dict[str, Any]:
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {
        "version": data.get("version"),
        "policy": data.get("policy"),
        "enabled_count": len([s for s in data.get("sources", []) if s.get("enabled") is True]),
        "source_ids": [s.get("source_id") for s in data.get("sources", [])],
    }


def list_configured_sources(include_urls: bool = True) -> dict[str, Any]:
    """Return configured public source metadata, including public URLs by default."""
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    last_status = _load_latest_source_status()
    sources = []
    for source in data.get("sources", []):
        source_id = source.get("source_id", "")
        entry = {
            "source_id": source_id,
            "source_name": source.get("source_name", ""),
            "source_type": source.get("type", ""),
            "country": source.get("country", ""),
            "fetch_method": source.get("fetch_method", ""),
            "enabled": source.get("enabled") is True,
            "notes": source.get("notes", ""),
            "limitations": "Public page fetch only; extraction may be low-yield or require manual verification.",
            "search_terms": source.get("search_terms", []),
            "last_fetch_status": last_status.get(source_id),
        }
        if include_urls:
            entry["base_url"] = source.get("base_url", "")
            entry["fetch_url"] = source.get("base_url", "")
            entry["recovery_candidates"] = source.get("recovery_candidates", [])
            entry["previous_urls"] = source.get("previous_urls", [])
        sources.append(entry)
    return {
        "registry_version": data.get("version"),
        "public_url_policy": "Configured public source names and URLs are not confidential. Disclose them when asked.",
        "include_urls": include_urls,
        "source_count": len(sources),
        "sources": sources,
    }


def _load_latest_source_status() -> dict[str, Any]:
    candidates = [
        ROOT / "outputs" / "PROMPT#05_source_coverage.json",
        ROOT / "outputs" / "PROMPT#05_live_leads_with_source_notes.json",
        ROOT / "outputs" / "PROMPT#04_live_leads.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        status: dict[str, Any] = {}
        for item in data.get("source_coverage", data.get("sources_fetched", [])):
            source_id = item.get("source_id")
            if source_id:
                status[source_id] = item
        if status:
            return status
    return {}
