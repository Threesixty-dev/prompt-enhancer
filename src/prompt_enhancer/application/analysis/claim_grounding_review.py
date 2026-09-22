"""Ephemeral review receipts for one current claim-grounding census.

This is deliberately a review-store foundation, not a native-confirmed or
metric-authority flow.  A future HTTP composition must put both operations
behind the application's existing owned native-confirmation dependency.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from secrets import token_hex
from threading import RLock
from time import monotonic
from typing import Callable, Literal, Protocol

from pydantic import Field, field_validator

from ...domain import PSEUDONYM_PATTERN, StrictModel
from .claim_grounding_evidence import (
    ClaimCensusClassificationEntry,
    ClaimCensusSourceManifest,
    ClaimGroundingIdFactory,
    EphemeralClaimReviewCandidate,
    ReviewedClaimCensus,
    build_reviewed_claim_census,
    derive_claim_census_source_manifest,
    validate_claim_census_source_manifest,
    validate_reviewed_claim_census,
)
from .text_contracts import P1TextAnalysisInput


CLAIM_GROUNDING_REVIEW_TTL = timedelta(minutes=5)
MAX_ACTIVE_CLAIM_GROUNDING_REVIEWS = 32
CLAIM_GROUNDING_REVIEW_SCHEMA_VERSION = "claim-grounding-native-review-v1"
CLAIM_GROUNDING_REVIEW_POLICY_VERSION = "current-sealed-source-complete-census-v1"


def _id(value: str) -> str:
    if PSEUDONYM_PATTERN.fullmatch(value) is None:
        raise ValueError("claim grounding review identifier is invalid")
    return value


def _require_id(value: object) -> str:
    if not isinstance(value, str):
        raise ClaimGroundingReviewConflictError("claim review request is invalid")
    try:
        return _id(value)
    except ValueError:
        raise ClaimGroundingReviewConflictError("claim review request is invalid") from None


class ClaimGroundingReviewError(RuntimeError):
    """Closed application error; it never carries review prose."""


class ClaimGroundingReviewUnavailableError(ClaimGroundingReviewError):
    pass


class ClaimGroundingReviewConflictError(ClaimGroundingReviewError):
    pass


@dataclass(frozen=True, slots=True)
class CurrentClaimGroundingSource:
    """Server-owned, ephemeral context for the current sealed source only."""

    source_run_id: str
    source_window_fingerprint: str
    context: P1TextAnalysisInput


class ClaimGroundingCurrentSource(Protocol):
    """Production composition must resolve a sealed current source here."""

    def current_source(self, session_id: str) -> CurrentClaimGroundingSource: ...


class CurrentClaimGroundingSourceResolver:
    """Resolve only the current published run and its retained census surface."""

    def __init__(self, repository, review_contexts, identifiers: ClaimGroundingIdFactory) -> None:
        self._repository = repository
        self._review_contexts = review_contexts
        self._identifiers = identifiers

    def current_source_for_review(
        self, *, session_id: str, expected_source_run_id: str,
        expected_source_window_fingerprint: str,
    ) -> tuple[ClaimCensusSourceManifest, tuple[EphemeralClaimReviewCandidate, ...]]:
        session_id = _require_id(session_id)
        expected_source_run_id = _require_id(expected_source_run_id)
        expected_source_window_fingerprint = _require_id(expected_source_window_fingerprint)
        try:
            latest = self._repository.get_latest(session_id)
        except Exception:
            raise ClaimGroundingReviewUnavailableError("current claim review source is unavailable") from None
        if latest is None or getattr(getattr(latest, "receipt", None), "metric_publication_v2", None) is None:
            raise ClaimGroundingReviewUnavailableError("current claim review source is unavailable")
        if (
            latest.session_id != session_id or latest.run_id != expected_source_run_id
            or latest.input_fingerprint != expected_source_window_fingerprint
        ):
            raise ClaimGroundingReviewConflictError("current claim review source changed")
        try:
            projection = self._review_contexts.project_current_claim_census(
                session_id=session_id, source_run_id=latest.run_id,
                source_window_fingerprint=latest.input_fingerprint,
                identifiers=self._identifiers,
            )
            reread = self._repository.get_latest(session_id)
        except Exception:
            raise ClaimGroundingReviewUnavailableError("current claim review source is unavailable") from None
        if (
            reread is None or getattr(getattr(reread, "receipt", None), "metric_publication_v2", None) is None
        ):
            raise ClaimGroundingReviewUnavailableError("current claim review source is unavailable")
        if (
            reread.session_id != latest.session_id or reread.run_id != latest.run_id
            or reread.input_fingerprint != latest.input_fingerprint
            or reread.receipt.metric_publication_v2 != latest.receipt.metric_publication_v2
        ):
            raise ClaimGroundingReviewConflictError("current claim review source changed")
        manifest, candidates = projection
        try:
            validate_claim_census_source_manifest(manifest, identifiers=self._identifiers)
            if (
                manifest.session_id != latest.session_id
                or manifest.source_run_id != latest.run_id
                or manifest.source_window_fingerprint != latest.input_fingerprint
                or tuple(item.candidate_id for item in candidates)
                != tuple(item.candidate_id for item in manifest.candidates)
            ):
                raise ValueError("claim census projection is not exact")
        except Exception:
            raise ClaimGroundingReviewConflictError("current claim review source changed") from None
        return projection


class UncomposedClaimGroundingSourceResolver:
    """Safe default until a sealed-run/context composition exists."""

    def current_source(self, session_id: str) -> CurrentClaimGroundingSource:
        _require_id(session_id)
        raise ClaimGroundingReviewUnavailableError("current claim review source is unavailable")


class ClaimGroundingCensusReviewProposal(StrictModel):
    """Ephemeral native-review surface; serializing it excludes candidate prose."""

    session_id: str
    source_run_id: str
    source_window_fingerprint: str
    manifest: ClaimCensusSourceManifest
    candidates: tuple[EphemeralClaimReviewCandidate, ...] = Field(max_length=12_800)
    review_receipt_id: str
    review_fingerprint: str
    review_expires_at: datetime
    native_confirmation_completed: Literal[False] = False
    metric_authority_established: Literal[False] = False
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False
    schema_version: Literal[CLAIM_GROUNDING_REVIEW_SCHEMA_VERSION] = CLAIM_GROUNDING_REVIEW_SCHEMA_VERSION
    policy_version: Literal[CLAIM_GROUNDING_REVIEW_POLICY_VERSION] = CLAIM_GROUNDING_REVIEW_POLICY_VERSION

    _ids = field_validator(
        "session_id", "source_run_id", "source_window_fingerprint",
        "review_receipt_id", "review_fingerprint",
    )(_id)


@dataclass(frozen=True, slots=True)
class _Receipt:
    review: ClaimGroundingCensusReviewProposal
    expires_monotonic: float


@dataclass(frozen=True, slots=True)
class ClaimGroundingReviewReservation:
    """Opaque, short-lived lease; it is not confirmation or metric authority."""
    _token: str
    census: ReviewedClaimCensus
    manifest: ClaimCensusSourceManifest


class ClaimGroundingReviewService:
    """Issue and consume a one-use receipt for an exact current census.

    This service deliberately owns no native confirmation.  It is useful only
    after a later application composition supplies a sealed-source resolver and
    exposes its methods under the existing HTTP native-confirmation boundary.
    """

    def __init__(
        self,
        source: ClaimGroundingCurrentSource,
        identifiers: ClaimGroundingIdFactory,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic_clock: Callable[[], float] = monotonic,
        token_factory: Callable[[], str] = lambda: token_hex(32),
        max_active: int = MAX_ACTIVE_CLAIM_GROUNDING_REVIEWS,
    ) -> None:
        if not 1 <= max_active <= MAX_ACTIVE_CLAIM_GROUNDING_REVIEWS:
            raise ValueError("claim grounding review capacity is outside its bound")
        self._source, self._identifiers = source, identifiers
        self._clock, self._monotonic, self._tokens = clock, monotonic_clock, token_factory
        self._max_active = max_active
        self._receipts: OrderedDict[str, _Receipt] = OrderedDict()
        self._used: OrderedDict[str, str] = OrderedDict()
        self._reserved: dict[str, tuple[str, _Receipt, str, int]] = {}
        self._lock = RLock()
        self._closed = False
        self._session_generations: dict[str, int] = {}
        self._inflight: dict[str, int] = {}
        self._last_monotonic: float | None = None

    def begin_review(
        self, *, session_id: str, expected_source_run_id: str | None = None,
        expected_source_window_fingerprint: str | None = None,
    ) -> ClaimGroundingCensusReviewProposal:
        """Expose the exact current bounded candidate set for native review."""
        session_id = _require_id(session_id)
        now, tick = self._time()
        with self._lock:
            self._require_open_locked()
            generation = self._start_inflight_locked(session_id)
        try:
            manifest, candidates = self._fresh_manifest(
                session_id, expected_source_run_id, expected_source_window_fingerprint
            )
            now, tick = self._time()
            receipt_id, fingerprint = self._issued_tokens()
            review = ClaimGroundingCensusReviewProposal(
                session_id=session_id, source_run_id=manifest.source_run_id,
                source_window_fingerprint=manifest.source_window_fingerprint,
                manifest=manifest, candidates=candidates,
                review_receipt_id=receipt_id, review_fingerprint=fingerprint,
                review_expires_at=now + CLAIM_GROUNDING_REVIEW_TTL,
            )
            with self._lock:
                if self._closed:
                    raise ClaimGroundingReviewUnavailableError("claim review service is unavailable")
                if generation != self._session_generations.get(session_id, 0):
                    raise ClaimGroundingReviewConflictError("claim review was revoked")
                self._expire_locked(now, tick)
                if receipt_id in self._receipts or receipt_id in self._used:
                    raise ClaimGroundingReviewConflictError("claim review receipt collision")
                if self._reserved and len(self._receipts) + len(self._reserved) >= self._max_active:
                    raise ClaimGroundingReviewUnavailableError("claim review capacity is unavailable")
                self._receipts[receipt_id] = _Receipt(
                    review=review,
                    expires_monotonic=tick + CLAIM_GROUNDING_REVIEW_TTL.total_seconds(),
                )
                while len(self._receipts) > self._max_active:
                    self._receipts.popitem(last=False)
            return review
        finally:
            with self._lock:
                self._finish_inflight_locked(session_id)

    def consume_review(
        self, *, session_id: str, review_receipt_id: str,
        review_fingerprint: str, manifest_fingerprint: str,
        classifications: tuple[ClaimCensusClassificationEntry, ...],
    ) -> ReviewedClaimCensus:
        """Consume only after the current source and exact census still match."""
        session_id, review_receipt_id, review_fingerprint, manifest_fingerprint = (
            _require_id(value)
            for value in (session_id, review_receipt_id, review_fingerprint, manifest_fingerprint)
        )
        now, tick = self._time()
        with self._lock:
            self._require_open_locked()
            generation = self._start_inflight_locked(session_id)
            self._expire_locked(now, tick)
            receipt = self._receipts.pop(review_receipt_id, None)
            if receipt is not None:
                self._used[review_receipt_id] = receipt.review.session_id
            while len(self._used) > self._max_active * 2:
                self._used.popitem(last=False)
        try:
            if (
                receipt is None
                or receipt.expires_monotonic <= tick
                or receipt.review.review_expires_at <= now
                or receipt.review.review_fingerprint != review_fingerprint
                or receipt.review.session_id != session_id
                or receipt.review.manifest.manifest_fingerprint != manifest_fingerprint
            ):
                raise ClaimGroundingReviewConflictError("claim review receipt is unavailable")
            review = receipt.review
            manifest, _ = self._fresh_manifest(
                session_id, review.source_run_id, review.source_window_fingerprint
            )
            if (
                manifest != review.manifest
                or manifest.source_run_id != review.source_run_id
                or manifest.source_window_fingerprint != review.source_window_fingerprint
            ):
                raise ClaimGroundingReviewConflictError("claim review source changed")
            census = build_reviewed_claim_census(
                manifest, classifications=classifications, identifiers=self._identifiers,
            )
            validate_reviewed_claim_census(census, manifest, identifiers=self._identifiers)
            now, tick = self._time()
            with self._lock:
                closed = self._closed
                revoked = generation != self._session_generations.get(session_id, 0)
                expired = receipt.expires_monotonic <= tick or review.review_expires_at <= now
            if closed:
                raise ClaimGroundingReviewUnavailableError("claim review service is unavailable")
            if revoked:
                raise ClaimGroundingReviewConflictError("claim review was revoked")
            if expired:
                raise ClaimGroundingReviewConflictError("claim review receipt is unavailable")
            return census
        except ClaimGroundingReviewError:
            raise
        except Exception:
            raise ClaimGroundingReviewConflictError("claim review census changed") from None
        finally:
            with self._lock:
                self._finish_inflight_locked(session_id)

    def revoke_session(self, session_id: str) -> None:
        """Dispose all ephemeral prose-bearing review surfaces for one session."""
        session_id = _require_id(session_id)
        with self._lock:
            if session_id in self._inflight:
                self._session_generations[session_id] = (
                    self._session_generations.get(session_id, 0) + 1
                )
            for receipt_id in tuple(
                key for key, value in self._receipts.items()
                if value.review.session_id == session_id
            ):
                del self._receipts[receipt_id]
            for receipt_id in tuple(
                key for key, value in self._used.items() if value == session_id
            ):
                del self._used[receipt_id]
            for reservation_id, (receipt_id, receipt, _, _) in tuple(self._reserved.items()):
                if receipt.review.session_id == session_id:
                    del self._reserved[reservation_id]

    def close(self) -> None:
        """Dispose all ephemeral review state on unmount/shutdown."""
        with self._lock:
            self._closed = True
            self._receipts.clear()
            self._used.clear()
            self._reserved.clear()

    def prepare_durable_consume(
        self, *, session_id: str, review_receipt_id: str, review_fingerprint: str,
        manifest_fingerprint: str,
        classifications: tuple[ClaimCensusClassificationEntry, ...], owner: str,
    ) -> ClaimGroundingReviewReservation:
        """Reserve an exact receipt for one durable transaction without consuming it."""
        session_id, review_receipt_id, review_fingerprint, manifest_fingerprint, owner = (
            _require_id(value) for value in (
                session_id, review_receipt_id, review_fingerprint, manifest_fingerprint, owner
            )
        )
        now, tick = self._time()
        with self._lock:
            self._require_open_locked(); self._expire_locked(now, tick)
            if any(item[0] == review_receipt_id for item in self._reserved.values()):
                raise ClaimGroundingReviewConflictError("claim review receipt is reserved")
            receipt = self._receipts.get(review_receipt_id)
            if receipt is None or receipt.expires_monotonic <= tick or receipt.review.review_expires_at <= now:
                raise ClaimGroundingReviewConflictError("claim review receipt is unavailable")
            review = receipt.review
            if (review.review_fingerprint != review_fingerprint or review.session_id != session_id
                or review.manifest.manifest_fingerprint != manifest_fingerprint):
                raise ClaimGroundingReviewConflictError("claim review receipt is unavailable")
            # Allocate before consuming the receipt: token errors/collisions
            # cannot strand a one-use review or its inflight accounting.
            reservation_id, _ = self._issued_tokens()
            if (reservation_id in self._reserved or reservation_id in self._receipts
                or reservation_id in self._used):
                raise ClaimGroundingReviewConflictError("claim review reservation collision")
            generation = self._start_inflight_locked(session_id)
            popped = self._receipts.pop(review_receipt_id, None)
            if popped is not receipt:
                self._finish_inflight_locked(session_id)
                raise ClaimGroundingReviewConflictError("claim review receipt is unavailable")
            self._reserved[reservation_id] = (review_receipt_id, receipt, owner, generation)
        try:
            manifest, _ = self._fresh_manifest(session_id, review.source_run_id, review.source_window_fingerprint)
            if manifest != review.manifest:
                raise ClaimGroundingReviewConflictError("claim review source changed")
            census = build_reviewed_claim_census(manifest, classifications=classifications, identifiers=self._identifiers)
            validate_reviewed_claim_census(census, manifest, identifiers=self._identifiers)
            now, tick = self._time()
            with self._lock:
                item = self._reserved.get(reservation_id)
                if (self._closed or item is None or item[2] != owner or item[3] != generation
                    or generation != self._session_generations.get(session_id, 0)
                    or item[1].expires_monotonic <= tick or item[1].review.review_expires_at <= now):
                    removed = self._reserved.pop(reservation_id, None)
                    if removed is not None:
                        self._finish_inflight_locked(session_id)
                    raise ClaimGroundingReviewConflictError("claim review reservation is unavailable")
            return ClaimGroundingReviewReservation(reservation_id, census, manifest)
        except ClaimGroundingReviewError:
            with self._lock:
                item = self._reserved.pop(locals().get("reservation_id", ""), None)
                if item is not None and not self._closed and item[2] == owner:
                    self._receipts[item[0]] = item[1]
                if item is not None:
                    self._finish_inflight_locked(session_id)
            raise
        except Exception:
            with self._lock:
                item = self._reserved.pop(locals().get("reservation_id", ""), None)
                if item is not None and not self._closed and item[2] == owner:
                    self._receipts[item[0]] = item[1]
                if item is not None:
                    self._finish_inflight_locked(session_id)
            raise ClaimGroundingReviewConflictError("claim review census changed") from None

    def finalize_durable_reservation(self, reservation: ClaimGroundingReviewReservation, *, owner: str) -> None:
        self._finish_durable_reservation(reservation, owner=owner, consume=True)

    def release_durable_reservation(self, reservation: ClaimGroundingReviewReservation, *, owner: str) -> None:
        self._finish_durable_reservation(reservation, owner=owner, consume=False)

    def assert_durable_reservation(self, reservation: ClaimGroundingReviewReservation, *, owner: str) -> None:
        """Fence a slow authority lookup immediately before durable issuance."""
        owner = _require_id(owner); now, tick = self._time()
        with self._lock:
            item = self._reserved.get(reservation._token)
            if (self._closed or item is None or item[2] != owner
                or item[3] != self._session_generations.get(item[1].review.session_id, 0)
                or item[1].expires_monotonic <= tick or item[1].review.review_expires_at <= now):
                raise ClaimGroundingReviewConflictError("claim review reservation is unavailable")

    def issue_durable_reservation(self, reservation: ClaimGroundingReviewReservation, *, owner: str, operation):
        """Linearize the single durable write against revocation."""
        owner = _require_id(owner)
        with self._lock:
            # Refresh after any wait for the commit lock; expiry while queued is
            # a conflict, never an authority to issue.
            now, tick = self._time()
            item = self._reserved.get(reservation._token)
            if (self._closed or item is None or item[2] != owner
                or item[3] != self._session_generations.get(item[1].review.session_id, 0)
                or item[1].expires_monotonic <= tick or item[1].review.review_expires_at <= now):
                raise ClaimGroundingReviewConflictError("claim review reservation is unavailable")
            return operation()

    def _finish_durable_reservation(self, reservation: ClaimGroundingReviewReservation, *, owner: str, consume: bool) -> None:
        owner = _require_id(owner)
        now_tick = None if consume else self._time()
        with self._lock:
            item = self._reserved.get(reservation._token)
            if item is None or item[2] != owner:
                raise ClaimGroundingReviewConflictError("claim review reservation is unavailable")
            receipt_id, receipt, _, generation = item; del self._reserved[reservation._token]
            if self._closed or generation != self._session_generations.get(receipt.review.session_id, 0):
                self._finish_inflight_locked(receipt.review.session_id)
                raise ClaimGroundingReviewConflictError("claim review reservation is unavailable")
            if consume:
                self._used[receipt_id] = receipt.review.session_id
                while len(self._used) > self._max_active * 2:
                    self._used.popitem(last=False)
            else:
                assert now_tick is not None
                now, tick = now_tick
                if not self._closed and receipt.expires_monotonic > tick and receipt.review.review_expires_at > now:
                    self._receipts[receipt_id] = receipt
            self._finish_inflight_locked(receipt.review.session_id)

    def _fresh_manifest(
        self, session_id: str, expected_source_run_id: str | None = None,
        expected_source_window_fingerprint: str | None = None,
    ) -> tuple[ClaimCensusSourceManifest, tuple[EphemeralClaimReviewCandidate, ...]]:
        _require_id(session_id)
        try:
            resolver = getattr(self._source, "current_source_for_review", None)
            if expected_source_run_id is not None and expected_source_window_fingerprint is not None and callable(resolver):
                manifest, candidates = resolver(
                    session_id=session_id,
                    expected_source_run_id=_require_id(expected_source_run_id),
                    expected_source_window_fingerprint=_require_id(expected_source_window_fingerprint),
                )
                self._validate_projection(
                    manifest=manifest, candidates=candidates, session_id=session_id,
                    source_run_id=expected_source_run_id,
                    source_window_fingerprint=expected_source_window_fingerprint,
                )
                return manifest, candidates
            source = self._source.current_source(session_id)
        except ClaimGroundingReviewError:
            raise
        except Exception:
            raise ClaimGroundingReviewUnavailableError(
                "current claim review source is unavailable"
            ) from None
        try:
            coherent = (
                source.context.session_id == session_id
                and source.context.analysis_window_fingerprint == source.source_window_fingerprint
            )
        except (AttributeError, TypeError):
            raise ClaimGroundingReviewUnavailableError(
                "current claim review source is unavailable"
            ) from None
        if not coherent:
            raise ClaimGroundingReviewConflictError("current claim review source changed")
        try:
            return derive_claim_census_source_manifest(
                source.context, source_run_id=source.source_run_id,
                identifiers=self._identifiers,
            )
        except Exception:
            raise ClaimGroundingReviewConflictError("current claim review source is invalid") from None

    def _validate_projection(
        self, *, manifest: ClaimCensusSourceManifest,
        candidates: tuple[EphemeralClaimReviewCandidate, ...], session_id: str,
        source_run_id: str, source_window_fingerprint: str,
    ) -> None:
        """Reject an injected projection before any candidate prose is exposed."""
        try:
            manifest = ClaimCensusSourceManifest.model_validate(manifest.model_dump())
            validate_claim_census_source_manifest(manifest, identifiers=self._identifiers)
            if (
                manifest.session_id != session_id or manifest.source_run_id != source_run_id
                or manifest.source_window_fingerprint != source_window_fingerprint
                or manifest.candidate_count != len(candidates)
            ):
                raise ValueError("claim census projection provenance is invalid")
            manifest_by_id = {item.candidate_id: item for item in manifest.candidates}
            candidate_ids = tuple(item.candidate_id for item in candidates)
            if (
                len(manifest_by_id) != len(candidates)
                or len(set(candidate_ids)) != len(candidates)
                or set(candidate_ids) != set(manifest_by_id)
            ):
                raise ValueError("claim census projection candidates are incomplete")
            for candidate in candidates:
                candidate = EphemeralClaimReviewCandidate.model_validate(
                    candidate.model_dump(exclude={"text"}) | {
                        "text": candidate.text.get_secret_value()
                    }
                )
                expected = manifest_by_id.get(candidate.candidate_id)
                expected_id = self._identifiers.fingerprint(
                    "claim-grounding-census-candidate-v1",
                    (
                        manifest.session_id, manifest.source_window_fingerprint,
                        candidate.message_id, str(candidate.clause_index),
                    ),
                )
                if expected is None or (
                    candidate.message_id != expected.message_id
                    or candidate.message_sequence != expected.message_sequence
                    or candidate.clause_index != expected.clause_index
                    or candidate.candidate_id != expected_id
                    or not candidate.text.get_secret_value()
                ):
                    raise ValueError("claim census projection candidate is invalid")
        except Exception:
            raise ClaimGroundingReviewConflictError("current claim review source is invalid") from None

    def _time(self) -> tuple[datetime, float]:
        try:
            value = self._clock()
            tick = self._monotonic()
        except Exception:
            raise ClaimGroundingReviewUnavailableError("claim review clock is unavailable") from None
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
            or not isinstance(tick, (int, float))
            or isinstance(tick, bool)
            or not isfinite(tick)
        ):
            raise ClaimGroundingReviewUnavailableError("claim review clock is unavailable")
        with self._lock:
            if self._last_monotonic is not None and tick < self._last_monotonic:
                raise ClaimGroundingReviewUnavailableError("claim review clock is unavailable")
            self._last_monotonic = float(tick)
        return value.astimezone(UTC), float(tick)

    def _require_open_locked(self) -> None:
        if self._closed:
            raise ClaimGroundingReviewUnavailableError("claim review service is unavailable")

    def _issued_tokens(self) -> tuple[str, str]:
        try:
            receipt_id, fingerprint = self._tokens(), self._tokens()
        except Exception:
            raise ClaimGroundingReviewUnavailableError("claim review receipt is unavailable") from None
        try:
            return _id(receipt_id), _id(fingerprint)
        except (TypeError, ValueError):
            raise ClaimGroundingReviewUnavailableError("claim review receipt is unavailable") from None

    def _start_inflight_locked(self, session_id: str) -> int:
        if session_id not in self._inflight:
            if len(self._inflight) >= self._max_active:
                raise ClaimGroundingReviewUnavailableError("claim review capacity is unavailable")
            self._inflight[session_id] = 0
        self._inflight[session_id] += 1
        return self._session_generations.get(session_id, 0)

    def _finish_inflight_locked(self, session_id: str) -> None:
        remaining = self._inflight.get(session_id, 0) - 1
        if remaining > 0:
            self._inflight[session_id] = remaining
            return
        self._inflight.pop(session_id, None)
        self._session_generations.pop(session_id, None)

    def _expire_locked(self, now: datetime, tick: float) -> None:
        for key in tuple(
            key for key, value in self._receipts.items()
            if value.review.review_expires_at <= now or value.expires_monotonic <= tick
        ):
            del self._receipts[key]
        for key in tuple(key for key, value in self._reserved.items()
                         if value[1].review.review_expires_at <= now or value[1].expires_monotonic <= tick):
            _, receipt, _, _ = self._reserved.pop(key)
            self._finish_inflight_locked(receipt.review.session_id)


__all__ = (
    "CLAIM_GROUNDING_REVIEW_POLICY_VERSION", "CLAIM_GROUNDING_REVIEW_SCHEMA_VERSION",
    "CLAIM_GROUNDING_REVIEW_TTL", "ClaimGroundingCensusReviewProposal",
    "ClaimGroundingCurrentSource", "ClaimGroundingReviewConflictError",
    "ClaimGroundingReviewError", "ClaimGroundingReviewService",
    "ClaimGroundingReviewReservation",
    "ClaimGroundingReviewUnavailableError", "CurrentClaimGroundingSource",
    "CurrentClaimGroundingSourceResolver", "UncomposedClaimGroundingSourceResolver",
)
