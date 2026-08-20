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
import difflib
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import threading
import time
from typing import Any, Literal
import uuid

from pydantic import Field, field_validator

from ..domain import StrictModel


AGENT_CONTRACT_VERSION = "local-agent.v1"
MAX_SESSIONS = 12
MAX_EVENTS = 4_000
MAX_STEPS_PER_TURN = 16
MAX_TOOL_RESULT_CHARS = 24_000
MAX_FILE_READ_BYTES = 96_000
MAX_LIST_ENTRIES = 400
MAX_SEARCH_RESULTS = 80
MAX_DIFF_CHARS = 60_000
MAX_REVIEWABLE_COMMAND_CHARS = 4_000
MAX_TOOL_CALLS_PER_REPLY = 8
MAX_HISTORY_MESSAGES = 60
OLD_TOOL_RESULT_KEEP_CHARS = 2_000
MAX_EVENT_PAGE = 500
MAX_COMMAND_SECONDS = 600
DEFAULT_COMMAND_SECONDS = 120
APPROVAL_WAIT_SECONDS = 1_800
SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build", ".next", ".cache"})
_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class LocalAgentError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ToolName(StrEnum):
    READ_FILE = "read_file"
    LIST_DIR = "list_dir"
    SEARCH_TEXT = "search_text"
    WRITE_FILE = "write_file"
    RUN_COMMAND = "run_command"
    FETCH_URL = "fetch_url"


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
    kind: Literal["user", "assistant", "tool_call", "tool_result", "approval_required", "approval_resolved", "status", "error", "done"]
    text: str | None = None
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    call_id: str | None = None
    approval_id: str | None = None
    ok: bool | None = None
    preview: str | None = None


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


# ----- workspace tools -----


@dataclass(slots=True)
class ToolOutcome:
    ok: bool
    text: str


