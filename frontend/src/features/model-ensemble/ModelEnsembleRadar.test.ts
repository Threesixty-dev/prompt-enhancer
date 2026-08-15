import { describe, expect, it } from "vitest";
import type { ModelEnsembleRun } from "../../shared/api/contracts";
import { modelEnsembleMetricPresentation } from "./ModelEnsembleRadar";

type EnsembleMetric = ModelEnsembleRun["metrics"][number];

function metric(overrides: Partial<EnsembleMetric> = {}): EnsembleMetric {
  return {
    metric_key: "prompt.task_definition_coverage",
    value_state: "known",
    numerator: 0,
    denominator: 2,
    numeric_value: 0,
    known_chunk_count: 2,
    abstained_chunk_count: 0,
    unsupported_chunk_count: 0,
    failed_chunk_count: 0,
    total_chunk_count: 2,
    explanation_code: "example_ratio_of_chunks",
    calibration_state: "not_assessed",
    product_metric_eligible: false,
    ...overrides,
  };
}

describe("modelEnsembleMetricPresentation", () => {
  it("distinguishes an explicit known zero from missing inference", () => {
    const value = modelEnsembleMetricPresentation(metric(), "higher_is_better");

    expect(value.value).toBe("0% signal");
    expect(value.detail).toMatch(/explicit committee decision/i);
    expect(value.detail).toMatch(/radar 0%/i);
  });

  it("explains that lower-is-better raw zero maps to the radar edge", () => {
    const value = modelEnsembleMetricPresentation(metric(), "lower_is_better");

    expect(value.value).toBe("0% signal");
    expect(value.detail).toMatch(/lower-is-better signal/i);
    expect(value.detail).toMatch(/radar 100%/i);
  });

  it("never presents abstention as numeric zero", () => {
    const value = modelEnsembleMetricPresentation(
      metric({
        value_state: "abstained",
        numerator: null,
        denominator: null,
        numeric_value: null,
        known_chunk_count: 0,
        abstained_chunk_count: 2,
      }),
      "higher_is_better",
    );

    expect(value.value).toBe("—");
    expect(value.detail).toMatch(/no numeric value was inferred/i);
  });
});
