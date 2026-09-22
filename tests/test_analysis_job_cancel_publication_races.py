from __future__ import annotations

from datetime import timedelta

import pytest

from prompt_enhancer.application.jobs import (
    AnalysisJobCancellationSignals,
    AnalysisJobCooperativeStop,
    AnalysisJobExecutionContext,
    AnalysisJobKind,
    AnalysisJobService,
    AnalysisJobState,
    AnalysisJobWorker,
    PowerSourceState,
)
from prompt_enhancer.application.runtime_cancellation import (
    RuntimeCleanupUnconfirmed,
    RuntimeCooperativeStop,
    raise_if_runtime_cancelled,
)
from prompt_enhancer.database import DatabaseInvariantError

from test_analysis_job_queue import (
    MutableClock,
    _database,
    _identity,
    _lease,
)
from test_automation_publication_deadline_persistence import (
    NOW,
    _automation_fixture,
    _counts,
    _result,
)


def _active_context(repository, job, lease, clock) -> AnalysisJobExecutionContext:
    return AnalysisJobExecutionContext(
        repository,
        job,
        lease,
        clock=clock,
        monotonic_clock=lambda: 100.0,
        lease_duration=timedelta(minutes=10),
        authorization_check=lambda _job: True,
        fingerprint_resolver=lambda current: (
            current.identity.input_fingerprint,
            current.identity.provenance_fingerprint,
        ),
        execution_stop_callback=lambda _job, _state, _reason: None,
    )


def _claim(repository, job, clock, *, owner: str, token: str):
    claimed = repository.claim_next(
        owner=owner,
        token=token,
        now=clock(),
        lease_duration=timedelta(minutes=10),
        power_source=PowerSourceState.EXTERNAL_POWER,
    )
    assert claimed is not None and claimed.job_id == job.job_id
    return claimed


def test_manual_cancel_commits_before_signaling_and_stops_at_publication_checkpoint(
    tmp_path,
) -> None:
    database, session = _database(tmp_path)
    repository = database.analysis_job_repository()
    clock = MutableClock()

    class DurableFirstSignals(AnalysisJobCancellationSignals):
        def signal_job(self, job_id: str) -> int:
            persisted = repository.get(job_id)
            assert persisted is not None and persisted.cancel_requested is True
            return super().signal_job(job_id)

    signals = DurableFirstSignals()
    service = AnalysisJobService(
        repository,
        clock=clock,
        cancellation_signals=signals,
    )
    queued = service.enqueue(_identity(session)).job
    claimed = _claim(
        repository,
        queued,
        clock,
        owner="1" * 64,
        token="2" * 64,
    )
    lease = _lease(claimed)
    context = _active_context(repository, claimed, lease, clock)

    with signals.admit(
        job_id=claimed.job_id,
        lease_owner=lease.owner,
        lease_token=lease.token,
        automation_grant_id=None,
    ) as admission:
        cancelled = service.cancel(claimed.job_id)
        assert cancelled.cancel_requested is True
        assert admission.event.is_set()
        with pytest.raises(AnalysisJobCooperativeStop) as raised:
            context.publication_checkpoint()

    assert raised.value.reason_code == "cancellation_requested"
    stopped = repository.get(claimed.job_id)
    assert stopped is not None
    assert stopped.state is AnalysisJobState.CANCELLED
    assert stopped.terminal_reason_code == "cancellation_requested"


def test_revoked_grant_persists_reason_signals_attempt_and_stops_before_publication(
    tmp_path,
) -> None:
    fixture = _automation_fixture(tmp_path)
    signals = AnalysisJobCancellationSignals()
    service = AnalysisJobService(
        fixture.job_repository,
        clock=lambda: NOW,
        cancellation_signals=signals,
    )
    context = _active_context(
        fixture.job_repository,
        fixture.job_repository.get(fixture.job_id),
        fixture.lease,
        lambda: NOW,
    )

    with signals.admit(
        job_id=fixture.job_id,
        lease_owner=fixture.lease.owner,
        lease_token=fixture.lease.token,
        automation_grant_id=fixture.grant_id,
    ) as admission:
        batch = service.revoke_automation_grant(fixture.grant_id)
        assert batch.cancelled == 0
        assert batch.cancellation_requested == 1
        assert admission.event.is_set()
        with pytest.raises(AnalysisJobCooperativeStop) as raised:
            context.publication_checkpoint()

    assert raised.value.reason_code == "automation_grant_revoked"
    stopped = fixture.job_repository.get(fixture.job_id)
    assert stopped is not None
    assert stopped.state is AnalysisJobState.CANCELLED
    assert stopped.terminal_reason_code == "automation_grant_revoked"


