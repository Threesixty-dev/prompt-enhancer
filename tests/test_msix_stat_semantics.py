"""Synthetic MSIX snapshot semantics; no native signer or package installation."""

from __future__ import annotations

import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from prompt_enhancer.application.updates.package_preflight import MsixPreflightReason
from prompt_enhancer.infrastructure.updates.msix_preflight import MsixPackagePreflight
from prompt_enhancer.infrastructure.updates import msix_preflight
from tests.test_msix_preflight_cli import (
    _SyntheticSigner,
    _artifact,
    _expectation,
    _package_bytes,
)


def _fixture(tmp_path, monkeypatch, *, mismatch=False, change=None, tamper=False):
    payload = _package_bytes()
    package = tmp_path / "synthetic-release.msix"
    package.write_bytes(payload)
    original_lstat = Path.lstat
    original_fstat = os.fstat
    identity = package.lstat()

    class Signer(_SyntheticSigner):
        def verify(self, *, path, descriptor):
            result = super().verify(path=path, descriptor=descriptor)
            if tamper:
                before = path.stat()
                changed = bytearray(payload)
                changed[-1] ^= 1
                path.write_bytes(changed)
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            return result

    signer = Signer()

    def snapshot(value, api):
        fields = {name: getattr(value, name) for name in dir(value) if name.startswith("st_")}
        fields.update(st_birthtime_ns=100, st_ctime_ns=200 if api == "fd" and mismatch else 100, st_mtime_ns=300)
        if change is not None:
            target_api, timing, field, changed = change
            if api == target_api and (timing == "initial" or signer.calls > 0):
                fields[field] = changed
        return SimpleNamespace(**fields)

    def lstat(path):
        result = original_lstat(path)
        return snapshot(result, "path") if path == package else result

    def fstat(descriptor):
        result = original_fstat(descriptor)
        if (result.st_dev, result.st_ino) == (identity.st_dev, identity.st_ino):
            return snapshot(result, "fd")
        return result

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(os, "fstat", fstat)
    return package, payload, signer


def _verify(package, payload, signer):
    return MsixPackagePreflight(signer=signer).verify(
        package_path=package, artifact=_artifact(payload), expectation=_expectation(),
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows cross-API semantics")
def test_cross_api_ctime_difference_with_matching_birthtime_is_accepted(tmp_path, monkeypatch):
    package, payload, signer = _fixture(tmp_path, monkeypatch, mismatch=True)
    result = _verify(package, payload, signer)
    assert result.state.value == "verified"
    assert signer.calls == 1


@pytest.mark.parametrize(("api", "field", "value"), [
    ("fd", "st_ino", 123), ("fd", "st_ino", 0),
    ("fd", "st_dev", 123),
    pytest.param("fd", "st_birthtime_ns", 101, marks=pytest.mark.skipif(os.name != "nt", reason="Windows creation-time binding")),
    ("fd", "st_file_attributes", 0x400),
])
def test_initial_descriptor_identity_birthtime_or_reparse_change_refused(tmp_path, monkeypatch, api, field, value):
    package, payload, signer = _fixture(tmp_path, monkeypatch, change=(api, "initial", field, value))
    result = _verify(package, payload, signer)
    assert result.reason is MsixPreflightReason.PACKAGE_CHANGED
    assert signer.calls == 0


@pytest.mark.parametrize(("api", "field", "value"), [
    ("fd", "st_ctime_ns", 101), ("path", "st_ctime_ns", 101),
    ("fd", "st_ino", 123), ("path", "st_ino", 123),
    ("fd", "st_file_attributes", 0x400),
    ("fd", "st_birthtime_ns", 101),
    ("fd", "st_mode", stat.S_IFDIR | 0o600),
])
def test_post_signer_snapshot_changes_are_refused(tmp_path, monkeypatch, api, field, value):
    package, payload, signer = _fixture(tmp_path, monkeypatch, change=(api, "after_signer", field, value))
    result = _verify(package, payload, signer)
    assert result.reason is MsixPreflightReason.PACKAGE_CHANGED
    assert signer.calls == 1


def test_post_signer_byte_mutation_with_restored_mtime_is_refused(tmp_path, monkeypatch):
    package, payload, signer = _fixture(tmp_path, monkeypatch, tamper=True)
    result = _verify(package, payload, signer)
    assert result.reason is MsixPreflightReason.PACKAGE_CHANGED
    assert signer.calls == 1


@pytest.mark.parametrize(("signer_result", "expected"), [
    (None, MsixPreflightReason.SIGNATURE_INVALID),
    ("b" * 64, MsixPreflightReason.SIGNER_MISMATCH),
])
def test_signature_guards_remain_required(tmp_path, monkeypatch, signer_result, expected):
    package, payload, signer = _fixture(tmp_path, monkeypatch)
    signer.result = signer_result
    assert _verify(package, payload, signer).reason is expected
    assert signer.calls == 1


@pytest.mark.parametrize("platform", ["nt", "posix"])
@pytest.mark.parametrize("matching_ctime", [True, False])
def test_missing_birthtime_uses_strict_ctime_on_both_platforms(monkeypatch, platform, matching_ctime):
    # Replace only this module's platform reference, never global os.name.
    monkeypatch.setattr(msix_preflight, "os", SimpleNamespace(name=platform))
    fields = dict(st_dev=11, st_ino=22, st_mode=stat.S_IFREG | 0o600,
                  st_nlink=1, st_size=1, st_mtime_ns=300, st_file_attributes=0)
    path = SimpleNamespace(**fields, st_ctime_ns=100)
    descriptor = SimpleNamespace(**fields, st_ctime_ns=100 if matching_ctime else 200)
    assert msix_preflight._same_path_and_open_file(path, descriptor) is matching_ctime


def test_posix_cross_api_does_not_normalize_ctime_even_when_birthtime_exists(monkeypatch):
    monkeypatch.setattr(msix_preflight, "os", SimpleNamespace(name="posix"))
    fields = dict(st_dev=11, st_ino=22, st_mode=stat.S_IFREG | 0o600,
                  st_nlink=1, st_size=1, st_mtime_ns=300, st_file_attributes=0,
                  st_birthtime_ns=100)
    path = SimpleNamespace(**fields, st_ctime_ns=100)
    descriptor = SimpleNamespace(**fields, st_ctime_ns=200)
    assert msix_preflight._same_path_and_open_file(path, descriptor) is False
