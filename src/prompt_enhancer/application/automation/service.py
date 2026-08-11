"""Consent-aware scheduler for renewable local automation grants."""

from __future__ import annotations

from datetime import datetime, timedelta
from threading import Event, Lock, Thread
from typing import Callable, Protocol

from pydantic import Field

from ...domain import DataTier, Provider, StrictModel
from ..analysis.coaching_baselines import COACHING_METRIC_DEFINITIONS
from .contracts import (
    AUTOMATION_GRANT_LIFETIME,
    AutomationCandidateSource,
    AutomationGrantDraft,
    AutomationGrantRecord,
    AutomationGrantRepository,
    AutomationGrantScope,
    AutomationGrantState,
    AutomationSessionCandidate,
)


AUTOMATION_POLL_LIMIT = 100
DEFAULT_AUTOMATION_WORKER_POLL_SECONDS = 60.0
COACHING_AUTOMATION_METRIC_KEYS = frozenset(
    definition.key for definition in COACHING_METRIC_DEFINITIONS
)


class AutomationGrantError(RuntimeError):
    """Base class whose messages are fixed, content-free reason codes."""

    def __init__(self, code: str) -> None:
        if not code.startswith("automation_"):
            raise ValueError("automation error code is invalid")
        self.code = code
        super().__init__(code)


class AutomationConsentError(AutomationGrantError):
    pass


class AutomationSelectionError(AutomationGrantError):
    pass


class AutomationGrantNotFoundError(AutomationGrantError):
    pass


class AutomationAccessPolicy(Protocol):
    def has_active_consent(self, provider: Provider, tier: DataTier) -> bool: ...

    def project_is_indexed(self, provider: Provider, project_id: str) -> bool: ...


class AutomationIdFactory(Protocol):
    def new_id(self) -> str: ...


class AutomationCatalogRefresher(Protocol):
    def refresh(self, provider: Provider, *, max_sessions: int) -> None: ...


class AutomationScheduleResult(StrictModel):
    created: bool
    superseded: int = Field(default=0, ge=0)


class AutomationJobSink(Protocol):
    def schedule(
        self,
        grant: AutomationGrantRecord,
        candidate: AutomationSessionCandidate,
    ) -> AutomationScheduleResult: ...

    def cancel_for_grant(self, grant_id: str, *, now: datetime) -> int: ...


class AutomationPollResult(StrictModel):
    grants_checked: int = Field(ge=0)
    grants_revoked: int = Field(ge=0)
    candidates_seen: int = Field(ge=0)
    jobs_created: int = Field(ge=0)
    jobs_reused: int = Field(ge=0)
    jobs_superseded: int = Field(ge=0)
    failures: int = Field(ge=0)


