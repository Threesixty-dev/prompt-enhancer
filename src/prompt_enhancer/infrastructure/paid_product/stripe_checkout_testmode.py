"""Stripe test-mode API mapper over an injected, non-network HTTP port."""
from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit
from pydantic import SecretStr
from typing import Protocol

STRIPE_API_VERSION = "2025-03-31.basil"
MAX_STRIPE_RESPONSE_BYTES = 16 * 1024

class StripeHttp(Protocol):
    def post(self, *, url: str, headers: dict[str, str], body: bytes, timeout_seconds: float, follow_redirects: bool) -> tuple[int, bytes]: ...

@dataclass(frozen=True, slots=True)
class StripeTestmodeConfig:
    api_key: SecretStr
    timeout_seconds: float = 5.0
    livemode: bool = False

class StripeCheckoutTestmodeTransport:
    def __init__(self, config: StripeTestmodeConfig, http: StripeHttp) -> None:
        if config.livemode or not config.api_key.get_secret_value().startswith("sk_test_") or not 0 < config.timeout_seconds <= 10: raise ValueError("stripe test-mode configuration invalid")
        self._config, self._http = config, http
    def _post(self, path, fields, key, host, expected_object, customer, checkout):
        status, payload = self._http.post(url="https://api.stripe.com" + path, headers={"Authorization":"Bearer "+self._config.api_key.get_secret_value(),"Stripe-Version":STRIPE_API_VERSION,"Idempotency-Key":key,"Content-Type":"application/x-www-form-urlencoded"}, body=urlencode(fields).encode(), timeout_seconds=self._config.timeout_seconds, follow_redirects=False)
        if status != 200 or len(payload) > MAX_STRIPE_RESPONSE_BYTES: raise OSError("stripe request failed")
        import json
        def pairs(items):
            result={}
            for name,value in items:
                if name in result: raise ValueError()
                result[name]=value
            return result
        try:
            data=json.loads(payload.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda _x: (_ for _ in ()).throw(ValueError()))
            if not isinstance(data,dict) or data.get("object") != expected_object or data.get("customer") != customer: raise ValueError()
            if checkout and (data.get("livemode") is not False or data.get("mode") != "subscription"): raise ValueError()
            url=data["url"]
        except (UnicodeDecodeError, ValueError, KeyError, TypeError, RecursionError): raise OSError("stripe response invalid") from None
        if not isinstance(url,str) or any(ord(c)<32 for c in url): raise OSError("stripe response invalid")
        try:
            parsed = urlsplit(url)
            unsafe_authority = (
                parsed.scheme != "https"
                or parsed.hostname != host
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port is not None
            )
        except ValueError:
            raise OSError("stripe response invalid") from None
        if unsafe_authority:
            raise OSError("stripe response invalid")
        return url
    def create_checkout(self, **kwargs: str) -> str:
        return self._post("/v1/checkout/sessions", {"mode":"subscription","customer":kwargs["customer_id"],"line_items[0][price]":kwargs["price_id"],"line_items[0][quantity]":"1","success_url":kwargs["success_url"],"cancel_url":kwargs["cancel_url"]}, kwargs["idempotency_key"], "checkout.stripe.com", "checkout.session", kwargs["customer_id"], True)
    def create_portal(self, **kwargs: str) -> str:
        return self._post("/v1/billing_portal/sessions", {"customer":kwargs["customer_id"],"return_url":kwargs["return_url"]}, kwargs["idempotency_key"], "billing.stripe.com", "billing_portal.session", kwargs["customer_id"], False)
