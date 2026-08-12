"""Content-free contracts for prospective temporal metric history.

These contracts deliberately do not infer revisions, metric selection, or values
from legacy rows.  A temporal series starts at a declared history floor and is
built only from immutable, directly observed receipts at or after that floor.

The models contain opaque digests, closed enums, bounded numbers, and short
path-free codes only.  Prompts, evidence text, model commentary, source paths,
URIs, and user-authored labels are outside this boundary.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
import hashlib
import json
import math
import re
from typing import Annotated, Any, Literal, TypeVar

from pydantic import ConfigDict, Field, field_validator, model_validator

from ...domain import PSEUDONYM_PATTERN, Provider, StrictModel


TEMPORAL_HISTORY_CONTRACT_VERSION = "temporal-history-v1"
SESSION_REVISION_RECEIPT_VERSION = "session-revision-receipt-v1"
TEMPORAL_OBSERVATION_BATCH_VERSION = "temporal-observation-batch-v1"
TEMPORAL_SNAPSHOT_SPEC_VERSION = "temporal-snapshot-spec-v1"
TEMPORAL_SNAPSHOT_RECEIPT_VERSION = "temporal-snapshot-receipt-v1"
COMPATIBILITY_BOUNDARY_VERSION = "compatibility-boundary-v1"
HALF_OPEN_WINDOW_BOUNDARY = "half_open_start_inclusive_end_exclusive"

MAX_LAST_N = 10_000
MAX_METRICS = 100
MAX_OBSERVATIONS = 100
MAX_COUNT = 9_007_199_254_740_991

_SAFE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")
_SAFE_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")

NonNegativeInt = Annotated[int, Field(strict=True, ge=0, le=MAX_COUNT)]
PositiveInt = Annotated[int, Field(strict=True, ge=1, le=MAX_COUNT)]
PersistenceModel = TypeVar("PersistenceModel", bound=StrictModel)


def _digest(value: str) -> str:
    if PSEUDONYM_PATTERN.fullmatch(value) is None:
        raise ValueError("value must be a lowercase SHA-256 identifier")
    return value


def _safe_code(value: str) -> str:
    if _SAFE_CODE_PATTERN.fullmatch(value) is None or ".." in value:
        raise ValueError("value must be a lowercase path-free content code")
    return value


def _optional_code(value: str | None) -> str | None:
    return None if value is None else _safe_code(value)


def _safe_version(value: str) -> str:
    if _SAFE_VERSION_PATTERN.fullmatch(value) is None or ".." in value:
        raise ValueError("value must be a path-free, URI-free version identifier")
    return value


def _optional_version(value: str | None) -> str | None:
    return None if value is None else _safe_version(value)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be canonical UTC")
    return value


def _finite(value: Any, *, field_name: str, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a JSON number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    if nonnegative and number < 0:
        raise ValueError(f"{field_name} must be non-negative")
    if number == 0 and math.copysign(1.0, number) < 0:
        raise ValueError(f"{field_name} cannot be negative zero")
    return number


def _probability(value: Any, *, field_name: str) -> float:
    number = _finite(value, field_name=field_name, nonnegative=True)
    if number > 1:
        raise ValueError(f"{field_name} must be between zero and one")
    return number


def _canonical_codes(
    values: tuple[str, ...], *, allow_empty: bool = False
) -> tuple[str, ...]:
    if not allow_empty and not values:
        raise ValueError("code set may not be empty")
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError("codes must be unique and sorted")
    return tuple(_safe_code(value) for value in values)


def _canonical_digests(
    values: tuple[str, ...], *, allow_empty: bool = False
) -> tuple[str, ...]:
    if not allow_empty and not values:
        raise ValueError("digest set may not be empty")
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError("digests must be unique and sorted")
    return tuple(_digest(value) for value in values)


def _canonical_digest(model: StrictModel) -> str:
    payload = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _plain_persistence_value(value: Any) -> Any:
    """Recursively discard trusted model instances before boundary validation."""

    if isinstance(value, StrictModel):
        return {
            field_name: _plain_persistence_value(getattr(value, field_name))
            for field_name in type(value).model_fields
        }
    if isinstance(value, dict):
        return {
            key: _plain_persistence_value(nested)
            for key, nested in value.items()
        }
    if isinstance(value, (tuple, list)):
        return tuple(_plain_persistence_value(nested) for nested in value)
    return value


def _revalidate_persistence_model(
    model_type: type[PersistenceModel], value: Any
) -> PersistenceModel:
    return model_type.model_validate(_plain_persistence_value(value))


class PersistenceRevalidatedModel(StrictModel):
    """Fail closed when nested frozen models cross a persistence boundary."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        revalidate_instances="always",
    )

    @model_validator(mode="before")
    @classmethod
    def recursively_revalidate_nested_models(cls, value: Any) -> Any:
        return _plain_persistence_value(value)

    @classmethod
    def revalidate_for_persistence(cls, value: Any) -> Any:
        """Revalidate plain values at every persistence read/write boundary."""

        return _revalidate_persistence_model(cls, value)


class TemporalWindowKind(StrEnum):
    LAST_N = "last_n"
    ROLLING_DAYS = "rolling_days"
    CUSTOM = "custom"


class HistoryCoverageState(StrEnum):
    COMPLETE = "complete"
    LEFT_CENSORED = "left_censored"
    PARTIAL = "partial"
    LEFT_CENSORED_PARTIAL = "left_censored_partial"
    NO_POST_FLOOR_OBSERVATIONS = "no_post_floor_observations"


class RevisionEffectiveTimeBasis(StrEnum):
    SESSION_ENDED_AT = "session_ended_at"
    REVISION_CAPTURED_AT = "revision_captured_at"


class SessionRevisionProvenance(StrEnum):
    DIRECT_ANALYSIS_WINDOW_RECEIPT = "direct_analysis_window_receipt"


class AnalysisWindowFingerprintBasis(StrEnum):
    CANONICAL_PROVIDER_EVENT_MANIFEST = "canonical_provider_event_manifest"


class TemporalSelectionState(StrEnum):
    SELECTED = "selected"
    NOT_SELECTED = "not_selected"
    SELECTION_UNKNOWN = "selection_unknown"


class TemporalScopeState(StrEnum):
    EXACT_SELECTION_RECEIPT = "exact_selection_receipt"
    NO_SELECTION_RECEIPT = "no_selection_receipt"


class TemporalSourceState(StrEnum):
    PRESENT = "present"
    NOT_REQUESTED = "not_requested"
    NO_POST_FLOOR_SOURCE = "no_post_floor_source"
    SOURCE_MISSING = "source_missing"
    SOURCE_FAILED = "source_failed"
    SOURCE_INCOMPATIBLE = "source_incompatible"


