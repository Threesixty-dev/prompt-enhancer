"""Offline handoff-readiness contract for a future authorized installer.

Nothing in this module installs, applies, relaunches, spawns, downloads, or
touches the filesystem.  It only decides whether already-recorded evidence
would be complete enough to hand to a separately authorized native installer
that does not exist yet.  Because no such executor exists, ``can_apply`` and
``can_install`` are permanently false and every plan carries the
``executor_unavailable`` block.

Missing or unreadable evidence is never treated as success: absent
authorization, absent quiescence evidence, an absent stage-review binding, or
an absent release binding each produce their own typed block rather than an
optimistic default.

Every input is a caller-supplied claim.  This module only checks that those
claims agree with each other, so a complete verdict is an internal
evidence-consistency statement and never proof that an artifact is authentic,
that a review really happened, or that anything may be installed.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ...domain import StrictModel
from .contracts import (
    ApplicationUpdateState,
    ApplicationUpdateStatus,
    PackageReviewState,
    UpdateChannel,
)
from .package_preflight import (
    AuthenticatedReleaseArtifact,
    MsixPackageExpectation,
)

UPDATE_HANDOFF_PLAN_CONTRACT_VERSION = "update-handoff-plan.v2"

_SEMVER = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
_MAX_EVIDENCE_AGE_SECONDS = 24 * 60 * 60


class HandoffBlockReason(StrEnum):
    """Content-free reasons a staged release cannot be handed to an installer."""

    CLEANUP_UNCONFIRMED = "cleanup_unconfirmed"
    EVIDENCE_TIME_UNTRUSTED = "evidence_time_untrusted"
    EXECUTOR_UNAVAILABLE = "executor_unavailable"
    HOST_NOT_QUIESCENT = "host_not_quiescent"
    OWNER_AUTHORIZATION_EXPIRED = "owner_authorization_expired"
    OWNER_AUTHORIZATION_MISMATCH = "owner_authorization_mismatch"
    OWNER_AUTHORIZATION_MISSING = "owner_authorization_missing"
    PACKAGE_REVIEW_NOT_VERIFIED = "package_review_not_verified"
    PACKAGE_REVIEW_STALE = "package_review_stale"
    QUIESCENCE_STALE = "quiescence_stale"
    QUIESCENCE_UNKNOWN = "quiescence_unknown"
    RELEASE_ARTIFACT_SIZE_MISMATCH = "release_artifact_size_mismatch"
    RELEASE_BINDING_MISMATCH = "release_binding_mismatch"
    RELEASE_BINDING_UNKNOWN = "release_binding_unknown"
    RELEASE_NOT_NEWER = "release_not_newer"
    STAGE_INCOMPLETE = "stage_incomplete"
    STAGE_REVIEW_BINDING_MISMATCH = "stage_review_binding_mismatch"
    STAGE_REVIEW_BINDING_MISSING = "stage_review_binding_missing"
    UPDATE_NOT_STAGED = "update_not_staged"


class UpdateHandoffState(StrEnum):
    """Evidence verdict only.  Neither value grants installation capability."""

    BLOCKED = "blocked"
    EVIDENCE_COMPLETE = "evidence_complete"


class StageReviewBinding(StrictModel):
    """Receipt naming the exact artifact one recorded package review inspected.

    ``ApplicationUpdateStatus`` carries no reviewed digest: it reports only a
    version and a size, which any independently supplied artifact can restate.
    This receipt records the reviewed identity explicitly -- the reviewed
    digest, size and version, the status instance and revision the review was
    recorded against, the review time, and the package expectation identity
    when the review had one -- so a substituted artifact cannot inherit an
    unrelated review.

    This is an internal evidence-consistency contract only.  Every field is a
    caller-supplied claim, so an exact match shows that one request agrees with
    itself; it is never proof of artifact authenticity and never an installer
    capability.
    """

    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_size_bytes: int = Field(gt=0, le=4 * 1024**3, strict=True)
    release_version: str = Field(max_length=32, pattern=_SEMVER)
    status_instance_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    status_revision: int = Field(ge=0, le=9_007_199_254_740_991, strict=True)
    reviewed_at: datetime
    package_expectation: MsixPackageExpectation | None = None

    @field_validator("reviewed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("stage review binding times must be timezone-aware")
        return value


class OwnerHandoffAuthorization(StrictModel):
    """An explicit owner grant bound to one exact release and one exact review."""

    channel: UpdateChannel
    release_version: str = Field(max_length=32, pattern=_SEMVER)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_signer_sha256: str | None = Field(default=None,
                                              pattern=r"^[0-9a-f]{64}$")
    reviewed_at: datetime
    granted_at: datetime
    expires_at: datetime

    @field_validator("reviewed_at", "granted_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("handoff authorization times must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> OwnerHandoffAuthorization:
        if self.expires_at <= self.granted_at:
            raise ValueError("handoff authorization window is empty")
        if self.granted_at < self.reviewed_at:
            raise ValueError("handoff authorization predates its own review")
        return self


class HandoffQuiescence(StrictModel):
    """Observed owned-process/cleanup evidence.  Absence of this model is unknown."""

    owned_worker_count: int = Field(ge=0, le=4096, strict=True)
    operation_active: bool = Field(strict=True)
    staged_cleanup_confirmed: bool = Field(strict=True)
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("quiescence observation times must be timezone-aware")
        return value


class UpdateHandoffRequest(StrictModel):
    """All evidence the evaluator is allowed to consider."""

    status: ApplicationUpdateStatus
    artifact: AuthenticatedReleaseArtifact | None = None
    stage_review_binding: StageReviewBinding | None = None
    authorization: OwnerHandoffAuthorization | None = None
    quiescence: HandoffQuiescence | None = None
    now: datetime
    review_max_age_seconds: int = Field(default=900,
                                        gt=0,
                                        le=_MAX_EVIDENCE_AGE_SECONDS,
                                        strict=True)
    quiescence_max_age_seconds: int = Field(default=60,
                                            gt=0,
                                            le=_MAX_EVIDENCE_AGE_SECONDS,
                                            strict=True)

    @field_validator("now")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("handoff evaluation time must be timezone-aware")
        return value


class UpdateHandoffPlan(StrictModel):
    """Immutable readiness verdict for an unbuilt installer.

    The verdict carries reason codes and the reviewed release binding only,
    never artifact bytes, paths, or manifest content.  It makes no claim to be
    publishable: local installation metadata such as versions, digests, and
    instance identity can be sensitive, and the absence of raw content is not
    permission to treat this verdict as public data.
    """

    contract_version: Literal["update-handoff-plan.v2"] = (
        UPDATE_HANDOFF_PLAN_CONTRACT_VERSION)
    state: UpdateHandoffState
    blocking_reasons: tuple[HandoffBlockReason, ...]
    can_apply: Literal[False] = False
    can_install: Literal[False] = False
    release_version: str | None = Field(default=None,
                                        max_length=32,
                                        pattern=_SEMVER)
    artifact_sha256: str | None = Field(default=None,
                                        pattern=r"^[0-9a-f]{64}$")
    evaluated_at: datetime

    @field_validator("evaluated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("handoff plan times must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_plan(self) -> UpdateHandoffPlan:
        reasons = self.blocking_reasons
        if HandoffBlockReason.EXECUTOR_UNAVAILABLE not in reasons:
            raise ValueError("no update handoff executor exists")
        if list(reasons) != _ordered(set(reasons)):
            raise ValueError("handoff blocking reasons must be sorted and unique")
        complete = reasons == (HandoffBlockReason.EXECUTOR_UNAVAILABLE, )
        if complete != (self.state is UpdateHandoffState.EVIDENCE_COMPLETE):
            raise ValueError("handoff state contradicts its blocking reasons")
        bound = (self.release_version is not None
                 and self.artifact_sha256 is not None)
        if bound != complete:
            raise ValueError("handoff release binding is incomplete")
        return self


def _ordered(reasons: set[HandoffBlockReason]) -> list[HandoffBlockReason]:
    return sorted(reasons, key=lambda reason: reason.value)


def _version_tuple(value: str) -> tuple[int, int, int]:
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def _age_seconds(*, now: datetime, observed_at: datetime) -> float:
    return (now - observed_at).total_seconds()


def evaluate_update_handoff(request: UpdateHandoffRequest) -> UpdateHandoffPlan:
    """Decide, offline, whether staged-update evidence is complete and consistent.

    The result never authorizes installation, and consistency among
    caller-supplied claims is never evidence of authenticity.  Every supplied
    model is revalidated first so that a bypassed or mutated snapshot cannot
    smuggle an inconsistent status past the update contracts.
    """

    request = UpdateHandoffRequest.model_validate(
        request.model_dump(mode="python", warnings=False))
    status, now = request.status, request.now
    artifact, authorization = request.artifact, request.authorization
    review = status.package_review
    reasons = {HandoffBlockReason.EXECUTOR_UNAVAILABLE}

    if status.state is not ApplicationUpdateState.STAGED:
        reasons.add(HandoffBlockReason.UPDATE_NOT_STAGED)

    reviewed_at = (review.checked_at
                   if review.state is PackageReviewState.VERIFIED else None)
    if reviewed_at is None:
        reasons.add(HandoffBlockReason.PACKAGE_REVIEW_NOT_VERIFIED)
    else:
        review_age = _age_seconds(now=now, observed_at=reviewed_at)
        if review_age < 0:
            reasons.add(HandoffBlockReason.EVIDENCE_TIME_UNTRUSTED)
        elif review_age > request.review_max_age_seconds:
            reasons.add(HandoffBlockReason.PACKAGE_REVIEW_STALE)

    if artifact is None:
        reasons.add(HandoffBlockReason.RELEASE_BINDING_UNKNOWN)
    else:
        if status.available_version != artifact.release_version:
            reasons.add(HandoffBlockReason.RELEASE_BINDING_MISMATCH)
        if status.artifact_size_bytes != artifact.size_bytes:
            reasons.add(HandoffBlockReason.RELEASE_ARTIFACT_SIZE_MISMATCH)
        if status.downloaded_bytes != artifact.size_bytes:
            reasons.add(HandoffBlockReason.STAGE_INCOMPLETE)
        if (_version_tuple(artifact.release_version)
                <= _version_tuple(status.installed_version)):
            reasons.add(HandoffBlockReason.RELEASE_NOT_NEWER)

    binding = request.stage_review_binding
    if binding is None:
        reasons.add(HandoffBlockReason.STAGE_REVIEW_BINDING_MISSING)
    elif (artifact is None or binding.artifact_sha256 != artifact.sha256
          or binding.artifact_size_bytes != artifact.size_bytes
          or binding.release_version != artifact.release_version
          or binding.status_instance_id != status.instance_id
          or binding.status_revision != status.revision or reviewed_at is None
          or binding.reviewed_at != reviewed_at):
        reasons.add(HandoffBlockReason.STAGE_REVIEW_BINDING_MISMATCH)

    expectation = binding.package_expectation if binding is not None else None
    reviewed_signer = (expectation.signer_sha256
                       if expectation is not None else None)

    if authorization is None:
        reasons.add(HandoffBlockReason.OWNER_AUTHORIZATION_MISSING)
    else:
        if (artifact is None
                or authorization.release_version != artifact.release_version
                or authorization.artifact_sha256 != artifact.sha256
                or authorization.package_signer_sha256 != reviewed_signer
                or authorization.channel is not status.channel
                or reviewed_at is None or authorization.reviewed_at != reviewed_at):
            reasons.add(HandoffBlockReason.OWNER_AUTHORIZATION_MISMATCH)
        if (authorization.granted_at > now
                or (reviewed_at is not None
                    and authorization.granted_at < reviewed_at)):
            reasons.add(HandoffBlockReason.EVIDENCE_TIME_UNTRUSTED)
        if authorization.expires_at <= now:
            reasons.add(HandoffBlockReason.OWNER_AUTHORIZATION_EXPIRED)

    quiescence = request.quiescence
    if quiescence is None:
        reasons.add(HandoffBlockReason.QUIESCENCE_UNKNOWN)
    else:
        quiescence_age = _age_seconds(now=now,
                                      observed_at=quiescence.observed_at)
        if quiescence_age < 0:
            reasons.add(HandoffBlockReason.EVIDENCE_TIME_UNTRUSTED)
        elif quiescence_age > request.quiescence_max_age_seconds:
            reasons.add(HandoffBlockReason.QUIESCENCE_STALE)
        if quiescence.owned_worker_count != 0 or quiescence.operation_active:
            reasons.add(HandoffBlockReason.HOST_NOT_QUIESCENT)
        if not quiescence.staged_cleanup_confirmed:
            reasons.add(HandoffBlockReason.CLEANUP_UNCONFIRMED)

    complete = reasons == {HandoffBlockReason.EXECUTOR_UNAVAILABLE}
    return UpdateHandoffPlan(
        state=UpdateHandoffState.EVIDENCE_COMPLETE
        if complete else UpdateHandoffState.BLOCKED,
        blocking_reasons=tuple(_ordered(reasons)),
        release_version=artifact.release_version
        if complete and artifact else None,
        artifact_sha256=artifact.sha256 if complete and artifact else None,
        evaluated_at=now,
    )


__all__ = (
    "HandoffBlockReason",
    "HandoffQuiescence",
    "OwnerHandoffAuthorization",
    "StageReviewBinding",
    "UPDATE_HANDOFF_PLAN_CONTRACT_VERSION",
    "UpdateHandoffPlan",
    "UpdateHandoffRequest",
    "UpdateHandoffState",
    "evaluate_update_handoff",
)
