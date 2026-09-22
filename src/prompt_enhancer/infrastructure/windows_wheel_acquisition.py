"""Hash-pinned registry wheel acquisition for an already reviewed plan.

This is deliberately a downloader, not an installer: it follows no redirects,
uses no proxy/auth configuration, extracts nothing, and publishes only a fresh
directory of bytes verified against both the plan and ``uv.lock``.
"""
from __future__ import annotations

import hashlib
import http.client
import os
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Protocol
from urllib.parse import urlsplit
import ssl

from packaging.utils import canonicalize_name

from .windows_dependency_preparation import WindowsDependencyPreparationReport
from .windows_wheel_inventory import WindowsWheelArtifact, WindowsWheelInventory, _lock_bytes

_HOST = "files.pythonhosted.org"
_MAX_WHEEL_BYTES = 128 * 1024 * 1024
_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_ARTIFACTS = 128
_REPARSE = 0x400


class WindowsWheelAcquisitionError(RuntimeError):
    """Content-free failure while acquiring reviewed registry wheel bytes."""


class _Response(Protocol):
    status: int
    url: str
    def read_chunk(self, size: int, timeout_seconds: float) -> bytes: ...
    def close(self) -> None: ...


Transport = Callable[[str, float], _Response]


@dataclass(frozen=True, slots=True)
class AcquiredWindowsWheels:
    files: tuple[tuple[str, int, str], ...]
    unresolved_blockers: tuple[str, ...]
    source_license_discrepancy_review_required: bool
    source_network_isolation_not_proven: bool
    source_python_runtime_dependencies_not_pinned: bool
    complete: bool = False
    release_accepted: bool = False

    def wheel_files(self, destination: Path) -> dict[str, Path]:
        return {name: Path(destination) / name for name, _size, _digest in self.files}


def _fail(message: str, error: Exception | None = None) -> None:
    if error is None: raise WindowsWheelAcquisitionError(message)
    raise WindowsWheelAcquisitionError(message) from error


def _unsafe(value: os.stat_result) -> bool:
    return stat.S_ISLNK(value.st_mode) or bool(getattr(value, "st_file_attributes", 0) & _REPARSE)


def _ancestors(path: Path) -> None:
    while True:
        try: value = path.lstat()
        except OSError as error: _fail("wheel acquisition destination is unavailable", error)
        if not stat.S_ISDIR(value.st_mode) or _unsafe(value): _fail("wheel acquisition destination is unavailable")
        if path.parent == path: return
        path = path.parent


def _url(value: object, artifact: WindowsWheelArtifact) -> str | None:
    if not isinstance(value, str): return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value): return None
    try: parsed = urlsplit(value); port = parsed.port
    except ValueError: return None
    path = PurePosixPath(parsed.path)
    if (parsed.scheme != "https" or parsed.hostname != _HOST or port is not None
            or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
            or not parsed.path.startswith("/packages/") or ".." in path.parts
            or path.name != artifact.filename): return None
    return value


def _lock_url(lock: dict[str, object], artifact: WindowsWheelArtifact) -> str:
    matches: list[dict[str, object]] = []
    for package in lock.get("package", []):
        if isinstance(package, dict) and canonicalize_name(str(package.get("name", ""))) == artifact.package and str(package.get("version", "")) == artifact.version:
            matches.append(package)
    if len(matches) != 1 or not isinstance(matches[0].get("wheels"), list): _fail("wheel acquisition lock does not match review")
    urls = []
    for wheel in matches[0]["wheels"]:
        if not isinstance(wheel, dict): continue
        url = _url(wheel.get("url"), artifact)
        if url is not None and wheel.get("hash") == f"sha256:{artifact.sha256}" and wheel.get("size") == artifact.size_bytes:
            urls.append(url)
    if len(urls) != 1: _fail("wheel acquisition lock does not match review")
    return urls[0]


def _validate(report: WindowsDependencyPreparationReport, inventory: WindowsWheelInventory,
              lockfile: Path) -> dict[str, object]:
    if (not isinstance(report, WindowsDependencyPreparationReport) or not isinstance(inventory, WindowsWheelInventory)
            or inventory.complete is not True or report.complete is not False or report.release_accepted is not False
            or report.target != inventory.target or report.registry_wheels != inventory.artifacts
            or report.lockfile_sha256 != inventory.lockfile_sha256 or report.pyproject_sha256 != inventory.pyproject_sha256
            or report.registry_export_fingerprint != inventory.export_fingerprint):
        _fail("wheel acquisition plan is invalid")
    try: return _lock_bytes(Path(lockfile), report.lockfile_sha256)
    except Exception as error: _fail("wheel acquisition lock does not match review", error)


class _HttpsResponse:
    """Minimal proxiless HTTPS response with a timeout per bounded read."""
    def __init__(self, connection: http.client.HTTPSConnection, response: http.client.HTTPResponse, url: str):
        self._connection, self._response, self.url = connection, response, url
        self.status = response.status

    def read_chunk(self, size: int, timeout_seconds: float) -> bytes:
        if self._connection.sock is None: raise OSError("connection unavailable")
        self._connection.sock.settimeout(timeout_seconds)
        return self._response.read1(size)

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._connection.close()


