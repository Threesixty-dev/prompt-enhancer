"""Synthetic evidence for workflow boundaries, parity and independent judging."""
import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from prompt_enhancer.application.prompt_check import PromptCheckRequest, _commentary_input, _SYSTEM_PROMPT
from prompt_enhancer.core.prompt_review import infer_context
from prompt_enhancer.enhancement.contracts import Evaluation, ExecuteRequest, Metric, Provenance
from prompt_enhancer.enhancement.engine import EnhancementEngine
from prompt_enhancer.enhancement.evaluators import DeterministicEvaluation
from prompt_enhancer.enhancement.ports import Candidate, CoreError
from prompt_enhancer.infrastructure.language import DeterministicEnglishPolishDetector
from prompt_enhancer.workflows.catalog import LEGACY_WORKFLOWS, WORKFLOWS, catalog, resolve
from prompt_enhancer.workflows.prompts import PromptWorkflowInput, PromptWorkflowRunner
from prompt_enhancer.workflows.session_links import SessionLinksWorkflow

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('workflow_id,version', [('prompt-check', '1.1.0'), ('prompt-rewrite', '2.1.0'), ('prompt-clarify', '2.1.0')])
def test_invalid_review_enum_retains_safe_diagnostic_and_partial_evidence(workflow_id, version):
    model = Model(json.dumps({'reformulated_elements': [
        {'element': 'goal', 'suggested': 'Example goal.'},
        {'element': 'ambiguity', 'suggested': 'EXAMPLE_RAW_RESPONSE_CANARY'},
    ]}))
    result = asyncio.run(engine(model).execute(request(workflow_id, version=version), lambda _: None))
    assert result.status == 'failed' and result.errors[0].code == 'workflow_review_reply_invalid'
    assert result.workflow_result.review.validation_issue.model_dump() == {
        'reason': 'enum_mismatch', 'field': 'reformulated_elements[1].element'}
    assert [step.status for step in result.workflow_result.steps] == ['succeeded', 'succeeded', 'failed']
    assert result.before and not result.after and not result.deltas and result.candidate is None
    assert 'EXAMPLE_RAW_RESPONSE_CANARY' not in result.model_dump_json()


def request(workflow_id="prompt-rewrite", *, version="1.1.0", **changes):
    definition = next(item for item in WORKFLOWS if item.workflow_id == workflow_id and item.version == version)
    value = json.loads((ROOT / "contracts/enhancement/examples/script-request.json").read_text())
    value.update(strategy=definition.strategy, workflow=definition.reference(),
        consumer=None if definition.model_step is None else {"binding_id": "example-model", "provider": "inference"})
    value.update(changes)
    return ExecuteRequest.model_validate(value)


class Model:
    provider = "inference"
    provenance = Provenance(provider="inference", adapter_version="example.v1", model="example-model",
                            model_revision="example-revision", identity_source="configured")

    def __init__(self, text='{"enhanced_prompt":"Add a fictional widget. Return unit tests for empty input."}', block=False):
        self.text, self.block, self.calls = text, block, []

    def validate_call(self, call):
        pass

    async def complete(self, call):
        self.calls.append(call)
        if self.block:
            await asyncio.sleep(30)
        return Candidate(self.text, self.provenance.model_copy(update={"rubric_version": call.policy_version}))


def engine(model, evaluator=None):
    return EnhancementEngine({"example-model": model}, {"deterministic.v1": evaluator or DeterministicEvaluation()})


@pytest.mark.parametrize("workflow_id,version", [("prompt-rewrite", "1.1.0"), ("prompt-rewrite", "2.1.0"), ("prompt-clarify", "2.1.0")])
def test_harness_judgments_cannot_change_workflow_messages(workflow_id, version):
    class Judge:
        kind = "deterministic"
        provenance = Provenance(provider="example", adapter_version="example.v1")
        def __init__(self, score): self.score = score
        def validate(self, spec): pass
        async def evaluate(self, subject, spec):
            return Evaluation(evaluator_id=spec.evaluator_id, kind=spec.kind, provenance=self.provenance,
                metrics=(Metric(key="prompt.task_definition_coverage", state="known", value=self.score, reason="example"),))

    first, second = Model(), Model()
    if version == "2.1.0":
        first.text = second.text = '{"notes":"Fictional review."}'
    item = request(workflow_id, version=version)
    a = asyncio.run(engine(first, Judge(0)).execute(item, lambda _: None))
    b = asyncio.run(engine(second, Judge(1)).execute(item, lambda _: None))
    assert a.status == b.status == "succeeded"
    assert a.before != b.before
    assert first.calls == second.calls
    assert a.workflow_result.diagnostics == b.workflow_result.diagnostics
    assert a.workflow_result.configuration_sha256 == b.workflow_result.configuration_sha256
    if version == "1.1.0":
        payload = json.loads(first.calls[0].user)
        assert set(payload) == {"subject", "workflow_diagnostics", "objective", "steering"}
    assert "evaluation" not in PromptWorkflowInput.model_fields
    assert "assertions" not in PromptWorkflowInput.model_fields


