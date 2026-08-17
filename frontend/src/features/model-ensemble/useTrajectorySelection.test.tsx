import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ModelEnsembleRun, ModelEnsembleTrajectoryPoint } from "../../shared/api/contracts";
import { modelEnsembleTrajectoryRadarData } from "./trajectorySelection";
import { useTrajectorySelection, type UseTrajectorySelectionResult } from "./useTrajectorySelection";

function point(runId: string, generation: number): ModelEnsembleTrajectoryPoint {
  return {
    generation,
    run_id: runId,
    published_at: `2040-01-0${generation}T10:00:01Z`,
    completed_at: `2040-01-0${generation}T10:00:00Z`,
    max_messages: 100,
    source_coverage_state: "complete_window",
    chunk_count: 1,
    comparable_to_head: true,
    metrics: [],
    typed_metrics: [],
    predictive_metrics: [],
  } as unknown as ModelEnsembleTrajectoryPoint;
}

function sealedRun(runId: string): ModelEnsembleRun {
  return { run_id: runId, metrics: [], typed_metrics: [], chunk_metrics: [], predictive_metrics: [] } as unknown as ModelEnsembleRun;
}

/** Mirrors the hook's `selectedRunId: string | null` so `rerender` may follow the head (null) again. */
type SelectionProps = { selectedRunId: string | null };

describe("useTrajectorySelection", () => {
  const head = sealedRun("9".repeat(64));
  const older = sealedRun("8".repeat(64));
  const points = [point(head.run_id, 2), point(older.run_id, 1)];

  it("does not fetch while following the exact head and fetches only the selected earlier snapshot", async () => {
    const getModelEnsembleSnapshot = vi.fn(async (runId: string) => runId === older.run_id ? older : head);
    const transport = { getModelEnsembleSnapshot };
    const initialProps: SelectionProps = { selectedRunId: head.run_id };
    const { result, rerender } = renderHook<UseTrajectorySelectionResult, SelectionProps>(
      ({ selectedRunId }) => useTrajectorySelection({ transport, points, selectedRunId, headRun: head }),
      { initialProps },
    );
    expect(result.current.selectedRadarRun).toBe(head);
    expect(result.current.historicalRun).toBeNull();
    expect(result.current.comparisonRadarRun).toEqual(modelEnsembleTrajectoryRadarData(points[1]));
    expect(getModelEnsembleSnapshot).not.toHaveBeenCalled();

    rerender({ selectedRunId: older.run_id });
    expect(result.current.historicalRunId).toBe(older.run_id);
    expect(result.current.selectedRadarRun).toEqual(modelEnsembleTrajectoryRadarData(points[1]));
    await waitFor(() => expect(result.current.historicalRun).toBe(older));
    expect(result.current.selectedRadarRun).toBe(older);
    expect(getModelEnsembleSnapshot).toHaveBeenCalledTimes(1);
    expect(getModelEnsembleSnapshot).toHaveBeenCalledWith(older.run_id, expect.any(AbortSignal));

    rerender({ selectedRunId: head.run_id });
    expect(result.current.historicalRun).toBeNull();
    expect(result.current.selectedRadarRun).toBe(head);
  });

  it("refuses a snapshot whose run id differs from the requested id and tolerates missing transport support", async () => {
    const wrong = vi.fn(async () => head);
    const wrongTransport = { getModelEnsembleSnapshot: wrong };
    const { result } = renderHook(() =>
      useTrajectorySelection({ transport: wrongTransport, points, selectedRunId: older.run_id, headRun: head }));
    await waitFor(() => expect(wrong).toHaveBeenCalledTimes(1));
    await Promise.resolve();
    expect(result.current.historicalRun).toBeNull();
    expect(result.current.selectedRadarRun).toEqual(modelEnsembleTrajectoryRadarData(points[1]));

    const noSnapshotTransport = {};
    const unsupported = renderHook(() =>
      useTrajectorySelection({ transport: noSnapshotTransport, points, selectedRunId: older.run_id, headRun: head }));
    expect(unsupported.result.current.historicalRun).toBeNull();
    expect(unsupported.result.current.selectedRadarRun).toEqual(modelEnsembleTrajectoryRadarData(points[1]));
  });
});
