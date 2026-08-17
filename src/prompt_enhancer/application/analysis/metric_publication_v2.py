"""The canonical safe publication seam for the twenty V2 metric contracts.

A publication is a complete, self-describing answer: every one of the twenty
contracts appears exactly once, in registry order, with a typed state and a
content-free guidance receipt.  A consumer therefore never has to decide what a
missing metric key meant, and no surface can quietly render absence as zero.

Two source paths reach the same contract.

``publish_metric_states_v2`` wraps a live projection over persisted
semantic-unit heads.  ``rehydrate_metric_states_v2`` republishes an already
persisted V1 analysis run, and it is deliberately conservative:

* the five objective contracts are resolved only by the typed evidence lane, so
  a stored conversational result can never ground a completion claim;
* a rubric contract republishes only when the stored fraction denominator is
  exactly the reviewed factor list, because that denominator is contract data
  rather than a lexical count;
* every other contract stays ``unknown`` with a fixed reason code.  A V1
  denominator was whatever a lexical rule matched, which is not the exactly
  owned opportunity set or declared profile slot set a V2 contract requires;
* a model-assisted stored result never publishes a value, and a failed stage
  keeps its own fixed reason code instead of blocking the rest of the run.

The withheld cases are the honest boundary of what a V1 receipt can support,
not a defect: closing them needs persisted semantic-unit reconciliation, not a
more permissive rule.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from ...domain import StrictModel
from ..persistence import MetricValueState, SessionAnalysisResultRecord
from .metric_contract_v2 import (
    DenominatorBasis,
    EvidenceAuthority,
    METRIC_CONTRACTS_V2,
    METRIC_CONTRACT_REGISTRY_VERSION_V2,
    MetricContractV2,
    MetricValueStateV2,
    NoOpportunityOutcome,
    metric_contract_v2_set_fingerprint,
)
from .metric_guidance import (
    METRIC_GUIDANCE_CONTRACT_VERSION,
    METRIC_GUIDANCE_TEMPLATE_CATALOG_VERSION,
    MetricGuidanceReceipt,
    build_metric_guidance,
)
from .metric_projection_v2 import (
    METRIC_PROJECTION_V2_VERSION,
    MetricStateV2,
    OpportunityStatistics,
    objective_metric_state,
    resolve_metric_state,
)
from .objective_metric_projection import ObjectiveMetricOverride


METRIC_PUBLICATION_V2_KEY = "metric.contract-v2.publication"
METRIC_PUBLICATION_V2_VERSION = 1

#: Fixed, content-free reasons a stored V1 result cannot resolve a V2 contract.
REASON_RESULT_ABSENT = "metric_result_absent"
REASON_DENOMINATOR_NOT_OPPORTUNITY_OWNED = "v1_denominator_not_opportunity_owned"
REASON_MODEL_ASSISTED_NOT_PUBLISHABLE = "model_assisted_result_not_publishable"
REASON_RUBRIC_DENOMINATOR_MISMATCH = "rubric_denominator_mismatch"
REASON_RESULT_STATE_UNPUBLISHABLE = "stored_result_state_unpublishable"


class MetricPublicationSource(StrEnum):
    """Where the published states came from; never mixed within one bundle."""

    LIVE_PROJECTION = "live_projection"
    PERSISTED_RUN_REHYDRATION = "persisted_run_rehydration"


class PublishedMetricV2(StrictModel):
    """One projected state paired with the guidance derived from it."""

    state: MetricStateV2
    guidance: MetricGuidanceReceipt

    @model_validator(mode="after")
    def validate_pairing(self) -> PublishedMetricV2:
        if self.state.metric_key != self.guidance.metric_key:
            raise ValueError("published guidance belongs to another metric")
        if self.state.value_state is not self.guidance.value_state:
            raise ValueError("published guidance must restate the metric state")
        if self.state.contract_fingerprint != self.guidance.metric_contract_fingerprint:
            raise ValueError("published guidance must match the contract fingerprint")
        if self.state.numerator != self.guidance.numerator or (
            self.state.denominator != self.guidance.denominator
        ):
            raise ValueError("published guidance must restate the exact fraction")
        return self


class MetricPublicationV2(StrictModel):
    """A complete twenty-metric publication with no absent key and no zero fill."""

    publication_key: Literal[METRIC_PUBLICATION_V2_KEY] = METRIC_PUBLICATION_V2_KEY
    publication_version: int = Field(
        default=METRIC_PUBLICATION_V2_VERSION, ge=1
    )
    registry_version: Literal[METRIC_CONTRACT_REGISTRY_VERSION_V2] = (
        METRIC_CONTRACT_REGISTRY_VERSION_V2
    )
    contract_set_fingerprint: str
    projection_version: Literal[METRIC_PROJECTION_V2_VERSION] = (
        METRIC_PROJECTION_V2_VERSION
    )
    guidance_contract_version: Literal[METRIC_GUIDANCE_CONTRACT_VERSION] = (
        METRIC_GUIDANCE_CONTRACT_VERSION
    )
    guidance_template_catalog_version: Literal[
        METRIC_GUIDANCE_TEMPLATE_CATALOG_VERSION
    ] = METRIC_GUIDANCE_TEMPLATE_CATALOG_VERSION
    source: MetricPublicationSource
    metrics: tuple[PublishedMetricV2, ...] = Field(
        min_length=len(METRIC_CONTRACTS_V2), max_length=len(METRIC_CONTRACTS_V2)
    )
    known_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    not_applicable_count: int = Field(ge=0)
    abstained_count: int = Field(ge=0)
    execution_error_count: int = Field(ge=0)
    objective_measured_count: int = Field(ge=0)
    product_metric_eligible: Literal[False] = False

    @model_validator(mode="after")
    def validate_publication(self) -> MetricPublicationV2:
        expected = tuple(item.metric_key for item in METRIC_CONTRACTS_V2)
        if tuple(item.state.metric_key for item in self.metrics) != expected:
            raise ValueError("a publication must list every V2 metric in registry order")
        if self.contract_set_fingerprint != metric_contract_v2_set_fingerprint():
            raise ValueError("publication contract-set fingerprint is stale")
        counts = {
            MetricValueStateV2.KNOWN: self.known_count,
            MetricValueStateV2.PENDING: self.pending_count,
            MetricValueStateV2.UNKNOWN: self.unknown_count,
            MetricValueStateV2.NOT_APPLICABLE: self.not_applicable_count,
            MetricValueStateV2.ABSTAINED: self.abstained_count,
            MetricValueStateV2.EXECUTION_ERROR: self.execution_error_count,
        }
        for value_state, declared in counts.items():
            observed = sum(
                item.state.value_state is value_state for item in self.metrics
            )
            if observed != declared:
                raise ValueError("publication state counts are inconsistent")
        objective_known = sum(
            1
            for item in self.metrics
            if item.state.evidence_authority is EvidenceAuthority.OBJECTIVE_RECEIPT
            and item.state.value_state is MetricValueStateV2.KNOWN
        )
        if objective_known != self.objective_measured_count:
            raise ValueError("publication objective counts are inconsistent")
        # Objective precedence, restated at the publication boundary so a
        # future producer cannot resolve an evidence-lane metric from prose.
        if any(
            item.state.evidence_authority is EvidenceAuthority.OBJECTIVE_RECEIPT
            and item.state.value_state is MetricValueStateV2.KNOWN
            and item.state.statistics.denominator_basis
            is not DenominatorBasis.OBJECTIVE_OPPORTUNITIES
            for item in self.metrics
        ):
            raise ValueError(
                "objective contracts cannot be published from conversational material"
            )
        return self


def publish_metric_states_v2(
    states: Iterable[MetricStateV2],
    *,
    source: MetricPublicationSource,
) -> MetricPublicationV2:
    """Pair every projected state with its guidance receipt.

    The input must already be a complete registry-order projection; a partial
    set is a producer defect rather than something to be padded here.
    """

    published = tuple(
        PublishedMetricV2(state=state, guidance=build_metric_guidance(state))
        for state in states
    )

    def _count(value_state: MetricValueStateV2) -> int:
        return sum(item.state.value_state is value_state for item in published)

    return MetricPublicationV2(
        contract_set_fingerprint=metric_contract_v2_set_fingerprint(),
        source=source,
        metrics=published,
        known_count=_count(MetricValueStateV2.KNOWN),
        pending_count=_count(MetricValueStateV2.PENDING),
        unknown_count=_count(MetricValueStateV2.UNKNOWN),
        not_applicable_count=_count(MetricValueStateV2.NOT_APPLICABLE),
        abstained_count=_count(MetricValueStateV2.ABSTAINED),
        execution_error_count=_count(MetricValueStateV2.EXECUTION_ERROR),
        objective_measured_count=sum(
            1
            for item in published
            if item.state.evidence_authority is EvidenceAuthority.OBJECTIVE_RECEIPT
            and item.state.value_state is MetricValueStateV2.KNOWN
        ),
    )


def _empty_statistics(
    contract: MetricContractV2,
    *,
    capability_available: bool,
    source_complete: bool,
) -> OpportunityStatistics:
    return OpportunityStatistics(
        metric_key=contract.metric_key,
        denominator_basis=contract.denominator_basis,
        opportunity_unit_kind=contract.opportunity_unit_kind,
        capability_available=capability_available,
        source_complete=source_complete,
        eligible_count=0,
    )


def _withheld(contract: MetricContractV2, reason_code: str) -> MetricStateV2:
    """Publish an unknown whose reason names the missing capability, not zero."""

    return resolve_metric_state(
        contract,
        _empty_statistics(
            contract,
            capability_available=False,
            source_complete=False,
        ),
        explanation_code=reason_code,
        unavailable_code=reason_code,
    )


def _rubric_statistics(
    contract: MetricContractV2,
    *,
    met: int,
) -> OpportunityStatistics:
    factor_count = len(contract.factors)
    return OpportunityStatistics(
        metric_key=contract.metric_key,
        denominator_basis=contract.denominator_basis,
        opportunity_unit_kind=contract.opportunity_unit_kind,
        capability_available=True,
        source_complete=True,
        eligible_count=factor_count,
        met_count=met,
        not_met_count=factor_count - met,
    )


def _rehydrated_rubric_state(
    contract: MetricContractV2,
    result: SessionAnalysisResultRecord,
) -> MetricStateV2:
    factor_count = len(contract.factors)
    numerator = result.fraction_numerator
    denominator = result.fraction_denominator
    if (
        numerator is None
        or denominator is None
        or denominator != factor_count
        or numerator > factor_count
    ):
        return _withheld(contract, REASON_RUBRIC_DENOMINATOR_MISMATCH)
    ratio = numerator / denominator
    return MetricStateV2(
        metric_key=contract.metric_key,
        contract_version=contract.contract_version,
        contract_fingerprint=contract.fingerprint,
        evidence_authority=contract.evidence_authority,
        value_state=MetricValueStateV2.KNOWN,
        explanation_code=result.explanation_code,
        numerator=numerator,
        denominator=denominator,
        numeric_value=ratio,
        censoring_lower_bound=ratio,
        censoring_upper_bound=ratio,
        statistics=_rubric_statistics(contract, met=numerator),
    )


def _rehydrated_conversational_state(
    contract: MetricContractV2,
    result: SessionAnalysisResultRecord | None,
) -> MetricStateV2:
    if result is None:
        return _withheld(contract, REASON_RESULT_ABSENT)
    if result.value_state is MetricValueState.EXECUTION_ERROR:
        # An optional local model stage failed.  Preserve its fixed reason code
        # and let every other contract publish normally.
        return MetricStateV2(
            metric_key=contract.metric_key,
            contract_version=contract.contract_version,
            contract_fingerprint=contract.fingerprint,
            evidence_authority=contract.evidence_authority,
            value_state=MetricValueStateV2.EXECUTION_ERROR,
            explanation_code=result.error_code or result.explanation_code,
            statistics=_empty_statistics(
                contract,
                capability_available=False,
                source_complete=False,
            ),
        )
    if result.model_id is not None:
        # A model-assisted observation is not a deterministic opportunity count
        # and has not passed the calibration gate, so it cannot publish a value.
        return _withheld(contract, REASON_MODEL_ASSISTED_NOT_PUBLISHABLE)
    if contract.denominator_basis is not DenominatorBasis.RUBRIC_FACTORS:
        return _withheld(contract, REASON_DENOMINATOR_NOT_OPPORTUNITY_OWNED)
    if result.value_state is MetricValueState.KNOWN:
        return _rehydrated_rubric_state(contract, result)
    if result.value_state is MetricValueState.ABSTAINED:
        return MetricStateV2(
            metric_key=contract.metric_key,
            contract_version=contract.contract_version,
            contract_fingerprint=contract.fingerprint,
            evidence_authority=contract.evidence_authority,
            value_state=MetricValueStateV2.ABSTAINED,
            explanation_code=result.explanation_code,
            statistics=_empty_statistics(
                contract,
                capability_available=True,
                source_complete=True,
            ),
        )
    if (
        result.value_state is MetricValueState.NOT_APPLICABLE
        and contract.no_opportunity_outcome is NoOpportunityOutcome.NOT_APPLICABLE
    ):
        return resolve_metric_state(
            contract,
            _empty_statistics(
                contract,
                capability_available=True,
                source_complete=True,
            ),
            explanation_code=result.explanation_code,
        )
    if result.value_state is MetricValueState.UNKNOWN:
        return _withheld(contract, result.explanation_code)
    return _withheld(contract, REASON_RESULT_STATE_UNPUBLISHABLE)


def rehydrate_metric_states_v2(
    results: Iterable[SessionAnalysisResultRecord],
    *,
    objective_overrides: Mapping[str, ObjectiveMetricOverride] | None = None,
) -> tuple[MetricStateV2, ...]:
    """Republish one persisted analysis run against the V2 registry.

    ``objective_overrides`` is the only way an evidence-lane contract can become
    known.  Passing none keeps all five fail-closed, which is the correct state
    for a run whose typed evidence was never captured.
    """

    by_key: dict[str, SessionAnalysisResultRecord] = {}
    duplicated: set[str] = set()
    for result in results:
        key = result.observation.key
        if key in by_key:
            duplicated.add(key)
            continue
        by_key[key] = result
    overrides = dict(objective_overrides or {})
    states: list[MetricStateV2] = []
    for contract in METRIC_CONTRACTS_V2:
        if contract.denominator_basis is DenominatorBasis.OBJECTIVE_OPPORTUNITIES:
            states.append(
                objective_metric_state(contract, overrides.get(contract.metric_key))
            )
            continue
        if contract.metric_key in duplicated:
            # Two rows for one metric make the exact fraction ambiguous.
            states.append(_withheld(contract, REASON_RESULT_STATE_UNPUBLISHABLE))
            continue
        states.append(
            _rehydrated_conversational_state(
                contract, by_key.get(contract.metric_key)
            )
        )
    return tuple(states)


__all__ = [
    "METRIC_PUBLICATION_V2_KEY",
    "METRIC_PUBLICATION_V2_VERSION",
    "REASON_DENOMINATOR_NOT_OPPORTUNITY_OWNED",
    "REASON_MODEL_ASSISTED_NOT_PUBLISHABLE",
    "REASON_RESULT_ABSENT",
    "REASON_RESULT_STATE_UNPUBLISHABLE",
    "REASON_RUBRIC_DENOMINATOR_MISMATCH",
    "MetricPublicationSource",
    "MetricPublicationV2",
    "PublishedMetricV2",
    "publish_metric_states_v2",
    "rehydrate_metric_states_v2",
]
