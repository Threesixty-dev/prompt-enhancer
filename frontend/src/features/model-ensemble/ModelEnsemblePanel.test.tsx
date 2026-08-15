import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  ModelEnsembleRun,
  PromptEnhancerTransport,
  ProviderCompatibilityStatus,
} from "../../shared/api/contracts";
import {
  ModelEnsemblePayloadError,
  parseModelEnsembleOutcome,
  parseModelEnsembleRun,
} from "../../shared/api/modelEnsembleContract";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { createHttpTransport, TransportError } from "../../shared/api/httpTransport";
import { ModelEnsemblePanel } from "./ModelEnsemblePanel";

const SESSION_ID = "a".repeat(64);
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
    completed_at: "2040-01-02T10:00:00Z",
    local_only: true,
    content_persisted: false,
    calibration_state: "not_assessed",
    product_metric_eligible: false,
  };
}

function renderPanel(transport: PromptEnhancerTransport) {
  return render(
    <ModelEnsemblePanel
      analysisCapability={CAPABILITY}
      category="prompt-quality"
      providerCompatibility={EXACT}
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
});

describe("ModelEnsemblePanel", () => {
  it("shows the separate shadow radar and never describes it as a product score", async () => {
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getLatestModelEnsemble: async () => structuredClone(runFixture()),
    };
    renderPanel(transport);

    expect(await screen.findByRole("img", { name: /shadow model radar/i })).toBeVisible();
    expect(screen.getByText(/shadow result—not a product score/i)).toBeVisible();
    expect(screen.getByText(/unknown, unsupported, failed, and abstained metrics are omitted/i)).toBeVisible();
    expect(screen.getByText("Models completed").parentElement).toHaveTextContent("10 / 10");
    expect(screen.getByText("Source coverage").parentElement).toHaveTextContent("Complete selected window");
    expect(screen.getAllByText(/unloaded yes/i)).toHaveLength(10);
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

  it("starts exactly one ten-model command with the explicit confirmation", async () => {
    const start = vi.fn(async () => ({ run: structuredClone(runFixture()), applied: true }));
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getLatestModelEnsemble: async () => { throw new TransportError("not found", 404); },
      startModelEnsemble: start,
    };
    renderPanel(transport);
    fireEvent.click(await screen.findByRole("button", { name: "Run 10 models locally" }));

    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    const calls = start.mock.calls as unknown as Array<[string, object, string]>;
    expect(calls[0][0]).toBe(SESSION_ID);
    expect(calls[0][1]).toEqual({
      confirmation: "run_ten_local_models_on_selected_redacted_text",
    });
    expect(calls[0][2]).toMatch(/^dashboard-model-ensemble-/);
    expect(await screen.findByText(/stored shadow run completed/i)).toBeVisible();
  });
});
