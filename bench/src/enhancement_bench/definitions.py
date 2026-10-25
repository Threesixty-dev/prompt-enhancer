"""GitOps definitions; execution messages are owned by contracts/enhancement."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Any, Literal

from jsonschema import Draft202012Validator, SchemaError, ValidationError
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_serializer, model_validator

from .errors import BenchError

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")]
IMAGE = re.compile(r"^[a-z0-9][a-z0-9./:_-]{0,240}@sha256:[a-f0-9]{64}$")
CoreVersion = Annotated[str, StringConstraints(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$", max_length=80)]


def canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError):
        raise BenchError("invalid_json") from None


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Subject(StrictModel):
    id: Identifier
    text: str = Field(min_length=1, max_length=32000)
    context: list[dict[str, str]] = Field(default_factory=list, max_length=8)


class CoreBuild(StrictModel):
    variant: Literal["default", "models"]
    image: str = Field(pattern=IMAGE.pattern)
    buildInputSha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ExperimentUnit(StrictModel):
    id: Identifier
    title: str = Field(min_length=1, max_length=120)
    strategy: str = Field(min_length=1, max_length=80)
    parameters: dict[str, Any] = Field(default_factory=dict)
    assertions: list[dict[str, Any]] = Field(default_factory=list, max_length=32)
    objective: dict[str, Any] = Field(default_factory=dict)
    steering: dict[str, Any] = Field(default_factory=dict)
    consumerBinding: dict[str, Any] = Field(default_factory=dict)
    stepSettings: dict[Identifier, dict[str, Any]] = Field(default_factory=dict)


class Experiment(StrictModel):
    schemaVersion: Literal["bench-experiment/v1", "bench-experiment/v2"]
    stableId: Identifier
    revision: Identifier
    generation: int = Field(ge=1, le=2**53 - 1)
    title: str = Field(min_length=1, max_length=120)
    enhancerVersion: str = Field(min_length=1, max_length=80)
    autoRun: bool = True
    subjects: list[Subject] = Field(min_length=1, max_length=32)
    units: list[ExperimentUnit] = Field(min_length=1, max_length=16)
    consumerBinding: dict[str, Any] | None
    evaluatorProfile: dict[str, Any]
    baseParameters: dict[str, Any] = Field(default_factory=dict)
    parameterSchema: dict[str, Any]
    objective: dict[str, Any]
    baseSteering: dict[str, Any]
    workflow: dict[str, Any] | None = None
    coreBuild: CoreBuild | None = None
    harnessAssertions: list[dict[str, Any]] = Field(default_factory=list, max_length=32)
    baseStepSettings: dict[Identifier, dict[str, Any]] = Field(default_factory=dict)

    @model_serializer(mode="wrap")
    def preserve_legacy_shape(self, handler):
        value = handler(self)
        if self.schemaVersion == "bench-experiment/v1":
            for key in ("workflow", "coreBuild", "harnessAssertions", "baseStepSettings"):
                value.pop(key, None)
            for unit in value["units"]:
                unit.pop("stepSettings", None)
        return value

    @model_validator(mode="after")
    def validate_definition(self):
        if self.schemaVersion == "bench-experiment/v2":
            if self.workflow is None or self.coreBuild is None:
                raise ValueError("workflow_and_core_build_required")
            if len({unit.strategy for unit in self.units}) != 1:
                raise ValueError("workflow_strategy_fixed")
            if any(unit.assertions for unit in self.units):
                raise ValueError("harness_assertions_belong_to_experiment")
        elif (self.workflow is not None or self.coreBuild is not None or self.harnessAssertions
              or self.baseStepSettings or any(unit.stepSettings for unit in self.units)):
            raise ValueError("versioned_experiment_required")
        for values in (self.subjects, self.units):
            if len({item.id for item in values}) != len(values):
                raise ValueError("duplicate_identifier")
        schema = self.parameterSchema
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            raise ValueError("closed_parameter_schema_required")
        # Definitions cannot resolve remote schemas or run arbitrary validators.
        if "$ref" in canonical(schema) or "$dynamicRef" in canonical(schema):
            raise ValueError("parameter_schema_refs_forbidden")
        try:
            Draft202012Validator.check_schema(schema)
            for unit in self.units:
                Draft202012Validator(schema).validate(self.baseParameters | unit.parameters)
        except (SchemaError, ValidationError):
            raise ValueError("invalid_parameters") from None
        return self


# Keep existing v1 imports and wire identities compatible.
Unit = ExperimentUnit
Definition = Experiment


class Publication(StrictModel):
    schemaVersion: Literal["bench-publication/v1", "bench-publication/v2"]
    definition: Definition
    image: str | None = None
    coreVersion: str | None = None

    @model_validator(mode="after")
    def validate_image(self):
        if self.definition.schemaVersion == "bench-experiment/v2" and self.schemaVersion != "bench-publication/v2":
            raise ValueError("versioned_definition_publication_required")
        if self.schemaVersion == "bench-publication/v2":
            if self.image is not None or self.coreVersion is not None:
                raise ValueError("definition_only_publication_required")
            return self
        if not isinstance(self.image, str) or not IMAGE.fullmatch(self.image):
            raise ValueError("immutable_image_required")
        if self.coreVersion != self.definition.enhancerVersion:
            raise ValueError("core_version_mismatch")
        return self


class CoreImage(StrictModel):
    schemaVersion: Literal["core-release/v1"]
    coreVersion: CoreVersion
    variant: Literal["default", "models"]
    image: str = Field(pattern=IMAGE.pattern)
    buildInputSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    validatedSourceRevision: str = Field(pattern=r"^[a-f0-9]{40}$")
    action: Literal["built", "reused"]
    runtimeVerified: Literal[True]


class Overrides(StrictModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    unitParameters: dict[Identifier, dict[str, Any]] = Field(default_factory=dict)
    subjectIds: list[Identifier] | None = Field(default=None, min_length=1)
    unitIds: list[Identifier] | None = Field(default=None, min_length=1)
    objective: dict[str, Any] = Field(default_factory=dict)
    steering: dict[str, Any] = Field(default_factory=dict)
    unitObjectives: dict[Identifier, dict[str, Any]] = Field(default_factory=dict)
    unitSteering: dict[Identifier, dict[str, Any]] = Field(default_factory=dict)
    unitConsumerBindings: dict[Identifier, dict[str, Any]] = Field(default_factory=dict)
    unitStepSettings: dict[Identifier, dict[Identifier, dict[str, Any]]] = Field(default_factory=dict)


class RunPlan(StrictModel):
    stableId: Identifier
    revision: Identifier
    overrides: Overrides = Field(default_factory=Overrides)


class RunInput(RunPlan):
    requestId: str
    retryOf: str | None = None


class PreflightChecks(StrictModel):
    definition: Literal["passed"]
    requests: Literal["passed"]
    coreArtifact: Literal["registered"]
    workerLiveness: Literal["unverified"]
    providerAuthentication: Literal["unverified"]
    modelReadiness: Literal["unverified"]


class QueueState(StrictModel):
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    cleanup: int = Field(ge=0)
    reconciliation: int = Field(ge=0)


class PreflightReceipt(StrictModel):
    schemaVersion: Literal["bench-preflight/v1"]
    valid: Literal[True]
    stableId: Identifier
    revision: Identifier
    attemptCount: int = Field(ge=1, le=512)
    coreVersion: CoreVersion
    image: str = Field(pattern=IMAGE.pattern)
    checks: PreflightChecks
    queue: QueueState
    executionReadiness: Literal["unverified"]


def _definition_fields(definition):
    return definition.model_dump()


def definition_payload(definition: Definition) -> dict:
    value = _definition_fields(definition)
    # Preserve the identity of v1 publications that predate per-unit bindings.
    for unit in value["units"]:
        if not unit["consumerBinding"]:
            del unit["consumerBinding"]
    return value


def effective_settings(definition: Definition, overrides: Overrides) -> dict:
    known_units = {u.id for u in definition.units}
    known_subjects = {s.id for s in definition.subjects}
    selected_units = set(overrides.unitIds or known_units)
    selected_subjects = set(overrides.subjectIds or known_subjects)
    if (not selected_units <= known_units or not selected_subjects <= known_subjects
            or not (set(overrides.unitParameters) | set(overrides.unitObjectives) | set(overrides.unitSteering)
                    | set(overrides.unitConsumerBindings) | set(overrides.unitStepSettings)) <= selected_units):
        raise BenchError("unknown_selection")
    if definition.schemaVersion == "bench-experiment/v1" and overrides.unitStepSettings:
        raise BenchError("versioned_experiment_required")
    result = _definition_fields(definition)
    result["subjects"] = [s for s in result["subjects"] if s["id"] in selected_subjects]
    result["units"] = [u for u in result["units"] if u["id"] in selected_units]
    validator = Draft202012Validator(definition.parameterSchema)
    for unit in result["units"]:
        binding = unit["consumerBinding"] | overrides.unitConsumerBindings.get(unit["id"], {})
        if unit["strategy"].startswith("consumer.") or unit["strategy"] == "prompt.check.v1":
            unit["consumerBinding"] = (definition.consumerBinding or {}) | binding
            if not unit["consumerBinding"]:
                unit["consumerBinding"] = None
        else:
            if binding:
                raise BenchError("consumer_binding_requires_consumer_strategy")
            unit["consumerBinding"] = None
        parameters = (definition.baseParameters | unit["parameters"] | overrides.parameters
                      | overrides.unitParameters.get(unit["id"], {}))
        try:
            validator.validate(parameters)
        except ValidationError:
            raise BenchError("invalid_override_parameters") from None
        unit["parameters"] = parameters
        unit["objective"] = (definition.objective | unit["objective"] | overrides.objective
                             | overrides.unitObjectives.get(unit["id"], {}))
        unit["steering"] = (definition.baseSteering | unit["steering"] | overrides.steering
                            | overrides.unitSteering.get(unit["id"], {}))
        if definition.schemaVersion == "bench-experiment/v2":
            step_overrides = overrides.unitStepSettings.get(unit["id"], {})
            steps = definition.baseStepSettings | unit["stepSettings"] | step_overrides
            unit["stepSettings"] = {
                key: definition.baseStepSettings.get(key, {}) | unit["stepSettings"].get(key, {})
                     | step_overrides.get(key, {}) for key in steps}
            unit["assertions"] = list(definition.harnessAssertions)
    result["overrides"] = overrides.model_dump()
    if not overrides.unitStepSettings:
        result["overrides"].pop("unitStepSettings")
    canonical(result)
    return result


def configuration_summary(effective: dict) -> dict:
    """Project immutable run configuration without prompts or evaluator targets."""
    units = []
    for unit in effective["units"]:
        binding = None
        if unit["strategy"].startswith("consumer.") or unit["strategy"] == "prompt.check.v1":
            source = (effective.get("consumerBinding") or {}) | (unit.get("consumerBinding") or {})
            binding = {key: source.get(key) for key in ("binding_id", "provider")}
        units.append({"id": unit["id"], "strategy": unit["strategy"], "consumerBinding": binding})
    summary = {
        "enhancerVersion": effective["enhancerVersion"],
        "caseCount": len(effective["subjects"]),
        "subjectIds": [subject["id"] for subject in effective["subjects"]],
        "units": units,
        "evaluatorProfile": {"evaluators": [
            {key: evaluator.get(key) for key in ("evaluator_id", "kind", "binding_id")}
            for evaluator in effective["evaluatorProfile"].get("evaluators", [])
        ]},
    }
    if effective.get("workflow"):
        summary["workflow"] = effective["workflow"]
        summary["coreBuild"] = effective["coreBuild"]
        for unit, source in zip(summary["units"], effective["units"]):
            unit["stepBindings"] = {key: value.get("binding") for key, value in source.get("stepSettings", {}).items()
                                    if value.get("binding")}
    return summary
