"""Expand reviewed wheels into a reviewed Windows runtime, entirely offline."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from packaging.tags import Tag
from packaging.utils import canonicalize_name, parse_wheel_filename

from .windows_python_runtime import WindowsPythonRuntimeFile
from .windows_wheel_inventory import WindowsWheelArtifact, WindowsWheelTarget, _target_tags

_REPARSE = 0x400
_MAX_WHEEL_BYTES = 128 * 1024 * 1024
_MAX_MEMBERS = 2_048
_MAX_MEMBER_BYTES = 64 * 1024 * 1024
_MAX_EXPANDED_BYTES = 256 * 1024 * 1024
_RESERVED = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))})
_MACHINE = {"amd64": 0x8664, "arm64": 0xAA64}


class WindowsWheelStagingError(RuntimeError):
    """Content-free failure while preparing an offline wheel runtime."""


@dataclass(frozen=True, slots=True)
class StagedWindowsWheels:
    files: tuple[tuple[str, int, str], ...]
    native_dll_dependencies_unresolved: bool = True
    runtime_execution_unproven: bool = True
    installable_product_unproven: bool = True
    complete: bool = False


def _fail(message: str, error: Exception | None = None) -> None:
    if error is None:
        raise WindowsWheelStagingError(message)
    raise WindowsWheelStagingError(message) from error


def _identity(value: os.stat_result) -> tuple[object, ...]:
    return (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode), value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns,
            getattr(value, "st_file_attributes", 0))


def _unsafe(value: os.stat_result) -> bool:
    return stat.S_ISLNK(value.st_mode) or bool(getattr(value, "st_file_attributes", 0) & _REPARSE)


def _ordinary_file(path: Path, maximum: int, *, allow_empty: bool = False) -> os.stat_result:
    try:
        value = path.lstat()
    except OSError as error:
        _fail("wheel staging input is unavailable", error)
    if (not stat.S_ISREG(value.st_mode) or _unsafe(value) or value.st_nlink != 1
            or not (0 <= value.st_size <= maximum if allow_empty else 0 < value.st_size <= maximum)):
        _fail("wheel staging input is unsafe")
    return value


def _ordinary_ancestors(path: Path) -> None:
    current = path
    while True:
        try:
            value = current.lstat()
        except OSError as error:
            _fail("wheel staging input is unavailable", error)
        if not stat.S_ISDIR(value.st_mode) or _unsafe(value):
            _fail("wheel staging input is unsafe")
        if current.parent == current:
            return
        current = current.parent


def _absolute(path: Path, *, purpose: str) -> Path:
    try:
        raw = os.fspath(path)
        if ".." in Path(raw).parts:
            _fail(f"wheel staging {purpose} is unavailable")
        return Path(os.path.abspath(raw))
    except (OSError, TypeError) as error:
        _fail(f"wheel staging {purpose} is unavailable", error)


def _within(parent: Path, child: Path) -> bool:
    try:
        return os.path.normcase(os.path.commonpath((os.fspath(parent), os.fspath(child)))) == os.path.normcase(os.fspath(parent))
    except ValueError:
        return False


def _read_regular(path: Path, maximum: int, *, expected_size: int | None = None,
                  expected_hash: str | None = None, allow_empty: bool = False) -> bytes:
    _ordinary_ancestors(path.parent)
    before = _ordinary_file(path, maximum, allow_empty=allow_empty)
    if expected_size is not None and before.st_size != expected_size:
        _fail("wheel staging input does not match review")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            opened = os.fstat(source.fileno())
            if _identity(before) != _identity(opened):
                _fail("wheel staging input changed")
            result = bytearray()
            while chunk := source.read(min(64 * 1024, maximum + 1 - len(result))):
                result.extend(chunk)
                if len(result) > maximum:
                    _fail("wheel staging input is unsafe")
            after_open = os.fstat(source.fileno())
    except OSError as error:
        _fail("wheel staging input is unavailable", error)
    after = _ordinary_file(path, maximum, allow_empty=allow_empty)
    data = bytes(result)
    if (_identity(before) != _identity(after_open) or _identity(before) != _identity(after)
            or len(data) != before.st_size
            or (expected_hash is not None and hashlib.sha256(data).hexdigest() != expected_hash)):
        _fail("wheel staging input does not match review")
    return data


def _parts(name: str) -> tuple[str, ...]:
    raw = name.split("/")
    value = PurePosixPath(name)
    if (not name or value.is_absolute() or "\\" in name or any(
            part in {"", ".", ".."} or ":" in part or part != part.rstrip(". ")
            or part.rstrip(". ").split(".", 1)[0].casefold() in _RESERVED for part in raw)):
        _fail("wheel staging archive layout is invalid")
    return value.parts


def _record_digest(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def _headers(data: bytes, kind: str, *, permit_body: bool = False) -> dict[str, list[str]]:
    if len(data) > 256 * 1024:
        _fail("wheel staging wheel is invalid")
    try:
        result: dict[str, list[str]] = {}
        current: str | None = None
        in_body = False
        lines = data.decode("utf-8").splitlines()
        for index, line in enumerate(lines):
            if in_body:
                continue
            if line == "" and permit_body:
                in_body = True
                continue
            if line == "":
                # A WHEEL header block may end with a conventional blank line,
                # but it has no RFC metadata body to accept after that point.
                if all(not trailing for trailing in lines[index:]):
                    break
                raise ValueError
            if line.startswith((" ", "\t")) and current:
                result[current][-1] += " " + line.strip()
                continue
            key, separator, value = line.partition(":")
            if not separator or not key or key != key.strip() or not value.startswith(" "):
                raise ValueError
            current = key.casefold()
            result.setdefault(current, []).append(value[1:].strip())
        if not result:
            raise ValueError
        return result
    except (UnicodeDecodeError, ValueError) as error:
        _fail(f"wheel staging {kind} is invalid", error)


def _wheel_contents(data: bytes, artifact: WindowsWheelArtifact,
                    target: WindowsWheelTarget) -> list[tuple[str, bytes]]:
    try:
        distribution, version, _build, filename_tags = parse_wheel_filename(artifact.filename)
        permitted = set(_target_tags(target))
        if (canonicalize_name(distribution) != artifact.package or str(version) != artifact.version
                or not set(filename_tags) & permitted):
            raise ValueError("filename")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if not 1 <= len(infos) <= _MAX_MEMBERS:
                raise ValueError("count")
            entries: dict[str, zipfile.ZipInfo] = {}
            folded: set[str] = set(); total = 0
            for info in infos:
                key = info.filename.rstrip("/")
                _parts(key)
                if (key.casefold() in folded or key in entries or stat.S_ISLNK(info.external_attr >> 16)
                        or info.file_size > _MAX_MEMBER_BYTES or info.compress_size < 0):
                    raise ValueError("entry")
                folded.add(key.casefold()); entries[key] = info
                if not info.is_dir():
                    total += info.file_size
                    if total > _MAX_EXPANDED_BYTES:
                        raise ValueError("size")
            files = {name: info for name, info in entries.items() if not info.is_dir()}
            dist_infos = {name.split("/", 1)[0] for name in files if "/" in name and name.split("/", 1)[0].endswith(".dist-info")}
            if len(dist_infos) != 1:
                raise ValueError("dist-info")
            dist_info = next(iter(dist_infos))
            dist_stem = dist_info.removesuffix(".dist-info")
            package_stem, separator, package_version = dist_stem.rpartition("-")
            if (not separator or canonicalize_name(package_stem) != artifact.package
                    or package_version != artifact.version):
                raise ValueError("dist-info identity")
            wheel_name, metadata_name, record_name = (f"{dist_info}/{item}" for item in ("WHEEL", "METADATA", "RECORD"))
            if not {wheel_name, metadata_name, record_name} <= set(files):
                raise ValueError("metadata")
            wheel_headers = _headers(archive.read(wheel_name), "WHEEL")
            metadata_headers = _headers(archive.read(metadata_name), "METADATA", permit_body=True)
            try:
                wheel_tags = {Tag(*item.split("-", 2)) for item in wheel_headers.get("tag", []) if item.count("-") == 2}
            except TypeError as error:
                raise ValueError("tag") from error
            if (len(wheel_headers.get("wheel-version", [])) != 1 or re.fullmatch(r"1\.\d+", wheel_headers["wheel-version"][0]) is None
                    or len(wheel_headers.get("root-is-purelib", [])) != 1
                    or set(wheel_headers) - {"wheel-version", "generator", "root-is-purelib", "tag", "build"}
                    or set(wheel_tags) != set(filename_tags) or not wheel_tags & permitted
                    or wheel_headers.get("root-is-purelib", [""])[0].casefold() not in {"true", "false"}
                    or not metadata_headers.get("metadata-version") or len(metadata_headers.get("name", [])) != 1 or len(metadata_headers.get("version", [])) != 1
                    or canonicalize_name(metadata_headers["name"][0]) != artifact.package
                    or metadata_headers["version"][0] != artifact.version):
                raise ValueError("metadata identity")
            rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"), newline="")))
            records: dict[str, tuple[str, str]] = {}
            for row in rows:
                if len(row) != 3 or row[0] in records or row[0] not in files:
                    raise ValueError("record")
                records[row[0]] = (row[1], row[2])
            if set(records) != set(files) or records[record_name] != ("", ""):
                raise ValueError("record")
            output: dict[str, bytes] = {}
            for name, info in files.items():
                payload = archive.read(info)
                digest, size = records[name]
                if name != record_name and (digest != _record_digest(payload) or size != str(len(payload))):
                    raise ValueError("record checksum")
                if ".data/" in name:
                    prefix, scheme, relative = name.split("/", 2)
                    if (prefix != f"{dist_stem}.data" or scheme not in {"purelib", "platlib", "scripts"}
                            or not relative):
                        raise ValueError("unsupported data scheme")
                    # Script entry points stay private to the prepared runtime.
                    # They are copied as inert bytes, never invoked, and are not
                    # allowed to target a system/global scripts directory.
                    name = relative if scheme in {"purelib", "platlib"} else f"Scripts/{relative}"
                if name in output:
                    raise ValueError("relocated collision")
                output[name] = payload
            # The wheel's RECORD describes archive paths, while data-scheme
            # members above have new installed paths.  Emit a fresh, exact
            # installed RECORD rather than leaving misleading provenance.
            if record_name not in output:
                raise ValueError("record relocation")
            record_stream = io.StringIO(newline="")
            writer = csv.writer(record_stream, lineterminator="\n")
            for name, payload in sorted(output.items()):
                if name != record_name:
                    writer.writerow((name, _record_digest(payload), str(len(payload))))
            writer.writerow((record_name, "", ""))
            output[record_name] = record_stream.getvalue().encode("utf-8")
            return list(output.items())
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        _fail("wheel staging wheel is invalid", error)


def _manifest(files: Iterable[WindowsPythonRuntimeFile]) -> dict[str, WindowsPythonRuntimeFile]:
    result: dict[str, WindowsPythonRuntimeFile] = {}; folded: set[str] = set()
    for item in files:
        if not isinstance(item, WindowsPythonRuntimeFile) or item.relative_path in result:
            _fail("wheel staging runtime manifest is invalid")
        _parts(item.relative_path)
        if (item.relative_path.casefold() in folded or isinstance(item.size_bytes, bool)
                or not isinstance(item.size_bytes, int) or item.size_bytes < 1
                or re.fullmatch(r"[0-9a-f]{64}", item.sha256) is None):
            _fail("wheel staging runtime manifest is invalid")
        folded.add(item.relative_path.casefold()); result[item.relative_path] = item
    if not result:
        _fail("wheel staging runtime manifest is invalid")
    return result


def _validate_runtime_layout(manifest: dict[str, WindowsPythonRuntimeFile], root: Path,
                             target: WindowsWheelTarget) -> None:
    """Retain the embeddable runtime's isolation contract at the handoff."""
    major, minor, _micro = target.python_full_version.split(".")
    pth = f"python{major}{minor}._pth"
    required = {"python.exe", "pythonw.exe", f"python{major}{minor}.dll", "python3.dll",
                f"python{major}{minor}.zip", pth, "LICENSE.txt", "vcruntime140.dll", "vcruntime140_1.dll"}
    if not required <= set(manifest):
        _fail("wheel staging runtime manifest is invalid")
    data = _read_regular(root / pth, _MAX_MEMBER_BYTES,
        expected_size=manifest[pth].size_bytes, expected_hash=manifest[pth].sha256)
    try:
        active = [line.strip() for line in data.decode("utf-8").splitlines()
                  if line.strip() and not line.lstrip().startswith("#")]
    except UnicodeDecodeError as error:
        _fail("wheel staging runtime path configuration is invalid", error)
    if active != [f"python{major}{minor}.zip", "."]:
        _fail("wheel staging runtime path configuration is not isolated")
    for relative in required:
        if relative.casefold().endswith((".exe", ".dll")):
            payload = _read_regular(root / relative, _MAX_MEMBER_BYTES,
                expected_size=manifest[relative].size_bytes, expected_hash=manifest[relative].sha256)
            if len(payload) < 64 or payload[:2] != b"MZ":
                _fail("wheel staging runtime architecture is invalid")
            offset = int.from_bytes(payload[0x3c:0x40], "little")
            if offset > len(payload) - 6 or payload[offset:offset + 4] != b"PE\0\0" or int.from_bytes(payload[offset + 4:offset + 6], "little") != _MACHINE[target.architecture]:
                _fail("wheel staging runtime architecture is invalid")


