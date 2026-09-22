"""Offline update recovery contract; every identity here is fictional."""

from __future__ import annotations

import itertools
import json
from typing import cast

import pytest

from prompt_enhancer.application.updates.recovery_plan import (
    ABSENT_ROLLBACK_RECEIPT,
    UNKNOWN_IDENTITY,
    UPDATE_RECOVERY_EVIDENCE_VERSION,
    UPDATE_RECOVERY_PLAN_CONTRACT_VERSION,
    EvidenceTrust,
    IdentityEvidence,
    PhaseEvidence,
    RecoveryOutcome,
    RecoveryReason,
    RollbackReadiness,
    RollbackReceipt,
    RollbackReceiptState,
    UpdateOperationRef,
    UpdatePhase,
    UpdateRecoveryEvidence,
    UpdateRecoveryEvidenceRejected,
    UpdateRecoveryPlan,
    plan_update_recovery,
)

_PREVIOUS = IdentityEvidence(trust=EvidenceTrust.AUTHENTICATED,
                             release_version="1.4.2",
                             artifact_sha256="a" * 64)
_TARGET = IdentityEvidence(trust=EvidenceTrust.AUTHENTICATED,
                           release_version="1.5.0",
                           artifact_sha256="b" * 64)
_FOREIGN = IdentityEvidence(trust=EvidenceTrust.AUTHENTICATED,
                            release_version="2.0.0",
                            artifact_sha256="c" * 64)
_TARGET_VERSION_ONLY = IdentityEvidence(trust=EvidenceTrust.UNVERIFIED,
                                        release_version="1.5.0")
_RESTAMPED_TARGET = IdentityEvidence(trust=EvidenceTrust.AUTHENTICATED,
                                     release_version="1.5.0",
                                     artifact_sha256="d" * 64)

_OPERATION = UpdateOperationRef(operation_id="0" * 32, attempt=1)
_RETRY = UpdateOperationRef(operation_id="0" * 32, attempt=2)
_OTHER_OPERATION = UpdateOperationRef(operation_id="1" * 32, attempt=1)


def _receipt(
    identity: IdentityEvidence = _PREVIOUS,
    *,
    operation: UpdateOperationRef = _OPERATION,
    state: RollbackReceiptState = RollbackReceiptState.CONFIRMED,
) -> RollbackReceipt:
    return RollbackReceipt(state=state,
                           operation=operation,
                           release_version=identity.release_version,
                           artifact_sha256=identity.artifact_sha256)


def _evidence(
    *,
    recorded: UpdatePhase,
    observed: UpdatePhase | None = None,
    operation: UpdateOperationRef = _OPERATION,
    observed_operation: UpdateOperationRef | None = None,
    running: IdentityEvidence = UNKNOWN_IDENTITY,
    target: IdentityEvidence = _TARGET,
    previous: IdentityEvidence = _PREVIOUS,
    receipt: RollbackReceipt = ABSENT_ROLLBACK_RECEIPT,
) -> UpdateRecoveryEvidence:
    return UpdateRecoveryEvidence(
        recorded=PhaseEvidence(operation=operation, phase=recorded),
        observed=PhaseEvidence(
            operation=operation
            if observed_operation is None else observed_operation,
            phase=recorded if observed is None else observed),
        running=running,
        target=target,
        previous=previous,
        rollback_receipt=receipt,
    )


def test_plan_declares_schema_provenance_and_never_executes_recovery() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.IDLE, running=_PREVIOUS))

    assert plan.contract_version == UPDATE_RECOVERY_PLAN_CONTRACT_VERSION
    assert plan.evidence_version == UPDATE_RECOVERY_EVIDENCE_VERSION
    assert plan.schema_version == 2
    assert plan.performs_recovery is False
    assert plan.outcome is RecoveryOutcome.NO_ACTION


def test_plan_makes_no_blanket_privacy_claim() -> None:
    """Versions, digests and operation identity stay sensitive local metadata."""

    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.INSTALL_STARTED, receipt=_receipt()))
    projection = plan.model_dump(mode="json")

    assert "contains_private_data" not in projection
    assert not any(field.startswith("contains_") for field in projection)
    assert plan.rollback_identity == _PREVIOUS