class WorkspaceTools:
    """Tool implementations scoped to one folder. No path may escape the root."""

    def __init__(self, root: Path, *, command_timeout: int = DEFAULT_COMMAND_SECONDS, runner: Callable[..., subprocess.CompletedProcess[str]] | None = None, fetcher: Callable[[str], str] | None = None) -> None:
        self.root = root.resolve()
        self._command_timeout = command_timeout
        self._runner = runner or run_with_tree_kill
        self._fetcher = fetcher

    def resolve(self, relative: str) -> Path:
        candidate = (self.root / (relative or ".")).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise LocalAgentError("path_outside_workspace")
        return candidate

    def read_file(self, path: str) -> ToolOutcome:
        target = self.resolve(path)
        if not target.is_file():
            return ToolOutcome(False, f"not a file: {path}")
        if (self.root / (path or ".")).is_symlink():
            return ToolOutcome(False, f"is a link, not followed: {path}")
        data = target.read_bytes()
        truncated = len(data) > MAX_FILE_READ_BYTES
        text = data[:MAX_FILE_READ_BYTES].decode("utf-8", errors="replace")
        if "\x00" in text[:4000]:
            return ToolOutcome(False, f"binary file, not shown: {path} ({len(data)} bytes)")
        return ToolOutcome(True, text + (f"\n… truncated ({len(data)} bytes total)" if truncated else ""))

    def list_dir(self, path: str = ".", depth: int = 1) -> ToolOutcome:
        target = self.resolve(path)
        if not target.is_dir():
            return ToolOutcome(False, f"not a folder: {path}")
        lines: list[str] = []
        depth = max(1, min(int(depth or 1), 2))

        def walk(folder: Path, level: int) -> None:
            try:
                entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except OSError:
                return
            for entry in entries:
                if len(lines) >= MAX_LIST_ENTRIES:
                    return
                rel = entry.relative_to(self.root).as_posix()
                if entry.is_symlink():
                    lines.append(f"{rel} (link, not followed)")
                    continue
                if entry.is_dir():
                    if entry.name in SKIP_DIRS:
                        lines.append(f"{rel}/ (skipped)")
                        continue
                    lines.append(f"{rel}/")
                    if level < depth:
                        walk(entry, level + 1)
                else:
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = -1
                    lines.append(f"{rel} ({size} bytes)")

        walk(target, 1)
        if len(lines) >= MAX_LIST_ENTRIES:
            lines.append("… more entries not shown")
        return ToolOutcome(True, "\n".join(lines) or "(empty folder)")

    def search_text(self, query: str, glob: str = "**/*", regex: bool = False) -> ToolOutcome:
        if not query:
            return ToolOutcome(False, "empty query")
        try:
            pattern = re.compile(query if regex else re.escape(query), re.I)
        except re.error:
            return ToolOutcome(False, "invalid regex")
        pattern_path = Path(glob or "**/*")
        if pattern_path.is_absolute() or ".." in pattern_path.parts or (glob or "").startswith(("/", "\\")):
            return ToolOutcome(False, "glob must stay inside the workspace")
        results: list[str] = []
        scanned = 0
        for file in self.root.glob(glob or "**/*"):
            if len(results) >= MAX_SEARCH_RESULTS or scanned > 20_000:
                break
            try:
                real = file.resolve()
            except OSError:
                continue
            if real != self.root and self.root not in real.parents:
                continue
            if file.is_symlink() or not file.is_file() or any(part in SKIP_DIRS for part in file.relative_to(self.root).parts):
                continue
            try:
                if file.stat().st_size > 2_000_000:
                    continue
                text = file.read_bytes()
            except OSError:
                continue
            if b"\x00" in text[:4000]:
                continue
            scanned += 1
            for number, line in enumerate(text.decode("utf-8", errors="replace").splitlines(), 1):
                if pattern.search(line):
                    results.append(f"{file.relative_to(self.root).as_posix()}:{number}: {line.strip()[:240]}")
                    if len(results) >= MAX_SEARCH_RESULTS:
                        break
        return ToolOutcome(True, "\n".join(results) or "no matches")

    def diff_preview(self, path: str, content: str) -> str:
        target = self.resolve(path)
        before = target.read_text(encoding="utf-8", errors="replace").splitlines() if target.is_file() else []
        diff = difflib.unified_diff(before, content.splitlines(), fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="", n=2)
        text = "\n".join(diff)
        if not text:
            text = "(no change)" if target.is_file() else f"(new file, {len(content.splitlines())} lines)"
        return text[:MAX_DIFF_CHARS] + ("\n… diff truncated" if len(text) > MAX_DIFF_CHARS else "")

    def write_file(self, path: str, content: str) -> ToolOutcome:
        target = self.resolve(path)
        if target.is_dir():
            return ToolOutcome(False, f"is a folder: {path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolOutcome(True, f"wrote {path} ({len(content)} characters)")

    def run_command(self, command: str, timeout_seconds: int | None = None) -> ToolOutcome:
        # The person's session setting is the ceiling; the model may only ask for less.
        requested = int(timeout_seconds) if timeout_seconds else self._command_timeout
        timeout = max(5, min(requested, self._command_timeout, MAX_COMMAND_SECONDS))
        if len(command) > MAX_REVIEWABLE_COMMAND_CHARS:
            return ToolOutcome(False, "command too long to review; split it into smaller commands")
        if platform.system() == "Windows":
            # PowerShell needs the call operator for a quoted executable path ("C:\x y\python.exe" -c ...).
            shell_command = ("& " + command) if command.lstrip().startswith(('"', "'")) else command
            argv = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", shell_command]
        else:
            argv = ["bash", "-c", command]
        try:
            completed = self._runner(
                argv, cwd=str(self.root), capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                errors="replace", env=minimal_environment(),
            )
        except subprocess.TimeoutExpired:
            return ToolOutcome(False, f"timed out after {timeout}s")
        except OSError as error:
            return ToolOutcome(False, f"could not start: {error.__class__.__name__}")
        out = (completed.stdout or "") + (("\n[stderr]\n" + completed.stderr) if completed.stderr else "")
        out = out[-MAX_TOOL_RESULT_CHARS:] if len(out) > MAX_TOOL_RESULT_CHARS else out
        return ToolOutcome(completed.returncode == 0, f"exit {completed.returncode}\n{out}".strip())

    def fetch_url(self, url: str) -> ToolOutcome:
        if self._fetcher is None:
            return ToolOutcome(False, "web access is not available in this session")
        try:
            return ToolOutcome(True, self._fetcher(url)[:MAX_TOOL_RESULT_CHARS])
        except Exception as error:  # noqa: BLE001 - reported as text to the model, never raised into the loop
            return ToolOutcome(False, f"fetch failed: {error.__class__.__name__}")


_ENV_KEEP = ("PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA",
             "LOCALAPPDATA", "PROGRAMDATA", "LANG", "LC_ALL", "TERM", "SHELL", "USERNAME", "USER", "PROCESSOR_ARCHITECTURE",
             "NUMBER_OF_PROCESSORS", "PYTHONIOENCODING", "VIRTUAL_ENV", "NVM_DIR", "JAVA_HOME", "CARGO_HOME", "GOPATH")


def minimal_environment() -> dict[str, str]:
    """Child commands get PATH and the usual locations, never the app's own secrets or tokens."""

    env = {key: value for key, value in os.environ.items() if key in _ENV_KEEP or key.upper() in _ENV_KEEP}
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return env


def run_with_tree_kill(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Like subprocess.run, but a timeout kills the whole process tree and never hangs on the pipes."""

    timeout = kwargs.pop("timeout", None)
    kwargs.pop("capture_output", None)
    popen_kwargs: dict[str, Any] = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, **kwargs}
    if platform.system() == "Windows":
        popen_kwargs["creationflags"] = popen_kwargs.get("creationflags", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(argv, **popen_kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        try:
            process.communicate(timeout=5)
        except Exception:  # noqa: BLE001 - best effort drain
            pass
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout or "", stderr or "")


def _kill_tree(process: subprocess.Popen[Any]) -> None:
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False)
        else:
            import signal

            os.killpg(process.pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001
        pass
    try:
        process.kill()
    except Exception:  # noqa: BLE001
        pass


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
    lock: threading.Lock = field(default_factory=threading.Lock)
    thread: threading.Thread | None = None


class LocalAgentService:
    def __init__(
        self,
        *,
        chat: Callable[[str, bytes], tuple[int, bytes, str]],
        active_model: Callable[[], str | None],
        allowed_roots: tuple[Path, ...] | None = None,
        fetcher: Callable[[str], str] | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        clock: Callable[[], datetime] | None = None,
        approval_wait_seconds: float = APPROVAL_WAIT_SECONDS,
    ) -> None:
        self._chat = chat
        self._active_model = active_model
        self._allowed_roots = tuple(root.resolve() for root in allowed_roots) if allowed_roots else None
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
        root = root.resolve()
        if self._allowed_roots is not None and not any(root == allowed or allowed in root.parents for allowed in self._allowed_roots):
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
                tools=WorkspaceTools(root, command_timeout=settings.command_timeout_seconds, runner=self._runner, fetcher=self._fetcher if settings.allow_web else None),
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
            items = tuple(event for event in session.events if event.seq > after)[:limit]
            return AgentEvents(
                session_id=session_id,
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
        if pending is not None:
            pending.approved = False
            pending.decided.set()
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
        with session.lock:
            seq = (session.events[-1].seq if session.events else 0) + 1
            event = AgentEvent(seq=seq, at=self._clock(), kind=kind, **fields)  # type: ignore[arg-type]
            session.events.append(event)
            if len(session.events) > MAX_EVENTS:
                del session.events[: len(session.events) - MAX_EVENTS]
        return event

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
                    status, payload, _ = self._chat(alias, body)
                except Exception as error:  # noqa: BLE001 - reported as an event
                    self._emit(session, "error", text=f"model unreachable ({error.__class__.__name__})")
                    break
                if status != 200:
                    self._emit(session, "error", text=f"model error (HTTP {status})")
                    break
                try:
                    reply = json.loads(payload.decode("utf-8"))
                    message = reply["choices"][0]["message"]
                except (ValueError, KeyError, IndexError, TypeError):
                    self._emit(session, "error", text="model reply was not usable")
                    break
                tool_calls = message.get("tool_calls") or []
                content = (message.get("content") or "").strip()
                session.messages.append({"role": "assistant", "content": content or None, **({"tool_calls": tool_calls} if tool_calls else {})})
                if content:
                    self._emit(session, "assistant", text=content)
                if not tool_calls:
                    break
                if len(tool_calls) > MAX_TOOL_CALLS_PER_REPLY:
                    self._emit(session, "status", text=f"The model asked for {len(tool_calls)} tool calls at once; only the first {MAX_TOOL_CALLS_PER_REPLY} run.")
                for call in tool_calls[:MAX_TOOL_CALLS_PER_REPLY]:
                    if session.stop_requested:
                        break
                    call_id = str(call.get("id") or hashlib.md5(json.dumps(call, sort_keys=True).encode()).hexdigest()[:12])  # noqa: S324
                    function = call.get("function") or {}
                    name = str(function.get("name") or "")
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                        if not isinstance(arguments, dict):
                            arguments = {}
                    except ValueError:
                        arguments = {}
                    self._emit(session, "tool_call", tool=name, arguments=_safe_arguments(arguments), call_id=call_id)
                    outcome = self._execute(session, name, arguments)
                    self._emit(session, "tool_result", tool=name, call_id=call_id, ok=outcome.ok, text=outcome.text[:MAX_TOOL_RESULT_CHARS])
                    session.messages.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": outcome.text[:MAX_TOOL_RESULT_CHARS]})
            else:
                self._emit(session, "status", text="Step limit reached for this turn; send another message to continue.")
        finally:
            with session.lock:
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
            if tool is ToolName.WRITE_FILE:
                preview = tools.diff_preview(str(arguments.get("path") or ""), str(arguments.get("content") or ""))
                if preview.endswith("… diff truncated"):
                    return ToolOutcome(False, "change too large to review in one step; write it in smaller pieces")
            if tool is ToolName.RUN_COMMAND and len(str(arguments.get("command") or "")) > MAX_REVIEWABLE_COMMAND_CHARS:
                return ToolOutcome(False, "command too long to review; split it into smaller commands")
            if not self._await_approval(session, tool, arguments, preview):
                return ToolOutcome(False, "denied by the person - do not retry this call; explain or choose another approach")
            if tool is ToolName.WRITE_FILE:
                return tools.write_file(str(arguments.get("path") or ""), str(arguments.get("content") or ""))
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
