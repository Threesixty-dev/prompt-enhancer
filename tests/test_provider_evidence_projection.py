from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from prompt_enhancer.application.analysis.evidence_contracts import (
    ActionFamily,
    ActionState,
    DecisionState,
    RationaleState,
    TypedEvidenceKind,
    TypedEvidenceOpportunityKind,
    VerificationMethod,
    VerificationOutcome,
)
from prompt_enhancer.application.analysis.provider_evidence import (
    SAFE_EVENT_EVIDENCE_DECODER_KEY,
    SAFE_EVENT_EVIDENCE_DECODER_VERSION,
    SafeEventTypedEvidenceProjector,
    bind_semantic_unit_opportunities,
)
from prompt_enhancer.application.analysis.objective_metric_projection import (
    project_objective_metric_overrides,
)
from prompt_enhancer.application.analysis.text_contracts import MetricValueState
from prompt_enhancer.application.analysis.semantic_units import (
    SemanticUnitExtractionBasis,
    SemanticUnitKind,
    SemanticUnitLifecycle,
    SemanticUnitReceipt,
    SemanticUnitReconciliation,
)
from prompt_enhancer.application.providers import (
    CapabilityKey,
    DecoderDescriptor,
    ProviderIdentity,
    ProviderSurface,
    SchemaArtifactKind,
    SchemaArtifactProvenance,
)
from prompt_enhancer.domain import (
    EventKind,
    Provider,
    SafeEvent,
    SafeSession,
    SessionState,
    ToolCategory,
)


SESSION_ID = "a" * 64


class _Source:
    def __init__(
        self,
        session: SafeSession | None,
        events: tuple[SafeEvent, ...],
    ) -> None:
        self.session = session
        self.events = events

    def get_session(self, session_id: str) -> SafeSession | None:
        assert session_id == SESSION_ID
        return self.session

    def get_session_events(self, session_id: str) -> tuple[SafeEvent, ...]:
        assert session_id == SESSION_ID
        return self.events


class _Ids:
    def fingerprint(self, namespace: str, values: tuple[str, ...]) -> str:
        assert namespace == "typed-safe-event-evidence-v2"
        return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()


def _descriptor(*capabilities: CapabilityKey) -> DecoderDescriptor:
    return DecoderDescriptor(
        provider=ProviderIdentity(key="codex"),
        surface=ProviderSurface.OPERATIONAL_EVENTS,
        adapter_version="synthetic-adapter-v1",
        decoder_key=SAFE_EVENT_EVIDENCE_DECODER_KEY,
        decoder_version=SAFE_EVENT_EVIDENCE_DECODER_VERSION,
        wire_schema_family="synthetic-safe-events",
        canonical_schema_version="synthetic-schema-v1",
        schema_artifact=SchemaArtifactProvenance(
            artifact_key="synthetic-safe-events",
            artifact_version="1",
            kind=SchemaArtifactKind.SYNTHETIC,
        ),
        capabilities=capabilities,
    )


DESCRIPTOR = _descriptor(
    CapabilityKey.TOOL_EVENTS,
    CapabilityKey.DECISION_EVENTS,
    CapabilityKey.VERIFICATION_EVENTS,
)


def _session(*, complete: bool = True) -> SafeSession:
    return SafeSession(
        provider=Provider.CODEX,
        installation_id="b" * 64,
        project_id="c" * 64,
        session_id=SESSION_ID,
        provider_version="synthetic-provider-v1",
        adapter_version="synthetic-adapter-v1",
        source_schema_version="synthetic-schema-v1",
        started_at=datetime(2040, 1, 1, tzinfo=UTC),
        terminal_state=SessionState.COMPLETED,
        events_complete=complete,
    )


def _event(
    ordinal: int,
    kind: EventKind,
    *,
    category: ToolCategory | None = None,
    success: bool | None = None,
) -> SafeEvent:
    return SafeEvent(
        session_id=SESSION_ID,
        event_id=f"{ordinal:x}" * 64,
        kind=kind,
        sequence=ordinal,
        occurred_at=datetime(2040, 1, 1, 10, ordinal, tzinfo=UTC),
        tool_category=category,
        success=success,
    )


def test_projects_content_free_actions_decisions_and_verification() -> None:
    projection = SafeEventTypedEvidenceProjector(
        _Source(
            _session(),
            (
                _event(1, EventKind.TOOL_START, category=ToolCategory.FILE_WRITE),
                _event(
                    2,
                    EventKind.TOOL_END,
                    category=ToolCategory.TEST,
                    success=True,
                ),
                _event(3, EventKind.DECISION, success=True),
            ),
        ),
        _Ids(),
        DESCRIPTOR,
    ).project(provider=Provider.CODEX, session_id=SESSION_ID)

    assert projection is not None
    assert projection.provenance.extraction_complete is True
    assert projection.declared_kinds == frozenset(
        {
            TypedEvidenceKind.ACTION,
            TypedEvidenceKind.DECISION,
            TypedEvidenceKind.VERIFICATION,
        }
    )
    assert len(projection.records) == 4
    first, second, verification, decision = projection.records
    assert (first.family, first.state) == (
        ActionFamily.FILE_CHANGE,
        ActionState.STARTED,
    )
    assert (second.family, second.state) == (
        ActionFamily.COMMAND,
        ActionState.COMPLETED,
    )
    assert (verification.method, verification.outcome) == (
        VerificationMethod.TEST,
        VerificationOutcome.PASSED,
    )
    assert verification.receipt_reference_ids == ("2" * 64,)
    assert (decision.state, decision.rationale_state) == (
        DecisionState.ACCEPTED,
        RationaleState.UNKNOWN,
    )
    assert [item.sequence for item in projection.records] == [4, 8, 10, 13]


