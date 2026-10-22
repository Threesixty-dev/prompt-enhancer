"""Reviewed, immutable compositions; no request-supplied executable graph."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json

from packaging.specifiers import SpecifierSet

from .prompt_policies import REVIEW_POLICIES


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    strategy: str
    steps: tuple[tuple[str, str], ...]
    model_step: str | None
    optional_model: bool = False
    version: str = "1.0.0"
    compatible_core: str = ">=0.2.0,<0.3.0"
    core_version_pattern: str = r"^0\.2\.[0-9]+$"

    @property
    def uses_review(self):
        return self.model_step == "review"

    def payload(self):
        return {
            "workflow_id": self.workflow_id, "version": self.version,
            "compatible_core": self.compatible_core, "strategy": self.strategy,
            "core_version_pattern": self.core_version_pattern,
            "input_contract": "prompt-subject.v1",
            "output_contract": "prompt-review.v1" if self.uses_review else "enhanced-prompt.v1",
            "steps": [{"step_id": key, "implementation": implementation}
                      for key, implementation in self.steps],
            "model_step": self.model_step, "optional_model": self.optional_model,
            "configurable_steps": {} if self.model_step is None else {
                self.model_step: ["binding", "policy", "generation", "enable_thinking"]},
            "defaults": {"policy_version": REVIEW_POLICIES[self.workflow_id][0],
                         "max_tokens": 1100, "temperature": 0.2, "enable_thinking": False}
                        if self.uses_review else {
                            "policy_version": "workflow-rewrite.v1" if self.model_step else "script.clarify.v1"},
        }

    def presentation(self):
        if self.uses_review:
            title = {"prompt-check": "Prompt Check", "prompt-rewrite": "Rewrite review",
                     "prompt-clarify": "Clarification review"}[self.workflow_id]
            return {"title": title + " (pre-Bench flow)",
                    "logic_steps": ["Score prompt", "Infer context", "Optional model review and rewrite"],
                    "relationship": "Uses the pre-Bench Prompt Check sequence. The review may return findings without a rewrite."}
        title = "Direct rewrite" if self.model_step else "Rule-based clarification"
        return {"title": title + " (Bench legacy)",
                "logic_steps": ["Score prompt", "Request a rewrite" if self.model_step else "Add clarification placeholders"],
                "relationship": "Retained Bench flow for existing experiment pins. Does not use the pre-Bench review sequence."}

    @property
    def sha256(self):
        return hashlib.sha256(json.dumps(self.payload(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def reference(self):
        return {"workflow_id": self.workflow_id, "version": self.version, "definition_sha256": self.sha256}


LEGACY_WORKFLOWS = (
    WorkflowDefinition("prompt-check", "prompt.check.v1", (
        ("diagnose", "prompt-evaluation.v1"), ("context", "prompt-context.v1"),
        ("review", "prompt-commentary.v1")), "review", optional_model=True),
    WorkflowDefinition("prompt-rewrite", "consumer.rewrite.v1", (
        ("diagnose", "prompt-evaluation.v1"), ("rewrite", "prompt-rewrite.v3")), "rewrite"),
    WorkflowDefinition("prompt-clarify", "script.clarify.v1", (
        ("diagnose", "prompt-evaluation.v1"), ("clarify", "script.clarify.v1")), None),
    WorkflowDefinition("prompt-rewrite", "prompt.check.v1", (
        ("diagnose", "prompt-evaluation.v1"), ("context", "prompt-context.v1"),
        ("review", "prompt-commentary.v1")), "review", optional_model=True, version="2.0.0"),
    WorkflowDefinition("prompt-clarify", "prompt.check.v1", (
        ("diagnose", "prompt-evaluation.v1"), ("context", "prompt-context.v1"),
        ("review", "prompt-commentary.v1")), "review", optional_model=True, version="2.0.0"),
)

# Compatibility is part of the immutable digest. Retain every 0.2.x pin and
# publish new manifest versions for the unchanged workflow logic on 0.3.x.
WORKFLOWS = LEGACY_WORKFLOWS + tuple(
    replace(item, version="1.1.0" if item.version == "1.0.0" else "2.1.0",
            compatible_core=">=0.3.0,<0.4.0", core_version_pattern=r"^0\.3\.[0-9]+$")
    for item in LEGACY_WORKFLOWS
)


def resolve(reference, core_version=None):
    from ..enhancement import CORE_VERSION
    definition = next((item for item in WORKFLOWS if item.workflow_id == reference.workflow_id
                       and item.version == reference.version), None)
    if definition is None:
        raise ValueError("workflow_version_unsupported")
    if reference.definition_sha256 != definition.sha256:
        raise ValueError("workflow_definition_mismatch")
    if (core_version or CORE_VERSION) not in SpecifierSet(definition.compatible_core):
        raise ValueError("workflow_core_incompatible")
    return definition


def validate_configuration(request):
    definition = resolve(request.workflow)
    if request.strategy != definition.strategy:
        raise ValueError("workflow_strategy_fixed")
    supported = {definition.model_step} if definition.model_step else set()
    if not set(request.workflow_steps) <= supported:
        raise ValueError("workflow_step_not_configurable")
    step = request.workflow_steps.get(definition.model_step)
    binding = step.binding if step and step.binding else request.consumer
    if definition.model_step is None and request.consumer is not None:
        raise ValueError("workflow_has_no_model_step")
    if definition.model_step and not definition.optional_model and binding is None:
        raise ValueError("workflow_model_binding_required")
    if step and binding is None and (step.policy is not None or step.generation is not None):
        raise ValueError("workflow_model_binding_required")
    if any(target.kind != "numeric" or target.direction != "increase"
           for target in request.objective.targets):
        raise ValueError("workflow_diagnostic_target_unsupported")


def catalog():
    # Presentation can be clarified without rebinding historical behavior digests.
    return [item.payload() | {"definition_sha256": item.sha256, "presentation": item.presentation()}
            for item in WORKFLOWS]
