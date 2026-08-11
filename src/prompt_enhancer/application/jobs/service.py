"""Use cases and local worker seam for durable analysis jobs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
import hashlib
import json
import secrets
from threading import Event, Lock, Thread
from typing import Protocol

from pydantic import Field, field_validator, model_validator

from ...database import DatabaseInvariantError
from ...domain import SAFE_VERSION_PATTERN, Provider, StrictModel
from .contracts import (
    ANALYSIS_JOB_CONTRACT_VERSION,
    TERMINAL_ANALYSIS_JOB_STATES,
    AnalysisJobCancellationBatchResult,
    AnalysisJobDraft,
    AnalysisJobEnqueueResult,
    AnalysisJobIdentity,
    AnalysisJobKind,
    AnalysisJobLease,
    AnalysisJobPage,
    AnalysisJobRecord,
    AnalysisJobRepository,
    AnalysisJobState,
)


DEFAULT_ANALYSIS_JOB_LEASE = timedelta(seconds=30)
DEFAULT_ANALYSIS_JOB_POLL_SECONDS = 1.0


class AnalysisJobServiceError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AnalysisJobNotFoundError(AnalysisJobServiceError):
    def __init__(self) -> None:
        super().__init__("analysis_job_not_found")


class AnalysisJobConflictError(AnalysisJobServiceError):
    def __init__(self) -> None:
        super().__init__("analysis_job_conflict")


class AnalysisJobExecutionError(RuntimeError):
    """Handler error that exposes only a reviewed content-free code."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        if SAFE_VERSION_PATTERN.fullmatch(code) is None:
            raise ValueError("execution error code must be content-free")
        self.code = code
        self.retryable = retryable
        super().__init__(code)


class AnalysisJobExecutionResult(StrictModel):
    state: AnalysisJobState
    reason_code: str
    progress_completed: int = Field(ge=0, le=1_000_000)
    progress_total: int = Field(ge=1, le=1_000_000)

    @field_validator("reason_code")
    @classmethod
    def safe_reason_code(cls, value: str) -> str:
        if SAFE_VERSION_PATTERN.fullmatch(value) is None:
            raise ValueError("execution result reason must be content-free")
        return value

    @model_validator(mode="after")
    def closed_result_state(self) -> AnalysisJobExecutionResult:
        if self.state not in {
            AnalysisJobState.AWAITING_APPROVAL,
            AnalysisJobState.COMPLETED,
            AnalysisJobState.PARTIAL,
        }:
            raise ValueError("handler returned an unsupported queue state")
        if self.progress_completed > self.progress_total:
            raise ValueError("execution progress cannot exceed its total")
        if (
            self.state is AnalysisJobState.COMPLETED
            and self.progress_completed != self.progress_total
        ):
            raise ValueError("completed execution must report complete progress")
        return self


class AnalysisJobHandler(Protocol):
    def __call__(
        self,
        job: AnalysisJobRecord,
        context: AnalysisJobExecutionContext,
    ) -> AnalysisJobExecutionResult: ...


