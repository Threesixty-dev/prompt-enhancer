"""Ephemeral native review of one issued verification opportunity.

No review prose, receipt, or context is durable.  A receipt is useful only for
one acceptance POST while the current sealed r8 source and reviewed r6 plan
remain identical.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
from secrets import token_hex
from threading import Lock
from time import monotonic
from typing import Callable, Literal, Protocol

from pydantic import Field, field_validator, model_validator

from ...domain import PSEUDONYM_PATTERN, StrictModel
from ..verification.observed_check_completion import (
    OBSERVED_CHECK_CLASSIFIER_VERSION,
    OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION,
    OBSERVED_CHECK_NORMALIZER_VERSION,
    OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION,
    EphemeralObservedCheckCompletion,
    ObservedCheckOutcome,
)
from .requirement_plan_evidence import (
    InMemoryRequirementPlanReviewContextStore, RequirementCoordinate,
    RequirementPlanEvidenceSnapshot,
    RequirementPlanConflictError, RequirementPlanNotFoundError,
    RequirementPlanSourceContract,
)
from .requirement_verification_persistence import (
    RequirementVerificationEvidenceSnapshot,
)

REQUIREMENT_VERIFICATION_REVIEW_CONFIRMATION = "open_exact_local_requirement_verification_review"
REQUIREMENT_VERIFICATION_REVIEW_TTL = timedelta(minutes=5)
MAX_ACTIVE_REQUIREMENT_VERIFICATION_REVIEWS = 32
REQUIREMENT_VERIFICATION_REVIEW_SCHEMA_VERSION = "requirement-verification-native-review-v1"
REQUIREMENT_VERIFICATION_REVIEW_POLICY_VERSION = "current-r8-reviewed-r6-clause-only-v1"
OBSERVED_CHECK_REVIEW_CONFIRMATION = (
    "open_exact_local_requirement_observed_check_review"
)
OBSERVED_CHECK_ISSUE_CONFIRMATION = (
    "issue_exact_local_requirement_observed_check_result"
)
OBSERVED_CHECK_REVIEW_SCHEMA_VERSION = "requirement-observed-check-review-v1"
OBSERVED_CHECK_COVERAGE_REVIEW_VERSION = "native-full-criterion-coverage-v1"


def _id(value: str) -> str:
    if PSEUDONYM_PATTERN.fullmatch(value) is None:
        raise ValueError("verification review identifier is invalid")
    return value


class RequirementVerificationReviewError(RuntimeError):
    pass


class RequirementVerificationReviewUnavailableError(RequirementVerificationReviewError):
    pass


class RequirementVerificationReviewConflictError(RequirementVerificationReviewError):
    pass


class RequirementVerificationOpportunityReview(StrictModel):
    session_id: str
    opportunity_set_fingerprint: str
    opportunity_id: str
    requirement_id: str
    coordinate: RequirementCoordinate
    expected_source_run_id: str
    source_window_fingerprint: str
    requirement_plan_confirmation_id: str
    requirement_plan_proposal_id: str
    expected_predecessor_authority_id: str | None = None
    through_revision: int = Field(ge=0, le=32_000)
    review_receipt_id: str
    review_fingerprint: str
    review_expires_at: datetime
    requirement_text: str = Field(min_length=1, max_length=32_000, repr=False)
    schema_version: Literal[REQUIREMENT_VERIFICATION_REVIEW_SCHEMA_VERSION] = REQUIREMENT_VERIFICATION_REVIEW_SCHEMA_VERSION
    policy_version: Literal[REQUIREMENT_VERIFICATION_REVIEW_POLICY_VERSION] = REQUIREMENT_VERIFICATION_REVIEW_POLICY_VERSION
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False

    _ids = field_validator(
        "session_id", "opportunity_set_fingerprint", "opportunity_id",
        "requirement_id", "expected_source_run_id", "source_window_fingerprint",
        "requirement_plan_confirmation_id", "requirement_plan_proposal_id",
        "review_receipt_id", "review_fingerprint",
    )(_id)
    _predecessor = field_validator("expected_predecessor_authority_id")(
        lambda value: None if value is None else _id(value)
    )


class ObservedCheckCandidate(StrictModel):
    """One content-free, server-resolved observed test completion."""

    candidate_id: str
    observed_sequence: int = Field(ge=0, le=4_000_000_000)
    check_kind: Literal["test"] = "test"
    observed_outcome: Literal["passed", "check_failed"]
    provider_execution_status: Literal["completed"] = "completed"
    exit_code: Literal[0, 1]
    source_completion_schema_version: Literal[
        OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION
    ] = OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION
    outcome_interpreter_version: Literal[
        OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION
    ] = OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION
    classifier_version: Literal[OBSERVED_CHECK_CLASSIFIER_VERSION]
    normalizer_version: Literal[OBSERVED_CHECK_NORMALIZER_VERSION]
    rule_id: Literal["test.pytest", "test.py_test"]
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False

    _candidate_id = field_validator("candidate_id")(_id)


class ObservedCheckCandidateManifest(StrictModel):
    """Bounded candidate set for one current verification opportunity."""

    session_id: str
    opportunity_set_fingerprint: str
    opportunity_id: str
    requirement_id: str
    expected_source_run_id: str
    source_window_fingerprint: str
    requirement_plan_confirmation_id: str
    requirement_plan_proposal_id: str
    expected_predecessor_authority_id: str | None = None
    through_revision: int = Field(ge=0, le=32_000)
    candidate_manifest_fingerprint: str
    candidates: tuple[ObservedCheckCandidate, ...] = Field(max_length=4_000)
    schema_version: Literal[OBSERVED_CHECK_REVIEW_SCHEMA_VERSION] = (
        OBSERVED_CHECK_REVIEW_SCHEMA_VERSION
    )
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False

    _ids = field_validator(
        "session_id", "opportunity_set_fingerprint", "opportunity_id",
        "requirement_id", "expected_source_run_id", "source_window_fingerprint",
        "requirement_plan_confirmation_id", "requirement_plan_proposal_id",
        "candidate_manifest_fingerprint",
    )(_id)
    _predecessor = field_validator("expected_predecessor_authority_id")(
        lambda value: None if value is None else _id(value)
    )

    @model_validator(mode="after")
    def exact_candidates(self) -> "ObservedCheckCandidateManifest":
        sequences = tuple(item.observed_sequence for item in self.candidates)
        identifiers = tuple(item.candidate_id for item in self.candidates)
        if sequences != tuple(sorted(sequences)) or len(set(identifiers)) != len(identifiers):
            raise ValueError("observed check candidates must preserve source order")
        return self


class ObservedCheckCriterionReview(StrictModel):
    """One ephemeral native review of a selected check and exact requirement."""

    session_id: str
    opportunity_set_fingerprint: str
    opportunity_id: str
    requirement_id: str
    expected_source_run_id: str
    source_window_fingerprint: str
    requirement_plan_confirmation_id: str
    requirement_plan_proposal_id: str
    expected_predecessor_authority_id: str | None = None
    through_revision: int = Field(ge=0, le=32_000)
    candidate_manifest_fingerprint: str
    candidate: ObservedCheckCandidate
    requirement_text: str = Field(min_length=1, max_length=32_000, repr=False)
    check_tool_name: str = Field(min_length=1, max_length=512, repr=False)
    check_invocation_preview: str = Field(min_length=1, max_length=16_384, repr=False)
    check_effect_preview: str | None = Field(default=None, max_length=16_384, repr=False)
    review_receipt_id: str
    review_fingerprint: str
    review_expires_at: datetime
    full_criterion_coverage_acknowledgement_required: Literal[True] = True
    objective_result_issued: Literal[False] = False
    schema_version: Literal[OBSERVED_CHECK_REVIEW_SCHEMA_VERSION] = (
        OBSERVED_CHECK_REVIEW_SCHEMA_VERSION
    )
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False

    _ids = field_validator(
        "session_id", "opportunity_set_fingerprint", "opportunity_id",
        "requirement_id", "expected_source_run_id", "source_window_fingerprint",
        "requirement_plan_confirmation_id", "requirement_plan_proposal_id",
        "candidate_manifest_fingerprint", "review_receipt_id", "review_fingerprint",
    )(_id)
    _predecessor = field_validator("expected_predecessor_authority_id")(
        lambda value: None if value is None else _id(value)
    )


class CurrentPlanAuthority(Protocol):
    def current_snapshot(self, session_id: str) -> RequirementPlanEvidenceSnapshot: ...


class OpportunityReader(Protocol):
    def snapshot(self, session_id: str, opportunity_set_fingerprint: str, *, through_revision: int | None = None) -> RequirementVerificationEvidenceSnapshot | None: ...


class CurrentSource(Protocol):
    def current_source_contract(self, session_id: str) -> RequirementPlanSourceContract: ...


@dataclass(frozen=True, slots=True)
class _Receipt:
    review: RequirementVerificationOpportunityReview
    expires_monotonic: float


@dataclass(frozen=True, slots=True)
class _ObservedReceipt:
    review: ObservedCheckCriterionReview
    manifest: ObservedCheckCandidateManifest
    descriptor_binding: str
    expires_monotonic: float


class RequirementVerificationReviewService:
    """Bridge a content-free issued opportunity to its exact local clause."""

    def __init__(self, opportunities: OpportunityReader, plans: CurrentPlanAuthority,
                 source: CurrentSource, contexts: InMemoryRequirementPlanReviewContextStore,
                 *, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 monotonic_clock: Callable[[], float] = monotonic,
                 token_factory: Callable[[], str] = lambda: token_hex(32),
                 manifest_key: bytes | None = None) -> None:
        self._opportunities, self._plans, self._source, self._contexts = opportunities, plans, source, contexts
        self._clock, self._monotonic, self._tokens = clock, monotonic_clock, token_factory
        self._receipts: OrderedDict[str, _Receipt] = OrderedDict()
        self._used: OrderedDict[str, None] = OrderedDict()
        self._observed_receipts: OrderedDict[str, _ObservedReceipt] = OrderedDict()
        self._observed_used: OrderedDict[str, _ObservedReceipt] = OrderedDict()
        self._manifest_key = manifest_key or bytes.fromhex(token_hex(32))
        self._lock = Lock()

    def observed_candidates(
        self,
        *,
        session_id: str,
        opportunity_set_fingerprint: str,
        opportunity_id: str,
        expected_source_run_id: str,
        through_revision: int,
        expected_predecessor_authority_id: str | None,
    ) -> ObservedCheckCandidateManifest:
        """Return only current, provider-reported eligible check receipts."""
        for value in (
            session_id, opportunity_set_fingerprint, opportunity_id,
            expected_source_run_id,
        ):
            _id(value)
        snapshot = self._validated_snapshot(
            session_id, opportunity_set_fingerprint, through_revision
        )
        opportunity = next(
            (item for item in snapshot.evidence.opportunities.opportunities
             if item.opportunity_id == opportunity_id),
            None,
        )
        if opportunity is None:
            raise RequirementVerificationReviewConflictError("opportunity is absent")
        head = next(
            (item for item in snapshot.authority_heads
             if item.opportunity_id == opportunity_id),
            None,
        )
        if (None if head is None else head.authority_record_id) != expected_predecessor_authority_id:
            raise RequirementVerificationReviewConflictError("opportunity authority head changed")
        plan, requirement, _ = self._validated_current_requirement(
            session_id, snapshot, opportunity.requirement_id, expected_source_run_id,
            include_text=False,
        )
        try:
            completions = self._contexts.active_observed_check_candidates(
                session_id=session_id,
                source_run_id=expected_source_run_id,
                source_window_fingerprint=plan.source_window_fingerprint,
            )
        except (RequirementPlanConflictError, RequirementPlanNotFoundError):
            raise RequirementVerificationReviewConflictError(
                "fresh current local review context is required"
            ) from None
        if len(completions) > 4_000:
            # Selecting an arbitrary tail would make an older eligible receipt
            # disappear without an owner choice.  The native review surface is
            # bounded by the same maximum as its complete P1 source contract.
            raise RequirementVerificationReviewUnavailableError(
                "observed check candidate surface exceeds its review bound"
            )
        candidates = tuple(
            self._candidate_from_completion(item)
            for item in sorted(completions, key=lambda value: value.observed_sequence)
        )
        fingerprint = self._manifest_fingerprint(
            session_id=session_id,
            opportunity_set_fingerprint=opportunity_set_fingerprint,
            opportunity_id=opportunity_id,
            requirement_id=requirement.requirement_id,
            expected_source_run_id=expected_source_run_id,
            source_window_fingerprint=plan.source_window_fingerprint,
            requirement_plan_confirmation_id=plan.confirmation_id,
            requirement_plan_proposal_id=plan.proposal_id,
            expected_predecessor_authority_id=expected_predecessor_authority_id,
            through_revision=through_revision,
            candidates=candidates,
        )
        return ObservedCheckCandidateManifest(
            session_id=session_id,
            opportunity_set_fingerprint=opportunity_set_fingerprint,
            opportunity_id=opportunity_id,
            requirement_id=requirement.requirement_id,
            expected_source_run_id=expected_source_run_id,
            source_window_fingerprint=plan.source_window_fingerprint,
            requirement_plan_confirmation_id=plan.confirmation_id,
            requirement_plan_proposal_id=plan.proposal_id,
            expected_predecessor_authority_id=expected_predecessor_authority_id,
            through_revision=through_revision,
            candidate_manifest_fingerprint=fingerprint,
            candidates=candidates,
        )

    def open_observed_check(
        self,
        *,
        session_id: str,
        opportunity_set_fingerprint: str,
        opportunity_id: str,
        candidate_id: str,
        expected_source_run_id: str,
        through_revision: int,
        expected_predecessor_authority_id: str | None,
        candidate_manifest_fingerprint: str,
    ) -> ObservedCheckCriterionReview:
        manifest = self.observed_candidates(
            session_id=session_id,
            opportunity_set_fingerprint=opportunity_set_fingerprint,
            opportunity_id=opportunity_id,
            expected_source_run_id=expected_source_run_id,
            through_revision=through_revision,
            expected_predecessor_authority_id=expected_predecessor_authority_id,
        )
        if not hmac.compare_digest(
            manifest.candidate_manifest_fingerprint, candidate_manifest_fingerprint
        ):
            raise RequirementVerificationReviewConflictError("observed check manifest changed")
        candidate = next(
            (item for item in manifest.candidates if item.candidate_id == candidate_id),
            None,
        )
        if candidate is None:
            raise RequirementVerificationReviewConflictError("observed check is absent")
        snapshot = self._validated_snapshot(
            session_id, opportunity_set_fingerprint, through_revision
        )
        plan, requirement, requirement_text = self._validated_current_requirement(
            session_id, snapshot, manifest.requirement_id, expected_source_run_id,
            include_text=True,
        )
        try:
            completion, descriptor = self._contexts.exact_active_observed_check(
                session_id=session_id,
                source_run_id=expected_source_run_id,
                source_window_fingerprint=plan.source_window_fingerprint,
                source_reference_id=candidate_id,
            )
        except (RequirementPlanConflictError, RequirementPlanNotFoundError):
            raise RequirementVerificationReviewConflictError(
                "fresh current local review context is required"
            ) from None
        if self._candidate_from_completion(completion) != candidate:
            raise RequirementVerificationReviewConflictError("observed check changed")
        if descriptor.invocation_truncated or descriptor.result_or_effect_truncated:
            raise RequirementVerificationReviewConflictError(
                "observed check descriptor is incomplete"
            )
        descriptor_binding = self._descriptor_binding(candidate, descriptor)
        now, tick = self._now(), self._monotonic()
        receipt_id = self._tokens(); _id(receipt_id)
        fingerprint = token_hex(32); _id(fingerprint)
        review = ObservedCheckCriterionReview(
            session_id=manifest.session_id,
            opportunity_set_fingerprint=manifest.opportunity_set_fingerprint,
            opportunity_id=manifest.opportunity_id,
            requirement_id=manifest.requirement_id,
            expected_source_run_id=manifest.expected_source_run_id,
            source_window_fingerprint=manifest.source_window_fingerprint,
            requirement_plan_confirmation_id=manifest.requirement_plan_confirmation_id,
            requirement_plan_proposal_id=manifest.requirement_plan_proposal_id,
            expected_predecessor_authority_id=manifest.expected_predecessor_authority_id,
            through_revision=manifest.through_revision,
            candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
            candidate=candidate,
            requirement_text=requirement_text,
            check_tool_name=descriptor.tool_name.get_secret_value(),
            check_invocation_preview=descriptor.invocation_preview.get_secret_value(),
            check_effect_preview=(None if descriptor.result_or_effect_preview is None
                                  else descriptor.result_or_effect_preview.get_secret_value()),
            review_receipt_id=receipt_id,
            review_fingerprint=fingerprint,
            review_expires_at=now + REQUIREMENT_VERIFICATION_REVIEW_TTL,
        )
        with self._lock:
            self._expire(now, tick)
            if receipt_id in self._observed_receipts or receipt_id in self._observed_used:
                raise RequirementVerificationReviewConflictError("review receipt collision")
            self._observed_receipts[receipt_id] = _ObservedReceipt(
                review, manifest, descriptor_binding,
                tick + REQUIREMENT_VERIFICATION_REVIEW_TTL.total_seconds(),
            )
            while len(self._observed_receipts) > MAX_ACTIVE_REQUIREMENT_VERIFICATION_REVIEWS:
                self._observed_receipts.popitem(last=False)
        return review

    def open(self, *, session_id: str, opportunity_set_fingerprint: str, opportunity_id: str,
             expected_source_run_id: str, through_revision: int,
             expected_predecessor_authority_id: str | None) -> RequirementVerificationOpportunityReview:
        for value in (session_id, opportunity_set_fingerprint, opportunity_id, expected_source_run_id): _id(value)
        snapshot = self._validated_snapshot(
            session_id, opportunity_set_fingerprint, through_revision
        )
        opportunity = next((x for x in snapshot.evidence.opportunities.opportunities if x.opportunity_id == opportunity_id), None)
        if opportunity is None:
            raise RequirementVerificationReviewConflictError("opportunity is absent")
        head = next((x for x in snapshot.authority_heads if x.opportunity_id == opportunity_id), None)
        if (None if head is None else head.authority_record_id) != expected_predecessor_authority_id:
            raise RequirementVerificationReviewConflictError("opportunity authority head changed")
        plan, requirement, text = self._validated_current_requirement(
            session_id, snapshot, opportunity.requirement_id, expected_source_run_id,
            include_text=True,
        )
        now, tick = self._now(), self._monotonic()
        receipt_id = self._tokens(); _id(receipt_id)
        # Opaque random binding nonce; it contains no source text.
        fingerprint = token_hex(32)
        review = RequirementVerificationOpportunityReview(
            session_id=session_id, opportunity_set_fingerprint=opportunity_set_fingerprint,
            opportunity_id=opportunity_id, requirement_id=opportunity.requirement_id,
            coordinate=requirement.coordinate, expected_source_run_id=expected_source_run_id,
            source_window_fingerprint=plan.source_window_fingerprint,
            requirement_plan_confirmation_id=plan.confirmation_id,
            requirement_plan_proposal_id=plan.proposal_id,
            expected_predecessor_authority_id=expected_predecessor_authority_id,
            through_revision=through_revision, review_receipt_id=receipt_id,
            review_fingerprint=fingerprint, review_expires_at=now + REQUIREMENT_VERIFICATION_REVIEW_TTL,
            requirement_text=text)
        with self._lock:
            self._expire(now, tick)
            if receipt_id in self._receipts or receipt_id in self._used:
                raise RequirementVerificationReviewConflictError("review receipt collision")
            self._receipts[receipt_id] = _Receipt(review, tick + REQUIREMENT_VERIFICATION_REVIEW_TTL.total_seconds())
            while len(self._receipts) > MAX_ACTIVE_REQUIREMENT_VERIFICATION_REVIEWS: self._receipts.popitem(last=False)
        return review

    def consume(self, *, session_id: str, command: object) -> None:
        receipt_id = getattr(command, "review_receipt_id", None)
        fingerprint = getattr(command, "review_fingerprint", None)
        if not isinstance(receipt_id, str) or not isinstance(fingerprint, str):
            raise RequirementVerificationReviewConflictError("fresh exact local review is required")
        now, tick = self._now(), self._monotonic()
        with self._lock:
            self._expire(now, tick)
            receipt = self._receipts.pop(receipt_id, None)
            self._used[receipt_id] = None
            while len(self._used) > 64: self._used.popitem(last=False)
        if receipt is None or receipt.expires_monotonic <= tick or receipt.review.review_fingerprint != fingerprint:
            raise RequirementVerificationReviewConflictError("review receipt is unavailable")
        review = receipt.review
        if (review.session_id != session_id or review.opportunity_set_fingerprint != getattr(command, "opportunity_set_fingerprint", None)
                or review.opportunity_id != getattr(command, "opportunity_id", None)
                or review.expected_predecessor_authority_id != getattr(command, "expected_predecessor_authority_id", None)
                or review.expected_source_run_id != getattr(command, "expected_source_run_id", None)
                or review.source_window_fingerprint != getattr(command, "source_window_fingerprint", None)):
            raise RequirementVerificationReviewConflictError("review receipt does not bind this acceptance")
        snapshot = self._validated_snapshot(
            session_id, review.opportunity_set_fingerprint, review.through_revision
        )
        current = next((item for item in snapshot.evidence.opportunities.opportunities
                        if item.opportunity_id == review.opportunity_id), None)
        if current is None or current.requirement_id != review.requirement_id:
            raise RequirementVerificationReviewConflictError("opportunity changed")
        head = next((item for item in snapshot.authority_heads if item.opportunity_id == review.opportunity_id), None)
        if (None if head is None else head.authority_record_id) != review.expected_predecessor_authority_id:
            raise RequirementVerificationReviewConflictError("opportunity authority head changed")
        self._validated_current_requirement(
            session_id, snapshot, review.requirement_id,
            review.expected_source_run_id, include_text=False,
        )

    def consume_observed_check(self, *, session_id: str, command: object) -> ObservedCheckCriterionReview:
        """Consume one exact native observed-check review after all live fences."""
        receipt_id = getattr(command, "review_receipt_id", None)
        fingerprint = getattr(command, "review_fingerprint", None)
        if not isinstance(receipt_id, str) or not isinstance(fingerprint, str):
            raise RequirementVerificationReviewConflictError("fresh exact local review is required")
        now, tick = self._now(), self._monotonic()
        with self._lock:
            self._expire(now, tick)
            receipt = self._observed_receipts.pop(receipt_id, None)
            if receipt is not None:
                self._observed_used[receipt_id] = receipt
            while len(self._observed_used) > 64:
                self._observed_used.popitem(last=False)
        command_manifest = getattr(command, "candidate_manifest_fingerprint", None)
        if (
            receipt is None
            or receipt.expires_monotonic <= tick
            or not hmac.compare_digest(receipt.review.review_fingerprint, fingerprint)
        ):
            raise RequirementVerificationReviewConflictError("review receipt is unavailable")
        review = receipt.review
        manifest = receipt.manifest
        if (
            manifest.session_id != session_id
            or manifest.opportunity_set_fingerprint != getattr(command, "opportunity_set_fingerprint", None)
            or manifest.opportunity_id != getattr(command, "opportunity_id", None)
            or review.candidate.candidate_id != getattr(command, "candidate_id", None)
            or manifest.expected_source_run_id != getattr(command, "expected_source_run_id", None)
            or manifest.source_window_fingerprint != getattr(command, "source_window_fingerprint", None)
            or manifest.expected_predecessor_authority_id != getattr(command, "expected_predecessor_authority_id", None)
            or manifest.through_revision != getattr(command, "through_revision", None)
            or not isinstance(command_manifest, str)
            or not hmac.compare_digest(manifest.candidate_manifest_fingerprint, command_manifest)
            or getattr(command, "full_criterion_coverage_acknowledged", None) is not True
        ):
            raise RequirementVerificationReviewConflictError("review receipt does not bind this issuance")
        current_manifest = self.observed_candidates(
            session_id=session_id,
            opportunity_set_fingerprint=manifest.opportunity_set_fingerprint,
            opportunity_id=manifest.opportunity_id,
            expected_source_run_id=manifest.expected_source_run_id,
            through_revision=manifest.through_revision,
            expected_predecessor_authority_id=manifest.expected_predecessor_authority_id,
        )
        if current_manifest != manifest:
            raise RequirementVerificationReviewConflictError("observed check authority changed")
        try:
            completion, descriptor = self._contexts.exact_active_observed_check(
                session_id=session_id,
                source_run_id=manifest.expected_source_run_id,
                source_window_fingerprint=manifest.source_window_fingerprint,
                source_reference_id=review.candidate.candidate_id,
            )
        except (RequirementPlanConflictError, RequirementPlanNotFoundError):
            raise RequirementVerificationReviewConflictError(
                "fresh current local review context is required"
            ) from None
        if (
            self._candidate_from_completion(completion) != review.candidate
            or descriptor.invocation_truncated
            or descriptor.result_or_effect_truncated
            or not hmac.compare_digest(
                receipt.descriptor_binding,
                self._descriptor_binding(review.candidate, descriptor),
            )
        ):
            raise RequirementVerificationReviewConflictError("observed check changed")
        return review

    def preview_observed_check(
        self, *, session_id: str, command: object
    ) -> tuple[ObservedCheckCriterionReview, bool]:
        """Return a bound receipt only to derive an idempotent server result.

        This does not establish freshness or consume the receipt; issuance calls
        ``consume_observed_check`` after replay has been checked.
        """
        receipt_id = getattr(command, "review_receipt_id", None)
        fingerprint = getattr(command, "review_fingerprint", None)
        if not isinstance(receipt_id, str) or not isinstance(fingerprint, str):
            raise RequirementVerificationReviewConflictError("fresh exact local review is required")
        now, tick = self._now(), self._monotonic()
        with self._lock:
            self._expire(now, tick)
            receipt = self._observed_receipts.get(receipt_id)
            consumed = False
            if receipt is None:
                receipt = self._observed_used.get(receipt_id)
                consumed = receipt is not None
        if receipt is None or not hmac.compare_digest(
            receipt.review.review_fingerprint, fingerprint
        ):
            raise RequirementVerificationReviewConflictError("review receipt is unavailable")
        review, manifest = receipt.review, receipt.manifest
        command_manifest = getattr(command, "candidate_manifest_fingerprint", None)
        if (
            manifest.session_id != session_id
            or manifest.opportunity_set_fingerprint != getattr(command, "opportunity_set_fingerprint", None)
            or manifest.opportunity_id != getattr(command, "opportunity_id", None)
            or review.candidate.candidate_id != getattr(command, "candidate_id", None)
            or manifest.expected_source_run_id != getattr(command, "expected_source_run_id", None)
            or manifest.source_window_fingerprint != getattr(command, "source_window_fingerprint", None)
            or manifest.expected_predecessor_authority_id != getattr(command, "expected_predecessor_authority_id", None)
            or manifest.through_revision != getattr(command, "through_revision", None)
            or not isinstance(command_manifest, str)
            or not hmac.compare_digest(manifest.candidate_manifest_fingerprint, command_manifest)
            or getattr(command, "full_criterion_coverage_acknowledged", None) is not True
        ):
            raise RequirementVerificationReviewConflictError("review receipt does not bind this issuance")
        return review, consumed

    def _validated_snapshot(self, session_id: str, opportunity_set_fingerprint: str,
                            through_revision: int) -> RequirementVerificationEvidenceSnapshot:
        historical = self._opportunities.snapshot(
            session_id, opportunity_set_fingerprint, through_revision=through_revision
        )
        current = self._opportunities.snapshot(session_id, opportunity_set_fingerprint)
        if (historical is None or current is None
                or historical.revision != through_revision
                or current.revision != through_revision):
            raise RequirementVerificationReviewConflictError("verification authority changed")
        return historical

    def _validated_current_requirement(self, session_id: str,
                                       snapshot: RequirementVerificationEvidenceSnapshot,
                                       requirement_id: str, expected_source_run_id: str,
                                       *, include_text: bool):
        try:
            plan = self._plans.current_snapshot(session_id)
            source = self._source.current_source_contract(session_id)
        except (RequirementPlanConflictError, RequirementPlanNotFoundError):
            raise RequirementVerificationReviewConflictError(
                "fresh current local review context is required"
            ) from None
        if (source.expected_source_run_id != expected_source_run_id
                or source.source_window_fingerprint != plan.source_window_fingerprint
                or plan.confirmation_id is None or plan.proposal_id is None
                or snapshot.evidence.opportunities.source_window_fingerprint
                != plan.source_window_fingerprint
                or snapshot.evidence.opportunities.requirement_plan_confirmation_id != plan.confirmation_id
                or snapshot.evidence.opportunities.requirement_plan_proposal_id != plan.proposal_id):
            raise RequirementVerificationReviewConflictError("reviewed plan or current source changed")
        requirement = next((x for x in plan.requirements if x.requirement_id == requirement_id), None)
        opportunity = next((x for x in snapshot.evidence.opportunities.opportunities
                            if x.requirement_id == requirement_id), None)
        if (requirement is None or opportunity is None
                or opportunity.coordinate != requirement.coordinate):
            raise RequirementVerificationReviewConflictError("opportunity no longer maps to an active requirement")
        if plan.session_id != session_id or source.session_id != session_id:
            raise RequirementVerificationReviewConflictError("review source belongs to another session")
        text = ""
        if include_text:
            try:
                text = self._contexts.exact_active_requirement_clause(
                    session_id=session_id, source_run_id=expected_source_run_id,
                    source_window_fingerprint=plan.source_window_fingerprint,
                    coordinate=requirement.coordinate)
            except (RequirementPlanConflictError, RequirementPlanNotFoundError):
                raise RequirementVerificationReviewConflictError(
                    "fresh current local review context is required"
                ) from None
        return plan, requirement, text

    def _now(self) -> datetime:
        return self._clock().astimezone(UTC)

    @staticmethod
    def _candidate_from_completion(
        completion: EphemeralObservedCheckCompletion,
    ) -> ObservedCheckCandidate:
        return ObservedCheckCandidate(
            candidate_id=completion.source_reference_id,
            observed_sequence=completion.observed_sequence,
            observed_outcome=(
                "passed" if completion.outcome is ObservedCheckOutcome.PASSED
                else "check_failed"
            ),
            exit_code=completion.exit_code,
            classifier_version=completion.classifier_version,
            normalizer_version=completion.normalizer_version,
            rule_id=completion.rule_id,
        )

    def _manifest_fingerprint(self, **values: object) -> str:
        """Key every content-free candidate semantic and current authority fence."""
        encoded = json.dumps(
            values, default=lambda value: value.model_dump(mode="json"),
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")
        return hmac.new(self._manifest_key, encoded, hashlib.sha256).hexdigest()

    def _descriptor_binding(self, candidate: ObservedCheckCandidate, descriptor: object) -> str:
        """Bind native-only redacted review content without persisting or exposing it."""
        tool_name = getattr(descriptor, "tool_name", None)
        invocation = getattr(descriptor, "invocation_preview", None)
        effect = getattr(descriptor, "result_or_effect_preview", None)
        try:
            values = (
                candidate.candidate_id,
                str(candidate.observed_sequence),
                tool_name.get_secret_value(),
                invocation.get_secret_value(),
                "" if effect is None else effect.get_secret_value(),
            )
        except AttributeError:
            raise RequirementVerificationReviewConflictError(
                "observed check descriptor is invalid"
            ) from None
        return hmac.new(
            self._manifest_key,
            json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _expire(self, now: datetime, tick: float) -> None:
        for key in tuple(k for k, value in self._receipts.items() if value.review.review_expires_at <= now or value.expires_monotonic <= tick):
            del self._receipts[key]
        for key in tuple(
            k for k, value in self._observed_receipts.items()
            if value.review.review_expires_at <= now or value.expires_monotonic <= tick
        ):
            del self._observed_receipts[key]
