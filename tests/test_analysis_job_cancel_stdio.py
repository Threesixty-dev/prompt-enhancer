from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
import time

import pytest

from prompt_enhancer.application.jobs import (
    AnalysisJobCancellationSignals,
    AnalysisJobIdentity,
    AnalysisJobKind,
    AnalysisJobService,
    PowerSourceState,
)
from prompt_enhancer.application.runtime_cancellation import (
    RuntimeCooperativeStop,
    runtime_request_scope,
)
from prompt_enhancer.infrastructure.providers.codex_app_server.transports import (
    stdio_jsonl,
)
from prompt_enhancer.infrastructure.providers.codex_app_server.transports.stdio_jsonl import (
    CODEX_APP_SERVER_ARGV,
    StdioJsonRpcTransport,
)
from prompt_enhancer.adapters.synthetic import SyntheticAdapter
from prompt_enhancer.database import Database
from prompt_enhancer.domain import Provider
from prompt_enhancer.ingestion import IngestionService
from prompt_enhancer.privacy import Pseudonymizer


class _StalledInput:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def close(self) -> None:
        self._events.append("stdin.close")


class _StalledOutput:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.started = Event()
        self._released = Event()

    def readline(self, _limit: int) -> bytes:
        self.started.set()
        self._released.wait(timeout=1)
        return b""

    def close(self) -> None:
        self._events.append("stdout.close")
        self._released.set()


class _StalledProcess:
    def __init__(self, events: list[str]) -> None:
        self.stdin = _StalledInput(events)
        self.stdout = _StalledOutput(events)
        self._events = events
        self._killed = False

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        self._events.append("terminate")

    def kill(self) -> None:
        self._events.append("kill")
        self._killed = True

    def wait(self, timeout: float | None = None) -> int:
        if self._killed:
            self._events.append("wait.after_kill")
            return 0
        raise subprocess.TimeoutExpired(CODEX_APP_SERVER_ARGV, timeout)


class _GetBarrier:
    """Forward the real transport queue while exposing entry into its wait."""

    def __init__(self, queue, entered: Event) -> None:  # type: ignore[no-untyped-def]
        self._queue = queue
        self._entered = entered

    def put(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._queue.put(*args, **kwargs)

    def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self._entered.set()
        return self._queue.get(*args, **kwargs)

    def get_nowait(self):  # type: ignore[no-untyped-def]
        return self._queue.get_nowait()

    def put_nowait(self, value):  # type: ignore[no-untyped-def]
        return self._queue.put_nowait(value)


def test_durable_job_cancel_interrupts_an_active_scoped_stdio_wait(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2046, 1, 2, tzinfo=UTC)
    database = Database(tmp_path / "synthetic-cancel-stdio.sqlite3")
    database.initialize()
    IngestionService(database, Pseudonymizer(bytes(range(32)))).ingest(
        SyntheticAdapter()
    )
    session = database.list_sessions(limit=1)[0]
    repository = database.analysis_job_repository()
    signals = AnalysisJobCancellationSignals()
    service = AnalysisJobService(
        repository, clock=lambda: now, cancellation_signals=signals
    )
    queued = service.enqueue(
        AnalysisJobIdentity(
            kind=AnalysisJobKind.SESSION_QUALITY,
            provider=Provider.SYNTHETIC,
            project_id=str(session["project_id"]),
            session_id=str(session["session_id"]),
            input_fingerprint="a" * 64,
            provenance_fingerprint="b" * 64,
            metric_keys=("prompt.goal_cue_coverage",),
            estimator_plan_version="synthetic-plan-v1",
            redactor_version="synthetic-redactor-v1",
            provider_schema_version="synthetic-schema-v1",
        )
    ).job
    claimed = repository.claim_next(
        owner="a" * 64,
        token="b" * 64,
        now=now,
        lease_duration=timedelta(minutes=5),
        power_source=PowerSourceState.EXTERNAL_POWER,
    )
    assert claimed is not None and claimed.job_id == queued.job_id
    assert claimed.lease_owner is not None
    assert claimed.lease_token is not None
    events: list[str] = []
    process = _StalledProcess(events)
    monkeypatch.setattr(stdio_jsonl, "start_codex_app_server_process", lambda: process)
    transport = StdioJsonRpcTransport()
    entered_wait = Event()
    transport._lines = _GetBarrier(transport._lines, entered_wait)  # type: ignore[assignment]
    transport._start()
    assert process.stdout.started.wait(timeout=1)

    try:
        with signals.admit(
            job_id=claimed.job_id,
            lease_owner=claimed.lease_owner,
            lease_token=claimed.lease_token,
            automation_grant_id=None,
        ) as admission:
            cancellation_complete = Event()

            def cancel_after_wait_begins() -> None:
                assert entered_wait.wait(timeout=1)
                cancelled = service.cancel(claimed.job_id)
                assert cancelled.cancel_requested is True
                cancellation_complete.set()

            canceller = Thread(target=cancel_after_wait_begins, daemon=True)
            canceller.start()
            started = time.monotonic()
            with runtime_request_scope(admission.event), pytest.raises(
                RuntimeCooperativeStop, match="^codex_provider_request_cancelled$"
            ):
                transport._next_message(deadline=10**9)
            assert time.monotonic() - started < 0.5
            canceller.join(timeout=1)
            assert cancellation_complete.is_set()
            assert not canceller.is_alive()
            assert admission.event.is_set()
    finally:
        transport.close()

    # Runtime cancellation kills only this transport-owned fake helper; the
    # normal close path then reaps it and releases its reader.
    assert events == ["kill", "stdin.close", "wait.after_kill", "stdout.close"]