def test_prompt_check_preserves_rich_input_policy_defaults_and_optional_rewrite():
    model = Model('{"notes":"The fictional request is clear; no rewrite is needed."}')
    item = request("prompt-check", parameters={}, subject={"text": "Fix the fictional parser. Return a patch and verify empty input.",
        "context": [{"role": "user", "content": "The fictional parser should accept an empty list."}]},
        assertions=[{"evaluator_id": "prompt", "metric_key": "prompt.task_definition_coverage",
                     "operator": "minimum_delta", "threshold": 0}])
    result = asyncio.run(engine(model).execute(item, lambda _: None))
    assert result.status == "succeeded"
    assert result.enhanced_prompt is None and result.candidate is None and not result.after
    assert result.assertion_outcome == "unknown" and result.assertions[0].observed is None
    assert all(delta.reason == "workflow_no_candidate" and delta.value is None for delta in result.deltas)
    legacy = PromptCheckRequest(prompt=item.subject.text, prior_messages=[m.model_dump() for m in item.subject.context])
    scorer = DeterministicEvaluation().evaluator
    readings = scorer.evaluate("0" * 64, legacy.prompt, legacy.prior_messages)
    context = infer_context(legacy.prompt, legacy.prior_messages, readings, DeterministicEnglishPolishDetector())
    assert model.calls[0].system == _SYSTEM_PROMPT
    assert model.calls[0].user == _commentary_input(legacy, legacy.prompt, readings, context)
    assert model.calls[0].generation.max_tokens == 1100 and model.calls[0].generation.temperature == 0.2
    assert model.calls[0].enable_thinking is False
    assert result.workflow_result.review.notes.startswith("The fictional")
    assert result.workflow_result.context == context
    assert result.workflow_result.diagnostics[0].cues
    assert result.workflow_result.diagnostics[0].numerator is not None


def test_prompt_check_without_model_and_standalone_invocation():
    item = request("prompt-check", consumer=None)
    runner = PromptWorkflowRunner({})
    result = asyncio.run(runner.run(PromptWorkflowInput.from_execution(item)))
    assert result.text is None and result.provenance is None
    assert result.receipt.review.state == "no_active_model"
    assert result.receipt.steps[-1].status == "skipped"
    measured = asyncio.run(EnhancementEngine({}, {"deterministic.v1": DeterministicEvaluation()}).execute(item, lambda _: None))
    assert measured.status == "succeeded" and not measured.errors
    assert measured.before and not measured.after and measured.candidate is None
    assert measured.workflow_result.review.state == "no_active_model"


def test_explicit_null_generation_controls_remain_provider_managed():
    model = Model('{"notes":"Fictional review."}')
    item = request("prompt-check", parameters={"generation": {"max_tokens": None, "temperature": None}})
    result = asyncio.run(engine(model).execute(item, lambda _: None))
    assert result.status == "succeeded"
    assert model.calls[0].generation.max_tokens is None and model.calls[0].generation.temperature is None


def test_omitted_and_explicit_null_step_controls_do_not_share_request_identity():
    from prompt_enhancer.enhancement.manager import ExecutionManager
    async def scenario():
        manager = ExecutionManager(engine(Model('{"notes":"Fictional review."}')), enabled=True)
        original = request("prompt-check", workflow_steps={"review": {}})
        key = manager.submit(original).execution_id
        with pytest.raises(CoreError, match="identity_conflict"):
            manager.submit(request("prompt-check", workflow_steps={"review": {"enable_thinking": None}}))
        await manager.get(key).task
        assert manager.get(key).result.workflow_result.steps[-1].enable_thinking is False
        await manager.close()
    asyncio.run(scenario())


