"""Provider-neutral contracts for objective verification evidence."""

from .contracts import (
    EphemeralVerificationCandidate,
    VerificationAbstentionReason,
    VerificationCapability,
    VerificationCapabilityState,
    VerificationClassification,
    VerificationClassificationDecision,
    VerificationClassifier,
    VerificationExecutionState,
    VerificationKind,
    VerificationOutcome,
)
from .observed_check_completion import (
    OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION,
    OBSERVED_CHECK_CLASSIFIER_VERSION,
    OBSERVED_CHECK_NORMALIZER_VERSION,
    OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION,
    EphemeralObservedCheckCompletion,
    ObservedCheckOutcome,
    interpret_observed_check_completion,
)

__all__ = [
    "EphemeralVerificationCandidate",
    "VerificationAbstentionReason",
    "VerificationCapability",
    "VerificationCapabilityState",
    "VerificationClassification",
    "VerificationClassificationDecision",
    "VerificationClassifier",
    "VerificationExecutionState",
    "VerificationKind",
    "VerificationOutcome",
    "OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION",
    "OBSERVED_CHECK_CLASSIFIER_VERSION",
    "OBSERVED_CHECK_NORMALIZER_VERSION",
    "OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION",
    "EphemeralObservedCheckCompletion",
    "ObservedCheckOutcome",
    "interpret_observed_check_completion",
]
