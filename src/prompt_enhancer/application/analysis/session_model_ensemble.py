"""Explicit local measured and predictive analysis for one redacted session window."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Callable, Literal, Protocol

from pydantic import field_validator, model_validator

from ...domain import DataTier, PSEUDONYM_PATTERN, Provider, SAFE_VERSION_PATTERN, StrictModel
from ..providers import DecoderDescriptor
from .evidence_contracts import (
    EphemeralTypedEvidenceProjection,
    validate_projection_descriptor,
)
from .declared_task_profiles import (
    DeclaredTaskProfileRecord,
    DeclaredTaskProfileRepository,
    apply_declared_task_profile,
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
from .metric_lifecycle_evidence import MetricLifecycleEvidenceSnapshot
from .metric_projection_v2 import (
    METRIC_PROJECTION_V2_VERSION_5,
    METRIC_PROJECTION_V2_VERSION_6,
)
from .metric_projection_v6 import project_metric_states_v6
from .metric_publication_v2 import MetricPublicationV2, publish_metric_states_v2
from .provider_evidence import bind_semantic_unit_opportunities
from .requirement_plan_evidence import (
    InMemoryRequirementPlanReviewContextStore,
    RequirementPlanEvidenceSnapshot,
)
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
from .text_contracts import P1LocalAnalysisGrant, P1TextAnalysisInput, TextTaskProfile
from .text_source import (
    TEXT_ANALYSIS_PROVIDERS,
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
COACHING_PROFILE_V1_UNCONFIGURED_SCHEMA_VERSION = (
    "coaching-profile-v1-unconfigured"
)
COACHING_PROFILE_V1_UNCONFIGURED_POLICY_VERSION = "server-preset-v1"
REQUIREMENT_PLAN_UNAVAILABLE_SCHEMA_VERSION = "requirement-plan-unavailable-v1"
REQUIREMENT_PLAN_AWAITING_REVIEW_SCHEMA_VERSION = (
    "requirement-plan-awaiting-review-v1"
)
REQUIREMENT_PLAN_UNAVAILABLE_POLICY_VERSION = "reviewed-requirement-plan-v1"


def requirement_plan_unavailable_fingerprint() -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "binding_contract": "requirement-plan-binding-v1",
                "source": "unavailable",
                "schema_version": REQUIREMENT_PLAN_UNAVAILABLE_SCHEMA_VERSION,
                "policy_version": REQUIREMENT_PLAN_UNAVAILABLE_POLICY_VERSION,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT = (
    "30f6b309825c563a881ed1b7587072222e3cb33ca70f7bff274ba968cb067641"
)
if requirement_plan_unavailable_fingerprint() != REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT:
    raise RuntimeError(
        "requirement-plan unavailable marker changed without a new identity"
    )


def requirement_plan_awaiting_review_fingerprint() -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "binding_contract": "requirement-plan-binding-v1",
                "source": "awaiting_review",
                "schema_version": REQUIREMENT_PLAN_AWAITING_REVIEW_SCHEMA_VERSION,
                "policy_version": REQUIREMENT_PLAN_UNAVAILABLE_POLICY_VERSION,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


REQUIREMENT_PLAN_AWAITING_REVIEW_FINGERPRINT = (
    "843a2a5154affde7f7cddc19137dfcdfa8253d9f541c98b6e2cdabd930401ff2"
)
if (
    requirement_plan_awaiting_review_fingerprint()
    != REQUIREMENT_PLAN_AWAITING_REVIEW_FINGERPRINT
):
    raise RuntimeError(
        "requirement-plan awaiting-review marker changed without a new identity"
    )


def coaching_profile_v1_unconfigured_fingerprint() -> str:
    """Hash every fixed field that gives the unconfigured preset meaning."""

    preset = COACHING_PROFILE_V1
    payload = {
        "fingerprint_contract": "coaching-profile-binding-v1",
        "preset_id": preset.preset_id.value,
        "analysis_profile_key": preset.analysis_profile_key,
        "analysis_profile_version": preset.analysis_profile_version,
        "metric_pack_key": preset.metric_pack_key,
        "metric_pack_version": preset.metric_pack_version,
        "task_profile": preset.task_profile.model_dump(mode="json"),
        "max_messages": preset.max_messages,
        "max_characters": preset.max_characters,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


COACHING_PROFILE_V1_UNCONFIGURED_FINGERPRINT = (
    "4cf952d189fd817c3959540a18538b76b161aa3a03d810cb967cafc7f284be71"
)
if (
    coaching_profile_v1_unconfigured_fingerprint()
    != COACHING_PROFILE_V1_UNCONFIGURED_FINGERPRINT
):
    raise RuntimeError(
        "COACHING_PROFILE_V1 changed without a new profile-binding identity"
    )


def _pseudonym(value: str) -> str:
    if PSEUDONYM_PATTERN.fullmatch(value) is None:
        raise ValueError("identifier must be a local pseudonym")
    return value


def _safe_code(value: str) -> str:
    if SAFE_VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("provenance value is invalid")
    return value


class MetricProfileSource(StrEnum):
    """Closed authority vocabulary for a measured r5 denominator profile."""

    COACHING_PROFILE_V1_UNCONFIGURED = "coaching_profile_v1_unconfigured"
    DECLARED_TASK_PROFILE = "declared_task_profile"


@dataclass(frozen=True, slots=True)
class _ResolvedMetricProfile:
    task_profile: TextTaskProfile
    declaration: DeclaredTaskProfileRecord | None

    @property
    def source(self) -> MetricProfileSource:
        return (
            MetricProfileSource.COACHING_PROFILE_V1_UNCONFIGURED
            if self.declaration is None
            else MetricProfileSource.DECLARED_TASK_PROFILE
        )

    def request_identity(self) -> tuple[str, ...]:
        declaration = self.declaration
        if declaration is None:
            return (
                self.source.value,
                "none",
                "none",
                COACHING_PROFILE_V1_UNCONFIGURED_FINGERPRINT,
                COACHING_PROFILE_V1_UNCONFIGURED_SCHEMA_VERSION,
                COACHING_PROFILE_V1_UNCONFIGURED_POLICY_VERSION,
            )
        return (
            self.source.value,
            declaration.profile_id,
            str(declaration.revision),
            declaration.profile_fingerprint,
            declaration.schema_version,
            declaration.policy_version,
        )


class SessionMetricProfileBinding(StrictModel):
    """Content-free, exact profile provenance for one measured source window."""

    profile_source: MetricProfileSource
    provider: Provider
    session_id: str
    source_window_fingerprint: str
    profile_id: str | None = None
    profile_revision: int | None = None
    profile_fingerprint: str
    profile_schema_version: str
    profile_policy_version: str
    bound_at: datetime
    local_only: bool = True
    content_persisted: bool = False

    _ids = field_validator(
        "session_id",
        "source_window_fingerprint",
        "profile_fingerprint",
    )(_pseudonym)
    _codes = field_validator(
        "profile_schema_version",
        "profile_policy_version",
    )(_safe_code)

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, value: str | None) -> str | None:
        return None if value is None else _pseudonym(value)

    @field_validator("profile_revision")
    @classmethod
    def validate_profile_revision(cls, value: int | None) -> int | None:
        if value is not None and (
            isinstance(value, bool) or not 1 <= value <= 1_000_000
        ):
            raise ValueError("profile revision is invalid")
        return value

    @field_validator("bound_at")
    @classmethod
    def validate_bound_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("profile binding timestamp must be UTC")
        return value

    @model_validator(mode="after")
    def validate_profile_authority(self) -> "SessionMetricProfileBinding":
        if not self.local_only or self.content_persisted:
            raise ValueError("metric profile bindings are content-free local metadata")
        if self.profile_source is MetricProfileSource.DECLARED_TASK_PROFILE:
            if self.profile_id is None or self.profile_revision is None:
                raise ValueError("declared task profile identity is incomplete")
            if (
                self.profile_schema_version != "declared-task-profile-v1"
                or self.profile_policy_version != "authenticated-local-user-v1"
            ):
                raise ValueError("declared task profile provenance is invalid")
        else:
            if self.profile_id is not None or self.profile_revision is not None:
                raise ValueError("the unconfigured preset has no declared revision")
            if (
                self.profile_fingerprint
                != COACHING_PROFILE_V1_UNCONFIGURED_FINGERPRINT
                or self.profile_schema_version
                != COACHING_PROFILE_V1_UNCONFIGURED_SCHEMA_VERSION
                or self.profile_policy_version
                != COACHING_PROFILE_V1_UNCONFIGURED_POLICY_VERSION
            ):
                raise ValueError("unconfigured coaching profile marker is invalid")
        return self


class RequirementPlanEvidenceSource(StrEnum):
    UNAVAILABLE = "unavailable"
    AWAITING_REVIEW = "awaiting_review"
    REVIEWED_REQUIREMENT_PLAN = "reviewed_requirement_plan"


@dataclass(frozen=True, slots=True)
class _ResolvedRequirementPlanEvidence:
    snapshot: RequirementPlanEvidenceSnapshot | None
    evidence_source: RequirementPlanEvidenceSource
    evidence_fingerprint: str

    def request_identity(self) -> tuple[str, ...]:
        snapshot = self.snapshot
        if (
            self.evidence_source
            is not RequirementPlanEvidenceSource.REVIEWED_REQUIREMENT_PLAN
        ):
            awaiting = (
                self.evidence_source
                is RequirementPlanEvidenceSource.AWAITING_REVIEW
            )
            return (
                self.evidence_source.value,
                "none",
                "none",
                (
                    REQUIREMENT_PLAN_AWAITING_REVIEW_FINGERPRINT
                    if awaiting
                    else REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT
                ),
                (
                    REQUIREMENT_PLAN_AWAITING_REVIEW_SCHEMA_VERSION
                    if awaiting
                    else REQUIREMENT_PLAN_UNAVAILABLE_SCHEMA_VERSION
                ),
                REQUIREMENT_PLAN_UNAVAILABLE_POLICY_VERSION,
            )
        if snapshot is None or snapshot.confirmation_id is None:
            raise AssertionError("reviewed requirement-plan evidence is absent")
        return (
            RequirementPlanEvidenceSource.REVIEWED_REQUIREMENT_PLAN.value,
            snapshot.confirmation_id,
            snapshot.proposal_id or "none",
            self.evidence_fingerprint,
            snapshot.schema_version,
            snapshot.policy_version,
            snapshot.source_window_fingerprint,
        )


class SessionRequirementPlanEvidenceBinding(StrictModel):
    """Exact content-free requirement-plan authority used by one r6 run."""

    evidence_source: RequirementPlanEvidenceSource
    session_id: str
    source_window_fingerprint: str
    confirmation_id: str | None = None
    proposal_id: str | None = None
    evidence_fingerprint: str
    evidence_schema_version: str
    evidence_policy_version: str
    bound_at: datetime
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False

    _ids = field_validator(
        "session_id", "source_window_fingerprint", "evidence_fingerprint"
    )(_pseudonym)
    _codes = field_validator(
        "evidence_schema_version", "evidence_policy_version"
    )(_safe_code)

    @field_validator("confirmation_id", "proposal_id")
    @classmethod
    def optional_authority_id(cls, value: str | None) -> str | None:
        return None if value is None else _pseudonym(value)

    @field_validator("bound_at")
    @classmethod
    def utc_bound_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("requirement-plan binding timestamp must be UTC")
        return value

    @model_validator(mode="after")
    def exact_authority(self) -> "SessionRequirementPlanEvidenceBinding":
        if self.evidence_source is RequirementPlanEvidenceSource.UNAVAILABLE:
            if (
                self.confirmation_id is not None
                or self.proposal_id is not None
                or self.evidence_fingerprint
                != REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT
                or self.evidence_schema_version
                != REQUIREMENT_PLAN_UNAVAILABLE_SCHEMA_VERSION
                or self.evidence_policy_version
                != REQUIREMENT_PLAN_UNAVAILABLE_POLICY_VERSION
            ):
                raise ValueError("unavailable requirement-plan marker is invalid")
        elif self.evidence_source is RequirementPlanEvidenceSource.AWAITING_REVIEW:
            if (
                self.confirmation_id is not None
                or self.proposal_id is not None
                or self.evidence_fingerprint
                != REQUIREMENT_PLAN_AWAITING_REVIEW_FINGERPRINT
                or self.evidence_schema_version
                != REQUIREMENT_PLAN_AWAITING_REVIEW_SCHEMA_VERSION
                or self.evidence_policy_version
                != REQUIREMENT_PLAN_UNAVAILABLE_POLICY_VERSION
            ):
                raise ValueError("awaiting-review requirement-plan marker is invalid")
        elif (
            self.confirmation_id is None
            or self.proposal_id is None
            or self.evidence_fingerprint
            in {
                REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT,
                REQUIREMENT_PLAN_AWAITING_REVIEW_FINGERPRINT,
            }
            or self.evidence_schema_version != "requirement-plan-evidence-v1"
            or self.evidence_policy_version != "reviewed-requirement-plan-v1"
        ):
            raise ValueError("reviewed requirement-plan authority is incomplete")
        return self


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
    metric_profile_binding: SessionMetricProfileBinding | None = None
    requirement_plan_evidence_binding: (
        SessionRequirementPlanEvidenceBinding | None
    ) = None
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
        binding = self.metric_profile_binding
        if binding is not None and (
            binding.provider is not self.provider
            or binding.session_id != self.session_id
            or binding.source_window_fingerprint != self.input_fingerprint
        ):
            raise ValueError("metric profile is bound to another source window")
        publication = self.receipt.metric_publication_v2
        if publication is not None:
            if publication.projection_version in {
                METRIC_PROJECTION_V2_VERSION_5,
                METRIC_PROJECTION_V2_VERSION_6,
            }:
                if binding is None:
                    raise ValueError("current metric publication requires a profile binding")
            elif binding is not None:
                raise ValueError("legacy metric publication cannot carry an r5 profile")
            evidence_binding = self.requirement_plan_evidence_binding
            if publication.projection_version == METRIC_PROJECTION_V2_VERSION_6:
                if evidence_binding is None:
                    raise ValueError(
                        "r6 metric publication requires a requirement-plan binding"
                    )
                if (
                    evidence_binding.session_id != self.session_id
                    or evidence_binding.source_window_fingerprint
                    != self.input_fingerprint
                ):
                    raise ValueError(
                        "requirement-plan evidence is bound to another source window"
                    )
            elif evidence_binding is not None:
                raise ValueError(
                    "legacy metric publication cannot carry requirement-plan authority"
                )
        elif self.requirement_plan_evidence_binding is not None:
            raise ValueError("a run without a metric publication has no evidence binding")
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


class SessionMetricLifecycleEvidenceReader(Protocol):
    """Content-free confirmed lifecycle receipts for one exact source window."""

    def snapshot(
        self,
        session_id: str,
        source_window_fingerprint: str,
    ) -> MetricLifecycleEvidenceSnapshot: ...


class SessionRequirementPlanEvidenceReader(Protocol):
    """Latest content-free reviewed requirement-plan authority for a session."""

    def latest_snapshot(self, session_id: str) -> RequirementPlanEvidenceSnapshot: ...


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
        lifecycle_evidence_reader: SessionMetricLifecycleEvidenceReader | None = None,
        declared_task_profile_reader: DeclaredTaskProfileRepository | None = None,
        requirement_plan_evidence_reader: (
            SessionRequirementPlanEvidenceReader | None
        ) = None,
        requirement_plan_review_contexts: (
            InMemoryRequirementPlanReviewContextStore | None
        ) = None,
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
        self._lifecycle_evidence_reader = lifecycle_evidence_reader
        self._declared_task_profile_reader = declared_task_profile_reader
        self._requirement_plan_evidence_reader = requirement_plan_evidence_reader
        self._requirement_plan_review_contexts = requirement_plan_review_contexts
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
            # Migration 51 widened the ensemble tables to the text analysis providers.
            provider not in TEXT_ANALYSIS_PROVIDERS
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
        with self._lock:
            self._enforce_access(provider, session_id)
            resolved_profile = self._resolve_metric_profile(provider, session_id)
            resolved_requirement_plan = self._resolve_requirement_plan_evidence(
                session_id
            )
            request_fingerprint = self._identifiers.fingerprint(
                "session-model-ensemble-request-v4",
                (
                    provider.value,
                    session_id,
                    idempotency_key,
                    MODEL_ENSEMBLE_POLICY_VERSION,
                    str(max_messages),
                    *resolved_profile.request_identity(),
                    *resolved_requirement_plan.request_identity(),
                ),
            )
            run_id = self._identifiers.fingerprint(
                "session-model-ensemble-run-v1",
                (session_id, request_fingerprint),
            )
            existing = self._safe_get(run_id)
            if existing is not None:
                return SessionModelEnsembleOutcome(run=existing, applied=False)
            context = self._read_context(
                provider,
                session_id,
                max_messages,
                resolved_profile.task_profile,
            )
            metric_profile_binding = self._bind_metric_profile(
                resolved_profile,
                context,
            )
            (
                requirement_plan_binding,
                requirement_plan_evidence,
            ) = self._bind_requirement_plan_evidence(
                resolved_requirement_plan,
                context,
            )
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
                    and self._metric_profile_identity_matches(
                        latest.metric_profile_binding,
                        metric_profile_binding,
                    )
                    and self._requirement_plan_identity_matches(
                        latest.requirement_plan_evidence_binding,
                        requirement_plan_binding,
                    )
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
                    requirement_plan_evidence,
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
                        self._publish_requirement_plan_review_context(
                            latest.run_id, context
                        )
                        return SessionModelEnsembleOutcome(run=latest, applied=False)
                    if latest.receipt.metric_projection_version is None:
                        projected = self._with_metric_projection(
                            latest,
                            typed_metrics,
                            metric_publication_v2,
                            projection_completed_at,
                            metric_profile_binding,
                            requirement_plan_binding,
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
                        self._publish_requirement_plan_review_context(
                            projected.run_id, context
                        )
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
                    requirement_plan_evidence,
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
                    metric_profile_binding=metric_profile_binding,
                    requirement_plan_evidence_binding=(
                        requirement_plan_binding
                    ),
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
                    self._publish_requirement_plan_review_context(
                        race.run_id, context
                    )
                    return SessionModelEnsembleOutcome(run=race, applied=False)
                raise ModelEnsemblePersistenceError(
                    "model ensemble result could not be stored"
                ) from None
            self._publish_requirement_plan_review_context(record.run_id, context)
            return SessionModelEnsembleOutcome(run=record, applied=True)

    def _publish_requirement_plan_review_context(
        self, run_id: str, context: P1TextAnalysisInput
    ) -> None:
        store = self._requirement_plan_review_contexts
        if store is None:
            return
        try:
            store.publish(run_id, context)
        except Exception:
            raise ModelEnsemblePersistenceError(
                "ephemeral requirement-plan review context could not be prepared"
            ) from None

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

        if provider not in TEXT_ANALYSIS_PROVIDERS or PSEUDONYM_PATTERN.fullmatch(session_id) is None:
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

    def _resolve_metric_profile(
        self,
        provider: Provider,
        session_id: str,
    ) -> _ResolvedMetricProfile:
        reader = self._declared_task_profile_reader
        if reader is None:
            return _ResolvedMetricProfile(
                task_profile=COACHING_PROFILE_V1.task_profile,
                declaration=None,
            )
        try:
            declaration = reader.get_latest(provider, session_id)
        except Exception:
            raise ModelEnsemblePersistenceError(
                "reviewed task profile is unavailable"
            ) from None
        if declaration is None:
            return _ResolvedMetricProfile(
                task_profile=COACHING_PROFILE_V1.task_profile,
                declaration=None,
            )
        if (
            declaration.provider is not provider
            or declaration.session_id != session_id
        ):
            raise ModelEnsemblePersistenceError(
                "reviewed task profile is bound to another session"
            )
        try:
            task_profile = apply_declared_task_profile(
                COACHING_PROFILE_V1.task_profile,
                declaration,
            )
        except (TypeError, ValueError):
            raise ModelEnsemblePersistenceError(
                "reviewed task profile is invalid"
            ) from None
        return _ResolvedMetricProfile(
            task_profile=task_profile,
            declaration=declaration,
        )

    def _bind_metric_profile(
        self,
        resolved: _ResolvedMetricProfile,
        context: P1TextAnalysisInput,
    ) -> SessionMetricProfileBinding:
        declaration = resolved.declaration
        try:
            return SessionMetricProfileBinding(
                profile_source=resolved.source,
                provider=context.provider,
                session_id=context.session_id,
                source_window_fingerprint=context.analysis_window_fingerprint,
                profile_id=(None if declaration is None else declaration.profile_id),
                profile_revision=(
                    None if declaration is None else declaration.revision
                ),
                profile_fingerprint=(
                    COACHING_PROFILE_V1_UNCONFIGURED_FINGERPRINT
                    if declaration is None
                    else declaration.profile_fingerprint
                ),
                profile_schema_version=(
                    COACHING_PROFILE_V1_UNCONFIGURED_SCHEMA_VERSION
                    if declaration is None
                    else declaration.schema_version
                ),
                profile_policy_version=(
                    COACHING_PROFILE_V1_UNCONFIGURED_POLICY_VERSION
                    if declaration is None
                    else declaration.policy_version
                ),
                bound_at=self._clock(),
                local_only=True,
                content_persisted=False,
            )
        except (TypeError, ValueError):
            raise ModelEnsemblePersistenceError(
                "metric profile binding could not be issued"
            ) from None

    def _resolve_requirement_plan_evidence(
        self,
        session_id: str,
    ) -> _ResolvedRequirementPlanEvidence:
        reader = self._requirement_plan_evidence_reader
        if reader is None:
            return _ResolvedRequirementPlanEvidence(
                snapshot=None,
                evidence_source=RequirementPlanEvidenceSource.UNAVAILABLE,
                evidence_fingerprint=REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT,
            )
        try:
            snapshot = reader.latest_snapshot(session_id)
        except Exception:
            raise ModelEnsemblePersistenceError(
                "reviewed requirement-plan evidence is unavailable"
            ) from None
        if snapshot.session_id != session_id:
            raise ModelEnsemblePersistenceError(
                "reviewed requirement-plan evidence belongs elsewhere"
            )
        if not snapshot.complete_user_clause_classification:
            return _ResolvedRequirementPlanEvidence(
                snapshot=snapshot,
                evidence_source=RequirementPlanEvidenceSource.AWAITING_REVIEW,
                evidence_fingerprint=(
                    REQUIREMENT_PLAN_AWAITING_REVIEW_FINGERPRINT
                ),
            )
        try:
            fingerprint = self._identifiers.fingerprint(
                "requirement-plan-evidence-snapshot-v1",
                (
                    snapshot.session_id,
                    snapshot.source_window_fingerprint,
                    snapshot.confirmation_id or "none",
                    snapshot.proposal_id or "none",
                    snapshot.schema_version,
                    snapshot.policy_version,
                    snapshot.review_rubric_version or "none",
                    *(
                        ()
                        if snapshot.producer_receipt is None
                        else (
                            f"producer-kind:{snapshot.producer_receipt.kind}",
                            "producer-claim:"
                            f"{snapshot.producer_receipt.claim_fingerprint}",
                            "producer-authority:"
                            f"{snapshot.producer_receipt.authority}",
                            "producer-raw-claim-persisted:"
                            f"{str(snapshot.producer_receipt.raw_claim_persisted).lower()}",
                        )
                    ),
                    *(
                        f"plan:{item.plan_id}:{item.coordinate.message_sequence}:"
                        f"{item.coordinate.clause_index}"
                        for item in snapshot.plan_items
                    ),
                    *(
                        f"requirement:{item.requirement_id}:"
                        f"{item.coordinate.message_sequence}:"
                        f"{item.coordinate.clause_index}:{item.disposition.value}:"
                        f"{','.join(item.linked_plan_ids)}"
                        for item in snapshot.requirements
                    ),
                    *(
                        "excluded-user-clause:"
                        f"{item.coordinate.message_sequence}:"
                        f"{item.coordinate.clause_index}:{item.reason.value}:"
                        f"{('none' if item.basis_coordinate is None else f'{item.basis_coordinate.message_sequence}:{item.basis_coordinate.clause_index}')}"
                        for item in snapshot.excluded_user_clauses
                    ),
                ),
            )
        except Exception:
            raise ModelEnsemblePersistenceError(
                "reviewed requirement-plan evidence is invalid"
            ) from None
        return _ResolvedRequirementPlanEvidence(
            snapshot=snapshot,
            evidence_source=RequirementPlanEvidenceSource.REVIEWED_REQUIREMENT_PLAN,
            evidence_fingerprint=fingerprint,
        )

    def _bind_requirement_plan_evidence(
        self,
        resolved: _ResolvedRequirementPlanEvidence,
        context: P1TextAnalysisInput,
    ) -> tuple[
        SessionRequirementPlanEvidenceBinding,
        RequirementPlanEvidenceSnapshot | None,
    ]:
        snapshot = resolved.snapshot
        reviewed = (
            snapshot
            if snapshot is not None
            and snapshot.complete_user_clause_classification
            and snapshot.source_window_fingerprint
            == context.analysis_window_fingerprint
            else None
        )
        try:
            if reviewed is None:
                service_available = (
                    resolved.evidence_source
                    is not RequirementPlanEvidenceSource.UNAVAILABLE
                )
                return (
                    SessionRequirementPlanEvidenceBinding(
                        evidence_source=(
                            RequirementPlanEvidenceSource.AWAITING_REVIEW
                            if service_available
                            else RequirementPlanEvidenceSource.UNAVAILABLE
                        ),
                        session_id=context.session_id,
                        source_window_fingerprint=(
                            context.analysis_window_fingerprint
                        ),
                        evidence_fingerprint=(
                            REQUIREMENT_PLAN_AWAITING_REVIEW_FINGERPRINT
                            if service_available
                            else REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT
                        ),
                        evidence_schema_version=(
                            REQUIREMENT_PLAN_AWAITING_REVIEW_SCHEMA_VERSION
                            if service_available
                            else REQUIREMENT_PLAN_UNAVAILABLE_SCHEMA_VERSION
                        ),
                        evidence_policy_version=(
                            REQUIREMENT_PLAN_UNAVAILABLE_POLICY_VERSION
                        ),
                        bound_at=self._clock(),
                    ),
                    (
                        RequirementPlanEvidenceSnapshot(
                            session_id=context.session_id,
                            source_window_fingerprint=(
                                context.analysis_window_fingerprint
                            ),
                        )
                        if service_available
                        else None
                    ),
                )
            return (
                SessionRequirementPlanEvidenceBinding(
                    evidence_source=(
                        RequirementPlanEvidenceSource.REVIEWED_REQUIREMENT_PLAN
                    ),
                    session_id=context.session_id,
                    source_window_fingerprint=context.analysis_window_fingerprint,
                    confirmation_id=reviewed.confirmation_id,
                    proposal_id=reviewed.proposal_id,
                    evidence_fingerprint=resolved.evidence_fingerprint,
                    evidence_schema_version=reviewed.schema_version,
                    evidence_policy_version=reviewed.policy_version,
                    bound_at=self._clock(),
                ),
                reviewed,
            )
        except (TypeError, ValueError):
            raise ModelEnsemblePersistenceError(
                "requirement-plan binding could not be issued"
            ) from None

    @staticmethod
    def _metric_profile_identity_matches(
        stored: SessionMetricProfileBinding | None,
        current: SessionMetricProfileBinding,
    ) -> bool:
        return stored is not None and stored.model_dump(
            exclude={"bound_at"}
        ) == current.model_dump(exclude={"bound_at"})

    @staticmethod
    def _requirement_plan_identity_matches(
        stored: SessionRequirementPlanEvidenceBinding | None,
        current: SessionRequirementPlanEvidenceBinding,
    ) -> bool:
        return stored is not None and stored.model_dump(
            exclude={"bound_at"}
        ) == current.model_dump(exclude={"bound_at"})

    def _read_context(
        self,
        provider: Provider,
        session_id: str,
        max_messages: int,
        task_profile: TextTaskProfile,
    ) -> P1TextAnalysisInput:
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
                task_profile=task_profile,
            )
        except TextSourceReadError as error:
            raise ModelEnsembleSourceError(error.reason) from None
        except Exception:
            raise ModelEnsembleSourceError(
                TextSourceFailureReason.PROVIDER_UNAVAILABLE
            ) from None
        if (
            context.provider is not provider
            or context.session_id != session_id
            or context.task_profile != task_profile
        ):
            raise ModelEnsembleSourceError(
                TextSourceFailureReason.PROVIDER_UNAVAILABLE
            )
        return context

    def _read_lifecycle_evidence(
        self,
        context: P1TextAnalysisInput,
    ) -> MetricLifecycleEvidenceSnapshot | None:
        if self._lifecycle_evidence_reader is None:
            return None
        try:
            snapshot = self._lifecycle_evidence_reader.snapshot(
                context.session_id,
                context.analysis_window_fingerprint,
            )
        except Exception:
            raise ModelEnsemblePersistenceError(
                "confirmed lifecycle evidence is unavailable"
            ) from None
        if (
            snapshot.session_id != context.session_id
            or snapshot.source_window_fingerprint
            != context.analysis_window_fingerprint
        ):
            raise ModelEnsemblePersistenceError(
                "confirmed lifecycle evidence is bound to another window"
            )
        return snapshot

    def _project_metrics(
        self,
        context: P1TextAnalysisInput,
        semantic_projection: SemanticUnitProjection | None,
        typed_evidence: EphemeralTypedEvidenceProjection | None = None,
        requirement_plan_evidence: RequirementPlanEvidenceSnapshot | None = None,
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
            # Current code writes projection identity r6 only. Frozen earlier
            # producers remain importable so historical rows retain the exact
            # meaning of the algorithm that wrote them.
            objective_overrides = project_objective_metric_overrides_v3(
                typed_evidence,
                self._objective_evidence_descriptor(context.provider),
            )
            live_states = project_metric_states_v6(
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
                lifecycle_evidence=self._read_lifecycle_evidence(context),
                requirement_plan_evidence=requirement_plan_evidence,
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
                self._objective_evidence_descriptor(provider),
            )
            return projection
        except Exception:
            # The safe metadata bridge is additive. Losing it must withhold
            # objective measurements, never discard deterministic text output.
            return None

    def _objective_evidence_descriptor(
        self, provider: Provider | None = None
    ) -> DecoderDescriptor | None:
        if self._typed_evidence_projector is None:
            return None
        try:
            descriptor_for = getattr(self._typed_evidence_projector, "descriptor_for", None)
            descriptor = (
                descriptor_for(provider)
                if provider is not None and callable(descriptor_for)
                else self._typed_evidence_projector.descriptor
            )
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
                self._objective_evidence_descriptor(
                    None if projection is None else projection.provenance.provider
                ),
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
        metric_profile_binding: SessionMetricProfileBinding,
        requirement_plan_evidence_binding: SessionRequirementPlanEvidenceBinding,
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
            {
                **run.model_dump(),
                "metric_profile_binding": metric_profile_binding,
                "requirement_plan_evidence_binding": (
                    requirement_plan_evidence_binding
                ),
                "receipt": receipt,
            }
        )


__all__ = [
    "COACHING_PROFILE_V1_UNCONFIGURED_FINGERPRINT",
    "COACHING_PROFILE_V1_UNCONFIGURED_POLICY_VERSION",
    "COACHING_PROFILE_V1_UNCONFIGURED_SCHEMA_VERSION",
    "coaching_profile_v1_unconfigured_fingerprint",
    "LEGACY_MODEL_ENSEMBLE_CONFIRMATION",
    "MODEL_ENSEMBLE_CONFIRMATION",
    "MetricProfileSource",
    "RequirementPlanEvidenceSource",
    "REQUIREMENT_PLAN_AWAITING_REVIEW_FINGERPRINT",
    "REQUIREMENT_PLAN_AWAITING_REVIEW_SCHEMA_VERSION",
    "REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT",
    "REQUIREMENT_PLAN_UNAVAILABLE_POLICY_VERSION",
    "REQUIREMENT_PLAN_UNAVAILABLE_SCHEMA_VERSION",
    "requirement_plan_awaiting_review_fingerprint",
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
    "SessionMetricProfileBinding",
    "SessionRequirementPlanEvidenceBinding",
    "SessionModelEnsembleRepository",
    "SessionModelEnsembleRunRecord",
    "SessionModelEnsembleRunner",
    "SessionModelEnsembleService",
    "SessionTypedEvidenceProjector",
]
