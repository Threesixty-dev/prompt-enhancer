from __future__ import annotations

from io import BytesIO, TextIOWrapper
import importlib.util
import json
from pathlib import Path

import pytest

from prompt_enhancer.infrastructure.text_models.model_ensemble import (
    MODEL_ENSEMBLE_RUNNER_SCHEMA_VERSION,
    ModelEnsembleError,
)


def _expert_module():  # type: ignore[no-untyped-def]
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_local_model_ensemble_expert.py"
    )
    spec = importlib.util.spec_from_file_location(
        "synthetic_local_model_ensemble_expert",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload() -> dict[str, object]:
    identifier = "1" * 64
    return {
        "schema_version": MODEL_ENSEMBLE_RUNNER_SCHEMA_VERSION,
        "fragments": [
            {
                "fragment_id": identifier,
                "text": "Fictional request with a bounded acceptance check.",
                "role": "user",
                "kind": "request",
                "language": "en",
                "is_focus_message": True,
            }
        ],
        "cases": [
            {
                "case_id": "2" * 64,
                "chunk_ordinal": 0,
                "metric_key": "prompt.task_definition_coverage",
                "candidate_ids": [identifier],
                "query": "Find task-definition evidence.",
                "hypothesis": "The focus request defines the task.",
                "rubric": "Assess only the focus request.",
            }
        ],
    }


def _install_stdin(module, payload: dict[str, object]) -> None:  # type: ignore[no-untyped-def]
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    module.sys.stdin = TextIOWrapper(BytesIO(encoded), encoding="utf-8")


def test_child_contract_preserves_scope_metadata_in_ephemeral_evidence() -> None:
    module = _expert_module()
    _install_stdin(module, _payload())

    fragments, cases = module._read_payload()
    evidence = module._evidence_text(fragments["1" * 64])

    assert len(cases) == 1
    assert evidence.startswith("[role=user kind=request language=en focus=yes]\n")
    assert "Fictional request" in evidence


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("role", "system"),
        ("kind", "tool_output"),
        ("language", "secret-language"),
        ("is_focus_message", "true"),
    ),
)
def test_child_contract_rejects_unallowlisted_scope_metadata(
    field: str,
    value: object,
) -> None:
    module = _expert_module()
    payload = _payload()
    fragments = payload["fragments"]
    assert isinstance(fragments, list) and isinstance(fragments[0], dict)
    fragments[0][field] = value
    _install_stdin(module, payload)

    with pytest.raises(ModelEnsembleError):
        module._read_payload()
