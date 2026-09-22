"""Synthetic-only unit coverage for the ephemeral verification-review bridge."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from prompt_enhancer.application.analysis.requirement_plan_evidence import (
    InMemoryRequirementPlanReviewContextStore, RequirementCoordinate,
)
from prompt_enhancer.application.analysis.requirement_verification_review import (
    RequirementVerificationReviewConflictError, RequirementVerificationReviewService,
)
from prompt_enhancer.application.analysis.text_contracts import (
    EphemeralRedactedActionDescriptor, EventKind, TextMessageKind, TextRole,
)
from prompt_enhancer.application.verification.observed_check_completion import (
    EphemeralObservedCheckCompletion, ObservedCheckOutcome,
)
from prompt_enhancer.domain import Provider


def _id(number: int) -> str:
    return f"{number:064x}"


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2030, 1, 1, tzinfo=UTC)
        self.tick = 10.0


class _Opportunities:
    def __init__(self) -> None:
        self.revision = 0
        self.head: str | None = None
        self.set = _id(4)
        self.session = _id(1)
        self.requirement = _id(2)
        self.opportunity = _id(3)
        self.coordinate = RequirementCoordinate(message_sequence=0, clause_index=0)

    def snapshot(self, session_id: str, fingerprint: str, *, through_revision=None):
        if session_id != self.session or fingerprint != self.set:
            return None
        revision = self.revision if through_revision is None else through_revision
        if revision != self.revision:
            return SimpleNamespace(revision=revision, evidence=SimpleNamespace(opportunities=SimpleNamespace(opportunities=())), authority_heads=())
        opportunity = SimpleNamespace(opportunity_id=self.opportunity, requirement_id=self.requirement,
                                      coordinate=self.coordinate)
        scope = SimpleNamespace(
            opportunities=(opportunity,), requirement_plan_confirmation_id=_id(7),
            requirement_plan_proposal_id=_id(8), source_window_fingerprint=_id(6),
        )
        head = () if self.head is None else (SimpleNamespace(opportunity_id=self.opportunity, authority_record_id=self.head),)
        return SimpleNamespace(revision=self.revision, evidence=SimpleNamespace(opportunities=scope), authority_heads=head)


def _service(clock: _Clock):
    opportunities = _Opportunities()
    context = SimpleNamespace(
        session_id=opportunities.session, analysis_window_fingerprint=_id(6),
        messages=(SimpleNamespace(sequence=0, role=TextRole.USER, kind=TextMessageKind.REQUEST,
                                  text=SecretStr("Synthetic requirement clause.")),),
    )
    contexts = InMemoryRequirementPlanReviewContextStore(
        clock=lambda: clock.now, monotonic_clock=lambda: clock.tick,
        token_factory=lambda: _id(30), candidate_binding_key=b"x" * 32,
    )
    contexts.publish(_id(5), context)
    requirement = SimpleNamespace(requirement_id=opportunities.requirement, coordinate=RequirementCoordinate(message_sequence=0, clause_index=0))
    plan = SimpleNamespace(session_id=opportunities.session, source_window_fingerprint=_id(6), confirmation_id=_id(7), proposal_id=_id(8), requirements=(requirement,))
    source = SimpleNamespace(session_id=opportunities.session, expected_source_run_id=_id(5), source_window_fingerprint=_id(6))
    token_values = iter((_id(31), _id(32), _id(33), _id(34)))
    service = RequirementVerificationReviewService(
        opportunities, SimpleNamespace(current_snapshot=lambda _session: plan),
        SimpleNamespace(current_source_contract=lambda _session: source), contexts,
        clock=lambda: clock.now, monotonic_clock=lambda: clock.tick,
        token_factory=lambda: next(token_values),
    )
    return service, opportunities, source, contexts, context


def _open(service, opportunities, source, *, predecessor=None, revision=0):
    return service.open(session_id=opportunities.session, opportunity_set_fingerprint=opportunities.set,
                        opportunity_id=opportunities.opportunity, expected_source_run_id=source.expected_source_run_id,
                        through_revision=revision, expected_predecessor_authority_id=predecessor)


def _add_observed_check(context) -> str:  # type: ignore[no-untyped-def]
    source_reference_id = _id(61)
    context.observed_check_completions = (
        EphemeralObservedCheckCompletion(
            provider=Provider.CODEX,
            source_reference_id=source_reference_id,
            observed_sequence=12,
            check_kind="test",
            outcome=ObservedCheckOutcome.PASSED,
            provider_execution_status="completed",
            exit_code=0,
            classifier_version="local-command-rules-v1",
            normalizer_version="strict-shell-free-v2",
            rule_id="test.pytest",
        ),
    )
    context.action_descriptors = (
        EphemeralRedactedActionDescriptor(
            source_reference_id=source_reference_id,
            event_kind=EventKind.TOOL_END,
            tool_name=SecretStr("commandExecution"),
            invocation_preview=SecretStr("pytest -q"),
            result_or_effect_preview=SecretStr("completed"),
            invocation_truncated=False,
            result_or_effect_truncated=False,
            redactor_version="redactor-v1",
        ),
    )
    return source_reference_id


def test_observed_check_review_binds_one_current_candidate_and_consumes_once() -> None:
    service, opportunities, source, _contexts, context = _service(_Clock())
    candidate_id = _add_observed_check(context)
    manifest = service.observed_candidates(
        session_id=opportunities.session,
        opportunity_set_fingerprint=opportunities.set,
        opportunity_id=opportunities.opportunity,
        expected_source_run_id=source.expected_source_run_id,
        through_revision=0,
        expected_predecessor_authority_id=None,
    )
    assert manifest.candidates[0].candidate_id == candidate_id
    assert manifest.candidates[0].observed_sequence == 12
    review = service.open_observed_check(
        session_id=opportunities.session,
        opportunity_set_fingerprint=opportunities.set,
        opportunity_id=opportunities.opportunity,
        candidate_id=candidate_id,
        expected_source_run_id=source.expected_source_run_id,
        through_revision=0,
        expected_predecessor_authority_id=None,
        candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
    )
    command = SimpleNamespace(
        opportunity_set_fingerprint=opportunities.set,
        opportunity_id=opportunities.opportunity,
        candidate_id=candidate_id,
        expected_predecessor_authority_id=None,
        expected_source_run_id=source.expected_source_run_id,
        source_window_fingerprint=manifest.source_window_fingerprint,
        through_revision=0,
        candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
        review_receipt_id=review.review_receipt_id,
        review_fingerprint=review.review_fingerprint,
        full_criterion_coverage_acknowledged=True,
    )
    service.consume_observed_check(session_id=opportunities.session, command=command)
    with pytest.raises(RequirementVerificationReviewConflictError):
        service.consume_observed_check(session_id=opportunities.session, command=command)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("candidate_id", _id(62)),
        ("through_revision", 1),
        ("expected_source_run_id", _id(63)),
        ("source_window_fingerprint", _id(64)),
        ("opportunity_set_fingerprint", _id(65)),
        ("opportunity_id", _id(66)),
        ("full_criterion_coverage_acknowledged", False),
    ),
)
def test_observed_check_review_rejects_each_tampered_issue_binding(
    field: str, value: object,
) -> None:
    service, opportunities, source, _contexts, context = _service(_Clock())
    candidate_id = _add_observed_check(context)
    manifest = service.observed_candidates(
        session_id=opportunities.session, opportunity_set_fingerprint=opportunities.set,
        opportunity_id=opportunities.opportunity,
        expected_source_run_id=source.expected_source_run_id,
        through_revision=0, expected_predecessor_authority_id=None,
    )
    review = service.open_observed_check(
        session_id=opportunities.session, opportunity_set_fingerprint=opportunities.set,
        opportunity_id=opportunities.opportunity, candidate_id=candidate_id,
        expected_source_run_id=source.expected_source_run_id,
        through_revision=0, expected_predecessor_authority_id=None,
        candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
    )
    command = SimpleNamespace(
        opportunity_set_fingerprint=opportunities.set, opportunity_id=opportunities.opportunity,
        candidate_id=candidate_id, expected_predecessor_authority_id=None,
        expected_source_run_id=source.expected_source_run_id,
        source_window_fingerprint=manifest.source_window_fingerprint,
        through_revision=0, candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
        review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint,
        full_criterion_coverage_acknowledged=True,
    )
    setattr(command, field, value)
    with pytest.raises(RequirementVerificationReviewConflictError):
        service.consume_observed_check(session_id=opportunities.session, command=command)


def test_observed_check_review_rechecks_current_head_descriptor_and_expiry() -> None:
    clock = _Clock(); service, opportunities, source, _contexts, context = _service(clock)
    candidate_id = _add_observed_check(context)
    manifest = service.observed_candidates(
        session_id=opportunities.session, opportunity_set_fingerprint=opportunities.set,
        opportunity_id=opportunities.opportunity,
        expected_source_run_id=source.expected_source_run_id,
        through_revision=0, expected_predecessor_authority_id=None,
    )
    review = service.open_observed_check(
        session_id=opportunities.session, opportunity_set_fingerprint=opportunities.set,
        opportunity_id=opportunities.opportunity, candidate_id=candidate_id,
        expected_source_run_id=source.expected_source_run_id,
        through_revision=0, expected_predecessor_authority_id=None,
        candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
    )
    command = SimpleNamespace(
        opportunity_set_fingerprint=opportunities.set, opportunity_id=opportunities.opportunity,
        candidate_id=candidate_id, expected_predecessor_authority_id=None,
        expected_source_run_id=source.expected_source_run_id,
        source_window_fingerprint=manifest.source_window_fingerprint,
        through_revision=0, candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
        review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint,
        full_criterion_coverage_acknowledged=True,
    )
    opportunities.head = _id(67)
    with pytest.raises(RequirementVerificationReviewConflictError):
        service.consume_observed_check(session_id=opportunities.session, command=command)
    # Use a fresh receipt to prove descriptor edits also invalidate native review.
    opportunities.head = None
    review = service.open_observed_check(
        session_id=opportunities.session, opportunity_set_fingerprint=opportunities.set,
        opportunity_id=opportunities.opportunity, candidate_id=candidate_id,
        expected_source_run_id=source.expected_source_run_id,
        through_revision=0, expected_predecessor_authority_id=None,
        candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
    )
    command.review_receipt_id, command.review_fingerprint = review.review_receipt_id, review.review_fingerprint
    context.action_descriptors = (
        context.action_descriptors[0].model_copy(
            update={"result_or_effect_preview": SecretStr("changed")}
        ),
    )
    with pytest.raises(RequirementVerificationReviewConflictError):
        service.consume_observed_check(session_id=opportunities.session, command=command)
    review = service.open_observed_check(
        session_id=opportunities.session, opportunity_set_fingerprint=opportunities.set,
        opportunity_id=opportunities.opportunity, candidate_id=candidate_id,
        expected_source_run_id=source.expected_source_run_id,
        through_revision=0, expected_predecessor_authority_id=None,
        candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
    )
    clock.now += timedelta(minutes=6); clock.tick += 360
    command.review_receipt_id, command.review_fingerprint = review.review_receipt_id, review.review_fingerprint
    with pytest.raises(RequirementVerificationReviewConflictError):
        service.consume_observed_check(session_id=opportunities.session, command=command)


def test_opens_one_exact_synthetic_clause_without_persisting_or_repr_leak() -> None:
    service, opportunities, source, _contexts, _context = _service(_Clock())
    review = _open(service, opportunities, source)
    assert review.requirement_text == "Synthetic requirement clause."
    assert review.local_only is True and review.content_persisted is False
    assert "Synthetic requirement clause" not in repr(review)


def test_expired_replayed_tampered_and_drifted_reviews_fail_closed_without_new_read() -> None:
    clock = _Clock(); service, opportunities, source, _contexts, _context = _service(clock)
    review = _open(service, opportunities, source)
    command = SimpleNamespace(opportunity_set_fingerprint=opportunities.set, opportunity_id=opportunities.opportunity,
                              expected_predecessor_authority_id=None, expected_source_run_id=source.expected_source_run_id,
                              source_window_fingerprint=review.source_window_fingerprint,
                              review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint)
    service.consume(session_id=opportunities.session, command=command)
    with pytest.raises(RequirementVerificationReviewConflictError): service.consume(session_id=opportunities.session, command=command)
    review = _open(service, opportunities, source)
    command.review_receipt_id, command.review_fingerprint = review.review_receipt_id, _id(99)
    with pytest.raises(RequirementVerificationReviewConflictError): service.consume(session_id=opportunities.session, command=command)
    review = _open(service, opportunities, source)
    command.review_receipt_id, command.review_fingerprint = review.review_receipt_id, review.review_fingerprint
    clock.now += timedelta(minutes=6); clock.tick += 360
    with pytest.raises(RequirementVerificationReviewConflictError): service.consume(session_id=opportunities.session, command=command)


@pytest.mark.parametrize("field,value", [
    ("session", _id(90)), ("set", _id(91)), ("opportunity", _id(92)),
])
def test_wrong_session_set_or_opportunity_is_denied(field: str, value: str) -> None:
    service, opportunities, source, _contexts, _context = _service(_Clock())
    arguments = {"session_id": opportunities.session, "opportunity_set_fingerprint": opportunities.set,
                 "opportunity_id": opportunities.opportunity, "expected_source_run_id": source.expected_source_run_id,
                 "through_revision": 0, "expected_predecessor_authority_id": None}
    arguments[{"session": "session_id", "set": "opportunity_set_fingerprint", "opportunity": "opportunity_id"}[field]] = value
    with pytest.raises((RequirementVerificationReviewConflictError, ValueError)):
        service.open(**arguments)


def test_current_head_revision_source_and_coordinate_drift_are_denied() -> None:
    service, opportunities, source, contexts, context = _service(_Clock())
    opportunities.head = _id(40)
    with pytest.raises(RequirementVerificationReviewConflictError): _open(service, opportunities, source)
    service, opportunities, source, contexts, context = _service(_Clock())
    opportunities.revision = 1
    with pytest.raises(RequirementVerificationReviewConflictError): _open(service, opportunities, source, revision=0)
    service, opportunities, source, contexts, context = _service(_Clock())
    source.expected_source_run_id = _id(41)
    with pytest.raises(RequirementVerificationReviewConflictError): _open(service, opportunities, source)
    service, opportunities, source, contexts, context = _service(_Clock())
    source.expected_source_run_id = _id(5)
    source.source_window_fingerprint = _id(42)
    with pytest.raises(RequirementVerificationReviewConflictError): _open(service, opportunities, source)
    source.source_window_fingerprint = _id(6)
    opportunities.coordinate = RequirementCoordinate(message_sequence=0, clause_index=1)
    with pytest.raises(RequirementVerificationReviewConflictError): _open(service, opportunities, source)
    opportunities.coordinate = RequirementCoordinate(message_sequence=0, clause_index=0)
    context.messages = (SimpleNamespace(sequence=0, role=TextRole.AGENT, kind=TextMessageKind.PLAN, text=SecretStr("Synthetic plan.")),)
    contexts.publish(_id(5), context)
    with pytest.raises(RequirementVerificationReviewConflictError): _open(service, opportunities, source)


def test_fresh_current_run_for_the_same_window_is_reviewable_after_restart() -> None:
    service, opportunities, source, contexts, context = _service(_Clock())
    source.expected_source_run_id = _id(50)
    # The second service/store is a restart boundary: it has no old context.
    with pytest.raises(RequirementVerificationReviewConflictError):
        _open(service, opportunities, source)
    contexts.publish(_id(50), context)
    review = _open(service, opportunities, source)
    assert review.expected_source_run_id == _id(50)


def test_consume_revalidates_current_binding_without_an_extra_clause_read() -> None:
    service, opportunities, source, contexts, _context = _service(_Clock())
    reads = 0
    original = contexts.exact_active_requirement_clause
    def counted(**kwargs):
        nonlocal reads
        reads += 1
        return original(**kwargs)
    contexts.exact_active_requirement_clause = counted  # type: ignore[method-assign]
    review = _open(service, opportunities, source)
    assert reads == 1
    command = SimpleNamespace(opportunity_set_fingerprint=opportunities.set, opportunity_id=opportunities.opportunity,
                              expected_predecessor_authority_id=None, expected_source_run_id=source.expected_source_run_id,
                              source_window_fingerprint=review.source_window_fingerprint,
                              review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint)
    service.consume(session_id=opportunities.session, command=command)
    assert reads == 1


def test_consume_rejects_tampered_binding_and_current_head_or_revision_drift() -> None:
    service, opportunities, source, _contexts, _context = _service(_Clock())
    review = _open(service, opportunities, source)
    command = SimpleNamespace(opportunity_set_fingerprint=opportunities.set, opportunity_id=_id(66),
                              expected_predecessor_authority_id=None, expected_source_run_id=source.expected_source_run_id,
                              source_window_fingerprint=review.source_window_fingerprint,
                              review_receipt_id=review.review_receipt_id, review_fingerprint=review.review_fingerprint)
    with pytest.raises(RequirementVerificationReviewConflictError): service.consume(session_id=opportunities.session, command=command)
    service, opportunities, source, _contexts, _context = _service(_Clock())
    review = _open(service, opportunities, source)
    command.opportunity_id = opportunities.opportunity; command.review_receipt_id = review.review_receipt_id; command.review_fingerprint = review.review_fingerprint
    opportunities.head = _id(67)
    with pytest.raises(RequirementVerificationReviewConflictError): service.consume(session_id=opportunities.session, command=command)
    service, opportunities, source, _contexts, _context = _service(_Clock())
    review = _open(service, opportunities, source)
    command.review_receipt_id = review.review_receipt_id; command.review_fingerprint = review.review_fingerprint
    opportunities.revision = 1
    with pytest.raises(RequirementVerificationReviewConflictError): service.consume(session_id=opportunities.session, command=command)
