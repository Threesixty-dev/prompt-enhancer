"""Synthetic, local-only coverage for the pre-proposal action authoring surface."""

from __future__ import annotations

import pytest

from prompt_enhancer.application.analysis.requirement_action_evidence import (
    RequirementActionConflictError,
    RequirementActionGuidedAuthoringCommand,
    RequirementActionLinkEntry,
    RequirementActionDecisionCommand,
    RequirementActionDecisionKind,
    REQUIREMENT_ACTION_DECISION_CONFIRMATION,
)

# Reuse the established synthetic-only r8 review harness.  It intentionally
# publishes ephemeral text/descriptors and keeps durable records content-free.
from test_requirement_action_evidence import (  # type: ignore[import-not-found]
    PLAN_CONFIRMATION,
    RUN,
    SESSION,
    WINDOW,
    _context,
    _harness,
    _manifest,
    _requirement_snapshot,
)


def _open(service):  # type: ignore[no-untyped-def]
    contract = service.contract(SESSION)
    return service.open_guided_authoring(
        session_id=SESSION,
        expected_source_run_id=contract.expected_source_run_id,
        source_window_fingerprint=contract.source_window_fingerprint,
        requirement_plan_confirmation_id=contract.requirement_plan_confirmation_id,
        requirement_plan_evidence_fingerprint=(
            contract.requirement_plan_evidence_fingerprint
        ),
        candidate_manifest_fingerprint=contract.candidate_manifest.manifest_fingerprint,
        expected_predecessor_confirmation_id=(
            contract.expected_predecessor_confirmation_id
        ),
    )


def test_guided_authoring_opens_complete_unlinked_surface_and_receipt_is_one_shot() -> None:
    service, _source, _repository, reviews = _harness()

    review = _open(service)

    assert review.source_run_id == RUN
    assert review.source_window_fingerprint == WINDOW
    assert review.requirement_plan_confirmation_id == PLAN_CONFIRMATION
    assert review.all_requirements_and_candidates_included is True
    assert all(not item.linked_action_ids for item in review.requirements)
    assert all(
        not item.linked_requirement_ids for item in review.candidate_memberships
    )

    # A receipt is not reusable even when a caller does not submit a proposal.
    command = RequirementActionGuidedAuthoringCommand(
        expected_source_run_id=review.source_run_id,
        source_window_fingerprint=review.source_window_fingerprint,
        requirement_plan_confirmation_id=review.requirement_plan_confirmation_id,
        requirement_plan_evidence_fingerprint=(
            review.requirement_plan_evidence_fingerprint
        ),
        candidate_manifest_fingerprint=review.candidate_manifest_fingerprint,
        expected_predecessor_confirmation_id=(
            review.expected_predecessor_confirmation_id
        ),
        authoring_receipt_id=review.authoring_receipt_id,
        links=(),
        complete_requirement_link_classification_acknowledged=True,
    )
    reviews.consume_guided_authoring_receipt(session_id=SESSION, command=command)
    with pytest.raises(RequirementActionConflictError):
        reviews.consume_guided_authoring_receipt(session_id=SESSION, command=command)


