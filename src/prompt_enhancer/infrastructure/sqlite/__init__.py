"""Narrow SQLite adapters for local, privacy-sensitive persistence."""

__all__ = (
    "SqliteAnalysisRunRepository",
    "SqliteModelLinkExperimentRepository",
    "SqliteSessionAnalysisRunRepository",
    "SqliteTaskRepository",
)


def __getattr__(name: str):
    """Load repositories lazily so migration imports cannot form a cycle."""

    if name == "SqliteAnalysisRunRepository":
        from .analysis_runs import SqliteAnalysisRunRepository

        return SqliteAnalysisRunRepository
    if name == "SqliteTaskRepository":
        from .tasks import SqliteTaskRepository

        return SqliteTaskRepository
    if name == "SqliteSessionAnalysisRunRepository":
        from .session_analysis_runs import SqliteSessionAnalysisRunRepository

        return SqliteSessionAnalysisRunRepository
    if name == "SqliteModelLinkExperimentRepository":
        from .model_link_experiments import SqliteModelLinkExperimentRepository

        return SqliteModelLinkExperimentRepository
    raise AttributeError(name)
