"""Durable opt-in scheduling for one continuously refreshed model ensemble.

The watch stores only pseudonymous identifiers, fingerprints, fixed reason
codes, progress counters, and timestamps.  Redacted text remains inside the
existing ephemeral ensemble execution boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
import hashlib
from threading import Event, Lock, Thread
from typing import Callable, Protocol

from pydantic import Field, field_validator, model_validator

from ...domain import PSEUDONYM_PATTERN, Provider, SAFE_VERSION_PATTERN, StrictModel
from .session_model_ensemble import (
    MODEL_ENSEMBLE_CONFIRMATION,
    SessionModelEnsembleError,
    SessionModelEnsembleOutcome,
)


MODEL_ENSEMBLE_WATCH_CONTRACT_VERSION = "model-ensemble-watch-v1"
MODEL_ENSEMBLE_WATCH_CONFIRMATION = "continuously_analyze_selected_redacted_session"
MODEL_ENSEMBLE_WATCH_POLL_SECONDS = 60
MODEL_ENSEMBLE_WATCH_LEASE_SECONDS = 30 * 60
MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL = 10


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _safe_id(value: str) -> str:
    if PSEUDONYM_PATTERN.fullmatch(value) is None:
        raise ValueError("watch identifier must be a local pseudonym")
    return value


def _safe_code(value: str) -> str:
    if SAFE_VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("watch reason must be a fixed content-free code")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("watch timestamp must be UTC")
    return value


class ModelEnsembleWatchState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    IDLE = "idle"
    FAILED = "failed"
    DISABLED = "disabled"


class ModelEnsembleWatchRecord(StrictModel):
    watch_id: str
    provider: Provider
    project_id: str
    session_id: str
    max_messages: int = Field(ge=1, le=100)
    state: ModelEnsembleWatchState
    generation: int = Field(ge=0)
    progress_completed: int = Field(ge=0, le=MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL)
    progress_total: int = Field(default=MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL)
    latest_run_id: str | None = None
    latest_input_fingerprint: str | None = None
    last_error_code: str | None = None
    next_check_at: datetime
    lease_owner: str | None = None
    lease_token: str | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    _ids = field_validator("watch_id", "project_id", "session_id")(_safe_id)
    _optional_ids = field_validator(
        "latest_run_id",
        "latest_input_fingerprint",
        "lease_owner",
        "lease_token",
    )(lambda value: None if value is None else _safe_id(value))
    _reason = field_validator("last_error_code")(
        lambda value: None if value is None else _safe_code(value)
    )
    _times = field_validator(
        "next_check_at",
        "lease_expires_at",
        "created_at",
        "updated_at",
    )(lambda value: None if value is None else _utc(value))

    @model_validator(mode="after")
    def validate_state(self) -> "ModelEnsembleWatchRecord":
        leased = self.state is ModelEnsembleWatchState.RUNNING
        lease_complete = all(
            value is not None
            for value in (self.lease_owner, self.lease_token, self.lease_expires_at)
        )
        if leased != lease_complete:
            raise ValueError("only a running watch may hold a complete lease")
        if self.progress_completed > self.progress_total:
            raise ValueError("watch progress cannot exceed its total")
        if self.state is ModelEnsembleWatchState.IDLE and self.last_error_code is not None:
            raise ValueError("an idle watch cannot retain a failure code")
        return self


class ModelEnsembleWatchLease(StrictModel):
    watch_id: str
    owner: str
    token: str
    expires_at: datetime

    _ids = field_validator("watch_id", "owner", "token")(_safe_id)
    _time = field_validator("expires_at")(_utc)


class ModelEnsembleWatchRepository(Protocol):
    def enable(
        self,
        *,
        watch_id: str,
        provider: Provider,
        project_id: str,
        session_id: str,
        max_messages: int = 100,
        now: datetime,
    ) -> ModelEnsembleWatchRecord: ...

    def disable(self, watch_id: str, *, now: datetime) -> ModelEnsembleWatchRecord: ...

    def get(self, watch_id: str) -> ModelEnsembleWatchRecord | None: ...

    def get_active(self) -> ModelEnsembleWatchRecord | None: ...

    def claim_due(
        self,
        *,
        owner: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> tuple[ModelEnsembleWatchRecord, ModelEnsembleWatchLease] | None: ...

    def heartbeat(
        self,
        lease: ModelEnsembleWatchLease,
        *,
        now: datetime,
        lease_duration: timedelta,
        progress_completed: int,
    ) -> tuple[ModelEnsembleWatchRecord, ModelEnsembleWatchLease]: ...

    def complete(
        self,
        lease: ModelEnsembleWatchLease,
        *,
        now: datetime,
        next_check_at: datetime,
        outcome: SessionModelEnsembleOutcome,
    ) -> ModelEnsembleWatchRecord: ...

    def fail(
        self,
        lease: ModelEnsembleWatchLease,
        *,
        now: datetime,
        next_check_at: datetime,
        reason_code: str,
    ) -> ModelEnsembleWatchRecord: ...


ProgressCallback = Callable[[int, int], None]


class ContinuousModelEnsembleCommand(Protocol):
    def require_watchable(self, *, provider: Provider, session_id: str) -> None: ...

    def run(
        self,
        *,
        provider: Provider,
        session_id: str,
        confirmation: str,
        idempotency_key: str,
        max_messages: int = 100,
        progress_callback: ProgressCallback | None = None,
        reuse_latest: bool = True,
    ) -> SessionModelEnsembleOutcome: ...


class ModelEnsembleWatchError(RuntimeError):
    code = "model_ensemble_watch_failed"


class ModelEnsembleWatchInputError(ModelEnsembleWatchError):
    code = "invalid_model_ensemble_watch_request"


class ModelEnsembleWatchNotFoundError(ModelEnsembleWatchError):
    code = "model_ensemble_watch_not_found"


class ModelEnsembleWatchConflictError(ModelEnsembleWatchError):
    code = "model_ensemble_watch_conflict"


class ModelEnsembleWatchStopped(RuntimeError):
    """Private cooperative signal used between serial expert stages."""


class ModelEnsembleWatchService:
    """Enable, inspect, and execute one durable continuous local watch."""

    def __init__(
        self,
        repository: ModelEnsembleWatchRepository,
        ensemble: ContinuousModelEnsembleCommand,
        *,
        clock: Callable[[], datetime] = _utc_now,
        poll_interval: timedelta = timedelta(seconds=MODEL_ENSEMBLE_WATCH_POLL_SECONDS),
        lease_duration: timedelta = timedelta(seconds=MODEL_ENSEMBLE_WATCH_LEASE_SECONDS),
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        if not timedelta(seconds=5) <= poll_interval <= timedelta(minutes=15):
            raise ValueError("watch poll interval is outside the reviewed bound")
        if lease_duration < timedelta(minutes=5):
            raise ValueError("watch lease is too short for serial local inference")
        self._repository = repository
        self._ensemble = ensemble
        self._clock = clock
        self._poll_interval = poll_interval
        self._lease_duration = lease_duration
        self._id_factory = id_factory or (
            lambda value: hashlib.sha256(value.encode("ascii")).hexdigest()
        )
        self._owner = self._id_factory(
            f"{MODEL_ENSEMBLE_WATCH_CONTRACT_VERSION}:worker:{id(self)}"
        )

    def enable(
        self,
        *,
        provider: Provider,
        project_id: str,
        session_id: str,
        max_messages: int = 100,
        confirmation: str,
    ) -> ModelEnsembleWatchRecord:
        if (
            provider is not Provider.CODEX
            or PSEUDONYM_PATTERN.fullmatch(project_id) is None
            or PSEUDONYM_PATTERN.fullmatch(session_id) is None
            or not isinstance(max_messages, int)
            or isinstance(max_messages, bool)
            or not 1 <= max_messages <= 100
            or confirmation != MODEL_ENSEMBLE_WATCH_CONFIRMATION
        ):
            raise ModelEnsembleWatchInputError()
        self._ensemble.require_watchable(provider=provider, session_id=session_id)
        watch_id = self._id_factory(
            ":".join(
                (
                    MODEL_ENSEMBLE_WATCH_CONTRACT_VERSION,
                    provider.value,
                    project_id,
                    session_id,
                )
            )
        )
        try:
            return self._repository.enable(
                watch_id=watch_id,
                provider=provider,
                project_id=project_id,
                session_id=session_id,
                max_messages=max_messages,
                now=self._clock(),
            )
        except ValueError:
            raise ModelEnsembleWatchConflictError() from None

    def disable(self, watch_id: str) -> ModelEnsembleWatchRecord:
        if PSEUDONYM_PATTERN.fullmatch(watch_id) is None:
            raise ModelEnsembleWatchInputError()
        try:
            return self._repository.disable(watch_id, now=self._clock())
        except ValueError:
            raise ModelEnsembleWatchNotFoundError() from None

    def get_active(self) -> ModelEnsembleWatchRecord | None:
        return self._repository.get_active()

    def run_once(self) -> ModelEnsembleWatchRecord | None:
        now = self._clock()
        claimed = self._repository.claim_due(
            owner=self._owner,
            now=now,
            lease_duration=self._lease_duration,
        )
        if claimed is None:
            return None
        record, lease = claimed

        def progress(completed: int, total: int) -> None:
            nonlocal record, lease
            if total != MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL:
                raise ValueError("watch progress total changed")
            operation_at = self._clock()
            record, lease = self._repository.heartbeat(
                lease,
                now=operation_at,
                lease_duration=self._lease_duration,
                progress_completed=completed,
            )
            if record.state is not ModelEnsembleWatchState.RUNNING:
                raise ModelEnsembleWatchStopped()

        key = self._id_factory(
            f"{MODEL_ENSEMBLE_WATCH_CONTRACT_VERSION}:{record.watch_id}:{record.generation}"
        )
        try:
            outcome = self._ensemble.run(
                provider=record.provider,
                session_id=record.session_id,
                confirmation=MODEL_ENSEMBLE_CONFIRMATION,
                idempotency_key=key,
                max_messages=record.max_messages,
                progress_callback=progress,
                reuse_latest=True,
            )
            finished_at = self._clock()
            return self._repository.complete(
                lease,
                now=finished_at,
                next_check_at=finished_at + self._poll_interval,
                outcome=outcome,
            )
        except ModelEnsembleWatchStopped:
            current = self._repository.get(record.watch_id)
            return current
        except SessionModelEnsembleError as error:
            reason = error.code
        except Exception:
            reason = "model_ensemble_watch_execution_failed"
        failed_at = self._clock()
        try:
            return self._repository.fail(
                lease,
                now=failed_at,
                next_check_at=failed_at + self._poll_interval,
                reason_code=reason,
            )
        except ValueError:
            return self._repository.get(record.watch_id)


class ModelEnsembleWatchWorker:
    """One coalescing watch worker and therefore one global model/GPU lane."""

    def __init__(
        self,
        service: ModelEnsembleWatchService,
        *,
        wake_seconds: float = 5.0,
    ) -> None:
        if not 1 <= wake_seconds <= 60:
            raise ValueError("watch worker cadence is outside the reviewed bound")
        self._service = service
        self._wake_seconds = wake_seconds
        self._stop = Event()
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = Thread(
                target=self._run,
                name="model-ensemble-watch-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        with self._lock:
            thread = self._thread
            if thread is None:
                return
            self._stop.set()
        thread.join(timeout=timeout)
        with self._lock:
            if self._thread is thread and not thread.is_alive():
                self._thread = None

    def run_once(self) -> ModelEnsembleWatchRecord | None:
        return self._service.run_once()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                # Exception text may carry private adapter details; retry later.
                pass
            self._stop.wait(self._wake_seconds)


__all__ = [
    "MODEL_ENSEMBLE_WATCH_CONFIRMATION",
    "MODEL_ENSEMBLE_WATCH_CONTRACT_VERSION",
    "MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL",
    "ContinuousModelEnsembleCommand",
    "ModelEnsembleWatchConflictError",
    "ModelEnsembleWatchError",
    "ModelEnsembleWatchInputError",
    "ModelEnsembleWatchLease",
    "ModelEnsembleWatchNotFoundError",
    "ModelEnsembleWatchRecord",
    "ModelEnsembleWatchRepository",
    "ModelEnsembleWatchService",
    "ModelEnsembleWatchState",
    "ModelEnsembleWatchWorker",
]
