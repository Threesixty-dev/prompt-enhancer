from __future__ import annotations
from dataclasses import replace
import pytest
from prompt_enhancer.application.analysis.claim_grounding_links import ClaimLinkCoverageDecision, ClaimObservedCheckCoverage, SourceBoundObservedCheckSet, build_claim_observed_check_coverage, build_source_bound_observed_check_set
from prompt_enhancer.application.verification.observed_check_completion import ObservedCheckOutcome
from test_claim_grounding_links import _completion, _Ids, _record

def rows(record, decision=ClaimLinkCoverageDecision.REVIEWED_NO_SUPPORT):
    return tuple(ClaimObservedCheckCoverage(candidate_id=x.candidate_id, decision=decision, observed_check_references=(), coverage_review_acknowledged=True) for x in record.census.classifications)

def observed(record, completions=(), **patch):
    return build_source_bound_observed_check_set(session_id=record.manifest.session_id, source_run_id=record.manifest.source_run_id, source_window_fingerprint=record.manifest.source_window_fingerprint, source_schema_version=record.manifest.source_schema_version, completions=tuple(completions), identifiers=_Ids()).model_copy(update=patch)

def test_exact_partition_rejects_missing_duplicate_and_out_of_set():
    record = _record()
    with pytest.raises(ValueError, match="complete exact partition"):
        build_claim_observed_check_coverage(record=record, coverage=rows(record)[:-1], observed_set=observed(record), identifiers=_Ids())
    extra = ClaimObservedCheckCoverage(candidate_id="a" * 64, decision=ClaimLinkCoverageDecision.REVIEWED_NO_SUPPORT, observed_check_references=(), coverage_review_acknowledged=True)
    with pytest.raises(ValueError, match="complete exact partition"):
        build_claim_observed_check_coverage(record=record, coverage=rows(record)[:-1] + (extra,), observed_set=observed(record), identifiers=_Ids())

def test_linked_references_need_available_unique_checks():
    record = _record(); candidate = record.census.classifications[0].candidate_id
    linked = ClaimObservedCheckCoverage(candidate_id=candidate, decision=ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS, observed_check_references=("a" * 64,), coverage_review_acknowledged=True)
    with pytest.raises(ValueError, match="unavailable"):
        build_claim_observed_check_coverage(record=record, coverage=(linked,) + tuple(x for x in rows(record) if x.candidate_id != candidate), observed_set=observed(record), identifiers=_Ids())
    with pytest.raises(ValueError, match="unique"):
        ClaimObservedCheckCoverage(candidate_id=candidate, decision=ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS, observed_check_references=("a" * 64, "a" * 64), coverage_review_acknowledged=True)

def test_source_cross_binding_and_forged_completion_rejected():
    record = _record()
    for field in ("session_id", "source_run_id", "source_window_fingerprint"):
        with pytest.raises(ValueError):
            build_claim_observed_check_coverage(record=record, coverage=rows(record), observed_set=observed(record).model_copy(update={field: "e" * 64}), identifiers=_Ids())
    with pytest.raises(ValueError, match="schema binding"):
        build_claim_observed_check_coverage(record=record, coverage=rows(record), observed_set=observed(record).model_copy(update={"source_schema_version": "synthetic-other-schema-v1"}), identifiers=_Ids())
    altered = replace(record, manifest=record.manifest.model_copy(update={"source_window_fingerprint": "e" * 64}))
    with pytest.raises(ValueError):
        build_claim_observed_check_coverage(record=altered, coverage=rows(altered), observed_set=observed(altered), identifiers=_Ids())
    candidate = record.census.classifications[0].candidate_id; forged = _completion().model_copy(update={"outcome": ObservedCheckOutcome.CHECK_FAILED})
    linked = ClaimObservedCheckCoverage(candidate_id=candidate, decision=ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS, observed_check_references=(forged.source_reference_id,), coverage_review_acknowledged=True)
    with pytest.raises(ValueError, match="outcome disagrees"):
        build_claim_observed_check_coverage(record=record, coverage=(linked,), observed_set=observed(record, (forged,)), identifiers=_Ids())

def test_no_support_and_unresolved_remain_distinct_nonmetric_states():
    record = _record(); items = record.census.classifications
    coverage = tuple(ClaimObservedCheckCoverage(candidate_id=x.candidate_id, decision=ClaimLinkCoverageDecision.REVIEWED_NO_SUPPORT if i == 0 else ClaimLinkCoverageDecision.UNRESOLVED, observed_check_references=(), coverage_review_acknowledged=True) for i, x in enumerate(items))
    result = build_claim_observed_check_coverage(record=record, coverage=coverage, observed_set=observed(record), identifiers=_Ids())
    assert {x.decision for x in result.coverage} == {ClaimLinkCoverageDecision.REVIEWED_NO_SUPPORT, ClaimLinkCoverageDecision.UNRESOLVED}
    assert result.proposal_only and not result.measured and not result.metric_authority_established

def test_mixed_outcomes_retained_without_aggregate_pass():
    record = _record(); candidate = record.census.classifications[0].candidate_id; passed = _completion("a" * 64); failed = _completion("b" * 64).model_copy(update={"outcome": ObservedCheckOutcome.CHECK_FAILED, "exit_code": 1})
    linked = ClaimObservedCheckCoverage(candidate_id=candidate, decision=ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS, observed_check_references=(passed.source_reference_id, failed.source_reference_id), coverage_review_acknowledged=True)
    result = build_claim_observed_check_coverage(record=record, coverage=(linked,) + tuple(x for x in rows(record) if x.candidate_id != candidate), observed_set=observed(record, (failed, passed)), identifiers=_Ids())
    assert [x.outcome for x in result.observed_completions] == [ObservedCheckOutcome.PASSED, ObservedCheckOutcome.CHECK_FAILED] and not hasattr(result, "aggregate_pass")

def test_reordered_coverage_is_canonical_and_content_free():
    record = _record(); result = build_claim_observed_check_coverage(record=record, coverage=tuple(reversed(rows(record))), observed_set=observed(record), identifiers=_Ids())
    assert tuple(x.candidate_id for x in result.coverage) == tuple(sorted(x.candidate_id for x in result.coverage))
    assert "Synthetic completed" not in result.model_dump_json() and result.content_persisted is False
