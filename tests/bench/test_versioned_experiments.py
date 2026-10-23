"""New revisions pin workflow/core/evaluation; old rows retain their identity."""
import copy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from enhancement_bench.definitions import CoreImage, Definition, Overrides, Publication, effective_settings
from enhancement_bench.errors import BenchError
from prompt_enhancer.enhancement import CORE_VERSION


def release(image="a"):
    return CoreImage(schemaVersion="core-release/v1", coreVersion=CORE_VERSION, variant="default",
        image="registry.example.com/example/enhancer@sha256:" + image * 64, buildInputSha256="c" * 64,
        validatedSourceRevision="d" * 40, action="built", runtimeVerified=True)


def definition(publication, contracts):
    value = publication.definition.model_dump()
    manifest = next(item for item in contracts.workflows if item["workflow_id"] == "prompt-clarify" and item["version"] == "1.1.0")
    value.update(schemaVersion="bench-experiment/v2", enhancerVersion=CORE_VERSION, autoRun=False,
        workflow={key: manifest[key] for key in ("workflow_id", "version", "definition_sha256")},
        coreBuild={"variant": "default", "image": release().image, "buildInputSha256": "c" * 64},
        harnessAssertions=[], consumerBinding=None)
    value["units"] = [value["units"][0]]
    value["units"][0].update(strategy="script.clarify.v1", assertions=[])
    return Definition.model_validate(value)


def request(contracts, definition, overrides=None):
    effective = effective_settings(definition, overrides or Overrides())
    return contracts.request({"stable_id": definition.stableId, "revision": definition.revision,
        "id": "example-run", "correlation_id": "example-correlation", "effective": effective},
        {"id": "example-attempt", "unit_id": effective["units"][0]["id"], "subject_id": effective["subjects"][0]["id"]})


def test_pins_survive_catalog_replacement_restart_and_reruns(store, publication, contracts):
    value = definition(publication, contracts)
    store.register_core_image(release())
    store.import_publication(Publication(schemaVersion="bench-publication/v2", definition=value))
    first = store.enqueue_ui(value.stableId, value.revision, Overrides(), str(uuid4()))
    before = store.run(first)
    store.register_core_image(release("b"))
    second = store.enqueue_ui(value.stableId, value.revision, Overrides(), str(uuid4()))
    assert store.run(second)["image"] == before["image"] == release().image
    assert store.run(first) == before
    from enhancement_bench.store import Store
    reopened = Store(store.path)
    third = reopened.enqueue_ui(value.stableId, value.revision, Overrides(), str(uuid4()))
    assert reopened.run(third)["image"] == release().image
    assert reopened.run(third)["effective"]["workflow"] == value.workflow


def test_new_image_pin_requires_new_revision(store, publication, contracts):
    store.register_core_image(release())
    store.register_core_image(release("b"))
    original = definition(publication, contracts)
    store.import_publication(Publication(schemaVersion="bench-publication/v2", definition=original))
    changed = original.model_dump()
    changed["coreBuild"]["image"] = release("b").image
    with pytest.raises(BenchError, match="immutable_revision_conflict"):
        store.import_publication(Publication(schemaVersion="bench-publication/v2", definition=Definition.model_validate(changed)))
    changed.update(revision="2", generation=2)
    revised = Definition.model_validate(changed)
    store.import_publication(Publication(schemaVersion="bench-publication/v2", definition=revised))
    run = store.enqueue_ui(revised.stableId, revised.revision, Overrides(), str(uuid4()))
    assert store.run(run)["image"] == release("b").image


def test_unverified_or_wrong_build_is_rejected_atomically(store, publication, contracts):
    value = definition(publication, contracts)
    with pytest.raises(BenchError, match="pinned_core_build_unavailable"):
        store.import_publication(Publication(schemaVersion="bench-publication/v2", definition=value))
    assert not store.definitions()
    store.register_core_image(release())
    changed = value.model_dump()
    changed["coreBuild"]["buildInputSha256"] = "f" * 64
    with pytest.raises(BenchError, match="pinned_core_build_mismatch"):
        store.import_publication(Publication(schemaVersion="bench-publication/v2", definition=Definition.model_validate(changed)))
    assert not store.definitions()