def _https_transport(url: str, timeout: float) -> _Response:
    parsed = urlsplit(url)
    connection = http.client.HTTPSConnection(_HOST, port=443, timeout=timeout, context=ssl.create_default_context())
    try:
        connection.request("GET", parsed.path, headers={"Host": _HOST, "User-Agent": "prompt-enhancer-wheel-acquisition/1"})
        return _HttpsResponse(connection, connection.getresponse(), url)
    except Exception:
        connection.close()
        raise


def _download(url: str, artifact: WindowsWheelArtifact, destination: Path, transport: Transport,
              deadline: float) -> None:
    response: _Response | None = None
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0: _fail("wheel acquisition deadline exceeded")
        response = transport(url, remaining)
        if response.status != 200 or response.url != url: _fail("wheel acquisition response is invalid")
        size = 0; digest = hashlib.sha256()
        with destination.open("xb") as output:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0: _fail("wheel acquisition deadline exceeded")
                chunk = response.read_chunk(64 * 1024, remaining)
                if time.monotonic() >= deadline: _fail("wheel acquisition deadline exceeded")
                if not chunk: break
                if not isinstance(chunk, bytes): _fail("wheel acquisition response is invalid")
                size += len(chunk)
                if size > artifact.size_bytes or size > _MAX_WHEEL_BYTES: _fail("wheel acquisition response exceeds review")
                digest.update(chunk); output.write(chunk)
        if size != artifact.size_bytes or digest.hexdigest() != artifact.sha256:
            _fail("wheel acquisition response does not match review")
    except WindowsWheelAcquisitionError: raise
    except Exception as error: _fail("wheel acquisition network failed", error)
    finally:
        if response is not None:
            try: response.close()
            except Exception: pass


def acquire_windows_wheels(*, report: WindowsDependencyPreparationReport, inventory: WindowsWheelInventory,
                           lockfile: Path, destination: Path, transport: Transport = _https_transport,
                           timeout_seconds: float = 20.0) -> AcquiredWindowsWheels:
    """Fetch only lock-selected registry wheels into a fresh local directory."""
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not 0 < timeout_seconds <= 120:
        _fail("wheel acquisition timeout is invalid")
    lock = _validate(report, inventory, lockfile)
    output = Path(os.path.abspath(destination))
    if ".." in Path(destination).parts or output.exists() or output.is_symlink(): _fail("wheel acquisition destination is unavailable")
    _ancestors(output.parent)
    if not 1 <= len(inventory.artifacts) <= _MAX_ARTIFACTS: _fail("wheel acquisition plan is invalid")
    planned: list[tuple[WindowsWheelArtifact, str]] = []
    total = 0
    for artifact in inventory.artifacts:
        if (not isinstance(artifact.size_bytes, int) or isinstance(artifact.size_bytes, bool) or not 0 < artifact.size_bytes <= _MAX_WHEEL_BYTES
                or len(artifact.sha256) != 64 or Path(artifact.filename).name != artifact.filename): _fail("wheel acquisition plan is invalid")
        total += artifact.size_bytes
        if total > _MAX_TOTAL_BYTES: _fail("wheel acquisition plan exceeds bounds")
        planned.append((artifact, _lock_url(lock, artifact)))
    temporary = Path(tempfile.mkdtemp(prefix=".wheel-acquisition-incomplete-", dir=output.parent))
    deadline = time.monotonic() + float(timeout_seconds)
    try:
        files = []
        for artifact, url in planned:
            _download(url, artifact, temporary / artifact.filename, transport, deadline)
            files.append((artifact.filename, artifact.size_bytes, artifact.sha256))
        if output.exists() or output.is_symlink(): _fail("wheel acquisition destination is unavailable")
        os.rename(temporary, output)
    except Exception as error:
        try:
            if (temporary.exists() and (temporary.parent != output.parent or _unsafe(temporary.lstat()))):
                _fail("wheel acquisition cleanup unconfirmed", error)
            for directory, directories, names in os.walk(temporary, topdown=True, followlinks=False):
                if any(_unsafe((Path(directory) / name).lstat()) for name in [*directories, *names]):
                    _fail("wheel acquisition cleanup unconfirmed", error)
            if temporary.exists(): shutil.rmtree(temporary)
        except OSError: _fail("wheel acquisition cleanup unconfirmed", error)
        raise
    source = report.prepared_source_wheels
    return AcquiredWindowsWheels(tuple(files), report.unresolved_blockers,
        any(item.license_discrepancy_review_required for item in source),
        any(item.network_isolation_not_proven for item in source),
        any(item.python_runtime_dependencies_not_pinned for item in source))


__all__ = ("AcquiredWindowsWheels", "Transport", "WindowsWheelAcquisitionError", "acquire_windows_wheels")
