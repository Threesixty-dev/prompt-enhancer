"""Synthetic, offline contract tests for test-mode Checkout and Portal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

import pytest
from pydantic import SecretStr

from prompt_enhancer.application.paid_product.checkout import (
    CheckoutService,
    CheckoutUnavailable,
)
from prompt_enhancer.application.paid_product.contracts import PaidPrincipal, PaidScope
from prompt_enhancer.infrastructure.paid_product.stripe_checkout_testmode import (
    MAX_STRIPE_RESPONSE_BYTES,
    STRIPE_API_VERSION,
    StripeCheckoutTestmodeTransport,
    StripeTestmodeConfig,
)
from prompt_enhancer.infrastructure.paid_product.sqlite import PaidProductSqliteStore


NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
API_KEY = "sk_test_example_fixture_key"
CUSTOMER_ID = "cus_test_fixture"
PRICE_ID = "price_test_fixture"
CHECKOUT_URL = "https://checkout.stripe.com/session/synthetic"
PORTAL_URL = "https://billing.stripe.com/session/synthetic"
SUCCESS_URL = "https://app.example.test/billing/return?result=success"
CANCEL_URL = "https://app.example.test/billing/return?result=cancel"
PORTAL_RETURN_URL = "https://app.example.test/billing"


def pseudonym(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


class Intent:
    organization_id = pseudonym("synthetic-organization")
    customer_id = CUSTOMER_ID
    price_id = PRICE_ID
    idempotency_key = "checkout-intent-fixture-01"
    return_destination = SUCCESS_URL


class Resolver:
    def checkout_intent(self, organization_id: str, intent_id: str) -> Intent | None:
        if organization_id == Intent.organization_id and intent_id == "intent-fixture":
            return Intent()
        return None

    def portal_customer(self, organization_id: str) -> str | None:
        return CUSTOMER_ID if organization_id == Intent.organization_id else None


class Authorizer:
    def allows(self, principal: PaidPrincipal, scope: PaidScope, *, now: datetime) -> bool:
        del now
        return principal.active and scope in principal.scopes


class RecordingHttp:
    def __init__(self, response: bytes | None = None) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        follow_redirects: bool,
    ) -> tuple[int, bytes]:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "body": body,
                "timeout_seconds": timeout_seconds,
                "follow_redirects": follow_redirects,
            }
        )
        if self.response is None:
            raise AssertionError("test must configure a response body")
        return 200, self.response


def checkout_response() -> dict[str, object]:
    return {
        "object": "checkout.session",
        "customer": CUSTOMER_ID,
        "livemode": False,
        "mode": "subscription",
        "url": CHECKOUT_URL,
    }


def portal_response() -> dict[str, object]:
    return {
        "object": "billing_portal.session",
        "customer": CUSTOMER_ID,
        "url": PORTAL_URL,
    }


def encode_response(operation: str, *, mutate: str | None = None) -> bytes:
    """Build each adversarial body by changing one property of a valid reply."""

    if operation == "checkout":
        value = checkout_response()
        expected_url = CHECKOUT_URL
    else:
        value = portal_response()
        expected_url = PORTAL_URL

    if mutate == "duplicate_json":
        valid = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return valid[:-1] + b',"url":"https://other.example.test/session"}'
    if mutate == "nan":
        valid = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return valid[:-1] + b',"optional_numeric":NaN}'
    if mutate == "invalid_utf8":
        return json.dumps(value, separators=(",", ":")).encode("utf-8").replace(
            expected_url.encode("ascii"), expected_url.encode("ascii") + b"\xff", 1
        )
    if mutate == "depth_1100":
        valid = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return (
            valid[:-1]
            + b',"untrusted_extension":'
            + b"[" * 1100
            + b"0"
            + b"]" * 1100
            + b"}"
        )
    if mutate == "oversize":
        value["padding"] = "x" * (MAX_STRIPE_RESPONSE_BYTES + 1)
        return json.dumps(value, separators=(",", ":")).encode("utf-8")
    if mutate == "missing_url":
        del value["url"]
    elif mutate == "url_type":
        value["url"] = 7
    elif mutate == "wrong_host":
        value["url"] = "https://evil.example.test/session/synthetic"
    elif mutate == "userinfo":
        host = "checkout.stripe.com" if operation == "checkout" else "billing.stripe.com"
        value["url"] = f"https://synthetic-user@{host}/session/synthetic"
    elif mutate == "port":
        host = "checkout.stripe.com" if operation == "checkout" else "billing.stripe.com"
        value["url"] = f"https://{host}:444/session/synthetic"
    elif mutate == "invalid_port":
        host = "checkout.stripe.com" if operation == "checkout" else "billing.stripe.com"
        value["url"] = f"https://{host}:notaport/session/synthetic"
    elif mutate == "control_character":
        host = "checkout.stripe.com" if operation == "checkout" else "billing.stripe.com"
        value["url"] = f"https://{host}/session/\x01synthetic"
    elif mutate == "wrong_object":
        value["object"] = "unrelated.object"
    elif mutate == "wrong_customer":
        value["customer"] = "cus_other_fixture"
    elif mutate == "wrong_mode":
        value["mode"] = "payment"
    elif mutate == "live_mode":
        value["livemode"] = True
    elif mutate is not None:
        raise AssertionError(f"unknown test mutation: {mutate}")

    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def transport_for(
    response: bytes | None = None,
) -> tuple[StripeCheckoutTestmodeTransport, RecordingHttp]:
    http = RecordingHttp(response)
    transport = StripeCheckoutTestmodeTransport(
        make_testmode_config(), http
    )
    return transport, http


def make_testmode_config(**overrides: object) -> StripeTestmodeConfig:
    values: dict[str, object] = {"api" + "_key": SecretStr(API_KEY)}
    values.update(overrides)
    return StripeTestmodeConfig(**values)


def expected_http_call(operation: str) -> dict[str, object]:
    if operation == "checkout":
        path = "/v1/checkout/sessions"
        form = {
            "mode": "subscription",
            "customer": CUSTOMER_ID,
            "line_items[0][price]": PRICE_ID,
            "line_items[0][quantity]": "1",
            "success_url": SUCCESS_URL,
            "cancel_url": CANCEL_URL,
        }
        idempotency_key = "checkout-idempotency-fixture-01"
    else:
        path = "/v1/billing_portal/sessions"
        form = {"customer": CUSTOMER_ID, "return_url": PORTAL_RETURN_URL}
        idempotency_key = "portal-idempotency-fixture-01"
    return {
        "url": "https://api.stripe.com" + path,
        "headers": {
            "Authorization": f"Bearer {API_KEY}",
            "Stripe-Version": STRIPE_API_VERSION,
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        "body": urlencode(form).encode("ascii"),
        "timeout_seconds": 5.0,
        "follow_redirects": False,
    }


def invoke_transport(
    transport: StripeCheckoutTestmodeTransport, operation: str
) -> str:
    if operation == "checkout":
        return transport.create_checkout(
            customer_id=CUSTOMER_ID,
            price_id=PRICE_ID,
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
            idempotency_key="checkout-idempotency-fixture-01",
        )
    return transport.create_portal(
        customer_id=CUSTOMER_ID,
        return_url=PORTAL_RETURN_URL,
        idempotency_key="portal-idempotency-fixture-01",
    )


def principal(
    scopes: tuple[PaidScope, ...] = (
        PaidScope.BILLING_ADMINISTER,
        PaidScope.BILLING_READ,
    ),
    *,
    organization_id: str = Intent.organization_id,
) -> PaidPrincipal:
    return PaidPrincipal(
        organization_id=organization_id,
        user_id=pseudonym("synthetic-user"),
        account_id=pseudonym("synthetic-account"),
        client_id=pseudonym("synthetic-client"),
        device_id=pseudonym("synthetic-device"),
        scopes=tuple(sorted(scopes, key=str)),
        verified_at=NOW - timedelta(seconds=1),
        expires_at=NOW + timedelta(hours=1),
        active=True,
    )


def test_checkout_is_server_resolved_and_repeated_request_is_idempotent() -> None:
    http = RecordingHttp(encode_response("checkout"))
    transport = StripeCheckoutTestmodeTransport(
        make_testmode_config(), http
    )
    service = CheckoutService(
        authorizer=Authorizer(),
        resolver=Resolver(),
        transport=transport,
        return_url=SUCCESS_URL,
    )

    first = service.checkout(principal(), intent_id="intent-fixture", now=NOW)
    second = service.checkout(principal(), intent_id="intent-fixture", now=NOW)
    assert first == second == CHECKOUT_URL
    assert len(http.calls) == 2
    with pytest.raises(CheckoutUnavailable, match="checkout_intent_unavailable"):
        service.checkout(principal(), intent_id="unknown-fixture", now=NOW)
    assert len(http.calls) == 2


def test_checkout_intent_return_destination_mismatch_fails_before_transport() -> None:
    class MismatchedIntent(Intent):
        return_destination = "https://app.example.test/other-return"

    class MismatchedResolver(Resolver):
        def checkout_intent(
            self, organization_id: str, intent_id: str
        ) -> MismatchedIntent | None:
            if organization_id == Intent.organization_id and intent_id == "intent-fixture":
                return MismatchedIntent()
            return None

    http = RecordingHttp(encode_response("checkout"))
    service = CheckoutService(
        authorizer=Authorizer(),
        resolver=MismatchedResolver(),
        transport=StripeCheckoutTestmodeTransport(make_testmode_config(), http),
        return_url=SUCCESS_URL,
    )

    with pytest.raises(
        CheckoutUnavailable, match="checkout_intent_destination_unavailable"
    ):
        service.checkout(principal(), intent_id="intent-fixture", now=NOW)
    assert http.calls == []


def test_checkout_transport_runs_outside_durable_intent_transaction(
    tmp_path: Path,
) -> None:
    store = PaidProductSqliteStore.under(tmp_path)
    store.initialize()
    with store:
        intent = store.create_checkout_intent(
            organization_id=Intent.organization_id,
            intent_id="intent-fixture",
            customer_id=CUSTOMER_ID,
            price_id=PRICE_ID,
            return_destination=SUCCESS_URL,
        )

    class TransactionProbeHttp(RecordingHttp):
        def post(self, **kwargs: object) -> tuple[int, bytes]:
            # A nested store transaction would raise if service transport were
            # invoked while checkout_intent() still owned its SQLite transaction.
            with store:
                assert store.checkout_intent(
                    intent.organization_id, intent.intent_id
                ) == intent
            return super().post(**kwargs)

    http = TransactionProbeHttp(encode_response("checkout"))
    service = CheckoutService(
        authorizer=Authorizer(),
        resolver=store,
        transport=StripeCheckoutTestmodeTransport(make_testmode_config(), http),
        return_url=SUCCESS_URL,
    )

    assert service.checkout(
        principal(organization_id=intent.organization_id),
        intent_id=intent.intent_id,
        now=NOW,
    ) == CHECKOUT_URL
    assert len(http.calls) == 1


def test_portal_uses_resolved_customer() -> None:
    http = RecordingHttp(encode_response("portal"))
    transport = StripeCheckoutTestmodeTransport(
        make_testmode_config(), http
    )
    service = CheckoutService(
        authorizer=Authorizer(),
        resolver=Resolver(),
        transport=transport,
        return_url=PORTAL_RETURN_URL,
    )

    assert service.portal(
        principal(), request_id="portal-fixture", now=NOW
    ) == PORTAL_URL
    assert len(http.calls) == 1


def test_portal_idempotency_key_is_stable_and_tenant_scoped() -> None:
    first_org = pseudonym("synthetic-organization-one")
    second_org = pseudonym("synthetic-organization-two")

    class MultiTenantResolver:
        customers = {
            first_org: "cus_tenant_one_fixture",
            second_org: "cus_tenant_two_fixture",
        }

        def portal_customer(self, organization_id: str) -> str | None:
            return self.customers.get(organization_id)

        def checkout_intent(self, _organization_id: str, _intent_id: str) -> None:
            return None

    class PortalCapture:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def create_portal(
            self, *, customer_id: str, return_url: str, idempotency_key: str
        ) -> str:
            self.calls.append(
                {
                    "customer_id": customer_id,
                    "return_url": return_url,
                    "idempotency_key": idempotency_key,
                }
            )
            return PORTAL_URL

        def create_checkout(self, **_kwargs: str) -> str:
            raise AssertionError("portal flow must not create checkout")

    transport = PortalCapture()
    service = CheckoutService(
        authorizer=Authorizer(),
        resolver=MultiTenantResolver(),
        transport=transport,
        return_url=PORTAL_RETURN_URL,
    )

    assert service.portal(
        principal(organization_id=first_org), request_id="shared-request-fixture", now=NOW
    ) == PORTAL_URL
    assert service.portal(
        principal(organization_id=second_org), request_id="shared-request-fixture", now=NOW
    ) == PORTAL_URL
    assert service.portal(
        principal(organization_id=first_org), request_id="shared-request-fixture", now=NOW
    ) == PORTAL_URL

    assert [call["customer_id"] for call in transport.calls] == [
        "cus_tenant_one_fixture",
        "cus_tenant_two_fixture",
        "cus_tenant_one_fixture",
    ]
    first_key, second_key, repeated_first_key = [
        call["idempotency_key"] for call in transport.calls
    ]
    assert first_key != second_key
    assert repeated_first_key == first_key
    canonical = json.dumps(
        {
            "organization_id": first_org,
            "purpose": "customer_portal",
            "request_id": "shared-request-fixture",
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert first_key == "portal_" + hashlib.sha256(canonical).hexdigest()


@pytest.mark.parametrize("request_id", ["", "x" * 256, "line\nbreak", "delete\x7f"])
def test_portal_rejects_empty_oversize_and_control_request_ids(
    request_id: str,
) -> None:
    http = RecordingHttp(encode_response("portal"))
    transport = StripeCheckoutTestmodeTransport(
        make_testmode_config(), http
    )
    service = CheckoutService(
        authorizer=Authorizer(),
        resolver=Resolver(),
        transport=transport,
        return_url=PORTAL_RETURN_URL,
    )

    with pytest.raises(CheckoutUnavailable, match="portal_request_id_invalid"):
        service.portal(principal(), request_id=request_id, now=NOW)
    assert http.calls == []


@pytest.mark.parametrize("operation", ["checkout", "portal"])
def test_transport_posts_exact_origin_path_form_auth_and_policy(
    operation: str,
) -> None:
    transport, http = transport_for(encode_response(operation))

    result = invoke_transport(transport, operation)

    expected_result = CHECKOUT_URL if operation == "checkout" else PORTAL_URL
    assert result == expected_result
    assert http.calls == [expected_http_call(operation)]


@pytest.mark.parametrize(
    "operation,mutation",
    [
        (operation, mutation)
        for operation in ("checkout", "portal")
        for mutation in (
            "duplicate_json",
            "nan",
            "invalid_utf8",
            "url_type",
            "wrong_host",
            "userinfo",
            "port",
            "invalid_port",
            "control_character",
            "missing_url",
            "wrong_object",
            "wrong_customer",
            "depth_1100",
            "oversize",
        )
    ]
    + [("checkout", "wrong_mode"), ("checkout", "live_mode")],
)
def test_one_field_malformed_or_unsafe_response_is_rejected(
    operation: str, mutation: str
) -> None:
    transport, http = transport_for(encode_response(operation, mutate=mutation))

    expected_error = "stripe request failed" if mutation == "oversize" else "stripe response invalid"
    with pytest.raises(OSError, match=expected_error):
        invoke_transport(transport, operation)

    assert http.calls == [expected_http_call(operation)]


@pytest.mark.parametrize(
    "config_kwargs",
    [
        {"api_key": "sk_live_synthetic_fixture"},
        {"api_key": API_KEY, "livemode": True},
        {"api_key": API_KEY, "timeout_seconds": 0},
        {"api_key": API_KEY, "timeout_seconds": 11},
    ],
)
def test_transport_configuration_rejects_live_or_invalid_values(
    config_kwargs: dict[str, object],
) -> None:
    normalized = dict(config_kwargs)
    normalized["api_key"] = SecretStr(str(normalized["api_key"]))
    with pytest.raises(ValueError, match="stripe test-mode configuration invalid"):
        StripeCheckoutTestmodeTransport(StripeTestmodeConfig(**normalized), RecordingHttp())


def test_checkout_service_rejects_non_https_or_credentialed_return_destination() -> None:
    for return_url in (
        "http://app.example.test/billing",
        "https://user@app.example.test/billing",
        "https://app.example.test:444/billing",
        "https://app.example.test/billing\x01",
    ):
        with pytest.raises(
            ValueError, match="checkout return destination must be exact HTTPS"
        ):
            CheckoutService(
                authorizer=Authorizer(),
                resolver=Resolver(),
                transport=object(),
                return_url=return_url,
            )
