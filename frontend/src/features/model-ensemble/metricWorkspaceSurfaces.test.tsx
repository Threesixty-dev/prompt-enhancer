import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ModelEnsembleRun } from "../../shared/api/contracts";
import { MetricWorkspace } from "./MetricWorkspace";
import {
  modelEnsembleAxisPlottedLabel,
  modelEnsembleAxisRawRateLabel,
  modelEnsembleMetricStateLabel,
  modelEnsembleRadarAxes,
  type ModelEnsembleRadarData,
} from "./metricAxisModel";

type TypedMetric = ModelEnsembleRun["typed_metrics"][number];

function typedMetric(metricKey: string, patch: Partial<TypedMetric>): TypedMetric {
  return {
    metric_key: metricKey,
    value_state: "known",
    numeric_value: 0.5,
    numerator: 1,
    denominator: 2,
    coverage: 1,
    observed_message_count: 2,
    eligible_message_count: 2,
    projection_source: "deterministic_typed_contract",
    explanation_code: "typed_requirement_ratio",
    ...patch,
  } as unknown as TypedMetric;
}

const run: ModelEnsembleRadarData = {
  metrics: [],
  chunk_metrics: [],
  typed_metrics: [
    typedMetric("collaboration.ambiguity_resolution", { numeric_value: 0.25, numerator: 1, denominator: 4 }),
    typedMetric("collaboration.clarification_yield", { value_state: "unknown", numeric_value: null, numerator: null, denominator: null, explanation_code: "episode_horizon_open" }),
    typedMetric("collaboration.exploration_conversion", { value_state: "not_applicable", numeric_value: null, numerator: null, denominator: null }),
    typedMetric("collaboration.rework_candidate_rate", { numeric_value: 0.02, numerator: 2, denominator: 100 }),
  ],
  predictive_metrics: [],
};

const transport = { getModelPredictiveMetricDetail: vi.fn(() => new Promise<never>(() => undefined)) };

describe("metric workspace surfaces share one axis presentation", () => {
  it("renders identical status and raw-rate captions on the axis strip and the exact-value board", () => {
    render(
      <MetricWorkspace lensId="collaboration-flow" mode="full" onLensChange={vi.fn()} run={run} runId={"e".repeat(64)} snapshotLabel="Synthetic" transport={transport} />,
    );
    const axes = modelEnsembleRadarAxes(run, "collaboration-flow");
    const strip = within(screen.getByRole("navigation", { name: "Collaboration flow metric axes" })).getAllByRole("button");
    const board = within(screen.getByRole("region", { name: "Exact metric values" })).getAllByRole("button");
    expect(strip).toHaveLength(axes.length);
    expect(board).toHaveLength(axes.length);

    axes.forEach((axis, index) => {
      const rawRate = modelEnsembleAxisRawRateLabel(axis);
      const stripValue = strip[index].querySelector("b")?.textContent;
      const stripSmalls = [...strip[index].querySelectorAll("small")].map((node) => node.textContent);
      const boardStatus = board[index].querySelector("small")?.textContent;
      expect(stripValue).toBe(modelEnsembleAxisPlottedLabel(axis));
      expect(strip[index]).toHaveClass(`is-${axis.metric === null ? "missing" : axis.metric.value_state === "unknown" && axis.metric.explanation_code === "episode_horizon_open" ? "pending" : axis.metric.value_state}`);
      const expectedStatus = modelEnsembleMetricStateLabel(axis.metric);
      expect(boardStatus).toBe(rawRate === null ? expectedStatus : `${expectedStatus} · ${rawRate}`);
      if (rawRate === null) {
        expect(stripSmalls.some((text) => text?.startsWith("raw rate"))).toBe(false);
      } else {
        expect(stripSmalls).toContain(rawRate);
      }
      expect(strip[index].getAttribute("aria-describedby")).toBe(board[index].getAttribute("aria-describedby"));
    });

    const rework = axes.findIndex((axis) => axis.key === "collaboration.rework_candidate_rate");
    expect(strip[rework].querySelector("b")?.textContent).toBe("98% radar quality");
    expect(board[rework].querySelector("small")?.textContent).toBe("known · raw rate 2%");
    expect(board[rework].querySelector("b")?.textContent).toBe("98% radar quality");
    const pending = axes.findIndex((axis) => axis.key === "collaboration.clarification_yield");
    expect(strip[pending].querySelector("b")?.textContent).toBe("Pending");
    expect(board[pending].querySelector("small")?.textContent).toBe("pending · horizon open");
    expect(board[pending].querySelector("b")?.textContent).toBe("Pending");
    const missing = axes.findIndex((axis) => axis.key === "collaboration.scope_change_discipline");
    expect(strip[missing].querySelector("b")?.textContent).toBe("No record");
    expect(board[missing].querySelector("b")?.textContent).toBe("—");
    expect(board[missing].querySelector("small")?.textContent).toBe("not observed");
  });
});
