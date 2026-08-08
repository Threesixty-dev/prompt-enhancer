"""Strict, content-free HTTP DTOs for task discovery and analysis views.

The API maps persistence records explicitly instead of serializing arbitrary
objects. These schemas have no field for prompt text, paths, source snippets,
account data, or provider credentials.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ...application.discovery import SignalDirection
from ...application.persistence import (
    AnalysisResultRecord,
    AnalysisRunRecord,
    AnalysisRunStatus,
    CandidateDecisionStatus,
    CandidateListItem,
    CandidateSignalRecord,
    DecisionAction,
    DecisionRevisionRole,
    MetricValueState,
    TaskCandidateRecord,
    TaskDecisionRecord,
    TaskRevisionRecord,
)
from ...domain import DataTier, MetricSource, PSEUDONYM_PATTERN, Provider


Pseudonym = Annotated[
    str,
    Field(
        min_length=64,
        max_length=64,
        pattern=PSEUDONYM_PATTERN.pattern,
        strict=True,
    ),
]


class HttpDto(BaseModel):
    """Base for API-owned DTOs; response construction is validated too."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )


class CandidateSignalDto(HttpDto):
    key: str
    version: int = Field(ge=1)
    session_ids: tuple[Pseudonym, Pseudonym]
    direction: SignalDirection
    confidence: float | None = Field(default=None, ge=0, le=1)
    weight: float = Field(gt=0, allow_inf_nan=False)
    evidence_code: str
    observed_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    numeric_evidence: float | None = Field(default=None, allow_inf_nan=False)
    evidence_unit: str | None

    @classmethod
    def from_record(cls, record: CandidateSignalRecord) -> CandidateSignalDto:
        return cls(
            key=record.key,
            version=record.version,
            session_ids=record.session_ids,
            direction=record.direction,
            confidence=record.confidence,
            weight=record.weight,
            evidence_code=record.evidence_code,
            observed_count=record.observed_count,
            eligible_count=record.eligible_count,
            coverage=record.coverage,
            numeric_evidence=record.numeric_evidence,
            evidence_unit=record.evidence_unit,
        )


class TaskCandidateDto(HttpDto):
    candidate_id: Pseudonym
    provider: Provider
    installation_id: Pseudonym
    project_id: Pseudonym
    session_ids: tuple[Pseudonym, ...]
    signals: tuple[CandidateSignalDto, ...]
    confidence: float | None = Field(default=None, ge=0, le=1)
    observed_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    discovery_version: str
    input_fingerprint: Pseudonym
    created_at: datetime

    @classmethod
    def from_record(cls, record: TaskCandidateRecord) -> TaskCandidateDto:
        return cls(
            candidate_id=record.candidate_id,
            provider=record.provider,
            installation_id=record.installation_id,
            project_id=record.project_id,
            session_ids=record.session_ids,
            signals=tuple(
                CandidateSignalDto.from_record(signal) for signal in record.signals
            ),
            confidence=record.confidence,
            observed_count=record.observed_count,
            eligible_count=record.eligible_count,
            coverage=record.coverage,
            discovery_version=record.discovery_version,
            input_fingerprint=record.input_fingerprint,
            created_at=record.created_at,
        )


class CandidateResponse(HttpDto):
    candidate: TaskCandidateDto


class CandidateListItemDto(HttpDto):
    candidate: TaskCandidateDto
    decision_status: CandidateDecisionStatus
    decision_id: Pseudonym | None
    decision_action: DecisionAction | None

    @classmethod
    def from_record(cls, record: CandidateListItem) -> CandidateListItemDto:
        return cls(
            candidate=TaskCandidateDto.from_record(record.candidate),
            decision_status=record.decision_status,
            decision_id=record.decision_id,
            decision_action=record.decision_action,
        )


class CandidateListResponse(HttpDto):
    candidates: tuple[CandidateListItemDto, ...]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class DecisionRevisionLinkDto(HttpDto):
    task_id: Pseudonym
    revision: int = Field(ge=1)
    role: DecisionRevisionRole


