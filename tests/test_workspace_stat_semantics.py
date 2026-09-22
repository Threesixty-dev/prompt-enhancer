"""Synthetic path/descriptor timestamp semantics without provider or model data."""

from __future__ import annotations

import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from prompt_enhancer.application.local_agent_limits import LocalAgentError
from prompt_enhancer.application.local_workspace_io import WorkspaceIO
from prompt_enhancer.application.runtime_cancellation import RuntimeCooperativeStop


def _fixture(tmp_path, monkeypatch, *, change=None, birthtime=True, descriptor_ctime=200):
    target = tmp_path / "example.txt"
    payload = b"synthetic bounded content"
    target.write_bytes(payload)
    workspace = WorkspaceIO(tmp_path)
    real_lstat = Path.lstat
    real_fstat = os.fstat
    actual = target.lstat()
    common = {
        name: getattr(actual, name)
        for name in ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size")
    }
    common.update(st_file_attributes=0, st_mtime_ns=300)
    if birthtime:
        common["st_birthtime_ns"] = 100
    snapshots = {
        "path_before": dict(common, st_ctime_ns=100),
        "descriptor_before": dict(common, st_ctime_ns=descriptor_ctime),
        "descriptor_after": dict(common, st_ctime_ns=descriptor_ctime),
        "path_after": dict(common, st_ctime_ns=100),
    }
    if change is not None:
        phase, field, value = change
        snapshots[phase][field] = value
    path_calls = iter(("path_before", "path_after"))
    descriptor_calls = iter(("descriptor_before", "descriptor_after"))

    def path_metadata(path):
        if path == target:
            return SimpleNamespace(**snapshots[next(path_calls)])
        return real_lstat(path)

    def descriptor_metadata(descriptor):
        observed = real_fstat(descriptor)
        if (observed.st_dev, observed.st_ino) == (actual.st_dev, actual.st_ino):
            return SimpleNamespace(**snapshots[next(descriptor_calls)])
        return observed

    # Use the admitted real workspace and no-follow open implementation. Only
    # the leaf stat results are synthetic; directory identities stay real.
    monkeypatch.setattr(WorkspaceIO, "_stat_entry", staticmethod(lambda path, parent: path_metadata(path)))
    monkeypatch.setattr(os, "fstat", descriptor_metadata)
    return workspace, target, payload


def test_workspace_read_accepts_cross_api_ctime_difference_with_birthtime(tmp_path, monkeypatch):
    workspace, target, payload = _fixture(tmp_path, monkeypatch)
    result = workspace.read(target, limit=100)
    assert result.payload == payload and result.truncated is False
    # Returned metadata retains descriptor semantics, not a rewritten revision.
    assert result.metadata.st_ctime_ns == 200


@pytest.mark.parametrize(("phase", "field", "value"), [
    ("descriptor_before", "st_ino", 0), ("path_before", "st_ino", 0),
    ("descriptor_before", "st_ino", 123), ("path_after", "st_ino", 123),
    ("descriptor_after", "st_dev", 123), ("path_after", "st_dev", 123),
    ("descriptor_before", "st_birthtime_ns", 101),
    ("descriptor_after", "st_birthtime_ns", 101), ("path_after", "st_birthtime_ns", 101),
    ("descriptor_before", "st_mtime_ns", 301),
    ("descriptor_after", "st_mtime_ns", 301), ("path_after", "st_mtime_ns", 301),
    ("descriptor_after", "st_ctime_ns", 201), ("path_after", "st_ctime_ns", 101),
    ("descriptor_after", "st_size", 1), ("path_after", "st_size", 1),
    ("descriptor_after", "st_nlink", 2), ("path_after", "st_nlink", 2),
    ("descriptor_before", "st_file_attributes", 0x400),
    ("descriptor_after", "st_file_attributes", 0x400), ("path_after", "st_file_attributes", 0x400),
    ("descriptor_after", "st_mode", stat.S_IFLNK | 0o600),
    ("path_after", "st_mode", stat.S_IFDIR | 0o600),
])
def test_workspace_read_rejects_replacement_mutation_and_reparse(tmp_path, monkeypatch, phase, field, value):
    workspace, target, _ = _fixture(tmp_path, monkeypatch, change=(phase, field, value))
    with pytest.raises(LocalAgentError):
        workspace.read(target, limit=100)


@pytest.mark.parametrize("descriptor_ctime", [100, 200])
def test_workspace_read_without_birthtime_keeps_cross_api_ctime_guard(tmp_path, monkeypatch, descriptor_ctime):
    workspace, target, payload = _fixture(tmp_path, monkeypatch, birthtime=False, descriptor_ctime=descriptor_ctime)
    if descriptor_ctime == 100:
        assert workspace.read(target, limit=100).payload == payload
    else:
        with pytest.raises(LocalAgentError, match="workspace_file_changed"):
            workspace.read(target, limit=100)


def test_workspace_read_prefix_remains_bounded_with_timestamp_mismatch(tmp_path, monkeypatch):
    workspace, target, payload = _fixture(tmp_path, monkeypatch)
    consumed = []
    result = workspace.read(target, limit=5, allow_prefix=True, consume=consumed.append)
    assert result.payload == payload[:5] and result.truncated is True
    assert sum(consumed) == 6


def test_workspace_read_limit_refuses_before_reading(tmp_path, monkeypatch):
    workspace, target, _ = _fixture(tmp_path, monkeypatch)
    consumed = []
    with pytest.raises(LocalAgentError, match="workspace_file_too_large"):
        workspace.read(target, limit=5, consume=consumed.append)
    assert consumed == []


def test_workspace_read_cancellation_still_closes_leaf_descriptor(tmp_path, monkeypatch):
    workspace, target, _ = _fixture(tmp_path, monkeypatch)
    closed = []
    original_close = os.close
    original_read = os.read
    read_completed = False
    read_descriptors = []

    def observed_read(descriptor, size):
        nonlocal read_completed
        result = original_read(descriptor, size)
        read_descriptors.append(descriptor)
        read_completed = True
        return result

    def check():
        if read_completed:
            raise RuntimeCooperativeStop("synthetic_cancelled")

    def close(descriptor):
        closed.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(os, "read", observed_read)
    monkeypatch.setattr(os, "close", close)
    with pytest.raises(RuntimeCooperativeStop):
        workspace.read(target, limit=100, check=check)
    assert read_completed and read_descriptors
    assert all(descriptor in closed for descriptor in read_descriptors)
