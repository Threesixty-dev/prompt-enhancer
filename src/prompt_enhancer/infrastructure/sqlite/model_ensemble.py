"""Normalized, content-free persistence for local measured/predictive analysis."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json

from ...application.analysis.model_ensemble import (
    ChunkMetricCommitteeReceipt,
    ModelEnsembleChunkReceipt,
    ModelEvidenceSelectionReceipt,
    ModelExpertIdentity,
    ModelExpertReceipt,
    ModelExpertRole,
    ModelExpertStatus,
    ModelMetricVote,
    ModelVoteState,
    MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION,
    SessionModelEnsembleMetricReceipt,
    SessionModelEnsembleReceipt,
    SessionModelEnsembleTypedMetricReceipt,
    SourceCoverageState,
)
from ...application.analysis.session_model_ensemble import (
    SessionModelEnsemblePersistenceAuthority,
    SessionModelEnsembleRepository,
    SessionModelEnsembleRunRecord,
)
from ...application.analysis.probabilistic_metrics import (
    PROBABILISTIC_METRIC_PROJECTION_VERSION,
    PROBABILISTIC_METRIC_CONTRACTS,
    FactorScale,
    PredictiveFactorContribution,
    PredictiveMetricState,
    PredictiveMetricTarget,
    PredictiveModelStageReceipt,
    SessionPredictiveMetricProjection,
    SessionPredictiveMetricReceipt,
)
from ...application.persistence import MetricValueState
from ...database import DatabaseInvariantError
from ...domain import Provider
from ._common import ConnectionScope, from_iso, require_safe_id, to_iso


def _graph_fingerprint(run: SessionModelEnsembleRunRecord) -> str:
    payload = run.model_dump(mode="json")
    receipt = payload["receipt"]
    # The typed projection is an append-only adjunct with its own seal.  Keep
    # the original v26 graph commitment byte-compatible for legacy runs.
    receipt.pop("metric_projection_version", None)
    receipt.pop("metric_projection_completed_at", None)
    receipt.pop("typed_metrics", None)
    receipt.pop("predictive_projection", None)
    receipt["chunk_plan"] = sorted(
        receipt["chunk_plan"], key=lambda item: item["ordinal"]
    )
    receipt["chunks"] = sorted(
        receipt["chunks"],
        key=lambda item: (item["chunk_ordinal"], item["metric_key"]),
    )
    receipt["metrics"] = sorted(
        receipt["metrics"], key=lambda item: item["metric_key"]
    )
    receipt["experts"] = sorted(
        receipt["experts"], key=lambda item: item["identity"]["ordinal"]
    )
    receipt["evidence_selections"] = sorted(
        receipt["evidence_selections"],
        key=lambda item: (
            item["chunk_ordinal"],
            item["metric_key"],
            item["model_key"],
        ),
    )
    receipt["model_votes"] = sorted(
        receipt["model_votes"],
        key=lambda item: (
            item["chunk_ordinal"],
            item["metric_key"],
            item["model_key"],
        ),
    )
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _metric_projection_fingerprint(receipt: SessionModelEnsembleReceipt) -> str:
    payload = {
        "projection_version": receipt.metric_projection_version,
        "projected_at": (
            None
            if receipt.metric_projection_completed_at is None
            else receipt.metric_projection_completed_at.isoformat()
        ),
        "metrics": sorted(
            (item.model_dump(mode="json") for item in receipt.typed_metrics),
            key=lambda item: item["metric_key"],
        ),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _predictive_projection_fingerprint(
    projection: SessionPredictiveMetricProjection,
) -> str:
    payload = projection.model_dump(mode="json")
    payload["metrics"] = sorted(
        payload["metrics"], key=lambda item: item["metric_key"]
    )
    for metric in payload["metrics"]:
        metric["factors"] = sorted(
            metric["factors"], key=lambda item: item["factor_key"]
        )
    payload["model_stages"] = sorted(
        payload["model_stages"], key=lambda item: item["model_key"]
    )
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


class SqliteSessionModelEnsembleRepository(SessionModelEnsembleRepository):
    def __init__(
        self,
        connection_scope: ConnectionScope,
        ensure_initialized: Callable[[], None],
    ) -> None:
        self._connection_scope = connection_scope
        self._ensure_initialized = ensure_initialized

    def save_completed(
        self,
        run: SessionModelEnsembleRunRecord,
        *,
        authority: SessionModelEnsemblePersistenceAuthority | None = None,
    ) -> None:
        self._ensure_initialized()
        receipt = run.receipt
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if authority is not None:
                    active = connection.execute(
                        """SELECT 1
                           FROM session_model_ensemble_watches
                           WHERE watch_id=? AND state='running'
                             AND generation=? AND lease_owner=? AND lease_token=?
                             AND lease_expires_at>? AND session_id=? AND provider=?
                             AND latest_run_id IS ?""",
                        (
                            authority.watch_id,
                            authority.generation,
                            authority.owner,
                            authority.token,
                            to_iso(authority.observed_at),
                            run.session_id,
                            run.provider.value,
                            authority.prior_run_id,
                        ),
                    ).fetchone()
                    if active is None:
                        raise DatabaseInvariantError(
                            "model ensemble watch persistence authority is no longer active"
                        )
                session = connection.execute(
                    "SELECT provider FROM sessions WHERE session_id=?",
                    (run.session_id,),
                ).fetchone()
                if session is None or session["provider"] != run.provider.value:
                    raise DatabaseInvariantError(
                        "model ensemble target does not match an indexed session"
                    )
                connection.execute(
                    """
                    INSERT INTO session_model_ensemble_runs(
                        run_id,session_id,request_fingerprint,input_fingerprint,
                        provider,provider_version,adapter_version,source_schema_version,
                        content_schema_version,redactor_version,consent_policy_version,
                        plan_version,plan_fingerprint,source_window_fingerprint,
                        source_coverage_state,chunk_count,model_count,metric_count,
                        created_at,completed_at,local_only,content_persisted,
                        calibration_state,product_metric_eligible
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,0,'not_assessed',0)
                    """,
                    (
                        run.run_id,
                        run.session_id,
                        run.request_fingerprint,
                        run.input_fingerprint,
                        run.provider.value,
                        run.provider_version,
                        run.adapter_version,
                        run.source_schema_version,
                        run.content_schema_version,
                        run.redactor_version,
                        run.consent_policy_version,
                        receipt.plan_version,
                        receipt.plan_fingerprint,
                        receipt.source_window_fingerprint,
                        receipt.source_coverage_state.value,
                        receipt.chunk_count,
                        receipt.model_count,
                        len(receipt.metrics),
                        to_iso(receipt.created_at),
                        to_iso(receipt.completed_at),
                    ),
                )
                connection.executemany(
                    """INSERT INTO session_model_ensemble_chunks
                       VALUES(?,?,?,?,?,?)""",
                    (
                        (
                            run.run_id,
                            chunk.ordinal,
                            chunk.chunk_fingerprint,
                            chunk.source_message_count,
                            chunk.fragment_count,
                            chunk.character_count,
                        )
                        for chunk in receipt.chunk_plan
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO session_model_ensemble_experts(
                        run_id,model_ordinal,model_key,role,repository_id,revision,
                        tokenizer_id,license_spdx,backend_key,contributes_to_decision,
                        status,error_code,device,inference_latency_ms,
                        peak_accelerator_memory_mb,process_rss_mb,
                        unloaded_after_stage,calibration_state
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,'not_assessed')
                    """,
                    (
                        (
                            run.run_id,
                            expert.identity.ordinal,
                            expert.identity.model_key,
                            expert.identity.role.value,
                            expert.identity.repository_id,
                            expert.identity.revision,
                            expert.identity.tokenizer_id,
                            expert.identity.license_spdx,
                            expert.identity.backend_key,
                            int(expert.identity.contributes_to_decision),
                            expert.status.value,
                            expert.error_code,
                            expert.device,
                            expert.inference_latency_ms,
                            expert.peak_accelerator_memory_mb,
                            expert.process_rss_mb,
                        )
                        for expert in receipt.experts
                    ),
                )
                for selection in receipt.evidence_selections:
                    connection.execute(
                        """INSERT INTO session_model_ensemble_evidence_selections
                           VALUES(?,?,?,?,?,?,?,?,?,'not_assessed')""",
                        (
                            run.run_id,
                            selection.chunk_ordinal,
                            selection.metric_key,
                            selection.model_key,
                            selection.role.value,
                            selection.candidate_count,
                            len(selection.selected_fragment_ids),
                            selection.ranking_fingerprint,
                            selection.top_raw_score,
                        ),
                    )
                    connection.executemany(
                        """INSERT INTO session_model_ensemble_selection_fragments
                           VALUES(?,?,?,?,?,?)""",
                        (
                            (
                                run.run_id,
                                selection.chunk_ordinal,
                                selection.metric_key,
                                selection.model_key,
                                ordinal,
                                fragment_id,
                            )
                            for ordinal, fragment_id in enumerate(
                                selection.selected_fragment_ids
                            )
                        ),
                    )
                for vote in receipt.model_votes:
                    connection.execute(
                        """INSERT INTO session_model_ensemble_votes
                           VALUES(?,?,?,?,?,?,?,?,?,'not_assessed')""",
                        (
                            run.run_id,
                            vote.chunk_ordinal,
                            vote.metric_key,
                            vote.model_key,
                            vote.role.value,
                            vote.state.value,
                            vote.raw_score,
                            len(vote.evidence_fragment_ids),
                            vote.reason_code,
                        ),
                    )
                    connection.executemany(
                        """INSERT INTO session_model_ensemble_vote_fragments
                           VALUES(?,?,?,?,?,?)""",
                        (
                            (
                                run.run_id,
                                vote.chunk_ordinal,
                                vote.metric_key,
                                vote.model_key,
                                ordinal,
                                fragment_id,
                            )
                            for ordinal, fragment_id in enumerate(
                                vote.evidence_fragment_ids
                            )
                        ),
                    )
                connection.executemany(
                    """INSERT INTO session_model_ensemble_chunk_metrics
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        (
                            run.run_id,
                            item.chunk_ordinal,
                            item.metric_key,
                            item.value_state.value,
                            item.numerator,
                            item.denominator,
                            item.rubric_vote.value,
                            item.contributing_nli_votes,
                            item.diagnostic_nli_votes,
                            item.reason_code,
                        )
                        for item in receipt.chunks
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO session_model_ensemble_metrics(
                        run_id,metric_key,value_state,numerator,denominator,
                        numeric_value,known_chunk_count,abstained_chunk_count,
                        unsupported_chunk_count,failed_chunk_count,total_chunk_count,
                        explanation_code,calibration_state,product_metric_eligible
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'not_assessed',0)
                    """,
                    (
                        (
                            run.run_id,
                            item.metric_key,
                            item.value_state.value,
                            item.numerator,
                            item.denominator,
                            item.numeric_value,
                            item.known_chunk_count,
                            item.abstained_chunk_count,
                            item.unsupported_chunk_count,
                            item.failed_chunk_count,
                            item.total_chunk_count,
                            item.explanation_code,
                        )
                        for item in receipt.metrics
                    ),
                )
                selection_fragment_count = sum(
                    len(item.selected_fragment_ids)
                    for item in receipt.evidence_selections
                )
                vote_fragment_count = sum(
                    len(item.evidence_fragment_ids) for item in receipt.model_votes
                )
                connection.execute(
                    """INSERT INTO session_model_ensemble_seals
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        run.run_id,
                        _graph_fingerprint(run),
                        receipt.chunk_count,
                        len(receipt.experts),
                        len(receipt.evidence_selections),
                        selection_fragment_count,
                        len(receipt.model_votes),
                        vote_fragment_count,
                        len(receipt.chunks),
                        len(receipt.metrics),
                        to_iso(receipt.completed_at),
                    ),
                )
                self._insert_metric_projection(connection, run)
                self._insert_predictive_projection(connection, run)
                hydrated = self._hydrate(connection, run.run_id)
                if hydrated is None or _graph_fingerprint(hydrated) != _graph_fingerprint(run):
                    raise DatabaseInvariantError(
                        "stored model ensemble graph failed exact rehydration"
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def save_metric_projection(
        self,
        run: SessionModelEnsembleRunRecord,
        *,
        authority: SessionModelEnsemblePersistenceAuthority | None = None,
    ) -> None:
        """Append the current typed projection to an already sealed legacy run."""

        self._ensure_initialized()
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if authority is not None:
                    active = connection.execute(
                        """SELECT 1 FROM session_model_ensemble_watches
                           WHERE watch_id=? AND state='running'
                             AND generation=? AND lease_owner=? AND lease_token=?
                             AND lease_expires_at>? AND session_id=? AND provider=?
                             AND latest_run_id=?""",
                        (
                            authority.watch_id,
                            authority.generation,
                            authority.owner,
                            authority.token,
                            to_iso(authority.observed_at),
                            run.session_id,
                            run.provider.value,
                            run.run_id,
                        ),
                    ).fetchone()
                    if active is None or authority.prior_run_id != run.run_id:
                        raise DatabaseInvariantError(
                            "model ensemble watch projection authority is no longer active"
                        )
                stored = self._hydrate(connection, run.run_id)
                if stored is None or _graph_fingerprint(stored) != _graph_fingerprint(run):
                    raise DatabaseInvariantError(
                        "typed metric projection does not match the sealed ensemble run"
                    )
                self._insert_metric_projection(connection, run)
                self._insert_predictive_projection(connection, run)
                hydrated = self._hydrate(connection, run.run_id)
                if (
                    hydrated is None
                    or hydrated.receipt.metric_projection_version
                    != run.receipt.metric_projection_version
                    or hydrated.receipt.metric_projection_completed_at
                    != run.receipt.metric_projection_completed_at
                    or hydrated.receipt.typed_metrics != run.receipt.typed_metrics
                ):
                    raise DatabaseInvariantError(
                        "typed metric projection failed exact rehydration"
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _insert_metric_projection(connection, run: SessionModelEnsembleRunRecord) -> None:
        receipt = run.receipt
        if not receipt.typed_metrics:
            return
        if (
            receipt.metric_projection_version
            != MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION
            or receipt.metric_projection_completed_at is None
        ):
            raise DatabaseInvariantError("typed metric projection identity is incomplete")
        connection.executemany(
            """
            INSERT INTO session_model_ensemble_typed_metrics(
                run_id,projection_version,metric_key,metric_version,value_state,
                numerator,denominator,numeric_value,observed_message_count,
                eligible_message_count,coverage,explanation_code,error_code,
                projection_source,metric_schema_version,engine_version,
                algorithm_id,algorithm_version,rubric_version,
                calibration_state,product_metric_eligible
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'deterministic_typed_contract',
                     ?,?,?,?,?,'not_assessed',0)
            """,
            (
                (
                    run.run_id,
                    receipt.metric_projection_version,
                    item.metric_key,
                    item.metric_version,
                    item.value_state.value,
                    item.numerator,
                    item.denominator,
                    item.numeric_value,
                    item.observed_message_count,
                    item.eligible_message_count,
                    item.coverage,
                    item.explanation_code,
                    item.error_code,
                    item.metric_schema_version,
                    item.engine_version,
                    item.algorithm_id,
                    item.algorithm_version,
                    item.rubric_version,
                )
                for item in receipt.typed_metrics
            ),
        )
        connection.execute(
            """INSERT INTO session_model_ensemble_typed_metric_seals(
                   run_id,projection_version,metric_count,projection_fingerprint,
                   projected_at
               ) VALUES(?,?,?,?,?)""",
            (
                run.run_id,
                receipt.metric_projection_version,
                len(receipt.typed_metrics),
                _metric_projection_fingerprint(receipt),
                to_iso(receipt.metric_projection_completed_at),
            ),
        )

    @staticmethod
    def _insert_predictive_projection(
        connection, run: SessionModelEnsembleRunRecord
    ) -> None:
        projection = run.receipt.predictive_projection
        if projection is None:
            return
        connection.executemany(
            """
            INSERT INTO session_model_ensemble_predictive_metrics(
                run_id,projection_version,metric_key,target,state,
                mean,median,q05,q25,q75,q95,applicability_probability,
                pending_probability,model_disagreement,effective_observation_count,
                model_set_version,calibration_version,contract_version,
                contract_fingerprint,factor_count,density_bin_count,
                product_metric_eligible
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
            """,
            (
                (
                    run.run_id,
                    projection.projection_version,
                    item.metric_key,
                    item.target.value,
                    item.state.value,
                    item.mean,
                    item.median,
                    item.q05,
                    item.q25,
                    item.q75,
                    item.q95,
                    item.applicability_probability,
                    item.pending_probability,
                    item.model_disagreement,
                    item.effective_observation_count,
                    item.model_set_version,
                    item.calibration_version,
                    item.contract_version,
                    item.contract_fingerprint,
                    len(item.factors),
                    len(item.density_bins),
                )
                for item in projection.metrics
            ),
        )
        connection.executemany(
            """
            INSERT INTO session_model_ensemble_predictive_factors(
                run_id,projection_version,metric_key,factor_ordinal,
                factor_key,scale,weight,applicability_probability,
                present_probability,neutral_probability,absent_probability,
                expert_count,critical
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                (
                    run.run_id,
                    projection.projection_version,
                    metric.metric_key,
                    ordinal,
                    factor.factor_key,
                    factor.scale.value,
                    factor.weight,
                    factor.applicability_probability,
                    factor.present_probability,
                    factor.neutral_probability,
                    factor.absent_probability,
                    factor.expert_count,
                    int(factor.critical),
                )
                for metric in projection.metrics
                for ordinal, factor in enumerate(metric.factors)
            ),
        )
        connection.executemany(
            """
            INSERT INTO session_model_ensemble_predictive_density_bins(
                run_id,projection_version,metric_key,bin_ordinal,probability_mass
            ) VALUES(?,?,?,?,?)
            """,
            (
                (
                    run.run_id,
                    projection.projection_version,
                    metric.metric_key,
                    ordinal,
                    probability,
                )
                for metric in projection.metrics
                for ordinal, probability in enumerate(metric.density_bins)
            ),
        )
        connection.executemany(
            """
            INSERT INTO session_model_ensemble_predictive_model_stages(
                run_id,projection_version,stage_ordinal,model_key,repository_id,
                revision,status,error_code,device,quantization,
                inference_latency_ms,peak_accelerator_memory_mb,process_rss_mb,
                unloaded_after_stage
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)
            """,
            (
                (
                    run.run_id,
                    projection.projection_version,
                    ordinal,
                    item.model_key,
                    item.repository_id,
                    item.revision,
                    item.status,
                    item.error_code,
                    item.device,
                    item.quantization,
                    item.inference_latency_ms,
                    item.peak_accelerator_memory_mb,
                    item.process_rss_mb,
                )
                for ordinal, item in enumerate(projection.model_stages)
            ),
        )
        factor_count = sum(len(item.factors) for item in projection.metrics)
        density_count = sum(len(item.density_bins) for item in projection.metrics)
        connection.execute(
            """
            INSERT INTO session_model_ensemble_predictive_metric_seals(
                run_id,projection_version,registry_version,model_set_version,
                metric_count,factor_count,density_bin_count,stage_count,
                sample_count,projection_fingerprint,projected_at,local_only,
                content_persisted,calibrated_as_truth
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,0,0)
            """,
            (
                run.run_id,
                projection.projection_version,
                projection.contract_registry_version,
                projection.model_set_version,
                len(projection.metrics),
                factor_count,
                density_count,
                len(projection.model_stages),
                projection.sample_count,
                _predictive_projection_fingerprint(projection),
                to_iso(projection.projected_at),
            ),
        )

    def get(self, run_id: str) -> SessionModelEnsembleRunRecord | None:
        self._ensure_initialized()
        require_safe_id(run_id)
        with self._connection_scope(readonly=True) as connection:
            return self._hydrate(connection, run_id)

    def get_latest(self, session_id: str) -> SessionModelEnsembleRunRecord | None:
        self._ensure_initialized()
        require_safe_id(session_id)
        with self._connection_scope(readonly=True) as connection:
            row = connection.execute(
                """SELECT r.run_id FROM session_model_ensemble_runs r
                   JOIN session_model_ensemble_seals s ON s.run_id=r.run_id
                   WHERE r.session_id=?
                   ORDER BY r.completed_at DESC,r.run_id DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
            return None if row is None else self._hydrate(connection, row["run_id"])

    def delete_for_privacy(self, run_id: str) -> bool:
        self._ensure_initialized()
        require_safe_id(run_id)
        with self._connection_scope() as connection:
            try:
                connection.execute("PRAGMA secure_delete=ON")
                connection.execute("BEGIN IMMEDIATE")
                target = connection.execute(
                    "SELECT session_id FROM session_model_ensemble_runs WHERE run_id=?",
                    (run_id,),
                ).fetchone()
                if target is None:
                    connection.rollback()
                    return False
                # Privacy removal is session-wide for shadow-model derivatives.
                # Disable and revoke the standing watch before erasing the
                # graph.  A watch-owned save validates this lease in the same
                # BEGIN IMMEDIATE transaction, so an in-flight generation can
                # neither recreate nor publish decisions derived from the
                # erased receipt.  Erasing all ensemble runs for the selected
                # session also closes the opposite transaction ordering, where
                # an in-flight descendant committed immediately before this
                # privacy transaction acquired the writer lock.
                connection.execute(
                    """UPDATE session_model_ensemble_watches
                       SET state='disabled',latest_run_id=NULL,
                           latest_input_fingerprint=NULL,
                           last_error_code='privacy_deleted',
                           lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
                       WHERE session_id=?""",
                    (target["session_id"],),
                )
                deleted = connection.execute(
                    "DELETE FROM session_model_ensemble_runs WHERE session_id=?",
                    (target["session_id"],),
                ).rowcount
                connection.commit()
                checkpoint = connection.execute(
                    "PRAGMA wal_checkpoint(TRUNCATE)"
                ).fetchone()
                if checkpoint is None or tuple(int(value) for value in checkpoint) != (
                    0,
                    0,
                    0,
                ):
                    raise DatabaseInvariantError(
                        "model ensemble privacy deletion committed; WAL purge pending"
                    )
                return bool(deleted)
            except Exception:
                connection.rollback()
                raise

    def _hydrate(self, connection, run_id: str) -> SessionModelEnsembleRunRecord | None:
        row = connection.execute(
            """SELECT r.* FROM session_model_ensemble_runs r
               JOIN session_model_ensemble_seals s ON s.run_id=r.run_id
               WHERE r.run_id=?""",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        chunks = tuple(
            ModelEnsembleChunkReceipt(
                ordinal=item["chunk_ordinal"],
                chunk_fingerprint=item["chunk_fingerprint"],
                source_message_count=item["source_message_count"],
                fragment_count=item["fragment_count"],
                character_count=item["character_count"],
            )
            for item in connection.execute(
                """SELECT * FROM session_model_ensemble_chunks WHERE run_id=?
                   ORDER BY chunk_ordinal""",
                (run_id,),
            ).fetchall()
        )
        experts = tuple(
            ModelExpertReceipt(
                identity=ModelExpertIdentity(
                    ordinal=item["model_ordinal"],
                    model_key=item["model_key"],
                    role=ModelExpertRole(item["role"]),
                    repository_id=item["repository_id"],
                    revision=item["revision"],
                    tokenizer_id=item["tokenizer_id"],
                    license_spdx=item["license_spdx"],
                    backend_key=item["backend_key"],
                    contributes_to_decision=bool(item["contributes_to_decision"]),
                ),
                status=ModelExpertStatus(item["status"]),
                error_code=item["error_code"],
                device=item["device"],
                inference_latency_ms=item["inference_latency_ms"],
                peak_accelerator_memory_mb=item["peak_accelerator_memory_mb"],
                process_rss_mb=item["process_rss_mb"],
            )
            for item in connection.execute(
                """SELECT * FROM session_model_ensemble_experts WHERE run_id=?
                   ORDER BY model_ordinal""",
                (run_id,),
            ).fetchall()
        )
        selections = []
        for item in connection.execute(
            """SELECT * FROM session_model_ensemble_evidence_selections
               WHERE run_id=? ORDER BY chunk_ordinal,metric_key,model_key""",
            (run_id,),
        ).fetchall():
            refs = tuple(
                ref["fragment_id"]
                for ref in connection.execute(
                    """SELECT fragment_id FROM session_model_ensemble_selection_fragments
                       WHERE run_id=? AND chunk_ordinal=? AND metric_key=? AND model_key=?
                       ORDER BY fragment_ordinal""",
                    (run_id, item["chunk_ordinal"], item["metric_key"], item["model_key"]),
                ).fetchall()
            )
            if len(refs) != item["selected_count"]:
                raise DatabaseInvariantError("model ensemble selection graph is incomplete")
            selections.append(
                ModelEvidenceSelectionReceipt(
                    chunk_ordinal=item["chunk_ordinal"],
                    metric_key=item["metric_key"],
                    model_key=item["model_key"],
                    role=ModelExpertRole(item["role"]),
                    candidate_count=item["candidate_count"],
                    selected_fragment_ids=refs,
                    ranking_fingerprint=item["ranking_fingerprint"],
                    top_raw_score=item["top_raw_score"],
                )
            )
        votes = []
        for item in connection.execute(
            """SELECT * FROM session_model_ensemble_votes WHERE run_id=?
               ORDER BY chunk_ordinal,metric_key,model_key""",
            (run_id,),
        ).fetchall():
            refs = tuple(
                ref["fragment_id"]
                for ref in connection.execute(
                    """SELECT fragment_id FROM session_model_ensemble_vote_fragments
                       WHERE run_id=? AND chunk_ordinal=? AND metric_key=? AND model_key=?
                       ORDER BY fragment_ordinal""",
                    (run_id, item["chunk_ordinal"], item["metric_key"], item["model_key"]),
                ).fetchall()
            )
            if len(refs) != item["evidence_count"]:
                raise DatabaseInvariantError("model ensemble vote graph is incomplete")
            votes.append(
                ModelMetricVote(
                    chunk_ordinal=item["chunk_ordinal"],
                    metric_key=item["metric_key"],
                    model_key=item["model_key"],
                    role=ModelExpertRole(item["role"]),
                    state=ModelVoteState(item["state"]),
                    raw_score=item["raw_score"],
                    evidence_fragment_ids=refs,
                    reason_code=item["reason_code"],
                )
            )
        chunk_metrics = tuple(
            ChunkMetricCommitteeReceipt(
                chunk_ordinal=item["chunk_ordinal"],
                metric_key=item["metric_key"],
                value_state=MetricValueState(item["value_state"]),
                numerator=item["numerator"],
                denominator=item["denominator"],
                rubric_vote=ModelVoteState(item["rubric_vote"]),
                contributing_nli_votes=item["contributing_nli_votes"],
                diagnostic_nli_votes=item["diagnostic_nli_votes"],
                reason_code=item["reason_code"],
            )
            for item in connection.execute(
                """SELECT * FROM session_model_ensemble_chunk_metrics
                   WHERE run_id=? ORDER BY chunk_ordinal,metric_key""",
                (run_id,),
            ).fetchall()
        )
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
            for item in connection.execute(
                """SELECT * FROM session_model_ensemble_metrics
                   WHERE run_id=? ORDER BY metric_key""",
                (run_id,),
            ).fetchall()
        )
        projection_seal = connection.execute(
            """SELECT * FROM session_model_ensemble_typed_metric_seals
               WHERE run_id=? AND projection_version=?""",
            (run_id, MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION),
        ).fetchone()
        typed_metrics: tuple[SessionModelEnsembleTypedMetricReceipt, ...] = ()
        projection_completed_at = None
        if projection_seal is not None:
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
                    product_metric_eligible=bool(item["product_metric_eligible"]),
                )
                for item in connection.execute(
                    """SELECT * FROM session_model_ensemble_typed_metrics
                       WHERE run_id=? AND projection_version=? ORDER BY metric_key""",
                    (run_id, MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION),
                ).fetchall()
            )
            projection_completed_at = from_iso(projection_seal["projected_at"])
        predictive_seal = connection.execute(
            """SELECT * FROM session_model_ensemble_predictive_metric_seals
               WHERE run_id=? AND projection_version=?""",
            (run_id, PROBABILISTIC_METRIC_PROJECTION_VERSION),
        ).fetchone()
        predictive_projection = None
        if predictive_seal is not None:
            predictive_metrics = []
            for item in connection.execute(
                """SELECT * FROM session_model_ensemble_predictive_metrics
                   WHERE run_id=? AND projection_version=? ORDER BY metric_key""",
                (run_id, PROBABILISTIC_METRIC_PROJECTION_VERSION),
            ).fetchall():
                factors = tuple(
                    PredictiveFactorContribution(
                        factor_key=factor["factor_key"],
                        scale=FactorScale(factor["scale"]),
                        weight=factor["weight"],
                        applicability_probability=factor[
                            "applicability_probability"
                        ],
                        present_probability=factor["present_probability"],
                        neutral_probability=factor["neutral_probability"],
                        absent_probability=factor["absent_probability"],
                        expert_count=factor["expert_count"],
                        critical=bool(factor["critical"]),
                    )
                    for factor in connection.execute(
                        """SELECT * FROM session_model_ensemble_predictive_factors
                           WHERE run_id=? AND projection_version=? AND metric_key=?
                           ORDER BY factor_ordinal""",
                        (
                            run_id,
                            PROBABILISTIC_METRIC_PROJECTION_VERSION,
                            item["metric_key"],
                        ),
                    ).fetchall()
                )
                density = tuple(
                    float(bin_row["probability_mass"])
                    for bin_row in connection.execute(
                        """SELECT probability_mass
                           FROM session_model_ensemble_predictive_density_bins
                           WHERE run_id=? AND projection_version=? AND metric_key=?
                           ORDER BY bin_ordinal""",
                        (
                            run_id,
                            PROBABILISTIC_METRIC_PROJECTION_VERSION,
                            item["metric_key"],
                        ),
                    ).fetchall()
                )
                predictive_metrics.append(
                    SessionPredictiveMetricReceipt(
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
                        density_bins=density,
                        factors=factors,
                        product_metric_eligible=bool(
                            item["product_metric_eligible"]
                        ),
                    )
                )
            predictive_stages = tuple(
                PredictiveModelStageReceipt(
                    model_key=item["model_key"],
                    repository_id=item["repository_id"],
                    revision=item["revision"],
                    status=item["status"],
                    error_code=item["error_code"],
                    device=item["device"],
                    quantization=item["quantization"],
                    inference_latency_ms=item["inference_latency_ms"],
                    peak_accelerator_memory_mb=item[
                        "peak_accelerator_memory_mb"
                    ],
                    process_rss_mb=item["process_rss_mb"],
                    unloaded_after_stage=bool(item["unloaded_after_stage"]),
                )
                for item in connection.execute(
                    """SELECT * FROM session_model_ensemble_predictive_model_stages
                       WHERE run_id=? AND projection_version=? ORDER BY stage_ordinal""",
                    (run_id, PROBABILISTIC_METRIC_PROJECTION_VERSION),
                ).fetchall()
            )
            metrics_by_key = {
                item.metric_key: item for item in predictive_metrics
            }
            predictive_projection = SessionPredictiveMetricProjection(
                projection_version=predictive_seal["projection_version"],
                contract_registry_version=predictive_seal["registry_version"],
                model_set_version=predictive_seal["model_set_version"],
                projected_at=from_iso(predictive_seal["projected_at"]),
                metrics=tuple(
                    metrics_by_key[item.metric_key]
                    for item in PROBABILISTIC_METRIC_CONTRACTS
                ),
                model_stages=predictive_stages,
                sample_count=predictive_seal["sample_count"],
                local_only=bool(predictive_seal["local_only"]),
                content_persisted=bool(predictive_seal["content_persisted"]),
                calibrated_as_truth=bool(predictive_seal["calibrated_as_truth"]),
            )
        receipt = SessionModelEnsembleReceipt(
            plan_version=row["plan_version"],
            plan_fingerprint=row["plan_fingerprint"],
            source_window_fingerprint=row["source_window_fingerprint"],
            source_coverage_state=SourceCoverageState(row["source_coverage_state"]),
            chunk_count=row["chunk_count"],
            model_count=row["model_count"],
            chunk_plan=chunks,
            chunks=chunk_metrics,
            metrics=metrics,
            metric_projection_version=(
                None
                if projection_seal is None
                else MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION
            ),
            metric_projection_completed_at=projection_completed_at,
            typed_metrics=typed_metrics,
            predictive_projection=predictive_projection,
            experts=experts,
            evidence_selections=tuple(selections),
            model_votes=tuple(votes),
            created_at=from_iso(row["created_at"]),
            completed_at=from_iso(row["completed_at"]),
        )
        record = SessionModelEnsembleRunRecord(
            run_id=row["run_id"],
            session_id=row["session_id"],
            request_fingerprint=row["request_fingerprint"],
            input_fingerprint=row["input_fingerprint"],
            provider=Provider(row["provider"]),
            provider_version=row["provider_version"],
            adapter_version=row["adapter_version"],
            source_schema_version=row["source_schema_version"],
            content_schema_version=row["content_schema_version"],
            redactor_version=row["redactor_version"],
            consent_policy_version=row["consent_policy_version"],
            receipt=receipt,
        )
        seal = connection.execute(
            "SELECT graph_fingerprint FROM session_model_ensemble_seals WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if seal is None or seal["graph_fingerprint"] != _graph_fingerprint(record):
            raise DatabaseInvariantError("model ensemble graph seal is invalid")
        if projection_seal is not None and (
            int(projection_seal["metric_count"]) != len(typed_metrics)
            or projection_seal["projection_fingerprint"]
            != _metric_projection_fingerprint(record.receipt)
        ):
            raise DatabaseInvariantError("typed metric projection seal is invalid")
        if predictive_seal is not None and (
            predictive_projection is None
            or int(predictive_seal["metric_count"])
            != len(predictive_projection.metrics)
            or int(predictive_seal["factor_count"])
            != sum(len(item.factors) for item in predictive_projection.metrics)
            or int(predictive_seal["density_bin_count"])
            != sum(
                len(item.density_bins) for item in predictive_projection.metrics
            )
            or int(predictive_seal["stage_count"])
            != len(predictive_projection.model_stages)
            or predictive_seal["projection_fingerprint"]
            != _predictive_projection_fingerprint(predictive_projection)
        ):
            raise DatabaseInvariantError("predictive metric projection seal is invalid")
        return record


__all__ = ["SqliteSessionModelEnsembleRepository"]
