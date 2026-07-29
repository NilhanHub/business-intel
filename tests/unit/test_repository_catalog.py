from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "check_repository_catalog.py"
SPEC = importlib.util.spec_from_file_location("check_repository_catalog", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_repository_catalog_covers_current_source() -> None:
    assert MODULE.validate() == []


def test_exported_adk_objects_are_all_cataloged() -> None:
    payload = MODULE.load_catalog()
    keys = {
        key
        for component in payload["components"]
        for key in component.get("discovery_keys", [])
    }
    assert MODULE.module_level_adk_exports() <= keys
