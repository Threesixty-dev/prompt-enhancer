"""Authenticated private API for the continuous local ensemble watch."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Callable, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import Field, field_validator

from ...application.analysis.model_ensemble_watch import (
    MODEL_ENSEMBLE_WATCH_CONFIRMATION,
    ModelEnsembleWatchConflictError,
    ModelEnsembleWatchInputError,
    ModelEnsembleWatchNotFoundError,
    ModelEnsembleWatchRecord,
    ModelEnsembleWatchService,
    ModelEnsembleTrajectoryPage,
)
from ...application.analysis.session_model_ensemble import (
    ModelEnsembleCompatibilityError,
    ModelEnsembleConsentError,
    ModelEnsembleInputError,
    ModelEnsemblePersistenceError,
    ModelEnsembleSelectionError,
    SessionModelEnsembleRunRecord,
)
from ...domain import PSEUDONYM_PATTERN, Provider, StrictModel
from .model_ensemble_routes import ModelEnsembleRunDto


_PRIVATE_HEADERS = {"Cache-Control": "no-store, private", "Pragma": "no-cache"}


class ModelEnsembleWatchRequest(StrictModel):
    project_id: str
    max_messages: int = Field(default=100, ge=1, le=100)
    confirmation: Literal[MODEL_ENSEMBLE_WATCH_CONFIRMATION]

    @field_validator("project_id")
    @classmethod
    def safe_project(cls, value: str) -> str:
        if PSEUDONYM_PATTERN.fullmatch(value) is None:
            raise ValueError("project selector is invalid")
        return value


class ModelEnsembleWatchDto(StrictModel):
    watch_id: str
    provider: Literal[Provider.CODEX]
    project_id: str
    session_id: str
    max_messages: int = Field(ge=1, le=100)
    state: Literal["queued", "running", "idle", "failed", "disabled"]
    generation: int
    progress_completed: int
    progress_total: Literal[10]
    has_result: bool
    last_error_code: str | None
    next_check_at: datetime
    updated_at: datetime
    serial_model_execution: Literal[True] = True
    process_isolated_model_release: Literal[True] = True
    cuda_resource_retry_on_cpu: Literal[True] = True
    content_persisted: Literal[False] = False
    calibrated_as_truth: Literal[False] = False

    @classmethod
    def from_record(cls, record: ModelEnsembleWatchRecord) -> "ModelEnsembleWatchDto":
        return cls(
            watch_id=record.watch_id,
            provider=Provider.CODEX,
            project_id=record.project_id,
            session_id=record.session_id,
            max_messages=record.max_messages,
            state=record.state.value,
            generation=record.generation,
            progress_completed=record.progress_completed,
            progress_total=10,
            has_result=record.latest_run_id is not None,
            last_error_code=record.last_error_code,
            next_check_at=record.next_check_at,
            updated_at=record.updated_at,
        )


class ModelEnsembleWatchSnapshotDto(StrictModel):
    watch: ModelEnsembleWatchDto
    latest_run: ModelEnsembleRunDto | None


class ModelEnsembleRunReader(Protocol):
    def get(self, run_id: str) -> SessionModelEnsembleRunRecord | None: ...


def _watch_failure(error: Exception) -> HTTPException:
    if isinstance(error, ModelEnsembleConsentError):
        return HTTPException(403, detail={"code": error.code, "message": "redacted-content consent required"})
    if isinstance(error, ModelEnsembleSelectionError):
        return HTTPException(404, detail={"code": error.code, "message": "selected session is not indexed"})
    if isinstance(error, ModelEnsembleCompatibilityError):
        return HTTPException(409, detail={"code": error.code, "message": "provider compatibility is not verified"})
    if isinstance(error, ModelEnsembleWatchConflictError):
        return HTTPException(409, detail={"code": error.code, "message": "model ensemble watch conflicts with local state"})
    if isinstance(error, ModelEnsembleWatchNotFoundError):
        return HTTPException(404, detail={"code": error.code, "message": "model ensemble watch was not found"})
    if isinstance(error, (ModelEnsembleWatchInputError, ModelEnsembleInputError)):
        return HTTPException(422, detail={"code": error.code, "message": "model ensemble watch request is invalid"})
    if isinstance(error, ModelEnsemblePersistenceError):
        return HTTPException(503, detail={"code": error.code, "message": "model ensemble result is unavailable"})
    raise TypeError("unsupported model ensemble watch error")


def create_model_ensemble_watch_router(
    require_local_auth: Callable[..., None],
    service: ModelEnsembleWatchService,
    ensemble: ModelEnsembleRunReader,
) -> APIRouter:
    router = APIRouter(
        prefix="/v1",
        tags=["local-model-ensemble-watch"],
        dependencies=[Depends(require_local_auth)],
    )

    def snapshot(record: ModelEnsembleWatchRecord) -> ModelEnsembleWatchSnapshotDto:
        latest = None
        if record.latest_run_id is not None:
            try:
                latest = ensemble.get(record.latest_run_id)
            except (ModelEnsembleInputError, ModelEnsemblePersistenceError) as error:
                raise _watch_failure(error) from None
            if latest is None or latest.session_id != record.session_id:
                raise _watch_failure(
                    ModelEnsemblePersistenceError(
                        "watch result binding is unavailable"
                    )
                )
        return ModelEnsembleWatchSnapshotDto(
            watch=ModelEnsembleWatchDto.from_record(record),
            latest_run=None if latest is None else ModelEnsembleRunDto.from_record(latest),
        )

    @router.put(
        "/sessions/{session_id}/model-ensemble-watch",
        response_model=ModelEnsembleWatchSnapshotDto,
    )
    def enable_watch(
        payload: ModelEnsembleWatchRequest,
        response: Response,
        session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
    ) -> ModelEnsembleWatchSnapshotDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            record = service.enable(
                provider=Provider.CODEX,
                project_id=payload.project_id,
                session_id=session_id,
                max_messages=payload.max_messages,
                confirmation=payload.confirmation,
            )
        except (
            ModelEnsembleCompatibilityError,
            ModelEnsembleConsentError,
            ModelEnsembleInputError,
            ModelEnsembleSelectionError,
            ModelEnsembleWatchConflictError,
            ModelEnsembleWatchInputError,
        ) as error:
            raise _watch_failure(error) from None
        return snapshot(record)

    @router.get(
        "/model-ensemble-watch/active",
        response_model=ModelEnsembleWatchSnapshotDto,
    )
    def active_watch(response: Response) -> ModelEnsembleWatchSnapshotDto:
        response.headers.update(_PRIVATE_HEADERS)
        record = service.get_active()
        if record is None:
            raise HTTPException(404, detail="active model ensemble watch not found")
        return snapshot(record)

    @router.post(
        "/model-ensemble-watches/{watch_id}/refresh",
        response_model=ModelEnsembleWatchSnapshotDto,
    )
    def refresh_watch(
        response: Response,
        watch_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
    ) -> ModelEnsembleWatchSnapshotDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            record = service.refresh(watch_id)
        except (
            ModelEnsembleWatchInputError,
            ModelEnsembleWatchNotFoundError,
        ) as error:
            raise _watch_failure(error) from None
        return snapshot(record)

    @router.delete(
        "/model-ensemble-watches/{watch_id}",
        response_model=ModelEnsembleWatchSnapshotDto,
    )
    def disable_watch(
        response: Response,
        watch_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
    ) -> ModelEnsembleWatchSnapshotDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            record = service.disable(watch_id)
        except (ModelEnsembleWatchInputError, ModelEnsembleWatchNotFoundError) as error:
            raise _watch_failure(error) from None
        return snapshot(record)

    @router.get(
        "/model-ensemble-watches/{watch_id}/trajectory",
        response_model=ModelEnsembleTrajectoryPage,
    )
    def watch_trajectory(
        response: Response,
        watch_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
        limit: Annotated[int, Query(ge=1, le=60)] = 12,
        before_generation: Annotated[
            int | None,
            Query(ge=1, le=1_000_000_000),
        ] = None,
    ) -> ModelEnsembleTrajectoryPage:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            return service.trajectory(
                watch_id,
                before_generation=before_generation,
                limit=limit,
            )
        except (
            ModelEnsembleWatchInputError,
            ModelEnsembleWatchNotFoundError,
        ) as error:
            raise _watch_failure(error) from None

    return router


__all__ = [
    "ModelEnsembleWatchDto",
    "ModelEnsembleWatchRequest",
    "ModelEnsembleWatchSnapshotDto",
    "create_model_ensemble_watch_router",
]
