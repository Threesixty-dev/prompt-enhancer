"""Application composition root for the private local runtime.

Concrete infrastructure is selected here so CLI and HTTP entry points do not
independently assemble databases, privacy primitives, and use-case services.
"""

from __future__ import annotations

from dataclasses import dataclass
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
        MetricCoverageService,
        MetricReadinessService,
        ProjectQualityAggregationService,
        SessionModelLinkExperimentService,
        SessionModelEnsembleService,
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
    from .application.task_lifecycle import TaskLifecycleService
    from .application.jobs import AnalysisJobService, AnalysisJobWorker
    from .application.automation import (
        AutomationGrantService,
        AutomationGrantWorker,
    )
    from .infrastructure.control_plane import DevelopmentControlPlane
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

    def create_task_lifecycle_service(self) -> TaskLifecycleService:
        """Construct explicit local-user work-state commands."""

        from .application.task_lifecycle import TaskLifecycleService
        from .infrastructure.identifiers import LocalArtifactIdFactory

        return TaskLifecycleService(
            self.database.task_lifecycle_repository(),
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
        from .application.persistence import SESSION_ANALYSIS_RUN_SCHEMA_VERSION
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
            schema_version=SESSION_ANALYSIS_RUN_SCHEMA_VERSION,
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

    def create_metric_coverage_service(
        self,
        metric_readiness_service: MetricReadinessService,
    ) -> MetricCoverageService:
        """Compose exact local-index counts with cached capability truth."""

        from datetime import UTC, datetime

        from .application.analysis.metric_coverage import MetricCoverageService

        return MetricCoverageService(
            self.database.metric_coverage_repository(),
            metric_readiness_service,
            clock=lambda: datetime.now(UTC),
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

    def create_session_model_ensemble_service(
        self,
        compatibility_policy: ProviderSurfaceCompatibilityPolicy,
    ) -> SessionModelEnsembleService:
        """Compose the serial, process-isolated all-metric live pipeline."""

        from .application.analysis import SessionModelEnsembleService
        from .application.analysis.provider_evidence import (
            SAFE_EVENT_EVIDENCE_DECODER_CURRENT_VERSION,
            SAFE_EVENT_EVIDENCE_DECODER_KEY,
            SafeEventTypedEvidenceProjector,
        )
        from .application.analysis.semantic_units import SemanticUnitReconciler
        from .application.providers import (
            CapabilityKey,
            DecoderDescriptor,
            ProviderIdentity,
            ProviderSurface,
            SchemaArtifactKind,
            SchemaArtifactProvenance,
        )
        from .domain import Provider
        from .infrastructure.identifiers import LocalArtifactIdFactory
        from .infrastructure.providers.codex_app_server import CodexTextAnalysisSource
        from .infrastructure.providers.codex_app_server.contracts import (
            ADAPTER_VERSION,
            SOURCE_SCHEMA_VERSION,
        )
        from .infrastructure.text_models.probabilistic_metrics import (
            LocalProbabilisticMetricRunner,
        )

        def source_factory(provider: Provider) -> CodexTextAnalysisSource:
            if provider is not Provider.CODEX:
                raise ValueError("unsupported local model-ensemble provider")
            return CodexTextAnalysisSource(self.pseudonymizer)

        safe_event_descriptor = DecoderDescriptor(
            provider=ProviderIdentity(key="codex"),
            surface=ProviderSurface.OPERATIONAL_EVENTS,
            adapter_version=ADAPTER_VERSION,
            decoder_key=SAFE_EVENT_EVIDENCE_DECODER_KEY,
            decoder_version=SAFE_EVENT_EVIDENCE_DECODER_CURRENT_VERSION,
            wire_schema_family="codex.app-server.v2.safe-events",
            canonical_schema_version=SOURCE_SCHEMA_VERSION,
            schema_artifact=SchemaArtifactProvenance(
                artifact_key="codex.safe-event-index",
                artifact_version="1",
                kind=SchemaArtifactKind.MINIMIZED,
            ),
            capabilities=(CapabilityKey.TOOL_EVENTS,),
        )

        return SessionModelEnsembleService(
            self.database,
            self.database.model_ensemble_repository(),
            source_factory,
            compatibility_policy,
            LocalArtifactIdFactory(self.pseudonymizer),
            LocalProbabilisticMetricRunner(),
            typed_evidence_projector=SafeEventTypedEvidenceProjector(
                self.database,
                LocalArtifactIdFactory(self.pseudonymizer),
                safe_event_descriptor,
            ),
            semantic_unit_reconciler=SemanticUnitReconciler(
                LocalArtifactIdFactory(self.pseudonymizer),
            ),
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

    def create_analysis_job_service(self) -> AnalysisJobService:
        """Compose the durable content-free queue without enabling a runner."""

        from .application.jobs import AnalysisJobService

        return AnalysisJobService(self.database.analysis_job_repository())

    def create_automation_runtime(
        self,
        *,
        codex_source_service: CodexLocalSourceService,
        session_text_analysis_service: SessionTextAnalysisService,
        analysis_job_service: AnalysisJobService,
    ) -> tuple[
        AutomationGrantService,
        AutomationGrantWorker,
        AnalysisJobWorker,
    ]:
        """Compose the local-only scheduler and its single reviewed worker."""

        from datetime import UTC, datetime, timedelta

        from .application.analysis.coaching_baselines import (
            COACHING_METRIC_ENGINE_VERSION,
            COACHING_METRIC_PACK_VERSION,
            COACHING_METRIC_RUBRIC_VERSION,
        )
        from .application.automation import (
            AutomationGrantService,
            AutomationGrantWorker,
            AutomationJobGuard,
            SessionQualityAutomationHandler,
        )
        from .application.jobs import (
            AnalysisJobKind,
            AnalysisJobWorker,
        )
        from .domain import Provider
        from .infrastructure.automation import (
            LocalAutomationAccessPolicy,
            LocalAutomationCatalogRefresher,
            LocalAutomationIdFactory,
            QueueAutomationJobSink,
        )
        from .infrastructure.power import LocalPowerSourceReader
        from .infrastructure.redaction.deterministic import (
            DETERMINISTIC_REDACTOR_VERSION,
        )

        estimator_plan_version = (
            f"coaching-v{COACHING_METRIC_PACK_VERSION}-"
            f"{COACHING_METRIC_ENGINE_VERSION}-"
            f"{COACHING_METRIC_RUBRIC_VERSION}"
        )
        clock = lambda: datetime.now(UTC)
        power_source = LocalPowerSourceReader()
        access = LocalAutomationAccessPolicy(self.database)
        candidates = self.database.automation_candidate_source(
            estimator_plan_version=estimator_plan_version,
            redactor_version=DETERMINISTIC_REDACTOR_VERSION,
        )
        grants = self.database.automation_grant_repository()
        grant_service = AutomationGrantService(
            grants,
            access,
            LocalAutomationCatalogRefresher(
                {Provider.CODEX: codex_source_service}
            ),
            candidates,
            QueueAutomationJobSink(
                analysis_job_service,
                estimator_plan_version=estimator_plan_version,
                redactor_version=DETERMINISTIC_REDACTOR_VERSION,
            ),
            LocalAutomationIdFactory(),
            power_source,
            clock=clock,
        )
        guard = AutomationJobGuard(
            grants,
            access,
            candidates,
            clock=clock,
        )
        job_worker = AnalysisJobWorker(
            self.database.analysis_job_repository(),
            {
                (AnalysisJobKind.SESSION_QUALITY, Provider.CODEX): (
                    SessionQualityAutomationHandler(
                        session_text_analysis_service
                    )
                )
            },
            authorization_check=guard.authorized,
            fingerprint_resolver=guard.fingerprints,
            power_source=power_source,
            clock=clock,
            lease_duration=timedelta(minutes=5),
        )
        return grant_service, AutomationGrantWorker(grant_service), job_worker

    def create_control_plane(self) -> DevelopmentControlPlane:
        """Compose the in-memory development control plane and its resolver.

        The composed plane starts with no organizations, no credentials, and no
        entitlement, so enabling the setting exposes routes that authenticate
        nobody and authorize nothing until a tenant is provisioned deliberately
        and in process. Nothing here reads the analyzer database, provider
        sessions, or local files, and nothing it holds survives a restart.
        """

        from datetime import UTC, datetime

        from .infrastructure.control_plane import create_development_control_plane

        return create_development_control_plane(lambda: datetime.now(UTC))

    def create_http_app(self) -> FastAPI:
        """Construct the authenticated HTTP adapter without exposing its token."""

        from .api import create_app
        from .application.providers import (
            CapabilityKey,
            ProviderSurface,
            ProviderSurfaceCompatibilityPolicy,
        )
        from .domain import Provider
        from .infrastructure.text_models.jobs import LocalTextModelEvaluationService
        from .application.resources import ResourceAvailability, ResourceKind
        from .infrastructure.resources import default_packaged_resource_resolver

        token = load_or_create_api_token(self.settings.api_token_path)
        dashboard_resource = default_packaged_resource_resolver().resolve(
            ResourceKind.DASHBOARD_STATIC
        )
        static_directory = (
            dashboard_resource.path
            if dashboard_resource.availability is ResourceAvailability.AVAILABLE
            else None
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
        codex_source_service = self.create_codex_local_source_service()
        session_text_analysis_service = self.create_session_text_analysis_service(
            compatibility_policy
        )
        metric_readiness_service = self.create_metric_readiness_service(
            compatibility_catalog
        )
        metric_coverage_service = self.create_metric_coverage_service(
            metric_readiness_service
        )
        session_model_ensemble_service = self.create_session_model_ensemble_service(
            compatibility_policy
        )
        from .application.analysis.model_ensemble_watch import (
            ModelEnsembleWatchService,
            ModelEnsembleWatchWorker,
        )

        model_ensemble_watch_service = ModelEnsembleWatchService(
            self.database.model_ensemble_watch_repository(),
            session_model_ensemble_service,
        )
        model_ensemble_watch_worker = ModelEnsembleWatchWorker(
            model_ensemble_watch_service
        )
        analysis_job_service = self.create_analysis_job_service()
        (
            automation_grant_service,
            automation_grant_worker,
            analysis_job_worker,
        ) = self.create_automation_runtime(
            codex_source_service=codex_source_service,
            session_text_analysis_service=session_text_analysis_service,
            analysis_job_service=analysis_job_service,
        )
        def revoke_local_workers(provider: Provider) -> int:
            return (
                automation_grant_service.revoke_provider(provider)
                + model_ensemble_watch_service.quarantine_for_provider(provider)
            )

        codex_source_service.set_automation_revoker(revoke_local_workers)
        control_plane = (
            self.create_control_plane()
            if self.settings.control_plane_development_api
            else None
        )
        return create_app(
            settings=self.settings,
            database=self.database,
            api_token=token,
            task_review_service=self.create_task_review_service(),
            task_lifecycle_service=self.create_task_lifecycle_service(),
            task_analysis_service=self.create_task_analysis_service(),
            session_text_analysis_service=session_text_analysis_service,
            session_model_link_experiment_service=(
                self.create_session_model_link_experiment_service(
                    compatibility_policy
                )
            ),
            session_model_ensemble_service=session_model_ensemble_service,
            model_ensemble_watch_service=model_ensemble_watch_service,
            model_ensemble_watch_worker=model_ensemble_watch_worker,
            project_quality_aggregation_service=(
                self.create_project_quality_aggregation_service()
            ),
            provider_compatibility_catalog=compatibility_catalog,
            metric_readiness_service=metric_readiness_service,
            metric_coverage_service=metric_coverage_service,
            codex_source_service=codex_source_service,
            display_label_service=self.create_manual_display_label_service(),
            model_evaluation_service=LocalTextModelEvaluationService(),
            analysis_job_service=analysis_job_service,
            analysis_job_worker=analysis_job_worker,
            automation_grant_service=automation_grant_service,
            automation_grant_worker=automation_grant_worker,
            control_plane_service=(
                None if control_plane is None else control_plane.service
            ),
            control_plane_principal_resolver=(
                None if control_plane is None else control_plane.resolver
            ),
            estimator_repository=self.database.estimator_repository(),
            static_directory=static_directory,
        )


def bootstrap_local_application(settings: AppSettings) -> LocalApplication:
    """Build the local modular monolith and enforce private-state prerequisites."""

    prepare_app_home(settings)
    pseudonymizer = load_or_create_pseudonymizer(settings.pseudonym_key_path)
    from .infrastructure.identifiers import LocalArtifactIdFactory

    database = Database(settings.database_path)
    database.configure_local_artifact_id_factory(
        LocalArtifactIdFactory(pseudonymizer)
    )
    database.initialize()

    # Initialization promises that every CLI command leaves a complete local
    # installation. Discard the value so it cannot leak through the composition
    # root or an object's repr.
    load_or_create_api_token(settings.api_token_path)

    return LocalApplication(
        settings=settings,
        database=database,
        pseudonymizer=pseudonymizer,
    )
