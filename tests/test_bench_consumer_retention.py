"""Synthetic native-history retention and runtime-release failure cases."""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import runpy
import shutil
import stat
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import pytest

Retention = runpy.run_path(str(Path(__file__).resolve().parents[1]
                              / "deployment/bench/consumer_retention.py"))["Retention"]


class Service:
    def __init__(self, root, *, status="finished", active=False, close_fails=False, process_stays=False):
        self.identifier = uuid4()
        self.conversations_dir = root
        history = root / self.identifier.hex
        history.mkdir(parents=True)
        (history / "example-event.json").write_text('{"text":"Fictional widget prompt"}')
        self.info = SimpleNamespace(execution_status=status,
            workspace=SimpleNamespace(working_dir=f"/tmp/enhancement-{self.identifier}"))
        self.process = SimpleNamespace(returncode=None)
        self.open = True
        async def close(*args):
            if close_fails:
                raise RuntimeError("example-close-failed")
            self.open = False
            if not process_stays:
                self.process.returncode = 0
        self._event_services = {self.identifier: SimpleNamespace(
            is_idle_evictable=lambda: not active, __aexit__=close, is_open=lambda: self.open,
            stored=object(), get_conversation=lambda: SimpleNamespace(agent=SimpleNamespace(_process=self.process)))}
        self._conversation_records = {self.identifier: SimpleNamespace(stored=None, cached_info=None)}
        self.deleted = []

    @asynccontextmanager
    async def _conversation_lifecycle(self, identifier):
        yield

    async def get_conversation(self, identifier):
        return self.info if identifier == self.identifier else None

    async def delete_conversation(self, identifier):
        self.deleted.append(identifier)
        shutil.rmtree(self.conversations_dir / identifier.hex)
        self.info = None
        return True


def test_completed_history_survives_release_and_retention_controller_restart(tmp_path):
    service = Service(tmp_path / "conversations")
    retention = Retention(tmp_path / "receipts", 7)
    held = asyncio.run(retention.release(service, service.identifier))
    assert held["runtime_released"] and not held["cleanup_confirmed"]
    assert held["expires_at"] is None and service.deleted == []
    assert service.process.returncode == 0 and not service._event_services
    assert (service.conversations_dir / service.identifier.hex / "example-event.json").exists()
    retained = asyncio.run(retention.retain(service, service.identifier))
    reloaded = Retention(tmp_path / "receipts", 7)
    assert reloaded.read(service.identifier) == retained
    assert asyncio.run(reloaded.retain(service, service.identifier)) == retained
    # Windows exposes read/write attributes here, not POSIX owner/group modes.
    assert reloaded.path(service.identifier).stat().st_mode & 0o777 == (0o666 if os.name == "nt" else 0o600)


def test_windows_receipt_syncs_the_file_without_opening_the_directory(tmp_path, monkeypatch):
    retention = Retention(tmp_path / "receipts", 7)
    identifier = uuid4()
    synced = []

    def sync_file(fd):
        assert stat.S_ISREG(os.fstat(fd).st_mode)
        synced.append(fd)
        os.fsync(fd)

    def reject_directory_open(*args, **kwargs):
        pytest.fail("Windows receipt writes must not open a directory descriptor")

    monkeypatch.setitem(Retention.write.__globals__, "os", SimpleNamespace(**(vars(os) | {
        "name": "nt", "fsync": sync_file, "open": reject_directory_open,
    })))
    retention.write(identifier, {"conversation_id": str(identifier)})
    assert len(synced) == 1
    assert retention.read(identifier) == {"conversation_id": str(identifier)}
    assert not list(retention.directory.glob("*.pending"))


