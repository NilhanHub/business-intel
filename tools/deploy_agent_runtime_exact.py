"""Guarded, exact-target deployment for the approved Business_Intel runtime.

This command exists because agents-cli 0.1.2 does not export optional dependency
groups into its generated Agent Runtime requirements file. It never creates a
runtime: the only supported mutation is one update of the approved existing
resource, followed by separately invoked status and smoke commands.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPROVED_PROJECT = "business-intel-123"
APPROVED_PROJECT_NUMBER = "44345068412"
APPROVED_REGION = "us-central1"
APPROVED_RUNTIME_ID = "3155700076542689280"
APPROVED_DISPLAY_NAME = "business-intel-agent-identity-direct-bluegreen"
APPROVED_RESOURCE_NAME = (
    f"projects/{APPROVED_PROJECT_NUMBER}/locations/{APPROVED_REGION}/"
    f"reasoningEngines/{APPROVED_RUNTIME_ID}"
)
APPROVED_ACCOUNT = "codex-key-power-proof-sa@business-intel-123.iam.gserviceaccount.com"
APPROVED_PYTHON_VERSION = "3.13"
EXPECTED_RUNTIME_COUNT = 4
EXPECTED_REQUIREMENTS_FILE = "sl_trigger_leads/app_utils/.requirements.txt"
EXPECTED_ENTRYPOINT_MODULE = "sl_trigger_leads.agent_runtime_app"
EXPECTED_ENTRYPOINT_OBJECT = "agent_runtime"
APPROVED_SOURCE_PACKAGES = (
    "./sl_trigger_leads",
    "./business_intel",
    "./uk_ie_d365_leads",
)
RUNTIME_GATE_NAME = "BT_ENABLE_AGENT_RUNTIME"
RUNTIME_GATE_VALUE = "1"
EXPECTED_ENV_NAMES = frozenset(
    {
        "AGENT_VERSION",
        "BUSINESS_INTEL_EFFECTIVE_IDENTITY",
        "BUSINESS_INTEL_REASONING_ENGINE_ID",
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY",
        "GOOGLE_CLOUD_REGION",
        "NUM_WORKERS",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
    }
)
REQUIRED_RUNTIME_PACKAGES = frozenset(
    {
        "gcsfs",
        "google-adk",
        "google-cloud-aiplatform",
        "google-cloud-logging",
        "google-cloud-secret-manager",
        "google-genai",
        "opentelemetry-instrumentation-google-genai",
    }
)
FORBIDDEN_RUNTIME_PACKAGES = frozenset(
    {
        "litellm",
        "pandas",
        "rouge-score",
        "ruamel-yaml",
        "scikit-learn",
        "scipy",
    }
)
SMOKE_PROMPT = (
    "State only the lead-evidence policy: may synthetic or sample leads, or "
    "tender-only signals, be returned? Do not call tools, browse, send email, "
    "perform outreach, or mutate any account."
)


class DeploymentGuardError(RuntimeError):
    """A fail-closed deployment guard rejected the requested action."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_package_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _hash_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path = path.resolve()
    _require_evidence_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentGuardError(f"Cannot read operation state: {path}") from exc
    if not isinstance(value, dict):
        raise DeploymentGuardError("Operation state must be a JSON object.")
    return value


def _require_evidence_path(path: Path) -> None:
    if "evidence" not in {part.lower() for part in path.resolve().parts}:
        raise DeploymentGuardError("Deployment artifacts must be stored under Evidence/.")


def parse_locked_requirements(text: str) -> dict[str, str]:
    """Return exact package pins from a uv-exported requirements file."""
    packages: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = line.split(";", maxsplit=1)[0].strip()
        match = re.fullmatch(
            r"([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s]+)",
            requirement,
        )
        if not match:
            raise DeploymentGuardError(
                f"Deployment requirement line {line_number} is not an exact pin."
            )
        name = _canonical_package_name(match.group(1))
        version = match.group(2)
        previous = packages.get(name)
        if previous is not None and previous != version:
            raise DeploymentGuardError(
                f"Deployment requirements contain conflicting pins for {name}."
            )
        packages[name] = version
    return packages


