"""Default-service Codex source proof for reviewed verification evidence.

The fixture replaces the documented app-server client transport, compatibility
receipt, and local model executor.  It never supplies a prebuilt P1 context:
the default ``CodexTextAnalysisSource`` parses the fictional wire payload on
every run. Native HTTP body binding is deliberately covered separately.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from prompt_enhancer.application.analysis.requirement_plan_evidence import (
    REQUIREMENT_PLAN_DECISION_CONFIRMATION,
    REQUIREMENT_PLAN_IMPORT_CONFIRMATION,
    REQUIREMENT_PLAN_REVIEW_CONFIRMATION,
    InMemoryRequirementPlanReviewContextStore,
    RequirementPlanDecisionCommand,
    RequirementPlanDecisionKind,
)
from prompt_enhancer.application.analysis.requirement_verification_persistence import (
    ObservedCheckResultIssueCommand,
)
from prompt_enhancer.application.analysis.session_model_ensemble import (
    MODEL_ENSEMBLE_CONFIRMATION,
)
from prompt_enhancer.bootstrap import bootstrap_local_application
from prompt_enhancer.config import AppSettings
from prompt_enhancer.domain import DataTier, Provider, SafeSession, SessionState
from prompt_enhancer.application.providers import (
    ProviderCompatibilityCatalog,
    ProviderSurfaceCompatibilityPolicy,
)
from prompt_enhancer.infrastructure.providers.codex_app_server.client import (
    CodexAppServerClient,
)
from prompt_enhancer.infrastructure.providers.codex_app_server.content_source import (
    CODEX_LOCAL_INSTALLATION_ID,
    CodexTextAnalysisSource,
)
from prompt_enhancer.infrastructure.text_models.model_ensemble import (
    SerialModelEnsembleRunner,
)
from prompt_enhancer.interfaces.http.requirement_plan_evidence_routes import (
    REQUIREMENT_PLAN_EVIDENCE_MEDIA_TYPE,
)
from prompt_enhancer.interfaces.http.user_presence import UserPresenceApprovalManager
from prompt_enhancer.privacy import load_or_create_api_token

from test_requirement_plan_evidence_persistence import _confirm, _import, _payload as _plan_payload
from test_requirement_verification_e2e import (
    API_TOKEN_HEADER,
    BASE_URL,
    _assert_private,
    _native_post,
    _verify_presence,
)
from test_session_model_ensemble import _execute


RAW_THREAD_ID = "example-cp40-default-codex-thread"


class _Compatible:
    def require_compatible(self, provider: str) -> object:
        assert provider == "codex"
        return object()


class _Transport:
    def __init__(self, payload: dict[str, object]) -> None:
        self._responses: list[object] = [
            {"serverInfo": {"version": "example-app-server-1"}},
            {
                "data": [
                    {
                        "id": RAW_THREAD_ID,
                        "createdAt": 1_768_473_600,
                        "status": {"type": "notLoaded"},
                    }
                ],
                "nextCursor": None,
            },
            payload,
        ]
        self.requests: list[tuple[str, dict[str, object]]] = []

    def _request(self, method: str, params: dict[str, object]) -> object:
        self.requests.append((method, params))
        return self._responses.pop(0)

    def _notify(self, _method: str, _params: dict[str, object] | None = None) -> None:
        return None

    def close(self) -> None:
        return None


def _payload(*, exit_code: int | None = 0) -> dict[str, object]:
    commands: list[dict[str, object]] = []
    for index, code in enumerate((exit_code, 1, 0)):
        command: dict[str, object] = {
            "type": "commandExecution",
            "id": f"example-cp40-check-{index}",
            "command": "pytest -q",
            "status": "completed",
        }
        if code is not None:
            command["exitCode"] = code
        commands.append(command)
    return {
        "thread": {
            "id": RAW_THREAD_ID,
            "turns": [
                {
                    "id": "example-cp40-turn",
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "example-cp40-request",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "First fictional requirement. Second fictional requirement. "
                                        "Third fictional requirement. Omitted fictional clause."
                                    ),
                                }
                            ],
                        },
                        {
                            "type": "plan",
                            "id": "example-cp40-plan",
                            "text": "Implement the first fictional requirement.",
                        },
                        *commands,
                    ],
                }
            ],
        }
    }


def _persist_codex_session(application) -> str:  # type: ignore[no-untyped-def]
    pseudonymizer = application.pseudonymizer
    installation_id = pseudonymizer.pseudonymize(
        "codex:installation", CODEX_LOCAL_INSTALLATION_ID
    )
    session_id = pseudonymizer.pseudonymize(
        f"codex:session:{installation_id}", RAW_THREAD_ID
    )
    application.database.persist_session(
        SafeSession(
            provider=Provider.CODEX,
            installation_id=installation_id,
            project_id=pseudonymizer.pseudonymize(
                f"codex:project:{installation_id}", "example-cp40-project"
            ),
            session_id=session_id,
            provider_version="example-app-server-1",
            adapter_version="codex-app-server-adapter-v2",
            source_schema_version="codex-app-server-source-v2",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            terminal_state=SessionState.UNKNOWN,
            events_complete=False,
        ),
        (),
    )
    application.database.grant_consent(Provider.CODEX, DataTier.REDACTED_CONTENT)
    return session_id


def _default_service(application, contexts):  # type: ignore[no-untyped-def]
    service = application.create_session_model_ensemble_service(
        _Compatible(), contexts
    )
    # The production composition chooses this runner.  The synthetic executor
    # avoids loading a local model while retaining the production run/seal path.
    service._runner = SerialModelEnsembleRunner(executor=_execute, device="cpu")  # type: ignore[attr-defined]
    return service


def _current_plan_payload(
    session_id: str, run, *, expires_at: datetime | None = None
) -> bytes:  # type: ignore[no-untyped-def]
    """Adapt the legacy synthetic graph to this run's sealed projection id."""
    document = json.loads(_plan_payload(session_id, run))
    document["source_projection_version"] = run.receipt.metric_publication_v2.projection_version
    if expires_at is not None:
        document["expires_at"] = expires_at.isoformat().replace("+00:00", "Z")
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")


