from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from frontend.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    reset_session_registry,
    revoke_session,
    verify_session_token,
)
from frontend.config import settings
from frontend.storage import JsonStore
from sl_trigger_leads.tools.signal_tools import assert_no_simulation_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
LEGACY_DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_STATE: dict[str, Any] = {
    "last_fetch": None,
    "total_leads_found": 0,
    "sources_enabled": 4,
    "sources_ok": 0,
    "sources_failed": 0,
    "leads_contact_now": 0,
    "leads_verify_first": 0,
    "leads_watch_list": 0,
    "leads_parked": 0,
    "notes": "",
}


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictRequest):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class NotesUpdateRequest(StrictRequest):
    notes: str = Field(max_length=5000)


class AgentQuery(StrictRequest):
    query: str = Field(min_length=1, max_length=5000)


class OkResponse(BaseModel):
    ok: bool = True
    message: str | None = None


class LoginResponse(BaseModel):
    ok: bool = True
    user: str
    role: str = "viewer"
    expires_in_minutes: int
    csrf_token: str


class VerifyResponse(BaseModel):
    ok: bool = True
    user: str
    role: str = "viewer"
    csrf_token: str


class ScoreBreakdown(StrictRequest):
    recent_public_trigger: int = Field(strict=True, ge=0, le=25)
    one_bt_service_fit: int = Field(
        strict=True,
        ge=0,
        le=25,
        alias="1bt_service_fit",
    )
    local_reachability: int = Field(strict=True, ge=0, le=20)
    named_person_found: int = Field(strict=True, ge=0, le=15)
    evidence_quality: int = Field(strict=True, ge=0, le=10)
    deal_size_likelihood: int = Field(strict=True, ge=0, le=5)


class LeadScore(StrictRequest):
    total: int = Field(strict=True, ge=0, le=100)
    breakdown: ScoreBreakdown
    verdict: Literal["Contact now", "Verify contact first", "Watch list", "Park"]
    scoring_notes: list[str] = Field(default_factory=list)


class LeadRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    company: str
    evidence_url: str
    evidence_excerpt: str
    source_name: str
    fetched_at: str
    verified_live: bool = Field(strict=True)
    score: LeadScore


class LeadsResponse(BaseModel):
    ok: bool = True
    count: int
    leads: list[LeadRecord]


class LeadsStatsResponse(BaseModel):
    ok: bool = True
    total: int
    avg_score: float
    verdicts: dict[str, int]
    sectors: dict[str, int]
    trigger_types: dict[str, int]


class RefreshResponse(BaseModel):
    ok: bool = True
    count: int
    source: str = "live_fetch"
    coverage: dict[str, Any]


class SourcesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool = True
    source_count: int = 0
    sources: list[dict[str, Any]] = Field(default_factory=list)
    note: str | None = None


class StateResponse(BaseModel):
    ok: bool = True
    last_fetch: str | None = None
    total_leads_found: int = 0
    sources_enabled: int = 4
    sources_ok: int = 0
    sources_failed: int = 0
    leads_contact_now: int = 0
    leads_verify_first: int = 0
    leads_watch_list: int = 0
    leads_parked: int = 0
    notes: str = ""


class ClassificationResponse(BaseModel):
    ok: bool = True
    trigger_type: str
    confidence: float
    reason: str


class FitPreviewResponse(BaseModel):
    ok: bool = True
    classification: dict[str, Any]
    service_fit: list[str]
    verified_lead: bool = False
    explanation: str


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def ensure_allowed(self, key: str, max_events: int, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] >= window_seconds:
                events.popleft()
            if len(events) >= max_events:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Try again later.",
                    headers={"Retry-After": str(window_seconds)},
                )
            events.append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)


class CooldownLimiter:
    def __init__(self) -> None:
        self._last_run: dict[str, float] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str, minimum_interval: int) -> None:
        now = time.monotonic()
        with self._lock:
            previous = self._last_run.get(key)
            if previous is not None and now - previous < minimum_interval:
                retry_after = max(1, int(minimum_interval - (now - previous)))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Refresh is rate limited. Try again shortly.",
                    headers={"Retry-After": str(retry_after)},
                )
            self._last_run[key] = now

    def reset(self) -> None:
        with self._lock:
            self._last_run.clear()


