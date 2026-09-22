"""Synthetic v63-to-v64 action-evidence provenance migration checks."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import re
import sqlite3
from pathlib import Path

import pytest

import prompt_enhancer.database as database_module
from prompt_enhancer.database import Database
from prompt_enhancer.infrastructure.sqlite import migrations

from test_model_ensemble_r7_persistence import (
    _confirmed_action_setup,
    _r7_record,
    _reviewed_action_binding,
)


ACTION_TABLES = (
    "requirement_action_evidence_proposals",
    "requirement_action_evidence_requirements",
    "requirement_action_evidence_candidates",
    "requirement_action_evidence_links",
    "requirement_action_evidence_proposal_seals",
    "requirement_action_evidence_decisions",
    "session_model_ensemble_requirement_action_bindings",
)
REBUILT_TABLES = (
    "requirement_action_evidence_proposals",
    "requirement_action_evidence_proposal_seals",
)
ATTACHED_OBJECTS = (
    "requirement_action_evidence_proposals_session_idx",
    "requirement_action_evidence_proposal_source_exact",
    "requirement_action_evidence_proposal_seal_complete",
    "requirement_action_evidence_proposals_no_update",
    "requirement_action_evidence_proposal_seals_no_update",
    "requirement_action_evidence_proposals_privacy_delete_only",
    "requirement_action_evidence_proposal_seals_privacy_delete_only",
)
_M65_TABLE = "requirement_verification_observed_check_provenance"
_M65_TRIGGERS = (
    "requirement_verification_observed_check_provenance_insert_guard",
    "requirement_verification_observed_check_provenance_no_update",
    "requirement_verification_observed_check_provenance_privacy_delete_only",
)
NOW = datetime(2055, 1, 2, 3, 4, 5, tzinfo=UTC).isoformat(
    timespec="microseconds"
)


def _create_table_sql(script: str, table: str) -> str:
    start = script.index(f"CREATE TABLE {table} (")
    end = script.index(") STRICT;", start) + len(") STRICT;")
    return script[start:end]


def _normalize_sql(sql: str) -> str:
    collapsed = re.sub(r"\s+", " ", sql).strip().lower()
    return re.sub(r"\s*([(),])\s*", r"\1", collapsed)


def _expected_v64_table_sql(old_sql: str) -> str:
    normalized = _normalize_sql(old_sql)
    normalized = normalized.replace(
        "check(producer_kind='local_coding_agent')",
        "check(producer_kind in('local_coding_agent','local_review_ui'))",
    )
    return normalized.replace(
        "check(producer_authority='untrusted_provenance_claim_commitment')",
        "check((producer_kind='local_coding_agent' and producer_authority='untrusted_provenance_claim_commitment')or(producer_kind='local_review_ui' and producer_authority='untrusted_local_authoring_commitment'))",
    )


def _attached_rebuild_objects(
    connection: sqlite3.Connection,
) -> tuple[sqlite3.Row, ...]:
    placeholders = ",".join("?" for _ in REBUILT_TABLES)
    return tuple(
        connection.execute(
            "SELECT type,name,sql FROM sqlite_master "
            f"WHERE type IN ('index','trigger') AND sql IS NOT NULL "
            f"AND tbl_name IN ({placeholders}) ORDER BY type,name",
            REBUILT_TABLES,
        ).fetchall()
    )


def _remove_m65_sidecar(connection: sqlite3.Connection) -> None:
    """Restore the synthetic ledger to v63 before replaying later migrations."""
    for trigger in _M65_TRIGGERS:
        connection.execute(f'DROP TRIGGER "{trigger}"')  # noqa: S608
    connection.execute(f'DROP TABLE "{_M65_TABLE}"')  # noqa: S608


def _without_m65_objects(
    objects: tuple[tuple[object, ...], ...],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        item
        for item in objects
        if item[1] not in _M65_TRIGGERS
    )


def _snapshot(path: Path) -> dict[str, object]:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        rows = {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),  # noqa: S608 - synthetic table names
                    key=repr,
                )
            )
            for table in ACTION_TABLES
        }
        foreign_keys = {
            table: tuple(
                tuple(row)
                for row in connection.execute(f"PRAGMA foreign_key_list({table})")  # noqa: S608 - synthetic table names
            )
            for table in ACTION_TABLES
        }
        schema_objects = tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE type != 'table' AND sql IS NOT NULL ORDER BY type,name"
            )
        )
        ledger = tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT version,checksum,applied_at FROM schema_migrations "
                "ORDER BY version"
            )
        )
        return {
            "rows": rows,
            "foreign_keys": foreign_keys,
            "schema_objects": schema_objects,
            "ledger": ledger,
            "user_version": connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0],
            "foreign_keys_pragma": connection.execute(
                "PRAGMA foreign_keys"
            ).fetchone()[0],
            "legacy_alter_table": connection.execute(
                "PRAGMA legacy_alter_table"
            ).fetchone()[0],
        }


def _make_populated_v63(directory: Path) -> Path:
    """Populate the complete action graph, then restore the v63 table checks."""

    database, source, plan_snapshot, _repository, _proposal, _decision, snapshot = (
        _confirmed_action_setup(directory)
    )
    record = _r7_record(
        source.session_id,
        run_character="f",
        request_character="1",
        plan_snapshot=plan_snapshot,
        action_snapshot=snapshot,
        action_binding=_reviewed_action_binding(snapshot),
    )
    database.model_ensemble_repository().save_completed(record)
    path = database.path
    proposal_sql = _create_table_sql(
        migrations.MIGRATION_56, "requirement_action_evidence_proposals"
    )
    seal_sql = _create_table_sql(
        migrations.MIGRATION_56, "requirement_action_evidence_proposal_seals"
    )
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        original_legacy_alter_table = int(
            connection.execute("PRAGMA legacy_alter_table").fetchone()[0]
        )
        connection.execute("PRAGMA legacy_alter_table=ON")
        connection.execute("BEGIN IMMEDIATE")
        captured = _attached_rebuild_objects(connection)
        assert {str(row[1]) for row in captured} == set(ATTACHED_OBJECTS)
        for row in captured:
            identifier = str(row[1]).replace('"', '""')
            connection.execute(
                f'DROP {str(row[0]).upper()} "{identifier}"'  # noqa: S608 - synthetic object names
            )
        for table, ddl in (
            (REBUILT_TABLES[0], proposal_sql),
            (REBUILT_TABLES[1], seal_sql),
        ):
            legacy = f"{table}_v63_seed"
            connection.execute(
                f'ALTER TABLE "{table}" RENAME TO "{legacy}"'  # noqa: S608 - synthetic table name
            )
            connection.execute(ddl)
            columns = [
                str(row[1])
                for row in connection.execute(
                    f'PRAGMA table_info("{legacy}")'  # noqa: S608 - synthetic table name
                )
            ]
            quoted = ",".join(f'"{column}"' for column in columns)
            connection.execute(
                f'INSERT INTO "{table}" ({quoted}) SELECT {quoted} FROM "{legacy}"'  # noqa: S608 - synthetic table/columns
            )
            connection.execute(
                f'DROP TABLE "{legacy}"'  # noqa: S608 - synthetic table name
            )
        for row in captured:
            connection.execute(str(row[2]))
        _remove_m65_sidecar(connection)
        connection.execute("DELETE FROM schema_migrations WHERE version>=64")
        connection.execute("PRAGMA user_version=63")
        connection.commit()
        connection.execute(f"PRAGMA legacy_alter_table={original_legacy_alter_table}")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.commit()
    return path


def test_populated_v63_action_upgrade_preserves_graph_authority_and_fks(
    tmp_path: Path,
) -> None:
    path = _make_populated_v63(tmp_path)
    before = _snapshot(path)
    assert before["user_version"] == 63
    assert before["foreign_keys_pragma"] == 1
    assert before["legacy_alter_table"] == 0
    with sqlite3.connect(path) as connection:
        old_proposal_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (REBUILT_TABLES[0],),
        ).fetchone()[0]
        old_seal_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (REBUILT_TABLES[1],),
        ).fetchone()[0]

    Database(path).initialize()
    after = _snapshot(path)
    assert after["user_version"] == 65
    assert after["foreign_keys_pragma"] == 1
    assert after["legacy_alter_table"] == 0
    assert after["ledger"][:-2] == before["ledger"]
    assert [row[0] for row in after["ledger"][-2:]] == [64, 65]
    assert after["rows"] == before["rows"]
    assert after["foreign_keys"] == before["foreign_keys"]
    assert _without_m65_objects(after["schema_objects"]) == before["schema_objects"]
    with sqlite3.connect(path) as connection:
        new_proposal_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (REBUILT_TABLES[0],),
        ).fetchone()[0]
        new_seal_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (REBUILT_TABLES[1],),
        ).fetchone()[0]
        assert _normalize_sql(new_proposal_sql) == _expected_v64_table_sql(old_proposal_sql)
        assert _normalize_sql(new_seal_sql) == _expected_v64_table_sql(old_seal_sql)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_failed_v64_action_rebuild_rolls_back_rows_ledger_and_pragmas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _make_populated_v63(tmp_path)
    before = _snapshot(path)
    original = database_module._execute_sql_statements

    def fail_after_full_rebuild(connection: sqlite3.Connection, script: str) -> None:
        original(connection, script)
        raise RuntimeError("synthetic failure after full rebuild")

    monkeypatch.setattr(database_module, "_execute_sql_statements", fail_after_full_rebuild)
    checksum = hashlib.sha256(migrations.MIGRATION_64.encode("utf-8")).hexdigest()
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA legacy_alter_table=ON")
        initial_legacy_alter_table = int(
            connection.execute("PRAGMA legacy_alter_table").fetchone()[0]
        )
        with pytest.raises(RuntimeError, match="synthetic failure after full rebuild"):
            database_module._apply_migration_64_rebuild(
                connection,
                version=64,
                script=migrations.MIGRATION_64,
                checksum=checksum,
                applied_at=NOW,
            )
        assert connection.in_transaction is False
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA legacy_alter_table").fetchone()[0] == initial_legacy_alter_table
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 63
        assert tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT version,checksum,applied_at FROM schema_migrations ORDER BY version"
            )
        ) == before["ledger"]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    assert _snapshot(path) == before
