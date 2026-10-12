"""Only fictional protocol examples; never load user/session configuration."""
import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from prompt_enhancer.enhancement.contracts import (
    Capabilities, ExecuteRequest, ExecutionResult, GenerationContext, Metric, Progress, Readiness,
)

ROOT = Path(__file__).resolve().parents[1] / "contracts" / "enhancement"


@pytest.mark.parametrize("model,name", [
    (ExecuteRequest, "execute-request"), (ExecutionResult, "execution-result"),
    (Progress, "progress"), (Readiness, "readiness"), (Capabilities, "capabilities"),
    (GenerationContext, "generation-context"),
])
def test_exported_schema_matches_code(model, name):
    assert json.loads((ROOT / f"{name}.schema.json").read_text()) == model.model_json_schema()


@pytest.mark.parametrize("filename,model,schema", [
    ("script-request", ExecuteRequest, "execute-request"),
    ("consumer-request", ExecuteRequest, "execute-request"),
    ("result", ExecutionResult, "execution-result"),
    ("generation-context", GenerationContext, "generation-context"),
])
def test_fictional_fixture_validates(filename, model, schema):
    payload = json.loads((ROOT / "examples" / f"{filename}.json").read_text())
    model.model_validate(payload)
    jsonschema.validate(payload, json.loads((ROOT / f"{schema}.schema.json").read_text()))


@pytest.mark.parametrize("mutation", [
    {"protocol_version": "enhancement.v2"}, {"strategy": "shell"},
    {"data_policy": "private_session"}, {"extra": "forbidden"},
    {"parameters": {"timeout_seconds": 0}},
    {"parameters": {"generation": {"temperature": float("nan")}}},
    {"subject": {"text": "\ud800"}},
    {"subject": {"text": "fictional", "context": [{"role": "user", "content": "\ud800"}]}},
    {"consumer": {"binding_id": "example", "provider": "inference"}},
])
def test_unsupported_values_rejected(mutation):
    payload = json.loads((ROOT / "examples" / "script-request.json").read_text())
    payload.update(mutation)
    with pytest.raises(ValidationError):
        ExecuteRequest.model_validate(payload)


def test_unknown_is_not_zero():
    with pytest.raises(ValidationError):
        Metric(key="example", state="unknown", value=0, reason="unavailable")


def test_evaluator_kind_requires_its_own_parameters():
    payload = json.loads((ROOT / "examples" / "script-request.json").read_text())
    payload["evaluation"]["evaluators"][0]["kind"] = "embedding"
    with pytest.raises(ValidationError):
        ExecuteRequest.model_validate(payload)
