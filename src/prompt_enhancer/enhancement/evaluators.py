"""Typed evaluation adapters sharing the application's deterministic evaluator."""
from __future__ import annotations

import hashlib
import math
from typing import Any

from ..application.prompt_evaluation import DeterministicPromptEvaluator
from ..application.analysis.coaching_baselines import DEFAULT_COACHING_METRIC_ENGINE
from ..infrastructure.language import DeterministicEnglishPolishDetector
from ..infrastructure.redaction import DeterministicLocalRedactor
from ..infrastructure.text_models.benchmark import NliCase, RetrievalCase, RetrievalCandidate, RubricCase
from ..infrastructure.text_models.manifests import ModelManifest, TextModelTask
from .contracts import Evaluation, Evaluator, Metric, Provenance, Subject
from .ports import CoreError


class DeterministicEvaluation:
    kind = "deterministic"

    def __init__(self, *, version="v1"):
        from .prompt_cues import PROMPT_CUE_METRIC_ENGINE
        engines = {"v1": DEFAULT_COACHING_METRIC_ENGINE, "v2": PROMPT_CUE_METRIC_ENGINE}
        if version not in engines:
            raise ValueError("unsupported_prompt_evaluator_version")
        engine = engines[version]
        redactor = DeterministicLocalRedactor()
        self.provenance = Provenance(
            provider="deterministic", adapter_version=f"prompt-evaluation.{version}",
            metric_version=engine.engine_version, rubric_version=engine.rubric_version,
            redactor_version=redactor.version,
        )
        self.evaluator = DeterministicPromptEvaluator(
            pseudonymize=lambda scope, text: hashlib.sha256(f"{scope}:{text}".encode()).hexdigest(),
            redactor=redactor, language_detector=DeterministicEnglishPolishDetector(), engine=engine,
        )

    def validate(self, spec: Evaluator) -> None:
        if spec.kind != self.kind:
            raise CoreError("evaluator_kind_mismatch")
        if spec.generation is not None:
            raise CoreError("local_evaluator_generation_parameter_unsupported")

    async def evaluate(self, subject: Subject, spec: Evaluator) -> Evaluation:
        self.validate(spec)
        readings = self.evaluator.evaluate("0" * 64, subject.text, subject.context)
        return Evaluation(evaluator_id=spec.evaluator_id, kind=spec.kind,
            provenance=self.provenance, metrics=tuple(Metric(
                key=r.key, state=r.state, value=r.value if r.state == "known" else None,
                reason=r.explanation_code,
            ) for r in readings))


class TypedTextEvaluation:
    """Dispatch to a reviewed, already-loaded backend, never a generic chat API.

    Production composition runs this adapter inside an owned bounded process.
    Labels stay categorical; embedding similarity alone carries a numeric value.
    """

    def __init__(self, kind: str, manifest: ModelManifest, backend: Any):
        valid = {
            "classifier": {TextModelTask.SCOPED_NLI, TextModelTask.BINARY_NLI},
            "embedding": {TextModelTask.REQUIREMENT_ACTION_RETRIEVAL},
            "rubric": {TextModelTask.STRUCTURED_RUBRIC},
        }
        if kind not in valid or manifest.task not in valid[kind]:
            raise CoreError("evaluator_manifest_mismatch")
        self.kind = kind
        self.backend = backend
        self.provenance = Provenance(
            provider="local_transformers", adapter_version=backend.key,
            model=manifest.repository_id, model_revision=manifest.revision,
            model_license=manifest.license_spdx, tokenizer_revision=manifest.tokenizer_revision,
            metric_version="typed-text.v1",
            rubric_version="structured-rubric.v1" if kind == "rubric" else None,
            identity_source="verified_manifest",
        )

    def validate(self, spec: Evaluator) -> None:
        if spec.kind != self.kind:
            raise CoreError("evaluator_kind_mismatch")
        if spec.generation is not None:
            raise CoreError("local_evaluator_generation_parameter_unsupported")

    async def evaluate(self, subject: Subject, spec: Evaluator) -> Evaluation:
        self.validate(spec)
        # These typed models evaluate only the explicit subject. Context is not
        # concatenated silently into a different, truncated model input.
        key = {"classifier": "nli.label", "embedding": "embedding.similarity", "rubric": "rubric.label"}[self.kind]
        try:
            if self.kind == "classifier":
                predictions = self.backend.predict((NliCase("en", subject.text, spec.target, "neutral", "explicit"),))
                if len(predictions) != 1 or predictions[0] not in {"entailment", "neutral", "contradiction"}:
                    raise ValueError("invalid_prediction")
                metric = Metric(key=key, state="known", label=predictions[0], reason="model_interpretation")
            elif self.kind == "embedding":
                rows = self.backend.score((RetrievalCase("en", spec.target, "candidate", (RetrievalCandidate("candidate", subject.text),)),))
                if len(rows) != 1 or len(rows[0]) != 1 or not math.isfinite(rows[0][0]):
                    raise ValueError("invalid_prediction")
                metric = Metric(key=key, state="known", value=rows[0][0], reason="model_similarity")
            else:
                predictions = self.backend.predict((RubricCase("candidate", "en", spec.rubric, subject.text, "abstain"),))
                if len(predictions) != 1:
                    raise ValueError("invalid_prediction")
                prediction = predictions[0]
                if not prediction.json_valid or prediction.label not in {"present", "absent", "abstain"}:
                    metric = Metric(key=key, state="unknown", reason="rubric_reply_invalid")
                elif prediction.label == "abstain":
                    metric = Metric(key=key, state="abstained", reason="rubric_abstained")
                else:
                    metric = Metric(key=key, state="known", label=prediction.label, reason="model_interpretation")
        except Exception:
            metric = Metric(key=key, state="execution_error", reason="evaluator_failed")
        return Evaluation(evaluator_id=spec.evaluator_id, kind=spec.kind,
                          provenance=self.provenance, metrics=(metric,))
