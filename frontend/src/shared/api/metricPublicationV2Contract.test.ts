import { describe, expect, it } from "vitest";

import {
  METRIC_CONTRACT_V2_SET_FINGERPRINT,
  METRIC_V2_CONTRACT_IDENTITIES,
  METRIC_V2_KEYS,
  MetricDefinitionsOutOfDateError,
  MetricPublicationV2PayloadError,
  expectedMetricGuidanceTemplateIdentities,
  parseMetricPublicationV2,
} from "./metricPublicationV2Contract";
import {
  ModelEnsembleTrajectoryPayloadError,
  parseModelEnsembleTrajectoryPage,
} from "./modelEnsembleTrajectoryContract";

function publicationFixture(): Record<string, unknown> {
  const metrics = METRIC_V2_KEYS.map((metricKey) => {
    const identity = METRIC_V2_CONTRACT_IDENTITIES[metricKey];
    const objective = identity.authority === "objective_receipt";
    const statistics = {
      metric_key: metricKey,
      denominator_basis: identity.basis,
      opportunity_unit_kind: identity.unit,
      capability_available: false,
      source_complete: false,
      eligible_count: 0,
      met_count: 0,
      not_met_count: 0,
      pending_count: 0,
      unknown_count: 0,
      superseded_excluded_count: 0,
      distinct_owner_count: 0,
    };
    const state = {
      metric_key: metricKey,
      registry_version: "all-20-factor-contracts-v2",
      contract_version: "probabilistic-metric-contract-v2",
      contract_fingerprint: identity.fingerprint,
      evidence_authority: identity.authority,
      value_state: "unknown",
      explanation_code: objective ? "typed_objective_absent" : "opportunity_family_unobservable",
      numerator: null,
      denominator: null,
      numeric_value: null,
      censoring_lower_bound: null,
      censoring_upper_bound: null,
      statistics,
      projection_version: "metric-contract-v2-projection-1",
      product_metric_eligible: false,
    };
    const stateClass = objective ? "objective_evidence_missing" : "evidence_unresolved";
    const templates = expectedMetricGuidanceTemplateIdentities(metricKey, stateClass);
    return {
      state,
      guidance: {
        schema_version: 1,
        contract_version: "metric-guidance-contract-v1",
        template_catalog_version: "metric-guidance-templates-v1",
        template_version: 1,
        metric_key: metricKey,
        metric_version: 2,
        registry_version: "all-20-factor-contracts-v2",
        metric_contract_version: "probabilistic-metric-contract-v2",
        metric_contract_fingerprint: identity.fingerprint,
        evidence_authority: identity.authority,
        denominator_basis: identity.basis,
        contract_factor_count: 1,
        audience: "user",
        role: objective ? "outcome_evidence" : "specification_signal",
        value_state: "unknown",
        state_class: stateClass,
        basis: "readiness",
        value_origin: "none",
        factor_evidence: "not_observed",
        focus_factor_keys: [],
        reason_code: objective ? "typed_objective_absent" : "opportunity_family_unobservable",
        diagnosis_template_id: templates.diagnosis,
        action_template_id: templates.action,
        verification_template_id: templates.verification,
        numerator: null,
        denominator: null,
        censoring_lower_bound: null,
        censoring_upper_bound: null,
        eligible_count: 0,
        met_count: 0,
        not_met_count: 0,
        pending_count: 0,
        unknown_count: 0,
        product_metric_eligible: false,
      },
      implementation_state: objective ? "objective_capability_missing" : "method_only_withheld",
    };
  });
  return {
    publication_key: "metric.contract-v2.publication",
    publication_version: 2,
    registry_version: "all-20-factor-contracts-v2",
    contract_set_fingerprint: METRIC_CONTRACT_V2_SET_FINGERPRINT,
    projection_version: "metric-contract-v2-projection-1",
    guidance_contract_version: "metric-guidance-contract-v1",
    guidance_template_catalog_version: "metric-guidance-templates-v1",
    source: "live_projection",
    canonical_live_snapshot: true,
    model_stage_consumed: false,
    compatibility_preview: false,
    metrics,
    known_count: 0,
    pending_count: 0,
    unknown_count: 20,
    not_applicable_count: 0,
    abstained_count: 0,
    execution_error_count: 0,
    objective_measured_count: 0,
    product_metric_eligible: false,
  };
}

