import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import type { AgentEvent, AgentEvents, AgentSessionView, LocalModelStatus, LocalModelsOverview } from "../../shared/api/contracts";
import { AgentPage } from "./AgentPage";
import { agentExitRisk, sameAgentExitRisk } from "./agentExitRisk";

describe("Agent exit risk", () => {
  it("maps an aggregate draft flag to unsaved risk", () => {
    expect(agentExitRisk({ hasDrafts: true, workspaceDirty: false, hasObservedWork: false }))
      .toEqual({ hasUnsavedChanges: true, hasActiveWork: false });
  });

  it("keeps aggregate unsaved and active-work dimensions separate", () => {
    expect(agentExitRisk({ hasDrafts: true, workspaceDirty: true, hasObservedWork: false }))
      .toEqual({ hasUnsavedChanges: true, hasActiveWork: false });
  });

  it("maps observed work independently from unsaved risk", () => {
    expect(agentExitRisk({ hasDrafts: false, workspaceDirty: false, hasObservedWork: true }))
      .toEqual({ hasUnsavedChanges: false, hasActiveWork: true });
  });

  it("compares only the two non-content booleans", () => {
    expect(sameAgentExitRisk({ hasUnsavedChanges: true, hasActiveWork: false }, { hasUnsavedChanges: true, hasActiveWork: false })).toBe(true);
    expect(sameAgentExitRisk({ hasUnsavedChanges: true, hasActiveWork: false }, { hasUnsavedChanges: false, hasActiveWork: false })).toBe(false);
  });

  it("reports a whitespace no-model draft, guards unload, replaces callbacks, and clears only on real unmount", async () => {
    const first = vi.fn();
    const second = vi.fn();
    const stableTransport = transport(session());
    const view = render(<StrictMode><AgentPage onExitRiskChange={first} transport={stableTransport} /></StrictMode>);
    const composer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(composer, { target: { value: "   " } });
    await waitFor(() => expect(first).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false }));
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    view.rerender(<StrictMode><AgentPage onExitRiskChange={second} transport={stableTransport} /></StrictMode>);
    await waitFor(() => expect(second).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false }));
    expect(second.mock.calls).not.toContainEqual([{ hasUnsavedChanges: false, hasActiveWork: false }]);
    fireEvent.change(screen.getByRole("textbox", { name: "Message to the agent" }), { target: { value: "" } });
    await waitFor(() => expect(second).toHaveBeenLastCalledWith({ hasUnsavedChanges: false, hasActiveWork: false }));
    const clearedUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clearedUnload);
    expect(clearedUnload.defaultPrevented).toBe(false);
    view.unmount();
    await act(async () => { await Promise.resolve(); });
    expect(second).toHaveBeenLastCalledWith({ hasUnsavedChanges: false, hasActiveWork: false });
  });

  it("keeps a draft while another observed session is active", async () => {
    const risk = vi.fn();
    render(<AgentPage onExitRiskChange={risk} transport={transport(session("first"), session("second", true))} />);
    const composer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(composer, { target: { value: "offscreen retained draft" } });
    await waitFor(() => expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: true }));
  });

  it("keeps the first chat draft unsaved when the real UI selects a blank second chat", async () => {
    const first = session("first");
    const second = session("second");
    const risk = vi.fn();
    render(<AgentPage onExitRiskChange={risk} transport={transport(first, second)} />);

    const composer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(composer, { target: { value: "draft retained in first chat" } });
    await waitFor(() => expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false }));

    fireEvent.click(await screen.findByRole("button", { name: /second · 0 turns · live/ }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Message to the agent" })).toHaveValue(""));
    expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false });
  });

  it("uses current-only running events for active-work risk, then clears when idle arrives", async () => {
    const current = session("first", false);
    const risk = vi.fn();
    const pageTransport = transport(current);
    let acceptPage: ((page: AgentEvents) => void) | undefined;
    pageTransport.streamAgentEvents = vi.fn(async (_sessionId: string, _after: number, accept: (page: AgentEvents) => void, signal?: AbortSignal) => {
      acceptPage = accept;
      await new Promise<void>((resolve) => signal?.addEventListener("abort", () => resolve(), { once: true }));
    });
    render(<AgentPage onExitRiskChange={risk} transport={pageTransport} />);

    await waitFor(() => expect(acceptPage).toBeDefined());
    act(() => acceptPage!(eventsPage(current.session_id, true, 1)));
    await waitFor(() => expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: false, hasActiveWork: true }));
    act(() => acceptPage!(eventsPage(current.session_id, false, 2)));
    await waitFor(() => expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: false, hasActiveWork: false }));
  });

  it("clears active-work risk when current terminal events override a stale running list snapshot", async () => {
    const current = session("first", true);
    const risk = vi.fn();
    const pageTransport = transport(current);
    let acceptPage: ((page: AgentEvents) => void) | undefined;
    pageTransport.streamAgentEvents = vi.fn(async (_sessionId: string, _after: number, accept: (page: AgentEvents) => void, signal?: AbortSignal) => {
      acceptPage = accept;
      await new Promise<void>((resolve) => signal?.addEventListener("abort", () => resolve(), { once: true }));
    });
    render(<AgentPage onExitRiskChange={risk} transport={pageTransport} />);

    await waitFor(() => expect(acceptPage).toBeDefined());
    act(() => acceptPage!(eventsPage(current.session_id, false, 1)));
    await waitFor(() => expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: false, hasActiveWork: false }));
  });

  it("retains a draft and unsaved risk when an actual send rejects", async () => {
    const current = session("first", false, MODEL_ALIAS);
    const risk = vi.fn();
    const pageTransport = transport(current);
    pageTransport.getLocalModels = vi.fn(async () => modelCatalog(modelStatus("running")));
    pageTransport.sendAgentMessage = vi.fn(async () => { throw new Error("synthetic send failure"); });
    render(<AgentPage onExitRiskChange={risk} transport={pageTransport} />);

    const composer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(composer, { target: { value: "draft survives failed send" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(pageTransport.sendAgentMessage).toHaveBeenCalledWith("first", "draft survives failed send", []));
    expect(screen.getByRole("textbox", { name: "Message to the agent" })).toHaveValue("draft survives failed send");
    expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false });
  });

  it("reports workspace-pane dirtiness through the exit-risk callback", async () => {
    const risk = vi.fn();
    const pageTransport = editableTransport(session("first"));
    render(<AgentPage onExitRiskChange={risk} transport={pageTransport} />);
    fireEvent.click(await screen.findByRole("button", { name: "Files & review" }));
    await act(async () => { await vi.dynamicImportSettled(); });
    expect(pageTransport.getAgentWorkspaceTree).toHaveBeenCalledWith("first", ".", expect.any(AbortSignal));
    fireEvent.click(await screen.findByRole("button", { name: "synthetic-note.txt" }));
    const editor = await screen.findByLabelText("Workspace file editor");
    await waitFor(() => expect(editor).toHaveValue("Synthetic original text.\n"));
    fireEvent.change(editor, { target: { value: "Synthetic unsaved edit.\n" } });
    await waitFor(() => expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false }));
  });
});

