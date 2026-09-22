from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Event
import time

from prompt_enhancer.adapters.synthetic import SyntheticAdapter
from prompt_enhancer.application.automation import (
    AUTOMATION_GRANT_LIFETIME,
    AutomationGrantDraft,
    AutomationGrantScope,
)
from prompt_enhancer.application.jobs import (
    AnalysisJobCancellationSignals,
    AnalysisJobCooperativeStop,
    AnalysisJobIdentity,
    AnalysisJobKind,
    AnalysisJobService,
    AnalysisJobState,
    AnalysisJobWorker,
    PowerSourceState,
)
from prompt_enhancer.application.runtime_cancellation import (
    RuntimeCooperativeStop,
    raise_if_runtime_cancelled,
)
from prompt_enhancer.bootstrap import LocalApplication
from prompt_enhancer.config import AppSettings
from prompt_enhancer.database import Database
from prompt_enhancer.domain import Provider
from prompt_enhancer.ingestion import IngestionService
from prompt_enhancer.privacy import Pseudonymizer


NOW = datetime(2048, 1, 2, 3, 4, tzinfo=UTC)


class MutableClock:
    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> datetime:
        return self.value


class ExternalPower:
    def current(self) -> PowerSourceState:
        return PowerSourceState.EXTERNAL_POWER


def _database(tmp_path) -> tuple[Database, dict[str, object]]:
    database = Database(tmp_path / "cancellation.sqlite3")
    database.initialize()
    IngestionService(database, Pseudonymizer(bytes(range(32)))).ingest(
        SyntheticAdapter()
    )
    return database, database.list_sessions(limit=1)[0]


def _identity(
    session: dict[str, object],
    *,
    input_fingerprint: str,
    automation_grant_id: str | None = None,
) -> AnalysisJobIdentity:
    return AnalysisJobIdentity(
        kind=AnalysisJobKind.SESSION_QUALITY,
        provider=Provider.SYNTHETIC,
        project_id=str(session["project_id"]),
        session_id=str(session["session_id"]),
        input_fingerprint=input_fingerprint,
        provenance_fingerprint="b" * 64,
        metric_keys=("prompt.goal_cue_coverage",),
        estimator_plan_version="synthetic-cancel-plan-v1",
        redactor_version="synthetic-cancel-redactor-v1",
        provider_schema_version="synthetic-schema-v1",
        automation_grant_id=automation_grant_id,
    )


def _wait_for_terminal(database: Database, job_id: str):  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = database.analysis_job_repository().get(job_id)
        assert job is not None
        if job.state in {
            AnalysisJobState.CANCELLED,
            AnalysisJobState.SUPERSEDED,
            AnalysisJobState.FAILED,
            AnalysisJobState.COMPLETED,
        }:
            return job
        time.sleep(0.01)
    raise AssertionError("synthetic job did not settle after cancellation")


def _blocking_handler(entered: Event, interrupted: Event):
    def handler(_job, context):  # type: ignore[no-untyped-def]
        entered.set()
        try:
            while True:
                raise_if_runtime_cancelled("synthetic_provider_wait_cancelled")
                time.sleep(0.005)
        except RuntimeCooperativeStop:
            interrupted.set()
            # This is the same authority resolution used by the automation
            # handler after a bounded source transport notices cancellation.
            context.publication_checkpoint()
            raise AssertionError("cancelled job unexpectedly remained active")

    return handler


