"""Typed model and worker adapter contracts with entirely fictional responses."""
import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from prompt_enhancer.enhancement.adapters import ConsumerConfig, ProcessConsumer, ProcessTextEvaluation, TextEvaluatorConfig
from prompt_enhancer.enhancement.contracts import Evaluator, GenerationSettings, ModelCall, Subject
from prompt_enhancer.enhancement.evaluators import TypedTextEvaluation
from prompt_enhancer.enhancement.ports import CoreError
from prompt_enhancer.enhancement.worker import acp_failure_code, inference, openhands, parse_candidate, rubric_inference
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


@pytest.mark.parametrize("operation", [inference, rubric_inference])
def test_chat_roles_preserve_transport_cause_without_upstream_details(monkeypatch, operation):
    from test_litellm import Connection, install

    connection = Connection(status=401, data=b"EXAMPLE_PRIVATE_AUTH_RESPONSE")
    created = install(monkeypatch, connection)
    item = consumer_request()
    payload = {"config": config().model_dump(), "credential": "example-invalid-value",
        "request": item.model_dump(), "generation_context": context_for(item).model_dump(),
        "subject": {"text": "Fictional widget request"},
        "spec": {"evaluator_id": "example", "kind": "rubric", "binding_id": "example",
                 "rubric": "task_definition"}}
    with pytest.raises(CoreError) as caught:
        operation(payload)
    assert caught.value.code == "gateway_http_unauthorized" and caught.value.uncertain
    assert "EXAMPLE_PRIVATE_AUTH_RESPONSE" not in str(caught.value)
    assert len(created) == len(connection.requests) == 1 and connection.closed


def test_inference_reuses_gateway_adapter_and_requires_complete_reply(monkeypatch):
    from prompt_enhancer.infrastructure import litellm
    sent = []
    def chat(settings, **kwargs):
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


