import { describe, expect, it } from "vitest";
import type { ModelEnsembleRun } from "../../shared/api/contracts";
import * as axisModel from "./metricAxisModel";
import {
  isModelEnsembleTypedMetric,
  modelEnsembleAxisCoverage,
  modelEnsembleAxisEvidence,
  modelEnsembleAxisPlottedLabel,
  modelEnsembleAxisRawRateLabel,
  modelEnsembleCompletedSmallExperts,
  modelEnsembleKnowledgeEntries,
  modelEnsembleMetricStateLabel,
  modelEnsembleMetricStateValue,
  modelEnsemblePrimaryMetrics,
  modelEnsembleRadarAxes,
  modelEnsembleRadarQualityValue,
  modelEnsembleReceiptsByKey,
} from "./metricAxisModel";
import { isDeepModelStage } from "./modelStages";
import * as radarModule from "./ModelEnsembleRadar";
import { moveRovingFocus } from "../../shared/ui/rovingFocus";

type EnsembleMetric = ModelEnsembleRun["metrics"][number];
type TypedMetric = ModelEnsembleRun["typed_metrics"][number];

function committeeMetric(overrides: Partial<EnsembleMetric> = {}): EnsembleMetric {
  return {
    metric_key: "prompt.task_definition_coverage",
    value_state: "known",
    numerator: 1,
    denominator: 2,
    numeric_value: 0.5,
    known_chunk_count: 2,
    abstained_chunk_count: 0,
    unsupported_chunk_count: 0,
    failed_chunk_count: 0,
    total_chunk_count: 4,
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

function runWith(typed: readonly TypedMetric[], metrics: readonly EnsembleMetric[] = []): ModelEnsembleRun {
  return { typed_metrics: typed, metrics, chunk_metrics: [] } as unknown as ModelEnsembleRun;
}

describe("metricAxisModel axis tile helpers", () => {
  const rework = "collaboration.rework_candidate_rate";
  const collaborationRun = runWith([
    typedMetric({ metric_key: rework, numerator: 2, denominator: 100, numeric_value: 0.02 }),
    typedMetric({ metric_key: "collaboration.ambiguity_resolution", numerator: 1, denominator: 4, numeric_value: 0.25 }),
    typedMetric({
      metric_key: "collaboration.clarification_yield",
      value_state: "unknown",
      numerator: null,
      denominator: null,
      numeric_value: null,
      explanation_code: "episode_horizon_open",
    }),
    typedMetric({
      metric_key: "collaboration.exploration_conversion",
      value_state: "not_applicable",
      numerator: null,
      denominator: null,
      numeric_value: null,
      explanation_code: "message_kind_unobserved",
    }),
  ]);
  const axes = modelEnsembleRadarAxes(collaborationRun, "collaboration-flow");
  const byKey = (key: string) => axes.find((axis) => axis.key === key)!;

  it("labels lower-is-better values as radar quality while exposing the raw rate once", () => {
    const axis = byKey(rework);
    expect(axis.plotted).toBe(0.98);
    expect(modelEnsembleAxisPlottedLabel(axis)).toBe("98% radar quality");
    expect(modelEnsembleAxisRawRateLabel(axis)).toBe("raw rate 2%");
  });

  it("labels higher-is-better values as plain percentages without a raw-rate caption", () => {
    const axis = byKey("collaboration.ambiguity_resolution");
    expect(modelEnsembleAxisPlottedLabel(axis)).toBe("25%");
    expect(modelEnsembleAxisRawRateLabel(axis)).toBeNull();
  });

  it("keeps pending, N/A, and missing axes unplotted with explicit state values", () => {
    expect(byKey("collaboration.clarification_yield").plotted).toBeNull();
    expect(modelEnsembleAxisPlottedLabel(byKey("collaboration.clarification_yield"))).toBe("Pending");
    expect(modelEnsembleAxisPlottedLabel(byKey("collaboration.exploration_conversion"))).toBe("N/A");
    expect(modelEnsembleAxisPlottedLabel(byKey("collaboration.scope_change_discipline"))).toBe("No record");
    expect(modelEnsembleAxisRawRateLabel(byKey("collaboration.clarification_yield"))).toBeNull();
    expect(modelEnsembleMetricStateValue(null)).toBe("No record");
    expect(modelEnsembleMetricStateLabel(null)).toBe("not observed");
    expect(modelEnsembleMetricStateLabel(byKey("collaboration.clarification_yield").metric)).toBe("pending · horizon open");
    expect(modelEnsembleMetricStateLabel(byKey("collaboration.exploration_conversion").metric)).toBe("not applicable");
  });

  it("derives guidance evidence that never carries a numeric value for a non-known state", () => {
    expect(modelEnsembleAxisEvidence(byKey(rework))).toEqual({
      state: "known",
      numericValue: 0.02,
      numerator: 2,
      denominator: 100,
      explanationCode: "typed_requirement_ratio",
    });
    expect(modelEnsembleAxisEvidence(byKey("collaboration.clarification_yield"))).toEqual({
      state: "unknown",
      numericValue: null,
      numerator: null,
      denominator: null,
      explanationCode: "episode_horizon_open",
    });
    expect(modelEnsembleAxisEvidence(byKey("collaboration.scope_change_discipline"))).toEqual({
      state: "missing",
      numericValue: null,
      numerator: null,
      denominator: null,
      explanationCode: null,
    });
  });

  it("passes only typed explanation codes to guidance; committee codes stay diagnostics", () => {
    const committeeOnly = modelEnsembleRadarAxes(
      runWith([], [committeeMetric({ value_state: "abstained", numerator: null, denominator: null, numeric_value: null, known_chunk_count: 0, abstained_chunk_count: 4 })]),
      "task-framing",
    )[0];
    expect(isModelEnsembleTypedMetric(committeeOnly.metric!)).toBe(false);
    expect(modelEnsembleAxisEvidence(committeeOnly)).toEqual({
      state: "abstained",
      numericValue: null,
      numerator: null,
      denominator: null,
      explanationCode: null,
    });
  });

  it("reports typed source coverage or legacy eligible-observation coverage for the ring", () => {
    expect(modelEnsembleAxisCoverage(byKey(rework))).toBe(0.8);
    const legacy = modelEnsembleRadarAxes(runWith([], [committeeMetric()]), "task-framing")[0];
    expect(modelEnsembleAxisCoverage(legacy)).toBe(0.5);
    expect(modelEnsembleAxisCoverage(byKey("collaboration.scope_change_discipline"))).toBe(0);
    const emptyDenominator = modelEnsembleRadarAxes(
      runWith([], [committeeMetric({ value_state: "unknown", numerator: null, denominator: null, numeric_value: null, known_chunk_count: 0, unsupported_chunk_count: 0, total_chunk_count: 0 })]),
      "task-framing",
    )[0];
    expect(modelEnsembleAxisCoverage(emptyDenominator)).toBe(0);
  });

  it("builds knowledge entries whose status matches the state label of each axis", () => {
    const entries = modelEnsembleKnowledgeEntries(axes);
    expect(entries.map((entry) => entry.key)).toEqual(axes.map((axis) => axis.key));
    expect(entries.map((entry) => entry.status)).toEqual(axes.map((axis) => modelEnsembleMetricStateLabel(axis.metric)));
    expect(entries.find((entry) => entry.key === rework)?.status).toBe("known");
    expect(entries.find((entry) => entry.key === "collaboration.scope_change_discipline")?.status).toBe("not observed");
  });
});

describe("metricAxisModel receipt resolver", () => {
  const rework = "collaboration.rework_candidate_rate";
  const typedRework = typedMetric({ metric_key: rework, numerator: 1, denominator: 5, numeric_value: 0.2 });
  const committeeRework = committeeMetric({ metric_key: rework, numerator: 7, denominator: 10, numeric_value: 0.7 });

  it("reads only the typed projection when one exists and the committee shadow otherwise, never mixing per key", () => {
    const typedUnknown = typedMetric({ metric_key: rework, value_state: "unknown", numerator: null, denominator: null, numeric_value: null });
    expect(modelEnsemblePrimaryMetrics(runWith([typedUnknown], [committeeRework]))).toEqual([typedUnknown]);
    expect(modelEnsemblePrimaryMetrics(runWith([], [committeeRework]))).toEqual([committeeRework]);
    expect(modelEnsembleReceiptsByKey(runWith([typedUnknown], [committeeRework])).get(rework)).toBe(typedUnknown);
    expect(modelEnsembleReceiptsByKey(runWith([typedRework], [committeeRework])).get(rework)).toBe(typedRework);
    expect(modelEnsembleReceiptsByKey(runWith([], [committeeRework])).get(rework)).toBe(committeeRework);
    // A typed projection that omits the key leaves it unobserved rather than borrowing the committee receipt.
    expect(modelEnsembleReceiptsByKey(runWith([typedMetric()], [committeeRework])).get(rework)).toBeUndefined();
  });

  it("orients only known numeric receipts and keeps every other state null, never zero", () => {
    expect(modelEnsembleRadarQualityValue(typedRework, "lower_is_better")).toBeCloseTo(0.8);
    expect(modelEnsembleRadarQualityValue(typedRework, "higher_is_better")).toBeCloseTo(0.2);
    expect(modelEnsembleRadarQualityValue(committeeRework, "lower_is_better")).toBeCloseTo(0.3);
    for (const state of ["unknown", "not_applicable", "abstained", "execution_error"] as const) {
      const metric = typedMetric({ metric_key: rework, value_state: state, numerator: null, denominator: null, numeric_value: null });
      expect(modelEnsembleRadarQualityValue(metric, "lower_is_better"), state).toBeNull();
    }
    expect(modelEnsembleRadarQualityValue(typedMetric({ numeric_value: null }), "higher_is_better")).toBeNull();
    expect(modelEnsembleRadarQualityValue(null, "lower_is_better")).toBeNull();
    expect(modelEnsembleRadarQualityValue(undefined, "higher_is_better")).toBeNull();
    // The axes use the same resolver: a typed unknown beside a known committee receipt stays unplotted.
    const axis = modelEnsembleRadarAxes(
      runWith([typedMetric({ metric_key: rework, value_state: "unknown", numerator: null, denominator: null, numeric_value: null })], [committeeRework]),
      "collaboration-flow",
    ).find((candidate) => candidate.key === rework)!;
    expect(axis.plotted).toBeNull();
    expect(axis.metric?.value_state).toBe("unknown");
  });
});

describe("metricAxisModel small-expert gate", () => {
  it("uses the single deep-model predicate shared with the stage drawer", () => {
    const stage = (modelKey: string, repositoryId: string, status: "completed" | "failed" = "completed") => ({
      model_key: modelKey,
      repository_id: repositoryId,
      revision: "f".repeat(40),
      status,
      error_code: null,
      device: "cpu" as const,
      quantization: "none" as const,
      inference_latency_ms: 10,
      peak_accelerator_memory_mb: 0,
      process_rss_mb: 128,
      unloaded_after_stage: true as const,
    });
    const run = {
      typed_metrics: [],
      metrics: [],
      chunk_metrics: [],
      predictive_model_stages: [
        stage("mdeberta_xnli", "example-org/mdeberta-xnli"),
        stage("multilingual_minilmv2_l6_nli", "example-org/minilm"),
        stage("qwen3_4b_rubric", "example-org/qwen3-4b-rubric"),
        stage("example_deep_judge", "example-org/deep-judge"),
        stage("modernbert_challenger", "example-org/modernbert", "failed"),
      ],
    } as unknown as ModelEnsembleRun;

    expect(modelEnsembleCompletedSmallExperts(run)).toBe(2);
    expect(run.predictive_model_stages.filter((candidate) => isDeepModelStage(candidate.model_key, candidate.repository_id)).map((candidate) => candidate.model_key))
      .toEqual(["qwen3_4b_rubric", "example_deep_judge"]);
    expect(modelEnsembleCompletedSmallExperts({ typed_metrics: [], metrics: [], chunk_metrics: [] })).toBeNull();
  });
});

describe("ModelEnsembleRadar public surface", () => {
  it("re-exports the pure axis model and the keyboard helper unchanged", () => {
    const names = [
      "MODEL_ENSEMBLE_LENSES",
      "MODEL_ENSEMBLE_STATE_LANE_MAGNITUDE",
      "MODEL_ENSEMBLE_WITHHELD_LANE_MAGNITUDE",
      "PREDICTIVE_WITHHELD_CONTRIBUTOR_PROOF_MISSING",
      "PREDICTIVE_WITHHELD_TOO_FEW_EXPERTS",
      "isModelEnsembleTypedMetric",
      "modelEnsembleAxisCoverage",
      "modelEnsembleAxisEvidence",
      "modelEnsembleAxisPlottedLabel",
      "modelEnsembleAxisRawRateLabel",
      "modelEnsembleCompletedSmallExperts",
      "modelEnsembleDensityBinsForDirection",
      "modelEnsembleIsRawExplicitZero",
      "modelEnsembleKnowledgeEntries",
      "modelEnsembleMetricPresentation",
      "modelEnsembleMetricStateLabel",
      "modelEnsembleMetricStateValue",
      "modelEnsembleMetricStatus",
      "modelEnsembleMetricStatusLabel",
      "modelEnsemblePredictiveBandPath",
      "modelEnsemblePredictiveSegments",
      "modelEnsemblePredictiveVisibility",
      "modelEnsemblePrimaryMetrics",
      "modelEnsembleRadarAxes",
      "modelEnsembleRadarMarkerMagnitude",
      "modelEnsembleRadarQualityValue",
      "modelEnsembleRadarSegments",
      "modelEnsembleReceiptsByKey",
    ] as const;
    const model = axisModel as unknown as Record<string, unknown>;
    const radar = radarModule as unknown as Record<string, unknown>;
    for (const name of names) {
      expect(model[name], name).toBeDefined();
      expect(radar[name], name).toBe(model[name]);
    }
    expect(radarModule.moveRovingFocus).toBe(moveRovingFocus);
    expect(typeof radarModule.ModelEnsembleRadar).toBe("function");
  });
});
