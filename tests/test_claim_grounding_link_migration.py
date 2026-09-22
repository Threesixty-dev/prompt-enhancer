from __future__ import annotations

import sqlite3

import pytest

from prompt_enhancer.infrastructure.sqlite.migrations import MIGRATION_67
from test_claim_grounding_migration import (
    CENSUS, CENSUS_FINGERPRINT, EXPECTED_PUBLICATION, MANIFEST, R, S, STAMP,
    W, _classification, _db, _header, _seal,
)

LINK = "a" * 64
CANDIDATE = "7" * 64
OBSERVED_SET = "b" * 64
SELECTED_EVIDENCE = "c" * 64


def _m67_db() -> sqlite3.Connection:
    db = _db()
    _header(db)
    _classification(db, candidate_id=CANDIDATE)
    _seal(db)
    db.executescript(MIGRATION_67)
    return db


def _review(db: sqlite3.Connection, **overrides: object) -> None:
    values = {
        "link_review_id": LINK, "session_id": S, "census_id": CENSUS,
        "candidate_id": CANDIDATE, "source_run_id": R,
        "source_window_fingerprint": W, "census_fingerprint": CENSUS_FINGERPRINT,
        "manifest_fingerprint": MANIFEST,
        "expected_publication_fingerprint": EXPECTED_PUBLICATION,
        "observed_set_fingerprint": OBSERVED_SET,
        "selected_evidence_fingerprint": SELECTED_EVIDENCE,
        "review_receipt_id": "d" * 64, "review_fingerprint": "e" * 64,
        "decision": "linked_observed_checks", "selected_count": 1,
        "idempotency_key_digest": "f" * 64, "command_fingerprint": "1" * 64,
        "created_at": STAMP, "schema_version": "claim-grounding-link-reviewed-decision-v1",
        "policy_version": "native-reviewed-claim-link-coverage-v1",
        "metadata_persisted": 1, "candidate_prose_persisted": 0,
        "proposal_only": 1, "measured": 0, "metric_authority_established": 0,
    }
    values.update(overrides)
    db.execute(
        """INSERT INTO claim_grounding_link_reviews(
        link_review_id,session_id,census_id,candidate_id,source_run_id,
        source_window_fingerprint,census_fingerprint,manifest_fingerprint,
        expected_publication_fingerprint,observed_set_fingerprint,
        selected_evidence_fingerprint,review_receipt_id,review_fingerprint,
        decision,selected_count,idempotency_key_digest,command_fingerprint,created_at,
        schema_version,policy_version,metadata_persisted,candidate_prose_persisted,
        proposal_only,measured,metric_authority_established
        ) VALUES(:link_review_id,:session_id,:census_id,:candidate_id,:source_run_id,
        :source_window_fingerprint,:census_fingerprint,:manifest_fingerprint,
        :expected_publication_fingerprint,:observed_set_fingerprint,
        :selected_evidence_fingerprint,:review_receipt_id,:review_fingerprint,
        :decision,:selected_count,:idempotency_key_digest,:command_fingerprint,:created_at,
        :schema_version,:policy_version,:metadata_persisted,:candidate_prose_persisted,
        :proposal_only,:measured,:metric_authority_established)""",
        values,
    )


def _reference(db: sqlite3.Connection, **overrides: object) -> None:
    values = {
        "link_review_id": LINK, "ordinal": 0, "source_reference_id": "2" * 64,
        "observed_sequence": 1, "provider": "synthetic", "check_kind": "test",
        "observed_outcome": "passed", "provider_execution_status": "completed",
        "exit_code": 0, "source_completion_schema_version": "observed-check-completion-v1",
        "outcome_interpreter_version": "pytest-exit-status-v1",
        "classifier_version": "local-command-rules-v1",
        "normalizer_version": "strict-shell-free-v2", "rule_id": "test.pytest",
        "local_only": 1, "content_persistence_allowed": 0,
    }
    values.update(overrides)
    db.execute(
        """INSERT INTO claim_grounding_link_review_selected_references(
        link_review_id,ordinal,source_reference_id,observed_sequence,provider,check_kind,
        observed_outcome,provider_execution_status,exit_code,source_completion_schema_version,
        outcome_interpreter_version,classifier_version,normalizer_version,rule_id,
        local_only,content_persistence_allowed
        ) VALUES(:link_review_id,:ordinal,:source_reference_id,:observed_sequence,:provider,
        :check_kind,:observed_outcome,:provider_execution_status,:exit_code,
        :source_completion_schema_version,:outcome_interpreter_version,:classifier_version,
        :normalizer_version,:rule_id,:local_only,:content_persistence_allowed)""",
        values,
    )


