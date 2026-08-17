import { useEffect, useMemo, useState } from "react";
import type {
  ModelEnsembleRun,
  ModelPredictiveMetricDetail,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { QUALITY_ANALYSIS_DEFINITIONS } from "../quality-profile/qualityProfile";
import { QUALITY_LENSES } from "../quality-profile/qualityLenses";

type CommitteeMetric = ModelEnsembleRun["metrics"][number];
type TypedMetric = ModelEnsembleRun["typed_metrics"][number];
type PredictiveMetric = ModelEnsembleRun["predictive_metrics"][number];
type EnsembleMetric = CommitteeMetric | TypedMetric;
export type ModelEnsembleRadarData = Pick<ModelEnsembleRun, "metrics" | "chunk_metrics"> & {
  typed_metrics: readonly TypedMetric[];
  predictive_metrics?: readonly PredictiveMetric[];
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

function stateExplanation(metric: EnsembleMetric): string {
  if (isTypedMetric(metric)) {
    switch (metric.explanation_code) {
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
  const signalKind = direction === "lower_is_better"
    ? "lower-is-better signal"
    : "positive signal";
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
  return lens.metrics.map(({ key }) => {
    const definition = DEFINITIONS.get(key);
    if (definition === undefined) throw new Error("model ensemble lens definition is missing");
    const metric = metrics.get(key) ?? null;
    const raw = metric?.value_state === "known" && metric.numeric_value != null
      ? metric.numeric_value
      : null;
    const prediction = predictions.get(key) ?? null;
    const distribution = prediction !== null
      && ["experimental", "calibrated", "out_of_distribution"].includes(prediction.state)
      && prediction.median != null && prediction.q05 != null && prediction.q25 != null
      && prediction.q75 != null && prediction.q95 != null;
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
      predictiveMedian: distribution ? orient(prediction.median) : null,
      predictiveQ05: distribution
        ? definition.direction === "lower_is_better" ? orient(prediction.q95) : orient(prediction.q05)
        : null,
      predictiveQ25: distribution
        ? definition.direction === "lower_is_better" ? orient(prediction.q75) : orient(prediction.q25)
        : null,
      predictiveQ75: distribution
        ? definition.direction === "lower_is_better" ? orient(prediction.q25) : orient(prediction.q75)
        : null,
      predictiveQ95: distribution
        ? definition.direction === "lower_is_better" ? orient(prediction.q05) : orient(prediction.q95)
        : null,
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

/** Keep state markers legible without changing the value geometry. */
export function modelEnsembleRadarMarkerMagnitude(plotted: number | null): number {
  if (plotted === null) return 0.1;
  return plotted === 0 ? 0.075 : plotted;
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
  return metric?.value_state.replaceAll("_", " ") ?? "not observed";
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
}: {
  run: ModelEnsembleRadarData;
  lensId: ModelEnsembleLensId;
  compact?: boolean;
  comparisonRun?: ModelEnsembleRadarData | null;
  snapshotLabel?: string;
  comparisonLabel?: string;
  detailRunId?: string;
  detailTransport?: Pick<PromptEnhancerTransport, "getModelPredictiveMetricDetail">;
}) {
  const axes = useMemo(() => modelEnsembleRadarAxes(run, lensId), [lensId, run]);
  const comparisonAxes = useMemo(
    () => comparisonRun === null ? null : modelEnsembleRadarAxes(comparisonRun, lensId),
    [comparisonRun, lensId],
  );
  const lens = MODEL_ENSEMBLE_LENSES.find((candidate) => candidate.id === lensId)!;
  const [selectedKey, setSelectedKey] = useState(axes.find((axis) => axis.metric !== null)?.key ?? axes[0]?.key ?? "");
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
    if (load === undefined || detailRunId === undefined || selected?.prediction === null || selected === undefined) {
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
  }, [detailRunId, detailTransport, selected?.key, selected?.prediction]);
  const size = compact ? 286 : 356;
  const center = size / 2;
  const radius = compact ? 82 : 108;
  const point = (index: number, magnitude: number) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / axes.length;
    return [
      center + Math.cos(angle) * radius * magnitude,
      center + Math.sin(angle) * radius * magnitude,
    ] as const;
  };
  const knownCount = axes.filter((axis) => axis.plotted !== null).length;
  const explicitZeroCount = axes.filter((axis) => axis.plotted === 0).length;
  const segments = modelEnsembleRadarSegments(axes);
  const predictiveSegments = modelEnsemblePredictiveSegments(axes);
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
  const band90 = modelEnsemblePredictiveBandPath(axes, "predictiveQ95", "predictiveQ05", point);
  const band50 = modelEnsemblePredictiveBandPath(axes, "predictiveQ75", "predictiveQ25", point);

  return (
    <figure className={`model-ensemble__radar${compact ? " model-ensemble__radar--compact" : ""}`}>
      <header className="model-ensemble__radar-header">
        <div>
          <strong>{lens.label}</strong>
          <span>
            {snapshotLabel} · {knownCount} numeric · {axes.length - knownCount} state-only
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
        {band90 !== null && <path className="model-ensemble__radar-band model-ensemble__radar-band--90" d={band90} fillRule="evenodd" />}
        {band50 !== null && <path className="model-ensemble__radar-band model-ensemble__radar-band--50" d={band50} fillRule="evenodd" />}
        {axes.map((axis, index) => {
          if (band90 !== null || axis.predictiveQ05 === null || axis.predictiveQ95 === null) return null;
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
        {predictiveSegments.map(([fromIndex, toIndex]) => {
          const from = point(fromIndex, axes[fromIndex].predictiveMedian!);
          const to = point(toIndex, axes[toIndex].predictiveMedian!);
          return <line className="model-ensemble__radar-predictive-segment" key={`predictive-${fromIndex}-${toIndex}`} x1={from[0]} x2={to[0]} y1={from[1]} y2={to[1]} />;
        })}
        {axes.map((axis, index) => {
          if (axis.predictiveMedian === null) return null;
          const value = point(index, axis.predictiveMedian);
          return <circle aria-label={`${axis.label}: experimental model median`} className="model-ensemble__radar-predictive-point" cx={value[0]} cy={value[1]} key={`predictive-point-${axis.key}`} r="2.8" />;
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
          const label = point(index, compact ? 1.24 : 1.28);
          const value = axis.plotted === null ? null : point(index, axis.plotted);
          const marker = point(index, modelEnsembleRadarMarkerMagnitude(axis.plotted));
          const coverage = axis.metric === null
            ? 0
            : isTypedMetric(axis.metric)
              ? axis.metric.coverage
              : axis.metric.total_chunk_count === 0
                ? 0
                : axis.metric.known_chunk_count / axis.metric.total_chunk_count;
          return (
            <g
              aria-label={`${axis.label}: ${stateLabel(axis.metric)}`}
              className={axis.key === selected?.key ? "is-selected" : undefined}
              key={axis.key}
              onClick={() => setSelectedKey(axis.key)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setSelectedKey(axis.key);
                }
              }}
              role="button"
              tabIndex={0}
            >
              <line className="model-ensemble__radar-axis" x1={center} x2={end[0]} y1={center} y2={end[1]} />
              <text className="model-ensemble__radar-label" textAnchor="middle" x={label[0]} y={label[1]}>
                {axis.shortLabel}
              </text>
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
                    aria-label={axis.plotted === 0 ? `${axis.label}: explicit known zero` : undefined}
                    className={`model-ensemble__radar-point${axis.plotted === 0 ? " model-ensemble__radar-point--zero" : ""}`}
                    cx={marker[0]}
                    cy={marker[1]}
                    r="4"
                  />
                </>
              ) : (
                <circle
                  aria-label={`${axis.label}: ${stateLabel(axis.metric)}`}
                  className={`model-ensemble__radar-state model-ensemble__radar-state--${axis.metric?.value_state ?? "missing"}`}
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
      <nav aria-label={`${lens.label} metric axes`} className="model-ensemble__axis-strip">
        {axes.map((axis) => (
          <button
            aria-pressed={axis.key === selected?.key}
            className={`is-${axis.metric?.value_state ?? "missing"}`}
            key={axis.key}
            onClick={() => setSelectedKey(axis.key)}
            type="button"
          >
            <span>{axis.shortLabel}</span>
            <b>{axis.plotted === null ? stateValue(axis.metric) : `${Math.round(axis.plotted * 100)}%`}</b>
            {axis.predictiveMedian !== null && <small>~{Math.round(axis.predictiveMedian * 100)}% model</small>}
          </button>
        ))}
      </nav>
      {selected !== undefined && (
        <section aria-live="polite" className="model-ensemble__focused-metric">
          <header>
            <div><strong>{selected.label}</strong><span>{stateLabel(selected.metric)}</span></div>
            <b>{selectedPresentation.value}</b>
          </header>
          <p>{selectedPresentation.detail}</p>
          <p>{selected.question}</p>
          {selected.prediction !== null && selected.predictiveMedian !== null && (
            <aside className="model-ensemble__predictive-detail">
              <strong>{selected.prediction.state === "calibrated" ? "Predictive interval" : "Experimental model range"}</strong>
              <span>
                median {Math.round(selected.predictiveMedian * 100)}% · central 50% {Math.round(selected.predictiveQ25! * 100)}–{Math.round(selected.predictiveQ75! * 100)}% · central 90% {Math.round(selected.predictiveQ05! * 100)}–{Math.round(selected.predictiveQ95! * 100)}%
              </span>
              <small>
                applicability {Math.round((selected.prediction.applicability_probability ?? 0) * 100)}% · disagreement {selected.prediction.model_disagreement == null ? "not estimable" : `${Math.round(selected.prediction.model_disagreement * 100)}%`} · n={selected.prediction.effective_observation_count} · {selected.prediction.calibration_version.replaceAll("-", " ")}
              </small>
              {predictiveDetailState === "loading" && <small>Loading the content-free factor distribution…</small>}
              {predictiveDetailState === "failed" && <small>Detailed factor distribution is temporarily unavailable.</small>}
              {predictiveDetail !== null && (
                <>
                  <div aria-label="Predictive density" className="model-ensemble__density">
                    {predictiveDetail.density_bins.map((mass, index) => (
                      <i
                        aria-label={`${index * 5}–${(index + 1) * 5}%: ${Math.round(mass * 100)}% mass`}
                        key={index}
                        style={{ height: `${Math.max(2, mass * 100)}%` }}
                      />
                    ))}
                  </div>
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
                  <div><dt>Message coverage</dt><dd>{selected.metric.observed_message_count}/{selected.metric.eligible_message_count}</dd></div>
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
        adjacent measured values only; gaps are unknown, not zero. The dotted line is the
        model median; dark and light translucent bands are central 50% and 90% experimental
        model ranges until a metric is independently calibrated. Rings around known
        points show source-message coverage for typed measurements (legacy
        receipts show eligible committee-observation coverage). Structural
        ownership cells are not analytic observations. The outline has no area fill because
        these metrics are separate constructs, not one overall quality score.
        {comparisonRun === null ? "" : ` Dashed lines and diamonds show ${comparisonLabel.toLowerCase()}.`}
      </figcaption>
    </figure>
  );
}
