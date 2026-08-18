from __future__ import annotations

from fastapi.testclient import TestClient

from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.application.analysis.metric_lifecycle_evidence import (
    MetricLifecycleDecisionCommand,
    MetricLifecycleDecisionKind,
    MetricLifecycleFamily,
)
from prompt_enhancer.config import AppSettings
from prompt_enhancer.interfaces.http.browser_session import CSRF_HEADER

from test_metric_lifecycle_evidence_persistence import (
    _opportunity_command,
    _service,
)


TOKEN = "example_metric_lifecycle_token_do_not_use_123456789"


def _app(tmp_path):
    database, session_id, run, _models, _repository, service = _service(tmp_path)
    app = create_app(
        settings=AppSettings(home=tmp_path),
        database=database,
        api_token=TOKEN,
        metric_lifecycle_evidence_service=service,
    )
    return app, session_id, run


def _private(response) -> None:
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"


def test_authenticated_propose_replay_decide_and_list_are_content_free(tmp_path) -> None:
    app, session_id, run = _app(tmp_path)
    base = f"/v1/sessions/{session_id}/metric-lifecycle-evidence/proposals"
    proposal_payload = _opportunity_command(
        run.run_id, MetricLifecycleFamily.AMBIGUITY_RESOLUTION
    ).model_dump(mode="json")
    headers = {
        API_TOKEN_HEADER: TOKEN,
        "Idempotency-Key": "metric-lifecycle-proposal-example",
    }
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get(base).status_code == 401
        proposed = client.post(base, headers=headers, json=proposal_payload)
        replay = client.post(base, headers=headers, json=proposal_payload)
        proposal = proposed.json()["proposal"]
        decided = client.post(
            f"{base}/{proposal['proposal_id']}/decision",
            headers={
                API_TOKEN_HEADER: TOKEN,
                "Idempotency-Key": "metric-lifecycle-decision-example",
            },
            json=MetricLifecycleDecisionCommand(
                expected_source_run_id=proposal["source_run_id"],
                decision=MetricLifecycleDecisionKind.CONFIRM,
            ).model_dump(mode="json"),
        )
        listing = client.get(base, headers={API_TOKEN_HEADER: TOKEN})

    for response in (proposed, replay, decided, listing):
        _private(response)
    assert proposed.status_code == 201
    assert replay.status_code == 200
    assert replay.json() == {**proposed.json(), "applied": False}
    assert decided.status_code == 201
    assert decided.json()["proposal"]["status"] == "confirmed"
    assert listing.status_code == 200
    assert listing.json()["proposals"] == [decided.json()["proposal"]]
    serialized = listing.text.casefold()
    for prohibited in ("prompt", "transcript", "excerpt", "message", "path"):
        assert prohibited not in serialized


def test_errors_are_sanitized_private_and_browser_mutations_are_csrf_bound(
    tmp_path,
) -> None:
    app, session_id, run = _app(tmp_path)
    base = f"/v1/sessions/{session_id}/metric-lifecycle-evidence/proposals"
    valid = _opportunity_command(
        run.run_id, MetricLifecycleFamily.CLARIFICATION_YIELD
    ).model_dump(mode="json")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        browser = client.get("/auth/session")
        csrf = browser.json()["csrf_token"]
        no_csrf = client.post(
            base,
            headers={
                "Idempotency-Key": "metric-lifecycle-browser-no-csrf",
                "Origin": "http://127.0.0.1",
            },
            json=valid,
        )
        wrong_origin = client.post(
            base,
            headers={
                "Idempotency-Key": "metric-lifecycle-browser-origin",
                CSRF_HEADER: csrf,
                "Origin": "https://attacker.invalid",
            },
            json=valid,
        )
        extra = client.post(
            base,
            headers={
                API_TOKEN_HEADER: TOKEN,
                "Idempotency-Key": "metric-lifecycle-extra-field",
            },
            json={**valid, "note": "PRIVATE-METRIC-LIFECYCLE-CANARY"},
        )
        stale = client.post(
            base,
            headers={
                API_TOKEN_HEADER: TOKEN,
                "Idempotency-Key": "metric-lifecycle-stale-window",
            },
            json={**valid, "expected_source_run_id": "f" * 64},
        )

    assert no_csrf.status_code == 403
    assert wrong_origin.status_code == 403
    assert extra.status_code == 422
    assert extra.json() == {"detail": "request validation failed"}
    assert "PRIVATE-METRIC-LIFECYCLE-CANARY" not in extra.text
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "metric_lifecycle_source_window_stale"
    for response in (no_csrf, wrong_origin, extra, stale):
        _private(response)


def test_openapi_exposes_only_closed_metric_lifecycle_commands(tmp_path) -> None:
    app, _session_id, _run = _app(tmp_path)
    schema = app.openapi()
    paths = tuple(
        path for path in schema["paths"] if "metric-lifecycle-evidence" in path
    )
    assert paths == (
        "/v1/sessions/{session_id}/metric-lifecycle-evidence/proposals",
        "/v1/sessions/{session_id}/metric-lifecycle-evidence/proposals/{proposal_id}/decision",
    )
    serialized = str(
        {
            key: value
            for key, value in schema["components"]["schemas"].items()
            if "MetricLifecycle" in key
        }
    ).casefold()
    for prohibited in ("note", "comment", "prompt", "transcript", "excerpt", "path"):
        assert prohibited not in serialized
