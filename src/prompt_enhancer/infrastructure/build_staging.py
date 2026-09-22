"""Offline explicit-file staging for a non-distributable Windows assembly."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PureWindowsPath
import stat
import tempfile
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ..application.build_evidence.manifest import (
    BuildManifest, MAX_STAGED_FILES, MAX_STAGED_FILE_BYTES, NamedDigest,
    PublicToolVersion, _validate_staged_relative_path, build_manifest,
)
from ..domain import StrictModel
from ..application.paths.policy import classify_windows_path_text

_MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
_REPARSE = 0x400


class WindowsReleaseStagingError(RuntimeError): pass


class WindowsReleaseFile(StrictModel):
    source_relative_path: str = Field(min_length=1, max_length=512, strict=True)
    destination_relative_path: str = Field(min_length=1, max_length=512, strict=True)
    size_bytes: int = Field(ge=0, le=MAX_STAGED_FILE_BYTES, strict=True)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    _source = field_validator("source_relative_path")(_validate_staged_relative_path)
    _destination = field_validator("destination_relative_path")(_validate_staged_relative_path)


class WindowsReleaseStagePlan(StrictModel):
    """Public plan: only revision, public tools/locks, and enumerated files."""
    git_revision: str = Field(pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
    tool_versions: tuple[PublicToolVersion, ...] = Field(max_length=64)
    lockfile_hashes: tuple[NamedDigest, ...] = Field(max_length=256)
    files: tuple[WindowsReleaseFile, ...] = Field(min_length=1, max_length=MAX_STAGED_FILES)
    schema_version: Literal[1] = 1
    distributable: Literal[False] = False

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_integer(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("stage plan schema version is invalid")
        return value

    @field_validator("distributable", mode="before")
    @classmethod
    def _not_distributable_boolean(cls, value: object) -> object:
        if not isinstance(value, bool):
            raise ValueError("stage plan distributable flag is invalid")
        return value

    @model_validator(mode="after")
    def _unique_tree(self) -> "WindowsReleaseStagePlan":
        destinations = [tuple(part.casefold() for part in item.destination_relative_path.split("/")) for item in self.files]
        if len(destinations) != len(set(destinations)):
            raise ValueError("stage plan destinations collide")
        for first, second in zip(sorted(destinations), sorted(destinations)[1:]):
            if len(first) < len(second) and second[:len(first)] == first:
                raise ValueError("stage plan has a file-directory collision")
        if sum(item.size_bytes for item in self.files) > _MAX_TOTAL_BYTES:
            raise ValueError("stage plan exceeds total size bound")
        if len({item.name for item in self.tool_versions}) != len(self.tool_versions):
            raise ValueError("stage plan tool versions collide")
        if len({item.name for item in self.lockfile_hashes}) != len(self.lockfile_hashes):
            raise ValueError("stage plan lockfile hashes collide")
        return self


def _ordinary(path: Path, *, directory: bool | None = None) -> os.stat_result:
    try: metadata = path.lstat()
    except OSError as error: raise WindowsReleaseStagingError("release staging path is unavailable") from error
    is_reparse = stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE)
    if is_reparse or (directory is True and not stat.S_ISDIR(metadata.st_mode)) or (directory is False and not stat.S_ISREG(metadata.st_mode)):
        raise WindowsReleaseStagingError("release staging path is unsafe")
    return metadata


def _safe_absolute(path: Path) -> Path:
    raw = os.fspath(path)
    if ".." in PureWindowsPath(raw).parts or classify_windows_path_text(raw) is not None:
        raise WindowsReleaseStagingError("release staging path is unsafe")
    return Path(os.path.abspath(raw))


def _verify_ancestors(path: Path) -> None:
    current = path
    while True:
        _ordinary(current, directory=True)
        if current.parent == current: return
        current = current.parent


def _within(root: Path, candidate: Path) -> bool:
    try: candidate.relative_to(root); return True
    except ValueError: return False


def _snapshot(metadata: os.stat_result) -> tuple:
    # Reading a file or enumerating a directory may update access time. Compare
    # same-API identity and mutation metadata, not our own access side effect.
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_nlink,
            metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns,
            getattr(metadata, "st_birthtime_ns", None),
            getattr(metadata, "st_file_attributes", 0))


def _hash_checked(path: Path, expected_size: int, expected_digest: str) -> None:
    before = _ordinary(path, directory=False)
    if before.st_size != expected_size or before.st_nlink != 1:
        raise WindowsReleaseStagingError("release staging source does not match plan")
    digest = hashlib.sha256(); size = 0
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                if size > expected_size or size > MAX_STAGED_FILE_BYTES:
                    raise WindowsReleaseStagingError("release staging source does not match plan")
                digest.update(chunk)
    except OSError as error: raise WindowsReleaseStagingError("release staging source is unavailable") from error
    after = _ordinary(path, directory=False)
    if size != expected_size or digest.hexdigest() != expected_digest or _snapshot(before) != _snapshot(after):
        raise WindowsReleaseStagingError("release staging source does not match plan")


def stage_windows_release(*, plan: WindowsReleaseStagePlan, source_root: Path,
                          destination: Path) -> BuildManifest:
    """Copy only hash-bound plan entries into a fresh sibling destination."""
    try: checked = WindowsReleaseStagePlan.model_validate(plan.model_dump(mode="python"))
    except Exception as error: raise WindowsReleaseStagingError("release staging plan is invalid") from error
    if os.name != "nt":
        raise WindowsReleaseStagingError("release staging requires Windows")
    source = _safe_absolute(source_root); output = _safe_absolute(destination)
    _verify_ancestors(source)
    parent = output.parent; _verify_ancestors(parent)
    if output.exists() or output.is_symlink() or _within(source, output) or _within(output, source):
        raise WindowsReleaseStagingError("release staging destination is unavailable")
    source_identity = _ordinary(source, directory=True)
    temporary = Path(tempfile.mkdtemp(prefix=".release-stage-incomplete-", dir=parent))
    parent_identity = _ordinary(parent, directory=True)
    try:
        for item in checked.files:
            source_file = source.joinpath(*item.source_relative_path.split("/"))
            destination_file = temporary.joinpath(*item.destination_relative_path.split("/"))
            if not _within(source, source_file) or not _within(temporary, destination_file):
                raise WindowsReleaseStagingError("release staging path is unsafe")
            _verify_ancestors(source_file.parent)
            _hash_checked(source_file, item.size_bytes, item.sha256)
            destination_file.parent.mkdir(parents=True, exist_ok=True)
            _verify_ancestors(destination_file.parent)
            copied = 0
            with source_file.open("rb") as incoming, destination_file.open("xb") as outgoing:
                for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                    copied += len(chunk)
                    if copied > item.size_bytes or copied > MAX_STAGED_FILE_BYTES:
                        raise WindowsReleaseStagingError("release staging source does not match plan")
                    outgoing.write(chunk)
            if copied != item.size_bytes:
                raise WindowsReleaseStagingError("release staging source does not match plan")
            _hash_checked(destination_file, item.size_bytes, item.sha256)
        temporary_identity = _ordinary(temporary, directory=True)
        manifest = build_manifest(temporary, git_revision=checked.git_revision,
            tool_versions={item.name: item.version for item in checked.tool_versions},
            lockfile_hashes={item.name: item.sha256 for item in checked.lockfile_hashes})
        if manifest.distributable is not False:
            raise WindowsReleaseStagingError("release staging manifest is invalid")
        expected = {
            item.destination_relative_path: (item.size_bytes, item.sha256)
            for item in checked.files
        }
        actual = {item.relative_path: (item.size_bytes, item.sha256) for item in manifest.files}
        if actual != expected:
            raise WindowsReleaseStagingError("release staging output differs from plan")
        # ``replace`` would overwrite a destination on Windows.  The explicit
        # precondition plus rename supplies a no-clobber directory handoff.
        _verify_ancestors(parent)
        if _snapshot(_ordinary(temporary, directory=True)) != _snapshot(temporary_identity):
            raise WindowsReleaseStagingError("release staging destination is unavailable")
        if (_snapshot(_ordinary(source, directory=True)) != _snapshot(source_identity)
            or _snapshot(_ordinary(parent, directory=True)) != _snapshot(parent_identity)
            or temporary.parent != parent or output.exists() or output.is_symlink()):
            raise WindowsReleaseStagingError("release staging destination is unavailable")
        os.rename(temporary, output)
        return manifest
    except Exception as error:
        # Keep a uniquely named incomplete sibling rather than recursively
        # deleting a path that could have changed after creation.
        if isinstance(error, WindowsReleaseStagingError): raise
        raise WindowsReleaseStagingError("release staging failed") from error