login_limiter = SlidingWindowLimiter()
refresh_limiter = CooldownLimiter()
_store: JsonStore | None = None


class RequestBodyTooLarge(Exception):
    """Raised when an HTTP body exceeds the local API limit."""


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={"detail": "Request body is too large"},
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw_content_length = headers.get(b"content-length")
        if raw_content_length:
            try:
                if int(raw_content_length) > self.max_body_size:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_size:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await self._reject(scope, receive, send)


def runtime_store() -> JsonStore:
    global _store
    configured_root = Path(settings.data_dir).resolve()
    if _store is None or _store.root != configured_root:
        _store = JsonStore(configured_root)
    return _store


def validate_runtime_leads(leads: Any) -> list[dict[str, Any]]:
    if not isinstance(leads, list):
        raise ValueError("Runtime leads must be a JSON array")
    for index, lead in enumerate(leads):
        if not isinstance(lead, dict):
            raise ValueError(f"Runtime lead {index} must be an object")
    assert_no_simulation_data(leads)
    validated: list[dict[str, Any]] = []
    for index, lead in enumerate(leads):
        missing = [
            field
            for field in ("company", "evidence_url", "evidence_excerpt", "source_name", "fetched_at")
            if not str(lead.get(field, "")).strip()
        ]
        if missing:
            raise ValueError(f"Runtime lead {index} missing required fields: {', '.join(missing)}")
        parsed_url = urlparse(str(lead["evidence_url"]))
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError(f"Runtime lead {index} has a non-HTTP(S) evidence URL")
        if lead.get("verified_live") is not True:
            raise ValueError(f"Runtime lead {index} is not verified live")
        if lead.get("trigger_type") == "tender_or_procurement":
            raise ValueError(f"Runtime lead {index} is tender/procurement-only")
        validated.append(LeadRecord.model_validate(lead).model_dump(by_alias=True))
    return validated


