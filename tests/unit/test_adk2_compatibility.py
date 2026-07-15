"""Deterministic compatibility checks for the ADK 2.x local runtime boundary."""

from __future__ import annotations

import ast
import importlib.metadata
import inspect
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from google.adk.artifacts import GcsArtifactService, InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from packaging.version import Version

from hello_cloud_agent.hello_cloud_agent.agent import app as hello_app
from hello_cloud_agent.hello_cloud_agent.agent import root_agent as hello_root_agent
from sl_trigger_leads.agent import app as sl_app
from sl_trigger_leads.agent import root_agent as sl_root_agent
from sl_trigger_leads.agents.contact_search_agent import contact_search_agent
from uk_ie_d365_leads.agent import app as uk_app
from uk_ie_d365_leads.agent import root_agent as uk_root_agent
from uk_ie_d365_leads.agents.search_agent import d365_search_agent

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_PACKAGES = (
    ROOT / "sl_trigger_leads",
    ROOT / "uk_ie_d365_leads",
    ROOT / "hello_cloud_agent",
)
EXPECTED_MODEL_FILES = {
    "hello_cloud_agent/hello_cloud_agent/agent.py",
    "sl_trigger_leads/agent.py",
    "sl_trigger_leads/agents/contact_resolver_agent.py",
    "sl_trigger_leads/agents/contact_search_agent.py",
    "sl_trigger_leads/agents/email_sender_agent.py",
    "sl_trigger_leads/agents/opportunity_analyst.py",
    "sl_trigger_leads/tools/live_contact_search_tools.py",
    "uk_ie_d365_leads/agent.py",
    "uk_ie_d365_leads/agents/classification_reviewer_agent.py",
    "uk_ie_d365_leads/agents/end_customer_extractor_agent.py",
    "uk_ie_d365_leads/agents/opportunity_vetter_agent.py",
    "uk_ie_d365_leads/agents/report_composer_agent.py",
    "uk_ie_d365_leads/agents/search_agent.py",
    "uk_ie_d365_leads/tools/classification_review_tools.py",
    "uk_ie_d365_leads/tools/lead_tools.py",
    "uk_ie_d365_leads/tools/opportunity_vetting_tools.py",
    "uk_ie_d365_leads/tools/report_composer_tools.py",
}
AGENT_RUNTIME_MODULES = (
    "sl_trigger_leads.agent_runtime_app",
    "hello_cloud_agent.agent_runtime_app",
    "hello_cloud_agent.hello_cloud_agent.agent_runtime_app",
)


def _production_sources() -> list[Path]:
    return sorted(path for package in PRODUCTION_PACKAGES for path in package.rglob("*.py"))


def _dotted_name(node: ast.expr | None) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _catches_base_exception(node: ast.expr | None) -> bool:
    if isinstance(node, ast.Tuple):
        return any(_catches_base_exception(item) for item in node.elts)
    return _dotted_name(node).endswith("BaseException")


def test_resolved_dependency_security_floor() -> None:
    assert Version(importlib.metadata.version("google-adk")) >= Version("2.4.0")
    assert Version(importlib.metadata.version("fastapi")) >= Version("0.139.0")
    assert Version(importlib.metadata.version("starlette")) >= Version("1.3.1")


def test_dependency_contract_separates_agent_runtime_extra() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    runtime_extra = project["project"]["optional-dependencies"]["agent-runtime"]

    assert any(item.startswith("google-adk>=2.4.0") for item in dependencies)
    assert any(item.startswith("starlette>=1.3.1") for item in dependencies)
    assert not any("google-cloud-aiplatform" in item for item in dependencies)
    assert any("google-cloud-aiplatform" in item for item in runtime_extra)
    assert any("google-cloud-secret-manager" in item for item in runtime_extra)


def test_agent_app_exports_and_search_tools_remain_compatible() -> None:
    assert sl_app.name == "sl_trigger_leads"
    assert sl_app.root_agent is sl_root_agent
    assert uk_app.name == "uk_ie_d365_leads"
    assert uk_app.root_agent is uk_root_agent
    assert hello_app.name == "hello_cloud_agent"
    assert hello_app.root_agent is hello_root_agent
    assert [tool.name for tool in contact_search_agent.tools] == ["google_search"]
    assert [tool.name for tool in d365_search_agent.tools] == ["google_search"]


@pytest.mark.asyncio
async def test_in_memory_runner_session_and_artifact_interfaces() -> None:
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=sl_app.name,
        user_id="compatibility-user",
        session_id="compatibility-session",
    )
    runner = Runner(app=sl_app, session_service=session_service)

    assert session.id == "compatibility-session"
    assert runner.app_name == "sl_trigger_leads"
    assert isinstance(InMemoryArtifactService(), InMemoryArtifactService)
    inspect.signature(GcsArtifactService).bind(bucket_name="compatibility-bucket")


def test_all_preserved_model_defaults_are_gemini_25_flash() -> None:
    found: dict[str, int] = {}
    for path in _production_sources():
        count = path.read_text(encoding="utf-8").count("gemini-2.5-flash")
        if count:
            found[path.relative_to(ROOT).as_posix()] = count

    assert set(found) == EXPECTED_MODEL_FILES
    assert set(found.values()) == {1}


def test_no_adk2_breaking_patterns_or_experimental_workflow_api() -> None:
    violations: list[str] = []
    for path in _production_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
                "_run_async_impl",
                "generate_content",
            }:
                violations.append(f"{relative}:{node.lineno}: custom ADK execution override")
            elif isinstance(node, ast.ClassDef) and any(
                _dotted_name(base).endswith("BaseAgent") for base in node.bases
            ):
                violations.append(f"{relative}:{node.lineno}: custom BaseAgent subclass")
            elif isinstance(node, ast.ExceptHandler) and _catches_base_exception(node.type):
                violations.append(f"{relative}:{node.lineno}: catches BaseException")
            elif isinstance(node, ast.Call):
                called = _dotted_name(node.func)
                if called.endswith("session.events.append") or called.endswith("enqueue_event"):
                    violations.append(f"{relative}:{node.lineno}: direct ADK event mutation")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif node.module:
                    modules = [node.module]
                if any(module.startswith("google.adk.workflow") for module in modules):
                    violations.append(f"{relative}:{node.lineno}: experimental Workflow API")
                names = {alias.name for alias in node.names}
                if names & {"BaseSessionService", "DatabaseSessionService"}:
                    violations.append(f"{relative}:{node.lineno}: persistent/custom session service")

    assert violations == []


def test_base_exception_handler_detection_includes_tuples() -> None:
    tree = ast.parse("try:\n    pass\nexcept (ValueError, builtins.BaseException):\n    pass\n")
    handler = next(node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler))

    assert _catches_base_exception(handler.type)


@pytest.mark.parametrize("module_name", AGENT_RUNTIME_MODULES)
def test_agent_runtime_imports_fail_closed_without_opt_in(module_name: str) -> None:
    env = os.environ.copy()
    for name in (
        "BT_ENABLE_AGENT_RUNTIME",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_PROJECT_ID",
        "GCLOUD_PROJECT",
    ):
        env.pop(name, None)

    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert "Agent Runtime is disabled for this local-only build" in result.stderr
    assert "resourcemanager" not in result.stderr.lower()
    assert "permission_denied" not in result.stderr.lower()
