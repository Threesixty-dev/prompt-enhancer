"""Synthetic no-process receipt and owned-runner wiring regressions."""
import importlib.util
import json
from pathlib import Path

import pytest
from prompt_enhancer.application import owned_process
from prompt_enhancer.application.owned_process import OwnedProcessResult, OwnedProcessRunError


@pytest.fixture
def runner(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("process launch forbidden in pure tests")
    monkeypatch.setattr(owned_process, "start_owned_process", forbidden)
    monkeypatch.setattr(owned_process, "run_owned_process", forbidden)
    support = Path(__file__).parent / "support"
    monkeypatch.syspath_prepend(str(support))
    spec = importlib.util.spec_from_file_location("workspace_browser_runner", support / "packaged_workspace_browser_runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def success(runner):
    return {"contract": "packaged-agent-workspace-probe.v1", "error_code": None,
            "traversal_response": {"status": 403, "error_category": "path_outside_workspace"},
            "stale_response": {"status": 409, "error_category": "workspace_revision_changed"},
            "file_response": {"status": 200, "error_category": None, "content_present": True,
                              "content_string": True, "content_matches": True},
            **dict.fromkeys(runner._FLAGS, True), **runner._COUNTS}


def encode(value):
    return b"PACKAGED_AGENT_WORKSPACE_PROBE=" + json.dumps(value).encode() + b"\n"


def test_success(runner):
    value = success(runner)
    assert runner._receipt(encode(value)) == value
    assert runner._receipt_passed(value)


@pytest.mark.parametrize("field", sorted({"browser_started", "browser_closed", "file_read", "diff_verified", "apply_disabled",
    "native_refused", "csrf_refused", "traversal_refused", "stale_refused", "discard_reopened",
    "file_unchanged_after_refusal", "fixture_restored", "readonly_session"}))
def test_success_requires_every_flag(runner, field):
    value = success(runner); value[field] = False
    assert runner._receipt(encode(value)) is None


@pytest.mark.parametrize("field", ["projects_created", "chats_created", "previews_created", "apply_attempts",
    "fixture_mutations", "forbidden_mutations", "external_requests", "page_errors", "server_failures"])
@pytest.mark.parametrize("bad", [-1, True, 101, 1.5, None])
def test_counts_closed(runner, field, bad):
    value = success(runner); value[field] = bad
    assert runner._receipt(encode(value)) is None


@pytest.mark.parametrize("field", ["projects_created", "chats_created", "previews_created", "apply_attempts", "fixture_mutations",
    "project_requests", "session_requests", "preview_requests", "apply_requests"])
def test_exact_success_counts(runner, field):
    value = success(runner); value[field] += 1
    assert runner._receipt(encode(value)) is None


@pytest.mark.parametrize("change", [lambda b: b + b"raw\n", lambda b: b.replace(b"\n", b"\r\n"),
    lambda b: b.replace(b'"contract":', b'"contract":"duplicate","contract":'),
    lambda b: b[:-1], lambda b: b"x" * 16385, lambda b: b"\xff\n"])
def test_framing_and_duplicates(runner, change):
    assert runner._receipt(change(encode(success(runner)))) is None


@pytest.mark.parametrize("key,bad", [("extra", "raw"), ("error_code", "arbitrary error"),
    ("error_code", []), ("contract", "wrong"), ("file_read", 1), ("apply_attempts", float("nan"))])
def test_closed_schema(runner, key, bad):
    value = success(runner); value[key] = bad
    assert runner._receipt(encode(value)) is None


def test_closed_failure_retained(runner):
    value = success(runner); value.update(passed=False, error_code="stale_failed", stale_refused=False)
    assert runner._receipt(encode(value)) == value
    assert not runner._receipt_passed(value)


def invoke(runner, tmp_path, monkeypatch, result=None, error=None):
    script = tmp_path / "probe.mjs"; script.touch()
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        if error: raise error
        return result
    monkeypatch.setattr(runner, "run_owned_process", run)
    report = {"browser_verified": False, "browser_cleanup_confirmed": False}
    env = {"PATH": "synthetic", "PE_PACKAGED_BASE_URL": "stale", "PE_PACKAGED_WORKSPACE": "stale"}
    params = (tmp_path / "node.exe", script, tmp_path / "browser.exe", env, tmp_path, 19001, report)
    return calls, report, params


def test_browser_wiring(runner, tmp_path, monkeypatch):
    result = OwnedProcessResult(0, encode(success(runner)), b"")
    calls, report, params = invoke(runner, tmp_path, monkeypatch, result)
    runner._browser(*params)
    args, kwargs = calls[0]
    assert args == (str(tmp_path / "node.exe"), str(tmp_path / "probe.mjs"))
    assert kwargs == {"cwd": tmp_path, "env": {"PATH": "synthetic",
        "PE_PACKAGED_BASE_URL": "http://127.0.0.1:19001",
        "PE_PACKAGED_WORKSPACE": str(tmp_path / "example-workspace"),
        "PE_PACKAGED_BROWSER_EXECUTABLE": str(tmp_path / "browser.exe")},
        "stdout_limit": 16384, "stderr_limit": 16384, "timeout": 90, "maximum_active_processes": 8}
    assert report["browser_verified"] and report["browser_cleanup_confirmed"]


@pytest.mark.parametrize("kind", ["nonzero", "stderr", "malformed"])
def test_browser_bad_result(runner, tmp_path, monkeypatch, kind):
    result = OwnedProcessResult(1 if kind == "nonzero" else 0,
        b"malformed" if kind == "malformed" else encode(success(runner)), b"hidden" if kind == "stderr" else b"")
    _, report, params = invoke(runner, tmp_path, monkeypatch, result)
    with pytest.raises(runner._ProbeFailure, match="browser_failed"): runner._browser(*params)
    assert report["browser_cleanup_confirmed"] and not report["browser_verified"]


@pytest.mark.parametrize("code,clean", [("owned_process_timeout", True), ("owned_process_stdout_limit", True),
    ("owned_process_stderr_limit", True), ("owned_process_cleanup_unconfirmed", False)])
def test_owned_failures(runner, tmp_path, monkeypatch, code, clean):
    _, report, params = invoke(runner, tmp_path, monkeypatch, error=OwnedProcessRunError(code))
    with pytest.raises(runner._ProbeFailure, match="browser_failed"): runner._browser(*params)
    assert report["browser_cleanup_confirmed"] is clean


def test_missing_script_refuses_without_launch(runner, tmp_path):
    with pytest.raises(runner._ProbeFailure, match="probe_inputs_unavailable"):
        runner._browser(tmp_path / "node", tmp_path / "missing", tmp_path / "browser", {}, tmp_path, 19001, {})


@pytest.mark.parametrize("missing", ["health_ok", "browser_verified", "browser_cleanup_confirmed", "server_tree_stopped",
    "server_handles_closed", "server_readers_stopped", "port_released", "fixture_unchanged"])
def test_completion_requires_all_cleanup_and_evidence(runner, missing):
    report = {"error_code": None, **dict.fromkeys(runner._FINAL_FLAGS, True)}
    assert runner._complete(report)
    del report[missing]
    assert not runner._complete(report)


def test_script_contract_and_safety_constants(runner):
    script = (Path(__file__).parents[1] / "frontend/e2e/packaged-agent-workspace-probe.mjs").read_text(encoding="utf-8")
    assert 'session.settings?.[key] === false' in script
    assert '"allow_writes", "allow_commands", "allow_web"' in script
    assert '"user-presence confirmation is unavailable"' in script
    assert 'result.status === 409' in script
    assert 'result.status === 403 && result.body.detail?.code === "path_outside_workspace"' in script
    assert 'response.body.getReader()' in script and 'total > 65536' in script
    assert 'serviceWorkers: "block"' in script
    assert 'screenshot(' not in script and 'storageState' not in script
    assert runner.ORIGINAL.decode()[:-1] in script and runner.CHANGED.decode()[:-1] in script


def test_editor_waits_for_http_and_committed_draft_not_visibility():
    script = (Path(__file__).parents[1] / "frontend/e2e/packaged-agent-workspace-probe.mjs").read_text(encoding="utf-8")
    helper = script.split("async function waitForOriginalEditor(page) {", 1)[1].split("\ntry {", 1)[0]
    assert 'await page.waitForFunction(expected =>' in helper
    assert 'editor !== null && !editor.disabled && editor.value === expected' in helper
    assert 'ORIGINAL, { timeout: 12000 }' in helper
    assert script.count('await waitForOriginalEditor(page);') == 2
    assert 'page.locator(".agent-workspace__tree")' in script
    assert '.getByRole("button", { name: "example.ts", exact: true })' in script
    assert script.index('const openedResponse = page.waitForResponse') < script.index('await fileButton.click();')
    assert script.index('requireThat(openedFile.status() === 200') < script.index('await waitForOriginalEditor(page);')
    assert 'await editor.waitFor({ state: "visible" })' not in script


@pytest.mark.parametrize("phase", ["file_response_failed", "editor_ready_failed"])
def test_closed_file_loading_phase(runner, phase):
    value = success(runner); value.update(passed=False, error_code=phase, file_read=False)
    assert runner._receipt(encode(value)) == value


@pytest.mark.parametrize("status,category,present,string,matches", [
    (403, "workspace_link_or_reparse_refused", False, False, False),
    (409, "workspace_file_changed", False, False, False),
    (200, None, True, True, False), (200, None, True, False, False),
    (422, "other", False, False, False), (200, "invalid_json", False, False, False)])
def test_file_response_closed_diagnostics(runner, status, category, present, string, matches):
    value = success(runner); value.update(passed=False, file_read=False, error_code="file_response_failed")
    value["file_response"] = {"status": status, "error_category": category,
        "content_present": present, "content_string": string, "content_matches": matches}
    assert runner._receipt(encode(value)) == value


@pytest.mark.parametrize("field,bad", [("status", True), ("status", 600), ("status", 99),
    ("status", 200.0), ("status", float("inf")), ("error_category", "private response"),
    ("error_category", []), ("content_present", 1), ("content_string", "true"),
    ("content_matches", None), ("raw_content", "example"), ("path", "example.ts")])
def test_file_diagnostic_rejects_unknown_or_untyped_values(runner, field, bad):
    value = success(runner); value["file_response"][field] = bad
    assert runner._receipt(encode(value)) is None


def test_file_diagnostic_duplicate_keys_rejected(runner):
    raw = encode(success(runner)).replace(b'"status": 200', b'"status": 200,"status": 409')
    assert runner._receipt(raw) is None


def test_file_diagnostic_required_for_success(runner):
    value = success(runner); value["file_response"] = None
    assert runner._receipt(encode(value)) is None


def test_writer_is_scoped_to_mutation_and_closed_before_http():
    script = (Path(__file__).parents[1] / "frontend/e2e/packaged-agent-workspace-probe.mjs").read_text(encoding="utf-8")
    assert 'file = await open(fixture, "r");' in script
    assert 'file = await open(fixture, "r+");' not in script
    writer = script.split("async function writeFixture(text) {", 1)[1].split("async function waitForOriginalEditor", 1)[0]
    assert script.count('await open(fixturePath, "r+")') == 1
    assert 'opened.ino === pinned.ino' in writer and 'opened.dev === pinned.dev' in writer
    assert 'await writer.sync();' in writer and 'finally { await writer.close(); }' in writer
    assert 'await file.write(' not in script and 'await file.sync(' not in script
    assert script.index('await writeFixture(CHANGED);') < script.index('result = await request("POST", "/previews"')
    assert 'await writeFixture(ORIGINAL);' in script


@pytest.mark.parametrize("diagnostic", [None, {"status": 200, "error_category": "other"},
    {"status": 422, "error_category": "path_invalid"}, {"status": 403, "error_category": "other"}])
def test_traversal_requires_exact_outside_workspace_refusal(runner, diagnostic):
    value = success(runner); value["traversal_response"] = diagnostic
    assert runner._receipt(encode(value)) is None
    value.update(passed=False, traversal_refused=False, error_code="refusal_failed")
    assert runner._receipt(encode(value)) == value


@pytest.mark.parametrize("diagnostic", [{"status": True, "error_category": "other"},
    {"status": 600, "error_category": "other"}, {"status": 403, "error_category": "raw text"},
    {"status": 403, "error_category": "other", "raw": "private"},
    {"status": 403, "error_category": ["other"]}])
def test_traversal_diagnostic_is_closed(runner, diagnostic):
    value = success(runner); value["traversal_response"] = diagnostic
    assert runner._receipt(encode(value)) is None


@pytest.mark.parametrize("diagnostic", [None, {"status": 409, "error_category": "workspace_file_changed"},
    {"status": 200, "error_category": "other"}, {"status": 403, "error_category": "workspace_revision_changed"}])
def test_stale_requires_exact_revision_conflict(runner, diagnostic):
    value = success(runner); value["stale_response"] = diagnostic
    assert runner._receipt(encode(value)) is None
    value.update(passed=False, stale_refused=False, error_code="stale_failed")
    assert runner._receipt(encode(value)) == value


@pytest.mark.parametrize("diagnostic", [{"status": True, "error_category": "other"},
    {"status": 409, "error_category": "raw"}, {"status": 409, "error_category": "other", "raw": "text"}])
def test_stale_diagnostic_is_closed(runner, diagnostic):
    value = success(runner); value["stale_response"] = diagnostic
    assert runner._receipt(encode(value)) is None


def test_stale_expectation_matches_editor_revision_boundary():
    root = Path(__file__).parents[1]
    script = (root / "frontend/e2e/packaged-agent-workspace-probe.mjs").read_text(encoding="utf-8")
    editor = (root / "src/prompt_enhancer/application/local_agent_editor.py").read_text(encoding="utf-8")
    routes = (root / "src/prompt_enhancer/interfaces/http/local_agent_routes.py").read_text(encoding="utf-8")
    assert 'result.status === 409 && result.body.detail?.code === "workspace_revision_changed"' in script
    assert 'if not self._matches(current.revision, command.expected_revision):' in editor
    assert 'raise LocalAgentError("workspace_revision_changed")' in editor
    assert '"workspace_revision_changed": 409' in routes
