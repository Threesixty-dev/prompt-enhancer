"""Project persisted content-free provider events into ephemeral metric evidence.

The safe event index deliberately contains no command arguments, output, paths,
diffs, prompts, or snippets.  This adapter keeps that boundary: it constructs an
ephemeral typed-evidence graph from provider-reported kind/status metadata only.
The graph may guide objective metric contracts during one local run, but it is
never itself a persistence record and it never invents requirement links.
"""

from __future__ import annotations

from typing import Protocol

from ...domain import EventKind, Provider, SafeEvent, SafeSession, ToolCategory
from ..providers import CapabilityKey, DecoderDescriptor
from .evidence_contracts import (
    ActionEvidence,
    ActionFamily,
    ActionState,
    DecisionEvidence,
    DecisionState,
    EphemeralTypedEvidenceProjection,
    RationaleState,
    TypedEvidenceKind,
    TypedEvidenceOpportunityKind,
    TypedEvidenceProvenance,
    VerificationEvidence,
    VerificationMethod,
    VerificationOutcome,
    validate_projection_descriptor,
)
from .semantic_units import (
    SemanticUnitKind,
    SemanticUnitLifecycle,
    SemanticUnitReconciliation,
)


SAFE_EVENT_EVIDENCE_DECODER_KEY = "safe-event-evidence"
SAFE_EVENT_EVIDENCE_DECODER_VERSION = "2"


class SafeEventEvidenceSource(Protocol):
    """Read an already-pseudonymized local metadata snapshot."""

    def get_session(self, session_id: str) -> SafeSession | None: ...

    def get_session_events(self, session_id: str) -> tuple[SafeEvent, ...]: ...


class SafeEventEvidenceIdFactory(Protocol):
    def fingerprint(self, namespace: str, values: tuple[str, ...]) -> str: ...


def _action_family(category: ToolCategory | None) -> ActionFamily:
    if category is ToolCategory.FILE_WRITE:
        return ActionFamily.FILE_CHANGE
    if category in {ToolCategory.FILE_READ, ToolCategory.SEARCH}:
        return ActionFamily.REVIEW
    if category in {ToolCategory.COMMAND, ToolCategory.TEST, ToolCategory.BUILD}:
        return ActionFamily.COMMAND
    if category is None or category is ToolCategory.UNKNOWN:
        return ActionFamily.OTHER_DOCUMENTED
    return ActionFamily.TOOL


def _action_state(event: SafeEvent) -> ActionState:
    if event.kind is EventKind.TOOL_START:
        return ActionState.STARTED
    if event.success is True:
        return ActionState.COMPLETED
    if event.success is False:
        return ActionState.FAILED
    return ActionState.UNKNOWN


def _verification_method(category: ToolCategory | None) -> VerificationMethod:
    if category is ToolCategory.TEST:
        return VerificationMethod.TEST
    if category is ToolCategory.BUILD:
        return VerificationMethod.BUILD
    if category in {ToolCategory.FILE_READ, ToolCategory.SEARCH}:
        return VerificationMethod.ARTIFACT_INSPECTION
    return VerificationMethod.OTHER_DOCUMENTED


def _verification_outcome(event: SafeEvent) -> VerificationOutcome:
    if event.success is True:
        return VerificationOutcome.PASSED
    if event.success is False:
        return VerificationOutcome.FAILED
    return VerificationOutcome.UNKNOWN


