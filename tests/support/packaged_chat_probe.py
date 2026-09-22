"""Bounded packaged-runtime probe for an empty model-free retained Agent chat.

This driver is for a separately reviewed staged-runtime invocation.  It uses
only public loopback HTTP, an isolated retained application home, a fictional
empty workspace, and browser cookie/CSRF authentication.  It never reads app
token files, provider data, credentials, model caches, or response content for
diagnostics, and it deliberately sends no chat message that could invoke a
model.  Its scope is catalog metadata and cold-restart reopenability, not
message persistence or browser rendering.
"""

from __future__ import annotations

from http.cookies import CookieError, SimpleCookie
import http.client
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
from typing import Any

from packaged_serve_probe import (
    _capture_threads,
    _environment,
    _ephemeral_loopback_port,
    _port_is_released,
    _startup_diagnostic,
)
from prompt_enhancer.application.owned_process import (
    process_tree_exited,
    start_owned_process,
    terminate_owned_process,
)


_STARTUP_TIMEOUT_SECONDS = 30.0
_HTTP_TIMEOUT_SECONDS = 1.0
_MAX_HTTP_BYTES = 128 * 1024
_RELEASE_TIMEOUT_SECONDS = 5.0
_PROJECT_ID = re.compile(r"^[0-9a-f]{32}$", flags=re.ASCII)
_SESSION_ID = re.compile(r"^[0-9a-f]{32}$", flags=re.ASCII)
_COOKIE_NAME = "prompt_enhancer_session"
_CSRF_HEADER = "X-Prompt-Enhancer-CSRF"
_PROJECT_NAME = "Synthetic packaged recovery project"
_CHAT_TITLE = "Synthetic packaged recovery chat"


