"""Annotation paths (ADR 0017): agents through the app's endpoint, and the central annotation server.

Path A (agent): after the person flips the allowance, any model they drive
(Codex, Claude Code, a local model) fetches the prepared metaprompt and the
sessions' redacted windows from the app's API and posts labels back; stored as
ordinary model judgments (``agent:<name>``).

Path B (central): a separate, explicit action submits redacted windows plus
pseudonymous ids to the central server (embedded locally today, VPS later,
same code as login will use). The central side annotates with its configured
active model and stores submission + labels - the dataset the owner's SaaS
collects from consenting, logged-in users. Labels come back locally as
``central:<model>`` judgments.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Literal

from pydantic import Field

from ..domain import PSEUDONYM_PATTERN, Provider, StrictModel
from .analysis.calibration_ratings import CALIBRATION_METRIC_KEYS, RatingLabel
from .analysis.model_judge import (
    JUDGE_PROMPT_VERSION,
    JUDGE_WINDOW_SCHEMA_VERSION,
    MAX_WINDOW_CHARACTERS,
    ZERO_WINDOW_FINGERPRINT,
    ModelJudgeError,
    ModelJudgeService,
    ModelJudgment,
    _QUESTIONS,
    _SYSTEM_PROMPT,
    _judge_user_prompt,
    parse_judge_reply,
    render_window,
)


ANNOTATION_CONTRACT_VERSION = "annotation.v1"
MAX_WORK_PAGE = 100
MAX_BATCH = 25
_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/+-]{0,119}$")


class AnnotationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AllowanceState(StrictModel):
    contract_version: Literal[ANNOTATION_CONTRACT_VERSION] = ANNOTATION_CONTRACT_VERSION
    agent_allowed: bool
    note: str = (
        "While on, models you drive may read sessions' redacted windows through this API and write labels back. "
        "Whatever model the agent runs on will see that content."
    )


class Metaprompt(StrictModel):
    contract_version: Literal[ANNOTATION_CONTRACT_VERSION] = ANNOTATION_CONTRACT_VERSION
    system_prompt: str
    questions: dict[str, str]
    labels: tuple[str, ...]
    prompt_version: str
    reply_format: str


class WorkItem(StrictModel):
    session_id: str
    project_id: str | None = None
    provider: str


class WorkList(StrictModel):
    contract_version: Literal[ANNOTATION_CONTRACT_VERSION] = ANNOTATION_CONTRACT_VERSION
    model_name: str
    items: tuple[WorkItem, ...]
    remaining: int = Field(ge=0)


class WorkWindow(StrictModel):
    contract_version: Literal[ANNOTATION_CONTRACT_VERSION] = ANNOTATION_CONTRACT_VERSION
    session_id: str
    provider: str
    window: str
    #: Identity of the exact analysis window sealed by the source and rendered
    #: above. The agent must echo it back when it submits labels.
    window_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    questions: dict[str, str]
    prompt_version: str


class SubmitAnnotation(StrictModel):
    session_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    model_name: str = Field(pattern=_MODEL_NAME.pattern)
    #: The ``window_fingerprint`` handed out with the window that was judged.
    #: Labels for a window that has since changed are rejected, not re-pointed.
    window_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    labels: dict[str, RatingLabel]


class SubmitResult(StrictModel):
    contract_version: Literal[ANNOTATION_CONTRACT_VERSION] = ANNOTATION_CONTRACT_VERSION
    session_id: str
    model_alias: str
    stored: int = Field(ge=0)


class RemoteSubmitRequest(StrictModel):
    limit: int = Field(default=5, ge=1, le=MAX_BATCH)


class RemoteAnnotationDisclosure(StrictModel):
    """Closed pre-send disclosure for the explicit remote annotation action."""

    contract_version: Literal[ANNOTATION_CONTRACT_VERSION] = ANNOTATION_CONTRACT_VERSION
    destination: str = Field(min_length=1, max_length=2_048)
    redacted_windows_retained: Literal[True] = True
    pseudonymous_session_ids_retained: Literal[True] = True
    pseudonymous_project_ids_retained: Literal[True] = True
    raw_transcripts_sent: Literal[False] = False
    model_policy: Literal["configured_active_model_at_submission"] = "configured_active_model_at_submission"
    active_model_alias: str | None = Field(default=None, pattern=_MODEL_NAME.pattern)


class RemoteSubmitResult(StrictModel):
    contract_version: Literal[ANNOTATION_CONTRACT_VERSION] = ANNOTATION_CONTRACT_VERSION
    destination: str
    submitted: int = Field(ge=0)
    annotated: int = Field(ge=0)
    model_identity: str | None = None
    stored_locally_as: str | None = None


def _sealed_window_fingerprint(context: object, *, session_id: str, provider: Provider) -> str:
    """The authoritative window identity, taken from the sealed source's own context.

    It is never recomputed from the rendered text: the source seals the window
    it read, and a judgment may only name that. The context must also own the
    session and provider it was requested for, so labels cannot be bound to a
    window belonging to some other session or run.
    """

    if getattr(context, "session_id", None) != session_id:
        raise AnnotationError("window_session_mismatch")
    try:
        if Provider(getattr(context, "provider")) is not provider:
            raise AnnotationError("window_provider_mismatch")
    except ValueError:
        raise AnnotationError("window_provider_mismatch") from None
    fingerprint = getattr(context, "analysis_window_fingerprint", None)
    if not isinstance(fingerprint, str) or PSEUDONYM_PATTERN.fullmatch(fingerprint) is None:
        raise AnnotationError("window_fingerprint_unavailable")
    if fingerprint == ZERO_WINDOW_FINGERPRINT:
        raise AnnotationError("window_fingerprint_unavailable")
    return fingerprint


def metaprompt() -> Metaprompt:
    return Metaprompt(
        system_prompt=_SYSTEM_PROMPT,
        questions=dict(_QUESTIONS),
        labels=tuple(label.value for label in RatingLabel),
        prompt_version=JUDGE_PROMPT_VERSION,
        reply_format='Reply with strict JSON only: {"<metric_key>": "<label>", ...} covering every question.',
    )


class AnnotationService:
    """Path A: the allowance switch and the agent-facing work/submit surface."""

    def __init__(
        self,
        judge: ModelJudgeService,
        *,
        list_sessions: Callable[..., list[dict[str, object]]],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._judge = judge
        self._list_sessions = list_sessions
        self._clock = clock or (lambda: datetime.now(UTC))
        self._agent_allowed = False
        self._lock = threading.Lock()

    def allowance(self) -> AllowanceState:
        return AllowanceState(agent_allowed=self._agent_allowed)

    def set_allowance(self, agent_allowed: bool) -> AllowanceState:
        with self._lock:
            self._agent_allowed = bool(agent_allowed)
        return self.allowance()

    def _require_allowance(self) -> None:
        if not self._agent_allowed:
            raise AnnotationError("allowance_required")

    def work(self, model_name: str, limit: int = 25) -> WorkList:
        self._require_allowance()
        if _MODEL_NAME.fullmatch(model_name or "") is None:
            raise AnnotationError("model_name_invalid")
        limit = max(1, min(int(limit), MAX_WORK_PAGE))
        alias = f"agent:{model_name}"
        done = {j.session_id for j in self._judge.repository.list(model_alias=alias)}
        pending: list[WorkItem] = []
        offset = 0
        while True:
            rows = self._list_sessions(limit=200, offset=offset)
            if not rows:
                break
            for row in rows:
                sid = str(row.get("session_id"))
                if sid in done:
                    continue
                pending.append(WorkItem(session_id=sid, project_id=str(row.get("project_id")) if row.get("project_id") else None, provider=str(row.get("provider"))))
            offset += len(rows)
            if len(rows) < 200 or offset >= 2000:
                break
        return WorkList(model_name=model_name, items=tuple(pending[:limit]), remaining=len(pending))

    def window(self, session_id: str) -> WorkWindow:
        self._require_allowance()
        session = self._judge.session_lookup(session_id)
        if session is None:
            raise AnnotationError("session_not_found")
        provider = Provider(getattr(session, "provider"))
        try:
            context = self._judge.window_for(provider, session_id)
        except ModelJudgeError as error:
            raise AnnotationError(error.code) from None
        return WorkWindow(
            session_id=session_id,
            provider=provider.value,
            window=render_window(context),
            window_fingerprint=_sealed_window_fingerprint(context, session_id=session_id, provider=provider),
            questions=dict(_QUESTIONS),
            prompt_version=JUDGE_PROMPT_VERSION,
        )

    def submit(self, request: SubmitAnnotation) -> SubmitResult:
        self._require_allowance()
        session = self._judge.session_lookup(request.session_id)
        if session is None:
            raise AnnotationError("session_not_found")
        unknown = set(request.labels) - set(CALIBRATION_METRIC_KEYS)
        if unknown or not request.labels:
            raise AnnotationError("labels_invalid")
        if request.window_fingerprint == ZERO_WINDOW_FINGERPRINT:
            raise AnnotationError("window_fingerprint_invalid")
        provider = Provider(getattr(session, "provider"))
        try:
            context = self._judge.window_for(provider, request.session_id)
        except ModelJudgeError as error:
            raise AnnotationError(error.code) from None
        except Exception:  # noqa: BLE001 - an unreadable window cannot be annotated
            raise AnnotationError("window_unavailable") from None
        fingerprint = _sealed_window_fingerprint(context, session_id=request.session_id, provider=provider)
        if fingerprint != request.window_fingerprint:
            # The session grew, or was re-read under a different run, since the
            # agent read it. Its labels describe a window that no longer exists.
            raise AnnotationError("window_fingerprint_mismatch")
        alias = f"agent:{request.model_name}"[:64]
        now = self._clock()
        stored = 0
        for key, label in request.labels.items():
            self._judge.repository.upsert(
                ModelJudgment(
                    session_id=request.session_id,
                    metric_key=key,
                    label=label,
                    model_alias=alias,
                    model_identity=request.model_name[:200],
                    prompt_version=JUDGE_PROMPT_VERSION,
                    window_fingerprint=fingerprint,
                    judged_at=now,
                )
            )
            stored += 1
        return SubmitResult(session_id=request.session_id, model_alias=alias, stored=stored)


# ----- Path B: the central annotation server (embedded locally; same code later on the VPS) -----


class CentralBatchItem(StrictModel):
    session_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    project_id: str | None = Field(default=None, pattern=PSEUDONYM_PATTERN.pattern)
    provider: str = Field(max_length=32)
    window: str = Field(min_length=1, max_length=60_000)


class CentralBatch(StrictModel):
    user_label: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    items: tuple[CentralBatchItem, ...] = Field(min_length=1, max_length=MAX_BATCH)


class CentralAnnotation(StrictModel):
    session_id: str
    labels: dict[str, RatingLabel]


class CentralBatchResult(StrictModel):
    contract_version: Literal[ANNOTATION_CONTRACT_VERSION] = ANNOTATION_CONTRACT_VERSION
    stored: int = Field(ge=0)
    annotations: tuple[CentralAnnotation, ...]
    model_identity: str | None = None
    prompt_version: str = JUDGE_PROMPT_VERSION


def _is_canonical_judge_window(value: str) -> bool:
    """Accept only the bounded JSON envelope produced by ``render_window``."""

    if len(value) > MAX_WINDOW_CHARACTERS:
        return False
    try:
        payload = json.loads(value)
    except ValueError:
        return False
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "authority",
        "available",
        "task_anchor_retained",
        "earlier_records_omitted",
        "records",
    }:
        return False
    records = payload.get("records")
    if (
        payload.get("schema") != JUDGE_WINDOW_SCHEMA_VERSION
        or payload.get("authority") != "untrusted_evidence"
        or payload.get("available") is not True
        or payload.get("task_anchor_retained") is not True
        or not isinstance(payload.get("earlier_records_omitted"), bool)
        or not isinstance(records, list)
        or not records
    ):
        return False
    sequences: list[int] = []
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "sequence",
            "role",
            "content",
        }:
            return False
        sequence = record.get("sequence")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 0
            or record.get("role") not in {"user", "agent", "plan"}
            or not isinstance(record.get("content"), str)
            or not str(record["content"]).strip()
        ):
            return False
        sequences.append(sequence)
    return (
        records[0]["role"] == "user"
        and sequences == sorted(sequences)
        and len(sequences) == len(set(sequences))
    )


class CentralAnnotationStore:
    """The central dataset: submissions + labels, one sqlite file (VPS-ready)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS central_annotations (
                    user_label TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    project_id TEXT,
                    provider TEXT NOT NULL,
                    window_chars INTEGER NOT NULL,
                    redacted_window TEXT NOT NULL,
                    labels_json TEXT NOT NULL,
                    model_identity TEXT,
                    prompt_version TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    PRIMARY KEY (user_label, session_id, prompt_version)
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def store(self, user_label: str, item: CentralBatchItem, labels: dict[str, RatingLabel], model_identity: str | None, submitted_at: datetime) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO central_annotations(
                    user_label, session_id, project_id, provider, window_chars, redacted_window,
                    labels_json, model_identity, prompt_version, submitted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_label, item.session_id, item.project_id, item.provider, len(item.window), item.window,
                    json.dumps({k: v.value for k, v in labels.items()}), model_identity, JUDGE_PROMPT_VERSION, submitted_at.isoformat(),
                ),
            )
            connection.commit()

    def count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM central_annotations").fetchone()[0])


