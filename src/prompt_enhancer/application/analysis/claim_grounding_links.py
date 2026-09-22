"""Content-free, non-authoritative coverage review for saved material claims."""
from __future__ import annotations

from enum import StrEnum
from typing import Literal
import json

from pydantic import Field, field_validator, model_validator

from ...domain import PSEUDONYM_PATTERN, SAFE_VERSION_PATTERN, StrictModel
from ..verification.observed_check_completion import EphemeralObservedCheckCompletion
from .claim_grounding_census import ClaimGroundingCensusRecord
from .claim_grounding_evidence import (
    ClaimCensusClassification, ClaimCensusSourceManifest, ClaimGroundingIdFactory,
    ReviewedClaimCensus,
    validate_claim_census_source_manifest, validate_reviewed_claim_census,
)

MAX_LINKED_OBSERVED_CHECKS = 128
MAX_TOTAL_LINK_REFERENCES = 12_800
CLAIM_LINK_OBSERVED_SET_SCHEMA_VERSION = "claim-grounding-observed-set-v1"
CLAIM_LINK_COVERAGE_SCHEMA_VERSION = "claim-grounding-link-coverage-v1"
CLAIM_LINK_POLICY_VERSION = "native-reviewed-claim-link-coverage-v1"


class ClaimLinkCoverageDecision(StrEnum):
    LINKED_OBSERVED_CHECKS = "linked_observed_checks"
    REVIEWED_NO_SUPPORT = "reviewed_no_support"
    UNRESOLVED = "unresolved"


class ClaimObservedCheckCoverage(StrictModel):
    """One native-review decision; references are not outcome authority."""
    candidate_id: str
    decision: ClaimLinkCoverageDecision
    observed_check_references: tuple[str, ...] = Field(max_length=MAX_LINKED_OBSERVED_CHECKS)
    coverage_review_acknowledged: Literal[True]
    native_authority_established: Literal[False] = False

    _id = field_validator("candidate_id")(
        lambda value: value if PSEUDONYM_PATTERN.fullmatch(value) else (_ for _ in ()).throw(ValueError("claim link identity is invalid"))
    )
    _references = field_validator("observed_check_references")(
        lambda values: tuple(value if PSEUDONYM_PATTERN.fullmatch(value) else (_ for _ in ()).throw(ValueError("observed check reference is invalid")) for value in values)
    )

    @model_validator(mode="after")
    def closed_partition(self) -> "ClaimObservedCheckCoverage":
        if len(set(self.observed_check_references)) != len(self.observed_check_references):
            raise ValueError("observed check references must be unique")
        if (self.decision is ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS) != bool(self.observed_check_references):
            raise ValueError("claim link coverage decision is incomplete")
        return self


class ClaimObservedCheckCoverageSet(StrictModel):
    session_id: str
    source_run_id: str
    source_window_fingerprint: str
    census_id: str
    census_fingerprint: str
    observed_set_fingerprint: str
    coverage_fingerprint: str
    coverage: tuple[ClaimObservedCheckCoverage, ...] = Field(max_length=12_800)
    observed_completions: tuple[EphemeralObservedCheckCompletion, ...] = Field(max_length=4_000)
    complete_material_claim_coverage_acknowledged: Literal[True]
    proposal_only: Literal[True] = True
    measured: Literal[False] = False
    metric_authority_established: Literal[False] = False
    content_persisted: Literal[False] = False
    schema_version: Literal[CLAIM_LINK_COVERAGE_SCHEMA_VERSION] = CLAIM_LINK_COVERAGE_SCHEMA_VERSION
    policy_version: Literal[CLAIM_LINK_POLICY_VERSION] = CLAIM_LINK_POLICY_VERSION
    _ids = field_validator("session_id", "source_run_id", "source_window_fingerprint", "census_id", "census_fingerprint", "observed_set_fingerprint", "coverage_fingerprint")(
        lambda value: value if PSEUDONYM_PATTERN.fullmatch(value) else (_ for _ in ()).throw(ValueError("claim link identity is invalid"))
    )


class SourceBoundObservedCheckSet(StrictModel):
    session_id: str
    source_run_id: str
    source_window_fingerprint: str
    source_schema_version: str
    completion_interpreter_version: Literal["pytest-exit-status-v1"]
    normalizer_version: Literal["strict-shell-free-v2"]
    completions: tuple[EphemeralObservedCheckCompletion, ...] = Field(max_length=4_000)
    observed_set_fingerprint: str
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False
    schema_version: Literal[CLAIM_LINK_OBSERVED_SET_SCHEMA_VERSION] = CLAIM_LINK_OBSERVED_SET_SCHEMA_VERSION
    policy_version: Literal[CLAIM_LINK_POLICY_VERSION] = CLAIM_LINK_POLICY_VERSION

    _ids = field_validator("session_id", "source_run_id", "source_window_fingerprint", "observed_set_fingerprint")(
        lambda value: value if PSEUDONYM_PATTERN.fullmatch(value) else (_ for _ in ()).throw(ValueError("observed set identity is invalid"))
    )
    _version = field_validator("source_schema_version")(
        lambda value: value if SAFE_VERSION_PATTERN.fullmatch(value) else (_ for _ in ()).throw(ValueError("observed set version is invalid"))
    )


