from __future__ import annotations

import os
from pathlib import Path

import bcrypt
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    """Keep mutable application data outside the source tree."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "1BT" / "Business_Intel"
    return Path.home() / ".local" / "share" / "1bt-business-intel"


class Settings(BaseSettings):
    app_name: str = "1BT Business Intel"
    app_version: str = "1.0.0"
    debug: bool = False

    shared_username: str = "1bt-user"
    shared_password_hash: str = ""

    session_secret_key: str = ""
    session_expire_minutes: int = Field(default=480, ge=15, le=1440)
    session_cookie_secure: bool = False

    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
    trusted_hosts: str = "127.0.0.1,localhost,testserver"

    login_max_attempts: int = Field(default=5, ge=1, le=20)
    login_window_seconds: int = Field(default=300, ge=30, le=3600)
    refresh_min_interval_seconds: int = Field(default=30, ge=0, le=3600)

    data_dir: Path = Field(default_factory=_default_data_dir)

    model_config = SettingsConfigDict(
        env_prefix="BT_",
        env_file=".env",
        extra="ignore",
    )

    @property
    def allowed_hosts(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    def validate_runtime_security(self) -> None:
        """Fail closed before the web app starts accepting requests."""
        problems: list[str] = []
        if not self.shared_username.strip():
            problems.append("BT_SHARED_USERNAME must not be empty")
        if not self.shared_password_hash:
            problems.append("BT_SHARED_PASSWORD_HASH is required")
        else:
            try:
                bcrypt.checkpw(b"configuration-check", self.shared_password_hash.encode("utf-8"))
            except (TypeError, ValueError):
                problems.append("BT_SHARED_PASSWORD_HASH must be a valid bcrypt hash")
        if len(self.session_secret_key) < 32:
            problems.append("BT_SESSION_SECRET_KEY must contain at least 32 characters")
        if self.host not in {"127.0.0.1", "localhost"}:
            problems.append("BT_HOST must remain local-only (127.0.0.1 or localhost)")
        if problems:
            raise RuntimeError("; ".join(problems))

    def verify_password(self, password: str) -> bool:
        if not self.shared_password_hash:
            return False
        try:
            return bcrypt.checkpw(password.encode("utf-8"), self.shared_password_hash.encode("utf-8"))
        except (TypeError, ValueError):
            return False


settings = Settings()
