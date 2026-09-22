"""Pure closed-contract tests for the packaged streaming runner."""

from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import pytest

from prompt_enhancer.application import owned_process


@pytest.fixture
def runner(monkeypatch):
    def forbidden_launch(*_args, **_kwargs):
        pytest.fail("receipt tests must not launch a process")

    monkeypatch.setattr(owned_process, "start_owned_process", forbidden_launch)
    support = Path(__file__).parent / "support"
    monkeypatch.syspath_prepend(str(support))
    spec = importlib.util.spec_from_file_location(
        "synthetic_packaged_streaming_runner", support / "packaged_streaming_runner.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _success():
    return {
        "contract": "packaged-agent-streaming-probe.v1", "passed": True,
        "browser_started": True, "agent_page_loaded": True,
        "projects_created": 1, "chats_created": 1, "retained_chat_verified": True,
        "model_alias_selected": True, "message_send_requests": 3, "stop_requests": 1,
        "model_mutation_requests": 0, "incremental_turns_verified": 2,
        "incremental_deltas_verified": 4, "completed_turns_verified": 2,
        "completed_chunks_verified": 6, "cancellations_verified": 1,
        "composer_ready_after_turns": 3, "reloads": 1, "catalog_reopens": 1,
        "retained_user_messages_verified": 2, "retained_assistant_messages_verified": 2,
        "draft_persistence_claimed": False, "server_restart_claimed": False,
        "external_requests": 0, "page_errors": 0, "server_failures": 0,
        "browser_closed": True, "exception_kind": None, "error_code": None,
    }


def _encode(receipt):
    return bytearray((
        "PACKAGED_AGENT_STREAMING_PROBE="
        + json.dumps(receipt, separators=(",", ":")) + "\n"
    ).encode())


def test_success_receipt_is_exact_and_process_free(runner):
    parsed = runner._browser_receipt(_encode(_success()))
    assert parsed == _success()
    assert runner._browser_receipt_passed(parsed) is True


@pytest.mark.parametrize("field", [
    "projects_created", "message_send_requests", "stop_requests",
    "incremental_deltas_verified", "completed_chunks_verified",
    "composer_ready_after_turns", "retained_assistant_messages_verified",
])
def test_inconsistent_success_counts_fail_closed(runner, field):
    receipt = {**_success(), field: _success()[field] + 1}
    parsed = runner._browser_receipt(_encode(receipt))
    assert parsed == receipt
    assert runner._browser_receipt_passed(parsed) is False


@pytest.mark.parametrize("value", [True, -1, 1001, 1.5, "1", None])
def test_count_types_and_ranges_are_closed(runner, value):
    assert runner._browser_receipt(_encode({**_success(), "reloads": value})) is None


@pytest.mark.parametrize("field", [
    "passed", "browser_started", "model_alias_selected", "draft_persistence_claimed",
    "server_restart_claimed", "browser_closed",
])
def test_boolean_fields_reject_integer_subtypes(runner, field):
    assert runner._browser_receipt(_encode({**_success(), field: 1})) is None


def test_unknown_and_missing_fields_are_rejected(runner):
    assert runner._browser_receipt(_encode({**_success(), "synthetic_extra": 1})) is None
    missing = _success()
    missing.pop("catalog_reopens")
    assert runner._browser_receipt(_encode(missing)) is None


def test_duplicate_fields_are_rejected(runner):
    raw = _encode(_success())
    assert b'"passed":true' in raw
    forged = raw.replace(b'"passed":true', b'"passed":true,"passed":true', 1)
    assert runner._browser_receipt(forged) is None


@pytest.mark.parametrize("transform", [
    lambda raw: b"synthetic diagnostics\n" + raw,
    lambda raw: raw + b"synthetic diagnostics\n",
    lambda raw: raw + raw,
    lambda raw: raw.replace(b"PACKAGED_AGENT_STREAMING_PROBE=", b"OTHER=", 1),
    lambda raw: raw.replace(b',"passed"', b',\n"passed"', 1),
])
def test_multiline_or_nonreceipt_output_is_rejected(runner, transform):
    assert runner._browser_receipt(bytearray(transform(_encode(_success())))) is None


@pytest.mark.parametrize("value", ["new_error", 1, True, {}, []])
def test_error_code_is_allowlisted(runner, value):
    receipt = {**_success(), "passed": False, "error_code": value}
    assert runner._browser_receipt(_encode(receipt)) is None


@pytest.mark.parametrize("value", ["Error", "new_kind", 1, True, {}, []])
def test_exception_kind_is_allowlisted(runner, value):
    receipt = {**_success(), "passed": False, "exception_kind": value}
    assert runner._browser_receipt(_encode(receipt)) is None


def test_allowlisted_failure_parses_but_does_not_pass(runner):
    receipt = {
        **_success(), "passed": False, "browser_closed": False,
        "error_code": "browser_launch_failed", "exception_kind": "playwright_error",
    }
    parsed = runner._browser_receipt(_encode(receipt))
    assert parsed == receipt
    assert runner._browser_receipt_passed(parsed) is False


@pytest.mark.parametrize("field", ["draft_persistence_claimed", "server_restart_claimed"])
def test_unsupported_claims_cannot_pass(runner, field):
    receipt = {**_success(), field: True}
    parsed = runner._browser_receipt(_encode(receipt))
    assert parsed == receipt
    assert runner._browser_receipt_passed(parsed) is False


def test_manifest_hash_is_a_required_content_free_cli_input(runner, capsys):
    result = runner.main([
        "--runtime", "C:/synthetic/runtime",
        "--fixture-root", "C:/synthetic/fixture",
        "--artifact-root", "C:/synthetic/artifacts",
        "--node", "C:/synthetic/node.exe",
        "--script", "C:/synthetic/probe.mjs",
        "--browser-executable", "C:/synthetic/browser.exe",
    ])
    assert result == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out.split("=", 1)[1]) == {"error_code": "invalid_arguments"}


