"""Harness execution wrapper, with compatibility for legacy enhancement requests."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
import hashlib
import json
import time
from types import MappingProxyType

from .contracts import (
    AssertionResult, Delta, Evaluation, ExecuteRequest, ExecutionError,
    ExecutionResult, GenerationContext, Identity, Objective, StageTiming, Subject, TextProvenance,
)
from .ports import Candidate, Consumer, CoreError, EvaluationProvider


def identity(request: Identity) -> dict[str, str]:
    return {key: getattr(request, key) for key in Identity.model_fields}


def execution_id(request: Identity) -> str:
    return hashlib.sha256(json.dumps(identity(request), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def text_provenance(text: str) -> TextProvenance:
    return TextProvenance(sha256=hashlib.sha256(text.encode()).hexdigest(), characters=len(text))


def compare(before: tuple[Evaluation, ...], after: tuple[Evaluation, ...]) -> tuple[Delta, ...]:
    result = []
    for left in before:
        right = next((r for r in after if r.evaluator_id == left.evaluator_id), None)
        for metric in left.metrics:
            other = next((m for m in right.metrics if m.key == metric.key), None) if right else None
            state, value, reason = "unknown", None, "metric_unknown"
            if right is None or left.kind != right.kind or left.provenance != right.provenance:
                state, reason = "not_comparable", "provenance_mismatch"
            elif other is not None and metric.state == other.state == "known":
                if metric.value is not None and other.value is not None:
                    state, value, reason = "comparable", other.value - metric.value, "same_evaluator"
                else:
                    state, reason = "not_comparable", "categorical_metric"
            result.append(Delta(evaluator_id=left.evaluator_id, metric_key=metric.key,
                                state=state, value=value, reason=reason))
    return tuple(result)


def assertions(request: ExecuteRequest, after: tuple[Evaluation, ...], deltas: tuple[Delta, ...]):
    results = []
    for assertion in request.assertions:
        value = None
        if assertion.operator == "minimum_delta":
            value = next((d.value for d in deltas if d.evaluator_id == assertion.evaluator_id
                          and d.metric_key == assertion.metric_key and d.state == "comparable"), None)
        else:
            value = next((m.value for e in after if e.evaluator_id == assertion.evaluator_id
                          for m in e.metrics if m.key == assertion.metric_key and m.state == "known"), None)
        outcome = "unknown" if value is None else "passed" if value >= assertion.threshold else "failed"
        results.append(AssertionResult(assertion=assertion, outcome=outcome, observed=value))
    outcome = ("not_evaluated" if not results else "failed" if any(r.outcome == "failed" for r in results)
               else "unknown" if any(r.outcome == "unknown" for r in results) else "passed")
    return tuple(results), outcome


class EnhancementEngine:
    def __init__(self, consumers: Mapping[str, Consumer], evaluators: Mapping[str, EvaluationProvider]):
        self.consumers = MappingProxyType(dict(consumers))
        self.evaluators = MappingProxyType(dict(evaluators))
        from ..workflows.prompts import PromptWorkflowRunner
        self.workflows = PromptWorkflowRunner(self.consumers)

    def validate(self, request: ExecuteRequest) -> None:
        if request.workflow:
            from ..workflows.prompts import PromptWorkflowInput
            self.workflows.validate(PromptWorkflowInput.from_execution(request))
        if request.strategy == "script.clarify.v1" and (
            request.parameters.generation.max_tokens is not None or request.parameters.generation.temperature is not None
        ):
            raise CoreError("script_generation_parameter_unsupported")
        if request.consumer and request.workflow is None:
            consumer = self.consumers.get(request.consumer.binding_id)
            if consumer is None or consumer.provider != request.consumer.provider:
                raise CoreError("consumer_binding_unsupported")
            consumer.validate(request)
        for spec in request.evaluation.evaluators:
            provider = self.evaluators.get(spec.binding_id)
            if provider is None:
                raise CoreError("evaluation_binding_unsupported")
            provider.validate(spec)
        supported_keys = {
            "deterministic": {"prompt.task_definition_coverage", "prompt.problem_evidence_quality",
                "prompt.context_sufficiency", "prompt.constraint_precision", "prompt.acceptance_testability", "prompt.deliverable_contract"},
            "classifier": {"nli.label"}, "embedding": {"embedding.similarity"}, "rubric": {"rubric.label"},
            "rerank": {"rerank.relevance"},
        }
        by_id = {spec.evaluator_id: spec for spec in request.evaluation.evaluators}
        for check in request.assertions:
            if check.metric_key not in supported_keys[by_id[check.evaluator_id].kind]:
                raise CoreError("assertion_metric_unsupported")
        if request.workflow:
            return
        for target in request.objective.targets:
            kind = by_id[target.evaluator_id].kind
            if target.metric_key not in supported_keys[kind]:
                raise CoreError("objective_metric_unsupported")
            if (target.kind == "numeric") != (kind in {"deterministic", "embedding", "rerank"}):
                raise CoreError("objective_target_kind_mismatch")
            if target.kind == "categorical":
                labels = {"present", "absent"} if kind == "rubric" else {"entailment", "neutral", "contradiction"}
                if target.desired_label not in labels:
                    raise CoreError("objective_label_unsupported")
        if request.strategy == "script.clarify.v1" and (
            request.steering.instructions is not None or request.steering.style != "preserve"
            or request.objective.description != Objective().description
        ):
            raise CoreError("script_steering_unsupported")
        if request.strategy == "script.clarify.v1" and any(
            target.kind != "numeric" or by_id[target.evaluator_id].kind != "deterministic" or target.direction != "increase"
            for target in request.objective.targets
        ):
            raise CoreError("script_objective_unsupported")

    async def execute(self, request: ExecuteRequest, progress: Callable[[str], None]) -> ExecutionResult:
        self.validate(request)
        result = ExecutionResult(**identity(request), execution_id=execution_id(request),
            status="running", assertion_outcome="not_evaluated", original=text_provenance(request.subject.text),
            effective_parameters=request.parameters, evaluation_profile=request.evaluation,
            strategy=request.strategy, consumer_binding=request.consumer,
            effective_objective=request.objective, effective_steering=request.steering,
            workflow=request.workflow, effective_workflow_steps=request.workflow_steps)
        stage, timings = "evaluate_original", []
        started = time.monotonic()

        async def evaluate(subject: Subject) -> tuple[Evaluation, ...]:
            nonlocal result
            values = []
            for spec in request.evaluation.evaluators:
                await asyncio.sleep(0)
                provider = self.evaluators[spec.binding_id]
                value = await provider.evaluate(subject, spec)
                if value.evaluator_id != spec.evaluator_id or value.kind != spec.kind or (
                    value.provenance.model_copy(update={"reported_model": None}) != provider.provenance
                ):
                    raise CoreError("evaluation_provenance_mismatch")
                values.append(value)
                result = result.model_copy(update={
                    "before" if stage == "evaluate_original" else "after": tuple(values)
                })
            return tuple(values)

        def advance(next_stage):
            nonlocal started, stage
            timings.append(StageTiming(stage=stage, seconds=time.monotonic() - started))
            stage, started = next_stage, time.monotonic()
            progress(stage)

        try:
            async with asyncio.timeout(request.parameters.timeout_seconds):
                progress(stage)
                result = result.model_copy(update={"before": await evaluate(request.subject)})
                advance("generate")
                if request.workflow:
                    from ..workflows.prompts import PromptWorkflowInput
                    output = await self.workflows.run(PromptWorkflowInput.from_execution(request))
                    candidate = Candidate(output.text, output.provenance) if output.text is not None else None
                    result = result.model_copy(update={"workflow_result": output.receipt,
                        "consumer_provenance": output.provenance,
                        "generation_context_version": "workflow-input.v1",
                        "generation_prompt_version": output.provenance.rubric_version
                            if output.provenance and output.provenance.rubric_version else "not_applicable"})
                    # Keep the receipt, but never treat a failed step as a valid review without a rewrite.
                    if any(step.status == "failed" for step in output.receipt.steps):
                        review = output.receipt.review
                        code = {"reply_invalid": "workflow_review_reply_invalid",
                                "model_error": "workflow_review_model_error"}.get(
                                    review.state if review else None, "workflow_step_failed")
                        raise CoreError(code)
                else:
                    generation_context = GenerationContext(**identity(request), before=result.before,
                        evaluation_profile=request.evaluation, objective=request.objective, steering=request.steering)
                    if request.consumer:
                        candidate = await self.consumers[request.consumer.binding_id].generate(request, generation_context)
                    else:
                        from .scripted import clarify
                        candidate = clarify(request, generation_context)
                after = ()
                if candidate is not None:
                    if not candidate.text.strip() or (request.workflow is None
                            and len(candidate.text) > request.parameters.generation.max_output_chars):
                        raise CoreError("candidate_invalid")
                    result = result.model_copy(update={"candidate": text_provenance(candidate.text),
                        "enhanced_prompt": candidate.text, "consumer_provenance": candidate.provenance})
                    advance("evaluate_candidate")
                    after = await evaluate(Subject(text=candidate.text, context=request.subject.context))
                result = result.model_copy(update={"after": after})
                advance("compare")
                deltas = compare(result.before, after) if candidate is not None else tuple(
                    Delta(evaluator_id=e.evaluator_id, metric_key=m.key, state="unknown", reason="workflow_no_candidate")
                    for e in result.before for m in e.metrics)
                checks, outcome = assertions(request, after, deltas)
                result = result.model_copy(update={"status": "succeeded", "deltas": deltas,
                    "assertions": checks, "assertion_outcome": outcome})
        except TimeoutError:
            result = result.model_copy(update={"status": "timed_out", "errors": (ExecutionError(code="deadline_exceeded", stage=stage),)})
        except asyncio.CancelledError:
            result = result.model_copy(update={"status": "cancelled", "errors": (ExecutionError(code="cancelled", stage=stage),)})
        except CoreError as exc:
            result = result.model_copy(update={"status": "uncertain" if exc.uncertain else "failed",
                "errors": (ExecutionError(code=exc.code, stage=stage, operation_id=exc.operation_id),)})
        except Exception:
            result = result.model_copy(update={"status": "failed", "errors": (ExecutionError(code="execution_failed", stage=stage),)})
        timings.append(StageTiming(stage=stage, seconds=time.monotonic() - started))
        return result.model_copy(update={"timings": tuple(timings)})
