"""Append-only persistence contracts for requirement-verification evidence.

This application boundary persists only keyed, content-free identities.  The
native-reviewed r6 requirement snapshot remains the denominator authority;
assistant claims, requirement-action completion, and provider prose have no
input type here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
import hmac
from typing import Callable, Literal, Protocol, TYPE_CHECKING

from pydantic import Field, field_validator, model_validator

from ...domain import PSEUDONYM_PATTERN, SAFE_VERSION_PATTERN, StrictModel
from .requirement_plan_evidence import (
    MAX_REQUIREMENT_PLAN_UNITS,
    RequirementPlanEvidenceSnapshot,
)
from .requirement_verification_evidence import (
    AppIssuedRequirementVerificationOpportunitySet,
    AppIssuedRequirementVerificationResult,
    ExplicitRequirementAcceptanceAuthority,
    RequirementAcceptanceOutcome,
    RequirementVerificationEvidenceSet,
    RequirementVerificationIdFactory,
    RequirementVerificationMethod,
    RequirementVerificationOutcome,
    issue_explicit_requirement_acceptance,
    issue_requirement_verification_result,
    issue_requirement_verification_opportunities,
    validate_requirement_verification_opportunities,
    validate_requirement_verification_result,
)
if TYPE_CHECKING:
    from .requirement_verification_review import RequirementVerificationReviewService


REQUIREMENT_VERIFICATION_PERSISTENCE_SCHEMA_VERSION = (
    "requirement-verification-persistence-v1"
)
REQUIREMENT_ACCEPTANCE_APPEND_CONFIRMATION = (
    "record_explicit_native_requirement_acceptance"
)
OBSERVED_CHECK_RESULT_ISSUE_CONFIRMATION = (
    "issue_exact_local_requirement_observed_check_result"
)
OBSERVED_CHECK_COVERAGE_REVIEW_VERSION = "native-full-criterion-coverage-v1"
OBSERVED_CHECK_PROVENANCE_SCHEMA_VERSION = "observed-check-authority-provenance-v1"
MAX_REQUIREMENT_VERIFICATION_HISTORY_PER_OPPORTUNITY = 32
MAX_REQUIREMENT_VERIFICATION_REVISIONS = (
    MAX_REQUIREMENT_PLAN_UNITS
    * MAX_REQUIREMENT_VERIFICATION_HISTORY_PER_OPPORTUNITY
)
MIN_REQUIREMENT_VERIFICATION_IDEMPOTENCY_KEY_LENGTH = 16
MAX_REQUIREMENT_VERIFICATION_IDEMPOTENCY_KEY_LENGTH = 128


def _pseudonym(value: str) -> str:
    if PSEUDONYM_PATTERN.fullmatch(value) is None:
        raise ValueError("requirement-verification identifiers must be pseudonyms")
    return value


def _optional_pseudonym(value: str | None) -> str | None:
    return None if value is None else _pseudonym(value)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("requirement-verification timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _idempotency_key(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) < MIN_REQUIREMENT_VERIFICATION_IDEMPOTENCY_KEY_LENGTH
        or len(value) > MAX_REQUIREMENT_VERIFICATION_IDEMPOTENCY_KEY_LENGTH
        or SAFE_VERSION_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("requirement-verification idempotency key is invalid")
    return value


class RequirementVerificationAuthorityRecordKind(StrEnum):
    OBJECTIVE_RESULT = "objective_result"
    NATIVE_ACCEPTANCE = "native_acceptance"


class RequirementVerificationOpportunitySetRecord(StrictModel):
    opportunities: AppIssuedRequirementVerificationOpportunitySet
    issued_at: datetime
    persistence_schema_version: Literal[
        REQUIREMENT_VERIFICATION_PERSISTENCE_SCHEMA_VERSION
    ] = REQUIREMENT_VERIFICATION_PERSISTENCE_SCHEMA_VERSION
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False

    _issued = field_validator("issued_at")(_utc)


class RequirementVerificationResultAppendCommand(StrictModel):
    result: AppIssuedRequirementVerificationResult
    expected_predecessor_authority_id: str | None = None

    _predecessor = field_validator("expected_predecessor_authority_id")(
        _optional_pseudonym
    )


class RequirementAcceptanceAppendCommand(StrictModel):
    opportunity_set_fingerprint: str
    opportunity_id: str
    expected_predecessor_authority_id: str | None = None
    outcome: RequirementAcceptanceOutcome
    confirmation: Literal[REQUIREMENT_ACCEPTANCE_APPEND_CONFIRMATION]
    # Required by the production composition. Nullable wire fields preserve
    # isolated content-free command/replay compatibility; composed acceptance
    # still fails closed unless the ephemeral review service consumes them.
    review_receipt_id: str | None = None
    review_fingerprint: str | None = None
    expected_source_run_id: str | None = None
    source_window_fingerprint: str | None = None

    _ids = field_validator("opportunity_set_fingerprint", "opportunity_id")(
        _pseudonym
    )
    _predecessor = field_validator("expected_predecessor_authority_id")(
        _optional_pseudonym
    )
    _review_ids = field_validator(
        "review_receipt_id", "review_fingerprint", "expected_source_run_id",
        "source_window_fingerprint",
    )(_optional_pseudonym)


class ObservedCheckResultIssueCommand(StrictModel):
    """Native issue command with no client-controlled outcome authority."""

    opportunity_set_fingerprint: str
    opportunity_id: str
    candidate_id: str
    expected_source_run_id: str
    source_window_fingerprint: str
    through_revision: int = Field(ge=0, le=MAX_REQUIREMENT_VERIFICATION_REVISIONS)
    expected_predecessor_authority_id: str | None = None
    candidate_manifest_fingerprint: str
    review_receipt_id: str
    review_fingerprint: str
    full_criterion_coverage_acknowledged: Literal[True]
    confirmation: Literal[OBSERVED_CHECK_RESULT_ISSUE_CONFIRMATION]

    _ids = field_validator(
        "opportunity_set_fingerprint", "opportunity_id", "candidate_id",
        "expected_source_run_id", "source_window_fingerprint",
        "candidate_manifest_fingerprint", "review_receipt_id", "review_fingerprint",
    )(_pseudonym)
    _predecessor = field_validator("expected_predecessor_authority_id")(
        _optional_pseudonym
    )


class ObservedCheckAuthorityProvenance(StrictModel):
    """Restart-readable, content-free distinction for a CP34 observed result."""

    authority_record_id: str
    session_id: str
    opportunity_set_fingerprint: str
    opportunity_id: str
    requirement_id: str
    source_run_id: str
    source_window_fingerprint: str
    requirement_plan_confirmation_id: str
    requirement_plan_proposal_id: str
    candidate_manifest_fingerprint: str
    source_reference_id: str
    coverage_review_reference_id: str
    observed_sequence: int = Field(ge=0, le=4_000_000_000)
    check_kind: Literal["test"] = "test"
    provider_execution_status: Literal["completed"] = "completed"
    observed_outcome: Literal["passed", "check_failed"]
    exit_code: Literal[0, 1]
    source_completion_schema_version: Literal["observed-check-completion-v1"]
    outcome_interpreter_version: Literal["pytest-exit-status-v1"]
    classifier_version: Literal["local-command-rules-v1"]
    normalizer_version: Literal["strict-shell-free-v2"]
    rule_id: Literal["test.pytest", "test.py_test"]
    coverage_review_version: Literal[OBSERVED_CHECK_COVERAGE_REVIEW_VERSION]
    full_criterion_coverage_acknowledged: Literal[True]
    provenance_fingerprint: str
    schema_version: Literal[OBSERVED_CHECK_PROVENANCE_SCHEMA_VERSION] = (
        OBSERVED_CHECK_PROVENANCE_SCHEMA_VERSION
    )
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False

    _ids = field_validator(
        "authority_record_id", "session_id", "opportunity_set_fingerprint",
        "opportunity_id", "requirement_id", "source_run_id",
        "source_window_fingerprint", "requirement_plan_confirmation_id",
        "requirement_plan_proposal_id", "candidate_manifest_fingerprint",
        "source_reference_id", "coverage_review_reference_id",
        "provenance_fingerprint",
    )(_pseudonym)

    @field_validator("observed_sequence", "exit_code", mode="before")
    @classmethod
    def exact_integer_fields(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("observed-check numeric provenance must be an integer")
        return value

    @model_validator(mode="after")
    def exact_outcome_partition(self) -> "ObservedCheckAuthorityProvenance":
        if (self.observed_outcome == "passed") != (self.exit_code == 0):
            raise ValueError("observed-check outcome disagrees with its exit code")
        return self


class RequirementVerificationAuthorityDraft(StrictModel):
    authority_record_id: str
    session_id: str
    opportunity_set_fingerprint: str
    opportunity_id: str
    requirement_id: str
    expected_predecessor_authority_id: str | None = None
    kind: RequirementVerificationAuthorityRecordKind
    idempotency_key_digest: str
    command_fingerprint: str
    recorded_at: datetime
    result: AppIssuedRequirementVerificationResult | None = None
    acceptance: ExplicitRequirementAcceptanceAuthority | None = None
    persistence_schema_version: Literal[
        REQUIREMENT_VERIFICATION_PERSISTENCE_SCHEMA_VERSION
    ] = REQUIREMENT_VERIFICATION_PERSISTENCE_SCHEMA_VERSION
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False

    _ids = field_validator(
        "authority_record_id",
        "session_id",
        "opportunity_set_fingerprint",
        "opportunity_id",
        "requirement_id",
        "idempotency_key_digest",
        "command_fingerprint",
    )(_pseudonym)
    _predecessor = field_validator("expected_predecessor_authority_id")(
        _optional_pseudonym
    )
    _recorded = field_validator("recorded_at")(_utc)

    @model_validator(mode="after")
    def exact_authority_partition(self) -> "RequirementVerificationAuthorityDraft":
        authority = self.result if self.result is not None else self.acceptance
        if (
            (self.kind is RequirementVerificationAuthorityRecordKind.OBJECTIVE_RESULT)
            != (self.result is not None and self.acceptance is None)
        ):
            raise ValueError("objective authority record has an invalid partition")
        if (
            (self.kind is RequirementVerificationAuthorityRecordKind.NATIVE_ACCEPTANCE)
            != (self.acceptance is not None and self.result is None)
        ):
            raise ValueError("acceptance authority record has an invalid partition")
        if authority is None:
            raise ValueError("authority record is empty")
        expected_record_id = (
            authority.result_id
            if isinstance(authority, AppIssuedRequirementVerificationResult)
            else authority.acceptance_id
        )
        if (
            self.authority_record_id != expected_record_id
            or self.opportunity_set_fingerprint
            != authority.opportunity_set_fingerprint
            or self.opportunity_id != authority.opportunity_id
            or self.requirement_id != authority.requirement_id
        ):
            raise ValueError("authority record identifiers disagree")
        return self


class RequirementVerificationAuthorityRecord(RequirementVerificationAuthorityDraft):
    revision: int = Field(ge=1, le=MAX_REQUIREMENT_VERIFICATION_REVISIONS)


class RequirementVerificationAuthorityHead(StrictModel):
    opportunity_id: str
    authority_record_id: str
    kind: RequirementVerificationAuthorityRecordKind
    revision: int = Field(ge=1, le=MAX_REQUIREMENT_VERIFICATION_REVISIONS)

    _ids = field_validator("opportunity_id", "authority_record_id")(_pseudonym)


class RequirementVerificationEvidenceSnapshot(StrictModel):
    evidence: RequirementVerificationEvidenceSet
    revision: int = Field(ge=0, le=MAX_REQUIREMENT_VERIFICATION_REVISIONS)
    authority_heads: tuple[RequirementVerificationAuthorityHead, ...] = Field(
        default=(), max_length=MAX_REQUIREMENT_PLAN_UNITS
    )
    persistence_schema_version: Literal[
        REQUIREMENT_VERIFICATION_PERSISTENCE_SCHEMA_VERSION
    ] = REQUIREMENT_VERIFICATION_PERSISTENCE_SCHEMA_VERSION
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False

    @model_validator(mode="after")
    def exact_heads(self) -> "RequirementVerificationEvidenceSnapshot":
        opportunity_ids = tuple(item.opportunity_id for item in self.authority_heads)
        if opportunity_ids != tuple(sorted(set(opportunity_ids))):
            raise ValueError("authority heads must be unique and sorted")
        expected: dict[str, tuple[str, RequirementVerificationAuthorityRecordKind]] = {
            item.opportunity_id: (
                item.result_id,
                RequirementVerificationAuthorityRecordKind.OBJECTIVE_RESULT,
            )
            for item in self.evidence.verification_results
        }
        expected.update(
            {
                item.opportunity_id: (
                    item.acceptance_id,
                    RequirementVerificationAuthorityRecordKind.NATIVE_ACCEPTANCE,
                )
                for item in self.evidence.acceptance_authorities
            }
        )
        actual = {
            item.opportunity_id: (item.authority_record_id, item.kind)
            for item in self.authority_heads
        }
        if actual != expected:
            raise ValueError("authority heads disagree with evidence authorities")
        if any(item.revision > self.revision for item in self.authority_heads):
            raise ValueError("authority head exceeds the snapshot revision")
        return self


class RequirementVerificationRepository(Protocol):
    def issue_opportunity_set(
        self, record: RequirementVerificationOpportunitySetRecord
    ) -> tuple[RequirementVerificationEvidenceSnapshot, bool]: ...

    def get_opportunity_set(
        self, opportunity_set_fingerprint: str
    ) -> RequirementVerificationOpportunitySetRecord | None: ...

    def find_replay(
        self, session_id: str, idempotency_key_digest: str
    ) -> RequirementVerificationAuthorityRecord | None: ...

    def append_authority(
        self, draft: RequirementVerificationAuthorityDraft
    ) -> tuple[RequirementVerificationEvidenceSnapshot, bool]: ...

    def append_observed_authority(
        self,
        draft: RequirementVerificationAuthorityDraft,
        provenance: ObservedCheckAuthorityProvenance,
    ) -> tuple[RequirementVerificationEvidenceSnapshot, bool]: ...

    def get_observed_check_provenance(
        self, session_id: str, authority_record_id: str
    ) -> ObservedCheckAuthorityProvenance | None: ...

    def snapshot(
        self,
        session_id: str,
        opportunity_set_fingerprint: str,
        *,
        through_revision: int | None = None,
    ) -> RequirementVerificationEvidenceSnapshot | None: ...


class CurrentRequirementVerificationEvidenceReader(Protocol):
    """Read-only current M58 authority for one exact reviewed r6 plan."""

    def snapshot_for_requirement_plan(
        self,
        session_id: str,
        requirement_plan_confirmation_id: str,
    ) -> RequirementVerificationEvidenceSnapshot | None: ...


class CurrentRequirementPlanAuthority(Protocol):
    def current_snapshot(self, session_id: str) -> RequirementPlanEvidenceSnapshot: ...


class RequirementPlanEvidenceSnapshotRepository(Protocol):
    def snapshot(
        self, session_id: str, source_window_fingerprint: str
    ) -> RequirementPlanEvidenceSnapshot: ...


class CurrentRequirementPlanSourceWindowAuthority(Protocol):
    def current_source_window(self, session_id: str) -> str: ...


class CurrentRequirementPlanSnapshotAuthority:
    """Resolve r6 through a durable, content-free current-window authority."""

    def __init__(
        self,
        repository: RequirementPlanEvidenceSnapshotRepository,
        source_windows: CurrentRequirementPlanSourceWindowAuthority,
    ) -> None:
        self._repository = repository
        self._source_windows = source_windows

    def current_snapshot(self, session_id: str) -> RequirementPlanEvidenceSnapshot:
        source_window_fingerprint = self._source_windows.current_source_window(
            session_id
        )
        _pseudonym(source_window_fingerprint)
        snapshot = self._repository.snapshot(
            session_id, source_window_fingerprint
        )
        if (
            snapshot.session_id != session_id
            or snapshot.source_window_fingerprint != source_window_fingerprint
        ):
            raise ValueError("current requirement-plan authority changed")
        return snapshot


class RequirementVerificationEvidenceError(RuntimeError):
    code = "requirement_verification_evidence_failed"


class RequirementVerificationInputError(RequirementVerificationEvidenceError):
    code = "invalid_requirement_verification_evidence"


class RequirementVerificationDefinitionsOutOfDateError(
    RequirementVerificationInputError
):
    code = "requirement_verification_evidence_definitions_out_of_date"


class RequirementVerificationNotFoundError(RequirementVerificationEvidenceError):
    code = "requirement_verification_evidence_not_found"


class RequirementVerificationStaleWindowError(RequirementVerificationEvidenceError):
    code = "requirement_verification_source_window_stale"


class RequirementVerificationConflictError(RequirementVerificationEvidenceError):
    code = "requirement_verification_evidence_conflict"


class RequirementVerificationPersistenceError(RequirementVerificationEvidenceError):
    code = "requirement_verification_evidence_persistence_failed"


class RequirementVerificationEvidenceService:
    """Issue, append, and replay durable content-free verification authority."""

    def __init__(
        self,
        repository: RequirementVerificationRepository,
        plan_authority: CurrentRequirementPlanAuthority,
        identifiers: RequirementVerificationIdFactory,
        *,
        review_service: "RequirementVerificationReviewService | None" = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._plan_authority = plan_authority
        self._identifiers = identifiers
        self._review_service = review_service
        self._clock = clock

    @property
    def review_service(self) -> "RequirementVerificationReviewService | None":
        return self._review_service

    def issue_current_opportunities(
        self, session_id: str
    ) -> tuple[RequirementVerificationEvidenceSnapshot, bool]:
        self._validate_session_id(session_id)
        snapshot = self._current_plan(session_id)
        try:
            opportunities = issue_requirement_verification_opportunities(
                snapshot, self._identifiers
            )
            record = RequirementVerificationOpportunitySetRecord(
                opportunities=opportunities,
                issued_at=_utc(self._clock()),
            )
            return self._repository.issue_opportunity_set(record)
        except RequirementVerificationEvidenceError:
            raise
        except ValueError:
            raise RequirementVerificationInputError(
                "current reviewed requirements cannot issue opportunities"
            ) from None
        except Exception:
            raise RequirementVerificationPersistenceError(
                "requirement-verification opportunities could not be persisted"
            ) from None

    def snapshot(
        self,
        session_id: str,
        opportunity_set_fingerprint: str,
        *,
        through_revision: int | None = None,
    ) -> RequirementVerificationEvidenceSnapshot:
        self._validate_session_id(session_id)
        try:
            _pseudonym(opportunity_set_fingerprint)
            if through_revision is not None and not (
                0 <= through_revision <= MAX_REQUIREMENT_VERIFICATION_REVISIONS
            ):
                raise ValueError("snapshot revision is outside its bound")
            result = self._repository.snapshot(
                session_id,
                opportunity_set_fingerprint,
                through_revision=through_revision,
            )
        except RequirementVerificationEvidenceError:
            raise
        except (TypeError, ValueError):
            raise RequirementVerificationInputError(
                "requirement-verification snapshot identity is invalid"
            ) from None
        except Exception:
            raise RequirementVerificationPersistenceError(
                "requirement-verification snapshot could not be read"
            ) from None
        if result is None:
            raise RequirementVerificationNotFoundError(
                "requirement-verification snapshot was not found"
            )
        return result

    def observed_check_provenance(
        self, session_id: str, authority_record_id: str
    ) -> ObservedCheckAuthorityProvenance:
        self._validate_session_id(session_id)
        try:
            _pseudonym(authority_record_id)
            result = self._repository.get_observed_check_provenance(
                session_id, authority_record_id
            )
        except RequirementVerificationEvidenceError:
            raise
        except (TypeError, ValueError):
            raise RequirementVerificationInputError(
                "observed-check provenance identity is invalid"
            ) from None
        except Exception:
            raise RequirementVerificationPersistenceError(
                "observed-check provenance could not be read"
            ) from None
        if result is None:
            raise RequirementVerificationNotFoundError(
                "observed-check provenance was not found"
            )
        return result

    def append_objective_result(
        self,
        *,
        session_id: str,
        command: RequirementVerificationResultAppendCommand,
        idempotency_key: str,
    ) -> tuple[RequirementVerificationEvidenceSnapshot, bool]:
        self._validate_session_id(session_id)
        checked_command = self._parse_result_command(command)
        checked_key = self._validate_idempotency_key(idempotency_key)
        set_record = self._opportunity_set(
            session_id, checked_command.result.opportunity_set_fingerprint
        )
        try:
            result = validate_requirement_verification_result(
                checked_command.result,
                set_record.opportunities,
                self._identifiers,
            )
        except (TypeError, ValueError):
            raise RequirementVerificationInputError(
                "objective result lacks app-issued authority"
            ) from None
        idempotency_digest = self._idempotency_digest(session_id, checked_key)
        command_fingerprint = self._identifiers.fingerprint(
            "requirement-verification-result-append-command-v1",
            (
                session_id,
                result.result_fingerprint,
                checked_command.expected_predecessor_authority_id or "none",
            ),
        )
        draft = RequirementVerificationAuthorityDraft(
            authority_record_id=result.result_id,
            session_id=session_id,
            opportunity_set_fingerprint=result.opportunity_set_fingerprint,
            opportunity_id=result.opportunity_id,
            requirement_id=result.requirement_id,
            expected_predecessor_authority_id=(
                checked_command.expected_predecessor_authority_id
            ),
            kind=RequirementVerificationAuthorityRecordKind.OBJECTIVE_RESULT,
            idempotency_key_digest=idempotency_digest,
            command_fingerprint=command_fingerprint,
            recorded_at=self._now(),
            result=result,
        )
        replay = self._exact_replay(draft)
        if replay is not None:
            return replay, False
        self._require_current_set(set_record)
        return self._append(draft)

    def append_observed_check_result(
        self,
        *,
        session_id: str,
        command: ObservedCheckResultIssueCommand,
        idempotency_key: str,
    ) -> tuple[RequirementVerificationEvidenceSnapshot, bool]:
        """Issue only a server-derived result after native criterion coverage review."""
        self._validate_session_id(session_id)
        checked = self._parse_observed_issue_command(command)
        checked_key = self._validate_idempotency_key(idempotency_key)
        if self._review_service is None:
            raise RequirementVerificationConflictError(
                "fresh exact local requirement review is required"
            )
        try:
            review, already_consumed = self._review_service.preview_observed_check(
                session_id=session_id, command=checked
            )
        except Exception as error:
            raise RequirementVerificationConflictError(
                "fresh exact local requirement review is required"
            ) from error
        set_record = self._opportunity_set(session_id, checked.opportunity_set_fingerprint)
        outcome = (
            RequirementVerificationOutcome.PASSED
            if review.candidate.observed_outcome == "passed"
            else RequirementVerificationOutcome.FAILED
        )
        coverage_reference_id = self._identifiers.fingerprint(
            "requirement-verification-observed-check-coverage-review-v1",
            (
                OBSERVED_CHECK_COVERAGE_REVIEW_VERSION,
                session_id,
                checked.opportunity_set_fingerprint,
                checked.opportunity_id,
                checked.candidate_id,
                str(review.candidate.observed_sequence),
                review.expected_source_run_id,
                review.source_window_fingerprint,
                review.requirement_plan_confirmation_id,
                review.requirement_plan_proposal_id,
                review.candidate_manifest_fingerprint,
                review.review_receipt_id,
                review.review_fingerprint,
                "full-criterion-coverage-acknowledged",
                str(review.through_revision),
                review.expected_predecessor_authority_id or "none",
            ),
        )
        try:
            result = issue_requirement_verification_result(
                set_record.opportunities,
                opportunity_id=checked.opportunity_id,
                observed_sequence=review.candidate.observed_sequence,
                method=RequirementVerificationMethod.TEST,
                outcome=outcome,
                receipt_reference_ids=tuple(sorted((
                    checked.candidate_id, coverage_reference_id,
                ))),
                identifiers=self._identifiers,
            )
        except (TypeError, ValueError):
            raise RequirementVerificationInputError(
                "observed check lacks app-issued authority"
            ) from None
        idempotency_digest = self._idempotency_digest(session_id, checked_key)
        # The append-only store seals all objective results under its existing
        # canonical result command identity.  The observed-review semantics are
        # already part of ``result_fingerprint`` through the server-derived
        # candidate and coverage-review receipt references.
        command_fingerprint = self._identifiers.fingerprint(
            "requirement-verification-result-append-command-v1",
            (
                session_id,
                result.result_fingerprint,
                checked.expected_predecessor_authority_id or "none",
            ),
        )
        draft = RequirementVerificationAuthorityDraft(
            authority_record_id=result.result_id,
            session_id=session_id,
            opportunity_set_fingerprint=result.opportunity_set_fingerprint,
            opportunity_id=result.opportunity_id,
            requirement_id=result.requirement_id,
            expected_predecessor_authority_id=checked.expected_predecessor_authority_id,
            kind=RequirementVerificationAuthorityRecordKind.OBJECTIVE_RESULT,
            idempotency_key_digest=idempotency_digest,
            command_fingerprint=command_fingerprint,
            recorded_at=self._now(),
            result=result,
        )
        provenance = ObservedCheckAuthorityProvenance(
            authority_record_id=result.result_id,
            session_id=session_id,
            opportunity_set_fingerprint=result.opportunity_set_fingerprint,
            opportunity_id=result.opportunity_id,
            requirement_id=result.requirement_id,
            source_run_id=review.expected_source_run_id,
            source_window_fingerprint=review.source_window_fingerprint,
            requirement_plan_confirmation_id=review.requirement_plan_confirmation_id,
            requirement_plan_proposal_id=review.requirement_plan_proposal_id,
            candidate_manifest_fingerprint=review.candidate_manifest_fingerprint,
            source_reference_id=review.candidate.candidate_id,
            coverage_review_reference_id=coverage_reference_id,
            observed_sequence=review.candidate.observed_sequence,
            observed_outcome=review.candidate.observed_outcome,
            exit_code=review.candidate.exit_code,
            source_completion_schema_version=(
                review.candidate.source_completion_schema_version
            ),
            outcome_interpreter_version=review.candidate.outcome_interpreter_version,
            classifier_version=review.candidate.classifier_version,
            normalizer_version=review.candidate.normalizer_version,
            rule_id=review.candidate.rule_id,
            coverage_review_version=OBSERVED_CHECK_COVERAGE_REVIEW_VERSION,
            full_criterion_coverage_acknowledged=True,
            provenance_fingerprint=self._identifiers.fingerprint(
                "observed-check-authority-provenance-v1",
                (
                    result.result_id,
                    result.result_fingerprint,
                    review.expected_source_run_id,
                    review.source_window_fingerprint,
                    review.requirement_plan_confirmation_id,
                    review.requirement_plan_proposal_id,
                    review.candidate_manifest_fingerprint,
                    review.candidate.candidate_id,
                    coverage_reference_id,
                    str(review.candidate.observed_sequence),
                    review.candidate.observed_outcome,
                    str(review.candidate.exit_code),
                    review.candidate.source_completion_schema_version,
                    review.candidate.outcome_interpreter_version,
                    review.candidate.classifier_version,
                    review.candidate.normalizer_version,
                    review.candidate.rule_id,
                    OBSERVED_CHECK_COVERAGE_REVIEW_VERSION,
                ),
            ),
        )
        replay = self._exact_observed_replay(draft, provenance)
        if replay is not None:
            return replay, False
        if already_consumed:
            raise RequirementVerificationConflictError("review receipt was already used")
        try:
            self._review_service.consume_observed_check(
                session_id=session_id, command=checked
            )
        except Exception as error:
            raise RequirementVerificationConflictError(
                "fresh exact local requirement review is required"
            ) from error
        self._require_current_set(set_record)
        return self._append_observed(draft, provenance)

    def append_acceptance(
        self,
        *,
        session_id: str,
        command: RequirementAcceptanceAppendCommand,
        idempotency_key: str,
    ) -> tuple[RequirementVerificationEvidenceSnapshot, bool]:
        self._validate_session_id(session_id)
        checked_command = self._parse_acceptance_command(command)
        checked_key = self._validate_idempotency_key(idempotency_key)
        set_record = self._opportunity_set(
            session_id, checked_command.opportunity_set_fingerprint
        )
        idempotency_digest = self._idempotency_digest(session_id, checked_key)
        confirmation_id = self._identifiers.fingerprint(
            "requirement-acceptance-confirmation-v1",
            (
                session_id,
                checked_command.opportunity_set_fingerprint,
                checked_command.opportunity_id,
                idempotency_digest,
            ),
        )
        try:
            acceptance = issue_explicit_requirement_acceptance(
                set_record.opportunities,
                opportunity_id=checked_command.opportunity_id,
                confirmation_id=confirmation_id,
                outcome=checked_command.outcome,
                identifiers=self._identifiers,
            )
        except (TypeError, ValueError):
            raise RequirementVerificationInputError(
                "native acceptance references an absent opportunity"
            ) from None
        command_fingerprint = self._identifiers.fingerprint(
            "requirement-acceptance-append-command-v1",
            (
                session_id,
                checked_command.opportunity_set_fingerprint,
                checked_command.opportunity_id,
                checked_command.outcome.value,
                checked_command.confirmation,
                checked_command.expected_predecessor_authority_id or "none",
            ),
        )
        draft = RequirementVerificationAuthorityDraft(
            authority_record_id=acceptance.acceptance_id,
            session_id=session_id,
            opportunity_set_fingerprint=acceptance.opportunity_set_fingerprint,
            opportunity_id=acceptance.opportunity_id,
            requirement_id=acceptance.requirement_id,
            expected_predecessor_authority_id=(
                checked_command.expected_predecessor_authority_id
            ),
            kind=RequirementVerificationAuthorityRecordKind.NATIVE_ACCEPTANCE,
            idempotency_key_digest=idempotency_digest,
            command_fingerprint=command_fingerprint,
            recorded_at=self._now(),
            acceptance=acceptance,
        )
        replay = self._exact_replay(draft)
        if replay is not None:
            return replay, False
        if self._review_service is not None:
            try:
                self._review_service.consume(
                    session_id=session_id, command=checked_command
                )
            except Exception as error:
                raise RequirementVerificationConflictError(
                    "fresh exact local requirement review is required"
                ) from error
        self._require_current_set(set_record)
        return self._append(draft)

    def _opportunity_set(
        self, session_id: str, opportunity_set_fingerprint: str
    ) -> RequirementVerificationOpportunitySetRecord:
        try:
            record = self._repository.get_opportunity_set(
                opportunity_set_fingerprint
            )
        except RequirementVerificationEvidenceError:
            raise
        except Exception:
            raise RequirementVerificationPersistenceError(
                "requirement-verification opportunity set could not be read"
            ) from None
        if record is None or record.opportunities.session_id != session_id:
            raise RequirementVerificationNotFoundError(
                "requirement-verification opportunity set was not found"
            )
        return record

    def _require_current_set(
        self, record: RequirementVerificationOpportunitySetRecord
    ) -> None:
        current = self._current_plan(record.opportunities.session_id)
        try:
            validate_requirement_verification_opportunities(
                record.opportunities, current, self._identifiers
            )
        except (TypeError, ValueError):
            raise RequirementVerificationStaleWindowError(
                "requirement-verification opportunity set is no longer current"
            ) from None

    def _current_plan(self, session_id: str) -> RequirementPlanEvidenceSnapshot:
        try:
            snapshot = self._plan_authority.current_snapshot(session_id)
        except RequirementVerificationEvidenceError:
            raise
        except Exception:
            raise RequirementVerificationPersistenceError(
                "current reviewed requirement authority could not be read"
            ) from None
        if snapshot.session_id != session_id:
            raise RequirementVerificationPersistenceError(
                "current reviewed requirement authority belongs elsewhere"
            )
        if (
            not snapshot.complete_user_clause_classification
            or snapshot.confirmation_id is None
            or snapshot.proposal_id is None
            or snapshot.producer_receipt is None
        ):
            raise RequirementVerificationInputError(
                "complete native-reviewed r6 authority is required"
            )
        return snapshot

    def _exact_replay(
        self, draft: RequirementVerificationAuthorityDraft
    ) -> RequirementVerificationEvidenceSnapshot | None:
        try:
            existing = self._repository.find_replay(
                draft.session_id, draft.idempotency_key_digest
            )
        except RequirementVerificationEvidenceError:
            raise
        except Exception:
            raise RequirementVerificationPersistenceError(
                "requirement-verification replay could not be read"
            ) from None
        if existing is None:
            return None
        comparable = existing.model_dump(
            mode="python", exclude={"revision", "recorded_at"}
        )
        candidate = draft.model_dump(mode="python", exclude={"recorded_at"})
        if comparable != candidate or not hmac.compare_digest(
            existing.command_fingerprint, draft.command_fingerprint
        ):
            raise RequirementVerificationConflictError(
                "requirement-verification idempotency key was reused"
            )
        snapshot = self.snapshot(
            draft.session_id,
            draft.opportunity_set_fingerprint,
            through_revision=existing.revision,
        )
        return snapshot

    def _append(
        self, draft: RequirementVerificationAuthorityDraft
    ) -> tuple[RequirementVerificationEvidenceSnapshot, bool]:
        try:
            return self._repository.append_authority(draft)
        except RequirementVerificationEvidenceError:
            raise
        except Exception as error:
            raise RequirementVerificationPersistenceError(
                "requirement-verification authority could not be persisted"
            ) from error

    def _exact_observed_replay(
        self,
        draft: RequirementVerificationAuthorityDraft,
        provenance: ObservedCheckAuthorityProvenance,
    ) -> RequirementVerificationEvidenceSnapshot | None:
        replay = self._exact_replay(draft)
        if replay is None:
            return None
        try:
            persisted = self._repository.get_observed_check_provenance(
                draft.session_id, draft.authority_record_id
            )
        except RequirementVerificationEvidenceError:
            raise
        except Exception:
            raise RequirementVerificationPersistenceError(
                "observed-check provenance could not be read"
            ) from None
        if persisted != provenance:
            raise RequirementVerificationConflictError(
                "requirement-verification idempotency key was reused"
            )
        return replay

    def _append_observed(
        self,
        draft: RequirementVerificationAuthorityDraft,
        provenance: ObservedCheckAuthorityProvenance,
    ) -> tuple[RequirementVerificationEvidenceSnapshot, bool]:
        try:
            return self._repository.append_observed_authority(draft, provenance)
        except RequirementVerificationEvidenceError:
            raise
        except Exception:
            raise RequirementVerificationPersistenceError(
                "observed-check authority could not be persisted"
            ) from None

    def _idempotency_digest(self, session_id: str, key: str) -> str:
        return self._identifiers.fingerprint(
            "requirement-verification-authority-idempotency-v1",
            (session_id, key),
        )

    def _now(self) -> datetime:
        try:
            return _utc(self._clock())
        except (TypeError, ValueError):
            raise RequirementVerificationInputError(
                "requirement-verification clock is invalid"
            ) from None

    @staticmethod
    def _validate_session_id(session_id: str) -> None:
        try:
            _pseudonym(session_id)
        except (TypeError, ValueError):
            raise RequirementVerificationInputError(
                "requirement-verification session is invalid"
            ) from None

    @staticmethod
    def _validate_idempotency_key(idempotency_key: str) -> str:
        try:
            return _idempotency_key(idempotency_key)
        except (TypeError, ValueError):
            raise RequirementVerificationInputError(
                "requirement-verification idempotency key is invalid"
            ) from None

    @staticmethod
    def _parse_result_command(
        command: RequirementVerificationResultAppendCommand,
    ) -> RequirementVerificationResultAppendCommand:
        try:
            return RequirementVerificationResultAppendCommand.model_validate(
                command.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError):
            raise RequirementVerificationInputError(
                "objective result command is invalid"
            ) from None

    @staticmethod
    def _parse_observed_issue_command(
        command: ObservedCheckResultIssueCommand,
    ) -> ObservedCheckResultIssueCommand:
        try:
            return ObservedCheckResultIssueCommand.model_validate(
                command.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError):
            raise RequirementVerificationInputError(
                "observed check issue command is invalid"
            ) from None

    @staticmethod
    def _parse_acceptance_command(
        command: RequirementAcceptanceAppendCommand,
    ) -> RequirementAcceptanceAppendCommand:
        try:
            return RequirementAcceptanceAppendCommand.model_validate(
                command.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError):
            raise RequirementVerificationInputError(
                "native acceptance command is invalid"
            ) from None


__all__ = (
    "CurrentRequirementPlanAuthority",
    "CurrentRequirementPlanSourceWindowAuthority",
    "CurrentRequirementPlanSnapshotAuthority",
    "CurrentRequirementVerificationEvidenceReader",
    "MAX_REQUIREMENT_VERIFICATION_HISTORY_PER_OPPORTUNITY",
    "MAX_REQUIREMENT_VERIFICATION_REVISIONS",
    "MAX_REQUIREMENT_VERIFICATION_IDEMPOTENCY_KEY_LENGTH",
    "MIN_REQUIREMENT_VERIFICATION_IDEMPOTENCY_KEY_LENGTH",
    "REQUIREMENT_ACCEPTANCE_APPEND_CONFIRMATION",
    "REQUIREMENT_VERIFICATION_PERSISTENCE_SCHEMA_VERSION",
    "RequirementAcceptanceAppendCommand",
    "RequirementPlanEvidenceSnapshotRepository",
    "RequirementVerificationAuthorityDraft",
    "RequirementVerificationAuthorityHead",
    "RequirementVerificationAuthorityRecord",
    "RequirementVerificationAuthorityRecordKind",
    "RequirementVerificationConflictError",
    "RequirementVerificationDefinitionsOutOfDateError",
    "RequirementVerificationEvidenceError",
    "RequirementVerificationEvidenceService",
    "RequirementVerificationEvidenceSnapshot",
    "RequirementVerificationInputError",
    "RequirementVerificationNotFoundError",
    "RequirementVerificationOpportunitySetRecord",
    "RequirementVerificationPersistenceError",
    "RequirementVerificationRepository",
    "RequirementVerificationResultAppendCommand",
    "ObservedCheckResultIssueCommand",
    "ObservedCheckAuthorityProvenance",
    "OBSERVED_CHECK_COVERAGE_REVIEW_VERSION",
    "OBSERVED_CHECK_PROVENANCE_SCHEMA_VERSION",
    "OBSERVED_CHECK_RESULT_ISSUE_CONFIRMATION",
    "RequirementVerificationStaleWindowError",
)
