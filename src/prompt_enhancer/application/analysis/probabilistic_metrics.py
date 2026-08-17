"""Versioned contracts and content-free receipts for the local radar estimator.

The deterministic coaching projection remains the only measured layer.  This
module describes a separate, explicitly experimental predictive layer.  It
never stores source text, prompts, logits, or samples; only typed factor
probabilities and compact distribution summaries cross the ephemeral model
boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
import hashlib
import json
import math
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ...domain import SAFE_VERSION_PATTERN, StrictModel


PROBABILISTIC_METRIC_PROJECTION_VERSION = "local-probabilistic-radar-v1"
PROBABILISTIC_CONTRACT_REGISTRY_VERSION = "all-20-factor-contracts-v1"
PROBABILISTIC_MODEL_SET_VERSION = "local-factor-router-v2"
EXPERIMENTAL_CALIBRATION_VERSION = "not-calibrated-v1"
PROBABILISTIC_DENSITY_BIN_COUNT = 20
PROBABILISTIC_SAMPLE_COUNT = 1_024
PROBABILISTIC_MAX_VRAM_MIB = 6_144
PROBABILISTIC_MAX_RSS_MIB = 8_192
PROBABILISTIC_MAX_EPISODE_TOKENS = 2_048


def _safe(value: str) -> str:
    if SAFE_VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("value must be a content-free version identifier")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("predictive timestamp must be UTC")
    return value


class PredictiveMetricTarget(StrEnum):
    METRIC_VALUE = "metric_value"
    OUTCOME_FORECAST = "outcome_forecast"


class PredictiveMetricState(StrEnum):
    UNAVAILABLE = "unavailable"
    EXPERIMENTAL = "experimental"
    CALIBRATED = "calibrated"
    OUT_OF_DISTRIBUTION = "out_of_distribution"
    EXECUTION_ERROR = "execution_error"


class FactorScale(StrEnum):
    BINARY = "binary"
    ORDINAL = "ordinal"
    PROPORTION = "proportion"


class EvidenceLane(StrEnum):
    DETERMINISTIC_SMALL = "deterministic_small"
    DETERMINISTIC_SMALL_RETRIEVAL = "deterministic_small_retrieval"
    DETERMINISTIC_SMALL_OBJECTIVE = "deterministic_small_objective"
    OBJECTIVE_ONLY = "objective_only"


class ObservationScope(StrEnum):
    FOCUS_REQUEST = "focus_request"
    CONVERSATION = "conversation"
    OBJECTIVE_EVIDENCE = "objective_evidence"


@dataclass(frozen=True, slots=True)
class FactorContract:
    factor_key: str
    description: str
    scale: FactorScale = FactorScale.BINARY
    weight: float = 1.0
    critical: bool = False

    def __post_init__(self) -> None:
        _safe(self.factor_key)
        if not self.description or len(self.description) > 500:
            raise ValueError("factor description is outside the reviewed bound")
        if not math.isfinite(self.weight) or self.weight <= 0:
            raise ValueError("factor weight must be positive and finite")


@dataclass(frozen=True, slots=True)
class MetricContract:
    metric_key: str
    contract_version: str
    observation_unit: str
    scope: ObservationScope
    lane: EvidenceLane
    target: PredictiveMetricTarget
    factors: tuple[FactorContract, ...]
    closure_horizon: str
    objective_evidence_required: bool = False

    def __post_init__(self) -> None:
        _safe(self.metric_key)
        _safe(self.contract_version)
        _safe(self.observation_unit)
        _safe(self.closure_horizon)
        if not self.factors or len(self.factors) > 8:
            raise ValueError("metric contracts require one to eight factors")
        keys = tuple(item.factor_key for item in self.factors)
        if len(set(keys)) != len(keys):
            raise ValueError("metric factor keys must be unique")

    @property
    def fingerprint(self) -> str:
        payload = {
            "registry": PROBABILISTIC_CONTRACT_REGISTRY_VERSION,
            "metric_key": self.metric_key,
            "contract_version": self.contract_version,
            "observation_unit": self.observation_unit,
            "scope": self.scope.value,
            "lane": self.lane.value,
            "target": self.target.value,
            "closure_horizon": self.closure_horizon,
            "objective_evidence_required": self.objective_evidence_required,
            "factors": [
                {
                    "key": item.factor_key,
                    "description": item.description,
                    "scale": item.scale.value,
                    "weight": item.weight,
                    "critical": item.critical,
                }
                for item in self.factors
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()


def _factor(
    key: str,
    description: str,
    *,
    scale: FactorScale = FactorScale.BINARY,
    critical: bool = False,
) -> FactorContract:
    return FactorContract(
        factor_key=key,
        description=description,
        scale=scale,
        critical=critical,
    )


def _contract(
    metric_key: str,
    observation_unit: str,
    scope: ObservationScope,
    lane: EvidenceLane,
    factors: tuple[FactorContract, ...],
    *,
    closure_horizon: str = "immediate",
    objective: bool = False,
) -> MetricContract:
    return MetricContract(
        metric_key=metric_key,
        contract_version="probabilistic-metric-contract-v1",
        observation_unit=observation_unit,
        scope=scope,
        lane=lane,
        target=(
            PredictiveMetricTarget.OUTCOME_FORECAST
            if metric_key.startswith("outcome.")
            else PredictiveMetricTarget.METRIC_VALUE
        ),
        factors=factors,
        closure_horizon=closure_horizon,
        objective_evidence_required=objective,
    )


PROBABILISTIC_METRIC_CONTRACTS: tuple[MetricContract, ...] = (
    _contract(
        "prompt.task_definition_coverage",
        "canonical_request_revision",
        ObservationScope.FOCUS_REQUEST,
        EvidenceLane.DETERMINISTIC_SMALL,
        (
            _factor("action", "The request states the action to perform.", critical=True),
            _factor("target", "The request identifies the target of the action.", critical=True),
            _factor("intended_outcome", "The request states the intended outcome."),
        ),
    ),
    _contract(
        "prompt.problem_evidence_quality",
        "diagnostic_request",
        ObservationScope.FOCUS_REQUEST,
        EvidenceLane.DETERMINISTIC_SMALL,
        (
            _factor("observed_state", "The observed or current problematic state is stated."),
            _factor("expected_state", "The expected state or behavior is stated."),
            _factor("reproduction", "A reproduction path is supplied when reproducibility applies."),
            _factor("relevant_environment", "Relevant environment information is supplied when environment-dependent."),
        ),
    ),
    _contract(
        "prompt.context_sufficiency",
        "stateful_request",
        ObservationScope.FOCUS_REQUEST,
        EvidenceLane.DETERMINISTIC_SMALL,
        (
            _factor("current_state", "The relevant current state is supplied.", critical=True),
            _factor("environment_version", "Relevant environment or version context is supplied."),
            _factor("dependency_boundary", "Dependencies and system boundaries are identified."),
        ),
    ),
    _contract(
        "prompt.constraint_precision",
        "explicit_constraint",
        ObservationScope.FOCUS_REQUEST,
        EvidenceLane.DETERMINISTIC_SMALL,
        (
            _factor("scope", "The constraint has an explicit scope."),
            _factor("concrete_bound", "The constraint contains a concrete bound or rule."),
            _factor("polarity", "The constraint clearly states what is required or forbidden."),
            _factor("priority_source", "Priority or source is clear when constraints conflict."),
        ),
    ),
    _contract(
        "prompt.acceptance_testability",
        "testable_requirement",
        ObservationScope.FOCUS_REQUEST,
        EvidenceLane.DETERMINISTIC_SMALL,
        (
            _factor("observable_result", "The required result is externally observable.", critical=True),
            _factor("oracle", "A pass or fail boundary is identifiable.", critical=True),
            _factor("verification_method", "A practical verification method is stated or inferable."),
            _factor("verification_scope", "The scope of verification is bounded."),
        ),
    ),
    _contract(
        "prompt.deliverable_contract",
        "requested_artifact",
        ObservationScope.FOCUS_REQUEST,
        EvidenceLane.DETERMINISTIC_SMALL,
        (
            _factor("artifact_interface", "The requested artifact or interface is identified.", critical=True),
            _factor("format_location", "The required format or location is identified."),
            _factor("audience", "The intended audience or consumer is identified when relevant."),
            _factor("compatibility", "Compatibility expectations are stated when relevant."),
        ),
    ),
    _contract(
        "collaboration.ambiguity_resolution",
        "ambiguity_episode",
        ObservationScope.CONVERSATION,
        EvidenceLane.DETERMINISTIC_SMALL,
        (
            _factor("ambiguity_identified", "A material ambiguity is identified."),
            _factor("clarified_or_replaced", "The ambiguity is clarified or the premise is replaced."),
            _factor("resolved_before_dependency", "Resolution occurs before dependent work relies on it."),
        ),
        closure_horizon="episode_closed_or_right_censored",
    ),
    _contract(
        "collaboration.clarification_yield",
        "clarification_question",
        ObservationScope.CONVERSATION,
        EvidenceLane.DETERMINISTIC_SMALL,
        (
            _factor("relevant_question", "The clarification question targets a material uncertainty."),
            _factor("substantive_answer", "The response substantively answers the clarification."),
            _factor("downstream_incorporation", "The answer is incorporated into later work."),
        ),
        closure_horizon="answer_and_downstream_use",
    ),
    _contract(
        "collaboration.exploration_conversion",
        "exploration_hypothesis",
        ObservationScope.CONVERSATION,
        EvidenceLane.DETERMINISTIC_SMALL_OBJECTIVE,
        (
            _factor("hypothesis", "The exploration states a testable hypothesis or uncertainty."),
            _factor("evidence_action", "An evidence-producing action addresses the hypothesis."),
            _factor("decision_update", "The resulting evidence updates a decision or plan."),
            _factor("objective_support", "Objective evidence supports the reported exploration result."),
        ),
        closure_horizon="evidence_action_completed",
    ),
    _contract(
        "collaboration.scope_change_discipline",
        "scope_change_episode",
        ObservationScope.CONVERSATION,
        EvidenceLane.DETERMINISTIC_SMALL,
        (
            _factor("acknowledgement", "The scope change is explicitly acknowledged."),
            _factor("impact", "Its impact on prior work or constraints is assessed."),
            _factor("replan", "The plan or next action is updated."),
            _factor("old_work_disposition", "Superseded work is retained, revised, or discarded explicitly."),
        ),
        closure_horizon="updated_plan_or_completion",
    ),
    _contract(
        "collaboration.rework_candidate_rate",
        "feedback_episode",
        ObservationScope.CONVERSATION,
        EvidenceLane.DETERMINISTIC_SMALL,
        (
            _factor("correction_signal", "Feedback corrects a misunderstanding or defective prior result."),
            _factor("new_information_exclusion", "New information is not mislabeled as rework."),
            _factor("scope_evolution_exclusion", "A genuine scope change is not mislabeled as rework."),
        ),
        closure_horizon="feedback_classified",
    ),
    _contract(
        "logic.decomposition_coverage",
        "active_requirement",
        ObservationScope.CONVERSATION,
        EvidenceLane.DETERMINISTIC_SMALL_RETRIEVAL,
        (
            _factor("requirement_link", "The plan item is linked to an active requirement."),
            _factor("actionable_plan_item", "The linked plan item is concrete and actionable."),
        ),
    ),
    _contract(
        "logic.hypothesis_test_linkage",
        "hypothesis_episode",
        ObservationScope.OBJECTIVE_EVIDENCE,
        EvidenceLane.DETERMINISTIC_SMALL_OBJECTIVE,
        (
            _factor("hypothesis", "A discriminating hypothesis is explicit."),
            _factor("planned_check", "A check capable of distinguishing outcomes is planned."),
            _factor("execution_receipt", "The check has an objective execution receipt.", critical=True),
            _factor("result_link", "The observed result is linked to the hypothesis."),
            _factor("belief_update", "The result updates the conclusion, decision, or plan."),
        ),
        closure_horizon="objective_check_completed",
        objective=True,
    ),
    _contract(
        "logic.decision_rationale_coverage",
        "material_decision",
        ObservationScope.CONVERSATION,
        EvidenceLane.DETERMINISTIC_SMALL,
        (
            _factor("decision", "A material decision is explicit."),
            _factor("evidence_or_constraint", "The decision is linked to evidence or a constraint."),
            _factor("rationale_or_alternative", "A concise rationale or considered alternative is recorded."),
            _factor("downstream_consistency", "Later action is consistent with the decision."),
        ),
    ),
    _contract(
        "logic.requirement_action_traceability",
        "active_requirement",
        ObservationScope.OBJECTIVE_EVIDENCE,
        EvidenceLane.DETERMINISTIC_SMALL_RETRIEVAL,
        (
            _factor("requirement", "The active requirement is identified."),
            _factor("action_or_artifact", "An executed action or produced artifact is linked to it."),
            _factor("objective_link", "The link is supported by typed action or artifact evidence."),
        ),
        objective=True,
    ),
    _contract(
        "logic.open_loop_closure",
        "open_loop_episode",
        ObservationScope.CONVERSATION,
        EvidenceLane.DETERMINISTIC_SMALL,
        (
            _factor("open_loop", "A material question or open loop is identified."),
            _factor("linked_resolution", "A later answer or action resolves the same loop."),
            _factor("not_reopened", "The loop remains closed through the observation horizon."),
        ),
        closure_horizon="episode_end_or_right_censored",
    ),
    _contract(
        "outcome.agent_claim_grounding",
        "material_completion_claim",
        ObservationScope.OBJECTIVE_EVIDENCE,
        EvidenceLane.DETERMINISTIC_SMALL_OBJECTIVE,
        (
            _factor("completion_claim", "A material completion claim is identified."),
            _factor("fresh_scoped_evidence", "Fresh objective evidence supports the claim and scope.", critical=True),
            _factor("no_conflict", "No objective receipt conflicts with the claim.", critical=True),
        ),
        objective=True,
    ),
    _contract(
        "outcome.verification_strategy_adequacy",
        "testable_requirement",
        ObservationScope.OBJECTIVE_EVIDENCE,
        EvidenceLane.DETERMINISTIC_SMALL_OBJECTIVE,
        (
            _factor("requirement", "The verification is linked to a testable requirement."),
            _factor("method", "The verification method is appropriate for the requirement."),
            _factor("oracle", "The pass or fail oracle is valid."),
            _factor("scope", "The verification scope matches the claim."),
            _factor("edge_strategy", "Negative or edge cases are addressed when applicable."),
        ),
        objective=True,
    ),
    _contract(
        "outcome.first_pass_verification",
        "eligible_verification_task",
        ObservationScope.OBJECTIVE_EVIDENCE,
        EvidenceLane.OBJECTIVE_ONLY,
        (
            _factor("eligible_task", "The task has an executable verification opportunity."),
            _factor("first_outcome", "The first valid executable verification outcome is identified.", critical=True),
            _factor("outcome_validity", "The first outcome is fresh, scoped, and mechanically valid.", critical=True),
        ),
        objective=True,
    ),
    _contract(
        "outcome.verified_requirement_coverage",
        "active_requirement",
        ObservationScope.OBJECTIVE_EVIDENCE,
        EvidenceLane.OBJECTIVE_ONLY,
        (
            _factor("requirement", "The active requirement is identified."),
            _factor("passing_evidence_or_acceptance", "Passing objective evidence or explicit user acceptance is linked.", critical=True),
            _factor("freshness_scope", "The evidence is fresh and covers the requirement scope.", critical=True),
        ),
        objective=True,
    ),
)


_CONTRACT_BY_KEY = {item.metric_key: item for item in PROBABILISTIC_METRIC_CONTRACTS}
if len(_CONTRACT_BY_KEY) != 20:
    raise RuntimeError("probabilistic registry must contain exactly twenty metrics")


def probabilistic_metric_contract(metric_key: str) -> MetricContract:
    try:
        return _CONTRACT_BY_KEY[metric_key]
    except KeyError:
        raise ValueError("metric is outside the probabilistic registry") from None


def probabilistic_contract_set_fingerprint() -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "registry": PROBABILISTIC_CONTRACT_REGISTRY_VERSION,
                "contracts": [
                    (item.metric_key, item.fingerprint)
                    for item in PROBABILISTIC_METRIC_CONTRACTS
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


class PredictiveFactorContribution(StrictModel):
    factor_key: str
    scale: FactorScale
    weight: float = Field(gt=0, allow_inf_nan=False)
    applicability_probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    present_probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    neutral_probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    absent_probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    expert_count: int = Field(ge=1, le=8)
    critical: bool

    _key = field_validator("factor_key")(_safe)

    @model_validator(mode="after")
    def validate_probabilities(self) -> "PredictiveFactorContribution":
        if not math.isclose(
            self.present_probability
            + self.neutral_probability
            + self.absent_probability,
            1.0,
            rel_tol=0,
            abs_tol=1e-6,
        ):
            raise ValueError("factor state probabilities must sum to one")
        return self


class PredictiveModelStageReceipt(StrictModel):
    model_key: str
    repository_id: str
    revision: str
    status: Literal[
        "completed", "unavailable", "resource_exhausted", "failed"
    ]
    error_code: str | None = None
    device: Literal["cpu", "cuda", "mps"] | None = None
    quantization: Literal["none", "bitsandbytes_nf4"] = "none"
    inference_latency_ms: float | None = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    peak_accelerator_memory_mb: float | None = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    process_rss_mb: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    unloaded_after_stage: Literal[True] = True

    _versions = field_validator("model_key")(_safe)
    _error = field_validator("error_code")(
        lambda value: None if value is None else _safe(value)
    )

    @model_validator(mode="after")
    def validate_stage(self) -> "PredictiveModelStageReceipt":
        if self.status == "completed":
            if self.error_code is not None or self.device is None:
                raise ValueError("completed predictive stages require a device")
            if (
                self.peak_accelerator_memory_mb is not None
                and self.peak_accelerator_memory_mb > PROBABILISTIC_MAX_VRAM_MIB
            ):
                raise ValueError("predictive stage exceeds the VRAM contract")
            if (
                self.process_rss_mb is not None
                and self.process_rss_mb > PROBABILISTIC_MAX_RSS_MIB
            ):
                raise ValueError("predictive stage exceeds the RAM contract")
        elif self.error_code is None or self.device is not None:
            raise ValueError("incomplete predictive stages require a fixed error")
        return self


class SessionPredictiveMetricReceipt(StrictModel):
    metric_key: str
    target: PredictiveMetricTarget
    state: PredictiveMetricState
    mean: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    median: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    q05: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    q25: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    q75: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    q95: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    applicability_probability: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    pending_probability: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    model_disagreement: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    effective_observation_count: int = Field(ge=0, le=10_000_000)
    model_set_version: Literal[PROBABILISTIC_MODEL_SET_VERSION] = (
        PROBABILISTIC_MODEL_SET_VERSION
    )
    calibration_version: str
    contract_version: str
    contract_fingerprint: str
    density_bins: tuple[float, ...] = Field(
        default=(), max_length=PROBABILISTIC_DENSITY_BIN_COUNT
    )
    factors: tuple[PredictiveFactorContribution, ...] = Field(
        default=(), max_length=8
    )
    product_metric_eligible: Literal[False] = False

    _versions = field_validator(
        "metric_key", "calibration_version", "contract_version"
    )(_safe)

    @field_validator("contract_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("contract fingerprint must be lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def validate_distribution(self) -> "SessionPredictiveMetricReceipt":
        values = (self.mean, self.median, self.q05, self.q25, self.q75, self.q95)
        has_distribution = self.state in {
            PredictiveMetricState.EXPERIMENTAL,
            PredictiveMetricState.CALIBRATED,
            PredictiveMetricState.OUT_OF_DISTRIBUTION,
        }
        if has_distribution:
            if any(value is None for value in values):
                raise ValueError("predictive distributions require all quantiles")
            q05, q25, median, q75, q95 = (
                self.q05,
                self.q25,
                self.median,
                self.q75,
                self.q95,
            )
            assert None not in (q05, q25, median, q75, q95)
            if not q05 <= q25 <= median <= q75 <= q95:
                raise ValueError("predictive quantiles must be monotonic")
            if (
                self.applicability_probability is None
                or self.pending_probability is None
                or len(self.density_bins) != PROBABILISTIC_DENSITY_BIN_COUNT
                or not self.factors
            ):
                raise ValueError("predictive distributions require state mass and density")
            if not math.isclose(
                sum(self.density_bins), 1.0, rel_tol=0, abs_tol=1e-6
            ):
                raise ValueError("predictive density bins must sum to one")
            if (
                self.state is PredictiveMetricState.EXPERIMENTAL
                and self.calibration_version != EXPERIMENTAL_CALIBRATION_VERSION
            ):
                raise ValueError("experimental ranges cannot claim calibration")
        elif any(value is not None for value in values) or any(
            value is not None
            for value in (
                self.applicability_probability,
                self.pending_probability,
                self.model_disagreement,
            )
        ) or self.density_bins or self.factors:
            raise ValueError("unavailable predictions cannot contain numeric estimates")
        contract = probabilistic_metric_contract(self.metric_key)
        if (
            self.target is not contract.target
            or self.contract_version != contract.contract_version
            or self.contract_fingerprint != contract.fingerprint
        ):
            raise ValueError("predictive receipt does not match its metric contract")
        return self


class SessionPredictiveMetricSummary(StrictModel):
    """Compact trajectory projection; density/factor detail stays run-scoped."""

    metric_key: str
    target: PredictiveMetricTarget
    state: PredictiveMetricState
    mean: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    median: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    q05: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    q25: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    q75: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    q95: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    applicability_probability: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    pending_probability: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    model_disagreement: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    effective_observation_count: int = Field(ge=0, le=10_000_000)
    model_set_version: str
    calibration_version: str
    contract_version: str
    contract_fingerprint: str
    product_metric_eligible: Literal[False] = False

    _versions = field_validator(
        "metric_key",
        "model_set_version",
        "calibration_version",
        "contract_version",
    )(_safe)

    @classmethod
    def from_receipt(
        cls, receipt: SessionPredictiveMetricReceipt
    ) -> "SessionPredictiveMetricSummary":
        return cls.model_validate(
            receipt.model_dump(exclude={"density_bins", "factors"})
        )


class SessionPredictiveMetricProjection(StrictModel):
    projection_version: Literal[PROBABILISTIC_METRIC_PROJECTION_VERSION] = (
        PROBABILISTIC_METRIC_PROJECTION_VERSION
    )
    contract_registry_version: Literal[PROBABILISTIC_CONTRACT_REGISTRY_VERSION] = (
        PROBABILISTIC_CONTRACT_REGISTRY_VERSION
    )
    model_set_version: Literal[PROBABILISTIC_MODEL_SET_VERSION] = (
        PROBABILISTIC_MODEL_SET_VERSION
    )
    projected_at: datetime
    metrics: tuple[SessionPredictiveMetricReceipt, ...] = Field(
        min_length=20, max_length=20
    )
    model_stages: tuple[PredictiveModelStageReceipt, ...] = Field(max_length=8)
    sample_count: Literal[PROBABILISTIC_SAMPLE_COUNT] = PROBABILISTIC_SAMPLE_COUNT
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False
    calibrated_as_truth: Literal[False] = False

    _time = field_validator("projected_at")(_utc)

    @model_validator(mode="after")
    def validate_projection(self) -> "SessionPredictiveMetricProjection":
        keys = tuple(item.metric_key for item in self.metrics)
        expected = tuple(item.metric_key for item in PROBABILISTIC_METRIC_CONTRACTS)
        if len(set(keys)) != len(keys) or set(keys) != set(expected):
            raise ValueError("predictive projection must cover all twenty metrics")
        if len({item.model_key for item in self.model_stages}) != len(
            self.model_stages
        ):
            raise ValueError("predictive model stages must be unique")
        return self


__all__ = [
    "EXPERIMENTAL_CALIBRATION_VERSION",
    "EvidenceLane",
    "FactorContract",
    "FactorScale",
    "MetricContract",
    "ObservationScope",
    "PROBABILISTIC_CONTRACT_REGISTRY_VERSION",
    "PROBABILISTIC_DENSITY_BIN_COUNT",
    "PROBABILISTIC_MAX_EPISODE_TOKENS",
    "PROBABILISTIC_MAX_RSS_MIB",
    "PROBABILISTIC_MAX_VRAM_MIB",
    "PROBABILISTIC_METRIC_CONTRACTS",
    "PROBABILISTIC_METRIC_PROJECTION_VERSION",
    "PROBABILISTIC_MODEL_SET_VERSION",
    "PROBABILISTIC_SAMPLE_COUNT",
    "PredictiveFactorContribution",
    "PredictiveMetricState",
    "PredictiveMetricTarget",
    "PredictiveModelStageReceipt",
    "SessionPredictiveMetricProjection",
    "SessionPredictiveMetricReceipt",
    "SessionPredictiveMetricSummary",
    "probabilistic_contract_set_fingerprint",
    "probabilistic_metric_contract",
]
