"""Private, read-only readiness surface for the optional paid-product boundary."""

from __future__ import annotations

from typing import Callable

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response

from ...application.paid_product.contracts import ProductReadiness
from ...application.paid_product.errors import BillingWebhookError
from ...infrastructure.paid_product.stripe_testmode import (
    MAX_STRIPE_WEBHOOK_BYTES,
    StripeTestmodeWebhookService,
    StripeWebhookRejected,
)


_PRIVATE_HEADERS = {"Cache-Control": "no-store, private", "Pragma": "no-cache"}


def create_paid_product_readiness_router(
    require_local_token: Callable[..., None],
    readiness: ProductReadiness,
) -> APIRouter:
    """Expose capability gaps without mounting identity, billing, or job APIs."""

    router = APIRouter(
        prefix="/v1/paid-product",
        tags=["paid-product-readiness"],
        dependencies=[Depends(require_local_token)],
    )

    @router.get(
        "/readiness",
        response_model=ProductReadiness,
    )
    def product_readiness(response: Response) -> ProductReadiness:
        for name, value in _PRIVATE_HEADERS.items():
            response.headers[name] = value
        return readiness

    return router


def create_stripe_testmode_webhook_router(
    service: StripeTestmodeWebhookService,
    *,
    clock: Callable[[], datetime] | None = None,
) -> APIRouter:
    """Public-by-necessity ingress; the Stripe signature is its authentication.

    This route is only mounted when the caller explicitly injects a test-mode
    service.  It has no local-token dependency because Stripe cannot possess a
    local operator token.  The service reads and authenticates exact raw bytes
    before it attempts JSON parsing.
    """

    router = APIRouter(prefix="/v1/paid-product/stripe", tags=["stripe-testmode"])

    @router.post("/webhook", status_code=200, include_in_schema=False)
    async def stripe_webhook(request: Request) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_STRIPE_WEBHOOK_BYTES:
                    return Response(status_code=400, headers=_PRIVATE_HEADERS)
            except ValueError:
                return Response(status_code=400, headers=_PRIVATE_HEADERS)
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_STRIPE_WEBHOOK_BYTES:
                return Response(status_code=400, headers=_PRIVATE_HEADERS)
            chunks.append(chunk)
        raw_body = b"".join(chunks)
        # Some global Starlette middleware legitimately buffers the receive
        # channel before routing.  In that case stream() is empty but the
        # cached body remains available; it was already length-gated above.
        if not raw_body:
            raw_body = await request.body()
            if len(raw_body) > MAX_STRIPE_WEBHOOK_BYTES:
                return Response(status_code=400, headers=_PRIVATE_HEADERS)
        try:
            service.process(
                raw_body,
                request.headers.get("stripe-signature"),
                now=(clock or (lambda: datetime.now(UTC).replace(microsecond=0)))(),
            )
        except (StripeWebhookRejected, BillingWebhookError):
            # Intentionally do not expose parsing, binding, or receipt detail.
            return Response(status_code=400, headers=_PRIVATE_HEADERS)
        return Response(status_code=200, headers=_PRIVATE_HEADERS)

    return router


__all__ = [
    "create_paid_product_readiness_router",
    "create_stripe_testmode_webhook_router",
]
