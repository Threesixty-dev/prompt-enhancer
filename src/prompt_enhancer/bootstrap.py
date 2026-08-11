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
    from .application.analysis import (
        MetricReadinessService,
        ProjectQualityAggregationService,
        SessionModelLinkExperimentService,
        SessionTextAnalysisService,
        TaskAnalysisService,
    )
    from .application.providers import (
        ProviderCompatibilityCatalog,
        ProviderSurfaceCompatibilityPolicy,
    )
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
        from .infrastructure.verification import validation_only_capability

        return CodexLocalSourceService(
            self.database,
            self.create_ingestion_service(),
            lambda operational_history: self.create_codex_adapter(
                operational_history=operational_history
            ),
            validation_only_capability(),
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

    def create_provider_compatibility_catalog(self) -> ProviderCompatibilityCatalog:
        """Compose only built-in, release-reviewed compatibility probes."""

        from .application.providers import (
            ProviderCompatibilityCatalog,
            ProviderCompatibilityService,
            TrustedProviderRegistry,
        )
        from .infrastructure.providers.codex_app_server import (
            CODEX_TEXT_WINDOW_DECODER_DESCRIPTOR,
            CodexTextWindowCompatibilityProbe,
        )

        descriptor = CODEX_TEXT_WINDOW_DECODER_DESCRIPTOR
        registry = TrustedProviderRegistry((descriptor,))
        service = ProviderCompatibilityService(
            registry,
            (CodexTextWindowCompatibilityProbe(),),
        )
        return ProviderCompatibilityCatalog(service, (descriptor,))

    def create_session_text_analysis_service(
        self,
        compatibility_policy: ProviderSurfaceCompatibilityPolicy,
    ) -> SessionTextAnalysisService:
        """Construct the explicit, one-session local P1 analysis command."""

        from .application.analysis import SessionTextAnalysisService
        from .database import SCHEMA_VERSION
        from .domain import Provider
        from .infrastructure.identifiers import LocalArtifactIdFactory
        from .infrastructure.providers.codex_app_server import CodexTextAnalysisSource

        def source_factory(provider: Provider) -> CodexTextAnalysisSource:
            if provider is not Provider.CODEX:
                raise ValueError("unsupported local text-analysis provider")
            return CodexTextAnalysisSource(self.pseudonymizer)

        return SessionTextAnalysisService(
            self.database,
            self.database.session_analysis_run_repository(),
            source_factory,
            compatibility_policy,
            LocalArtifactIdFactory(self.pseudonymizer),
            schema_version=SCHEMA_VERSION,
        )

    def create_metric_readiness_service(
        self,
        compatibility_catalog: ProviderCompatibilityCatalog,
    ) -> MetricReadinessService:
        """Compose cached provider capability and persisted readiness queries."""

        from .application.analysis.metric_readiness import MetricReadinessService

        return MetricReadinessService(
            self.database,
            self.database.session_analysis_run_repository(),
            compatibility_catalog,
        )

    def create_session_model_link_experiment_service(
        self,
        compatibility_policy: ProviderSurfaceCompatibilityPolicy,
    ) -> SessionModelLinkExperimentService:
        """Compose the explicit offline neural comparison for one session."""

        from .application.analysis import SessionModelLinkExperimentService
        from .domain import Provider
        from .infrastructure.identifiers import LocalArtifactIdFactory
        from .infrastructure.providers.codex_app_server import CodexTextAnalysisSource
        from .infrastructure.text_models.session_links import (
            SubprocessSessionModelLinkRunner,
        )

        def source_factory(provider: Provider) -> CodexTextAnalysisSource:
            if provider is not Provider.CODEX:
                raise ValueError("unsupported local model-link provider")
            return CodexTextAnalysisSource(self.pseudonymizer)

        return SessionModelLinkExperimentService(
            self.database,
            self.database.model_link_experiment_repository(),
            source_factory,
            compatibility_policy,
            LocalArtifactIdFactory(self.pseudonymizer),
            SubprocessSessionModelLinkRunner(),
        )

    def create_project_quality_aggregation_service(
        self,
    ) -> ProjectQualityAggregationService:
        """Compose indexed-project resolution with immutable session aggregation."""

        from .application.analysis import (
            FingerprintedSessionQualityAggregator,
            ProjectQualityAggregationService,
            SessionQualityAggregationService,
        )
        from .application.analysis.coaching_baselines import (
            COACHING_METRIC_DEFINITIONS,
            COACHING_METRIC_PACK_KEY,
            COACHING_METRIC_PACK_VERSION,
        )
        from .application.analysis.text_analysis_presets import COACHING_PROFILE_V1

        def session_quality_factory(repository):
            return FingerprintedSessionQualityAggregator(
                SessionQualityAggregationService(
                    repository,
                    definitions=COACHING_METRIC_DEFINITIONS,
                    analysis_profile_key=COACHING_PROFILE_V1.analysis_profile_key,
                    analysis_profile_version=(
                        COACHING_PROFILE_V1.analysis_profile_version
                    ),
                    metric_pack_key=COACHING_METRIC_PACK_KEY,
                    metric_pack_version=COACHING_METRIC_PACK_VERSION,
                )
            )

        return ProjectQualityAggregationService(
            self.database,
            session_quality_factory,
        )

    def create_http_app(self) -> FastAPI:
        """Construct the authenticated HTTP adapter without exposing its token."""

        from .api import create_app
        from .application.providers import (
            CapabilityKey,
            ProviderSurface,
            ProviderSurfaceCompatibilityPolicy,
        )
        from .infrastructure.text_models.jobs import LocalTextModelEvaluationService

        token = load_or_create_api_token(self.settings.api_token_path)
        dashboard_build = Path(__file__).parents[2] / "frontend" / "dist"
        static_directory = (
            dashboard_build if (dashboard_build / "index.html").is_file() else None
        )
        compatibility_catalog = self.create_provider_compatibility_catalog()
        # This invokes only the documented schema generator in an isolated
        # empty provider home. It never lists or reads provider sessions.
        compatibility_catalog.refresh("codex", ProviderSurface.TEXT_WINDOW)
        compatibility_policy = ProviderSurfaceCompatibilityPolicy(
            compatibility_catalog,
            surface=ProviderSurface.TEXT_WINDOW,
            required_capabilities=(
                CapabilityKey.USER_MESSAGES,
                CapabilityKey.AGENT_MESSAGES,
                CapabilityKey.PLAN_MESSAGES,
            ),
        )
        return create_app(
            settings=self.settings,
            database=self.database,
            api_token=token,
            task_review_service=self.create_task_review_service(),
            task_analysis_service=self.create_task_analysis_service(),
            session_text_analysis_service=(
                self.create_session_text_analysis_service(compatibility_policy)
            ),
            session_model_link_experiment_service=(
                self.create_session_model_link_experiment_service(
                    compatibility_policy
                )
            ),
            project_quality_aggregation_service=(
                self.create_project_quality_aggregation_service()
            ),
            provider_compatibility_catalog=compatibility_catalog,
            metric_readiness_service=(
                self.create_metric_readiness_service(compatibility_catalog)
            ),
            codex_source_service=self.create_codex_local_source_service(),
            display_label_service=self.create_manual_display_label_service(),
            model_evaluation_service=LocalTextModelEvaluationService(),
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