def _snapshot_candidates() -> list[Path]:
    candidates = [ROOT_DIR / "outputs" / "PROMPT#04_live_leads.json"]
    candidates.extend((ROOT_DIR / "sl_trigger_leads" / "data" / "live_runs").glob("*_live_leads.json"))
    return sorted(
        (path for path in candidates if path.exists()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def try_load_adk_output() -> list[dict[str, Any]]:
    """Use the newest valid saved snapshot only for first-run bootstrap."""
    for path in _snapshot_candidates():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            leads = validate_runtime_leads(payload.get("leads", []))
            if leads:
                logger.info("Bootstrapping runtime leads from %s", path)
                return leads
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Skipping invalid bootstrap snapshot %s: %s", path, exc)
    return []


def _migrate_legacy_data() -> None:
    store = runtime_store()
    legacy_leads_path = LEGACY_DATA_DIR / "leads.json"
    if not store.exists("leads.json") and legacy_leads_path.exists():
        try:
            leads = validate_runtime_leads(json.loads(legacy_leads_path.read_text(encoding="utf-8")))
            if leads:
                store.write("leads.json", leads)
                logger.info("Migrated verified leads into %s", store.root)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Legacy leads were not migrated: %s", exc)

    legacy_state_path = LEGACY_DATA_DIR / "app_state.json"
    if not store.exists("app_state.json") and legacy_state_path.exists():
        try:
            state = json.loads(legacy_state_path.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                merged_state = {**DEFAULT_STATE, **state}
                merged_state["notes"] = str(merged_state.get("notes", ""))[:5000]
                store.write("app_state.json", merged_state)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Legacy application state was not migrated: %s", exc)


def get_shared_leads() -> list[dict[str, Any]]:
    store = runtime_store()
    leads = store.read("leads.json", [])
    if leads:
        return validate_runtime_leads(leads)
    bootstrap = try_load_adk_output()
    if bootstrap:
        store.write("leads.json", bootstrap)
    return bootstrap


def _normalize_app_state(state: Any) -> dict[str, Any]:
    current = state if isinstance(state, dict) else {}
    merged = {**DEFAULT_STATE, **current}
    merged["notes"] = str(merged.get("notes", ""))[:5000]
    return merged


def get_app_state() -> dict[str, Any]:
    return _normalize_app_state(runtime_store().read("app_state.json", {}))


def update_app_state(mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    def transform(current: Any) -> dict[str, Any]:
        state = _normalize_app_state(current)
        mutator(state)
        return _normalize_app_state(state)

    return runtime_store().update("app_state.json", {}, transform)


def _run_live_refresh() -> dict[str, Any]:
    from sl_trigger_leads.tools.live_source_tools import find_live_leads

    return find_live_leads(max_results=10, source_limit=4, write_outputs=False)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings.validate_runtime_security()
    reset_session_registry()
    runtime_store().ensure_ready()
    _migrate_legacy_data()
    get_shared_leads()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=False,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=16_384)


@app.middleware("http")
async def security_middleware(request: Request, call_next: Any) -> Response:
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if request.url.path.startswith(("/api/", "/static/")) or request.url.path in {"/", "/app"}:
        response.headers["Cache-Control"] = "no-store"
    return response


async def require_auth(request: Request) -> dict[str, Any]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    payload = verify_session_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")
    return payload


AuthSession = Annotated[dict[str, Any], Depends(require_auth)]


async def require_csrf(request: Request, auth: AuthSession) -> dict[str, Any]:
    supplied = request.headers.get("X-CSRF-Token", "")
    expected = str(auth.get("csrf", ""))
    if not supplied or not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    fetch_site = request.headers.get("Sec-Fetch-Site")
    if fetch_site and fetch_site not in {"same-origin", "same-site", "none"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-site request blocked")
    return auth


CsrfSession = Annotated[dict[str, Any], Depends(require_csrf)]


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.post("/api/auth/login", response_model=LoginResponse)
async def api_login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    client_key = _client_key(request)
    login_limiter.ensure_allowed(
        client_key,
        max_events=settings.login_max_attempts,
        window_seconds=settings.login_window_seconds,
    )
    username_ok = secrets.compare_digest(
        body.username.encode("utf-8"),
        settings.shared_username.encode("utf-8"),
    )
    password_ok = settings.verify_password(body.password)
    if not username_ok or not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    login_limiter.reset(client_key)
    token, csrf_token = create_session_token()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.session_expire_minutes * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )
    return LoginResponse(
        user=settings.shared_username,
        expires_in_minutes=settings.session_expire_minutes,
        csrf_token=csrf_token,
    )


@app.post("/api/auth/logout", response_model=OkResponse)
async def api_logout(auth: CsrfSession, response: Response) -> OkResponse:
    revoke_session(auth)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
    )
    return OkResponse(message="Session cleared")


@app.get("/api/auth/verify", response_model=VerifyResponse)
async def api_verify(auth: AuthSession) -> VerifyResponse:
    return VerifyResponse(
        user=settings.shared_username,
        csrf_token=str(auth["csrf"]),
    )


@app.get("/api/leads", response_model=LeadsResponse)
async def api_get_leads(_auth: AuthSession) -> LeadsResponse:
    leads = get_shared_leads()
    return LeadsResponse(count=len(leads), leads=leads)


@app.get("/api/leads/stats", response_model=LeadsStatsResponse)
async def api_leads_stats(_auth: AuthSession) -> LeadsStatsResponse:
    leads = get_shared_leads()
    verdicts: dict[str, int] = {}
    sectors: dict[str, int] = {}
    trigger_types: dict[str, int] = {}
    total_score = 0
    for lead in leads:
        score = lead.get("score", {})
        verdict = str(score.get("verdict", "Unknown"))
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
        total_score += int(score.get("total", 0) or 0)
        sector = str(lead.get("sector", "Unknown"))
        sectors[sector] = sectors.get(sector, 0) + 1
        trigger_type = str(lead.get("trigger_type", "Unknown"))
        trigger_types[trigger_type] = trigger_types.get(trigger_type, 0) + 1
    total = len(leads)
    return LeadsStatsResponse(
        total=total,
        avg_score=round(total_score / total, 1) if total else 0,
        verdicts=verdicts,
        sectors=sectors,
        trigger_types=trigger_types,
    )


@app.post("/api/leads/refresh", response_model=RefreshResponse)
async def api_refresh_leads(request: Request, auth: CsrfSession) -> RefreshResponse:
    refresh_limiter.acquire(str(auth["sub"]), settings.refresh_min_interval_seconds)
    try:
        result = await run_in_threadpool(_run_live_refresh)
        leads = validate_runtime_leads(result.get("leads", []))
        if not leads:
            raise ValueError("Live refresh returned no verified leads")
    except Exception as exc:
        logger.warning("Live refresh failed; existing leads preserved: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live refresh failed; existing verified leads were preserved.",
        ) from exc

    runtime_store().write("leads.json", leads)
    coverage = result.get("source_coverage_summary", {})
    update_app_state(
        lambda state: state.update(
            {
            "last_fetch": str(result.get("fetched_at", "")),
            "total_leads_found": len(leads),
            "sources_ok": int(coverage.get("sources_succeeded", 0))
            + int(coverage.get("sources_recovered", 0)),
            "sources_failed": int(coverage.get("sources_failed", 0)),
            }
        )
    )
    return RefreshResponse(count=len(leads), coverage=coverage)


@app.get("/api/sources", response_model=SourcesResponse)
async def api_get_sources(_auth: AuthSession) -> SourcesResponse:
    from sl_trigger_leads.tools.source_registry import list_configured_sources

    sources = list_configured_sources(include_urls=True)
    return SourcesResponse(**sources)


@app.get("/api/state", response_model=StateResponse)
async def api_get_state(_auth: AuthSession) -> StateResponse:
    return StateResponse(**get_app_state())


@app.put("/api/state", response_model=OkResponse)
async def api_update_state(body: NotesUpdateRequest, _auth: CsrfSession) -> OkResponse:
    update_app_state(lambda state: state.__setitem__("notes", body.notes))
    return OkResponse()


@app.post("/api/agent/classify", response_model=ClassificationResponse)
async def api_agent_classify(body: AgentQuery, _auth: CsrfSession) -> ClassificationResponse:
    from sl_trigger_leads.tools.signal_tools import classify_signal

    return ClassificationResponse(**classify_signal(body.query))


@app.post("/api/agent/fit-preview", response_model=FitPreviewResponse)
async def api_agent_fit_preview(body: AgentQuery, _auth: CsrfSession) -> FitPreviewResponse:
    from sl_trigger_leads.tools.signal_tools import classify_signal, detect_1bt_fit

    classification = classify_signal(body.query)
    service_fit = detect_1bt_fit(body.query)
    return FitPreviewResponse(
        classification=classification,
        service_fit=service_fit,
        explanation=(
            "This is a text-only fit preview. It is not a verified lead, does not carry a lead score, "
            "and must not be used as evidence without a genuine live public source."
        ),
    )


@app.get("/")
async def get_login(request: Request) -> Response:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token and verify_session_token(token):
        return RedirectResponse(url="/app", status_code=status.HTTP_303_SEE_OTHER)
    return FileResponse(STATIC_DIR / "login.html", media_type="text/html")


@app.get("/app")
async def get_app(request: Request) -> Response:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token or not verify_session_token(token):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@app.get("/static/css/app.css", include_in_schema=False)
async def get_app_stylesheet() -> FileResponse:
    return FileResponse(STATIC_DIR / "css" / "app.css", media_type="text/css")


@app.get("/static/js/app.js", include_in_schema=False)
async def get_app_javascript() -> FileResponse:
    return FileResponse(STATIC_DIR / "js" / "app.js", media_type="text/javascript")


@app.get("/static/js/login.js", include_in_schema=False)
async def get_login_javascript() -> FileResponse:
    return FileResponse(STATIC_DIR / "js" / "login.js", media_type="text/javascript")


@app.get("/api/health", response_model=HealthResponse)
async def api_health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, version=settings.app_version)
