"""Owned packaged calibration acceptance with one fictional local-source session.

This runner uses the staged production server entry point, public onboarding and
calibration HTTP routes, and a fresh browser. It never reads provider homes,
token files, or existing databases and never starts a model.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

from packaged_chat_probe import _ProbeFailure, _await_ready, _fresh_browser_auth, _json_request
from packaged_serve_probe import _capture_threads, _environment, _ephemeral_loopback_port, _port_is_released
from packaged_streaming_runner import _checked_file, _safe_external_root, _unique_pairs
from prompt_enhancer.application.owned_process import (
    OwnedProcessRunError, process_tree_exited, run_owned_process,
    start_owned_process, terminate_owned_process,
)

_PREFIX = b"PACKAGED_CALIBRATION_BROWSER_PROBE="
_BOOLS = {
    "passed", "browser_started", "browser_closed", "calibration_page_loaded",
    "case_reviewed", "review_acknowledged", "ratings_saved", "reload_verified",
    "rater_persisted", "review_expiry_claimed",
    "evidence_container_visible", "expected_evidence_visible",
    "reloaded_evidence_container_visible", "reloaded_expected_evidence_visible",
}
_COUNTS = {
    "review_requests", "rating_mutations", "ratings_verified",
    "cannot_judge_verified", "reloads", "model_mutation_requests",
    "forbidden_mutations", "external_requests", "page_errors", "server_failures",
}
_STATUSES = {"initial_review_status", "reload_review_status"}
_BROWSER_ERRORS = {
    "invalid_environment", "browser_launch_failed", "context_create_failed",
    "page_create_failed", "calibration_page_failed", "case_review_failed",
    "initial_review_response_failed", "evidence_container_failed",
    "evidence_content_failed", "reload_review_response_failed",
    "reload_evidence_container_failed", "reload_evidence_content_failed",
    "rating_input_failed", "rating_save_failed", "reload_failed",
    "request_boundary_failed", "browser_cleanup_failed", "probe_failed",
}
_RUNNER_FLAGS = {
    "health_ok", "onboarding_verified", "browser_verified", "export_verified",
    "fixture_unchanged", "browser_cleanup_confirmed", "server_tree_stopped",
    "server_handles_closed", "server_readers_stopped", "port_released",
}
_RUNNER_ERRORS = {
    "probe_inputs_unavailable", "artifact_root_unsafe", "unsafe_probe_port",
    "server_output_limit", "server_exited_before_ready", "health_timeout",
    "onboarding_failed", "browser_failed", "export_failed",
    "server_exited_during_browser", "fixture_changed", "cleanup_unconfirmed",
    "probe_failed", "invalid_arguments",
}
_TRANSCRIPT = (
    '{"type":"user","message":{"role":"user","content":"Review the fictional module and report the checks performed."},'
    '"timestamp":"2040-01-01T10:00:00Z","sessionId":"example-calibration-session",'
    '"cwd":"C:\\\\example\\\\calibration","version":"2.1.0"}\n'
    '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"The fictional checks completed."}]},'
    '"timestamp":"2040-01-01T10:01:00Z","sessionId":"example-calibration-session",'
    '"cwd":"C:\\\\example\\\\calibration","version":"2.1.0"}\n'
).encode("utf-8")
_PSEUDONYM = re.compile(r"^(?!0{64}$)[a-f0-9]{64}$")
_EXPECTED_RATINGS = {
    "prompt.task_definition_coverage": "high",
    "prompt.context_sufficiency": "cannot_judge",
    "outcome.verification_strategy_adequacy": "medium",
}


def _valid_pseudonyms(values: set[object]) -> bool:
    return len(values) == 1 and all(
        isinstance(value, str) and _PSEUDONYM.fullmatch(value) is not None
        for value in values
    )


def _browser_receipt(output: bytearray) -> dict[str, object] | None:
    raw = bytes(output)
    try:
        if len(raw) > 16_384 or not raw.startswith(_PREFIX) or not raw.endswith(b"\n") \
                or raw.count(b"\n") != 1 or b"\r" in raw:
            return None
        value = json.loads(raw[len(_PREFIX):-1], object_pairs_hook=_unique_pairs)
        expected = _BOOLS | _COUNTS | _STATUSES | {"contract", "error_code", "exception_kind"}
        if not isinstance(value, dict) or set(value) != expected:
            return None
        if value["contract"] != "packaged-calibration-browser-probe.v1":
            return None
        if any(type(value[key]) is not bool for key in _BOOLS):
            return None
        if any(type(value[key]) is not int or not 0 <= value[key] <= 100 for key in _COUNTS):
            return None
        if any(value[key] is not None and (
                type(value[key]) is not int or not 100 <= value[key] <= 599) for key in _STATUSES):
            return None
        if value["error_code"] is not None and (
                type(value["error_code"]) is not str or value["error_code"] not in _BROWSER_ERRORS):
            return None
        if value["exception_kind"] is not None and value["exception_kind"] not in {
                "timeout", "target_closed", "playwright_error", "unknown"}:
            return None
        if value["passed"] != _browser_passed(value):
            return None
        return value
    except (TypeError, ValueError, UnicodeError):
        return None


def _browser_passed(value: dict[str, object] | None) -> bool:
    return bool(value and value.get("error_code") is None and value.get("exception_kind") is None
        and all(value.get(key) is True for key in _BOOLS - {"review_expiry_claimed"})
        and value.get("review_expiry_claimed") is False
        and value.get("review_requests") == 2 and value.get("rating_mutations") == 1
        and value.get("initial_review_status") == 200 and value.get("reload_review_status") == 200
        and value.get("ratings_verified") == 3 and value.get("cannot_judge_verified") == 1
        and value.get("reloads") == 1
        and all(value.get(key) == 0 for key in (
            "model_mutation_requests", "forbidden_mutations", "external_requests",
            "page_errors", "server_failures")))


def _write_fixture(root: Path) -> Path:
    target = root / "fictional-claude" / "projects" / "-C-example-calibration"
    target.mkdir(parents=True)
    transcript = target / "example-calibration-session.jsonl"
    with transcript.open("xb") as stream:
        stream.write(_TRANSCRIPT)
    return transcript


def _ordinary(path: Path, *, directory: bool) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    return expected and not stat.S_ISLNK(metadata.st_mode) \
        and not bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def _fixture_identity(path: Path):
    metadata = path.lstat()
    if not _ordinary(path, directory=False) or metadata.st_nlink != 1:
        raise _ProbeFailure("fixture_changed")
    return metadata.st_dev, metadata.st_ino, metadata.st_size


def _fixture_matches(root: Path, transcript: Path | None, identity) -> bool:
    if transcript is None or identity is None:
        return False
    claude = root / "fictional-claude"
    projects = claude / "projects"
    project = projects / "-C-example-calibration"
    try:
        if not all(_ordinary(path, directory=True) for path in (claude, projects, project)):
            return False
        if list(claude.iterdir()) != [projects] or list(projects.iterdir()) != [project] \
                or list(project.iterdir()) != [transcript]:
            return False
        metadata = transcript.lstat()
        if not _ordinary(transcript, directory=False) or metadata.st_nlink != 1 \
                or (metadata.st_dev, metadata.st_ino, metadata.st_size) != identity:
            return False
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(transcript, flags)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino, opened.st_size) != identity \
                    or not stat.S_ISREG(opened.st_mode):
                return False
            content = os.read(descriptor, len(_TRANSCRIPT) + 1)
        finally:
            os.close(descriptor)
        return content == _TRANSCRIPT
    except OSError:
        return False


def _onboard(port: int) -> None:
    auth = _fresh_browser_auth(port)
    status, body, _cookie = _json_request(
        port, "POST", "/v1/onboarding/accept", auth=auth,
        body={"providers": ["claude_code"]}, timeout_seconds=20,
    )
    if status != 200 or body.get("granted") != ["claude_code"] \
            or body.get("indexed_sessions") != 1:
        raise _ProbeFailure("onboarding_failed")
    state = body.get("status")
    providers = state.get("providers") if isinstance(state, dict) else None
    selected = [item for item in providers or []
                if isinstance(item, dict) and item.get("provider") == "claude_code"]
    if len(selected) != 1 or selected[0].get("consent_active") is not True \
            or selected[0].get("indexed_sessions") != 1:
        raise _ProbeFailure("onboarding_failed")


def _run_browser(node: Path, script: Path, executable: Path, environment: dict[str, str],
                 root: Path, port: int, report: dict[str, object]) -> dict[str, object]:
    child = dict(environment)
    child.update(PE_PACKAGED_BASE_URL=f"http://127.0.0.1:{port}",
                 PE_PACKAGED_BROWSER_EXECUTABLE=os.fspath(executable))
    try:
        result = run_owned_process(
            (os.fspath(node), os.fspath(script)), cwd=root, env=child,
            stdout_limit=16_384, stderr_limit=16_384, timeout=90,
            maximum_active_processes=8,
        )
    except OwnedProcessRunError as error:
        report["browser_owned_failure_code"] = error.code if error.code in {
            "owned_process_timeout", "owned_process_stdout_limit", "owned_process_stderr_limit",
            "owned_process_unavailable", "owned_process_cleanup_unconfirmed",
        } else "owned_process_failure"
        report["browser_cleanup_confirmed"] = error.code in {
            "owned_process_timeout", "owned_process_stdout_limit", "owned_process_stderr_limit"}
        raise _ProbeFailure("browser_failed") from None
    receipt = _browser_receipt(result.stdout)
    report["browser_receipt"] = receipt
    report["browser_process_exit_zero"] = result.returncode == 0
    report["browser_stderr_empty"] = not result.stderr
    report["browser_cleanup_confirmed"] = True
    if result.returncode != 0 or result.stderr or not _browser_passed(receipt):
        raise _ProbeFailure("browser_failed")
    return receipt  # type: ignore[return-value]


def _verify_export(port: int) -> None:
    auth = _fresh_browser_auth(port)
    status, body, _cookie = _json_request(port, "GET", "/v1/calibration/export", auth=auth)
    rows = body.get("rows")
    if status != 200 or body.get("contract_version") != "calibration-ratings.v1" \
            or not isinstance(rows, list) or len(rows) != 3:
        raise _ProbeFailure("export_failed")
    if any(not isinstance(row, dict) for row in rows):
        raise _ProbeFailure("export_failed")
    mapping = {row.get("metric_key"): row.get("label") for row in rows}
    raters = {row.get("rater_id") for row in rows}
    sessions = {row.get("session_id") for row in rows}
    cases = {row.get("case_fingerprint") for row in rows}
    windows = {row.get("window_fingerprint") for row in rows}
    case_versions = {row.get("case_version") for row in rows}
    rating_versions = {row.get("rating_version") for row in rows}
    if mapping != _EXPECTED_RATINGS or not _valid_pseudonyms(raters) \
            or not _valid_pseudonyms(sessions) or not _valid_pseudonyms(cases) \
            or not _valid_pseudonyms(windows) \
            or case_versions != {"calibration-case.v1"} \
            or rating_versions != {"calibration-rating-v2-reviewed-case"} \
            or any(row.get("provider") != "claude_code" or row.get("revision") != 1 for row in rows) \
            or any(text in json.dumps(body) for text in (
                "Example calibration rater", "fictional module", "fictional checks")):
        raise _ProbeFailure("export_failed")


def _complete(report: dict[str, object]) -> bool:
    return report.get("error_code") is None and all(report.get(key) is True for key in _RUNNER_FLAGS)


def probe(runtime: Path, node: Path, script: Path, browser_executable: Path,
          artifact_root: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "contract": "packaged-calibration-runner.v1", "passed": False,
        "error_code": None, **dict.fromkeys(_RUNNER_FLAGS, False),
        "sessions_indexed": 0, "ratings_exported": 0, "cannot_judge_exported": 0,
        "model_mutations": 0, "shutdown_kind": "owned_process_termination",
        "review_expiry_claimed": False,
        "browser_receipt": None, "browser_owned_failure_code": None,
        "browser_process_exit_zero": False, "browser_stderr_empty": False,
    }
    if sys.platform != "win32" or any(_checked_file(path) is None for path in (
            runtime / "python.exe", node, script, browser_executable)):
        report["error_code"] = "probe_inputs_unavailable"
        return report
    if _safe_external_root(artifact_root) is None:
        report["error_code"] = "artifact_root_unsafe"
        return report
    port = _ephemeral_loopback_port()
    if port in {8765, 8766} or not 1024 <= port <= 65535:
        report["error_code"] = "unsafe_probe_port"
        return report
    root = Path(tempfile.mkdtemp(prefix="packaged-calibration-", dir=artifact_root))
    server = capture = None
    transcript = None
    try:
        for name in ("temp", "empty-profile", "empty-codex", "empty-model-cache"):
            (root / name).mkdir()
        transcript = _write_fixture(root)
        identity = _fixture_identity(transcript)
        environment = _environment(runtime, root, port)
        environment["PROMPT_ENHANCER_SESSION_READER"] = "enabled"
        environment["PROMPT_ENHANCER_CLAUDE_HOME"] = os.fspath(root / "fictional-claude")
        server = start_owned_process(
            (os.fspath(runtime / "python.exe"), "-I", "-B", "-m", "prompt_enhancer", "serve"),
            cwd=root, env=environment, capture_stdout=True, capture_stderr=True,
            maximum_active_processes=4,
        )
        capture = _capture_threads(server)
        _await_ready(server, port, capture[2])
        report["health_ok"] = True
        _onboard(port)
        report["onboarding_verified"] = True
        report["sessions_indexed"] = 1
        browser_receipt = _run_browser(node, script, browser_executable, environment, root, port, report)
        report["browser_verified"] = True
        report["model_mutations"] = browser_receipt["model_mutation_requests"]
        _verify_export(port)
        report["export_verified"] = True
        report["ratings_exported"] = 3
        report["cannot_judge_exported"] = 1
        if process_tree_exited(server):
            raise _ProbeFailure("server_exited_during_browser")
    except _ProbeFailure as error:
        report["error_code"] = error.code if error.code in _RUNNER_ERRORS else "probe_failed"
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
        report["fixture_unchanged"] = _fixture_matches(root, transcript, locals().get("identity"))
        if report["error_code"] is None and not report["fixture_unchanged"]:
            report["error_code"] = "fixture_changed"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if _port_is_released(port):
                report["port_released"] = True
                break
            time.sleep(.05)
        if report["error_code"] is None and not _complete(report):
            report["error_code"] = "cleanup_unconfirmed"
    report["passed"] = _complete(report) and report["sessions_indexed"] == 1 \
        and report["ratings_exported"] == 3 and report["cannot_judge_exported"] == 1 \
        and report["model_mutations"] == 0 and report["review_expiry_claimed"] is False
    return report


def main(argv: list[str] | None = None) -> int:
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError() from None
    parser = Parser(description=__doc__)
    for name in ("runtime", "node", "script", "browser-executable", "artifact-root"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    try:
        args = parser.parse_args(argv)
        report = probe(args.runtime, args.node, args.script, args.browser_executable, args.artifact_root)
    except Exception:
        report = {"contract": "packaged-calibration-runner.v1", "passed": False,
                  "error_code": "invalid_arguments"}
    print("PACKAGED_CALIBRATION_RUNNER=" + json.dumps(report, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if report.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
