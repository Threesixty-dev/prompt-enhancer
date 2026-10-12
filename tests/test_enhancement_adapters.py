"""Typed model and worker adapter contracts with entirely fictional responses."""
import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from prompt_enhancer.enhancement.adapters import ConsumerConfig, ProcessConsumer, ProcessTextEvaluation, TextEvaluatorConfig
from prompt_enhancer.enhancement.contracts import Evaluator, GenerationSettings, Subject
from prompt_enhancer.enhancement.evaluators import TypedTextEvaluation
from prompt_enhancer.enhancement.ports import CoreError
from prompt_enhancer.enhancement.worker import inference, openhands, parse_candidate, rubric_inference
from prompt_enhancer.infrastructure.text_models.benchmark import RubricPrediction
from prompt_enhancer.infrastructure.text_models.manifests import ModelManifest, TextModelTask
from test_enhancement_core import consumer_request, context_for


def config(provider="inference"):
    return ConsumerConfig(binding_id="example", provider=provider, endpoint="https://example.invalid",
        credential_env="ENHANCEMENT_EXAMPLE_CREDENTIAL", model="example-model",
        model_revision="example-revision-1", model_license="Apache-2.0")


def manifest(kind):
    return ModelManifest(key="example_model", task={"classifier": TextModelTask.SCOPED_NLI,
        "embedding": TextModelTask.REQUIREMENT_ACTION_RETRIEVAL, "rubric": TextModelTask.STRUCTURED_RUBRIC}[kind],
        repository_id="example/model", revision="a" * 40, tokenizer_repository_id="example/model",
        tokenizer_revision="a" * 40, license_spdx="MIT", weight_filename="model.safetensors",
        weight_sha256="b" * 64, max_sequence_length=128, max_batch_size=1,
        output_label_by_index=((0, "entailment"), (1, "neutral"), (2, "contradiction")) if kind == "classifier" else ())


@pytest.mark.parametrize("kind", ["classifier", "embedding", "rubric"])
def test_typed_dispatch_pins_provenance_and_preserves_value_types(kind):
    calls = []
    class Backend:
        key = "example-backend.v1"
        def predict(self, cases):
            calls.extend(cases)
            return ("neutral",) if kind == "classifier" else (RubricPrediction("abstain", True),)
        def score(self, cases):
            calls.extend(cases)
            return ((0.75,),)
    adapter = TypedTextEvaluation(kind, manifest(kind), Backend())
    spec = Evaluator(evaluator_id="example", kind=kind, binding_id="example",
        target="Fictional target" if kind != "rubric" else None,
        rubric="task_definition" if kind == "rubric" else None)
    result = asyncio.run(adapter.evaluate(Subject(text="Fictional prompt"), spec))
    assert len(calls) == 1
    assert result.provenance.identity_source == "verified_manifest"
    assert result.provenance.model_revision == "a" * 40
    if kind == "classifier":
        assert result.metrics[0].label == "neutral" and result.metrics[0].value is None
    elif kind == "embedding":
        assert result.metrics[0].value == 0.75 and result.metrics[0].label is None
    else:
        assert result.metrics[0].state == "abstained" and result.metrics[0].value is None


def test_malformed_typed_model_output_is_not_zero():
    backend = SimpleNamespace(key="example.v1", score=lambda cases: ((float("nan"),),))
    adapter = TypedTextEvaluation("embedding", manifest("embedding"), backend)
    spec = Evaluator(evaluator_id="example", kind="embedding", binding_id="example", target="Example target")
    metric = asyncio.run(adapter.evaluate(Subject(text="Fictional prompt"), spec)).metrics[0]
    assert metric.state == "execution_error" and metric.value is None


def test_manifest_kind_mismatch_rejected():
    with pytest.raises(CoreError, match="evaluator_manifest_mismatch"):
        TypedTextEvaluation("embedding", manifest("classifier"), None)


@pytest.mark.parametrize("bad", ["not JSON", '{"enhanced_prompt":"ok","extra":1}',
    '{"enhanced_prompt":"first","enhanced_prompt":"second"}', '{"enhanced_prompt":null}'])
