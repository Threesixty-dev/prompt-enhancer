"""Model-judge lane: a local LLM rates the calibration questions (ADR 0013 §4).

The active local model reads the same redacted analysis window the P1
pipeline reads (local, read-only, never persisted) and answers the three
Calibration questions on the same scale - low / medium / high / cannot_judge.
Those answers are **model judgments**: stored separately from product
metrics with the model's identity and the prompt version, never as a metric
value, and compared with human ratings through the estimator agreement math.
Objective evidence (ADR 0012) always outranks them; nothing here makes a
metric calibrated.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import json
import re
import threading
from typing import Literal, Protocol

from pydantic import Field

from ...domain import DataTier, PSEUDONYM_PATTERN, Provider, StrictModel
from ..estimators.calibration import AgreementObservation, EvaluationState, model_human_agreement
from .calibration_ratings import CALIBRATION_METRIC_KEYS, RatingLabel
from .text_contracts import P1TextAnalysisInput, TextRole, TextTaskProfile
from .text_source import TextAnalysisPurpose, TextAnalysisSelection, TextSourceAccessGrant


MODEL_JUDGE_CONTRACT_VERSION = "model-judge.v1"
JUDGE_PROMPT_VERSION = "judge-v1"
#: ~4k tokens of transcript so prompt + window stay well inside an 8192 context.
MAX_WINDOW_CHARACTERS = 15_000
MAX_WINDOW_MESSAGES = 120
JUDGE_MAX_TOKENS = 220

_QUESTIONS: dict[str, str] = {
    "prompt.task_definition_coverage": "Did the person say clearly what they wanted done - scope, deliverable, done-when?",
    "prompt.context_sufficiency": "Did the prompts carry the context the agent needed (files, constraints, prior decisions) instead of leaving it to guess?",
    "outcome.verification_strategy_adequacy": "Was the work checked in a way that fits the change - tests, builds, inspection - before it was called done?",
}
_SYSTEM_PROMPT = (
    "You rate a coding-agent session for a calibration study. You will see a redacted transcript window "
    "(USER / AGENT / PLAN lines). For each question answer exactly one of: low, medium, high, cannot_judge. "
    "Reply with strict JSON only, no prose, of the form "
    '{"prompt.task_definition_coverage": "...", "prompt.context_sufficiency": "...", "outcome.verification_strategy_adequacy": "..."}.'
)


class ModelJudgment(StrictModel):
    session_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    metric_key: str = Field(min_length=1, max_length=120)
    label: RatingLabel
    model_alias: str = Field(min_length=1, max_length=64)
    model_identity: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=64)
    window_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    judged_at: datetime


class JudgeOutcome(StrictModel):
    contract_version: Literal[MODEL_JUDGE_CONTRACT_VERSION] = MODEL_JUDGE_CONTRACT_VERSION
    session_id: str
    model_alias: str
    judgments: tuple[ModelJudgment, ...]
    raw_valid: bool


class SessionInterpretation(StrictModel):
    """Plain-language reading of one session's metrics by the local model - commentary, never a metric."""

    contract_version: Literal[MODEL_JUDGE_CONTRACT_VERSION] = MODEL_JUDGE_CONTRACT_VERSION
    session_id: str
    model_alias: str
    strengths: tuple[str, ...] = ()
    improvements: tuple[str, ...] = ()
    reframed_prompt: str | None = None
    summary: str | None = None
    metrics_seen: int = Field(ge=0)
    caveat: str = (
        "Written by a local model from the session's metric states and the redacted window; it is an interpretation, "
        "not a measurement, and may be wrong. Unknown metrics were reported to it as unknown."
    )


class SessionJudgments(StrictModel):
    """Every stored judgment for one session, grouped by model, with the questions asked."""

    contract_version: Literal[MODEL_JUDGE_CONTRACT_VERSION] = MODEL_JUDGE_CONTRACT_VERSION
    session_id: str
    active_model_alias: str | None = None
    questions: dict[str, str]
    judgments: tuple[ModelJudgment, ...]
    caveat: str = "Model judgments are labels from a local model, stored apart from metrics; they are never metric values."