def test_workflow_provider_transports_only_prepared_messages_and_preserves_review_json(monkeypatch):
    from prompt_enhancer.enhancement import adapters
    from prompt_enhancer.infrastructure import litellm
    sent, worker_inputs = [], []
    reply = '{"notes":"Fictional review without a rewrite."}'
    def chat(settings, **kwargs):
        def complete(model, body):
            sent.append(json.loads(body))
            return 200, json.dumps({"model": "example-model", "choices": [{"finish_reason": "stop",
                "message": {"role": "assistant", "content": reply}}]}).encode(), "application/json"
        return complete
    monkeypatch.setattr(litellm, "LiteLLMChat", chat)
    async def worker(payload, **kwargs):
        worker_inputs.append(payload)
        return inference(payload)
    monkeypatch.setattr(adapters, "run_worker", worker)
    call = ModelCall(system="Review this fictional input.", user="Fictional widget request.",
        policy_version="example-review.v1", generation=GenerationSettings(max_tokens=128, temperature=0.2),
        timeout_seconds=10, enable_thinking=False, response_schema={"type": "object"})
    result = asyncio.run(ProcessConsumer(config(), SecretStr("example-invalid-value")).complete(call))
    assert result.text == reply and result.provenance.rubric_version == call.policy_version
    assert "request" not in worker_inputs[0] and "generation_context" not in worker_inputs[0]
    assert sent[0]["messages"] == [{"role": "system", "content": call.system}, {"role": "user", "content": call.user}]
    assert sent[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert sent[0]["response_format"]["json_schema"]["schema"] == call.response_schema


def test_legacy_generation_context_keeps_its_existing_payload_bound():
    from prompt_enhancer.enhancement.contracts import GenerationContext
    from prompt_enhancer.enhancement.engine import identity
    from prompt_enhancer.enhancement.worker import model_call
    item = consumer_request(evaluation={"profile_id": "example-profile", "revision": "1", "evaluators": [
        {"evaluator_id": f"example-{i}", "kind": "embedding", "binding_id": "example-embedding", "target": "Fictional target. " * 1000}
        for i in range(8)]})
    context = GenerationContext(**identity(item), before=(), evaluation_profile=item.evaluation,
        objective=item.objective, steering=item.steering)
    call = model_call({"request": item.model_dump(), "generation_context": context.model_dump()})
    assert len(call.user) > 100_000
    assert json.loads(call.user)["generation_context"]["evaluation_profile"] == item.evaluation.model_dump(mode="json")


def test_rubric_gateway_is_independent_and_applies_only_evaluation_settings(monkeypatch):
    from prompt_enhancer.infrastructure import litellm
    calls = []
    def chat(settings, **kwargs):
        assert settings.reasoning_effort == "none"
        def complete(model, body):
            calls.append(json.loads(body))
            return 200, json.dumps({"model": "example-model", "choices": [{"finish_reason": "stop",
                "message": {"role": "assistant", "content": '{"label":"abstain"}'}}]}).encode(), "application/json"
        return complete
    monkeypatch.setattr(litellm, "LiteLLMChat", chat)
    spec = Evaluator(evaluator_id="example", kind="rubric", binding_id="example-evaluator",
        rubric="task_definition", generation=GenerationSettings(max_tokens=64, temperature=0.1))
    binding = config().model_copy(update={"reasoning_effort": "none"})
    value = rubric_inference({"config": binding.model_dump(), "credential": "example-invalid-value",
        "spec": spec.model_dump(), "subject": {"text": "Fictional input"}})
    assert value["metric"]["state"] == "abstained" and value["metric"]["value"] is None
    assert calls[0]["max_tokens"] == 64 and calls[0]["temperature"] == 0.1


@pytest.mark.parametrize("finish,content", [
    ("length", ""), ("length", '{"label":"present"}'),
    ("stop", '{"label":"present","extra":true}'),
])
def test_rubric_reasoning_or_invalid_reply_stays_unknown(monkeypatch, finish, content):
    from prompt_enhancer.infrastructure import litellm
    def chat(settings, **kwargs):
        return lambda *args: (200, json.dumps({"choices": [{"finish_reason": finish,
            "message": {"role": "assistant", "content": content,
                        "reasoning_content": "Fictional reasoning"}}]}).encode(), "application/json")
    monkeypatch.setattr(litellm, "LiteLLMChat", chat)
    spec = Evaluator(evaluator_id="example", kind="rubric", binding_id="example-evaluator",
        rubric="task_definition", generation=GenerationSettings())
    result = rubric_inference({"config": config().model_dump(), "credential": "example-invalid-value",
        "spec": spec.model_dump(), "subject": {"text": "Fictional input"}})
    assert result["metric"]["state"] == "unknown"
    assert result["metric"]["label"] is None


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
        reasoning_effort="none",
        access_client_id_env="ENHANCEMENT_EXAMPLE_ACCESS_ID",
        access_client_secret_env="ENHANCEMENT_EXAMPLE_ACCESS_SECRET")
    binding = ConsumerConfig.model_validate(value)
    environment = {"ENHANCEMENT_EXAMPLE_ACCESS_ID": "example-access-id",
                   "ENHANCEMENT_EXAMPLE_ACCESS_SECRET": "example-access-secret",
                   "UNRELATED_SECRET": "example-unrelated"}
    with pytest.raises(ValueError, match="gateway_access_credential_invalid"):
        _gateway_access(binding, {})
    captured = []
    def chat(settings, **kwargs):
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
    assert result.provenance.reasoning_effort == "none"
    assert captured[0].access_client_id.get_secret_value() == "example-access-id"
    assert captured[0].access_client_secret.get_secret_value() == "example-access-secret"
    assert captured[0].credential.get_secret_value() == "example-model-key"
    assert "example-access" not in json.dumps(binding.model_dump())
    for changes in ({"access_client_secret_env": None}, {"provider": "openhands_acp"},
                    {"access_client_id_env": binding.credential_env}):
        with pytest.raises(ValidationError):
            ConsumerConfig.model_validate({**value, **changes})


@pytest.mark.parametrize("generation", [{"max_tokens": 128}, {"temperature": 0.1}])
def test_acp_rejects_unsupported_generation_before_process(monkeypatch, generation):
    adapter = ProcessConsumer(config("openhands_acp"), SecretStr("example-invalid-value"))
    with pytest.raises(CoreError, match="acp_generation_parameter_unsupported"):
        adapter.validate(consumer_request(parameters={"generation": generation}))


def test_acp_binding_rejects_inference_reasoning_control():
    with pytest.raises(ValidationError, match="reasoning_effort_requires_inference"):
        ConsumerConfig.model_validate({**config("openhands_acp").model_dump(), "reasoning_effort": "none"})


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