def _http_headers(token: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {API_TOKEN_HEADER: token}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _run_over_http(
    client: TestClient, *, session_id: str, token: str, idempotency_key: str
) -> dict[str, object]:
    response = client.post(
        f"/v1/sessions/{session_id}/model-ensemble-runs",
        headers=_http_headers(token, idempotency_key=idempotency_key),
        json={"confirmation": MODEL_ENSEMBLE_CONFIRMATION},
    )
    _assert_private(response)
    assert response.status_code == 200, response.text
    return response.json()["run"]


def _confirm_current_plan_over_http(
    client: TestClient,
    *,
    session_id: str,
    run,  # type: ignore[no-untyped-def]
    token: str,
    presence: UserPresenceApprovalManager,
) -> None:
    """Exercise import, exact native review, and exact native confirmation."""

    base = f"/v1/sessions/{session_id}/requirement-plan-evidence"
    payload = _current_plan_payload(
        session_id, run, expires_at=datetime.now(UTC) + timedelta(minutes=5)
    )
    imported = client.post(
        f"{base}/import",
        headers={
            **_http_headers(token, idempotency_key="synthetic-cp40-http-plan-import-0001"),
            "Content-Type": REQUIREMENT_PLAN_EVIDENCE_MEDIA_TYPE,
            "X-Requirement-Plan-Payload-SHA256": hashlib.sha256(payload).hexdigest(),
            "X-Requirement-Plan-Confirmation": REQUIREMENT_PLAN_IMPORT_CONFIRMATION,
        },
        content=payload,
    )
    _assert_private(imported)
    assert imported.status_code == 201, imported.text
    proposal = imported.json()["proposal"]
    browser = client.get("/auth/session").json()
    review_path = f"{base}/proposals/{proposal['proposal_id']}/review"
    review = _native_post(
        client,
        presence,
        path=review_path,
        payload={
            "expected_source_run_id": run.run_id,
            "confirmation": REQUIREMENT_PLAN_REVIEW_CONFIRMATION,
        },
        csrf_token=browser["csrf_token"],
    )
    _assert_private(review)
    assert review.status_code == 200, review.text
    reviewed = review.json()
    decision = RequirementPlanDecisionCommand(
        expected_source_run_id=run.run_id,
        decision=RequirementPlanDecisionKind.CONFIRM,
        confirmation=REQUIREMENT_PLAN_DECISION_CONFIRMATION,
        review_receipt_id=reviewed["review_receipt_id"],
        manifest_fingerprint=reviewed["manifest_fingerprint"],
        reviewed_graph_fingerprint=reviewed["reviewed_graph_fingerprint"],
        reviewed_candidate_set_fingerprint=reviewed[
            "reviewed_candidate_set_fingerprint"
        ],
        complete_review_acknowledged=True,
    )
    decided = _native_post(
        client,
        presence,
        path=f"{base}/proposals/{proposal['proposal_id']}/decision",
        payload=decision.model_dump(mode="json"),
        csrf_token=browser["csrf_token"],
        idempotency_key="synthetic-cp40-http-plan-decision-0002",
    )
    _assert_private(decided)
    assert decided.status_code == 201, decided.text


def _issue_observed_checks_over_http(
    client: TestClient,
    *,
    session_id: str,
    source_run_id: str,
    token: str,
    presence: UserPresenceApprovalManager,
) -> None:
    base = f"/v1/sessions/{session_id}/requirement-verification-evidence"
    issued = client.post(
        f"{base}/opportunity-sets/current", headers=_http_headers(token)
    )
    _assert_private(issued)
    assert issued.status_code == 201, issued.text
    snapshot = issued.json()["snapshot"]
    opportunities = snapshot["evidence"]["opportunities"]
    fingerprint = opportunities["opportunity_set_fingerprint"]
    browser = client.get("/auth/session").json()
    for index, opportunity in enumerate(opportunities["opportunities"]):
        path = (
            f"{base}/opportunity-sets/{fingerprint}/opportunities/"
            f"{opportunity['opportunity_id']}/observed-checks"
        )
        preflight_payload = {
            "expected_source_run_id": source_run_id,
            "through_revision": index,
            "expected_predecessor_authority_id": None,
        }
        preflight = client.post(
            f"{path}/preflight", headers=_http_headers(token), json=preflight_payload
        )
        _assert_private(preflight)
        assert preflight.status_code == 200, preflight.text
        manifest = preflight.json()
        candidate = manifest["candidates"][index]
        review_path = f"{path}/{candidate['candidate_id']}/review"
        review = _native_post(
            client,
            presence,
            path=review_path,
            payload={
                **preflight_payload,
                "candidate_manifest_fingerprint": manifest[
                    "candidate_manifest_fingerprint"
                ],
                "confirmation": "open_exact_local_requirement_observed_check_review",
            },
            csrf_token=browser["csrf_token"],
        )
        _assert_private(review)
        assert review.status_code == 200, review.text
        reviewed = review.json()
        issue = _native_post(
            client,
            presence,
            path=f"{path}/{candidate['candidate_id']}/issue",
            payload={
                "expected_source_run_id": source_run_id,
                "source_window_fingerprint": manifest["source_window_fingerprint"],
                "through_revision": index,
                "expected_predecessor_authority_id": None,
                "candidate_manifest_fingerprint": manifest[
                    "candidate_manifest_fingerprint"
                ],
                "review_receipt_id": reviewed["review_receipt_id"],
                "review_fingerprint": reviewed["review_fingerprint"],
                "full_criterion_coverage_acknowledged": True,
                "confirmation": "issue_exact_local_requirement_observed_check_result",
            },
            csrf_token=browser["csrf_token"],
            idempotency_key=f"synthetic-cp40-http-issue-{index:04d}",
        )
        _assert_private(issue)
        assert issue.status_code == 201, issue.text


def _default_http_app(
    application, monkeypatch  # type: ignore[no-untyped-def]
) -> tuple[object, UserPresenceApprovalManager, str]:
    """Build the normal HTTP composition without a provider probe or model load.

    The production factories remain in use: only the documented compatibility
    receipt and local executor are synthetic.  The default Codex source itself
    is deliberately left untouched here (apart from its app-server transport).
    """

    application_type = type(application)
    original_catalog = application_type.create_provider_compatibility_catalog
    original_ensemble = application_type.create_session_model_ensemble_service

    def deterministic_ensemble(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        service = original_ensemble(self, *args, **kwargs)
        service._runner = SerialModelEnsembleRunner(executor=_execute, device="cpu")  # type: ignore[attr-defined]
        return service

    # ``create_http_app`` eagerly refreshes the documented decoder probe.  This
    # test verifies the composition around it; it must not inspect a real local
    # provider installation or launch the schema generator.
    monkeypatch.setattr(application_type, "create_session_model_ensemble_service", deterministic_ensemble)
    monkeypatch.setattr(ProviderCompatibilityCatalog, "refresh", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        ProviderSurfaceCompatibilityPolicy,
        "require_compatible",
        lambda *_args, **_kwargs: object(),
    )
    presence = UserPresenceApprovalManager()
    app = application.create_http_app(
        user_presence_confirmation=_verify_presence(presence),
        user_presence_confirmation_mode="native_bridge_bound_token",
    )
    return app, presence, load_or_create_api_token(application.settings.api_token_path)


def test_default_http_composition_binds_codex_observed_evidence_only_to_fresh_run(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """HTTP-root proof; native tokens and executor are synthetic test seams."""

    application = bootstrap_local_application(AppSettings(home=tmp_path))
    session_id = _persist_codex_session(application)
    payload = _payload()
    transports: list[_Transport] = []

    def default_client(_self):  # type: ignore[no-untyped-def]
        transport = _Transport(payload)
        transports.append(transport)
        return CodexAppServerClient(transport)

    monkeypatch.setattr(CodexTextAnalysisSource, "_default_client_factory", default_client)
    app, presence, token = _default_http_app(application, monkeypatch)
    # Do not enter the app lifespan: the test proves route composition, while
    # runtime workers are separately tested and must not start here.
    client = TestClient(app, base_url=BASE_URL)
    try:
        first_dto = _run_over_http(
            client,
            session_id=session_id,
            token=token,
            idempotency_key="synthetic-cp40-http-first-0001",
        )
        first = application.database.model_ensemble_repository().get(first_dto["run_id"])
        assert first is not None
        assert first.requirement_verification_evidence_binding.evidence_source == "unavailable"
        saved_first_payload = first.model_dump(mode="json")
        _confirm_current_plan_over_http(
            client,
            session_id=session_id,
            run=first,
            token=token,
            presence=presence,
        )
        _issue_observed_checks_over_http(
            client,
            session_id=session_id,
            source_run_id=first.run_id,
            token=token,
            presence=presence,
        )
        saved_first = application.database.model_ensemble_repository().get(first.run_id)
        assert saved_first is not None
        assert saved_first.model_dump(mode="json") == saved_first_payload
        fresh_dto = _run_over_http(
            client,
            session_id=session_id,
            token=token,
            idempotency_key="synthetic-cp40-http-fresh-0002",
        )
        fresh = application.database.model_ensemble_repository().get(fresh_dto["run_id"])
        assert fresh is not None
        assert fresh.run_id != first.run_id
        reloaded_first = application.database.model_ensemble_repository().get(first.run_id)
        assert reloaded_first is not None
        assert reloaded_first.model_dump(mode="json") == saved_first_payload
        assert fresh.requirement_verification_evidence_binding.evidence_source == "persisted_evidence"
        metric = next(
            item.state
            for item in fresh.receipt.metric_publication_v2.metrics
            if item.state.metric_key == "outcome.verified_requirement_coverage"
        )
        assert (metric.value_state.value, metric.numerator, metric.denominator) == (
            "known",
            2,
            3,
        )
        assert (
            fresh_dto["requirement_verification_evidence_binding"]["evidence_source"]
            == "persisted_evidence"
        )
        response_metric = next(
            item["state"]
            for item in fresh_dto["metric_publication_v2"]["metrics"]
            if item["state"]["metric_key"] == "outcome.verified_requirement_coverage"
        )
        assert (
            response_metric["value_state"],
            response_metric["numerator"],
            response_metric["denominator"],
        ) == ("known", 2, 3)
    finally:
        client.close()
    assert all(
        [method for method, _params in transport.requests]
        == ["initialize", "thread/list", "thread/read"]
        and transport.requests[-1][1]
        == {"threadId": RAW_THREAD_ID, "includeTurns": True}
        for transport in transports
    )


def test_default_codex_source_can_publish_observed_check_evidence_on_a_fresh_run(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    application = bootstrap_local_application(AppSettings(home=tmp_path))
    session_id = _persist_codex_session(application)
    payload = _payload()
    transports: list[_Transport] = []

    def default_client(_self):  # type: ignore[no-untyped-def]
        transport = _Transport(payload)
        transports.append(transport)
        return CodexAppServerClient(transport)

    monkeypatch.setattr(CodexTextAnalysisSource, "_default_client_factory", default_client)
    contexts = InMemoryRequirementPlanReviewContextStore()
    ensemble = _default_service(application, contexts)
    first = ensemble.run(
        provider=Provider.CODEX,
        session_id=session_id,
        confirmation=MODEL_ENSEMBLE_CONFIRMATION,
        idempotency_key="synthetic-cp40-default-first-0001",
    ).run
    # Until the independently reviewed requirement plan exists, verification
    # opportunities are correctly unavailable rather than silently pending.
    assert first.requirement_verification_evidence_binding.evidence_source == "unavailable"

    plan_service = application.create_requirement_plan_evidence_service(contexts)
    confirmed = _confirm(
        plan_service,
        session_id,
        first,
        _import(
            plan_service,
            session_id,
            first,
            suffix="cp40-default",
            payload=_current_plan_payload(session_id, first),
        ),
        suffix="cp40-default",
    )
    assert confirmed.decision is not None

    verification = application.create_requirement_verification_evidence_service(contexts)
    snapshot, created = verification.issue_current_opportunities(session_id)
    assert created is True
    review_service = verification._review_service  # type: ignore[attr-defined]
    assert review_service is not None
    for index, opportunity in enumerate(snapshot.evidence.opportunities.opportunities):
        manifest = review_service.observed_candidates(
            session_id=session_id,
            opportunity_set_fingerprint=snapshot.evidence.opportunities.opportunity_set_fingerprint,
            opportunity_id=opportunity.opportunity_id,
            expected_source_run_id=first.run_id,
            through_revision=index,
            expected_predecessor_authority_id=None,
        )
        candidate = manifest.candidates[index]
        review = review_service.open_observed_check(
            session_id=session_id,
            opportunity_set_fingerprint=manifest.opportunity_set_fingerprint,
            opportunity_id=opportunity.opportunity_id,
            candidate_id=candidate.candidate_id,
            expected_source_run_id=first.run_id,
            through_revision=index,
            expected_predecessor_authority_id=None,
            candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
        )
        evidence, applied = verification.append_observed_check_result(
            session_id=session_id,
            command=ObservedCheckResultIssueCommand(
                opportunity_set_fingerprint=manifest.opportunity_set_fingerprint,
                opportunity_id=opportunity.opportunity_id,
                candidate_id=candidate.candidate_id,
                expected_source_run_id=first.run_id,
                source_window_fingerprint=manifest.source_window_fingerprint,
                through_revision=index,
                candidate_manifest_fingerprint=manifest.candidate_manifest_fingerprint,
                review_receipt_id=review.review_receipt_id,
                review_fingerprint=review.review_fingerprint,
                full_criterion_coverage_acknowledged=True,
                confirmation="issue_exact_local_requirement_observed_check_result",
            ),
            idempotency_key=f"synthetic-cp40-default-issue-{index:04d}",
        )
        assert applied is True
    assert sorted(item.outcome.value for item in evidence.evidence.verification_results) == [
        "failed", "passed", "passed"
    ]
    saved_first = application.database.model_ensemble_repository().get(first.run_id)
    assert saved_first is not None
    saved_first_payload = saved_first.model_dump(mode="json")

    fresh = ensemble.run(
        provider=Provider.CODEX,
        session_id=session_id,
        confirmation=MODEL_ENSEMBLE_CONFIRMATION,
        idempotency_key="synthetic-cp40-default-fresh-0002",
    ).run
    assert fresh.run_id != first.run_id
    reloaded_first = application.database.model_ensemble_repository().get(first.run_id)
    assert reloaded_first is not None
    assert reloaded_first.model_dump(mode="json") == saved_first_payload
    assert fresh.requirement_verification_evidence_binding.evidence_source == "persisted_evidence"
    metric = next(
        item.state
        for item in fresh.receipt.metric_publication_v2.metrics
        if item.state.metric_key == "outcome.verified_requirement_coverage"
    )
    assert (metric.value_state.value, metric.numerator, metric.denominator) == ("known", 2, 3)
    assert all(
        [method for method, _params in transport.requests]
        == ["initialize", "thread/list", "thread/read"]
        and transport.requests[-1][1]
        == {"threadId": RAW_THREAD_ID, "includeTurns": True}
        for transport in transports
    )

    # A changed documented completion is a different source window; previously
    # sealed authority may not be quietly reused for that newer analysis.
    items = payload["thread"]["turns"][0]["items"]  # type: ignore[index]
    next(item for item in items if item.get("id") == "example-cp40-check-0")["exitCode"] = 1
    drifted = ensemble.run(
        provider=Provider.CODEX,
        session_id=session_id,
        confirmation=MODEL_ENSEMBLE_CONFIRMATION,
        idempotency_key="synthetic-cp40-default-drift-0003",
    ).run
    assert drifted.input_fingerprint != fresh.input_fingerprint
    assert drifted.requirement_verification_evidence_binding.evidence_source != "persisted_evidence"
    drifted_metric = next(
        item.state
        for item in drifted.receipt.metric_publication_v2.metrics
        if item.state.metric_key == "outcome.verified_requirement_coverage"
    )
    assert drifted_metric.value_state.value == "unknown"


@pytest.mark.parametrize(
    ("field", "value"),
    (("exitCode", None), ("status", "unrecognized-terminal-state")),
)
def test_default_codex_source_withholds_incomplete_or_malformed_completion_metadata(
    tmp_path, monkeypatch, field: str, value: object
) -> None:  # type: ignore[no-untyped-def]
    application = bootstrap_local_application(AppSettings(home=tmp_path))
    session_id = _persist_codex_session(application)
    missing = _payload(exit_code=None)
    items = missing["thread"]["turns"][0]["items"]  # type: ignore[index]
    for item in items:
        if item.get("type") == "commandExecution":
            if value is None:
                item.pop(field, None)
            else:
                item[field] = value

    def default_client(_self):  # type: ignore[no-untyped-def]
        return CodexAppServerClient(_Transport(missing))

    monkeypatch.setattr(CodexTextAnalysisSource, "_default_client_factory", default_client)
    contexts = InMemoryRequirementPlanReviewContextStore()
    run = _default_service(application, contexts).run(
        provider=Provider.CODEX,
        session_id=session_id,
        confirmation=MODEL_ENSEMBLE_CONFIRMATION,
        idempotency_key="synthetic-cp40-default-missing-0001",
    ).run
    context = contexts._entries[run.run_id].context  # type: ignore[attr-defined]
    assert context.observed_check_completions == ()
