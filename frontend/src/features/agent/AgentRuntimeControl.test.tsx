import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  AgentCatalogSession,
  AgentSessionContextStatus,
  AgentSessionView,
  DeviceMode,
  LocalModelPlacementAdmission,
  LocalModelsOverview,
  LocalRuntimeCoordinatorStatus,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { AgentRuntimeControl } from "./AgentRuntimeControl";

const SESSION_ID = "a".repeat(32);
const PROJECT_ID = "b".repeat(32);
const MODEL_A = "example-model-a";
const MODEL_B = "example-model-b";
const initialParameters = { temperature: 0.2, top_p: 0.95, max_tokens: 1400, enable_thinking: false };

type RuntimeTransport = Partial<Pick<
  PromptEnhancerTransport,
  "getLocalRuntime" | "switchLocalRuntime" | "stopLocalRuntime"
  | "getLocalModelPlacement"
  | "getAgentCatalogSession" | "getAgentSessionContext" | "switchAgentSessionModel"
  | "getAgentSession" | "updateAgentSessionParameters"
>>;

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((accept, decline) => {
    resolve = accept;
    reject = decline;
  });
  return { promise, reject, resolve };
}

function chatContext(
  overrides: Partial<AgentSessionContextStatus> = {},
): AgentSessionContextStatus {
  return {
    contract_version: "agent-session-context.v1",
    session_id: SESSION_ID,
    revision: 0,
    binding_state: "unmeasured",
    source: "runtime_chat_template_preflight",
    unknown_reason: "no_request_measured",
    turn_id: null,
    turn_number: null,
    model_alias: null,
    observed_at: null,
    context: null,
    ...overrides,
  };
}

function measuredChatContext(): AgentSessionContextStatus {
  return chatContext({
    revision: 2,
    binding_state: "bound",
    unknown_reason: null,
    turn_id: "c".repeat(32),
    turn_number: 2,
    model_alias: MODEL_A,
    observed_at: "2040-01-01T10:02:00Z",
    context: {
      state: "known",
      used_tokens: 640,
      limit_tokens: 8192,
      requested_output_tokens: 1400,
      available_output_tokens: 7552,
      source: "runtime_chat_input_tokens",
      scope: "last_request",
      policy: "exact_admitted",
      compacted_messages: 0,
      reason_code: null,
    },
  });
}

function session(alias = MODEL_A, running = false): AgentSessionView {
  return {
    contract_version: "local-agent.v9",
    cleanup_unconfirmed: false,
    closing: false,
    stopping: false,
    session_id: SESSION_ID,
    settings: {
      workspace: "D:\\example\\project",
      project_id: PROJECT_ID,
      model_alias: alias,
      parameters: {
        temperature: 0.2,
        top_p: 0.95,
        max_tokens: 1400,
        enable_thinking: false,
      },
      instructions: null,
      allow_writes: false,
      allow_commands: false,
      allow_web: false,
      max_steps: 10,
      command_timeout_seconds: 120,
      title: "Synthetic chat",
      retention_policy: "metadata_only",
    },
    created_at: "2040-01-01T10:00:00Z",
    running,
    last_seq: 0,
    pending_approval_id: null,
    model_alias: alias,
    turns: 2,
    history_revision: 0,
    recovered: false,
    authority_revalidated: true,
    history_write_failed: false,
    recovery_state: "current",
  };
}

function catalogSession(alias = MODEL_A, revision = 4): AgentCatalogSession {
  return {
    contract_version: "agent-catalog.v2",
    session_id: SESSION_ID,
    project_id: PROJECT_ID,
    title: "Synthetic chat",
    workspace: "D:\\example\\project",
    model_alias: alias,
    created_at: "2040-01-01T10:00:00Z",
    updated_at: "2040-01-01T10:00:00Z",
    last_opened_at: "2040-01-01T10:00:00Z",
    revision,
    pinned: false,
    archived_at: null,
    history_state: "memory_only",
    retention_policy: "metadata_only",
    history_revision: 0,
    last_event_seq: 0,
    turn_count: 0,
    conversation_available: true,
    lineage: null,
  };
}

function model(alias: string, displayName: string, device: DeviceMode, contextSize: number) {
  return {
    endpoint_path: `/v1/local-models/${alias}/chat`,
    record: {
      added_at: "2040-01-01T09:00:00Z",
      alias,
      context_size: contextSize,
      default_device: device,
      display_name: displayName,
      format: "gguf" as const,
      path: `D:\\example\\models\\${alias}.gguf`,
      provenance_verified: true,
    },
    runtime: { state: "stopped" as const },
    placement: placement(alias, contextSize),
  };
}

function placement(alias: string, contextSize: number): LocalModelPlacementAdmission {
  return {
    contract_version: "local-model-placement.v1",
    alias,
    context_size: contextSize,
    gpu_memory_free_mb: 12000,
    actual_offload_verified: false,
    options: [
      { device: "gpu", state: "available", reason_code: "gpu_estimate_fits", recommended_gpu_layers: 8, estimated_vram_required_mb: 6000 },
      { device: "split", state: "available", reason_code: "split_estimate_available", recommended_gpu_layers: 6, estimated_vram_required_mb: 5000 },
      { device: "cpu", state: "available", reason_code: "cpu_available", recommended_gpu_layers: 0, estimated_vram_required_mb: 0 },
    ],
  };
}

function overview(): LocalModelsOverview {
  return {
    contract_version: "local-models.v1",
    runtime_available: true,
    storage_root: "D:\\example\\models",
    storage_free_bytes: 64 * 1024 ** 3,
    download_reserve_bytes: 512 * 1024 ** 2,
    download_ledger_error_code: null,
    downloads: [],
    hardware: {
      gpu_name: "Synthetic GPU",
      gpu_memory_mb: 16000,
      gpu_memory_free_mb: 12000,
      ram_mb: 32000,
      llama_server_path: "D:\\example\\bin\\llama-server.exe",
      llama_server_version: "synthetic-v1",
    },
    models: [
      model(MODEL_A, "Example Model A", "split", 8192),
      model(MODEL_B, "Example Model B", "cpu", 16384),
    ],
  };
}

function runtime(
  alias: string | null = MODEL_A,
  overrides: Partial<LocalRuntimeCoordinatorStatus> = {},
): LocalRuntimeCoordinatorStatus {
  const selection = alias === null ? null : {
    alias,
    device: "split" as const,
    gpu_layers: -1,
    context_size: 8192,
  };
  return {
    contract_version: "local-runtime-coordinator.v2",
    revision: 7,
    state: alias === null ? "idle" : "ready",
    requested: selection,
    served: selection === null ? null : {
      ...selection,
      pid: 4242,
      started_at: "2040-01-01T10:00:00Z",
    },
    active_requests: 0,
    cleanup: {
      state: "not_required",
      process_exit_confirmed: true,
      gpu_memory_free_before_mb: null,
      gpu_memory_free_after_mb: null,
      gpu_memory_released_mb: null,
    },
    capabilities: {
      probe_version: "local-runtime-multimodal-probe.v2",
      state: alias === null ? "not_probed" : "verified",
      text: alias !== null,
      tools: alias !== null,
      structured_output: false,
      vision: false,
      audio: false,
      recording: false,
      error_code: null,
    },
    context: {
      state: "unknown",
      used_tokens: null,
      limit_tokens: selection?.context_size ?? null,
      requested_output_tokens: null,
      available_output_tokens: null,
      source: "runtime_limit_only",
      scope: "runtime_limit",
      policy: "runtime_enforced",
      compacted_messages: 0,
      reason_code: selection === null ? "runtime_not_served" : "no_request_measured",
    },
    last_error_code: null,
    ...overrides,
  };
}

function renderControl(options: {
  current?: AgentSessionView | null;
  liveSessions?: AgentSessionView[];
  initialRuntime?: LocalRuntimeCoordinatorStatus;
  initialModels?: LocalModelsOverview | null;
  initialSessionContext?: AgentSessionContextStatus;
  contextReadFails?: boolean;
  transportOverrides?: RuntimeTransport;
  variant?: Parameters<typeof AgentRuntimeControl>[0]["variant"];
} = {}) {
  let currentRuntime = options.initialRuntime ?? runtime();
  let currentSessionContext = options.initialSessionContext ?? chatContext();
  const updated = session(MODEL_B);
  const transport = {
    getLocalRuntime: vi.fn(async () => currentRuntime),
    getLocalModelPlacement: vi.fn(async (alias: string, contextSize: number) => placement(alias, contextSize)),
    getAgentSessionContext: vi.fn(async () => {
      if (options.contextReadFails) throw new Error("synthetic context read failure");
      return currentSessionContext;
    }),
    switchLocalRuntime: vi.fn(async (request: {
      alias: string;
      device?: DeviceMode | null;
      context_size?: number | null;
    }) => {
      currentRuntime = runtime(request.alias, {
        revision: currentRuntime.revision + 1,
        requested: {
          alias: request.alias,
          device: request.device ?? "split",
          gpu_layers: request.device === "cpu" ? 0 : -1,
          context_size: request.context_size ?? 8192,
        },
        served: {
          alias: request.alias,
          device: request.device ?? "split",
          gpu_layers: request.device === "cpu" ? 0 : -1,
          context_size: request.context_size ?? 8192,
          pid: 5252,
          started_at: "2040-01-01T10:01:00Z",
        },
        context: {
          state: "unknown",
          used_tokens: null,
          limit_tokens: request.context_size ?? 8192,
          requested_output_tokens: null,
          available_output_tokens: null,
          source: "runtime_limit_only",
          scope: "runtime_limit",
          policy: "runtime_enforced",
          compacted_messages: 0,
          reason_code: "no_request_measured",
        },
      });
      return currentRuntime;
    }),
    stopLocalRuntime: vi.fn(async () => {
      currentRuntime = runtime(null, { revision: currentRuntime.revision + 1 });
      return currentRuntime;
    }),
    getAgentCatalogSession: vi.fn(async () => catalogSession()),
    getAgentSession: vi.fn(async () => session()),
    switchAgentSessionModel: vi.fn(async () => {
      currentSessionContext = chatContext({
        revision: currentSessionContext.revision + 1,
        unknown_reason: "model_changed",
      });
      return updated;
    }),
    updateAgentSessionParameters: vi.fn(async (_sessionId: string, request: { expected_project_id: string; expected_revision: number; expected_parameters: AgentSessionView["settings"]["parameters"]; parameters: AgentSessionView["settings"]["parameters"] }) => ({
      ...session(),
      settings: { ...session().settings, parameters: request.parameters },
    })),
  };
  Object.assign(transport, options.transportOverrides);
  const callbacks = {
    onBusyChange: vi.fn(),
    onModelSelected: vi.fn(),
    onModelsRefresh: vi.fn(async () => overview()),
    onRuntimeStatus: vi.fn(),
    onSessionUpdated: vi.fn(),
  };
  let current = options.current === undefined ? session() : options.current;
  let renderedModels: LocalModelsOverview | null = options.initialModels === undefined
    ? overview()
    : options.initialModels;
  let renderedTransport: RuntimeTransport = transport;
  const liveSessions = options.liveSessions ?? [session()];
  const view = () => (
    <AgentRuntimeControl
      current={current}
      disabled={false}
      liveSessions={liveSessions}
      models={renderedModels}
      {...callbacks}
      transport={renderedTransport}
      variant={options.variant}
    />
  );
  const rendered = render(view());
  return {
    callbacks,
    rendered,
    transport,
    rerenderCurrent: (next: AgentSessionView | null) => {
      current = next;
      rendered.rerender(view());
    },
    rerenderModels: (models: LocalModelsOverview | null) => {
      renderedModels = models;
      rendered.rerender(view());
    },
    rerenderTransport: (next: RuntimeTransport) => {
      renderedTransport = next;
      rendered.rerender(view());
    },
  };
}

