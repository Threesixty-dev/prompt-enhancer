from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterator

from fastapi.testclient import TestClient
from pydantic import SecretStr

from prompt_enhancer.adapters.synthetic import SyntheticAdapter
from prompt_enhancer.application.analysis.deterministic import DEFAULT_METRIC_PACK
from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.config import AppSettings
from prompt_enhancer.database import Database
from prompt_enhancer.domain import (
    DataTier,
    EventKind,
    Provider,
    SourceEvent,
    SourceSession,
    UsageCounterKind,
    UsageRecord,
    UsageScope,
)
from prompt_enhancer.ingestion import IngestionService
from prompt_enhancer.privacy import Pseudonymizer

EXAMPLE_API_TOKEN = "example_local_api_token_do_not_use_123456789"


class SyntheticMissingTotalAdapter(SyntheticAdapter):
    """Content-free fixture with observed input/output but unknown total usage."""

    def read_events(self, session: SourceSession) -> Iterator[SourceEvent]:
        yield from super().read_events(session)
        if (
            session.source_session_id.get_secret_value()
            == "example-session-interrupted"
        ):
            yield SourceEvent(
                source_event_id=SecretStr("example-usage-without-total"),
                kind=EventKind.USAGE,
                sequence=3,
                occurred_at=session.ended_at
                or datetime(2026, 1, 15, 10, 3, tzinfo=UTC),
                usage=UsageRecord(
                    input_tokens=20,
                    output_tokens=5,
                    total_tokens=None,
                    counter_kind=UsageCounterKind.DELTA,
                    scope=UsageScope.TURN,
                ),
            )


def _ingested_database(tmp_path) -> Database:
    database = Database(tmp_path / "metrics.sqlite3")
    database.initialize()
    IngestionService(database, Pseudonymizer(bytes(range(32)))).ingest(
        SyntheticAdapter()
    )
    return database


def test_database_preserves_unknown_metric_values_and_coverage(tmp_path) -> None:
    database = _ingested_database(tmp_path)
    interrupted = next(
        record
        for record in database.list_sessions()
        if record["terminal_state"] == "interrupted"
    )
    metrics = {
        record["key"]: record
        for record in database.get_session_metrics(interrupted["session_id"])
    }

    duration = metrics["efficiency.observed_tool_duration_ms"]
    tokens = metrics["usage.total_tokens"]

    assert duration["numeric_value"] is None
    assert duration["observed_count"] == 0
    assert duration["eligible_count"] == 1
    assert duration["coverage"] == 0
    assert tokens["numeric_value"] is None
    assert tokens["observed_count"] == 0
    assert tokens["coverage"] == 0


def test_unknown_token_metric_survives_real_session_metrics_http_route(tmp_path) -> None:
    database = Database(tmp_path / "metrics.sqlite3")
    database.initialize()
    IngestionService(database, Pseudonymizer(bytes(range(32)))).ingest(
        SyntheticMissingTotalAdapter()
    )
    interrupted = next(
        record
        for record in database.list_sessions()
        if record["terminal_state"] == "interrupted"
    )
    app = create_app(
        settings=AppSettings(home=tmp_path),
        database=database,
        api_token=EXAMPLE_API_TOKEN,
    )

    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get(
            f"/v1/sessions/{interrupted['session_id']}/metrics",
            headers={API_TOKEN_HEADER: EXAMPLE_API_TOKEN},
        )

    assert response.status_code == 200
    assert response.json()["session_id"] == interrupted["session_id"]
    token_metric = next(
        metric
        for metric in response.json()["metrics"]
        if metric["key"] == "usage.total_tokens"
    )
    assert token_metric["numeric_value"] is None
    assert token_metric["text_value"] is None
    assert token_metric["observed_count"] == 0
    assert token_metric["eligible_count"] == 1
    assert token_metric["coverage"] == 0
    assert token_metric["confidence"] is None
    assert token_metric["metric_pack_key"] == DEFAULT_METRIC_PACK.key
    assert token_metric["metric_pack_version"] == DEFAULT_METRIC_PACK.version
    assert token_metric["metric_engine_version"]


def test_consent_grant_is_explicit_and_revocable(tmp_path) -> None:
    database = Database(tmp_path / "metrics.sqlite3")
    database.initialize()

    assert database.has_active_consent(Provider.CODEX, DataTier.METADATA) is False
    database.grant_consent(Provider.CODEX, DataTier.METADATA)
    assert database.has_active_consent(Provider.CODEX, DataTier.METADATA) is True
    database.revoke_consent(Provider.CODEX, DataTier.METADATA)
    assert database.has_active_consent(Provider.CODEX, DataTier.METADATA) is False


def test_metric_rows_record_definition_and_analysis_provenance(tmp_path) -> None:
    database = _ingested_database(tmp_path)
    session_id = database.list_sessions(limit=1)[0]["session_id"]
    metrics = database.get_session_metrics(session_id)

    required = {
        "version",
        "source",
        "metric_pack_key",
        "metric_pack_version",
        "metric_engine_version",
        "redactor_version",
        "model_id",
        "model_revision",
        "tokenizer_id",
        "prompt_version",
        "rubric_version",
    }
    assert metrics
    assert all(required <= record.keys() for record in metrics)
    assert all(record["metric_engine_version"] for record in metrics)
    assert all(record["redactor_version"] for record in metrics)
    assert {
        (record["metric_pack_key"], record["metric_pack_version"])
        for record in metrics
    } == {(DEFAULT_METRIC_PACK.key, DEFAULT_METRIC_PACK.version)}
