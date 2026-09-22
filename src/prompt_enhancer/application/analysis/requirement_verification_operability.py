"""Static composition contract for conditional requirement verification.

This is an operability descriptor, not a session receipt.  It records the
versioned local path which *can* publish verified-requirement coverage when an
exact current source, a complete native-reviewed denominator, and observed
checks all exist.  It does not claim that any session is ready or that a
provider-reported command outcome proves an arbitrary requirement by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..verification import (
    OBSERVED_CHECK_CLASSIFIER_VERSION,
    OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION,
    OBSERVED_CHECK_NORMALIZER_VERSION,
    OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION,
)
from .metric_projection_v2 import METRIC_PROJECTION_V2_VERSION_8
from .requirement_plan_evidence import (
    REQUIREMENT_PLAN_EVIDENCE_POLICY_VERSION,
    REQUIREMENT_PLAN_EVIDENCE_SCHEMA_VERSION,
)
from .requirement_verification_evidence import (
    REQUIREMENT_VERIFICATION_EVIDENCE_POLICY_VERSION,
    REQUIREMENT_VERIFICATION_EVIDENCE_SCHEMA_VERSION,
    REQUIREMENT_VERIFICATION_PROJECTION_VERSION,
)
from .requirement_verification_persistence import (
    OBSERVED_CHECK_COVERAGE_REVIEW_VERSION,
    OBSERVED_CHECK_PROVENANCE_SCHEMA_VERSION,
    REQUIREMENT_VERIFICATION_PERSISTENCE_SCHEMA_VERSION,
)
from .requirement_verification_review import (
    OBSERVED_CHECK_REVIEW_SCHEMA_VERSION,
    REQUIREMENT_VERIFICATION_REVIEW_POLICY_VERSION,
)


REVIEWED_REQUIREMENT_VERIFICATION_OPERABILITY_VERSION = (
    "reviewed-requirement-verification-operability-v1"
)


@dataclass(frozen=True, slots=True)
class ReviewedRequirementVerificationOperabilityDescriptor:
    """Closed, content-free description of the shipped conditional path."""

    descriptor_version: Literal[
        "reviewed-requirement-verification-operability-v1"
    ]
    provider: Literal["codex"]
    decoder_key: str
    decoder_version: str
    text_adapter_version: str
    text_schema_version: str
    source_schema_version: str
    completion_schema_version: str
    completion_classifier_version: str
    completion_normalizer_version: str
    completion_outcome_interpreter_version: str
    requirement_plan_schema_version: str
    requirement_plan_policy_version: str
    requirement_review_policy_version: str
    verification_schema_version: str
    verification_policy_version: str
    verification_persistence_schema_version: str
    observed_check_review_schema_version: str
    observed_check_coverage_review_version: str
    observed_check_provenance_schema_version: str
    verification_projection_version: str
    sealed_metric_projection_version: str
    requires_complete_source: Literal[True]
    requires_native_review: Literal[True]
    requires_full_criterion_coverage_acknowledgment: Literal[True]
    requires_fresh_sealed_source_binding: Literal[True]
    provider_reported_outcome_only: Literal[True]
    model_authority: Literal[False]


REVIEWED_REQUIREMENT_VERIFICATION_OPERABILITY = (
    ReviewedRequirementVerificationOperabilityDescriptor(
        descriptor_version=REVIEWED_REQUIREMENT_VERIFICATION_OPERABILITY_VERSION,
        provider="codex",
        # The adapter-owned values are deliberately repeated in this
        # application contract rather than imported from infrastructure.
        # ``test_metric_operability`` compares every value to the concrete
        # adapter/interpreter constants, keeping the dependency one-way.
        decoder_key="codex.app-server.text-window",
        decoder_version="6",
        text_adapter_version="0.8.0",
        text_schema_version="codex-thread-item-text-v9",
        source_schema_version="codex-app-server-v2",
        completion_schema_version=OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION,
        completion_classifier_version=OBSERVED_CHECK_CLASSIFIER_VERSION,
        completion_normalizer_version=OBSERVED_CHECK_NORMALIZER_VERSION,
        completion_outcome_interpreter_version=(
            OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION
        ),
        requirement_plan_schema_version=REQUIREMENT_PLAN_EVIDENCE_SCHEMA_VERSION,
        requirement_plan_policy_version=REQUIREMENT_PLAN_EVIDENCE_POLICY_VERSION,
        requirement_review_policy_version=REQUIREMENT_VERIFICATION_REVIEW_POLICY_VERSION,
        verification_schema_version=REQUIREMENT_VERIFICATION_EVIDENCE_SCHEMA_VERSION,
        verification_policy_version=REQUIREMENT_VERIFICATION_EVIDENCE_POLICY_VERSION,
        verification_persistence_schema_version=(
            REQUIREMENT_VERIFICATION_PERSISTENCE_SCHEMA_VERSION
        ),
        observed_check_review_schema_version=OBSERVED_CHECK_REVIEW_SCHEMA_VERSION,
        observed_check_coverage_review_version=OBSERVED_CHECK_COVERAGE_REVIEW_VERSION,
        observed_check_provenance_schema_version=(
            OBSERVED_CHECK_PROVENANCE_SCHEMA_VERSION
        ),
        verification_projection_version=REQUIREMENT_VERIFICATION_PROJECTION_VERSION,
        sealed_metric_projection_version=METRIC_PROJECTION_V2_VERSION_8,
        requires_complete_source=True,
        requires_native_review=True,
        requires_full_criterion_coverage_acknowledgment=True,
        requires_fresh_sealed_source_binding=True,
        provider_reported_outcome_only=True,
        model_authority=False,
    )
)


__all__ = (
    "REVIEWED_REQUIREMENT_VERIFICATION_OPERABILITY",
    "REVIEWED_REQUIREMENT_VERIFICATION_OPERABILITY_VERSION",
    "ReviewedRequirementVerificationOperabilityDescriptor",
)
