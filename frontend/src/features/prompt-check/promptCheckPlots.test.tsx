import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PromptMetricRadar } from "./promptCheckPlots";

describe("PromptMetricRadar", () => {
  it("keeps an actual zero numeric while leaving unavailable axes out of the chart geometry", () => {
    const { container } = render(
      <PromptMetricRadar
        readings={[
          { key: "zero", label: "Measured zero", value: 0, higherIsBetter: true },
          { key: "unknown", label: "Unavailable", value: null, higherIsBetter: true },
          { key: "known", label: "Measured", value: 0.75, higherIsBetter: true },
        ]}
      />,
    );

    expect(screen.getByRole("img", { name: "Prompt metric radar" })).toHaveTextContent("Unavailable (Unknown)");
    expect(container.querySelectorAll(".prompt-plot__dot--unknown")).toHaveLength(0);
    expect(container.querySelector(".prompt-plot__area")).toBeNull();

    const zeroDot = container.querySelector(".prompt-plot__dot");
    expect(zeroDot).toHaveAttribute("cx", "150");
    expect(zeroDot).toHaveAttribute("cy", "150");
    expect(zeroDot).toHaveTextContent("Measured zero: 0%");
  });

  it("rejects non-finite and out-of-range readings without relabeling them as numeric values", () => {
    const { container } = render(
      <PromptMetricRadar
        readings={[
          { key: "nan", label: "NaN", value: Number.NaN, higherIsBetter: true },
          { key: "infinity", label: "Infinity", value: Number.POSITIVE_INFINITY, higherIsBetter: true },
          { key: "range", label: "Out of range", value: 1.1, higherIsBetter: true },
        ]}
      />,
    );

    expect(container.querySelectorAll(".prompt-plot__dot")).toHaveLength(0);
    expect(container.querySelectorAll(".prompt-plot__segment")).toHaveLength(0);
    expect(container.querySelector(".prompt-plot__area")).toBeNull();
    expect(container).toHaveTextContent("NaN (Unknown)");
    expect(container).toHaveTextContent("Infinity (Unknown)");
    expect(container).toHaveTextContent("Out of range (Unknown)");
  });

  it("draws a closed area only when all three or more axes are known", () => {
    const { container } = render(
      <PromptMetricRadar
        chartLabel="Synthetic session metric radar"
        readings={[
          { key: "one", label: "One", value: 0.25, higherIsBetter: true },
          { key: "two", label: "Two", value: 0.5, higherIsBetter: true },
          { key: "three", label: "Three", value: 0.75, higherIsBetter: true },
        ]}
      />,
    );

    expect(screen.getByRole("img", { name: "Synthetic session metric radar" })).toBeVisible();
    expect(container.querySelector(".prompt-plot__area")).not.toBeNull();
    expect(container.querySelectorAll(".prompt-plot__segment")).toHaveLength(0);
  });

  it("draws only edges between adjacent known axes, including the wraparound edge", () => {
    const { container } = render(
      <PromptMetricRadar
        readings={[
          { key: "first", label: "First", value: 0.25, higherIsBetter: true },
          { key: "gap", label: "Gap", value: null, higherIsBetter: true },
          { key: "third", label: "Third", value: 0.5, higherIsBetter: true },
          { key: "fourth", label: "Fourth", value: 0.75, higherIsBetter: true },
        ]}
      />,
    );

    expect(container.querySelector(".prompt-plot__area")).toBeNull();
    const segments = container.querySelectorAll(".prompt-plot__segment");
    expect(segments).toHaveLength(2);
    expect(segments[0]).toHaveAttribute("x1", "150");
    expect(segments[0]).toHaveAttribute("y1", "204");
    expect(segments[0]).toHaveAttribute("x2", "69");
    expect(segments[0]).toHaveAttribute("y2", "150");
    expect(segments[1]).toHaveAttribute("x1", "69");
    expect(segments[1]).toHaveAttribute("y1", "150");
    expect(segments[1]).toHaveAttribute("x2", "150");
    expect(segments[1]).toHaveAttribute("y2", "123");
  });

  it("does not create an edge for an isolated known axis and preserves lower-is-better labels", () => {
    const { container } = render(
      <PromptMetricRadar
        readings={[
          { key: "first", label: "First", value: null, higherIsBetter: true },
          { key: "risk", label: "Risk", value: 0.1, higherIsBetter: false },
          { key: "third", label: "Third", value: null, higherIsBetter: true },
        ]}
      />,
    );

    expect(container.querySelectorAll(".prompt-plot__dot")).toHaveLength(1);
    expect(container.querySelectorAll(".prompt-plot__segment")).toHaveLength(0);
    expect(container.querySelector(".prompt-plot__area")).toBeNull();
    expect(container.querySelectorAll(".prompt-plot__label")[1]).toHaveTextContent("Risk 90% quality");
    expect(container.querySelector(".prompt-plot__dot title")).toHaveTextContent("Risk: 90% quality (raw 10%; lower is better)");
  });

  it("uses a caller-provided unavailable state without treating it as a number", () => {
    render(
      <PromptMetricRadar
        readings={[{ key: "error", label: "Evidence", value: null, higherIsBetter: true, stateLabel: "Execution error" }]}
      />,
    );

    expect(screen.getByRole("img", { name: "Prompt metric radar" })).toHaveTextContent("Evidence (Execution error)");
  });
});
