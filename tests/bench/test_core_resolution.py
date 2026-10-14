import concurrent.futures
import json
from uuid import uuid4

import httpx
import pytest
import yaml

from enhancement_bench import cli
from enhancement_bench.definitions import CoreImage, Overrides, Publication
from enhancement_bench.errors import BenchError
from enhancement_bench.store import Store
from test_api import ORIGIN, client_for


def artifact(publication, digest="b", variant="default"):
    return CoreImage(
        schemaVersion="core-release/v1", coreVersion=publication.definition.enhancerVersion,
        variant=variant, image=publication.image.split("@", 1)[0] + "@sha256:" + digest * 64,
        buildInputSha256="c" * 64, validatedSourceRevision="d" * 40,
        action="built", runtimeVerified=True,
    )


def version_publication(publication, **changes):
    definition = publication.definition.model_dump() | changes
    return Publication.model_validate({"schemaVersion": "bench-publication/v2", "definition": definition})


def enqueue(store, request_id=None, retry_of=None, overrides=None):
    return store.enqueue_ui("example-widget", "1", overrides or Overrides(),
                            request_id or str(uuid4()), retry_of)


def test_new_run_and_rerun_resolve_current_version_without_revising_experiment(store, publication):
    first = store.import_publication(publication)["runId"]
    store.cancel(first)
    old_run, old_definition = store.run(first), store.definitions()
    replacement = artifact(publication)
    assert store.register_core_image(replacement)["registered"]
    assert not store.register_core_image(replacement)["registered"]
    fresh = enqueue(store)
    rerun = enqueue(store, retry_of=first)
    reopened = Store(store.path)
    assert reopened.run(first) == old_run
    assert reopened.definitions() == old_definition
    for run_id in (fresh, rerun):
        run = reopened.run(run_id)
        assert run["image"] == replacement.image
        assert run["effective"]["enhancerVersion"] == "0.1.0"
        assert run["revision"] == "1"
    assert reopened.run(rerun)["retry_of"] == first
    assert "image" not in old_definition[0]


@pytest.mark.parametrize("running", [False, True])
def test_replacement_never_changes_admitted_run_image(store, publication, running):
    run_id = store.import_publication(publication)["runId"]
    if running:
        store.claim()
    before = store.run(run_id)
    store.register_core_image(artifact(publication))
    assert store.run(run_id) == before


def test_duplicate_request_does_not_resolve_again_and_conflicting_request_still_fails(store, publication):
    store.import_publication(version_publication(publication, autoRun=False))
    store.register_core_image(artifact(publication, "a"))
    request_id = str(uuid4())
    first = enqueue(store, request_id)
    store.register_core_image(artifact(publication))
    assert enqueue(store, request_id) == first
    with store.transaction() as db:
        db.execute("DELETE FROM core_images")
    assert enqueue(store, request_id) == first
    with pytest.raises(BenchError, match="idempotency_conflict"):
        enqueue(store, request_id, overrides=Overrides(parameters={"timeout_seconds": 30}))
    with pytest.raises(BenchError, match="core_version_unavailable"):
        enqueue(store)
    assert len(store.runs()) == 1


def test_legacy_and_v2_republication_never_roll_back_registered_image(store, publication):
    old = store.import_publication(publication)
    replacement = artifact(publication)
    store.register_core_image(replacement)
    assert store.import_publication(version_publication(publication)) == {"imported": False, "runId": old["runId"]}
    assert store.import_publication(publication) == {"imported": False, "runId": old["runId"]}
    legacy = publication.model_dump()
    legacy["image"] = artifact(publication, "e").image
    assert not store.import_publication(Publication.model_validate(legacy))["imported"]
    assert len(store.runs()) == 1
    assert store.run(enqueue(store))["image"] == replacement.image
    with pytest.raises(BenchError, match="immutable_revision_conflict"):
        store.import_publication(version_publication(publication, title="Different example"))


def test_revision_conflicts_preserve_json_number_identity(store, publication):
    store.import_publication(publication)
    parameters = publication.definition.baseParameters | {"timeout_seconds": 120.0}
    with pytest.raises(BenchError, match="immutable_revision_conflict"):
        store.import_publication(version_publication(publication, baseParameters=parameters))


def test_unavailable_version_refuses_auto_run_atomically(store, publication):
    original = store.import_publication(publication)["runId"]
    unavailable = version_publication(publication, revision="2", generation=2, enhancerVersion="0.2.0")
    with pytest.raises(BenchError, match="core_version_unavailable"):
        store.import_publication(unavailable)
    assert len(store.definitions()) == len(store.runs()) == 1
    assert store.run(original)["status"] == "queued"