class MetricAgreement(StrictModel):
    metric_key: str
    pairs: int = Field(ge=0)
    agreement_rate: float | None = None
    cohen_kappa: float | None = None
    state: str
    reason: str | None = None


class JudgeAgreementReport(StrictModel):
    contract_version: Literal[MODEL_JUDGE_CONTRACT_VERSION] = MODEL_JUDGE_CONTRACT_VERSION
    model_alias: str | None
    judged_sessions: int = Field(ge=0)
    metrics: tuple[MetricAgreement, ...]
    caveat: str = (
        "Model judgments are experimental and are never product metrics; agreement with human ratings "
        "is evidence for the activation gate, not calibration by itself."
    )


class JudgeSweepStatus(StrictModel):
    contract_version: Literal[MODEL_JUDGE_CONTRACT_VERSION] = MODEL_JUDGE_CONTRACT_VERSION
    running: bool
    model_alias: str | None = None
    total: int = Field(ge=0)
    done: int = Field(ge=0)
    failed: int = Field(ge=0)
    last_error_code: str | None = None


class ModelJudgmentRepository(Protocol):
    def upsert(self, judgment: ModelJudgment) -> None: ...

    def list(self, *, session_id: str | None = None, model_alias: str | None = None) -> tuple[ModelJudgment, ...]: ...


class HumanRatingReader(Protocol):
    def list_ratings(self, *, rater_id: str | None = None, session_id: str | None = None): ...


class ModelJudgeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def render_window(context: P1TextAnalysisInput, *, max_characters: int = MAX_WINDOW_CHARACTERS) -> str:
    """Render the redacted window as USER/AGENT/PLAN lines, newest kept within budget."""

    lines: list[str] = []
    for message in context.messages[-MAX_WINDOW_MESSAGES:]:
        role = "PLAN" if message.kind.value == "plan" else ("USER" if message.role is TextRole.USER else "AGENT")
        text = message.text.get_secret_value().strip()
        if text:
            lines.append(f"{role}: {text}")
    rendered = "\n".join(lines)
    if len(rendered) > max_characters:
        rendered = "[...earlier part omitted...]\n" + rendered[-max_characters:]
    return rendered


_LABELS = {label.value: label for label in RatingLabel}


def parse_judge_reply(text: str) -> dict[str, RatingLabel] | None:
    """Strict JSON with the three keys; tolerate a fenced block around it."""

    candidate = text.strip()
    fenced = re.search(r"\{.*\}", candidate, re.S)
    if fenced:
        candidate = fenced.group(0)
    try:
        payload = json.loads(candidate)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    labels: dict[str, RatingLabel] = {}
    for key in CALIBRATION_METRIC_KEYS:
        value = payload.get(key)
        if not isinstance(value, str) or value.strip().lower() not in _LABELS:
            return None
        labels[key] = _LABELS[value.strip().lower()]
    return labels