const MODEL_ALIAS = "synthetic-exit-risk-model";

function modelStatus(state: LocalModelStatus["runtime"]["state"]): LocalModelStatus {
  return {
    endpoint_path: `/v1/local-models/${MODEL_ALIAS}/chat`,
    record: { added_at: "2040-01-01T00:00:00Z", alias: MODEL_ALIAS, context_size: 8192, default_device: "cpu", display_name: "Synthetic exit-risk model", format: "gguf", path: "D:/synthetic/models/model.gguf", provenance_verified: true },
    runtime: { state },
    placement: { contract_version: "local-model-placement.v1", alias: MODEL_ALIAS, context_size: 8192, gpu_memory_free_mb: null, actual_offload_verified: false, options: [], },
  };
}

function modelCatalog(...models: LocalModelStatus[]): LocalModelsOverview {
  return {
    contract_version: "local-models.v1", runtime_available: true, storage_root: "D:/synthetic/models", storage_free_bytes: 10000, download_reserve_bytes: 1,
    download_ledger_error_code: null, downloads: [], hardware: { gpu_name: null, gpu_memory_mb: null, gpu_memory_free_mb: null, ram_mb: null, llama_server_path: null, llama_server_version: null }, models,
  };
}

function eventsPage(sessionId: string, running: boolean, lastSeq: number): AgentEvents {
  const event: AgentEvent = { seq: lastSeq, at: "2040-01-01T00:00:00Z", kind: "status", attachments: [], text: null, tool: null, arguments: null, call_id: null, approval_id: null, ok: null, preview: null };
  return { contract_version: "local-agent.v9", cleanup_unconfirmed: false, closing: false, stopping: false, session_id: sessionId, events: [event], running, pending_approval_id: null, last_seq: lastSeq, first_seq: lastSeq };
}

