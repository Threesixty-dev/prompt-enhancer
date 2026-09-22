"""Native-gated, ephemeral claim-grounding census review boundary."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import Field, ValidationError

from ...application.analysis.claim_grounding_evidence import (
    ClaimCensusClassificationEntry, ClaimCensusSourceManifest, ReviewedClaimCensus,
)
from ...application.analysis.claim_grounding_review import (
    ClaimGroundingCensusReviewProposal, ClaimGroundingReviewConflictError,
    ClaimGroundingReviewUnavailableError,
)
from ...domain import PSEUDONYM_PATTERN, StrictModel

_PRIVATE_HEADERS = {"Cache-Control": "no-store, private", "Pragma": "no-cache"}
_MAX_BODY_BYTES = 4 * 1_048_576


def _inline_local_schema_refs(schema: dict) -> dict:
    definitions = dict(schema.pop("$defs", {}))

    def resolve(value):  # type: ignore[no-untyped-def]
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if not isinstance(value, dict):
            return value
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            target = definitions.get(reference.removeprefix("#/$defs/"))
            if isinstance(target, dict):
                return resolve(dict(target))
        return {key: resolve(item) for key, item in value.items()}

    return resolve(schema)


class ClaimGroundingReviewCommand(StrictModel):
    expected_source_run_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    expected_source_window_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)


class ClaimGroundingConsumeCommand(StrictModel):
    review_receipt_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    review_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    manifest_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    classifications: tuple[ClaimCensusClassificationEntry, ...] = Field(max_length=12_800)


_BEGIN_REQUEST_BODY = {
    "requestBody": {"required": True, "content": {"application/json": {
        "schema": _inline_local_schema_refs(ClaimGroundingReviewCommand.model_json_schema())
    }}},
}
_CONSUME_REQUEST_BODY = {
    "requestBody": {"required": True, "content": {"application/json": {
        "schema": _inline_local_schema_refs(ClaimGroundingConsumeCommand.model_json_schema())
    }}},
}


class ClaimGroundingCandidateDto(StrictModel):
    candidate_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    message_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    message_sequence: int = Field(ge=0)
    clause_index: int = Field(ge=0)
    text: str = Field(min_length=1)


class ClaimGroundingBeginDto(StrictModel):
    session_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    source_run_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    source_window_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    manifest: ClaimCensusSourceManifest
    candidates: tuple[ClaimGroundingCandidateDto, ...] = Field(max_length=12_800)
    review_receipt_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    review_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    review_expires_at: datetime
    local_only: Literal[True]
    content_persisted: Literal[False]

    @classmethod
    def from_review(cls, review: ClaimGroundingCensusReviewProposal) -> "ClaimGroundingBeginDto":
        return cls(
            session_id=review.session_id, source_run_id=review.source_run_id,
            source_window_fingerprint=review.source_window_fingerprint,
            manifest=review.manifest,
            candidates=tuple(ClaimGroundingCandidateDto(
                candidate_id=item.candidate_id, message_id=item.message_id,
                message_sequence=item.message_sequence, clause_index=item.clause_index,
                text=item.text.get_secret_value(),
            ) for item in review.candidates),
            review_receipt_id=review.review_receipt_id,
            review_fingerprint=review.review_fingerprint,
            review_expires_at=review.review_expires_at,
            local_only=True, content_persisted=False,
        )


class ClaimGroundingProposalDto(StrictModel):
    reviewed_census: ReviewedClaimCensus
    proposal_only: Literal[True] = True
    measured: Literal[False] = False
    metric_authority_established: Literal[False] = False
    content_persisted: Literal[False] = False


class ClaimGroundingReviewCommandService(Protocol):
    def begin_review(self, *, session_id: str, expected_source_run_id: str, expected_source_window_fingerprint: str) -> ClaimGroundingCensusReviewProposal: ...
    def consume_review(self, *, session_id: str, review_receipt_id: str, review_fingerprint: str, manifest_fingerprint: str, classifications: tuple[ClaimCensusClassificationEntry, ...]) -> ReviewedClaimCensus: ...


async def _body(request: Request) -> bytes:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, detail={"code": "claim_grounding_review_media_type_required", "message": "claim-grounding review requires JSON"}, headers=_PRIVATE_HEADERS)
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > _MAX_BODY_BYTES:
            raise HTTPException(413, detail={"code": "claim_grounding_review_too_large", "message": "claim-grounding review exceeds the local limit"}, headers=_PRIVATE_HEADERS)
        payload.extend(chunk)
    # Native presence proof reads ``request.body()`` after this preflight.
    # Cache only the bounded body so that proof and handler bind the same bytes.
    request._body = bytes(payload)  # type: ignore[attr-defined]
    return request._body  # type: ignore[attr-defined]


async def _bounded_json_preflight(request: Request) -> None:
    await _body(request)


def _failure(error: Exception) -> HTTPException:
    if isinstance(error, ClaimGroundingReviewUnavailableError):
        status, code, message = 404, "claim_grounding_review_unavailable", "claim-grounding review is unavailable"
    elif isinstance(error, ClaimGroundingReviewConflictError):
        status, code, message = 409, "claim_grounding_review_conflict", "claim-grounding review binding changed"
    else:
        status, code, message = 422, "claim_grounding_review_invalid", "claim-grounding review is invalid"
    return HTTPException(status, detail={"code": code, "message": message}, headers=_PRIVATE_HEADERS)


def create_claim_grounding_review_router(require_local_auth: Callable[..., None], require_user_confirmation: Callable[..., None], service: ClaimGroundingReviewCommandService) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["claim-grounding-review"], dependencies=[Depends(require_local_auth)])

    @router.post("/sessions/{session_id}/claim-grounding-review/begin", response_model=ClaimGroundingBeginDto, dependencies=[Depends(_bounded_json_preflight), Depends(require_user_confirmation)], openapi_extra=_BEGIN_REQUEST_BODY)
    async def begin(request: Request, response: Response, session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)]) -> ClaimGroundingBeginDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            command = ClaimGroundingReviewCommand.model_validate_json(await _body(request))
            return ClaimGroundingBeginDto.from_review(service.begin_review(
                session_id=session_id, expected_source_run_id=command.expected_source_run_id,
                expected_source_window_fingerprint=command.expected_source_window_fingerprint,
            ))
        except ValidationError:
            raise _failure(ValueError()) from None
        except (ClaimGroundingReviewUnavailableError, ClaimGroundingReviewConflictError, ValueError) as error:
            raise _failure(error) from None

    @router.post("/sessions/{session_id}/claim-grounding-review/consume", response_model=ClaimGroundingProposalDto, dependencies=[Depends(_bounded_json_preflight), Depends(require_user_confirmation)], openapi_extra=_CONSUME_REQUEST_BODY)
    async def consume(request: Request, response: Response, session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)]) -> ClaimGroundingProposalDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            command = ClaimGroundingConsumeCommand.model_validate_json(await _body(request))
            return ClaimGroundingProposalDto(reviewed_census=service.consume_review(
                session_id=session_id,
                review_receipt_id=command.review_receipt_id,
                review_fingerprint=command.review_fingerprint,
                manifest_fingerprint=command.manifest_fingerprint,
                classifications=command.classifications,
            ))
        except ValidationError:
            raise _failure(ValueError()) from None
        except (ClaimGroundingReviewUnavailableError, ClaimGroundingReviewConflictError, ValueError) as error:
            raise _failure(error) from None

    return router
