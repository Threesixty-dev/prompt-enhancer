"""Local agent workspace (ADR 0016): sessions, turns, events, approvals - all loopback, all in memory."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from ...application.local_agent import (
    AgentEvents,
    AgentSessionView,
    AgentSettings,
    ApprovalDecision,
    LocalAgentError,
    LocalAgentService,
    SendMessage,
)


_STATUS = {
    "workspace_not_a_folder": 422,
    "workspace_not_allowed": 403,
    "workspace_is_a_drive_root": 422,
    "too_many_sessions": 409,
    "session_not_found": 404,
    "turn_in_progress": 409,
    "no_active_model": 409,
    "approval_not_pending": 409,
}
_SESSION_ID = r"^[0-9a-f]{32}$"


def _failure(error: LocalAgentError) -> HTTPException:
    return HTTPException(status_code=_STATUS.get(error.code, 500), detail={"code": error.code})


def create_local_agent_router(require_local_auth: Callable[..., None], service: LocalAgentService) -> APIRouter:
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

    @router.post("/sessions/{session_id}/approvals/{approval_id}", response_model=AgentSessionView)
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