def test_failed_file_sync_preserves_the_previous_receipt(tmp_path, monkeypatch):
    retention = Retention(tmp_path / "receipts", 7)
    identifier = uuid4()
    original = {"conversation_id": str(identifier), "cleanup_confirmed": False}
    retention.write(identifier, original)

    def fail_sync(fd):
        raise OSError("example-file-sync-failure")

    monkeypatch.setitem(Retention.write.__globals__, "os", SimpleNamespace(**(vars(os) | {
        "fsync": fail_sync,
    })))
    with pytest.raises(OSError, match="example-file-sync-failure"):
        retention.write(identifier, {**original, "cleanup_confirmed": True})
    assert retention.read(identifier) == original
    assert not list(retention.directory.glob("*.pending"))


def test_posix_directory_sync_failure_remains_visible_and_closes_descriptor(tmp_path, monkeypatch):
    retention = Retention(tmp_path / "receipts", 7)
    identifier = uuid4()
    directory_fd = object()
    closed = []

    def open_directory(path, flags):
        assert path == retention.directory
        return directory_fd

    def sync(fd):
        if fd is directory_fd:
            raise OSError("example-directory-sync-failure")
        os.fsync(fd)

    def close(fd):
        assert fd is directory_fd
        closed.append(fd)

    monkeypatch.setitem(Retention.write.__globals__, "os", SimpleNamespace(**(vars(os) | {
        "name": "posix", "open": open_directory, "fsync": sync, "close": close,
    })))
    with pytest.raises(OSError, match="example-directory-sync-failure"):
        retention.write(identifier, {"conversation_id": str(identifier)})
    assert closed == [directory_fd]
    assert not list(retention.directory.glob("*.pending"))


@pytest.mark.parametrize("options", [dict(status="running"), dict(active=True),
    dict(close_fails=True), dict(process_stays=True)])
def test_uncertain_or_active_runtime_never_gets_expiry(tmp_path, options):
    service = Service(tmp_path / "conversations", **options)
    retention = Retention(tmp_path / "receipts", 7)
    with pytest.raises((HTTPException, RuntimeError)):
        asyncio.run(retention.release(service, service.identifier))
    assert retention.read(service.identifier) is None
    assert service.deleted == []


def test_expiry_keeps_cleanup_holds_and_unexpired_history(tmp_path):
    service = Service(tmp_path / "conversations")
    retention = Retention(tmp_path / "receipts", 7)
    asyncio.run(retention.release(service, service.identifier))
    asyncio.run(retention.expire(service))
    assert service.deleted == []
    receipt = asyncio.run(retention.retain(service, service.identifier))
    asyncio.run(retention.expire(service))
    assert service.deleted == []
    receipt["expires_at"] = 1
    retention.write(service.identifier, receipt)
    asyncio.run(Retention(tmp_path / "receipts", 7).expire(service))
    assert service.deleted == [service.identifier]
    assert not retention.path(service.identifier).exists()


def test_expired_history_is_not_deleted_if_runtime_was_reopened(tmp_path):
    service = Service(tmp_path / "conversations")
    retention = Retention(tmp_path / "receipts", 7)
    asyncio.run(retention.release(service, service.identifier))
    receipt = asyncio.run(retention.retain(service, service.identifier))
    receipt["expires_at"] = 1
    retention.write(service.identifier, receipt)
    service._event_services[service.identifier] = object()
    asyncio.run(retention.expire(service))
    assert service.deleted == []


@pytest.mark.parametrize("days", [0, -1, 91])
def test_retention_requires_bounded_positive_days(tmp_path, days):
    with pytest.raises(ValueError, match="retention_days_invalid"):
        Retention(tmp_path / "receipts", days)


def test_nonbench_conversation_is_never_adopted(tmp_path):
    service = Service(tmp_path / "conversations")
    service.info.workspace.working_dir = "/tmp/example-unrelated"
    retention = Retention(tmp_path / "receipts", 7)
    with pytest.raises(HTTPException, match="conversation_not_bench_owned"):
        asyncio.run(retention.release(service, service.identifier))
    assert service.open and retention.read(service.identifier) is None
