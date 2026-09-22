"""Independent acceptance boundary for observed objective check completion.

These tests deliberately keep the command and provider result synthetic and
process-local.  The existing command classifier remains a candidate detector;
this module verifies that objective authority additionally requires one exact
terminal execution receipt.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr, ValidationError

from prompt_enhancer.application.analysis.provider_evidence import (
    _verification_outcome,
)
from prompt_enhancer.application.analysis.evidence_contracts import (
    VerificationOutcome,
)
from prompt_enhancer.application.verification import (
    OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION,
    OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION,
    EphemeralObservedCheckCompletion,
    EphemeralVerificationCandidate,
    ObservedCheckOutcome,
    VerificationExecutionState,
    interpret_observed_check_completion,
)
from prompt_enhancer.domain import EventKind, EventTimeBasis, Provider, SafeEvent
from prompt_enhancer.infrastructure.verification import (
    DeterministicCommandVerificationClassifier,
)


CLASSIFIER = DeterministicCommandVerificationClassifier()
SOURCE_ID = "a" * 64
SESSION_ID = "b" * 64
EVENT_ID = "c" * 64
NOW = datetime(2026, 9, 8, tzinfo=UTC)


def _candidate(
    command: str = "pytest -q",
    *,
    execution_state: VerificationExecutionState = VerificationExecutionState.UNKNOWN,
    exit_code: int | None = None,
    observed_sequence: int | None = 1,
) -> EphemeralVerificationCandidate:
    return EphemeralVerificationCandidate(
        provider=Provider.SYNTHETIC,
        source_item_id=SecretStr(SOURCE_ID),
        command=SecretStr(command),
        candidate_schema_version="ephemeral-command-v1",
        execution_state=execution_state,
        exit_code=exit_code,
        observed_sequence=observed_sequence,
    )


def _completion() -> EphemeralObservedCheckCompletion:
    result = interpret_observed_check_completion(
        candidate=_candidate(
            execution_state=VerificationExecutionState.COMPLETED,
            exit_code=0,
        ),
        provider_execution_status="completed",
        classifier=CLASSIFIER,
    )
    assert result is not None
    return result


@pytest.mark.parametrize(
    ("exit_code", "expected"),
    ((0, ObservedCheckOutcome.PASSED), (1, ObservedCheckOutcome.CHECK_FAILED)),
)
def test_exact_completed_pytest_receipt_is_issued_for_only_binary_exit_codes(
    exit_code: int,
    expected: ObservedCheckOutcome,
) -> None:
    result = interpret_observed_check_completion(
        candidate=_candidate(
            execution_state=VerificationExecutionState.COMPLETED,
            exit_code=exit_code,
        ),
        provider_execution_status="completed",
        classifier=CLASSIFIER,
    )

    assert result is not None
    assert result.outcome is expected
    assert result.exit_code == exit_code
    assert result.provider_execution_status == "completed"
    assert result.source_reference_id == SOURCE_ID


@pytest.mark.parametrize("exit_code", (True, False, 0.0, 1.0, 0.5, "0"))
def test_non_strict_or_fractional_exit_codes_cannot_enter_completion_contract(
    exit_code: object,
) -> None:
    with pytest.raises(ValidationError):
        _candidate(
            execution_state=VerificationExecutionState.COMPLETED,
            exit_code=exit_code,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("exit_code", (None, -1, 2, 3, 4, 5, 127))
def test_missing_or_non_binary_pytest_exit_codes_are_not_check_outcomes(
    exit_code: int | None,
) -> None:
    result = interpret_observed_check_completion(
        candidate=_candidate(
            execution_state=VerificationExecutionState.COMPLETED,
            exit_code=exit_code,
        )
        if exit_code is not None
        else _candidate(
            execution_state=VerificationExecutionState.COMPLETED,
            exit_code=None,
        ),
        provider_execution_status="completed",
        classifier=CLASSIFIER,
    )

    assert result is None


def test_missing_observed_sequence_cannot_enter_completion_contract() -> None:
    result = interpret_observed_check_completion(
        candidate=_candidate(
            execution_state=VerificationExecutionState.COMPLETED,
            exit_code=0,
            observed_sequence=None,
        ),
        provider_execution_status="completed",
        classifier=CLASSIFIER,
    )

    assert result is None


@pytest.mark.parametrize("status", ("running", "pending", "failed", "error", "unknown"))
def test_non_terminal_or_contradictory_provider_status_never_issues_receipt(
    status: str,
) -> None:
    result = interpret_observed_check_completion(
        candidate=_candidate(
            execution_state=VerificationExecutionState.COMPLETED,
            exit_code=0,
        ),
        provider_execution_status=status,
        classifier=CLASSIFIER,
    )

    assert result is None


@pytest.mark.parametrize(
    ("state", "candidate_exit", "expected_eligible"),
    (
        (VerificationExecutionState.FAILED, 1, False),
        (VerificationExecutionState.COMPLETED, 0, True),
        (VerificationExecutionState.INTERRUPTED, None, False),
        (VerificationExecutionState.COMPLETED, 2, False),
    ),
)
def test_candidate_execution_facts_must_agree_with_its_observed_completion(
    state: VerificationExecutionState,
    candidate_exit: int | None,
    expected_eligible: bool,
) -> None:
    result = interpret_observed_check_completion(
        candidate=_candidate(
            execution_state=state,
            exit_code=candidate_exit,
        ),
        provider_execution_status="completed",
        classifier=CLASSIFIER,
    )

    assert (result is not None) is expected_eligible


@pytest.mark.parametrize(
    "command",
    (
        "pytest --collect-only",
        "pytest --help",
        "pytest --dry-run",
        "pytest --version",
        "pytest --watch",
        "pytest && echo done",
        "python -m pytest && pytest",
        "make test",
        "cargo test --workspace",
        "npm test",
        "unknown-checker --pass",
    ),
)
def test_non_evaluating_compound_or_non_exact_commands_do_not_issue_receipt(
    command: str,
) -> None:
    result = interpret_observed_check_completion(
        candidate=_candidate(
            command,
            execution_state=VerificationExecutionState.COMPLETED,
            exit_code=0,
        ),
        provider_execution_status="completed",
        classifier=CLASSIFIER,
    )

    assert result is None


@pytest.mark.parametrize(
    "field",
    (
        "source_completion_schema_version",
        "outcome_interpreter_version",
        "classifier_version",
        "normalizer_version",
    ),
)
def test_completion_provenance_cannot_be_replaced_by_an_arbitrary_safe_version(
    field: str,
) -> None:
    payload = _completion().model_dump()
    payload[field] = "synthetic-alternate-v9"

    with pytest.raises(ValidationError):
        EphemeralObservedCheckCompletion.model_validate(payload)


@pytest.mark.parametrize("exit_code", (-1, 2, 5))
def test_completion_dto_rejects_exit_codes_without_defined_pytest_outcome(
    exit_code: int,
) -> None:
    payload = _completion().model_dump()
    payload["exit_code"] = exit_code
    payload["outcome"] = ObservedCheckOutcome.CHECK_FAILED

    with pytest.raises(ValidationError):
        EphemeralObservedCheckCompletion.model_validate(payload)


@pytest.mark.parametrize("exit_code", (True, False, 0.5, "0"))
def test_completion_dto_requires_a_strict_integer_exit_code(exit_code: object) -> None:
    payload = _completion().model_dump()
    payload["exit_code"] = exit_code

    with pytest.raises(ValidationError):
        EphemeralObservedCheckCompletion.model_validate(payload)


def test_generic_safe_event_verification_outcome_remains_separate_and_unchanged() -> None:
    passed = SafeEvent(
        session_id=SESSION_ID,
        event_id=EVENT_ID,
        kind=EventKind.VERIFICATION,
        sequence=1,
        occurred_at=NOW,
        time_basis=EventTimeBasis.PROVIDER_REPORTED,
        success=True,
    )
    failed = passed.model_copy(update={"event_id": "d" * 64, "success": False})

    assert _verification_outcome(passed) is VerificationOutcome.PASSED
    assert _verification_outcome(failed) is VerificationOutcome.FAILED


def test_completion_is_content_free_and_process_local() -> None:
    completion = _completion()

    assert completion.local_only is True
    assert completion.content_persistence_allowed is False
    assert set(completion.model_dump()) == {
        "provider",
        "source_reference_id",
        "observed_sequence",
        "check_kind",
        "outcome",
        "provider_execution_status",
        "exit_code",
        "source_completion_schema_version",
        "outcome_interpreter_version",
        "classifier_version",
        "normalizer_version",
        "rule_id",
        "local_only",
        "content_persistence_allowed",
    }
    assert completion.source_completion_schema_version == (
        OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION
    )
    assert completion.outcome_interpreter_version == (
        OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION
    )
