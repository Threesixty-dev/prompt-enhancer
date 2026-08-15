from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import sqlite3

import pytest

from prompt_enhancer.adapters.synthetic import SyntheticAdapter
from prompt_enhancer.application.analysis.model_ensemble import (
    ChunkMetricCommitteeReceipt,
    ModelEnsembleChunkReceipt,
    ModelExpertReceipt,
    ModelExpertRole,
    ModelExpertStatus,
    ModelMetricVote,
    ModelVoteState,
    SessionModelEnsembleMetricReceipt,
    SessionModelEnsembleReceipt,
    SourceCoverageState,
    ensemble_plan_fingerprint,
)
from prompt_enhancer.application.analysis.session_model_ensemble import (
    SessionModelEnsembleOutcome,
    SessionModelEnsembleRunRecord,
)
from prompt_enhancer.application.analysis.model_ensemble import (
    coaching_ensemble_metric_specs,
)
from prompt_enhancer.application.persistence import MetricValueState
from prompt_enhancer.database import SCHEMA_VERSION, Database, _MIGRATION_1
from prompt_enhancer.domain import Provider
from prompt_enhancer.ingestion import IngestionService
from prompt_enhancer.infrastructure.text_models.model_ensemble import (
    ensemble_expert_specs,
)
from prompt_enhancer.infrastructure.sqlite import migrations
from prompt_enhancer.privacy import Pseudonymizer


NOW = datetime(2040, 2, 3, 10, 0, tzinfo=UTC)
METRIC_KEY = "prompt.task_definition_coverage"


def _database_and_session(tmp_path) -> tuple[Database, str]:
    database = Database(tmp_path / "metrics.sqlite3")
    database.initialize()
    IngestionService(database, Pseudonymizer(bytes(range(32)))).ingest(
        SyntheticAdapter()
    )
    session_id = database.list_sessions(provider=Provider.SYNTHETIC, limit=1)[0][
        "session_id"
    ]
    with sqlite3.connect(database.path) as connection:
        connection.execute("UPDATE projects SET provider='codex'")
        connection.execute("UPDATE sessions SET provider='codex'")
        connection.commit()
    return database, session_id


def _run(session_id: str) -> SessionModelEnsembleRunRecord:
    identities = tuple(item.identity for item in ensemble_expert_specs())
    expert_receipts = tuple(
        ModelExpertReceipt(
            identity=identity,
            status=ModelExpertStatus.COMPLETED,
            device="cuda",
            inference_latency_ms=float(identity.ordinal + 1),
            peak_accelerator_memory_mb=100.0,
            process_rss_mb=200.0,
        )
        for identity in identities
    )
    selected_identity = {
        identity.model_key: identity for identity in identities
    }
    decision_keys = (
        "mdeberta_xnli",
        "multilingual_minilmv2_l6_nli",
        "multilingual_minilmv2_l12_nli",
        "qwen3_4b_rubric",
    )
    votes = tuple(
        ModelMetricVote(
            chunk_ordinal=0,
            metric_key=METRIC_KEY,
            model_key=key,
            role=selected_identity[key].role,
            state=ModelVoteState.PRESENT,
            raw_score=0.9,
            evidence_fragment_ids=("e" * 64,),
            reason_code="synthetic_present",
        )
        for key in decision_keys
    )
    receipt = SessionModelEnsembleReceipt(
        plan_fingerprint=ensemble_plan_fingerprint(
            identities,
            (coaching_ensemble_metric_specs()[0],),
        ),
        source_window_fingerprint="d" * 64,
        source_coverage_state=SourceCoverageState.COMPLETE_WINDOW,
        chunk_count=1,
        chunk_plan=(
            ModelEnsembleChunkReceipt(
                ordinal=0,
                chunk_fingerprint="c" * 64,
                source_message_count=2,
                fragment_count=2,
                character_count=120,
            ),
        ),
        chunks=(
            ChunkMetricCommitteeReceipt(
                chunk_ordinal=0,
                metric_key=METRIC_KEY,
                value_state=MetricValueState.KNOWN,
                numerator=1,
                denominator=1,
                rubric_vote=ModelVoteState.PRESENT,
                contributing_nli_votes=2,
                diagnostic_nli_votes=1,
                reason_code="model_committee_present",
            ),
        ),
        metrics=(
            SessionModelEnsembleMetricReceipt(
                metric_key=METRIC_KEY,
                value_state=MetricValueState.KNOWN,
                numerator=1,
                denominator=1,
                numeric_value=1.0,
                known_chunk_count=1,
                abstained_chunk_count=0,
                unsupported_chunk_count=0,
                failed_chunk_count=0,
                total_chunk_count=1,
                explanation_code="model_chunk_ratio",
            ),
        ),
        experts=expert_receipts,
        model_votes=tuple(sorted(votes, key=lambda item: item.model_key)),
        created_at=NOW,
        completed_at=NOW + timedelta(seconds=4),
    )
    return SessionModelEnsembleRunRecord(
        run_id="a" * 64,
        session_id=session_id,
        request_fingerprint="b" * 64,
        input_fingerprint="d" * 64,
        provider=Provider.CODEX,
        provider_version="codex-app-server-v1",
        adapter_version="codex-adapter-v1",
        source_schema_version="codex-source-v1",
        content_schema_version="codex-content-v1",
        redactor_version="deterministic-redactor-v1",
        receipt=receipt,
    )


