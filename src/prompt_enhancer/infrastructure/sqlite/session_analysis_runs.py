"""SQLite persistence for immutable, content-free session quality snapshots."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ...application.persistence import (
    AnalysisRunStatus,
    MetricValueState,
    SessionAnalysisCompletionAuthority,
    SessionAnalysisAggregationResultRecord,
    SessionAnalysisAggregationSnapshotRecord,
    SessionAnalysisEvidenceRecord,
    SessionAnalysisSignalRecord,
    SessionAnalysisResultRecord,
    SessionAnalysisRunDraft,
    SessionAnalysisRunRecord,
    SessionEvidenceOrigin,
    SessionMetricAggregation,
    SessionMetricApplicability,
    SessionMetricDirection,
    SessionMetricScopeState,
    SessionMetricSignalStatus,
)
from ...database import DatabaseInvariantError, SCHEMA_VERSION
from ...domain import DataTier, MetricObservation, MetricSource, Provider
from ._common import (
    ConnectionScope,
    from_iso,
    require_safe_id,
    require_safe_label,
    require_utc,
    to_iso,
)


class SqliteSessionAnalysisRunRepository:
    """Append a selected-window profile once; expose explicit privacy deletion."""

    def __init__(
        self,
        connection_scope: ConnectionScope,
        ensure_initialized: Callable[[], None],
    ) -> None:
        self._connection_scope = connection_scope
        self._ensure_initialized = ensure_initialized

    def begin(self, draft: SessionAnalysisRunDraft) -> None:
        self._ensure_initialized()
        if draft.schema_version != SCHEMA_VERSION:
            raise DatabaseInvariantError(
                "session analysis schema version does not match storage"
            )
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute(
                    "SELECT 1 FROM session_analysis_runs WHERE run_id = ?",
                    (draft.run_id,),
                ).fetchone() is not None:
                    raise DatabaseInvariantError("session analysis run already exists")
                session = connection.execute(
                    "SELECT provider FROM sessions WHERE session_id = ?",
                    (draft.session_id,),
                ).fetchone()
                if session is None:
                    raise DatabaseInvariantError("session analysis target does not exist")
                if session["provider"] != draft.provider.value:
                    raise DatabaseInvariantError(
                        "session analysis provider does not match the selected session"
                    )
                connection.execute(
                    """
                    INSERT INTO session_analysis_runs(
                        run_id, session_id, request_fingerprint,
                        input_fingerprint, analysis_profile_key,
                        analysis_profile_version, metric_pack_key,
                        metric_pack_version, metric_scope_state, data_tier, consent_purpose,
                        consent_policy_version, provider, provider_version,
                        adapter_version, source_schema_version,
                        content_schema_version, metric_engine_version,
                        redactor_version, model_plan_fingerprint,
                        schema_version, local_only, started_at, status
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,
                        ?, 'running'
                    )
                    """,
                    (
                        draft.run_id,
                        draft.session_id,
                        draft.request_fingerprint,
                        draft.input_fingerprint,
                        draft.analysis_profile_key,
                        draft.analysis_profile_version,
                        draft.metric_pack_key,
                        draft.metric_pack_version,
                        draft.metric_scope_state.value,
                        draft.data_tier.value,
                        draft.consent_purpose,
                        draft.consent_policy_version,
                        draft.provider.value,
                        draft.provider_version,
                        draft.adapter_version,
                        draft.source_schema_version,
                        draft.content_schema_version,
                        draft.metric_engine_version,
                        draft.redactor_version,
                        draft.model_plan_fingerprint,
                        draft.schema_version,
                        to_iso(draft.started_at),
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO session_analysis_run_metrics(
                        run_id, metric_key, ordinal
                    ) VALUES (?, ?, ?)
                    """,
                    (
                        (draft.run_id, metric_key, ordinal)
                        for ordinal, metric_key in enumerate(
                            draft.selected_metric_keys
                        )
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def complete(
        self,
        run_id: str,
        results: tuple[SessionAnalysisResultRecord, ...],
        *,
        finished_at: datetime,
        completion_authority: SessionAnalysisCompletionAuthority | None = None,
    ) -> None:
        self._ensure_initialized()
        require_safe_id(run_id)
        finished_at = require_utc(finished_at)
        if not results:
            raise DatabaseInvariantError("completed session analysis requires results")
        identities = {
            (result.observation.key, result.observation.version) for result in results
        }
        if len(identities) != len(results):
            raise DatabaseInvariantError("session analysis results contain duplicates")

        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                run = connection.execute(
                    """
                    SELECT started_at, status, metric_scope_state
                    FROM session_analysis_runs
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                if run is None or run["status"] != AnalysisRunStatus.RUNNING.value:
                    raise DatabaseInvariantError(
                        "session analysis run is missing or already terminal"
                    )
                selected_metric_keys = tuple(
                    row["metric_key"]
                    for row in connection.execute(
                        """
                        SELECT metric_key FROM session_analysis_run_metrics
                        WHERE run_id = ? ORDER BY ordinal
                        """,
                        (run_id,),
                    ).fetchall()
                )
                if (
                    run["metric_scope_state"]
                    != SessionMetricScopeState.EXACT.value
                    or tuple(sorted(result.observation.key for result in results))
                    != selected_metric_keys
                ):
                    raise DatabaseInvariantError(
                        "session analysis results do not match selected metric scope"
                    )
                if completion_authority is not None:
                    authorized = connection.execute(
                        """
                        SELECT 1
                        FROM analysis_jobs AS job
                        JOIN automation_grants AS grant
                          ON grant.grant_id = job.automation_grant_id
                        JOIN sessions AS target
                          ON target.session_id = job.session_id
                        JOIN session_analysis_runs AS analysis
                          ON analysis.run_id = ?
                        WHERE job.job_id = ?
                          AND job.automation_grant_id = ?
                          AND job.kind = 'session_quality'
                          AND job.state IN ('preprocessing', 'stage_n')
                          AND job.cancel_requested = 0
                          AND job.lease_owner = ?
                          AND job.lease_token = ?
                          AND job.lease_expires_at > ?
                          AND job.local_only = 1
                          AND grant.state = 'active'
                          AND grant.expires_at > ?
                          AND grant.local_only = 1
                          AND grant.remote_requires_fresh_approval = 1
                          AND analysis.status = 'running'
                          AND analysis.local_only = 1
                          AND analysis.session_id = job.session_id
                          AND analysis.provider = job.provider
                          AND target.project_id = job.project_id
                          AND target.provider = job.provider
                          AND grant.project_id = job.project_id
                          AND grant.provider = job.provider
                          AND NOT EXISTS (
                              SELECT metric_key
                              FROM session_analysis_run_metrics
                              WHERE run_id = analysis.run_id
                              EXCEPT
                              SELECT metric_key
                              FROM analysis_job_metrics
                              WHERE job_id = job.job_id
                          )
                          AND NOT EXISTS (
                              SELECT metric_key
                              FROM analysis_job_metrics
                              WHERE job_id = job.job_id
                              EXCEPT
                              SELECT metric_key
                              FROM session_analysis_run_metrics
                              WHERE run_id = analysis.run_id
                          )
                          AND NOT EXISTS (
                              SELECT metric_key
                              FROM session_analysis_run_metrics
                              WHERE run_id = analysis.run_id
                              EXCEPT
                              SELECT metric_key
                              FROM automation_grant_metrics
                              WHERE grant_id = grant.grant_id
                          )
                          AND NOT EXISTS (
                              SELECT metric_key
                              FROM automation_grant_metrics
                              WHERE grant_id = grant.grant_id
                              EXCEPT
                              SELECT metric_key
                              FROM session_analysis_run_metrics
                              WHERE run_id = analysis.run_id
                          )
                        """,
                        (
                            run_id,
                            completion_authority.job_id,
                            completion_authority.automation_grant_id,
                            completion_authority.lease_owner,
                            completion_authority.lease_token,
                            to_iso(finished_at),
                            to_iso(finished_at),
                        ),
                    ).fetchone()
                    if authorized is None:
                        raise DatabaseInvariantError(
                            "automation completion authority is no longer valid"
                        )
                started_at = from_iso(run["started_at"])
                if started_at is None or finished_at < started_at:
                    raise DatabaseInvariantError(
                        "session analysis cannot finish before it starts"
                    )
                for result in results:
                    if not started_at <= result.computed_at <= finished_at:
                        raise DatabaseInvariantError(
                            "session result timestamp is outside the analysis window"
                        )
                    observation = result.observation
                    connection.execute(
                        """
                        INSERT INTO session_analysis_results(
                            run_id, key, version, metric_schema_version,
                            value_state, numeric_value, unit, source, direction,
                            applicability, aggregation_method, fraction_numerator,
                            fraction_denominator, observed_count, eligible_count,
                            coverage, confidence, evidence_data_tier,
                            explanation_code, error_code, algorithm_id,
                            algorithm_version, model_id, model_revision,
                            model_license, tokenizer_id, prompt_version,
                            rubric_version, computed_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            run_id,
                            observation.key,
                            observation.version,
                            result.metric_schema_version,
                            result.value_state.value,
                            observation.numeric_value,
                            observation.unit,
                            observation.source.value,
                            result.direction.value,
                            result.applicability.value,
                            result.aggregation_method.value,
                            result.fraction_numerator,
                            result.fraction_denominator,
                            observation.observed_count,
                            observation.eligible_count,
                            observation.coverage,
                            observation.confidence,
                            result.evidence_data_tier.value,
                            result.explanation_code,
                            result.error_code,
                            result.algorithm_id,
                            result.algorithm_version,
                            result.model_id,
                            result.model_revision,
                            result.model_license,
                            result.tokenizer_id,
                            result.prompt_version,
                            result.rubric_version,
                            to_iso(result.computed_at),
                        ),
                    )
                    connection.executemany(
                        """
                        INSERT INTO session_analysis_result_evidence(
                            run_id, key, version, message_id, origin, ordinal
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            (
                                run_id,
                                observation.key,
                                observation.version,
                                evidence.message_id,
                                evidence.origin.value,
                                ordinal,
                            )
                            for ordinal, evidence in enumerate(result.evidence)
                        ),
                    )
                    connection.executemany(
                        """
                        INSERT INTO session_analysis_result_signals(
                            run_id, key, version, code, status, signal_count, ordinal
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            (
                                run_id,
                                observation.key,
                                observation.version,
                                signal.code,
                                signal.status.value,
                                signal.count,
                                ordinal,
                            )
                            for ordinal, signal in enumerate(result.signals)
                        ),
                    )
                cursor = connection.execute(
                    """
                    UPDATE session_analysis_runs
                    SET finished_at = ?, status = 'completed'
                    WHERE run_id = ? AND status = 'running'
                    """,
                    (to_iso(finished_at), run_id),
                )
                if cursor.rowcount != 1:
                    raise DatabaseInvariantError(
                        "session analysis transition was rejected"
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def fail(self, run_id: str, *, finished_at: datetime, failure_code: str) -> None:
        self._ensure_initialized()
        require_safe_id(run_id)
        finished_at = require_utc(finished_at)
        require_safe_label(failure_code)
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT started_at, status FROM session_analysis_runs
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                if row is None or row["status"] != AnalysisRunStatus.RUNNING.value:
                    raise DatabaseInvariantError(
                        "session analysis run is missing or already terminal"
                    )
                started_at = from_iso(row["started_at"])
                if started_at is None or finished_at < started_at:
                    raise DatabaseInvariantError(
                        "session analysis cannot finish before it starts"
                    )
                cursor = connection.execute(
                    """
                    UPDATE session_analysis_runs
                    SET finished_at = ?, status = 'failed', failure_code = ?
                    WHERE run_id = ? AND status = 'running'
                    """,
                    (to_iso(finished_at), failure_code, run_id),
                )
                if cursor.rowcount != 1:
                    raise DatabaseInvariantError(
                        "session analysis transition was rejected"
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _selected_metrics(connection, run_id: str) -> tuple[str, ...]:  # type: ignore[no-untyped-def]
        return tuple(
            row["metric_key"]
            for row in connection.execute(
                """
                SELECT metric_key FROM session_analysis_run_metrics
                WHERE run_id = ? ORDER BY ordinal
                """,
                (run_id,),
            ).fetchall()
        )

    @classmethod
    def _record_from_row(
        cls,
        connection,  # type: ignore[no-untyped-def]
        row: object,
    ) -> SessionAnalysisRunRecord:
        draft = SessionAnalysisRunDraft(
            run_id=row["run_id"],
            session_id=row["session_id"],
            request_fingerprint=row["request_fingerprint"],
            input_fingerprint=row["input_fingerprint"],
            analysis_profile_key=row["analysis_profile_key"],
            analysis_profile_version=row["analysis_profile_version"],
            metric_pack_key=row["metric_pack_key"],
            metric_pack_version=row["metric_pack_version"],
            metric_scope_state=SessionMetricScopeState(
                row["metric_scope_state"]
            ),
            selected_metric_keys=cls._selected_metrics(
                connection,
                row["run_id"],
            ),
            data_tier=DataTier(row["data_tier"]),
            consent_purpose=row["consent_purpose"],
            consent_policy_version=row["consent_policy_version"],
            provider=Provider(row["provider"]),
            provider_version=row["provider_version"],
            adapter_version=row["adapter_version"],
            source_schema_version=row["source_schema_version"],
            content_schema_version=row["content_schema_version"],
            metric_engine_version=row["metric_engine_version"],
            redactor_version=row["redactor_version"],
            model_plan_fingerprint=row["model_plan_fingerprint"],
            schema_version=row["schema_version"],
            local_only=bool(row["local_only"]),
            started_at=from_iso(row["started_at"]),
        )
        return SessionAnalysisRunRecord(
            draft=draft,
            status=AnalysisRunStatus(row["status"]),
            finished_at=from_iso(row["finished_at"]),
            failure_code=row["failure_code"],
        )

    def get(self, run_id: str) -> SessionAnalysisRunRecord | None:
        self._ensure_initialized()
        require_safe_id(run_id)
        with self._connection_scope(readonly=True) as connection:
            row = connection.execute(
                "SELECT * FROM session_analysis_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            return (
                None
                if row is None
                else self._record_from_row(connection, row)
            )

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset cannot be negative")

    def list_for_session(
        self,
        session_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[SessionAnalysisRunRecord, ...]:
        self._ensure_initialized()
        require_safe_id(session_id)
        self._validate_page(limit, offset)
        with self._connection_scope(readonly=True) as connection:
            rows = connection.execute(
                """
                SELECT * FROM session_analysis_runs
                WHERE session_id = ?
                ORDER BY started_at DESC, run_id
                LIMIT ? OFFSET ?
                """,
                (session_id, limit, offset),
            ).fetchall()
            return tuple(
                self._record_from_row(connection, row) for row in rows
            )

    def get_latest_completed(
        self, session_id: str
    ) -> SessionAnalysisRunRecord | None:
        self._ensure_initialized()
        require_safe_id(session_id)
        with self._connection_scope(readonly=True) as connection:
            row = connection.execute(
                """
                SELECT * FROM session_analysis_runs
                WHERE session_id = ? AND status = 'completed'
                ORDER BY started_at DESC, run_id LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            return (
                None
                if row is None
                else self._record_from_row(connection, row)
            )

    def get_latest_for_profile(
        self,
        session_id: str,
        *,
        analysis_profile_key: str,
        analysis_profile_version: int,
        metric_pack_key: str,
        metric_pack_version: int,
    ) -> SessionAnalysisRunRecord | None:
        """Load the latest run for one exact server-owned profile and pack."""

        self._ensure_initialized()
        require_safe_id(session_id)
        require_safe_label(analysis_profile_key)
        require_safe_label(metric_pack_key)
        if (
            isinstance(analysis_profile_version, bool)
            or not isinstance(analysis_profile_version, int)
            or analysis_profile_version < 1
            or isinstance(metric_pack_version, bool)
            or not isinstance(metric_pack_version, int)
            or metric_pack_version < 1
        ):
            raise ValueError("analysis profile and metric pack versions begin at one")
        with self._connection_scope(readonly=True) as connection:
            row = connection.execute(
                """
                SELECT * FROM session_analysis_runs
                WHERE session_id = ?
                  AND analysis_profile_key = ?
                  AND analysis_profile_version = ?
                  AND metric_pack_key = ?
                  AND metric_pack_version = ?
                ORDER BY started_at DESC, run_id LIMIT 1
                """,
                (
                    session_id,
                    analysis_profile_key,
                    analysis_profile_version,
                    metric_pack_key,
                    metric_pack_version,
                ),
            ).fetchone()
            return (
                None
                if row is None
                else self._record_from_row(connection, row)
            )

    @staticmethod
    def _validate_aggregation_selection(session_ids: tuple[str, ...]) -> None:
        if not 1 <= len(session_ids) <= 100:
            raise ValueError("aggregation selection must contain 1 to 100 sessions")
        for session_id in session_ids:
            require_safe_id(session_id)
        if len(set(session_ids)) != len(session_ids):
            raise ValueError("aggregation selection cannot contain duplicates")

    def get_latest_completed_for_aggregation(
        self,
        session_ids: tuple[str, ...],
        *,
        analysis_profile_key: str,
        analysis_profile_version: int,
        metric_pack_key: str,
        metric_pack_version: int,
    ) -> tuple[SessionAnalysisAggregationSnapshotRecord, ...]:
        """Load the latest matching profile/pack snapshots in one SQLite query."""

        self._ensure_initialized()
        self._validate_aggregation_selection(session_ids)
        require_safe_label(analysis_profile_key)
        require_safe_label(metric_pack_key)
        if analysis_profile_version < 1 or metric_pack_version < 1:
            raise ValueError("aggregation profile and pack versions begin at one")
        selected_values = ", ".join("(?, ?)" for _ in session_ids)
        parameters = tuple(
            value
            for ordinal, session_id in enumerate(session_ids)
            for value in (session_id, ordinal)
        ) + (
            analysis_profile_key,
            analysis_profile_version,
            metric_pack_key,
            metric_pack_version,
        )
        query = f"""
            WITH selected(session_id, selection_order) AS (
                VALUES {selected_values}
            ),
            scope AS (
                SELECT ordered.run_id,
                       GROUP_CONCAT(ordered.metric_key, '|') AS metric_keys
                FROM (
                    SELECT run_id, metric_key
                    FROM session_analysis_run_metrics
                    ORDER BY run_id, ordinal
                ) AS ordered
                GROUP BY ordered.run_id
            ),
            ranked AS (
                SELECT
                    selected.selection_order,
                    run.run_id,
                    run.session_id,
                    run.analysis_profile_key,
                    run.analysis_profile_version,
                    run.metric_pack_key,
                    run.metric_pack_version,
                    run.metric_scope_state,
                    COALESCE(scope.metric_keys, '') AS selected_metric_keys,
                    run.data_tier,
                    run.consent_policy_version,
                    run.provider,
                    run.provider_version,
                    run.adapter_version,
                    run.source_schema_version,
                    run.content_schema_version,
                    run.metric_engine_version,
                    run.redactor_version,
                    run.model_plan_fingerprint,
                    run.schema_version,
                    run.local_only,
                    ROW_NUMBER() OVER (
                        PARTITION BY run.session_id
                        ORDER BY run.started_at DESC, run.run_id
                    ) AS run_rank
                FROM selected
                JOIN session_analysis_runs AS run
                  ON run.session_id = selected.session_id
                 AND run.status = 'completed'
                 AND run.analysis_profile_key = ?
                 AND run.analysis_profile_version = ?
                 AND run.metric_pack_key = ?
                 AND run.metric_pack_version = ?
                LEFT JOIN scope ON scope.run_id = run.run_id
            )
            SELECT
                ranked.selection_order,
                ranked.session_id AS snapshot_session_id,
                ranked.analysis_profile_key,
                ranked.analysis_profile_version,
                ranked.metric_pack_key,
                ranked.metric_pack_version,
                ranked.metric_scope_state,
                ranked.selected_metric_keys,
                ranked.data_tier,
                ranked.consent_policy_version,
                ranked.provider,
                ranked.provider_version,
                ranked.adapter_version,
                ranked.source_schema_version,
                ranked.content_schema_version,
                ranked.metric_engine_version,
                ranked.redactor_version,
                ranked.model_plan_fingerprint,
                ranked.schema_version AS persistence_schema_version,
                ranked.local_only,
                result.key AS result_key,
                result.version AS result_version,
                result.metric_schema_version AS result_metric_schema_version,
                result.value_state AS result_value_state,
                result.numeric_value AS result_numeric_value,
                result.unit AS result_unit,
                result.source AS result_source,
                result.direction AS result_direction,
                result.applicability AS result_applicability,
                result.aggregation_method AS result_aggregation_method,
                result.fraction_numerator AS result_fraction_numerator,
                result.fraction_denominator AS result_fraction_denominator,
                result.observed_count AS result_observed_count,
                result.eligible_count AS result_eligible_count,
                result.coverage AS result_coverage,
                result.confidence AS result_confidence,
                result.algorithm_id AS result_algorithm_id,
                result.algorithm_version AS result_algorithm_version,
                result.model_id AS result_model_id,
                result.model_revision AS result_model_revision,
                result.model_license AS result_model_license,
                result.tokenizer_id AS result_tokenizer_id,
                result.prompt_version AS result_prompt_version,
                result.rubric_version AS result_rubric_version
            FROM ranked
            LEFT JOIN session_analysis_results AS result
              ON result.run_id = ranked.run_id
            WHERE ranked.run_rank = 1
            ORDER BY ranked.selection_order, result.key, result.version
        """
        with self._connection_scope(readonly=True) as connection:
            rows = connection.execute(query, parameters).fetchall()

        provenance: dict[str, dict[str, object]] = {}
        projected_results: dict[
            str, list[SessionAnalysisAggregationResultRecord]
        ] = {}
        for row in rows:
            session_id = row["snapshot_session_id"]
            if session_id not in provenance:
                provenance[session_id] = {
                    "session_id": session_id,
                    "analysis_profile_key": row["analysis_profile_key"],
                    "analysis_profile_version": row["analysis_profile_version"],
                    "metric_pack_key": row["metric_pack_key"],
                    "metric_pack_version": row["metric_pack_version"],
                    "metric_scope_state": SessionMetricScopeState(
                        row["metric_scope_state"]
                    ),
                    "selected_metric_keys": tuple(
                        key
                        for key in row["selected_metric_keys"].split("|")
                        if key
                    ),
                    "data_tier": DataTier(row["data_tier"]),
                    "consent_policy_version": row["consent_policy_version"],
                    "provider": Provider(row["provider"]),
                    "provider_version": row["provider_version"],
                    "adapter_version": row["adapter_version"],
                    "source_schema_version": row["source_schema_version"],
                    "content_schema_version": row["content_schema_version"],
                    "metric_engine_version": row["metric_engine_version"],
                    "redactor_version": row["redactor_version"],
                    "model_plan_fingerprint": row["model_plan_fingerprint"],
                    "persistence_schema_version": row[
                        "persistence_schema_version"
                    ],
                    "local_only": bool(row["local_only"]),
                }
                projected_results[session_id] = []
            if row["result_key"] is None:
                continue
            observation = MetricObservation(
                key=row["result_key"],
                version=row["result_version"],
                numeric_value=row["result_numeric_value"],
                unit=row["result_unit"],
                source=MetricSource(row["result_source"]),
                observed_count=row["result_observed_count"],
                eligible_count=row["result_eligible_count"],
                coverage=row["result_coverage"],
                confidence=row["result_confidence"],
            )
            projected_results[session_id].append(
                SessionAnalysisAggregationResultRecord(
                    observation=observation,
                    value_state=MetricValueState(row["result_value_state"]),
                    direction=SessionMetricDirection(row["result_direction"]),
                    applicability=SessionMetricApplicability(
                        row["result_applicability"]
                    ),
                    aggregation_method=SessionMetricAggregation(
                        row["result_aggregation_method"]
                    ),
                    metric_schema_version=row["result_metric_schema_version"],
                    fraction_numerator=row["result_fraction_numerator"],
                    fraction_denominator=row["result_fraction_denominator"],
                    algorithm_id=row["result_algorithm_id"],
                    algorithm_version=row["result_algorithm_version"],
                    model_id=row["result_model_id"],
                    model_revision=row["result_model_revision"],
                    model_license=row["result_model_license"],
                    tokenizer_id=row["result_tokenizer_id"],
                    prompt_version=row["result_prompt_version"],
                    rubric_version=row["result_rubric_version"],
                )
            )

        return tuple(
            SessionAnalysisAggregationSnapshotRecord(
                **provenance[session_id],
                results=tuple(projected_results[session_id]),
            )
            for session_id in session_ids
            if session_id in provenance
        )

    def get_results(
        self, run_id: str
    ) -> tuple[SessionAnalysisResultRecord, ...]:
        self._ensure_initialized()
        require_safe_id(run_id)
        with self._connection_scope(readonly=True) as connection:
            rows = connection.execute(
                """
                SELECT * FROM session_analysis_results
                WHERE run_id = ? ORDER BY key, version
                """,
                (run_id,),
            ).fetchall()
            results: list[SessionAnalysisResultRecord] = []
            for row in rows:
                evidence_rows = connection.execute(
                    """
                    SELECT message_id, origin
                    FROM session_analysis_result_evidence
                    WHERE run_id = ? AND key = ? AND version = ?
                    ORDER BY ordinal
                    """,
                    (run_id, row["key"], row["version"]),
                ).fetchall()
                signal_rows = connection.execute(
                    """
                    SELECT code, status, signal_count
                    FROM session_analysis_result_signals
                    WHERE run_id = ? AND key = ? AND version = ?
                    ORDER BY ordinal
                    """,
                    (run_id, row["key"], row["version"]),
                ).fetchall()
                observation = MetricObservation(
                    key=row["key"],
                    version=row["version"],
                    numeric_value=row["numeric_value"],
                    unit=row["unit"],
                    source=MetricSource(row["source"]),
                    observed_count=row["observed_count"],
                    eligible_count=row["eligible_count"],
                    coverage=row["coverage"],
                    confidence=row["confidence"],
                )
                results.append(
                    SessionAnalysisResultRecord(
                        observation=observation,
                        value_state=MetricValueState(row["value_state"]),
                        direction=SessionMetricDirection(row["direction"]),
                        applicability=SessionMetricApplicability(
                            row["applicability"]
                        ),
                        aggregation_method=SessionMetricAggregation(
                            row["aggregation_method"]
                        ),
                        metric_schema_version=row["metric_schema_version"],
                        evidence_data_tier=DataTier(row["evidence_data_tier"]),
                        fraction_numerator=row["fraction_numerator"],
                        fraction_denominator=row["fraction_denominator"],
                        evidence=tuple(
                            SessionAnalysisEvidenceRecord(
                                message_id=evidence["message_id"],
                                origin=SessionEvidenceOrigin(evidence["origin"]),
                            )
                            for evidence in evidence_rows
                        ),
                        signals=tuple(
                            SessionAnalysisSignalRecord(
                                code=signal["code"],
                                status=SessionMetricSignalStatus(signal["status"]),
                                count=signal["signal_count"],
                            )
                            for signal in signal_rows
                        ),
                        explanation_code=row["explanation_code"],
                        error_code=row["error_code"],
                        algorithm_id=row["algorithm_id"],
                        algorithm_version=row["algorithm_version"],
                        model_id=row["model_id"],
                        model_revision=row["model_revision"],
                        model_license=row["model_license"],
                        tokenizer_id=row["tokenizer_id"],
                        prompt_version=row["prompt_version"],
                        rubric_version=row["rubric_version"],
                        computed_at=from_iso(row["computed_at"]),
                    )
                )
        return tuple(results)

    def delete_for_privacy(self, run_id: str) -> bool:
        self._ensure_initialized()
        require_safe_id(run_id)
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    "DELETE FROM session_analysis_runs WHERE run_id = ?", (run_id,)
                )
                connection.commit()
                return cursor.rowcount == 1
            except Exception:
                connection.rollback()
                raise
