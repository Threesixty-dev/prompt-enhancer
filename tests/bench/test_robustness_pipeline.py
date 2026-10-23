"""Real orchestration and export with synthetic providers; no network or model proof."""

import asyncio
import csv
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from enhancement_bench.analysis import dataset, inspect_run, validated_run, write_export
from enhancement_bench.definitions import CoreImage, Overrides, Publication, Subject as BenchSubject
from prompt_enhancer.enhancement import CORE_VERSION
from prompt_enhancer.enhancement.contracts import Evaluation, ExecuteRequest, Metric, Provenance, Subject
from prompt_enhancer.enhancement.engine import EnhancementEngine
from prompt_enhancer.enhancement.evaluators import DeterministicEvaluation
from prompt_enhancer.enhancement.ports import Candidate, CoreError

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "registry.example.com/example/core@sha256:" + "a" * 64


def experiment(workflow):
    value = json.loads((ROOT / f"experiments/example-robustness-prompt-{workflow}-20261023-r1.json").read_text())
    value.update(autoRun=True, enhancerVersion=CORE_VERSION,
                 coreBuild={"variant": "default", "image": IMAGE, "buildInputSha256": "b" * 64})
    value["subjects"] = [value["subjects"][1]]
    value["subjects"][0]["context"] = [{"role": "user", "content": "EXAMPLE_CONTEXT: preserve the public interface."}]
    value["units"] = [value["units"][0]]
    value["units"][0]["stepSettings"]["review"]["binding"] = {"binding_id": "example-review", "provider": "inference"}
    for spec in value["evaluatorProfile"]["evaluators"]:
        spec["binding_id"] = "example-" + spec["kind"]
    return value


class RecordingEvaluator:
    def __init__(self, kind, events):
        self.kind, self.events, self.calls = kind, events, []
        self.delegate = DeterministicEvaluation() if kind == "deterministic" else None
        self.provenance = self.delegate.provenance if self.delegate else Provenance(
            provider="example", adapter_version="example.v1", model="example-" + kind,
            model_revision="example-r1", model_license="example-license", identity_source="configured")

    def validate(self, spec):
        assert spec.kind == self.kind
        if self.delegate:
            self.delegate.validate(spec)

    async def evaluate(self, subject, spec):
        self.events.append(("evaluation", self.kind, subject.text))
        self.calls.append((subject, spec))
        if self.delegate:
            return await self.delegate.evaluate(subject, spec)
        first = len(self.calls) == 1
        metric = {
            "embedding": Metric(key="embedding.similarity", state="known", value=0 if first else 0.75, reason="example"),
            "classifier": Metric(key="nli.label", state="known", label="neutral" if first else "entailment", reason="example"),
            "rerank": Metric(key="rerank.relevance", state="unknown" if first else "known",
                             value=None if first else -0.25, reason="example_unavailable" if first else "example"),
            "rubric": Metric(key="rubric.label", state="abstained", reason="example_ambiguous"),
        }[self.kind]
        return Evaluation(evaluator_id=spec.evaluator_id, kind=spec.kind,
                          provenance=self.provenance, metrics=(metric,))


class RecordingReview:
    provider = "inference"
    provenance = Provenance(provider="example", adapter_version="example.v1", model="example-review",
                            model_revision="example-r1", identity_source="configured")

    def __init__(self, outcome, text, events):
        self.outcome, self.text, self.events, self.calls = outcome, text, events, []

    def validate_call(self, call):
        assert call.generation.max_tokens is None and call.generation.temperature is None

    async def complete(self, call):
        self.events.append(("review", self.outcome, None))
        self.calls.append(call)
        if self.outcome == "model-error":
            raise CoreError("example_provider_unavailable")
        text = (json.dumps({"reformulated_prompt": self.text}) if self.outcome == "rewrite" else
                '{"notes":"The fictional request needs no rewrite."}' if self.outcome == "notes" else '{}')
        return Candidate(text, self.provenance.model_copy(update={"rubric_version": call.policy_version}))