def test_plan_projection_contains_no_paths_commands_or_urls() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.INSTALL_STARTED, receipt=_receipt()))
    rendered = json.dumps(plan.model_dump(mode="json"))

    assert plan.rollback is RollbackReadiness.OWNER_REVIEW_REQUIRED
    for forbidden in ("/", "\\", "http", "://", ".msix", ".exe", "Traceback",
                      "Error"):
        assert forbidden not in rendered


def test_idle_authenticated_current_release_needs_no_action() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.IDLE, running=_PREVIOUS))

    assert plan.outcome is RecoveryOutcome.NO_ACTION
    assert plan.reason is RecoveryReason.NOTHING_INTERRUPTED
    assert plan.rollback is RollbackReadiness.NOT_APPLICABLE
    assert plan.rollback_identity is None
    assert plan.requires_owner_review is False


def test_idle_authenticated_new_release_reports_a_settled_update() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.IDLE,
                  running=_TARGET,
                  receipt=_receipt()))

    assert plan.outcome is RecoveryOutcome.NO_ACTION
    assert plan.reason is RecoveryReason.UPDATE_SETTLED
    assert plan.rollback is RollbackReadiness.NOT_APPLICABLE


def test_uncorroborated_pre_install_phase_requires_owner_review() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.REVIEWED,
                  observed=UpdatePhase.STAGED,
                  running=_PREVIOUS))

    assert plan.outcome is RecoveryOutcome.MANUAL_REVIEW
    assert plan.reason is RecoveryReason.INTERRUPTED_BEFORE_INSTALL
    assert plan.rollback is RollbackReadiness.NOT_APPLICABLE


def test_corroborated_staging_reports_no_installation_change() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.STAGED, running=_PREVIOUS))

    assert plan.outcome is RecoveryOutcome.NO_ACTION
    assert plan.reason is RecoveryReason.NOTHING_INTERRUPTED


def test_new_release_running_before_install_is_out_of_order() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.REVIEWED, running=_TARGET))

    assert plan.outcome is RecoveryOutcome.BLOCKED
    assert plan.reason is RecoveryReason.PHASE_OUT_OF_ORDER
    assert plan.rollback is RollbackReadiness.UNAVAILABLE


def test_shutdown_phase_never_settles_without_the_owner() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.SHUTDOWN_REQUESTED, running=_PREVIOUS))

    assert plan.outcome is RecoveryOutcome.MANUAL_REVIEW
    assert plan.reason is RecoveryReason.INTERRUPTED_BEFORE_INSTALL
    assert plan.requires_owner_review is True


def test_interrupted_install_with_unknown_identity_offers_reviewed_rollback(
) -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.INSTALL_STARTED,
                  running=UNKNOWN_IDENTITY,
                  receipt=_receipt()))

    assert plan.outcome is RecoveryOutcome.MANUAL_REVIEW
    assert plan.reason is RecoveryReason.IDENTITY_UNKNOWN
    assert plan.rollback is RollbackReadiness.OWNER_REVIEW_REQUIRED
    assert plan.rollback_identity == _PREVIOUS


def test_unauthenticated_running_identity_is_never_treated_as_known() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.INSTALL_STARTED,
                  running=_TARGET_VERSION_ONLY,
                  receipt=_receipt()))

    assert plan.outcome is RecoveryOutcome.MANUAL_REVIEW
    assert plan.reason is RecoveryReason.IDENTITY_UNAUTHENTICATED
    assert plan.rollback is RollbackReadiness.OWNER_REVIEW_REQUIRED


def test_rollback_candidate_requires_an_objective_receipt() -> None:
    for state in (RollbackReceiptState.ABSENT,
                  RollbackReceiptState.UNREADABLE):
        plan = plan_update_recovery(
            _evidence(recorded=UpdatePhase.INSTALL_STARTED,
                      receipt=RollbackReceipt(state=state)))
        assert plan.rollback is RollbackReadiness.UNAVAILABLE
        assert plan.rollback_identity is None


def test_rollback_candidate_requires_an_authenticated_previous_release(
) -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.INSTALL_STARTED,
                  previous=IdentityEvidence(trust=EvidenceTrust.UNVERIFIED,
                                            release_version="1.4.2")))

    assert plan.rollback is RollbackReadiness.UNAVAILABLE
    assert plan.rollback_identity is None


def test_confirmed_receipt_requires_an_authenticated_previous_release() -> None:
    for previous in (UNKNOWN_IDENTITY,
                     IdentityEvidence(trust=EvidenceTrust.UNVERIFIED,
                                      release_version="1.4.2")):
        with pytest.raises(ValueError):
            _evidence(recorded=UpdatePhase.INSTALL_STARTED,
                      previous=previous,
                      receipt=_receipt(_PREVIOUS))


