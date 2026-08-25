import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentEvent, AgentSessionView, AgentSettings, LocalModelStatus, LocalModelsOverview, PromptCheckRequest, PromptCheckResult } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { AgentPage } from "./AgentPage";
import "../../styles.css";

const SESSION = "a".repeat(32);
const APPROVAL = "b".repeat(32);
const MODEL_ALIAS = "orca27b-iq3m";
const originalPywebview = Object.getOwnPropertyDescriptor(globalThis, "pywebview");
const originalScrollIntoView = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollIntoView");

function userPresenceCapability(available: boolean) {
  return {
    contract_version: "native-user-presence-capability-v1" as const,
    confirmation_available: available,
    mode: available ? "native_bridge_bound_token" as const : "unavailable" as const,
  };
}

function installNativeFolderPicker(choose: () => Promise<unknown>): void {
  Object.defineProperty(globalThis, "pywebview", {
    configurable: true,
    value: { api: { choose_workspace_folder: choose } },
  });
}

afterEach(() => {
  if (originalPywebview) Object.defineProperty(globalThis, "pywebview", originalPywebview);
  else Reflect.deleteProperty(globalThis, "pywebview");
  if (originalScrollIntoView) Object.defineProperty(HTMLElement.prototype, "scrollIntoView", originalScrollIntoView);
  else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
});

function view(overrides: Partial<AgentSessionView> = {}): AgentSessionView {
  return {
    contract_version: "local-agent.v2" as const,
    session_id: SESSION,
    settings: { workspace: "D:\\example\\project", model_alias: null, parameters: { temperature: 0.2, top_p: 0.95, max_tokens: 1400, enable_thinking: false }, instructions: null, allow_writes: true, allow_commands: true, allow_web: false, max_steps: 10, command_timeout_seconds: 120, title: null },
    created_at: "2026-08-20T01:00:00Z",
    running: false,
    last_seq: 0,
    pending_approval_id: null,
    model_alias: MODEL_ALIAS,
    turns: 0,
    ...overrides,
  };
}

function event(seq: number, kind: AgentEvent["kind"], extra: Partial<AgentEvent> = {}): AgentEvent {
  return { seq, at: "2026-08-20T01:00:00Z", kind, text: null, tool: null, arguments: null, call_id: null, approval_id: null, ok: null, preview: null, ...extra };
}

function modelStatus(
  state: LocalModelStatus["runtime"]["state"],
  alias = MODEL_ALIAS,
  displayName = "Synthetic Local Model",
): LocalModelStatus {
  return {
    endpoint_path: `/v1/local-models/${alias}/chat`,
    record: {
      added_at: "2026-08-20T00:00:00Z",
      alias,
      context_size: 8192,
      default_device: "cpu",
      display_name: displayName,
      format: "gguf",
      path: "D:\\example\\models\\synthetic-model.gguf",
      provenance_verified: true,
    },
    runtime: { state },
  };
}

function modelsOverview(...models: LocalModelStatus[]): LocalModelsOverview {
  return {
    contract_version: "local-models.v1",
    runtime_available: true,
    storage_root: "D:\\example\\models",
    downloads: [],
    hardware: {
      gpu_name: null,
      gpu_memory_mb: null,
      gpu_memory_free_mb: null,
      ram_mb: null,
      llama_server_path: null,
      llama_server_version: null,
    },
    models,
  };
}

function workspaceMethods() {
  return {
    getAgentWorkspaceTree: vi.fn(async (sessionId: string, path: string) => ({
      contract_version: "local-agent-workspace.v1" as const,
      session_id: sessionId,
      path,
      entries: [],
      complete: true,
    })),
    getAgentWorkspaceFile: vi.fn(),
    previewAgentWorkspaceEdit: vi.fn(),
    applyAgentWorkspaceEdit: vi.fn(),
  };
}

function promptCheckResult(overrides: Partial<PromptCheckResult> = {}): PromptCheckResult {
  return {
    contract_version: "prompt-check.v1",
    check_id: "c".repeat(32),
    created_at: "2026-08-20T01:02:00Z",
    provider: "other",
    agent_model: "orca27b-iq3m",
    metrics: [{
      key: "prompt.acceptance_testability",
      display_name: "Acceptance testability",
      description: "Checkable acceptance requirements",
      state: "known",
      value: 0.5,
      numerator: 1,
      denominator: 2,
      higher_is_better: true,
      explanation_code: "observed",
      cues: [],
    }],
    context: {
      task_type: "implement",
      language: "en",
      prompt_chars: 42,
      prompt_words: 8,
      sentence_count: 1,
      bullet_count: 0,
      question_count: 0,
      file_references: 1,
      code_identifiers: 0,
      urls: 0,
      prior_context_supplied: 2,
      depends_on_prior_context: true,
      verification_requested: false,
      missing_elements: ["a checkable pass condition"],
    },
    commentary: {
      state: "ok",
      model_alias: "orca27b-iq3m",
      prompt_version: "prompt-check-commentary-v1",
      findings: [{ aspect: "verification", severity: "high", why: "No test is named.", suggestion: "Name the exact test command." }],
      reformulated_prompt: "Update example.ts and run the focused test; report the changed files and result.",
      reformulated_elements: [],
      notes: null,
      caveat: "Local-model suggestion; not measured evidence.",
    },
    summary: "The goal is visible, but verification needs a concrete pass condition.",
    engine_version: "engine-v1",
    rubric_version: "rubric-v1",
    dashboard_path: "/prompt-checks/" + "c".repeat(32),
    other_metric_families_note: "Collaboration and outcome metrics require later session evidence.",
    ...overrides,
  };
}

