"""Allowlisted App Server DTOs for explicit local text analysis.

The documented ``thread/read`` ``ThreadItem`` union contains many highly
sensitive item families.  This module projects only text from ``userMessage``,
``agentMessage``, and ``plan``.  Reasoning, commands and output, diffs, paths,
tool arguments and results, images, searches, reviews, and unknown future item
types are discarded without entering a boundary DTO. Unknown tagged variants
also mark extraction incomplete so downstream metrics cannot treat omission as
complete evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ....application.analysis.text_contracts import (
    MAX_REDACTED_MESSAGE_CHARACTERS,
)
from .errors import CodexCompatibilityError, CodexLimitError


TEXT_CONTENT_ADAPTER_VERSION = "0.3.0"
TEXT_CONTENT_SCHEMA_VERSION = "codex-thread-item-text-v4"


class CodexTextItemKind(StrEnum):
    USER_MESSAGE = "user_message"
    AGENT_MESSAGE = "agent_message"
    PLAN = "plan"


class _PrivateWireModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class RawCodexTextFragment(_PrivateWireModel):
    """One private allowlisted fragment; never persistence-safe."""

    turn_id: SecretStr = Field(repr=False)
    item_id: SecretStr = Field(repr=False)
    content_index: int = Field(ge=0)
    kind: CodexTextItemKind
    text: SecretStr = Field(
        repr=False,
        min_length=1,
        max_length=MAX_REDACTED_MESSAGE_CHARACTERS,
    )


class RawCodexTextThread(_PrivateWireModel):
    """Minimized private result of one explicit ``thread/read`` call."""

    thread_id: SecretStr = Field(repr=False)
    fragments: tuple[RawCodexTextFragment, ...] = Field(repr=False)
    extraction_complete: bool


@dataclass(frozen=True, slots=True)
class CodexTextContentLimits:
    """Post-decode bounds below the dedicated text-analysis frame ceiling."""

    max_turns_per_session: int = 500
    max_items_per_turn: int = 500
    max_total_items: int = 5_000
    max_user_content_parts_per_item: int = 32
    max_text_fragments_per_session: int = 2_000
    max_characters_per_fragment: int = MAX_REDACTED_MESSAGE_CHARACTERS
    max_total_text_characters: int = 1_000_000

    def __post_init__(self) -> None:
        values = (
            self.max_turns_per_session,
            self.max_items_per_turn,
            self.max_total_items,
            self.max_user_content_parts_per_item,
            self.max_text_fragments_per_session,
            self.max_characters_per_fragment,
            self.max_total_text_characters,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values):
            raise ValueError("Codex text-content limits must be positive integers")
        if self.max_characters_per_fragment > MAX_REDACTED_MESSAGE_CHARACTERS:
            raise ValueError("Codex text fragment bound exceeds the analysis contract")
        if self.max_total_items < self.max_items_per_turn:
            raise ValueError("Codex total item bound cannot be below the per-turn bound")
        if self.max_total_text_characters < self.max_characters_per_fragment:
            raise ValueError("Codex total text bound cannot be below the fragment bound")


ADMITTED_THREAD_ITEM_TYPES = frozenset({"userMessage", "agentMessage", "plan"})
DISCARDED_THREAD_ITEM_TYPES = frozenset(
    {
        "reasoning",
        "commandExecution",
        "fileChange",
        "mcpToolCall",
        "dynamicToolCall",
        "collabToolCall",
        "collabAgentToolCall",
        "hookPrompt",
        "subAgentActivity",
        "webSearch",
        "imageView",
        "sleep",
        "imageGeneration",
        "enteredReviewMode",
        "exitedReviewMode",
        "contextCompaction",
    }
)
_TEXT_USER_INPUT_TYPE = "text"
DISCARDED_USER_INPUT_TYPES = frozenset(
    {"image", "localImage", "skill", "mention"}
)
_AGENT_PHASES = frozenset({"commentary", "final_answer"})


def _bounded_string(
    value: object,
    *,
    field: str,
    maximum: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str) or (not value and not allow_empty):
        raise CodexCompatibilityError(f"provider {field} has an unsupported shape")
    if len(value) > maximum:
        raise CodexLimitError(f"provider {field} exceeded the character bound")
    if "\x00" in value:
        raise CodexCompatibilityError(f"provider {field} contains an unsupported control")
    return value


def _append_fragment(
    fragments: list[RawCodexTextFragment],
    *,
    turn_id: str,
    item_id: str,
    content_index: int,
    kind: CodexTextItemKind,
    text: object,
    limits: CodexTextContentLimits,
    total_characters: int,
) -> int:
    private_text = _bounded_string(
        text,
        field="text item",
        maximum=limits.max_characters_per_fragment,
        allow_empty=True,
    )
    if not private_text.strip():
        return total_characters
    if len(fragments) >= limits.max_text_fragments_per_session:
        raise CodexLimitError("provider read exceeded the text-fragment bound")
    total_characters += len(private_text)
    if total_characters > limits.max_total_text_characters:
        raise CodexLimitError("provider read exceeded the total text bound")
    fragments.append(
        RawCodexTextFragment(
            turn_id=SecretStr(turn_id),
            item_id=SecretStr(item_id),
            content_index=content_index,
            kind=kind,
            text=SecretStr(private_text),
        )
    )
    return total_characters


def parse_text_thread_read(
    result: object,
    limits: CodexTextContentLimits | None = None,
) -> RawCodexTextThread:
    """Parse the stable documented read shape and fail closed on text variants."""

    effective_limits = limits or CodexTextContentLimits()
    if not isinstance(result, dict):
        raise CodexCompatibilityError("provider text read has an unsupported shape")
    thread = result.get("thread")
    if not isinstance(thread, dict):
        raise CodexCompatibilityError("provider text read has an unsupported shape")
    thread_id = _bounded_string(
        thread.get("id"), field="thread identifier", maximum=4_096
    )
    turns = thread.get("turns")
    if not isinstance(turns, list):
        raise CodexCompatibilityError("provider text turns have an unsupported shape")
    if len(turns) > effective_limits.max_turns_per_session:
        raise CodexLimitError("provider text read exceeded the turn bound")

    fragments: list[RawCodexTextFragment] = []
    extraction_complete = True
    total_items = 0
    total_characters = 0
    for turn in turns:
        if not isinstance(turn, dict):
            raise CodexCompatibilityError("provider text turn has an unsupported shape")
        turn_id = _bounded_string(
            turn.get("id"), field="turn identifier", maximum=4_096
        )
        items = turn.get("items")
        if not isinstance(items, list):
            raise CodexCompatibilityError("provider text items have an unsupported shape")
        if len(items) > effective_limits.max_items_per_turn:
            raise CodexLimitError("provider text read exceeded the per-turn item bound")
        total_items += len(items)
        if total_items > effective_limits.max_total_items:
            raise CodexLimitError("provider text read exceeded the total item bound")

        for item in items:
            if not isinstance(item, dict):
                raise CodexCompatibilityError("provider text item has an unsupported shape")
            item_type = item.get("type")
            if not isinstance(item_type, str) or not item_type:
                raise CodexCompatibilityError("provider text item type is unsupported")
            if item_type in DISCARDED_THREAD_ITEM_TYPES:
                continue
            if item_type not in ADMITTED_THREAD_ITEM_TYPES:
                # Never inspect an unknown variant's payload. It cannot become
                # admitted merely by adding a text-like field, but its presence
                # means this adapter cannot prove that extraction is complete.
                extraction_complete = False
                continue

            item_id = _bounded_string(
                item.get("id"), field="text item identifier", maximum=4_096
            )
            if item_type == "userMessage":
                content = item.get("content")
                if not isinstance(content, list):
                    raise CodexCompatibilityError(
                        "provider user message has an unsupported shape"
                    )
                if len(content) > effective_limits.max_user_content_parts_per_item:
                    raise CodexLimitError(
                        "provider user message exceeded the content-part bound"
                    )
                for content_index, part in enumerate(content):
                    if not isinstance(part, dict):
                        raise CodexCompatibilityError(
                            "provider user input has an unsupported shape"
                        )
                    part_type = part.get("type")
                    if not isinstance(part_type, str) or not part_type:
                        raise CodexCompatibilityError(
                            "provider user input type is unsupported"
                        )
                    if part_type != _TEXT_USER_INPUT_TYPE:
                        if part_type not in DISCARDED_USER_INPUT_TYPES:
                            # As with an unknown ThreadItem, inspect only its tag
                            # and conservatively mark extraction incomplete.
                            extraction_complete = False
                        continue
                    total_characters = _append_fragment(
                        fragments,
                        turn_id=turn_id,
                        item_id=item_id,
                        content_index=content_index,
                        kind=CodexTextItemKind.USER_MESSAGE,
                        text=part.get("text"),
                        limits=effective_limits,
                        total_characters=total_characters,
                    )
                continue

            phase = item.get("phase")
            if item_type == "agentMessage" and (
                phase is not None and phase not in _AGENT_PHASES
            ):
                raise CodexCompatibilityError("provider agent phase is unsupported")
            total_characters = _append_fragment(
                fragments,
                turn_id=turn_id,
                item_id=item_id,
                content_index=0,
                kind=(
                    CodexTextItemKind.AGENT_MESSAGE
                    if item_type == "agentMessage"
                    else CodexTextItemKind.PLAN
                ),
                text=item.get("text"),
                limits=effective_limits,
                total_characters=total_characters,
            )

    return RawCodexTextThread(
        thread_id=SecretStr(thread_id),
        fragments=tuple(fragments),
        extraction_complete=extraction_complete,
    )
