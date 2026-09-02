"""Authenticated, browser-gesture-only application update advisory routes."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Response

from ...application.updates import ApplicationUpdateStatus, ApplicationUpdateSurface


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"


def create_application_update_router(
    require_local_auth: Callable[..., None],
    require_browser_interaction: Callable[..., None],
    service: ApplicationUpdateSurface,
) -> APIRouter:
    """Read status locally; permit advisory egress only after a UI gesture."""

    router = APIRouter(prefix="/v1/application-updates", tags=["application-updates"])

    @router.get(
        "/status",
        response_model=ApplicationUpdateStatus,
        dependencies=[Depends(require_local_auth)],
    )
    def status(response: Response) -> ApplicationUpdateStatus:
        _private(response)
        return service.status()

    @router.post(
        "/check",
        response_model=ApplicationUpdateStatus,
        dependencies=[Depends(require_browser_interaction)],
    )
    def check(response: Response) -> ApplicationUpdateStatus:
        _private(response)
        return service.check()

    return router


__all__ = ("create_application_update_router",)
