from __future__ import annotations

import hashlib
import hmac
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from prompt_enhancer.application.analysis.claim_grounding_evidence import (
    ClaimCensusClassification,
    ClaimCensusClassificationEntry,
)
from prompt_enhancer.application.analysis.claim_grounding_review import (
    CLAIM_GROUNDING_REVIEW_TTL,
    CurrentClaimGroundingSource,
    ClaimGroundingReviewConflictError,
    ClaimGroundingReviewService,
)
from prompt_enhancer.application.analysis.text_contracts import (
    EphemeralRedactedMessage,
    P1TextAnalysisInput,
    TextLanguage,
    TextMessageKind,
    TextRole,
    TextTaskProfile,
)
from prompt_enhancer.domain import Provider


class Ids:
    def fingerprint(self, namespace: str, values: tuple[str, ...]) -> str:
        return hmac.new(b"synthetic-review-key", "\x1f".join((namespace, *values)).encode(), hashlib.sha256).hexdigest()


class Resolver:
    def __init__(self, source: CurrentClaimGroundingSource) -> None:
        self.source = source
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False
        self.on_return = None

    def current_source(self, session_id: str) -> CurrentClaimGroundingSource:
        if self.block:
            self.entered.set()
            self.release.wait(timeout=3)
        if self.on_return is not None:
            self.on_return()
        return self.source


SESSION, WINDOW, RUN = "1" * 64, "2" * 64, "3" * 64


def context(window: str = WINDOW) -> P1TextAnalysisInput:
    messages = (
        EphemeralRedactedMessage(
            message_id="4" * 64, sequence=1, role=TextRole.USER,
            kind=TextMessageKind.REQUEST, language=TextLanguage.ENGLISH,
            text=SecretStr("Synthetic request."),
        ),
        EphemeralRedactedMessage(
            message_id="5" * 64, sequence=2, role=TextRole.AGENT,
            kind=TextMessageKind.RESPONSE, language=TextLanguage.ENGLISH,
            text=SecretStr("Synthetic completion claim."),
        ),
    )
    return P1TextAnalysisInput(
        provider=Provider.SYNTHETIC, session_id=SESSION,
        provider_version="synthetic.1", adapter_version="synthetic-adapter.1",
        source_schema_version="synthetic-source.1", content_schema_version="synthetic-content.1",
        redactor_version="synthetic-redactor.1", text_extraction_complete=True,
        available_message_kinds=frozenset({TextMessageKind.REQUEST, TextMessageKind.RESPONSE}),
        analysis_window_fingerprint=window, focus_message_id="4" * 64,
        observed_message_count=2, eligible_message_count=2, messages=messages,
        task_profile=TextTaskProfile(applicability=()),
    )


def setup(*, resolver=None, **kwargs):
    source = resolver or Resolver(CurrentClaimGroundingSource(RUN, WINDOW, context()))
    service = ClaimGroundingReviewService(source, Ids(), **kwargs)
    review = service.begin_review(session_id=SESSION)
    candidate_id = review.manifest.candidates[0].candidate_id
    classifications = (ClaimCensusClassificationEntry(candidate_id=candidate_id, classification=ClaimCensusClassification.MATERIAL_CLAIM),)
    return service, source, review, classifications


def args(review, classifications):
    return dict(session_id=SESSION, review_receipt_id=review.review_receipt_id,
                review_fingerprint=review.review_fingerprint,
                manifest_fingerprint=review.manifest.manifest_fingerprint,
                classifications=classifications)


def test_replay_and_concurrent_double_consume_are_one_use():
    service, _, review, classifications = setup()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _consume(service, review, classifications), range(2)))
    assert sum(result is None for result in results) == 1
    with pytest.raises(ClaimGroundingReviewConflictError):
        service.consume_review(**args(review, classifications))


def _consume(service, review, classifications):
    try:
        return service.consume_review(**args(review, classifications))
    except ClaimGroundingReviewConflictError:
        return None


def test_changed_current_source_invalidates_receipt():
    service, source, review, classifications = setup()
    source.source = CurrentClaimGroundingSource("6" * 64, WINDOW, context())
    with pytest.raises(ClaimGroundingReviewConflictError, match="source changed"):
        service.consume_review(**args(review, classifications))


def test_revoke_while_resolver_blocked_invalidates_in_flight_consume():
    service, source, review, classifications = setup()
    source.block = True
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(_consume(service, review, classifications)))
    thread.start()
    assert source.entered.wait(timeout=2)
    service.revoke_session(SESSION)
    source.release.set()
    thread.join(timeout=3)
    assert not thread.is_alive() and outcome == [None]


def test_resolver_crossing_ttl_cannot_consume_expired_receipt():
    tick = [10.0]
    service, source, review, classifications = setup(monotonic_clock=lambda: tick[0])
    source.on_return = lambda: tick.__setitem__(0, tick[0] + CLAIM_GROUNDING_REVIEW_TTL.total_seconds() + 1)
    with pytest.raises(ClaimGroundingReviewConflictError):
        service.consume_review(**args(review, classifications))


def test_expiry_capacity_and_monotonic_clock_backwards_are_bounded():
    wall = [datetime(2030, 1, 1, tzinfo=UTC)]
    tick = [10.0]
    service, _, review, classifications = setup(clock=lambda: wall[0], monotonic_clock=lambda: tick[0], max_active=1)
    evicted = service.begin_review(session_id=SESSION)
    # A second receipt evicts the oldest at capacity.
    with pytest.raises(ClaimGroundingReviewConflictError):
        service.consume_review(**args(review, classifications))
    # Advancing monotonic time expires even when wall clock moves backwards.
    tick[0] += CLAIM_GROUNDING_REVIEW_TTL.total_seconds() + 1
    wall[0] -= timedelta(days=1)
    with pytest.raises(ClaimGroundingReviewConflictError):
        service.consume_review(**args(evicted, classifications))


@pytest.mark.parametrize("receipt_id", ["", "unsafe receipt", "x" * 63, "x" * 65])
def test_invalid_receipt_ids_are_rejected_without_secret_prose(receipt_id):
    service, _, review, classifications = setup()
    with pytest.raises(ClaimGroundingReviewConflictError) as exc:
        service.consume_review(session_id=SESSION, review_receipt_id=receipt_id,
                               review_fingerprint=review.review_fingerprint,
                               manifest_fingerprint=review.manifest.manifest_fingerprint,
                               classifications=classifications)
    assert "Synthetic completion claim" not in repr(exc.value)


def test_review_repr_and_serialization_never_include_candidate_prose():
    _, _, review, _ = setup()
    assert "Synthetic completion claim" not in repr(review)
    encoded = json.dumps(review.model_dump(mode="json"))
    assert "Synthetic completion claim" not in encoded


def test_mutating_returned_proposal_does_not_mutate_receipt_state():
    service, _, review, classifications = setup()
    original = args(review, classifications)
    review = review.model_copy(update={"review_fingerprint": "9" * 64})
    assert service.consume_review(**original).session_id == SESSION
