"""Interpret one documented provider command completion without executing it.

The provider command and output remain process-local.  This module consumes an
already-decoded terminal status and exit code, and returns only a content-free
receipt candidate.  It deliberately supports a very small outcome surface:
direct pytest invocations have documented exit semantics; package scripts,
wrappers, build tools, and generic successful tool calls do not.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ...domain import PSEUDONYM_PATTERN, Provider, SAFE_VERSION_PATTERN, StrictModel
from .contracts import (
    EphemeralVerificationCandidate,
    VerificationClassificationDecision,
    VerificationClassifier,
    VerificationExecutionState,
    VerificationKind,
)


OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION = "observed-check-completion-v1"
OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION = "pytest-exit-status-v1"
OBSERVED_CHECK_CLASSIFIER_VERSION = "local-command-rules-v1"
OBSERVED_CHECK_NORMALIZER_VERSION = "strict-shell-free-v2"
_TERMINAL_PROVIDER_STATUS = "completed"
_PYTEST_RULE_IDS = frozenset({"test.pytest", "test.py_test"})


class ObservedCheckOutcome(StrEnum):
    PASSED = "passed"
    CHECK_FAILED = "check_failed"


class EphemeralObservedCheckCompletion(StrictModel):
    """A content-free, process-local result from one exact provider receipt."""

    provider: Provider
    source_reference_id: str
    observed_sequence: int = Field(ge=0, le=4_000_000_000)
    check_kind: VerificationKind
    outcome: ObservedCheckOutcome
    provider_execution_status: Literal["completed"]
    exit_code: int = Field(strict=True, ge=-2_147_483_648, le=2_147_483_647)
    source_completion_schema_version: Literal[
        OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION
    ] = OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION
    outcome_interpreter_version: Literal[
        OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION
    ] = OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION
    classifier_version: Literal[OBSERVED_CHECK_CLASSIFIER_VERSION]
    normalizer_version: Literal[OBSERVED_CHECK_NORMALIZER_VERSION]
    rule_id: str
    local_only: Literal[True] = True
    content_persistence_allowed: Literal[False] = False

    @field_validator("source_reference_id")
    @classmethod
    def require_pseudonym(cls, value: str) -> str:
        if not PSEUDONYM_PATTERN.fullmatch(value):
            raise ValueError("observed check source identifier is invalid")
        return value

    @field_validator(
        "rule_id",
        "provider_execution_status",
    )
    @classmethod
    def require_safe_identifier(cls, value: str) -> str:
        if not SAFE_VERSION_PATTERN.fullmatch(value):
            raise ValueError("observed check provenance is invalid")
        return value

    @model_validator(mode="after")
    def require_exact_boundary(self) -> "EphemeralObservedCheckCompletion":
        if self.check_kind is not VerificationKind.TEST:
            raise ValueError("observed completion kind is unsupported")
        if self.rule_id not in _PYTEST_RULE_IDS:
            raise ValueError("observed completion rule is unsupported")
        if type(self.exit_code) is not int or self.exit_code not in {0, 1}:
            raise ValueError("observed completion exit code is unsupported")
        if (self.outcome is ObservedCheckOutcome.PASSED) != (self.exit_code == 0):
            raise ValueError("observed completion outcome disagrees with exit code")
        return self


def interpret_observed_check_completion(
    *,
    candidate: EphemeralVerificationCandidate,
    provider_execution_status: str,
    classifier: VerificationClassifier,
) -> EphemeralObservedCheckCompletion | None:
    """Return an eligible exact pytest receipt, otherwise abstain without a claim.

    A provider's success boolean is intentionally ignored.  The documented
    command-execution terminal status and pytest's explicit exit codes are the
    only admitted outcome authority in this initial integration.
    """

    exit_code = candidate.exit_code
    if (
        provider_execution_status != _TERMINAL_PROVIDER_STATUS
        or candidate.execution_state is not VerificationExecutionState.COMPLETED
        or type(candidate.observed_sequence) is not int
        or type(exit_code) is not int
        or exit_code not in {0, 1}
    ):
        return None
    classification = classifier.classify(candidate)
    if (
        classification.decision is not VerificationClassificationDecision.VERIFICATION
        or classification.kind is not VerificationKind.TEST
        or classification.rule_id not in _PYTEST_RULE_IDS
        or classification.classifier_version != OBSERVED_CHECK_CLASSIFIER_VERSION
        or classification.normalizer_version != OBSERVED_CHECK_NORMALIZER_VERSION
    ):
        return None
    return EphemeralObservedCheckCompletion(
        provider=candidate.provider,
        source_reference_id=candidate.source_item_id.get_secret_value(),
        observed_sequence=candidate.observed_sequence,
        check_kind=VerificationKind.TEST,
        outcome=(
            ObservedCheckOutcome.PASSED
            if exit_code == 0
            else ObservedCheckOutcome.CHECK_FAILED
        ),
        provider_execution_status=provider_execution_status,
        exit_code=exit_code,
        classifier_version=classification.classifier_version,
        normalizer_version=classification.normalizer_version,
        rule_id=classification.rule_id,
    )
