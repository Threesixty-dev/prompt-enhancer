import { useMemo, useState } from "react";
import type {
  ModelEnsembleRun,
  ModelEnsembleAttemptStage,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { moveRovingFocus } from "../../shared/ui/rovingFocus";
import { sessionMetricGuidance } from "../quality-profile/metricGuidance";
import {
  MetricKnowledgeCardSlot,
  metricKnowledgeCardTriggerProps,
  useMetricKnowledgeCardController,
} from "./MetricKnowledgeCard";
import { MetricHistoryDrawer, type MetricWorkspaceHistory } from "./MetricHistoryDrawer";
import { ModelConstellationDrawer } from "./ModelConstellationDrawer";
import { ModelEnsembleRadar } from "./ModelEnsembleRadar";
import {
  MODEL_ENSEMBLE_LENSES,
  modelEnsembleAxisEvidence,
  modelEnsembleAxisRawRateLabel,
  modelEnsembleKnowledgeEntries,
  modelEnsembleMetricPresentation,
  modelEnsemblePrimaryMetrics,
  modelEnsembleCompletedSmallExperts,
  modelEnsembleMetricStatus,
  modelEnsembleMetricStatusLabel,
  modelEnsemblePredictiveVisibility,
  modelEnsembleRadarAxes,
  type ModelEnsembleLensId,
  type ModelEnsembleRadarData,
} from "./metricAxisModel";
import { shortIdentity } from "./modelStages";

/**
 * The trajectory helpers and the history contract used to live in this file.
 * They are re-exported so existing imports keep working; new code should import
 * `./trajectorySelection` and `./MetricHistoryDrawer` directly.
 */
export {
  modelEnsembleHistoryRadarValue,
  modelEnsembleTrajectoryRadarData,
} from "./trajectorySelection";
export type { MetricWorkspaceHistory } from "./MetricHistoryDrawer";

/** U+00A0: keeps the comparison note's line box when no comparison is shown, without visible text. */
const NON_BREAKING_SPACE = String.fromCharCode(0xa0);

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
  const boardHelp = useMetricKnowledgeCardController();
  const axes = useMemo(() => modelEnsembleRadarAxes(run, lensId), [lensId, run]);
  const primaryMetrics = useMemo(() => modelEnsemblePrimaryMetrics(run), [run]);
  const known = primaryMetrics.filter((metric) => metric.value_state === "known").length;
  const pending = primaryMetrics.filter((metric) => modelEnsembleMetricStatus(metric) === "pending").length;
  const unavailable = primaryMetrics.filter((metric) => metric.value_state !== "known").length;
  const completedSmallExperts = modelEnsembleCompletedSmallExperts(run);
  const visibleExperimental = (run.predictive_metrics ?? []).filter(
    (metric) => modelEnsemblePredictiveVisibility(metric, completedSmallExperts).visible,
  ).length;
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
          <div><dt>Visible estimates</dt><dd>{visibleExperimental}/20</dd></div>
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
          helpController={boardHelp}
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
                const rawRate = modelEnsembleAxisRawRateLabel(axis);
                const evidence = modelEnsembleAxisEvidence(axis);
                const guidance = sessionMetricGuidance(axis.key, {
                  state: evidence.state,
                  numericValue: evidence.numericValue,
                  direction: axis.direction,
                  explanationCode: evidence.explanationCode,
                });
                return (
                  <button
                    aria-pressed={axis.key === activeMetricKey}
                    data-status={status}
                    key={axis.key}
                    {...metricKnowledgeCardTriggerProps(boardHelp, "board", axis.key)}
                    onClick={() => { setSelectedMetricKey(axis.key); boardHelp.togglePin({ surface: "board", metricKey: axis.key }); }}
                    type="button"
                  >
                    <span>
                      <strong>{axis.label}</strong>
                      <small>
                        {modelEnsembleMetricStatusLabel(status)}
                        {rawRate === null ? "" : ` · ${rawRate}`}
                      </small>
                    </span>
                    <b>{presentation.value}</b>
                    <p>{guidance.action}</p>
                  </button>
                );
              })}
            </div>
            <MetricKnowledgeCardSlot
              controller={boardHelp}
              entries={modelEnsembleKnowledgeEntries(axes)}
              surface="board"
            />
          </section>
        )}
      </div>
      <p aria-hidden={comparisonRun === null} className="metric-workspace__comparison-note">
        {comparisonRun === null ? NON_BREAKING_SPACE : "Dashed geometry is the immediately preceding comparable publication."}
      </p>
      <div className="metric-workspace__drawers">
        <ModelConstellationDrawer attemptStages={attemptStages} compact={mode === "compact"} run={stageRun} />
        <MetricHistoryDrawer
          direction={activeDirection}
          history={activeMetricKey === "" ? undefined : history}
          metricKey={activeMetricKey}
        />
      </div>
    </section>
  );
}
