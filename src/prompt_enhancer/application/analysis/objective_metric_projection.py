"""Conservative measured projections from typed local evidence.

This module never inspects provider payloads and never infers a semantic link
that the adapter did not declare. It turns only descriptor-authorized,
content-free evidence relations into exact fractions for the measured layer.
Text models remain outside this authority boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..providers import DecoderDescriptor
from .evidence_contracts import (
    ActionEvidence,
    ActionState,
    DecisionEvidence,
    DecisionState,
    EphemeralTypedEvidenceProjection,
    TypedEvidenceOpportunityKind,
    VerificationEvidence,
    VerificationOutcome,
    validate_projection_descriptor,
)
from .text_contracts import MetricValueState


OBJECTIVE_EVIDENCE_METRIC_KEYS = (
    "logic.hypothesis_test_linkage",
    "logic.requirement_action_traceability",
    "outcome.agent_claim_grounding",
    "outcome.first_pass_verification",
    "outcome.verified_requirement_coverage",
)
# The current immutable typed-metric receipt still names these fields as
# message counts and bounds the observed side at 100. Larger authoritative
# opportunity sets must fail closed instead of overflowing or being truncated.
MAX_OBJECTIVE_RECEIPT_OPPORTUNITIES = 100


@dataclass(frozen=True, slots=True)
class ObjectiveMetricOverride:
    """One exact, content-free replacement for a deterministic metric result."""

    value_state: MetricValueState
    explanation_code: str
    numerator: int | None = None
    denominator: int | None = None
    resolved_opportunity_count: int = 0
    eligible_opportunity_count: int = 0

    def __post_init__(self) -> None:
        known = self.value_state is MetricValueState.KNOWN
        if known != (self.numerator is not None and self.denominator is not None):
            raise ValueError("known objective metrics require an exact fraction")
        if known and (
            self.denominator is None
            or self.denominator < 1
            or self.numerator is None
            or not 0 <= self.numerator <= self.denominator
        ):
            raise ValueError("objective metric fraction is invalid")
        if not (
            0
            <= self.resolved_opportunity_count
            <= self.eligible_opportunity_count
        ):
            raise ValueError("objective opportunity coverage is invalid")
        if known and (
            self.denominator != self.eligible_opportunity_count
            or self.resolved_opportunity_count != self.eligible_opportunity_count
        ):
            raise ValueError("known objective metrics require complete opportunity coverage")
        if (
            self.value_state is MetricValueState.NOT_APPLICABLE
            and self.eligible_opportunity_count != 0
        ):
            raise ValueError("not-applicable objective metrics require an empty set")


def _not_applicable(code: str) -> ObjectiveMetricOverride:
    return ObjectiveMetricOverride(
        value_state=MetricValueState.NOT_APPLICABLE,
        explanation_code=code,
    )


def _unknown(code: str, *, resolved: int, eligible: int) -> ObjectiveMetricOverride:
    return ObjectiveMetricOverride(
        value_state=MetricValueState.UNKNOWN,
        explanation_code=code,
        resolved_opportunity_count=resolved,
        eligible_opportunity_count=eligible,
    )


def _known(code: str, *, numerator: int, denominator: int) -> ObjectiveMetricOverride:
    return ObjectiveMetricOverride(
        value_state=MetricValueState.KNOWN,
        explanation_code=code,
        numerator=numerator,
        denominator=denominator,
        resolved_opportunity_count=denominator,
        eligible_opportunity_count=denominator,
    )


def _withheld_map(code: str) -> dict[str, ObjectiveMetricOverride]:
    return {
        metric_key: _unknown(code, resolved=0, eligible=0)
        for metric_key in OBJECTIVE_EVIDENCE_METRIC_KEYS
    }


def _latest_verification_by_reference(
    records: tuple[VerificationEvidence, ...],
    reference_field: str,
) -> dict[str, VerificationEvidence]:
    latest: dict[str, VerificationEvidence] = {}
    for record in records:
        references = getattr(record, reference_field)
        for reference in references:
            previous = latest.get(reference)
            if previous is None or record.sequence > previous.sequence:
                latest[reference] = record
    return latest


def _receipt_bound_unknown() -> ObjectiveMetricOverride:
    # Do not cap counts: that would fabricate both the denominator and coverage.
    return _unknown(
        "typed_objective_opportunity_count_exceeds_receipt_bound",
        resolved=0,
        eligible=0,
    )


def project_objective_metric_overrides(
    projection: EphemeralTypedEvidenceProjection | None,
    descriptor: DecoderDescriptor | None,
) -> dict[str, ObjectiveMetricOverride]:
    """Return only objective measurements justified by an authorized graph.

    Denominators come exclusively from explicitly declared opportunity sets.
    A linked action or receipt can therefore never erase eligible requirements
    that have no link. Missing or right-edge evidence remains unknown whenever
    the typed state does not mechanically close the opportunity.
    """

    if projection is None or descriptor is None:
        return _withheld_map("typed_objective_authority_unavailable")
    validate_projection_descriptor(projection, descriptor)
    if not projection.provenance.extraction_complete:
        return _withheld_map("typed_objective_extraction_incomplete")

    actions = tuple(
        record for record in projection.records if isinstance(record, ActionEvidence)
    )
    decisions = tuple(
        record for record in projection.records if isinstance(record, DecisionEvidence)
    )
    verifications = tuple(
        record
        for record in projection.records
        if isinstance(record, VerificationEvidence)
    )
    declared = projection.declared_opportunity_kinds
    overrides = _withheld_map("typed_objective_opportunity_authority_missing")

    if TypedEvidenceOpportunityKind.HYPOTHESIS in declared:
        hypotheses = frozenset(projection.eligible_hypothesis_reference_ids)
        if not hypotheses:
            overrides["logic.hypothesis_test_linkage"] = _not_applicable(
                "typed_hypothesis_set_empty"
            )
        elif len(hypotheses) > MAX_OBJECTIVE_RECEIPT_OPPORTUNITIES:
            overrides["logic.hypothesis_test_linkage"] = _receipt_bound_unknown()
        else:
            linked = 0
            unresolved = 0
            for hypothesis_id in hypotheses:
                hypothesis_actions = tuple(
                    item
                    for item in actions
                    if hypothesis_id in item.hypothesis_reference_ids
                )
                hypothesis_verifications = tuple(
                    item
                    for item in verifications
                    if hypothesis_id in item.hypothesis_reference_ids
                )
                hypothesis_decisions = tuple(
                    item
                    for item in decisions
                    if hypothesis_id in item.hypothesis_reference_ids
                )
                latest_verification = max(
                    hypothesis_verifications,
                    key=lambda item: item.sequence,
                    default=None,
                )
                chain_found = latest_verification is not None and any(
                    action.state is ActionState.COMPLETED
                    and action.sequence
                    < latest_verification.sequence
                    < decision.sequence
                    and latest_verification.outcome
                    in {VerificationOutcome.PASSED, VerificationOutcome.FAILED}
                    and decision.state
                    in {DecisionState.ACCEPTED, DecisionState.SUPERSEDED}
                    for action in hypothesis_actions
                    for decision in hypothesis_decisions
                )
                if chain_found:
                    linked += 1
                elif any(
                    item.state in {ActionState.STARTED, ActionState.UNKNOWN}
                    for item in hypothesis_actions
                ) or (
                    latest_verification is not None
                    and latest_verification.outcome in {
                        VerificationOutcome.INCONCLUSIVE,
                        VerificationOutcome.UNKNOWN,
                    }
                ) or any(
                    item.state in {DecisionState.PROPOSED, DecisionState.UNKNOWN}
                    for item in hypothesis_decisions
                ):
                    unresolved += 1
            if unresolved:
                overrides["logic.hypothesis_test_linkage"] = _unknown(
                    "typed_hypothesis_links_unresolved",
                    resolved=len(hypotheses) - unresolved,
                    eligible=len(hypotheses),
                )
            else:
                overrides["logic.hypothesis_test_linkage"] = _known(
                    "typed_hypothesis_test_links",
                    numerator=linked,
                    denominator=len(hypotheses),
                )

    if TypedEvidenceOpportunityKind.REQUIREMENT in declared:
        requirements = frozenset(projection.eligible_requirement_reference_ids)
        if not requirements:
            overrides["logic.requirement_action_traceability"] = _not_applicable(
                "typed_requirement_set_empty"
            )
            overrides["outcome.verified_requirement_coverage"] = _not_applicable(
                "typed_requirement_set_empty"
            )
        elif len(requirements) > MAX_OBJECTIVE_RECEIPT_OPPORTUNITIES:
            overrides["logic.requirement_action_traceability"] = (
                _receipt_bound_unknown()
            )
            overrides["outcome.verified_requirement_coverage"] = (
                _receipt_bound_unknown()
            )
        else:
            completed = frozenset(
                reference
                for record in actions
                if record.state is ActionState.COMPLETED
                for reference in record.requirement_reference_ids
            )
            unresolved_actions = frozenset(
                reference
                for record in actions
                if record.state in {ActionState.STARTED, ActionState.UNKNOWN}
                for reference in record.requirement_reference_ids
                if reference not in completed
            )
            if requirements & unresolved_actions:
                overrides["logic.requirement_action_traceability"] = _unknown(
                    "typed_requirement_action_links_unresolved",
                    resolved=len(requirements - unresolved_actions),
                    eligible=len(requirements),
                )
            else:
                overrides["logic.requirement_action_traceability"] = _known(
                    "typed_requirement_action_links",
                    numerator=len(requirements & completed),
                    denominator=len(requirements),
                )

            latest_requirement_verification = _latest_verification_by_reference(
                verifications,
                "requirement_reference_ids",
            )
            passing = frozenset(
                reference
                for reference, record in latest_requirement_verification.items()
                if record.outcome is VerificationOutcome.PASSED
            )
            unresolved_verifications = frozenset(
                reference
                for reference, record in latest_requirement_verification.items()
                if record.outcome
                in {
                    VerificationOutcome.INCONCLUSIVE,
                    VerificationOutcome.UNKNOWN,
                }
                if reference not in passing
            )
            if requirements & unresolved_verifications:
                overrides["outcome.verified_requirement_coverage"] = _unknown(
                    "typed_requirement_verification_links_unresolved",
                    resolved=len(requirements - unresolved_verifications),
                    eligible=len(requirements),
                )
            else:
                overrides["outcome.verified_requirement_coverage"] = _known(
                    "typed_requirement_verification_links",
                    numerator=len(requirements & passing),
                    denominator=len(requirements),
                )

    if TypedEvidenceOpportunityKind.MATERIAL_CLAIM in declared:
        claims = frozenset(projection.eligible_claim_reference_ids)
        if not claims:
            overrides["outcome.agent_claim_grounding"] = _not_applicable(
                "typed_claim_set_empty"
            )
        elif len(claims) > MAX_OBJECTIVE_RECEIPT_OPPORTUNITIES:
            overrides["outcome.agent_claim_grounding"] = _receipt_bound_unknown()
        else:
            latest_claim_verification = _latest_verification_by_reference(
                verifications,
                "claim_reference_ids",
            )
            grounded = 0
            unresolved = 0
            for claim_id in claims:
                evidence = latest_claim_verification.get(claim_id)
                if evidence is None or evidence.outcome is VerificationOutcome.FAILED:
                    continue
                if evidence.outcome is VerificationOutcome.PASSED:
                    grounded += 1
                elif (
                    evidence.outcome
                    in {
                        VerificationOutcome.INCONCLUSIVE,
                        VerificationOutcome.UNKNOWN,
                    }
                ):
                    unresolved += 1
            if unresolved:
                overrides["outcome.agent_claim_grounding"] = _unknown(
                    "typed_claim_grounding_unresolved",
                    resolved=len(claims) - unresolved,
                    eligible=len(claims),
                )
            else:
                overrides["outcome.agent_claim_grounding"] = _known(
                    "typed_claim_grounding_links",
                    numerator=grounded,
                    denominator=len(claims),
                )

    if TypedEvidenceOpportunityKind.VERIFICATION_TASK in declared:
        tasks = frozenset(projection.eligible_verification_task_reference_ids)
        if not tasks:
            overrides["outcome.first_pass_verification"] = _not_applicable(
                "typed_verification_task_set_empty"
            )
        elif len(tasks) > MAX_OBJECTIVE_RECEIPT_OPPORTUNITIES:
            overrides["outcome.first_pass_verification"] = _receipt_bound_unknown()
        else:
            passed = 0
            resolved = 0
            for task_id in tasks:
                outcomes = tuple(
                    sorted(
                        (
                            item
                            for item in verifications
                            if task_id in item.verification_task_reference_ids
                            and item.outcome
                            in {
                                VerificationOutcome.PASSED,
                                VerificationOutcome.FAILED,
                            }
                        ),
                        key=lambda item: item.sequence,
                    )
                )
                if not outcomes:
                    continue
                resolved += 1
                if outcomes[0].outcome is VerificationOutcome.PASSED:
                    passed += 1
            if resolved != len(tasks):
                overrides["outcome.first_pass_verification"] = _unknown(
                    "typed_first_verification_unresolved",
                    resolved=resolved,
                    eligible=len(tasks),
                )
            else:
                overrides["outcome.first_pass_verification"] = _known(
                    "typed_first_verification_outcomes",
                    numerator=passed,
                    denominator=len(tasks),
                )

    return overrides


__all__ = [
    "MAX_OBJECTIVE_RECEIPT_OPPORTUNITIES",
    "OBJECTIVE_EVIDENCE_METRIC_KEYS",
    "ObjectiveMetricOverride",
    "project_objective_metric_overrides",
]
