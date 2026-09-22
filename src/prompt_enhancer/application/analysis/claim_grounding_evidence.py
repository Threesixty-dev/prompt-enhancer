"""Content-free foundation for a native-reviewed assistant-claim census.

This module deliberately stops before persistence, HTTP, native confirmation,
or metric projection.  It establishes only the bounded, source-bound shapes a
later owned review flow must use.  In particular, assistant prose is available
only in :class:`EphemeralClaimReviewCandidate`; no durable contract contains a
claim excerpt or a digest derived from one.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol

from pydantic import Field, SecretStr, field_validator, model_validator

from ...domain import PSEUDONYM_PATTERN, SAFE_VERSION_PATTERN, StrictModel
from .requirement_plan_evidence import (
    MAX_REQUIREMENT_PLAN_CLAUSES_PER_MESSAGE,
    REQUIREMENT_PLAN_CLAUSE_ALGORITHM,
    reviewable_message_clauses,
)
from .text_contracts import P1TextAnalysisInput, TextMessageKind, TextRole


CLAIM_GROUNDING_CENSUS_SCHEMA_VERSION = "claim-grounding-census-v1"
CLAIM_GROUNDING_CENSUS_POLICY_VERSION = "native-reviewed-agent-claim-census-v1"
CLAIM_GROUNDING_CENSUS_ISSUER_VERSION = "reviewed-agent-response-census-v1"
MAX_CLAIM_GROUNDING_CANDIDATES = 100 * MAX_REQUIREMENT_PLAN_CLAUSES_PER_MESSAGE


def _id(value: str) -> str:
    if PSEUDONYM_PATTERN.fullmatch(value) is None:
        raise ValueError("claim-grounding identities must be HMAC pseudonyms")
    return value


def _version(value: str) -> str:
    if SAFE_VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("claim-grounding versions must use safe identifier characters")
    return value


class ClaimGroundingIdFactory(Protocol):
    def fingerprint(self, namespace: str, values: tuple[str, ...]) -> str: ...


class ClaimCensusClassification(StrEnum):
    MATERIAL_CLAIM = "material_claim"
    EXCLUDED = "excluded"


class ClaimCensusExclusionReason(StrEnum):
    NOT_A_COMPLETION_OR_VERIFICATION_CLAIM = "not_a_completion_or_verification_claim"
    DUPLICATE_OR_SUPERSEDED_CLAIM = "duplicate_or_superseded_claim"
    NON_ASSERTIVE_STATUS_OR_QUALIFICATION = "non_assertive_status_or_qualification"


class ClaimCensusCandidateManifestEntry(StrictModel):
    """Content-free identity and coordinate of one reviewable response clause."""

    candidate_id: str
    message_id: str
    message_sequence: int = Field(ge=0)
    clause_index: int = Field(ge=0, lt=MAX_REQUIREMENT_PLAN_CLAUSES_PER_MESSAGE)

    _ids = field_validator("candidate_id", "message_id")(_id)


class ClaimCensusSourceManifest(StrictModel):
    """A structurally complete response-only review set; never contains prose.

    This DTO does not authenticate the origin of ``text_extraction_complete``.
    A later native source composition must bind it to a sealed current run
    before it can support an owned review or any metric authority.
    """

    session_id: str
    source_run_id: str
    source_window_fingerprint: str
    source_schema_version: str
    text_adapter_version: str
    clause_algorithm: Literal[REQUIREMENT_PLAN_CLAUSE_ALGORITHM] = (
        REQUIREMENT_PLAN_CLAUSE_ALGORITHM
    )
    text_extraction_complete: Literal[True] = True
    candidates: tuple[ClaimCensusCandidateManifestEntry, ...] = Field(
        max_length=MAX_CLAIM_GROUNDING_CANDIDATES
    )
    candidate_count: int = Field(ge=0, le=MAX_CLAIM_GROUNDING_CANDIDATES)
    manifest_fingerprint: str
    schema_version: Literal[CLAIM_GROUNDING_CENSUS_SCHEMA_VERSION] = (
        CLAIM_GROUNDING_CENSUS_SCHEMA_VERSION
    )
    policy_version: Literal[CLAIM_GROUNDING_CENSUS_POLICY_VERSION] = (
        CLAIM_GROUNDING_CENSUS_POLICY_VERSION
    )
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False

    _ids = field_validator(
        "session_id", "source_run_id", "source_window_fingerprint", "manifest_fingerprint"
    )(_id)
    _versions = field_validator("source_schema_version", "text_adapter_version")(_version)

    @model_validator(mode="after")
    def exact_candidate_set(self) -> "ClaimCensusSourceManifest":
        order = tuple((item.message_sequence, item.clause_index) for item in self.candidates)
        candidate_ids = tuple(item.candidate_id for item in self.candidates)
        coordinates = tuple((item.message_id, item.clause_index) for item in self.candidates)
        by_message: dict[str, list[int]] = {}
        sequences: dict[str, int] = {}
        messages_by_sequence: dict[int, str] = {}
        for item in self.candidates:
            if item.message_id in sequences and sequences[item.message_id] != item.message_sequence:
                raise ValueError("claim census message identity has inconsistent sequence")
            if (
                item.message_sequence in messages_by_sequence
                and messages_by_sequence[item.message_sequence] != item.message_id
            ):
                raise ValueError("claim census message sequence has inconsistent identity")
            sequences[item.message_id] = item.message_sequence
            messages_by_sequence[item.message_sequence] = item.message_id
            by_message.setdefault(item.message_id, []).append(item.clause_index)
        if (
            order != tuple(sorted(order))
            or len(set(candidate_ids)) != len(candidate_ids)
            or len(set(coordinates)) != len(coordinates)
            or any(tuple(indexes) != tuple(range(len(indexes))) for indexes in by_message.values())
        ):
            raise ValueError("claim census candidates must be unique and ordered")
        if self.candidate_count != len(self.candidates):
            raise ValueError("claim census candidate count is invalid")
        return self


class ClaimCensusClassificationEntry(StrictModel):
    candidate_id: str
    classification: ClaimCensusClassification
    exclusion_reason: ClaimCensusExclusionReason | None = None

    _candidate = field_validator("candidate_id")(_id)

    @model_validator(mode="after")
    def closed_classification(self) -> "ClaimCensusClassificationEntry":
        if (self.classification is ClaimCensusClassification.EXCLUDED) != (
            self.exclusion_reason is not None
        ):
            raise ValueError("claim census exclusions require exactly one reason")
        return self


class ReviewedClaimCensus(StrictModel):
    """Content-free proposal input, not native-confirmed or metric authority."""

    manifest_fingerprint: str
    session_id: str
    source_run_id: str
    source_window_fingerprint: str
    classifications: tuple[ClaimCensusClassificationEntry, ...] = Field(
        max_length=MAX_CLAIM_GROUNDING_CANDIDATES
    )
    complete_candidate_classification_acknowledged: Literal[True]
    census_fingerprint: str
    issuer_version: Literal[CLAIM_GROUNDING_CENSUS_ISSUER_VERSION] = (
        CLAIM_GROUNDING_CENSUS_ISSUER_VERSION
    )
    schema_version: Literal[CLAIM_GROUNDING_CENSUS_SCHEMA_VERSION] = (
        CLAIM_GROUNDING_CENSUS_SCHEMA_VERSION
    )
    policy_version: Literal[CLAIM_GROUNDING_CENSUS_POLICY_VERSION] = (
        CLAIM_GROUNDING_CENSUS_POLICY_VERSION
    )
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False

    _ids = field_validator(
        "manifest_fingerprint", "session_id", "source_run_id", "source_window_fingerprint", "census_fingerprint"
    )(_id)

    @model_validator(mode="after")
    def ordered_unique_classifications(self) -> "ReviewedClaimCensus":
        ids = tuple(item.candidate_id for item in self.classifications)
        if ids != tuple(sorted(ids)) or len(set(ids)) != len(ids):
            raise ValueError("claim census classifications must be unique and ordered")
        return self


class EphemeralClaimReviewCandidate(StrictModel):
    """Review-only prose. ``text`` is excluded from normal serialization."""

    candidate_id: str
    message_id: str
    message_sequence: int = Field(ge=0)
    clause_index: int = Field(ge=0, lt=MAX_REQUIREMENT_PLAN_CLAUSES_PER_MESSAGE)
    text: SecretStr = Field(repr=False, exclude=True, min_length=1)

    _ids = field_validator("candidate_id", "message_id")(_id)


def _manifest_fingerprint(
    ids: ClaimGroundingIdFactory, *, session_id: str, source_run_id: str,
    source_window_fingerprint: str, source_schema_version: str,
    text_adapter_version: str, clause_algorithm: str,
    schema_version: str, policy_version: str,
    candidates: tuple[ClaimCensusCandidateManifestEntry, ...],
) -> str:
    return ids.fingerprint(
        "claim-grounding-census-manifest-v1",
        (session_id, source_run_id, source_window_fingerprint, source_schema_version,
         text_adapter_version, clause_algorithm, schema_version, policy_version,
         *(value for item in candidates for value in (
             item.candidate_id, item.message_id, str(item.message_sequence), str(item.clause_index)
         ))),
    )


def _census_fingerprint(
    identifiers: ClaimGroundingIdFactory, census: ReviewedClaimCensus,
) -> str:
    return identifiers.fingerprint(
        "claim-grounding-reviewed-census-v1",
        (
            census.manifest_fingerprint, census.session_id, census.source_run_id,
            census.source_window_fingerprint, census.issuer_version,
            census.schema_version, census.policy_version,
            *(f"{item.candidate_id}:{item.classification.value}:{item.exclusion_reason or '-'}" for item in census.classifications),
        ),
    )


def validate_claim_census_source_manifest(
    manifest: ClaimCensusSourceManifest, *, identifiers: ClaimGroundingIdFactory,
) -> None:
    """Verify the manifest's keyed identity before any later composition."""
    # ``model_copy`` intentionally skips Pydantic validation. Reconstruct the
    # DTO here so a caller cannot bypass structural invariants before the keyed
    # identity is checked.
    manifest = ClaimCensusSourceManifest.model_validate(manifest.model_dump())
    expected = _manifest_fingerprint(
        identifiers, session_id=manifest.session_id, source_run_id=manifest.source_run_id,
        source_window_fingerprint=manifest.source_window_fingerprint,
        source_schema_version=manifest.source_schema_version,
        text_adapter_version=manifest.text_adapter_version,
        clause_algorithm=manifest.clause_algorithm, schema_version=manifest.schema_version,
        policy_version=manifest.policy_version, candidates=manifest.candidates,
    )
    if expected != manifest.manifest_fingerprint:
        raise ValueError("claim census source manifest fingerprint is invalid")


