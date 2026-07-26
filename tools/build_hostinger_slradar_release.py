from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from frontend.main import validate_runtime_leads

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "deploy" / "hostinger-slradar"
RELEASE_ROOT = ROOT / "tmp" / "hostinger-releases"
DOMAIN = "slradar.globalapps.world"
HOSTING_DATA_DIR = f"/home/u624401615/domains/{DOMAIN}/data"


def _load_leads() -> list[dict[str, object]]:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is required to locate the verified lead snapshot.")
    leads_path = Path(local_app_data) / "1BT" / "Business_Intel" / "leads.json"
    leads = json.loads(leads_path.read_text(encoding="utf-8"))
    validated = validate_runtime_leads(leads)
    if not validated:
        raise RuntimeError("The deployment seed must contain verified leads.")
    return validated


def _state_for(leads: list[dict[str, object]]) -> dict[str, object]:
    verdicts = [
        str((lead.get("score") or {}).get("verdict", ""))
        for lead in leads
        if isinstance(lead.get("score"), dict)
    ]
    return {
        "last_fetch": None,
        "total_leads_found": len(leads),
        "sources_enabled": 4,
        "sources_ok": 0,
        "sources_failed": 0,
        "leads_contact_now": verdicts.count("Contact now"),
        "leads_verify_first": verdicts.count("Verify contact first"),
        "leads_watch_list": verdicts.count("Watch list"),
        "leads_parked": verdicts.count("Park"),
        "notes": "",
    }


def _runtime_config(password: str) -> dict[str, object]:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=64,
    )
    return {
        "app_name": "1BT Opportunity Radar",
        "app_version": "1.0.0",
        "shared_username": "1bt-user",
        "password_salt": salt.hex(),
        "password_hash": password_hash.hex(),
        "session_secret": base64.urlsafe_b64encode(secrets.token_bytes(48)).decode("ascii"),
        "trusted_hosts": [
            DOMAIN,
            f"www.{DOMAIN}",
            "127.0.0.1",
            "localhost",
        ],
        "cookie_secure": True,
        "session_minutes": 480,
        "login_max_attempts": 5,
        "login_window_seconds": 300,
        "refresh_min_interval_seconds": 30,
        "data_dir": HOSTING_DATA_DIR,
    }


def _copy_release_source(staging: Path) -> None:
    shutil.copy2(ADAPTER / "package.json", staging / "package.json")
    shutil.copy2(ADAPTER / "server.mjs", staging / "server.mjs")
    shutil.copytree(ADAPTER / "src", staging / "src")
    shutil.copytree(ROOT / "frontend" / "static", staging / "public")
    shutil.copy2(
        ROOT / "sl_trigger_leads" / "data" / "source_registry.json",
        staging / "source-registry.json",
    )


def _git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build() -> Path:
    password = os.environ.get("SLRADAR_DEPLOY_PASSWORD", "")
    if len(password) < 10:
        raise RuntimeError("SLRADAR_DEPLOY_PASSWORD must contain at least 10 characters.")

    created = datetime.now(UTC)
    stamp = created.astimezone().strftime("%Y%m%d_%H%M%S")
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    staging = RELEASE_ROOT / f"slradar-hostinger_{stamp}"
    archive = RELEASE_ROOT / f"slradar-hostinger_{stamp}.zip"
    if staging.exists() or archive.exists():
        raise RuntimeError(f"Release path already exists: {staging}")
    staging.mkdir()

    leads = _load_leads()
    _copy_release_source(staging)
    (staging / "seed-leads.json").write_text(
        json.dumps(leads, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (staging / "seed-state.json").write_text(
        json.dumps(_state_for(leads), indent=2) + "\n",
        encoding="utf-8",
    )
    (staging / "runtime-config.json").write_text(
        json.dumps(_runtime_config(password), indent=2) + "\n",
        encoding="utf-8",
    )
    (staging / "release-manifest.json").write_text(
        json.dumps(
            {
                "domain": DOMAIN,
                "created_at": created.isoformat(),
                "source_commit": _git_revision(),
                "verified_lead_count": len(leads),
                "runtime": "Hostinger Node.js",
                "secrets_committed": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for item in sorted(staging.rglob("*")):
            if item.is_file():
                bundle.write(item, item.relative_to(staging).as_posix())

    print(archive.resolve())
    return archive


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:
        print(f"Release build failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