describe("AgentRuntimeControl", () => {
  it.each(["immediate", "deferred"] as const)("abandons an unresolved settings-catalog read on chat switch and permits the reopened chat to save when its catalog resolves %s", async (resolution) => {
    const oldCatalogRead = deferred<AgentCatalogSession>();
    const reopenedCatalogRead = deferred<AgentCatalogSession>();
    const secondSessionId = "d".repeat(32);
    const secondProjectId = "e".repeat(32);
    const secondSession: AgentSessionView = {
      ...session(MODEL_B),
      session_id: secondSessionId,
      settings: { ...session(MODEL_B).settings, model_alias: MODEL_B, project_id: secondProjectId },
    };
    const getAgentCatalogSession = vi.fn((sessionId: string, _signal?: AbortSignal) => (
      sessionId === SESSION_ID
        ? oldCatalogRead.promise
        : resolution === "immediate"
          ? Promise.resolve({ ...catalogSession(MODEL_B, 9), session_id: secondSessionId, project_id: secondProjectId })
          : reopenedCatalogRead.promise
    ));
    const { rerenderCurrent, transport } = renderControl({
      variant: "composer",
      transportOverrides: { getAgentCatalogSession },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    const summary = within(panel).getByLabelText(/Model and context settings\./u);
    fireEvent.click(summary);
    await waitFor(() => expect(getAgentCatalogSession).toHaveBeenCalledWith(SESSION_ID, expect.any(AbortSignal)));
    const oldSignal = getAgentCatalogSession.mock.calls[0]?.[1] as AbortSignal;

    rerenderCurrent(secondSession);
    fireEvent.click(summary);
    fireEvent.click(summary);
    await waitFor(() => expect(getAgentCatalogSession).toHaveBeenCalledWith(secondSessionId, expect.any(AbortSignal)));
    expect(getAgentCatalogSession).toHaveBeenCalledTimes(2);
    expect(oldSignal.aborted).toBe(true);
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    fireEvent.change(screen.getByLabelText("Generation max tokens"), { target: { value: "2048" } });
    if (resolution === "deferred") {
      expect(screen.getByRole("button", { name: "Save generation settings" })).toBeDisabled();
      await act(async () => reopenedCatalogRead.resolve({
        ...catalogSession(MODEL_B, 9), session_id: secondSessionId, project_id: secondProjectId,
      }));
    }
    await waitFor(() => expect(screen.getByRole("button", { name: "Save generation settings" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Save generation settings" }));
    await waitFor(() => expect(transport.updateAgentSessionParameters).toHaveBeenCalledWith(secondSessionId, expect.objectContaining({
      expected_project_id: secondProjectId,
      expected_revision: 9,
    }), expect.any(AbortSignal)));

    await act(async () => oldCatalogRead.resolve(catalogSession()));
    expect(transport.updateAgentSessionParameters).toHaveBeenCalledTimes(1);
  });

  it("rejects a late settings-catalog response from a replaced transport", async () => {
    const oldCatalogRead = deferred<AgentCatalogSession>();
    const oldGetCatalog = vi.fn((_sessionId: string, _signal?: AbortSignal) => oldCatalogRead.promise);
    const { rerenderTransport, transport } = renderControl({
      variant: "composer",
      transportOverrides: { getAgentCatalogSession: oldGetCatalog },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    const summary = within(panel).getByLabelText(/Model and context settings\./u);
    fireEvent.click(summary);
    await waitFor(() => expect(oldGetCatalog).toHaveBeenCalledOnce());
    const oldSignal = oldGetCatalog.mock.calls[0]?.[1] as AbortSignal;
    const replacementGetCatalog = vi.fn(async () => catalogSession(MODEL_A, 10));

    rerenderTransport({ ...transport, getAgentCatalogSession: replacementGetCatalog });
    fireEvent.click(summary);
    fireEvent.click(summary);
    await waitFor(() => expect(replacementGetCatalog).toHaveBeenCalledWith(SESSION_ID, expect.any(AbortSignal)));
    expect(oldSignal.aborted).toBe(true);
    await act(async () => oldCatalogRead.resolve(catalogSession(MODEL_A, 4)));

    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    fireEvent.change(screen.getByLabelText("Generation max tokens"), { target: { value: "2048" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Save generation settings" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Save generation settings" }));
    await waitFor(() => expect(transport.updateAgentSessionParameters).toHaveBeenCalledWith(SESSION_ID, expect.objectContaining({
      expected_revision: 10,
    }), expect.any(AbortSignal)));
  });

  it("does not reuse a completed settings catalog after replacing its transport", async () => {
    const replacementCatalogRead = deferred<AgentCatalogSession>();
    const { rerenderTransport, transport } = renderControl({ variant: "composer" });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    const summary = within(panel).getByLabelText(/Model and context settings\./u);
    fireEvent.click(summary);
    await waitFor(() => expect(transport.getAgentCatalogSession).toHaveBeenCalledOnce());

    const replacementGetCatalog = vi.fn((_sessionId: string, _signal?: AbortSignal) => replacementCatalogRead.promise);
    rerenderTransport({ ...transport, getAgentCatalogSession: replacementGetCatalog });
    fireEvent.click(summary);
    fireEvent.click(summary);
    await waitFor(() => expect(replacementGetCatalog).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    fireEvent.change(screen.getByLabelText("Generation max tokens"), { target: { value: "2048" } });
    fireEvent.click(screen.getByRole("button", { name: "Save generation settings" }));
    expect(transport.updateAgentSessionParameters).not.toHaveBeenCalled();

    await act(async () => replacementCatalogRead.resolve(catalogSession(MODEL_A, 12)));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save generation settings" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Save generation settings" }));
    await waitFor(() => expect(transport.updateAgentSessionParameters).toHaveBeenCalledWith(SESSION_ID, expect.objectContaining({
      expected_revision: 12,
    }), expect.any(AbortSignal)));
  });

  it("times out a hanging settings-catalog read, then accepts only the manual retry", async () => {
    vi.useFakeTimers();
    try {
      const firstCatalogRead = deferred<AgentCatalogSession>();
      const getAgentCatalogSession = vi.fn()
        .mockImplementationOnce((_sessionId: string, _signal?: AbortSignal) => firstCatalogRead.promise)
        .mockResolvedValueOnce(catalogSession(MODEL_A, 11));
      const { transport } = renderControl({
        variant: "composer",
        transportOverrides: { getAgentCatalogSession },
      });
      const panel = screen.getByRole("region", { name: "Shared local model runtime" });
      const summary = within(panel).getByLabelText(/Model and context settings\./u);
      fireEvent.click(summary);
      await act(async () => { await Promise.resolve(); });
      const firstSignal = getAgentCatalogSession.mock.calls[0]?.[1] as AbortSignal;

      await act(async () => { await vi.advanceTimersByTimeAsync(10_000); await Promise.resolve(); });
      expect(firstSignal.aborted).toBe(true);
      expect(within(panel).getByRole("alert")).toHaveTextContent("Generation settings could not load");

      fireEvent.click(summary);
      fireEvent.click(summary);
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(getAgentCatalogSession).toHaveBeenCalledTimes(2);
      await act(async () => firstCatalogRead.resolve(catalogSession(MODEL_A, 4)));

      fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
      fireEvent.change(screen.getByLabelText("Generation max tokens"), { target: { value: "2048" } });
      expect(screen.getByRole("button", { name: "Save generation settings" })).toBeEnabled();
      fireEvent.click(screen.getByRole("button", { name: "Save generation settings" }));
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(transport.updateAgentSessionParameters).toHaveBeenCalledWith(SESSION_ID, expect.objectContaining({
        expected_revision: 11,
      }), expect.any(AbortSignal));
    } finally {
      vi.useRealTimers();
    }
  });

  it("blocks Save after a catalog failure but lets Reload restore current catalog CAS", async () => {
    const getAgentCatalogSession = vi.fn()
      .mockRejectedValueOnce(new Error("synthetic catalog failure"))
      .mockResolvedValueOnce(catalogSession(MODEL_A, 11));
    const { transport } = renderControl({
      variant: "composer",
      transportOverrides: { getAgentCatalogSession },
    });
    fireEvent.click(screen.getByRole("button", { name: /Model and context settings/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Generation settings could not load"));
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    fireEvent.change(screen.getByLabelText("Generation max tokens"), { target: { value: "2048" } });
    expect(screen.getByRole("button", { name: "Save generation settings" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Reload current settings" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save generation settings" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Save generation settings" }));
    await waitFor(() => expect(transport.updateAgentSessionParameters).toHaveBeenCalledWith(SESSION_ID, expect.objectContaining({
      expected_project_id: PROJECT_ID,
      expected_revision: 11,
    }), expect.any(AbortSignal)));
  });

  it("saves generation settings from the existing composer disclosure with catalog CAS", async () => {
    const { transport, callbacks } = renderControl({ variant: "composer" });
    fireEvent.click(screen.getByRole("button", { name: /Model and context settings/i }));
    await waitFor(() => expect(transport.getAgentCatalogSession).toHaveBeenCalledWith(SESSION_ID, expect.any(AbortSignal)));
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    fireEvent.change(screen.getByLabelText("Generation max tokens"), { target: { value: "2048" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Save generation settings" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Save generation settings" }));
    await waitFor(() => expect(transport.updateAgentSessionParameters).toHaveBeenCalledWith(SESSION_ID, expect.objectContaining({
      expected_project_id: PROJECT_ID,
      expected_revision: 4,
      expected_parameters: initialParameters,
      parameters: { ...initialParameters, max_tokens: 2048 },
    }), expect.any(AbortSignal)));
    expect(callbacks.onSessionUpdated).toHaveBeenCalled();
  });

  it("keeps model selection usable in a dismissible composer popover", async () => {
    renderControl({
      initialSessionContext: measuredChatContext(),
      variant: "composer",
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    const summary = within(panel).getByLabelText(
      "Model and context settings. Example Model A. 8% context. Ready.",
    );

    expect(summary.tagName).toBe("SUMMARY");
    expect(summary.closest("details")).not.toHaveAttribute("open");
    expect(within(panel).getByText("8% context")).toBeVisible();
    expect(within(panel).getAllByText("Ready", { exact: true })).toHaveLength(1);
    fireEvent.click(summary);

    expect(summary.closest("details")).toHaveAttribute("open");
    const chooser = within(panel).getByRole("dialog", { name: "Choose model and runtime settings" });
    expect(within(chooser).getByText("Nothing changes until Apply succeeds.", { exact: false })).toBeVisible();
    expect(within(chooser).getByLabelText("Model")).toHaveValue(MODEL_A);
    expect(within(chooser).getByLabelText("Model")).not.toHaveAccessibleDescription();
    expect(within(chooser).getByLabelText("Model placement")).toHaveValue("split");
    expect(within(chooser).getByLabelText("Context limit")).toHaveValue("8192");
    expect(within(chooser).getByRole("button", { name: "Applied" })).toBeDisabled();
    fireEvent.click(within(chooser).getByText("Context, compatibility & runtime evidence"));
    expect(within(panel).getByRole("progressbar", { name: "Exact context use" }))
      .toHaveAttribute("aria-valuenow", "8");
    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("640 input / 8192 · 7552 available · turn 2");

    fireEvent.change(within(chooser).getByLabelText("Model"), { target: { value: MODEL_B } });
    expect(within(panel).getByText("Pending change")).toBeVisible();
    await waitFor(() => expect(within(chooser).getByRole("button", { name: "Switch model" })).toBeEnabled());
    expect(summary).toHaveAccessibleName(/Example Model B.*Pending change/u);

    fireEvent.click(within(chooser).getByRole("button", { name: "Close model and context settings" }));
    expect(summary.closest("details")).not.toHaveAttribute("open");
    expect(summary).toHaveFocus();

    fireEvent.click(summary);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(summary.closest("details")).not.toHaveAttribute("open");
    expect(summary).toHaveFocus();

    fireEvent.click(summary);
    fireEvent.pointerDown(document.body);
    expect(summary.closest("details")).not.toHaveAttribute("open");
  });

  it("keeps a new chat explicitly unmeasured while reporting verified runtime capabilities", async () => {
    const { callbacks } = renderControl();
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });

    expect(within(panel).getByText("Ready")).toBeVisible();
    expect(within(panel).getAllByText(MODEL_A)).toHaveLength(2);
    const contextValue = within(panel).getByText("Context use").parentElement;
    expect(contextValue).toBeVisible();
    expect(contextValue).toHaveTextContent("not measured for this chat");
    fireEvent.click(within(panel).getByText("Runtime details"));
    expect(within(panel).getByText("Not measured for this chat")).toBeVisible();
    expect(within(panel).getByText("Text verified")).toBeVisible();
    expect(within(panel).getByText("Tools configured")).toBeVisible();
    expect(within(panel).getByText("Vision not verified")).toBeVisible();
    expect(within(panel).getByText("Audio not verified")).toBeVisible();
    expect(within(panel).getByText("Microphone not verified")).toBeVisible();
    expect(callbacks.onRuntimeStatus).toHaveBeenLastCalledWith(expect.objectContaining({
      state: "ready",
      served: expect.objectContaining({ alias: MODEL_A }),
    }));
  });

  it("shows exact evidence from this chat instead of another runtime request", async () => {
    renderControl({
      initialSessionContext: measuredChatContext(),
      initialRuntime: runtime(MODEL_A, {
        context: {
          state: "known",
          used_tokens: 2048,
          limit_tokens: 8192,
          requested_output_tokens: 1024,
          available_output_tokens: 6144,
          source: "runtime_chat_input_tokens",
          scope: "last_request",
          policy: "exact_admitted",
          compacted_messages: 0,
          reason_code: null,
        },
      }),
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    expect(within(panel).getByText("Context use").parentElement).toHaveTextContent(
      "640 input / 8192 · 7552 available · turn 2",
    );
    fireEvent.click(within(panel).getByText("Runtime details"));
    expect(within(panel).getByText("This chat · turn 2")).toBeVisible();
    expect(within(panel).getByText("exact admitted")).toBeVisible();
  });

  it("does not restart an exact context read for every streamed event sequence", async () => {
    const { rerenderCurrent, transport } = renderControl({
      initialSessionContext: measuredChatContext(),
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await waitFor(() => expect(transport.getAgentSessionContext).toHaveBeenCalledTimes(1));
    expect(within(panel).getByText("Context use").parentElement).toHaveTextContent("640 input");

    rerenderCurrent({ ...session(), last_seq: 1 });
    rerenderCurrent({ ...session(), last_seq: 2 });
    rerenderCurrent({ ...session(), last_seq: 3 });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    expect(transport.getAgentSessionContext).toHaveBeenCalledTimes(1);
    expect(within(panel).getByText("Context use").parentElement).toHaveTextContent("640 input");
  });

  it("rejects exact evidence from an older completed turn", async () => {
    renderControl({
      current: { ...session(), turns: 3 },
      initialSessionContext: measuredChatContext(),
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });

    await waitFor(() => expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("context evidence unavailable"));
    expect(within(panel).getByText("Context use").parentElement).not.toHaveTextContent("640 input");
  });

  it("shows exact overflow as refused instead of clamping it to zero available", async () => {
    renderControl({
      initialSessionContext: {
        ...measuredChatContext(),
        context: {
          ...measuredChatContext().context!,
          used_tokens: 8500,
          available_output_tokens: -308,
          policy: "exact_refused",
          reason_code: "context_window_exceeded",
        },
      },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });

    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("8500 input / 8192 · 308 over limit · refused · turn 2");
    expect(within(panel).getByRole("alert")).toHaveTextContent(
      "The exact preflight refused this request because it exceeded the context limit.",
    );
    const meter = within(panel).getByRole("progressbar", { name: "Exact context use" });
    expect(meter).toHaveAttribute("aria-valuenow", "100");
    expect(meter).toHaveAttribute("aria-valuetext", "104% exact input utilization · exact refused");
    expect(meter).toHaveAttribute("data-tone", "critical");
  });

  it("renders unknown bound evidence without inventing an estimate or zero", async () => {
    renderControl({
      initialSessionContext: {
        ...measuredChatContext(),
        context: {
          state: "unknown",
          used_tokens: null,
          limit_tokens: 8192,
          requested_output_tokens: null,
          available_output_tokens: null,
          source: "runtime_limit_only",
          scope: "runtime_limit",
          policy: "runtime_enforced",
          compacted_messages: 0,
          reason_code: "input_counter_unavailable",
        },
      },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });

    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("Unknown · no token estimate / 8192 limit · turn 2");
    expect(within(panel).queryByRole("progressbar", { name: "Exact context use" })).toBeNull();
    expect(within(panel).getByText(/No tokenizer estimate was substituted/u)).toBeVisible();
    expect(within(panel).getByText("Context use").parentElement).not.toHaveTextContent("0 input");
  });

  it("exposes exact utilization and compacted history as an accessible warning", async () => {
    renderControl({
      initialSessionContext: {
        ...measuredChatContext(),
        context: {
          ...measuredChatContext().context!,
          used_tokens: 7000,
          requested_output_tokens: 1000,
          available_output_tokens: 1192,
          policy: "exact_compacted",
          compacted_messages: 4,
        },
      },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    const meter = within(panel).getByRole("progressbar", { name: "Exact context use" });

    expect(meter).toHaveAttribute("aria-valuenow", "85");
    expect(meter).toHaveAttribute("data-tone", "caution");
    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("4 earlier messages omitted");
    expect(within(panel).getByRole("status")).toHaveTextContent(
      "The exact preflight omitted 4 earlier conversation messages before admission.",
    );
  });

  it("raises an accessible critical warning at ninety percent exact utilization", async () => {
    renderControl({
      initialSessionContext: {
        ...measuredChatContext(),
        context: {
          ...measuredChatContext().context!,
          used_tokens: 7500,
          requested_output_tokens: 500,
          available_output_tokens: 692,
        },
      },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    const meter = within(panel).getByRole("progressbar", { name: "Exact context use" });

    expect(meter).toHaveAttribute("aria-valuenow", "92");
    expect(meter).toHaveAttribute("data-tone", "critical");
    expect(within(panel).getByRole("status")).toHaveTextContent(
      "Exact input occupies 92% of the context limit.",
    );
  });

  it("keeps last-confirmed exact evidence visibly stale after a refresh failure", async () => {
    const getAgentSessionContext = vi.fn()
      .mockResolvedValueOnce(measuredChatContext())
      .mockRejectedValueOnce(new Error("synthetic refresh failure"));
    renderControl({ transportOverrides: { getAgentSessionContext } });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await waitFor(() => expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("640 input"));

    fireEvent(window, new Event("focus"));
    await waitFor(() => expect(getAgentSessionContext).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("last confirmed · refresh failed"));
    expect(within(panel).getByText("Context use").parentElement).toHaveTextContent("640 input");
  });

  it("labels retained evidence as last-confirmed while a newer receipt is loading", async () => {
    const latest = deferred<AgentSessionContextStatus>();
    const getAgentSessionContext = vi.fn()
      .mockResolvedValueOnce(measuredChatContext())
      .mockImplementationOnce(() => latest.promise);
    renderControl({ transportOverrides: { getAgentSessionContext } });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await waitFor(() => expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("640 input"));

    fireEvent(window, new Event("focus"));
    await waitFor(() => expect(getAgentSessionContext).toHaveBeenCalledTimes(2));
    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("640 input / 8192 · 7552 available · turn 2 · checking latest");
    expect(within(panel).getByText(/Showing last-confirmed context evidence while checking/u)).toBeVisible();

    await act(async () => latest.resolve({
      ...measuredChatContext(),
      revision: 3,
      context: {
        ...measuredChatContext().context!,
        used_tokens: 700,
        available_output_tokens: 7492,
      },
    }));
    await waitFor(() => expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("700 input / 8192 · 7492 available · turn 2"));
    expect(within(panel).getByText("Context use").parentElement).not.toHaveTextContent("checking latest");
  });

  it("does not fall back to global context when this chat receipt is unavailable", async () => {
    renderControl({ contextReadFails: true });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("context evidence unavailable");
    fireEvent.click(within(panel).getByText("Runtime details"));
    expect(within(panel).getByText("Unavailable for this chat")).toBeVisible();
  });

  it("reports a pending chat-context read as checking instead of claiming it is unmeasured", async () => {
    const pending = deferred<AgentSessionContextStatus>();
    renderControl({
      transportOverrides: {
        getAgentSessionContext: vi.fn(() => pending.promise),
      },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });

    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("checking this chat's context evidence");
    expect(panel).toHaveAttribute("aria-busy", "true");

    await act(async () => pending.resolve(chatContext()));
    await waitFor(() => expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("not measured for this chat"));
  });

  it("polls one pending turn preflight without depending on streamed event churn", async () => {
    const pendingContext = chatContext({
      revision: 3,
      unknown_reason: "turn_pending_preflight",
      turn_id: "d".repeat(32),
      turn_number: 2,
      model_alias: MODEL_A,
    });
    const exactContext = {
      ...measuredChatContext(),
      revision: 4,
      turn_id: "d".repeat(32),
      turn_number: 2,
    };
    const getAgentSessionContext = vi.fn()
      .mockResolvedValueOnce(pendingContext)
      .mockResolvedValueOnce(exactContext);
    renderControl({
      current: session(MODEL_A, true),
      transportOverrides: { getAgentSessionContext },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });

    await waitFor(() => expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("Measuring exact context · turn 2…"));
    await waitFor(() => expect(getAgentSessionContext).toHaveBeenCalledTimes(2), { timeout: 1_500 });
    await waitFor(() => expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("640 input / 8192 · 7552 available · turn 2"));
  });

  it("keeps a permanently pending preflight on one 10-second budget, including older receipts", async () => {
    vi.useFakeTimers();
    try {
      const pending = chatContext({
        revision: 3,
        unknown_reason: "turn_pending_preflight",
        turn_id: "d".repeat(32),
        turn_number: 2,
        model_alias: MODEL_A,
      });
      const olderPending = { ...pending, revision: 2 };
      let reads = 0;
      const getAgentSessionContext = vi.fn(async () => {
        reads += 1;
        return reads === 1 ? pending : olderPending;
      });
      renderControl({
        current: session(MODEL_A, true),
        transportOverrides: { getAgentSessionContext },
      });
      const panel = screen.getByRole("region", { name: "Shared local model runtime" });
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(getAgentSessionContext).toHaveBeenCalledOnce();

      for (let index = 0; index < 4; index += 1) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(500);
          await Promise.resolve();
          await Promise.resolve();
        });
      }
      expect(getAgentSessionContext.mock.calls.length).toBeGreaterThan(2);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(8_000);
        await Promise.resolve();
      });
      expect(panel).toHaveTextContent(/Exact context preflight did not settle within 10 seconds.*Refresh to retry/u);
      expect(panel).toHaveAttribute("aria-busy", "false");
      const readsAfterExpiry = getAgentSessionContext.mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(getAgentSessionContext).toHaveBeenCalledTimes(readsAfterExpiry);
    } finally {
      vi.useRealTimers();
    }
  });

  it("aborts a hung context read at 10 seconds and leaves context unknown", async () => {
    vi.useFakeTimers();
    try {
      const pending = deferred<AgentSessionContextStatus>();
      let signal: AbortSignal | undefined;
      const getAgentSessionContext = vi.fn((_sessionId: string, readSignal?: AbortSignal) => {
        signal = readSignal;
        return pending.promise;
      });
      renderControl({
        current: session(MODEL_A, true),
        transportOverrides: { getAgentSessionContext },
      });
      const panel = screen.getByRole("region", { name: "Shared local model runtime" });
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(signal?.aborted).toBe(false);
      expect(panel).toHaveAttribute("aria-busy", "true");

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
        await Promise.resolve();
      });
      expect(signal?.aborted).toBe(true);
      expect(panel).toHaveAttribute("aria-busy", "false");
      expect(panel).toHaveTextContent(/Exact context preflight did not settle within 10 seconds.*Refresh to retry/u);
      await act(async () => pending.resolve({
        ...measuredChatContext(),
        revision: 4,
        context: { ...measuredChatContext().context!, used_tokens: 733, available_output_tokens: 7459 },
      }));
      expect(panel).toHaveTextContent(/Exact context preflight did not settle within 10 seconds.*Refresh to retry/u);
    } finally {
      vi.useRealTimers();
    }
  });

  it("restarts an expired preflight only after explicit Refresh and adopts the exact receipt", async () => {
    vi.useFakeTimers();
    try {
      const pending = chatContext({
        revision: 3,
        unknown_reason: "turn_pending_preflight",
        turn_id: "d".repeat(32),
        turn_number: 2,
        model_alias: MODEL_A,
      });
      const exact = {
        ...measuredChatContext(),
        revision: 4,
      };
      let allowExact = false;
      const getAgentSessionContext = vi.fn(async () => allowExact ? exact : pending);
      renderControl({
        current: session(MODEL_A, true),
        transportOverrides: { getAgentSessionContext },
      });
      const panel = screen.getByRole("region", { name: "Shared local model runtime" });
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
        await Promise.resolve();
      });
      expect(panel).toHaveTextContent(/Exact context preflight did not settle within 10 seconds.*Refresh to retry/u);
      const readsBeforeRefresh = getAgentSessionContext.mock.calls.length;

      allowExact = true;
      fireEvent.click(within(panel).getByRole("button", { name: "Refresh" }));
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(getAgentSessionContext.mock.calls.length).toBeGreaterThan(readsBeforeRefresh);
      expect(within(panel).getByText("Context use").parentElement)
        .toHaveTextContent("640 input / 8192 · 7552 available · turn 2");
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops a pending preflight after a GET rejection and exposes Refresh recovery", async () => {
    vi.useFakeTimers();
    try {
      const pending = chatContext({
        revision: 3,
        unknown_reason: "turn_pending_preflight",
        turn_id: "d".repeat(32),
        turn_number: 2,
        model_alias: MODEL_A,
      });
      const getAgentSessionContext = vi.fn()
        .mockResolvedValueOnce(pending)
        .mockRejectedValueOnce(new Error("synthetic context GET failed"));
      renderControl({
        current: session(MODEL_A, true),
        transportOverrides: { getAgentSessionContext },
      });
      const panel = screen.getByRole("region", { name: "Shared local model runtime" });
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(within(panel).getByText("Context use").parentElement)
        .toHaveTextContent("Measuring exact context · turn 2…");

      await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(getAgentSessionContext).toHaveBeenCalledTimes(2);
      expect(within(panel).getByText("Context evidence could not be refreshed. It remains unknown; use Refresh to retry.")).toBeVisible();
      expect(panel).toHaveAttribute("aria-busy", "false");
      const readsAfterFailure = getAgentSessionContext.mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
      expect(getAgentSessionContext).toHaveBeenCalledTimes(readsAfterFailure);
      expect(panel).not.toHaveTextContent("Measuring exact context");
    } finally {
      vi.useRealTimers();
    }
  });

  it("announces an unresolved composer context failure once when its evidence is expanded", async () => {
    vi.useFakeTimers();
    try {
      const pending = chatContext({
        revision: 3,
        unknown_reason: "turn_pending_preflight",
        turn_id: "d".repeat(32),
        turn_number: 2,
        model_alias: MODEL_A,
      });
      const getAgentSessionContext = vi.fn()
        .mockResolvedValueOnce(pending)
        .mockRejectedValueOnce(new Error("synthetic context GET failed"));
      renderControl({
        current: session(MODEL_A, true),
        transportOverrides: { getAgentSessionContext },
        variant: "composer",
      });
      const panel = screen.getByRole("region", { name: "Shared local model runtime" });
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
        await Promise.resolve();
        await Promise.resolve();
      });

      fireEvent.click(within(panel).getByLabelText(/Model and context settings\./u));
      fireEvent.click(within(panel).getByText("Context, compatibility & runtime evidence"));
      const recovery = "Context evidence could not be refreshed. It remains unknown; use Refresh to retry.";
      expect(within(panel).getAllByRole("status").filter((node) => node.textContent === recovery)).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("fences a late context result after transport replacement", async () => {
    const oldRead = deferred<AgentSessionContextStatus>();
    let oldSignal: AbortSignal | undefined;
    const oldGet = vi.fn((_sessionId: string, signal?: AbortSignal) => {
      oldSignal = signal;
      return oldRead.promise;
    });
    const { rerenderTransport, transport } = renderControl({
      current: session(MODEL_A, true),
      transportOverrides: { getAgentSessionContext: oldGet },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await waitFor(() => expect(oldGet).toHaveBeenCalledOnce());
    const replacementGet = vi.fn(async () => measuredChatContext());
    rerenderTransport({ ...transport, getAgentSessionContext: replacementGet });
    await waitFor(() => expect(replacementGet).toHaveBeenCalledOnce());
    expect(oldSignal?.aborted).toBe(true);
    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("640 input / 8192 · 7552 available · turn 2");
    await act(async () => oldRead.resolve({
      ...measuredChatContext(),
      revision: 5,
      context: { ...measuredChatContext().context!, used_tokens: 111, available_output_tokens: 8081 },
    }));
    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("640 input / 8192 · 7552 available · turn 2");
  });

  it("fences a late context result after session, model, and turn replacement", async () => {
    const oldRead = deferred<AgentSessionContextStatus>();
    const replacementSessionId = "d".repeat(32);
    let replacement = false;
    const oldContext = chatContext({
      revision: 3,
      unknown_reason: "turn_pending_preflight",
      turn_id: "e".repeat(32),
      turn_number: 2,
      model_alias: MODEL_A,
    });
    const newContext = {
      ...measuredChatContext(),
      session_id: replacementSessionId,
      model_alias: MODEL_B,
      turn_id: "f".repeat(32),
      turn_number: 3,
    };
    const getAgentSessionContext = vi.fn(async () => replacement ? newContext : oldRead.promise);
    const { rerenderCurrent } = renderControl({
      current: session(MODEL_A, true),
      transportOverrides: { getAgentSessionContext },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await waitFor(() => expect(getAgentSessionContext).toHaveBeenCalledOnce());
    replacement = true;
    const next = {
      ...session(MODEL_B, true),
      session_id: replacementSessionId,
      model_alias: MODEL_B,
      turns: 3,
      settings: { ...session(MODEL_B, true).settings, model_alias: MODEL_B },
    };
    rerenderCurrent(next);
    await waitFor(() => expect(getAgentSessionContext).toHaveBeenCalledWith(replacementSessionId, expect.any(AbortSignal)));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("640 input / 8192 · 7552 available · turn 3");
    await act(async () => oldRead.resolve(oldContext));
    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("640 input / 8192 · 7552 available · turn 3");
  });

  it("rejects context evidence bound to a different model than the current chat", async () => {
    renderControl({
      initialSessionContext: {
        ...measuredChatContext(),
        model_alias: MODEL_B,
      },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });

    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("context evidence unavailable");
    fireEvent.click(within(panel).getByText("Runtime details"));
    expect(within(panel).getByText("Unavailable for this chat")).toBeVisible();
  });

  it("keeps the newest runtime revision when an older focus refresh resolves late", async () => {
    const first = deferred<LocalRuntimeCoordinatorStatus>();
    const second = deferred<LocalRuntimeCoordinatorStatus>();
    const getLocalRuntime = vi.fn()
      .mockImplementationOnce((_signal?: AbortSignal) => first.promise)
      .mockImplementationOnce((_signal?: AbortSignal) => second.promise);
    renderControl({ transportOverrides: { getLocalRuntime } });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(1));
    const firstSignal = getLocalRuntime.mock.calls[0]?.[0] as AbortSignal;

    fireEvent(window, new Event("focus"));
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(2));
    await act(async () => second.resolve(runtime(MODEL_B, { revision: 9 })));
    await waitFor(() => expect(within(panel).getByLabelText("Model")).toHaveValue(MODEL_B));

    await act(async () => first.resolve(runtime(MODEL_A, { revision: 8 })));
    expect(firstSignal.aborted).toBe(true);
    expect(within(panel).getByLabelText("Model")).toHaveValue(MODEL_B);
    fireEvent.click(within(panel).getByText("Runtime details"));
    expect(within(panel).getAllByText(MODEL_B)).toHaveLength(2);
  });

  it("does not mark a replacement transport stale when the old runtime read rejects late", async () => {
    const oldRead = deferred<LocalRuntimeCoordinatorStatus>();
    const oldGetRuntime = vi.fn((_signal?: AbortSignal) => oldRead.promise);
    const { rerenderTransport, transport } = renderControl({ transportOverrides: { getLocalRuntime: oldGetRuntime } });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await waitFor(() => expect(oldGetRuntime).toHaveBeenCalledTimes(1));
    const oldSignal = oldGetRuntime.mock.calls[0]?.[0] as AbortSignal;
    const replacementGetRuntime = vi.fn(async () => runtime(MODEL_B, { revision: 10 }));

    rerenderTransport({ ...transport, getLocalRuntime: replacementGetRuntime });
    await waitFor(() => expect(replacementGetRuntime).toHaveBeenCalledTimes(1));
    await act(async () => { oldRead.reject(new Error("synthetic old transport failure")); });

    expect(oldSignal.aborted).toBe(true);
    expect(panel).toHaveAttribute("data-state", "ready");
    expect(within(panel).queryByRole("alert")).toBeNull();
    expect(within(panel).getByLabelText("Model")).toHaveValue(MODEL_B);
  });

  it.each(["panel", "composer"] as const)("marks a failed runtime refresh stale and restores it only after Refresh in the %s", async (variant) => {
    const getLocalRuntime = vi.fn()
      .mockResolvedValueOnce(runtime())
      .mockRejectedValueOnce(new Error("synthetic runtime refresh failure"))
      .mockResolvedValueOnce(runtime(MODEL_B, { revision: 8 }));
    const { callbacks, transport } = renderControl({ variant, transportOverrides: { getLocalRuntime } });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(1));
    let controls = within(panel);
    if (variant === "composer") {
      fireEvent.click(within(panel).getByLabelText(/Model and context settings\./u));
      controls = within(within(panel).getByRole("dialog", { name: "Choose model and runtime settings" }));
    }

    fireEvent.change(controls.getByLabelText("Model"), { target: { value: MODEL_B } });
    fireEvent(window, new Event("focus"));
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(2));
    expect(panel).toHaveAttribute("data-state", "unavailable");
    expect(within(panel).getByRole("alert")).toHaveTextContent("Runtime status is unavailable");
    expect(controls.getByLabelText("Model")).toHaveValue(MODEL_B);
    expect(controls.getByRole("button", { name: "Switch model" })).toBeDisabled();
    if (variant === "composer") {
      expect(within(panel).getByLabelText(/Model and context settings\./u)).toHaveAttribute("data-pending-selection", "true");
    }
    expect(transport.switchLocalRuntime).not.toHaveBeenCalled();
    expect(transport.stopLocalRuntime).not.toHaveBeenCalled();
    expect(callbacks.onRuntimeStatus).toHaveBeenLastCalledWith(null);

    fireEvent.click(controls.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(panel).toHaveAttribute("data-state", "ready"));
    expect(controls.getByLabelText("Model")).toHaveValue(MODEL_B);
    expect(controls.getByRole("button", { name: "Switch model" })).toBeEnabled();
    expect(callbacks.onRuntimeStatus).toHaveBeenLastCalledWith(expect.objectContaining({
      revision: 8,
      served: expect.objectContaining({ alias: MODEL_B }),
    }));
    expect(transport.switchLocalRuntime).not.toHaveBeenCalled();
    expect(transport.stopLocalRuntime).not.toHaveBeenCalled();
  });

  it("offers Refresh after an initial runtime read failure without waiting indefinitely", async () => {
    const getLocalRuntime = vi.fn()
      .mockRejectedValueOnce(new Error("synthetic initial runtime failure"))
      .mockResolvedValueOnce(runtime(null, { revision: 8 }));
    const { transport } = renderControl({ transportOverrides: { getLocalRuntime } });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });

    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(1));
    expect(panel).toHaveAttribute("data-state", "unavailable");
    expect(within(panel).getByRole("alert")).toHaveTextContent("Retry after the local service reconnects");
    expect(within(panel).getByRole("button", { name: "Start model" })).toBeDisabled();
    expect(transport.switchLocalRuntime).not.toHaveBeenCalled();

    fireEvent.click(within(panel).getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(panel).toHaveAttribute("data-state", "idle"));
    expect(within(panel).getByRole("button", { name: "Start model" })).toBeEnabled();
  });

  it("times out a never-settling initial runtime read and recovers only from manual Refresh", async () => {
    vi.useFakeTimers();
    try {
      const initial = deferred<LocalRuntimeCoordinatorStatus>();
      const getLocalRuntime = vi.fn()
        .mockImplementationOnce((_signal?: AbortSignal) => initial.promise)
        .mockResolvedValueOnce(runtime(null, { revision: 8 }));
      const { transport } = renderControl({ transportOverrides: { getLocalRuntime } });
      const panel = screen.getByRole("region", { name: "Shared local model runtime" });
      await act(async () => { await Promise.resolve(); });
      const initialSignal = getLocalRuntime.mock.calls[0]?.[0] as AbortSignal;

      await act(async () => { await vi.advanceTimersByTimeAsync(10_000); await Promise.resolve(); await Promise.resolve(); });
      expect(initialSignal.aborted).toBe(true);
      expect(panel).toHaveAttribute("data-state", "unavailable");
      expect(within(panel).getByRole("alert")).toHaveTextContent("Retry after the local service reconnects");
      expect(within(panel).getByRole("button", { name: "Start model" })).toBeDisabled();
      expect(transport.switchLocalRuntime).not.toHaveBeenCalled();

      fireEvent.click(within(panel).getByRole("button", { name: "Refresh" }));
      await act(async () => { await Promise.resolve(); });
      expect(getLocalRuntime).toHaveBeenCalledTimes(2);
      expect(panel).toHaveAttribute("data-state", "idle");
      expect(within(panel).getByRole("button", { name: "Start model" })).toBeEnabled();

      await act(async () => { initial.resolve(runtime(MODEL_A, { revision: 99 })); });
      expect(panel).toHaveAttribute("data-state", "idle");
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps an unchanged composer choice out of pending state while its runtime snapshot is stale", async () => {
    const getLocalRuntime = vi.fn()
      .mockResolvedValueOnce(runtime())
      .mockRejectedValueOnce(new Error("synthetic runtime refresh failure"));
    renderControl({ variant: "composer", transportOverrides: { getLocalRuntime } });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    const summary = within(panel).getByLabelText(/Model and context settings\./u);
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(1));

    fireEvent(window, new Event("focus"));
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(2));
    expect(summary).toHaveAttribute("data-pending-selection", "false");
    fireEvent.click(summary);
    expect(within(panel).getByText("Context, compatibility & runtime evidence").parentElement)
      .toHaveTextContent("last confirmed");
  });

  it("keeps the last-confirmed Stop available after a hanging refresh times out", async () => {
    vi.useFakeTimers();
    try {
      const pending = deferred<LocalRuntimeCoordinatorStatus>();
      const getLocalRuntime = vi.fn()
        .mockResolvedValueOnce(runtime())
        .mockImplementationOnce((_signal?: AbortSignal) => pending.promise);
      const { transport } = renderControl({ transportOverrides: { getLocalRuntime } });
      const panel = screen.getByRole("region", { name: "Shared local model runtime" });
      await act(async () => { await Promise.resolve(); });

      fireEvent(window, new Event("focus"));
      await act(async () => { await Promise.resolve(); });
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000); await Promise.resolve(); });
      expect(panel).toHaveAttribute("data-state", "unavailable");
      fireEvent.click(within(panel).getByRole("button", { name: "Stop" }));
      await act(async () => { await Promise.resolve(); });
      expect(transport.stopLocalRuntime).toHaveBeenCalledWith({
        alias: MODEL_A,
        expected_revision: 7,
      }, expect.any(AbortSignal));
    } finally {
      vi.useRealTimers();
    }
  });

  it("clears a superseded runtime-read deadline when an exact Stop begins", async () => {
    vi.useFakeTimers();
    try {
      const pending = deferred<LocalRuntimeCoordinatorStatus>();
      const getLocalRuntime = vi.fn()
        .mockResolvedValueOnce(runtime())
        .mockImplementationOnce((_signal?: AbortSignal) => pending.promise);
      const { transport } = renderControl({ transportOverrides: { getLocalRuntime } });
      const panel = screen.getByRole("region", { name: "Shared local model runtime" });
      await act(async () => { await Promise.resolve(); });

      fireEvent(window, new Event("focus"));
      await act(async () => { await Promise.resolve(); });
      expect(vi.getTimerCount()).toBe(1);
      fireEvent.click(within(panel).getByRole("button", { name: "Stop" }));
      await act(async () => { await Promise.resolve(); });

      expect(transport.stopLocalRuntime).toHaveBeenCalledOnce();
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not clear stale status from a lower-revision retry", async () => {
    const getLocalRuntime = vi.fn()
      .mockResolvedValueOnce(runtime(MODEL_A, { revision: 9 }))
      .mockRejectedValueOnce(new Error("synthetic runtime refresh failure"))
      .mockResolvedValueOnce(runtime(MODEL_A, { revision: 8 }));
    renderControl({ transportOverrides: { getLocalRuntime } });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(1));

    fireEvent(window, new Event("focus"));
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(2));
    expect(panel).toHaveAttribute("data-state", "unavailable");
    fireEvent.click(within(panel).getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(3));

    expect(panel).toHaveAttribute("data-state", "unavailable");
    expect(within(panel).getByRole("alert")).toHaveTextContent("Runtime status is unavailable");
  });

  it("clears a superseded runtime-read deadline on transport replacement", async () => {
    vi.useFakeTimers();
    try {
      const oldRead = deferred<LocalRuntimeCoordinatorStatus>();
      const oldGetRuntime = vi.fn((_signal?: AbortSignal) => oldRead.promise);
      const { rerenderTransport, transport } = renderControl({ transportOverrides: { getLocalRuntime: oldGetRuntime } });
      const panel = screen.getByRole("region", { name: "Shared local model runtime" });
      await act(async () => { await Promise.resolve(); });
      const oldSignal = oldGetRuntime.mock.calls[0]?.[0] as AbortSignal;
      const replacementGetRuntime = vi.fn(async () => runtime(MODEL_B, { revision: 10 }));

      rerenderTransport({ ...transport, getLocalRuntime: replacementGetRuntime });
      await act(async () => { await Promise.resolve(); });
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
      expect(oldSignal.aborted).toBe(true);
      expect(panel).toHaveAttribute("data-state", "ready");
      expect(within(panel).queryByRole("alert")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("clears a runtime-read deadline after unmount without publishing a late snapshot", async () => {
    vi.useFakeTimers();
    try {
      const pending = deferred<LocalRuntimeCoordinatorStatus>();
      const getLocalRuntime = vi.fn((_signal?: AbortSignal) => pending.promise);
      const { callbacks, rendered } = renderControl({ transportOverrides: { getLocalRuntime } });
      await act(async () => { await Promise.resolve(); });
      const signal = getLocalRuntime.mock.calls[0]?.[0] as AbortSignal;
      const callsBeforeUnmount = callbacks.onRuntimeStatus.mock.calls.length;
      rendered.unmount();
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
      await act(async () => { pending.resolve(runtime(MODEL_B, { revision: 10 })); });

      expect(signal.aborted).toBe(true);
      expect(callbacks.onRuntimeStatus).toHaveBeenCalledTimes(callsBeforeUnmount);
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps an exact last-confirmed stop available while a runtime status retry is stale", async () => {
    const getLocalRuntime = vi.fn()
      .mockResolvedValueOnce(runtime())
      .mockRejectedValueOnce(new Error("synthetic runtime refresh failure"));
    const { transport } = renderControl({ transportOverrides: { getLocalRuntime } });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(1));

    fireEvent(window, new Event("focus"));
    await waitFor(() => expect(getLocalRuntime).toHaveBeenCalledTimes(2));
    expect(within(panel).getByText(/Stop will target the last confirmed example-model-a runtime at revision 7/i)).toBeVisible();
    fireEvent.click(within(panel).getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(transport.stopLocalRuntime).toHaveBeenCalledWith({
      alias: MODEL_A,
      expected_revision: 7,
    }, expect.any(AbortSignal)));
    await waitFor(() => expect(panel).toHaveAttribute("data-state", "idle"));
  });

  it("retains a runtime operation error when its status refresh succeeds", async () => {
    const switchLocalRuntime = vi.fn(async () => {
      throw new TransportError("synthetic runtime conflict", 409, "runtime_revision_conflict");
    });
    const { transport } = renderControl({ transportOverrides: { switchLocalRuntime } });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await within(panel).findByText("Ready");

    fireEvent.change(within(panel).getByLabelText("Model"), { target: { value: MODEL_B } });
    const apply = within(panel).getByRole("button", { name: "Switch model" });
    await waitFor(() => expect(apply).toBeEnabled());
    fireEvent.click(apply);
    expect(await within(panel).findByRole("alert")).toHaveTextContent("Runtime state changed in another view");
    expect(transport.getLocalRuntime).toHaveBeenCalledTimes(2);
    expect(panel).toHaveAttribute("data-state", "ready");
  });

  it("does not let an old chat-context response cross a chat switch", async () => {
    const oldRead = deferred<AgentSessionContextStatus>();
    const newRead = deferred<AgentSessionContextStatus>();
    const secondSessionId = "d".repeat(32);
    const secondSession: AgentSessionView = {
      ...session(MODEL_B),
      session_id: secondSessionId,
      settings: { ...session(MODEL_B).settings, model_alias: MODEL_B },
    };
    const getAgentSessionContext = vi.fn((sessionId: string, _signal?: AbortSignal) => (
      sessionId === SESSION_ID ? oldRead.promise : newRead.promise
    ));
    const { rerenderCurrent } = renderControl({
      transportOverrides: { getAgentSessionContext },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await waitFor(() => expect(getAgentSessionContext).toHaveBeenCalledTimes(1));
    const oldSignal = getAgentSessionContext.mock.calls[0]?.[1] as AbortSignal;

    rerenderCurrent(secondSession);
    await waitFor(() => expect(getAgentSessionContext).toHaveBeenCalledTimes(2));
    await act(async () => newRead.resolve({
      ...measuredChatContext(),
      session_id: secondSessionId,
      revision: 5,
      model_alias: MODEL_B,
      context: {
        ...measuredChatContext().context!,
        used_tokens: 900,
        available_output_tokens: 7292,
      },
    }));
    await waitFor(() => expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("900 input / 8192 · 7292 available · turn 2"));

    await act(async () => oldRead.resolve(measuredChatContext()));
    expect(oldSignal.aborted).toBe(true);
    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("900 input / 8192 · 7292 available · turn 2");
  });

  it("switches placement and context revision-safely, then rebinds the existing chat", async () => {
    const { callbacks, transport } = renderControl();
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await within(panel).findByText("Ready");

    fireEvent.change(within(panel).getByLabelText("Model"), { target: { value: MODEL_B } });
    fireEvent.change(within(panel).getByLabelText("Placement"), { target: { value: "gpu" } });
    fireEvent.change(within(panel).getByLabelText("Context limit"), { target: { value: "32768" } });
    const switchButton = within(panel).getByRole("button", { name: "Switch model" });
    await waitFor(() => expect(switchButton).toBeEnabled());
    fireEvent.click(switchButton);

    await waitFor(() => expect(transport.switchLocalRuntime).toHaveBeenCalledWith({
      alias: MODEL_B,
      expected_revision: 7,
      device: "gpu",
      gpu_layers: null,
      context_size: 32768,
      remember: true,
      fast_attention: true,
      tool_calling: true,
    }, expect.any(AbortSignal)));
    expect(transport.getAgentCatalogSession).toHaveBeenCalledWith(SESSION_ID, expect.any(AbortSignal));
    expect(transport.switchAgentSessionModel).toHaveBeenCalledWith(SESSION_ID, {
      model_alias: MODEL_B,
      expected_revision: 4,
    }, expect.any(AbortSignal));
    expect(callbacks.onSessionUpdated).toHaveBeenCalledWith(session(MODEL_B));
    expect(await within(panel).findByRole("status")).toHaveTextContent(
      "Example Model B is serving text with requested GPU placement. Actual tensor offload is not measured. This chat is bound to it.",
    );
  });

  it("uses live admission to disable unavailable GPU modes and fall back to CPU", async () => {
    const getLocalModelPlacement = vi.fn(async (alias: string, contextSize: number) => ({
      ...placement(alias, contextSize),
      gpu_memory_free_mb: null,
      options: [
        { device: "gpu" as const, state: "blocked" as const, reason_code: "accelerator_evidence_unavailable" as const, recommended_gpu_layers: null, estimated_vram_required_mb: null },
        { device: "split" as const, state: "blocked" as const, reason_code: "accelerator_evidence_unavailable" as const, recommended_gpu_layers: null, estimated_vram_required_mb: null },
        { device: "cpu" as const, state: "available" as const, reason_code: "cpu_available" as const, recommended_gpu_layers: 0, estimated_vram_required_mb: 0 },
      ],
    }));
    const { transport } = renderControl({ transportOverrides: { getLocalModelPlacement } });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });

    fireEvent.change(within(panel).getByLabelText("Model"), { target: { value: MODEL_B } });
    await waitFor(() => expect(within(panel).getByLabelText("Placement")).toHaveValue("cpu"));
    const placementSelect = within(panel).getByLabelText("Placement") as HTMLSelectElement;
    expect(within(placementSelect).getByRole("option", { name: /GPU · unavailable/ })).toBeDisabled();
    expect(within(placementSelect).getByRole("option", { name: /GPU \+ CPU · unavailable/ })).toBeDisabled();
    expect(within(panel).getByText(/no current accelerator and free-memory evidence/i)).toBeVisible();

    const switchButton = within(panel).getByRole("button", { name: "Switch model" });
    await waitFor(() => expect(switchButton).toBeEnabled());
    fireEvent.click(switchButton);
    await waitFor(() => expect(transport.switchLocalRuntime).toHaveBeenCalledWith(
      expect.objectContaining({ alias: MODEL_B, device: "cpu", gpu_layers: 0 }),
      expect.any(AbortSignal),
    ));
  });

  it("fails closed instead of crashing when a model record has no placement evidence", async () => {
    const source = overview();
    const incomplete = {
      ...source,
      models: source.models.map(({ placement: _placement, ...item }) => item),
    } as LocalModelsOverview;
    renderControl({
      initialModels: incomplete,
      transportOverrides: { getLocalModelPlacement: undefined },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });

    expect(within(panel).getByText(/Placement evidence is unavailable/u)).toBeVisible();
    expect(within(panel).getByRole("button", { name: "Applied" })).toBeDisabled();
  });

  it.each(["panel", "composer"] as const)("retries a failed live placement admission from Refresh in the %s", async (variant) => {
    const retry = deferred<LocalModelPlacementAdmission>();
    let reads = 0;
    const getLocalModelPlacement = vi.fn(async () => {
      reads += 1;
      if (reads === 1) throw new Error("synthetic placement read failure");
      return retry.promise;
    });
    renderControl({
      initialRuntime: runtime(null),
      transportOverrides: { getLocalModelPlacement },
      variant,
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    if (variant === "composer") {
      fireEvent.click(within(panel).getByLabelText(/Model and context settings\./u));
    }
    const failure = variant === "composer"
      ? "Placement admission could not be refreshed. Apply stays disabled; use Refresh to retry the check."
      : "Placement admission could not be refreshed; Apply stays disabled.";
    const checking = variant === "composer"
      ? "Checking verified placement admission. Apply stays disabled until it returns."
      : "Checking current placement admission…";

    await within(panel).findByText(failure);
    const apply = within(panel).getByRole("button", { name: "Start model" });
    expect(apply).toBeDisabled();
    expect(apply).toHaveAccessibleDescription(/verified placement admission or retry/i);

    fireEvent.click(within(panel).getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(getLocalModelPlacement).toHaveBeenCalledTimes(2));
    await within(panel).findByText(checking);
    expect(apply).toBeDisabled();

    await act(async () => retry.resolve(placement(MODEL_A, 8192)));
    await waitFor(() => expect(apply).toBeEnabled());
  });

  it("disables Start model while a live Refresh replaces previously admitted placement evidence", async () => {
    const retry = deferred<LocalModelPlacementAdmission>();
    let reads = 0;
    const getLocalModelPlacement = vi.fn(async () => {
      reads += 1;
      if (reads === 1) return placement(MODEL_A, 8192);
      return retry.promise;
    });
    renderControl({
      initialRuntime: runtime(null),
      transportOverrides: { getLocalModelPlacement },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    const apply = within(panel).getByRole("button", { name: "Start model" });
    await waitFor(() => expect(apply).toBeEnabled());
    fireEvent.click(within(panel).getByRole("button", { name: "Refresh" }));
    await within(panel).findByText("Checking current placement admission…");
    expect(apply).toBeDisabled();

    await act(async () => retry.resolve({
      ...placement(MODEL_A, 8192),
      options: [
        { device: "gpu" as const, state: "blocked" as const, reason_code: "gpu_estimate_exceeds_free_memory" as const, recommended_gpu_layers: null, estimated_vram_required_mb: null },
        { device: "split" as const, state: "blocked" as const, reason_code: "split_estimate_exceeds_free_memory" as const, recommended_gpu_layers: null, estimated_vram_required_mb: null },
        { device: "cpu" as const, state: "blocked" as const, reason_code: "context_exceeds_model_metadata" as const, recommended_gpu_layers: null, estimated_vram_required_mb: null },
      ],
    }));
    const placementSelect = within(panel).getByLabelText("Placement") as HTMLSelectElement;
    await waitFor(() => expect(within(placementSelect).getByRole("option", { name: /GPU · unavailable/ })).toBeDisabled());
    expect(apply).toBeDisabled();
  });

  it("preserves a pending runtime selection across an independently resolving model-catalog refresh", async () => {
    const { rerenderModels } = renderControl();
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await within(panel).findByText("Ready");

    fireEvent.change(within(panel).getByLabelText("Model"), { target: { value: MODEL_B } });
    fireEvent.change(within(panel).getByLabelText("Placement"), { target: { value: "gpu" } });
    fireEvent.change(within(panel).getByLabelText("Context limit"), { target: { value: "32768" } });
    rerenderModels(overview());

    expect(within(panel).getByLabelText("Model")).toHaveValue(MODEL_B);
    expect(within(panel).getByLabelText("Placement")).toHaveValue("gpu");
    expect(within(panel).getByLabelText("Context limit")).toHaveValue("32768");
    await waitFor(() => expect(within(panel).getByRole("button", { name: "Switch model" })).toBeEnabled());
  });

  it("disables runtime mutation while any chat response is active", async () => {
    const { transport } = renderControl({ liveSessions: [session(MODEL_A, true)] });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await within(panel).findByText("Ready");

    for (const label of ["Model", "Placement", "Context limit"]) {
      const control = within(panel).getByLabelText(label);
      expect(control).toBeDisabled();
      expect(control).toHaveAccessibleDescription(/finish or stop active responses/i);
      expect(control).not.toHaveAccessibleDescription(/already applied/i);
    }
    const apply = within(panel).getByRole("button", { name: "Applied" });
    const stop = within(panel).getByRole("button", { name: "Stop" });
    expect(apply).toBeDisabled();
    expect(apply).toHaveAccessibleDescription(/finish or stop active responses/i);
    expect(stop).toBeDisabled();
    expect(stop).toHaveAccessibleDescription(/finish or stop active responses/i);
    expect(within(panel).getByText(/Finish or stop active responses/)).toBeVisible();
    expect(transport.switchLocalRuntime).not.toHaveBeenCalled();
  });

  it("names the in-flight operation on the selects it disables, and drops it once settled", async () => {
    const pending = deferred<LocalRuntimeCoordinatorStatus>();
    const switchLocalRuntime = vi.fn((_request: unknown, _signal?: AbortSignal) => pending.promise);
    renderControl({ transportOverrides: { switchLocalRuntime } });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await within(panel).findByText("Ready");

    fireEvent.change(within(panel).getByLabelText("Model"), { target: { value: MODEL_B } });
    const switchButton = within(panel).getByRole("button", { name: "Switch model" });
    await waitFor(() => expect(switchButton).toBeEnabled());
    fireEvent.click(switchButton);
    await waitFor(() => expect(switchLocalRuntime).toHaveBeenCalledTimes(1));

    for (const label of ["Model", "Placement", "Context limit"]) {
      const control = within(panel).getByLabelText(label);
      expect(control).toBeDisabled();
      expect(control).toHaveAccessibleDescription(/model change is in progress/i);
      expect(control).not.toHaveAccessibleDescription(/runtime stop/i);
    }

    await act(async () => pending.resolve(runtime(MODEL_B, { revision: 8 })));
    await waitFor(() => expect(within(panel).getByLabelText("Model")).toBeEnabled());
    for (const label of ["Model", "Placement", "Context limit"]) {
      expect(within(panel).getByLabelText(label)).not.toHaveAccessibleDescription();
    }
  });

  it("offers no runtime selects or stale disabled reason when the coordinator is unavailable", async () => {
    renderControl({
      transportOverrides: {
        getLocalRuntime: undefined,
        switchLocalRuntime: undefined,
        stopLocalRuntime: undefined,
      },
    });
    const section = (await screen.findByText("Model runtime")).closest("section");

    expect(section).toHaveAttribute("data-state", "unavailable");
    expect(within(section!).getByText(/Update the local app to use coordinated placement and context controls/u))
      .toBeVisible();
    expect(screen.queryByLabelText("Model")).toBeNull();
    expect(screen.queryByLabelText("Placement")).toBeNull();
    expect(screen.queryByLabelText("Context limit")).toBeNull();
    expect(screen.queryByText(/is in progress/u)).toBeNull();
  });

  it("stops only the served revision and keeps chat state intact", async () => {
    const { callbacks, transport } = renderControl();
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await within(panel).findByText("Ready");

    fireEvent.click(within(panel).getByRole("button", { name: "Stop" }));

    await waitFor(() => expect(transport.stopLocalRuntime).toHaveBeenCalledWith({
      alias: MODEL_A,
      expected_revision: 7,
    }, expect.any(AbortSignal)));
    expect(await within(panel).findByRole("status")).toHaveTextContent(
      "Chats remain open; their drafts and messages were not changed.",
    );
    expect(callbacks.onSessionUpdated).not.toHaveBeenCalled();
    expect(within(panel).getByText("Stopped")).toBeVisible();
  });

  it("never presents unconfirmed cleanup as ready and explains the fail-closed block", async () => {
    const unsafe = runtime(null, {
      state: "cleanup_unknown",
      requested: {
        alias: MODEL_A,
        device: "gpu",
        gpu_layers: -1,
        context_size: 8192,
      },
      cleanup: {
        state: "unknown",
        process_exit_confirmed: true,
        gpu_memory_free_before_mb: 8000,
        gpu_memory_free_after_mb: null,
        gpu_memory_released_mb: null,
      },
      last_error_code: "runtime_cleanup_unconfirmed",
    });
    const { transport } = renderControl({ initialRuntime: unsafe });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });

    expect(within(panel).getByText("Cleanup unconfirmed")).toBeVisible();
    expect(within(panel).queryByText("Ready")).toBeNull();
    const start = within(panel).getByRole("button", { name: "Start model" });
    const stop = within(panel).getByRole("button", { name: "Stop" });
    expect(start).toBeDisabled();
    expect(start).toHaveAccessibleDescription(/runtime cleanup is unconfirmed/i);
    expect(stop).toBeDisabled();
    expect(stop).toHaveAccessibleDescription(/runtime cleanup is unconfirmed/i);
    expect(within(panel).getByText(/Starting or switching stays disabled/)).toBeVisible();
    expect(transport.switchLocalRuntime).not.toHaveBeenCalled();
  });

  it("blocks overlapping mutations while the coordinator is already transitioning", async () => {
    const { transport } = renderControl({
      initialRuntime: runtime(MODEL_A, { state: "loading" }),
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });

    expect(await within(panel).findByText("Loading")).toBeVisible();
    expect(within(panel).getByRole("button", { name: "Switch model" })).toBeDisabled();
    expect(within(panel).getByRole("button", { name: "Stop" })).toBeDisabled();
    expect(within(panel).getByText(/Wait for the shared runtime transition/)).toBeVisible();
    expect(transport.switchLocalRuntime).not.toHaveBeenCalled();
    expect(transport.stopLocalRuntime).not.toHaveBeenCalled();
  });

  it("aborts an in-flight model switch when the transport owner is replaced", async () => {
    const pending = deferred<LocalRuntimeCoordinatorStatus>();
    const switchLocalRuntime = vi.fn((_request: unknown, _signal?: AbortSignal) => pending.promise);
    const { callbacks, rerenderTransport, transport } = renderControl({
      transportOverrides: { switchLocalRuntime },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await within(panel).findByText("Ready");
    fireEvent.change(within(panel).getByLabelText("Model"), { target: { value: MODEL_B } });
    const switchButton = within(panel).getByRole("button", { name: "Switch model" });
    await waitFor(() => expect(switchButton).toBeEnabled());
    fireEvent.click(switchButton);
    await waitFor(() => expect(switchLocalRuntime).toHaveBeenCalledTimes(1));
    const signal = switchLocalRuntime.mock.calls[0]?.[1] as AbortSignal;

    rerenderTransport({
      ...transport,
      getLocalRuntime: vi.fn(async () => runtime(MODEL_A, { revision: 10 })),
      switchLocalRuntime: vi.fn(async () => runtime(MODEL_A, { revision: 11 })),
    });
    await waitFor(() => expect(signal.aborted).toBe(true));
    await waitFor(() => expect(within(panel).queryByText("Applying…")).toBeNull());

    await act(async () => pending.resolve(runtime(MODEL_B, { revision: 8 })));
    expect(callbacks.onSessionUpdated).not.toHaveBeenCalled();
    expect(callbacks.onRuntimeStatus).not.toHaveBeenCalledWith(expect.objectContaining({
      revision: 8,
      served: expect.objectContaining({ alias: MODEL_B }),
    }));
    expect(callbacks.onBusyChange).toHaveBeenLastCalledWith(false);
  });

  it("can retry only the chat binding after the runtime switched successfully", async () => {
    const { transport } = renderControl();
    transport.switchAgentSessionModel
      .mockRejectedValueOnce(new TransportError("synthetic stale catalog", 409, "runtime_revision_conflict"))
      .mockResolvedValueOnce(session(MODEL_B));
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await within(panel).findByText("Ready");

    fireEvent.change(within(panel).getByLabelText("Model"), { target: { value: MODEL_B } });
    const switchButton = within(panel).getByRole("button", { name: "Switch model" });
    await waitFor(() => expect(switchButton).toBeEnabled());
    fireEvent.click(switchButton);

    expect(await within(panel).findByRole("alert")).toHaveTextContent(
      "The new model is running, but this chat binding did not update.",
    );
    fireEvent.click(within(panel).getByRole("button", { name: "Bind this chat" }));

    await waitFor(() => expect(transport.switchAgentSessionModel).toHaveBeenCalledTimes(2));
    expect(transport.switchLocalRuntime).toHaveBeenCalledTimes(1);
    expect(await within(panel).findByRole("status")).toHaveTextContent("This chat is bound to it.");
  });

  it("measures a chat identity change that arrived during a stop operation", async () => {
    const pendingStop = deferred<LocalRuntimeCoordinatorStatus>();
    const stopLocalRuntime = vi.fn((_request: unknown, _signal?: AbortSignal) => pendingStop.promise);
    const nextTurnContext: AgentSessionContextStatus = {
      ...measuredChatContext(),
      revision: 3,
      turn_number: 3,
      context: {
        ...measuredChatContext().context!,
        used_tokens: 900,
        available_output_tokens: 7292,
      },
    };
    const getAgentSessionContext = vi.fn()
      .mockResolvedValueOnce(measuredChatContext())
      .mockResolvedValueOnce(nextTurnContext);
    const { rerenderCurrent } = renderControl({
      transportOverrides: { getAgentSessionContext, stopLocalRuntime },
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    await waitFor(() => expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("640 input"));

    fireEvent.click(within(panel).getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(stopLocalRuntime).toHaveBeenCalledTimes(1));
    expect(within(panel).getByLabelText("Placement"))
      .toHaveAccessibleDescription(/runtime stop is in progress/i);
    rerenderCurrent({ ...session(), turns: 3 });
    expect(getAgentSessionContext).toHaveBeenCalledTimes(1);
    expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("checking this chat's context evidence");

    await act(async () => pendingStop.resolve(runtime(null, { revision: 8 })));

    await waitFor(() => expect(getAgentSessionContext).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(within(panel).getByText("Context use").parentElement)
      .toHaveTextContent("900 input / 8192 · 7292 available · turn 3"));
    expect(panel).toHaveAttribute("aria-busy", "false");
  });

  it("dismisses the composer popover on Escape without stealing focus from the composer", async () => {
    renderControl({
      initialSessionContext: measuredChatContext(),
      variant: "composer",
    });
    const panel = await screen.findByRole("region", { name: "Shared local model runtime" });
    const summary = await within(panel).findByLabelText(
      "Model and context settings. Example Model A. 8% context. Ready.",
    );
    const outside = document.createElement("input");
    document.body.append(outside);

    try {
      fireEvent.click(summary);
      outside.focus();
      fireEvent.keyDown(outside, { key: "Escape" });

      expect(summary.closest("details")).not.toHaveAttribute("open");
      expect(outside).toHaveFocus();

      fireEvent.click(summary);
      const chooser = within(panel).getByRole("dialog", { name: "Choose model and runtime settings" });
      const modelSelect = within(chooser).getByLabelText("Model");
      modelSelect.focus();
      fireEvent.keyDown(modelSelect, { key: "Escape" });

      expect(summary.closest("details")).not.toHaveAttribute("open");
      expect(summary).toHaveFocus();
    } finally {
      outside.remove();
    }
  });
});
