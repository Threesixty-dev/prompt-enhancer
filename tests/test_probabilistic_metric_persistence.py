from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import sqlite3

from fastapi.testclient import TestClient
import pytest
from pydantic import SecretStr

import prompt_enhancer.application.analysis.probabilistic_metrics as probabilistic_module
from prompt_enhancer.adapters.synthetic import SyntheticAdapter
from prompt_enhancer.application.analysis.coaching_baselines import (
    COACHING_METRIC_DEFINITIONS,
)
from prompt_enhancer.application.analysis.model_ensemble import (
    build_ensemble_chunks,
    coaching_ensemble_metric_specs,
)
from prompt_enhancer.application.analysis.model_ensemble_watch import (
    ModelEnsembleAttemptState,
    ModelEnsembleStageState,
    ModelEnsembleWatchState,
)
from prompt_enhancer.application.analysis.metric_projection_v2 import (
    project_metric_states_v2,
)
from prompt_enhancer.application.analysis.metric_publication_v2 import (
    MetricPublicationSource,
    publish_metric_states_v2,
)
from prompt_enhancer.application.analysis.probabilistic_metrics import (
    EVIDENCE_LANE_METRIC_KEYS,
    PROBABILISTIC_METRIC_CONTRACTS,
    PROBABILISTIC_METRIC_PROJECTION_VERSION,
    PROBABILISTIC_MODEL_SET_VERSION,
    PROBABILISTIC_MODEL_SET_VERSION_V2,
    PredictiveMetricState,
    SessionPredictiveMetricProjection,
    SessionPredictiveMetricReceipt,
)
from prompt_enhancer.application.analysis.session_model_ensemble import (
    SessionModelEnsembleOutcome,
    SessionModelEnsembleRunRecord,
)
from prompt_enhancer.application.analysis.semantic_units import (
    SemanticUnitReconciler,
)
from prompt_enhancer.application.analysis.text_contracts import (
    ApplicabilityBasis,
    EphemeralRedactedMessage,
    MetricApplicability,
    MetricApplicabilityDecision,
    P1TextAnalysisInput,
    TextLanguage,
    TextMessageKind,
    TextRole,
    TextTaskProfile,
)
from prompt_enhancer.database import (
    SCHEMA_VERSION,
    Database,
    DatabaseError,
    _MIGRATION_1,
)
from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.config import AppSettings
from prompt_enhancer.domain import Provider
from prompt_enhancer.ingestion import IngestionService
from prompt_enhancer.infrastructure.text_models.probabilistic_metrics import (
    LIVE_PROBABILISTIC_PLAN_VERSION,
    LocalProbabilisticMetricRunner,
    PROBABILISTIC_DEEP_TIMEOUT_ERROR_CODE,
)
from prompt_enhancer.infrastructure.sqlite import migrations
from prompt_enhancer.infrastructure.sqlite.model_ensemble import (
    SqliteSessionModelEnsembleRepository,
    _predictive_projection_fingerprint,
)
from prompt_enhancer.privacy import Pseudonymizer


NOW = datetime(2042, 4, 5, 12, 0, tzinfo=UTC)
TOKEN = "example_probabilistic_metric_token_1234567890"


class _SyntheticIdFactory:
    def fingerprint(self, namespace: str, values: tuple[str, ...]) -> str:
        return hashlib.sha256(
            "\x1f".join((namespace, *values)).encode("utf-8")
        ).hexdigest()

    def fingerprint_secret(
        self,
        namespace: str,
        values: tuple[str, ...],
        secret: SecretStr,
    ) -> str:
        return hashlib.sha256(
            "\x1f".join(
                (namespace, *values, secret.get_secret_value())
            ).encode("utf-8")
        ).hexdigest()


IDS = _SyntheticIdFactory()


class _ReadOnlyService:
    def __init__(self, record: SessionModelEnsembleRunRecord) -> None:
        self._record = record

    def get(self, run_id: str) -> SessionModelEnsembleRunRecord | None:
        return self._record if run_id == self._record.run_id else None

    def latest(self, session_id: str) -> SessionModelEnsembleRunRecord | None:
        return self._record if session_id == self._record.session_id else None

    def run(self, **_values):  # type: ignore[no-untyped-def]
        raise AssertionError("not used")