def validate_runtime_requirements(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    expected = (PROJECT_ROOT / EXPECTED_REQUIREMENTS_FILE).resolve()
    if resolved != expected:
        raise DeploymentGuardError(
            f"Requirements file must be {EXPECTED_REQUIREMENTS_FILE}."
        )
    if not resolved.is_file():
        raise DeploymentGuardError("Canonical deployment requirements file is missing.")

    packages = parse_locked_requirements(resolved.read_text(encoding="utf-8"))
    missing = sorted(REQUIRED_RUNTIME_PACKAGES - packages.keys())
    forbidden = sorted(FORBIDDEN_RUNTIME_PACKAGES & packages.keys())
    if missing:
        raise DeploymentGuardError(
            "Deployment requirements are missing: " + ", ".join(missing)
        )
    if forbidden:
        raise DeploymentGuardError(
            "Deployment requirements contain evaluation-only packages: "
            + ", ".join(forbidden)
        )
    if packages["google-adk"] != "2.4.0":
        raise DeploymentGuardError("Deployment must use the locked Google ADK 2.4.0.")

    return {
        "path": EXPECTED_REQUIREMENTS_FILE,
        "sha256": _hash_file(resolved),
        "package_count": len(packages),
        "required_versions": {
            name: packages[name] for name in sorted(REQUIRED_RUNTIME_PACKAGES)
        },
        "forbidden_packages_present": [],
    }


def validate_source_package_closure() -> dict[str, Any]:
    """Require every first-party import to be present in the uploaded source."""
    included_roots = {
        Path(package.removeprefix("./")).parts[0]
        for package in APPROVED_SOURCE_PACKAGES
    }
    first_party_roots = {
        "business_intel",
        "frontend",
        "sl_trigger_leads",
        "uk_ie_d365_leads",
    }
    imported_roots: set[str] = set()
    for package_root in sorted(included_roots):
        for source_path in (PROJECT_ROOT / package_root).rglob("*.py"):
            if "tests" in source_path.relative_to(PROJECT_ROOT).parts:
                continue
            tree = ast.parse(
                source_path.read_text(encoding="utf-8"),
                filename=str(source_path),
            )
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_roots.update(
                        alias.name.partition(".")[0]
                        for alias in node.names
                        if alias.name.partition(".")[0] in first_party_roots
                    )
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.level == 0
                    and node.module
                ):
                    root = node.module.partition(".")[0]
                    if root in first_party_roots:
                        imported_roots.add(root)
        imported_roots.add(package_root)
    missing = sorted(imported_roots - included_roots)
    if missing:
        raise DeploymentGuardError(
            "Runtime source package closure is incomplete; missing: "
            + ", ".join(missing)
        )
    return {
        "source_packages": list(APPROVED_SOURCE_PACKAGES),
        "first_party_import_roots": sorted(imported_roots),
    }


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise DeploymentGuardError(f"Git check failed: git {' '.join(args)}")
    return result.stdout.strip()


