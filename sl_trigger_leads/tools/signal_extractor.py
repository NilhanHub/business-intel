from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

from .signal_tools import (
    classify_signal,
    clean_text,
    contains_simulation_marker,
    detect_1bt_fit,
)

COMPANY_SUFFIXES = r"(?:PLC|Pvt\.?\s+Ltd\.?|Private\s+Limited|Limited|Ltd\.?|Group|Holdings|Bank|Finance|Insurance|Hotels?|Technologies|Solutions|Systems|Digital|Global|Lanka)"


def _infer_company(text: str, url: str = "") -> str:
    cleaned = clean_text(text)
    decoded_url = unquote(url or "")
    slug_match = re.search(r"-at-([^/?#]+)", decoded_url)
    if slug_match:
        slug_company = re.sub(r"[-_]+", " ", slug_match.group(1))
        slug_company = re.sub(r"\b(pvt|ltd)\b", lambda m: m.group(1).upper(), slug_company, flags=re.I)
        slug_company = clean_text(slug_company).title().replace(" Pvt Ltd", " (Pvt) Ltd")
        if slug_company:
            return slug_company[:120]
    patterns = [
        r"\b([A-Z0-9][A-Za-z0-9&.'-]*(?:\s+[A-Z0-9][A-Za-z0-9&.'-]*){0,5}\s+\(Pvt\)\s+Ltd)\b",
        rf"\b([A-Z][A-Za-z&.'-]*(?:\s+[A-Z][A-Za-z&.'-]*){{0,5}}\s+{COMPANY_SUFFIXES})\b",
        r"\b([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){1,3})\s+(?:appoints|appointed|launches|launched|opens|opened|partners|wins|is hiring|seeks)",
        r"(?:at|with|for)\s+([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,4})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            candidate = clean_text(match.group(1))
            if candidate.lower() not in {"sri lanka", "daily ft", "all jobs"}:
                return candidate[:120]
    # ITPro-style title: Role Company Location Date
    pieces = cleaned.split()
    if len(pieces) >= 4:
        return " ".join(pieces[-5:-2])[:120]
    return ""


def _infer_sector(text: str, source_type: str) -> str:
    lowered = text.lower()
    if source_type == "job_board":
        return "software/IT services"
    if any(term in lowered for term in ["bank", "finance", "insurance", "financial"]):
        return "finance/insurance"
    if any(term in lowered for term in ["apparel", "garment", "export", "manufacturing"]):
        return "apparel/manufacturing/export"
    if any(term in lowered for term in ["hotel", "tourism", "travel", "leisure"]):
        return "hospitality/tourism"
    if any(term in lowered for term in ["logistics", "shipping", "warehouse", "freight"]):
        return "logistics"
    if any(term in lowered for term in ["health", "hospital", "clinic"]):
        return "healthcare"
    if any(term in lowered for term in ["retail", "fmcg", "consumer"]):
        return "retail/FMCG"
    if any(term in lowered for term in ["software", "tech", "digital", "it ", "ai "]):
        return "software/IT services"
    return "unknown"


def _evidence_items_from_links(source_result: dict[str, Any]) -> list[dict[str, str]]:
    source_meta = source_result["source_meta"]
    terms = [term.lower() for term in source_meta.get("search_terms", [])]
    items = []
    for link in source_result.get("links", []):
        text = clean_text(link.get("text"))
        if len(text) < 18:
            continue
        lowered = text.lower()
        if terms and not any(term in lowered for term in terms):
            continue
        items.append({"text": text, "url": link.get("url") or source_result.get("resolved_url")})
    return items


def _evidence_items_from_text(source_result: dict[str, Any]) -> list[dict[str, str]]:
    source_meta = source_result["source_meta"]
    terms = [term.lower() for term in source_meta.get("search_terms", [])]
    text = clean_text(source_result.get("text"))
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    items = []
    for sentence in sentences:
        sentence = clean_text(sentence)
        if len(sentence) < 50 or len(sentence) > 500:
            continue
        lowered = sentence.lower()
        if terms and not any(term in lowered for term in terms):
            continue
        items.append({"text": sentence, "url": source_result.get("resolved_url") or source_meta["base_url"]})
    return items[:40]


def extract_public_signals(html_or_text: str, source_meta: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract source-backed candidate public signals from text for a single source."""
    pseudo_result = {
        "source_meta": source_meta,
        "text": html_or_text,
        "links": [],
        "resolved_url": source_meta.get("base_url"),
        "fetched_at": source_meta.get("fetched_at"),
    }
    return extract_public_signals_from_source(pseudo_result)


def extract_public_signals_from_source(source_result: dict[str, Any]) -> list[dict[str, Any]]:
    source_meta = source_result["source_meta"]
    if not source_result.get("ok"):
        return []

    raw_items = _evidence_items_from_links(source_result) + _evidence_items_from_text(source_result)
    seen = set()
    leads = []
    for item in raw_items:
        excerpt = clean_text(item["text"])
        url = clean_text(item["url"])
        key = (excerpt.lower(), url)
        if key in seen:
            continue
        seen.add(key)
        lowered_excerpt = excerpt.lower()
        if contains_simulation_marker(excerpt) or contains_simulation_marker(url):
            continue
        if any(term in lowered_excerpt for term in ["intern", "internship", "trainee"]):
            continue
        classification = classify_signal(excerpt)
        fit = detect_1bt_fit(excerpt)
        if classification["trigger_type"] in {"irrelevant", "generic_pr_fluff", "tender_or_procurement"} and not fit:
            continue
        company = _infer_company(excerpt, url)
        if not company:
            continue
        leads.append(
            {
                "company": company,
                "country": "Sri Lanka",
                "sector": _infer_sector(excerpt, source_meta.get("type", "")),
                "trigger_type": classification["trigger_type"],
                "trigger_summary": excerpt[:280],
                "evidence_url": url,
                "evidence_excerpt": excerpt[:500],
                "source_name": source_meta["source_name"],
                "source_type": source_meta["type"],
                "published_or_seen_date": _extract_date(excerpt) or source_result.get("fetched_at", "")[:10],
                "fetched_at": source_result.get("fetched_at"),
                "verified_live": True,
                "1bt_fit": fit,
                "limits": "Source page was fetched live, but company/contact details may require manual verification before outreach.",
            }
        )
    return leads


def _extract_date(text: str) -> str:
    match = re.search(r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+\d{1,2}\s+[A-Z][a-z]+\s+20\d{2}\b", text)
    if match:
        return match.group(0)
    match = re.search(r"\b\d{1,2}\s+[A-Z][a-z]+\s+20\d{2}\b", text)
    if match:
        return match.group(0)
    match = re.search(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", text)
    if match:
        return match.group(0)
    return ""
