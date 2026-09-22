"""Offline-testable Stripe snapshot webhook adapter.

This module performs no Stripe API calls and does not read credentials.  Its
secret is constructor-injected solely by an explicitly composed test service.
It deliberately supports only the small subscription lifecycle below; all
other Stripe event types are rejected without a ledger mutation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
from typing import Any
from pydantic import SecretStr

from ...application.paid_product.contracts import (
    EntitlementDeltaKind,
    SignedBillingWebhook,
    StripeSubscriptionBinding,
    WebhookDisposition,
)
from ...application.paid_product.errors import BillingWebhookError
from ...application.paid_product.ports import StripeSubscriptionBindingStore
from ...application.paid_product.services import BillingService


MAX_STRIPE_WEBHOOK_BYTES = 64 * 1024
STRIPE_SIGNATURE_TOLERANCE = timedelta(minutes=5)
# This is the explicit snapshot Event version accepted by this test-mode slice.
SUPPORTED_STRIPE_SNAPSHOT_API_VERSION = "2025-03-31.basil"
SUPPORTED_STRIPE_EVENTS = frozenset(
    {"invoice.paid", "customer.subscription.deleted"}
)


class StripeWebhookRejected(ValueError):
    """A request is not an accepted Stripe test-mode snapshot event."""


class StripeLedgerWebhookVerifier:
    """BillingService bridge for a webhook already verified from raw bytes.

    This intentionally does not implement Stripe cryptography.  The ingress
    service above does that before constructing the internal receipt.
    """

    def __init__(self, bridge_key: bytes) -> None:
        self._bridge_key = bridge_key

    def verify(self, webhook: SignedBillingWebhook) -> bool:
        expected = _ledger_receipt_mac(self._bridge_key, webhook)
        return hmac.compare_digest(webhook.signature.get_secret_value(), expected)


def _ledger_receipt_mac(key: bytes, webhook: SignedBillingWebhook) -> str:
    material = {
        "delivered_at": webhook.delivered_at.isoformat(), "effective_at": webhook.effective_at.isoformat(),
        "entry_id": webhook.entry_id, "expires_at": None if webhook.expires_at is None else webhook.expires_at.isoformat(),
        "feature": webhook.feature.value, "kind": webhook.kind.value, "organization_id": webhook.organization_id,
        "provider_event_digest": webhook.provider_event_digest, "provider_event_id": webhook.provider_event_id,
    }
    return hmac.new(key, json.dumps(material, sort_keys=True, separators=(",", ":")).encode("ascii"), hashlib.sha256).hexdigest()


def stripe_identifier_pseudonym(secret: bytes, value: str) -> str:
    """Do not persist a raw Stripe identifier in the local billing database."""

    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


class StripeTestmodeWebhookService:
    """Verify raw Stripe bytes then map a small, server-bound lifecycle."""

    def __init__(
        self,
        *,
        signing_secret: bytes,
        pseudonym_key: bytes,
        ledger_bridge_key: bytes,
        bindings: StripeSubscriptionBindingStore,
        billing: BillingService,
    ) -> None:
        if min(len(signing_secret), len(pseudonym_key), len(ledger_bridge_key)) < 32:
            raise ValueError("Stripe test-mode keys must have at least 32 bytes")
        self._secret = signing_secret
        self._pseudonym_key = pseudonym_key
        self._ledger_bridge_key = ledger_bridge_key
        self._bindings = bindings
        self._billing = billing

    def process(
        self, raw_body: bytes, signature_header: str | None, *, now: datetime
    ) -> WebhookDisposition:
        if len(raw_body) == 0 or len(raw_body) > MAX_STRIPE_WEBHOOK_BYTES:
            raise StripeWebhookRejected("stripe_webhook_body_size_invalid")
        timestamp = self._verify_signature(raw_body, signature_header, now=now)
        event = self._parse_snapshot(raw_body)
        if event.get("livemode") is not False:
            raise StripeWebhookRejected("stripe_webhook_livemode_not_allowed")
        if event.get("api_version") != SUPPORTED_STRIPE_SNAPSHOT_API_VERSION:
            raise StripeWebhookRejected("stripe_webhook_api_version_unsupported")
        event_type = event.get("type")
        if event_type not in SUPPORTED_STRIPE_EVENTS:
            raise StripeWebhookRejected("stripe_webhook_event_unsupported")
        event_id = self._string(event, "id")
        created = event.get("created")
        if not isinstance(created, int) or isinstance(created, bool) or created < 0:
            raise StripeWebhookRejected("stripe_webhook_created_invalid")
        object_ = self._object(event)
        if object_.get("object") != ("invoice" if event_type == "invoice.paid" else "subscription"):
            raise StripeWebhookRejected("stripe_webhook_object_type_invalid")
        customer = self._string(object_, "customer")
        subscription = self._subscription(object_, event_type)
        binding = self._bindings.stripe_subscription_binding(
            stripe_identifier_pseudonym(self._pseudonym_key, customer),
            stripe_identifier_pseudonym(self._pseudonym_key, subscription),
        )
        if binding is None:
            raise StripeWebhookRejected("stripe_webhook_binding_missing")
        subscription_pseudonym = binding.subscription_pseudonym
        expires_at = self._assert_bound_product(object_, binding, created=created, event_type=event_type)
        kind = self._delta(event_type, object_)
        try:
            effective_at = datetime.fromtimestamp(created, UTC).replace(microsecond=0)
        except (OverflowError, OSError, ValueError):
            raise StripeWebhookRejected("stripe_webhook_created_invalid") from None
        if effective_at > now:
            raise StripeWebhookRejected("stripe_webhook_created_future")
        # Signature-time is deliberately only a verification tolerance.  Stripe
        # can retry a valid event much later, so it is not the entitlement time.
        del timestamp
        provider_id = stripe_identifier_pseudonym(self._pseudonym_key, event_id)
        digest = hashlib.sha256(raw_body).hexdigest()
        webhook = SignedBillingWebhook(
            provider_event_id=provider_id,
            provider_event_digest=digest,
            organization_id=binding.organization_id,
            entry_id=stripe_identifier_pseudonym(self._pseudonym_key, "entry:" + event_id),
            feature=binding.feature,
            kind=kind,
            effective_at=effective_at,
            expires_at=expires_at,
            delivered_at=now,
            signature="",
        )
        webhook = webhook.model_copy(update={"signature": SecretStr(_ledger_receipt_mac(self._ledger_bridge_key, webhook))})
        def locked_policy(_webhook: SignedBillingWebhook) -> None:
            if event_type == "customer.subscription.deleted":
                self._bindings.tombstone_stripe_subscription(subscription_pseudonym)
            elif self._bindings.stripe_subscription_canceled(subscription_pseudonym):
                raise StripeWebhookRejected("stripe_webhook_subscription_canceled")
        return self._billing.process_webhook(webhook, now=now, locked_policy=locked_policy)

    def _verify_signature(
        self, raw_body: bytes, header: str | None, *, now: datetime
    ) -> int:
        if header is None or len(header) > 4096 or not header.isascii():
            raise StripeWebhookRejected("stripe_signature_missing")
        fields: dict[str, list[str]] = {}
        for component in header.split(","):
            key, separator, value = component.strip().partition("=")
            if not separator or not key or not value:
                raise StripeWebhookRejected("stripe_signature_malformed")
            fields.setdefault(key, []).append(value)
        if len(fields.get("t", [])) != 1 or not fields["t"][0].isdigit() or len(fields["t"][0]) > 10:
            raise StripeWebhookRejected("stripe_signature_timestamp_invalid")
        try:
            timestamp = int(fields["t"][0])
        except (KeyError, ValueError):
            raise StripeWebhookRejected("stripe_signature_timestamp_invalid") from None
        signed = str(timestamp).encode("ascii") + b"." + raw_body
        expected = hmac.new(self._secret, signed, hashlib.sha256).hexdigest()
        supplied = fields.get("v1", [])
        if not supplied or not any(hmac.compare_digest(value, expected) for value in supplied):
            raise StripeWebhookRejected("stripe_signature_invalid")
        try:
            signed_at = datetime.fromtimestamp(timestamp, UTC)
        except (OverflowError, OSError, ValueError):
            raise StripeWebhookRejected("stripe_signature_timestamp_invalid") from None
        if abs(now - signed_at) > STRIPE_SIGNATURE_TOLERANCE:
            raise StripeWebhookRejected("stripe_signature_stale")
        return timestamp

    @staticmethod
    def _parse_snapshot(raw_body: bytes) -> dict[str, Any]:
        def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise StripeWebhookRejected("stripe_webhook_json_duplicate_key")
                result[key] = value
            return result
        try:
            decoded = json.loads(
                raw_body.decode("utf-8"), object_pairs_hook=no_duplicate_keys,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
            raise StripeWebhookRejected("stripe_webhook_json_invalid") from None
        if not isinstance(decoded, dict):
            raise StripeWebhookRejected("stripe_webhook_shape_invalid")
        if not StripeTestmodeWebhookService._bounded_json(decoded):
            raise StripeWebhookRejected("stripe_webhook_shape_invalid")
        return decoded

    @staticmethod
    def _bounded_json(value: Any, depth: int = 0, count: list[int] | None = None) -> bool:
        count = [0] if count is None else count
        count[0] += 1
        if depth > 32 or count[0] > 2048:
            return False
        if isinstance(value, dict):
            return all(StripeTestmodeWebhookService._bounded_json(v, depth + 1, count) for v in value.values())
        if isinstance(value, list):
            return all(StripeTestmodeWebhookService._bounded_json(v, depth + 1, count) for v in value)
        return value is None or isinstance(value, (str, int, bool))

    @staticmethod
    def _string(object_: dict[str, Any], field: str) -> str:
        value = object_.get(field)
        if not isinstance(value, str) or not value or len(value) > 255:
            raise StripeWebhookRejected("stripe_webhook_object_invalid")
        return value

    @classmethod
    def _object(cls, event: dict[str, Any]) -> dict[str, Any]:
        data = event.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("object"), dict):
            raise StripeWebhookRejected("stripe_webhook_object_invalid")
        return data["object"]

    def _assert_bound_product(
        self, object_: dict[str, Any], binding: StripeSubscriptionBinding, *, created: int, event_type: str
    ) -> datetime | None:
        items = object_.get("lines") if event_type == "invoice.paid" else object_.get("items")
        if not isinstance(items, dict) or not isinstance(items.get("data"), list):
            raise StripeWebhookRejected("stripe_webhook_product_invalid")
        prices = []
        for item in items["data"]:
            if not isinstance(item, dict):
                raise StripeWebhookRejected("stripe_webhook_product_invalid")
            if event_type == "invoice.paid":
                pricing = item.get("pricing")
                details = pricing.get("price_details") if isinstance(pricing, dict) and pricing.get("type") == "price_details" else None
                price = details.get("price") if isinstance(details, dict) else None
                if item.get("object") != "line_item":
                    raise StripeWebhookRejected("stripe_webhook_product_invalid")
                parent = item.get("parent")
                if not isinstance(parent, dict) or parent.get("type") != "subscription_item_details":
                    raise StripeWebhookRejected("stripe_webhook_parent_invalid")
                parent_details = parent.get("subscription_item_details")
                line_subscription = parent_details.get("subscription") if isinstance(parent_details, dict) else None
                if (
                    not isinstance(line_subscription, str)
                    or stripe_identifier_pseudonym(self._pseudonym_key, line_subscription)
                    != binding.subscription_pseudonym
                ):
                    raise StripeWebhookRejected("stripe_webhook_subscription_mismatch")
            else:
                price = item.get("price", {}).get("id") if isinstance(item.get("price"), dict) else None
            if not isinstance(price, str):
                raise StripeWebhookRejected("stripe_webhook_product_invalid")
            prices.append(stripe_identifier_pseudonym(self._pseudonym_key, price))
        if len(prices) != 1 or prices != [binding.price_pseudonym]:
            raise StripeWebhookRejected("stripe_webhook_product_mismatch")
        if event_type == "customer.subscription.deleted":
            return None
        # A subscription update can report `active` during collections changes;
        # require an explicit future paid-through period and never issue an
        # unbounded entitlement from a status field.
        if event_type == "invoice.paid":
            line = items["data"][0]
            period = line.get("period") if isinstance(line, dict) else None
            period_end = period.get("end") if isinstance(period, dict) else None
        else:
            period_end = object_.get("current_period_end")
        if not isinstance(period_end, int) or isinstance(period_end, bool) or period_end <= created:
            raise StripeWebhookRejected("stripe_webhook_period_invalid")
        try:
            return datetime.fromtimestamp(period_end, UTC).replace(microsecond=0)
        except (OverflowError, OSError, ValueError):
            raise StripeWebhookRejected("stripe_webhook_period_invalid") from None

    def _subscription(self, object_: dict[str, Any], event_type: str) -> str:
        if event_type != "invoice.paid":
            return self._string(object_, "id")
        parent = object_.get("parent")
        details = parent.get("subscription_details") if isinstance(parent, dict) and parent.get("type") == "subscription_details" else None
        if not isinstance(details, dict):
            raise StripeWebhookRejected("stripe_webhook_parent_invalid")
        return self._string(details, "subscription")

    @staticmethod
    def _delta(event_type: str, object_: dict[str, Any]) -> EntitlementDeltaKind:
        if event_type == "customer.subscription.deleted":
            if object_.get("status") != "canceled":
                raise StripeWebhookRejected("stripe_webhook_subscription_not_canceled")
            return EntitlementDeltaKind.REVOKE
        # A signed event with arbitrary metadata/status never grants access.
        if event_type == "invoice.paid":
            if object_.get("status") != "paid" or object_.get("paid") is not True:
                raise StripeWebhookRejected("stripe_webhook_invoice_unpaid")
            return EntitlementDeltaKind.GRANT
        if object_.get("status") != "canceled":
            return EntitlementDeltaKind.REVOKE
        return EntitlementDeltaKind.REVOKE


__all__ = [
    "MAX_STRIPE_WEBHOOK_BYTES",
    "STRIPE_SIGNATURE_TOLERANCE",
    "SUPPORTED_STRIPE_EVENTS",
    "SUPPORTED_STRIPE_SNAPSHOT_API_VERSION",
    "StripeTestmodeWebhookService",
    "StripeLedgerWebhookVerifier",
    "StripeWebhookRejected",
    "stripe_identifier_pseudonym",
]