def test_consumer_strict_reply(bad):
    with pytest.raises(CoreError):
        parse_candidate(bad, 20000)


def test_inference_reuses_gateway_adapter_and_requires_complete_reply(monkeypatch):
    from prompt_enhancer.infrastructure import litellm
    sent = []
    def chat(settings):
        def complete(model, body):
            sent.append(json.loads(body))
            return 200, json.dumps({"model": "example-model", "choices": [{"finish_reason": "stop",
                "message": {"role": "assistant", "content": '{"enhanced_prompt":"Fictional revised prompt"}'}}]}).encode(), "application/json"
        return complete
    monkeypatch.setattr(litellm, "LiteLLMChat", chat)
    item = consumer_request(parameters={"generation": {"temperature": 0.2, "max_tokens": 128}})
    context = context_for(item)
    result = inference({"config": config().model_dump(), "request": item.model_dump(),
        "generation_context": context.model_dump(), "credential": "example-invalid-value"})
    assert result["text"] == "Fictional revised prompt"
    assert result["reported_model"] == "example-model"
    assert sent[0]["temperature"] == 0.2 and sent[0]["max_tokens"] == 128
    assert len(sent[0]["messages"]) == 2
    assert json.loads(sent[0]["messages"][1]["content"])["generation_context"]["before"] == context.model_dump(mode="json")["before"]


def test_rubric_gateway_is_independent_and_applies_only_evaluation_settings(monkeypatch):
    from prompt_enhancer.infrastructure import litellm
    calls = []
    def chat(settings):
        def complete(model, body):
            calls.append(json.loads(body))
            return 200, json.dumps({"model": "example-model", "choices": [{"finish_reason": "stop",
                "message": {"role": "assistant", "content": '{"label":"abstain"}'}}]}).encode(), "application/json"
        return complete
    monkeypatch.setattr(litellm, "LiteLLMChat", chat)
    spec = Evaluator(evaluator_id="example", kind="rubric", binding_id="example-evaluator",
        rubric="task_definition", generation=GenerationSettings(max_tokens=64, temperature=0.1))
    value = rubric_inference({"config": config().model_dump(), "credential": "example-invalid-value",
        "spec": spec.model_dump(), "subject": {"text": "Fictional input"}})
    assert value["metric"]["state"] == "abstained" and value["metric"]["value"] is None
    assert calls[0]["max_tokens"] == 64 and calls[0]["temperature"] == 0.1


def test_local_rubric_rejects_unsupported_generation_controls():
    adapter = TypedTextEvaluation("rubric", manifest("rubric"), SimpleNamespace(key="example.v1"))
    with pytest.raises(CoreError, match="local_evaluator_generation_parameter_unsupported"):
        adapter.validate(Evaluator(evaluator_id="example", kind="rubric", binding_id="example",
            rubric="task_definition", generation=GenerationSettings(max_tokens=64)))


def test_gateway_access_binding_resolves_only_named_credentials_and_keeps_unknown_identity(monkeypatch):
    from prompt_enhancer.enhancement.adapters import InferenceRubricEvaluation
    from prompt_enhancer.enhancement.cli import _gateway_access
    from prompt_enhancer.enhancement import adapters
    from prompt_enhancer.infrastructure import litellm
    value = config().model_dump()
    value.update(model_revision=None, model_license=None,
        access_client_id_env="ENHANCEMENT_EXAMPLE_ACCESS_ID",
        access_client_secret_env="ENHANCEMENT_EXAMPLE_ACCESS_SECRET")
    binding = ConsumerConfig.model_validate(value)
    environment = {"ENHANCEMENT_EXAMPLE_ACCESS_ID": "example-access-id",
                   "ENHANCEMENT_EXAMPLE_ACCESS_SECRET": "example-access-secret",
                   "UNRELATED_SECRET": "example-unrelated"}
    with pytest.raises(ValueError, match="gateway_access_credential_invalid"):
        _gateway_access(binding, {})
    captured = []
    def chat(settings):
        captured.append(settings)
        return lambda *args: (200, json.dumps({"model": "example-model", "choices": [{
            "finish_reason": "stop", "message": {"role": "assistant", "content": '{"label":"present"}'}}]}).encode(), "application/json")
    monkeypatch.setattr(litellm, "LiteLLMChat", chat)
    async def worker(payload, **kwargs):
        assert "example-unrelated" not in json.dumps(payload)
        return rubric_inference(payload)
    monkeypatch.setattr(adapters, "run_worker", worker)
    adapter = InferenceRubricEvaluation(binding, SecretStr("example-model-key"),
        gateway_access=_gateway_access(binding, environment))
    spec = Evaluator(evaluator_id="example", kind="rubric", binding_id="example", rubric="task_definition")
    result = asyncio.run(adapter.evaluate(Subject(text="Fictional widget request"), spec))
    assert result.metrics[0].label == "present"
    assert result.provenance.model_revision is None and result.provenance.model_license is None
    assert captured[0].access_client_id.get_secret_value() == "example-access-id"
    assert captured[0].access_client_secret.get_secret_value() == "example-access-secret"
    assert captured[0].credential.get_secret_value() == "example-model-key"
    assert "example-access" not in json.dumps(binding.model_dump())
    for changes in ({"access_client_secret_env": None}, {"provider": "openhands_acp"},
                    {"access_client_id_env": binding.credential_env}):
        with pytest.raises(ValidationError):
            ConsumerConfig.model_validate({**value, **changes})


