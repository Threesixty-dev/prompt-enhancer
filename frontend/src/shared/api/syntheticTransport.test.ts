import { describe, expect, it } from "vitest";
import type { ReviewCommand } from "./contracts";
import {
  SYNTHETIC_CANDIDATES,
  SYNTHETIC_COACHING_PROJECTION,
  SYNTHETIC_CURRENT_SESSION_QUALITY_RUN,
  SYNTHETIC_QUALITY_PROJECT_ID,
  SYNTHETIC_QUALITY_SESSION_ID,
  SYNTHETIC_RUN,
  SYNTHETIC_MODEL_LINK_EXPERIMENT,
} from "./syntheticFixtures";
import { createSyntheticTransport } from "./syntheticTransport";

describe("synthetic transport vertical slice", () => {
  it("is explicitly tagged as fixture transport and exposes no loopback health check", () => {
    const transport = createSyntheticTransport();

    expect(transport.runtimeKind).toBe("synthetic_fixture");
    expect("getRuntimeHealth" in transport).toBe(false);
  });

  it("exposes a coherent canned pack-v3 readiness example", async () => {
    const detail = await createSyntheticTransport().getAnalysisRun(SYNTHETIC_RUN.run_id);
    const byKey = new Map(detail.results.map((result) => [result.key, result]));
    const eventEvidence = new Set(
      byKey.get("task.workflow.observed_event_count")?.evidence_event_ids,
    );

    expect(detail.run).toMatchObject({
      metric_pack_version: 3,
      metric_engine_version: "task-deterministic-2",
      schema_version: 6,
    });
    expect(detail.results).toHaveLength(15);
    expect(byKey.get("task.verification.pass_rate")).toMatchObject({
      numeric_value: 0.5,
      observed_count: 2,
      eligible_count: 2,
      coverage: 1,
      confidence: 1,
    });
    expect(byKey.get("task.usage.input_tokens")).toMatchObject({
      numeric_value: 10,
      observed_count: 1,
      eligible_count: 2,
      coverage: 0.5,
      confidence: null,
    });
    for (const result of detail.results) {
      expect(new Set(result.evidence_event_ids).size).toBe(result.evidence_event_ids.length);
      expect(result.evidence_event_ids.every((eventId) => eventEvidence.has(eventId))).toBe(true);
    }
  });

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
    expect(detail.run).toMatchObject({
      metric_pack_key: "core.metadata.task",
      metric_pack_version: 3,
      metric_engine_version: "task-deterministic-2",
      schema_version: 6,
    });
    expect(detail.results).toHaveLength(15);
    expect(detail.results.every((result) => result.evidence_event_ids.length === 0)).toBe(true);
    expect(detail.results.map((result) => result.key)).toContain(
      "task.data_quality.turn_usage_coverage",
    );
    expect(
      detail.results.find(
        (result) => result.key === "task.data_quality.turn_usage_coverage",
      ),
    ).toMatchObject({ value_state: "unknown", numeric_value: null });
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

  it("exposes one explicit synthetic metric lab and current immutable coaching run", async () => {
    const transport = createSyntheticTransport();
    const sessions = await transport.listCodexSessions();
    expect(sessions.sessions).toEqual([
      expect.objectContaining({
        project_id: SYNTHETIC_QUALITY_PROJECT_ID,
        session_id: SYNTHETIC_QUALITY_SESSION_ID,
        project_display_name: "Synthetic Metric Lab",
      }),
    ]);
    const projectSessions = await transport.listProjectSessions(
      SYNTHETIC_QUALITY_PROJECT_ID,
    );
    expect(projectSessions).toMatchObject({ total: 1, has_more: false });
    expect(projectSessions.sessions).toHaveLength(1);
    const missingProject = await transport.listProjectSessions("f".repeat(64));
    expect(missingProject).toMatchObject({
      sessions: [],
      total: 0,
      has_more: false,
    });

    const latest = await transport.getLatestSessionQualityAnalysis(
      SYNTHETIC_QUALITY_SESSION_ID,
    );
    expect(latest.run).toMatchObject({
      run_id: SYNTHETIC_CURRENT_SESSION_QUALITY_RUN.run.run_id,
      status: "completed",
      metric_pack_key: "experimental.redacted-text.coaching",
      metric_pack_version: 3,
      local_only: true,
    });
    expect(latest.results).toHaveLength(20);
    expect(latest.results.every((result) => result.value_state === "known")).toBe(true);
    expect(latest.results.every((result) => result.model_id === null)).toBe(true);

    const projectAggregate = await transport.aggregateProjectQuality({
      project_ids: [SYNTHETIC_QUALITY_PROJECT_ID],
      selection_mode: "all_analyzed_work",
    });
    expect(projectAggregate).toMatchObject({
      aggregation_method: "ratio_of_sums",
      estimand: "per_eligible_opportunity",
      selected_project_count: 1,
      selection_mode: "all_analyzed_work",
      session_quality: {
        selected_session_count: 1,
        completed_run_count: 1,
        missing_run_count: 0,
      },
    });
    const publicCohort = projectAggregate.session_quality.metrics.find(
      (metric) => metric.compatibility_cohorts.length > 0,
    )!.compatibility_cohorts[0];
    expect(publicCohort.compatibility_fingerprint).toMatch(/^[0-9a-f]{64}$/);
    expect(publicCohort).not.toHaveProperty("key");
    const serializedProjectAggregate = JSON.stringify(projectAggregate);
    expect(serializedProjectAggregate).not.toContain("provider_version");
    expect(serializedProjectAggregate).not.toContain("adapter_version");
    expect(serializedProjectAggregate).not.toContain("model_plan_fingerprint");

    latest.results[0].numeric_value = 0;
    const secondRead = await transport.getSessionQualityAnalysisRun(
      latest.run.run_id,
    );
    expect(secondRead.results[0].numeric_value).toBe(1);
    await expect(
      transport.getSessionCoachingSummary!(latest.run.run_id),
    ).resolves.toEqual(SYNTHETIC_COACHING_PROJECTION);
  });

  it("replays the immutable current fixture for an explicit synthetic quality command", async () => {
    const transport = createSyntheticTransport();
    const outcome = await transport.startSessionQualityAnalysis(
      SYNTHETIC_QUALITY_SESSION_ID,
      {
        confirmation: "analyze_selected_redacted_text",
        preset_id: "coaching_profile_v1",
      },
      "dashboard-quality-analysis-synthetic",
    );
    expect(outcome).toMatchObject({
      applied: false,
      result_count: 20,
      run_id: SYNTHETIC_CURRENT_SESSION_QUALITY_RUN.run.run_id,
      status: "completed",
    });

    const latest = await transport.getLatestSessionQualityAnalysis(
      SYNTHETIC_QUALITY_SESSION_ID,
    );
    expect(latest).toEqual(SYNTHETIC_CURRENT_SESSION_QUALITY_RUN);
  });

  it("keeps model-link excerpts transient while revisioning fictional review labels", async () => {
    const transport = createSyntheticTransport();
    const outcome = await transport.startModelLinkExperiment(
      SYNTHETIC_QUALITY_SESSION_ID,
      {
        confirmation: "compare_selected_redacted_text_with_local_models",
        device: "auto",
      },
      "dashboard-model-link-experiment-synthetic",
    );
    expect(outcome.suggestions).toHaveLength(2);

    const linkId = outcome.experiment.links[0].link_id;
    const annotation = await transport.annotateModelLink(
      outcome.experiment.run.run_id,
      linkId,
      { label: "relevant", expected_revision: 0 },
    );
    expect(annotation).toMatchObject({ revision: 1, label: "relevant" });

    const latest = await transport.getLatestModelLinkExperiment(
      SYNTHETIC_QUALITY_SESSION_ID,
    );
    expect(latest.annotations).toEqual([annotation]);
    expect(JSON.stringify(latest)).not.toContain("query_excerpt");
    expect(SYNTHETIC_MODEL_LINK_EXPERIMENT.annotations).toEqual([]);
  });
});