def build_source_bound_observed_check_set(*, session_id: str, source_run_id: str,
                                          source_window_fingerprint: str,
                                          source_schema_version: str,
                                          completions: tuple[EphemeralObservedCheckCompletion, ...],
                                          identifiers: ClaimGroundingIdFactory) -> SourceBoundObservedCheckSet:
    reparsed = tuple(EphemeralObservedCheckCompletion.model_validate(item.model_dump()) for item in completions)
    ordered = tuple(sorted(reparsed, key=lambda item: item.source_reference_id))
    if len({item.source_reference_id for item in ordered}) != len(ordered):
        raise ValueError("observed completion references must be unique")
    for item in ordered: item.require_exact_boundary()
    canonical = tuple(json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) for item in ordered)
    fingerprint = identifiers.fingerprint("claim-grounding-observed-check-set-v1", (session_id, source_run_id, source_window_fingerprint, source_schema_version, CLAIM_LINK_OBSERVED_SET_SCHEMA_VERSION, CLAIM_LINK_POLICY_VERSION, *canonical))
    return SourceBoundObservedCheckSet(session_id=session_id, source_run_id=source_run_id, source_window_fingerprint=source_window_fingerprint, source_schema_version=source_schema_version, completion_interpreter_version="pytest-exit-status-v1", normalizer_version="strict-shell-free-v2", completions=ordered, observed_set_fingerprint=fingerprint)


def build_claim_observed_check_coverage(*, record: ClaimGroundingCensusRecord,
                                        coverage: tuple[ClaimObservedCheckCoverage, ...],
                                        observed_set: SourceBoundObservedCheckSet,
                                        identifiers: ClaimGroundingIdFactory) -> ClaimObservedCheckCoverageSet:
    """Validate exact material-claim coverage against server-normalized checks.

    This deliberately does not establish a metric, durable provenance, or a
    semantic requirement link.  A later native flow must separately attest
    claim coverage and issue any observed outcome through its own authority.
    """
    # Reparse all caller-supplied Pydantic objects: model_copy/model_construct
    # must not bypass the pure builder's bounded structural contracts.
    if len(coverage) > 12_800 or len(observed_set.completions) > 4_000:
        raise ValueError("claim link coverage is outside its bound")
    if PSEUDONYM_PATTERN.fullmatch(record.census_id) is None:
        raise ValueError("claim census identity is invalid")
    manifest = ClaimCensusSourceManifest.model_validate(record.manifest.model_dump())
    census = ReviewedClaimCensus.model_validate(record.census.model_dump())
    coverage = tuple(ClaimObservedCheckCoverage.model_validate(item.model_dump()) for item in coverage)
    observed_set = SourceBoundObservedCheckSet.model_validate(observed_set.model_dump())
    observed_completions = observed_set.completions
    validate_claim_census_source_manifest(manifest, identifiers=identifiers)
    validate_reviewed_claim_census(census, manifest, identifiers=identifiers)
    if (record.census.session_id != record.manifest.session_id
        or record.census.source_run_id != record.manifest.source_run_id
        or record.census.source_window_fingerprint != record.manifest.source_window_fingerprint):
        raise ValueError("claim census source binding is invalid")
    if (observed_set.session_id != census.session_id
        or observed_set.source_run_id != census.source_run_id
        or observed_set.source_window_fingerprint != census.source_window_fingerprint):
        raise ValueError("observed check set source binding is invalid")
    if observed_set.source_schema_version != manifest.source_schema_version:
        raise ValueError("observed check set schema binding is invalid")
    expected_set = build_source_bound_observed_check_set(session_id=observed_set.session_id, source_run_id=observed_set.source_run_id, source_window_fingerprint=observed_set.source_window_fingerprint, source_schema_version=observed_set.source_schema_version, completions=observed_completions, identifiers=identifiers)
    if expected_set.observed_set_fingerprint != observed_set.observed_set_fingerprint:
        raise ValueError("observed check set fingerprint is invalid")
    material = {item.candidate_id for item in census.classifications
                if item.classification is ClaimCensusClassification.MATERIAL_CLAIM}
    by_candidate = {item.candidate_id: item for item in coverage}
    if len(by_candidate) != len(coverage) or set(by_candidate) != material:
        raise ValueError("material claim coverage must be a complete exact partition")
    if sum(len(item.observed_check_references) for item in coverage) > MAX_TOTAL_LINK_REFERENCES:
        raise ValueError("total observed check references exceed their bound")
    completion_by_reference = {item.source_reference_id: item for item in observed_completions}
    if len(completion_by_reference) != len(observed_completions):
        raise ValueError("observed completion references must be unique")
    for completion in observed_completions:
        completion.require_exact_boundary()
    for item in coverage:
        if any(reference not in completion_by_reference for reference in item.observed_check_references):
            raise ValueError("claim link references an unavailable observed check")
    coverage_fingerprint = identifiers.fingerprint("claim-grounding-observed-check-coverage-v1", (
        record.census_id, census.census_fingerprint, observed_set.observed_set_fingerprint,
        CLAIM_LINK_COVERAGE_SCHEMA_VERSION, CLAIM_LINK_POLICY_VERSION, *(f"{item.candidate_id}:{item.decision.value}:{','.join(sorted(item.observed_check_references))}" for item in sorted(coverage, key=lambda item: item.candidate_id)),
    ))
    return ClaimObservedCheckCoverageSet(
        session_id=record.census.session_id, source_run_id=record.census.source_run_id,
        source_window_fingerprint=record.census.source_window_fingerprint,
        census_id=record.census_id, census_fingerprint=record.census.census_fingerprint,
        observed_set_fingerprint=observed_set.observed_set_fingerprint,
        coverage_fingerprint=coverage_fingerprint,
        coverage=tuple(sorted(coverage, key=lambda item: item.candidate_id)),
        observed_completions=tuple(sorted(observed_completions, key=lambda item: item.source_reference_id)),
        complete_material_claim_coverage_acknowledged=True,
    )
