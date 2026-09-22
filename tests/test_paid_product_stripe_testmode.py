"""Synthetic contract tests for the narrow, credential-free Stripe adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
from pathlib import Path
import pytest

from fastapi.testclient import TestClient

from prompt_enhancer.api import create_app
from prompt_enhancer.application.paid_product.contracts import EntitlementFeature, StripeSubscriptionBinding
from prompt_enhancer.application.paid_product.services import BillingService
from prompt_enhancer.application.paid_product.errors import BillingWebhookError
from prompt_enhancer.config import AppSettings
from prompt_enhancer.database import Database
from prompt_enhancer.infrastructure.paid_product.sqlite import PaidProductSqliteStore
from prompt_enhancer.infrastructure.paid_product.stripe_testmode import (
    SUPPORTED_STRIPE_SNAPSHOT_API_VERSION,
    StripeTestmodeWebhookService,
    StripeWebhookRejected,
    StripeLedgerWebhookVerifier,
    stripe_identifier_pseudonym,
)


NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
SECRET = b"synthetic-stripe-testmode-webhook-secret-00001"
PSEUDONYM_KEY = b"synthetic-stripe-stable-pseudonym-key-0000001"
BRIDGE_KEY = b"synthetic-stripe-ledger-bridge-key-00000001"


def pid(value: str) -> str:
    return hashlib.sha256(("fictional:" + value).encode()).hexdigest()


def raw_event(*, event_id: str = "evt_fixture_01", state: str = "active", created: int | None = None, customer: str = "cus_fixture", subscription: str = "sub_fixture", price: str = "price_fixture", metadata: dict[str, str] | None = None, livemode: bool = False) -> bytes:
    return json.dumps({
        "id": event_id, "api_version": SUPPORTED_STRIPE_SNAPSHOT_API_VERSION,
        "created": int(NOW.timestamp()) if created is None else created,
        "livemode": livemode, "type": "invoice.paid",
        "data": {"object": {"object": "invoice", "customer": customer,
            "status": "paid" if state == "active" else state, "paid": state == "active", "metadata": metadata or {},
            "parent": {"type": "subscription_details", "subscription_details": {"subscription": subscription}},
            "lines": {"data": [{"object": "line_item", "parent": {"type": "subscription_item_details", "subscription_item_details": {"subscription_item": "si_fixture", "subscription": subscription}}, "pricing": {"type": "price_details", "price_details": {"price": price}}, "period": {"end": int(NOW.timestamp()) + 3600}}]}}},
    }, separators=(",", ":")).encode("utf-8")


def signature(raw: bytes, *, at: datetime = NOW) -> str:
    timestamp = int(at.timestamp())
    digest = hmac.new(SECRET, str(timestamp).encode() + b"." + raw, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def composed(tmp_path: Path) -> tuple[PaidProductSqliteStore, StripeTestmodeWebhookService]:
    store = PaidProductSqliteStore.under(tmp_path)
    store.initialize()
    binding = StripeSubscriptionBinding(
        organization_id=pid("organization"),
        customer_pseudonym=stripe_identifier_pseudonym(PSEUDONYM_KEY, "cus_fixture"),
        subscription_pseudonym=stripe_identifier_pseudonym(PSEUDONYM_KEY, "sub_fixture"),
        price_pseudonym=stripe_identifier_pseudonym(PSEUDONYM_KEY, "price_fixture"),
        feature=EntitlementFeature.HOSTED_DEEP_ANALYSIS,
        created_at=NOW,
    )
    with store:
        store.save_stripe_subscription_binding(binding)
    billing = BillingService(store=store, transaction=store, verifier=StripeLedgerWebhookVerifier(BRIDGE_KEY))
    return store, StripeTestmodeWebhookService(signing_secret=SECRET, pseudonym_key=PSEUDONYM_KEY, ledger_bridge_key=BRIDGE_KEY, bindings=store, billing=billing)


def test_signed_snapshot_grants_and_identical_replay_is_idempotent(tmp_path: Path) -> None:
    store, service = composed(tmp_path)
    raw = raw_event()
    assert service.process(raw, signature(raw), now=NOW).value == "applied"
    assert service.process(raw, signature(raw), now=NOW).value == "idempotent_replay"
    assert service._billing.entitlement(pid("organization"), EntitlementFeature.HOSTED_DEEP_ANALYSIS, now=NOW).enabled


def test_metadata_cannot_bind_another_tenant_or_grant_unmapped_subscription(tmp_path: Path) -> None:
    _store, service = composed(tmp_path)
    raw = raw_event(subscription="sub_attacker", metadata={"organization_id": pid("attacker")})
    try:
        service.process(raw, signature(raw), now=NOW)
    except StripeWebhookRejected as error:
        assert str(error) == "stripe_webhook_binding_missing"
    else:  # pragma: no cover - makes an accidental metadata authority obvious
        raise AssertionError("unmapped metadata granted an entitlement")


def test_same_effective_second_revocation_wins_over_reordered_late_grant(tmp_path: Path) -> None:
    store, service = composed(tmp_path)
    deleted = json.loads(raw_event(event_id="evt_deleted"))
    deleted["type"] = "customer.subscription.deleted"
    deleted["data"]["object"] = {"object": "subscription", "id": "sub_fixture", "customer": "cus_fixture", "status": "canceled", "items": {"data": [{"price": {"id": "price_fixture"}}]}}
    revoked = json.dumps(deleted, separators=(",", ":")).encode()
    active = raw_event(event_id="evt_late_active")
    service.process(revoked, signature(revoked), now=NOW)
    with pytest.raises(StripeWebhookRejected, match="subscription_canceled"):
        service.process(active, signature(active), now=NOW + timedelta(seconds=1))
    assert not service._billing.entitlement(pid("organization"), EntitlementFeature.HOSTED_DEEP_ANALYSIS, now=NOW).enabled
    assert len(store.entitlement_entries(pid("organization"), EntitlementFeature.HOSTED_DEEP_ANALYSIS)) == 1


def test_later_created_paid_invoice_cannot_resurrect_canceled_binding(tmp_path: Path) -> None:
    _store, service = composed(tmp_path)
    deleted = json.loads(raw_event(event_id="evt_deleted_terminal"))
    deleted["type"] = "customer.subscription.deleted"
    deleted["data"]["object"] = {"object": "subscription", "id": "sub_fixture", "customer": "cus_fixture", "status": "canceled", "items": {"data": [{"price": {"id": "price_fixture"}}]}}
    tombstone = json.dumps(deleted, separators=(",", ":")).encode()
    service.process(tombstone, signature(tombstone), now=NOW)
    later = raw_event(event_id="evt_late_paid", created=int(NOW.timestamp()) + 1)
    with pytest.raises(StripeWebhookRejected, match="subscription_canceled"):
        service.process(later, signature(later), now=NOW + timedelta(seconds=1))
    assert not service._billing.entitlement(pid("organization"), EntitlementFeature.HOSTED_DEEP_ANALYSIS, now=NOW + timedelta(seconds=1)).enabled


def test_tamper_livemode_version_and_stale_signature_never_mutate(tmp_path: Path) -> None:
    store, service = composed(tmp_path)
    raw = raw_event()
    wrong_version = raw.replace(SUPPORTED_STRIPE_SNAPSHOT_API_VERSION.encode(), b"2025-02-24.acacia")
    live = raw_event(livemode=True)
    cases = [
        (raw + b" ", signature(raw)),
        (live, signature(live)),
        (wrong_version, signature(wrong_version)),
        (raw, signature(raw, at=NOW - timedelta(minutes=6))),
    ]
    for body, header in cases:
        try:
            service.process(body, header, now=NOW)
        except StripeWebhookRejected:
            pass
        else:
            raise AssertionError("invalid Stripe event was accepted")
    assert store.entitlement_entries(pid("organization"), EntitlementFeature.HOSTED_DEEP_ANALYSIS) == ()


def test_endpoint_secret_rotation_keeps_stable_binding_and_replay_fence(tmp_path: Path) -> None:
    _store, service = composed(tmp_path)
    raw = raw_event()
    assert service.process(raw, signature(raw), now=NOW).value == "applied"
    replacement = b"synthetic-rotated-stripe-endpoint-secret-00001"
    rotated = StripeTestmodeWebhookService(
        signing_secret=replacement, pseudonym_key=PSEUDONYM_KEY,
        ledger_bridge_key=BRIDGE_KEY, bindings=service._bindings, billing=service._billing,
    )
    timestamp = int(NOW.timestamp())
    header = "t=%s,v1=%s" % (timestamp, hmac.new(replacement, str(timestamp).encode() + b"." + raw, hashlib.sha256).hexdigest())
    assert rotated.process(raw, header, now=NOW).value == "idempotent_replay"


def test_same_provider_event_id_with_different_signed_raw_body_conflicts(tmp_path: Path) -> None:
    _store, service = composed(tmp_path)
    first = raw_event()
    assert service.process(first, signature(first), now=NOW).value == "applied"
    changed = raw_event(metadata={"ignored": "but_changes_raw_digest"})
    try:
        service.process(changed, signature(changed), now=NOW)
    except BillingWebhookError:
        pass
    else:
        raise AssertionError("same event id with changed signed bytes was accepted")


def test_failed_ledger_append_rolls_back_adapter_replay_fence(tmp_path: Path, monkeypatch) -> None:
    store, service = composed(tmp_path)
    raw = raw_event(event_id="evt_rollback")

    def fail_append(self, entry):
        raise RuntimeError("synthetic_append_failure")

    monkeypatch.setattr(PaidProductSqliteStore, "append_entitlement", fail_append)
    try:
        service.process(raw, signature(raw), now=NOW)
    except RuntimeError as error:
        assert str(error) == "synthetic_append_failure"
    else:
        raise AssertionError("forced append failure was hidden")
    event_pseudonym = stripe_identifier_pseudonym(PSEUDONYM_KEY, "evt_rollback")
    assert store.webhook_digest(event_pseudonym) is None


def test_route_is_only_present_with_explicit_injected_service(tmp_path: Path) -> None:
    settings = AppSettings(home=tmp_path)
    base = TestClient(create_app(settings=settings, database=Database(tmp_path / "metrics.sqlite3"), api_token="t" * 32), base_url="http://127.0.0.1:8765")
    assert base.post("/v1/paid-product/stripe/webhook").status_code == 404
    store, service = composed(tmp_path / "paid")
    composed_app = create_app(settings=settings, database=Database(tmp_path / "metrics-2.sqlite3"), api_token="t" * 32, stripe_testmode_webhook_service=service, stripe_testmode_clock=lambda: NOW)
    app = TestClient(composed_app, base_url="http://127.0.0.1:8765")
    raw = raw_event()
    response = app.post("/v1/paid-product/stripe/webhook", content=raw, headers={"Stripe-Signature": signature(raw)})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert service._billing.entitlement(pid("organization"), EntitlementFeature.HOSTED_DEEP_ANALYSIS, now=NOW).enabled
    # Injecting Stripe ingress does not relax unrelated private mutations.
    assert app.post("/v1/application-updates/check").status_code == 401
