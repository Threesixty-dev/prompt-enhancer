"""Narrow inward-facing ports for provider ingestion orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ...domain import DataTier, MetricObservation, Provider, SafeEvent, SafeSession


class PersistenceOutcome(Protocol):
    session_inserted: int
    session_updated: int
    events_inserted: int
    events_updated: int


class IngestionRepository(Protocol):
    """Persistence capability needed by one ingestion transaction stream."""

    def initialize(self) -> None: ...

    def has_active_consent(
        self, provider: Provider, tier: DataTier = DataTier.METADATA
    ) -> bool: ...

    def begin_ingestion_run(
        self,
        *,
        provider: Provider,
        provider_version: str,
        adapter_version: str,
        source_schema_version: str,
        data_tier: DataTier = DataTier.METADATA,
    ) -> str: ...

    def finish_ingestion_run(
        self,
        run_id: str,
        *,
        status: str,
        sessions_seen: int,
        events_seen: int,
        metrics_written: int,
        error_code: str | None = None,
    ) -> None: ...

    def persist_session(
        self, session: SafeSession, events: Iterable[SafeEvent]
    ) -> PersistenceOutcome: ...

    def get_session(self, session_id: str) -> SafeSession | None: ...

    def get_session_events(self, session_id: str) -> tuple[SafeEvent, ...]: ...

    def replace_session_metrics(
        self,
        session_id: str,
        observations: Iterable[MetricObservation],
        *,
        metric_engine_version: str = ...,
    ) -> int: ...


class SourceIdentifierProtector(Protocol):
    """One-way domain-separated transformation before persistence."""

    def pseudonymize(self, namespace: str, value: str) -> str: ...


class SessionMetricComputer(Protocol):
    def __call__(
        self, session: SafeSession, events: Iterable[SafeEvent]
    ) -> tuple[MetricObservation, ...]: ...