def test_confirmed_receipt_requires_a_complete_binding() -> None:
    """A bare ``confirmed`` label is not a receipt; the binding is the evidence."""

    with pytest.raises(ValueError):
        RollbackReceipt(state=RollbackReceiptState.CONFIRMED)
    with pytest.raises(ValueError):
        RollbackReceipt(state=RollbackReceiptState.CONFIRMED,
                        release_version="1.4.2",
                        artifact_sha256="a" * 64)
    with pytest.raises(ValueError):
        RollbackReceipt(state=RollbackReceiptState.CONFIRMED,
                        operation=_OPERATION,
                        artifact_sha256="a" * 64)
    with pytest.raises(ValueError):
        RollbackReceipt(state=RollbackReceiptState.CONFIRMED,
                        operation=_OPERATION,
                        release_version="1.4.2")


def test_unread_receipt_cannot_carry_a_binding() -> None:
    for state in (RollbackReceiptState.ABSENT,
                  RollbackReceiptState.UNREADABLE):
        with pytest.raises(ValueError):
            RollbackReceipt(state=state, operation=_OPERATION)
        with pytest.raises(ValueError):
            RollbackReceipt(state=state, release_version="1.4.2")
        with pytest.raises(ValueError):
            RollbackReceipt(state=state, artifact_sha256="a" * 64)


def test_receipt_from_another_operation_never_nominates_a_candidate() -> None:
    """A receipt written for a different run is foreign evidence, not weaker proof."""

    for operation in (_OTHER_OPERATION, _RETRY):
        plan = plan_update_recovery(
            _evidence(recorded=UpdatePhase.INSTALL_STARTED,
                      running=UNKNOWN_IDENTITY,
                      receipt=_receipt(_PREVIOUS, operation=operation)))
        assert plan.outcome is RecoveryOutcome.BLOCKED
        assert plan.reason is RecoveryReason.RECEIPT_BINDING_MISMATCHED
        assert plan.rollback is RollbackReadiness.UNAVAILABLE
        assert plan.rollback_identity is None


def test_receipt_naming_another_release_never_nominates_a_candidate() -> None:
    partial_version = RollbackReceipt(state=RollbackReceiptState.CONFIRMED,
                                      operation=_OPERATION,
                                      release_version="1.4.2",
                                      artifact_sha256="f" * 64)
    partial_digest = RollbackReceipt(state=RollbackReceiptState.CONFIRMED,
                                     operation=_OPERATION,
                                     release_version="1.4.3",
                                     artifact_sha256="a" * 64)

    for receipt in (_receipt(_FOREIGN), partial_version, partial_digest):
        plan = plan_update_recovery(
            _evidence(recorded=UpdatePhase.INSTALL_STARTED,
                      running=UNKNOWN_IDENTITY,
                      receipt=receipt))
        assert plan.outcome is RecoveryOutcome.BLOCKED
        assert plan.reason is RecoveryReason.RECEIPT_BINDING_MISMATCHED
        assert plan.rollback_identity is None


def test_mismatched_receipt_blocks_even_with_a_complete_binding() -> None:
    for receipt in (RollbackReceipt(state=RollbackReceiptState.MISMATCHED),
                    _receipt(_PREVIOUS,
                             state=RollbackReceiptState.MISMATCHED)):
        plan = plan_update_recovery(
            _evidence(recorded=UpdatePhase.INSTALL_STARTED,
                      running=UNKNOWN_IDENTITY,
                      receipt=receipt))
        assert plan.outcome is RecoveryOutcome.BLOCKED
        assert plan.reason is RecoveryReason.RECEIPT_MISMATCHED
        assert plan.rollback is RollbackReadiness.UNAVAILABLE


