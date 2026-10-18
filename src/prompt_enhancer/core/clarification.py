"""Deterministic clarification from explicit diagnostic readings."""

ASPECTS = {
    "goal": ("prompt.task_definition_coverage", "Goal: <specify: action, target and observable result>."),
    "scope": ("prompt.context_sufficiency", "Scope: <specify: files or components>."),
    "context": ("prompt.problem_evidence_quality", "Context: <specify: relevant evidence and current state>."),
    "constraints": ("prompt.constraint_precision", "Constraints: <specify: boundaries and compatibility>."),
    "acceptance": ("prompt.acceptance_testability", "Acceptance: <specify: observable checks>."),
    "deliverable": ("prompt.deliverable_contract", "Deliverable: <specify: output format>."),
}


def clarify_prompt(text, readings, *, focus=(), target_keys=(), targeted=False):
    measured = {reading.key: reading for reading in readings}
    additions = []
    for aspect, (key, wording) in ASPECTS.items():
        if focus and aspect not in focus:
            continue
        if targeted and target_keys and key not in target_keys:
            continue
        reading = measured.get(key)
        if reading is None or reading.state != "known" or (
            reading.value is not None and reading.value < 1
        ) or key in target_keys:
            additions.append("- " + wording)
    result = text.rstrip()
    if additions:
        result += "\n\nClarify before acting:\n" + "\n".join(additions)
    return result