def test_fixed_workflow_and_harness_cannot_be_changed_by_overrides(publication, contracts):
    value = definition(publication, contracts)
    request(contracts, value)
    for payload in ({"workflow": {}}, {"evaluatorProfile": {}}, {"coreBuild": {}}, {"harnessAssertions": []}):
        with pytest.raises(ValidationError): Overrides.model_validate(payload)
    changed = value.model_dump()
    changed["units"].append(copy.deepcopy(changed["units"][0]))
    changed["units"][-1].update(id="example-other", strategy="consumer.rewrite.v1")
    with pytest.raises(ValidationError, match="workflow_strategy_fixed"):
        Definition.model_validate(changed)
    with pytest.raises(BenchError, match="workflow_step_not_configurable"):
        request(contracts, value, Overrides(unitStepSettings={value.units[0].id: {"diagnose": {
            "binding": {"binding_id": "example-model", "provider": "inference"}}}}))


def test_workflow_pin_is_verified_by_offline_contract_validation(publication, contracts):
    value = definition(publication, contracts).model_dump()
    value["workflow"]["definition_sha256"] = "0" * 64
    with pytest.raises(BenchError, match="workflow_definition_unsupported"):
        request(contracts, Definition.model_validate(value))
    value = definition(publication, contracts).model_dump()
    value["enhancerVersion"] = "0.1.4"
    with pytest.raises(BenchError, match="workflow_core_incompatible"):
        request(contracts, Definition.model_validate(value))


def test_malformed_workflow_parameters_return_contract_errors(publication, contracts):
    value = definition(publication, contracts).model_dump()
    value["objective"]["targets"] = ["example-malformed-target"]
    with pytest.raises(BenchError, match="core_contract_violation"):
        request(contracts, Definition.model_validate(value))


def test_protocol_round_trip_checks_workflow_and_effective_step_settings(publication, contracts):
    import asyncio
    from prompt_enhancer.enhancement.contracts import ExecuteRequest
    from prompt_enhancer.enhancement.engine import EnhancementEngine
    from prompt_enhancer.enhancement.evaluators import DeterministicEvaluation
    value = request(contracts, definition(publication, contracts))
    item = ExecuteRequest.model_validate(value)
    result = asyncio.run(EnhancementEngine({}, {"deterministic.v1": DeterministicEvaluation()}).execute(item, lambda _: None)).model_dump(mode="json")
    assert result["status"] == "succeeded"
    contracts.result(result, value, CORE_VERSION)
    with pytest.raises(BenchError, match="core_version_mismatch"):
        contracts.result(result, value, "0.0.0")
    invalid_failure = copy.deepcopy(result)
    invalid_failure["status"] = "failed"
    invalid_failure["workflow_result"]["definition_sha256"] = "0" * 64
    with pytest.raises(BenchError, match="core_workflow_provenance_mismatch"):
        contracts.result(invalid_failure, value, CORE_VERSION)
    result["workflow"]["definition_sha256"] = "0" * 64
    with pytest.raises(BenchError, match="core_workflow_settings_mismatch"):
        contracts.result(result, value, CORE_VERSION)


@pytest.mark.parametrize("version", ["1.1.0", "2.1.0"])
def test_model_filters_follow_step_binding_instead_of_unused_default(store, publication, contracts, version):
    from enhancement_bench.history import RunFilters
    value = definition(publication, contracts).model_dump()
    manifest = next(item for item in contracts.workflows if item["workflow_id"] == "prompt-rewrite" and item["version"] == version)
    value["workflow"] = {key: manifest[key] for key in ("workflow_id", "version", "definition_sha256")}
    value["units"][0].update(strategy=manifest["strategy"], stepSettings={manifest["model_step"]: {
        "binding": {"binding_id": "example-selected", "provider": "inference"}}})
    value["consumerBinding"] = {"binding_id": "example-unused", "provider": "inference"}
    value = Definition.model_validate(value)
    store.register_core_image(release())
    store.import_publication(Publication(schemaVersion="bench-publication/v2", definition=value))
    run_id = store.enqueue_ui(value.stableId, value.revision, Overrides(), str(uuid4()))
    assert [row["id"] for row in store.runs(filters=RunFilters(model="example-selected"))] == [run_id]
    assert store.runs(filters=RunFilters(model="example-unused")) == []
    history = store.run_history(100, None, RunFilters())
    assert "example-selected" in history["modelOptions"] and "example-unused" not in history["modelOptions"]


