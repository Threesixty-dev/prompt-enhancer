from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from prompt_enhancer.application.analysis.claim_grounding_evidence import (
    derive_claim_census_source_manifest,
)
from prompt_enhancer.application.analysis.claim_grounding_review import (
    ClaimGroundingReviewConflictError,
    ClaimGroundingReviewService,
    ClaimGroundingReviewUnavailableError,
    CurrentClaimGroundingSourceResolver,
)
from prompt_enhancer.application.analysis.requirement_plan_evidence import (
    InMemoryRequirementPlanReviewContextStore,
)
from test_claim_grounding_review import SESSION, RUN, WINDOW, _Ids, _context


class _Repository:
    def __init__(self, *records) -> None: self._records = list(records)

    def get_latest(self, session_id: str):
        assert session_id == SESSION
        return self._records.pop(0) if len(self._records) > 1 else self._records[0]


def _sealed(*, run: str = RUN, window: str = WINDOW, publication: object = "published"):
    return SimpleNamespace(
        session_id=SESSION, run_id=run, input_fingerprint=window,
        receipt=SimpleNamespace(metric_publication_v2=publication),
    )


def _resolver(*records, contexts=None):
    store = contexts or InMemoryRequirementPlanReviewContextStore()
    return CurrentClaimGroundingSourceResolver(_Repository(*records), store, _Ids()), store


def test_current_sealed_run_projects_matching_retained_context_only() -> None:
    resolver, contexts = _resolver(_sealed())
    contexts.publish(RUN, _context())
    manifest, candidates = resolver.current_source_for_review(
        session_id=SESSION, expected_source_run_id=RUN,
        expected_source_window_fingerprint=WINDOW,
    )
    assert manifest.source_run_id == RUN
    assert manifest.text_extraction_complete is True
    assert {item.candidate_id for item in candidates} == {
        item.candidate_id for item in manifest.candidates
    }


@pytest.mark.parametrize("published", [False, True])
def test_missing_or_expired_retained_context_fails_closed(published: bool) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    tick = [0.0]
    store = InMemoryRequirementPlanReviewContextStore(
        clock=lambda: now + (timedelta(minutes=6) if published else timedelta()),
        monotonic_clock=lambda: tick[0] + (360.0 if published else 0.0),
    )
    if published:
        # Publish against a fresh clock, then advance both independently.
        store = InMemoryRequirementPlanReviewContextStore(
            clock=lambda: now, monotonic_clock=lambda: tick[0]
        )
        store.publish(RUN, _context())
        tick[0] = 960.0
        now = now + timedelta(minutes=16)
    resolver, _ = _resolver(_sealed(), contexts=store)
    with pytest.raises(ClaimGroundingReviewUnavailableError):
        resolver.current_source_for_review(
            session_id=SESSION, expected_source_run_id=RUN,
            expected_source_window_fingerprint=WINDOW,
        )


def test_expected_selection_and_double_read_changes_are_fenced() -> None:
    contexts = InMemoryRequirementPlanReviewContextStore(); contexts.publish(RUN, _context())
    resolver, _ = _resolver(_sealed(), contexts=contexts)
    with pytest.raises(ClaimGroundingReviewConflictError):
        resolver.current_source_for_review(session_id=SESSION, expected_source_run_id="a" * 64, expected_source_window_fingerprint=WINDOW)
    for changed in (
        _sealed(run="a" * 64), _sealed(window="b" * 64), _sealed(publication="changed"),
    ):
        resolver, _ = _resolver(_sealed(), changed, contexts=contexts)
        with pytest.raises(ClaimGroundingReviewConflictError, match="source changed"):
            resolver.current_source_for_review(session_id=SESSION, expected_source_run_id=RUN, expected_source_window_fingerprint=WINDOW)


class _ProjectedSource:
    def __init__(self, manifest, candidates) -> None:
        self.manifest, self.candidates = manifest, candidates

    def current_source_for_review(self, **_values):  # type: ignore[no-untyped-def]
        return self.manifest, self.candidates


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "coordinate", "cross_session"])
def test_review_service_rejects_mutated_production_projection_before_prose(mutation: str) -> None:
    manifest, candidates = derive_claim_census_source_manifest(_context(), source_run_id=RUN, identifiers=_Ids())
    if mutation == "duplicate":
        candidates = (candidates[0], candidates[0])
    elif mutation == "missing":
        candidates = candidates[:-1]
    elif mutation == "coordinate":
        candidates = (candidates[0].model_copy(update={"clause_index": 99}), *candidates[1:])
    else:
        manifest = manifest.model_copy(update={"session_id": "a" * 64})
    service = ClaimGroundingReviewService(_ProjectedSource(manifest, candidates), _Ids())
    with pytest.raises(ClaimGroundingReviewConflictError):
        service.begin_review(session_id=SESSION, expected_source_run_id=RUN, expected_source_window_fingerprint=WINDOW)
