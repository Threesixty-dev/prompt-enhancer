"""Narrow SQLite adapters for local, privacy-sensitive persistence."""

__all__ = ("SqliteAnalysisRunRepository", "SqliteTaskRepository")


def __getattr__(name: str):
    """Load repositories lazily so migration imports cannot form a cycle."""

    if name == "SqliteAnalysisRunRepository":
        from .analysis_runs import SqliteAnalysisRunRepository

        return SqliteAnalysisRunRepository
    if name == "SqliteTaskRepository":
        from .tasks import SqliteTaskRepository

        return SqliteTaskRepository
    raise AttributeError(name)
