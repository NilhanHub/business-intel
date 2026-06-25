"""Evidence-first UK and Ireland Dynamics 365 lead discovery tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import urllib.parse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

import requests

from uk_ie_d365_leads.tools import discovery_backbone_tools


AUDIT_SCHEMA_VERSION = "1.1"
CLASSIFIER_VERSION = "2026-05-17.deterministic-rules-v1"
QUERY_MATRIX_VERSION = "2026-05-17.commercial-non-tender-v1"
SEARCH_PROMPT_VERSION = "2026-05-17.google-grounding-json-v1"
GOOGLE_GROUNDING_DEFAULT_MODEL = "gemini-2.5-flash"
GOOGLE_GROUNDING_PROVIDER_PATH = "direct google-genai Google Search grounding"
LEAD_CONSERVATION_VERSION = "2026-06-24.lead-conservation-v1"
DISCOVERY_BACKBONE_VERSION = discovery_backbone_tools.DISCOVERY_BACKBONE_VERSION
FANOUT_PROVIDER_NAME = "fanout"
FANOUT_PROVIDER_ORDER = [
    "google_grounding",
    "exa",
    "tavily",
    "serper",
    "serpapi",
    "firecrawl",
]
FANOUT_DEFAULT_MAX_PROVIDERS = 4
FANOUT_DEFAULT_QUERIES_PER_PROVIDER = 5
FANOUT_DEFAULT_RESULTS_PER_QUERY = 5
FANOUT_DEFAULT_MAX_RAW_RESULTS = 100
SOURCE_FETCH_DEFAULT_MAX_URLS = 100
SOURCE_FETCH_MAX_BYTES = 250_000
PDF_SOURCE_FETCH_MAX_BYTES = 2_000_000
SOURCE_FETCH_TIMEOUT_SECONDS = 12
DISCOVERY_MEMORY_VERSION = "2026-06-25.local-discovery-memory-v1"
PROVIDER_SCORECARD_VERSION = "2026-06-25.provider-scorecard-v1"
SOURCE_RETRY_VERSION = "2026-06-25.source-retry-v1"
QUERY_PACK_VERSION = "2026-06-25.discovery-query-packs-v1"
BINARY_SOURCE_SUFFIXES = (
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".rar",
    ".7z",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
)
BINARY_CONTENT_TYPES = (
    "application/pdf",
    "application/msword",
    "application/vnd.ms-",
    "application/zip",
    "image/",
    "video/",
    "audio/",
)

COUNTRY_TERMS = {
    "United Kingdom": [
        "united kingdom",
        "uk",
        "england",
        "scotland",
        "wales",
        "northern ireland",
        "london",
        "manchester",
        "birmingham",
        "leeds",
        "glasgow",
        "edinburgh",
        "belfast",
        "cardiff",
    ],
    "Ireland": [
        "ireland",
        "republic of ireland",
        "dublin",
        "cork",
        "galway",
        "limerick",
    ],
}

D365_PRODUCTS = {
    "Dynamics 365 CE / Customer Engagement": [
        "dynamics 365 ce",
        "customer engagement",
        "d365 ce",
        "dynamics crm",
        "crm support",
    ],
    "Dynamics 365 Sales": ["dynamics 365 sales", "d365 sales"],
    "Dynamics 365 Customer Service": [
        "dynamics 365 customer service",
        "d365 customer service",
    ],
    "Dynamics 365 Field Service": ["dynamics 365 field service", "d365 field service"],
    "Dynamics 365 Finance": ["dynamics 365 finance", "d365 finance", "d365 f&o"],
    "Dynamics 365 Supply Chain Management": [
        "dynamics 365 supply chain",
        "supply chain management",
        "d365 scm",
    ],
    "Dynamics 365 Business Central": [
        "dynamics 365 business central",
        "business central",
        "d365 bc",
    ],
    "Dataverse / Power Platform connected to Dynamics 365": [
        "dataverse",
        "power platform",
        "power apps",
    ],
}

SIGNAL_CLASSES = {
    "hiring_pain": {
        "source_type": "job_posting",
        "queries": [
            '"Dynamics 365 Administrator" "United Kingdom" careers',
            '"D365 Support Analyst" "United Kingdom" careers',
            '"Dynamics 365 CE" "Support Analyst" UK',
            '"D365 F&O" "Application Support" UK',
            '"Dynamics 365 Business Central" "Support" Ireland careers',
            '"Dynamics 365 Functional Consultant" "in-house" UK',
            '"CRM Manager" "Dynamics 365" "United Kingdom"',
            '"Business Systems Manager" "Dynamics 365" Ireland',
            '"ERP Manager" "Dynamics 365" UK',
        ],
        "terms": [
            "hiring",
            "job",
            "vacancy",
            "careers",
            "administrator",
            "functional consultant",
            "support analyst",
            "application support",
            "crm support",
            "erp support",
            "in-house",
            "business systems manager",
            "erp manager",
        ],
    },
    "direct_company_career_site_searches": {
        "source_type": "job_posting",
        "queries": [
            'site:greenhouse.io "Dynamics 365" "United Kingdom"',
            'site:lever.co "Dynamics 365" UK',
            'site:workable.com "Dynamics 365" Ireland',
            'site:jobs.ashbyhq.com "Dynamics 365" UK',
            '"Dynamics 365" "UK" "careers" "apply"',
            '"Dynamics 365" "Ireland" "careers" "apply"',
        ],
        "terms": [
            "greenhouse",
            "lever",
            "workable",
            "ashby",
            "careers",
            "apply",
            "job",
            "vacancy",
        ],
    },
    "commercial_non_tender_buying_signals": {
        "source_type": "commercial_signal",
        "queries": [
            '"Dynamics 365" ("support needs" OR "support partner" OR "application support") ("United Kingdom" OR UK OR Ireland)',
            '"Dynamics 365" ("growth" OR "expansion" OR "new sites" OR "acquisition") ("United Kingdom" OR UK OR Ireland)',
            '"Dynamics 365" ("integration" OR "rollout" OR "implementation") ("United Kingdom" OR UK OR Ireland)',
            '"Microsoft business applications" ("ERP" OR "CRM") transformation ("United Kingdom" OR UK OR Ireland)',
            '"Power Platform" Dataverse "Dynamics 365" ("support" OR "transformation") ("United Kingdom" OR UK OR Ireland)',
            '"Dynamics 365" "case study" ("customer" OR "client") ("United Kingdom" OR UK OR Ireland)',
        ],
        "terms": [
            "support needs",
            "support partner",
            "application support",
            "growth",
            "expansion",
            "acquisition",
            "integration",
            "rollout",
            "implementation",
            "microsoft business applications",
            "erp transformation",
            "crm transformation",
            "case study",
            "customer story",
        ],
    },
    "implementation_migration_upgrade_rescue": {
        "source_type": "implementation_signal",
        "queries": [
            '"we are implementing Dynamics 365" UK',
            '"implemented Dynamics 365" "United Kingdom" company',
            '"migrating to Dynamics 365" UK company',
            '"Dynamics 365 rollout" Ireland company',
            '"Business Central migration" UK company',
            '"Dynamics 365 upgrade" "United Kingdom" "case study"',
            '"Dynamics 365 customer story" UK',
            '"Dynamics 365 case study" Ireland',
            '"Dynamics CRM replacement" "United Kingdom" company',
            '"Finance and Operations rollout" "Dynamics 365" UK company',
            '"Dynamics 365" ("failed implementation" OR rescue OR backlog) UK',
        ],
        "terms": [
            "failed",
            "struggling",
            "rescue",
            "backlog",
            "issue",
            "stabilise",
            "stabilize",
            "remediation",
            "upgrade",
            "migration",
            "migrate",
            "rollout",
            "replacement",
            "implementation",
            "integration",
        ],
    },
    "installed_base_discovery": {
        "source_type": "installed_base",
        "queries": [
            '"uses Dynamics 365" UK company',
            '"Dynamics 365 customer" "United Kingdom"',
            '"Dynamics 365 Business Central customer" Ireland',
            '"Dynamics 365 Field Service" UK company',
            '"Dynamics 365 Finance" UK company',
            'site:microsoft.com "Dynamics 365" "United Kingdom" "customer story"',
            '"Dynamics 365" "case study" Ireland customer',
        ],
        "terms": [
            "case study",
            "customer story",
            "transformation",
            "roll-out",
            "roll out",
            "go-live",
            "uses dynamics 365",
            "implemented dynamics 365",
        ],
    },
    "transformation_trigger": {
        "source_type": "transformation_trigger",
        "queries": [
            '"Dynamics 365" "digital transformation" UK company',
            '"Dynamics 365" "new CIO" UK',
            '"Dynamics 365" "ERP transformation" Ireland',
            '"Microsoft business applications" "digital transformation" UK company',
            '"Power Platform" Dataverse "Dynamics 365" "ERP transformation" Ireland',
        ],
        "terms": [
            "new cio",
            "new cto",
            "digital transformation",
            "erp transformation",
            "crm transformation",
            "microsoft business applications",
        ],
    },
}

SIGNAL_TYPES = {
    "hiring_support_or_augmentation": [
        "hiring",
        "job",
        "vacancy",
        "administrator",
        "functional consultant",
        "support analyst",
        "crm support",
        "erp support",
        "contract",
    ],
    "implementation_rescue_or_backlog": [
        "failed",
        "struggling",
        "rescue",
        "backlog",
        "issue",
        "stabilise",
        "stabilize",
        "remediation",
    ],
    "upgrade_or_migration": [
        "upgrade",
        "migration",
        "migrate",
        "rollout",
        "replacement",
        "implementation",
        "integration",
    ],
    "managed_services_or_support": [
        "managed services",
        "support services",
        "application support",
        "support partner",
        "maintenance",
    ],
    "customer_story_or_scale_signal": [
        "case study",
        "customer story",
        "transformation",
        "roll-out",
        "roll out",
        "go-live",
    ],
}

TENDER_DOMAINS = (
    "find-tender.service.gov.uk",
    "contracts.service.gov.uk",
    "etenders.gov.ie",
)
TENDER_TERMS = (
    "tender",
    "rfp",
    "procurement notice",
    "procurement portal",
    "procurement opportunity",
    "public procurement",
    "contract notice",
    "invitation to tender",
    "bid opportunity",
    "public-sector procurement",
    "public sector procurement",
)
VENDOR_TERMS = (
    "we provide",
    "we implement",
    "we support",
    "we offer",
    "we specialise",
    "specialise in providing",
    "design and implement",
    "designed and implemented",
    "helps business organisations",
    "offers assessment",
    "advisory",
    "project governance services",
    "our dynamics 365 services",
    "business central services",
    "support services",
    "migration services",
    "consulting",
    "hire microsoft dynamics",
    "dynamics 365 partner",
    "business central partner",
    "d365 partner",
    "dynamics partner",
    "erp partner",
    "crm partner",
    "migration partners",
    "certified microsoft solutions partner",
    "microsoft partner",
    "solutions partner",
    "implementation partner",
    "as a partner",
    "as an erp partner",
    "partner in the uk",
    "partner in ireland",
    "our customers",
    "our clients",
    "partner network",
    "growth announcement",
    "book a demo",
    "contact us for dynamics",
)
TARGET_CUSTOMER_TERMS = (
    "case study",
    "customer story",
    "client:",
    "customer:",
    "implemented for",
    "using dynamics 365 at",
    "selected by",
    "deployed at",
    "worked with",
    "helped",
    "for its",
    "for their",
)
AGENCY_TERMS = ("recruitment", "recruiter", "staffing agency", "job board")
DEFENSIBLE_HIRING_COMPANY_TERMS = (
    "hiring company",
    "direct employer",
    "company:",
    "employer:",
)
DIRECT_EMPLOYER_TERMS = (
    "careers",
    "our team",
    "join us",
    "we are hiring",
    "direct employer",
    "company:",
    "employer:",
    "business systems manager",
    "crm manager",
    "erp manager",
)
COMMERCIAL_SIGNAL_TERMS = (
    "hiring",
    "careers",
    "support",
    "migration",
    "upgrade",
    "rollout",
    "implementation",
    "integration",
    "backlog",
    "rescue",
    "digital transformation",
    "erp transformation",
    "crm transformation",
)
FAKE_OR_EXAMPLE_HOSTS = {
    "example.com",
    "example.net",
    "example.org",
    "example.test",
    "localhost",
    "127.0.0.1",
}
HARD_REJECTION_REASONS = {
    "missing_evidence_url",
    "fake_or_example_url",
    "private_or_linkedin_source_excluded",
    "tender_or_procurement_out_of_scope",
    "missing_explicit_dynamics_365_or_business_app_evidence",
    "generic_it_support_without_dynamics_365_evidence",
    "uk_ireland_not_evidenced",
}
AI_REVIEW_FLAG_REASONS = {
    "vendor_or_service_provider_page_without_defensible_target_customer",
    "recruitment_agency_post_without_defensible_hiring_company",
    "uk_ireland_not_evidenced_in_snippet",
    "missing_explicit_d365_in_snippet_needs_source_check",
    "grounding_redirect_needs_clean_source",
    "thin_snippet_needs_source_check",
}
RETENTION_STATUSES = {
    "final_ready",
    "needs_source_cleanup",
    "needs_identity_resolution",
    "same_company_new_opportunity_review",
    "duplicate_same_opportunity",
    "hard_reject",
}

DEFAULT_QUERIES = [
    query
    for signal_class in SIGNAL_CLASSES.values()
    for query in signal_class["queries"]
]

QUERY_PACKS: dict[str, list[dict[str, str]]] = {
    "support": [
        {"signal_class": "support_pain", "query": '"Dynamics 365" ("rescue" OR "stabilisation" OR "stabilization") (UK OR Ireland) -tender -procurement'},
        {"signal_class": "support_pain", "query": '"Dynamics 365" "post go-live" support (UK OR Ireland) -jobs -tender'},
        {"signal_class": "support_pain", "query": '"D365" ("support backlog" OR "managed support") (UK OR Ireland) -recruiter -tender'},
    ],
    "migration": [
        {"signal_class": "migration_upgrade", "query": '"migrated to Dynamics 365" (UK OR Ireland) company -jobs -tender'},
        {"signal_class": "migration_upgrade", "query": '"Business Central upgrade" (UK OR Ireland) "case study" -jobs -tender'},
        {"signal_class": "migration_upgrade", "query": '"Dynamics 365 upgrade" ("United Kingdom" OR Ireland) "customer" -jobs -tender'},
    ],
    "case-study": [
        {"signal_class": "named_customer_case_study", "query": '"Dynamics 365" "case study" ("United Kingdom" OR Ireland) -jobs -careers -tender'},
        {"signal_class": "named_customer_case_study", "query": '"Business Central" "customer story" (UK OR Ireland) -jobs -careers -tender'},
        {"signal_class": "power_platform_d365", "query": '"Power Platform" "Dynamics 365" "case study" (UK OR Ireland) -jobs -tender'},
    ],
    "pdf": [
        {"signal_class": "pdf_case_study", "query": 'filetype:pdf "Dynamics 365" "case study" (UK OR Ireland) -tender'},
        {"signal_class": "pdf_case_study", "query": 'filetype:pdf "Business Central" "case study" (UK OR Ireland) -tender'},
        {"signal_class": "pdf_case_study", "query": 'filetype:pdf "Dynamics 365" "customer" "Microsoft partner" (UK OR Ireland) -tender'},
    ],
}
QUERY_PACK_ALIASES = {
    "default": [],
    "all": ["support", "migration", "case-study", "pdf"],
}
RETRYABLE_SOURCE_FETCH_STATUSES = {
    "timeout",
    "fetch_error",
    "http_error",
    "decode_error",
    "pdf_parse_error",
    "pdf_parser_unavailable",
}
NON_RETRYABLE_SOURCE_FETCH_STATUSES = {
    "skipped_private_linkedin_source",
    "skipped_tender_or_procurement_source",
    "skipped_fake_or_example_source",
    "skipped_non_http_source",
}

NO_PROVIDER_MESSAGE = (
    "No local live search provider is configured. Configure one of: "
    "D365_ENABLE_GOOGLE_GROUNDING=true with local ADK Google Search auth, "
    "TAVILY_API_KEY, EXA_API_KEY, SERPER_API_KEY, SERPAPI_API_KEY, "
    "FIRECRAWL_API_KEY, or GOOGLE_CSE_API_KEY plus GOOGLE_CSE_CX."
)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str
    published_date: str | None = None
    signal_class: str | None = None
    source_url_type: str = "clean_public_url"
    source_query: str | None = None
    source_query_group: str | None = None
    run_id: str | None = None
    source_channel: str = "public_web"
    original_url: str | None = None
    final_url: str | None = None
    source_fetch_status: str | None = None
    source_fetch: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    configured: bool
    unavailable_reason: str | None


@dataclass(frozen=True)
class HttpText:
    url: str
    status_code: int | None
    text: str
    error: str | None = None


class SearchProvider(Protocol):
    name: str
    configured: bool
    unavailable_reason: str | None

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Return real public web search results or an empty list."""


