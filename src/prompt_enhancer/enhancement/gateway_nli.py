"""Typed NLI gateway binding; never asks a chat model to simulate a classifier."""
from __future__ import annotations

import json
import math
from typing import Literal

from pydantic import SecretStr, model_validator

from .adapters import ConsumerConfig, _access_payload
from .contracts import Evaluation, Evaluator, Metric, Provenance, Subject
from .ports import CoreError
from .process import run_worker
from ..infrastructure.text_models.manifests import TEXT_MODEL_MANIFESTS, TextModelTask


class ClassifierEvaluatorConfig(ConsumerConfig):
    provider: Literal["inference"] = "inference"
    manifest_key: str

    @model_validator(mode="after")
    def classifier_manifest(self):
        manifest = TEXT_MODEL_MANIFESTS.get(self.manifest_key)
        if (manifest is None or manifest.task != TextModelTask.SCOPED_NLI
                or self.model_revision != manifest.revision
                or self.model_license != manifest.license_spdx
                or self.tokenizer_revision != manifest.tokenizer_revision
                or self.reasoning_effort is not None or self.gateway_model_id is not None):
            raise ValueError("evaluator_manifest_mismatch")
        return self


class InferenceClassifierEvaluation:
    kind = "classifier"

    def __init__(self, config: ClassifierEvaluatorConfig, credential: SecretStr, *, gateway_access=None):
        self.config, self.credential = config, credential
        self.gateway_access = gateway_access
        self.provenance = Provenance(provider="litellm", adapter_version="litellm-nli.v1",
            model=config.model, model_revision=config.model_revision, model_license=config.model_license,
            tokenizer_revision=config.tokenizer_revision, metric_version="typed-text.v1",
            identity_source="configured")

    def validate(self, spec: Evaluator):
        if spec.kind != self.kind:
            raise CoreError("evaluator_kind_mismatch")
        if spec.generation is not None:
            raise CoreError("local_evaluator_generation_parameter_unsupported")

    async def evaluate(self, subject: Subject, spec: Evaluator) -> Evaluation:
        self.validate(spec)
        payload = await run_worker({"operation": "nli_inference", "subject": subject.model_dump(),
            "spec": spec.model_dump(), "config": self.config.model_dump(mode="json"),
            "credential": self.credential.get_secret_value(),
            "gateway_access": _access_payload(self.gateway_access)}, remote=True)
        return Evaluation(evaluator_id=spec.evaluator_id, kind=spec.kind,
            provenance=self.provenance,
            metrics=(Metric.model_validate(payload["metric"]),))


def classification_label(response):
    if isinstance(response, list) and len(response) == 1 and isinstance(response[0], list):
        response = response[0]
    if not isinstance(response, list) or len(response) != 3:
        raise ValueError("classifier_reply_invalid")
    scores = {}
    for row in response:
        if not isinstance(row, dict) or set(row) != {"label", "score"}:
            raise ValueError("classifier_reply_invalid")
        label, score = row["label"], row["score"]
        if (not isinstance(label, str) or label not in {"entailment", "neutral", "contradiction"}
                or label in scores or type(score) not in {int, float}
                or not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError("classifier_reply_invalid")
        scores[label] = score
    if not math.isclose(math.fsum(scores.values()), 1, abs_tol=1e-5):
        raise ValueError("classifier_reply_invalid")
    winners = [label for label, score in scores.items() if score == max(scores.values())]
    if len(winners) != 1:
        raise ValueError("classifier_reply_invalid")
    return winners[0]


def nli_inference(payload):
    from ..config import LiteLLMSettings
    from ..infrastructure.litellm import LiteLLMNli

    config = ClassifierEvaluatorConfig.model_validate(payload["config"])
    spec, subject = Evaluator.model_validate(payload["spec"]), Subject.model_validate(payload["subject"])
    if spec.kind != "classifier" or spec.generation is not None:
        raise CoreError("evaluator_kind_mismatch")
    settings = LiteLLMSettings(base_url=config.endpoint, model=config.model,
        credential=SecretStr(payload["credential"]), model_revision=config.model_revision,
        model_license=config.model_license, **payload.get("gateway_access", {}))
    status, data, _ = LiteLLMNli(settings)(config.model, json.dumps({
        "premise": subject.text, "hypothesis": spec.target, "model_revision": config.model_revision}).encode())
    if status != 200:
        raise CoreError("evaluator_failed", uncertain=True)
    try:
        response = json.loads(data)
    except (ValueError, TypeError):
        raise CoreError("evaluator_failed") from None
    try:
        label = classification_label(response)
    except (ValueError, TypeError, OverflowError):
        metric = Metric(key="nli.label", state="unknown", reason="classifier_reply_invalid")
    else:
        metric = Metric(key="nli.label", state="known", label=label, reason="model_interpretation")
    return {"metric": metric.model_dump()}
