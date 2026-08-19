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

from prompt_enhancer.api import API_TOKEN_HEADER
from prompt_enhancer.application.local_agent import (
    AgentSettings,
    ApprovalDecision,
    LocalAgentError,
    LocalAgentService,
    SendMessage,
    WorkspaceTools,
    tool_schemas,
)
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
    assert "+++ b/docs/new.md" in tools.diff_preview("docs/new.md", "hello\n")
    written = tools.write_file("docs/new.md", "hello\n")
    assert written.ok and (root / "docs" / "new.md").read_text(encoding="utf-8") == "hello\n"


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
    assert client.get(f"/v1/agent/sessions/{session_id}/events?after={events['last_seq']}", headers=headers).json()["events"] == []
    assert client.post(f"/v1/agent/sessions/{session_id}/approvals/{'0' * 32}", headers=headers, json={"approved": True}).status_code == 409
    assert client.delete(f"/v1/agent/sessions/{session_id}", headers=headers).status_code == 204
    assert client.get(f"/v1/agent/sessions/{session_id}", headers=headers).status_code == 404
