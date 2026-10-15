import copy
from uuid import uuid4

import pytest

from enhancement_bench.definitions import Overrides, effective_settings
from enhancement_bench.store import Store
from test_api import ORIGIN, client_for


def profile(publication):
    return copy.deepcopy(publication.definition.evaluatorProfile["evaluators"]) + [{
        "evaluator_id": "example-judge", "kind": "rubric", "binding_id": "example-qwen",
        "rubric": "acceptance_testability",
        "generation": {"max_output_chars": 1000, "max_tokens": None, "temperature": 0},
    }]


def run_body(publication, evaluators):
    return {"stableId": publication.definition.stableId, "revision": publication.definition.revision,
            "requestId": str(uuid4()), "overrides": {"evaluators": evaluators}}


def test_routing_is_frozen_for_every_attempt_and_survives_restart_and_rerun(store, publication, contracts):
    store.import_publication(publication)
    original = store.definitions()
    body = run_body(publication, profile(publication))
    with client_for(store, contracts) as client:
        created = client.post("/api/runs", json=body, headers=ORIGIN)
        assert created.status_code == 202
        run_id = created.json()["runId"]
        assert client.post("/api/runs", json=body, headers=ORIGIN).json()["runId"] == run_id
        altered = copy.deepcopy(body)
        altered["overrides"]["evaluators"][1]["binding_id"] = "example-other-model"
        assert client.post("/api/runs", json=altered, headers=ORIGIN).status_code == 409
        client.post(f"/api/runs/{run_id}/cancel", json={}, headers=ORIGIN)
    reopened = Store(store.path)
    run = reopened.run(run_id)
    selected = run["effective"]["evaluatorProfile"]
    assert selected["evaluators"] == body["overrides"]["evaluators"]
    assert selected["revision"].startswith("run-")
    assert selected["revision"] != publication.definition.evaluatorProfile["revision"]
    for attempt in run["attempts"]:
        assert contracts.request(run, attempt)["evaluation"] == selected
    with client_for(reopened, contracts) as client:
        retry = body | {"requestId": str(uuid4()), "retryOf": run_id}
        retry_id = client.post("/api/runs", json=retry, headers=ORIGIN).json()["runId"]
        assert reopened.run(retry_id)["effective"]["evaluatorProfile"] == selected
        cards = client.get("/api/runs?summary=true&model=example-qwen").json()
        assert {row["id"] for row in cards["runs"]} == {run_id, retry_id}
    assert reopened.definitions() == original
    assert reopened.run(run_id)["effective"]["evaluatorProfile"] == selected


def test_unmodified_profile_preserves_legacy_effective_configuration(publication):
    effective = effective_settings(publication.definition, Overrides())
    assert "evaluators" not in effective["overrides"]
    assert effective["evaluatorProfile"] == publication.definition.evaluatorProfile
    explicit = effective_settings(publication.definition, Overrides(
        evaluators=publication.definition.evaluatorProfile["evaluators"]))
    assert explicit["evaluatorProfile"] == effective["evaluatorProfile"]


@pytest.mark.parametrize("mutation,error", [
    (lambda values: values.append(copy.deepcopy(values[0])), "duplicate_evaluator"),
    (lambda values: values.pop(0), "referenced_evaluator_required"),
    (lambda values: values[0].update(kind="rubric", rubric="task_definition"), "evaluator_metric_incompatible"),
    (lambda values: values[1].pop("rubric"), "invalid_evaluator_settings"),
    (lambda values: values[1].update(target="example-private-canary"), "invalid_evaluator_settings"),
    (lambda values: values[0].update(generation={"max_tokens": None}), "invalid_evaluator_settings"),
    (lambda values: values[1].update(kind="embedding", rubric=None, generation=None), "invalid_evaluator_settings"),
    (lambda values: values[1].update(endpoint="https://example.com/private-canary"), "core_contract_violation"),
    (lambda values: values[1].update(binding_id="https://example.com/private-canary"), "core_contract_violation"),
])
def test_invalid_routes_do_not_enqueue_or_expose_content(store, publication, contracts, mutation, error):
    store.import_publication(publication)
    before = store.runs()
    values = profile(publication)
    mutation(values)
    with client_for(store, contracts) as client:
        response = client.post("/api/runs", json=run_body(publication, values), headers=ORIGIN)
    assert response.status_code in {422, 502}
    assert response.json() == {"error": {"code": error}}
    assert "private-canary" not in response.text
    assert store.runs() == before


@pytest.mark.parametrize("kind,settings", [
    ("classifier", {"target": "The fictional task requests tests."}),
    ("embedding", {"target": "A fictional implementation with unit tests."}),
    ("rubric", {"rubric": "constraint_precision"}),
])
def test_typed_model_routes_are_admitted(store, publication, contracts, kind, settings):
    store.import_publication(publication)
    values = profile(publication)
    values[1] = {"evaluator_id": "example-judge", "kind": kind, "binding_id": "example-model", **settings}
    with client_for(store, contracts) as client:
        response = client.post("/api/runs", json=run_body(publication, values), headers=ORIGIN)
    assert response.status_code == 202


@pytest.mark.parametrize("values", [[], [{"evaluator_id": "example"}] * 9])
def test_evaluator_count_is_bounded(store, publication, contracts, values):
    store.import_publication(publication)
    with client_for(store, contracts) as client:
        assert client.post("/api/runs", json=run_body(publication, values), headers=ORIGIN).status_code == 422