def _context(session_id: str) -> P1TextAnalysisInput:
    messages = (
        EphemeralRedactedMessage(
            message_id="1" * 64,
            sequence=0,
            role=TextRole.USER,
            kind=TextMessageKind.REQUEST,
            language=TextLanguage.ENGLISH,
            text=SecretStr(
                "Create a fictional parser, preserve unknown values, and verify it with tests."
            ),
        ),
        EphemeralRedactedMessage(
            message_id="2" * 64,
            sequence=1,
            role=TextRole.AGENT,
            kind=TextMessageKind.VERIFICATION,
            language=TextLanguage.ENGLISH,
            text=SecretStr(
                "The fictional implementation is linked to a synthetic passing test receipt."
            ),
        ),
    )
    return P1TextAnalysisInput(
        provider=Provider.CODEX,
        session_id=session_id,
        provider_version="synthetic-provider-v1",
        adapter_version="synthetic-adapter-v1",
        source_schema_version="synthetic-source-v1",
        content_schema_version="synthetic-content-v1",
        redactor_version="synthetic-redactor-v1",
        text_extraction_complete=True,
        available_message_kinds=frozenset(
            {TextMessageKind.REQUEST, TextMessageKind.VERIFICATION}
        ),
        analysis_window_fingerprint="a" * 64,
        focus_message_id=messages[0].message_id,
        observed_message_count=2,
        eligible_message_count=2,
        messages=messages,
        task_profile=TextTaskProfile(
            applicability=tuple(
                MetricApplicabilityDecision(
                    metric_key=item.key,
                    applicability=MetricApplicability.APPLICABLE,
                    basis=ApplicabilityBasis.USER_SELECTED,
                )
                for item in COACHING_METRIC_DEFINITIONS
            )
        ),
    )


def _database_and_session(tmp_path) -> tuple[Database, str]:
    database = Database(tmp_path / "probabilistic.sqlite3")
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


def _database_and_session_at_v38(tmp_path) -> tuple[Database, str, str]:
    """Create a real v38 database without allowing Database to auto-upgrade."""

    path = tmp_path / "probabilistic-v38.sqlite3"
    scripts = (_MIGRATION_1,) + tuple(
        getattr(migrations, f"MIGRATION_{version}")
        for version in range(2, 39)
    )
    applied_at = NOW.isoformat(timespec="microseconds")
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
                (
                    version,
                    hashlib.sha256(script.encode("utf-8")).hexdigest(),
                    applied_at,
                )
                for version, script in enumerate(scripts, start=1)
            ),
        )
        installation_id = "4" * 64
        project_id = "5" * 64
        session_id = "6" * 64
        connection.execute(
            "INSERT INTO installations VALUES(?,?,?)",
            (installation_id, "codex", applied_at),
        )
        connection.execute(
            """INSERT INTO projects(
                   project_id,installation_id,provider,created_at
               ) VALUES(?,?,?,?)""",
            (project_id, installation_id, "codex", applied_at),
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
                "codex",
                "synthetic-provider-v1",
                "synthetic-adapter-v1",
                "synthetic-source-v1",
                applied_at,
                applied_at,
                applied_at,
                applied_at,
            ),
        )
        connection.execute("PRAGMA user_version=38")
        connection.commit()

    return Database(path), session_id, project_id


def _completed_result(payload):
    return {
        "status": "completed",
        "device": "cuda",
        "rows": [
            {
                "case_id": item["case_id"],
                "entailment": 0.98,
                "neutral": 0.01,
                "contradiction": 0.01,
            }
            for item in payload["cases"]
        ],
        "runtime": {
            "inference_latency_ms": 80.0,
            "peak_cuda_allocated_mb": 900.0,
            "process_rss_after_load_and_inference_mb": 1_400.0,
        },
    }


def _uncertain_result(payload):
    return {
        "status": "completed",
        "device": "cuda",
        "rows": [
            {
                "case_id": item["case_id"],
                "entailment": 0.35,
                "neutral": 0.50,
                "contradiction": 0.15,
            }
            for item in payload["cases"]
        ],
        "runtime": {
            "inference_latency_ms": 80.0,
            "peak_cuda_allocated_mb": 900.0,
            "process_rss_after_load_and_inference_mb": 1_400.0,
        },
    }


