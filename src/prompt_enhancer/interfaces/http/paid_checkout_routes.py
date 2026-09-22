"""Development-only, authenticated checkout and portal session routes."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...application.paid_product.checkout import CheckoutService, CheckoutUnavailable
from ...application.paid_product.contracts import PaidPrincipal
from ...application.paid_product.errors import PaidAuthorizationError

_HEADERS = {"Cache-Control": "no-store, private", "Pragma": "no-cache"}


class PaidPrincipalResolver(Protocol):
    def __call__(self, request: Request) -> PaidPrincipal: ...


def create_paid_checkout_router(require_local_token: Callable[..., None], service: CheckoutService,
                                principal_resolver: PaidPrincipalResolver,
                                *, clock: Callable[[], datetime] | None = None) -> APIRouter:
    router = APIRouter(prefix="/v1/paid-product", tags=["paid-product-development"], dependencies=[Depends(require_local_token)])
    now = clock or (lambda: datetime.now(UTC).replace(microsecond=0))
    def principal(request: Request) -> PaidPrincipal:
        try:
            value = principal_resolver(request)
            if not isinstance(value, PaidPrincipal): raise ValueError
            return value
        except Exception as error: raise HTTPException(status_code=403, detail={"code": "default_deny"}, headers=_HEADERS) from error
    def unavailable() -> HTTPException:
        return HTTPException(status_code=503, detail={"code": "checkout_unavailable"}, headers=_HEADERS)
    @router.post("/checkout-intents/{intent_id}/session")
    def checkout(intent_id: str, request: Request, response: Response) -> dict[str, str]:
        try: url = service.checkout(principal(request), intent_id=intent_id, now=now())
        except PaidAuthorizationError: raise HTTPException(status_code=403, detail={"code": "default_deny"}, headers=_HEADERS) from None
        except CheckoutUnavailable: raise unavailable() from None
        response.headers.update(_HEADERS); return {"url": url}
    @router.post("/portal/{request_id}/session")
    def portal(request_id: str, request: Request, response: Response) -> dict[str, str]:
        try: url = service.portal(principal(request), request_id=request_id, now=now())
        except PaidAuthorizationError: raise HTTPException(status_code=403, detail={"code": "default_deny"}, headers=_HEADERS) from None
        except CheckoutUnavailable: raise unavailable() from None
        response.headers.update(_HEADERS); return {"url": url}
    return router

__all__ = ("PaidPrincipalResolver", "create_paid_checkout_router")
