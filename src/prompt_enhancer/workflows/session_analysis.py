"""Versioned session-analysis composition over reusable factor components.

The input is an explicitly prepared chunk plan; no session discovery or storage.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import UTC, datetime
import hashlib
import json
import math
import random
import re
from statistics import median, pstdev
from time import monotonic
from typing import Callable, Mapping, Sequence
from ..application.analysis.model_ensemble import (
    ChunkMetricCommitteeReceipt,
    EnsembleChunkPlan,
    EnsembleMetricSpec,
    MODEL_ENSEMBLE_MODEL_COUNT,
    ModelExpertReceipt,
    ModelExpertStatus,
    ModelMetricVote,
    ModelVoteState,
    SessionModelEnsembleReceipt,
    SourceCoverageState,
    aggregate_chunk_metrics,
    content_free_chunk_plan,
)
from ..application.analysis.probabilistic_metrics import (
    EVIDENCE_LANE_METRIC_KEYS,
    EXPERIMENTAL_CALIBRATION_VERSION,
    PROBABILISTIC_DENSITY_BIN_COUNT,
    PROBABILISTIC_MAX_INFORMATIVE_INTERVAL_WIDTH,
    PROBABILISTIC_MAX_CRITICAL_UNRESOLVED_MASS,
    PROBABILISTIC_MAX_UNRESOLVED_FACTOR_MASS,
    PROBABILISTIC_MAX_WEIGHTED_UNRESOLVED_MASS,
    PROBABILISTIC_MAX_RSS_MIB,
    PROBABILISTIC_MAX_VRAM_MIB,
    PROBABILISTIC_METRIC_CONTRACTS,
    PROBABILISTIC_MIN_EXPERT_CONTRIBUTORS,
    PROBABILISTIC_MIN_RETAINED_SAMPLE_RATE,
    PROBABILISTIC_MODEL_SET_VERSION,
    PROBABILISTIC_PROMPT_PACKET_VERSION,
    PROBABILISTIC_SAMPLE_COUNT,
    EvidenceLane,
    MetricContract,
    ObservationScope,
    PromptLocale,
    PredictiveFactorContribution,
    PredictiveMetricState,
    PredictiveModelStageReceipt,
    SessionPredictiveMetricProjection,
    SessionPredictiveMetricReceipt,
    probabilistic_contract_set_fingerprint,
    probabilistic_metric_prompt_packet,
)
from ..application.analysis.evidence_contracts import EphemeralTypedEvidenceProjection
from ..application.persistence import MetricValueState
from ..infrastructure.text_models.model_ensemble import (
    MODEL_ENSEMBLE_RUNNER_SCHEMA_VERSION,
    MODEL_ENSEMBLE_SUBPROCESS_TIMEOUT_ERROR_CODE,
    EnsembleExpertSpec,
    ModelEnsembleError,
    StageExecutor,
    ensemble_expert_specs,
    probabilistic_challenger_specs,
    run_ensemble_expert_subprocess,
)
from ..infrastructure.text_models.run_control import ModelRunControl, controlled_model_run

from ..core.session_analysis import (
    LIVE_PROBABILISTIC_PLAN_VERSION,
    LIVE_PROBABILISTIC_MAX_SELECTED_FRAGMENTS,
    LIVE_PROBABILISTIC_MAX_DEEP_CASES,
    PROBABILISTIC_DEEP_PUBLICATION_BUDGET_SECONDS,
    PROBABILISTIC_DEEP_TIMEOUT_SECONDS,
    PROBABILISTIC_DEEP_TIMEOUT_ERROR_CODE,
    DISABLED_PROBABILISTIC_MODEL_KEYS,
    _TOKEN,
    DeepStageExecutor,
    _digest,
    _case_id,
    _tokens,
    _select_fragments,
    _build_cases,
    _parse_rows,
    _runtime_value,
    _stage_receipt,
    _invalid_output_stage,
    _old_stage_receipt,
    _quantile,
    _density,
    _robust_probability_pool,
    _unavailable_metric,
    _deep_cases,
    _parse_deep_rows,
    _cuda_deep_lane_available,
    _draw_metric_samples,
    _has_sufficient_retained_samples,
    _project_metric,
)

class SessionAnalysisWorkflow:
    """Pre-Bench factor workflow; providers execute typed, sequential steps."""

    workflow_id = "session-analysis"
    workflow_version = "1.0.0"
    compatible_core = ">=0.2.0,<0.3.0"
    step_implementations = (
        ("select", "factor-lexical-selection.v5"),
        ("nli_primary", "factor-nli.v5"),
        ("nli_secondary", "factor-nli.v5"),
        ("nli_tertiary", "factor-nli.v5"),
        ("adjudicate", "factor-disagreement-adjudication.v5"),
        ("project", "factor-projection.v5"),
    )

    def __init__(
        self,
        *,
        executor: StageExecutor | None = None,
        device: str = "auto",
        python_executable: str | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        deep_executor: DeepStageExecutor | None = None,
        deep_enabled: bool = True,
        expert_bindings: Mapping[str, EnsembleExpertSpec] | None = None,
    ) -> None:
        if device not in {"auto", "cpu", "cuda", "mps"}:
            raise ValueError("unsupported probabilistic device")
        self._device = device
        self._python_executable = python_executable
        self._clock = clock
        self._executor = executor or self._execute
        self._deep_executor = (
            deep_executor
            if deep_executor is not None
            else self._execute_deep
            if executor is None
            else None
        )
        self._deep_enabled = deep_enabled
        self._run_control = ModelRunControl()
        self._expert_bindings = dict(expert_bindings or {})
        defaults = ensemble_expert_specs()
        slots = {"nli_primary": 6, "nli_secondary": 7, "nli_tertiary": 8, "adjudicate": 9}
        if not set(self._expert_bindings) <= set(slots):
            raise ValueError("workflow_step_not_configurable")
        for key, spec in self._expert_bindings.items():
            if spec.identity.role != defaults[slots[key]].identity.role:
                raise ValueError("workflow_model_role_mismatch")
        specs = list(defaults)
        for key, spec in self._expert_bindings.items():
            specs[slots[key]] = spec
        if len({spec.identity.model_key for spec in specs}) != len(specs):
            raise ValueError("workflow_model_identity_duplicate")
        self._specs = tuple(specs)

    @property
    def _heartbeat(self) -> Callable[[], None] | None:
        return self._run_control.heartbeat

    @_heartbeat.setter
    def _heartbeat(self, callback: Callable[[], None] | None) -> None:
        self._run_control.heartbeat = callback

    def _execute(
        self,
        spec: EnsembleExpertSpec,
        stage: str,
        payload: Mapping[str, object],
        device: str,
    ) -> Mapping[str, object]:
        return run_ensemble_expert_subprocess(
            spec,
            stage,
            payload,
            device,
            python_executable=self._python_executable,
            heartbeat=self._heartbeat,
        )

    def _execute_deep(
        self,
        spec: EnsembleExpertSpec,
        stage: str,
        payload: Mapping[str, object],
        device: str,
        quantization: str,
    ) -> Mapping[str, object]:
        return run_ensemble_expert_subprocess(
            spec,
            stage,
            payload,
            device,
            python_executable=self._python_executable,
            heartbeat=self._heartbeat,
            quantization=quantization,
            timeout_seconds=PROBABILISTIC_DEEP_TIMEOUT_SECONDS,
        )

    def plan_fingerprint(
        self,
        metric_specs: tuple[EnsembleMetricSpec, ...],
    ) -> str:
        all_specs = self._specs
        challengers = tuple(
            item
            for item in probabilistic_challenger_specs()
            if item.identity.model_key not in DISABLED_PROBABILISTIC_MODEL_KEYS
        )
        specs = (*all_specs[6:9], *challengers, all_specs[9])
        return _digest(
            {
                "plan": LIVE_PROBABILISTIC_PLAN_VERSION,
                "contract_set": probabilistic_contract_set_fingerprint(),
                "prompt_packets": PROBABILISTIC_PROMPT_PACKET_VERSION,
                "models": [
                    {
                        "key": item.identity.model_key,
                        "revision": item.identity.revision,
                        "backend": item.identity.backend_key,
                        "quantization": (
                            "bitsandbytes_nf4"
                            if item.identity.model_key == all_specs[9].identity.model_key
                            else "none"
                        ),
                    }
                    for item in specs
                ],
                "metric_specs": [
                    (item.metric_key, item.metric_version) for item in metric_specs
                ],
                "resource": {
                    "vram_mib": PROBABILISTIC_MAX_VRAM_MIB,
                    "rss_mib": PROBABILISTIC_MAX_RSS_MIB,
                    "deep_timeout_seconds": PROBABILISTIC_DEEP_TIMEOUT_SECONDS,
                    "deep_publication_budget_seconds": (
                        PROBABILISTIC_DEEP_PUBLICATION_BUDGET_SECONDS
                    ),
                },
            }
        )

    @controlled_model_run
    def run(
        self,
        chunk_plan: EnsembleChunkPlan,
        metric_specs: tuple[EnsembleMetricSpec, ...],
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        prior_receipt: SessionModelEnsembleReceipt | None = None,
        typed_evidence: EphemeralTypedEvidenceProjection | None = None,
    ) -> SessionModelEnsembleReceipt:
        if chunk_plan.source_coverage_state is not SourceCoverageState.COMPLETE_WINDOW:
            raise ModelEnsembleError("probabilistic_source_incomplete")
        expected_keys = {item.metric_key for item in PROBABILISTIC_METRIC_CONTRACTS}
        if {item.metric_key for item in metric_specs} != expected_keys:
            raise ModelEnsembleError("probabilistic_metric_registry_mismatch")
        _ = prior_receipt
        # The objective projection is accepted as an ephemeral seam for the
        # measured semantic-unit lane. Predictive evidence-lane forecasts are
        # intentionally disabled regardless of its contents.
        _ = typed_evidence
        created_at = self._clock()
        fragments = tuple(
            fragment for chunk in chunk_plan.chunks for fragment in chunk.fragments
        )
        cases = _build_cases(chunk_plan)
        common = {
            "schema_version": MODEL_ENSEMBLE_RUNNER_SCHEMA_VERSION,
            "fragments": [
                {
                    "fragment_id": item.fragment_id,
                    "text": item.text.get_secret_value(),
                    "role": item.role.value,
                    "kind": item.kind.value,
                    "language": item.language.value,
                    "is_focus_message": item.is_focus_message,
                }
                for item in fragments
            ],
            "cases": list(cases),
        }
        nli_specs = self._specs[6:9]
        challenger_specs = tuple(
            item
            for item in probabilistic_challenger_specs()
            if item.identity.model_key not in DISABLED_PROBABILISTIC_MODEL_KEYS
        )
        language_by_fragment = {
            item.fragment_id: item.language.value for item in fragments
        }
        english_cases = tuple(
            case
            for case in cases
            if all(
                language_by_fragment.get(str(identifier)) == "en"
                for identifier in case["candidate_ids"]
            )
        )
        active_specs = (
            (*nli_specs, *challenger_specs) if english_cases else nli_specs
        )
        heartbeat_progress = [0]
        self._heartbeat = (
            None
            if progress_callback is None
            else lambda: progress_callback(
                heartbeat_progress[0], MODEL_ENSEMBLE_MODEL_COUNT
            )
        )
        if progress_callback is not None:
            progress_callback(0, MODEL_ENSEMBLE_MODEL_COUNT)
        stage_receipts: list[PredictiveModelStageReceipt] = []
        rows_by_model: dict[str, dict[str, tuple[float, float, float]]] = {}
        for index, spec in enumerate(active_specs, start=1):
            stage_cases = (
                english_cases if spec in challenger_specs else cases
            )
            stage_payload = {**common, "cases": list(stage_cases)}
            self._run_control.check()
            try:
                result = self._executor(
                    spec, "scope_nli", stage_payload, self._device
                )
                self._run_control.check()
                if (
                    result.get("status") != "completed"
                    and result.get("error_code") == "resource_exhausted"
                    and self._device != "cpu"
                ):
                    result = self._executor(
                        spec, "scope_nli", stage_payload, "cpu"
                    )
                    self._run_control.check()
            except ModelEnsembleError as error:
                self._run_control.check(error)
                result = None
            except Exception as error:
                self._run_control.check(error)
                result = None
            try:
                stage = _stage_receipt(spec, result)
            except (ModelEnsembleError, ValueError):
                stage = _invalid_output_stage(
                    spec,
                    error_code="probabilistic_stage_output_invalid",
                )
            stage_receipts.append(stage)
            if stage.status == "completed":
                try:
                    parsed_rows = _parse_rows(result, stage_cases)
                except ModelEnsembleError:
                    stage_receipts[-1] = _invalid_output_stage(
                        spec,
                        error_code="probabilistic_factor_output_invalid",
                    )
                else:
                    rows_by_model[spec.identity.model_key] = parsed_rows
            if progress_callback is not None:
                heartbeat_progress[0] = min(
                    MODEL_ENSEMBLE_MODEL_COUNT - 1,
                    round(
                        index
                        * (MODEL_ENSEMBLE_MODEL_COUNT - 1)
                        / len(active_specs)
                    ),
                )
                progress_callback(
                    heartbeat_progress[0], MODEL_ENSEMBLE_MODEL_COUNT
                )
        case_identity = {
            _case_id(contract.metric_key, factor.factor_key, purpose): (
                contract.metric_key,
                factor.factor_key,
                purpose,
            )
            for contract in PROBABILISTIC_METRIC_CONTRACTS
            for factor in contract.factors
            for purpose in ("applicability", "satisfaction")
        }
        deep_deadline = monotonic() + PROBABILISTIC_DEEP_PUBLICATION_BUDGET_SECONDS
        deep_cases = _deep_cases(cases, rows_by_model, case_identity)
        deep_spec = self._specs[9]
        deep_eligible = (
            deep_cases
            and self._deep_enabled
            and self._deep_executor is not None
            and _cuda_deep_lane_available(self._device, stage_receipts)
        )
        if deep_eligible:
            deep_payload = {**common, "cases": list(deep_cases)}
            if monotonic() >= deep_deadline:
                deep_result = {
                    "status": "unavailable",
                    "error_code": PROBABILISTIC_DEEP_TIMEOUT_ERROR_CODE,
                }
            else:
                self._run_control.check()
                try:
                    deep_result = self._deep_executor(
                        deep_spec,
                        "structured_rubric",
                        deep_payload,
                        self._device,
                        "bitsandbytes_nf4",
                    )
                    self._run_control.check()
                except ModelEnsembleError as error:
                    self._run_control.check(error)
                    deep_result = (
                        {
                            "status": "unavailable",
                            "error_code": PROBABILISTIC_DEEP_TIMEOUT_ERROR_CODE,
                        }
                        if error.args
                        == (MODEL_ENSEMBLE_SUBPROCESS_TIMEOUT_ERROR_CODE,)
                        else None
                    )
                except Exception as error:
                    self._run_control.check(error)
                    deep_result = None
            if monotonic() >= deep_deadline:
                deep_result = {
                    "status": "unavailable",
                    "error_code": PROBABILISTIC_DEEP_TIMEOUT_ERROR_CODE,
                }
            try:
                deep_stage = _stage_receipt(
                    deep_spec,
                    deep_result,
                    quantization="bitsandbytes_nf4",
                )
            except (ModelEnsembleError, ValueError):
                deep_stage = _invalid_output_stage(
                    deep_spec,
                    error_code="probabilistic_deep_stage_output_invalid",
                    quantization="bitsandbytes_nf4",
                )
            stage_receipts.append(deep_stage)
            if deep_stage.status == "completed":
                try:
                    labels = _parse_deep_rows(deep_result, deep_cases)
                except ModelEnsembleError:
                    stage_receipts[-1] = _invalid_output_stage(
                        deep_spec,
                        error_code="probabilistic_deep_output_invalid",
                        quantization="bitsandbytes_nf4",
                    )
                else:
                    deep_values: dict[str, tuple[float, float, float]] = {}
                    for case in deep_cases:
                        if monotonic() >= deep_deadline:
                            stage_receipts[-1] = _stage_receipt(
                                deep_spec,
                                {
                                    "status": "unavailable",
                                    "error_code": (
                                        PROBABILISTIC_DEEP_TIMEOUT_ERROR_CODE
                                    ),
                                },
                                quantization="bitsandbytes_nf4",
                            )
                            deep_values = {}
                            break
                        case_id = str(case["case_id"])
                        metric_key, factor_key, _purpose = case_identity[case_id]
                        label = labels[case_id]
                        # The deep judge emits a categorical state, not a
                        # calibrated probability. Preserve exactly that state.
                        deep_values[case_id] = {
                            "present": (1.0, 0.0, 0.0),
                            "absent": (0.0, 0.0, 1.0),
                            "abstain": (0.0, 1.0, 0.0),
                        }[label]
                        applicability_id = _case_id(
                            metric_key, factor_key, "applicability"
                        )
                        applicability_rows = [
                            values[applicability_id]
                            for values in rows_by_model.values()
                            if applicability_id in values
                        ]
                        if len(applicability_rows) >= PROBABILISTIC_MIN_EXPERT_CONTRIBUTORS:
                            deep_values[applicability_id] = _robust_probability_pool(
                                applicability_rows
                            )
                    if monotonic() >= deep_deadline:
                        stage_receipts[-1] = _stage_receipt(
                            deep_spec,
                            {
                                "status": "unavailable",
                                "error_code": PROBABILISTIC_DEEP_TIMEOUT_ERROR_CODE,
                            },
                            quantization="bitsandbytes_nf4",
                        )
                        deep_values = {}
                    if deep_values and stage_receipts[-1].status == "completed":
                        rows_by_model[deep_spec.identity.model_key] = deep_values
            if progress_callback is not None:
                progress_callback(MODEL_ENSEMBLE_MODEL_COUNT, MODEL_ENSEMBLE_MODEL_COUNT)
        self._heartbeat = None

        factor_outputs: dict[
            tuple[str, str, str, str], tuple[float, float, float]
        ] = {}
        for model_key, rows in rows_by_model.items():
            for case_id, values in rows.items():
                metric_key, factor_key, purpose = case_identity[case_id]
                factor_outputs[(model_key, metric_key, factor_key, purpose)] = values
        model_keys = tuple(rows_by_model)
        predictive_metrics = tuple(
            _project_metric(
                contract,
                factor_outputs,
                model_keys,
                chunk_plan.source_window_fingerprint,
            )
            for contract in PROBABILISTIC_METRIC_CONTRACTS
        )
        projected_at = self._clock()
        projection = SessionPredictiveMetricProjection(
            projected_at=projected_at,
            metrics=predictive_metrics,
            model_stages=tuple(stage_receipts),
        )

        all_specs = self._specs
        stage_by_key = {item.model_key: item for item in stage_receipts}
        experts = tuple(
            _old_stage_receipt(spec, stage_by_key.get(spec.identity.model_key))
            for spec in all_specs
        )
        owner = chunk_plan.chunks[-1].ordinal
        chunk_metrics: list[ChunkMetricCommitteeReceipt] = []
        votes: list[ModelMetricVote] = []
        for chunk in chunk_plan.chunks:
            for metric in metric_specs:
                structural = chunk.ordinal != owner
                chunk_metrics.append(
                    ChunkMetricCommitteeReceipt(
                        chunk_ordinal=chunk.ordinal,
                        metric_key=metric.metric_key,
                        value_state=(
                            MetricValueState.NOT_APPLICABLE
                            if structural
                            else MetricValueState.UNKNOWN
                        ),
                        rubric_vote=ModelVoteState.UNSUPPORTED,
                        contributing_nli_votes=0,
                        diagnostic_nli_votes=0,
                        reason_code=(
                            "predictive_observation_owned_by_final_chunk"
                            if structural
                            else "legacy_committee_replaced_by_predictive_sidecar"
                        ),
                    )
                )
                for spec in all_specs[6:]:
                    votes.append(
                        ModelMetricVote(
                            chunk_ordinal=chunk.ordinal,
                            metric_key=metric.metric_key,
                            model_key=spec.identity.model_key,
                            role=spec.identity.role,
                            state=ModelVoteState.UNSUPPORTED,
                            reason_code="predictive_sidecar_only",
                        )
                    )
        completed_at = self._clock()
        if progress_callback is not None:
            progress_callback(MODEL_ENSEMBLE_MODEL_COUNT, MODEL_ENSEMBLE_MODEL_COUNT)
        return SessionModelEnsembleReceipt(
            plan_fingerprint=self.plan_fingerprint(metric_specs),
            source_window_fingerprint=chunk_plan.source_window_fingerprint,
            source_coverage_state=chunk_plan.source_coverage_state,
            chunk_count=len(chunk_plan.chunks),
            chunk_plan=content_free_chunk_plan(chunk_plan),
            chunks=tuple(chunk_metrics),
            metrics=aggregate_chunk_metrics(tuple(chunk_metrics)),
            predictive_projection=projection,
            experts=experts,
            evidence_selections=(),
            model_votes=tuple(votes),
            created_at=created_at,
            completed_at=completed_at,
        )


LocalProbabilisticMetricRunner = SessionAnalysisWorkflow
