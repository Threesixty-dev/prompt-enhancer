from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.application.analysis.model_ensemble import (
    MODEL_ENSEMBLE_MODEL_COUNT,
    ModelExpertRole,
)
from prompt_enhancer.application.analysis.evidence_contracts import (
    EphemeralTypedEvidenceProjection,
    TypedEvidenceKind,
    TypedEvidenceOpportunityKind,
    TypedEvidenceProvenance,
    VerificationEvidence,
    VerificationMethod,
    VerificationOutcome,
)
from prompt_enhancer.application.providers import (
    CapabilityKey,
    DecoderDescriptor,
    ProviderIdentity,
    ProviderSurface,
    SchemaArtifactKind,
    SchemaArtifactProvenance,
)
from prompt_enhancer.application.analysis.session_model_ensemble import (
    MODEL_ENSEMBLE_CONFIRMATION,
    ModelEnsembleConsentError,
    ModelEnsembleExecutionError,
    SessionModelEnsembleRunRecord,
    SessionModelEnsembleService,
)
from prompt_enhancer.application.analysis.semantic_units import SemanticUnitReconciler
from prompt_enhancer.application.analysis.model_ensemble_watch import (
    MODEL_ENSEMBLE_WATCH_CONFIRMATION,
    MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL,
    ModelEnsembleWatchLease,
    ModelEnsembleCanonicalHead,
    ModelEnsembleWatchRecord,
    ModelEnsembleWatchService,
    ModelEnsembleWatchState,
    ModelEnsembleTrajectoryPage,
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
    MODEL_ENSEMBLE_RUNNER_SCHEMA_VERSION,
    SerialModelEnsembleRunner,
)
from prompt_enhancer.infrastructure.text_models.probabilistic_metrics import (
    LocalProbabilisticMetricRunner,
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

    def fingerprint_secret(
        self,
        namespace: str,
        values: tuple[str, ...],
        secret: SecretStr,
    ) -> str:
        return _id(
            "\x1f".join((namespace, *values, secret.get_secret_value()))
        )


class _Source:
    provider = Provider.CODEX
    purpose = TextAnalysisPurpose.TEXT_ANALYSIS
    read_only = True
    requires_explicit_selection = True

    def __init__(self) -> None:
        self.read_count = 0
        self.message_limits: list[int] = []

    def read(self, *, selection, grant, task_profile):
        self.read_count += 1
        self.message_limits.append(selection.max_messages)
        assert selection.session_id == SESSION_ID
        assert 1 <= selection.max_messages <= 100
        assert selection.max_characters == 100_000
        assert grant.local_only and not grant.content_persistence_allowed
        assert task_profile == COACHING_PROFILE_V1.task_profile
        return _context()


class _Repository:
    def __init__(self) -> None:
        self.items: dict[str, SessionModelEnsembleRunRecord] = {}
        self.semantic_units = {}

    def save_completed(self, run: SessionModelEnsembleRunRecord, **_values) -> None:  # type: ignore[no-untyped-def]
        if run.run_id in self.items:
            raise ValueError("duplicate")
        self.items[run.run_id] = run
        if _values.get("semantic_units") is not None:
            self.semantic_units[run.run_id] = _values["semantic_units"]

    def get(self, run_id: str):
        return self.items.get(run_id)

    def get_latest(self, session_id: str):
        rows = [value for value in self.items.values() if value.session_id == session_id]
        return max(rows, key=lambda item: item.receipt.completed_at) if rows else None

    def save_metric_projection(self, run: SessionModelEnsembleRunRecord, **_values) -> None:  # type: ignore[no-untyped-def]
        if run.run_id not in self.items:
            raise ValueError("missing")
        self.items[run.run_id] = run

    def get_semantic_unit_reconciliation(self, run_id: str):  # type: ignore[no-untyped-def]
        return self.semantic_units.get(run_id)

    def delete_for_privacy(self, run_id: str) -> bool:
        return self.items.pop(run_id, None) is not None


class _WatchRepository:
    def __init__(self) -> None:
        self.record: ModelEnsembleWatchRecord | None = None

    def enable(self, *, watch_id, provider, project_id, session_id, max_messages=100, now):  # type: ignore[no-untyped-def]
        self.record = ModelEnsembleWatchRecord(
            watch_id=watch_id,
            provider=provider,
            project_id=project_id,
            session_id=session_id,
            max_messages=max_messages,
            state=ModelEnsembleWatchState.QUEUED,
            generation=0,
            progress_completed=0,
            progress_total=MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL,
            next_check_at=now,
            created_at=now,
            updated_at=now,
        )
        return self.record

    def disable(self, watch_id, *, now):  # type: ignore[no-untyped-def]
        if self.record is None or self.record.watch_id != watch_id:
            raise ValueError("missing")
        self.record = self.record.model_copy(
            update={"state": ModelEnsembleWatchState.DISABLED, "updated_at": now}
        )
        return self.record

    def get(self, watch_id):  # type: ignore[no-untyped-def]
        return self.record if self.record is not None and self.record.watch_id == watch_id else None

    def get_active(self):  # type: ignore[no-untyped-def]
        if self.record is None or self.record.state is ModelEnsembleWatchState.DISABLED:
            return None
        return self.record

    def get_for_session(self, session_id):  # type: ignore[no-untyped-def]
        if self.record is None or self.record.session_id != session_id:
            return None
        return self.record

    def canonical_head(self, watch_id):  # type: ignore[no-untyped-def]
        if self.record is None or self.record.watch_id != watch_id:
            raise ValueError("missing")
        return ModelEnsembleCanonicalHead(
            watch=self.record,
            head_run_id=self.record.latest_run_id,
            head_generation=(
                None if self.record.latest_run_id is None else self.record.generation
            ),
        )

    def get_attempt(self, attempt_id):  # type: ignore[no-untyped-def]
        return None

    def get_attempt_stages(self, attempt_id):  # type: ignore[no-untyped-def]
        return ()

    def get_attempt_snapshot(self, attempt_id):  # type: ignore[no-untyped-def]
        return None

    def list_attempts(self, watch_id, *, limit):  # type: ignore[no-untyped-def]
        assert self.record is not None and self.record.watch_id == watch_id
        assert 1 <= limit <= 60
        return ()

    def request_refresh(self, watch_id, *, now):  # type: ignore[no-untyped-def]
        if (
            self.record is None
            or self.record.watch_id != watch_id
            or self.record.state is ModelEnsembleWatchState.DISABLED
        ):
            raise ValueError("missing")
        self.record = self.record.model_copy(
            update={"next_check_at": now, "updated_at": now}
        )
        return self.record

    def list_publications(self, watch_id, *, before_generation, limit):  # type: ignore[no-untyped-def]
        if self.record is None or self.record.watch_id != watch_id:
            raise ValueError("missing")
        assert before_generation is None
        assert 1 <= limit <= 60
        return ModelEnsembleTrajectoryPage(
            watch_id=watch_id,
            head_run_id=None,
            head_generation=None,
            points=(),
            next_before_generation=None,
        )

    def claim_due(self, **_values):  # type: ignore[no-untyped-def]
        if self.record is None or self.record.state not in {
            ModelEnsembleWatchState.QUEUED,
            ModelEnsembleWatchState.IDLE,
            ModelEnsembleWatchState.FAILED,
        }:
            return None
        now = _values["now"]
        duration = _values["lease_duration"]
        lease = ModelEnsembleWatchLease(
            watch_id=self.record.watch_id,
            owner=_values["owner"],
            token="e" * 64,
            expires_at=now + duration,
        )
        self.record = self.record.model_copy(
            update={
                "state": ModelEnsembleWatchState.RUNNING,
                "generation": self.record.generation + 1,
                "progress_completed": 0,
                "lease_owner": lease.owner,
                "lease_token": lease.token,
                "lease_expires_at": lease.expires_at,
                "updated_at": now,
            }
        )
        return self.record, lease

    def heartbeat(self, lease: ModelEnsembleWatchLease, **_values):  # type: ignore[no-untyped-def]
        assert self.record is not None and self.record.lease_token == lease.token
        expires_at = _values["now"] + _values["lease_duration"]
        renewed = lease.model_copy(update={"expires_at": expires_at})
        self.record = self.record.model_copy(
            update={
                "progress_completed": _values["progress_completed"],
                "lease_expires_at": expires_at,
                "updated_at": _values["now"],
            }
        )
        return self.record, renewed

    def complete(self, lease: ModelEnsembleWatchLease, **_values):  # type: ignore[no-untyped-def]
        assert self.record is not None and self.record.lease_token == lease.token
        run = _values["outcome"].run
        self.record = self.record.model_copy(
            update={
                "state": ModelEnsembleWatchState.IDLE,
                "progress_completed": MODEL_ENSEMBLE_WATCH_PROGRESS_TOTAL,
                "latest_run_id": run.run_id,
                "latest_input_fingerprint": run.input_fingerprint,
                "last_error_code": None,
                "next_check_at": _values["next_check_at"],
                "lease_owner": None,
                "lease_token": None,
                "lease_expires_at": None,
                "updated_at": _values["now"],
            }
        )
        return self.record

    def fail(self, lease: ModelEnsembleWatchLease, **_values):  # type: ignore[no-untyped-def]
        raise AssertionError("not used")


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
        "schema_version": MODEL_ENSEMBLE_RUNNER_SCHEMA_VERSION,
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


def _service(
    policy: _Policy | None = None,
    *,
    with_semantic_units: bool = False,
):
    source = _Source()
    repository = _Repository()
    service = SessionModelEnsembleService(
        policy or _Policy(),
        repository,
        lambda provider: source,
        _Compatibility(),
        _Identifiers(),
        SerialModelEnsembleRunner(executor=_execute, device="cpu"),
        semantic_unit_reconciler=(
            SemanticUnitReconciler(_Identifiers())
            if with_semantic_units
            else None
        ),
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
    assert len(first.run.receipt.typed_metrics) == 20
    assert first.run.receipt.metric_projection_version == "coaching-typed-projection-v1"
    assert sum(
        item.value_state.value == "known"
        for item in first.run.receipt.typed_metrics
    ) >= 1
    typed_by_key = {
        item.metric_key: item for item in first.run.receipt.typed_metrics
    }
    assert all(
        typed_by_key[key].value_state.value == "unknown"
        for key in (
            "logic.hypothesis_test_linkage",
            "logic.requirement_action_traceability",
            "outcome.agent_claim_grounding",
            "outcome.first_pass_verification",
            "outcome.verified_requirement_coverage",
        )
    )
    assert len(first.run.receipt.model_votes) == first.run.receipt.chunk_count * 20 * 4
    assert all(item.unloaded_after_stage for item in first.run.receipt.experts)
    assert repository.get(first.run.run_id) is not None
    serialized = first.model_dump_json()
    assert "fictional" not in serialized.lower()
    assert '"content_persisted":false' in serialized
    assert '"product_metric_eligible":false' in serialized


def test_service_atomically_persists_content_free_semantic_unit_heads() -> None:
    service, _source, repository = _service(with_semantic_units=True)

    outcome = service.run(
        provider=Provider.CODEX,
        session_id=SESSION_ID,
        confirmation=MODEL_ENSEMBLE_CONFIRMATION,
        idempotency_key="example-semantic-unit-run-0001",
    )

    reconciliation = repository.get_semantic_unit_reconciliation(
        outcome.run.run_id
    )
    assert reconciliation is not None
    assert reconciliation.session_id == SESSION_ID
    assert len(reconciliation.heads) == 1
    assert reconciliation.heads[0].kind.value == "request_revision"
    serialized = reconciliation.model_dump_json()
    assert "fictional" not in serialized.lower()


def test_typed_provider_verification_updates_only_the_measured_evidence_lane() -> None:
    class _EvidenceProjector:
        descriptor = DecoderDescriptor(
            provider=ProviderIdentity(key="codex"),
            surface=ProviderSurface.OPERATIONAL_EVENTS,
            adapter_version="example-adapter-v1",
            decoder_key="example-events",
            decoder_version="1",
            wire_schema_family="example-events-v1",
            canonical_schema_version="example-source-v1",
            schema_artifact=SchemaArtifactProvenance(
                artifact_key="example-events",
                artifact_version="1",
                kind=SchemaArtifactKind.SYNTHETIC,
            ),
            capabilities=(CapabilityKey.VERIFICATION_EVENTS,),
        )

        def project(self, *, provider, session_id):  # type: ignore[no-untyped-def]
            assert provider is Provider.CODEX and session_id == SESSION_ID
            task_id = _id("typed-verification-task")
            return EphemeralTypedEvidenceProjection(
                session_id=SESSION_ID,
                provenance=TypedEvidenceProvenance(
                    provider=Provider.CODEX,
                    provider_version="example-provider-v1",
                    adapter_version="example-adapter-v1",
                    decoder_key="example-events",
                    decoder_version="1",
                    source_schema_version="example-source-v1",
                    extraction_complete=True,
                ),
                declared_kinds=frozenset({TypedEvidenceKind.VERIFICATION}),
                declared_opportunity_kinds=frozenset(
                    {TypedEvidenceOpportunityKind.VERIFICATION_TASK}
                ),
                eligible_verification_task_reference_ids=(task_id,),
                records=(
                    VerificationEvidence(
                        evidence_id=_id("typed-verification"),
                        sequence=0,
                        source_reference_id=_id("typed-source"),
                        method=VerificationMethod.TEST,
                        outcome=VerificationOutcome.PASSED,
                        receipt_reference_ids=(_id("typed-receipt"),),
                        verification_task_reference_ids=(task_id,),
                    ),
                ),
            )

    source = _Source()
    repository = _Repository()
    service = SessionModelEnsembleService(
        _Policy(),
        repository,
        lambda provider: source,
        _Compatibility(),
        _Identifiers(),
        LocalProbabilisticMetricRunner(
            executor=_execute,
            device="cpu",
            deep_enabled=False,
        ),
        typed_evidence_projector=_EvidenceProjector(),
    )

    outcome = service.run(
        provider=Provider.CODEX,
        session_id=SESSION_ID,
        confirmation=MODEL_ENSEMBLE_CONFIRMATION,
        idempotency_key="example-objective-evidence-0001",
    )
    measured = next(
        item
        for item in outcome.run.receipt.typed_metrics
        if item.metric_key == "outcome.first_pass_verification"
    )
    predicted = next(
        item
        for item in outcome.run.receipt.predictive_projection.metrics
        if item.metric_key == "outcome.first_pass_verification"
    )
    assert (measured.value_state.value, measured.numerator, measured.denominator) == (
        "known",
        1,
        1,
    )
    assert measured.explanation_code == "typed_first_verification_outcomes"
    assert measured.algorithm_id == "typed-objective-evidence"
    assert measured.engine_version == "typed-objective-evidence-v2"
    assert measured.observed_message_count == measured.eligible_message_count == 1
    assert measured.coverage == 1.0
    assert predicted.state.value == "unavailable"
    assert predicted.mean is None and predicted.density_bins == ()


def test_unchanged_legacy_head_gets_typed_projection_without_a_new_model_run() -> None:
    service, source, repository = _service()
    first = service.run(
        provider=Provider.CODEX,
        session_id=SESSION_ID,
        confirmation=MODEL_ENSEMBLE_CONFIRMATION,
        idempotency_key="example-model-ensemble-legacy-0001",
    )
    legacy_receipt = first.run.receipt.model_copy(
        update={
            "metric_projection_version": None,
            "metric_projection_completed_at": None,
            "typed_metrics": (),
        }
    )
    repository.items[first.run.run_id] = first.run.model_copy(
        update={"receipt": legacy_receipt}
    )

    upgraded = service.run(
        provider=Provider.CODEX,
        session_id=SESSION_ID,
        confirmation=MODEL_ENSEMBLE_CONFIRMATION,
        idempotency_key="example-model-ensemble-legacy-0002",
        reuse_latest=True,
        prior_run_id=first.run.run_id,
    )

    assert upgraded.applied is False
    assert upgraded.run.run_id == first.run.run_id
    assert len(upgraded.run.receipt.typed_metrics) == 20
    assert source.read_count == 2


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


def test_private_watch_api_enables_without_reading_and_can_be_disabled(tmp_path) -> None:
    ensemble, source, _ = _service()
    watch_repository = _WatchRepository()
    watch = ModelEnsembleWatchService(
        watch_repository,
        ensemble,
        clock=lambda: datetime(2040, 1, 2, 3, 4, tzinfo=UTC),
        poll_interval=timedelta(seconds=60),
    )
    database = Database(tmp_path / "metrics.sqlite3")
    database.initialize()
    app = create_app(
        settings=AppSettings(home=tmp_path),
        database=database,
        api_token=TOKEN,
        session_model_ensemble_service=ensemble,
        model_ensemble_watch_service=watch,
    )
    headers = {API_TOKEN_HEADER: TOKEN}
    path = f"/v1/sessions/{SESSION_ID}/model-ensemble-watch"

    with TestClient(app, base_url="http://127.0.0.1") as client:
        missing_session_head = client.get(
            f"/v2/sessions/{SESSION_ID}/model-ensemble-head", headers=headers
        )
        unauthorized = client.put(
            path,
            json={
                "project_id": "c" * 64,
                "max_messages": 25,
                "confirmation": MODEL_ENSEMBLE_WATCH_CONFIRMATION,
            },
        )
        rejected = client.put(
            path,
            headers=headers,
            json={
                "project_id": "c" * 64,
                "confirmation": MODEL_ENSEMBLE_WATCH_CONFIRMATION,
                "transcript": "SYNTHETIC_PRIVATE_CANARY",
            },
        )
        enabled = client.put(
            path,
            headers=headers,
            json={
                "project_id": "c" * 64,
                "max_messages": 25,
                "confirmation": MODEL_ENSEMBLE_WATCH_CONFIRMATION,
            },
        )
        active = client.get("/v1/model-ensemble-watch/active", headers=headers)
        watch_id = enabled.json()["watch"]["watch_id"]
        canonical = client.get(
            "/v2/model-ensemble-watch/active/head", headers=headers
        )
        session_canonical = client.get(
            f"/v2/sessions/{SESSION_ID}/model-ensemble-head", headers=headers
        )
        attempts = client.get(
            f"/v2/model-ensemble-watches/{watch_id}/attempts", headers=headers
        )
        trajectory = client.get(
            f"/v1/model-ensemble-watches/{watch_id}/trajectory?limit=12",
            headers=headers,
        )
        refreshed = client.post(
            f"/v1/model-ensemble-watches/{watch_id}/refresh",
            headers=headers,
        )
        disabled = client.delete(
            f"/v1/model-ensemble-watches/{watch_id}", headers=headers
        )

    assert unauthorized.status_code == 401
    assert missing_session_head.status_code == 404
    assert missing_session_head.headers["cache-control"] == "no-store, private"
    assert missing_session_head.headers["pragma"] == "no-cache"
    assert rejected.status_code == 422
    assert rejected.json() == {"detail": "request validation failed"}
    assert (
        enabled.status_code
        == active.status_code
        == trajectory.status_code
        == refreshed.status_code
        == disabled.status_code
        == canonical.status_code
        == session_canonical.status_code
        == attempts.status_code
        == 200
    )
    assert enabled.headers["cache-control"] == "no-store, private"
    assert enabled.headers["pragma"] == "no-cache"
    assert enabled.json()["watch"]["state"] == "queued"
    assert enabled.json()["watch"]["max_messages"] == 25
    assert enabled.json()["latest_run"] is None
    assert active.json() == enabled.json()
    assert canonical.json()["schema_version"] == "analysis-snapshot-v2"
    assert canonical.json()["head_run_id"] is None
    assert canonical.json()["latest_attempt"] is None
    assert session_canonical.json() == canonical.json()
    assert session_canonical.headers["cache-control"] == "no-store, private"
    assert session_canonical.headers["pragma"] == "no-cache"
    assert attempts.json()["attempts"] == []
    assert trajectory.headers["cache-control"] == "no-store, private"
    assert trajectory.headers["pragma"] == "no-cache"
    assert refreshed.headers["cache-control"] == "no-store, private"
    assert trajectory.json() == {
        "watch_id": watch_id,
        "head_run_id": None,
        "head_generation": None,
        "points": [],
        "next_before_generation": None,
        "content_persisted": False,
        "calibrated_as_truth": False,
    }
    assert disabled.json()["watch"]["state"] == "disabled"
    assert source.read_count == 0
    assert "SYNTHETIC_PRIVATE_CANARY" not in rejected.text


def test_watch_worker_runs_all_ten_progress_boundaries_and_coalesces_unchanged_input() -> None:
    ensemble, source, repository = _service()
    watch_repository = _WatchRepository()
    watch = ModelEnsembleWatchService(
        watch_repository,
        ensemble,
        clock=lambda: datetime(2040, 1, 2, 3, 4, tzinfo=UTC),
        poll_interval=timedelta(seconds=60),
    )
    enabled = watch.enable(
        provider=Provider.CODEX,
        project_id="c" * 64,
        session_id=SESSION_ID,
        max_messages=25,
        confirmation=MODEL_ENSEMBLE_WATCH_CONFIRMATION,
    )

    first = watch.run_once()
    assert enabled.state is ModelEnsembleWatchState.QUEUED
    assert enabled.max_messages == 25
    assert first is not None and first.state is ModelEnsembleWatchState.IDLE
    assert first.generation == 1
    assert first.progress_completed == 10
    assert first.latest_run_id is not None
    assert source.read_count == 1
    assert source.message_limits == [25]
    assert len(repository.items) == 1

    # Make the same watch due again. The source is read to observe the local
    # snapshot, but an unchanged fingerprint reuses the sealed run and stores
    # no duplicate result graph.
    assert watch_repository.record is not None
    watch_repository.record = watch_repository.record.model_copy(
        update={"next_check_at": datetime(2040, 1, 2, 3, 4, tzinfo=UTC)}
    )
    second = watch.run_once()
    assert second is not None and second.state is ModelEnsembleWatchState.IDLE
    assert second.generation == 2
    assert second.latest_run_id == first.latest_run_id
    assert source.read_count == 2
    assert len(repository.items) == 1


def test_watch_recomputes_unchanged_input_after_the_execution_plan_changes() -> None:
    ensemble, source, repository = _service()
    watch_repository = _WatchRepository()
    watch = ModelEnsembleWatchService(
        watch_repository,
        ensemble,
        clock=lambda: datetime(2040, 1, 2, 3, 4, tzinfo=UTC),
        poll_interval=timedelta(seconds=60),
    )
    watch.enable(
        provider=Provider.CODEX,
        project_id="c" * 64,
        session_id=SESSION_ID,
        max_messages=25,
        confirmation=MODEL_ENSEMBLE_WATCH_CONFIRMATION,
    )
    first = watch.run_once()
    assert first is not None and first.latest_run_id is not None
    prior = repository.items[first.latest_run_id]
    current_plan_fingerprint = prior.receipt.plan_fingerprint

    # Model an immutable receipt created by an older observation policy.  The
    # source window is unchanged, but the current plan must supersede it.
    repository.items[first.latest_run_id] = prior.model_copy(
        update={
            "receipt": prior.receipt.model_copy(
                update={"plan_fingerprint": "f" * 64}
            )
        }
    )
    assert watch_repository.record is not None
    watch_repository.record = watch_repository.record.model_copy(
        update={"next_check_at": datetime(2040, 1, 2, 3, 4, tzinfo=UTC)}
    )

    second = watch.run_once()

    assert second is not None and second.latest_run_id is not None
    assert second.latest_run_id != first.latest_run_id
    assert source.read_count == 2
    assert len(repository.items) == 2
    current = repository.items[second.latest_run_id]
    assert current.receipt.plan_fingerprint != "f" * 64
    assert current.receipt.plan_fingerprint == current_plan_fingerprint


def test_watch_api_does_not_substitute_an_unbound_historical_run(tmp_path) -> None:
    ensemble, _, repository = _service()
    watch_repository = _WatchRepository()
    watch = ModelEnsembleWatchService(
        watch_repository,
        ensemble,
        clock=lambda: datetime(2040, 1, 2, 3, 4, tzinfo=UTC),
        poll_interval=timedelta(seconds=60),
    )
    watch.enable(
        provider=Provider.CODEX,
        project_id="c" * 64,
        session_id=SESSION_ID,
        max_messages=25,
        confirmation=MODEL_ENSEMBLE_WATCH_CONFIRMATION,
    )
    completed = watch.run_once()
    assert completed is not None and completed.latest_run_id is not None
    assert repository.get_latest(SESSION_ID) is not None

    # Reconfiguring a watch intentionally clears its bound head.  The API must
    # not replace that absence with an older or manually-created session run.
    watch.enable(
        provider=Provider.CODEX,
        project_id="c" * 64,
        session_id=SESSION_ID,
        max_messages=50,
        confirmation=MODEL_ENSEMBLE_WATCH_CONFIRMATION,
    )
    database = Database(tmp_path / "metrics.sqlite3")
    database.initialize()
    app = create_app(
        settings=AppSettings(home=tmp_path),
        database=database,
        api_token=TOKEN,
        session_model_ensemble_service=ensemble,
        model_ensemble_watch_service=watch,
    )

    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get(
            "/v1/model-ensemble-watch/active",
            headers={API_TOKEN_HEADER: TOKEN},
        )
        snapshot = client.get(
            f"/v2/model-ensemble-snapshots/{completed.latest_run_id}",
            headers={API_TOKEN_HEADER: TOKEN},
        )
        unchanged = client.get(
            f"/v2/model-ensemble-snapshots/{completed.latest_run_id}",
            headers={
                API_TOKEN_HEADER: TOKEN,
                "If-None-Match": f'"{completed.latest_run_id}"',
            },
        )
        nonexistent_id = "f" * 64
        nonexistent = client.get(
            f"/v2/model-ensemble-snapshots/{nonexistent_id}",
            headers={
                API_TOKEN_HEADER: TOKEN,
                "If-None-Match": f'"{nonexistent_id}"',
            },
        )

    assert response.status_code == 200
    assert response.json()["watch"]["has_result"] is False
    assert response.json()["latest_run"] is None
    assert snapshot.status_code == 200
    assert snapshot.headers["cache-control"] == "no-store, private"
    assert snapshot.headers["pragma"] == "no-cache"
    assert snapshot.headers["etag"] == f'"{completed.latest_run_id}"'
    assert snapshot.json()["run_id"] == completed.latest_run_id
    assert unchanged.status_code == 304
    assert unchanged.headers["cache-control"] == "no-store, private"
    assert unchanged.headers["pragma"] == "no-cache"
    assert unchanged.content == b""
    assert nonexistent.status_code == 404


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
