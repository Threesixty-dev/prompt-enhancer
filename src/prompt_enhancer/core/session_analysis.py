"""Pure factor selection, uncertainty routing, projection and receipt validation.

The session-analysis workflow supplies explicit prepared inputs and stage
outputs. These components never launch models, discover sessions or persist data.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
import random
import re
from statistics import median, pstdev
from typing import Callable, Mapping, Sequence

from ..application.analysis.model_ensemble import EnsembleChunkPlan, ModelExpertReceipt, ModelExpertStatus
from ..application.analysis.probabilistic_metrics import EVIDENCE_LANE_METRIC_KEYS, EXPERIMENTAL_CALIBRATION_VERSION, PROBABILISTIC_DENSITY_BIN_COUNT, PROBABILISTIC_MAX_INFORMATIVE_INTERVAL_WIDTH, PROBABILISTIC_MAX_CRITICAL_UNRESOLVED_MASS, PROBABILISTIC_MAX_UNRESOLVED_FACTOR_MASS, PROBABILISTIC_MAX_WEIGHTED_UNRESOLVED_MASS, PROBABILISTIC_MAX_RSS_MIB, PROBABILISTIC_MAX_VRAM_MIB, PROBABILISTIC_METRIC_CONTRACTS, PROBABILISTIC_MIN_EXPERT_CONTRIBUTORS, PROBABILISTIC_MIN_RETAINED_SAMPLE_RATE, PROBABILISTIC_MODEL_SET_VERSION, PROBABILISTIC_SAMPLE_COUNT, MetricContract, ObservationScope, PromptLocale, PredictiveFactorContribution, PredictiveMetricState, PredictiveModelStageReceipt, SessionPredictiveMetricReceipt, probabilistic_metric_prompt_packet
from ..infrastructure.text_models.model_ensemble import EnsembleExpertSpec, ModelEnsembleError


LIVE_PROBABILISTIC_PLAN_VERSION = "small-factor-router-v5"
LIVE_PROBABILISTIC_MAX_SELECTED_FRAGMENTS = 4
LIVE_PROBABILISTIC_MAX_DEEP_CASES = 12
PROBABILISTIC_DEEP_PUBLICATION_BUDGET_SECONDS = 30.0
# Reserve three seconds for forced tree termination, pipe closure, bounded
# result parsing, projection, and publication. The child may never consume the
# whole live budget by itself.
PROBABILISTIC_DEEP_TIMEOUT_SECONDS = 27.0
PROBABILISTIC_DEEP_TIMEOUT_ERROR_CODE = "probabilistic_deep_timeout"
DISABLED_PROBABILISTIC_MODEL_KEYS = frozenset(
    {"deberta_small_long_nli", "modernbert_base_zeroshot"}
)
_TOKEN = re.compile(r"[^\W_]{2,}", flags=re.UNICODE)

DeepStageExecutor = Callable[
    [EnsembleExpertSpec, str, Mapping[str, object], str, str],
    Mapping[str, object],
]


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _case_id(metric_key: str, factor_key: str, purpose: str) -> str:
    return _digest(
        {
            "plan": LIVE_PROBABILISTIC_PLAN_VERSION,
            "metric": metric_key,
            "factor": factor_key,
            "purpose": purpose,
        }
    )


def _tokens(value: str) -> frozenset[str]:
    return frozenset(match.group(0).casefold() for match in _TOKEN.finditer(value))


def _select_fragments(
    plan: EnsembleChunkPlan,
    contract: MetricContract,
    factor_key: str,
) -> tuple[str, ...]:
    ordered = tuple(fragment for chunk in plan.chunks for fragment in chunk.fragments)
    if contract.scope is ObservationScope.FOCUS_REQUEST:
        eligible = tuple(
            item
            for item in ordered
            if item.is_focus_message and item.role.value == "user"
        )
        if not eligible:
            eligible = tuple(item for item in ordered if item.role.value == "user")[-2:]
    elif contract.scope is ObservationScope.OBJECTIVE_EVIDENCE:
        eligible = tuple(
            item
            for item in ordered
            if item.kind.value in {"verification", "action", "decision", "response"}
        ) or ordered
    else:
        eligible = ordered
    if len(eligible) <= LIVE_PROBABILISTIC_MAX_SELECTED_FRAGMENTS:
        return tuple(item.fragment_id for item in eligible)

    factor_packet = probabilistic_metric_prompt_packet(contract.metric_key).factor(
        factor_key
    )
    # Retrieval is bilingual even though an individual NLI hypothesis is
    # localized later. This prevents Polish evidence selection from degrading
    # into role/recency-only ranking against an English query.
    query_tokens = _tokens(
        f"{factor_packet.statement_en} {factor_packet.statement_pl}".replace(".", " ")
    )
    scored: list[tuple[float, int, str]] = []
    for ordinal, item in enumerate(eligible):
        text_tokens = _tokens(item.text.get_secret_value())
        lexical = len(query_tokens & text_tokens)
        kind_bonus = 1.5 if item.kind.value in {"request", "feedback", "verification", "decision"} else 0.0
        focus_bonus = 2.0 if item.is_focus_message else 0.0
        recency = ordinal / max(1, len(eligible) - 1)
        scored.append((lexical * 3.0 + kind_bonus + focus_bonus + recency, ordinal, item.fragment_id))
    selected = {
        item.fragment_id for item in (eligible[0], eligible[-1])
    }
    for _score, _ordinal, identifier in sorted(
        scored, key=lambda item: (-item[0], item[1], item[2])
    ):
        selected.add(identifier)
        if len(selected) >= LIVE_PROBABILISTIC_MAX_SELECTED_FRAGMENTS:
            break
    order = {item.fragment_id: ordinal for ordinal, item in enumerate(ordered)}
    return tuple(sorted(selected, key=order.__getitem__))


def _build_cases(plan: EnsembleChunkPlan) -> tuple[dict[str, object], ...]:
    cases: list[dict[str, object]] = []
    owner = plan.chunks[-1].ordinal
    for contract in PROBABILISTIC_METRIC_CONTRACTS:
        # These metrics require typed objective receipts. Text models may help
        # route/link evidence later, but must not forecast the evidence result.
        if contract.metric_key in EVIDENCE_LANE_METRIC_KEYS:
            continue
        packet = probabilistic_metric_prompt_packet(contract.metric_key)
        for factor in contract.factors:
            candidates = _select_fragments(plan, contract, factor.factor_key)
            if not candidates:
                continue
            selected = tuple(
                fragment
                for chunk in plan.chunks
                for fragment in chunk.fragments
                if fragment.fragment_id in candidates
            )
            locale = (
                PromptLocale.POLISH
                if selected
                and all(item.language.value == "pl" for item in selected)
                else PromptLocale.ENGLISH
            )
            factor_statement = packet.factor(factor.factor_key).statement(locale)
            if locale is PromptLocale.POLISH:
                applicability_hypothesis = (
                    "Ten ograniczony epizod zawiera obserwowalną możliwość oceny "
                    f"następującego czynnika: {factor_statement}"
                )
                satisfaction_hypothesis = (
                    "Wybrane dowody spełniają następujący czynnik w określonym "
                    f"zakresie: {factor_statement}"
                )
            else:
                applicability_hypothesis = (
                    "This bounded episode contains an observable opportunity to "
                    f"assess the following factor: {factor_statement}"
                )
                satisfaction_hypothesis = (
                    "The selected evidence satisfies the following factor under "
                    f"its stated scope: {factor_statement}"
                )
            common = {
                "chunk_ordinal": owner,
                "metric_key": contract.metric_key,
                "candidate_ids": list(candidates),
                "query": factor_statement,
                "rubric": packet.deep_rubric(factor.factor_key, locale),
            }
            cases.append(
                {
                    **common,
                    "case_id": _case_id(
                        contract.metric_key, factor.factor_key, "applicability"
                    ),
                    "hypothesis": applicability_hypothesis,
                }
            )
            cases.append(
                {
                    **common,
                    "case_id": _case_id(
                        contract.metric_key, factor.factor_key, "satisfaction"
                    ),
                    "hypothesis": satisfaction_hypothesis,
                }
            )
    if not 1 <= len(cases) <= 160:
        raise ModelEnsembleError("probabilistic_factor_case_count_invalid")
    return tuple(cases)


def _parse_rows(
    result: Mapping[str, object] | None,
    cases: Sequence[Mapping[str, object]],
) -> dict[str, tuple[float, float, float]]:
    if result is None or result.get("status") != "completed":
        return {}
    rows = result.get("rows")
    if not isinstance(rows, list) or len(rows) != len(cases):
        raise ModelEnsembleError("probabilistic_factor_output_invalid")
    expected = {str(item["case_id"]) for item in cases}
    parsed: dict[str, tuple[float, float, float]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "case_id",
            "entailment",
            "neutral",
            "contradiction",
        }:
            raise ModelEnsembleError("probabilistic_factor_output_invalid")
        case_id = row["case_id"]
        if not isinstance(case_id, str) or case_id not in expected or case_id in parsed:
            raise ModelEnsembleError("probabilistic_factor_output_invalid")
        values = tuple(row[key] for key in ("entailment", "neutral", "contradiction"))
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0 <= float(value) <= 1
            for value in values
        ):
            raise ModelEnsembleError("probabilistic_factor_output_invalid")
        numeric = tuple(float(value) for value in values)
        if not math.isclose(sum(numeric), 1.0, rel_tol=0, abs_tol=1e-5):
            raise ModelEnsembleError("probabilistic_factor_output_invalid")
        parsed[case_id] = numeric
    if set(parsed) != expected:
        raise ModelEnsembleError("probabilistic_factor_output_invalid")
    return parsed


def _runtime_value(result: Mapping[str, object] | None, key: str) -> float | None:
    if result is None:
        return None
    runtime = result.get("runtime")
    if not isinstance(runtime, dict):
        return None
    value = runtime.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) and numeric >= 0 else None


def _stage_receipt(
    spec: EnsembleExpertSpec,
    result: Mapping[str, object] | None,
    *,
    quantization: str = "none",
) -> PredictiveModelStageReceipt:
    status = "failed"
    error = "model_stage_failed"
    device = None
    latency = _runtime_value(result, "inference_latency_ms")
    vram = _runtime_value(result, "peak_cuda_allocated_mb")
    rss = _runtime_value(result, "process_rss_after_load_and_inference_mb")
    if result is not None and result.get("status") == "completed":
        raw_device = result.get("device")
        if raw_device not in {"cpu", "cuda", "mps"}:
            raise ModelEnsembleError("probabilistic_stage_output_invalid")
        if (vram is not None and vram > PROBABILISTIC_MAX_VRAM_MIB) or (
            rss is not None and rss > PROBABILISTIC_MAX_RSS_MIB
        ):
            status = "resource_exhausted"
            error = "resource_contract_exceeded"
        else:
            status = "completed"
            error = None
            device = str(raw_device)
    elif result is not None:
        raw = result.get("error_code")
        error = raw if isinstance(raw, str) else "model_stage_failed"
        status = (
            "resource_exhausted"
            if error == "resource_exhausted"
            else "unavailable"
            if error in {
                "model_cache_missing_or_invalid",
                "cuda_unavailable",
                "quantization_backend_unavailable",
                PROBABILISTIC_DEEP_TIMEOUT_ERROR_CODE,
            }
            else "failed"
        )
    return PredictiveModelStageReceipt(
        model_key=spec.identity.model_key,
        repository_id=spec.identity.repository_id,
        revision=spec.identity.revision,
        status=status,
        error_code=error,
        device=device,
        quantization=quantization,
        inference_latency_ms=latency if status == "completed" else None,
        peak_accelerator_memory_mb=vram if status == "completed" else None,
        process_rss_mb=rss if status == "completed" else None,
        unloaded_after_stage=True,
    )


def _invalid_output_stage(
    spec: EnsembleExpertSpec,
    *,
    error_code: str,
    quantization: str = "none",
) -> PredictiveModelStageReceipt:
    return PredictiveModelStageReceipt(
        model_key=spec.identity.model_key,
        repository_id=spec.identity.repository_id,
        revision=spec.identity.revision,
        status="failed",
        error_code=error_code,
        quantization=quantization,
        unloaded_after_stage=True,
    )


def _old_stage_receipt(
    spec: EnsembleExpertSpec,
    stage: PredictiveModelStageReceipt | None,
) -> ModelExpertReceipt:
    if stage is not None and stage.status == "completed":
        return ModelExpertReceipt(
            identity=spec.identity,
            status=ModelExpertStatus.COMPLETED,
            device=stage.device,
            inference_latency_ms=stage.inference_latency_ms,
            peak_accelerator_memory_mb=stage.peak_accelerator_memory_mb,
            process_rss_mb=stage.process_rss_mb,
        )
    status = ModelExpertStatus.UNAVAILABLE
    error = "superseded_by_live_factor_router"
    if stage is not None:
        error = stage.error_code or "model_stage_failed"
        status = {
            "resource_exhausted": ModelExpertStatus.RESOURCE_EXHAUSTED,
            "failed": ModelExpertStatus.FAILED,
            "unavailable": ModelExpertStatus.UNAVAILABLE,
        }[stage.status]
    return ModelExpertReceipt(
        identity=spec.identity,
        status=status,
        error_code=error,
    )


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires samples")
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _density(values: Sequence[float]) -> tuple[float, ...]:
    counts = [0] * PROBABILISTIC_DENSITY_BIN_COUNT
    for value in values:
        index = min(
            PROBABILISTIC_DENSITY_BIN_COUNT - 1,
            int(value * PROBABILISTIC_DENSITY_BIN_COUNT),
        )
        counts[index] += 1
    total = sum(counts)
    if total == 0:
        raise ValueError("density requires samples")
    result = [count / total for count in counts]
    # Make the persisted vector sum exactly to one after binary floating-point
    # rounding without retaining any underlying samples.
    result[-1] += 1.0 - sum(result)
    return tuple(result)


def _robust_probability_pool(
    rows: Sequence[tuple[float, float, float]],
) -> tuple[float, float, float]:
    """Pool uncalibrated experts without treating softmax scores as weights.

    Component-wise medians are deliberately conservative under one extreme
    challenger. Calibration may replace this with a trained stacker later.
    """

    if len(rows) < PROBABILISTIC_MIN_EXPERT_CONTRIBUTORS:
        raise ValueError("robust probability pool requires two contributors")
    pooled = tuple(median(row[index] for row in rows) for index in range(3))
    total = sum(pooled)
    if total <= 1e-9:
        raise ValueError("robust probability pool has no mass")
    return tuple(value / total for value in pooled)  # type: ignore[return-value]


def _unavailable_metric(contract: MetricContract) -> SessionPredictiveMetricReceipt:
    return SessionPredictiveMetricReceipt(
        metric_key=contract.metric_key,
        target=contract.target,
        state=PredictiveMetricState.UNAVAILABLE,
        effective_observation_count=0,
        calibration_version=EXPERIMENTAL_CALIBRATION_VERSION,
        contract_version=contract.contract_version,
        contract_fingerprint=contract.fingerprint,
        product_metric_eligible=False,
    )


def _deep_cases(
    cases: Sequence[Mapping[str, object]],
    rows_by_model: Mapping[str, Mapping[str, tuple[float, float, float]]],
    case_identity: Mapping[str, tuple[str, str, str]],
) -> tuple[Mapping[str, object], ...]:
    selected: list[Mapping[str, object]] = []
    for case in cases:
        case_id = str(case["case_id"])
        identity = case_identity[case_id]
        if identity[2] != "satisfaction":
            continue
        rows = [values[case_id] for values in rows_by_model.values() if case_id in values]
        if len(rows) < 2:
            continue
        present = [item[0] for item in rows]
        neutral = median(item[1] for item in rows)
        if max(present) - min(present) >= 0.25 or neutral >= 0.34:
            selected.append(case)
        if len(selected) >= LIVE_PROBABILISTIC_MAX_DEEP_CASES:
            break
    return tuple(selected)


def _parse_deep_rows(
    result: Mapping[str, object] | None,
    cases: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    if result is None or result.get("status") != "completed":
        return {}
    rows = result.get("rows")
    if not isinstance(rows, list) or len(rows) != len(cases):
        raise ModelEnsembleError("probabilistic_deep_output_invalid")
    expected = {str(item["case_id"]) for item in cases}
    parsed: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"case_id", "label"}:
            raise ModelEnsembleError("probabilistic_deep_output_invalid")
        case_id, label = row["case_id"], row["label"]
        if (
            not isinstance(case_id, str)
            or case_id not in expected
            or case_id in parsed
            or label not in {"present", "absent", "abstain"}
        ):
            raise ModelEnsembleError("probabilistic_deep_output_invalid")
        parsed[case_id] = str(label)
    if set(parsed) != expected:
        raise ModelEnsembleError("probabilistic_deep_output_invalid")
    return parsed


def _cuda_deep_lane_available(
    device: str,
    completed_stages: Sequence[PredictiveModelStageReceipt],
) -> bool:
    """Decide from bounded receipts; never initialize Torch in the server."""

    if device in {"cpu", "mps"}:
        return False
    if device == "cuda":
        return True
    return any(
        stage.status == "completed" and stage.device == "cuda"
        for stage in completed_stages
    )


def _draw_metric_samples(
    contributions: Sequence[PredictiveFactorContribution],
    *,
    seed: int,
) -> tuple[tuple[float, ...], int]:
    """Draw exact aggregation samples while retaining unresolved mass."""

    generator = random.Random(seed)
    samples: list[float] = []
    applicable_draws = 0
    for _ in range(PROBABILISTIC_SAMPLE_COUNT):
        numerator = 0.0
        denominator = 0.0
        unresolved_draw = False
        any_applicable = False
        for factor in contributions:
            if generator.random() > factor.applicability_probability:
                continue
            any_applicable = True
            draw = generator.random()
            if draw < factor.present_probability:
                value = 1.0
            elif draw < factor.present_probability + factor.neutral_probability:
                # NLI neutral is unresolved evidence, never ordinal partial
                # credit. Invalidate the whole metric draw instead of
                # conditioning the surviving density on resolved factors.
                unresolved_draw = True
                continue
            else:
                value = 0.0
            numerator += value * factor.weight
            denominator += factor.weight
        if any_applicable:
            applicable_draws += 1
        if denominator > 0 and not unresolved_draw:
            samples.append(numerator / denominator)
    return tuple(samples), applicable_draws


def _has_sufficient_retained_samples(samples: Sequence[float]) -> bool:
    return (
        len(samples) / PROBABILISTIC_SAMPLE_COUNT
        >= PROBABILISTIC_MIN_RETAINED_SAMPLE_RATE
    )


def _project_metric(
    contract: MetricContract,
    outputs: Mapping[
        tuple[str, str, str, str],
        tuple[float, float, float],
    ],
    model_keys: tuple[str, ...],
    source_fingerprint: str,
) -> SessionPredictiveMetricReceipt:
    if contract.metric_key in EVIDENCE_LANE_METRIC_KEYS:
        return _unavailable_metric(contract)
    # v1 marks verification-strategy adequacy as objective-only even though the
    # future product route belongs in the behavioral reasoning view. Mutating
    # that frozen contract would invalidate persisted receipts, so v1 fails
    # closed here. TODO(v2): define a new CONVERSATION D+S contract and registry
    # identity before enabling its experimental estimate.
    if contract.objective_evidence_required:
        return _unavailable_metric(contract)
    # This v1 predictor has no typed semantic-lifecycle input.  A neutral NLI
    # class is epistemic uncertainty, not evidence that an interaction horizon
    # is still open.  Until lifecycle receipts are wired into this projection,
    # only structurally immediate contracts may publish an experimental range.
    if contract.closure_horizon != "immediate":
        return _unavailable_metric(contract)
    contributions: list[PredictiveFactorContribution] = []
    expert_factor_values: dict[str, list[tuple[float, float]]] = defaultdict(list)
    unresolved_weighted_mass = 0.0
    unresolved_weight = 0.0
    maximum_unresolved_factor_mass = 0.0
    joint_resolved_mass = 1.0
    critical_unresolved = False
    for factor in contract.factors:
        applicability_rows = []
        satisfaction_rows = []
        for model_key in model_keys:
            applicability = outputs.get(
                (model_key, contract.metric_key, factor.factor_key, "applicability")
            )
            satisfaction = outputs.get(
                (model_key, contract.metric_key, factor.factor_key, "satisfaction")
            )
            if applicability is None or satisfaction is None:
                continue
            applicability_rows.append(applicability)
            satisfaction_rows.append(satisfaction)
            decisive = satisfaction[0] + satisfaction[2]
            if decisive > 1e-9:
                expert_factor_values[model_key].append(
                    (satisfaction[0] / decisive, factor.weight)
                )
        if (
            len(applicability_rows) < PROBABILISTIC_MIN_EXPERT_CONTRIBUTORS
            or len(satisfaction_rows) < PROBABILISTIC_MIN_EXPERT_CONTRIBUTORS
        ):
            continue
        present, neutral, absent = _robust_probability_pool(satisfaction_rows)
        applicability, app_neutral, _app_absent = _robust_probability_pool(
            applicability_rows
        )
        # Applicability neutral and satisfaction neutral are both unresolved
        # model evidence. Neither is temporal pending and neither may be
        # conditioned away to make the score distribution look sharper.
        factor_unresolved_mass = max(neutral, app_neutral)
        unresolved_weighted_mass += factor_unresolved_mass * factor.weight
        unresolved_weight += factor.weight
        maximum_unresolved_factor_mass = max(
            maximum_unresolved_factor_mass,
            factor_unresolved_mass,
        )
        joint_resolved_mass *= 1.0 - factor_unresolved_mass
        if (
            factor.critical
            and factor_unresolved_mass
            >= PROBABILISTIC_MAX_CRITICAL_UNRESOLVED_MASS
        ):
            critical_unresolved = True
        contributions.append(
            PredictiveFactorContribution(
                factor_key=factor.factor_key,
                scale=factor.scale,
                weight=factor.weight,
                applicability_probability=applicability,
                present_probability=present,
                neutral_probability=neutral,
                absent_probability=absent,
                expert_count=len(satisfaction_rows),
                critical=factor.critical,
            )
        )
    if len(contributions) != len(contract.factors):
        return _unavailable_metric(contract)
    if (
        critical_unresolved
        or maximum_unresolved_factor_mass
        >= PROBABILISTIC_MAX_UNRESOLVED_FACTOR_MASS
        or unresolved_weighted_mass / unresolved_weight
        >= PROBABILISTIC_MAX_WEIGHTED_UNRESOLVED_MASS
        or joint_resolved_mass < PROBABILISTIC_MIN_RETAINED_SAMPLE_RATE
    ):
        return _unavailable_metric(contract)

    seed = int(
        hashlib.sha256(
            f"{PROBABILISTIC_MODEL_SET_VERSION}:{source_fingerprint}:{contract.metric_key}".encode(
                "ascii"
            )
        ).hexdigest(),
        16,
    )
    samples, applicable_draws = _draw_metric_samples(
        contributions,
        seed=seed,
    )
    if not _has_sufficient_retained_samples(samples):
        return _unavailable_metric(contract)

    expert_means = []
    for values in expert_factor_values.values():
        if values:
            expert_means.append(
                sum(value * weight for value, weight in values)
                / sum(weight for _value, weight in values)
            )
    disagreement = pstdev(expert_means) if len(expert_means) >= 2 else None
    q05 = _quantile(samples, 0.05)
    q95 = _quantile(samples, 0.95)
    if q95 - q05 >= PROBABILISTIC_MAX_INFORMATIVE_INTERVAL_WIDTH:
        return _unavailable_metric(contract)
    return SessionPredictiveMetricReceipt(
        metric_key=contract.metric_key,
        target=contract.target,
        state=PredictiveMetricState.EXPERIMENTAL,
        mean=sum(samples) / len(samples),
        median=_quantile(samples, 0.50),
        q05=q05,
        q25=_quantile(samples, 0.25),
        q75=_quantile(samples, 0.75),
        q95=q95,
        applicability_probability=applicable_draws / PROBABILISTIC_SAMPLE_COUNT,
        # Immediate contracts have no open/right-censored horizon by
        # definition.  Neutral mass remains in factor uncertainty and never
        # masquerades as temporal pending probability.
        pending_probability=0.0,
        model_disagreement=disagreement,
        effective_observation_count=1,
        calibration_version=EXPERIMENTAL_CALIBRATION_VERSION,
        contract_version=contract.contract_version,
        contract_fingerprint=contract.fingerprint,
        density_bins=_density(samples),
        factors=tuple(contributions),
        product_metric_eligible=False,
    )