def test_uncertain_review_failure_is_not_downgraded_to_commentary():
    class Uncertain(Model):
        async def complete(self, call):
            raise CoreError("remote_cleanup_unconfirmed", uncertain=True)
    result = asyncio.run(engine(Uncertain()).execute(request("prompt-check"), lambda _: None))
    assert result.status == "uncertain" and result.enhanced_prompt is None


@pytest.mark.parametrize("workflow_id,version", [("prompt-check", "1.1.0"), ("prompt-rewrite", "2.1.0"), ("prompt-clarify", "2.1.0")])
def test_prebench_golden_metrics_context_model_input_and_policy(workflow_id, version):
    fixture = json.loads((ROOT / "tests/fixtures/example_prebench_prompt_review.json").read_text())
    assert hashlib.sha256(_SYSTEM_PROMPT.encode()).hexdigest() == fixture["policy_sha256"]
    for case in fixture["cases"]:
        model = Model('{"notes":"Fictional review."}')
        item = request(workflow_id, version=version, subject={"text": case["prompt"], "context": case["prior"]})
        result = asyncio.run(engine(model).execute(item, lambda _: None))
        assert result.status == "succeeded", case["id"]
        receipt = result.workflow_result.model_dump(mode="json")
        assert receipt["diagnostics"] == case["readings"], case["id"]
        assert receipt["context"] == case["context"], case["id"]
        assert model.calls[0].user == case["model_input"], case["id"]
        assert model.calls[0].system.startswith(_SYSTEM_PROMPT)


@pytest.mark.parametrize("workflow_id", ["prompt-rewrite", "prompt-clarify"])
@pytest.mark.parametrize("reply,review_state,rewritten", [
    ('{"reformulated_prompt":"Fix the fictional parser and verify empty input."}', "ok", True),
    ('{"notes":"The fictional request needs no rewrite."}', "ok", False),
    ('{"enhanced_prompt":"Old direct-rewrite format."}', "reply_invalid", False),
])
def test_adjusted_flows_review_after_scoring_and_context(workflow_id, reply, review_state, rewritten):
    model = Model(reply)
    events = []
    diagnostics = DeterministicEvaluation()
    evaluate = diagnostics.evaluator.evaluate
    def score(*args):
        events.append("score")
        return evaluate(*args)
    diagnostics.evaluator.evaluate = score
    complete = model.complete
    async def review(call):
        events.append("review")
        assert "task type guess:" in call.user and "depends on earlier conversation:" in call.user
        assert "Earlier conversation" in call.user and "Deterministic findings:" in call.user
        return await complete(call)
    model.complete = review
    runner = PromptWorkflowRunner({"example-model": model}, diagnostics=diagnostics)
    result = asyncio.run(runner.run(PromptWorkflowInput.from_execution(request(workflow_id, version="2.1.0", parameters={}))))
    assert events == ["score", "review"]
    assert [step.step_id for step in result.receipt.steps] == ["diagnose", "context", "review"]
    assert result.receipt.context is not None and result.receipt.review.state == review_state
    assert (result.text is not None) == rewritten
    assert len(model.calls) == 1 and model.calls[0].response_schema is not None
    assert model.calls[0].generation.max_tokens == 1100 and model.calls[0].enable_thinking is False
    assert ("rewriting the prompt" if workflow_id == "prompt-rewrite" else "clarification questions") in model.calls[0].system


@pytest.mark.parametrize("workflow_id", ["prompt-rewrite", "prompt-clarify"])
def test_adjusted_flows_preserve_optional_model_and_configurable_review(workflow_id):
    item = request(workflow_id, version="2.1.0", consumer=None)
    result = asyncio.run(PromptWorkflowRunner({}).run(PromptWorkflowInput.from_execution(item)))
    assert result.receipt.context is not None and result.receipt.review.state == "no_active_model"
    assert result.receipt.steps[-1].status == "skipped" and result.text is None
    assert result.receipt.review.prompt_version == "workflow-" + workflow_id.removeprefix("prompt-") + "-review.v1"
    model = Model('{"notes":"Fictional review."}')
    item = request(workflow_id, version="2.1.0", consumer=None, workflow_steps={"review": {
        "binding": {"binding_id": "example-model", "provider": "inference"},
        "policy": {"policy_id": "example-review", "revision": "2", "instructions": "Review the fictional request as JSON."},
        "generation": {"max_tokens": 128, "temperature": None}, "enable_thinking": None}})
    result = asyncio.run(engine(model).execute(item, lambda _: None))
    assert result.status == "succeeded" and result.after == ()
    assert model.calls[0].system == "Review the fictional request as JSON."
    assert model.calls[0].generation.max_tokens == 128 and model.calls[0].enable_thinking is None
    with pytest.raises(ValidationError, match="workflow_step_not_configurable"):
        request(workflow_id, version="2.1.0", workflow_steps={"rewrite": {}})


