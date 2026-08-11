"""Read-only, content-free research catalog for the dashboard Model Lab."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import Field

from ...application.analysis.method_research import (
    CATALOG_KEY,
    CATALOG_REVIEWED_ON,
    CATALOG_VERSION,
    METHODS,
    METRIC_ROADMAP,
    MODEL_CANDIDATES,
    SOURCES,
    AnalysisMethod,
    MetricRoadmapItem,
    ModelBenchmark,
    ModelCandidate,
    ResearchSource,
)
from .dto import HttpDto
from ...infrastructure.text_models.jobs import (
    CandidateEvaluationSummary,
    LocalTextModelEvaluationService,
    ModelEvaluationBusyError,
    ModelEvaluationJob,
    ModelEvaluationNotFoundError,
    ModelEvaluationRequest,
    ModelRuntimeInventory,
)


class ResearchSourceDto(HttpDto):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    title: str = Field(min_length=1, max_length=160)
    url: str = Field(pattern=r"^https://[^\s]+$", max_length=256)
    kind: Literal["paper", "model_card"]


class AnalysisMethodDto(HttpDto):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=96)
    family: Literal[
        "extraction", "conversation", "linking", "semantic_inference", "workflow", "evaluation"
    ]
    approach: Literal[
        "rules",
        "classifier",
        "hybrid",
        "statistical",
        "embedding",
        "reranker",
        "nli",
        "graph_rules",
        "graph",
        "process_mining",
        "generative_model",
        "calibration",
    ]
    maturity: Literal[
        "product_baseline", "evaluated_exploratory", "research_candidate", "failed_gate"
    ]
    privacy_tier: Literal["metadata", "redacted_content"]
    purpose: str = Field(min_length=1, max_length=320)
    produces: tuple[str, ...] = Field(min_length=1, max_length=8)
    candidate_model_keys: tuple[str, ...] = Field(max_length=8)
    source_keys: tuple[str, ...] = Field(max_length=8)
    limitations: tuple[str, ...] = Field(min_length=1, max_length=8)


class ModelBenchmarkDto(HttpDto):
    benchmark_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    case_count: int = Field(ge=1, le=100_000)
    primary_metric: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    primary_value: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    secondary_metric: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$"
    )
    secondary_value: float | None = Field(
        default=None, ge=0.0, le=1.0, allow_inf_nan=False
    )
    critical_metric: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$"
    )
    critical_value: float | None = Field(
        default=None, ge=0.0, le=1.0, allow_inf_nan=False
    )


class ModelCandidateDto(HttpDto):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    display_name: str = Field(min_length=1, max_length=96)
    repository_id: str = Field(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
    task: str = Field(min_length=1, max_length=80)
    license_spdx: Literal["MIT", "Apache-2.0"]
    revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")
    parameter_scale: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+)?[MB]$", max_length=16)
    language_scope: str = Field(min_length=1, max_length=96)
    status: Literal[
        "evaluated_exploratory", "research_shortlist", "rejected_screen"
    ]
    product_enabled: Literal[False]
    trust_remote_code: Literal[False]
    decision: str = Field(min_length=1, max_length=360)
    benchmark: ModelBenchmarkDto | None
    source_keys: tuple[str, ...] = Field(min_length=1, max_length=8)


class MetricRoadmapItemDto(HttpDto):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=96)
    profile: Literal["prompt", "collaboration", "logic", "agent_answer", "outcome"]
    question: str = Field(min_length=1, max_length=240)
    direction: Literal["higher_is_better", "lower_is_better", "contextual"]
    state: Literal["baseline_available", "research", "needs_objective_evidence"]
    evidence: str = Field(min_length=1, max_length=280)
    method_keys: tuple[str, ...] = Field(min_length=1, max_length=8)
    caution: str = Field(min_length=1, max_length=240)


class TextAnalysisResearchCatalogDto(HttpDto):
    catalog_key: Literal["text-analysis-methods"]
    catalog_version: int = Field(ge=1)
    reviewed_on: date
    privacy_mode: Literal["local_only_redacted_content"]
    summary_policy: Literal["multidimensional_profile_no_universal_score"]
    catalog_read_starts_session_access: Literal[False]
    catalog_read_downloads_models: Literal[False]
    methods: tuple[AnalysisMethodDto, ...] = Field(min_length=1, max_length=64)
    model_candidates: tuple[ModelCandidateDto, ...] = Field(
        min_length=1, max_length=32
    )
    metric_roadmap: tuple[MetricRoadmapItemDto, ...] = Field(
        min_length=10, max_length=64
    )
    sources: tuple[ResearchSourceDto, ...] = Field(min_length=1, max_length=64)


class ModelRuntimeInventoryDto(HttpDto):
    preferred_device: Literal["cpu", "cuda", "mps"]
    cuda_available: bool
    mps_available: bool
    cpu_available: Literal[True]
    cuda_memory_mb: int | None = Field(default=None, ge=1, le=1_048_576)
    one_model_at_a_time: Literal[True]
    subprocess_isolation: Literal[True]
    raw_session_data_accepted: Literal[False]


class ModelEvaluationRequestDto(HttpDto):
    candidate: Literal[
        "all",
        "session-link",
        "e5",
        "nli",
        "bge-m3",
        "bge-reranker",
        "qwen-embedding",
        "qwen-reranker",
        "qwen-rubric",
    ] = "all"
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    mode: Literal["smoke", "full"] = "smoke"
    allow_download: bool = False


class CandidateEvaluationSummaryDto(HttpDto):
    key: Literal[
        "multilingual_e5_small",
        "mdeberta_xnli",
        "bge_m3",
        "bge_reranker_v2_m3",
        "qwen3_embedding_06b",
        "qwen3_reranker_06b",
        "qwen3_4b_rubric",
    ]
    status: Literal["evaluated", "not_completed", "blocked_before_download"]
    error_code: Literal[
        "unsafe_pickle_only",
        "model_cache_missing_or_invalid",
        "batch_size_outside_manifest_bound",
        "cuda_unavailable",
        "mps_unavailable",
        "resource_exhausted",
        "evaluation_failed",
    ] | None = None
    primary_metric: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    primary_value: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    secondary_metric: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    secondary_value: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    critical_metric: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    critical_value: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    inference_latency_ms: float | None = Field(
        default=None, ge=0, le=86_400_000, allow_inf_nan=False
    )
    peak_accelerator_memory_mb: float | None = Field(
        default=None, ge=0, le=1_048_576, allow_inf_nan=False
    )


class ModelEvaluationJobDto(HttpDto):
    job_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    status: Literal["queued", "running", "completed", "failed"]
    candidate: ModelEvaluationRequestDto
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    resolved_device: Literal["cpu", "cuda", "mps"] | None
    error_code: Literal[
        "candidate_evaluation_incomplete", "model_evaluation_failed"
    ] | None
    outcomes: tuple[CandidateEvaluationSummaryDto, ...] = Field(max_length=7)


def _source(value: ResearchSource) -> ResearchSourceDto:
    return ResearchSourceDto(
        key=value.key,
        title=value.title,
        url=value.url,
        kind=value.kind,
    )


def _method(value: AnalysisMethod) -> AnalysisMethodDto:
    return AnalysisMethodDto(
        key=value.key,
        name=value.name,
        family=value.family,
        approach=value.approach,
        maturity=value.maturity.value,
        privacy_tier=value.privacy_tier,
        purpose=value.purpose,
        produces=value.produces,
        candidate_model_keys=value.candidate_model_keys,
        source_keys=value.source_keys,
        limitations=value.limitations,
    )


def _benchmark(value: ModelBenchmark | None) -> ModelBenchmarkDto | None:
    if value is None:
        return None
    return ModelBenchmarkDto(
        benchmark_key=value.benchmark_key,
        case_count=value.case_count,
        primary_metric=value.primary_metric,
        primary_value=value.primary_value,
        secondary_metric=value.secondary_metric,
        secondary_value=value.secondary_value,
        critical_metric=value.critical_metric,
        critical_value=value.critical_value,
    )


def _candidate(value: ModelCandidate) -> ModelCandidateDto:
    return ModelCandidateDto(
        key=value.key,
        display_name=value.display_name,
        repository_id=value.repository_id,
        task=value.task,
        license_spdx=value.license_spdx,
        revision=value.revision,
        parameter_scale=value.parameter_scale,
        language_scope=value.language_scope,
        status=value.status.value,
        product_enabled=False,
        trust_remote_code=False,
        decision=value.decision,
        benchmark=_benchmark(value.benchmark),
        source_keys=value.source_keys,
    )


def _metric(value: MetricRoadmapItem) -> MetricRoadmapItemDto:
    return MetricRoadmapItemDto(
        key=value.key,
        name=value.name,
        profile=value.profile,
        question=value.question,
        direction=value.direction.value,
        state=value.state.value,
        evidence=value.evidence,
        method_keys=value.method_keys,
        caution=value.caution,
    )


def text_analysis_research_catalog() -> TextAnalysisResearchCatalogDto:
    return TextAnalysisResearchCatalogDto(
        catalog_key=CATALOG_KEY,
        catalog_version=CATALOG_VERSION,
        reviewed_on=date.fromisoformat(CATALOG_REVIEWED_ON),
        privacy_mode="local_only_redacted_content",
        summary_policy="multidimensional_profile_no_universal_score",
        catalog_read_starts_session_access=False,
        catalog_read_downloads_models=False,
        methods=tuple(_method(value) for value in METHODS),
        model_candidates=tuple(_candidate(value) for value in MODEL_CANDIDATES),
        metric_roadmap=tuple(_metric(value) for value in METRIC_ROADMAP),
        sources=tuple(_source(value) for value in SOURCES),
    )


def _runtime_dto(value: ModelRuntimeInventory) -> ModelRuntimeInventoryDto:
    return ModelRuntimeInventoryDto(
        preferred_device=value.preferred_device,
        cuda_available=value.cuda_available,
        mps_available=value.mps_available,
        cpu_available=value.cpu_available,
        cuda_memory_mb=value.cuda_memory_mb,
        one_model_at_a_time=value.one_model_at_a_time,
        subprocess_isolation=value.subprocess_isolation,
        raw_session_data_accepted=value.raw_session_data_accepted,
    )


def _outcome_dto(value: CandidateEvaluationSummary) -> CandidateEvaluationSummaryDto:
    return CandidateEvaluationSummaryDto(
        key=value.key,
        status=value.status,
        error_code=value.error_code,
        primary_metric=value.primary_metric,
        primary_value=value.primary_value,
        secondary_metric=value.secondary_metric,
        secondary_value=value.secondary_value,
        critical_metric=value.critical_metric,
        critical_value=value.critical_value,
        inference_latency_ms=value.inference_latency_ms,
        peak_accelerator_memory_mb=value.peak_accelerator_memory_mb,
    )


def _job_dto(value: ModelEvaluationJob) -> ModelEvaluationJobDto:
    request = value.request
    return ModelEvaluationJobDto(
        job_id=value.job_id,
        status=value.status,
        candidate=ModelEvaluationRequestDto(
            candidate=request.candidate,
            device=request.device,
            mode=request.mode,
            allow_download=request.allow_download,
        ),
        created_at=value.created_at,
        started_at=value.started_at,
        completed_at=value.completed_at,
        resolved_device=value.resolved_device,
        error_code=value.error_code,
        outcomes=tuple(_outcome_dto(item) for item in value.outcomes),
    )


def create_research_router(
    require_local_auth: Callable[..., None],
    model_evaluation_service: LocalTextModelEvaluationService | None = None,
) -> APIRouter:
    router = APIRouter(
        prefix="/v1/research",
        tags=["research"],
        dependencies=[Depends(require_local_auth)],
    )

    @router.get(
        "/text-analysis-methods",
        response_model=TextAnalysisResearchCatalogDto,
    )
    def get_text_analysis_methods() -> TextAnalysisResearchCatalogDto:
        return text_analysis_research_catalog()

    if model_evaluation_service is not None:

        @router.get(
            "/text-model-runtime",
            response_model=ModelRuntimeInventoryDto,
        )
        def get_text_model_runtime() -> ModelRuntimeInventoryDto:
            return _runtime_dto(model_evaluation_service.inventory())

        @router.post(
            "/text-model-evaluations",
            response_model=ModelEvaluationJobDto,
            status_code=202,
        )
        def start_text_model_evaluation(
            body: ModelEvaluationRequestDto,
        ) -> ModelEvaluationJobDto:
            try:
                job = model_evaluation_service.start(
                    ModelEvaluationRequest(
                        candidate=body.candidate,
                        device=body.device,
                        mode=body.mode,
                        allow_download=body.allow_download,
                    )
                )
            except ModelEvaluationBusyError:
                raise HTTPException(
                    status_code=409,
                    detail="a local model evaluation is already running",
                ) from None
            return _job_dto(job)

        @router.get(
            "/text-model-evaluations/{job_id}",
            response_model=ModelEvaluationJobDto,
        )
        def get_text_model_evaluation(
            job_id: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")],
        ) -> ModelEvaluationJobDto:
            try:
                return _job_dto(model_evaluation_service.get(job_id))
            except ModelEvaluationNotFoundError:
                raise HTTPException(
                    status_code=404,
                    detail="model evaluation not found",
                ) from None

    return router
