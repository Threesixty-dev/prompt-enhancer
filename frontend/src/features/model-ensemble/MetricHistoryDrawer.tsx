import type { ModelEnsembleTrajectoryPoint } from "../../shared/api/contracts";
import type { ModelEnsembleMetricDirection } from "./metricAxisModel";
import { metricHistoryPlot } from "./trajectorySelection";

/**
 * Sealed-snapshot history for the selected metric. The drawer is a plain
 * `<details>` disclosure so its open state survives receipt refreshes, and the
 * sparkline is presentation-only: geometry comes from `metricHistoryPlot`.
 */
export interface MetricWorkspaceHistory {
  points: readonly ModelEnsembleTrajectoryPoint[];
  headRunId: string | null;
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
  error?: boolean;
}

export function MetricHistoryDrawer({ history, metricKey, direction }: {
  history?: MetricWorkspaceHistory;
  metricKey: string;
  direction: ModelEnsembleMetricDirection;
}) {
  const { chronological, coordinates, segments } = metricHistoryPlot(history?.points ?? [], metricKey, direction);
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