def test_acp_rejects_unsupported_generation_before_process(monkeypatch):
    adapter = ProcessConsumer(config("openhands_acp"), SecretStr("example-invalid-value"))
    with pytest.raises(CoreError, match="acp_generation_parameter_unsupported"):
        adapter.validate(consumer_request(parameters={"generation": {"max_tokens": 128}}))


def test_remote_reported_model_mismatch_is_not_blessed(monkeypatch):
    from prompt_enhancer.enhancement import adapters
    async def worker(*args, **kwargs):
        return {"text": "Fictional prompt", "reported_model": "different-model"}
    monkeypatch.setattr(adapters, "run_worker", worker)
    adapter = ProcessConsumer(config(), SecretStr("example-invalid-value"))
    with pytest.raises(CoreError, match="consumer_model_mismatch"):
        item = consumer_request()
        asyncio.run(adapter.generate(item, context_for(item)))


@pytest.mark.parametrize("provider", ["inference", "openhands_acp"])
def test_process_consumer_forwards_exact_generation_context(monkeypatch, provider):
    from prompt_enhancer.enhancement import adapters
    sent = []
    async def worker(payload, **kwargs):
        sent.append(payload)
        return {"text": "Fictional revised prompt", "reported_model": "example-model"}
    monkeypatch.setattr(adapters, "run_worker", worker)
    monkeypatch.setattr(adapters.importlib.util, "find_spec", lambda name: object())
    item = consumer_request()
    context = context_for(item)
    adapter = ProcessConsumer(config(provider), SecretStr("example-invalid-value"))
    candidate = asyncio.run(adapter.generate(item, context))
    assert sent[0]["generation_context"] == context.model_dump()
    assert candidate.provenance.rubric_version == "enhancement-rewrite.v2"
    if provider == "openhands_acp":
        assert candidate.provenance.operation_id == sent[0]["operation_id"]


def fake_sdk(monkeypatch, *, finished=True, cleanup=True):
    import httpx
    import importlib.metadata
    created, agents, sent = [], [], []
    def conversation(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(send_message=sent.append, run=lambda: None, close=lambda: None,
            state=SimpleNamespace(execution_status="finished" if finished else "running",
                events=[SimpleNamespace(source="agent", llm_message=SimpleNamespace(role="assistant",
                    content=[SimpleNamespace(text='{"enhanced_prompt":"Fictional revised prompt"}')]))]))
    def agent(**kwargs):
        agents.append(kwargs)
        return object()
    def workspace(**kwargs):
        commands = []
        def execute(command, **options):
            commands.append(command)
            return SimpleNamespace(exit_code=0)
        return SimpleNamespace(reset_client=lambda: None, execute_command=execute, commands=commands,
                               working_dir=kwargs["working_dir"])
    modules = {"openhands.sdk": {"Conversation": conversation},
        "openhands.sdk.agent": {"ACPAgent": agent},
        "openhands.sdk.context": {"AgentContext": lambda **kwargs: object()},
        "openhands.sdk.workspace": {"RemoteWorkspace": workspace}}
    for name, attributes in modules.items():
        module = ModuleType(name)
        for key, value in attributes.items():
            setattr(module, key, value)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "1.49.1")
    class Client:
        deleted = False
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, path):
            return SimpleNamespace(status_code=404 if self.deleted and cleanup else 200,
                raise_for_status=lambda: None, json=lambda: {"execution_status": "finished", "current_model_id": "example-model"})
        def delete(self, path):
            self.deleted = True
            return SimpleNamespace(status_code=204)
    monkeypatch.setattr(httpx, "Client", Client)
    return created, agents, sent


