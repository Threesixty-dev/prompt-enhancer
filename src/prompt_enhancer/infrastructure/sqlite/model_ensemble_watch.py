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
    ModelEnsembleTrajectoryPage,
    ModelEnsembleTrajectoryPoint,
)
from ...application.analysis.model_ensemble import (
    MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION,
    SessionModelEnsembleMetricReceipt,
    SessionModelEnsembleTypedMetricReceipt,
    SourceCoverageState,
)
from ...application.analysis.session_model_ensemble import SessionModelEnsembleOutcome
from ...application.analysis.probabilistic_metrics import (
    PROBABILISTIC_METRIC_PROJECTION_VERSION,
    PredictiveMetricState,
    PredictiveMetricTarget,
    SessionPredictiveMetricSummary,
)
from ...application.persistence import MetricValueState
from ...domain import Provider
from ._common import ConnectionScope, from_iso, require_safe_id, require_safe_label, to_iso


def _record(row: object) -> ModelEnsembleWatchRecord:
    return ModelEnsembleWatchRecord(
        watch_id=row["watch_id"],  # type: ignore[index]
        provider=Provider(row["provider"]),  # type: ignore[index]
        project_id=row["project_id"],  # type: ignore[index]
        session_id=row["session_id"],  # type: ignore[index]
        max_messages=int(row["max_messages"]),  # type: ignore[index]
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


def _predictive_identity(connection, run_id: str | None) -> tuple[object, ...] | None:
    if run_id is None:
        return None
    seal = connection.execute(
        """SELECT projection_version,registry_version,model_set_version,sample_count
           FROM session_model_ensemble_predictive_metric_seals
           WHERE run_id=? AND projection_version=?""",
        (run_id, PROBABILISTIC_METRIC_PROJECTION_VERSION),
    ).fetchone()
    if seal is None:
        return None
    metrics = tuple(
        (
            item["metric_key"],
            item["target"],
            item["model_set_version"],
            item["calibration_version"],
            item["contract_version"],
            item["contract_fingerprint"],
        )
        for item in connection.execute(
            """SELECT metric_key,target,model_set_version,calibration_version,
                      contract_version,contract_fingerprint
               FROM session_model_ensemble_predictive_metrics
               WHERE run_id=? AND projection_version=? ORDER BY metric_key""",
            (run_id, PROBABILISTIC_METRIC_PROJECTION_VERSION),
        ).fetchall()
    )
    stages = tuple(
        (
            item["model_key"],
            item["revision"],
            item["quantization"],
        )
        for item in connection.execute(
            """SELECT model_key,revision,quantization
               FROM session_model_ensemble_predictive_model_stages
               WHERE run_id=? AND projection_version=? ORDER BY stage_ordinal""",
            (run_id, PROBABILISTIC_METRIC_PROJECTION_VERSION),
        ).fetchall()
    )
    return (
        seal["projection_version"],
        seal["registry_version"],
        seal["model_set_version"],
        int(seal["sample_count"]),
        metrics,
        stages,
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
        max_messages: int = 100,
        now: datetime,
    ) -> ModelEnsembleWatchRecord:
        require_safe_id(watch_id)
        require_safe_id(project_id)
        require_safe_id(session_id)
        if (
            not isinstance(max_messages, int)
            or isinstance(max_messages, bool)
            or not 1 <= max_messages <= 100
        ):
            raise ValueError("watch message window is invalid")
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
                if (
                    existing is not None
                    and existing["state"] != "disabled"
                    and int(existing["max_messages"]) == max_messages
                ):
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
                           watch_id,provider,project_id,session_id,max_messages,state,generation,
                           progress_completed,progress_total,latest_run_id,
                           latest_input_fingerprint,last_error_code,next_check_at,
                           lease_owner,lease_token,lease_expires_at,created_at,updated_at
                           ) VALUES(?,?,?,?,?,'queued',0,0,?,NULL,NULL,NULL,?,NULL,NULL,NULL,?,?)""",
                        (
                            watch_id,
                            provider.value,
                            project_id,
                            session_id,
                            max_messages,
                            MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL,
                            stamp,
                            stamp,
                            stamp,
                        ),
                    )
                else:
                    if existing["state"] != "disabled":
                        connection.execute(
                            """UPDATE session_model_ensemble_watches
                               SET state='disabled',lease_owner=NULL,lease_token=NULL,
                                   lease_expires_at=NULL,updated_at=? WHERE watch_id=?""",
                            (stamp, watch_id),
                        )
                    connection.execute(
                        """UPDATE session_model_ensemble_watches
                           SET state='queued',max_messages=?,progress_completed=0,
                               latest_run_id=NULL,latest_input_fingerprint=NULL,last_error_code=NULL,
                               next_check_at=?,lease_owner=NULL,lease_token=NULL,
                               lease_expires_at=NULL,updated_at=?
                           WHERE watch_id=?""",
                        (max_messages, stamp, stamp, watch_id),
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

    def request_refresh(
        self,
        watch_id: str,
        *,
        now: datetime,
    ) -> ModelEnsembleWatchRecord:
        require_safe_id(watch_id)
        self._ensure_initialized()
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._row(connection, watch_id)
                if current is None or current["state"] == "disabled":
                    raise ValueError("watch does not exist")
                # A refresh is an admission request, not cancellation.  Never
                # revoke an active model subprocess lease: the worker cannot
                # safely pre-empt an in-flight local inference call, and doing
                # so only turns a healthy run into a restart loop.
                if current["state"] == "running":
                    connection.rollback()
                    return _record(current)
                connection.execute(
                    """UPDATE session_model_ensemble_watches
                       SET state='queued',progress_completed=0,
                           last_error_code=CASE WHEN state='failed'
                               THEN last_error_code ELSE NULL END,next_check_at=?,
                           lease_owner=NULL,lease_token=NULL,
                           lease_expires_at=NULL,updated_at=?
                       WHERE watch_id=?""",
                    (to_iso(now), to_iso(now), watch_id),
                )
                row = self._row(connection, watch_id)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if row is None:
            raise ValueError("watch does not exist")
        return _record(row)

    def list_publications(
        self,
        watch_id: str,
        *,
        before_generation: int | None,
        limit: int,
    ) -> ModelEnsembleTrajectoryPage:
        require_safe_id(watch_id)
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 60
            or (
                before_generation is not None
                and (
                    not isinstance(before_generation, int)
                    or isinstance(before_generation, bool)
                    or not 1 <= before_generation <= 1_000_000_000
                )
            )
        ):
            raise ValueError("trajectory page is invalid")
        self._ensure_initialized()
        with self._connection_scope(readonly=True) as connection:
            watch = connection.execute(
                """SELECT w.latest_run_id,p.generation AS head_generation,
                          p.max_messages AS head_max_messages,
                          r.plan_fingerprint AS head_plan,
                          r.provider_version AS head_provider_version,
                          r.adapter_version AS head_adapter_version,
                          r.source_schema_version AS head_source_schema_version,
                          r.content_schema_version AS head_content_schema_version,
                          r.redactor_version AS head_redactor_version,
                          typed.projection_version AS head_projection_version,
                          predictive.projection_version AS head_predictive_version
                   FROM session_model_ensemble_watches w
                   LEFT JOIN session_model_ensemble_watch_publications p
                     ON p.watch_id=w.watch_id AND p.run_id=w.latest_run_id
                   LEFT JOIN session_model_ensemble_runs r ON r.run_id=p.run_id
                   LEFT JOIN session_model_ensemble_typed_metric_seals typed
                     ON typed.run_id=r.run_id
                    AND typed.projection_version=?
                   LEFT JOIN session_model_ensemble_predictive_metric_seals predictive
                     ON predictive.run_id=r.run_id
                    AND predictive.projection_version='local-probabilistic-radar-v1'
                   WHERE w.watch_id=?""",
                (MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION, watch_id),
            ).fetchone()
            if watch is None:
                raise ValueError("watch does not exist")
            parameters: list[object] = [watch_id]
            cursor = ""
            if before_generation is not None:
                cursor = " AND p.generation<?"
                parameters.append(before_generation)
            parameters.append(limit + 1)
            rows = connection.execute(
                f"""SELECT p.generation,p.run_id,p.max_messages,p.published_at,
                           r.completed_at,r.source_coverage_state,r.chunk_count,
                           r.plan_fingerprint,r.provider_version,r.adapter_version,
                           r.source_schema_version,r.content_schema_version,
                           r.redactor_version,typed.projection_version,
                           typed.projected_at,
                           predictive.projection_version AS predictive_projection_version
                    FROM session_model_ensemble_watch_publications p
                    JOIN session_model_ensemble_runs r ON r.run_id=p.run_id
                    JOIN session_model_ensemble_seals s ON s.run_id=r.run_id
                    LEFT JOIN session_model_ensemble_typed_metric_seals typed
                      ON typed.run_id=r.run_id
                     AND typed.projection_version='{MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION}'
                    LEFT JOIN session_model_ensemble_predictive_metric_seals predictive
                      ON predictive.run_id=r.run_id
                     AND predictive.projection_version='{PROBABILISTIC_METRIC_PROJECTION_VERSION}'
                    WHERE p.watch_id=?{cursor}
                    ORDER BY p.generation DESC LIMIT ?""",
                tuple(parameters),
            ).fetchall()
            has_more = len(rows) > limit
            rows = rows[:limit]
            points = []
            head_predictive_identity = _predictive_identity(
                connection, watch["latest_run_id"]
            )
            for row in rows:
                metric_rows = connection.execute(
                    """SELECT * FROM session_model_ensemble_metrics
                       WHERE run_id=? ORDER BY metric_key""",
                    (row["run_id"],),
                ).fetchall()
                metrics = tuple(
                    SessionModelEnsembleMetricReceipt(
                        metric_key=item["metric_key"],
                        value_state=MetricValueState(item["value_state"]),
                        numerator=item["numerator"],
                        denominator=item["denominator"],
                        numeric_value=item["numeric_value"],
                        known_chunk_count=item["known_chunk_count"],
                        abstained_chunk_count=item["abstained_chunk_count"],
                        unsupported_chunk_count=item["unsupported_chunk_count"],
                        failed_chunk_count=item["failed_chunk_count"],
                        total_chunk_count=item["total_chunk_count"],
                        explanation_code=item["explanation_code"],
                    )
                    for item in metric_rows
                )
                typed_metrics = tuple(
                    SessionModelEnsembleTypedMetricReceipt(
                        metric_key=item["metric_key"],
                        metric_version=item["metric_version"],
                        value_state=MetricValueState(item["value_state"]),
                        numerator=item["numerator"],
                        denominator=item["denominator"],
                        numeric_value=item["numeric_value"],
                        observed_message_count=item["observed_message_count"],
                        eligible_message_count=item["eligible_message_count"],
                        coverage=item["coverage"],
                        explanation_code=item["explanation_code"],
                        error_code=item["error_code"],
                        projection_source=item["projection_source"],
                        metric_schema_version=item["metric_schema_version"],
                        engine_version=item["engine_version"],
                        algorithm_id=item["algorithm_id"],
                        algorithm_version=item["algorithm_version"],
                        rubric_version=item["rubric_version"],
                        calibration_state=item["calibration_state"],
                        product_metric_eligible=bool(
                            item["product_metric_eligible"]
                        ),
                    )
                    for item in connection.execute(
                        """SELECT * FROM session_model_ensemble_typed_metrics
                           WHERE run_id=? AND projection_version=?
                           ORDER BY metric_key""",
                        (
                            row["run_id"],
                            MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION,
                        ),
                    ).fetchall()
                )
                predictive_metrics = tuple(
                    SessionPredictiveMetricSummary(
                        metric_key=item["metric_key"],
                        target=PredictiveMetricTarget(item["target"]),
                        state=PredictiveMetricState(item["state"]),
                        mean=item["mean"],
                        median=item["median"],
                        q05=item["q05"],
                        q25=item["q25"],
                        q75=item["q75"],
                        q95=item["q95"],
                        applicability_probability=item[
                            "applicability_probability"
                        ],
                        pending_probability=item["pending_probability"],
                        model_disagreement=item["model_disagreement"],
                        effective_observation_count=item[
                            "effective_observation_count"
                        ],
                        model_set_version=item["model_set_version"],
                        calibration_version=item["calibration_version"],
                        contract_version=item["contract_version"],
                        contract_fingerprint=item["contract_fingerprint"],
                        product_metric_eligible=bool(
                            item["product_metric_eligible"]
                        ),
                    )
                    for item in connection.execute(
                        """SELECT * FROM session_model_ensemble_predictive_metrics
                           WHERE run_id=? AND projection_version=?
                           ORDER BY metric_key""",
                        (
                            row["run_id"],
                            PROBABILISTIC_METRIC_PROJECTION_VERSION,
                        ),
                    ).fetchall()
                )
                point_predictive_identity = _predictive_identity(
                    connection, row["run_id"]
                )
                points.append(
                    ModelEnsembleTrajectoryPoint(
                        generation=int(row["generation"]),
                        run_id=row["run_id"],
                        published_at=from_iso(row["published_at"]),
                        completed_at=from_iso(row["completed_at"]),
                        max_messages=int(row["max_messages"]),
                        source_coverage_state=SourceCoverageState(
                            row["source_coverage_state"]
                        ),
                        chunk_count=int(row["chunk_count"]),
                        comparable_to_head=(
                            watch["head_generation"] is not None
                            and row["plan_fingerprint"] == watch["head_plan"]
                            and int(row["max_messages"])
                            == int(watch["head_max_messages"])
                            and row["provider_version"]
                            == watch["head_provider_version"]
                            and row["adapter_version"]
                            == watch["head_adapter_version"]
                            and row["source_schema_version"]
                            == watch["head_source_schema_version"]
                            and row["content_schema_version"]
                            == watch["head_content_schema_version"]
                            and row["redactor_version"]
                            == watch["head_redactor_version"]
                            and row["projection_version"]
                            == watch["head_projection_version"]
                            and row["predictive_projection_version"]
                            == watch["head_predictive_version"]
                            and point_predictive_identity
                            == head_predictive_identity
                        ),
                        metrics=metrics,
                        metric_projection_version=row["projection_version"],
                        metric_projection_completed_at=(
                            None
                            if row["projected_at"] is None
                            else from_iso(row["projected_at"])
                        ),
                        typed_metrics=typed_metrics,
                        predictive_projection_version=row[
                            "predictive_projection_version"
                        ],
                        predictive_metrics=predictive_metrics,
                    )
                )
        head_generation = (
            None
            if watch["head_generation"] is None
            else int(watch["head_generation"])
        )
        return ModelEnsembleTrajectoryPage(
            watch_id=watch_id,
            head_run_id=(
                None if head_generation is None else watch["latest_run_id"]
            ),
            head_generation=head_generation,
            points=tuple(points),
            next_before_generation=(
                points[-1].generation if has_more and points else None
            ),
        )

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
                           lease_owner=?,lease_token=?,
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
            connection.execute(
                """INSERT INTO session_model_ensemble_watch_publications(
                       watch_id,generation,run_id,max_messages,published_at
                   )
                   SELECT watch_id,generation,?,?,?
                   FROM session_model_ensemble_watches
                   WHERE watch_id=? AND state='running' AND lease_owner=?
                     AND lease_token=? AND lease_expires_at>?
                   ON CONFLICT(watch_id,run_id) DO NOTHING""",
                (
                    run.run_id,
                    _record(self._row(connection, lease.watch_id)).max_messages,
                    to_iso(now),
                    lease.watch_id,
                    lease.owner,
                    lease.token,
                    to_iso(now),
                ),
            )
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
