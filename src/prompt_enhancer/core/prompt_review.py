"""Prompt review components shared by the app and versioned workflows.

These functions neither read sessions nor persist content or invoke a provider.
"""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Literal, Protocol
from pydantic import Field, SecretStr, ValidationError, field_validator
from ..domain import StrictModel
from ..application.model_reply import model_json_object
from .prompt_evaluation import PromptMetricReading, LanguageDetector
from .review_validation import ReviewValidationIssue, schema_issue

class ReviewRequestLike(Protocol):
    prior_messages: tuple[PromptCheckMessage, ...]

PROMPT_CHECK_CONTRACT_VERSION = "prompt-check.v1"

PROMPT_CHECK_PROMPT_VERSION = "prompt-check-commentary-v2-complete-json"

MAX_PROMPT_CHARS = 20_000

MAX_CONTEXT_MESSAGES = 24

MAX_CONTEXT_MESSAGE_CHARS = 8_000

MAX_CONTEXT_TOTAL_CHARS = 40_000

MAX_COMMENTARY_INPUT_CHARS = 14_000

_TASK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fix", re.compile(r"\b(fix|debug|resolve|repair|bug|error|crash|fail(?:s|ing|ure)?|napraw|błąd|blad|nie działa|nie dziala|crashuje)\b", re.I)),
    ("test", re.compile(r"\b(write|add|create)\s+(unit\s+|integration\s+)?tests?\b|\btest coverage\b|\bnapisz testy\b|\bdodaj testy\b", re.I)),
    ("refactor", re.compile(r"\b(refactor|clean ?up|simplify|restructure|rename|zrefaktor\w*|uprość|uprosc|przenieś|przenies)\b", re.I)),
    ("review", re.compile(r"\b(review|audit|assess|critique|check (?:this|the) (?:code|pr|diff)|zrecenzuj|przejrzyj|oceń|ocen|audyt)\b", re.I)),
    ("explain", re.compile(r"\b(explain|why does|what does|how does|describe|walk me through|wyjaśnij|wyjasnij|dlaczego|jak działa|jak dziala|opisz)\b", re.I)),
    ("plan", re.compile(r"\b(plan|design|architect|propose|outline|roadmap|zaplanuj|zaprojektuj|zaproponuj)\b", re.I)),
    ("write", re.compile(r"\b(write|draft|document|readme|docs?|changelog|napisz|udokumentuj|dokumentacj\w*)\b", re.I)),
    ("implement", re.compile(r"\b(implement|add|create|build|introduce|support|make|generate|zaimplementuj|dodaj|stwórz|stworz|zbuduj|wprowadź|wprowadz)\b", re.I)),
)

_PRIOR_CONTEXT_MARKERS = re.compile(
    r"\b(as (?:before|above|earlier|discussed|mentioned|agreed)|like (?:before|last time)|the same (?:as|way)|again|"
    r"(?:that|this|the) (?:one|file|function|bug|issue|approach|plan|error|change)|continue|go on|next step|"
    r"jak (?:wcześniej|wczesniej|poprzednio|ustaliliśmy|ustalilismy|wyżej|wyzej)|to samo|tak samo|"
    r"(?:ten|ta|to|tego|tej|tym) (?:sam|sama|samo|plik|błąd|blad|problem|plan|zmian\w*)|kontynuuj|dalej)\b",
    re.I,
)

_LEADING_PRONOUN = re.compile(r"^\s*(it|this|that|they|those|these|he|she|to|tego|tym|je|go)\b", re.I)

_VERIFICATION_MARKERS = re.compile(
    r"\b(test(?:s|ed|ing)?|verify|verif(?:y|ied|ication)|validate|check (?:that|if|whether)|make sure|run (?:the )?(?:tests|build|linter|suite)|"
    r"pytest|vitest|jest|npm test|cargo test|go test|ci passes?|green|"
    r"przetestuj|sprawdź|sprawdz|zweryfikuj|upewnij się|upewnij sie|uruchom testy|testy przechodzą|testy przechodza)\b",
    re.I,
)