def test_guided_authoring_persists_only_inert_local_ui_proposal_and_replays() -> None:
    service, _source, _repository, reviews = _harness()
    review = _open(service)
    command = RequirementActionGuidedAuthoringCommand(
        expected_source_run_id=review.source_run_id,
        source_window_fingerprint=review.source_window_fingerprint,
        requirement_plan_confirmation_id=review.requirement_plan_confirmation_id,
        requirement_plan_evidence_fingerprint=(
            review.requirement_plan_evidence_fingerprint
        ),
        candidate_manifest_fingerprint=review.candidate_manifest_fingerprint,
        expected_predecessor_confirmation_id=(
            review.expected_predecessor_confirmation_id
        ),
        authoring_receipt_id=review.authoring_receipt_id,
        links=(
            RequirementActionLinkEntry(
                requirement_index=0, action_candidate_indexes=(0,)
            ),
            RequirementActionLinkEntry(requirement_index=1),
        ),
        complete_requirement_link_classification_acknowledged=True,
    )

    view, applied = service.create_guided_authoring_proposal(
        session_id=SESSION, command=command, idempotency_key="guided-key-00000001"
    )
    replay, replayed = service.create_guided_authoring_proposal(
        session_id=SESSION, command=command, idempotency_key="guided-key-00000001"
    )

    assert applied is True and replayed is False
    assert replay == view
    assert view.status.value == "proposed"
    assert view.decision is None
    assert view.proposal.producer_receipt.kind == "local_review_ui"
    assert (
        view.proposal.producer_receipt.authority
        == "untrusted_local_authoring_commitment"
    )

    # A second valid source receipt cannot repurpose the same idempotency key
    # for a different complete graph.
    reviews._token_factory = lambda: "c" * 64  # test-only distinct receipt
    conflicting = command.model_copy(
        update={
            "authoring_receipt_id": _open(service).authoring_receipt_id,
            "links": (
                RequirementActionLinkEntry(requirement_index=0),
                RequirementActionLinkEntry(
                    requirement_index=1, action_candidate_indexes=(0,)
                ),
            ),
        }
    )
    with pytest.raises(RequirementActionConflictError):
        service.create_guided_authoring_proposal(
            session_id=SESSION,
            command=conflicting,
            idempotency_key="guided-key-00000001",
        )

    native_review = service.review_proposal(
        session_id=SESSION,
        proposal_id=view.proposal.proposal_id,
        expected_source_run_id=RUN,
    )
    confirmed, confirmed_applied = service.decide(
        session_id=SESSION,
        proposal_id=view.proposal.proposal_id,
        command=RequirementActionDecisionCommand(
            expected_source_run_id=RUN,
            decision=RequirementActionDecisionKind.CONFIRM,
            confirmation=REQUIREMENT_ACTION_DECISION_CONFIRMATION,
            review_receipt_id=native_review.review_receipt_id,
            reviewed_graph_fingerprint=native_review.reviewed_graph_fingerprint,
            candidate_manifest_fingerprint=native_review.candidate_manifest_fingerprint,
            reviewed_candidate_set_fingerprint=(
                native_review.reviewed_candidate_set_fingerprint
            ),
            reviewed_descriptor_set_fingerprint=(
                native_review.reviewed_descriptor_set_fingerprint
            ),
            complete_review_acknowledged=True,
            all_requirements_and_candidates_acknowledged=True,
            all_linked_action_semantics_reviewed=True,
        ),
        idempotency_key="guided-decision-key-00000001",
    )
    assert confirmed_applied is True
    assert confirmed.status.value == "confirmed"


def test_guided_receipts_fail_closed_after_republish_rebinding_or_expiry() -> None:
    service, _source, _repository, reviews = _harness()
    review = _open(service)
    command = RequirementActionGuidedAuthoringCommand(
        expected_source_run_id=review.source_run_id,
        source_window_fingerprint=review.source_window_fingerprint,
        requirement_plan_confirmation_id=review.requirement_plan_confirmation_id,
        requirement_plan_evidence_fingerprint=(
            review.requirement_plan_evidence_fingerprint
        ),
        candidate_manifest_fingerprint=review.candidate_manifest_fingerprint,
        expected_predecessor_confirmation_id=(
            review.expected_predecessor_confirmation_id
        ),
        authoring_receipt_id=review.authoring_receipt_id,
        links=(
            RequirementActionLinkEntry(requirement_index=0),
            RequirementActionLinkEntry(requirement_index=1),
        ),
        complete_requirement_link_classification_acknowledged=True,
    )

    # Same run/window but changed ephemeral descriptor text invalidates the
    # old source surface; the receipt cannot be rebound to a new display.
    reviews.publish(
        RUN,
        _context(invocation_preview='{"target":"changed-synthetic-output"}'),
        _requirement_snapshot(),
        service.contract(SESSION).requirement_plan_evidence_fingerprint,
        _manifest(),
    )
    with pytest.raises(RequirementActionConflictError):
        reviews.consume_guided_authoring_receipt(session_id=SESSION, command=command)

    reviews._token_factory = lambda: "e" * 64  # test-only distinct synthetic receipt
    fresh = _open(service)
    rebound = command.model_copy(
        update={
            "authoring_receipt_id": fresh.authoring_receipt_id,
            "requirement_plan_evidence_fingerprint": "f" * 64,
        }
    )
    with pytest.raises(RequirementActionConflictError):
        reviews.consume_guided_authoring_receipt(session_id=SESSION, command=rebound)

    reviews._token_factory = lambda: "d" * 64  # test-only distinct synthetic receipt
    expired = _open(service)
    entry = reviews._entries[RUN]  # test-only synthetic monotonic expiry fence
    entry.expires_monotonic = 100.0
    with pytest.raises(RequirementActionConflictError):
        reviews.consume_guided_authoring_receipt(
            session_id=SESSION,
            command=command.model_copy(
                update={"authoring_receipt_id": expired.authoring_receipt_id}
            ),
        )