function editableTransport(...sessions: AgentSessionView[]): Parameters<typeof AgentPage>[0]["transport"] {
  const pageTransport = transport(...sessions);
  pageTransport.getAgentWorkspaceTree = vi.fn(async (sessionId: string, path: string) => ({ contract_version: "local-agent-workspace.v1" as const, session_id: sessionId, path, entries: [{ path: "synthetic-note.txt", name: "synthetic-note.txt", kind: "file" as const, byte_size: 25, editable_candidate: true }], complete: true }));
  pageTransport.getAgentWorkspaceFile = vi.fn(async (sessionId: string, path: string) => ({ contract_version: "local-agent-workspace.v1" as const, session_id: sessionId, path, content: "Synthetic original text.\n", revision: "f".repeat(64), byte_size: 25, line_ending: "lf" as const, editable: true as const }));
  return pageTransport;
}

function session(id = "first", running = false, modelAlias: string | null = null) {
  return {
    contract_version: "local-agent.v9", cleanup_unconfirmed: false, closing: false, stopping: false,
    session_id: id, running, pending_approval_id: null, last_seq: 0, turns: 0, history_revision: 0,
    model_alias: modelAlias, created_at: "2040-01-01T00:00:00Z", recovered: false, authority_revalidated: true,
    history_write_failed: false, recovery_state: "current",
    settings: { workspace: "D:/synthetic", project_id: null, model_alias: modelAlias, parameters: { temperature: 0.2, top_p: 0.9, max_tokens: 100, enable_thinking: false }, instructions: null, allow_writes: false, allow_commands: false, allow_web: false, max_steps: 1, command_timeout_seconds: 1, title: id, retention_policy: "metadata_only" },
  } as AgentSessionView;
}

function transport(...sessions: AgentSessionView[]): Parameters<typeof AgentPage>[0]["transport"] {
  const base = createSyntheticTransport();
  const result = {
    ...base,
    listAgentSessions: vi.fn(async () => sessions),
    getAgentEvents: vi.fn(async (sessionId: string) => ({ contract_version: "local-agent.v9", cleanup_unconfirmed: false, closing: false, stopping: false, session_id: sessionId, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
  } as Parameters<typeof AgentPage>[0]["transport"];
  Reflect.deleteProperty(result, "listAgentProjects");
  Reflect.deleteProperty(result, "createAgentProject");
  Reflect.deleteProperty(result, "updateAgentProject");
  Reflect.deleteProperty(result, "deleteAgentProject");
  Reflect.deleteProperty(result, "listAgentCatalogSessions");
  Reflect.deleteProperty(result, "updateAgentCatalogSession");
  Reflect.deleteProperty(result, "deleteAgentCatalogSession");
  return result;
}
