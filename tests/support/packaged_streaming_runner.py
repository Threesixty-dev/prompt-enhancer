"""Bounded packaged streaming probe using only a reviewed synthetic runtime.

The caller supplies a staged runtime, an externally retained synthetic fixture,
an external task-owned artifact root, and reviewed Node/browser inputs. Child
output, HTTP bodies, paths, tokens, process identifiers, and model ports are
never forwarded. Importing this module never launches a process.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
from pathlib import Path
import stat
import sys
import tempfile
import time

from packaged_chat_probe import _ProbeFailure, _fresh_browser_auth, _json_request
from probe_synthetic_llama_fixture import ProbeFailure as _FixtureFailure, verify_fixture
from packaged_serve_probe import (
    _capture_threads,
    _environment,
    _ephemeral_loopback_port,
    _port_is_released,
)
from prompt_enhancer.application.owned_process import (
    process_tree_exited,
    start_owned_process,
    terminate_owned_process,
    run_owned_process,
    OwnedProcessRunError,
)


_ALIAS = "synthetic-fixture"
_RESTART_FLAGS = ("cold_restart_verified", "restart_history_verified", "restart_authority_reset",
                  "restart_model_not_running", "restart_tree_stopped", "restart_handles_closed",
                  "restart_port_released", "restart_readers_stopped")
_RESTART_BROWSER_FLAGS = ("restart_browser_verified", "restart_browser_cleanup_confirmed")
_RESTART_BROWSER_BOOLS = {"passed", "browser_started", "browser_closed", "history_verified", "resumed_readonly", "draft_cleared", "reopened_verified"}
_RESTART_BROWSER_COUNTS = {"user_messages", "complete_replies", "stopped_replies", "resume_requests", "forbidden_mutations", "external_requests", "page_errors", "server_failures", "auth_responses"}
_RESTART_BROWSER_ERRORS = {"invalid_environment", "browser_launch_failed", "catalog_open_failed", "retained_history_failed", "resume_ui_failed", "composer_guard_failed", "reopen_failed", "browser_cleanup_failed", "request_boundary_failed"}
_BROWSER_BOOLEANS = {
    "passed", "browser_started", "agent_page_loaded", "retained_chat_verified",
    "model_alias_selected", "draft_persistence_claimed", "server_restart_claimed",
    "browser_closed",
}
_BROWSER_COUNTS = {
    "projects_created", "chats_created", "message_send_requests", "stop_requests",
    "model_mutation_requests", "incremental_turns_verified", "incremental_deltas_verified",
    "completed_turns_verified", "completed_chunks_verified", "cancellations_verified",
    "composer_ready_after_turns", "reloads", "catalog_reopens",
    "retained_user_messages_verified", "retained_assistant_messages_verified",
    "external_requests", "page_errors", "server_failures",
}
_BROWSER_ERRORS = {
    "invalid_environment", "browser_launch_failed", "context_create_failed",
    "page_create_failed", "agent_page_unavailable", "project_create_ui_failed",
    "chat_create_ui_failed", "model_selection_failed", "composer_unavailable",
    "first_send_failed", "first_stream_increment_failed", "first_completion_failed",
    "cancellation_send_failed", "cancellation_stream_failed", "cancellation_stop_failed",
    "cancellation_settle_failed", "retained_send_failed", "retained_stream_failed",
    "retained_completion_failed", "reload_reopen_failed", "browser_cleanup_unconfirmed",
    "browser_probe_failed",
}
_RUNNER_ERRORS = {
    "probe_inputs_unavailable", "artifact_root_unsafe", "fixture_manifest_invalid",
    "fixture_hash_mismatch", "unsafe_probe_port", "server_output_limit",
    "server_exited_before_ready", "health_timeout", "browser_auth_unavailable",
    "browser_auth_contract_mismatch", "browser_cookie_contract_mismatch",
    "http_response_over_budget", "http_response_not_json", "http_response_invalid_json",
    "http_response_shape_mismatch", "model_register_failed", "model_register_mismatch",
    "model_activate_failed", "model_activate_mismatch", "child_output_limit",
    "server_exited_during_browser", "browser_probe_failed", "browser_timeout",
    "browser_receipt_invalid", "browser_stderr_not_empty", "model_deactivate_failed",
    "probe_cleanup_unconfirmed",
    "packaged_streaming_probe_failed",
}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _restart_browser_receipt(output):
    prefix = b"PACKAGED_AGENT_RESTART_PROBE="
    raw = bytes(output).strip()
    if len(raw) > 16384 or not raw.startswith(prefix) or b"\n" in raw or b"\r" in raw:
        return None
    try:
        value = json.loads(raw[len(prefix):], object_pairs_hook=_unique_pairs)
        if not isinstance(value, dict) or set(value) != _RESTART_BROWSER_BOOLS | _RESTART_BROWSER_COUNTS | {"contract", "error_code"}:
            return None
        if value["contract"] != "packaged-agent-restart-probe.v1":
            return None
        if any(type(value[key]) is not bool for key in _RESTART_BROWSER_BOOLS):
            return None
        if any(type(value[key]) is not int or not 0 <= value[key] <= 1000 for key in _RESTART_BROWSER_COUNTS):
            return None
        if value["error_code"] is not None and value["error_code"] not in _RESTART_BROWSER_ERRORS:
            return None
        return value
    except (ValueError, TypeError):
        return None


def _restart_browser_passed(value):
    return (value is not None and all(value[key] is True for key in _RESTART_BROWSER_BOOLS)
            and value["error_code"] is None
            and value["user_messages"] == 3 and value["complete_replies"] == 2
            and value["stopped_replies"] == 1 and value["resume_requests"] == 1
            and value["auth_responses"] >= 1
            and all(value[key] == 0 for key in ("forbidden_mutations", "external_requests", "page_errors", "server_failures")))


def _restart_browser(node, script, browser_executable, environment, root, port, report):
    child_environment = dict(environment)
    child_environment.update(PE_PACKAGED_BASE_URL=f"http://127.0.0.1:{port}",
                             PE_PACKAGED_BROWSER_EXECUTABLE=os.fspath(browser_executable))
    try:
        result = run_owned_process((os.fspath(node), os.fspath(script)), cwd=root, env=child_environment,
                                   stdout_limit=16384, stderr_limit=16384, timeout=90, maximum_active_processes=8)
        report["restart_browser_cleanup_confirmed"] = True
    except OwnedProcessRunError as error:
        report["restart_browser_cleanup_confirmed"] = error.code in {
            "owned_process_stdout_limit", "owned_process_stderr_limit", "owned_process_timeout"}
        raise _ProbeFailure("restart_browser_failed") from None
    receipt = _restart_browser_receipt(result.stdout)
    if receipt is not None:
        report["restart_browser_receipt"] = receipt
    report["restart_browser_verified"] = result.returncode == 0 and not result.stderr and _restart_browser_passed(receipt)
    if not report["restart_browser_verified"]:
        raise _ProbeFailure("restart_browser_failed")


def _browser_receipt(output: bytearray) -> dict[str, object] | None:
    """Accept only the streaming script's closed content-free receipt."""
    prefix = b"PACKAGED_AGENT_STREAMING_PROBE="
    raw = bytes(output).strip()
    if not raw.startswith(prefix) or b"\n" in raw or b"\r" in raw:
        return None
    try:
        receipt = json.loads(raw[len(prefix):], object_pairs_hook=_unique_pairs)
    except (ValueError, UnicodeError):
        return None
    expected = _BROWSER_BOOLEANS | _BROWSER_COUNTS | {
        "contract", "error_code", "exception_kind",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected:
        return None
    if receipt["contract"] != "packaged-agent-streaming-probe.v1":
        return None
    if any(type(receipt[key]) is not bool for key in _BROWSER_BOOLEANS):
        return None
    if any(type(receipt[key]) is not int or not 0 <= receipt[key] <= 1000 for key in _BROWSER_COUNTS):
        return None
    error = receipt["error_code"]
    if error is not None and (not isinstance(error, str) or error not in _BROWSER_ERRORS):
        return None
    kind = receipt["exception_kind"]
    if kind is not None and (
        not isinstance(kind, str)
        or kind not in {"target_closed", "timeout", "playwright_error", "unknown"}
    ):
        return None
    return receipt


def _browser_receipt_passed(receipt: dict[str, object]) -> bool:
    return (
        receipt["passed"] is True
        and receipt["error_code"] is None
        and receipt["exception_kind"] is None
        and all(receipt[key] is True for key in _BROWSER_BOOLEANS - {
            "draft_persistence_claimed", "server_restart_claimed",
        })
        and receipt["draft_persistence_claimed"] is False
        and receipt["server_restart_claimed"] is False
        and all(receipt[key] == 0 for key in (
            "model_mutation_requests", "external_requests", "page_errors", "server_failures",
        ))
        and receipt["projects_created"] == 1
        and receipt["chats_created"] == 1
        and receipt["message_send_requests"] == 3
        and receipt["stop_requests"] == 1
        and receipt["incremental_turns_verified"] == 2
        and receipt["incremental_deltas_verified"] == 4
        and receipt["completed_turns_verified"] == 2
        and receipt["completed_chunks_verified"] == 6
        and receipt["cancellations_verified"] == 1
        and receipt["composer_ready_after_turns"] == 3
        and receipt["reloads"] == 1
        and receipt["catalog_reopens"] == 1
        and receipt["retained_user_messages_verified"] == 2
        and receipt["retained_assistant_messages_verified"] == 2
    )


def _safe_external_root(candidate: Path) -> Path | None:
    try:
        if not candidate.is_absolute():
            return None
        lexical = Path(os.path.abspath(os.fspath(candidate)))
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        for component in (lexical, *lexical.parents):
            metadata = component.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or bool(getattr(metadata, "st_file_attributes", 0) & reparse)
            ):
                return None
        resolved = lexical.resolve(strict=True)
        repository = Path(__file__).resolve().parents[2]
        home = Path.home().resolve(strict=True)
        if (
            resolved == Path(resolved.anchor)
            or resolved == home or resolved.is_relative_to(home) or home.is_relative_to(resolved)
            or resolved == repository or resolved.is_relative_to(repository)
            or repository.is_relative_to(resolved)
        ):
            return None
        return resolved
    except OSError:
        return None


