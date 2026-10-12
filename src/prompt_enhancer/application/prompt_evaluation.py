"""Shared deterministic prompt evaluator; no history, UI, or inference composition."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal, Protocol
from pydantic import SecretStr
from ..domain import DataTier, Provider, StrictModel
from .analysis.coaching_baselines import DEFAULT_COACHING_METRIC_ENGINE
from .analysis.text_analysis_presets import COACHING_PROFILE_V1
from .analysis.text_baselines import TextMetricEngine
from .analysis.text_contracts import (
    EphemeralRedactedMessage, P1LocalAnalysisGrant, P1TextAnalysisInput,
    TextAnalysisScope, TextAnalysisScopeKind, TextAnalysisScopeState,
    TextLanguage, TextMessageKind, TextMetricResult, TextRole,
)


class MessageLike(Protocol):
    role: str
    content: str


class Redactor(Protocol):
    version: str
    def redact(self, value: SecretStr) -> Any: ...


class LanguageDetector(Protocol):
    def detect(self, value: SecretStr) -> TextLanguage: ...


PROMPT_METRIC_KEYS: tuple[str, ...] = (
    "prompt.task_definition_coverage",
    "prompt.problem_evidence_quality",
    "prompt.context_sufficiency",
    "prompt.constraint_precision",
    "prompt.acceptance_testability",
    "prompt.deliverable_contract",
)
CUE_LABELS: Mapping[str, str] = {
    "task.action": "what to do (an action verb)",
    "task.target": "what to act on (the target)",
    "task.outcome": "the intended result",
    "problem.observed": "observed behaviour",
    "problem.expected": "expected behaviour",
    "problem.reproduction": "how to reproduce",
    "problem.environment": "environment or version",
    "context.current_state": "current state",
    "context.environment": "environment or version",
    "context.boundary": "relevant boundary (files, modules, scope)",
    "constraints.detected": "constraint clauses",
    "constraints.precise": "precise constraints (value, boundary, platform, version, prohibition)",
    "acceptance.requirements": "requirement clauses",
    "acceptance.checkable": "checkable requirements (observable check, threshold, pass condition)",
    "deliverables.detected": "deliverable clauses",
    "deliverables.detailed": "detailed deliverables (format, interface, location, audience, compatibility)",
}

class PromptCue(StrictModel):
    code: str
    label: str
    status: Literal["detected", "missing", "counted", "unknown"]
    count: int | None = None


class PromptMetricReading(StrictModel):
    key: str
    display_name: str
    description: str
    state: Literal["known", "unknown", "not_applicable", "abstained", "execution_error"]
    value: float | None = None
    numerator: int | None = None
    denominator: int | None = None
    higher_is_better: bool = True
    explanation_code: str
    cues: tuple[PromptCue, ...] = ()


class DeterministicPromptEvaluator:
    def __init__(self, *, pseudonymize: Callable[[str, str], str],
                 redactor: Redactor, language_detector: LanguageDetector,
                 engine: TextMetricEngine = DEFAULT_COACHING_METRIC_ENGINE):
        self._pseudonymize = pseudonymize
        self._redactor = redactor
        self._language = language_detector
        self._engine = engine

    def evaluate(
        self, check_id: str, prompt_text: str, prior: tuple[MessageLike, ...]
    ) -> tuple[PromptMetricReading, ...]:
        session_id = self._pseudonymize("prompt-check:session", check_id)
        messages: list[EphemeralRedactedMessage] = []
        sequence = 0
        saw_agent = False
        for item in prior:
            redacted = self._redactor.redact(SecretStr(item.content))
            text = redacted.text if isinstance(redacted.text, SecretStr) else SecretStr(str(redacted.text))
            if item.role == "assistant":
                role, kind, saw_agent = TextRole.AGENT, TextMessageKind.RESPONSE, True
            else:
                role, kind = TextRole.USER, (TextMessageKind.FEEDBACK if saw_agent else TextMessageKind.REQUEST)
            messages.append(
                EphemeralRedactedMessage(
                    message_id=self._pseudonymize("prompt-check:message", f"{check_id}:{sequence}"),
                    sequence=sequence,
                    role=role,
                    kind=kind,
                    language=self._language.detect(text),
                    text=text,
                )
            )
            sequence += 1
        focus_redacted = self._redactor.redact(SecretStr(prompt_text))
        focus_text = focus_redacted.text if isinstance(focus_redacted.text, SecretStr) else SecretStr(str(focus_redacted.text))
        focus_id = self._pseudonymize("prompt-check:message", f"{check_id}:{sequence}")
        messages.append(
            EphemeralRedactedMessage(
                message_id=focus_id,
                sequence=sequence,
                role=TextRole.USER,
                kind=TextMessageKind.REQUEST,
                language=self._language.detect(focus_text),
                text=focus_text,
            )
        )
        available = frozenset({TextMessageKind.REQUEST, TextMessageKind.FEEDBACK, TextMessageKind.RESPONSE})
        total_chars = sum(len(m.text.get_secret_value()) for m in messages)
        scope = TextAnalysisScope(
            kind=TextAnalysisScopeKind.FULL_AVAILABLE_SESSION,
            state=TextAnalysisScopeState.COMPLETE,
            requested_max_messages=max(1, len(messages)),
            requested_max_characters=max(1, min(total_chars, 100_000)),
            source_history_complete=True,
        )
        fingerprint = self._pseudonymize("prompt-check:window", f"{check_id}:{total_chars}:{len(messages)}")
        context = P1TextAnalysisInput(
            provider=Provider.SYNTHETIC,
            session_id=session_id,
            provider_version="prompt-check-1",
            adapter_version="prompt-check-adapter-1",
            source_schema_version="prompt-check-source-1",
            content_schema_version="prompt-check-content-1",
            redactor_version=self._redactor.version,
            analysis_scope=scope,
            text_extraction_complete=True,
            available_message_kinds=available,
            analysis_window_fingerprint=fingerprint,
            focus_message_id=focus_id,
            observed_message_count=len(messages),
            eligible_message_count=len(messages),
            messages=tuple(messages),
            task_profile=COACHING_PROFILE_V1.task_profile,
        )
        grant = P1LocalAnalysisGrant(
            provider=Provider.SYNTHETIC,
            session_id=session_id,
            analysis_window_fingerprint=fingerprint,
            data_tier=DataTier.REDACTED_CONTENT,
            consent_active=True,
            local_only=True,
            content_persistence_allowed=False,
        )
        results = self._engine.compute(
            context, grant, pack_key=self._engine.pack_key, pack_version=self._engine.pack_version
        )
        by_key = {result.observation.key: result for result in results}
        return tuple(_reading(by_key[key]) for key in PROMPT_METRIC_KEYS if key in by_key)


def _reading(result: TextMetricResult) -> PromptMetricReading:
    fraction = result.fraction
    value = result.observation.numeric_value
    definition_name = getattr(result.observation, "display_name", None)
    description = ""
    display_name = definition_name or result.observation.key
    from .analysis.coaching_baselines import COACHING_METRIC_DEFINITIONS

    for definition in COACHING_METRIC_DEFINITIONS:
        if definition.key == result.observation.key:
            display_name, description = definition.display_name, definition.description
            break
    cues = tuple(
        PromptCue(
            code=signal.code,
            label=CUE_LABELS.get(signal.code, signal.code.replace(".", " ").replace("_", " ")),
            status=signal.status.value,  # type: ignore[arg-type]
            count=signal.count,
        )
        for signal in result.signals
    )
    return PromptMetricReading(
        key=result.observation.key,
        display_name=display_name,
        description=description,
        state=result.value_state.value,  # type: ignore[arg-type]
        value=value,
        numerator=fraction.numerator if fraction else None,
        denominator=fraction.denominator if fraction else None,
        higher_is_better=result.direction.value != "lower_is_better",
        explanation_code=result.explanation_code,
        cues=cues,
    )
