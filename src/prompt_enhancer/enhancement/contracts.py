"""Authoritative, closed wire models for the enhancement execution protocol."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from . import CORE_VERSION, PROTOCOL_VERSION
from ..core.prompt_evaluation import PromptMetricReading
from ..core.prompt_review import ContextInference, ModelCommentary

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")]


def valid_text(value: str) -> str:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise ValueError("invalid_unicode") from None
    if not value.strip():
        raise ValueError("blank_text")
    return value


Text = Annotated[str, Field(min_length=1, max_length=20_000), AfterValidator(valid_text)]
Finite = Annotated[float, Field(allow_inf_nan=False)]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Identity(WireModel):
    experiment_id: Identifier
    revision: Identifier
    run_id: Identifier
    correlation_id: Identifier
    unit_id: Identifier
    attempt_id: Identifier


class ContextMessage(WireModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, Field(min_length=1, max_length=8_000), AfterValidator(valid_text)]


class Subject(WireModel):
    text: Text
    context: tuple[ContextMessage, ...] = Field(default=(), max_length=24)

    @model_validator(mode="after")
    def bounded(self) -> Subject:
        if not self.text.strip() or sum(len(m.content) for m in self.context) > 40_000:
            raise ValueError("subject_invalid")
        return self


class ConsumerBinding(WireModel):
    binding_id: Identifier
    provider: Literal["openhands_acp", "inference"]


class GenerationSettings(WireModel):
    max_output_chars: int = Field(default=20_000, ge=256, le=20_000)
    max_tokens: int | None = Field(default=None, ge=16, le=8192)
    temperature: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class Parameters(WireModel):
    timeout_seconds: int = Field(default=120, ge=1, le=600)
    generation: GenerationSettings = Field(default_factory=GenerationSettings)


class Evaluator(WireModel):
    evaluator_id: Identifier
    kind: Literal["deterministic", "classifier", "embedding", "rubric", "rerank"]
    binding_id: Identifier
    target: Text | None = None
    rubric: Literal["task_definition", "constraint_precision", "acceptance_testability", "deliverable_contract"] | None = None
    generation: GenerationSettings | None = None

    @model_validator(mode="after")
    def typed_parameters(self) -> Evaluator:
        if (self.target is not None) != (self.kind in {"classifier", "embedding", "rerank"}):
            raise ValueError("target_required_for_pair_evaluation")
        if (self.rubric is not None) != (self.kind == "rubric"):
            raise ValueError("rubric_required_only_for_rubric_evaluation")
        if self.generation is not None and self.kind != "rubric":
            raise ValueError("generation_only_for_rubric_evaluation")
        return self


class EvaluationProfile(WireModel):
    profile_id: Identifier
    revision: Identifier
    evaluators: tuple[Evaluator, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def unique_evaluators(self) -> EvaluationProfile:
        if len({e.evaluator_id for e in self.evaluators}) != len(self.evaluators):
            raise ValueError("duplicate_evaluator")
        return self


class Assertion(WireModel):
    evaluator_id: Identifier
    metric_key: Identifier
    operator: Literal["minimum_value", "minimum_delta"]
    threshold: Finite


class NumericTarget(WireModel):
    kind: Literal["numeric"] = "numeric"
    evaluator_id: Identifier
    metric_key: Identifier
    direction: Literal["increase", "decrease"]
    desired_value: Finite | None = None


class CategoricalTarget(WireModel):
    kind: Literal["categorical"] = "categorical"
    evaluator_id: Identifier
    metric_key: Identifier
    desired_label: Identifier


OptimizationTarget = Annotated[NumericTarget | CategoricalTarget, Field(discriminator="kind")]


class Objective(WireModel):
    objective_id: Identifier = "prompt-clarity"
    revision: Identifier = "1"
    description: Annotated[str, Field(min_length=1, max_length=2_000), AfterValidator(valid_text)] = (
        "Improve clarity and testability while preserving intent. Mark unavailable details with placeholders."
    )
    targets: tuple[OptimizationTarget, ...] = Field(default=(), max_length=16)


class Steering(WireModel):
    profile: Literal["conservative.v1", "targeted.v1"] = "conservative.v1"
    style: Literal["preserve", "concise", "structured"] = "preserve"
    focus: tuple[Literal["goal", "scope", "context", "constraints", "acceptance", "deliverable"], ...] = Field(default=(), max_length=6)
    instructions: Annotated[str, Field(min_length=1, max_length=2_000), AfterValidator(valid_text)] | None = None


class WorkflowReference(WireModel):
    workflow_id: Literal["prompt-check", "prompt-rewrite", "prompt-clarify"]
    version: Literal["1.0.0", "1.1.0", "2.0.0", "2.1.0"]
    definition_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Policy(WireModel):
    policy_id: Identifier
    revision: Identifier
    instructions: Text


class WorkflowStepSettings(WireModel):
    binding: ConsumerBinding | None = None
    policy: Policy | None = None
    generation: GenerationSettings | None = None
    enable_thinking: bool | None = None


class ModelCall(WireModel):
    """Provider input contains only the workflow's selected messages and settings."""
    system: Annotated[str, Field(min_length=1, max_length=32_000), AfterValidator(valid_text)]
    user: Annotated[str, Field(min_length=1, max_length=600_000), AfterValidator(valid_text)]
    policy_version: Identifier
    generation: GenerationSettings
    timeout_seconds: int = Field(ge=1, le=600)
    response_schema: dict | None = None
    enable_thinking: bool | None = None


