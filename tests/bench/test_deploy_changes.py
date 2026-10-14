"""Synthetic Git histories distinguish core releases from Bench protocol changes."""

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("deploy_changes", ROOT / "bench/deploy_changes.py")
changes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changes)
SCHEMA = "contracts/enhancement/readiness.schema.json"


def test_every_workflow_trigger_path_is_covered_by_deployment_selection():
    workflow = yaml.safe_load((ROOT / ".github/workflows/bench-deploy.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))
    assert tuple(triggers["push"]["paths"]) == changes.DEPLOY_PATHS


def schema(version="0.1.0", **properties):
    return json.dumps({"properties": {
        "core_version": {"type": "string", "default": version}, **properties,
    }}).encode()


@pytest.mark.parametrize("path", sorted(changes.VERSION_SCHEMAS))
def test_only_generated_core_version_defaults_can_be_ignored(path):
    assert changes.version_metadata_only(path, schema(), schema("0.2.0"))
    assert not changes.version_metadata_only(path, schema(), schema("0.2.0", ready={"type": "boolean"}))


@pytest.mark.parametrize("after", [
    None, b"not-json", b"{}", b"[]", b'{"properties": null}',
    schema(None), schema(3), schema("not-a-version"),
    b'{"properties":{"core_version":{"type":"string"}}}',
])
def test_missing_or_invalid_contracts_cannot_skip_deployment(after):
    assert not changes.version_metadata_only(SCHEMA, schema(), after)


def test_other_schema_defaults_are_protocol_changes():
    assert not changes.version_metadata_only(
        "contracts/enhancement/execute-request.schema.json", schema(), schema("0.2.0"),
    )
    assert not changes.version_metadata_only(
        SCHEMA, schema(timeout={"default": 10}), schema("0.2.0", timeout={"default": 20}),
    )


@pytest.fixture
def history(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, stderr=subprocess.DEVNULL).decode().strip()

    git("init", "--quiet")
    git("config", "user.name", "Example Contributor")
    git("config", "user.email", "contributor@example.com")

    def commit(files):
        for name, value in files.items():
            path = tmp_path / name
            if value is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
        git("add", ".")
        git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Synthetic change")
        return git("rev-parse", "HEAD")

    return tmp_path, commit


def test_version_release_skips_deployment_but_real_protocol_change_selects_it(history):
    root, commit = history
    before = commit({SCHEMA: schema(), "src/example_core.py": b'VERSION = "0.1.0"\n'})
    version = commit({SCHEMA: schema("0.2.0"), "src/example_core.py": b'VERSION = "0.2.0"\n'})
    assert not changes.requires_deployment(before, version, root=root)
    protocol = commit({SCHEMA: schema("0.2.0", capability={"type": "boolean"})})
    assert changes.requires_deployment(version, protocol, root=root)


@pytest.mark.parametrize("path", ["bench/src/example.py", ".github/workflows/bench-deploy.yml"])
def test_runtime_or_deployment_changes_override_a_version_only_schema_edit(history, path):
    root, commit = history
    before = commit({SCHEMA: schema()})
    after = commit({SCHEMA: schema("0.2.0"), path: b"example\n"})
    assert changes.requires_deployment(before, after, root=root)


def test_deleted_contract_and_unavailable_history_select_deployment(history):
    root, commit = history
    before = commit({SCHEMA: schema()})
    after = commit({SCHEMA: None})
    assert changes.requires_deployment(before, after, root=root)
    assert changes.requires_deployment("0" * 40, after, root=root)
    assert changes.requires_deployment("a" * 40, after, root=root)


def test_manual_deployment_remains_available_without_a_diff(monkeypatch, tmp_path):
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(changes, "requires_deployment", lambda *_: pytest.fail("manual deploy needs no diff"))
    changes.main()
    assert output.read_text() == "deploy=true\n"
