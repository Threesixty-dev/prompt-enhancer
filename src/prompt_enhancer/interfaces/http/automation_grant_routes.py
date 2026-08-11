"""Authenticated local automation-grant commands and status queries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Path,
    Query,
    Response,
    status,
)
from pydantic import Field

from ...application.automation import (
    AutomationConsentError,
    AutomationGrantNotFoundError,
    AutomationGrantRecord,
    AutomationGrantScope,
    AutomationGrantService,
    AutomationPollResult,
    AutomationResourcePolicy,
    AutomationSelectionError,
)
from ...database import DatabaseError
from ...domain import PSEUDONYM_PATTERN, Provider, StrictModel


class AutomationGrantCreateRequest(StrictModel):
    provider: Provider
    project_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    metric_keys: tuple[str, ...] = Field(min_length=1, max_length=100)
    newest_session_limit: int = Field(default=20, ge=1, le=100)
    check_interval_seconds: int = Field(default=15 * 60, ge=60, le=86_400)
    resource_policy: AutomationResourcePolicy = Field(
        default_factory=AutomationResourcePolicy
    )

    def scope(self) -> AutomationGrantScope:
        return AutomationGrantScope(
            provider=self.provider,
            project_id=self.project_id,
            metric_keys=tuple(sorted(self.metric_keys)),
            newest_session_limit=self.newest_session_limit,
            check_interval_seconds=self.check_interval_seconds,
            resource_policy=self.resource_policy,
        )


def create_automation_grant_router(
    require_local_auth: Callable[..., None],
    service: AutomationGrantService,
) -> APIRouter:
    def prevent_private_caching(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"

    router = APIRouter(
        prefix="/v1",
        tags=["automation-grants"],
        dependencies=[
            Depends(require_local_auth),
            Depends(prevent_private_caching),
        ],
    )

    @router.post(
        "/automation-grants",
        response_model=AutomationGrantRecord,
        status_code=status.HTTP_201_CREATED,
        responses={
            403: {"description": "Standing local consent required"},
            409: {"description": "Project unavailable or grant conflict"},
        },
    )
    def create_grant(
        payload: Annotated[AutomationGrantCreateRequest, Body()],
    ) -> AutomationGrantRecord:
        try:
            return service.create(payload.scope())
        except AutomationConsentError:
            raise HTTPException(
                status_code=403,
                detail={"code": "automation_consent_required"},
            ) from None
        except AutomationSelectionError as error:
            raise HTTPException(
                status_code=409,
                detail={"code": error.code},
            ) from None
        except DatabaseError:
            raise HTTPException(
                status_code=409,
                detail={"code": "automation_grant_conflict"},
            ) from None

    @router.get(
        "/automation-grants",
        response_model=tuple[AutomationGrantRecord, ...],
    )
    def list_grants(
        provider: Annotated[Provider, Query()],
        active_only: Annotated[bool, Query()] = False,
    ) -> tuple[AutomationGrantRecord, ...]:
        return service.list_for_provider(provider, active_only=active_only)

    @router.get(
        "/automation-grants/{grant_id}",
        response_model=AutomationGrantRecord,
        responses={404: {"description": "Grant not found"}},
    )
    def get_grant(
        grant_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
    ) -> AutomationGrantRecord:
        try:
            return service.get(grant_id)
        except AutomationGrantNotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "automation_grant_not_found"},
            ) from None

    @router.post(
        "/automation-grants/{grant_id}/renewal",
        response_model=AutomationGrantRecord,
        responses={403: {"description": "Consent required"}, 404: {"description": "Not found"}},
    )
    def renew_grant(
        grant_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
    ) -> AutomationGrantRecord:
        try:
            return service.renew(grant_id)
        except AutomationGrantNotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "automation_grant_not_found"},
            ) from None
        except AutomationConsentError:
            raise HTTPException(
                status_code=403,
                detail={"code": "automation_consent_required"},
            ) from None
        except AutomationSelectionError as error:
            raise HTTPException(
                status_code=409,
                detail={"code": error.code},
            ) from None
        except DatabaseError:
            raise HTTPException(
                status_code=409,
                detail={"code": "automation_grant_conflict"},
            ) from None

    @router.post(
        "/automation-grants/{grant_id}/revocation",
        response_model=AutomationGrantRecord,
        responses={404: {"description": "Grant not found"}},
    )
    def revoke_grant(
        grant_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
    ) -> AutomationGrantRecord:
        try:
            return service.revoke(grant_id)
        except AutomationGrantNotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "automation_grant_not_found"},
            ) from None

    @router.post(
        "/automation-grants/poll",
        response_model=AutomationPollResult,
    )
    def poll_grants() -> AutomationPollResult:
        return service.poll_due()

    return router


__all__ = ["AutomationGrantCreateRequest", "create_automation_grant_router"]
