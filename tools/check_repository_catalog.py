#!/usr/bin/env python3
"""Validate repository catalog structure and Business_Intel source coverage."""

from __future__ import annotations

import ast
import json
import re
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog" / "repository.catalog.v1.json"
PROJECTION_PATH = ROOT / "docs" / "REPOSITORY_CATALOG.md"
AGENT_ROOTS = (ROOT / "sl_trigger_leads", ROOT / "uk_ie_d365_leads")
ALLOWED_KINDS = {
    "application",
    "website",
    "agent_app",
    "agent",
    "service",
    "library",
    "cli",
    "workflow",
    "data_store",
    "integration",
    "deployment",
    "external_resource",
    "documentation_set",
    "test_suite",
    "historical",
}
ALLOWED_CONFIDENCE = {"verified", "observed", "candidate", "unknown"}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\b(?:ghp|github_pat|xox[baprs])[-_A-Za-z0-9]{12,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b"),
)


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def relative_path_is_safe(value: str) -> bool:
    if not value or value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", value):
        return False
    return ".." not in PurePosixPath(value.replace("\\", "/")).parts


def module_level_adk_exports() -> set[str]:
    exports: set[str] = set()
    for source_root in AGENT_ROOTS:
        for path in source_root.rglob("*.py"):
            if "tests" in {part.lower() for part in path.parts}:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            relative = path.relative_to(ROOT).as_posix()
            for node in tree.body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                value = node.value
                if not isinstance(value, ast.Call):
                    continue
                function = value.func
                constructor = (
                    function.id
                    if isinstance(function, ast.Name)
                    else getattr(function, "attr", "")
                )
                if constructor not in {"Agent", "App"}:
                    continue
                targets: list[ast.expr] = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                for target in targets:
                    if isinstance(target, ast.Name):
                        kind = "agent_app" if constructor == "App" else "agent"
                        exports.add(f"{kind}:{relative}:{target.id}".lower())
    return exports


def external_references(components: list[dict[str, Any]]) -> set[str]:
    references: set[str] = set()
    for component in components:
        for resource in component.get("external_resources", []):
            if isinstance(resource, dict) and isinstance(resource.get("reference"), str):
                references.add(resource["reference"])
    return references


def walk_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            strings.extend(walk_strings(child))
    elif isinstance(value, list):
        for child in value:
            strings.extend(walk_strings(child))
    return strings


def validate() -> list[str]:
    errors: list[str] = []
    payload = load_catalog()
    if payload.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    repository = payload.get("repository")
    if not isinstance(repository, dict):
        return ["repository must be an object"]
    if repository.get("id") != "REG-PRJ-BUSINESS-INTEL":
        errors.append("repository id must remain REG-PRJ-BUSINESS-INTEL")
    if repository.get("root") != ".":
        errors.append("repository.root must remain relative")
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        return [*errors, "components must be a non-empty array"]

    ids: set[str] = set()
    discovery_keys: set[str] = set()
    for index, component in enumerate(components):
        prefix = f"components[{index}]"
        if not isinstance(component, dict):
            errors.append(f"{prefix} must be an object")
            continue
        component_id = component.get("id")
        if not isinstance(component_id, str) or not re.fullmatch(
            r"[A-Z0-9][A-Z0-9-]+", component_id
        ):
            errors.append(f"{prefix}.id is invalid")
            continue
        if component_id in ids:
            errors.append(f"duplicate component id {component_id}")
        ids.add(component_id)
        if component.get("kind") not in ALLOWED_KINDS:
            errors.append(f"{component_id} has unsupported kind")
        if component.get("confidence") not in ALLOWED_CONFIDENCE:
            errors.append(f"{component_id} has unsupported confidence")
        for field in ("name", "purpose", "status", "last_verified_at"):
            if not isinstance(component.get(field), str) or not component[field].strip():
                errors.append(f"{component_id}.{field} is required")
        for field in ("locations", "entrypoints"):
            values = component.get(field)
            if not isinstance(values, list):
                errors.append(f"{component_id}.{field} must be an array")
                continue
            for value in values:
                if not isinstance(value, str) or not relative_path_is_safe(value):
                    errors.append(f"{component_id}.{field} contains unsafe path {value!r}")
        component_discovery_keys = component.get("discovery_keys", [])
        if not isinstance(component_discovery_keys, list):
            errors.append(f"{component_id}.discovery_keys must be an array")
            component_discovery_keys = []
        for key in component_discovery_keys:
            if key in discovery_keys:
                errors.append(f"duplicate discovery key {key}")
            discovery_keys.add(str(key))

    for component in components:
        if not isinstance(component, dict) or not isinstance(component.get("id"), str):
            continue
        for dependency in component.get("depends_on", []):
            if dependency not in ids:
                errors.append(f"{component['id']} depends on missing {dependency}")

    missing_exports = sorted(module_level_adk_exports() - discovery_keys)
    if missing_exports:
        errors.append(f"uncataloged exported ADK objects: {missing_exports}")

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packages = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    covered_locations = {
        location
        for component in components
        for location in component.get("locations", [])
        if isinstance(location, str)
    }
    for package in packages:
        if not any(
            location == package or location.startswith(f"{package}/")
            for location in covered_locations
        ):
            errors.append(f"wheel package {package} is not represented")

    for package_manifest in (ROOT / "deploy").glob("*/package.json"):
        deploy_root = package_manifest.parent.relative_to(ROOT).as_posix()
        if not any(
            location == deploy_root or location.startswith(f"{deploy_root}/")
            for location in covered_locations
        ):
            errors.append(f"deployable package {deploy_root} is not represented")

    references = external_references(components)
    deployment = json.loads(
        (ROOT / "deployment_metadata.json").read_text(encoding="utf-8")
    )
    required_references = {
        deployment["remote_agent_runtime_id"],
        "https://slradar.globalapps.world",
        "https://crm.globalapps.world",
        "globalapps-northwind-crm",
        "https://docs.google.com/spreadsheets/d/1nikwNWJ3N5622S_a8l9YQsP_pTLxCLtmezgNmBq4abs/edit",
    }
    missing_references = sorted(required_references - references)
    if missing_references:
        errors.append(f"required external resources are missing: {missing_references}")

    for text in walk_strings(payload):
        if re.match(r"^[A-Za-z]:[\\/]", text):
            errors.append("catalog contains an absolute Windows path")
            break
    for text in walk_strings(payload):
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            errors.append("catalog appears to contain a secret value")
            break

    projection = PROJECTION_PATH.read_text(encoding="utf-8")
    if f"- Components: **{len(components)}**" not in projection:
        errors.append("generated Markdown component count is stale")
    missing_projection_ids = sorted(
        component_id for component_id in ids if f"`{component_id}`" not in projection
    )
    if missing_projection_ids:
        errors.append(f"generated Markdown omits components: {missing_projection_ids}")
    return sorted(set(errors))


def main() -> int:
    try:
        errors = validate()
    except (OSError, KeyError, ValueError, json.JSONDecodeError, SyntaxError) as exc:
        errors = [str(exc)]
    result = {
        "status": "pass" if not errors else "fail",
        "catalog": CATALOG_PATH.relative_to(ROOT).as_posix(),
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
