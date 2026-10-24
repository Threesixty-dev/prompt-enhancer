"""Configured pair relevance evaluation over the authenticated rerank route."""
from __future__ import annotations

import json
import math
from typing import Literal

from pydantic import Field, SecretStr, model_validator

from .adapters import ConsumerConfig, _access_payload, gateway_transport
from .contracts import Evaluation, Evaluator, Metric, Provenance, Subject
from .ports import CoreError
from .process import run_worker


class RerankEvaluatorConfig(ConsumerConfig):
    provider: Literal["inference"] = "inference"
    model_revision: str = Field(min_length=1, max_length=160)
    model_license: str = Field(min_length=1, max_length=100)
    gateway_model_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,160}$")

    @model_validator(mode="after")
    def rerank_parameters(self):
        if self.reasoning_effort is not None:
            raise ValueError("rerank_reasoning_parameter_unsupported")
        return self


class InferenceRerankEvaluation:
    kind = "rerank"

    def __init__(self, config: RerankEvaluatorConfig, credential: SecretStr, *, gateway_access=None):
        self.config, self.credential = config, credential
        self.gateway_access = gateway_access
        self.provenance = Provenance(provider="litellm", adapter_version="litellm-rerank.v2",
            model=config.model, model_revision=config.model_revision, model_license=config.model_license,
            tokenizer_revision=config.tokenizer_revision, metric_version="pair-relevance.v1",
            identity_source="configured")

    def validate(self, spec: Evaluator):
        if spec.kind != self.kind:
            raise CoreError("evaluator_kind_mismatch")
        if spec.generation is not None:
            raise CoreError("local_evaluator_generation_parameter_unsupported")

    async def evaluate(self, subject: Subject, spec: Evaluator) -> Evaluation:
        self.validate(spec)
        payload = await run_worker({"operation": "rerank_inference", "subject": subject.model_dump(),
            "spec": spec.model_dump(), "config": self.config.model_dump(mode="json"),
            "credential": self.credential.get_secret_value(),
            "gateway_access": _access_payload(self.gateway_access)}, remote=True)
        return Evaluation(evaluator_id=spec.evaluator_id, kind=spec.kind,
            provenance=self.provenance, metrics=(Metric.model_validate(payload["metric"]),))


def pair_relevance(response):
    rows = response.get("results") if isinstance(response, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("rerank_reply_invalid")
    row = rows[0]
    score = row.get("relevance_score")
    if type(row.get("index")) is not int or row["index"] != 0 or type(score) not in {int, float} or not math.isfinite(score):
        raise ValueError("rerank_reply_invalid")
    # This is the model's relevance score, not a calibrated probability.
    return float(score)


def rerank_inference(payload):
    from ..config import LiteLLMSettings
    from ..infrastructure.litellm import LiteLLMRerank

    config = RerankEvaluatorConfig.model_validate(payload["config"])
    spec, subject = Evaluator.model_validate(payload["spec"]), Subject.model_validate(payload["subject"])
    if spec.kind != "rerank" or spec.generation is not None:
        raise CoreError("evaluator_kind_mismatch")
    settings = LiteLLMSettings(base_url=config.endpoint, model=config.model,
        credential=SecretStr(payload["credential"]), model_revision=config.model_revision,
        model_license=config.model_license, **payload.get("gateway_access", {}))
    status, data, _ = gateway_transport(LiteLLMRerank, settings, config)(config.model,
        json.dumps({"query": spec.target, "document": subject.text}).encode())
    if status != 200:
        raise CoreError("evaluator_failed", uncertain=True)
    try:
        score = pair_relevance(json.loads(data))
    except (ValueError, TypeError, OverflowError):
        metric = Metric(key="rerank.relevance", state="unknown", reason="rerank_reply_invalid")
    else:
        metric = Metric(key="rerank.relevance", state="known", value=score, reason="model_relevance")
    return {"metric": metric.model_dump()}
