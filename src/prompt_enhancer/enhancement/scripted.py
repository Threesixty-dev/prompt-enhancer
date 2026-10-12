"""Packaged clarification strategy driven by evaluator findings, not shell code."""
from .contracts import ExecuteRequest, GenerationContext, Provenance
from .ports import Candidate

_ASPECTS = {
    "goal": ("prompt.task_definition_coverage", "Goal: <specify: action, target and observable result>."),
    "scope": ("prompt.context_sufficiency", "Scope: <specify: files or components>."),
    "context": ("prompt.problem_evidence_quality", "Context: <specify: relevant evidence and current state>."),
    "constraints": ("prompt.constraint_precision", "Constraints: <specify: boundaries and compatibility>."),
    "acceptance": ("prompt.acceptance_testability", "Acceptance: <specify: observable checks>."),
    "deliverable": ("prompt.deliverable_contract", "Deliverable: <specify: output format>."),
}


def clarify(request: ExecuteRequest, context: GenerationContext) -> Candidate:
    measured = {metric.key: metric for result in context.before if result.kind == "deterministic" for metric in result.metrics}
    targeted = {target.metric_key for target in context.objective.targets}
    additions = []
    for aspect, (key, wording) in _ASPECTS.items():
        if context.steering.focus and aspect not in context.steering.focus:
            continue
        if context.steering.profile == "targeted.v1" and targeted and key not in targeted:
            continue
        reading = measured.get(key)
        # Unknowns prompt a clarification, not an invented numeric deficit.
        if reading is None or reading.state != "known" or (reading.value is not None and reading.value < 1) or key in targeted:
            additions.append("- " + wording)
    text = request.subject.text.rstrip()
    if additions:
        text += "\n\nClarify before acting:\n" + "\n".join(additions)
    return Candidate(text, Provenance(provider="packaged_script", adapter_version="script.clarify.v1",
        rubric_version=context.prompt_version))
