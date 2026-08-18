"""Normalized, content-free persistence for local measured/predictive analysis."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
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
from ...application.analysis.metric_contract_v2 import (
    DenominatorBasis,
    EvidenceAuthority,
    METRIC_CONTRACTS_V2,
    MetricValueStateV2,
)
from ...application.analysis.metric_projection_v2 import (
    METRIC_PROJECTION_V2_VERSION_2,
    METRIC_PROJECTION_V2_VERSION_3,
    MetricStateV2,
    OpportunityStatistics,
    _issue_metric_state_projection,
)
from ...application.analysis.metric_publication_v2 import (
    METRIC_PUBLICATION_V2_KEY,
    METRIC_PUBLICATION_V2_VERSION,
    MetricPublicationSource,
    MetricPublicationV2,
    metric_publication_v2_fingerprint,
    publish_metric_states_v2,
)
from ...application.analysis.session_model_ensemble import (
    SessionModelEnsemblePersistenceAuthority,
    SessionModelEnsembleRepository,
    SessionModelEnsembleRunRecord,
)
from ...application.analysis.semantic_units import (
    SEMANTIC_UNIT_CONTRACT_VERSION,
    SEMANTIC_UNIT_SCHEMA_VERSION,
    SemanticUnitReceipt,
    SemanticUnitReconciliation,
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
    receipt.pop("metric_publication_v2", None)
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


#: Sidecar tables per projection identity, newest first.  The r1 pair (frozen
#: at MIGRATION_40) and the r2 pair (MIGRATION_41) never gain a row from current
#: code; the r3 pair added by MIGRATION_42 receives every new publication.  All
#: three stay readable, and a run carries at most one of them.
METRIC_V2_SIDECARS = (
    (
        METRIC_PROJECTION_V2_VERSION_3,
        "session_model_ensemble_metric_states_v2_r3",
        "session_model_ensemble_metric_publication_v2_seals_r3",
    ),
    (
        METRIC_PROJECTION_V2_VERSION_2,
        "session_model_ensemble_metric_states_v2_r2",
        "session_model_ensemble_metric_publication_v2_seals_r2",
    ),
    (
        "metric-contract-v2-projection-1",
        "session_model_ensemble_metric_states_v2",
        "session_model_ensemble_metric_publication_v2_seals",
    ),
)


def _metric_v2_tables(projection_version: str) -> tuple[str, str]:
    for version, states_table, seals_table in METRIC_V2_SIDECARS:
        if projection_version == version:
            return states_table, seals_table
    raise DatabaseInvariantError("metric V2 projection identity is unsupported")


def _metric_publication_v2_fingerprint(
    publication: MetricPublicationV2,
) -> str:
    """Delegate to the one canonical definition the API projection also reads."""

    return metric_publication_v2_fingerprint(publication)


def _semantic_unit_reconciliation_fingerprint(
    reconciliation: SemanticUnitReconciliation,
) -> str:
    """Seal an already content-free canonical semantic-unit projection."""

    return hashlib.sha256(
        json.dumps(
            reconciliation.model_dump(mode="json"),
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
        semantic_units: SemanticUnitReconciliation | None = None,
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
                self._insert_metric_publication_v2(connection, run)
                self._insert_predictive_projection(connection, run)
                self._insert_semantic_unit_reconciliation(
                    connection,
                    run,
                    semantic_units,
                )
                hydrated = self._hydrate(connection, run.run_id)
                if (
                    hydrated is None
                    or _graph_fingerprint(hydrated) != _graph_fingerprint(run)
                    or hydrated.receipt.metric_publication_v2
                    != run.receipt.metric_publication_v2
                ):
                    raise DatabaseInvariantError(
                        "stored model ensemble graph failed exact rehydration"
                    )
                hydrated_semantic_units = self._hydrate_semantic_units(
                    connection,
                    run.run_id,
                )
                if hydrated_semantic_units != semantic_units:
                    raise DatabaseInvariantError(
                        "stored semantic-unit sidecar failed exact rehydration"
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
                self._insert_metric_publication_v2(connection, run)
                self._insert_predictive_projection(connection, run)
                hydrated = self._hydrate(connection, run.run_id)
                if (
                    hydrated is None
                    or hydrated.receipt.metric_projection_version
                    != run.receipt.metric_projection_version
                    or hydrated.receipt.metric_projection_completed_at
                    != run.receipt.metric_projection_completed_at
                    or hydrated.receipt.typed_metrics != run.receipt.typed_metrics
                    or hydrated.receipt.metric_publication_v2
                    != run.receipt.metric_publication_v2
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

    @staticmethod
    def _insert_metric_publication_v2(
        connection,
        run: SessionModelEnsembleRunRecord,
    ) -> None:
        publication = run.receipt.metric_publication_v2
        if publication is None:
            return
        if (
            publication.source is not MetricPublicationSource.LIVE_PROJECTION
            or publication.compatibility_preview
            or not publication.canonical_live_snapshot
            or publication.model_stage_consumed
        ):
            raise DatabaseInvariantError(
                "metric V2 sidecar must be a canonical live measured publication"
            )
        # Historical r1 and r2 rows are read-only.  Accepting a superseded
        # model here would let current code mint a fresh value under a frozen
        # producer identity, defeating the append-only correction even if the
        # SQL sidecars stayed separate.  Every current write must use r3.
        if publication.projection_version != METRIC_PROJECTION_V2_VERSION_3:
            raise DatabaseInvariantError(
                "new metric V2 publications require the current projection identity"
            )
        states_table, seals_table = _metric_v2_tables(
            METRIC_PROJECTION_V2_VERSION_3
        )
        connection.executemany(
            f"""
            INSERT INTO {states_table}(
                run_id,metric_ordinal,registry_version,projection_version,
                metric_key,contract_version,contract_fingerprint,
                evidence_authority,value_state,explanation_code,numerator,
                denominator,numeric_value,censoring_lower_bound,
                censoring_upper_bound,denominator_basis,opportunity_unit_kind,
                capability_available,source_complete,eligible_count,met_count,
                not_met_count,pending_count,unknown_count,
                superseded_excluded_count,distinct_owner_count,
                product_metric_eligible
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
            """,
            (
                (
                    run.run_id,
                    ordinal,
                    publication.registry_version,
                    publication.projection_version,
                    item.state.metric_key,
                    item.state.contract_version,
                    item.state.contract_fingerprint,
                    item.state.evidence_authority.value,
                    item.state.value_state.value,
                    item.state.explanation_code,
                    item.state.numerator,
                    item.state.denominator,
                    item.state.numeric_value,
                    item.state.censoring_lower_bound,
                    item.state.censoring_upper_bound,
                    item.state.statistics.denominator_basis.value,
                    (
                        None
                        if item.state.statistics.opportunity_unit_kind is None
                        else item.state.statistics.opportunity_unit_kind.value
                    ),
                    int(item.state.statistics.capability_available),
                    int(item.state.statistics.source_complete),
                    item.state.statistics.eligible_count,
                    item.state.statistics.met_count,
                    item.state.statistics.not_met_count,
                    item.state.statistics.pending_count,
                    item.state.statistics.unknown_count,
                    item.state.statistics.superseded_excluded_count,
                    item.state.statistics.distinct_owner_count,
                )
                for ordinal, item in enumerate(publication.metrics)
            ),
        )
        projected_at = (
            run.receipt.metric_projection_completed_at
            or run.receipt.completed_at
        )
        connection.execute(
            f"""
            INSERT INTO {seals_table}(
                run_id,publication_key,publication_version,registry_version,
                contract_set_fingerprint,projection_version,
                guidance_contract_version,guidance_template_catalog_version,
                source,canonical_live_snapshot,model_stage_consumed,
                compatibility_preview,metric_count,known_count,pending_count,
                unknown_count,not_applicable_count,abstained_count,
                execution_error_count,objective_measured_count,
                projection_fingerprint,projected_at,local_only,
                content_persisted,product_metric_eligible
            ) VALUES(?,?,?,?,?,?,?,?,?,1,0,0,?,?,?,?,?,?,?,?,?,?,1,0,0)
            """,
            (
                run.run_id,
                publication.publication_key,
                publication.publication_version,
                publication.registry_version,
                publication.contract_set_fingerprint,
                publication.projection_version,
                publication.guidance_contract_version,
                publication.guidance_template_catalog_version,
                publication.source.value,
                len(publication.metrics),
                publication.known_count,
                publication.pending_count,
                publication.unknown_count,
                publication.not_applicable_count,
                publication.abstained_count,
                publication.execution_error_count,
                publication.objective_measured_count,
                _metric_publication_v2_fingerprint(publication),
                to_iso(projected_at),
            ),
        )

    @staticmethod
    def _insert_semantic_unit_reconciliation(
        connection,
        run: SessionModelEnsembleRunRecord,
        reconciliation: SemanticUnitReconciliation | None,
    ) -> None:
        if reconciliation is None:
            return
        if (
            reconciliation.schema_version != SEMANTIC_UNIT_SCHEMA_VERSION
            or reconciliation.contract_version != SEMANTIC_UNIT_CONTRACT_VERSION
            or reconciliation.provider is not run.provider
            or reconciliation.session_id != run.session_id
            or reconciliation.analysis_window_fingerprint != run.input_fingerprint
        ):
            raise DatabaseInvariantError(
                "semantic-unit sidecar does not match the ensemble run"
            )
        appended_ids = {item.receipt_id for item in reconciliation.appended}
        connection.executemany(
            """
            INSERT INTO session_model_ensemble_semantic_unit_heads(
                run_id,unit_ordinal,schema_version,contract_version,
                unit_kind_version,receipt_id,unit_id,unit_digest,revision,
                previous_receipt_id,kind,lifecycle,extraction_basis,
                owner_source_digest,source_version_digest,source_count,
                first_sequence,closed_at_sequence,
                superseded_by_source_digest,superseded_by_unit_id,
                owner_role,owner_message_kind,rework_class,disposition
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                (
                    run.run_id,
                    ordinal,
                    item.schema_version,
                    item.contract_version,
                    item.unit_kind_version,
                    item.receipt_id,
                    item.unit_id,
                    item.unit_digest,
                    item.revision,
                    item.previous_receipt_id,
                    item.kind.value,
                    item.lifecycle.value,
                    item.extraction_basis.value,
                    item.owner_source_digest,
                    item.source_version_digest,
                    len(item.source_digests),
                    item.first_sequence,
                    item.closed_at_sequence,
                    item.superseded_by_source_digest,
                    item.superseded_by_unit_id,
                    None if item.owner_role is None else item.owner_role.value,
                    (
                        None
                        if item.owner_message_kind is None
                        else item.owner_message_kind.value
                    ),
                    None if item.rework_class is None else item.rework_class.value,
                    "appended" if item.receipt_id in appended_ids else "unchanged",
                )
                for ordinal, item in enumerate(reconciliation.heads)
            ),
        )
        connection.executemany(
            """
            INSERT INTO session_model_ensemble_semantic_unit_sources(
                run_id,unit_id,source_ordinal,source_digest
            ) VALUES(?,?,?,?)
            """,
            (
                (run.run_id, item.unit_id, ordinal, source_digest)
                for item in reconciliation.heads
                for ordinal, source_digest in enumerate(item.source_digests)
            ),
        )
        connection.execute(
            """
            INSERT INTO session_model_ensemble_semantic_unit_seals(
                run_id,schema_version,contract_version,reconciliation_id,
                analysis_window_fingerprint,source_complete,head_count,
                appended_count,unchanged_count,retained_unobserved_unit_count,
                reconciliation_fingerprint,sealed_at,local_only,content_persisted
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,0)
            """,
            (
                run.run_id,
                reconciliation.schema_version,
                reconciliation.contract_version,
                reconciliation.reconciliation_id,
                reconciliation.analysis_window_fingerprint,
                int(reconciliation.source_complete),
                len(reconciliation.heads),
                len(reconciliation.appended),
                len(reconciliation.unchanged_receipt_ids),
                reconciliation.retained_unobserved_unit_count,
                _semantic_unit_reconciliation_fingerprint(reconciliation),
                to_iso(run.receipt.completed_at),
            ),
        )

    def get(self, run_id: str) -> SessionModelEnsembleRunRecord | None:
        # Hydrating one run reads the seal, the metrics, the typed and
        # predictive sidecars, the semantic-unit sidecar, and whichever V2
        # projection sidecar the run carries.  Outside a transaction those are
        # separate read snapshots, so a privacy deletion committing between
        # them could return a head whose children were already erased.  A
        # deferred read transaction pins all of them to one snapshot;
        # ``query_only`` is on for this scope, so no writer lock is taken and a
        # concurrent writer is never blocked.
        self._ensure_initialized()
        require_safe_id(run_id)
        with self._connection_scope(readonly=True) as connection:
            try:
                connection.execute("BEGIN")
                record = self._hydrate(connection, run_id)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return record

    def get_latest(self, session_id: str) -> SessionModelEnsembleRunRecord | None:
        self._ensure_initialized()
        require_safe_id(session_id)
        with self._connection_scope(readonly=True) as connection:
            try:
                connection.execute("BEGIN")
                row = connection.execute(
                    """SELECT r.run_id FROM session_model_ensemble_runs r
                       JOIN session_model_ensemble_seals s ON s.run_id=r.run_id
                       WHERE r.session_id=?
                       ORDER BY r.completed_at DESC,r.run_id DESC LIMIT 1""",
                    (session_id,),
                ).fetchone()
                record = (
                    None if row is None else self._hydrate(connection, row["run_id"])
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return record

    def get_semantic_unit_reconciliation(
        self,
        run_id: str,
    ) -> SemanticUnitReconciliation | None:
        """Read the immutable semantic-unit sidecar for one run, if present."""

        self._ensure_initialized()
        require_safe_id(run_id)
        with self._connection_scope(readonly=True) as connection:
            try:
                connection.execute("BEGIN")
                reconciliation = self._hydrate_semantic_units(connection, run_id)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return reconciliation

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
                privacy_stamp = to_iso(datetime.now(UTC))
                # Privacy removal is session-wide for shadow-model derivatives.
                # Disable and revoke the standing watch before erasing the
                # graph.  A watch-owned save validates this lease in the same
                # BEGIN IMMEDIATE transaction, so an in-flight generation can
                # neither recreate nor publish decisions derived from the
                # erased receipt.  Erasing all ensemble runs for the selected
                # session also closes the opposite transaction ordering, where
                # an in-flight descendant committed immediately before this
                # privacy transaction acquired the writer lock.
                running_attempt_ids = tuple(
                    row["attempt_id"]
                    for row in connection.execute(
                        """SELECT attempt.attempt_id
                           FROM session_model_ensemble_analysis_attempts attempt
                           JOIN session_model_ensemble_watches watch
                             ON watch.watch_id=attempt.watch_id
                           WHERE watch.session_id=? AND attempt.state='running'""",
                        (target["session_id"],),
                    ).fetchall()
                )
                if running_attempt_ids:
                    placeholders = ",".join("?" for _ in running_attempt_ids)
                    connection.execute(
                        """UPDATE session_model_ensemble_analysis_attempts
                           SET state='cancelled',error_code='privacy_deleted',
                               completed_at=?
                           WHERE attempt_id IN ("""
                        + placeholders
                        + ") AND state='running'",
                        (privacy_stamp, *running_attempt_ids),
                    )
                    connection.execute(
                        """INSERT INTO session_model_ensemble_analysis_attempt_seals(
                               attempt_id,contract_version,stage_count,warning_count,
                               sealed_at,local_only,content_persisted
                           )
                           SELECT attempt_id,'model-ensemble-attempt-stage-seal-v1',
                                  stage_count,warning_count,completed_at,1,0
                           FROM session_model_ensemble_analysis_attempts
                           WHERE attempt_id IN ("""
                        + placeholders
                        + ")",
                        running_attempt_ids,
                    )
                connection.execute(
                    """UPDATE session_model_ensemble_watches
                       SET state='disabled',latest_run_id=NULL,
                           latest_input_fingerprint=NULL,
                           last_error_code='privacy_deleted',
                           lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,
                           updated_at=?
                       WHERE session_id=?""",
                    (privacy_stamp, target["session_id"]),
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

    @staticmethod
    def _hydrate_semantic_units(
        connection,
        run_id: str,
    ) -> SemanticUnitReconciliation | None:
        seal = connection.execute(
            """SELECT seal.*,run.session_id,run.provider
               FROM session_model_ensemble_semantic_unit_seals seal
               JOIN session_model_ensemble_runs run ON run.run_id=seal.run_id
               WHERE seal.run_id=?""",
            (run_id,),
        ).fetchone()
        if seal is None:
            return None
        rows = connection.execute(
            """SELECT * FROM session_model_ensemble_semantic_unit_heads
               WHERE run_id=? ORDER BY unit_ordinal""",
            (run_id,),
        ).fetchall()
        heads: list[SemanticUnitReceipt] = []
        dispositions: list[str] = []
        for row in rows:
            sources = tuple(
                item["source_digest"]
                for item in connection.execute(
                    """SELECT source_digest
                       FROM session_model_ensemble_semantic_unit_sources
                       WHERE run_id=? AND unit_id=? ORDER BY source_ordinal""",
                    (run_id, row["unit_id"]),
                ).fetchall()
            )
            if len(sources) != int(row["source_count"]):
                raise DatabaseInvariantError(
                    "semantic-unit source graph is incomplete"
                )
            heads.append(
                SemanticUnitReceipt(
                    schema_version=row["schema_version"],
                    contract_version=row["contract_version"],
                    unit_kind_version=row["unit_kind_version"],
                    provider=Provider(seal["provider"]),
                    session_id=seal["session_id"],
                    receipt_id=row["receipt_id"],
                    unit_id=row["unit_id"],
                    unit_digest=row["unit_digest"],
                    revision=row["revision"],
                    previous_receipt_id=row["previous_receipt_id"],
                    kind=row["kind"],
                    lifecycle=row["lifecycle"],
                    extraction_basis=row["extraction_basis"],
                    owner_source_digest=row["owner_source_digest"],
                    source_digests=sources,
                    source_version_digest=row["source_version_digest"],
                    first_sequence=row["first_sequence"],
                    closed_at_sequence=row["closed_at_sequence"],
                    superseded_by_source_digest=row[
                        "superseded_by_source_digest"
                    ],
                    superseded_by_unit_id=row["superseded_by_unit_id"],
                    owner_role=row["owner_role"],
                    owner_message_kind=row["owner_message_kind"],
                    rework_class=row["rework_class"],
                )
            )
            dispositions.append(row["disposition"])
        appended = tuple(
            item
            for item, disposition in zip(heads, dispositions, strict=True)
            if disposition == "appended"
        )
        unchanged_receipt_ids = tuple(
            sorted(
                item.receipt_id
                for item, disposition in zip(heads, dispositions, strict=True)
                if disposition == "unchanged"
            )
        )
        reconciliation = SemanticUnitReconciliation(
            schema_version=seal["schema_version"],
            contract_version=seal["contract_version"],
            provider=Provider(seal["provider"]),
            session_id=seal["session_id"],
            analysis_window_fingerprint=seal["analysis_window_fingerprint"],
            source_complete=bool(seal["source_complete"]),
            reconciliation_id=seal["reconciliation_id"],
            heads=tuple(heads),
            appended=appended,
            unchanged_receipt_ids=unchanged_receipt_ids,
            retained_unobserved_unit_count=seal[
                "retained_unobserved_unit_count"
            ],
        )
        if (
            int(seal["head_count"]) != len(reconciliation.heads)
            or int(seal["appended_count"]) != len(reconciliation.appended)
            or int(seal["unchanged_count"])
            != len(reconciliation.unchanged_receipt_ids)
            or not bool(seal["local_only"])
            or bool(seal["content_persisted"])
            or seal["reconciliation_fingerprint"]
            != _semantic_unit_reconciliation_fingerprint(reconciliation)
        ):
            raise DatabaseInvariantError("semantic-unit sidecar seal is invalid")
        return reconciliation

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
        # Current repository code is also used by the v38/v39 upgrade fixtures to
        # prove that historical graphs remain readable before MIGRATION_40 is
        # applied.  Missing sidecar tables in those exact legacy schemas mean
        # "no V2 publication", not database corruption.  The r2 sidecar is read
        # first and the r1 sidecar second: a run carries at most one of them,
        # and each keeps the projection identity it was sealed under.
        metric_publication_v2_seal = None
        metric_v2_states_table = None
        for _version, states_table, seals_table in METRIC_V2_SIDECARS:
            present = connection.execute(
                """SELECT COUNT(*) AS table_count FROM sqlite_master
                   WHERE type='table' AND name IN (?,?)""",
                (states_table, seals_table),
            ).fetchone()["table_count"] == 2
            if not present:
                continue
            seal = connection.execute(
                f"SELECT * FROM {seals_table} WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if seal is None:
                continue
            if metric_publication_v2_seal is not None:
                raise DatabaseInvariantError(
                    "a run cannot carry two metric V2 publication identities"
                )
            metric_publication_v2_seal = seal
            metric_v2_states_table = states_table
        metric_publication_v2 = None
        if metric_publication_v2_seal is not None:
            states = tuple(
                MetricStateV2(
                    metric_key=item["metric_key"],
                    registry_version=item["registry_version"],
                    contract_version=item["contract_version"],
                    contract_fingerprint=item["contract_fingerprint"],
                    evidence_authority=EvidenceAuthority(
                        item["evidence_authority"]
                    ),
                    value_state=MetricValueStateV2(item["value_state"]),
                    explanation_code=item["explanation_code"],
                    numerator=item["numerator"],
                    denominator=item["denominator"],
                    numeric_value=item["numeric_value"],
                    censoring_lower_bound=item["censoring_lower_bound"],
                    censoring_upper_bound=item["censoring_upper_bound"],
                    statistics=OpportunityStatistics(
                        metric_key=item["metric_key"],
                        denominator_basis=DenominatorBasis(
                            item["denominator_basis"]
                        ),
                        opportunity_unit_kind=item["opportunity_unit_kind"],
                        capability_available=bool(item["capability_available"]),
                        source_complete=bool(item["source_complete"]),
                        eligible_count=item["eligible_count"],
                        met_count=item["met_count"],
                        not_met_count=item["not_met_count"],
                        pending_count=item["pending_count"],
                        unknown_count=item["unknown_count"],
                        superseded_excluded_count=item[
                            "superseded_excluded_count"
                        ],
                        distinct_owner_count=item["distinct_owner_count"],
                    ),
                    projection_version=item["projection_version"],
                    product_metric_eligible=bool(
                        item["product_metric_eligible"]
                    ),
                )
                for item in connection.execute(
                    f"""SELECT * FROM {metric_v2_states_table}
                        WHERE run_id=? ORDER BY metric_ordinal""",
                    (run_id,),
                ).fetchall()
            )
            live_projection = _issue_metric_state_projection(
                states,
                compatibility=False,
            )
            metric_publication_v2 = publish_metric_states_v2(live_projection)
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
            metric_publication_v2=metric_publication_v2,
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
        if metric_publication_v2_seal is not None and (
            metric_publication_v2 is None
            or metric_publication_v2_seal["publication_key"]
            != METRIC_PUBLICATION_V2_KEY
            or int(metric_publication_v2_seal["publication_version"])
            != METRIC_PUBLICATION_V2_VERSION
            or metric_publication_v2_seal["registry_version"]
            != metric_publication_v2.registry_version
            or metric_publication_v2_seal["contract_set_fingerprint"]
            != metric_publication_v2.contract_set_fingerprint
            or metric_publication_v2_seal["projection_version"]
            != metric_publication_v2.projection_version
            or metric_publication_v2_seal["guidance_contract_version"]
            != metric_publication_v2.guidance_contract_version
            or metric_publication_v2_seal["guidance_template_catalog_version"]
            != metric_publication_v2.guidance_template_catalog_version
            or metric_publication_v2_seal["source"]
            != MetricPublicationSource.LIVE_PROJECTION.value
            or not bool(metric_publication_v2_seal["canonical_live_snapshot"])
            or bool(metric_publication_v2_seal["compatibility_preview"])
            or bool(metric_publication_v2_seal["model_stage_consumed"])
            or int(metric_publication_v2_seal["metric_count"])
            != len(metric_publication_v2.metrics)
            or int(metric_publication_v2_seal["known_count"])
            != metric_publication_v2.known_count
            or int(metric_publication_v2_seal["pending_count"])
            != metric_publication_v2.pending_count
            or int(metric_publication_v2_seal["unknown_count"])
            != metric_publication_v2.unknown_count
            or int(metric_publication_v2_seal["not_applicable_count"])
            != metric_publication_v2.not_applicable_count
            or int(metric_publication_v2_seal["abstained_count"])
            != metric_publication_v2.abstained_count
            or int(metric_publication_v2_seal["execution_error_count"])
            != metric_publication_v2.execution_error_count
            or int(metric_publication_v2_seal["objective_measured_count"])
            != metric_publication_v2.objective_measured_count
            or metric_publication_v2_seal["projection_fingerprint"]
            != _metric_publication_v2_fingerprint(metric_publication_v2)
        ):
            raise DatabaseInvariantError("metric V2 publication seal is invalid")
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
