"""Synthetic CLI checks for the offline frontend dashboard preparation service."""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest

from prompt_enhancer.application.owned_process import run_owned_process
from prompt_enhancer.infrastructure import frontend_dashboard_preparation as service
from prompt_enhancer.infrastructure.frontend_dashboard_preparation import (
    FrontendDashboardPreparationError,
    PreparedFrontendDashboard,
)
from scripts import prepare_frontend_dashboard as cli


SCRIPT = Path(cli.__file__).resolve()
CANARY_TOKEN = "synthetic-secret-token-canary-0000"
CANARY_DIRECTORY = "synthetic-private-path-canary"
RECEIPT_FIELDS = frozenset({
    "contract", "passed", "release_accepted",
    "manifest_sha256", "manifest_size_bytes", "source_manifest_sha256", "source_manifest_size_bytes",
    "tooling_manifest_sha256", "tooling_manifest_size_bytes", "node_sha256", "node_size_bytes",
    "node_version", "package_lock_sha256", "package_lock_size_bytes", "node_modules_closure_not_pinned",
    "network_isolation_not_proven", "module_inventory_sha256", "module_inventory_size_bytes",
    "module_inventory_complete", "frontend_licence_closure_verified", "package_binding_sha256",
    "package_bindings_present", "package_bindings_missing",
})


def _arguments(root: Path) -> list[str]:
    return [
        "--frontend-root", str(root / "frontend"),
        "--source-manifest", str(root / "source-manifest.json"),
        "--tooling-manifest", str(root / "tooling-manifest.json"),
        "--node-executable", str(root / "node.exe"),
        "--node-sha256", "a" * 64,
        "--node-size-bytes", "4096",
        "--node-version", "22.0.0",
        "--destination", str(root / "output" / "dashboard-group"),
    ]


def _prepared(root: Path, **overrides: object) -> PreparedFrontendDashboard:
    private = root / CANARY_DIRECTORY / "dashboard"
    prepared = PreparedFrontendDashboard(
        private, private / "dashboard-manifest.json",
        "1" * 64, 101, "2" * 64, 102, "3" * 64, 103, "a" * 64, 4096, "22.0.0", "4" * 64, 104,
        module_inventory_sha256="5" * 64, module_inventory_size_bytes=105,
        package_binding_sha256="6" * 64, package_bindings_present=7, package_bindings_missing=1,
    )
    return dataclasses.replace(prepared, **overrides)


