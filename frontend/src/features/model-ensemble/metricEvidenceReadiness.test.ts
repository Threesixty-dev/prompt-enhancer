import { describe, expect, it } from "vitest";
import {
  syntheticMetricEvidenceReadinessV2,
  syntheticMetricPublicationV2,
} from "../../test/metricPublicationV2Fixture";
import { metricEvidenceReadinessForPublication } from "./metricEvidenceReadiness";

describe("metric evidence readiness presentation binding", () => {
  it("accepts the all-twenty additive projection only for its exact sealed publication", () => {
    const publication = syntheticMetricPublicationV2({
      "prompt.task_definition_coverage": { value_state: "known", numerator: 2, denominator: 3 },
      "prompt.context_sufficiency": { value_state: "pending", eligible: 4, pending: 2, numerator: 1 },
    });
    const readiness = syntheticMetricEvidenceReadinessV2(publication);
    expect(metricEvidenceReadinessForPublication(readiness, publication)).toEqual(readiness);
    expect(readiness.metrics).toHaveLength(20);
    expect(readiness.measured_count + readiness.pending_count + readiness.capability_missing_count).toBe(20);
    expect(readiness.objective_metric_count).toBe(5);
    expect(readiness.objective_measurable_count).toBe(0);
    expect(readiness.objective_measured_count).toBe(0);
    expect(readiness.metrics.find((row) => row.metric_key === "logic.hypothesis_test_linkage")?.required_adapter_capabilities)
      .toEqual(["hypothesis_opportunities", "hypothesis_evidence_links", "tool_events", "decision_events", "verification_events"]);
  });

  it("withholds contributor prose when identity, row order, counts, or contributor partitions drift", () => {
    const publication = syntheticMetricPublicationV2();
    const readiness = syntheticMetricEvidenceReadinessV2(publication);
    const mutations: Array<(value: any) => void> = [
      (value) => { value.contract_set_fingerprint = "0".repeat(64); },
      (value) => { value.metric_projection_version = "metric-contract-v2-projection-3"; },
      (value) => { [value.metrics[0], value.metrics[1]] = [value.metrics[1], value.metrics[0]]; },
      (value) => { value.metrics[0].contract_fingerprint = "1".repeat(64); },
      (value) => { value.metrics[0].missing_contributors = []; },
      (value) => { value.metrics[12].required_adapter_capabilities = ["verification_events"]; },
      (value) => { value.metrics[12].reason_code = "generic_objective_capability_required"; },
      (value) => { value.capability_missing_count += 1; },
      (value) => { value.objective_measurable_count += 1; },
    ];
    for (const mutate of mutations) {
      const tampered = structuredClone(readiness);
      mutate(tampered);
      expect(metricEvidenceReadinessForPublication(tampered, publication)).toBeNull();
    }
  });

  it("keeps the contributor partition exact when a capable adapter has resolved nothing yet", () => {
    // Abstained with an available capability and an empty denominator: some
    // proof contributors are observed, the rest are not. The projection must
    // still name the missing ones, otherwise the guard withholds every row.
    const publication = syntheticMetricPublicationV2({
      "collaboration.clarification_yield": { value_state: "abstained", capability_available: true, eligible: 0 },
    });
    const readiness = syntheticMetricEvidenceReadinessV2(publication);
    const row = readiness.metrics.find((candidate) => candidate.metric_key === "collaboration.clarification_yield");
    expect(row?.availability_state).toBe("abstained");
    expect(row?.observed_contributors.length).toBeGreaterThan(0);
    expect([...(row?.observed_contributors ?? []), ...(row?.missing_contributors ?? [])].sort())
      .toEqual([...(row?.required_contributors ?? [])].sort());
    expect(row?.missing_contributors.length).toBeGreaterThan(0);
    expect(metricEvidenceReadinessForPublication(readiness, publication)).toEqual(readiness);
  });

  it("binds the r3 open-loop row to explicit plan and supersession evidence", () => {
    const publication = structuredClone(syntheticMetricPublicationV2({
      "logic.open_loop_closure": {
        value_state: "pending",
        eligible: 2,
        pending: 1,
        numerator: 1,
      },
    }));
    publication.projection_version = "metric-contract-v2-projection-3";
    for (const metric of publication.metrics) {
      metric.state.projection_version = "metric-contract-v2-projection-3";
    }
    const readiness = syntheticMetricEvidenceReadinessV2(publication);
    const openLoop = readiness.metrics.find((row) => row.metric_key === "logic.open_loop_closure");

    expect(openLoop?.required_contributors).toEqual([
      "documented_plan_message",
      "explicit_plan_supersession_link",
    ]);
    expect(openLoop?.availability_state).toBe("pending_right_censored");
    expect(metricEvidenceReadinessForPublication(readiness, publication)).toEqual(readiness);

    const stale = structuredClone(readiness);
    const staleOpenLoop = stale.metrics.find((row) => row.metric_key === "logic.open_loop_closure");
    if (staleOpenLoop === undefined) throw new Error("synthetic open-loop row missing");
    staleOpenLoop.required_contributors = ["semantic_unit_heads", "agent_response_text"];
    expect(metricEvidenceReadinessForPublication(stale, publication)).toBeNull();
  });

  it("treats absence as no additive detail, never as an empty measured projection", () => {
    const publication = syntheticMetricPublicationV2();
    expect(metricEvidenceReadinessForPublication(null, publication)).toBeNull();
    expect(metricEvidenceReadinessForPublication({}, publication)).toBeNull();
    expect(metricEvidenceReadinessForPublication(syntheticMetricEvidenceReadinessV2(publication), null)).toBeNull();
  });
});
