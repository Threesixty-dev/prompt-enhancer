"""Synthetic M63 migration checks for guided local requirement-plan authoring."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

import pytest

import prompt_enhancer.database as database_module
from prompt_enhancer.database import Database, SCHEMA_VERSION
from prompt_enhancer.infrastructure.sqlite import migrations

from test_requirement_plan_evidence_persistence import _confirm, _import, _setup


PLAN_TABLES = (
    "requirement_plan_evidence_proposals",
    "requirement_plan_evidence_requirements",
    "requirement_plan_evidence_excluded_user_clauses",
    "requirement_plan_evidence_plans",
    "requirement_plan_evidence_links",
    "requirement_plan_evidence_proposal_seals",
    "requirement_plan_evidence_decisions",
    "requirement_plan_evidence_decision_authority_m56",
    "session_model_ensemble_requirement_plan_bindings",
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
ALL_TABLES = PLAN_TABLES + ACTION_TABLES
REBUILT_TABLES = (
    "requirement_plan_evidence_proposals",
    "requirement_plan_evidence_proposal_seals",
    "requirement_action_evidence_proposals",
    "requirement_action_evidence_proposal_seals",
)
ATTACHED_OBJECTS = (
    "requirement_plan_evidence_proposals_session_idx",
    "requirement_plan_evidence_proposal_source_exact",
    "requirement_plan_evidence_proposals_no_update",
    "requirement_plan_evidence_proposals_privacy_delete_only",
    "requirement_plan_evidence_proposal_seals_no_update",
    "requirement_plan_evidence_proposal_seals_privacy_delete_only",
    "requirement_plan_evidence_proposal_seal_complete",
    "requirement_action_evidence_proposals_session_idx",
    "requirement_action_evidence_proposal_source_exact",
    "requirement_action_evidence_proposals_no_update",
    "requirement_action_evidence_proposal_seals_no_update",
    "requirement_action_evidence_proposals_privacy_delete_only",
    "requirement_action_evidence_proposal_seals_privacy_delete_only",
    "requirement_action_evidence_proposal_seal_complete",
)
_M65_TABLE = "requirement_verification_observed_check_provenance"
_M65_TRIGGERS = (
    "requirement_verification_observed_check_provenance_insert_guard",
    "requirement_verification_observed_check_provenance_no_update",
    "requirement_verification_observed_check_provenance_privacy_delete_only",
)
NOW = "2055-01-02T03:04:05.000000+00:00"


def _create_table_sql(script: str, table: str) -> str:
    start = script.index(f"CREATE TABLE {table} (")
    end = script.index(") STRICT;", start) + len(") STRICT;")
    return script[start:end]


def _normalize_sql(sql: str) -> str:
    collapsed = re.sub(r"\s+", " ", sql).strip().lower()
    return re.sub(r"\s*([(),])\s*", r"\1", collapsed)


def _expected_guided_table_sql(old_sql: str) -> str:
    """Model M63 as the two producer-check edits, with all other DDL fixed."""

    normalized = _normalize_sql(old_sql)
    normalized = normalized.replace(
        "check(producer_kind='local_coding_agent')",
        "check(producer_kind in('local_coding_agent','local_review_ui'))",
    )
    normalized = normalized.replace(
        "check(producer_authority='untrusted_provenance_claim_commitment')",
        "check((producer_kind='local_coding_agent' and producer_authority='untrusted_provenance_claim_commitment')or(producer_kind='local_review_ui' and producer_authority='untrusted_local_authoring_commitment'))",
    )
    return normalized


def _attached_rebuild_objects(connection: sqlite3.Connection) -> tuple[sqlite3.Row, ...]:
    placeholders = ",".join("?" for _ in REBUILT_TABLES)
    return tuple(
        connection.execute(
            "SELECT type,name,sql FROM sqlite_master "
            f"WHERE type IN ('index','trigger') AND sql IS NOT NULL AND tbl_name IN ({placeholders}) "
            "ORDER BY type,name",
            REBUILT_TABLES,
        ).fetchall()
    )


def _remove_m65_sidecar(connection: sqlite3.Connection) -> None:
    """Restore the synthetic ledger to v62 before replaying M63 onward."""
    for trigger in _M65_TRIGGERS:
        connection.execute(f'DROP TRIGGER "{trigger}"')  # noqa: S608
    connection.execute(f'DROP TABLE "{_M65_TABLE}"')  # noqa: S608


def _snapshot(path: Path) -> dict[str, object]:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        # PRAGMA foreign_keys is connection-local; normalize this read-only
        # snapshot so it can be compared across separately opened connections.
        connection.execute("PRAGMA foreign_keys=ON")
        rows: dict[str, tuple[tuple[object, ...], ...]] = {}
        foreign_keys: dict[str, tuple[tuple[object, ...], ...]] = {}
        for table in ALL_TABLES:
            values = connection.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608 - closed synthetic table names
            rows[table] = tuple(sorted((tuple(row) for row in values), key=repr))
            foreign_keys[table] = tuple(
                tuple(row)
                for row in connection.execute(f"PRAGMA foreign_key_list({table})")  # noqa: S608 - closed synthetic table names
            )
        objects = tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT type,name,sql FROM sqlite_master "
                f"WHERE name IN ({','.join('?' for _ in ATTACHED_OBJECTS)}) "
                "ORDER BY type,name",
                ATTACHED_OBJECTS,
            )
        )
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
                "SELECT version,checksum,applied_at FROM schema_migrations ORDER BY version"
            )
        )
        return {
            "rows": rows,
            "foreign_keys": foreign_keys,
            "objects": objects,
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


def _make_populated_v62(directory: Path) -> Path:
    """Create a real synthetic graph, then restore the exact pre-M63 table shape."""

    database, session_id, run, _repository, service = _setup(directory)
    path = database.path
    imported = _import(service, session_id, run, suffix="m63-preservation")
    _confirm(service, session_id, run, imported, suffix="m63-preservation")

    proposal_sql = _create_table_sql(migrations.MIGRATION_55, "requirement_plan_evidence_proposals")
    seal_sql = _create_table_sql(migrations.MIGRATION_55, "requirement_plan_evidence_proposal_seals")
    action_proposal_sql = _create_table_sql(migrations.MIGRATION_56, "requirement_action_evidence_proposals")
    action_seal_sql = _create_table_sql(migrations.MIGRATION_56, "requirement_action_evidence_proposal_seals")
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
            kind = str(row[0])
            identifier = str(row[1]).replace('"', '""')
            connection.execute(f'DROP {kind.upper()} "{identifier}"')  # noqa: S608 - closed synthetic object names
        for table, ddl in (
            ("requirement_plan_evidence_proposals", proposal_sql),
            ("requirement_plan_evidence_proposal_seals", seal_sql),
            ("requirement_action_evidence_proposals", action_proposal_sql),
            ("requirement_action_evidence_proposal_seals", action_seal_sql),
        ):
            legacy = f"{table}_m62_seed"
            connection.execute(f'ALTER TABLE "{table}" RENAME TO "{legacy}"')  # noqa: S608 - closed synthetic table names
            connection.execute(ddl)
            columns = [
                str(row[1])
                for row in connection.execute(f'PRAGMA table_info("{legacy}")')  # noqa: S608 - closed synthetic table name
            ]
            quoted = ",".join(f'"{column}"' for column in columns)
            connection.execute(
                f'INSERT INTO "{table}" ({quoted}) SELECT {quoted} FROM "{legacy}"'  # noqa: S608 - closed synthetic table names/columns
            )
            connection.execute(f'DROP TABLE "{legacy}"')  # noqa: S608 - closed synthetic table name
        for row in captured:
            connection.execute(str(row[2]))
        _remove_m65_sidecar(connection)
        connection.execute("DELETE FROM schema_migrations WHERE version>62")
        connection.execute("PRAGMA user_version=62")
        connection.commit()
        connection.execute(f"PRAGMA legacy_alter_table={original_legacy_alter_table}")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.commit()
    return path


def test_populated_v62_guided_upgrade_preserves_graph_authority_and_fk_wiring(
    tmp_path: Path,
) -> None:
    path = _make_populated_v62(tmp_path)
    before = _snapshot(path)
    assert before["user_version"] == 62
    assert before["foreign_keys_pragma"] == 1
    assert before["legacy_alter_table"] == 0
    with sqlite3.connect(path) as connection:
        old_table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='requirement_plan_evidence_proposals'"
        ).fetchone()[0]
        old_seal_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='requirement_plan_evidence_proposal_seals'"
        ).fetchone()[0]
        old_action_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='requirement_action_evidence_proposals'"
        ).fetchone()[0]
        old_action_seal_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='requirement_action_evidence_proposal_seals'"
        ).fetchone()[0]
    assert "CHECK(producer_kind='local_coding_agent')" in old_table_sql
    assert "CHECK(producer_kind='local_coding_agent')" in old_seal_sql
    assert "local_review_ui" not in old_table_sql
    assert "local_review_ui" not in old_action_sql
    assert "local_review_ui" not in old_action_seal_sql

    Database(path).initialize()
    after = _snapshot(path)
    assert SCHEMA_VERSION == 65
    assert after["user_version"] == 65
    assert after["foreign_keys_pragma"] == 1
    assert after["legacy_alter_table"] == 0
    assert after["ledger"][:-3] == before["ledger"]
    assert [row[0] for row in after["ledger"][-3:]] == [63, 64, 65]
    assert after["rows"] == before["rows"]
    assert after["foreign_keys"] == before["foreign_keys"]
    assert after["objects"] == before["objects"]
    with sqlite3.connect(path) as connection:
        new_proposal_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='requirement_plan_evidence_proposals'"
        ).fetchone()[0]
        new_seal_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='requirement_plan_evidence_proposal_seals'"
        ).fetchone()[0]
        new_action_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='requirement_action_evidence_proposals'"
        ).fetchone()[0]
        new_action_seal_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='requirement_action_evidence_proposal_seals'"
        ).fetchone()[0]
        assert _normalize_sql(new_proposal_sql) == _expected_guided_table_sql(old_table_sql)
        assert _normalize_sql(new_seal_sql) == _expected_guided_table_sql(old_seal_sql)
        assert _normalize_sql(new_action_sql) == _expected_guided_table_sql(old_action_sql)
        assert _normalize_sql(new_action_seal_sql) == _expected_guided_table_sql(old_action_seal_sql)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_failed_v63_guided_rebuild_rolls_back_rows_ledger_and_pragmas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _make_populated_v62(tmp_path)
    before = _snapshot(path)
    before_ledger = before["ledger"]
    original = database_module._execute_sql_statements

    def fail_after_rebuild(connection: sqlite3.Connection, script: str) -> None:
        original(connection, script)
        raise RuntimeError("synthetic failure after full rebuild")

    monkeypatch.setattr(database_module, "_execute_sql_statements", fail_after_rebuild)
    checksum = hashlib.sha256(migrations.MIGRATION_63.encode("utf-8")).hexdigest()
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA legacy_alter_table=ON")
        initial_legacy_alter_table = int(
            connection.execute("PRAGMA legacy_alter_table").fetchone()[0]
        )
        with pytest.raises(RuntimeError, match="synthetic failure after full rebuild"):
            database_module._apply_migration_63_rebuild(
                connection,
                version=63,
                script=migrations.MIGRATION_63,
                checksum=checksum,
                applied_at=NOW,
            )
        assert connection.in_transaction is False
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert (
            connection.execute("PRAGMA legacy_alter_table").fetchone()[0]
            == initial_legacy_alter_table
        )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 62
        assert tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT version,checksum,applied_at FROM schema_migrations ORDER BY version"
            )
        ) == before_ledger
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    after = _snapshot(path)
    assert after == before
