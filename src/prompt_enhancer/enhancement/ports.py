"""Independent consumer and typed evaluator ports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .contracts import Evaluation, Evaluator, ExecuteRequest, GenerationContext, ModelCall, Provenance, Subject
from ..core.errors import CoreError


# Only these package-owned diagnostics may cross the worker boundary.
WORKER_ERROR_CODES = frozenset({
    "generation_context_mismatch", "consumer_failed", "evaluator_failed",
    "consumer_reply_invalid", "candidate_invalid", "openhands_sdk_version_unsupported",
    "consumer_workspace_unavailable", "remote_execution_unconfirmed",
    "remote_cleanup_unconfirmed", "worker_input_too_large",
    "evaluator_model_mismatch",
})


@dataclass(frozen=True)
class Candidate:
    text: str
    provenance: Provenance


class Consumer(Protocol):
    provider: str
    provenance: Provenance

    def validate(self, request: ExecuteRequest) -> None: ...
    async def generate(self, request: ExecuteRequest, context: GenerationContext) -> Candidate: ...


class ModelProvider(Protocol):
    provider: str
    provenance: Provenance

    def validate_call(self, call: ModelCall) -> None: ...
    async def complete(self, call: ModelCall) -> Candidate: ...


class EvaluationProvider(Protocol):
    kind: str
    provenance: Provenance

    def validate(self, spec: Evaluator) -> None: ...
    async def evaluate(self, subject: Subject, spec: Evaluator) -> Evaluation: ...
