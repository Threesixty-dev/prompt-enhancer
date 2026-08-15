from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.application.analysis.model_ensemble import (
    MODEL_ENSEMBLE_MODEL_COUNT,
    ModelExpertRole,
)
from prompt_enhancer.application.analysis.session_model_ensemble import (
    MODEL_ENSEMBLE_CONFIRMATION,
    ModelEnsembleConsentError,
    ModelEnsembleExecutionError,
    SessionModelEnsembleRunRecord,
    SessionModelEnsembleService,
)
from prompt_enhancer.application.analysis.text_analysis_presets import (
    COACHING_PROFILE_V1,
)
from prompt_enhancer.application.analysis.text_contracts import (
    EphemeralRedactedMessage,
    P1TextAnalysisInput,
    TextLanguage,
    TextMessageKind,
    TextRole,
)
from prompt_enhancer.application.analysis.text_source import TextAnalysisPurpose
from prompt_enhancer.config import AppSettings
from prompt_enhancer.database import Database
from prompt_enhancer.domain import DataTier, Provider
from prompt_enhancer.infrastructure.text_models.model_ensemble import (
    SerialModelEnsembleRunner,
)


SESSION_ID = "a" * 64
WINDOW_ID = "b" * 64
TOKEN = "example_model_ensemble_api_token_1234567890"


def _id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _context() -> P1TextAnalysisInput:
    messages = (
        EphemeralRedactedMessage(
            message_id=_id("fictional-request"),
            sequence=0,
            role=TextRole.USER,
            kind=TextMessageKind.REQUEST,
            language=TextLanguage.ENGLISH,
            text=SecretStr(
                "Build a fictional loopback dashboard with explicit tests and boundaries."
            ),
        ),
        EphemeralRedactedMessage(
            message_id=_id("fictional-response"),
            sequence=1,
            role=TextRole.AGENT,
            kind=TextMessageKind.RESPONSE,
            language=TextLanguage.ENGLISH,
            text=SecretStr(
                "Implemented the fictional dashboard and ran the synthetic checks."
            ),
        ),
    )
    return P1TextAnalysisInput(
        provider=Provider.CODEX,
        session_id=SESSION_ID,
        provider_version="example-provider-v1",
        adapter_version="example-adapter-v1",
        source_schema_version="example-source-v1",
        content_schema_version="example-content-v1",
        redactor_version="example-redactor-v1",
        text_extraction_complete=True,
        available_message_kinds=frozenset(
            {TextMessageKind.REQUEST, TextMessageKind.RESPONSE}
        ),
        analysis_window_fingerprint=WINDOW_ID,
        focus_message_id=messages[0].message_id,
        observed_message_count=2,
        eligible_message_count=2,
        messages=messages,
        task_profile=COACHING_PROFILE_V1.task_profile,
    )


class _Policy:
    consent = True

    def has_active_consent(self, provider: Provider, tier: DataTier) -> bool:
        return self.consent and provider is Provider.CODEX and tier is DataTier.REDACTED_CONTENT

    def selection_is_indexed(
        self,
        provider: Provider,
        *,
        project_ids: frozenset[str],
        session_ids: frozenset[str],
    ) -> bool:
        return provider is Provider.CODEX and not project_ids and session_ids == {SESSION_ID}


class _Compatibility:
    def require_compatible(self, provider: str) -> object:
        if provider != "codex":
            raise ValueError("unsupported")
        return object()


class _Identifiers:
    def fingerprint(self, namespace: str, values: tuple[str, ...]) -> str:
        return _id("\x1f".join((namespace, *values)))


class _Source:
    provider = Provider.CODEX
    purpose = TextAnalysisPurpose.TEXT_ANALYSIS
    read_only = True
    requires_explicit_selection = True

    def __init__(self) -> None:
        self.read_count = 0

    def read(self, *, selection, grant, task_profile):
        self.read_count += 1
        assert selection.session_id == SESSION_ID
        assert selection.max_messages == 100
        assert selection.max_characters == 100_000
        assert grant.local_only and not grant.content_persistence_allowed
        assert task_profile == COACHING_PROFILE_V1.task_profile
        return _context()


class _Repository:
    def __init__(self) -> None:
        self.items: dict[str, SessionModelEnsembleRunRecord] = {}

    def save_completed(self, run: SessionModelEnsembleRunRecord) -> None:
        if run.run_id in self.items:
            raise ValueError("duplicate")
        self.items[run.run_id] = run

    def get(self, run_id: str):
        return self.items.get(run_id)

    def get_latest(self, session_id: str):
        rows = [value for value in self.items.values() if value.session_id == session_id]
        return max(rows, key=lambda item: item.receipt.completed_at) if rows else None

    def delete_for_privacy(self, run_id: str) -> bool:
        return self.items.pop(run_id, None) is not None


def _execute(spec, stage, payload, device):  # type: ignore[no-untyped-def]
    rows = []
    for case in payload["cases"]:
        if stage in {"retrieval", "reranking"}:
            rows.append(
                {
                    "case_id": case["case_id"],
                    "scores": [
                        {"fragment_id": fragment_id, "score": 1.0 / (index + 1)}
                        for index, fragment_id in enumerate(case["candidate_ids"])
                    ],
                }
            )
        elif stage == ModelExpertRole.SCOPE_NLI.value:
            rows.append(
                {
                    "case_id": case["case_id"],
                    "entailment": 0.9,
                    "neutral": 0.05,
                    "contradiction": 0.05,
                }
            )
        else:
            rows.append({"case_id": case["case_id"], "label": "present"})
    return {
        "schema_version": 1,
        "model_key": spec.identity.model_key,
        "status": "completed",
        "error_code": None,
        "device": "cpu",
        "rows": rows,
        "runtime": {
            "inference_latency_ms": 1.0,
            "peak_cuda_allocated_mb": 0.0,
            "process_rss_after_load_and_inference_mb": 100.0,
        },
    }


