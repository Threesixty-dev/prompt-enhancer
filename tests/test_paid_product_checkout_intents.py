"""Durability, migration, and concurrency tests for checkout intents."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import sqlite3
from threading import Barrier

import pytest

from prompt_enhancer.application.paid_product.contracts import (
    EntitlementFeature,
    StripeSubscriptionBinding,
)
from prompt_enhancer.infrastructure.paid_product.sqlite import (
    PAID_PRODUCT_SCHEMA_VERSION,
    PaidProductSqliteStore,
    _EXPECTED_PAID_TABLES,
    _MIGRATIONS,
)
from prompt_enhancer.infrastructure.paid_product.stripe_testmode import (
    stripe_identifier_pseudonym,
)
from prompt_enhancer.sqlite_migration_integrity import SqliteMigrationIntegrity


NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
CUSTOMER = "cus_checkout_fixture"
PRICE = "price_checkout_fixture"
RETURN_DESTINATION = "https://app.example.test/billing/return"


def pseudonym(value: str) -> str:
    return hashlib.sha256(("synthetic-checkout:" + value).encode("ascii")).hexdigest()


def make_store(root: Path) -> PaidProductSqliteStore:
    store = PaidProductSqliteStore.under(root)
    assert store.initialize() == PAID_PRODUCT_SCHEMA_VERSION
    return store


def create_intent(
    store: PaidProductSqliteStore,
    *,
    organization_id: str = pseudonym("organization-one"),
    intent_id: str = "checkout-intent-fixture",
    customer_id: str = CUSTOMER,
    price_id: str = PRICE,
    return_destination: str = RETURN_DESTINATION,
):
    with store:
        return store.create_checkout_intent(
            organization_id=organization_id,
            intent_id=intent_id,
            customer_id=customer_id,
            price_id=price_id,
            return_destination=return_destination,
        )


def _make_schema_v4_database(root: Path) -> tuple[PaidProductSqliteStore, StripeSubscriptionBinding]:
    """Apply production paid-product migrations 1–4 to a new historical DB."""

    store = PaidProductSqliteStore.under(root)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    binding = StripeSubscriptionBinding(
        organization_id=pseudonym("migration-organization"),
        customer_pseudonym=stripe_identifier_pseudonym(
            b"synthetic-checkout-migration-pseudonym-key-0001", "cus_migration_fixture"
        ),
        subscription_pseudonym=stripe_identifier_pseudonym(
            b"synthetic-checkout-migration-pseudonym-key-0001", "sub_migration_fixture"
        ),
        price_pseudonym=stripe_identifier_pseudonym(
            b"synthetic-checkout-migration-pseudonym-key-0001", "price_migration_fixture"
        ),
        feature=EntitlementFeature.HOSTED_DEEP_ANALYSIS,
        created_at=NOW,
    )
    schema_v4_integrity = SqliteMigrationIntegrity(
        scope="paid_product",
        ledger_table="paid_product_schema_migrations",
        checksum_table="paid_product_migration_checksums",
        schema_version=4,
        checksum_introduced_version=2,
        migrations=_MIGRATIONS[:4],
        application_tables=frozenset(
            _EXPECTED_PAID_TABLES
            - {
                "paid_product_schema_migrations",
                "paid_product_migration_checksums",
                "paid_checkout_intents",
            }
        ),
    )

    with sqlite3.connect(store.path, isolation_level=None) as connection:
        connection.execute("BEGIN IMMEDIATE")
        schema_v4_integrity.create_ledger(connection)
        schema_v4_integrity.apply_pending(
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
    return store, binding


def test_real_schema_v4_fixture_migrates_to_v5_and_preserves_existing_binding(
    tmp_path: Path,
) -> None:
    store, binding = _make_schema_v4_database(tmp_path)

    with sqlite3.connect(store.path) as before:
        assert before.execute("PRAGMA user_version").fetchone() == (4,)
        assert before.execute(
            "SELECT version FROM paid_product_schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,)]
        assert before.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            ("paid_checkout_intents",),
        ).fetchone() is None

    assert store.initialize() == 5
    assert PAID_PRODUCT_SCHEMA_VERSION == 5
    assert store.stripe_subscription_binding(
        binding.customer_pseudonym, binding.subscription_pseudonym
    ) == binding
    assert store.checkout_intent(pseudonym("migration-organization"), "none") is None
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


def test_checkout_intents_are_immutable_against_update_and_delete(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    created = create_intent(store)

    with sqlite3.connect(store.path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.IntegrityError, match="paid_checkout_intent_immutable"):
            connection.execute(
                """
                UPDATE paid_checkout_intents SET return_destination = ?
                WHERE organization_id = ? AND intent_id = ?
                """,
                ("https://app.example.test/changed", created.organization_id, created.intent_id),
            )
        with pytest.raises(sqlite3.IntegrityError, match="paid_checkout_intent_immutable"):
            connection.execute(
                "DELETE FROM paid_checkout_intents WHERE organization_id = ? AND intent_id = ?",
                (created.organization_id, created.intent_id),
            )
        connection.rollback()

    assert store.checkout_intent(created.organization_id, created.intent_id) == created


def test_checkout_intent_transaction_rollback_leaves_no_row(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    organization_id = pseudonym("rollback-organization")
    with pytest.raises(RuntimeError, match="synthetic_checkout_intent_abort"):
        with store:
            store.create_checkout_intent(
                organization_id=organization_id,
                intent_id="rollback-intent",
                customer_id=CUSTOMER,
                price_id=PRICE,
                return_destination=RETURN_DESTINATION,
            )
            raise RuntimeError("synthetic_checkout_intent_abort")

    assert store.checkout_intent(organization_id, "rollback-intent") is None
    with sqlite3.connect(store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM paid_checkout_intents WHERE organization_id = ?",
            (organization_id,),
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    "field",
    [
        "organization_id",
        "intent_id",
        "customer_id",
        "price_id",
        "return_destination",
    ],
)
@pytest.mark.parametrize("control", ["\n", "\x7f"])
def test_checkout_intent_rejects_control_characters_in_every_field(
    tmp_path: Path, field: str, control: str
) -> None:
    store = make_store(tmp_path)
    values = {
        "organization_id": pseudonym("control-organization"),
        "intent_id": "control-intent",
        "customer_id": CUSTOMER,
        "price_id": PRICE,
        "return_destination": RETURN_DESTINATION,
    }
    values[field] += control

    with pytest.raises(ValueError, match="paid_checkout_intent_invalid"):
        with store:
            store.create_checkout_intent(**values)

    assert store.checkout_intent(pseudonym("control-organization"), "control-intent") is None


def test_checkout_intent_is_tenant_keyed_idempotent_and_survives_reopen(
    tmp_path: Path,
) -> None:
    first_org = pseudonym("tenant-one")
    second_org = pseudonym("tenant-two")
    store = make_store(tmp_path)
    first = create_intent(store, organization_id=first_org)
    first_retry = create_intent(store, organization_id=first_org)
    second = create_intent(store, organization_id=second_org)

    assert first == first_retry
    assert first.idempotency_key != second.idempotency_key
    assert store.checkout_intent(first_org, first.intent_id) == first
    assert store.checkout_intent(second_org, second.intent_id) == second
    assert store.checkout_intent(pseudonym("tenant-unknown"), first.intent_id) is None

    reopened = PaidProductSqliteStore.under(tmp_path)
    assert reopened.initialize() == PAID_PRODUCT_SCHEMA_VERSION
    assert reopened.checkout_intent(first_org, first.intent_id) == first
    assert reopened.checkout_intent(second_org, second.intent_id) == second


def test_concurrent_separate_stores_same_payload_returns_same_intent(
    tmp_path: Path,
) -> None:
    first_store = make_store(tmp_path)
    second_store = PaidProductSqliteStore.under(tmp_path)
    assert second_store.initialize() == PAID_PRODUCT_SCHEMA_VERSION
    barrier = Barrier(2)
    organization_id = pseudonym("concurrent-same-organization")

    def create_on(store: PaidProductSqliteStore):
        barrier.wait(timeout=5)
        return create_intent(store, organization_id=organization_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(create_on, first_store)
        second_future = executor.submit(create_on, second_store)
        first = first_future.result(timeout=10)
        second = second_future.result(timeout=10)

    assert first == second
    assert first_store.checkout_intent(organization_id, first.intent_id) == first


def test_concurrent_separate_stores_conflicting_payload_has_one_winner(
    tmp_path: Path,
) -> None:
    first_store = make_store(tmp_path)
    second_store = PaidProductSqliteStore.under(tmp_path)
    assert second_store.initialize() == PAID_PRODUCT_SCHEMA_VERSION
    barrier = Barrier(2)
    organization_id = pseudonym("concurrent-conflict-organization")

    def create_variant(store: PaidProductSqliteStore, destination: str):
        barrier.wait(timeout=5)
        try:
            return create_intent(
                store,
                organization_id=organization_id,
                return_destination=destination,
            )
        except ValueError as error:
            if str(error) != "paid_checkout_intent_payload_conflict":
                raise
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            create_variant, first_store, "https://app.example.test/variant-one"
        )
        second_future = executor.submit(
            create_variant, second_store, "https://app.example.test/variant-two"
        )
        results = [first_future.result(timeout=10), second_future.result(timeout=10)]

    winners = [result for result in results if result != "conflict"]
    conflicts = [result for result in results if result == "conflict"]
    assert len(winners) == 1
    assert len(conflicts) == 1
    winning_intent = winners[0]
    assert (store_read := first_store.checkout_intent(organization_id, "checkout-intent-fixture"))
    assert store_read == winning_intent
