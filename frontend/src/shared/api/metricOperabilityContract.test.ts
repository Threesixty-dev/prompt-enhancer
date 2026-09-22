import { describe, expect, it } from "vitest";
import {
  createSyntheticMetricOperabilityCatalog,
  METRIC_V2_PROVIDER_ADAPTER_GAP_KEYS,
  MetricOperabilityDefinitionsOutOfDateError,
  MetricOperabilityPayloadError,
  parseMetricOperabilityCatalog,
} from "./metricOperabilityContract";

function copyFixture(): Record<string, unknown> {
  return structuredClone(createSyntheticMetricOperabilityCatalog()) as unknown as Record<string, unknown>;
}

describe("metric operability catalog contract", () => {
  it("accepts the exact all-twenty v6 release partition", () => {
    const result = parseMetricOperabilityCatalog(copyFixture());

    expect(result.entries).toHaveLength(20);
    expect(result.shipped_path_count).toBe(18);
    expect(result.task_profile_configuration_gap_count).toBe(0);
    expect(result.provider_adapter_gap_count).toBe(2);
    expect(METRIC_V2_PROVIDER_ADAPTER_GAP_KEYS).toEqual([
      "logic.hypothesis_test_linkage",
      "outcome.agent_claim_grounding",
    ]);
    expect(result.entries.find((entry) => entry.metric_key === "logic.decomposition_coverage")).toMatchObject({
      measured_path: "reviewed_requirement_plan",
      shipped_path_state: "available_when_evidence_exists",
      next_step_code: "confirm_requirement_plan_evidence",
    });
    expect(result.entries.find((entry) => entry.metric_key === "logic.requirement_action_traceability")).toMatchObject({
      measured_path: "reviewed_requirement_action",
      shipped_path_state: "available_when_evidence_exists",
      next_step_code: "compose_requirement_action_evidence",
    });
    expect(result.entries.find((entry) => entry.metric_key === "outcome.verified_requirement_coverage")).toMatchObject({
      measured_path: "reviewed_requirement_verification",
      shipped_path_state: "available_when_evidence_exists",
      next_step_code: "issue_reviewed_observed_check",
    });
    expect(result.experimental_model_path_count).toBe(8);
    expect(result.model_authoritative_metric_count).toBe(0);
    expect(result.entries.every((entry) => !entry.measured_value_may_use_model_output)).toBe(true);
    expect(result.catalog_version).toBe("metric-operability-v6");
    expect(result.projection_version).toBe("metric-contract-v2-projection-8");
    expect(result.readiness_catalog_version).toBe("metric-evidence-readiness-v2-7");
  });

  it("accepts the v6 release partition with reviewed requirement actions and checks", () => {
    const value = copyFixture();
    value.catalog_version = "metric-operability-v6";
    value.shipped_path_count = 18;
    value.provider_adapter_gap_count = 2;
    const actionEntry = (value.entries as Record<string, unknown>[]).find(
      (entry) => entry.metric_key === "logic.requirement_action_traceability",
    );
    if (!actionEntry) throw new Error("Synthetic requirement-action entry is missing");
    actionEntry.shipped_path_state = "available_when_evidence_exists";

    const result = parseMetricOperabilityCatalog(value);
    expect(result.catalog_version).toBe("metric-operability-v6");
    expect(result.shipped_path_count).toBe(18);
    expect(result.task_profile_configuration_gap_count).toBe(0);
    expect(result.provider_adapter_gap_count).toBe(2);
    expect(result.entries.find((entry) => entry.metric_key === "logic.requirement_action_traceability")).toMatchObject({
      measured_path: "reviewed_requirement_action",
      shipped_path_state: "available_when_evidence_exists",
      measured_value_may_use_model_output: false,
    });
  });

  it.each([
    ["missing row", (value: Record<string, unknown>) => {
      (value.entries as unknown[]).pop();
    }],
    ["extra top-level field", (value: Record<string, unknown>) => {
      value.private_detail = "forbidden";
    }],
    ["wrong count", (value: Record<string, unknown>) => {
      value.shipped_path_count = 13;
    }],
    ["model authority", (value: Record<string, unknown>) => {
      value.model_authoritative_metric_count = 1;
    }],
    ["reordered rows", (value: Record<string, unknown>) => {
      (value.entries as unknown[]).reverse();
    }],
  ])("rejects malformed catalog: %s", (_name, mutate) => {
    const value = copyFixture();
    mutate(value);
    expect(() => parseMetricOperabilityCatalog(value)).toThrow(MetricOperabilityPayloadError);
  });

  it.each([
    ["stale projection", (value: Record<string, unknown>) => {
      value.projection_version = "metric-contract-v2-projection-7";
    }],
    ["stale v5 operability catalog", (value: Record<string, unknown>) => {
      value.catalog_version = "metric-operability-v5";
    }],
    ["stale readiness catalog", (value: Record<string, unknown>) => {
      value.readiness_catalog_version = "metric-evidence-readiness-v2-6";
    }],
    ["contract set", (value: Record<string, unknown>) => {
      value.contract_set_fingerprint = "0".repeat(64);
    }],
    ["metric fingerprint", (value: Record<string, unknown>) => {
      ((value.entries as Record<string, unknown>[])[0]).contract_fingerprint = "0".repeat(64);
    }],
    ["state drift", (value: Record<string, unknown>) => {
      ((value.entries as Record<string, unknown>[])[3]).shipped_path_state = "task_profile_configuration_required";
    }],
    ["forged verified-coverage path", (value: Record<string, unknown>) => {
      const entry = (value.entries as Record<string, unknown>[]).find(
        (candidate) => candidate.metric_key === "outcome.verified_requirement_coverage",
      );
      if (!entry) throw new Error("Synthetic verified-coverage entry is missing");
      entry.measured_path = "typed_objective";
      entry.shipped_path_state = "provider_adapter_required";
      entry.next_step_code = "add_objective_opportunity_link_adapter";
    }],
    ["model-authored row", (value: Record<string, unknown>) => {
      ((value.entries as Record<string, unknown>[])[0]).measured_value_may_use_model_output = true;
    }],
  ])("classifies definition drift: %s", (_name, mutate) => {
    const value = copyFixture();
    mutate(value);
    expect(() => parseMetricOperabilityCatalog(value)).toThrow(
      MetricOperabilityDefinitionsOutOfDateError,
    );
  });
});