def test_phase_observation_from_another_operation_settles_nothing() -> None:
    """Cross-run phase evidence can never report no_action or a settled update."""

    settling = (
        (UpdatePhase.IDLE, _PREVIOUS),
        (UpdatePhase.STAGED, _PREVIOUS),
        (UpdatePhase.IDLE, _TARGET),
        (UpdatePhase.INSTALL_SETTLED, _TARGET),
        (UpdatePhase.RELAUNCH_REQUESTED, _TARGET),
    )
    for phase, running in settling:
        settled = plan_update_recovery(
            _evidence(recorded=phase, running=running))
        assert settled.outcome is RecoveryOutcome.NO_ACTION

        for observed_operation in (_OTHER_OPERATION, _RETRY):
            plan = plan_update_recovery(
                _evidence(recorded=phase,
                          running=running,
                          observed_operation=observed_operation,
                          receipt=_receipt()))
            assert plan.outcome is RecoveryOutcome.BLOCKED
            assert plan.reason is RecoveryReason.OPERATION_BINDING_MISMATCHED
            assert plan.rollback is RollbackReadiness.UNAVAILABLE
            assert plan.rollback_identity is None


def test_install_interruption_on_either_known_release_stays_in_review() -> None:
    for running, rollback in ((_TARGET,
                               RollbackReadiness.OWNER_REVIEW_REQUIRED),
                              (_PREVIOUS, RollbackReadiness.NOT_APPLICABLE)):
        plan = plan_update_recovery(
            _evidence(recorded=UpdatePhase.INSTALL_STARTED,
                      running=running,
                      receipt=_receipt()))
        assert plan.outcome is RecoveryOutcome.MANUAL_REVIEW
        assert plan.reason is RecoveryReason.INTERRUPTED_DURING_INSTALL
        assert plan.rollback is rollback


def test_unexplained_running_release_is_blocked() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.INSTALL_STARTED, running=_FOREIGN))

    assert plan.outcome is RecoveryOutcome.BLOCKED
    assert plan.reason is RecoveryReason.IDENTITY_MISMATCHED


def test_missing_reference_evidence_is_incomplete_not_mismatched() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.INSTALL_STARTED,
                  running=_FOREIGN,
                  target=UNKNOWN_IDENTITY,
                  previous=UNKNOWN_IDENTITY))

    assert plan.outcome is RecoveryOutcome.MANUAL_REVIEW
    assert plan.reason is RecoveryReason.PHASE_EVIDENCE_INCOMPLETE
    assert plan.rollback is RollbackReadiness.UNAVAILABLE


def test_corroborated_settled_install_needs_no_action() -> None:
    for phase in (UpdatePhase.INSTALL_SETTLED, UpdatePhase.RELAUNCH_REQUESTED):
        plan = plan_update_recovery(_evidence(recorded=phase,
                                              running=_TARGET))
        assert plan.outcome is RecoveryOutcome.NO_ACTION
        assert plan.reason is RecoveryReason.UPDATE_SETTLED


def test_uncorroborated_settled_install_requires_review() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.RELAUNCH_REQUESTED,
                  observed=UpdatePhase.INSTALL_SETTLED,
                  running=_TARGET,
                  receipt=_receipt()))

    assert plan.outcome is RecoveryOutcome.MANUAL_REVIEW
    assert plan.reason is RecoveryReason.INTERRUPTED_AFTER_INSTALL
    assert plan.rollback is RollbackReadiness.OWNER_REVIEW_REQUIRED


def test_previous_release_after_a_recorded_install_is_not_a_proven_rollback(
) -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.INSTALL_SETTLED,
                  running=_PREVIOUS,
                  receipt=_receipt()))

    assert plan.outcome is RecoveryOutcome.BLOCKED
    assert plan.reason is RecoveryReason.PHASE_OUT_OF_ORDER
    assert plan.rollback is RollbackReadiness.UNAVAILABLE
    assert plan.rollback_identity is None


def test_observation_ahead_of_the_durable_record_is_blocked() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.STAGED,
                  observed=UpdatePhase.INSTALL_SETTLED,
                  running=_PREVIOUS))

    assert plan.outcome is RecoveryOutcome.BLOCKED
    assert plan.reason is RecoveryReason.PHASE_OUT_OF_ORDER


def test_restamped_release_digest_is_blocked_as_mismatched() -> None:
    plan = plan_update_recovery(
        _evidence(recorded=UpdatePhase.INSTALL_STARTED,
                  running=_RESTAMPED_TARGET))

    assert plan.outcome is RecoveryOutcome.BLOCKED
    assert plan.reason is RecoveryReason.IDENTITY_MISMATCHED


