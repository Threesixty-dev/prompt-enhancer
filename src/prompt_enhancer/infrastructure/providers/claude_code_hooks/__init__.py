"""Claude Code hook-based provider surface.

Prospective, content-free capture: Claude Code invokes the receiver for each
lifecycle event; the receiver minimizes the payload in-process and appends to
an append-only ledger; the adapter reads that ledger through the ordinary
``ProviderAdapter`` port.  Nothing here reads a transcript, a settings file, or
any path under the provider's private directory.
"""

from .contracts import (
    ADAPTER_VERSION,
    CONTRACT_VERSION,
    HOOK_INSTALLATION_MARKER,
    RECEIVER_VERSION,
    SOURCE_SCHEMA_VERSION,
    HookEventName,
    MinimizedHookEvent,
    categorize_tool_name,
)
from .ledger import (
    HookLedgerConsentInactive,
    HookLedgerUnavailable,
    LEDGER_SCHEMA_VERSION,
    LedgerEvent,
    LedgerSession,
    SqliteClaudeHookLedger,
    receiver_append,
)
from .receiver import (
    ALLOWED_PAYLOAD_KEYS,
    ReceiverOutcome,
    ReceiverStatus,
    minimize_payload,
    receive,
)

__all__ = (
    "ADAPTER_VERSION",
    "ALLOWED_PAYLOAD_KEYS",
    "CONTRACT_VERSION",
    "HOOK_INSTALLATION_MARKER",
    "HookEventName",
    "HookLedgerConsentInactive",
    "HookLedgerUnavailable",
    "LEDGER_SCHEMA_VERSION",
    "LedgerEvent",
    "LedgerSession",
    "MinimizedHookEvent",
    "RECEIVER_VERSION",
    "ReceiverOutcome",
    "ReceiverStatus",
    "SOURCE_SCHEMA_VERSION",
    "SqliteClaudeHookLedger",
    "categorize_tool_name",
    "minimize_payload",
    "receive",
    "receiver_append",
)
