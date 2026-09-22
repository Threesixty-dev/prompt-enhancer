"""Durable, content-free claim-census proposal composition; never a metric."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable, Literal, Protocol
import re

from ...domain import PSEUDONYM_PATTERN

from .claim_grounding_evidence import ClaimCensusClassificationEntry, ClaimCensusSourceManifest, ClaimGroundingIdFactory, ReviewedClaimCensus
from .claim_grounding_review import ClaimGroundingReviewConflictError, ClaimGroundingReviewReservation, ClaimGroundingReviewService


class ClaimGroundingCensusError(RuntimeError): pass
class ClaimGroundingCensusInputError(ClaimGroundingCensusError): pass
class ClaimGroundingCensusConflictError(ClaimGroundingCensusError): pass
class ClaimGroundingCensusNotFoundError(ClaimGroundingCensusError): pass
class ClaimGroundingCensusPersistenceError(ClaimGroundingCensusError): pass
class ClaimGroundingCensusOutcomeUnknownError(ClaimGroundingCensusError): pass


@dataclass(frozen=True, slots=True)
class ClaimGroundingCensusRecord:
    census_id: str
    census: ReviewedClaimCensus
    manifest: ClaimCensusSourceManifest
    idempotency_key_digest: str
    command_fingerprint: str
    expected_publication_fingerprint: str
    created_at: datetime
    reviewed_classification_metadata_persisted: Literal[True] = field(default=True, init=False)
    candidate_prose_persisted: Literal[False] = field(default=False, init=False)
    proposal_only: Literal[True] = field(default=True, init=False)
    measured: Literal[False] = field(default=False, init=False)
    metric_authority_established: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class ClaimGroundingCensusPageSnapshot:
    snapshot_id: str; total: int
    high_water_created_at: datetime | None
    high_water_census_id: str | None


class ClaimGroundingCensusRepository(Protocol):
    def issue(self, *, census_id: str, census: ReviewedClaimCensus, manifest: ClaimCensusSourceManifest, idempotency_key_digest: str, command_fingerprint: str, expected_publication_fingerprint: str, created_at: datetime) -> tuple[ClaimGroundingCensusRecord, bool]: ...
    def get(self, census_id: str) -> ClaimGroundingCensusRecord | None: ...
    def get_by_idempotency(self, *, session_id: str, idempotency_key_digest: str) -> ClaimGroundingCensusRecord | None: ...
    def list_page(self, session_id: str, *, limit: int, offset: int, snapshot: ClaimGroundingCensusPageSnapshot | None = None) -> tuple[tuple[ClaimGroundingCensusRecord, ...], ClaimGroundingCensusPageSnapshot]: ...


class ClaimGroundingPublicationAuthority(Protocol):
    def expected_publication_fingerprint(self, *, session_id: str, source_run_id: str, source_window_fingerprint: str) -> str: ...


class DurableClaimGroundingCensusService:
    def __init__(self, reviews: ClaimGroundingReviewService, repository: ClaimGroundingCensusRepository, authority: ClaimGroundingPublicationAuthority, identifiers: ClaimGroundingIdFactory, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._reviews, self._repository, self._authority, self._ids, self._clock = reviews, repository, authority, identifiers, clock

    def consume_and_issue(self, *, session_id: str, review_receipt_id: str, review_fingerprint: str, manifest_fingerprint: str, classifications: tuple[ClaimCensusClassificationEntry, ...], idempotency_key: str) -> ClaimGroundingCensusRecord:
        values = (session_id, review_receipt_id, review_fingerprint, manifest_fingerprint)
        if any(not isinstance(value, str) or PSEUDONYM_PATTERN.fullmatch(value) is None for value in values):
            raise ClaimGroundingCensusInputError("claim census identity is invalid")
        if (not isinstance(idempotency_key, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{16,128}", idempotency_key) is None):
            raise ClaimGroundingCensusInputError("claim census idempotency key is invalid")
        if len(classifications) > 12_800:
            raise ClaimGroundingCensusInputError("claim census classifications are outside their bound")
        try:
            normalized = tuple(ClaimCensusClassificationEntry.model_validate(item.model_dump()) for item in classifications)
        except Exception:
            raise ClaimGroundingCensusInputError("claim census classifications are invalid") from None
        normalized = tuple(sorted(normalized, key=lambda item: item.candidate_id))
        if len({item.candidate_id for item in normalized}) != len(normalized):
            raise ClaimGroundingCensusInputError("claim census classifications are not canonical")
        digest = self._ids.fingerprint("claim-grounding-census-idempotency-v1", (session_id, idempotency_key))
        command = self._ids.fingerprint("claim-grounding-census-command-v1", (session_id, review_receipt_id, review_fingerprint, manifest_fingerprint, *(f"{x.candidate_id}:{x.classification.value}:{x.exclusion_reason or '-'}" for x in normalized)))
        census_id = self._ids.fingerprint("claim-grounding-census-v1", (session_id, digest))
        try: existing = self._repository.get_by_idempotency(session_id=session_id, idempotency_key_digest=digest)
        except Exception as error: raise ClaimGroundingCensusPersistenceError("claim census recovery is unavailable") from error
        if existing is not None:
            if existing.census_id == census_id and existing.command_fingerprint == command:
                return existing
            raise ClaimGroundingCensusConflictError("claim census idempotency key conflicts")
        reservation: ClaimGroundingReviewReservation | None = None
        try:
            reservation = self._reviews.prepare_durable_consume(session_id=session_id, review_receipt_id=review_receipt_id, review_fingerprint=review_fingerprint, manifest_fingerprint=manifest_fingerprint, classifications=normalized, owner=command)
            publication = self._authority.expected_publication_fingerprint(session_id=session_id, source_run_id=reservation.census.source_run_id, source_window_fingerprint=reservation.census.source_window_fingerprint)
            def issue():
                return self._repository.issue(census_id=census_id, census=reservation.census, manifest=reservation.manifest, idempotency_key_digest=digest, command_fingerprint=command, expected_publication_fingerprint=publication, created_at=self._clock())[0]
            record = self._reviews.issue_durable_reservation(reservation, owner=command, operation=issue)
            self._reviews.finalize_durable_reservation(reservation, owner=command)
            return record
        except Exception as error:
            try: reconciled = self._repository.get_by_idempotency(session_id=session_id, idempotency_key_digest=digest)
            except Exception:
                if reservation is not None:
                    try: self._reviews.finalize_durable_reservation(reservation, owner=command)
                    except Exception: pass
                raise ClaimGroundingCensusOutcomeUnknownError("claim census recovery is required") from None
            if reconciled is not None and reconciled.census_id == census_id and reconciled.command_fingerprint == command:
                if reservation is not None:
                    try: self._reviews.finalize_durable_reservation(reservation, owner=command)
                    except ClaimGroundingReviewConflictError: pass
                return reconciled
            if reconciled is not None:
                if reservation is not None:
                    try: self._reviews.finalize_durable_reservation(reservation, owner=command)
                    except ClaimGroundingReviewConflictError: pass
                raise ClaimGroundingCensusConflictError("claim census idempotency key conflicts") from None
            if reservation is not None:
                self._reviews.release_durable_reservation(reservation, owner=command)
            if isinstance(error, ClaimGroundingReviewConflictError):
                raise ClaimGroundingCensusConflictError("claim census source changed") from None
            raise ClaimGroundingCensusPersistenceError("claim census persistence failed") from None

    def get(self, census_id: str) -> ClaimGroundingCensusRecord:
        try:
            record = self._repository.get(census_id)
        except ClaimGroundingReviewConflictError as error:
            raise ClaimGroundingCensusConflictError("claim census binding changed") from error
        except Exception as error:
            raise ClaimGroundingCensusPersistenceError("claim census recovery is unavailable") from error
        if record is None: raise ClaimGroundingCensusNotFoundError("claim census does not exist")
        return record

    def recover(self, *, session_id: str, idempotency_key: str) -> ClaimGroundingCensusRecord:
        """Return a prior durable outcome without exposing the key commitment."""
        if (not isinstance(session_id, str) or PSEUDONYM_PATTERN.fullmatch(session_id) is None
            or not isinstance(idempotency_key, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{16,128}", idempotency_key) is None):
            raise ClaimGroundingCensusInputError("claim census recovery is invalid")
        digest = self._ids.fingerprint("claim-grounding-census-idempotency-v1", (session_id, idempotency_key))
        try:
            record = self._repository.get_by_idempotency(
                session_id=session_id, idempotency_key_digest=digest
            )
        except Exception as error:
            raise ClaimGroundingCensusPersistenceError("claim census recovery is unavailable") from error
        if record is None:
            raise ClaimGroundingCensusNotFoundError("claim census does not exist")
        return record

    def list_page(self, session_id: str, *, limit: int, offset: int, snapshot: ClaimGroundingCensusPageSnapshot | None = None) -> tuple[tuple[ClaimGroundingCensusRecord, ...], ClaimGroundingCensusPageSnapshot]:
        try:
            return self._repository.list_page(session_id, limit=limit, offset=offset, snapshot=snapshot)
        except ClaimGroundingReviewConflictError as error:
            raise ClaimGroundingCensusConflictError("claim census page changed") from error
        except ValueError:
            raise
        except Exception as error:
            raise ClaimGroundingCensusPersistenceError("claim census recovery is unavailable") from error
