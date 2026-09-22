from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing

import pytest

from prompt_enhancer import database as database_module
from prompt_enhancer.database import Database, SCHEMA_VERSION, _MIGRATION_1
from prompt_enhancer.infrastructure.sqlite import migrations
from prompt_enhancer.infrastructure.sqlite.migrations import MIGRATION_66

S, OTHER_SESSION, R, OTHER_RUN, W = (
    "a" * 64,
    "b" * 64,
    "c" * 64,
    "d" * 64,
    "e" * 64,
)
CENSUS, MANIFEST, CENSUS_FINGERPRINT, EXPECTED_PUBLICATION = (
    "f" * 64,
    "1" * 64,
    "2" * 64,
    "3" * 64,
)
STAMP = "2026-01-01T00:00:00.000000+00:00"


def _db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("CREATE TABLE sessions(session_id TEXT PRIMARY KEY)")
    db.execute("CREATE TABLE session_model_ensemble_runs(run_id TEXT PRIMARY KEY,session_id TEXT REFERENCES sessions(session_id) ON DELETE CASCADE,input_fingerprint TEXT)")
    db.execute("INSERT INTO sessions VALUES(?)", (S,))
    db.execute("INSERT INTO sessions VALUES(?)", (OTHER_SESSION,))
    db.execute("INSERT INTO session_model_ensemble_runs VALUES(?,?,?)", (R,S,W))
    db.execute("INSERT INTO session_model_ensemble_runs VALUES(?,?,?)", (OTHER_RUN,OTHER_SESSION,"4" * 64))
    db.executescript(MIGRATION_66)
    return db


def _header_values(
    *,
    census_id: str = CENSUS,
    session_id: str = S,
    source_run_id: str = R,
    source_window_fingerprint: str = W,
) -> tuple[object, ...]:
    return (
        census_id, session_id, source_run_id, source_window_fingerprint, MANIFEST,
        "source-v1", "adapter-v1", "message-clause-coordinates-en-pl-v1", 1,
        CENSUS_FINGERPRINT, EXPECTED_PUBLICATION, "5" * 64, "6" * 64, 1,
        STAMP, "claim-grounding-census-v1",
        "native-reviewed-agent-claim-census-v1",
        "reviewed-agent-response-census-v1", 1, 0,
    )


