from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from prompt_enhancer.infrastructure.build_staging import (
    WindowsReleaseStagePlan, WindowsReleaseStagingError, stage_windows_release,
)
import prompt_enhancer.infrastructure.build_staging as staging_module

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows staging handoff requires Windows no-clobber semantics")


def _digest(value: bytes) -> str: return hashlib.sha256(value).hexdigest()


def _plan(*files: tuple[str, str, bytes]) -> WindowsReleaseStagePlan:
    return WindowsReleaseStagePlan.model_validate({
        "git_revision": "a" * 40,
        "tool_versions": [{"name": "python", "version": "3.11"}],
        "lockfile_hashes": [{"name": "uv.lock", "sha256": "b" * 64}],
        "files": [{"source_relative_path": source, "destination_relative_path": destination,
                   "size_bytes": len(payload), "sha256": _digest(payload)}
                  for source, destination, payload in files],
    })


def test_stage_copies_only_enumerated_hash_bound_files_and_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir()
    (source / "public.txt").write_bytes(b"synthetic public release item")
    (source / "SECRET_CANARY.txt").write_bytes(b"synthetic secret canary")
    plan = _plan(("public.txt", "app/public.txt", b"synthetic public release item"))
    first = stage_windows_release(plan=plan, source_root=source, destination=tmp_path / "one")
    second = stage_windows_release(plan=plan, source_root=source, destination=tmp_path / "two")
    assert (tmp_path / "one" / "app" / "public.txt").read_bytes() == b"synthetic public release item"
    assert not (tmp_path / "one" / "SECRET_CANARY.txt").exists()
    assert first == second and first.distributable is False


def test_stage_rejects_tampering_missing_collisions_and_preserves_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir(); payload = b"synthetic item"
    (source / "item.txt").write_bytes(payload)
    plan = _plan(("item.txt", "item.txt", payload))
    (source / "item.txt").write_bytes(b"synthetic tampered item")
    with pytest.raises(WindowsReleaseStagingError):
        stage_windows_release(plan=plan, source_root=source, destination=tmp_path / "tampered")
    existing = tmp_path / "existing"; existing.mkdir(); (existing / "keep.txt").write_bytes(b"keep")
    with pytest.raises(WindowsReleaseStagingError):
        stage_windows_release(plan=plan, source_root=source, destination=existing)
    assert (existing / "keep.txt").read_bytes() == b"keep"
    with pytest.raises(Exception):
        _plan(("item.txt", "Folder/item.txt", payload), ("item.txt", "folder/ITEM.txt", payload))
    missing = _plan(("missing.txt", "missing.txt", payload))
    with pytest.raises(WindowsReleaseStagingError):
        stage_windows_release(plan=missing, source_root=source, destination=tmp_path / "missing")


def test_stage_rejects_source_destination_overlap_and_windows_ambiguous_paths(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir(); payload = b"synthetic item"
    (source / "item.txt").write_bytes(payload); plan = _plan(("item.txt", "item.txt", payload))
    with pytest.raises(WindowsReleaseStagingError):
        stage_windows_release(plan=plan, source_root=source, destination=source / "out")
    with pytest.raises(Exception):
        _plan(("item.txt", "NUL.txt", payload))
    with pytest.raises(Exception):
        WindowsReleaseStagePlan.model_validate({
            "git_revision": "a" * 40, "tool_versions": [], "lockfile_hashes": [],
            "files": [{"source_relative_path": "item.txt", "destination_relative_path": "item.txt", "size_bytes": True, "sha256": "a" * 64}],
        })


def test_stage_rejects_injected_extra_file_and_late_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"; source.mkdir(); payload = b"synthetic item"
    (source / "item.txt").write_bytes(payload); plan = _plan(("item.txt", "item.txt", payload))
    original_manifest = staging_module.build_manifest
    def inject_extra(root: Path, **kwargs: object):
        (root / "unexpected.txt").write_bytes(b"synthetic unexpected")
        return original_manifest(root, **kwargs)
    monkeypatch.setattr(staging_module, "build_manifest", inject_extra)
    with pytest.raises(WindowsReleaseStagingError):
        stage_windows_release(plan=plan, source_root=source, destination=tmp_path / "output")
    assert not (tmp_path / "output").exists()
    monkeypatch.setattr(staging_module, "build_manifest", original_manifest)
    original_rename = staging_module.os.rename
    def create_late_output(source_path: object, destination_path: object) -> None:
        Path(destination_path).mkdir()
        original_rename(source_path, destination_path)
    monkeypatch.setattr(staging_module.os, "rename", create_late_output)
    with pytest.raises(Exception):
        stage_windows_release(plan=plan, source_root=source, destination=tmp_path / "late")
    assert (tmp_path / "late").is_dir()
