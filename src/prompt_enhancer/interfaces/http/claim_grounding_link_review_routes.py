from __future__ import annotations
from collections.abc import Callable
from typing import Annotated, Protocol, Literal
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import Field, ValidationError, SecretStr, model_validator
from ...application.analysis.claim_grounding_link_review import ClaimGroundingLinkReview, ClaimGroundingLinkReviewConflictError, ClaimGroundingLinkReviewUnavailableError
from ...application.analysis.claim_grounding_link_source import (
    ClaimGroundingLinkCandidateManifest, ClaimGroundingLinkSourceConflictError,
    ClaimGroundingLinkSourceUnavailableError,
)
from ...application.analysis.claim_grounding_links import ClaimLinkCoverageDecision
from ...domain import PSEUDONYM_PATTERN, SAFE_VERSION_PATTERN, Provider, StrictModel
from .claim_grounding_review_routes import _PRIVATE_HEADERS, _bounded_json_preflight, _body, _inline_local_schema_refs

class ClaimGroundingLinkBeginCommand(StrictModel):
    census_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    candidate_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    selected_check_references: tuple[Annotated[str, Field(pattern=PSEUDONYM_PATTERN.pattern)], ...] = Field(max_length=128)

class ClaimGroundingLinkObservedCheckDto(StrictModel):
    source_reference_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    observed_sequence: int = Field(ge=0)
    outcome: Literal["passed", "check_failed"]
    tool_name: str
    invocation_preview: str
    effect_preview: str | None

class ClaimGroundingLinkReviewDto(StrictModel):
    session_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern); census_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern); candidate_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern); source_run_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern); source_window_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern); census_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern); manifest_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern); observed_set_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    review_receipt_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern); review_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern); review_expires_at: datetime
    claim_clause: str
    observed_checks: tuple[ClaimGroundingLinkObservedCheckDto, ...] = Field(max_length=128)
    proposal_only: Literal[True] = True; measured: Literal[False] = False; metric_authority_established: Literal[False] = False; content_persisted: Literal[False] = False
    @classmethod
    def from_review(cls, review: ClaimGroundingLinkReview):
        return cls(session_id=review.session_id,census_id=review.census_id,candidate_id=review.candidate_id,source_run_id=review.source_run_id,source_window_fingerprint=review.source_window_fingerprint,census_fingerprint=review.census_fingerprint,manifest_fingerprint=review.manifest_fingerprint,observed_set_fingerprint=review.observed_set_fingerprint,review_receipt_id=review.review_receipt_id,review_fingerprint=review.review_fingerprint,review_expires_at=review.review_expires_at,claim_clause=review.claim_clause.get_secret_value(),observed_checks=tuple({"source_reference_id":x.source_reference_id,"observed_sequence":x.observed_sequence,"outcome":x.outcome,"tool_name":x.tool_name.get_secret_value(),"invocation_preview":x.invocation_preview.get_secret_value(),"effect_preview":None if x.effect_preview is None else x.effect_preview.get_secret_value()} for x in review.observed_checks))


class ClaimGroundingLinkMaterialCandidateDto(StrictModel):
    candidate_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    message_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    message_sequence: int = Field(ge=0)
    clause_index: int = Field(ge=0, lt=128)


class ClaimGroundingLinkObservedCheckMetadataDto(StrictModel):
    source_reference_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    observed_sequence: int = Field(ge=0, le=4_000_000_000)
    provider: Provider
    check_kind: Literal["test"]
    outcome: Literal["passed", "check_failed"]
    provider_execution_status: Literal["completed"]
    exit_code: Literal[0, 1]
    source_completion_schema_version: Literal["observed-check-completion-v1"]
    outcome_interpreter_version: Literal["pytest-exit-status-v1"]
    classifier_version: Literal["local-command-rules-v1"]
    normalizer_version: Literal["strict-shell-free-v2"]
    rule_id: Literal["test.pytest", "test.py_test"]

    @model_validator(mode="after")
    def exact_outcome(self) -> "ClaimGroundingLinkObservedCheckMetadataDto":
        if (self.outcome == "passed") != (self.exit_code == 0):
            raise ValueError("observed check outcome is invalid")
        return self


