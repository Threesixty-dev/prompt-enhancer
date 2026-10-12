"""Bounded ephemeral admission and execution ownership; bench owns persistence."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib

from .contracts import ExecuteRequest, ExecutionResult, Progress, Readiness
from .engine import EnhancementEngine, execution_id, identity
from .ports import CoreError


@dataclass
class Entry:
    fingerprint: str
    progress: Progress
    result: ExecutionResult | None = None
    task: asyncio.Task | None = None


class ExecutionManager:
    def __init__(self, engine: EnhancementEngine, *, enabled: bool = False,
                 max_active: int = 1, max_retained: int = 32):
        if not 1 <= max_active <= 4 or not max_active <= max_retained <= 128:
            raise ValueError("capacity_invalid")
        self.engine, self.enabled = engine, enabled
        self.max_active, self.max_retained = max_active, max_retained
        self.entries: dict[str, Entry] = {}
        self.quarantined = False

    def readiness(self) -> Readiness:
        active = sum(e.result is None for e in self.entries.values())
        reason = ("disabled" if not self.enabled else "cleanup_unconfirmed" if self.quarantined
                  else "capacity_exhausted" if active >= self.max_active or len(self.entries) >= self.max_retained else "ready")
        return Readiness(ready=reason == "ready", active=active, retained=len(self.entries),
                         capacity=self.max_active, reason=reason)

    def submit(self, request: ExecuteRequest) -> Progress:
        key = execution_id(request)
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        if existing := self.entries.get(key):
            if existing.fingerprint != fingerprint:
                raise CoreError("identity_conflict")
            return existing.progress
        if not self.enabled:
            raise CoreError("synthetic_benchmark_disabled")
        self.engine.validate(request)
        if not self.readiness().ready:
            raise CoreError("admission_unavailable")
        entry = Entry(fingerprint, Progress(**identity(request), execution_id=key,
            status="queued", stage="queued", sequence=0, result_available=False))
        self.entries[key] = entry
        entry.task = asyncio.create_task(self._execute(entry, request))
        return entry.progress

    async def _execute(self, entry: Entry, request: ExecuteRequest):
        def progress(stage):
            entry.progress = entry.progress.model_copy(update={"stage": stage, "status": "running",
                "sequence": entry.progress.sequence + 1})
        result = await self.engine.execute(request, progress)
        entry.result = result
        if result.status == "uncertain":
            self.quarantined = True
        entry.progress = entry.progress.model_copy(update={"status": result.status,
            "stage": "finished", "sequence": entry.progress.sequence + 1, "result_available": True})

    def get(self, key: str) -> Entry:
        if key not in self.entries:
            raise CoreError("execution_not_found")
        return self.entries[key]

    def cancel(self, key: str) -> Progress:
        entry = self.get(key)
        if entry.result is None and entry.progress.status != "cancelling":
            # A newly created task must enter the engine's cancellation handler
            # before cancellation is delivered; scheduling preserves that order.
            entry.progress = entry.progress.model_copy(update={"status": "cancelling",
                "sequence": entry.progress.sequence + 1})
            asyncio.get_running_loop().call_soon(entry.task.cancel)
        return entry.progress

    def delete(self, key: str) -> None:
        if self.get(key).result is None:
            raise CoreError("execution_active")
        del self.entries[key]

    async def close(self) -> None:
        self.enabled = False
        tasks = []
        for key, entry in self.entries.items():
            if entry.task is not None and not entry.task.done():
                self.cancel(key)
                tasks.append(entry.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
