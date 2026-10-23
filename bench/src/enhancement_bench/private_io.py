"""Bounded JSON inputs and private, non-overwriting client artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from .definitions import canonical
from .errors import BenchError


def local_path(path: Path) -> Path:
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise BenchError("file_link_forbidden")
    return path


def decode_json(data: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("nonfinite_json")
    try:
        return json.loads(data, object_pairs_hook=unique, parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError):
        raise BenchError("invalid_json") from None


def read_json(path: Path, *, private=False, limit=1_000_000):
    path = local_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise BenchError("regular_file_required")
            if private and os.name != "nt" and info.st_mode & 0o077:
                raise BenchError("private_file_required")
            data = stream.read(limit + 1)
    except OSError:
        raise BenchError("file_read_failed") from None
    if len(data) > limit:
        raise BenchError("file_too_large")
    return decode_json(data)


def write_new(path: Path, data: bytes):
    path = local_path(path)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        raise BenchError("output_exists") from None
    except OSError:
        raise BenchError("file_write_failed") from None
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        sync_directory(path.parent)
    except OSError:
        path.unlink(missing_ok=True)
        raise BenchError("file_write_failed") from None


def sync_directory(path: Path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def write_json(path: Path, value, *, replace=False):
    data = (canonical(value) + "\n").encode()
    if not replace:
        write_new(path, data)
        return
    path = local_path(path)
    read_json(path, private=True)
    temporary = path.with_name(".bench-" + uuid4().hex + ".tmp")
    try:
        write_new(temporary, data)
        os.replace(temporary, path)
        sync_directory(path.parent)
    except OSError:
        raise BenchError("file_write_failed") from None
    finally:
        temporary.unlink(missing_ok=True)