Clock = Callable[[], datetime]
AuthorizationCheck = Callable[[AnalysisJobRecord], bool]
FingerprintResolver = Callable[[AnalysisJobRecord], tuple[str, str] | None]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _identity_digest(identity: AnalysisJobIdentity, max_attempts: int) -> str:
    canonical = json.dumps(
        {
            "contract_version": ANALYSIS_JOB_CONTRACT_VERSION,
            "identity": identity.model_dump(mode="json"),
            "max_attempts": max_attempts,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _job_id(dedupe_key: str) -> str:
    return hashlib.sha256(
        f"{ANALYSIS_JOB_CONTRACT_VERSION}:{dedupe_key}".encode("ascii")
    ).hexdigest()


class AnalysisJobService:
    """Content-free enqueue/query/cancel boundary used by HTTP and automation."""

    def __init__(
        self,
        repository: AnalysisJobRepository,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def enqueue(
        self,
        identity: AnalysisJobIdentity,
        *,
        max_attempts: int = 3,
    ) -> AnalysisJobEnqueueResult:
        if isinstance(max_attempts, bool) or not 1 <= max_attempts <= 5:
            raise ValueError("max attempts must be between one and five")
        dedupe_key = _identity_digest(identity, max_attempts)
        job_id = _job_id(dedupe_key)
        existing = self._repository.get(job_id)
        if existing is not None:
            if (
                existing.dedupe_key != dedupe_key
                or existing.identity != identity
                or existing.max_attempts != max_attempts
            ):
                raise AnalysisJobConflictError()
            return AnalysisJobEnqueueResult(job=existing, created=False)
        try:
            return self._repository.enqueue(
                AnalysisJobDraft(
                    job_id=job_id,
                    dedupe_key=dedupe_key,
                    identity=identity,
                    max_attempts=max_attempts,
                    created_at=self._clock(),
                )
            )
        except DatabaseInvariantError:
            # A concurrent identical enqueue may have won after the first read.
            concurrent = self._repository.get(job_id)
            if (
                concurrent is not None
                and concurrent.dedupe_key == dedupe_key
                and concurrent.identity == identity
                and concurrent.max_attempts == max_attempts
            ):
                return AnalysisJobEnqueueResult(job=concurrent, created=False)
            raise AnalysisJobConflictError() from None

    def get(self, job_id: str) -> AnalysisJobRecord:
        try:
            job = self._repository.get(job_id)
        except ValueError:
            raise AnalysisJobNotFoundError() from None
        if job is None:
            raise AnalysisJobNotFoundError()
        return job

    def list(
        self,
        *,
        state: AnalysisJobState | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> AnalysisJobPage:
        return self._repository.list(state=state, limit=limit, offset=offset)

    def list_active(self, *, limit: int = 100) -> AnalysisJobPage:
        return self._repository.list_active(limit=limit)

    def latest_for_session(self, session_id: str) -> AnalysisJobRecord | None:
        try:
            return self._repository.get_latest_for_session(session_id)
        except ValueError:
            raise AnalysisJobNotFoundError() from None

    def cancel(self, job_id: str) -> AnalysisJobRecord:
        self.get(job_id)
        try:
            return self._repository.request_cancel(job_id, now=self._clock())
        except DatabaseInvariantError:
            raise AnalysisJobConflictError() from None

    def resume_after_approval(self, job_id: str) -> AnalysisJobRecord:
        self.get(job_id)
        try:
            return self._repository.resume_after_approval(
                job_id,
                now=self._clock(),
            )
        except DatabaseInvariantError:
            raise AnalysisJobConflictError() from None

    def revoke_automation_grant(
        self,
        automation_grant_id: str,
    ) -> AnalysisJobCancellationBatchResult:
        try:
            return self._repository.cancel_by_automation_grant(
                automation_grant_id,
                now=self._clock(),
            )
        except ValueError:
            raise AnalysisJobNotFoundError() from None

    def supersede_if_changed(
        self,
        job_id: str,
        *,
        input_fingerprint: str,
        provenance_fingerprint: str,
    ) -> AnalysisJobRecord:
        job = self.get(job_id)
        if job.state in TERMINAL_ANALYSIS_JOB_STATES:
            return job
        reason: str | None = None
        if input_fingerprint != job.identity.input_fingerprint:
            reason = "input_changed"
        elif provenance_fingerprint != job.identity.provenance_fingerprint:
            reason = "provenance_changed"
        if reason is None:
            return job
        try:
            return self._repository.supersede(
                job_id,
                now=self._clock(),
                reason_code=reason,
            )
        except DatabaseInvariantError:
            raise AnalysisJobConflictError() from None


class _ExecutionStopped(RuntimeError):
    pass


class AnalysisJobExecutionContext:
    """Lease-bound handler controls; values are all content-free."""

    def __init__(
        self,
        repository: AnalysisJobRepository,
        job: AnalysisJobRecord,
        lease: AnalysisJobLease,
        *,
        clock: Clock,
        lease_duration: timedelta,
        authorization_check: AuthorizationCheck,
        fingerprint_resolver: FingerprintResolver,
    ) -> None:
        self._repository = repository
        self._job = job
        self._lease = lease
        self._clock = clock
        self._lease_duration = lease_duration
        self._authorization_check = authorization_check
        self._fingerprint_resolver = fingerprint_resolver
        self._lock = Lock()

    @property
    def job(self) -> AnalysisJobRecord:
        return self._job

    @property
    def lease(self) -> AnalysisJobLease:
        return self._lease

    def _stop(
        self,
        state: AnalysisJobState,
        reason_code: str,
    ) -> None:
        self._job = self._repository.finish(
            self._lease,
            now=self._clock(),
            state=state,
            reason_code=reason_code,
            progress_completed=self._job.progress_completed,
            progress_total=self._job.progress_total,
        )
        raise _ExecutionStopped()

    def _guard_and_renew_locked(self) -> AnalysisJobRecord:
        persisted = self._repository.get(self._job.job_id)
        if persisted is None:
            raise _ExecutionStopped()
        self._job = persisted
        if persisted.cancel_requested:
            reason = persisted.last_error_code or "cancellation_requested"
            terminal = (
                AnalysisJobState.SUPERSEDED
                if reason in {"input_changed", "provenance_changed"}
                else AnalysisJobState.CANCELLED
            )
            self._stop(terminal, reason)
        if not self._authorization_check(persisted):
            self._stop(AnalysisJobState.CANCELLED, "authorization_revoked")
        current = self._fingerprint_resolver(persisted)
        if current is None:
            self._stop(AnalysisJobState.FAILED, "identity_check_unavailable")
        current_input, current_provenance = current
        if current_input != persisted.identity.input_fingerprint:
            self._stop(AnalysisJobState.SUPERSEDED, "input_changed")
        if current_provenance != persisted.identity.provenance_fingerprint:
            self._stop(AnalysisJobState.SUPERSEDED, "provenance_changed")
        renewed = self._repository.renew(
            self._lease,
            now=self._clock(),
            lease_duration=self._lease_duration,
        )
        self._job = renewed
        if renewed.lease_expires_at is None:
            raise _ExecutionStopped()
        self._lease = AnalysisJobLease(
            job_id=renewed.job_id,
            owner=renewed.lease_owner,
            token=renewed.lease_token,
            expires_at=renewed.lease_expires_at,
        )
        return renewed

    def heartbeat(self) -> AnalysisJobRecord:
        with self._lock:
            return self._guard_and_renew_locked()

    def enter_stage(
        self,
        stage_number: int,
        *,
        progress_completed: int,
        progress_total: int,
    ) -> AnalysisJobRecord:
        with self._lock:
            self._guard_and_renew_locked()
            self._job = self._repository.advance_stage(
                self._lease,
                now=self._clock(),
                stage_number=stage_number,
                progress_completed=progress_completed,
                progress_total=progress_total,
            )
            return self._job


class AnalysisJobWorker:
    """One bounded local worker; handlers must be explicitly reviewed/injected."""

    def __init__(
        self,
        repository: AnalysisJobRepository,
        handlers: Mapping[tuple[AnalysisJobKind, Provider], AnalysisJobHandler],
        *,
        authorization_check: AuthorizationCheck = lambda _job: False,
        fingerprint_resolver: FingerprintResolver = lambda _job: None,
        clock: Clock = _utc_now,
        lease_duration: timedelta = DEFAULT_ANALYSIS_JOB_LEASE,
        poll_seconds: float = DEFAULT_ANALYSIS_JOB_POLL_SECONDS,
        worker_id: str | None = None,
    ) -> None:
        if not 0.05 <= poll_seconds <= 60:
            raise ValueError("worker poll interval is outside the reviewed bound")
        self._repository = repository
        self._handlers = dict(handlers)
        self._authorization_check = authorization_check
        self._fingerprint_resolver = fingerprint_resolver
        self._clock = clock
        self._lease_duration = lease_duration
        self._poll_seconds = poll_seconds
        self._worker_id = worker_id or secrets.token_hex(32)
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._lifecycle_lock = Lock()

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._repository.recover_expired(now=self._clock())
            self._stop_event.clear()
            self._thread = Thread(
                target=self._run,
                name="analysis-job-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        with self._lifecycle_lock:
            thread = self._thread
            if thread is None:
                return
            self._stop_event.set()
        thread.join(timeout=timeout)
        with self._lifecycle_lock:
            if self._thread is thread and not thread.is_alive():
                self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            worked = self.run_once()
            if not worked:
                self._stop_event.wait(self._poll_seconds)

    def run_once(self) -> bool:
        now = self._clock()
        token = secrets.token_hex(32)
        job = self._repository.claim_next(
            owner=self._worker_id,
            token=token,
            now=now,
            lease_duration=self._lease_duration,
        )
        if job is None:
            return False
        if job.lease_expires_at is None or job.lease_owner is None or job.lease_token is None:
            return True
        lease = AnalysisJobLease(
            job_id=job.job_id,
            owner=job.lease_owner,
            token=job.lease_token,
            expires_at=job.lease_expires_at,
        )
        handler = self._handlers.get((job.identity.kind, job.identity.provider))
        if handler is None:
            self._repository.retry_or_fail(
                lease,
                now=self._clock(),
                error_code="execution_handler_unavailable",
                retryable=False,
            )
            return True
        context = AnalysisJobExecutionContext(
            self._repository,
            job,
            lease,
            clock=self._clock,
            lease_duration=self._lease_duration,
            authorization_check=self._authorization_check,
            fingerprint_resolver=self._fingerprint_resolver,
        )
        try:
            context.enter_stage(1, progress_completed=0, progress_total=1)
            result = handler(context.job, context)
            context.heartbeat()
            if result.state is AnalysisJobState.AWAITING_APPROVAL:
                self._repository.await_approval(
                    context.lease,
                    now=self._clock(),
                    reason_code=result.reason_code,
                    progress_completed=result.progress_completed,
                    progress_total=result.progress_total,
                )
            else:
                self._repository.finish(
                    context.lease,
                    now=self._clock(),
                    state=result.state,
                    reason_code=result.reason_code,
                    progress_completed=result.progress_completed,
                    progress_total=result.progress_total,
                )
        except _ExecutionStopped:
            pass
        except AnalysisJobExecutionError as error:
            self._retry_safely(context.lease, error.code, error.retryable)
        except Exception:
            self._retry_safely(context.lease, "execution_handler_failed", True)
        return True

    def _retry_safely(
        self,
        lease: AnalysisJobLease,
        error_code: str,
        retryable: bool,
    ) -> None:
        try:
            self._repository.retry_or_fail(
                lease,
                now=self._clock(),
                error_code=error_code,
                retryable=retryable,
            )
        except DatabaseInvariantError:
            # The lease was already recovered or terminal; never expose handler data.
            return
