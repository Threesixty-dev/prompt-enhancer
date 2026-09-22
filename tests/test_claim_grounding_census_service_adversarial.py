from __future__ import annotations

from datetime import timedelta
from threading import Event, Thread

import pytest

from prompt_enhancer.application.analysis.claim_grounding_census import (
    ClaimGroundingCensusConflictError, ClaimGroundingCensusOutcomeUnknownError, ClaimGroundingCensusPersistenceError,
    ClaimGroundingCensusRecord, DurableClaimGroundingCensusService,
)
from prompt_enhancer.application.analysis.claim_grounding_review import ClaimGroundingReviewConflictError
from prompt_enhancer.application.analysis.claim_grounding_review import ClaimGroundingReviewService

from test_claim_grounding_review import SESSION, _Ids, _begin, _classifications, _service


class _TransactionalRepository:
    def __init__(self, mode: str = "ok") -> None:
        self.mode, self.rows, self.issue_calls = mode, {}, 0
        self.reconcile_outage = False

    def get_by_idempotency(self, *, session_id: str, idempotency_key_digest: str):
        if self.reconcile_outage:
            self.reconcile_outage = False
            raise RuntimeError("synthetic reconciliation outage")
        return self.rows.get(idempotency_key_digest)

    def issue(self, **values):
        self.issue_calls += 1
        if self.mode == "source_conflict":
            raise ClaimGroundingReviewConflictError("synthetic current source changed")
        if self.mode == "rollback":
            self.mode = "ok"
            raise RuntimeError("synthetic transaction rollback")
        row = ClaimGroundingCensusRecord(
            values["census_id"], values["census"], values["manifest"],
            values["idempotency_key_digest"], values["command_fingerprint"],
            values["expected_publication_fingerprint"], values["created_at"],
        )
        self.rows[row.idempotency_key_digest] = row
        if self.mode == "committed_then_error":
            self.mode = "ok"
            raise RuntimeError("synthetic post-commit transport failure")
        if self.mode == "unknown":
            self.rows.clear(); self.reconcile_outage = True
            raise RuntimeError("synthetic unknown outcome")
        return row, True

    def get(self, census_id: str):
        return next((row for row in self.rows.values() if row.census_id == census_id), None)

    def list_page(self, *args, **kwargs):
        raise AssertionError("not used")


class _Authority:
    def __init__(self, *, block: bool = False) -> None:
        self.block, self.entered, self.release = block, Event(), Event()

    def expected_publication_fingerprint(self, **kwargs):
        self.entered.set()
        if self.block:
            assert self.release.wait(timeout=3)
        return "a" * 64


def _command(service, review, classifications, *, key: str = "retry_key_00000001"):
    return service.consume_and_issue(
        session_id=SESSION, review_receipt_id=review.review_receipt_id,
        review_fingerprint=review.review_fingerprint,
        manifest_fingerprint=review.manifest.manifest_fingerprint,
        classifications=classifications, idempotency_key=key,
    )


def _durable(reviews, repository, authority, clock):
    return DurableClaimGroundingCensusService(
        reviews, repository, authority, _Ids(), clock=clock.wall
    )


def test_rollback_before_commit_releases_exact_receipt_for_retry() -> None:
    reviews, _, clock = _service(); review = _begin(reviews)
    reviews._tokens = lambda: "a" * 64  # type: ignore[attr-defined]  # repeatable synthetic reservation IDs
    repository = _TransactionalRepository("rollback")
    durable = _durable(reviews, repository, _Authority(), clock)
    with pytest.raises(ClaimGroundingCensusPersistenceError):
        _command(durable, review, _classifications(review))
    result = _command(durable, review, _classifications(review))
    assert repository.issue_calls == 2 and result.census.manifest_fingerprint == review.manifest.manifest_fingerprint


def test_committed_then_exception_recovers_once_and_replay_does_not_reissue() -> None:
    reviews, _, clock = _service(); review = _begin(reviews)
    repository = _TransactionalRepository("committed_then_error")
    durable = _durable(reviews, repository, _Authority(), clock)
    result = _command(durable, review, _classifications(review))
    assert repository.issue_calls == 1
    assert _command(durable, review, _classifications(review)) == result
    assert repository.issue_calls == 1