def test_acp_allocates_independent_context_and_checks_completion_cleanup(monkeypatch):
    created, agents, sent = fake_sdk(monkeypatch)
    item = consumer_request()
    payload = {"config": config("openhands_acp").model_dump(),
               "request": item.model_dump(), "generation_context": context_for(item).model_dump(),
               "credential": "example-invalid-value"}
    assert openhands(payload)["text"] == "Fictional revised prompt"
    assert openhands(payload)["text"] == "Fictional revised prompt"
    assert created[0]["conversation_id"] != created[1]["conversation_id"]
    for trial in created:
        workspace = trial["workspace"]
        assert workspace.commands == [f"mkdir -m 700 -- {workspace.working_dir}", f"rmdir -- {workspace.working_dir}"]
        assert workspace.working_dir.endswith(str(trial["conversation_id"]))
    assert all(agent["acp_session_mode"] == "read-only" for agent in agents)
    assert json.loads(sent[0])["generation_context"] == json.loads(json.dumps(payload["generation_context"]))


@pytest.mark.parametrize("finish,cleanup", [(False, True), (True, False)])
def test_acp_uncertain_status_and_cleanup_are_not_success(monkeypatch, finish, cleanup):
    fake_sdk(monkeypatch, finished=finish, cleanup=cleanup)
    item = consumer_request()
    with pytest.raises(CoreError) as caught:
        openhands({"config": config("openhands_acp").model_dump(), "request": item.model_dump(),
                   "generation_context": context_for(item).model_dump(),
                   "credential": "example-invalid-value"})
    assert caught.value.uncertain


@pytest.mark.parametrize("provider", ["inference", "openhands_acp"])
def test_changed_objective_and_steering_reach_both_worker_adapters(monkeypatch, provider):
    from prompt_enhancer.infrastructure import litellm
    if provider == "openhands_acp":
        _, _, messages = fake_sdk(monkeypatch)
        operation = openhands
    else:
        messages = []
        def chat(settings):
            def complete(model, body):
                messages.append(json.loads(body)["messages"][1]["content"])
                return 200, json.dumps({"model": "example-model", "choices": [{"finish_reason": "stop",
                    "message": {"role": "assistant", "content": '{"enhanced_prompt":"Fictional revised prompt"}'}}]}).encode(), "application/json"
            return complete
        monkeypatch.setattr(litellm, "LiteLLMChat", chat)
        operation = inference
    first = consumer_request()
    changed = consumer_request(objective={"objective_id": "example-deliverable", "revision": "2",
        "description": "Clarify the fictional deliverable format.", "targets": [{"kind": "numeric",
        "evaluator_id": "prompt", "metric_key": "prompt.deliverable_contract", "direction": "increase"}]},
        steering={"profile": "targeted.v1", "style": "structured", "focus": ["deliverable"],
                  "instructions": "Use a concise fictional checklist."})
    for item in (first, changed):
        operation({"config": config(provider).model_dump(), "request": item.model_dump(),
            "generation_context": context_for(item).model_dump(), "credential": "example-invalid-value"})
    before, after = [json.loads(message)["generation_context"] for message in messages]
    assert before["objective"] != after["objective"] and before["steering"] != after["steering"]
    assert before["before"] == after["before"]
    assert after["before"][0]["provenance"]["provider"] == "deterministic"
    with pytest.raises(CoreError):
        parse_candidate('{"enhanced_prompt":"Fictional prompt","after":{"score":999}}', 20000)
