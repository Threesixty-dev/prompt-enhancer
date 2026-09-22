"""Synthetic same-API metadata regression tests; no release assembly."""
import hashlib
import stat
from types import SimpleNamespace

import pytest

from prompt_enhancer.infrastructure import build_staging as staging


def metadata(**changes):
    values = dict(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o600, st_nlink=1,
                  st_size=9, st_mtime_ns=10, st_ctime_ns=11, st_birthtime_ns=12,
                  st_atime_ns=13, st_file_attributes=0)
    values.update(changes)
    return SimpleNamespace(**values)


def check(tmp_path, monkeypatch, after):
    path = tmp_path / "synthetic.txt"
    data = b"synthetic"
    path.write_bytes(data)
    observations = iter([metadata(), after])
    monkeypatch.setattr(staging, "_ordinary", lambda *args, **kwargs: next(observations))
    staging._hash_checked(path, len(data), hashlib.sha256(data).hexdigest())


def test_read_access_time_change_accepted(tmp_path, monkeypatch):
    check(tmp_path, monkeypatch, metadata(st_atime_ns=999))


@pytest.mark.parametrize("field,value", [
    ("st_dev", 3), ("st_ino", 3), ("st_mode", stat.S_IFREG | 0o400),
    ("st_nlink", 2), ("st_size", 10), ("st_mtime_ns", 99), ("st_ctime_ns", 99),
    ("st_birthtime_ns", 99), ("st_file_attributes", 0x400),
])
def test_mutation_still_rejected(tmp_path, monkeypatch, field, value):
    with pytest.raises(staging.WindowsReleaseStagingError):
        check(tmp_path, monkeypatch, metadata(**{field: value}))


def test_directory_access_time_excluded_without_mutation_relaxation():
    before = metadata(st_mode=stat.S_IFDIR | 0o700)
    after = metadata(st_mode=stat.S_IFDIR | 0o700, st_atime_ns=999)
    assert staging._snapshot(before) == staging._snapshot(after)
    after.st_ctime_ns += 1
    assert staging._snapshot(before) != staging._snapshot(after)


def test_optional_birthtime_absence_is_stable():
    before, after = metadata(), metadata(st_atime_ns=999)
    del before.st_birthtime_ns
    del after.st_birthtime_ns
    assert staging._snapshot(before) == staging._snapshot(after)
    after.st_ctime_ns += 1
    assert staging._snapshot(before) != staging._snapshot(after)
