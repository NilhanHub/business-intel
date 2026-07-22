"""Regression coverage for the exact-target Agent Runtime release helper."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from business_intel import public_http
from sl_trigger_leads.tools import (
    live_contact_search_tools,
    source_fetcher,
    source_health,
)
from tools import deploy_agent_runtime_exact as deploy


def _runtime_resource(
    *,
    name: str = deploy.APPROVED_RESOURCE_NAME,
    display_name: str = deploy.APPROVED_DISPLAY_NAME,
    python_version: str = "3.14",
    include_runtime_gate: bool = False,
) -> dict[str, Any]:
    env = [
        {"name": name, "value": f"preserved-{index}"}
        for index, name in enumerate(sorted(deploy.EXPECTED_ENV_NAMES), start=1)
    ]
    if include_runtime_gate:
        env.append({"name": "BT_ENABLE_AGENT_RUNTIME", "value": "1"})
    return {
        "name": name,
        "display_name": display_name,
        "update_time": "2026-05-10T14:27:48Z",
        "labels": {},
        "spec": {
            "identity_type": "AGENT_IDENTITY",
            "effective_identity": "present-but-never-reported",
            "agent_framework": "google-adk",
            "class_methods": [
                {"name": "async_stream_query", "api_mode": "bidi_stream"},
                {"name": "register_feedback", "api_mode": ""},
            ],
            "source_code_spec": {
                "python_spec": {
                    "version": python_version,
                    "entrypoint_module": deploy.EXPECTED_ENTRYPOINT_MODULE,
                    "entrypoint_object": deploy.EXPECTED_ENTRYPOINT_OBJECT,
                    "requirements_file": deploy.EXPECTED_REQUIREMENTS_FILE,
                }
            },
            "deployment_spec": {
                "env": env,
                "secret_env": [],
                "min_instances": 1,
                "max_instances": 10,
                "resource_limits": {"cpu": "4", "memory": "8Gi"},
                "container_concurrency": 9,
            },
        },
    }


def _approved_args(**overrides: Any) -> argparse.Namespace:
    values = {
        "project": deploy.APPROVED_PROJECT,
        "region": deploy.APPROVED_REGION,
        "runtime_id": deploy.APPROVED_RUNTIME_ID,
        "display_name": deploy.APPROVED_DISPLAY_NAME,
        "python_version": deploy.APPROVED_PYTHON_VERSION,
        "account": deploy.APPROVED_ACCOUNT,
        "commit": "a" * 40,
        "requirements_file": deploy.EXPECTED_REQUIREMENTS_FILE,
        "operation_file": "",
        "output": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_runtime_extra_excludes_vertex_evaluation_dependencies() -> None:
    project = (deploy.PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    runtime_line = "google-cloud-aiplatform[agent-engines]>=1.161.0,<2.0.0"

    assert runtime_line in project
    assert "google-cloud-aiplatform[evaluation,agent-engines]" not in project

    result = deploy.validate_runtime_requirements(
        deploy.PROJECT_ROOT / deploy.EXPECTED_REQUIREMENTS_FILE
    )
    assert result["required_versions"]["google-adk"] == "2.4.0"
    assert result["required_versions"]["google-cloud-aiplatform"] == "1.161.0"
    assert result["forbidden_packages_present"] == []


def test_runtime_requirements_are_the_exact_locked_export() -> None:
    result = subprocess.run(
        [
            "uv",
            "export",
            "--extra",
            "agent-runtime",
            "--no-dev",
            "--no-hashes",
            "--no-sources",
            "--no-header",
            "--no-emit-project",
            "--locked",
        ],
        cwd=deploy.PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    canonical = (
        deploy.PROJECT_ROOT / deploy.EXPECTED_REQUIREMENTS_FILE
    ).read_text(encoding="utf-8")
    assert canonical.replace("\r\n", "\n") == result.stdout.replace("\r\n", "\n")


def test_requirement_validation_rejects_unpinned_and_evaluation_packages() -> None:
    with pytest.raises(deploy.DeploymentGuardError, match="not an exact pin"):
        deploy.parse_locked_requirements("google-adk>=2.4.0\n")

    packages = deploy.parse_locked_requirements("litellm==1.85.7\n")
    assert deploy.FORBIDDEN_RUNTIME_PACKAGES & packages.keys() == {"litellm"}


def test_approved_argument_guard_rejects_other_projects() -> None:
    args = _approved_args(project="wrong-project")

    with pytest.raises(deploy.DeploymentGuardError, match="--project"):
        deploy.validate_approved_arguments(args)


def test_pre_update_snapshot_requires_exact_identity_and_configuration() -> None:
    snapshot = deploy.parse_runtime_snapshot(_runtime_resource())
    deploy.validate_pre_update_snapshot(snapshot)

    drifted = deploy.parse_runtime_snapshot(
        _runtime_resource(display_name="business-intel")
    )
    with pytest.raises(deploy.DeploymentGuardError, match="configuration drift"):
        deploy.validate_pre_update_snapshot(drifted)


def test_update_config_preserves_runtime_and_adds_only_gate() -> None:
    snapshot = deploy.parse_runtime_snapshot(_runtime_resource())
    config = deploy.build_update_config_kwargs(snapshot)

    assert config["python_version"] == "3.13"
    assert config["source_packages"] == ["./sl_trigger_leads"]
    assert config["requirements_file"] == deploy.EXPECTED_REQUIREMENTS_FILE
    assert config["identity_type"] == "AGENT_IDENTITY"
    assert config["min_instances"] == 1
    assert config["max_instances"] == 10
    assert config["resource_limits"] == {"cpu": "4", "memory": "8Gi"}
    assert config["container_concurrency"] == 9
    assert config["class_methods"] == snapshot.class_methods
    assert config["env_vars"] == {
        **snapshot.env_values,
        "BT_ENABLE_AGENT_RUNTIME": "1",
    }


def test_exact_target_lookup_refuses_creation_or_ambiguity() -> None:
    target = _runtime_resource()
    others = [
        _runtime_resource(
            name=f"projects/p/locations/l/reasoningEngines/{index}",
            display_name=f"other-{index}",
        )
        for index in range(3)
    ]

    class AgentEngines:
        def list(self) -> Sequence[dict[str, Any]]:
            return [target, *others]

    client = argparse.Namespace(agent_engines=AgentEngines())
    snapshot, count = deploy._list_exact_target(client)
    assert snapshot.name == deploy.APPROVED_RESOURCE_NAME
    assert count == 4

    target_copy = _runtime_resource(
        name="projects/p/locations/l/reasoningEngines/duplicate",
        display_name=deploy.APPROVED_DISPLAY_NAME,
    )
    client.agent_engines.list = lambda: [target, target_copy, *others[:2]]
    with pytest.raises(deploy.DeploymentGuardError, match="not one unique resource"):
        deploy._list_exact_target(client)


def test_start_exact_update_has_no_create_path() -> None:
    calls: list[tuple[str, Any]] = []

    class AgentEngines:
        def _create_config(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(("create_config", kwargs))
            return {"validated": True}

        def _update(self, **kwargs: Any) -> argparse.Namespace:
            calls.append(("update", kwargs))
            return argparse.Namespace(name="operations/one")

        def _create(self, **kwargs: Any) -> None:
            raise AssertionError("create must never be called")

    client = argparse.Namespace(agent_engines=AgentEngines())
    operation = deploy.start_exact_update(
        client,
        deploy.parse_runtime_snapshot(_runtime_resource()),
    )

    assert operation.name == "operations/one"
    assert [name for name, _ in calls] == ["create_config", "update"]
    assert calls[1][1]["name"] == deploy.APPROVED_RESOURCE_NAME
    assert calls[0][1]["mode"] == "update"
    assert calls[0][1]["python_version"] == "3.13"


def test_existing_operation_file_refuses_second_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = tmp_path / "Evidence"
    evidence.mkdir()
    operation_file = evidence / "operation.json"
    operation_file.write_text("{}", encoding="utf-8")
    args = _approved_args(operation_file=str(operation_file))
    monkeypatch.setattr(
        deploy,
        "run_preflight",
        lambda *_args, **_kwargs: pytest.fail("preflight must not run"),
    )

    with pytest.raises(deploy.DeploymentGuardError, match="second deployment"):
        deploy.run_deploy(args)


def test_post_update_requires_preserved_state_and_no_fifth_runtime() -> None:
    before = deploy.parse_runtime_snapshot(_runtime_resource())
    after_data = _runtime_resource(
        python_version="3.13",
        include_runtime_gate=True,
    )
    after_data["update_time"] = "2026-07-16T16:00:00Z"
    after = deploy.parse_runtime_snapshot(after_data)
    state = {
        "runtime_count_before": 4,
        "pre_update": before.safe_dict(),
    }

    deploy.validate_post_update_snapshot(after, state, 4)
    with pytest.raises(deploy.DeploymentGuardError, match="runtime count"):
        deploy.validate_post_update_snapshot(after, state, 5)


class TrackingHTTPResponse:
    status = 404
    reason = "Not Found"

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.was_closed = False

    def close(self) -> None:
        self.was_closed = True

    def getheader(self, _name: str) -> None:
        return None


class TrackingHTTPConnection:
    def __init__(self) -> None:
        self.was_closed = False

    def close(self) -> None:
        self.was_closed = True


@pytest.mark.parametrize(
    "call",
    [
        lambda: source_health.test_source_url("https://example.com"),
        lambda: source_fetcher.fetch_url("https://example.com"),
        lambda: live_contact_search_tools.HunterContactEnrichmentProvider(
            api_key="test-only"
        )._request_json("domain-search", {"domain": "example.invalid"}),
        lambda: live_contact_search_tools._http_get_text(
            "https://example.com", timeout=1
        ),
    ],
)
def test_all_http_error_paths_close_responses(
    call: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = TrackingHTTPResponse()
    connection = TrackingHTTPConnection()

    monkeypatch.setattr(
        public_http,
        "resolve_public_url",
        lambda url, **_kwargs: (
            url,
            (public_http.ipaddress.ip_address("93.184.216.34"),),
        ),
    )
    monkeypatch.setattr(
        public_http,
        "_open_pinned_response",
        lambda *_args, **_kwargs: (response, connection),
    )

    try:
        call()
    except RuntimeError:
        pass

    assert response.was_closed is True
    assert connection.was_closed is True
