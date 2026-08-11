"""Explicit, content-free HTTP command for one local quality-analysis run."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pydantic import Field

from ...application.analysis.session_text_service import (
    SESSION_TEXT_ANALYSIS_CONFIRMATION,
    SessionTextAnalysisConfirmationError,
    SessionTextAnalysisConflictError,
    SessionTextAnalysisCompatibilityError,
    SessionTextAnalysisConsentError,
    SessionTextAnalysisExecutionError,
    SessionTextAnalysisInputError,
    SessionTextAnalysisOutcome,
    SessionTextAnalysisPersistenceError,
    SessionTextAnalysisSelectionError,
    SessionTextAnalysisSourceError,
)
from ...application.analysis.text_analysis_presets import TextAnalysisPresetId
from ...application.analysis.text_source import TextSourceFailureReason
from ...application.persistence import AnalysisRunStatus
from ...domain import PSEUDONYM_PATTERN, SAFE_VERSION_PATTERN, Provider, StrictModel


class SessionTextAnalysisCommand(Protocol):
    def run_preset(
        self,
        *,
        provider: Provider,
        session_id: str,
        preset_id: TextAnalysisPresetId,
        confirmation: str,
        idempotency_key: str,
    ) -> SessionTextAnalysisOutcome: ...


class SessionTextAnalysisRequest(StrictModel):
    """A named server-owned scope. The API never accepts profile or transcript text."""

    confirmation: Literal["analyze_selected_redacted_text"]
    preset_id: TextAnalysisPresetId


class SessionTextAnalysisCommandResponse(StrictModel):
    run_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    status: AnalysisRunStatus
    result_count: int = Field(ge=0, le=100)
    applied: bool
    analysis_profile_key: str
    analysis_profile_version: int = Field(ge=1)

    @classmethod
    def from_outcome(
        cls, outcome: SessionTextAnalysisOutcome
    ) -> SessionTextAnalysisCommandResponse:
        return cls(
            run_id=outcome.run_id,
            status=outcome.status,
            result_count=outcome.result_count,
            applied=outcome.applied,
            analysis_profile_key=outcome.analysis_profile_key,
            analysis_profile_version=outcome.analysis_profile_version,
        )


class SessionTextAnalysisFailureCode(StrEnum):
    """Closed HTTP error vocabulary; values never contain provider data."""

    CONSENT_REQUIRED = SessionTextAnalysisConsentError.code
    SESSION_NOT_INDEXED = SessionTextAnalysisSelectionError.code
    IDEMPOTENCY_CONFLICT = SessionTextAnalysisConflictError.code
    INVALID_REQUEST = SessionTextAnalysisInputError.code
    CONFIRMATION_REQUIRED = SessionTextAnalysisConfirmationError.code
    SCHEMA_UNSUPPORTED = TextSourceFailureReason.SCHEMA_UNSUPPORTED.value
    SELECTION_SNAPSHOT_MISS = TextSourceFailureReason.SELECTION_SNAPSHOT_MISS.value
    RESOURCE_LIMIT = TextSourceFailureReason.RESOURCE_LIMIT.value
    TIMEOUT = TextSourceFailureReason.TIMEOUT.value
    PROVIDER_UNAVAILABLE = TextSourceFailureReason.PROVIDER_UNAVAILABLE.value
    NO_ANALYZABLE_TEXT = TextSourceFailureReason.NO_ANALYZABLE_TEXT.value
    PROTOCOL_REJECTED = TextSourceFailureReason.PROTOCOL_REJECTED.value
    COMPATIBILITY_BLOCKED = SessionTextAnalysisCompatibilityError.code
    PERSISTENCE_FAILED = SessionTextAnalysisPersistenceError.code
    EXECUTION_FAILED = SessionTextAnalysisExecutionError.code


class SessionTextAnalysisFailureDetail(StrictModel):
    code: SessionTextAnalysisFailureCode
    message: str = Field(min_length=1, max_length=128)


class SessionTextAnalysisFailureResponse(StrictModel):
    detail: SessionTextAnalysisFailureDetail


class SanitizedRequestValidationFailureResponse(StrictModel):
    detail: Literal["request validation failed"]


_SOURCE_FAILURE_HTTP: dict[TextSourceFailureReason, tuple[int, str]] = {
    TextSourceFailureReason.SCHEMA_UNSUPPORTED: (
        503,
        "local source schema is unsupported",
    ),
    TextSourceFailureReason.SELECTION_SNAPSHOT_MISS: (
        409,
        "selected session is absent from the current provider snapshot",
    ),
    TextSourceFailureReason.RESOURCE_LIMIT: (
        413,
        "selected session exceeds the local analysis bounds",
    ),
    TextSourceFailureReason.TIMEOUT: (504, "local source read timed out"),
    TextSourceFailureReason.PROVIDER_UNAVAILABLE: (
        503,
        "local source provider is unavailable",
    ),
    TextSourceFailureReason.NO_ANALYZABLE_TEXT: (
        422,
        "selected session has no analyzable text",
    ),
    TextSourceFailureReason.PROTOCOL_REJECTED: (
        503,
        "local provider rejected the bounded read protocol",
    ),
}


def _failure(
    status_code: int,
    code: SessionTextAnalysisFailureCode,
    message: str,
) -> HTTPException:
    detail = SessionTextAnalysisFailureDetail(code=code, message=message)
    return HTTPException(status_code=status_code, detail=detail.model_dump(mode="json"))


def create_session_analysis_command_router(
    require_local_auth: Callable[..., None],
    service: SessionTextAnalysisCommand,
) -> APIRouter:
    router = APIRouter(
        prefix="/v1",
        tags=["session-quality-analysis"],
        dependencies=[Depends(require_local_auth)],
    )

    @router.post(
        "/sessions/{session_id}/quality-analysis-runs",
        response_model=SessionTextAnalysisCommandResponse,
        responses={
            **{
                status: {"model": SessionTextAnalysisFailureResponse}
                for status in (403, 404, 409, 413, 503, 504)
            },
            422: {
                "model": (
                    SessionTextAnalysisFailureResponse
                    | SanitizedRequestValidationFailureResponse
                )
            },
        },
    )
    def start_session_analysis(
        payload: SessionTextAnalysisRequest,
        session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                pattern=SAFE_VERSION_PATTERN.pattern,
            ),
        ],
    ) -> SessionTextAnalysisCommandResponse:
        try:
            outcome = service.run_preset(
                provider=Provider.CODEX,
                session_id=session_id,
                preset_id=payload.preset_id,
                confirmation=payload.confirmation,
                idempotency_key=idempotency_key,
            )
        except SessionTextAnalysisConsentError:
            raise _failure(
                403,
                SessionTextAnalysisFailureCode.CONSENT_REQUIRED,
                "redacted-content consent required",
            ) from None
        except SessionTextAnalysisSelectionError:
            raise _failure(
                404,
                SessionTextAnalysisFailureCode.SESSION_NOT_INDEXED,
                "selected session is not indexed",
            ) from None
        except SessionTextAnalysisCompatibilityError:
            raise _failure(
                409,
                SessionTextAnalysisFailureCode.COMPATIBILITY_BLOCKED,
                "provider compatibility is not verified",
            ) from None
        except SessionTextAnalysisConflictError:
            raise _failure(
                409,
                SessionTextAnalysisFailureCode.IDEMPOTENCY_CONFLICT,
                "analysis idempotency conflict",
            ) from None
        except (
            SessionTextAnalysisInputError,
            SessionTextAnalysisConfirmationError,
        ) as error:
            raise _failure(
                422,
                SessionTextAnalysisFailureCode(error.code),
                "quality analysis request is invalid",
            ) from None
        except SessionTextAnalysisSourceError as error:
            status, message = _SOURCE_FAILURE_HTTP[error.reason]
            raise _failure(
                status,
                SessionTextAnalysisFailureCode(error.reason.value),
                message,
            ) from None
        except SessionTextAnalysisPersistenceError:
            raise _failure(
                503,
                SessionTextAnalysisFailureCode.PERSISTENCE_FAILED,
                "local analysis persistence is unavailable",
            ) from None
        except SessionTextAnalysisExecutionError:
            raise _failure(
                503,
                SessionTextAnalysisFailureCode.EXECUTION_FAILED,
                "local metric execution is unavailable",
            ) from None
        return SessionTextAnalysisCommandResponse.from_outcome(outcome)

    return router
