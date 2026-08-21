import { useMemo, useState } from "react";
import type {
  ModelEnsembleRun,
  ModelEnsembleAttemptStage,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { moveRovingFocus } from "../../shared/ui/rovingFocus";
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
  MODEL_ENSEMBLE_OBJECTIVE_CONTRACT_COUNT,
  modelEnsembleAxisGuidanceSentences,
  modelEnsembleAxisPendingBoundsLabel,
  modelEnsembleAxisRawRateLabel,
  modelEnsembleKnowledgeEntries,
  modelEnsembleMetricPresentation,
  modelEnsembleObjectiveMeasurableCount,
  modelEnsembleObjectiveMeasuredCount,
  modelEnsemblePrimaryMetrics,
  modelEnsembleCompletedSmallExperts,
  modelEnsembleMetricStatus,
  modelEnsembleMetricStatusLabel,
  modelEnsemblePredictiveVisibility,
  modelEnsembleRadarAxes,
  type ModelEnsembleLensId,
  type ModelEnsembleRadarData,
} from "./metricAxisModel";
import { ME_SCOPE_CONTEXT, type MetricScopeContext } from "./metricContextFacts";
import { shortIdentity } from "./modelStages";
import { metricEvidenceReadinessForPublication } from "./metricEvidenceReadiness";
import { MetricEvidenceFilePanel } from "./MetricEvidenceFilePanel";

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

export function metricEvidenceFileProjectionSupported(
  projectionVersion: string | undefined,
): boolean {
  return projectionVersion === "metric-contract-v2-projection-4"
    || projectionVersion === "metric-contract-v2-projection-5";
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
  scopeContext,
  evidenceSessionId,
  evidenceEnabled = false,
  onEvidenceChanged,
}: {
  mode: "full" | "compact";
  run: ModelEnsembleRadarData;
  runId: string;
  stageRun?: ModelEnsembleRun | null;
  transport: Pick<PromptEnhancerTransport,
    | "getModelPredictiveMetricDetail"
    | "previewAgentMetricEvidence"
    | "importAgentMetricEvidence"
    | "listMetricLifecycleProposals"
    | "decideMetricLifecycleProposal">
    & Partial<Pick<PromptEnhancerTransport, "getUserPresenceCapability">>;
  lensId: ModelEnsembleLensId;
  onLensChange: (lens: ModelEnsembleLensId) => void;
  snapshotLabel: string;
  comparisonRun?: ModelEnsembleRadarData | null;
  comparisonLabel?: string;
  scopeLabel?: string;
  history?: MetricWorkspaceHistory;
  attemptStages?: readonly ModelEnsembleAttemptStage[];
  /** Analytics scope carried into every knowledge card (strip and board); defaults to Me. */
  scopeContext?: MetricScopeContext;
  evidenceSessionId?: string;
  evidenceEnabled?: boolean;
  onEvidenceChanged?: () => void;
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
  const objectiveMeasured = modelEnsembleObjectiveMeasuredCount(run);
  // Derived from the sealed states themselves (capability_available on the five
  // objective contracts), so the header stays truthful with or without the
  // additive readiness projection; the projection can only restate this count.
  const objectiveMeasurable = modelEnsembleObjectiveMeasurableCount(run);
  const evidenceReadiness = useMemo(
    () => metricEvidenceReadinessForPublication(run.metric_evidence_readiness_v2, run.metric_publication_v2),
    [run.metric_evidence_readiness_v2, run.metric_publication_v2],
  );
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
        <div><span>{snapshotLabel}{pending > 0 ? ` · ${pending} pending` : ""}</span><strong>Snapshot {shortIdentity(runId)}</strong><span className="metric-workspace__scope" data-scope={(scopeContext ?? ME_SCOPE_CONTEXT).scope}>Scope · {(scopeContext ?? ME_SCOPE_CONTEXT).label}</span></div>
        <dl>
          <div><dt>Measured</dt><dd>{known}/20</dd></div>
          {objectiveMeasurable !== null && (
            <div data-objective-measurable={objectiveMeasurable}>
              <dt>Objective measurable</dt>
              <dd>{objectiveMeasurable}/{MODEL_ENSEMBLE_OBJECTIVE_CONTRACT_COUNT}</dd>
            </div>
          )}
          {objectiveMeasured !== null && (
            <div data-objective-measured={objectiveMeasured}>
              <dt>Objective measured</dt>
              <dd>{objectiveMeasured}/{MODEL_ENSEMBLE_OBJECTIVE_CONTRACT_COUNT}</dd>
            </div>
          )}
          <div><dt>State-only</dt><dd>{unavailable}</dd></div>
          {evidenceReadiness !== null && (
            <div data-capability-gaps={evidenceReadiness.capability_missing_count}>
              <dt>Capability gaps</dt><dd>{evidenceReadiness.capability_missing_count}/20</dd>
            </div>
          )}
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
          scopeContext={scopeContext}
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
                const pendingBounds = modelEnsembleAxisPendingBoundsLabel(axis);
                // The same two sentences the radar inspector and knowledge card
                // render: the action here can never differ from the inspector's.
                const guidance = modelEnsembleAxisGuidanceSentences(axis);
                return (
                  <button
                    aria-pressed={axis.key === activeMetricKey}
                    data-guidance-kind={guidance.kind}
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
                        {pendingBounds === null ? "" : ` · ${pendingBounds}`}
                      </small>
                    </span>
                    <b>{presentation.value}</b>
                    <span aria-hidden="true" className="metric-workspace__board-action">{guidance.action}</span>
                  </button>
                );
              })}
            </div>
            <MetricKnowledgeCardSlot
              controller={boardHelp}
              entries={modelEnsembleKnowledgeEntries(axes, scopeContext)}
              surface="board"
            />
          </section>
        )}
      </div>
      {evidenceEnabled
        && evidenceSessionId !== undefined
        && metricEvidenceFileProjectionSupported(run.metric_publication_v2?.projection_version)
        && (
          <MetricEvidenceFilePanel
            compact={mode === "compact"}
            onEvidenceChanged={onEvidenceChanged}
            sessionId={evidenceSessionId}
            sourceRunId={runId}
            transport={transport}
          />
        )}
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