def test_durable_job_cancel_interrupts_only_its_active_provider_wait(tmp_path) -> None:
    database, session = _database(tmp_path)
    clock = MutableClock()
    signals = AnalysisJobCancellationSignals()
    jobs = AnalysisJobService(
        database.analysis_job_repository(),
        clock=clock,
        cancellation_signals=signals,
    )
    first = jobs.enqueue(_identity(session, input_fingerprint="1" * 64)).job
    second = jobs.enqueue(_identity(session, input_fingerprint="2" * 64)).job
    first_entered, first_interrupted = Event(), Event()
    second_entered, second_interrupted = Event(), Event()

    def handler(job, context):  # type: ignore[no-untyped-def]
        if job.job_id == first.job_id:
            return _blocking_handler(first_entered, first_interrupted)(job, context)
        assert job.job_id == second.job_id
        return _blocking_handler(second_entered, second_interrupted)(job, context)

    first_worker = AnalysisJobWorker(
        database.analysis_job_repository(),
        {(AnalysisJobKind.SESSION_QUALITY, Provider.SYNTHETIC): handler},
        authorization_check=lambda _job: True,
        fingerprint_resolver=lambda job: (
            job.identity.input_fingerprint,
            job.identity.provenance_fingerprint,
        ),
        cancellation_signals=signals,
        clock=clock,
        worker_id="c" * 64,
        poll_seconds=0.05,
    )
    second_worker = AnalysisJobWorker(
        database.analysis_job_repository(),
        {(AnalysisJobKind.SESSION_QUALITY, Provider.SYNTHETIC): handler},
        authorization_check=lambda _job: True,
        fingerprint_resolver=lambda job: (
            job.identity.input_fingerprint,
            job.identity.provenance_fingerprint,
        ),
        cancellation_signals=signals,
        clock=clock,
        worker_id="d" * 64,
        poll_seconds=0.05,
    )
    try:
        first_worker.start()
        second_worker.start()
        assert first_entered.wait(2)
        assert second_entered.wait(2)

        cancelled = jobs.cancel(first.job_id)
        assert cancelled.cancel_requested is True
        settled = _wait_for_terminal(database, first.job_id)
        assert settled.state is AnalysisJobState.CANCELLED
        assert settled.terminal_reason_code == "cancellation_requested"
        assert first_interrupted.is_set()
        # No shared worker-stop event is used for a user cancel.
        assert not second_interrupted.wait(0.1)
        assert database.analysis_job_repository().get(second.job_id).state in {
            AnalysisJobState.PREPROCESSING,
            AnalysisJobState.STAGE_N,
        }

        jobs.cancel(second.job_id)
        assert _wait_for_terminal(database, second.job_id).state is AnalysisJobState.CANCELLED
    finally:
        first_worker.stop(timeout=2)
        second_worker.stop(timeout=2)


def test_grant_revocation_wakes_active_attempt_and_preserves_reason(tmp_path) -> None:
    database, session = _database(tmp_path)
    clock = MutableClock()
    signals = AnalysisJobCancellationSignals()
    jobs = AnalysisJobService(
        database.analysis_job_repository(),
        clock=clock,
        cancellation_signals=signals,
    )
    grant_id = "e" * 64
    database.automation_grant_repository().create(
        AutomationGrantDraft(
            grant_id=grant_id,
            scope=AutomationGrantScope(
                provider=Provider.SYNTHETIC,
                project_id=str(session["project_id"]),
                metric_keys=("prompt.goal_cue_coverage",),
            ),
            created_at=clock(),
            expires_at=clock() + AUTOMATION_GRANT_LIFETIME,
        )
    )
    job = jobs.enqueue(
        _identity(
            session,
            input_fingerprint="3" * 64,
            automation_grant_id=grant_id,
        )
    ).job
    entered, interrupted = Event(), Event()
    worker = AnalysisJobWorker(
        database.analysis_job_repository(),
        {
            (AnalysisJobKind.SESSION_QUALITY, Provider.SYNTHETIC): (
                _blocking_handler(entered, interrupted)
            )
        },
        authorization_check=lambda _job: True,
        fingerprint_resolver=lambda current: (
            current.identity.input_fingerprint,
            current.identity.provenance_fingerprint,
        ),
        cancellation_signals=signals,
        power_source=ExternalPower(),
        clock=clock,
        worker_id="f" * 64,
        poll_seconds=0.05,
    )
    try:
        worker.start()
        assert entered.wait(2)
        batch = jobs.revoke_automation_grant(grant_id)
        assert batch.cancellation_requested == 1
        settled = _wait_for_terminal(database, job.job_id)
        assert settled.state is AnalysisJobState.CANCELLED
        assert settled.terminal_reason_code == "automation_grant_revoked"
        assert interrupted.is_set()
    finally:
        worker.stop(timeout=2)


