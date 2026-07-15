"""Security and integrity tests for the local Business Intel web app."""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

import bcrypt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import frontend.main as frontend_main
import frontend.storage as storage_module
from frontend import auth as frontend_auth
from frontend.auth import SESSION_COOKIE_NAME
from frontend.config import settings
from frontend.storage import JsonStore

TEST_USERNAME = "1bt-user"
TEST_PASSWORD = "local-test-password"
TEST_PASSWORD_HASH = bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt()).decode()
TEST_SESSION_SECRET = "test-only-session-secret-that-is-longer-than-thirty-two-characters"


def _valid_lead(company: str = "Verified Lanka PLC") -> dict[str, Any]:
    return {
        "company": company,
        "country": "Sri Lanka",
        "sector": "Technology",
        "trigger_summary": "The company is hiring software engineers for an integration programme.",
        "trigger_type": "hiring_spike",
        "evidence_url": "https://itpro.lk/jobs",
        "evidence_excerpt": "Verified public job listing for software engineering and integration roles.",
        "source_name": "ITPro.lk Jobs",
        "published_or_seen_date": "2026-07-15",
        "fetched_at": "2026-07-15T09:00:00+00:00",
        "verified_live": True,
        "score": {
            "total": 75,
            "breakdown": {
                "recent_public_trigger": 25,
                "1bt_service_fit": 20,
                "local_reachability": 15,
                "named_person_found": 5,
                "evidence_quality": 7,
                "deal_size_likelihood": 3,
            },
            "verdict": "Verify contact first",
            "scoring_notes": ["Verified deterministic test score."],
        },
    }


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "shared_username", TEST_USERNAME)
    monkeypatch.setattr(settings, "shared_password_hash", TEST_PASSWORD_HASH)
    monkeypatch.setattr(settings, "session_secret_key", TEST_SESSION_SECRET)
    monkeypatch.setattr(settings, "session_cookie_secure", False)
    monkeypatch.setattr(settings, "host", "127.0.0.1")
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "refresh_min_interval_seconds", 0)
    monkeypatch.setattr(settings, "login_max_attempts", 5)
    monkeypatch.setattr(settings, "login_window_seconds", 300)
    frontend_main.login_limiter.reset()
    frontend_main.refresh_limiter.reset()
    frontend_auth.reset_session_registry()
    frontend_main.runtime_store().write("leads.json", [_valid_lead()])
    with TestClient(frontend_main.app) as test_client:
        yield test_client
    frontend_auth.reset_session_registry()


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def _csrf_headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token, "Sec-Fetch-Site": "same-origin"}


class TestConfigurationAndPassword:
    def test_missing_security_configuration_fails_startup(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "shared_password_hash", "")
        monkeypatch.setattr(settings, "session_secret_key", "")
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        with pytest.raises(RuntimeError, match="BT_SHARED_PASSWORD_HASH"):
            with TestClient(frontend_main.app):
                pass

    def test_bcrypt_password_verification(self, client: TestClient) -> None:
        assert settings.verify_password(TEST_PASSWORD) is True
        assert settings.verify_password("wrong-password") is False
        assert settings.shared_password_hash != TEST_PASSWORD

    def test_non_local_bind_is_rejected(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "host", "0.0.0.0")
        with pytest.raises(RuntimeError, match="local-only"):
            settings.validate_runtime_security()