def test_registration_never_queues_work_and_import_without_auto_run_needs_no_image(store, publication):
    value = version_publication(publication, autoRun=False)
    assert store.import_publication(value) == {"imported": True, "runId": None}
    with pytest.raises(BenchError, match="core_version_unavailable"):
        enqueue(store)
    store.register_core_image(artifact(publication))
    assert not store.runs()
    assert not store.import_publication(value)["imported"]
    assert not store.runs()
    assert store.run(enqueue(store))["image"] == artifact(publication).image


def test_variants_are_resolved_independently_and_changed_build_inputs_are_rejected(store, publication):
    store.import_publication(version_publication(publication, autoRun=False))
    models = artifact(publication, "e", "models")
    store.register_core_image(models)
    with pytest.raises(BenchError, match="core_version_unavailable"):
        enqueue(store)
    default = artifact(publication)
    store.register_core_image(default)
    assert store.run(enqueue(store))["image"] == default.image
    model_store = Store(store.path, core_variant="models")
    assert model_store.run(enqueue(model_store))["image"] == models.image
    changed = artifact(publication, "f").model_dump() | {"buildInputSha256": "e" * 64}
    with pytest.raises(BenchError, match="core_version_reused_for_changed_code"):
        store.register_core_image(CoreImage.model_validate(changed))
    assert store.run(enqueue(store))["image"] == default.image


def test_v1_database_upgrade_preserves_runs_request_hashes_and_immutable_definitions(store, publication):
    auto_id = store.import_publication(publication)["runId"]
    key = str(uuid4())
    ui_id = enqueue(store, key)
    before = {run_id: store.run(run_id) for run_id in (auto_id, ui_id)}
    with store.transaction() as db:
        definitions = [tuple(row) for row in db.execute("SELECT * FROM definitions")]
        # This is the v1 layout, including the old image-bound request hashes.
        db.execute("DROP TABLE core_images")
        db.execute("PRAGMA user_version=1")
    upgraded = Store(store.path)
    assert {run_id: upgraded.run(run_id) for run_id in before} == before
    with upgraded.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert [tuple(row) for row in db.execute("SELECT * FROM definitions")] == definitions
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    replacement = artifact(publication)
    upgraded.register_core_image(replacement)
    reopened = Store(store.path)
    assert enqueue(reopened, key) == ui_id
    assert reopened.run(enqueue(reopened))["image"] == replacement.image
    assert reopened.run(auto_id) == before[auto_id]
    assert not reopened.import_publication(version_publication(publication))["imported"]


def test_concurrent_duplicate_requests_freeze_one_binding(store, publication):
    store.import_publication(version_publication(publication, autoRun=False))
    store.register_core_image(artifact(publication, "a"))
    key = str(uuid4())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        calls = [pool.submit(enqueue, store, key) for _ in range(8)]
        update = pool.submit(store.register_core_image, artifact(publication))
        ids = {call.result() for call in calls}
        update.result()
    assert len(ids) == len(store.runs()) == 1
    assert enqueue(store, key) in ids
    assert store.run(enqueue(store))["image"] == artifact(publication).image


def test_api_registration_and_version_only_publication_create_new_bindings(store, publication, contracts):
    with client_for(store, contracts) as client:
        value = version_publication(publication).model_dump(exclude={"image", "coreVersion"})
        assert client.post("/api/publications", json=value, headers=ORIGIN).json() == {
            "error": {"code": "core_version_unavailable"}}
        first_artifact = artifact(publication, "a")
        assert client.post("/api/core-images", json=first_artifact.model_dump(), headers=ORIGIN).status_code == 202
        imported = client.post("/api/publications", json=value, headers=ORIGIN)
        assert imported.status_code == 202
        first = imported.json()["runId"]
        client.post(f"/api/runs/{first}/cancel", json={}, headers=ORIGIN)
        replacement = artifact(publication)
        assert client.post("/api/core-images", json=replacement.model_dump(), headers=ORIGIN).status_code == 202
        rerun = client.post("/api/runs", headers=ORIGIN, json={
            "stableId": "example-widget", "revision": "1", "requestId": str(uuid4()),
            "overrides": {}, "retryOf": first,
        })
        assert rerun.status_code == 202
        assert client.get(f"/api/runs/{first}").json()["image"] == first_artifact.image
        assert client.get("/api/runs/" + rerun.json()["runId"]).json()["image"] == replacement.image
        assert "image" not in client.get("/api/experiments").json()["experiments"][0]