class ProviderUnavailable:
    name = "none"
    configured = False

    def __init__(self, reason: str = NO_PROVIDER_MESSAGE) -> None:
        self.unavailable_reason = reason

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        return []


class FanoutSearchProvider:
    name = FANOUT_PROVIDER_NAME

    def __init__(self) -> None:
        self.providers = configured_fanout_providers(max_providers=FANOUT_DEFAULT_MAX_PROVIDERS)
        self.configured = bool(self.providers)
        if self.configured:
            self.unavailable_reason = None
        else:
            self.unavailable_reason = (
                "No fanout providers are configured. Configure Google grounding, "
                "EXA_API_KEY, TAVILY_API_KEY, SERPER_API_KEY, SERPAPI_API_KEY, or FIRECRAWL_API_KEY."
            )

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        merged: list[SearchResult] = []
        seen: set[str] = set()
        per_provider_limit = max(1, min(int(limit or FANOUT_DEFAULT_RESULTS_PER_QUERY), FANOUT_DEFAULT_RESULTS_PER_QUERY))
        for provider in self.providers:
            try:
                results = provider.search_web(query, limit=per_provider_limit)
            except Exception:
                continue
            for result in results:
                normalized = normalize_public_url(result.url)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                merged.append(result)
                if len(merged) >= limit:
                    return merged
        return merged


class ADKGoogleGroundingProvider:
    name = "google_grounding"

    def __init__(self) -> None:
        discovery = _adk_google_search_discovery()
        readiness = google_native_readiness()
        self.enabled = readiness["ready"]
        self.configured = bool(discovery["available"] and self.enabled)
        if self.configured:
            self.unavailable_reason = None
        elif not discovery["available"]:
            self.unavailable_reason = discovery["error"]
        else:
            self.unavailable_reason = readiness["reason"]

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        _prepare_google_native_env()
        return _run_google_genai_grounded_search_results(query, limit=limit, source=self.name)


class GoogleCustomSearchProvider:
    name = "custom_search_api"

    def __init__(self) -> None:
        self.api_key = os.environ.get("GOOGLE_CSE_API_KEY")
        self.cx = os.environ.get("GOOGLE_CSE_CX")
        self.configured = bool(self.api_key and self.cx)
        self.unavailable_reason = None if self.configured else (
            "Configure GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX."
        )

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "num": max(1, min(int(limit or 5), 10)),
        }
        payload = _request_json(
            "GET",
            f"https://www.googleapis.com/customsearch/v1?{urllib.parse.urlencode(params)}",
        )
        return [
            SearchResult(
                title=item.get("title") or "",
                url=item.get("link") or "",
                snippet=item.get("snippet") or "",
                source=self.name,
            )
            for item in payload.get("items", [])[:limit]
            if item.get("link")
        ]


class SerpApiSearchProvider:
    name = "serpapi"

    def __init__(self) -> None:
        self.api_key = os.environ.get("SERPAPI_API_KEY")
        self.configured = bool(self.api_key)
        self.unavailable_reason = None if self.configured else "Configure SERPAPI_API_KEY."

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        params = {
            "api_key": self.api_key,
            "engine": "google",
            "q": query,
            "num": max(1, min(int(limit or 5), 10)),
            "gl": "uk",
        }
        payload = _request_json("GET", f"https://serpapi.com/search.json?{urllib.parse.urlencode(params)}")
        return _organic_results(payload.get("organic_results", []), self.name, limit)


class SerperSearchProvider:
    name = "serper"

    def __init__(self) -> None:
        self.api_key = os.environ.get("SERPER_API_KEY")
        self.configured = bool(self.api_key)
        self.unavailable_reason = None if self.configured else "Configure SERPER_API_KEY."

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        payload = _request_json(
            "POST",
            "https://google.serper.dev/search",
            headers={"X-API-KEY": self.api_key or "", "Content-Type": "application/json"},
            json_body={"q": query, "num": max(1, min(int(limit or 5), 10)), "gl": "gb"},
        )
        return _organic_results(payload.get("organic", []), self.name, limit)


class TavilySearchProvider:
    name = "tavily"

    def __init__(self) -> None:
        self.api_key = os.environ.get("TAVILY_API_KEY")
        self.configured = bool(self.api_key)
        self.unavailable_reason = None if self.configured else "Configure TAVILY_API_KEY."

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        payload = _request_json(
            "POST",
            "https://api.tavily.com/search",
            json_body={
                "api_key": self.api_key,
                "query": query,
                "max_results": max(1, min(int(limit or 5), 10)),
                "search_depth": "basic",
            },
        )
        return [
            SearchResult(
                title=item.get("title") or "",
                url=item.get("url") or "",
                snippet=item.get("content") or "",
                source=self.name,
                published_date=item.get("published_date"),
            )
            for item in payload.get("results", [])[:limit]
            if item.get("url")
        ]


class ExaSearchProvider:
    name = "exa"

    def __init__(self) -> None:
        self.api_key = os.environ.get("EXA_API_KEY")
        self.configured = bool(self.api_key)
        self.unavailable_reason = None if self.configured else "Configure EXA_API_KEY."

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        payload = _request_json(
            "POST",
            "https://api.exa.ai/search",
            headers={"x-api-key": self.api_key or "", "Content-Type": "application/json"},
            json_body={"query": query, "numResults": max(1, min(int(limit or 5), 10))},
        )
        return [
            SearchResult(
                title=item.get("title") or "",
                url=item.get("url") or "",
                snippet=item.get("text") or item.get("summary") or "",
                source=self.name,
                published_date=item.get("publishedDate"),
            )
            for item in payload.get("results", [])[:limit]
            if item.get("url")
        ]


class FirecrawlSearchProvider:
    name = "firecrawl"

    def __init__(self) -> None:
        self.api_key = os.environ.get("FIRECRAWL_API_KEY")
        self.configured = bool(self.api_key)
        self.unavailable_reason = None if self.configured else "Configure FIRECRAWL_API_KEY."

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        payload = _request_json(
            "POST",
            "https://api.firecrawl.dev/v1/search",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json_body={"query": query, "limit": max(1, min(int(limit or 5), 10))},
        )
        rows = payload.get("data") or payload.get("results") or []
        return [
            SearchResult(
                title=item.get("title") or "",
                url=item.get("url") or "",
                snippet=item.get("description") or item.get("content") or "",
                source=self.name,
            )
            for item in rows[:limit]
            if item.get("url")
        ]


def discover_d365_search_providers() -> dict[str, Any]:
    """Report local provider readiness without making outbound calls."""
    providers = _provider_candidates()
    fanout = FanoutSearchProvider()
    statuses = [
        asdict(ProviderStatus(p.name, bool(p.configured), p.unavailable_reason))
        for p in providers
    ]
    chosen = next((status["name"] for status in statuses if status["configured"]), None)
    return {
        "chosen_provider": chosen,
        "fanout": asdict(ProviderStatus(fanout.name, bool(fanout.configured), fanout.unavailable_reason)),
        "fanout_provider_order": FANOUT_PROVIDER_ORDER,
        "providers": statuses,
        "adk": _adk_google_search_discovery(),
        "google_native_readiness": google_native_readiness(),
        "missing_env_vars": missing_provider_env_vars(),
        "notes": [
            "Search providers are real adapters only; missing credentials produce no leads.",
            "Use provider_name='fanout' to search across all configured high-value providers with provider-level budgets.",
            "Google-native live search uses google-genai grounding directly; d365_search_agent remains search-only for ADK routing.",
        ],
    }


def audit_metadata(
    *,
    search_provider: str | None,
    live_search_run: bool,
    live_request_count: int,
    run_started_at: str | None,
    run_finished_at: str | None,
) -> dict[str, Any]:
    model_name, model_source = effective_google_model()
    adc = _adc_status()
    api_key_present = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if api_key_present:
        provider_client_mode = "API_KEY"
    elif adc.get("available") and adc.get("project_present"):
        provider_client_mode = "ADC"
    else:
        provider_client_mode = "unknown"
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
    return {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "classifier_version": CLASSIFIER_VERSION,
        "query_matrix_version": QUERY_MATRIX_VERSION,
        "prompt_version": SEARCH_PROMPT_VERSION,
        "search_provider": search_provider or "unknown",
        "search_provider_path": (
            GOOGLE_GROUNDING_PROVIDER_PATH
            if (search_provider or "") == "google_grounding"
            else "provider adapter"
        ),
        "effective_model_name": model_name,
        "model_source": model_source,
        "provider_client_mode": provider_client_mode,
        "google_project_present": bool(adc.get("project_present")),
        "google_project_id_masked": mask_identifier(str(adc.get("project") or "")) if adc.get("project") else None,
        "project_id_present": bool(adc.get("project")),
        "google_location": location,
        "live_search_run": bool(live_search_run),
        "live_request_count": int(live_request_count or 0),
        "run_started_at": run_started_at,
        "run_finished_at": run_finished_at,
        "code_version_hint": code_version_hint(),
    }


def effective_google_model() -> tuple[str, str]:
    configured = os.environ.get("D365_GOOGLE_MODEL")
    if configured:
        return configured, "env:D365_GOOGLE_MODEL"
    return GOOGLE_GROUNDING_DEFAULT_MODEL, "default"