def test_model_ensemble_graph_round_trips_and_contains_no_content_columns(tmp_path) -> None:
    database, session_id = _database_and_session(tmp_path)
    repository = database.model_ensemble_repository()
    run = _run(session_id)

    repository.save_completed(run)
    stored = repository.get(run.run_id)

    assert stored is not None
    assert stored.model_dump(mode="json") == run.model_dump(mode="json")
    assert repository.get_latest(session_id) == stored
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        tables = tuple(
            row[0]
            for row in connection.execute(
                """SELECT name FROM sqlite_master
                   WHERE type='table' AND name LIKE 'session_model_ensemble_%'"""
            )
        )
        columns = {
            row[1]
            for table in tables
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
    assert not any(
        fragment in column
        for column in columns
        for fragment in ("text", "prompt", "response", "output", "path")
    )


def test_model_ensemble_graph_is_immutable_sealed_and_privacy_deletable(tmp_path) -> None:
    database, session_id = _database_and_session(tmp_path)
    repository = database.model_ensemble_repository()
    run = _run(session_id)
    repository.save_completed(run)

    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE session_model_ensemble_metrics SET numeric_value=0 WHERE run_id=?",
                (run.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="sealed"):
            connection.execute(
                """INSERT INTO session_model_ensemble_vote_fragments
                   VALUES(?,?,?,?,?,?)""",
                (run.run_id, 0, METRIC_KEY, "qwen3_4b_rubric", 1, "f" * 64),
            )

    assert repository.delete_for_privacy(run.run_id) is True
    assert repository.get(run.run_id) is None
    with sqlite3.connect(database.path) as connection:
        counts = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "session_model_ensemble_runs",
                "session_model_ensemble_chunks",
                "session_model_ensemble_experts",
                "session_model_ensemble_votes",
                "session_model_ensemble_vote_fragments",
                "session_model_ensemble_chunk_metrics",
                "session_model_ensemble_metrics",
                "session_model_ensemble_seals",
            )
        )
    assert counts == (0,) * 8


def test_model_ensemble_migrations_have_zero_backfill(tmp_path) -> None:
    database, _ = _database_and_session(tmp_path)
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 29
        assert tuple(
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ) == tuple(range(1, 30))
        assert connection.execute(
            "SELECT COUNT(*) FROM session_model_ensemble_runs"
        ).fetchone()[0] == 0