def _seal_link(db: sqlite3.Connection, **overrides: object) -> None:
    values = {
        "link_review_id": LINK, "selected_count": 1, "census_id": CENSUS,
        "candidate_id": CANDIDATE, "census_fingerprint": CENSUS_FINGERPRINT,
        "manifest_fingerprint": MANIFEST,
        "expected_publication_fingerprint": EXPECTED_PUBLICATION,
        "observed_set_fingerprint": OBSERVED_SET,
        "selected_evidence_fingerprint": SELECTED_EVIDENCE,
        "issuance_seal": "3" * 64, "sealed_at": STAMP,
    }
    values.update(overrides)
    db.execute(
        """INSERT INTO claim_grounding_link_review_seals(
        link_review_id,selected_count,census_id,candidate_id,census_fingerprint,
        manifest_fingerprint,expected_publication_fingerprint,observed_set_fingerprint,
        selected_evidence_fingerprint,issuance_seal,sealed_at
        ) VALUES(:link_review_id,:selected_count,:census_id,:candidate_id,:census_fingerprint,
        :manifest_fingerprint,:expected_publication_fingerprint,:observed_set_fingerprint,
        :selected_evidence_fingerprint,:issuance_seal,:sealed_at)""",
        values,
    )


def test_m67_preserves_a_sealed_m66_parent_and_seals_exact_selected_provenance() -> None:
    db = _m67_db()
    _review(db); _reference(db); _seal_link(db)
    assert db.execute("SELECT candidate_count FROM claim_grounding_reviewed_censuses WHERE census_id=?", (CENSUS,)).fetchone()[0] == 1
    assert db.execute("SELECT selected_count FROM claim_grounding_link_review_seals WHERE link_review_id=?", (LINK,)).fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        _reference(db, ordinal=1, source_reference_id="4" * 64)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE claim_grounding_link_reviews SET decision='unresolved'")


def test_m67_rejects_insert_or_replace_for_every_immutable_history_table() -> None:
    db = _m67_db(); _review(db); _reference(db); _seal_link(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT OR REPLACE INTO claim_grounding_link_reviews "
                   "SELECT * FROM claim_grounding_link_reviews")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT OR REPLACE INTO claim_grounding_link_review_selected_references "
                   "SELECT * FROM claim_grounding_link_review_selected_references")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT OR REPLACE INTO claim_grounding_link_review_seals "
                   "SELECT * FROM claim_grounding_link_review_seals")
    assert db.execute("SELECT count(*) FROM claim_grounding_link_reviews").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM claim_grounding_link_review_selected_references").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM claim_grounding_link_review_seals").fetchone()[0] == 1


def test_m67_rejects_wrong_parent_decision_count_provenance_and_seal_bindings() -> None:
    db = _m67_db()
    with pytest.raises(sqlite3.IntegrityError): _review(db, candidate_id="9" * 64)
    with pytest.raises(sqlite3.IntegrityError): _review(db, decision="reviewed_no_support", selected_count=1)
    with pytest.raises(sqlite3.IntegrityError): _review(db, created_at=("x" * 26) + "+00:00")
    with pytest.raises(sqlite3.IntegrityError): _review(db, created_at="2026-02-30T00:00:00.000000+00:00")
    with pytest.raises(sqlite3.IntegrityError): _review(db, created_at="2026-01-00T00:00:00.000000+00:00")
    with pytest.raises(sqlite3.IntegrityError): _review(db, created_at="2026-01-99T00:00:00.000000+00:00")
    with pytest.raises(sqlite3.IntegrityError): _review(db, created_at="0000-01-01T00:00:00.000000+00:00")
    _review(db)
    with pytest.raises(sqlite3.IntegrityError): _reference(db, observed_outcome="passed", exit_code=1)
    with pytest.raises(sqlite3.IntegrityError): _reference(db, provider="unknown")
    _reference(db)
    with pytest.raises(sqlite3.IntegrityError): _seal_link(db, selected_count=0)
    with pytest.raises(sqlite3.IntegrityError): _seal_link(db, manifest_fingerprint="9" * 64)
    with pytest.raises(sqlite3.IntegrityError): _seal_link(db, sealed_at="2026-13-01T00:00:00.000000+00:00")
    with pytest.raises(sqlite3.IntegrityError): _review(db, link_review_id=("a" * 64) + "\x00suffix")
    leap_db = _m67_db()
    _review(leap_db, created_at="2024-02-29T23:59:59.999999+00:00")
    _reference(leap_db)
    _seal_link(leap_db, sealed_at="2024-02-29T23:59:59.999999+00:00")


def test_m67_allows_only_session_privacy_cascade_deletion() -> None:
    db = _m67_db(); _review(db); _reference(db); _seal_link(db)
    for table in (
        "claim_grounding_link_review_selected_references",
        "claim_grounding_link_review_seals", "claim_grounding_link_reviews",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(f"DELETE FROM {table}")
    db.execute("DELETE FROM sessions WHERE session_id=?", (S,))
    for table in (
        "claim_grounding_link_review_selected_references",
        "claim_grounding_link_review_seals", "claim_grounding_link_reviews",
    ):
        assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
