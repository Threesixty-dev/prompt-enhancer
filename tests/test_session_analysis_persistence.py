from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import sqlite3

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from prompt_enhancer.adapters.synthetic import SyntheticAdapter
from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.application.analysis.text_baselines import (
    DEFAULT_TEXT_METRIC_PACK_KEY,
    DEFAULT_TEXT_METRIC_PACK_VERSION,
    TEXT_METRIC_ALGORITHM_ID,
    TEXT_METRIC_ALGORITHM_VERSION,
    TEXT_METRIC_ENGINE_VERSION,
)
from prompt_enhancer.application.analysis.coaching_baselines import (
    COACHING_METRIC_ALGORITHM_ID,
    COACHING_METRIC_ALGORITHM_VERSION,
    COACHING_METRIC_ENGINE_VERSION,
    COACHING_METRIC_PACK_KEY,
    COACHING_METRIC_PACK_VERSION,
)
from prompt_enhancer.application.analysis.text_contracts import (
    TEXT_METRIC_SCHEMA_VERSION,
)
from prompt_enhancer.application.persistence import (
    AnalysisRunStatus,
    MetricValueState,
    SessionAnalysisEvidenceRecord,
    SessionAnalysisSignalRecord,
    SessionAnalysisResultRecord,
    SessionAnalysisRunDraft,
    SessionEvidenceOrigin,
    SessionMetricAggregation,
    SessionMetricApplicability,
    SessionMetricDirection,
    SessionMetricSignalStatus,
    TaskRevisionRecord,
)
from prompt_enhancer.database import (
    SCHEMA_VERSION,
    Database,
    DatabaseInvariantError,
    _MIGRATION_1,
)
from prompt_enhancer.config import AppSettings
from prompt_enhancer.domain import DataTier, MetricObservation, MetricSource, Provider
from prompt_enhancer.ingestion import IngestionService
from prompt_enhancer.privacy import Pseudonymizer
from prompt_enhancer.infrastructure.sqlite.migrations import (
    MIGRATION_2,
    MIGRATION_3,
    MIGRATION_4,
    MIGRATION_5,
    MIGRATION_6,
    MIGRATION_7,
)


NOW = datetime(2040, 1, 2, 10, 0, tzinfo=UTC)
EXAMPLE_TOKEN = "example_session_analysis_token_1234567890"
AGGREGATION_FILTER = {
    "analysis_profile_key": "standard_engineering",
    "analysis_profile_version": 1,
    "metric_pack_key": DEFAULT_TEXT_METRIC_PACK_KEY,
    "metric_pack_version": DEFAULT_TEXT_METRIC_PACK_VERSION,
}


