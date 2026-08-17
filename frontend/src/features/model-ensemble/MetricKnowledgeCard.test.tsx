import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModelEnsembleRun, PromptEnhancerTransport } from "../../shared/api/contracts";
import { MetricWorkspace } from "./MetricWorkspace";
import { ModelEnsembleRadar, type ModelEnsembleRadarData } from "./ModelEnsembleRadar";

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
    projection_source: "example-projection",
    explanation_code: null,
    ...patch,
  } as unknown as TypedMetric;
}

const run: ModelEnsembleRadarData = {
  metrics: [],
  chunk_metrics: [],
  typed_metrics: [
    typedMetric("prompt.task_definition_coverage", { numeric_value: 0.5, numerator: 1, denominator: 2 }),
    typedMetric("prompt.problem_evidence_quality", { value_state: "unknown", numeric_value: null, numerator: null, denominator: null }),
    typedMetric("prompt.context_sufficiency", { value_state: "not_applicable", numeric_value: null, numerator: null, denominator: null }),
    typedMetric("prompt.constraint_precision", { value_state: "unknown", numeric_value: null, numerator: null, denominator: null, explanation_code: "episode_horizon_open" }),
    typedMetric("prompt.acceptance_testability", { value_state: "abstained", numeric_value: null, numerator: null, denominator: null }),
    typedMetric("prompt.deliverable_contract", { numeric_value: 0, numerator: 0, denominator: 3 }),
  ],
  predictive_metrics: [],
};

const transport = {
  getModelPredictiveMetricDetail: vi.fn(() => new Promise(() => undefined)),
} as unknown as Pick<PromptEnhancerTransport, "getModelPredictiveMetricDetail">;

function renderWorkspace(mode: "full" | "compact") {
  return render(
    <MetricWorkspace
      lensId="task-framing"
      mode={mode}
      onLensChange={() => undefined}
      run={run}
      runId="example-run-0001"
      snapshotLabel="Synthetic snapshot"
      transport={transport}
    />,
  );
}

afterEach(() => {
  vi.useRealTimers();
});

