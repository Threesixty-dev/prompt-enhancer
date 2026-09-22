"""Current, content-free source composition for native claim-link coverage."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from .claim_grounding_census import ClaimGroundingCensusNotFoundError, DurableClaimGroundingCensusService
from .claim_grounding_links import SourceBoundObservedCheckSet, build_source_bound_observed_check_set
from .claim_grounding_evidence import (
    ClaimCensusClassification, ClaimCensusSourceManifest, ClaimGroundingIdFactory,
    ReviewedClaimCensus, validate_claim_census_source_manifest,
    validate_reviewed_claim_census,
)
from .metric_publication_v2 import metric_publication_v2_fingerprint
from ..verification.observed_check_completion import EphemeralObservedCheckCompletion
from ...domain import PSEUDONYM_PATTERN


class ClaimGroundingLinkSourceConflictError(RuntimeError): pass
class ClaimGroundingLinkSourceUnavailableError(RuntimeError): pass


class _LatestRuns(Protocol):
    def get_latest(self, session_id: str): ...  # type: ignore[no-untyped-def]


class _ObservedContexts(Protocol):
    def active_observed_check_candidates(self, *, session_id: str, source_run_id: str, source_window_fingerprint: str): ...  # type: ignore[no-untyped-def]


@dataclass(frozen=True, slots=True)
class CurrentClaimGroundingLinkSource:
    census_id: str
    session_id: str
    source_run_id: str
    source_window_fingerprint: str
    census_fingerprint: str
    observed_set: SourceBoundObservedCheckSet
    proposal_only: Literal[True] = field(default=True, init=False)
    measured: Literal[False] = field(default=False, init=False)
    metric_authority_established: Literal[False] = field(default=False, init=False)
    content_persisted: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class ClaimGroundingLinkMaterialCandidate:
    """One saved material-claim coordinate, deliberately without its clause text."""

    candidate_id: str
    message_id: str
    message_sequence: int
    clause_index: int


@dataclass(frozen=True, slots=True)
class ClaimGroundingLinkObservedCheckMetadata:
    """Normalized observed completion provenance, deliberately without tool content."""

    source_reference_id: str
    observed_sequence: int
    provider: str
    check_kind: str
    outcome: str
    provider_execution_status: str
    exit_code: int
    source_completion_schema_version: str
    outcome_interpreter_version: str
    classifier_version: str
    normalizer_version: str
    rule_id: str


@dataclass(frozen=True, slots=True)
class ClaimGroundingLinkCandidateManifest:
    """Content-free current selection surface; not an outcome or metric authority."""

    session_id: str
    census_id: str
    source_run_id: str
    source_window_fingerprint: str
    census_fingerprint: str
    manifest_fingerprint: str
    observed_set_fingerprint: str
    source_schema_version: str
    text_adapter_version: str
    observed_set_schema_version: str
    observed_set_policy_version: str
    material_candidates: tuple[ClaimGroundingLinkMaterialCandidate, ...]
    observed_checks: tuple[ClaimGroundingLinkObservedCheckMetadata, ...]
    proposal_only: Literal[True] = field(default=True, init=False)
    measured: Literal[False] = field(default=False, init=False)
    metric_authority_established: Literal[False] = field(default=False, init=False)
    content_persisted: Literal[False] = field(default=False, init=False)


class CurrentClaimGroundingLinkSourceResolver:
    """Two-read fence over a saved census and retained content-free checks."""
    def __init__(self, censuses: DurableClaimGroundingCensusService, runs: _LatestRuns,
                 contexts: _ObservedContexts, identifiers: ClaimGroundingIdFactory) -> None:
        self._censuses, self._runs, self._contexts, self._ids = censuses, runs, contexts, identifiers

    def current_source(self, *, session_id: str, census_id: str) -> CurrentClaimGroundingLinkSource:
        if (PSEUDONYM_PATTERN.fullmatch(session_id) is None
            or PSEUDONYM_PATTERN.fullmatch(census_id) is None):
            raise ClaimGroundingLinkSourceUnavailableError("saved claim census is unavailable")
        try:
            record = self._censuses.get(census_id)
        except ClaimGroundingCensusNotFoundError as error:
            raise ClaimGroundingLinkSourceUnavailableError("saved claim census is unavailable") from error
        if record.census.session_id != session_id:
            raise ClaimGroundingLinkSourceUnavailableError("saved claim census is unavailable")
        first = self._runs.get_latest(session_id)
        if not self._matches(record, first):
            raise ClaimGroundingLinkSourceConflictError("saved claim census source changed")
        try:
            raw = self._contexts.active_observed_check_candidates(
                session_id=session_id, source_run_id=record.census.source_run_id,
                source_window_fingerprint=record.census.source_window_fingerprint,
            )
            if len(raw) > 4_000:
                raise ValueError("observed check candidate surface exceeds its bound")
            completions = tuple(EphemeralObservedCheckCompletion.model_validate(item.model_dump()) for item in raw)
            if any(item.provider != first.provider for item in completions):
                raise ValueError("observed check provider binding changed")
            observed = build_source_bound_observed_check_set(
                session_id=session_id, source_run_id=record.census.source_run_id,
                source_window_fingerprint=record.census.source_window_fingerprint,
                source_schema_version=record.manifest.source_schema_version,
                completions=completions, identifiers=self._ids,
            )
        except Exception as error:
            raise ClaimGroundingLinkSourceUnavailableError("current observed checks are unavailable") from error
        second = self._runs.get_latest(session_id)
        if not self._matches(record, second):
            raise ClaimGroundingLinkSourceConflictError("saved claim census source changed")
        return CurrentClaimGroundingLinkSource(census_id=record.census_id, session_id=session_id,
            source_run_id=record.census.source_run_id,
            source_window_fingerprint=record.census.source_window_fingerprint,
            census_fingerprint=record.census.census_fingerprint, observed_set=observed)

    def material_descriptor(self, *, session_id: str, census_id: str, candidate_id: str):
        """Return only the content-free saved binding for one material claim."""
        source = self.current_source(session_id=session_id, census_id=census_id)
        record = self._censuses.get(census_id)
        item = next((value for value in record.census.classifications if value.candidate_id == candidate_id), None)
        if item is None or item.classification.value != "material_claim":
            raise ClaimGroundingLinkSourceConflictError("claim candidate is not material")
        return source, record.manifest.manifest_fingerprint

    def candidate_manifest(self, *, session_id: str, census_id: str) -> ClaimGroundingLinkCandidateManifest:
        """Return the exact current material coordinates and normalized check metadata.

        This is intentionally a selection surface only: no clause, invocation, or
        effect text is loaded or returned.
        """
        before = self.current_source(session_id=session_id, census_id=census_id)
        try:
            record = self._censuses.get(census_id)
            manifest = ClaimCensusSourceManifest.model_validate(record.manifest.model_dump())
            census = ReviewedClaimCensus.model_validate(record.census.model_dump())
            validate_claim_census_source_manifest(manifest, identifiers=self._ids)
            validate_reviewed_claim_census(census, manifest, identifiers=self._ids)
        except ClaimGroundingCensusNotFoundError as error:
            raise ClaimGroundingLinkSourceUnavailableError("saved claim census is unavailable") from error
        except Exception as error:
            raise ClaimGroundingLinkSourceUnavailableError("saved claim census is unavailable") from error
        if not self._record_matches_source(record, before, manifest, census):
            raise ClaimGroundingLinkSourceConflictError("saved claim census source changed")
        after = self.current_source(session_id=session_id, census_id=census_id)
        if not self._same_current_source(before, after):
            raise ClaimGroundingLinkSourceConflictError("saved claim census source changed")
        classification = {item.candidate_id: item.classification for item in census.classifications}
        material = tuple(
            ClaimGroundingLinkMaterialCandidate(
                candidate_id=item.candidate_id, message_id=item.message_id,
                message_sequence=item.message_sequence, clause_index=item.clause_index,
            )
            for item in manifest.candidates
            if classification[item.candidate_id] is ClaimCensusClassification.MATERIAL_CLAIM
        )
        if len(material) > 12_800 or len(after.observed_set.completions) > 4_000:
            raise ClaimGroundingLinkSourceUnavailableError("claim link selection is unavailable")
        observed = tuple(
            ClaimGroundingLinkObservedCheckMetadata(
                source_reference_id=item.source_reference_id,
                observed_sequence=item.observed_sequence, provider=item.provider.value,
                check_kind=item.check_kind.value, outcome=item.outcome.value,
                provider_execution_status=item.provider_execution_status,
                exit_code=item.exit_code,
                source_completion_schema_version=item.source_completion_schema_version,
                outcome_interpreter_version=item.outcome_interpreter_version,
                classifier_version=item.classifier_version,
                normalizer_version=item.normalizer_version, rule_id=item.rule_id,
            )
            for item in after.observed_set.completions
        )
        return ClaimGroundingLinkCandidateManifest(
            session_id=after.session_id, census_id=after.census_id,
            source_run_id=after.source_run_id,
            source_window_fingerprint=after.source_window_fingerprint,
            census_fingerprint=after.census_fingerprint,
            manifest_fingerprint=manifest.manifest_fingerprint,
            observed_set_fingerprint=after.observed_set.observed_set_fingerprint,
            source_schema_version=manifest.source_schema_version,
            text_adapter_version=manifest.text_adapter_version,
            observed_set_schema_version=after.observed_set.schema_version,
            observed_set_policy_version=after.observed_set.policy_version,
            material_candidates=material, observed_checks=observed,
        )

    @staticmethod
    def _same_current_source(left: CurrentClaimGroundingLinkSource,
                             right: CurrentClaimGroundingLinkSource) -> bool:
        return (
            left.session_id == right.session_id and left.census_id == right.census_id
            and left.source_run_id == right.source_run_id
            and left.source_window_fingerprint == right.source_window_fingerprint
            and left.census_fingerprint == right.census_fingerprint
            and left.observed_set.observed_set_fingerprint
            == right.observed_set.observed_set_fingerprint
        )

    @staticmethod
    def _record_matches_source(record, source: CurrentClaimGroundingLinkSource,
                               manifest: ClaimCensusSourceManifest,
                               census: ReviewedClaimCensus) -> bool:  # type: ignore[no-untyped-def]
        return (
            record.census_id == source.census_id
            and record.census.session_id == source.session_id == manifest.session_id == census.session_id
            and record.census.source_run_id == source.source_run_id == manifest.source_run_id == census.source_run_id
            and record.census.source_window_fingerprint == source.source_window_fingerprint
            == manifest.source_window_fingerprint == census.source_window_fingerprint
            and record.census.census_fingerprint == source.census_fingerprint == census.census_fingerprint
            and record.manifest.manifest_fingerprint == manifest.manifest_fingerprint
            and record.census.manifest_fingerprint == manifest.manifest_fingerprint
        )

    @staticmethod
    def _matches(record, run) -> bool:  # type: ignore[no-untyped-def]
        if (run is None or run.session_id != record.census.session_id
            or run.run_id != record.census.source_run_id
            or run.input_fingerprint != record.census.source_window_fingerprint
            or getattr(run, "source_schema_version", None) != record.manifest.source_schema_version
            or getattr(run, "adapter_version", None) != record.manifest.text_adapter_version):
            return False
        publication = getattr(run.receipt, "metric_publication_v2", None)
        return bool(publication is not None and metric_publication_v2_fingerprint(publication) == record.expected_publication_fingerprint)
