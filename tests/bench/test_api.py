from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from enhancement_bench.api import create_app

ORIGIN = {"Origin": "http://testserver"}


@pytest.mark.parametrize("path", [
    "/experiments", "/experiments/example-widget",
    "/experiments/example-widget/runs/new",
    "/experiments/example-widget/runs/example-run",
    "/stats", "/experiments/example-widget/stats",
])
def test_client_deep_links_serve_the_shell(store, contracts, path):
    with client_for(store, contracts) as client:
        response = client.get(path)
        assert response.status_code == 200
        assert 'id="page-content"' in response.text
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get("/assets/forms.js").status_code == 200
        assert client.get("/assets/overview.js").status_code == 200
        assert client.get("/assets/missing.js").status_code == 404


def test_run_form_uses_authoritative_schemas_behind_gateway(store, contracts):
    with client_for(store, contracts) as client:
        response = client.get("/api/run-form-schema", headers=ORIGIN)
        assert response.status_code == 200
        schema = contracts.validators["execute-request"].schema
        assert response.json() == {"$defs": schema["$defs"], "properties": {
            key: schema["properties"][key] for key in ("objective", "steering", "consumer", "evaluation")
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


def test_run_history_paginates_beyond_default_limit_without_skips(store, publication, contracts):
    from conftest import changed
    from enhancement_bench.definitions import Overrides

    store.import_publication(publication)
    store.import_publication(changed(publication, revision="2", generation=2))
    store.import_publication(changed(publication, stableId="example-other"))
    for _ in range(102):
        store.enqueue_ui("example-widget", "1", Overrides(), str(uuid4()))
    with store.transaction() as db:
        db.execute("UPDATE runs SET created=1000")
    expected = [run["id"] for run in store.runs(500)]
    with client_for(store, contracts) as client:
        first = client.get("/api/runs").json()
        assert len(first["runs"]) == 100
        assert first["nextCursor"] == first["runs"][-1]["id"]
        # New runs must not shift the boundary of an already-open history page.
        inserted = store.enqueue_ui("example-widget", "2", Overrides(), str(uuid4()))
        seen = first["runs"]
        cursor = first["nextCursor"]
        while cursor:
            response = client.get("/api/runs", params={"limit": 3, "before": cursor})
            assert response.status_code == 200
            page = response.json()
            assert 0 < len(page["runs"]) <= 3
            seen.extend(page["runs"])
            cursor = page["nextCursor"]
        assert [run["id"] for run in seen] == expected
        assert inserted not in expected
        assert {(run["stable_id"], run["revision"]) for run in seen} == {
            ("example-widget", "1"), ("example-widget", "2"), ("example-other", "1")}


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=invalid", "before=" + "x" * 81])
def test_run_history_rejects_invalid_page_bounds(store, contracts, query):
    with client_for(store, contracts) as client:
        assert client.get("/api/runs?" + query).status_code == 422


def test_run_history_handles_empty_list_and_unknown_cursor(store, contracts):
    with client_for(store, contracts) as client:
        assert client.get("/api/runs?limit=10").json() == {"runs": [], "nextCursor": None}
        response = client.get("/api/runs?before=example-missing")
        assert response.status_code == 400
        assert response.json() == {"error": {"code": "invalid_run_cursor"}}


@pytest.mark.parametrize("peer,headers,status,emits", [
    ("127.0.0.1", {}, 200, True), ("::1", {}, 200, True),
    ("192.0.2.1", {}, 200, False),
    ("127.0.0.1", {"Host": "example.com"}, 403, False),
])
def test_readiness_receipt_contains_only_baked_revision_and_time(
    store, contracts, monkeypatch, capsys, peer, headers, status, emits,
):
    from pathlib import Path
    import enhancement_bench.api as api

    original_is_file, original_read_text = Path.is_file, Path.read_text
    monkeypatch.setattr(Path, "is_file", lambda path: True if path.name == "revision.txt" else original_is_file(path))
    monkeypatch.setattr(Path, "read_text", lambda path, *a, **kw: "a" * 40 if path.name == "revision.txt" else original_read_text(path, *a, **kw))
    monkeypatch.setattr(api.time, "time_ns", lambda: 1_790_000_000_000_000_000)
    app = create_app(store, contracts, allowed_repositories=(), origin="http://testserver")
    with TestClient(app, client=(peer, 50000)) as client:
        response = client.get("/health/ready?example-private-canary=1", headers=headers)
        assert response.status_code == status
        if status == 200:
            assert response.json()["revision"] == "a" * 40
    assert capsys.readouterr().out == (
        "BENCH_READY_V1 revision=" + "a" * 40 + " time_ms=1790000000000\n" if emits else ""
    )
