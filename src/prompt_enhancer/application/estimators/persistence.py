"""Content-free persistence boundary for immutable estimator evaluation bundles.

Only synthetic cases are accepted by this first vertical slice.  The types do
not contain prompts, excerpts, evidence bodies, model responses, rationales, or
commentary; those values must remain ephemeral outside the repository.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
import re
from typing import Literal, Protocol

from pydantic import Field, field_validator, model_validator

from ...domain import PSEUDONYM_PATTERN, SAFE_VERSION_PATTERN, StrictModel
from .contracts import (
    EstimatorExecution,
    EstimatorExecutionState,
    EstimatorPlan,
    EstimatorStageKind,
    EvidencePacketReceipt,
    ExecutionDestination,
    MetricEstimate,
    MetricEstimateSource,
    MetricEstimateState,
    ModelRun,
    ModelRunState,
    ModelSource,
    ModelVote,
    StageCondition,
)


SYNTHETIC_ESTIMATOR_CASE_VERSION = "synthetic-estimator-case-v1"
ESTIMATOR_BUNDLE_VERSION = "estimator-bundle-v1"
MODEL_LAB_SUMMARY_VERSION = "model-lab-summary-v1"


def _digest(value: str) -> str:
    if PSEUDONYM_PATTERN.fullmatch(value) is None:
        raise ValueError("value must be a lowercase SHA-256 identifier")
    return value


def _version(value: str) -> str:
    path_shaped = (
        value.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:[/\\]", value) is not None
        or "\\" in value
        or "://" in value
        or ".." in value.split("/")
    )
    if SAFE_VERSION_PATTERN.fullmatch(value) is None or path_shaped:
        raise ValueError("value must be a content-free version identifier")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be UTC")
    return value


class SyntheticEstimatorCase(StrictModel):
    """Pseudonymous scope receipt for a fixed synthetic evaluation case."""

    contract_version: Literal[SYNTHETIC_ESTIMATOR_CASE_VERSION] = (
        SYNTHETIC_ESTIMATOR_CASE_VERSION
    )
    case_id: str
    case_schema_version: str
    plan_fingerprint: str
    evidence_packet_fingerprint: str
    created_at: datetime
    source_kind: Literal["synthetic"] = "synthetic"

    _safe_ids = field_validator(
        "case_id", "plan_fingerprint", "evidence_packet_fingerprint"
    )(_digest)
    _safe_version = field_validator("case_schema_version")(_version)
    _utc_created = field_validator("created_at")(_utc)

    @model_validator(mode="after")
    def distinct_lineage(self) -> SyntheticEstimatorCase:
        if len(
            {self.case_id, self.plan_fingerprint, self.evidence_packet_fingerprint}
        ) != 3:
            raise ValueError("case and provenance identifiers must be distinct")
        return self


class CompletedSyntheticEstimatorBundle(StrictModel):
    """One complete, immutable synthetic execution and its scalar outputs."""

    contract_version: Literal[ESTIMATOR_BUNDLE_VERSION] = ESTIMATOR_BUNDLE_VERSION
    test_case: SyntheticEstimatorCase
    plan: EstimatorPlan
    evidence_packet: EvidencePacketReceipt
    execution: EstimatorExecution
    model_runs: tuple[ModelRun, ...] = Field(default=(), max_length=1000)
    model_votes: tuple[ModelVote, ...] = Field(default=(), max_length=10_000)
    metric_estimates: tuple[MetricEstimate, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_complete_lineage(self) -> CompletedSyntheticEstimatorBundle:
        plan_fingerprint = self.plan.canonical_fingerprint
        packet_fingerprint = self.evidence_packet.canonical_fingerprint
        if not self.plan.uses_synthetic_model:
            raise ValueError("this repository slice accepts synthetic plans only")
        if self.test_case.plan_fingerprint != plan_fingerprint:
            raise ValueError("case plan fingerprint does not match the plan")
        if self.test_case.evidence_packet_fingerprint != packet_fingerprint:
            raise ValueError("case evidence fingerprint does not match the receipt")
        if (
            self.evidence_packet.created_at > self.test_case.created_at
            or self.test_case.created_at > self.execution.created_at
        ):
            raise ValueError("case provenance timestamps are not chronological")
        provider_match = any(
            identity.provider is self.evidence_packet.provider
            and identity.adapter_version == self.evidence_packet.adapter_version
            and identity.provider_schema_version
            == self.evidence_packet.provider_schema_version
            for identity in self.plan.provider_schemas
        )
        if not provider_match:
            raise ValueError("evidence provider provenance does not match the plan")
        if (
            self.evidence_packet.packet_schema_version
            != self.plan.evidence_packet_schema_version
            or self.evidence_packet.preprocessing_version
            != self.plan.preprocessing_version
            or self.evidence_packet.preprocessing_sha256
            != self.plan.preprocessing_sha256
            or self.evidence_packet.redactor_version != self.plan.redactor_version
            or self.evidence_packet.redactor_sha256 != self.plan.redactor_sha256
        ):
            raise ValueError("evidence preprocessing provenance does not match the plan")
        if (
            self.execution.plan_fingerprint != plan_fingerprint
            or self.execution.evidence_packet_fingerprint != packet_fingerprint
            or self.execution.route is not self.plan.route
        ):
            raise ValueError("execution provenance does not match its plan and packet")
        if self.execution.state is not EstimatorExecutionState.COMPLETED:
            raise ValueError("only completed executions can be persisted")
        if self.execution.project_id is not None or self.execution.session_id is not None:
            raise ValueError("synthetic cases cannot claim a real project or session scope")
        questions = {
            question.canonical_fingerprint: question
            for question in self.plan.question_specs
        }
        stage_artifacts = {
            stage.ordinal: stage.model_artifact.canonical_fingerprint
            for stage in self.plan.stages
            if stage.model_artifact is not None
        }
        plan_stages = {stage.ordinal: stage for stage in self.plan.stages}
        runs = {run.run_id: run for run in self.model_runs}
        if len(runs) != len(self.model_runs):
            raise ValueError("model run identifiers must be unique")
        if tuple(
            (run.stage_ordinal, run.started_at, run.finished_at, run.run_id)
            for run in self.model_runs
        ) != tuple(
            sorted(
                (run.stage_ordinal, run.started_at, run.finished_at, run.run_id)
                for run in self.model_runs
            )
        ):
            raise ValueError("model runs must use canonical stage and chronology order")
        for run in self.model_runs:
            reached_receipt = next(
                (
                    receipt
                    for receipt in self.execution.stage_receipts
                    if receipt.ordinal == run.stage_ordinal
                ),
                None,
            )
            if (
                run.execution_id != self.execution.execution_id
                or run.plan_fingerprint != plan_fingerprint
                or run.evidence_packet_fingerprint != packet_fingerprint
                or run.route is not self.plan.route
                or reached_receipt is None
                or (
                    run.state is ModelRunState.COMPLETED
                    and reached_receipt.state.value != "completed"
                )
                or (
                    run.state is not ModelRunState.COMPLETED
                    and reached_receipt.state.value
                    not in {"completed", "failed", "cancelled"}
                )
                or run.stage_ordinal > self.execution.cascade_stop_stage_ordinal
                or run.started_at < reached_receipt.started_at
                or run.finished_at > reached_receipt.finished_at
                or run.started_at < self.execution.started_at
                or run.finished_at > self.execution.finished_at
                or run.latency_ms
                != round((run.finished_at - run.started_at).total_seconds() * 1000)
                or run.response_schema_version
                != plan_stages[run.stage_ordinal].output_schema_version
            ):
                raise ValueError("model run lineage does not match a reached stage")
            if run.model_artifact.source is not ModelSource.SYNTHETIC:
                raise ValueError("synthetic cases cannot contain a real model run")
            if run.execution.destination is not ExecutionDestination.SYNTHETIC_TEST:
                raise ValueError("synthetic model runs require the synthetic destination")
            if stage_artifacts.get(run.stage_ordinal) != (
                run.model_artifact.canonical_fingerprint
            ):
                raise ValueError("model run does not match its registered plan stage")
        previous_run = None
        for run in self.model_runs:
            if previous_run is not None and run.started_at < previous_run.finished_at:
                raise ValueError("serialized model runs cannot overlap")
            previous_run = run
        for receipt in self.execution.stage_receipts:
            plan_stage = plan_stages[receipt.ordinal]
            if (
                receipt.state.value == "skipped"
                and plan_stage.condition is StageCondition.ALWAYS
            ):
                raise ValueError("always-run estimator stages cannot be skipped")
            stage_runs = tuple(
                run for run in self.model_runs if run.stage_ordinal == receipt.ordinal
            )
            if receipt.kind in {
                EstimatorStageKind.EMBEDDING_RETRIEVAL,
                EstimatorStageKind.RERANKER,
                EstimatorStageKind.SPECIALIST,
                EstimatorStageKind.SECOND_OPINION,
            }:
                if receipt.state.value == "skipped" and stage_runs:
                    raise ValueError("skipped model stages cannot contain runs")
                if receipt.state.value == "completed" and not any(
                    run.state is ModelRunState.COMPLETED for run in stage_runs
                ):
                    raise ValueError("completed model stages require a completed run")
                if receipt.state.value == "failed" and (
                    not stage_runs
                    or any(run.state is ModelRunState.COMPLETED for run in stage_runs)
                    or not any(
                        run.state
                        in {
                            ModelRunState.FAILED,
                            ModelRunState.REFUSED,
                            ModelRunState.TIMED_OUT,
                            ModelRunState.OUT_OF_MEMORY,
                        }
                        for run in stage_runs
                    )
                ):
                    raise ValueError("failed model stages require a failed attempt")
                if receipt.state.value == "cancelled" and (
                    not stage_runs
                    or any(
                        run.state is not ModelRunState.CANCELLED for run in stage_runs
                    )
                ):
                    raise ValueError("cancelled model stages require cancelled attempts only")
            if (
                receipt.kind is EstimatorStageKind.HUMAN_ADJUDICATION
                and receipt.state.value != "skipped"
            ):
                raise ValueError(
                    "human adjudication stage must remain skipped without persisted adjudication"
                )

        packet_refs = set(self.evidence_packet.opaque_evidence_refs)
        votes = {vote.vote_id: vote for vote in self.model_votes}
        if len(votes) != len(self.model_votes):
            raise ValueError("model vote identifiers must be unique")
        if tuple((vote.metric_key, vote.vote_id) for vote in self.model_votes) != tuple(
            sorted((vote.metric_key, vote.vote_id) for vote in self.model_votes)
        ):
            raise ValueError("model votes must use canonical metric and identifier order")
        for vote in self.model_votes:
            question = questions.get(vote.metric_question_fingerprint)
            selected_run = runs.get(vote.model_run_id)
            completed_structured_vote = vote.state in {
                MetricEstimateState.KNOWN,
                MetricEstimateState.UNKNOWN,
                MetricEstimateState.NOT_APPLICABLE,
            }
            completed_or_refused_abstention = (
                vote.state is MetricEstimateState.ABSTAINED
                and selected_run is not None
                and (
                    (
                        selected_run.state is ModelRunState.COMPLETED
                        and selected_run.structured_output_valid
                    )
                    or (
                        selected_run.state is ModelRunState.REFUSED
                        and not selected_run.structured_output_valid
                        and vote.abstention_reason_code == selected_run.refusal_code
                    )
                )
            )
            failed_attempt_vote = (
                vote.state is MetricEstimateState.FAILED
                and selected_run is not None
                and selected_run.state
                in {
                    ModelRunState.FAILED,
                    ModelRunState.TIMED_OUT,
                    ModelRunState.OUT_OF_MEMORY,
                    ModelRunState.CANCELLED,
                }
                and not selected_run.structured_output_valid
                and vote.failure_code == selected_run.failure_code
            )
            if (
                vote.execution_id != self.execution.execution_id
                or vote.plan_fingerprint != plan_fingerprint
                or vote.evidence_packet_fingerprint != packet_fingerprint
                or selected_run is None
                or (
                    completed_structured_vote
                    and (
                        selected_run.state is not ModelRunState.COMPLETED
                        or not selected_run.structured_output_valid
                    )
                )
                or not (
                    completed_structured_vote
                    or completed_or_refused_abstention
                    or failed_attempt_vote
                )
                or selected_run.stage_kind
                not in {
                    EstimatorStageKind.SPECIALIST,
                    EstimatorStageKind.SECOND_OPINION,
                }
                or question is None
                or vote.metric_key != question.metric_key
                or vote.value_kind is not question.value_kind
                or (
                    vote.state is MetricEstimateState.KNOWN
                    and vote.numeric_value is not None
                    and not (
                        question.lower_bound
                        <= vote.numeric_value
                        <= question.upper_bound
                    )
                )
            ):
                raise ValueError("model vote scope does not match the execution")
            if not set(vote.opaque_evidence_refs) <= packet_refs:
                raise ValueError("model vote references evidence outside its packet")
            if (
                vote.state is MetricEstimateState.KNOWN
                and not vote.opaque_evidence_refs
            ):
                raise ValueError("known model votes require cited packet evidence")
        vote_producing_run_ids = {
            vote.model_run_id for vote in self.model_votes
        }
        if any(
            run.state is ModelRunState.COMPLETED
            and run.stage_kind
            in {
                EstimatorStageKind.SPECIALIST,
                EstimatorStageKind.SECOND_OPINION,
            }
            and run.run_id not in vote_producing_run_ids
            for run in self.model_runs
        ):
            raise ValueError("successful judgment runs require a persisted model vote")

        estimates = {estimate.estimate_id: estimate for estimate in self.metric_estimates}
        if len(estimates) != len(self.metric_estimates):
            raise ValueError("metric estimate identifiers must be unique")
        if tuple(
            (estimate.metric_key, estimate.estimate_id)
            for estimate in self.metric_estimates
        ) != tuple(
            sorted(
                (estimate.metric_key, estimate.estimate_id)
                for estimate in self.metric_estimates
            )
        ):
            raise ValueError(
                "metric estimates must use canonical metric and identifier order"
            )
        estimate_questions: set[str] = set()
        for estimate in self.metric_estimates:
            question = questions.get(estimate.metric_question_fingerprint)
            if (
                estimate.execution_id != self.execution.execution_id
                or estimate.plan_fingerprint != plan_fingerprint
                or estimate.evidence_packet_fingerprint != packet_fingerprint
                or question is None
                or estimate.metric_key != question.metric_key
                or estimate.value_kind is not question.value_kind
                or estimate.unit_code != question.unit_code
                or estimate.created_at < self.execution.started_at
                or estimate.created_at > self.execution.finished_at
                or (
                    estimate.state is MetricEstimateState.KNOWN
                    and estimate.numeric_value is not None
                    and not (
                        question.lower_bound
                        <= estimate.numeric_value
                        <= question.upper_bound
                    )
                )
            ):
                raise ValueError("metric estimate scope does not match the execution")
            if any(
                vote_id not in votes
                or votes[vote_id].metric_question_fingerprint
                != estimate.metric_question_fingerprint
                for vote_id in estimate.vote_ids
            ):
                raise ValueError("metric estimate references an incompatible model vote")
            if (
                estimate.source is MetricEstimateSource.MODEL_CASCADE
                and not estimate.vote_ids
            ):
                raise ValueError("model cascade estimates require a persisted vote")
            if (
                estimate.source is MetricEstimateSource.MODEL_CASCADE
                and not any(
                    votes[vote_id].state is estimate.state
                    for vote_id in estimate.vote_ids
                )
            ):
                raise ValueError(
                    "model cascade result requires a vote supporting its final state"
                )
            if (
                estimate.source is MetricEstimateSource.MODEL_CASCADE
                and estimate.state is MetricEstimateState.KNOWN
                and (
                    estimate.evidence_coverage <= 0
                    or not any(
                        votes[vote_id].state is MetricEstimateState.KNOWN
                        and votes[vote_id].opaque_evidence_refs
                        for vote_id in estimate.vote_ids
                    )
                )
            ):
                raise ValueError(
                    "known model estimates require cited evidence and positive coverage"
                )
            if (
                estimate.source is not MetricEstimateSource.MODEL_CASCADE
                and estimate.vote_ids
            ):
                raise ValueError("only model cascade estimates can reference model votes")
            if estimate.source is MetricEstimateSource.HUMAN_ADJUDICATED:
                raise ValueError(
                    "human adjudication persistence is outside this repository slice"
                )
            required_stage = {
                MetricEstimateSource.OBJECTIVE_EVIDENCE: 1,
                MetricEstimateSource.DETERMINISTIC: 2,
            }.get(estimate.source)
            if required_stage is not None:
                source_receipt = next(
                    (
                        receipt
                        for receipt in self.execution.stage_receipts
                        if receipt.ordinal == required_stage
                        and receipt.state.value == "completed"
                    ),
                    None,
                )
                if source_receipt is None:
                    raise ValueError("metric estimate source requires a completed stage")
                if estimate.created_at < source_receipt.finished_at:
                    raise ValueError("metric estimate predates its source stage")
            if estimate.source is MetricEstimateSource.MODEL_CASCADE and any(
                estimate.created_at < runs[votes[vote_id].model_run_id].finished_at
                for vote_id in estimate.vote_ids
            ):
                raise ValueError("metric estimate predates a selected model run")
            if (
                estimate.state is MetricEstimateState.KNOWN
                and estimate.source
                in {
                    MetricEstimateSource.OBJECTIVE_EVIDENCE,
                    MetricEstimateSource.DETERMINISTIC,
                }
                and (
                    estimate.evidence_coverage <= 0
                    or not self.evidence_packet.opaque_evidence_refs
                    or (
                        estimate.source is MetricEstimateSource.OBJECTIVE_EVIDENCE
                        and self.evidence_packet.verification_count == 0
                    )
                )
            ):
                raise ValueError("known evidence estimates require positive evidence")
            if (
                estimate.state is MetricEstimateState.KNOWN
                and estimate.numeric_value is not None
                and estimate.uncertainty is not None
                and estimate.uncertainty.kind.value == "interval"
                and not (
                    question.lower_bound
                    <= estimate.uncertainty.lower_bound
                    <= estimate.numeric_value
                    <= estimate.uncertainty.upper_bound
                    <= question.upper_bound
                )
            ):
                raise ValueError(
                    "estimate interval must contain its value within metric bounds"
                )
            estimate_questions.add(estimate.metric_question_fingerprint)
        referenced_votes = {
            vote_id for estimate in self.metric_estimates for vote_id in estimate.vote_ids
        }
        if referenced_votes != set(votes):
            raise ValueError("every persisted model vote must support an estimate")
        if estimate_questions != set(questions) or len(self.metric_estimates) != len(
            questions
        ):
            raise ValueError("the bundle requires exactly one estimate per metric question")
        return self


class ActivationAttemptOutcome(StrEnum):
    SYNTHETIC_OR_INSUFFICIENT = "synthetic_or_insufficient"


class PrivacyDeleteOutcome(StrEnum):
    DELETED_AND_PURGED = "deleted_and_purged"
    ALREADY_ABSENT_AND_PURGED = "already_absent_and_purged"


class ModelLabSummary(StrictModel):
    """Content-free inventory; it deliberately has no activation switch."""

    contract_version: Literal[MODEL_LAB_SUMMARY_VERSION] = MODEL_LAB_SUMMARY_VERSION
    plan_fingerprint: str
    registered: bool
    synthetic_execution_count: int = Field(ge=0)
    metric_estimate_count: int = Field(ge=0)
    activation_outcome: Literal[
        ActivationAttemptOutcome.SYNTHETIC_OR_INSUFFICIENT
    ] = ActivationAttemptOutcome.SYNTHETIC_OR_INSUFFICIENT
    activation_allowed: Literal[False] = False

    _safe_plan = field_validator("plan_fingerprint")(_digest)


class EstimatorRepository(Protocol):
    def register_plan(self, plan: EstimatorPlan) -> str: ...

    def get_plan(self, plan_fingerprint: str) -> EstimatorPlan | None: ...

    def save_completed_synthetic_bundle(
        self, bundle: CompletedSyntheticEstimatorBundle
    ) -> None: ...

    def get_completed_bundle(
        self, execution_id: str
    ) -> CompletedSyntheticEstimatorBundle | None: ...

    def model_lab_summary(self, plan_fingerprint: str) -> ModelLabSummary: ...

    def attempt_activation(self, plan_fingerprint: str) -> ModelLabSummary: ...

    def delete_synthetic_case_for_privacy(
        self, case_id: str
    ) -> PrivacyDeleteOutcome: ...
