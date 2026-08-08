from __future__ import annotations

import subprocess
import time
from collections.abc import Callable

import pytest

from prompt_enhancer.infrastructure.providers.codex_app_server.errors import (
    CodexProtocolViolation,
)
from prompt_enhancer.infrastructure.providers.codex_app_server.transports.stdio_jsonl import (
    NOTIFICATION_METHOD_ALLOWLIST,
    REQUEST_METHOD_ALLOWLIST,
    StdioJsonRpcTransport,
)


def test_transport_rejects_non_allowlisted_calls_before_process_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process_attempts: list[object] = []

    def forbidden_popen(*args: object, **_kwargs: object) -> object:
        process_attempts.extend(args)
        raise AssertionError("synthetic boundary test must not launch a process")

    monkeypatch.setattr(subprocess, "Popen", forbidden_popen)
    transport = StdioJsonRpcTransport()
    rejected_calls: tuple[Callable[[], object], ...] = (
        lambda: transport._request("thread/delete", {}),
        lambda: transport._request("thread/list", {}),
        lambda: transport._request("thread/list", {"useStateDbOnly": False}),
        lambda: transport._notify("thread/changed"),
        lambda: transport._notify("initialized"),
    )

    for call in rejected_calls:
        with pytest.raises(CodexProtocolViolation):
            call()

    assert process_attempts == []
    assert REQUEST_METHOD_ALLOWLIST == {"initialize", "thread/list", "thread/read"}
    assert NOTIFICATION_METHOD_ALLOWLIST == {"initialized"}


def test_transport_rejects_an_invalid_json_rpc_version_without_starting() -> None:
    transport = StdioJsonRpcTransport()
    transport._lines.put(b'{"jsonrpc":"1.0","id":1,"result":{}}\n')

    with pytest.raises(CodexProtocolViolation):
        transport._next_message(deadline=time.monotonic() + 1)

    assert transport._process is None


def test_transport_accepts_current_headerless_app_server_frame() -> None:
    transport = StdioJsonRpcTransport()
    transport._lines.put(b'{"id":1,"result":{}}\n')

    assert transport._next_message(deadline=time.monotonic() + 1) == {
        "id": 1,
        "result": {},
    }
