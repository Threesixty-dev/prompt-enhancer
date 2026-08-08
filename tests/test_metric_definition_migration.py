from __future__ import annotations

import hashlib
import sqlite3

from prompt_enhancer.application.analysis import TASK_METRIC_ENGINE_VERSION
from prompt_enhancer.database import (
    SCHEMA_VERSION,
    Database,
    _MIGRATION_1,
)
from prompt_enhancer.infrastructure.sqlite.migrations import MIGRATION_2
from prompt_enhancer.metrics import METRIC_ENGINE_VERSION


def test_v2_database_keeps_v1_metric_provenance_when_seeding_v2(tmp_path) -> None:
    path = tmp_path / "metrics.sqlite3"
    applied_at = "2026-01-01T00:00:00+00:00"
    old_checksum = "0" * 64
    old_definitions = (
        (
            "workflow.event_count",
            1,
            "workflow",
            "Legacy event count",
            "Synthetic v1 definition retained for migration coverage.",
            "count",
            "deterministic",
            "deterministic-1",
            old_checksum,
        ),
        (
            "task.workflow.session_count",
            1,
            "workflow",
            "Legacy task session count",
            "Synthetic v1 task definition retained for migration coverage.",
            "count",
            "deterministic",
            "task-deterministic-1",
            old_checksum,
        ),
    )

    with sqlite3.connect(path) as connection:
        connection.executescript(_MIGRATION_1)
        connection.executescript(MIGRATION_2)
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        for version, script in ((1, _MIGRATION_1), (2, MIGRATION_2)):
            connection.execute(
                """
                INSERT INTO schema_migrations(version, checksum, applied_at)
                VALUES (?, ?, ?)
                """,
                (version, hashlib.sha256(script.encode("utf-8")).hexdigest(), applied_at),
            )
        connection.executemany(
            """
            INSERT INTO metric_definitions(
                key, version, dimension, display_name, description, unit,
                source, algorithm_version, definition_checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            old_definitions,
        )
        connection.execute("PRAGMA user_version = 2")
        connection.commit()

    database = Database(path)
    database.initialize()
    definitions = {
        (item["key"], item["version"]): item
        for item in database.list_metric_definitions()
    }

    assert database.summary()["schema_version"] == SCHEMA_VERSION == 5
    assert definitions[("workflow.event_count", 1)]["algorithm_version"] == (
        "deterministic-1"
    )
    assert definitions[("workflow.event_count", 1)]["definition_checksum"] == (
        old_checksum
    )
    assert definitions[("workflow.event_count", 2)]["algorithm_version"] == (
        METRIC_ENGINE_VERSION
    )
    assert definitions[("task.workflow.session_count", 1)][
        "algorithm_version"
    ] == "task-deterministic-1"
    assert definitions[("task.workflow.session_count", 2)][
        "algorithm_version"
    ] == TASK_METRIC_ENGINE_VERSION
