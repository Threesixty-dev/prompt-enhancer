"""Append-only SQLite ledger for minimized Claude Code hook events.

Two callers share this module with different trust postures:

* the hook receiver appends one event per invocation.  It runs inside the
  user's Claude Code session, must finish quickly, must never create or
  migrate the store, and must fail *silent* rather than fail the session; and
* the provider adapter reads sessions and events back so the ordinary
  ingestion pipeline can pseudonymize and persist them like any other source.

Sequence numbers are assigned inside one ``BEGIN IMMEDIATE`` transaction so
two hook processes for the same session (parallel tool calls) cannot collide.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

from ....domain import DataTier, EventKind, Provider, StrictModel, ToolCategory
from ....privacy import Pseudonymizer
from ...sqlite._common import ConnectionScope, from_iso, require_safe_id, to_iso
from .contracts import (
    CONTRACT_VERSION,
    HOOK_INSTALLATION_MARKER,
    MAX_HOOK_EVENTS_PER_SESSION,
    MAX_TOOL_PAIRING_WINDOW,
    RECEIVER_VERSION,
    CompactTrigger,
    HookEventName,
    MinimizedHookEvent,
    SessionEndReason,
    SessionStartSource,
)


LEDGER_SCHEMA_VERSION = 45
RECEIVER_BUSY_TIMEOUT_MS = 250
_CONSENT_TIER = DataTier.REDACTED_CONTENT


class HookLedgerUnavailable(RuntimeError):
    """The store is absent, older than the ledger schema, or locked."""


class HookLedgerConsentInactive(RuntimeError):
    """No active claude_code local-history consent; nothing may be written."""


class LedgerSession(StrictModel):
    hook_session_id: str
    hook_project_id: str
    project_display_label: str | None = None
    contract_version: str
    receiver_version: str
    first_received_at: datetime
    last_received_at: datetime
    session_start_source: SessionStartSource | None = None
    session_end_reason: SessionEndReason | None = None
    ended_at: datetime | None = None
    event_count: int


class LedgerEvent(StrictModel):
    hook_event_id: str
    hook_session_id: str
    sequence: int
    received_at: datetime
    hook_event_name: HookEventName
    event_kind: EventKind
    tool_category: ToolCategory | None = None
    tool_use_ref: str | None = None
    duration_ms: int | None = None
    success: bool | None = None
    session_start_source: SessionStartSource | None = None
    session_end_reason: SessionEndReason | None = None
    compact_trigger: CompactTrigger | None = None


class AppendOutcome(StrictModel):
    hook_event_id: str
    sequence: int
    paired_duration_ms: int | None = None


def _event_identity(
    pseudonymizer: Pseudonymizer, hook_session_id: str, sequence: int
) -> str:
    return pseudonymizer.pseudonymize(
        f"claude_code:hook-event:{hook_session_id}", f"{sequence}"
    )


def _row_session(row: sqlite3.Row) -> LedgerSession:
    first = from_iso(row["first_received_at"])
    last = from_iso(row["last_received_at"])
    assert first is not None and last is not None
    return LedgerSession(
        hook_session_id=row["hook_session_id"],
        hook_project_id=row["hook_project_id"],
        project_display_label=row["project_display_label"],
        contract_version=row["contract_version"],
        receiver_version=row["receiver_version"],
        first_received_at=first,
        last_received_at=last,
        session_start_source=(
            None
            if row["session_start_source"] is None
            else SessionStartSource(row["session_start_source"])
        ),
        session_end_reason=(
            None
            if row["session_end_reason"] is None
            else SessionEndReason(row["session_end_reason"])
        ),
        ended_at=from_iso(row["ended_at"]),
        event_count=int(row["event_count"]),
    )


def _row_event(row: sqlite3.Row) -> LedgerEvent:
    received = from_iso(row["received_at"])
    assert received is not None
    return LedgerEvent(
        hook_event_id=row["hook_event_id"],
        hook_session_id=row["hook_session_id"],
        sequence=int(row["sequence"]),
        received_at=received,
        hook_event_name=HookEventName(row["hook_event_name"]),
        event_kind=EventKind(row["event_kind"]),
        tool_category=(
            None if row["tool_category"] is None else ToolCategory(row["tool_category"])
        ),
        tool_use_ref=row["tool_use_ref"],
        duration_ms=row["duration_ms"],
        success=None if row["success"] is None else bool(row["success"]),
        session_start_source=(
            None
            if row["session_start_source"] is None
            else SessionStartSource(row["session_start_source"])
        ),
        session_end_reason=(
            None
            if row["session_end_reason"] is None
            else SessionEndReason(row["session_end_reason"])
        ),
        compact_trigger=(
            None if row["compact_trigger"] is None else CompactTrigger(row["compact_trigger"])
        ),
    )


def _append(
    connection: sqlite3.Connection,
    pseudonymizer: Pseudonymizer,
    event: MinimizedHookEvent,
) -> AppendOutcome:
    """Append one event and maintain the session row inside the caller's txn."""

    received_iso = to_iso(event.received_at)
    session_row = connection.execute(
        """SELECT event_count, first_received_at FROM claude_code_hook_sessions
           WHERE hook_session_id=?""",
        (event.hook_session_id,),
    ).fetchone()
    if session_row is None:
        connection.execute(
            """INSERT INTO claude_code_hook_sessions(
                   hook_session_id, hook_project_id, project_display_label,
                   contract_version, receiver_version,
                   first_received_at, last_received_at,
                   session_start_source, session_end_reason, ended_at, event_count)
               VALUES (?,?,?,?,?,?,?,?,NULL,NULL,0)""",
            (
                event.hook_session_id,
                event.hook_project_id,
                event.project_display_label,
                CONTRACT_VERSION,
                RECEIVER_VERSION,
                received_iso,
                received_iso,
                (
                    event.session_start_source.value
                    if event.session_start_source is not None
                    else None
                ),
            ),
        )
        sequence = 0
    else:
        sequence = int(session_row["event_count"])
        if sequence >= MAX_HOOK_EVENTS_PER_SESSION:
            raise HookLedgerUnavailable("hook session event bound reached")

    paired_duration: int | None = None
    if (
        event.hook_event_name is HookEventName.POST_TOOL_USE
        and event.tool_use_ref is not None
    ):
        opener = connection.execute(
            """SELECT received_at FROM claude_code_hook_events
               WHERE hook_session_id=? AND tool_use_ref=? AND hook_event_name='PreToolUse'
               ORDER BY sequence DESC LIMIT 1""",
            (event.hook_session_id, event.tool_use_ref),
        ).fetchone()
        if opener is not None:
            opened_at = from_iso(opener["received_at"])
            assert opened_at is not None
            delta = event.received_at.astimezone(UTC) - opened_at
            if timedelta(0) <= delta <= MAX_TOOL_PAIRING_WINDOW:
                paired_duration = round(delta.total_seconds() * 1_000)

    hook_event_id = _event_identity(pseudonymizer, event.hook_session_id, sequence)
    connection.execute(
        """INSERT INTO claude_code_hook_events(
               hook_event_id, hook_session_id, sequence, received_at,
               hook_event_name, event_kind, tool_category, tool_use_ref,
               duration_ms, success, session_start_source, session_end_reason,
               compact_trigger)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            hook_event_id,
            event.hook_session_id,
            sequence,
            received_iso,
            event.hook_event_name.value,
            event.event_kind.value,
            None if event.tool_category is None else event.tool_category.value,
            event.tool_use_ref,
            paired_duration,
            None if event.success is None else int(event.success),
            (
                event.session_start_source.value
                if event.session_start_source is not None
                else None
            ),
            (
                event.session_end_reason.value
                if event.session_end_reason is not None
                else None
            ),
            None if event.compact_trigger is None else event.compact_trigger.value,
        ),
    )

    # A SessionEnd closes the session; any later event reopens it, because a
    # resumed session keeps its provider identifier.  The session row keeps
    # the first observed start source; every event row keeps its own.
    if event.hook_event_name is HookEventName.SESSION_END:
        connection.execute(
            """UPDATE claude_code_hook_sessions
               SET last_received_at=?, event_count=event_count+1,
                   session_end_reason=?, ended_at=?
               WHERE hook_session_id=?""",
            (
                received_iso,
                (
                    event.session_end_reason.value
                    if event.session_end_reason is not None
                    else SessionEndReason.UNKNOWN.value
                ),
                received_iso,
                event.hook_session_id,
            ),
        )
    elif event.hook_event_name is HookEventName.SESSION_START:
        connection.execute(
            """UPDATE claude_code_hook_sessions
               SET last_received_at=?, event_count=event_count+1,
                   session_end_reason=NULL, ended_at=NULL,
                   session_start_source=COALESCE(session_start_source, ?),
                   project_display_label=COALESCE(project_display_label, ?)
               WHERE hook_session_id=?""",
            (
                received_iso,
                (
                    event.session_start_source.value
                    if event.session_start_source is not None
                    else None
                ),
                event.project_display_label,
                event.hook_session_id,
            ),
        )
    else:
        connection.execute(
            """UPDATE claude_code_hook_sessions
               SET last_received_at=?, event_count=event_count+1,
                   session_end_reason=NULL, ended_at=NULL,
                   project_display_label=COALESCE(project_display_label, ?)
               WHERE hook_session_id=?""",
            (received_iso, event.project_display_label, event.hook_session_id),
        )
    return AppendOutcome(
        hook_event_id=hook_event_id, sequence=sequence, paired_duration_ms=paired_duration
    )


class SqliteClaudeHookLedger:
    """Reader used inside the application over the shared connection scope."""

    def __init__(
        self,
        connection_scope: ConnectionScope,
        ensure_initialized: Callable[[], None],
    ) -> None:
        self._connection_scope = connection_scope
        self._ensure_initialized = ensure_initialized

    _SESSION_UNION = """
        SELECT hook_session_id, hook_project_id, project_display_label, contract_version,
               receiver_version, first_received_at, last_received_at, session_start_source,
               session_end_reason, ended_at, event_count
          FROM claude_code_hook_sessions
        UNION ALL
        SELECT t.hook_session_id, t.hook_project_id, NULL, t.contract_version,
               'claude-code-otlp-receiver-1', t.first_received_at, t.last_received_at,
               NULL, NULL, NULL, 0
          FROM claude_code_telemetry_sessions t
         WHERE NOT EXISTS (SELECT 1 FROM claude_code_hook_sessions h
                            WHERE h.hook_session_id = t.hook_session_id)
    """

    def list_sessions(
        self, *, limit: int, after: tuple[datetime, str] | None = None
    ) -> tuple[LedgerSession, ...]:
        """Sessions in first-receipt order; ``after`` is a keyset cursor.

        A session captured only through telemetry (OTEL on, hooks off) is
        listed too, with no events and no display label.
        """

        self._ensure_initialized()
        if not 1 <= limit <= 1_001:
            raise ValueError("hook session page limit is outside its bound")
        with self._connection_scope(readonly=True) as connection:
            if after is None:
                rows = connection.execute(
                    f"""SELECT * FROM ({self._SESSION_UNION})
                        ORDER BY first_received_at ASC, hook_session_id ASC LIMIT ?""",
                    (limit,),
                ).fetchall()
            else:
                after_at, after_id = after
                require_safe_id(after_id)
                rows = connection.execute(
                    f"""SELECT * FROM ({self._SESSION_UNION})
                        WHERE first_received_at > ?
                           OR (first_received_at = ? AND hook_session_id > ?)
                        ORDER BY first_received_at ASC, hook_session_id ASC LIMIT ?""",
                    (to_iso(after_at), to_iso(after_at), after_id, limit),
                ).fetchall()
        return tuple(_row_session(row) for row in rows)

    def get_telemetry_session(self, hook_session_id: str):
        from .telemetry import row_telemetry_session

        self._ensure_initialized()
        require_safe_id(hook_session_id)
        with self._connection_scope(readonly=True) as connection:
            row = connection.execute(
                "SELECT * FROM claude_code_telemetry_sessions WHERE hook_session_id=?",
                (hook_session_id,),
            ).fetchone()
        return None if row is None else row_telemetry_session(row)

    def list_telemetry_requests(self, hook_session_id: str):
        from .telemetry import row_telemetry_request

        self._ensure_initialized()
        require_safe_id(hook_session_id)
        with self._connection_scope(readonly=True) as connection:
            rows = connection.execute(
                """SELECT * FROM claude_code_telemetry_requests
                   WHERE hook_session_id=? ORDER BY sequence ASC""",
                (hook_session_id,),
            ).fetchall()
        return tuple(row_telemetry_request(row) for row in rows)

    def latest_provider_version(self) -> str | None:
        """Most recently reported Claude Code version, if telemetry supplied one."""

        self._ensure_initialized()
        with self._connection_scope(readonly=True) as connection:
            row = connection.execute(
                """SELECT provider_version FROM claude_code_telemetry_sessions
                   WHERE provider_version IS NOT NULL
                   ORDER BY last_received_at DESC LIMIT 1"""
            ).fetchone()
        return None if row is None else row["provider_version"]

    def get_session(self, hook_session_id: str) -> LedgerSession | None:
        self._ensure_initialized()
        require_safe_id(hook_session_id)
        with self._connection_scope(readonly=True) as connection:
            row = connection.execute(
                "SELECT * FROM claude_code_hook_sessions WHERE hook_session_id=?",
                (hook_session_id,),
            ).fetchone()
        return None if row is None else _row_session(row)

    def list_events(self, hook_session_id: str) -> tuple[LedgerEvent, ...]:
        self._ensure_initialized()
        require_safe_id(hook_session_id)
        with self._connection_scope(readonly=True) as connection:
            rows = connection.execute(
                """SELECT * FROM claude_code_hook_events
                   WHERE hook_session_id=? ORDER BY sequence ASC""",
                (hook_session_id,),
            ).fetchall()
        return tuple(_row_event(row) for row in rows)

    def summary(self) -> dict[str, int]:
        self._ensure_initialized()
        with self._connection_scope(readonly=True) as connection:
            sessions = connection.execute(
                "SELECT COUNT(*) FROM claude_code_hook_sessions"
            ).fetchone()[0]
            events = connection.execute(
                "SELECT COUNT(*) FROM claude_code_hook_events"
            ).fetchone()[0]
            telemetry_sessions = connection.execute(
                "SELECT COUNT(*) FROM claude_code_telemetry_sessions"
            ).fetchone()[0]
            requests = connection.execute(
                "SELECT COUNT(*) FROM claude_code_telemetry_requests"
            ).fetchone()[0]
        return {
            "sessions": int(sessions),
            "events": int(events),
            "telemetry_sessions": int(telemetry_sessions),
            "requests": int(requests),
        }

    def append(
        self, pseudonymizer: Pseudonymizer, event: MinimizedHookEvent
    ) -> AppendOutcome:
        """In-application append (tests, future importers); enforces consent."""

        self._ensure_initialized()
        with self._connection_scope() as connection:
            if not _consent_active(connection):
                raise HookLedgerConsentInactive("claude_code local-history consent is inactive")
            connection.execute("BEGIN IMMEDIATE")
            try:
                outcome = _append(connection, pseudonymizer, event)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            return outcome


def _consent_active(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """SELECT 1 FROM consent_grants
           WHERE provider=? AND data_tier=? AND revoked_at IS NULL""",
        (Provider.CLAUDE_CODE.value, _CONSENT_TIER.value),
    ).fetchone()
    return row is not None


@contextmanager
def _receiver_connection(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path, timeout=RECEIVER_BUSY_TIMEOUT_MS / 1000)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {RECEIVER_BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA secure_delete = ON")
        yield connection
    finally:
        connection.close()


def receiver_append(
    database_path: Path, pseudonymizer: Pseudonymizer, event: MinimizedHookEvent
) -> AppendOutcome:
    """Append from the hook process without initializing or migrating the store.

    Raises ``HookLedgerUnavailable`` when the store does not exist, predates
    the ledger schema, or cannot be locked within the receiver's short budget,
    and ``HookLedgerConsentInactive`` when no active consent exists.  Both are
    caught by the receiver and turned into a silent no-op.
    """

    if database_path.is_symlink() or not database_path.is_file():
        raise HookLedgerUnavailable("local metadata store is absent")
    try:
        with _receiver_connection(database_path) as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version < LEDGER_SCHEMA_VERSION:
                raise HookLedgerUnavailable("local metadata store predates the hook ledger")
            if not _consent_active(connection):
                raise HookLedgerConsentInactive(
                    "claude_code local-history consent is inactive"
                )
            connection.execute("BEGIN IMMEDIATE")
            try:
                outcome = _append(connection, pseudonymizer, event)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            return outcome
    except sqlite3.OperationalError as exc:
        raise HookLedgerUnavailable("local metadata store is busy or unreadable") from exc


__all__ = (
    "AppendOutcome",
    "HOOK_INSTALLATION_MARKER",
    "HookLedgerConsentInactive",
    "HookLedgerUnavailable",
    "LEDGER_SCHEMA_VERSION",
    "LedgerEvent",
    "LedgerSession",
    "SqliteClaudeHookLedger",
    "receiver_append",
)