def test_existing_workflow_digests_keep_their_original_logic():
    expected = {
        "prompt-check": "f0d1466c9240d5377e73b4156326c6290b7b548e2cee2dd5d5bc877c9be5e3e7",
        "prompt-rewrite": "611042bec3f78db0bdaa35a213878dc0da3b5f82ddff3a5901d525c9202166f0",
        "prompt-clarify": "4ada9b4b41be2d06b285f2bebf3bfd668c6c4d66b247e87a2e7048e53faecf71",
    }
    assert {w.workflow_id: w.sha256 for w in WORKFLOWS if w.version == "1.0.0"} == expected
    direct = asyncio.run(engine(Model()).execute(request(), lambda _: None))
    scripted = asyncio.run(engine(Model()).execute(request("prompt-clarify"), lambda _: None))
    assert [step.step_id for step in direct.workflow_result.steps] == ["diagnose", "rewrite"]
    assert [step.step_id for step in scripted.workflow_result.steps] == ["diagnose", "clarify"]
    assert direct.workflow_result.context is None and scripted.workflow_result.review is None


@pytest.mark.parametrize("historical", LEGACY_WORKFLOWS)
def test_core_03_workflow_manifests_preserve_logic_and_historical_compatibility(historical):
    from prompt_enhancer.enhancement.contracts import WorkflowReference
    version = "1.1.0" if historical.version == "1.0.0" else "2.1.0"
    current = next(item for item in WORKFLOWS
                   if item.workflow_id == historical.workflow_id and item.version == version)
    old_ref = WorkflowReference.model_validate(historical.reference())
    new_ref = WorkflowReference.model_validate(current.reference())
    assert resolve(old_ref, "0.2.0") == historical
    assert resolve(new_ref, "0.3.0") == current
    with pytest.raises(ValueError, match="workflow_core_incompatible"):
        resolve(old_ref, "0.3.0")
    with pytest.raises(ValueError, match="workflow_core_incompatible"):
        resolve(new_ref, "0.2.0")
    compatibility = {"version", "compatible_core", "core_version_pattern"}
    assert {k: v for k, v in historical.payload().items() if k not in compatibility} == {
        k: v for k, v in current.payload().items() if k not in compatibility}
    assert historical.sha256 != current.sha256


def test_step_binding_policy_and_parameters_are_effective():
    first, second = Model(), Model()
    item = request(workflow_steps={"rewrite": {"binding": {"binding_id": "example-second", "provider": "inference"},
        "policy": {"policy_id": "example-compact", "revision": "2", "instructions": "Return the fictional rewrite as JSON."},
        "generation": {"max_tokens": 128, "temperature": 0.1, "max_output_chars": 500}}})
    service = EnhancementEngine({"example-model": first, "example-second": second}, {"deterministic.v1": DeterministicEvaluation()})
    result = asyncio.run(service.execute(item, lambda _: None))
    assert result.status == "succeeded" and not first.calls and len(second.calls) == 1
    assert second.calls[0].system == "Return the fictional rewrite as JSON."
    assert second.calls[0].generation.max_tokens == 128
    assert result.effective_workflow_steps == item.workflow_steps
    assert result.workflow_result.steps[-1].policy.policy_id == "example-compact"


