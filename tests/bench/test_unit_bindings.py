import copy
from uuid import uuid4

import pytest

from enhancement_bench.definitions import Overrides, Publication, fingerprint
from enhancement_bench.store import Store
from test_api import client_for, ORIGIN
from test_client_worker import make_worker


def test_sibling_models_route_independently_and_keep_shared_evaluation(store, publication, contracts, result_template):
    payload = publication.model_dump()
    first = payload["definition"]["units"][1]
    second = copy.deepcopy(first)
    second.update(id="comparison", consumerBinding={"binding_id": "example-comparison-model"})
    payload["definition"]["units"] = [first, second]
    publication = Publication.model_validate(payload)
    run_id = store.import_publication(publication)["runId"]
    worker, core, runtime = make_worker(store, contracts, result_template)
    worker.step()
    run = Store(store.path).run(run_id)
    assert run["status"] == "succeeded"
    assert [r["consumer"]["binding_id"] for r in core.requests] == ["example-consumer", "example-comparison-model"]
    assert all(r["consumer"]["provider"] == publication.definition.consumerBinding["provider"] for r in core.requests)
    assert core.requests[0]["evaluation"] == core.requests[1]["evaluation"]
    assert len(runtime.launched) == 1
    for attempt, request, unit in zip(run["attempts"], core.requests, run["effective"]["units"]):
        assert attempt["result"]["consumer_binding"] == unit["consumerBinding"] == request["consumer"]


def test_ui_binding_override_is_immutable_and_survives_retry(store, publication, contracts):
    with client_for(store, contracts) as client:
        client.post("/api/publications", json=publication.model_dump(), headers=ORIGIN)
        headers = ORIGIN
        overrides = {"unitIds": ["consumer"], "unitConsumerBindings": {"consumer": {"binding_id": "example-ui-model"}}}
        payload = {"stableId": "example-widget", "revision": "1", "requestId": str(uuid4()), "overrides": overrides}
        response = client.post("/api/runs", json=payload, headers=headers)
        assert response.status_code == 202
        run_id = response.json()["runId"]
        assert client.post("/api/runs", json=payload, headers=headers).json()["runId"] == run_id
        run = Store(store.path).run(run_id)
        binding = run["effective"]["units"][0]["consumerBinding"]
        assert binding == {"binding_id": "example-ui-model", "provider": "openhands_acp"}
        client.post(f"/api/runs/{run_id}/cancel", json={}, headers=headers)
        payload.update(requestId=str(uuid4()), retryOf=run_id)
        payload["overrides"]["unitConsumerBindings"]["consumer"] = binding
        retry = client.post("/api/runs", json=payload, headers=headers)
        assert retry.status_code == 202
        assert Store(store.path).run(retry.json()["runId"])["effective"]["units"][0]["consumerBinding"] == binding
        assert store.definitions()[0]["consumerBinding"] == publication.definition.consumerBinding


@pytest.mark.parametrize("binding", [
    {"binding_id": "example-model", "endpoint": "https://example.invalid/v1"},
    {"binding_id": "example-model", "credential": "example-not-a-secret"},
    {"binding_id": "example-model", "provider": "unsupported"},
])
def test_binding_authority_is_validated_before_storage(store, publication, contracts, binding):
    payload = publication.model_dump()
    payload["definition"]["units"][1]["consumerBinding"] = binding
    with client_for(store, contracts) as client:
        response = client.post("/api/publications", json=payload, headers=ORIGIN)
        assert response.status_code == 502
    assert not store.definitions() and not store.runs()


def test_script_binding_and_unknown_unit_override_are_rejected(store, publication, contracts):
    store.import_publication(publication)
    with client_for(store, contracts) as client:
        for unit in ("script", "missing"):
            response = client.post("/api/runs", headers=ORIGIN, json={
                "stableId": "example-widget", "revision": "1", "requestId": str(uuid4()),
                "overrides": {"unitConsumerBindings": {unit: {"binding_id": "example-model"}}}})
            assert response.status_code == 400
    assert len(store.runs()) == 1


def test_legacy_publication_identity_and_queued_requests_remain_compatible(store, publication, contracts):
    legacy = publication.model_dump()
    for unit in legacy["definition"]["units"]:
        del unit["consumerBinding"]
    first = store.import_publication(Publication.model_validate(legacy))
    assert store.definitions()[0]["specHash"] == fingerprint(legacy)
    assert store.import_publication(publication)["runId"] == first["runId"]
    run = store.run(first["runId"])
    for unit in run["effective"]["units"]:
        del unit["consumerBinding"]
    assert contracts.request(run, run["attempts"][1])["consumer"] == publication.definition.consumerBinding
