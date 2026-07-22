"""Live public-web search provider for the Contact Resolver Agent."""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol

from business_intel.public_http import fetch_public_http
from uk_ie_d365_leads.tools.lead_tools import gcloud_account_credentials

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_ADK_ENV_PATH = PROJECT_ROOT / "sl_trigger_leads" / ".env"


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = "adk_google_search"


@dataclass(frozen=True)
class PageFetchResult:
    url: str
    status_code: int | None
    text: str
    error: str | None = None


@dataclass(frozen=True)
class ContactRoute:
    route_type: str
    name: str | None
    role: str | None
    email: str | None
    url: str | None
    confidence: int
    confidence_label: str
    evidence_urls: list[str]
    why: str
    source: str


HUNTER_FOUND = "HUNTER_FOUND"
HUNTER_VERIFIED = "HUNTER_VERIFIED"
HUNTER_NOT_FOUND = "HUNTER_NOT_FOUND"
HUNTER_NOT_CONFIGURED = "HUNTER_NOT_CONFIGURED"


@dataclass(frozen=True)
class HunterEmailRecord:
    email: str
    full_name: str | None
    first_name: str | None
    last_name: str | None
    position: str | None
    department: str | None
    email_kind: str | None
    confidence: int | None
    verification_status: str | None
    hunter_status: str
    domain: str | None
    source_urls: list[str]
    linkedin_url: str | None = None


@dataclass(frozen=True)
class HunterLookupResult:
    status: str
    domain: str | None
    emails: list[HunterEmailRecord]
    source: str = "hunter"
    error: str | None = None
    endpoint: str | None = None


