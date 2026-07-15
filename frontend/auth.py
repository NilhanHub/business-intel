from __future__ import annotations

import secrets
import threading
import time
from typing import Any

import jwt

from frontend.config import settings

ALGORITHM = "HS256"
ISSUER = "1bt-business-intel-local"
AUDIENCE = "1bt-business-intel-browser"
SESSION_COOKIE_NAME = "session_token"


class SessionRegistry:
    """Process-local allowlist for issued browser sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, int] = {}
        self._lock = threading.RLock()

    def _prune_expired(self, now: int) -> None:
        expired = [jti for jti, expires_at in self._sessions.items() if expires_at <= now]
        for jti in expired:
            self._sessions.pop(jti, None)

    def register(self, jti: str, expires_at: int) -> None:
        with self._lock:
            self._prune_expired(int(time.time()))
            self._sessions[jti] = expires_at

    def is_active(self, jti: str, expires_at: int) -> bool:
        now = int(time.time())
        with self._lock:
            self._prune_expired(now)
            return self._sessions.get(jti) == expires_at and expires_at > now

    def revoke(self, jti: str) -> None:
        with self._lock:
            self._sessions.pop(jti, None)

    def reset(self) -> None:
        with self._lock:
            self._sessions.clear()


session_registry = SessionRegistry()


def create_session_token() -> tuple[str, str]:
    now = int(time.time())
    csrf_token = secrets.token_urlsafe(32)
    jti = secrets.token_urlsafe(16)
    expires_at = now + settings.session_expire_minutes * 60
    payload: dict[str, Any] = {
        "sub": settings.shared_username,
        "role": "viewer",
        "csrf": csrf_token,
        "jti": jti,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.session_secret_key, algorithm=ALGORITHM)
    session_registry.register(jti, expires_at)
    return token, csrf_token


def verify_session_token(token: str) -> dict[str, Any] | None:
    if not settings.session_secret_key:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.session_secret_key,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["sub", "csrf", "jti", "iss", "aud", "iat", "exp"]},
        )
        if payload.get("sub") != settings.shared_username or payload.get("role") != "viewer":
            return None
        jti = payload.get("jti")
        expires_at = payload.get("exp")
        if not isinstance(jti, str) or not isinstance(expires_at, int):
            return None
        if not session_registry.is_active(jti, expires_at):
            return None
        return payload
    except jwt.PyJWTError:
        return None


def revoke_session(payload: dict[str, Any]) -> None:
    jti = payload.get("jti")
    if isinstance(jti, str):
        session_registry.revoke(jti)


def reset_session_registry() -> None:
    """Clear process-local sessions for startup isolation and deterministic tests."""
    session_registry.reset()
