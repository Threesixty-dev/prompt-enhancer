"""Keep MCP package installation's version parser in the base runtime closure."""

from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_packaging_is_a_pinned_base_dependency_for_mcp_package_installation() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))

    assert "packaging==26.3" in project["project"]["dependencies"]

    # Keep the established release extra spelling for existing release commands,
    # but do not make the normal MCP runtime depend on an optional extra.
    assert project["project"]["optional-dependencies"]["release"] == []

    root_package = next(
        package for package in lock["package"] if package["name"] == "prompt-enhancer"
    )
    assert any(
        dependency["name"] == "packaging"
        for dependency in root_package["dependencies"]
    )
    locked_requirement = next(
        requirement
        for requirement in root_package["metadata"]["requires-dist"]
        if requirement["name"] == "packaging"
    )
    assert locked_requirement["specifier"] == "==26.3"
    assert "marker" not in locked_requirement
    assert any(
        package["name"] == "packaging" and package["version"] == "26.3"
        for package in lock["package"]
    )
