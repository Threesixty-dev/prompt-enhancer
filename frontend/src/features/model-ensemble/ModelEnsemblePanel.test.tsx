import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  ModelEnsembleRun,
  ModelPredictiveMetricDetail,
  ModelEnsembleTrajectoryPage,
  ModelEnsembleWatchSnapshot,
  PromptEnhancerTransport,
  ProviderCompatibilityStatus,
} from "../../shared/api/contracts";
import {
  ModelEnsemblePayloadError,
  parseModelEnsembleOutcome,
  parseModelEnsembleRun,
} from "../../shared/api/modelEnsembleContract";
import {
  ModelEnsembleWatchPayloadError,
  parseModelEnsembleWatchSnapshot,
} from "../../shared/api/modelEnsembleWatchContract";
import {
  ModelEnsembleTrajectoryPayloadError,
  parseModelEnsembleTrajectoryPage,
} from "../../shared/api/modelEnsembleTrajectoryContract";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { parseModelPredictiveMetricDetail } from "../../shared/api/modelPredictiveMetricDetailContract";
import { createHttpTransport, TransportError } from "../../shared/api/httpTransport";
import { ModelEnsemblePanel } from "./ModelEnsemblePanel";

const SESSION_ID = "a".repeat(64);
const PROJECT_ID = "b".repeat(64);
const EXACT: ProviderCompatibilityStatus = {
  provider: "codex",
  capability: "session_text_analysis",
  state: "exact",
  capability_state: "supported",
  provider_family: "codex_app_server",
  provider_version: "1.2.3",
  adapter_family: "codex_app_server",
  adapter_version: "2.0.0",
  source_schema_family: "codex_thread",
  source_schema_version: "1",
  content_schema_family: "codex_thread_items",
  content_schema_version: "1",
  reason_code: "exact_match",
  checked_at: "2040-01-01T10:00:00Z",
  update_support: "unsupported",
  update_target: null,
};
const CAPABILITY = {
  available: true,
  reason_code: "available",
  data_tier: "redacted_content",
  content_persistence: false,
  network_inference: false,
  raw_transcripts: false,
} as const;