def _runtime_files(root: Path) -> dict[str, Path]:
    _ordinary_ancestors(root.parent)
    try:
        root_stat = root.lstat()
    except OSError as error:
        _fail("wheel staging runtime is unavailable", error)
    if not stat.S_ISDIR(root_stat.st_mode) or _unsafe(root_stat):
        _fail("wheel staging runtime is unavailable")
    result: dict[str, Path] = {}; folded: set[str] = set()
    for directory, directories, names in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        for name in [*directories, *names]:
            candidate = current / name
            try: value = candidate.lstat()
            except OSError as error: _fail("wheel staging runtime is unavailable", error)
            if _unsafe(value): _fail("wheel staging runtime is unsafe")
        for name in names:
            candidate = current / name; relative = candidate.relative_to(root).as_posix()
            _parts(relative)
            if not stat.S_ISREG(candidate.lstat().st_mode) or relative.casefold() in folded:
                _fail("wheel staging runtime is unsafe")
            folded.add(relative.casefold()); result[relative] = candidate
    return result


def _runtime_directories(root: Path) -> set[str]:
    """Return existing directories so a wheel cannot replace one with a file."""
    result: set[str] = set()
    for directory, directories, _names in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        for name in directories:
            relative = (current / name).relative_to(root).as_posix()
            _parts(relative)
            result.add(relative.casefold())
    return result


