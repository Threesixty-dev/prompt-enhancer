import { describe, expect, it } from "vitest";
import type { ModelEnsembleTrajectoryPoint } from "../../shared/api/contracts";
import {
  modelEnsembleHistoryRadarValue,
  modelEnsembleTrajectoryRadarData,
} from "./MetricWorkspace";
import { modelEnsembleRadarAxes } from "./ModelEnsembleRadar";

describe("modelEnsembleHistoryRadarValue", () => {
  it("keeps lower-is-better rework history aligned with radar quality", () => {
    const point = {
      typed_metrics: [{
        metric_key: "collaboration.rework_candidate_rate",
        value_state: "known",
        numeric_value: 0.02,
      }],
      metrics: [],
    } as unknown as ModelEnsembleTrajectoryPoint;

    expect(modelEnsembleHistoryRadarValue(
      point,
      "collaboration.rework_candidate_rate",
      "lower_is_better",
    )).toBeCloseTo(0.98);
    expect(modelEnsembleHistoryRadarValue(
      point,
      "collaboration.rework_candidate_rate",
      "higher_is_better",
    )).toBeCloseTo(0.02);
  });

  it("withholds trajectory-only experimental summaries without contributor proof", () => {
    const point = {
      typed_metrics: [],
      metrics: [],
      predictive_metrics: [{
        metric_key: "prompt.task_definition_coverage",
        target: "metric_value",
        state: "experimental",
        mean: 0.6,
        median: 0.6,
        q05: 0.4,
        q25: 0.5,
        q75: 0.7,
        q95: 0.8,
        applicability_probability: 0.9,
        pending_probability: 0,
        model_disagreement: 0.1,
        effective_observation_count: 2,
        model_set_version: "example-model-set-v1",
        calibration_version: "not-calibrated-v1",
        contract_version: "example-contract-v1",
        contract_fingerprint: "a".repeat(64),
        product_metric_eligible: false,
      }],
    } as unknown as ModelEnsembleTrajectoryPoint;

    const axis = modelEnsembleRadarAxes(
      modelEnsembleTrajectoryRadarData(point),
      "task-framing",
    )[0];
    expect(axis.predictiveMedian).toBeNull();
    expect(axis.predictiveWithheldReason).toMatch(/fewer than two small experts/i);
  });
});
