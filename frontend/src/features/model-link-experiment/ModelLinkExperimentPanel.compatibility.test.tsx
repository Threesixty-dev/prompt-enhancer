import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PromptEnhancerTransport, ProviderCompatibilityStatus } from "../../shared/api/contracts";
import { parseProviderCompatibilityStatus, TransportError } from "../../shared/api/httpTransport";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { ModelLinkExperimentPanel } from "./ModelLinkExperimentPanel";

const SESSION_ID = "c".repeat(64);
const CAPABILITY = {
  available: true,
  reason_code: "available",
  data_tier: "redacted_content",
  content_persistence: false,
  network_inference: false,
  raw_transcripts: false,
} as const;
const COMPATIBILITY: ProviderCompatibilityStatus = parseProviderCompatibilityStatus({
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

function renderPanel(
  compatibility: ProviderCompatibilityStatus,
  start: PromptEnhancerTransport["startModelLinkExperiment"],
) {
  const transport: PromptEnhancerTransport = {
    ...createSyntheticTransport(),
    getLatestModelLinkExperiment: async () => { throw new TransportError("Synthetic absence", 404); },
    startModelLinkExperiment: start,
  };
  return render(
    <ModelLinkExperimentPanel
      analysisCapability={CAPABILITY}
      providerCompatibility={compatibility}
      sessionId={SESSION_ID}
      transport={transport}
    />,
  );
}

describe("ModelLinkExperimentPanel compatibility capability gate", () => {
  it.each(["exact", "compatible"] as const)("blocks supported %s operational events with the shared reason", async (state) => {
    const start = vi.fn<PromptEnhancerTransport["startModelLinkExperiment"]>();
    renderPanel({
      ...COMPATIBILITY,
      capability: "operational_events",
      state,
      reason_code: state === "exact" ? "exact_match" : "compatible_version",
    }, start);

    const run = await screen.findByRole("button", { name: "Run Qwen + BGE locally" });
    expect(run).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(
      "This compatibility result covers operational events, not session-text analysis, so prompt-text analysis stays disabled.",
    );
    fireEvent.click(run);
    expect(start).not.toHaveBeenCalled();
  });

  it.each(["exact", "compatible"] as const)("launches for supported %s session text", async (state) => {
    const start = vi.fn<PromptEnhancerTransport["startModelLinkExperiment"]>(async () => { throw new Error("Synthetic run rejection"); });
    renderPanel({
      ...COMPATIBILITY,
      state,
      reason_code: state === "exact" ? "exact_match" : "compatible_version",
    }, start);

    fireEvent.click(await screen.findByRole("button", { name: "Run Qwen + BGE locally" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith(
      SESSION_ID,
      { confirmation: "compare_selected_redacted_text_with_local_models", device: "auto" },
      expect.stringMatching(/^dashboard-model-link-experiment-/u),
      expect.any(AbortSignal),
    ));
  });
});