class LiveSearchProvider(Protocol):
    name: str
    configured: bool
    unavailable_reason: str | None

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Search public web."""


def load_local_adk_env() -> None:
    """Load non-secret local ADK env settings and normalize Vertex flag."""
    if LOCAL_ADK_ENV_PATH.is_file():
        for raw_line in LOCAL_ADK_ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip().lstrip("\ufeff")
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE":
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"


def adk_google_search_discovery() -> dict[str, Any]:
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
        "provider": "adk_google_search",
        "error_type": None,
        "error": None,
    }


class ADKGoogleSearchProvider:
    name = "adk_google_search"
    configured = True
    unavailable_reason: str | None = None

    def __init__(self) -> None:
        self.discovery = adk_google_search_discovery()
        self.configured = bool(self.discovery["available"])
        self.unavailable_reason = None if self.configured else self.discovery["error"]

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            raise RuntimeError(self.unavailable_reason or "ADK google_search unavailable")
        load_local_adk_env()
        prompt = (
            "Use Google Search for this public web query and return JSON only. "
            f"Query: {query!r}. "
            f"Return up to {limit} objects with title, url, snippet. "
            "Prefer official company, contact, careers, leadership, team, public LinkedIn, "
            "press, speaker, and news pages. Do not invent URLs."
        )
        text = _run_coro_sync(_run_contact_search_agent(prompt))
        return parse_search_results(text, limit=limit, source=self.name)


class ProviderUnavailable:
    name = "none"
    configured = False

    def __init__(self, reason: str) -> None:
        self.unavailable_reason = reason

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        return []


class HunterContactEnrichmentProvider:
    """Small Hunter API adapter used by the Contact Resolver when configured."""

    name = "hunter"
    base_url = "https://api.hunter.io/v2"

    def __init__(self, api_key: str | None = None, timeout_seconds: int = 20) -> None:
        raw_key = api_key if api_key is not None else os.environ.get("HUNTER_API_KEY")
        self.api_key = str(raw_key or "").strip()
        self.timeout_seconds = timeout_seconds
        self.configured = bool(self.api_key)
        self.unavailable_reason = None if self.configured else "HUNTER_API_KEY is not set."

    @classmethod
    def from_env(cls) -> HunterContactEnrichmentProvider:
        return cls()

    def domain_search(self, domain: str, *, limit: int = 10) -> HunterLookupResult:
        clean_domain = normalize_company_domain(domain)
        if not self.configured:
            return HunterLookupResult(
                status=HUNTER_NOT_CONFIGURED,
                domain=clean_domain,
                emails=[],
                endpoint="domain-search",
            )
        if not clean_domain:
            return HunterLookupResult(
                status=HUNTER_NOT_FOUND,
                domain=None,
                emails=[],
                endpoint="domain-search",
                error="valid_company_domain_required",
            )
        try:
            payload = self._request_json(
                "domain-search",
                {"domain": clean_domain, "limit": max(1, min(int(limit or 10), 10))},
            )
        except Exception as exc:
            return HunterLookupResult(
                status=HUNTER_NOT_FOUND,
                domain=clean_domain,
                emails=[],
                endpoint="domain-search",
                error=_safe_hunter_error_message(exc),
            )
        emails = [
            record
            for item in (payload.get("data") or {}).get("emails", [])
            if isinstance(item, dict)
            for record in [_hunter_email_record_from_payload(item, default_domain=clean_domain)]
            if record
        ]
        return HunterLookupResult(
            status=_hunter_result_status(emails),
            domain=clean_domain,
            emails=emails,
            endpoint="domain-search",
        )

    def email_finder(
        self,
        *,
        domain: str,
        full_name: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        max_duration: int = 3,
    ) -> HunterLookupResult:
        clean_domain = normalize_company_domain(domain)
        split_first, split_last = split_person_name(full_name or "")
        first = (first_name or split_first or "").strip()
        last = (last_name or split_last or "").strip()
        if not self.configured:
            return HunterLookupResult(
                status=HUNTER_NOT_CONFIGURED,
                domain=clean_domain,
                emails=[],
                endpoint="email-finder",
            )
        if not clean_domain or not first or not last:
            return HunterLookupResult(
                status=HUNTER_NOT_FOUND,
                domain=clean_domain,
                emails=[],
                endpoint="email-finder",
                error="real_named_person_and_domain_required",
            )
        try:
            payload = self._request_json(
                "email-finder",
                {
                    "domain": clean_domain,
                    "first_name": first,
                    "last_name": last,
                    "max_duration": max(3, min(int(max_duration or 3), 20)),
                },
            )
        except Exception as exc:
            return HunterLookupResult(
                status=HUNTER_NOT_FOUND,
                domain=clean_domain,
                emails=[],
                endpoint="email-finder",
                error=_safe_hunter_error_message(exc),
            )
        data = payload.get("data") or {}
        record = _hunter_email_record_from_payload(data, default_domain=clean_domain)
        emails = [record] if record else []
        return HunterLookupResult(
            status=_hunter_result_status(emails),
            domain=clean_domain,
            emails=emails,
            endpoint="email-finder",
        )

    def _request_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        safe_endpoint = endpoint.strip("/")
        request_params = {**params, "api_key": self.api_key}
        url = f"{self.base_url}/{safe_endpoint}?{urllib.parse.urlencode(request_params)}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 Business_Intel_ContactResolver/1.0 "
                    "(Hunter contact enrichment)"
                )
            },
        )
        try:
            response = fetch_public_http(
                request,
                timeout_seconds=self.timeout_seconds,
                max_body_bytes=1_000_000,
            )
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.body.decode(charset, errors="replace"))
        except urllib.error.HTTPError as exc:
            try:
                raise RuntimeError(f"Hunter API HTTP {exc.code}") from exc
            finally:
                exc.close()


class GoogleCSESearchProvider:
    name = "google_cse"

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
        params = urllib.parse.urlencode(
            {
                "key": self.api_key,
                "cx": self.cx,
                "q": query,
                "num": max(1, min(limit, 10)),
            }
        )
        url = f"https://www.googleapis.com/customsearch/v1?{params}"
        payload = json.loads(_http_get_text(url, timeout=20).text)
        results = []
        for item in payload.get("items", [])[:limit]:
            results.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=item.get("link") or "",
                    snippet=item.get("snippet") or "",
                    source=self.name,
                )
            )
        return [result for result in results if result.url]


class SerpAPISearchProvider:
    name = "serpapi"

    def __init__(self) -> None:
        self.api_key = os.environ.get("SERPAPI_API_KEY")
        self.configured = bool(self.api_key)
        self.unavailable_reason = None if self.configured else "Configure SERPAPI_API_KEY."

    def search_web(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            return []
        params = urllib.parse.urlencode(
            {
                "api_key": self.api_key,
                "engine": "google",
                "q": query,
                "num": max(1, min(limit, 10)),
            }
        )
        url = f"https://serpapi.com/search.json?{params}"
        payload = json.loads(_http_get_text(url, timeout=20).text)
        results = []
        for item in payload.get("organic_results", [])[:limit]:
            results.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=item.get("link") or "",
                    snippet=item.get("snippet") or "",
                    source=self.name,
                )
            )
        return [result for result in results if result.url]


class RequestsPageFetcher:
    def __init__(self, timeout_seconds: int = 15, max_chars: int = 250_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_chars = max_chars

    def fetch_page(self, url: str) -> PageFetchResult:
        normalized_url = normalize_public_url(url)
        if not normalized_url:
            return PageFetchResult(
                url=url,
                status_code=None,
                text="",
                error=f"rejected_malformed_url: {url}",
            )
        fetched = _http_get_text(normalized_url, timeout=self.timeout_seconds)
        text = html_to_text(fetched.text[: self.max_chars])
        return PageFetchResult(
            url=fetched.url,
            status_code=fetched.status_code,
            text=text[: self.max_chars],
            error=fetched.error,
        )


class EmailExtractor:
    EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)

    def extract(self, text: str) -> list[str]:
        emails: list[str] = []
        for match in self.EMAIL_RE.findall(text or ""):
            email = match.strip(".,;:()[]<>").lower()
            if email and email not in emails:
                emails.append(email)
        return emails


class PeopleRoleExtractor:
    def extract(self, text: str, company: str, target_personas: list[str]) -> list[dict[str, Any]]:
        people: list[dict[str, Any]] = []
        for line in (text or "").splitlines():
            clean = re.sub(r"\s+", " ", line).strip()
            if not clean:
                continue
            role = next(
                (persona for persona in target_personas if persona.lower() in clean.lower()),
                None,
            )
            if not role:
                continue
            if re.search(rf"\bformer\s+{re.escape(role)}\b", clean, flags=re.I):
                continue
            name = _extract_name_near_role(clean, role)
            if not name or _is_company_like_name(name, company):
                continue
            people.append(
                {
                    "name": name,
                    "role": role,
                    "company": company,
                    "evidence_summary": clean[:240],
                }
            )
        return people


class ContactRouteResolver:
    def best(self, routes: list[ContactRoute]) -> ContactRoute:
        if not routes:
            return ContactRoute(
                route_type="no_contact_found",
                name=None,
                role=None,
                email=None,
                url=None,
                confidence=0,
                confidence_label="None",
                evidence_urls=[],
                why="No public route found after live attempts.",
                source="none",
            )
        return sorted(routes, key=lambda route: route.confidence, reverse=True)[0]


def get_default_live_search_provider() -> LiveSearchProvider:
    load_local_adk_env()
    adk_provider = ADKGoogleSearchProvider()
    if adk_provider.configured:
        return adk_provider
    cse_provider = GoogleCSESearchProvider()
    if cse_provider.configured:
        return cse_provider
    serp_provider = SerpAPISearchProvider()
    if serp_provider.configured:
        return serp_provider
    reason = (
        "ADK google_search unavailable in this install. Configure GOOGLE_CSE_API_KEY "
        "and GOOGLE_CSE_CX or approve another provider."
    )
    if adk_provider.unavailable_reason:
        reason = f"{reason} ADK error: {adk_provider.unavailable_reason}"
    return ProviderUnavailable(reason)


def normalize_company_domain(value: Any) -> str | None:
    """Normalize a company domain for enrichment APIs without guessing one."""
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if "@" in raw and "://" not in raw:
        raw = raw.rsplit("@", 1)[1]
    if "://" in raw or raw.startswith("www.") or "/" in raw:
        normalized_url = normalize_public_url(raw)
        if not normalized_url:
            return None
        host = urllib.parse.urlparse(normalized_url).netloc
    else:
        host = raw.split("/", 1)[0]
    host = host.split("@")[-1].split(":", 1)[0].strip(".").removeprefix("www.")
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", host):
        return None
    if any(token in host for token in ("..", "localhost")):
        return None
    return host


def split_person_name(full_name: str) -> tuple[str | None, str | None]:
    parts = [
        part.strip(" .'\"")
        for part in re.split(r"\s+", str(full_name or "").strip())
        if part.strip(" .'\"")
    ]
    if len(parts) < 2:
        return None, None
    return parts[0], parts[-1]


def hunter_status_from_verification(
    verification_status: str | None,
    *,
    has_email: bool,
) -> str:
    if not has_email:
        return HUNTER_NOT_FOUND
    normalized = str(verification_status or "").strip().lower()
    if normalized == "valid":
        return HUNTER_VERIFIED
    if normalized == "invalid":
        return HUNTER_NOT_FOUND
    return HUNTER_FOUND


def hunter_source_urls(sources: Any) -> list[str]:
    urls: list[str] = []
    if not isinstance(sources, list):
        return urls
    for item in sources:
        if not isinstance(item, dict):
            continue
        url = normalize_public_url(item.get("uri") or item.get("url"))
        if url and url not in urls:
            urls.append(url)
    return urls


def _hunter_email_record_from_payload(
    item: dict[str, Any],
    *,
    default_domain: str | None,
) -> HunterEmailRecord | None:
    email = str(item.get("value") or item.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return None
    first_name = _clean_optional_str(item.get("first_name"))
    last_name = _clean_optional_str(item.get("last_name"))
    full_name = " ".join(part for part in (first_name, last_name) if part) or None
    verification = item.get("verification") if isinstance(item.get("verification"), dict) else {}
    verification_status = _clean_optional_str(verification.get("status"))
    confidence = item.get("confidence", item.get("score"))
    try:
        confidence_int = int(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_int = None
    status = hunter_status_from_verification(verification_status, has_email=True)
    return HunterEmailRecord(
        email=email,
        full_name=full_name,
        first_name=first_name,
        last_name=last_name,
        position=_clean_optional_str(item.get("position") or item.get("position_raw")),
        department=_clean_optional_str(item.get("department")),
        email_kind=_clean_optional_str(item.get("type")),
        confidence=confidence_int,
        verification_status=verification_status,
        hunter_status=status,
        domain=normalize_company_domain(item.get("domain") or default_domain or email),
        source_urls=hunter_source_urls(item.get("sources")),
        linkedin_url=normalize_public_url(item.get("linkedin") or item.get("linkedin_url")),
    )


def _hunter_result_status(emails: list[HunterEmailRecord]) -> str:
    if not emails:
        return HUNTER_NOT_FOUND
    if any(record.hunter_status == HUNTER_VERIFIED for record in emails):
        return HUNTER_VERIFIED
    return HUNTER_FOUND


def _clean_optional_str(value: Any) -> str | None:
    clean = str(value or "").strip()
    return clean or None


def _safe_hunter_error_message(exc: BaseException) -> str:
    message = str(exc)
    message = re.sub(r"api_key=[^&\s]+", "api_key=REDACTED", message, flags=re.I)
    message = re.sub(r"key=[^&\s]+", "key=REDACTED", message, flags=re.I)
    return message[:240]


def search_result_to_dict(result: SearchResult) -> dict[str, Any]:
    return asdict(result)


def page_fetch_to_dict(result: PageFetchResult) -> dict[str, Any]:
    return asdict(result)


def contact_search_model() -> Any:
    """Build the ADK search model with optional refreshable command-scoped auth."""
    from google.adk.models.google_llm import Gemini

    credentials = gcloud_account_credentials()
    client_kwargs: dict[str, Any] | None = None
    if credentials:
        project = os.environ.get("D365_GOOGLE_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            raise RuntimeError("Google project is unclear for command-scoped Contact Resolver credentials.")
        client_kwargs = {
            "vertexai": True,
            "project": project,
            "location": os.environ.get("GOOGLE_CLOUD_LOCATION") or "global",
            "credentials": credentials,
        }
    return Gemini(model="gemini-2.5-flash", client_kwargs=client_kwargs)


async def _run_contact_search_agent(prompt: str) -> str:
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools import google_search
    from google.genai import types

    load_local_adk_env()
    model = await asyncio.to_thread(contact_search_model)
    contact_search_agent = Agent(
        model=model,
        name="contact_search_agent_runtime",
        instruction=(
            "You are a search-only public web specialist. Use only Google Search. "
            "Return JSON only: [{\"title\":\"...\",\"url\":\"https://...\",\"snippet\":\"...\"}]. "
            "Do not invent URLs, people, roles, or emails."
        ),
        tools=[google_search],
    )

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="contact_search_agent",
        user_id="contact_resolver",
        session_id=f"search-{abs(hash(prompt))}",
    )
    runner = Runner(
        app_name="contact_search_agent",
        agent=contact_search_agent,
        session_service=session_service,
    )
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt)],
    )
    texts: list[str] = []
    async for event in runner.run_async(
        user_id="contact_resolver",
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


def _run_coro_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover - defensive thread bridge
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def parse_search_results(text: str, *, limit: int, source: str) -> list[SearchResult]:
    cleaned = _strip_json_fence(text or "")
    parsed: Any = None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = None

    results: list[SearchResult] = []
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                _append_result(results, item, source)
    elif isinstance(parsed, dict):
        if isinstance(parsed.get("results"), list):
            for item in parsed["results"]:
                if isinstance(item, dict):
                    _append_result(results, item, source)
        else:
            for key, value in parsed.items():
                if isinstance(value, str):
                    normalized_url = normalize_public_url(value)
                    if normalized_url:
                        results.append(
                            SearchResult(
                                title=str(key),
                                url=normalized_url,
                                snippet="",
                                source=source,
                            )
                        )

    for url in re.findall(r"(?:https?://|www\.)[^\s\"'<>),]+", text or ""):
        normalized_url = normalize_public_url(url)
        if normalized_url and not any(result.url == normalized_url for result in results):
            results.append(SearchResult(title="", url=normalized_url, snippet="", source=source))

    deduped: list[SearchResult] = []
    seen: set[str] = set()
    for result in results:
        if not result.url or result.url in seen:
            continue
        seen.add(result.url)
        deduped.append(result)
        if len(deduped) >= limit:
            break
    return deduped


def _append_result(results: list[SearchResult], item: dict[str, Any], source: str) -> None:
    url = normalize_public_url(item.get("url") or item.get("link"))
    if not url:
        return
    results.append(
        SearchResult(
            title=str(item.get("title") or ""),
            url=url,
            snippet=str(item.get("snippet") or item.get("summary") or ""),
            source=source,
        )
    )


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


@dataclass(frozen=True)
class _HTTPText:
    url: str
    status_code: int | None
    text: str
    error: str | None = None


def _http_get_text(url: str, *, timeout: int) -> _HTTPText:
    normalized_url = normalize_public_url(url)
    if not normalized_url:
        return _HTTPText(
            url=url,
            status_code=None,
            text="",
            error=f"rejected_malformed_url: {url}",
        )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 Business_Intel_ContactResolver/1.0 "
            "(public web contact route verification)"
        )
    }
    request = urllib.request.Request(normalized_url, headers=headers)
    try:
        response = fetch_public_http(
            request,
            timeout_seconds=timeout,
            max_body_bytes=1_000_000,
        )
        charset = response.headers.get_content_charset() or "utf-8"
        return _HTTPText(
            url=response.url,
            status_code=response.status_code,
            text=response.body.decode(charset, errors="replace"),
            error=None,
        )
    except urllib.error.HTTPError as exc:
        try:
            return _HTTPText(url=normalized_url, status_code=exc.code, text="", error=str(exc))
        finally:
            exc.close()
    except Exception as exc:
        return _HTTPText(
            url=normalized_url,
            status_code=None,
            text="",
            error=f"{type(exc).__name__}: {exc}",
        )


def normalize_public_url(url: Any) -> str | None:
    """Normalize public URLs and reject malformed values safely."""
    value = str(url or "").strip().strip(".,;:()[]<>\"'")
    if not value:
        return None
    if value.startswith("//"):
        value = "https:" + value
    if not re.match(r"^https?://", value, flags=re.I):
        if value.startswith("www.") or re.match(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/.*)?$", value):
            value = "https://" + value
        else:
            return None
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or "." not in parsed.netloc:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    try:
        host = parsed.netloc.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    if not host:
        return None
    path = parsed.path or ""
    return urllib.parse.urlunparse(
        (
            parsed.scheme.lower(),
            host,
            path,
            "",
            parsed.query,
            "",
        )
    )


class _HTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True
        if tag in {"p", "div", "section", "article", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False
        if tag in {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _HTMLTextParser()
    try:
        parser.feed(html)
        text = " ".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_name_near_role(line: str, role: str) -> str | None:
    name_pattern = r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})"
    role_pattern = re.escape(role)
    for pattern in (
        rf"{name_pattern}\s*[-|,]\s*{role_pattern}",
        rf"{role_pattern}\s*[:|-]\s*{name_pattern}",
        rf"{name_pattern}.{{0,80}}{role_pattern}",
    ):
        match = re.search(pattern, line)
        if match:
            groups = [group for group in match.groups() if group and group != role]
            if groups:
                name = re.sub(
                    r"^(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+",
                    "",
                    groups[-1].strip(),
                    flags=re.I,
                )
                return name if _is_plausible_person_name(name) else None
    return None


PERSON_NAME_STOPWORDS = {
    "architect",
    "article",
    "blog",
    "business",
    "career",
    "careers",
    "contact",
    "customer",
    "cto",
    "cio",
    "ceo",
    "developer",
    "director",
    "engineer",
    "manager",
    "lead",
    "head",
    "engineering",
    "quality",
    "solutions",
    "solution",
    "software",
    "enterprise",
    "five",
    "former",
    "founder",
    "leaders",
    "leadership",
    "management",
    "executive",
    "news",
    "practical",
    "report",
    "company",
    "team",
    "ways",
}


def _is_plausible_person_name(name: str | None) -> bool:
    clean = re.sub(r"[^A-Za-z.' -]", " ", str(name or "")).strip(" .'-")
    parts = [part.strip(" .'") for part in clean.split() if part.strip(" .'")]
    if len(parts) < 2 or len(parts) > 4:
        return False
    if sum(1 for part in parts if part.isupper()) >= 2:
        return False
    lowered = {part.lower() for part in parts}
    if lowered & PERSON_NAME_STOPWORDS:
        return False
    return all(part[:1].isupper() and re.match(r"^[A-Za-z.'-]+$", part) for part in parts)


def _is_company_like_name(name: str, company: str) -> bool:
    name_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", name.lower())
        if token not in {"pvt", "ltd", "limited", "private"}
    }
    company_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", company.lower())
        if token not in {"pvt", "ltd", "limited", "private"}
    }
    return bool(name_tokens and name_tokens.issubset(company_tokens))
