import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  AnalysisRun,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import {
  SYNTHETIC_RESULTS,
  SYNTHETIC_RUN,
} from "../../shared/api/syntheticFixtures";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { TaskDetail } from "./TaskDetail";

describe("TaskDetail analysis lifecycle", () => {
  it("can append a latest-pack run without replacing an existing run", async () => {
    const base = createSyntheticTransport();
    const oldRun: AnalysisRun = {
      ...SYNTHETIC_RUN,
      metric_pack_version: 2,
    };
    const currentRun: AnalysisRun = {
      ...SYNTHETIC_RUN,
      run_id: "a".repeat(64),
      metric_pack_version: 3,
      metric_engine_version: "task-deterministic-2",
      schema_version: 6,
      started_at: "2040-01-03T12:00:00Z",
      finished_at: "2040-01-03T12:00:02Z",
    };
    let latestPackStarted = false;
    const startAnalysis = vi.fn(async () => {
      latestPackStarted = true;
      return {
        run_id: currentRun.run_id,
        status: "completed" as const,
        result_count: SYNTHETIC_RESULTS.length,
        applied: true,
      };
    });
    const transport: PromptEnhancerTransport = {
      ...base,
      listAnalysisRuns: vi.fn(async () => ({
        runs: latestPackStarted ? [currentRun, oldRun] : [oldRun],
        limit: 100,
        offset: 0,
      })),
      getAnalysisRun: vi.fn(async (runId) => ({
        run: runId === currentRun.run_id ? currentRun : oldRun,
        results: SYNTHETIC_RESULTS,
      })),
      startAnalysis,
    };

    render(
      <TaskDetail
        navigate={vi.fn()}
        revision={oldRun.task_revision}
        taskId={oldRun.task_id}
        transport={transport}
      />,
    );

    expect(await screen.findByText("Core Metadata Task - v2")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Run latest pack" }));

    expect(await screen.findByText("Core Metadata Task - v3")).toBeVisible();
    expect(startAnalysis).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Core Metadata Task - v2")).not.toBeInTheDocument();
  });
});