class ExecuteRequest(Identity):
    protocol_version: Literal["enhancement.v1"] = PROTOCOL_VERSION
    data_policy: Literal["synthetic_benchmark"]
    subject: Subject
    strategy: Literal["script.clarify.v1", "consumer.rewrite.v1", "prompt.check.v1"]
    parameters: Parameters = Field(default_factory=Parameters)
    consumer: ConsumerBinding | None = None
    evaluation: EvaluationProfile
    assertions: tuple[Assertion, ...] = Field(default=(), max_length=32)
    objective: Objective = Field(default_factory=Objective)
    steering: Steering = Field(default_factory=Steering)
    workflow: WorkflowReference | None = None
    workflow_steps: dict[Identifier, WorkflowStepSettings] = Field(default_factory=dict, max_length=8)

    @model_validator(mode="after")
    def consistent(self) -> ExecuteRequest:
        if self.workflow is not None:
            from ..workflows.catalog import validate_configuration
            validate_configuration(self)
        elif self.workflow_steps or self.strategy == "prompt.check.v1":
            raise ValueError("versioned_workflow_required")
        elif (self.consumer is not None) != (self.strategy == "consumer.rewrite.v1"):
            raise ValueError("consumer_required_only_for_consumer_strategy")
        ids = {e.evaluator_id for e in self.evaluation.evaluators}
        if any(a.evaluator_id not in ids for a in self.assertions):
            raise ValueError("assertion_evaluator_unknown")
        objective_ids = {"diagnostics"} if self.workflow else ids
        if any(target.evaluator_id not in objective_ids for target in self.objective.targets):
            raise ValueError("objective_evaluator_unknown")
        return self


class Provenance(WireModel):
    provider: Identifier
    adapter_version: Identifier
    model: str | None = Field(default=None, max_length=160)
    model_revision: str | None = Field(default=None, max_length=160)
    model_license: str | None = Field(default=None, max_length=100)
    tokenizer_revision: str | None = Field(default=None, max_length=160)
    rubric_version: Identifier | None = None
    metric_version: Identifier | None = None
    redactor_version: Identifier | None = None
    identity_source: Literal["not_applicable", "configured", "verified_manifest"] = "not_applicable"
    reported_model: str | None = Field(default=None, max_length=160)
    operation_id: Identifier | None = None
    reasoning_effort: Literal["none", "low", "medium", "high"] | None = None


class Metric(WireModel):
    key: Identifier
    state: Literal["known", "unknown", "not_applicable", "abstained", "execution_error"]
    value: Finite | None = None
    label: Identifier | None = None
    reason: Identifier

    @model_validator(mode="after")
    def preserve_unknowns(self) -> Metric:
        if self.state != "known" and (self.value is not None or self.label is not None):
            raise ValueError("unknown_metric_has_value")
        if self.state == "known" and self.value is None and self.label is None:
            raise ValueError("known_metric_requires_value")
        return self


class Evaluation(WireModel):
    evaluator_id: Identifier
    kind: Literal["deterministic", "classifier", "embedding", "rubric", "rerank"]
    provenance: Provenance
    metrics: tuple[Metric, ...]


class GenerationContext(Identity):
    protocol_version: Literal["enhancement-generation.v1"] = "enhancement-generation.v1"
    prompt_version: Literal["enhancement-rewrite.v2"] = "enhancement-rewrite.v2"
    before: tuple[Evaluation, ...]
    evaluation_profile: EvaluationProfile
    objective: Objective
    steering: Steering
    output_contract: Literal["enhanced-prompt.v1"] = "enhanced-prompt.v1"


class Delta(WireModel):
    evaluator_id: Identifier
    metric_key: Identifier
    state: Literal["comparable", "unknown", "not_comparable"]
    value: Finite | None = None
    reason: Identifier