def test_http_timeout_default_and_closed_bounds(runner):
    request = runner._json_request
    assert inspect.signature(request).parameters["timeout_seconds"].default == 1.0
    for value in (0, -1, 20.1, True, "20", None):
        with pytest.raises(runner._ProbeFailure, match="^http_timeout_invalid$"):
            request(1, "GET", "/synthetic", timeout_seconds=value)


def test_only_model_lifecycle_requests_use_extended_timeout(runner):
    source = inspect.getsource(runner.probe)
    assert source.count("timeout_seconds=20") == 2
    assert 'f"/v1/local-models/{_ALIAS}/activate"' in source
    assert 'f"/v1/local-models/{_ALIAS}/deactivate"' in source


def _history():
    return {"events": [
        {"kind": "user", "text": "Synthetic streaming acceptance."},
        {"kind": "assistant", "text": "Synthetic chunk. Synthetic chunk. Synthetic chunk.", "stream_status": "complete"},
        {"kind": "user", "text": "Synthetic cancellation acceptance."},
        {"kind": "assistant", "text": "Synthetic chunk. ", "stream_status": "stopped"},
        {"kind": "user", "text": "Synthetic retained-history acceptance."},
        {"kind": "assistant", "text": "Synthetic chunk. Synthetic chunk. Synthetic chunk.", "stream_status": "complete"},
    ]}


def test_restart_exact_synthetic_history(runner):
    assert runner._history_matches(_history())


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "text", "failed", "tool"])
def test_restart_history_mismatch_rejected(runner, mutation):
    history = _history()
    if mutation == "missing":
        history["events"].pop()
    elif mutation == "duplicate":
        history["events"].append(dict(history["events"][-1]))
    elif mutation == "text":
        history["events"][0]["text"] = "Different synthetic message."
    elif mutation == "failed":
        history["events"][-1]["stream_status"] = "failed"
    else:
        history["events"].append({"kind": "tool_call"})
    assert not runner._history_matches(history)


def _resumed():
    return {"session_id": "session", "model_alias": "synthetic-fixture", "recovered": True,
            "authority_revalidated": False, "pending_approval_id": None,
            "running": False, "closing": False, "stopping": False, "cleanup_unconfirmed": False,
            "settings": {"project_id": "project", "model_alias": "synthetic-fixture",
                         "retention_policy": "local_history", "allow_writes": False,
                         "allow_commands": False, "allow_web": False}}


def test_resume_preserves_alias_without_restoring_authority(runner):
    assert runner._recovered_readonly(_resumed(), "project", "session")


@pytest.mark.parametrize("field", ["allow_writes", "allow_commands", "allow_web"])
def test_resume_refuses_restored_permissions(runner, field):
    resumed = _resumed()
    resumed["settings"][field] = True
    assert not runner._recovered_readonly(resumed, "project", "session")


@pytest.mark.parametrize("field", ["authority_revalidated", "running", "closing", "stopping", "cleanup_unconfirmed"])
def test_resume_refuses_active_authority_or_work(runner, field):
    assert not runner._recovered_readonly({**_resumed(), field: True}, "project", "session")


def test_restart_success_requires_exact_two_launches_and_auths(runner):
    report = {key: True for key in runner._RESTART_FLAGS}
    report.update(launches_started=2, launches_ready=2, browser_auth_sessions=2)
    assert runner._restart_passed(report)
    for field in ("launches_started", "launches_ready", "browser_auth_sessions"):
        for value in (0, 1, 3, True, "2", 2.0):
            assert not runner._restart_passed({**report, field: value})
    for field in runner._RESTART_FLAGS:
        assert not runner._restart_passed({**report, field: False})


@pytest.mark.parametrize("text", ["Synthetic chunk. " * 3, "Synthetic chunk. Synthetic chunk.",
                                  "Synthetic chunk. Synthetic chunk. Synthetic chunk. Synthetic chunk."])
def test_history_requires_exact_canonical_reply(runner, text):
    history = _history()
    history["events"][1]["text"] = text
    assert not runner._history_matches(history)