def _header(db: sqlite3.Connection, **overrides: str) -> None:
    db.execute(
        """INSERT INTO claim_grounding_reviewed_censuses(
            census_id,session_id,source_run_id,source_window_fingerprint,
            manifest_fingerprint,source_schema_version,text_adapter_version,
            clause_algorithm,text_extraction_complete,census_fingerprint,
            expected_publication_fingerprint,idempotency_key_digest,
            command_fingerprint,candidate_count,created_at,schema_version,
            policy_version,issuer_version,local_only,content_persisted
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        _header_values(**overrides),
    )


def _classification(db: sqlite3.Connection, **overrides: object) -> None:
    values = {
        "census_id": CENSUS, "ordinal": 0, "candidate_id": "7" * 64,
        "message_id": "8" * 64, "message_sequence": 1, "clause_index": 0,
        "classification": "material_claim", "exclusion_reason": None,
    }
    values.update(overrides)
    db.execute(
        """INSERT INTO claim_grounding_reviewed_census_classifications(
            census_id,ordinal,candidate_id,message_id,message_sequence,clause_index,
            classification,exclusion_reason
        ) VALUES(:census_id,:ordinal,:candidate_id,:message_id,:message_sequence,
                 :clause_index,:classification,:exclusion_reason)""",
        values,
    )


def _seal(db: sqlite3.Connection, **overrides: object) -> None:
    values = {
        "census_id": CENSUS, "candidate_count": 1,
        "manifest_fingerprint": MANIFEST, "census_fingerprint": CENSUS_FINGERPRINT,
        "expected_publication_fingerprint": EXPECTED_PUBLICATION,
        "issuance_seal": "9" * 64, "sealed_at": STAMP,
    }
    values.update(overrides)
    db.execute(
        """INSERT INTO claim_grounding_reviewed_census_seals(
            census_id,candidate_count,manifest_fingerprint,census_fingerprint,
            expected_publication_fingerprint,issuance_seal,sealed_at
        ) VALUES(:census_id,:candidate_count,:manifest_fingerprint,:census_fingerprint,
                 :expected_publication_fingerprint,:issuance_seal,:sealed_at)""",
        values,
    )


def test_migration66_creates_content_free_sealed_sidecar_and_guards_source() -> None:
    db = _db(); _header(db)
    _classification(db)
    _seal(db)
    with pytest.raises(sqlite3.IntegrityError):
        _classification(db, ordinal=1, candidate_id="a" * 64, message_id="b" * 64)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE claim_grounding_reviewed_censuses SET candidate_count=2")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE claim_grounding_reviewed_census_seals SET candidate_count=2")


def test_migration66_rejects_wrong_source_closed_enums_and_incomplete_seal() -> None:
    db = _db()
    with pytest.raises(sqlite3.IntegrityError):
        _header(db, session_id=OTHER_SESSION)
    with pytest.raises(sqlite3.IntegrityError):
        _header(db, source_window_fingerprint="9" * 64)
    _header(db)
    with pytest.raises(sqlite3.IntegrityError):
        _classification(db, classification="unclassified")
    with pytest.raises(sqlite3.IntegrityError):
        _classification(db, exclusion_reason="non_assertive_status_or_qualification")
    with pytest.raises(sqlite3.IntegrityError):
        _classification(db, classification="excluded")
    with pytest.raises(sqlite3.IntegrityError):
        _classification(db, clause_index=128)
    _classification(db)
    with pytest.raises(sqlite3.IntegrityError):
        _seal(db, candidate_count=2)
    with pytest.raises(sqlite3.IntegrityError):
        _seal(db, expected_publication_fingerprint="a" * 64)


def test_migration66_allows_only_session_privacy_cascade_deletion() -> None:
    db = _db(); _header(db); _classification(db); _seal(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM claim_grounding_reviewed_census_classifications")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM claim_grounding_reviewed_census_seals")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM claim_grounding_reviewed_censuses")
    db.execute("DELETE FROM sessions WHERE session_id=?", (S,))
    assert db.execute("SELECT count(*) FROM claim_grounding_reviewed_censuses").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM claim_grounding_reviewed_census_classifications").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM claim_grounding_reviewed_census_seals").fetchone()[0] == 0


def test_fresh_database_upgrades_synthetic_v66_to_migration67_preserves_sealed_census(tmp_path) -> None:
    path = tmp_path / "synthetic.sqlite3"
    pre_rebuild_scripts = (_MIGRATION_1,) + tuple(
        getattr(migrations, f"MIGRATION_{version}") for version in range(2, 63)
    )
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        for script in pre_rebuild_scripts:
            connection.executescript(script)
        connection.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO schema_migrations VALUES(?,?,?)",
            [(version, hashlib.sha256(script.encode()).hexdigest(), STAMP) for version, script in enumerate(pre_rebuild_scripts, 1)],
        )
        connection.commit()
        for version in (63, 64):
            script = getattr(migrations, f"MIGRATION_{version}")
            getattr(database_module, f"_apply_migration_{version}_rebuild")(connection, version=version, script=script, checksum=hashlib.sha256(script.encode()).hexdigest(), applied_at=STAMP)
        connection.executescript(migrations.MIGRATION_65)
        connection.execute("INSERT INTO schema_migrations VALUES(?,?,?)", (65, hashlib.sha256(migrations.MIGRATION_65.encode()).hexdigest(), STAMP))
        connection.execute("INSERT INTO installations VALUES(?,?,?)", ("7" * 64, "synthetic", STAMP))
        connection.execute("INSERT INTO projects(project_id,installation_id,provider,created_at) VALUES(?,?,?,?)", ("8" * 64, "7" * 64, "synthetic", STAMP))
        connection.execute("INSERT INTO sessions(session_id,installation_id,project_id,provider,provider_version,adapter_version,source_schema_version,started_at,terminal_state,events_complete,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (S, "7" * 64, "8" * 64, "synthetic", "example-v1", "example-v1", "example-v1", STAMP, "completed", 1, STAMP, STAMP))
        connection.execute(
            """INSERT INTO session_model_ensemble_runs(
                run_id,session_id,request_fingerprint,input_fingerprint,provider,
                provider_version,adapter_version,source_schema_version,content_schema_version,
                redactor_version,consent_policy_version,plan_version,plan_fingerprint,
                source_window_fingerprint,source_coverage_state,chunk_count,model_count,
                metric_count,created_at,completed_at,local_only,content_persisted,
                calibration_state,product_metric_eligible
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (R, S, "9" * 64, W, "codex", "example-v1", "adapter-v1", "source-v1",
             "content-v1", "redactor-v1", "explicit-local-shadow-ensemble-v1",
             "local-shadow-ensemble-v1", "a" * 64, W, "complete_window", 1, 10, 1,
             STAMP, STAMP, 1, 0, "not_assessed", 0),
        )
        connection.executescript(migrations.MIGRATION_66)
        connection.execute("INSERT INTO schema_migrations VALUES(?,?,?)", (66, hashlib.sha256(migrations.MIGRATION_66.encode()).hexdigest(), STAMP))
        _header(connection); _classification(connection); _seal(connection)
        connection.execute("PRAGMA user_version=66")
        connection.commit()
    database = Database(path)
    database.initialize()
    with database._connection(readonly=True) as connection:
        assert SCHEMA_VERSION >= 67
        assert connection.execute("SELECT session_id FROM sessions WHERE session_id=?", (S,)).fetchone() is not None
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='claim_grounding_reviewed_censuses'").fetchone() is not None
        assert connection.execute("SELECT version FROM schema_migrations WHERE version=66").fetchone() is not None
        assert connection.execute("SELECT candidate_count FROM claim_grounding_reviewed_censuses WHERE census_id=?", (CENSUS,)).fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM claim_grounding_reviewed_census_classifications WHERE census_id=?", (CENSUS,)).fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM claim_grounding_reviewed_census_seals WHERE census_id=?", (CENSUS,)).fetchone()[0] == 1
        assert connection.execute("SELECT checksum FROM schema_migrations WHERE version=67").fetchone()[0] == hashlib.sha256(migrations.MIGRATION_67.encode()).hexdigest()