def validate_git_release_state(expected_commit: str) -> dict[str, Any]:
    if Path.cwd().resolve() != PROJECT_ROOT:
        raise DeploymentGuardError("Run the deployment command from its repository root.")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise DeploymentGuardError("--commit must be a full lowercase Git commit hash.")
    actual_commit = _git("rev-parse", "HEAD")
    if actual_commit != expected_commit:
        raise DeploymentGuardError(
            f"HEAD {actual_commit} does not match approved commit {expected_commit}."
        )
    dirty = _git("status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise DeploymentGuardError("Deployment source must have a clean working tree.")
    return {
        "commit": actual_commit,
        "tree": _git("rev-parse", "HEAD^{tree}"),
        "clean": True,
    }


def validate_approved_arguments(args: argparse.Namespace) -> None:
    expected = {
        "project": APPROVED_PROJECT,
        "region": APPROVED_REGION,
        "runtime_id": APPROVED_RUNTIME_ID,
        "display_name": APPROVED_DISPLAY_NAME,
        "python_version": APPROVED_PYTHON_VERSION,
        "account": APPROVED_ACCOUNT,
    }
    for name, value in expected.items():
        if getattr(args, name) != value:
            raise DeploymentGuardError(
                f"--{name.replace('_', '-')} must be the approved value {value!r}."
            )


def _gcloud_executable() -> str:
    for name in ("gcloud.cmd", "gcloud.exe", "gcloud"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise DeploymentGuardError("Google Cloud CLI is not available on PATH.")


def credentials_for_account(account: str) -> Any:
    """Return short-lived credentials without changing active gcloud state."""
    result = subprocess.run(
        [
            _gcloud_executable(),
            "auth",
            "print-access-token",
            "--account",
            account,
            "--quiet",
        ],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token:
        raise DeploymentGuardError(
            "The approved gcloud account cannot provide a short-lived access token."
        )
    try:
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise DeploymentGuardError(
            "Google authentication dependencies are not installed."
        ) from exc
    return Credentials(token)


def make_vertex_client(args: argparse.Namespace) -> Any:
    try:
        import vertexai
    except ImportError as exc:
        raise DeploymentGuardError(
            "Agent Runtime dependencies are not installed; use --extra agent-runtime."
        ) from exc
    return vertexai.Client(
        project=args.project,
        location=args.region,
        credentials=credentials_for_account(args.account),
        http_options={"api_version": "v1beta1"},
    )


@dataclass(frozen=True)
class RuntimeSnapshot:
    name: str
    display_name: str
    update_time: str
    description: str | None
    labels: dict[str, str]
    identity_type: str
    effective_identity_present: bool
    agent_framework: str
    service_account: str | None
    env_values: dict[str, str]
    secret_env_count: int
    min_instances: int | None
    max_instances: int | None
    resource_limits: dict[str, str]
    container_concurrency: int | None
    python_version: str | None
    entrypoint_module: str | None
    entrypoint_object: str | None
    requirements_file: str | None
    class_methods: list[dict[str, Any]]

    @property
    def env_hash(self) -> str:
        return _hash_json(self.env_values)

    @property
    def preserved_env_hash(self) -> str:
        return _hash_json(
            {
                name: value
                for name, value in self.env_values.items()
                if name != RUNTIME_GATE_NAME
            }
        )

    @property
    def class_methods_hash(self) -> str:
        return _hash_json(self.class_methods)

    def safe_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "update_time": self.update_time,
            "description_present": self.description is not None,
            "labels": self.labels,
            "identity_type": self.identity_type,
            "effective_identity_present": self.effective_identity_present,
            "agent_framework": self.agent_framework,
            "service_account_present": self.service_account is not None,
            "environment_names": sorted(self.env_values),
            "environment_values_sha256": self.env_hash,
            "preserved_environment_values_sha256": self.preserved_env_hash,
            "secret_binding_count": self.secret_env_count,
            "scaling": {
                "min_instances": self.min_instances,
                "max_instances": self.max_instances,
                "resource_limits": self.resource_limits,
                "container_concurrency": self.container_concurrency,
            },
            "python_version": self.python_version,
            "entrypoint_module": self.entrypoint_module,
            "entrypoint_object": self.entrypoint_object,
            "requirements_file": self.requirements_file,
            "class_method_count": len(self.class_methods),
            "class_method_names": [
                method.get("name") for method in self.class_methods
            ],
            "class_methods_sha256": self.class_methods_hash,
        }


def _resource_dict(agent: Any) -> dict[str, Any]:
    resource = getattr(agent, "api_resource", agent)
    if hasattr(resource, "model_dump"):
        value = resource.model_dump(mode="json", exclude_none=True)
    elif isinstance(resource, dict):
        value = resource
    else:
        raise DeploymentGuardError("Vertex returned an unsupported runtime resource.")
    if not isinstance(value, dict):
        raise DeploymentGuardError("Vertex returned a malformed runtime resource.")
    return value


def parse_runtime_snapshot(resource: Mapping[str, Any]) -> RuntimeSnapshot:
    spec = resource.get("spec") or {}
    deployment = spec.get("deployment_spec") or {}
    source = spec.get("source_code_spec") or {}
    python_spec = source.get("python_spec") or {}

    env_values: dict[str, str] = {}
    for item in deployment.get("env") or []:
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise DeploymentGuardError("Runtime environment has a malformed value.")
        if name in env_values:
            raise DeploymentGuardError(f"Runtime environment repeats {name}.")
        env_values[name] = value

    class_methods = spec.get("class_methods") or []
    if not isinstance(class_methods, list) or not all(
        isinstance(item, dict) for item in class_methods
    ):
        raise DeploymentGuardError("Runtime operation schemas are malformed.")

    return RuntimeSnapshot(
        name=str(resource.get("name") or ""),
        display_name=str(resource.get("display_name") or ""),
        update_time=str(resource.get("update_time") or ""),
        description=resource.get("description"),
        labels=dict(resource.get("labels") or {}),
        identity_type=str(spec.get("identity_type") or ""),
        effective_identity_present=bool(spec.get("effective_identity")),
        agent_framework=str(spec.get("agent_framework") or ""),
        service_account=spec.get("service_account")
        or deployment.get("service_account"),
        env_values=env_values,
        secret_env_count=len(deployment.get("secret_env") or []),
        min_instances=deployment.get("min_instances"),
        max_instances=deployment.get("max_instances"),
        resource_limits=dict(deployment.get("resource_limits") or {}),
        container_concurrency=deployment.get("container_concurrency"),
        python_version=python_spec.get("version"),
        entrypoint_module=python_spec.get("entrypoint_module"),
        entrypoint_object=python_spec.get("entrypoint_object"),
        requirements_file=python_spec.get("requirements_file"),
        class_methods=[dict(item) for item in class_methods],
    )


def validate_pre_update_snapshot(snapshot: RuntimeSnapshot) -> None:
    checks = {
        "resource name": (snapshot.name, APPROVED_RESOURCE_NAME),
        "display name": (snapshot.display_name, APPROVED_DISPLAY_NAME),
        "identity type": (snapshot.identity_type, "AGENT_IDENTITY"),
        "agent framework": (snapshot.agent_framework, "google-adk"),
        "service account": (snapshot.service_account, None),
        "secret binding count": (snapshot.secret_env_count, 0),
        "min instances": (snapshot.min_instances, 1),
        "max instances": (snapshot.max_instances, 10),
        "resource limits": (
            snapshot.resource_limits,
            {"cpu": "4", "memory": "8Gi"},
        ),
        "container concurrency": (snapshot.container_concurrency, 9),
        "entrypoint module": (
            snapshot.entrypoint_module,
            EXPECTED_ENTRYPOINT_MODULE,
        ),
        "entrypoint object": (
            snapshot.entrypoint_object,
            EXPECTED_ENTRYPOINT_OBJECT,
        ),
        "requirements file": (
            snapshot.requirements_file,
            EXPECTED_REQUIREMENTS_FILE,
        ),
        "labels": (snapshot.labels, {}),
    }
    mismatches = [
        f"{name}: expected {expected!r}, got {actual!r}"
        for name, (actual, expected) in checks.items()
        if actual != expected
    ]
    if not snapshot.effective_identity_present:
        mismatches.append("effective Agent Identity is missing")
    environment_names = frozenset(snapshot.env_values)
    is_legacy_baseline = (
        environment_names == EXPECTED_ENV_NAMES
        and snapshot.python_version == "3.14"
        and RUNTIME_GATE_NAME not in snapshot.env_values
    )
    is_hardened_baseline = (
        environment_names == EXPECTED_ENV_NAMES | {RUNTIME_GATE_NAME}
        and snapshot.python_version == APPROVED_PYTHON_VERSION
        and snapshot.env_values.get(RUNTIME_GATE_NAME) == RUNTIME_GATE_VALUE
    )
    if not (is_legacy_baseline or is_hardened_baseline):
        mismatches.append(
            "runtime baseline must be either legacy Python 3.14 without the "
            f"{RUNTIME_GATE_NAME} gate or hardened Python "
            f"{APPROVED_PYTHON_VERSION} with {RUNTIME_GATE_NAME}="
            f"{RUNTIME_GATE_VALUE!r}; got Python {snapshot.python_version!r}, "
            f"environment names {environment_names!r}, and gate value "
            f"{snapshot.env_values.get(RUNTIME_GATE_NAME)!r}"
        )
    if not snapshot.class_methods:
        mismatches.append("operation schemas are empty")
    if mismatches:
        raise DeploymentGuardError(
            "Runtime configuration drift detected: " + "; ".join(mismatches)
        )


def _list_exact_target(client: Any) -> tuple[RuntimeSnapshot, int]:
    resources = [_resource_dict(item) for item in client.agent_engines.list()]
    if len(resources) != EXPECTED_RUNTIME_COUNT:
        raise DeploymentGuardError(
            f"Expected {EXPECTED_RUNTIME_COUNT} runtimes, found {len(resources)}."
        )
    exact = [item for item in resources if item.get("name") == APPROVED_RESOURCE_NAME]
    by_display_name = [
        item
        for item in resources
        if item.get("display_name") == APPROVED_DISPLAY_NAME
    ]
    if len(exact) != 1 or len(by_display_name) != 1 or exact[0] is not by_display_name[0]:
        raise DeploymentGuardError(
            "The approved runtime ID and display name are not one unique resource."
        )
    snapshot = parse_runtime_snapshot(exact[0])
    return snapshot, len(resources)


def run_preflight(
    args: argparse.Namespace,
    *,
    client_factory: Callable[[argparse.Namespace], Any] = make_vertex_client,
) -> tuple[dict[str, Any], RuntimeSnapshot, Any]:
    validate_approved_arguments(args)
    git_state = validate_git_release_state(args.commit)
    requirements = validate_runtime_requirements(Path(args.requirements_file))
    source_package_closure = validate_source_package_closure()
    client = client_factory(args)
    snapshot, runtime_count = _list_exact_target(client)
    validate_pre_update_snapshot(snapshot)
    result = {
        "status": "PASS",
        "checked_at": _now(),
        "git": git_state,
        "requirements": requirements,
        "source_package_closure": source_package_closure,
        "runtime_count": runtime_count,
        "target": snapshot.safe_dict(),
        "planned_change": {
            "python_version": APPROVED_PYTHON_VERSION,
            "environment_gate": RUNTIME_GATE_NAME,
            "environment_gate_value": RUNTIME_GATE_VALUE,
            "environment_gate_already_present": (
                snapshot.env_values.get(RUNTIME_GATE_NAME) == RUNTIME_GATE_VALUE
            ),
            "action": "update-only",
        },
    }
    return result, snapshot, client


def build_update_config_kwargs(snapshot: RuntimeSnapshot) -> dict[str, Any]:
    env_values = dict(snapshot.env_values)
    env_values[RUNTIME_GATE_NAME] = RUNTIME_GATE_VALUE
    kwargs: dict[str, Any] = {
        "display_name": snapshot.display_name,
        "labels": snapshot.labels,
        "source_packages": list(APPROVED_SOURCE_PACKAGES),
        "entrypoint_module": snapshot.entrypoint_module,
        "entrypoint_object": snapshot.entrypoint_object,
        "class_methods": snapshot.class_methods,
        "env_vars": env_values,
        "identity_type": "AGENT_IDENTITY",
        "requirements_file": EXPECTED_REQUIREMENTS_FILE,
        "min_instances": snapshot.min_instances,
        "max_instances": snapshot.max_instances,
        "resource_limits": snapshot.resource_limits,
        "container_concurrency": snapshot.container_concurrency,
        "agent_framework": snapshot.agent_framework,
        "python_version": APPROVED_PYTHON_VERSION,
    }
    if snapshot.description is not None:
        kwargs["description"] = snapshot.description
    return kwargs


def start_exact_update(client: Any, snapshot: RuntimeSnapshot) -> Any:
    """Start one update operation; there is deliberately no create branch."""
    config = build_update_config_kwargs(snapshot)
    api_config = client.agent_engines._create_config(
        mode="update",
        agent=None,
        identity_type=config["identity_type"],
        display_name=config["display_name"],
        description=config.get("description"),
        env_vars=config["env_vars"],
        service_account=None,
        min_instances=config["min_instances"],
        max_instances=config["max_instances"],
        resource_limits=config["resource_limits"],
        container_concurrency=config["container_concurrency"],
        labels=config["labels"],
        class_methods=config["class_methods"],
        source_packages=config["source_packages"],
        entrypoint_module=config["entrypoint_module"],
        entrypoint_object=config["entrypoint_object"],
        requirements_file=config["requirements_file"],
        agent_framework=config["agent_framework"],
        python_version=config["python_version"],
    )
    return client.agent_engines._update(
        name=APPROVED_RESOURCE_NAME,
        config=api_config,
    )


def run_deploy(args: argparse.Namespace) -> dict[str, Any]:
    operation_file = Path(args.operation_file).resolve()
    _require_evidence_path(operation_file)
    if operation_file.exists():
        raise DeploymentGuardError(
            "Operation file already exists; refusing a second deployment attempt."
        )

    preflight, snapshot, client = run_preflight(args)
    state: dict[str, Any] = {
        "schema_version": 1,
        "phase": "reserved",
        "reserved_at": _now(),
        "deployment_attempts": 0,
        "source_commit": args.commit,
        "target_resource": APPROVED_RESOURCE_NAME,
        "display_name": APPROVED_DISPLAY_NAME,
        "project": APPROVED_PROJECT,
        "region": APPROVED_REGION,
        "runtime_count_before": preflight["runtime_count"],
        "requirements": preflight["requirements"],
        "pre_update": snapshot.safe_dict(),
    }
    _atomic_write_json(operation_file, state)

    state["deployment_attempts"] = 1
    state["attempted_at"] = _now()
    try:
        operation = start_exact_update(client, snapshot)
    except Exception as exc:
        state["phase"] = "start_failed_or_uncertain"
        state["error_type"] = type(exc).__name__
        state["error"] = str(exc)[:1000]
        _atomic_write_json(operation_file, state)
        raise

    operation_name = str(getattr(operation, "name", ""))
    if not operation_name:
        state["phase"] = "start_failed_or_uncertain"
        state["error"] = "Vertex returned no operation name."
        _atomic_write_json(operation_file, state)
        raise DeploymentGuardError("Vertex returned no deployment operation name.")

    state["phase"] = "started"
    state["operation_name"] = operation_name
    _atomic_write_json(operation_file, state)
    return {
        "status": "STARTED",
        "started_at": state["attempted_at"],
        "operation_name": operation_name,
        "target_resource": APPROVED_RESOURCE_NAME,
        "deployment_attempts": 1,
        "operation_file": str(operation_file),
    }


def _operation_error(operation: Any) -> dict[str, Any] | None:
    error = getattr(operation, "error", None)
    if not error:
        return None
    if hasattr(error, "model_dump"):
        value = error.model_dump(mode="json", exclude_none=True)
        if isinstance(value, dict):
            return {
                "code": value.get("code"),
                "message": str(value.get("message") or "")[:1000],
            }
    return {"code": None, "message": str(error)[:1000]}


def _operation_response_name(operation: Any) -> str | None:
    response = getattr(operation, "response", None)
    if response is None:
        return None
    if hasattr(response, "model_dump"):
        response = response.model_dump(mode="json", exclude_none=True)
    if isinstance(response, dict):
        value = response.get("name")
        return str(value) if value else None
    return None


def validate_post_update_snapshot(
    snapshot: RuntimeSnapshot,
    operation_state: Mapping[str, Any],
    runtime_count: int,
) -> None:
    pre_update = operation_state.get("pre_update") or {}
    old_env = {
        name: value
        for name, value in snapshot.env_values.items()
        if name != RUNTIME_GATE_NAME
    }
    checks = {
        "resource name": (snapshot.name, APPROVED_RESOURCE_NAME),
        "display name": (snapshot.display_name, APPROVED_DISPLAY_NAME),
        "runtime count": (runtime_count, operation_state.get("runtime_count_before")),
        "identity type": (snapshot.identity_type, "AGENT_IDENTITY"),
        "effective Agent Identity": (snapshot.effective_identity_present, True),
        "service account": (snapshot.service_account, None),
        "secret binding count": (snapshot.secret_env_count, 0),
        "environment names": (
            frozenset(snapshot.env_values),
            EXPECTED_ENV_NAMES | {RUNTIME_GATE_NAME},
        ),
        "runtime gate": (
            snapshot.env_values.get(RUNTIME_GATE_NAME),
            RUNTIME_GATE_VALUE,
        ),
        "preserved environment values": (
            _hash_json(old_env),
            pre_update.get("preserved_environment_values_sha256"),
        ),
        "min instances": (snapshot.min_instances, 1),
        "max instances": (snapshot.max_instances, 10),
        "resource limits": (
            snapshot.resource_limits,
            {"cpu": "4", "memory": "8Gi"},
        ),
        "container concurrency": (snapshot.container_concurrency, 9),
        "Python version": (snapshot.python_version, APPROVED_PYTHON_VERSION),
        "entrypoint module": (
            snapshot.entrypoint_module,
            EXPECTED_ENTRYPOINT_MODULE,
        ),
        "entrypoint object": (
            snapshot.entrypoint_object,
            EXPECTED_ENTRYPOINT_OBJECT,
        ),
        "requirements file": (
            snapshot.requirements_file,
            EXPECTED_REQUIREMENTS_FILE,
        ),
        "operation schemas": (
            snapshot.class_methods_hash,
            pre_update.get("class_methods_sha256"),
        ),
        "labels": (snapshot.labels, pre_update.get("labels")),
    }
    mismatches = [
        f"{name}: expected {expected!r}, got {actual!r}"
        for name, (actual, expected) in checks.items()
        if actual != expected
    ]
    if snapshot.update_time == pre_update.get("update_time"):
        mismatches.append("runtime update timestamp did not advance")
    if mismatches:
        raise DeploymentGuardError(
            "Post-deployment verification failed: " + "; ".join(mismatches)
        )


def _load_operation_state(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    path = Path(args.operation_file).resolve()
    _require_evidence_path(path)
    state = _read_json(path)
    expected = {
        "source_commit": args.commit,
        "target_resource": APPROVED_RESOURCE_NAME,
        "project": APPROVED_PROJECT,
        "region": APPROVED_REGION,
        "deployment_attempts": 1,
    }
    for key, value in expected.items():
        if state.get(key) != value:
            raise DeploymentGuardError(f"Operation state has unexpected {key}.")
    return path, state


def run_status(args: argparse.Namespace) -> dict[str, Any]:
    validate_approved_arguments(args)
    validate_git_release_state(args.commit)
    operation_file, state = _load_operation_state(args)
    if state.get("phase") not in {"started", "running", "completed"}:
        raise DeploymentGuardError(
            f"Operation state is not monitorable: {state.get('phase')!r}."
        )
    if state.get("phase") == "completed":
        return {
            "status": "SUCCEEDED",
            "phase": "completed",
            "operation_name": state.get("operation_name"),
            "post_update": state.get("post_update"),
        }

    client = make_vertex_client(args)
    operation = client.agent_engines._get_agent_operation(
        operation_name=state["operation_name"]
    )
    checked_at = _now()
    state["last_checked_at"] = checked_at
    if not bool(getattr(operation, "done", False)):
        state["phase"] = "running"
        _atomic_write_json(operation_file, state)
        return {
            "status": "RUNNING",
            "checked_at": checked_at,
            "operation_name": state["operation_name"],
        }

    error = _operation_error(operation)
    if error:
        state["phase"] = "failed"
        state["completed_at"] = checked_at
        state["operation_error"] = error
        _atomic_write_json(operation_file, state)
        return {
            "status": "FAILED",
            "checked_at": checked_at,
            "operation_name": state["operation_name"],
            "error": error,
        }

    response_name = _operation_response_name(operation)
    if response_name and response_name != APPROVED_RESOURCE_NAME:
        state["phase"] = "verification_failed"
        state["error"] = "Operation response referenced the wrong resource."
        _atomic_write_json(operation_file, state)
        raise DeploymentGuardError(state["error"])

    snapshot, runtime_count = _list_exact_target(client)
    validate_post_update_snapshot(snapshot, state, runtime_count)
    state["phase"] = "completed"
    state["completed_at"] = checked_at
    state["post_update"] = snapshot.safe_dict()
    _atomic_write_json(operation_file, state)
    return {
        "status": "SUCCEEDED",
        "checked_at": checked_at,
        "operation_name": state["operation_name"],
        "post_update": state["post_update"],
    }


def _event_dict(event: Any) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        value = event.model_dump(mode="json", exclude_none=True)
    elif isinstance(event, dict):
        value = event
    else:
        return {"text": str(event)}
    return value if isinstance(value, dict) else {"text": str(value)}


def _collect_text(value: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "text" and isinstance(item, str):
                texts.append(item)
            else:
                texts.extend(_collect_text(item))
    elif isinstance(value, list):
        for item in value:
            texts.extend(_collect_text(item))
    return texts


def _contains_tool_call(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key in {"function_call", "functionCall", "tool_call", "toolCall"}
            or _contains_tool_call(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_tool_call(item) for item in value)
    return False


async def _query_policy_smoke(agent: Any, user_id: str) -> tuple[str, int, bool]:
    events: list[dict[str, Any]] = []
    async for event in agent.async_stream_query(
        message=SMOKE_PROMPT,
        user_id=user_id,
    ):
        events.append(_event_dict(event))
    text = "\n".join(part.strip() for part in _collect_text(events) if part.strip())
    return text, len(events), any(_contains_tool_call(event) for event in events)


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    validate_approved_arguments(args)
    validate_git_release_state(args.commit)
    operation_file, state = _load_operation_state(args)
    if state.get("phase") not in {"completed", "smoke_passed"}:
        raise DeploymentGuardError("Deployment must verify successfully before smoke testing.")
    if state.get("phase") == "smoke_passed":
        return dict(state["smoke"])

    client = make_vertex_client(args)
    snapshot, runtime_count = _list_exact_target(client)
    validate_post_update_snapshot(snapshot, state, runtime_count)
    agent = client.agent_engines.get(name=APPROVED_RESOURCE_NAME)
    user_id = f"release-policy-smoke-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    text, event_count, tool_call_seen = asyncio.run(
        _query_policy_smoke(agent, user_id)
    )
    lowered = text.lower()
    refusal_language = any(
        phrase in lowered
        for phrase in ("not allowed", "not return", "reject", "not permitted")
    )
    if not text or "synthetic" not in lowered or "tender" not in lowered:
        raise DeploymentGuardError("Policy smoke response omitted required policy terms.")
    if not refusal_language:
        raise DeploymentGuardError("Policy smoke response did not refuse disallowed leads.")
    if tool_call_seen:
        raise DeploymentGuardError("Policy smoke unexpectedly invoked a tool.")

    result = {
        "status": "PASS",
        "checked_at": _now(),
        "target_resource": APPROVED_RESOURCE_NAME,
        "event_count": event_count,
        "tool_call_seen": False,
        "response_text": text[:2000],
    }
    state["phase"] = "smoke_passed"
    state["smoke"] = result
    _atomic_write_json(operation_file, state)
    return result


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--account", default=APPROVED_ACCOUNT)
    parser.add_argument(
        "--requirements-file",
        default=EXPECTED_REQUIREMENTS_FILE,
    )
    parser.add_argument("--output")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("preflight", "deploy", "status", "smoke"):
        command = commands.add_parser(name)
        _add_common_arguments(command)
        if name in {"deploy", "status", "smoke"}:
            command.add_argument("--operation-file", required=True)
    return root


def _write_optional_output(args: argparse.Namespace, result: Mapping[str, Any]) -> None:
    if args.output:
        _atomic_write_json(Path(args.output), result)


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "preflight":
            result, _, _ = run_preflight(args)
        elif args.command == "deploy":
            result = run_deploy(args)
        elif args.command == "status":
            result = run_status(args)
        elif args.command == "smoke":
            result = run_smoke(args)
        else:  # pragma: no cover - argparse enforces the command set.
            raise DeploymentGuardError(f"Unsupported command: {args.command}")
        _write_optional_output(args, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if result.get("status") == "FAILED" else 0
    except DeploymentGuardError as exc:
        result = {
            "status": "BLOCKED",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        _write_optional_output(args, result)
        print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
        return 2
    except Exception as exc:  # Fail closed without an automatic retry.
        result = {
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }
        _write_optional_output(args, result)
        print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
