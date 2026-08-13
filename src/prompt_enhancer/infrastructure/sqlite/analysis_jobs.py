"""SQLite state machine for durable, content-free local analysis jobs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import sqlite3

from ...application.jobs import (
    ACTIVE_ANALYSIS_JOB_STATES,
    TERMINAL_ANALYSIS_JOB_STATES,
    AnalysisJobCancellationBatchResult,
    AnalysisJobDraft,
    AnalysisJobEnqueueResult,
    AnalysisJobIdentity,
    AnalysisJobKind,
    AnalysisJobLease,
    AnalysisJobPage,
    AnalysisJobRecord,
    AnalysisJobRecoveryResult,
    AnalysisJobState,
    PowerSourceState,
)
from ...database import DatabaseInvariantError
from ...domain import Provider
from ._common import (
    ConnectionScope,
    from_iso,
    require_safe_id,
    require_safe_label,
    require_utc,
    to_iso,
)


_RETRY_BASE = timedelta(seconds=5)
_RETRY_MAX = timedelta(minutes=5)


class SqliteAnalysisJobRepository:
    """Transactional queue with expiring leases and bounded retry recovery."""

    def __init__(
        self,
        connection_scope: ConnectionScope,
        ensure_initialized: Callable[[], None],
    ) -> None:
        self._connection_scope = connection_scope
        self._ensure_initialized = ensure_initialized

    @staticmethod
    def _retry_delay(attempt_count: int) -> timedelta:
        seconds = _RETRY_BASE.total_seconds() * (2 ** max(0, attempt_count - 1))
        return timedelta(seconds=min(seconds, _RETRY_MAX.total_seconds()))

    @staticmethod
    def _metrics(
        connection: sqlite3.Connection,
        job_id: str,
    ) -> tuple[str, ...]:
        return tuple(
            row["metric_key"]
            for row in connection.execute(
                """
                SELECT metric_key FROM analysis_job_metrics
                WHERE job_id = ? ORDER BY ordinal
                """,
                (job_id,),
            ).fetchall()
        )

    @classmethod
    def _record(
        cls,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> AnalysisJobRecord:
        return AnalysisJobRecord(
            job_id=row["job_id"],
            dedupe_key=row["dedupe_key"],
            identity=AnalysisJobIdentity(
                kind=AnalysisJobKind(row["kind"]),
                provider=Provider(row["provider"]),
                project_id=row["project_id"],
                session_id=row["session_id"],
                input_fingerprint=row["input_fingerprint"],
                provenance_fingerprint=row["provenance_fingerprint"],
                metric_keys=cls._metrics(connection, row["job_id"]),
                estimator_plan_version=row["estimator_plan_version"],
                redactor_version=row["redactor_version"],
                provider_schema_version=row["provider_schema_version"],
                automation_grant_id=row["automation_grant_id"],
                local_only=bool(row["local_only"]),
            ),
            state=AnalysisJobState(row["state"]),
            stage_number=row["stage_number"],
            progress_completed=row["progress_completed"],
            progress_total=row["progress_total"],
            attempt_count=row["attempt_count"],
            max_attempts=row["max_attempts"],
            available_at=from_iso(row["available_at"]),
            cancel_requested=bool(row["cancel_requested"]),
            lease_owner=row["lease_owner"],
            lease_token=row["lease_token"],
            lease_expires_at=from_iso(row["lease_expires_at"]),
            last_error_code=row["last_error_code"],
            terminal_reason_code=row["terminal_reason_code"],
            created_at=from_iso(row["created_at"]),
            updated_at=from_iso(row["updated_at"]),
            terminal_at=from_iso(row["terminal_at"]),
        )

    @classmethod
    def _get_locked(
        cls,
        connection: sqlite3.Connection,
        job_id: str,
    ) -> AnalysisJobRecord | None:
        row = connection.execute(
            "SELECT * FROM analysis_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return None if row is None else cls._record(connection, row)

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset cannot be negative")

    @staticmethod
    def _validate_lease_duration(value: timedelta) -> timedelta:
        if not timedelta(seconds=5) <= value <= timedelta(minutes=10):
            raise ValueError("lease duration must be between five seconds and ten minutes")
        return value

    @staticmethod
    def _validate_progress(completed: int, total: int) -> None:
        if (
            isinstance(completed, bool)
            or not isinstance(completed, int)
            or isinstance(total, bool)
            or not isinstance(total, int)
            or not 0 <= completed <= total <= 1_000_000
            or total < 1
        ):
            raise ValueError("job progress is outside the reviewed bound")

    def enqueue(self, draft: AnalysisJobDraft) -> AnalysisJobEnqueueResult:
        self._ensure_initialized()
        if draft.identity.kind is AnalysisJobKind.ESTIMATOR_EXECUTION:
            raise DatabaseInvariantError(
                "estimator execution requires the atomic runtime launch boundary"
            )
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing_row = connection.execute(
                    "SELECT * FROM analysis_jobs WHERE dedupe_key = ?",
                    (draft.dedupe_key,),
                ).fetchone()
                if existing_row is not None:
                    existing = self._record(connection, existing_row)
                    if (
                        existing.job_id != draft.job_id
                        or existing.identity != draft.identity
                        or existing.max_attempts != draft.max_attempts
                    ):
                        raise DatabaseInvariantError(
                            "analysis job deduplication identity conflicted"
                        )
                    connection.commit()
                    return AnalysisJobEnqueueResult(job=existing, created=False)

                target = connection.execute(
                    """
                    SELECT s.project_id, s.provider
                    FROM sessions s WHERE s.session_id = ?
                    """,
                    (draft.identity.session_id,),
                ).fetchone()
                if target is None:
                    raise DatabaseInvariantError("analysis job session does not exist")
                if (
                    target["project_id"] != draft.identity.project_id
                    or target["provider"] != draft.identity.provider.value
                ):
                    raise DatabaseInvariantError(
                        "analysis job target provenance does not match the safe index"
                    )
                identity = draft.identity
                timestamp = to_iso(draft.created_at)
                connection.execute(
                    """
                    INSERT INTO analysis_jobs(
                        job_id, dedupe_key, kind, provider, project_id, session_id,
                        input_fingerprint, provenance_fingerprint,
                        estimator_plan_version, redactor_version,
                        provider_schema_version, automation_grant_id, local_only,
                        state, stage_number,
                        progress_completed, progress_total, attempt_count,
                        max_attempts, available_at, cancel_requested, lease_owner,
                        lease_token, lease_expires_at, last_error_code,
                        terminal_reason_code, created_at, updated_at, terminal_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'queued', NULL,
                        0, 1, 0, ?, ?, 0, NULL, NULL, NULL, NULL, NULL, ?, ?, NULL
                    )
                    """,
                    (
                        draft.job_id,
                        draft.dedupe_key,
                        identity.kind.value,
                        identity.provider.value,
                        identity.project_id,
                        identity.session_id,
                        identity.input_fingerprint,
                        identity.provenance_fingerprint,
                        identity.estimator_plan_version,
                        identity.redactor_version,
                        identity.provider_schema_version,
                        identity.automation_grant_id,
                        draft.max_attempts,
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO analysis_job_metrics(job_id, metric_key, ordinal)
                    VALUES (?, ?, ?)
                    """,
                    (
                        (draft.job_id, metric_key, ordinal)
                        for ordinal, metric_key in enumerate(identity.metric_keys)
                    ),
                )
                created = self._get_locked(connection, draft.job_id)
                if created is None:
                    raise DatabaseInvariantError("analysis job enqueue failed")
                connection.commit()
                return AnalysisJobEnqueueResult(job=created, created=True)
            except Exception:
                connection.rollback()
                raise

    def get(self, job_id: str) -> AnalysisJobRecord | None:
        self._ensure_initialized()
        require_safe_id(job_id)
        with self._connection_scope(readonly=True) as connection:
            return self._get_locked(connection, job_id)

    def list(
        self,
        *,
        state: AnalysisJobState | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> AnalysisJobPage:
        self._ensure_initialized()
        self._validate_page(limit, offset)
        with self._connection_scope(readonly=True) as connection:
            if state is None:
                rows = connection.execute(
                    """
                    SELECT * FROM analysis_jobs
                    ORDER BY created_at DESC, job_id DESC LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM analysis_jobs WHERE state = ?
                    ORDER BY created_at DESC, job_id DESC LIMIT ? OFFSET ?
                    """,
                    (state.value, limit, offset),
                ).fetchall()
            jobs = tuple(self._record(connection, row) for row in rows)
        return AnalysisJobPage(jobs=jobs, limit=limit, offset=offset)

    def list_active(self, *, limit: int = 100) -> AnalysisJobPage:
        self._ensure_initialized()
        self._validate_page(limit, 0)
        with self._connection_scope(readonly=True) as connection:
            rows = connection.execute(
                """
                SELECT * FROM analysis_jobs
                WHERE state NOT IN (
                    'completed', 'partial', 'failed', 'cancelled', 'superseded'
                )
                ORDER BY created_at, job_id LIMIT ?
                """,
                (limit,),
            ).fetchall()
            jobs = tuple(self._record(connection, row) for row in rows)
        return AnalysisJobPage(jobs=jobs, limit=limit, offset=0)

    def get_latest_for_session(self, session_id: str) -> AnalysisJobRecord | None:
        self._ensure_initialized()
        require_safe_id(session_id)
        with self._connection_scope(readonly=True) as connection:
            row = connection.execute(
                """
                SELECT * FROM analysis_jobs WHERE session_id = ?
                ORDER BY created_at DESC, job_id DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            return None if row is None else self._record(connection, row)

    def _recover_expired_locked(
        self,
        connection: sqlite3.Connection,
        *,
        now: datetime,
    ) -> AnalysisJobRecoveryResult:
        timestamp = to_iso(now)
        rows = connection.execute(
            """
            SELECT job_id, attempt_count, max_attempts, cancel_requested,
                   last_error_code
            FROM analysis_jobs
            WHERE state IN ('preprocessing', 'stage_n')
              AND kind <> 'estimator_execution'
              AND lease_expires_at <= ?
            ORDER BY lease_expires_at, job_id
            """,
            (timestamp,),
        ).fetchall()
        requeued = cancelled = failed = superseded = 0
        for row in rows:
            if bool(row["cancel_requested"]):
                reason = row["last_error_code"] or "cancellation_requested"
                state = (
                    AnalysisJobState.SUPERSEDED
                    if reason in {"input_changed", "provenance_changed"}
                    else AnalysisJobState.CANCELLED
                )
                terminal_at = timestamp
                available_at = timestamp
                if state is AnalysisJobState.CANCELLED:
                    cancelled += 1
                else:
                    superseded += 1
            elif row["attempt_count"] >= row["max_attempts"]:
                state = AnalysisJobState.FAILED
                reason = "lease_expired"
                terminal_at = timestamp
                available_at = timestamp
                failed += 1
            else:
                state = AnalysisJobState.QUEUED
                reason = None
                terminal_at = None
                available_at = to_iso(
                    now + self._retry_delay(int(row["attempt_count"]))
                )
                requeued += 1
            connection.execute(
                """
                UPDATE analysis_jobs SET
                    state = ?, stage_number = NULL, available_at = ?,
                    lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, last_error_code = 'lease_expired',
                    terminal_reason_code = ?, terminal_at = ?, updated_at = ?
                WHERE job_id = ? AND state IN ('preprocessing', 'stage_n')
                """,
                (
                    state.value,
                    available_at,
                    reason,
                    terminal_at,
                    timestamp,
                    row["job_id"],
                ),
            )
        return AnalysisJobRecoveryResult(
            requeued=requeued,
            cancelled=cancelled,
            failed=failed,
            superseded=superseded,
        )

    @staticmethod
    def _reconcile_ineligible_automation_jobs_locked(
        connection: sqlite3.Connection,
        *,
        now: datetime,
    ) -> None:
        """Fail closed stale/unsupported non-runtime automation queue work.

        Estimator executions have a separate append-only runtime sealing
        boundary and are deliberately excluded from this generic maintenance.
        """

        timestamp = to_iso(now)
        metric_mismatch = """
            EXISTS (
              SELECT metric_key, ordinal FROM analysis_job_metrics
              WHERE job_id = analysis_jobs.job_id
              EXCEPT
              SELECT metric_key, ordinal FROM automation_grant_metrics
              WHERE grant_id = analysis_jobs.automation_grant_id
            )
            OR EXISTS (
              SELECT metric_key, ordinal FROM automation_grant_metrics
              WHERE grant_id = analysis_jobs.automation_grant_id
              EXCEPT
              SELECT metric_key, ordinal FROM analysis_job_metrics
              WHERE job_id = analysis_jobs.job_id
            )
        """
        reasons_and_conditions = (
            (
                "automation_grant_not_found",
                "NOT EXISTS (SELECT 1 FROM automation_grants AS grant "
                "WHERE grant.grant_id = analysis_jobs.automation_grant_id)",
                (),
            ),
            (
                "automation_grant_inactive",
                "EXISTS (SELECT 1 FROM automation_grants AS grant "
                "WHERE grant.grant_id = analysis_jobs.automation_grant_id "
                "AND grant.state = 'revoked')",
                (),
            ),
            (
                "automation_grant_expired",
                "EXISTS (SELECT 1 FROM automation_grants AS grant "
                "WHERE grant.grant_id = analysis_jobs.automation_grant_id "
                "AND (grant.state = 'expired' OR (grant.state = 'active' "
                "AND grant.expires_at <= ?)))",
                (timestamp,),
            ),
            (
                "automation_resource_policy_unsupported",
                "EXISTS (SELECT 1 FROM automation_grants AS grant "
                "WHERE grant.grant_id = analysis_jobs.automation_grant_id "
                "AND grant.state = 'active' AND grant.expires_at > ? AND ("
                "grant.route <> 'balanced' OR grant.max_gpu_workers <> 1 OR "
                "grant.max_cpu_workers <> 1 OR grant.pause_on_battery <> 1 OR "
                "grant.maximum_session_seconds <> 1800))",
                (timestamp,),
            ),
            (
                "automation_grant_scope_mismatch",
                "EXISTS (SELECT 1 FROM automation_grants AS grant "
                "WHERE grant.grant_id = analysis_jobs.automation_grant_id "
                "AND grant.state = 'active' AND grant.expires_at > ? "
                "AND grant.route = 'balanced' AND grant.max_gpu_workers = 1 "
                "AND grant.max_cpu_workers = 1 AND grant.pause_on_battery = 1 "
                "AND grant.maximum_session_seconds = 1800 AND ("
                "analysis_jobs.kind <> 'session_quality' OR "
                "grant.local_only <> 1 OR "
                "grant.remote_requires_fresh_approval <> 1 OR "
                "grant.provider <> analysis_jobs.provider OR "
                "grant.project_id <> analysis_jobs.project_id OR "
                f"{metric_mismatch}))",
                (timestamp,),
            ),
        )
        for reason, condition, parameters in reasons_and_conditions:
            connection.execute(
                f"""
                UPDATE analysis_jobs SET
                    state = 'cancelled', stage_number = NULL,
                    cancel_requested = 1, last_error_code = ?,
                    terminal_reason_code = ?, terminal_at = ?, updated_at = ?
                WHERE automation_grant_id IS NOT NULL
                  AND kind <> 'estimator_execution'
                  AND state IN ('queued', 'awaiting_approval')
                  AND ({condition})
                """,
                (reason, reason, timestamp, timestamp, *parameters),
            )
            connection.execute(
                f"""
                UPDATE analysis_jobs SET
                    cancel_requested = 1, last_error_code = ?, updated_at = ?
                WHERE automation_grant_id IS NOT NULL
                  AND kind <> 'estimator_execution'
                  AND state IN ('preprocessing', 'stage_n')
                  AND ({condition})
                """,
                (reason, timestamp, *parameters),
            )

    def recover_expired(self, *, now: datetime) -> AnalysisJobRecoveryResult:
        self._ensure_initialized()
        now = require_utc(now)
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                result = self._recover_expired_locked(connection, now=now)
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def claim_next(
        self,
        *,
        owner: str,
        token: str,
        now: datetime,
        lease_duration: timedelta,
        power_source: PowerSourceState = PowerSourceState.UNKNOWN,
    ) -> AnalysisJobRecord | None:
        self._ensure_initialized()
        require_safe_id(owner)
        require_safe_id(token)
        now = require_utc(now)
        lease_duration = self._validate_lease_duration(lease_duration)
        if not isinstance(power_source, PowerSourceState):
            raise ValueError("power source state is invalid")
        timestamp = to_iso(now)
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._recover_expired_locked(connection, now=now)
                self._reconcile_ineligible_automation_jobs_locked(
                    connection,
                    now=now,
                )
                row = connection.execute(
                    """
                    SELECT queued.job_id
                    FROM analysis_jobs AS queued
                    LEFT JOIN automation_grants AS grant
                      ON grant.grant_id = queued.automation_grant_id
                    WHERE queued.state = 'queued'
                      AND queued.cancel_requested = 0
                      AND queued.available_at <= ?
                      AND (
                        queued.automation_grant_id IS NULL
                        OR (
                          grant.state = 'active'
                          AND grant.expires_at > ?
                          AND grant.route = 'balanced'
                          AND grant.max_gpu_workers = 1
                          AND grant.max_cpu_workers = 1
                          AND grant.pause_on_battery = 1
                          AND grant.maximum_session_seconds = 1800
                          AND grant.local_only = 1
                          AND grant.remote_requires_fresh_approval = 1
                          AND queued.kind IN (
                            'session_quality', 'estimator_execution'
                          )
                          AND grant.provider = queued.provider
                          AND grant.project_id = queued.project_id
                          AND NOT EXISTS (
                            SELECT metric_key, ordinal
                            FROM analysis_job_metrics
                            WHERE job_id = queued.job_id
                            EXCEPT
                            SELECT metric_key, ordinal
                            FROM automation_grant_metrics
                            WHERE grant_id = grant.grant_id
                          )
                          AND NOT EXISTS (
                            SELECT metric_key, ordinal
                            FROM automation_grant_metrics
                            WHERE grant_id = grant.grant_id
                            EXCEPT
                            SELECT metric_key, ordinal
                            FROM analysis_job_metrics
                            WHERE job_id = queued.job_id
                          )
                          AND ? = 'external_power'
                        )
                      )
                      AND (
                        queued.automation_grant_id IS NULL
                        OR NOT EXISTS (
                          SELECT 1 FROM analysis_jobs AS active
                          WHERE active.automation_grant_id =
                                queued.automation_grant_id
                            AND active.state IN ('preprocessing', 'stage_n')
                            AND active.lease_expires_at > ?
                        )
                      )
                    ORDER BY queued.available_at, queued.created_at,
                             queued.job_id
                    LIMIT 1
                    """,
                    (timestamp, timestamp, power_source.value, timestamp),
                ).fetchone()
                if row is None:
                    connection.commit()
                    return None
                expires_at = now + lease_duration
                cursor = connection.execute(
                    """
                    UPDATE analysis_jobs SET
                        state = 'preprocessing', stage_number = NULL,
                        attempt_count = attempt_count + 1,
                        lease_owner = ?, lease_token = ?, lease_expires_at = ?,
                        updated_at = ?, terminal_reason_code = NULL,
                        terminal_at = NULL
                    WHERE job_id = ? AND state = 'queued'
                      AND cancel_requested = 0 AND available_at <= ?
                    """,
                    (
                        owner,
                        token,
                        to_iso(expires_at),
                        timestamp,
                        row["job_id"],
                        timestamp,
                    ),
                )
                if cursor.rowcount != 1:
                    raise DatabaseInvariantError("analysis job claim conflicted")
                claimed = self._get_locked(connection, row["job_id"])
                if claimed is None:
                    raise DatabaseInvariantError("claimed analysis job disappeared")
                connection.commit()
                return claimed
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _active_row_for_lease(
        connection: sqlite3.Connection,
        lease: AnalysisJobLease,
        now: datetime,
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT * FROM analysis_jobs
            WHERE job_id = ? AND lease_owner = ? AND lease_token = ?
              AND state IN ('preprocessing', 'stage_n')
              AND lease_expires_at > ?
            """,
            (lease.job_id, lease.owner, lease.token, to_iso(now)),
        ).fetchone()
        if row is None:
            raise DatabaseInvariantError("analysis job lease is unavailable")
        return row

    def renew(
        self,
        lease: AnalysisJobLease,
        *,
        now: datetime,
        lease_duration: timedelta,
    ) -> AnalysisJobRecord:
        self._ensure_initialized()
        now = require_utc(now)
        lease_duration = self._validate_lease_duration(lease_duration)
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._active_row_for_lease(connection, lease, now)
                connection.execute(
                    """
                    UPDATE analysis_jobs SET lease_expires_at = ?, updated_at = ?
                    WHERE job_id = ? AND lease_owner = ? AND lease_token = ?
                    """,
                    (
                        to_iso(now + lease_duration),
                        to_iso(now),
                        lease.job_id,
                        lease.owner,
                        lease.token,
                    ),
                )
                renewed = self._get_locked(connection, lease.job_id)
                if renewed is None:
                    raise DatabaseInvariantError("analysis job renewal failed")
                connection.commit()
                return renewed
            except Exception:
                connection.rollback()
                raise

    def advance_stage(
        self,
        lease: AnalysisJobLease,
        *,
        now: datetime,
        stage_number: int,
        progress_completed: int,
        progress_total: int,
    ) -> AnalysisJobRecord:
        self._ensure_initialized()
        now = require_utc(now)
        self._validate_progress(progress_completed, progress_total)
        if isinstance(stage_number, bool) or not isinstance(stage_number, int):
            raise ValueError("stage number is invalid")
        if not 1 <= stage_number <= 32:
            raise ValueError("stage number is outside the reviewed bound")
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._active_row_for_lease(connection, lease, now)
                previous = row["stage_number"]
                if previous is not None and stage_number < previous:
                    raise DatabaseInvariantError("analysis job stage cannot move backward")
                connection.execute(
                    """
                    UPDATE analysis_jobs SET
                        state = 'stage_n', stage_number = ?,
                        progress_completed = ?, progress_total = ?, updated_at = ?
                    WHERE job_id = ? AND lease_owner = ? AND lease_token = ?
                    """,
                    (
                        stage_number,
                        progress_completed,
                        progress_total,
                        to_iso(now),
                        lease.job_id,
                        lease.owner,
                        lease.token,
                    ),
                )
                updated = self._get_locked(connection, lease.job_id)
                if updated is None:
                    raise DatabaseInvariantError("analysis job stage update failed")
                connection.commit()
                return updated
            except Exception:
                connection.rollback()
                raise

    def await_approval(
        self,
        lease: AnalysisJobLease,
        *,
        now: datetime,
        reason_code: str,
        progress_completed: int,
        progress_total: int,
    ) -> AnalysisJobRecord:
        self._ensure_initialized()
        now = require_utc(now)
        require_safe_label(reason_code)
        self._validate_progress(progress_completed, progress_total)
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._active_row_for_lease(connection, lease, now)
                connection.execute(
                    """
                    UPDATE analysis_jobs SET
                        state = 'awaiting_approval', stage_number = NULL,
                        progress_completed = ?, progress_total = ?,
                        lease_owner = NULL, lease_token = NULL,
                        lease_expires_at = NULL, last_error_code = ?, updated_at = ?
                    WHERE job_id = ? AND lease_owner = ? AND lease_token = ?
                    """,
                    (
                        progress_completed,
                        progress_total,
                        reason_code,
                        to_iso(now),
                        lease.job_id,
                        lease.owner,
                        lease.token,
                    ),
                )
                updated = self._get_locked(connection, lease.job_id)
                if updated is None:
                    raise DatabaseInvariantError("analysis job approval wait failed")
                connection.commit()
                return updated
            except Exception:
                connection.rollback()
                raise

    def resume_after_approval(
        self,
        job_id: str,
        *,
        now: datetime,
    ) -> AnalysisJobRecord:
        self._ensure_initialized()
        require_safe_id(job_id)
        now = require_utc(now)
        timestamp = to_iso(now)
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._get_locked(connection, job_id)
                if current is None:
                    raise DatabaseInvariantError("analysis job does not exist")
                if current.identity.kind is AnalysisJobKind.ESTIMATOR_EXECUTION:
                    raise DatabaseInvariantError(
                        "estimator execution approval requires its runtime boundary"
                    )
                cursor = connection.execute(
                    """
                    UPDATE analysis_jobs SET
                        state = 'queued', available_at = ?,
                        last_error_code = NULL, updated_at = ?
                    WHERE job_id = ? AND state = 'awaiting_approval'
                      AND cancel_requested = 0
                    """,
                    (timestamp, timestamp, job_id),
                )
                if cursor.rowcount != 1:
                    raise DatabaseInvariantError(
                        "analysis job is not awaiting approval"
                    )
                updated = self._get_locked(connection, job_id)
                if updated is None:
                    raise DatabaseInvariantError("analysis job approval resume failed")
                connection.commit()
                return updated
            except Exception:
                connection.rollback()
                raise

    def request_cancel(self, job_id: str, *, now: datetime) -> AnalysisJobRecord:
        self._ensure_initialized()
        require_safe_id(job_id)
        now = require_utc(now)
        timestamp = to_iso(now)
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._get_locked(connection, job_id)
                if current is None:
                    raise DatabaseInvariantError("analysis job does not exist")
                if current.identity.kind is AnalysisJobKind.ESTIMATOR_EXECUTION:
                    raise DatabaseInvariantError(
                        "estimator execution cancellation requires its runtime boundary"
                    )
                if current.state in TERMINAL_ANALYSIS_JOB_STATES:
                    connection.commit()
                    return current
                if current.state in {
                    AnalysisJobState.QUEUED,
                    AnalysisJobState.AWAITING_APPROVAL,
                }:
                    connection.execute(
                        """
                        UPDATE analysis_jobs SET
                            state = 'cancelled', stage_number = NULL,
                            cancel_requested = 1, terminal_reason_code = ?,
                            terminal_at = ?, updated_at = ?
                        WHERE job_id = ?
                        """,
                        ("cancellation_requested", timestamp, timestamp, job_id),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE analysis_jobs SET cancel_requested = 1,
                            last_error_code = 'cancellation_requested', updated_at = ?
                        WHERE job_id = ?
                        """,
                        (timestamp, job_id),
                    )
                updated = self._get_locked(connection, job_id)
                if updated is None:
                    raise DatabaseInvariantError("analysis job cancellation failed")
                connection.commit()
                return updated
            except Exception:
                connection.rollback()
                raise

    def cancel_by_automation_grant(
        self,
        automation_grant_id: str,
        *,
        now: datetime,
    ) -> AnalysisJobCancellationBatchResult:
        self._ensure_initialized()
        require_safe_id(automation_grant_id)
        now = require_utc(now)
        reason_code = "automation_grant_revoked"
        timestamp = to_iso(now)
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute(
                    """
                    SELECT 1 FROM analysis_jobs
                    WHERE automation_grant_id=? AND kind='estimator_execution'
                      AND state NOT IN (
                          'completed','partial','failed','cancelled','superseded'
                      ) LIMIT 1
                    """,
                    (automation_grant_id,),
                ).fetchone() is not None:
                    raise DatabaseInvariantError(
                        "estimator execution grant revocation requires its runtime boundary"
                    )
                cancelled = connection.execute(
                    """
                    UPDATE analysis_jobs SET
                        state = 'cancelled', stage_number = NULL,
                        cancel_requested = 1,
                        last_error_code = ?,
                        terminal_reason_code = ?,
                        terminal_at = ?, updated_at = ?
                    WHERE automation_grant_id = ?
                      AND state IN ('queued', 'awaiting_approval')
                    """,
                    (
                        reason_code,
                        reason_code,
                        timestamp,
                        timestamp,
                        automation_grant_id,
                    ),
                ).rowcount
                requested = connection.execute(
                    """
                    UPDATE analysis_jobs SET
                        cancel_requested = 1,
                        last_error_code = ?,
                        updated_at = ?
                    WHERE automation_grant_id = ?
                      AND state IN ('preprocessing', 'stage_n')
                    """,
                    (reason_code, timestamp, automation_grant_id),
                ).rowcount
                connection.commit()
                return AnalysisJobCancellationBatchResult(
                    cancelled=cancelled,
                    cancellation_requested=requested,
                )
            except Exception:
                connection.rollback()
                raise

    def supersede(
        self,
        job_id: str,
        *,
        now: datetime,
        reason_code: str,
    ) -> AnalysisJobRecord:
        self._ensure_initialized()
        require_safe_id(job_id)
        now = require_utc(now)
        require_safe_label(reason_code)
        timestamp = to_iso(now)
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._get_locked(connection, job_id)
                if current is None:
                    raise DatabaseInvariantError("analysis job does not exist")
                if current.identity.kind is AnalysisJobKind.ESTIMATOR_EXECUTION:
                    raise DatabaseInvariantError(
                        "estimator execution supersession requires its runtime boundary"
                    )
                if current.state in TERMINAL_ANALYSIS_JOB_STATES:
                    connection.commit()
                    return current
                if current.state in {
                    AnalysisJobState.QUEUED,
                    AnalysisJobState.AWAITING_APPROVAL,
                }:
                    connection.execute(
                        """
                        UPDATE analysis_jobs SET
                            state = 'superseded', stage_number = NULL,
                            cancel_requested = 1, last_error_code = ?,
                            terminal_reason_code = ?, terminal_at = ?, updated_at = ?
                        WHERE job_id = ?
                        """,
                        (reason_code, reason_code, timestamp, timestamp, job_id),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE analysis_jobs SET cancel_requested = 1,
                            last_error_code = ?, updated_at = ? WHERE job_id = ?
                        """,
                        (reason_code, timestamp, job_id),
                    )
                updated = self._get_locked(connection, job_id)
                if updated is None:
                    raise DatabaseInvariantError("analysis job supersession failed")
                connection.commit()
                return updated
            except Exception:
                connection.rollback()
                raise

    def finish(
        self,
        lease: AnalysisJobLease,
        *,
        now: datetime,
        state: AnalysisJobState,
        reason_code: str,
        progress_completed: int,
        progress_total: int,
    ) -> AnalysisJobRecord:
        self._ensure_initialized()
        now = require_utc(now)
        require_safe_label(reason_code)
        self._validate_progress(progress_completed, progress_total)
        if state not in TERMINAL_ANALYSIS_JOB_STATES:
            raise ValueError("analysis job finish requires a terminal state")
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._active_row_for_lease(connection, lease, now)
                if bool(row["cancel_requested"]):
                    reason_code = row["last_error_code"] or "cancellation_requested"
                    state = (
                        AnalysisJobState.SUPERSEDED
                        if reason_code in {"input_changed", "provenance_changed"}
                        else AnalysisJobState.CANCELLED
                    )
                timestamp = to_iso(now)
                connection.execute(
                    """
                    UPDATE analysis_jobs SET
                        state = ?, stage_number = NULL,
                        progress_completed = ?, progress_total = ?,
                        lease_owner = NULL, lease_token = NULL,
                        lease_expires_at = NULL, terminal_reason_code = ?,
                        terminal_at = ?, updated_at = ?
                    WHERE job_id = ? AND lease_owner = ? AND lease_token = ?
                    """,
                    (
                        state.value,
                        progress_completed,
                        progress_total,
                        reason_code,
                        timestamp,
                        timestamp,
                        lease.job_id,
                        lease.owner,
                        lease.token,
                    ),
                )
                terminal = self._get_locked(connection, lease.job_id)
                if terminal is None:
                    raise DatabaseInvariantError("analysis job completion failed")
                connection.commit()
                return terminal
            except Exception:
                connection.rollback()
                raise

    def retry_or_fail(
        self,
        lease: AnalysisJobLease,
        *,
        now: datetime,
        error_code: str,
        retryable: bool,
    ) -> AnalysisJobRecord:
        self._ensure_initialized()
        now = require_utc(now)
        require_safe_label(error_code)
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._active_row_for_lease(connection, lease, now)
                timestamp = to_iso(now)
                if bool(row["cancel_requested"]):
                    reason = row["last_error_code"] or "cancellation_requested"
                    state = (
                        AnalysisJobState.SUPERSEDED
                        if reason in {"input_changed", "provenance_changed"}
                        else AnalysisJobState.CANCELLED
                    )
                    terminal_at = timestamp
                    available_at = timestamp
                elif retryable and row["attempt_count"] < row["max_attempts"]:
                    state = AnalysisJobState.QUEUED
                    reason = None
                    terminal_at = None
                    available_at = to_iso(
                        now + self._retry_delay(int(row["attempt_count"]))
                    )
                else:
                    state = AnalysisJobState.FAILED
                    reason = error_code
                    terminal_at = timestamp
                    available_at = timestamp
                connection.execute(
                    """
                    UPDATE analysis_jobs SET
                        state = ?, stage_number = NULL, available_at = ?,
                        lease_owner = NULL, lease_token = NULL,
                        lease_expires_at = NULL, last_error_code = ?,
                        terminal_reason_code = ?, terminal_at = ?, updated_at = ?
                    WHERE job_id = ? AND lease_owner = ? AND lease_token = ?
                    """,
                    (
                        state.value,
                        available_at,
                        error_code,
                        reason,
                        terminal_at,
                        timestamp,
                        lease.job_id,
                        lease.owner,
                        lease.token,
                    ),
                )
                updated = self._get_locked(connection, lease.job_id)
                if updated is None:
                    raise DatabaseInvariantError("analysis job retry transition failed")
                connection.commit()
                return updated
            except Exception:
                connection.rollback()
                raise
