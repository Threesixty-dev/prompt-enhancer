"""Ephemeral contracts for consent-gated, local P1 text analysis.

This module intentionally provides no persistence or provider-reading behavior.
Redacted text is accepted only as ``SecretStr`` and is excluded from object
representations.  Persistable results contain numeric observations, safe codes,
pseudonymous evidence identifiers, and complete analysis provenance only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Protocol

from pydantic import Field, SecretStr, field_validator, model_validator

from ...domain import (
    DataTier,
    MetricObservation,
    PSEUDONYM_PATTERN,
    Provider,
    SAFE_VERSION_PATTERN,
    StrictModel,
)
from ..persistence import MetricValueState


MAX_REDACTED_MESSAGE_CHARACTERS = 32_000
MAX_ANALYSIS_MESSAGES = 500
MAX_ANALYSIS_CHARACTERS = 500_000
MAX_ELIGIBLE_MESSAGES = 10_000_000
TEXT_METRIC_SCHEMA_VERSION = 2
MAX_TEXT_METRIC_SIGNALS = 32

_SAFE_LABEL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _pseudonym(value: str) -> str:
    if not PSEUDONYM_PATTERN.fullmatch(value):
        raise ValueError("identifiers must be 64-character HMAC pseudonyms")
    return value


def _safe_version(value: str | None) -> str | None:
    if value is not None and not SAFE_VERSION_PATTERN.fullmatch(value):
        raise ValueError("versions must use safe identifier characters")
    return value


def _safe_label(value: str | None) -> str | None:
    if value is not None and not _SAFE_LABEL.fullmatch(value):
        raise ValueError("codes must be short content-free identifiers")
    return value


def _unique(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} cannot contain duplicates")
    return values


class TextRole(StrEnum):
    USER = "user"
    AGENT = "agent"


class TextMessageKind(StrEnum):
    REQUEST = "request"
    RESPONSE = "response"
    PLAN = "plan"
    ACTION = "action"
    VERIFICATION = "verification"
    DECISION = "decision"
    FEEDBACK = "feedback"
    SUMMARY = "summary"


class TextLanguage(StrEnum):
    ENGLISH = "en"
    POLISH = "pl"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class EvidenceOrigin(StrEnum):
    DIRECT = "direct"
    INHERITED = "inherited"


class TextMetricSignalStatus(StrEnum):
    """Closed, content-free interpretation of one metric factor."""

    DETECTED = "detected"
    MISSING = "missing"
    COUNTED = "counted"
    UNKNOWN = "unknown"


class MetricApplicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class ApplicabilityBasis(StrEnum):
    USER_SELECTED = "user_selected"
    TASK_PROFILE = "task_profile"
    DETERMINISTIC_RULE = "deterministic_rule"


class MetricDirection(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class AggregationMethod(StrEnum):
    RATIO_OF_SUMS = "ratio_of_sums"
    COUNT_SUM = "count_sum"
    NOT_AGGREGATABLE = "not_aggregatable"


class ApplicabilitySemantics(StrEnum):
    EXPLICIT_PROFILE_REQUIRED = "explicit_profile_required"


class GoalSlot(StrEnum):
    ACTION = "action"
    TARGET = "target"
    OUTCOME = "outcome"


class ConstraintKind(StrEnum):
    PRIVACY = "privacy"
    COST = "cost"
    PLATFORM = "platform"
    VERSION = "version"
    SCOPE = "scope"
    PERFORMANCE = "performance"
    DELIVERY = "delivery"
    SAFETY = "safety"


class DeliverableSlot(StrEnum):
    ARTIFACT = "artifact"
    FORMAT = "format"
    LOCATION = "location"
    AUDIENCE = "audience"
    INTERFACE = "interface"
    COMPATIBILITY = "compatibility"


class EphemeralRedactedMessage(StrictModel):
    """One locally redacted message; never a persistence record.

    ``SecretStr`` prevents accidental disclosure through normal representation,
    serialization, validation errors, and logging.  It is not encryption and does
    not make the content safe to persist.
    """

    message_id: str
    sequence: int = Field(ge=0)
    role: TextRole
    kind: TextMessageKind
    language: TextLanguage
    scope_key: str = "task.current"
    text: SecretStr = Field(
        repr=False,
        min_length=1,
        max_length=MAX_REDACTED_MESSAGE_CHARACTERS,
    )
    supersedes_message_ids: tuple[str, ...] = ()

    _validate_message_id = field_validator("message_id")(_pseudonym)
    _validate_scope = field_validator("scope_key")(_safe_label)
    _validate_superseded = field_validator("supersedes_message_ids")(
        lambda values: _unique(
            tuple(_pseudonym(value) for value in values),
            "supersedes_message_ids",
        )
    )

    @field_validator("text")
    @classmethod
    def reject_nul(cls, value: SecretStr) -> SecretStr:
        if "\x00" in value.get_secret_value():
            raise ValueError("redacted message cannot contain NUL")
        return value


class MetricApplicabilityDecision(StrictModel):
    metric_key: str
    applicability: MetricApplicability
    basis: ApplicabilityBasis

    _validate_metric_key = field_validator("metric_key")(_safe_version)


class TextTaskProfile(StrictModel):
    """Explicit applicability and task-specific denominator configuration.

    An empty expected-slot set is deliberately not interpreted as zero.  A
    calculator must abstain when it cannot form a defensible denominator.
    """

    applicability: tuple[MetricApplicabilityDecision, ...]
    expected_goal_slots: tuple[GoalSlot, ...] = (
        GoalSlot.ACTION,
        GoalSlot.TARGET,
        GoalSlot.OUTCOME,
    )
    expected_constraint_kinds: tuple[ConstraintKind, ...] = ()
    expected_deliverable_slots: tuple[DeliverableSlot, ...] = ()
    expected_outcome_count: int | None = Field(default=None, ge=1, le=100)

    @field_validator(
        "expected_goal_slots",
        "expected_constraint_kinds",
        "expected_deliverable_slots",
    )
    @classmethod
    def unique_enums(cls, values: tuple[StrEnum, ...]) -> tuple[StrEnum, ...]:
        if len(set(values)) != len(values):
            raise ValueError("expected profile values cannot contain duplicates")
        return values

    @model_validator(mode="after")
    def unique_metric_decisions(self) -> TextTaskProfile:
        keys = tuple(item.metric_key for item in self.applicability)
        if len(set(keys)) != len(keys):
            raise ValueError("metric applicability decisions cannot contain duplicates")
        return self

    def applicability_for(self, metric_key: str) -> MetricApplicability:
        for decision in self.applicability:
            if decision.metric_key == metric_key:
                return decision.applicability
        return MetricApplicability.UNKNOWN


class P1TextAnalysisInput(StrictModel):
    """Bounded redacted conversation window supplied by a trusted ingress port."""

    provider: Provider
    session_id: str
    provider_version: str
    adapter_version: str
    source_schema_version: str
    content_schema_version: str
    redactor_version: str
    # False is the safe default for adapters that have not proved every
    # content-bearing source variant was either admitted or deliberately
    # classified. Providers must opt into completeness explicitly.
    text_extraction_complete: bool = False
    available_message_kinds: frozenset[TextMessageKind] = Field(min_length=1)
    analysis_window_fingerprint: str
    focus_message_id: str
    observed_message_count: int = Field(ge=1, le=MAX_ANALYSIS_MESSAGES)
    eligible_message_count: int = Field(ge=1, le=MAX_ELIGIBLE_MESSAGES)
    messages: tuple[EphemeralRedactedMessage, ...] = Field(
        repr=False,
        min_length=1,
        max_length=MAX_ANALYSIS_MESSAGES,
    )
    task_profile: TextTaskProfile

    _validate_ids = field_validator(
        "session_id", "analysis_window_fingerprint", "focus_message_id"
    )(_pseudonym)
    _validate_versions = field_validator(
        "provider_version",
        "adapter_version",
        "source_schema_version",
        "content_schema_version",
        "redactor_version",
    )(_safe_version)

    @model_validator(mode="after")
    def validate_window(self) -> P1TextAnalysisInput:
        if self.observed_message_count != len(self.messages):
            raise ValueError("observed message count must match the bounded window")
        observed_kinds = {message.kind for message in self.messages}
        if not observed_kinds.issubset(self.available_message_kinds):
            raise ValueError(
                "observed message kinds must be declared by the source capability"
            )
        if self.observed_message_count > self.eligible_message_count:
            raise ValueError("observed message count cannot exceed eligible count")
        if (
            sum(len(message.text.get_secret_value()) for message in self.messages)
            > MAX_ANALYSIS_CHARACTERS
        ):
            raise ValueError("analysis window exceeds the redacted-text budget")
        ids = tuple(message.message_id for message in self.messages)
        if len(set(ids)) != len(ids):
            raise ValueError("analysis messages cannot contain duplicate identifiers")
        if tuple(message.sequence for message in self.messages) != tuple(
            sorted(message.sequence for message in self.messages)
        ):
            raise ValueError("analysis messages must be ordered by sequence")
        if len(set(message.sequence for message in self.messages)) != len(self.messages):
            raise ValueError("analysis messages cannot share a sequence")
        if self.focus_message_id not in set(ids):
            raise ValueError("focus message must belong to the analysis window")
        focus_message = next(
            message
            for message in self.messages
            if message.message_id == self.focus_message_id
        )
        if focus_message.role is not TextRole.USER or focus_message.kind not in {
            TextMessageKind.REQUEST,
            TextMessageKind.FEEDBACK,
        }:
            raise ValueError("focus message must be a user request or feedback")
        position = {message_id: index for index, message_id in enumerate(ids)}
        for index, message in enumerate(self.messages):
            if message.message_id in set(message.supersedes_message_ids):
                raise ValueError("a message cannot supersede itself")
            if any(
                superseded not in position or position[superseded] >= index
                for superseded in message.supersedes_message_ids
            ):
                raise ValueError("superseded messages must precede their replacement")
        return self

    @property
    def window_complete(self) -> bool:
        return self.observed_message_count == self.eligible_message_count


class P1LocalAnalysisGrant(StrictModel):
    """Explicit capability passed by the consent-gated application service."""

    provider: Provider
    session_id: str
    analysis_window_fingerprint: str
    data_tier: DataTier
    consent_active: bool
    local_only: bool = True
    content_persistence_allowed: bool = False

    _validate_ids = field_validator(
        "session_id", "analysis_window_fingerprint"
    )(_pseudonym)

    @model_validator(mode="after")
    def enforce_local_p1_boundary(self) -> P1LocalAnalysisGrant:
        if self.data_tier is not DataTier.REDACTED_CONTENT:
            raise ValueError("text analysis requires the redacted-content tier")
        if not self.consent_active:
            raise ValueError("text analysis requires active consent")
        if not self.local_only:
            raise ValueError("the deterministic text pack is local-only")
        if self.content_persistence_allowed:
            raise ValueError("ephemeral text cannot cross the persistence boundary")
        return self


@dataclass(frozen=True, slots=True)
class TextMetricDefinition:
    key: str
    version: int
    dimension: str
    display_name: str
    description: str
    unit: str
    direction: MetricDirection
    aggregation_method: AggregationMethod = AggregationMethod.RATIO_OF_SUMS
    required_tier: DataTier = DataTier.REDACTED_CONTENT
    applicability_semantics: ApplicabilitySemantics = (
        ApplicabilitySemantics.EXPLICIT_PROFILE_REQUIRED
    )
    evidence_reference_kind: str = "pseudonymous_message_id"

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("metric definition versions begin at one")
        for value in (self.key, self.dimension, self.unit):
            if not SAFE_VERSION_PATTERN.fullmatch(value):
                raise ValueError("metric definition identifiers must be safe")
        if self.required_tier is not DataTier.REDACTED_CONTENT:
            raise ValueError("P1 text metrics require the redacted-content tier")
        if not _SAFE_LABEL.fullmatch(self.evidence_reference_kind):
            raise ValueError("evidence reference kind must be a safe code")


class TextMetricEvidence(StrictModel):
    message_id: str
    origin: EvidenceOrigin

    _validate_message_id = field_validator("message_id")(_pseudonym)


class TextMetricSignal(StrictModel):
    """One bounded score receipt item; never text, an excerpt, or an identifier."""

    code: str
    status: TextMetricSignalStatus
    count: int | None = Field(default=None, ge=0, le=MAX_ELIGIBLE_MESSAGES)

    _validate_code = field_validator("code")(_safe_label)

    @model_validator(mode="after")
    def validate_signal(self) -> TextMetricSignal:
        if self.status is TextMetricSignalStatus.DETECTED and self.count != 1:
            raise ValueError("detected binary signals require count one")
        if self.status is TextMetricSignalStatus.MISSING and self.count != 0:
            raise ValueError("missing binary signals require count zero")
        if self.status is TextMetricSignalStatus.COUNTED and self.count is None:
            raise ValueError("counted signals require a non-negative count")
        if self.status is TextMetricSignalStatus.UNKNOWN and self.count is not None:
            raise ValueError("unknown signals cannot claim a count")
        return self


class MetricFraction(StrictModel):
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_fraction(self) -> MetricFraction:
        if self.numerator > self.denominator:
            raise ValueError("metric numerator cannot exceed its denominator")
        return self


class TextMetricProvenance(StrictModel):
    provider: Provider
    provider_version: str
    adapter_version: str
    source_schema_version: str
    content_schema_version: str
    redactor_version: str
    analysis_window_fingerprint: str
    algorithm_id: str
    algorithm_version: str
    metric_schema_version: int = Field(ge=1)
    model_id: str | None = None
    model_revision: str | None = None
    model_license: str | None = None
    tokenizer_id: str | None = None
    prompt_version: str | None = None
    rubric_version: str | None = None
    local_only: bool = True

    _validate_fingerprint = field_validator("analysis_window_fingerprint")(_pseudonym)
    _validate_versions = field_validator(
        "provider_version",
        "adapter_version",
        "source_schema_version",
        "content_schema_version",
        "redactor_version",
        "algorithm_id",
        "algorithm_version",
        "model_id",
        "model_revision",
        "model_license",
        "tokenizer_id",
        "prompt_version",
        "rubric_version",
    )(_safe_version)

    @model_validator(mode="after")
    def enforce_local_provenance(self) -> TextMetricProvenance:
        if not self.local_only:
            raise ValueError("this result contract is for local analysis only")
        immutable_model_fields = (
            self.model_revision,
            self.model_license,
            self.tokenizer_id,
        )
        if self.model_id is None:
            if any(
                value is not None
                for value in immutable_model_fields + (self.prompt_version,)
            ):
                raise ValueError("model provenance fields require a model identifier")
        elif any(value is None for value in immutable_model_fields):
            raise ValueError(
                "modeled results require pinned revision, license, and tokenizer"
            )
        return self


class TextMetricCalculation(StrictModel):
    """Content-free output of one calculator before engine provenance stamping."""

    value_state: MetricValueState
    fraction: MetricFraction | None = None
    evidence: tuple[TextMetricEvidence, ...] = ()
    signals: tuple[TextMetricSignal, ...] = ()
    explanation_code: str
    error_code: str | None = None

    _validate_explanation = field_validator("explanation_code")(_safe_label)
    _validate_error = field_validator("error_code")(_safe_label)

    @model_validator(mode="after")
    def validate_calculation_state(self) -> TextMetricCalculation:
        if self.value_state is MetricValueState.KNOWN:
            if self.fraction is None or self.error_code is not None:
                raise ValueError("known calculations require a fraction")
        elif self.fraction is not None:
            raise ValueError("non-known calculations cannot contain a fraction")
        elif self.value_state is MetricValueState.EXECUTION_ERROR:
            if self.error_code is None:
                raise ValueError("execution errors require a safe error code")
        elif self.error_code is not None:
            raise ValueError("only execution errors may contain an error code")
        identities = tuple(item.message_id for item in self.evidence)
        if len(set(identities)) != len(identities):
            raise ValueError("calculation evidence cannot contain duplicates")
        signal_codes = tuple(item.code for item in self.signals)
        if len(signal_codes) > MAX_TEXT_METRIC_SIGNALS:
            raise ValueError("calculation signal receipt exceeds its fixed bound")
        if len(set(signal_codes)) != len(signal_codes):
            raise ValueError("calculation signals cannot contain duplicate codes")
        if self.value_state is MetricValueState.EXECUTION_ERROR and self.signals:
            raise ValueError("execution errors cannot claim extracted signals")
        return self


class TextMetricResult(StrictModel):
    observation: MetricObservation
    value_state: MetricValueState
    direction: MetricDirection
    aggregation_method: AggregationMethod
    applicability: MetricApplicability
    evidence_data_tier: DataTier
    fraction: MetricFraction | None = None
    evidence: tuple[TextMetricEvidence, ...] = ()
    signals: tuple[TextMetricSignal, ...] = ()
    explanation_code: str
    error_code: str | None = None
    provenance: TextMetricProvenance

    _validate_explanation = field_validator("explanation_code")(_safe_label)
    _validate_error = field_validator("error_code")(_safe_label)

    @model_validator(mode="after")
    def validate_result_state(self) -> TextMetricResult:
        has_value = self.observation.numeric_value is not None
        if self.observation.text_value is not None:
            raise ValueError("text-analysis metrics cannot persist textual values")
        if self.value_state is MetricValueState.KNOWN:
            if not has_value or self.fraction is None or self.error_code is not None:
                raise ValueError("known results require a fraction and numeric value")
            expected = self.fraction.numerator / self.fraction.denominator
            if abs(self.observation.numeric_value - expected) > 1e-9:
                raise ValueError("numeric value must equal the versioned fraction")
            if self.aggregation_method is not AggregationMethod.RATIO_OF_SUMS:
                raise ValueError("fraction metrics require ratio-of-sums aggregation")
        else:
            if has_value or self.fraction is not None:
                raise ValueError("non-known results cannot contain a value")
            if self.value_state is MetricValueState.EXECUTION_ERROR:
                if self.error_code is None:
                    raise ValueError("execution errors require a safe error code")
            elif self.error_code is not None:
                raise ValueError("only execution errors may contain an error code")
        identities = tuple(item.message_id for item in self.evidence)
        if len(set(identities)) != len(identities):
            raise ValueError("metric evidence cannot contain duplicates")
        signal_codes = tuple(item.code for item in self.signals)
        if len(signal_codes) > MAX_TEXT_METRIC_SIGNALS:
            raise ValueError("metric signal receipt exceeds its fixed bound")
        if len(set(signal_codes)) != len(signal_codes):
            raise ValueError("metric signals cannot contain duplicate codes")
        if self.value_state is MetricValueState.EXECUTION_ERROR and self.signals:
            raise ValueError("execution errors cannot claim extracted signals")
        if self.evidence_data_tier is not DataTier.REDACTED_CONTENT:
            raise ValueError("text metric evidence originates at the P1 tier")
        if (
            self.applicability is MetricApplicability.UNKNOWN
            and self.value_state is not MetricValueState.UNKNOWN
        ):
            raise ValueError("unknown applicability requires an unknown value")
        if (
            self.applicability is MetricApplicability.NOT_APPLICABLE
            and self.value_state is not MetricValueState.NOT_APPLICABLE
        ):
            raise ValueError(
                "not-applicable scope requires a not-applicable value"
            )
        if (
            self.applicability is MetricApplicability.APPLICABLE
            and self.value_state is MetricValueState.NOT_APPLICABLE
        ):
            raise ValueError("applicable scope cannot emit not-applicable")
        return self


class TextAnalysisPrivacyError(PermissionError):
    """The supplied consent capability does not match the bounded input."""


class TextFeatureSet(Protocol):
    """Marker protocol for an ephemeral, non-persistable feature snapshot."""


class TextMetricCalculator(Protocol):
    definition: TextMetricDefinition

    def calculate(
        self,
        context: P1TextAnalysisInput,
        features: TextFeatureSet,
    ) -> TextMetricCalculation: ...
