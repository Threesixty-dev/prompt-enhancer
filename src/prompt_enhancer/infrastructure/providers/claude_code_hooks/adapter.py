"""Read-only ``ProviderAdapter`` over the Claude Code hook ledger.

The adapter never touches Claude Code, its settings, or its transcripts.  Its
only source is the local append-only ledger the hook receiver fills, so every
value it yields was already minimized under an active consent grant.  It
speaks the same port as the Codex adapter: probe first, list a bounded
snapshot, then read only sessions that belong to that snapshot.

Identifiers it yields are already installation-local pseudonyms; the ordinary
ingestion service protects them again under the provider namespace exactly as
it does for any other source, so downstream storage cannot tell the sources
apart by shape.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import SecretStr

from ....adapters.base import AdapterHealth, AdapterProbe, ProviderAdapter
from ....application.providers import (
    CapabilityKey,
    CapabilityObservation,
    CapabilityState,
    CompatibilityReason,
    CompatibilityReasonCode,
    CompatibilityState,
    DecoderDescriptor,
    ExtractionCompleteness,
    ExtractionCompletenessState,
    ProviderCompatibilityReport,
    ProviderIdentity,
    ProviderSurface,
    SchemaArtifactKind,
    SchemaArtifactProvenance,
)
from ....domain import (
    DataTier,
    EventTimeBasis,
    Provider,
    SessionState,
    SourceEvent,
    SourceSession,
    SourceSessionPage,
    SourceSessionSnapshot,
)
from .contracts import (
    ADAPTER_VERSION,
    HOOK_INSTALLATION_MARKER,
    SOURCE_SCHEMA_VERSION,
    UNKNOWN_PROVIDER_VERSION,
    SessionEndReason,
)
from .ledger import LedgerEvent, LedgerSession, SqliteClaudeHookLedger


MAX_HOOK_PAGE_SIZE = 500
MAX_HOOK_PAGES = 200

# Every capability the hooks decoder can honestly claim.  It deliberately
# declares no ``*_opportunities`` or ``*_links`` member and no message content
# capability: hooks enumerate no requirements, hypotheses, or verification
# tasks, and the receiver never keeps text.  ``EVENT_TIMING`` is the one claim
# the Codex safe-event decoder cannot make - each hook fires synchronously at
# its event, so the receipt clock orders and times every record.
CLAUDE_CODE_HOOK_CAPABILITIES: tuple[CapabilityKey, ...] = (
    CapabilityKey.SESSION_LIST,
    CapabilityKey.SESSION_LABELS,
    CapabilityKey.OPERATIONAL_EVENTS,
    CapabilityKey.TOOL_EVENTS,
    CapabilityKey.EVENT_TIMING,
)

CLAUDE_CODE_HOOKS_DECODER_DESCRIPTOR = DecoderDescriptor(
    provider=ProviderIdentity(key="claude_code"),
    surface=ProviderSurface.OPERATIONAL_EVENTS,
    adapter_version=ADAPTER_VERSION,
    decoder_key="claude-code.hooks.operational-events",
    decoder_version="1",
    wire_schema_family="claude-code.hooks.v1",
    canonical_schema_version=SOURCE_SCHEMA_VERSION,
    schema_artifact=SchemaArtifactProvenance(
        artifact_key="claude-code.hooks.documented-payload",
        artifact_version="1",
        kind=SchemaArtifactKind.DOCUMENTED,
    ),
    capabilities=CLAUDE_CODE_HOOK_CAPABILITIES,
    tested_provider_versions=(),
)


class ClaudeHookAdapterError(RuntimeError):
    """Content-free adapter failure."""


class ClaudeHookScopeError(ClaudeHookAdapterError):
    """A read was requested outside the current listed snapshot."""


class ClaudeHookLifecycleError(ClaudeHookAdapterError):
    """The adapter was used before a successful probe or after close."""


def _terminal_state(session: LedgerSession) -> SessionState:
    """Map only what the provider's end reason actually says.

    ``prompt_input_exit`` is the user closing an idle prompt - the ordinary
    completion of a session's lifecycle.  ``logout`` interrupts it.  ``clear``
    and ``other`` are ambiguous, and a session with no end event may still be
    live, so all of those stay unknown rather than borrowing an outcome.
    """

    if session.ended_at is None or session.session_end_reason is None:
        return SessionState.UNKNOWN
    if session.session_end_reason is SessionEndReason.PROMPT_INPUT_EXIT:
        return SessionState.COMPLETED
    if session.session_end_reason is SessionEndReason.LOGOUT:
        return SessionState.INTERRUPTED
    return SessionState.UNKNOWN


def _source_session(session: LedgerSession) -> SourceSession:
    return SourceSession(
        provider=Provider.CLAUDE_CODE,
        source_installation_id=SecretStr(HOOK_INSTALLATION_MARKER),
        source_project_id=SecretStr(session.hook_project_id),
        source_session_id=SecretStr(session.hook_session_id),
        provider_version=UNKNOWN_PROVIDER_VERSION,
        adapter_version=ADAPTER_VERSION,
        source_schema_version=SOURCE_SCHEMA_VERSION,
        started_at=session.first_received_at,
        source_activity_at=session.last_received_at,
        ended_at=session.ended_at,
        terminal_state=_terminal_state(session),
        # A hook configuration cannot prove it covered every event, and the
        # receiver drops rather than blocks under contention, so completeness
        # is never claimed; metrics run at bounded confidence.
        events_complete=False,
        source_project_display_name=(
            None
            if session.project_display_label is None
            else SecretStr(session.project_display_label)
        ),
        source_session_display_name=None,
    )


def _source_event(event: LedgerEvent) -> SourceEvent:
    return SourceEvent(
        source_event_id=SecretStr(event.hook_event_id),
        kind=event.event_kind,
        sequence=event.sequence,
        occurred_at=event.received_at,
        # The provider supplies no timestamp; the receiver stamps the receipt
        # of a synchronous hook.  SOURCE_SCHEMA_VERSION names that clock.
        time_basis=EventTimeBasis.PROVIDER_REPORTED,
        duration_ms=event.duration_ms,
        success=event.success,
        tool_category=event.tool_category,
        usage=None,
    )


class ClaudeCodeHookAdapter(ProviderAdapter):
    """Read-only adapter over the local hook ledger; construction reads nothing."""

    provider = Provider.CLAUDE_CODE

    def __init__(self, ledger: SqliteClaudeHookLedger) -> None:
        self._ledger = ledger
        self._health = AdapterHealth.UNAVAILABLE
        self._probed = False
        self._closed = False
        self._page_count = 0
        self._cursor_counter = 0
        self._cursors: dict[str, tuple[datetime, str]] = {}
        self._listed: dict[str, SourceSession] = {}

    @property
    def required_consent_tier(self) -> DataTier:
        # The hook payload transits content in memory before minimization, so
        # capture requires the same tier as the Codex list surface, whose
        # documented preview field puts it in the same position.
        return DataTier.REDACTED_CONTENT

    @property
    def requires_explicit_selection(self) -> bool:
        return False

    def probe(self) -> AdapterProbe:
        if self._closed:
            raise ClaudeHookLifecycleError("Claude Code hook adapter is closed")
        try:
            self._ledger.summary()
            self._health = AdapterHealth.READY
        except Exception:
            self._health = AdapterHealth.UNAVAILABLE
        self._probed = True
        return AdapterProbe(
            provider=self.provider,
            provider_version=UNKNOWN_PROVIDER_VERSION,
            adapter_version=ADAPTER_VERSION,
            source_schema_version=SOURCE_SCHEMA_VERSION,
            supports_metadata=True,
            supports_content=False,
            supports_watch=False,
            health=self._health,
        )

    def _ready(self) -> SqliteClaudeHookLedger:
        if self._closed:
            raise ClaudeHookLifecycleError("Claude Code hook adapter is closed")
        if not self._probed or self._health is not AdapterHealth.READY:
            raise ClaudeHookLifecycleError(
                "a successful probe is required before source access"
            )
        return self._ledger

    def _reset_snapshot(self) -> None:
        self._page_count = 0
        self._cursor_counter = 0
        self._cursors.clear()
        self._listed.clear()

    def list_sessions(
        self, *, cursor: str | None = None, limit: int = 100
    ) -> SourceSessionPage:
        ledger = self._ready()
        if limit < 1 or limit > MAX_HOOK_PAGE_SIZE:
            raise ValueError("limit must be within the configured page bound")
        if cursor is None:
            self._reset_snapshot()
            after: tuple[datetime, str] | None = None
        else:
            try:
                after = self._cursors.pop(cursor)
            except KeyError:
                raise ClaudeHookScopeError(
                    "pagination cursor is not part of this snapshot"
                ) from None
        if self._page_count >= MAX_HOOK_PAGES:
            raise ClaudeHookAdapterError("session listing exceeded the page bound")

        rows = ledger.list_sessions(limit=limit + 1, after=after)
        has_more = len(rows) > limit
        rows = rows[:limit]
        sessions: list[SourceSession] = []
        for row in rows:
            if row.hook_session_id in self._listed:
                raise ClaudeHookAdapterError("ledger repeated a session in one snapshot")
            session = _source_session(row)
            self._listed[row.hook_session_id] = session
            sessions.append(session)
        self._page_count += 1

        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            self._cursor_counter += 1
            next_cursor = f"p{self._cursor_counter}"
            self._cursors[next_cursor] = (last.first_received_at, last.hook_session_id)
        return SourceSessionPage(sessions=tuple(sessions), next_cursor=next_cursor)

    def read_session(self, session: SourceSession) -> SourceSessionSnapshot:
        ledger = self._ready()
        hook_session_id = session.source_session_id.get_secret_value()
        listed = self._listed.get(hook_session_id)
        if listed is None or listed != session:
            raise ClaudeHookScopeError("session is not part of the current listed snapshot")
        events = tuple(_source_event(event) for event in ledger.list_events(hook_session_id))
        return SourceSessionSnapshot(session=session, events=events)

    def read_events(self, session: SourceSession) -> Iterator[SourceEvent]:
        yield from self.read_session(session).events

    def health(self) -> AdapterHealth:
        return self._health

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._health = AdapterHealth.UNAVAILABLE
        self._reset_snapshot()


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ClaudeCodeHooksCompatibilityProbe:
    """Compatibility report for the hook surface; reads only the local ledger."""

    ledger: SqliteClaudeHookLedger
    _clock: Clock = field(default=_utc_now, repr=False)

    @property
    def descriptor(self) -> DecoderDescriptor:
        return CLAUDE_CODE_HOOKS_DECODER_DESCRIPTOR

    def check(self) -> ProviderCompatibilityReport:
        try:
            checked_at = self._clock().astimezone(UTC)
        except Exception:
            checked_at = datetime.now(UTC)
        try:
            summary = self.ledger.summary()
        except Exception:
            return ProviderCompatibilityReport(
                descriptor=self.descriptor,
                provider_version=UNKNOWN_PROVIDER_VERSION,
                state=CompatibilityState.UNAVAILABLE,
                capabilities=tuple(
                    CapabilityObservation(
                        key=capability,
                        state=CapabilityState.UNKNOWN,
                        reason_code=CompatibilityReasonCode.PROVIDER_UNAVAILABLE,
                    )
                    for capability in self.descriptor.capabilities
                ),
                extraction=ExtractionCompleteness(
                    state=ExtractionCompletenessState.NONE, observed_units=0
                ),
                reasons=(
                    CompatibilityReason(code=CompatibilityReasonCode.PROVIDER_UNAVAILABLE),
                ),
                checked_at=checked_at,
            )
        # The decoder fully understands every payload it admits, but it can
        # neither attest to the Claude Code version (hook payloads carry none)
        # nor prove that the user's hook configuration delivered every event.
        # That is a degraded, unknown-completeness surface, and it says so.
        return ProviderCompatibilityReport(
            descriptor=self.descriptor,
            provider_version=UNKNOWN_PROVIDER_VERSION,
            state=CompatibilityState.DEGRADED,
            capabilities=tuple(
                CapabilityObservation(key=capability, state=CapabilityState.SUPPORTED)
                for capability in self.descriptor.capabilities
            ),
            extraction=ExtractionCompleteness(
                state=ExtractionCompletenessState.UNKNOWN,
                observed_units=min(int(summary["events"]), 10_000_000),
            ),
            reasons=(
                CompatibilityReason(code=CompatibilityReasonCode.PROVIDER_VERSION_UNKNOWN),
            ),
            checked_at=checked_at,
        )


__all__ = (
    "CLAUDE_CODE_HOOKS_DECODER_DESCRIPTOR",
    "CLAUDE_CODE_HOOK_CAPABILITIES",
    "ClaudeCodeHookAdapter",
    "ClaudeCodeHooksCompatibilityProbe",
    "ClaudeHookAdapterError",
    "ClaudeHookLifecycleError",
    "ClaudeHookScopeError",
    "MAX_HOOK_PAGES",
    "MAX_HOOK_PAGE_SIZE",
)
