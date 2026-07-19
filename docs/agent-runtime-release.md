# Exact Agent Runtime release

This runbook updates only the existing Business_Intel ADK runtime. It never deploys the FastAPI web interface, creates another runtime, changes models, sends email, or performs outreach.

## Fixed target

- Project: `business-intel-123`
- Region: `us-central1`
- Runtime ID: `3155700076542689280`
- Display name: `business-intel-agent-identity-direct-bluegreen`
- Managed Python: `3.13`
- Deployment identity: `codex-key-power-proof-sa@business-intel-123.iam.gserviceaccount.com`

The command refuses any other values. It also requires a clean working tree at the full commit supplied through `--commit`, exactly four existing runtimes, the existing Agent Identity, no service account or secret bindings, and the preserved `1/10`, `4 CPU`, `8GiB`, concurrency `9` scaling contract.

## Prepare the locked Runtime package

Run these commands after dependency changes and commit the resulting lock and requirements file:

```powershell
uv lock
uv export --extra agent-runtime --no-dev --no-hashes --no-sources --no-header --no-emit-project --locked --output-file sl_trigger_leads\app_utils\.requirements.txt
uv run pytest -q tests\unit\test_agent_runtime_deploy.py
```

The Runtime export must include ADK 2.4, Vertex AI, Cloud Logging, Secret Manager, Google GenAI, GCS support, and telemetry. It must not include Vertex evaluation packages such as `litellm`, `pandas`, or `scikit-learn`.

## Preflight and single update

Run from a clean detached worktree at the exact merged `master` commit. Create a fresh ignored folder under the main repository's `Evidence` directory and use absolute paths for its output and operation state.

```powershell
$Commit = (git rev-parse HEAD).Trim()
$Evidence = 'D:\gaps\Business_Intel\Evidence\agent-runtime-repair-YYYYMMDD-HHMMSS'
$Operation = Join-Path $Evidence 'operation.json'
$Common = @(
    '--project', 'business-intel-123',
    '--region', 'us-central1',
    '--runtime-id', '3155700076542689280',
    '--display-name', 'business-intel-agent-identity-direct-bluegreen',
    '--commit', $Commit,
    '--python-version', '3.13',
    '--account', 'codex-key-power-proof-sa@business-intel-123.iam.gserviceaccount.com'
)

uv run --extra agent-runtime python .\tools\deploy_agent_runtime_exact.py preflight @Common `
    --output (Join-Path $Evidence 'preflight.json')

uv run --extra agent-runtime python .\tools\deploy_agent_runtime_exact.py deploy @Common `
    --operation-file $Operation `
    --output (Join-Path $Evidence 'deploy-start.json')
```

The deploy command reserves the operation file before contacting Vertex. Never delete or reuse that file to retry. An uncertain start is a stop condition.

## Monitor and verify

Wait one minute between status checks. Invoke only `status`; do not run `deploy` again.

```powershell
uv run --extra agent-runtime python .\tools\deploy_agent_runtime_exact.py status @Common `
    --operation-file $Operation `
    --output (Join-Path $Evidence 'status-latest.json')
```

After `SUCCEEDED`, run the one policy-only smoke request:

```powershell
uv run --extra agent-runtime python .\tools\deploy_agent_runtime_exact.py smoke @Common `
    --operation-file $Operation `
    --output (Join-Path $Evidence 'policy-smoke.json')
```

Success requires the same runtime ID and count, Python 3.13, the explicit requirements path, preserved operation schemas and environment values, `BT_ENABLE_AGENT_RUNTIME=1`, clean startup logs, and a response that rejects synthetic and tender-only leads without invoking tools.

## Failure policy

Any failed preflight, update, postflight, log check, or smoke test stops the release. Do not create a replacement runtime, delete historical runtimes, redeploy automatically, change IAM, deploy the web UI, or send outreach. Record the failure and keep the previous runtime for diagnosis.
