from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from enhancement_bench.api import create_app

OPERATOR = "example-operator-token-not-a-secret"
IMPORT = "example-import-token-not-a-secret"


def client_for(store, contracts):
    return TestClient(create_app(store, contracts, operator_token=OPERATOR, import_token=IMPORT,
        allowed_repositories=("registry.example.com/example/enhancer",), origin="http://testserver"))


def test_api_auth_origin_validation_and_private_errors(store, publication, contracts):
    with client_for(store, contracts) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/experiments").status_code == 401
        assert client.get("/api/experiments", headers={"Authorization": "Bearer " + IMPORT}).status_code == 401
        assert client.get("/api/experiments", headers={"Authorization": "Bearer " + OPERATOR, "Origin": "https://example.com"}).status_code == 403
        assert client.get("/api/experiments", headers={"Host": "example.com"}).status_code == 403
        headers = {"Authorization": "Bearer " + IMPORT}
        response = client.post("/api/publications", json=publication.model_dump(), headers=headers)
        assert response.status_code == 202
        run_id = response.json()["runId"]
        assert client.post("/api/publications", json=publication.model_dump(), headers=headers).json()["runId"] == run_id
        payload = publication.model_dump()
        payload["sensitive-canary"] = "example-private-content"
        response = client.post("/api/publications", json=payload, headers=headers)
        assert response.status_code == 422
        assert "example-private-content" not in response.text
        response = client.post("/api/publications", content=b"x" * 1_000_001, headers=headers | {"Content-Type": "application/json"})
        assert response.status_code == 413
        response = client.get(f"/api/runs/{run_id}", headers={"Authorization": "Bearer " + OPERATOR})
        assert response.json()["effective"]["subjects"][0]["text"] == publication.definition.subjects[0].text
        assert response.headers["Cache-Control"] == "no-store"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_ui_run_cancel_and_restart_through_api(store, publication, contracts):
    with client_for(store, contracts) as client:
        client.post("/api/publications", json=publication.model_dump(), headers={"Authorization": "Bearer " + IMPORT})
        headers = {"Authorization": "Bearer " + OPERATOR}
        payload = {"stableId": "example-widget", "revision": "1", "requestId": str(uuid4()), "overrides": {"parameters": {"timeout_seconds": 60}}}
        response = client.post("/api/runs", json=payload, headers=headers)
        assert response.status_code == 202
        run_id = response.json()["runId"]
        assert client.post("/api/runs", json=payload, headers=headers).json()["runId"] == run_id
        assert client.post(f"/api/runs/{run_id}/cancel", json={}, headers=headers).json()["status"] == "cancelled"
    from enhancement_bench.store import Store
    with client_for(Store(store.path), contracts) as client:
        response = client.get(f"/api/runs/{run_id}", headers=headers)
        assert response.json()["status"] == "cancelled"
        assert response.json()["effective"]["units"][0]["parameters"]["timeout_seconds"] == 60


def test_definition_rejects_provider_urls_before_persistence(store, publication, contracts):
    payload = publication.model_dump()
    payload["definition"]["consumerBinding"]["endpoint"] = "https://example.com/untrusted"
    with client_for(store, contracts) as client:
        response = client.post("/api/publications", json=payload, headers={"Authorization": "Bearer " + IMPORT})
        assert response.status_code == 502
        assert not store.runs() and not store.definitions()


@pytest.mark.parametrize("overrides", [
    {"objective": {"targets": [{"kind": "numeric", "evaluator_id": "prompt", "metric_key": "prompt.acceptance_testability", "direction": "sideways"}]}},
    {"unitSteering": {"consumer": {"style": "invented"}}},
])
def test_invalid_generation_controls_are_rejected_before_persistence(store, publication, contracts, overrides):
    store.import_publication(publication)
    original_runs = store.runs()
    with client_for(store, contracts) as client:
        response = client.post("/api/runs", headers={"Authorization": "Bearer " + OPERATOR}, json={
            "stableId": publication.definition.stableId, "revision": publication.definition.revision,
            "requestId": str(uuid4()), "overrides": overrides})
    assert response.status_code == 502
    assert response.json() == {"error": {"code": "core_contract_violation"}}
    assert store.runs() == original_runs
