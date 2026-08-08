"""Consent and bounded ingestion use cases for local provider sources."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ..adapters.base import ProviderAdapter
from ..domain import DataTier, Provider, StrictModel
from ..ingestion import (
    ConsentRequiredError,
    IngestionError,
    IngestionReport,
    IngestionSelection,
)
from .display_labels import LabelEnrichmentReport

MAX_LOCAL_SOURCE_SELECTORS = 100


class LocalSourceRepository(Protocol):
    def has_active_consent(self, provider: Provider, tier: DataTier) -> bool: ...

    def grant_consent(self, provider: Provider, tier: DataTier) -> None: ...

    def revoke_consent(self, provider: Provider, tier: DataTier) -> None: ...

    def provider_catalog_summary(self, provider: Provider) -> dict[str, int]: ...

    def selection_is_indexed(
        self,
        provider: Provider,
        *,
        project_ids: frozenset[str],
        session_ids: frozenset[str],
    ) -> bool: ...


class IngestionRunner(Protocol):
    def ingest(
        self,
        adapter: ProviderAdapter,
        *,
        page_limit: int = 100,
        selection: IngestionSelection | None = None,
    ) -> IngestionReport: ...


class LabelEnrichmentRunner(Protocol):
    def enrich(
        self,
        *,
        project_ids: frozenset[str],
        session_ids: frozenset[str],
        max_sessions: int,
    ) -> LabelEnrichmentReport: ...


CodexAdapterFactory = Callable[[bool], ProviderAdapter]


class LocalSourceSelectionError(RuntimeError):
    """A safe selector is missing, excessive, or absent from the local index."""


class CodexLocalSourceStatus(StrictModel):
    consent_active: bool
    indexed_sessions: int
    indexed_projects: int


class CodexLocalSourceService:
    """Application boundary for explicit, user-triggered Codex source access."""

    _TIER = DataTier.REDACTED_CONTENT

    def __init__(
        self,
        repository: LocalSourceRepository,
        ingestion: IngestionRunner,
        adapter_factory: CodexAdapterFactory,
        label_enrichment: LabelEnrichmentRunner | None = None,
    ) -> None:
        self._repository = repository
        self._ingestion = ingestion
        self._adapter_factory = adapter_factory
        self._label_enrichment = label_enrichment

    def status(self) -> CodexLocalSourceStatus:
        counts = self._repository.provider_catalog_summary(Provider.CODEX)
        return CodexLocalSourceStatus(
            consent_active=self._repository.has_active_consent(
                Provider.CODEX, self._TIER
            ),
            indexed_sessions=counts["sessions"],
            indexed_projects=counts["projects"],
        )

    def grant_local_history(self) -> CodexLocalSourceStatus:
        self._repository.grant_consent(Provider.CODEX, self._TIER)
        return self.status()

    def revoke_local_history(self) -> CodexLocalSourceStatus:
        self._repository.revoke_consent(Provider.CODEX, self._TIER)
        return self.status()

    def index(self, *, max_sessions: int) -> IngestionReport:
        self._require_consent()
        return self._ingestion.ingest(
            self._adapter_factory(False),
            selection=IngestionSelection(max_sessions=max_sessions),
        )

    def analyze(
        self,
        *,
        project_ids: frozenset[str],
        session_ids: frozenset[str],
        max_sessions: int,
    ) -> IngestionReport:
        self._require_consent()
        if len(project_ids) + len(session_ids) > MAX_LOCAL_SOURCE_SELECTORS:
            raise LocalSourceSelectionError(
                "local-source selection exceeds the safe bound"
            )
        selection = IngestionSelection(
            project_ids=project_ids,
            session_ids=session_ids,
            max_sessions=max_sessions,
        )
        if not selection.has_selector:
            raise LocalSourceSelectionError(
                "operational history access requires an explicit safe selection"
            )
        if not self._repository.selection_is_indexed(
            Provider.CODEX,
            project_ids=selection.project_ids,
            session_ids=selection.session_ids,
        ):
            raise LocalSourceSelectionError(
                "local-source selection is not present in the safe index"
            )
        return self._ingestion.ingest(
            self._adapter_factory(True), selection=selection
        )

    def enrich_labels(
        self,
        *,
        project_ids: frozenset[str],
        session_ids: frozenset[str],
        max_sessions: int,
    ) -> LabelEnrichmentReport:
        if self._label_enrichment is None:
            raise IngestionError("local label enrichment is unavailable")
        return self._label_enrichment.enrich(
            project_ids=project_ids,
            session_ids=session_ids,
            max_sessions=max_sessions,
        )

    def _require_consent(self) -> None:
        if not self._repository.has_active_consent(Provider.CODEX, self._TIER):
            raise ConsentRequiredError(
                "explicit source consent is required before provider access"
            )
