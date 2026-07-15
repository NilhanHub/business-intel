# Dependency security status

Last checked: 2026-07-15.

The resolved local environment uses Google ADK `2.4.0`, FastAPI `0.139.0`, and Starlette `1.3.1`. This closes the previous ADK 1.x constraint that held Starlette below the complete advisory-fix floor.

## Required release gate

Both dependency surfaces must pass the ordinary audit without `--ignore-vuln`:

```powershell
uv sync --locked
uv run --with pip-audit pip-audit --skip-editable --format json --output Evidence/pip-audit-default.json
uv run --with pip-audit pip-audit --skip-editable --format cyclonedx-json --output Evidence/sbom-default.cdx.json

uv sync --all-extras --locked
uv run --with pip-audit pip-audit --skip-editable --format json --output Evidence/pip-audit-all-extras.json
uv run --with pip-audit pip-audit --skip-editable --format cyclonedx-json --output Evidence/sbom-all-extras.cdx.json

Copy-Item Evidence/pip-audit-default.json Evidence/pip-audit-final.json -Force
Copy-Item Evidence/sbom-default.cdx.json Evidence/sbom-final.cdx.json -Force
uv sync --locked
```

The first command set proves the supported local installation. The second proves that optional evaluation and Agent Runtime dependencies do not reintroduce a vulnerable transitive package. The default and all-extras JSON/CycloneDX files preserve both surfaces; `Evidence/pip-audit-final.json` and `Evidence/sbom-final.cdx.json` are the canonical local-runtime copies.

## Local-only dependency boundary

- Cloud Agent Runtime, Cloud Logging, Secret Manager, GCS telemetry, and related instrumentation are in the `agent-runtime` optional extra.
- Legacy Agent Runtime modules require `BT_ENABLE_AGENT_RUNTIME=1` before importing Vertex or constructing `AdkApp`.
- A normal local import fails closed without cloud discovery, credentials lookup, deployment, or project mutation.
- The local web protections remain in force: trusted-host validation, strict cookie/CSRF handling, bounded schema-driven JSON, fixed asset routes, security headers, and `127.0.0.1` binding.

## Compatibility notes

- Existing `Agent`, `App`, and `Runner` patterns and all model selections are preserved; the experimental Workflow API is not used.
- Runtime sessions remain in-memory, so there is no ADK session database migration and no ADK 1.x/2.x shared session store.
- ADK `2.4.0` emits one internal `BaseAgentConfig` deprecation during import. Pytest filters only that exact upstream warning and treats every other warning as an error. Remove the narrow filter as soon as a later ADK release stops emitting it.
- Paid model evaluation, live integrations, deployment, and email sending are not implied by a clean dependency audit and remain explicit approval gates.

## Rollback

If compatibility verification fails, restore only the migration-specific dependency and adapter changes from the pre-migration snapshot under `Evidence/`. Returning to ADK `1.36.1` is not a secure release fallback because it restores the known Starlette audit blocker; that state remains no-go.