describe("AgentPage", () => {
  it("coalesces streamed deltas into one live bubble and replaces it with the terminal reply", async () => {
    const streamId = "c".repeat(32);
    let finishStream: (() => void) | undefined;
    const current = view({ running: true, turns: 1 });
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(), decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(async () => current),
      streamAgentEvents: vi.fn(async (_id: string, _after: number, onPage: (page: {
        contract_version: "local-agent.v2";
        session_id: string;
        events: AgentEvent[];
        running: boolean;
        pending_approval_id: string | null;
        last_seq: number;
        first_seq: number;
      }) => void) => {
        onPage({
          contract_version: "local-agent.v2",
          session_id: SESSION,
          events: [
            event(1, "user", { text: "Say hello" }),
            event(2, "assistant_delta", { text: "Hel", stream_id: streamId, stream_phase: "content" }),
            event(3, "assistant_delta", { text: "lo", stream_id: streamId, stream_phase: "content" }),
          ],
          running: true,
          pending_approval_id: null,
          last_seq: 3,
          first_seq: 1,
        });
        await new Promise<void>((resolve) => { finishStream = resolve; });
        onPage({
          contract_version: "local-agent.v2",
          session_id: SESSION,
          events: [
            event(4, "assistant", { text: "Hello", stream_id: streamId, stream_status: "complete" }),
            event(5, "done"),
          ],
          running: false,
          pending_approval_id: null,
          last_seq: 5,
          first_seq: 1,
        });
      }),
    };
    render(<AgentPage transport={transport} />);
    const live = await screen.findByLabelText("Agent response streaming");
    expect(live.textContent).toContain("Hello");
    expect(screen.getByRole("form", { name: "Message composer" })).toContainElement(
      screen.getByRole("button", { name: "Stop response" }),
    );
    finishStream?.();
    await waitFor(() => expect(screen.queryByLabelText("Agent response streaming")).toBeNull());
    expect(screen.getByText("Hello")).toBeTruthy();
    expect(transport.getAgentEvents).not.toHaveBeenCalled();
  });

  it("renders reasoning and tool execution as explicit coding-agent activity", async () => {
    const current = view({
      last_seq: 4,
      turns: 1,
      settings: {
        ...view().settings,
        parameters: { ...view().settings.parameters, enable_thinking: true },
      },
    });
    const activity = [
      event(1, "user", { text: "Inspect the synthetic project" }),
      event(2, "assistant", { text: "I inspected the requested file.", reasoning: "I should read the target before proposing a change." }),
      event(3, "tool_call", { tool: "read_file", arguments: { path: "src/example.ts" }, call_id: "synthetic-call" }),
      event(4, "tool_result", { tool: "read_file", call_id: "synthetic-call", ok: true, text: "synthetic result" }),
    ];
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: activity, running: false, pending_approval_id: null, last_seq: 4, first_seq: 1 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview(modelStatus("running"))),
    };

    render(<AgentPage transport={transport} />);

    expect(await screen.findByRole("region", { name: "Agent activity" })).toBeVisible();
    expect(await screen.findByText("Reasoning visible")).toBeVisible();
    expect(screen.getByText("model-provided · expand")).toBeVisible();
    expect(screen.getByLabelText("Agent action: Read file")).toHaveTextContent("src/example.ts");
    expect(screen.getByText("Completed").closest("summary")).toHaveTextContent("Read file");
  });

  it("creates a session, sends a message, shows tool activity and approves a write with its diff", async () => {
    let events: AgentEvent[] = [event(1, "status", { text: "Session ready in project/ - reads are free." })];
    let current = view();
    const transport = {
      ...workspaceMethods(),
      getUserPresenceCapability: vi.fn(async () => userPresenceCapability(true)),
      listAgentSessions: vi.fn(async () => (current ? [current] : [])),
      createAgentSession: vi.fn(async () => { current = view(); return current; }),
      getAgentSession: vi.fn(async () => current),
      deleteAgentSession: vi.fn(async () => undefined),
      sendAgentMessage: vi.fn(async () => {
        events = [
          ...events,
          event(2, "user", { text: "Add a noqa comment" }),
          event(3, "tool_call", { tool: "read_file", arguments: { path: "src/app.py" }, call_id: "c1" }),
          event(4, "tool_result", { tool: "read_file", call_id: "c1", ok: true, text: "def add(a, b):\n    return a + b\n" }),
          event(5, "approval_required", { tool: "write_file", arguments: { path: "src/app.py", content: "..." }, approval_id: APPROVAL, preview: "--- a/src/app.py\n+++ b/src/app.py\n-    return a + b\n+    return a + b  # noqa" }),
        ];
        current = view({ running: true, pending_approval_id: APPROVAL, last_seq: 5, turns: 1 });
        return current;
      }),
      getAgentEvents: vi.fn(async (_id: string, after: number) => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: events.filter((e) => e.seq > after), running: current.running, pending_approval_id: current.pending_approval_id, last_seq: events.length ? events[events.length - 1].seq : 0, first_seq: events.length ? events[0].seq : 0 })),
      decideAgentApproval: vi.fn(async () => {
        events = [...events, event(6, "approval_resolved", { tool: "write_file", approval_id: APPROVAL, ok: true }), event(7, "tool_result", { tool: "write_file", ok: true, text: "wrote src/app.py" }), event(8, "assistant", { text: "Done - comment added." }), event(9, "done")];
        current = view({ running: false, pending_approval_id: null, last_seq: 9, turns: 1 });
        return current;
      }),
      stopAgentSession: vi.fn(async () => current),
      getLocalModels: vi.fn(async () => modelsOverview(modelStatus("running"))),
    };
    render(<AgentPage transport={transport} />);
    await screen.findByText(/Session ready/);
    const composer = screen.getByRole("form", { name: "Message composer" });
    expect(composer).toHaveTextContent("Message to the agent");
    expect(screen.getByLabelText("Message to the agent")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Message to the agent"), { target: { value: "Add a noqa comment" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(transport.sendAgentMessage).toHaveBeenCalledWith(SESSION, "Add a noqa comment"));
    await screen.findByLabelText("Agent action: Read file");
    const approvalDialog = await screen.findByRole("alertdialog", { name: "Approval needed" });
    expect(approvalDialog.getAttribute("aria-modal")).toBe("true");
    expect(document.activeElement).toBe(approvalDialog);
    expect(screen.getByText("Approval needed for Write file.")).toBeTruthy();
    expect(screen.getByText(/return a \+ b\s+# noqa/)).toBeTruthy();
    await waitFor(() => expect(screen.getByRole("button", { name: "Approve" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(transport.decideAgentApproval).toHaveBeenCalledWith(SESSION, APPROVAL, true));
    await screen.findByText("Done - comment added.");
    expect(screen.getByText("Approved").closest(".agent__activity-event")).toHaveTextContent("Write file");
  });

  it("shows stopped models truthfully, starts the selection in place, then creates the exact session", async () => {
    const stopped = modelStatus("stopped", MODEL_ALIAS, "Synthetic 27B");
    const running = modelStatus("running", MODEL_ALIAS, "Synthetic 27B");
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => []),
      createAgentSession: vi.fn(async (settings: AgentSettings) => view({
        settings: { ...view().settings, workspace: settings.workspace, model_alias: settings.model_alias },
        model_alias: settings.model_alias,
      })),
      getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview(stopped)),
      activateLocalModel: vi.fn(async () => running),
    };
    render(<AgentPage transport={transport} />);

    expect(await screen.findByRole("option", { name: "Synthetic 27B · stopped" })).toBeVisible();
    fireEvent.change(screen.getByLabelText("Workspace folder"), { target: { value: "D:\\example\\project" } });
    fireEvent.change(screen.getByLabelText("Agent model"), { target: { value: MODEL_ALIAS } });

    expect(screen.getByText("Synthetic 27B is stopped and cannot run a session yet.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Start model first" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Start selected model" }));

    await waitFor(() => expect(transport.activateLocalModel).toHaveBeenCalledWith(MODEL_ALIAS, {
      remember: true,
      fast_attention: true,
      tool_calling: true,
    }));
    expect(await screen.findByText("Synthetic 27B is running and ready for the agent.")).toBeVisible();
    const start = screen.getByRole("button", { name: "Start read-only session" });
    expect(start).toBeEnabled();
    fireEvent.click(start);

    await waitFor(() => expect(transport.createAgentSession).toHaveBeenCalledOnce());
    expect(transport.createAgentSession.mock.calls[0][0]).toMatchObject({
      workspace: "D:\\example\\project",
      model_alias: MODEL_ALIAS,
    });
  });

  it("blocks an existing session while its model is stopped and enables the composer after activation", async () => {
    const current = view();
    const stopped = modelStatus("stopped");
    const running = modelStatus("running");
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(),
      sendAgentMessage: vi.fn(async () => view({ turns: 1 })),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview(stopped)),
      activateLocalModel: vi.fn(async () => running),
    };
    render(<AgentPage transport={transport} />);

    expect(await screen.findByText(/stopped · start it before sending/)).toBeVisible();
    const composer = screen.getByLabelText("Message to the agent");
    expect(composer).toBeDisabled();
    expect(composer).toHaveAttribute("placeholder", "Start the session model to write a message");

    fireEvent.click(screen.getByRole("button", { name: "Start session model" }));
    await waitFor(() => expect(transport.activateLocalModel).toHaveBeenCalledOnce());
    expect(await screen.findByText(/running · ready for messages/)).toBeVisible();
    expect(composer).toBeEnabled();

    fireEvent.change(composer, { target: { value: "Inspect the synthetic project" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(transport.sendAgentMessage).toHaveBeenCalledWith(SESSION, "Inspect the synthetic project"));
  });

  it("stops the exact session model without closing the session and exposes restart recovery", async () => {
    const current = view({ turns: 2 });
    const running = modelStatus("running");
    const stopped = modelStatus("stopped");
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview(running)),
      activateLocalModel: vi.fn(async () => running),
      deactivateLocalModel: vi.fn(async () => stopped),
    };

    render(<AgentPage transport={transport} />);

    const stopModel = await screen.findByRole("button", { name: "Stop model" });
    expect(stopModel).toBeEnabled();
    fireEvent.click(stopModel);

    await waitFor(() => expect(transport.deactivateLocalModel).toHaveBeenCalledWith(MODEL_ALIAS));
    expect(await screen.findByText(/stopped · start it before sending/)).toBeVisible();
    expect(screen.getByText(/sessions using it remain open but cannot send until it is restarted/i)).toBeVisible();
    expect(screen.getByLabelText("Message to the agent")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Start session model" })).toBeEnabled();
    expect(transport.deleteAgentSession).not.toHaveBeenCalled();
  });

  it("does not stop a shared model while another session is actively using it", async () => {
    const current = view({ turns: 2 });
    const other = view({ session_id: "d".repeat(32), running: true, turns: 1 });
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current, other]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview(modelStatus("running"))),
      deactivateLocalModel: vi.fn(async () => modelStatus("stopped")),
    };

    render(<AgentPage transport={transport} />);

    fireEvent.click(await screen.findByRole("button", { name: "Stop model" }));
    expect(await screen.findByText(/Stop every active response using this model/i)).toBeVisible();
    expect(transport.deactivateLocalModel).not.toHaveBeenCalled();
  });

  it("polls a starting model until it becomes ready instead of leaving the session blocked", async () => {
    const current = view();
    const getLocalModels = vi.fn()
      .mockResolvedValueOnce(modelsOverview(modelStatus("starting")))
      .mockResolvedValue(modelsOverview(modelStatus("running")));
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels,
      activateLocalModel: vi.fn(),
    };
    render(<AgentPage transport={transport} />);

    expect(await screen.findByText(/starting · start it before sending/)).toBeVisible();
    expect(screen.getByLabelText("Message to the agent")).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "Refresh model status" }).length).toBeGreaterThan(0);

    expect(await screen.findByText(/running · ready for messages/, {}, { timeout: 3000 })).toBeVisible();
    expect(getLocalModels).toHaveBeenCalledTimes(2);
    expect(screen.getByLabelText("Message to the agent")).toBeEnabled();
  });

  it("refreshes a stopped model when the Agent window regains focus", async () => {
    const current = view();
    const getLocalModels = vi.fn()
      .mockResolvedValueOnce(modelsOverview(modelStatus("stopped")))
      .mockResolvedValue(modelsOverview(modelStatus("running")));
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels,
    };
    render(<AgentPage transport={transport} />);

    expect(await screen.findByText(/stopped · start it before sending/)).toBeVisible();
    window.dispatchEvent(new Event("focus"));

    expect(await screen.findByText(/running · ready for messages/)).toBeVisible();
    expect(getLocalModels).toHaveBeenCalledTimes(2);
  });

  it("refreshes readiness after an asynchronous runtime failure event", async () => {
    const current = view({ running: true, turns: 1 });
    const getLocalModels = vi.fn()
      .mockResolvedValueOnce(modelsOverview(modelStatus("running")))
      .mockResolvedValue(modelsOverview(modelStatus("stopped")));
    const runtimeError = event(1, "error", {
      text: "The local model stopped or became unreachable. Start the session model, then send the request again.",
    });
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async (_id: string, after: number) => ({
        contract_version: "local-agent.v2" as const,
        session_id: SESSION,
        events: after < 1 ? [runtimeError, event(2, "done")] : [],
        running: false,
        pending_approval_id: null,
        last_seq: 2,
        first_seq: 1,
      })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels,
      activateLocalModel: vi.fn(async () => modelStatus("running")),
    };
    render(<AgentPage transport={transport} />);

    expect(await screen.findByText(/stopped · start it before sending/)).toBeVisible();
    expect(getLocalModels).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "Start session model" })).toBeEnabled();
    expect(screen.getByLabelText("Message to the agent")).toBeDisabled();
  });

  it("keeps the own-window composition chat-only, focused, and associated with model status", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scrollIntoView });
    const current = view();
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview(modelStatus("running"))),
    };
    const { container } = render(<AgentPage sessionId={SESSION} transport={transport} windowMode />);

    const composer = await screen.findByLabelText("Message to the agent");
    await waitFor(() => expect(composer).toHaveFocus());
    expect(composer).toHaveAttribute("aria-describedby", "agent-session-model-status");
    expect(container.querySelector(".agent__workbench")).toHaveAttribute("data-has-workspace", "false");
    expect(screen.queryByText("Files and reviewed changes")).toBeNull();
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
  });

  it("resolves a dedicated window directly when the session list does not contain its route session", async () => {
    const current = view({ turns: 1 });
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => []),
      createAgentSession: vi.fn(),
      getAgentSession: vi.fn(async () => current),
      deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview(modelStatus("running"))),
    };

    render(<AgentPage sessionId={SESSION} transport={transport} windowMode />);

    expect(await screen.findByLabelText("Message to the agent")).toBeVisible();
    expect(transport.getAgentSession).toHaveBeenCalledWith(SESSION, expect.any(AbortSignal));
    expect(screen.queryByText(/This window has no session/)).toBeNull();
  });

  it("explains when a dedicated in-memory session no longer exists", async () => {
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => []),
      createAgentSession: vi.fn(),
      getAgentSession: vi.fn(async () => { throw new TransportError("synthetic missing session", 404); }),
      deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(), getAgentEvents: vi.fn(),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview(modelStatus("running"))),
    };

    render(<AgentPage sessionId={SESSION} transport={transport} windowMode />);

    expect(await screen.findByText(/in-memory session is no longer available/i)).toBeVisible();
    expect(screen.getByRole("link", { name: "Return to Agent" })).toHaveAttribute("href", "/agent");
  });

  it("gives a model-less own-window session an explicit recovery path", async () => {
    const current = view({
      model_alias: null,
      settings: { ...view().settings, model_alias: null },
    });
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview()),
    };
    render(<AgentPage sessionId={SESSION} transport={transport} windowMode />);

    expect(await screen.findByText("No local model is running for this session. Start one on the Models page.")).toBeVisible();
    const recovery = screen.getByRole("link", { name: "Open Models" });
    expect(recovery).toHaveAttribute("href", "/models");
    expect(screen.getByLabelText("Message to the agent")).toBeDisabled();
  });

  it("keeps session-creation capacity feedback beside the New session form", async () => {
    const current = view();
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(async () => { throw new TransportError("synthetic rejection", 409, "too_many_sessions"); }),
      getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview(modelStatus("running"))),
    };
    render(<AgentPage transport={transport} />);

    await screen.findByText(/running · ready for messages/);
    fireEvent.change(screen.getByLabelText("Workspace folder"), { target: { value: "D:\\example\\second-project" } });
    const start = screen.getByRole("button", { name: "Start read-only session" });
    fireEvent.click(start);

    const error = await screen.findByText("Too many open sessions - close one first.");
    expect(start.closest("form")).toContainElement(error);
    expect(start).toHaveAttribute("aria-describedby", "agent-create-error");
    expect(screen.getByLabelText("Message to the agent")).toHaveAttribute("aria-describedby", "agent-session-model-status");
  });

  it("explains a model-readiness race instead of misreporting session capacity", async () => {
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => []),
      createAgentSession: vi.fn(async () => { throw new TransportError("synthetic rejection", 409, "model_not_ready"); }),
      getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(), decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview(modelStatus("running"))),
    };
    render(<AgentPage transport={transport} />);

    await screen.findByText(/running and ready/);
    fireEvent.change(screen.getByLabelText("Workspace folder"), { target: { value: "D:\\example\\project" } });
    fireEvent.click(screen.getByRole("button", { name: "Start read-only session" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("selected model is not running");
    expect(document.body).not.toHaveTextContent("Too many open sessions");
  });

  it.each([
    ["model_not_ready" as const, /session's model is stopped/i],
    ["no_active_model" as const, /No local model is running/i],
    ["turn_in_progress" as const, /already working on a turn/i],
  ])("shows an actionable %s send failure", async (reasonCode, expected) => {
    const current = view();
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(),
      sendAgentMessage: vi.fn(async () => { throw new TransportError("synthetic rejection", 409, reasonCode); }),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview(modelStatus("running"))),
    };
    render(<AgentPage transport={transport} />);

    const composer = await screen.findByLabelText("Message to the agent");
    await waitFor(() => expect(composer).toBeEnabled());
    fireEvent.change(composer, { target: { value: "Synthetic request" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
  });

  it("clears turn feedback when the user switches to a different session", async () => {
    const first = view({ settings: { ...view().settings, title: "Session A" } });
    const second = view({
      session_id: "d".repeat(32),
      settings: { ...view().settings, title: "Session B" },
    });
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [first, second]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(),
      sendAgentMessage: vi.fn(async () => { throw new TransportError("synthetic rejection", 409, "model_not_ready"); }),
      getAgentEvents: vi.fn(async (sessionId: string) => ({ contract_version: "local-agent.v2" as const, session_id: sessionId, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      getLocalModels: vi.fn(async () => modelsOverview(modelStatus("running"))),
    };
    render(<AgentPage transport={transport} />);

    const composer = await screen.findByLabelText("Message to the agent");
    await waitFor(() => expect(composer).toBeEnabled());
    fireEvent.change(composer, { target: { value: "Synthetic request" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("session's model is stopped");
    expect(composer).toHaveAttribute("aria-describedby", "agent-session-model-status agent-message-error");

    fireEvent.click(screen.getByText("Session B").closest("button")!);
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(screen.getByLabelText("Message to the agent")).toHaveAttribute("aria-describedby", "agent-session-model-status");
  });

  it("explains when the agent is unavailable and lets a new session be created", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scrollIntoView });
    const transport = {
      ...workspaceMethods(),
      getUserPresenceCapability: vi.fn(async () => userPresenceCapability(false)),
      listAgentSessions: vi.fn(async () => []),
      createAgentSession: vi.fn(async (settings: AgentSettings) => view({ settings: { ...view().settings, workspace: settings.workspace } })),
      getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
    };
    render(<AgentPage transport={transport} />);
    await screen.findByText(/No session yet/);
    await screen.findByText(/This browser can start read-only sessions/);
    fireEvent.change(screen.getByLabelText("Workspace folder"), { target: { value: "D:\\example\\project" } });
    fireEvent.click(screen.getByRole("button", { name: "Start read-only session" }));
    await waitFor(() => expect(transport.createAgentSession).toHaveBeenCalled());
    expect(await screen.findByText(/Session ready\. Write your first request below\./)).toBeVisible();
    expect(screen.getByLabelText("Message to the agent")).toHaveFocus();
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
    const settings = transport.createAgentSession.mock.calls[0][0];
    expect(settings.workspace).toBe("D:\\example\\project");
    expect(settings.allow_writes).toBe(false);
    expect(settings.allow_commands).toBe(false);
    expect(settings.allow_web).toBe(false);
  });

  it("uses the native folder picker without reading files and preserves the path on cancel", async () => {
    const choose = vi.fn()
      .mockResolvedValueOnce({
        version: "native-folder-picker-v1",
        status: "selected",
        path: "D:\\example\\chosen-workspace",
      })
      .mockResolvedValueOnce({
        version: "native-folder-picker-v1",
        status: "cancelled",
      });
    installNativeFolderPicker(choose);
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => []),
      createAgentSession: vi.fn(async (_settings: AgentSettings) => view({
        settings: { ...view().settings, workspace: "D:\\example\\chosen-workspace", allow_writes: false, allow_commands: false, allow_web: false },
      })),
      getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(), decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
    };
    render(<AgentPage transport={transport} />);

    const workspace = screen.getByLabelText("Workspace folder");
    const browse = screen.getByRole("button", { name: "Browse…" });
    expect(browse).toBeEnabled();
    expect(getComputedStyle(workspace).cursor).not.toBe("pointer");
    expect(getComputedStyle(browse).cursor).toBe("pointer");

    fireEvent.click(browse);
    await waitFor(() => expect(workspace).toHaveValue("D:\\example\\chosen-workspace"));
    expect(screen.getByText("Workspace folder selected.")).toBeVisible();

    fireEvent.click(browse);
    await screen.findByText("Folder selection cancelled. The workspace path was not changed.");
    expect(workspace).toHaveValue("D:\\example\\chosen-workspace");
    expect(choose).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole("button", { name: "Start read-only session" }));
    await waitFor(() => expect(transport.createAgentSession).toHaveBeenCalledOnce());
    expect(transport.createAgentSession.mock.calls[0][0]).toMatchObject({
      workspace: "D:\\example\\chosen-workspace",
      allow_writes: false,
      allow_commands: false,
      allow_web: false,
    });
  });

  it("enables Browse when the native bridge becomes ready after the form renders", async () => {
    Reflect.deleteProperty(globalThis, "pywebview");
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => []),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(), decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
    };
    render(<AgentPage transport={transport} />);
    expect(screen.getByRole("button", { name: "Browse…" })).toBeDisabled();

    installNativeFolderPicker(vi.fn().mockResolvedValue({
      version: "native-folder-picker-v1",
      status: "cancelled",
    }));
    window.dispatchEvent(new Event("pywebviewready"));

    await waitFor(() => expect(screen.getByRole("button", { name: "Browse…" })).toBeEnabled());
  });

  it("keeps protected scopes off while checking, then enables explicit choices only", async () => {
    let resolveCapability!: (value: ReturnType<typeof userPresenceCapability>) => void;
    const capability = new Promise<ReturnType<typeof userPresenceCapability>>((resolve) => {
      resolveCapability = resolve;
    });
    const transport = {
      ...workspaceMethods(),
      getUserPresenceCapability: vi.fn(() => capability),
      listAgentSessions: vi.fn(async () => []),
      createAgentSession: vi.fn(async (_settings: AgentSettings) => view()),
      getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(), decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
    };
    render(<AgentPage transport={transport} />);

    fireEvent.change(screen.getByLabelText("Workspace folder"), { target: { value: "D:\\example\\project" } });
    expect(screen.getByText("Checking whether native confirmation is available…")).toBeVisible();
    expect(screen.getByRole("button", { name: "Start read-only session" })).toBeDisabled();
    expect(screen.getByLabelText(/May write files/i)).toBeDisabled();

    await act(async () => resolveCapability(userPresenceCapability(true)));
    await waitFor(() => expect(screen.getByLabelText(/May write files/i)).toBeEnabled());
    expect(screen.getByLabelText(/May write files/i)).not.toBeChecked();
    expect(screen.getByLabelText(/May run commands/i)).not.toBeChecked();
    expect(screen.getByLabelText(/May fetch web pages/i)).not.toBeChecked();

    fireEvent.click(screen.getByLabelText(/May write files/i));
    fireEvent.click(screen.getByLabelText(/May fetch web pages/i));
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));
    await waitFor(() => expect(transport.createAgentSession).toHaveBeenCalledOnce());
    expect(transport.createAgentSession.mock.calls[0][0]).toMatchObject({
      workspace: "D:\\example\\project",
      allow_writes: true,
      allow_commands: false,
      allow_web: true,
    });
  });

  it("fails closed on a capability error and exposes a retry plus the Windows launcher", async () => {
    const getUserPresenceCapability = vi.fn()
      .mockRejectedValueOnce(new Error("synthetic capability failure"))
      .mockResolvedValueOnce(userPresenceCapability(false));
    const transport = {
      ...workspaceMethods(),
      getUserPresenceCapability,
      listAgentSessions: vi.fn(async () => []),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(), decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
    };
    render(<AgentPage transport={transport} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Native confirmation could not be verified");
    expect(screen.getByLabelText(/May write files/i)).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Retry confirmation check" }));

    await screen.findByText(/This browser can start read-only sessions/);
    expect(screen.getByText("prompt-enhancer agent-desktop")).toBeVisible();
    expect(screen.getByRole("button", { name: "Start read-only session" })).toBeDisabled();
    expect(getUserPresenceCapability).toHaveBeenCalledTimes(2);
  });

  it.each([
    [422, /not an existing folder/i],
    [403, /outside the allowed workspace roots/i],
  ])("associates a %s workspace failure with the folder field", async (status, expected) => {
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => []),
      createAgentSession: vi.fn(async () => { throw new TransportError("synthetic rejection", status); }),
      getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(), decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
    };
    render(<AgentPage transport={transport} />);

    const workspace = screen.getByLabelText("Workspace folder");
    fireEvent.change(workspace, { target: { value: "D:\\example\\rejected" } });
    fireEvent.click(screen.getByRole("button", { name: "Start read-only session" }));

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent(expected);
    expect(workspace).toHaveAttribute("aria-invalid", "true");
    expect(workspace).toHaveAttribute("aria-errormessage", error.id);
    expect(workspace).toHaveFocus();
  });

  it("sends the chosen model parameters and standing instructions", async () => {
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => []),
      createAgentSession: vi.fn(async () => view()),
      getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
    };
    render(<AgentPage transport={transport} />);
    await screen.findByText(/No session yet/);
    fireEvent.change(screen.getByLabelText("Workspace folder"), { target: { value: "D:\\example\\project" } });
    fireEvent.change(screen.getByLabelText("Temperature"), { target: { value: "0.7" } });
    fireEvent.change(screen.getByLabelText("Max tokens"), { target: { value: "2048" } });
    fireEvent.click(screen.getByLabelText(/Thinking mode/));
    fireEvent.change(screen.getByLabelText("Standing instructions"), { target: { value: "Answer in Polish." } });
    fireEvent.click(screen.getByRole("button", { name: "Start read-only session" }));
    await waitFor(() => expect(transport.createAgentSession).toHaveBeenCalled());
    const settings = (transport.createAgentSession.mock.calls[0] as unknown[])[0] as {
      parameters: { temperature: number; max_tokens: number; enable_thinking: boolean };
      instructions: string | null;
    };
    expect(settings.parameters.temperature).toBeCloseTo(0.7);
    expect(settings.parameters.max_tokens).toBe(2048);
    expect(settings.parameters.enable_thinking).toBe(true);
    expect(settings.instructions).toBe("Answer in Polish.");
  });

  it("checks a draft with conversational context without sending it, then applies the suggested rewrite", async () => {
    const priorEvents = [
      event(1, "user", { text: "Earlier request" }),
      event(2, "tool_result", { text: "private tool output must not become prompt context", tool: "read_file", ok: true }),
      event(3, "assistant", { text: "Earlier response" }),
    ];
    const current = view({ last_seq: 3, turns: 1 });
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: priorEvents, running: false, pending_approval_id: null, last_seq: 3, first_seq: 1 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      checkPrompt: vi.fn(async (_request: PromptCheckRequest, _signal?: AbortSignal) => promptCheckResult()),
    };
    render(<AgentPage transport={transport} />);
    await screen.findByText("Earlier response");

    fireEvent.change(screen.getByLabelText("Message to the agent"), { target: { value: "Update example.ts" } });
    fireEvent.click(screen.getByRole("button", { name: "Check & improve" }));

    await waitFor(() => expect(transport.checkPrompt).toHaveBeenCalledTimes(1));
    const request = transport.checkPrompt.mock.calls[0][0];
    expect(request).toMatchObject({
      prompt: "Update example.ts",
      prior_messages: [
        { role: "user", content: "Earlier request" },
        { role: "assistant", content: "Earlier response" },
      ],
      session_id: null,
      provider: "other",
      agent_model: "orca27b-iq3m",
      want_commentary: true,
    });
    expect(transport.sendAgentMessage).not.toHaveBeenCalled();
    expect(await screen.findByText("Before the agent acts")).toBeTruthy();
    expect(screen.getByText("a checkable pass condition")).toBeTruthy();
    expect(screen.getByText(/Name the exact test command/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Use suggested prompt" }));
    expect((screen.getByLabelText("Message to the agent") as HTMLTextAreaElement).value).toBe("Update example.ts and run the focused test; report the changed files and result.");
    expect(screen.queryByText("Before the agent acts")).toBeNull();
    expect(screen.getByText(/Check it again to validate/)).toBeTruthy();
  });

  it("aborts a stale prompt check when the draft changes and never renders its late result", async () => {
    let resolveCheck: ((result: PromptCheckResult) => void) | undefined;
    let receivedSignal: AbortSignal | undefined;
    const current = view();
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      checkPrompt: vi.fn((_request: unknown, signal?: AbortSignal) => {
        receivedSignal = signal;
        return new Promise<PromptCheckResult>((resolve) => { resolveCheck = resolve; });
      }),
    };
    render(<AgentPage transport={transport} />);
    await screen.findByLabelText("Message to the agent");
    fireEvent.change(screen.getByLabelText("Message to the agent"), { target: { value: "First draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Check & improve" }));
    await waitFor(() => expect(transport.checkPrompt).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("Message to the agent"), { target: { value: "Second draft" } });
    expect(receivedSignal?.aborted).toBe(true);
    resolveCheck?.(promptCheckResult());
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryByText("Before the agent acts")).toBeNull();
  });

  it("keeps prompt-check failures content-free", async () => {
    const current = view();
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v2" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
      checkPrompt: vi.fn(async () => { throw new Error("synthetic-secret-canary"); }),
    };
    render(<AgentPage transport={transport} />);
    await screen.findByLabelText("Message to the agent");
    fireEvent.change(screen.getByLabelText("Message to the agent"), { target: { value: "Review example.ts" } });
    fireEvent.click(screen.getByRole("button", { name: "Check & improve" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The prompt check did not run. Your draft was not changed.");
    expect(document.body.textContent).not.toContain("synthetic-secret-canary");
  });

  it("caps failed live-stream reconnects and requires an explicit retry", async () => {
    vi.useFakeTimers();
    const current = view({ running: true, turns: 1 });
    const transport = {
      ...workspaceMethods(),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(), getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(), decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(async () => current),
      streamAgentEvents: vi.fn(async () => { throw new Error("synthetic stream failure"); }),
    };
    try {
      render(<AgentPage transport={transport} />);
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(transport.streamAgentEvents).toHaveBeenCalledTimes(1);

      for (let attempt = 1; attempt < 5; attempt += 1) {
        await act(async () => { await vi.runOnlyPendingTimersAsync(); });
      }
      expect(transport.streamAgentEvents).toHaveBeenCalledTimes(5);
      expect(screen.getByText(/Live updates paused after repeated connection failures/)).toBeTruthy();

      await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
      expect(transport.streamAgentEvents).toHaveBeenCalledTimes(5);

      fireEvent.click(screen.getByRole("button", { name: "Retry live updates" }));
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(transport.streamAgentEvents).toHaveBeenCalledTimes(6);
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps tool decisions and new mutation scopes disabled without native presence", async () => {
    const pendingEvent = event(1, "approval_required", {
      tool: "write_file",
      arguments: { path: "src/example.py" },
      approval_id: APPROVAL,
      preview: "--- a/src/example.py\n+++ b/src/example.py\n-old\n+new",
    });
    const current = view({ running: true, pending_approval_id: APPROVAL, last_seq: 1 });
    const transport = {
      ...workspaceMethods(),
      getUserPresenceCapability: vi.fn(async () => ({
        contract_version: "native-user-presence-capability-v1" as const,
        confirmation_available: false,
        mode: "unavailable" as const,
      })),
      listAgentSessions: vi.fn(async () => [current]),
      createAgentSession: vi.fn(),
      getAgentSession: vi.fn(async () => current),
      deleteAgentSession: vi.fn(),
      sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({
        contract_version: "local-agent.v2" as const,
        session_id: SESSION,
        events: [pendingEvent],
        running: true,
        pending_approval_id: APPROVAL,
        last_seq: 1,
        first_seq: 1,
      })),
      decideAgentApproval: vi.fn(),
      stopAgentSession: vi.fn(async () => current),
    };
    render(<AgentPage sessionId={SESSION} transport={transport} />);

    const dialog = await screen.findByRole("alertdialog", { name: "Approval needed" });
    expect(dialog).toHaveTextContent(/cannot be decided until the app is opened/i);
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Deny" })).toBeDisabled();
    await waitFor(() => expect(screen.getByLabelText(/May write files/i)).not.toBeChecked());
    expect(screen.getByLabelText(/May write files/i)).toBeDisabled();
    expect(screen.getByLabelText(/May run commands/i)).toBeDisabled();
    expect(screen.getByLabelText(/May fetch web pages/i)).toBeDisabled();
    expect(transport.decideAgentApproval).not.toHaveBeenCalled();
  });
});