def test_target_that_is_not_newer_than_the_known_good_release_is_blocked(
) -> None:
    for target in (_PREVIOUS,
                   IdentityEvidence(trust=EvidenceTrust.AUTHENTICATED,
                                    release_version="1.0.0",
                                    artifact_sha256="e" * 64)):
        plan = plan_update_recovery(
            _evidence(recorded=UpdatePhase.INSTALL_STARTED,
                      running=UNKNOWN_IDENTITY,
                      target=target,
                      receipt=_receipt()))
        assert plan.outcome is RecoveryOutcome.BLOCKED
        assert plan.reason is RecoveryReason.RELEASE_ORDER_INVALID


def test_identity_evidence_rejects_incoherent_trust() -> None:
    with pytest.raises(ValueError):
        IdentityEvidence(trust=EvidenceTrust.AUTHENTICATED,
                         release_version="1.5.0")
    with pytest.raises(ValueError):
        IdentityEvidence(trust=EvidenceTrust.AUTHENTICATED,
                         artifact_sha256="b" * 64)
    with pytest.raises(ValueError):
        IdentityEvidence(trust=EvidenceTrust.UNKNOWN, release_version="1.5.0")
    with pytest.raises(ValueError):
        IdentityEvidence(trust=EvidenceTrust.UNVERIFIED)


def test_identity_evidence_rejects_malformed_release_identity() -> None:
    with pytest.raises(ValueError):
        IdentityEvidence(trust=EvidenceTrust.UNVERIFIED,
                         release_version="1.5")
    with pytest.raises(ValueError):
        IdentityEvidence(trust=EvidenceTrust.UNVERIFIED,
                         release_version="1.5.0-beta")
    with pytest.raises(ValueError):
        IdentityEvidence(trust=EvidenceTrust.UNVERIFIED,
                         artifact_sha256="A" * 64)
    with pytest.raises(ValueError):
        IdentityEvidence(trust=EvidenceTrust.UNVERIFIED,
                         artifact_sha256="b" * 63)