_FILE_REFERENCE = re.compile(r"(?<![\w/])[\w./-]+\.(?:py|ts|tsx|js|jsx|json|md|yml|yaml|toml|rs|go|java|kt|cs|cpp|c|h|sql|css|html|sh|ps1)\b")

_CODE_IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\(\)|`[^`\n]{1,80}`|\b[a-z]+(?:_[a-z0-9]+){1,}\b|\b[a-z]+(?:[A-Z][a-z0-9]+){1,}\b")

_URL = re.compile(r"https?://\S+")

_SENTENCE = re.compile(r"[.!?]+(?:\s|$)")

_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)]|\[[ xX-]\])\s+", re.M)

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

_COMMON_WORDS = frozenset(
    {
        "about", "after", "again", "before", "between", "could", "every", "first", "请", "should", "their", "there",
        "these", "thing", "things", "those", "through", "under", "which", "while", "would", "write", "please", "make",
        "change", "changes", "update", "implement", "create", "tests", "test", "using", "where", "other", "without",
        "także", "które", "który", "która", "proszę", "zrobić", "dodać", "zmiany", "zmianę", "przez", "jest", "oraz",
    }
)

class PromptCheckMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_CONTEXT_MESSAGE_CHARS)

class ContextInference(StrictModel):
    task_type: Literal["implement", "fix", "refactor", "review", "explain", "plan", "write", "test", "other"]
    language: Literal["en", "pl", "mixed", "unknown"]
    prompt_chars: int = Field(ge=0)
    prompt_words: int = Field(ge=0)
    sentence_count: int = Field(ge=0)
    bullet_count: int = Field(ge=0)
    question_count: int = Field(ge=0)
    file_references: int = Field(ge=0)
    code_identifiers: int = Field(ge=0)
    urls: int = Field(ge=0)
    prior_context_supplied: int = Field(ge=0)
    depends_on_prior_context: bool
    verification_requested: bool
    missing_elements: tuple[str, ...] = ()

class CommentaryFinding(StrictModel):
    aspect: Literal["goal", "scope", "context", "constraints", "acceptance", "deliverable", "verification", "ambiguity", "other"]
    severity: Literal["low", "medium", "high"]
    why: str = Field(min_length=1, max_length=600)
    suggestion: str = Field(min_length=1, max_length=800)

    @field_validator("why", "suggestion")
    @classmethod
    def _nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model_reply_invalid")
        return value.strip()

class ReformulatedElement(StrictModel):
    element: Literal["goal", "scope", "context", "constraints", "acceptance", "deliverable", "verification", "other"]
    original: str | None = Field(default=None, max_length=600)
    suggested: str = Field(min_length=1, max_length=1_200)

    @field_validator("suggested")
    @classmethod
    def _nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model_reply_invalid")
        return value.strip()

class _CommentaryReply(StrictModel):
    findings: list[CommentaryFinding] = Field(default_factory=list, max_length=6)
    reformulated_prompt: str | None = Field(default=None, min_length=1, max_length=MAX_PROMPT_CHARS * 2 + 2_000)
    reformulated_elements: list[ReformulatedElement] = Field(default_factory=list, max_length=8)
    notes: str | None = Field(default=None, min_length=1, max_length=1_000)

    @field_validator("reformulated_prompt", "notes")
    @classmethod
    def _nonblank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("model_reply_invalid")
        return value.strip() if value is not None else None

class ModelCommentary(StrictModel):
    state: Literal["ok", "no_active_model", "model_error", "reply_invalid", "skipped"]
    model_alias: str | None = None
    prompt_version: str = PROMPT_CHECK_PROMPT_VERSION
    inference_provider: Literal["local", "litellm"] = "local"
    model_revision: str | None = None
    model_license: str | None = None
    redactor_version: str | None = None
    adapter_version: str | None = None
    findings: tuple[CommentaryFinding, ...] = ()
    reformulated_prompt: str | None = Field(default=None, max_length=MAX_PROMPT_CHARS * 2 + 2_000)
    reformulated_elements: tuple[ReformulatedElement, ...] = ()
    notes: str | None = Field(default=None, max_length=1_000)
    caveat: str = (
        "Commentary and rewrites come from a local model; they are suggestions, not metrics, and may be wrong. "
        "The deterministic cues above are what was actually detected."
    )

_SYSTEM_PROMPT = (
    "You review prompts that people send to coding agents (Claude Code, Codex). You get the prompt about to be sent, "
    "optionally the earlier conversation, and deterministic findings. Answer with strict JSON only, no markdown, no code fences: "
    '{"findings":[{"aspect":"goal|scope|context|constraints|acceptance|deliverable|verification|ambiguity|other",'
    '"severity":"low|medium|high","why":"...","suggestion":"..."}],'
    '"reformulated_prompt":"...","reformulated_elements":[{"element":"goal|scope|context|constraints|acceptance|deliverable|verification|other",'
    '"original":"... or null","suggested":"..."}],"notes":"..."}. '
    "Rules: keep the person's intent, language and tone; never invent facts or values - any parameter, number, path or name the person "
    "did not state must appear as a placeholder like <specify: max retries> so the person fills it; the reformulated prompt must stay "
    "concise (at most twice the original length); "
    "at most six findings ordered by severity; if the prompt is already good say so in notes and keep findings short; "
    "if the prompt relies on the earlier conversation, say what must be restated when starting fresh."
)

def _commentary_input(
    request: ReviewRequestLike,
    prompt_text: str,
    readings: tuple[PromptMetricReading, ...],
    context: ContextInference,
) -> str:
    budget = MAX_COMMENTARY_INPUT_CHARS - min(len(prompt_text), MAX_COMMENTARY_INPUT_CHARS // 2)
    prior_lines: list[str] = []
    used = 0
    for item in reversed(request.prior_messages):
        snippet = item.content.strip()
        if len(snippet) > 1_500:
            snippet = snippet[:1_500] + " …"
        if used + len(snippet) > budget:
            break
        prior_lines.append(f"{item.role}: {snippet}")
        used += len(snippet)
    prior_lines.reverse()
    findings = []
    for reading in readings:
        if reading.state == "known":
            missing = [cue.label for cue in reading.cues if cue.status == "missing"]
            findings.append(f"- {reading.display_name}: {reading.numerator}/{reading.denominator}" + (f" (missing: {', '.join(missing)})" if missing else ""))
        else:
            findings.append(f"- {reading.display_name}: {reading.state} ({reading.explanation_code})")
    parts = []
    if prior_lines:
        parts.append("Earlier conversation (most recent last):\n" + "\n".join(prior_lines))
    else:
        parts.append("Earlier conversation: none supplied.")
    parts.append("Prompt to review:\n" + prompt_text[: MAX_COMMENTARY_INPUT_CHARS // 2])
    parts.append(
        "Deterministic findings:\n" + "\n".join(findings)
        + f"\n- task type guess: {context.task_type}; language: {context.language}; "
        + f"depends on earlier conversation: {'yes' if context.depends_on_prior_context else 'no'}; "
        + f"verification requested: {'yes' if context.verification_requested else 'no'}"
    )
    return "\n\n".join(parts)

def parse_commentary_reply(text: object, *, prompt_chars: int) -> ModelCommentary | None:
    """Reject malformed suggestions; never manufacture labels, reasons or text."""

    return validate_commentary_reply(text, prompt_chars=prompt_chars)[0]


def validate_commentary_reply(text: object, *, prompt_chars: int) -> tuple[ModelCommentary | None, ReviewValidationIssue | None]:
    """Return the first safe rejection reason while preserving strict acceptance."""

    data = model_json_object(text)
    if data is None:
        return None, ReviewValidationIssue(reason="invalid_json", field="reply")
    if type(prompt_chars) is not int or prompt_chars < 0:
        return None, ReviewValidationIssue(reason="schema_mismatch", field="reply")
    try:
        reply = _CommentaryReply.model_validate(data, strict=True)
    except ValidationError as error:
        return None, schema_issue(error)
    if reply.reformulated_prompt is not None and len(reply.reformulated_prompt) > max(prompt_chars * 2 + 2_000, 200):
        return None, ReviewValidationIssue(reason="rewrite_too_long", field="reformulated_prompt")
    if not (reply.findings or reply.reformulated_prompt or reply.reformulated_elements or reply.notes):
        return None, ReviewValidationIssue(reason="empty_review", field="reply")
    return ModelCommentary(
        state="ok",
        findings=tuple(sorted(reply.findings, key=lambda finding: _SEVERITY_ORDER[finding.severity])),
        reformulated_prompt=reply.reformulated_prompt,
        reformulated_elements=tuple(reply.reformulated_elements),
        notes=reply.notes,
    ), None

def infer_context(
    prompt_text: str, prior: tuple[PromptCheckMessage, ...], readings: tuple[PromptMetricReading, ...],
    language_detector: LanguageDetector,
) -> ContextInference:
    language = language_detector.detect(SecretStr(prompt_text))
    # Earliest-mentioned task verb wins; the pattern order only breaks ties.
    task_type: str = "other"
    best: tuple[int, int] | None = None
    for order, (name, pattern) in enumerate(_TASK_PATTERNS):
        match = pattern.search(prompt_text)
        if match and (best is None or (match.start(), order) < best):
            best = (match.start(), order)
            task_type = name
    words = len(prompt_text.split())
    depends = bool(_PRIOR_CONTEXT_MARKERS.search(prompt_text)) or bool(_LEADING_PRONOUN.match(prompt_text)) or (
        words <= 6 and not _FILE_REFERENCE.search(prompt_text)
    )
    if not depends and prior and not _FILE_REFERENCE.search(prompt_text):
        # The prompt names things only the earlier turns identify (shared rare words, no explicit file).
        prompt_tokens = {t for t in _WORD.findall(prompt_text.casefold()) if len(t) >= 5 and t not in _COMMON_WORDS}
        prior_tokens = {t for m in prior for t in _WORD.findall(m.content.casefold()) if len(t) >= 5}
        depends = len(prompt_tokens & prior_tokens) >= 2
    missing: list[str] = []
    for reading in readings:
        if reading.state != "known":
            continue
        for cue in reading.cues:
            if cue.status == "missing" and cue.label not in missing:
                missing.append(cue.label)
        if reading.key == "prompt.constraint_precision" and reading.denominator == 0 and "constraints" not in " ".join(missing):
            pass
    by_key = {reading.key: reading for reading in readings}
    constraints = by_key.get("prompt.constraint_precision")
    if constraints is not None and constraints.state != "known":
        missing.append("any constraint (what must not change, limits, platform)")
    acceptance = by_key.get("prompt.acceptance_testability")
    if acceptance is not None and acceptance.state != "known":
        missing.append("an acceptance criterion (how you will know it is done)")
    deliverable = by_key.get("prompt.deliverable_contract")
    if deliverable is not None and deliverable.state != "known":
        missing.append("the deliverable (what should exist at the end, where, in what form)")
    verification = bool(_VERIFICATION_MARKERS.search(prompt_text))
    if not verification:
        missing.append("how the result should be verified (tests, build, inspection)")
    return ContextInference(
        task_type=task_type,  # type: ignore[arg-type]
        language=language.value,  # type: ignore[arg-type]
        prompt_chars=len(prompt_text),
        prompt_words=words,
        sentence_count=max(1, len(_SENTENCE.findall(prompt_text))) if prompt_text.strip() else 0,
        bullet_count=len(_BULLET.findall(prompt_text)),
        question_count=prompt_text.count("?"),
        file_references=len(_FILE_REFERENCE.findall(prompt_text)),
        code_identifiers=len(_CODE_IDENTIFIER.findall(prompt_text)),
        urls=len(_URL.findall(prompt_text)),
        prior_context_supplied=len(prior),
        depends_on_prior_context=depends,
        verification_requested=verification,
        missing_elements=tuple(missing[:8]),
    )
