import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SYNTHETIC_RESULTS } from "../../shared/api/syntheticFixtures";
import { MetricObservationCard } from "./MetricObservationCard";

describe("MetricObservationCard", () => {
  it("shows unknown as a state rather than a numeric zero", () => {
    const result = SYNTHETIC_RESULTS.find((item) => item.value_state === "unknown")!;
    render(<MetricObservationCard result={result} />);

    expect(screen.getByRole("heading", { name: "Usage Input Tokens" })).toBeVisible();
    expect(screen.getByText("Unknown", { selector: ".metric-card__value" })).toBeVisible();
    expect(screen.queryByText("0 tokens")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAccessibleName(
      "0 of 1 observations (0%)",
    );
  });

  it("renders an arbitrary known metric through the generic presenter", () => {
    const result = {
      ...SYNTHETIC_RESULTS[0],
      key: "fictional_delivery_signal",
      numeric_value: 0.42,
      unit: "ratio",
    };
    render(<MetricObservationCard result={result} />);

    expect(screen.getByRole("heading", { name: "Fictional Delivery Signal" })).toBeVisible();
    expect(screen.getByText("42%")).toBeVisible();
  });
});
