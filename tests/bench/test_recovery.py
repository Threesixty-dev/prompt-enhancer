"""Synthetic failure recovery; no model or Docker daemon access."""

import copy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from enhancement_bench.analysis import inspect_run
from enhancement_bench.definitions import Overrides
from enhancement_bench.errors import BenchError
from enhancement_bench.recovery import failure_summary, recovery_summary
from enhancement_bench.store import Store
from enhancement_bench.worker import Worker
from test_api import ORIGIN, client_for
from test_client_worker import make_worker


@pytest.fixture
def clock(monkeypatch):
    import enhancement_bench.store as storage
    now = SimpleNamespace(value=1000.0)
    monkeypatch.setattr(storage, "time", SimpleNamespace(time=lambda: now.value))
    return now


def interrupted(store, publication, contracts):
    run_id = store.import_publication(publication)["runId"]
    run = store.claim()
    attempt = run["attempts"][0]
    store.attempt_started(run_id, attempt["id"], contracts.request(run, attempt))
    store.attempt_finished(run_id, attempt["id"], "interrupted", {
        "errors": [{"code": "gateway_io_timeout", "stage": "evaluate_original", "operation_id": None}],
        "private": "example-private-response-canary"})
    store.finish(run_id, "interrupted", "core_uncertain")
    return run_id


def test_cleanup_retries_in_live_loop_without_replay_and_keeps_remote_hold(store, publication, contracts, result_template, clock):
    run_id = interrupted(store, publication, contracts)
    worker, core, runtime = make_worker(store, contracts, result_template, admission_check=lambda: False)
    runtime.fail_cleanup = True
    worker.reconcile()  # A Docker outage must not kill worker startup.
    assert store.run(run_id)["cleanup_check"]["attempts"] == 1
    for _ in range(5):
        assert not worker.step()
    assert store.run(run_id)["cleanup_check"]["attempts"] == 1
    runtime.fail_cleanup = False
    clock.value += 5
    assert not worker.step()  # Cleanup runs even when consumer readiness is false.
    run = store.run(run_id)
    assert not run["cleanup_pending"] and run["reconciliation_required"]
    assert run["cleanup_check"]["state"] == "confirmed"
    assert recovery_summary(run)["nextAction"] == "confirm_remote_stop"
    assert not core.requests and not runtime.launched
    assert run["error_code"] == "core_uncertain"
    assert run["attempts"][0]["result"]["errors"][0]["code"] == "gateway_io_timeout"


def test_cleanup_budget_survives_restarts_and_manual_request_is_deduplicated(store, publication, contracts, result_template, clock):
    run_id = interrupted(store, publication, contracts)
    worker, core, runtime = make_worker(store, contracts, result_template)
    runtime.fail_cleanup = True
    for delay, expected in [(0, 1), (5, 2), (30, 3), (600, 3)]:
        clock.value += delay
        worker = Worker(Store(store.path), contracts, runtime)
        worker.reconcile()
        assert not worker.step()
        assert store.run(run_id)["cleanup_check"]["attempts"] == expected
    assert recovery_summary(store.run(run_id))["nextAction"] == "retry_cleanup"
    before = store.run(run_id)
    with client_for(store, contracts) as client:
        for _ in range(2):
            assert client.post(f"/api/runs/{run_id}/cleanup-check", json={}, headers=ORIGIN).status_code == 202
    pending = store.run(run_id)
    assert pending["cleanup_check"]["attempts"] == 0
    assert sum(e["state"] == "cleanup_check_requested" for e in pending["events"]) == 1
    assert pending["attempts"] == before["attempts"] and pending["effective"] == before["effective"]
    runtime.fail_cleanup = False
    assert not worker.step()
    assert store.run(run_id)["reconciliation_required"]
    assert not core.requests and not runtime.launched


def test_cleanup_crash_reservation_expires_without_resetting_budget(store, publication, contracts, clock):
    run_id = interrupted(store, publication, contracts)
    for expected in range(1, 4):
        assert store.claim_cleanup_check()["id"] == run_id
        assert store.run(run_id)["cleanup_check"]["attempts"] == expected
        store.request_cleanup_check(run_id)
        assert store.claim_cleanup_check() is None
        clock.value += 120
        store = Store(store.path)
    assert store.claim_cleanup_check() is None
    assert recovery_summary(store.run(run_id))["nextAction"] == "retry_cleanup"
    assert store.run(run_id)["cleanup_pending"] and store.run(run_id)["reconciliation_required"]


def test_ownership_mismatch_never_retries_automatically(store, publication, contracts, clock):
    run_id = interrupted(store, publication, contracts)
    calls = []
    def reject(*args):
        calls.append(args)
        raise BenchError("container_ownership_mismatch")
    worker = Worker(store, contracts, SimpleNamespace(cleanup=reject))
    worker.reconcile()
    clock.value += 600
    assert not worker.step() and len(calls) == 1
    assert store.run(run_id)["cleanup_check"]["error_code"] == "container_ownership_mismatch"


