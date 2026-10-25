import copy
import json
from types import SimpleNamespace

import httpx
import pytest

from enhancement_bench.client import CoreClient
from enhancement_bench.definitions import Overrides
from enhancement_bench.errors import BenchError
from enhancement_bench.protocol import IDENTITY, execution_id
from enhancement_bench.worker import Worker, exclusive_worker


class SyntheticCore:
    """Deliberate test double. Does not establish real-core or model acceptance."""
    def __init__(self, template):
        self.template = template
        self.requests, self.deleted, self.cancelled = [], [], []
        self.lose_ack, self.keep_running, self.mismatch, self.fail_assertions = False, False, False, False

    def progress(self, request, status="succeeded", sequence=2):
        return {**{k: request[k] for k in IDENTITY}, "protocol_version": "enhancement.v1",
                "execution_id": execution_id(request), "status": status,
                "stage": "finished" if status == "succeeded" else "generate", "sequence": sequence,
                "result_available": status == "succeeded"}

    def handle(self, request):
        path = request.url.path
        if path == "/health/ready":
            return httpx.Response(200, json={"protocol_version": "enhancement.v1", "core_version": "0.1.0",
                                           "ready": True, "active": 0, "retained": 0, "capacity": 1, "reason": "ready"})
        if path == "/v1/capabilities":
            return httpx.Response(200, json={"protocol_version": "enhancement.v1", "core_version": "0.1.0"})
        if path == "/v1/executions":
            value = json.loads(request.content)
            self.requests.append(value)
            if self.lose_ack:
                raise httpx.ReadTimeout("synthetic lost acknowledgement")
            return httpx.Response(202, json=self.progress(value, "running" if self.keep_running else "succeeded"))
        current = self.requests[-1]
        if request.method == "DELETE":
            self.deleted.append(execution_id(current))
            return httpx.Response(204)
        if path.endswith("/cancel"):
            self.cancelled.append(execution_id(current))
            return httpx.Response(202, json=self.progress(current, "cancelling", 3))
        if path.endswith("/result"):
            result = copy.deepcopy(self.template)
            result.update({k: current[k] for k in IDENTITY})
            result.update(execution_id=execution_id(current), effective_parameters=current["parameters"],
                          evaluation_profile=current["evaluation"], strategy=current["strategy"], consumer_binding=current["consumer"],
                          effective_objective=current["objective"], effective_steering=current["steering"])
            if self.mismatch:
                result["correlation_id"] = "example-wrong-correlation"
            if self.fail_assertions:
                result["assertion_outcome"] = "failed"
            return httpx.Response(200, json=result)
        return httpx.Response(200, json=self.progress(current, "running" if self.keep_running else "succeeded", 3))


class SyntheticRuntime:
    def __init__(self):
        self.launched, self.cleaned, self.fail_cleanup = [], [], False

    def launch(self, run):
        self.launched.append(run["image"])
        return "http://127.0.0.1:8091"

    def cleanup(self, run_id, name):
        if self.fail_cleanup:
            raise BenchError("container_cleanup_unconfirmed")
        self.cleaned.append((run_id, name))


def make_worker(store, contracts, template, **kwargs):
    core, runtime = SyntheticCore(template), SyntheticRuntime()
    worker = Worker(store, contracts, runtime, client_factory=lambda endpoint, c: CoreClient(endpoint, c, transport=httpx.MockTransport(core.handle)), poll_seconds=0.001, **kwargs)
    return worker, core, runtime


def test_two_siblings_use_same_evaluator_and_digest_with_correlated_results(store, publication, contracts, result_template):
    run_id = store.import_publication(publication)["runId"]
    worker, core, runtime = make_worker(store, contracts, result_template)
    for side in ("before", "after"):
        core.template[side][0]["metrics"][0].update(state="unknown", value=None, label=None, reason="example_unknown")
    core.template["deltas"][0].update(state="unknown", value=None, reason="metric_unknown")
    assert worker.step()
    run = store.run(run_id)
    assert run["status"] == "succeeded" and not run["cleanup_pending"]
    assert len(core.requests) == len(core.deleted) == 2
    assert len(runtime.launched) == len(runtime.cleaned) == 1
    assert core.requests[0]["evaluation"] == core.requests[1]["evaluation"]
    assert core.requests[0]["consumer"] is None
    assert core.requests[1]["consumer"] == publication.definition.consumerBinding
    assert core.requests[1]["steering"]["style"] == "structured"
    assert core.requests[1]["objective"]["targets"][0]["direction"] == "increase"
    assert run["attempts"][1]["result"]["effective_steering"] == core.requests[1]["steering"]
    assert len({r["attempt_id"] for r in core.requests}) == 2
    assert all(a["result"]["run_id"] == run_id for a in run["attempts"])
    assert all(a["result"]["deltas"][0]["value"] is None for a in run["attempts"])


