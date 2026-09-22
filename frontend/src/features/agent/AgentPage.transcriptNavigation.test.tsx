import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AgentEvent, AgentEvents, AgentSessionView } from "../../shared/api/contracts";
import { AgentPage } from "./AgentPage";
import "../../styles.css";

const SESSION = "a".repeat(32);

function session(): AgentSessionView {
  return {
    contract_version: "local-agent.v9",
    cleanup_unconfirmed: false,
    closing: false,
    stopping: false,
    session_id: SESSION,
    settings: {
      workspace: "D:\\example\\project",
      project_id: null,
      model_alias: "synthetic-model",
      parameters: { temperature: 0.2, top_p: 0.95, max_tokens: 1400, enable_thinking: false },
      instructions: null,
      allow_writes: true,
      allow_commands: true,
      allow_web: false,
      max_steps: 10,
      command_timeout_seconds: 120,
      title: "Synthetic transcript",
      retention_policy: "metadata_only",
    },
    created_at: "2040-01-01T00:00:00Z",
    running: false,
    last_seq: 201,
    pending_approval_id: null,
    model_alias: "synthetic-model",
    turns: 0,
    history_revision: 0,
    recovered: false,
    authority_revalidated: true,
    history_write_failed: false,
    recovery_state: "current",
  };
}

function activity(seq: number): AgentEvent {
  return {
    seq,
    at: "2040-01-01T00:00:00Z",
    kind: "status",
    attachments: [],
    text: `Synthetic activity ${seq}`,
    tool: null,
    arguments: null,
    call_id: null,
    approval_id: null,
    ok: null,
    preview: null,
  };
}

