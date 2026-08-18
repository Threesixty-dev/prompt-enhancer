"""Authenticated private API for measured metrics and local predictive ranges."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response
from pydantic import Field

from ...application.analysis.model_ensemble import (
    MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION,
    ModelExpertRole,
)
from ...application.analysis.metric_evidence_readiness_v2 import (
    MetricEvidenceReadinessProjectionV2,
    project_metric_evidence_readiness_v2,
)
from ...application.analysis.metric_publication_v2 import MetricPublicationV2
from ...application.analysis.session_model_ensemble import (
    LEGACY_MODEL_ENSEMBLE_CONFIRMATION,
    MODEL_ENSEMBLE_CONFIRMATION,
    ModelEnsembleCompatibilityError,
    ModelEnsembleConfirmationError,
    ModelEnsembleConsentError,
    ModelEnsembleExecutionError,
    ModelEnsembleInputError,
    ModelEnsemblePersistenceError,
    ModelEnsembleSelectionError,
    ModelEnsembleSourceError,
    SessionModelEnsembleOutcome,
    SessionModelEnsembleRunRecord,
)
from ...application.analysis.text_source import TextSourceFailureReason
from ...application.analysis.text_contracts import MAX_ELIGIBLE_MESSAGES
from ...application.analysis.probabilistic_metrics import (
    PROBABILISTIC_DENSITY_BIN_COUNT,
    PROBABILISTIC_METRIC_PROJECTION_VERSION,
    PredictiveMetricState,
    PredictiveMetricTarget,
)
from ...domain import PSEUDONYM_PATTERN, SAFE_VERSION_PATTERN, Provider, StrictModel


_PRIVATE_HEADERS = {"Cache-Control": "no-store, private", "Pragma": "no-cache"}


class ModelEnsembleCommand(Protocol):
    def run(
        self,
        *,
        provider: Provider,
        session_id: str,
        confirmation: str,
        idempotency_key: str,
    ) -> SessionModelEnsembleOutcome: ...

    def latest(self, session_id: str) -> SessionModelEnsembleRunRecord | None: ...

    def get(self, run_id: str) -> SessionModelEnsembleRunRecord | None: ...


class ModelEnsembleRequest(StrictModel):
    confirmation: Literal[
        MODEL_ENSEMBLE_CONFIRMATION,
        LEGACY_MODEL_ENSEMBLE_CONFIRMATION,
    ]


class ModelEnsembleChunkDto(StrictModel):
    ordinal: int = Field(ge=0, le=7)
    source_message_count: int = Field(ge=1, le=100)
    fragment_count: int = Field(ge=1, le=128)
    character_count: int = Field(ge=1, le=100_000)


class ModelEnsembleExpertDto(StrictModel):
    ordinal: int = Field(ge=0, le=9)
    model_key: str
    role: ModelExpertRole
    repository_id: str
    revision: str
    license_spdx: Literal["MIT", "Apache-2.0"]
    contributes_to_decision: bool
    status: Literal["completed", "unavailable", "resource_exhausted", "failed"]
    error_code: str | None
    device: Literal["cpu", "cuda", "mps"] | None
    inference_latency_ms: float | None = Field(default=None, ge=0)
    peak_accelerator_memory_mb: float | None = Field(default=None, ge=0)
    process_rss_mb: float | None = Field(default=None, ge=0)
    unloaded_after_stage: Literal[True]


class ModelEnsembleVoteDto(StrictModel):
    chunk_ordinal: int = Field(ge=0, le=7)
    metric_key: str
    model_key: str
    role: Literal["scope_nli", "structured_rubric"]
    state: Literal["present", "absent", "abstain", "unsupported", "failed"]
    raw_score: float | None = Field(default=None, ge=0, le=1)
    evidence_fragment_count: int = Field(ge=0, le=8)
    reason_code: str


class ModelEnsembleChunkMetricDto(StrictModel):
    chunk_ordinal: int = Field(ge=0, le=7)
    metric_key: str
    value_state: Literal[
        "known", "unknown", "not_applicable", "abstained", "execution_error"
    ]
    numerator: int | None = Field(default=None, ge=0, le=1)
    denominator: int | None = Field(default=None, ge=1, le=1)
    rubric_vote: Literal["present", "absent", "abstain", "unsupported", "failed"]
    contributing_nli_votes: int = Field(ge=0, le=2)
    diagnostic_nli_votes: int = Field(ge=0, le=1)
    reason_code: str


class ModelEnsembleMetricDto(StrictModel):
    metric_key: str
    value_state: Literal[
        "known", "unknown", "not_applicable", "abstained", "execution_error"
    ]
    numerator: int | None = Field(default=None, ge=0)
    denominator: int | None = Field(default=None, ge=1, le=8)
    numeric_value: float | None = Field(default=None, ge=0, le=1)
    known_chunk_count: int = Field(
        ge=0,
        le=8,
        description="Known eligible observations; legacy field name retained for compatibility.",
    )
    abstained_chunk_count: int = Field(
        ge=0,
        le=8,
        description="Abstained eligible observations; structural ownership cells are excluded.",
    )
    unsupported_chunk_count: int = Field(
        ge=0,
        le=8,
        description="Unknown or unsupported eligible observations; structural cells are excluded.",
    )
    failed_chunk_count: int = Field(
        ge=0,
        le=8,
        description="Execution-failed eligible observations; structural cells are excluded.",
    )
    total_chunk_count: int = Field(
        ge=1,
        le=8,
        description="Eligible observation count; may be smaller than the physical chunk count.",
    )
    explanation_code: str
    calibration_state: Literal["not_assessed"]
    product_metric_eligible: Literal[False]


class ModelEnsembleTypedMetricDto(StrictModel):
    metric_key: str
    metric_version: int = Field(ge=1, le=1_000_000)
    value_state: Literal[
        "known", "unknown", "not_applicable", "abstained", "execution_error"
    ]
    numerator: int | None = Field(default=None, ge=0, le=1_000_000)
    denominator: int | None = Field(default=None, ge=1, le=1_000_000)
    numeric_value: float | None = Field(default=None, ge=0, le=1)
    observed_message_count: int = Field(ge=0, le=100)
    eligible_message_count: int = Field(ge=0, le=MAX_ELIGIBLE_MESSAGES)
    coverage: float = Field(ge=0, le=1)
    explanation_code: str
    error_code: str | None
    projection_source: Literal["deterministic_typed_contract"]
    metric_schema_version: int = Field(ge=1, le=1_000_000)
    engine_version: str
    algorithm_id: str
    algorithm_version: str
    rubric_version: str
    calibration_state: Literal["not_assessed"]
    product_metric_eligible: Literal[False]


class ModelPredictiveMetricDto(StrictModel):
    metric_key: str
    target: PredictiveMetricTarget
    state: PredictiveMetricState
    mean: float | None = Field(default=None, ge=0, le=1)
    median: float | None = Field(default=None, ge=0, le=1)
    q05: float | None = Field(default=None, ge=0, le=1)
    q25: float | None = Field(default=None, ge=0, le=1)
    q75: float | None = Field(default=None, ge=0, le=1)
    q95: float | None = Field(default=None, ge=0, le=1)
    applicability_probability: float | None = Field(default=None, ge=0, le=1)
    pending_probability: float | None = Field(default=None, ge=0, le=1)
    model_disagreement: float | None = Field(default=None, ge=0, le=1)
    effective_observation_count: int = Field(ge=0, le=10_000_000)
    model_set_version: str
    calibration_version: str
    contract_version: str
    contract_fingerprint: str
    product_metric_eligible: Literal[False]


class ModelPredictiveStageDto(StrictModel):
    model_key: str
    repository_id: str
    revision: str
    status: Literal["completed", "unavailable", "resource_exhausted", "failed"]
    error_code: str | None
    device: Literal["cpu", "cuda", "mps"] | None
    quantization: Literal["none", "bitsandbytes_nf4"]
    inference_latency_ms: float | None = Field(default=None, ge=0)
    peak_accelerator_memory_mb: float | None = Field(default=None, ge=0, le=6_144)
    process_rss_mb: float | None = Field(default=None, ge=0, le=8_192)
    unloaded_after_stage: Literal[True]


class ModelPredictiveFactorDto(StrictModel):
    factor_key: str
    scale: Literal["binary", "ordinal", "proportion"]
    weight: float = Field(gt=0)
    applicability_probability: float = Field(ge=0, le=1)
    present_probability: float = Field(ge=0, le=1)
    neutral_probability: float = Field(ge=0, le=1)
    absent_probability: float = Field(ge=0, le=1)
    expert_count: int = Field(ge=1, le=8)
    critical: bool


class ModelPredictiveMetricDetailDto(StrictModel):
    run_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    projection_version: Literal[PROBABILISTIC_METRIC_PROJECTION_VERSION]
    projected_at: datetime
    metric: ModelPredictiveMetricDto
    density_bins: tuple[float, ...] = Field(
        min_length=PROBABILISTIC_DENSITY_BIN_COUNT,
        max_length=PROBABILISTIC_DENSITY_BIN_COUNT,
    )
    factors: tuple[ModelPredictiveFactorDto, ...] = Field(max_length=8)
    experimental_label: Literal["Experimental model range"] = (
        "Experimental model range"
    )
    local_only: Literal[True] = True
    content_persisted: Literal[False] = False
    universal_trust_percentage_available: Literal[False] = False


class ModelEnsembleRunDto(StrictModel):
    run_id: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    plan_version: Literal["local-shadow-ensemble-v1"]
    plan_fingerprint: str = Field(pattern=PSEUDONYM_PATTERN.pattern)
    source_coverage_state: Literal["complete_window", "incomplete_source"]
    chunk_count: int = Field(ge=1, le=8)
    model_count: Literal[10] = Field(
        description=(
            "Historical compatibility expert-slot count; actual live model stages "
            "are listed in predictive_model_stages."
        )
    )
    chunks: tuple[ModelEnsembleChunkDto, ...] = Field(min_length=1, max_length=8)
    experts: tuple[ModelEnsembleExpertDto, ...] = Field(
        min_length=10,
        max_length=10,
        description=(
            "Immutable compatibility graph slots, not a claim that ten model "
            "processes ran in the current live cascade."
        ),
    )
    votes: tuple[ModelEnsembleVoteDto, ...] = Field(max_length=640)
    chunk_metrics: tuple[ModelEnsembleChunkMetricDto, ...] = Field(max_length=160)
    metrics: tuple[ModelEnsembleMetricDto, ...] = Field(min_length=1, max_length=20)
    metric_projection_version: Literal[
        MODEL_ENSEMBLE_METRIC_PROJECTION_VERSION
    ] | None
    metric_projection_completed_at: datetime | None
    typed_metrics: tuple[ModelEnsembleTypedMetricDto, ...] = Field(max_length=20)
    metric_publication_v2: MetricPublicationV2 | None
    #: Derived from the sealed publication above plus this run's provenance.
    #: It stores nothing of its own, so it is absent exactly when the sealed
    #: publication is absent.
    metric_evidence_readiness_v2: MetricEvidenceReadinessProjectionV2 | None
    predictive_projection_version: Literal[
        PROBABILISTIC_METRIC_PROJECTION_VERSION
    ] | None
    predictive_projected_at: datetime | None
    predictive_metrics: tuple[ModelPredictiveMetricDto, ...] = Field(max_length=20)
    predictive_model_stages: tuple[ModelPredictiveStageDto, ...] = Field(max_length=8)
    completed_at: datetime
    local_only: Literal[True]
    content_persisted: Literal[False]
    calibration_state: Literal["not_assessed"]
    product_metric_eligible: Literal[False]

    @classmethod
    def from_record(cls, record: SessionModelEnsembleRunRecord) -> "ModelEnsembleRunDto":
        receipt = record.receipt
        return cls(
            run_id=record.run_id,
            plan_version=receipt.plan_version,
            plan_fingerprint=receipt.plan_fingerprint,
            source_coverage_state=receipt.source_coverage_state.value,
            chunk_count=receipt.chunk_count,
            model_count=10,
            chunks=tuple(
                ModelEnsembleChunkDto(
                    ordinal=item.ordinal,
                    source_message_count=item.source_message_count,
                    fragment_count=item.fragment_count,
                    character_count=item.character_count,
                )
                for item in receipt.chunk_plan
            ),
            experts=tuple(
                ModelEnsembleExpertDto(
                    ordinal=item.identity.ordinal,
                    model_key=item.identity.model_key,
                    role=item.identity.role,
                    repository_id=item.identity.repository_id,
                    revision=item.identity.revision,
                    license_spdx=item.identity.license_spdx,
                    contributes_to_decision=item.identity.contributes_to_decision,
                    status=item.status.value,
                    error_code=item.error_code,
                    device=item.device,
                    inference_latency_ms=item.inference_latency_ms,
                    peak_accelerator_memory_mb=item.peak_accelerator_memory_mb,
                    process_rss_mb=item.process_rss_mb,
                    unloaded_after_stage=True,
                )
                for item in receipt.experts
            ),
            votes=tuple(
                ModelEnsembleVoteDto(
                    chunk_ordinal=item.chunk_ordinal,
                    metric_key=item.metric_key,
                    model_key=item.model_key,
                    role=item.role.value,
                    state=item.state.value,
                    raw_score=item.raw_score,
                    evidence_fragment_count=len(item.evidence_fragment_ids),
                    reason_code=item.reason_code,
                )
                for item in receipt.model_votes
            ),
            chunk_metrics=tuple(
                ModelEnsembleChunkMetricDto(
                    chunk_ordinal=item.chunk_ordinal,
                    metric_key=item.metric_key,
                    value_state=item.value_state.value,
                    numerator=item.numerator,
                    denominator=item.denominator,
                    rubric_vote=item.rubric_vote.value,
                    contributing_nli_votes=item.contributing_nli_votes,
                    diagnostic_nli_votes=item.diagnostic_nli_votes,
                    reason_code=item.reason_code,
                )
                for item in receipt.chunks
            ),
            metrics=tuple(
                ModelEnsembleMetricDto.model_validate(item.model_dump())
                for item in receipt.metrics
            ),
            metric_projection_version=receipt.metric_projection_version,
            metric_projection_completed_at=receipt.metric_projection_completed_at,
            typed_metrics=tuple(
                ModelEnsembleTypedMetricDto.model_validate(item.model_dump())
                for item in receipt.typed_metrics
            ),
            metric_publication_v2=receipt.metric_publication_v2,
            metric_evidence_readiness_v2=(
                None
                if receipt.metric_publication_v2 is None
                else project_metric_evidence_readiness_v2(
                    receipt.metric_publication_v2,
                    provider=record.provider,
                    provider_version=record.provider_version,
                    adapter_version=record.adapter_version,
                    source_schema_version=record.source_schema_version,
                )
            ),
            predictive_projection_version=(
                None
                if receipt.predictive_projection is None
                else receipt.predictive_projection.projection_version
            ),
            predictive_projected_at=(
                None
                if receipt.predictive_projection is None
                else receipt.predictive_projection.projected_at
            ),
            predictive_metrics=(
                ()
                if receipt.predictive_projection is None
                else tuple(
                    ModelPredictiveMetricDto.model_validate(
                        item.model_dump(exclude={"density_bins", "factors"})
                    )
                    for item in receipt.predictive_projection.metrics
                )
            ),
            predictive_model_stages=(
                ()
                if receipt.predictive_projection is None
                else tuple(
                    ModelPredictiveStageDto.model_validate(item.model_dump())
                    for item in receipt.predictive_projection.model_stages
                )
            ),
            completed_at=receipt.completed_at,
            local_only=True,
            content_persisted=False,
            calibration_state="not_assessed",
            product_metric_eligible=False,
        )


class ModelEnsembleOutcomeDto(StrictModel):
    run: ModelEnsembleRunDto
    applied: bool


def _failure(error: Exception) -> HTTPException:
    if isinstance(error, ModelEnsembleConsentError):
        return HTTPException(403, detail={"code": error.code, "message": "redacted-content consent required"})
    if isinstance(error, ModelEnsembleSelectionError):
        return HTTPException(404, detail={"code": error.code, "message": "selected session is not indexed"})
    if isinstance(error, ModelEnsembleCompatibilityError):
        return HTTPException(409, detail={"code": error.code, "message": "provider compatibility is not verified"})
    if isinstance(error, (ModelEnsembleInputError, ModelEnsembleConfirmationError)):
        return HTTPException(422, detail={"code": error.code, "message": "model ensemble request is invalid"})
    if isinstance(error, ModelEnsembleSourceError):
        status = {
            TextSourceFailureReason.SELECTION_SNAPSHOT_MISS: 409,
            TextSourceFailureReason.SELECTION_LIMIT: 413,
            TextSourceFailureReason.PROVIDER_RESPONSE_LIMIT: 413,
            TextSourceFailureReason.THREAD_STRUCTURE_LIMIT: 413,
            TextSourceFailureReason.PREVIEW_WINDOW_LIMIT: 413,
            TextSourceFailureReason.RESOURCE_LIMIT: 413,
            TextSourceFailureReason.NO_ANALYZABLE_TEXT: 422,
            TextSourceFailureReason.TIMEOUT: 504,
        }.get(error.reason, 503)
        return HTTPException(status, detail={"code": error.code, "message": "bounded local source read failed"})
    if isinstance(error, ModelEnsembleExecutionError):
        return HTTPException(503, detail={"code": error.code, "message": "local model ensemble execution failed"})
    if isinstance(error, ModelEnsemblePersistenceError):
        return HTTPException(503, detail={"code": error.code, "message": "local model ensemble persistence failed"})
    raise TypeError("unsupported model ensemble error")


def create_model_ensemble_router(
    require_local_auth: Callable[..., None],
    service: ModelEnsembleCommand,
) -> APIRouter:
    router = APIRouter(
        prefix="/v1",
        tags=["local-model-ensemble"],
        dependencies=[Depends(require_local_auth)],
    )

    @router.post(
        "/sessions/{session_id}/model-ensemble-runs",
        response_model=ModelEnsembleOutcomeDto,
    )
    def run_model_ensemble(
        payload: ModelEnsembleRequest,
        response: Response,
        session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
        idempotency_key: Annotated[
            str,
            Header(alias="Idempotency-Key", pattern=SAFE_VERSION_PATTERN.pattern),
        ],
    ) -> ModelEnsembleOutcomeDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            outcome = service.run(
                provider=Provider.CODEX,
                session_id=session_id,
                confirmation=payload.confirmation,
                idempotency_key=idempotency_key,
            )
        except (
            ModelEnsembleCompatibilityError,
            ModelEnsembleConfirmationError,
            ModelEnsembleConsentError,
            ModelEnsembleExecutionError,
            ModelEnsembleInputError,
            ModelEnsemblePersistenceError,
            ModelEnsembleSelectionError,
            ModelEnsembleSourceError,
        ) as error:
            raise _failure(error) from None
        return ModelEnsembleOutcomeDto(
            run=ModelEnsembleRunDto.from_record(outcome.run),
            applied=outcome.applied,
        )

    @router.get(
        "/sessions/{session_id}/model-ensemble-runs/latest",
        response_model=ModelEnsembleRunDto,
    )
    def latest_model_ensemble(
        response: Response,
        session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
    ) -> ModelEnsembleRunDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            run = service.latest(session_id)
        except (ModelEnsembleInputError, ModelEnsemblePersistenceError) as error:
            raise _failure(error) from None
        if run is None:
            raise HTTPException(404, detail="model ensemble result not found")
        return ModelEnsembleRunDto.from_record(run)

    @router.get(
        "/model-ensemble-runs/{run_id}/metrics/{metric_key}/predictive-detail",
        response_model=ModelPredictiveMetricDetailDto,
    )
    def predictive_metric_detail(
        response: Response,
        run_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)],
        metric_key: Annotated[str, Path(pattern=SAFE_VERSION_PATTERN.pattern)],
    ) -> ModelPredictiveMetricDetailDto:
        response.headers.update(_PRIVATE_HEADERS)
        try:
            run = service.get(run_id)
        except (ModelEnsembleInputError, ModelEnsemblePersistenceError) as error:
            raise _failure(error) from None
        if run is None or run.receipt.predictive_projection is None:
            raise HTTPException(404, detail="predictive metric result not found")
        projection = run.receipt.predictive_projection
        metric = next(
            (item for item in projection.metrics if item.metric_key == metric_key),
            None,
        )
        if metric is None or not metric.density_bins:
            raise HTTPException(404, detail="predictive metric detail is unavailable")
        return ModelPredictiveMetricDetailDto(
            run_id=run.run_id,
            projection_version=projection.projection_version,
            projected_at=projection.projected_at,
            metric=ModelPredictiveMetricDto.model_validate(
                metric.model_dump(exclude={"density_bins", "factors"})
            ),
            density_bins=metric.density_bins,
            factors=tuple(
                ModelPredictiveFactorDto.model_validate(item.model_dump())
                for item in metric.factors
            ),
        )

    return router


__all__ = [
    "ModelEnsembleOutcomeDto",
    "ModelEnsembleRequest",
    "ModelEnsembleRunDto",
    "ModelPredictiveMetricDetailDto",
    "ModelPredictiveMetricDto",
    "create_model_ensemble_router",
]
