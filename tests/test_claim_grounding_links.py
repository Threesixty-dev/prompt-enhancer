from __future__ import annotations

import pytest

from prompt_enhancer.application.analysis.claim_grounding_census import ClaimGroundingCensusRecord
from prompt_enhancer.application.analysis.claim_grounding_evidence import ClaimCensusClassification, ClaimCensusClassificationEntry, build_reviewed_claim_census, derive_claim_census_source_manifest
from prompt_enhancer.application.analysis.claim_grounding_links import ClaimLinkCoverageDecision, ClaimObservedCheckCoverage, build_source_bound_observed_check_set, build_claim_observed_check_coverage
from prompt_enhancer.application.verification.observed_check_completion import EphemeralObservedCheckCompletion, ObservedCheckOutcome
from prompt_enhancer.domain import Provider
from test_claim_grounding_review import _Ids, _context, RUN


def _record():
    manifest, _ = derive_claim_census_source_manifest(_context(), source_run_id=RUN, identifiers=_Ids())
    census = build_reviewed_claim_census(manifest, classifications=tuple(ClaimCensusClassificationEntry(candidate_id=item.candidate_id, classification=ClaimCensusClassification.MATERIAL_CLAIM) for item in manifest.candidates), identifiers=_Ids())
    return ClaimGroundingCensusRecord("9" * 64, census, manifest, "8" * 64, "7" * 64, "6" * 64, __import__("datetime").datetime.now(__import__("datetime").UTC))


def _completion(reference="a" * 64):
    return EphemeralObservedCheckCompletion(provider=Provider.CODEX, source_reference_id=reference, observed_sequence=1, check_kind="test", outcome=ObservedCheckOutcome.PASSED, provider_execution_status="completed", exit_code=0, classifier_version="local-command-rules-v1", normalizer_version="strict-shell-free-v2", rule_id="test.pytest")

def _set(record, completions):
    return build_source_bound_observed_check_set(session_id=record.census.session_id, source_run_id=record.census.source_run_id, source_window_fingerprint=record.census.source_window_fingerprint, source_schema_version=record.manifest.source_schema_version, completions=completions, identifiers=_Ids())


def test_complete_material_partition_is_nonmetric_and_retains_exact_outcomes() -> None:
    record = _record(); first = record.census.classifications[0].candidate_id
    rows = tuple(ClaimObservedCheckCoverage(candidate_id=item.candidate_id, decision=ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS if item.candidate_id == first else ClaimLinkCoverageDecision.REVIEWED_NO_SUPPORT, observed_check_references=("a" * 64,) if item.candidate_id == first else (), coverage_review_acknowledged=True) for item in record.census.classifications)
    result = build_claim_observed_check_coverage(record=record, coverage=rows, observed_set=_set(record, (_completion(),)), identifiers=_Ids())
    assert result.proposal_only is True and result.measured is False and result.content_persisted is False
    assert result.observed_completions[0].outcome is ObservedCheckOutcome.PASSED


def test_rejects_partial_or_unavailable_links() -> None:
    record = _record(); candidate = record.census.classifications[0].candidate_id
    with pytest.raises(ValueError, match="partition"):
        build_claim_observed_check_coverage(record=record, coverage=(ClaimObservedCheckCoverage(candidate_id=candidate, decision=ClaimLinkCoverageDecision.UNRESOLVED, observed_check_references=(), coverage_review_acknowledged=True),), observed_set=_set(record, ()), identifiers=_Ids())
    rows = tuple(ClaimObservedCheckCoverage(candidate_id=item.candidate_id, decision=ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS, observed_check_references=("b" * 64,), coverage_review_acknowledged=True) for item in record.census.classifications)
    with pytest.raises(ValueError, match="unavailable"):
        build_claim_observed_check_coverage(record=record, coverage=rows, observed_set=_set(record, (_completion(),)), identifiers=_Ids())
