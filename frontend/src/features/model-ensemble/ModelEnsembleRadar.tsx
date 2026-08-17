import { useEffect, useMemo, useState } from "react";
import type {
  ModelEnsembleRun,
  ModelPredictiveMetricDetail,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { QUALITY_ANALYSIS_DEFINITIONS } from "../quality-profile/qualityProfile";
import { QUALITY_LENSES } from "../quality-profile/qualityLenses";
import {
  MetricKnowledgeCardSlot,
  MetricKnowledgeDescriptions,
  metricKnowledgeCardTriggerProps,
  useMetricKnowledgeCardController,
  type MetricKnowledgeCardController,
} from "./MetricKnowledgeCard";
import { metricInspectorSentences } from "./metricHelpV2";

type CommitteeMetric = ModelEnsembleRun["metrics"][number];
type TypedMetric = ModelEnsembleRun["typed_metrics"][number];
type PredictiveMetric = ModelEnsembleRun["predictive_metrics"][number];
type EnsembleMetric = CommitteeMetric | TypedMetric;
export type ModelEnsembleRadarData = Pick<ModelEnsembleRun, "metrics" | "chunk_metrics"> & {
  typed_metrics: readonly TypedMetric[];
  predictive_metrics?: readonly PredictiveMetric[];
  predictive_model_stages?: ModelEnsembleRun["predictive_model_stages"];
};
type MetricDirection = "higher_is_better" | "lower_is_better";

export type ModelEnsembleLensId =
  | "task-framing"
  | "collaboration-flow"
  | "reasoning-trace"
  | "outcome-evidence";

const LENS_IDS = new Set<ModelEnsembleLensId>([
  "task-framing",
  "collaboration-flow",
  "reasoning-trace",
  "outcome-evidence",
]);

export const MODEL_ENSEMBLE_LENSES = QUALITY_LENSES.filter(
  (lens): lens is (typeof QUALITY_LENSES)[number] & { id: ModelEnsembleLensId } =>
    LENS_IDS.has(lens.id as ModelEnsembleLensId),
);

const DEFINITIONS = new Map(
  QUALITY_ANALYSIS_DEFINITIONS.map((definition) => [definition.key, definition]),
);

function isTypedMetric(metric: EnsembleMetric): metric is TypedMetric {
  return "projection_source" in metric;
}

/**
 * Presentation status for one sealed metric. `pending` is a typed unknown whose
 * episode horizon is still open: candidates were observed, but their follow-up
 * cannot be judged yet. It stays unplotted and is never converted to zero.
 */
export type ModelEnsembleMetricStatus =
  | EnsembleMetric["value_state"]
  | "pending"
  | "missing";

export function modelEnsembleMetricStatus(metric: EnsembleMetric | null): ModelEnsembleMetricStatus {
  if (metric === null) return "missing";
  if (
    isTypedMetric(metric)
    && metric.value_state !== "known"
    && metric.explanation_code === "episode_horizon_open"
  ) return "pending";
  return metric.value_state;
}

export function modelEnsembleMetricStatusLabel(status: ModelEnsembleMetricStatus): string {
  switch (status) {
    case "pending": return "pending · horizon open";
    case "missing": return "not observed";
    default: return status.replaceAll("_", " ");
  }
}

function stateExplanation(metric: EnsembleMetric): string {
  if (isTypedMetric(metric)) {
    switch (metric.explanation_code) {
      case "episode_horizon_open":
        return "Pending: the newest exchange is still open, so its follow-up cannot be judged yet. The value stays unknown until the episode closes. This is pending evidence, not a zero.";
      case "message_kind_unavailable":
        return "This adapter version does not expose the typed event family required by this metric. This is unavailable evidence, not a zero.";
      case "message_kind_unobserved":
        return "The adapter supports the required event family, but none was observed in this selected window. This is not a zero.";
      case "scope_changes_unobserved":
        return "No explicit scope-change opportunity was detected in this selected window. This is not a zero.";
      case "objective_evidence_stream_required":
      case "objective_verification_episode_required":
      case "objective_verification_stream_required":
        return "A typed local tool, test, artifact, or verification receipt is required. Transcript prose is deliberately not accepted as proof.";
      default:
        break;
    }
  }
  switch (metric.value_state) {
    case "not_applicable":
      return "No eligible denominator was observed in this window.";
    case "unknown":
      return metric.metric_key.startsWith("outcome.")
        ? "Objective test, tool, artifact, or requirement-verification evidence is unavailable. Assistant prose is not accepted as proof."
        : "The required evidence capability or denominator is unavailable.";
    case "abstained":
      return isTypedMetric(metric)
        ? "The typed contract could not establish a defensible denominator for this window."
        : "The opportunity may exist, but the committee did not support a numeric decision.";
    case "execution_error":
      return "Required local inference failed; this is not a low score.";
    default:
      return "No numeric value is available.";
  }
}

function stateValue(metric: EnsembleMetric | null): string {
  if (modelEnsembleMetricStatus(metric) === "pending") return "Pending";
  switch (metric?.value_state) {
    case "not_applicable":
      return "N/A";
    case "unknown":
      return "Unknown";
    case "abstained":
      return "Needs evidence";
    case "execution_error":
      return "Error";
    default:
      return metric === null ? "No record" : "—";
  }
}

export function modelEnsembleMetricPresentation(
  metric: EnsembleMetric,
  direction: MetricDirection,
) {
  if (
    metric.value_state !== "known"
    || metric.numeric_value == null
    || metric.numerator == null
    || metric.denominator == null
  ) {
    return { value: stateValue(metric), detail: stateExplanation(metric) };
  }
  const rawPercent = Math.round(metric.numeric_value * 100);
  const radarPercent = direction === "lower_is_better" ? 100 - rawPercent : rawPercent;
  if (direction === "lower_is_better") {
    const source = isTypedMetric(metric)
      ? `${metric.numerator}/${metric.denominator} typed opportunities`
      : `${metric.numerator}/${metric.denominator} known eligible observations`;
    return {
      value: `${radarPercent}% radar quality`,
      detail: `Raw lower-is-better rate ${rawPercent}% (${source}). The radar quality is ${radarPercent}%, so a lower observed rate appears farther from the center.`,
    };
  }
  const signalKind = "positive signal";
  if (isTypedMetric(metric)) {
    return {
      value: `${rawPercent}% measured`,
      detail: `${metric.numerator}/${metric.denominator} typed opportunities met the versioned local contract. ${metric.observed_message_count}/${metric.eligible_message_count} eligible messages were observed. Radar ${radarPercent}%.`,
    };
  }
  const explicitZero = metric.numerator === 0
    ? " This sealed shadow receipt stored a committee negative, not missing data or a failure score. Typed opportunity eligibility is still required before product use."
    : "";
  return {
    value: `${rawPercent}% signal`,
    detail: `${metric.numerator}/${metric.denominator} known eligible observations contained the ${signalKind}.${explicitZero} Radar ${radarPercent}%.`,
  };
}

export interface ModelEnsembleRadarAxis {
  key: string;
  label: string;
  shortLabel: string;
  direction: MetricDirection;
  question: string;
  metric: EnsembleMetric | null;
  plotted: number | null;
  prediction: PredictiveMetric | null;
  predictiveMedian: number | null;
  predictiveQ05: number | null;
  predictiveQ25: number | null;
  predictiveQ75: number | null;
  predictiveQ95: number | null;
  predictiveWithheldReason: string | null;
}

function isDeepModel(modelKey: string, repositoryId: string): boolean {
  return /qwen|rubric|deep/i.test(`${modelKey} ${repositoryId}`);
}

export const PREDICTIVE_WITHHELD_CONTRIBUTOR_PROOF_MISSING =
  "Withheld because this history point does not expose contributor proof; open the sealed snapshot to check its model stages.";
export const PREDICTIVE_WITHHELD_TOO_FEW_EXPERTS =
  "Withheld because fewer than two small experts are proven by this receipt.";

/**
 * Counts completed small (non-deep) expert stages, or `null` when the receipt
 * does not expose stage receipts at all. A trajectory-only history point has no
 * contributor proof; that is not the same as a sealed receipt proving fewer
 * than two experts.
 */
export function modelEnsembleCompletedSmallExperts(run: ModelEnsembleRadarData): number | null {
  if (run.predictive_model_stages === undefined) return null;
  return run.predictive_model_stages.filter(
    (stage) => stage.status === "completed" && !isDeepModel(stage.model_key, stage.repository_id),
  ).length;
}

export function modelEnsemblePredictiveVisibility(
  prediction: PredictiveMetric | null,
  completedSmallExperts: number | null,
): { visible: boolean; reason: string | null } {
  if (prediction === null || prediction.state === "unavailable" || prediction.state === "execution_error") {
    return { visible: false, reason: "No experimental estimate is available." };
  }
  if (prediction.state === "out_of_distribution") {
    return { visible: false, reason: "Withheld because this receipt is outside its calibration cohort." };
  }
  if (completedSmallExperts === null) {
    return { visible: false, reason: PREDICTIVE_WITHHELD_CONTRIBUTOR_PROOF_MISSING };
  }
  if (completedSmallExperts < 2) {
    return { visible: false, reason: PREDICTIVE_WITHHELD_TOO_FEW_EXPERTS };
  }
  if (
    prediction.median == null || prediction.q05 == null || prediction.q25 == null
    || prediction.q75 == null || prediction.q95 == null
  ) return { visible: false, reason: "The estimate does not contain a complete interval summary." };
  if (prediction.q95 - prediction.q05 >= 0.65) {
    return { visible: false, reason: "Uninformative experimental range withheld (90% span is at least 65 points)." };
  }
  return { visible: true, reason: null };
}

export function modelEnsembleDensityBinsForDirection(
  bins: readonly number[],
  direction: MetricDirection,
): number[] {
  return direction === "lower_is_better" ? [...bins].reverse() : [...bins];
}

export function modelEnsembleRadarAxes(
  run: ModelEnsembleRadarData,
  lensId: ModelEnsembleLensId,
): ModelEnsembleRadarAxis[] {
  const lens = MODEL_ENSEMBLE_LENSES.find((candidate) => candidate.id === lensId);
  if (lens === undefined) throw new Error("unknown model ensemble lens");
  const primaryMetrics = (run.typed_metrics?.length ?? 0) > 0 ? run.typed_metrics : run.metrics;
  const metrics = new Map(primaryMetrics.map((metric) => [metric.metric_key, metric]));
  const predictions = new Map((run.predictive_metrics ?? []).map((metric) => [metric.metric_key, metric]));
  const completedSmallExperts = modelEnsembleCompletedSmallExperts(run);
  return lens.metrics.map(({ key }) => {
    const definition = DEFINITIONS.get(key);
    if (definition === undefined) throw new Error("model ensemble lens definition is missing");
    const metric = metrics.get(key) ?? null;
    const raw = metric?.value_state === "known" && metric.numeric_value != null
      ? metric.numeric_value
      : null;
    const prediction = predictions.get(key) ?? null;
    const visibility = modelEnsemblePredictiveVisibility(prediction, completedSmallExperts);
    const distribution = visibility.visible;
    const visiblePrediction = distribution ? prediction! : null;
    const orient = (value: number | null | undefined): number | null => value == null
      ? null
      : definition.direction === "lower_is_better" ? 1 - value : value;
    return {
      key,
      label: definition.label,
      shortLabel: definition.shortLabel,
      direction: definition.direction,
      question: definition.question,
      metric,
      plotted: raw == null ? null : definition.direction === "lower_is_better" ? 1 - raw : raw,
      prediction,
      predictiveMedian: distribution ? orient(visiblePrediction!.median) : null,
      predictiveQ05: distribution
        ? definition.direction === "lower_is_better" ? orient(visiblePrediction!.q95) : orient(visiblePrediction!.q05)
        : null,
      predictiveQ25: distribution
        ? definition.direction === "lower_is_better" ? orient(visiblePrediction!.q75) : orient(visiblePrediction!.q25)
        : null,
      predictiveQ75: distribution
        ? definition.direction === "lower_is_better" ? orient(visiblePrediction!.q25) : orient(visiblePrediction!.q75)
        : null,
      predictiveQ95: distribution
        ? definition.direction === "lower_is_better" ? orient(visiblePrediction!.q05) : orient(visiblePrediction!.q95)
        : null,
      predictiveWithheldReason: visibility.reason,
    };
  });
}

/** Adjacent known axes may connect; an unknown axis always breaks the outline. */
export function modelEnsembleRadarSegments(
  axes: readonly ModelEnsembleRadarAxis[],
): Array<readonly [number, number]> {
  if (axes.length < 2) return [];
  const segments: Array<readonly [number, number]> = [];
  axes.forEach((axis, index) => {
    const next = (index + 1) % axes.length;
    if (axis.plotted !== null && axes[next].plotted !== null) {
      segments.push([index, next]);
    }
  });
  return segments;
}

/**
 * Non-numeric states (N/A, pending, unknown, error, abstained, missing) sit in a
 * state lane outside the numeric scale (magnitude > 1). Only a proven numeric
 * zero renders at the center; the value geometry is never shifted.
 */
export const MODEL_ENSEMBLE_STATE_LANE_MAGNITUDE = 1.1;
export const MODEL_ENSEMBLE_WITHHELD_LANE_MAGNITUDE = 1.18;
export function modelEnsembleRadarMarkerMagnitude(plotted: number | null): number {
  if (plotted === null) return MODEL_ENSEMBLE_STATE_LANE_MAGNITUDE;
  return plotted;
}

/** Explicit zero is a property of the sealed raw measurement, not radar geometry. */
export function modelEnsembleIsRawExplicitZero(axis: ModelEnsembleRadarAxis): boolean {
  return axis.metric?.value_state === "known" && axis.metric.numeric_value === 0;
}

export function modelEnsemblePredictiveSegments(
  axes: readonly ModelEnsembleRadarAxis[],
): Array<readonly [number, number]> {
  if (axes.length < 2) return [];
  const segments: Array<readonly [number, number]> = [];
  axes.forEach((axis, index) => {
    const next = (index + 1) % axes.length;
    if (axis.predictiveMedian !== null && axes[next].predictiveMedian !== null) {
      segments.push([index, next]);
    }
  });
  return segments;
}

export function modelEnsemblePredictiveBandPath(
  axes: readonly ModelEnsembleRadarAxis[],
  outer: "predictiveQ95" | "predictiveQ75",
  inner: "predictiveQ05" | "predictiveQ25",
  point: (index: number, magnitude: number) => readonly [number, number],
): string | null {
  if (axes.length < 3 || axes.some((axis) => axis[outer] === null || axis[inner] === null)) {
    return null;
  }
  const outerPoints = axes.map((axis, index) => point(index, axis[outer]!));
  const innerPoints = axes.map((axis, index) => point(index, axis[inner]!)).reverse();
  return `M ${outerPoints.map((value) => value.join(" ")).join(" L ")} Z M ${innerPoints.map((value) => value.join(" ")).join(" L ")} Z`;
}

function stateLabel(metric: EnsembleMetric | null): string {
  return modelEnsembleMetricStatusLabel(modelEnsembleMetricStatus(metric));
}

/**
 * Arrow-key navigation for a row of aria-pressed buttons. Tab remains usable;
 * arrows, Home, and End provide the expected compact-widget interaction.
 */
export function moveRovingFocus(
  event: { key: string; currentTarget: HTMLElement; preventDefault(): void },
  select?: (index: number) => void,
): void {
  const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
  if (buttons.length === 0) return;
  const current = buttons.findIndex((button) => button === event.currentTarget.ownerDocument.activeElement);
  let next: number;
  switch (event.key) {
    case "ArrowRight":
    case "ArrowDown":
      next = current < 0 ? 0 : (current + 1) % buttons.length;
      break;
    case "ArrowLeft":
    case "ArrowUp":
      next = current < 0 ? buttons.length - 1 : (current - 1 + buttons.length) % buttons.length;
      break;
    case "Home":
      next = 0;
      break;
    case "End":
      next = buttons.length - 1;
      break;
    default:
      return;
  }
  event.preventDefault();
  buttons[next].focus();
  select?.(next);
}

export function ModelEnsembleRadar({
  run,
  lensId,
  compact = false,
  comparisonRun = null,
  snapshotLabel = "Current snapshot",
  comparisonLabel = "Previous comparable snapshot",
  detailRunId,
  detailTransport,
  selectedMetricKey,
  onSelectedMetricKeyChange,
  helpController,
}: {
  run: ModelEnsembleRadarData;
  lensId: ModelEnsembleLensId;
  compact?: boolean;
  comparisonRun?: ModelEnsembleRadarData | null;
  snapshotLabel?: string;
  comparisonLabel?: string;
  detailRunId?: string;
  detailTransport?: Pick<PromptEnhancerTransport, "getModelPredictiveMetricDetail">;
  selectedMetricKey?: string;
  onSelectedMetricKeyChange?: (metricKey: string) => void;
  helpController?: MetricKnowledgeCardController;
}) {
  const axes = useMemo(() => modelEnsembleRadarAxes(run, lensId), [lensId, run]);
  const comparisonAxes = useMemo(
    () => comparisonRun === null ? null : modelEnsembleRadarAxes(comparisonRun, lensId),
    [comparisonRun, lensId],
  );
  const lens = MODEL_ENSEMBLE_LENSES.find((candidate) => candidate.id === lensId)!;
  const [internalSelectedKey, setInternalSelectedKey] = useState(axes.find((axis) => axis.metric !== null)?.key ?? axes[0]?.key ?? "");
  const selectedKey = selectedMetricKey ?? internalSelectedKey;
  const setSelectedKey = (metricKey: string) => {
    setInternalSelectedKey(metricKey);
    onSelectedMetricKeyChange?.(metricKey);
  };
  const [predictiveDetail, setPredictiveDetail] = useState<ModelPredictiveMetricDetail | null>(null);
  const [predictiveDetailState, setPredictiveDetailState] = useState<"idle" | "loading" | "failed">("idle");
  useEffect(() => {
    if (!axes.some((axis) => axis.key === selectedKey)) {
      setSelectedKey(axes.find((axis) => axis.metric !== null)?.key ?? axes[0]?.key ?? "");
    }
  }, [axes, selectedKey]);
  const selected = axes.find((axis) => axis.key === selectedKey) ?? axes[0];
  useEffect(() => {
    const load = detailTransport?.getModelPredictiveMetricDetail;
    if (
      load === undefined
      || detailRunId === undefined
      || selected === undefined
      || selected.prediction === null
      || selected.predictiveMedian === null
    ) {
      setPredictiveDetail(null);
      setPredictiveDetailState("idle");
      return undefined;
    }
    const controller = new AbortController();
    setPredictiveDetail(null);
    setPredictiveDetailState("loading");
    void load(detailRunId, selected.key, controller.signal)
      .then((detail) => {
        if (detail.metric.metric_key !== selected.key) throw new Error("predictive detail metric mismatch");
        setPredictiveDetail(detail);
        setPredictiveDetailState("idle");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setPredictiveDetail(null);
        setPredictiveDetailState("failed");
      });
    return () => controller.abort();
  }, [detailRunId, detailTransport, selected?.key, selected?.prediction, selected?.predictiveMedian]);
  const size = compact ? 340 : 380;
  const center = size / 2;
  const radius = compact ? 96 : 108;
  const ownHelpController = useMetricKnowledgeCardController();
  const helpCards = helpController ?? ownHelpController;
  const helpEntries = axes.map((axis) => ({ key: axis.key, label: axis.label, status: stateLabel(axis.metric) }));
  const point = (index: number, magnitude: number) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / axes.length;
    return [
      center + Math.cos(angle) * radius * magnitude,
      center + Math.sin(angle) * radius * magnitude,
    ] as const;
  };
  const knownCount = axes.filter((axis) => axis.plotted !== null).length;
  const pendingCount = axes.filter((axis) => modelEnsembleMetricStatus(axis.metric) === "pending").length;
  const explicitZeroCount = axes.filter(modelEnsembleIsRawExplicitZero).length;
  const segments = modelEnsembleRadarSegments(axes);
  const comparisonSegments = comparisonAxes === null ? [] : modelEnsembleRadarSegments(comparisonAxes);
  const selectedPresentation = selected?.metric === null || selected === undefined
    ? { value: "—", detail: "This metric is not present in the current receipt." }
    : modelEnsembleMetricPresentation(selected.metric, selected.direction);
  const chunkTrace = selected === undefined
    ? []
    : run.chunk_metrics
      .filter((metric) => metric.metric_key === selected.key)
      .sort((left, right) => left.chunk_ordinal - right.chunk_ordinal);
  const usesTypedProjection = (run.typed_metrics?.length ?? 0) > 0;
  const selectedCommitteeMetric = selected === undefined
    ? null
    : run.metrics.find((metric) => metric.metric_key === selected.key) ?? null;
  const predictiveCount = axes.filter((axis) => axis.predictiveMedian !== null).length;
  const weakestFactorKeys = predictiveDetail?.factors
    .slice()
    .sort((left, right) => left.present_probability - right.present_probability)
    .slice(0, 2)
    .map((factor) => factor.factor_key) ?? [];
  const displayDensityBins = predictiveDetail === null || selected === undefined
    ? []
    : modelEnsembleDensityBinsForDirection(predictiveDetail.density_bins, selected.direction);

  return (
    <figure className={`model-ensemble__radar${compact ? " model-ensemble__radar--compact" : ""}`}>
      <header className="model-ensemble__radar-header">
        <div>
          <strong>{lens.label}</strong>
          <span>
            {snapshotLabel} · {knownCount} numeric · {axes.length - knownCount} state-only
            {pendingCount > 0 ? ` · ${pendingCount} pending` : ""}
            {predictiveCount > 0 ? ` · ${predictiveCount} experimental ranges` : ""}
            {explicitZeroCount > 0 ? ` · ${explicitZeroCount} explicit zero${explicitZeroCount === 1 ? "" : "s"}` : ""}
          </span>
        </div>
        <span className="model-ensemble__radar-coverage">
          {usesTypedProjection ? "Typed local measurement" : "Legacy committee shadow"} · coverage, not confidence
        </span>
      </header>
      <svg
        aria-label={`${lens.label} ${usesTypedProjection ? "typed local metric" : "legacy shadow model"} radar with fixed axes`}
        role="img"
        viewBox={`0 0 ${size} ${size}`}
      >
        {[0.25, 0.5, 0.75, 1].map((level) => (
          <polygon
            className="model-ensemble__radar-ring"
            key={level}
            points={axes.map((_, index) => point(index, level).join(",")).join(" ")}
          />
        ))}
        {axes.map((axis, index) => {
          if (axis.predictiveQ05 === null || axis.predictiveQ95 === null) return null;
          const low = point(index, axis.predictiveQ05);
          const high = point(index, axis.predictiveQ95);
          const innerLow = point(index, axis.predictiveQ25!);
          const innerHigh = point(index, axis.predictiveQ75!);
          return (
            <g key={`predictive-band-${axis.key}`}>
              <line className="model-ensemble__radar-axis-range model-ensemble__radar-axis-range--90" x1={low[0]} x2={high[0]} y1={low[1]} y2={high[1]} />
              <line className="model-ensemble__radar-axis-range model-ensemble__radar-axis-range--50" x1={innerLow[0]} x2={innerHigh[0]} y1={innerLow[1]} y2={innerHigh[1]} />
            </g>
          );
        })}
        {axes.map((axis, index) => {
          if (axis.predictiveMedian === null) return null;
          const value = point(index, axis.predictiveMedian);
          return <rect
            aria-label={`${axis.label}: experimental radar-quality median`}
            className="model-ensemble__radar-predictive-point"
            height="6"
            key={`predictive-point-${axis.key}`}
            transform={`rotate(45 ${value[0]} ${value[1]})`}
            width="6"
            x={value[0] - 3}
            y={value[1] - 3}
          />;
        })}
        {comparisonAxes !== null && comparisonSegments.map(([fromIndex, toIndex]) => {
          const from = point(fromIndex, comparisonAxes[fromIndex].plotted!);
          const to = point(toIndex, comparisonAxes[toIndex].plotted!);
          return <line className="model-ensemble__radar-prior-segment" key={`prior-${fromIndex}-${toIndex}`} x1={from[0]} x2={to[0]} y1={from[1]} y2={to[1]} />;
        })}
        {comparisonAxes?.map((axis, index) => {
          if (axis.plotted === null) return null;
          const value = point(index, axis.plotted);
          return (
            <rect
              aria-label={`${comparisonLabel}: ${axis.label}`}
              className="model-ensemble__radar-prior-point"
              height="6"
              key={`prior-point-${axis.key}`}
              transform={`rotate(45 ${value[0]} ${value[1]})`}
              width="6"
              x={value[0] - 3}
              y={value[1] - 3}
            />
          );
        })}
        {axes.map((axis, index) => {
          const end = point(index, 1);
          const label = point(index, compact ? 1.3 : 1.32);
          const value = axis.plotted === null ? null : point(index, axis.plotted);
          const marker = point(index, modelEnsembleRadarMarkerMagnitude(axis.plotted));
          const withheld = point(index, MODEL_ENSEMBLE_WITHHELD_LANE_MAGNITUDE);
          const estimateWithheld = axis.prediction !== null && axis.predictiveMedian === null;
          const rawExplicitZero = modelEnsembleIsRawExplicitZero(axis);
          const coverage = axis.metric === null
            ? 0
            : isTypedMetric(axis.metric)
              ? axis.metric.coverage
              : axis.metric.total_chunk_count === 0
                ? 0
                : axis.metric.known_chunk_count / axis.metric.total_chunk_count;
          return (
            <g
              className={axis.key === selected?.key ? "is-selected" : undefined}
              key={axis.key}
            >
              <line className="model-ensemble__radar-axis" x1={center} x2={end[0]} y1={center} y2={end[1]} />
              <text className="model-ensemble__radar-label" textAnchor="middle" x={label[0]} y={label[1]}>
                {axis.shortLabel}
              </text>
              {estimateWithheld && (
                <rect
                  aria-label={`${axis.label}: experimental estimate withheld`}
                  className="model-ensemble__radar-withheld"
                  height="6"
                  transform={`rotate(45 ${withheld[0]} ${withheld[1]})`}
                  width="6"
                  x={withheld[0] - 3}
                  y={withheld[1] - 3}
                />
              )}
              {value !== null ? (
                <>
                  <circle
                    className="model-ensemble__radar-coverage-ring"
                    cx={marker[0]}
                    cy={marker[1]}
                    pathLength="100"
                    r="8"
                    strokeDasharray={`${Math.round(coverage * 100)} ${100 - Math.round(coverage * 100)}`}
                  />
                  <circle
                    aria-label={rawExplicitZero ? `${axis.label}: explicit known raw zero` : undefined}
                    className={`model-ensemble__radar-point${rawExplicitZero ? " model-ensemble__radar-point--zero" : ""}`}
                    cx={marker[0]}
                    cy={marker[1]}
                    r="4"
                  />
                </>
              ) : (
                <circle
                  aria-label={`${axis.label}: ${stateLabel(axis.metric)}`}
                  className={`model-ensemble__radar-state model-ensemble__radar-state--${modelEnsembleMetricStatus(axis.metric)}`}
                  cx={marker[0]}
                  cy={marker[1]}
                  r="5"
                />
              )}
            </g>
          );
        })}
        {segments.map(([fromIndex, toIndex]) => {
          const from = point(fromIndex, axes[fromIndex].plotted!);
          const to = point(toIndex, axes[toIndex].plotted!);
          return <line className="model-ensemble__radar-value-segment" key={`${fromIndex}-${toIndex}`} x1={from[0]} x2={to[0]} y1={from[1]} y2={to[1]} />;
        })}
      </svg>
      <MetricKnowledgeDescriptions controller={helpCards} entries={helpEntries} />
      <nav
        aria-label={`${lens.label} metric axes`}
        className="model-ensemble__axis-strip"
        onKeyDown={(event) => moveRovingFocus(event, (index) => setSelectedKey(axes[index].key))}
      >
        {axes.map((axis) => (
          <button
            aria-pressed={axis.key === selected?.key}
            className={`is-${modelEnsembleMetricStatus(axis.metric)}`}
            key={axis.key}
            {...metricKnowledgeCardTriggerProps(helpCards, "strip", axis.key)}
            onClick={() => { setSelectedKey(axis.key); helpCards.togglePin({ surface: "strip", metricKey: axis.key }); }}
            type="button"
          >
            <span>{axis.shortLabel}</span>
            <b>
              {axis.plotted === null
                ? stateValue(axis.metric)
                : axis.direction === "lower_is_better"
                  ? `${Math.round(axis.plotted * 100)}% radar quality`
                  : `${Math.round(axis.plotted * 100)}%`}
            </b>
            {axis.direction === "lower_is_better" && axis.metric?.value_state === "known" && axis.metric.numeric_value != null
              ? <small>raw rate {Math.round(axis.metric.numeric_value * 100)}%</small>
              : null}
            {axis.predictiveMedian !== null
              ? <small>◇ {Math.round(axis.predictiveMedian * 100)}% radar-quality estimate</small>
              : axis.prediction !== null ? <small>Estimate withheld</small> : null}
          </button>
        ))}
      </nav>
      <MetricKnowledgeCardSlot compact={compact} controller={helpCards} entries={helpEntries} surface="strip" />
      {selected !== undefined && (
        <section aria-live="polite" className="model-ensemble__focused-metric">
          <header>
            <div><strong>{selected.label}</strong><span>{stateLabel(selected.metric)}</span></div>
            <b>{selectedPresentation.value}</b>
          </header>
          {(() => {
            const sentences = metricInspectorSentences({
              metricKey: selected.key,
              label: selected.label,
              state: selected.metric?.value_state ?? "missing",
              direction: selected.direction,
              numericValue: selected.metric?.value_state === "known" ? selected.metric.numeric_value ?? null : null,
              numerator: selected.metric?.numerator ?? null,
              denominator: selected.metric?.denominator ?? null,
              explanationCode: selected.metric !== null && isTypedMetric(selected.metric) ? selected.metric.explanation_code : null,
              experimentalFactorKeys: predictiveDetail !== null && selected.predictiveMedian !== null ? weakestFactorKeys : [],
              experimentalVisible: selected.predictiveMedian !== null,
              experimentalMedian: selected.predictiveMedian,
            });
            return (
              <div className="metric-inspector-sentences" data-kind={sentences.kind}>
                <p><span>Meaning</span>{sentences.meaning}</p>
                <p><span>Next</span>{sentences.action}</p>
              </div>
            );
          })()}
          <p>{selectedPresentation.detail}</p>
          {selected.prediction !== null && (
            <aside className="model-ensemble__predictive-detail">
              <strong>{selected.prediction.state === "calibrated" ? "Predictive interval" : "Experimental estimate"}</strong>
              {selected.predictiveMedian === null ? (
                <span>{selected.predictiveWithheldReason}</span>
              ) : (
                <span>
                  radar-quality median {Math.round(selected.predictiveMedian * 100)}% · central 50% {Math.round(selected.predictiveQ25! * 100)}–{Math.round(selected.predictiveQ75! * 100)}% · central 90% {Math.round(selected.predictiveQ05! * 100)}–{Math.round(selected.predictiveQ95! * 100)}%
                </span>
              )}
              {selected.direction === "lower_is_better" && selected.prediction.median != null && (
                <small>
                  Raw modeled lower-is-better rate: median {Math.round(selected.prediction.median! * 100)}%
                  {selected.prediction.q05 != null && selected.prediction.q95 != null
                    ? ` · central 90% ${Math.round(selected.prediction.q05! * 100)}–${Math.round(selected.prediction.q95! * 100)}%`
                    : ""}.
                </small>
              )}
              <small>
                applicability {selected.prediction.applicability_probability == null
                  ? "not estimable"
                  : `${Math.round(selected.prediction.applicability_probability! * 100)}%`} · disagreement {selected.prediction.model_disagreement == null ? "not estimable" : `${Math.round(selected.prediction.model_disagreement * 100)}%`} · n={selected.prediction.effective_observation_count} · {selected.prediction.calibration_version.replaceAll("-", " ")}
              </small>
              {predictiveDetailState === "loading" && <small>Loading the content-free factor distribution…</small>}
              {predictiveDetailState === "failed" && <small>Detailed factor distribution is temporarily unavailable.</small>}
              {predictiveDetail !== null && (
                <>
                  <svg aria-label="Radar-quality predictive density" className="model-ensemble__density" role="img" viewBox="0 0 200 36">
                    <title>Experimental radar-quality density across twenty five-point bins</title>
                    <path d={`M 0 36 ${displayDensityBins.map((mass, index) => `L ${index * (200 / 19)} ${36 - Math.min(34, mass * 180)}`).join(" ")} L 200 36 Z`} />
                  </svg>
                  <small>The density uses the same radar-quality direction as the diamond and whiskers.</small>
                  <ul className="model-ensemble__factor-list">
                    {predictiveDetail.factors.map((factor) => (
                      <li key={factor.factor_key}>
                        <span>{factor.factor_key.replaceAll("_", " ")}</span>
                        <small>
                          present {Math.round(factor.present_probability * 100)}% · uncertain {Math.round(factor.neutral_probability * 100)}% · absent {Math.round(factor.absent_probability * 100)}%
                        </small>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </aside>
          )}
          {selected.metric !== null && (
            <dl>
              {isTypedMetric(selected.metric) ? (
                <>
                  <div><dt>Typed fraction</dt><dd>{selected.metric.numerator ?? "—"}/{selected.metric.denominator ?? "—"}</dd></div>
                  <div><dt>Metric coverage</dt><dd>{selected.metric.observed_message_count}/{selected.metric.eligible_message_count}</dd></div>
                  <div><dt>Model diagnostic</dt><dd>{selectedCommitteeMetric?.value_state.replaceAll("_", " ") ?? "unavailable"}</dd></div>
                  <div><dt>Calibration</dt><dd>not assessed</dd></div>
                </>
              ) : (
                <>
                  <div><dt>Known observations</dt><dd>{selected.metric.known_chunk_count}/{selected.metric.total_chunk_count}</dd></div>
                  <div><dt>Abstained</dt><dd>{selected.metric.abstained_chunk_count}</dd></div>
                  <div><dt>Unsupported</dt><dd>{selected.metric.unsupported_chunk_count}</dd></div>
                  <div><dt>Failed</dt><dd>{selected.metric.failed_chunk_count}</dd></div>
                </>
              )}
            </dl>
          )}
          {chunkTrace.length === 0 ? (
            <p className="model-ensemble__chunk-trace-note">
              Aggregate-only history point; select the live head for its per-window trace.
            </p>
          ) : (
            <div aria-label="Selected metric window trace" className="model-ensemble__chunk-trace">
              <span>{usesTypedProjection ? "Model committee diagnostic" : "Window trace"}</span>
              {chunkTrace.map((chunk) => (
                <i
                  aria-label={`Chunk ${chunk.chunk_ordinal + 1}: ${chunk.value_state.replaceAll("_", " ")}`}
                  className={`is-${chunk.value_state}`}
                  key={chunk.chunk_ordinal}
                  title={`Chunk ${chunk.chunk_ordinal + 1}: ${chunk.value_state.replaceAll("_", " ")}`}
                >
                  {chunk.value_state === "known" ? chunk.numerator : "·"}
                </i>
              ))}
              <small>{usesTypedProjection ? "does not override the typed value" : "ordered chunks, not a calibrated time trend"}</small>
            </div>
          )}
        </section>
      )}
      <figcaption>
        Axes and order stay fixed for this versioned lens. Solid segments connect
        adjacent measured values only; gaps are unknown, not zero. N/A, pending,
        unknown, error, and withheld markers sit in a state lane outside the numeric
        scale; only a known radar-quality zero renders at the center (a raw zero for
        higher-is-better, a raw rate of 100% for lower-is-better). A model estimate
        appears as an independent diamond with per-axis whiskers only when
        at least two small experts are proven and the 90% span is informative. Rings around known
        points show source-message coverage for typed measurements (legacy
        receipts show eligible committee-observation coverage). Structural
        ownership cells are not analytic observations. The outline has no area fill because
        these metrics are separate constructs, not one overall quality score.
        {comparisonRun === null ? "" : ` Dashed lines and diamonds show ${comparisonLabel.toLowerCase()}.`}
      </figcaption>
    </figure>
  );
}
