"""Local agent workspace (ADR 0016): a chosen local model works inside one folder with tools.

The model reaches files and commands only through the tools defined here, every
tool is scoped to the workspace folder the person chose, and the tools that
change anything - writing a file, running a command, fetching a URL - pause the
run until the person approves that exact call in the dashboard (writes show a
diff first). Reads never leave the workspace; nothing is persisted except in
memory for the life of the server. The model is the app's own loopback runtime
(ADR 0013) and speaks OpenAI tool calls through the runtime's chat template.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import threading
import time
from typing import Any, Literal, Protocol
import uuid

from pydantic import Field, field_validator, model_validator

from ..domain import StrictModel
from .local_agent_limits import (
    AGENT_CONTRACT_VERSION,
    APPROVAL_WAIT_SECONDS,
    DEFAULT_COMMAND_SECONDS,
    ID_PATTERN as _ID_PATTERN,
    LocalAgentError,
    MAX_AGENT_STREAM_BYTES,
    MAX_ASSISTANT_TEXT_CHARS,
    MAX_CALL_ID_CHARS,
    MAX_COMMAND_SECONDS,
    MAX_EVENTS,
    MAX_EVENT_PAGE,
    MAX_HISTORY_MESSAGES,
    MAX_REVIEWABLE_COMMAND_CHARS,
    MAX_SESSIONS,
    MAX_STEPS_PER_TURN,
    MAX_STREAM_DELTA_EVENTS,
    MAX_TOOL_CALLS_PER_REPLY,
    MAX_TOOL_NAME_CHARS,
    MAX_TOOL_RESULT_CHARS,
    OLD_TOOL_RESULT_KEEP_CHARS,
    STREAM_EVENT_CHARS,
    STREAM_WAIT_SECONDS,
)
from .local_agent_workspace import (
    PreparedWrite,
    ToolOutcome,
    WorkspaceTools,
    minimal_environment,
    run_with_tree_kill,
)


class ToolName(StrEnum):
    READ_FILE = "read_file"
    LIST_DIR = "list_dir"
    SEARCH_TEXT = "search_text"
    WRITE_FILE = "write_file"
    RUN_COMMAND = "run_command"
    FETCH_URL = "fetch_url"


class AgentStreamPhase(StrEnum):
    CONTENT = "content"
    REASONING = "reasoning"


class AgentStreamStatus(StrEnum):
    COMPLETE = "complete"
    STOPPED = "stopped"
    FAILED = "failed"


SAFE_TOOLS = frozenset({ToolName.READ_FILE, ToolName.LIST_DIR, ToolName.SEARCH_TEXT})
APPROVAL_TOOLS = frozenset({ToolName.WRITE_FILE, ToolName.RUN_COMMAND, ToolName.FETCH_URL})


class AgentModelParameters(StrictModel):
    """Sampling and budget knobs for the chosen model - one preset per session."""

    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, gt=0.0, le=1.0)
    max_tokens: int = Field(default=1_400, ge=64, le=8_192)
    #: Reasoning/thinking mode where the model's chat template supports it.
    enable_thinking: bool = False


class AgentSettings(StrictModel):
    workspace: str = Field(min_length=1, max_length=1024)
    model_alias: str | None = Field(default=None, max_length=64)
    parameters: AgentModelParameters = AgentModelParameters()
    #: Extra standing instructions folded into the system prompt for this session.
    instructions: str | None = Field(default=None, max_length=4_000)
    allow_writes: bool = True
    allow_commands: bool = True
    #: Web access is off unless the person turns it on; each fetch still needs approval.
    allow_web: bool = False
    max_steps: int = Field(default=10, ge=1, le=MAX_STEPS_PER_TURN)
    command_timeout_seconds: int = Field(default=DEFAULT_COMMAND_SECONDS, ge=5, le=MAX_COMMAND_SECONDS)
    title: str | None = Field(default=None, max_length=120)


class AgentEvent(StrictModel):
    seq: int
    at: datetime
    kind: Literal["user", "assistant", "assistant_delta", "tool_call", "tool_result", "approval_required", "approval_resolved", "status", "error", "done"]
    text: str | None = Field(default=None, max_length=MAX_ASSISTANT_TEXT_CHARS)
    reasoning: str | None = Field(default=None, max_length=MAX_ASSISTANT_TEXT_CHARS)
    stream_id: str | None = None
    stream_phase: AgentStreamPhase | None = None
    stream_status: AgentStreamStatus | None = None
    tool: str | None = Field(default=None, max_length=MAX_TOOL_NAME_CHARS)
    arguments: dict[str, Any] | None = None
    call_id: str | None = Field(default=None, max_length=MAX_CALL_ID_CHARS)
    approval_id: str | None = None
    ok: bool | None = None
    preview: str | None = None

    @field_validator("stream_id")
    @classmethod
    def validate_stream_id(cls, value: str | None) -> str | None:
        if value is not None and _ID_PATTERN.fullmatch(value) is None:
            raise ValueError("agent stream id is invalid")
        return value

    @model_validator(mode="after")
    def validate_stream_fields(self) -> "AgentEvent":
        if self.kind == "assistant_delta":
            if self.stream_id is None or self.stream_phase is None or not self.text:
                raise ValueError("assistant deltas require stream identity, phase, and text")
            if self.reasoning is not None or self.stream_status is not None or len(self.text) > STREAM_EVENT_CHARS:
                raise ValueError("assistant delta payload is invalid")
        elif self.kind == "assistant":
            if self.stream_phase is not None:
                raise ValueError("completed assistant events cannot carry a stream phase")
            if (self.stream_id is None) is not (self.stream_status is None):
                raise ValueError("streamed assistant events require identity and terminal status")
        elif self.stream_id is not None or self.stream_phase is not None or self.stream_status is not None or self.reasoning is not None:
            raise ValueError("only assistant events may carry stream fields")
        return self


class AgentSessionView(StrictModel):
    contract_version: Literal[AGENT_CONTRACT_VERSION] = AGENT_CONTRACT_VERSION
    session_id: str
    settings: AgentSettings
    created_at: datetime
    running: bool
    last_seq: int
    pending_approval_id: str | None = None
    model_alias: str | None = None
    turns: int


class AgentEvents(StrictModel):
    contract_version: Literal[AGENT_CONTRACT_VERSION] = AGENT_CONTRACT_VERSION
    session_id: str
    events: tuple[AgentEvent, ...]
    running: bool
    pending_approval_id: str | None = None
    last_seq: int
    #: Oldest sequence number still kept; a client whose cursor is below it missed events.
    first_seq: int = 0


class SendMessage(StrictModel):
    text: str = Field(min_length=1, max_length=40_000)


class ApprovalDecision(StrictModel):
    approved: bool


class AgentChatUpstream(Protocol):
    """Structural boundary to ADR 0013 without importing its runtime adapter."""

    status_code: int
    content_type: str
    body: bytes | None
    lines: Iterator[bytes] | None
    cancel: Callable[[], None] | None


@dataclass(slots=True)
class AgentModelReply:
    content: str
    reasoning: str
    tool_calls: list[dict[str, Any]]
    stream_id: str | None = None
    stream_status: AgentStreamStatus = AgentStreamStatus.COMPLETE
    failure_code: str | None = None
    tool_call_overflow: bool = False


# ----- tool schemas the model sees -----


def tool_schemas(settings: AgentSettings) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = [
        {"type": "function", "function": {"name": ToolName.READ_FILE.value, "description": "Read a text file inside the workspace (UTF-8, truncated beyond ~96 KB).",
                                          "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path relative to the workspace root"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": ToolName.LIST_DIR.value, "description": "List files and folders inside the workspace (one or two levels).",
                                          "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Relative folder, default '.'"}, "depth": {"type": "integer", "minimum": 1, "maximum": 2}}, "required": []}}},
        {"type": "function", "function": {"name": ToolName.SEARCH_TEXT.value, "description": "Search text (case-insensitive substring or regex) across workspace files; returns path:line: text.",
                                          "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "glob": {"type": "string", "description": "File glob such as **/*.py (default all text files)"}, "regex": {"type": "boolean"}}, "required": ["query"]}}},
    ]
    if settings.allow_writes:
        tools.append({"type": "function", "function": {"name": ToolName.WRITE_FILE.value, "description": "Create or overwrite a text file inside the workspace. The person sees a diff and must approve before anything is written.",
                                                       "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}})
    if settings.allow_commands:
        tools.append({"type": "function", "function": {"name": ToolName.RUN_COMMAND.value, "description": "Run a shell command in the workspace (tests, builds, git status). The person must approve each command; output is returned (truncated).",
                                                       "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "timeout_seconds": {"type": "integer", "minimum": 5, "maximum": MAX_COMMAND_SECONDS}}, "required": ["command"]}}})
    if settings.allow_web:
        tools.append({"type": "function", "function": {"name": ToolName.FETCH_URL.value, "description": "Fetch a public web page (text only, truncated). The person must approve each fetch.",
                                                       "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}})
    return tools


SYSTEM_PROMPT = (
    "You are a careful local coding agent working inside one workspace folder on the person's machine. "
    "Inspect before changing: list and read files, search, then make small verifiable changes and run the relevant tests or build. "
    "Use the tools for every file access and command; never invent file contents. Paths are relative to the workspace root. "
    "Writes, commands and web fetches pause for the person's approval - if a call is denied, adapt instead of retrying it. "
    "Documents are ordinary files: write Markdown (.md), notes, plans and reports with write_file like any other change. "
    "When you are done, summarise what changed and how it was verified, briefly. Answer in the person's language."
)


def _system_prompt(settings: "AgentSettings", root: Path) -> str:
    shell = (
        "Commands run under PowerShell (Windows syntax: ; between commands, $env:VAR, backslash or forward-slash paths)."
        if platform.system() == "Windows"
        else "Commands run under bash."
    )
    parts = [SYSTEM_PROMPT, shell, f"Workspace root: {root.name}/"]
    if settings.instructions:
        parts.append("Standing instructions from the person for this session: " + settings.instructions.strip())
    return " ".join(parts)


# ----- sessions and the run loop -----


@dataclass(slots=True)
class PendingApproval:
    approval_id: str
    tool: ToolName
    arguments: dict[str, Any]
    decided: threading.Event = field(default_factory=threading.Event)
    approved: bool = False


@dataclass(slots=True)
class AgentSession:
    session_id: str
    settings: AgentSettings
    created_at: datetime
    tools: WorkspaceTools
    messages: list[dict[str, Any]] = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)
    running: bool = False
    stop_requested: bool = False
    pending: PendingApproval | None = None
    turns: int = 0
    lock: threading.RLock = field(default_factory=threading.RLock)
    event_ready: threading.Condition = field(init=False)
    thread: threading.Thread | None = None
    cancel_stream: Callable[[], None] | None = None

    def __post_init__(self) -> None:
        self.event_ready = threading.Condition(self.lock)


class LocalAgentService:
    def __init__(
        self,
        *,
        chat: Callable[[str, bytes], tuple[int, bytes, str]],
        open_chat: Callable[[str, bytes], AgentChatUpstream] | None = None,
        active_model: Callable[[], str | None],
        allowed_roots: tuple[Path, ...] | None = None,
        forbidden_roots: tuple[Path, ...] = (),
        fetcher: Callable[[str], str] | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        clock: Callable[[], datetime] | None = None,
        approval_wait_seconds: float = APPROVAL_WAIT_SECONDS,
    ) -> None:
        self._chat = chat
        self._open_chat = open_chat
        self._active_model = active_model
        self._allowed_roots = tuple(root.resolve() for root in allowed_roots) if allowed_roots else None
        self._forbidden_roots = tuple(root.expanduser().resolve() for root in forbidden_roots)
        self._fetcher = fetcher
        self._runner = runner
        self._clock = clock or (lambda: datetime.now(UTC))
        self._approval_wait = approval_wait_seconds
        self._sessions: dict[str, AgentSession] = {}
        self._lock = threading.Lock()

    # -- sessions --

    def create(self, settings: AgentSettings) -> AgentSessionView:
        root = Path(settings.workspace).expanduser()
        if not root.is_absolute() or not root.is_dir():
            raise LocalAgentError("workspace_not_a_folder")
        tools = WorkspaceTools(
            root,
            command_timeout=settings.command_timeout_seconds,
            runner=self._runner,
            fetcher=self._fetcher if settings.allow_web else None,
        )
        root = tools.root
        if self._allowed_roots is not None and not any(root == allowed or allowed in root.parents for allowed in self._allowed_roots):
            raise LocalAgentError("workspace_not_allowed")
        if any(
            root == forbidden
            or forbidden in root.parents
            or root in forbidden.parents
            for forbidden in self._forbidden_roots
        ):
            raise LocalAgentError("workspace_not_allowed")
        if root.anchor == str(root):
            raise LocalAgentError("workspace_is_a_drive_root")
        with self._lock:
            if len(self._sessions) >= MAX_SESSIONS:
                raise LocalAgentError("too_many_sessions")
            session_id = uuid.uuid4().hex
            session = AgentSession(
                session_id=session_id,
                settings=settings,
                created_at=self._clock(),
                tools=tools,
                messages=[{"role": "system", "content": _system_prompt(settings, root)}],
            )
            self._sessions[session_id] = session
        self._emit(session, "status", text=f"Session ready in {root.name}/ - reads are free; writes, commands and fetches wait for your approval.")
        return self._view(session)

    def list(self) -> tuple[AgentSessionView, ...]:
        with self._lock:
            sessions = list(self._sessions.values())
        return tuple(self._view(s) for s in sorted(sessions, key=lambda s: s.created_at, reverse=True))

    def get(self, session_id: str) -> AgentSessionView:
        return self._view(self._session(session_id))

    def delete(self, session_id: str) -> None:
        session = self._session(session_id)
        self.stop(session_id)
        thread = session.thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=15)
        with self._lock:
            self._sessions.pop(session_id, None)

    def events(self, session_id: str, after: int = 0, limit: int = MAX_EVENT_PAGE) -> AgentEvents:
        session = self._session(session_id)
        limit = max(1, min(int(limit), MAX_EVENT_PAGE))
        with session.lock:
            return self._events_locked(session, after=after, limit=limit)

    def wait_events(
        self,
        session_id: str,
        after: int = 0,
        limit: int = MAX_EVENT_PAGE,
        timeout: float = STREAM_WAIT_SECONDS,
    ) -> AgentEvents:
        """Wait for a cursor advance without busy-polling.

        This is an in-process notification only. The HTTP adapter may expose it
        as a private loopback SSE stream; it never opens a socket itself.
        """

        session = self._session(session_id)
        limit = max(1, min(int(limit), MAX_EVENT_PAGE))
        timeout = max(0.0, min(float(timeout), STREAM_WAIT_SECONDS))
        with session.event_ready:
            if not any(event.seq > after for event in session.events):
                session.event_ready.wait(timeout=timeout)
            return self._events_locked(session, after=after, limit=limit)

    @staticmethod
    def _events_locked(session: AgentSession, *, after: int, limit: int) -> AgentEvents:
        items = tuple(event for event in session.events if event.seq > after)[:limit]
        return AgentEvents(
            session_id=session.session_id,
            events=items,
            running=session.running,
            pending_approval_id=session.pending.approval_id if session.pending else None,
            last_seq=session.events[-1].seq if session.events else 0,
            first_seq=session.events[0].seq if session.events else 0,
        )

    # -- turns --

    def send(self, session_id: str, message: SendMessage) -> AgentSessionView:
        session = self._session(session_id)
        alias = session.settings.model_alias or self._active_model()
        with session.lock:
            if session.running:
                raise LocalAgentError("turn_in_progress")
            if alias is None:
                raise LocalAgentError("no_active_model")
            session.running = True
            session.stop_requested = False
            session.turns += 1
        self._emit(session, "user", text=message.text)
        session.messages.append({"role": "user", "content": message.text})
        thread = threading.Thread(target=self._run_turn, args=(session, alias), name=f"local-agent-{session_id[:8]}", daemon=True)
        session.thread = thread
        thread.start()
        return self._view(session)

    def stop(self, session_id: str) -> AgentSessionView:
        session = self._session(session_id)
        with session.lock:
            session.stop_requested = True
            pending = session.pending
            cancel_stream = session.cancel_stream
        if pending is not None:
            pending.approved = False
            pending.decided.set()
        if cancel_stream is not None:
            cancel_stream()
        return self._view(session)

    def approve(self, session_id: str, approval_id: str, decision: ApprovalDecision) -> AgentSessionView:
        session = self._session(session_id)
        with session.lock:
            pending = session.pending
        if pending is None or pending.approval_id != approval_id:
            raise LocalAgentError("approval_not_pending")
        pending.approved = decision.approved
        pending.decided.set()
        return self._view(session)

    # -- internals --

    def _session(self, session_id: str) -> AgentSession:
        if not _ID_PATTERN.fullmatch(session_id or ""):
            raise LocalAgentError("session_not_found")
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise LocalAgentError("session_not_found")
        return session

    def _view(self, session: AgentSession) -> AgentSessionView:
        alias = session.settings.model_alias or self._active_model()  # may probe hardware; never under the lock
        with session.lock:
            return AgentSessionView(
                session_id=session.session_id,
                settings=session.settings,
                created_at=session.created_at,
                running=session.running,
                last_seq=session.events[-1].seq if session.events else 0,
                pending_approval_id=session.pending.approval_id if session.pending else None,
                model_alias=alias,
                turns=session.turns,
            )

    def _emit(self, session: AgentSession, kind: str, **fields: Any) -> AgentEvent:
        with session.event_ready:
            seq = (session.events[-1].seq if session.events else 0) + 1
            event = AgentEvent(seq=seq, at=self._clock(), kind=kind, **fields)  # type: ignore[arg-type]
            session.events.append(event)
            if len(session.events) > MAX_EVENTS:
                delta_index = next(
                    (index for index, item in enumerate(session.events) if item.kind == "assistant_delta"),
                    0,
                )
                del session.events[delta_index]
            session.event_ready.notify_all()
        return event

    @staticmethod
    def _whole_model_reply(payload: bytes) -> AgentModelReply:
        try:
            reply = json.loads(payload.decode("utf-8"))
            message = reply["choices"][0]["message"]
        except (UnicodeDecodeError, ValueError, KeyError, IndexError, TypeError):
            raise LocalAgentError("model_reply_unusable") from None
        if not isinstance(message, dict):
            raise LocalAgentError("model_reply_unusable")
        content = message.get("content")
        reasoning = message.get("reasoning_content")
        tool_calls = message.get("tool_calls") or []
        if content is not None and not isinstance(content, str):
            raise LocalAgentError("model_reply_unusable")
        if reasoning is not None and not isinstance(reasoning, str):
            raise LocalAgentError("model_reply_unusable")
        if not isinstance(tool_calls, list) or not all(isinstance(call, dict) for call in tool_calls):
            raise LocalAgentError("model_reply_unusable")
        if len(content or "") > MAX_ASSISTANT_TEXT_CHARS or len(reasoning or "") > MAX_ASSISTANT_TEXT_CHARS:
            raise LocalAgentError("model_reply_too_large")
        return AgentModelReply(
            content=(content or "").strip(),
            reasoning=(reasoning or "").strip(),
            tool_calls=tool_calls,
        )

    @staticmethod
    def _prune_completed_deltas(session: AgentSession) -> None:
        """Keep deltas only for the newest live stream, never as transcript history."""

        with session.event_ready:
            completed = {
                event.stream_id
                for event in session.events
                if event.kind == "assistant" and event.stream_id is not None
            }
            if completed:
                session.events[:] = [
                    event
                    for event in session.events
                    if not (event.kind == "assistant_delta" and event.stream_id in completed)
                ]

    def _stream_model_reply(
        self,
        session: AgentSession,
        alias: str,
        body: bytes,
    ) -> tuple[int, AgentModelReply | None]:
        """Consume one OpenAI-compatible SSE response and emit bounded chunks.

        Tool-call deltas are reassembled before the existing approval/tool loop
        sees them. Partial assistant text is display-only until the final
        assistant event is emitted; it is never inserted into model history as
        separate messages.
        """

        if self._open_chat is None:
            status, payload, _ = self._chat(alias, body)
            return status, self._whole_model_reply(payload) if status == 200 else None

        self._prune_completed_deltas(session)
        request = json.loads(body.decode("utf-8"))
        request["stream"] = True
        upstream = self._open_chat(alias, json.dumps(request).encode("utf-8"))
        if upstream.status_code != 200:
            return upstream.status_code, None
        if upstream.lines is None:
            if upstream.body is None:
                raise LocalAgentError("model_reply_unusable")
            reply = self._whole_model_reply(upstream.body)
            reply.stream_id = uuid.uuid4().hex
            return upstream.status_code, reply

        stream_id = uuid.uuid4().hex
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        pending = {
            AgentStreamPhase.CONTENT: "",
            AgentStreamPhase.REASONING: "",
        }
        text_lengths = {
            AgentStreamPhase.CONTENT: 0,
            AgentStreamPhase.REASONING: 0,
        }
        last_delta_at = {
            AgentStreamPhase.CONTENT: 0.0,
            AgentStreamPhase.REASONING: 0.0,
        }
        emitted_delta_count = 0
        tool_parts: dict[int, dict[str, str]] = {}
        buffered = b""
        received = 0
        saw_choice = False
        saw_done = False
        saw_finish = False
        stopped = False
        failure_code: str | None = None
        malformed_tool_delta = False
        tool_call_overflow = False

        def emit_delta(phase: AgentStreamPhase, chunk: str) -> None:
            nonlocal emitted_delta_count
            if not chunk or emitted_delta_count >= MAX_STREAM_DELTA_EVENTS:
                return
            self._emit(
                session,
                "assistant_delta",
                text=chunk,
                stream_id=stream_id,
                stream_phase=phase,
            )
            emitted_delta_count += 1
            last_delta_at[phase] = time.monotonic()

        def emit_text(phase: AgentStreamPhase, value: str) -> None:
            if not value:
                return
            if text_lengths[phase] + len(value) > MAX_ASSISTANT_TEXT_CHARS:
                raise LocalAgentError("model_reply_too_large")
            target = content_parts if phase is AgentStreamPhase.CONTENT else reasoning_parts
            target.append(value)
            text_lengths[phase] += len(value)
            pending[phase] += value
            while len(pending[phase]) >= STREAM_EVENT_CHARS:
                chunk = pending[phase][:STREAM_EVENT_CHARS]
                pending[phase] = pending[phase][STREAM_EVENT_CHARS:]
                emit_delta(phase, chunk)
            if pending[phase] and time.monotonic() - last_delta_at[phase] >= 0.1:
                chunk = pending[phase]
                pending[phase] = ""
                emit_delta(phase, chunk)

        def consume_line(raw_line: bytes) -> bool:
            nonlocal malformed_tool_delta, saw_choice, saw_done, saw_finish, tool_call_overflow
            line = raw_line.rstrip(b"\r")
            if not line.startswith(b"data:"):
                return False
            data = line[5:].strip()
            if data == b"[DONE]":
                saw_done = True
                return True
            try:
                event = json.loads(data.decode("utf-8"))
                choice = event["choices"][0]
                delta = choice.get("delta") or {}
            except (UnicodeDecodeError, ValueError, KeyError, IndexError, TypeError, AttributeError):
                raise LocalAgentError("model_reply_unusable") from None
            if not isinstance(delta, dict):
                raise LocalAgentError("model_reply_unusable")
            saw_choice = True
            finish_reason = choice.get("finish_reason")
            if isinstance(finish_reason, str) and finish_reason:
                saw_finish = True
            content = delta.get("content")
            reasoning = delta.get("reasoning_content")
            if isinstance(content, str):
                emit_text(AgentStreamPhase.CONTENT, content)
            if session.settings.parameters.enable_thinking and isinstance(reasoning, str):
                emit_text(AgentStreamPhase.REASONING, reasoning)
            calls = delta.get("tool_calls") or []
            if isinstance(calls, list):
                for raw_call in calls:
                    if not isinstance(raw_call, dict):
                        malformed_tool_delta = True
                        continue
                    index = raw_call.get("index", 0)
                    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                        malformed_tool_delta = True
                        continue
                    if index >= MAX_TOOL_CALLS_PER_REPLY:
                        tool_call_overflow = True
                        continue
                    current = tool_parts.setdefault(index, {"id": "", "name": "", "arguments": ""})
                    call_id = raw_call.get("id")
                    function = raw_call.get("function") or {}
                    if isinstance(call_id, str) and call_id:
                        current["id"] = call_id
                    if isinstance(function, dict):
                        name = function.get("name")
                        arguments = function.get("arguments")
                        if isinstance(name, str) and name:
                            if not current["name"] or name.startswith(current["name"]):
                                current["name"] = name
                            elif name != current["name"]:
                                current["name"] += name
                        if isinstance(arguments, str):
                            current["arguments"] += arguments
            return False

        lines = upstream.lines
        cancel_stream = getattr(upstream, "cancel", None)
        with session.lock:
            session.cancel_stream = cancel_stream if callable(cancel_stream) else None
        try:
            for chunk in lines:
                if session.stop_requested:
                    stopped = True
                    break
                if not isinstance(chunk, bytes):
                    raise LocalAgentError("model_reply_unusable")
                received += len(chunk)
                if received > MAX_AGENT_STREAM_BYTES:
                    raise LocalAgentError("model_reply_too_large")
                buffered += chunk
                while b"\n" in buffered:
                    raw_line, buffered = buffered.split(b"\n", 1)
                    if consume_line(raw_line):
                        buffered = b""
                        break
                else:
                    continue
                break
            if buffered and not stopped:
                consume_line(buffered)
        except LocalAgentError as error:
            failure_code = error.code
        except Exception:  # noqa: BLE001 - the terminal event carries a fixed safe failure
            failure_code = "model_stream_failed"
        finally:
            with session.lock:
                session.cancel_stream = None
            close = getattr(lines, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 - failure is represented below
                    failure_code = failure_code or "model_stream_failed"

        if session.stop_requested:
            stopped = True

        for phase in (AgentStreamPhase.REASONING, AgentStreamPhase.CONTENT):
            if pending[phase]:
                emit_delta(phase, pending[phase])
        tool_calls = [
            {
                "id": item["id"],
                "type": "function",
                "function": {"name": item["name"], "arguments": item["arguments"] or "{}"},
            }
            for _, item in sorted(tool_parts.items())
            if item["name"]
        ]
        if any(
            (not item["name"] and (item["id"] or item["arguments"]))
            or len(item["name"]) > MAX_TOOL_NAME_CHARS
            for item in tool_parts.values()
        ):
            malformed_tool_delta = True
        content = "".join(content_parts).strip()
        reasoning = "".join(reasoning_parts).strip()
        if stopped:
            stream_status = AgentStreamStatus.STOPPED
        else:
            if failure_code is None and not (saw_done or saw_finish):
                failure_code = "model_stream_incomplete"
            if failure_code is None and (not saw_choice or malformed_tool_delta):
                failure_code = "model_reply_unusable"
            if failure_code is None and not (content or reasoning or tool_calls):
                failure_code = "model_reply_unusable"
            stream_status = AgentStreamStatus.FAILED if failure_code else AgentStreamStatus.COMPLETE
        return upstream.status_code, AgentModelReply(
            content=content,
            reasoning=reasoning,
            tool_calls=tool_calls,
            stream_id=stream_id,
            stream_status=stream_status,
            failure_code=failure_code,
            tool_call_overflow=tool_call_overflow,
        )

    def _run_turn(self, session: AgentSession, alias: str) -> None:
        try:
            for _ in range(session.settings.max_steps):
                if session.stop_requested:
                    self._emit(session, "status", text="Stopped.")
                    break
                _trim_history(session.messages)
                parameters = session.settings.parameters
                body = json.dumps({
                    "messages": session.messages,
                    "tools": tool_schemas(session.settings),
                    "tool_choice": "auto",
                    "temperature": parameters.temperature,
                    "top_p": parameters.top_p,
                    "max_tokens": parameters.max_tokens,
                    "chat_template_kwargs": {"enable_thinking": parameters.enable_thinking},
                }).encode("utf-8")
                try:
                    status, reply = self._stream_model_reply(session, alias, body)
                except LocalAgentError as error:
                    text = (
                        "model reply exceeded the local safety limit"
                        if error.code == "model_reply_too_large"
                        else "model reply was not usable"
                    )
                    self._emit(session, "error", text=text)
                    break
                except Exception as error:  # noqa: BLE001 - reported as an event
                    self._emit(session, "error", text=f"model unreachable ({error.__class__.__name__})")
                    break
                if status != 200:
                    self._emit(session, "error", text=f"model error (HTTP {status})")
                    break
                if reply is None:
                    self._emit(session, "error", text="model reply was not usable")
                    break
                if len(reply.tool_calls) > MAX_TOOL_CALLS_PER_REPLY:
                    reply.tool_call_overflow = True
                tool_calls = _normalized_tool_calls(reply.tool_calls)
                content = reply.content
                reasoning = reply.reasoning if parameters.enable_thinking else ""
                if reply.stream_id is not None:
                    self._emit(
                        session,
                        "assistant",
                        text=content or None,
                        reasoning=reasoning or None,
                        stream_id=reply.stream_id,
                        stream_status=reply.stream_status,
                    )
                elif content or reasoning:
                    self._emit(session, "assistant", text=content or None, reasoning=reasoning or None)
                if reply.stream_status is AgentStreamStatus.STOPPED:
                    self._emit(session, "status", text="Stopped.")
                    break
                if reply.stream_status is AgentStreamStatus.FAILED:
                    failure_text = {
                        "model_reply_too_large": "model reply exceeded the local safety limit",
                        "model_stream_incomplete": "model stream ended before completion",
                        "model_reply_unusable": "model reply was not usable",
                    }.get(reply.failure_code, "model stream failed")
                    self._emit(session, "error", text=failure_text)
                    break
                if not (content or reasoning or tool_calls):
                    self._emit(session, "error", text="model reply was not usable")
                    break
                if content or tool_calls:
                    session.messages.append({"role": "assistant", "content": content or None, **({"tool_calls": tool_calls} if tool_calls else {})})
                if not tool_calls:
                    break
                if reply.tool_call_overflow:
                    self._emit(session, "status", text=f"The model asked for more than {MAX_TOOL_CALLS_PER_REPLY} tool calls at once; only the first {MAX_TOOL_CALLS_PER_REPLY} run.")
                for position, call in enumerate(tool_calls[:MAX_TOOL_CALLS_PER_REPLY]):
                    if session.stop_requested:
                        remaining = tool_calls[position:MAX_TOOL_CALLS_PER_REPLY]
                        for skipped in remaining:
                            skipped_id, skipped_name, skipped_arguments, _ = _tool_call_parts(skipped)
                            self._emit(session, "tool_call", tool=skipped_name, arguments=_safe_arguments(skipped_arguments), call_id=skipped_id)
                            self._emit(session, "tool_result", tool=skipped_name, call_id=skipped_id, ok=False, text="cancelled before execution")
                            session.messages.append({"role": "tool", "tool_call_id": skipped_id, "name": skipped_name, "content": "cancelled before execution"})
                        break
                    call_id, name, arguments, malformed_arguments = _tool_call_parts(call)
                    self._emit(session, "tool_call", tool=name, arguments=_safe_arguments(arguments), call_id=call_id)
                    outcome = (
                        ToolOutcome(False, "model supplied invalid tool arguments")
                        if malformed_arguments
                        else self._execute(session, name, arguments)
                    )
                    self._emit(session, "tool_result", tool=name, call_id=call_id, ok=outcome.ok, text=outcome.text[:MAX_TOOL_RESULT_CHARS])
                    session.messages.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": outcome.text[:MAX_TOOL_RESULT_CHARS]})
            else:
                self._emit(session, "status", text="Step limit reached for this turn; send another message to continue.")
        finally:
            with session.event_ready:
                session.running = False
                session.pending = None
                self._emit(session, "done")

    def _execute(self, session: AgentSession, name: str, arguments: Mapping[str, Any]) -> ToolOutcome:
        try:
            tool = ToolName(name)
        except ValueError:
            return ToolOutcome(False, f"unknown tool: {name}")
        tools = session.tools
        try:
            if tool is ToolName.READ_FILE:
                return tools.read_file(str(arguments.get("path") or ""))
            if tool is ToolName.LIST_DIR:
                return tools.list_dir(str(arguments.get("path") or "."), int(arguments.get("depth") or 1))
            if tool is ToolName.SEARCH_TEXT:
                return tools.search_text(str(arguments.get("query") or ""), str(arguments.get("glob") or "**/*"), bool(arguments.get("regex")))
            if tool is ToolName.WRITE_FILE and not session.settings.allow_writes:
                return ToolOutcome(False, "writes are disabled in this session")
            if tool is ToolName.RUN_COMMAND and not session.settings.allow_commands:
                return ToolOutcome(False, "commands are disabled in this session")
            if tool is ToolName.FETCH_URL and not session.settings.allow_web:
                return ToolOutcome(False, "web access is disabled in this session")
            preview = None
            prepared_write: PreparedWrite | None = None
            if tool is ToolName.WRITE_FILE:
                prepared_write = tools.prepare_write(
                    str(arguments.get("path") or ""),
                    str(arguments.get("content") or ""),
                )
                preview = prepared_write.preview
            if tool is ToolName.RUN_COMMAND and len(str(arguments.get("command") or "")) > MAX_REVIEWABLE_COMMAND_CHARS:
                return ToolOutcome(False, "command too long to review; split it into smaller commands")
            if not self._await_approval(session, tool, arguments, preview):
                return ToolOutcome(False, "denied by the person - do not retry this call; explain or choose another approach")
            if tool is ToolName.WRITE_FILE:
                if prepared_write is None:
                    return ToolOutcome(False, "write preview was unavailable")
                return tools.apply_prepared_write(prepared_write)
            if tool is ToolName.RUN_COMMAND:
                return tools.run_command(str(arguments.get("command") or ""), arguments.get("timeout_seconds"))
            return tools.fetch_url(str(arguments.get("url") or ""))
        except LocalAgentError as error:
            return ToolOutcome(False, error.code.replace("_", " "))
        except Exception as error:  # noqa: BLE001 - the loop must survive any tool failure
            return ToolOutcome(False, f"tool failed: {error.__class__.__name__}")

    def _await_approval(self, session: AgentSession, tool: ToolName, arguments: Mapping[str, Any], preview: str | None) -> bool:
        approval = PendingApproval(approval_id=uuid.uuid4().hex, tool=tool, arguments=dict(arguments))
        with session.lock:
            if session.stop_requested:
                return False
            session.pending = approval
        self._emit(session, "approval_required", tool=tool.value, arguments=_safe_arguments(arguments), approval_id=approval.approval_id, preview=preview)
        decided = approval.decided.wait(self._approval_wait)
        with session.lock:
            session.pending = None
        approved = bool(decided and approval.approved and not session.stop_requested)
        self._emit(session, "approval_resolved", tool=tool.value, approval_id=approval.approval_id, ok=approved, text=None if decided else "no decision in time; treated as denied")
        return approved


def _trim_history(messages: list[dict[str, Any]]) -> None:
    """Keep the system prompt and a rolling window; shrink old tool results so requests stay bounded."""

    if len(messages) > MAX_HISTORY_MESSAGES:
        keep = messages[-(MAX_HISTORY_MESSAGES - 1):]
        # never cut between an assistant tool_calls message and its tool results
        while keep and keep[0].get("role") == "tool":
            keep.pop(0)
        messages[:] = [messages[0], *keep]
    for message in messages[1:-6]:
        if message.get("role") == "tool" and isinstance(message.get("content"), str) and len(message["content"]) > OLD_TOOL_RESULT_KEEP_CHARS:
            message["content"] = message["content"][:OLD_TOOL_RESULT_KEEP_CHARS] + "\n… (older tool output shortened)"


def _safe_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Arguments for the event stream: strings bounded so a huge file write does not flood the UI."""

    out: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > 4_000:
            out[str(key)] = value[:4_000] + f"… ({len(value)} chars)"
        else:
            out[str(key)] = value
    return out


