"""Local model runtimes: list, add, activate/deactivate, downloads, chat proxy."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import StreamingResponse

from ...application.local_models import (
    ALIAS_PATTERN,
    ActivateLocalModel,
    AddLocalModel,
    DownloadRequest,
    DownloadStatus,
    LocalModelError,
    LocalModelRecord,
    LocalModelService,
    LocalModelStatus,
    LocalModelsOverview,
    RemoteRepoFiles,
)

import json


_STATUS_FOR_CODE = {
    "model_not_found": 404,
    "alias_exists": 409,
    "model_file_invalid": 422,
    "model_file_missing": 409,
    "runtime_unavailable": 409,
    "runtime_spawn_failed": 502,
    "runtime_not_healthy": 502,
    "runtime_unreachable": 502,
    "model_not_active": 409,
    "chat_body_invalid": 422,
    "chat_body_too_large": 413,
    "huggingface_hub_unavailable": 409,
    "remote_repo_unavailable": 502,
}


def _failure(error: LocalModelError) -> HTTPException:
    return HTTPException(status_code=_STATUS_FOR_CODE.get(error.code, 500), detail={"code": error.code})


def create_local_model_router(require_local_auth: Callable[..., None], service: LocalModelService) -> APIRouter:
    router = APIRouter(prefix="/v1/local-models", tags=["local-models"], dependencies=[Depends(require_local_auth)])

    @router.get("", response_model=LocalModelsOverview)
    def overview() -> LocalModelsOverview:
        return service.overview()

    @router.post("", response_model=LocalModelRecord, status_code=201)
    def add(payload: AddLocalModel) -> LocalModelRecord:
        try:
            return service.add(payload)
        except LocalModelError as error:
            raise _failure(error) from None

    @router.get("/remote-files", response_model=RemoteRepoFiles)
    def remote_files(repo_id: Annotated[str, Query(min_length=3, max_length=200)]) -> RemoteRepoFiles:
        try:
            return service.remote_files(repo_id)
        except LocalModelError as error:
            raise _failure(error) from None

    @router.post("/downloads", response_model=DownloadStatus, status_code=202)
    def start_download(payload: DownloadRequest) -> DownloadStatus:
        try:
            return service.start_download(payload)
        except LocalModelError as error:
            raise _failure(error) from None

    @router.get("/{alias}", response_model=LocalModelStatus)
    def status(alias: Annotated[str, Path(pattern=ALIAS_PATTERN.pattern)]) -> LocalModelStatus:
        try:
            return service.status(alias)
        except LocalModelError as error:
            raise _failure(error) from None

    @router.delete("/{alias}", status_code=204)
    def remove(
        alias: Annotated[str, Path(pattern=ALIAS_PATTERN.pattern)],
        delete_weights: Annotated[bool, Query()] = False,
    ) -> Response:
        try:
            service.remove(alias, delete_weights=delete_weights)
        except LocalModelError as error:
            raise _failure(error) from None
        return Response(status_code=204)

    @router.post("/{alias}/activate", response_model=LocalModelStatus)
    def activate(
        alias: Annotated[str, Path(pattern=ALIAS_PATTERN.pattern)],
        payload: ActivateLocalModel | None = None,
    ) -> LocalModelStatus:
        try:
            return service.activate(alias, payload)
        except LocalModelError as error:
            raise _failure(error) from None

    @router.post("/{alias}/deactivate", response_model=LocalModelStatus)
    def deactivate(alias: Annotated[str, Path(pattern=ALIAS_PATTERN.pattern)]) -> LocalModelStatus:
        try:
            service.deactivate(alias)
            return service.status(alias)
        except LocalModelError as error:
            raise _failure(error) from None

    def _model_list(aliases: tuple[str, ...]) -> dict[str, object]:
        return {
            "object": "list",
            "data": [{"id": alias, "object": "model", "created": 0, "owned_by": "local"} for alias in aliases],
        }

    def _relay(alias: str, body: bytes) -> Response:
        try:
            upstream = service.open_chat(alias, body)
        except LocalModelError as error:
            raise _failure(error) from None
        if upstream.lines is not None:
            return StreamingResponse(
                upstream.lines,
                status_code=upstream.status_code,
                media_type="text/event-stream",
                headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
            )
        return Response(
            content=upstream.body or b"",
            status_code=upstream.status_code,
            media_type=upstream.content_type,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/openai/v1/models")
    def openai_models() -> dict[str, object]:
        """OpenAI-style model list for clients that use one base URL for every running model."""

        return _model_list(service.running_aliases())

    @router.post("/openai/v1/chat/completions")
    async def openai_chat_completions(request: Request) -> Response:
        """OpenAI-style chat completion routed by the ``model`` field to a running alias."""

        body = await request.body()
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(status_code=422, detail={"code": "chat_body_invalid"}) from None
        model = payload.get("model") if isinstance(payload, dict) else None
        if not isinstance(model, str) or ALIAS_PATTERN.fullmatch(model) is None:
            raise HTTPException(status_code=422, detail={"code": "chat_body_invalid"})
        return _relay(model, body)

    @router.get("/{alias}/v1/models")
    def model_list(alias: Annotated[str, Path(pattern=ALIAS_PATTERN.pattern)]) -> dict[str, object]:
        """OpenAI-style single-model list, so ``…/{alias}/v1`` works as a base URL."""

        try:
            status = service.status(alias)
        except LocalModelError as error:
            raise _failure(error) from None
        return _model_list((alias,) if status.runtime.state == "running" else ())

    @router.post("/{alias}/v1/chat/completions")
    async def chat_completions_openai_base(
        request: Request,
        alias: Annotated[str, Path(pattern=ALIAS_PATTERN.pattern)],
    ) -> Response:
        """Same proxy under an OpenAI-style base URL (``…/{alias}/v1``)."""

        return _relay(alias, await request.body())

    @router.post("/{alias}/chat/completions")
    async def chat_completions(
        request: Request,
        alias: Annotated[str, Path(pattern=ALIAS_PATTERN.pattern)],
    ) -> Response:
        """OpenAI-compatible chat completion proxied to the model's loopback runtime; ``stream: true`` relays SSE."""

        return _relay(alias, await request.body())

    return router


__all__ = ("create_local_model_router",)
