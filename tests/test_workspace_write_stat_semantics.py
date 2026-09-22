"""Windows write/recovery checks under synthetic path/fd ctime differences."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest

from prompt_enhancer.application.local_agent_workspace import WorkspaceTools
from prompt_enhancer.application.local_agent_limits import LocalAgentError


@pytest.fixture
def timestamp_mismatch(monkeypatch):
    if sys.platform != "win32":
        pytest.skip("real Windows handle workflow")
    original = os.fstat
    original_lstat = Path.lstat
    observed = []

    def fields_for(value):
        fields = {name: getattr(value, name) for name in dir(value) if name.startswith("st_")}
        fields["st_birthtime_ns"] = getattr(value, "st_birthtime_ns", value.st_ctime_ns)
        return fields

    def lstat(path):
        value = original_lstat(path)
        return SimpleNamespace(**fields_for(value)) if stat.S_ISREG(value.st_mode) else value

    def fstat(descriptor):
        value = original(descriptor)
        if not stat.S_ISREG(value.st_mode):
            return value
        fields = fields_for(value)
        fields["st_ctime_ns"] += 1
        observed.append(fields["st_ctime_ns"] != fields["st_birthtime_ns"])
        return SimpleNamespace(**fields)

    monkeypatch.setattr(os, "fstat", fstat)
    monkeypatch.setattr(Path, "lstat", lstat)
    return observed


@pytest.mark.parametrize("existing", [False, True])
def test_reviewed_write_succeeds_with_cross_api_ctime_difference(tmp_path, timestamp_mismatch, existing):
    path = tmp_path / "example.txt"
    if existing:
        path.write_bytes(b"original synthetic\n")
    tools = WorkspaceTools(tmp_path)
    prepared = tools.prepare_write(path.name, "reviewed synthetic\n")
    outcome = tools.apply_prepared_write(prepared)
    assert timestamp_mismatch and all(timestamp_mismatch) and outcome.ok
    assert outcome.code is None
    assert path.read_bytes() == b"reviewed synthetic\n"
    assert not list(tmp_path.glob(".prompt-enhancer-*.tmp"))


def test_move_succeeds_with_cross_api_ctime_difference(tmp_path, timestamp_mismatch):
    source = tmp_path / "source.txt"
    source.write_bytes(b"synthetic move\n")
    tools = WorkspaceTools(tmp_path)
    prepared = tools.prepare_move(source.name, "target.txt")
    outcome = tools.apply_prepared_move(prepared)
    assert outcome.state == "verified"
    assert not source.exists()
    assert (tmp_path / "target.txt").read_bytes() == b"synthetic move\n"


def test_transaction_created_file_rollback_keeps_exact_identity_guard(tmp_path, timestamp_mismatch):
    tools = WorkspaceTools(tmp_path)
    prepared = tools.prepare_write("created.txt", "synthetic created\n")
    assert tools.apply_prepared_write(prepared).ok
    path = tmp_path / "created.txt"
    identity = tools._identity(path.lstat())
    assert tools._remove_created_transaction_write(prepared, identity) is True
    assert not path.exists()


def test_transaction_created_file_rollback_refuses_replacement(tmp_path, timestamp_mismatch):
    tools = WorkspaceTools(tmp_path)
    prepared = tools.prepare_write("created.txt", "synthetic created\n")
    assert tools.apply_prepared_write(prepared).ok
    path = tmp_path / "created.txt"
    identity = tools._identity(path.lstat())
    replacement = tmp_path / "replacement.txt"
    replacement.write_bytes(b"synthetic external\n")
    replacement.replace(path)
    assert tools._remove_created_transaction_write(prepared, identity) is False
    assert path.read_bytes() == b"synthetic external\n"


def test_changed_reviewed_file_is_rejected_with_timestamp_mismatch(tmp_path, timestamp_mismatch):
    path = tmp_path / "example.txt"
    path.write_bytes(b"original synthetic\n")
    tools = WorkspaceTools(tmp_path)
    prepared = tools.prepare_write(path.name, "reviewed synthetic\n")
    path.write_bytes(b"external synthetic\n")
    outcome = tools.apply_prepared_write(prepared)
    assert not outcome.ok and outcome.code == "workspace_revision_changed"
    assert path.read_bytes() == b"external synthetic\n"


def test_unreviewed_publication_is_restored_under_timestamp_mismatch(tmp_path, monkeypatch, timestamp_mismatch):
    path = tmp_path / "example.txt"
    path.write_bytes(b"original synthetic\n")
    tools = WorkspaceTools(tmp_path)
    prepared = tools.prepare_write(path.name, "reviewed synthetic\n")
    original = tools._replace_windows_file
    replacements = []

    def tamper_first(target, replacement, backup):
        if not replacements:
            Path(replacement).write_bytes(b"unreviewed synthetic\n")
        replacements.append(True)
        return original(target, replacement, backup)

    monkeypatch.setattr(tools, "_replace_windows_file", tamper_first)
    outcome = tools.apply_prepared_write(prepared)
    assert len(replacements) == 2
    assert not outcome.ok and outcome.code == "workspace_revision_changed"
    assert path.read_bytes() == b"original synthetic\n"
    assert not list(tmp_path.glob(".prompt-enhancer-*.tmp"))


def test_refused_replace_is_verified_unchanged_under_timestamp_mismatch(tmp_path, monkeypatch, timestamp_mismatch):
    path = tmp_path / "example.txt"
    path.write_bytes(b"original synthetic\n")
    tools = WorkspaceTools(tmp_path)
    prepared = tools.prepare_write(path.name, "reviewed synthetic\n")

    def refuse(*_):
        raise OSError("synthetic replacement refused")

    monkeypatch.setattr(tools, "_replace_windows_file", refuse)
    outcome = tools.apply_prepared_write(prepared)
    assert not outcome.ok and outcome.code == "workspace_write_failed"
    assert path.read_bytes() == b"original synthetic\n"
    assert not list(tmp_path.glob(".prompt-enhancer-*.tmp"))


def test_failed_publication_read_restores_original_under_timestamp_mismatch(tmp_path, monkeypatch, timestamp_mismatch):
    path = tmp_path / "example.txt"
    path.write_bytes(b"original synthetic\n")
    tools = WorkspaceTools(tmp_path)
    prepared = tools.prepare_write(path.name, "reviewed synthetic\n")
    original_replace = tools._replace_windows_file
    original_open = tools._open_windows_target
    replacements = []
    failures = []

    def replace(*args):
        original_replace(*args)
        replacements.append(True)

    def open_target(target):
        if target == path and len(replacements) == 1 and not failures:
            failures.append(True)
            raise OSError("synthetic published read refused")
        return original_open(target)

    monkeypatch.setattr(tools, "_replace_windows_file", replace)
    monkeypatch.setattr(tools, "_open_windows_target", open_target)
    outcome = tools.apply_prepared_write(prepared)
    assert failures and len(replacements) == 2
    assert not outcome.ok and outcome.code == "workspace_write_failed"
    assert path.read_bytes() == b"original synthetic\n"
    assert not list(tmp_path.glob(".prompt-enhancer-*.tmp"))


def test_same_descriptor_ctime_mutation_still_rejected(tmp_path, monkeypatch, timestamp_mismatch):
    path = tmp_path / "example.txt"
    path.write_bytes(b"synthetic\n")
    tools = WorkspaceTools(tmp_path)
    original = os.fstat
    calls = []

    def fstat(descriptor):
        result = original(descriptor)
        calls.append(True)
        if len(calls) == 2:
            result.st_ctime_ns += 1
        return result

    descriptor = tools._open_windows_target(path)
    monkeypatch.setattr(os, "fstat", fstat)
    try:
        with pytest.raises(LocalAgentError, match="workspace_file_changed"):
            tools._read_open_descriptor(descriptor)
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(("field", "value"), [
    ("st_ino", 0), ("st_ino", 23), ("st_dev", 12),
    ("st_size", 2), ("st_nlink", 2), ("st_mtime_ns", 301),
    ("st_birthtime_ns", 101), ("st_mode", stat.S_IFLNK | 0o600),
    ("st_file_attributes", 0x400),
])
def test_cross_api_predicate_refuses_identity_metadata_and_reparse_changes(field, value):
    fields = dict(st_dev=11, st_ino=22, st_size=1, st_nlink=1,
                  st_mode=stat.S_IFREG | 0o600, st_file_attributes=0,
                  st_mtime_ns=300, st_birthtime_ns=100)
    path = SimpleNamespace(**fields, st_ctime_ns=100)
    descriptor = SimpleNamespace(**{**fields, field: value}, st_ctime_ns=200)
    assert WorkspaceTools._path_matches_descriptor(path, descriptor) is False
