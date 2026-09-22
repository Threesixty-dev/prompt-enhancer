"""Process-local wakeups for durable, content-free analysis-job cancellation.

The database remains the authority: callers commit a cancellation first, then
signal a matching active attempt so an owned bounded provider wait can stop
without polling SQLite.  Signals are deliberately process-local; a separately
started worker still rechecks the durable job row before it begins provider
work and at every existing publication boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Event, Lock
from typing import Iterator


@dataclass(frozen=True, slots=True)
class AnalysisJobCancellationAdmission:
    """One exact leased attempt's scoped cancellation event."""

    job_id: str
    lease_owner: str
    lease_token: str
    event: Event


@dataclass(frozen=True, slots=True)
class _RegisteredAdmission:
    admission: AnalysisJobCancellationAdmission
    automation_grant_id: str | None


class AnalysisJobCancellationSignals:
    """Wake only the active attempt selected by a durable cancellation.

    A registration is keyed by the full lease identity rather than just a job
    id.  An old attempt's ``finally`` therefore cannot remove a newer attempt
    that was admitted after lease recovery.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._active: dict[tuple[str, str, str], _RegisteredAdmission] = {}

    @staticmethod
    def _key(
        job_id: str,
        lease_owner: str,
        lease_token: str,
    ) -> tuple[str, str, str]:
        return (job_id, lease_owner, lease_token)

    @contextmanager
    def admit(
        self,
        *,
        job_id: str,
        lease_owner: str,
        lease_token: str,
        automation_grant_id: str | None,
    ) -> Iterator[AnalysisJobCancellationAdmission]:
        admission = AnalysisJobCancellationAdmission(
            job_id=job_id,
            lease_owner=lease_owner,
            lease_token=lease_token,
            event=Event(),
        )
        key = self._key(job_id, lease_owner, lease_token)
        with self._lock:
            if key in self._active:
                raise RuntimeError("analysis_job_cancellation_admission_duplicate")
            self._active[key] = _RegisteredAdmission(admission, automation_grant_id)
        try:
            yield admission
        finally:
            with self._lock:
                current = self._active.get(key)
                if current is not None and current.admission is admission:
                    del self._active[key]

    def signal_job(self, job_id: str) -> int:
        """Signal all active attempts for one durable job id."""

        return self._signal_matching(
            lambda admission: admission.admission.job_id == job_id
        )

    def signal_automation_grant(self, automation_grant_id: str) -> int:
        """Signal active attempts bound to one durably revoked grant."""

        return self._signal_matching(
            lambda admission: admission.automation_grant_id == automation_grant_id
        )

    def signal_worker(self, worker_id: str) -> int:
        """Propagate one worker's shutdown without stopping another worker."""

        return self._signal_matching(
            lambda admission: admission.admission.lease_owner == worker_id
        )

    def _signal_matching(
        self,
        predicate: Callable[[_RegisteredAdmission], bool],
    ) -> int:
        with self._lock:
            matches = tuple(
                admission
                for admission in self._active.values()
                if predicate(admission)
            )
            for admission in matches:
                admission.admission.event.set()
            return len(matches)


__all__ = ["AnalysisJobCancellationAdmission", "AnalysisJobCancellationSignals"]
