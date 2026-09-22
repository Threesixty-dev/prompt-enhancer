"""Synthetic current-context review and SQLite issuance proof for observed checks.

This starts at an already sealed synthetic source context.  Provider-ingress
binding is covered independently by the CP34a Codex content-source tests.
"""
from __future__ import annotations

from datetime import timedelta
import sqlite3

import pytest
from pydantic import SecretStr

from prompt_enhancer.application.analysis.requirement_plan_evidence import (
    SealedRunRequirementPlanSource,
)
from prompt_enhancer.application.analysis.requirement_verification_evidence import (
    RequirementVerificationMethod, RequirementVerificationOutcome,
)
from prompt_enhancer.application.analysis.requirement_verification_persistence import (
    ObservedCheckResultIssueCommand, RequirementVerificationEvidenceService,
    RequirementVerificationConflictError,
)
from prompt_enhancer.application.analysis.requirement_verification_review import (
    RequirementVerificationReviewService,
)
from prompt_enhancer.application.analysis.text_contracts import (
    ACTION_REVIEW_DESCRIPTOR_ALGORITHM_VERSION,
    OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION, EphemeralRedactedActionDescriptor,
    EventKind,
)
from prompt_enhancer.application.verification.observed_check_completion import (
    EphemeralObservedCheckCompletion, ObservedCheckOutcome,
)
from prompt_enhancer.domain import Provider
from prompt_enhancer.database import Database

from test_model_ensemble_r5_profile_persistence import NOW
from test_requirement_plan_evidence_persistence import (
    ARTIFACT_IDS, _confirm, _import, _setup,
)


def _id(label: str) -> str:
    return ARTIFACT_IDS.fingerprint("synthetic-observed-check-e2e-v1", (label,))