class ModelJudgeService:
    def __init__(
        self,
        *,
        repository: ModelJudgmentRepository,
        ratings: HumanRatingReader,
        access,
        source_factory: Callable[[Provider], object],
        chat: Callable[[str, bytes], tuple[int, bytes, str]],
        active_model: Callable[[], tuple[str, str] | None],
        session_lookup: Callable[[str], object | None],
        metrics_lookup: Callable[[str], list[dict[str, object]]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._ratings = ratings
        self._access = access
        self._source_factory = source_factory
        self._chat = chat
        self._active_model = active_model
        self._session_lookup = session_lookup
        self._metrics_lookup = metrics_lookup
        self._clock = clock
        self._sweep_lock = threading.Lock()
        self._sweep = JudgeSweepStatus(running=False, total=0, done=0, failed=0)

    # ----- one session -----

    def _window(self, provider: Provider, session_id: str) -> P1TextAnalysisInput:
        if not self._access.has_active_consent(provider, DataTier.REDACTED_CONTENT):
            raise ModelJudgeError("consent_required")
        selection = TextAnalysisSelection(provider=provider, session_id=session_id)
        grant = TextSourceAccessGrant(
            purpose=TextAnalysisPurpose.TEXT_ANALYSIS,
            provider=provider,
            session_id=session_id,
            data_tier=DataTier.REDACTED_CONTENT,
            per_run_confirmation_active=True,
            local_only=True,
            content_persistence_allowed=False,
        )
        source = self._source_factory(provider)
        return source.read(selection=selection, grant=grant, task_profile=TextTaskProfile(applicability=()))  # type: ignore[attr-defined]

    def judge(self, session_id: str) -> JudgeOutcome:
        active = self._active_model()
        if active is None:
            raise ModelJudgeError("no_active_model")
        alias, identity = active
        session = self._session_lookup(session_id)
        if session is None:
            raise ModelJudgeError("session_not_found")
        provider = Provider(getattr(session, "provider"))
        try:
            context = self._window(provider, session_id)
        except ModelJudgeError:
            raise
        except Exception:
            raise ModelJudgeError("window_unavailable") from None
        window = render_window(context)
        body = json.dumps(
            {
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": "Questions:\n" + "\n".join(f"- {key}: {q}" for key, q in _QUESTIONS.items()) + "\n\nTranscript window:\n" + window},
                ],
                "max_tokens": JUDGE_MAX_TOKENS,
                "temperature": 0,
                "chat_template_kwargs": {"enable_thinking": False},
            }
        ).encode("utf-8")
        try:
            status, payload, _ = self._chat(alias, body)
        except Exception as error:
            code = getattr(error, "code", None)
            raise ModelJudgeError(code if isinstance(code, str) else "model_unreachable") from None
        if status != 200:
            # llama-server answers 400 when prompt + completion exceed the context;
            # retry once with a much smaller window before giving up.
            if status == 400 and len(window) > 6_000:
                body = json.dumps(
                    {
                        "messages": [
                            {"role": "system", "content": _SYSTEM_PROMPT},
                            {"role": "user", "content": "Questions:\n" + "\n".join(f"- {key}: {q}" for key, q in _QUESTIONS.items()) + "\n\nTranscript window:\n" + render_window(context, max_characters=6_000)},
                        ],
                        "max_tokens": JUDGE_MAX_TOKENS,
                        "temperature": 0,
                        "chat_template_kwargs": {"enable_thinking": False},
                    }
                ).encode("utf-8")
                try:
                    status, payload, _ = self._chat(alias, body)
                except Exception:
                    raise ModelJudgeError("model_unreachable") from None
            if status != 200:
                raise ModelJudgeError("model_error")
        try:
            reply = json.loads(payload.decode("utf-8"))
            text = reply["choices"][0]["message"].get("content") or ""
        except Exception:
            raise ModelJudgeError("model_reply_invalid") from None
        labels = parse_judge_reply(text)
        judged_at = self._clock()
        judgments: list[ModelJudgment] = []
        if labels is not None:
            for key, label in labels.items():
                judgment = ModelJudgment(
                    session_id=session_id,
                    metric_key=key,
                    label=label,
                    model_alias=alias,
                    model_identity=identity[:200],
                    prompt_version=JUDGE_PROMPT_VERSION,
                    window_fingerprint=context.analysis_window_fingerprint,
                    judged_at=judged_at,
                )
                self._repository.upsert(judgment)
                judgments.append(judgment)
        return JudgeOutcome(session_id=session_id, model_alias=alias, judgments=tuple(judgments), raw_valid=labels is not None)

    # ----- sweep -----

    def sweep_status(self) -> JudgeSweepStatus:
        return self._sweep

    def start_sweep(self, session_ids: tuple[str, ...]) -> JudgeSweepStatus:
        active = self._active_model()
        if active is None:
            raise ModelJudgeError("no_active_model")
        alias = active[0]
        with self._sweep_lock:
            if self._sweep.running:
                return self._sweep
            already = {j.session_id for j in self._repository.list(model_alias=alias)}
            pending = tuple(sid for sid in session_ids if sid not in already)
            self._sweep = JudgeSweepStatus(running=bool(pending), model_alias=alias, total=len(pending), done=0, failed=0)
        if not pending:
            return self._sweep
        worker = threading.Thread(target=self._run_sweep, args=(pending,), name="model-judge-sweep", daemon=True)
        worker.start()
        return self._sweep

    def _run_sweep(self, session_ids: tuple[str, ...]) -> None:
        for session_id in session_ids:
            try:
                outcome = self.judge(session_id)
                ok = outcome.raw_valid
                code = None if ok else "model_reply_invalid"
            except ModelJudgeError as error:
                ok, code = False, error.code
                if error.code in {"no_active_model", "model_unreachable", "model_not_active"}:
                    self._sweep = self._sweep.model_copy(update={"running": False, "failed": self._sweep.failed + 1, "last_error_code": code})
                    return
            except Exception:
                ok, code = False, "judge_failed"
            self._sweep = self._sweep.model_copy(
                update={"done": self._sweep.done + 1, "failed": self._sweep.failed + (0 if ok else 1), "last_error_code": code or self._sweep.last_error_code}
            )
        self._sweep = self._sweep.model_copy(update={"running": False})

    # ----- agreement -----

    def interpret(self, session_id: str) -> SessionInterpretation:
        """Ask the active model to read the session's metrics (and redacted window) in plain language."""

        active = self._active_model()
        if active is None:
            raise ModelJudgeError("no_active_model")
        alias, _ = active
        session = self._session_lookup(session_id)
        if session is None:
            raise ModelJudgeError("session_not_found")
        provider = Provider(getattr(session, "provider"))
        rows = self._metrics_lookup(session_id) if self._metrics_lookup is not None else []
        lines: list[str] = []
        for row in rows[:40]:
            key = str(row.get("key"))
            value = row.get("numeric_value")
            text_value = row.get("text_value")
            coverage = row.get("coverage")
            if value is not None:
                lines.append(f"- {key}: {float(value):.2f}" + (f" (coverage {float(coverage):.2f})" if isinstance(coverage, (int, float)) else ""))
            elif text_value is not None:
                lines.append(f"- {key}: {text_value}")
            else:
                lines.append(f"- {key}: unknown")
        try:
            window = render_window(self._window(provider, session_id), max_characters=9_000)
        except ModelJudgeError:
            raise
        except Exception:
            window = "(transcript window unavailable)"
        prompt = (
            "Metric readings for this coding-agent session (unknown means not measurable, never zero):\n"
            + ("\n".join(lines) if lines else "- none recorded")
            + "\n\nRedacted transcript window:\n" + window
        )
        body = json.dumps(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You explain a coding-agent session to the person who ran it, using the metric readings and the redacted window. "
                            "Answer with strict JSON only: {\"summary\": \"one sentence\", \"strengths\": [\"...\"], "
                            "\"improvements\": [\"...\"], \"reframed_prompt\": \"how the first request could have been phrased\"}. "
                            "At most three strengths and three improvements, concrete and kind; treat unknown metrics as unknown; "
                            "never invent events that are not in the window; answer in the person's language."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 700,
                "chat_template_kwargs": {"enable_thinking": False},
            }
        ).encode("utf-8")
        try:
            status, payload, _ = self._chat(alias, body)
        except Exception:
            raise ModelJudgeError("model_unreachable") from None
        if status != 200:
            raise ModelJudgeError("model_error")
        try:
            text = json.loads(payload.decode("utf-8"))["choices"][0]["message"]["content"]
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text).strip(), flags=re.I | re.M)
            data = json.loads(cleaned[cleaned.find("{") : cleaned.rfind("}") + 1])
        except (ValueError, KeyError, IndexError, TypeError, UnicodeDecodeError):
            raise ModelJudgeError("model_reply_invalid") from None
        def _strings(value: object) -> tuple[str, ...]:
            if not isinstance(value, list):
                return ()
            return tuple(str(item).strip()[:400] for item in value if str(item).strip())[:3]
        reframed = data.get("reframed_prompt") if isinstance(data, dict) else None
        summary = data.get("summary") if isinstance(data, dict) else None
        return SessionInterpretation(
            session_id=session_id,
            model_alias=alias,
            strengths=_strings(data.get("strengths") if isinstance(data, dict) else None),
            improvements=_strings(data.get("improvements") if isinstance(data, dict) else None),
            reframed_prompt=str(reframed).strip()[:2_000] if isinstance(reframed, str) and reframed.strip() else None,
            summary=str(summary).strip()[:600] if isinstance(summary, str) and summary.strip() else None,
            metrics_seen=len(lines),
        )

    def judgments_for(self, session_id: str) -> SessionJudgments:
        """Stored judgments for one session (no model call, no content)."""

        if PSEUDONYM_PATTERN.fullmatch(session_id) is None:
            raise ModelJudgeError("session_not_found")
        active = self._active_model()
        rows = tuple(sorted(self._repository.list(session_id=session_id), key=lambda j: (j.model_alias, j.metric_key)))
        return SessionJudgments(
            session_id=session_id,
            active_model_alias=active[0] if active else None,
            questions=dict(_QUESTIONS),
            judgments=rows,
        )

    def judged_model_aliases(self) -> tuple[str, ...]:
        """Every model alias that has stored judgments (for surfaces outside the serving process)."""

        return tuple(sorted({judgment.model_alias for judgment in self._repository.list()}))

    def agreement(self, model_alias: str | None = None) -> JudgeAgreementReport:
        if model_alias is None:
            active = self._active_model()
            alias = active[0] if active else None
        else:
            alias = model_alias
        judgments = self._repository.list(model_alias=alias) if alias else ()
        judged_sessions = {j.session_id for j in judgments}
        ratings = self._ratings.list_ratings()
        metrics: list[MetricAgreement] = []
        for key in CALIBRATION_METRIC_KEYS:
            by_session = {j.session_id: j.label.value for j in judgments if j.metric_key == key}
            pairs = [
                AgreementObservation(first_label=by_session[r.session_id], second_label=r.label.value)
                for r in ratings
                if r.metric_key == key and r.session_id in by_session
            ]
            if not pairs:
                metrics.append(MetricAgreement(metric_key=key, pairs=0, state="insufficient_data", reason="no_overlapping_ratings"))
                continue
            report = model_human_agreement(pairs)
            metrics.append(
                MetricAgreement(
                    metric_key=key,
                    pairs=report.sample_count,
                    agreement_rate=report.observed_agreement.value,
                    cohen_kappa=report.cohen_kappa.value,
                    state=report.state.value if isinstance(report.state, EvaluationState) else str(report.state),
                    reason=report.reason,
                )
            )
        return JudgeAgreementReport(model_alias=alias, judged_sessions=len(judged_sessions), metrics=tuple(metrics))


__all__ = (
    "JUDGE_PROMPT_VERSION",
    "JudgeAgreementReport",
    "JudgeOutcome",
    "JudgeSweepStatus",
    "MODEL_JUDGE_CONTRACT_VERSION",
    "MetricAgreement",
    "ModelJudgeError",
    "ModelJudgeService",
    "ModelJudgment",
    "SessionInterpretation",
    "SessionJudgments",
    "ModelJudgmentRepository",
    "parse_judge_reply",
    "render_window",
)
