"""Export the dashboard contract at build time; runtime docs stay disabled."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _REPOSITORY_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from prompt_enhancer.api import create_app
from prompt_enhancer.application.analysis import (
    ModelExperimentDevice,
    ModelLinkAnnotationLabel,
    SessionTextAnalysisOutcome,
    TaskAnalysisOutcome,
    TextAnalysisPresetId,
)
from prompt_enhancer.application.discovery import TaskDecisionCommand, TaskReviewResult
from prompt_enhancer.application.local_sources import CodexLocalSourceStatus
from prompt_enhancer.application.persistence import AnalysisRunStatus
from prompt_enhancer.config import AppSettings
from prompt_enhancer.domain import Provider
from prompt_enhancer.ingestion import IngestionReport
from prompt_enhancer.infrastructure.text_models.jobs import LocalTextModelEvaluationService


class _SchemaStore:
    """Content-free stand-in used only while FastAPI builds route schemas."""

    def initialize(self) -> None:
        return None

    def list_metric_definitions(self) -> list[dict[str, object]]:
        return []

    def list_sessions(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        provider: Provider | None = None,
    ) -> list[dict[str, object]]:
        return []

    def get_session_metrics(self, session_id: str) -> list[dict[str, object]]:
        return []


class _SchemaReviewService:
    def apply(
        self,
        command: TaskDecisionCommand,
        *,
        idempotency_key: str,
    ) -> TaskReviewResult:
        raise RuntimeError("schema-only service cannot execute commands")


class _SchemaAnalysisService:
    def run(
        self,
        task_id: str,
        task_revision: int,
        *,
        idempotency_key: str,
    ) -> TaskAnalysisOutcome:
        return TaskAnalysisOutcome(
            run_id="0" * 64,
            status=AnalysisRunStatus.COMPLETED,
            result_count=0,
            applied=False,
        )


class _SchemaSessionTextAnalysisService:
    def run_preset(
        self,
        *,
        provider: Provider,
        session_id: str,
        preset_id: TextAnalysisPresetId,
        confirmation: str,
        idempotency_key: str,
    ) -> SessionTextAnalysisOutcome:
        raise RuntimeError("schema-only service cannot access session text")


class _SchemaModelLinkExperimentService:
    def run(
        self,
        *,
        provider: Provider,
        session_id: str,
        confirmation: str,
        device: ModelExperimentDevice,
        idempotency_key: str,
    ) -> object:
        raise RuntimeError("schema-only service cannot access session text")

    def latest(self, session_id: str) -> object:
        raise RuntimeError("schema-only service cannot access local experiments")

    def annotate(
        self,
        *,
        run_id: str,
        link_id: str,
        label: ModelLinkAnnotationLabel,
        expected_revision: int,
    ) -> object:
        raise RuntimeError("schema-only service cannot change annotations")


class _SchemaProjectQualityAggregationService:
    """Non-executing stand-in that only enables the project aggregate schema."""

    def aggregate(self, selection: object) -> object:
        raise RuntimeError("schema-only service cannot resolve indexed projects")


class _SchemaProviderCompatibilityCatalog:
    """Non-executing stand-in that exposes compatibility route signatures."""

    def descriptor(self, provider: str, surface: object) -> object:
        raise RuntimeError("schema-only service cannot inspect providers")

    def get_cached(self, provider: str, surface: object) -> object:
        raise RuntimeError("schema-only service cannot inspect providers")

    def refresh(self, provider: str, surface: object) -> object:
        raise RuntimeError("schema-only service cannot inspect providers")


class _SchemaCodexSourceService:
    """Non-executing stand-in that exposes only local-source route signatures."""

    def status(self) -> CodexLocalSourceStatus:
        raise RuntimeError("schema-only service cannot access local sources")

    def grant_local_history(self) -> CodexLocalSourceStatus:
        raise RuntimeError("schema-only service cannot change consent")

    def revoke_local_history(self) -> CodexLocalSourceStatus:
        raise RuntimeError("schema-only service cannot change consent")

    def index(self, *, max_sessions: int) -> IngestionReport:
        raise RuntimeError("schema-only service cannot access local sources")

    def analyze(
        self,
        *,
        project_ids: frozenset[str],
        session_ids: frozenset[str],
        max_sessions: int,
    ) -> IngestionReport:
        raise RuntimeError("schema-only service cannot access local sources")


class _SchemaManualDisplayLabelService:
    """Non-executing stand-in for local override route signatures."""

    pass

def build_openapi_schema() -> dict[str, Any]:
    """Build the complete UI contract without creating local state or secrets."""

    app = create_app(
        settings=AppSettings(home=Path("example-state")),
        database=_SchemaStore(),
        api_token="example_schema_token_do_not_use_123456789",
        task_review_service=_SchemaReviewService(),
        task_analysis_service=_SchemaAnalysisService(),
        session_text_analysis_service=_SchemaSessionTextAnalysisService(),
        session_model_link_experiment_service=_SchemaModelLinkExperimentService(),  # type: ignore[arg-type]
        project_quality_aggregation_service=_SchemaProjectQualityAggregationService(),  # type: ignore[arg-type]
        provider_compatibility_catalog=_SchemaProviderCompatibilityCatalog(),  # type: ignore[arg-type]
        codex_source_service=_SchemaCodexSourceService(),
        display_label_service=_SchemaManualDisplayLabelService(),
        model_evaluation_service=LocalTextModelEvaluationService(),
    )
    return app.openapi()


def export_openapi(output: Path) -> None:
    """Write one deterministic UTF-8 JSON artifact for frontend code generation."""

    output = output.absolute()
    if output.suffix.casefold() != ".json":
        raise ValueError("OpenAPI output must be a JSON file")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(build_openapi_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/openapi.json"),
        help="JSON artifact destination (default: docs/openapi.json)",
    )
    arguments = parser.parse_args()
    export_openapi(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
