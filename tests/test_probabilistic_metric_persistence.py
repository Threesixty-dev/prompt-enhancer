from __future__ import annotations

from datetime import UTC, datetime
import sqlite3

from fastapi.testclient import TestClient
import pytest
from pydantic import SecretStr

from prompt_enhancer.adapters.synthetic import SyntheticAdapter
from prompt_enhancer.application.analysis.coaching_baselines import (
    COACHING_METRIC_DEFINITIONS,
)
from prompt_enhancer.application.analysis.model_ensemble import (
    build_ensemble_chunks,
    coaching_ensemble_metric_specs,
)
from prompt_enhancer.application.analysis.probabilistic_metrics import (
    PROBABILISTIC_METRIC_PROJECTION_VERSION,
    PredictiveMetricState,
)
from prompt_enhancer.application.analysis.session_model_ensemble import (
    SessionModelEnsembleRunRecord,
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
from prompt_enhancer.database import Database
from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.config import AppSettings
from prompt_enhancer.domain import Provider
from prompt_enhancer.ingestion import IngestionService
from prompt_enhancer.infrastructure.text_models.probabilistic_metrics import (
    LocalProbabilisticMetricRunner,
)
from prompt_enhancer.privacy import Pseudonymizer


NOW = datetime(2042, 4, 5, 12, 0, tzinfo=UTC)
TOKEN = "example_probabilistic_metric_token_1234567890"


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


def _completed_result(payload):
    return {
        "status": "completed",
        "device": "cuda",
        "rows": [
            {
                "case_id": item["case_id"],
                "entailment": 0.64,
                "neutral": 0.24,
                "contradiction": 0.12,
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
    loaded = repository.get(record.run_id)

    assert loaded is not None
    assert loaded.receipt.predictive_projection == receipt.predictive_projection
    assert loaded.receipt.predictive_projection is not None
    assert len(loaded.receipt.predictive_projection.metrics) == 20
    assert all(
        item.state is PredictiveMetricState.EXPERIMENTAL
        for item in loaded.receipt.predictive_projection.metrics
    )
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
        assert counts["session_model_ensemble_predictive_density_bins"] == 400
        assert counts["session_model_ensemble_predictive_model_stages"] == 5
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
