"""Independent consumer and typed evaluator ports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .contracts import Evaluation, Evaluator, ExecuteRequest, GenerationContext, Provenance, Subject


class CoreError(Exception):
    def __init__(self, code: str, *, uncertain: bool = False, operation_id: str | None = None):
        self.code = code
        self.uncertain = uncertain
        self.operation_id = operation_id
        super().__init__(code)


@dataclass(frozen=True)
class Candidate:
    text: str
    provenance: Provenance


class Consumer(Protocol):
    provider: str
    provenance: Provenance

    def validate(self, request: ExecuteRequest) -> None: ...
    async def generate(self, request: ExecuteRequest, context: GenerationContext) -> Candidate: ...


class EvaluationProvider(Protocol):
    kind: str
    provenance: Provenance

    def validate(self, spec: Evaluator) -> None: ...
    async def evaluate(self, subject: Subject, spec: Evaluator) -> Evaluation: ...