def fake_sdk(monkeypatch, *, finished=True, cleanup=True, command_runner=None, reply_kind="finish",
             reply='{"enhanced_prompt":"Fictional revised prompt"}', failure_category=None, failure_guard=True):
    import httpx
    import importlib.metadata
    created, agents, sent = [], [], []
    class ActionEvent(SimpleNamespace): pass
    class FinishAction(SimpleNamespace): pass
    class ConversationErrorEvent(SimpleNamespace): pass
    finish = ActionEvent(source="agent", tool_name="finish", action=FinishAction(message=reply))
    events = [SimpleNamespace(source="agent", llm_message=SimpleNamespace(role="assistant",
        content=[SimpleNamespace(text="Fictional intermediate commentary")]))]
    if reply_kind == "finish":
        events.append(finish)
    elif reply_kind == "duplicate":
        events.extend([finish, finish])
    elif reply_kind == "wrong_tool":
        events.append(ActionEvent(source="agent", tool_name="example", action=FinishAction(message=reply)))
    elif reply_kind == "invalid_json":
        events.append(ActionEvent(source="agent", tool_name="finish", action=FinishAction(message="Fictional prose")))
    if failure_category is not None:
        events.append(ConversationErrorEvent(source="agent", code="ACPPromptError",
            detail="[-32603] bench_consumer_upstream_" + failure_category))
    def execute():
        if failure_category is not None:
            raise RuntimeError("example-private-sdk-detail")
    def conversation(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(send_message=sent.append, run=execute, close=lambda: None,
            state=SimpleNamespace(execution_status="finished" if finished else "running",
                events=events))
    def agent(**kwargs):
        agents.append(kwargs)
        return object()
    def workspace(**kwargs):
        commands = []
        def execute(command, **options):
            commands.append(command)
            return SimpleNamespace(exit_code=command_runner(command, kwargs["working_dir"]) if command_runner else 0)
        return SimpleNamespace(reset_client=lambda: None, execute_command=execute, commands=commands,
                               working_dir=kwargs["working_dir"])
    modules = {"openhands.sdk": {"Conversation": conversation},
        "openhands.sdk.agent": {"ACPAgent": agent},
        "openhands.sdk.event": {"ActionEvent": ActionEvent},
        "openhands.sdk.event.conversation_error": {"ConversationErrorEvent": ConversationErrorEvent},
        "openhands.sdk.tool.builtins.finish": {"FinishAction": FinishAction},
        "openhands.sdk.context": {"AgentContext": lambda **kwargs: SimpleNamespace(**kwargs)},
        "openhands.sdk.workspace": {"RemoteWorkspace": workspace}}
    for name, attributes in modules.items():
        module = ModuleType(name)
        for key, value in attributes.items():
            setattr(module, key, value)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "1.49.1")
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, path):
            if path.endswith("/api/bench/retention"):
                return SimpleNamespace(status_code=200, json=lambda: {"version": "bench-retention.v1",
                    "failure_guard": "bench-acp-failure.v1" if failure_guard else None})
            return SimpleNamespace(status_code=200,
                raise_for_status=lambda: None, json=lambda: {"execution_status": "finished", "current_model_id": "example-model"})
        def post(self, path):
            assert path.endswith(("/release", "/retain"))
            return SimpleNamespace(status_code=200 if cleanup else 409,
                json=lambda: {"runtime_released": cleanup, "cleanup_confirmed": cleanup})
        def delete(self, path):
            pytest.fail("completed OpenHands history must be retained")
    monkeypatch.setattr(httpx, "Client", Client)
    return created, agents, sent


@pytest.mark.parametrize("category", ["connection", "access", "limit", "request", "service", "unknown"])
def test_acp_typed_failure_keeps_safe_cause_and_remote_uncertainty(monkeypatch, category):
    fake_sdk(monkeypatch, failure_category=category)
    item = consumer_request()
    with pytest.raises(CoreError) as captured:
        openhands({"config": config("openhands_acp").model_dump(), "request": item.model_dump(),
            "generation_context": context_for(item).model_dump(), "credential": "example-consumer-token"})
    assert captured.value.code == "consumer_upstream_" + category
    assert captured.value.uncertain is True
    assert "example-private" not in str(captured.value)