def _json(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    captured = capsys.readouterr()
    assert captured.err == ""
    assert len(captured.out) <= 4096 and captured.out.count("\n") == 1
    return json.loads(captured.out)


def _refuse(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(cli, "prepare_frontend_dashboard", lambda **kwargs: calls.append(kwargs))
    return calls


def _raise(failure: BaseException):
    def prepare(**kwargs: object):
        raise failure
    return prepare


def test_success_forwards_exact_flags_and_emits_whitelisted_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    received: dict[str, object] = {}

    def prepare(**kwargs: object) -> PreparedFrontendDashboard:
        received.update(kwargs)
        return _prepared(tmp_path)

    monkeypatch.setattr(cli, "prepare_frontend_dashboard", prepare)
    assert cli.main(_arguments(tmp_path)) == 0
    assert received == {
        "frontend_root": tmp_path / "frontend",
        "source_manifest": tmp_path / "source-manifest.json",
        "tooling_manifest": tmp_path / "tooling-manifest.json",
        "node_executable": tmp_path / "node.exe",
        "node_sha256": "a" * 64,
        "node_size_bytes": 4096,
        "node_version": "22.0.0",
        "destination": tmp_path / "output" / "dashboard-group",
    }
    assert type(received["node_size_bytes"]) is int
    receipt = _json(capsys)
    assert set(receipt) == RECEIPT_FIELDS
    assert receipt == {
        "contract": "frontend-dashboard-preparation.v1", "passed": True, "release_accepted": False,
        "manifest_sha256": "1" * 64, "manifest_size_bytes": 101,
        "source_manifest_sha256": "2" * 64, "source_manifest_size_bytes": 102,
        "tooling_manifest_sha256": "3" * 64, "tooling_manifest_size_bytes": 103,
        "node_sha256": "a" * 64, "node_size_bytes": 4096, "node_version": "22.0.0",
        "package_lock_sha256": "4" * 64, "package_lock_size_bytes": 104,
        "node_modules_closure_not_pinned": True, "network_isolation_not_proven": True,
        "module_inventory_sha256": "5" * 64, "module_inventory_size_bytes": 105,
        "module_inventory_complete": False, "frontend_licence_closure_verified": False,
        "package_binding_sha256": "6" * 64, "package_bindings_present": 7, "package_bindings_missing": 1,
    }


def test_receipt_excludes_private_paths_and_extra_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fields = {field.name: getattr(_prepared(tmp_path), field.name)
              for field in dataclasses.fields(PreparedFrontendDashboard)}
    extra = SimpleNamespace(**fields, private_note=CANARY_TOKEN, output_path=tmp_path / CANARY_DIRECTORY)
    monkeypatch.setattr(cli, "prepare_frontend_dashboard", lambda **kwargs: extra)
    assert cli.main(_arguments(tmp_path)) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    receipt = json.loads(captured.out)
    assert set(receipt) == RECEIPT_FIELDS
    assert {"root", "manifest_path", "private_note", "output_path"}.isdisjoint(receipt)
    for marker in (CANARY_TOKEN, CANARY_DIRECTORY, str(tmp_path), tmp_path.name, "dashboard-manifest.json"):
        assert marker not in captured.out
    assert json.dumps(str(tmp_path))[1:-1] not in captured.out


@pytest.mark.parametrize("flags", [
    {"node_modules_closure_not_pinned": True, "network_isolation_not_proven": True,
     "module_inventory_complete": False, "frontend_licence_closure_verified": False},
    {"node_modules_closure_not_pinned": False, "network_isolation_not_proven": False,
     "module_inventory_complete": True, "frontend_licence_closure_verified": True},
])
def test_limitation_flags_are_copied_verbatim_and_release_is_never_accepted(
    flags: dict[str, bool], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "prepare_frontend_dashboard", lambda **kwargs: _prepared(tmp_path, **flags))
    assert cli.main(_arguments(tmp_path)) == 0
    receipt = _json(capsys)
    assert {name: receipt[name] for name in flags} == flags
    assert receipt["passed"] is True and receipt["release_accepted"] is False


@pytest.mark.parametrize("override", [
    {"manifest_sha256": CANARY_TOKEN},
    {"package_binding_sha256": ""},
    {"node_size_bytes": True},
    {"package_bindings_missing": -1},
    {"module_inventory_size_bytes": "105"},
    {"frontend_licence_closure_verified": 1},
    {"node_version": CANARY_TOKEN},
])
def test_malformed_service_results_fail_closed_without_content(
    override: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fields = {field.name: getattr(_prepared(tmp_path), field.name)
              for field in dataclasses.fields(PreparedFrontendDashboard)}
    fields.update(override)
    monkeypatch.setattr(cli, "prepare_frontend_dashboard", lambda **kwargs: SimpleNamespace(**fields))
    assert cli.main(_arguments(tmp_path)) == 1
    assert _json(capsys) == {"passed": False, "error_code": cli.RECEIPT_INVALID}


def test_missing_service_result_field_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fields = {field.name: getattr(_prepared(tmp_path), field.name)
              for field in dataclasses.fields(PreparedFrontendDashboard)}
    del fields["package_lock_sha256"]
    monkeypatch.setattr(cli, "prepare_frontend_dashboard", lambda **kwargs: SimpleNamespace(**fields))
    assert cli.main(_arguments(tmp_path)) == 1
    assert _json(capsys) == {"passed": False, "error_code": cli.RECEIPT_INVALID}


def _malformed(kind: str, root: Path) -> list[str]:
    arguments = _arguments(root)
    canary = str(root / CANARY_DIRECTORY / CANARY_TOKEN)
    if kind == "empty":
        return []
    if kind == "missing":
        index = arguments.index("--tooling-manifest")
        return arguments[:index] + arguments[index + 2:]
    if kind == "unknown":
        return arguments + ["--environment-file", canary]
    if kind == "abbreviated":
        index = arguments.index("--frontend-root")
        arguments[index:index + 2] = ["--frontend", canary]
        return arguments
    if kind == "repeated":
        return arguments + ["--destination", canary]
    if kind == "positional":
        return arguments + [canary]
    if kind == "help_with_other_arguments":
        return ["--help", "--frontend-root", canary]
    arguments[arguments.index("--node-size-bytes") + 1] = kind.removeprefix("size:")
    return arguments


@pytest.mark.parametrize("kind", [
    "empty", "missing", "unknown", "abbreviated", "repeated", "positional", "help_with_other_arguments",
    "size:", "size:0", "size:-1", "size:+4096", "size:4_096", "size: 4096", "size:4096 ",
    "size:0x1000", "size:4096.0", "size:４０９６", "size:12345678901",
    "size:" + CANARY_TOKEN,
])
def test_invalid_arguments_are_content_free_and_never_reach_service(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _refuse(monkeypatch)
    assert cli.main(_malformed(kind, tmp_path)) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert CANARY_TOKEN not in captured.out and CANARY_DIRECTORY not in captured.out
    assert str(tmp_path) not in captured.out and "usage" not in captured.out
    assert json.loads(captured.out) == {"passed": False, "error_code": cli.CLI_INVALID}
    assert calls == []


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_is_static_usage_only(
    flag: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _refuse(monkeypatch)
    monkeypatch.setattr(sys, "argv", [str(Path("synthetic-launcher") / CANARY_TOKEN), flag])
    assert cli.main() == 0
    captured = capsys.readouterr()
    assert captured.err == "" and captured.out == cli.USAGE
    assert CANARY_TOKEN not in captured.out and calls == []
    for name in ("frontend-root", "source-manifest", "tooling-manifest", "node-executable",
                 "node-sha256", "node-size-bytes", "node-version", "destination"):
        assert "--" + name in cli.USAGE
    assert "not signing" in cli.USAGE and "release acceptance" in cli.USAGE


@pytest.mark.parametrize("message, code", [
    *sorted(cli._SERVICE_ERROR_CODES.items()),
    ("frontend dashboard build failed: module_input_query_unknown", "frontend_dashboard_build_failed"),
])
def test_known_service_failures_map_to_fixed_codes(
    message: str, code: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = FrontendDashboardPreparationError(message)
    error.__cause__ = OSError(str(tmp_path / CANARY_DIRECTORY / CANARY_TOKEN))
    monkeypatch.setattr(cli, "prepare_frontend_dashboard", _raise(error))
    assert cli.main(_arguments(tmp_path)) == 1
    assert _json(capsys) == {"passed": False, "error_code": code}
    assert code in cli.ERROR_CODES


@pytest.mark.parametrize("failure", [
    FrontendDashboardPreparationError("frontend dashboard build failed: " + CANARY_TOKEN),
    FrontendDashboardPreparationError(f"synthetic failure at {CANARY_DIRECTORY}/{CANARY_TOKEN}"),
    FrontendDashboardPreparationError("frontend dashboard command failed", CANARY_TOKEN),
    FrontendDashboardPreparationError(),
    RuntimeError(CANARY_TOKEN),
    OSError(2, CANARY_TOKEN, CANARY_DIRECTORY),
    ValueError(CANARY_TOKEN),
])
def test_unknown_failures_are_sanitized(
    failure: Exception, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "prepare_frontend_dashboard", _raise(failure))
    assert cli.main(_arguments(tmp_path)) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert CANARY_TOKEN not in captured.out and CANARY_DIRECTORY not in captured.out
    assert "Traceback" not in captured.out
    assert json.loads(captured.out) == {"passed": False, "error_code": cli.FALLBACK_ERROR_CODE}


def test_interrupt_is_reported_with_fixed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "prepare_frontend_dashboard", _raise(KeyboardInterrupt(CANARY_TOKEN)))
    assert cli.main(_arguments(tmp_path)) == 130
    assert _json(capsys) == {"passed": False, "error_code": cli.INTERRUPTED}


def test_every_service_failure_message_has_a_fixed_code() -> None:
    source = Path(service.__file__).read_text(encoding="utf-8")
    messages = set(re.findall(r"_fail\('([^']+)'", source))
    assert messages and messages <= set(cli._SERVICE_ERROR_CODES)
    assert cli.FALLBACK_ERROR_CODE not in cli.ERROR_CODES
    assert all(re.fullmatch(r"frontend_dashboard_[a-z_]+", code) for code in cli.ERROR_CODES)


def _child_environment(root: Path) -> dict[str, str]:
    environment = {"TEMP": str(root), "TMP": str(root), "HOME": str(root / "unused-home"),
                   "USERPROFILE": str(root / "unused-home")}
    for name in ("PATH", "SYSTEMROOT", "WINDIR"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    if "SYSTEMROOT" not in environment and (value := os.environ.get("SystemRoot")):
        environment["SYSTEMROOT"] = value
    return environment


@pytest.mark.parametrize("case", ["unknown_option", "missing_inputs", "help"])
def test_real_process_output_is_fixed_without_traceback(case: str, tmp_path: Path) -> None:
    private = tmp_path / CANARY_DIRECTORY
    if case == "unknown_option":
        arguments = ["--frontend-root", str(private), "--synthetic-token", CANARY_TOKEN]
    elif case == "missing_inputs":
        arguments = _arguments(private)
        arguments[arguments.index("--node-version") + 1] = "22.0.0-" + CANARY_TOKEN.replace("-", ".")
    else:
        arguments = ["--help"]
    # A Windows venv sys.executable is a launcher that spawns its base interpreter
    # as an owned child, so the tree needs two slots; elsewhere one is sufficient.
    maximum_active_processes = 2 if os.name == "nt" else 1
    result = run_owned_process(
        (sys.executable, "-I", "-B", str(SCRIPT), *arguments),
        cwd=tmp_path, env=_child_environment(tmp_path),
        stdout_limit=4096, stderr_limit=4096, timeout=60,
        maximum_active_processes=maximum_active_processes,
    )
    assert result.stderr == b""
    text = result.stdout.decode("ascii").replace("\r\n", "\n")
    assert CANARY_TOKEN not in text and CANARY_DIRECTORY not in text and "Traceback" not in text
    assert not private.exists()
    if case == "help":
        assert result.returncode == 0 and text == cli.USAGE
        return
    expected = cli.CLI_INVALID if case == "unknown_option" else "frontend_dashboard_manifest_invalid"
    assert result.returncode == 1
    assert json.loads(text) == {"passed": False, "error_code": expected}