describe("canonical metric V2 publication contract", () => {
  it("accepts the exact all-twenty live measured envelope", () => {
    const fixture = publicationFixture();
    expect(parseMetricPublicationV2(structuredClone(fixture))).toEqual(fixture);
  });

  it("accepts every readable projection identity and rejects an unknown future identity", () => {
    const legacy = publicationFixture();
    expect(parseMetricPublicationV2(structuredClone(legacy))).toEqual(legacy);
    for (const version of [
      "metric-contract-v2-projection-2",
      "metric-contract-v2-projection-3",
    ]) {
      const readable = structuredClone(legacy) as any;
      readable.projection_version = version;
      readable.metrics.forEach((item: any) => {
        item.state.projection_version = version;
      });
      expect(parseMetricPublicationV2(structuredClone(readable))).toEqual(readable);
    }
    const future = structuredClone(legacy) as any;
    future.projection_version = "metric-contract-v2-projection-4";
    future.metrics.forEach((item: any) => {
      item.state.projection_version = "metric-contract-v2-projection-4";
    });
    expect(() => parseMetricPublicationV2(future)).toThrow(MetricPublicationV2PayloadError);
  });

  it("rejects a publication that mixes legacy and current row projections", () => {
    const mixed = publicationFixture() as any;
    mixed.projection_version = "metric-contract-v2-projection-2";
    expect(() => parseMetricPublicationV2(mixed)).toThrow(MetricPublicationV2PayloadError);
  });

  it("refuses a safe-looking template identity outside the exact reviewed catalog", () => {
    const fixture = publicationFixture() as any;
    fixture.metrics[0].guidance.verification_template_id = "verification.review_evidence_coverage.v1";
    let caught: unknown;
    try { parseMetricPublicationV2(fixture); } catch (error) { caught = error; }
    expect(caught).toBeInstanceOf(MetricDefinitionsOutOfDateError);
    expect((caught as MetricDefinitionsOutOfDateError).mismatch).toBe("guidance_template_identity");
  });

  it("carries the same strict V2 states in compact trajectory points", () => {
    const publication = publicationFixture() as any;
    const page = {
      watch_id: "1".repeat(64),
      head_run_id: "2".repeat(64),
      head_generation: 1,
      points: [{
        generation: 1,
        run_id: "2".repeat(64),
        published_at: "2042-01-01T00:00:02+00:00",
        completed_at: "2042-01-01T00:00:01+00:00",
        max_messages: 100,
        source_coverage_state: "complete_window",
        chunk_count: 1,
        comparable_to_head: true,
        metrics: METRIC_V2_KEYS.map((metricKey) => ({
          metric_key: metricKey,
          value_state: "known",
          numerator: 1,
          denominator: 1,
          numeric_value: 1,
          known_chunk_count: 1,
          abstained_chunk_count: 0,
          unsupported_chunk_count: 0,
          failed_chunk_count: 0,
          total_chunk_count: 1,
          explanation_code: "synthetic_known",
          calibration_state: "not_assessed",
          product_metric_eligible: false,
        })),
        metric_projection_version: null,
        metric_projection_completed_at: null,
        typed_metrics: [],
        metric_states_v2: publication.metrics.map((item: any) => item.state),
        predictive_projection_version: null,
        predictive_metrics: [],
      }],
      next_before_generation: null,
      content_persisted: false,
      calibrated_as_truth: false,
    };
    expect(parseModelEnsembleTrajectoryPage(structuredClone(page))).toEqual(page);
    const tampered = structuredClone(page);
    tampered.points[0].metric_states_v2[0].numeric_value = 0;
    expect(() => parseModelEnsembleTrajectoryPage(tampered)).toThrow(
      ModelEnsembleTrajectoryPayloadError,
    );
  });

  it.each([
    ["zero-filled unknown", (value: any) => { value.metrics[0].state.numeric_value = 0; }],
    ["compatibility relabel", (value: any) => { value.source = "v1_compatibility_preview"; }],
    ["contract fingerprint", (value: any) => { value.metrics[0].state.contract_fingerprint = "0".repeat(64); }],
    ["guidance mismatch", (value: any) => { value.metrics[0].guidance.metric_key = METRIC_V2_KEYS[1]; }],
    ["measured guidance on an unknown", (value: any) => { value.metrics[0].guidance.basis = "measured"; }],
    ["neural origin on the measured layer", (value: any) => { value.metrics[0].guidance.value_origin = "neural_uncalibrated"; }],
    ["aggregate factor evidence without receipts", (value: any) => { value.metrics[0].guidance.factor_evidence = "aggregate_only"; }],
    ["objective unknown relabelled as a method gap", (value: any) => {
      const objective = value.metrics.find((item: any) => item.state.evidence_authority === "objective_receipt");
      objective.implementation_state = "method_only_withheld";
    }],
    ["state count mismatch", (value: any) => { value.unknown_count = 19; }],
    ["registry order", (value: any) => { [value.metrics[0], value.metrics[1]] = [value.metrics[1], value.metrics[0]]; }],
  ])("rejects %s tampering", (_label, mutate) => {
    const fixture = structuredClone(publicationFixture());
    mutate(fixture);
    expect(() => parseMetricPublicationV2(fixture)).toThrow(MetricPublicationV2PayloadError);
  });
});