def derive_claim_census_source_manifest(
    context: P1TextAnalysisInput, *, source_run_id: str, identifiers: ClaimGroundingIdFactory,
) -> tuple[ClaimCensusSourceManifest, tuple[EphemeralClaimReviewCandidate, ...]]:
    """Derive a structurally complete agent-RESPONSE review surface.

    A false completeness declaration is rejected rather than interpreted as an
    empty census.  Clause splitting is imported from the reviewed requirement
    plan algorithm; it labels no clause as a claim.  This accepts an ephemeral
    context only to construct a review DTO; it neither authenticates that
    context nor issues an authoritative census.
    """
    if not context.text_extraction_complete:
        raise ValueError("claim census source must have complete text extraction")
    candidates: list[ClaimCensusCandidateManifestEntry] = []
    ephemeral: list[EphemeralClaimReviewCandidate] = []
    for message in context.messages:
        if message.role is not TextRole.AGENT or message.kind is not TextMessageKind.RESPONSE:
            continue
        for clause_index, text in enumerate(reviewable_message_clauses(message.text.get_secret_value())):
            candidate_id = identifiers.fingerprint(
                "claim-grounding-census-candidate-v1",
                (context.session_id, context.analysis_window_fingerprint, message.message_id, str(clause_index)),
            )
            entry = ClaimCensusCandidateManifestEntry(
                candidate_id=candidate_id, message_id=message.message_id,
                message_sequence=message.sequence, clause_index=clause_index,
            )
            candidates.append(entry)
            ephemeral.append(EphemeralClaimReviewCandidate(**entry.model_dump(), text=SecretStr(text)))
    if len(candidates) > MAX_CLAIM_GROUNDING_CANDIDATES:
        raise ValueError("claim census source exceeds the bounded candidate count")
    ordered = tuple(sorted(candidates, key=lambda item: (item.message_sequence, item.clause_index, item.candidate_id)))
    manifest = ClaimCensusSourceManifest(
        session_id=context.session_id, source_run_id=source_run_id,
        source_window_fingerprint=context.analysis_window_fingerprint,
        source_schema_version=context.source_schema_version,
        text_adapter_version=context.adapter_version, candidates=ordered,
        candidate_count=len(ordered),
        manifest_fingerprint=_manifest_fingerprint(
            identifiers, session_id=context.session_id, source_run_id=source_run_id,
            source_window_fingerprint=context.analysis_window_fingerprint,
            source_schema_version=context.source_schema_version,
            text_adapter_version=context.adapter_version,
            clause_algorithm=REQUIREMENT_PLAN_CLAUSE_ALGORITHM,
            schema_version=CLAIM_GROUNDING_CENSUS_SCHEMA_VERSION,
            policy_version=CLAIM_GROUNDING_CENSUS_POLICY_VERSION, candidates=ordered,
        ),
    )
    return manifest, tuple(ephemeral)


