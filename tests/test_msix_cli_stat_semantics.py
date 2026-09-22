"""Synthetic release-input reader guards; no signer, runtime or package launch."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def reader():
    spec = importlib.util.spec_from_file_location("synthetic_msix_reader", Path(__file__).parents[1] / "scripts" / "verify_msix_package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_metadata(tmp_path, monkeypatch, *, change=None, birthtime=True, split=None):
    target = tmp_path / "synthetic.manifest"
    target.write_bytes(b"synthetic")
    real_lstat, real_fstat = Path.lstat, os.fstat
    identity = real_lstat(target)
    calls = {"path": 0, "fd": 0}
    descriptors = []

    def convert(value, api):
        fields = {key: getattr(value, key) for key in dir(value) if key.startswith("st_")}
        mismatch = os.name == "nt" if split is None else split
        fields.update(st_ctime_ns=200 if api == "fd" and mismatch else 100, st_mtime_ns=300)
        if birthtime:
            fields["st_birthtime_ns"] = 100
        else:
            fields.pop("st_birthtime_ns", None)
        calls[api] += 1
        if change is not None:
            target_api, at, field, changed = change
            if api == target_api and calls[api] >= at:
                fields[field] = changed
        return SimpleNamespace(**fields)

    def lstat(path):
        value = real_lstat(path)
        return convert(value, "path") if path == target else value

    def fstat(fd):
        value = real_fstat(fd)
        if (value.st_dev, value.st_ino) == (identity.st_dev, identity.st_ino):
            descriptors.append(fd)
            return convert(value, "fd")
        return value

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(os, "fstat", fstat)
    return target, descriptors, real_fstat


def test_cross_api_semantics_and_descriptor_cleanup(reader, tmp_path, monkeypatch):
    target, descriptors, real_fstat = fixture_metadata(tmp_path, monkeypatch, split=True)
    result = reader._read_regular(target, maximum=64)
    assert result == (b"synthetic" if os.name == "nt" else None)
    assert descriptors
    with pytest.raises(OSError):
        real_fstat(descriptors[-1])


@pytest.mark.parametrize("change", [
    ("fd", 1, "st_ino", 0), ("fd", 1, "st_ino", 123), ("fd", 1, "st_dev", 123),
    ("fd", 1, "st_size", 8), ("fd", 1, "st_birthtime_ns", 101),
    ("fd", 1, "st_file_attributes", 0x400), ("fd", 1, "st_nlink", 2),
    ("fd", 2, "st_ctime_ns", 201), ("fd", 2, "st_file_attributes", 0x400),
    ("fd", 2, "st_birthtime_ns", 101), ("fd", 2, "st_mode", 0),
    ("path", 2, "st_ctime_ns", 101), ("path", 3, "st_ctime_ns", 101),
    ("path", 3, "st_ino", 123), ("path", 3, "st_file_attributes", 0x400),
])
def test_mutation_identity_and_reparse_rejected(reader, tmp_path, monkeypatch, change):
    target, _, _ = fixture_metadata(tmp_path, monkeypatch, change=change)
    assert reader._read_regular(target, maximum=64) is None


def test_missing_birthtime_retains_strict_ctime(reader, tmp_path, monkeypatch):
    target, _, _ = fixture_metadata(tmp_path, monkeypatch, birthtime=False, split=True)
    assert reader._read_regular(target, maximum=64) is None


@pytest.mark.parametrize("maximum,exact", [(8, None), (64, 8), (64, 10)])
def test_byte_bounds_still_enforced(reader, tmp_path, monkeypatch, maximum, exact):
    target, _, _ = fixture_metadata(tmp_path, monkeypatch)
    assert reader._read_regular(target, maximum=maximum, exact=exact) is None


def test_plain_read_and_exact_limit(reader, tmp_path):
    target = tmp_path / "synthetic.manifest"
    target.write_bytes(b"synthetic")
    assert reader._read_regular(target, maximum=9, exact=9) == b"synthetic"


def test_posix_comparison_keeps_raw_ctime(reader, monkeypatch):
    metadata = dict(st_dev=1, st_ino=2, st_size=9, st_mtime_ns=3, st_ctime_ns=4,
                    st_nlink=1, st_mode=0o100600, st_birthtime_ns=1)
    monkeypatch.setattr(reader, "os", SimpleNamespace(name="posix"))
    assert reader._same_path_and_descriptor(SimpleNamespace(**metadata), SimpleNamespace(**metadata))
    assert not reader._same_path_and_descriptor(SimpleNamespace(**metadata), SimpleNamespace(**{**metadata, "st_ctime_ns": 5}))