def test_predictive_projection_round_trips_is_immutable_and_privacy_cascades(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, session_id = _database_and_session(tmp_path)
    runner = LocalProbabilisticMetricRunner(
        executor=lambda spec, stage, payload, device: _completed_result(payload),
        clock=lambda: NOW,
    )
    receipt = runner.run(
        build_ensemble_chunks(_context(session_id)),
        coaching_ensemble_metric_specs(),
    )
    record = SessionModelEnsembleRunRecord(
        run_id="b" * 64,
        session_id=session_id,
        request_fingerprint="c" * 64,
        input_fingerprint="a" * 64,
        provider=Provider.CODEX,
        provider_version="synthetic-provider-v1",
        adapter_version="synthetic-adapter-v1",
        source_schema_version="synthetic-source-v1",
        content_schema_version="synthetic-content-v1",
        redactor_version="synthetic-redactor-v1",
        receipt=receipt,
    )

    repository = database.model_ensemble_repository()
    repository.save_completed(record)

    # A stored v35/v1 receipt is historical data. Advancing the active live
    # registry must not make that immutable row unreadable.
    advanced = replace(
        PROBABILISTIC_METRIC_CONTRACTS[0],
        contract_version="probabilistic-metric-contract-v2",
    )
    advanced_registry = (advanced, *PROBABILISTIC_METRIC_CONTRACTS[1:])
    monkeypatch.setattr(
        probabilistic_module,
        "PROBABILISTIC_METRIC_CONTRACTS",
        advanced_registry,
    )
    monkeypatch.setattr(
        probabilistic_module,
        "_CONTRACT_BY_KEY",
        {item.metric_key: item for item in advanced_registry},
    )
    loaded = repository.get(record.run_id)

    assert loaded is not None
    assert loaded.receipt.predictive_projection == receipt.predictive_projection
    assert loaded.receipt.predictive_projection is not None
    assert len(loaded.receipt.predictive_projection.metrics) == 20
    by_key = {
        item.metric_key: item
        for item in loaded.receipt.predictive_projection.metrics
    }
    assert all(
        by_key[key].state is PredictiveMetricState.UNAVAILABLE
        for key in EVIDENCE_LANE_METRIC_KEYS
    )
    contract_by_key = {
        item.metric_key: item for item in PROBABILISTIC_METRIC_CONTRACTS
    }
    assert all(
        item.state
        is (
            PredictiveMetricState.EXPERIMENTAL
            if contract_by_key[key].closure_horizon == "immediate"
            and not contract_by_key[key].objective_evidence_required
            and key not in EVIDENCE_LANE_METRIC_KEYS
            else PredictiveMetricState.UNAVAILABLE
        )
        for key, item in by_key.items()
    )

    project_id = database.list_sessions(provider=Provider.CODEX, limit=1)[0][
        "project_id"
    ]
    watches = database.model_ensemble_watch_repository()
    watch_id = "9" * 64
    watches.enable(
        watch_id=watch_id,
        provider=Provider.CODEX,
        project_id=project_id,
        session_id=session_id,
        max_messages=100,
        now=NOW,
    )
    claimed = watches.claim_due(
        owner="8" * 64,
        now=NOW,
        lease_duration=timedelta(minutes=30),
    )
    assert claimed is not None
    _, lease = claimed
    watches.complete(
        lease,
        now=NOW + timedelta(seconds=1),
        next_check_at=NOW + timedelta(seconds=61),
        outcome=SessionModelEnsembleOutcome(run=record, applied=True),
    )
    first_attempt = watches.list_attempts(watch_id, limit=1)[0]
    assert first_attempt.stage_count == 3

    claimed = watches.claim_due(
        owner="8" * 64,
        now=NOW + timedelta(seconds=61),
        lease_duration=timedelta(minutes=30),
    )
    assert claimed is not None
    _, lease = claimed
    watches.complete(
        lease,
        now=NOW + timedelta(seconds=62),
        next_check_at=NOW + timedelta(seconds=122),
        outcome=SessionModelEnsembleOutcome(run=record, applied=False),
    )
    reused_attempt = watches.list_attempts(watch_id, limit=1)[0]
    assert reused_attempt.stage_count == 0
    assert watches.get_attempt_stages(reused_attempt.attempt_id) == ()
    with sqlite3.connect(database.path) as connection:
        counts = {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - closed test constants
            ).fetchone()[0]
            for table in (
                "session_model_ensemble_predictive_metrics",
                "session_model_ensemble_predictive_factors",
                "session_model_ensemble_predictive_density_bins",
                "session_model_ensemble_predictive_model_stages",
                "session_model_ensemble_predictive_metric_seals",
            )
        }
        assert counts["session_model_ensemble_predictive_metrics"] == 20
        assert counts["session_model_ensemble_predictive_density_bins"] == 160
        assert counts["session_model_ensemble_predictive_model_stages"] == 3
        assert counts["session_model_ensemble_predictive_metric_seals"] == 1
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """UPDATE session_model_ensemble_predictive_metrics
                   SET mean=0.0 WHERE run_id=? AND projection_version=?""",
                (record.run_id, PROBABILISTIC_METRIC_PROJECTION_VERSION),
            )

    app = create_app(
        settings=AppSettings(home=tmp_path),
        database=database,
        api_token=TOKEN,
        session_model_ensemble_service=_ReadOnlyService(record),  # type: ignore[arg-type]
    )
    metric_key = receipt.predictive_projection.metrics[0].metric_key
    detail_path = (
        f"/v1/model-ensemble-runs/{record.run_id}/metrics/{metric_key}/predictive-detail"
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get(detail_path).status_code == 401
        detail = client.get(detail_path, headers={API_TOKEN_HEADER: TOKEN})
    assert detail.status_code == 200
    assert detail.headers["cache-control"] == "no-store, private"
    assert detail.headers["pragma"] == "no-cache"
    payload = detail.json()
    assert payload["experimental_label"] == "Experimental model range"
    assert payload["universal_trust_percentage_available"] is False
    assert len(payload["density_bins"]) == 20
    assert payload["factors"]
    assert "source_window_fingerprint" not in detail.text
    assert "fragment_id" not in detail.text
    assert "fictional parser" not in detail.text.lower()

    database_bytes = database.path.read_bytes()
    assert b"Create a fictional parser" not in database_bytes
    assert b"fictional implementation" not in database_bytes

    assert repository.delete_for_privacy(record.run_id) is True
    with sqlite3.connect(database.path) as connection:
        for table in (
            "session_model_ensemble_predictive_metrics",
            "session_model_ensemble_predictive_factors",
            "session_model_ensemble_predictive_density_bins",
            "session_model_ensemble_predictive_model_stages",
            "session_model_ensemble_predictive_metric_seals",
        ):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - closed test constants
            ).fetchone()[0] == 0


