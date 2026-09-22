import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentSessionView, LocalModelsOverview } from "../../shared/api/contracts";
import { AgentPage } from "./AgentPage";

const HANDOFF_ALIAS = "synthetic-handoff-model";

afterEach(() => vi.restoreAllMocks());

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => { resolve = accept; });
  return { promise, resolve };
}

function handoffTransport(sessions: AgentSessionView[] = []) {
  return {
    listAgentSessions: vi.fn(async () => sessions),
    createAgentSession: vi.fn(),
    getAgentSession: vi.fn(),
    deleteAgentSession: vi.fn(),
    sendAgentMessage: vi.fn(),
    getAgentEvents: vi.fn(async () => ({
      contract_version: "local-agent.v9" as const,
      cleanup_unconfirmed: false,
      closing: false,
      stopping: false,
      session_id: "a".repeat(32),
      events: [],
      running: false,
      pending_approval_id: null,
      last_seq: 0,
      first_seq: 0,
    })),
    decideAgentApproval: vi.fn(),
    stopAgentSession: vi.fn(),
    getAgentWorkspaceTree: vi.fn(),
    getAgentWorkspaceFile: vi.fn(),
    previewAgentWorkspaceEdit: vi.fn(),
    applyAgentWorkspaceEdit: vi.fn(),
    activateLocalModel: vi.fn(),
  };
}

function liveSession(projectId: string): AgentSessionView {
  return {
    contract_version: "local-agent.v9", cleanup_unconfirmed: false, closing: false, stopping: false,
    session_id: "a".repeat(32),
    settings: {
      workspace: "D:\\synthetic\\workspace", project_id: projectId, model_alias: null,
      parameters: { temperature: 0.2, top_p: 0.9, max_tokens: 512, enable_thinking: false },
      instructions: null, allow_writes: false, allow_commands: false, allow_web: false, max_steps: 10,
      command_timeout_seconds: 120, title: null, retention_policy: "metadata_only",
    },
    created_at: "2040-01-01T00:00:00Z", running: false, last_seq: 0, pending_approval_id: null,
    model_alias: null, turns: 0, history_revision: 0, recovered: false, authority_revalidated: false,
    history_write_failed: false, recovery_state: "current",
  };
}

function modelCatalog(): LocalModelsOverview {
  return {
    contract_version: "local-models.v1", runtime_available: true, storage_root: "D:\\synthetic\\models",
    storage_free_bytes: 10_000, download_reserve_bytes: 1, download_ledger_error_code: null, downloads: [],
    hardware: { gpu_name: null, gpu_memory_mb: null, gpu_memory_free_mb: null, ram_mb: null, llama_server_path: null, llama_server_version: null },
    models: [],
  };
}

describe("AgentPage temporary-model handoff", () => {
  it("consumes an alias once into explicit empty Agent setup without creating or starting anything", async () => {
    const transport = handoffTransport();
    const createSession = transport.createAgentSession;
    const consumed = vi.fn();
    const intent = { requestId: 41, modelAlias: HANDOFF_ALIAS };
    const view = render(
      <StrictMode><AgentPage newChatIntent={intent} onNewChatIntentConsumed={consumed} transport={transport} /></StrictMode>,
    );

    const setup = await screen.findByRole("dialog", { name: "New session" });
    expect(screen.getByLabelText("Workspace folder")).toHaveValue("");
    expect(screen.getByLabelText("Agent model")).toHaveValue(HANDOFF_ALIAS);
    expect(screen.getByRole("option", { name: `Unverified selected model · ${HANDOFF_ALIAS}` })).toBeVisible();
    expect(screen.getByRole("radio", { name: /Save locally/i })).toBeChecked();
    expect(consumed).toHaveBeenCalledOnce();
    expect(consumed).toHaveBeenCalledWith(intent.requestId);
    expect(createSession).not.toHaveBeenCalled();
    expect(transport.activateLocalModel).not.toHaveBeenCalled();
    expect(transport.sendAgentMessage).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Close new chat setup" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "New session" })).toBeNull());
    // Re-rendering the same intent (as can happen around transport/catalogue
    // refreshes) cannot reopen or overwrite a choice the owner closed.
    view.rerender(<StrictMode><AgentPage newChatIntent={intent} onNewChatIntentConsumed={consumed} transport={transport} /></StrictMode>);
    expect(screen.queryByRole("dialog", { name: "New session" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(await screen.findByLabelText("Agent model")).toHaveValue("");
    expect(createSession).not.toHaveBeenCalled();
  });

  it("keeps explicit setup open while a live-session landing and delayed model catalog settle", async () => {
    const models = deferred<LocalModelsOverview>();
    const sessions = deferred<AgentSessionView[]>();
    const transport = {
      ...handoffTransport(),
      listAgentSessions: vi.fn(() => sessions.promise),
      getLocalModels: vi.fn(() => models.promise),
    };
    render(<AgentPage newChatIntent={{ requestId: 42, modelAlias: HANDOFF_ALIAS }} transport={transport} />);

    expect(await screen.findByRole("option", { name: `Checking selected model · ${HANDOFF_ALIAS}` })).toBeVisible();
    fireEvent.change(screen.getByLabelText("Agent model"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Workspace folder"), { target: { value: "D:\\synthetic\\chosen-workspace" } });
    await act(async () => {
      sessions.resolve([liveSession("b".repeat(64))]);
      models.resolve(modelCatalog());
      await Promise.resolve();
    });

    expect(transport.listAgentSessions).toHaveBeenCalled();
    expect(transport.getLocalModels).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("dialog", { name: "New session" })).toBeVisible());
    expect(screen.getByLabelText("Agent model")).toHaveValue("");
    expect(screen.getByLabelText("Workspace folder")).toHaveValue("D:\\synthetic\\chosen-workspace");
    expect(transport.createAgentSession).not.toHaveBeenCalled();
    expect(transport.activateLocalModel).not.toHaveBeenCalled();
    expect(transport.sendAgentMessage).not.toHaveBeenCalled();
  });
});
