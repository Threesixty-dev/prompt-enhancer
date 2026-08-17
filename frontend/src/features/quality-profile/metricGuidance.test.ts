import { describe, expect, it } from "vitest";
import { sessionMetricGuidance } from "./metricGuidance";

describe("sessionMetricGuidance", () => {
  it("requests objective local evidence instead of prompt rewriting", () => {
    const guidance = sessionMetricGuidance("outcome.verified_requirement_coverage", {
      state: "abstained",
      numericValue: null,
      direction: "higher_is_better",
      explanationCode: "objective_verification_stream_required",
    });

    expect(guidance.audience).toBe("tooling");
    expect(guidance.basis).toBe("readiness");
    expect(guidance.action).toMatch(/tool, test, artifact, action, or acceptance receipt/i);
    expect(guidance.action).not.toMatch(/rewrite|improve the prompt/i);
  });

  it("names at most two weak factors without generating source-derived prose", () => {
    const guidance = sessionMetricGuidance("prompt.task_definition_coverage", {
      state: "known",
      numericValue: 0.25,
      direction: "higher_is_better",
      factorKeys: ["action", "intended_outcome", "target"],
    });

    expect(guidance.factorKeys).toEqual(["action", "intended_outcome"]);
    expect(guidance.action).toMatch(/focus on action and intended outcome/i);
    expect(guidance.basis).toBe("measured");
  });

  it("does not prescribe changes for a not-applicable metric", () => {
    const guidance = sessionMetricGuidance("logic.decomposition_coverage", {
      state: "not_applicable",
      numericValue: null,
      direction: "higher_is_better",
    });

    expect(guidance.action).toMatch(/no change is required/i);
    expect(guidance.basis).toBe("readiness");
  });
});
