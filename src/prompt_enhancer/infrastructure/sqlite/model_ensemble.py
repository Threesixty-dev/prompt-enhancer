"""Normalized, content-free persistence for local ten-model shadow analysis."""

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
    SessionModelEnsembleMetricReceipt,
    SessionModelEnsembleReceipt,
    SourceCoverageState,
)
from ...application.analysis.session_model_ensemble import (
    SessionModelEnsembleRepository,
    SessionModelEnsembleRunRecord,
)
from ...application.persistence import MetricValueState
from ...database import DatabaseInvariantError
from ...domain import Provider
from ._common import ConnectionScope, from_iso, require_safe_id, to_iso


def _graph_fingerprint(run: SessionModelEnsembleRunRecord) -> str:
    payload = run.model_dump(mode="json")
    receipt = payload["receipt"]
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


class SqliteSessionModelEnsembleRepository(SessionModelEnsembleRepository):
    def __init__(
        self,
        connection_scope: ConnectionScope,
        ensure_initialized: Callable[[], None],
    ) -> None:
        self._connection_scope = connection_scope
        self._ensure_initialized = ensure_initialized

    def save_completed(self, run: SessionModelEnsembleRunRecord) -> None:
        self._ensure_initialized()
        receipt = run.receipt
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
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
                hydrated = self._hydrate(connection, run.run_id)
                if hydrated is None or _graph_fingerprint(hydrated) != _graph_fingerprint(run):
                    raise DatabaseInvariantError(
                        "stored model ensemble graph failed exact rehydration"
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

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
                deleted = connection.execute(
                    "DELETE FROM session_model_ensemble_runs WHERE run_id=?",
                    (run_id,),
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
        return record


__all__ = ["SqliteSessionModelEnsembleRepository"]
