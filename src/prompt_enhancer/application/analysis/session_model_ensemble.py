"""Explicit local measured and predictive analysis for one redacted session window."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Callable, Protocol

from pydantic import field_validator, model_validator

from ...domain import DataTier, PSEUDONYM_PATTERN, Provider, SAFE_VERSION_PATTERN, StrictModel
from ..providers import DecoderDescriptor
from .evidence_contracts import (
    EphemeralTypedEvidenceProjection,
    validate_projection_descriptor,
)
from .model_ensemble import (
    EnsembleChunkPlan,
    EnsembleMetricSpec,
    MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION,
    SessionModelEnsembleReceipt,
    SessionModelEnsembleTypedMetricReceipt,
    build_ensemble_chunks,
    coaching_ensemble_metric_specs,
)
from .objective_metric_projection import project_objective_metric_overrides_v3
from .metric_projection_v3 import project_metric_states_v3
from .metric_publication_v2 import MetricPublicationV2, publish_metric_states_v2
from .provider_evidence import bind_semantic_unit_opportunities
from .semantic_units import (
    SemanticUnitProjection,
    SemanticUnitReconciliation,
    SemanticUnitReconciler,
)
from .coaching_baselines import (
    COACHING_METRIC_PACK_KEY,
    COACHING_METRIC_PACK_VERSION,
    DEFAULT_COACHING_METRIC_ENGINE,
)
from .session_text_service import (
    SessionTextAnalysisAccessPolicy,
    SessionTextAnalysisCompatibilityPolicy,
    SessionTextAnalysisIdFactory,
    SessionTextAnalysisSourceFactory,
)
from .text_analysis_presets import COACHING_PROFILE_V1
from .text_baselines import TextMetricEngine
from .text_contracts import P1LocalAnalysisGrant, P1TextAnalysisInput
from .text_source import (
    TextAnalysisPurpose,
    TextAnalysisSelection,
    TextSourceAccessGrant,
    TextSourceFailureReason,
    TextSourceReadError,
)


MODEL_ENSEMBLE_CONFIRMATION = "run_local_metric_cascade_on_selected_redacted_text"
LEGACY_MODEL_ENSEMBLE_CONFIRMATION = "run_ten_local_models_on_selected_redacted_text"
MODEL_ENSEMBLE_POLICY_VERSION = "explicit-local-shadow-ensemble-v1"
_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")


def _pseudonym(value: str) -> str:
    if PSEUDONYM_PATTERN.fullmatch(value) is None:
        raise ValueError("identifier must be a local pseudonym")
    return value


def _safe_code(value: str) -> str:
    if SAFE_VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("provenance value is invalid")
    return value


class SessionModelEnsembleRunRecord(StrictModel):
    run_id: str
    session_id: str
    request_fingerprint: str
    input_fingerprint: str
    provider: Provider
    provider_version: str
    adapter_version: str
    source_schema_version: str
    content_schema_version: str
    redactor_version: str
    consent_policy_version: str = MODEL_ENSEMBLE_POLICY_VERSION
    receipt: SessionModelEnsembleReceipt

    _ids = field_validator(
        "run_id", "session_id", "request_fingerprint", "input_fingerprint"
    )(_pseudonym)
    _codes = field_validator(
        "provider_version",
        "adapter_version",
        "source_schema_version",
        "content_schema_version",
        "redactor_version",
        "consent_policy_version",
    )(_safe_code)

    @model_validator(mode="after")
    def validate_binding(self) -> "SessionModelEnsembleRunRecord":
        if self.input_fingerprint != self.receipt.source_window_fingerprint:
            raise ValueError("ensemble receipt is bound to another source window")
        return self


class SessionModelEnsembleOutcome(StrictModel):
    run: SessionModelEnsembleRunRecord
    applied: bool


class SessionModelEnsemblePersistenceAuthority(StrictModel):
    """Ephemeral lease proof checked atomically with a watch-owned save."""

    watch_id: str
    owner: str
    token: str
    generation: int
    observed_at: datetime
    prior_run_id: str | None = None

    _ids = field_validator("watch_id", "owner", "token")(_pseudonym)

    @field_validator("prior_run_id")
    @classmethod
    def validate_prior_run_id(cls, value: str | None) -> str | None:
        return None if value is None else _pseudonym(value)

    @field_validator("generation")
    @classmethod
    def validate_generation(cls, value: int) -> int:
        if isinstance(value, bool) or not 1 <= value <= 1_000_000_000:
            raise ValueError("watch generation is invalid")
        return value

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("watch persistence observation must be UTC")
        return value


class SessionModelEnsembleRunner(Protocol):
    def plan_fingerprint(
        self,
        metric_specs: tuple[EnsembleMetricSpec, ...],
    ) -> str: ...

    def run(
        self,
        chunk_plan: EnsembleChunkPlan,
        metric_specs: tuple[EnsembleMetricSpec, ...],
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        prior_receipt: SessionModelEnsembleReceipt | None = None,
        typed_evidence: EphemeralTypedEvidenceProjection | None = None,
    ) -> SessionModelEnsembleReceipt: ...


class SessionTypedEvidenceProjector(Protocol):
    """Optional content-free provider-event bridge for the measured lane."""

    @property
    def descriptor(self) -> DecoderDescriptor: ...

    def project(
        self,
        *,
        provider: Provider,
        session_id: str,
    ) -> EphemeralTypedEvidenceProjection | None: ...


class SessionModelEnsembleRepository(Protocol):
    def save_completed(
        self,
        run: SessionModelEnsembleRunRecord,
        *,
        authority: SessionModelEnsemblePersistenceAuthority | None = None,
        semantic_units: SemanticUnitReconciliation | None = None,
    ) -> None: ...

    def get(self, run_id: str) -> SessionModelEnsembleRunRecord | None: ...

    def get_latest(self, session_id: str) -> SessionModelEnsembleRunRecord | None: ...

    def save_metric_projection(
        self,
        run: SessionModelEnsembleRunRecord,
        *,
        authority: SessionModelEnsemblePersistenceAuthority | None = None,
    ) -> None: ...

    def get_semantic_unit_reconciliation(
        self,
        run_id: str,
    ) -> SemanticUnitReconciliation | None: ...

    def delete_for_privacy(self, run_id: str) -> bool: ...


class SessionModelEnsembleError(RuntimeError):
    code = "model_ensemble_failed"


class ModelEnsembleInputError(SessionModelEnsembleError):
    code = "invalid_model_ensemble_request"


class ModelEnsembleConfirmationError(SessionModelEnsembleError):
    code = "model_ensemble_confirmation_required"


class ModelEnsembleConsentError(SessionModelEnsembleError):
    code = "redacted_content_consent_required"


class ModelEnsembleSelectionError(SessionModelEnsembleError):
    code = "session_not_in_safe_index"


class ModelEnsembleCompatibilityError(SessionModelEnsembleError):
    code = "provider_compatibility_blocked"


class ModelEnsembleSourceError(SessionModelEnsembleError):
    def __init__(self, reason: TextSourceFailureReason) -> None:
        self.reason = reason
        self.code = reason.value
        super().__init__(reason.value)


class ModelEnsembleExecutionError(SessionModelEnsembleError):
    code = "local_model_ensemble_execution_failed"


class ModelEnsemblePersistenceError(SessionModelEnsembleError):
    code = "model_ensemble_persistence_failed"


class SessionModelEnsembleService:
    """Run the local measured-and-predictive cascade over a redacted window."""

    def __init__(
        self,
        access_policy: SessionTextAnalysisAccessPolicy,
        repository: SessionModelEnsembleRepository,
        source_factory: SessionTextAnalysisSourceFactory,
        compatibility_policy: SessionTextAnalysisCompatibilityPolicy,
        identifiers: SessionTextAnalysisIdFactory,
        runner: SessionModelEnsembleRunner,
        metric_engine: TextMetricEngine = DEFAULT_COACHING_METRIC_ENGINE,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        typed_evidence_projector: SessionTypedEvidenceProjector | None = None,
        semantic_unit_reconciler: SemanticUnitReconciler | None = None,
    ) -> None:
        self._access_policy = access_policy
        self._repository = repository
        self._source_factory = source_factory
        self._compatibility_policy = compatibility_policy
        self._identifiers = identifiers
        self._runner = runner
        self._metric_engine = metric_engine
        self._clock = clock
        self._typed_evidence_projector = typed_evidence_projector
        self._semantic_unit_reconciler = semantic_unit_reconciler
        self._lock = Lock()

    def run(
        self,
        *,
        provider: Provider,
        session_id: str,
        confirmation: str,
        idempotency_key: str,
        max_messages: int = COACHING_PROFILE_V1.max_messages,
        progress_callback: Callable[[int, int], None] | None = None,
        reuse_latest: bool = False,
        prior_run_id: str | None = None,
        persistence_authority: (
            Callable[[], SessionModelEnsemblePersistenceAuthority] | None
        ) = None,
    ) -> SessionModelEnsembleOutcome:
        if (
            provider is not Provider.CODEX
            or PSEUDONYM_PATTERN.fullmatch(session_id) is None
            or _IDEMPOTENCY.fullmatch(idempotency_key) is None
            or not isinstance(max_messages, int)
            or isinstance(max_messages, bool)
            or not 1 <= max_messages <= COACHING_PROFILE_V1.max_messages
            or (
                prior_run_id is not None
                and PSEUDONYM_PATTERN.fullmatch(prior_run_id) is None
            )
        ):
            raise ModelEnsembleInputError("model ensemble selection is invalid")
        if confirmation not in {
            MODEL_ENSEMBLE_CONFIRMATION,
            LEGACY_MODEL_ENSEMBLE_CONFIRMATION,
        }:
            raise ModelEnsembleConfirmationError(
                "explicit model ensemble confirmation is required"
            )
        request_fingerprint = self._identifiers.fingerprint(
            "session-model-ensemble-request-v2",
            (
                provider.value,
                session_id,
                idempotency_key,
                MODEL_ENSEMBLE_POLICY_VERSION,
                str(max_messages),
            ),
        )
        run_id = self._identifiers.fingerprint(
            "session-model-ensemble-run-v1",
            (session_id, request_fingerprint),
        )
        with self._lock:
            existing = self._safe_get(run_id)
            if existing is not None:
                return SessionModelEnsembleOutcome(run=existing, applied=False)
            self._enforce_access(provider, session_id)
            context = self._read_context(provider, session_id, max_messages)
            typed_evidence = self._project_typed_evidence(provider, session_id)
            typed_metrics: tuple[SessionModelEnsembleTypedMetricReceipt, ...] | None = None
            metric_publication_v2: MetricPublicationV2 | None = None
            projection_completed_at: datetime | None = None
            latest: SessionModelEnsembleRunRecord | None = None
            prior_semantic_units: SemanticUnitReconciliation | None = None
            semantic_projection: SemanticUnitProjection | None = None
            specs = coaching_ensemble_metric_specs()
            try:
                current_plan_fingerprint = self._runner.plan_fingerprint(specs)
            except Exception:
                raise ModelEnsembleExecutionError(
                    "local model ensemble plan is unavailable"
                ) from None
            if reuse_latest:
                try:
                    latest = (
                        None
                        if prior_run_id is None
                        else self._repository.get(prior_run_id)
                    )
                except Exception:
                    raise ModelEnsemblePersistenceError(
                        "model ensemble results are unavailable"
                    ) from None
                compatible = latest is not None and (
                    latest.session_id == session_id
                    and latest.provider is provider
                    and latest.provider_version == context.provider_version
                    and latest.adapter_version == context.adapter_version
                    and latest.source_schema_version == context.source_schema_version
                    and latest.content_schema_version == context.content_schema_version
                    and latest.redactor_version == context.redactor_version
                )
                if latest is not None and not compatible:
                    latest = None
                semantic_projection, prior_semantic_units = (
                    self._reconcile_semantic_units(context, latest)
                )
                typed_evidence = self._bind_objective_opportunities(
                    typed_evidence,
                    semantic_projection,
                )
                (
                    typed_metrics,
                    metric_publication_v2,
                    projection_completed_at,
                ) = self._project_metrics(
                    context,
                    semantic_projection,
                    typed_evidence,
                )
                semantic_units_reusable = (
                    semantic_projection is None
                    or (
                        prior_semantic_units is not None
                        and not semantic_projection.reconciliation.appended
                        and semantic_projection.reconciliation.heads
                        == prior_semantic_units.heads
                    )
                )
                if (
                    latest is not None
                    and latest.input_fingerprint == context.analysis_window_fingerprint
                    and latest.receipt.plan_fingerprint == current_plan_fingerprint
                    and semantic_units_reusable
                ):
                    if (
                        latest.receipt.metric_projection_version
                        == MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION
                        and latest.receipt.typed_metrics == typed_metrics
                        and latest.receipt.metric_publication_v2
                        == metric_publication_v2
                    ):
                        if progress_callback is not None:
                            progress_callback(10, 10)
                        return SessionModelEnsembleOutcome(run=latest, applied=False)
                    if latest.receipt.metric_projection_version is None:
                        projected = self._with_metric_projection(
                            latest,
                            typed_metrics,
                            metric_publication_v2,
                            projection_completed_at,
                        )
                        try:
                            self._repository.save_metric_projection(
                                projected,
                                authority=(
                                    None
                                    if persistence_authority is None
                                    else persistence_authority()
                                ),
                            )
                        except Exception:
                            race = self._safe_get(latest.run_id)
                            if (
                                race is None
                                or race.receipt.metric_projection_version
                                != MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION
                                or race.receipt.typed_metrics != typed_metrics
                                or race.receipt.metric_publication_v2
                                != metric_publication_v2
                            ):
                                raise ModelEnsemblePersistenceError(
                                    "typed metric projection could not be stored"
                                ) from None
                            projected = race
                        if progress_callback is not None:
                            progress_callback(10, 10)
                        return SessionModelEnsembleOutcome(
                            run=projected,
                            applied=False,
                        )
                    # Provider event evidence is a second, content-free input
                    # plane. It may change while the bounded text window stays
                    # byte-identical, so a new run must be published instead
                    # of treating that measured change as version drift.
            if semantic_projection is None:
                semantic_projection, prior_semantic_units = (
                    self._reconcile_semantic_units(context, latest)
                )
            if (
                typed_metrics is None
                or metric_publication_v2 is None
                or projection_completed_at is None
            ):
                typed_evidence = self._bind_objective_opportunities(
                    typed_evidence,
                    semantic_projection,
                )
                (
                    typed_metrics,
                    metric_publication_v2,
                    projection_completed_at,
                ) = self._project_metrics(
                    context,
                    semantic_projection,
                    typed_evidence,
                )
            plan = build_ensemble_chunks(context)
            try:
                receipt = self._run_pipeline(
                    plan,
                    specs,
                    progress_callback=progress_callback,
                    prior_receipt=None if latest is None else latest.receipt,
                    typed_evidence=typed_evidence,
                )
                projected_receipt = SessionModelEnsembleReceipt.model_validate(
                    {
                        **receipt.model_dump(),
                        "metric_projection_version": (
                            MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION
                        ),
                        "metric_projection_completed_at": projection_completed_at,
                        "typed_metrics": typed_metrics,
                        "metric_publication_v2": metric_publication_v2,
                    }
                )
                record = SessionModelEnsembleRunRecord(
                    run_id=run_id,
                    session_id=session_id,
                    request_fingerprint=request_fingerprint,
                    input_fingerprint=context.analysis_window_fingerprint,
                    provider=provider,
                    provider_version=context.provider_version,
                    adapter_version=context.adapter_version,
                    source_schema_version=context.source_schema_version,
                    content_schema_version=context.content_schema_version,
                    redactor_version=context.redactor_version,
                    receipt=projected_receipt,
                )
            except SessionModelEnsembleError:
                raise
            except Exception:
                raise ModelEnsembleExecutionError(
                    "local model ensemble failed"
                ) from None
            try:
                save_arguments = {}
                if persistence_authority is not None:
                    save_arguments["authority"] = persistence_authority()
                if semantic_projection is not None:
                    save_arguments["semantic_units"] = (
                        semantic_projection.reconciliation
                    )
                self._repository.save_completed(record, **save_arguments)
            except Exception:
                race = self._safe_get(run_id)
                if race is not None:
                    if semantic_projection is not None:
                        try:
                            race_semantic = (
                                self._repository.get_semantic_unit_reconciliation(
                                    run_id
                                )
                            )
                        except Exception:
                            race_semantic = None
                        if race_semantic != semantic_projection.reconciliation:
                            raise ModelEnsemblePersistenceError(
                                "semantic-unit sidecar could not be stored"
                            ) from None
                    return SessionModelEnsembleOutcome(run=race, applied=False)
                raise ModelEnsemblePersistenceError(
                    "model ensemble result could not be stored"
                ) from None
            return SessionModelEnsembleOutcome(run=record, applied=True)

    def latest(self, session_id: str) -> SessionModelEnsembleRunRecord | None:
        if PSEUDONYM_PATTERN.fullmatch(session_id) is None:
            raise ModelEnsembleInputError("model ensemble selection is invalid")
        try:
            return self._repository.get_latest(session_id)
        except Exception:
            raise ModelEnsemblePersistenceError(
                "model ensemble results are unavailable"
            ) from None

    def get(self, run_id: str) -> SessionModelEnsembleRunRecord | None:
        """Load one exact sealed run without substituting a newer session run."""

        if PSEUDONYM_PATTERN.fullmatch(run_id) is None:
            raise ModelEnsembleInputError("model ensemble selection is invalid")
        return self._safe_get(run_id)

    def require_watchable(self, *, provider: Provider, session_id: str) -> None:
        """Validate standing local authority without reading session content."""

        if provider is not Provider.CODEX or PSEUDONYM_PATTERN.fullmatch(session_id) is None:
            raise ModelEnsembleInputError("model ensemble selection is invalid")
        self._enforce_access(provider, session_id)

    def _safe_get(self, run_id: str) -> SessionModelEnsembleRunRecord | None:
        try:
            return self._repository.get(run_id)
        except Exception:
            raise ModelEnsemblePersistenceError(
                "model ensemble persistence is unavailable"
            ) from None

    def _enforce_access(self, provider: Provider, session_id: str) -> None:
        try:
            consent = self._access_policy.has_active_consent(
                provider, DataTier.REDACTED_CONTENT
            )
        except Exception:
            raise ModelEnsembleConsentError(
                "redacted-content consent is unavailable"
            ) from None
        if not consent:
            raise ModelEnsembleConsentError("redacted-content consent is required")
        try:
            indexed = self._access_policy.selection_is_indexed(
                provider,
                project_ids=frozenset(),
                session_ids=frozenset((session_id,)),
            )
        except Exception:
            raise ModelEnsembleSelectionError("safe selection is unavailable") from None
        if not indexed:
            raise ModelEnsembleSelectionError(
                "session is not present in the safe index"
            )
        try:
            self._compatibility_policy.require_compatible(provider.value)
        except Exception:
            raise ModelEnsembleCompatibilityError(
                "provider compatibility is not verified"
            ) from None

    def _read_context(self, provider: Provider, session_id: str, max_messages: int):
        selection = TextAnalysisSelection(
            provider=provider,
            session_id=session_id,
            max_messages=max_messages,
            max_characters=COACHING_PROFILE_V1.max_characters,
        )
        grant = TextSourceAccessGrant(
            purpose=TextAnalysisPurpose.TEXT_ANALYSIS,
            provider=provider,
            session_id=session_id,
            data_tier=DataTier.REDACTED_CONTENT,
            per_run_confirmation_active=True,
            local_only=True,
            content_persistence_allowed=False,
        )
        try:
            source = self._source_factory(provider)
            context = source.read(
                selection=selection,
                grant=grant,
                task_profile=COACHING_PROFILE_V1.task_profile,
            )
        except TextSourceReadError as error:
            raise ModelEnsembleSourceError(error.reason) from None
        except Exception:
            raise ModelEnsembleSourceError(
                TextSourceFailureReason.PROVIDER_UNAVAILABLE
            ) from None
        if context.provider is not provider or context.session_id != session_id:
            raise ModelEnsembleSourceError(
                TextSourceFailureReason.PROVIDER_UNAVAILABLE
            )
        return context

    def _project_metrics(
        self,
        context: P1TextAnalysisInput,
        semantic_projection: SemanticUnitProjection | None,
        typed_evidence: EphemeralTypedEvidenceProjection | None = None,
    ) -> tuple[
        tuple[SessionModelEnsembleTypedMetricReceipt, ...],
        MetricPublicationV2,
        datetime,
    ]:
        grant = P1LocalAnalysisGrant(
            provider=context.provider,
            session_id=context.session_id,
            analysis_window_fingerprint=context.analysis_window_fingerprint,
            data_tier=DataTier.REDACTED_CONTENT,
            consent_active=True,
            local_only=True,
            content_persistence_allowed=False,
        )
        try:
            results = self._metric_engine.compute(
                context,
                grant,
                pack_key=COACHING_METRIC_PACK_KEY,
                pack_version=COACHING_METRIC_PACK_VERSION,
            )
            projected_at = self._clock()
            if projected_at.tzinfo is None or projected_at.utcoffset() != timedelta(0):
                raise ValueError("metric projection clock must return UTC")
            # Current code writes projection identity r3 only.  The frozen r2
            # producers stay importable for historical rows and for the tests
            # that prove they still answer exactly as they did.
            objective_overrides = project_objective_metric_overrides_v3(
                typed_evidence,
                self._objective_evidence_descriptor(),
            )
            live_states = project_metric_states_v3(
                context=context,
                reconciliation=(
                    None
                    if semantic_projection is None
                    else semantic_projection.reconciliation
                ),
                id_factory=self._identifiers,
                conversational_results={
                    item.observation.key: item for item in results
                },
                objective_overrides=objective_overrides,
            )
            metric_publication_v2 = publish_metric_states_v2(live_states)
            projected_items: list[SessionModelEnsembleTypedMetricReceipt] = []
            for result in results:
                objective_override = objective_overrides.get(result.observation.key)
                objective_eligible_count = (
                    0
                    if objective_override is None
                    else objective_override.eligible_opportunity_count
                )
                objective_observed_count = (
                    0
                    if objective_override is None
                    else objective_override.resolved_opportunity_count
                )
                projected_items.append(SessionModelEnsembleTypedMetricReceipt(
                    metric_key=result.observation.key,
                    metric_version=result.observation.version,
                    value_state=(
                        objective_override.value_state
                        if objective_override is not None
                        else result.value_state
                    ),
                    numerator=(
                        objective_override.numerator
                        if objective_override is not None
                        else None
                        if result.fraction is None
                        else result.fraction.numerator
                    ),
                    denominator=(
                        objective_override.denominator
                        if objective_override is not None
                        else None
                        if result.fraction is None
                        else result.fraction.denominator
                    ),
                    numeric_value=(
                        (
                            objective_override.numerator
                            / objective_override.denominator
                        )
                        if objective_override is not None
                        and objective_override.numerator is not None
                        and objective_override.denominator is not None
                        else None
                        if objective_override is not None
                        else result.observation.numeric_value
                    ),
                    observed_message_count=(
                        objective_observed_count
                        if objective_override is not None
                        else result.observation.observed_count
                    ),
                    eligible_message_count=(
                        objective_eligible_count
                        if objective_override is not None
                        else result.observation.eligible_count
                    ),
                    coverage=(
                        (
                            0.0
                            if objective_eligible_count == 0
                            else objective_observed_count
                            / objective_eligible_count
                        )
                        if objective_override is not None
                        else result.observation.coverage
                    ),
                    explanation_code=(
                        objective_override.explanation_code
                        if objective_override is not None
                        else result.explanation_code
                    ),
                    error_code=(
                        None
                        if objective_override is not None
                        else result.error_code
                    ),
                    projection_source="deterministic_typed_contract",
                    metric_schema_version=result.provenance.metric_schema_version,
                    engine_version=(
                        "typed-objective-evidence-v2"
                        if objective_override is not None
                        else self._metric_engine.engine_version
                    ),
                    algorithm_id=(
                        "typed-objective-evidence"
                        if objective_override is not None
                        else result.provenance.algorithm_id
                    ),
                    algorithm_version=(
                        "2"
                        if objective_override is not None
                        else result.provenance.algorithm_version
                    ),
                    rubric_version=(
                        "objective-evidence-no-rubric-v2"
                        if objective_override is not None
                        else self._metric_engine.rubric_version
                    ),
                    calibration_state="not_assessed",
                    product_metric_eligible=False,
                ))
            projected = tuple(projected_items)
        except SessionModelEnsembleError:
            raise
        except Exception:
            raise ModelEnsembleExecutionError(
                "typed local metric projection failed"
            ) from None
        return projected, metric_publication_v2, projected_at

    def _project_typed_evidence(
        self,
        provider: Provider,
        session_id: str,
    ) -> EphemeralTypedEvidenceProjection | None:
        if self._typed_evidence_projector is None:
            return None
        try:
            projection = self._typed_evidence_projector.project(
                provider=provider,
                session_id=session_id,
            )
            if projection is None:
                return None
            if (
                projection.session_id != session_id
                or projection.provenance.provider is not provider
            ):
                raise ValueError("typed evidence belongs to another session")
            validate_projection_descriptor(
                projection,
                self._typed_evidence_projector.descriptor,
            )
            return projection
        except Exception:
            # The safe metadata bridge is additive. Losing it must withhold
            # objective measurements, never discard deterministic text output.
            return None

    def _objective_evidence_descriptor(self) -> DecoderDescriptor | None:
        if self._typed_evidence_projector is None:
            return None
        try:
            descriptor = self._typed_evidence_projector.descriptor
            return descriptor if isinstance(descriptor, DecoderDescriptor) else None
        except Exception:
            return None

    def _bind_objective_opportunities(
        self,
        projection: EphemeralTypedEvidenceProjection | None,
        semantic_projection: SemanticUnitProjection | None,
    ) -> EphemeralTypedEvidenceProjection | None:
        try:
            return bind_semantic_unit_opportunities(
                projection,
                None
                if semantic_projection is None
                else semantic_projection.reconciliation,
                self._objective_evidence_descriptor(),
            )
        except Exception:
            # A semantic-link binding is optional objective authority. Any
            # mismatch withholds it without discarding deterministic metrics.
            return None

    def _reconcile_semantic_units(
        self,
        context: P1TextAnalysisInput,
        prior_run: SessionModelEnsembleRunRecord | None,
    ) -> tuple[SemanticUnitProjection | None, SemanticUnitReconciliation | None]:
        if self._semantic_unit_reconciler is None:
            return None, None
        prior: SemanticUnitReconciliation | None = None
        if prior_run is not None:
            try:
                prior = self._repository.get_semantic_unit_reconciliation(
                    prior_run.run_id
                )
            except Exception:
                raise ModelEnsemblePersistenceError(
                    "semantic-unit history is unavailable"
                ) from None
        try:
            projection = self._semantic_unit_reconciler.reconcile(
                context,
                prior_receipts=() if prior is None else prior.heads,
                include_ephemeral_evidence=False,
            )
        except Exception:
            raise ModelEnsembleExecutionError(
                "semantic-unit reconciliation failed"
            ) from None
        return projection, prior

    def _run_pipeline(
        self,
        plan: EnsembleChunkPlan,
        specs: tuple[EnsembleMetricSpec, ...],
        *,
        progress_callback: Callable[[int, int], None] | None,
        prior_receipt: SessionModelEnsembleReceipt | None,
        typed_evidence: EphemeralTypedEvidenceProjection | None,
    ) -> SessionModelEnsembleReceipt:
        if typed_evidence is None:
            if progress_callback is None and prior_receipt is None:
                return self._runner.run(plan, specs)
            if progress_callback is None:
                return self._runner.run(
                    plan,
                    specs,
                    prior_receipt=prior_receipt,
                )
            if prior_receipt is None:
                return self._runner.run(
                    plan,
                    specs,
                    progress_callback=progress_callback,
                )
            return self._runner.run(
                plan,
                specs,
                progress_callback=progress_callback,
                prior_receipt=prior_receipt,
            )
        return self._runner.run(
            plan,
            specs,
            progress_callback=progress_callback,
            prior_receipt=prior_receipt,
            typed_evidence=typed_evidence,
        )

    @staticmethod
    def _with_metric_projection(
        run: SessionModelEnsembleRunRecord,
        metrics: tuple[SessionModelEnsembleTypedMetricReceipt, ...],
        metric_publication_v2: MetricPublicationV2,
        completed_at: datetime,
    ) -> SessionModelEnsembleRunRecord:
        receipt = SessionModelEnsembleReceipt.model_validate(
            {
                **run.receipt.model_dump(),
                "metric_projection_version": MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION,
                "metric_projection_completed_at": completed_at,
                "typed_metrics": metrics,
                "metric_publication_v2": metric_publication_v2,
            }
        )
        return SessionModelEnsembleRunRecord.model_validate(
            {**run.model_dump(), "receipt": receipt}
        )


__all__ = [
    "LEGACY_MODEL_ENSEMBLE_CONFIRMATION",
    "MODEL_ENSEMBLE_CONFIRMATION",
    "ModelEnsembleCompatibilityError",
    "ModelEnsembleConfirmationError",
    "ModelEnsembleConsentError",
    "ModelEnsembleExecutionError",
    "ModelEnsembleInputError",
    "ModelEnsemblePersistenceError",
    "ModelEnsembleSelectionError",
    "ModelEnsembleSourceError",
    "SessionModelEnsembleError",
    "SessionModelEnsembleOutcome",
    "SessionModelEnsemblePersistenceAuthority",
    "SessionModelEnsembleRepository",
    "SessionModelEnsembleRunRecord",
    "SessionModelEnsembleRunner",
    "SessionModelEnsembleService",
    "SessionTypedEvidenceProjector",
]