def test_already_committed_publication_wins_over_late_job_cancel(tmp_path) -> None:
    fixture = _automation_fixture(tmp_path)
    finished_at = NOW + timedelta(minutes=1)
    fixture.run_repository.complete(
        fixture.run_id,
        (_result(computed_at=finished_at),),
        finished_at=finished_at,
        completion_authority=fixture.authority,
    )

    cancelled = AnalysisJobService(
        fixture.job_repository,
        clock=lambda: finished_at,
    ).cancel(fixture.job_id)

    assert cancelled.state is AnalysisJobState.COMPLETED
    assert cancelled.cancel_requested is False
    assert cancelled.terminal_reason_code == "local_analysis_completed"
    assert _counts(fixture.database, fixture.run_id, fixture.job_id)[
        "publication"
    ] == 1


def test_cancelled_automation_job_rejects_late_publication_without_derived_rows(
    tmp_path,
) -> None:
    fixture = _automation_fixture(tmp_path)
    cancelled = AnalysisJobService(
        fixture.job_repository,
        clock=lambda: NOW,
    ).cancel(fixture.job_id)
    assert cancelled.cancel_requested is True

    with pytest.raises(
        DatabaseInvariantError,
        match="automation completion authority is no longer valid",
    ):
        fixture.run_repository.complete(
            fixture.run_id,
            (_result(computed_at=NOW + timedelta(minutes=1)),),
            finished_at=NOW + timedelta(minutes=1),
            completion_authority=fixture.authority,
        )

    assert _counts(fixture.database, fixture.run_id, fixture.job_id) == {
        "results": 0,
        "evidence": 0,
        "signals": 0,
        "history": 0,
        "publication": 0,
        "closure": 0,
        "authorization": 0,
    }
    run = fixture.run_repository.get(fixture.run_id)
    job = fixture.job_repository.get(fixture.job_id)
    assert run is not None and run.status.value == "running"
    assert job is not None and job.state is AnalysisJobState.PREPROCESSING


def test_cleanup_uncertainty_keeps_worker_quarantined_after_cancellation_race(
    tmp_path,
) -> None:
    database, session = _database(tmp_path)
    repository = database.analysis_job_repository()
    signals = AnalysisJobCancellationSignals()
    service = AnalysisJobService(repository, cancellation_signals=signals)
    queued = service.enqueue(_identity(session)).job
    calls: list[str] = []

    def uncertain(job, _context):  # type: ignore[no-untyped-def]
        calls.append("handler_entered")
        cancelled = service.cancel(job.job_id)
        assert cancelled.cancel_requested is True
        try:
            raise_if_runtime_cancelled("synthetic_provider_wait_cancelled")
        except RuntimeCooperativeStop:
            calls.append("owned_close_uncertain")
            raise RuntimeCleanupUnconfirmed("synthetic cleanup uncertainty")
        raise AssertionError("durable cancellation did not reach the active scope")

    worker = AnalysisJobWorker(
        repository,
        {(AnalysisJobKind.SESSION_QUALITY, "synthetic"): uncertain},
        authorization_check=lambda _job: True,
        fingerprint_resolver=lambda job: (
            job.identity.input_fingerprint,
            job.identity.provenance_fingerprint,
        ),
        cancellation_signals=signals,
    )

    assert worker.run_once() is False
    assert worker.cleanup_unconfirmed is True
    assert calls == ["handler_entered", "owned_close_uncertain"]
    active = repository.get(queued.job_id)
    assert active is not None
    assert active.state in {AnalysisJobState.PREPROCESSING, AnalysisJobState.STAGE_N}
    assert active.cancel_requested is True
    assert worker.run_once() is False
    assert calls == ["handler_entered", "owned_close_uncertain"]
    with pytest.raises(RuntimeCleanupUnconfirmed, match="analysis_job_cleanup_unconfirmed"):
        worker.start()
