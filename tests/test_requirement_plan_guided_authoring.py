"""Synthetic coverage for native-gated guided requirement-plan authoring."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from prompt_enhancer.application.analysis.requirement_plan_evidence import (
    ExcludedRequirementClause,
    PlanCoordinate,
    RequirementDisposition,
    RequirementEvidenceEntry,
    RequirementPlanConflictError,
    RequirementPlanGuidedAuthoringCommand,
    RequirementPlanGuidedAuthoringReview,
    RequirementPlanProposalStatus,
    RequirementPlanExclusionReason,
    RequirementPlanInputError,
    REQUIREMENT_PLAN_DECISION_CONFIRMATION,
    RequirementPlanDecisionCommand,
    RequirementPlanDecisionKind,
)
from pydantic import SecretStr
from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.config import AppSettings
from prompt_enhancer.interfaces.http.browser_session import CSRF_HEADER

from test_requirement_plan_evidence import (
    RUN,
    SESSION,
    WINDOW,
    _Repository,
    _Source,
    _complete_review_context,
    _service,
)
from test_requirement_plan_evidence_persistence import _setup


TOKEN = "synthetic_guided_authoring_http_token_123456789"


def _command(review, *, predecessor: str | None = None):  # type: ignore[no-untyped-def]
    user = tuple(
        candidate
        for candidate in review.candidate_clauses
        if candidate.candidate_kind == "user_clause"
    )
    plans = tuple(
        candidate
        for candidate in review.candidate_clauses
        if candidate.candidate_kind == "plan"
    )
    latest_plan_sequence = max(candidate.message_sequence for candidate in plans)
    active = tuple(candidate for candidate in user if candidate.message_sequence <= latest_plan_sequence)
    excluded = tuple(candidate for candidate in user if candidate.message_sequence > latest_plan_sequence)
    return RequirementPlanGuidedAuthoringCommand(
        expected_source_run_id=review.source_run_id,
        source_window_fingerprint=review.source_window_fingerprint,
        expected_predecessor_confirmation_id=predecessor,
        manifest_fingerprint=review.manifest_fingerprint,
        authoring_receipt_id=review.authoring_receipt_id,
        requirements=tuple(
            RequirementEvidenceEntry(
                coordinate={
                    "message_sequence": candidate.message_sequence,
                    "clause_index": candidate.clause_index,
                },
                disposition=RequirementDisposition.LINKED,
                plan_indexes=tuple(range(len(plans))),
            )
            for candidate in active
        ),
        excluded_user_clauses=tuple(
            ExcludedRequirementClause(
                coordinate={
                    "message_sequence": candidate.message_sequence,
                    "clause_index": candidate.clause_index,
                },
                reason=RequirementPlanExclusionReason.NOT_REQUIREMENT,
            )
            for candidate in excluded
        ),
        plan_items=tuple(
            PlanCoordinate(
                message_sequence=candidate.message_sequence,
                clause_index=candidate.clause_index,
            )
            for candidate in plans
        ),
        complete_user_clause_classification_acknowledged=True,
    )


def _open(service):  # type: ignore[no-untyped-def]
    contract = service.contract(SESSION)
    return service.open_guided_authoring(
        session_id=SESSION,
        expected_source_run_id=contract.expected_source_run_id,
        source_window_fingerprint=contract.source_window_fingerprint,
        manifest_fingerprint=contract.source_manifest.manifest_fingerprint,
        expected_predecessor_confirmation_id=(
            contract.expected_predecessor_confirmation_id
        ),
    )


def test_guided_authoring_creates_only_an_unconfirmed_local_review_ui_proposal() -> None:
    source = _Source(context=_complete_review_context())
    service = _service(_Repository(), source)
    review = _open(service)

    proposal, applied = service.create_guided_proposal(
        session_id=SESSION,
        command=_command(review),
        idempotency_key="guided-authoring-synthetic-0001",
    )

    assert applied is True
    assert review.contract_version == "requirement-plan-guided-authoring-v1"
    assert review.all_candidates_included is True
    assert proposal.status is RequirementPlanProposalStatus.PROPOSED
    assert proposal.decision is None
    assert proposal.proposal.producer_receipt.kind == "local_review_ui"
    assert (
        proposal.proposal.producer_receipt.authority
        == "untrusted_local_authoring_commitment"
    )
    assert proposal.proposal.content_persisted is False


def test_guided_authoring_receipt_cannot_be_rebound_to_a_new_predecessor() -> None:
    source = _Source(context=_complete_review_context())
    service = _service(_Repository(), source)
    review = _open(service)

    with pytest.raises(RequirementPlanConflictError):
        source.store.consume_guided_authoring_receipt(
            authoring_receipt_id=review.authoring_receipt_id,
            session_id=SESSION,
            source_run_id=RUN,
            source_window_fingerprint=WINDOW,
            manifest_fingerprint=review.manifest_fingerprint,
            expected_predecessor_confirmation_id="9" * 64,
        )


def test_guided_authoring_receipt_refuses_same_source_republished_with_new_text() -> None:
    source = _Source(context=_complete_review_context())
    service = _service(_Repository(), source)
    review = _open(service)
    context = _complete_review_context()
    changed_plan = context.messages[1].model_copy(
        update={"text": SecretStr("Implement the revised synthetic plan.")}
    )
    source.store.publish(
        RUN, context.model_copy(update={"messages": (context.messages[0], changed_plan, context.messages[2])})
    )

    with pytest.raises(RequirementPlanConflictError):
        source.store.consume_guided_authoring_receipt(
            authoring_receipt_id=review.authoring_receipt_id,
            session_id=SESSION,
            source_run_id=RUN,
            source_window_fingerprint=WINDOW,
            manifest_fingerprint=review.manifest_fingerprint,
            expected_predecessor_confirmation_id=None,
        )


def test_guided_authoring_reuses_closed_graph_validation_before_consuming_receipt() -> None:
    source = _Source(context=_complete_review_context())
    service = _service(_Repository(), source)
    review = _open(service)
    complete = _command(review)
    incomplete = complete.model_copy(update={"requirements": complete.requirements[:-1]})

    with pytest.raises(RequirementPlanInputError):
        service.create_guided_proposal(
            session_id=SESSION,
            command=incomplete,
            idempotency_key="guided-authoring-incomplete-0001",
        )
    # Validation failed before consuming the native receipt; a complete retry remains valid.
    proposal, applied = service.create_guided_proposal(
        session_id=SESSION,
        command=complete,
        idempotency_key="guided-authoring-complete-after-reject-0001",
    )
    assert applied is True and proposal.status is RequirementPlanProposalStatus.PROPOSED

    with pytest.raises(ValueError):
        ExcludedRequirementClause(
            coordinate={"message_sequence": 1, "clause_index": 0},
            reason=RequirementPlanExclusionReason.SUPERSEDED,
        )
    with pytest.raises(ValueError):
        complete.model_copy(
            update={
                "requirements": (
                    complete.requirements[0].model_copy(update={"plan_indexes": (99,)}),
                    *complete.requirements[1:],
                )
            }
        ).normalized_graph()


def test_native_guided_authoring_http_then_review_and_decision_persist_to_sqlite(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    database, session_id, run, repository, service = _setup(tmp_path)
    app = create_app(
        settings=AppSettings(home=tmp_path / "synthetic-guided-http"),
        database=database,
        api_token=TOKEN,
        requirement_plan_evidence_service=service,
        user_presence_confirmation=lambda _request, _body: None,
    )
    base = f"/v1/sessions/{session_id}/requirement-plan-evidence"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        contract = client.get(f"{base}/contract", headers={API_TOKEN_HEADER: TOKEN})
        browser = client.get("/auth/session")
        native_headers = {
            CSRF_HEADER: browser.json()["csrf_token"],
            "Origin": "http://127.0.0.1",
        }
        native_review = client.post(
            f"{base}/guided-authoring/review",
            headers=native_headers,
            json={
                "expected_source_run_id": run.run_id,
                "source_window_fingerprint": contract.json()[
                    "source_window_fingerprint"
                ],
                "manifest_fingerprint": contract.json()["source_manifest"][
                    "manifest_fingerprint"
                ],
                "expected_predecessor_confirmation_id": None,
                "confirmation": "open_exact_local_requirement_plan_guided_authoring",
            },
        )
        guided = RequirementPlanGuidedAuthoringReview.model_validate(native_review.json())
        command = _command(guided)
        proposed = client.post(
            f"{base}/guided-authoring/proposals",
            headers={
                API_TOKEN_HEADER: TOKEN,
                "Content-Type": "application/json",
                "Idempotency-Key": "guided-authoring-http-example-0001",
            },
            json=command.model_dump(mode="json"),
        )
        replayed = client.post(
            f"{base}/guided-authoring/proposals",
            headers={
                API_TOKEN_HEADER: TOKEN,
                "Content-Type": "application/json",
                "Idempotency-Key": "guided-authoring-http-example-0001",
            },
            json=command.model_dump(mode="json"),
        )
        conflicting = command.model_copy(
            update={
                "requirements": (
                    command.requirements[0].model_copy(
                        update={
                            "disposition": RequirementDisposition.PENDING,
                            "plan_indexes": (),
                        }
                    ),
                    *command.requirements[1:],
                )
            }
        )
        conflict = client.post(
            f"{base}/guided-authoring/proposals",
            headers={
                API_TOKEN_HEADER: TOKEN,
                "Content-Type": "application/json",
                "Idempotency-Key": "guided-authoring-http-example-0001",
            },
            json=conflicting.model_dump(mode="json"),
        )
        proposal = proposed.json()["proposal"]
        ordinary_review = client.post(
            f"{base}/proposals/{proposal['proposal_id']}/review",
            headers=native_headers,
            json={
                "expected_source_run_id": run.run_id,
                "confirmation": "open_exact_local_requirement_plan_clause_review",
            },
        )
        reviewed = ordinary_review.json()
        decided = client.post(
            f"{base}/proposals/{proposal['proposal_id']}/decision",
            headers={
                **native_headers,
                "Idempotency-Key": "guided-authoring-http-decision-0001",
            },
            json=RequirementPlanDecisionCommand(
                expected_source_run_id=run.run_id,
                decision=RequirementPlanDecisionKind.CONFIRM,
                confirmation=REQUIREMENT_PLAN_DECISION_CONFIRMATION,
                review_receipt_id=reviewed["review_receipt_id"],
                manifest_fingerprint=reviewed["manifest_fingerprint"],
                reviewed_graph_fingerprint=reviewed["reviewed_graph_fingerprint"],
                reviewed_candidate_set_fingerprint=reviewed[
                    "reviewed_candidate_set_fingerprint"
                ],
                complete_review_acknowledged=True,
            ).model_dump(mode="json"),
        )

    assert native_review.status_code == 200
    assert proposed.status_code == 201
    assert proposed.json()["proposal"]["decision"] is None
    assert replayed.status_code == 200 and replayed.json()["applied"] is False
    assert conflict.status_code == 409
    assert proposed.json()["proposal"]["producer_receipt"]["kind"] == "local_review_ui"
    assert ordinary_review.status_code == 200
    assert decided.status_code == 201
    assert decided.json()["proposal"]["status"] == "confirmed"
    assert repository.snapshot(
        session_id, contract.json()["source_window_fingerprint"]
    ).confirmation_id == decided.json()["proposal"]["decision_id"]


def test_guided_authoring_rejects_token_only_native_review_and_oversized_json(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    database, session_id, run, _repository, service = _setup(tmp_path)
    app = create_app(
        settings=AppSettings(home=tmp_path / "synthetic-guided-denial"),
        database=database,
        api_token=TOKEN,
        requirement_plan_evidence_service=service,
        user_presence_confirmation=None,
    )
    base = f"/v1/sessions/{session_id}/requirement-plan-evidence"
    marker = b"synthetic-guided-body-must-not-be-reflected"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        token_only = client.post(
            f"{base}/guided-authoring/review",
            headers={API_TOKEN_HEADER: TOKEN},
            json={
                "expected_source_run_id": run.run_id,
                "source_window_fingerprint": "3" * 64,
                "manifest_fingerprint": "4" * 64,
                "expected_predecessor_confirmation_id": None,
                "confirmation": "open_exact_local_requirement_plan_guided_authoring",
            },
        )
        oversized = client.post(
            f"{base}/guided-authoring/proposals",
            headers={
                API_TOKEN_HEADER: TOKEN,
                "Content-Type": "application/json",
                "Idempotency-Key": "guided-authoring-body-limit-0001",
            },
            content=b'{' + marker + b" " * (64 * 1024),
        )

    assert token_only.status_code == 403
    assert oversized.status_code == 413
    assert marker.decode("ascii") not in oversized.text
