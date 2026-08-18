"""Deterministic, public manifest generation for a synthetic staged tree."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Literal

from pydantic import Field, field_validator

from ...domain import StrictModel


BUILD_MANIFEST_SCHEMA_VERSION = 1
BUILD_MANIFEST_GENERATOR_VERSION = "deterministic-public-build-manifest-v1"
MAX_STAGED_FILES = 50_000
MAX_STAGED_ENTRIES = 100_000
MAX_STAGED_FILE_BYTES = 4 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
NONDETERMINISTIC_EXCLUSIONS: tuple[tuple[str, str], ...] = (
    ("filesystem_mtime", "timestamps are not artifact identity"),
    ("absolute_path", "host paths are private and non-reproducible"),
    ("hostname", "host identity is private and non-reproducible"),
    ("environment", "ambient variables are private and non-reproducible"),
)


class PublicToolVersion(StrictModel):
    name: str = Field(pattern=r"^[a-z0-9_.-]{1,64}$")
    version: str = Field(pattern=r"^[A-Za-z0-9_.+\-]{1,96}$")


class NamedDigest(StrictModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,96}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class StagedFile(StrictModel):
    relative_path: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(ge=0, le=MAX_STAGED_FILE_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        if "\\" in value or "\x00" in value:
            raise ValueError("build path must use portable separators")
        parsed = PurePosixPath(value)
        if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
            raise ValueError("build path must be a normalized relative path")
        return value


class BuildManifest(StrictModel):
    schema_version: Literal[1] = BUILD_MANIFEST_SCHEMA_VERSION
    generator_version: Literal["deterministic-public-build-manifest-v1"] = (
        BUILD_MANIFEST_GENERATOR_VERSION
    )
    git_revision: str = Field(pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
    tool_versions: tuple[PublicToolVersion, ...]
    lockfile_hashes: tuple[NamedDigest, ...]
    files: tuple[StagedFile, ...]
    nondeterministic_exclusions: tuple[tuple[str, str], ...] = NONDETERMINISTIC_EXCLUSIONS
    distributable: Literal[False] = False


class DifferenceKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"


class ManifestDifference(StrictModel):
    relative_path: str
    kind: DifferenceKind
    first_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    second_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ManifestComparison(StrictModel):
    identical: bool
    differences: tuple[ManifestDifference, ...]


def canonical_json(value: StrictModel | Mapping[str, Any]) -> bytes:
    payload = value.model_dump(mode="json") if isinstance(value, StrictModel) else dict(value)
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii") + b"\n"
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError("canonical manifest exceeded the public size bound")
    return encoded


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            if size > MAX_STAGED_FILE_BYTES:
                raise ValueError("staged file exceeded the build size bound")
            digest.update(chunk)
    return digest.hexdigest(), size


def _ordinary_staged_files(staging_root: Path) -> list[tuple[Path, str, os.stat_result]]:
    """Walk without descending through symlinks, junctions, or reparse points."""

    discovered: list[tuple[Path, str, os.stat_result]] = []
    pending: list[tuple[Path, PurePosixPath]] = [(staging_root, PurePosixPath())]
    entry_count = 0
    while pending:
        directory, relative_directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name, reverse=True)
        except OSError as error:
            raise ValueError("staging directory could not be inspected") from error
        for entry in entries:
            entry_count += 1
            if entry_count > MAX_STAGED_ENTRIES:
                raise ValueError("staging tree exceeded the entry-count bound")
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise ValueError("staging entry could not be inspected") from error
            if stat.S_ISLNK(metadata.st_mode) or bool(
                getattr(metadata, "st_file_attributes", 0) & 0x400
            ):
                raise ValueError("staging tree contains a link or reparse point")
            relative = relative_directory / entry.name
            candidate = Path(entry.path)
            if stat.S_ISDIR(metadata.st_mode):
                pending.append((candidate, relative))
            elif stat.S_ISREG(metadata.st_mode):
                discovered.append((candidate, relative.as_posix(), metadata))
                if len(discovered) > MAX_STAGED_FILES:
                    raise ValueError("staging tree exceeded the file-count bound")
            else:
                raise ValueError("staging tree contains a non-regular file")
    return sorted(discovered, key=lambda item: item[1])


def build_manifest(
    staging_root: Path,
    *,
    git_revision: str,
    tool_versions: Mapping[str, str],
    lockfile_hashes: Mapping[str, str],
) -> BuildManifest:
    """Hash ordinary files under a synthetic/public staging root.

    Symlinks, reparse points, special files, and changing files are rejected.
    The output intentionally contains neither timestamps nor absolute paths.
    """

    try:
        root_metadata = staging_root.lstat()
    except OSError as error:
        raise ValueError("staging root could not be inspected") from error
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or bool(getattr(root_metadata, "st_file_attributes", 0) & 0x400)
    ):
        raise ValueError("staging root is not an ordinary directory")
    files: list[StagedFile] = []
    for candidate, relative, metadata in _ordinary_staged_files(staging_root):
        digest, size = _sha256_file(candidate)
        after = candidate.stat()
        if (
            after.st_size != metadata.st_size
            or after.st_mtime_ns != metadata.st_mtime_ns
            or after.st_ctime_ns != metadata.st_ctime_ns
        ):
            raise ValueError("staged file changed while it was hashed")
        files.append(StagedFile(relative_path=relative, size_bytes=size, sha256=digest))
    manifest = BuildManifest(
        git_revision=git_revision,
        tool_versions=tuple(
            PublicToolVersion(name=name, version=version)
            for name, version in sorted(tool_versions.items())
        ),
        lockfile_hashes=tuple(
            NamedDigest(name=name, sha256=digest)
            for name, digest in sorted(lockfile_hashes.items())
        ),
        files=tuple(files),
    )
    canonical_json(manifest)
    return manifest


def compare_manifests(first: BuildManifest, second: BuildManifest) -> ManifestComparison:
    first_files = {entry.relative_path: entry for entry in first.files}
    second_files = {entry.relative_path: entry for entry in second.files}
    differences: list[ManifestDifference] = []
    for path in sorted(first_files.keys() | second_files.keys()):
        left = first_files.get(path)
        right = second_files.get(path)
        if left is None:
            differences.append(ManifestDifference(relative_path=path, kind=DifferenceKind.ADDED, second_sha256=right.sha256 if right else None))
        elif right is None:
            differences.append(ManifestDifference(relative_path=path, kind=DifferenceKind.REMOVED, first_sha256=left.sha256))
        elif left != right:
            differences.append(ManifestDifference(relative_path=path, kind=DifferenceKind.CHANGED, first_sha256=left.sha256, second_sha256=right.sha256))
    metadata_equal = (
        first.git_revision == second.git_revision
        and first.tool_versions == second.tool_versions
        and first.lockfile_hashes == second.lockfile_hashes
        and first.nondeterministic_exclusions == second.nondeterministic_exclusions
    )
    if not metadata_equal and not differences:
        differences.append(
            ManifestDifference(
                relative_path=".build-metadata",
                kind=DifferenceKind.CHANGED,
                first_sha256=hashlib.sha256(canonical_json(first)).hexdigest(),
                second_sha256=hashlib.sha256(canonical_json(second)).hexdigest(),
            )
        )
    return ManifestComparison(identical=not differences, differences=tuple(differences))