function runFixture(): ModelEnsembleRun {
  const roles = [
    "retrieval", "retrieval", "retrieval", "retrieval",
    "reranking", "reranking",
    "scope_nli", "scope_nli", "scope_nli",
    "structured_rubric",
  ] as const;
  const keys = roles.map((_, index) => `example_model_${index}`);
  const metricKeys = [
    "prompt.task_definition_coverage",
    "prompt.context_sufficiency",
    "prompt.acceptance_testability",
  ];
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
      model_key: keys[ordinal],
      role,
      repository_id: `example-org/model-${ordinal}`,
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
      model_key: keys[ordinal],
      role: ordinal === 9 ? "structured_rubric" as const : "scope_nli" as const,
      state: "present" as const,
      raw_score: 0.9,
      evidence_fragment_count: 2,
      reason_code: "example_present",
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
      reason_code: "example_committee_present",
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
    metric_projection_version: "coaching-typed-projection-v1",
    metric_projection_completed_at: "2040-01-02T10:00:01Z",
    typed_metrics: metricKeys.map((metric_key, index) => ({
      metric_key,
      metric_version: 3,
      value_state: "known" as const,
      numerator: [3, 1, 4][index],
      denominator: 4,
      numeric_value: [0.75, 0.25, 1][index],
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
    predictive_projection_version: "local-probabilistic-radar-v1",
    predictive_projected_at: "2040-01-02T10:00:02Z",
    predictive_metrics: metricKeys.map((metric_key, index) => ({
      metric_key,
      target: "metric_value" as const,
      state: "experimental" as const,
      mean: [0.7, 0.4, 0.8][index],
      median: [0.7, 0.4, 0.8][index],
      q05: [0.45, 0.15, 0.55][index],
      q25: [0.6, 0.3, 0.7][index],
      q75: [0.8, 0.5, 0.9][index],
      q95: [0.95, 0.75, 0.98][index],
      applicability_probability: 0.9,
      pending_probability: 0.05,
      model_disagreement: 0.12,
      effective_observation_count: 1,
      model_set_version: "local-factor-router-v2",
      calibration_version: "not-calibrated-v1",
      contract_version: "example-contract-v1",
      contract_fingerprint: (index + 4).toString(16).repeat(64),
      product_metric_eligible: false as const,
    })),
    predictive_model_stages: [0, 1, 2].map((ordinal) => ({
      model_key: `example_predictive_model_${ordinal}`,
      repository_id: `example-org/predictive-model-${ordinal}`,
      revision: (ordinal + 4).toString(16).repeat(40),
      status: "completed" as const,
      error_code: null,
      device: "cpu" as const,
      quantization: "none" as const,
      inference_latency_ms: 12,
      peak_accelerator_memory_mb: 0,
      process_rss_mb: 256,
      unloaded_after_stage: true as const,
    })),
    completed_at: "2040-01-02T10:00:00Z",
    local_only: true,
    content_persisted: false,
    calibration_state: "not_assessed",
    product_metric_eligible: false,
  };
}

function watchFixture(latestRun: ModelEnsembleRun | null = null): ModelEnsembleWatchSnapshot {
  return {
    watch: {
      watch_id: "d".repeat(64),
      provider: "codex",
      project_id: PROJECT_ID,
      session_id: SESSION_ID,
      max_messages: 100,
      state: "idle",
      generation: 2,
      progress_completed: 10,
      progress_total: 10,
      has_result: latestRun !== null,
      last_error_code: null,
      next_check_at: "2040-01-02T10:01:00Z",
      updated_at: "2040-01-02T10:00:00Z",
      serial_model_execution: true,
      process_isolated_model_release: true,
      cuda_resource_retry_on_cpu: true,
      content_persisted: false,
      calibrated_as_truth: false,
    },
    latest_run: latestRun,
  };
}

function trajectoryFixture(): ModelEnsembleTrajectoryPage {
  const run = runFixture();
  return {
    watch_id: "d".repeat(64),
    head_run_id: run.run_id,
    head_generation: 2,
    points: [{
      generation: 2,
      run_id: run.run_id,
      published_at: "2040-01-02T10:00:01Z",
      completed_at: run.completed_at,
      max_messages: 100,
      source_coverage_state: run.source_coverage_state,
      chunk_count: run.chunk_count,
      comparable_to_head: true,
      metrics: run.metrics,
      metric_projection_version: run.metric_projection_version,
      metric_projection_completed_at: run.metric_projection_completed_at,
      typed_metrics: run.typed_metrics,
      predictive_projection_version: run.predictive_projection_version,
      predictive_metrics: run.predictive_metrics,
    }],
    next_before_generation: null,
    content_persisted: false,
    calibrated_as_truth: false,
  };
}

function predictiveDetailFixture(metricKey = "prompt.task_definition_coverage"): ModelPredictiveMetricDetail {
  const metric = runFixture().predictive_metrics.find((item) => item.metric_key === metricKey)!;
  return {
    run_id: "b".repeat(64),
    projection_version: "local-probabilistic-radar-v1",
    projected_at: "2040-01-02T10:00:02Z",
    metric,
    density_bins: Array.from({ length: 20 }, () => 0.05),
    factors: [{
      factor_key: "action",
      scale: "binary",
      weight: 1,
      applicability_probability: 0.9,
      present_probability: 0.7,
      neutral_probability: 0.2,
      absent_probability: 0.1,
      expert_count: 3,
      critical: true,
    }],
    experimental_label: "Experimental model range",
    local_only: true,
    content_persisted: false,
    universal_trust_percentage_available: false,
  };
}

function renderPanel(transport: PromptEnhancerTransport) {
  return render(
    <ModelEnsemblePanel
      analysisCapability={CAPABILITY}
      category="prompt-quality"
      providerCompatibility={EXACT}
      projectId={PROJECT_ID}
      sessionId={SESSION_ID}
      transport={transport}
    />,
  );
}

describe("model ensemble response contract", () => {
  it("accepts the complete fixed committee and rejects missing votes", () => {
    const valid = runFixture();
    expect(parseModelEnsembleRun(structuredClone(valid))).toEqual(valid);
    expect(parseModelEnsembleOutcome({ run: structuredClone(valid), applied: true })).toEqual({
      run: valid,
      applied: true,
    });
    const invalid = structuredClone(valid);
    invalid.votes.pop();
    expect(() => parseModelEnsembleRun(invalid)).toThrow(ModelEnsemblePayloadError);
  });

  it("preserves a zero-opportunity typed metric as nonnumeric", () => {
    const valid = structuredClone(runFixture());
    valid.typed_metrics[0] = {
      ...valid.typed_metrics[0],
      value_state: "unknown",
      numerator: null,
      denominator: null,
      numeric_value: null,
      observed_message_count: 0,
      eligible_message_count: 0,
      coverage: 0,
      explanation_code: "typed_opportunity_unavailable",
    };

    expect(parseModelEnsembleRun(valid)).toEqual(valid);

    const boundedSuffix = structuredClone(runFixture());
    boundedSuffix.typed_metrics[0] = {
      ...boundedSuffix.typed_metrics[0],
      observed_message_count: 100,
      eligible_message_count: 324,
      coverage: 100 / 324,
    };
    expect(parseModelEnsembleRun(boundedSuffix)).toEqual(boundedSuffix);
  });

  it("rejects false unload claims, impossible dates, and aggregate tampering", () => {
    const unload = structuredClone(runFixture());
    unload.experts[0].unloaded_after_stage = false as true;
    expect(() => parseModelEnsembleRun(unload)).toThrow(ModelEnsemblePayloadError);

    const calendar = structuredClone(runFixture());
    calendar.completed_at = "2040-02-31T10:00:00Z";
    expect(() => parseModelEnsembleRun(calendar)).toThrow(ModelEnsemblePayloadError);

    const aggregate = structuredClone(runFixture());
    aggregate.metrics[0].numeric_value = 0.5;
    expect(() => parseModelEnsembleRun(aggregate)).toThrow(ModelEnsemblePayloadError);
  });

  it("uses exact private loopback routes and rejects cacheable model receipts", async () => {
    const auth = new Response(
      JSON.stringify({ csrf_token: "example-csrf", expires_in_seconds: 300 }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
    const privateResponse = (body: unknown) => new Response(JSON.stringify(body), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store, private",
        Pragma: "no-cache",
      },
    });
    const fetch = vi.fn()
      .mockResolvedValueOnce(auth)
      .mockResolvedValueOnce(privateResponse(runFixture()))
      .mockResolvedValueOnce(privateResponse({ run: runFixture(), applied: true }));
    const transport = createHttpTransport({ fetch, origin: "http://127.0.0.1:8765" });

    await transport.getLatestModelEnsemble(SESSION_ID);
    await transport.startModelEnsemble(
      SESSION_ID,
      { confirmation: "run_ten_local_models_on_selected_redacted_text" },
      "example-model-ensemble-key-0001",
    );

    const calls = fetch.mock.calls as unknown as Array<[string, RequestInit]>;
    expect(calls[1][0]).toBe(`/v1/sessions/${SESSION_ID}/model-ensemble-runs/latest`);
    expect(calls[2][0]).toBe(`/v1/sessions/${SESSION_ID}/model-ensemble-runs`);
    expect(calls[2][1].cache).toBe("no-store");
    expect((calls[2][1].headers as Record<string, string>)["Idempotency-Key"]).toBe("example-model-ensemble-key-0001");

    const unsafeFetch = vi.fn()
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ csrf_token: "example-csrf", expires_in_seconds: 300 }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ))
      .mockResolvedValueOnce(new Response(JSON.stringify(runFixture()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    await expect(
      createHttpTransport({ fetch: unsafeFetch, origin: "http://127.0.0.1:8765" })
        .getLatestModelEnsemble(SESSION_ID),
    ).rejects.toThrow("Private local response was not cache-safe");
  });

  it("validates continuous-watch identity, truth flags, timestamps, and result coherence", () => {
    const valid = watchFixture(runFixture());
    expect(parseModelEnsembleWatchSnapshot(structuredClone(valid))).toEqual(valid);

    const extra = structuredClone(valid) as unknown as Record<string, unknown>;
    extra.private_text = "SYNTHETIC_PRIVATE_CANARY";
    expect(() => parseModelEnsembleWatchSnapshot(extra)).toThrow(ModelEnsembleWatchPayloadError);

    const invalidDate = structuredClone(valid);
    invalidDate.watch.updated_at = "2040-02-31T10:00:00Z";
    expect(() => parseModelEnsembleWatchSnapshot(invalidDate)).toThrow(ModelEnsembleWatchPayloadError);

    const missing = structuredClone(valid);
    missing.latest_run = null;
    expect(() => parseModelEnsembleWatchSnapshot(missing)).toThrow(ModelEnsembleWatchPayloadError);

    const falseRelease = structuredClone(valid);
    falseRelease.watch.process_isolated_model_release = false as true;
    expect(() => parseModelEnsembleWatchSnapshot(falseRelease)).toThrow(ModelEnsembleWatchPayloadError);

    const invalidWindow = structuredClone(valid);
    invalidWindow.watch.max_messages = 101;
    expect(() => parseModelEnsembleWatchSnapshot(invalidWindow)).toThrow(ModelEnsembleWatchPayloadError);
  });

  it("validates the slim trajectory graph and rejects forged chronology or metric counts", () => {
    const valid = trajectoryFixture();
    expect(parseModelEnsembleTrajectoryPage(structuredClone(valid))).toEqual(valid);

    const ownedObservation = structuredClone(valid);
    ownedObservation.points[0].chunk_count = 2;
    expect(parseModelEnsembleTrajectoryPage(ownedObservation)).toEqual(ownedObservation);

    const extra = structuredClone(valid) as unknown as Record<string, unknown>;
    extra.private_text = "SYNTHETIC_PRIVATE_CANARY";
    expect(() => parseModelEnsembleTrajectoryPage(extra)).toThrow(ModelEnsembleTrajectoryPayloadError);

    const chronology = structuredClone(valid);
    chronology.points[0].published_at = "2040-01-02T09:59:59Z";
    expect(() => parseModelEnsembleTrajectoryPage(chronology)).toThrow(ModelEnsembleTrajectoryPayloadError);

    const calendar = structuredClone(valid);
    calendar.points[0].completed_at = "2040-02-31T10:00:00Z";
    expect(() => parseModelEnsembleTrajectoryPage(calendar)).toThrow(ModelEnsembleTrajectoryPayloadError);

    const counts = structuredClone(valid);
    counts.points[0].metrics[0].known_chunk_count = 0;
    expect(() => parseModelEnsembleTrajectoryPage(counts)).toThrow(ModelEnsembleTrajectoryPayloadError);

    const wrongHead = structuredClone(valid);
    wrongHead.head_generation = 1;
    expect(() => parseModelEnsembleTrajectoryPage(wrongHead)).toThrow(ModelEnsembleTrajectoryPayloadError);
  });

  it("validates a fixed-bin predictive detail without accepting source text", () => {
    const valid = predictiveDetailFixture();
    expect(parseModelPredictiveMetricDetail(structuredClone(valid))).toEqual(valid);
    const forged = structuredClone(valid) as unknown as Record<string, unknown>;
    forged.private_text = "SYNTHETIC_PRIVATE_CANARY";
    expect(() => parseModelPredictiveMetricDetail(forged)).toThrow();
    const badDensity = structuredClone(valid);
    badDensity.density_bins[0] = 0.5;
    expect(() => parseModelPredictiveMetricDetail(badDensity)).toThrow();
  });

  it("uses exact private watch routes and cache-safe transport", async () => {
    const auth = new Response(
      JSON.stringify({ csrf_token: "example-csrf", expires_in_seconds: 300 }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
    const response = () => new Response(JSON.stringify(watchFixture()), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store, private",
        Pragma: "no-cache",
      },
    });
    const fetch = vi.fn()
      .mockResolvedValueOnce(auth)
      .mockResolvedValueOnce(response())
      .mockResolvedValueOnce(response())
      .mockResolvedValueOnce(response())
      .mockResolvedValueOnce(new Response(JSON.stringify(trajectoryFixture()), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store, private",
          Pragma: "no-cache",
        },
      }));
    const transport = createHttpTransport({ fetch, origin: "http://127.0.0.1:8765" });

    await transport.getActiveModelEnsembleWatch!();
    await transport.enableModelEnsembleWatch!(SESSION_ID, {
      project_id: PROJECT_ID,
      max_messages: 25,
      confirmation: "continuously_analyze_selected_redacted_session",
    });
    await transport.disableModelEnsembleWatch!("d".repeat(64));
    await transport.getModelEnsembleTrajectory!("d".repeat(64), 24, 8);

    const calls = fetch.mock.calls as unknown as Array<[string, RequestInit]>;
    expect(calls[1][0]).toBe("/v1/model-ensemble-watch/active");
    expect(calls[2][0]).toBe(`/v1/sessions/${SESSION_ID}/model-ensemble-watch`);
    expect(calls[2][1].method).toBe("PUT");
    expect(calls[2][1].cache).toBe("no-store");
    expect(calls[3][0]).toBe(`/v1/model-ensemble-watches/${"d".repeat(64)}`);
    expect(calls[3][1].method).toBe("DELETE");
    expect(calls[4][0]).toBe(`/v1/model-ensemble-watches/${"d".repeat(64)}/trajectory?limit=24&before_generation=8`);
    expect(calls[4][1].method).toBe("GET");
    expect(calls[4][1].cache).toBe("no-store");
  });
});