@pytest.mark.parametrize("workflow", ["check", "rewrite", "clarify"])
@pytest.mark.parametrize("outcome", ["rewrite", "notes", "malformed", "model-error", "no-model"])
def test_real_pipeline_preserves_order_inputs_states_and_export(store, contracts, tmp_path, workflow, outcome):
    definition = experiment(workflow)
    if outcome == "no-model":
        definition["units"][0]["stepSettings"] = {}
    store.register_core_image(CoreImage(schemaVersion="core-release/v1", coreVersion=CORE_VERSION,
        variant="default", image=IMAGE, buildInputSha256="b" * 64, validatedSourceRevision="c" * 40,
        action="built", runtimeVerified=True))
    run_id = store.import_publication(Publication.model_validate({
        "schemaVersion": "bench-publication/v2", "definition": definition}))["runId"]
    run = store.claim()
    attempt = run["attempts"][0]
    payload = contracts.request(run, attempt)
    request = ExecuteRequest.model_validate(payload)
    events, stages = [], []
    candidate = request.subject.text + " Acceptance: test each boundary with explicit assertions."
    model = RecordingReview(outcome, candidate, events)
    providers = {spec.binding_id: RecordingEvaluator(spec.kind, events) for spec in request.evaluation.evaluators}
    engine = EnhancementEngine({"example-review": model}, providers)
    store.attempt_started(run_id, attempt["id"], payload)
    result = asyncio.run(engine.execute(request, stages.append))
    wire = result.model_dump(mode="json")
    contracts.result(wire, payload, CORE_VERSION)
    store.attempt_finished(run_id, attempt["id"], result.status, wire)
    store.finish(run_id, result.status, assertion=result.assertion_outcome)
    store.cleanup_confirmed(run_id)

    kinds = [spec.kind for spec in request.evaluation.evaluators]
    expected = [("evaluation", kind, request.subject.text) for kind in kinds]
    if outcome != "no-model":
        expected.append(("review", outcome, None))
    if outcome == "rewrite":
        expected.extend(("evaluation", kind, candidate) for kind in kinds)
    assert events == expected
    for spec in request.evaluation.evaluators:
        calls = providers[spec.binding_id].calls
        assert [subject.text for subject, _ in calls] == [request.subject.text] + ([candidate] if outcome == "rewrite" else [])
        assert all(subject.context == request.subject.context and observed == spec for subject, observed in calls)
    assert [step.step_id for step in result.workflow_result.steps] == ["diagnose", "context", "review"]
    if model.calls:
        assert "EXAMPLE_CONTEXT" in model.calls[0].user
        assert request.subject.text in model.calls[0].user
        assert request.evaluation.evaluators[1].target not in model.calls[0].user
        assert "example_unavailable" not in model.calls[0].user

    failed = outcome in {"malformed", "model-error"}
    assert result.status == ("failed" if failed else "succeeded")
    assert stages == (["evaluate_original", "generate"] if failed else
                      ["evaluate_original", "generate", "evaluate_candidate", "compare"] if outcome == "rewrite" else
                      ["evaluate_original", "generate", "compare"])
    checked = validated_run(store.run(run_id), contracts)
    report = inspect_run(checked)
    tables = dataset([checked])["tables"]
    assert report["attempts"][0]["technicalOutcome"] == ("failed" if failed else "succeeded")
    assert report["attempts"][0]["missingEvaluators"]["before"] == []
    assert tables["attempts"][0]["workflow_step_order"] == ["diagnose", "context", "review"]
    rows = {row["evaluator_id"]: row for row in tables["metrics"] if row["evaluator_id"] != "prompt"}
    assert rows["embedding"]["before_value"] == 0
    assert rows["nli"]["before_label"] == "neutral" and rows["nli"]["delta_value"] is None
    assert rows["rerank"]["before_state"] == "unknown" and rows["rerank"]["before_value"] is None
    assert rows["rubric"]["before_state"] == "abstained" and rows["rubric"]["before_value"] is None
    if outcome == "rewrite":
        assert rows["embedding"]["delta_value"] == 0.75 and rows["embedding"]["pair_eligible"]
        assert rows["nli"]["after_label"] == "entailment"
        assert rows["rerank"]["after_value"] == -0.25 and rows["rerank"]["delta_value"] is None
    else:
        assert result.candidate is None and result.enhanced_prompt is None and not result.after
        assert all(row["after_state"] == "missing" and row["delta_value"] is None for row in rows.values())
        assert result.assertion_outcome == ("not_evaluated" if failed else "unknown")
    output = tmp_path / "export"
    write_export(output, dataset([checked]))
    with (output / "metrics.csv").open() as stream:
        exported = {row["evaluator_id"]: row for row in csv.DictReader(stream) if row["evaluator_id"] != "prompt"}
    assert float(exported["embedding"]["before_value"]) == 0
    assert exported["rerank"]["before_value"] == "" and exported["rubric"]["before_value"] == ""
    assert exported["nli"]["before_label"] == "neutral"


@pytest.mark.parametrize("text", ["", " \t\r\n", "x" * 20001, "\ud800"])
def test_invalid_prompt_boundaries_are_rejected(text):
    with pytest.raises(ValidationError):
        Subject(text=text)


@pytest.mark.parametrize("context", [
    [{"role": "user", "content": "x" * 8001}],
    [{"role": "user", "content": "x" * 5000}] * 8 + [{"role": "user", "content": "x"}],
    [{"role": "user", "content": "x"}] * 25,
    [{"role": "system", "content": "Example untrusted role"}],
])
def test_invalid_core_context_boundaries_are_rejected(context):
    with pytest.raises(ValidationError):
        Subject(text="Example", context=context)


def test_bench_context_count_and_valid_exact_core_boundaries():
    with pytest.raises(ValidationError):
        BenchSubject(id="example-case", text="Example", context=[{"role": "user", "content": "Example"}] * 9)
    context = [{"role": "user", "content": "x" * 5000}] * 8
    assert len(Subject(text="x" * 20000, context=context).text) == 20000
    assert Subject(text="Example", context=[{"role": "user", "content": "x" * 8000}])


@pytest.mark.parametrize("exit_path", ["lost-acknowledgement", "worker-restart"])
@pytest.mark.parametrize("binding", [None, {"binding_id": "example-review", "provider": "inference"}])
def test_step_bound_remote_operation_holds_admission_after_uncertain_stop(store, publication, exit_path, binding):
    first = store.import_publication(publication)["runId"]
    run = store.claim()
    request = {"consumer": None, "workflow_steps": {"review": {"binding": binding}}}
    store.attempt_started(first, run["attempts"][0]["id"], request)
    store.enqueue_ui(publication.definition.stableId, publication.definition.revision, Overrides(), str(uuid4()))
    if exit_path == "worker-restart":
        store.recover()
    else:
        store.attempt_finished(first, run["attempts"][0]["id"], "interrupted", error="core_transport_uncertain")
        store.finish(first, "interrupted")
    store.cleanup_confirmed(first)
    assert bool(store.run(first)["reconciliation_required"]) == (binding is not None)
    if binding is not None:
        assert store.claim() is None
        store.acknowledge_remote_stopped(first, "example-verified-stop-receipt")
    assert store.claim() is not None