class AssertionResult(WireModel):
    assertion: Assertion
    outcome: Literal["passed", "failed", "unknown"]
    observed: Finite | None = None


class TextProvenance(WireModel):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    characters: int = Field(ge=0)


class StageTiming(WireModel):
    stage: Literal["evaluate_original", "generate", "evaluate_candidate", "compare"]
    seconds: float = Field(ge=0, allow_inf_nan=False)


class WorkflowStepReceipt(WireModel):
    step_id: Identifier
    implementation: Identifier
    status: Literal["succeeded", "skipped", "failed"]
    provenance: Provenance | None = None
    policy: Policy | None = None
    generation: GenerationSettings | None = None
    binding: ConsumerBinding | None = None
    enable_thinking: bool | None = None


class WorkflowCommentary(ModelCommentary):
    inference_provider: Literal["local", "litellm", "openhands_acp"] = "local"


class WorkflowReceipt(WireModel):
    workflow: WorkflowReference
    definition_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    configuration_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    compatible_core: str
    steps: tuple[WorkflowStepReceipt, ...]
    # These are workflow diagnostics; they never stand in for harness measurements.
    diagnostics: tuple[PromptMetricReading, ...] = ()
    context: ContextInference | None = None
    review: WorkflowCommentary | None = None


class ExecutionError(WireModel):
    code: Identifier
    stage: Identifier
    retryable: bool = False
    operation_id: Identifier | None = None


ExecutionStatus = Literal["queued", "running", "cancelling", "succeeded", "failed", "cancelled", "timed_out", "uncertain"]


class ExecutionResult(Identity):
    protocol_version: Literal["enhancement.v1"] = PROTOCOL_VERSION
    core_version: str = CORE_VERSION
    execution_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ExecutionStatus
    assertion_outcome: Literal["passed", "failed", "unknown", "not_evaluated"]
    original: TextProvenance
    candidate: TextProvenance | None = None
    enhanced_prompt: Text | None = None
    consumer_provenance: Provenance | None = None
    before: tuple[Evaluation, ...] = ()
    after: tuple[Evaluation, ...] = ()
    deltas: tuple[Delta, ...] = ()
    assertions: tuple[AssertionResult, ...] = ()
    effective_parameters: Parameters
    evaluation_profile: EvaluationProfile
    strategy: Literal["script.clarify.v1", "consumer.rewrite.v1", "prompt.check.v1"]
    consumer_binding: ConsumerBinding | None = None
    effective_objective: Objective = Field(default_factory=Objective)
    effective_steering: Steering = Field(default_factory=Steering)
    generation_context_version: Identifier = "enhancement-generation.v1"
    generation_prompt_version: Identifier = "enhancement-rewrite.v2"
    timings: tuple[StageTiming, ...] = ()
    errors: tuple[ExecutionError, ...] = ()
    workflow: WorkflowReference | None = None
    effective_workflow_steps: dict[Identifier, WorkflowStepSettings] = Field(default_factory=dict)
    workflow_result: WorkflowReceipt | None = None


class Progress(Identity):
    protocol_version: Literal["enhancement.v1"] = PROTOCOL_VERSION
    execution_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ExecutionStatus
    stage: Literal["queued", "evaluate_original", "generate", "evaluate_candidate", "compare", "finished"]
    sequence: int = Field(ge=0)
    result_available: bool


class Readiness(WireModel):
    protocol_version: Literal["enhancement.v1"] = PROTOCOL_VERSION
    core_version: str = CORE_VERSION
    ready: bool
    active: int = Field(ge=0)
    retained: int = Field(ge=0)
    capacity: int = Field(ge=1)
    reason: Identifier


class ConsumerCapability(WireModel):
    binding_id: Identifier
    provider: Literal["openhands_acp", "inference"]
    provenance: Provenance


class EvaluatorCapability(WireModel):
    binding_id: Identifier
    kind: Literal["deterministic", "classifier", "embedding", "rubric", "rerank"]
    provenance: Provenance


class Capabilities(WireModel):
    protocol_version: Literal["enhancement.v1"] = PROTOCOL_VERSION
    core_version: str = CORE_VERSION
    strategies: tuple[Literal["script.clarify.v1", "consumer.rewrite.v1"], ...]
    consumers: tuple[ConsumerCapability, ...]
    evaluators: tuple[EvaluatorCapability, ...]
    request_schema: dict
    data_policies: tuple[Literal["synthetic_benchmark"], ...] = ("synthetic_benchmark",)
    result_storage: Literal["ephemeral"] = "ephemeral"
    max_active: int = Field(ge=1, le=4)
    max_retained: int = Field(ge=1, le=128)
    workflows: tuple[dict, ...] = ()
