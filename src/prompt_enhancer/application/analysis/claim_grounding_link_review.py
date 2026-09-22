"""Ephemeral, non-authoritative native-review preparation for claim coverage."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
from threading import RLock
from typing import Callable, Literal, Protocol
import secrets

from pydantic import Field, SecretStr, field_validator

from ...domain import PSEUDONYM_PATTERN, StrictModel
from .claim_grounding_evidence import ClaimCensusClassification, ClaimGroundingIdFactory
from .claim_grounding_link_source import CurrentClaimGroundingLinkSourceResolver
from .claim_grounding_links import ClaimLinkCoverageDecision

_TTL = timedelta(minutes=5); _MAX_RECEIPTS = 128
_DECISION_SCHEMA_VERSION = "claim-grounding-link-reviewed-decision-v1"
_DECISION_POLICY_VERSION = "native-reviewed-claim-link-coverage-v1"

class ClaimGroundingLinkReviewConflictError(RuntimeError): pass
class ClaimGroundingLinkReviewUnavailableError(RuntimeError): pass

class _Contexts(Protocol):
    def exact_active_claim_grounding_clause(self, **values): ...  # type: ignore[no-untyped-def]
    def exact_active_observed_check(self, **values): ...  # type: ignore[no-untyped-def]

class ClaimObservedCheckPreview(StrictModel):
    source_reference_id: str
    observed_sequence: int = Field(ge=0)
    outcome: Literal["passed", "check_failed"]
    invocation_preview: SecretStr = Field(repr=False, exclude=True)
    tool_name: SecretStr = Field(repr=False, exclude=True)
    effect_preview: SecretStr | None = Field(repr=False, exclude=True)

class ClaimGroundingLinkReview(StrictModel):
    session_id: str; census_id: str; candidate_id: str; source_run_id: str
    source_window_fingerprint: str; census_fingerprint: str; manifest_fingerprint: str; observed_set_fingerprint: str
    review_receipt_id: str; review_fingerprint: str; review_expires_at: datetime
    claim_clause: SecretStr = Field(repr=False, exclude=True)
    observed_checks: tuple[ClaimObservedCheckPreview, ...] = Field(max_length=128)
    proposal_only: Literal[True] = True; measured: Literal[False] = False
    metric_authority_established: Literal[False] = False; content_persisted: Literal[False] = False

class ClaimGroundingLinkCoverageCommand(StrictModel):
    session_id: str; review_receipt_id: str; review_fingerprint: str; decision: ClaimLinkCoverageDecision
    selected_check_references: tuple[str, ...] = Field(max_length=128)
    coverage_review_acknowledged: Literal[True]

    _ids = field_validator("session_id", "review_receipt_id", "review_fingerprint")(
        lambda value: value if PSEUDONYM_PATTERN.fullmatch(value) else (_ for _ in ()).throw(ValueError("claim link review identity is invalid"))
    )
    _references = field_validator("selected_check_references")(
        lambda values: tuple(value if PSEUDONYM_PATTERN.fullmatch(value) else (_ for _ in ()).throw(ValueError("claim link observed check identity is invalid")) for value in values)
    )

@dataclass(frozen=True, slots=True)
class ClaimGroundingLinkReviewReservation:
    receipt_id: str; owner: str; token: str


@dataclass(frozen=True, slots=True)
class ClaimGroundingLinkReviewedDecision:
    """Exact native-reviewed linkage choice; content-free and non-authoritative."""

    session_id: str
    census_id: str
    candidate_id: str
    source_run_id: str
    source_window_fingerprint: str
    census_fingerprint: str
    manifest_fingerprint: str
    observed_set_fingerprint: str
    review_receipt_id: str
    review_fingerprint: str
    decision: ClaimLinkCoverageDecision
    selected_check_references: tuple[str, ...]
    selected_observed_completions: tuple["ClaimGroundingLinkObservedCompletionSnapshot", ...]
    coverage_review_acknowledged: Literal[True] = field(default=True, init=False)
    schema_version: Literal[_DECISION_SCHEMA_VERSION] = field(default=_DECISION_SCHEMA_VERSION, init=False)
    policy_version: Literal[_DECISION_POLICY_VERSION] = field(default=_DECISION_POLICY_VERSION, init=False)
    proposal_only: Literal[True] = field(default=True, init=False)
    measured: Literal[False] = field(default=False, init=False)
    metric_authority_established: Literal[False] = field(default=False, init=False)
    content_persisted: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class ClaimGroundingLinkObservedCompletionSnapshot:
    """Canonical primitive clone of a selected normalized completion; no tool text.

    ``content_persistence_allowed`` describes only the retained context policy;
    it never authorizes a future durable record.
    """

    source_reference_id: str
    observed_sequence: int
    provider: str
    check_kind: str
    outcome: str
    provider_execution_status: str
    exit_code: int
    source_completion_schema_version: str
    outcome_interpreter_version: str
    classifier_version: str
    normalizer_version: str
    rule_id: str
    local_only: Literal[True] = field(default=True, init=False)
    content_persistence_allowed: Literal[False] = field(default=False, init=False)

@dataclass(slots=True)
class _Receipt:
    review: ClaimGroundingLinkReview; expires_tick: float; used: bool = False; reserved_owner: str | None = None; reservation_token: str | None = None; reviewed_decision: ClaimGroundingLinkReviewedDecision | None = None

class ClaimGroundingLinkReviewService:
    def __init__(self, sources: CurrentClaimGroundingLinkSourceResolver, contexts: _Contexts,
                 identifiers: ClaimGroundingIdFactory, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC), token_factory: Callable[[], str] = lambda: secrets.token_hex(32)) -> None:
        self._sources, self._contexts, self._ids, self._clock = sources, contexts, identifiers, clock
        import time
        self._receipts: OrderedDict[str, _Receipt] = OrderedDict(); self._lock = RLock(); self._monotonic = time.monotonic; self._tokens = token_factory; self._nonce = 0; self._generation = 0; self._session_generations: dict[str, int] = {}; self._closed = False

    def begin_review(self, *, session_id: str, census_id: str, candidate_id: str,
                     selected_check_references: tuple[str, ...]) -> ClaimGroundingLinkReview:
        if (any(PSEUDONYM_PATTERN.fullmatch(value) is None for value in (session_id, census_id, candidate_id, *selected_check_references))
            or len(selected_check_references) > 128 or len(set(selected_check_references)) != len(selected_check_references)):
            raise ClaimGroundingLinkReviewConflictError("selected observed checks changed")
        with self._lock:
            if self._closed: raise ClaimGroundingLinkReviewUnavailableError("claim link review is closed")
            generation = self._generation; session_generation = self._session_generations.get(session_id, 0)
        source, manifest_fingerprint = self._sources.material_descriptor(session_id=session_id, census_id=census_id, candidate_id=candidate_id)
        allowed = {x.source_reference_id for x in source.observed_set.completions}
        if len(set(selected_check_references)) != len(selected_check_references) or any(x not in allowed for x in selected_check_references):
            raise ClaimGroundingLinkReviewConflictError("selected observed checks changed")
        try:
            clause = self._contexts.exact_active_claim_grounding_clause(session_id=session_id, source_run_id=source.source_run_id, source_window_fingerprint=source.source_window_fingerprint, candidate_id=candidate_id, manifest_fingerprint=manifest_fingerprint, identifiers=self._ids)
            previews = []
            for reference in selected_check_references:
                completion, descriptor = self._contexts.exact_active_observed_check(session_id=session_id, source_run_id=source.source_run_id, source_window_fingerprint=source.source_window_fingerprint, source_reference_id=reference)
                if descriptor.invocation_truncated or descriptor.result_or_effect_truncated:
                    raise ValueError("observed check descriptor is incomplete")
                source_completion = next((item for item in source.observed_set.completions if item.source_reference_id == reference), None)
                if source_completion != completion:
                    raise ValueError("observed check changed")
                previews.append(ClaimObservedCheckPreview(source_reference_id=reference, observed_sequence=completion.observed_sequence, outcome=completion.outcome.value, tool_name=descriptor.tool_name, invocation_preview=descriptor.invocation_preview, effect_preview=descriptor.result_or_effect_preview))
        except Exception as error:
            raise ClaimGroundingLinkReviewUnavailableError("current local review context is unavailable") from error
        # Re-read fences source after all local prose/descriptor access.
        fresh = self._sources.current_source(session_id=session_id, census_id=census_id)
        if not self._same_source(source, fresh, session_id=session_id, census_id=census_id):
            raise ClaimGroundingLinkReviewConflictError("claim link source changed")
        with self._lock:
            if self._closed or generation != self._generation or session_generation != self._session_generations.get(session_id, 0):
                raise ClaimGroundingLinkReviewUnavailableError("claim link review is closed")
            self._nonce += 1
            nonce = str(self._nonce)
        token = self._tokens()
        if PSEUDONYM_PATTERN.fullmatch(token) is None: raise ClaimGroundingLinkReviewUnavailableError("claim link review token is invalid")
        receipt_id = self._ids.fingerprint("claim-grounding-link-review-receipt-v1", (
            session_id, census_id, candidate_id, source.source_run_id,
            source.source_window_fingerprint, source.census_fingerprint,
            manifest_fingerprint, source.observed_set.observed_set_fingerprint,
            *selected_check_references, nonce, token,
        ))
        descriptor_payload = json.dumps({
            "claim_clause": clause.text.get_secret_value(),
            "checks": [
                {
                    "effect_preview": None if item.effect_preview is None else item.effect_preview.get_secret_value(),
                    "invocation_preview": item.invocation_preview.get_secret_value(),
                    "source_reference_id": item.source_reference_id,
                    "tool_name": item.tool_name.get_secret_value(),
                }
                for item in sorted(previews, key=lambda item: item.source_reference_id)
            ],
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        descriptor = self._ids.fingerprint("claim-grounding-link-review-descriptor-v1", (
            source.census_fingerprint, manifest_fingerprint, descriptor_payload,
        ))
        fingerprint = self._ids.fingerprint("claim-grounding-link-review-v1", (receipt_id, source.source_run_id, source.source_window_fingerprint, source.census_fingerprint, manifest_fingerprint, source.observed_set.observed_set_fingerprint, descriptor))
        review = ClaimGroundingLinkReview(session_id=session_id, census_id=census_id, candidate_id=candidate_id, source_run_id=source.source_run_id, source_window_fingerprint=source.source_window_fingerprint, census_fingerprint=source.census_fingerprint, manifest_fingerprint=manifest_fingerprint, observed_set_fingerprint=source.observed_set.observed_set_fingerprint, review_receipt_id=receipt_id, review_fingerprint=fingerprint, review_expires_at=self._clock() + _TTL, claim_clause=clause.text, observed_checks=tuple(previews))
        with self._lock:
            if self._closed or generation != self._generation or session_generation != self._session_generations.get(session_id, 0):
                raise ClaimGroundingLinkReviewUnavailableError("claim link review is closed")
            if len(self._receipts) >= _MAX_RECEIPTS and all(item.reserved_owner is not None for item in self._receipts.values()):
                raise ClaimGroundingLinkReviewUnavailableError("claim link review capacity is unavailable")
            self._receipts[receipt_id] = _Receipt(review, self._monotonic() + _TTL.total_seconds()); self._receipts.move_to_end(receipt_id)
            while len(self._receipts) > _MAX_RECEIPTS:
                evict = next((key for key, item in self._receipts.items() if item.reserved_owner is None), None)
                if evict is None:
                    self._receipts.pop(receipt_id, None)
                    raise ClaimGroundingLinkReviewUnavailableError("claim link review capacity is unavailable")
                self._receipts.pop(evict)
        return review

    def candidate_manifest(self, *, session_id: str, census_id: str):  # type: ignore[no-untyped-def]
        """Expose only the resolver's content-free, current selection surface."""
        return self._sources.candidate_manifest(session_id=session_id, census_id=census_id)

    def reserve(self, *, command: ClaimGroundingLinkCoverageCommand, owner: str) -> ClaimGroundingLinkReviewReservation:
        try:
            command = ClaimGroundingLinkCoverageCommand.model_validate(command.model_dump())
        except Exception as error:
            raise ClaimGroundingLinkReviewConflictError("claim link coverage decision is invalid") from error
        if not isinstance(owner, str) or not 1 <= len(owner) <= 128:
            raise ClaimGroundingLinkReviewConflictError("claim link review owner is invalid")
        with self._lock:
            receipt = self._receipts.get(command.review_receipt_id)
            if receipt is None or receipt.used or receipt.review.session_id != command.session_id or receipt.review.review_fingerprint != command.review_fingerprint or receipt.review.review_expires_at <= self._clock() or receipt.expires_tick <= self._monotonic() or receipt.reserved_owner is not None:
                raise ClaimGroundingLinkReviewConflictError("claim link review is unavailable")
            census_id, generation, snapshot_receipt = receipt.review.census_id, self._generation, receipt
        try:
            fresh = self._sources.current_source(session_id=command.session_id, census_id=census_id)
        except Exception as error:
            raise ClaimGroundingLinkReviewConflictError("claim link source changed") from error
        with self._lock:
            receipt = self._receipts.get(command.review_receipt_id)
            if (self._closed or generation != self._generation or receipt is not snapshot_receipt or receipt.used
                or receipt.review.census_id != census_id or receipt.review.session_id != command.session_id
                or receipt.review.review_fingerprint != command.review_fingerprint
                or receipt.review.review_expires_at <= self._clock()
                or receipt.expires_tick <= self._monotonic()
                or receipt.reserved_owner is not None):
                raise ClaimGroundingLinkReviewConflictError("claim link review changed")
            if not self._same_source(fresh, receipt.review, session_id=command.session_id, census_id=census_id):
                raise ClaimGroundingLinkReviewConflictError("claim link source changed")
            available = {item.source_reference_id for item in receipt.review.observed_checks}
            refs = command.selected_check_references
            if (len(set(refs)) != len(refs)
                or ((command.decision is ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS) and set(refs) != available)
                or ((command.decision is not ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS) and refs)
                or ((command.decision is ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS) != bool(refs))):
                raise ClaimGroundingLinkReviewConflictError("claim link coverage decision is invalid")
            selected_completions = tuple(sorted(
                (item for item in fresh.observed_set.completions if item.source_reference_id in refs),
                key=lambda item: item.source_reference_id,
            ))
            if tuple(item.source_reference_id for item in selected_completions) != tuple(sorted(refs)):
                raise ClaimGroundingLinkReviewConflictError("claim link coverage decision is invalid")
            decision = ClaimGroundingLinkReviewedDecision(
                session_id=receipt.review.session_id, census_id=receipt.review.census_id,
                candidate_id=receipt.review.candidate_id,
                source_run_id=receipt.review.source_run_id,
                source_window_fingerprint=receipt.review.source_window_fingerprint,
                census_fingerprint=receipt.review.census_fingerprint,
                manifest_fingerprint=receipt.review.manifest_fingerprint,
                observed_set_fingerprint=receipt.review.observed_set_fingerprint,
                review_receipt_id=receipt.review.review_receipt_id,
                review_fingerprint=receipt.review.review_fingerprint,
                decision=command.decision,
                selected_check_references=tuple(sorted(refs)),
                selected_observed_completions=tuple(
                    ClaimGroundingLinkObservedCompletionSnapshot(
                        source_reference_id=item.source_reference_id,
                        observed_sequence=item.observed_sequence,
                        provider=item.provider.value, check_kind=item.check_kind.value,
                        outcome=item.outcome.value,
                        provider_execution_status=item.provider_execution_status,
                        exit_code=item.exit_code,
                        source_completion_schema_version=item.source_completion_schema_version,
                        outcome_interpreter_version=item.outcome_interpreter_version,
                        classifier_version=item.classifier_version,
                        normalizer_version=item.normalizer_version, rule_id=item.rule_id,
                    )
                    for item in selected_completions
                ),
            )
            self._nonce += 1
            unique = self._tokens()
            if PSEUDONYM_PATTERN.fullmatch(unique) is None: raise ClaimGroundingLinkReviewUnavailableError("claim link review token is invalid")
            token = self._ids.fingerprint("claim-grounding-link-review-reservation-v1", (command.review_receipt_id, owner, str(self._nonce), unique))
            receipt.reserved_owner = owner
            receipt.reservation_token = token
            receipt.reviewed_decision = decision
            return ClaimGroundingLinkReviewReservation(command.review_receipt_id, owner, token)

    def snapshot_under_reservation(self, reservation: ClaimGroundingLinkReviewReservation) -> ClaimGroundingLinkReviewedDecision:
        """Read the immutable decision only while its exact lease remains valid."""
        with self._lock:
            receipt = self._receipts.get(reservation.receipt_id)
            if (receipt is None or receipt.used or receipt.reserved_owner != reservation.owner
                or receipt.reservation_token != reservation.token
                or receipt.reviewed_decision is None
                or receipt.expires_tick <= self._monotonic()
                or receipt.review.review_expires_at <= self._clock()):
                raise ClaimGroundingLinkReviewConflictError("claim link review changed")
            return receipt.reviewed_decision

    def finalize(self, reservation: ClaimGroundingLinkReviewReservation) -> None:
        with self._lock:
            receipt = self._receipts.get(reservation.receipt_id)
            if receipt is None or receipt.reserved_owner != reservation.owner or receipt.reservation_token != reservation.token: raise ClaimGroundingLinkReviewConflictError("claim link review changed")
            receipt.used = True; receipt.reserved_owner = None; receipt.reservation_token = None; receipt.reviewed_decision = None

    def release(self, reservation: ClaimGroundingLinkReviewReservation) -> None:
        with self._lock:
            receipt = self._receipts.get(reservation.receipt_id)
            if receipt is not None and receipt.reserved_owner == reservation.owner and receipt.reservation_token == reservation.token: receipt.reserved_owner = None; receipt.reservation_token = None; receipt.reviewed_decision = None

    def issue_under_reservation(self, reservation: ClaimGroundingLinkReviewReservation, operation: Callable[[], object]) -> object:
        """Run a future durable write atomically with the reservation state."""
        with self._lock:
            receipt = self._receipts.get(reservation.receipt_id)
            if (receipt is None or receipt.used or receipt.reserved_owner != reservation.owner
                or receipt.reservation_token != reservation.token
                or receipt.reviewed_decision is None
                or receipt.expires_tick <= self._monotonic()
                or receipt.review.review_expires_at <= self._clock()):
                raise ClaimGroundingLinkReviewConflictError("claim link review changed")
            return operation()

    def close(self) -> None:
        with self._lock:
            self._closed = True; self._generation += 1; self._receipts.clear()

    @staticmethod
    def _same_source(left, right, *, session_id: str, census_id: str) -> bool:  # type: ignore[no-untyped-def]
        try:
            left_observed = left.observed_set.observed_set_fingerprint
            right_observed = right.observed_set_fingerprint if isinstance(right, ClaimGroundingLinkReview) else right.observed_set.observed_set_fingerprint
            return (left.session_id == right.session_id == session_id and left.census_id == right.census_id == census_id
                and left.source_run_id == right.source_run_id and left.source_window_fingerprint == right.source_window_fingerprint
                and left.census_fingerprint == right.census_fingerprint
                and left_observed == right_observed)
        except AttributeError:
            return False

    def revoke_session(self, session_id: str) -> None:
        """Invalidate one owner's receipts and any in-flight construction."""
        with self._lock:
            self._session_generations[session_id] = self._session_generations.get(session_id, 0) + 1
            for key in tuple(self._receipts):
                if self._receipts[key].review.session_id == session_id:
                    self._receipts.pop(key)
