"""Authenticated loopback API for typed metric-lifecycle confirmations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response
from pydantic import Field

from ...application.analysis.metric_lifecycle_evidence import (
    MAX_LIFECYCLE_ENUMERATION_SIZE,
    MetricLifecycleConflictError,
    MetricLifecycleDecisionCommand,
    MetricLifecycleDecisionKind,
    MetricLifecycleInputError,
    MetricLifecycleLinkKind,
    MetricLifecycleNotFoundError,
    MetricLifecycleOpportunityKind,
    MetricLifecycleOutcomeKind,
    MetricLifecyclePersistenceError,
    MetricLifecycleProposalCommand,
    MetricLifecycleProposalKind,
    MetricLifecycleProposalStatus,
    MetricLifecycleProposalView,
    MetricLifecycleStaleWindowError,
    MetricLifecycleFamily,
)
from ...domain import PSEUDONYM_PATTERN, SAFE_VERSION_PATTERN, StrictModel


_PRIVATE_HEADERS = {"Cache-Control": "no-store, private", "Pragma": "no-cache"}


class MetricLifecycleEvidenceCommand(Protocol):
    def propose(
        self,
        *,
        session_id: str,
        command: MetricLifecycleProposalCommand,
        idempotency_key: str,
    ) -> tuple[MetricLifecycleProposalView, bool]: ...

    def decide(
        self,
        *,
        session_id: str,
        proposal_id: str,
        command: MetricLifecycleDecisionCommand,
        idempotency_key: str,
    ) -> tuple[MetricLifecycleProposalView, bool]: ...

    def list(self, session_id: str) -> tuple[MetricLifecycleProposalView, ...]: ...


class MetricLifecycleProposalDto(StrictModel):
    proposal_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    session_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    source_run_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    proposal_revision: int = Field(ge=1, le=1)
    proposal_kind: MetricLifecycleProposalKind
    family: MetricLifecycleFamily
    opportunity_kind: MetricLifecycleOpportunityKind
    opportunity_id: str | None = Field(
        default=None, pattern=PSEUDONYM_PATTERN.pattern
    )
    link_kind: MetricLifecycleLinkKind | None = None
    outcome_kind: MetricLifecycleOutcomeKind | None = None
    enumerated_opportunity_ids: tuple[str, ...] = Field(
        default=(), max_length=MAX_LIFECYCLE_ENUMERATION_SIZE
    )
    status: MetricLifecycleProposalStatus
    decision_id: str | None = Field(default=None, pattern=PSEUDONYM_PATTERN.pattern)
    decision: MetricLifecycleDecisionKind | None = None
    created_at: datetime
    decided_at: datetime | None = None
    schema_version: str
    policy_version: str
    local_only: bool
    content_persisted: bool

    @classmethod
    def from_view(cls, view: MetricLifecycleProposalView) -> "MetricLifecycleProposalDto":
        proposal = view.proposal
        decision = view.decision
        return cls(
            proposal_id=proposal.proposal_id,
            session_id=proposal.session_id,
            source_run_id=proposal.source_run_id,
            proposal_revision=proposal.proposal_revision,
            proposal_kind=proposal.proposal_kind,
            family=proposal.family,
            opportunity_kind=proposal.opportunity_kind,
            opportunity_id=proposal.opportunity_id,
            link_kind=proposal.link_kind,
            outcome_kind=proposal.outcome_kind,
            enumerated_opportunity_ids=proposal.enumerated_opportunity_ids,
            status=view.status,
            decision_id=None if decision is None else decision.decision_id,
            decision=None if decision is None else decision.decision,
            created_at=proposal.created_at,
            decided_at=None if decision is None else decision.decided_at,
            schema_version=proposal.schema_version,
            policy_version=proposal.policy_version,
            local_only=proposal.local_only,
            content_persisted=proposal.content_persisted,
        )


class MetricLifecycleProposalOutcomeDto(StrictModel):
    proposal: MetricLifecycleProposalDto
    applied: bool


class MetricLifecycleProposalListDto(StrictModel):
    session_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    proposals: tuple[MetricLifecycleProposalDto, ...] = Field(max_length=1_000)


def _failure(error: Exception) -> HTTPException:
    if isinstance(error, MetricLifecycleInputError):
        return HTTPException(
            422,
            detail={"code": error.code, "message": "lifecycle evidence request is invalid"},
        )
    if isinstance(error, MetricLifecycleNotFoundError):
        return HTTPException(
            404,
            detail={"code": error.code, "message": "lifecycle evidence authority was not found"},
        )
    if isinstance(error, (MetricLifecycleStaleWindowError, MetricLifecycleConflictError)):
        return HTTPException(
            409,
            detail={"code": error.code, "message": "lifecycle evidence state changed"},
        )
    if isinstance(error, MetricLifecyclePersistenceError):
        return HTTPException(
            503,
            detail={"code": error.code, "message": "lifecycle evidence is unavailable"},
        )
    raise TypeError("unsupported lifecycle evidence error")


def create_metric_lifecycle_evidence_router(
    require_local_auth: Callable[..., None],
    service: MetricLifecycleEvidenceCommand,
) -> APIRouter:
    router = APIRouter(
        prefix="/v1",
        tags=["metric-lifecycle-evidence"],
        dependencies=[Depends(require_local_auth)],
    )

    @router.post(
        "/sessions/{session_id}/metric-lifecycle-evidence/proposals",
        response_model=MetricLifecycleProposalOutcomeDto,
    )
    def propose(
        payload: MetricLifecycleProposalCommand,
        response: Response,
        session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
        idempotency_key: Annotated[
            str,
            Header(alias="Idempotency-Key", pattern=SAFE_VERSION_PATTERN.pattern),
        ],
    ) -> MetricLifecycleProposalOutcomeDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            view, applied = service.propose(
                session_id=session_id,
                command=payload,
                idempotency_key=idempotency_key,
            )
        except (
            MetricLifecycleConflictError,
            MetricLifecycleInputError,
            MetricLifecycleNotFoundError,
            MetricLifecyclePersistenceError,
            MetricLifecycleStaleWindowError,
        ) as error:
            raise _failure(error) from None
        response.status_code = 201 if applied else 200
        return MetricLifecycleProposalOutcomeDto(
            proposal=MetricLifecycleProposalDto.from_view(view),
            applied=applied,
        )

    @router.post(
        "/sessions/{session_id}/metric-lifecycle-evidence/proposals/{proposal_id}/decision",
        response_model=MetricLifecycleProposalOutcomeDto,
    )
    def decide(
        payload: MetricLifecycleDecisionCommand,
        response: Response,
        session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
        proposal_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
        idempotency_key: Annotated[
            str,
            Header(alias="Idempotency-Key", pattern=SAFE_VERSION_PATTERN.pattern),
        ],
    ) -> MetricLifecycleProposalOutcomeDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            view, applied = service.decide(
                session_id=session_id,
                proposal_id=proposal_id,
                command=payload,
                idempotency_key=idempotency_key,
            )
        except (
            MetricLifecycleConflictError,
            MetricLifecycleInputError,
            MetricLifecycleNotFoundError,
            MetricLifecyclePersistenceError,
            MetricLifecycleStaleWindowError,
        ) as error:
            raise _failure(error) from None
        response.status_code = 201 if applied else 200
        return MetricLifecycleProposalOutcomeDto(
            proposal=MetricLifecycleProposalDto.from_view(view),
            applied=applied,
        )

    @router.get(
        "/sessions/{session_id}/metric-lifecycle-evidence/proposals",
        response_model=MetricLifecycleProposalListDto,
    )
    def list_proposals(
        response: Response,
        session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
    ) -> MetricLifecycleProposalListDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            proposals = service.list(session_id)
        except (
            MetricLifecycleInputError,
            MetricLifecycleNotFoundError,
            MetricLifecyclePersistenceError,
        ) as error:
            raise _failure(error) from None
        return MetricLifecycleProposalListDto(
            session_id=session_id,
            proposals=tuple(
                MetricLifecycleProposalDto.from_view(item) for item in proposals
            ),
        )

    return router


__all__ = [
    "MetricLifecycleProposalDto",
    "MetricLifecycleProposalListDto",
    "MetricLifecycleProposalOutcomeDto",
    "create_metric_lifecycle_evidence_router",
]
