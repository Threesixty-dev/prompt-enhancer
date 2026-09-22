"""Offline, non-executing reconciliation contract for interrupted updates.

This module only classifies evidence about an interrupted future update phase.
It never installs, rolls back, relaunches, reads the filesystem, or names a
path, command, URL or raw error.

Every field here is a caller-supplied claim.  The planner only checks that
those claims agree with each other and with the one operation attempt they
name, so a verdict is an internal evidence-consistency statement and nothing
more: a receipt state authenticates no receipt, an ``authenticated`` trust
label proves no signature was checked, and no verdict is evidence that a
release is genuine or that a usable rollback artifact exists.

A previous release becomes a rollback candidate only when its identity is
authenticated *and* a typed receipt binds the exact previous version and
digest to the exact interrupted operation attempt; anything less keeps the
candidate unavailable.  Even a bound candidate only asks for owner review; it
never claims that a rollback happened, is possible, or would succeed.
"""

from __future__ import annotations

from enum import Enum, StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ...domain import StrictModel

UPDATE_RECOVERY_EVIDENCE_VERSION = "update-recovery-evidence.v2"
UPDATE_RECOVERY_PLAN_CONTRACT_VERSION = "update-recovery-plan.v2"

_RELEASE_VERSION = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
_OPERATION_ID = r"^[0-9a-f]{32}$"
_MAX_ATTEMPT = 4096


class UpdateRecoveryEvidenceRejected(ValueError):
    """Content-free refusal; the offending evidence is never echoed."""

    def __init__(self) -> None:
        super().__init__("update_recovery_evidence_rejected")


class UpdatePhase(StrEnum):
    """Ordered phases a future apply/relaunch/rollback slice may record."""

    IDLE = "idle"
    STAGED = "staged"
    REVIEWED = "reviewed"
    SHUTDOWN_REQUESTED = "shutdown_requested"
    INSTALL_STARTED = "install_started"
    INSTALL_SETTLED = "install_settled"
    RELAUNCH_REQUESTED = "relaunch_requested"


_PHASE_ORDER: dict[UpdatePhase, int] = {
    phase: index
    for index, phase in enumerate(UpdatePhase)
}
_PRE_INSTALL_PHASES = frozenset({
    UpdatePhase.IDLE,
    UpdatePhase.STAGED,
    UpdatePhase.REVIEWED,
})
_POST_INSTALL_PHASES = frozenset({
    UpdatePhase.INSTALL_SETTLED,
    UpdatePhase.RELAUNCH_REQUESTED,
})


class EvidenceTrust(StrEnum):
    """How a release identity was obtained.  Missing stays unknown."""

    UNKNOWN = "unknown"
    UNVERIFIED = "unverified"
    AUTHENTICATED = "authenticated"


class RollbackReceiptState(StrEnum):
    """What a receipt reader reported.  The state alone binds nothing."""

    ABSENT = "absent"
    UNREADABLE = "unreadable"
    MISMATCHED = "mismatched"
    CONFIRMED = "confirmed"


class UpdateOperationRef(StrictModel):
    """Bounded opaque identity of one update operation attempt.

    ``operation_id`` is a local correlation handle only.  It is never a path,
    command, URL, account, host or session identifier, it carries no
    authority, and it is used for exact equality alone: two pieces of evidence
    describe the same interrupted run only if they name the same handle and
    the same attempt.
    """

    operation_id: str = Field(pattern=_OPERATION_ID)
    attempt: int = Field(ge=0, le=_MAX_ATTEMPT, strict=True)