@pytest.mark.parametrize("change,status", [
    ({"runtimeVerified": False}, 422), ({"image": "registry.example.com/example/enhancer:latest"}, 422),
    ({"image": "registry.example.com/unapproved/core@sha256:" + "a" * 64}, 403),
    ({"coreVersion": "example-invalid-version"}, 422), ({"variant": "example-variant"}, 422),
    ({"extra": "EXAMPLE_PRIVATE_CANARY"}, 422),
])
def test_invalid_registration_is_content_free_and_does_not_change_binding(store, publication, contracts, change, status):
    original = artifact(publication)
    store.register_core_image(original)
    with client_for(store, contracts) as client:
        response = client.post("/api/core-images", headers=ORIGIN, json=original.model_dump() | change)
        assert response.status_code == status
        assert "EXAMPLE_PRIVATE_CANARY" not in response.text
        assert client.post("/api/core-images", json=original.model_dump()).status_code == 403
    store.import_publication(version_publication(publication, autoRun=False))
    assert store.run(enqueue(store))["image"] == original.image


def test_register_cli_delivers_only_verified_release_metadata(monkeypatch, tmp_path, publication, contracts):
    value = artifact(publication)
    path = tmp_path / "example-release.json"
    path.write_text(value.model_dump_json())
    monkeypatch.setattr("sys.argv", ["enhancement-bench", "register-core", str(path)])
    monkeypatch.setattr(cli, "default_contracts", lambda: contracts.directory)
    monkeypatch.setenv("BENCH_DELIVERY_URL", "https://bench.example.com")
    for key in ("BENCH_CF_ACCESS_CLIENT_ID", "BENCH_CF_ACCESS_CLIENT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    requests = []

    def send(request):
        requests.append(request)
        assert request.url.path == "/api/core-images"
        assert request.headers["Origin"] == "https://bench.example.com"
        assert json.loads(request.content) == value.model_dump()
        return httpx.Response(202, json={"registered": True, "coreVersion": "0.1.0", "variant": "default"})

    client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(send), **kwargs))
    cli.main()
    assert len(requests) == 1


@pytest.mark.parametrize("receipt", [
    {"registered": True, "coreVersion": "0.2.0", "variant": "default"},
    {"registered": True, "coreVersion": "0.1.0", "variant": "models"},
    {"registered": "yes", "coreVersion": "0.1.0", "variant": "default"},
])
def test_registration_requires_matching_acknowledgement(monkeypatch, publication, receipt):
    client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(
        lambda request: httpx.Response(202, json=receipt)), **kwargs))
    with pytest.raises(BenchError, match="core_registration_acknowledgement_invalid"):
        cli.register_core_image(artifact(publication), "https://bench.example.com")


def test_api_and_worker_select_the_same_catalog_variant():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    services = yaml.safe_load((root / "deployment/bench/compose.yaml").read_text())["services"]
    assert services["bench-api"]["environment"]["BENCH_CORE_VARIANT"] == services["bench-worker"]["environment"]["BENCH_CORE_VARIANT"]


@pytest.mark.parametrize("status", [302, 403, 503])
def test_registration_cli_failure_stops_the_job_without_echoing_response(
        monkeypatch, tmp_path, publication, contracts, capsys, status):
    path = tmp_path / "example-release.json"
    path.write_text(artifact(publication).model_dump_json())
    monkeypatch.setattr("sys.argv", ["enhancement-bench", "register-core", str(path)])
    monkeypatch.setattr(cli, "default_contracts", lambda: contracts.directory)
    monkeypatch.setenv("BENCH_DELIVERY_URL", "https://bench.example.com")
    monkeypatch.setenv("BENCH_CF_ACCESS_CLIENT_ID", "example-client")
    monkeypatch.setenv("BENCH_CF_ACCESS_CLIENT_SECRET", "example-not-a-secret")
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, text="EXAMPLE_PRIVATE_RESPONSE",
                              headers={"Location": "https://other.example.com"})

    client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client(
        transport=httpx.MockTransport(respond), **kwargs))
    with pytest.raises(SystemExit) as failed:
        cli.main()
    assert failed.value.code == 1
    assert len(requests) == 1
    assert capsys.readouterr().out == f"core_registration_delivery_failed_http_{status}\n"
