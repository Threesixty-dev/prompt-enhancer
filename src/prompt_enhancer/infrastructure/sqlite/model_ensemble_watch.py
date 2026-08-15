"""SQLite persistence for the content-free continuous ensemble watch."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import hashlib

from ...application.analysis.model_ensemble_watch import (
    MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL,
    ModelEnsembleWatchLease,
    ModelEnsembleWatchRecord,
    ModelEnsembleWatchRepository,
    ModelEnsembleWatchState,
)
from ...application.analysis.session_model_ensemble import SessionModelEnsembleOutcome
from ...domain import Provider
from ._common import ConnectionScope, from_iso, require_safe_id, require_safe_label, to_iso


def _record(row: object) -> ModelEnsembleWatchRecord:
    return ModelEnsembleWatchRecord(
        watch_id=row["watch_id"],  # type: ignore[index]
        provider=Provider(row["provider"]),  # type: ignore[index]
        project_id=row["project_id"],  # type: ignore[index]
        session_id=row["session_id"],  # type: ignore[index]
        state=ModelEnsembleWatchState(row["state"]),  # type: ignore[index]
        generation=int(row["generation"]),  # type: ignore[index]
        progress_completed=int(row["progress_completed"]),  # type: ignore[index]
        progress_total=int(row["progress_total"]),  # type: ignore[index]
        latest_run_id=row["latest_run_id"],  # type: ignore[index]
        latest_input_fingerprint=row["latest_input_fingerprint"],  # type: ignore[index]
        last_error_code=row["last_error_code"],  # type: ignore[index]
        next_check_at=from_iso(row["next_check_at"]),  # type: ignore[index]
        lease_owner=row["lease_owner"],  # type: ignore[index]
        lease_token=row["lease_token"],  # type: ignore[index]
        lease_expires_at=(
            None
            if row["lease_expires_at"] is None  # type: ignore[index]
            else from_iso(row["lease_expires_at"])  # type: ignore[index]
        ),
        created_at=from_iso(row["created_at"]),  # type: ignore[index]
        updated_at=from_iso(row["updated_at"]),  # type: ignore[index]
    )


class SqliteModelEnsembleWatchRepository(ModelEnsembleWatchRepository):
    def __init__(
        self,
        connection_scope: ConnectionScope,
        ensure_initialized: Callable[[], None],
    ) -> None:
        self._connection_scope = connection_scope
        self._ensure_initialized = ensure_initialized

    @staticmethod
    def _row(connection: object, watch_id: str):
        return connection.execute(  # type: ignore[attr-defined]
            "SELECT * FROM session_model_ensemble_watches WHERE watch_id=?",
            (watch_id,),
        ).fetchone()

    def enable(
        self,
        *,
        watch_id: str,
        provider: Provider,
        project_id: str,
        session_id: str,
        now: datetime,
    ) -> ModelEnsembleWatchRecord:
        require_safe_id(watch_id)
        require_safe_id(project_id)
        require_safe_id(session_id)
        self._ensure_initialized()
        stamp = to_iso(now)
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                target = connection.execute(
                    """SELECT 1 FROM sessions s
                       JOIN projects p ON p.project_id=s.project_id
                       WHERE s.session_id=? AND s.project_id=?
                         AND s.provider=? AND p.provider=?""",
                    (session_id, project_id, provider.value, provider.value),
                ).fetchone()
                if target is None:
                    raise ValueError("watch target is outside the safe index")
                existing = self._row(connection, watch_id)
                if existing is not None and existing["state"] != "disabled":
                    connection.rollback()
                    return _record(existing)
                connection.execute(
                    """UPDATE session_model_ensemble_watches
                       SET state='disabled',lease_owner=NULL,lease_token=NULL,
                           lease_expires_at=NULL,updated_at=?
                       WHERE state<>'disabled' AND watch_id<>?""",
                    (stamp, watch_id),
                )
                if existing is None:
                    connection.execute(
                        """INSERT INTO session_model_ensemble_watches(
                           watch_id,provider,project_id,session_id,state,generation,
                           progress_completed,progress_total,latest_run_id,
                           latest_input_fingerprint,last_error_code,next_check_at,
                           lease_owner,lease_token,lease_expires_at,created_at,updated_at
                           ) VALUES(?,?,?,?,'queued',0,0,?,NULL,NULL,NULL,?,NULL,NULL,NULL,?,?)""",
                        (
                            watch_id,
                            provider.value,
                            project_id,
                            session_id,
                            MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL,
                            stamp,
                            stamp,
                            stamp,
                        ),
                    )
                else:
                    connection.execute(
                        """UPDATE session_model_ensemble_watches
                           SET state='queued',progress_completed=0,last_error_code=NULL,
                               next_check_at=?,lease_owner=NULL,lease_token=NULL,
                               lease_expires_at=NULL,updated_at=?
                           WHERE watch_id=?""",
                        (stamp, stamp, watch_id),
                    )
                row = self._row(connection, watch_id)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if row is None:
            raise RuntimeError("watch enable did not persist")
        return _record(row)

    def disable(self, watch_id: str, *, now: datetime) -> ModelEnsembleWatchRecord:
        require_safe_id(watch_id)
        self._ensure_initialized()
        stamp = to_iso(now)
        with self._connection_scope() as connection:
            connection.execute("BEGIN IMMEDIATE")
            result = connection.execute(
                """UPDATE session_model_ensemble_watches
                   SET state='disabled',lease_owner=NULL,lease_token=NULL,
                       lease_expires_at=NULL,updated_at=?
                   WHERE watch_id=?""",
                (stamp, watch_id),
            )
            if result.rowcount != 1:
                connection.rollback()
                raise ValueError("watch does not exist")
            row = self._row(connection, watch_id)
            connection.commit()
        return _record(row)

    def get(self, watch_id: str) -> ModelEnsembleWatchRecord | None:
        require_safe_id(watch_id)
        self._ensure_initialized()
        with self._connection_scope(readonly=True) as connection:
            row = self._row(connection, watch_id)
        return None if row is None else _record(row)

    def get_active(self) -> ModelEnsembleWatchRecord | None:
        self._ensure_initialized()
        with self._connection_scope(readonly=True) as connection:
            row = connection.execute(
                """SELECT * FROM session_model_ensemble_watches
                   WHERE state<>'disabled'
                   ORDER BY updated_at DESC,watch_id LIMIT 1"""
            ).fetchone()
        return None if row is None else _record(row)

    def claim_due(
        self,
        *,
        owner: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> tuple[ModelEnsembleWatchRecord, ModelEnsembleWatchLease] | None:
        require_safe_id(owner)
        self._ensure_initialized()
        stamp = to_iso(now)
        expires = now + lease_duration
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """UPDATE session_model_ensemble_watches
                       SET state='queued',lease_owner=NULL,lease_token=NULL,
                           lease_expires_at=NULL,last_error_code='watch_lease_recovered',
                           next_check_at=?,updated_at=?
                       WHERE state='running' AND lease_expires_at<=?""",
                    (stamp, stamp, stamp),
                )
                candidate = connection.execute(
                    """SELECT watch_id,generation
                       FROM session_model_ensemble_watches
                       WHERE state IN ('queued','idle','failed') AND next_check_at<=?
                       ORDER BY next_check_at,created_at,watch_id LIMIT 1""",
                    (stamp,),
                ).fetchone()
                if candidate is None:
                    connection.rollback()
                    return None
                generation = int(candidate["generation"]) + 1
                token = hashlib.sha256(
                    f"model-ensemble-watch-lease:{candidate['watch_id']}:{generation}:{stamp}".encode(
                        "ascii"
                    )
                ).hexdigest()
                connection.execute(
                    """UPDATE session_model_ensemble_watches
                       SET state='running',generation=?,progress_completed=0,
                           last_error_code=NULL,lease_owner=?,lease_token=?,
                           lease_expires_at=?,updated_at=? WHERE watch_id=?""",
                    (
                        generation,
                        owner,
                        token,
                        to_iso(expires),
                        stamp,
                        candidate["watch_id"],
                    ),
                )
                row = self._row(connection, candidate["watch_id"])
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        record = _record(row)
        return record, ModelEnsembleWatchLease(
            watch_id=record.watch_id,
            owner=owner,
            token=token,
            expires_at=expires,
        )

    def heartbeat(
        self,
        lease: ModelEnsembleWatchLease,
        *,
        now: datetime,
        lease_duration: timedelta,
        progress_completed: int,
    ) -> tuple[ModelEnsembleWatchRecord, ModelEnsembleWatchLease]:
        if not 0 <= progress_completed <= MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL:
            raise ValueError("watch progress is invalid")
        self._ensure_initialized()
        expires = now + lease_duration
        with self._connection_scope() as connection:
            connection.execute("BEGIN IMMEDIATE")
            result = connection.execute(
                """UPDATE session_model_ensemble_watches
                   SET progress_completed=?,lease_expires_at=?,updated_at=?
                   WHERE watch_id=? AND state='running' AND lease_owner=?
                     AND lease_token=? AND lease_expires_at>?""",
                (
                    progress_completed,
                    to_iso(expires),
                    to_iso(now),
                    lease.watch_id,
                    lease.owner,
                    lease.token,
                    to_iso(now),
                ),
            )
            if result.rowcount != 1:
                connection.rollback()
                raise ValueError("watch lease is no longer active")
            row = self._row(connection, lease.watch_id)
            connection.commit()
        record = _record(row)
        return record, ModelEnsembleWatchLease(
            watch_id=lease.watch_id,
            owner=lease.owner,
            token=lease.token,
            expires_at=expires,
        )

    def complete(
        self,
        lease: ModelEnsembleWatchLease,
        *,
        now: datetime,
        next_check_at: datetime,
        outcome: SessionModelEnsembleOutcome,
    ) -> ModelEnsembleWatchRecord:
        self._ensure_initialized()
        run = outcome.run
        with self._connection_scope() as connection:
            connection.execute("BEGIN IMMEDIATE")
            result = connection.execute(
                """UPDATE session_model_ensemble_watches
                   SET state='idle',progress_completed=?,latest_run_id=?,
                       latest_input_fingerprint=?,last_error_code=NULL,next_check_at=?,
                       lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,updated_at=?
                   WHERE watch_id=? AND state='running' AND lease_owner=?
                     AND lease_token=? AND lease_expires_at>? AND session_id=?""",
                (
                    MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL,
                    run.run_id,
                    run.input_fingerprint,
                    to_iso(next_check_at),
                    to_iso(now),
                    lease.watch_id,
                    lease.owner,
                    lease.token,
                    to_iso(now),
                    run.session_id,
                ),
            )
            if result.rowcount != 1:
                connection.rollback()
                raise ValueError("watch lease is no longer active")
            row = self._row(connection, lease.watch_id)
            connection.commit()
        return _record(row)

    def fail(
        self,
        lease: ModelEnsembleWatchLease,
        *,
        now: datetime,
        next_check_at: datetime,
        reason_code: str,
    ) -> ModelEnsembleWatchRecord:
        require_safe_label(reason_code)
        self._ensure_initialized()
        with self._connection_scope() as connection:
            connection.execute("BEGIN IMMEDIATE")
            result = connection.execute(
                """UPDATE session_model_ensemble_watches
                   SET state='failed',last_error_code=?,next_check_at=?,
                       lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,updated_at=?
                   WHERE watch_id=? AND state='running' AND lease_owner=?
                     AND lease_token=? AND lease_expires_at>?""",
                (
                    reason_code,
                    to_iso(next_check_at),
                    to_iso(now),
                    lease.watch_id,
                    lease.owner,
                    lease.token,
                    to_iso(now),
                ),
            )
            if result.rowcount != 1:
                connection.rollback()
                raise ValueError("watch lease is no longer active")
            row = self._row(connection, lease.watch_id)
            connection.commit()
        return _record(row)


__all__ = ["SqliteModelEnsembleWatchRepository"]
