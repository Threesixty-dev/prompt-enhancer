"""Synthetic core, role isolation, lifecycle, and HTTP evidence."""
import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from prompt_enhancer.enhancement.contracts import (
    ConsumerBinding, Evaluation, EvaluationProfile, Evaluator, ExecuteRequest,
    GenerationContext, Metric, Parameters, Provenance, Subject,
)
from prompt_enhancer.enhancement.engine import EnhancementEngine, compare, execution_id, identity
from prompt_enhancer.enhancement.evaluators import DeterministicEvaluation
from prompt_enhancer.enhancement.http import create_app
from prompt_enhancer.enhancement.manager import ExecutionManager
from prompt_enhancer.enhancement.ports import Candidate, CoreError

EXAMPLE = Path(__file__).resolve().parents[1] / "contracts/enhancement/examples/script-request.json"
TOKEN = "example-benchmark-api-access-value-only"
HEADERS = {"Authorization": "Bearer " + TOKEN}


def request(**changes):
    value = json.loads(EXAMPLE.read_text())
    value.update(changes)
    return ExecuteRequest.model_validate(value)


class Consumer:
    provider = "inference"
    provenance = Provenance(provider="example", adapter_version="example.v1")

    def __init__(self, *, block=False, uncertain=False):
        self.calls = []
        self.contexts = []
        self.block = block
        self.uncertain = uncertain

    def validate(self, request):
        pass

    async def generate(self, request, context):
        self.calls.append(request)
        self.contexts.append(context)
        if self.block:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                if self.uncertain:
                    raise CoreError("remote_execution_unconfirmed", uncertain=True)
                raise
        return Candidate("Add a fictional widget parser. Return a patch and unit tests that verify empty input.", self.provenance)


def consumer_request(**changes):
    return request(strategy="consumer.rewrite.v1",
                   consumer={"binding_id": "example", "provider": "inference"}, **changes)


def engine(consumer=None):
    return EnhancementEngine({"example": consumer} if consumer else {}, {"deterministic.v1": DeterministicEvaluation()})


def context_for(item):
    before = asyncio.run(DeterministicEvaluation().evaluate(item.subject, item.evaluation.evaluators[0]))
    return GenerationContext(**identity(item), before=(before,), evaluation_profile=item.evaluation,
        objective=item.objective, steering=item.steering)


async def finished(manager, key):
    await manager.get(key).task
    return manager.get(key).result


def test_script_runs_complete_shared_flow_with_context():
    stages = []
    item = request(subject={"text": "Fix the fictional parser. Return a patch.",
                            "context": [{"role": "user", "content": "The parser returns empty text for valid input."}]})
    result = asyncio.run(engine().execute(item, stages.append))
    assert result.status == "succeeded"
    assert result.assertion_outcome == "not_evaluated"
    assert stages == ["evaluate_original", "generate", "evaluate_candidate", "compare"]
    assert len(result.before[0].metrics) == len(result.after[0].metrics) == 6
    assert result.before[0].provenance == result.after[0].provenance
    assert "<specify:" in result.enhanced_prompt
    assert result.original.sha256 != result.candidate.sha256
    assert [t.stage for t in result.timings] == stages
    assert result.effective_parameters == item.parameters
    assert result.evaluation_profile == item.evaluation


def test_consumer_strategy_has_same_result_contract_and_separate_binding():
    consumer = Consumer()
    item = consumer_request()
    result = asyncio.run(engine(consumer).execute(item, lambda stage: None))
    assert result.status == "succeeded"
    assert consumer.calls == [item]
    assert consumer.contexts[0].before == result.before
    assert result.consumer_provenance.provider == "example"
    assert result.before[0].provenance.provider == "deterministic"
    assert result.after and result.deltas


def test_assertion_failure_is_not_execution_failure_and_unknown_is_preserved():
    item = request(assertions=[{"evaluator_id": "prompt", "metric_key": "prompt.task_definition_coverage",
                                "operator": "minimum_value", "threshold": 999}])
    result = asyncio.run(engine().execute(item, lambda stage: None))
    assert result.status == "succeeded"
    assert result.assertion_outcome == "failed"
    unknown = request(subject={"text": "..."}, assertions=[{"evaluator_id": "prompt",
        "metric_key": "prompt.problem_evidence_quality", "operator": "minimum_delta", "threshold": 0}])
    result = asyncio.run(engine().execute(unknown, lambda stage: None))
    assert result.assertion_outcome == "unknown"
    assert result.assertions[0].observed is None


