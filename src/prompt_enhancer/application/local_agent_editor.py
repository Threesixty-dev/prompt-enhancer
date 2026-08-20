"""Session-bound, review-before-apply text editing for the local agent UI.

The browser sees only paths relative to the already-selected workspace.  A
preview creates a short-lived, single-use capability containing only the
relative path, hashes, and file identities; draft text is never retained in the
capability store. Applying requires the caller to send the exact text and
revisions again, after which ``WorkspaceTools`` repeats every filesystem guard.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import hashlib
import hmac
import re
import threading
import time
from typing import Literal
import uuid

from pydantic import Field, field_validator

from ..domain import StrictModel
from .local_agent_limits import MAX_DIFF_CHARS, MAX_FILE_WRITE_BYTES
from .local_agent_workspace import PreparedWrite, WorkspaceTools
from .local_agent_limits import LocalAgentError


WORKSPACE_CONTRACT_VERSION = "local-agent-workspace.v1"
WORKSPACE_APPLY_CONFIRMATION = "apply_reviewed_workspace_edit"
WORKSPACE_PREVIEW_TTL_SECONDS = 120
MAX_ACTIVE_PREVIEWS_PER_SESSION = 8
_REVISION_PATTERN = r"^[0-9a-f]{64}$"
_ID_PATTERN = r"^[0-9a-f]{32}$"


class WorkspaceEntryKind(StrEnum):
    DIRECTORY = "directory"
    FILE = "file"
    UNAVAILABLE = "unavailable"


class WorkspaceLineEnding(StrEnum):
    LF = "lf"
    CRLF = "crlf"
    NONE = "none"


class WorkspaceEntry(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    name: str = Field(min_length=1, max_length=255)
    kind: WorkspaceEntryKind
    byte_size: int | None = Field(default=None, ge=0)
    editable_candidate: bool


class WorkspaceTree(StrictModel):
    contract_version: Literal[WORKSPACE_CONTRACT_VERSION] = WORKSPACE_CONTRACT_VERSION
    session_id: str = Field(pattern=_ID_PATTERN)
    path: str = Field(min_length=1, max_length=1024)
    entries: tuple[WorkspaceEntry, ...]
    complete: bool


class WorkspaceFile(StrictModel):
    contract_version: Literal[WORKSPACE_CONTRACT_VERSION] = WORKSPACE_CONTRACT_VERSION
    session_id: str = Field(pattern=_ID_PATTERN)
    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(max_length=MAX_FILE_WRITE_BYTES)
    revision: str = Field(pattern=_REVISION_PATTERN)
    byte_size: int = Field(ge=0, le=MAX_FILE_WRITE_BYTES)
    line_ending: WorkspaceLineEnding
    editable: Literal[True] = True


class WorkspacePreviewCommand(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(max_length=MAX_FILE_WRITE_BYTES)
    expected_revision: str = Field(pattern=_REVISION_PATTERN)
    line_ending: WorkspaceLineEnding

    @field_validator("content")
    @classmethod
    def normalized_text_only(cls, value: str) -> str:
        if "\x00" in value or "\r" in value:
            raise ValueError("workspace editor accepts normalized UTF-8 text only")
        return value


class WorkspaceEditPreview(StrictModel):
    contract_version: Literal[WORKSPACE_CONTRACT_VERSION] = WORKSPACE_CONTRACT_VERSION
    session_id: str = Field(pattern=_ID_PATTERN)
    preview_id: str = Field(pattern=_ID_PATTERN)
    path: str = Field(min_length=1, max_length=1024)
    expected_revision: str = Field(pattern=_REVISION_PATTERN)
    proposed_revision: str = Field(pattern=_REVISION_PATTERN)
    line_ending: WorkspaceLineEnding
    diff: str = Field(min_length=1, max_length=MAX_DIFF_CHARS)
    expires_at: datetime


class WorkspaceApplyCommand(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(max_length=MAX_FILE_WRITE_BYTES)
    expected_revision: str = Field(pattern=_REVISION_PATTERN)
    proposed_revision: str = Field(pattern=_REVISION_PATTERN)
    line_ending: WorkspaceLineEnding
    confirmation: Literal[WORKSPACE_APPLY_CONFIRMATION]

    @field_validator("content")
    @classmethod
    def normalized_text_only(cls, value: str) -> str:
        if "\x00" in value or "\r" in value:
            raise ValueError("workspace editor accepts normalized UTF-8 text only")
        return value


class WorkspaceApplyResult(StrictModel):
    contract_version: Literal[WORKSPACE_CONTRACT_VERSION] = WORKSPACE_CONTRACT_VERSION
    session_id: str = Field(pattern=_ID_PATTERN)
    path: str = Field(min_length=1, max_length=1024)
    revision: str = Field(pattern=_REVISION_PATTERN)
    byte_size: int = Field(ge=0, le=MAX_FILE_WRITE_BYTES)
    applied: Literal[True] = True


@dataclass(frozen=True, slots=True)
class _EditCapability:
    preview_id: str
    session_id: str
    path: str
    expected_revision: str
    proposed_revision: str
    line_ending: WorkspaceLineEnding
    base_identity: tuple[int, int]
    parent_identity: tuple[int, int]
    mode: int
    expires_at: datetime
    deadline: float


class LocalAgentWorkspaceEditor:
    """In-memory editor capability service; it never owns workspace content."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        ttl_seconds: int = WORKSPACE_PREVIEW_TTL_SECONDS,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic = monotonic or time.monotonic
        self._ttl_seconds = max(1, min(int(ttl_seconds), WORKSPACE_PREVIEW_TTL_SECONDS))
        self._capabilities: dict[str, _EditCapability] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _disk_content(content: str, line_ending: WorkspaceLineEnding) -> str:
        if "\x00" in content or "\r" in content:
            raise LocalAgentError("workspace_text_invalid")
        if line_ending is WorkspaceLineEnding.CRLF:
            return content.replace("\n", "\r\n")
        return content

    @staticmethod
    def _matches(left: str, right: str) -> bool:
        return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))

    def _prune_locked(self, now: float) -> None:
        expired = [
            preview_id
            for preview_id, capability in self._capabilities.items()
            if capability.deadline < now
        ]
        for preview_id in expired:
            self._capabilities.pop(preview_id, None)

    def discard_session(self, session_id: str) -> None:
        with self._lock:
            for preview_id in [
                item.preview_id
                for item in self._capabilities.values()
                if item.session_id == session_id
            ]:
                self._capabilities.pop(preview_id, None)

    def tree(self, session_id: str, tools: WorkspaceTools, path: str) -> WorkspaceTree:
        normalized = "." if path in {"", "."} else path
        if len(normalized) > 1024:
            raise LocalAgentError("path_invalid")
        entries, complete = tools.list_entries(normalized)
        represented = tuple(
            item
            for item in entries
            if len(item.path) <= 1024
            and len(item.name) <= 255
            and "\\" not in item.path
            and re.match(r"^[A-Za-z]:", item.path) is None
        )
        return WorkspaceTree(
            session_id=session_id,
            path=normalized,
            entries=tuple(
                WorkspaceEntry(
                    path=item.path,
                    name=item.name,
                    kind=WorkspaceEntryKind(item.kind),
                    byte_size=item.byte_size,
                    editable_candidate=item.editable_candidate,
                )
                for item in represented
            ),
            complete=complete and len(represented) == len(entries),
        )

    def read(self, session_id: str, tools: WorkspaceTools, path: str) -> WorkspaceFile:
        snapshot = tools.read_text_snapshot(path)
        return WorkspaceFile(
            session_id=session_id,
            path=snapshot.path,
            content=snapshot.content,
            revision=snapshot.revision,
            byte_size=snapshot.byte_size,
            line_ending=WorkspaceLineEnding(snapshot.line_ending),
        )

    def preview(
        self,
        session_id: str,
        tools: WorkspaceTools,
        command: WorkspacePreviewCommand,
    ) -> WorkspaceEditPreview:
        current = tools.read_text_snapshot(command.path)
        if not self._matches(current.revision, command.expected_revision):
            raise LocalAgentError("workspace_revision_changed")
        if WorkspaceLineEnding(current.line_ending) is not command.line_ending:
            raise LocalAgentError("workspace_line_ending_changed")
        prepared = tools.prepare_write(
            current.path,
            self._disk_content(command.content, command.line_ending),
        )
        if not prepared.existed or prepared.base_identity is None or prepared.mode is None:
            raise LocalAgentError("workspace_existing_file_required")
        if prepared.base_sha256 is None or not self._matches(
            prepared.base_sha256, command.expected_revision
        ):
            raise LocalAgentError("workspace_revision_changed")
        if self._matches(prepared.proposed_sha256, command.expected_revision):
            raise LocalAgentError("workspace_no_change")
        if prepared.preview == "(no change)":
            raise LocalAgentError("workspace_change_not_reviewable")

        now = self._monotonic()
        expires_at = self._clock() + timedelta(seconds=self._ttl_seconds)
        capability = _EditCapability(
            preview_id=uuid.uuid4().hex,
            session_id=session_id,
            path=prepared.path,
            expected_revision=command.expected_revision,
            proposed_revision=prepared.proposed_sha256,
            line_ending=command.line_ending,
            base_identity=prepared.base_identity,
            parent_identity=prepared.parent_identity,
            mode=prepared.mode,
            expires_at=expires_at,
            deadline=now + self._ttl_seconds,
        )
        with self._lock:
            self._prune_locked(now)
            session_capabilities = sorted(
                (
                    item
                    for item in self._capabilities.values()
                    if item.session_id == session_id
                ),
                key=lambda item: item.deadline,
            )
            while len(session_capabilities) >= MAX_ACTIVE_PREVIEWS_PER_SESSION:
                oldest = session_capabilities.pop(0)
                self._capabilities.pop(oldest.preview_id, None)
            self._capabilities[capability.preview_id] = capability
        return WorkspaceEditPreview(
            session_id=session_id,
            preview_id=capability.preview_id,
            path=prepared.path,
            expected_revision=capability.expected_revision,
            proposed_revision=capability.proposed_revision,
            line_ending=capability.line_ending,
            diff=prepared.preview,
            expires_at=capability.expires_at,
        )

    def apply(
        self,
        session_id: str,
        preview_id: str,
        tools: WorkspaceTools,
        command: WorkspaceApplyCommand,
    ) -> WorkspaceApplyResult:
        now = self._monotonic()
        with self._lock:
            capability = self._capabilities.get(preview_id)
            if capability is not None and capability.session_id == session_id:
                self._capabilities.pop(preview_id, None)
        if capability is None or capability.session_id != session_id:
            raise LocalAgentError("workspace_preview_not_found")
        if capability.deadline < now:
            raise LocalAgentError("workspace_preview_expired")
        exact = (
            self._matches(capability.path, command.path)
            and self._matches(capability.expected_revision, command.expected_revision)
            and self._matches(capability.proposed_revision, command.proposed_revision)
            and capability.line_ending is command.line_ending
        )
        disk_content = self._disk_content(command.content, command.line_ending)
        proposed_revision = hashlib.sha256(disk_content.encode("utf-8")).hexdigest()
        if not exact or not self._matches(proposed_revision, capability.proposed_revision):
            raise LocalAgentError("workspace_preview_mismatch")
        prepared = PreparedWrite(
            path=capability.path,
            content=disk_content,
            preview="",
            base_sha256=capability.expected_revision,
            base_identity=capability.base_identity,
            parent_identity=capability.parent_identity,
            proposed_sha256=capability.proposed_revision,
            existed=True,
            mode=capability.mode,
        )
        outcome = tools.apply_prepared_write(prepared)
        if not outcome.ok:
            raise LocalAgentError(outcome.code or "workspace_apply_failed")
        written = tools.read_text_snapshot(capability.path)
        if not self._matches(written.revision, capability.proposed_revision):
            raise LocalAgentError("workspace_verification_failed")
        return WorkspaceApplyResult(
            session_id=session_id,
            path=written.path,
            revision=written.revision,
            byte_size=written.byte_size,
        )


__all__ = (
    "LocalAgentWorkspaceEditor",
    "WORKSPACE_APPLY_CONFIRMATION",
    "WORKSPACE_CONTRACT_VERSION",
    "WorkspaceApplyCommand",
    "WorkspaceApplyResult",
    "WorkspaceEditPreview",
    "WorkspaceEntry",
    "WorkspaceEntryKind",
    "WorkspaceFile",
    "WorkspaceLineEnding",
    "WorkspacePreviewCommand",
    "WorkspaceTree",
)