def test_metric_v2_publication_round_trips_is_immutable_and_privacy_cascades(
    tmp_path,
) -> None:
    database, session_id = _database_and_session(tmp_path)
    context = _context(session_id)
    receipt = LocalProbabilisticMetricRunner(
        executor=lambda spec, stage, payload, device: _completed_result(payload),
        clock=lambda: NOW,
    ).run(
        build_ensemble_chunks(context),
        coaching_ensemble_metric_specs(),
    )
    reconciliation = SemanticUnitReconciler(IDS).reconcile(context).reconciliation
    publication = publish_metric_states_v2(
        project_metric_states_v2(
            context=context,
            reconciliation=reconciliation,
            id_factory=IDS,
        )
    )
    assert publication.source is MetricPublicationSource.LIVE_PROJECTION
    assert publication.canonical_live_snapshot is True
    assert publication.compatibility_preview is False
    assert publication.model_stage_consumed is False
    assert len(publication.metrics) == 20

    receipt = receipt.model_copy(
        update={"metric_publication_v2": publication}
    )
    record = SessionModelEnsembleRunRecord(
        run_id="7" * 64,
        session_id=session_id,
        request_fingerprint="8" * 64,
        input_fingerprint="a" * 64,
        provider=Provider.CODEX,
        provider_version="synthetic-provider-v1",
        adapter_version="synthetic-adapter-v1",
        source_schema_version="synthetic-source-v1",
        content_schema_version="synthetic-content-v1",
        redactor_version="synthetic-redactor-v1",
        receipt=receipt,
    )
    repository = database.model_ensemble_repository()
    repository.save_completed(record)

    loaded = repository.get(record.run_id)
    assert loaded is not None
    assert loaded.receipt.metric_publication_v2 == publication
    assert {item.metric_key for item in loaded.receipt.metrics} == {
        item.metric_key for item in record.receipt.metrics
    }

    # A projection fingerprint seals content; it is not a global run identity.
    # Two independent runs may legitimately publish the same twenty states.
    second = record.model_copy(
        update={
            "run_id": "6" * 64,
            "request_fingerprint": "5" * 64,
            "receipt": record.receipt.model_copy(
                update={"predictive_projection": None}
            ),
        }
    )
    repository.save_completed(second)
    second_loaded = repository.get(second.run_id)
    assert second_loaded is not None
    assert second_loaded.receipt.metric_publication_v2 == publication
    third = second.model_copy(
        update={
            "run_id": "0" * 64,
            "request_fingerprint": "9" * 64,
        }
    )
    repository.save_completed(third)

    legacy = second.model_copy(
        update={
            "run_id": "4" * 64,
            "request_fingerprint": "3" * 64,
            "receipt": second.receipt.model_copy(
                update={"metric_publication_v2": None}
            ),
        }
    )
    repository.save_completed(legacy)
    project_id = database.list_sessions(provider=Provider.CODEX, limit=1)[0][
        "project_id"
    ]
    watches = database.model_ensemble_watch_repository()
    watch_id = "2" * 64
    watches.enable(
        watch_id=watch_id,
        provider=Provider.CODEX,
        project_id=project_id,
        session_id=session_id,
        max_messages=100,
        now=NOW,
    )
    claimed = watches.claim_due(
        owner="1" * 64,
        now=NOW,
        lease_duration=timedelta(minutes=30),
    )
    assert claimed is not None
    _, lease = claimed
    watches.complete(
        lease,
        now=NOW + timedelta(seconds=1),
        next_check_at=NOW + timedelta(seconds=2),
        outcome=SessionModelEnsembleOutcome(run=legacy, applied=True),
    )
    claimed = watches.claim_due(
        owner="1" * 64,
        now=NOW + timedelta(seconds=2),
        lease_duration=timedelta(minutes=30),
    )
    assert claimed is not None
    _, lease = claimed
    watches.complete(
        lease,
        now=NOW + timedelta(seconds=3),
        next_check_at=NOW + timedelta(seconds=4),
        outcome=SessionModelEnsembleOutcome(run=second, applied=True),
    )
    claimed = watches.claim_due(
        owner="1" * 64,
        now=NOW + timedelta(seconds=4),
        lease_duration=timedelta(minutes=30),
    )
    assert claimed is not None
    _, lease = claimed
    watches.complete(
        lease,
        now=NOW + timedelta(seconds=5),
        next_check_at=NOW + timedelta(seconds=60),
        outcome=SessionModelEnsembleOutcome(run=third, applied=True),
    )
    trajectory = watches.list_publications(
        watch_id,
        before_generation=None,
        limit=12,
    )
    assert tuple(point.run_id for point in trajectory.points) == (
        third.run_id,
        second.run_id,
        legacy.run_id,
    )
    assert trajectory.points[0].comparable_to_head is True
    assert trajectory.points[1].comparable_to_head is True
    assert trajectory.points[2].comparable_to_head is False
    assert trajectory.points[0].metric_states_v2 == tuple(
        item.state for item in publication.metrics
    )
    assert trajectory.points[1].metric_states_v2 == trajectory.points[0].metric_states_v2
    assert trajectory.points[2].metric_states_v2 == ()

    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        assert connection.execute(
            """SELECT COUNT(*) FROM session_model_ensemble_metric_states_v2
               WHERE run_id=?""",
            (record.run_id,),
        ).fetchone()[0] == 20
        assert connection.execute(
            """SELECT COUNT(*)
               FROM session_model_ensemble_metric_publication_v2_seals
               WHERE run_id=?""",
            (record.run_id,),
        ).fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """UPDATE session_model_ensemble_metric_states_v2
                   SET source_complete=source_complete
                   WHERE run_id=?""",
                (record.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="sealed"):
            connection.execute(
                """INSERT INTO session_model_ensemble_metric_states_v2
                   SELECT * FROM session_model_ensemble_metric_states_v2
                   WHERE run_id=? LIMIT 1""",
                (record.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """UPDATE session_model_ensemble_metric_publication_v2_seals
                   SET known_count=known_count WHERE run_id=?""",
                (record.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="parent privacy deletion"):
            connection.execute(
                """DELETE FROM session_model_ensemble_metric_states_v2
                   WHERE run_id=?""",
                (record.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="parent privacy deletion"):
            connection.execute(
                """DELETE FROM session_model_ensemble_metric_publication_v2_seals
                   WHERE run_id=?""",
                (record.run_id,),
            )

    database_bytes = database.path.read_bytes()
    assert b"Create a fictional parser" not in database_bytes
    assert b"fictional implementation" not in database_bytes

    assert repository.delete_for_privacy(record.run_id) is True
    # Privacy deletion is deliberately session-wide, so the sibling run is
    # erased by the same operation.
    assert repository.get(second.run_id) is None
    with sqlite3.connect(database.path) as connection:
        assert connection.execute(
            """SELECT COUNT(*) FROM session_model_ensemble_metric_states_v2
               WHERE run_id=?""",
            (record.run_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            """SELECT COUNT(*)
               FROM session_model_ensemble_metric_publication_v2_seals
               WHERE run_id=?""",
            (record.run_id,),
        ).fetchone()[0] == 0


def test_optional_deep_timeout_publishes_partial_head_and_clears_watch_failure(
    tmp_path,
) -> None:
    database, session_id = _database_and_session(tmp_path)
    repository = database.model_ensemble_repository()
    context = _context(session_id)
    chunks = build_ensemble_chunks(context)
    metrics = coaching_ensemble_metric_specs()
    baseline_receipt = LocalProbabilisticMetricRunner(
        executor=lambda spec, stage, payload, device: _completed_result(payload),
        deep_enabled=False,
        clock=lambda: NOW,
    ).run(chunks, metrics)
    baseline = SessionModelEnsembleRunRecord(
        run_id="b" * 64,
        session_id=session_id,
        request_fingerprint="c" * 64,
        input_fingerprint="a" * 64,
        provider=Provider.CODEX,
        provider_version="synthetic-provider-v1",
        adapter_version="synthetic-adapter-v1",
        source_schema_version="synthetic-source-v1",
        content_schema_version="synthetic-content-v1",
        redactor_version="synthetic-redactor-v1",
        receipt=baseline_receipt,
    )
    repository.save_completed(baseline)

    timeout_receipt = LocalProbabilisticMetricRunner(
        executor=lambda spec, stage, payload, device: _uncertain_result(payload),
        deep_executor=lambda spec, stage, payload, device, quantization: {
            "status": "unavailable",
            "error_code": PROBABILISTIC_DEEP_TIMEOUT_ERROR_CODE,
        },
        device="cuda",
        clock=lambda: NOW + timedelta(seconds=2),
    ).run(chunks, metrics)
    timed_out = SessionModelEnsembleRunRecord(
        run_id="d" * 64,
        session_id=session_id,
        request_fingerprint="e" * 64,
        input_fingerprint="a" * 64,
        provider=Provider.CODEX,
        provider_version="synthetic-provider-v1",
        adapter_version="synthetic-adapter-v1",
        source_schema_version="synthetic-source-v1",
        content_schema_version="synthetic-content-v1",
        redactor_version="synthetic-redactor-v1",
        receipt=timeout_receipt,
    )
    repository.save_completed(timed_out)

    project_id = database.list_sessions(provider=Provider.CODEX, limit=1)[0][
        "project_id"
    ]
    watches = database.model_ensemble_watch_repository()
    watch_id = "9" * 64
    owner = "8" * 64
    watches.enable(
        watch_id=watch_id,
        provider=Provider.CODEX,
        project_id=project_id,
        session_id=session_id,
        max_messages=100,
        now=NOW,
    )
    claimed = watches.claim_due(
        owner=owner,
        now=NOW,
        lease_duration=timedelta(minutes=30),
    )
    assert claimed is not None
    _, lease = claimed
    watches.complete(
        lease,
        now=NOW + timedelta(seconds=1),
        next_check_at=NOW + timedelta(seconds=2),
        outcome=SessionModelEnsembleOutcome(run=baseline, applied=True),
    )
    assert watches.canonical_head(watch_id).head_run_id == baseline.run_id

    claimed = watches.claim_due(
        owner=owner,
        now=NOW + timedelta(seconds=2),
        lease_duration=timedelta(minutes=30),
    )
    assert claimed is not None
    _, lease = claimed
    in_flight = watches.canonical_head(watch_id)
    assert in_flight.head_run_id == baseline.run_id
    assert in_flight.latest_attempt is not None
    assert in_flight.latest_attempt.state is ModelEnsembleAttemptState.RUNNING
    assert in_flight.latest_attempt.prior_head_run_id == baseline.run_id

    watch = watches.complete(
        lease,
        now=NOW + timedelta(seconds=3),
        next_check_at=NOW + timedelta(seconds=63),
        outcome=SessionModelEnsembleOutcome(run=timed_out, applied=True),
    )
    assert watch.state is ModelEnsembleWatchState.IDLE
    assert watch.failure_streak == 0
    head = watches.canonical_head(watch_id)
    assert head.head_run_id == timed_out.run_id
    assert head.latest_attempt is not None
    assert head.latest_attempt.state is ModelEnsembleAttemptState.PARTIAL
    assert head.latest_attempt.published_run_id == timed_out.run_id
    assert head.latest_attempt.stage_count == 4
    assert head.latest_attempt.warning_count == 1
    assert len(head.stages) == 4
    assert head.stages[-1].state is ModelEnsembleStageState.UNAVAILABLE
    assert head.stages[-1].error_code == PROBABILISTIC_DEEP_TIMEOUT_ERROR_CODE
    assert tuple(
        point.run_id
        for point in watches.list_publications(
            watch_id,
            before_generation=None,
            limit=12,
        ).points
    ) == (timed_out.run_id, baseline.run_id)


def test_v39_preserves_v2_writes_v3_and_breaks_trajectory_comparability(
    tmp_path,
) -> None:
    assert SCHEMA_VERSION == 40
    assert LIVE_PROBABILISTIC_PLAN_VERSION == "small-factor-router-v5"
    assert PROBABILISTIC_MODEL_SET_VERSION == "local-factor-router-v3"

    database, session_id, project_id = _database_and_session_at_v38(tmp_path)
    runner = LocalProbabilisticMetricRunner(
        executor=lambda spec, stage, payload, device: _completed_result(payload),
        clock=lambda: NOW,
    )
    live_receipt = runner.run(
        build_ensemble_chunks(_context(session_id)),
        coaching_ensemble_metric_specs(),
    )
    live_projection = live_receipt.predictive_projection
    assert live_projection is not None
    assert live_projection.model_set_version == PROBABILISTIC_MODEL_SET_VERSION

    historical_metrics = tuple(
        SessionPredictiveMetricReceipt.model_validate(
            {
                **item.model_dump(),
                "model_set_version": PROBABILISTIC_MODEL_SET_VERSION_V2,
            }
        )
        for item in live_projection.metrics
    )
    historical_projection = SessionPredictiveMetricProjection.model_validate(
        {
            **live_projection.model_dump(exclude={"metrics"}),
            "model_set_version": PROBABILISTIC_MODEL_SET_VERSION_V2,
            "metrics": historical_metrics,
        }
    )
    historical_receipt = live_receipt.model_copy(
        update={"predictive_projection": historical_projection}
    )
    historical_record = SessionModelEnsembleRunRecord(
        run_id="b" * 64,
        session_id=session_id,
        request_fingerprint="c" * 64,
        input_fingerprint="a" * 64,
        provider=Provider.CODEX,
        provider_version="synthetic-provider-v1",
        adapter_version="synthetic-adapter-v1",
        source_schema_version="synthetic-source-v1",
        content_schema_version="synthetic-content-v1",
        redactor_version="synthetic-redactor-v1",
        receipt=historical_receipt,
    )
    legacy_runs = SqliteSessionModelEnsembleRepository(
        database._connection,  # noqa: SLF001 - deliberate pre-upgrade fixture
        lambda: None,
    )
    legacy_runs.save_completed(historical_record)

    with sqlite3.connect(database.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 38
        assert connection.execute(
            """SELECT DISTINCT model_set_version
               FROM session_model_ensemble_predictive_metrics"""
        ).fetchall() == [(PROBABILISTIC_MODEL_SET_VERSION_V2,)]
        assert connection.execute(
            """SELECT projection_fingerprint
               FROM session_model_ensemble_predictive_metric_seals
               WHERE run_id=?""",
            (historical_record.run_id,),
        ).fetchone()[0] == _predictive_projection_fingerprint(
            historical_projection
        )

    database.initialize()
    runs = database.model_ensemble_repository()
    loaded_historical = runs.get(historical_record.run_id)
    assert loaded_historical is not None
    assert loaded_historical.receipt.metric_publication_v2 is None
    assert loaded_historical.receipt.predictive_projection is not None
    assert (
        loaded_historical.receipt.predictive_projection.model_set_version
        == PROBABILISTIC_MODEL_SET_VERSION_V2
    )
    assert all(
        item.model_set_version == PROBABILISTIC_MODEL_SET_VERSION_V2
        for item in loaded_historical.receipt.predictive_projection.metrics
    )
    with sqlite3.connect(database.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM session_model_ensemble_metric_states_v2"
        ).fetchone()[0] == 0
        assert connection.execute(
            """SELECT COUNT(*)
               FROM session_model_ensemble_metric_publication_v2_seals"""
        ).fetchone()[0] == 0

    live_record = historical_record.model_copy(
        update={
            "run_id": "d" * 64,
            "request_fingerprint": "e" * 64,
            "receipt": live_receipt,
        }
    )
    runs.save_completed(live_record)

    # Bypass Pydantic deliberately to prove the database seal rejects a graph
    # whose seal claims v3 while its twenty metric rows still claim v2.
    mismatched_projection = historical_projection.model_copy(
        update={"model_set_version": PROBABILISTIC_MODEL_SET_VERSION}
    )
    mismatched_record = historical_record.model_copy(
        update={
            "run_id": "f" * 64,
            "request_fingerprint": "0" * 64,
            "receipt": live_receipt.model_copy(
                update={"predictive_projection": mismatched_projection}
            ),
        }
    )
    with pytest.raises(DatabaseError, match="local database operation failed"):
        runs.save_completed(mismatched_record)
    assert runs.get(mismatched_record.run_id) is None

    expected_triggers = {
        "session_model_ensemble_predictive_seal_complete",
        "session_model_ensemble_predictive_metrics_sealed_insert",
        "session_model_ensemble_predictive_factors_sealed_insert",
        "session_model_ensemble_predictive_density_sealed_insert",
        "session_model_ensemble_predictive_stages_sealed_insert",
        "session_model_ensemble_predictive_metrics_no_update",
        "session_model_ensemble_predictive_factors_no_update",
        "session_model_ensemble_predictive_density_no_update",
        "session_model_ensemble_predictive_stages_no_update",
        "session_model_ensemble_predictive_seals_no_update",
        "session_model_ensemble_predictive_metrics_privacy_delete_only",
        "session_model_ensemble_predictive_factors_privacy_delete_only",
        "session_model_ensemble_predictive_density_privacy_delete_only",
        "session_model_ensemble_predictive_stages_privacy_delete_only",
        "session_model_ensemble_predictive_seals_privacy_delete_only",
    }
    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 40
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version=39"
        ).fetchone()[0] == hashlib.sha256(
            migrations.MIGRATION_39.encode("utf-8")
        ).hexdigest()
        model_sets = connection.execute(
            """SELECT model_set_version,COUNT(*)
               FROM session_model_ensemble_predictive_metrics
               GROUP BY model_set_version ORDER BY model_set_version"""
        ).fetchall()
        assert model_sets == [
            (PROBABILISTIC_MODEL_SET_VERSION_V2, 20),
            (PROBABILISTIC_MODEL_SET_VERSION, 20),
        ]
        trigger_rows = connection.execute(
            """SELECT name,sql FROM sqlite_master
               WHERE type='trigger'
                 AND name LIKE 'session_model_ensemble_predictive_%'"""
        ).fetchall()
        assert {row[0] for row in trigger_rows} == expected_triggers
        assert all("_v39" not in row[1] for row in trigger_rows)
        assert connection.execute(
            """SELECT name FROM sqlite_master
               WHERE sql IS NOT NULL AND sql LIKE '%_v39%'"""
        ).fetchall() == []
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """UPDATE session_model_ensemble_predictive_model_stages
                   SET status=status WHERE run_id=?""",
                (live_record.run_id,),
            )

    watches = database.model_ensemble_watch_repository()
    watch_id = "9" * 64
    watches.enable(
        watch_id=watch_id,
        provider=Provider.CODEX,
        project_id=project_id,
        session_id=session_id,
        max_messages=100,
        now=NOW,
    )
    claimed = watches.claim_due(
        owner="8" * 64,
        now=NOW,
        lease_duration=timedelta(minutes=30),
    )
    assert claimed is not None
    _, lease = claimed
    watches.complete(
        lease,
        now=NOW + timedelta(seconds=1),
        next_check_at=NOW + timedelta(seconds=2),
        outcome=SessionModelEnsembleOutcome(run=historical_record, applied=True),
    )
    claimed = watches.claim_due(
        owner="8" * 64,
        now=NOW + timedelta(seconds=2),
        lease_duration=timedelta(minutes=30),
    )
    assert claimed is not None
    _, lease = claimed
    watches.complete(
        lease,
        now=NOW + timedelta(seconds=3),
        next_check_at=NOW + timedelta(seconds=60),
        outcome=SessionModelEnsembleOutcome(run=live_record, applied=True),
    )

    trajectory = watches.list_publications(
        watch_id,
        before_generation=None,
        limit=12,
    )
    assert tuple(point.run_id for point in trajectory.points) == (
        live_record.run_id,
        historical_record.run_id,
    )
    assert trajectory.points[0].comparable_to_head is True
    assert trajectory.points[1].comparable_to_head is False
    assert {
        item.model_set_version for item in trajectory.points[0].predictive_metrics
    } == {PROBABILISTIC_MODEL_SET_VERSION}
    assert {
        item.model_set_version for item in trajectory.points[1].predictive_metrics
    } == {PROBABILISTIC_MODEL_SET_VERSION_V2}