class TestAuthentication:
    def test_health_and_security_headers(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert "unsafe-inline" not in response.headers["content-security-policy"]

    def test_openapi_is_disabled(self, client: TestClient) -> None:
        assert client.get("/openapi.json").status_code == 404

    def test_untrusted_host_is_rejected(self, client: TestClient) -> None:
        assert client.get("/api/health", headers={"Host": "evil.invalid"}).status_code == 400

    def test_login_sets_strict_httponly_cookie_without_returning_jwt(self, client: TestClient) -> None:
        response = client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"] == TEST_USERNAME
        assert data["csrf_token"]
        assert "token" not in data
        cookie = response.headers["set-cookie"]
        assert "session_token=" in cookie
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        assert "Secure" not in cookie

    @pytest.mark.parametrize(
        ("username", "password"),
        [(TEST_USERNAME, "wrong"), ("wrong-user", TEST_PASSWORD)],
    )
    def test_login_rejects_bad_credentials(
        self,
        client: TestClient,
        username: str,
        password: str,
    ) -> None:
        assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 401

    def test_unicode_username_is_rejected_without_server_error(self, client: TestClient) -> None:
        response = client.post(
            "/api/auth/login",
            json={"username": "\u7528\u6237", "password": TEST_PASSWORD},
        )
        assert response.status_code == 401

    def test_login_is_rate_limited(self, client: TestClient) -> None:
        for _attempt in range(settings.login_max_attempts):
            response = client.post(
                "/api/auth/login",
                json={"username": TEST_USERNAME, "password": "wrong"},
            )
            assert response.status_code == 401
        blocked = client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        )
        assert blocked.status_code == 429
        assert blocked.headers["retry-after"] == str(settings.login_window_seconds)

    def test_login_limiter_check_and_record_is_atomic(self) -> None:
        limiter = frontend_main.SlidingWindowLimiter()
        barrier = threading.Barrier(20)
        outcomes: list[str] = []

        def attempt() -> None:
            barrier.wait()
            try:
                limiter.ensure_allowed("shared-client", max_events=5, window_seconds=300)
                outcomes.append("allowed")
            except HTTPException as exc:
                assert exc.status_code == 429
                outcomes.append("blocked")

        threads = [threading.Thread(target=attempt) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        assert outcomes.count("allowed") == 5
        assert outcomes.count("blocked") == 15

    def test_route_protection_and_app_redirect(self, client: TestClient) -> None:
        assert client.get("/api/leads").status_code == 401
        app_response = client.get("/app", follow_redirects=False)
        assert app_response.status_code == 303
        assert app_response.headers["location"] == "/"

    def test_verify_returns_csrf_for_cookie_session(self, client: TestClient) -> None:
        csrf_token = _login(client)
        response = client.get("/api/auth/verify")
        assert response.status_code == 200
        assert response.json()["csrf_token"] == csrf_token

    def test_csrf_is_required_for_state_changes(self, client: TestClient) -> None:
        csrf_token = _login(client)
        assert client.put("/api/state", json={"notes": "blocked"}).status_code == 403
        assert client.put(
            "/api/state",
            headers=_csrf_headers("wrong-token"),
            json={"notes": "blocked"},
        ).status_code == 403
        assert client.put(
            "/api/state",
            headers=_csrf_headers(csrf_token),
            json={"notes": "allowed"},
        ).status_code == 200

    def test_logout_requires_csrf_and_clears_cookie(self, client: TestClient) -> None:
        csrf_token = _login(client)
        copied_token = client.cookies.get(SESSION_COOKIE_NAME)
        assert copied_token
        assert client.post("/api/auth/logout").status_code == 403
        response = client.post("/api/auth/logout", headers=_csrf_headers(csrf_token))
        assert response.status_code == 200
        assert "session_token=" in response.headers["set-cookie"]
        assert client.get("/api/auth/verify").status_code == 401

        client.cookies.set(SESSION_COOKIE_NAME, copied_token)
        assert client.get("/api/auth/verify").status_code == 401

    def test_unknown_session_identifier_is_rejected(self, client: TestClient) -> None:
        token, _csrf_token = frontend_auth.create_session_token()
        frontend_auth.reset_session_registry()
        assert frontend_auth.verify_session_token(token) is None


class TestSchemasAndIntegrity:
    def test_unknown_request_fields_are_rejected(self, client: TestClient) -> None:
        csrf_token = _login(client)
        response = client.put(
            "/api/state",
            headers=_csrf_headers(csrf_token),
            json={"notes": "ok", "is_admin": True},
        )
        assert response.status_code == 422

    def test_notes_length_is_bounded(self, client: TestClient) -> None:
        csrf_token = _login(client)
        response = client.put(
            "/api/state",
            headers=_csrf_headers(csrf_token),
            json={"notes": "x" * 5001},
        )
        assert response.status_code == 422

    def test_request_size_limit(self, client: TestClient) -> None:
        csrf_token = _login(client)
        response = client.put(
            "/api/state",
            headers={**_csrf_headers(csrf_token), "Content-Type": "application/json"},
            content='{"notes":"' + ("x" * 17_000) + '"}',
        )
        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_streamed_request_size_limit_without_content_length(self) -> None:
        messages = [
            {"type": "http.request", "body": b"x" * 9_000, "more_body": True},
            {"type": "http.request", "body": b"y" * 9_000, "more_body": False},
        ]
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return messages.pop(0)

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        async def consume_body(scope: dict[str, Any], receive_body: Any, send_body: Any) -> None:
            while True:
                message = await receive_body()
                if not message.get("more_body"):
                    break
            await send_body({"type": "http.response.start", "status": 204, "headers": []})
            await send_body({"type": "http.response.body", "body": b""})

        middleware = frontend_main.RequestBodyLimitMiddleware(consume_body, max_body_size=16_384)
        await middleware(
            {
                "type": "http",
                "method": "PUT",
                "path": "/api/state",
                "headers": [(b"content-type", b"application/json")],
            },
            receive,
            send,
        )
        assert sent[0]["status"] == 413

    def test_arbitrary_lead_update_endpoint_is_removed(self, client: TestClient) -> None:
        csrf_token = _login(client)
        response = client.put(
            "/api/leads/0",
            headers=_csrf_headers(csrf_token),
            json={"field": "verified_live", "value": "false"},
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "url",
        ["javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "file:///tmp/source"],
    )
    def test_non_http_evidence_urls_are_rejected(self, url: str) -> None:
        lead = _valid_lead()
        lead["evidence_url"] = url
        with pytest.raises(ValueError, match=r"non-HTTP\(S\)"):
            frontend_main.validate_runtime_leads([lead])

    def test_synthetic_leads_are_rejected(self) -> None:
        lead = _valid_lead("Synthetic Sample Company")
        lead["evidence_url"] = "https://example.test/source"
        with pytest.raises(ValueError, match="blocked"):
            frontend_main.validate_runtime_leads([lead])

    def test_tender_only_leads_are_rejected(self) -> None:
        lead = _valid_lead()
        lead["trigger_type"] = "tender_or_procurement"
        with pytest.raises(ValueError, match="tender"):
            frontend_main.validate_runtime_leads([lead])

    @pytest.mark.parametrize(
        "invalid_score",
        [
            None,
            {},
            {"total": "75", "breakdown": {}, "verdict": "Verify contact first"},
            {
                "total": 101,
                "breakdown": {
                    "recent_public_trigger": 25,
                    "1bt_service_fit": 25,
                    "local_reachability": 20,
                    "named_person_found": 15,
                    "evidence_quality": 10,
                    "deal_size_likelihood": 5,
                },
                "verdict": "Contact now",
            },
            {
                "total": 75,
                "breakdown": {
                    "recent_public_trigger": 25,
                    "1bt_service_fit": 20,
                    "local_reachability": 15,
                    "named_person_found": 5,
                    "evidence_quality": 7,
                    "deal_size_likelihood": 3,
                },
                "verdict": "Definitely buy",
            },
        ],
    )
    def test_invalid_lead_scores_are_rejected(self, invalid_score: Any) -> None:
        lead = _valid_lead()
        lead["score"] = invalid_score
        with pytest.raises(ValueError, match="score"):
            frontend_main.validate_runtime_leads([lead])

    def test_verified_live_must_be_exact_boolean_true(self) -> None:
        lead = _valid_lead()
        lead["verified_live"] = "true"
        with pytest.raises(ValueError, match="verified_live"):
            frontend_main.validate_runtime_leads([lead])

        lead["verified_live"] = False
        with pytest.raises(ValueError, match="verified_live"):
            frontend_main.validate_runtime_leads([lead])

    def test_xss_payload_is_stored_only_as_json_data(self, client: TestClient) -> None:
        csrf_token = _login(client)
        payload = '<img src=x onerror="alert(1)"><script>alert(2)</script>'
        response = client.put(
            "/api/state",
            headers=_csrf_headers(csrf_token),
            json={"notes": payload},
        )
        assert response.status_code == 200
        state_response = client.get("/api/state")
        assert state_response.json()["notes"] == payload

        static_root = Path(frontend_main.STATIC_DIR)
        javascript = (static_root / "js" / "app.js").read_text(encoding="utf-8")
        html = (static_root / "index.html").read_text(encoding="utf-8")
        assert "innerHTML" not in javascript
        assert "insertAdjacentHTML" not in javascript
        assert "localStorage" not in javascript
        assert not re.search(r"\son[a-z]+=", html, re.IGNORECASE)
        assert "style=" not in html

    def test_modal_focus_trap_moves_focus_without_browser_default_behavior(self) -> None:
        javascript = (
            Path(frontend_main.STATIC_DIR) / "js" / "app.js"
        ).read_text(encoding="utf-8")

        assert "event.preventDefault();\n      const currentIndex" in javascript
        assert "focusable.indexOf(document.activeElement)" in javascript
        assert "focusable[nextIndex].focus()" in javascript

    def test_fit_preview_never_claims_a_verified_scored_lead(self, client: TestClient) -> None:
        csrf_token = _login(client)
        response = client.post(
            "/api/agent/fit-preview",
            headers=_csrf_headers(csrf_token),
            json={"query": "A Sri Lankan company is hiring software engineers for API integration."},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["verified_lead"] is False
        assert "service_fit" in data
        assert "score" not in data
        assert "evidence_url" not in data
        assert client.post(
            "/api/agent/score",
            headers=_csrf_headers(csrf_token),
            json={"query": "test"},
        ).status_code == 404


class TestStorageAndRefresh:
    def test_corrupt_json_is_not_silently_replaced(self, tmp_path: Path) -> None:
        store = JsonStore(tmp_path)
        path = tmp_path / "app_state.json"
        corrupt = '{"notes": '
        path.write_text(corrupt, encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            store.read("app_state.json", {})
        assert path.read_text(encoding="utf-8") == corrupt

    def test_permission_error_is_not_silently_treated_as_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = JsonStore(tmp_path)
        store.write("app_state.json", {"notes": "preserve"})
        original_read_text = Path.read_text

        def deny_read(path: Path, *args: Any, **kwargs: Any) -> str:
            if path.name == "app_state.json":
                raise PermissionError("simulated permission failure")
            return original_read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", deny_read)
        with pytest.raises(PermissionError, match="permission failure"):
            store.read("app_state.json", {})

    def test_concurrent_updates_preserve_both_changes(self, tmp_path: Path) -> None:
        store = JsonStore(tmp_path)
        store.write("app_state.json", {})
        start = threading.Barrier(3)
        errors: list[BaseException] = []

        def worker(key: str) -> None:
            try:
                start.wait(timeout=2)

                def mutate(current: Any) -> dict[str, Any]:
                    state = dict(current)
                    time.sleep(0.02)
                    state[key] = True
                    return state

                store.update("app_state.json", {}, mutate)
            except BaseException as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        first = threading.Thread(target=worker, args=("refresh",))
        second = threading.Thread(target=worker, args=("notes",))
        first.start()
        second.start()
        start.wait(timeout=2)
        first.join(timeout=2)
        second.join(timeout=2)

        assert not errors
        assert store.read("app_state.json", {}) == {"refresh": True, "notes": True}

    def test_atomic_write_preserves_original_on_replace_failure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = JsonStore(tmp_path)
        original = {"notes": "original"}
        store.write("app_state.json", original)

        def fail_replace(_source: Path, _destination: Path) -> None:
            raise OSError("simulated replace failure")

        monkeypatch.setattr(storage_module.os, "replace", fail_replace)
        with pytest.raises(OSError, match="replace failure"):
            store.write("app_state.json", {"notes": "new"})
        assert store.read("app_state.json", {}) == original
        assert not list(tmp_path.glob("*.tmp"))

    def test_failed_live_refresh_preserves_existing_leads(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        csrf_token = _login(client)
        before = client.get("/api/leads").json()["leads"]

        def fail_refresh() -> dict[str, Any]:
            raise RuntimeError("source unavailable")

        monkeypatch.setattr(frontend_main, "_run_live_refresh", fail_refresh)
        response = client.post("/api/leads/refresh", headers=_csrf_headers(csrf_token))
        assert response.status_code == 503
        assert client.get("/api/leads").json()["leads"] == before

    def test_invalid_live_refresh_preserves_existing_leads(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        csrf_token = _login(client)
        before = client.get("/api/leads").json()["leads"]
        invalid = _valid_lead("Bad URL Co")
        invalid["evidence_url"] = "javascript:alert(1)"
        monkeypatch.setattr(
            frontend_main,
            "_run_live_refresh",
            lambda: {"leads": [invalid], "source_coverage_summary": {}},
        )
        response = client.post("/api/leads/refresh", headers=_csrf_headers(csrf_token))
        assert response.status_code == 503
        assert client.get("/api/leads").json()["leads"] == before

    def test_valid_live_refresh_replaces_data_atomically(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        csrf_token = _login(client)
        replacement = _valid_lead("Fresh Public Signal PLC")
        monkeypatch.setattr(
            frontend_main,
            "_run_live_refresh",
            lambda: {
                "leads": [replacement],
                "fetched_at": "2026-07-15T10:00:00+00:00",
                "source_coverage_summary": {
                    "sources_succeeded": 1,
                    "sources_recovered": 0,
                    "sources_failed": 0,
                },
            },
        )
        response = client.post("/api/leads/refresh", headers=_csrf_headers(csrf_token))
        assert response.status_code == 200
        assert client.get("/api/leads").json()["leads"][0]["company"] == "Fresh Public Signal PLC"


class TestFrontendRegressionContracts:
    def test_navigation_uses_abort_and_generation_guards(self) -> None:
        javascript = (Path(frontend_main.STATIC_DIR) / "js" / "app.js").read_text(encoding="utf-8")
        assert "AbortController" in javascript
        assert "navigationGeneration" in javascript
        assert "config.signal" in javascript
        assert "isActiveNavigation" in javascript

    def test_mobile_sidebar_focus_and_escape_contract(self) -> None:
        javascript = (Path(frontend_main.STATIC_DIR) / "js" / "app.js").read_text(encoding="utf-8")
        assert "onSidebarKeyDown" in javascript
        assert 'event.key === "Escape"' in javascript
        assert "firstNavigationItem.focus()" in javascript
        assert 'document.removeEventListener("keydown", onSidebarKeyDown)' in javascript

    def test_source_status_and_login_error_fallbacks_are_explicit(self) -> None:
        app_javascript = (Path(frontend_main.STATIC_DIR) / "js" / "app.js").read_text(encoding="utf-8")
        login_javascript = (Path(frontend_main.STATIC_DIR) / "js" / "login.js").read_text(encoding="utf-8")
        assert 'state: "offline"' in app_javascript
        assert 'state: "unknown"' in app_javascript
        assert "response.status === 429" in login_javascript
        assert "await response.json()" in login_javascript

    def test_short_login_viewport_can_scroll(self) -> None:
        stylesheet = (Path(frontend_main.STATIC_DIR) / "css" / "app.css").read_text(encoding="utf-8")
        assert "overflow-y: auto" in stylesheet
        assert "max-height: 560px" in stylesheet

    def test_async_ui_actions_preserve_submitted_state(self) -> None:
        javascript = (Path(frontend_main.STATIC_DIR) / "js" / "app.js").read_text(encoding="utf-8")
        assert "const submittedNotes = notesInput.value" in javascript
        assert "JSON.stringify({ notes: submittedNotes })" in javascript
        assert "appState.notesOriginal = submittedNotes" in javascript
        assert "classifyButton.disabled = true" in javascript
        assert "fitButton.disabled = true" in javascript
        assert "queryInput.readOnly = true" in javascript
        assert "queryInput.readOnly = false" in javascript

    def test_startup_error_and_date_only_guards_are_explicit(self) -> None:
        javascript = (Path(frontend_main.STATIC_DIR) / "js" / "app.js").read_text(encoding="utf-8")
        assert "renderStartupError" in javascript
        assert 'createButton("Retry startup"' in javascript
        assert 'error.message === "Session expired"' in javascript
        assert r"/^(\d{4})-(\d{2})-(\d{2})$/" in javascript
        assert "new Date(year, month, day)" in javascript
