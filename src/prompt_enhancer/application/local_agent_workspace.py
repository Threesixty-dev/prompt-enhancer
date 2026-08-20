"""Workspace-scoped file, command, and fetch tools for ADR 0016.

This module is deliberately independent of session and streaming state.  The
agent service supplies one instance per selected workspace and keeps approval
authority in the orchestration layer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import difflib
import os
from pathlib import Path
import platform
import re
import subprocess
from typing import Any

from .local_agent_limits import (
    DEFAULT_COMMAND_SECONDS,
    LocalAgentError,
    MAX_COMMAND_SECONDS,
    MAX_DIFF_CHARS,
    MAX_FILE_READ_BYTES,
    MAX_LIST_ENTRIES,
    MAX_REVIEWABLE_COMMAND_CHARS,
    MAX_SEARCH_RESULTS,
    MAX_TOOL_RESULT_CHARS,
    SKIP_DIRS,
)


@dataclass(slots=True)
class ToolOutcome:
    ok: bool
    text: str


class WorkspaceTools:
    """Tool implementations scoped to one folder. No path may escape the root."""

    def __init__(
        self,
        root: Path,
        *,
        command_timeout: int = DEFAULT_COMMAND_SECONDS,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        fetcher: Callable[[str], str] | None = None,
    ) -> None:
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
        return ToolOutcome(
            True,
            text + (f"\n… truncated ({len(data)} bytes total)" if truncated else ""),
        )

    def list_dir(self, path: str = ".", depth: int = 1) -> ToolOutcome:
        target = self.resolve(path)
        if not target.is_dir():
            return ToolOutcome(False, f"not a folder: {path}")
        lines: list[str] = []
        depth = max(1, min(int(depth or 1), 2))

        def walk(folder: Path, level: int) -> None:
            try:
                entries = sorted(
                    folder.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())
                )
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
            if (
                file.is_symlink()
                or not file.is_file()
                or any(part in SKIP_DIRS for part in file.relative_to(self.root).parts)
            ):
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
            for number, line in enumerate(
                text.decode("utf-8", errors="replace").splitlines(), 1
            ):
                if pattern.search(line):
                    results.append(
                        f"{file.relative_to(self.root).as_posix()}:{number}: {line.strip()[:240]}"
                    )
                    if len(results) >= MAX_SEARCH_RESULTS:
                        break
        return ToolOutcome(True, "\n".join(results) or "no matches")

    def diff_preview(self, path: str, content: str) -> str:
        target = self.resolve(path)
        before = (
            target.read_text(encoding="utf-8", errors="replace").splitlines()
            if target.is_file()
            else []
        )
        diff = difflib.unified_diff(
            before,
            content.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
            n=2,
        )
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
        requested = int(timeout_seconds) if timeout_seconds else self._command_timeout
        timeout = max(5, min(requested, self._command_timeout, MAX_COMMAND_SECONDS))
        if len(command) > MAX_REVIEWABLE_COMMAND_CHARS:
            return ToolOutcome(False, "command too long to review; split it into smaller commands")
        if platform.system() == "Windows":
            shell_command = ("& " + command) if command.lstrip().startswith(('"', "'")) else command
            argv = [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                shell_command,
            ]
        else:
            argv = ["bash", "-c", command]
        try:
            completed = self._runner(
                argv,
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                errors="replace",
                env=minimal_environment(),
            )
        except subprocess.TimeoutExpired:
            return ToolOutcome(False, f"timed out after {timeout}s")
        except OSError as error:
            return ToolOutcome(False, f"could not start: {error.__class__.__name__}")
        out = (completed.stdout or "") + (
            ("\n[stderr]\n" + completed.stderr) if completed.stderr else ""
        )
        out = out[-MAX_TOOL_RESULT_CHARS:] if len(out) > MAX_TOOL_RESULT_CHARS else out
        return ToolOutcome(completed.returncode == 0, f"exit {completed.returncode}\n{out}".strip())

    def fetch_url(self, url: str) -> ToolOutcome:
        if self._fetcher is None:
            return ToolOutcome(False, "web access is not available in this session")
        try:
            return ToolOutcome(True, self._fetcher(url)[:MAX_TOOL_RESULT_CHARS])
        except Exception as error:  # noqa: BLE001 - reported to the model
            return ToolOutcome(False, f"fetch failed: {error.__class__.__name__}")


_ENV_KEEP = (
    "PATH",
    "SYSTEMROOT",
    "SystemRoot",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "LANG",
    "LC_ALL",
    "TERM",
    "SHELL",
    "USERNAME",
    "USER",
    "PROCESSOR_ARCHITECTURE",
    "NUMBER_OF_PROCESSORS",
    "PYTHONIOENCODING",
    "VIRTUAL_ENV",
    "NVM_DIR",
    "JAVA_HOME",
    "CARGO_HOME",
    "GOPATH",
)


def minimal_environment() -> dict[str, str]:
    """Child commands get locations, never the app's own secrets or tokens."""

    env = {
        key: value
        for key, value in os.environ.items()
        if key in _ENV_KEEP or key.upper() in _ENV_KEEP
    }
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return env


def run_with_tree_kill(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Like subprocess.run, but a timeout kills the whole process tree."""

    timeout = kwargs.pop("timeout", None)
    kwargs.pop("capture_output", None)
    popen_kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        **kwargs,
    }
    if platform.system() == "Windows":
        popen_kwargs["creationflags"] = popen_kwargs.get("creationflags", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
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
    return subprocess.CompletedProcess(
        argv, process.returncode, stdout or "", stderr or ""
    )


def _kill_tree(process: subprocess.Popen[Any]) -> None:
    try:
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
        else:
            import signal

            os.killpg(process.pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001
        pass
    try:
        process.kill()
    except Exception:  # noqa: BLE001
        pass


__all__ = (
    "ToolOutcome",
    "WorkspaceTools",
    "minimal_environment",
    "run_with_tree_kill",
)
