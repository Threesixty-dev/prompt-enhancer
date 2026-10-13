from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from enhancement_bench.api import create_app

ORIGIN = {"Origin": "http://testserver"}


@pytest.mark.parametrize("path", [
    "/experiments", "/experiments/example-widget",
    "/experiments/example-widget/runs/new",
    "/experiments/example-widget/runs/example-run",
])
def test_client_deep_links_serve_the_shell(store, contracts, path):
    with client_for(store, contracts) as client:
        response = client.get(path)
        assert response.status_code == 200
        assert 'id="page-content"' in response.text
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get("/assets/forms.js").status_code == 200
        assert client.get("/assets/missing.js").status_code == 404


def test_run_form_uses_authoritative_schemas_behind_gateway(store, contracts):
    with client_for(store, contracts) as client:
        response = client.get("/api/run-form-schema", headers=ORIGIN)
        assert response.status_code == 200
        schema = contracts.validators["execute-request"].schema
        assert response.json() == {"$defs": schema["$defs"], "properties": {
            key: schema["properties"][key] for key in ("objective", "steering", "consumer")
        }}


def client_for(store, contracts):
    return TestClient(create_app(store, contracts,
        allowed_repositories=("registry.example.com/example/enhancer",), origin="http://testserver"))


def test_api_gateway_origin_validation_and_private_errors(store, publication, contracts):
    with client_for(store, contracts) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/experiments").status_code == 200
        assert client.get("/api/experiments", headers={"Origin": "https://example.com"}).status_code == 403
        assert client.get("/api/experiments", headers={"Host": "example.com"}).status_code == 403
        headers = ORIGIN
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
        response = client.get(f"/api/runs/{run_id}", headers=ORIGIN)
        assert response.json()["effective"]["subjects"][0]["text"] == publication.definition.subjects[0].text
        assert response.headers["Cache-Control"] == "no-store"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


@pytest.mark.parametrize("headers", [{}, {"Origin": "null"}, {"Origin": "https://example.com"}])
def test_writes_require_same_origin_without_bench_credentials(store, publication, contracts, headers):
    with client_for(store, contracts) as client:
        for route, payload in [("/api/publications", publication.model_dump()),
                               ("/api/runs", {}), ("/api/runs/example/cancel", {}),
                               ("/api/runs/example/reconcile", {})]:
            assert client.post(route, json=payload, headers=headers).status_code == 403
        assert not store.definitions() and not store.runs()


def test_same_origin_form_posts_are_rejected(store, publication, contracts):
    with client_for(store, contracts) as client:
        response = client.post("/api/publications", content=publication.model_dump_json(),
                               headers=ORIGIN | {"Content-Type": "text/plain"})
        assert response.status_code == 415
        assert not store.definitions() and not store.runs()


def test_ui_run_cancel_and_restart_through_api(store, publication, contracts):
    with client_for(store, contracts) as client:
        client.post("/api/publications", json=publication.model_dump(), headers=ORIGIN)
        headers = ORIGIN
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
        response = client.post("/api/publications", json=payload, headers=ORIGIN)
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
        response = client.post("/api/runs", headers=ORIGIN, json={
            "stableId": publication.definition.stableId, "revision": publication.definition.revision,
            "requestId": str(uuid4()), "overrides": overrides})
    assert response.status_code == 502
    assert response.json() == {"error": {"code": "core_contract_violation"}}
    assert store.runs() == original_runs
