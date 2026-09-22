"""Contract-only validation tests for revision-bound generation settings."""

from typing import Any

import pytest
from pydantic import ValidationError

from src.prompt_enhancer.application.local_agent import (
    AgentModelParameters,
    UpdateAgentSessionParameters,
)


PROJECT_ID = "b" * 32
PARAMETERS = {
    "temperature": 0.2,
    "top_p": 0.95,
    "max_tokens": 1400,
    "enable_thinking": False,
}


def request(**overrides: Any) -> dict[str, Any]:
    value = {
        "expected_project_id": PROJECT_ID,
        "expected_revision": 4,
        "expected_parameters": PARAMETERS.copy(),
        "parameters": PARAMETERS.copy(),
    }
    value.update(overrides)
    return value


def test_complete_revision_bound_request_is_valid() -> None:
    parsed = UpdateAgentSessionParameters.model_validate(request())
    assert parsed.expected_project_id == PROJECT_ID
    assert parsed.expected_revision == 4
    assert parsed.expected_parameters.max_tokens == 1400
    assert parsed.parameters.top_p == 0.95


@pytest.mark.parametrize("field", ["workspace", "model_alias", "allow_writes", "instructions", "retention_policy"])
def test_forbidden_top_level_fields_are_rejected_independently(field: str) -> None:
    with pytest.raises(ValidationError):
        UpdateAgentSessionParameters.model_validate(request(**{field: "synthetic"}))


def test_extra_nested_parameter_is_rejected() -> None:
    nested = PARAMETERS | {"workspace": "synthetic"}
    with pytest.raises(ValidationError):
        UpdateAgentSessionParameters.model_validate(request(parameters=nested))


@pytest.mark.parametrize("temperature", [-0.01, 2.01, float("nan"), float("inf"), float("-inf")])
def test_temperature_bounds_and_finite_values_are_enforced(temperature: float) -> None:
    with pytest.raises(ValidationError):
        UpdateAgentSessionParameters.model_validate(request(parameters=PARAMETERS | {"temperature": temperature}))


@pytest.mark.parametrize("top_p", [0, 1.01])
def test_top_p_bounds_are_enforced(top_p: float) -> None:
    with pytest.raises(ValidationError):
        UpdateAgentSessionParameters.model_validate(request(parameters=PARAMETERS | {"top_p": top_p}))


@pytest.mark.parametrize("max_tokens", [63, 8193, 1400.5, True])
def test_output_budget_is_strict_and_bounded(max_tokens: object) -> None:
    with pytest.raises(ValidationError):
        UpdateAgentSessionParameters.model_validate(request(parameters=PARAMETERS | {"max_tokens": max_tokens}))


def test_malformed_project_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UpdateAgentSessionParameters.model_validate(request(expected_project_id="synthetic-project"))


def test_malformed_revision_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UpdateAgentSessionParameters.model_validate(request(expected_revision=0))


@pytest.mark.parametrize("max_tokens", [64, 8192])
def test_no_model_compatible_parameter_boundaries_are_valid(max_tokens: int) -> None:
    parsed = UpdateAgentSessionParameters.model_validate(
        request(
            expected_parameters={**PARAMETERS, "max_tokens": max_tokens},
            parameters={**PARAMETERS, "max_tokens": max_tokens, "enable_thinking": True},
        )
    )
    assert parsed.parameters.max_tokens == max_tokens
    assert parsed.parameters.enable_thinking is True


def test_agent_model_parameters_accepts_no_model_neutral_defaults() -> None:
    parsed = AgentModelParameters.model_validate(PARAMETERS)
    assert parsed.model_dump() == PARAMETERS
