"""Explicit, app-local pywin32 bootstrap for an isolated embeddable runtime.

It intentionally does not enable ``site`` or process ``.pth`` files.  The
small fixed path set replaces pywin32's arbitrary ``.pth`` import hook.
"""
from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, MutableSequence, Protocol

_REPARSE = 0x400
_IMPORT_DIRECTORIES = ("win32", "win32/lib", "pythonwin")
_DLL_DIRECTORIES = ("pywin32_system32",)


class WindowsRuntimeBootstrapError(RuntimeError):
    """Content-free failure while binding the staged runtime bootstrap."""


class DllDirectoryHandle(Protocol):
    def close(self) -> None: ...


class _OwnedPath(str):
    """Identity marker so teardown cannot remove a later equal path string."""


@dataclass(slots=True)
class WindowsRuntimeBootstrap:
    staged_root: Path
    import_paths: tuple[Path, ...]
    dll_paths: tuple[Path, ...]
    _path_list: MutableSequence[str]
    _inserted: tuple[_OwnedPath, ...]
    _handles: tuple[DllDirectoryHandle, ...]
    site_enabled_by_bootstrap: bool = False
    pth_executed_by_bootstrap: bool = False
    _closed: bool = False

    def close(self) -> None:
        """Release DLL search handles and remove only paths this object added."""
        if self._closed: return
        self._closed = True
        failures: list[Exception] = []
        for handle in reversed(self._handles):
            try: handle.close()
            except Exception as error: failures.append(error)
        for value in self._inserted:
            for index, current in enumerate(self._path_list):
                if current is value:
                    del self._path_list[index]
                    break
        if failures: _fail("windows runtime bootstrap cleanup unconfirmed", failures[0])


def _fail(message: str, error: Exception | None = None) -> None:
    if error is None: raise WindowsRuntimeBootstrapError(message)
    raise WindowsRuntimeBootstrapError(message) from error


def _ordinary_directory(path: Path) -> None:
    current = path
    while True:
        try: value = current.lstat()
        except OSError as error: _fail("windows runtime bootstrap path is unavailable", error)
        if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode) or getattr(value, "st_file_attributes", 0) & _REPARSE:
            _fail("windows runtime bootstrap path is unsafe")
        if current.parent == current: return
        current = current.parent


def _bound(root: Path, relative: str) -> Path:
    candidate = root.joinpath(*relative.split("/"))
    try:
        if os.path.normcase(os.path.commonpath((os.fspath(root), os.fspath(candidate)))) != os.path.normcase(os.fspath(root)):
            _fail("windows runtime bootstrap path is unsafe")
    except ValueError as error: _fail("windows runtime bootstrap path is unsafe", error)
    _ordinary_directory(candidate)
    return candidate


def bootstrap_windows_runtime(*, staged_root: Path, add_dll_directory: Callable[[str], DllDirectoryHandle],
                              path_list: MutableSequence[str]) -> WindowsRuntimeBootstrap:
    """Bind only reviewed pywin32 import/DLL directories to one staged root."""
    raw = os.fspath(staged_root)
    if ".." in Path(raw).parts: _fail("windows runtime bootstrap path is unsafe")
    root = Path(os.path.abspath(raw)); _ordinary_directory(root)
    imports = tuple(_bound(root, item) for item in _IMPORT_DIRECTORIES)
    dlls = tuple(_bound(root, item) for item in _DLL_DIRECTORIES)
    inserted: list[_OwnedPath] = []
    handles: list[DllDirectoryHandle] = []
    try:
        # Insert in reverse so the declared order is preserved at the front.
        for path in reversed(imports):
            value = os.fspath(path)
            if value not in path_list:
                owned = _OwnedPath(value)
                path_list.insert(0, owned); inserted.append(owned)
        for path in dlls: handles.append(add_dll_directory(os.fspath(path)))
        return WindowsRuntimeBootstrap(root, imports, dlls, path_list, tuple(inserted), tuple(handles))
    except Exception as error:
        cleanup_failed = False
        for handle in reversed(handles):
            try: handle.close()
            except Exception: cleanup_failed = True
        for value in inserted:
            for index, current in enumerate(path_list):
                if current is value:
                    del path_list[index]
                    break
        if cleanup_failed: _fail("windows runtime bootstrap cleanup unconfirmed", error)
        _fail("windows runtime bootstrap failed", error)


def _isolated_pth(root: Path, major: int, minor: int) -> bool:
    marker = root / f"python{major}{minor}._pth"
    try:
        before = marker.lstat()
    except FileNotFoundError:
        return False
    try:
        _ordinary_directory(root)
        def snapshot(value: os.stat_result) -> tuple[int, ...]:
            if (not stat.S_ISREG(value.st_mode) or stat.S_ISLNK(value.st_mode)
                    or getattr(value, "st_file_attributes", 0) & _REPARSE
                    or not 0 < value.st_size <= 4096 or not value.st_ino):
                raise ValueError()
            # CPython 3.13 Windows lstat aliases ctime to birthtime, while
            # fstat can expose metadata-change time. Compare creation time
            # across APIs, but preserve ctime checks within each API below.
            # https://docs.python.org/3.13/library/os.html#os.stat_result
            return (
                value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size,
                value.st_mtime_ns,
                getattr(value, "st_birthtime_ns", value.st_ctime_ns),
                getattr(value, "st_file_attributes", 0),
            )

        expected = snapshot(before)
        with marker.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if snapshot(opened) != expected:
                raise ValueError()
            data = stream.read(4097)
            read_completed = os.fstat(stream.fileno())
            after = marker.lstat()
            if (snapshot(read_completed) != expected or snapshot(after) != expected
                    or opened.st_ctime_ns != read_completed.st_ctime_ns
                    or before.st_ctime_ns != after.st_ctime_ns
                    or len(data) != before.st_size or len(data) > 4096):
                raise ValueError()
        active = [line.strip() for line in data.decode("utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if active != [f"python{major}{minor}.zip", "."]:
            raise ValueError()
    except (OSError, UnicodeDecodeError, ValueError) as error:
        _fail("windows runtime bootstrap path is unsafe", error)
    return True


def bootstrap_current_embedded_windows_runtime(*, platform: str | None = None,
                                               executable: str | None = None,
                                               version: tuple[int, int] | None = None,
                                               add_dll_directory: Callable[[str], DllDirectoryHandle] | None = None,
                                               path_list: MutableSequence[str] | None = None) -> WindowsRuntimeBootstrap | None:
    """Bind pywin32 only when executing from an app-local embeddable runtime."""
    if (os.name if platform is None else platform) != "nt":
        return None
    major, minor = (sys.version_info.major, sys.version_info.minor) if version is None else version
    root = Path(os.path.abspath(sys.executable if executable is None else executable)).parent
    if not _isolated_pth(root, major, minor):
        return None
    if add_dll_directory is None:
        try: add_dll_directory = os.add_dll_directory
        except AttributeError as error: _fail("windows runtime bootstrap is unavailable", error)
    return bootstrap_windows_runtime(staged_root=root, add_dll_directory=add_dll_directory, path_list=sys.path if path_list is None else path_list)


__all__ = ("DllDirectoryHandle", "WindowsRuntimeBootstrap", "WindowsRuntimeBootstrapError", "bootstrap_current_embedded_windows_runtime", "bootstrap_windows_runtime")
