"""Hard resource bounds for local Codex history inspection."""

from __future__ import annotations

from dataclasses import dataclass


TURN_SEQUENCE_STRIDE = 10_000
TURN_USAGE_OFFSET = TURN_SEQUENCE_STRIDE - 2
TURN_END_OFFSET = TURN_SEQUENCE_STRIDE - 1
MAX_STABLE_ITEMS_PER_TURN = TURN_USAGE_OFFSET - 1


@dataclass(frozen=True, slots=True)
class CodexReadLimits:
    """Small, explicit ceilings that prevent unbounded history ingestion."""

    max_json_line_bytes: int = 4 * 1024 * 1024
    request_timeout_seconds: float = 10.0
    shutdown_timeout_seconds: float = 2.0
    max_page_size: int = 100
    max_pages: int = 50
    max_sessions: int = 2_000
    max_label_reads: int = 25
    max_turns_per_session: int = 2_000
    max_items_per_turn: int = 2_000
    max_events_per_session: int = 10_000

    def __post_init__(self) -> None:
        integer_bounds = (
            self.max_json_line_bytes,
            self.max_page_size,
            self.max_pages,
            self.max_sessions,
            self.max_label_reads,
            self.max_turns_per_session,
            self.max_items_per_turn,
            self.max_events_per_session,
        )
        if any(value < 1 for value in integer_bounds):
            raise ValueError("Codex read limits must be positive")
        if self.request_timeout_seconds <= 0 or self.shutdown_timeout_seconds <= 0:
            raise ValueError("Codex transport timeouts must be positive")
        if self.max_items_per_turn > MAX_STABLE_ITEMS_PER_TURN:
            raise ValueError(
                "Codex item bound exceeds the stable sequence capacity"
            )
        if self.max_page_size > 100:
            raise ValueError("Codex page size cannot exceed the provider contract")
        if self.max_label_reads > 25:
            raise ValueError("Codex label-read bound cannot exceed 25")
