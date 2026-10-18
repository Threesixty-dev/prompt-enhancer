"""Prompt check: validate one prompt in its context before an agent acts on it (ADR 0015).

A coding agent (or the person) sends the prompt that is about to be sent,
optionally with the earlier messages of the conversation. The app answers with

* the same deterministic prompt metrics the dashboard uses for sessions
  (coaching pack, focus request only), with the cues it detected or missed,
* content-free context inference (task type, language, dependence on earlier
  messages, references, whether verification was asked for),
* when a local model is active, commentary: findings, a reformulated prompt
  that keeps the person's intent, and element-level rewrites - marked as model
  output, never a metric,
* a compact summary the agent can show or act on.

Only metrics and content-free counters are persisted (history and plots); the
prompt text, the prior messages and the commentary are returned to the caller
and never stored.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import hashlib
import hmac
import secrets
import json
from typing import Any, Literal, Protocol

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator

from ..core.prompt_review import (
    CommentaryFinding,
    ContextInference,
    MAX_COMMENTARY_INPUT_CHARS,
    MAX_CONTEXT_MESSAGES,
    MAX_CONTEXT_MESSAGE_CHARS,
    MAX_CONTEXT_TOTAL_CHARS,
    MAX_PROMPT_CHARS,
    ModelCommentary,
    PROMPT_CHECK_CONTRACT_VERSION,
    PROMPT_CHECK_PROMPT_VERSION,
    PromptCheckMessage,
    ReformulatedElement,
    _BULLET,
    _CODE_IDENTIFIER,
    _COMMON_WORDS,
    _CommentaryReply,
    _FILE_REFERENCE,
    _LEADING_PRONOUN,
    _PRIOR_CONTEXT_MARKERS,
    _SENTENCE,
    _SEVERITY_ORDER,
    _SYSTEM_PROMPT,
    _TASK_PATTERNS,
    _URL,
    _VERIFICATION_MARKERS,
    _WORD,
    _commentary_input,
    parse_commentary_reply,
    infer_context,
)

from ..domain import PSEUDONYM_PATTERN, StrictModel
from .prompt_evaluation import (
    DeterministicPromptEvaluator, PROMPT_METRIC_KEYS, CUE_LABELS,
    PromptCue, PromptMetricReading,
)
from .model_reply import completed_chat_content
from .analysis.coaching_baselines import DEFAULT_COACHING_METRIC_ENGINE
from .analysis.text_baselines import TextMetricEngine
from .analysis.text_contracts import TextLanguage


MAX_HISTORY_PAGE = 100
EXPLANATION_PHRASES: Mapping[str, str] = {
    "unsupported_language": "too short or language not recognised (English and Polish are analysed)",
    "diagnostic_task_not_detected": "only measured for bug / diagnosis prompts",
    "constraints_unobserved": "no constraint clause detected",
    "requirements_unknown": "no requirement clause detected",
    "deliverables_unobserved": "no deliverable clause detected",
    "source_extraction_incomplete": "the text could not be analysed completely",
    "message_kind_unobserved": "needs a message kind this prompt does not contain",
}


class PromptCheckError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# ----- request -----




class PromptCheckRequest(StrictModel):
    """The prompt about to be sent, the earlier turns if the agent has them, and hints about the agent."""

    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    prior_messages: tuple[PromptCheckMessage, ...] = Field(default=(), max_length=MAX_CONTEXT_MESSAGES)
    #: When set, the session's own redacted tail becomes the prior context (server-side, consent-gated).
    session_id: str | None = Field(default=None, pattern=PSEUDONYM_PATTERN.pattern)
    provider: Literal["codex", "claude_code", "other"] = "other"
    agent_model: str | None = Field(default=None, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._:/+-]*$")
    want_commentary: bool = True
    remote_approval: str | None = Field(default=None, max_length=100, repr=False)

    @field_validator("prompt")
    @classmethod
    def prompt_has_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must contain text")
        return value

    @model_validator(mode="after")
    def bound_context(self) -> PromptCheckRequest:
        if sum(len(m.content) for m in self.prior_messages) > MAX_CONTEXT_TOTAL_CHARS:
            raise ValueError("prior messages exceed the context bound")
        return self


# ----- results -----












class PromptCheckConfiguration(StrictModel):
    remote: bool = False
    model: str | None = None
    provider: Literal["local", "litellm"] = "local"


class PromptCheckPreview(StrictModel):
    model: str
    provider: Literal["litellm"] = "litellm"
    messages: tuple[dict[str, str], ...] = Field(repr=False)
    approval: str = Field(repr=False)
    expires_in_seconds: int = 600
    redactor_version: str
    prompt_version: str = PROMPT_CHECK_PROMPT_VERSION
    model_revision: str | None = None
    model_license: str | None = None


class PromptCheckResult(StrictModel):
    contract_version: Literal[PROMPT_CHECK_CONTRACT_VERSION] = PROMPT_CHECK_CONTRACT_VERSION
    check_id: str
    created_at: datetime
    provider: Literal["codex", "claude_code", "other"]
    agent_model: str | None = None
    metrics: tuple[PromptMetricReading, ...]
    context: ContextInference
    commentary: ModelCommentary
    summary: str
    engine_version: str
    rubric_version: str
    dashboard_path: str
    other_metric_families_note: str = (
        "Collaboration, logic and outcome metrics need the agent's replies and the session's evidence; "
        "they are computed for the session afterwards, not for a single prompt."
    )


class PromptCheckRecord(StrictModel):
    """Stored history row: metrics and counters only; no text."""

    check_id: str
    created_at: datetime
    provider: Literal["codex", "claude_code", "other"]
    agent_model: str | None = None
    language: str
    task_type: str
    prompt_chars: int = Field(ge=0)
    prior_message_count: int = Field(ge=0)
    depends_on_prior_context: bool
    verification_requested: bool
    metrics: tuple[PromptMetricReading, ...]
    commentary_state: str
    commentary_model_alias: str | None = None
    prompt_fingerprint: str


class PromptCheckHistory(StrictModel):
    contract_version: Literal[PROMPT_CHECK_CONTRACT_VERSION] = PROMPT_CHECK_CONTRACT_VERSION
    checks: tuple[PromptCheckRecord, ...]
    limit: int
    offset: int


class PromptCheckRepository(Protocol):
    def insert(self, record: PromptCheckRecord) -> None: ...

    def list(self, *, limit: int, offset: int) -> tuple[PromptCheckRecord, ...]: ...

    def get(self, check_id: str) -> PromptCheckRecord | None: ...


class Redactor(Protocol):
    version: str

    def redact(self, value: SecretStr) -> Any: ...


class LanguageDetector(Protocol):
    def detect(self, value: SecretStr) -> TextLanguage: ...


# ----- the service -----




class PromptCheckService:
    def __init__(
        self,
        repository: PromptCheckRepository,
        *,
        pseudonymize: Callable[[str, str], str],
        engine: TextMetricEngine = DEFAULT_COACHING_METRIC_ENGINE,
        redactor: Redactor | None = None,
        language_detector: LanguageDetector | None = None,
        chat: Callable[[str, bytes], tuple[int, bytes, str]] | None = None,
        active_model: Callable[[], str | None] | None = None,
        session_context: Callable[[str], tuple[PromptCheckMessage, ...]] | None = None,
        clock: Callable[[], datetime] | None = None,
        dashboard_path: str = "/prompt-checks",
        remote_model: str | None = None,
        remote_model_revision: str | None = None,
        remote_model_license: str | None = None,
    ) -> None:
        self._repository = repository
        self._pseudonymize = pseudonymize
        self._engine = engine
        if redactor is None:
            from ..infrastructure.redaction import DeterministicLocalRedactor

            redactor = DeterministicLocalRedactor()
        if language_detector is None:
            from ..infrastructure.language import DeterministicEnglishPolishDetector

            language_detector = DeterministicEnglishPolishDetector()
        self._redactor = redactor
        self._language = language_detector
        self._evaluator = DeterministicPromptEvaluator(
            pseudonymize=pseudonymize, redactor=redactor,
            language_detector=language_detector, engine=engine,
        )
        self._chat = chat
        self._active_model = active_model or (lambda: None)
        self._session_context = session_context
        self._clock = clock or (lambda: datetime.now(UTC))
        self._dashboard_path = dashboard_path
        self._remote_model = remote_model
        self._remote_revision = remote_model_revision
        self._remote_license = remote_model_license
        self._preview_key = secrets.token_bytes(32)

    # -- public --

    def configuration(self) -> PromptCheckConfiguration:
        return PromptCheckConfiguration(
            remote=self._remote_model is not None,
            model=self._remote_model,
            provider="litellm" if self._remote_model else "local",
        )

    def _remote_body(self, request: PromptCheckRequest) -> bytes:
        if request.session_id is not None:
            raise PromptCheckError("remote_session_context_forbidden")
        text = request.prompt.strip()
        readings = self._deterministic_readings("0" * 64, text, request.prior_messages)
        context = self._infer_context(text, request.prior_messages, readings)
        return self._commentary_body(request, text, readings, context)

    def _approval(self, body: bytes, issued: int) -> str:
        payload = str(issued).encode() + b"\0" + (self._remote_model or "").encode() + b"\0" + body
        return f"{issued}." + hmac.new(self._preview_key, payload, hashlib.sha256).hexdigest()

    def preview(self, request: PromptCheckRequest) -> PromptCheckPreview:
        if self._remote_model is None:
            raise PromptCheckError("remote_model_not_configured")
        body = self._remote_body(request)
        issued = int(self._clock().timestamp())
        return PromptCheckPreview(
            model=self._remote_model,
            messages=tuple(json.loads(body)["messages"]),
            approval=self._approval(body, issued),
            redactor_version=self._redactor.version,
            model_revision=self._remote_revision,
            model_license=self._remote_license,
        )

    def _require_remote_approval(self, request: PromptCheckRequest) -> None:
        body = self._remote_body(request)
        token = request.remote_approval or ""
        try:
            issued = int(token.split(".", 1)[0])
        except ValueError:
            raise PromptCheckError("remote_preview_required") from None
        age = int(self._clock().timestamp()) - issued
        if not 0 <= age <= 600 or not hmac.compare_digest(token, self._approval(body, issued)):
            raise PromptCheckError("remote_preview_required")

    def check(self, request: PromptCheckRequest) -> PromptCheckResult:
        if self._remote_model is not None and request.want_commentary:
            self._require_remote_approval(request)
        created_at = self._clock()
        if request.session_id and not request.prior_messages and self._session_context is not None:
            try:
                context_messages = self._session_context(request.session_id)[-MAX_CONTEXT_MESSAGES:]
            except Exception:
                context_messages = ()
            if context_messages:
                request = request.model_copy(update={"prior_messages": context_messages})
        prompt_text = request.prompt.strip()
        check_id = hashlib.sha256(
            f"{created_at.isoformat()}|{len(prompt_text)}|{hashlib.sha256(prompt_text.encode('utf-8')).hexdigest()}".encode("utf-8")
        ).hexdigest()
        readings = self._deterministic_readings(check_id, prompt_text, request.prior_messages)
        context = self._infer_context(prompt_text, request.prior_messages, readings)
        commentary = self._commentary(request, prompt_text, readings, context)
        if self._remote_model is not None:
            commentary = commentary.model_copy(update={
                "caveat": "Commentary and rewrites come from the configured LiteLLM model; "
                "they are suggestions, not metrics, and may be wrong.",
                "inference_provider": "litellm",
                "model_revision": self._remote_revision,
                "model_license": self._remote_license,
                "redactor_version": self._redactor.version,
                "adapter_version": "litellm-chat-v1",
            })
        summary = _summary(readings, context, commentary)
        result = PromptCheckResult(
            check_id=check_id,
            created_at=created_at,
            provider=request.provider,
            agent_model=request.agent_model,
            metrics=readings,
            context=context,
            commentary=commentary,
            summary=summary,
            engine_version=self._engine.engine_version,
            rubric_version=self._engine.rubric_version,
            dashboard_path=f"{self._dashboard_path}/{check_id}",
        )
        self._repository.insert(
            PromptCheckRecord(
                check_id=check_id,
                created_at=created_at,
                provider=request.provider,
                agent_model=request.agent_model,
                language=context.language,
                task_type=context.task_type,
                prompt_chars=context.prompt_chars,
                prior_message_count=len(request.prior_messages),
                depends_on_prior_context=context.depends_on_prior_context,
                verification_requested=context.verification_requested,
                metrics=readings,
                commentary_state=commentary.state,
                commentary_model_alias=commentary.model_alias,
                prompt_fingerprint=self._pseudonymize("prompt-check:text", prompt_text),
            )
        )
        return result

    def history(self, *, limit: int = 50, offset: int = 0) -> PromptCheckHistory:
        limit = max(1, min(limit, MAX_HISTORY_PAGE))
        return PromptCheckHistory(checks=self._repository.list(limit=limit, offset=max(0, offset)), limit=limit, offset=max(0, offset))

    def get(self, check_id: str) -> PromptCheckRecord:
        if PSEUDONYM_PATTERN.fullmatch(check_id) is None:
            raise PromptCheckError("check_not_found")
        record = self._repository.get(check_id)
        if record is None:
            raise PromptCheckError("check_not_found")
        return record

    # -- deterministic metrics through the coaching engine --

    def _deterministic_readings(
        self, check_id: str, prompt_text: str, prior: tuple[PromptCheckMessage, ...]
    ) -> tuple[PromptMetricReading, ...]:
        return self._evaluator.evaluate(check_id, prompt_text, prior)

    # -- context inference (content-free outputs) --

    def _infer_context(self, prompt_text, prior, readings) -> ContextInference:
        return infer_context(prompt_text, prior, readings, self._language)

    # -- model commentary --

    def _commentary(
        self,
        request: PromptCheckRequest,
        prompt_text: str,
        readings: tuple[PromptMetricReading, ...],
        context: ContextInference,
    ) -> ModelCommentary:
        if not request.want_commentary:
            return ModelCommentary(state="skipped")
        alias = self._active_model()
        if alias is None or self._chat is None:
            return ModelCommentary(state="no_active_model")
        body = self._commentary_body(request, prompt_text, readings, context)
        try:
            status, payload, _ = self._chat(alias, body)
        except Exception:
            return ModelCommentary(state="model_error", model_alias=alias)
        if status != 200:
            return ModelCommentary(state="model_error", model_alias=alias)
        text = completed_chat_content(payload)
        parsed = parse_commentary_reply(text, prompt_chars=len(prompt_text))
        if parsed is None:
            return ModelCommentary(state="reply_invalid", model_alias=alias)
        return parsed.model_copy(update={"model_alias": alias})

    def _commentary_body(
        self, request: PromptCheckRequest, prompt_text: str,
        readings: tuple[PromptMetricReading, ...], context: ContextInference,
    ) -> bytes:
        user_message = _commentary_input(request, prompt_text, readings, context)
        if self._remote_model is not None:
            from ..infrastructure.redaction import LocalRedactionError
            try:
                user_message = self._redactor.redact(SecretStr(user_message)).text.get_secret_value()
            except LocalRedactionError:
                raise PromptCheckError("remote_redaction_failed") from None
        payload = {
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.2,
            "max_tokens": 1_100,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if self._remote_model is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "prompt_commentary", "schema": _CommentaryReply.model_json_schema()},
            }
        return json.dumps(payload).encode("utf-8")


# ----- helpers -----






def _summary(readings: tuple[PromptMetricReading, ...], context: ContextInference, commentary: ModelCommentary) -> str:
    parts: list[str] = []
    known = [r for r in readings if r.state == "known"]
    for reading in known:
        missing = [cue.label for cue in reading.cues if cue.status == "missing"]
        piece = f"{reading.display_name}: {reading.numerator}/{reading.denominator}"
        if missing:
            piece += " (missing: " + ", ".join(missing) + ")"
        parts.append(piece)
    unknown = [
        f"{r.display_name} ({EXPLANATION_PHRASES.get(r.explanation_code, r.explanation_code.replace('_', ' '))})"
        for r in readings
        if r.state != "known"
    ]
    if unknown:
        parts.append("not measurable on this prompt: " + "; ".join(unknown))
    parts.append(f"task type: {context.task_type}; language: {context.language}; {context.prompt_words} words")
    parts.append(
        "depends on earlier conversation: "
        + ("yes" if context.depends_on_prior_context else "no")
        + (f" ({context.prior_context_supplied} earlier messages supplied)" if context.prior_context_supplied else " (no earlier messages supplied)")
    )
    parts.append("verification requested: " + ("yes" if context.verification_requested else "no"))
    if context.missing_elements:
        parts.append("consider adding: " + "; ".join(context.missing_elements))
    if commentary.state == "ok":
        top = [f"[{f.severity}] {f.suggestion}" for f in commentary.findings[:3]]
        if top:
            parts.append("model suggestions: " + " | ".join(top))
        if commentary.reformulated_prompt:
            parts.append("a reformulated prompt is included (model output; keep what matches your intent)")
    elif commentary.state == "no_active_model":
        parts.append("no local model active: deterministic cues only (activate one on the Models page for commentary)")
    return "Prompt check - " + ". ".join(parts) + "."


__all__ = (
    "CUE_LABELS",
    "EXPLANATION_PHRASES",
    "MAX_CONTEXT_MESSAGES",
    "MAX_PROMPT_CHARS",
    "PROMPT_CHECK_CONTRACT_VERSION",
    "PROMPT_CHECK_PROMPT_VERSION",
    "PROMPT_METRIC_KEYS",
    "CommentaryFinding",
    "ContextInference",
    "ModelCommentary",
    "PromptCheckError",
    "PromptCheckHistory",
    "PromptCheckMessage",
    "PromptCheckRecord",
    "PromptCheckRepository",
    "PromptCheckRequest",
    "PromptCheckResult",
    "PromptCheckService",
    "PromptCue",
    "PromptMetricReading",
    "ReformulatedElement",
    "parse_commentary_reply",
)