def _checked_file(path: Path) -> Path | None:
    try:
        if not path.is_absolute():
            return None
        lexical = Path(os.path.abspath(os.fspath(path)))
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        metadata = lexical.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or bool(getattr(metadata, "st_file_attributes", 0) & reparse)
        ):
            return None
        resolved = lexical.resolve(strict=True)
        return resolved
    except OSError:
        return None


def _model_running(payload: dict[str, object]) -> bool:
    runtime = payload.get("runtime")
    record = payload.get("record")
    return (
        isinstance(runtime, dict) and isinstance(record, dict)
        and record.get("alias") == _ALIAS
        and runtime.get("state") == "running"
        and runtime.get("device") == "cpu"
        and runtime.get("gpu_layers") == 0
        and runtime.get("context_size") == 4096
        and runtime.get("fast_attention") is False
        and runtime.get("tool_calling") is False
    )


def _history_matches(payload: dict[str, object]) -> bool:
    events = payload.get("events")
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        return False
    users = [event.get("text") for event in events if event.get("kind") == "user"]
    replies = [event.get("text") for event in events
               if event.get("kind") == "assistant" and event.get("stream_status") == "complete"]
    return (
        users == ["Synthetic streaming acceptance.", "Synthetic cancellation acceptance.",
                  "Synthetic retained-history acceptance."]
        # The application canonicalizes streamed text before emitting durable events.
        and replies == ["Synthetic chunk. Synthetic chunk. Synthetic chunk."] * 2
        and sum(event.get("kind") == "assistant" for event in events) == 3
        and sum(event.get("kind") == "assistant" and event.get("stream_status") == "stopped"
                for event in events) == 1
        and not any(event.get("kind") in {"tool_call", "tool_result", "approval_required"} for event in events)
    )


