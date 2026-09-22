"""Owned packaged browser workspace acceptance; synthetic data, no native approval.

Only a reviewed invocation launches anything. Imports and receipt tests are inert.
The browser's one controlled stale-revision mutation is restored, never an app edit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from packaged_chat_probe import _ProbeFailure, _json_request
from packaged_serve_probe import _capture_threads, _environment, _ephemeral_loopback_port, _port_is_released
from packaged_streaming_runner import _checked_file, _safe_external_root, _unique_pairs
from prompt_enhancer.application.paths.policy import classify_windows_path_text
from prompt_enhancer.application.owned_process import (
    OwnedProcessRunError, run_owned_process, start_owned_process,
    process_tree_exited, terminate_owned_process,
)

ORIGINAL = b"export const exampleValue = 1;\n"
CHANGED = b"export const exampleValue = 3;\n"
_FLAGS = {"browser_started", "browser_closed", "file_read", "diff_verified", "apply_disabled",
          "native_refused", "csrf_refused", "traversal_refused", "stale_refused", "discard_reopened",
          "file_unchanged_after_refusal", "fixture_restored", "readonly_session", "passed"}
_COUNTS = {"projects_created": 1, "chats_created": 1, "previews_created": 1, "apply_attempts": 2,
           "fixture_mutations": 1, "forbidden_mutations": 0, "external_requests": 0,
           "page_errors": 0, "server_failures": 0, "project_requests": 1, "session_requests": 1,
           "preview_requests": 2, "apply_requests": 2}
_ERRORS = {"invalid_environment", "browser_failed", "project_failed", "chat_failed", "file_read_failed",
           "file_response_failed", "editor_ready_failed",
           "preview_failed", "refusal_failed", "discard_failed", "stale_failed", "fixture_cleanup_failed",
           "browser_cleanup_failed", "completion_failed"}
_FINAL_FLAGS = {"health_ok", "browser_verified", "browser_cleanup_confirmed", "server_tree_stopped",
                "server_handles_closed", "server_readers_stopped", "port_released", "fixture_unchanged"}
_FILE_ERRORS = {"workspace_file_unavailable", "workspace_file_changed", "workspace_root_changed",
    "workspace_link_or_reparse_refused", "workspace_file_too_large", "workspace_binary_refused",
    "workspace_text_invalid", "workspace_line_endings_unsupported", "workspace_directory_unavailable",
    "path_invalid", "path_outside_workspace", "session_not_found", "session_closing", "other", "invalid_json",
    "workspace_revision_changed"}


def _file_response_valid(value):
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != {
            "status", "error_category", "content_present", "content_string", "content_matches"}:
        return False
    if type(value["status"]) is not int or not 100 <= value["status"] <= 599:
        return False
    category = value["error_category"]
    if category is not None and (type(category) is not str or category not in _FILE_ERRORS):
        return False
    if any(type(value[key]) is not bool for key in ("content_present", "content_string", "content_matches")):
        return False
    return (not value["content_matches"] or value["content_string"]) and (
        not value["content_string"] or value["content_present"])


def _file_response_passed(value):
    return value == {"status": 200, "error_category": None,
                     "content_present": True, "content_string": True, "content_matches": True}


def _traversal_response_valid(value):
    return value is None or (isinstance(value, dict) and set(value) == {"status", "error_category"}
        and type(value["status"]) is int and 100 <= value["status"] <= 599
        and type(value["error_category"]) is str and value["error_category"] in _FILE_ERRORS)


def _traversal_response_passed(value):
    return value == {"status": 403, "error_category": "path_outside_workspace"}


def _stale_response_passed(value):
    return value == {"status": 409, "error_category": "workspace_revision_changed"}


def _receipt(output):
    try:
        if len(output) > 16384:
            return None
        text = bytes(output).decode("utf-8")
        prefix = "PACKAGED_AGENT_WORKSPACE_PROBE="
        if not text.startswith(prefix) or not text.endswith("\n") or "\r" in text or text.count("\n") != 1:
            return None
        value = json.loads(text[len(prefix):-1], object_pairs_hook=_unique_pairs)
        if not isinstance(value, dict) or set(value) != _FLAGS | set(_COUNTS) | {"contract", "error_code", "file_response", "traversal_response", "stale_response"}:
            return None
        if value["contract"] != "packaged-agent-workspace-probe.v1":
            return None
        if not _file_response_valid(value["file_response"]):
            return None
        if value["file_read"] is True and not _file_response_passed(value["file_response"]):
            return None
        if not _traversal_response_valid(value["traversal_response"]):
            return None
        if value["traversal_refused"] is True and not _traversal_response_passed(value["traversal_response"]):
            return None
        if not _traversal_response_valid(value["stale_response"]):
            return None
        if value["stale_refused"] is True and not _stale_response_passed(value["stale_response"]):
            return None
        if any(type(value[key]) is not bool for key in _FLAGS):
            return None
        if any(type(value[key]) is not int or not 0 <= value[key] <= 100 for key in _COUNTS):
            return None
        if value["error_code"] is not None and (type(value["error_code"]) is not str or value["error_code"] not in _ERRORS):
            return None
        if value["passed"] != _receipt_passed(value):
            return None
        return value
    except (ValueError, TypeError, UnicodeError):
        return None


def _receipt_passed(value):
    return isinstance(value, dict) and value.get("error_code") is None and all(
        value.get(key) is True for key in _FLAGS) and all(value.get(key) == expected for key, expected in _COUNTS.items()) \
        and _file_response_passed(value.get("file_response")) and _traversal_response_passed(value.get("traversal_response")) \
        and _stale_response_passed(value.get("stale_response"))


def _browser(node, script, executable, environment, root, port, report):
    if _checked_file(script) is None:
        raise _ProbeFailure("probe_inputs_unavailable")
    child_env = dict(environment)
    child_env.update(PE_PACKAGED_BASE_URL=f"http://127.0.0.1:{port}",
                     PE_PACKAGED_WORKSPACE=os.fspath(root / "example-workspace"),
                     PE_PACKAGED_BROWSER_EXECUTABLE=os.fspath(executable))
    try:
        result = run_owned_process((os.fspath(node), os.fspath(script)), cwd=root, env=child_env,
                                  stdout_limit=16384, stderr_limit=16384, timeout=90, maximum_active_processes=8)
        report["browser_cleanup_confirmed"] = True
    except OwnedProcessRunError as error:
        report["browser_cleanup_confirmed"] = error.code in {
            "owned_process_timeout", "owned_process_stdout_limit", "owned_process_stderr_limit"}
        raise _ProbeFailure("browser_failed") from None
    receipt = _receipt(result.stdout)
    if receipt is not None:
        report["browser_receipt"] = receipt
    report["browser_verified"] = result.returncode == 0 and not result.stderr and _receipt_passed(receipt)
    if not report["browser_verified"]:
        raise _ProbeFailure("browser_failed")


def _complete(report):
    return report.get("error_code") is None and all(report.get(key) is True for key in _FINAL_FLAGS)


def probe(runtime, node, script, browser_executable, artifact_root):
    report = {"contract": "packaged-workspace-browser-runner.v1", "error_code": None,
              **dict.fromkeys(_FINAL_FLAGS, False), "fixture_sha256": hashlib.sha256(ORIGINAL).hexdigest(),
              "native_apply_success_claimed": False, "shutdown_kind": "owned_process_termination"}
    if (sys.platform != "win32" or any(_checked_file(p) is None for p in
            (runtime / "python.exe", node, script, browser_executable))):
        report["error_code"] = "probe_inputs_unavailable"
        return report
    if (classify_windows_path_text(os.fspath(artifact_root)) is not None or ".." in artifact_root.parts
            or _safe_external_root(artifact_root) is None):
        report["error_code"] = "artifact_root_unsafe"
        return report
    port = _ephemeral_loopback_port()
    if port in {8765, 8766} or not 1024 <= port <= 65535:
        report["error_code"] = "unsafe_probe_port"
        return report
    root = Path(tempfile.mkdtemp(prefix="packaged-workspace-browser-", dir=artifact_root))
    server = capture = None
    fixture = root / "example-workspace" / "example.ts"
    identity = None
    try:
        for name in ("temp", "empty-profile", "example-workspace"):
            (root / name).mkdir()
        with fixture.open("xb") as stream:
            stream.write(ORIGINAL)
        identity = fixture.stat()
        environment = _environment(runtime, root, port)
        server = start_owned_process((os.fspath(runtime / "python.exe"), "-I", "-B", "-m", "prompt_enhancer", "serve"),
                                     cwd=root, env=environment, capture_stdout=True, capture_stderr=True,
                                     maximum_active_processes=4)
        capture = _capture_threads(server)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if any(event.is_set() for event in capture[2]):
                raise _ProbeFailure("server_output_limit")
            if process_tree_exited(server):
                raise _ProbeFailure("server_exited_before_ready")
            try:
                status, body, _ = _json_request(port, "GET", "/health")
                if status == 200 and body == {"status": "ok", "cost_mode": "offline_only", "data_tier": "metadata"}:
                    report["health_ok"] = True
                    break
            except (OSError, _ProbeFailure):
                pass
            time.sleep(.1)
        if not report["health_ok"]:
            raise _ProbeFailure("health_timeout")
        _browser(node, script, browser_executable, environment, root, port, report)
        if process_tree_exited(server):
            raise _ProbeFailure("server_exited_during_browser")
    except _ProbeFailure as error:
        report["error_code"] = error.code
    except Exception:
        report["error_code"] = "probe_failed"
    finally:
        if server is not None:
            try:
                report["server_tree_stopped"] = terminate_owned_process(server, graceful_timeout=.1, forced_timeout=3)
            except Exception:
                pass
            try:
                report["server_handles_closed"] = bool(server.close(close_streams=True))
            except Exception:
                pass
        if capture is not None:
            for thread in capture[0]:
                thread.join(timeout=1)
            report["server_readers_stopped"] = all(not thread.is_alive() for thread in capture[0])
            if any(event.is_set() for event in capture[2]):
                report["error_code"] = "server_output_limit"
            for buffer in capture[1]:
                buffer.clear()
        try:
            current = fixture.lstat()
            if identity is not None and current.st_ino == identity.st_ino and current.st_dev == identity.st_dev:
                with fixture.open("rb") as stream:
                    content = stream.read(len(ORIGINAL) + 1)
                report["fixture_unchanged"] = content == ORIGINAL and list(fixture.parent.iterdir()) == [fixture]
        except OSError:
            pass
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if _port_is_released(port):
                report["port_released"] = True
                break
            time.sleep(.05)
        if report["error_code"] is None and not _complete(report):
            report["error_code"] = "completion_unconfirmed"
    return report


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError()
    parser = Parser(description=__doc__)
    for name in ("runtime", "node", "script", "browser-executable", "artifact-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    try:
        args = parser.parse_args(argv)
        report = probe(args.runtime, args.node, args.script, args.browser_executable, args.artifact_root)
    except Exception:
        report = {"error_code": "invalid_arguments"}
    print("PACKAGED_WORKSPACE_BROWSER_RUNNER=" + json.dumps(report, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if _complete(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