def test_local_only_failure_recovers_and_next_queued_run_executes_once(store, publication, contracts, result_template, clock):
    run_id = store.import_publication(publication)["runId"]
    worker, core, runtime = make_worker(store, contracts, result_template)
    runtime.fail_cleanup = True
    assert worker.step()
    old = copy.deepcopy(store.run(run_id))
    assert not old["reconciliation_required"]
    next_id = store.enqueue_ui(publication.definition.stableId, "1", Overrides(), str(uuid4()))
    assert not worker.step()
    runtime.fail_cleanup = False
    clock.value += 5
    assert worker.step() and store.run(next_id)["status"] == "succeeded"
    recovered = store.run(run_id)
    assert recovered["status"] == "interrupted" and recovered["attempts"] == old["attempts"]
    assert len(core.requests) == 4 and len(runtime.launched) == 2
    assert not worker.step()


def test_api_global_hold_and_primary_cause_are_content_free_and_keep_history(store, publication, contracts, clock):
    run_id = interrupted(store, publication, contracts)
    with client_for(store, contracts) as client:
        detail = client.get(f"/api/runs/{run_id}").json()
        queue = client.get("/api/recovery").json()
        history = client.get("/api/runs").json()["runs"][0]
        assert queue["total"] == 1 and queue["runs"][0]["id"] == run_id
        assert queue["runs"][0]["failure"] == history["failure"] == detail["failure"]
        assert detail["failure"]["code"] == "gateway_io_timeout"
        assert detail["failure"]["stage"] == "evaluate_original"
        assert detail["failure"]["operationId"] is None
        assert "example-private-response-canary" not in json.dumps(queue)
        assert publication.definition.subjects[0].text not in json.dumps(history)
        assert client.get("/api/runs?status=succeeded").json()["runs"] == []
        assert client.get("/api/recovery").json()["blocked"]  # Not hidden by filters.
        assert client.post(f"/api/runs/{run_id}/reconcile", json={"remoteStopped": True,
            "evidenceReference": "example-stop-check"}, headers=ORIGIN).status_code == 409
        store.cleanup_confirmed(run_id)
        retained = store.run(run_id)
        for _ in range(2):
            assert client.post(f"/api/runs/{run_id}/reconcile", json={"remoteStopped": True,
                "evidenceReference": "example-stop-check"}, headers=ORIGIN).status_code == 200
        recovered = client.get(f"/api/runs/{run_id}").json()
        assert recovered["recovery"]["reconciliation"]["evidence_reference"] == "example-stop-check"
        assert recovered["recovery"]["remoteCompletion"] == "operator_confirmed"
        assert recovered["failure"] == detail["failure"] and recovered["attempts"] == retained["attempts"]
        assert not client.get("/api/recovery").json()["blocked"]
        assert recovered["recovery"] == inspect_run(store.run(run_id))["recovery"]


@pytest.mark.parametrize("headers,body,status", [({}, {}, 403), (ORIGIN, {"force": True}, 422)])
def test_cleanup_request_requires_same_origin_and_rejects_unknown_fields(store, publication, contracts, headers, body, status):
    run_id = interrupted(store, publication, contracts)
    before = store.run(run_id)
    with client_for(store, contracts) as client:
        assert client.post(f"/api/runs/{run_id}/cleanup-check", json=body, headers=headers).status_code == status
    assert store.run(run_id) == before


def test_active_and_queued_runs_are_not_recovery_blockers(store, publication, contracts):
    run_id = store.import_publication(publication)["runId"]
    assert not store.recovery_queue()["blocked"]
    store.claim()
    assert not store.recovery_queue()["blocked"]
    with client_for(store, contracts) as client:
        assert client.post(f"/api/runs/{run_id}/cleanup-check", json={}, headers=ORIGIN).status_code == 409
    assert recovery_summary(store.run(run_id))["nextAction"] == "observe_run"


def test_historical_failed_review_is_explicit_without_rewriting_success(store, publication, contracts):
    run_id = store.import_publication(publication)["runId"]
    run = store.claim()
    for attempt in run["attempts"]:
        store.attempt_started(run_id, attempt["id"], contracts.request(run, attempt))
        store.attempt_finished(run_id, attempt["id"], "succeeded", {
            "workflow_result": {"review": {"state": "reply_invalid"}}})
    store.cleanup_confirmed(run_id)
    store.finish(run_id, "succeeded")
    summary = store.runs()[0]
    assert summary["status"] == "succeeded" and summary["failure"]["code"] == "workflow_review_reply_invalid"
    assert summary["failure"] == failure_summary(store.run(run_id))


def test_old_database_adds_cleanup_metadata_without_changing_runs(store, publication, contracts):
    run_id = interrupted(store, publication, contracts)
    before = store.run(run_id)
    with store.transaction() as db:
        db.execute("DROP TABLE cleanup_checks")
    reopened = Store(store.path)
    assert reopened.run(run_id) == before
    assert reopened.claim_cleanup_check()["id"] == run_id
    assert reopened.run(run_id)["reconciliation_required"]


def test_unexpected_cleanup_failure_is_sanitized_and_does_not_kill_worker(store, publication, contracts):
    run_id = interrupted(store, publication, contracts)
    def fail(*args):
        raise RuntimeError("example-private-exception-canary")
    Worker(store, contracts, SimpleNamespace(cleanup=fail)).reconcile()
    run = store.run(run_id)
    assert run["cleanup_check"]["error_code"] == "container_cleanup_unconfirmed"
    assert "example-private-exception-canary" not in json.dumps(run)
