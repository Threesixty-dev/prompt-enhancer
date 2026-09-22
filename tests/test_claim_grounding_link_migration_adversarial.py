from __future__ import annotations

import sqlite3

import pytest

from prompt_enhancer.infrastructure.sqlite.migrations import MIGRATION_67
from test_claim_grounding_migration import (
    CENSUS, CENSUS_FINGERPRINT, EXPECTED_PUBLICATION, MANIFEST,
    R, S, STAMP, W, _classification, _db as db66, _header, _seal,
)

LINK = "a" * 64
CANDIDATE = "7" * 64
REF = "8" * 64


def _db() -> sqlite3.Connection:
    db = db66()
    db.executescript(MIGRATION_67)
    _header(db)
    _classification(db, candidate_id=CANDIDATE)
    _seal(db)
    return db


def _review_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "link_review_id": LINK, "session_id": S, "census_id": CENSUS,
        "candidate_id": CANDIDATE, "source_run_id": R,
        "source_window_fingerprint": W, "census_fingerprint": CENSUS_FINGERPRINT,
        "manifest_fingerprint": MANIFEST, "expected_publication_fingerprint": EXPECTED_PUBLICATION,
        "observed_set_fingerprint": "1" * 64, "selected_evidence_fingerprint": "2" * 64,
        "review_receipt_id": "3" * 64, "review_fingerprint": "4" * 64,
        "decision": "linked_observed_checks", "selected_count": 1,
        "idempotency_key_digest": "5" * 64, "command_fingerprint": "6" * 64,
        "created_at": STAMP, "schema_version": "claim-grounding-link-reviewed-decision-v1",
        "policy_version": "native-reviewed-claim-link-coverage-v1",
        "metadata_persisted": 1, "candidate_prose_persisted": 0,
        "proposal_only": 1, "measured": 0, "metric_authority_established": 0,
    }
    values.update(overrides)
    return values


def _review(db: sqlite3.Connection, *, replace: bool = False, **overrides: object) -> None:
    values = _review_values(**overrides)
    columns = ",".join(values)
    verb = "INSERT OR REPLACE" if replace else "INSERT"
    db.execute(f"{verb} INTO claim_grounding_link_reviews({columns}) VALUES({','.join(':'+key for key in values)})", values)


def _reference(db: sqlite3.Connection, *, replace: bool = False, **overrides: object) -> None:
    values: dict[str, object] = {
        "link_review_id": LINK, "ordinal": 0, "source_reference_id": REF,
        "observed_sequence": 1, "provider": "codex", "check_kind": "test",
        "observed_outcome": "passed", "provider_execution_status": "completed",
        "exit_code": 0, "source_completion_schema_version": "observed-check-completion-v1",
        "outcome_interpreter_version": "pytest-exit-status-v1",
        "classifier_version": "local-command-rules-v1", "normalizer_version": "strict-shell-free-v2",
        "rule_id": "test.pytest", "local_only": 1, "content_persistence_allowed": 0,
    }
    values.update(overrides)
    columns = ",".join(values)
    verb = "INSERT OR REPLACE" if replace else "INSERT"
    db.execute(f"{verb} INTO claim_grounding_link_review_selected_references({columns}) VALUES({','.join(':'+key for key in values)})", values)


def _seal_link(db: sqlite3.Connection, *, replace: bool = False, **overrides: object) -> None:
    values: dict[str, object] = {
        "link_review_id": LINK, "selected_count": 1, "census_id": CENSUS,
        "candidate_id": CANDIDATE, "census_fingerprint": CENSUS_FINGERPRINT,
        "manifest_fingerprint": MANIFEST, "expected_publication_fingerprint": EXPECTED_PUBLICATION,
        "observed_set_fingerprint": "1" * 64, "selected_evidence_fingerprint": "2" * 64,
        "issuance_seal": "9" * 64, "sealed_at": STAMP,
    }
    values.update(overrides)
    columns = ",".join(values)
    verb = "INSERT OR REPLACE" if replace else "INSERT"
    db.execute(f"{verb} INTO claim_grounding_link_review_seals({columns}) VALUES({','.join(':'+key for key in values)})", values)


