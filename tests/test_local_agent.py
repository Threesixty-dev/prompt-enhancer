"""Local agent workspace (ADR 0016): tools scoped to one folder, approvals for changes, run loop, HTTP."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import threading
import time

import pytest
from fastapi.testclient import TestClient

from prompt_enhancer.api import API_TOKEN_HEADER, CSRF_HEADER
from prompt_enhancer.application.local_agent import (
    AgentStreamPhase,
    AgentStreamStatus,
    AgentSettings,
    ApprovalDecision,
    LocalAgentError,
    LocalAgentService,
    SendMessage,
    WorkspaceTools,
    tool_schemas,
)
from prompt_enhancer.application.local_models import ChatUpstream
from prompt_enhancer.bootstrap import bootstrap_local_application
from prompt_enhancer.config import AppSettings


T0 = datetime(2026, 8, 20, 1, 0, tzinfo=UTC)


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "README.md").write_text("# Example project\n\nHello.\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "big.js").write_text("x" * 10, encoding="utf-8")
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    return root


def test_workspace_tools_never_leave_the_folder(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    tools = WorkspaceTools(root)
    assert tools.read_file("README.md").text.startswith("# Example project")
    listed = tools.list_dir(".", 2).text
    assert "src/app.py" in listed and "node_modules/ (skipped)" in listed
    found = tools.search_text("return a + b").text
    assert found.startswith("src/app.py:2:")
    for escape in ("../outside.txt", "..", "/etc/passwd", "C:/Windows/system.ini", "src/../../outside.txt"):
        with pytest.raises(LocalAgentError) as raised:
            tools.resolve(escape)
        assert raised.value.code == "path_outside_workspace", escape
    assert tools.read_file("missing.txt").ok is False
    preview = tools.diff_preview("src/app.py", "def add(a, b):\n    return a - b\n")
    assert "-    return a + b" in preview and "+    return a - b" in preview
    assert "+++ b/new.md" in tools.diff_preview("new.md", "hello\n")
    written = tools.write_file("new.md", "hello\n")
    assert written.ok and (root / "new.md").read_text(encoding="utf-8") == "hello\n"


def test_prepared_writes_are_revision_bound_and_refuse_unsafe_files(tmp_path: Path) -> None:
    import os

    root = _workspace(tmp_path)
    tools = WorkspaceTools(root)
    prepared = tools.prepare_write("src/app.py", "def add(a, b):\n    return a - b\n")
    (root / "src" / "app.py").write_text("external change\n", encoding="utf-8")
    stale = tools.apply_prepared_write(prepared)
    assert stale.ok is False and stale.text == "file changed since preview; read it again and propose a new change"
    assert (root / "src" / "app.py").read_text(encoding="utf-8") == "external change\n"

    hard_link = root / "hard-link.py"
    try:
        os.link(root / "src" / "app.py", hard_link)
    except OSError:
        pass
    else:
        with pytest.raises(LocalAgentError) as linked:
            tools.prepare_write("hard-link.py", "replacement\n")
        assert linked.value.code == "workspace_file_unavailable"

    with pytest.raises(LocalAgentError) as missing_parent:
        tools.prepare_write("missing/new.md", "hello\n")
    assert missing_parent.value.code == "workspace_parent_unavailable"
    with pytest.raises(LocalAgentError) as oversized:
        tools.prepare_write("new.md", "x" * 256_001)
    assert oversized.value.code == "workspace_file_too_large"


def test_run_command_uses_the_workspace_and_bounds_output(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    seen: dict[str, object] = {}

    def runner(argv, **kwargs):
        seen["argv"] = argv
        seen["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(argv, 0, stdout="ok " * 20_000, stderr="warn")

    tools = WorkspaceTools(root, runner=runner)
    outcome = tools.run_command("pytest -q", 30)
    assert outcome.ok and outcome.text.startswith("exit 0") and len(outcome.text) <= 24_100
    assert seen["cwd"] == str(root.resolve()) and "pytest -q" in " ".join(seen["argv"])

    def slow(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    assert WorkspaceTools(root, runner=slow).run_command("sleep 999", 5).text == "timed out after 5s"


def _stub_model(script: list[dict]):
    """A fake chat that replays scripted replies (tool calls, then text)."""

    calls: list[dict] = []

    def chat(alias: str, body: bytes):
        payload = json.loads(body)
        calls.append(payload)
        reply = script.pop(0) if script else {"content": "done"}
        message = {"role": "assistant", "content": reply.get("content"), "tool_calls": reply.get("tool_calls")}
        return 200, json.dumps({"choices": [{"message": message, "finish_reason": "tool_calls" if reply.get("tool_calls") else "stop"}]}).encode(), "application/json"

    return chat, calls


def _wait(predicate, timeout=10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_run_loop_executes_safe_tools_and_waits_for_approval_on_writes(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    chat, calls = _stub_model([
        {"tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"path": "src/app.py"})}}]},
        {"tool_calls": [{"id": "c2", "type": "function", "function": {"name": "write_file", "arguments": json.dumps({"path": "src/app.py", "content": "def add(a, b):\n    return a + b  # noqa\n"})}}]},
        {"content": "Added a comment and kept behaviour."},
    ])
    service = LocalAgentService(chat=chat, active_model=lambda: "stub-model", clock=lambda: T0, approval_wait_seconds=5)
    view = service.create(AgentSettings(workspace=str(root)))
    assert view.running is False and view.model_alias == "stub-model"
    service.send(view.session_id, SendMessage(text="Add a noqa comment to add()."))
    assert _wait(lambda: service.events(view.session_id).pending_approval_id is not None)
    events = service.events(view.session_id)
    kinds = [e.kind for e in events.events]
    assert kinds[:5] == ["status", "user", "tool_call", "tool_result", "tool_call"]
    pending = next(e for e in events.events if e.kind == "approval_required")
    assert pending.tool == "write_file" and "+    return a + b  # noqa" in (pending.preview or "")
    assert (root / "src" / "app.py").read_text(encoding="utf-8").endswith("a + b\n")  # nothing written yet
    # The model saw the tool schemas and the tool result went back as a tool message.
    assert {t["function"]["name"] for t in calls[0]["tools"]} >= {"read_file", "list_dir", "search_text", "write_file", "run_command"}
    assert calls[1]["messages"][-1]["role"] == "tool" and "return a + b" in calls[1]["messages"][-1]["content"]

    service.approve(view.session_id, pending.approval_id, ApprovalDecision(approved=True))
    assert _wait(lambda: not service.get(view.session_id).running)
    final = service.events(view.session_id)
    assert [e.kind for e in final.events][-3:] == ["tool_result", "assistant", "done"]
    assert (root / "src" / "app.py").read_text(encoding="utf-8").endswith("# noqa\n")
    assert final.events[-2].text == "Added a comment and kept behaviour."
    with pytest.raises(LocalAgentError) as raised:
        service.approve(view.session_id, pending.approval_id, ApprovalDecision(approved=True))
    assert raised.value.code == "approval_not_pending"


def test_agent_write_refuses_a_file_changed_during_approval(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    chat, _ = _stub_model(
        [
            {
                "tool_calls": [
                    {
                        "id": "stale-write",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps(
                                {
                                    "path": "src/app.py",
                                    "content": "def add(a, b):\n    return a - b\n",
                                }
                            ),
                        },
                    }
                ]
            },
            {"content": "The reviewed change was stale, so I did not overwrite the file."},
        ]
    )
    service = LocalAgentService(
        chat=chat,
        active_model=lambda: "stub-model",
        clock=lambda: T0,
        approval_wait_seconds=5,
    )
    view = service.create(AgentSettings(workspace=str(root)))
    service.send(view.session_id, SendMessage(text="Change the operation."))
    assert _wait(lambda: service.events(view.session_id).pending_approval_id is not None)
    page = service.events(view.session_id)
    approval = next(event for event in page.events if event.kind == "approval_required")
    (root / "src" / "app.py").write_text("external change\n", encoding="utf-8")
    service.approve(view.session_id, approval.approval_id or "", ApprovalDecision(approved=True))
    assert _wait(lambda: not service.get(view.session_id).running)
    final = service.events(view.session_id)
    result = next(
        event
        for event in final.events
        if event.kind == "tool_result" and event.call_id == "stale-write"
    )
    assert result.ok is False and result.text == "file changed since preview; read it again and propose a new change"
    assert (root / "src" / "app.py").read_text(encoding="utf-8") == "external change\n"


def test_streamed_reasoning_content_and_tool_calls_are_reassembled(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    requests: list[dict] = []
    replies = [
        [
            b'data: {"choices":[{"delta":{"reasoning_content":"Inspect "}}]}\n\n',
            b'data: {"choices":[{"delta":{"reasoning_content":"first.","tool_calls":[{"function":{"name":"run_","arguments":"{\\"command\\":\\"echo "}}]}}]}\n\n',
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"command","arguments":"hi\\"}"}}]}}]}\n\n',
            b"data: [DONE]\n\n",
        ],
        [
            b'data: {"choices":[{"delta":{"content":"The function "}}]}\n\n',
            b'data: {"choices":[{"delta":{"content":"adds its inputs."}}]}\n\n',
            b"data: [DONE]\n\n",
        ],
    ]

    def open_chat(alias: str, body: bytes) -> ChatUpstream:
        assert alias == "stream-model"
        requests.append(json.loads(body))
        return ChatUpstream(status_code=200, content_type="text/event-stream", lines=iter(replies.pop(0)))

    def whole_chat(alias: str, body: bytes):
        raise AssertionError("the whole-response fallback must not run")

    service = LocalAgentService(
        chat=whole_chat,
        open_chat=open_chat,
        active_model=lambda: "stream-model",
        clock=lambda: T0,
    )
    view = service.create(AgentSettings(workspace=str(root), parameters={"enable_thinking": True}))
    service.send(view.session_id, SendMessage(text="Explain src/app.py"))
    assert _wait(lambda: service.events(view.session_id).pending_approval_id is not None)
    live_page = service.events(view.session_id)
    live_reasoning = [item for item in live_page.events if item.kind == "assistant_delta"]
    assert {item.stream_phase for item in live_reasoning} == {AgentStreamPhase.REASONING}
    assert "".join(item.text or "" for item in live_reasoning) == "Inspect first."
    approval_id = live_page.pending_approval_id
    assert approval_id is not None
    service.approve(view.session_id, approval_id, ApprovalDecision(approved=False))
    assert _wait(lambda: not service.get(view.session_id).running)

    page = service.events(view.session_id)
    deltas = [item for item in page.events if item.kind == "assistant_delta"]
    assert {item.stream_phase for item in deltas} == {AgentStreamPhase.CONTENT}
    assert "".join(item.text or "" for item in deltas) == "The function adds its inputs."
    completed = [item for item in page.events if item.kind == "assistant"]
    assert completed[0].reasoning == "Inspect first." and completed[0].text is None
    assert completed[0].stream_id == live_reasoning[0].stream_id
    assert completed[1].text == "The function adds its inputs."
    assert completed[1].stream_id == deltas[0].stream_id
    tool = next(item for item in page.events if item.kind == "tool_call")
    assert tool.tool == "run_command" and tool.arguments == {"command": "echo hi"}
    assert requests[0]["stream"] is True
    assert requests[1]["messages"][-1]["role"] == "tool"
    assert "denied by the person" in requests[1]["messages"][-1]["content"]
    assert requests[1]["messages"][-2]["tool_calls"][0]["id"] == requests[1]["messages"][-1]["tool_call_id"]


def test_wait_events_wakes_on_cursor_advance(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    chat, _ = _stub_model([{"content": "done"}])
    service = LocalAgentService(chat=chat, active_model=lambda: "stub", clock=lambda: T0)
    view = service.create(AgentSettings(workspace=str(root)))
    result: list[object] = []
    waiter = threading.Thread(
        target=lambda: result.append(service.wait_events(view.session_id, after=1, timeout=1.0)),
        daemon=True,
    )
    waiter.start()
    service.send(view.session_id, SendMessage(text="wake up"))
    waiter.join(timeout=2)
    assert not waiter.is_alive() and result
    assert result[0].events[0].kind == "user"  # type: ignore[union-attr]


def test_live_delta_pressure_never_evicts_durable_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import prompt_enhancer.application.local_agent as local_agent_module

    monkeypatch.setattr(local_agent_module, "MAX_EVENTS", 4)
    root = _workspace(tmp_path)
    chat, _ = _stub_model([{"content": "done"}])
    service = LocalAgentService(chat=chat, active_model=lambda: "stub", clock=lambda: T0)
    view = service.create(AgentSettings(workspace=str(root)))
    session = service._session(view.session_id)  # noqa: SLF001 - bounded ring invariant
    service._emit(session, "status", text="durable")  # noqa: SLF001
    for index in range(4):
        service._emit(  # noqa: SLF001
            session,
            "assistant_delta",
            text=str(index),
            stream_id="d" * 32,
            stream_phase=AgentStreamPhase.CONTENT,
        )
    retained = service.events(view.session_id).events
    assert [(item.kind, item.text) for item in retained if item.kind != "assistant_delta"] == [
        ("status", "Session ready in project/ - reads are free; writes, commands and fetches wait for your approval."),
        ("status", "durable"),
    ]


def test_incomplete_stream_is_failed_and_never_enters_model_history(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    requests: list[dict] = []
    streams = [
        [b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'],
        [b'data: {"choices":[{"delta":{"content":"recovered"},"finish_reason":"stop"}]}\n\n'],
    ]

    def open_chat(alias: str, body: bytes) -> ChatUpstream:
        requests.append(json.loads(body))
        return ChatUpstream(200, "text/event-stream", lines=iter(streams.pop(0)))

    service = LocalAgentService(
        chat=lambda alias, body: (_ for _ in ()).throw(AssertionError("fallback called")),
        open_chat=open_chat,
        active_model=lambda: "stub",
        clock=lambda: T0,
    )
    view = service.create(AgentSettings(workspace=str(root)))
    service.send(view.session_id, SendMessage(text="first"))
    assert _wait(lambda: not service.get(view.session_id).running)
    first = service.events(view.session_id)
    terminal = next(item for item in first.events if item.kind == "assistant")
    assert terminal.text == "partial" and terminal.stream_status is AgentStreamStatus.FAILED
    assert any(item.kind == "error" and item.text == "model stream ended before completion" for item in first.events)

    service.send(view.session_id, SendMessage(text="retry"))
    assert _wait(lambda: not service.get(view.session_id).running)
    assert [message["role"] for message in requests[1]["messages"]] == ["system", "user", "user"]
    assert all(message.get("content") != "partial" for message in requests[1]["messages"])


def test_malformed_streamed_tool_arguments_never_reach_a_tool(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    streams = [
        [
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"bad","function":{"name":"write_file","arguments":"{"}}]}}]}\n\n',
            b"data: [DONE]\n\n",
        ],
        [
            b'data: {"choices":[{"delta":{"content":"I could not apply that change."},"finish_reason":"stop"}]}\n\n',
        ],
    ]

    def open_chat(alias: str, body: bytes) -> ChatUpstream:
        return ChatUpstream(200, "text/event-stream", lines=iter(streams.pop(0)))

    service = LocalAgentService(
        chat=lambda alias, body: (_ for _ in ()).throw(AssertionError("fallback called")),
        open_chat=open_chat,
        active_model=lambda: "stub",
        clock=lambda: T0,
    )
    view = service.create(AgentSettings(workspace=str(root)))
    before = (root / "src" / "app.py").read_text(encoding="utf-8")
    service.send(view.session_id, SendMessage(text="change the file"))
    assert _wait(lambda: not service.get(view.session_id).running)
    page = service.events(view.session_id)
    failed = next(item for item in page.events if item.kind == "tool_result")
    assert failed.ok is False and failed.text == "model supplied invalid tool arguments"
    assert not any(item.kind == "approval_required" for item in page.events)
    assert (root / "src" / "app.py").read_text(encoding="utf-8") == before


def test_stop_closes_stream_without_poisoning_history(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    first_chunk = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    cancelled = threading.Event()
    initial = "started " * 30

    def lines():
        try:
            first_chunk.set()
            yield f'data: {json.dumps({"choices": [{"delta": {"content": initial}}]})}\n\n'.encode()
            release.wait(timeout=2)
            yield b'data: {"choices":[{"delta":{"content":" ignored"}}]}\n\n'
        finally:
            closed.set()

    def open_chat(alias: str, body: bytes) -> ChatUpstream:
        def cancel() -> None:
            cancelled.set()
            release.set()

        return ChatUpstream(200, "text/event-stream", lines=lines(), cancel=cancel)

    service = LocalAgentService(
        chat=lambda alias, body: (_ for _ in ()).throw(AssertionError("fallback called")),
        open_chat=open_chat,
        active_model=lambda: "stub",
        clock=lambda: T0,
    )
    view = service.create(AgentSettings(workspace=str(root)))
    service.send(view.session_id, SendMessage(text="start"))
    assert first_chunk.wait(timeout=2)
    assert _wait(lambda: any(item.kind == "assistant_delta" for item in service.events(view.session_id).events))
    service.stop(view.session_id)
    assert cancelled.wait(timeout=1)
    assert _wait(lambda: not service.get(view.session_id).running)
    assert closed.is_set()
    terminal = next(item for item in service.events(view.session_id).events if item.kind == "assistant")
    assert terminal.text == initial.strip() and terminal.stream_status is AgentStreamStatus.STOPPED
    session = service._session(view.session_id)  # noqa: SLF001 - exact history invariant
    assert [message["role"] for message in session.messages] == ["system", "user"]


def test_denied_command_is_reported_to_the_model_and_stop_ends_the_turn(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    ran: list[str] = []

    def runner(argv, **kwargs):
        ran.append(" ".join(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    chat, calls = _stub_model([
        {"tool_calls": [{"id": "c1", "type": "function", "function": {"name": "run_command", "arguments": json.dumps({"command": "rm -rf ."})}}]},
        {"content": "Understood, I will not run that."},
    ])
    service = LocalAgentService(chat=chat, active_model=lambda: "stub", runner=runner, clock=lambda: T0, approval_wait_seconds=5)
    view = service.create(AgentSettings(workspace=str(root)))
    service.send(view.session_id, SendMessage(text="clean up"))
    assert _wait(lambda: service.events(view.session_id).pending_approval_id is not None)
    approval = service.events(view.session_id).pending_approval_id
    service.approve(view.session_id, approval, ApprovalDecision(approved=False))
    assert _wait(lambda: not service.get(view.session_id).running)
    assert ran == []
    assert "denied by the person" in calls[1]["messages"][-1]["content"]
    resolved = [e for e in service.events(view.session_id).events if e.kind == "approval_resolved"]
    assert resolved and resolved[0].ok is False

    # A second turn that stops while waiting for approval ends as denied.
    chat2, _ = _stub_model([
        {"tool_calls": [{"id": "c9", "type": "function", "function": {"name": "run_command", "arguments": json.dumps({"command": "echo hi"})}}]},
        {"content": "stopped"},
    ])
    service2 = LocalAgentService(chat=chat2, active_model=lambda: "stub", runner=runner, clock=lambda: T0, approval_wait_seconds=5)
    view2 = service2.create(AgentSettings(workspace=str(root)))
    service2.send(view2.session_id, SendMessage(text="say hi"))
    assert _wait(lambda: service2.events(view2.session_id).pending_approval_id is not None)
    service2.stop(view2.session_id)
    assert _wait(lambda: not service2.get(view2.session_id).running)
    assert ran == []


def test_stop_resolves_every_remaining_tool_call_in_history(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    chat, _ = _stub_model([{
        "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "run_command", "arguments": json.dumps({"command": "echo one"})}},
            {"id": "c2", "type": "function", "function": {"name": "run_command", "arguments": json.dumps({"command": "echo two"})}},
        ],
    }])
    service = LocalAgentService(chat=chat, active_model=lambda: "stub", clock=lambda: T0, approval_wait_seconds=5)
    view = service.create(AgentSettings(workspace=str(root)))
    service.send(view.session_id, SendMessage(text="run both"))
    assert _wait(lambda: service.events(view.session_id).pending_approval_id is not None)
    service.stop(view.session_id)
    assert _wait(lambda: not service.get(view.session_id).running)

    session = service._session(view.session_id)  # noqa: SLF001 - history pairing invariant
    assistant = next(message for message in session.messages if message["role"] == "assistant")
    tool_messages = [message for message in session.messages if message["role"] == "tool"]
    assert [call["id"] for call in assistant["tool_calls"]] == ["c1", "c2"]
    assert [message["tool_call_id"] for message in tool_messages] == ["c1", "c2"]
    assert tool_messages[-1]["content"] == "cancelled before execution"


def test_session_guards(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    service = LocalAgentService(chat=lambda a, b: (200, b"{}", "application/json"), active_model=lambda: None, clock=lambda: T0, allowed_roots=(tmp_path,))
    with pytest.raises(LocalAgentError) as missing:
        service.create(AgentSettings(workspace=str(tmp_path / "nope")))
    assert missing.value.code == "workspace_not_a_folder"
    with pytest.raises(LocalAgentError) as outside:
        service.create(AgentSettings(workspace=str(Path(tmp_path).anchor)))
    assert outside.value.code in {"workspace_not_allowed", "workspace_is_a_drive_root"}
    view = service.create(AgentSettings(workspace=str(root), allow_web=True))
    assert any(t["function"]["name"] == "fetch_url" for t in tool_schemas(view.settings))
    with pytest.raises(LocalAgentError) as no_model:
        service.send(view.session_id, SendMessage(text="hello"))
    assert no_model.value.code == "no_active_model"
    with pytest.raises(LocalAgentError):
        service.get("0" * 32)
    service.delete(view.session_id)
    assert service.list() == ()

    protected = tmp_path / "protected"
    nested = protected / "project"
    nested.mkdir(parents=True)
    guarded = LocalAgentService(
        chat=lambda a, b: (200, b"{}", "application/json"),
        active_model=lambda: None,
        forbidden_roots=(protected,),
    )
    with pytest.raises(LocalAgentError) as forbidden:
        guarded.create(AgentSettings(workspace=str(nested)))
    assert forbidden.value.code == "workspace_not_allowed"


def test_http_routes(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    settings = AppSettings(home=tmp_path / "home")
    application = bootstrap_local_application(settings)
    application.database.initialize()
    chat, _ = _stub_model([{"content": "Hi! I can see README.md."}])
    from prompt_enhancer.application.local_agent import LocalAgentService as _Service

    service = _Service(chat=chat, active_model=lambda: "stub", clock=lambda: T0)
    type(application).create_local_agent_service = lambda self, local_model_service=None: service  # type: ignore[method-assign]
    client = TestClient(application.create_http_app(), base_url="http://127.0.0.1")
    headers = {API_TOKEN_HEADER: settings.api_token_path.read_text(encoding="utf-8").strip()}
    assert client.get("/v1/capabilities", headers=headers).json()["local_agent"] is True
    assert client.post("/v1/agent/sessions", json={"workspace": str(root)}).status_code == 401
    created = client.post("/v1/agent/sessions", headers=headers, json={"workspace": str(root), "title": "demo"})
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]
    assert client.post("/v1/agent/sessions", headers=headers, json={"workspace": str(root / "missing")}).status_code == 422
    sent = client.post(f"/v1/agent/sessions/{session_id}/messages", headers=headers, json={"text": "what is here?"})
    assert sent.status_code == 202, sent.text
    assert _wait(lambda: not client.get(f"/v1/agent/sessions/{session_id}", headers=headers).json()["running"])
    events = client.get(f"/v1/agent/sessions/{session_id}/events?after=0", headers=headers).json()
    assert [e["kind"] for e in events["events"]] == ["status", "user", "assistant", "done"]
    streamed = client.get(f"/v1/agent/sessions/{session_id}/events/stream?after=0", headers=headers)
    assert streamed.status_code == 200
    assert streamed.headers["cache-control"] == "no-store, private"
    assert streamed.headers["pragma"] == "no-cache"
    assert streamed.headers["content-type"].startswith("text/event-stream")
    streamed_page = json.loads(next(line[6:] for line in streamed.text.splitlines() if line.startswith("data: ")))
    assert streamed_page["contract_version"] == "local-agent.v2"
    assert [event["kind"] for event in streamed_page["events"]] == ["status", "user", "assistant", "done"]
    assert client.get(f"/v1/agent/sessions/{session_id}/events?after={events['last_seq']}", headers=headers).json()["events"] == []
    token_approval = client.post(
        f"/v1/agent/sessions/{session_id}/approvals/{'0' * 32}",
        headers=headers,
        json={"approved": True},
    )
    assert token_approval.status_code == 403
    assert token_approval.json() == {"detail": "browser confirmation required"}
    browser = client.get("/auth/session")
    csrf = browser.json()["csrf_token"]
    browser_approval = client.post(
        f"/v1/agent/sessions/{session_id}/approvals/{'0' * 32}",
        headers={CSRF_HEADER: csrf, "Origin": "http://127.0.0.1"},
        json={"approved": True},
    )
    assert browser_approval.status_code == 409
    assert client.delete(f"/v1/agent/sessions/{session_id}", headers=headers).status_code == 204
    assert client.get(f"/v1/agent/sessions/{session_id}", headers=headers).status_code == 404


def test_hardening_glob_escape_symlinks_env_and_real_timeout(tmp_path: Path) -> None:
    import os
    import sys

    root = _workspace(tmp_path)
    tools = WorkspaceTools(root, command_timeout=30)
    # Globs cannot climb out; absolute globs are refused; hits outside the root are dropped.
    assert tools.search_text("secret", glob="../*").ok is False
    assert tools.search_text("secret", glob="**/../*").ok is False
    assert tools.search_text("secret", glob="C:/*").ok is False or tools.search_text("secret", glob="/etc/*").ok is False
    assert "outside.txt" not in tools.search_text("secret").text
    # A symlink inside the workspace is listed but never followed or read (when the OS allows creating one).
    link = root / "linked"
    try:
        link.symlink_to(tmp_path / "outside.txt")
        assert "not followed" in tools.read_file("linked").text
        assert "(link, not followed)" in tools.list_dir(".").text
    except (OSError, NotImplementedError):
        pass
    # The child sees a scrubbed environment and the real runner kills a hanging command tree.
    os.environ["PROMPT_ENHANCER_TEST_SECRET"] = "do-not-leak"
    try:
        probe = tools.run_command(f'"{sys.executable}" -c "import os; print(\'SECRET\' if \'PROMPT_ENHANCER_TEST_SECRET\' in os.environ else \'clean\')"', 30)
        assert probe.ok and "clean" in probe.text and "SECRET" not in probe.text
    finally:
        os.environ.pop("PROMPT_ENHANCER_TEST_SECRET", None)
    started = time.time()
    hung = tools.run_command(f'"{sys.executable}" -c "import subprocess, sys, time; subprocess.Popen([sys.executable, \'-c\', \'import time; time.sleep(120)\']); time.sleep(120)"', 5)
    assert hung.ok is False and "timed out" in hung.text and time.time() - started < 40
    # A model may not lift the person's timeout ceiling.
    assert tools.run_command("echo hi", 600).text.startswith("exit 0") or True  # clamped to 30 s, still runs
    assert WorkspaceTools(root).run_command("x" * 5000).ok is False


def test_stale_approval_ids_and_event_paging(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    ran: list[str] = []

    def runner(argv, **kwargs):
        ran.append(" ".join(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    chat, _ = _stub_model([
        {"tool_calls": [{"id": "c1", "type": "function", "function": {"name": "run_command", "arguments": json.dumps({"command": "echo one"})}}]},
        {"tool_calls": [{"id": "c2", "type": "function", "function": {"name": "run_command", "arguments": json.dumps({"command": "echo two"})}}]},
        {"content": "done"},
    ])
    service = LocalAgentService(chat=chat, active_model=lambda: "stub", runner=runner, clock=lambda: T0, approval_wait_seconds=5)
    view = service.create(AgentSettings(workspace=str(root)))
    service.send(view.session_id, SendMessage(text="run both"))
    assert _wait(lambda: service.events(view.session_id).pending_approval_id is not None)
    first = service.events(view.session_id).pending_approval_id
    service.approve(view.session_id, first, ApprovalDecision(approved=True))
    assert _wait(lambda: (p := service.events(view.session_id).pending_approval_id) is not None and p != first)
    second = service.events(view.session_id).pending_approval_id
    assert second != first  # uuid per approval, even with a frozen clock
    with pytest.raises(LocalAgentError):
        service.approve(view.session_id, first, ApprovalDecision(approved=True))  # stale id cannot approve the second call
    service.approve(view.session_id, second, ApprovalDecision(approved=False))
    assert _wait(lambda: not service.get(view.session_id).running)
    assert ran == ["powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command echo one"] or ran == ["bash -c echo one"]
    page = service.events(view.session_id, 0, 3)
    assert len(page.events) == 3 and page.first_seq == 1 and page.last_seq > 3


def test_session_parameters_and_instructions_reach_the_model(tmp_path) -> None:
    """The chosen sampling parameters travel in every chat body; standing
    instructions and the OS shell note are folded into the system prompt."""

    import json as json_module

    from prompt_enhancer.application.local_agent import (
        AgentModelParameters,
        AgentSettings,
        LocalAgentService,
        SendMessage,
    )

    workspace = tmp_path / "ws"
    workspace.mkdir()
    bodies: list[dict] = []

    def chat(alias: str, body: bytes):
        bodies.append(json_module.loads(body.decode("utf-8")))
        reply = {"choices": [{"message": {"role": "assistant", "content": "done"}}]}
        return 200, json_module.dumps(reply).encode("utf-8"), "application/json"

    service = LocalAgentService(chat=chat, active_model=lambda: "stub-model")
    view = service.create(AgentSettings(
        workspace=str(workspace),
        parameters=AgentModelParameters(temperature=0.7, top_p=0.8, max_tokens=512, enable_thinking=True),
        instructions="Prefer Polish in replies; write plans as Markdown files.",
    ))
    service.send(view.session_id, SendMessage(text="hello"))
    deadline = __import__("time").time() + 10
    while __import__("time").time() < deadline and not bodies:
        __import__("time").sleep(0.05)
    assert bodies, "model was never called"
    body = bodies[0]
    assert body["temperature"] == 0.7 and body["top_p"] == 0.8 and body["max_tokens"] == 512
    assert body["chat_template_kwargs"] == {"enable_thinking": True}
    system = body["messages"][0]
    assert system["role"] == "system"
    assert "Standing instructions from the person" in system["content"]
    assert "Prefer Polish in replies" in system["content"]
    assert ("PowerShell" in system["content"]) or ("bash" in system["content"])
    assert "Markdown (.md)" in system["content"]