@pytest.mark.parametrize("workflow_id", ["prompt-rewrite", "prompt-clarify"])
def test_adjusted_review_workflows_round_trip_through_bench(publication, contracts, workflow_id):
    import asyncio
    from prompt_enhancer.enhancement.contracts import ExecuteRequest, Provenance
    from prompt_enhancer.enhancement.engine import EnhancementEngine
    from prompt_enhancer.enhancement.evaluators import DeterministicEvaluation
    from prompt_enhancer.enhancement.ports import Candidate
    class Model:
        provider = "inference"
        def validate_call(self, call): pass
        async def complete(self, call):
            assert "task type guess:" in call.user and "Deterministic findings:" in call.user
            return Candidate('{"notes":"Fictional review with no rewrite."}',
                Provenance(provider="inference", adapter_version="example.v1", model="example-review"))
    value = definition(publication, contracts).model_dump()
    manifest = next(item for item in contracts.workflows if item["workflow_id"] == workflow_id and item["version"] == "2.1.0")
    value["workflow"] = {key: manifest[key] for key in ("workflow_id", "version", "definition_sha256")}
    value["units"][0].update(strategy=manifest["strategy"], stepSettings={"review": {
        "binding": {"binding_id": "example-review", "provider": "inference"}}})
    payload = request(contracts, Definition.model_validate(value))
    runner = EnhancementEngine({"example-review": Model()}, {"deterministic.v1": DeterministicEvaluation()})
    result = asyncio.run(runner.execute(ExecuteRequest.model_validate(payload), lambda _: None)).model_dump(mode="json")
    assert result["status"] == "succeeded" and result["after"] == []
    assert [step["step_id"] for step in result["workflow_result"]["steps"]] == ["diagnose", "context", "review"]
    contracts.result(result, payload, CORE_VERSION)