def test_provenance_and_categorical_comparisons_are_not_numeric_deltas():
    value = Evaluation(evaluator_id="example", kind="classifier", provenance=Consumer.provenance,
                       metrics=(Metric(key="nli.label", state="known", label="neutral", reason="model_interpretation"),))
    assert compare((value,), (value,))[0].reason == "categorical_metric"
    changed = value.model_copy(update={"provenance": value.provenance.model_copy(update={"model_revision": "different"})})
    assert compare((value,), (changed,))[0].reason == "provenance_mismatch"


def test_invalid_binding_is_rejected_before_any_call():
    consumer = Consumer()
    service = engine(consumer)
    bad = consumer_request(evaluation={"profile_id": "example", "revision": "1", "evaluators": [
        {"evaluator_id": "example", "kind": "deterministic", "binding_id": "missing"}]})
    with pytest.raises(CoreError, match="evaluation_binding_unsupported"):
        service.validate(bad)
    assert consumer.calls == []


def test_duplicate_conflict_capacity_retention_and_delete():
    async def scenario():
        manager = ExecutionManager(engine(), enabled=True, max_retained=1)
        item = request()
        first = manager.submit(item)
        assert manager.submit(item).execution_id == first.execution_id
        with pytest.raises(CoreError, match="identity_conflict"):
            manager.submit(request(subject={"text": "Different fictional input"}))
        with pytest.raises(CoreError, match="admission_unavailable"):
            manager.submit(request(attempt_id="2"))
        with pytest.raises(CoreError, match="execution_active"):
            manager.delete(first.execution_id)
        result = await finished(manager, first.execution_id)
        assert result.status == "succeeded"
        assert manager.cancel(first.execution_id).status == "succeeded"
        assert not manager.readiness().ready
        manager.delete(first.execution_id)
        assert manager.readiness().ready
        await manager.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("uncertain,expected", [(False, "cancelled"), (True, "uncertain")])
def test_cancellation_and_remote_uncertainty_quarantine(uncertain, expected):
    async def scenario():
        consumer = Consumer(block=True, uncertain=uncertain)
        manager = ExecutionManager(engine(consumer), enabled=True)
        key = manager.submit(consumer_request()).execution_id
        while not consumer.calls:
            await asyncio.sleep(0)
        assert manager.cancel(key).status == "cancelling"
        result = await finished(manager, key)
        assert result.status == expected
        assert bool(manager.quarantined) == uncertain
        assert result.after == ()
        assert result.before
    asyncio.run(scenario())


def test_cancel_immediately_after_submit_has_terminal_result():
    async def scenario():
        manager = ExecutionManager(engine(Consumer(block=True)), enabled=True)
        key = manager.submit(consumer_request()).execution_id
        manager.cancel(key)
        assert (await finished(manager, key)).status == "cancelled"
    asyncio.run(scenario())


def test_deadline_is_bounded_and_preserves_before_evidence():
    result = asyncio.run(engine(Consumer(block=True)).execute(
        consumer_request(parameters={"timeout_seconds": 1}), lambda stage: None))
    assert result.status == "timed_out"
    assert result.before and not result.after


def test_http_full_lifecycle_auth_privacy_and_validation():
    manager = ExecutionManager(engine(), enabled=True)
    with TestClient(create_app(manager, api_token=TOKEN)) as client:
        assert client.get("/v1/capabilities").status_code == 401
        assert client.get("/health/ready", headers={**HEADERS, "Origin": "https://example.invalid"}).status_code == 403
        capabilities = client.get("/v1/capabilities", headers=HEADERS).json()
        assert capabilities["evaluators"][0]["kind"] == "deterministic"
        item = request()
        invalid = item.model_dump()
        invalid["private_extra"] = "fictional untrusted content"
        rejected = client.post("/v1/executions", json=invalid, headers=HEADERS)
        assert rejected.status_code == 422
        assert "fictional" not in rejected.text
        accepted = client.post("/v1/executions", json=item.model_dump(), headers=HEADERS)
        assert accepted.status_code == 202
        key = accepted.json()["execution_id"]
        assert key == execution_id(item)
        for _ in range(50):
            state = client.get(f"/v1/executions/{key}", headers=HEADERS).json()
            assert item.subject.text not in json.dumps(state)
            if state["result_available"]:
                break
        assert state["status"] == "succeeded"
        response = client.get(f"/v1/executions/{key}/result", headers=HEADERS)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json()["before"] and response.json()["after"]
        assert client.delete(f"/v1/executions/{key}", headers=HEADERS).status_code == 204
        assert client.get(f"/v1/executions/{key}", headers=HEADERS).status_code == 404
        assert client.get("/v1/prompt-checks", headers=HEADERS).status_code == 404


