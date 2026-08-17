import { useEffect, useState } from "react";
import type {
  ModelEnsembleRun,
  ModelEnsembleTrajectoryPoint,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { resolveTrajectorySelection, type TrajectorySelection } from "./trajectorySelection";

/**
 * Loads the immutable snapshot for an earlier selected history point. The
 * displayed run is cleared while loading, admitted only when its run id equals
 * the requested id, and dropped again on failure; the aggregate-only trajectory
 * point remains the fallback for the caller.
 */
export function useHistoricalRun(
  transport: Pick<PromptEnhancerTransport, "getModelEnsembleSnapshot">,
  historicalRunId: string | null,
): ModelEnsembleRun | null {
  const [historicalRun, setHistoricalRun] = useState<ModelEnsembleRun | null>(null);
  useEffect(() => {
    if (historicalRunId === null || transport.getModelEnsembleSnapshot === undefined) {
      setHistoricalRun(null);
      return;
    }
    const controller = new AbortController();
    setHistoricalRun(null);
    transport.getModelEnsembleSnapshot(historicalRunId, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted && value.run_id === historicalRunId) setHistoricalRun(value);
      })
      .catch(() => { if (!controller.signal.aborted) setHistoricalRun(null); });
    return () => controller.abort();
  }, [historicalRunId, transport]);
  return historicalRun;
}

export interface UseTrajectorySelectionInput {
  transport: Pick<PromptEnhancerTransport, "getModelEnsembleSnapshot">;
  /** Visible trajectory points, newest first (empty when no trajectory is shown). */
  points: readonly ModelEnsembleTrajectoryPoint[];
  selectedRunId: string | null;
  /** The exact sealed head run currently loaded for this surface, if any. */
  headRun: ModelEnsembleRun | null;
}

export interface UseTrajectorySelectionResult extends TrajectorySelection {
  /** The exact snapshot loaded for the selected earlier point, when it is not the head. */
  historicalRun: ModelEnsembleRun | null;
}

/**
 * Head/history reconciliation shared by the session panel and the live overlay:
 * resolves which point is selected, loads its exact snapshot when it is not the
 * head, and derives the radar data plus the comparable prior publication.
 */
export function useTrajectorySelection({
  transport,
  points,
  selectedRunId,
  headRun,
}: UseTrajectorySelectionInput): UseTrajectorySelectionResult {
  const selectedPointIndex = points.findIndex((point) => point.run_id === selectedRunId);
  const selectedPoint = selectedPointIndex < 0 ? null : points[selectedPointIndex];
  const historicalRunId = selectedPoint !== null && selectedPoint.run_id !== headRun?.run_id
    ? selectedPoint.run_id
    : null;
  const historicalRun = useHistoricalRun(transport, historicalRunId);
  return {
    ...resolveTrajectorySelection({ points, selectedRunId, headRun, historicalRun }),
    historicalRun,
  };
}
