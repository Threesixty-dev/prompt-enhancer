from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from threading import RLock
from types import SimpleNamespace

import pytest

from prompt_enhancer.application.analysis.claim_grounding_link_review import (
    ClaimGroundingLinkReviewConflictError, ClaimGroundingLinkReviewReservation,
    ClaimGroundingLinkReviewService, _Receipt,
)
from pydantic import SecretStr
from test_claim_grounding_link_review_adversarial import C, O, S, Contexts, Sources, command, service
from test_claim_grounding_links import _Ids


def _service() -> ClaimGroundingLinkReviewService:
    service = object.__new__(ClaimGroundingLinkReviewService)
    service._lock = RLock(); service._monotonic = lambda: 10.0; service._clock = lambda: datetime(2026, 1, 1, tzinfo=UTC)
    review = SimpleNamespace(review_expires_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=1))
    service._receipts = OrderedDict({"a" * 64: _Receipt(review, 20.0, reserved_owner="owner", reservation_token="token")})
    return service


def test_finalized_released_or_stale_reservation_never_executes_callback() -> None:
    service = _service(); reservation = ClaimGroundingLinkReviewReservation("a" * 64, "owner", "token")
    called: list[bool] = []
    service.finalize(reservation)
    with pytest.raises(ClaimGroundingLinkReviewConflictError): service.issue_under_reservation(reservation, lambda: called.append(True))
    service = _service(); reservation = ClaimGroundingLinkReviewReservation("a" * 64, "owner", "token")
    service.release(reservation)
    with pytest.raises(ClaimGroundingLinkReviewConflictError): service.issue_under_reservation(reservation, lambda: called.append(True))
    service = _service()
    with pytest.raises(ClaimGroundingLinkReviewConflictError): service.issue_under_reservation(ClaimGroundingLinkReviewReservation("a" * 64, "owner", "stale"), lambda: called.append(True))
    assert called == []


@pytest.mark.parametrize("advance", ["wall", "monotonic"])
def test_expiry_during_source_revalidation_blocks_reservation(advance: str) -> None:
    svc, sources, clock = service()
    if advance == "monotonic":
        tick = [10.0]
        svc._monotonic = lambda: tick[0]
    review = svc.begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    original = sources.current_source
    def advancing(**values):
        if advance == "wall": clock.now += timedelta(minutes=6)
        else: tick[0] = svc._receipts[review.review_receipt_id].expires_tick + 1
        return original(**values)
    sources.current_source = advancing
    with pytest.raises(ClaimGroundingLinkReviewConflictError): svc.reserve(command=command(review), owner="owner")


def test_reservation_fingerprint_failure_leaves_receipt_unreserved() -> None:
    svc, _, _ = service(); review = svc.begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    original = svc._ids
    class Failing:
        def fingerprint(self, *_args): raise RuntimeError("synthetic fingerprint failure")
    svc._ids = Failing()
    with pytest.raises(RuntimeError): svc.reserve(command=command(review), owner="owner")
    assert svc._receipts[review.review_receipt_id].reserved_owner is None
    svc._ids = original
    assert svc.reserve(command=command(review), owner="owner").receipt_id == review.review_receipt_id


def test_revoke_session_removes_only_its_receipts() -> None:
    svc, _, _ = service()
    review = svc.begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    svc.revoke_session(S)
    with pytest.raises(ClaimGroundingLinkReviewConflictError): svc.reserve(command=command(review), owner="owner")


def test_malformed_begin_ids_do_not_access_source() -> None:
    svc, sources, _ = service()
    with pytest.raises(ClaimGroundingLinkReviewConflictError): svc.begin_review(session_id="bad", census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    assert sources.calls == 0


def test_separate_service_instances_do_not_collide_receipts() -> None:
    first, _, _ = service(); second, _, _ = service()
    first._tokens = lambda: "1" * 64; second._tokens = lambda: "2" * 64
    a = first.begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    b = second.begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    assert a.review_receipt_id != b.review_receipt_id


@pytest.mark.parametrize(("field", "value"), [
    ("session_id", "7" * 64),
    ("census_id", "8" * 64),
    ("source_run_id", "3" * 64),
    ("source_window_fingerprint", "4" * 64),
    ("census_fingerprint", "5" * 64),
])
def test_begin_refresh_rejects_full_source_identity_drift(field: str, value: str) -> None:
    svc, sources, _ = service()
    original = sources.current_source

    def drift(**values):
        source = original(**values)
        changed = SimpleNamespace(**vars(source))
        setattr(changed, field, value)
        return changed

    sources.current_source = drift
    with pytest.raises(ClaimGroundingLinkReviewConflictError, match="source changed"):
        svc.begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))


