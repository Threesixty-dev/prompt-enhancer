import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AgentEvent, AgentSessionView } from "../../shared/api/contracts";
import { AgentPage } from "./AgentPage";

const SESSION = "a".repeat(32);
const APPROVAL = "b".repeat(32);

function view(overrides: Partial<AgentSessionView> = {}): AgentSessionView {
  return {
    contract_version: "local-agent.v1" as const,
    session_id: SESSION,
    settings: { workspace: "D:\\example\\project", model_alias: null, allow_writes: true, allow_commands: true, allow_web: false, max_steps: 10, command_timeout_seconds: 120, title: null },
    created_at: "2026-08-20T01:00:00Z",
    running: false,
    last_seq: 0,
    pending_approval_id: null,
    model_alias: "orca27b-iq3m",
    turns: 0,
    ...overrides,
  };
}

function event(seq: number, kind: AgentEvent["kind"], extra: Partial<AgentEvent> = {}): AgentEvent {
  return { seq, at: "2026-08-20T01:00:00Z", kind, text: null, tool: null, arguments: null, call_id: null, approval_id: null, ok: null, preview: null, ...extra };
}

describe("AgentPage", () => {
  it("creates a session, sends a message, shows tool activity and approves a write with its diff", async () => {
    let events: AgentEvent[] = [event(1, "status", { text: "Session ready in project/ - reads are free." })];
    let current = view();
    const transport = {
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
      getAgentEvents: vi.fn(async (_id: string, after: number) => ({ contract_version: "local-agent.v1" as const, session_id: SESSION, events: events.filter((e) => e.seq > after), running: current.running, pending_approval_id: current.pending_approval_id, last_seq: events.length ? events[events.length - 1].seq : 0, first_seq: events.length ? events[0].seq : 0 })),
      decideAgentApproval: vi.fn(async () => {
        events = [...events, event(6, "approval_resolved", { tool: "write_file", approval_id: APPROVAL, ok: true }), event(7, "tool_result", { tool: "write_file", ok: true, text: "wrote src/app.py" }), event(8, "assistant", { text: "Done - comment added." }), event(9, "done")];
        current = view({ running: false, pending_approval_id: null, last_seq: 9, turns: 1 });
        return current;
      }),
      stopAgentSession: vi.fn(async () => current),
      getLocalModels: vi.fn(async () => ({ contract_version: "local-models.v1" as const, runtime_available: true, storage_root: "D:/x", downloads: [], hardware: { gpu_name: null, gpu_memory_mb: null, gpu_memory_free_mb: null, ram_mb: null, llama_server_path: null, llama_server_version: null }, models: [] })),
    };
    render(<AgentPage transport={transport} />);
    await screen.findByText(/Session ready/);
    fireEvent.change(screen.getByLabelText("Message to the agent"), { target: { value: "Add a noqa comment" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(transport.sendAgentMessage).toHaveBeenCalledWith(SESSION, "Add a noqa comment"));
    await screen.findByText("Read file");
    await screen.findByRole("alertdialog", { name: "Approval needed" });
    expect(screen.getByText(/return a \+ b\s+# noqa/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(transport.decideAgentApproval).toHaveBeenCalledWith(SESSION, APPROVAL, true));
    await screen.findByText("Done - comment added.");
    expect(screen.getByText(/Approved: Write file/)).toBeTruthy();
  });

  it("explains when the agent is unavailable and lets a new session be created", async () => {
    const transport = {
      listAgentSessions: vi.fn(async () => []),
      createAgentSession: vi.fn(async (settings: { workspace: string; allow_web?: boolean }) => view({ settings: { ...view().settings, workspace: settings.workspace } })),
      getAgentSession: vi.fn(), deleteAgentSession: vi.fn(), sendAgentMessage: vi.fn(),
      getAgentEvents: vi.fn(async () => ({ contract_version: "local-agent.v1" as const, session_id: SESSION, events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })),
      decideAgentApproval: vi.fn(), stopAgentSession: vi.fn(),
    };
    render(<AgentPage transport={transport} />);
    await screen.findByText(/No session yet/);
    fireEvent.change(screen.getByLabelText("Workspace folder"), { target: { value: "D:\\example\\project" } });
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));
    await waitFor(() => expect(transport.createAgentSession).toHaveBeenCalled());
    const settings = transport.createAgentSession.mock.calls[0][0];
    expect(settings.workspace).toBe("D:\\example\\project");
    expect(settings.allow_web).toBe(false);
  });
});
