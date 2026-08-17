"""Explicit local measured and predictive analysis for one redacted session window."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Callable, Protocol

from pydantic import field_validator, model_validator

from ...domain import DataTier, PSEUDONYM_PATTERN, Provider, SAFE_VERSION_PATTERN, StrictModel
from .model_ensemble import (
    EnsembleChunkPlan,
    EnsembleMetricSpec,
    MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION,
    SessionModelEnsembleReceipt,
    SessionModelEnsembleTypedMetricReceipt,
    build_ensemble_chunks,
    coaching_ensemble_metric_specs,
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


MODEL_ENSEMBLE_CONFIRMATION = "run_ten_local_models_on_selected_redacted_text"
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
    ) -> SessionModelEnsembleReceipt: ...


class SessionModelEnsembleRepository(Protocol):
    def save_completed(
        self,
        run: SessionModelEnsembleRunRecord,
        *,
        authority: SessionModelEnsemblePersistenceAuthority | None = None,
    ) -> None: ...

    def get(self, run_id: str) -> SessionModelEnsembleRunRecord | None: ...

    def get_latest(self, session_id: str) -> SessionModelEnsembleRunRecord | None: ...

    def save_metric_projection(
        self,
        run: SessionModelEnsembleRunRecord,
        *,
        authority: SessionModelEnsemblePersistenceAuthority | None = None,
    ) -> None: ...

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
    """Run ten pinned local experts serially over one bounded redacted window."""

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
    ) -> None:
        self._access_policy = access_policy
        self._repository = repository
        self._source_factory = source_factory
        self._compatibility_policy = compatibility_policy
        self._identifiers = identifiers
        self._runner = runner
        self._metric_engine = metric_engine
        self._clock = clock
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
        if confirmation != MODEL_ENSEMBLE_CONFIRMATION:
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
            typed_metrics, projection_completed_at = self._project_metrics(context)
            latest: SessionModelEnsembleRunRecord | None = None
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
                if (
                    latest is not None
                    and latest.input_fingerprint == context.analysis_window_fingerprint
                    and latest.receipt.plan_fingerprint == current_plan_fingerprint
                ):
                    if (
                        latest.receipt.metric_projection_version
                        == MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION
                        and latest.receipt.typed_metrics == typed_metrics
                    ):
                        if progress_callback is not None:
                            progress_callback(10, 10)
                        return SessionModelEnsembleOutcome(run=latest, applied=False)
                    if latest.receipt.metric_projection_version is None:
                        projected = self._with_metric_projection(
                            latest,
                            typed_metrics,
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
                    # The same projection version must be deterministic for an
                    # identical source window.  Refuse to hide version drift.
                    raise ModelEnsembleExecutionError(
                        "typed metric projection identity changed without a version bump"
                    )
            plan = build_ensemble_chunks(context)
            try:
                if progress_callback is None and latest is None:
                    receipt = self._runner.run(plan, specs)
                elif progress_callback is None:
                    receipt = self._runner.run(
                        plan, specs, prior_receipt=latest.receipt
                    )
                elif latest is None:
                    receipt = self._runner.run(
                        plan, specs, progress_callback=progress_callback
                    )
                else:
                    receipt = self._runner.run(
                        plan,
                        specs,
                        progress_callback=progress_callback,
                        prior_receipt=latest.receipt,
                    )
                projected_receipt = SessionModelEnsembleReceipt.model_validate(
                    {
                        **receipt.model_dump(),
                        "metric_projection_version": (
                            MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION
                        ),
                        "metric_projection_completed_at": projection_completed_at,
                        "typed_metrics": typed_metrics,
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
                if persistence_authority is None:
                    self._repository.save_completed(record)
                else:
                    self._repository.save_completed(
                        record,
                        authority=persistence_authority(),
                    )
            except Exception:
                race = self._safe_get(run_id)
                if race is not None:
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
    ) -> tuple[tuple[SessionModelEnsembleTypedMetricReceipt, ...], datetime]:
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
            projected = tuple(
                SessionModelEnsembleTypedMetricReceipt(
                    metric_key=result.observation.key,
                    metric_version=result.observation.version,
                    value_state=result.value_state,
                    numerator=(
                        None if result.fraction is None else result.fraction.numerator
                    ),
                    denominator=(
                        None if result.fraction is None else result.fraction.denominator
                    ),
                    numeric_value=result.observation.numeric_value,
                    observed_message_count=result.observation.observed_count,
                    eligible_message_count=result.observation.eligible_count,
                    coverage=result.observation.coverage,
                    explanation_code=result.explanation_code,
                    error_code=result.error_code,
                    projection_source="deterministic_typed_contract",
                    metric_schema_version=result.provenance.metric_schema_version,
                    engine_version=self._metric_engine.engine_version,
                    algorithm_id=result.provenance.algorithm_id,
                    algorithm_version=result.provenance.algorithm_version,
                    rubric_version=self._metric_engine.rubric_version,
                    calibration_state="not_assessed",
                    product_metric_eligible=False,
                )
                for result in results
            )
        except SessionModelEnsembleError:
            raise
        except Exception:
            raise ModelEnsembleExecutionError(
                "typed local metric projection failed"
            ) from None
        return projected, projected_at

    @staticmethod
    def _with_metric_projection(
        run: SessionModelEnsembleRunRecord,
        metrics: tuple[SessionModelEnsembleTypedMetricReceipt, ...],
        completed_at: datetime,
    ) -> SessionModelEnsembleRunRecord:
        receipt = SessionModelEnsembleReceipt.model_validate(
            {
                **run.receipt.model_dump(),
                "metric_projection_version": MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION,
                "metric_projection_completed_at": completed_at,
                "typed_metrics": metrics,
            }
        )
        return SessionModelEnsembleRunRecord.model_validate(
            {**run.model_dump(), "receipt": receipt}
        )


__all__ = [
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
]