def _cleanup_owned(path: Path, parent: Path) -> bool:
    try:
        if not path.exists(): return True
        if path.parent != parent or _unsafe(path.lstat()): return False
        for directory, directories, names in os.walk(path, topdown=True, followlinks=False):
            if any(_unsafe((Path(directory) / name).lstat()) for name in [*directories, *names]): return False
        shutil.rmtree(path)
        return not path.exists()
    except OSError:
        return False


def stage_windows_wheels(*, runtime_root: Path, runtime_files: tuple[WindowsPythonRuntimeFile, ...],
                         artifacts: tuple[WindowsWheelArtifact, ...], wheel_files: dict[str, Path],
                         target: WindowsWheelTarget, destination: Path) -> StagedWindowsWheels:
    """Create a fresh runtime with only manifest-bound runtime and wheel bytes."""
    root, output = _absolute(Path(runtime_root), purpose="runtime"), _absolute(Path(destination), purpose="destination")
    if output.exists() or output.is_symlink() or root == output or _within(root, output) or _within(output, root):
        _fail("wheel staging destination is unavailable")
    _ordinary_ancestors(output.parent)
    manifest = _manifest(runtime_files); actual = _runtime_files(root)
    if set(actual) != set(manifest): _fail("wheel staging runtime does not match manifest")
    _validate_runtime_layout(manifest, root, target)
    if set(wheel_files) != {item.filename for item in artifacts} or len({item.filename for item in artifacts}) != len(artifacts):
        _fail("wheel staging artifacts are incomplete")
    temporary = Path(tempfile.mkdtemp(prefix=".wheel-stage-incomplete-", dir=output.parent))
    occupied = {item.casefold() for item in manifest}
    runtime_directories = _runtime_directories(root)
    try:
        for relative, expected in manifest.items():
            payload = _read_regular(actual[relative], _MAX_MEMBER_BYTES, expected_size=expected.size_bytes, expected_hash=expected.sha256)
            target_file = temporary.joinpath(*_parts(relative)); target_file.parent.mkdir(parents=True, exist_ok=True)
            with target_file.open("xb") as stream: stream.write(payload)
        for artifact in artifacts:
            wheel_path = Path(wheel_files[artifact.filename])
            if wheel_path.name != artifact.filename:
                _fail("wheel staging input does not match inventory")
            data = _read_regular(wheel_path, _MAX_WHEEL_BYTES, expected_size=artifact.size_bytes, expected_hash=artifact.sha256)
            for relative, payload in _wheel_contents(data, artifact, target):
                _parts(relative); key = relative.casefold()
                if (key in occupied or key in runtime_directories
                        or any(value.startswith(key + "/") for value in occupied | runtime_directories)):
                    _fail("wheel staging files collide")
                target_file = temporary.joinpath(*_parts(relative))
                if target_file.exists() or target_file.is_symlink(): _fail("wheel staging files collide")
                target_file.parent.mkdir(parents=True, exist_ok=True)
                with target_file.open("xb") as stream: stream.write(payload)
                occupied.add(key)
        files = []
        for relative, candidate in _runtime_files(temporary).items():
            payload = _read_regular(candidate, _MAX_MEMBER_BYTES, allow_empty=True)
            files.append((relative, len(payload), hashlib.sha256(payload).hexdigest()))
        if output.exists() or output.is_symlink(): _fail("wheel staging destination is unavailable")
        os.rename(temporary, output)
        return StagedWindowsWheels(tuple(sorted(files, key=lambda value: value[0].casefold())))
    except Exception as error:
        if not _cleanup_owned(temporary, output.parent):
            _fail("wheel staging cleanup unconfirmed", error)
        raise


__all__ = ("StagedWindowsWheels", "WindowsWheelStagingError", "stage_windows_wheels")