@pytest.mark.parametrize("binding", ["deterministic.v1", "deterministic.v2"])
def test_bench_worker_executes_versioned_workflow_through_real_core_http(store, publication, contracts, binding):
    import httpx
    from fastapi.testclient import TestClient
    from enhancement_bench.client import CoreClient
    from enhancement_bench.worker import Worker
    from prompt_enhancer.enhancement.engine import EnhancementEngine
    from prompt_enhancer.enhancement.evaluators import DeterministicEvaluation
    from prompt_enhancer.enhancement.http import create_app
    from prompt_enhancer.enhancement.manager import ExecutionManager
    from test_client_worker import SyntheticRuntime
    payload = definition(publication, contracts).model_dump()
    payload["evaluatorProfile"]["evaluators"][0]["binding_id"] = binding
    value = Definition.model_validate(payload)
    store.register_core_image(release())
    store.import_publication(Publication(schemaVersion="bench-publication/v2", definition=value))
    run_id = store.enqueue_ui(value.stableId, value.revision, Overrides(), str(uuid4()))
    manager = ExecutionManager(EnhancementEngine({}, {binding: DeterministicEvaluation(version=binding.rsplit(".", 1)[1])}), enabled=True)
    runtime = SyntheticRuntime()
    token = "example-versioned-core-access-value-only"
    with TestClient(create_app(manager, api_token=token)) as core:
        def transport(request):
            response = core.request(request.method, request.url.path, content=request.content,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            return httpx.Response(response.status_code, content=response.content, headers=response.headers)
        worker = Worker(store, contracts, runtime, poll_seconds=0.001,
            client_factory=lambda endpoint, contracts: CoreClient(endpoint, contracts, transport=httpx.MockTransport(transport)))
        assert worker.step()
    run = store.run(run_id)
    assert run["status"] == "succeeded" and not run["cleanup_pending"]
    assert run["attempts"][0]["result"]["workflow_result"]["workflow"] == value.workflow
    assert run["attempts"][0]["result"]["before"][0]["provenance"]["adapter_version"] == binding.replace("deterministic", "prompt-evaluation")
    assert runtime.launched == [release().image] and len(runtime.cleaned) == 1
    assert not manager.entries


@pytest.mark.parametrize("review_state", ["ok", "reply_invalid", "model_error"])
def test_review_outcome_survives_http_storage_cleanup_and_recovery(store, publication, contracts, review_state, tmp_path):
    import httpx
    from fastapi.testclient import TestClient
    from enhancement_bench.api import create_app as bench_app
    from enhancement_bench.client import CoreClient
    from enhancement_bench.store import Store
    from enhancement_bench.worker import Worker
    from prompt_enhancer.enhancement.contracts import Provenance
    from prompt_enhancer.enhancement.engine import EnhancementEngine
    from prompt_enhancer.enhancement.evaluators import DeterministicEvaluation
    from prompt_enhancer.enhancement.http import create_app
    from prompt_enhancer.enhancement.manager import ExecutionManager
    from prompt_enhancer.enhancement.ports import Candidate, CoreError
    from test_client_worker import SyntheticRuntime

    class Model:
        provider = "inference"
        mode, calls = review_state, 0
        provenance = Provenance(provider="inference", adapter_version="example.v1", model="example-review")
        def validate_call(self, call): pass
        async def complete(self, call):
            self.calls += 1
            if self.mode == "model_error":
                raise CoreError("consumer_failed")
            return Candidate('{"notes":"Fictional review without a rewrite."}' if self.mode == "ok" else '{}',
                self.provenance)

    payload = definition(publication, contracts).model_dump()
    manifest = next(item for item in contracts.workflows if item["workflow_id"] == "prompt-check" and item["version"] == "1.1.0")
    payload["workflow"] = {key: manifest[key] for key in ("workflow_id", "version", "definition_sha256")}
    payload["units"][0].update(strategy=manifest["strategy"], stepSettings={"review": {
        "binding": {"binding_id": "example-review", "provider": "inference"}}})
    payload["units"].append(copy.deepcopy(payload["units"][0]) | {"id": "example-second-review"})
    value = Definition.model_validate(payload)
    store.register_core_image(release())
    store.import_publication(Publication(schemaVersion="bench-publication/v2", definition=value))
    run_id = store.enqueue_ui(value.stableId, value.revision, Overrides(), str(uuid4()))
    model, runtime = Model(), SyntheticRuntime()
    manager = ExecutionManager(EnhancementEngine({"example-review": model}, {"deterministic.v1": DeterministicEvaluation()}), enabled=True)
    token = "example-versioned-core-access-value-only"
    with TestClient(create_app(manager, api_token=token)) as core:
        def transport(request):
            response = core.request(request.method, request.url.path, content=request.content,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            return httpx.Response(response.status_code, content=response.content, headers=response.headers)
        worker = Worker(store, contracts, runtime, poll_seconds=0.001,
            client_factory=lambda endpoint, contracts: CoreClient(endpoint, contracts, transport=httpx.MockTransport(transport)))
        assert worker.step()
        retained = Store(store.path).run(run_id)
        failed = review_state != "ok"
        assert retained["status"] == ("failed" if failed else "succeeded"), retained["error_code"]
        assert [attempt["status"] for attempt in retained["attempts"]] == (["failed", "skipped"] if failed else ["succeeded", "succeeded"])
        assert model.calls == (1 if failed else 2)
        result = retained["attempts"][0]["result"]
        assert result["workflow_result"]["review"]["state"] == review_state and result["before"]
        assert result["candidate"] is None and result["enhanced_prompt"] is None and not result["after"]
        assert result["assertion_outcome"] == "not_evaluated"
        assert not retained["cleanup_pending"] and not retained["reconciliation_required"]
        assert len(runtime.cleaned) == 1 and not manager.entries
        if failed:
            assert result["errors"][0]["code"] == "workflow_review_" + review_state
            assert retained["attempts"][1]["result"] is None
            model.mode = "ok"
            recovery = store.enqueue_ui(value.stableId, value.revision, Overrides(), str(uuid4()))
            assert worker.step() and store.run(recovery)["status"] == "succeeded"
            assert model.calls == 3 and len(runtime.cleaned) == 2 and not manager.entries
            assert store.run(run_id) == retained
    with TestClient(bench_app(Store(store.path), contracts, allowed_repositories=(), origin="http://testserver")) as client:
        response = client.get("/api/runs/" + run_id)
        assert response.status_code == 200 and response.json() == retained
    from enhancement_bench.analysis import dataset, inspect_run, validated_run, write_export
    from enhancement_bench.protocol import Contracts
    export_contracts = Contracts.from_payload(contracts.payload())
    checked = validated_run(response.json(), export_contracts)
    assert inspect_run(checked)["attempts"][0]["reviewState"] == review_state
    analysis = dataset([checked])
    manifest = write_export(tmp_path / "analysis", analysis)
    assert manifest["rowCounts"]["attempts"] == 2
    row = analysis["tables"]["attempts"][0]
    assert row["technical_outcome"] == ("failed" if failed else "succeeded")
    assert row["workflow_step_order"] == [step["step_id"] for step in result["workflow_result"]["steps"]]
    assert row["generation_context_version"] == result["generation_context_version"]
    assert all(metric["after_state"] == "missing" and metric["after_value"] is None
               and not metric["pair_eligible"] for metric in analysis["tables"]["metrics"])
