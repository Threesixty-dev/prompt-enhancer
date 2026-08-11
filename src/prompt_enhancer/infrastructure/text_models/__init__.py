"""Offline-first text-model evaluation and explicit local experiment adapters.

The model evaluator remains separate from product metrics. The selected-session
adapter is an explicit local experiment whose outputs require human review.
"""

from .manifests import (
    BGE_M3_BLOCKED,
    BGE_RERANKER_V2_M3,
    E5_MULTILINGUAL_SMALL,
    MDEBERTA_XNLI,
    QWEN3_4B_RUBRIC,
    QWEN3_EMBEDDING_06B,
    QWEN3_RERANKER_06B,
    BLOCKED_TEXT_MODEL_MANIFESTS,
    TEXT_MODEL_MANIFESTS,
    BlockedModelManifest,
    ModelManifest,
    TextModelTask,
)
from .session_links import SubprocessSessionModelLinkRunner

__all__ = [
    "BGE_M3_BLOCKED",
    "BGE_RERANKER_V2_M3",
    "E5_MULTILINGUAL_SMALL",
    "MDEBERTA_XNLI",
    "QWEN3_4B_RUBRIC",
    "QWEN3_EMBEDDING_06B",
    "QWEN3_RERANKER_06B",
    "BLOCKED_TEXT_MODEL_MANIFESTS",
    "TEXT_MODEL_MANIFESTS",
    "BlockedModelManifest",
    "ModelManifest",
    "TextModelTask",
    "SubprocessSessionModelLinkRunner",
]
