import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ModelEnsembleTrajectoryPoint } from "../../shared/api/contracts";
import { MetricHistoryDrawer } from "./MetricHistoryDrawer";
import { MetricWorkspace, type MetricWorkspaceHistory } from "./MetricWorkspace";

const METRIC = "prompt.task_definition_coverage";

function point(runId: string, generation: number, value: number | null, comparable = true): ModelEnsembleTrajectoryPoint {
  return {
    generation,
    run_id: runId,
    published_at: `2040-01-0${generation}T10:00:01Z`,
    completed_at: `2040-01-0${generation}T10:00:00Z`,
    max_messages: 100,
    source_coverage_state: "complete_window",
    chunk_count: 1,
    comparable_to_head: comparable,
    metrics: [],
    typed_metrics: value === null
      ? [{ metric_key: METRIC, value_state: "unknown", numeric_value: null }]
      : [{ metric_key: METRIC, value_state: "known", numeric_value: value }],
    predictive_metrics: [],
  } as unknown as ModelEnsembleTrajectoryPoint;
}

describe("MetricHistoryDrawer", () => {
  it("states that history is not exposed instead of drawing an empty chart", () => {
    render(<MetricHistoryDrawer direction="higher_is_better" metricKey={METRIC} />);
    expect(screen.getByText("History").parentElement).toHaveTextContent("Not exposed for this receipt");
    expect(screen.getByText(/content-free trajectory/i)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Selected metric history" })).not.toBeInTheDocument();
  });

  it("renders sealed snapshots with exact head labelling, comparability, and selection state", () => {
    const onSelectRun = vi.fn();
    const points = [
      point("9".repeat(64), 4, 1),
      point("8".repeat(64), 3, null),
      point("7".repeat(64), 2, 0.5, false),
    ];
    const history: MetricWorkspaceHistory = {
      points,
      headRunId: points[0].run_id,
      selectedRunId: points[2].run_id,
      onSelectRun,
      error: true,
    };
    render(<MetricHistoryDrawer direction="higher_is_better" history={history} metricKey={METRIC} />);

    expect(screen.getByText("History").parentElement).toHaveTextContent("3 sealed snapshots");
    fireEvent.click(screen.getByText("History"));
    expect(screen.getByText("History").closest("details")).toHaveAttribute("open");
    expect(screen.getByRole("status")).toHaveTextContent(/refresh is delayed/i);
    const chart = screen.getByRole("img", { name: "Selected metric history" });
    // Baseline only: the unknown middle point breaks every segment, and the scope break never connects.
    expect(chart.querySelectorAll("line")).toHaveLength(1);
    expect(chart.querySelectorAll("circle")).toHaveLength(2);
    expect(chart.querySelectorAll("circle.is-selected")).toHaveLength(1);

    const live = screen.getByRole("button", { name: "Open live snapshot" });
    const earlier = screen.getByRole("button", { name: "Open earlier snapshot 3" });
    expect(live).toHaveAttribute("aria-pressed", "false");
    expect(earlier).toHaveAttribute("aria-pressed", "true");
    expect(live).toHaveTextContent("Live");
    expect(live).toHaveTextContent("comparable");
    expect(earlier).toHaveTextContent("#3");
    expect(earlier).toHaveTextContent("scope break");
    fireEvent.click(screen.getByRole("button", { name: "Open earlier snapshot 2" }));
    expect(onSelectRun).toHaveBeenCalledWith(points[1].run_id);
  });

  it("keeps the same drawer contract in full and compact workspaces", () => {
    const points = [point("9".repeat(64), 2, 0.75), point("8".repeat(64), 1, 0.25)];
    const history: MetricWorkspaceHistory = { points, headRunId: points[0].run_id, selectedRunId: points[0].run_id, onSelectRun: vi.fn() };
    const run = { metrics: [], chunk_metrics: [], typed_metrics: [], predictive_metrics: [] };
    const transport = { getModelPredictiveMetricDetail: vi.fn(() => new Promise<never>(() => undefined)) };
    const view = render(
      <MetricWorkspace history={history} lensId="task-framing" mode="full" onLensChange={vi.fn()} run={run} runId={points[0].run_id} snapshotLabel="Synthetic" transport={transport} />,
    );
    const fullSummary = screen.getByText("History").parentElement?.textContent;
    const fullButtons = [...document.querySelectorAll(".metric-history__snapshots button")].map((button) => button.getAttribute("aria-label"));
    view.unmount();
    render(
      <MetricWorkspace history={history} lensId="task-framing" mode="compact" onLensChange={vi.fn()} run={run} runId={points[0].run_id} snapshotLabel="Synthetic" transport={transport} />,
    );
    expect(screen.getByText("History").parentElement?.textContent).toBe(fullSummary);
    expect([...document.querySelectorAll(".metric-history__snapshots button")].map((button) => button.getAttribute("aria-label"))).toEqual(fullButtons);
    expect(fullButtons).toEqual(["Open live snapshot", "Open earlier snapshot 2"]);
  });
});