def mask_identifier(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return f"{value[:1]}***{value[-1:]}"
    return f"{value[:3]}***{value[-3:]}"


def code_version_hint() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return "not_git_repository"
    except Exception:  # noqa: BLE001 - audit metadata should never block lead extraction.
        return "unknown"


def find_uk_ie_d365_leads(
    query: str | None = None,
    max_results: int = 5,
    provider_name: str | None = None,
    max_live_requests: int = 5,
    include_rejected: bool = True,
    source_fetch: bool = True,
    fanout_max_providers: int = FANOUT_DEFAULT_MAX_PROVIDERS,
    fanout_queries_per_provider: int = FANOUT_DEFAULT_QUERIES_PER_PROVIDER,
    fanout_results_per_query: int = FANOUT_DEFAULT_RESULTS_PER_QUERY,
    fanout_max_raw_results: int = FANOUT_DEFAULT_MAX_RAW_RESULTS,
    source_fetch_max_urls: int = SOURCE_FETCH_DEFAULT_MAX_URLS,
    parse_pdfs: bool = False,
    query_pack: str = "default",
    shortage_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Find evidence-backed UK/Ireland Dynamics 365 lead signals."""
    max_results = max(1, min(int(max_results or 5), 50))
    per_query_limit = max(1, min(max_results, 10))
    requested_provider = (provider_name or os.environ.get("D365_SEARCH_PROVIDER") or "").strip().lower()
    provider = get_search_provider(provider_name)
    started = datetime.now(UTC).isoformat()
    run_id = make_run_id(started, provider.name)
    cloud_preflight = discovery_backbone_tools.build_discovery_preflight()
    source_channel_policy = discovery_backbone_tools.source_channel_policy()
    query_plan = build_query_plan(
        query,
        cloud_preflight=cloud_preflight,
        query_pack=query_pack,
        shortage_report=shortage_report,
    )
    queries = [item["query"] for item in query_plan]
    if requested_provider == FANOUT_PROVIDER_NAME or provider.name == FANOUT_PROVIDER_NAME:
        return find_uk_ie_d365_leads_fanout(
            query=query,
            max_results=max_results,
            max_live_requests=max_live_requests,
            include_rejected=include_rejected,
            source_fetch=source_fetch,
            fanout_max_providers=fanout_max_providers,
            fanout_queries_per_provider=fanout_queries_per_provider,
            fanout_results_per_query=fanout_results_per_query,
            fanout_max_raw_results=fanout_max_raw_results,
            source_fetch_max_urls=source_fetch_max_urls,
            parse_pdfs=parse_pdfs,
            query_pack=query_pack,
            started=started,
            run_id=run_id,
            cloud_preflight=cloud_preflight,
            source_channel_policy=source_channel_policy,
            query_plan=query_plan,
        )
    if not provider.configured:
        finished = datetime.now(UTC).isoformat()
        return {
            "status": "blocked",
            "provider": provider.name,
            "run_id": run_id,
            "audit_metadata": audit_metadata(
                search_provider=provider.name,
                live_search_run=False,
                live_request_count=0,
                run_started_at=started,
                run_finished_at=finished,
            ),
            "setup_error": provider.unavailable_reason or NO_PROVIDER_MESSAGE,
            "missing_env_vars": missing_provider_env_vars(),
            "queries_planned": queries,
            "query_plan": query_plan,
            "query_pack": query_pack,
            "parse_pdfs": bool(parse_pdfs),
            "query_strategy": "memory_augmented_default" if not (query and query.strip()) else "custom_query",
            "cloud_discovery_preflight": cloud_preflight,
            "source_channel_policy": source_channel_policy,
            "provider_readiness": discover_d365_search_providers(),
            "provider_budget": {},
            "source_fetches": [],
            "source_fetch_errors": [],
            "raw_result_ledger": [],
            "leads": [],
            "lead_count": 0,
            "tier_counts": {"A": 0, "B": 0, "C": 0, "D": 0},
            "tier_a_leads": [],
            "tier_b_provisional_leads": [],
            "tier_c_watchlist_leads": [],
            "tier_d_rejected": [],
            "rejected_leads": [],
            "rejected_count": 0,
            "review_candidates": [],
            "hard_rejected_leads": [],
            "hard_rejected_count": 0,
            "candidate_ledger": [],
            "fetched_at": started,
        }

    raw_results: list[SearchResult] = []
    raw_result_ledger: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    live_requests_made = 0
    for query_item in query_plan[: max(1, min(int(max_live_requests or 5), 25))]:
        search_query = query_item["query"]
        try:
            live_requests_made += 1
            results = provider.search_web(search_query, limit=per_query_limit)
            for result in results:
                row = SearchResult(
                    title=result.title,
                    url=result.url,
                    snippet=result.snippet,
                    source=result.source,
                    published_date=result.published_date,
                    signal_class=query_item["signal_class"],
                    source_url_type=result.source_url_type,
                    source_query=search_query,
                    source_query_group=query_item["signal_class"],
                    run_id=run_id,
                    source_channel=discovery_backbone_tools.classify_source_channel(
                        source=result.source,
                        provider_path=GOOGLE_GROUNDING_PROVIDER_PATH if result.source == "google_grounding" else None,
                        url=result.url,
                        explicit=result.source_channel,
                    ),
                )
                raw_results.append(row)
                raw_result_ledger.append(raw_result_audit_row(row, search_query=search_query))
        except Exception as exc:  # noqa: BLE001 - return actionable provider error.
            errors.append({"query": search_query, "error": _safe_error(exc)})
            break

    deduped_results, duplicate_raw_results = dedupe_search_results_by_url(raw_results)
    source_fetches = (
        fetch_sources_for_results(deduped_results, max_urls=source_fetch_max_urls, parse_pdfs=parse_pdfs)
        if source_fetch
        else []
    )
    enriched_results = enrich_results_with_source_fetches(deduped_results, source_fetches)
    extraction = extract_d365_leads(enriched_results, max_results=max_results, include_rejected=include_rejected)
    leads = extraction["surfaced_leads"]
    tier_counts = extraction["tier_counts"]
    finished = datetime.now(UTC).isoformat()
    return {
        "status": "ok" if leads else "no_verified_leads_found",
        "provider": provider.name,
        "run_id": run_id,
        "audit_metadata": audit_metadata(
            search_provider=provider.name,
            live_search_run=live_requests_made > 0,
            live_request_count=live_requests_made,
            run_started_at=started,
            run_finished_at=finished,
        ),
        "queries_run": [item["query"] for item in query_plan[:live_requests_made]],
        "queries_planned": queries,
        "query_plan": query_plan,
        "query_groups_run": [item["signal_class"] for item in query_plan[:live_requests_made]],
        "query_strategy": "memory_augmented_default" if not (query and query.strip()) else "custom_query",
        "query_pack": query_pack,
        "cloud_discovery_preflight": cloud_preflight,
        "source_channel_policy": source_channel_policy,
        "live_requests_made": live_requests_made,
        "provider_readiness": discover_d365_search_providers(),
        "provider_budget": {
            provider.name: {
                "configured": bool(provider.configured),
                "requests_attempted": live_requests_made,
                "successes": max(0, live_requests_made - len(errors)),
                "failures": len(errors),
                "timeouts": sum(1 for item in errors if "timeout" in str(item.get("error", "")).lower()),
                "raw_result_count": len(raw_results),
            }
        },
        "source_fetch_enabled": bool(source_fetch),
        "parse_pdfs": bool(parse_pdfs),
        "source_fetches": source_fetches,
        "source_fetch_errors": [item for item in source_fetches if item.get("source_fetch_status") != "fetched"],
        "raw_result_ledger": raw_result_ledger,
        "duplicate_raw_result_count": len(duplicate_raw_results),
        "duplicate_raw_results": duplicate_raw_results,
        "cost_risk": (
            "Google-native grounding may incur normal model/search API cost when configured."
            if provider.name == "google_grounding"
            else "No Google-native cost risk from this provider."
        ),
        "provider_errors": errors,
        "leads": leads,
        "lead_count": len(leads),
        "candidate_ledger": extraction.get("candidate_ledger", []),
        "tier_counts": tier_counts,
        "tier_a_leads": extraction["tier_a_leads"],
        "tier_b_provisional_leads": extraction["tier_b_provisional_leads"],
        "tier_c_watchlist_leads": extraction["tier_c_watchlist_leads"],
        "tier_d_rejected": extraction["tier_d_rejected"] if include_rejected else [],
        "rejected_leads": extraction["rejected_leads"] if include_rejected else [],
        "rejected_count": len(extraction["rejected_leads"]),
        "review_candidates": extraction.get("review_candidates", []),
        "hard_rejected_leads": extraction.get("hard_rejected_leads", []) if include_rejected else [],
        "hard_rejected_count": len(extraction.get("hard_rejected_leads", [])),
        "fetched_at": started,
        "run_finished_at": finished,
    }


def find_uk_ie_d365_leads_fanout(
    *,
    query: str | None,
    max_results: int,
    max_live_requests: int,
    include_rejected: bool,
    source_fetch: bool,
    fanout_max_providers: int,
    fanout_queries_per_provider: int,
    fanout_results_per_query: int,
    fanout_max_raw_results: int,
    source_fetch_max_urls: int,
    parse_pdfs: bool,
    query_pack: str,
    started: str,
    run_id: str,
    cloud_preflight: dict[str, Any],
    source_channel_policy: dict[str, Any],
    query_plan: list[dict[str, str]],
) -> dict[str, Any]:
    providers = configured_fanout_providers(max_providers=fanout_max_providers)
    provider_readiness = discover_d365_search_providers()
    provider_budget = build_initial_provider_budget()
    queries_per_provider = max(1, min(int(fanout_queries_per_provider or FANOUT_DEFAULT_QUERIES_PER_PROVIDER), FANOUT_DEFAULT_QUERIES_PER_PROVIDER))
    results_per_query = max(1, min(int(fanout_results_per_query or FANOUT_DEFAULT_RESULTS_PER_QUERY), 10))
    planned_request_cap = max(1, len(providers) * queries_per_provider)
    total_request_cap = planned_request_cap if int(max_live_requests or 0) == 5 else max(1, min(int(max_live_requests or planned_request_cap), planned_request_cap))
    raw_result_cap = max(1, min(int(fanout_max_raw_results or FANOUT_DEFAULT_MAX_RAW_RESULTS), FANOUT_DEFAULT_MAX_RAW_RESULTS))
    queries_for_provider = query_plan[:queries_per_provider]

    if not providers:
        finished = datetime.now(UTC).isoformat()
        return {
            "status": "blocked",
            "provider": FANOUT_PROVIDER_NAME,
            "run_id": run_id,
            "audit_metadata": audit_metadata(
                search_provider=FANOUT_PROVIDER_NAME,
                live_search_run=False,
                live_request_count=0,
                run_started_at=started,
                run_finished_at=finished,
            ),
            "setup_error": "No configured fanout providers were available.",
            "missing_env_vars": missing_provider_env_vars(),
            "queries_planned": [item["query"] for item in query_plan],
            "query_plan": query_plan,
            "query_pack": query_pack,
            "parse_pdfs": bool(parse_pdfs),
            "query_strategy": "fanout_memory_augmented_default" if not (query and query.strip()) else "fanout_custom_query",
            "cloud_discovery_preflight": cloud_preflight,
            "source_channel_policy": source_channel_policy,
            "provider_readiness": provider_readiness,
            "provider_budget": provider_budget,
            "source_fetch_enabled": bool(source_fetch),
            "source_fetches": [],
            "source_fetch_errors": [],
            "raw_result_ledger": [],
            "leads": [],
            "lead_count": 0,
            "tier_counts": {"A": 0, "B": 0, "C": 0, "D": 0},
            "tier_a_leads": [],
            "tier_b_provisional_leads": [],
            "tier_c_watchlist_leads": [],
            "tier_d_rejected": [],
            "rejected_leads": [],
            "rejected_count": 0,
            "review_candidates": [],
            "hard_rejected_leads": [],
            "hard_rejected_count": 0,
            "candidate_ledger": [],
            "fetched_at": started,
            "run_finished_at": finished,
        }

    raw_results: list[SearchResult] = []
    raw_result_ledger: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    queries_run: list[str] = []
    query_groups_run: list[str] = []
    live_requests_made = 0
    stop = False
    for provider in providers:
        budget = provider_budget.setdefault(provider.name, provider_budget_row(provider))
        for query_item in queries_for_provider:
            if live_requests_made >= total_request_cap or len(raw_results) >= raw_result_cap:
                stop = True
                break
            search_query = query_item["query"]
            live_requests_made += 1
            budget["requests_attempted"] += 1
            queries_run.append(search_query)
            query_groups_run.append(query_item["signal_class"])
            try:
                results = provider.search_web(search_query, limit=results_per_query)
                budget["successes"] += 1
                budget["raw_result_count"] += len(results)
                for result in results:
                    row = SearchResult(
                        title=result.title,
                        url=result.url,
                        snippet=result.snippet,
                        source=result.source,
                        published_date=result.published_date,
                        signal_class=query_item["signal_class"],
                        source_url_type=result.source_url_type,
                        source_query=search_query,
                        source_query_group=query_item["signal_class"],
                        run_id=run_id,
                        source_channel=discovery_backbone_tools.classify_source_channel(
                            source=result.source,
                            provider_path=GOOGLE_GROUNDING_PROVIDER_PATH if result.source == "google_grounding" else None,
                            url=result.url,
                            explicit=result.source_channel,
                        ),
                    )
                    raw_results.append(row)
                    raw_result_ledger.append(raw_result_audit_row(row, search_query=search_query))
                    if len(raw_results) >= raw_result_cap:
                        break
            except Exception as exc:  # noqa: BLE001 - fanout keeps partial provider results.
                safe = _safe_error(exc)
                budget["failures"] += 1
                if is_timeout_error(exc, safe):
                    budget["timeouts"] += 1
                errors.append({"provider": provider.name, "query": search_query, "error": safe})
        if stop:
            break

    deduped_results, duplicate_raw_results = dedupe_search_results_by_url(raw_results)
    source_fetches = (
        fetch_sources_for_results(deduped_results, max_urls=source_fetch_max_urls, parse_pdfs=parse_pdfs)
        if source_fetch
        else []
    )
    enriched_results = enrich_results_with_source_fetches(deduped_results, source_fetches)
    extraction = extract_d365_leads(enriched_results, max_results=max_results, include_rejected=include_rejected)
    leads = extraction["surfaced_leads"]
    finished = datetime.now(UTC).isoformat()
    return {
        "status": "ok" if leads else "no_verified_leads_found",
        "provider": FANOUT_PROVIDER_NAME,
        "run_id": run_id,
        "audit_metadata": audit_metadata(
            search_provider=FANOUT_PROVIDER_NAME,
            live_search_run=live_requests_made > 0,
            live_request_count=live_requests_made,
            run_started_at=started,
            run_finished_at=finished,
        ),
        "queries_run": queries_run,
        "queries_planned": [item["query"] for item in query_plan],
        "query_plan": query_plan,
        "query_groups_run": query_groups_run,
        "query_strategy": "fanout_memory_augmented_default" if not (query and query.strip()) else "fanout_custom_query",
        "query_pack": query_pack,
        "cloud_discovery_preflight": cloud_preflight,
        "source_channel_policy": source_channel_policy,
        "live_requests_made": live_requests_made,
        "provider_readiness": provider_readiness,
        "provider_budget": provider_budget,
        "fanout_limits": {
            "max_providers": fanout_max_providers,
            "queries_per_provider": queries_per_provider,
            "results_per_query": results_per_query,
            "max_raw_results": raw_result_cap,
            "total_request_cap": total_request_cap,
        },
        "source_fetch_enabled": bool(source_fetch),
        "parse_pdfs": bool(parse_pdfs),
        "source_fetches": source_fetches,
        "source_fetch_errors": [item for item in source_fetches if item.get("source_fetch_status") != "fetched"],
        "raw_result_ledger": raw_result_ledger,
        "raw_result_count": len(raw_results),
        "deduped_raw_result_count": len(deduped_results),
        "duplicate_raw_result_count": len(duplicate_raw_results),
        "duplicate_raw_results": duplicate_raw_results,
        "cost_risk": "Fanout may call multiple configured live search APIs and public source pages; each provider may incur its normal API cost.",
        "provider_errors": errors,
        "leads": leads,
        "lead_count": len(leads),
        "candidate_ledger": extraction.get("candidate_ledger", []),
        "tier_counts": extraction["tier_counts"],
        "tier_a_leads": extraction["tier_a_leads"],
        "tier_b_provisional_leads": extraction["tier_b_provisional_leads"],
        "tier_c_watchlist_leads": extraction["tier_c_watchlist_leads"],
        "tier_d_rejected": extraction["tier_d_rejected"] if include_rejected else [],
        "rejected_leads": extraction["rejected_leads"] if include_rejected else [],
        "rejected_count": len(extraction["rejected_leads"]),
        "review_candidates": extraction.get("review_candidates", []),
        "hard_rejected_leads": extraction.get("hard_rejected_leads", []) if include_rejected else [],
        "hard_rejected_count": len(extraction.get("hard_rejected_leads", [])),
        "fetched_at": started,
        "run_finished_at": finished,
    }


def refuse_d365_email_sending(request: str = "") -> dict[str, Any]:
    """Refuse any email sending or outreach delivery request."""
    return {
        "sending_enabled": False,
        "request": request,
        "message": (
            "No. uk_ie_d365_leads only discovers evidence-backed lead signals. "
            "It does not send emails or unlock outreach delivery."
        ),
    }


def inspect_d365_discovery_backbone(evidence_dir: str | None = None) -> dict[str, Any]:
    """Return the local read-only Google ecosystem discovery preflight."""
    return discovery_backbone_tools.build_discovery_preflight(
        evidence_dir=Path(evidence_dir) if evidence_dir else discovery_backbone_tools.EVIDENCE_DIR
    )


def build_local_discovery_memory(evidence_dir: str | Path | None = None) -> dict[str, Any]:
    """Build local discovery memory from saved Evidence artifacts."""
    root = Path(evidence_dir) if evidence_dir else discovery_backbone_tools.EVIDENCE_DIR
    prior_final_leads: list[dict[str, Any]] = []
    duplicate_opportunities: list[dict[str, Any]] = []
    rejected_patterns: Counter[str] = Counter()
    provider_score = empty_nested_counter()
    domain_score = empty_nested_counter()
    query_score = empty_nested_counter()
    retryable_fetch_failures: list[dict[str, Any]] = []

    for payload in discovery_backbone_tools.iter_evidence_json_payloads(root):
        for record in discovery_backbone_tools.walk_records(payload):
            status = retention_or_record_status(record)
            provider = str(record.get("source_provider") or record.get("provider") or "unknown")
            query = str(record.get("source_query") or record.get("query") or "unknown")
            domain = first_domain_from_record(record) or "unknown"
            increment_score(provider_score, provider, status)
            increment_score(domain_score, domain, status)
            increment_score(query_score, query, status)
            reason = clean_snippet(record.get("reason") or record.get("rejection_reason") or record.get("final_rejection_reason") or "")
            if reason:
                rejected_patterns[reason] += 1
            if status == "final_ready":
                prior_final_leads.append(memory_record(record))
            if status == "duplicate_same_opportunity" or record.get("opportunity_fingerprint"):
                duplicate_opportunities.append(memory_record(record))
        retryable_fetch_failures.extend(
            item
            for item in collect_source_fetch_items(payload)
            if should_retry_source_fetch(item)
        )

    return {
        "artifact_type": "uk_ie_d365_discovery_memory",
        "version": DISCOVERY_MEMORY_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "local Evidence artifacts only",
        "prior_final_leads": prior_final_leads[:250],
        "prior_duplicate_opportunities": duplicate_opportunities[:250],
        "rejected_generic_patterns": dict(rejected_patterns.most_common(50)),
        "provider_success_rates": summarize_score_counter(provider_score),
        "domain_success_rates": summarize_score_counter(domain_score),
        "query_success_rates": summarize_score_counter(query_score),
        "retryable_fetch_failures": retryable_fetch_failures[:250],
    }


def build_provider_scorecard(raw_search: dict[str, Any], final_output: dict[str, Any] | None = None) -> dict[str, Any]:
    provider_score = empty_nested_counter()
    domain_score = empty_nested_counter()
    query_score = empty_nested_counter()
    final_ids = {
        str(item.get("candidate_id") or "")
        for item in (final_output or {}).get("leads", [])
        if item.get("candidate_id")
    }
    for row in raw_search.get("raw_result_ledger") or []:
        increment_score(provider_score, str(row.get("provider") or "unknown"), "raw_result")
        increment_score(domain_score, domain_from_url(row.get("normalized_url") or row.get("url")) or "unknown", "raw_result")
        increment_score(query_score, str(row.get("source_query") or "unknown"), "raw_result")
    for row in raw_search.get("candidate_ledger") or []:
        status = str(row.get("retention_status") or "unknown")
        if row.get("candidate_id") in final_ids:
            status = "final_selected"
        provider = str(row.get("source_provider") or "unknown")
        domain = first_domain_from_record(row) or "unknown"
        query = str(row.get("source_query") or "unknown")
        increment_score(provider_score, provider, status)
        increment_score(domain_score, domain, status)
        increment_score(query_score, query, status)
    for fetch in raw_search.get("source_fetches") or []:
        provider = str(fetch.get("provider") or "unknown")
        status = str(fetch.get("source_fetch_status") or "unknown")
        increment_score(provider_score, provider, f"fetch_{status}")
        increment_score(domain_score, domain_from_url(fetch.get("final_url") or fetch.get("url")) or "unknown", f"fetch_{status}")

    return {
        "artifact_type": "uk_ie_d365_provider_scorecard",
        "version": PROVIDER_SCORECARD_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": raw_search.get("run_id"),
        "provider": raw_search.get("provider"),
        "provider_budget": raw_search.get("provider_budget") or {},
        "provider_readiness": raw_search.get("provider_readiness") or {},
        "provider_scores": summarize_score_counter(provider_score),
        "domain_scores": summarize_score_counter(domain_score),
        "query_scores": summarize_score_counter(query_score),
        "final_selected_count": len(final_ids),
    }


def retry_source_fetches_from_payload(
    payload: Any,
    *,
    parse_pdfs: bool = False,
    max_urls: int = 50,
) -> dict[str, Any]:
    candidates = source_retry_candidates(payload, parse_pdfs=parse_pdfs)
    fetcher = SourceFetcher(parse_pdfs=parse_pdfs)
    results = []
    seen: set[str] = set()
    for item in candidates:
        url = item.get("url") or item.get("final_url") or item.get("evidence_url")
        key = canonical_url_key(url)
        if not key or key in seen:
            continue
        seen.add(key)
        fetched = fetcher.fetch(str(url), provider=str(item.get("provider") or "source_retry"), source_query=item.get("source_query"))
        fetched["retry_source_status"] = item.get("source_fetch_status") or item.get("reason")
        results.append(fetched)
        if len(results) >= max(1, min(int(max_urls or 50), 250)):
            break
    return {
        "artifact_type": "uk_ie_d365_source_retry_run",
        "version": SOURCE_RETRY_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "parse_pdfs": bool(parse_pdfs),
        "candidate_count": len(candidates),
        "retried_count": len(results),
        "results": results,
        "still_failed": [item for item in results if item.get("source_fetch_status") != "fetched"],
    }


def source_retry_candidates(payload: Any, *, parse_pdfs: bool = False) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in collect_source_fetch_items(payload):
        if should_retry_source_fetch(item, parse_pdfs=parse_pdfs):
            candidates.append(item)
    for record in discovery_backbone_tools.walk_records(payload):
        status = str(record.get("retention_status") or "")
        reason = str(record.get("reason") or record.get("rejection_reason") or "")
        if status == "needs_source_cleanup" or "source" in reason.lower():
            url = record.get("evidence_url") or first_nonempty(record.get("evidence_urls") or [])
            if url:
                candidates.append({**record, "url": url})
    return candidates


def collect_source_fetch_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if "source_fetch_status" in value and (value.get("url") or value.get("final_url")):
            items.append(value)
        for child in value.values():
            items.extend(collect_source_fetch_items(child))
    elif isinstance(value, list):
        for child in value:
            items.extend(collect_source_fetch_items(child))
    return items


def should_retry_source_fetch(item: dict[str, Any], *, parse_pdfs: bool = False) -> bool:
    status = str(item.get("source_fetch_status") or "").strip()
    url = str(item.get("url") or item.get("final_url") or item.get("evidence_url") or "")
    if status in NON_RETRYABLE_SOURCE_FETCH_STATUSES:
        return False
    if status == "skipped_binary_source":
        return bool(parse_pdfs and urllib.parse.urlparse(url).path.lower().endswith(".pdf"))
    return status in RETRYABLE_SOURCE_FETCH_STATUSES


def empty_nested_counter() -> dict[str, Counter[str]]:
    return {}


def increment_score(counter_map: dict[str, Counter[str]], key: str, status: str) -> None:
    counter_map.setdefault(key or "unknown", Counter())[status or "unknown"] += 1


def summarize_score_counter(counter_map: dict[str, Counter[str]]) -> list[dict[str, Any]]:
    rows = []
    for key, counts in counter_map.items():
        total = sum(counts.values())
        finalish = counts.get("final_selected", 0) + counts.get("final_ready", 0)
        rows.append(
            {
                "key": key,
                "total": total,
                "final_or_ready_count": finalish,
                "cleanup_count": counts.get("needs_source_cleanup", 0),
                "identity_count": counts.get("needs_identity_resolution", 0),
                "duplicate_count": counts.get("duplicate_same_opportunity", 0),
                "hard_reject_count": counts.get("hard_reject", 0),
                "counts": dict(counts),
            }
        )
    return sorted(rows, key=lambda item: (item["final_or_ready_count"], item["total"]), reverse=True)


def retention_or_record_status(record: dict[str, Any]) -> str:
    if record.get("retention_status"):
        return str(record["retention_status"])
    if record.get("hard_rejection_reason") or record.get("rejection_reason"):
        return "hard_reject"
    if record.get("verified_live") or record.get("final_pdf_eligible"):
        return "final_ready"
    return "unknown"


def memory_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": record.get("candidate_id"),
        "company_name": record.get("company_name"),
        "retention_status": retention_or_record_status(record),
        "company_fingerprint": record.get("company_fingerprint"),
        "opportunity_fingerprint": record.get("opportunity_fingerprint"),
        "source_provider": record.get("source_provider"),
        "evidence_urls": record.get("evidence_urls") or ([record.get("evidence_url")] if record.get("evidence_url") else []),
    }


def first_domain_from_record(record: dict[str, Any]) -> str:
    for url in record.get("evidence_urls") or []:
        domain = domain_from_url(url)
        if domain:
            return domain
    for key in ("evidence_url", "source_url", "url", "final_url"):
        domain = domain_from_url(record.get(key))
        if domain:
            return domain
    return ""


def domain_from_url(url: Any) -> str:
    parsed = urllib.parse.urlparse(str(url or ""))
    return re.sub(r"^www\.", "", parsed.netloc.lower().split(":")[0])


def provider_budget_row(provider: SearchProvider) -> dict[str, Any]:
    return {
        "configured": bool(provider.configured),
        "unavailable_reason": provider.unavailable_reason,
        "requests_attempted": 0,
        "successes": 0,
        "failures": 0,
        "timeouts": 0,
        "raw_result_count": 0,
    }


def build_initial_provider_budget() -> dict[str, dict[str, Any]]:
    return {
        provider.name: provider_budget_row(provider)
        for provider in fanout_base_providers()
    }


def raw_result_audit_row(result: SearchResult, *, search_query: str | None = None) -> dict[str, Any]:
    normalized = normalize_public_url(result.url)
    return {
        "provider": result.source,
        "title": result.title,
        "url": result.url,
        "normalized_url": normalized,
        "snippet": clean_snippet(result.snippet)[:1000],
        "published_date": result.published_date,
        "source_query": search_query or result.source_query,
        "source_query_group": result.source_query_group or result.signal_class,
        "source_url_type": result.source_url_type,
        "source_channel": result.source_channel,
        "run_id": result.run_id,
    }


def dedupe_search_results_by_url(results: list[SearchResult]) -> tuple[list[SearchResult], list[dict[str, Any]]]:
    seen: set[str] = set()
    unique: list[SearchResult] = []
    duplicates: list[dict[str, Any]] = []
    for result in results:
        normalized = normalize_public_url(result.url)
        key = canonical_url_key(normalized or result.url)
        if not key:
            unique.append(result)
            continue
        if key in seen:
            duplicates.append(
                {
                    "provider": result.source,
                    "url": result.url,
                    "canonical_url_key": key,
                    "source_query": result.source_query,
                    "reason": "duplicate_canonical_url",
                }
            )
            continue
        seen.add(key)
        unique.append(result)
    return unique, duplicates


def canonical_url_key(url: str | None) -> str:
    normalized = normalize_public_url(url)
    if not normalized:
        return ""
    parsed = urllib.parse.urlparse(normalized)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+$", "", parsed.path or "/")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    filtered_query = [
        (key, value)
        for key, value in query
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    encoded_query = urllib.parse.urlencode(sorted(filtered_query))
    return urllib.parse.urlunparse(("https", host, path, "", encoded_query, ""))


def fetch_sources_for_results(
    results: list[SearchResult],
    *,
    max_urls: int = SOURCE_FETCH_DEFAULT_MAX_URLS,
    parse_pdfs: bool = False,
    fetcher: "SourceFetcher | None" = None,
) -> list[dict[str, Any]]:
    fetcher = fetcher or SourceFetcher(parse_pdfs=parse_pdfs)
    seen: set[str] = set()
    fetched: list[dict[str, Any]] = []
    for result in results:
        key = canonical_url_key(result.url)
        if not key or key in seen:
            continue
        seen.add(key)
        fetched.append(fetcher.fetch(result.url, provider=result.source, source_query=result.source_query))
        if len(fetched) >= max(1, min(int(max_urls or SOURCE_FETCH_DEFAULT_MAX_URLS), SOURCE_FETCH_DEFAULT_MAX_URLS)):
            break
    return fetched


def enrich_results_with_source_fetches(
    results: list[SearchResult],
    fetches: list[dict[str, Any]],
) -> list[SearchResult]:
    by_key = {
        canonical_url_key(item.get("url")): item
        for item in fetches
        if item.get("url")
    }
    enriched: list[SearchResult] = []
    for result in results:
        fetch = by_key.get(canonical_url_key(result.url))
        if not fetch:
            enriched.append(result)
            continue
        final_url = clean_public_fetch_url(fetch.get("canonical_url") or fetch.get("final_url"))
        use_url = final_url or normalize_public_url(result.url) or result.url
        page_title = clean_snippet(fetch.get("page_title") or "")
        text_excerpt = clean_snippet(fetch.get("text_excerpt") or "")
        snippet_parts = [result.snippet]
        if page_title and page_title not in result.snippet:
            snippet_parts.append(page_title)
        if text_excerpt:
            snippet_parts.append(text_excerpt)
        enriched.append(
            SearchResult(
                title=result.title or page_title,
                url=use_url,
                snippet=clean_snippet(" ".join(part for part in snippet_parts if part)),
                source=result.source,
                published_date=result.published_date,
                signal_class=result.signal_class,
                source_url_type=source_url_type(use_url),
                source_query=result.source_query,
                source_query_group=result.source_query_group,
                run_id=result.run_id,
                source_channel=result.source_channel,
                original_url=result.original_url or result.url,
                final_url=final_url,
                source_fetch_status=fetch.get("source_fetch_status"),
                source_fetch=fetch,
            )
        )
    return enriched


class SourceFetcher:
    def __init__(
        self,
        *,
        timeout: int = SOURCE_FETCH_TIMEOUT_SECONDS,
        max_bytes: int = SOURCE_FETCH_MAX_BYTES,
        pdf_max_bytes: int = PDF_SOURCE_FETCH_MAX_BYTES,
        parse_pdfs: bool = False,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.pdf_max_bytes = pdf_max_bytes
        self.parse_pdfs = parse_pdfs

    def fetch(self, url: str, *, provider: str | None = None, source_query: str | None = None) -> dict[str, Any]:
        fetched_at = datetime.now(UTC).isoformat()
        normalized = normalize_public_url(url)
        base = {
            "url": url,
            "provider": provider,
            "source_query": source_query,
            "fetched_at": fetched_at,
            "verified_live": False,
        }
        skip_reason = source_fetch_skip_reason(normalized or url, allow_pdf=self.parse_pdfs)
        if skip_reason:
            return {**base, "source_fetch_status": skip_reason, "fetch_error": skip_reason}
        assert normalized is not None
        try:
            response = requests.get(
                normalized,
                headers={
                    "User-Agent": "Business_Intel/1.0 public-source lead verification",
                    "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,text/plain;q=0.8,*/*;q=0.5",
                },
                timeout=self.timeout,
                allow_redirects=True,
            )
            final_url = clean_public_fetch_url(response.url) or normalized
            final_skip_reason = source_fetch_skip_reason(final_url, allow_pdf=self.parse_pdfs)
            if final_skip_reason:
                return {
                    **base,
                    "final_url": final_url,
                    "source_name": source_name_from_url(final_url),
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "source_fetch_status": final_skip_reason,
                    "fetch_error": final_skip_reason,
                }
            content_type = response.headers.get("content-type", "")
            if is_pdf_source(content_type, final_url) and self.parse_pdfs:
                raw_pdf = response.content[: self.pdf_max_bytes]
                parsed_pdf = extract_pdf_source_text(raw_pdf, final_url)
                status = "fetched" if response.ok and parsed_pdf.get("text_excerpt") else parsed_pdf["parser_status"]
                return {
                    **base,
                    "final_url": final_url,
                    "canonical_url": None,
                    "source_name": source_name_from_url(final_url),
                    "status_code": response.status_code,
                    "content_type": content_type or "application/pdf",
                    "page_title": parsed_pdf.get("title") or source_name_from_url(final_url),
                    "source_fetch_status": status,
                    "verified_live": bool(response.ok and parsed_pdf.get("text_excerpt")),
                    "text_excerpt": str(parsed_pdf.get("text_excerpt") or "")[:4000],
                    "pdf_parser_status": parsed_pdf["parser_status"],
                    "pdf_page_count": parsed_pdf.get("page_count"),
                    "fetch_error": parsed_pdf.get("fetch_error"),
                }
            if binary_content(content_type, final_url, allow_pdf=self.parse_pdfs):
                return {
                    **base,
                    "final_url": final_url,
                    "source_name": source_name_from_url(final_url),
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "source_fetch_status": "skipped_binary_source",
                    "fetch_error": "skipped_binary_source",
                }
            raw = response.content[: self.max_bytes]
            encoding = response.encoding or response.apparent_encoding or "utf-8"
            body = raw.decode(encoding, errors="replace")
            is_html = "html" in content_type.lower() or "<html" in body[:1000].lower()
            text = html_to_text(body) if is_html else clean_snippet(body)
            page_title = html_title(body) if is_html else ""
            canonical = clean_public_fetch_url(html_canonical_url(body, final_url)) if is_html else None
            status = "fetched" if response.ok and text else "http_error"
            return {
                **base,
                "final_url": final_url,
                "canonical_url": canonical,
                "source_name": source_name_from_url(final_url),
                "status_code": response.status_code,
                "content_type": content_type,
                "page_title": page_title,
                "source_fetch_status": status,
                "verified_live": bool(response.ok and text),
                "text_excerpt": text[:4000],
            }
        except requests.Timeout as exc:
            return {**base, "source_fetch_status": "timeout", "fetch_error": _safe_error(exc)}
        except requests.RequestException as exc:
            return {**base, "source_fetch_status": "fetch_error", "fetch_error": _safe_error(exc)}
        except UnicodeError as exc:
            return {**base, "source_fetch_status": "decode_error", "fetch_error": _safe_error(exc)}


def source_fetch_skip_reason(url: str | None, *, allow_pdf: bool = False) -> str | None:
    normalized = normalize_public_url(url)
    if not normalized:
        return "skipped_non_http_source"
    if private_linkedin_source(normalized):
        return "skipped_private_linkedin_source"
    if tender_or_procurement_source("", normalized):
        return "skipped_tender_or_procurement_source"
    if fake_or_example_source("", normalized):
        return "skipped_fake_or_example_source"
    if obvious_binary_url(normalized, allow_pdf=allow_pdf):
        return "skipped_binary_source"
    return None


def obvious_binary_url(url: str, *, allow_pdf: bool = False) -> bool:
    path = urllib.parse.urlparse(url).path.lower()
    suffixes = BINARY_SOURCE_SUFFIXES
    if allow_pdf:
        suffixes = tuple(suffix for suffix in suffixes if suffix != ".pdf")
    return any(path.endswith(suffix) for suffix in suffixes)


def binary_content(content_type: str, url: str, *, allow_pdf: bool = False) -> bool:
    lower = str(content_type or "").lower()
    tokens = BINARY_CONTENT_TYPES
    if allow_pdf:
        tokens = tuple(token for token in tokens if token != "application/pdf")
    return obvious_binary_url(url, allow_pdf=allow_pdf) or any(token in lower for token in tokens)


def is_pdf_source(content_type: str, url: str) -> bool:
    lower = str(content_type or "").lower()
    return "application/pdf" in lower or urllib.parse.urlparse(str(url or "")).path.lower().endswith(".pdf")


def extract_pdf_source_text(raw_pdf: bytes, final_url: str) -> dict[str, Any]:
    """Extract public PDF text for evidence review.

    This is intentionally conservative: no text means no verified-live final
    evidence, even when the PDF was reachable.
    """
    if not raw_pdf.startswith(b"%PDF"):
        return {
            "parser_status": "pdf_invalid_or_truncated",
            "title": source_name_from_url(final_url),
            "page_count": None,
            "text_excerpt": "",
            "fetch_error": "pdf_invalid_or_truncated",
        }
    try:
        from pypdf import PdfReader
    except Exception as exc:  # noqa: BLE001 - parser availability is reported in artifacts.
        fallback_text = simple_pdf_text_fallback(raw_pdf)
        return {
            "parser_status": "pdf_text_extracted_fallback" if fallback_text else "pdf_parser_unavailable",
            "title": source_name_from_url(final_url),
            "page_count": None,
            "text_excerpt": fallback_text[:4000],
            "fetch_error": None if fallback_text else _safe_error(exc),
        }
    try:
        reader = PdfReader(BytesIO(raw_pdf))
        parts: list[str] = []
        for page in reader.pages[:20]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        text = clean_snippet(" ".join(parts))
        if not text:
            text = simple_pdf_text_fallback(raw_pdf)
        title = ""
        try:
            title = clean_snippet((reader.metadata or {}).get("/Title") or "")
        except Exception:
            title = ""
        return {
            "parser_status": "pdf_text_extracted" if text else "pdf_no_text_extracted",
            "title": title or source_name_from_url(final_url),
            "page_count": len(reader.pages),
            "text_excerpt": text[:4000],
            "fetch_error": None if text else "pdf_no_text_extracted",
        }
    except Exception as exc:  # noqa: BLE001 - source cleanup should see parser errors.
        fallback_text = simple_pdf_text_fallback(raw_pdf)
        return {
            "parser_status": "pdf_text_extracted_fallback" if fallback_text else "pdf_parse_error",
            "title": source_name_from_url(final_url),
            "page_count": None,
            "text_excerpt": fallback_text[:4000],
            "fetch_error": None if fallback_text else _safe_error(exc),
        }


def simple_pdf_text_fallback(raw_pdf: bytes) -> str:
    try:
        decoded = raw_pdf.decode("latin-1", errors="ignore")
    except Exception:
        return ""
    chunks = re.findall(r"\(([^()]{4,500})\)\s*Tj", decoded)
    chunks.extend(re.findall(r"\(([^()]{4,500})\)\s*'", decoded))
    return clean_snippet(" ".join(unescape_pdf_text(chunk) for chunk in chunks))


def unescape_pdf_text(text: str) -> str:
    return (
        text.replace(r"\(", "(")
        .replace(r"\)", ")")
        .replace(r"\\", "\\")
        .replace(r"\n", " ")
        .replace(r"\r", " ")
        .replace(r"\t", " ")
    )


def clean_public_fetch_url(url: Any) -> str | None:
    normalized = normalize_public_url(url)
    if not normalized:
        return None
    if source_fetch_skip_reason_without_binary(normalized):
        return None
    return normalized


def source_fetch_skip_reason_without_binary(url: str | None) -> str | None:
    normalized = normalize_public_url(url)
    if not normalized:
        return "skipped_non_http_source"
    if private_linkedin_source(normalized):
        return "skipped_private_linkedin_source"
    if tender_or_procurement_source("", normalized):
        return "skipped_tender_or_procurement_source"
    if fake_or_example_source("", normalized):
        return "skipped_fake_or_example_source"
    return None


def html_title(html: str) -> str:
    match = re.search(r"<title[^>]*>([\s\S]*?)</title>", html or "", flags=re.I)
    return clean_snippet(unescape(match.group(1))) if match else ""


def html_canonical_url(html: str, base_url: str) -> str | None:
    match = re.search(
        r"<link[^>]+rel=[\"'][^\"']*canonical[^\"']*[\"'][^>]+href=[\"']([^\"']+)[\"']",
        html or "",
        flags=re.I,
    )
    if not match:
        match = re.search(
            r"<link[^>]+href=[\"']([^\"']+)[\"'][^>]+rel=[\"'][^\"']*canonical[^\"']*[\"']",
            html or "",
            flags=re.I,
        )
    if not match:
        return None
    return urllib.parse.urljoin(base_url, unescape(match.group(1)))


def is_timeout_error(exc: BaseException, safe_error: str) -> bool:
    return isinstance(exc, requests.Timeout) or "timeout" in safe_error.lower() or "timed out" in safe_error.lower()


def get_search_provider(provider_name: str | None = None) -> SearchProvider:
    requested = (provider_name or os.environ.get("D365_SEARCH_PROVIDER") or "").strip().lower()
    if requested == FANOUT_PROVIDER_NAME:
        return FanoutSearchProvider()
    candidates = _provider_candidates()
    if requested:
        aliases = {p.name.lower(): p for p in candidates}
        if requested in {"google_grounding", "google", "adk_google_search"}:
            requested = "google_grounding"
        provider = aliases.get(requested)
        if provider:
            return provider if provider.configured else ProviderUnavailable(
                provider.unavailable_reason or f"{provider.name} is not configured."
            )
        return ProviderUnavailable(f"Unknown D365_SEARCH_PROVIDER: {provider_name}")
    for provider in candidates:
        if provider.configured:
            return provider
    return ProviderUnavailable()


def build_queries(query: str | None = None) -> list[str]:
    return [item["query"] for item in build_query_plan(query)]


def build_query_plan(
    query: str | None = None,
    *,
    cloud_preflight: dict[str, Any] | None = None,
    query_pack: str = "default",
    shortage_report: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    if query and query.strip():
        return [{"signal_class": "custom", "query": query.strip()}]
    base_plan = [
        {"signal_class": signal_class, "query": query_text}
        for signal_class, config in SIGNAL_CLASSES.items()
        for query_text in config["queries"]
    ]
    enriched_plan = [
        *query_pack_queries(query_pack),
        *shortage_report_queries(shortage_report),
        *base_plan,
    ]
    return discovery_backbone_tools.augment_query_plan_with_memory(
        enriched_plan,
        cloud_preflight,
        custom_query=False,
    )


def query_pack_queries(query_pack: str | None) -> list[dict[str, str]]:
    requested = (query_pack or "default").strip().lower()
    if requested in QUERY_PACK_ALIASES:
        names = QUERY_PACK_ALIASES[requested]
    elif requested in QUERY_PACKS:
        names = [requested]
    else:
        names = []
    queries: list[dict[str, str]] = []
    for name in names:
        queries.extend(dict(item) for item in QUERY_PACKS.get(name, []))
    return dedupe_query_plan(queries)


def shortage_report_queries(shortage_report: dict[str, Any] | None) -> list[dict[str, str]]:
    if not shortage_report:
        return []
    actions = " ".join(str(item) for item in shortage_report.get("next_actions") or []).lower()
    queue_counts = shortage_report.get("queue_counts") or {}
    queries: list[dict[str, str]] = []
    if queue_counts.get("source_cleanup_queue") or "source" in actions:
        queries.extend(QUERY_PACKS["case-study"])
    if queue_counts.get("identity_resolution_queue") or "identity" in actions:
        queries.append(
            {
                "signal_class": "shortage_identity_cleanup",
                "query": '"Dynamics 365" ("customer story" OR "case study") ("customer" OR "client") (UK OR Ireland) -jobs -tender',
            }
        )
    if shortage_report.get("shortage_count", 0):
        queries.extend(QUERY_PACKS["support"][:1])
    for item in shortage_report.get("selection_exclusions") or []:
        company = clean_snippet(item.get("company_name") or "")
        if company and not generic_company_title(company):
            queries.append(
                {
                    "signal_class": "shortage_company_followup",
                    "query": f'"{company}" ("Dynamics 365" OR "Business Central" OR "Power Platform") (case study OR support OR migration OR upgrade)',
                }
            )
    return dedupe_query_plan(queries)


def dedupe_query_plan(query_plan: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in query_plan:
        query_text = str(item.get("query") or "").strip()
        if not query_text or query_text in seen:
            continue
        seen.add(query_text)
        unique.append({"signal_class": str(item.get("signal_class") or "custom"), "query": query_text})
    return unique


def extract_d365_leads(
    results: list[SearchResult],
    max_results: int = 5,
    include_rejected: bool = False,
) -> dict[str, list[dict[str, Any]]] | list[dict[str, Any]]:
    tier_a: list[dict[str, Any]] = []
    tier_b: list[dict[str, Any]] = []
    tier_c: list[dict[str, Any]] = []
    tier_d: list[dict[str, Any]] = []
    candidate_ledger: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_opportunities: set[tuple[str, str]] = set()
    for result in results:
        decision = evaluate_search_result(result)
        lead = decision["lead"]
        candidate_ledger.append(lead_conservation_row(lead))
        urls = lead.get("evidence_urls") or []
        url = urls[0] if urls else f"no-url:{lead.get('company_name')}:{lead.get('signal_summary')}"
        url_key = canonical_url_key(url) or url
        opportunity_key = (
            str(lead.get("company_fingerprint") or ""),
            str(lead.get("opportunity_fingerprint") or ""),
        )
        duplicate_same_opportunity = (
            lead.get("signal_tier") != "D"
            and (
                url_key in seen_urls
                or (all(opportunity_key) and opportunity_key in seen_opportunities)
            )
        )
        if duplicate_same_opportunity:
            lead["retention_status"] = "duplicate_same_opportunity"
            candidate_ledger[-1] = lead_conservation_row(lead, retention_status="duplicate_same_opportunity")
            continue
        seen_urls.add(url_key)
        if all(opportunity_key):
            seen_opportunities.add(opportunity_key)
        tier = lead.get("signal_tier")
        if tier == "A":
            tier_a.append(lead)
        elif tier == "B":
            tier_b.append(lead)
        elif tier == "C":
            tier_c.append(lead)
        else:
            tier_d.append(lead)
    surfaced_all = tier_a + tier_b + tier_c
    surfaced = surfaced_all[:max_results]
    review_candidates = [
        lead
        for lead in surfaced_all
        if lead.get("needs_ai_review") or lead.get("deterministic_flags")
    ]
    hard_rejected = [
        lead
        for lead in tier_d
        if lead.get("hard_rejection_reason") or lead.get("rejection_reason") in HARD_REJECTION_REASONS
    ]
    if include_rejected:
        return {
            "accepted_leads": tier_a,
            "surfaced_leads": surfaced,
            "tier_a_leads": tier_a,
            "tier_b_provisional_leads": tier_b,
            "tier_c_watchlist_leads": tier_c,
            "tier_d_rejected": tier_d,
            "rejected_leads": tier_d,
            "hard_rejected_leads": hard_rejected,
            "review_candidates": review_candidates,
            "candidate_ledger": candidate_ledger,
            "tier_counts": {
                "A": len(tier_a),
                "B": len(tier_b),
                "C": len(tier_c),
                "D": len(tier_d),
            },
        }
    return surfaced


def replay_uk_ie_d365_audit(
    input_path: str,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Add audit traces to a saved run without making live search calls."""
    started = datetime.now(UTC).isoformat()
    source = Path(input_path)
    data = json.loads(source.read_text(encoding="utf-8"))
    replay = dict(data)
    leads = [augment_saved_candidate_audit(item, index=i) for i, item in enumerate(data.get("leads", []), start=1)]
    rejected = [
        augment_saved_candidate_audit(item, index=i)
        for i, item in enumerate(data.get("rejected_leads", []), start=len(leads) + 1)
    ]
    tier_a = [item for item in leads if item.get("signal_tier") == "A"]
    tier_b = [item for item in leads if item.get("signal_tier") == "B"]
    tier_c = [item for item in leads if item.get("signal_tier") == "C"]
    tier_d = [item for item in rejected if item.get("signal_tier") == "D"]
    review_candidates = [
        item
        for item in [*leads, *rejected]
        if item.get("needs_ai_review") or item.get("deterministic_flags")
    ]
    hard_rejected = [
        item
        for item in rejected
        if item.get("hard_rejection_reason") or item.get("rejection_reason") in HARD_REJECTION_REASONS
    ]
    finished = datetime.now(UTC).isoformat()
    replay.update(
        {
            "audit_metadata": audit_metadata(
                search_provider=data.get("provider") or "google_grounding",
                live_search_run=False,
                live_request_count=0,
                run_started_at=started,
                run_finished_at=finished,
            ),
            "audit_replay": True,
            "audit_replay_source_path": str(source),
            "audit_replay_note": "Offline replay over saved evidence; no provider.search_web call is made.",
            "live_search_run": False,
            "live_request_count": 0,
            "leads": leads,
            "tier_a_leads": tier_a,
            "tier_b_provisional_leads": tier_b,
            "tier_c_watchlist_leads": tier_c,
            "tier_d_rejected": tier_d,
            "rejected_leads": rejected,
            "review_candidates": review_candidates,
            "hard_rejected_leads": hard_rejected,
            "hard_rejected_count": len(hard_rejected),
            "candidate_ledger": [lead_conservation_row(item) for item in [*leads, *rejected]],
            "lead_count": len(leads),
            "rejected_count": len(rejected),
            "tier_counts": {
                "A": len(tier_a),
                "B": len(tier_b),
                "C": len(tier_c),
                "D": len(tier_d),
            },
            "previous_tier_counts": data.get("tier_counts"),
            "expected_previous_tier_counts": {"A": 0, "B": 4, "C": 1, "D": 42},
        }
    )
    replay["replay_counts_match_previous"] = replay["tier_counts"] == data.get("tier_counts")
    replay["replay_counts_match_expected"] = replay["tier_counts"] == replay["expected_previous_tier_counts"]
    if output_path:
        Path(output_path).write_text(json.dumps(replay, indent=2, ensure_ascii=False), encoding="utf-8")
    return replay


def augment_saved_candidate_audit(candidate: dict[str, Any], *, index: int) -> dict[str, Any]:
    item = dict(candidate)
    evidence_urls = item.get("evidence_urls") or []
    evidence_snippets = item.get("evidence_snippets") or []
    raw_url = evidence_urls[0] if evidence_urls else ""
    raw_snippet = evidence_snippets[0] if evidence_snippets else item.get("signal_summary") or ""
    raw_title = item.get("company_name") or item.get("signal_summary") or f"saved_candidate_{index}"
    result = SearchResult(
        title=str(raw_title),
        url=str(raw_url),
        snippet=str(raw_snippet),
        source=str(item.get("source_provider") or "saved_replay"),
        published_date=item.get("evidence_date_if_available"),
        signal_class=item.get("signal_type"),
        source_url_type=item.get("source_url_type") or source_url_type(str(raw_url)),
        source_query=item.get("source_query"),
        source_query_group=item.get("source_query_group"),
    )
    text = f"{result.title}\n{result.snippet}"
    item.setdefault("source_url_type", result.source_url_type)
    item.setdefault("missing_verification_points", missing_verification_points(item, text, raw_url))
    item.setdefault("signal_tier", "D" if item.get("rejection_reason") else "B")
    hard_reason = (
        item.get("rejection_reason")
        if item.get("rejection_reason") in HARD_REJECTION_REASONS
        else None
    )
    item.setdefault("hard_rejection_reason", hard_reason)
    item.setdefault("deterministic_flags", [] if hard_reason else review_flags_for_result(result, text=text, url=raw_url))
    item.setdefault(
        "needs_ai_review",
        bool(item.get("deterministic_flags") or item.get("missing_verification_points") or item.get("signal_tier") in {"B", "C"}),
    )
    add_candidate_audit(item, result, text, accepted=item.get("signal_tier") != "D")
    return item


def evaluate_search_result(result: SearchResult) -> dict[str, Any]:
    url = normalize_public_url(result.url)
    text = f"{result.title}\n{result.snippet}"
    combined_signal_text = f"{text}\n{url or ''}"
    source_fetch = result.source_fetch or {}
    final_url = result.final_url or source_fetch.get("final_url") or url
    identity = resolve_account_identity(result.title, url or result.url, text)
    source_channel = discovery_backbone_tools.classify_source_channel(
        source=result.source,
        url=result.url,
        explicit=result.source_channel,
    )
    base = {
        "run_id": result.run_id or make_run_id("local", result.source),
        "company_name": identity["company_name"],
        "source_company": identity["source_company"],
        "source_role": identity["source_role"],
        "account_identity_status": identity["account_identity_status"],
        "end_customer_candidates": identity["end_customer_candidates"],
        "identity_evidence_excerpt": identity["identity_evidence_excerpt"],
        "identity_confidence": identity["identity_confidence"],
        "identity_notes": identity["identity_notes"],
        "identity_resolution_required": identity["identity_resolution_required"],
        "country": infer_country(text, url or ""),
        "company_website": company_website_from_url(url) if url else None,
        "signal_type": infer_signal_type(text),
        "dynamics_product": infer_dynamics_product(combined_signal_text),
        "signal_summary": summarize_signal(text),
        "evidence_urls": [url] if url else [],
        "evidence_snippets": [clean_snippet(result.snippet or result.title)] if (result.snippet or result.title) else [],
        "evidence_date_if_available": result.published_date,
        "source_type": infer_source_type(text, url or "", result.signal_class),
        "source_url_type": result.source_url_type if url else None,
        "original_url": result.original_url or result.url,
        "final_url": final_url,
        "source_fetch_status": result.source_fetch_status or source_fetch.get("source_fetch_status"),
        "source_fetch": source_fetch,
        "verified_live": bool(source_fetch.get("verified_live")),
        "confidence_score": 0,
        "urgency_score": 0,
        "fit_for_1BT": "rejected",
        "recommended_outreach_angle": "",
        "suggested_contact_roles": [],
        "contact_route_status": "not_resolved_by_this_agent",
        "missing_verification_points": [],
        "signal_tier": "D",
        "source_provider": result.source,
        "source_query": result.source_query,
        "source_query_group": result.source_query_group or result.signal_class,
        "source_channel": source_channel,
        "final_pdf_eligible": discovery_backbone_tools.final_pdf_eligible_from_channel(source_channel),
        "rejection_reason": None,
        "hard_rejection_reason": None,
        "deterministic_flags": [],
        "needs_ai_review": False,
        "retention_status": "hard_reject",
    }
    apply_conservation_metadata(base)
    hard_rejection_reason = rejection_reason_for_result(result, text=text, url=url)
    flags = review_flags_for_result(result, text=text, url=url)
    base["deterministic_flags"] = flags
    if hard_rejection_reason:
        base["rejection_reason"] = hard_rejection_reason
        base["hard_rejection_reason"] = hard_rejection_reason
        base["missing_verification_points"] = missing_verification_points(base, text, url)
        base["retention_status"] = retention_status_for_lead(base)
        add_candidate_audit(base, result, text, accepted=False)
        return {"accepted": False, "lead": base}

    country = str(base["country"])
    product = str(base["dynamics_product"])
    signal_type = str(base["signal_type"])
    confidence = confidence_score(text, country, product, signal_type)
    urgency = urgency_score(text, signal_type)
    tier = classify_signal_tier(
        text=text,
        source_type=str(base["source_type"]),
        signal_type=signal_type,
        confidence=confidence,
        urgency=urgency,
        source_url_type=str(base["source_url_type"] or ""),
    )
    missing = missing_verification_points(base, text, url)
    base.update(
        {
            "confidence_score": confidence,
            "urgency_score": urgency,
            "fit_for_1BT": fit_for_1bt(confidence, urgency, product, signal_type),
            "recommended_outreach_angle": outreach_angle(product, signal_type),
            "suggested_contact_roles": suggested_contact_roles(product, signal_type),
            "missing_verification_points": missing,
            "signal_tier": tier,
            "rejection_reason": None,
            "hard_rejection_reason": None,
            "deterministic_flags": flags,
            "needs_ai_review": bool(flags or missing or tier in {"B", "C"}),
        }
    )
    if base["identity_resolution_required"] and "identity_resolution_required" not in base["missing_verification_points"]:
        base["missing_verification_points"].append("identity_resolution_required")
        base["needs_ai_review"] = True
    base["retention_status"] = retention_status_for_lead(base)
    apply_conservation_metadata(base)
    add_candidate_audit(base, result, text, accepted=True)
    return {"accepted": True, "lead": base}


def add_candidate_audit(
    lead: dict[str, Any],
    result: SearchResult,
    text: str,
    *,
    accepted: bool,
) -> None:
    rule_results = build_rule_results(lead, result, text)
    lead.setdefault("candidate_id", candidate_id(result.title, result.url, result.snippet))
    lead.setdefault("run_id", result.run_id or make_run_id("local", result.source))
    lead["retention_status"] = retention_status_for_lead(lead)
    apply_conservation_metadata(lead)
    lead["audit_trace"] = {
        "candidate_id": lead["candidate_id"],
        "run_id": lead.get("run_id"),
        "company_fingerprint": lead.get("company_fingerprint"),
        "opportunity_fingerprint": lead.get("opportunity_fingerprint"),
        "source_fingerprint": lead.get("source_fingerprint"),
        "retention_status": lead.get("retention_status"),
        "source_query": result.source_query,
        "source_query_group": result.source_query_group or result.signal_class,
        "source_channel": lead.get("source_channel") or result.source_channel,
        "original_url": result.original_url or result.url,
        "final_url": result.final_url or lead.get("final_url"),
        "source_fetch_status": result.source_fetch_status or lead.get("source_fetch_status"),
        "source_fetch_verified_live": bool((result.source_fetch or {}).get("verified_live") or lead.get("verified_live")),
        "final_pdf_eligible": bool(
            lead.get("final_pdf_eligible")
            if "final_pdf_eligible" in lead
            else discovery_backbone_tools.final_pdf_eligible_from_channel(lead.get("source_channel") or result.source_channel)
        ),
        "raw_title": result.title,
        "raw_url": result.url,
        "raw_snippet": result.snippet,
        "normalized_company_name": lead.get("company_name"),
        "normalized_country": lead.get("country"),
        "normalized_dynamics_product": lead.get("dynamics_product"),
        "normalized_signal_type": lead.get("signal_type"),
        "account_identity_status": lead.get("account_identity_status"),
        "source_company": lead.get("source_company"),
        "source_role": lead.get("source_role"),
        "extracted_evidence_urls": lead.get("evidence_urls") or [],
        "extracted_evidence_snippets": lead.get("evidence_snippets") or [],
        "rule_results": rule_results,
    }
    lead["final_decision"] = final_decision(lead, accepted=accepted, rule_results=rule_results)


def candidate_id(title: str, url: str, snippet: str) -> str:
    digest = hashlib.sha256(f"{title}\n{url}\n{snippet}".encode("utf-8", errors="ignore")).hexdigest()
    return f"cand_{digest[:16]}"


def build_rule_results(lead: dict[str, Any], result: SearchResult, text: str) -> list[dict[str, Any]]:
    url = normalize_public_url(result.url)
    combined = f"{result.title}\n{result.url}\n{result.snippet}"
    source_type = str(lead.get("source_type") or "")
    signal_type = str(lead.get("signal_type") or "")
    source_url = str(lead.get("source_url_type") or source_url_type(url))
    has_evidence = bool(url)
    has_d365 = has_dynamics_evidence(f"{text}\n{url or ''}")
    d365_guard_pass = has_d365 or query_has_dynamics_signal(result)
    country = bool(lead.get("country"))
    country_guard_pass = country or query_has_market_signal(result)
    tender_terms = matched_terms(combined, [*TENDER_DOMAINS, *TENDER_TERMS])
    generic_it = generic_it_support_only(text)
    vendor_terms = matched_terms(combined, VENDOR_TERMS)
    target_terms = matched_terms(combined, TARGET_CUSTOMER_TERMS)
    agency_terms = matched_terms(combined, AGENCY_TERMS)
    hiring_company_terms = matched_terms(combined, DEFENSIBLE_HIRING_COMPANY_TERMS)
    direct_terms = matched_terms(combined, DIRECT_EMPLOYER_TERMS)
    commercial_terms = matched_terms(combined, COMMERCIAL_SIGNAL_TERMS)
    installed_base = source_type == "installed_base"
    grounding_redirect = source_url == "grounding_redirect"
    clean_url = source_url == "clean_public_url"
    return [
        rule_result(
            "has_evidence_url",
            "Has evidence URL",
            has_evidence,
            "blocking",
            [url] if url else [],
            result,
            "url",
            "Candidate has at least one normalized public evidence URL." if has_evidence else "Candidate has no usable public evidence URL.",
        ),
        rule_result(
            "has_explicit_d365_or_business_app_evidence",
            "Has explicit Dynamics 365 or Microsoft business app evidence",
            d365_guard_pass,
            "blocking",
            matched_d365_terms(text),
            result,
            "combined_text",
            "Title/snippet/URL or source query contains a Dynamics 365 or connected Microsoft business app signal." if d365_guard_pass else "Title/snippet lacks explicit Dynamics 365 or connected Microsoft business app evidence.",
        ),
        rule_result(
            "uk_or_ireland_evidenced",
            "UK or Ireland evidenced",
            country_guard_pass,
            "blocking",
            matched_country_terms(combined),
            result,
            "combined_text",
            "Candidate text, URL, or source query evidences UK/Ireland scope." if country_guard_pass else "Candidate text and URL do not evidence UK/Ireland scope.",
        ),
        rule_result(
            "tender_or_procurement_out_of_scope",
            "Tender/procurement out of scope",
            not bool(tender_terms),
            "blocking",
            tender_terms,
            result,
            "combined_text",
            "No tender/procurement exclusion term was found." if not tender_terms else "Tender/procurement exclusion term was found.",
        ),
        rule_result(
            "generic_it_support_only",
            "Generic IT support only",
            not generic_it or query_has_dynamics_signal(result),
            "blocking" if generic_it and not query_has_dynamics_signal(result) else "informational",
            ["it support"] if generic_it else [],
            result,
            "combined_text",
            "Candidate is not generic IT support without Dynamics evidence." if not generic_it else "Candidate appears generic in the snippet; AI/source review may still inspect query-matched D365 context.",
        ),
        rule_result(
            "vendor_or_service_provider_without_target_customer",
            "Vendor/service-provider without target customer",
            not (vendor_terms and not target_terms),
            "informational",
            vendor_terms if vendor_terms and not target_terms else target_terms,
            result,
            "combined_text",
            "Candidate is not a vendor page without a defensible target customer." if not (vendor_terms and not target_terms) else "Vendor/service-provider terms were found; AI vetting should inspect whether a target customer is present.",
        ),
        rule_result(
            "recruitment_agency_without_defensible_hiring_company",
            "Recruitment agency without defensible hiring company",
            not (agency_terms and not hiring_company_terms),
            "informational",
            agency_terms if agency_terms and not hiring_company_terms else hiring_company_terms,
            result,
            "combined_text",
            "Candidate is not an unsupported recruitment-agency/job-board item." if not (agency_terms and not hiring_company_terms) else "Recruitment/job-board terms were found; AI vetting should inspect whether a defensible employer is present.",
        ),
        rule_result(
            "installed_base_only",
            "Installed base only",
            not installed_base,
            "scoring",
            ["installed_base"] if installed_base else [],
            result,
            "combined_text",
            "Candidate is not classified as installed-base only." if not installed_base else "Candidate is classified as installed-base/watchlist evidence.",
        ),
        rule_result(
            "commercial_signal_present",
            "Commercial signal present",
            bool(commercial_terms) or signal_type in SIGNAL_CLASSES,
            "scoring",
            commercial_terms,
            result,
            "combined_text",
            "Candidate has a commercial/change/hiring signal." if (commercial_terms or signal_type in SIGNAL_CLASSES) else "No commercial/change/hiring signal was found.",
        ),
        rule_result(
            "direct_employer_hiring_signal",
            "Direct employer hiring signal",
            direct_employer_signal(text),
            "scoring",
            direct_terms,
            result,
            "combined_text",
            "Direct employer hiring terms were found." if direct_terms else "No direct employer hiring terms were found.",
        ),
        rule_result(
            "target_customer_extractable_from_case_study",
            "Target customer extractable from case study",
            bool(target_terms or extract_named_target_company(text)),
            "scoring",
            target_terms or ([extract_named_target_company(text)] if extract_named_target_company(text) else []),
            result,
            "combined_text",
            "Target customer evidence is extractable." if (target_terms or extract_named_target_company(text)) else "No target customer evidence was extractable.",
        ),
        rule_result(
            "grounding_redirect_url_detected",
            "Grounding redirect URL detected",
            grounding_redirect,
            "informational",
            ["vertexaisearch.cloud.google.com/grounding-api-redirect"] if grounding_redirect else [],
            result,
            "url",
            "Evidence URL is a Google grounding redirect." if grounding_redirect else "Evidence URL is not a Google grounding redirect.",
        ),
        rule_result(
            "clean_public_url_detected",
            "Clean public URL detected",
            clean_url,
            "informational",
            [url] if clean_url and url else [],
            result,
            "url",
            "Evidence URL is a clean public URL." if clean_url else "Evidence URL is not a clean public URL.",
        ),
    ]


def rule_result(
    rule_id: str,
    rule_name: str,
    passed: bool,
    severity: str,
    terms: list[str],
    result: SearchResult,
    evidence_field_used: str,
    explanation: str,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "rule_name": rule_name,
        "passed": bool(passed),
        "severity": severity,
        "matched_terms": terms,
        "matched_text_excerpt": matched_excerpt(result, terms),
        "evidence_field_used": evidence_field_used,
        "explanation": explanation,
    }


def matched_terms(text: str, terms: Any) -> list[str]:
    lower = str(text or "").lower()
    return [term for term in terms if term and str(term).lower() in lower]


def matched_excerpt(result: SearchResult, terms: list[str]) -> str:
    if not terms:
        return ""
    fields = [result.title, result.url, result.snippet]
    combined = "\n".join(str(field or "") for field in fields)
    lower = combined.lower()
    for term in terms:
        idx = lower.find(str(term).lower())
        if idx >= 0:
            start = max(0, idx - 70)
            end = min(len(combined), idx + len(str(term)) + 110)
            return clean_snippet(combined[start:end])
    return ""


def matched_d365_terms(text: str) -> list[str]:
    terms = ["dynamics 365", "d365", "dynamics crm", "microsoft business applications", "microsoft business apps", "microsoft business app", "business central", "dataverse", "power platform", "power apps"]
    return matched_terms(text, terms)


def matched_country_terms(text: str) -> list[str]:
    terms: list[str] = []
    for country_terms in COUNTRY_TERMS.values():
        terms.extend(country_terms)
    return matched_terms(text, terms)


def final_decision(
    lead: dict[str, Any],
    *,
    accepted: bool,
    rule_results: list[dict[str, Any]],
) -> dict[str, Any]:
    tier = str(lead.get("signal_tier") or "D")
    rejection_reason = lead.get("rejection_reason") if tier == "D" else None
    flags = list(lead.get("deterministic_flags") or [])
    hard_rejection_reason = lead.get("hard_rejection_reason") or (
        rejection_reason if rejection_reason in HARD_REJECTION_REASONS else None
    )
    return {
        "final_tier": tier,
        "accepted": bool(accepted and tier != "D"),
        "rejection_reason": rejection_reason,
        "hard_rejection_reason": hard_rejection_reason,
        "deterministic_flags": flags,
        "needs_ai_review": bool(lead.get("needs_ai_review") or flags),
        "retention_status": retention_status_for_lead(lead),
        "source_channel": lead.get("source_channel"),
        "final_pdf_eligible": bool(
            lead.get("final_pdf_eligible")
            if "final_pdf_eligible" in lead
            else discovery_backbone_tools.final_pdf_eligible_from_channel(lead.get("source_channel"))
        ),
        "promotion_reason": promotion_reason(lead, rule_results) if tier != "D" else None,
        "confidence_score": lead.get("confidence_score", 0),
        "urgency_score": lead.get("urgency_score", 0),
        "fit_for_1BT": lead.get("fit_for_1BT"),
        "missing_verification_points": lead.get("missing_verification_points") or [],
        "human_review_recommended": human_review_recommended(lead, rule_results),
        "human_review_reason": human_review_reason(lead, rule_results),
        "decision_rule_summary": decision_rule_summary(lead, rule_results),
    }


def promotion_reason(lead: dict[str, Any], rule_results: list[dict[str, Any]]) -> str:
    tier = str(lead.get("signal_tier") or "")
    if tier == "A":
        return "Deterministic rules found evidence URL, Dynamics evidence, UK/Ireland evidence, and a strong commercial signal."
    if tier == "B":
        return "Deterministic rules found a useful commercial signal but one or more verification points remain."
    if tier == "C":
        return "Deterministic rules found installed-base or weak-urgency evidence, so the candidate remains visible as watchlist."
    return ""


def human_review_recommended(lead: dict[str, Any], rule_results: list[dict[str, Any]]) -> bool:
    if lead.get("needs_ai_review") or lead.get("deterministic_flags"):
        return True
    if lead.get("missing_verification_points"):
        return True
    if lead.get("signal_tier") in {"B", "C"}:
        return True
    risk_reasons = {
        "vendor_or_service_provider_page_without_defensible_target_customer",
        "recruitment_agency_post_without_defensible_hiring_company",
        "uk_ireland_not_evidenced",
    }
    return lead.get("rejection_reason") in risk_reasons or any(
        rule["rule_id"] == "grounding_redirect_url_detected" and rule["passed"]
        for rule in rule_results
    )


def human_review_reason(lead: dict[str, Any], rule_results: list[dict[str, Any]]) -> str:
    flags = list(lead.get("deterministic_flags") or [])
    if flags:
        return f"Candidate has deterministic AI-review flags: {', '.join(flags)}."
    if lead.get("missing_verification_points"):
        return "Candidate has unresolved verification points."
    if lead.get("signal_tier") == "C":
        return "Installed-base or weak-urgency candidate may become useful if a current change/support trigger is found."
    reason = lead.get("rejection_reason")
    if reason == "vendor_or_service_provider_page_without_defensible_target_customer":
        return "Vendor/case-study pages can hide a target customer if extraction is weak."
    if reason == "recruitment_agency_post_without_defensible_hiring_company":
        return "Recruitment/job-board snippets can hide the actual employer."
    if reason == "uk_ireland_not_evidenced":
        return "UK/Ireland evidence may exist on the source page but be absent from the snippet."
    if any(rule["rule_id"] == "grounding_redirect_url_detected" and rule["passed"] for rule in rule_results):
        return "Clean source URL is not resolved from the grounding redirect."
    return "No special human-review risk was identified."


def decision_rule_summary(lead: dict[str, Any], rule_results: list[dict[str, Any]]) -> list[str]:
    if lead.get("signal_tier") == "D":
        reason = lead.get("rejection_reason") or "unknown"
        failed = [rule["rule_id"] for rule in rule_results if rule["severity"] == "blocking" and not rule["passed"]]
        hard = lead.get("hard_rejection_reason") or ("not_hard_rejected" if lead.get("deterministic_flags") else reason)
        return [f"Tier D because {reason}.", f"Hard rejection reason: {hard}.", f"Failed blocking rules: {', '.join(failed) or 'none recorded'}."]
    tier = lead.get("signal_tier")
    source_type = lead.get("source_type")
    flags = ", ".join(lead.get("deterministic_flags") or [])
    if tier == "A":
        suffix = f"; review flags: {flags}" if flags else ""
        return [f"Tier A from source_type={source_type}, confidence={lead.get('confidence_score')}, urgency={lead.get('urgency_score')}{suffix}."]
    if tier == "B":
        suffix = f"; review flags: {flags}" if flags else ""
        return [f"Tier B from source_type={source_type}; missing verification: {', '.join(lead.get('missing_verification_points') or []) or 'none'}{suffix}."]
    suffix = f"; review flags: {flags}" if flags else ""
    return [f"Tier C from source_type={source_type}; watchlist/installed-base or weak urgency{suffix}."]


def rejection_reason_for_result(result: SearchResult, *, text: str, url: str | None) -> str | None:
    """Return only hard deterministic guardrail rejections.

    Risky evidence-shape cases are intentionally not rejected here. They are
    emitted as deterministic flags so the AI vetter can interpret them.
    """
    if not url:
        return "missing_evidence_url"
    combined = f"{text}\n{url}"
    if fake_or_example_source(combined, url):
        return "fake_or_example_url"
    if private_linkedin_source(url):
        return "private_or_linkedin_source_excluded"
    if tender_or_procurement_source(text, url):
        return "tender_or_procurement_out_of_scope"
    if generic_it_support_only(text) and not query_has_dynamics_signal(result):
        return "generic_it_support_without_dynamics_365_evidence"
    if not has_dynamics_evidence(combined) and not query_has_dynamics_signal(result):
        return "missing_explicit_dynamics_365_or_business_app_evidence"
    country = infer_country(text, url)
    if not country and not query_has_market_signal(result):
        return "uk_ireland_not_evidenced"
    return None


def review_flags_for_result(result: SearchResult, *, text: str, url: str | None) -> list[str]:
    """Return non-blocking evidence-shape flags for AI opportunity vetting."""
    flags: list[str] = []
    combined = f"{text}\n{url or ''}"
    if url and result.source_url_type == "grounding_redirect":
        flags.append("grounding_redirect_needs_clean_source")
    if url and not has_dynamics_evidence(combined) and query_has_dynamics_signal(result):
        flags.append("missing_explicit_d365_in_snippet_needs_source_check")
    if url and not infer_country(text, url) and query_has_market_signal(result):
        flags.append("uk_ireland_not_evidenced_in_snippet")
    if url and vendor_page_without_target_customer(text, url):
        flags.append("vendor_or_service_provider_page_without_defensible_target_customer")
    if url and recruitment_agency_without_hiring_company(text, url):
        flags.append("recruitment_agency_post_without_defensible_hiring_company")
    if url and len(clean_snippet(text)) < 80:
        flags.append("thin_snippet_needs_source_check")
    return list(dict.fromkeys(flags))


def classify_signal_tier(
    *,
    text: str,
    source_type: str,
    signal_type: str,
    confidence: int,
    urgency: int,
    source_url_type: str,
) -> str:
    lower = text.lower()
    if source_type == "installed_base":
        if any(term in lower for term in ("hiring", "support", "migration", "upgrade", "rollout", "implementation")):
            return "B" if source_url_type == "grounding_redirect" else "A"
        return "C"
    if source_type == "job_posting":
        if direct_employer_signal(text) and confidence >= 65:
            return "A"
        return "B"
    if any(term in lower for term in ("migration", "upgrade", "rollout", "implementation", "integration", "support", "backlog", "rescue")):
        if confidence >= 70 and urgency >= 55 and source_url_type != "grounding_redirect":
            return "A"
        return "B"
    if signal_type == "transformation_trigger":
        return "B"
    return "C"


def missing_verification_points(base: dict[str, Any], text: str, url: str | None) -> list[str]:
    missing: list[str] = []
    if not url:
        missing.append("find_public_evidence_url")
    if not base.get("country"):
        missing.append("verify_uk_or_ireland_scope")
    if not has_dynamics_evidence(text):
        missing.append("verify_explicit_dynamics_365_or_microsoft_business_app_evidence")
    if base.get("source_url_type") == "grounding_redirect":
        missing.append("resolve_clean_public_source_url_if_available")
    if base.get("source_type") == "job_posting" and not direct_employer_signal(text):
        missing.append("verify_actual_direct_employer")
    if base.get("source_type") == "installed_base":
        missing.append("verify_current_support_change_or_augmentation_trigger")
    return missing


def direct_employer_signal(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in DIRECT_EMPLOYER_TERMS) and not recruitment_agency_without_hiring_company(text, "")


def has_dynamics_evidence(text: str) -> bool:
    lower = text.lower()
    d365 = "dynamics 365" in lower or "d365" in lower or "dynamics crm" in lower
    microsoft_business_apps = (
        "microsoft business applications" in lower
        or "microsoft business apps" in lower
        or "microsoft business app" in lower
    )
    business_apps = any(
        token in lower
        for token in ("business central", "dataverse", "power platform", "power apps")
    )
    return d365 or microsoft_business_apps or (
        business_apps and ("dynamics" in lower or "crm" in lower or "erp" in lower or "business application" in lower)
    )


def generic_it_support_only(text: str) -> bool:
    lower = text.lower()
    return "it support" in lower and not has_dynamics_evidence(lower)


def tender_or_procurement_source(text: str, url: str) -> bool:
    lower = f"{text} {url}".lower()
    return any(domain in lower for domain in TENDER_DOMAINS) or any(term in lower for term in TENDER_TERMS)


def fake_or_example_source(text: str, url: str) -> bool:
    lower = f"{text} {url}".lower()
    parsed = urllib.parse.urlparse(url)
    host = (parsed.netloc or parsed.path).split("/")[0].split(":")[0].lower()
    return (
        host in FAKE_OR_EXAMPLE_HOSTS
        or host.endswith(".example")
        or "example.test" in lower
        or "sample.demo" in lower
    )


def private_linkedin_source(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def vendor_page_without_target_customer(text: str, url: str) -> bool:
    lower = f"{text} {url}".lower()
    return any(term in lower for term in VENDOR_TERMS) and not any(term in lower for term in TARGET_CUSTOMER_TERMS)


def recruitment_agency_without_hiring_company(text: str, url: str) -> bool:
    lower = f"{text} {url}".lower()
    return any(term in lower for term in AGENCY_TERMS) and not any(term in lower for term in DEFENSIBLE_HIRING_COMPANY_TERMS)


def query_context_text(result: SearchResult) -> str:
    return " ".join(
        str(value or "")
        for value in (result.source_query, result.source_query_group, result.signal_class)
    )


def query_has_dynamics_signal(result: SearchResult) -> bool:
    query_text = query_context_text(result)
    return has_dynamics_evidence(query_text) or any(
        term in query_text.lower()
        for term in ("dynamics 365", "d365", "dynamics crm", "business central", "dataverse", "power platform")
    )


def query_has_market_signal(result: SearchResult) -> bool:
    query_text = query_context_text(result)
    return bool(infer_country(query_text, ""))


def infer_country(text: str, url: str = "") -> str | None:
    lower = f"{text} {url}".lower()
    if "sri lanka" in lower and not any(t in lower for t in COUNTRY_TERMS["United Kingdom"] + COUNTRY_TERMS["Ireland"]):
        return None
    uk_hit = any(term in lower for term in COUNTRY_TERMS["United Kingdom"]) or url.endswith(".uk")
    ie_hit = any(term in lower for term in COUNTRY_TERMS["Ireland"]) or url.endswith(".ie")
    if uk_hit and "northern ireland" in lower:
        return "United Kingdom"
    if uk_hit:
        return "United Kingdom"
    if ie_hit:
        return "Ireland"
    return None


def infer_dynamics_product(text: str) -> str:
    lower = text.lower()
    for product, terms in D365_PRODUCTS.items():
        if any(term in lower for term in terms):
            return product
    return "Microsoft Dynamics 365"


def infer_signal_type(text: str) -> str:
    lower = text.lower()
    for signal_class, config in SIGNAL_CLASSES.items():
        if any(term in lower for term in config["terms"]):
            return signal_class
    for signal_type, terms in SIGNAL_TYPES.items():
        if any(term in lower for term in terms):
            return signal_type
    return "d365_public_evidence"


def infer_source_type(text: str, url: str, signal_class: str | None) -> str:
    if signal_class and signal_class in SIGNAL_CLASSES:
        return str(SIGNAL_CLASSES[signal_class]["source_type"])
    signal_type = infer_signal_type(text)
    if signal_type in SIGNAL_CLASSES:
        return str(SIGNAL_CLASSES[signal_type]["source_type"])
    lower = f"{text} {url}".lower()
    if any(term in lower for term in ("job", "vacancy", "hiring")):
        return "job_posting"
    if any(term in lower for term in ("case study", "customer story")):
        return "installed_base"
    return "public_web"


def confidence_score(text: str, country: str, product: str, signal_type: str) -> int:
    score = 35
    if country:
        score += 15
    if product != "Microsoft Dynamics 365":
        score += 15
    if signal_type != "d365_public_evidence":
        score += 20
    if re.search(r"\b(company|council|nhs|university|limited|ltd|plc)\b", text, re.I):
        score += 5
    if any(term in text.lower() for term in ("failed", "urgent", "backlog", "support", "rescue")):
        score += 10
    return min(score, 95)


def urgency_score(text: str, signal_type: str) -> int:
    lower = text.lower()
    score = 30
    if signal_type in {"hiring_support_or_augmentation", "hiring_pain"}:
        score += 25
    if signal_type in {"implementation_rescue_or_backlog", "managed_services_or_support"}:
        score += 35
    if any(term in lower for term in ("urgent", "immediate", "asap", "backlog", "failed", "rescue")):
        score += 20
    return min(score, 95)


def fit_for_1bt(confidence: int, urgency: int, product: str, signal_type: str) -> str:
    average = (confidence + urgency) // 2
    if average >= 75:
        return "high"
    if average >= 55:
        return "medium"
    return "watch"


def outreach_angle(product: str, signal_type: str) -> str:
    if signal_type == "implementation_rescue_or_backlog":
        return f"Offer a low-risk {product} rescue/stabilisation assessment with evidence-led next steps."
    if signal_type == "upgrade_or_migration":
        return f"Position 1BT around {product} migration, integration, and rollout support capacity."
    if signal_type == "hiring_support_or_augmentation":
        return f"Offer specialist {product} delivery/support augmentation to reduce hiring pressure."
    return f"Open with the public {product} signal and ask whether specialist support capacity would help."


def suggested_contact_roles(product: str, signal_type: str) -> list[str]:
    roles = ["Head of IT", "IT Director", "Business Systems Manager"]
    if "Customer" in product or "Sales" in product or "CE" in product:
        roles.extend(["CRM Manager", "Customer Operations Director"])
    if "Finance" in product or "Business Central" in product:
        roles.extend(["Finance Systems Manager", "ERP Manager"])
    return roles


def missing_provider_env_vars() -> dict[str, list[str]]:
    return {
        "google_grounding": [
            "D365_ENABLE_GOOGLE_GROUNDING=true",
            "GOOGLE_GENAI_USE_VERTEXAI or ADK local Google Search auth",
        ],
        "tavily": ["TAVILY_API_KEY"],
        "exa": ["EXA_API_KEY"],
        "serper": ["SERPER_API_KEY"],
        "serpapi": ["SERPAPI_API_KEY"],
        "firecrawl": ["FIRECRAWL_API_KEY"],
        "custom_search_api": ["GOOGLE_CSE_API_KEY", "GOOGLE_CSE_CX"],
    }


def google_native_readiness() -> dict[str, Any]:
    env = {
        "GOOGLE_GENAI_USE_VERTEXAI": _presence("GOOGLE_GENAI_USE_VERTEXAI"),
        "GOOGLE_CLOUD_PROJECT": _presence("GOOGLE_CLOUD_PROJECT"),
        "GOOGLE_CLOUD_LOCATION": _presence("GOOGLE_CLOUD_LOCATION"),
        "GEMINI_API_KEY": _presence("GEMINI_API_KEY"),
        "GOOGLE_API_KEY": _presence("GOOGLE_API_KEY"),
        "D365_ENABLE_GOOGLE_GROUNDING": _presence("D365_ENABLE_GOOGLE_GROUNDING"),
    }
    adc = _adc_status()
    api_key_ready = env["GEMINI_API_KEY"] == "present" or env["GOOGLE_API_KEY"] == "present"
    vertex_ready = bool(adc["available"] and adc["project_present"])
    ready = api_key_ready or vertex_ready
    if ready:
        reason = "Google-native credentials appear available locally."
    else:
        reason = "No Gemini API key and no ADC project were available."
    return {
        "ready": ready,
        "reason": reason,
        "env": env,
        "adc": adc,
        "effective_project": effective_google_project(adc),
        "cost_risk": (
            "Live grounded search uses remote Google model/search services and may incur project/API cost."
        ),
    }


def effective_google_project(adc: dict[str, Any] | None = None) -> str | None:
    adc = adc if adc is not None else _adc_status()
    return (
        os.environ.get("D365_GOOGLE_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or adc.get("project")
        or None
    )


def require_google_project(required_project: str | None) -> dict[str, Any]:
    readiness = google_native_readiness()
    effective_project = readiness.get("effective_project")
    if required_project and effective_project != required_project:
        raise RuntimeError(
            f"Refusing live Google run: effective project is {effective_project!r}, "
            f"required {required_project!r}."
        )
    return readiness


def _prepare_google_native_env() -> None:
    readiness = google_native_readiness()
    adc = readiness["adc"]
    if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("GEMINI_API_KEY") and adc.get("available"):
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
        project = readiness.get("effective_project")
        if project:
            os.environ.setdefault("GOOGLE_CLOUD_PROJECT", str(project))
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")


def _presence(name: str) -> str:
    return "present" if os.environ.get(name) else "missing"


def _adc_status() -> dict[str, Any]:
    try:
        import google.auth

        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return {
            "available": True,
            "project_present": bool(project),
            "project": project or None,
            "credential_type": type(credentials).__name__,
        }
    except Exception as exc:  # noqa: BLE001 - readiness only.
        return {
            "available": False,
            "project_present": False,
            "project": None,
            "error_type": type(exc).__name__,
            "error": str(exc)[:200],
        }


def parse_search_results(text: str, *, source: str, limit: int = 5) -> list[SearchResult]:
    raw = _extract_json(text)
    if raw is None:
        return []
    rows = raw if isinstance(raw, list) else [raw]
    results = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("link") or item.get("href")
        normalized = normalize_public_url(url)
        if not normalized:
            continue
        results.append(
            SearchResult(
                title=str(item.get("title") or item.get("name") or ""),
                url=normalized,
                snippet=str(item.get("snippet") or item.get("description") or item.get("content") or ""),
                source=source,
                published_date=item.get("published_date") or item.get("date"),
                source_url_type=source_url_type(normalized),
            )
        )
        if len(results) >= limit:
            break
    return results


def normalize_public_url(url: Any) -> str | None:
    raw = str(url or "").strip()
    if not raw or raw.startswith(("mailto:", "javascript:", "#")):
        return None
    if not re.match(r"^https?://", raw, flags=re.I):
        raw = f"https://{raw}"
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or "." not in parsed.netloc:
        return None
    if parsed.hostname and parsed.hostname.lower() in {"localhost", "127.0.0.1"}:
        return None
    return urllib.parse.urlunparse(parsed)


def source_url_type(url: str | None) -> str:
    lower = str(url or "").lower()
    if not lower:
        return "unknown"
    if "vertexaisearch.cloud.google.com/grounding-api-redirect" in lower:
        return "grounding_redirect"
    return "clean_public_url"


def company_website_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else url


def source_name_from_url(url: str | None) -> str:
    parsed = urllib.parse.urlparse(str(url or ""))
    host = (parsed.netloc or parsed.path).split("/")[0].lower()
    return host.removeprefix("www.")


def make_run_id(started_at: str, provider_name: str) -> str:
    seed = f"{started_at}:{provider_name}:{LEAD_CONSERVATION_VERSION}"
    digest = hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()
    return f"run_{digest[:16]}"


def stable_fingerprint(prefix: str, *parts: Any) -> str:
    normalized = "\n".join(normalize_fingerprint_text(part) for part in parts if part is not None)
    digest = hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def normalize_fingerprint_text(value: Any) -> str:
    text = clean_snippet(value)
    text = re.sub(r"&", " and ", text.lower())
    text = re.sub(r"https?://", "", text)
    text = re.sub(r"www\.", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def apply_conservation_metadata(lead: dict[str, Any]) -> None:
    evidence_url = first_nonempty(lead.get("evidence_urls") or [])
    lead["company_fingerprint"] = stable_fingerprint("company", lead.get("company_name"))
    lead["source_fingerprint"] = stable_fingerprint("source", evidence_url, lead.get("source_provider"))
    lead["opportunity_fingerprint"] = stable_fingerprint(
        "opp",
        lead.get("company_name"),
        lead.get("dynamics_product"),
        lead.get("signal_type"),
        evidence_url,
        lead.get("signal_summary"),
    )
    lead["lead_conservation_version"] = LEAD_CONSERVATION_VERSION


def first_nonempty(values: list[Any]) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def lead_conservation_row(
    lead: dict[str, Any],
    *,
    retention_status: str | None = None,
) -> dict[str, Any]:
    status = retention_status or lead.get("retention_status") or retention_status_for_lead(lead)
    return {
        "run_id": lead.get("run_id"),
        "candidate_id": lead.get("candidate_id") or (lead.get("audit_trace") or {}).get("candidate_id"),
        "company_name": lead.get("company_name"),
        "source_company": lead.get("source_company"),
        "source_role": lead.get("source_role"),
        "account_identity_status": lead.get("account_identity_status"),
        "company_fingerprint": lead.get("company_fingerprint"),
        "opportunity_fingerprint": lead.get("opportunity_fingerprint"),
        "source_fingerprint": lead.get("source_fingerprint"),
        "signal_tier": lead.get("signal_tier"),
        "signal_type": lead.get("signal_type"),
        "dynamics_product": lead.get("dynamics_product"),
        "retention_status": status,
        "source_provider": lead.get("source_provider"),
        "source_channel": lead.get("source_channel"),
        "source_query": lead.get("source_query") or (lead.get("audit_trace") or {}).get("source_query"),
        "source_query_group": lead.get("source_query_group") or (lead.get("audit_trace") or {}).get("source_query_group"),
        "original_url": lead.get("original_url"),
        "final_url": lead.get("final_url"),
        "source_fetch_status": lead.get("source_fetch_status"),
        "verified_live": bool(lead.get("verified_live")),
        "final_pdf_eligible": bool(
            lead.get("final_pdf_eligible")
            if "final_pdf_eligible" in lead
            else discovery_backbone_tools.final_pdf_eligible_from_channel(lead.get("source_channel"))
        ),
        "rejection_reason": lead.get("rejection_reason"),
        "hard_rejection_reason": lead.get("hard_rejection_reason"),
        "deterministic_flags": lead.get("deterministic_flags") or [],
        "missing_verification_points": lead.get("missing_verification_points") or [],
        "evidence_urls": lead.get("evidence_urls") or [],
        "identity_resolution_required": bool(lead.get("identity_resolution_required")),
    }


def retention_status_for_lead(lead: dict[str, Any]) -> str:
    if lead.get("hard_rejection_reason") or lead.get("rejection_reason") in HARD_REJECTION_REASONS:
        return "hard_reject"
    if lead.get("identity_resolution_required") or lead.get("account_identity_status") in {"ambiguous", "generic_title"}:
        return "needs_identity_resolution"
    flags = set(lead.get("deterministic_flags") or [])
    cleanup_flags = {
        "grounding_redirect_needs_clean_source",
        "missing_explicit_d365_in_snippet_needs_source_check",
        "uk_ireland_not_evidenced_in_snippet",
        "thin_snippet_needs_source_check",
        "recruitment_agency_post_without_defensible_hiring_company",
    }
    if flags & cleanup_flags or lead.get("missing_verification_points"):
        return "needs_source_cleanup"
    return "final_ready"


def resolve_account_identity(title: str, url: str, text: str) -> dict[str, Any]:
    combined = f"{title}\n{text}\n{url}"
    evidence_text = f"{title}\n{text}"
    source_company = source_company_from_url(url)
    source_role = infer_source_role(combined, url)
    extracted = extract_named_target_company(evidence_text)
    title_candidate = extract_company_from_case_title(title)
    generic_title = generic_company_title(title)
    end_customer_candidates = []
    for candidate in (extracted, title_candidate):
        if candidate and candidate not in end_customer_candidates:
            end_customer_candidates.append(candidate)

    if extracted:
        company_name = extracted
        status = "resolved_end_customer"
        confidence = "high"
        required = False
        notes = ["Named customer extracted from title/snippet evidence before source/vendor fallback."]
    elif title_candidate and not generic_title:
        company_name = title_candidate
        status = "direct_company_page" if source_role not in {"partner", "vendor", "job_board"} else "resolved_end_customer"
        confidence = "medium"
        required = False
        notes = ["Company inferred from non-generic title."]
    elif title_candidate:
        company_name = title_candidate
        status = "ambiguous"
        confidence = "low"
        required = True
        notes = ["Title has a possible account name but also looks generic; keep for identity review."]
    else:
        company_name = source_company or infer_company_name_from_host(url)
        status = "generic_title" if generic_title else "ambiguous"
        confidence = "low"
        required = source_role in {"partner", "vendor", "job_board"} or generic_title
        notes = ["No defensible end-customer name was extracted; source/host fallback needs review."]

    return {
        "company_name": clean_snippet(company_name)[:120],
        "source_company": source_company,
        "source_role": source_role,
        "account_identity_status": status,
        "end_customer_candidates": end_customer_candidates,
        "identity_evidence_excerpt": clean_snippet(extracted or title_candidate or title or source_company)[:300],
        "identity_confidence": confidence,
        "identity_notes": notes,
        "identity_resolution_required": required,
    }


def infer_company_name(title: str, url: str, text: str = "") -> str:
    return resolve_account_identity(title, url, text)["company_name"]


def legacy_infer_company_name(title: str, url: str, text: str = "") -> str:
    clean = clean_snippet(re.split(r"\s[-|]\s", title or "")[0])
    generic_titles = (
        "news",
        "22 dynamics",
        "dynamics 365 business central jobs",
        "microsoft dynamics 365",
        "microsoft dynamics erp",
        "dynamics 365 case studies",
    )
    if clean and len(clean) >= 2 and clean.lower() not in {"uk", "ireland"} and not clean.lower().startswith(("uk ", "ireland ")) and not any(clean.lower().startswith(term) for term in generic_titles):
        return clean[:120]
    extracted = extract_named_target_company(text)
    if extracted:
        return extracted[:120]
    host = urllib.parse.urlparse(url).netloc.removeprefix("www.")
    return host.split(".")[0].replace("-", " ").title()


def source_company_from_url(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.removeprefix("www.")
    if not host:
        return ""
    label = host.split(".")[0].replace("-", " ").strip()
    return clean_snippet(label).title()


def infer_company_name_from_host(url: str) -> str:
    return source_company_from_url(url) or "Unknown Account"


def infer_source_role(text: str, url: str) -> str:
    lower = f"{text} {url}".lower()
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(term in lower for term in TENDER_DOMAINS + TENDER_TERMS):
        return "procurement"
    if "linkedin.com" in host or any(term in lower for term in AGENCY_TERMS):
        return "job_board"
    if "microsoft.com" in host:
        return "microsoft"
    if any(term in lower for term in VENDOR_TERMS) or any(term in lower for term in ("partner", "case stud", "client success", "customer story")):
        return "partner"
    return "customer"


def generic_company_title(title: str) -> bool:
    clean = clean_snippet(re.split(r"\s[-|]\s", title or "")[0]).lower()
    if not clean:
        return True
    generic_terms = (
        "case study",
        "case studies",
        "customer story",
        "success stories",
        "client success",
        "microsoft dynamics 365",
        "dynamics 365",
        "business central",
        "d365",
        "power platform",
        "services",
        "support services",
        "jobs",
        "careers",
        "vacancy",
        "news",
        "blog",
    )
    return clean in generic_terms or any(clean.startswith(term) for term in generic_terms)


def extract_company_from_case_title(title: str) -> str | None:
    clean = clean_snippet(re.split(r"\s[-|]\s", title or "")[0])
    if not clean or generic_company_title(clean):
        return None
    stripped = re.split(
        r"\b(?:Dynamics 365|D365|Business Central|Power Platform|Dataverse|case study|customer story|client story|portal|implementation|upgrade|migration|rollout|support)\b",
        clean,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" -:|")
    candidate = stripped or clean
    candidate = re.sub(r"^(UK|Ireland)\s+", "", candidate, flags=re.I).strip()
    if len(candidate) < 2 or candidate.lower() in {"uk", "ireland", "microsoft", "dynamics"}:
        return None
    return candidate


def extract_named_target_company(text: str) -> str | None:
    patterns = (
        r"\b(?:customer|client|organisation|organization|account)\s*(?:is|was|:|-)\s*([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,5})\b",
        r"\b(?:case study|success story|customer story)\s*(?:for|:|-)\s*([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,5})\b",
        r"\b(?:worked with|helped|delivered for|implemented for|deployed for|rolled out for)\s+([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,5})\b",
        r"\b(?:helped|delivered|implemented|deployed|rolled out)\s+(?:a\s+)?(?:Microsoft\s+)?(?:Dynamics 365|D365|Business Central|Power Platform|Dataverse)[^.\n]{0,100}\s+(?:for|with)\s+([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,5})\b",
        r"\b([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,4}\s+(?:Limited|Ltd|plc|PLC|Group|NI))\b",
        r"\b([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,5})\s+(?:has completed|implemented|uses|were facing|is implementing|migrating to|upgraded to|selected|onboarded|rolled out|replaced|moved to|worked with|partnered with)",
        r"\b(?:customer|client):\s*([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,4})\b",
    )
    for pattern in patterns:
        flags = re.I if pattern.startswith(r"\b(?:customer") else 0
        match = re.search(pattern, text, flags)
        if match:
            candidate = clean_snippet(match.group(1).strip(" -:|"))
            candidate = re.sub(r"^(UK|Ireland)\s+", "", candidate).strip()
            words = candidate.split()
            if len(words) >= 2 and len(words) % 2 == 0 and words[: len(words) // 2] == words[len(words) // 2 :]:
                candidate = " ".join(words[: len(words) // 2])
            if "/" not in candidate and candidate.lower() not in {"microsoft dynamics", "dynamics", "dynamics 365", "business central", "power platform", "dataverse", "case study", "success stories", "customer story", "microsoft partner"}:
                return candidate
    return None


def summarize_signal(text: str) -> str:
    return clean_snippet(text)[:280]


def clean_snippet(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(str(text or ""))).strip()


def _provider_candidates() -> list[SearchProvider]:
    return [
        ADKGoogleGroundingProvider(),
        TavilySearchProvider(),
        ExaSearchProvider(),
        SerperSearchProvider(),
        SerpApiSearchProvider(),
        FirecrawlSearchProvider(),
        GoogleCustomSearchProvider(),
    ]


def fanout_base_providers() -> list[SearchProvider]:
    providers_by_name = {provider.name: provider for provider in _provider_candidates()}
    return [
        providers_by_name[name]
        for name in FANOUT_PROVIDER_ORDER
        if name in providers_by_name
    ]


def configured_fanout_providers(*, max_providers: int = FANOUT_DEFAULT_MAX_PROVIDERS) -> list[SearchProvider]:
    configured = [
        provider
        for provider in fanout_base_providers()
        if bool(provider.configured)
    ]
    return configured[: max(1, min(int(max_providers or FANOUT_DEFAULT_MAX_PROVIDERS), len(FANOUT_PROVIDER_ORDER)))]


def _adk_google_search_discovery() -> dict[str, Any]:
    try:
        from google.adk.tools import google_search  # noqa: F401
        from google.adk.tools.agent_tool import AgentTool  # noqa: F401
    except Exception as exc:
        return {
            "available": False,
            "provider": "none",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    return {
        "available": True,
        "provider": "google_grounding",
        "error_type": None,
        "error": None,
    }


async def _run_adk_search_agent(prompt: str) -> str:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from uk_ie_d365_leads.agents.search_agent import d365_search_agent

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="uk_ie_d365_leads_search",
        user_id="uk_ie_d365_leads",
        session_id=f"search-{abs(hash(prompt))}",
    )
    runner = Runner(
        app_name="uk_ie_d365_leads_search",
        agent=d365_search_agent,
        session_service=session_service,
    )
    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    texts: list[str] = []
    async for event in runner.run_async(
        user_id="uk_ie_d365_leads",
        session_id=session.id,
        new_message=message,
    ):
        content = getattr(event, "content", None)
        if not content or not content.parts:
            continue
        for part in content.parts:
            text = getattr(part, "text", None)
            if text:
                texts.append(text)
    return "\n".join(texts)


def _run_google_genai_grounded_search_results(query: str, limit: int = 5, source: str = "google_grounding") -> list[SearchResult]:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        client = genai.Client(api_key=api_key)
    else:
        readiness = google_native_readiness()
        project = readiness.get("effective_project")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
        client = genai.Client(vertexai=True, project=project, location=location)
    prompt = (
        "Search the public web for the query below. Return JSON only: "
        "[{\"title\":\"...\",\"url\":\"https://...\",\"snippet\":\"...\"}]. "
        f"Return at most {max(1, min(int(limit or 5), 10))} results. "
        "Only include public web evidence for UK/Ireland Microsoft Dynamics 365 lead intelligence. "
        "Do not invent companies, URLs, or snippets.\n\n"
        f"Query: {query}"
    )
    response = client.models.generate_content(
        model=effective_google_model()[0],
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(googleSearch=types.GoogleSearch())],
            temperature=0,
            maxOutputTokens=2048,
        ),
    )
    text_results = parse_search_results(getattr(response, "text", "") or "", source=source, limit=limit)
    metadata_results = _grounding_metadata_results(response, source=source, limit=limit)
    merged: list[SearchResult] = []
    seen: set[str] = set()
    for result in text_results + metadata_results:
        normalized = normalize_public_url(result.url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(
            SearchResult(
                title=result.title,
                url=normalized,
                snippet=result.snippet,
                source=result.source,
                published_date=result.published_date,
                signal_class=result.signal_class,
                source_url_type=source_url_type(normalized),
            )
        )
        if len(merged) >= limit:
            break
    return merged


def _grounding_metadata_results(response: Any, *, source: str, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        metadata = (
            getattr(candidate, "grounding_metadata", None)
            or getattr(candidate, "groundingMetadata", None)
        )
        chunks = (
            getattr(metadata, "grounding_chunks", None)
            or getattr(metadata, "groundingChunks", None)
            or []
        )
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if web is None and isinstance(chunk, dict):
                web = chunk.get("web")
            title = _attr_or_key(web, "title") or ""
            uri = _attr_or_key(web, "uri") or _attr_or_key(web, "url") or ""
            normalized = normalize_public_url(uri)
            if not normalized:
                continue
            results.append(
                SearchResult(
                    title=str(title),
                    url=normalized,
                    snippet=str(title),
                    source=source,
                    source_url_type=source_url_type(normalized),
                )
            )
            if len(results) >= limit:
                return results
    return results


def _attr_or_key(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _run_coro_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("ADK search provider cannot run inside an active event loop.")


def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    response = requests.request(
        method,
        url,
        headers=headers,
        json=json_body,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _organic_results(rows: list[dict[str, Any]], source: str, limit: int) -> list[SearchResult]:
    return [
        SearchResult(
            title=item.get("title") or "",
            url=item.get("link") or item.get("url") or "",
            snippet=item.get("snippet") or item.get("description") or "",
            source=source,
            published_date=item.get("date"),
        )
        for item in rows[:limit]
        if item.get("link") or item.get("url")
    ]


def _extract_json(text: str) -> Any:
    clean = (text or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?", "", clean, flags=re.I).strip()
        clean = re.sub(r"```$", "", clean).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", clean)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _safe_error(exc: BaseException) -> str:
    text = str(exc)
    text = re.sub(r"(api[_-]?key=)[^&\s]+", r"\1REDACTED", text, flags=re.I)
    text = re.sub(r"(Authorization:\s*Bearer\s+)[A-Za-z0-9._-]+", r"\1REDACTED", text, flags=re.I)
    return text[:300]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        clean = data.strip()
        if clean:
            self.parts.append(clean)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html or "")
    return clean_snippet(" ".join(parser.parts))