def _create_v7_analysis_run(path) -> str:
    migrations = (
        (1, _MIGRATION_1),
        (2, MIGRATION_2),
        (3, MIGRATION_3),
        (4, MIGRATION_4),
        (5, MIGRATION_5),
        (6, MIGRATION_6),
        (7, MIGRATION_7),
    )
    installation_id, project_id, session_id, run_id = (
        "1" * 64,
        "2" * 64,
        "3" * 64,
        "4" * 64,
    )
    timestamp = NOW.isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for _, script in migrations:
            connection.executescript(script)
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO schema_migrations(version, checksum, applied_at)
            VALUES (?, ?, ?)
            """,
            tuple(
                (
                    version,
                    hashlib.sha256(script.encode("utf-8")).hexdigest(),
                    timestamp,
                )
                for version, script in migrations
            ),
        )
        connection.execute(
            "INSERT INTO installations(installation_id, provider, created_at) VALUES (?, ?, ?)",
            (installation_id, "synthetic", timestamp),
        )
        connection.execute(
            "INSERT INTO projects(project_id, installation_id, provider, created_at) VALUES (?, ?, ?, ?)",
            (project_id, installation_id, "synthetic", timestamp),
        )
        connection.execute(
            """
            INSERT INTO sessions(
                session_id, installation_id, project_id, provider,
                provider_version, adapter_version, source_schema_version,
                started_at, ended_at, terminal_state, events_complete,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
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
                "completed",
                1,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO session_analysis_runs(
                run_id, session_id, request_fingerprint, input_fingerprint,
                metric_pack_key, metric_pack_version, data_tier,
                consent_purpose, consent_policy_version, provider,
                provider_version, adapter_version, source_schema_version,
                content_schema_version, metric_engine_version, redactor_version,
                model_plan_fingerprint, schema_version, local_only, started_at,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 'running')
            """,
            (
                run_id,
                session_id,
                "5" * 64,
                "6" * 64,
                DEFAULT_TEXT_METRIC_PACK_KEY,
                DEFAULT_TEXT_METRIC_PACK_VERSION,
                "redacted_content",
                "text_analysis",
                "explicit-session-text-analysis-v1",
                "synthetic",
                "synthetic-provider-v1",
                "synthetic-adapter-v1",
                "synthetic-schema-v1",
                "redacted-message-v1",
                TEXT_METRIC_ENGINE_VERSION,
                "deterministic-redactor-v1",
                "7" * 64,
                7,
                timestamp,
            ),
        )
        connection.execute("PRAGMA user_version = 7")
        connection.commit()
    return run_id


def _database_and_session(tmp_path) -> tuple[Database, str]:
    database = Database(tmp_path / "metrics.sqlite3")
    database.initialize()
    IngestionService(database, Pseudonymizer(bytes(range(32)))).ingest(
        SyntheticAdapter()
    )
    session_id = database.list_sessions(limit=1)[0]["session_id"]
    return database, session_id


def _draft(session_id: str, identity: str = "a", *, started_at: datetime = NOW):
    return SessionAnalysisRunDraft(
        run_id=identity * 64,
        session_id=session_id,
        request_fingerprint="f" * 64,
        input_fingerprint="b" * 64,
        analysis_profile_key="standard_engineering",
        analysis_profile_version=1,
        metric_pack_key=DEFAULT_TEXT_METRIC_PACK_KEY,
        metric_pack_version=DEFAULT_TEXT_METRIC_PACK_VERSION,
        data_tier=DataTier.REDACTED_CONTENT,
        consent_purpose="text_analysis",
        consent_policy_version="explicit-session-text-analysis-v1",
        provider=Provider.SYNTHETIC,
        provider_version="synthetic-v1",
        adapter_version="synthetic-adapter-v1",
        source_schema_version="synthetic-schema-v1",
        content_schema_version="redacted-message-v1",
        metric_engine_version=TEXT_METRIC_ENGINE_VERSION,
        redactor_version="deterministic-redactor-v1",
        model_plan_fingerprint="c" * 64,
        schema_version=SCHEMA_VERSION,
        started_at=started_at,
    )


def _known_result(
    *,
    key: str = "prompt.goal_definition",
    direction: SessionMetricDirection = SessionMetricDirection.HIGHER_IS_BETTER,
    model_id: str | None = None,
    model_revision: str | None = None,
    model_license: str | None = None,
    tokenizer_id: str | None = None,
    prompt_version: str | None = None,
    rubric_version: str | None = "prompt-logic-rubric-v1",
) -> SessionAnalysisResultRecord:
    return SessionAnalysisResultRecord(
        observation=MetricObservation(
            key=key,
            version=1,
            numeric_value=2 / 3,
            unit="ratio",
            source=MetricSource.DETERMINISTIC,
            observed_count=3,
            eligible_count=4,
            coverage=0.75,
            confidence=0.8,
        ),
        value_state=MetricValueState.KNOWN,
        direction=direction,
        applicability=SessionMetricApplicability.APPLICABLE,
        aggregation_method=SessionMetricAggregation.RATIO_OF_SUMS,
        metric_schema_version=TEXT_METRIC_SCHEMA_VERSION,
        evidence_data_tier=DataTier.REDACTED_CONTENT,
        fraction_numerator=2,
        fraction_denominator=3,
        evidence=(
            SessionAnalysisEvidenceRecord(
                message_id="d" * 64,
                origin=SessionEvidenceOrigin.DIRECT,
            ),
        ),
        signals=(
            SessionAnalysisSignalRecord(
                code="goal.action",
                status=SessionMetricSignalStatus.DETECTED,
                count=1,
            ),
            SessionAnalysisSignalRecord(
                code="goal.target",
                status=SessionMetricSignalStatus.DETECTED,
                count=1,
            ),
            SessionAnalysisSignalRecord(
                code="goal.outcome",
                status=SessionMetricSignalStatus.MISSING,
                count=0,
            ),
        ),
        explanation_code="synthetic_known",
        algorithm_id=TEXT_METRIC_ALGORITHM_ID,
        algorithm_version=TEXT_METRIC_ALGORITHM_VERSION,
        model_id=model_id,
        model_revision=model_revision,
        model_license=model_license,
        tokenizer_id=tokenizer_id,
        prompt_version=prompt_version,
        rubric_version=rubric_version,
        computed_at=NOW + timedelta(minutes=1),
    )


def _not_applicable_result() -> SessionAnalysisResultRecord:
    return SessionAnalysisResultRecord(
        observation=MetricObservation(
            key="logic.plan_state_accounting",
            version=1,
            numeric_value=None,
            unit="ratio",
            source=MetricSource.DETERMINISTIC,
            observed_count=0,
            eligible_count=0,
            coverage=0.0,
            confidence=None,
        ),
        value_state=MetricValueState.NOT_APPLICABLE,
        direction=SessionMetricDirection.HIGHER_IS_BETTER,
        applicability=SessionMetricApplicability.NOT_APPLICABLE,
        aggregation_method=SessionMetricAggregation.RATIO_OF_SUMS,
        metric_schema_version=TEXT_METRIC_SCHEMA_VERSION,
        evidence_data_tier=DataTier.REDACTED_CONTENT,
        explanation_code="no_explicit_plan",
        algorithm_id=TEXT_METRIC_ALGORITHM_ID,
        algorithm_version=TEXT_METRIC_ALGORITHM_VERSION,
        rubric_version="prompt-logic-rubric-v1",
        computed_at=NOW + timedelta(minutes=1),
    )


def test_v8_migration_marks_legacy_analysis_profile_without_guessing(tmp_path) -> None:
    path = tmp_path / "legacy-metrics.sqlite3"
    run_id = _create_v7_analysis_run(path)

    database = Database(path)
    database.initialize()
    stored = database.session_analysis_run_repository().get(run_id)

    assert stored is not None
    assert stored.draft.analysis_profile_key == "legacy.explicit-profile"
    assert stored.draft.analysis_profile_version == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute(
            "SELECT COUNT(*) FROM session_analysis_result_signals"
        ).fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError, match="transition"):
            connection.execute(
                """
                UPDATE session_analysis_runs
                SET analysis_profile_key = 'standard_engineering'
                WHERE run_id = ?
                """,
                (run_id,),
            )


def test_session_quality_snapshot_is_immutable_and_privacy_deletion_cascades(
    tmp_path,
) -> None:
    database, session_id = _database_and_session(tmp_path)
    repository = database.session_analysis_run_repository()
    draft = _draft(session_id)
    known = _known_result()
    not_applicable = _not_applicable_result()

    repository.begin(draft)
    repository.complete(
        draft.run_id,
        (known, not_applicable),
        finished_at=NOW + timedelta(minutes=2),
    )

    stored = repository.get(draft.run_id)
    assert stored is not None and stored.status is AnalysisRunStatus.COMPLETED
    assert repository.get_latest_completed(session_id) == stored
    assert repository.list_for_session(session_id) == (stored,)
    assert repository.get_results(draft.run_id) == (not_applicable, known)
    round_tripped_known = repository.get_results(draft.run_id)[1]
    assert round_tripped_known.fraction_numerator == 2
    assert round_tripped_known.fraction_denominator == 3
    assert round_tripped_known.observation.observed_count == 3
    assert round_tripped_known.observation.eligible_count == 4
    assert tuple(signal.code for signal in round_tripped_known.signals) == (
        "goal.action",
        "goal.target",
        "goal.outcome",
    )

    with sqlite3.connect(database.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE session_analysis_results SET numeric_value = 1 WHERE run_id = ?",
                (draft.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE session_analysis_result_signals SET signal_count = 0 WHERE run_id = ?",
                (draft.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="parent privacy deletion"):
            connection.execute(
                "DELETE FROM session_analysis_result_signals WHERE run_id = ?",
                (draft.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE session_analysis_result_evidence SET origin = 'inherited' WHERE run_id = ?",
                (draft.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="parent privacy deletion"):
            connection.execute(
                "DELETE FROM session_analysis_result_evidence WHERE run_id = ?",
                (draft.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="parent privacy deletion"):
            connection.execute(
                "DELETE FROM session_analysis_results WHERE run_id = ?",
                (draft.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="transition"):
            connection.execute(
                "UPDATE session_analysis_runs SET adapter_version = 'changed-v2' WHERE run_id = ?",
                (draft.run_id,),
            )
        for column, value in (
            ("request_fingerprint", "1" * 64),
            ("input_fingerprint", "2" * 64),
        ):
            with pytest.raises(sqlite3.IntegrityError, match="transition"):
                connection.execute(
                    f"UPDATE session_analysis_runs SET {column} = ? WHERE run_id = ?",
                    (value, draft.run_id),
                )

    assert repository.delete_for_privacy(draft.run_id) is True
    assert repository.get(draft.run_id) is None
    with sqlite3.connect(database.path) as connection:
        counts = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "session_analysis_runs",
                "session_analysis_results",
                "session_analysis_result_evidence",
                "session_analysis_result_signals",
            )
        )
    assert counts == (0, 0, 0, 0)


def test_hybrid_model_provenance_round_trips_per_result(tmp_path) -> None:
    database, session_id = _database_and_session(tmp_path)
    repository = database.session_analysis_run_repository()
    draft = _draft(session_id)
    embedding_result = _known_result(
        key="logic.requirement_action_traceability",
        model_id="example/e5-small",
        model_revision="0123456789abcdef",
        model_license="mit",
        tokenizer_id="example/e5-small",
        rubric_version="traceability-rubric-v1",
    )
    nli_result = _known_result(
        key="logic.scoped_consistency_candidate_rate",
        direction=SessionMetricDirection.LOWER_IS_BETTER,
        model_id="example/mdeberta-nli",
        model_revision="fedcba9876543210",
        model_license="mit",
        tokenizer_id="example/mdeberta-nli",
        prompt_version=None,
        rubric_version="consistency-rubric-v1",
    )

    repository.begin(draft)
    repository.complete(
        draft.run_id,
        (embedding_result, nli_result),
        finished_at=NOW + timedelta(minutes=2),
    )

    by_key = {
        result.observation.key: result
        for result in repository.get_results(draft.run_id)
    }
    assert by_key["logic.requirement_action_traceability"].model_id == (
        "example/e5-small"
    )
    assert by_key["logic.scoped_consistency_candidate_rate"].model_id == (
        "example/mdeberta-nli"
    )
    assert all(result.prompt_version is None for result in by_key.values())


def test_authenticated_quality_reads_return_hybrid_profile_without_text(tmp_path) -> None:
    database, session_id = _database_and_session(tmp_path)
    repository = database.session_analysis_run_repository()
    draft = _draft(session_id)
    e5 = _known_result(
        key="logic.requirement_action_traceability",
        model_id="example/e5-small",
        model_revision="0123456789abcdef",
        model_license="mit",
        tokenizer_id="example/e5-small",
        rubric_version="traceability-rubric-v1",
    )
    nli = _known_result(
        key="logic.scoped_consistency_candidate_rate",
        direction=SessionMetricDirection.LOWER_IS_BETTER,
        model_id="example/mdeberta-nli",
        model_revision="fedcba9876543210",
        model_license="mit",
        tokenizer_id="example/mdeberta-nli",
        rubric_version="consistency-rubric-v1",
    )
    repository.begin(draft)
    repository.complete(
        draft.run_id,
        (e5, nli),
        finished_at=NOW + timedelta(minutes=2),
    )

    app = create_app(
        settings=AppSettings(home=tmp_path),
        database=database,
        api_token=EXAMPLE_TOKEN,
    )
    headers = {API_TOKEN_HEADER: EXAMPLE_TOKEN}
    with TestClient(app, base_url="http://127.0.0.1") as client:
        unauthorized = client.get(
            f"/v1/sessions/{session_id}/quality-analysis-runs/latest"
        )
        run_list = client.get(
            f"/v1/sessions/{session_id}/quality-analysis-runs",
            headers=headers,
        )
        latest = client.get(
            f"/v1/sessions/{session_id}/quality-analysis-runs/latest",
            headers=headers,
        )
        detail = client.get(
            f"/v1/quality-analysis/runs/{draft.run_id}",
            headers=headers,
        )

    assert unauthorized.status_code == 401
    assert run_list.status_code == latest.status_code == detail.status_code == 200
    assert run_list.json()["runs"][0]["request_fingerprint"] == "f" * 64
    assert latest.json() == detail.json()
    payload = detail.json()
    assert payload["run"]["input_fingerprint"] == "b" * 64
    assert payload["run"]["analysis_profile_key"] == "standard_engineering"
    assert payload["run"]["analysis_profile_version"] == 1
    assert payload["run"]["model_plan_fingerprint"] == "c" * 64
    by_key = {result["key"]: result for result in payload["results"]}
    traceability = by_key["logic.requirement_action_traceability"]
    consistency = by_key["logic.scoped_consistency_candidate_rate"]
    assert traceability["dimension"] == "logic"
    assert traceability["display_name"] == "Requirement-to-action traceability"
    assert traceability["fraction"] == {"numerator": 2, "denominator": 3}
    assert traceability["signals"] == [
        {"code": "goal.action", "status": "detected", "count": 1},
        {"code": "goal.target", "status": "detected", "count": 1},
        {"code": "goal.outcome", "status": "missing", "count": 0},
    ]
    assert (traceability["observed_count"], traceability["eligible_count"]) == (3, 4)
    assert traceability["aggregation_method"] == "ratio_of_sums"
    assert traceability["model_id"] == "example/e5-small"
    assert consistency["model_id"] == "example/mdeberta-nli"
    serialized = detail.text.casefold()
    for prohibited in ("prompt_text", "excerpt", "filesystem_path", "raw_content"):
        assert prohibited not in serialized


def test_authenticated_current_coaching_projection_uses_reviewed_task_context(
    tmp_path,
) -> None:
    database, session_id = _database_and_session(tmp_path)
    session = database.get_session(session_id)
    assert session is not None
    draft = _draft(session_id).model_copy(
        update={
            "analysis_profile_key": "coaching_profile",
            "metric_pack_key": COACHING_METRIC_PACK_KEY,
            "metric_pack_version": COACHING_METRIC_PACK_VERSION,
            "metric_engine_version": COACHING_METRIC_ENGINE_VERSION,
        }
    )
    deliverable = _known_result(key="prompt.deliverable_contract")
    deliverable = deliverable.model_copy(
        update={
            "observation": deliverable.observation.model_copy(
                update={
                    "version": 3,
                    "numeric_value": 1.0,
                    "observed_count": 12,
                    "eligible_count": 12,
                    "coverage": 1.0,
                    "confidence": None,
                }
            ),
            "fraction_numerator": 12,
            "fraction_denominator": 12,
            "algorithm_id": COACHING_METRIC_ALGORITHM_ID,
            "algorithm_version": COACHING_METRIC_ALGORITHM_VERSION,
            "rubric_version": "coaching-observables-rubric-2",
        }
    )
    acceptance = _known_result(key="prompt.acceptance_testability")
    acceptance = acceptance.model_copy(
        update={
            "observation": acceptance.observation.model_copy(
                update={
                    "version": 2,
                    "numeric_value": 0.0,
                    "observed_count": 12,
                    "eligible_count": 12,
                    "coverage": 1.0,
                    "confidence": None,
                }
            ),
            "fraction_numerator": 0,
            "fraction_denominator": 12,
            "algorithm_id": COACHING_METRIC_ALGORITHM_ID,
            "algorithm_version": COACHING_METRIC_ALGORITHM_VERSION,
            "rubric_version": "coaching-observables-rubric-2",
        }
    )
    analysis_repository = database.session_analysis_run_repository()
    analysis_repository.begin(draft)
    analysis_repository.complete(
        draft.run_id,
        (deliverable, acceptance),
        finished_at=NOW + timedelta(minutes=2),
    )
    database.task_repository().append_revision(
        TaskRevisionRecord(
            task_id="9" * 64,
            revision=1,
            project_id=session.project_id,
            task_type="feature_implementation",
            lifecycle_state="confirmed",
            session_ids=(session_id,),
            input_fingerprint="8" * 64,
            created_at=NOW,
        )
    )
    app = create_app(
        settings=AppSettings(home=tmp_path),
        database=database,
        api_token=EXAMPLE_TOKEN,
    )
    path = f"/v1/quality-analysis/runs/{draft.run_id}/coaching-summary"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        unauthorized = client.get(path)
        response = client.get(path, headers={API_TOKEN_HEADER: EXAMPLE_TOKEN})

    assert unauthorized.status_code == 401
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["projection_key"] == "coaching.loop.current"
    assert body["task_type"] == "implementation"
    assert body["task_context_source"] == "reviewed_task"
    assert body["summary"]["outcome"]["status"] == "unknown"
    strength = body["summary"]["strength"]
    friction = body["summary"]["friction"]
    assert strength["code"] == "strength.deliverable_contract"
    assert strength["task_type"] == "implementation"
    assert strength["denominator_kind"] == "event_count"
    assert strength["polarity_successes"] == 12
    assert strength["evidence_lower_bound"] >= 0.75
    assert strength["candidate_policy_version"] == 2
    assert friction["code"] == (
        "friction.acceptance_before_implementation_unclear"
    )
    assert friction["evidence_upper_bound"] <= 0.25
    serialized = response.text.casefold()
    assert session_id not in serialized
    for prohibited in ("prompt_text", "excerpt", "filesystem_path", "raw_content"):
        assert prohibited not in serialized


def test_contracts_reject_text_and_incomplete_model_provenance_without_echoing(
    tmp_path,
) -> None:
    _, session_id = _database_and_session(tmp_path)
    canary = "SYNTHETIC-PRIVATE-SESSION-TEXT-CANARY"
    with pytest.raises(ValidationError) as error:
        SessionAnalysisResultRecord(
            **_known_result().model_dump(),
            prompt_text=canary,
        )
    assert canary not in str(error.value)

    with pytest.raises(ValidationError, match="pinned revision"):
        _known_result(model_id="example/model")
    with pytest.raises(ValidationError, match="redacted-content"):
        SessionAnalysisRunDraft.model_validate(
            {
                **_draft(session_id).model_dump(),
                "data_tier": DataTier.METADATA,
            }
        )


def test_newer_failed_run_does_not_replace_latest_completed_snapshot(tmp_path) -> None:
    database, session_id = _database_and_session(tmp_path)
    repository = database.session_analysis_run_repository()
    completed = _draft(session_id, "a")
    failed = _draft(
        session_id,
        "e",
        started_at=NOW + timedelta(minutes=10),
    )
    repository.begin(completed)
    repository.complete(
        completed.run_id,
        (_known_result(),),
        finished_at=NOW + timedelta(minutes=2),
    )
    repository.begin(failed)
    repository.fail(
        failed.run_id,
        finished_at=NOW + timedelta(minutes=11),
        failure_code="synthetic_failure",
    )

    latest = repository.get_latest_completed(session_id)
    assert latest is not None and latest.draft.run_id == completed.run_id
    assert [run.status for run in repository.list_for_session(session_id)] == [
        AnalysisRunStatus.FAILED,
        AnalysisRunStatus.COMPLETED,
    ]


def test_latest_completed_aggregation_projection_is_one_query_and_evidence_free(
    tmp_path,
) -> None:
    database = Database(tmp_path / "metrics.sqlite3")
    database.initialize()
    IngestionService(database, Pseudonymizer(bytes(range(32)))).ingest(
        SyntheticAdapter()
    )
    session_ids = tuple(
        row["session_id"] for row in database.list_sessions(limit=10)
    )
    assert len(session_ids) == 2
    first_session, second_session = session_ids
    repository = database.session_analysis_run_repository()

    older = _draft(
        first_session,
        "a",
        started_at=NOW - timedelta(minutes=10),
    )
    newer = _draft(first_session, "b", started_at=NOW)
    second = _draft(second_session, "c", started_at=NOW)
    repository.begin(older)
    repository.complete(
        older.run_id,
        (_known_result(),),
        finished_at=NOW + timedelta(minutes=2),
    )
    repository.begin(newer)
    repository.complete(
        newer.run_id,
        (
            _known_result(
                model_id="example/model",
                model_revision="pinned-revision",
                model_license="mit",
                tokenizer_id="example/tokenizer",
                prompt_version="prompt-v1",
            ),
        ),
        finished_at=NOW + timedelta(minutes=2),
    )
    repository.begin(second)
    repository.complete(
        second.run_id,
        (_not_applicable_result(),),
        finished_at=NOW + timedelta(minutes=2),
    )

    selected_set = set(session_ids)
    missing_ids: list[str] = []
    candidate = 1
    while len(missing_ids) < 98:
        safe_id = f"{candidate:064x}"
        candidate += 1
        if safe_id not in selected_set:
            missing_ids.append(safe_id)
    selection = (
        second_session,
        *missing_ids[:49],
        first_session,
        *missing_ids[49:],
    )
    assert len(selection) == 100

    statements: list[str] = []
    connection_scope = repository._connection_scope

    @contextmanager
    def traced_connection(*, readonly: bool = False):
        with connection_scope(readonly=readonly) as connection:
            connection.set_trace_callback(statements.append)
            yield connection

    repository._connection_scope = traced_connection
    snapshots = repository.get_latest_completed_for_aggregation(
        selection,
        **AGGREGATION_FILTER,
    )

    batch_statements = tuple(
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("WITH SELECTED")
    )
    assert len(batch_statements) == 1
    assert all(
        "session_analysis_result_evidence" not in statement.lower()
        for statement in statements
    )
    assert all(
        "session_analysis_result_signals" not in statement.lower()
        for statement in statements
    )
    assert tuple(snapshot.session_id for snapshot in snapshots) == (
        second_session,
        first_session,
    )
    assert snapshots[1].results[0].model_id == "example/model"
    assert snapshots[1].results[0].model_revision == "pinned-revision"

    serialized = "".join(snapshot.model_dump_json() for snapshot in snapshots)
    assert "d" * 64 not in serialized
    for forbidden_field in (
        '"evidence"',
        '"message_id"',
        '"explanation_code"',
        '"error_code"',
        '"computed_at"',
        '"run_id"',
        '"request_fingerprint"',
        '"input_fingerprint"',
    ):
        assert forbidden_field not in serialized


def test_aggregation_projection_rejects_empty_oversized_and_duplicate_selection(
    tmp_path,
) -> None:
    database, session_id = _database_and_session(tmp_path)
    repository = database.session_analysis_run_repository()

    with pytest.raises(ValueError):
        repository.get_latest_completed_for_aggregation((), **AGGREGATION_FILTER)
    with pytest.raises(ValueError):
        repository.get_latest_completed_for_aggregation(
            (session_id, session_id),
            **AGGREGATION_FILTER,
        )
    with pytest.raises(ValueError):
        repository.get_latest_completed_for_aggregation(
            tuple(f"{index:064x}" for index in range(101)),
            **AGGREGATION_FILTER,
        )


def test_aggregation_projection_selects_latest_matching_profile_not_latest_any_pack(
    tmp_path,
) -> None:
    database, session_id = _database_and_session(tmp_path)
    repository = database.session_analysis_run_repository()
    matching = _draft(session_id, "a", started_at=NOW)
    repository.begin(matching)
    repository.complete(
        matching.run_id,
        (_known_result(),),
        finished_at=NOW + timedelta(minutes=1),
    )
    newer_other_profile = _draft(
        session_id,
        "b",
        started_at=NOW + timedelta(minutes=2),
    ).model_copy(
        update={
            "request_fingerprint": "e" * 64,
            "input_fingerprint": "d" * 64,
            "analysis_profile_key": "alternate_engineering",
        }
    )
    repository.begin(newer_other_profile)
    repository.complete(
        newer_other_profile.run_id,
        (
            _known_result().model_copy(
                update={"computed_at": NOW + timedelta(minutes=2)}
            ),
        ),
        finished_at=NOW + timedelta(minutes=3),
    )

    snapshots = repository.get_latest_completed_for_aggregation(
        (session_id,),
        **AGGREGATION_FILTER,
    )

    assert len(snapshots) == 1
    assert snapshots[0].analysis_profile_key == "standard_engineering"
    assert snapshots[0].metric_pack_key == DEFAULT_TEXT_METRIC_PACK_KEY