class ClaimGroundingLinkCandidateManifestDto(StrictModel):
    session_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    census_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    source_run_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    source_window_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    census_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    manifest_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    observed_set_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    source_schema_version: str = Field(pattern=SAFE_VERSION_PATTERN.pattern)
    text_adapter_version: str = Field(pattern=SAFE_VERSION_PATTERN.pattern)
    observed_set_schema_version: Literal["claim-grounding-observed-set-v1"]
    observed_set_policy_version: Literal["native-reviewed-claim-link-coverage-v1"]
    material_candidates: tuple[ClaimGroundingLinkMaterialCandidateDto, ...] = Field(max_length=12_800)
    observed_checks: tuple[ClaimGroundingLinkObservedCheckMetadataDto, ...] = Field(max_length=4_000)
    proposal_only: Literal[True] = True
    measured: Literal[False] = False
    metric_authority_established: Literal[False] = False
    content_persisted: Literal[False] = False

    @classmethod
    def from_manifest(cls, manifest: ClaimGroundingLinkCandidateManifest):
        return cls(
            session_id=manifest.session_id, census_id=manifest.census_id,
            source_run_id=manifest.source_run_id,
            source_window_fingerprint=manifest.source_window_fingerprint,
            census_fingerprint=manifest.census_fingerprint,
            manifest_fingerprint=manifest.manifest_fingerprint,
            observed_set_fingerprint=manifest.observed_set_fingerprint,
            source_schema_version=manifest.source_schema_version,
            text_adapter_version=manifest.text_adapter_version,
            observed_set_schema_version=manifest.observed_set_schema_version,
            observed_set_policy_version=manifest.observed_set_policy_version,
            material_candidates=tuple({
                "candidate_id": item.candidate_id, "message_id": item.message_id,
                "message_sequence": item.message_sequence, "clause_index": item.clause_index,
            } for item in manifest.material_candidates),
            observed_checks=tuple({
                "source_reference_id": item.source_reference_id,
                "observed_sequence": item.observed_sequence, "provider": item.provider,
                "check_kind": item.check_kind, "outcome": item.outcome,
                "provider_execution_status": item.provider_execution_status,
                "exit_code": item.exit_code,
                "source_completion_schema_version": item.source_completion_schema_version,
                "outcome_interpreter_version": item.outcome_interpreter_version,
                "classifier_version": item.classifier_version,
                "normalizer_version": item.normalizer_version, "rule_id": item.rule_id,
            } for item in manifest.observed_checks),
        )

class ClaimGroundingLinkReviewService(Protocol):
    def begin_review(self, *, session_id: str, census_id: str, candidate_id: str, selected_check_references: tuple[str, ...]) -> ClaimGroundingLinkReview: ...
    def candidate_manifest(self, *, session_id: str, census_id: str) -> ClaimGroundingLinkCandidateManifest: ...

async def _validated_link_body(request: Request) -> None:
    try:
        ClaimGroundingLinkBeginCommand.model_validate_json(await _body(request))
    except ValidationError:
        raise _failure(ValueError()) from None

def _failure(error: Exception) -> HTTPException:
    if isinstance(error, (ClaimGroundingLinkReviewUnavailableError, ClaimGroundingLinkSourceUnavailableError)): status, code, message = 404, "claim_grounding_link_review_unavailable", "claim-grounding link review is unavailable"
    elif isinstance(error, (ClaimGroundingLinkReviewConflictError, ClaimGroundingLinkSourceConflictError)): status, code, message = 409, "claim_grounding_link_review_conflict", "claim-grounding link review binding changed"
    else: status, code, message = 422, "claim_grounding_link_review_invalid", "claim-grounding link review is invalid"
    return HTTPException(status, detail={"code":code,"message":message}, headers=_PRIVATE_HEADERS)


def _unavailable() -> HTTPException:
    return HTTPException(503, detail={
        "code": "claim_grounding_link_review_unavailable",
        "message": "claim-grounding link review is unavailable",
    }, headers=_PRIVATE_HEADERS)

def create_claim_grounding_link_review_router(require_local_auth: Callable[..., None], require_user_confirmation: Callable[..., None], service: ClaimGroundingLinkReviewService) -> APIRouter:
    router=APIRouter(prefix="/v1", tags=["claim-grounding-review"], dependencies=[Depends(require_local_auth)])
    @router.post("/sessions/{session_id}/claim-grounding-review/links/begin", response_model=ClaimGroundingLinkReviewDto, dependencies=[Depends(_bounded_json_preflight), Depends(_validated_link_body), Depends(require_user_confirmation)], openapi_extra={"requestBody":{"required":True,"content":{"application/json":{"schema":_inline_local_schema_refs(ClaimGroundingLinkBeginCommand.model_json_schema())}}}})
    async def begin(request: Request, response: Response, session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)]):
        response.headers.update(_PRIVATE_HEADERS)
        try:
            command=ClaimGroundingLinkBeginCommand.model_validate_json(await _body(request))
            return ClaimGroundingLinkReviewDto.from_review(service.begin_review(session_id=session_id,census_id=command.census_id,candidate_id=command.candidate_id,selected_check_references=command.selected_check_references))
        except ValidationError: raise _failure(ValueError()) from None
        except (ClaimGroundingLinkReviewUnavailableError, ClaimGroundingLinkReviewConflictError, ClaimGroundingLinkSourceUnavailableError, ClaimGroundingLinkSourceConflictError, ValueError) as error: raise _failure(error) from None
    @router.get("/sessions/{session_id}/claim-grounding-review/links/candidates/{census_id}", response_model=ClaimGroundingLinkCandidateManifestDto)
    async def candidates(response: Response, session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)], census_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)]):
        response.headers.update(_PRIVATE_HEADERS)
        try:
            return ClaimGroundingLinkCandidateManifestDto.from_manifest(
                service.candidate_manifest(session_id=session_id, census_id=census_id)
            )
        except (ClaimGroundingLinkReviewUnavailableError, ClaimGroundingLinkReviewConflictError, ClaimGroundingLinkSourceUnavailableError, ClaimGroundingLinkSourceConflictError, ValueError) as error:
            raise _failure(error) from None
        except Exception:
            raise _unavailable() from None
    return router