def build_reviewed_claim_census(
    manifest: ClaimCensusSourceManifest, *,
    classifications: tuple[ClaimCensusClassificationEntry, ...],
    identifiers: ClaimGroundingIdFactory,
) -> ReviewedClaimCensus:
    """Construct a keyed, still-untrusted proposal for an exact manifest."""
    validate_claim_census_source_manifest(manifest, identifiers=identifiers)
    normalized = tuple(sorted(classifications, key=lambda item: item.candidate_id))
    provisional = ReviewedClaimCensus(
        manifest_fingerprint=manifest.manifest_fingerprint, session_id=manifest.session_id,
        source_run_id=manifest.source_run_id,
        source_window_fingerprint=manifest.source_window_fingerprint,
        classifications=normalized, complete_candidate_classification_acknowledged=True,
        census_fingerprint="0" * 64,
    )
    candidate_ids = {item.candidate_id for item in manifest.candidates}
    if {item.candidate_id for item in provisional.classifications} != candidate_ids:
        raise ValueError("claim census must classify every exact source candidate")
    return provisional.model_copy(update={"census_fingerprint": _census_fingerprint(identifiers, provisional)})


def validate_reviewed_claim_census(
    census: ReviewedClaimCensus, manifest: ClaimCensusSourceManifest, *,
    identifiers: ClaimGroundingIdFactory,
) -> None:
    """Require an exact classification partition for this one sealed source."""
    validate_claim_census_source_manifest(manifest, identifiers=identifiers)
    if (
        census.manifest_fingerprint != manifest.manifest_fingerprint
        or census.session_id != manifest.session_id
        or census.source_run_id != manifest.source_run_id
        or census.source_window_fingerprint != manifest.source_window_fingerprint
    ):
        raise ValueError("claim census belongs to another sealed source")
    if {item.candidate_id for item in census.classifications} != {
        item.candidate_id for item in manifest.candidates
    }:
        raise ValueError("claim census must classify every exact source candidate")
    if _census_fingerprint(identifiers, census) != census.census_fingerprint:
        raise ValueError("claim census fingerprint is invalid")


__all__ = (
    "CLAIM_GROUNDING_CENSUS_ISSUER_VERSION", "CLAIM_GROUNDING_CENSUS_POLICY_VERSION",
    "CLAIM_GROUNDING_CENSUS_SCHEMA_VERSION", "ClaimCensusClassification",
    "ClaimCensusClassificationEntry", "ClaimCensusExclusionReason",
    "ClaimCensusSourceManifest", "EphemeralClaimReviewCandidate",
    "MAX_CLAIM_GROUNDING_CANDIDATES", "ReviewedClaimCensus",
    "build_reviewed_claim_census", "derive_claim_census_source_manifest",
    "validate_claim_census_source_manifest",
    "validate_reviewed_claim_census",
)
