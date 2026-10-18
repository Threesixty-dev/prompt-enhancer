"""Packaged clarification strategy driven by evaluator findings, not shell code."""
from .contracts import ExecuteRequest, GenerationContext, Provenance
from .ports import Candidate
from ..core.clarification import ASPECTS as _ASPECTS, clarify_prompt


def clarify(request: ExecuteRequest, context: GenerationContext) -> Candidate:
    readings = [metric for result in context.before if result.kind == "deterministic" for metric in result.metrics]
    text = clarify_prompt(request.subject.text, readings, focus=context.steering.focus,
        target_keys={target.metric_key for target in context.objective.targets},
        targeted=context.steering.profile == "targeted.v1")
    return Candidate(text, Provenance(provider="packaged_script", adapter_version="script.clarify.v1",
        rubric_version=context.prompt_version))