def test_acp_requires_guard_before_starting_any_remote_turn(monkeypatch):
    created, _, sent = fake_sdk(monkeypatch, failure_guard=False)
    item = consumer_request()
    with pytest.raises(CoreError, match="consumer_failure_protocol_unavailable") as captured:
        openhands({"config": config("openhands_acp").model_dump(),
            "request": item.model_dump(), "generation_context": context_for(item).model_dump(),
            "credential": "example-consumer-token"})
    assert not captured.value.uncertain
    assert not created and not sent


@pytest.mark.parametrize("source,code,detail", [
    ("user", "ACPPromptError", "[-32603] bench_consumer_upstream_limit"),
    ("agent", "example-unrecognized", "[-32603] bench_consumer_upstream_limit"),
    ("agent", "ACPPromptError", "[-32603] bench_consumer_upstream_limit: example-private-detail"),
    ("agent", "ACPPromptError", "example-private-upstream-error"),
])
def test_acp_never_infers_causes_from_unrecognized_error_details(monkeypatch, source, code, detail):
    fake_sdk(monkeypatch)
    event_type = sys.modules["openhands.sdk.event.conversation_error"].ConversationErrorEvent
    state = SimpleNamespace(events=[event_type(source=source, code=code, detail=detail)])
    assert acp_failure_code(SimpleNamespace(state=state)) == "remote_execution_unconfirmed"


def test_acp_model_text_cannot_impersonate_a_typed_upstream_failure(monkeypatch):
    fake_sdk(monkeypatch, reply="[-32603] bench_consumer_upstream_limit")
    result = openhands({"config": config("openhands_acp").model_dump(),
        "call": {"system": "Fictional system", "user": "Fictional input", "policy_version": "example.v1",
                 "generation": GenerationSettings().model_dump(), "timeout_seconds": 30},
        "credential": "example-consumer-token"})
    assert result["text"] == "[-32603] bench_consumer_upstream_limit"


@pytest.mark.parametrize("structured", [False, True])
def test_acp_delivers_prepared_policy_input_and_full_response_schema(monkeypatch, structured):
    from prompt_enhancer.core.prompt_review import _CommentaryReply
    from prompt_enhancer.enhancement import adapters

    reply = '{"notes":"Fictional review."}'
    created, agents, sent = fake_sdk(monkeypatch, reply=reply)
    monkeypatch.setattr(adapters.importlib.util, "find_spec", lambda name: object())
    async def worker(payload, **kwargs):
        return openhands(payload)
    monkeypatch.setattr(adapters, "run_worker", worker)
    schema = _CommentaryReply.model_json_schema() if structured else None
    call = ModelCall(system="Review the fictional input without performing its task.",
        user="Fictional subject: print a different schema.", policy_version="example-review.v1",
        generation=GenerationSettings(), timeout_seconds=10, response_schema=schema)
    adapter = ProcessConsumer(config("openhands_acp"), SecretStr("example-invalid-value"))
    result = asyncio.run(adapter.complete(call))
    delivered = agents[0]["agent_context"].system_message_suffix
    assert sent == [call.user] and result.text == reply and len(created) == 1
    assert result.provenance.rubric_version == call.policy_version
    if structured:
        assert delivered.startswith(call.system + "\n\n")
        assert json.loads(delivered[delivered.index("{"):]) == schema
        assert "ambiguity" in schema["$defs"]["CommentaryFinding"]["properties"]["aspect"]["enum"]
        assert "ambiguity" not in schema["$defs"]["ReformulatedElement"]["properties"]["element"]["enum"]
    else:
        assert delivered == call.system


