"""Normalized SQLite storage for content-free P1 estimator provenance."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import NoReturn

from ...application.estimators.contracts import (
    ArtifactAvailability,
    ArtifactDigest,
    CandidateFamilySelection,
    EstimateUncertainty,
    EstimatorExecution,
    EstimatorExecutionState,
    EstimatorPlan,
    EstimatorReasoningEffort,
    EstimatorRoute,
    EstimatorStage,
    EstimatorStageKind,
    EstimatorStageReceipt,
    EstimatorStageReceiptState,
    EvidencePacketReceipt,
    ExecutionDestination,
    ExecutionDisclosure,
    LabelProbability,
    MetricDirection,
    MetricEstimate,
    MetricEstimateSource,
    MetricEstimateState,
    MetricQuestionSpec,
    MetricValueKind,
    ModelArtifactIdentity,
    ModelExecutionMode,
    ModelRun,
    ModelRunState,
    ModelSource,
    ModelVote,
    ProviderSchemaIdentity,
    RetentionClass,
    StageCondition,
    TokenizerIdentity,
    UncertaintyKind,
)
from ...application.estimators.persistence import (
    ActivationAttemptOutcome,
    CompletedSyntheticEstimatorBundle,
    EstimatorRepository,
    MAX_MODEL_LAB_PLANS,
    ModelLabInventory,
    ModelLabPlanSummary,
    ModelLabSummary,
    PrivacyDeleteOutcome,
    SyntheticEstimatorCase,
)
from ...database import DatabaseInvariantError
from ...domain import Provider
from ._common import ConnectionScope, from_iso, require_safe_id, to_iso


def _required_time(value: str) -> datetime:
    parsed = from_iso(value)
    if parsed is None:  # Defensive: schema requires these timestamps.
        raise DatabaseInvariantError("estimator timestamp is missing")
    return parsed


class SqliteEstimatorRepository(EstimatorRepository):
    """Append-only relational repository with an explicit privacy delete."""

    def __init__(
        self,
        connection_scope: ConnectionScope,
        ensure_initialized: Callable[[], None],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._connection_scope = connection_scope
        self._ensure_initialized = ensure_initialized
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _conflict(message: str) -> NoReturn:
        raise DatabaseInvariantError(message)

    def register_plan(self, plan: EstimatorPlan) -> str:
        self._ensure_initialized()
        fingerprint = plan.canonical_fingerprint
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT 1 FROM estimator_plans WHERE plan_fingerprint = ?",
                    (fingerprint,),
                ).fetchone()
                if existing is not None:
                    if self._hydrate_plan(connection, fingerprint) != plan:
                        self._conflict("estimator plan fingerprint conflicts with storage")
                    connection.commit()
                    return fingerprint
                version_owner = connection.execute(
                    """
                    SELECT plan_fingerprint FROM estimator_plans
                    WHERE plan_key = ? AND plan_version = ?
                    """,
                    (plan.plan_key, plan.plan_version),
                ).fetchone()
                if version_owner is not None:
                    self._conflict(
                        "estimator plan key and version already identify another configuration"
                    )
                self._insert_plan(connection, plan)
                connection.commit()
                return fingerprint
            except Exception:
                connection.rollback()
                raise

    def get_plan(self, plan_fingerprint: str) -> EstimatorPlan | None:
        self._ensure_initialized()
        require_safe_id(plan_fingerprint)
        with self._connection_scope(readonly=True) as connection:
            row = connection.execute(
                "SELECT 1 FROM estimator_plans WHERE plan_fingerprint = ?",
                (plan_fingerprint,),
            ).fetchone()
            if row is None:
                return None
            return self._hydrate_plan(connection, plan_fingerprint)

    def _insert_artifact(self, connection, artifact: ModelArtifactIdentity) -> str:
        fingerprint = artifact.canonical_fingerprint
        row = connection.execute(
            "SELECT 1 FROM estimator_model_artifacts WHERE artifact_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        if row is not None:
            if self._hydrate_artifact(connection, fingerprint) != artifact:
                self._conflict("model artifact fingerprint conflicts with storage")
            return fingerprint
        connection.executemany(
            """
            INSERT INTO estimator_model_weight_files(
                artifact_fingerprint, ordinal, file_name, sha256
            ) VALUES (?, ?, ?, ?)
            """,
            (
                (fingerprint, ordinal, item.file_name, item.sha256)
                for ordinal, item in enumerate(artifact.weight_artifacts)
            ),
        )
        connection.executemany(
            """
            INSERT INTO estimator_model_tokenizer_files(
                artifact_fingerprint, ordinal, file_name, sha256
            ) VALUES (?, ?, ?, ?)
            """,
            (
                (fingerprint, ordinal, item.file_name, item.sha256)
                for ordinal, item in enumerate(artifact.tokenizer.artifacts)
            ),
        )
        connection.execute(
            """
            INSERT INTO estimator_model_artifacts(
                artifact_fingerprint, contract_version, source,
                requested_model_id, served_model_id, requested_revision,
                served_revision, requested_execution_mode, served_execution_mode,
                weight_availability, weight_file_count, tokenizer_id,
                tokenizer_revision, tokenizer_availability, tokenizer_file_count,
                license_id, trust_remote_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                fingerprint,
                artifact.contract_version,
                artifact.source.value,
                artifact.requested_model_id,
                artifact.served_model_id,
                artifact.requested_revision,
                artifact.served_revision,
                artifact.requested_execution_mode.value,
                artifact.served_execution_mode.value,
                artifact.weight_availability.value,
                len(artifact.weight_artifacts),
                artifact.tokenizer.tokenizer_id,
                artifact.tokenizer.revision,
                artifact.tokenizer.availability.value,
                len(artifact.tokenizer.artifacts),
                artifact.license_id,
            ),
        )
        return fingerprint

    def _insert_question(self, connection, question: MetricQuestionSpec) -> str:
        fingerprint = question.canonical_fingerprint
        row = connection.execute(
            "SELECT 1 FROM estimator_metric_questions WHERE question_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        if row is not None:
            if self._hydrate_question(connection, fingerprint) != question:
                self._conflict("metric question fingerprint conflicts with storage")
            return fingerprint
        connection.execute(
            """
            INSERT INTO estimator_metric_questions(
                question_fingerprint, contract_version, metric_key,
                metric_definition_version, question_id, question_version,
                question_sha256, prompt_template_id, prompt_template_version,
                prompt_template_sha256, rubric_id, rubric_version, rubric_sha256,
                output_schema_version, value_kind, unit_code, direction,
                lower_bound, upper_bound
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fingerprint,
                question.contract_version,
                question.metric_key,
                question.metric_definition_version,
                question.question_id,
                question.question_version,
                question.question_sha256,
                question.prompt_template_id,
                question.prompt_template_version,
                question.prompt_template_sha256,
                question.rubric_id,
                question.rubric_version,
                question.rubric_sha256,
                question.output_schema_version,
                question.value_kind.value,
                question.unit_code,
                question.direction.value,
                question.lower_bound,
                question.upper_bound,
            ),
        )
        return fingerprint

    def _insert_plan(self, connection, plan: EstimatorPlan) -> None:
        plan_fingerprint = plan.canonical_fingerprint
        artifacts = {
            artifact.canonical_fingerprint: artifact
            for artifact in (
                [
                    stage.model_artifact
                    for stage in plan.stages
                    if stage.model_artifact is not None
                ]
                + [
                    candidate
                    for family in plan.candidate_families
                    for candidate in family.screened_candidates
                ]
            )
        }
        for fingerprint in sorted(artifacts):
            self._insert_artifact(connection, artifacts[fingerprint])
        for question in plan.question_specs:
            self._insert_question(connection, question)

        connection.executemany(
            """
            INSERT INTO estimator_plan_questions(
                plan_fingerprint, ordinal, question_fingerprint
            ) VALUES (?, ?, ?)
            """,
            (
                (plan_fingerprint, ordinal, question.canonical_fingerprint)
                for ordinal, question in enumerate(plan.question_specs)
            ),
        )
        connection.executemany(
            """
            INSERT INTO estimator_plan_provider_schemas(
                plan_fingerprint, ordinal, provider, adapter_version,
                provider_schema_version
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                (
                    plan_fingerprint,
                    ordinal,
                    identity.provider.value,
                    identity.adapter_version,
                    identity.provider_schema_version,
                )
                for ordinal, identity in enumerate(plan.provider_schemas)
            ),
        )
        for family_ordinal, family in enumerate(plan.candidate_families):
            connection.executemany(
                """
                INSERT INTO estimator_candidate_models(
                    plan_fingerprint, family_key, ordinal, artifact_fingerprint
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    (
                        plan_fingerprint,
                        family.family_key,
                        ordinal,
                        candidate.canonical_fingerprint,
                    )
                    for ordinal, candidate in enumerate(family.screened_candidates)
                ),
            )
            connection.executemany(
                """
                INSERT INTO estimator_candidate_promotions(
                    plan_fingerprint, family_key, ordinal, artifact_fingerprint
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    (plan_fingerprint, family.family_key, ordinal, fingerprint)
                    for ordinal, fingerprint in enumerate(
                        family.promoted_artifact_fingerprints
                    )
                ),
            )
            connection.executemany(
                """
                INSERT INTO estimator_candidate_baselines(
                    plan_fingerprint, family_key, ordinal, baseline_id
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    (plan_fingerprint, family.family_key, ordinal, baseline_id)
                    for ordinal, baseline_id in enumerate(
                        family.deterministic_baseline_ids
                    )
                ),
            )
            connection.execute(
                """
                INSERT INTO estimator_candidate_families(
                    plan_fingerprint, ordinal, family_key, candidate_count,
                    promotion_count, baseline_count
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_fingerprint,
                    family_ordinal,
                    family.family_key,
                    len(family.screened_candidates),
                    len(family.promoted_artifact_fingerprints),
                    len(family.deterministic_baseline_ids),
                ),
            )
        connection.executemany(
            """
            INSERT INTO estimator_plan_stages(
                plan_fingerprint, ordinal, kind, condition_code,
                component_version, configuration_sha256, output_schema_version,
                artifact_fingerprint, candidate_family_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    plan_fingerprint,
                    stage.ordinal,
                    stage.kind.value,
                    stage.condition.value,
                    stage.component_version,
                    stage.configuration_sha256,
                    stage.output_schema_version,
                    None
                    if stage.model_artifact is None
                    else stage.model_artifact.canonical_fingerprint,
                    stage.candidate_family_key,
                )
                for stage in plan.stages
            ),
        )
        connection.execute(
            """
            INSERT INTO estimator_plans(
                plan_fingerprint, contract_version, plan_key, plan_version, route,
                evidence_packet_schema_version, preprocessing_version,
                preprocessing_sha256, reasoning_effort, calibration_version,
                calibration_sha256, router_version, router_sha256,
                redactor_version, redactor_sha256, execution_mode,
                model_load_policy, max_loaded_models, question_count,
                provider_schema_count, candidate_family_count,
                uses_synthetic_model, registered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_fingerprint,
                plan.contract_version,
                plan.plan_key,
                plan.plan_version,
                plan.route.value,
                plan.evidence_packet_schema_version,
                plan.preprocessing_version,
                plan.preprocessing_sha256,
                plan.reasoning_effort.value,
                plan.calibration_version,
                plan.calibration_sha256,
                plan.router_version,
                plan.router_sha256,
                plan.redactor_version,
                plan.redactor_sha256,
                plan.execution_mode,
                plan.model_load_policy,
                plan.max_loaded_models,
                len(plan.question_specs),
                len(plan.provider_schemas),
                len(plan.candidate_families),
                int(plan.uses_synthetic_model),
                to_iso(self._clock()),
            ),
        )

    def _hydrate_artifact(self, connection, fingerprint: str) -> ModelArtifactIdentity:
        row = connection.execute(
            "SELECT * FROM estimator_model_artifacts WHERE artifact_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        if row is None:
            self._conflict("registered model artifact is missing")
        weights = connection.execute(
            """
            SELECT file_name, sha256 FROM estimator_model_weight_files
            WHERE artifact_fingerprint = ? ORDER BY ordinal
            """,
            (fingerprint,),
        ).fetchall()
        tokenizer_files = connection.execute(
            """
            SELECT file_name, sha256 FROM estimator_model_tokenizer_files
            WHERE artifact_fingerprint = ? ORDER BY ordinal
            """,
            (fingerprint,),
        ).fetchall()
        artifact = ModelArtifactIdentity(
            contract_version=row["contract_version"],
            source=ModelSource(row["source"]),
            requested_model_id=row["requested_model_id"],
            served_model_id=row["served_model_id"],
            requested_revision=row["requested_revision"],
            served_revision=row["served_revision"],
            requested_execution_mode=ModelExecutionMode(
                row["requested_execution_mode"]
            ),
            served_execution_mode=ModelExecutionMode(row["served_execution_mode"]),
            weight_availability=ArtifactAvailability(row["weight_availability"]),
            weight_artifacts=tuple(
                ArtifactDigest(file_name=item["file_name"], sha256=item["sha256"])
                for item in weights
            ),
            tokenizer=TokenizerIdentity(
                tokenizer_id=row["tokenizer_id"],
                revision=row["tokenizer_revision"],
                availability=ArtifactAvailability(row["tokenizer_availability"]),
                artifacts=tuple(
                    ArtifactDigest(
                        file_name=item["file_name"], sha256=item["sha256"]
                    )
                    for item in tokenizer_files
                ),
            ),
            license_id=row["license_id"],
            trust_remote_code=False,
        )
        if artifact.canonical_fingerprint != fingerprint:
            self._conflict("stored model artifact fingerprint is not reproducible")
        return artifact

    @staticmethod
    def _hydrate_question(connection, fingerprint: str) -> MetricQuestionSpec:
        row = connection.execute(
            "SELECT * FROM estimator_metric_questions WHERE question_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        if row is None:
            raise DatabaseInvariantError("registered metric question is missing")
        question = MetricQuestionSpec(
            contract_version=row["contract_version"],
            metric_key=row["metric_key"],
            metric_definition_version=row["metric_definition_version"],
            question_id=row["question_id"],
            question_version=row["question_version"],
            question_sha256=row["question_sha256"],
            prompt_template_id=row["prompt_template_id"],
            prompt_template_version=row["prompt_template_version"],
            prompt_template_sha256=row["prompt_template_sha256"],
            rubric_id=row["rubric_id"],
            rubric_version=row["rubric_version"],
            rubric_sha256=row["rubric_sha256"],
            output_schema_version=row["output_schema_version"],
            value_kind=MetricValueKind(row["value_kind"]),
            unit_code=row["unit_code"],
            direction=MetricDirection(row["direction"]),
            lower_bound=row["lower_bound"],
            upper_bound=row["upper_bound"],
        )
        if question.canonical_fingerprint != fingerprint:
            raise DatabaseInvariantError(
                "stored metric question fingerprint is not reproducible"
            )
        return question

    def _hydrate_plan(self, connection, fingerprint: str) -> EstimatorPlan:
        row = connection.execute(
            "SELECT * FROM estimator_plans WHERE plan_fingerprint = ?", (fingerprint,)
        ).fetchone()
        if row is None:
            self._conflict("registered estimator plan is missing")
        question_rows = connection.execute(
            """
            SELECT question_fingerprint FROM estimator_plan_questions
            WHERE plan_fingerprint = ? ORDER BY ordinal
            """,
            (fingerprint,),
        ).fetchall()
        provider_rows = connection.execute(
            """
            SELECT * FROM estimator_plan_provider_schemas
            WHERE plan_fingerprint = ? ORDER BY ordinal
            """,
            (fingerprint,),
        ).fetchall()
        family_rows = connection.execute(
            """
            SELECT * FROM estimator_candidate_families
            WHERE plan_fingerprint = ? ORDER BY ordinal
            """,
            (fingerprint,),
        ).fetchall()
        families: list[CandidateFamilySelection] = []
        for family_row in family_rows:
            family_key = family_row["family_key"]
            candidate_rows = connection.execute(
                """
                SELECT artifact_fingerprint FROM estimator_candidate_models
                WHERE plan_fingerprint = ? AND family_key = ? ORDER BY ordinal
                """,
                (fingerprint, family_key),
            ).fetchall()
            promotion_rows = connection.execute(
                """
                SELECT artifact_fingerprint FROM estimator_candidate_promotions
                WHERE plan_fingerprint = ? AND family_key = ? ORDER BY ordinal
                """,
                (fingerprint, family_key),
            ).fetchall()
            baseline_rows = connection.execute(
                """
                SELECT baseline_id FROM estimator_candidate_baselines
                WHERE plan_fingerprint = ? AND family_key = ? ORDER BY ordinal
                """,
                (fingerprint, family_key),
            ).fetchall()
            families.append(
                CandidateFamilySelection(
                    family_key=family_key,
                    screened_candidates=tuple(
                        self._hydrate_artifact(
                            connection, item["artifact_fingerprint"]
                        )
                        for item in candidate_rows
                    ),
                    promoted_artifact_fingerprints=tuple(
                        item["artifact_fingerprint"] for item in promotion_rows
                    ),
                    deterministic_baseline_ids=tuple(
                        item["baseline_id"] for item in baseline_rows
                    ),
                )
            )
        stage_rows = connection.execute(
            """
            SELECT * FROM estimator_plan_stages
            WHERE plan_fingerprint = ? ORDER BY ordinal
            """,
            (fingerprint,),
        ).fetchall()
        stages = tuple(
            EstimatorStage(
                ordinal=item["ordinal"],
                kind=EstimatorStageKind(item["kind"]),
                condition=StageCondition(item["condition_code"]),
                component_version=item["component_version"],
                configuration_sha256=item["configuration_sha256"],
                output_schema_version=item["output_schema_version"],
                model_artifact=(
                    None
                    if item["artifact_fingerprint"] is None
                    else self._hydrate_artifact(
                        connection, item["artifact_fingerprint"]
                    )
                ),
                candidate_family_key=item["candidate_family_key"],
            )
            for item in stage_rows
        )
        plan = EstimatorPlan(
            contract_version=row["contract_version"],
            plan_key=row["plan_key"],
            plan_version=row["plan_version"],
            route=EstimatorRoute(row["route"]),
            question_specs=tuple(
                self._hydrate_question(connection, item["question_fingerprint"])
                for item in question_rows
            ),
            evidence_packet_schema_version=row["evidence_packet_schema_version"],
            provider_schemas=tuple(
                ProviderSchemaIdentity(
                    provider=Provider(item["provider"]),
                    adapter_version=item["adapter_version"],
                    provider_schema_version=item["provider_schema_version"],
                )
                for item in provider_rows
            ),
            preprocessing_version=row["preprocessing_version"],
            preprocessing_sha256=row["preprocessing_sha256"],
            reasoning_effort=EstimatorReasoningEffort(row["reasoning_effort"]),
            calibration_version=row["calibration_version"],
            calibration_sha256=row["calibration_sha256"],
            router_version=row["router_version"],
            router_sha256=row["router_sha256"],
            redactor_version=row["redactor_version"],
            redactor_sha256=row["redactor_sha256"],
            stages=stages,
            candidate_families=tuple(families),
            execution_mode=row["execution_mode"],
            model_load_policy=row["model_load_policy"],
            max_loaded_models=row["max_loaded_models"],
        )
        if plan.canonical_fingerprint != fingerprint:
            self._conflict("stored estimator plan fingerprint is not reproducible")
        return plan

    def save_completed_synthetic_bundle(
        self, bundle: CompletedSyntheticEstimatorBundle
    ) -> None:
        self._ensure_initialized()
        execution_id = bundle.execution.execution_id
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                stored_plan = connection.execute(
                    "SELECT 1 FROM estimator_plans WHERE plan_fingerprint = ?",
                    (bundle.plan.canonical_fingerprint,),
                ).fetchone()
                if stored_plan is None or self._hydrate_plan(
                    connection, bundle.plan.canonical_fingerprint
                ) != bundle.plan:
                    self._conflict("estimator bundle requires its exact registered plan")
                if connection.execute(
                    "SELECT 1 FROM estimator_executions WHERE execution_id = ?",
                    (execution_id,),
                ).fetchone() is not None:
                    if self._hydrate_bundle(connection, execution_id) != bundle:
                        self._conflict("estimator execution identifier conflicts")
                    connection.commit()
                    return
                case_row = connection.execute(
                    """
                    SELECT * FROM estimator_synthetic_cases
                    WHERE case_id = ? OR evidence_packet_fingerprint = ?
                    """,
                    (
                        bundle.test_case.case_id,
                        bundle.evidence_packet.canonical_fingerprint,
                    ),
                ).fetchone()
                if case_row is not None:
                    existing_case = SyntheticEstimatorCase(
                        case_id=case_row["case_id"],
                        case_schema_version=case_row["case_schema_version"],
                        plan_fingerprint=case_row["plan_fingerprint"],
                        evidence_packet_fingerprint=case_row[
                            "evidence_packet_fingerprint"
                        ],
                        created_at=_required_time(case_row["created_at"]),
                        source_kind=case_row["source_kind"],
                    )
                    if (
                        existing_case != bundle.test_case
                        or self._hydrate_packet(
                            connection, bundle.evidence_packet.canonical_fingerprint
                        )
                        != bundle.evidence_packet
                    ):
                        self._conflict(
                            "synthetic estimator case conflicts with immutable storage"
                        )
                self._insert_bundle(
                    connection,
                    bundle,
                    persist_case=case_row is None,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _insert_bundle(
        self,
        connection,
        bundle: CompletedSyntheticEstimatorBundle,
        *,
        persist_case: bool,
    ) -> None:
        test_case = bundle.test_case
        packet = bundle.evidence_packet
        packet_fingerprint = packet.canonical_fingerprint
        plan_fingerprint = bundle.plan.canonical_fingerprint
        execution = bundle.execution

        if persist_case:
            connection.executemany(
                """
                INSERT INTO estimator_evidence_refs(
                    packet_fingerprint, ordinal, evidence_ref
                ) VALUES (?, ?, ?)
                """,
                (
                    (packet_fingerprint, ordinal, reference)
                    for ordinal, reference in enumerate(packet.opaque_evidence_refs)
                ),
            )
            connection.execute(
                """
                INSERT INTO estimator_evidence_packets(
                    packet_fingerprint, case_id, contract_version,
                    packet_schema_version, packet_sha256, requirements_sha256,
                    chronology_sha256, retrieval_index_sha256, provider,
                    adapter_version, provider_schema_version,
                    preprocessing_version, preprocessing_sha256,
                    redactor_version, redactor_sha256,
                    source_record_count, requirement_count, action_count,
                    decision_count, feedback_count, verification_count,
                    evidence_ref_count, created_at, ephemeral_payload_retained
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    packet_fingerprint,
                    test_case.case_id,
                    packet.contract_version,
                    packet.packet_schema_version,
                    packet.packet_sha256,
                    packet.requirements_sha256,
                    packet.chronology_sha256,
                    packet.retrieval_index_sha256,
                    packet.provider.value,
                    packet.adapter_version,
                    packet.provider_schema_version,
                    packet.preprocessing_version,
                    packet.preprocessing_sha256,
                    packet.redactor_version,
                    packet.redactor_sha256,
                    packet.source_record_count,
                    packet.requirement_count,
                    packet.action_count,
                    packet.decision_count,
                    packet.feedback_count,
                    packet.verification_count,
                    len(packet.opaque_evidence_refs),
                    to_iso(packet.created_at),
                ),
            )
            connection.execute(
                """
                INSERT INTO estimator_synthetic_cases(
                    case_id, case_schema_version, plan_fingerprint,
                    evidence_packet_fingerprint, created_at, source_kind
                ) VALUES (?, ?, ?, ?, ?, 'synthetic')
                """,
                (
                    test_case.case_id,
                    test_case.case_schema_version,
                    plan_fingerprint,
                    packet_fingerprint,
                    to_iso(test_case.created_at),
                ),
            )
        connection.executemany(
            """
            INSERT INTO estimator_stage_receipts(
                execution_id, ordinal, kind, state, outcome_code,
                started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    execution.execution_id,
                    receipt.ordinal,
                    receipt.kind.value,
                    receipt.state.value,
                    receipt.outcome_code,
                    None if receipt.started_at is None else to_iso(receipt.started_at),
                    None
                    if receipt.finished_at is None
                    else to_iso(receipt.finished_at),
                )
                for receipt in execution.stage_receipts
            ),
        )
        for run in bundle.model_runs:
            self._insert_run(connection, run)
        for vote in bundle.model_votes:
            self._insert_vote(connection, vote)
        for estimate in bundle.metric_estimates:
            self._insert_estimate(connection, estimate)
        connection.execute(
            """
            INSERT INTO estimator_executions(
                execution_id, case_id, contract_version, plan_fingerprint,
                evidence_packet_fingerprint, route, project_id, session_id,
                state, created_at, started_at, finished_at,
                cascade_stop_stage_ordinal, cascade_stop_stage_kind,
                cascade_stop_reason_code, stage_receipt_count, model_run_count,
                model_vote_count, metric_estimate_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution.execution_id,
                test_case.case_id,
                execution.contract_version,
                plan_fingerprint,
                packet_fingerprint,
                execution.route.value,
                execution.project_id,
                execution.session_id,
                execution.state.value,
                to_iso(execution.created_at),
                to_iso(execution.started_at),  # validated terminal execution
                to_iso(execution.finished_at),
                execution.cascade_stop_stage_ordinal,
                execution.cascade_stop_stage_kind.value,
                execution.cascade_stop_reason_code,
                len(execution.stage_receipts),
                len(bundle.model_runs),
                len(bundle.model_votes),
                len(bundle.metric_estimates),
            ),
        )

    @staticmethod
    def _insert_run(connection, run: ModelRun) -> None:
        disclosure = run.execution
        connection.execute(
            """
            INSERT INTO estimator_model_runs(
                run_id, execution_id, contract_version, plan_fingerprint,
                evidence_packet_fingerprint, route, stage_ordinal, stage_kind,
                artifact_fingerprint, destination, retention_class,
                retention_days, disclosure_version, approval_receipt_id,
                retention_acknowledged, state, started_at, finished_at,
                cold_start, queue_latency_ms, latency_ms, input_tokens,
                output_tokens, peak_ram_mib, peak_vram_mib, disk_mib,
                energy_mwh, api_cost_microusd, throughput_unit_code,
                measured_unit_count, throughput_window_ms,
                throughput_provenance_version, usage_provenance_version,
                response_schema_version, structured_output_valid, fallback_used,
                fallback_reason_code, refusal_code, failure_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.execution_id,
                run.contract_version,
                run.plan_fingerprint,
                run.evidence_packet_fingerprint,
                run.route.value,
                run.stage_ordinal,
                run.stage_kind.value,
                run.model_artifact.canonical_fingerprint,
                disclosure.destination.value,
                disclosure.retention_class.value,
                disclosure.retention_days,
                disclosure.disclosure_version,
                disclosure.approval_receipt_id,
                int(disclosure.retention_acknowledged),
                run.state.value,
                to_iso(run.started_at),
                to_iso(run.finished_at),
                int(run.cold_start),
                run.queue_latency_ms,
                run.latency_ms,
                run.input_tokens,
                run.output_tokens,
                run.peak_ram_mib,
                run.peak_vram_mib,
                run.disk_mib,
                run.energy_mwh,
                run.api_cost_microusd,
                run.throughput_unit_code,
                run.measured_unit_count,
                run.throughput_window_ms,
                run.throughput_provenance_version,
                run.usage_provenance_version,
                run.response_schema_version,
                int(run.structured_output_valid),
                int(run.fallback_used),
                run.fallback_reason_code,
                run.refusal_code,
                run.failure_code,
            ),
        )

    @staticmethod
    def _insert_vote(connection, vote: ModelVote) -> None:
        connection.executemany(
            """
            INSERT INTO estimator_vote_probabilities(
                vote_id, ordinal, label_code, probability
            ) VALUES (?, ?, ?, ?)
            """,
            (
                (vote.vote_id, ordinal, item.label_code, item.probability)
                for ordinal, item in enumerate(vote.probabilities)
            ),
        )
        connection.executemany(
            """
            INSERT INTO estimator_vote_evidence_refs(
                vote_id, ordinal, evidence_ref
            ) VALUES (?, ?, ?)
            """,
            (
                (vote.vote_id, ordinal, reference)
                for ordinal, reference in enumerate(vote.opaque_evidence_refs)
            ),
        )
        connection.execute(
            """
            INSERT INTO estimator_model_votes(
                vote_id, execution_id, model_run_id, contract_version,
                plan_fingerprint, evidence_packet_fingerprint,
                metric_question_fingerprint, metric_key, state, value_kind,
                numeric_value, label_code, confidence, unknown_reason_code,
                abstention_reason_code, not_applicable_reason_code, failure_code,
                probability_count, evidence_ref_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                vote.vote_id,
                vote.execution_id,
                vote.model_run_id,
                vote.contract_version,
                vote.plan_fingerprint,
                vote.evidence_packet_fingerprint,
                vote.metric_question_fingerprint,
                vote.metric_key,
                vote.state.value,
                vote.value_kind.value,
                vote.numeric_value,
                vote.label_code,
                vote.confidence,
                vote.unknown_reason_code,
                vote.abstention_reason_code,
                vote.not_applicable_reason_code,
                vote.failure_code,
                len(vote.probabilities),
                len(vote.opaque_evidence_refs),
            ),
        )

    @staticmethod
    def _insert_estimate(connection, estimate: MetricEstimate) -> None:
        connection.executemany(
            """
            INSERT INTO estimator_estimate_votes(estimate_id, ordinal, vote_id)
            VALUES (?, ?, ?)
            """,
            (
                (estimate.estimate_id, ordinal, vote_id)
                for ordinal, vote_id in enumerate(estimate.vote_ids)
            ),
        )
        uncertainty = estimate.uncertainty
        connection.execute(
            """
            INSERT INTO estimator_metric_estimates(
                estimate_id, execution_id, contract_version, plan_fingerprint,
                evidence_packet_fingerprint, metric_question_fingerprint,
                metric_key, source, state, value_kind, unit_code, numeric_value,
                label_code, numerator, denominator, uncertainty_kind,
                uncertainty_confidence, uncertainty_lower_bound,
                uncertainty_upper_bound, uncertainty_confidence_level,
                uncertainty_entropy, uncertainty_reason_code, evidence_coverage,
                adjudication_id, unknown_reason_code, abstention_reason_code,
                not_applicable_reason_code, failure_code, vote_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                estimate.estimate_id,
                estimate.execution_id,
                estimate.contract_version,
                estimate.plan_fingerprint,
                estimate.evidence_packet_fingerprint,
                estimate.metric_question_fingerprint,
                estimate.metric_key,
                estimate.source.value,
                estimate.state.value,
                estimate.value_kind.value,
                estimate.unit_code,
                estimate.numeric_value,
                estimate.label_code,
                estimate.numerator,
                estimate.denominator,
                None if uncertainty is None else uncertainty.kind.value,
                None if uncertainty is None else uncertainty.confidence,
                None if uncertainty is None else uncertainty.lower_bound,
                None if uncertainty is None else uncertainty.upper_bound,
                None if uncertainty is None else uncertainty.confidence_level,
                None if uncertainty is None else uncertainty.entropy,
                None if uncertainty is None else uncertainty.reason_code,
                estimate.evidence_coverage,
                estimate.adjudication_id,
                estimate.unknown_reason_code,
                estimate.abstention_reason_code,
                estimate.not_applicable_reason_code,
                estimate.failure_code,
                len(estimate.vote_ids),
                to_iso(estimate.created_at),
            ),
        )

    def get_completed_bundle(
        self, execution_id: str
    ) -> CompletedSyntheticEstimatorBundle | None:
        self._ensure_initialized()
        require_safe_id(execution_id)
        with self._connection_scope(readonly=True) as connection:
            row = connection.execute(
                "SELECT * FROM estimator_executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if row is None:
                return None
            return self._hydrate_bundle(connection, execution_id)

    def _hydrate_bundle(
        self, connection, execution_id: str
    ) -> CompletedSyntheticEstimatorBundle:
            row = connection.execute(
                "SELECT * FROM estimator_executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if row is None:
                self._conflict("estimator execution is missing")
            case_row = connection.execute(
                "SELECT * FROM estimator_synthetic_cases WHERE case_id = ?",
                (row["case_id"],),
            ).fetchone()
            if case_row is None:
                self._conflict("estimator case is missing")
            plan = self._hydrate_plan(connection, row["plan_fingerprint"])
            packet = self._hydrate_packet(
                connection, row["evidence_packet_fingerprint"]
            )
            test_case = SyntheticEstimatorCase(
                case_id=case_row["case_id"],
                case_schema_version=case_row["case_schema_version"],
                plan_fingerprint=case_row["plan_fingerprint"],
                evidence_packet_fingerprint=case_row["evidence_packet_fingerprint"],
                created_at=_required_time(case_row["created_at"]),
                source_kind=case_row["source_kind"],
            )
            receipt_rows = connection.execute(
                """
                SELECT * FROM estimator_stage_receipts
                WHERE execution_id = ? ORDER BY ordinal
                """,
                (execution_id,),
            ).fetchall()
            execution = EstimatorExecution(
                contract_version=row["contract_version"],
                execution_id=row["execution_id"],
                plan_fingerprint=row["plan_fingerprint"],
                evidence_packet_fingerprint=row["evidence_packet_fingerprint"],
                route=EstimatorRoute(row["route"]),
                project_id=row["project_id"],
                session_id=row["session_id"],
                state=EstimatorExecutionState(row["state"]),
                created_at=_required_time(row["created_at"]),
                started_at=_required_time(row["started_at"]),
                finished_at=_required_time(row["finished_at"]),
                stage_receipts=tuple(
                    EstimatorStageReceipt(
                        ordinal=item["ordinal"],
                        kind=EstimatorStageKind(item["kind"]),
                        state=EstimatorStageReceiptState(item["state"]),
                        outcome_code=item["outcome_code"],
                        started_at=from_iso(item["started_at"]),
                        finished_at=from_iso(item["finished_at"]),
                    )
                    for item in receipt_rows
                ),
                cascade_stop_stage_ordinal=row["cascade_stop_stage_ordinal"],
                cascade_stop_stage_kind=EstimatorStageKind(
                    row["cascade_stop_stage_kind"]
                ),
                cascade_stop_reason_code=row["cascade_stop_reason_code"],
            )
            run_rows = connection.execute(
                """
                SELECT * FROM estimator_model_runs
                WHERE execution_id = ?
                ORDER BY stage_ordinal, started_at, finished_at, run_id
                """,
                (execution_id,),
            ).fetchall()
            runs = tuple(self._hydrate_run(connection, item) for item in run_rows)
            vote_rows = connection.execute(
                """
                SELECT * FROM estimator_model_votes
                WHERE execution_id = ? ORDER BY metric_key, vote_id
                """,
                (execution_id,),
            ).fetchall()
            votes = tuple(self._hydrate_vote(connection, item) for item in vote_rows)
            estimate_rows = connection.execute(
                """
                SELECT * FROM estimator_metric_estimates
                WHERE execution_id = ? ORDER BY metric_key, estimate_id
                """,
                (execution_id,),
            ).fetchall()
            estimates = tuple(
                self._hydrate_estimate(connection, item) for item in estimate_rows
            )
            return CompletedSyntheticEstimatorBundle(
                test_case=test_case,
                plan=plan,
                evidence_packet=packet,
                execution=execution,
                model_runs=runs,
                model_votes=votes,
                metric_estimates=estimates,
            )

    @staticmethod
    def _hydrate_packet(connection, fingerprint: str) -> EvidencePacketReceipt:
        row = connection.execute(
            "SELECT * FROM estimator_evidence_packets WHERE packet_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        if row is None:
            raise DatabaseInvariantError("estimator evidence receipt is missing")
        refs = connection.execute(
            """
            SELECT evidence_ref FROM estimator_evidence_refs
            WHERE packet_fingerprint = ? ORDER BY ordinal
            """,
            (fingerprint,),
        ).fetchall()
        packet = EvidencePacketReceipt(
            contract_version=row["contract_version"],
            packet_schema_version=row["packet_schema_version"],
            packet_sha256=row["packet_sha256"],
            requirements_sha256=row["requirements_sha256"],
            chronology_sha256=row["chronology_sha256"],
            retrieval_index_sha256=row["retrieval_index_sha256"],
            provider=Provider(row["provider"]),
            adapter_version=row["adapter_version"],
            provider_schema_version=row["provider_schema_version"],
            preprocessing_version=row["preprocessing_version"],
            preprocessing_sha256=row["preprocessing_sha256"],
            redactor_version=row["redactor_version"],
            redactor_sha256=row["redactor_sha256"],
            source_record_count=row["source_record_count"],
            requirement_count=row["requirement_count"],
            action_count=row["action_count"],
            decision_count=row["decision_count"],
            feedback_count=row["feedback_count"],
            verification_count=row["verification_count"],
            opaque_evidence_refs=tuple(item["evidence_ref"] for item in refs),
            created_at=_required_time(row["created_at"]),
            ephemeral_payload_retained=False,
        )
        if packet.canonical_fingerprint != fingerprint:
            raise DatabaseInvariantError(
                "stored evidence receipt fingerprint is not reproducible"
            )
        return packet

    def _hydrate_run(self, connection, row) -> ModelRun:
        return ModelRun(
            contract_version=row["contract_version"],
            run_id=row["run_id"],
            execution_id=row["execution_id"],
            plan_fingerprint=row["plan_fingerprint"],
            evidence_packet_fingerprint=row["evidence_packet_fingerprint"],
            route=EstimatorRoute(row["route"]),
            stage_ordinal=row["stage_ordinal"],
            stage_kind=EstimatorStageKind(row["stage_kind"]),
            model_artifact=self._hydrate_artifact(
                connection, row["artifact_fingerprint"]
            ),
            execution=ExecutionDisclosure(
                destination=ExecutionDestination(row["destination"]),
                retention_class=RetentionClass(row["retention_class"]),
                retention_days=row["retention_days"],
                disclosure_version=row["disclosure_version"],
                approval_receipt_id=row["approval_receipt_id"],
                retention_acknowledged=bool(row["retention_acknowledged"]),
            ),
            state=ModelRunState(row["state"]),
            started_at=_required_time(row["started_at"]),
            finished_at=_required_time(row["finished_at"]),
            cold_start=bool(row["cold_start"]),
            queue_latency_ms=row["queue_latency_ms"],
            latency_ms=row["latency_ms"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            peak_ram_mib=row["peak_ram_mib"],
            peak_vram_mib=row["peak_vram_mib"],
            disk_mib=row["disk_mib"],
            energy_mwh=row["energy_mwh"],
            api_cost_microusd=row["api_cost_microusd"],
            throughput_unit_code=row["throughput_unit_code"],
            measured_unit_count=row["measured_unit_count"],
            throughput_window_ms=row["throughput_window_ms"],
            throughput_provenance_version=row["throughput_provenance_version"],
            usage_provenance_version=row["usage_provenance_version"],
            response_schema_version=row["response_schema_version"],
            structured_output_valid=bool(row["structured_output_valid"]),
            fallback_used=bool(row["fallback_used"]),
            fallback_reason_code=row["fallback_reason_code"],
            refusal_code=row["refusal_code"],
            failure_code=row["failure_code"],
        )

    @staticmethod
    def _hydrate_vote(connection, row) -> ModelVote:
        probabilities = connection.execute(
            """
            SELECT label_code, probability FROM estimator_vote_probabilities
            WHERE vote_id = ? ORDER BY ordinal
            """,
            (row["vote_id"],),
        ).fetchall()
        refs = connection.execute(
            """
            SELECT evidence_ref FROM estimator_vote_evidence_refs
            WHERE vote_id = ? ORDER BY ordinal
            """,
            (row["vote_id"],),
        ).fetchall()
        return ModelVote(
            contract_version=row["contract_version"],
            vote_id=row["vote_id"],
            execution_id=row["execution_id"],
            model_run_id=row["model_run_id"],
            plan_fingerprint=row["plan_fingerprint"],
            evidence_packet_fingerprint=row["evidence_packet_fingerprint"],
            metric_question_fingerprint=row["metric_question_fingerprint"],
            metric_key=row["metric_key"],
            state=MetricEstimateState(row["state"]),
            value_kind=MetricValueKind(row["value_kind"]),
            numeric_value=row["numeric_value"],
            label_code=row["label_code"],
            confidence=row["confidence"],
            probabilities=tuple(
                LabelProbability(
                    label_code=item["label_code"], probability=item["probability"]
                )
                for item in probabilities
            ),
            opaque_evidence_refs=tuple(item["evidence_ref"] for item in refs),
            unknown_reason_code=row["unknown_reason_code"],
            abstention_reason_code=row["abstention_reason_code"],
            not_applicable_reason_code=row["not_applicable_reason_code"],
            failure_code=row["failure_code"],
        )

    @staticmethod
    def _hydrate_estimate(connection, row) -> MetricEstimate:
        vote_rows = connection.execute(
            """
            SELECT vote_id FROM estimator_estimate_votes
            WHERE estimate_id = ? ORDER BY ordinal
            """,
            (row["estimate_id"],),
        ).fetchall()
        uncertainty = None
        if row["uncertainty_kind"] is not None:
            uncertainty = EstimateUncertainty(
                kind=UncertaintyKind(row["uncertainty_kind"]),
                confidence=row["uncertainty_confidence"],
                lower_bound=row["uncertainty_lower_bound"],
                upper_bound=row["uncertainty_upper_bound"],
                confidence_level=row["uncertainty_confidence_level"],
                entropy=row["uncertainty_entropy"],
                reason_code=row["uncertainty_reason_code"],
            )
        return MetricEstimate(
            contract_version=row["contract_version"],
            estimate_id=row["estimate_id"],
            execution_id=row["execution_id"],
            plan_fingerprint=row["plan_fingerprint"],
            evidence_packet_fingerprint=row["evidence_packet_fingerprint"],
            metric_question_fingerprint=row["metric_question_fingerprint"],
            metric_key=row["metric_key"],
            source=MetricEstimateSource(row["source"]),
            state=MetricEstimateState(row["state"]),
            value_kind=MetricValueKind(row["value_kind"]),
            unit_code=row["unit_code"],
            numeric_value=row["numeric_value"],
            label_code=row["label_code"],
            numerator=row["numerator"],
            denominator=row["denominator"],
            uncertainty=uncertainty,
            evidence_coverage=row["evidence_coverage"],
            vote_ids=tuple(item["vote_id"] for item in vote_rows),
            adjudication_id=row["adjudication_id"],
            unknown_reason_code=row["unknown_reason_code"],
            abstention_reason_code=row["abstention_reason_code"],
            not_applicable_reason_code=row["not_applicable_reason_code"],
            failure_code=row["failure_code"],
            created_at=_required_time(row["created_at"]),
        )

    def model_lab_summary(self, plan_fingerprint: str) -> ModelLabSummary:
        self._ensure_initialized()
        require_safe_id(plan_fingerprint)
        with self._connection_scope(readonly=True) as connection:
            registered = connection.execute(
                "SELECT 1 FROM estimator_plans WHERE plan_fingerprint = ?",
                (plan_fingerprint,),
            ).fetchone() is not None
            counts = connection.execute(
                """
                SELECT COUNT(DISTINCT execution.execution_id) AS execution_count,
                       COUNT(estimate.estimate_id) AS estimate_count
                FROM estimator_executions AS execution
                LEFT JOIN estimator_metric_estimates AS estimate
                  ON estimate.execution_id = execution.execution_id
                WHERE execution.plan_fingerprint = ?
                """,
                (plan_fingerprint,),
            ).fetchone()
        return ModelLabSummary(
            plan_fingerprint=plan_fingerprint,
            registered=registered,
            synthetic_execution_count=counts["execution_count"],
            metric_estimate_count=counts["estimate_count"],
            activation_outcome=ActivationAttemptOutcome.SYNTHETIC_OR_INSUFFICIENT,
            activation_allowed=False,
        )

    def model_lab_inventory(self) -> ModelLabInventory:
        """Return bounded synthetic aggregates without hydrating private evidence."""

        self._ensure_initialized()
        with self._connection_scope(readonly=True) as connection:
            rows = connection.execute(
                """
                SELECT plan.plan_fingerprint,
                       plan.plan_key,
                       plan.plan_version,
                       plan.route,
                       plan.question_count,
                       COUNT(execution.execution_id) AS execution_count,
                       COALESCE(SUM(execution.model_run_count), 0) AS run_count,
                       COALESCE(SUM(execution.model_vote_count), 0) AS vote_count,
                       COALESCE(SUM(execution.metric_estimate_count), 0)
                           AS estimate_count
                FROM estimator_plans AS plan
                LEFT JOIN estimator_executions AS execution
                  ON execution.plan_fingerprint = plan.plan_fingerprint
                WHERE plan.uses_synthetic_model = 1
                GROUP BY plan.plan_fingerprint,
                         plan.plan_key,
                         plan.plan_version,
                         plan.route,
                         plan.question_count
                ORDER BY plan.plan_key, plan.plan_version, plan.plan_fingerprint
                LIMIT ?
                """,
                (MAX_MODEL_LAB_PLANS + 1,),
            ).fetchall()
        if len(rows) > MAX_MODEL_LAB_PLANS:
            raise DatabaseInvariantError("model lab plan inventory exceeds its safe bound")
        plans = tuple(
            ModelLabPlanSummary(
                plan_fingerprint=row["plan_fingerprint"],
                plan_key=row["plan_key"],
                plan_version=row["plan_version"],
                route=EstimatorRoute(row["route"]),
                metric_question_count=row["question_count"],
                synthetic_execution_count=row["execution_count"],
                model_run_count=row["run_count"],
                model_vote_count=row["vote_count"],
                metric_estimate_count=row["estimate_count"],
                activation_outcome=(
                    ActivationAttemptOutcome.SYNTHETIC_OR_INSUFFICIENT
                ),
                activation_allowed=False,
            )
            for row in rows
        )
        return ModelLabInventory(
            registered_plan_count=len(plans),
            synthetic_execution_count=sum(
                plan.synthetic_execution_count for plan in plans
            ),
            model_run_count=sum(plan.model_run_count for plan in plans),
            model_vote_count=sum(plan.model_vote_count for plan in plans),
            metric_estimate_count=sum(plan.metric_estimate_count for plan in plans),
            activation_outcome=ActivationAttemptOutcome.SYNTHETIC_OR_INSUFFICIENT,
            activation_allowed=False,
            plans=plans,
        )

    def attempt_activation(self, plan_fingerprint: str) -> ModelLabSummary:
        """Fail closed; synthetic inventory can never create an activation row."""

        return self.model_lab_summary(plan_fingerprint)

    def delete_synthetic_case_for_privacy(self, case_id: str) -> PrivacyDeleteOutcome:
        """Delete one case and prove its WAL frames were durably truncated.

        A logical cascade is not reported as a successful privacy erase while a
        reader pins older WAL frames.  A caller may retry the same case ID after
        readers close; the retry checkpoints even when the logical row is gone.
        """

        self._ensure_initialized()
        require_safe_id(case_id)
        with self._connection_scope() as connection:
            try:
                connection.execute("PRAGMA secure_delete = ON")
                if int(connection.execute("PRAGMA secure_delete").fetchone()[0]) != 1:
                    raise DatabaseInvariantError(
                        "privacy deletion requires SQLite secure_delete"
                    )
                connection.execute("BEGIN IMMEDIATE")
                deleted = connection.execute(
                    "DELETE FROM estimator_synthetic_cases WHERE case_id = ?",
                    (case_id,),
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
                        "privacy deletion committed but durable WAL purge is pending"
                    )
                return (
                    PrivacyDeleteOutcome.DELETED_AND_PURGED
                    if deleted
                    else PrivacyDeleteOutcome.ALREADY_ABSENT_AND_PURGED
                )
            except Exception:
                connection.rollback()
                raise
