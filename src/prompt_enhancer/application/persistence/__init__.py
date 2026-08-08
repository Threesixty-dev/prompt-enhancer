"""Stable persistence records and ports used by application use cases."""

from .contracts import (
    AnalysisResultRecord,
    AnalysisRunDraft,
    AnalysisRunRecord,
    AnalysisRunRepository,
    AnalysisRunStatus,
    CandidateSignalRecord,
    CandidateDecisionStatus,
    CandidateListItem,
    DecisionAction,
    DecisionRevisionLink,
    DecisionRevisionRole,
    MetricValueState,
    TaskCandidateRecord,
    TaskDecisionRecord,
    TaskRepository,
    TaskRevisionRecord,
)
from .errors import PersistenceConflictError

__all__ = (
    "AnalysisResultRecord",
    "AnalysisRunDraft",
    "AnalysisRunRecord",
    "AnalysisRunRepository",
    "AnalysisRunStatus",
    "CandidateSignalRecord",
    "CandidateDecisionStatus",
    "CandidateListItem",
    "DecisionAction",
    "DecisionRevisionLink",
    "DecisionRevisionRole",
    "MetricValueState",
    "PersistenceConflictError",
    "TaskCandidateRecord",
    "TaskDecisionRecord",
    "TaskRepository",
    "TaskRevisionRecord",
)