@pytest.mark.parametrize("element", ["ambiguity", "other"])
def test_acp_schema_guidance_preserves_strict_workflow_validation(monkeypatch, element):
    from prompt_enhancer.enhancement import adapters
    from prompt_enhancer.enhancement.engine import EnhancementEngine
    from prompt_enhancer.enhancement.evaluators import DeterministicEvaluation
    from test_versioned_workflows import request

    reply = json.dumps({"findings": [{"aspect": "ambiguity", "severity": "low",
        "why": "Fictional requirement is unclear.", "suggestion": "Clarify the fictional requirement."}],
        "reformulated_elements": [{"element": element, "suggested": "State the fictional requirement."}]})
    created, _, _ = fake_sdk(monkeypatch, reply=reply)
    monkeypatch.setattr(adapters.importlib.util, "find_spec", lambda name: object())
    async def worker(payload, **kwargs):
        return openhands(payload)
    monkeypatch.setattr(adapters, "run_worker", worker)
    adapter = ProcessConsumer(config("openhands_acp"), SecretStr("example-invalid-value"))
    item = request("prompt-check", consumer={"binding_id": "example", "provider": "openhands_acp"},
        workflow_steps={"review": {"generation": {"max_tokens": None, "temperature": None},
                                   "enable_thinking": None}})
    engine = EnhancementEngine({"example": adapter}, {"deterministic.v1": DeterministicEvaluation()})
    result = asyncio.run(engine.execute(item, lambda _: None))
    assert len(created) == 1 and result.before and not result.after and result.candidate is None
    if element == "ambiguity":
        assert result.status == "failed"
        assert result.errors[0].code == "workflow_review_reply_invalid"
        assert result.workflow_result.review.state == "reply_invalid"
    else:
        assert result.status == "succeeded"
        assert result.workflow_result.review.reformulated_elements[0].element == element


@pytest.mark.parametrize("reply_kind", ["message_only", "duplicate", "wrong_tool", "invalid_json"])
def test_acp_requires_one_valid_finished_turn(monkeypatch, reply_kind):
    created, _, _ = fake_sdk(monkeypatch, reply_kind=reply_kind)
    item = consumer_request()
    with pytest.raises(CoreError, match="consumer_reply_invalid"):
        openhands({"config": config("openhands_acp").model_dump(), "request": item.model_dump(),
            "generation_context": context_for(item).model_dump(), "credential": "example-invalid-value"})
    assert len(created[0]["workspace"].commands) == 2


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
        assert workspace.commands == [f"mkdir -m 700 -- {workspace.working_dir}",
            f"test ! -L {workspace.working_dir} && rm -rf -- {workspace.working_dir}/.git && rmdir -- {workspace.working_dir}"]
        assert workspace.working_dir.endswith(str(trial["conversation_id"]))
    assert all(agent["acp_session_mode"] == "read-only" for agent in agents)
    assert json.loads(sent[0])["generation_context"] == json.loads(json.dumps(payload["generation_context"]))


@pytest.mark.parametrize("residue", ["git_only", "unexpected_file", "symlink"])
def test_acp_cleanup_removes_only_owned_git_metadata(monkeypatch, tmp_path, residue):
    import os
    import shlex
    import shutil
    import subprocess

    if os.name == "nt":
        pytest.skip("Agent Server cleanup uses a POSIX shell")
    owned, outside = tmp_path / "owned", tmp_path / "outside"
    outside.mkdir()
    (outside / ".git").mkdir()
    sentinel = outside / ".git" / "example-sentinel"
    sentinel.write_text("fictional outside data")

    def execute(command, directory):
        if command.startswith("mkdir "):
            owned.mkdir()
            (owned / ".git").mkdir()
            (owned / ".git" / "HEAD").write_text("ref: refs/heads/example")
            if residue == "unexpected_file":
                (owned / "example-artifact").write_text("fictional artifact")
            elif residue == "symlink":
                shutil.rmtree(owned)
                owned.symlink_to(outside, target_is_directory=True)
            return 0
        return subprocess.run(command.replace(directory, shlex.quote(str(owned))), shell=True,
            cwd=tmp_path, env={"PATH": os.defpath}, capture_output=True, timeout=5).returncode

    fake_sdk(monkeypatch, command_runner=execute)
    item = consumer_request()
    payload = {"config": config("openhands_acp").model_dump(), "request": item.model_dump(),
        "generation_context": context_for(item).model_dump(), "credential": "example-invalid-value"}
    if residue == "git_only":
        assert openhands(payload)["text"] == "Fictional revised prompt"
        assert not owned.exists()
    else:
        with pytest.raises(CoreError, match="remote_cleanup_unconfirmed") as caught:
            openhands(payload)
        assert caught.value.uncertain
        assert owned.exists()
        if residue == "unexpected_file":
            assert (owned / "example-artifact").read_text() == "fictional artifact"
    assert sentinel.read_text() == "fictional outside data"


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
        def chat(settings, **kwargs):
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
