"""Content-free contracts for task and immutable analysis persistence.

These records deliberately contain only pseudonymous identifiers, bounded safe
labels, numeric observations, and provenance. They provide no place to attach
prompt text, summaries, source snippets, paths, or provider account data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
import re
from typing import Protocol

from pydantic import Field, field_validator, model_validator

from ...domain import (
    DataTier,
    MetricObservation,
    Provider,
    SignalDirection,
    StrictModel,
)


_HEX_64 = re.compile(r"^[a-f0-9]{64}$")
_SAFE_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:/-]{0,127}$")
_SAFE_LABEL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _pseudonym(value: str) -> str:
    if not _HEX_64.fullmatch(value):
        raise ValueError("persistent identifiers must be 64-character safe identifiers")
    return value


def _optional_pseudonym(value: str | None) -> str | None:
    if value is None:
        return None
    return _pseudonym(value)


def _safe_code(value: str | None) -> str | None:
    if value is not None and not _SAFE_CODE.fullmatch(value):
        raise ValueError("provenance versions must use safe identifier characters")
    return value


def _safe_label(value: str | None) -> str | None:
    if value is not None and not _SAFE_LABEL.fullmatch(value):
        raise ValueError("labels must be short content-free identifiers")
    return value


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(UTC)


def _unique(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")
    return values


class DecisionAction(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    MERGE = "merge"
    SPLIT = "split"


class CandidateDecisionStatus(StrEnum):
    UNDECIDED = "undecided"
    DECIDED = "decided"


class DecisionRevisionRole(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


class AnalysisRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MetricValueState(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    ABSTAINED = "abstained"
    EXECUTION_ERROR = "execution_error"


class CandidateSignalRecord(StrictModel):
    key: str
    version: int = Field(ge=1)
    session_ids: tuple[str, str]
    direction: SignalDirection
    confidence: float | None = Field(default=None, ge=0, le=1)
    weight: float = Field(gt=0, allow_inf_nan=False)
    evidence_code: str
    observed_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    numeric_evidence: float | None = Field(default=None, allow_inf_nan=False)
    evidence_unit: str | None = None

    _validate_key = field_validator("key")(_safe_code)
    _validate_evidence_code = field_validator("evidence_code")(_safe_label)
    _validate_evidence_unit = field_validator("evidence_unit")(_safe_code)
    _validate_session_ids = field_validator("session_ids")(
        lambda values: _unique(tuple(_pseudonym(value) for value in values), "session_ids")
    )

    @model_validator(mode="after")
    def validate_signal(self) -> CandidateSignalRecord:
        if self.observed_count > self.eligible_count:
            raise ValueError("observed_count cannot exceed eligible_count")
        expected = (
            0.0
            if self.eligible_count == 0
            else self.observed_count / self.eligible_count
        )
        if abs(self.coverage - expected) > 1e-9:
            raise ValueError("coverage must equal observed_count / eligible_count")
        if self.direction is SignalDirection.UNKNOWN:
            if self.confidence is not None:
                raise ValueError("unknown signals cannot have confidence")
        elif self.confidence is None:
            raise ValueError("directional signals require confidence")
        if self.confidence is not None and self.observed_count == 0:
            raise ValueError("confidence requires observed evidence")
        if (self.numeric_evidence is None) != (self.evidence_unit is None):
            raise ValueError("numeric evidence and unit must be supplied together")
        return self


class TaskCandidateRecord(StrictModel):
    candidate_id: str
    provider: Provider
    installation_id: str
    project_id: str
    session_ids: tuple[str, ...]
    signals: tuple[CandidateSignalRecord, ...]
    confidence: float | None = Field(default=None, ge=0, le=1)
    observed_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    discovery_version: str
    input_fingerprint: str
    created_at: datetime

    _validate_ids = field_validator(
        "candidate_id", "installation_id", "project_id", "input_fingerprint"
    )(_pseudonym)
    _validate_version = field_validator("discovery_version")(_safe_code)
    _validate_created_at = field_validator("created_at")(_utc)
    _validate_session_ids = field_validator("session_ids")(
        lambda values: _unique(tuple(_pseudonym(value) for value in values), "session_ids")
    )

    @model_validator(mode="after")
    def validate_candidate(self) -> TaskCandidateRecord:
        if not self.session_ids:
            raise ValueError("task candidates require at least one session")
        if self.observed_count > self.eligible_count:
            raise ValueError("observed_count cannot exceed eligible_count")
        expected = (
            0.0
            if self.eligible_count == 0
            else self.observed_count / self.eligible_count
        )
        if abs(self.coverage - expected) > 1e-9:
            raise ValueError("coverage must equal observed_count / eligible_count")
        if self.confidence is not None and self.observed_count == 0:
            raise ValueError("candidate confidence requires observed evidence")
        candidate_sessions = set(self.session_ids)
        if any(not set(signal.session_ids) <= candidate_sessions for signal in self.signals):
            raise ValueError("signal sessions must belong to the candidate")
        return self


class CandidateListItem(StrictModel):
    candidate: TaskCandidateRecord
    decision_status: CandidateDecisionStatus
    decision_id: str | None = None
    decision_action: DecisionAction | None = None

    _validate_decision_id = field_validator("decision_id")(_optional_pseudonym)

    @model_validator(mode="after")
    def validate_decision_state(self) -> CandidateListItem:
        has_decision = self.decision_id is not None or self.decision_action is not None
        if self.decision_status is CandidateDecisionStatus.UNDECIDED:
            if has_decision:
                raise ValueError("undecided candidates cannot include a decision")
        elif self.decision_id is None or self.decision_action is None:
            raise ValueError("decided candidates require decision provenance")
        return self


class TaskRevisionRecord(StrictModel):
    task_id: str
    revision: int = Field(ge=1)
    project_id: str
    task_type: str
    lifecycle_state: str
    session_ids: tuple[str, ...]
    input_fingerprint: str
    created_at: datetime

    _validate_ids = field_validator("task_id", "project_id", "input_fingerprint")(
        _pseudonym
    )
    _validate_labels = field_validator("task_type", "lifecycle_state")(_safe_label)
    _validate_created_at = field_validator("created_at")(_utc)
    _validate_session_ids = field_validator("session_ids")(
        lambda values: _unique(tuple(_pseudonym(value) for value in values), "session_ids")
    )

    @model_validator(mode="after")
    def require_sessions(self) -> TaskRevisionRecord:
        if not self.session_ids:
            raise ValueError("task revisions require at least one session")
        return self


class DecisionRevisionLink(StrictModel):
    task_id: str
    revision: int = Field(ge=1)
    role: DecisionRevisionRole

    _validate_task_id = field_validator("task_id")(_pseudonym)


class TaskDecisionRecord(StrictModel):
    decision_id: str
    action: DecisionAction
    candidate_ids: tuple[str, ...]
    revision_links: tuple[DecisionRevisionLink, ...]
    decision_schema_version: str
    decision_code: str | None = None
    decided_at: datetime

    _validate_decision_id = field_validator("decision_id")(_pseudonym)
    _validate_version = field_validator("decision_schema_version")(_safe_code)
    _validate_decision_code = field_validator("decision_code")(_safe_label)
    _validate_decided_at = field_validator("decided_at")(_utc)
    _validate_candidate_ids = field_validator("candidate_ids")(
        lambda values: _unique(tuple(_pseudonym(value) for value in values), "candidate_ids")
    )

    @model_validator(mode="after")
    def validate_shape(self) -> TaskDecisionRecord:
        revision_identities = {
            (link.task_id, link.revision, link.role) for link in self.revision_links
        }
        if len(revision_identities) != len(self.revision_links):
            raise ValueError("revision links cannot contain duplicates")
        inputs = [link for link in self.revision_links if link.role is DecisionRevisionRole.INPUT]
        outputs = [link for link in self.revision_links if link.role is DecisionRevisionRole.OUTPUT]
        if self.action is DecisionAction.REJECT:
            if (
                len(self.candidate_ids) != 1
                or self.revision_links
                or self.decision_code is None
            ):
                raise ValueError("reject decisions require candidates and no task revisions")
        elif self.decision_code is not None:
            raise ValueError("only reject decisions may include a decision code")
        elif self.action is DecisionAction.ACCEPT:
            if len(self.candidate_ids) != 1 or inputs or len(outputs) != 1:
                raise ValueError("accept decisions require one candidate and one output revision")
        elif self.action is DecisionAction.MERGE:
            source_count = len(self.candidate_ids) + len(inputs)
            if source_count < 2 or len(outputs) != 1:
                raise ValueError("merge decisions require multiple inputs and one output revision")
        elif self.action is DecisionAction.SPLIT:
            source_count = len(self.candidate_ids) + len(inputs)
            if source_count != 1 or len(outputs) < 2:
                raise ValueError("split decisions require one input and multiple output revisions")
        return self


class AnalysisRunDraft(StrictModel):
    run_id: str
    task_id: str
    task_revision: int = Field(ge=1)
    metric_pack_key: str
    metric_pack_version: int = Field(ge=1)
    data_tier: DataTier
    input_fingerprint: str
    metric_engine_version: str
    redactor_version: str
    schema_version: int = Field(ge=1)
    started_at: datetime

    _validate_ids = field_validator("run_id", "task_id", "input_fingerprint")(
        _pseudonym
    )
    _validate_pack = field_validator("metric_pack_key")(_safe_code)
    _validate_versions = field_validator("metric_engine_version", "redactor_version")(
        _safe_code
    )
    _validate_started_at = field_validator("started_at")(_utc)


class AnalysisResultRecord(StrictModel):
    observation: MetricObservation
    value_state: MetricValueState
    calculator_version: str
    evidence_event_ids: tuple[str, ...] = ()
    model_id: str | None = None
    model_revision: str | None = None
    tokenizer_id: str | None = None
    prompt_version: str | None = None
    rubric_version: str | None = None
    error_code: str | None = None
    computed_at: datetime

    _validate_calculator = field_validator("calculator_version")(_safe_code)
    _validate_provenance = field_validator(
        "model_id", "model_revision", "tokenizer_id", "prompt_version", "rubric_version"
    )(_safe_code)
    _validate_error = field_validator("error_code")(_safe_label)
    _validate_computed_at = field_validator("computed_at")(_utc)
    _validate_evidence = field_validator("evidence_event_ids")(
        lambda values: _unique(
            tuple(_pseudonym(value) for value in values), "evidence_event_ids"
        )
    )

    @model_validator(mode="after")
    def validate_value_state(self) -> AnalysisResultRecord:
        has_value = (
            self.observation.numeric_value is not None
            or self.observation.text_value is not None
        )
        if self.value_state is MetricValueState.KNOWN:
            if not has_value or self.error_code is not None:
                raise ValueError("known results require a value and no error code")
        elif has_value:
            raise ValueError("non-known results cannot contain a metric value")
        elif self.value_state is MetricValueState.EXECUTION_ERROR:
            if self.error_code is None:
                raise ValueError("execution errors require a safe error code")
        elif self.error_code is not None:
            raise ValueError("only execution errors may contain an error code")
        return self


class AnalysisRunRecord(StrictModel):
    draft: AnalysisRunDraft
    status: AnalysisRunStatus
    finished_at: datetime | None = None
    failure_code: str | None = None

    _validate_finished_at = field_validator("finished_at")(_utc)
    _validate_failure_code = field_validator("failure_code")(_safe_label)

    @model_validator(mode="after")
    def validate_terminal_state(self) -> AnalysisRunRecord:
        if self.status is AnalysisRunStatus.RUNNING:
            if self.finished_at is not None or self.failure_code is not None:
                raise ValueError("running analysis cannot have terminal fields")
        elif self.status is AnalysisRunStatus.COMPLETED:
            if self.finished_at is None or self.failure_code is not None:
                raise ValueError("completed analysis requires only a finish timestamp")
        elif self.finished_at is None or self.failure_code is None:
            raise ValueError("failed analysis requires a finish timestamp and failure code")
        return self


class TaskRepository(Protocol):
    def add_candidate(self, candidate: TaskCandidateRecord) -> None: ...

    def get_candidate(self, candidate_id: str) -> TaskCandidateRecord | None: ...

    def list_candidates(
        self,
        *,
        status: CandidateDecisionStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[CandidateListItem, ...]: ...

    def append_revision(self, revision: TaskRevisionRecord) -> None: ...

    def get_revision(self, task_id: str, revision: int) -> TaskRevisionRecord | None: ...

    def list_task_revisions(
        self,
        *,
        task_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[TaskRevisionRecord, ...]: ...

    def record_decision(self, decision: TaskDecisionRecord) -> None: ...

    def apply_review_decision(
        self,
        decision: TaskDecisionRecord,
        output_revisions: tuple[TaskRevisionRecord, ...],
        *,
        expected_discovery_version: str,
    ) -> bool: ...

    def list_decisions(self, candidate_id: str) -> tuple[TaskDecisionRecord, ...]: ...

    def delete_candidate_for_privacy(self, candidate_id: str) -> bool: ...

    def delete_task_for_privacy(self, task_id: str) -> bool: ...


class AnalysisRunRepository(Protocol):
    def begin(self, draft: AnalysisRunDraft) -> None: ...

    def complete(
        self,
        run_id: str,
        results: tuple[AnalysisResultRecord, ...],
        *,
        finished_at: datetime,
    ) -> None: ...

    def fail(self, run_id: str, *, finished_at: datetime, failure_code: str) -> None: ...

    def get(self, run_id: str) -> AnalysisRunRecord | None: ...

    def list_analysis_runs(
        self,
        *,
        task_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[AnalysisRunRecord, ...]: ...

    def get_results(self, run_id: str) -> tuple[AnalysisResultRecord, ...]: ...

    def delete_for_privacy(self, run_id: str) -> bool: ...
