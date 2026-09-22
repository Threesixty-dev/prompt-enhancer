from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from prompt_enhancer.application.verification import (
    EphemeralVerificationCandidate,
    ObservedCheckOutcome,
    VerificationExecutionState,
    interpret_observed_check_completion,
)
from prompt_enhancer.domain import Provider
from prompt_enhancer.infrastructure.verification import (
    CANDIDATE_SCHEMA_VERSION,
    DeterministicCommandVerificationClassifier,
)


def _candidate(
    command: str,
    *,
    exit_code: int | None,
    state: VerificationExecutionState = VerificationExecutionState.COMPLETED,
) -> EphemeralVerificationCandidate:
    return EphemeralVerificationCandidate(
        provider=Provider.CODEX,
        source_item_id=SecretStr("a" * 64),
        observed_sequence=7,
        command=SecretStr(command),
        candidate_schema_version=CANDIDATE_SCHEMA_VERSION,
        execution_state=state,
        exit_code=exit_code,
    )


@pytest.mark.parametrize(
    ("exit_code", "outcome"),
    [(0, ObservedCheckOutcome.PASSED), (1, ObservedCheckOutcome.CHECK_FAILED)],
)
def test_direct_pytest_completed_exit_has_documented_observed_outcome(
    exit_code: int,
    outcome: ObservedCheckOutcome,
) -> None:
    completion = interpret_observed_check_completion(
        candidate=_candidate("pytest -q", exit_code=exit_code),
        provider_execution_status="completed",
        classifier=DeterministicCommandVerificationClassifier(),
    )

    assert completion is not None
    assert completion.outcome is outcome
    assert completion.exit_code == exit_code
    assert completion.provider_execution_status == "completed"


@pytest.mark.parametrize("exit_code", [None, 2, 3, 4, 5])
def test_non_evaluable_pytest_exit_codes_do_not_claim_an_observed_outcome(
    exit_code: int | None,
) -> None:
    assert (
        interpret_observed_check_completion(
            candidate=_candidate("pytest -q", exit_code=exit_code),
            provider_execution_status="completed",
            classifier=DeterministicCommandVerificationClassifier(),
        )
        is None
    )


@pytest.mark.parametrize(
    "command",
    [
        "pytest --collect-only",
        "python -m pytest",
        "npm test",
        "pytest -q && echo done",
    ],
)
def test_unsupported_or_ambiguous_commands_do_not_claim_an_observed_outcome(
    command: str,
) -> None:
    assert (
        interpret_observed_check_completion(
            candidate=_candidate(command, exit_code=0),
            provider_execution_status="completed",
            classifier=DeterministicCommandVerificationClassifier(),
        )
        is None
    )


def test_nonterminal_status_and_unknown_execution_do_not_claim_an_outcome() -> None:
    candidate = _candidate(
        "pytest -q",
        exit_code=0,
        state=VerificationExecutionState.UNKNOWN,
    )
    assert (
        interpret_observed_check_completion(
            candidate=candidate,
            provider_execution_status="running",
            classifier=DeterministicCommandVerificationClassifier(),
        )
        is None
    )


@pytest.mark.parametrize("invalid_exit", [False, "0", 0.0])
def test_exit_authority_rejects_coerced_scalars(invalid_exit: object) -> None:
    with pytest.raises(ValidationError):
        _candidate("pytest -q", exit_code=invalid_exit)  # type: ignore[arg-type]
