"""Owned packaged analytics acceptance with one fictional Claude transcript.

The staged app is read through public onboarding/catalog/metrics routes and one
fresh browser. No model, analysis job, provider home, or existing database is
used. The supplied packaged candidate and fixture are verified before/after.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

sys.path.insert(0, os.fspath(Path(__file__).resolve().parents[2] / "scripts"))

from pack_msix_candidate import PackError, _manifest, _verify_candidate
from packaged_chat_probe import _ProbeFailure, _await_ready, _fresh_browser_auth, _json_request
from packaged_serve_probe import _capture_threads, _environment, _ephemeral_loopback_port, _port_is_released
from packaged_streaming_runner import _checked_file, _safe_external_root, _unique_pairs
from prompt_enhancer.application.owned_process import (
    OwnedProcessRunError, process_tree_exited, run_owned_process,
    start_owned_process, terminate_owned_process,
)

_BROWSER_PREFIX = b"PACKAGED_ANALYTICS_BROWSER_PROBE="
_BROWSER_FLAGS = {
    "passed", "browser_started", "browser_closed", "sessions_page_loaded",
    "catalog_session_opened", "model_usage_api_verified",
    "unknown_token_displayed", "token_coverage_displayed",
    "provenance_displayed", "outcome_api_verified",
    "assistant_claim_not_verified", "outcome_displayed",
}
_BROWSER_COUNTS = {
    "session_rows", "metric_response_events", "verified_category_responses",
    "forbidden_mutations",
    "external_requests", "page_errors", "server_failures",
    "model_mutation_requests",
}
_BROWSER_STATUSES = {"model_usage_status", "outcome_status"}
_BROWSER_ERRORS = {
    "invalid_environment", "browser_launch_failed", "context_create_failed",
    "page_create_failed", "sessions_page_failed", "catalog_open_failed",
    "model_usage_response_failed", "unknown_token_contract_failed",
    "unknown_token_display_failed", "token_coverage_failed", "provenance_failed",
    "outcome_response_failed", "claim_boundary_failed", "outcome_display_failed",
    "request_boundary_failed", "browser_cleanup_failed", "probe_failed",
}
_RUNNER_FLAGS = {
    "health_ok", "onboarding_verified", "http_metrics_verified",
    "browser_verified", "fixture_unchanged", "candidate_unchanged",
    "browser_cleanup_confirmed", "server_tree_stopped", "server_handles_closed",
    "server_readers_stopped", "port_released", "candidate_ui_entrypoint_verified",
}
_RUNNER_ERRORS = {
    "probe_inputs_unavailable", "artifact_root_unsafe", "candidate_invalid",
    "candidate_ui_resource_missing",
    "unsafe_probe_port", "server_output_limit", "server_exited_before_ready",
    "health_timeout", "onboarding_failed", "http_metrics_failed",
    "browser_failed", "server_exited_during_browser", "fixture_changed",
    "candidate_changed", "cleanup_unconfirmed", "probe_failed",
    "invalid_arguments",
}
_TRANSCRIPT = (
    '{"type":"user","message":{"role":"user","content":"Inspect the fictional example and report only observed evidence."},'
    '"timestamp":"2040-01-02T10:00:00Z","sessionId":"example-analytics-session",'
    '"cwd":"C:\\\\example\\\\analytics","version":"2.1.0"}\n'
    '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text",'
    '"text":"The fictional task is complete and all checks passed."}]},'
    '"timestamp":"2040-01-02T10:01:00Z","sessionId":"example-analytics-session",'
    '"cwd":"C:\\\\example\\\\analytics","version":"2.1.0"}\n'
).encode("utf-8")
_PSEUDONYM = re.compile(r"^(?!0{64}$)[a-f0-9]{64}$")
_DASHBOARD_PREFIX = "prompt_enhancer/_resources/dashboard/"


def _candidate_ui_bound(candidate: object) -> bool:
    """Require the installed dashboard resource layout, not a root web tree."""
    try:
        names = {item.relative_path for item in candidate.files}  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        return False
    return (_DASHBOARD_PREFIX + "index.html" in names
            and any(name.startswith(_DASHBOARD_PREFIX + "assets/")
                    and name.endswith(".js") for name in names))


def _browser_passed(value: dict[str, object] | None) -> bool:
    return bool(value and value.get("error_code") is None
        and value.get("exception_kind") is None
        and all(value.get(key) is True for key in _BROWSER_FLAGS)
        and value.get("session_rows") == 1
        and value.get("verified_category_responses") == 2
        and value.get("model_usage_status") == 200 and value.get("outcome_status") == 200
        and all(value.get(key) == 0 for key in (
            "forbidden_mutations", "external_requests", "page_errors",
            "server_failures", "model_mutation_requests")))


def _browser_receipt(output: bytes | bytearray) -> dict[str, object] | None:
    raw = bytes(output)
    try:
        if (len(raw) > 16_384 or not raw.startswith(_BROWSER_PREFIX)
                or not raw.endswith(b"\n") or raw.count(b"\n") != 1 or b"\r" in raw):
            return None
        value = json.loads(raw[len(_BROWSER_PREFIX):-1], object_pairs_hook=_unique_pairs)
        expected = (_BROWSER_FLAGS | _BROWSER_COUNTS | _BROWSER_STATUSES
                    | {"contract", "error_code", "exception_kind"})
        if not isinstance(value, dict) or set(value) != expected \
                or value.get("contract") != "packaged-analytics-browser-probe.v1":
            return None
        if any(type(value[key]) is not bool for key in _BROWSER_FLAGS):
            return None
        if any(type(value[key]) is not int or not 0 <= value[key] <= 100
               for key in _BROWSER_COUNTS):
            return None
        if any(value[key] is not None and (
                type(value[key]) is not int or not 100 <= value[key] <= 599)
               for key in _BROWSER_STATUSES):
            return None
        if value["error_code"] is not None and (
                type(value["error_code"]) is not str
                or value["error_code"] not in _BROWSER_ERRORS):
            return None
        if value["exception_kind"] is not None and value["exception_kind"] not in {
                "timeout", "target_closed", "playwright_error", "unknown"}:
            return None
        if value["passed"] != _browser_passed(value):
            return None
        return value
    except (TypeError, ValueError, UnicodeError):
        return None


def _ordinary(path: Path, *, directory: bool) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    return (expected and not stat.S_ISLNK(metadata.st_mode)
            and not bool(getattr(metadata, "st_file_attributes", 0) & 0x400))


def _write_fixture(root: Path) -> tuple[Path, tuple[int, int, int]]:
    target = root / "fictional-claude" / "projects" / "-C-example-analytics"
    target.mkdir(parents=True)
    transcript = target / "example-analytics-session.jsonl"
    with transcript.open("xb") as stream:
        stream.write(_TRANSCRIPT)
    metadata = transcript.lstat()
    return transcript, (metadata.st_dev, metadata.st_ino, metadata.st_size)


def _fixture_matches(root: Path, transcript: Path | None,
                     identity: tuple[int, int, int] | None) -> bool:
    if transcript is None or identity is None:
        return False
    claude = root / "fictional-claude"
    projects = claude / "projects"
    project = projects / "-C-example-analytics"
    try:
        if not all(_ordinary(path, directory=True) for path in (claude, projects, project)):
            return False
        if (list(claude.iterdir()) != [projects] or list(projects.iterdir()) != [project]
                or list(project.iterdir()) != [transcript]):
            return False
        metadata = transcript.lstat()
        if (not _ordinary(transcript, directory=False) or metadata.st_nlink != 1
                or (metadata.st_dev, metadata.st_ino, metadata.st_size) != identity):
            return False
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(transcript, flags)
        try:
            opened = os.fstat(descriptor)
            if ((opened.st_dev, opened.st_ino, opened.st_size) != identity
                    or not stat.S_ISREG(opened.st_mode)):
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
    state = body.get("status") if isinstance(body, dict) else None
    providers = state.get("providers") if isinstance(state, dict) else None
    selected = [item for item in providers or [] if isinstance(item, dict)
                and item.get("provider") == "claude_code"]
    if (status != 200 or body.get("granted") != ["claude_code"]
            or body.get("indexed_sessions") != 1 or len(selected) != 1
            or selected[0].get("consent_active") is not True
            or selected[0].get("indexed_sessions") != 1):
        raise _ProbeFailure("onboarding_failed")


def _metric(rows: object, key: str) -> dict[str, object] | None:
    if not isinstance(rows, list) or len(rows) > 64:
        return None
    found = [item for item in rows if isinstance(item, dict) and item.get("key") == key]
    return found[0] if len(found) == 1 else None


def _verify_http(port: int, report: dict[str, object]) -> tuple[int, int]:
    auth = _fresh_browser_auth(port)
    status, catalog, _cookie = _json_request(port, "GET", "/v1/sessions?limit=2&offset=0", auth=auth)
    sessions = catalog.get("sessions") if isinstance(catalog, dict) else None
    report["catalog_status"] = status
    if status != 200 or not isinstance(sessions, list) or len(sessions) != 1:
        report["http_error_code"] = "catalog_response_failed"
        raise _ProbeFailure("http_metrics_failed")
    session = sessions[0]
    if (not isinstance(session, dict) or session.get("provider") != "claude_code"
            or not isinstance(session.get("session_id"), str)
            or _PSEUDONYM.fullmatch(session["session_id"]) is None
            or not isinstance(session.get("project_id"), str)
            or _PSEUDONYM.fullmatch(session["project_id"]) is None):
        report["http_error_code"] = "catalog_contract_failed"
        raise _ProbeFailure("http_metrics_failed")
    status, payload, _cookie = _json_request(
        port, "GET", f"/v1/sessions/{session['session_id']}/metrics", auth=auth)
    report["metrics_status"] = status
    if status != 200 or payload.get("session_id") != session["session_id"]:
        report["http_error_code"] = "metrics_response_failed"
        raise _ProbeFailure("http_metrics_failed")
    rows = payload.get("metrics")
    tokens = _metric(rows, "usage.total_tokens")
    verification_count = _metric(rows, "verification.verification_count")
    pass_rate = _metric(rows, "verification.pass_rate")
    if verification_count is not None:
        report["verification_count_value"] = verification_count.get("numeric_value")
        report["verification_count_observed"] = verification_count.get("observed_count")
        report["verification_count_eligible"] = verification_count.get("eligible_count")
    if (tokens is None or tokens.get("numeric_value") is not None
            or tokens.get("text_value") is not None or tokens.get("unit") != "tokens"
            or tokens.get("observed_count") != 0 or tokens.get("eligible_count") != 1
            or tokens.get("coverage") != 0 or tokens.get("confidence") is not None
            or verification_count is None or verification_count.get("numeric_value") != 0
            or verification_count.get("observed_count") != 1
            or verification_count.get("eligible_count") != 1
            or verification_count.get("coverage") != 1
            or pass_rate is None or pass_rate.get("numeric_value") is not None
            or pass_rate.get("observed_count") != 0 or pass_rate.get("eligible_count") != 0):
        report["http_error_code"] = (
            "token_metric_failed" if tokens is None
            or tokens.get("numeric_value") is not None
            or tokens.get("observed_count") != 0
            or tokens.get("eligible_count") != 1 else "objective_metric_failed")
        raise _ProbeFailure("http_metrics_failed")
    report["http_error_code"] = None
    return 1, len(rows) if isinstance(rows, list) else 0


def _run_browser(node: Path, script: Path, executable: Path,
                 environment: dict[str, str], root: Path, port: int,
                 report: dict[str, object]) -> dict[str, object]:
    child = dict(environment)
    child.update(PE_PACKAGED_BASE_URL=f"http://127.0.0.1:{port}",
                 PE_PACKAGED_BROWSER_EXECUTABLE=os.fspath(executable))
    try:
        result = run_owned_process(
            (os.fspath(node), os.fspath(script)), cwd=root, env=child,
            stdout_limit=16_384, stderr_limit=16_384, timeout=90,
            maximum_active_processes=8,
        )
        report["browser_cleanup_confirmed"] = True
    except OwnedProcessRunError as error:
        report["browser_cleanup_confirmed"] = error.code in {
            "owned_process_timeout", "owned_process_stdout_limit", "owned_process_stderr_limit"}
        raise _ProbeFailure("browser_failed") from None
    receipt = _browser_receipt(result.stdout)
    report["browser_receipt"] = receipt
    report["browser_process_exit_zero"] = result.returncode == 0
    report["browser_stderr_empty"] = not result.stderr
    if result.returncode != 0 or result.stderr or not _browser_passed(receipt):
        raise _ProbeFailure("browser_failed")
    return receipt  # type: ignore[return-value]


def _complete(report: dict[str, object]) -> bool:
    return report.get("error_code") is None and all(
        report.get(key) is True for key in _RUNNER_FLAGS)


def probe(runtime: Path, candidate_manifest: Path, candidate_manifest_sha256: str,
          node: Path, script: Path, browser_executable: Path,
          artifact_root: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "contract": "packaged-analytics-runner.v1", "passed": False,
        "error_code": None, **dict.fromkeys(_RUNNER_FLAGS, False),
        "sessions_indexed": 0, "projects_indexed": 0, "stored_metrics": 0,
        "unknown_token_observations": 0, "objective_verifications": 0,
        "model_mutations": 0, "shutdown_kind": "owned_process_termination",
        "browser_receipt": None, "browser_process_exit_zero": False,
        "browser_stderr_empty": False,
        "catalog_status": None, "metrics_status": None, "http_error_code": None,
        "verification_count_value": None, "verification_count_observed": None,
        "verification_count_eligible": None,
    }
    if (sys.platform != "win32" or any(_checked_file(path) is None for path in (
            runtime / "python.exe", candidate_manifest, node, script, browser_executable))):
        report["error_code"] = "probe_inputs_unavailable"
        return report
    if _safe_external_root(artifact_root) is None:
        report["error_code"] = "artifact_root_unsafe"
        return report
    try:
        candidate, canonical = _manifest(candidate_manifest, candidate_manifest_sha256)
        _verify_candidate(runtime, candidate, canonical)
    except (PackError, OSError, ValueError):
        report["error_code"] = "candidate_invalid"
        return report
    if not _candidate_ui_bound(candidate):
        report["error_code"] = "candidate_ui_resource_missing"
        return report
    port = _ephemeral_loopback_port()
    if port in {8765, 8766} or not 1024 <= port <= 65535:
        report["error_code"] = "unsafe_probe_port"
        return report
    root = Path(tempfile.mkdtemp(prefix="packaged-analytics-", dir=artifact_root))
    server = capture = transcript = identity = None
    try:
        for name in ("temp", "empty-profile", "empty-codex", "empty-model-cache"):
            (root / name).mkdir()
        transcript, identity = _write_fixture(root)
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
        report["projects_indexed"] = 1
        _session_count, metric_count = _verify_http(port, report)
        report["stored_metrics"] = metric_count
        report["unknown_token_observations"] = 1
        report["objective_verifications"] = 0
        report["http_metrics_verified"] = True
        receipt = _run_browser(node, script, browser_executable, environment, root, port, report)
        report["browser_verified"] = True
        report["candidate_ui_entrypoint_verified"] = True
        report["model_mutations"] = receipt["model_mutation_requests"]
        if process_tree_exited(server):
            raise _ProbeFailure("server_exited_during_browser")
    except _ProbeFailure as error:
        report["error_code"] = error.code if error.code in _RUNNER_ERRORS else "probe_failed"
    except Exception:
        report["error_code"] = "probe_failed"
    finally:
        if server is not None:
            try:
                report["server_tree_stopped"] = terminate_owned_process(
                    server, graceful_timeout=.1, forced_timeout=3)
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
        report["fixture_unchanged"] = _fixture_matches(root, transcript, identity)
        if report["error_code"] is None and not report["fixture_unchanged"]:
            report["error_code"] = "fixture_changed"
        try:
            _verify_candidate(runtime, candidate, canonical)
            report["candidate_unchanged"] = True
        except Exception:
            if report["error_code"] is None:
                report["error_code"] = "candidate_changed"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if _port_is_released(port):
                report["port_released"] = True
                break
            time.sleep(.05)
        if report["error_code"] is None and not _complete(report):
            report["error_code"] = "cleanup_unconfirmed"
    report["passed"] = (_complete(report) and report["sessions_indexed"] == 1
        and report["projects_indexed"] == 1 and report["stored_metrics"] > 0
        and report["unknown_token_observations"] == 1
        and report["objective_verifications"] == 0 and report["model_mutations"] == 0)
    return report


def main(argv: list[str] | None = None) -> int:
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError() from None
    parser = Parser(description=__doc__)
    for name in ("runtime", "candidate-manifest", "node", "script",
                 "browser-executable", "artifact-root"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--candidate-manifest-sha256", required=True)
    try:
        args = parser.parse_args(argv)
        report = probe(args.runtime, args.candidate_manifest,
                       args.candidate_manifest_sha256, args.node, args.script,
                       args.browser_executable, args.artifact_root)
    except Exception:
        report = {"contract": "packaged-analytics-runner.v1", "passed": False,
                  "error_code": "invalid_arguments"}
    print("PACKAGED_ANALYTICS_RUNNER=" + json.dumps(
        report, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if report.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
