"""Unmounted test-mode Checkout and Portal application boundary."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from urllib.parse import urlsplit
from typing import Protocol
from dataclasses import dataclass
from .contracts import PaidPrincipal, PaidReasonCode, PaidScope
from .errors import PaidAuthorizationError

class CheckoutUnavailable(ValueError): pass

class CheckoutIntent(Protocol):
    organization_id: str
    customer_id: str
    price_id: str
    idempotency_key: str
    return_destination: str

@dataclass(frozen=True, slots=True)
class DurableCheckoutIntent:
    organization_id: str
    intent_id: str
    customer_id: str
    price_id: str
    return_destination: str
    idempotency_key: str

class CheckoutResolver(Protocol):
    def checkout_intent(self, organization_id: str, intent_id: str) -> CheckoutIntent | None: ...
    def portal_customer(self, organization_id: str) -> str | None: ...

class CheckoutTransport(Protocol):
    def create_checkout(self, *, customer_id: str, price_id: str, success_url: str, cancel_url: str, idempotency_key: str) -> str: ...
    def create_portal(self, *, customer_id: str, return_url: str, idempotency_key: str) -> str: ...

class CheckoutService:
    def __init__(self, *, authorizer, resolver: CheckoutResolver, transport: CheckoutTransport, return_url: str) -> None:
        parsed = urlsplit(return_url)
        if len(return_url) > 200 or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port is not None or any(ord(c) < 32 for c in return_url):
            raise ValueError("checkout return destination must be exact HTTPS")
        self._authorizer, self._resolver, self._transport, self._return_url = authorizer, resolver, transport, return_url
    def checkout(self, principal: PaidPrincipal, *, intent_id: str, now: datetime) -> str:
        if not self._authorizer.allows(principal, PaidScope.BILLING_ADMINISTER, now=now): raise PaidAuthorizationError(PaidReasonCode.DEFAULT_DENY)
        intent = self._resolver.checkout_intent(principal.organization_id, intent_id)
        if intent is None or intent.organization_id != principal.organization_id: raise CheckoutUnavailable("checkout_intent_unavailable")
        if intent.return_destination != self._return_url: raise CheckoutUnavailable("checkout_intent_destination_unavailable")
        try: return self._transport.create_checkout(customer_id=intent.customer_id, price_id=intent.price_id, success_url=intent.return_destination, cancel_url=intent.return_destination, idempotency_key=intent.idempotency_key)
        except (TimeoutError, OSError): raise CheckoutUnavailable("checkout_provider_unavailable") from None
    def portal(self, principal: PaidPrincipal, *, request_id: str, now: datetime) -> str:
        if not self._authorizer.allows(principal, PaidScope.BILLING_ADMINISTER, now=now): raise PaidAuthorizationError(PaidReasonCode.DEFAULT_DENY)
        if (
            not isinstance(request_id, str)
            or not request_id
            or len(request_id) > 255
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in request_id)
        ):
            raise CheckoutUnavailable("portal_request_id_invalid")
        customer = self._resolver.portal_customer(principal.organization_id)
        if customer is None: raise CheckoutUnavailable("portal_customer_unavailable")
        key_material = json.dumps(
            {
                "organization_id": principal.organization_id,
                "purpose": "customer_portal",
                "request_id": request_id,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        provider_idempotency_key = "portal_" + hashlib.sha256(key_material).hexdigest()
        try: return self._transport.create_portal(customer_id=customer, return_url=self._return_url, idempotency_key=provider_idempotency_key)
        except (TimeoutError, OSError): raise CheckoutUnavailable("portal_provider_unavailable") from None