def _recovered_readonly(payload: dict[str, object], project_id: str, session_id: str) -> bool:
    settings = payload.get("settings")
    return (
        isinstance(settings, dict) and payload.get("session_id") == session_id
        and settings.get("project_id") == project_id
        and payload.get("recovered") is True and payload.get("authority_revalidated") is False
        and settings.get("model_alias") == _ALIAS and payload.get("model_alias") == _ALIAS
        and settings.get("retention_policy") == "local_history"
        and all(settings.get(key) is False for key in ("allow_writes", "allow_commands", "allow_web"))
        and payload.get("pending_approval_id") is None
        and all(payload.get(key) is False for key in ("running", "closing", "stopping", "cleanup_unconfirmed"))
    )


def _restart_passed(report: dict[str, object]) -> bool:
    return (all(report.get(key) is True for key in _RESTART_FLAGS)
            and all(type(report.get(key)) is int and report[key] == 2
                    for key in ("launches_started", "launches_ready", "browser_auth_sessions")))


def _complete_passed(report):
    return (report.get("streaming_phase_passed") is True and report.get("error_code") is None
            and _restart_passed(report) and all(report.get(key) is True for key in _RESTART_BROWSER_FLAGS))


def _cold_restart(runtime: Path, executable: Path, root: Path, fixture_executable: Path,
                  previous_port: int, report: dict[str, object], node: Path, restart_script: Path,
                  browser_executable: Path) -> None:
    process = None
    capture = None
    port = _ephemeral_loopback_port()
    if port in {8765, 8766, previous_port} or not 1024 <= port <= 65535:
        report["error_code"] = "restart_port_invalid"
        return
    phase = "restart_startup_failed"
    try:
        environment = _environment(runtime, root, port)
        environment["PROMPT_ENHANCER_LLAMA_SERVER"] = os.fspath(fixture_executable)
        process = start_owned_process(
            (os.fspath(executable), "-I", "-B", "-m", "prompt_enhancer", "serve"),
            cwd=root, env=environment, capture_stdout=True, capture_stderr=True,
            maximum_active_processes=4,
        )
        report["launches_started"] += 1
        capture = _capture_threads(process)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process_tree_exited(process) or any(event.is_set() for event in capture[2]):
                raise _ProbeFailure(phase)
            try:
                status, payload, _ = _json_request(port, "GET", "/health")
                if status == 200 and payload == {"status": "ok", "cost_mode": "offline_only", "data_tier": "metadata"}:
                    break
            except (OSError, http.client.HTTPException, _ProbeFailure):
                pass
            time.sleep(0.1)
        else:
            raise _ProbeFailure(phase)
        report["launches_ready"] += 1
        phase = "restart_auth_failed"
        auth = _fresh_browser_auth(port)
        report["browser_auth_sessions"] += 1

        def get(path):
            status, payload, _ = _json_request(port, "GET", path, auth=auth, timeout_seconds=20)
            if status != 200:
                raise _ProbeFailure(phase)
            return payload

        phase = "restart_model_running"
        model = get(f"/v1/local-models/{_ALIAS}")
        if model.get("runtime", {}).get("state") != "stopped":
            raise _ProbeFailure(phase)
        phase = "restart_catalog_mismatch"
        projects = get("/v1/agent/projects").get("projects")
        sessions = get("/v1/agent/catalog/sessions").get("sessions")
        if not isinstance(projects, list) or len(projects) != 1 or not isinstance(sessions, list) or len(sessions) != 1:
            raise _ProbeFailure(phase)
        project, record = projects[0], sessions[0]
        project_id, session_id = project.get("project_id"), record.get("session_id")
        if (not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value)
                    for value in (project_id, session_id))
                or project.get("name") != "Synthetic packaged streaming project"
                or record.get("project_id") != project_id or record.get("model_alias") != _ALIAS
                or record.get("retention_policy") != "local_history"
                or record.get("history_state") != "durable_local"
                or record.get("conversation_available") is not True
                or any(type(record.get(key)) is not int or record[key] < 1
                       for key in ("revision", "history_revision"))):
            raise _ProbeFailure(phase)
        route = f"/v1/agent/projects/{project_id}/sessions/{session_id}"
        phase = "restart_history_mismatch"
        history = get(route + "/export?expected_catalog_revision=" + str(record["revision"])
                      + "&expected_history_revision=" + str(record["history_revision"]))
        if (history.get("project_id") != project_id or history.get("session_id") != session_id
                or history.get("model_alias") != _ALIAS or not _history_matches(history)):
            raise _ProbeFailure(phase)
        report["restart_history_verified"] = True
        phase = "restart_browser_failed"
        _restart_browser(node, restart_script, browser_executable, environment, root, port, report)
        # UI resume creates the live recovered session. Preserve the HTTP check
        # below as an explicit idempotent resume verification, not a second
        # cold recovery claim. Export again to prove UI draft/reopen did not
        # append, duplicate or alter retained conversation events.
        phase = "restart_history_mismatch"
        current_records = get("/v1/agent/catalog/sessions").get("sessions")
        if not isinstance(current_records, list) or len(current_records) != 1 or current_records[0].get("session_id") != session_id:
            raise _ProbeFailure(phase)
        current_record = current_records[0]
        current_revision = current_record.get("revision")
        current_history_revision = current_record.get("history_revision")
        if type(current_revision) is not int or type(current_history_revision) is not int:
            raise _ProbeFailure(phase)
        after_history = get(route + "/export?expected_catalog_revision=" + str(current_revision)
                            + "&expected_history_revision=" + str(current_history_revision))
        if not _history_matches(after_history):
            raise _ProbeFailure(phase)
        phase = "restart_resume_mismatch"
        status, resumed, _ = _json_request(port, "POST", route + "/resume", auth=auth,
            body={"expected_catalog_revision": record["revision"], "expected_history_revision": record["history_revision"]},
            timeout_seconds=20)
        if status != 200 or not _recovered_readonly(resumed, project_id, session_id):
            raise _ProbeFailure(phase)
        report["restart_authority_reset"] = True
        phase = "restart_model_running"
        model = get(f"/v1/local-models/{_ALIAS}")
        if model.get("runtime", {}).get("state") != "stopped":
            raise _ProbeFailure(phase)
        report["restart_model_not_running"] = True
        report["cold_restart_verified"] = True
    except Exception:
        report["error_code"] = phase
    finally:
        if process is not None:
            try:
                report["restart_tree_stopped"] = terminate_owned_process(process, graceful_timeout=0.1, forced_timeout=3)
            except Exception:
                pass
            try:
                report["restart_handles_closed"] = bool(process.close(close_streams=True))
            except Exception:
                pass
        if capture is not None:
            for thread in capture[0]:
                thread.join(timeout=1)
            report["restart_readers_stopped"] = all(not thread.is_alive() for thread in capture[0])
            if any(event.is_set() for event in capture[2]):
                report["error_code"] = report["error_code"] or "restart_output_limit"
            for buffer in capture[1]:
                buffer.clear()
        until = time.monotonic() + 5
        while time.monotonic() < until:
            if _port_is_released(port):
                report["restart_port_released"] = True
                break
            time.sleep(0.05)
        if report["error_code"] is None and not _restart_passed(report):
            report["error_code"] = "restart_cleanup_unconfirmed"