def test_operation_reference_is_bounded_and_opaque() -> None:
    with pytest.raises(ValueError):
        UpdateOperationRef(operation_id="0" * 31, attempt=1)
    with pytest.raises(ValueError):
        UpdateOperationRef(operation_id="A" * 32, attempt=1)
    with pytest.raises(ValueError):
        UpdateOperationRef(operation_id="0" * 32, attempt=-1)
    with pytest.raises(ValueError):
        UpdateOperationRef(operation_id="0" * 32, attempt=4097)
    with pytest.raises(ValueError):
        UpdateOperationRef(operation_id="0" * 32, attempt=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        UpdateOperationRef(operation_id="0" * 32)  # type: ignore[call-arg]


def test_phase_evidence_requires_its_operation_binding() -> None:
    with pytest.raises(ValueError):
        PhaseEvidence(phase=UpdatePhase.IDLE)  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        UpdateRecoveryEvidence(  # type: ignore[call-arg]
            recorded=PhaseEvidence(operation=_OPERATION,
                                   phase=UpdatePhase.IDLE))


def test_evidence_schema_is_closed_and_version_pinned() -> None:
    idle = PhaseEvidence(operation=_OPERATION, phase=UpdatePhase.IDLE)
    with pytest.raises(ValueError):
        UpdateRecoveryEvidence(recorded=idle,
                               observed=idle,
                               update_root="anything")  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        UpdateRecoveryEvidence(schema_version=1,  # type: ignore[arg-type]
                               recorded=idle,
                               observed=idle)
    with pytest.raises(ValueError):
        UpdateRecoveryEvidence(schema_version=True,  # type: ignore[arg-type]
                               recorded=idle,
                               observed=idle)
    with pytest.raises(ValueError):
        UpdateRecoveryEvidence(
            evidence_version="update-recovery-evidence.v1",  # type: ignore[arg-type]
            recorded=idle,
            observed=idle)
    with pytest.raises(ValueError):
        UpdateRecoveryEvidence(
            recorded=PhaseEvidence(operation=_OPERATION,
                                   phase="installing"),  # type: ignore[arg-type]
            observed=idle)


def test_planner_refuses_tampered_evidence_without_echoing_it() -> None:
    tampered = UpdateRecoveryEvidence.model_construct(
        schema_version=2,
        evidence_version=UPDATE_RECOVERY_EVIDENCE_VERSION,
        recorded=PhaseEvidence(operation=_OPERATION,
                               phase=UpdatePhase.INSTALL_STARTED),
        observed=PhaseEvidence(operation=_OPERATION,
                               phase=UpdatePhase.INSTALL_STARTED),
        running=IdentityEvidence.model_construct(
            trust=EvidenceTrust.AUTHENTICATED,
            release_version=None,
            artifact_sha256=None),
        target=_TARGET,
        previous=_PREVIOUS,
        rollback_receipt=_receipt(),
    )

    with pytest.raises(UpdateRecoveryEvidenceRejected) as rejected:
        plan_update_recovery(tampered)
    assert str(rejected.value) == "update_recovery_evidence_rejected"
    assert rejected.value.__cause__ is None


def test_planner_refuses_a_forged_receipt_without_a_known_good_identity(
) -> None:
    forged = UpdateRecoveryEvidence.model_construct(
        schema_version=2,
        evidence_version=UPDATE_RECOVERY_EVIDENCE_VERSION,
        recorded=PhaseEvidence(operation=_OPERATION,
                               phase=UpdatePhase.INSTALL_STARTED),
        observed=PhaseEvidence(operation=_OPERATION,
                               phase=UpdatePhase.INSTALL_STARTED),
        running=UNKNOWN_IDENTITY,
        target=_TARGET,
        previous=UNKNOWN_IDENTITY,
        rollback_receipt=_receipt(),
    )

    with pytest.raises(UpdateRecoveryEvidenceRejected):
        plan_update_recovery(forged)


def test_planner_refuses_a_forged_receipt_without_a_binding() -> None:
    forged = UpdateRecoveryEvidence.model_construct(
        schema_version=2,
        evidence_version=UPDATE_RECOVERY_EVIDENCE_VERSION,
        recorded=PhaseEvidence(operation=_OPERATION,
                               phase=UpdatePhase.INSTALL_STARTED),
        observed=PhaseEvidence(operation=_OPERATION,
                               phase=UpdatePhase.INSTALL_STARTED),
        running=UNKNOWN_IDENTITY,
        target=_TARGET,
        previous=_PREVIOUS,
        rollback_receipt=RollbackReceipt.model_construct(
            state=RollbackReceiptState.CONFIRMED,
            operation=None,
            release_version=None,
            artifact_sha256=None),
    )

    with pytest.raises(UpdateRecoveryEvidenceRejected):
        plan_update_recovery(forged)


def test_planner_refuses_untyped_evidence() -> None:
    with pytest.raises(UpdateRecoveryEvidenceRejected):
        plan_update_recovery(
            cast(UpdateRecoveryEvidence, {
                "recorded": {
                    "phase": "idle"
                },
                "observed": {
                    "phase": "idle"
                }
            }))


def _phase(phase: UpdatePhase,
           operation: UpdateOperationRef = _OPERATION) -> PhaseEvidence:
    return PhaseEvidence(operation=operation, phase=phase)


def _plan_fields(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "outcome": RecoveryOutcome.MANUAL_REVIEW,
        "reason": RecoveryReason.INTERRUPTED_DURING_INSTALL,
        "recorded": _phase(UpdatePhase.INSTALL_STARTED),
        "observed": _phase(UpdatePhase.INSTALL_STARTED),
        "rollback": RollbackReadiness.UNAVAILABLE,
        "rollback_identity": None,
        "requires_owner_review": True,
    }
    fields.update(overrides)
    return fields


def test_plan_schema_refuses_unsupported_outcome_combinations() -> None:
    assert UpdateRecoveryPlan(**_plan_fields()).requires_owner_review is True
    with pytest.raises(ValueError):
        UpdateRecoveryPlan(**_plan_fields(
            outcome=RecoveryOutcome.NO_ACTION,
            reason=RecoveryReason.NOTHING_INTERRUPTED,
            rollback=RollbackReadiness.NOT_APPLICABLE))
    with pytest.raises(ValueError):
        UpdateRecoveryPlan(**_plan_fields(
            outcome=RecoveryOutcome.NO_ACTION,
            reason=RecoveryReason.INTERRUPTED_DURING_INSTALL,
            rollback=RollbackReadiness.NOT_APPLICABLE,
            requires_owner_review=False))
    with pytest.raises(ValueError):
        UpdateRecoveryPlan(**_plan_fields(
            reason=RecoveryReason.PHASE_OUT_OF_ORDER))
    with pytest.raises(ValueError):
        UpdateRecoveryPlan(**_plan_fields(
            outcome=RecoveryOutcome.BLOCKED,
            reason=RecoveryReason.IDENTITY_MISMATCHED,
            rollback=RollbackReadiness.NOT_APPLICABLE))


def test_plan_schema_refuses_unsupported_rollback_claims() -> None:
    with pytest.raises(ValueError):
        UpdateRecoveryPlan(**_plan_fields(
            rollback=RollbackReadiness.OWNER_REVIEW_REQUIRED))
    with pytest.raises(ValueError):
        UpdateRecoveryPlan(**_plan_fields(rollback_identity=_PREVIOUS))
    with pytest.raises(ValueError):
        UpdateRecoveryPlan(**_plan_fields(
            rollback=RollbackReadiness.OWNER_REVIEW_REQUIRED,
            rollback_identity=_TARGET_VERSION_ONLY))
    with pytest.raises(ValueError):
        UpdateRecoveryPlan(**_plan_fields(
            outcome=RecoveryOutcome.BLOCKED,
            reason=RecoveryReason.PHASE_OUT_OF_ORDER,
            rollback=RollbackReadiness.OWNER_REVIEW_REQUIRED,
            rollback_identity=_PREVIOUS))


def test_plan_schema_refuses_uncorroborated_phase_order() -> None:
    with pytest.raises(ValueError):
        UpdateRecoveryPlan(**_plan_fields(
            recorded=_phase(UpdatePhase.STAGED),
            observed=_phase(UpdatePhase.INSTALL_SETTLED)))
    blocked = UpdateRecoveryPlan(**_plan_fields(
        outcome=RecoveryOutcome.BLOCKED,
        reason=RecoveryReason.PHASE_OUT_OF_ORDER,
        recorded=_phase(UpdatePhase.STAGED),
        observed=_phase(UpdatePhase.INSTALL_SETTLED)))
    assert blocked.rollback is RollbackReadiness.UNAVAILABLE
    with pytest.raises(ValueError):
        UpdateRecoveryPlan(**_plan_fields(installer="anything"))


def test_plan_schema_requires_phase_evidence_from_one_operation() -> None:
    """Two operations may only be reported as an unbound observation."""

    for operation in (_OTHER_OPERATION, _RETRY):
        with pytest.raises(ValueError):
            UpdateRecoveryPlan(**_plan_fields(
                observed=_phase(UpdatePhase.INSTALL_STARTED, operation)))
        unbound = UpdateRecoveryPlan(**_plan_fields(
            outcome=RecoveryOutcome.BLOCKED,
            reason=RecoveryReason.OPERATION_BINDING_MISMATCHED,
            observed=_phase(UpdatePhase.INSTALL_STARTED, operation)))
        assert unbound.rollback is RollbackReadiness.UNAVAILABLE
        assert unbound.rollback_identity is None
    with pytest.raises(ValueError):
        UpdateRecoveryPlan(**_plan_fields(
            outcome=RecoveryOutcome.BLOCKED,
            reason=RecoveryReason.OPERATION_BINDING_MISMATCHED))


def test_each_reason_belongs_to_exactly_one_outcome() -> None:
    for reason in RecoveryReason:
        unbound = reason is RecoveryReason.OPERATION_BINDING_MISMATCHED
        accepted: set[RecoveryOutcome] = set()
        for outcome in RecoveryOutcome:
            settled = outcome is RecoveryOutcome.NO_ACTION
            try:
                UpdateRecoveryPlan(**_plan_fields(
                    outcome=outcome,
                    reason=reason,
                    observed=_phase(
                        UpdatePhase.INSTALL_STARTED,
                        _OTHER_OPERATION if unbound else _OPERATION),
                    rollback=(RollbackReadiness.NOT_APPLICABLE if settled else
                              RollbackReadiness.UNAVAILABLE),
                    requires_owner_review=not settled))
            except ValueError:
                continue
            accepted.add(outcome)
        assert len(accepted) == 1, reason


_RUNNING_OPTIONS = (UNKNOWN_IDENTITY, _TARGET_VERSION_ONLY, _PREVIOUS,
                    _TARGET, _FOREIGN)
_TARGET_OPTIONS = (UNKNOWN_IDENTITY, _TARGET)
_PREVIOUS_OPTIONS = (UNKNOWN_IDENTITY, _PREVIOUS, _TARGET)


def _receipt_options(previous: IdentityEvidence) -> tuple[RollbackReceipt, ...]:
    """Every receipt the evidence schema accepts for this previous identity."""

    options = [
        ABSENT_ROLLBACK_RECEIPT,
        RollbackReceipt(state=RollbackReceiptState.UNREADABLE),
        RollbackReceipt(state=RollbackReceiptState.MISMATCHED),
        _receipt(_PREVIOUS, state=RollbackReceiptState.MISMATCHED),
    ]
    if previous.trust is EvidenceTrust.AUTHENTICATED:
        options.extend((
            _receipt(previous),
            _receipt(previous, operation=_OTHER_OPERATION),
            _receipt(previous, operation=_RETRY),
            _receipt(_FOREIGN),
        ))
    return tuple(options)


def _assert_conservative(plan: UpdateRecoveryPlan,
                         evidence: UpdateRecoveryEvidence) -> None:
    previous, receipt = evidence.previous, evidence.rollback_receipt

    assert plan == plan_update_recovery(evidence)
    assert plan == UpdateRecoveryPlan.model_validate(
        plan.model_dump(mode="json"))
    assert plan.recorded == evidence.recorded
    assert plan.observed == evidence.observed
    assert plan.performs_recovery is False
    assert plan.requires_owner_review is (plan.outcome
                                          is not RecoveryOutcome.NO_ACTION)

    if plan.rollback is RollbackReadiness.OWNER_REVIEW_REQUIRED:
        assert plan.outcome is RecoveryOutcome.MANUAL_REVIEW
        assert previous.trust is EvidenceTrust.AUTHENTICATED
        assert receipt.state is RollbackReceiptState.CONFIRMED
        assert receipt.operation == evidence.recorded.operation
        assert receipt.release_version == previous.release_version
        assert receipt.artifact_sha256 == previous.artifact_sha256
        assert plan.rollback_identity == previous
    else:
        assert plan.rollback_identity is None

    if plan.outcome is RecoveryOutcome.NO_ACTION:
        assert evidence.recorded.operation == evidence.observed.operation
        assert evidence.recorded.phase is evidence.observed.phase
        assert evidence.running.trust is EvidenceTrust.AUTHENTICATED
        assert evidence.running in {evidence.target, previous}
        assert receipt.state is not RollbackReceiptState.MISMATCHED
        assert plan.rollback is RollbackReadiness.NOT_APPLICABLE
    if plan.outcome is RecoveryOutcome.BLOCKED:
        assert plan.rollback is RollbackReadiness.UNAVAILABLE


def test_every_phase_transition_and_receipt_binding_stays_conservative(
) -> None:
    outcomes: set[RecoveryOutcome] = set()
    reasons: set[RecoveryReason] = set()
    combinations = itertools.product(UpdatePhase, UpdatePhase,
                                     _RUNNING_OPTIONS, _TARGET_OPTIONS,
                                     _PREVIOUS_OPTIONS)

    for recorded, observed, running, target, previous in combinations:
        for receipt in _receipt_options(previous):
            evidence = _evidence(recorded=recorded,
                                 observed=observed,
                                 running=running,
                                 target=target,
                                 previous=previous,
                                 receipt=receipt)
            plan = plan_update_recovery(evidence)
            outcomes.add(plan.outcome)
            reasons.add(plan.reason)
            _assert_conservative(plan, evidence)

            if list(UpdatePhase).index(observed) > list(UpdatePhase).index(
                    recorded):
                assert plan.outcome is RecoveryOutcome.BLOCKED
                assert plan.reason is RecoveryReason.PHASE_OUT_OF_ORDER

    assert outcomes == set(RecoveryOutcome)
    assert reasons == set(RecoveryReason) - {
        RecoveryReason.OPERATION_BINDING_MISMATCHED
    }


def test_every_cross_operation_observation_is_blocked_as_unbound() -> None:
    combinations = itertools.product(UpdatePhase, UpdatePhase,
                                     _RUNNING_OPTIONS,
                                     (_OTHER_OPERATION, _RETRY))

    for recorded, observed, running, observed_operation in combinations:
        evidence = _evidence(recorded=recorded,
                             observed=observed,
                             running=running,
                             observed_operation=observed_operation,
                             receipt=_receipt())
        plan = plan_update_recovery(evidence)

        assert plan.outcome is RecoveryOutcome.BLOCKED
        assert plan.reason is RecoveryReason.OPERATION_BINDING_MISMATCHED
        assert plan.rollback is RollbackReadiness.UNAVAILABLE
        _assert_conservative(plan, evidence)
