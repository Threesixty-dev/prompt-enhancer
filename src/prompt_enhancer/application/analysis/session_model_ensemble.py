"""Explicit local ten-model shadow analysis for one redacted session window."""

from __future__ import annotations

import re
from threading import Lock
from typing import Callable, Protocol

from pydantic import field_validator, model_validator

from ...domain import DataTier, PSEUDONYM_PATTERN, Provider, SAFE_VERSION_PATTERN, StrictModel
from .model_ensemble import (
    EnsembleChunkPlan,
    EnsembleMetricSpec,
    SessionModelEnsembleReceipt,
    build_ensemble_chunks,
    coaching_ensemble_metric_specs,
)
from .session_text_service import (
    SessionTextAnalysisAccessPolicy,
    SessionTextAnalysisCompatibilityPolicy,
    SessionTextAnalysisIdFactory,
    SessionTextAnalysisSourceFactory,
)
from .text_analysis_presets import COACHING_PROFILE_V1
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


class SessionModelEnsembleRunner(Protocol):
    def run(
        self,
        chunk_plan: EnsembleChunkPlan,
        metric_specs: tuple[EnsembleMetricSpec, ...],
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        prior_receipt: SessionModelEnsembleReceipt | None = None,
    ) -> SessionModelEnsembleReceipt: ...


class SessionModelEnsembleRepository(Protocol):
    def save_completed(self, run: SessionModelEnsembleRunRecord) -> None: ...

    def get(self, run_id: str) -> SessionModelEnsembleRunRecord | None: ...

    def get_latest(self, session_id: str) -> SessionModelEnsembleRunRecord | None: ...

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
    ) -> None:
        self._access_policy = access_policy
        self._repository = repository
        self._source_factory = source_factory
        self._compatibility_policy = compatibility_policy
        self._identifiers = identifiers
        self._runner = runner
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
    ) -> SessionModelEnsembleOutcome:
        if (
            provider is not Provider.CODEX
            or PSEUDONYM_PATTERN.fullmatch(session_id) is None
            or _IDEMPOTENCY.fullmatch(idempotency_key) is None
            or not isinstance(max_messages, int)
            or isinstance(max_messages, bool)
            or not 1 <= max_messages <= COACHING_PROFILE_V1.max_messages
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
            latest: SessionModelEnsembleRunRecord | None = None
            if reuse_latest:
                try:
                    latest = self._repository.get_latest(session_id)
                except Exception:
                    raise ModelEnsemblePersistenceError(
                        "model ensemble results are unavailable"
                    ) from None
                if (
                    latest is not None
                    and latest.input_fingerprint
                    == context.analysis_window_fingerprint
                ):
                    if progress_callback is not None:
                        progress_callback(10, 10)
                    return SessionModelEnsembleOutcome(run=latest, applied=False)
            plan = build_ensemble_chunks(context)
            specs = coaching_ensemble_metric_specs()
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
                    receipt=receipt,
                )
            except SessionModelEnsembleError:
                raise
            except Exception:
                raise ModelEnsembleExecutionError(
                    "local model ensemble failed"
                ) from None
            try:
                self._repository.save_completed(record)
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
    "SessionModelEnsembleRepository",
    "SessionModelEnsembleRunRecord",
    "SessionModelEnsembleRunner",
    "SessionModelEnsembleService",
]
