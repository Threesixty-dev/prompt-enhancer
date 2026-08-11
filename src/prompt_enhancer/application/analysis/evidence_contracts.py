"""Versioned, ephemeral contracts for structured coaching evidence.

These are ingress contracts, not persistence records. A provider adapter may
construct them only from a documented, compatibility-checked surface. Text is
secret-bearing and objective verification requires a provider or artifact
receipt; an assistant completion claim is not verification evidence.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from ...domain import PSEUDONYM_PATTERN, SAFE_VERSION_PATTERN, Provider, StrictModel
from ..providers import CapabilityKey, DecoderDescriptor
from .text_contracts import TextLanguage


TYPED_EVIDENCE_SCHEMA_VERSION = 1
MAX_TYPED_EVIDENCE_RECORDS = 5_000


def _pseudonym(value: str) -> str:
    if PSEUDONYM_PATTERN.fullmatch(value) is None:
        raise ValueError("evidence identifiers must be HMAC pseudonyms")
    return value


def _safe_version(value: str) -> str:
    if SAFE_VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("evidence provenance must use safe identifiers")
    return value


def _unique_pseudonyms(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(_pseudonym(value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError("evidence references cannot contain duplicates")
    return normalized


class TypedEvidenceKind(StrEnum):
    ACTION = "action"
    DECISION = "decision"
    FEEDBACK = "feedback"
    VERIFICATION = "verification"


class ActionFamily(StrEnum):
    TOOL = "tool"
    COMMAND = "command"
    FILE_CHANGE = "file_change"
    REVIEW = "review"
    OTHER_DOCUMENTED = "other_documented"


class ActionState(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class DecisionState(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


class RationaleState(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class VerificationMethod(StrEnum):
    TEST = "test"
    STATIC_CHECK = "static_check"
    BUILD = "build"
    ARTIFACT_INSPECTION = "artifact_inspection"
    HUMAN_ACCEPTANCE = "human_acceptance"
    OTHER_DOCUMENTED = "other_documented"


class VerificationOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    UNKNOWN = "unknown"


class _EvidenceBase(StrictModel):
    evidence_id: str
    sequence: int = Field(ge=0)
    source_reference_id: str

    _validate_evidence_id = field_validator("evidence_id")(_pseudonym)
    _validate_source_reference = field_validator("source_reference_id")(
        _pseudonym
    )


class ActionEvidence(_EvidenceBase):
    kind: Literal[TypedEvidenceKind.ACTION] = TypedEvidenceKind.ACTION
    family: ActionFamily
    state: ActionState
    requirement_reference_ids: tuple[str, ...] = ()

    _validate_requirements = field_validator("requirement_reference_ids")(
        _unique_pseudonyms
    )


class DecisionEvidence(_EvidenceBase):
    kind: Literal[TypedEvidenceKind.DECISION] = TypedEvidenceKind.DECISION
    state: DecisionState
    rationale_state: RationaleState
    rationale_reference_id: str | None = None
    requirement_reference_ids: tuple[str, ...] = ()

    _validate_rationale_reference = field_validator("rationale_reference_id")(
        lambda value: None if value is None else _pseudonym(value)
    )
    _validate_requirements = field_validator("requirement_reference_ids")(
        _unique_pseudonyms
    )

    @model_validator(mode="after")
    def rationale_reference_matches_state(self) -> DecisionEvidence:
        if (
            self.rationale_state is RationaleState.PRESENT
            and self.rationale_reference_id is None
        ):
            raise ValueError("present rationale requires a source reference")
        if (
            self.rationale_state is not RationaleState.PRESENT
            and self.rationale_reference_id is not None
        ):
            raise ValueError("non-present rationale cannot claim a source reference")
        return self


class FeedbackEvidence(_EvidenceBase):
    kind: Literal[TypedEvidenceKind.FEEDBACK] = TypedEvidenceKind.FEEDBACK
    language: TextLanguage
    text: SecretStr = Field(repr=False, min_length=1, max_length=32_000)
    supersedes_evidence_ids: tuple[str, ...] = ()

    _validate_superseded = field_validator("supersedes_evidence_ids")(
        _unique_pseudonyms
    )

    @field_validator("text")
    @classmethod
    def reject_nul(cls, value: SecretStr) -> SecretStr:
        if "\x00" in value.get_secret_value():
            raise ValueError("feedback evidence cannot contain NUL")
        return value


class VerificationEvidence(_EvidenceBase):
    kind: Literal[TypedEvidenceKind.VERIFICATION] = (
        TypedEvidenceKind.VERIFICATION
    )
    method: VerificationMethod
    outcome: VerificationOutcome
    objective: Literal[True] = True
    receipt_reference_ids: tuple[str, ...] = Field(min_length=1)
    requirement_reference_ids: tuple[str, ...] = ()

    _validate_receipts = field_validator("receipt_reference_ids")(
        _unique_pseudonyms
    )
    _validate_requirements = field_validator("requirement_reference_ids")(
        _unique_pseudonyms
    )


TypedEvidenceRecord = Annotated[
    ActionEvidence | DecisionEvidence | FeedbackEvidence | VerificationEvidence,
    Field(discriminator="kind"),
]


class TypedEvidenceProvenance(StrictModel):
    provider: Provider
    provider_version: str
    adapter_version: str
    decoder_key: str
    decoder_version: str
    source_schema_version: str
    evidence_schema_version: int = TYPED_EVIDENCE_SCHEMA_VERSION
    extraction_complete: bool = False

    _validate_versions = field_validator(
        "provider_version",
        "adapter_version",
        "decoder_key",
        "decoder_version",
        "source_schema_version",
    )(_safe_version)


class EphemeralTypedEvidenceProjection(StrictModel):
    """Bounded secret-bearing projection that must never be persisted."""

    provenance: TypedEvidenceProvenance
    declared_kinds: frozenset[TypedEvidenceKind]
    records: tuple[TypedEvidenceRecord, ...] = Field(
        repr=False,
        max_length=MAX_TYPED_EVIDENCE_RECORDS,
    )

    @model_validator(mode="after")
    def validate_projection(self) -> EphemeralTypedEvidenceProjection:
        identities = tuple(record.evidence_id for record in self.records)
        if len(set(identities)) != len(identities):
            raise ValueError("typed evidence records cannot share identifiers")
        sequences = tuple(record.sequence for record in self.records)
        if len(set(sequences)) != len(sequences):
            raise ValueError("typed evidence records cannot share a sequence")
        if sequences != tuple(sorted(sequences)):
            raise ValueError("typed evidence records must be chronological")
        observed = {record.kind for record in self.records}
        if not observed.issubset(self.declared_kinds):
            raise ValueError("observed evidence was not declared by the adapter")
        return self


_CAPABILITY_FOR_KIND = {
    TypedEvidenceKind.ACTION: CapabilityKey.TOOL_EVENTS,
    TypedEvidenceKind.DECISION: CapabilityKey.DECISION_EVENTS,
    TypedEvidenceKind.FEEDBACK: CapabilityKey.FEEDBACK_MESSAGES,
    TypedEvidenceKind.VERIFICATION: CapabilityKey.VERIFICATION_EVENTS,
}


def validate_projection_descriptor(
    projection: EphemeralTypedEvidenceProjection,
    descriptor: DecoderDescriptor,
) -> None:
    """Reject a projection not covered by the exact decoder identity."""

    provenance = projection.provenance
    if (
        descriptor.provider.key != provenance.provider.value
        or descriptor.adapter_version != provenance.adapter_version
        or descriptor.decoder_key != provenance.decoder_key
        or descriptor.decoder_version != provenance.decoder_version
        or descriptor.canonical_schema_version != provenance.source_schema_version
    ):
        raise ValueError("typed evidence provenance does not match the decoder")
    declared_capabilities = set(descriptor.capabilities)
    if any(
        _CAPABILITY_FOR_KIND[kind] not in declared_capabilities
        for kind in projection.declared_kinds
    ):
        raise ValueError("typed evidence kind was not declared by the decoder")


__all__ = [
    "ActionEvidence",
    "ActionFamily",
    "ActionState",
    "DecisionEvidence",
    "DecisionState",
    "EphemeralTypedEvidenceProjection",
    "FeedbackEvidence",
    "RationaleState",
    "TYPED_EVIDENCE_SCHEMA_VERSION",
    "TypedEvidenceKind",
    "TypedEvidenceProvenance",
    "TypedEvidenceRecord",
    "VerificationEvidence",
    "VerificationMethod",
    "VerificationOutcome",
    "validate_projection_descriptor",
]
