"""Workspace-scoped file, command, and fetch tools for ADR 0016.

This module is deliberately independent of session and streaming state.  The
agent service supplies one instance per selected workspace and keeps approval
authority in the orchestration layer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import difflib
import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import re
import stat
import subprocess
import tempfile
import threading
from typing import Any, Literal

from .local_agent_limits import (
    DEFAULT_COMMAND_SECONDS,
    LocalAgentError,
    MAX_COMMAND_SECONDS,
    MAX_DIFF_CHARS,
    MAX_FILE_READ_BYTES,
    MAX_FILE_WRITE_BYTES,
    MAX_LIST_ENTRIES,
    MAX_REVIEWABLE_COMMAND_CHARS,
    MAX_SEARCH_RESULTS,
    MAX_TOOL_RESULT_CHARS,
    MAX_TREE_SCAN_ENTRIES,
    SKIP_DIRS,
)


@dataclass(slots=True)
class ToolOutcome:
    ok: bool
    text: str
    code: str | None = None


@dataclass(frozen=True, slots=True)
class PreparedWrite:
    """A reviewable write bound to the exact file and parent seen in preview."""

    path: str
    content: str
    preview: str
    base_sha256: str | None
    base_identity: tuple[int, int] | None
    parent_identity: tuple[int, int]
    proposed_sha256: str
    existed: bool
    mode: int | None


@dataclass(frozen=True, slots=True)
class WorkspacePathEntry:
    path: str
    name: str
    kind: Literal["directory", "file", "unavailable"]
    byte_size: int | None
    editable_candidate: bool


@dataclass(frozen=True, slots=True)
class WorkspaceTextSnapshot:
    path: str
    content: str
    revision: str
    byte_size: int
    line_ending: Literal["lf", "crlf", "none"]


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & 0x400
    )


def _path_components_are_safe(value: Path) -> bool:
    """Fail closed when any existing component is a link/reparse or unreadable."""

    for candidate in (value, *value.parents):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return False
        if _is_link_or_reparse(metadata):
            return False
    return True


_WINDOWS_RESERVED_COMPONENTS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
_SKIPPED_COMPONENTS = frozenset(component.casefold() for component in SKIP_DIRS)


def _relative_components_are_portable(value: PureWindowsPath) -> bool:
    """Reject Windows device/ADS spellings before any filesystem access."""

    if value.drive or value.root:
        return False
    for component in value.parts:
        if ":" in component or any(ord(character) < 32 for character in component):
            return False
        if platform.system() == "Windows" and (
            component.rstrip(" .") != component
            or any(character in component for character in '<>"|?*')
            or component.split(".", 1)[0].upper() in _WINDOWS_RESERVED_COMPONENTS
        ):
            return False
    return True


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
        lexical_root = Path(os.path.abspath(os.fspath(root.expanduser())))
        if not lexical_root.is_dir() or not _path_components_are_safe(lexical_root):
            raise LocalAgentError("workspace_link_or_reparse_refused")
        self.root = lexical_root.resolve()
        self._command_timeout = command_timeout
        self._runner = runner or run_with_tree_kill
        self._fetcher = fetcher
        self._write_lock = threading.RLock()

    def _lexical_candidate(self, relative: str) -> Path:
        if not relative or "\x00" in relative:
            raise LocalAgentError("path_invalid")
        posix = PurePosixPath(relative)
        windows = PureWindowsPath(relative)
        if (
            posix.is_absolute()
            or windows.is_absolute()
            or ".." in posix.parts
            or ".." in windows.parts
        ):
            raise LocalAgentError("path_outside_workspace")
        if any(
            component.casefold() in _SKIPPED_COMPONENTS
            for component in (*posix.parts, *windows.parts)
        ):
            raise LocalAgentError("workspace_path_not_found")
        if not _relative_components_are_portable(windows):
            raise LocalAgentError("path_invalid")
        if platform.system() != "Windows" and "\\" in relative:
            raise LocalAgentError("path_invalid")
        candidate = Path(os.path.abspath(os.fspath(self.root / Path(relative))))
        if candidate != self.root and self.root not in candidate.parents:
            raise LocalAgentError("path_outside_workspace")
        return candidate

    def resolve(self, relative: str) -> Path:
        if relative in {"", "."}:
            candidate = self.root
        else:
            candidate = self._lexical_candidate(relative).resolve()
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

    def list_entries(
        self, path: str = "."
    ) -> tuple[tuple[WorkspacePathEntry, ...], bool]:
        target = self.root if path in {"", "."} else self._lexical_candidate(path)
        if target != self.root and target.name in SKIP_DIRS:
            raise LocalAgentError("workspace_directory_unavailable")
        if not _path_components_are_safe(target):
            raise LocalAgentError("workspace_link_or_reparse_refused")
        try:
            metadata = target.lstat()
        except FileNotFoundError as error:
            raise LocalAgentError("workspace_path_not_found") from error
        except OSError as error:
            raise LocalAgentError("workspace_directory_unavailable") from error
        if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise LocalAgentError("workspace_not_a_directory")

        candidates: list[Path] = []
        scan_complete = True
        try:
            for candidate in target.iterdir():
                if len(candidates) >= MAX_TREE_SCAN_ENTRIES:
                    scan_complete = False
                    break
                candidates.append(candidate)
        except OSError as error:
            raise LocalAgentError("workspace_directory_unavailable") from error

        entries: list[WorkspacePathEntry] = []
        for candidate in candidates:
            relative = candidate.relative_to(self.root).as_posix()
            try:
                item = candidate.lstat()
            except OSError:
                entries.append(
                    WorkspacePathEntry(
                        path=relative,
                        name=candidate.name,
                        kind="unavailable",
                        byte_size=None,
                        editable_candidate=False,
                    )
                )
                continue
            if (
                candidate.name in SKIP_DIRS
                or _is_link_or_reparse(item)
                or not _path_components_are_safe(candidate)
                or not _relative_components_are_portable(PureWindowsPath(relative))
            ):
                kind: Literal["directory", "file", "unavailable"] = "unavailable"
                size = None
                editable = False
            elif stat.S_ISDIR(item.st_mode):
                kind = "directory"
                size = None
                editable = False
            elif stat.S_ISREG(item.st_mode):
                kind = "file"
                size = item.st_size
                editable = item.st_nlink == 1 and item.st_size <= MAX_FILE_WRITE_BYTES
            else:
                kind = "unavailable"
                size = None
                editable = False
            entries.append(
                WorkspacePathEntry(
                    path=relative,
                    name=candidate.name,
                    kind=kind,
                    byte_size=size,
                    editable_candidate=editable,
                )
            )
        order = {"directory": 0, "file": 1, "unavailable": 2}
        entries.sort(key=lambda entry: (order[entry.kind], entry.name.casefold(), entry.name))
        complete = scan_complete and len(entries) <= MAX_LIST_ENTRIES
        return tuple(entries[:MAX_LIST_ENTRIES]), complete

    def read_text_snapshot(self, path: str) -> WorkspaceTextSnapshot:
        target = self._lexical_candidate(path)
        snapshot = self._snapshot_file(target)
        if snapshot is None:
            raise LocalAgentError("workspace_path_not_found")
        payload = snapshot[0]
        try:
            content = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise LocalAgentError("workspace_binary_refused") from error
        if "\x00" in content:
            raise LocalAgentError("workspace_binary_refused")
        without_crlf = payload.replace(b"\r\n", b"")
        if b"\r" in without_crlf or (b"\r\n" in payload and b"\n" in without_crlf):
            raise LocalAgentError("workspace_line_endings_unsupported")
        if b"\r\n" in payload:
            line_ending: Literal["lf", "crlf", "none"] = "crlf"
            content = content.replace("\r\n", "\n")
        elif b"\n" in payload:
            line_ending = "lf"
        else:
            line_ending = "none"
        return WorkspaceTextSnapshot(
            path=target.relative_to(self.root).as_posix(),
            content=content,
            revision=hashlib.sha256(payload).hexdigest(),
            byte_size=len(payload),
            line_ending=line_ending,
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

    @staticmethod
    def _identity(metadata: os.stat_result) -> tuple[int, int]:
        return metadata.st_dev, metadata.st_ino

    @staticmethod
    def _write_all(descriptor: int, payload: bytes) -> None:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short local write")
            offset += written

    def _snapshot_file(
        self, target: Path
    ) -> tuple[bytes, os.stat_result] | None:
        if not _path_components_are_safe(target):
            raise LocalAgentError("workspace_link_or_reparse_refused")
        try:
            before = target.lstat()
        except FileNotFoundError:
            return None
        except OSError as error:
            raise LocalAgentError("workspace_file_unavailable") from error
        if (
            _is_link_or_reparse(before)
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > MAX_FILE_WRITE_BYTES
        ):
            raise LocalAgentError("workspace_file_unavailable")
        try:
            payload = target.read_bytes()
            after = target.lstat()
        except OSError as error:
            raise LocalAgentError("workspace_file_unavailable") from error
        if (
            self._identity(before) != self._identity(after)
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or _is_link_or_reparse(after)
            or after.st_nlink != 1
        ):
            raise LocalAgentError("workspace_file_changed")
        return payload, after

    def prepare_write(self, path: str, content: str) -> PreparedWrite:
        try:
            proposed = content.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise LocalAgentError("workspace_text_invalid") from error
        if len(proposed) > MAX_FILE_WRITE_BYTES:
            raise LocalAgentError("workspace_file_too_large")
        if b"\x00" in proposed:
            raise LocalAgentError("workspace_binary_refused")
        target = self._lexical_candidate(path)
        parent = target.parent
        if not _path_components_are_safe(parent):
            raise LocalAgentError("workspace_link_or_reparse_refused")
        try:
            parent_metadata = parent.lstat()
        except OSError as error:
            raise LocalAgentError("workspace_parent_unavailable") from error
        if _is_link_or_reparse(parent_metadata) or not stat.S_ISDIR(parent_metadata.st_mode):
            raise LocalAgentError("workspace_parent_unavailable")
        snapshot = self._snapshot_file(target)
        before_bytes = snapshot[0] if snapshot is not None else b""
        try:
            before_text = before_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise LocalAgentError("workspace_binary_refused") from error
        if "\x00" in before_text:
            raise LocalAgentError("workspace_binary_refused")
        canonical_path = target.relative_to(self.root).as_posix()
        diff = difflib.unified_diff(
            before_text.split("\n"),
            content.split("\n"),
            fromfile=f"a/{canonical_path}",
            tofile=f"b/{canonical_path}",
            lineterm="",
            n=2,
        )
        text = "\n".join(diff)
        if not text:
            text = (
                "(no change)"
                if snapshot is not None
                else f"(new file, {len(content.splitlines())} lines)"
            )
        if len(text) > MAX_DIFF_CHARS:
            raise LocalAgentError("change_too_large_to_review")
        return PreparedWrite(
            path=target.relative_to(self.root).as_posix(),
            content=content,
            preview=text,
            base_sha256=(hashlib.sha256(before_bytes).hexdigest() if snapshot else None),
            base_identity=(self._identity(snapshot[1]) if snapshot else None),
            parent_identity=self._identity(parent_metadata),
            proposed_sha256=hashlib.sha256(proposed).hexdigest(),
            existed=snapshot is not None,
            mode=(stat.S_IMODE(snapshot[1].st_mode) if snapshot else None),
        )

    def diff_preview(self, path: str, content: str) -> str:
        return self.prepare_write(path, content).preview

    def apply_prepared_write(self, prepared: PreparedWrite) -> ToolOutcome:
        target = self._lexical_candidate(prepared.path)
        proposed = prepared.content.encode("utf-8", errors="strict")
        if hashlib.sha256(proposed).hexdigest() != prepared.proposed_sha256:
            return ToolOutcome(
                False,
                "change no longer matches its reviewed preview",
                "workspace_preview_mismatch",
            )
        with self._write_lock:
            try:
                parent_metadata = target.parent.lstat()
                snapshot = self._snapshot_file(target)
            except (OSError, LocalAgentError):
                return ToolOutcome(
                    False,
                    "file is no longer safe to write; inspect it again",
                    "workspace_file_unavailable",
                )
            current_sha = hashlib.sha256(snapshot[0]).hexdigest() if snapshot else None
            current_identity = self._identity(snapshot[1]) if snapshot else None
            if (
                self._identity(parent_metadata) != prepared.parent_identity
                or current_sha != prepared.base_sha256
                or current_identity != prepared.base_identity
                or (snapshot is not None) != prepared.existed
            ):
                return ToolOutcome(
                    False,
                    "file changed since preview; read it again and propose a new change",
                    "workspace_revision_changed",
                )

            temporary: str | None = None
            try:
                if prepared.existed:
                    descriptor, temporary = tempfile.mkstemp(
                        prefix=".prompt-enhancer-edit-",
                        suffix=".tmp",
                        dir=target.parent,
                    )
                    try:
                        self._write_all(descriptor, proposed)
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                    if prepared.mode is not None:
                        os.chmod(temporary, prepared.mode)
                    latest = self._snapshot_file(target)
                    latest_parent = target.parent.lstat()
                    if (
                        latest is None
                        or self._identity(latest[1]) != prepared.base_identity
                        or hashlib.sha256(latest[0]).hexdigest() != prepared.base_sha256
                        or self._identity(latest_parent) != prepared.parent_identity
                    ):
                        return ToolOutcome(
                            False,
                            "file changed since preview; read it again and propose a new change",
                            "workspace_revision_changed",
                        )
                    os.replace(temporary, target)
                    temporary = None
                else:
                    flags = (
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_BINARY", 0)
                        | getattr(os, "O_NOFOLLOW", 0)
                    )
                    descriptor = os.open(target, flags, 0o600)
                    try:
                        self._write_all(descriptor, proposed)
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
            except (OSError, LocalAgentError):
                return ToolOutcome(
                    False,
                    "file changed or became unsafe before it could be written",
                    "workspace_revision_changed",
                )
            finally:
                if temporary is not None:
                    try:
                        os.unlink(temporary)
                    except OSError:
                        pass
            try:
                written = self._snapshot_file(target)
            except LocalAgentError:
                return ToolOutcome(
                    False,
                    "write completed but the file could not be verified",
                    "workspace_verification_failed",
                )
            if written is None or hashlib.sha256(written[0]).hexdigest() != prepared.proposed_sha256:
                return ToolOutcome(
                    False,
                    "write completed but the file could not be verified",
                    "workspace_verification_failed",
                )
            return ToolOutcome(True, f"wrote {prepared.path} ({len(prepared.content)} characters)")

    def write_file(self, path: str, content: str) -> ToolOutcome:
        return self.apply_prepared_write(self.prepare_write(path, content))

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
    "PreparedWrite",
    "ToolOutcome",
    "WorkspacePathEntry",
    "WorkspaceTextSnapshot",
    "WorkspaceTools",
    "minimal_environment",
    "run_with_tree_kill",
)