class TaskDecisionDto(HttpDto):
    decision_id: Pseudonym
    action: DecisionAction
    candidate_ids: tuple[Pseudonym, ...]
    revision_links: tuple[DecisionRevisionLinkDto, ...]
    decision_schema_version: str
    decision_code: str | None
    decided_at: datetime

    @classmethod
    def from_record(cls, record: TaskDecisionRecord) -> TaskDecisionDto:
        return cls(
            decision_id=record.decision_id,
            action=record.action,
            candidate_ids=record.candidate_ids,
            revision_links=tuple(
                DecisionRevisionLinkDto(
                    task_id=link.task_id,
                    revision=link.revision,
                    role=link.role,
                )
                for link in record.revision_links
            ),
            decision_schema_version=record.decision_schema_version,
            decision_code=record.decision_code,
            decided_at=record.decided_at,
        )


class CandidateDecisionsResponse(HttpDto):
    candidate_id: Pseudonym
    decisions: tuple[TaskDecisionDto, ...]


class TaskRevisionDto(HttpDto):
    task_id: Pseudonym
    revision: int = Field(ge=1)
    project_id: Pseudonym
    task_type: str
    lifecycle_state: str
    session_ids: tuple[Pseudonym, ...]
    input_fingerprint: Pseudonym
    created_at: datetime

    @classmethod
    def from_record(cls, record: TaskRevisionRecord) -> TaskRevisionDto:
        return cls(
            task_id=record.task_id,
            revision=record.revision,
            project_id=record.project_id,
            task_type=record.task_type,
            lifecycle_state=record.lifecycle_state,
            session_ids=record.session_ids,
            input_fingerprint=record.input_fingerprint,
            created_at=record.created_at,
        )


class TaskRevisionResponse(HttpDto):
    task: TaskRevisionDto


class TaskRevisionListResponse(HttpDto):
    tasks: tuple[TaskRevisionDto, ...]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class AnalysisRunDto(HttpDto):
    run_id: Pseudonym
    task_id: Pseudonym
    task_revision: int = Field(ge=1)
    metric_pack_key: str
    metric_pack_version: int = Field(ge=1)
    data_tier: DataTier
    input_fingerprint: Pseudonym
    metric_engine_version: str
    redactor_version: str
    schema_version: int = Field(ge=1)
    started_at: datetime
    status: AnalysisRunStatus
    finished_at: datetime | None
    failure_code: str | None

    @classmethod
    def from_record(cls, record: AnalysisRunRecord) -> AnalysisRunDto:
        return cls(
            run_id=record.draft.run_id,
            task_id=record.draft.task_id,
            task_revision=record.draft.task_revision,
            metric_pack_key=record.draft.metric_pack_key,
            metric_pack_version=record.draft.metric_pack_version,
            data_tier=record.draft.data_tier,
            input_fingerprint=record.draft.input_fingerprint,
            metric_engine_version=record.draft.metric_engine_version,
            redactor_version=record.draft.redactor_version,
            schema_version=record.draft.schema_version,
            started_at=record.draft.started_at,
            status=record.status,
            finished_at=record.finished_at,
            failure_code=record.failure_code,
        )


class AnalysisRunListResponse(HttpDto):
    runs: tuple[AnalysisRunDto, ...]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class AnalysisResultDto(HttpDto):
    key: str
    version: int = Field(ge=1)
    value_state: MetricValueState
    numeric_value: float | None
    text_value: str | None
    unit: str
    source: MetricSource
    observed_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    calculator_version: str
    evidence_event_ids: tuple[Pseudonym, ...]
    model_id: str | None
    model_revision: str | None
    tokenizer_id: str | None
    prompt_version: str | None
    rubric_version: str | None
    error_code: str | None
    computed_at: datetime

    @classmethod
    def from_record(cls, record: AnalysisResultRecord) -> AnalysisResultDto:
        observation = record.observation
        return cls(
            key=observation.key,
            version=observation.version,
            value_state=record.value_state,
            numeric_value=observation.numeric_value,
            text_value=observation.text_value,
            unit=observation.unit,
            source=observation.source,
            observed_count=observation.observed_count,
            eligible_count=observation.eligible_count,
            coverage=observation.coverage,
            confidence=observation.confidence,
            calculator_version=record.calculator_version,
            evidence_event_ids=record.evidence_event_ids,
            model_id=record.model_id,
            model_revision=record.model_revision,
            tokenizer_id=record.tokenizer_id,
            prompt_version=record.prompt_version,
            rubric_version=record.rubric_version,
            error_code=record.error_code,
            computed_at=record.computed_at,
        )


class AnalysisRunResponse(HttpDto):
    run: AnalysisRunDto
    results: tuple[AnalysisResultDto, ...]