class CentralAnnotationServer:
    """Annotates submitted windows with the configured active model and stores the dataset."""

    def __init__(
        self,
        store: CentralAnnotationStore,
        *,
        chat: Callable[[str, bytes], tuple[int, bytes, str]],
        active_model: Callable[[], str | None],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._chat = chat
        self._active_model = active_model
        self._clock = clock or (lambda: datetime.now(UTC))

    def annotate_batch(self, batch: CentralBatch) -> CentralBatchResult:
        alias = self._active_model()
        if alias is None:
            raise AnnotationError("no_central_model")
        annotations: list[CentralAnnotation] = []
        stored = 0
        for item in batch.items:
            if not _is_canonical_judge_window(item.window):
                continue
            body = json.dumps(
                {
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": _judge_user_prompt(item.window),
                        },
                    ],
                    "temperature": 0,
                    "max_tokens": 220,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
            ).encode("utf-8")
            try:
                status, payload, _ = self._chat(alias, body)
                text = json.loads(payload.decode("utf-8"))["choices"][0]["message"]["content"] if status == 200 else None
            except Exception:  # noqa: BLE001 - one bad window must not sink the batch
                text = None
            labels = parse_judge_reply(text) if text else None
            if not labels:
                continue
            self._store.store(batch.user_label, item, labels, alias, self._clock())
            annotations.append(CentralAnnotation(session_id=item.session_id, labels=labels))
            stored += 1
        return CentralBatchResult(stored=stored, annotations=tuple(annotations), model_identity=alias)