class IdentityEvidence(StrictModel):
    """A release identity plus the trust that produced it."""

    trust: EvidenceTrust
    release_version: str | None = Field(default=None,
                                        max_length=32,
                                        pattern=_RELEASE_VERSION)
    artifact_sha256: str | None = Field(default=None,
                                        pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity(self) -> IdentityEvidence:
        has_version = self.release_version is not None
        has_digest = self.artifact_sha256 is not None
        if self.trust is EvidenceTrust.AUTHENTICATED and not (has_version
                                                              and has_digest):
            raise ValueError(
                "authenticated identity requires version and digest evidence")
        if self.trust is EvidenceTrust.UNKNOWN and (has_version or has_digest):
            raise ValueError("unknown identity cannot carry evidence")
        if self.trust is EvidenceTrust.UNVERIFIED and not (has_version
                                                           or has_digest):
            raise ValueError("unverified identity requires observed evidence")
        return self


UNKNOWN_IDENTITY = IdentityEvidence(trust=EvidenceTrust.UNKNOWN)


class PhaseEvidence(StrictModel):
    """One phase claim tied to the exact operation attempt that produced it.

    A bare phase is not reconcilable evidence: a durable record from one run
    and an observation from another describe different histories, so both
    sides carry their own binding and the planner compares them.
    """

    operation: UpdateOperationRef
    phase: UpdatePhase


class RollbackReceipt(StrictModel):
    """Receipt evidence for the previous release, bound to one operation.

    A ``confirmed`` state must name the exact previous release version and
    digest and the exact operation attempt the receipt was written for.  The
    binding is what the planner checks; the state itself is a caller-supplied
    label and authenticates neither the receipt nor the release it names.
    """

    state: RollbackReceiptState = RollbackReceiptState.ABSENT
    operation: UpdateOperationRef | None = None
    release_version: str | None = Field(default=None,
                                        max_length=32,
                                        pattern=_RELEASE_VERSION)
    artifact_sha256: str | None = Field(default=None,
                                        pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_receipt(self) -> RollbackReceipt:
        bound = (self.operation is not None and self.release_version is not None
                 and self.artifact_sha256 is not None)
        if self.state is RollbackReceiptState.CONFIRMED and not bound:
            raise ValueError(
                "a confirmed receipt requires its operation and release binding"
            )
        unread = self.state in (RollbackReceiptState.ABSENT,
                                RollbackReceiptState.UNREADABLE)
        if unread and (self.operation is not None
                       or self.release_version is not None
                       or self.artifact_sha256 is not None):
            raise ValueError("an unread receipt cannot carry a binding")
        return self


ABSENT_ROLLBACK_RECEIPT = RollbackReceipt()


class UpdateRecoveryEvidence(StrictModel):
    """Everything the planner is allowed to know.  Absent fields stay unknown."""

    schema_version: Literal[2] = 2
    evidence_version: Literal["update-recovery-evidence.v2"] = (
        UPDATE_RECOVERY_EVIDENCE_VERSION)
    recorded: PhaseEvidence
    observed: PhaseEvidence
    running: IdentityEvidence = UNKNOWN_IDENTITY
    target: IdentityEvidence = UNKNOWN_IDENTITY
    previous: IdentityEvidence = UNKNOWN_IDENTITY
    rollback_receipt: RollbackReceipt = ABSENT_ROLLBACK_RECEIPT

    @field_validator("schema_version", mode="before")
    @classmethod
    def reject_boolean_integers(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("recovery schema version requires an integer")
        return value

    @model_validator(mode="after")
    def validate_evidence(self) -> UpdateRecoveryEvidence:
        if (self.rollback_receipt.state is RollbackReceiptState.CONFIRMED
                and self.previous.trust is not EvidenceTrust.AUTHENTICATED):
            raise ValueError(
                "a confirmed receipt requires an authenticated previous identity"
            )
        return self


class RecoveryOutcome(StrEnum):
    """The only outcomes this contract may produce."""

    NO_ACTION = "no_action"
    MANUAL_REVIEW = "manual_review"
    BLOCKED = "blocked"


class RecoveryReason(StrEnum):
    NOTHING_INTERRUPTED = "nothing_interrupted"
    UPDATE_SETTLED = "update_settled"
    INTERRUPTED_BEFORE_INSTALL = "interrupted_before_install"
    INTERRUPTED_DURING_INSTALL = "interrupted_during_install"
    INTERRUPTED_AFTER_INSTALL = "interrupted_after_install"
    IDENTITY_UNKNOWN = "identity_unknown"
    IDENTITY_UNAUTHENTICATED = "identity_unauthenticated"
    PHASE_EVIDENCE_INCOMPLETE = "phase_evidence_incomplete"
    IDENTITY_MISMATCHED = "identity_mismatched"
    OPERATION_BINDING_MISMATCHED = "operation_binding_mismatched"
    PHASE_OUT_OF_ORDER = "phase_out_of_order"
    RECEIPT_BINDING_MISMATCHED = "receipt_binding_mismatched"
    RECEIPT_MISMATCHED = "receipt_mismatched"
    RELEASE_ORDER_INVALID = "release_order_invalid"


_NO_ACTION_REASONS = frozenset({
    RecoveryReason.NOTHING_INTERRUPTED,
    RecoveryReason.UPDATE_SETTLED,
})
_REVIEW_REASONS = frozenset({
    RecoveryReason.INTERRUPTED_BEFORE_INSTALL,
    RecoveryReason.INTERRUPTED_DURING_INSTALL,
    RecoveryReason.INTERRUPTED_AFTER_INSTALL,
    RecoveryReason.IDENTITY_UNKNOWN,
    RecoveryReason.IDENTITY_UNAUTHENTICATED,
    RecoveryReason.PHASE_EVIDENCE_INCOMPLETE,
})
_BLOCKED_REASONS = frozenset({
    RecoveryReason.IDENTITY_MISMATCHED,
    RecoveryReason.OPERATION_BINDING_MISMATCHED,
    RecoveryReason.PHASE_OUT_OF_ORDER,
    RecoveryReason.RECEIPT_BINDING_MISMATCHED,
    RecoveryReason.RECEIPT_MISMATCHED,
    RecoveryReason.RELEASE_ORDER_INVALID,
})
# Phase order only means something inside one operation attempt; an unrelated
# observation is reported as unbound rather than as a corroborating history.
_UNORDERED_PHASE_REASONS = frozenset({
    RecoveryReason.OPERATION_BINDING_MISMATCHED,
    RecoveryReason.PHASE_OUT_OF_ORDER,
})


class RollbackReadiness(StrEnum):
    """Rollback is never reported as done, available or guaranteed."""

    NOT_APPLICABLE = "not_applicable"
    UNAVAILABLE = "unavailable"
    OWNER_REVIEW_REQUIRED = "owner_review_required"


class UpdateRecoveryPlan(StrictModel):
    """Reconciliation result for one interrupted update operation attempt.

    The verdict carries reason codes, the bound phase evidence it was derived
    from, and a rollback candidate identity only when a receipt binds one.  It
    holds no raw content, path, command, URL or error, but it makes no claim
    to be publishable: local installation metadata such as release versions,
    artifact digests and operation identity can be sensitive, and excluding
    raw content is not permission to treat this verdict as public data.
    """

    contract_version: Literal["update-recovery-plan.v2"] = (
        UPDATE_RECOVERY_PLAN_CONTRACT_VERSION)
    evidence_version: Literal["update-recovery-evidence.v2"] = (
        UPDATE_RECOVERY_EVIDENCE_VERSION)
    schema_version: Literal[2] = 2
    performs_recovery: Literal[False] = False
    outcome: RecoveryOutcome
    reason: RecoveryReason
    recorded: PhaseEvidence
    observed: PhaseEvidence
    rollback: RollbackReadiness
    rollback_identity: IdentityEvidence | None = None
    requires_owner_review: bool

    @model_validator(mode="after")
    def validate_plan(self) -> UpdateRecoveryPlan:
        if self.outcome is RecoveryOutcome.NO_ACTION:
            if (self.reason not in _NO_ACTION_REASONS
                    or self.rollback is not RollbackReadiness.NOT_APPLICABLE
                    or self.requires_owner_review):
                raise ValueError("settled recovery plan is inconsistent")
        elif self.outcome is RecoveryOutcome.MANUAL_REVIEW:
            if self.reason not in _REVIEW_REASONS or not self.requires_owner_review:
                raise ValueError("review recovery plan is inconsistent")
        else:
            if (self.reason not in _BLOCKED_REASONS
                    or self.rollback is not RollbackReadiness.UNAVAILABLE
                    or not self.requires_owner_review):
                raise ValueError("blocked recovery plan is inconsistent")
        candidate = self.rollback is RollbackReadiness.OWNER_REVIEW_REQUIRED
        if candidate != (self.rollback_identity is not None):
            raise ValueError(
                "a reviewed rollback candidate requires its exact identity")
        if (self.rollback_identity is not None and
                self.rollback_identity.trust is not EvidenceTrust.AUTHENTICATED
            ):
            raise ValueError(
                "a rollback candidate requires an authenticated identity")
        unbound = self.recorded.operation != self.observed.operation
        if unbound != (self.reason
                       is RecoveryReason.OPERATION_BINDING_MISMATCHED):
            raise ValueError(
                "phase evidence from two operations must be reported as unbound"
            )
        if (_PHASE_ORDER[self.observed.phase] > _PHASE_ORDER[self.recorded.phase]
                and self.reason not in _UNORDERED_PHASE_REASONS):
            raise ValueError("uncorroborated phase order is inconsistent")
        return self


class _Match(Enum):
    UNKNOWN = "unknown"
    SAME = "same"
    DIFFERENT = "different"
    CONFLICT = "conflict"


def _compare(left: IdentityEvidence, right: IdentityEvidence) -> _Match:
    """Compare only authenticated identities; partial equality is a conflict."""

    if (left.trust is not EvidenceTrust.AUTHENTICATED
            or right.trust is not EvidenceTrust.AUTHENTICATED):
        return _Match.UNKNOWN
    same_version = left.release_version == right.release_version
    same_digest = left.artifact_sha256 == right.artifact_sha256
    if same_version and same_digest:
        return _Match.SAME
    if same_version or same_digest:
        return _Match.CONFLICT
    return _Match.DIFFERENT


def _version_tuple(value: str) -> tuple[int, int, int]:
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def _trust_reason(identity: IdentityEvidence) -> RecoveryReason:
    return (RecoveryReason.IDENTITY_UNKNOWN
            if identity.trust is EvidenceTrust.UNKNOWN else
            RecoveryReason.IDENTITY_UNAUTHENTICATED)


def _receipt_binds(evidence: UpdateRecoveryEvidence) -> bool:
    """Does a confirmed receipt name this exact operation and previous release?

    Equality is required on every part, so a receipt written for another run,
    another attempt, or another release cannot nominate a candidate here.  A
    match still only means the supplied evidence agrees with itself.
    """

    receipt, previous = evidence.rollback_receipt, evidence.previous
    if receipt.state is not RollbackReceiptState.CONFIRMED:
        return False
    return (previous.trust is EvidenceTrust.AUTHENTICATED
            and receipt.operation == evidence.recorded.operation
            and receipt.release_version == previous.release_version
            and receipt.artifact_sha256 == previous.artifact_sha256)


def _plan(
    evidence: UpdateRecoveryEvidence,
    *,
    outcome: RecoveryOutcome,
    reason: RecoveryReason,
    rollback: RollbackReadiness,
    rollback_identity: IdentityEvidence | None,
) -> UpdateRecoveryPlan:
    return UpdateRecoveryPlan(
        outcome=outcome,
        reason=reason,
        recorded=evidence.recorded,
        observed=evidence.observed,
        rollback=rollback,
        rollback_identity=rollback_identity,
        requires_owner_review=outcome is not RecoveryOutcome.NO_ACTION,
    )


def _no_action(evidence: UpdateRecoveryEvidence,
               reason: RecoveryReason) -> UpdateRecoveryPlan:
    return _plan(evidence,
                 outcome=RecoveryOutcome.NO_ACTION,
                 reason=reason,
                 rollback=RollbackReadiness.NOT_APPLICABLE,
                 rollback_identity=None)


def _blocked(evidence: UpdateRecoveryEvidence,
             reason: RecoveryReason) -> UpdateRecoveryPlan:
    """Contradictory evidence never carries a rollback candidate."""

    return _plan(evidence,
                 outcome=RecoveryOutcome.BLOCKED,
                 reason=reason,
                 rollback=RollbackReadiness.UNAVAILABLE,
                 rollback_identity=None)


def _rollback_candidate(
    evidence: UpdateRecoveryEvidence,
    *,
    running_is_previous: bool,
    receipt_bound: bool,
) -> tuple[RollbackReadiness, IdentityEvidence | None]:
    if running_is_previous:
        return RollbackReadiness.NOT_APPLICABLE, None
    if (receipt_bound
            and evidence.previous.trust is EvidenceTrust.AUTHENTICATED):
        return RollbackReadiness.OWNER_REVIEW_REQUIRED, evidence.previous
    return RollbackReadiness.UNAVAILABLE, None


def _revalidate(evidence: UpdateRecoveryEvidence) -> UpdateRecoveryEvidence:
    if not isinstance(evidence, UpdateRecoveryEvidence):
        raise UpdateRecoveryEvidenceRejected()
    try:
        return UpdateRecoveryEvidence.model_validate(
            evidence.model_dump(mode="python", warnings=False))
    except Exception:
        # Fail closed without surfacing the rejected values or a raw error.
        raise UpdateRecoveryEvidenceRejected() from None


def plan_update_recovery(
        evidence: UpdateRecoveryEvidence) -> UpdateRecoveryPlan:
    """Classify one interrupted update run.  This performs no recovery."""

    evidence = _revalidate(evidence)
    recorded, observed = evidence.recorded.phase, evidence.observed.phase
    running, target, previous = (evidence.running, evidence.target,
                                 evidence.previous)

    if evidence.observed.operation != evidence.recorded.operation:
        # The observation describes another run, so it can neither corroborate
        # nor contradict this record: it settles nothing.
        return _blocked(evidence, RecoveryReason.OPERATION_BINDING_MISMATCHED)
    if _PHASE_ORDER[observed] > _PHASE_ORDER[recorded]:
        return _blocked(evidence, RecoveryReason.PHASE_OUT_OF_ORDER)
    if evidence.rollback_receipt.state is RollbackReceiptState.MISMATCHED:
        return _blocked(evidence, RecoveryReason.RECEIPT_MISMATCHED)
    receipt_bound = _receipt_binds(evidence)
    if (evidence.rollback_receipt.state is RollbackReceiptState.CONFIRMED
            and not receipt_bound):
        # A receipt that names another operation or another release is foreign
        # evidence, not a weaker form of confirmation.
        return _blocked(evidence, RecoveryReason.RECEIPT_BINDING_MISMATCHED)

    release_pair = _compare(target, previous)
    if (release_pair is _Match.CONFLICT
            or _compare(running, target) is _Match.CONFLICT
            or _compare(running, previous) is _Match.CONFLICT):
        return _blocked(evidence, RecoveryReason.IDENTITY_MISMATCHED)
    if release_pair is _Match.SAME:
        return _blocked(evidence, RecoveryReason.RELEASE_ORDER_INVALID)
    if (release_pair is _Match.DIFFERENT
            and target.release_version is not None
            and previous.release_version is not None
            and _version_tuple(target.release_version) <= _version_tuple(
                previous.release_version)):
        return _blocked(evidence, RecoveryReason.RELEASE_ORDER_INVALID)

    running_is_target = _compare(running, target) is _Match.SAME
    running_is_previous = _compare(running, previous) is _Match.SAME
    differs_from_target = _compare(running, target) is _Match.DIFFERENT
    differs_from_previous = _compare(running, previous) is _Match.DIFFERENT
    corroborated = observed is recorded
    rollback, rollback_identity = _rollback_candidate(
        evidence,
        running_is_previous=running_is_previous,
        receipt_bound=receipt_bound)

    def review(reason: RecoveryReason) -> UpdateRecoveryPlan:
        return _plan(evidence,
                     outcome=RecoveryOutcome.MANUAL_REVIEW,
                     reason=reason,
                     rollback=rollback,
                     rollback_identity=rollback_identity)

    if recorded in _PRE_INSTALL_PHASES:
        # Nothing was installed in this run.  While an update is staged or
        # reviewed the new release cannot already be running; at rest either
        # authenticated release is a settled, non-interrupted state.
        if running_is_target and recorded is not UpdatePhase.IDLE:
            return _blocked(evidence, RecoveryReason.PHASE_OUT_OF_ORDER)
        if running.trust is not EvidenceTrust.AUTHENTICATED:
            return review(_trust_reason(running))
        if running_is_target:
            return _no_action(evidence, RecoveryReason.UPDATE_SETTLED)
        if running_is_previous:
            if corroborated:
                return _no_action(evidence,
                                  RecoveryReason.NOTHING_INTERRUPTED)
            return review(RecoveryReason.INTERRUPTED_BEFORE_INSTALL)
        if differs_from_previous:
            return _blocked(evidence, RecoveryReason.IDENTITY_MISMATCHED)
        return review(RecoveryReason.PHASE_EVIDENCE_INCOMPLETE)

    if recorded is UpdatePhase.SHUTDOWN_REQUESTED:
        # The owned process tree may have been partially closed, so this phase
        # never settles itself without an owner.
        if running_is_target:
            return _blocked(evidence, RecoveryReason.PHASE_OUT_OF_ORDER)
        if running.trust is not EvidenceTrust.AUTHENTICATED:
            return review(_trust_reason(running))
        if running_is_previous:
            return review(RecoveryReason.INTERRUPTED_BEFORE_INSTALL)
        if differs_from_previous:
            return _blocked(evidence, RecoveryReason.IDENTITY_MISMATCHED)
        return review(RecoveryReason.PHASE_EVIDENCE_INCOMPLETE)

    if recorded is UpdatePhase.INSTALL_STARTED:
        if running.trust is not EvidenceTrust.AUTHENTICATED:
            return review(_trust_reason(running))
        if running_is_target or running_is_previous:
            return review(RecoveryReason.INTERRUPTED_DURING_INSTALL)
        if differs_from_target and differs_from_previous:
            return _blocked(evidence, RecoveryReason.IDENTITY_MISMATCHED)
        return review(RecoveryReason.PHASE_EVIDENCE_INCOMPLETE)

    if recorded in _POST_INSTALL_PHASES:
        # The record claims the new release was installed; the previous release
        # running now is an unexplained reversal, not a proven rollback.
        if running_is_previous:
            return _blocked(evidence, RecoveryReason.PHASE_OUT_OF_ORDER)
        if running.trust is not EvidenceTrust.AUTHENTICATED:
            return review(_trust_reason(running))
        if running_is_target:
            if corroborated:
                return _no_action(evidence, RecoveryReason.UPDATE_SETTLED)
            return review(RecoveryReason.INTERRUPTED_AFTER_INSTALL)
        if differs_from_target:
            return _blocked(evidence, RecoveryReason.IDENTITY_MISMATCHED)
        return review(RecoveryReason.PHASE_EVIDENCE_INCOMPLETE)

    raise UpdateRecoveryEvidenceRejected()


__all__ = (
    "ABSENT_ROLLBACK_RECEIPT",
    "EvidenceTrust",
    "IdentityEvidence",
    "PhaseEvidence",
    "RecoveryOutcome",
    "RecoveryReason",
    "RollbackReadiness",
    "RollbackReceipt",
    "RollbackReceiptState",
    "UNKNOWN_IDENTITY",
    "UPDATE_RECOVERY_EVIDENCE_VERSION",
    "UPDATE_RECOVERY_PLAN_CONTRACT_VERSION",
    "UpdateOperationRef",
    "UpdatePhase",
    "UpdateRecoveryEvidence",
    "UpdateRecoveryEvidenceRejected",
    "UpdateRecoveryPlan",
    "plan_update_recovery",
)