describe("metric knowledge cards", () => {
  it("keeps the radar SVG presentation-only", () => {
    renderWorkspace("full");
    const svg = document.querySelector(".model-ensemble__radar svg")!;
    expect(svg.querySelectorAll("[role], [tabindex], a, button, foreignObject")).toHaveLength(0);
    expect(document.querySelectorAll(".model-ensemble__radar-state").length).toBeGreaterThan(0);
  });

  it("shows exactly one visible card across strip and board surfaces with pointer, focus, pin, and Escape", () => {
    vi.useFakeTimers();
    renderWorkspace("full");
    const cards = () => document.querySelectorAll('[role="tooltip"]');
    expect(cards()).toHaveLength(0);
    const strip = screen.getByRole("navigation", { name: /metric axes/ });
    const stripButtons = strip.querySelectorAll("button");
    const board = screen.getByRole("region", { name: "Exact metric values" });
    const boardButtons = board.querySelectorAll("button");
    for (const button of [...stripButtons, ...boardButtons]) {
      const description = document.getElementById(button.getAttribute("aria-describedby")!);
      expect(description?.textContent).toMatch(/: /);
    }
    fireEvent.pointerEnter(stripButtons[0]);
    expect(cards()).toHaveLength(1);
    expect(cards()[0].closest(".metric-knowledge-slot")?.getAttribute("data-surface")).toBe("strip");
    fireEvent.pointerEnter(boardButtons[1]);
    expect(cards()).toHaveLength(1);
    expect(cards()[0].closest(".metric-knowledge-slot")?.getAttribute("data-surface")).toBe("board");
    fireEvent.pointerLeave(boardButtons[1]);
    act(() => { vi.advanceTimersByTime(200); });
    expect(cards()).toHaveLength(0);
    fireEvent.focus(stripButtons[2]);
    expect(cards()).toHaveLength(1);
    fireEvent.click(stripButtons[2]);
    expect(cards()[0].getAttribute("data-pinned")).toBe("true");
    fireEvent.pointerEnter(boardButtons[0]);
    expect(cards()).toHaveLength(1);
    expect(cards()[0].getAttribute("data-metric-key")).toBe("prompt.context_sufficiency");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(cards()).toHaveLength(0);
    expect(document.querySelectorAll(".metric-knowledge-slot")).toHaveLength(2);
  });

  it("separates the current candidate definition from its shipped measurement method", () => {
    renderWorkspace("full");
    fireEvent.pointerEnter(screen.getByRole("navigation", { name: /metric axes/ }).querySelector("button")!);
    const card = document.querySelector('[role="tooltip"]')!;
    expect(card.textContent).toMatch(/Current local candidate definition\./);
    expect(card.textContent).toMatch(/Current measurement \(shipped definition v\d\)/);
    expect(card.textContent).not.toMatch(/confidence|probability of success/i);
  });

  it("renders the same two inspector sentences in full and compact mode for the same selection", () => {
    const full = renderWorkspace("full");
    fireEvent.click(screen.getByRole("navigation", { name: /metric axes/ }).querySelectorAll("button")[3]);
    const fullText = [...document.querySelectorAll(".metric-inspector-sentences p")].map((p) => p.textContent);
    expect(fullText).toHaveLength(2);
    expect(fullText[0]).toMatch(/Pending: the newest episode is still open/);
    expect(document.querySelectorAll(".model-ensemble__guidance")).toHaveLength(0);
    full.unmount();
    renderWorkspace("compact");
    fireEvent.click(screen.getByRole("navigation", { name: /metric axes/ }).querySelectorAll("button")[3]);
    const compactText = [...document.querySelectorAll(".metric-inspector-sentences p")].map((p) => p.textContent);
    expect(compactText).toEqual(fullText);
  });

  it("keeps a standalone radar working without a workspace controller", () => {
    render(<ModelEnsembleRadar lensId="task-framing" run={run} />);
    fireEvent.pointerEnter(screen.getByRole("navigation", { name: /metric axes/ }).querySelector("button")!);
    expect(document.querySelectorAll('[role="tooltip"]')).toHaveLength(1);
  });

  it("renders the compact card in a viewport overlay without inserting panel height", () => {
    renderWorkspace("compact");
    fireEvent.pointerEnter(screen.getByRole("navigation", { name: /metric axes/ }).querySelector("button")!);
    const card = document.querySelector('[role="tooltip"]')!;
    const slot = card.closest(".metric-knowledge-slot");
    expect(slot).not.toBeNull();
    expect(slot?.getAttribute("data-surface")).toBe("strip");
    expect(card.classList.contains("metric-knowledge-card--viewport")).toBe(true);
    expect(card.classList.contains("metric-knowledge-card--compact")).toBe(true);
  });

  it("dismisses a pinned key when a lens change makes that target unavailable", () => {
    const view = renderWorkspace("full");
    const first = screen.getByRole("navigation", { name: /metric axes/ }).querySelector("button")!;
    fireEvent.click(first);
    expect(document.querySelector('[role="tooltip"]')?.getAttribute("data-pinned")).toBe("true");

    view.rerender(
      <MetricWorkspace
        lensId="collaboration-flow"
        mode="full"
        onLensChange={() => undefined}
        run={run}
        runId="example-run-0001"
        snapshotLabel="Synthetic snapshot"
        transport={transport}
      />,
    );

    expect(document.querySelectorAll('[role="tooltip"]')).toHaveLength(0);
    const next = screen.getByRole("navigation", { name: /metric axes/ }).querySelector("button")!;
    fireEvent.pointerEnter(next);
    expect(document.querySelectorAll('[role="tooltip"]')).toHaveLength(1);
  });
});