@pytest.mark.parametrize(("field", "value"), [
    ("session_id", "7" * 64),
    ("census_id", "8" * 64),
    ("source_run_id", "3" * 64),
    ("source_window_fingerprint", "4" * 64),
    ("census_fingerprint", "5" * 64),
])
def test_reserve_rejects_full_source_identity_drift(field: str, value: str) -> None:
    svc, sources, _ = service()
    review = svc.begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    setattr(sources.sources[(S, "9" * 64)], field, value)
    with pytest.raises(ClaimGroundingLinkReviewConflictError, match="source changed"):
        svc.reserve(command=command(review), owner="owner")


def test_descriptor_commitment_is_canonical_and_changes_with_descriptor_text() -> None:
    class ChangedContexts:
        def __init__(self, completion): self._base = Contexts(completion)
        def exact_active_claim_grounding_clause(self, **values): return self._base.exact_active_claim_grounding_clause(**values)
        def exact_active_observed_check(self, **values):
            completion, descriptor = self._base.exact_active_observed_check(**values)
            return completion, SimpleNamespace(
                invocation_truncated=False, result_or_effect_truncated=False,
                tool_name=descriptor.tool_name, invocation_preview=SecretStr("pytest:-q"),
                result_or_effect_preview=descriptor.result_or_effect_preview,
            )

    first_sources = Sources()
    second_sources = Sources()
    first = ClaimGroundingLinkReviewService(first_sources, Contexts(first_sources.completion), _Ids(), token_factory=lambda: "1" * 64)
    second = ClaimGroundingLinkReviewService(second_sources, ChangedContexts(second_sources.completion), _Ids(), token_factory=lambda: "1" * 64)
    first_review = first.begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    second_review = second.begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    assert first_review.review_receipt_id == second_review.review_receipt_id
    assert first_review.review_fingerprint != second_review.review_fingerprint


def test_reservation_snapshot_is_exact_content_free_and_immutable_after_command_mutation() -> None:
    svc, _, _ = service()
    review = svc.begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    submitted = command(review)
    reservation = svc.reserve(command=submitted, owner="owner")
    snapshot = svc.snapshot_under_reservation(reservation)
    assert snapshot.session_id == S
    assert snapshot.census_id == "9" * 64
    assert snapshot.candidate_id == C
    assert snapshot.review_receipt_id == review.review_receipt_id
    assert snapshot.review_fingerprint == review.review_fingerprint
    assert snapshot.selected_check_references == (O,)
    completion = snapshot.selected_observed_completions[0]
    assert completion.source_reference_id == O
    assert completion.outcome == "passed" and completion.exit_code == 0
    assert completion.classifier_version == "local-command-rules-v1"
    assert snapshot.proposal_only and not snapshot.measured and not snapshot.metric_authority_established
    assert "Synthetic claim" not in repr(snapshot)
    assert "pytest -q" not in repr(snapshot)
    object.__setattr__(submitted, "selected_check_references", ())
    assert svc.snapshot_under_reservation(reservation).selected_check_references == (O,)
    with pytest.raises(AttributeError):
        snapshot.selected_check_references = ()  # type: ignore[misc]


def test_released_finalized_or_expired_reservation_cannot_read_snapshot() -> None:
    svc, _, clock = service()
    review = svc.begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    reservation = svc.reserve(command=command(review), owner="owner")
    svc.release(reservation)
    with pytest.raises(ClaimGroundingLinkReviewConflictError):
        svc.snapshot_under_reservation(reservation)
    reservation = svc.reserve(command=command(review), owner="owner")
    svc.finalize(reservation)
    with pytest.raises(ClaimGroundingLinkReviewConflictError):
        svc.snapshot_under_reservation(reservation)
    review = svc.begin_review(session_id=S, census_id="8" * 64, candidate_id=C, selected_check_references=(O,))
    reservation = svc.reserve(command=command(review), owner="owner")
    clock.now += timedelta(minutes=6)
    with pytest.raises(ClaimGroundingLinkReviewConflictError):
        svc.snapshot_under_reservation(reservation)
