"""Application composition root for the private local runtime.

Concrete infrastructure is selected here so CLI and HTTP entry points do not
independently assemble databases, privacy primitives, and use-case services.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .config import AppSettings, prepare_app_home
from .database import Database
from .ingestion import IngestionService
from .privacy import (
    Pseudonymizer,
    load_or_create_api_token,
    load_or_create_pseudonymizer,
)

if TYPE_CHECKING:
    from .application.analysis import TaskAnalysisService
    from .application.discovery import (
        DiscoveryPersistenceService,
        TaskDiscoveryEngine,
        TaskReviewService,
    )
    from .application.local_sources import CodexLocalSourceService
    from fastapi import FastAPI


@dataclass(frozen=True, slots=True)
class LocalApplication:
    """Concrete services for one local application installation.

    The API token is deliberately not retained on this object, exposed as a
    property, or included in its representation. It is loaded only when the HTTP
    adapter is constructed.
    """

    settings: AppSettings
    database: Database
    pseudonymizer: Pseudonymizer

    def create_ingestion_service(self) -> IngestionService:
        """Construct the ingestion use case from already validated dependencies."""
        return IngestionService(self.database, self.pseudonymizer)

    def create_codex_local_source_service(
        self,
    ) -> CodexLocalSourceService:
        """Construct explicit consent, index, and selected-analysis commands."""

        from .application.display_labels import (
            LabelObservationMethod,
            ProviderLabelSource,
            ProviderDisplayLabelEnrichmentService,
            ProviderDisplayLabelPolicy,
        )
        from .application.local_sources import CodexLocalSourceService
        from .domain import DataTier, Provider
        from .infrastructure.providers.codex_app_server import (
            LABEL_EXTRACTOR_VERSION,
        )

        return CodexLocalSourceService(
            self.database,
            self.create_ingestion_service(),
            lambda operational_history: self.create_codex_adapter(
                operational_history=operational_history
            ),
            ProviderDisplayLabelEnrichmentService(
                self.database,
                self.pseudonymizer,
                lambda: self.create_codex_adapter(label_enrichment=True),
                ProviderDisplayLabelPolicy(
                    provider=Provider.CODEX,
                    consent_tier=DataTier.REDACTED_CONTENT,
                    observation_method=LabelObservationMethod.THREAD_READ_SUMMARY,
                    extractor_version=LABEL_EXTRACTOR_VERSION,
                    project_label_source=ProviderLabelSource.PATH_BASENAME,
                    session_label_source=ProviderLabelSource.EXPLICIT_TITLE,
                ),
            ),
        )

    @staticmethod
    def create_codex_adapter(
        *,
        operational_history: bool = False,
        label_enrichment: bool = False,
    ):
        """Select the documented, read-only Codex infrastructure adapter."""

        from .infrastructure.providers.codex_app_server import (
            CodexAppServerAdapter,
            CodexReadMode,
        )

        if operational_history and label_enrichment:
            raise ValueError("Codex adapter modes are mutually exclusive")
        if operational_history:
            mode = CodexReadMode.OPERATIONAL_HISTORY
        elif label_enrichment:
            mode = CodexReadMode.LABEL_ENRICHMENT
        else:
            mode = CodexReadMode.METADATA_INDEX
        return CodexAppServerAdapter(mode=mode)

    def create_manual_display_label_service(self):
        from .application.display_labels import ManualDisplayLabelService

        return ManualDisplayLabelService(self.database)

    def create_task_discovery_engine(self) -> TaskDiscoveryEngine:
        """Construct deterministic discovery with installation-local IDs."""

        from .application.discovery import TaskDiscoveryEngine
        from .infrastructure.identifiers import LocalArtifactIdFactory

        return TaskDiscoveryEngine(LocalArtifactIdFactory(self.pseudonymizer))

    def create_discovery_persistence_service(self) -> DiscoveryPersistenceService:
        """Construct discovery plus immutable candidate persistence."""

        from .application.discovery import (
            DiscoveryPersistenceService,
            TaskDiscoveryEngine,
        )
        from .infrastructure.identifiers import LocalArtifactIdFactory

        identifiers = LocalArtifactIdFactory(self.pseudonymizer)
        return DiscoveryPersistenceService(
            TaskDiscoveryEngine(identifiers),
            self.database.task_repository(),
            identifiers,
        )

    def create_task_review_service(self) -> TaskReviewService:
        """Construct explicit review commands over the narrow task repository."""

        from .application.discovery import TaskReviewService
        from .infrastructure.identifiers import LocalArtifactIdFactory

        return TaskReviewService(
            self.database.task_repository(),
            LocalArtifactIdFactory(self.pseudonymizer),
        )

    def create_task_analysis_service(self) -> TaskAnalysisService:
        """Construct the immutable deterministic task-analysis use case."""

        from .application.analysis import TaskAnalysisService
        from .database import SCHEMA_VERSION
        from .infrastructure.identifiers import LocalArtifactIdFactory

        return TaskAnalysisService(
            self.database.task_repository(),
            self.database.analysis_run_repository(),
            self.database,
            LocalArtifactIdFactory(self.pseudonymizer),
            schema_version=SCHEMA_VERSION,
        )

    def create_http_app(self) -> FastAPI:
        """Construct the authenticated HTTP adapter without exposing its token."""

        from .api import create_app

        token = load_or_create_api_token(self.settings.api_token_path)
        dashboard_build = Path(__file__).parents[2] / "frontend" / "dist"
        static_directory = (
            dashboard_build if (dashboard_build / "index.html").is_file() else None
        )
        return create_app(
            settings=self.settings,
            database=self.database,
            api_token=token,
            task_review_service=self.create_task_review_service(),
            task_analysis_service=self.create_task_analysis_service(),
            codex_source_service=self.create_codex_local_source_service(),
            display_label_service=self.create_manual_display_label_service(),
            static_directory=static_directory,
        )


def bootstrap_local_application(settings: AppSettings) -> LocalApplication:
    """Build the local modular monolith and enforce private-state prerequisites."""

    prepare_app_home(settings)
    database = Database(settings.database_path)
    database.initialize()
    pseudonymizer = load_or_create_pseudonymizer(settings.pseudonym_key_path)

    # Initialization promises that every CLI command leaves a complete local
    # installation. Discard the value so it cannot leak through the composition
    # root or an object's repr.
    load_or_create_api_token(settings.api_token_path)

    return LocalApplication(
        settings=settings,
        database=database,
        pseudonymizer=pseudonymizer,
    )