def test_admission_reread_refuses_cancellation_that_wins_after_claim(tmp_path) -> None:
    database, session = _database(tmp_path)
    clock = MutableClock()
    cancelled: list[str] = []

    class CancelAtAdmission(AnalysisJobCancellationSignals):
        @contextmanager
        def admit(self, **kwargs):  # type: ignore[no-untyped-def]
            with super().admit(**kwargs) as admission:
                cancelled.append(str(kwargs["job_id"]))
                jobs.cancel(str(kwargs["job_id"]))
                yield admission

    signals = CancelAtAdmission()
    jobs = AnalysisJobService(
        database.analysis_job_repository(),
        clock=clock,
        cancellation_signals=signals,
    )
    job = jobs.enqueue(_identity(session, input_fingerprint="4" * 64)).job
    handler_calls: list[str] = []
    worker = AnalysisJobWorker(
        database.analysis_job_repository(),
        {
            (AnalysisJobKind.SESSION_QUALITY, Provider.SYNTHETIC): (
                lambda current, _context: handler_calls.append(current.job_id)
            )
        },
        authorization_check=lambda _job: True,
        fingerprint_resolver=lambda current: (
            current.identity.input_fingerprint,
            current.identity.provenance_fingerprint,
        ),
        cancellation_signals=signals,
        clock=clock,
        worker_id="0" * 64,
    )

    assert worker.run_once() is True
    assert cancelled == [job.job_id]
    assert handler_calls == []
    settled = database.analysis_job_repository().get(job.job_id)
    assert settled is not None
    assert settled.state is AnalysisJobState.CANCELLED
    assert settled.terminal_reason_code == "cancellation_requested"


def test_worker_stop_wakes_only_its_own_active_attempt(tmp_path) -> None:
    database, session = _database(tmp_path)
    clock = MutableClock()
    signals = AnalysisJobCancellationSignals()
    jobs = AnalysisJobService(
        database.analysis_job_repository(),
        clock=clock,
        cancellation_signals=signals,
    )
    first = jobs.enqueue(_identity(session, input_fingerprint="5" * 64)).job
    second = jobs.enqueue(_identity(session, input_fingerprint="6" * 64)).job
    first_entered, first_interrupted = Event(), Event()
    second_entered, second_interrupted = Event(), Event()

    def handler(job, context):  # type: ignore[no-untyped-def]
        if job.job_id == first.job_id:
            return _blocking_handler(first_entered, first_interrupted)(job, context)
        return _blocking_handler(second_entered, second_interrupted)(job, context)

    first_worker = AnalysisJobWorker(
        database.analysis_job_repository(),
        {(AnalysisJobKind.SESSION_QUALITY, Provider.SYNTHETIC): handler},
        authorization_check=lambda _job: True,
        fingerprint_resolver=lambda current: (
            current.identity.input_fingerprint,
            current.identity.provenance_fingerprint,
        ),
        cancellation_signals=signals,
        clock=clock,
        worker_id="7" * 64,
        poll_seconds=0.05,
    )
    second_worker = AnalysisJobWorker(
        database.analysis_job_repository(),
        {(AnalysisJobKind.SESSION_QUALITY, Provider.SYNTHETIC): handler},
        authorization_check=lambda _job: True,
        fingerprint_resolver=lambda current: (
            current.identity.input_fingerprint,
            current.identity.provenance_fingerprint,
        ),
        cancellation_signals=signals,
        clock=clock,
        worker_id="8" * 64,
        poll_seconds=0.05,
    )
    try:
        first_worker.start()
        second_worker.start()
        assert first_entered.wait(2)
        assert second_entered.wait(2)
        first_worker.stop(timeout=2)
        assert first_interrupted.is_set()
        assert not second_interrupted.wait(0.1)
        stopped = database.analysis_job_repository().get(first.job_id)
        assert stopped is not None
        assert stopped.state is AnalysisJobState.QUEUED
        assert stopped.last_error_code == "application_shutdown"

        jobs.cancel(second.job_id)
        assert _wait_for_terminal(database, second.job_id).state is AnalysisJobState.CANCELLED
    finally:
        first_worker.stop(timeout=2)
        second_worker.stop(timeout=2)


def test_bootstrap_passes_the_api_service_registry_to_the_automation_worker(
    tmp_path,
) -> None:
    database = Database(tmp_path / "bootstrap-cancellation.sqlite3")
    database.initialize()
    application = LocalApplication(
        AppSettings(home=tmp_path),
        database,
        Pseudonymizer(bytes(range(32))),
    )
    service = application.create_analysis_job_service()
    _grants, _grant_worker, worker = application.create_automation_runtime(
        codex_source_service=object(),
        session_text_analysis_service=object(),
        analysis_job_service=service,
    )
    assert worker.cancellation_signals is service.cancellation_signals
