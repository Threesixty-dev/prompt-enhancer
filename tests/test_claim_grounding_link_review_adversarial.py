from __future__ import annotations
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from threading import Event, Thread
import pytest
from pydantic import SecretStr
from prompt_enhancer.application.analysis.claim_grounding_link_review import ClaimGroundingLinkReviewService, ClaimGroundingLinkReviewConflictError, ClaimGroundingLinkReviewUnavailableError, ClaimGroundingLinkCoverageCommand
from prompt_enhancer.application.analysis.claim_grounding_links import ClaimLinkCoverageDecision
from test_claim_grounding_links import _completion, _Ids

S= "a"*64; R= "b"*64; W= "c"*64; M= "d"*64; C= "e"*64; O= "f"*64
class Sources:
    def __init__(self):
        completion=_completion(O); self.completion=completion; self.sources={}; self.source=None; self.calls=0
    def _source(self, *, session_id, census_id):
        key = (session_id, census_id)
        if key not in self.sources:
            self.sources[key] = SimpleNamespace(session_id=session_id, census_id=census_id,
                source_run_id=R, source_window_fingerprint=W, census_fingerprint="2" * 64,
                observed_set=SimpleNamespace(observed_set_fingerprint=M, completions=(self.completion,)))
        self.source = self.sources[key]
        return self.source
    def material_descriptor(self, *, session_id, census_id, **_): return self._source(session_id=session_id, census_id=census_id), "1"*64
    def current_source(self, *, session_id, census_id): self.calls+=1; return self._source(session_id=session_id, census_id=census_id)
class Contexts:
    def __init__(self, completion): self.completion = completion
    def exact_active_claim_grounding_clause(self, **_): return SimpleNamespace(text=SecretStr("Synthetic claim clause."))
    def exact_active_observed_check(self, **_): return self.completion, SimpleNamespace(invocation_truncated=False, result_or_effect_truncated=False, tool_name=SecretStr("pytest"), invocation_preview=SecretStr("pytest -q"), result_or_effect_preview=SecretStr("exit 0"))
class Clock:
    def __init__(self): self.now=datetime(2026,1,1,tzinfo=UTC)
    def __call__(self): return self.now
def service():
    sources=Sources(); clock=Clock(); return ClaimGroundingLinkReviewService(sources, Contexts(sources.completion), _Ids(), clock=clock), sources, clock
def command(review, decision=ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS, refs=(O,)):
    return ClaimGroundingLinkCoverageCommand(session_id=S, review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint, decision=decision, selected_check_references=refs, coverage_review_acknowledged=True)

def test_begin_is_content_free_and_typed_descriptors_are_preview_only():
    svc, _, _ = service(); review=svc.begin_review(session_id=S,census_id="9"*64,candidate_id=C,selected_check_references=(O,))
    assert "Synthetic claim clause" not in review.model_dump_json() and review.proposal_only and not review.measured

def test_missing_receipt_and_session_mismatch_do_not_reserve():
    svc, sources, _ = service()
    with pytest.raises(ClaimGroundingLinkReviewConflictError): svc.reserve(command=ClaimGroundingLinkCoverageCommand(session_id=S,review_receipt_id="9"*64,review_fingerprint="8"*64,decision=ClaimLinkCoverageDecision.REVIEWED_NO_SUPPORT,selected_check_references=(),coverage_review_acknowledged=True), owner="owner")
    assert sources.calls == 0
    with pytest.raises(ClaimGroundingLinkReviewConflictError):
        svc.reserve(command=ClaimGroundingLinkCoverageCommand(session_id="e" * 64, review_receipt_id="9" * 64, review_fingerprint="8" * 64, decision=ClaimLinkCoverageDecision.REVIEWED_NO_SUPPORT, selected_check_references=(), coverage_review_acknowledged=True), owner="owner")

def test_reservation_release_token_and_finalize_are_one_use():
    svc, _, _ = service(); review=svc.begin_review(session_id=S,census_id="9"*64,candidate_id=C,selected_check_references=(O,)); reservation=svc.reserve(command=command(review),owner="owner")
    with pytest.raises(ClaimGroundingLinkReviewConflictError): svc.finalize(reservation.__class__(reservation.receipt_id,reservation.owner,"8"*64))
    svc.release(reservation); reservation=svc.reserve(command=command(review),owner="owner"); svc.finalize(reservation)
    with pytest.raises(ClaimGroundingLinkReviewConflictError): svc.finalize(reservation)