def test_unavailable_reconciliation_reports_unknown_and_retires_receipt() -> None:
    reviews, _, clock = _service(); review = _begin(reviews)
    repository = _TransactionalRepository("unknown")
    durable = _durable(reviews, repository, _Authority(), clock)
    with pytest.raises(ClaimGroundingCensusOutcomeUnknownError):
        _command(durable, review, _classifications(review))
    with pytest.raises(ClaimGroundingCensusConflictError):
        _command(durable, review, _classifications(review))


def test_repository_current_source_conflict_never_persists_a_census() -> None:
    reviews, _, clock = _service(); review = _begin(reviews)
    repository = _TransactionalRepository("source_conflict")
    durable = _durable(reviews, repository, _Authority(), clock)
    with pytest.raises(ClaimGroundingCensusConflictError):
        _command(durable, review, _classifications(review))
    assert repository.issue_calls == 1 and repository.rows == {}


def test_reservation_is_exclusive_against_legacy_consume_and_ttl_capacity() -> None:
    _unused, source, clock = _service()
    tokens = iter(("a" * 64, "b" * 64, "c" * 64, "d" * 64))
    reviews = ClaimGroundingReviewService(source, _Ids(), clock=clock.wall,
                                          monotonic_clock=clock.monotonic,
                                          token_factory=lambda: next(tokens),
                                          max_active=1)
    review = _begin(reviews)
    reservation = reviews.prepare_durable_consume(
        session_id=SESSION, review_receipt_id=review.review_receipt_id,
        review_fingerprint=review.review_fingerprint,
        manifest_fingerprint=review.manifest.manifest_fingerprint,
        classifications=_classifications(review), owner="a" * 64,
    )
    with pytest.raises(ClaimGroundingReviewConflictError):
        reviews.consume_review(session_id=SESSION, review_receipt_id=review.review_receipt_id,
                               review_fingerprint=review.review_fingerprint,
                               manifest_fingerprint=review.manifest.manifest_fingerprint,
                               classifications=_classifications(review))
    clock.advance(timedelta(minutes=6))
    with pytest.raises(ClaimGroundingReviewConflictError):
        reviews.assert_durable_reservation(reservation, owner="a" * 64)


def test_revoke_while_prepare_resolution_is_blocked_restores_no_receipt() -> None:
    reviews, source, _clock = _service(); review = _begin(reviews)
    entered, release, outcome = Event(), Event(), []
    original = source.current_source
    def blocked(session_id):
        entered.set(); assert release.wait(timeout=3)
        return original(session_id)
    source.current_source = blocked  # type: ignore[method-assign]
    worker = Thread(target=lambda: outcome.append(_prepare(reviews, review)))
    worker.start(); assert entered.wait(timeout=2)
    reviews.revoke_session(SESSION); release.set(); worker.join(timeout=3)
    assert not worker.is_alive() and isinstance(outcome[0], ClaimGroundingReviewConflictError)
    with pytest.raises(ClaimGroundingReviewConflictError):
        reviews.consume_review(session_id=SESSION, review_receipt_id=review.review_receipt_id,
                               review_fingerprint=review.review_fingerprint,
                               manifest_fingerprint=review.manifest.manifest_fingerprint,
                               classifications=_classifications(review))


@pytest.mark.parametrize("action", ("revoke", "close"))
def test_revocation_or_close_during_blocked_publication_never_issues(action) -> None:
    reviews, _, clock = _service(); review = _begin(reviews)
    repository, authority = _TransactionalRepository(), _Authority(block=True)
    durable = _durable(reviews, repository, authority, clock)
    outcome = []
    worker = Thread(target=lambda: outcome.append(_run_command(durable, review)))
    worker.start(); assert authority.entered.wait(timeout=2)
    interrupter = Thread(target=(lambda: reviews.revoke_session(SESSION)) if action == "revoke" else reviews.close)
    interrupter.start()
    authority.release.set(); worker.join(timeout=3); interrupter.join(timeout=3)
    assert not worker.is_alive() and not interrupter.is_alive()
    assert repository.issue_calls == 0


def _run_command(service, review):
    try:
        return _command(service, review, _classifications(review))
    except Exception as error:
        return error


def _prepare(reviews, review):
    try:
        return reviews.prepare_durable_consume(
            session_id=SESSION, review_receipt_id=review.review_receipt_id,
            review_fingerprint=review.review_fingerprint,
            manifest_fingerprint=review.manifest.manifest_fingerprint,
            classifications=_classifications(review), owner="a" * 64,
        )
    except Exception as error:
        return error
