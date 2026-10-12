import concurrent.futures
import json
import sqlite3
from uuid import uuid4

import pytest

from enhancement_bench.definitions import Overrides, Publication
from enhancement_bench.errors import BenchError
from enhancement_bench.store import Store

from conftest import changed


def test_duplicate_and_late_publications_create_exactly_one_eligible_run(store, publication):
    latest = changed(publication, revision="3", generation=3)
    first = store.import_publication(latest)
    assert store.import_publication(latest) == {"imported": False, "runId": first["runId"]}
    assert store.import_publication(publication)["runId"] is None
    assert store.import_publication(changed(publication, revision="2", generation=2))["runId"] is None
    assert len(store.runs()) == 1
    assert store.run(first["runId"])["image"] == publication.image


def test_new_revision_supersedes_queued_but_never_rewrites_running(store, publication):
    first = store.import_publication(publication)["runId"]
    second = store.import_publication(changed(publication, revision="2", generation=2))["runId"]
    assert store.run(first)["status"] == "superseded"
    assert {a["status"] for a in store.run(first)["attempts"]} == {"superseded"}
    assert store.claim()["id"] == second
    third = store.import_publication(changed(publication, revision="3", generation=3))["runId"]
    assert store.run(second)["status"] == "running"
    assert store.run(third)["status"] == "queued"
    assert store.claim() is None


def test_disabled_new_revision_does_not_hide_latest_eligible(store, publication):
    store.import_publication(changed(publication, revision="4", generation=4, autoRun=False))
    assert store.import_publication(publication)["runId"]


def test_revision_and_generation_conflicts_are_atomic(store, publication):
    store.import_publication(publication)
    with pytest.raises(BenchError, match="immutable_revision_conflict"):
        store.import_publication(changed(publication, title="Changed immutable title"))
    with pytest.raises(BenchError, match="generation_conflict"):
        store.import_publication(changed(publication, revision="another"))
    assert len(store.definitions()) == len(store.runs()) == 1


def test_concurrent_duplicate_delivery_and_claim(store, publication):
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.import_publication(publication), range(16)))
        claims = list(pool.map(lambda _: store.claim(), range(16)))
    assert len({r["runId"] for r in results}) == 1
    assert sum(bool(r) for r in claims) == 1


def test_ui_overrides_and_results_survive_restart_without_git_change(store, publication):
    store.import_publication(changed(publication, autoRun=False))
    overrides = Overrides(parameters={"timeout_seconds": 42}, unitIds=["script"])
    key = str(uuid4())
    run_id = store.enqueue_ui("example-widget", "1", overrides, key)
    assert store.enqueue_ui("example-widget", "1", overrides, key) == run_id
    with pytest.raises(BenchError, match="idempotency_conflict"):
        store.enqueue_ui("example-widget", "1", Overrides(), key)
    run = store.claim()
    attempt = run["attempts"][0]
    store.attempt_started(run_id, attempt["id"], {"example": "request"})
    store.attempt_finished(run_id, attempt["id"], "succeeded", {"unknown_metric": None})
    store.cleanup_confirmed(run_id)
    store.finish(run_id, "succeeded", assertion="not_evaluated")
    reopened = Store(store.path).run(run_id)
    assert reopened["effective"]["units"][0]["parameters"]["timeout_seconds"] == 42
    assert reopened["attempts"][0]["result"] == {"unknown_metric": None}
    assert reopened["status"] == "succeeded"
    assert reopened["correlation_id"] == run["correlation_id"]
    assert store.definitions()[0]["baseParameters"]["timeout_seconds"] == 120


def test_recovery_interrupts_and_holds_slot_without_replay(store, publication):
    first = store.import_publication(publication)["runId"]
    run = store.claim()
    store.attempt_started(first, run["attempts"][0]["id"], {"consumer": {"binding_id": "example-consumer"}})
    store.enqueue_ui("example-widget", "1", Overrides(), str(uuid4()))
    reopened = Store(store.path)
    reopened.recover()
    assert reopened.run(first)["status"] == "interrupted"
    assert reopened.claim() is None
    reopened.cleanup_confirmed(first)
    assert reopened.claim() is None
    with pytest.raises(BenchError, match="retry_requires_reconciled"):
        reopened.enqueue_ui("example-widget", "1", Overrides(), str(uuid4()), first)
    reopened.acknowledge_remote_stopped(first, "example-operator-receipt")
    assert reopened.claim() is not None
    assert reopened.run(first)["status"] == "interrupted"


def test_cancel_queued_and_running_are_distinct(store, publication):
    first = store.import_publication(publication)["runId"]
    assert store.cancel(first)["status"] == "cancelled"
    second = store.enqueue_ui("example-widget", "1", Overrides(), str(uuid4()), first)
    store.claim()
    value = store.cancel(second)
    assert value["status"] == "running" and value["cancel_requested"]
    assert store.cancel(second)["events"] == value["events"]


def test_invalid_overrides_do_not_enqueue(store, publication):
    store.import_publication(publication)
    for overrides in (Overrides(parameters={"unknown": 1}), Overrides(parameters={"timeout_seconds": True}),
                      Overrides(parameters={"timeout_seconds": 900}), Overrides(unitIds=["missing"])):
        with pytest.raises(BenchError):
            store.enqueue_ui("example-widget", "1", overrides, str(uuid4()))
    assert len(store.runs()) == 1


def test_objective_and_per_unit_steering_are_immutable_effective_values(store, publication):
    store.import_publication(publication)
    overrides = Overrides(unitIds=["consumer"], objective={"description": "Improve the fictional acceptance instructions."},
                          unitSteering={"consumer": {"style": "concise", "focus": ["acceptance"]}})
    run_id = store.enqueue_ui("example-widget", "1", overrides, str(uuid4()))
    run = Store(store.path).run(run_id)
    unit = run["effective"]["units"][0]
    assert unit["objective"]["description"] == overrides.objective["description"]
    assert unit["steering"]["style"] == "concise" and unit["steering"]["focus"] == ["acceptance"]
    assert unit["objective"]["targets"][0]["direction"] == "increase"
    assert store.definitions()[0]["units"][1]["steering"]["style"] == "structured"


def test_database_enforces_immutable_run_bindings(store, publication):
    run_id = store.import_publication(publication)["runId"]
    with store.transaction() as db, pytest.raises(sqlite3.IntegrityError, match="immutable_run_settings"):
        db.execute("UPDATE runs SET image='mutable:latest' WHERE id=?", (run_id,))


def test_newer_database_is_rejected(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(BenchError, match="unsupported_database_schema"):
        Store(path)


def test_definition_rejects_mutable_images_and_remote_schema(publication):
    from pydantic import ValidationError

    payload = publication.model_dump()
    payload["image"] = "registry.example.com/example/enhancer:latest"
    with pytest.raises(ValidationError):
        Publication.model_validate(payload)
    payload = publication.model_dump()
    payload["definition"]["parameterSchema"]["$ref"] = "https://example.com/schema"
    with pytest.raises(ValidationError):
        Publication.model_validate(payload)
