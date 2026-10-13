"""Synthetic native-history retention and runtime-release failure cases."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import runpy
import shutil
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
    assert reloaded.path(service.identifier).stat().st_mode & 0o777 == 0o600


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
