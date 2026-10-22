"""Explicit gateway embeddings; vectors never become persisted Bench artifacts."""
from __future__ import annotations

import json
import math
from typing import Literal

from pydantic import Field, SecretStr, model_validator

from .adapters import ConsumerConfig, _access_payload, gateway_transport, reported_gateway_model
from .contracts import Evaluation, Evaluator, Metric, Provenance, Subject
from .ports import CoreError
from .process import run_worker


class EmbeddingEvaluatorConfig(ConsumerConfig):
    provider: Literal["inference"] = "inference"
    model_revision: str = Field(min_length=1, max_length=160)
    model_license: str = Field(min_length=1, max_length=100)
    dimensions: int = Field(strict=True, ge=1, le=8192)

    @model_validator(mode="after")
    def embedding_parameters(self):
        if self.reasoning_effort is not None:
            raise ValueError("embedding_reasoning_parameter_unsupported")
        return self


class InferenceEmbeddingEvaluation:
    kind = "embedding"

    def __init__(self, config: EmbeddingEvaluatorConfig, credential: SecretStr, *, gateway_access=None):
        self.config, self.credential = config, credential
        self.gateway_access = gateway_access
        self.provenance = Provenance(provider="litellm", adapter_version="litellm-embedding.v1",
            model=config.model, model_revision=config.model_revision, model_license=config.model_license,
            tokenizer_revision=config.tokenizer_revision,
            metric_version=f"plain-text-cosine-{config.dimensions}.v1", identity_source="configured")

    def validate(self, spec: Evaluator):
        if spec.kind != self.kind:
            raise CoreError("evaluator_kind_mismatch")
        if spec.generation is not None:
            raise CoreError("local_evaluator_generation_parameter_unsupported")

    async def evaluate(self, subject: Subject, spec: Evaluator) -> Evaluation:
        self.validate(spec)
        payload = await run_worker({"operation": "embedding_inference", "subject": subject.model_dump(),
            "spec": spec.model_dump(), "config": self.config.model_dump(mode="json"),
            "credential": self.credential.get_secret_value(),
            "gateway_access": _access_payload(self.gateway_access)}, remote=True)
        reported = payload.get("reported_model")
        if reported != self.config.model and not (reported is None and self.config.gateway_model_id):
            raise CoreError("evaluator_model_mismatch")
        return Evaluation(evaluator_id=spec.evaluator_id, kind=spec.kind,
            provenance=self.provenance.model_copy(update={"reported_model": reported}),
            metrics=(Metric.model_validate(payload["metric"]),))


def cosine_from_response(response: dict, *, dimensions: int) -> float:
    rows = response.get("data")
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("embedding_rows_invalid")
    vectors = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("index")) is not int:
            raise ValueError("embedding_index_invalid")
        index, vector = row["index"], row.get("embedding")
        if index not in {0, 1} or index in vectors:
            raise ValueError("embedding_index_invalid")
        if (not isinstance(vector, list) or len(vector) != dimensions
                or any(type(value) not in {int, float} or not math.isfinite(value) for value in vector)):
            raise ValueError("embedding_vector_invalid")
        norm = math.hypot(*vector)
        if not math.isfinite(norm) or norm == 0:
            raise ValueError("embedding_norm_invalid")
        vectors[index] = [value / norm for value in vector]
    value = math.fsum(left * right for left, right in zip(vectors[0], vectors[1]))
    if not math.isfinite(value) or not -1.000000000001 <= value <= 1.000000000001:
        raise ValueError("embedding_similarity_invalid")
    return max(-1.0, min(1.0, value))


def embedding_inference(payload):
    from ..config import LiteLLMSettings
    from ..infrastructure.litellm import LiteLLMEmbedding

    config = EmbeddingEvaluatorConfig.model_validate(payload["config"])
    spec, subject = Evaluator.model_validate(payload["spec"]), Subject.model_validate(payload["subject"])
    if spec.kind != "embedding" or spec.generation is not None:
        raise CoreError("evaluator_kind_mismatch")
    settings = LiteLLMSettings(base_url=config.endpoint, model=config.model,
        credential=SecretStr(payload["credential"]), model_revision=config.model_revision,
        model_license=config.model_license, **payload.get("gateway_access", {}))
    status, data, _ = gateway_transport(LiteLLMEmbedding, settings, config)(config.model,
        json.dumps({"input": [spec.target, subject.text]}).encode())
    if status != 200:
        raise CoreError("evaluator_failed", uncertain=True)
    try:
        response = json.loads(data)
    except (ValueError, TypeError):
        raise CoreError("evaluator_failed") from None
    if not isinstance(response, dict):
        raise CoreError("evaluator_model_mismatch")
    reported = reported_gateway_model(response, config)
    if reported != config.model and not (reported is None and config.gateway_model_id):
        raise CoreError("evaluator_model_mismatch")
    try:
        value = cosine_from_response(response, dimensions=config.dimensions)
    except (ValueError, TypeError, OverflowError):
        metric = Metric(key="embedding.similarity", state="unknown", reason="embedding_reply_invalid")
    else:
        metric = Metric(key="embedding.similarity", state="known", value=value, reason="model_similarity")
    return {"metric": metric.model_dump(), "reported_model": reported}
