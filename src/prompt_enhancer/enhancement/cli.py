"""Explicit synthetic benchmark composition; never reads application settings."""
from __future__ import annotations

import argparse
import importlib.util
import importlib.metadata
import os
from pathlib import Path

from pydantic import Field, SecretStr
import uvicorn

from .adapters import ConsumerConfig, InferenceRubricEvaluation, ProcessConsumer, ProcessTextEvaluation, TextEvaluatorConfig
from .contracts import WireModel
from .engine import EnhancementEngine
from .evaluators import DeterministicEvaluation
from .gateway_embeddings import EmbeddingEvaluatorConfig, InferenceEmbeddingEvaluation
from .gateway_nli import ClassifierEvaluatorConfig, InferenceClassifierEvaluation
from .gateway_rerank import RerankEvaluatorConfig, InferenceRerankEvaluation
from .http import create_app
from .manager import ExecutionManager


class CoreConfiguration(WireModel):
    consumers: tuple[ConsumerConfig, ...] = Field(default=(), max_length=8)
    evaluators: tuple[TextEvaluatorConfig, ...] = Field(default=(), max_length=8)
    rubric_evaluators: tuple[ConsumerConfig, ...] = Field(default=(), max_length=8)
    embedding_evaluators: tuple[EmbeddingEvaluatorConfig, ...] = Field(default=(), max_length=8)
    classifier_evaluators: tuple[ClassifierEvaluatorConfig, ...] = Field(default=(), max_length=8)
    rerank_evaluators: tuple[RerankEvaluatorConfig, ...] = Field(default=(), max_length=8)
    max_active: int = Field(default=1, ge=1, le=4)
    max_retained: int = Field(default=32, ge=1, le=128)


def _gateway_access(config: ConsumerConfig, environment: dict[str, str]):
    if config.access_client_id_env is None:
        return None
    result = {}
    for key, name in (("access_client_id", config.access_client_id_env),
                      ("access_client_secret", config.access_client_secret_env)):
        value = environment.get(name, "")
        if not 1 <= len(value) <= 4096 or any(not 33 <= ord(c) <= 126 for c in value):
            raise ValueError("gateway_access_credential_invalid")
        result[key] = SecretStr(value)
    return result


def compose(config: CoreConfiguration, *, enabled: bool, environment: dict[str, str]):
    consumers = {}
    evaluators = {"deterministic.v1": DeterministicEvaluation()}
    for item in config.consumers:
        if item.binding_id in consumers:
            raise ValueError("duplicate_consumer_binding")
        credential = environment.get(item.credential_env)
        if not credential:
            raise ValueError("consumer_credential_missing")
        if item.provider == "openhands_acp" and importlib.metadata.version("openhands-sdk") != "1.49.1":
            raise ValueError("openhands_sdk_version_unsupported")
        consumers[item.binding_id] = ProcessConsumer(item, SecretStr(credential),
            gateway_access=_gateway_access(item, environment))
    for item in config.evaluators:
        if item.binding_id in evaluators:
            raise ValueError("duplicate_evaluator_binding")
        if importlib.util.find_spec("transformers") is None or importlib.util.find_spec("torch") is None:
            raise ValueError("typed_model_dependencies_unavailable")
        evaluators[item.binding_id] = ProcessTextEvaluation(item)
    for item in config.rubric_evaluators:
        if item.binding_id in evaluators:
            raise ValueError("duplicate_evaluator_binding")
        credential = environment.get(item.credential_env)
        if not credential:
            raise ValueError("evaluator_credential_missing")
        evaluators[item.binding_id] = InferenceRubricEvaluation(item, SecretStr(credential),
            gateway_access=_gateway_access(item, environment))
    for item in config.embedding_evaluators:
        if item.binding_id in evaluators:
            raise ValueError("duplicate_evaluator_binding")
        credential = environment.get(item.credential_env)
        if not credential:
            raise ValueError("evaluator_credential_missing")
        evaluators[item.binding_id] = InferenceEmbeddingEvaluation(item, SecretStr(credential),
            gateway_access=_gateway_access(item, environment))
    for item in config.classifier_evaluators:
        if item.binding_id in evaluators:
            raise ValueError("duplicate_evaluator_binding")
        credential = environment.get(item.credential_env)
        if not credential:
            raise ValueError("evaluator_credential_missing")
        evaluators[item.binding_id] = InferenceClassifierEvaluation(item, SecretStr(credential),
            gateway_access=_gateway_access(item, environment))
    for item in config.rerank_evaluators:
        if item.binding_id in evaluators:
            raise ValueError("duplicate_evaluator_binding")
        credential = environment.get(item.credential_env)
        if not credential:
            raise ValueError("evaluator_credential_missing")
        evaluators[item.binding_id] = InferenceRerankEvaluation(item, SecretStr(credential),
            gateway_access=_gateway_access(item, environment))
    manager = ExecutionManager(EnhancementEngine(consumers, evaluators), enabled=enabled,
        max_active=config.max_active, max_retained=config.max_retained)
    return create_app(manager, api_token=environment.get("ENHANCEMENT_API_TOKEN", ""))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the bounded synthetic enhancement core")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--synthetic-benchmark", action="store_true")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("port_invalid")
    try:
        config = CoreConfiguration.model_validate_json(args.config.read_bytes()) if args.config else CoreConfiguration()
        app = compose(config, enabled=args.synthetic_benchmark, environment=os.environ)
    except Exception:
        parser.error("core_configuration_invalid")
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
