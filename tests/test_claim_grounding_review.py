from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta

import pytest

from prompt_enhancer.application.analysis.claim_grounding_evidence import (
    ClaimCensusClassification, ClaimCensusClassificationEntry,
)
from prompt_enhancer.application.analysis.claim_grounding_review import (
    ClaimGroundingCensusReviewProposal, ClaimGroundingReviewConflictError, ClaimGroundingReviewService,
    ClaimGroundingReviewUnavailableError, CurrentClaimGroundingSource,
    UncomposedClaimGroundingSourceResolver,
    CurrentClaimGroundingSourceResolver,
)
from prompt_enhancer.application.analysis.requirement_plan_evidence import (
    InMemoryRequirementPlanReviewContextStore,
)
from prompt_enhancer.application.analysis.text_contracts import (
    EphemeralRedactedMessage, P1TextAnalysisInput, TextLanguage,
    TextMessageKind, TextRole, TextTaskProfile,
)
from prompt_enhancer.domain import Provider
from pydantic import SecretStr


SESSION, RUN, WINDOW = "1" * 64, "2" * 64, "3" * 64


class _Ids:
    def fingerprint(self, namespace: str, values: tuple[str, ...]) -> str:
        return hmac.new(b"synthetic-claim-review-key", "\x1f".join((namespace, *values)).encode(), hashlib.sha256).hexdigest()


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)
        self.tick = 0.0

    def wall(self) -> datetime: return self.now
    def monotonic(self) -> float: return self.tick
    def advance(self, value: timedelta) -> None:
        self.now += value; self.tick += value.total_seconds()


def _context(text: str = "Implemented synthetic feature. Tests passed.") -> P1TextAnalysisInput:
    request = EphemeralRedactedMessage(message_id="4" * 64, sequence=1, role=TextRole.USER, kind=TextMessageKind.REQUEST, language=TextLanguage.ENGLISH, text=SecretStr("Synthetic request."))
    response = EphemeralRedactedMessage(message_id="5" * 64, sequence=2, role=TextRole.AGENT, kind=TextMessageKind.RESPONSE, language=TextLanguage.ENGLISH, text=SecretStr(text))
    return P1TextAnalysisInput(provider=Provider.SYNTHETIC, session_id=SESSION, provider_version="synthetic.1", adapter_version="synthetic-adapter.1", source_schema_version="synthetic-source.1", content_schema_version="synthetic-content.1", redactor_version="synthetic-redactor.1", text_extraction_complete=True, available_message_kinds=frozenset({TextMessageKind.REQUEST, TextMessageKind.RESPONSE}), analysis_window_fingerprint=WINDOW, focus_message_id=request.message_id, observed_message_count=2, eligible_message_count=2, messages=(request, response), task_profile=TextTaskProfile(applicability=()))


class _Source:
    def __init__(self) -> None: self.current = CurrentClaimGroundingSource(RUN, WINDOW, _context())
    def current_source(self, session_id: str) -> CurrentClaimGroundingSource:
        assert session_id == SESSION
        return self.current


def _service(clock: _Clock | None = None):
    clock = clock or _Clock(); source = _Source()
    tokens = iter(("6" * 64, "7" * 64, "8" * 64, "9" * 64))
    return ClaimGroundingReviewService(source, _Ids(), clock=clock.wall, monotonic_clock=clock.monotonic, token_factory=lambda: next(tokens)), source, clock


def _begin(service: ClaimGroundingReviewService):
    return service.begin_review(session_id=SESSION)


def _classifications(review):
    return tuple(ClaimCensusClassificationEntry(candidate_id=item.candidate_id, classification=ClaimCensusClassification.MATERIAL_CLAIM) for item in review.candidates)


def test_full_review_receipt_flow_is_ephemeral_content_free_and_one_use() -> None:
    service, _source, _clock = _service(); review = _begin(service)
    assert review.native_confirmation_completed is False
    assert review.metric_authority_established is False
    assert "Implemented" not in review.model_dump_json()
    payload = review.model_dump()
    payload["candidates"] = review.candidates
    with pytest.raises(ValueError):
        ClaimGroundingCensusReviewProposal.model_validate({
            **payload, "native_confirmation_completed": True,
        })
    census = service.consume_review(session_id=SESSION, review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint, manifest_fingerprint=review.manifest.manifest_fingerprint, classifications=_classifications(review))
    assert census.manifest_fingerprint == review.manifest.manifest_fingerprint
    with pytest.raises(ClaimGroundingReviewConflictError):
        service.consume_review(session_id=SESSION, review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint, manifest_fingerprint=review.manifest.manifest_fingerprint, classifications=_classifications(review))


