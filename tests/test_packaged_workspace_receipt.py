"""Pure process-free tests for the packaged workspace child's closed receipt."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from prompt_enhancer.application import owned_process


@pytest.fixture
def helper(monkeypatch):
    def forbidden_launch(*_args, **_kwargs):
        pytest.fail("receipt parsing must not launch a process")

    monkeypatch.setattr(owned_process, "run_owned_process", forbidden_launch)
    support = Path(__file__).parent / "support"
    monkeypatch.syspath_prepend(str(support))
    spec = importlib.util.spec_from_file_location(
        "synthetic_packaged_workspace_probe", support / "packaged_workspace_probe.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _success():
    return {
        "contract": "packaged-workspace-child.v1", "passed": True,
        "bootstrap_closed": True, "workspace_reads": 5,
        "reviewed_new_writes": 1, "reviewed_existing_writes": 1,
        "reviewed_moves": 1, "stale_reviews_rejected": 1,
        "temporary_files_remaining": 0, "network_attempts": 0,
        "python_version": [3, 13, 0], "cross_api_ctime_diff_observed": True,
        "birthtime_equal": True,
        "error_code": None,
    }


def _encode(receipt) -> bytearray:
    return bytearray(
        ("PACKAGED_WORKSPACE_CHILD=" + json.dumps(receipt, separators=(",", ":")) + "\n").encode()
    )


def test_closed_success_receipt_is_process_free(helper):
    receipt = helper._child_receipt(_encode(_success()))
    assert receipt == _success()
    assert helper._child_passed(receipt) is True


@pytest.mark.parametrize(("key", "value"), [
    ("passed", 1), ("bootstrap_closed", 1), ("workspace_reads", True),
    ("workspace_reads", -1), ("workspace_reads", 1001),
    ("error_code", "unreviewed_error"), ("contract", "unknown.v1"),
    ("python_version", [3, 13]), ("python_version", [3, 13, True]),
    ("cross_api_ctime_diff_observed", 1), ("birthtime_equal", 1),
])
def test_closed_types_ranges_and_enums(helper, key, value):
    assert helper._child_receipt(_encode({**_success(), key: value})) is None


@pytest.mark.parametrize("key", [
    "workspace_reads", "reviewed_new_writes", "reviewed_existing_writes",
    "reviewed_moves", "stale_reviews_rejected", "temporary_files_remaining",
    "network_attempts",
])
def test_inconsistent_counts_never_pass(helper, key):
    receipt = helper._child_receipt(_encode({**_success(), key: 2}))
    assert receipt is not None
    assert helper._child_passed(receipt) is False


def test_failure_receipt_keeps_only_allowlisted_error(helper):
    receipt = {
        **_success(), "passed": False, "bootstrap_closed": False,
        "workspace_reads": 0, "error_code": "bootstrap_failed",
    }
    assert helper._child_receipt(_encode(receipt)) == receipt
    assert helper._child_passed(receipt) is False


def test_unknown_and_duplicate_fields_are_rejected(helper):
    assert helper._child_receipt(_encode({**_success(), "synthetic_extra": 1})) is None
    raw = _encode(_success())
    needle = b'"passed":true'
    assert needle in raw
    assert helper._child_receipt(raw.replace(needle, b'"passed":true,"passed":true', 1)) is None


@pytest.mark.parametrize("transform", [
    lambda raw: b"synthetic output\n" + raw,
    lambda raw: raw + b"synthetic output\n",
    lambda raw: raw.replace(b',"passed"', b',\n"passed"', 1),
    lambda raw: raw + raw,
    lambda raw: raw.replace(b"PACKAGED_WORKSPACE_CHILD=", b"OTHER=", 1),
])
def test_multiline_and_nonreceipt_output_is_rejected(helper, transform):
    assert helper._child_receipt(bytearray(transform(_encode(_success())))) is None


def test_artifact_root_rejects_relative_root_home_and_repository(helper):
    repository = Path(helper.__file__).resolve().parents[2]
    assert helper._safe_artifact_root(Path("synthetic-relative")) is None
    assert helper._safe_artifact_root(Path(repository.anchor)) is None
    assert helper._safe_artifact_root(Path.home()) is None
    assert helper._safe_artifact_root(repository) is None


@pytest.mark.parametrize("reparse_component", ["candidate", "ancestor"])
def test_artifact_root_rejects_lexical_reparse_before_resolution(
    helper, monkeypatch, tmp_path, reparse_component
):
    candidate = tmp_path / "synthetic-artifacts" / "workspace-probes"
    candidate.mkdir(parents=True)
    target = candidate if reparse_component == "candidate" else candidate.parent
    original_lstat = Path.lstat

    def simulated_lstat(path):
        metadata = original_lstat(path)
        if Path(os.path.abspath(os.fspath(path))) == target:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR | 0o755,
                st_file_attributes=getattr(metadata, "st_file_attributes", 0) | 0x400,
            )
        return metadata

    monkeypatch.setattr(Path, "lstat", simulated_lstat)
    assert helper._safe_artifact_root(candidate) is None
