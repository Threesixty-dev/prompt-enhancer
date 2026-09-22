"""Adversarial synthetic regressions for the test-mode Stripe boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from prompt_enhancer.api import create_app
from prompt_enhancer.application.paid_product.contracts import (
    EntitlementDeltaKind,
    EntitlementFeature,
    SignedBillingWebhook,
    StripeSubscriptionBinding,
    WebhookDisposition,
)
from prompt_enhancer.application.paid_product.errors import BillingWebhookError
from prompt_enhancer.application.paid_product.services import BillingService
from prompt_enhancer.config import AppSettings
from prompt_enhancer.database import Database
from prompt_enhancer.infrastructure.paid_product.development import (
    DevelopmentWebhookVerifier,
    canonical_webhook_digest,
    canonical_webhook_signature,
)
from prompt_enhancer.infrastructure.paid_product.sqlite import (
    PAID_PRODUCT_DATABASE_FILENAME,
    PAID_PRODUCT_SCHEMA_VERSION,
    PaidProductSqliteStore,
    _EXPECTED_PAID_TABLES,
    _MIGRATIONS,
)
from prompt_enhancer.infrastructure.paid_product.stripe_testmode import (
    SUPPORTED_STRIPE_SNAPSHOT_API_VERSION,
    StripeLedgerWebhookVerifier,
    StripeTestmodeWebhookService,
    StripeWebhookRejected,
    stripe_identifier_pseudonym,
)
from prompt_enhancer.sqlite_migration_integrity import SqliteMigrationIntegrity


NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
SECRET = b"synthetic-stripe-testmode-webhook-secret-00001"
PSEUDONYM_KEY = b"synthetic-stripe-stable-pseudonym-key-0000001"
BRIDGE_KEY = b"synthetic-stripe-ledger-bridge-key-00000001"
BILLING_KEY = b"synthetic-billing-signature-key-000000001"


def pid(value: str) -> str:
    return hashlib.sha256(("fictional:" + value).encode("ascii")).hexdigest()


ORG = pid("stripe-organization")


def raw_invoice(
    *, event_id: str = "evt_invoice_fixture", created: int | None = None
) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "api_version": SUPPORTED_STRIPE_SNAPSHOT_API_VERSION,
            "created": int(NOW.timestamp()) if created is None else created,
            "livemode": False,
            "type": "invoice.paid",
            "data": {
                "object": {
                    "object": "invoice",
                    "customer": "cus_fixture",
                    "status": "paid",
                    "paid": True,
                    "parent": {
                        "type": "subscription_details",
                        "subscription_details": {"subscription": "sub_fixture"},
                    },
                    "lines": {
                        "data": [
                            {
                                "object": "line_item",
                                "parent": {
                                    "type": "subscription_item_details",
                                    "subscription_item_details": {
                                        "subscription_item": "si_fixture",
                                        "subscription": "sub_fixture",
                                    },
                                },
                                "pricing": {
                                    "type": "price_details",
                                    "price_details": {"price": "price_fixture"},
                                },
                                "period": {
                                    "end": int(NOW.timestamp()) + 3600
                                },
                            }
                        ]
                    },
                }
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")


def raw_cancellation(*, event_id: str) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "api_version": SUPPORTED_STRIPE_SNAPSHOT_API_VERSION,
            "created": int(NOW.timestamp()),
            "livemode": False,
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "object": "subscription",
                    "id": "sub_fixture",
                    "customer": "cus_fixture",
                    "status": "canceled",
                    "items": {"data": [{"price": {"id": "price_fixture"}}]},
                }
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")


def signature(raw: bytes, *, secret: bytes = SECRET, at: datetime = NOW) -> str:
    timestamp = int(at.timestamp())
    digest = hmac.new(
        secret, str(timestamp).encode("ascii") + b"." + raw, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def composed(root: Path) -> tuple[PaidProductSqliteStore, StripeTestmodeWebhookService]:
    store = PaidProductSqliteStore.under(root)
    store.initialize()
    binding = StripeSubscriptionBinding(
        organization_id=ORG,
        customer_pseudonym=stripe_identifier_pseudonym(
            PSEUDONYM_KEY, "cus_fixture"
        ),
        subscription_pseudonym=stripe_identifier_pseudonym(
            PSEUDONYM_KEY, "sub_fixture"
        ),
        price_pseudonym=stripe_identifier_pseudonym(PSEUDONYM_KEY, "price_fixture"),
        feature=EntitlementFeature.HOSTED_DEEP_ANALYSIS,
        created_at=NOW,
    )
    with store:
        store.save_stripe_subscription_binding(binding)
    billing = BillingService(
        store=store,
        transaction=store,
        verifier=StripeLedgerWebhookVerifier(BRIDGE_KEY),
    )
    service = StripeTestmodeWebhookService(
        signing_secret=SECRET,
        pseudonym_key=PSEUDONYM_KEY,
        ledger_bridge_key=BRIDGE_KEY,
        bindings=store,
        billing=billing,
    )
    return store, service


def test_distinct_cancellation_events_preserve_idempotent_terminal_policy(
    tmp_path: Path,
) -> None:
    store, service = composed(tmp_path)
    first = raw_cancellation(event_id="evt_cancel_one")
    second = raw_cancellation(event_id="evt_cancel_two")

    assert service.process(first, signature(first), now=NOW) is WebhookDisposition.APPLIED
    assert service.process(second, signature(second), now=NOW) is WebhookDisposition.APPLIED
    assert service.process(first, signature(first), now=NOW) is WebhookDisposition.IDEMPOTENT_REPLAY
    assert store.stripe_subscription_canceled(
        stripe_identifier_pseudonym(PSEUDONYM_KEY, "sub_fixture")
    )
    entries = store.entitlement_entries(ORG, EntitlementFeature.HOSTED_DEEP_ANALYSIS)
    assert len(entries) == 2
    assert all(entry.kind is EntitlementDeltaKind.REVOKE for entry in entries)
    assert not service._billing.entitlement(
        ORG, EntitlementFeature.HOSTED_DEEP_ANALYSIS, now=NOW
    ).enabled


def test_replayed_accepted_invoice_stays_idempotent_after_cancellation(
    tmp_path: Path,
) -> None:
    _store, service = composed(tmp_path)
    invoice = raw_invoice(event_id="evt_paid_before_cancel")
    cancellation = raw_cancellation(event_id="evt_cancel_after_paid")
    assert service.process(invoice, signature(invoice), now=NOW) is WebhookDisposition.APPLIED
    assert service.process(cancellation, signature(cancellation), now=NOW) is WebhookDisposition.APPLIED

    assert service.process(invoice, signature(invoice), now=NOW) is WebhookDisposition.IDEMPOTENT_REPLAY
    assert not service._billing.entitlement(
        ORG, EntitlementFeature.HOSTED_DEEP_ANALYSIS, now=NOW
    ).enabled


def test_cancellation_append_failure_rolls_back_tombstone_and_event_fence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, service = composed(tmp_path)
    raw = raw_cancellation(event_id="evt_cancel_rollback")

    def fail_append(_self: PaidProductSqliteStore, _entry: object) -> None:
        raise RuntimeError("synthetic_append_failure")

    monkeypatch.setattr(PaidProductSqliteStore, "append_entitlement", fail_append)
    with pytest.raises(RuntimeError, match="synthetic_append_failure"):
        service.process(raw, signature(raw), now=NOW)

    subscription = stripe_identifier_pseudonym(PSEUDONYM_KEY, "sub_fixture")
    event = stripe_identifier_pseudonym(PSEUDONYM_KEY, "evt_cancel_rollback")
    assert not store.stripe_subscription_canceled(subscription)
    assert store.webhook_digest(event) is None
    assert store.entitlement_entries(ORG, EntitlementFeature.HOSTED_DEEP_ANALYSIS) == ()


def _direct_webhook(
    label: str,
    *,
    kind: EntitlementDeltaKind,
    effective_at: datetime,
) -> SignedBillingWebhook:
    draft = SignedBillingWebhook(
        provider_event_id=pid("direct-event-" + label),
        provider_event_digest=pid("direct-digest-" + label),
        organization_id=ORG,
        entry_id=pid("direct-entry-" + label),
        feature=EntitlementFeature.HOSTED_DEEP_ANALYSIS,
        kind=kind,
        effective_at=effective_at,
        expires_at=(effective_at + timedelta(hours=1))
        if kind is EntitlementDeltaKind.GRANT
        else None,
        delivered_at=effective_at,
        signature=SecretStr("0" * 64),
    )
    digested = draft.model_copy(
        update={"provider_event_digest": canonical_webhook_digest(draft)}
    )
    return digested.model_copy(
        update={
            "signature": SecretStr(canonical_webhook_signature(digested, BILLING_KEY))
        }
    )


def test_generic_billing_allows_later_legitimate_grant_after_revoke(
    tmp_path: Path,
) -> None:
    store = PaidProductSqliteStore.under(tmp_path)
    store.initialize()
    billing = BillingService(
        store=store,
        transaction=store,
        verifier=DevelopmentWebhookVerifier(BILLING_KEY),
    )
    revoked_at = NOW
    granted_at = NOW + timedelta(minutes=5)
    billing.process_webhook(
        _direct_webhook("revoke", kind=EntitlementDeltaKind.REVOKE, effective_at=revoked_at),
        now=revoked_at,
    )
    billing.process_webhook(
        _direct_webhook("later-grant", kind=EntitlementDeltaKind.GRANT, effective_at=granted_at),
        now=granted_at,
    )

    projection = billing.entitlement(
        ORG, EntitlementFeature.HOSTED_DEEP_ANALYSIS, now=granted_at
    )
    assert projection.enabled is True
    assert projection.effective_at == granted_at


def _bridge_signed_webhook() -> SignedBillingWebhook:
    draft = SignedBillingWebhook(
        provider_event_id=pid("bridge-event"),
        provider_event_digest=pid("bridge-digest"),
        organization_id=ORG,
        entry_id=pid("bridge-entry"),
        feature=EntitlementFeature.HOSTED_DEEP_ANALYSIS,
        kind=EntitlementDeltaKind.GRANT,
        effective_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        delivered_at=NOW,
        signature=SecretStr("0" * 64),
    )
    material = {
        "delivered_at": draft.delivered_at.isoformat(),
        "effective_at": draft.effective_at.isoformat(),
        "entry_id": draft.entry_id,
        "expires_at": draft.expires_at.isoformat(),
        "feature": draft.feature.value,
        "kind": draft.kind.value,
        "organization_id": draft.organization_id,
        "provider_event_digest": draft.provider_event_digest,
        "provider_event_id": draft.provider_event_id,
    }
    mac = hmac.new(
        BRIDGE_KEY,
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return draft.model_copy(update={"signature": SecretStr(mac)})


@pytest.mark.parametrize(
    "field, replacement",
    [
        ("delivered_at", NOW + timedelta(seconds=1)),
        ("effective_at", NOW + timedelta(seconds=1)),
        ("entry_id", pid("tampered-entry")),
        ("expires_at", NOW + timedelta(hours=2)),
        ("feature", EntitlementFeature.TEAM_SYNC),
        ("kind", EntitlementDeltaKind.REVOKE),
        ("organization_id", pid("tampered-organization")),
        ("provider_event_digest", pid("tampered-digest")),
        ("provider_event_id", pid("tampered-event")),
    ],
)
def test_every_normalized_bridge_mac_field_is_authenticated(
    tmp_path: Path, field: str, replacement: object
) -> None:
    store = PaidProductSqliteStore.under(tmp_path)
    store.initialize()
    billing = BillingService(
        store=store,
        transaction=store,
        verifier=StripeLedgerWebhookVerifier(BRIDGE_KEY),
    )
    tampered = _bridge_signed_webhook().model_copy(update={field: replacement})

    with pytest.raises(BillingWebhookError):
        billing.process_webhook(tampered, now=NOW)
    assert store.entitlement_entries(ORG, EntitlementFeature.HOSTED_DEEP_ANALYSIS) == ()


def _http_client(tmp_path: Path) -> TestClient:
    store, service = composed(tmp_path / "paid")
    del store
    settings = AppSettings(home=tmp_path)
    app = create_app(
        settings=settings,
        database=Database(tmp_path / "metrics.sqlite3"),
        api_token="fictional-local-test-token-00000001",
        stripe_testmode_webhook_service=service,
        stripe_testmode_clock=lambda: NOW,
    )
    return TestClient(app, base_url="http://127.0.0.1:8765")


@pytest.mark.parametrize("malformation", ["nan", "deep_json"])
def test_signed_nan_and_deep_json_are_http_400_not_500(
    tmp_path: Path, malformation: str
) -> None:
    raw = raw_invoice(event_id="evt_invalid_json")
    if malformation == "nan":
        marker = b'"created":'
        start = raw.index(marker) + len(marker)
        end = raw.index(b",", start)
        raw = raw[:start] + b"NaN" + raw[end:]
    else:
        raw = raw[:-1] + b',"padding":' + b"[" * 1100 + b"0" + b"]" * 1100 + b"}"
    response = _http_client(tmp_path).post(
        "/v1/paid-product/stripe/webhook",
        content=raw,
        headers={"Stripe-Signature": signature(raw)},
    )
    assert response.status_code == 400


def test_schema_three_database_replays_real_fourth_migration_and_preserves_binding(
    tmp_path: Path,
) -> None:
    store = PaidProductSqliteStore.under(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    binding = StripeSubscriptionBinding(
        organization_id=ORG,
        customer_pseudonym=stripe_identifier_pseudonym(PSEUDONYM_KEY, "cus_fixture"),
        subscription_pseudonym=stripe_identifier_pseudonym(PSEUDONYM_KEY, "sub_fixture"),
        price_pseudonym=stripe_identifier_pseudonym(PSEUDONYM_KEY, "price_fixture"),
        feature=EntitlementFeature.HOSTED_DEEP_ANALYSIS,
        created_at=NOW,
    )
    v3_integrity = SqliteMigrationIntegrity(
        scope="paid_product",
        ledger_table="paid_product_schema_migrations",
        checksum_table="paid_product_migration_checksums",
        schema_version=3,
        checksum_introduced_version=2,
        migrations=_MIGRATIONS[:3],
        application_tables=frozenset(
            _EXPECTED_PAID_TABLES
            - {
                "paid_product_schema_migrations",
                "paid_product_migration_checksums",
                "paid_stripe_subscription_tombstones",
            }
        ),
    )
    with sqlite3.connect(store.path, isolation_level=None) as connection:
        connection.execute("BEGIN IMMEDIATE")
        v3_integrity.create_ledger(connection)
        v3_integrity.apply_pending(
            connection,
            current=0,
            applied_at=NOW.isoformat(),
        )
        connection.execute(
            """
            INSERT INTO paid_stripe_subscription_bindings(
                customer_pseudonym, subscription_pseudonym, organization_id,
                price_pseudonym, feature, body_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                binding.customer_pseudonym,
                binding.subscription_pseudonym,
                binding.organization_id,
                binding.price_pseudonym,
                binding.feature.value,
                binding.model_dump_json(),
            ),
        )
        connection.execute("COMMIT")

    with sqlite3.connect(store.path) as before:
        assert before.execute("PRAGMA user_version").fetchone() == (3,)
        assert before.execute(
            "SELECT version FROM paid_product_schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,)]
        assert before.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            ("paid_stripe_subscription_tombstones",),
        ).fetchone() is None

    assert store.initialize() == PAID_PRODUCT_SCHEMA_VERSION == 5
    assert PAID_PRODUCT_DATABASE_FILENAME == store.path.name
    assert store.stripe_subscription_binding(
        binding.customer_pseudonym, binding.subscription_pseudonym
    ) == binding
    assert store.structural_check()
    with sqlite3.connect(store.path) as after:
        assert after.execute("PRAGMA user_version").fetchone() == (5,)
        assert after.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert after.execute("PRAGMA foreign_key_check").fetchall() == []
        assert after.execute(
            "SELECT version FROM paid_product_schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,), (5,)]
        assert after.execute(
            "SELECT version FROM paid_product_migration_checksums ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,), (5,)]
        assert after.execute(
            "SELECT subscription_pseudonym FROM paid_stripe_subscription_bindings"
        ).fetchall() == [(binding.subscription_pseudonym,)]
