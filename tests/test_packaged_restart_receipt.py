"""Closed restart-browser protocol checks; no server, model or browser launch."""
import importlib.util
import json
from pathlib import Path

import pytest
from prompt_enhancer.application import owned_process
from prompt_enhancer.application.owned_process import OwnedProcessResult, OwnedProcessRunError


@pytest.fixture
def runner(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("no process execution")
    monkeypatch.setattr(owned_process, "start_owned_process", forbidden)
    monkeypatch.setattr(owned_process, "run_owned_process", forbidden)
    support = Path(__file__).parent / "support"
    monkeypatch.syspath_prepend(str(support))
    spec = importlib.util.spec_from_file_location("restart_runner", support / "packaged_streaming_runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def success(runner):
    return {"contract": "packaged-agent-restart-probe.v1", "error_code": None,
            **{key: True for key in runner._RESTART_BROWSER_BOOLS},
            **{key: 0 for key in runner._RESTART_BROWSER_COUNTS},
            "user_messages": 3, "complete_replies": 2, "stopped_replies": 1,
            "resume_requests": 1, "auth_responses": 2}


def encode(value):
    return b"PACKAGED_AGENT_RESTART_PROBE=" + json.dumps(value).encode() + b"\n"


def test_valid(runner):
    value = runner._restart_browser_receipt(encode(success(runner)))
    assert runner._restart_browser_passed(value)


@pytest.mark.parametrize("field,value", [("user_messages", 2), ("complete_replies", 3), ("stopped_replies", 0),
    ("resume_requests", 2), ("auth_responses", 0), ("forbidden_mutations", 1), ("external_requests", 1),
    ("page_errors", 1), ("server_failures", 1), ("draft_cleared", False), ("resumed_readonly", False),
    ("browser_closed", False), ("reopened_verified", False)])
def test_inconsistent_success_refused(runner, field, value):
    parsed = runner._restart_browser_receipt(encode({**success(runner), field: value}))
    assert not runner._restart_browser_passed(parsed)


@pytest.mark.parametrize("field,value", [("user_messages", True), ("resume_requests", -1), ("auth_responses", 1001),
    ("history_verified", 1), ("error_code", "arbitrary-canary"), ("extra", "arbitrary-canary")])
def test_closed_types(runner, field, value):
    assert runner._restart_browser_receipt(encode({**success(runner), field: value})) is None


def test_duplicate_multiline_oversize_refused(runner):
    raw = encode(success(runner)).rstrip()
    for malformed in (raw + b"\nraw-canary", raw[:-1] + b',"passed":true}', b"x" * 16385):
        assert runner._restart_browser_receipt(malformed) is None


def test_error_receipt_remains_safe(runner):
    value = {**success(runner), "passed": False, "error_code": "composer_guard_failed"}
    assert runner._restart_browser_receipt(encode(value)) == value
    assert not runner._restart_browser_passed(value)


def invoke_browser(runner, monkeypatch, result):
    node = Path("D:/synthetic/node.exe")
    script = Path("D:/synthetic/restart.mjs")
    browser = Path("D:/synthetic/headless.exe")
    root = Path("D:/synthetic/fixture")
    environment = {"SYNTHETIC": "retained", "PE_PACKAGED_BASE_URL": "incorrect", "PE_PACKAGED_BROWSER_EXECUTABLE": "incorrect"}
    original = dict(environment)
    def mocked(argv, **kwargs):
        assert argv == (str(node), str(script))
        assert kwargs == {"cwd": root, "env": {"SYNTHETIC": "retained", "PE_PACKAGED_BASE_URL": "http://127.0.0.1:12345",
                          "PE_PACKAGED_BROWSER_EXECUTABLE": str(browser)},
                          "stdout_limit": 16384, "stderr_limit": 16384, "timeout": 90, "maximum_active_processes": 8}
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(runner, "run_owned_process", mocked)
    report = {key: False for key in runner._RESTART_BROWSER_FLAGS}
    try:
        runner._restart_browser(node, script, browser, environment, root, 12345, report)
    except runner._ProbeFailure:
        report["caught_failure"] = True
    assert environment == original
    return report


def test_browser_wiring_success(runner, monkeypatch):
    report = invoke_browser(runner, monkeypatch, OwnedProcessResult(returncode=0, stdout=encode(success(runner)), stderr=b""))
    assert report["restart_browser_verified"] is True
    assert report["restart_browser_cleanup_confirmed"] is True
    assert report["restart_browser_receipt"] == success(runner)


@pytest.mark.parametrize("mode", ["nonzero", "stderr", "malformed"])
def test_browser_wiring_failure(runner, monkeypatch, mode):
    result = OwnedProcessResult(returncode=1 if mode == "nonzero" else 0,
                               stdout=b"malformed" if mode == "malformed" else encode(success(runner)),
                               stderr=b"synthetic" if mode == "stderr" else b"")
    report = invoke_browser(runner, monkeypatch, result)
    assert report["caught_failure"] is True and report["restart_browser_verified"] is False
    assert report["restart_browser_cleanup_confirmed"] is True


@pytest.mark.parametrize("code,cleanup", [("owned_process_timeout", True), ("owned_process_stdout_limit", True),
    ("owned_process_stderr_limit", True), ("owned_process_cleanup_unconfirmed", False)])
def test_browser_owned_failure_flags(runner, monkeypatch, code, cleanup):
    report = invoke_browser(runner, monkeypatch, OwnedProcessRunError(code))
    assert report["caught_failure"] is True and report["restart_browser_verified"] is False
    assert report["restart_browser_cleanup_confirmed"] is cleanup


def test_missing_restart_script_refused_before_launch(runner, monkeypatch):
    monkeypatch.setattr(runner, "_checked_file", lambda path: path)
    monkeypatch.setattr(runner, "_safe_external_root", lambda path: path)
    path = Path("D:/synthetic/input")
    report = runner.probe(path, path, "a" * 64, path, path, path, path)
    assert report["error_code"] == "probe_inputs_unavailable"
    assert report["launches_started"] == 0


def test_final_success_requires_both_browser_flags(runner):
    report = {key: True for key in (*runner._RESTART_FLAGS, *runner._RESTART_BROWSER_FLAGS)}
    report.update(streaming_phase_passed=True, error_code=None, launches_started=2, launches_ready=2, browser_auth_sessions=2)
    assert runner._complete_passed(report)
    for key in runner._RESTART_BROWSER_FLAGS:
        assert not runner._complete_passed({**report, key: False})
        assert not runner._complete_passed({name: value for name, value in report.items() if name != key})
