import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  ModelLinkExperimentRequest,
  PromptEnhancerTransport,
  ProviderCompatibilityStatus,
} from "../../shared/api/contracts";
import {
  SYNTHETIC_MODEL_LINK_EXPERIMENT,
  SYNTHETIC_MODEL_LINK_OUTCOME,
  SYNTHETIC_QUALITY_SESSION_ID,
} from "../../shared/api/syntheticFixtures";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { TransportError } from "../../shared/api/httpTransport";
import { ModelLinkExperimentPanel } from "./ModelLinkExperimentPanel";
import {
  parseModelLinkExperiment,
  parseModelLinkOutcome,
} from "./modelLinkContract";


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

function renderPanel(transport: PromptEnhancerTransport) {
  return render(
    <ModelLinkExperimentPanel
      analysisCapability={CAPABILITY}
      providerCompatibility={EXACT}
      sessionId={SYNTHETIC_QUALITY_SESSION_ID}
      transport={transport}
    />,
  );
}

describe("ModelLinkExperimentPanel", () => {
  it("loads only content-free stored metadata and makes no experiment command on render", async () => {
    const latest = vi.fn(async () => structuredClone(SYNTHETIC_MODEL_LINK_EXPERIMENT));
    const start = vi.fn();
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getLatestModelLinkExperiment: latest,
      startModelLinkExperiment: start,
    };
    renderPanel(transport);

    expect(
      await screen.findByRole("heading", {
        name: /do the models link requests to the right agent work/i,
      }),
    ).toBeVisible();
    await waitFor(() => expect(latest).toHaveBeenCalledTimes(1));
    expect(start).not.toHaveBeenCalled();
    expect(screen.getByText(/retrieval method, not your intelligence/i)).toBeVisible();
    fireEvent.click(screen.getByText("How this experiment works"));
    expect(screen.getByRole("list", { name: "How the model experiment works" })).toBeVisible();
    expect(screen.getByText("Run locally")).toBeVisible();
    expect(screen.getByText("Review suggestions")).toBeVisible();
    expect(screen.getByText("Judge the method")).toBeVisible();
    expect(screen.queryByText(/overall score/i)).not.toBeInTheDocument();
    expect(screen.getByText(/only content-free scores and labels survive reload/i)).toBeVisible();
  });

  it("runs the fixed local experiment with one explicit button and shows transient review pairs", async () => {
    const start = vi.fn(
      async (
        _sessionId: string,
        _request: ModelLinkExperimentRequest,
        _idempotencyKey: string,
      ) => structuredClone(SYNTHETIC_MODEL_LINK_OUTCOME),
    );
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getLatestModelLinkExperiment: async () => {
        throw new TransportError("not found", 404);
      },
      startModelLinkExperiment: start,
    };
    renderPanel(transport);

    const button = await screen.findByRole("button", {
      name: "Run Qwen + BGE locally",
    });
    fireEvent.click(button);

    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    expect(start.mock.calls[0][0]).toBe(SYNTHETIC_QUALITY_SESSION_ID);
    expect(start.mock.calls[0][1]).toEqual({
      confirmation: "compare_selected_redacted_text_with_local_models",
      device: "auto",
    });
    expect(start.mock.calls[0][2]).toMatch(/^dashboard-model-link-experiment-/);
    expect(await screen.findAllByText("User request")).toHaveLength(2);
    expect(screen.getAllByText(/fictional readiness summary/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("stores a human label with the current revision and excludes unsure from precision", async () => {
    const annotate = vi.fn(async (_runId, linkId, request) => ({
      link_id: linkId,
      revision: request.expected_revision + 1,
      label: request.label,
      annotated_at: "2040-01-03T09:02:00Z",
    }));
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getLatestModelLinkExperiment: async () => {
        throw new TransportError("not found", 404);
      },
      startModelLinkExperiment: async () =>
        structuredClone(SYNTHETIC_MODEL_LINK_OUTCOME),
      annotateModelLink: annotate,
    };
    renderPanel(transport);
    fireEvent.click(
      await screen.findByRole("button", { name: "Run Qwen + BGE locally" }),
    );
    const relevant = (await screen.findAllByRole("button", {
      name: "Relevant",
    }))[0];
    fireEvent.click(relevant);

    await waitFor(() => expect(annotate).toHaveBeenCalledTimes(1));
    expect(annotate.mock.calls[0][2]).toEqual({
      label: "relevant",
      expected_revision: 0,
    });
    expect(await screen.findByText(/Qwen: 1\/1 relevant/)).toBeVisible();
    expect(screen.getByText(/Unsure is excluded/)).toBeVisible();
  });

  it("fails closed for malformed model responses without displaying injected text", async () => {
    const malformed = structuredClone(SYNTHETIC_MODEL_LINK_OUTCOME) as unknown as Record<string, unknown>;
    const experiment = malformed.experiment as Record<string, unknown>;
    experiment["private_excerpt"] = "SYNTHETIC_PRIVATE_CANARY";
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getLatestModelLinkExperiment: async () => {
        throw new TransportError("not found", 404);
      },
      startModelLinkExperiment: async () => malformed as never,
    };
    renderPanel(transport);
    fireEvent.click(
      await screen.findByRole("button", { name: "Run Qwen + BGE locally" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /did not complete/i,
    );
    expect(document.body.textContent).not.toContain("SYNTHETIC_PRIVATE_CANARY");
  });
});

describe("model-link runtime contract", () => {
  it("rejects missing provenance, extra transcript fields, and suggestions outside stored links", () => {
    const missing = structuredClone(SYNTHETIC_MODEL_LINK_EXPERIMENT) as unknown as Record<string, unknown>;
    delete (missing.run as Record<string, unknown>).qwen_model;
    expect(() => parseModelLinkExperiment(missing)).toThrow("invalid-model-link-contract");

    const extra = structuredClone(SYNTHETIC_MODEL_LINK_EXPERIMENT) as unknown as Record<string, unknown>;
    extra.transcript = "SYNTHETIC_PRIVATE_CANARY";
    expect(() => parseModelLinkExperiment(extra)).toThrow("invalid-model-link-contract");

    const outside = structuredClone(SYNTHETIC_MODEL_LINK_OUTCOME);
    outside.suggestions[0].link_id = "9".repeat(64);
    expect(() => parseModelLinkOutcome(outside)).toThrow("invalid-model-link-contract");
  });
});