def test_receipt_is_bound_to_exact_manifest_census_and_fresh_source() -> None:
    service, source, _clock = _service(); review = _begin(service)
    with pytest.raises(ClaimGroundingReviewConflictError):
        service.consume_review(session_id=SESSION, review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint, manifest_fingerprint="a" * 64, classifications=_classifications(review))
    service, source, _clock = _service(); review = _begin(service)
    source.current = CurrentClaimGroundingSource("8" * 64, WINDOW, _context())
    with pytest.raises(ClaimGroundingReviewConflictError):
        service.consume_review(session_id=SESSION, review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint, manifest_fingerprint=review.manifest.manifest_fingerprint, classifications=_classifications(review))


def test_expiry_revocation_and_uncomposed_source_fail_closed() -> None:
    service, _source, clock = _service(); review = _begin(service); clock.advance(timedelta(minutes=6))
    with pytest.raises(ClaimGroundingReviewConflictError):
        service.consume_review(session_id=SESSION, review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint, manifest_fingerprint=review.manifest.manifest_fingerprint, classifications=_classifications(review))
    service, _source, _clock = _service(); review = _begin(service); service.revoke_session(SESSION)
    with pytest.raises(ClaimGroundingReviewConflictError):
        service.consume_review(session_id=SESSION, review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint, manifest_fingerprint=review.manifest.manifest_fingerprint, classifications=_classifications(review))
    with pytest.raises(ClaimGroundingReviewUnavailableError):
        ClaimGroundingReviewService(UncomposedClaimGroundingSourceResolver(), _Ids()).begin_review(session_id=SESSION)


def test_close_during_source_resolution_releases_inflight_ownership() -> None:
    service, source, _clock = _service()
    original = source.current_source
    source.current_source = lambda session_id: (service.close(), original(session_id))[1]  # type: ignore[method-assign]
    with pytest.raises(ClaimGroundingReviewUnavailableError):
        service.begin_review(session_id=SESSION)
    assert service._inflight == {}  # type: ignore[attr-defined]
    assert service._session_generations == {}  # type: ignore[attr-defined]


def test_close_during_consume_resolution_releases_inflight_ownership() -> None:
    service, source, _clock = _service(); review = _begin(service)
    original = source.current_source
    source.current_source = lambda session_id: (service.close(), original(session_id))[1]  # type: ignore[method-assign]
    with pytest.raises(ClaimGroundingReviewUnavailableError):
        service.consume_review(session_id=SESSION, review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint, manifest_fingerprint=review.manifest.manifest_fingerprint, classifications=_classifications(review))
    assert service._inflight == {}  # type: ignore[attr-defined]
    assert service._session_generations == {}  # type: ignore[attr-defined]


class _SealedRepository:
    def __init__(self, *records) -> None: self.records = list(records)
    def get_latest(self, session_id: str):
        assert session_id == SESSION
        return self.records.pop(0) if len(self.records) > 1 else self.records[0]


def _sealed(publication: object):
    return SimpleNamespace(
        session_id=SESSION, run_id=RUN, input_fingerprint=WINDOW,
        receipt=SimpleNamespace(metric_publication_v2=publication),
    )


def test_production_resolver_projects_only_matching_complete_retained_source() -> None:
    contexts = InMemoryRequirementPlanReviewContextStore()
    contexts.publish(RUN, _context())
    publication = object()
    resolver = CurrentClaimGroundingSourceResolver(
        _SealedRepository(_sealed(publication)), contexts, _Ids(),
    )
    service = ClaimGroundingReviewService(resolver, _Ids())
    review = service.begin_review(
        session_id=SESSION, expected_source_run_id=RUN,
        expected_source_window_fingerprint=WINDOW,
    )
    assert review.source_run_id == RUN
    assert tuple(item.candidate_id for item in review.candidates) == tuple(
        item.candidate_id for item in review.manifest.candidates
    )


def test_production_resolver_fences_publication_change_after_projection() -> None:
    contexts = InMemoryRequirementPlanReviewContextStore()
    contexts.publish(RUN, _context())
    resolver = CurrentClaimGroundingSourceResolver(
        _SealedRepository(_sealed(object()), _sealed(object())), contexts, _Ids(),
    )
    with pytest.raises(ClaimGroundingReviewConflictError, match="source changed"):
        resolver.current_source_for_review(
            session_id=SESSION, expected_source_run_id=RUN,
            expected_source_window_fingerprint=WINDOW,
        )