class TemporalValueState(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    ABSTAINED = "abstained"
    NOT_APPLICABLE = "not_applicable"
    FAILED = "failed"
    INCOMPATIBLE = "incompatible"


class TemporalValueKind(StrEnum):
    FRACTION = "fraction"
    COUNT_WITH_EXPOSURE = "count_with_exposure"
    DISTRIBUTION_SAMPLE = "distribution_sample"
    SAMPLED_PROPORTION = "sampled_proportion"


class TemporalAggregationSemantics(StrEnum):
    RATIO_OF_SUMS = "ratio_of_sums"
    COUNT_SUM_WITH_EXPOSURE = "count_sum_with_exposure"
    MEDIAN_AND_QUANTILES = "median_and_quantiles"
    PROPORTION_INTERVAL_FROM_SUMS = "proportion_interval_from_sums"


class TemporalTrendMethod(StrEnum):
    NONE = "none"
    ROLLING_MEDIAN = "rolling_median"
    EWMA = "ewma"


class MetricDirection(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    NEUTRAL = "neutral"


class EvidenceTier(StrEnum):
    METADATA = "metadata"
    REDACTED_CONTENT = "redacted_content"
    OBJECTIVE_ARTIFACT = "objective_artifact"
    HUMAN_ADJUDICATED = "human_adjudicated"


class EstimatorIdentityKind(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"


class EstimatorLifecycleState(StrEnum):
    PROVISIONAL = "provisional"
    ACTIVATED = "activated"
    RETIRED = "retired"


class ModelProviderKind(StrEnum):
    LOCAL = "local"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    SYNTHETIC = "synthetic"


class ArtifactIdentityState(StrEnum):
    PINNED_SHA256 = "pinned_sha256"
    PROVIDER_MANAGED_UNAVAILABLE = "provider_managed_unavailable"
    SYNTHETIC_NO_ARTIFACT = "synthetic_no_artifact"


class ReasoningEffort(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"
    ULTRA = "ultra"


class SnapshotAsOfSource(StrEnum):
    SERVER_CLOCK = "server_clock"


class SnapshotMetricCompatibilityState(StrEnum):
    COMPATIBLE = "compatible"
    DISCONTINUITY = "discontinuity"
    NO_COMPARABLE_OBSERVATIONS = "no_comparable_observations"


class MaterializationTrustState(StrEnum):
    UNTRUSTED_UNTIL_MATERIALIZED = "untrusted_until_materialized"


class CompatibilityDimension(StrEnum):
    METRIC_CONTRACT = "metric_contract"
    VALUE_SEMANTICS = "value_semantics"
    EVIDENCE_CONTRACT = "evidence_contract"
    ESTIMATOR_CONFIGURATION = "estimator_configuration"
    MODEL_IDENTITY = "model_identity"
    CALIBRATION = "calibration"
    PROVIDER_SCHEMA = "provider_schema"
    PRIVACY_REDACTOR = "privacy_redactor"


class TemporalWindowSpec(StrictModel):
    kind: TemporalWindowKind
    window_boundary_semantics: Literal[HALF_OPEN_WINDOW_BOUNDARY] = (
        HALF_OPEN_WINDOW_BOUNDARY
    )
    last_n: int | None = Field(default=None, strict=True, ge=1, le=MAX_LAST_N)
    days: int | None = Field(default=None, strict=True)
    start_at: datetime | None = None
    end_at: datetime | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def utc_optional(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)

    @model_validator(mode="after")
    def exact_shape(self) -> TemporalWindowSpec:
        if self.kind is TemporalWindowKind.LAST_N:
            if self.last_n is None or any(
                value is not None for value in (self.days, self.start_at, self.end_at)
            ):
                raise ValueError("last-N windows require only last_n")
        elif self.kind is TemporalWindowKind.ROLLING_DAYS:
            if self.days not in {7, 30, 90} or any(
                value is not None
                for value in (self.last_n, self.start_at, self.end_at)
            ):
                raise ValueError("rolling windows must be exactly 7, 30, or 90 days")
        elif (
            self.start_at is None
            or self.end_at is None
            or self.start_at >= self.end_at
            or self.last_n is not None
            or self.days is not None
        ):
            raise ValueError("custom windows require only an ordered UTC range")
        return self


class SessionRevisionReceipt(PersistenceRevalidatedModel):
    contract_version: Literal[SESSION_REVISION_RECEIPT_VERSION] = (
        SESSION_REVISION_RECEIPT_VERSION
    )
    revision_id: str
    project_id: str
    session_id: str
    revision_ordinal: PositiveInt
    predecessor_revision_id: str | None = None
    analysis_window_fingerprint: str
    analysis_window_fingerprint_basis: Literal[
        AnalysisWindowFingerprintBasis.CANONICAL_PROVIDER_EVENT_MANIFEST
    ] = AnalysisWindowFingerprintBasis.CANONICAL_PROVIDER_EVENT_MANIFEST
    analysis_window_fingerprint_version: str
    analysis_window_started_at: datetime
    analysis_window_ended_at: datetime
    effective_at: datetime
    captured_at: datetime
    effective_time_basis: RevisionEffectiveTimeBasis
    provenance: Literal[
        SessionRevisionProvenance.DIRECT_ANALYSIS_WINDOW_RECEIPT
    ] = SessionRevisionProvenance.DIRECT_ANALYSIS_WINDOW_RECEIPT
    legacy_inference_allowed: Literal[False] = False
    provider: Provider
    provider_adapter_version: str
    provider_schema_version: str
    source_schema_version: str
    content_schema_version: str
    redactor_version: str
    event_count: NonNegativeInt
    contains_local_content: Literal[False] = False
    remote_processing_allowed: Literal[False] = False
    private_export_allowed: Literal[False] = False
    team_share_allowed: Literal[False] = False

    _digests = field_validator(
        "revision_id",
        "project_id",
        "session_id",
        "analysis_window_fingerprint",
    )(_digest)
    _versions = field_validator(
        "provider_adapter_version",
        "analysis_window_fingerprint_version",
        "provider_schema_version",
        "source_schema_version",
        "content_schema_version",
        "redactor_version",
    )(_safe_version)
    _times = field_validator(
        "analysis_window_started_at",
        "analysis_window_ended_at",
        "effective_at",
        "captured_at",
    )(_utc)

    @field_validator("predecessor_revision_id")
    @classmethod
    def optional_predecessor(cls, value: str | None) -> str | None:
        return None if value is None else _digest(value)

    @model_validator(mode="after")
    def immutable_revision_shape(self) -> SessionRevisionReceipt:
        if self.analysis_window_started_at > self.analysis_window_ended_at:
            raise ValueError("analysis window timestamps must be ordered")
        if self.analysis_window_ended_at > self.captured_at:
            raise ValueError("analysis windows cannot end after capture")
        if self.effective_at > self.captured_at:
            raise ValueError("revision effective time cannot follow capture")
        if self.effective_time_basis is RevisionEffectiveTimeBasis.SESSION_ENDED_AT:
            if self.effective_at != self.analysis_window_ended_at:
                raise ValueError("ended-session revisions use the window end time")
        elif self.effective_at != self.captured_at:
            raise ValueError("open-session revisions use the capture time")
        if self.revision_ordinal == 1 and self.predecessor_revision_id is not None:
            raise ValueError("the first revision cannot have a predecessor")
        if self.revision_ordinal > 1 and self.predecessor_revision_id is None:
            raise ValueError("later revisions require an immutable predecessor")
        if self.predecessor_revision_id == self.revision_id:
            raise ValueError("a revision cannot be its own predecessor")
        return self


class TemporalTrendSpec(StrictModel):
    method: TemporalTrendMethod = TemporalTrendMethod.NONE
    rolling_observation_count: int | None = Field(
        default=None, strict=True, ge=2, le=MAX_LAST_N
    )
    ewma_alpha: float | None = None

    @field_validator("ewma_alpha", mode="before")
    @classmethod
    def finite_alpha(cls, value: Any) -> float | None:
        return None if value is None else _probability(value, field_name="ewma_alpha")

    @model_validator(mode="after")
    def exact_shape(self) -> TemporalTrendSpec:
        if self.method is TemporalTrendMethod.NONE:
            if self.rolling_observation_count is not None or self.ewma_alpha is not None:
                raise ValueError("untrended observations cannot carry trend parameters")
        elif self.method is TemporalTrendMethod.ROLLING_MEDIAN:
            if self.rolling_observation_count is None or self.ewma_alpha is not None:
                raise ValueError("rolling medians require only an observation count")
        elif (
            self.ewma_alpha is None
            or self.ewma_alpha <= 0
            or self.rolling_observation_count is not None
        ):
            raise ValueError("EWMA requires only an alpha greater than zero")
        return self


class MetricComparisonIdentity(StrictModel):
    metric_key: str
    metric_definition_version: str
    metric_definition_sha256: str
    metric_question_version: str
    metric_question_sha256: str
    value_kind: TemporalValueKind
    unit_code: str
    direction: MetricDirection
    aggregation_semantics: TemporalAggregationSemantics
    exposure_unit_code: str | None = None
    trend: TemporalTrendSpec = Field(default_factory=TemporalTrendSpec)
    interval_method_version: str | None = None
    evidence_tier: EvidenceTier
    evidence_contract_version: str
    estimator_kind: EstimatorIdentityKind
    estimator_plan_version: str
    estimator_plan_sha256: str
    estimator_lifecycle: EstimatorLifecycleState
    activation_receipt_sha256: str | None = None
    model_provider: ModelProviderKind | None = None
    requested_model_key: str | None = None
    requested_model_revision: str | None = None
    served_model_key: str | None = None
    served_model_revision: str | None = None
    served_model_fallback: bool | None = None
    model_weight_identity_state: ArtifactIdentityState | None = None
    model_weight_set_sha256: str | None = None
    tokenizer_key: str | None = None
    tokenizer_revision: str | None = None
    tokenizer_identity_state: ArtifactIdentityState | None = None
    tokenizer_sha256: str | None = None
    model_license_code: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    preprocessing_version: str
    preprocessing_sha256: str
    prompt_template_version: str | None = None
    prompt_template_sha256: str | None = None
    rubric_version: str | None = None
    rubric_sha256: str | None = None
    calibration_version: str
    calibration_sha256: str
    router_version: str
    router_sha256: str
    redactor_version: str
    redactor_sha256: str
    provider: Provider
    provider_adapter_version: str
    provider_schema_version: str
    source_schema_version: str
    privacy_policy_version: str
    observation_contract_version: Literal[TEMPORAL_HISTORY_CONTRACT_VERSION] = (
        TEMPORAL_HISTORY_CONTRACT_VERSION
    )

    _codes = field_validator("metric_key", "unit_code")(_safe_code)
    _optional_exposure_unit = field_validator("exposure_unit_code")(_optional_code)
    _digests = field_validator(
        "metric_definition_sha256",
        "metric_question_sha256",
        "estimator_plan_sha256",
        "preprocessing_sha256",
        "calibration_sha256",
        "router_sha256",
        "redactor_sha256",
    )(_digest)
    _versions = field_validator(
        "metric_definition_version",
        "metric_question_version",
        "evidence_contract_version",
        "estimator_plan_version",
        "preprocessing_version",
        "calibration_version",
        "router_version",
        "redactor_version",
        "provider_adapter_version",
        "provider_schema_version",
        "source_schema_version",
        "privacy_policy_version",
    )(_safe_version)
    _optional_codes = field_validator(
        "requested_model_key",
        "served_model_key",
        "tokenizer_key",
        "model_license_code",
    )(_optional_code)
    _optional_versions = field_validator(
        "interval_method_version",
        "requested_model_revision",
        "served_model_revision",
        "tokenizer_revision",
        "prompt_template_version",
        "rubric_version",
    )(_optional_version)

    @field_validator(
        "activation_receipt_sha256",
        "model_weight_set_sha256",
        "tokenizer_sha256",
        "prompt_template_sha256",
        "rubric_sha256",
    )
    @classmethod
    def optional_digest(cls, value: str | None) -> str | None:
        return None if value is None else _digest(value)

    @model_validator(mode="after")
    def complete_identity(self) -> MetricComparisonIdentity:
        expected_semantics = {
            TemporalValueKind.FRACTION: TemporalAggregationSemantics.RATIO_OF_SUMS,
            TemporalValueKind.COUNT_WITH_EXPOSURE: (
                TemporalAggregationSemantics.COUNT_SUM_WITH_EXPOSURE
            ),
            TemporalValueKind.DISTRIBUTION_SAMPLE: (
                TemporalAggregationSemantics.MEDIAN_AND_QUANTILES
            ),
            TemporalValueKind.SAMPLED_PROPORTION: (
                TemporalAggregationSemantics.PROPORTION_INTERVAL_FROM_SUMS
            ),
        }[self.value_kind]
        if self.aggregation_semantics is not expected_semantics:
            raise ValueError("aggregation semantics must match the raw value kind")
        if (
            self.aggregation_semantics
            is TemporalAggregationSemantics.COUNT_SUM_WITH_EXPOSURE
        ) != (self.exposure_unit_code is not None):
            raise ValueError("count-with-exposure identities require an exposure unit")
        if (self.value_kind is TemporalValueKind.SAMPLED_PROPORTION) != (
            self.interval_method_version is not None
        ):
            raise ValueError("sampled proportions require an interval method version")
        if self.estimator_lifecycle is EstimatorLifecycleState.PROVISIONAL:
            if self.activation_receipt_sha256 is not None:
                raise ValueError("provisional estimators cannot claim activation")
        elif self.activation_receipt_sha256 is None:
            raise ValueError("activated or retired estimators require activation provenance")

        model_fields = (
            self.model_provider,
            self.requested_model_key,
            self.requested_model_revision,
            self.served_model_key,
            self.served_model_revision,
            self.served_model_fallback,
            self.model_weight_identity_state,
            self.tokenizer_key,
            self.tokenizer_revision,
            self.tokenizer_identity_state,
            self.model_license_code,
            self.reasoning_effort,
            self.prompt_template_version,
            self.prompt_template_sha256,
            self.rubric_version,
            self.rubric_sha256,
        )
        if self.estimator_kind is EstimatorIdentityKind.DETERMINISTIC:
            if any(value is not None for value in model_fields):
                raise ValueError("deterministic identities cannot claim model provenance")
            if self.model_weight_set_sha256 is not None or self.tokenizer_sha256 is not None:
                raise ValueError("deterministic identities cannot claim model artifacts")
            return self

        if any(value is None for value in model_fields):
            raise ValueError("model-assisted identities require complete model provenance")
        if self.reasoning_effort is ReasoningEffort.NONE:
            raise ValueError("model-assisted identities require an explicit non-none effort")
        served_is_fallback = (
            self.requested_model_key,
            self.requested_model_revision,
        ) != (
            self.served_model_key,
            self.served_model_revision,
        )
        if self.served_model_fallback is not served_is_fallback:
            raise ValueError("fallback state must match requested and served identities")
        if (
            self.model_weight_identity_state is ArtifactIdentityState.PINNED_SHA256
        ) != (self.model_weight_set_sha256 is not None):
            raise ValueError("model weight hash presence must match its identity state")
        if (self.tokenizer_identity_state is ArtifactIdentityState.PINNED_SHA256) != (
            self.tokenizer_sha256 is not None
        ):
            raise ValueError("tokenizer hash presence must match its identity state")
        required_artifact_state = {
            ModelProviderKind.LOCAL: ArtifactIdentityState.PINNED_SHA256,
            ModelProviderKind.OPENAI: (
                ArtifactIdentityState.PROVIDER_MANAGED_UNAVAILABLE
            ),
            ModelProviderKind.ANTHROPIC: (
                ArtifactIdentityState.PROVIDER_MANAGED_UNAVAILABLE
            ),
            ModelProviderKind.SYNTHETIC: ArtifactIdentityState.SYNTHETIC_NO_ARTIFACT,
        }[self.model_provider]
        if (
            self.model_weight_identity_state is not required_artifact_state
            or self.tokenizer_identity_state is not required_artifact_state
        ):
            raise ValueError(
                "weight and tokenizer identity states must match the model provider"
            )
        return self

    @property
    def fingerprint(self) -> str:
        """Return the canonical comparison identity used to join observations."""

        return _canonical_digest(self)


class FractionObservationValue(StrictModel):
    kind: Literal[TemporalValueKind.FRACTION] = TemporalValueKind.FRACTION
    numerator: NonNegativeInt
    denominator: PositiveInt

    @model_validator(mode="after")
    def valid_fraction(self) -> FractionObservationValue:
        if self.numerator > self.denominator:
            raise ValueError("fraction numerator cannot exceed denominator")
        return self


class CountExposureObservationValue(StrictModel):
    kind: Literal[TemporalValueKind.COUNT_WITH_EXPOSURE] = (
        TemporalValueKind.COUNT_WITH_EXPOSURE
    )
    count: NonNegativeInt
    exposure: float
    exposure_unit_code: str

    _unit = field_validator("exposure_unit_code")(_safe_code)

    @field_validator("exposure", mode="before")
    @classmethod
    def finite_positive_exposure(cls, value: Any) -> float:
        number = _finite(value, field_name="exposure", nonnegative=True)
        if number == 0:
            raise ValueError("exposure must be greater than zero")
        return number


class DistributionSampleObservationValue(StrictModel):
    kind: Literal[TemporalValueKind.DISTRIBUTION_SAMPLE] = (
        TemporalValueKind.DISTRIBUTION_SAMPLE
    )
    sample: float

    @field_validator("sample", mode="before")
    @classmethod
    def finite_sample(cls, value: Any) -> float:
        return _finite(value, field_name="sample")


class SampledProportionObservationValue(StrictModel):
    kind: Literal[TemporalValueKind.SAMPLED_PROPORTION] = (
        TemporalValueKind.SAMPLED_PROPORTION
    )
    successes: NonNegativeInt
    trials: PositiveInt

    @model_validator(mode="after")
    def valid_proportion(self) -> SampledProportionObservationValue:
        if self.successes > self.trials:
            raise ValueError("successes cannot exceed trials")
        return self


TemporalObservationValue = Annotated[
    FractionObservationValue
    | CountExposureObservationValue
    | DistributionSampleObservationValue
    | SampledProportionObservationValue,
    Field(discriminator="kind"),
]


class TemporalUncertainty(StrictModel):
    lower: float
    upper: float
    confidence_level: float
    method_version: str

    _method = field_validator("method_version")(_safe_version)

    @field_validator("lower", "upper", mode="before")
    @classmethod
    def finite_bound(cls, value: Any, info: Any) -> float:
        return _finite(value, field_name=info.field_name)

    @field_validator("confidence_level", mode="before")
    @classmethod
    def confidence_probability(cls, value: Any) -> float:
        number = _probability(value, field_name="confidence_level")
        if number in {0.0, 1.0}:
            raise ValueError("confidence level must be strictly between zero and one")
        return number

    @model_validator(mode="after")
    def ordered_bounds(self) -> TemporalUncertainty:
        if self.lower > self.upper:
            raise ValueError("uncertainty bounds must be ordered")
        return self


class TemporalMetricObservation(PersistenceRevalidatedModel):
    observation_id: str
    revision_id: str
    comparison_identity: MetricComparisonIdentity
    selection_state: TemporalSelectionState
    source_state: TemporalSourceState
    value_state: TemporalValueState
    value: TemporalObservationValue | None = None
    unavailable_reason_code: str | None = None
    evidence_numerator: NonNegativeInt | None = None
    evidence_denominator: PositiveInt | None = None
    uncertainty: TemporalUncertainty | None = None
    observed_at: datetime
    follow_up_window_end_at: datetime | None = None
    contains_local_content: Literal[False] = False
    private_export_allowed: Literal[False] = False
    team_share_allowed: Literal[False] = False

    _ids = field_validator("observation_id", "revision_id")(_digest)
    _reason = field_validator("unavailable_reason_code")(_optional_code)
    _observed = field_validator("observed_at")(_utc)

    @field_validator("follow_up_window_end_at")
    @classmethod
    def optional_follow_up(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)

    @model_validator(mode="after")
    def truthful_state_axes(self) -> TemporalMetricObservation:
        if (self.evidence_numerator is None) != (self.evidence_denominator is None):
            raise ValueError("evidence coverage requires numerator and denominator")
        if (
            self.evidence_numerator is not None
            and self.evidence_denominator is not None
            and self.evidence_numerator > self.evidence_denominator
        ):
            raise ValueError("evidence numerator cannot exceed denominator")
        if self.follow_up_window_end_at is not None and (
            self.follow_up_window_end_at < self.observed_at
        ):
            raise ValueError("follow-up windows cannot end before observation")
        if self.source_state is not TemporalSourceState.PRESENT and any(
            value is not None
            for value in (self.evidence_numerator, self.evidence_denominator)
        ):
            raise ValueError("absent sources cannot claim evidence coverage")

        allowed_sources = {
            TemporalSelectionState.SELECTED: {
                TemporalSourceState.PRESENT,
                TemporalSourceState.SOURCE_MISSING,
                TemporalSourceState.SOURCE_FAILED,
                TemporalSourceState.SOURCE_INCOMPATIBLE,
            },
            TemporalSelectionState.NOT_SELECTED: {TemporalSourceState.NOT_REQUESTED},
            TemporalSelectionState.SELECTION_UNKNOWN: {
                TemporalSourceState.NO_POST_FLOOR_SOURCE
            },
        }[self.selection_state]
        if self.source_state not in allowed_sources:
            raise ValueError("selection state conflicts with source state")

        allowed_values = {
            TemporalSourceState.PRESENT: {
                TemporalValueState.KNOWN,
                TemporalValueState.UNKNOWN,
                TemporalValueState.ABSTAINED,
                TemporalValueState.NOT_APPLICABLE,
            },
            TemporalSourceState.NOT_REQUESTED: {TemporalValueState.UNKNOWN},
            TemporalSourceState.NO_POST_FLOOR_SOURCE: {TemporalValueState.UNKNOWN},
            TemporalSourceState.SOURCE_MISSING: {TemporalValueState.UNKNOWN},
            TemporalSourceState.SOURCE_FAILED: {TemporalValueState.FAILED},
            TemporalSourceState.SOURCE_INCOMPATIBLE: {
                TemporalValueState.INCOMPATIBLE
            },
        }[self.source_state]
        if self.value_state not in allowed_values:
            raise ValueError("source state conflicts with value state")

        is_known = self.value_state is TemporalValueState.KNOWN
        if is_known:
            if self.selection_state is not TemporalSelectionState.SELECTED:
                raise ValueError("known values must have been selected")
            if self.source_state is not TemporalSourceState.PRESENT:
                raise ValueError("known values require a present source")
            if self.value is None or self.unavailable_reason_code is not None:
                raise ValueError("known values require only their typed value")
            if self.value.kind is not self.comparison_identity.value_kind:
                raise ValueError("value shape must match the comparison identity")
            if (
                isinstance(self.value, CountExposureObservationValue)
                and self.value.exposure_unit_code
                != self.comparison_identity.exposure_unit_code
            ):
                raise ValueError("observation exposure unit must match its identity")
            if self.value.kind is TemporalValueKind.SAMPLED_PROPORTION:
                if self.uncertainty is None or (
                    self.uncertainty.method_version
                    != self.comparison_identity.interval_method_version
                ):
                    raise ValueError(
                        "sampled-proportion uncertainty must use the identity interval method"
                    )
            if (
                self.uncertainty is not None
                and self.value.kind
                in {
                    TemporalValueKind.FRACTION,
                    TemporalValueKind.SAMPLED_PROPORTION,
                }
                and not (
                    0 <= self.uncertainty.lower <= self.uncertainty.upper <= 1
                )
            ):
                raise ValueError("fraction uncertainty must remain within zero and one")
        else:
            if self.value is not None or self.uncertainty is not None:
                raise ValueError("unavailable observations cannot carry values")
            if self.unavailable_reason_code is None:
                raise ValueError("unavailable observations require a safe reason code")
        return self


class TemporalObservationBatch(PersistenceRevalidatedModel):
    contract_version: Literal[TEMPORAL_OBSERVATION_BATCH_VERSION] = (
        TEMPORAL_OBSERVATION_BATCH_VERSION
    )
    batch_id: str
    project_id: str
    session_id: str
    revision_id: str
    selection_revision_id: str | None = None
    scope_state: TemporalScopeState
    source_state: TemporalSourceState
    selected_metric_keys: tuple[str, ...] = Field(
        default=(), max_length=MAX_METRICS
    )
    observations: tuple[TemporalMetricObservation, ...] = Field(
        default=(), max_length=MAX_OBSERVATIONS
    )
    recorded_at: datetime
    direct_receipt_only: Literal[True] = True
    legacy_inference_allowed: Literal[False] = False
    contains_local_content: Literal[False] = False
    remote_processing_allowed: Literal[False] = False
    private_export_allowed: Literal[False] = False
    team_share_allowed: Literal[False] = False

    _ids = field_validator(
        "batch_id",
        "project_id",
        "session_id",
        "revision_id",
    )(_digest)
    _recorded = field_validator("recorded_at")(_utc)

    @field_validator("selection_revision_id")
    @classmethod
    def optional_selection_id(cls, value: str | None) -> str | None:
        return None if value is None else _digest(value)

    @field_validator("selected_metric_keys")
    @classmethod
    def canonical_metrics(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_codes(values, allow_empty=True)

    @model_validator(mode="after")
    def exact_scope_and_source(self) -> TemporalObservationBatch:
        exact_scope = self.scope_state is TemporalScopeState.EXACT_SELECTION_RECEIPT
        if exact_scope != (self.selection_revision_id is not None):
            raise ValueError("exact scope requires a selection revision receipt")
        if exact_scope != bool(self.selected_metric_keys):
            raise ValueError("exact scope requires a non-empty selected metric set")
        if not exact_scope and self.observations:
            raise ValueError("unknown selection scope cannot invent metric observations")

        observation_keys = tuple(
            observation.comparison_identity.metric_key
            for observation in self.observations
        )
        if len(observation_keys) != len(set(observation_keys)):
            raise ValueError("a batch may contain at most one observation per metric")
        if exact_scope and observation_keys != self.selected_metric_keys:
            raise ValueError("observations must exactly cover the selected metric set")
        if any(observation.revision_id != self.revision_id for observation in self.observations):
            raise ValueError("all observations must bind to the batch revision")
        if any(
            observation.selection_state is not TemporalSelectionState.SELECTED
            for observation in self.observations
        ):
            raise ValueError("exact batch observations must be selected")
        if any(
            observation.observed_at > self.recorded_at
            for observation in self.observations
        ):
            raise ValueError("a batch cannot precede any contained observation")
        if exact_scope:
            if self.source_state is not TemporalSourceState.PRESENT:
                raise ValueError("prospective exact batches require a present batch receipt")
            if not self.observations:
                raise ValueError("present batches require observations")
        elif self.source_state is not TemporalSourceState.NO_POST_FLOOR_SOURCE:
            raise ValueError("missing selection receipts remain no-post-floor history")
        return self

    @property
    def fingerprint(self) -> str:
        """Derive the immutable batch fingerprint from its canonical payload."""

        return _canonical_digest(self)


class TemporalSnapshotMaterializationRequest(StrictModel):
    project_id: str
    selection_revision_id: str
    selected_metric_keys: tuple[str, ...] = Field(
        min_length=1, max_length=MAX_METRICS
    )
    window: TemporalWindowSpec
    task_mix_policy_version: str
    contains_local_content: Literal[False] = False
    remote_processing_allowed: Literal[False] = False
    private_export_allowed: Literal[False] = False
    team_share_allowed: Literal[False] = False

    _ids = field_validator("project_id", "selection_revision_id")(_digest)
    _policy = field_validator("task_mix_policy_version")(_safe_version)

    @field_validator("selected_metric_keys")
    @classmethod
    def canonical_metrics(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_codes(values)


class TemporalSnapshotSpec(PersistenceRevalidatedModel):
    contract_version: Literal[TEMPORAL_SNAPSHOT_SPEC_VERSION] = (
        TEMPORAL_SNAPSHOT_SPEC_VERSION
    )
    request: TemporalSnapshotMaterializationRequest
    as_of: datetime
    as_of_source: Literal[SnapshotAsOfSource.SERVER_CLOCK] = (
        SnapshotAsOfSource.SERVER_CLOCK
    )
    history_floor_at: datetime
    source_manifest_fingerprint: str
    materializer_version: str
    aggregation_contract_version: str
    no_legacy_backfill: Literal[True] = True
    contains_local_content: Literal[False] = False
    remote_processing_allowed: Literal[False] = False
    private_export_allowed: Literal[False] = False
    team_share_allowed: Literal[False] = False

    _times = field_validator("as_of", "history_floor_at")(_utc)
    _manifest = field_validator("source_manifest_fingerprint")(_digest)
    _versions = field_validator(
        "materializer_version", "aggregation_contract_version"
    )(_safe_version)

    @model_validator(mode="after")
    def server_bounded_window(self) -> TemporalSnapshotSpec:
        if self.history_floor_at > self.as_of:
            raise ValueError("history floor cannot follow the server as-of time")
        if (
            self.request.window.kind is TemporalWindowKind.CUSTOM
            and self.request.window.end_at is not None
            and self.request.window.end_at > self.as_of
        ):
            raise ValueError("custom windows cannot extend beyond the server as-of time")
        return self

    @property
    def fingerprint(self) -> str:
        return _canonical_digest(self)

    @classmethod
    def revalidate_for_persistence(cls, value: Any) -> TemporalSnapshotSpec:
        """Revalidate plain values at every persistence read/write boundary."""

        return _revalidate_persistence_model(cls, value)


class TemporalSnapshotMetricReceipt(PersistenceRevalidatedModel):
    metric_key: str
    compatibility_state: SnapshotMetricCompatibilityState
    comparison_identity_fingerprints: tuple[str, ...] = Field(
        default=(), max_length=MAX_OBSERVATIONS
    )
    eligible_revision_count: NonNegativeInt
    selected_revision_count: NonNegativeInt
    not_selected_revision_count: NonNegativeInt
    selection_unknown_revision_count: NonNegativeInt
    present_source_count: NonNegativeInt
    not_requested_source_count: NonNegativeInt
    no_post_floor_source_count: NonNegativeInt
    source_missing_count: NonNegativeInt
    source_failed_count: NonNegativeInt
    source_incompatible_count: NonNegativeInt
    known_count: NonNegativeInt
    unknown_count: NonNegativeInt
    abstained_count: NonNegativeInt
    not_applicable_count: NonNegativeInt
    failed_count: NonNegativeInt
    incompatible_count: NonNegativeInt
    aggregate_values_omitted: Literal[True] = True
    materialization_trust: Literal[
        MaterializationTrustState.UNTRUSTED_UNTIL_MATERIALIZED
    ] = MaterializationTrustState.UNTRUSTED_UNTIL_MATERIALIZED
    comparison_allowed: Literal[False] = False

    _metric = field_validator("metric_key")(_safe_code)

    @field_validator("comparison_identity_fingerprints")
    @classmethod
    def canonical_identities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_digests(values, allow_empty=True)

    @model_validator(mode="after")
    def coherent_counts_and_compatibility(self) -> TemporalSnapshotMetricReceipt:
        selection_classified = sum(
            (
                self.selected_revision_count,
                self.not_selected_revision_count,
                self.selection_unknown_revision_count,
            )
        )
        source_classified = sum(
            (
                self.present_source_count,
                self.not_requested_source_count,
                self.no_post_floor_source_count,
                self.source_missing_count,
                self.source_failed_count,
                self.source_incompatible_count,
            )
        )
        value_classified = sum(
            (
                self.known_count,
                self.unknown_count,
                self.abstained_count,
                self.not_applicable_count,
                self.failed_count,
                self.incompatible_count,
            )
        )
        if any(
            count != self.eligible_revision_count
            for count in (selection_classified, source_classified, value_classified)
        ):
            raise ValueError("selection, source, and value axes must each cover eligibility")
        if self.not_requested_source_count != self.not_selected_revision_count:
            raise ValueError("not-requested sources must exactly match unselected scope")
        if self.no_post_floor_source_count != self.selection_unknown_revision_count:
            raise ValueError("unknown selection must remain no-post-floor source state")
        selected_sources = sum(
            (
                self.present_source_count,
                self.source_missing_count,
                self.source_failed_count,
                self.source_incompatible_count,
            )
        )
        if selected_sources != self.selected_revision_count:
            raise ValueError("selected scope must map to an explicit selected-source state")
        mandatory_unknown = sum(
            (
                self.not_requested_source_count,
                self.no_post_floor_source_count,
                self.source_missing_count,
            )
        )
        if self.unknown_count < mandatory_unknown:
            raise ValueError("missing or absent sources must remain unknown values")
        present_unknown = self.unknown_count - mandatory_unknown
        if sum(
            (
                self.known_count,
                present_unknown,
                self.abstained_count,
                self.not_applicable_count,
            )
        ) != self.present_source_count:
            raise ValueError("present sources must map to a permitted present value state")
        if self.failed_count != self.source_failed_count:
            raise ValueError("failed sources must exactly map to failed values")
        if self.incompatible_count != self.source_incompatible_count:
            raise ValueError("incompatible sources must exactly map to incompatible values")
        if self.compatibility_state is SnapshotMetricCompatibilityState.COMPATIBLE:
            if len(self.comparison_identity_fingerprints) != 1:
                raise ValueError("compatible aggregates require exactly one identity")
        elif self.compatibility_state is SnapshotMetricCompatibilityState.DISCONTINUITY:
            if len(self.comparison_identity_fingerprints) < 2:
                raise ValueError("discontinuities require at least two identities")
        elif len(self.comparison_identity_fingerprints) > 1 or self.known_count:
            raise ValueError("no-comparison metrics cannot claim comparable known values")
        return self

    @classmethod
    def revalidate_for_persistence(
        cls, value: Any
    ) -> TemporalSnapshotMetricReceipt:
        """Revalidate plain values at every persistence read/write boundary."""

        return _revalidate_persistence_model(cls, value)


class TemporalSnapshotReceipt(PersistenceRevalidatedModel):
    contract_version: Literal[TEMPORAL_SNAPSHOT_RECEIPT_VERSION] = (
        TEMPORAL_SNAPSHOT_RECEIPT_VERSION
    )
    snapshot_id: str
    spec: TemporalSnapshotSpec
    coverage_state: HistoryCoverageState
    effective_window_start_at: datetime | None = None
    effective_window_end_at: datetime | None = None
    selected_session_count: NonNegativeInt
    eligible_revision_count: NonNegativeInt
    included_revision_count: NonNegativeInt
    omitted_revision_count: NonNegativeInt
    present_batch_revision_count: NonNegativeInt
    metric_receipts: tuple[TemporalSnapshotMetricReceipt, ...] = Field(
        min_length=1, max_length=MAX_METRICS
    )
    materialized_at: datetime
    materialization_trust: Literal[
        MaterializationTrustState.UNTRUSTED_UNTIL_MATERIALIZED
    ] = MaterializationTrustState.UNTRUSTED_UNTIL_MATERIALIZED
    repository_verification_required: Literal[True] = True
    sealed: Literal[False] = False
    comparison_allowed: Literal[False] = False
    activation_allowed: Literal[False] = False
    legacy_backfill_performed: Literal[False] = False
    contains_local_content: Literal[False] = False
    remote_processing_allowed: Literal[False] = False
    private_export_allowed: Literal[False] = False
    team_share_allowed: Literal[False] = False

    _id = field_validator("snapshot_id")(_digest)
    _materialized = field_validator("materialized_at")(_utc)

    @field_validator("effective_window_start_at", "effective_window_end_at")
    @classmethod
    def optional_window_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)

    @model_validator(mode="after")
    def immutable_snapshot_shape(self) -> TemporalSnapshotReceipt:
        if self.materialized_at < self.spec.as_of:
            raise ValueError("materialization cannot precede the server as-of time")
        if (self.effective_window_start_at is None) != (
            self.effective_window_end_at is None
        ):
            raise ValueError("effective window bounds must be present together")
        if self.effective_window_start_at is not None:
            if self.effective_window_start_at < self.spec.history_floor_at:
                raise ValueError("effective history cannot precede the declared floor")
            if self.effective_window_end_at is None or (
                self.effective_window_start_at > self.effective_window_end_at
                or self.effective_window_end_at > self.spec.as_of
            ):
                raise ValueError("effective window bounds must be ordered before as-of")
        if (self.included_revision_count > 0) != (
            self.effective_window_start_at is not None
        ):
            raise ValueError("included history requires an explicit effective window")
        if self.included_revision_count + self.omitted_revision_count != (
            self.eligible_revision_count
        ):
            raise ValueError("included and omitted revisions must cover eligibility")
        if self.eligible_revision_count == 0:
            if self.selected_session_count != 0:
                raise ValueError("empty eligibility cannot claim selected sessions")
        elif not 1 <= self.selected_session_count <= self.eligible_revision_count:
            raise ValueError(
                "selected-session count must be a distinct-session projection of eligibility"
            )
        if self.present_batch_revision_count > self.included_revision_count:
            raise ValueError("present batch revisions must be included exactly once")

        metric_keys = tuple(receipt.metric_key for receipt in self.metric_receipts)
        if metric_keys != tuple(sorted(metric_keys)) or len(metric_keys) != len(
            set(metric_keys)
        ):
            raise ValueError("snapshot metric receipts must be unique and sorted")
        if any(
            receipt.eligible_revision_count != self.eligible_revision_count
            for receipt in self.metric_receipts
        ):
            raise ValueError("every metric receipt must cover global revision eligibility")
        if any(
            receipt.present_source_count > self.present_batch_revision_count
            for receipt in self.metric_receipts
        ):
            raise ValueError("metric present sources cannot exceed materialized batches")
        if any(
            (
                receipt.selected_revision_count
                + receipt.not_selected_revision_count
                != self.present_batch_revision_count
            )
            or receipt.selection_unknown_revision_count
            != (
                self.eligible_revision_count
                - self.present_batch_revision_count
            )
            for receipt in self.metric_receipts
        ):
            raise ValueError(
                "each metric selection axis must exactly partition present-batch and unknown revisions"
            )
        if metric_keys != self.spec.request.selected_metric_keys:
            raise ValueError("metric receipts must exactly cover the snapshot selection")

        if self.coverage_state is HistoryCoverageState.COMPLETE:
            if self.omitted_revision_count != 0 or self.included_revision_count == 0:
                raise ValueError("complete history cannot omit eligible revisions")
        elif self.coverage_state is HistoryCoverageState.LEFT_CENSORED:
            if (
                self.omitted_revision_count != 0
                or self.included_revision_count == 0
                or self.effective_window_start_at != self.spec.history_floor_at
            ):
                raise ValueError("left-censored history must visibly begin at its floor")
        elif self.coverage_state is HistoryCoverageState.PARTIAL:
            if self.omitted_revision_count == 0 or self.included_revision_count == 0:
                raise ValueError("partial history must identify omitted revisions")
        elif self.coverage_state is HistoryCoverageState.LEFT_CENSORED_PARTIAL:
            if (
                self.omitted_revision_count == 0
                or self.included_revision_count == 0
                or self.effective_window_start_at != self.spec.history_floor_at
            ):
                raise ValueError(
                    "left-censored partial history must expose its floor and omissions"
                )
        elif self.coverage_state is HistoryCoverageState.NO_POST_FLOOR_OBSERVATIONS:
            if self.included_revision_count != 0 or self.present_batch_revision_count != 0:
                raise ValueError("empty post-floor history cannot claim observations")
            if self.effective_window_start_at is not None:
                raise ValueError("empty post-floor history has no effective window")
        return self

    @classmethod
    def from_spec_and_children(
        cls,
        *,
        snapshot_id: str,
        spec: TemporalSnapshotSpec,
        coverage_state: HistoryCoverageState,
        effective_window_start_at: datetime | None,
        effective_window_end_at: datetime | None,
        selected_session_count: int,
        eligible_revision_count: int,
        included_revision_count: int,
        omitted_revision_count: int,
        present_batch_revision_count: int,
        metric_receipts: tuple[TemporalSnapshotMetricReceipt, ...],
        materialized_at: datetime,
    ) -> TemporalSnapshotReceipt:
        """Reconstruct an untrusted receipt from its complete materialization inputs."""

        return cls.revalidate_for_persistence(
            {
                "snapshot_id": snapshot_id,
                "spec": spec,
                "coverage_state": coverage_state,
                "effective_window_start_at": effective_window_start_at,
                "effective_window_end_at": effective_window_end_at,
                "selected_session_count": selected_session_count,
                "eligible_revision_count": eligible_revision_count,
                "included_revision_count": included_revision_count,
                "omitted_revision_count": omitted_revision_count,
                "present_batch_revision_count": present_batch_revision_count,
                "metric_receipts": metric_receipts,
                "materialized_at": materialized_at,
            }
        )

    @property
    def spec_fingerprint(self) -> str:
        return self.spec.fingerprint

    @property
    def snapshot_fingerprint(self) -> str:
        return _canonical_digest(self)

    @classmethod
    def revalidate_for_persistence(cls, value: Any) -> TemporalSnapshotReceipt:
        """Recursively revalidate nested spec and metrics for persistence."""

        return _revalidate_persistence_model(cls, value)


class CompatibilityBoundary(PersistenceRevalidatedModel):
    contract_version: Literal[COMPATIBILITY_BOUNDARY_VERSION] = (
        COMPATIBILITY_BOUNDARY_VERSION
    )
    boundary_id: str
    project_id: str
    from_snapshot_id: str
    to_snapshot_id: str
    from_as_of: datetime
    to_as_of: datetime
    from_identity: MetricComparisonIdentity
    to_identity: MetricComparisonIdentity
    dimensions: tuple[CompatibilityDimension, ...] = Field(min_length=1)
    detected_at: datetime
    contains_local_content: Literal[False] = False
    remote_processing_allowed: Literal[False] = False
    private_export_allowed: Literal[False] = False
    team_share_allowed: Literal[False] = False

    _ids = field_validator(
        "boundary_id", "project_id", "from_snapshot_id", "to_snapshot_id"
    )(_digest)
    _times = field_validator("from_as_of", "to_as_of", "detected_at")(_utc)

    @field_validator("dimensions")
    @classmethod
    def canonical_dimensions(
        cls, values: tuple[CompatibilityDimension, ...]
    ) -> tuple[CompatibilityDimension, ...]:
        if values != tuple(sorted(values, key=lambda value: value.value)) or len(
            values
        ) != len(set(values)):
            raise ValueError("compatibility dimensions must be unique and sorted")
        return values

    @model_validator(mode="after")
    def exact_boundary(self) -> CompatibilityBoundary:
        if self.from_snapshot_id == self.to_snapshot_id:
            raise ValueError("a boundary requires distinct snapshots")
        if self.from_as_of >= self.to_as_of or self.detected_at < self.to_as_of:
            raise ValueError("boundary timestamps must be strictly ordered")
        if self.from_identity.metric_key != self.to_identity.metric_key:
            raise ValueError("a compatibility boundary cannot change metric keys")
        if self.from_identity.fingerprint == self.to_identity.fingerprint:
            raise ValueError("identical comparison identities have no boundary")

        expected: set[CompatibilityDimension] = set()
        if (
            self.from_identity.metric_definition_version,
            self.from_identity.metric_definition_sha256,
            self.from_identity.metric_question_version,
            self.from_identity.metric_question_sha256,
        ) != (
            self.to_identity.metric_definition_version,
            self.to_identity.metric_definition_sha256,
            self.to_identity.metric_question_version,
            self.to_identity.metric_question_sha256,
        ):
            expected.add(CompatibilityDimension.METRIC_CONTRACT)
        if (
            self.from_identity.value_kind,
            self.from_identity.unit_code,
            self.from_identity.direction,
            self.from_identity.aggregation_semantics,
            self.from_identity.exposure_unit_code,
            self.from_identity.trend,
            self.from_identity.interval_method_version,
        ) != (
            self.to_identity.value_kind,
            self.to_identity.unit_code,
            self.to_identity.direction,
            self.to_identity.aggregation_semantics,
            self.to_identity.exposure_unit_code,
            self.to_identity.trend,
            self.to_identity.interval_method_version,
        ):
            expected.add(CompatibilityDimension.VALUE_SEMANTICS)
        if (
            self.from_identity.evidence_tier,
            self.from_identity.evidence_contract_version,
        ) != (
            self.to_identity.evidence_tier,
            self.to_identity.evidence_contract_version,
        ):
            expected.add(CompatibilityDimension.EVIDENCE_CONTRACT)
        if (
            self.from_identity.estimator_kind,
            self.from_identity.estimator_plan_version,
            self.from_identity.estimator_plan_sha256,
            self.from_identity.estimator_lifecycle,
            self.from_identity.activation_receipt_sha256,
            self.from_identity.preprocessing_version,
            self.from_identity.preprocessing_sha256,
            self.from_identity.prompt_template_version,
            self.from_identity.prompt_template_sha256,
            self.from_identity.rubric_version,
            self.from_identity.rubric_sha256,
            self.from_identity.reasoning_effort,
            self.from_identity.router_version,
            self.from_identity.router_sha256,
        ) != (
            self.to_identity.estimator_kind,
            self.to_identity.estimator_plan_version,
            self.to_identity.estimator_plan_sha256,
            self.to_identity.estimator_lifecycle,
            self.to_identity.activation_receipt_sha256,
            self.to_identity.preprocessing_version,
            self.to_identity.preprocessing_sha256,
            self.to_identity.prompt_template_version,
            self.to_identity.prompt_template_sha256,
            self.to_identity.rubric_version,
            self.to_identity.rubric_sha256,
            self.to_identity.reasoning_effort,
            self.to_identity.router_version,
            self.to_identity.router_sha256,
        ):
            expected.add(CompatibilityDimension.ESTIMATOR_CONFIGURATION)
        if (
            self.from_identity.model_provider,
            self.from_identity.requested_model_key,
            self.from_identity.requested_model_revision,
            self.from_identity.served_model_key,
            self.from_identity.served_model_revision,
            self.from_identity.served_model_fallback,
            self.from_identity.model_weight_identity_state,
            self.from_identity.model_weight_set_sha256,
            self.from_identity.tokenizer_key,
            self.from_identity.tokenizer_revision,
            self.from_identity.tokenizer_identity_state,
            self.from_identity.tokenizer_sha256,
            self.from_identity.model_license_code,
        ) != (
            self.to_identity.model_provider,
            self.to_identity.requested_model_key,
            self.to_identity.requested_model_revision,
            self.to_identity.served_model_key,
            self.to_identity.served_model_revision,
            self.to_identity.served_model_fallback,
            self.to_identity.model_weight_identity_state,
            self.to_identity.model_weight_set_sha256,
            self.to_identity.tokenizer_key,
            self.to_identity.tokenizer_revision,
            self.to_identity.tokenizer_identity_state,
            self.to_identity.tokenizer_sha256,
            self.to_identity.model_license_code,
        ):
            expected.add(CompatibilityDimension.MODEL_IDENTITY)
        if (
            self.from_identity.calibration_version,
            self.from_identity.calibration_sha256,
        ) != (
            self.to_identity.calibration_version,
            self.to_identity.calibration_sha256,
        ):
            expected.add(CompatibilityDimension.CALIBRATION)
        if (
            self.from_identity.provider,
            self.from_identity.provider_adapter_version,
            self.from_identity.provider_schema_version,
            self.from_identity.source_schema_version,
        ) != (
            self.to_identity.provider,
            self.to_identity.provider_adapter_version,
            self.to_identity.provider_schema_version,
            self.to_identity.source_schema_version,
        ):
            expected.add(CompatibilityDimension.PROVIDER_SCHEMA)
        if (
            self.from_identity.redactor_version,
            self.from_identity.redactor_sha256,
            self.from_identity.privacy_policy_version,
        ) != (
            self.to_identity.redactor_version,
            self.to_identity.redactor_sha256,
            self.to_identity.privacy_policy_version,
        ):
            expected.add(CompatibilityDimension.PRIVACY_REDACTOR)
        if set(self.dimensions) != expected:
            raise ValueError("boundary dimensions must exactly describe identity changes")
        return self


__all__ = [
    "COMPATIBILITY_BOUNDARY_VERSION",
    "HALF_OPEN_WINDOW_BOUNDARY",
    "MAX_LAST_N",
    "SESSION_REVISION_RECEIPT_VERSION",
    "TEMPORAL_HISTORY_CONTRACT_VERSION",
    "TEMPORAL_OBSERVATION_BATCH_VERSION",
    "TEMPORAL_SNAPSHOT_RECEIPT_VERSION",
    "TEMPORAL_SNAPSHOT_SPEC_VERSION",
    "ArtifactIdentityState",
    "AnalysisWindowFingerprintBasis",
    "CompatibilityBoundary",
    "CompatibilityDimension",
    "CountExposureObservationValue",
    "DistributionSampleObservationValue",
    "EstimatorIdentityKind",
    "EstimatorLifecycleState",
    "EvidenceTier",
    "FractionObservationValue",
    "HistoryCoverageState",
    "MaterializationTrustState",
    "MetricComparisonIdentity",
    "MetricDirection",
    "ModelProviderKind",
    "ReasoningEffort",
    "RevisionEffectiveTimeBasis",
    "SampledProportionObservationValue",
    "SessionRevisionProvenance",
    "SessionRevisionReceipt",
    "SnapshotAsOfSource",
    "SnapshotMetricCompatibilityState",
    "TemporalAggregationSemantics",
    "TemporalMetricObservation",
    "TemporalObservationBatch",
    "TemporalObservationValue",
    "TemporalScopeState",
    "TemporalSelectionState",
    "TemporalSnapshotMaterializationRequest",
    "TemporalSnapshotMetricReceipt",
    "TemporalSnapshotReceipt",
    "TemporalSnapshotSpec",
    "TemporalSourceState",
    "TemporalTrendMethod",
    "TemporalTrendSpec",
    "TemporalUncertainty",
    "TemporalValueKind",
    "TemporalValueState",
    "TemporalWindowKind",
    "TemporalWindowSpec",
]
