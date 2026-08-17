import { describe, expect, it } from "vitest";
import type { ModelEnsembleRun } from "../../shared/api/contracts";
import {
  MODEL_ENSEMBLE_LENSES,
  modelEnsembleMetricPresentation,
  modelEnsembleRadarAxes,
  modelEnsembleRadarMarkerMagnitude,
  modelEnsembleRadarSegments,
} from "./ModelEnsembleRadar";

type EnsembleMetric = ModelEnsembleRun["metrics"][number];
type TypedMetric = ModelEnsembleRun["typed_metrics"][number];

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

function typedMetric(overrides: Partial<TypedMetric> = {}): TypedMetric {
  return {
    metric_key: "prompt.task_definition_coverage",
    metric_version: 3,
    value_state: "known",
    numerator: 3,
    denominator: 4,
    numeric_value: 0.75,
    observed_message_count: 8,
    eligible_message_count: 10,
    coverage: 0.8,
    explanation_code: "typed_requirement_ratio",
    error_code: null,
    projection_source: "deterministic_typed_contract",
    metric_schema_version: 2,
    engine_version: "coaching-rules-en-pl-2",
    algorithm_id: "coaching-text-features",
    algorithm_version: "coaching-features-en-pl-2",
    rubric_version: "coaching-rubric-v3",
    calibration_state: "not_assessed",
    product_metric_eligible: false,
    ...overrides,
  };
}

describe("modelEnsembleMetricPresentation", () => {
  it("distinguishes an explicit known zero from missing inference", () => {
    const value = modelEnsembleMetricPresentation(metric(), "higher_is_better");

    expect(value.value).toBe("0% signal");
    expect(value.detail).toMatch(/typed opportunity eligibility/i);
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

    expect(value.value).toBe("Needs evidence");
    expect(value.detail).toMatch(/did not support a numeric decision/i);
  });

  it("keeps four versioned lenses with stable axis counts", () => {
    expect(MODEL_ENSEMBLE_LENSES.map((lens) => [lens.id, lens.expectedMetricCount])).toEqual([
      ["task-framing", 6],
      ["collaboration-flow", 5],
      ["reasoning-trace", 5],
      ["outcome-evidence", 4],
    ]);
  });

  it("uses typed numerator and denominator even when the model committee abstains", () => {
    const committee = metric({
      value_state: "abstained",
      numerator: null,
      denominator: null,
      numeric_value: null,
      known_chunk_count: 0,
      abstained_chunk_count: 2,
    });
    const run = {
      metrics: [committee],
      typed_metrics: [typedMetric()],
      chunk_metrics: [],
    } as unknown as ModelEnsembleRun;

    const axes = modelEnsembleRadarAxes(run, "task-framing");
    expect(axes[0].plotted).toBe(0.75);
    const presentation = modelEnsembleMetricPresentation(axes[0].metric!, "higher_is_better");
    expect(presentation.value).toBe("75% measured");
    expect(presentation.detail).toMatch(/3\/4 typed opportunities/i);
  });

  it("breaks the outline at unknown axes instead of bridging them as zero", () => {
    const run = {
      typed_metrics: [],
      metrics: [
        metric({ metric_key: "prompt.task_definition_coverage", numeric_value: 0.8, numerator: 4, denominator: 5 }),
        metric({ metric_key: "prompt.problem_evidence_quality", numeric_value: 0.6, numerator: 3, denominator: 5 }),
        metric({
          metric_key: "prompt.context_sufficiency",
          value_state: "unknown",
          numeric_value: null,
          numerator: null,
          denominator: null,
          known_chunk_count: 0,
          unsupported_chunk_count: 2,
        }),
      ],
    } as unknown as ModelEnsembleRun;
    const axes = modelEnsembleRadarAxes(run, "task-framing");

    expect(axes).toHaveLength(6);
    expect(axes[2].plotted).toBeNull();
    expect(modelEnsembleRadarSegments(axes)).toEqual([[0, 1]]);
  });

  it("gives explicit zeros and nonnumeric states distinct marker positions without changing values", () => {
    expect(modelEnsembleRadarMarkerMagnitude(0)).toBe(0.075);
    expect(modelEnsembleRadarMarkerMagnitude(null)).toBe(0.1);
    expect(modelEnsembleRadarMarkerMagnitude(0.67)).toBe(0.67);
  });

  it("explains adapter and objective-receipt gaps instead of calling them low scores", () => {
    const unavailable = modelEnsembleMetricPresentation(
      typedMetric({
        metric_key: "logic.decision_rationale_coverage",
        value_state: "abstained",
        numerator: null,
        denominator: null,
        numeric_value: null,
        explanation_code: "message_kind_unavailable",
      }),
      "higher_is_better",
    );
    const objective = modelEnsembleMetricPresentation(
      typedMetric({
        metric_key: "outcome.verified_requirement_coverage",
        value_state: "abstained",
        numerator: null,
        denominator: null,
        numeric_value: null,
        explanation_code: "objective_verification_stream_required",
      }),
      "higher_is_better",
    );

    expect(unavailable.detail).toMatch(/adapter version/i);
    expect(unavailable.detail).toMatch(/not a zero/i);
    expect(unavailable.value).toBe("Needs evidence");
    expect(objective.detail).toMatch(/typed local tool, test, artifact, or verification receipt/i);
  });
});