@pytest.mark.parametrize(
    ("exit_code", "expected"),
    ((0, RequirementVerificationOutcome.PASSED), (1, RequirementVerificationOutcome.FAILED)),
)
def test_current_source_review_then_issue_persists_one_observed_pytest_result(
    tmp_path, exit_code: int, expected: RequirementVerificationOutcome,
) -> None:
    database, session_id, run, _repository, plan_service = _setup(tmp_path)
    contexts = plan_service._review_contexts  # type: ignore[attr-defined]
    original = contexts._entries[run.run_id].context  # type: ignore[attr-defined]
    source_reference_id = _id(f"source-{exit_code}")
    completion = EphemeralObservedCheckCompletion(
        provider=Provider.CODEX,
        source_reference_id=source_reference_id,
        observed_sequence=41,
        check_kind="test",
        outcome=(ObservedCheckOutcome.PASSED if exit_code == 0 else ObservedCheckOutcome.CHECK_FAILED),
        provider_execution_status="completed",
        exit_code=exit_code,
        classifier_version="local-command-rules-v1",
        normalizer_version="strict-shell-free-v2",
        rule_id="test.pytest",
    )
    context = original.model_copy(update={
        "action_descriptor_algorithm_version": ACTION_REVIEW_DESCRIPTOR_ALGORITHM_VERSION,
        "action_descriptor_extraction_complete": True,
        "action_descriptors": (EphemeralRedactedActionDescriptor(
            source_reference_id=source_reference_id,
            event_kind=EventKind.TOOL_END,
            tool_name=SecretStr("commandExecution"),
            invocation_preview=SecretStr("pytest -q"),
            result_or_effect_preview=SecretStr("completed"),
            invocation_truncated=False,
            result_or_effect_truncated=False,
            redactor_version=original.redactor_version,
        ),),
        "observed_check_completion_schema_version": OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION,
        "observed_check_completions": (completion,),
    })
    # Do not rely on ``model_copy``'s intentionally unvalidated update path.
    context = type(context).model_validate(context.model_dump(mode="python"))
    contexts.publish(run.run_id, context)
    confirmed = _confirm(
        plan_service, session_id, run,
        _import(plan_service, session_id, run, suffix=f"observed-{exit_code}"),
        suffix=f"observed-{exit_code}",
    )
    assert confirmed.decision is not None
    review_service = RequirementVerificationReviewService(
        database.requirement_verification_evidence_repository(),
        database.requirement_verification_current_plan_authority(),
        SealedRunRequirementPlanSource(database.model_ensemble_repository(), contexts),
        contexts,
        clock=lambda: NOW + timedelta(minutes=2),
        monotonic_clock=lambda: 200.0,
        token_factory=lambda: _id(f"receipt-{exit_code}"),
        manifest_key=b"o" * 32,
    )
    service = RequirementVerificationEvidenceService(
        database.requirement_verification_evidence_repository(),
        database.requirement_verification_current_plan_authority(),
        ARTIFACT_IDS,
        review_service=review_service,
        clock=lambda: NOW + timedelta(minutes=2),
    )
    snapshot, created = service.issue_current_opportunities(session_id)
    assert created is True
    opportunity = snapshot.evidence.opportunities.opportunities[0]
    manifest = review_service.observed_candidates(
        session_id=session_id,
        opportunity_set_fingerprint=snapshot.evidence.opportunities.opportunity_set_fingerprint,
        opportunity_id=opportunity.opportunity_id,
        expected_source_run_id=run.run_id,
        through_revision=0,
        expected_predecessor_authority_id=None,
    )
    review = review_service.open_observed_check(
        session_id=session_id,
        opportunity_set_fingerprint=manifest.opportunity_set_fingerprint,
        opportunity_id=manifest.opportunity_id,
        candidate_id=source_reference_id,
        expected_source_run_id=run.run_id,
        through_revision=0,
        expected_predecessor_authority_id=None,
        candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
    )
    command = ObservedCheckResultIssueCommand(
        opportunity_set_fingerprint=manifest.opportunity_set_fingerprint,
        opportunity_id=manifest.opportunity_id,
        candidate_id=source_reference_id,
        expected_source_run_id=run.run_id,
        source_window_fingerprint=manifest.source_window_fingerprint,
        through_revision=0,
        candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
        review_receipt_id=review.review_receipt_id,
        review_fingerprint=review.review_fingerprint,
        full_criterion_coverage_acknowledged=True,
        confirmation="issue_exact_local_requirement_observed_check_result",
    )
    persisted, applied = service.append_observed_check_result(
        session_id=session_id, command=command,
        idempotency_key=f"synthetic-observed-check-e2e-{exit_code}-0001",
    )
    assert applied is True
    result = persisted.evidence.verification_results[0]
    assert result.outcome is expected
    assert result.method is RequirementVerificationMethod.TEST
    assert result.observed_sequence == 41
    assert source_reference_id in result.receipt_reference_ids
    provenance = service.observed_check_provenance(session_id, result.result_id)
    assert provenance.authority_record_id == result.result_id
    assert provenance.source_reference_id == source_reference_id
    assert provenance.observed_sequence == 41
    assert provenance.exit_code == exit_code
    assert provenance.observed_outcome == (
        "passed" if exit_code == 0 else "check_failed"
    )
    assert provenance.full_criterion_coverage_acknowledged is True
    assert provenance.content_persisted is False
    replayed, replayed_applied = service.append_observed_check_result(
        session_id=session_id, command=command,
        idempotency_key=f"synthetic-observed-check-e2e-{exit_code}-0001",
    )
    assert replayed == persisted and replayed_applied is False
    # A normal SQLite update is refused by M65.  This synthetic trigger removal
    # models offline corruption and proves a restarted reader verifies the keyed
    # sidecar digest rather than trusting valid-shaped rows.
    with database._connection() as connection:  # type: ignore[attr-defined]
        connection.execute(
            "DROP TRIGGER requirement_verification_observed_check_provenance_no_update"
        )
        connection.execute(
            "UPDATE requirement_verification_observed_check_provenance "
            "SET candidate_manifest_fingerprint=? WHERE authority_record_id=?",
            (_id(f"tampered-manifest-{exit_code}"), result.result_id),
        )
        connection.commit()
    restarted = Database(database.path)
    restarted.configure_local_artifact_id_factory(ARTIFACT_IDS)
    restarted_service = RequirementVerificationEvidenceService(
        restarted.requirement_verification_evidence_repository(),
        restarted.requirement_verification_current_plan_authority(),
        ARTIFACT_IDS,
    )
    with pytest.raises(RequirementVerificationConflictError):
        restarted_service.observed_check_provenance(session_id, result.result_id)
    with database._connection() as connection:  # type: ignore[attr-defined]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM requirement_verification_observed_check_provenance "
                "WHERE authority_record_id=?",
                (result.result_id,),
            )
        connection.rollback()
    # Exercise the production source-run privacy path, not only a raw fixture
    # delete: every run for this session is erased atomically.
    assert database.model_ensemble_repository().delete_for_privacy(run.run_id) is True
    with database._connection(readonly=True) as connection:  # type: ignore[attr-defined]
        assert connection.execute(
            "SELECT COUNT(*) FROM requirement_verification_observed_check_provenance"
        ).fetchone()[0] == 0