def test_close_revokes_receipts_and_future_operation():
    svc, _, _ = service(); review=svc.begin_review(session_id=S,census_id="9"*64,candidate_id=C,selected_check_references=(O,)); reservation=svc.reserve(command=command(review),owner="owner"); svc.close()
    with pytest.raises(ClaimGroundingLinkReviewConflictError): svc.issue_under_reservation(reservation, lambda: None)

def test_wall_clock_expiry_blocks_reservation():
    svc, _, clock=service(); review=svc.begin_review(session_id=S,census_id="9"*64,candidate_id=C,selected_check_references=(O,)); clock.now += timedelta(minutes=6)
    with pytest.raises(ClaimGroundingLinkReviewConflictError): svc.reserve(command=command(review),owner="owner")

def test_monotonic_expiry_blocks_reservation_with_stable_wall_clock():
    svc, _, clock = service(); ticks = iter((10.0, 10.0, 311.0)); svc._monotonic = lambda: next(ticks)
    review = svc.begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    with pytest.raises(ClaimGroundingLinkReviewConflictError): svc.reserve(command=command(review), owner="owner")
    assert clock.now == datetime(2026, 1, 1, tzinfo=UTC)

def test_release_and_rereserve_rejects_stale_aba_token():
    svc, _, _ = service(); review=svc.begin_review(session_id=S,census_id="9"*64,candidate_id=C,selected_check_references=(O,)); first=svc.reserve(command=command(review), owner="owner"); svc.release(first); second=svc.reserve(command=command(review), owner="owner")
    with pytest.raises(ClaimGroundingLinkReviewConflictError): svc.finalize(first)
    svc.finalize(second)

def test_close_during_blocked_begin_does_not_resurrect_receipt():
    svc, sources, _ = service(); entered=Event(); unblock=Event(); original=sources.material_descriptor
    def blocked(**values):
        entered.set(); unblock.wait(2); return original(**values)
    sources.material_descriptor=blocked
    result=[]
    def start():
        try: result.append(svc.begin_review(session_id=S,census_id="9"*64,candidate_id=C,selected_check_references=(O,)))
        except Exception as error: result.append(error)
    thread=Thread(target=start)
    thread.start(); assert entered.wait(1)
    try:
        svc.close()
    finally:
        unblock.set(); thread.join(2)
    assert not thread.is_alive(); assert len(result) == 1 and isinstance(result[0], ClaimGroundingLinkReviewUnavailableError)

def test_begin_after_close_does_not_read_source():
    svc, sources, _ = service(); svc.close()
    with pytest.raises(ClaimGroundingLinkReviewUnavailableError): svc.begin_review(session_id=S,census_id="9"*64,candidate_id=C,selected_check_references=(O,))
    assert sources.calls == 0

def test_mixed_reserved_and_unreserved_capacity_allows_128_and_rejects_129th():
    svc, _, _ = service(); reviews=[svc.begin_review(session_id=S,census_id=(str(i).zfill(64)),candidate_id=C,selected_check_references=(O,)) for i in range(128)]
    reservations=[svc.reserve(command=command(review), owner="owner"+str(i)) for i,review in enumerate(reviews[:64])]
    extra=svc.begin_review(session_id=S,census_id="f"*64,candidate_id=C,selected_check_references=(O,))
    assert extra.review_receipt_id
    for reservation in reservations: svc.release(reservation)

def test_close_during_receipt_fingerprint_allocation_cannot_insert_receipt():
    sources = Sources(); clock = Clock(); holder = {}
    base = _Ids()
    class ClosingIds:
        def fingerprint(self, namespace, values):
            result = base.fingerprint(namespace, values)
            if namespace == "claim-grounding-link-review-receipt-v1": holder["service"].close()
            return result
    holder["service"] = ClaimGroundingLinkReviewService(sources, Contexts(sources.completion), ClosingIds(), clock=clock)
    with pytest.raises(ClaimGroundingLinkReviewUnavailableError):
        holder["service"].begin_review(session_id=S, census_id="9" * 64, candidate_id=C, selected_check_references=(O,))
    assert holder["service"]._receipts == {}
