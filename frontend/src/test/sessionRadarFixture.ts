import type { ModelEnsembleRun } from "../shared/api/contracts";
import { METRIC_V2_KEYS } from "../shared/api/metricPublicationV2Contract";
import { syntheticMetricPublicationV2 } from "./metricPublicationV2Fixture";

export type SessionRadarFixtureSource = "v2" | "typed" | "committee";

/**
 * Content-free wire-shaped ensemble receipt shared by session-radar tests.
 * Keep it parser-valid: consumers exercise the same decoded contract as the
 * HTTP transport, rather than a partial object cast to a run.
 */
export function createSessionRadarRun({
  source = "v2",
  canonicalState = "measured",
}: {
  source?: SessionRadarFixtureSource;
  canonicalState?: "measured" | "unknown";
} = {}): ModelEnsembleRun {
  const roles = [
    "retrieval", "retrieval", "retrieval", "retrieval",
    "reranking", "reranking",
    "scope_nli", "scope_nli", "scope_nli",
    "structured_rubric",
  ] as const;
  const modelKeys = roles.map((_, index) => `example_radar_model_${index}`);
  const metricKeys = METRIC_V2_KEYS;
  const publication = source !== "v2"
    ? null
    : syntheticMetricPublicationV2(canonicalState === "unknown" ? {} : {
      "prompt.task_definition_coverage": {
        value_state: "known",
        numerator: 3,
        denominator: 4,
        eligible: 4,
        state_class: "known_improve",
        factor_evidence: "per_factor_measured",
        source_complete: true,
      },
      "collaboration.rework_candidate_rate": {
        value_state: "known",
        numerator: 0,
        denominator: 4,
        eligible: 4,
        state_class: "known_retain",
        factor_evidence: "per_factor_measured",
        source_complete: true,
      },
    });

  return {
    run_id: "b".repeat(64),
    plan_version: "local-shadow-ensemble-v1",
    plan_fingerprint: "c".repeat(64),
    source_coverage_state: "complete_window",
    chunk_count: 1,
    model_count: 10,
    chunks: [{ ordinal: 0, source_message_count: 4, fragment_count: 8, character_count: 4000 }],
    experts: roles.map((role, ordinal) => ({
      ordinal,
      model_key: modelKeys[ordinal],
      role,
      repository_id: `example-org/radar-model-${ordinal}`,
      revision: ordinal.toString(16).repeat(40),
      license_spdx: ordinal % 2 === 0 ? "MIT" as const : "Apache-2.0" as const,
      contributes_to_decision: ordinal >= 7,
      status: "completed" as const,
      error_code: null,
      device: "cpu" as const,
      inference_latency_ms: 10,
      peak_accelerator_memory_mb: 0,
      process_rss_mb: 256,
      unloaded_after_stage: true as const,
    })),
    votes: metricKeys.flatMap((metric_key) => [6, 7, 8, 9].map((ordinal) => ({
      chunk_ordinal: 0,
      metric_key,
      model_key: modelKeys[ordinal],
      role: ordinal === 9 ? "structured_rubric" as const : "scope_nli" as const,
      state: "present" as const,
      raw_score: 0.9,
      evidence_fragment_count: 2,
      reason_code: "example_radar_present",
    }))),
    chunk_metrics: metricKeys.map((metric_key) => ({
      chunk_ordinal: 0,
      metric_key,
      value_state: "known" as const,
      numerator: 1,
      denominator: 1,
      rubric_vote: "present" as const,
      contributing_nli_votes: 2,
      diagnostic_nli_votes: 1,
      reason_code: "example_radar_committee_present",
    })),
    metrics: metricKeys.map((metric_key) => ({
      metric_key,
      value_state: "known" as const,
      numerator: 1,
      denominator: 1,
      numeric_value: 1,
      known_chunk_count: 1,
      abstained_chunk_count: 0,
      unsupported_chunk_count: 0,
      failed_chunk_count: 0,
      total_chunk_count: 1,
      explanation_code: "example_ratio_of_chunks",
      calibration_state: "not_assessed" as const,
      product_metric_eligible: false as const,
    })),
    metric_projection_version: source === "committee" ? null : "coaching-typed-projection-v1",
    metric_projection_completed_at: source === "committee" ? null : "2040-01-02T10:00:01Z",
    metric_publication_v2: publication,
    metric_profile_binding: null,
    requirement_plan_evidence_binding: null,
    requirement_action_evidence_binding: null,
    requirement_verification_evidence_binding: null,
    metric_evidence_readiness_v2: null,
    typed_metrics: source === "committee" ? [] : metricKeys.map((metric_key, index) => ({
      metric_key,
      metric_version: 3,
      value_state: "known" as const,
      numerator: index === 0 ? 1 : 3,
      denominator: 4,
      numeric_value: index === 0 ? 0.25 : 0.75,
      observed_message_count: 4,
      eligible_message_count: 4,
      coverage: 1,
      explanation_code: "typed_requirement_ratio",
      error_code: null,
      projection_source: "deterministic_typed_contract" as const,
      metric_schema_version: 2,
      engine_version: "coaching-rules-en-pl-2",
      algorithm_id: "coaching-text-features",
      algorithm_version: "coaching-features-en-pl-2",
      rubric_version: "coaching-rubric-v3",
      calibration_state: "not_assessed" as const,
      product_metric_eligible: false as const,
    })),
    predictive_projection_version: null,
    predictive_projected_at: null,
    predictive_metrics: [],
    predictive_model_stages: [],
    completed_at: "2040-01-02T10:00:00Z",
    local_only: true,
    content_persisted: false,
    calibration_state: "not_assessed",
    product_metric_eligible: false,
  };
}