class RemoteAnnotationClient:
    """The app-side 'Annotate remotely' action: build the batch, send it, record returned labels locally."""

    def __init__(
        self,
        service: AnnotationService,
        *,
        submit: Callable[[CentralBatch], CentralBatchResult],
        destination: str,
        user_label: str,
        list_sessions: Callable[..., list[dict[str, object]]],
        active_model: Callable[[], str | None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._service = service
        self._submit = submit
        self._destination = destination
        self._user_label = user_label
        self._list_sessions = list_sessions
        self._active_model = active_model or (lambda: None)
        self._clock = clock or (lambda: datetime.now(UTC))

    def disclosure(self) -> RemoteAnnotationDisclosure:
        """Describe the exact remote boundary without reading or submitting session data."""

        return RemoteAnnotationDisclosure(
            destination=self._destination,
            active_model_alias=self._active_model(),
        )

    def submit_batch(self, request: RemoteSubmitRequest) -> RemoteSubmitResult:
        judge = self._service._judge  # noqa: SLF001 - same composition unit
        central_done = {j.session_id for j in judge.repository.list() if j.model_alias.startswith("central:")}
        items: list[CentralBatchItem] = []
        # Window identity of each window this run actually sealed and sent, so the
        # labels that come back are recorded against that window and no other.
        sealed: dict[str, str] = {}
        offset = 0
        while len(items) < request.limit:
            rows = self._list_sessions(limit=100, offset=offset)
            if not rows:
                break
            for row in rows:
                if len(items) >= request.limit:
                    break
                sid = str(row.get("session_id"))
                if sid in central_done:
                    continue
                session = judge.session_lookup(sid)
                if session is None:
                    continue
                provider = Provider(getattr(session, "provider"))
                try:
                    context = judge.window_for(provider, sid)
                except Exception:  # noqa: BLE001 - unreadable windows are skipped
                    continue
                try:
                    sealed[sid] = _sealed_window_fingerprint(context, session_id=sid, provider=provider)
                except AnnotationError:  # a window without provable identity is not submitted
                    continue
                items.append(CentralBatchItem(session_id=sid, project_id=str(row.get("project_id")) if row.get("project_id") else None, provider=str(row.get("provider")), window=render_window(context)))
            offset += len(rows)
            if len(rows) < 100:
                break
        if not items:
            return RemoteSubmitResult(destination=self._destination, submitted=0, annotated=0)
        result = self._submit(CentralBatch(user_label=self._user_label, items=tuple(items)))
        alias = f"central:{result.model_identity}"[:64] if result.model_identity else "central:unknown"
        now = self._clock()
        recorded = 0
        for annotation in result.annotations:
            fingerprint = sealed.get(annotation.session_id)
            if fingerprint is None:
                # Labels for a session this run did not seal and send. Nothing
                # local can vouch for which window they describe, so they are
                # dropped rather than stored against a guessed one.
                continue
            for key, label in annotation.labels.items():
                if key not in CALIBRATION_METRIC_KEYS:
                    continue
                judge.repository.upsert(
                    ModelJudgment(
                        session_id=annotation.session_id, metric_key=key, label=label, model_alias=alias,
                        model_identity=result.model_identity or "unknown", prompt_version=result.prompt_version,
                        window_fingerprint=fingerprint, judged_at=now,
                    )
                )
                recorded += 1
        return RemoteSubmitResult(destination=self._destination, submitted=len(items), annotated=result.stored, model_identity=result.model_identity, stored_locally_as=alias if recorded else None)


__all__ = (
    "ANNOTATION_CONTRACT_VERSION",
    "AllowanceState",
    "AnnotationError",
    "AnnotationService",
    "CentralAnnotationServer",
    "CentralAnnotationStore",
    "CentralBatch",
    "CentralBatchItem",
    "CentralBatchResult",
    "Metaprompt",
    "RemoteAnnotationDisclosure",
    "RemoteAnnotationClient",
    "RemoteSubmitRequest",
    "RemoteSubmitResult",
    "SubmitAnnotation",
    "SubmitResult",
    "WorkList",
    "WorkWindow",
    "metaprompt",
)