def test_http_body_limit_and_explicit_opt_in():
    with TestClient(create_app(ExecutionManager(engine()), api_token=TOKEN)) as client:
        assert client.get("/health/ready", headers=HEADERS).status_code == 503
        assert client.post("/v1/executions", json=request().model_dump(), headers=HEADERS).status_code == 403
        assert client.post("/v1/executions", content=b"x" * 320001,
            headers={**HEADERS, "Content-Type": "application/json"}).status_code == 413
        assert client.post("/v1/executions", content='{"run_id":"first","run_id":"second"}',
            headers={**HEADERS, "Content-Type": "application/json"}).status_code == 422


def test_unsupported_assertion_metric_rejected_before_consumer_call():
    consumer = Consumer()
    item = consumer_request(assertions=[{"evaluator_id": "prompt", "metric_key": "unsupported",
        "operator": "minimum_value", "threshold": 0}])
    with pytest.raises(CoreError, match="assertion_metric_unsupported"):
        engine(consumer).validate(item)
    assert consumer.calls == []


def test_measured_baseline_objective_and_steering_drive_generation_and_are_recorded():
    consumer = Consumer()
    item = consumer_request(objective={"objective_id": "example-testability", "revision": "2",
        "description": "Make fictional acceptance conditions observable.", "targets": [
            {"kind": "numeric", "evaluator_id": "prompt", "metric_key": "prompt.acceptance_testability",
             "direction": "increase", "desired_value": 1}]},
        steering={"profile": "targeted.v1", "style": "concise", "focus": ["acceptance"],
                  "instructions": "Use a compact checklist and preserve the fictional function name."})
    result = asyncio.run(engine(consumer).execute(item, lambda stage: None))
    context = consumer.contexts[0]
    assert context.before == result.before
    assert context.objective == item.objective and context.steering == item.steering
    assert result.effective_objective == item.objective and result.effective_steering == item.steering
    assert result.generation_context_version == "enhancement-generation.v1"
    assert any(m.state != "known" and m.value is None for m in context.before[0].metrics)
    assert result.after[0].provenance.provider == "deterministic"


def test_script_targeted_profile_uses_findings_and_focus():
    item = request(steering={"profile": "targeted.v1", "focus": ["acceptance"]},
        objective={"targets": [{"kind": "numeric", "evaluator_id": "prompt", "metric_key": "prompt.acceptance_testability", "direction": "increase"}]})
    result = asyncio.run(engine().execute(item, lambda stage: None))
    assert "Acceptance: <specify:" in result.enhanced_prompt
    assert "Constraints: <specify:" not in result.enhanced_prompt


def test_numeric_objective_cannot_treat_categorical_output_as_a_score():
    item = consumer_request(evaluation={"profile_id": "example", "revision": "1", "evaluators": [
        {"evaluator_id": "labels", "kind": "rubric", "binding_id": "example", "rubric": "task_definition"}]},
        objective={"targets": [{"kind": "numeric", "evaluator_id": "labels", "metric_key": "rubric.label", "direction": "increase"}]})
    class Provider:
        def validate(self, spec): pass
    with pytest.raises(CoreError, match="objective_target_kind_mismatch"):
        EnhancementEngine({"example": Consumer()}, {"example": Provider()}).validate(item)


def test_partial_evaluator_failure_preserves_completed_measurements():
    class Failing:
        kind = "deterministic"
        provenance = Consumer.provenance
        def validate(self, spec): pass
        async def evaluate(self, subject, spec):
            raise CoreError("evaluator_unavailable")
    item = request(evaluation={"profile_id": "example", "revision": "1", "evaluators": [
        {"evaluator_id": "first", "kind": "deterministic", "binding_id": "deterministic.v1"},
        {"evaluator_id": "second", "kind": "deterministic", "binding_id": "failing"}]})
    service = EnhancementEngine({}, {"deterministic.v1": DeterministicEvaluation(), "failing": Failing()})
    result = asyncio.run(service.execute(item, lambda stage: None))
    assert result.status == "failed" and result.before[0].evaluator_id == "first"
    assert result.enhanced_prompt is None and not result.after
