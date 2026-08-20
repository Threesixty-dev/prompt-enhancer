"""Local agent workspace (ADR 0016): sessions, turns, events, approvals - all loopback, all in memory."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from fastapi.responses import StreamingResponse

from ...application.local_agent import (
    AgentEvents,
    AgentSessionView,
    AgentSettings,
    ApprovalDecision,
    LocalAgentError,
    LocalAgentService,
    SendMessage,
)
from ...application.local_agent_editor import (
    WorkspaceApplyCommand,
    WorkspaceApplyResult,
    WorkspaceEditPreview,
    WorkspaceFile,
    WorkspacePreviewCommand,
    WorkspaceTree,
)


_STATUS = {
    "workspace_not_a_folder": 422,
    "workspace_not_allowed": 403,
    "workspace_link_or_reparse_refused": 403,
    "workspace_is_a_drive_root": 422,
    "workspace_path_not_found": 404,
    "workspace_directory_unavailable": 422,
    "workspace_not_a_directory": 422,
    "workspace_file_unavailable": 422,
    "workspace_file_changed": 409,
    "workspace_binary_refused": 415,
    "workspace_line_endings_unsupported": 422,
    "workspace_revision_changed": 409,
    "workspace_line_ending_changed": 409,
    "workspace_existing_file_required": 422,
    "workspace_no_change": 409,
    "workspace_change_not_reviewable": 422,
    "workspace_file_too_large": 413,
    "workspace_text_invalid": 422,
    "workspace_parent_unavailable": 422,
    "change_too_large_to_review": 413,
    "workspace_preview_not_found": 409,
    "workspace_preview_expired": 409,
    "workspace_preview_mismatch": 409,
    "workspace_apply_failed": 409,
    "workspace_verification_failed": 409,
    "path_outside_workspace": 403,
    "path_invalid": 422,
    "too_many_sessions": 409,
    "session_not_found": 404,
    "turn_in_progress": 409,
    "no_active_model": 409,
    "approval_not_pending": 409,
}
_SESSION_ID = r"^[0-9a-f]{32}$"


def _failure(error: LocalAgentError) -> HTTPException:
    return HTTPException(status_code=_STATUS.get(error.code, 500), detail={"code": error.code})


def _stream_event_pages(
    service: LocalAgentService,
    session_id: str,
    after: int,
    limit: int,
) -> Iterator[bytes]:
    """Relay bounded event pages until the current turn is fully drained."""

    cursor = after
    while True:
        try:
            page = service.wait_events(session_id, cursor, limit)
        except LocalAgentError:
            return
        if page.events:
            cursor = page.events[-1].seq
            yield f"data: {page.model_dump_json()}\n\n".encode("utf-8")
        else:
            yield b": keepalive\n\n"
        if not page.running and page.pending_approval_id is None and cursor >= page.last_seq:
            return


def create_local_agent_router(
    require_local_auth: Callable[..., None],
    require_browser_confirmation: Callable[..., None],
    service: LocalAgentService,
) -> APIRouter:
    router = APIRouter(prefix="/v1/agent", tags=["local-agent"], dependencies=[Depends(require_local_auth)])

    @router.get("/sessions", response_model=tuple[AgentSessionView, ...])
    def list_sessions() -> tuple[AgentSessionView, ...]:
        return service.list()

    @router.post("/sessions", response_model=AgentSessionView, status_code=201)
    def create_session(payload: AgentSettings) -> AgentSessionView:
        try:
            return service.create(payload)
        except LocalAgentError as error:
            raise _failure(error) from None

    @router.get("/sessions/{session_id}", response_model=AgentSessionView)
    def get_session(session_id: Annotated[str, Path(pattern=_SESSION_ID)]) -> AgentSessionView:
        try:
            return service.get(session_id)
        except LocalAgentError as error:
            raise _failure(error) from None

    @router.delete("/sessions/{session_id}", status_code=204)
    def delete_session(session_id: Annotated[str, Path(pattern=_SESSION_ID)]) -> Response:
        try:
            service.delete(session_id)
        except LocalAgentError as error:
            raise _failure(error) from None
        return Response(status_code=204)

    @router.post("/sessions/{session_id}/messages", response_model=AgentSessionView, status_code=202)
    def send_message(session_id: Annotated[str, Path(pattern=_SESSION_ID)], payload: SendMessage) -> AgentSessionView:
        try:
            return service.send(session_id, payload)
        except LocalAgentError as error:
            raise _failure(error) from None

    @router.get("/sessions/{session_id}/events", response_model=AgentEvents)
    def events(
        session_id: Annotated[str, Path(pattern=_SESSION_ID)],
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 500,
    ) -> AgentEvents:
        try:
            return service.events(session_id, after, limit)
        except LocalAgentError as error:
            raise _failure(error) from None

    @router.get(
        "/sessions/{session_id}/workspace/tree",
        response_model=WorkspaceTree,
    )
    def workspace_tree(
        session_id: Annotated[str, Path(pattern=_SESSION_ID)],
        path: Annotated[str, Query(min_length=1, max_length=1024)] = ".",
    ) -> WorkspaceTree:
        try:
            return service.workspace_tree(session_id, path)
        except LocalAgentError as error:
            raise _failure(error) from None

    @router.get(
        "/sessions/{session_id}/workspace/file",
        response_model=WorkspaceFile,
    )
    def workspace_file(
        session_id: Annotated[str, Path(pattern=_SESSION_ID)],
        path: Annotated[str, Query(min_length=1, max_length=1024)],
    ) -> WorkspaceFile:
        try:
            return service.workspace_file(session_id, path)
        except LocalAgentError as error:
            raise _failure(error) from None

    @router.post(
        "/sessions/{session_id}/workspace/previews",
        response_model=WorkspaceEditPreview,
        status_code=201,
    )
    def preview_workspace_edit(
        session_id: Annotated[str, Path(pattern=_SESSION_ID)],
        payload: WorkspacePreviewCommand,
    ) -> WorkspaceEditPreview:
        try:
            return service.preview_workspace_edit(session_id, payload)
        except LocalAgentError as error:
            raise _failure(error) from None

    @router.post(
        "/sessions/{session_id}/workspace/previews/{preview_id}/apply",
        response_model=WorkspaceApplyResult,
        dependencies=[Depends(require_browser_confirmation)],
    )
    def apply_workspace_edit(
        session_id: Annotated[str, Path(pattern=_SESSION_ID)],
        preview_id: Annotated[str, Path(pattern=_SESSION_ID)],
        payload: WorkspaceApplyCommand,
    ) -> WorkspaceApplyResult:
        try:
            return service.apply_workspace_edit(session_id, preview_id, payload)
        except LocalAgentError as error:
            raise _failure(error) from None

    @router.get(
        "/sessions/{session_id}/events/stream",
        response_class=StreamingResponse,
        responses={200: {"content": {"text/event-stream": {}}}},
    )
    def stream_events(
        session_id: Annotated[str, Path(pattern=_SESSION_ID)],
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 500,
    ) -> StreamingResponse:
        try:
            service.get(session_id)
        except LocalAgentError as error:
            raise _failure(error) from None
        return StreamingResponse(
            _stream_event_pages(service, session_id, after, limit),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store, private",
                "Pragma": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post(
        "/sessions/{session_id}/approvals/{approval_id}",
        response_model=AgentSessionView,
        dependencies=[Depends(require_browser_confirmation)],
    )
    def decide(
        session_id: Annotated[str, Path(pattern=_SESSION_ID)],
        approval_id: Annotated[str, Path(pattern=_SESSION_ID)],
        payload: ApprovalDecision,
    ) -> AgentSessionView:
        try:
            return service.approve(session_id, approval_id, payload)
        except LocalAgentError as error:
            raise _failure(error) from None

    @router.post("/sessions/{session_id}/stop", response_model=AgentSessionView)
    def stop(session_id: Annotated[str, Path(pattern=_SESSION_ID)]) -> AgentSessionView:
        try:
            return service.stop(session_id)
        except LocalAgentError as error:
            raise _failure(error) from None

    return router


__all__ = ("create_local_agent_router",)