def test_v28_watch_upgrade_preserves_the_original_message_window(tmp_path) -> None:
    path = tmp_path / "watch-v28.sqlite3"
    scripts = (_MIGRATION_1,) + tuple(
        getattr(migrations, f"MIGRATION_{version}")
        for version in range(2, 29)
    )
    checksums = tuple(
        hashlib.sha256(script.encode("utf-8")).hexdigest()
        for script in scripts
    )
    timestamp = NOW.isoformat(timespec="microseconds")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA trusted_schema=ON")
        for script in scripts:
            connection.executescript(script)
        connection.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO schema_migrations VALUES(?,?,?)",
            tuple(
                (version, checksum, timestamp)
                for version, checksum in enumerate(checksums, start=1)
            ),
        )
        connection.execute(
            "INSERT INTO installations VALUES(?,?,?)",
            ("1" * 64, "codex", timestamp),
        )
        connection.execute(
            "INSERT INTO projects(project_id,installation_id,provider,created_at) VALUES(?,?,?,?)",
            ("2" * 64, "1" * 64, "codex", timestamp),
        )
        connection.execute(
            """INSERT INTO sessions(
               session_id,installation_id,project_id,provider,provider_version,
               adapter_version,source_schema_version,started_at,ended_at,
               terminal_state,events_complete,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,'completed',1,?,?)""",
            (
                "3" * 64,
                "1" * 64,
                "2" * 64,
                "codex",
                "example-provider-v1",
                "example-adapter-v1",
                "example-schema-v1",
                timestamp,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """INSERT INTO session_model_ensemble_watches(
               watch_id,provider,project_id,session_id,state,generation,
               progress_completed,progress_total,next_check_at,created_at,updated_at
               ) VALUES(?,?,?,?,'queued',0,0,10,?,?,?)""",
            ("4" * 64, "codex", "2" * 64, "3" * 64, timestamp, timestamp, timestamp),
        )
        connection.execute("PRAGMA user_version=28")
        connection.commit()

    Database(path).initialize()

    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT version,checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 29
        assert tuple(row[1] for row in rows[:28]) == checksums
        assert rows[28][1] == hashlib.sha256(
            migrations.MIGRATION_29.encode("utf-8")
        ).hexdigest()
        assert connection.execute(
            "SELECT max_messages FROM session_model_ensemble_watches"
        ).fetchone()[0] == 100
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("populated", (False, True))
def test_v25_to_v26_preserves_prior_checksums_and_rows(tmp_path, populated: bool) -> None:
    path = tmp_path / f"{'populated' if populated else 'fresh'}-v25.sqlite3"
    scripts = (_MIGRATION_1,) + tuple(
        getattr(migrations, f"MIGRATION_{version}")
        for version in range(2, 26)
    )
    checksums = tuple(
        hashlib.sha256(script.encode("utf-8")).hexdigest()
        for script in scripts
    )
    timestamp = NOW.isoformat(timespec="microseconds")
    session_id = ""
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA trusted_schema=ON")
        for script in scripts:
            connection.executescript(script)
        connection.execute(
            """CREATE TABLE schema_migrations(
                   version INTEGER PRIMARY KEY,
                   checksum TEXT NOT NULL,
                   applied_at TEXT NOT NULL
               )"""
        )
        connection.executemany(
            "INSERT INTO schema_migrations VALUES(?,?,?)",
            tuple(
                (version, checksum, timestamp)
                for version, checksum in enumerate(checksums, start=1)
            ),
        )
        if populated:
            installation_id = "1" * 64
            project_id = "2" * 64
            session_id = "3" * 64
            connection.execute(
                "INSERT INTO installations VALUES(?,?,?)",
                (installation_id, "synthetic", timestamp),
            )
            connection.execute(
                """INSERT INTO projects(
                       project_id,installation_id,provider,created_at
                   ) VALUES(?,?,?,?)""",
                (project_id, installation_id, "synthetic", timestamp),
            )
            connection.execute(
                """INSERT INTO sessions(
                       session_id,installation_id,project_id,provider,
                       provider_version,adapter_version,source_schema_version,
                       started_at,ended_at,terminal_state,events_complete,
                       created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,'completed',1,?,?)""",
                (
                    session_id,
                    installation_id,
                    project_id,
                    "synthetic",
                    "synthetic-provider-v1",
                    "synthetic-adapter-v1",
                    "synthetic-schema-v1",
                    timestamp,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
        connection.execute("PRAGMA user_version=25")
        connection.commit()

    Database(path).initialize()

    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT version,checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 29
        assert tuple(row[0] for row in rows) == tuple(range(1, 30))
        assert tuple(row[1] for row in rows[:25]) == checksums
        assert rows[25][1] == hashlib.sha256(
            migrations.MIGRATION_26.encode("utf-8")
        ).hexdigest()
        assert rows[26][1] == hashlib.sha256(
            migrations.MIGRATION_27.encode("utf-8")
        ).hexdigest()
        assert rows[27][1] == hashlib.sha256(
            migrations.MIGRATION_28.encode("utf-8")
        ).hexdigest()
        assert rows[28][1] == hashlib.sha256(
            migrations.MIGRATION_29.encode("utf-8")
        ).hexdigest()
        assert connection.execute(
            "SELECT COUNT(*) FROM session_model_ensemble_runs"
        ).fetchone()[0] == 0
        if populated:
            assert connection.execute(
                """SELECT terminal_state,provider_activity_revision
                   FROM sessions WHERE session_id=?""",
                (session_id,),
            ).fetchone() == ("completed", None)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_continuous_watch_claim_progress_completion_and_disable(tmp_path) -> None:
    database, session_id = _database_and_session(tmp_path)
    run_repository = database.model_ensemble_repository()
    run = _run(session_id)
    run_repository.save_completed(run)
    project_id = database.list_sessions(provider=Provider.CODEX, limit=1)[0][
        "project_id"
    ]
    repository = database.model_ensemble_watch_repository()
    watch_id = "9" * 64

    enabled = repository.enable(
        watch_id=watch_id,
        provider=Provider.CODEX,
        project_id=project_id,
        session_id=session_id,
        max_messages=25,
        now=NOW,
    )
    assert enabled.state.value == "queued"
    assert enabled.max_messages == 25
    claimed = repository.claim_due(
        owner="8" * 64,
        now=NOW,
        lease_duration=timedelta(minutes=30),
    )
    assert claimed is not None
    running, lease = claimed
    assert running.state.value == "running"
    assert running.generation == 1
    running, lease = repository.heartbeat(
        lease,
        now=NOW + timedelta(seconds=10),
        lease_duration=timedelta(minutes=30),
        progress_completed=4,
    )
    assert running.progress_completed == 4

    completed = repository.complete(
        lease,
        now=NOW + timedelta(seconds=20),
        next_check_at=NOW + timedelta(seconds=80),
        outcome=SessionModelEnsembleOutcome(run=run, applied=True),
    )
    assert completed.state.value == "idle"
    assert completed.latest_run_id == run.run_id
    assert completed.latest_input_fingerprint == run.input_fingerprint
    assert completed.progress_completed == 10
    assert repository.get_active() == completed

    reconfigured = repository.enable(
        watch_id=watch_id,
        provider=Provider.CODEX,
        project_id=project_id,
        session_id=session_id,
        max_messages=50,
        now=NOW + timedelta(seconds=21),
    )
    assert reconfigured.state.value == "queued"
    assert reconfigured.max_messages == 50
    assert reconfigured.progress_completed == 0
    assert reconfigured.latest_run_id is None
    assert reconfigured.latest_input_fingerprint is None

    disabled = repository.disable(watch_id, now=NOW + timedelta(seconds=22))
    assert disabled.state.value == "disabled"
    assert repository.get_active() is None


def test_continuous_watch_replaces_another_active_session_atomically(tmp_path) -> None:
    database, session_id = _database_and_session(tmp_path)
    repository = database.model_ensemble_watch_repository()
    with sqlite3.connect(database.path) as connection:
        first = connection.execute(
            "SELECT project_id,installation_id FROM sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        second_session = "7" * 64
        connection.execute(
            """INSERT INTO sessions(
               session_id,installation_id,project_id,provider,provider_version,
               adapter_version,source_schema_version,started_at,ended_at,
               terminal_state,events_complete,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,'completed',1,?,?)""",
            (
                second_session,
                first[1],
                first[0],
                "codex",
                "codex-app-server-v1",
                "codex-adapter-v1",
                "codex-source-v1",
                NOW.isoformat(timespec="microseconds"),
                NOW.isoformat(timespec="microseconds"),
                NOW.isoformat(timespec="microseconds"),
                NOW.isoformat(timespec="microseconds"),
            ),
        )
        connection.commit()

    first_watch = repository.enable(
        watch_id="6" * 64,
        provider=Provider.CODEX,
        project_id=first[0],
        session_id=session_id,
        now=NOW,
    )
    second_watch = repository.enable(
        watch_id="5" * 64,
        provider=Provider.CODEX,
        project_id=first[0],
        session_id=second_session,
        now=NOW + timedelta(seconds=1),
    )

    assert repository.get(first_watch.watch_id).state.value == "disabled"
    assert repository.get_active() == second_watch
