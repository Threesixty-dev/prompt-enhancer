"""Versioned coding-request cues for the independent Bench evaluator."""
from dataclasses import replace
import re

from ..application.analysis.coaching_baselines import (
    COACHING_METRIC_PACK_KEY,
    COACHING_METRIC_PACK_VERSION,
    COACHING_METRIC_REGISTRY,
    COACHING_METRIC_RUBRIC_VERSION,
    CoachingTextFeatureExtractor,
    _VAGUE,
)
from ..application.analysis.text_baselines import TextMetricEngine
from ..application.analysis.text_contracts import TextMessageKind


_REQUESTED_ARTIFACT = re.compile(
    r"^\s*(?:(?:please\s+)?(?:return|provide|deliver|include|write|add|create|generate|submit)\b"
    r"|(?:deliverables?|output)\s*:)"
    r"[^.!?\n]*\b(?:patch(?:es)?|diffs?|(?:unit\s+)?tests?|test\s+(?:suite|files?|cases?))\b",
    re.IGNORECASE,
)
_ARTIFACT_FORMAT = re.compile(r"\b(?:patch(?:es)?|diffs?|unit\s+tests?|test\s+suite)\b", re.IGNORECASE)
_PROHIBITION = re.compile(
    r"\b(?:do not|don't|must not|never)\s+"
    r"(?:add|change|remove|modify|mutate|write|read|send|use|call|access|delete|overwrite|"
    r"touch|introduce|alter)\b\s+\S",
    re.IGNORECASE,
)


class PromptCueFeatureExtractor(CoachingTextFeatureExtractor):
    algorithm_id = "rules.en-pl.prompt-cues"
    algorithm_version = "1"

    def extract(self, context):
        features = super().extract(context)
        requests = tuple(c for c in features.user_clauses
                         if c.kind in {TextMessageKind.REQUEST, TextMessageKind.FEEDBACK})
        constraints = tuple(c for c in requests if c in features.constraint_clauses or _PROHIBITION.search(c.text))
        deliverables = tuple(c for c in requests if c in features.deliverable_clauses or _REQUESTED_ARTIFACT.search(c.text))
        return replace(
            features,
            constraint_clauses=constraints,
            precise_constraints=tuple(c for c in constraints if c in features.precise_constraints
                or (_PROHIBITION.search(c.text) and not _VAGUE.search(c.text))),
            deliverable_clauses=deliverables,
            detailed_deliverables=tuple(c for c in deliverables if c in features.detailed_deliverables
                or (_REQUESTED_ARTIFACT.search(c.text) and _ARTIFACT_FORMAT.search(c.text))),
        )


# The v1 engine remains available for pinned workflows and session analytics.
PROMPT_CUE_METRIC_ENGINE = TextMetricEngine(
    registry=COACHING_METRIC_REGISTRY,
    extractor=PromptCueFeatureExtractor(),
    pack_key=COACHING_METRIC_PACK_KEY,
    pack_version=COACHING_METRIC_PACK_VERSION,
    engine_version="prompt-cues-en-pl-1",
    rubric_version=COACHING_METRIC_RUBRIC_VERSION,
)
