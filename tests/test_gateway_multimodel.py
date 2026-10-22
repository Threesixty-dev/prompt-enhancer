"""Synthetic contract checks for the integrated gateway evaluator set."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from prompt_enhancer.enhancement.adapters import reported_gateway_model
from prompt_enhancer.enhancement.cli import CoreConfiguration, compose
from prompt_enhancer.enhancement.contracts import Evaluator, Subject
from prompt_enhancer.enhancement.gateway_embeddings import (
    EmbeddingEvaluatorConfig, InferenceEmbeddingEvaluation, cosine_from_response, embedding_inference,
)
from prompt_enhancer.enhancement.gateway_nli import (
    ClassifierEvaluatorConfig, classification_label, nli_inference,
)
from prompt_enhancer.enhancement.gateway_rerank import (
    RerankEvaluatorConfig, InferenceRerankEvaluation, pair_relevance, rerank_inference,
)
from prompt_enhancer.enhancement.ports import CoreError
from prompt_enhancer.infrastructure import litellm
from prompt_enhancer.infrastructure.text_models.manifests import MDEBERTA_XNLI
from test_litellm import Connection, install, settings


def config(kind="embedding", **changes):
    values = dict(binding_id="example-evaluator", endpoint="https://gateway.example.test",
        credential_env="ENHANCEMENT_EXAMPLE_TOKEN", model="example-alias",
        model_revision="a" * 40, model_license="MIT", gateway_model_id="example-route")
    if kind == "embedding":
        values["dimensions"] = 2
        cls = EmbeddingEvaluatorConfig
    elif kind == "rerank":
        cls = RerankEvaluatorConfig
    else:
        cls = ClassifierEvaluatorConfig
        values.update(manifest_key=MDEBERTA_XNLI.key, model_revision=MDEBERTA_XNLI.revision,
            tokenizer_revision=MDEBERTA_XNLI.tokenizer_revision, gateway_model_id=None)
    values.update(changes)
    return cls(**values)


def payload(kind="embedding", **changes):
    value = {"config": config(kind).model_dump(mode="json"), "credential": "example-invalid-token",
        "subject": {"text": "Return a fictional widget count.", "context": []},
        "spec": {"evaluator_id": "example", "kind": kind, "binding_id": "example-evaluator",
                 "target": "Return a widget count."}}
    value.update(changes)
    return value


@pytest.mark.parametrize("adapter,body,path", [
    (litellm.LiteLLMEmbedding, {"input": ["Example A", "Example B"]}, "/v1/embeddings"),
    (litellm.LiteLLMRerank, {"query": "Example A", "document": "Example B"}, "/v1/rerank"),
    (litellm.LiteLLMNli, {"premise": "Example A", "hypothesis": "Example B", "model_revision": "a" * 40}, "/v1/bench/nli"),
])
def test_typed_transports_preserve_operation_and_privacy(monkeypatch, adapter, body, path):
    connection = Connection()
    install(monkeypatch, connection)
    assert adapter(settings(model_revision="a" * 40))("example-qwen", json.dumps(body).encode())[0] == 200
    _, actual_path, sent, headers = connection.requests[0]
    assert actual_path == path
    data = json.loads(sent)
    assert data["model"] == "example-qwen"
    assert headers["x-litellm-enable-message-redaction"] == "true"
    assert connection.closed
    if adapter is litellm.LiteLLMNli:
        assert data["args"] == [{"text": "Example A", "text_pair": "Example B"}]
        assert data["top_k"] is None and data["truncation"] is False
        assert "kwargs" not in data
    elif adapter is litellm.LiteLLMRerank:
        assert data["documents"] == ["Example B"] and data["return_documents"] is False
        assert data["top_n"] == 1 and data["no-log"] is True
    else:
        assert data["input"] == ["Example A", "Example B"] and data["truncate"] is False


@pytest.mark.parametrize("actual", [None, "example-other-route", "example-route"])
def test_gateway_route_header_is_checked_before_accepting_body(monkeypatch, actual):
    connection = Connection()
    response = connection.getresponse()
    response.getheader = lambda key, default=None: actual if key.lower() == "x-litellm-model-id" else default
    connection.getresponse = lambda: response
    install(monkeypatch, connection)
    result = litellm.LiteLLMEmbedding(settings(), expected_route_id="example-route")(
        "example-qwen", b'{"input":["Example A","Example B"]}')
    assert result[0] == (200 if actual == "example-route" else 502)
    assert connection.closed


@pytest.mark.parametrize("adapter,body", [
    (litellm.LiteLLMEmbedding, {"input": ["Example A"]}),
    (litellm.LiteLLMRerank, {"query": "Example A", "document": "Example B", "api_base": "https://example.test"}),
    (litellm.LiteLLMNli, {"premise": "Example A", "hypothesis": "Example B", "model_revision": "b" * 40}),
])
def test_invalid_input_is_rejected_before_connect(monkeypatch, adapter, body):
    connection = Connection()
    install(monkeypatch, connection)
    assert adapter(settings(model_revision="a" * 40))("example-qwen", json.dumps(body).encode())[0] == 502
    assert not connection.connected


def test_vectors_respect_indexes_and_stay_out_of_result(monkeypatch):
    response = {"model": "example-alias", "data": [
        {"index": 1, "embedding": [3., 4.]}, {"index": 0, "embedding": [1., 0.]}]}
    monkeypatch.setattr(litellm, "LiteLLMEmbedding", lambda *a, **k:
        lambda *args: (200, json.dumps(response).encode(), "application/json"))
    value = embedding_inference(payload())
    assert value["metric"]["value"] == pytest.approx(.6)
    assert "embedding" not in value and "data" not in value
    response["data"][1]["embedding"] = [0, 0]
    value = embedding_inference(payload())
    assert value["metric"]["state"] == "unknown" and value["metric"]["value"] is None


@pytest.mark.parametrize("vector", [[True, 0], [float("nan"), 0], [1], [float("inf"), 0]])
def test_invalid_vectors_do_not_become_zero(vector):
    with pytest.raises(ValueError):
        cosine_from_response({"data": [{"index": 0, "embedding": [1, 0]},
            {"index": 1, "embedding": vector}]}, dimensions=2)


def classifier_reply():
    return [{"label": "contradiction", "score": .1}, {"label": "entailment", "score": .8},
            {"label": "neutral", "score": .1}]


def test_native_nli_keeps_categorical_result_without_inventing_identity(monkeypatch):
    monkeypatch.setattr(litellm, "LiteLLMNli", lambda settings:
        lambda *args: (200, json.dumps(classifier_reply()).encode(), "application/json"))
    result = nli_inference(payload("classifier"))
    assert result["metric"]["label"] == "entailment" and result["metric"]["value"] is None
    assert "reported_model" not in result
    assert classification_label([classifier_reply()]) == "entailment"


@pytest.mark.parametrize("reply", [[], {"label": "entailment"},
    [{"label": "entailment", "score": 1}],
    [{"label": "entailment", "score": .5}, {"label": "neutral", "score": .5}, {"label": "contradiction", "score": 0}],
    [{"label": "entailment", "score": True}, {"label": "neutral", "score": 0}, {"label": "contradiction", "score": 0}],
    [{"label": "entailment", "score": .8}, {"label": "entailment", "score": .1}, {"label": "neutral", "score": .1}],
])
def test_nli_partial_duplicate_tied_or_malformed_scores_are_unknown(monkeypatch, reply):
    monkeypatch.setattr(litellm, "LiteLLMNli", lambda settings:
        lambda *args: (200, json.dumps(reply).encode(), "application/json"))
    result = nli_inference(payload("classifier"))
    assert result["metric"]["state"] == "unknown" and result["metric"]["label"] is None


def test_rerank_preserves_score_without_probability_conversion(monkeypatch):
    assert pair_relevance({"results": [{"index": 0, "relevance_score": -2.5}]}) == -2.5
    monkeypatch.setattr(litellm, "LiteLLMRerank", lambda *a, **k:
        lambda *args: (200, b'{"results":[{"index":0,"relevance_score":0.75}]}', "application/json"))
    value = rerank_inference(payload("rerank"))
    assert value["metric"]["value"] == .75
    assert set(value) == {"metric"}


@pytest.mark.parametrize("rows", [[], [{"index": 1, "relevance_score": .5}],
    [{"index": False, "relevance_score": .5}], [{"index": 0, "relevance_score": True}],
    [{"index": 0, "relevance_score": float("nan")}],
    [{"index": 0, "relevance_score": .5}, {"index": 0, "relevance_score": .4}]])
def test_rerank_invalid_index_or_score_stays_unknown(monkeypatch, rows):
    monkeypatch.setattr(litellm, "LiteLLMRerank", lambda *a, **k:
        lambda *args: (200, json.dumps({"results": rows}).encode(), "application/json"))
    value = rerank_inference(payload("rerank"))
    assert value["metric"]["state"] == "unknown" and value["metric"]["value"] is None


def test_configured_route_does_not_report_a_server_weights_path():
    assert reported_gateway_model({"model": "/srv/example/weights/model.gguf"}, config()) is None
    assert reported_gateway_model({"model": "example-alias"}, config()) == "example-alias"


def test_all_gateway_evaluator_kinds_are_composed_with_explicit_credentials():
    values = CoreConfiguration(embedding_evaluators=(config(binding_id="example-embedding"),),
        classifier_evaluators=(config("classifier", binding_id="example-nli"),),
        rerank_evaluators=(config("rerank", binding_id="example-rerank"),))
    with pytest.raises(ValueError, match="evaluator_credential_missing"):
        compose(values, enabled=True, environment={})
    token = "example-" * 8
    with TestClient(compose(values, enabled=True, environment={"ENHANCEMENT_EXAMPLE_TOKEN": token,
            "ENHANCEMENT_API_TOKEN": token})) as client:
        response = client.get("/v1/capabilities", headers={"Authorization": "Bearer " + token})
        assert response.status_code == 200
        assert {r["kind"] for r in response.json()["evaluators"]} == {"deterministic", "embedding", "classifier", "rerank"}


def test_rerank_contract_requires_target_and_forbids_generation():
    with pytest.raises(ValidationError):
        Evaluator(evaluator_id="example", kind="rerank", binding_id="example")
    with pytest.raises(ValidationError):
        Evaluator(evaluator_id="example", kind="rerank", binding_id="example", target="Example", generation={})


def test_core_executes_all_evaluator_types_before_and_after_one_workflow(monkeypatch):
    from collections import Counter
    from prompt_enhancer.enhancement import adapters, gateway_embeddings, gateway_nli, gateway_rerank
    from prompt_enhancer.enhancement.adapters import InferenceRubricEvaluation
    from prompt_enhancer.enhancement.engine import EnhancementEngine
    from prompt_enhancer.enhancement.evaluators import DeterministicEvaluation
    from prompt_enhancer.enhancement.gateway_nli import InferenceClassifierEvaluation
    from prompt_enhancer.enhancement.worker import rubric_inference
    from test_enhancement_core import request

    calls = Counter()
    responses = {
        "embedding": {"model": "example-alias", "data": [
            {"index": 0, "embedding": [1., 0.]}, {"index": 1, "embedding": [0.6, 0.8]}]},
        "nli": classifier_reply(),
        "rerank": {"results": [{"index": 0, "relevance_score": .7}]},
        "rubric": {"model": "example-alias", "choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": '{"label":"present"}'}}]},
    }
    def transport(kind):
        def adapter(settings, **kwargs):
            def invoke(*args):
                calls[kind] += 1
                return 200, json.dumps(responses[kind]).encode(), "application/json"
            return invoke
        return adapter
    for name, kind in (("LiteLLMEmbedding", "embedding"), ("LiteLLMNli", "nli"),
                       ("LiteLLMRerank", "rerank"), ("LiteLLMChat", "rubric")):
        monkeypatch.setattr(litellm, name, transport(kind))
    operations = {"embedding_inference": embedding_inference, "nli_inference": nli_inference,
                  "rerank_inference": rerank_inference, "rubric_inference": rubric_inference}
    async def worker(value, **kwargs):
        return operations[value["operation"]](value)
    for module in (adapters, gateway_embeddings, gateway_nli, gateway_rerank):
        monkeypatch.setattr(module, "run_worker", worker)
    token = SecretStr("example-invalid-token")
    rubric_config = adapters.ConsumerConfig.model_validate({k: v for k, v in config().model_dump().items()
        if k != "dimensions"})
    providers = {"deterministic.v1": DeterministicEvaluation(),
        "example-embedding": InferenceEmbeddingEvaluation(config(), token),
        "example-nli": InferenceClassifierEvaluation(config("classifier"), token),
        "example-rerank": InferenceRerankEvaluation(config("rerank"), token),
        "example-rubric": InferenceRubricEvaluation(rubric_config, token)}
    evaluators = [{"evaluator_id": "prompt", "kind": "deterministic", "binding_id": "deterministic.v1"}]
    for kind, binding in (("embedding", "example-embedding"), ("classifier", "example-nli"), ("rerank", "example-rerank")):
        evaluators.append({"evaluator_id": kind, "kind": kind, "binding_id": binding,
                           "target": "Return a code patch and unit tests."})
    evaluators.append({"evaluator_id": "rubric", "kind": "rubric", "binding_id": "example-rubric",
                       "rubric": "acceptance_testability"})
    item = request(evaluation={"profile_id": "example-full-profile", "revision": "1", "evaluators": evaluators})
    stages = []
    result = asyncio.run(EnhancementEngine({}, providers).execute(item, stages.append))
    assert result.status == "succeeded"
    assert stages == ["evaluate_original", "generate", "evaluate_candidate", "compare"]
    assert {e.kind for e in result.before} == {e.kind for e in result.after} == {
        "deterministic", "embedding", "classifier", "rerank", "rubric"}
    assert calls == Counter(embedding=2, nli=2, rerank=2, rubric=2)
    assert all(left.provenance == right.provenance for left, right in zip(result.before, result.after))
    assert next(d for d in result.deltas if d.metric_key == "rerank.relevance").value == 0
    assert next(d for d in result.deltas if d.metric_key == "nli.label").state == "not_comparable"
    assert '"embedding": [' not in result.model_dump_json()
