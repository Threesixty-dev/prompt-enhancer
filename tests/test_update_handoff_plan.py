"""Synthetic contract tests for the offline update handoff-readiness plan.

Every fixture here is fictional.  No installer, process, network call, or
filesystem access is involved: the evaluator is a pure function over models.

A complete verdict only means the supplied claims agree with each other, so
the adversarial cases below check that agreement is exact rather than merely
plausible.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from prompt_enhancer.application.updates.contracts import (
    ApplicationUpdateReason,
    ApplicationUpdateState,
    ApplicationUpdateStatus,
    PackageReview,
    PackageReviewState,
    UpdateChannel,
)
from prompt_enhancer.application.updates.handoff_plan import (
    UPDATE_HANDOFF_PLAN_CONTRACT_VERSION,
    HandoffBlockReason,
    HandoffQuiescence,
    OwnerHandoffAuthorization,
    StageReviewBinding,
    UpdateHandoffPlan,
    UpdateHandoffRequest,
    UpdateHandoffState,
    evaluate_update_handoff,
)
from prompt_enhancer.application.updates.package_preflight import (
    AuthenticatedReleaseArtifact,
    MsixPackageExpectation,
)

_NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
_REVIEWED_AT = _NOW - timedelta(seconds=60)
_DIGEST = "b" * 64
_OTHER_DIGEST = "c" * 64
_SIGNER = "d" * 64
_OTHER_SIGNER = "e" * 64
_INSTANCE_ID = "0123456789abcdef0123456789abcdef"
_OTHER_INSTANCE_ID = "fedcba9876543210fedcba9876543210"
_REVISION = 4
_SIZE = 2048


def _expectation(**overrides: object) -> MsixPackageExpectation:
    fields: dict[str, object] = {
        "name": "Example.PromptEnhancer",
        "publisher": "CN=Example Fictional Publisher, O=Example, C=US",
        "architecture": "x64",
        "signer_sha256": _SIGNER,
    }
    fields.update(overrides)
    return MsixPackageExpectation(**fields)


def _status(**overrides: object) -> ApplicationUpdateStatus:
    fields: dict[str, object] = {
        "installed_version": "1.2.3",
        "channel": UpdateChannel.STABLE,
        "state": ApplicationUpdateState.STAGED,
        "instance_id": _INSTANCE_ID,
        "revision": _REVISION,
        "available_version": "1.3.0",
        "artifact_size_bytes": _SIZE,
        "downloaded_bytes": _SIZE,
        "last_checked_at": _NOW - timedelta(seconds=120),
        "can_check": True,
        "can_stage": False,
        "can_cancel": False,
        "can_retry": False,
        "can_apply": False,
        "can_verify": True,
        "package_review": PackageReview(state=PackageReviewState.VERIFIED,
                                        checked_at=_REVIEWED_AT),
    }
    fields.update(overrides)
    return ApplicationUpdateStatus(**fields)


def _artifact(**overrides: object) -> AuthenticatedReleaseArtifact:
    fields: dict[str, object] = {
        "sha256": _DIGEST,
        "size_bytes": _SIZE,
        "release_version": "1.3.0",
    }
    fields.update(overrides)
    return AuthenticatedReleaseArtifact(**fields)


def _binding(**overrides: object) -> StageReviewBinding:
    fields: dict[str, object] = {
        "artifact_sha256": _DIGEST,
        "artifact_size_bytes": _SIZE,
        "release_version": "1.3.0",
        "status_instance_id": _INSTANCE_ID,
        "status_revision": _REVISION,
        "reviewed_at": _REVIEWED_AT,
        "package_expectation": _expectation(),
    }
    fields.update(overrides)
    return StageReviewBinding(**fields)


def _authorization(**overrides: object) -> OwnerHandoffAuthorization:
    fields: dict[str, object] = {
        "channel": UpdateChannel.STABLE,
        "release_version": "1.3.0",
        "artifact_sha256": _DIGEST,
        "package_signer_sha256": _SIGNER,
        "reviewed_at": _REVIEWED_AT,
        "granted_at": _NOW - timedelta(seconds=30),
        "expires_at": _NOW + timedelta(seconds=300),
    }
    fields.update(overrides)
    return OwnerHandoffAuthorization(**fields)


def _quiescence(**overrides: object) -> HandoffQuiescence:
    fields: dict[str, object] = {
        "owned_worker_count": 0,
        "operation_active": False,
        "staged_cleanup_confirmed": True,
        "observed_at": _NOW - timedelta(seconds=10),
    }
    fields.update(overrides)
    return HandoffQuiescence(**fields)


def _request(**overrides: object) -> UpdateHandoffRequest:
    fields: dict[str, object] = {
        "status": _status(),
        "artifact": _artifact(),
        "stage_review_binding": _binding(),
        "authorization": _authorization(),
        "quiescence": _quiescence(),
        "now": _NOW,
    }
    fields.update(overrides)
    return UpdateHandoffRequest(**fields)


def _reasons(request: UpdateHandoffRequest) -> set[HandoffBlockReason]:
    return set(evaluate_update_handoff(request).blocking_reasons)


def _blocked(request: UpdateHandoffRequest) -> set[HandoffBlockReason]:
    """Evaluate while re-asserting the invariants no evidence can relax."""

    plan = evaluate_update_handoff(request)
    assert plan.state is UpdateHandoffState.BLOCKED
    assert plan.can_apply is False and plan.can_install is False
    assert HandoffBlockReason.EXECUTOR_UNAVAILABLE in plan.blocking_reasons
    assert plan.release_version is None and plan.artifact_sha256 is None
    return set(plan.blocking_reasons)


def test_complete_evidence_still_cannot_apply_or_install() -> None:
    plan = evaluate_update_handoff(_request())

    assert plan.state is UpdateHandoffState.EVIDENCE_COMPLETE
    assert plan.blocking_reasons == (HandoffBlockReason.EXECUTOR_UNAVAILABLE, )
    assert plan.can_apply is False
    assert plan.can_install is False
    assert plan.release_version == "1.3.0"
    assert plan.artifact_sha256 == _DIGEST
    assert plan.evaluated_at == _NOW
    assert plan.contract_version == UPDATE_HANDOFF_PLAN_CONTRACT_VERSION


def test_plan_is_immutable_and_carries_no_artifact_content() -> None:
    plan = evaluate_update_handoff(_request())

    with pytest.raises(ValidationError):
        plan.state = UpdateHandoffState.BLOCKED  # type: ignore[misc]

    assert set(plan.model_dump(mode="json")) == {
        "contract_version",
        "state",
        "blocking_reasons",
        "can_apply",
        "can_install",
        "release_version",
        "artifact_sha256",
        "evaluated_at",
    }


def test_evaluation_is_deterministic() -> None:
    request = _request()

    assert evaluate_update_handoff(request) == evaluate_update_handoff(request)


def test_all_unknown_evidence_blocks_without_binding() -> None:
    plan = evaluate_update_handoff(
        _request(artifact=None,
                 stage_review_binding=None,
                 authorization=None,
                 quiescence=None))

    assert plan.state is UpdateHandoffState.BLOCKED
    assert set(plan.blocking_reasons) == {
        HandoffBlockReason.EXECUTOR_UNAVAILABLE,
        HandoffBlockReason.RELEASE_BINDING_UNKNOWN,
        HandoffBlockReason.STAGE_REVIEW_BINDING_MISSING,
        HandoffBlockReason.OWNER_AUTHORIZATION_MISSING,
        HandoffBlockReason.QUIESCENCE_UNKNOWN,
    }
    assert plan.release_version is None and plan.artifact_sha256 is None


def test_unstaged_update_blocks() -> None:
    available = _status(
        state=ApplicationUpdateState.AVAILABLE,
        downloaded_bytes=0,
        can_stage=True,
        can_verify=False,
        package_review=PackageReview(state=PackageReviewState.NOT_STAGED),
    )

    assert _reasons(_request(status=available)) == {
        HandoffBlockReason.EXECUTOR_UNAVAILABLE,
        HandoffBlockReason.UPDATE_NOT_STAGED,
        HandoffBlockReason.STAGE_INCOMPLETE,
        HandoffBlockReason.STAGE_REVIEW_BINDING_MISMATCH,
        HandoffBlockReason.PACKAGE_REVIEW_NOT_VERIFIED,
        HandoffBlockReason.OWNER_AUTHORIZATION_MISMATCH,
    }


def test_failed_update_with_uncertain_cleanup_blocks() -> None:
    failed = _status(
        state=ApplicationUpdateState.FAILED,
        available_version=None,
        artifact_size_bytes=None,
        downloaded_bytes=None,
        reason_code=ApplicationUpdateReason.STAGING_CLEANUP_UNCONFIRMED,
        can_check=False,
        can_verify=False,
        package_review=PackageReview(state=PackageReviewState.NOT_STAGED),
    )

    reasons = _reasons(_request(status=failed))
    assert HandoffBlockReason.UPDATE_NOT_STAGED in reasons
    assert HandoffBlockReason.RELEASE_BINDING_MISMATCH in reasons
    assert HandoffBlockReason.PACKAGE_REVIEW_NOT_VERIFIED in reasons


@pytest.mark.parametrize(
    "review",
    [
        PackageReview(state=PackageReviewState.NOT_CHECKED),
        PackageReview(state=PackageReviewState.REJECTED,
                      reason_code="signature_unverifiable",
                      checked_at=_REVIEWED_AT),
    ],
)
def test_unverified_package_review_blocks(review: PackageReview) -> None:
    reasons = _reasons(_request(status=_status(package_review=review)))

    assert HandoffBlockReason.PACKAGE_REVIEW_NOT_VERIFIED in reasons
    assert HandoffBlockReason.OWNER_AUTHORIZATION_MISMATCH in reasons
    assert HandoffBlockReason.STAGE_REVIEW_BINDING_MISMATCH in reasons


def test_review_freshness_boundary() -> None:
    fresh = _request(review_max_age_seconds=60)
    stale = _request(review_max_age_seconds=59)

    assert _reasons(fresh) == {HandoffBlockReason.EXECUTOR_UNAVAILABLE}
    assert HandoffBlockReason.PACKAGE_REVIEW_STALE in _reasons(stale)


def test_review_recorded_in_the_future_is_untrusted() -> None:
    ahead = _NOW + timedelta(seconds=1)
    request = _request(
        status=_status(package_review=PackageReview(
            state=PackageReviewState.VERIFIED, checked_at=ahead)),
        stage_review_binding=_binding(reviewed_at=ahead),
        authorization=_authorization(reviewed_at=ahead, granted_at=ahead),
    )

    reasons = _reasons(request)
    assert HandoffBlockReason.EVIDENCE_TIME_UNTRUSTED in reasons
    assert HandoffBlockReason.PACKAGE_REVIEW_STALE not in reasons


def test_release_binding_must_match_the_status_exactly() -> None:
    version_conflict = _request(status=_status(available_version="1.4.0"))
    size_conflict = _request(artifact=_artifact(size_bytes=_SIZE + 1))

    assert HandoffBlockReason.RELEASE_BINDING_MISMATCH in _reasons(
        version_conflict)
    reasons = _reasons(size_conflict)
    assert HandoffBlockReason.RELEASE_ARTIFACT_SIZE_MISMATCH in reasons
    assert HandoffBlockReason.STAGE_INCOMPLETE in reasons


def test_partial_stage_blocks() -> None:
    staging = _status(
        state=ApplicationUpdateState.STAGING,
        downloaded_bytes=_SIZE - 1,
        can_check=False,
        can_cancel=True,
        can_verify=False,
        package_review=PackageReview(state=PackageReviewState.NOT_STAGED),
    )

    assert HandoffBlockReason.STAGE_INCOMPLETE in _reasons(
        _request(status=staging))


@pytest.mark.parametrize("release_version", ["1.2.3", "1.2.2"])
def test_same_or_older_release_blocks(release_version: str) -> None:
    request = _request(
        status=_status(available_version=release_version),
        artifact=_artifact(release_version=release_version),
        stage_review_binding=_binding(release_version=release_version),
        authorization=_authorization(release_version=release_version),
    )

    assert _reasons(request) == {
        HandoffBlockReason.EXECUTOR_UNAVAILABLE,
        HandoffBlockReason.RELEASE_NOT_NEWER,
    }


def test_missing_stage_review_binding_blocks() -> None:
    """A signer pinned by the owner has nothing to match without the receipt.

    The binding is the only evidence naming the reviewed package identity, so
    its absence also strands an authorization that pins a signer: an unmatched
    pin stays a mismatch rather than degrading to an unpinned grant.
    """

    assert _blocked(_request(stage_review_binding=None)) == {
        HandoffBlockReason.EXECUTOR_UNAVAILABLE,
        HandoffBlockReason.STAGE_REVIEW_BINDING_MISSING,
        HandoffBlockReason.OWNER_AUTHORIZATION_MISMATCH,
    }


def test_same_version_and_size_with_another_reviewed_digest_blocks() -> None:
    """Version and size alone cannot tell two same-sized releases apart."""

    substituted = _request(
        artifact=_artifact(sha256=_OTHER_DIGEST),
        authorization=_authorization(artifact_sha256=_OTHER_DIGEST),
    )

    assert _blocked(substituted) == {
        HandoffBlockReason.EXECUTOR_UNAVAILABLE,
        HandoffBlockReason.STAGE_REVIEW_BINDING_MISMATCH,
    }


@pytest.mark.parametrize(
    "status_override",
    [
        {
            "instance_id": _OTHER_INSTANCE_ID
        },
        {
            "revision": _REVISION + 1
        },
    ],
)
def test_binding_replayed_onto_another_status_identity_blocks(
        status_override: dict[str, object]) -> None:
    replayed = _request(status=_status(**status_override))

    assert _blocked(replayed) == {
        HandoffBlockReason.EXECUTOR_UNAVAILABLE,
        HandoffBlockReason.STAGE_REVIEW_BINDING_MISMATCH,
    }


@pytest.mark.parametrize(
    "override",
    [
        {
            "artifact_sha256": _OTHER_DIGEST
        },
        {
            "artifact_size_bytes": _SIZE + 1
        },
        {
            "release_version": "1.4.0"
        },
        {
            "status_instance_id": _OTHER_INSTANCE_ID
        },
        {
            "status_revision": _REVISION + 1
        },
        {
            "reviewed_at": _REVIEWED_AT + timedelta(microseconds=1)
        },
    ],
)
def test_binding_must_name_the_exact_reviewed_artifact(
        override: dict[str, object]) -> None:
    request = _request(stage_review_binding=_binding(**override))

    assert HandoffBlockReason.STAGE_REVIEW_BINDING_MISMATCH in _blocked(request)


@pytest.mark.parametrize(
    ("binding_override", "authorization_override"),
    [
        ({}, {
            "package_signer_sha256": _OTHER_SIGNER
        }),
        ({}, {
            "package_signer_sha256": None
        }),
        ({
            "package_expectation": None
        }, {}),
    ],
)
def test_authorization_must_bind_the_reviewed_package_identity(
        binding_override: dict[str, object],
        authorization_override: dict[str, object]) -> None:
    request = _request(
        stage_review_binding=_binding(**binding_override),
        authorization=_authorization(**authorization_override),
    )

    assert _blocked(request) == {
        HandoffBlockReason.EXECUTOR_UNAVAILABLE,
        HandoffBlockReason.OWNER_AUTHORIZATION_MISMATCH,
    }


def test_review_without_a_package_expectation_still_completes() -> None:
    plan = evaluate_update_handoff(
        _request(stage_review_binding=_binding(package_expectation=None),
                 authorization=_authorization(package_signer_sha256=None)))

    assert plan.state is UpdateHandoffState.EVIDENCE_COMPLETE
    assert plan.blocking_reasons == (HandoffBlockReason.EXECUTOR_UNAVAILABLE, )
    assert plan.can_apply is False and plan.can_install is False


def test_missing_owner_authorization_blocks() -> None:
    assert _reasons(_request(authorization=None)) == {
        HandoffBlockReason.EXECUTOR_UNAVAILABLE,
        HandoffBlockReason.OWNER_AUTHORIZATION_MISSING,
    }


@pytest.mark.parametrize(
    "override",
    [
        {"artifact_sha256": _OTHER_DIGEST},
        {"release_version": "1.4.0"},
        {"channel": UpdateChannel.BETA},
        {"reviewed_at": _REVIEWED_AT + timedelta(microseconds=1)},
    ],
)
def test_authorization_must_bind_the_exact_release_and_review(
        override: dict[str, object]) -> None:
    request = _request(authorization=_authorization(**override))

    assert HandoffBlockReason.OWNER_AUTHORIZATION_MISMATCH in _reasons(request)


def test_authorization_without_a_release_binding_is_a_mismatch() -> None:
    reasons = _reasons(_request(artifact=None))

    assert HandoffBlockReason.RELEASE_BINDING_UNKNOWN in reasons
    assert HandoffBlockReason.OWNER_AUTHORIZATION_MISMATCH in reasons


def test_expired_authorization_blocks_at_its_boundary() -> None:
    expired = _request(authorization=_authorization(expires_at=_NOW))
    valid = _request(
        authorization=_authorization(expires_at=_NOW + timedelta(seconds=1)))

    assert HandoffBlockReason.OWNER_AUTHORIZATION_EXPIRED in _reasons(expired)
    assert _reasons(valid) == {HandoffBlockReason.EXECUTOR_UNAVAILABLE}


def test_authorization_granted_in_the_future_is_untrusted() -> None:
    request = _request(authorization=_authorization(
        granted_at=_NOW + timedelta(seconds=1),
        expires_at=_NOW + timedelta(seconds=600),
    ))

    assert HandoffBlockReason.EVIDENCE_TIME_UNTRUSTED in _reasons(request)


def test_empty_authorization_window_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _authorization(expires_at=_NOW - timedelta(seconds=30))


def test_authorization_granted_before_its_own_review_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _authorization(granted_at=_REVIEWED_AT - timedelta(microseconds=1))


def test_authorization_granted_at_its_review_is_accepted() -> None:
    request = _request(authorization=_authorization(granted_at=_REVIEWED_AT))

    assert _reasons(request) == {HandoffBlockReason.EXECUTOR_UNAVAILABLE}


def test_authorization_granted_before_the_recorded_review_is_untrusted() -> None:
    earlier_review = _REVIEWED_AT - timedelta(seconds=600)
    replayed = _request(authorization=_authorization(
        reviewed_at=earlier_review,
        granted_at=earlier_review + timedelta(seconds=1),
    ))

    reasons = _blocked(replayed)
    assert HandoffBlockReason.EVIDENCE_TIME_UNTRUSTED in reasons
    assert HandoffBlockReason.OWNER_AUTHORIZATION_MISMATCH in reasons


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({
            "owned_worker_count": 1
        }, HandoffBlockReason.HOST_NOT_QUIESCENT),
        ({
            "operation_active": True
        }, HandoffBlockReason.HOST_NOT_QUIESCENT),
        ({
            "staged_cleanup_confirmed": False
        }, HandoffBlockReason.CLEANUP_UNCONFIRMED),
        ({
            "observed_at": _NOW + timedelta(seconds=1)
        }, HandoffBlockReason.EVIDENCE_TIME_UNTRUSTED),
    ],
)
def test_quiescence_evidence_must_be_clean(override: dict[str, object],
                                           expected: HandoffBlockReason) -> None:
    assert expected in _reasons(_request(quiescence=_quiescence(**override)))


def test_quiescence_freshness_boundary() -> None:
    fresh = _request(quiescence_max_age_seconds=10)
    stale = _request(quiescence_max_age_seconds=9)

    assert _reasons(fresh) == {HandoffBlockReason.EXECUTOR_UNAVAILABLE}
    assert HandoffBlockReason.QUIESCENCE_STALE in _reasons(stale)


def test_conflicting_evidence_accumulates_sorted_and_unique() -> None:
    plan = evaluate_update_handoff(
        _request(
            status=_status(available_version="1.4.0",
                           package_review=PackageReview(
                               state=PackageReviewState.NOT_CHECKED)),
            authorization=_authorization(artifact_sha256=_OTHER_DIGEST,
                                         expires_at=_NOW),
            quiescence=_quiescence(owned_worker_count=2,
                                   staged_cleanup_confirmed=False),
        ))

    assert plan.state is UpdateHandoffState.BLOCKED
    assert set(plan.blocking_reasons) == {
        HandoffBlockReason.CLEANUP_UNCONFIRMED,
        HandoffBlockReason.EXECUTOR_UNAVAILABLE,
        HandoffBlockReason.HOST_NOT_QUIESCENT,
        HandoffBlockReason.OWNER_AUTHORIZATION_EXPIRED,
        HandoffBlockReason.OWNER_AUTHORIZATION_MISMATCH,
        HandoffBlockReason.PACKAGE_REVIEW_NOT_VERIFIED,
        HandoffBlockReason.RELEASE_BINDING_MISMATCH,
        HandoffBlockReason.STAGE_REVIEW_BINDING_MISMATCH,
    }
    values = [reason.value for reason in plan.blocking_reasons]
    assert values == sorted(values) and len(values) == len(set(values))


def test_bypassed_status_snapshot_is_revalidated() -> None:
    tampered = _status().model_copy(update={"can_apply": True})

    with pytest.raises(ValidationError):
        evaluate_update_handoff(_request(status=tampered))


@pytest.mark.parametrize(
    "override",
    [
        {
            "now": datetime(2026, 9, 5, 12, 0)
        },
        {
            "review_max_age_seconds": True
        },
        {
            "quiescence_max_age_seconds": 0
        },
        {
            "review_max_age_seconds": 86401
        },
        {
            "unexpected": "value"
        },
    ],
)
def test_request_rejects_invalid_or_unknown_input(
        override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _request(**override)


@pytest.mark.parametrize(
    "override",
    [
        {
            "observed_at": datetime(2026, 9, 5, 12, 0)
        },
        {
            "owned_worker_count": True
        },
        {
            "owned_worker_count": -1
        },
        {
            "operation_active": 1
        },
    ],
)
def test_quiescence_rejects_invalid_input(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _quiescence(**override)


def test_authorization_requires_timezone_aware_times() -> None:
    with pytest.raises(ValidationError):
        _authorization(granted_at=datetime(2026, 9, 5, 11, 59))


def _plan(**overrides: object) -> UpdateHandoffPlan:
    fields: dict[str, object] = {
        "state": UpdateHandoffState.EVIDENCE_COMPLETE,
        "blocking_reasons": (HandoffBlockReason.EXECUTOR_UNAVAILABLE, ),
        "release_version": "1.3.0",
        "artifact_sha256": _DIGEST,
        "evaluated_at": _NOW,
    }
    fields.update(overrides)
    return UpdateHandoffPlan(**fields)


@pytest.mark.parametrize(
    "override",
    [
        {
            "can_apply": True
        },
        {
            "can_install": True
        },
        {
            "blocking_reasons": ()
        },
        {
            "blocking_reasons": (HandoffBlockReason.QUIESCENCE_UNKNOWN, )
        },
        {
            "blocking_reasons": (
                HandoffBlockReason.EXECUTOR_UNAVAILABLE,
                HandoffBlockReason.EXECUTOR_UNAVAILABLE,
            )
        },
        {
            "blocking_reasons": (
                HandoffBlockReason.QUIESCENCE_UNKNOWN,
                HandoffBlockReason.EXECUTOR_UNAVAILABLE,
            ),
            "state": UpdateHandoffState.BLOCKED,
            "release_version": None,
            "artifact_sha256": None,
        },
        {
            "state": UpdateHandoffState.BLOCKED
        },
        {
            "release_version": None
        },
        {
            "artifact_sha256": None
        },
        {
            "contract_version": "update-handoff-plan.v1"
        },
        {
            "evaluated_at": datetime(2026, 9, 5, 12, 0)
        },
    ],
)
def test_plan_rejects_inconsistent_construction(
        override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _plan(**override)


def test_valid_blocked_plan_construction() -> None:
    plan = _plan(
        state=UpdateHandoffState.BLOCKED,
        blocking_reasons=(
            HandoffBlockReason.EXECUTOR_UNAVAILABLE,
            HandoffBlockReason.QUIESCENCE_UNKNOWN,
        ),
        release_version=None,
        artifact_sha256=None,
    )

    assert plan.can_apply is False and plan.can_install is False