def _normalized_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give every model-emitted call one stable ID before it enters history."""

    normalized: list[dict[str, Any]] = []
    for call in calls[:MAX_TOOL_CALLS_PER_REPLY]:
        copied = dict(call)
        call_id = copied.get("id")
        if not isinstance(call_id, str) or not call_id or len(call_id) > MAX_CALL_ID_CHARS or not call_id.isprintable():
            call_id = hashlib.md5(json.dumps(copied, sort_keys=True, default=str).encode()).hexdigest()[:12]  # noqa: S324
        copied["id"] = call_id
        function = copied.get("function")
        if isinstance(function, Mapping):
            normalized_function = dict(function)
            name = normalized_function.get("name")
            if not isinstance(name, str) or len(name) > MAX_TOOL_NAME_CHARS or not name.isprintable():
                normalized_function["name"] = ""
            copied["function"] = normalized_function
        normalized.append(copied)
    return normalized


def _tool_call_parts(call: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], bool]:
    call_id = str(call.get("id") or "")
    function = call.get("function")
    if not isinstance(function, Mapping):
        return call_id, "", {}, True
    name = function.get("name")
    raw_arguments = function.get("arguments")
    malformed = (
        not isinstance(name, str)
        or not name
        or len(name) > MAX_TOOL_NAME_CHARS
        or not name.isprintable()
        or not isinstance(raw_arguments, str)
    )
    try:
        arguments = json.loads(raw_arguments or "{}") if isinstance(raw_arguments, str) else {}
        if not isinstance(arguments, dict):
            malformed = True
            arguments = {}
    except (TypeError, ValueError):
        malformed = True
        arguments = {}
    return call_id, str(name or ""), arguments, malformed


__all__ = (
    "AGENT_CONTRACT_VERSION",
    "APPROVAL_TOOLS",
    "SAFE_TOOLS",
    "AgentEvent",
    "AgentModelParameters",
    "AgentEvents",
    "AgentSessionView",
    "AgentSettings",
    "ApprovalDecision",
    "LocalAgentError",
    "LocalAgentService",
    "SendMessage",
    "ToolName",
    "WorkspaceTools",
    "minimal_environment",
    "run_with_tree_kill",
    "tool_schemas",
)