def test_incomplete_event_stream_stays_explicit_and_empty_is_valid() -> None:
    projection = SafeEventTypedEvidenceProjector(
        _Source(_session(complete=False), ()),
        _Ids(),
        DESCRIPTOR,
    ).project(provider=Provider.CODEX, session_id=SESSION_ID)

    assert projection is not None
    assert projection.provenance.extraction_complete is False
    assert projection.records == ()


def test_current_safe_events_without_semantic_links_never_become_numeric() -> None:
    projection = SafeEventTypedEvidenceProjector(
        _Source(
            _session(),
            (
                _event(
                    1,
                    EventKind.TOOL_END,
                    category=ToolCategory.TEST,
                    success=True,
                ),
            ),
        ),
        _Ids(),
        DESCRIPTOR,
    ).project(provider=Provider.CODEX, session_id=SESSION_ID)

    assert projection is not None
    result = project_objective_metric_overrides(projection, DESCRIPTOR)
    assert len(result) == 5
    assert all(
        item.value_state is MetricValueState.UNKNOWN for item in result.values()
    )


def test_missing_or_wrong_provider_session_is_not_projected() -> None:
    projector = SafeEventTypedEvidenceProjector(
        _Source(None, ()), _Ids(), DESCRIPTOR
    )
    assert projector.project(provider=Provider.CODEX, session_id=SESSION_ID) is None

    projector = SafeEventTypedEvidenceProjector(
        _Source(_session(), ()), _Ids(), DESCRIPTOR
    )
    assert (
        projector.project(provider=Provider.CLAUDE_CODE, session_id=SESSION_ID)
        is None
    )


def test_projection_rejects_descriptor_without_authoritative_capabilities() -> None:
    projector = SafeEventTypedEvidenceProjector(
        _Source(
            _session(),
            (_event(1, EventKind.TOOL_END, category=ToolCategory.TEST),),
        ),
        _Ids(),
        _descriptor(CapabilityKey.USER_MESSAGES),
    )

    with pytest.raises(ValueError, match="not authorized"):
        projector.project(provider=Provider.CODEX, session_id=SESSION_ID)


def test_tool_only_descriptor_skips_undeclared_verification_evidence() -> None:
    projection = SafeEventTypedEvidenceProjector(
        _Source(
            _session(),
            (
                _event(
                    1,
                    EventKind.TOOL_END,
                    category=ToolCategory.TEST,
                    success=True,
                ),
                _event(2, EventKind.VERIFICATION, success=True),
            ),
        ),
        _Ids(),
        _descriptor(CapabilityKey.TOOL_EVENTS),
    ).project(provider=Provider.CODEX, session_id=SESSION_ID)

    assert projection is not None
    assert projection.declared_kinds == frozenset({TypedEvidenceKind.ACTION})
    assert len(projection.records) == 1
    assert projection.records[0].kind is TypedEvidenceKind.ACTION


def test_complete_semantic_requirement_set_becomes_authoritative_denominator() -> None:
    projection = SafeEventTypedEvidenceProjector(
        _Source(_session(), ()),
        _Ids(),
        DESCRIPTOR,
    ).project(provider=Provider.CODEX, session_id=SESSION_ID)
    assert projection is not None
    projection = projection.model_copy(
        update={
            "declared_opportunity_kinds": frozenset(
                {TypedEvidenceOpportunityKind.REQUIREMENT}
            )
        }
    )
    requirement = SemanticUnitReceipt(
        provider=Provider.CODEX,
        session_id=SESSION_ID,
        receipt_id="1" * 64,
        unit_id="2" * 64,
        unit_digest="3" * 64,
        revision=1,
        kind=SemanticUnitKind.REQUIREMENT,
        lifecycle=SemanticUnitLifecycle.CLOSED,
        extraction_basis=SemanticUnitExtractionBasis.TYPED_PROVIDER_EVENT,
        owner_source_digest="4" * 64,
        source_digests=("4" * 64,),
        source_version_digest="5" * 64,
        first_sequence=1,
        closed_at_sequence=1,
    )
    reconciliation = SemanticUnitReconciliation(
        provider=Provider.CODEX,
        session_id=SESSION_ID,
        analysis_window_fingerprint="6" * 64,
        source_complete=True,
        reconciliation_id="7" * 64,
        heads=(requirement,),
        appended=(requirement,),
        unchanged_receipt_ids=(),
        retained_unobserved_unit_count=0,
    )

    bound = bind_semantic_unit_opportunities(projection, reconciliation)
    without_link_authority = bind_semantic_unit_opportunities(
        projection.model_copy(update={"declared_opportunity_kinds": frozenset()}),
        reconciliation,
    )

    assert bound is not None
    assert bound.eligible_requirement_reference_ids == (requirement.unit_id,)
    assert without_link_authority is not None
    assert without_link_authority.eligible_requirement_reference_ids == ()