def probe(
    runtime: Path,
    fixture_root: Path,
    fixture_manifest_sha256: str,
    artifact_root: Path,
    node: Path,
    script: Path,
    browser_executable: Path,
    restart_script: Path | None = None,
) -> dict[str, object]:
    report: dict[str, object] = {
        "contract": "packaged-streaming-runner.v1", "passed": False,
        "fixture_manifest_verified": False, "fixture_hashes_verified": False,
        "health_ok": False, "model_registered": False, "model_ready_cpu": False,
        "browser_exit_ok": False, "browser_receipt_ok": False,
        "model_deactivate_attempted": False, "model_deactivated": False,
        "server_tree_stopped": False, "browser_tree_stopped": False,
        "server_handles_closed": False, "browser_handles_closed": False,
        "app_port_released": False, "model_runtime_port_reported": False,
        "model_runtime_port_released": None, "fixture_retained": False,
        "browser_stderr_bytes": 0, "capture_readers_stopped": False,
        "browser_process_limit": 8, "server_process_limit": 4,
        "browser_peak_observed_processes": None,
        "browser_process_inventory_available": False,
        "shutdown_kind": "owned_process_termination", "error_code": None,
        "launches_started": 0, "launches_ready": 0, "browser_auth_sessions": 0,
        "streaming_phase_passed": False, **{key: False for key in _RESTART_FLAGS},
        **{key: False for key in _RESTART_BROWSER_FLAGS},
    }
    executable = _checked_file(runtime / "python.exe") if runtime.is_absolute() else None
    inputs = tuple(_checked_file(path) for path in (node, script, browser_executable))
    checked_restart_script = _checked_file(restart_script) if restart_script is not None else None
    retained_root = _safe_external_root(artifact_root)
    if sys.platform != "win32" or executable is None or any(path is None for path in inputs) or checked_restart_script is None:
        report["error_code"] = "probe_inputs_unavailable"
        return report
    if retained_root is None:
        report["error_code"] = "artifact_root_unsafe"
        return report
    try:
        verified = verify_fixture(fixture_root, fixture_manifest_sha256)
    except (_FixtureFailure, OSError, ValueError):
        report["error_code"] = "fixture_manifest_invalid"
        return report
    fixture_executable, model = verified
    report["fixture_manifest_verified"] = True
    report["fixture_hashes_verified"] = True
    port = _ephemeral_loopback_port()
    if port in {8765, 8766} or not 1024 <= port <= 65535:
        report["error_code"] = "unsafe_probe_port"
        return report

    retained_fixture: Path | None = None
    server = browser = None
    browser_capture = None
    captures = []
    auth = None
    try:
        retained_fixture = Path(tempfile.mkdtemp(prefix="packaged-streaming-", dir=retained_root))
        for name in (
            "temp", "empty-profile", "example-workspace", "empty-claude", "empty-codex",
            "empty-model-cache",
        ):
            (retained_fixture / name).mkdir()
        environment = _environment(runtime, retained_fixture, port)
        environment["PROMPT_ENHANCER_LLAMA_SERVER"] = os.fspath(fixture_executable)
        server = start_owned_process(
            (os.fspath(executable), "-I", "-B", "-m", "prompt_enhancer", "serve"),
            cwd=retained_fixture, env=environment, capture_stdout=True, capture_stderr=True,
            maximum_active_processes=4,
        )
        server_capture = _capture_threads(server)
        report["launches_started"] = 1
        captures.append(server_capture)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if any(event.is_set() for event in server_capture[2]):
                raise _ProbeFailure("server_output_limit")
            if process_tree_exited(server):
                raise _ProbeFailure("server_exited_before_ready")
            try:
                status, payload, _cookie = _json_request(port, "GET", "/health")
                if status == 200 and payload == {
                    "status": "ok", "cost_mode": "offline_only", "data_tier": "metadata",
                }:
                    report["health_ok"] = True
                    break
            except (OSError, http.client.HTTPException, _ProbeFailure):
                pass
            time.sleep(0.1)
        if not report["health_ok"]:
            raise _ProbeFailure("health_timeout")
        auth = _fresh_browser_auth(port)
        report["launches_ready"] = 1
        report["browser_auth_sessions"] = 1
        status, added, _cookie = _json_request(
            port, "POST", "/v1/local-models", auth=auth,
            body={
                "alias": _ALIAS, "path": os.fspath(model), "default_device": "cpu",
                "context_size": 4096,
            },
        )
        if status != 201:
            raise _ProbeFailure("model_register_failed")
        if added.get("alias") != _ALIAS:
            raise _ProbeFailure("model_register_mismatch")
        report["model_registered"] = True
        status, activated, _cookie = _json_request(
            port, "POST", f"/v1/local-models/{_ALIAS}/activate", auth=auth,
            body={
                "device": "cpu", "gpu_layers": 0, "context_size": 4096,
                "remember": False, "fast_attention": False, "tool_calling": False,
            },
            timeout_seconds=20,
        )
        if status != 200:
            raise _ProbeFailure("model_activate_failed")
        if not _model_running(activated):
            raise _ProbeFailure("model_activate_mismatch")
        report["model_ready_cpu"] = True

        browser_environment = dict(environment)
        browser_environment.update({
            "PE_PACKAGED_BASE_URL": f"http://127.0.0.1:{port}",
            "PE_PACKAGED_WORKSPACE": os.fspath(retained_fixture / "example-workspace"),
            "PE_PACKAGED_BROWSER_EXECUTABLE": os.fspath(browser_executable),
            "PE_PACKAGED_MODEL_ALIAS": _ALIAS,
        })
        browser = start_owned_process(
            (os.fspath(node), os.fspath(script)), cwd=retained_fixture,
            env=browser_environment, capture_stdout=True, capture_stderr=True,
            maximum_active_processes=8,
        )
        browser_capture = _capture_threads(browser)
        captures.append(browser_capture)
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline:
            try:
                count = len(browser.active_process_ids())
                previous = report["browser_peak_observed_processes"]
                report["browser_peak_observed_processes"] = max(
                    count, previous if isinstance(previous, int) else 0,
                )
                report["browser_process_inventory_available"] = True
            except (AttributeError, OSError):
                pass
            if any(event.is_set() for capture in captures for event in capture[2]):
                raise _ProbeFailure("child_output_limit")
            if process_tree_exited(server):
                raise _ProbeFailure("server_exited_during_browser")
            if browser.poll() is not None:
                report["browser_exit_ok"] = browser.returncode == 0
                if not report["browser_exit_ok"]:
                    raise _ProbeFailure("browser_probe_failed")
                break
            time.sleep(0.1)
        else:
            raise _ProbeFailure("browser_timeout")
    except _ProbeFailure as error:
        report["error_code"] = error.code if error.code in _RUNNER_ERRORS else "packaged_streaming_probe_failed"
    except Exception:
        report["error_code"] = "packaged_streaming_probe_failed"
    finally:
        if auth is not None and report["model_registered"]:
            report["model_deactivate_attempted"] = True
            try:
                status, stopped, _cookie = _json_request(
                    port, "POST", f"/v1/local-models/{_ALIAS}/deactivate", auth=auth,
                    timeout_seconds=20,
                )
                runtime_status = stopped.get("runtime")
                report["model_deactivated"] = (
                    status == 200 and isinstance(runtime_status, dict)
                    and runtime_status.get("state") == "stopped"
                )
            except (OSError, http.client.HTTPException, _ProbeFailure):
                report["model_deactivated"] = False
            if not report["model_deactivated"]:
                report["error_code"] = report["error_code"] or "model_deactivate_failed"
        for label, process in (("browser", browser), ("server", server)):
            if process is None:
                continue
            try:
                report[f"{label}_tree_stopped"] = terminate_owned_process(
                    process, graceful_timeout=0.1, forced_timeout=3.0,
                )
            except Exception:
                report[f"{label}_tree_stopped"] = False
            finally:
                try:
                    report[f"{label}_handles_closed"] = bool(process.close(close_streams=True))
                except Exception:
                    report[f"{label}_handles_closed"] = False
        for threads, _buffers, _events in captures:
            for thread in threads:
                thread.join(timeout=1.0)
        report["capture_readers_stopped"] = all(
            not thread.is_alive() for threads, _buffers, _events in captures for thread in threads
        )
        if any(event.is_set() for capture in captures for event in capture[2]):
            report["error_code"] = report["error_code"] or "child_output_limit"
        if browser_capture is not None:
            report["browser_stderr_bytes"] = len(browser_capture[1][1])
            if report["browser_stderr_bytes"] != 0:
                report["error_code"] = report["error_code"] or "browser_stderr_not_empty"
            receipt = _browser_receipt(browser_capture[1][0])
            if receipt is not None:
                report["browser_receipt"] = receipt
                report["browser_receipt_ok"] = _browser_receipt_passed(receipt)
            if not report["browser_receipt_ok"]:
                report["error_code"] = report["error_code"] or "browser_receipt_invalid"
        for _threads, buffers, _events in captures:
            for buffer in buffers:
                buffer.clear()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if _port_is_released(port):
                report["app_port_released"] = True
                break
            time.sleep(0.05)
        report["fixture_retained"] = retained_fixture is not None and retained_fixture.is_dir()
        required_cleanup = all(report[key] is True for key in (
            "server_tree_stopped", "server_handles_closed", "app_port_released", "fixture_retained",
            "capture_readers_stopped",
        )) and (browser is None or all(report[key] is True for key in (
            "browser_tree_stopped", "browser_handles_closed",
        )))
        if report["error_code"] is None and not required_cleanup:
            report["error_code"] = "probe_cleanup_unconfirmed"

    report["streaming_phase_passed"] = (
        report["error_code"] is None
        and report["fixture_manifest_verified"] is True
        and report["fixture_hashes_verified"] is True
        and report["health_ok"] is True and report["model_registered"] is True
        and report["model_ready_cpu"] is True and report["browser_exit_ok"] is True
        and report["browser_receipt_ok"] is True
        and report["model_deactivate_attempted"] is True and report["model_deactivated"] is True
        and required_cleanup
    )
    if report["streaming_phase_passed"]:
        _cold_restart(runtime, executable, retained_fixture, fixture_executable, port, report,
                      node, checked_restart_script, browser_executable)
    report["passed"] = _complete_passed(report)
    return report


def main(argv: list[str] | None = None) -> int:
    class ContentFreeParser(argparse.ArgumentParser):
        def error(self, message: str) -> None:
            raise ValueError("invalid_arguments")

    parser = ContentFreeParser(description=__doc__)
    for name in (
        "runtime", "fixture-root", "artifact-root", "node", "script", "browser-executable", "restart-script",
    ):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--fixture-manifest-sha256", required=True)
    try:
        arguments = parser.parse_args(argv)
    except ValueError:
        print('PACKAGED_STREAMING_RUNNER={"error_code":"invalid_arguments"}', flush=True)
        return 2
    report = probe(
        arguments.runtime, arguments.fixture_root, arguments.fixture_manifest_sha256,
        arguments.artifact_root,
        arguments.node, arguments.script, arguments.browser_executable, arguments.restart_script,
    )
    print("PACKAGED_STREAMING_RUNNER=" + json.dumps(report, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