class AutomationGrantService:
    """Schedule only indexed, changed metadata under active local consent."""

    _TIER = DataTier.REDACTED_CONTENT

    def __init__(
        self,
        repository: AutomationGrantRepository,
        access: AutomationAccessPolicy,
        refresher: AutomationCatalogRefresher,
        candidates: AutomationCandidateSource,
        jobs: AutomationJobSink,
        id_factory: AutomationIdFactory,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._access = access
        self._refresher = refresher
        self._candidates = candidates
        self._jobs = jobs
        self._id_factory = id_factory
        self._clock = clock

    def create(self, scope: AutomationGrantScope) -> AutomationGrantRecord:
        self._require_access(scope)
        now = self._clock()
        return self._repository.create(
            AutomationGrantDraft(
                grant_id=self._id_factory.new_id(),
                scope=scope,
                created_at=now,
                expires_at=now + AUTOMATION_GRANT_LIFETIME,
            )
        )

    def get(self, grant_id: str) -> AutomationGrantRecord:
        return self._require_grant(grant_id)

    def list_for_provider(
        self,
        provider: Provider,
        *,
        active_only: bool = False,
    ) -> tuple[AutomationGrantRecord, ...]:
        records = self._repository.list_for_provider(
            provider,
            active_only=active_only,
        )
        if not active_only:
            return records
        now = self._clock()
        return tuple(
            record
            for record in records
            if record.effective_state(now) is AutomationGrantState.ACTIVE
        )

    def renew(self, grant_id: str) -> AutomationGrantRecord:
        current = self._require_grant(grant_id)
        self._require_access(current.scope)
        return self._repository.renew(grant_id, now=self._clock())

    def revoke(self, grant_id: str) -> AutomationGrantRecord:
        now = self._clock()
        self._require_grant(grant_id)
        revoked = self._repository.revoke(grant_id, now=now)
        self._jobs.cancel_for_grant(grant_id, now=now)
        return revoked

    def revoke_provider(self, provider: Provider) -> int:
        now = self._clock()
        grants = self._repository.list_for_provider(provider, active_only=True)
        for grant in grants:
            self._repository.revoke(grant.grant_id, now=now)
            self._jobs.cancel_for_grant(grant.grant_id, now=now)
        return len(grants)

    def poll_due(self, *, limit: int = AUTOMATION_POLL_LIMIT) -> AutomationPollResult:
        if limit < 1 or limit > AUTOMATION_POLL_LIMIT:
            raise ValueError("automation poll limit is out of bounds")
        now = self._clock()
        self._repository.expire_due(now=now)
        checked = revoked = seen = created = reused = superseded = failures = 0
        for grant in self._repository.list_due(now=now, limit=limit):
            checked += 1
            if not self._access.has_active_consent(
                grant.scope.provider, self._TIER
            ):
                self._repository.revoke(grant.grant_id, now=now)
                self._jobs.cancel_for_grant(grant.grant_id, now=now)
                revoked += 1
                continue
            try:
                self._refresher.refresh(
                    grant.scope.provider,
                    max_sessions=grant.scope.newest_session_limit,
                )
                candidates = self._candidates.newest_changed(
                    grant.scope,
                    limit=grant.scope.newest_session_limit,
                )
                seen += len(candidates)
                for candidate in candidates:
                    if (
                        candidate.provider is not grant.scope.provider
                        or candidate.project_id != grant.scope.project_id
                    ):
                        raise AutomationSelectionError(
                            "automation_candidate_scope_mismatch"
                        )
                    outcome = self._jobs.schedule(grant, candidate)
                    created += int(outcome.created)
                    reused += int(not outcome.created)
                    superseded += outcome.superseded
                self._repository.record_check(
                    grant.grant_id,
                    now=now,
                    next_check_at=(
                        now
                        + timedelta(
                            seconds=grant.scope.check_interval_seconds
                        )
                    ),
                    error_code=None,
                )
            except AutomationSelectionError:
                failures += 1
                self._repository.record_check(
                    grant.grant_id,
                    now=now,
                    next_check_at=(
                        now
                        + timedelta(
                            seconds=grant.scope.check_interval_seconds
                        )
                    ),
                    error_code="candidate_scope_mismatch",
                )
            except Exception:
                # Provider/repository exception text may contain private details.
                failures += 1
                self._repository.record_check(
                    grant.grant_id,
                    now=now,
                    next_check_at=(
                        now
                        + timedelta(
                            seconds=grant.scope.check_interval_seconds
                        )
                    ),
                    error_code="automation_check_failed",
                )
        return AutomationPollResult(
            grants_checked=checked,
            grants_revoked=revoked,
            candidates_seen=seen,
            jobs_created=created,
            jobs_reused=reused,
            jobs_superseded=superseded,
            failures=failures,
        )

    def _require_access(self, scope: AutomationGrantScope) -> None:
        if not set(scope.metric_keys).issubset(COACHING_AUTOMATION_METRIC_KEYS):
            raise AutomationSelectionError("automation_metric_unsupported")
        if not self._access.has_active_consent(scope.provider, self._TIER):
            raise AutomationConsentError("automation_consent_required")
        if not self._access.project_is_indexed(scope.provider, scope.project_id):
            raise AutomationSelectionError("automation_project_not_indexed")

    def _require_grant(self, grant_id: str) -> AutomationGrantRecord:
        grant = self._repository.get(grant_id)
        if grant is None:
            raise AutomationGrantNotFoundError("automation_grant_not_found")
        return grant


class AutomationGrantWorker:
    """One local scheduler thread; job execution remains in the job worker."""

    def __init__(
        self,
        service: AutomationGrantService,
        *,
        poll_seconds: float = DEFAULT_AUTOMATION_WORKER_POLL_SECONDS,
    ) -> None:
        if not 1 <= poll_seconds <= 15 * 60:
            raise ValueError("automation worker poll interval is out of bounds")
        self._service = service
        self._poll_seconds = poll_seconds
        self._stop_event = Event()
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = Thread(
                target=self._run,
                name="automation-grant-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        with self._lock:
            thread = self._thread
            if thread is None:
                return
            self._stop_event.set()
        thread.join(timeout=timeout)
        with self._lock:
            if self._thread is thread and not thread.is_alive():
                self._thread = None

    def run_once(self) -> AutomationPollResult:
        return self._service.poll_due()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                # Scheduler failures are retried; exception text is never logged.
                pass
            self._stop_event.wait(self._poll_seconds)


__all__ = [
    "AUTOMATION_POLL_LIMIT",
    "COACHING_AUTOMATION_METRIC_KEYS",
    "AutomationAccessPolicy",
    "AutomationCatalogRefresher",
    "AutomationConsentError",
    "AutomationGrantError",
    "AutomationGrantNotFoundError",
    "AutomationGrantService",
    "AutomationGrantWorker",
    "AutomationIdFactory",
    "AutomationJobSink",
    "AutomationPollResult",
    "AutomationScheduleResult",
    "AutomationSelectionError",
    "DEFAULT_AUTOMATION_WORKER_POLL_SECONDS",
]