describe("ModelEnsemblePanel", () => {
  it("shows the typed radar with separate diagnostics and never describes it as a product score", async () => {
    const getDetail = vi.fn(async (_runId: string, metricKey: string) => predictiveDetailFixture(metricKey));
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getLatestModelEnsemble: async () => structuredClone(runFixture()),
      getModelPredictiveMetricDetail: getDetail,
    };
    renderPanel(transport);

    expect(await screen.findByRole("img", { name: /typed local metric radar/i })).toBeVisible();
    expect(screen.getByText(/solid measurements and model ranges stay separate/i)).toBeVisible();
    expect(screen.getByText(/axes and order stay fixed/i)).toBeVisible();
    expect(screen.getByText(/gaps are unknown, not zero/i)).toBeVisible();
    expect(screen.getByText(/coverage, not confidence/i)).toBeVisible();
    expect(screen.getByText("Predictive stages").parentElement).toHaveTextContent("3 / 3");
    expect(screen.getByText("Source coverage").parentElement).toHaveTextContent("Complete selected window");
    expect(screen.getAllByText(/unloaded yes/i)).toHaveLength(3);
    expect(await screen.findByLabelText("Predictive density")).toBeVisible();
    expect(getDetail).toHaveBeenCalledWith(
      "b".repeat(64),
      "prompt.task_definition_coverage",
      expect.any(AbortSignal),
    );
  });

  it("marks an incomplete source window without presenting it as complete-session evidence", async () => {
    const incomplete = structuredClone(runFixture());
    incomplete.source_coverage_state = "incomplete_source";
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getLatestModelEnsemble: async () => incomplete,
    };
    renderPanel(transport);

    expect(await screen.findByText("Incomplete source window")).toBeVisible();
    expect(screen.getByText(/retained content only/i)).toBeVisible();
    expect(screen.getByText(/not a complete-session judgment/i)).toBeVisible();
  });

  it("starts exactly one local analysis command with the explicit compatibility confirmation", async () => {
    const start = vi.fn(async () => ({ run: structuredClone(runFixture()), applied: true }));
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getLatestModelEnsemble: async () => { throw new TransportError("not found", 404); },
      startModelEnsemble: start,
    };
    renderPanel(transport);
    fireEvent.click(await screen.findByRole("button", { name: "Analyze metric ranges" }));

    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    const calls = start.mock.calls as unknown as Array<[string, object, string]>;
    expect(calls[0][0]).toBe(SESSION_ID);
    expect(calls[0][1]).toEqual({
      confirmation: "run_ten_local_models_on_selected_redacted_text",
    });
    expect(calls[0][2]).toMatch(/^dashboard-model-ensemble-/);
    expect(await screen.findByText(/stored local analysis completed/i)).toBeVisible();
  });

  it("starts the one-session watch with an explicit standing confirmation", async () => {
    const enable = vi.fn(async () => watchFixture());
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getLatestModelEnsemble: async () => { throw new TransportError("not found", 404); },
      getActiveModelEnsembleWatch: async () => { throw new TransportError("not found", 404); },
      enableModelEnsembleWatch: enable,
    };
    renderPanel(transport);
    fireEvent.click(await screen.findByRole("button", { name: "Watch this session" }));

    await waitFor(() => expect(enable).toHaveBeenCalledTimes(1));
    expect(enable).toHaveBeenCalledWith(
      SESSION_ID,
      {
        project_id: PROJECT_ID,
        max_messages: 100,
        confirmation: "continuously_analyze_selected_redacted_session",
      },
    );
  });
});