class _ProbeFailure(RuntimeError):
    """A content-free expected probe failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _BrowserAuth:
    def __init__(self, cookie: str, csrf: str) -> None:
        self.cookie = cookie
        self.csrf = csrf


def _json_request(
    port: int,
    method: str,
    path: str,
    *,
    auth: _BrowserAuth | None = None,
    body: dict[str, object] | None = None,
    include_csrf: bool = True,
    timeout_seconds: int | float = _HTTP_TIMEOUT_SECONDS,
) -> tuple[int, dict[str, Any], str | None]:
    if (
        type(timeout_seconds) not in {int, float}
        or not 0 < timeout_seconds <= 20
    ):
        raise _ProbeFailure("http_timeout_invalid")
    payload = None
    headers = {"Accept": "application/json"}
    if body is not None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(payload))
    if auth is not None:
        headers["Cookie"] = f"{_COOKIE_NAME}={auth.cookie}"
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            headers["Origin"] = f"http://127.0.0.1:{port}"
            if include_csrf:
                headers[_CSRF_HEADER] = auth.csrf
    connection = http.client.HTTPConnection(
        "127.0.0.1", port, timeout=timeout_seconds
    )
    try:
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        content_type = response.getheader("Content-Type", "")
        set_cookie = response.getheader("Set-Cookie")
        content = response.read(_MAX_HTTP_BYTES + 1)
        if len(content) > _MAX_HTTP_BYTES:
            raise _ProbeFailure("http_response_over_budget")
        if "application/json" not in content_type.casefold():
            raise _ProbeFailure("http_response_not_json")
        try:
            decoded = json.loads(content)
        except (UnicodeDecodeError, ValueError):
            raise _ProbeFailure("http_response_invalid_json") from None
        if not isinstance(decoded, dict):
            raise _ProbeFailure("http_response_shape_mismatch")
        return response.status, decoded, set_cookie
    finally:
        connection.close()


def _fresh_browser_auth(port: int) -> _BrowserAuth:
    status, payload, set_cookie = _json_request(port, "GET", "/auth/session")
    if status != 200 or not isinstance(payload.get("csrf_token"), str):
        raise _ProbeFailure("browser_auth_unavailable")
    csrf = payload["csrf_token"]
    if not csrf or len(csrf) > 512 or set_cookie is None:
        raise _ProbeFailure("browser_auth_contract_mismatch")
    parsed = SimpleCookie()
    try:
        parsed.load(set_cookie)
        cookie = parsed[_COOKIE_NAME].value
    except (KeyError, ValueError, CookieError):
        raise _ProbeFailure("browser_cookie_contract_mismatch") from None
    if not cookie or len(cookie) > 512:
        raise _ProbeFailure("browser_cookie_contract_mismatch")
    return _BrowserAuth(cookie, csrf)


def _require_status(
    result: tuple[int, dict[str, Any], str | None],
    expected: int,
    code: str,
) -> dict[str, Any]:
    status, payload, _set_cookie = result
    if status != expected:
        raise _ProbeFailure(code)
    return payload


def _await_ready(process, port: int, overflows: list[threading.Event]) -> None:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if any(item.is_set() for item in overflows):
            raise _ProbeFailure("server_output_limit")
        try:
            status, payload, _cookie = _json_request(port, "GET", "/health")
            if status == 200 and payload == {
                "status": "ok",
                "cost_mode": "offline_only",
                "data_tier": "metadata",
            }:
                return
        except (OSError, http.client.HTTPException, _ProbeFailure):
            pass
        if process_tree_exited(process):
            raise _ProbeFailure("server_exited_before_ready")
        time.sleep(0.1)
    raise _ProbeFailure("health_timeout")


def _create_model_free_chat(
    port: int,
    auth: _BrowserAuth,
    workspace: Path,
) -> tuple[str, str, int, int]:
    unauthenticated, _payload, _cookie = _json_request(
        port, "GET", "/v1/agent/projects"
    )
    if unauthenticated != 401:
        raise _ProbeFailure("catalog_authentication_not_enforced")
    missing_csrf, _payload, _cookie = _json_request(
        port,
        "POST",
        "/v1/agent/projects",
        auth=auth,
        body={"name": _PROJECT_NAME},
        include_csrf=False,
    )
    if missing_csrf != 403:
        raise _ProbeFailure("catalog_csrf_not_enforced")
    empty_catalog = _require_status(
        _json_request(port, "GET", "/v1/agent/projects", auth=auth),
        200,
        "catalog_precondition_get_failed",
    )
    if empty_catalog.get("projects") != []:
        raise _ProbeFailure("rejected_create_changed_catalog")

    project = _require_status(
        _json_request(
            port,
            "POST",
            "/v1/agent/projects",
            auth=auth,
            body={"name": _PROJECT_NAME},
        ),
        201,
        "project_create_failed",
    )
    project_id = project.get("project_id")
    if (
        not isinstance(project_id, str)
        or _PROJECT_ID.fullmatch(project_id) is None
        or project.get("name") != _PROJECT_NAME
    ):
        raise _ProbeFailure("project_create_contract_mismatch")
    created_catalog = _require_status(
        _json_request(port, "GET", "/v1/agent/projects", auth=auth),
        200,
        "created_catalog_get_failed",
    )
    projects = created_catalog.get("projects")
    if (
        not isinstance(projects, list)
        or len(projects) != 1
        or not isinstance(projects[0], dict)
        or projects[0].get("project_id") != project_id
    ):
        raise _ProbeFailure("project_create_count_mismatch")

    chat = _require_status(
        _json_request(
            port,
            "POST",
            "/v1/agent/sessions",
            auth=auth,
            body={
                "workspace": os.fspath(workspace),
                "project_id": project_id,
                "title": _CHAT_TITLE,
                "retention_policy": "local_history",
                "allow_writes": False,
                "allow_commands": False,
                "allow_web": False,
            },
        ),
        201,
        "chat_create_failed",
    )
    session_id = chat.get("session_id")
    settings = chat.get("settings")
    if (
        not isinstance(session_id, str)
        or _SESSION_ID.fullmatch(session_id) is None
        or not isinstance(settings, dict)
        or settings.get("project_id") != project_id
        or settings.get("title") != _CHAT_TITLE
        or settings.get("model_alias") is not None
        or chat.get("model_alias") is not None
        or settings.get("retention_policy") != "local_history"
        or settings.get("allow_writes") is not False
        or settings.get("allow_commands") is not False
        or settings.get("allow_web") is not False
    ):
        raise _ProbeFailure("chat_create_contract_mismatch")

    record = _require_status(
        _json_request(
            port,
            "GET",
            f"/v1/agent/catalog/sessions/{session_id}",
            auth=auth,
        ),
        200,
        "created_chat_get_failed",
    )
    revision = record.get("revision")
    history_revision = record.get("history_revision")
    if (
        record.get("project_id") != project_id
        or record.get("title") != _CHAT_TITLE
        or record.get("model_alias") is not None
        or record.get("retention_policy") != "local_history"
        or record.get("history_state") != "durable_local"
        or record.get("conversation_available") is not True
        or not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision < 1
        or not isinstance(history_revision, int)
        or isinstance(history_revision, bool)
        or history_revision < 0
    ):
        raise _ProbeFailure("created_chat_metadata_mismatch")
    return project_id, session_id, revision, history_revision


def _verify_and_resume(
    port: int,
    auth: _BrowserAuth,
    project_id: str,
    session_id: str,
) -> None:
    project = _require_status(
        _json_request(
            port,
            "GET",
            f"/v1/agent/projects/{project_id}",
            auth=auth,
        ),
        200,
        "restarted_project_get_failed",
    )
    record = _require_status(
        _json_request(
            port,
            "GET",
            f"/v1/agent/catalog/sessions/{session_id}",
            auth=auth,
        ),
        200,
        "restarted_chat_get_failed",
    )
    revision = record.get("revision")
    history_revision = record.get("history_revision")
    if (
        project.get("project_id") != project_id
        or project.get("name") != _PROJECT_NAME
        or record.get("session_id") != session_id
        or record.get("project_id") != project_id
        or record.get("title") != _CHAT_TITLE
        or record.get("model_alias") is not None
        or record.get("retention_policy") != "local_history"
        or record.get("history_state") != "durable_local"
        or record.get("conversation_available") is not True
        or not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision < 1
        or not isinstance(history_revision, int)
        or isinstance(history_revision, bool)
        or history_revision < 0
    ):
        raise _ProbeFailure("restarted_metadata_mismatch")

    resumed = _require_status(
        _json_request(
            port,
            "POST",
            f"/v1/agent/projects/{project_id}/sessions/{session_id}/resume",
            auth=auth,
            body={
                "expected_catalog_revision": revision,
                "expected_history_revision": history_revision,
            },
        ),
        200,
        "chat_resume_failed",
    )
    settings = resumed.get("settings")
    if (
        resumed.get("session_id") != session_id
        or resumed.get("recovered") is not True
        or resumed.get("authority_revalidated") is not False
        or resumed.get("model_alias") is not None
        or not isinstance(settings, dict)
        or settings.get("model_alias") is not None
        or settings.get("project_id") != project_id
        or settings.get("title") != _CHAT_TITLE
        or settings.get("allow_writes") is not False
        or settings.get("allow_commands") is not False
        or settings.get("allow_web") is not False
    ):
        raise _ProbeFailure("chat_resume_contract_mismatch")


def probe(runtime_root: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "contract": "packaged-chat-probe.v1",
        "runtime_python_present": False,
        "launches_started": 0,
        "launches_ready": 0,
        "browser_auth_sessions": 0,
        "security_rejections_verified": 0,
        "projects_created": 0,
        "chats_created": 0,
        "model_free_create_verified": False,
        "restart_metadata_verified": False,
        "resumes_verified": 0,
        "model_free_resume_verified": False,
        "owned_trees_stopped": 0,
        "process_handles_closed": 0,
        "ports_released": 0,
        "shutdown_kind": "owned_process_termination",
        "retained_artifact": False,
        "error_code": None,
    }
    executable = runtime_root / "python.exe"
    if sys.platform != "win32" or not executable.is_file():
        report["error_code"] = "runtime_unavailable"
        return report
    report["runtime_python_present"] = True

    artifact_root = Path(__file__).resolve().parents[2] / "test-results"
    artifact_root.mkdir(parents=True, exist_ok=True)
    # Intentionally retained for review.  The probe never prints this path and
    # never deletes or rewrites the resulting application database.
    root = Path(tempfile.mkdtemp(prefix="packaged-chat-probe-", dir=artifact_root))
    report["retained_artifact"] = True
    for directory in (
        root / "temp",
        root / "empty-profile",
        root / "empty-claude",
        root / "empty-codex",
        root / "empty-model-cache",
        root / "workspace",
    ):
        directory.mkdir()

    project_id: str | None = None
    session_id: str | None = None
    try:
        for launch_index in range(2):
            process = None
            threads: list[threading.Thread] = []
            buffers: list[bytearray] = []
            overflows: list[threading.Event] = []
            port = _ephemeral_loopback_port()
            launch_failure: _ProbeFailure | None = None
            try:
                env = _environment(runtime_root, root, port)
                process = start_owned_process(
                    (
                        os.fspath(executable),
                        "-I",
                        "-B",
                        "-m",
                        "prompt_enhancer",
                        "serve",
                    ),
                    cwd=root,
                    env=env,
                    capture_stdout=True,
                    capture_stderr=True,
                    maximum_active_processes=4,
                )
                threads, buffers, overflows = _capture_threads(process)
                report["launches_started"] = int(report["launches_started"]) + 1
                _await_ready(process, port, overflows)
                report["launches_ready"] = int(report["launches_ready"]) + 1
                auth = _fresh_browser_auth(port)
                report["browser_auth_sessions"] = int(
                    report["browser_auth_sessions"]
                ) + 1
                if launch_index == 0:
                    project_id, session_id, _revision, _history_revision = (
                        _create_model_free_chat(port, auth, root / "workspace")
                    )
                    report["projects_created"] = 1
                    report["chats_created"] = 1
                    report["security_rejections_verified"] = 2
                    report["model_free_create_verified"] = True
                else:
                    if project_id is None or session_id is None:
                        raise _ProbeFailure("restart_identity_unavailable")
                    _verify_and_resume(port, auth, project_id, session_id)
                    report["restart_metadata_verified"] = True
                    report["resumes_verified"] = 1
                    report["model_free_resume_verified"] = True
            except _ProbeFailure as error:
                launch_failure = error
            except (OSError, http.client.HTTPException):
                launch_failure = _ProbeFailure("loopback_request_failed")
            except Exception:
                launch_failure = _ProbeFailure("packaged_chat_probe_failed")
            finally:
                stopped = False
                closed = False
                if process is not None:
                    stopped = terminate_owned_process(
                        process,
                        graceful_timeout=0.1,
                        forced_timeout=2.0,
                    )
                    if stopped:
                        report["owned_trees_stopped"] = int(
                            report["owned_trees_stopped"]
                        ) + 1
                    try:
                        closed = bool(process.close(close_streams=True))
                    except Exception:
                        closed = False
                    if closed:
                        report["process_handles_closed"] = int(
                            report["process_handles_closed"]
                        ) + 1
                    for thread in threads:
                        thread.join(timeout=1.0)
                released = False
                release_deadline = time.monotonic() + _RELEASE_TIMEOUT_SECONDS
                while time.monotonic() < release_deadline:
                    if _port_is_released(port):
                        released = True
                        report["ports_released"] = int(report["ports_released"]) + 1
                        break
                    time.sleep(0.05)
                if launch_failure is None and not (stopped and closed and released):
                    launch_failure = _ProbeFailure("serve_cleanup_unconfirmed")
                if launch_failure is not None and launch_failure.code in {
                    "server_exited_before_ready",
                    "health_timeout",
                }:
                    report["startup_diagnostic"] = _startup_diagnostic(buffers)
            if launch_failure is not None:
                raise launch_failure
    except _ProbeFailure as error:
        report["error_code"] = error.code
    except Exception:
        report["error_code"] = "packaged_chat_probe_failed"
    return report


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print('PACKAGED_CHAT_PROBE={"error_code":"invalid_arguments"}')
        return 2
    report = probe(Path(arguments[0]))
    print(
        "PACKAGED_CHAT_PROBE="
        + json.dumps(report, sort_keys=True, separators=(",", ":")),
        flush=True,
    )
    passed = (
        report.get("runtime_python_present") is True
        and report.get("launches_started") == 2
        and report.get("launches_ready") == 2
        and report.get("browser_auth_sessions") == 2
        and report.get("security_rejections_verified") == 2
        and report.get("projects_created") == 1
        and report.get("chats_created") == 1
        and report.get("model_free_create_verified") is True
        and report.get("restart_metadata_verified") is True
        and report.get("resumes_verified") == 1
        and report.get("model_free_resume_verified") is True
        and report.get("owned_trees_stopped") == 2
        and report.get("process_handles_closed") == 2
        and report.get("ports_released") == 2
        and report.get("retained_artifact") is True
        and report.get("error_code") is None
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