function transcriptTransport(events: AgentEvent[]) {
  const current = { ...session(), last_seq: events.length };
  return {
    listAgentSessions: vi.fn(async () => [current]),
    getAgentEvents: vi.fn(async (): Promise<AgentEvents> => ({
      contract_version: "local-agent.v9",
      cleanup_unconfirmed: false,
      closing: false,
      stopping: false,
      session_id: SESSION,
      events,
      running: false,
      pending_approval_id: null,
      first_seq: 1,
      last_seq: events.length,
    })),
    createAgentSession: vi.fn(),
    getAgentSession: vi.fn(),
    deleteAgentSession: vi.fn(),
    sendAgentMessage: vi.fn(),
    decideAgentApproval: vi.fn(),
    stopAgentSession: vi.fn(),
    activateLocalModel: vi.fn(),
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

describe("AgentPage transcript navigation", () => {
  it("mounts the newest activity page when Jump to latest follows Earlier without disturbing the composer", async () => {
    const events = Array.from({ length: 201 }, (_, index) => activity(index + 1));
    const transport = transcriptTransport(events);

    render(<AgentPage transport={transport} />);
    await screen.findByText("Synthetic activity 201");
    fireEvent.change(screen.getByLabelText("Message to the agent"), { target: { value: "Keep this fictional composer draft" } });
    fireEvent.click(screen.getByRole("button", { name: /^Earlier 1$/u }));
    expect(await screen.findByText("Synthetic activity 1")).toBeVisible();
    expect(screen.queryByText("Synthetic activity 201")).not.toBeInTheDocument();

    const log = screen.getByRole("log");
    Object.defineProperties(log, {
      clientHeight: { configurable: true, value: 100 },
      scrollHeight: { configurable: true, value: 1_000 },
      scrollTop: { configurable: true, writable: true, value: 0 },
    });
    fireEvent.scroll(log);
    fireEvent.click(await screen.findByRole("button", { name: "Jump to latest activity" }));

    expect(await screen.findByText("Synthetic activity 201")).toBeVisible();
    expect(screen.queryByText("Synthetic activity 1")).not.toBeInTheDocument();
    await waitFor(() => expect(log).toHaveFocus());
    expect(log.scrollTop).toBe(log.scrollHeight);
    expect(screen.getByLabelText("Message to the agent")).toHaveValue("Keep this fictional composer draft");
    expect(transport.sendAgentMessage).not.toHaveBeenCalled();
    expect(transport.activateLocalModel).not.toHaveBeenCalled();
    expect(transport.applyAgentWorkspaceEdit).not.toHaveBeenCalled();
  });

  it("keeps Jump to latest activity available on the current page when the log is scrolled away", async () => {
    const events = Array.from({ length: 201 }, (_, index) => activity(index + 1));
    const transport = transcriptTransport(events);
    render(<AgentPage transport={transport} />);
    await screen.findByText("Synthetic activity 201");

    const log = screen.getByRole("log");
    Object.defineProperties(log, {
      clientHeight: { configurable: true, value: 100 },
      scrollHeight: { configurable: true, value: 1_000 },
      scrollTop: { configurable: true, writable: true, value: 0 },
    });
    fireEvent.scroll(log);
    fireEvent.click(await screen.findByRole("button", { name: "Jump to latest activity" }));

    expect(screen.getByText("Synthetic activity 201")).toBeVisible();
    await waitFor(() => expect(log).toHaveFocus());
    expect(log.scrollTop).toBe(log.scrollHeight);
  });

  it("retains an older page through a new event until an explicit Jump to latest activity", async () => {
    const events = Array.from({ length: 201 }, (_, index) => activity(index + 1));
    let publish: ((page: AgentEvents) => void) | undefined;
    const transport = {
      ...transcriptTransport(events),
      streamAgentEvents: vi.fn(async (
        _sessionId: string,
        _after: number,
        onPage: (page: AgentEvents) => void,
        signal?: AbortSignal,
      ) => {
        publish = onPage;
        onPage({
          contract_version: "local-agent.v9",
          cleanup_unconfirmed: false,
          closing: false,
          stopping: false,
          session_id: SESSION,
          events,
          running: false,
          pending_approval_id: null,
          first_seq: 1,
          last_seq: events.length,
        });
        await new Promise<void>((resolve) => signal?.addEventListener("abort", () => resolve(), { once: true }));
      }),
    };
    render(<AgentPage transport={transport} />);
    await screen.findByText("Synthetic activity 201");
    fireEvent.change(screen.getByLabelText("Message to the agent"), { target: { value: "Preserve fictional draft on older page" } });
    fireEvent.click(screen.getByRole("button", { name: /^Earlier 1$/u }));
    expect(await screen.findByText("Synthetic activity 1")).toBeVisible();
    await waitFor(() => expect(publish).toBeDefined());
    await act(async () => publish?.({
      contract_version: "local-agent.v9",
      cleanup_unconfirmed: false,
      closing: false,
      stopping: false,
      session_id: SESSION,
      events: [activity(202)],
      running: false,
      pending_approval_id: null,
      first_seq: 1,
      last_seq: 202,
    }));

    expect(screen.getByText("Synthetic activity 1")).toBeVisible();
    expect(screen.queryByText("Synthetic activity 202")).not.toBeInTheDocument();
    const log = screen.getByRole("log");
    Object.defineProperties(log, {
      clientHeight: { configurable: true, value: 100 },
      scrollHeight: { configurable: true, value: 1_000 },
      scrollTop: { configurable: true, writable: true, value: 0 },
    });
    fireEvent.scroll(log);
    fireEvent.click(await screen.findByRole("button", { name: "Jump to latest activity" }));

    expect(await screen.findByText("Synthetic activity 202")).toBeVisible();
    expect(screen.queryByText("Synthetic activity 1")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("log")).toHaveFocus());
    expect(screen.getByLabelText("Message to the agent")).toHaveValue("Preserve fictional draft on older page");
    expect(transport.sendAgentMessage).not.toHaveBeenCalled();
    expect(transport.applyAgentWorkspaceEdit).not.toHaveBeenCalled();
  });
});
