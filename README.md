# Business Intel

Business Intel is a local-only Google ADK and FastAPI workspace for Sri Lanka public-signal lead intelligence. Runtime leads are accepted only when they retain genuine public evidence, and tender/procurement-only signals are rejected.

## Local setup on Windows

Requirements: Python 3.11–3.13, [`uv`](https://docs.astral.sh/uv/), and PowerShell.

```powershell
uv sync
Copy-Item frontend\.env.example .env
```

Generate a bcrypt password hash without placing the plaintext password in shell history:

```powershell
uv run python -c "import bcrypt,getpass; p=getpass.getpass('Shared password: '); print(bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode())"
```

Generate an independent session-signing secret:

```powershell
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste those two generated values into `.env` as `BT_SHARED_PASSWORD_HASH` and `BT_SESSION_SECRET_KEY`. The app intentionally refuses to start when either value is missing or invalid.

Start the local server:

```powershell
uv run python -m frontend.server
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). The single shared username defaults to `1bt-user`; the password is the one used to generate the bcrypt hash.

The server is restricted to `127.0.0.1`. Mutable leads and workspace state default to `%LOCALAPPDATA%\1BT\Business_Intel`, outside the repository. Override that location with `BT_DATA_DIR` only when needed.

## Web workspace

- Dashboard, verified live leads, public-source status, and shared local notes
- HttpOnly, SameSite=Strict session cookie with CSRF protection
- Genuine live-source refresh; saved output is used only for first-run bootstrap
- Text-only signal classification and 1BT service-fit preview
- No free-text lead score, fabricated evidence, multi-user tenancy, or deployment path

## Verification

The safe default suite excludes `Evidence`, archives, integration tests, and paid live-model evaluation:

```powershell
uv sync --extra lint
uv run pytest
uv run ruff check .
uv run ty check
uv run codespell
node --check frontend\static\js\app.js
node --check frontend\static\js\login.js
uv run --with pip-audit pip-audit --skip-editable
```

The local runtime is locked to Google ADK `2.4.0`, FastAPI `0.139.0`, and Starlette `1.3.1`. The ordinary dependency audit must exit cleanly without ignored vulnerabilities. See [docs/dependency-security.md](docs/dependency-security.md) for the exact release gate and all-extras audit.

Paid or account-sensitive checks are explicit approval gates and are not part of `uv run pytest`:

```powershell
uv run pytest tests\integration hello_cloud_agent\tests\integration
agents-cli eval run --all
```

## Project layout

- `frontend/` — local FastAPI server and static browser UI
- `sl_trigger_leads/` — Sri Lanka public-signal ADK app and real-data guardrails
- `uk_ie_d365_leads/` — separate UK/IE Dynamics 365 workflow
- `tests/unit/` — deterministic web security and integrity checks
- `tests/eval/` — explicit model-evaluation configuration and lead-policy cases
- `Evidence/` — local verification evidence; ignored by Git

## Deployment status

The FastAPI browser workspace remains local-only and must not be deployed. The ADK agent has one separately approved Google Agent Runtime release path. Cloud dependencies are not installed by `uv sync`; they live in the optional `agent-runtime` extra, and adapters still fail closed unless `BT_ENABLE_AGENT_RUNTIME=1` is present in the managed runtime.

Do not use `agents-cli deploy` for this repository. Version 0.1.2 omits the `agent-runtime` optional dependency group when it generates deployment requirements and inherits its own Python version. Use the exact-target, update-only command documented in [docs/agent-runtime-release.md](docs/agent-runtime-release.md). It supplies the canonical locked requirements file, pins Python 3.13, and refuses to create or update any other runtime.

[HOSTINGER_DEPLOYMENT.md](HOSTINGER_DEPLOYMENT.md) is retained only as an unsupported future draft and must not be treated as a runbook. The `agents-cli` deployment metadata is historical scaffold configuration, not authorization to deploy.
