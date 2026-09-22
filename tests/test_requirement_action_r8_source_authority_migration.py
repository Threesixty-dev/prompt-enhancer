"""Synthetic M62 upgrade coverage for reviewed action-source authority."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3

from prompt_enhancer.database import Database, SCHEMA_VERSION
from prompt_enhancer.infrastructure.sqlite import migrations


def _m56_action_source_trigger() -> str:
    source = migrations.MIGRATION_56
    start = source.index(
        "CREATE TRIGGER requirement_action_evidence_proposal_source_exact"
    )
    end = source.index("\n\nCREATE TRIGGER", start)
    return source[start:end]


def _m62_action_source_trigger() -> str:
    source = migrations.MIGRATION_62
    start = source.index(
        "CREATE TRIGGER requirement_action_evidence_proposal_source_exact"
    )
    end = source.index("\nCOMMIT;", start)
    return source[start:end]


def test_m62_upgrades_exact_v61_action_authority_trigger_without_rewriting_history(
    tmp_path: Path,
) -> None:
    """A synthetic v61 database receives only the R8 seal admission change."""

    path = tmp_path / "synthetic-requirement-action-v61.sqlite3"
    Database(path).initialize()
    with sqlite3.connect(path) as connection:
        before = tuple(
            connection.execute(
                "SELECT version, checksum FROM schema_migrations "
                "WHERE version <= 61 ORDER BY version"
            ).fetchall()
        )
        connection.execute(
            "DROP TRIGGER requirement_action_evidence_proposal_source_exact"
        )
        old_trigger = _m56_action_source_trigger()
        assert "metric_publication_v2_seals_r8" not in old_trigger
        connection.executescript(old_trigger)
        connection.execute("DELETE FROM schema_migrations WHERE version=62")
        connection.execute("PRAGMA user_version=61")
        connection.commit()

    Database(path).initialize()

    with sqlite3.connect(path) as connection:
        after = tuple(
            connection.execute(
                "SELECT version, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
        )
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
            ("requirement_action_evidence_proposal_source_exact",),
        ).fetchone()
        assert connection.execute("PRAGMA user_version").fetchone() == (
            SCHEMA_VERSION,
        )
        assert SCHEMA_VERSION == 62
        assert after[:61] == before
        assert after[61] == (
            62,
            hashlib.sha256(migrations.MIGRATION_62.encode("utf-8")).hexdigest(),
        )
        assert trigger is not None
        trigger_sql = str(trigger[0])
        for seal_table in (
            "session_model_ensemble_metric_publication_v2_seals_r6",
            "session_model_ensemble_metric_publication_v2_seals_r7",
            "session_model_ensemble_metric_publication_v2_seals_r8",
        ):
            assert seal_table in trigger_sql
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_m62_preserves_the_exact_stale_window_and_source_authority_guards() -> None:
    """M62 adds R8 admission without relaxing the exact source authority."""

    old = _m56_action_source_trigger()
    new = _m62_action_source_trigger()
    r8_admission = """      OR EXISTS(SELECT 1 FROM session_model_ensemble_metric_publication_v2_seals_r8
                WHERE run_id=run.run_id)
"""
    assert r8_admission in new
    assert "".join(new.replace(r8_admission, "").split()) == "".join(old.split())