def test_migration67_rejects_null_identity_flags_bad_timestamp_and_nul() -> None:
    for field, value in (("link_review_id", None), ("metadata_persisted", None), ("created_at", "2026-01-01T00:00:00Z"), ("created_at", "x" * 26 + "+00:00"), ("created_at", "2026-02-30T00:00:00.000000+00:00"), ("selected_evidence_fingerprint", "2" * 64 + "\0")):
        db = _db()
        with pytest.raises(sqlite3.IntegrityError):
            _review(db, **{field: value})


def test_migration67_rejects_parent_binding_drift_and_unsealed_parent() -> None:
    db = _db()
    with pytest.raises(sqlite3.IntegrityError):
        _review(db, census_fingerprint="a" * 64)
    db = db66(); db.executescript(MIGRATION_67); _header(db); _classification(db, candidate_id=CANDIDATE)
    with pytest.raises(sqlite3.IntegrityError):
        _review(db)


def test_migration67_rejects_duplicate_reference_and_idempotency() -> None:
    db = _db(); _review(db); _reference(db)
    with pytest.raises(sqlite3.IntegrityError):
        _reference(db, ordinal=1)
    with pytest.raises(sqlite3.IntegrityError):
        _review(db, link_review_id="a" * 63 + "b")


def test_migration67_rejects_postseal_mutation_delete_and_overflow() -> None:
    db = _db(); _review(db); _reference(db); _seal_link(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE claim_grounding_link_reviews SET decision='unresolved' WHERE link_review_id=?", (LINK,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE claim_grounding_link_review_selected_references SET ordinal=1 WHERE link_review_id=?", (LINK,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM claim_grounding_link_review_seals WHERE link_review_id=?", (LINK,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM claim_grounding_link_reviews WHERE link_review_id=?", (LINK,))
    db = _db()
    with pytest.raises(sqlite3.IntegrityError):
        _review(db, selected_count=129)
    db = _db(); _review(db)
    with pytest.raises(sqlite3.IntegrityError):
        _reference(db, ordinal=128)


def test_migration67_rejects_replace_that_would_bypass_append_only_guards() -> None:
    db = _db(); _review(db); _reference(db); _seal_link(db)
    with pytest.raises(sqlite3.IntegrityError):
        _review(db, replace=True, command_fingerprint="a" * 64)


def test_migration67_rejects_replace_with_different_parent_pk() -> None:
    db = _db(); _review(db)
    with pytest.raises(sqlite3.IntegrityError):
        _review(db, replace=True, link_review_id="a" * 63 + "b")


def test_migration67_rejects_preseal_reference_replacement() -> None:
    db = _db(); _review(db); _reference(db)
    with pytest.raises(sqlite3.IntegrityError):
        _reference(db, replace=True, source_reference_id="9" * 64)


def test_migration67_rejects_preseal_reference_ordinal_replacement() -> None:
    db = _db(); _review(db); _reference(db)
    with pytest.raises(sqlite3.IntegrityError):
        _reference(db, replace=True, ordinal=1)


def test_migration67_rejects_seal_replacement() -> None:
    db = _db(); _review(db); _reference(db); _seal_link(db)
    with pytest.raises(sqlite3.IntegrityError):
        _seal_link(db, replace=True, issuance_seal="8" * 64)


def test_migration67_rejects_malformed_seal_timestamps() -> None:
    for value in ("x" * 26 + "+00:00", "2026-02-30T00:00:00.000000+00:00"):
        db = _db(); _review(db); _reference(db)
        with pytest.raises(sqlite3.IntegrityError):
            _seal_link(db, sealed_at=value)


def test_migration67_privacy_cascade_removes_rows() -> None:
    db = _db(); _review(db); _reference(db); _seal_link(db)
    db.execute("DELETE FROM sessions WHERE session_id=?", (S,))
    assert db.execute("SELECT count(*) FROM claim_grounding_link_reviews").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM claim_grounding_link_review_selected_references").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM claim_grounding_link_review_seals").fetchone()[0] == 0