def _service(policy: _Policy | None = None):
    source = _Source()
    repository = _Repository()
    service = SessionModelEnsembleService(
        policy or _Policy(),
        repository,
        lambda provider: source,
        _Compatibility(),
        _Identifiers(),
        SerialModelEnsembleRunner(executor=_execute, device="cpu"),
    )
    return service, source, repository


def test_service_runs_all_ten_models_once_and_idempotently_stores_no_text() -> None:
    service, source, repository = _service()
    request = {
        "provider": Provider.CODEX,
        "session_id": SESSION_ID,
        "confirmation": MODEL_ENSEMBLE_CONFIRMATION,
        "idempotency_key": "example-model-ensemble-0001",
    }

    first = service.run(**request)
    second = service.run(**request)

    assert first.applied is True
    assert second.applied is False
    assert source.read_count == 1
    assert len(first.run.receipt.experts) == MODEL_ENSEMBLE_MODEL_COUNT
    assert len(first.run.receipt.metrics) == 20
    assert len(first.run.receipt.model_votes) == first.run.receipt.chunk_count * 20 * 4
    assert all(item.unloaded_after_stage for item in first.run.receipt.experts)
    assert repository.get(first.run.run_id) is not None
    serialized = first.model_dump_json()
    assert "fictional" not in serialized.lower()
    assert '"content_persisted":false' in serialized
    assert '"product_metric_eligible":false' in serialized


def test_consent_fails_before_the_local_source_or_models() -> None:
    policy = _Policy()
    policy.consent = False
    service, source, repository = _service(policy)

    with pytest.raises(ModelEnsembleConsentError):
        service.run(
            provider=Provider.CODEX,
            session_id=SESSION_ID,
            confirmation=MODEL_ENSEMBLE_CONFIRMATION,
            idempotency_key="example-model-ensemble-0002",
        )

    assert source.read_count == 0
    assert repository.items == {}


def test_private_api_returns_only_content_free_shadow_receipts(tmp_path) -> None:
    service, source, _ = _service()
    database = Database(tmp_path / "metrics.sqlite3")
    database.initialize()
    app = create_app(
        settings=AppSettings(home=tmp_path),
        database=database,
        api_token=TOKEN,
        session_model_ensemble_service=service,
    )
    path = f"/v1/sessions/{SESSION_ID}/model-ensemble-runs"
    headers = {
        API_TOKEN_HEADER: TOKEN,
        "Idempotency-Key": "example-model-ensemble-0003",
    }

    with TestClient(app, base_url="http://127.0.0.1") as client:
        unauthorized = client.post(
            path,
            json={"confirmation": MODEL_ENSEMBLE_CONFIRMATION},
            headers={"Idempotency-Key": "example-model-ensemble-0003"},
        )
        rejected = client.post(
            path,
            json={
                "confirmation": MODEL_ENSEMBLE_CONFIRMATION,
                "transcript": "SYNTHETIC_PRIVATE_CANARY",
            },
            headers=headers,
        )
        response = client.post(
            path,
            json={"confirmation": MODEL_ENSEMBLE_CONFIRMATION},
            headers=headers,
        )
        latest = client.get(f"{path}/latest", headers={API_TOKEN_HEADER: TOKEN})

    assert unauthorized.status_code == 401
    assert rejected.status_code == 422
    assert rejected.json() == {"detail": "request validation failed"}
    assert response.status_code == latest.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    payload = response.json()["run"]
    assert payload["model_count"] == 10
    assert len(payload["experts"]) == 10
    assert payload["content_persisted"] is False
    assert payload["product_metric_eligible"] is False
    assert "source_window_fingerprint" not in response.text
    assert "fragment_id" not in response.text
    assert "SYNTHETIC_PRIVATE_CANARY" not in response.text
    assert source.read_count == 1


@dataclass
class _FailingService:
    def run(self, **values):
        raise ModelEnsembleExecutionError("SYNTHETIC_PRIVATE_CANARY")

    def latest(self, session_id: str):
        return None


def test_api_discards_model_exception_details(tmp_path) -> None:
    database = Database(tmp_path / "metrics.sqlite3")
    database.initialize()
    app = create_app(
        settings=AppSettings(home=tmp_path),
        database=database,
        api_token=TOKEN,
        session_model_ensemble_service=_FailingService(),  # type: ignore[arg-type]
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post(
            f"/v1/sessions/{SESSION_ID}/model-ensemble-runs",
            json={"confirmation": MODEL_ENSEMBLE_CONFIRMATION},
            headers={
                API_TOKEN_HEADER: TOKEN,
                "Idempotency-Key": "example-model-ensemble-0004",
            },
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "local_model_ensemble_execution_failed",
            "message": "local model ensemble execution failed",
        }
    }
    assert "SYNTHETIC_PRIVATE_CANARY" not in response.text
