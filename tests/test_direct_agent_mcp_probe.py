"""Disposable live-listener acceptance for the direct Agent MCP probe."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys
import threading
import time

import pytest

from prompt_enhancer import desktop_overlay
from prompt_enhancer.application.agent_mcp_connections import (
    AgentMcpConnectionService,
    CreateAgentMcpConnection,
    RevokeAgentMcpConnection,
)
from prompt_enhancer.application.agent_catalog import (
    AgentCatalogService,
    CreateAgentProject,
)
from prompt_enhancer.infrastructure.sqlite.agent_catalog import (
    AgentCatalogSqliteDatabase,
    SqliteAgentCatalogRepository,
    SqliteAgentMcpConnectionRepository,
)
from prompt_enhancer.application.owned_process import OwnedProcessRunError
from prompt_enhancer.application import owned_process
from tests.support import direct_agent_mcp_probe
from tests.support.agent_mcp_integration_harness import (
    isolated_child_environment,
    run_bounded_owned_helper,
    start_ephemeral_owned_server,
)


REPOSITORY = Path(__file__).resolve().parents[1]
PROBE = REPOSITORY / "tests" / "support" / "direct_agent_mcp_probe.py"


class _ObservedOwnedProcess:
    def __init__(self, process) -> None:
        self._process = process
        self.tree_exited_before_close: bool | None = None
        self.streams_closed_before_close: bool | None = None
        self.close_result: bool | None = None

    def __getattr__(self, name: str):
        return getattr(self._process, name)

    def close(self, *, close_streams: bool = True) -> bool:
        self.tree_exited_before_close = (
            self._process.poll() is not None and self._process.tree_exited()
        )
        self.streams_closed_before_close = all(
            stream is None or stream.closed
            for stream in (
                self._process.stdin,
                self._process.stdout,
                self._process.stderr,
            )
        )
        self.close_result = self._process.close(close_streams=close_streams)
        return self.close_result


def _probe_environment(
    root: Path,
    *,
    endpoint: str,
    bearer: str,
) -> dict[str, str]:
    environment = isolated_child_environment(root)
    environment.update(
        {
            "PROMPT_ENHANCER_HOME": os.fspath(root / "isolated-application"),
            "PROMPT_ENHANCER_SESSION_READER": "disabled",
            "PROMPT_ENHANCER_AGENT_MCP_URL": endpoint,
            "PROMPT_ENHANCER_AGENT_MCP_TOKEN": bearer,
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return environment


def _run_probe(
    root: Path,
    *,
    endpoint: str,
    bearer: str,
    mode: str,
) -> dict[str, object]:
    completed = run_bounded_owned_helper(
        [sys.executable, os.fspath(PROBE), mode],
        cwd=root,
        environment=_probe_environment(root, endpoint=endpoint, bearer=bearer),
    )
    assert completed.returncode == 0
    assert completed.stderr == b""
    stdout = completed.stdout.decode("utf-8")
    assert bearer not in stdout
    prefix = "DIRECT_AGENT_MCP_PROBE="
    assert stdout.startswith(prefix)
    payload = json.loads(stdout.removeprefix(prefix))
    assert isinstance(payload, dict)
    return payload


def test_probe_uses_two_clients_then_proves_revocation_on_real_listener(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "direct-agent-mcp-probe"
    (root / "empty-provider").mkdir(parents=True)
    monkeypatch.setenv(
        "PROMPT_ENHANCER_CLAUDE_HOME",
        os.fspath(root / "empty-provider"),
    )
    settings, owned = start_ephemeral_owned_server(
        home=root / "application",
    )
    origin = ""
    try:
        application_token = settings.api_token_path.read_text(
            encoding="utf-8"
        ).strip()
        origin = desktop_overlay._wait_for_owned_service(
            owned.endpoints,
            application_token,
            owned,
        )
        database = AgentCatalogSqliteDatabase(settings.agent_catalog_path)
        scope_project = AgentCatalogService(
            SqliteAgentCatalogRepository(database),
            id_factory=lambda: "8" * 32,
        ).create_project(CreateAgentProject(name="Synthetic live probe project"))
        service = AgentMcpConnectionService(
            SqliteAgentMcpConnectionRepository(database),
            token_pepper=application_token,
            id_factory=lambda: "9" * 32,
        )
        private = service.create(
            CreateAgentMcpConnection(
                request_id="8" * 32,
                label="Synthetic live probe",
                client_kind="other",
                project_id=scope_project.project_id,
                allow_model_lifecycle=False,
            ),
            endpoint_url=origin + "/mcp/agent",
        )

        active = _run_probe(
            root,
            endpoint=private.endpoint_url,
            bearer=private.bearer_token,
            mode="--expect-active",
        )
        assert active == {
            "catalog_mutation_requested": False,
            "contract": "direct-agent-mcp-live-probe.v1",
            "default_tool_surface_exact": True,
            "discovery_contract_valid": True,
            "error_code": None,
            "independent_clients": 2,
            "loopback_endpoint_valid": True,
            "mode": "active",
            "model_lifecycle_absent": True,
            "protocol_valid": True,
            "server_identity_valid": True,
            "tool_count": 19,
        }

        revoked_connection = service.revoke(
            private.connection.connection_id,
            RevokeAgentMcpConnection(
                expected_revision=private.connection.revision,
            ),
        )
        assert revoked_connection.state == "revoked"
        revoked = _run_probe(
            root,
            endpoint=private.endpoint_url,
            bearer=private.bearer_token,
            mode="--expect-revoked",
        )
        assert revoked == {
            "contract": "direct-agent-mcp-live-probe.v1",
            "credential_rejected": True,
            "error_code": None,
            "loopback_endpoint_valid": True,
            "mode": "revoked",
            "rejection_status": 401,
        }
    finally:
        owned.stop()

    assert owned.lifecycle.cleanup_finished is True
    assert owned.thread.is_alive() is False
    if origin:
        port = int(origin.rsplit(":", 1)[1])
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_probe_endpoint_requires_explicit_valid_loopback_opt_in(monkeypatch) -> None:
    monkeypatch.delenv(direct_agent_mcp_probe.ENDPOINT_ENV, raising=False)
    with pytest.raises(
        direct_agent_mcp_probe.ProbeFailure,
        match="^endpoint_invalid$",
    ):
        direct_agent_mcp_probe._endpoint()

    for invalid in (
        "http://127.0.0.1:invalid/mcp/agent",
        "http://[invalid/mcp/agent",
    ):
        monkeypatch.setenv(direct_agent_mcp_probe.ENDPOINT_ENV, invalid)
        with pytest.raises(
            direct_agent_mcp_probe.ProbeFailure,
            match="^endpoint_invalid$",
        ):
            direct_agent_mcp_probe._endpoint()


def test_probe_opener_disables_redirects_and_response_read_is_bounded() -> None:
    opener = direct_agent_mcp_probe._opener()
    no_redirect = next(
        handler
        for handler in opener.handlers
        if isinstance(handler, direct_agent_mcp_probe._NoRedirect)
    )
    redirect_request = direct_agent_mcp_probe.Request(
        "http://127.0.0.1:49152/mcp/agent"
    )
    assert no_redirect.redirect_request(
        redirect_request,
        None,
        302,
        "synthetic-redirect",
        {},
        "http://127.0.0.1:49153/mcp/agent",
    ) is None

    class OversizedResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, amount: int) -> bytes:
            assert amount == direct_agent_mcp_probe.MAX_RESPONSE_BYTES + 1
            return b"x" * amount

    class SyntheticOpener:
        def open(self, *_args, **_kwargs):
            return OversizedResponse()

    with pytest.raises(
        direct_agent_mcp_probe.ProbeFailure,
        match="^mcp_response_too_large$",
    ):
        direct_agent_mcp_probe._post(
            SyntheticOpener(),
            endpoint="http://127.0.0.1:49152/mcp/agent",
            token="synthetic-token",
            message={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )


def test_listener_harness_hands_off_actual_ephemeral_socket_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_reserve = desktop_overlay._try_reserve_listener
    reservations = []
    owned = object()

    def reserve(address: str, port: int):
        assert (address, port) == ("127.0.0.1", 0)
        result = original_reserve(address, port)
        assert result is not None
        reservations.append(result)
        return result

    def start(settings):
        handed_off = desktop_overlay._reserve_owned_listener(
            settings,
            allow_ephemeral=False,
        )
        listener, selected, endpoints = handed_off
        assert selected is settings
        assert listener.fileno() >= 0
        assert listener.getsockname() == ("127.0.0.1", settings.port)
        assert endpoints == (("127.0.0.1", f"http://127.0.0.1:{settings.port}"),)
        return owned

    monkeypatch.setattr(desktop_overlay, "_try_reserve_listener", reserve)
    monkeypatch.setattr(desktop_overlay, "_start_owned_server", start)
    settings, actual_owned = start_ephemeral_owned_server(
        home=tmp_path / "application",
    )

    assert len(reservations) == 1
    listener = reservations[0][0]
    assert settings.port != 8765
    assert settings.port != 8766
    assert actual_owned is owned
    listener.close()


def test_listener_harness_closes_reservation_when_setup_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_reserve = desktop_overlay._try_reserve_listener
    listeners = []

    def reserve(address: str, port: int):
        result = original_reserve(address, port)
        assert result is not None
        listeners.append(result[0])
        return result

    def fail_start(_settings):
        raise RuntimeError("synthetic_setup_failure")

    monkeypatch.setattr(desktop_overlay, "_try_reserve_listener", reserve)
    monkeypatch.setattr(desktop_overlay, "_start_owned_server", fail_start)
    with pytest.raises(RuntimeError, match="^synthetic_setup_failure$"):
        start_ephemeral_owned_server(home=tmp_path / "application")

    assert len(listeners) == 1
    assert listeners[0].fileno() == -1


def test_owned_helper_reports_success_nonzero_stderr_and_spawn_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    environment = isolated_child_environment(tmp_path)
    processes: list[_ObservedOwnedProcess] = []
    visible_windows = []
    original_start = owned_process.start_owned_process

    def capture_start(*args, **kwargs):
        process = original_start(*args, **kwargs)
        visible_windows.append(process.visible_window_detected())
        observed = _ObservedOwnedProcess(process)
        processes.append(observed)
        return observed

    monkeypatch.setattr(owned_process, "start_owned_process", capture_start)
    success = run_bounded_owned_helper(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())",
        ],
        cwd=tmp_path,
        environment=environment,
        stdin_payload=b'{"jsonrpc":"2.0","id":1}\n',
        timeout=3,
    )
    assert success.returncode == 0
    assert success.stdout == b'{"jsonrpc":"2.0","id":1}\n'
    assert success.stderr == b""
    assert processes[-1].tree_exited_before_close is True
    assert processes[-1].streams_closed_before_close is True
    assert processes[-1].close_result is True

    failed = run_bounded_owned_helper(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; sys.stderr.write('synthetic-protocol-error'); raise SystemExit(7)",
        ],
        cwd=tmp_path,
        environment=environment,
        timeout=3,
    )
    assert failed.returncode == 7
    assert failed.stdout == b""
    assert failed.stderr == b"synthetic-protocol-error"
    assert processes[-1].tree_exited_before_close is True
    assert processes[-1].streams_closed_before_close is True
    assert processes[-1].close_result is True

    with pytest.raises(OwnedProcessRunError, match="^owned_process_stdout_limit$"):
        run_bounded_owned_helper(
            [sys.executable, "-I", "-c", "print('x' * 1024)"],
            cwd=tmp_path,
            environment=environment,
            timeout=3,
            stdout_limit=8,
        )

    with pytest.raises(
        OwnedProcessRunError,
        match="^owned_process_unavailable$",
    ):
        run_bounded_owned_helper(
            [os.fspath(tmp_path / "missing-synthetic-executable")],
            cwd=tmp_path,
            environment=environment,
            timeout=3,
        )
    assert visible_windows == [False, False, False]
    assert all(process.tree_exited_before_close is True for process in processes)
    assert all(process.close_result is True for process in processes)
    assert not any(
        thread.is_alive()
        and thread.name.startswith("prompt-enhancer-owned-")
        for thread in threading.enumerate()
    )


def test_owned_helper_timeout_reaps_child_before_delayed_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = tmp_path / "unexpected-survivor"
    processes: list[_ObservedOwnedProcess] = []
    original_start = owned_process.start_owned_process

    def capture_start(*args, **kwargs):
        process = original_start(*args, **kwargs)
        assert process.visible_window_detected() is False
        observed = _ObservedOwnedProcess(process)
        processes.append(observed)
        return observed

    monkeypatch.setattr(owned_process, "start_owned_process", capture_start)
    code = (
        "import pathlib,time; time.sleep(0.4); "
        f"pathlib.Path({str(marker)!r}).write_text('unexpected', encoding='utf-8')"
    )
    with pytest.raises(OwnedProcessRunError, match="^owned_process_timeout$"):
        run_bounded_owned_helper(
            [sys.executable, "-I", "-c", code],
            cwd=tmp_path,
            environment=isolated_child_environment(tmp_path),
            timeout=0.05,
        )
    time.sleep(0.6)
    assert not marker.exists()
    assert len(processes) == 1
    assert processes[0].tree_exited_before_close is True
    assert processes[0].streams_closed_before_close is True
    assert processes[0].close_result is True
    assert not any(
        thread.is_alive()
        and thread.name.startswith("prompt-enhancer-owned-")
        for thread in threading.enumerate()
    )