def test_configuration_fingerprint_ignores_subject_and_separates_policy_variants():
    model = Model()
    first = asyncio.run(engine(model).execute(request(), lambda _: None))
    other_subject = asyncio.run(engine(model).execute(request(subject={"text": "Review another fictional widget."}), lambda _: None))
    other_policy = asyncio.run(engine(model).execute(request(workflow_steps={"rewrite": {"policy": {
        "policy_id": "example-other", "revision": "1", "instructions": "Return the fictional rewritten prompt as JSON."}}}), lambda _: None))
    assert first.workflow_result.configuration_sha256 == other_subject.workflow_result.configuration_sha256
    assert first.workflow_result.configuration_sha256 != other_policy.workflow_result.configuration_sha256


@pytest.mark.parametrize("changes", [
    {"strategy": "script.clarify.v1"},
    {"workflow_steps": {"diagnose": {"binding": {"binding_id": "example-model", "provider": "inference"}}}},
    {"workflow_steps": {"rewrite": {"implementation": "example.replacement"}}},
    {"objective": {"targets": [{"kind": "numeric", "evaluator_id": "prompt", "metric_key": "prompt.task_definition_coverage", "direction": "increase"}]}},
])
def test_fixed_workflow_structure_and_harness_separation_reject_invalid_configuration(changes):
    with pytest.raises(ValidationError): request(**changes)


def test_workflow_definition_digest_and_version_are_checked():
    reference = request("prompt-check").workflow.model_dump()
    for key, value in (("version", "2.1.0"), ("definition_sha256", "0" * 64)):
        with pytest.raises(ValidationError): request("prompt-check", workflow=reference | {key: value})
    assert json.loads((ROOT / "contracts/enhancement/workflows.json").read_text()) == catalog()


@pytest.mark.parametrize("workflow_id,version", [
    ("prompt-check", "1.1.0"), ("prompt-rewrite", "2.1.0"), ("prompt-clarify", "2.1.0"),
])
@pytest.mark.parametrize("review_state", ["reply_invalid", "model_error"])
def test_failed_review_fails_execution_and_retains_partial_evidence(workflow_id, version, review_state):
    class FailedModel(Model):
        async def complete(self, call):
            self.calls.append(call)
            if review_state == "model_error":
                raise CoreError("consumer_failed")
            return Candidate('{}', self.provenance)

    model, stages = FailedModel(), []
    item = request(workflow_id, version=version, assertions=[{
        "evaluator_id": "prompt", "metric_key": "prompt.task_definition_coverage",
        "operator": "minimum_delta", "threshold": 0,
    }])
    result = asyncio.run(engine(model).execute(item, stages.append))
    assert result.status == "failed"
    assert result.errors[0].code == "workflow_review_" + review_state
    assert result.errors[0].stage == "generate" and not result.errors[0].retryable
    assert result.before and result.workflow_result.diagnostics and result.workflow_result.context
    assert result.workflow_result.review.state == review_state
    assert [step.status for step in result.workflow_result.steps] == ["succeeded", "succeeded", "failed"]
    assert result.candidate is None and result.enhanced_prompt is None and not result.after
    assert result.assertion_outcome == "not_evaluated" and not result.assertions and not result.deltas
    assert stages == ["evaluate_original", "generate"] and len(model.calls) == 1
    assert [timing.stage for timing in result.timings] == stages


def test_review_deadline_does_not_fabricate_output():
    result = asyncio.run(engine(Model(block=True)).execute(
        request("prompt-check", parameters={"timeout_seconds": 1}), lambda _: None))
    assert result.status == "timed_out" and result.enhanced_prompt is None and not result.after


def test_pair_workflow_scores_the_same_pairs_in_order_and_rejects_incomplete_scores():
    from prompt_enhancer.infrastructure.text_models.benchmark import RetrievalCandidate, RetrievalCase
    cases = (RetrievalCase("en", "Fictional request", "example-a", (
        RetrievalCandidate("example-a", "Fictional response"), RetrievalCandidate("example-b", "Another fictional response"))),)
    calls = []
    def stage(name, values):
        def score(inputs):
            calls.append((name, inputs))
            return values
        return score
    result = SessionLinksWorkflow(stage("embedding", ((0.2, 0.8),)), stage("rerank", ((3.0, 1.0),))).run(("example-query",), cases)
    assert calls == [("embedding", cases), ("rerank", cases)] and len(result) == 2
    with pytest.raises(ValueError, match="invalid_model_score_shape"):
        SessionLinksWorkflow(lambda _: (), lambda _: ((3.0, 1.0),)).run(("example-query",), cases)
