import { useEffect, useMemo, useState } from "react";
import type {
  ModelEnsembleRun,
  ModelEnsembleAttemptStage,
  ModelEnsembleTrajectoryPoint,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { sessionMetricGuidance } from "../quality-profile/metricGuidance";
import {
  MODEL_ENSEMBLE_LENSES,
  ModelEnsembleRadar,
  modelEnsembleMetricPresentation,
  modelEnsembleMetricStatus,
  modelEnsembleMetricStatusLabel,
  modelEnsembleRadarAxes,
  moveRovingFocus,
  type ModelEnsembleLensId,
  type ModelEnsembleRadarData,
} from "./ModelEnsembleRadar";

type MetricStage = {
  modelKey: string;
  repositoryId: string;
  revision: string;
  status: "completed" | "unavailable" | "resource_exhausted" | "failed" | "cancelled";
  errorCode: string | null;
  device: "cpu" | "cuda" | "mps" | null;
  quantization: string;
  latency: number | null;
  acceleratorMemory: number | null;
  rss: number | null;
  unloaded: boolean;
  evaluatedCases: number | null;
  contributedCases: number | null;
  group: "Factor models" | "Challengers" | "Deep judge" | "Legacy stages";
  role: string;
};

export interface MetricWorkspaceHistory {
  points: readonly ModelEnsembleTrajectoryPoint[];
  headRunId: string | null;
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
  error?: boolean;
}

export function modelEnsembleTrajectoryRadarData(
  point: ModelEnsembleTrajectoryPoint,
): ModelEnsembleRadarData {
  return {
    metrics: point.metrics,
    typed_metrics: point.typed_metrics ?? [],
    predictive_metrics: point.predictive_metrics ?? [],
    chunk_metrics: [],
  };
}

function shortIdentity(value: string): string {
  return value.length <= 12 ? value : `${value.slice(0, 8)}…${value.slice(-4)}`;
}

function stageGroup(modelKey: string, repositoryId: string): MetricStage["group"] {
  const identity = `${modelKey} ${repositoryId}`;
  if (/qwen|rubric|deep/i.test(identity)) return "Deep judge";
  if (/modernbert|deberta.*small.*long|challenger/i.test(identity)) return "Challengers";
  return "Factor models";
}

function stageRole(modelKey: string, repositoryId: string): string {
  const identity = `${modelKey} ${repositoryId}`;
  if (/qwen|rubric|deep/i.test(identity)) return "Selective disagreement adjudicator";
  if (/modernbert|deberta.*small.*long/i.test(identity)) return "English / long-context challenger";
  if (/minilm/i.test(identity)) return "Cheap multilingual factor challenger";
  if (/mdeberta|xnli/i.test(identity)) return "Primary multilingual factor model";
  return "Local factor model";
}

function stagesFor(run: ModelEnsembleRun | null): MetricStage[] {
  if (run === null) return [];
  const predictiveStages = run.predictive_model_stages ?? [];
  if (predictiveStages.length > 0) {
    return predictiveStages.map((stage) => ({
      modelKey: stage.model_key,
      repositoryId: stage.repository_id,
      revision: stage.revision,
      status: stage.status,
      errorCode: stage.error_code,
      device: stage.device,
      quantization: stage.quantization,
      latency: stage.inference_latency_ms ?? null,
      acceleratorMemory: stage.peak_accelerator_memory_mb ?? null,
      rss: stage.process_rss_mb ?? null,
      unloaded: stage.unloaded_after_stage,
      evaluatedCases: null,
      contributedCases: null,
      group: stageGroup(stage.model_key, stage.repository_id),
      role: stageRole(stage.model_key, stage.repository_id),
    }));
  }
  return (run.experts ?? []).map((stage) => ({
    modelKey: stage.model_key,
    repositoryId: stage.repository_id,
    revision: stage.revision,
    status: stage.status,
    errorCode: stage.error_code,
    device: stage.device,
    quantization: "legacy receipt",
    latency: stage.inference_latency_ms ?? null,
    acceleratorMemory: stage.peak_accelerator_memory_mb ?? null,
    rss: stage.process_rss_mb ?? null,
    unloaded: stage.unloaded_after_stage,
    evaluatedCases: null,
    contributedCases: null,
    group: "Legacy stages",
    role: stage.role.replaceAll("_", " "),
  }));
}

function attemptStagesFor(stages: readonly ModelEnsembleAttemptStage[]): MetricStage[] {
  return stages.map((stage) => ({
    modelKey: stage.model_key ?? stage.stage_key,
    repositoryId: stage.repository_id ?? stage.stage_key.replaceAll("_", " "),
    revision: stage.revision ?? "not-recorded",
    status: stage.state,
    errorCode: stage.error_code,
    device: stage.device,
    quantization: stage.quantization,
    latency: stage.inference_latency_ms,
    acceleratorMemory: stage.peak_accelerator_memory_mb,
    rss: stage.process_rss_mb,
    unloaded: stage.unloaded_after_stage ?? false,
    evaluatedCases: stage.evaluated_case_count,
    contributedCases: stage.contributed_case_count,
    group: stageGroup(stage.model_key ?? stage.stage_key, stage.repository_id ?? ""),
    role: stageRole(stage.model_key ?? stage.stage_key, stage.repository_id ?? ""),
  }));
}

function formatResource(value: number | null): string {
  return value === null ? "not recorded" : `${Math.round(value)} MiB`;
}

function ModelConstellation({ run, attemptStages, compact }: { run: ModelEnsembleRun | null; attemptStages: readonly ModelEnsembleAttemptStage[]; compact: boolean }) {
  const stages = attemptStages.length > 0 ? attemptStagesFor(attemptStages) : stagesFor(run);
  const [selectedKey, setSelectedKey] = useState(stages[0]?.modelKey ?? "");
  const selected = stages.find((stage) => stage.modelKey === selectedKey) ?? stages[0];
  const groups = ["Factor models", "Challengers", "Deep judge", "Legacy stages"] as const;
  useEffect(() => {
    if (stages.length > 0 && !stages.some((stage) => stage.modelKey === selectedKey)) {
      setSelectedKey(stages[0].modelKey);
    }
  }, [selectedKey, stages]);
  return (
    <details className="metric-workspace__drawer model-constellation">
      <summary>
        <span>Models</span>
        <small>{stages.length === 0
          ? "Stage receipts not exposed"
          : `${stages.filter((stage) => stage.status === "completed").length}/${stages.length} stages completed`}</small>
      </summary>
      <div className="model-constellation__body">
        {stages.length === 0 && <p>Model stage details are not exposed for this sealed receipt.</p>}
        {groups.map((group) => {
          const groupStages = stages.filter((stage) => stage.group === group);
          if (groupStages.length === 0) return null;
          return (
            <section key={group}>
              <strong>{group}</strong>
              <div
                className="model-constellation__nodes"
                onKeyDown={(event) => moveRovingFocus(event)}
              >
                {groupStages.map((stage) => (
                  <button
                    aria-pressed={stage.modelKey === selected?.modelKey}
                    data-status={stage.status}
                    key={stage.modelKey}
                    onClick={() => setSelectedKey(stage.modelKey)}
                    title={`${stage.repositoryId} · ${stage.role}`}
                    type="button"
                  >
                    <i aria-hidden="true" />
                    <span>{stage.repositoryId.split("/").at(-1)}</span>
                    <small>{stage.status.replaceAll("_", " ")}</small>
                  </button>
                ))}
              </div>
            </section>
          );
        })}
        {selected !== undefined && (
          <aside aria-live="polite" className="model-constellation__inspector">
            <header><strong>{selected.repositoryId}</strong><span>{selected.role}</span></header>
            <dl>
              <div><dt>Status</dt><dd>{selected.status.replaceAll("_", " ")}</dd></div>
              <div><dt>Device</dt><dd>{selected.device?.toUpperCase() ?? "none"}</dd></div>
              <div><dt>Quantization</dt><dd>{selected.quantization.replaceAll("_", " ")}</dd></div>
              <div><dt>Latency</dt><dd>{selected.latency === null ? "not recorded" : `${selected.latency} ms`}</dd></div>
              {!compact && <div><dt>Peak VRAM</dt><dd>{formatResource(selected.acceleratorMemory)}</dd></div>}
              {!compact && <div><dt>Peak RAM</dt><dd>{formatResource(selected.rss)}</dd></div>}
              <div><dt>Released</dt><dd>{selected.unloaded ? "yes" : "not confirmed"}</dd></div>
              <div><dt>Revision</dt><dd>{shortIdentity(selected.revision)}</dd></div>
              <div><dt>Evaluated</dt><dd>{selected.evaluatedCases ?? "unavailable"}</dd></div>
              <div><dt>Contributed</dt><dd>{selected.contributedCases ?? "unavailable"}</dd></div>
            </dl>
            {selected.errorCode !== null && <p role="alert">{selected.errorCode.replaceAll("_", " ")}</p>}
            {(selected.evaluatedCases === null || selected.contributedCases === null) && <p>Case counts are unavailable for this stage receipt; they are not zero. Current v1 receipts identify the stage without trustworthy per-metric contribution counts.</p>}
          </aside>
        )}
      </div>
    </details>
  );
}

export function modelEnsembleHistoryRadarValue(
  point: ModelEnsembleTrajectoryPoint,
  metricKey: string,
  direction: "higher_is_better" | "lower_is_better",
): number | null {
  const typed = point.typed_metrics.find((metric) => metric.metric_key === metricKey);
  const raw = typed?.value_state === "known"
    ? typed.numeric_value ?? null
    : point.metrics.find((metric) => metric.metric_key === metricKey)?.value_state === "known"
      ? point.metrics.find((metric) => metric.metric_key === metricKey)?.numeric_value ?? null
      : null;
  return raw === null ? null : direction === "lower_is_better" ? 1 - raw : raw;
}

function HistoryDrawer({ history, metricKey, direction }: {
  history?: MetricWorkspaceHistory;
  metricKey: string;
  direction: "higher_is_better" | "lower_is_better";
}) {
  const chronological = [...(history?.points ?? [])].reverse();
  const values = chronological.map((point) => modelEnsembleHistoryRadarValue(point, metricKey, direction));
  const coordinates = values.map((value, index) => value === null
    ? null
    : [8 + index * (184 / Math.max(1, values.length - 1)), 42 - value * 34] as const);
  const segments = coordinates.flatMap((coordinate, index) => {
    const next = coordinates[index + 1];
    const currentPoint = chronological[index];
    const nextPoint = chronological[index + 1];
    return coordinate !== null && next !== null && currentPoint?.comparable_to_head && nextPoint?.comparable_to_head
      ? [[coordinate, next] as const]
      : [];
  });
  return (
    <details className="metric-workspace__drawer metric-history">
      <summary><span>History</span><small>{history === undefined ? "Not exposed for this receipt" : `${history.points.length} sealed snapshots`}</small></summary>
      <div className="metric-history__body">
        {history === undefined ? (
          <p>Snapshot history becomes available when the local watch exposes a content-free trajectory. The current sealed snapshot remains unchanged.</p>
        ) : (
          <>
            {history.error && <p role="status">History refresh is delayed; the previously loaded trajectory remains visible.</p>}
            <p>Radar quality over comparable sealed snapshots · higher is better.</p>
            <svg aria-label="Selected metric history" role="img" viewBox="0 0 200 50">
              <line x1="8" x2="192" y1="42" y2="42" />
              {segments.map(([from, to], index) => <line key={index} x1={from[0]} x2={to[0]} y1={from[1]} y2={to[1]} />)}
              {coordinates.map((coordinate, index) => coordinate === null ? null : (
                <circle
                  className={chronological[index].run_id === history.selectedRunId ? "is-selected" : undefined}
                  cx={coordinate[0]}
                  cy={coordinate[1]}
                  key={chronological[index].run_id}
                  r="3"
                />
              ))}
            </svg>
            <div className="metric-history__snapshots">
              {history.points.slice(0, 8).map((point, index) => (
                <button
                  aria-label={point.run_id === history.headRunId ? "Open live snapshot" : `Open earlier snapshot ${index + 1}`}
                  aria-pressed={point.run_id === history.selectedRunId}
                  key={point.run_id}
                  onClick={() => history.onSelectRun(point.run_id)}
                  type="button"
                >
                  <span>{point.run_id === history.headRunId ? "Live" : `#${index + 1}`}</span>
                  <small>{point.comparable_to_head ? "comparable" : "scope break"}</small>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </details>
  );
}

export function MetricWorkspace({
  mode,
  run,
  runId,
  stageRun = null,
  transport,
  lensId,
  onLensChange,
  snapshotLabel,
  comparisonRun = null,
  comparisonLabel,
  scopeLabel = "Scope not exposed",
  history,
  attemptStages = [],
}: {
  mode: "full" | "compact";
  run: ModelEnsembleRadarData;
  runId: string;
  stageRun?: ModelEnsembleRun | null;
  transport: Pick<PromptEnhancerTransport, "getModelPredictiveMetricDetail">;
  lensId: ModelEnsembleLensId;
  onLensChange: (lens: ModelEnsembleLensId) => void;
  snapshotLabel: string;
  comparisonRun?: ModelEnsembleRadarData | null;
  comparisonLabel?: string;
  scopeLabel?: string;
  history?: MetricWorkspaceHistory;
  attemptStages?: readonly ModelEnsembleAttemptStage[];
}) {
  const [selectedMetricKey, setSelectedMetricKey] = useState("");
  const axes = useMemo(() => modelEnsembleRadarAxes(run, lensId), [lensId, run]);
  const known = run.typed_metrics.filter((metric) => metric.value_state === "known").length;
  const pending = run.typed_metrics.filter((metric) => modelEnsembleMetricStatus(metric) === "pending").length;
  const unavailable = run.typed_metrics.filter((metric) => metric.value_state !== "known").length;
  const experimental = (run.predictive_metrics ?? []).filter((metric) => metric.state === "experimental").length;
  const activeMetricKey = axes.some((axis) => axis.key === selectedMetricKey)
    ? selectedMetricKey
    : axes[0]?.key ?? "";
  const activeDirection = axes.find((axis) => axis.key === activeMetricKey)?.direction ?? "higher_is_better";
  const activeLens = MODEL_ENSEMBLE_LENSES.find((lens) => lens.id === lensId);
  return (
    <section
      aria-label={`Metric workspace · ${snapshotLabel}`}
      className={`metric-workspace metric-workspace--${mode}`}
      data-run-id={runId}
      data-workspace-mode={mode}
    >
      <header className="metric-workspace__snapshot">
        <div><span>{snapshotLabel}{pending > 0 ? ` · ${pending} pending` : ""}</span><strong>Snapshot {shortIdentity(runId)}</strong></div>
        <dl>
          <div><dt>Measured</dt><dd>{known}/20</dd></div>
          <div><dt>State-only</dt><dd>{unavailable}</dd></div>
          <div><dt>Experimental</dt><dd>{experimental}/20</dd></div>
          <div><dt>Window</dt><dd>{scopeLabel}</dd></div>
        </dl>
      </header>
      <nav
        aria-label="Metric workspace view"
        className="metric-workspace__lenses"
        onKeyDown={(event) => moveRovingFocus(event, (index) => onLensChange(MODEL_ENSEMBLE_LENSES[index].id))}
      >
        {MODEL_ENSEMBLE_LENSES.map((lens) => (
          <button
            aria-label={`${lens.label} lens · ${lens.expectedMetricCount} metrics`}
            aria-pressed={lens.id === lensId}
            key={lens.id}
            onClick={() => onLensChange(lens.id)}
            type="button"
          >
            <span aria-hidden="true">{lens.shortLabel}</span><small aria-hidden="true">{lens.expectedMetricCount} metrics</small>
          </button>
        ))}
      </nav>
      <div className="metric-workspace__primary">
        <ModelEnsembleRadar
          compact={mode === "compact"}
          comparisonLabel={comparisonLabel}
          comparisonRun={comparisonRun}
          detailRunId={runId}
          detailTransport={transport}
          lensId={lensId}
          onSelectedMetricKeyChange={setSelectedMetricKey}
          run={run}
          selectedMetricKey={activeMetricKey}
          snapshotLabel={snapshotLabel}
        />
        {mode === "full" && (
          <section aria-label="Exact metric values" className="metric-workspace__board">
            <header><strong>{activeLens?.label}</strong><span>Exact states and next actions</span></header>
            <div onKeyDown={(event) => moveRovingFocus(event, (index) => setSelectedMetricKey(axes[index].key))}>
              {axes.map((axis) => {
                const presentation = axis.metric === null
                  ? { value: "—", detail: "No sealed receipt." }
                  : modelEnsembleMetricPresentation(axis.metric, axis.direction);
                const status = modelEnsembleMetricStatus(axis.metric);
                const guidance = sessionMetricGuidance(axis.key, {
                  state: axis.metric?.value_state ?? "missing",
                  numericValue: axis.metric?.numeric_value ?? null,
                  direction: axis.direction,
                  explanationCode: axis.metric !== null && "projection_source" in axis.metric ? axis.metric.explanation_code : null,
                });
                return (
                  <button
                    aria-pressed={axis.key === activeMetricKey}
                    data-status={status}
                    key={axis.key}
                    onClick={() => setSelectedMetricKey(axis.key)}
                    type="button"
                  >
                    <span>
                      <strong>{axis.label}</strong>
                      <small>
                        {modelEnsembleMetricStatusLabel(status)}
                        {axis.direction === "lower_is_better" && axis.metric?.value_state === "known" && axis.metric.numeric_value != null
                          ? ` · raw rate ${Math.round(axis.metric.numeric_value! * 100)}%`
                          : ""}
                      </small>
                    </span>
                    <b>{presentation.value}</b>
                    <p>{guidance.action}</p>
                  </button>
                );
              })}
            </div>
          </section>
        )}
      </div>
      <p aria-hidden={comparisonRun === null} className="metric-workspace__comparison-note">
        {comparisonRun === null ? "\u00a0" : "Dashed geometry is the immediately preceding comparable publication."}
      </p>
      <div className="metric-workspace__drawers">
        <ModelConstellation attemptStages={attemptStages} compact={mode === "compact"} run={stageRun} />
        <HistoryDrawer
          direction={activeDirection}
          history={activeMetricKey === "" ? undefined : history}
          metricKey={activeMetricKey}
        />
      </div>
    </section>
  );
}
