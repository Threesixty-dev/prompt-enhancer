"""Synthetic M65 checks for content-free observed-check provenance."""

from __future__ import annotations

import hashlib
import sqlite3

import pytest

from prompt_enhancer.application.analysis.requirement_verification_persistence import (
    ObservedCheckAuthorityProvenance,
)
from prompt_enhancer.database import Database, SCHEMA_VERSION, _apply_migration_atomically
from prompt_enhancer.infrastructure.sqlite import migrations

from test_requirement_verification_evidence_persistence import (
    _objective_command,
    _reviewed_setup,
    _service,
)


_TABLE = "requirement_verification_observed_check_provenance"
_TRIGGERS = (
    "requirement_verification_observed_check_provenance_insert_guard",
    "requirement_verification_observed_check_provenance_no_update",
    "requirement_verification_observed_check_provenance_privacy_delete_only",
)


def _provenance_payload() -> dict[str, object]:
    identifier = "a" * 64
    return {
        "authority_record_id": identifier, "session_id": identifier,
        "opportunity_set_fingerprint": identifier, "opportunity_id": identifier,
        "requirement_id": identifier, "source_run_id": identifier,
        "source_window_fingerprint": identifier,
        "requirement_plan_confirmation_id": identifier,
        "requirement_plan_proposal_id": identifier,
        "candidate_manifest_fingerprint": identifier,
        "source_reference_id": identifier,
        "coverage_review_reference_id": identifier,
        "observed_sequence": 1, "observed_outcome": "passed", "exit_code": 0,
        "source_completion_schema_version": "observed-check-completion-v1",
        "outcome_interpreter_version": "pytest-exit-status-v1",
        "classifier_version": "local-command-rules-v1",
        "normalizer_version": "strict-shell-free-v2", "rule_id": "test.pytest",
        "coverage_review_version": "native-full-criterion-coverage-v1",
        "full_criterion_coverage_acknowledged": True,
        "provenance_fingerprint": identifier,
    }


@pytest.mark.parametrize("field,value", (("exit_code", True), ("exit_code", 0.0), ("observed_sequence", False), ("observed_sequence", 1.0)))
def test_observed_provenance_rejects_coerced_boolean_and_float_numeric_fields(
    field: str, value: object,
) -> None:
    payload = _provenance_payload()
    payload[field] = value
    with pytest.raises(ValueError, match="numeric provenance"):
        ObservedCheckAuthorityProvenance.model_validate(payload)


def _to_v64(path) -> None:  # type: ignore[no-untyped-def]
    """Restore a synthetic v64 fixture by removing only later migrations."""
    Database(path).initialize()
    with sqlite3.connect(path) as connection:
        # M66 is now registered after M65.  Remove its isolated sidecar before
        # rewinding the synthetic fixture ledger, so the fixture remains a
        # genuine complete v64 history instead of an impossible mixed schema.
        connection.execute("DROP TABLE claim_grounding_reviewed_census_seals")
        connection.execute("DROP TABLE claim_grounding_reviewed_census_classifications")
        connection.execute("DROP TABLE claim_grounding_reviewed_censuses")
        for trigger in _TRIGGERS:
            connection.execute(f"DROP TRIGGER {trigger}")  # noqa: S608
        connection.execute(f"DROP TABLE {_TABLE}")  # noqa: S608
        connection.execute("DELETE FROM schema_migrations WHERE version IN (65,66)")
        connection.execute("PRAGMA user_version=64")


def test_m65_upgrades_a_clean_v64_database_with_content_free_append_only_sidecar(
    tmp_path,
) -> None:
    path = tmp_path / "synthetic-v64.sqlite3"
    _to_v64(path)

    Database(path).initialize()

    with sqlite3.connect(path) as connection:
        assert SCHEMA_VERSION == 66
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 66
        assert connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version=65"
        ).fetchone()[0] == hashlib.sha256(migrations.MIGRATION_65.encode()).hexdigest()
        columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({_TABLE})")  # noqa: S608
        }
        assert not columns & {"prompt", "text", "command", "output", "path"}
        assert {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' "
                "AND name LIKE 'requirement_verification_observed_check_provenance_%'"
            )
        } == set(_TRIGGERS)
        assert connection.execute(f"SELECT COUNT(*) FROM {_TABLE}").fetchone()[0] == 0  # noqa: S608
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_failed_m65_rolls_back_table_ledger_and_user_version_together(tmp_path) -> None:
    path = tmp_path / "synthetic-broken-v64.sqlite3"
    _to_v64(path)
    broken = migrations.MIGRATION_65.replace(
        "\nCOMMIT;\n", "\nSELECT synthetic_missing_m65_function();\nCOMMIT;\n"
    )

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.OperationalError):
            _apply_migration_atomically(
                connection,
                version=65,
                script=broken,
                checksum=hashlib.sha256(broken.encode()).hexdigest(),
                applied_at="2059-01-02T03:04:05.000000+00:00",
            )

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 64
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 64
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (_TABLE,)
        ).fetchone() is None


def test_m65_preserves_populated_v64_verification_authority_and_seals(tmp_path) -> None:
    """M65 adds no synthetic provenance to the frozen legacy authority chain."""
    database, session_id, _run, _confirmed = _reviewed_setup(tmp_path)
    service = _service(database)
    issued, _ = service.issue_current_opportunities(session_id)
    service.append_objective_result(
        session_id=session_id,
        command=_objective_command(issued, 0),
        idempotency_key="synthetic-m65-populated-legacy-authority-0001",
    )
    path = database.path
    with sqlite3.connect(path) as connection:
        before_records = connection.execute(
            "SELECT * FROM requirement_verification_authority_records"
        ).fetchall()
        before_refs = connection.execute(
            "SELECT * FROM requirement_verification_result_receipt_refs"
        ).fetchall()
        before_seals = connection.execute(
            "SELECT * FROM requirement_verification_authority_record_seals"
        ).fetchall()
        before_ledger = connection.execute(
            "SELECT version, checksum, applied_at FROM schema_migrations "
            "WHERE version <= 64 ORDER BY version"
        ).fetchall()

    _to_v64(path)
    Database(path).initialize()

    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT * FROM requirement_verification_authority_records"
        ).fetchall() == before_records
        assert connection.execute(
            "SELECT * FROM requirement_verification_result_receipt_refs"
        ).fetchall() == before_refs
        assert connection.execute(
            "SELECT * FROM requirement_verification_authority_record_seals"
        ).fetchall() == before_seals
        assert connection.execute(
            "SELECT version, checksum, applied_at FROM schema_migrations "
            "WHERE version <= 64 ORDER BY version"
        ).fetchall() == before_ledger
        assert connection.execute(f"SELECT COUNT(*) FROM {_TABLE}").fetchone()[0] == 0  # noqa: S608
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
