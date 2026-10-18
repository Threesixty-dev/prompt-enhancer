"""Prompt workflows usable by a harness or an app without harness judgments."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType, SimpleNamespace

from pydantic import Field, model_validator

from ..core.clarification import clarify_prompt
from ..core.prompt_evaluation import PROMPT_METRIC_KEYS
from ..core.prompt_review import (
    ModelCommentary, _CommentaryReply, _commentary_input, infer_context, parse_commentary_reply,
)
from ..core.prompt_rewrite import REWRITE_INSTRUCTION, parse_candidate
from ..enhancement.contracts import (
    ConsumerBinding, Identifier, ModelCall, Objective, Parameters,
    Provenance, Steering, Subject, WireModel, WorkflowCommentary, WorkflowReceipt, WorkflowReference,
    WorkflowStepReceipt, WorkflowStepSettings,
)
from ..enhancement.evaluators import DeterministicEvaluation
from ..enhancement.ports import CoreError
from ..infrastructure.language import DeterministicEnglishPolishDetector
from .catalog import resolve, validate_configuration
from .prompt_policies import REVIEW_POLICIES


class PromptWorkflowInput(WireModel):
    subject: Subject
    workflow: WorkflowReference
    consumer: ConsumerBinding | None = None
    parameters: Parameters = Field(default_factory=Parameters)
    objective: Objective = Field(default_factory=Objective)
    steering: Steering = Field(default_factory=Steering)
    workflow_steps: dict[Identifier, WorkflowStepSettings] = Field(default_factory=dict)

    @property
    def strategy(self):
        return resolve(self.workflow).strategy

    @model_validator(mode="after")
    def valid_configuration(self):
        validate_configuration(self)
        return self

    @classmethod
    def from_execution(cls, request):
        # Deliberate projection: no experiment evaluation, assertions, or judgments.
        return cls(**{key: getattr(request, key) for key in cls.model_fields})


@dataclass(frozen=True)
class PromptWorkflowOutput:
    text: str | None
    provenance: Provenance | None
    receipt: WorkflowReceipt


class PromptWorkflowRunner:
    def __init__(self, consumers, *, diagnostics=None, language_detector=None):
        self.consumers = MappingProxyType(dict(consumers))
        self.diagnostics = diagnostics or DeterministicEvaluation()
        self.language = language_detector or DeterministicEnglishPolishDetector()

    def _settings(self, inputs):
        definition = resolve(inputs.workflow)
        step = inputs.workflow_steps.get(definition.model_step, WorkflowStepSettings())
        binding = step.binding or inputs.consumer
        generation = step.generation or inputs.parameters.generation
        if definition.uses_review:
            defaults = {"max_tokens": 1100, "temperature": 0.2}
            generation = generation.model_copy(update={key: value for key, value in defaults.items()
                if key not in generation.model_fields_set})
        return definition, step, binding, generation

    @staticmethod
    def _thinking(definition, step):
        if "enable_thinking" in step.model_fields_set:
            return step.enable_thinking
        return False if definition.uses_review else None

    def validate(self, inputs: PromptWorkflowInput):
        definition, step, binding, generation = self._settings(inputs)
        if any(target.evaluator_id != "diagnostics" or target.metric_key not in PROMPT_METRIC_KEYS
               for target in inputs.objective.targets):
            raise CoreError("workflow_diagnostic_target_unsupported")
        if definition.uses_review and (
            inputs.objective != Objective() or inputs.steering != Steering()
        ):
            raise CoreError("prompt_check_uses_review_step_policy")
        if definition.model_step is None and (
            generation.max_tokens is not None or generation.temperature is not None
            or inputs.steering.instructions is not None or inputs.steering.style != "preserve"
            or inputs.objective.description != Objective().description
        ):
            raise CoreError("script_steering_unsupported")
        if binding is not None:
            consumer = self.consumers.get(binding.binding_id)
            if consumer is None or consumer.provider != binding.provider:
                raise CoreError("consumer_binding_unsupported")
            if not callable(getattr(consumer, "complete", None)) or not callable(getattr(consumer, "validate_call", None)):
                raise CoreError("workflow_provider_contract_unsupported")
            consumer.validate_call(ModelCall(system="Validate settings.", user="Fictional input.",
                policy_version="validation.v1", generation=generation,
                timeout_seconds=inputs.parameters.timeout_seconds, enable_thinking=self._thinking(definition, step)))

    async def run(self, inputs: PromptWorkflowInput) -> PromptWorkflowOutput:
        self.validate(inputs)
        definition, step, binding, generation = self._settings(inputs)
        subject = inputs.subject
        text = subject.text.strip() if definition.uses_review else subject.text
        readings = self.diagnostics.evaluator.evaluate("0" * 64, text, subject.context)
        receipts = [WorkflowStepReceipt(step_id="diagnose", implementation="prompt-evaluation.v1",
            status="succeeded", provenance=self.diagnostics.provenance)]
        context, review, provenance, output = None, None, None, None
        if definition.uses_review:
            context = infer_context(text, subject.context, readings, self.language)
            receipts.append(WorkflowStepReceipt(step_id="context", implementation="prompt-context.v1", status="succeeded"))
            policy_version, policy = REVIEW_POLICIES[definition.workflow_id]
            if binding is None:
                review = ModelCommentary(state="no_active_model", prompt_version=policy_version)
                receipts.append(WorkflowStepReceipt(step_id="review", implementation="prompt-commentary.v1", status="skipped"))
            else:
                user = _commentary_input(SimpleNamespace(prior_messages=subject.context), text, readings, context)
                call = ModelCall(system=step.policy.instructions if step.policy else policy,
                    user=user, policy_version=step.policy.revision if step.policy else policy_version,
                    generation=generation, timeout_seconds=inputs.parameters.timeout_seconds,
                    response_schema=_CommentaryReply.model_json_schema(), enable_thinking=self._thinking(definition, step))
                try:
                    response = await self.consumers[binding.binding_id].complete(call)
                except CoreError as error:
                    if error.uncertain:
                        raise
                    review = ModelCommentary(state="model_error", prompt_version=call.policy_version)
                else:
                    review = parse_commentary_reply(response.text, prompt_chars=len(text)) or ModelCommentary(state="reply_invalid")
                    provenance, output = response.provenance, review.reformulated_prompt
                    review = WorkflowCommentary.model_validate(review.model_dump() | {"model_alias": provenance.model, "prompt_version": call.policy_version,
                        "model_revision": provenance.model_revision, "model_license": provenance.model_license,
                        "adapter_version": provenance.adapter_version,
                        "inference_provider": "litellm" if binding.provider == "inference" else "openhands_acp",
                        "caveat": "Model commentary is a suggestion, not an objective metric, and may be wrong."})
                receipts.append(WorkflowStepReceipt(step_id="review", implementation="prompt-commentary.v1",
                    status="succeeded" if review.state == "ok" else "failed", provenance=provenance,
                    policy=step.policy, generation=generation, binding=binding, enable_thinking=call.enable_thinking))
        elif definition.workflow_id == "prompt-rewrite":
            call = ModelCall(system=step.policy.instructions if step.policy else REWRITE_INSTRUCTION.replace(
                "generation_context.before", "workflow_diagnostics"), user=json.dumps({
                    "subject": subject.model_dump(), "workflow_diagnostics": [r.model_dump() for r in readings],
                    "objective": inputs.objective.model_dump(), "steering": inputs.steering.model_dump()}),
                policy_version=step.policy.revision if step.policy else "workflow-rewrite.v1",
                generation=generation, timeout_seconds=inputs.parameters.timeout_seconds,
                enable_thinking=self._thinking(definition, step))
            response = await self.consumers[binding.binding_id].complete(call)
            output, provenance = parse_candidate(response.text, generation.max_output_chars), response.provenance
            receipts.append(WorkflowStepReceipt(step_id="rewrite", implementation="prompt-rewrite.v3",
                status="succeeded", provenance=provenance, policy=step.policy, generation=generation,
                binding=binding, enable_thinking=call.enable_thinking))
        else:
            output = clarify_prompt(text, readings, focus=inputs.steering.focus,
                target_keys={target.metric_key for target in inputs.objective.targets},
                targeted=inputs.steering.profile == "targeted.v1")
            provenance = Provenance(provider="packaged_script", adapter_version="script.clarify.v1")
            receipts.append(WorkflowStepReceipt(step_id="clarify", implementation="script.clarify.v1",
                status="succeeded", provenance=provenance))
        if output is not None and (not output.strip() or len(output) > generation.max_output_chars):
            raise CoreError("candidate_invalid")
        configuration = {"inputs": inputs.model_dump(mode="json", exclude={"subject"}),
                         "steps": [receipt.model_dump(mode="json", exclude={"provenance", "status"}) for receipt in receipts]}
        configuration_sha256 = hashlib.sha256(json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return PromptWorkflowOutput(output, provenance, WorkflowReceipt(workflow=inputs.workflow,
            definition_sha256=definition.sha256, compatible_core=definition.compatible_core,
            configuration_sha256=configuration_sha256,
            steps=tuple(receipts), diagnostics=tuple(r.model_dump(mode="json") for r in readings),
            context=context.model_dump(mode="json") if context else None,
            review=review.model_dump(mode="json") if review else None))
