"""Configured provider adapters. Requests select aliases, never endpoints."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
import uuid

from pydantic import Field, SecretStr, field_validator, model_validator

from ..infrastructure.text_models.manifests import TEXT_MODEL_MANIFESTS, TextModelTask
from .contracts import Evaluation, Evaluator, ExecuteRequest, GenerationContext, Identifier, Metric, Provenance, Subject, WireModel
from .ports import Candidate, CoreError
from .process import run_worker


class ConsumerConfig(WireModel):
    binding_id: Identifier
    provider: Literal["openhands_acp", "inference"]
    endpoint: str = Field(repr=False)
    credential_env: str = Field(pattern=r"^ENHANCEMENT_[A-Z0-9_]+$")
    model: str = Field(min_length=1, max_length=160)
    model_revision: str | None = Field(default=None, min_length=1, max_length=160)
    model_license: str | None = Field(default=None, min_length=1, max_length=100)
    reasoning_effort: Literal["none", "low", "medium", "high"] | None = None
    access_client_id_env: str | None = Field(default=None, pattern=r"^ENHANCEMENT_[A-Z0-9_]+$")
    access_client_secret_env: str | None = Field(default=None, pattern=r"^ENHANCEMENT_[A-Z0-9_]+$")
    tokenizer_revision: str | None = None
    # The static worker must already expose this reviewed command. The core
    # never launches a new worker host or accesses a local provider account.
    acp_command: tuple[str, ...] = ("codex-acp",)
    acp_server: Literal["codex", "openhands"] = "codex"
    acp_session_mode: Literal["read-only"] = "read-only"

    @field_validator("endpoint")
    @classmethod
    def safe_endpoint(cls, value):
        parsed = urlsplit(value)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("endpoint_invalid")
        if not parsed.hostname or not (parsed.scheme == "https" or
                parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}):
            raise ValueError("verified_https_or_loopback_required")
        return value.rstrip("/")

    @field_validator("acp_command")
    @classmethod
    def bounded_command(cls, value):
        if not 1 <= len(value) <= 16 or any(not v or len(v) > 256 for v in value):
            raise ValueError("acp_command_invalid")
        return value

    @model_validator(mode="after")
    def inference_uses_verified_tls(self):
        if self.provider != "inference" and self.reasoning_effort is not None:
            raise ValueError("reasoning_effort_requires_inference")
        if self.provider == "inference" and not self.endpoint.startswith("https://"):
            raise ValueError("inference_https_required")
        if (self.access_client_id_env is None) != (self.access_client_secret_env is None):
            raise ValueError("gateway_access_pair_required")
        if self.access_client_id_env is not None:
            if self.provider != "inference" or len({self.credential_env, self.access_client_id_env,
                                                    self.access_client_secret_env}) != 3:
                raise ValueError("gateway_access_binding_invalid")
        return self


class TextEvaluatorConfig(WireModel):
    binding_id: Identifier
    kind: Literal["classifier", "embedding", "rubric"]
    manifest_key: str
    cache_root: Path
    device: Literal["cpu", "cuda", "mps"] = "cpu"

    @model_validator(mode="after")
    def compatible(self):
        manifest = TEXT_MODEL_MANIFESTS.get(self.manifest_key)
        supported = {"classifier": {TextModelTask.SCOPED_NLI, TextModelTask.BINARY_NLI},
                     "embedding": {TextModelTask.REQUIREMENT_ACTION_RETRIEVAL},
                     "rubric": {TextModelTask.STRUCTURED_RUBRIC}}
        if manifest is None or manifest.task not in supported[self.kind]:
            raise ValueError("evaluator_manifest_mismatch")
        if not self.cache_root.is_absolute() or self.cache_root.name != "model-eval" or self.cache_root.parent.name != "runtime":
            raise ValueError("explicit_isolated_model_cache_required")
        return self


class ProcessConsumer:
    def __init__(self, config: ConsumerConfig, credential: SecretStr, *, gateway_access=None):
        self.config, self.credential = config, credential
        self.gateway_access = gateway_access
        self.provider = config.provider
        self.provenance = Provenance(provider=config.provider,
            adapter_version="openhands-acp-1.49.1.v4" if config.provider == "openhands_acp" else "litellm-chat-v1",
            model=config.model, model_revision=config.model_revision,
            model_license=config.model_license, tokenizer_revision=config.tokenizer_revision,
            rubric_version="enhancement-rewrite.v2", identity_source="configured",
            reasoning_effort=config.reasoning_effort)

    def validate(self, request: ExecuteRequest):
        if self.provider == "openhands_acp":
            generation = request.parameters.generation
            if generation.max_tokens is not None or generation.temperature is not None:
                raise CoreError("acp_generation_parameter_unsupported")
            if importlib.util.find_spec("openhands") is None:
                raise CoreError("openhands_sdk_unavailable")

    async def generate(self, request: ExecuteRequest, context: GenerationContext) -> Candidate:
        self.validate(request)
        operation_id = str(uuid.uuid4()) if self.provider == "openhands_acp" else None
        try:
            payload = await run_worker({"operation": self.provider, "request": request.model_dump(),
                "operation_id": operation_id, "config": self.config.model_dump(mode="json"),
                "generation_context": context.model_dump(),
                "credential": self.credential.get_secret_value(),
                "gateway_access": _access_payload(self.gateway_access)}, remote=True)
        except CoreError as exc:
            raise CoreError(exc.code, uncertain=exc.uncertain, operation_id=operation_id) from None
        text = payload.get("text")
        if not isinstance(text, str):
            raise CoreError("consumer_reply_invalid")
        reported = payload.get("reported_model")
        if reported is not None and reported != self.config.model:
            raise CoreError("consumer_model_mismatch")
        return Candidate(text, self.provenance.model_copy(update={"reported_model": reported, "operation_id": operation_id}))


_BACKENDS = {
    "auto": "TransformersE5Scorer",
    "e5_embedding": "TransformersE5Scorer",
    "bert_embedding": "TransformersClsEmbeddingScorer",
    "xlm_roberta_cls": "TransformersClsEmbeddingScorer",
    "qwen3_embedding": "TransformersLastTokenEmbeddingScorer",
    "sequence_classifier": "TransformersNliClassifier",
    "modernbert_sequence_classifier": "TransformersNliClassifier",
    "deberta_v2_sequence_classifier": "TransformersNliClassifier",
    "qwen3_instruct": "TransformersStructuredRubricJudge",
}


class ProcessTextEvaluation:
    def __init__(self, config: TextEvaluatorConfig):
        self.config, self.kind = config, config.kind
        manifest = TEXT_MODEL_MANIFESTS[config.manifest_key]
        from ..infrastructure.text_models import transformers_backends
        backend = getattr(transformers_backends, _BACKENDS.get(manifest.architecture, ""), None)
        if manifest.architecture == "auto" and self.kind == "classifier":
            backend = transformers_backends.TransformersNliClassifier
        if backend is None:
            raise CoreError("evaluator_backend_unsupported")
        self.backend = backend.__name__
        self.provenance = Provenance(provider="local_transformers", adapter_version=backend.key,
            model=manifest.repository_id, model_revision=manifest.revision, model_license=manifest.license_spdx,
            tokenizer_revision=manifest.tokenizer_revision, metric_version="typed-text.v1",
            rubric_version="structured-rubric.v1" if self.kind == "rubric" else None,
            identity_source="verified_manifest")

    def validate(self, spec: Evaluator):
        if spec.kind != self.kind:
            raise CoreError("evaluator_kind_mismatch")
        if spec.generation is not None:
            raise CoreError("local_evaluator_generation_parameter_unsupported")
        if importlib.util.find_spec("transformers") is None:
            raise CoreError("transformers_unavailable")

    async def evaluate(self, subject: Subject, spec: Evaluator) -> Evaluation:
        self.validate(spec)
        payload = await run_worker({"operation": "typed_evaluation", "subject": subject.model_dump(),
            "spec": spec.model_dump(), "config": self.config.model_dump(mode="json"), "backend": self.backend})
        return Evaluation.model_validate(payload)


def _access_payload(access):
    return {key: value.get_secret_value() for key, value in access.items()} if access else {}


class InferenceRubricEvaluation:
    """Only structured rubric interpretation uses the chat gateway evaluator."""
    kind = "rubric"

    def __init__(self, config: ConsumerConfig, credential: SecretStr, *, gateway_access=None):
        if config.provider != "inference":
            raise CoreError("rubric_gateway_provider_unsupported")
        self.config, self.credential = config, credential
        self.gateway_access = gateway_access
        self.provenance = Provenance(provider="litellm", adapter_version="litellm-rubric.v2",
            model=config.model, model_revision=config.model_revision, model_license=config.model_license,
            tokenizer_revision=config.tokenizer_revision, rubric_version="structured-rubric.v1",
            metric_version="typed-text.v1", identity_source="configured",
            reasoning_effort=config.reasoning_effort)

    def validate(self, spec: Evaluator):
        if spec.kind != "rubric":
            raise CoreError("evaluator_kind_mismatch")

    async def evaluate(self, subject: Subject, spec: Evaluator) -> Evaluation:
        self.validate(spec)
        payload = await run_worker({"operation": "rubric_inference", "subject": subject.model_dump(),
            "spec": spec.model_dump(), "config": self.config.model_dump(mode="json"),
            "credential": self.credential.get_secret_value(),
            "gateway_access": _access_payload(self.gateway_access)}, remote=True)
        reported = payload.get("reported_model")
        if reported is not None and reported != self.config.model:
            raise CoreError("evaluator_model_mismatch")
        return Evaluation(evaluator_id=spec.evaluator_id, kind=spec.kind,
            provenance=self.provenance.model_copy(update={"reported_model": reported}),
            metrics=(Metric.model_validate(payload["metric"]),))
