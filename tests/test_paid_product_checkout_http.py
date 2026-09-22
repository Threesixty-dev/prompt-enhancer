"""Synthetic HTTP acceptance for the opt-in local Checkout/Portal routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from prompt_enhancer.api import API_TOKEN_HEADER, CSRF_HEADER, create_app
from prompt_enhancer.application.paid_product.contracts import PaidPrincipal, PaidScope
from prompt_enhancer.config import AppSettings
from prompt_enhancer.database import Database
from prompt_enhancer.infrastructure.paid_product.development import (
    DevelopmentPrincipalAuthorizer,
)
from prompt_enhancer.infrastructure.paid_product.sqlite import PaidProductSqliteStore


API_TOKEN = "example_checkout_local_api_token_123456789"
ORG_A = hashlib.sha256(b"example_checkout_org_a").hexdigest()
ORG_B = hashlib.sha256(b"example_checkout_org_b").hexdigest()
RETURN_URL = "https://example.invalid/billing/return"
CHECKOUT_URL = "https://checkout.stripe.com/example-session"
PORTAL_URL = "https://billing.stripe.com/example-session"
INTENT_A = "example-intent-a"


def _pseudonym(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _principal(organization_id: str, label: str) -> PaidPrincipal:
    now = datetime.now(UTC).replace(microsecond=0)
    return PaidPrincipal(
        organization_id=organization_id,
        user_id=_pseudonym(f"user:{label}"),
        account_id=_pseudonym(f"account:{label}"),
        client_id=_pseudonym(f"client:{label}"),
        device_id=_pseudonym(f"device:{label}"),
        scopes=(PaidScope.BILLING_ADMINISTER,),
        verified_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=10),
        active=True,
    )


class SyntheticCheckoutTransport:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.checkout_calls: list[dict[str, str]] = []
        self.portal_calls: list[dict[str, str]] = []

    def create_checkout(self, **values: str) -> str:
        self.checkout_calls.append(values)
        if self.fail:
            raise TimeoutError("SYNTHETIC_PRIVATE_PROVIDER_DETAIL")
        return CHECKOUT_URL

    def create_portal(self, **values: str) -> str:
        self.portal_calls.append(values)
        if self.fail:
            raise TimeoutError("SYNTHETIC_PRIVATE_PROVIDER_DETAIL")
        return PORTAL_URL


class LocalCheckoutApplication:
    def __init__(
        self,
        tmp_path: Path,
        *,
        enabled: bool = True,
        fail_transport: bool = False,
        principals: dict[str, PaidPrincipal] | None = None,
        compose_service: bool = True,
        compose_resolver: bool = True,
    ) -> None:
        self.settings = AppSettings(
            home=tmp_path / "app-home",
            host="127.0.0.1",
            port=18765,
            paid_product_development_api=enabled,
        )
        self.store = PaidProductSqliteStore.under(tmp_path / "paid-state")
        self.store.initialize()
        self.authorizer = DevelopmentPrincipalAuthorizer()
        self.principals = principals or {
            "tenant-a": _principal(ORG_A, "tenant-a"),
            "tenant-b": _principal(ORG_B, "tenant-b"),
        }
        for principal in self.principals.values():
            self.authorizer.register(principal)
        self.transport = SyntheticCheckoutTransport(fail=fail_transport)
        from prompt_enhancer.application.paid_product.checkout import CheckoutService

        self.service = CheckoutService(
            authorizer=self.authorizer,
            resolver=self.store,
            transport=self.transport,
            return_url=RETURN_URL,
        )
        self.compose_service = compose_service
        self.compose_resolver = compose_resolver
        self.client = self.client_for()

    def client_for(
        self,
        principal_name: str = "tenant-a",
        *,
        resolver_mode: str = "principal",
        compose_service: bool | None = None,
        compose_resolver: bool | None = None,
        service_override=None,
    ) -> TestClient:
        selected_principal = self.principals[principal_name]

        def resolve_principal(_request):
            if resolver_mode == "invalid":
                raise ValueError("SYNTHETIC_PRIVATE_RESOLVER_DETAIL")
            if resolver_mode == "missing":
                return None
            if resolver_mode != "principal":
                raise ValueError("synthetic_principal_unavailable")
            return selected_principal

        include_service = (
            self.compose_service if compose_service is None else compose_service
        )
        include_resolver = (
            self.compose_resolver if compose_resolver is None else compose_resolver
        )
        selected_service = self.service if service_override is None else service_override
        app = create_app(
            settings=self.settings,
            database=Database(self.settings.database_path),
            api_token=API_TOKEN,
            paid_checkout_service=selected_service if include_service else None,
            paid_principal_resolver=(
                resolve_principal if include_resolver else None
            ),
        )
        return TestClient(app, base_url="http://127.0.0.1:18765")

    def add_intent(
        self,
        *,
        organization_id: str = ORG_A,
        intent_id: str = INTENT_A,
        customer_id: str = "cus_example_a",
    ) -> None:
        with self.store:
            self.store.create_checkout_intent(
                organization_id=organization_id,
                intent_id=intent_id,
                customer_id=customer_id,
                price_id="price_example_monthly",
                return_destination=RETURN_URL,
            )

    @staticmethod
    def headers() -> dict[str, str]:
        return {API_TOKEN_HEADER: API_TOKEN}


def _checkout_path(intent_id: str = INTENT_A) -> str:
    return f"/v1/paid-product/checkout-intents/{intent_id}/session"


def _portal_path(request_id: str = "example-portal-request") -> str:
    return f"/v1/paid-product/portal/{request_id}/session"


def test_real_app_route_is_default_off_and_requires_local_auth(tmp_path: Path) -> None:
    disabled = LocalCheckoutApplication(tmp_path / "disabled", enabled=False)
    disabled.add_intent()
    missing_route = disabled.client.post(
        _checkout_path(), headers=disabled.headers()
    )
    assert missing_route.status_code == 404
    assert disabled.client.post(
        _portal_path(), headers=disabled.headers()
    ).status_code == 404
    assert disabled.transport.checkout_calls == []
    health = disabled.client.get("/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "cost_mode": "offline_only",
        "data_tier": "metadata",
    }

    missing_service = LocalCheckoutApplication(
        tmp_path / "missing-service", compose_service=False
    )
    missing_service.add_intent()
    assert missing_service.client.post(
        _checkout_path(), headers=missing_service.headers()
    ).status_code == 404

    missing_resolver = LocalCheckoutApplication(
        tmp_path / "missing-resolver", compose_resolver=False
    )
    missing_resolver.add_intent()
    assert missing_resolver.client.post(
        _checkout_path(), headers=missing_resolver.headers()
    ).status_code == 404

    enabled = LocalCheckoutApplication(tmp_path / "enabled")
    enabled.add_intent()
    denied = enabled.client.post(_checkout_path())
    assert denied.status_code == 401
    assert enabled.transport.checkout_calls == []


def test_browser_cookie_mutation_requires_same_origin_and_csrf(tmp_path: Path) -> None:
    composed = LocalCheckoutApplication(tmp_path)
    composed.add_intent()
    client = composed.client
    session = client.get("/auth/session")
    assert session.status_code == 200
    csrf = session.json()["csrf_token"]

    path = _checkout_path()
    assert client.post(path).status_code == 403
    assert client.post(
        path,
        headers={"Origin": "http://127.0.0.1:18765"},
    ).status_code == 403

    accepted = client.post(
        path,
        json={
            "principal": "tenant-b",
            "organization_id": ORG_B,
            "customer_id": "cus_attacker",
            "price_id": "price_attacker",
            "return_destination": "https://attacker.invalid/",
        },
        headers={
            "Origin": "http://127.0.0.1:18765",
            CSRF_HEADER: csrf,
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {"url": CHECKOUT_URL}
    assert len(composed.transport.checkout_calls) == 1
    assert composed.transport.checkout_calls[0]["customer_id"] == "cus_example_a"
    assert composed.transport.checkout_calls[0]["price_id"] == "price_example_monthly"
    assert composed.transport.checkout_calls[0]["success_url"] == RETURN_URL


def test_reopened_sqlite_intent_is_tenant_scoped_and_unknown_intent_is_unavailable(
    tmp_path: Path,
) -> None:
    composed = LocalCheckoutApplication(tmp_path)
    composed.add_intent()
    reopened = PaidProductSqliteStore(composed.store.path)
    assert reopened.initialize() > 0

    from prompt_enhancer.application.paid_product.checkout import CheckoutService

    service = CheckoutService(
        authorizer=composed.authorizer,
        resolver=reopened,
        transport=composed.transport,
        return_url=RETURN_URL,
    )
    client = composed.client_for(service_override=service)
    tenant_b_client = composed.client_for(
        "tenant-b",
        service_override=service,
    )

    missing = client.post(
        _checkout_path("example-unknown-intent"),
        headers={API_TOKEN_HEADER: API_TOKEN},
    )
    assert missing.status_code == 503
    assert missing.json() == {"detail": {"code": "checkout_unavailable"}}

    cross_tenant = tenant_b_client.post(
        _checkout_path(),
        headers={API_TOKEN_HEADER: API_TOKEN},
    )
    assert cross_tenant.status_code == 503
    assert cross_tenant.json() == {"detail": {"code": "checkout_unavailable"}}
    assert composed.transport.checkout_calls == []

    owner = client.post(
        _checkout_path(),
        headers={API_TOKEN_HEADER: API_TOKEN},
    )
    assert owner.status_code == 200
    assert composed.transport.checkout_calls[0]["customer_id"] == "cus_example_a"


def test_revoked_principal_is_403_separately_from_unknown_intent_503(
    tmp_path: Path,
) -> None:
    composed = LocalCheckoutApplication(tmp_path)
    composed.add_intent()
    headers = composed.headers()

    unknown = composed.client.post(
        _checkout_path("example-unknown-intent"),
        headers=headers,
    )
    assert unknown.status_code == 503

    principal = composed.principals["tenant-a"]
    composed.authorizer.revoke_user(ORG_A, principal.user_id)
    revoked = composed.client.post(_checkout_path(), headers=headers)
    assert revoked.status_code == 403
    assert revoked.json() == {"detail": {"code": "default_deny"}}
    assert revoked.headers["cache-control"] == "no-store, private"
    revoked_portal = composed.client.post(_portal_path(), headers=headers)
    assert revoked_portal.status_code == 403
    assert revoked_portal.json() == {"detail": {"code": "default_deny"}}
    assert revoked_portal.headers["cache-control"] == "no-store, private"
    assert composed.transport.checkout_calls == []
    assert composed.transport.portal_calls == []


@pytest.mark.parametrize("resolver_mode", ["invalid", "missing"])
def test_invalid_or_missing_server_principal_is_denied_without_leaking_resolver_error(
    tmp_path: Path,
    resolver_mode: str,
) -> None:
    composed = LocalCheckoutApplication(tmp_path)
    composed.add_intent()
    client = composed.client_for(resolver_mode=resolver_mode)

    response = client.post(_checkout_path(), headers={API_TOKEN_HEADER: API_TOKEN})

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "default_deny"}}
    assert "SYNTHETIC_PRIVATE_RESOLVER_DETAIL" not in response.text
    assert composed.transport.checkout_calls == []


def test_portal_without_one_unambiguous_customer_is_unavailable(tmp_path: Path) -> None:
    composed = LocalCheckoutApplication(tmp_path)
    headers = composed.headers()

    no_customer = composed.client.post(_portal_path(), headers=headers)
    assert no_customer.status_code == 503

    composed.add_intent(intent_id="example-portal-intent-a", customer_id="cus_example_a")
    composed.add_intent(intent_id="example-portal-intent-b", customer_id="cus_example_b")
    ambiguous = composed.client.post(_portal_path(), headers=headers)
    assert ambiguous.status_code == 503
    assert ambiguous.json() == {"detail": {"code": "checkout_unavailable"}}
    assert composed.transport.portal_calls == []


def test_portal_uses_reopened_server_owned_customer_and_is_not_cached(
    tmp_path: Path,
) -> None:
    composed = LocalCheckoutApplication(tmp_path)
    composed.add_intent()
    reopened = PaidProductSqliteStore(composed.store.path)
    reopened.initialize()

    from prompt_enhancer.application.paid_product.checkout import CheckoutService

    service = CheckoutService(
        authorizer=composed.authorizer,
        resolver=reopened,
        transport=composed.transport,
        return_url=RETURN_URL,
    )
    client = composed.client_for(service_override=service)
    response = client.post(
        _portal_path(),
        headers={API_TOKEN_HEADER: API_TOKEN},
        json={
            "organization_id": ORG_B,
            "customer_id": "cus_attacker",
            "return_url": "https://attacker.invalid/",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"url": PORTAL_URL}
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert composed.transport.portal_calls[0]["customer_id"] == "cus_example_a"
    assert composed.transport.portal_calls[0]["return_url"] == RETURN_URL


def test_provider_timeout_is_sanitized_and_never_cached(tmp_path: Path) -> None:
    composed = LocalCheckoutApplication(tmp_path, fail_transport=True)
    composed.add_intent()

    response = composed.client.post(_checkout_path(), headers=composed.headers())

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "checkout_unavailable"}}
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert "SYNTHETIC_PRIVATE_PROVIDER_DETAIL" not in response.text
