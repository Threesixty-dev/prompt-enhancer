"""Native-gated metadata-only durable claim-census boundary."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from pydantic import Field, ValidationError

from ...application.analysis.claim_grounding_census import (
    ClaimGroundingCensusConflictError, ClaimGroundingCensusInputError,
    ClaimGroundingCensusNotFoundError, ClaimGroundingCensusOutcomeUnknownError,
    ClaimGroundingCensusPageSnapshot, ClaimGroundingCensusPersistenceError,
    ClaimGroundingCensusRecord,
)
from ...application.analysis.claim_grounding_evidence import ClaimCensusClassificationEntry
from ...domain import PSEUDONYM_PATTERN, StrictModel
from .claim_grounding_review_routes import _PRIVATE_HEADERS, _bounded_json_preflight, _body, _inline_local_schema_refs


class ClaimGroundingPersistCommand(StrictModel):
    review_receipt_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    review_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    manifest_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    classifications: tuple[ClaimCensusClassificationEntry, ...] = Field(max_length=12_800)


class ClaimGroundingCensusDto(StrictModel):
    census_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    session_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    source_run_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    source_window_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    manifest_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    census_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    candidate_count: int = Field(ge=0, le=12_800)
    metadata_persisted: Literal[True] = True
    candidate_prose_persisted: Literal[False] = False
    proposal_only: Literal[True] = True
    measured: Literal[False] = False
    metric_authority_established: Literal[False] = False

    @classmethod
    def from_record(cls, record: ClaimGroundingCensusRecord) -> "ClaimGroundingCensusDto":
        return cls(census_id=record.census_id, session_id=record.census.session_id,
                   source_run_id=record.census.source_run_id,
                   source_window_fingerprint=record.census.source_window_fingerprint,
                   manifest_fingerprint=record.manifest.manifest_fingerprint,
                   census_fingerprint=record.census.census_fingerprint,
                   candidate_count=record.manifest.candidate_count)


class ClaimGroundingCensusListDto(StrictModel):
    items: tuple[ClaimGroundingCensusDto, ...]
    snapshot_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    high_water_created_at: datetime | None = None
    high_water_census_id: str | None = Field(default=None, pattern=PSEUDONYM_PATTERN.pattern)


class ClaimGroundingCensusService(Protocol):
    def consume_and_issue(self, **values) -> ClaimGroundingCensusRecord: ...  # type: ignore[no-untyped-def]
    def get(self, census_id: str) -> ClaimGroundingCensusRecord: ...
    def recover(self, *, session_id: str, idempotency_key: str) -> ClaimGroundingCensusRecord: ...
    def list_page(self, session_id: str, *, limit: int, offset: int, snapshot: ClaimGroundingCensusPageSnapshot | None = None): ...  # type: ignore[no-untyped-def]


_PERSIST_BODY = {"requestBody": {"required": True, "content": {"application/json": {"schema": _inline_local_schema_refs(ClaimGroundingPersistCommand.model_json_schema())}}}}

def _failure(error: Exception) -> HTTPException:
    if isinstance(error, ClaimGroundingCensusNotFoundError):
        status, code, message = 404, "claim_grounding_census_not_found", "claim-grounding census is unavailable"
    elif isinstance(error, ClaimGroundingCensusOutcomeUnknownError):
        status, code, message = 409, "claim_grounding_census_recovery_required", "claim-grounding census recovery is required"
    elif isinstance(error, ClaimGroundingCensusConflictError):
        status, code, message = 409, "claim_grounding_census_conflict", "claim-grounding census binding changed"
    elif isinstance(error, ClaimGroundingCensusPersistenceError):
        status, code, message = 503, "claim_grounding_census_unavailable", "claim-grounding census is unavailable"
    else:
        status, code, message = 422, "claim_grounding_census_invalid", "claim-grounding census is invalid"
    return HTTPException(status, detail={"code": code, "message": message}, headers=_PRIVATE_HEADERS)


def create_claim_grounding_census_router(require_local_auth, require_user_confirmation, service: ClaimGroundingCensusService) -> APIRouter:  # type: ignore[no-untyped-def]
    router = APIRouter(prefix="/v1", tags=["claim-grounding-review"], dependencies=[Depends(require_local_auth)])
    async def persist(request: Request, response: Response, session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)], idempotency_key: Annotated[str, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9_-]{16,128}$")]) -> ClaimGroundingCensusDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            command = ClaimGroundingPersistCommand.model_validate_json(await _body(request))
            return ClaimGroundingCensusDto.from_record(service.consume_and_issue(
                session_id=session_id, idempotency_key=idempotency_key,
                review_receipt_id=command.review_receipt_id,
                review_fingerprint=command.review_fingerprint,
                manifest_fingerprint=command.manifest_fingerprint,
                classifications=command.classifications,
            ))
        except ValidationError:
            raise _failure(ValueError()) from None
        except (ClaimGroundingCensusConflictError, ClaimGroundingCensusInputError, ClaimGroundingCensusNotFoundError, ClaimGroundingCensusOutcomeUnknownError, ClaimGroundingCensusPersistenceError, ValueError) as error:
            raise _failure(error) from None
    router.post("/sessions/{session_id}/claim-grounding-review/persist", response_model=ClaimGroundingCensusDto, dependencies=[Depends(_bounded_json_preflight), Depends(require_user_confirmation)], openapi_extra=_PERSIST_BODY)(persist)

    @router.get("/sessions/{session_id}/claim-grounding-review/saved-census/{census_id}", response_model=ClaimGroundingCensusDto)
    def get_saved(response: Response, session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)], census_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)]) -> ClaimGroundingCensusDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            item = service.get(census_id)
            if item.census.session_id != session_id: raise ClaimGroundingCensusNotFoundError("not owned")
            return ClaimGroundingCensusDto.from_record(item)
        except (ClaimGroundingCensusConflictError, ClaimGroundingCensusNotFoundError, ClaimGroundingCensusPersistenceError, ValueError) as error: raise _failure(error) from None

    @router.get("/sessions/{session_id}/claim-grounding-review/recovery-status", response_model=ClaimGroundingCensusDto)
    def recovery(response: Response, session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)], idempotency_key: Annotated[str, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9_-]{16,128}$")]) -> ClaimGroundingCensusDto:
        response.headers.update(_PRIVATE_HEADERS)
        try: return ClaimGroundingCensusDto.from_record(service.recover(session_id=session_id, idempotency_key=idempotency_key))
        except (ClaimGroundingCensusNotFoundError, ClaimGroundingCensusInputError, ClaimGroundingCensusPersistenceError, ValueError) as error: raise _failure(error) from None

    @router.get("/sessions/{session_id}/claim-grounding-review/saved-censuses", response_model=ClaimGroundingCensusListDto)
    def list_saved(response: Response, session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)], limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0, snapshot_id: Annotated[str | None, Query(pattern=PSEUDONYM_PATTERN.pattern)] = None, snapshot_total: Annotated[int | None, Query(ge=0)] = None, high_water_created_at: datetime | None = None, high_water_census_id: Annotated[str | None, Query(pattern=PSEUDONYM_PATTERN.pattern)] = None) -> ClaimGroundingCensusListDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            supplied = (snapshot_id, snapshot_total, high_water_created_at, high_water_census_id)
            valid_empty = (snapshot_id is not None and snapshot_total == 0
                           and high_water_created_at is None
                           and high_water_census_id is None)
            valid_nonempty = all(value is not None for value in supplied)
            if any(value is not None for value in supplied) and not (valid_empty or valid_nonempty):
                raise ValueError("incomplete claim census page snapshot")
            snapshot = None if snapshot_id is None else ClaimGroundingCensusPageSnapshot(snapshot_id, snapshot_total, high_water_created_at, high_water_census_id)  # type: ignore[arg-type]
            items, snapshot = service.list_page(session_id, limit=limit, offset=offset, snapshot=snapshot)
            return ClaimGroundingCensusListDto(items=tuple(ClaimGroundingCensusDto.from_record(x) for x in items), snapshot_id=snapshot.snapshot_id, total=snapshot.total, offset=offset, high_water_created_at=snapshot.high_water_created_at, high_water_census_id=snapshot.high_water_census_id)
        except (ClaimGroundingCensusConflictError, ClaimGroundingCensusPersistenceError, ValueError) as error: raise _failure(error) from None
    return router