class SafeEventTypedEvidenceProjector:
    """Create one bounded, content-free evidence projection for a local run."""

    def __init__(
        self,
        source: SafeEventEvidenceSource,
        identifiers: SafeEventEvidenceIdFactory,
        descriptor: DecoderDescriptor,
    ) -> None:
        self._source = source
        self._identifiers = identifiers
        if not isinstance(descriptor, DecoderDescriptor):
            raise ValueError("typed evidence requires a trusted decoder descriptor")
        self._descriptor = descriptor

    @property
    def descriptor(self) -> DecoderDescriptor:
        """The composition-root-selected authority for this projection."""

        return self._descriptor

    def project(
        self,
        *,
        provider: Provider,
        session_id: str,
    ) -> EphemeralTypedEvidenceProjection | None:
        session = self._source.get_session(session_id)
        if session is None or session.provider is not provider:
            return None
        events = tuple(
            sorted(
                self._source.get_session_events(session_id),
                key=lambda item: (item.sequence, item.event_id),
            )
        )
        records: list[ActionEvidence | DecisionEvidence | VerificationEvidence] = []
        declared_kinds = frozenset(
            kind
            for kind, capability in (
                (TypedEvidenceKind.ACTION, CapabilityKey.TOOL_EVENTS),
                (TypedEvidenceKind.DECISION, CapabilityKey.DECISION_EVENTS),
                (TypedEvidenceKind.VERIFICATION, CapabilityKey.VERIFICATION_EVENTS),
            )
            if capability in self._descriptor.capabilities
        )

        for event in events:
            if event.session_id != session_id:
                raise ValueError("safe event belongs to another session")
            base_sequence = event.sequence * 4
            if event.kind in {
                EventKind.TOOL_START,
                EventKind.TOOL_END,
                EventKind.ARTIFACT,
            }:
                if TypedEvidenceKind.ACTION not in declared_kinds:
                    raise ValueError("tool evidence capability is not authorized")
                records.append(
                    ActionEvidence(
                        evidence_id=self._evidence_id(
                            session_id, event.event_id, "action"
                        ),
                        sequence=base_sequence,
                        source_reference_id=event.event_id,
                        family=_action_family(event.tool_category),
                        state=_action_state(event),
                    )
                )
            if event.kind is EventKind.DECISION:
                if TypedEvidenceKind.DECISION not in declared_kinds:
                    raise ValueError("decision evidence capability is not authorized")
                records.append(
                    DecisionEvidence(
                        evidence_id=self._evidence_id(
                            session_id, event.event_id, "decision"
                        ),
                        sequence=base_sequence + 1,
                        source_reference_id=event.event_id,
                        state=(
                            DecisionState.ACCEPTED
                            if event.success is True
                            else DecisionState.REJECTED
                            if event.success is False
                            else DecisionState.UNKNOWN
                        ),
                        rationale_state=RationaleState.UNKNOWN,
                    )
                )
            if event.kind is EventKind.VERIFICATION or (
                event.kind is EventKind.TOOL_END
                and event.tool_category in {ToolCategory.TEST, ToolCategory.BUILD}
            ):
                # A documented tool event may be authoritative for ACTION but
                # not for VERIFICATION. Keep the declared action and omit the
                # stronger evidence kind rather than failing the entire local
                # projection or upgrading the decoder's capability.
                if TypedEvidenceKind.VERIFICATION in declared_kinds:
                    records.append(
                        VerificationEvidence(
                            evidence_id=self._evidence_id(
                                session_id, event.event_id, "verification"
                            ),
                            sequence=base_sequence + 2,
                            source_reference_id=event.event_id,
                            method=_verification_method(event.tool_category),
                            outcome=_verification_outcome(event),
                            receipt_reference_ids=(event.event_id,),
                        )
                    )

        projection = EphemeralTypedEvidenceProjection(
            session_id=session_id,
            provenance=TypedEvidenceProvenance(
                provider=provider,
                provider_version=session.provider_version,
                adapter_version=session.adapter_version,
                decoder_key=SAFE_EVENT_EVIDENCE_DECODER_KEY,
                decoder_version=SAFE_EVENT_EVIDENCE_DECODER_VERSION,
                source_schema_version=session.source_schema_version,
                extraction_complete=session.events_complete,
            ),
            declared_kinds=declared_kinds,
            records=tuple(sorted(records, key=lambda item: item.sequence)),
        )
        validate_projection_descriptor(projection, self._descriptor)
        return projection

    def _evidence_id(
        self,
        session_id: str,
        event_id: str,
        kind: str,
    ) -> str:
        return self._identifiers.fingerprint(
            "typed-safe-event-evidence-v2",
            (session_id, event_id, kind),
        )


def bind_semantic_unit_opportunities(
    projection: EphemeralTypedEvidenceProjection | None,
    reconciliation: SemanticUnitReconciliation | None,
) -> EphemeralTypedEvidenceProjection | None:
    """Bind exact semantic-unit denominators without persisting their links.

    Only a complete reconciliation may enlarge a denominator family that the
    evidence adapter already declared it can link. Active requirement units
    define that requirement denominator. Hypotheses are included only after
    closure; an open/right-censored episode must remain pending rather than
    become a measured failure.
    """

    if projection is None or reconciliation is None:
        return projection
    if (
        projection.provenance.provider is not reconciliation.provider
        or projection.session_id != reconciliation.session_id
    ):
        raise ValueError("typed evidence and semantic units use different providers")
    if not reconciliation.source_complete:
        return projection

    requirements = frozenset(
        item.unit_id
        for item in reconciliation.heads
        if item.kind is SemanticUnitKind.REQUIREMENT
        and item.lifecycle is not SemanticUnitLifecycle.SUPERSEDED
    ) if (
        TypedEvidenceOpportunityKind.REQUIREMENT
        in projection.declared_opportunity_kinds
    ) else frozenset()
    hypotheses = frozenset(
        item.unit_id
        for item in reconciliation.heads
        if item.kind is SemanticUnitKind.HYPOTHESIS
        and item.lifecycle is SemanticUnitLifecycle.CLOSED
    ) if (
        TypedEvidenceOpportunityKind.HYPOTHESIS
        in projection.declared_opportunity_kinds
    ) else frozenset()

    payload = projection.model_dump()
    payload.update(
        {
            "declared_opportunity_kinds": projection.declared_opportunity_kinds,
            "eligible_requirement_reference_ids": tuple(
                sorted(
                    requirements
                    | frozenset(projection.eligible_requirement_reference_ids)
                )
            ),
            "eligible_hypothesis_reference_ids": tuple(
                sorted(
                    hypotheses
                    | frozenset(projection.eligible_hypothesis_reference_ids)
                )
            ),
            "records": projection.records,
        }
    )
    return EphemeralTypedEvidenceProjection.model_validate(payload)


__all__ = [
    "SAFE_EVENT_EVIDENCE_DECODER_KEY",
    "SAFE_EVENT_EVIDENCE_DECODER_VERSION",
    "SafeEventEvidenceIdFactory",
    "SafeEventEvidenceSource",
    "SafeEventTypedEvidenceProjector",
    "bind_semantic_unit_opportunities",
]