def test_assertion_failure_is_not_execution_failure(store, publication, contracts, result_template):
    run_id = store.import_publication(publication)["runId"]
    worker, core, _ = make_worker(store, contracts, result_template)
    core.fail_assertions = True
    worker.step()
    assert store.run(run_id)["status"] == "succeeded"
    assert store.run(run_id)["assertion_outcome"] == "failed"


def test_consumer_startup_gate_keeps_run_queued_without_attempt_admission(store, publication, contracts, result_template):
    run_id = store.import_publication(publication)["runId"]
    ready = [False]
    worker, core, runtime = make_worker(store, contracts, result_template, admission_check=lambda: ready[0])
    assert not worker.step()
    assert store.run(run_id)["status"] == "queued"
    assert not core.requests and not runtime.launched
    ready[0] = True
    assert worker.step() and store.run(run_id)["status"] == "succeeded"


@pytest.mark.parametrize("mode", ["lose_ack", "mismatch", "keep_running"])
def test_uncertain_delivery_never_replays_and_blocks_next_consumer(store, publication, contracts, result_template, mode):
    publication.definition.units = publication.definition.units[1:]
    run_id = store.import_publication(publication)["runId"]
    worker, core, runtime = make_worker(store, contracts, result_template, run_seconds=0.04, cancel_seconds=0.01)
    setattr(core, mode, True)
    worker.step()
    run = store.run(run_id)
    assert run["status"] == "interrupted"
    assert run["reconciliation_required"] and not run["cleanup_pending"]
    assert len(core.requests) == 1 and len(runtime.cleaned) == 1
    assert not worker.step()
    if mode == "keep_running":
        assert len(core.cancelled) == 1


def test_cleanup_failure_holds_admission_until_recovery(store, publication, contracts, result_template, monkeypatch):
    import enhancement_bench.store as storage
    now = [1000.0]
    monkeypatch.setattr(storage, "time", SimpleNamespace(time=lambda: now[0]))
    run_id = store.import_publication(publication)["runId"]
    worker, _, runtime = make_worker(store, contracts, result_template)
    runtime.fail_cleanup = True
    worker.step()
    assert store.run(run_id)["cleanup_pending"]
    assert not worker.step()
    runtime.fail_cleanup = False
    now[0] += 5
    worker.step()
    assert not store.run(run_id)["cleanup_pending"]


@pytest.mark.parametrize("terminal", ["uncertain", "cancelled", "timed_out", "failed"])
@pytest.mark.parametrize("trigger", ["deadline", "user", "user_crosses_deadline", "core"])
def test_run_deadline_cause_preserves_core_result_and_recovery_state(
        store, publication, contracts, result_template, monkeypatch, terminal, trigger):
    import enhancement_bench.worker as worker_module

    first = copy.deepcopy(publication.definition.units[-1])
    sibling = copy.deepcopy(first)
    sibling.id = "example-pending"
    publication.definition.units = [first, sibling]
    run_id = store.import_publication(publication)["runId"]
    worker, core, runtime = make_worker(store, contracts, result_template, run_seconds=1)
    clock = SimpleNamespace(value=0.0)
    monkeypatch.setattr(worker_module, "time", SimpleNamespace(
        monotonic=lambda: clock.value, sleep=lambda seconds: None))
    core.keep_running = True
    handle = core.handle
    delayed_cancellation = False

    def complete_after_cancellation(request):
        nonlocal delayed_cancellation
        response = handle(request)
        path = request.url.path
        if path == "/v1/executions":
            if trigger == "deadline":
                clock.value = 2.0
            elif trigger.startswith("user"):
                store.cancel(run_id)
        if (trigger == "user_crosses_deadline" and core.cancelled and not delayed_cancellation
                and request.method == "GET" and not path.endswith("/result")):
            delayed_cancellation = True
            clock.value = 2.0
            return response
        if (path.startswith("/v1/executions") and request.method != "DELETE"
                and not path.endswith("/cancel") and (core.cancelled or trigger == "core")):
            value = response.json()
            value["status"] = terminal
            if path.endswith("/result"):
                value["errors"] = [{"code": "remote_execution_unconfirmed", "stage": "generate",
                                    "retryable": False, "operation_id": None}] if terminal == "uncertain" else []
            else:
                value.update(stage="finished", result_available=True)
            return httpx.Response(response.status_code, json=value)
        return response

    worker.client_factory = lambda endpoint, c: CoreClient(
        endpoint, c, transport=httpx.MockTransport(complete_after_cancellation))
    assert worker.step()
    run = store.run(run_id)
    expected_status = {"uncertain": "interrupted", "timed_out": "failed"}.get(terminal, terminal)
    assert run["status"] == expected_status
    assert run["error_code"] == ("run_deadline_exceeded" if trigger == "deadline" else "core_" + terminal)
    assert run["attempts"][0]["status"] == expected_status
    assert run["attempts"][0]["result"]["status"] == terminal
    assert run["attempts"][1]["status"] == ("cancelled" if terminal == "cancelled" else "skipped")
    assert bool(run["reconciliation_required"]) == (terminal == "uncertain")
    assert not run["cleanup_pending"]
    assert len(core.requests) == len(core.deleted) == len(runtime.cleaned) == 1
    assert len(core.cancelled) == (0 if trigger == "core" else 1)
    assert delayed_cancellation == (trigger == "user_crosses_deadline")
    if terminal == "uncertain":
        assert run["attempts"][0]["result"]["errors"][0]["code"] == "remote_execution_unconfirmed"
        assert not worker.step()


