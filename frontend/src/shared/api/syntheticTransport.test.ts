import { describe, expect, it } from "vitest";
import type { ReviewCommand } from "./contracts";
import { SYNTHETIC_CANDIDATES } from "./syntheticFixtures";
import { createSyntheticTransport } from "./syntheticTransport";

describe("synthetic transport vertical slice", () => {
  it("reviews, analyzes, and queries one fictional task idempotently", async () => {
    const transport = createSyntheticTransport();
    const candidate = SYNTHETIC_CANDIDATES[0].candidate;
    const command = {
      action: "accept",
      request: {
        candidate_id: candidate.candidate_id,
        expected_discovery_version: candidate.discovery_version,
        task_category: "feature_implementation",
      },
    } satisfies ReviewCommand;

    const decision = await transport.review(command, "synthetic-review-v1");
    const repeatedDecision = await transport.review(command, "synthetic-review-v1");
    expect(decision.applied).toBe(true);
    expect(repeatedDecision).toMatchObject({
      decision_id: decision.decision_id,
      applied: false,
    });

    const output = decision.output_revisions[0];
    const taskIndex = await transport.listTaskRevisions();
    expect(taskIndex.tasks[0]).toMatchObject({
      task_id: output.task_id,
      session_ids: candidate.session_ids,
    });
    const analysis = await transport.startAnalysis(
      output.task_id,
      output.revision,
      "synthetic-analysis-v1",
    );
    const repeatedAnalysis = await transport.startAnalysis(
      output.task_id,
      output.revision,
      "synthetic-analysis-v1",
    );
    expect(analysis).toMatchObject({ status: "completed", applied: true });
    expect(repeatedAnalysis).toMatchObject({ run_id: analysis.run_id, applied: false });

    const detail = await transport.getAnalysisRun(analysis.run_id);
    expect(detail.results.map((result) => result.key)).toContain(
      "task.verification.pass_rate",
    );
    const sessionCount = detail.results.find(
      (result) => result.key === "task.workflow.session_count",
    );
    expect(sessionCount).toMatchObject({
      value_state: "known",
      numeric_value: candidate.session_ids.length,
      observed_count: candidate.session_ids.length,
      eligible_count: candidate.session_ids.length,
    });
    expect(detail.results.some((result) => result.value_state === "unknown")).toBe(true);
  });
});
