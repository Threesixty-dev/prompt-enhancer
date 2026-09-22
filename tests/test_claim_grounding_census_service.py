from __future__ import annotations

from datetime import UTC, datetime

import pytest

from prompt_enhancer.application.analysis.claim_grounding_census import (
    ClaimGroundingCensusRecord,
    DurableClaimGroundingCensusService,
)
from test_claim_grounding_review import SESSION, _Ids, _begin, _classifications, _service


class _Repository:
    def __init__(self) -> None: self.rows: dict[str, ClaimGroundingCensusRecord] = {}; self.issues = 0
    def get_by_idempotency(self, *, session_id: str, idempotency_key_digest: str): return self.rows.get(idempotency_key_digest)
    def issue(self, **values):
        self.issues += 1
        row = ClaimGroundingCensusRecord(values["census_id"], values["census"], values["manifest"], values["idempotency_key_digest"], values["command_fingerprint"], values["expected_publication_fingerprint"], values["created_at"])
        self.rows[row.idempotency_key_digest] = row
        return row, True
    def get(self, census_id: str): return next((x for x in self.rows.values() if x.census_id == census_id), None)
    def list_page(self, *args, **kwargs): raise AssertionError("not used")


class _Authority:
    def expected_publication_fingerprint(self, **kwargs): return "a" * 64


def test_durable_census_replays_before_spending_expired_receipt() -> None:
    reviews, _, clock = _service(); review = _begin(reviews); repository = _Repository()
    service = DurableClaimGroundingCensusService(reviews, repository, _Authority(), _Ids(), clock=clock.wall)
    key = "b" * 64; classifications = _classifications(review)
    first = service.consume_and_issue(session_id=SESSION, review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint, manifest_fingerprint=review.manifest.manifest_fingerprint, classifications=classifications, idempotency_key=key)
    clock.advance(__import__("datetime").timedelta(minutes=6))
    replay = service.consume_and_issue(session_id=SESSION, review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint, manifest_fingerprint=review.manifest.manifest_fingerprint, classifications=classifications, idempotency_key=key)
    assert replay == first and repository.issues == 1
    assert replay.measured is False and replay.candidate_prose_persisted is False


def test_durable_census_canonicalizes_equivalent_classification_order() -> None:
    reviews, _, clock = _service(); review = _begin(reviews); repository = _Repository()
    service = DurableClaimGroundingCensusService(reviews, repository, _Authority(), _Ids(), clock=clock.wall)
    result = service.consume_and_issue(session_id=SESSION, review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint, manifest_fingerprint=review.manifest.manifest_fingerprint, classifications=tuple(reversed(_classifications(review))), idempotency_key="b" * 64)
    replay = service.consume_and_issue(session_id=SESSION, review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint, manifest_fingerprint=review.manifest.manifest_fingerprint, classifications=_classifications(review), idempotency_key="b" * 64)
    assert tuple(item.candidate_id for item in result.census.classifications) == tuple(sorted(item.candidate_id for item in _classifications(review)))
    assert replay == result and repository.issues == 1