def test_uncertain_result_keeps_hold_when_retention_delete_fails(store, publication, contracts, result_template):
    from uuid import uuid4
    from enhancement_bench.store import Store

    publication.definition.units = publication.definition.units[1:]
    run_id = store.import_publication(publication)["runId"]
    worker, core, runtime = make_worker(store, contracts, result_template)
    handle = core.handle
    operation_id = str(uuid4())

    def uncertain(request):
        response = handle(request)
        if request.url.path.startswith("/v1/executions"):
            if request.method == "DELETE":
                raise httpx.ReadTimeout("synthetic lost retention acknowledgement")
            value = response.json()
            value["status"] = "uncertain"
            if request.url.path.endswith("/result"):
                value["consumer_provenance"] = {"provider": "openhands_acp", "adapter_version": "example.v1",
                                                "operation_id": operation_id}
                value["errors"] = [{"code": "consumer_cleanup_uncertain", "stage": "generate",
                                    "retryable": False, "operation_id": operation_id}]
            return httpx.Response(response.status_code, json=value)
        return response

    worker.client_factory = lambda endpoint, c: CoreClient(endpoint, c, transport=httpx.MockTransport(uncertain))
    worker.step()
    run = store.run(run_id)
    assert run["attempts"][0]["result"]["status"] == "uncertain"
    assert run["reconciliation_required"] and not run["cleanup_pending"]
    assert len(runtime.cleaned) == 1 and len(core.requests) == 1
    assert not worker.step()
    reopened = Store(store.path)
    Worker(reopened, contracts, runtime).reconcile()
    reopened.cleanup_confirmed(run_id)
    retained = reopened.run(run_id)
    assert retained["reconciliation_required"] and not retained["cleanup_pending"]
    result = retained["attempts"][0]["result"]
    assert result["consumer_provenance"]["operation_id"] == operation_id
    assert result["errors"][0]["operation_id"] == operation_id
    queued = reopened.enqueue_ui(publication.definition.stableId, publication.definition.revision,
                                 Overrides(), str(uuid4()))
    assert reopened.claim() is None
    reopened.acknowledge_remote_stopped(run_id, "example-reviewed-stop-receipt")
    assert reopened.claim()["id"] == queued


def test_one_worker_process_lock(store):
    with exclusive_worker(store):
        with pytest.raises(BenchError, match="worker_already_active"):
            with exclusive_worker(store):
                pass


def test_worker_lock_is_released_after_failure(store):
    with pytest.raises(RuntimeError, match="example-worker-failure"):
        with exclusive_worker(store):
            raise RuntimeError("example-worker-failure")
    with exclusive_worker(store):
        with pytest.raises(BenchError, match="worker_already_active"):
            with exclusive_worker(store):
                pass


def test_shared_schema_rejects_wrong_provider_before_container_launch(store, publication, contracts, result_template):
    definition = publication.model_dump()
    definition["definition"]["consumerBinding"]["provider"] = "chat_for_every_model"
    from enhancement_bench.definitions import Publication

    run_id = store.import_publication(Publication.model_validate(definition))["runId"]
    worker, core, runtime = make_worker(store, contracts, result_template)
    worker.step()
    assert store.run(run_id)["status"] == "failed"
    assert not runtime.launched and not core.requests
