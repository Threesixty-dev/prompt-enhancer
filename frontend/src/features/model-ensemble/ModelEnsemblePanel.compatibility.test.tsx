import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  ModelEnsembleWatchSnapshot,
  PromptEnhancerTransport,
  ProviderCompatibilityStatus,
} from "../../shared/api/contracts";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { parseProviderCompatibilityStatus, TransportError } from "../../shared/api/httpTransport";
import { ModelEnsemblePanel } from "./ModelEnsemblePanel";

const SESSION_ID = "a".repeat(64);
const PROJECT_ID = "b".repeat(64);

const ANALYSIS_CAPABILITY = {
  available: true,
  reason_code: "available",
  data_tier: "redacted_content",
  content_persistence: false,
  network_inference: false,
  raw_transcripts: false,
} as const;

const SESSION_TEXT_COMPATIBILITY: ProviderCompatibilityStatus = parseProviderCompatibilityStatus({
  provider: "synthetic",
  capability: "session_text_analysis",
  state: "exact",
  capability_state: "supported",
  provider_family: "synthetic_provider",
  provider_version: "1",
  adapter_family: "synthetic_adapter",
  adapter_version: "1",
  source_schema_family: "synthetic_session",
  source_schema_version: "1",
  content_schema_family: "synthetic_content",
  content_schema_version: "1",
  reason_code: "exact_match",
  checked_at: "2040-01-01T00:00:00Z",
  update_support: "unsupported",
  update_target: null,
}, "synthetic");

const WATCH_COMPATIBILITY: ProviderCompatibilityStatus = parseProviderCompatibilityStatus({
  ...SESSION_TEXT_COMPATIBILITY,
  provider: "codex",
  provider_family: "codex_app_server",
  adapter_family: "codex_app_server",
  source_schema_family: "codex_thread",
  content_schema_family: "codex_thread_items",
}, "codex");

function renderPanel(
  compatibility: ProviderCompatibilityStatus,
  start: PromptEnhancerTransport["startModelEnsemble"],
  enableWatch: NonNullable<PromptEnhancerTransport["enableModelEnsembleWatch"]> = vi.fn(),
  overrides: Partial<PromptEnhancerTransport> = {},
) {
  const transport: PromptEnhancerTransport = {
    ...createSyntheticTransport(),
    getLatestModelEnsemble: async () => { throw new TransportError("Synthetic absence", 404); },
    enableModelEnsembleWatch: enableWatch,
    startModelEnsemble: start,
    ...overrides,
  };
  return render(
    <ModelEnsemblePanel
      analysisCapability={ANALYSIS_CAPABILITY}
      category="prompt-quality"
      projectId={PROJECT_ID}
      providerCompatibility={compatibility}
      sessionId={SESSION_ID}
      transport={transport}
    />,
  );
}

describe("ModelEnsemblePanel compatibility capability gate", () => {
  it.each(["exact", "compatible"] as const)("does not launch or watch prompt analysis for supported %s operational events", async (state) => {
    const start = vi.fn<PromptEnhancerTransport["startModelEnsemble"]>();
    const enableWatch = vi.fn<NonNullable<PromptEnhancerTransport["enableModelEnsembleWatch"]>>();
    renderPanel({
      ...SESSION_TEXT_COMPATIBILITY,
      capability: "operational_events",
      state,
      reason_code: state === "exact" ? "exact_match" : "compatible_version",
    }, start, enableWatch);

    const analyze = await screen.findByRole("button", { name: "Analyze metric ranges" });
    expect(analyze).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(analyze);
    fireEvent.click(screen.getByRole("button", { name: "Watch this session" }));
    expect(start).not.toHaveBeenCalled();
    expect(enableWatch).not.toHaveBeenCalled();
  });

  it.each(["exact", "compatible"] as const)("launches prompt analysis for supported %s session text", async (state) => {
    const start = vi.fn<PromptEnhancerTransport["startModelEnsemble"]>(async () => { throw new Error("Synthetic launch rejection"); });
    renderPanel({
      ...SESSION_TEXT_COMPATIBILITY,
      state,
      reason_code: state === "exact" ? "exact_match" : "compatible_version",
    }, start);

    fireEvent.click(await screen.findByRole("button", { name: "Analyze metric ranges" }));
    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    expect(start).toHaveBeenCalledWith(
      SESSION_ID,
      { confirmation: "run_local_metric_cascade_on_selected_redacted_text" },
      expect.stringMatching(/^dashboard-model-ensemble-/u),
      expect.any(AbortSignal),
    );
  });

  it("keeps Stop continuous updates available for an active operational-events watch", async () => {
    const active: ModelEnsembleWatchSnapshot = {
      watch: {
        watch_id: "d".repeat(64),
        provider: "codex",
        project_id: PROJECT_ID,
        session_id: SESSION_ID,
        max_messages: 100,
        state: "idle",
        generation: 1,
        progress_completed: 10,
        progress_total: 10,
        has_result: false,
        last_error_code: null,
        next_check_at: "2040-01-01T00:01:00Z",
        updated_at: "2040-01-01T00:00:00Z",
        serial_model_execution: true,
        process_isolated_model_release: true,
        cuda_resource_retry_on_cpu: true,
        content_persisted: false,
        calibrated_as_truth: false,
      },
      latest_run: null,
    };
    const disabled: ModelEnsembleWatchSnapshot = {
      ...active,
      watch: { ...active.watch, state: "disabled" },
    };
    const start = vi.fn<PromptEnhancerTransport["startModelEnsemble"]>();
    const enableWatch = vi.fn<NonNullable<PromptEnhancerTransport["enableModelEnsembleWatch"]>>();
    const disableWatch = vi.fn<NonNullable<PromptEnhancerTransport["disableModelEnsembleWatch"]>>(async () => disabled);
    renderPanel(
      { ...WATCH_COMPATIBILITY, capability: "operational_events" },
      start,
      enableWatch,
      {
        disableModelEnsembleWatch: disableWatch,
        getActiveModelEnsembleWatch: vi.fn(async () => active),
        getSessionModelEnsembleCanonicalHead: undefined,
      },
    );

    expect(await screen.findByRole("button", { name: "Stop continuous updates" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Stop continuous updates" }));
    await waitFor(() => expect(disableWatch).toHaveBeenCalledWith(active.watch.watch_id, expect.any(AbortSignal)));
    expect(start).not.toHaveBeenCalled();
    expect(enableWatch).not.toHaveBeenCalled();
  });
});
