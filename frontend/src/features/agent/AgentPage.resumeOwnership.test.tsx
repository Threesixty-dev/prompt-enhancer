import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import type { AgentArtifactListView, AgentCatalogSession, AgentEvent, AgentEvents, AgentProject, AgentSessionView, ResumeAgentSession } from "../../shared/api/contracts";
import { AgentPage } from "./AgentPage";

type AgentTransport = Parameters<typeof AgentPage>[0]["transport"];

const PROJECT_ID = "a".repeat(32);
const SESSION_A = "b".repeat(32);
const SESSION_B = "c".repeat(32);
const SAFE_RESUME_MESSAGE = "The retained chat could not be resumed. Its saved history remains unchanged.";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((accept, decline) => {
    resolve = accept;
    reject = decline;
  });
  return { promise, reject, resolve };
}

function project(): AgentProject {
  return {
    contract_version: "agent-catalog.v2",
    project_id: PROJECT_ID,
    name: "Synthetic resume ownership project",
    created_at: "2040-01-01T00:00:00Z",
    updated_at: "2040-01-01T00:01:00Z",
    revision: 1,
    pinned: false,
    archived_at: null,
    session_count: 2,
    is_default: false,
  };
}

function savedSession(
  sessionId: string,
  title: string,
  overrides: Partial<AgentCatalogSession> = {},
): AgentCatalogSession {
  return {
    contract_version: "agent-catalog.v2",
    session_id: sessionId,
    project_id: PROJECT_ID,
    title,
    workspace: "D:\\example\\resume-ownership",
    model_alias: null,
    created_at: "2040-01-01T00:00:00Z",
    updated_at: "2040-01-01T00:01:00Z",
    last_opened_at: "2040-01-01T00:00:00Z",
    revision: 1,
    pinned: false,
    archived_at: null,
    history_state: "durable_local",
    retention_policy: "local_history",
    history_revision: 0,
    last_event_seq: 0,
    turn_count: 0,
    conversation_available: true,
    lineage: null,
    ...overrides,
  };
}

function resumedView(session: AgentCatalogSession): AgentSessionView {
  return {
    contract_version: "local-agent.v9",
    cleanup_unconfirmed: false,
    closing: false,
    stopping: false,
    session_id: session.session_id,
    settings: {
      workspace: session.workspace,
      project_id: session.project_id,
      model_alias: null,
      parameters: {
        temperature: 0.2,
        top_p: 0.95,
        max_tokens: 100,
        enable_thinking: false,
      },
      instructions: null,
      allow_writes: false,
      allow_commands: false,
      allow_web: false,
      max_steps: 1,
      command_timeout_seconds: 1,
      title: session.title,
      retention_policy: "local_history",
    },
    created_at: session.created_at,
    running: false,
    last_seq: 0,
    pending_approval_id: null,
    model_alias: null,
    turns: 0,
    history_revision: 0,
    recovered: true,
    authority_revalidated: false,
    history_write_failed: false,
    recovery_state: "recovered",
  };
}

function retainedEvent(seq: number, text = "Synthetic retained status"): AgentEvent {
  return {
    seq,
    at: "2040-01-01T00:00:00Z",
    kind: "status",
    attachments: [],
    text,
    tool: null,
    arguments: null,
    call_id: null,
    approval_id: null,
    ok: null,
    preview: null,
  };
}

function conversationEvent(seq: number, kind: "user" | "assistant", text: string): AgentEvent {
  return {
    ...retainedEvent(seq, text),
    kind,
    stream_status: kind === "assistant" ? "complete" : null,
  };
}

function retainedPage(sessionId: string, lastSeq = 0): AgentEvents {
  return {
    contract_version: "local-agent.v9",
    session_id: sessionId,
    events: Array.from({ length: lastSeq }, (_, index) => retainedEvent(index + 1)),
    running: false,
    closing: false,
    stopping: false,
    cleanup_unconfirmed: false,
    pending_approval_id: null,
    first_seq: 0,
    last_seq: lastSeq,
  };
}

function durableTransport(
  sessions: AgentCatalogSession[],
  resumeAgentSession: (
    projectId: string,
    sessionId: string,
    request: ResumeAgentSession,
    signal?: AbortSignal,
  ) => Promise<AgentSessionView>,
): AgentTransport {
  const base = createSyntheticTransport();
  return {
    ...base,
    listAgentSessions: vi.fn(async () => []),
    listAgentProjects: vi.fn(async () => ({
      contract_version: "agent-catalog.v2" as const,
      projects: [{ ...project(), session_count: sessions.length }],
    })),
    listAgentCatalogSessions: vi.fn(async () => ({
      contract_version: "agent-catalog.v2" as const,
      sessions,
    })),
    getAgentCatalogSession: vi.fn(async (sessionId: string) => (
      sessions.find((session) => session.session_id === sessionId) ?? sessions[0]
    )),
    getAgentPersistedEvents: vi.fn(async (_projectId: string, sessionId: string) => (
      retainedPage(sessionId, sessions.find((session) => session.session_id === sessionId)?.last_event_seq ?? 0)
    )),
    listAgentArtifacts: vi.fn(async (projectId: string, sessionId: string, view: AgentArtifactListView = "active") => ({
      contract_version: "agent-artifact.v3" as const,
      project_id: projectId,
      session_id: sessionId,
      view,
      counts: { active: 0, archived: 0, removed: 0, total: 0 },
      artifacts: [],
    })),
    resumeAgentSession: vi.fn(resumeAgentSession),
  };
}

async function selectSavedSession(title: string): Promise<void> {
  fireEvent.click(await screen.findByRole("button", { name: new RegExp(`${title} ·`, "u") }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Resume chat" })).toBeEnabled());
}

describe("AgentPage resume ownership", () => {
  it("passes missing resume and export capabilities through as disabled retained-history actions", async () => {
    const saved = savedSession(SESSION_A, "Saved unsupported actions");
    const resume = vi.fn(async () => resumedView(saved));
    const base = durableTransport([saved], resume);
    const transport = {
      ...base,
      resumeAgentSession: undefined,
      exportAgentHistory: undefined,
    } as AgentTransport;

    render(<AgentPage transport={transport} />);
    await screen.findByRole("button", { name: /Synthetic resume ownership project.*1 chat/u });
    fireEvent.click(await screen.findByRole("button", { name: /Saved unsupported actions ·/u }));
    const unavailableResume = await screen.findByRole("button", { name: "Resume unavailable" });
    const unavailableExport = screen.getByRole("button", { name: "Export unavailable" });
    expect(unavailableResume).toBeDisabled();
    expect(unavailableExport).toBeDisabled();
    expect(unavailableResume).toHaveAccessibleDescription(/transport does not provide retained-session resume/i);
    expect(unavailableExport).toHaveAccessibleDescription(/transport does not provide retained-history export/i);
    fireEvent.click(unavailableResume);
    fireEvent.click(unavailableExport);
    expect(resume).not.toHaveBeenCalled();
  });

  it("does not let a delayed resume of saved A replace a later selection of saved B", async () => {
    const savedA = savedSession(SESSION_A, "Saved A");
    const savedB = savedSession(SESSION_B, "Saved B");
    const resumedA = resumedView(savedA);
    const resumeA = deferred<AgentSessionView>();
    let resumeASignal: AbortSignal | undefined;
    const transport = durableTransport([savedA, savedB], async (
      _projectId,
      sessionId,
      _request,
      signal,
    ) => {
      if (sessionId === SESSION_A) resumeASignal = signal;
      return sessionId === SESSION_A ? resumeA.promise : Promise.resolve(resumedView(savedB));
    });

    render(<AgentPage transport={transport} />);

    await selectSavedSession("Saved A");
    fireEvent.click(screen.getByRole("button", { name: "Resume chat" }));
    await waitFor(() => expect(transport.resumeAgentSession).toHaveBeenCalledOnce());

    await selectSavedSession("Saved B");
    expect(resumeASignal).toBeDefined();
    expect(resumeASignal?.aborted).toBe(true);
    expect(await screen.findByRole("heading", { name: "Saved B", level: 2 })).toBeVisible();

    await act(async () => {
      resumeA.resolve(resumedA);
      await Promise.resolve();
    });

    expect(screen.getByRole("heading", { name: "Saved B", level: 2 })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Saved A", level: 2 })).toBeNull();
    expect(screen.queryByLabelText("Message to the agent")).toBeNull();
  });

  it("opens a resumed model-free chat with an editable composer without activation or send", async () => {
    const savedA = savedSession(SESSION_A, "Model-free saved A");
    const resumedA = resumedView(savedA);
    const transport = durableTransport([savedA], async () => resumedA);
    const activateLocalModel = vi.fn();
    const sendAgentMessage = vi.fn();
    transport.activateLocalModel = activateLocalModel;
    transport.sendAgentMessage = sendAgentMessage;

    render(<AgentPage transport={transport} />);
    await selectSavedSession("Model-free saved A");
    fireEvent.click(screen.getByRole("button", { name: "Resume chat" }));

    const composer = await screen.findByLabelText("Message to the agent");
    expect(composer).toBeEnabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(activateLocalModel).not.toHaveBeenCalled();
    expect(sendAgentMessage).not.toHaveBeenCalled();
  });

  it("reloads retained history when the exact saved row is selected again", async () => {
    const savedA = savedSession(SESSION_A, "Same-row saved A");
    const pendingResume = vi.fn(async () => resumedView(savedA));
    const sendAgentMessage = vi.fn();
    const transport = durableTransport([savedA], pendingResume);
    let persistedReads = 0;
    transport.getAgentPersistedEvents = vi.fn(async (
      _projectId: string,
      sessionId: string,
      _after: number,
      _signal?: AbortSignal,
    ) => {
      persistedReads += 1;
      return retainedPage(sessionId);
    });
    transport.sendAgentMessage = sendAgentMessage;

    render(<AgentPage transport={transport} />);
    await selectSavedSession("Same-row saved A");
    const firstReadCount = persistedReads;
    fireEvent.click(screen.getByRole("button", { name: /Same-row saved A ·/u }));

    await waitFor(() => expect(persistedReads).toBeGreaterThan(firstReadCount));
    expect(screen.getByRole("button", { name: "Resume chat" })).toBeEnabled();
    expect(pendingResume).not.toHaveBeenCalled();
    expect(sendAgentMessage).not.toHaveBeenCalled();
  });

  it.each(["polling", "stream"] as const)(
    "accepts a coherent resumed response whose retained history and event head advance over %s",
    async (mode) => {
      const savedA = savedSession(SESSION_A, "Advanced saved A", {
        history_revision: 2,
        last_event_seq: 2,
      });
      const resumedA = {
        ...resumedView(savedA),
        history_revision: 3,
        last_seq: 3,
      };
      const transport = durableTransport([savedA], async () => Promise.resolve(resumedA));
      const retained = {
        ...retainedPage(SESSION_A, 2),
        events: [
          conversationEvent(1, "user", "Synthetic retained request"),
          conversationEvent(2, "assistant", "Synthetic retained response"),
        ],
      };
      let initialCursor: number | undefined;
      transport.getAgentPersistedEvents = vi.fn(async () => retained);
      const livePage = {
        ...retainedPage(SESSION_A, 3),
        first_seq: 1,
        events: [conversationEvent(3, "assistant", "Synthetic streamed event after resume")],
      };
      transport.getAgentEvents = vi.fn(async (_sessionId: string, after: number) => {
        initialCursor = after;
        return { ...livePage, events: after < 3 ? livePage.events : [] };
      });
      if (mode === "polling") {
        Reflect.deleteProperty(transport, "streamAgentEvents");
      } else {
        transport.streamAgentEvents = vi.fn(async (
          _sessionId: string,
          after: number,
          accept: (page: AgentEvents) => void,
          signal?: AbortSignal,
        ) => {
          initialCursor = after;
          accept({ ...livePage, events: after < 3 ? livePage.events : [] });
          await new Promise<void>((resolve) => {
            if (signal?.aborted) resolve();
            else signal?.addEventListener("abort", () => resolve(), { once: true });
          });
        });
      }

      render(<AgentPage transport={transport} />);
      await selectSavedSession("Advanced saved A");
      fireEvent.click(screen.getByRole("button", { name: "Resume chat" }));

      expect(await screen.findByLabelText("Message to the agent")).toBeEnabled();
      expect(await screen.findByText("Synthetic streamed event after resume")).toBeVisible();
      expect(initialCursor).toBe(2);
      expect(screen.queryByText(SAFE_RESUME_MESSAGE)).toBeNull();
    },
  );

  it.each(["success", "error"] as const)(
    "keeps a newer same-row resume busy when the superseded resume later settles with %s",
    async (settlement) => {
      const savedA = savedSession(SESSION_A, "Pending same-row saved A");
      const oldAttempt = deferred<AgentSessionView>();
      const newAttempt = deferred<AgentSessionView>();
      let resumeCalls = 0;
      let oldSignal: AbortSignal | undefined;
      let newSignal: AbortSignal | undefined;
      let persistedReads = 0;
      const transport = durableTransport([savedA], async (_projectId, _sessionId, _request, signal) => {
        resumeCalls += 1;
        if (resumeCalls === 1) {
          oldSignal = signal;
          return oldAttempt.promise;
        }
        newSignal = signal;
        return newAttempt.promise;
      });
      transport.getAgentPersistedEvents = vi.fn(async (
        _projectId: string,
        sessionId: string,
        _after: number,
        _signal?: AbortSignal,
      ) => {
        persistedReads += 1;
        return retainedPage(sessionId);
      });

      render(<AgentPage transport={transport} />);
      await selectSavedSession("Pending same-row saved A");
      fireEvent.click(screen.getByRole("button", { name: "Resume chat" }));
      await waitFor(() => expect(resumeCalls).toBe(1));
      const firstReadCount = persistedReads;

      fireEvent.click(screen.getByRole("button", { name: /Pending same-row saved A ·/u }));
      await waitFor(() => expect(persistedReads).toBeGreaterThan(firstReadCount));
      expect(oldSignal?.aborted).toBe(true);
      expect(screen.getByRole("button", { name: "Resume chat" })).toBeEnabled();

      fireEvent.click(screen.getByRole("button", { name: "Resume chat" }));
      await waitFor(() => expect(resumeCalls).toBe(2));
      expect(newSignal?.aborted).toBe(false);
      expect(screen.getByRole("button", { name: "Resuming…" })).toBeDisabled();

      await act(async () => {
        if (settlement === "success") oldAttempt.resolve(resumedView(savedA));
        else oldAttempt.reject(new Error("Synthetic superseded resume failure"));
        await Promise.resolve();
      });
      expect(screen.getByRole("button", { name: "Resuming…" })).toBeDisabled();
      expect(screen.queryByLabelText("Message to the agent")).toBeNull();

      await act(async () => {
        newAttempt.resolve(resumedView(savedA));
        await Promise.resolve();
      });
      expect(await screen.findByLabelText("Message to the agent")).toBeEnabled();
      expect(resumeCalls).toBe(2);
    },
  );

  it("keeps a failed resume safe, clears busy, and allows an exact retry", async () => {
    const savedA = savedSession(SESSION_A, "Failed saved A");
    const firstAttempt = deferred<AgentSessionView>();
    const retryAttempt = deferred<AgentSessionView>();
    let attempt = 0;
    const transport = durableTransport([savedA], async () => {
      attempt += 1;
      return (attempt === 1 ? firstAttempt : retryAttempt).promise;
    });

    render(<AgentPage transport={transport} />);
    await selectSavedSession("Failed saved A");
    fireEvent.click(screen.getByRole("button", { name: "Resume chat" }));
    await waitFor(() => expect(attempt).toBe(1));

    await act(async () => {
      firstAttempt.reject(new Error("Synthetic delayed resume failure"));
      await Promise.resolve();
    });
    const safeResumeMessage = await screen.findByText(SAFE_RESUME_MESSAGE);
    expect(safeResumeMessage.closest('[role="status"]')).not.toBeNull();
    expect(screen.getByRole("button", { name: "Resume chat" })).toBeEnabled();
    expect(screen.queryByLabelText("Message to the agent")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Resume chat" }));
    await waitFor(() => expect(attempt).toBe(2));
    expect(screen.getByRole("button", { name: "Resuming…" })).toBeDisabled();
    await act(async () => {
      retryAttempt.resolve(resumedView(savedA));
      await Promise.resolve();
    });
    expect(await screen.findByLabelText("Message to the agent")).toBeEnabled();
  });

  it("does not leak a late resume error from saved A into selected saved B", async () => {
    const savedA = savedSession(SESSION_A, "Late-error saved A");
    const savedB = savedSession(SESSION_B, "Late-error saved B");
    const lateA = deferred<AgentSessionView>();
    const transport = durableTransport([savedA, savedB], async (_projectId, sessionId) => (
      sessionId === SESSION_A ? lateA.promise : Promise.resolve(resumedView(savedB))
    ));

    render(<AgentPage transport={transport} />);
    await selectSavedSession("Late-error saved A");
    fireEvent.click(screen.getByRole("button", { name: "Resume chat" }));
    await waitFor(() => expect(transport.resumeAgentSession).toHaveBeenCalledOnce());
    await selectSavedSession("Late-error saved B");
    await act(async () => {
      lateA.reject(new Error("Synthetic late A error"));
      await Promise.resolve();
    });

    expect(screen.getByRole("heading", { name: "Late-error saved B", level: 2 })).toBeVisible();
    expect(screen.getByRole("button", { name: "Resume chat" })).toBeEnabled();
    expect(screen.queryByText("The retained chat could not be resumed. Its saved history remains unchanged.")).toBeNull();
  });

  it.each(["success", "error"] as const)(
    "does not let a same-id replacement transport inherit a late old resume %s",
    async (settlement) => {
      const oldSaved = savedSession(SESSION_A, "Old same-id saved chat");
      const replacementSaved = savedSession(SESSION_A, "Replacement same-id saved chat");
      const oldAttempt = deferred<AgentSessionView>();
      const oldTransport = durableTransport([oldSaved], async () => oldAttempt.promise);
      const replacementTransport = durableTransport([replacementSaved], async () => Promise.resolve(resumedView(replacementSaved)));
      const rendered = render(<AgentPage transport={oldTransport} />);

      await selectSavedSession("Old same-id saved chat");
      fireEvent.click(screen.getByRole("button", { name: "Resume chat" }));
      await waitFor(() => expect(oldTransport.resumeAgentSession).toHaveBeenCalledOnce());

      rendered.rerender(<AgentPage transport={replacementTransport} />);
      await selectSavedSession("Replacement same-id saved chat");
      await act(async () => {
        if (settlement === "success") oldAttempt.resolve(resumedView(oldSaved));
        else oldAttempt.reject(new Error("Synthetic old transport resume failure"));
        await Promise.resolve();
      });

      expect(screen.getByRole("heading", { name: "Replacement same-id saved chat", level: 2 })).toBeVisible();
      expect(screen.queryByLabelText("Message to the agent")).toBeNull();
      expect(screen.getByRole("button", { name: "Resume chat" })).toBeEnabled();
      expect(screen.queryByText("The retained chat could not be resumed. Its saved history remains unchanged.")).toBeNull();
    },
  );

  it("aborts an owned resume on unmount and ignores its late callback", async () => {
    const savedA = savedSession(SESSION_A, "Unmount saved A");
    const lateA = deferred<AgentSessionView>();
    let resumeSignal: AbortSignal | undefined;
    const transport = durableTransport([savedA], async (_projectId, _sessionId, _request, signal) => {
      resumeSignal = signal;
      return lateA.promise;
    });
    const rendered = render(<AgentPage transport={transport} />);

    await selectSavedSession("Unmount saved A");
    fireEvent.click(screen.getByRole("button", { name: "Resume chat" }));
    await waitFor(() => expect(resumeSignal).toBeDefined());
    expect(resumeSignal?.aborted).toBe(false);
    rendered.unmount();
    expect(resumeSignal?.aborted).toBe(true);

    await act(async () => {
      lateA.resolve(resumedView(savedA));
      await Promise.resolve();
    });
  });

  it("guards immediate duplicate resume activation", async () => {
    const savedA = savedSession(SESSION_A, "Duplicate saved A");
    const pending = deferred<AgentSessionView>();
    let calls = 0;
    const transport = durableTransport([savedA], async () => {
      calls += 1;
      return pending.promise;
    });

    render(<AgentPage transport={transport} />);
    await selectSavedSession("Duplicate saved A");
    const resume = screen.getByRole("button", { name: "Resume chat" });
    await act(async () => {
      fireEvent.click(resume);
      fireEvent.click(resume);
    });
    expect(calls).toBe(1);
    expect(screen.getByRole("button", { name: "Resuming…" })).toBeDisabled();
    await act(async () => {
      pending.resolve(resumedView(savedA));
      await Promise.resolve();
    });
  });

  it.each([
    ["session id", (value: AgentSessionView) => ({ ...value, session_id: SESSION_B })],
    ["project id", (value: AgentSessionView) => ({ ...value, settings: { ...value.settings, project_id: "d".repeat(32) } })],
    ["retention policy", (value: AgentSessionView) => ({ ...value, settings: { ...value.settings, retention_policy: "metadata_only" as const } })],
    ["backward history revision", (value: AgentSessionView) => ({ ...value, history_revision: 1 })],
    ["backward event head", (value: AgentSessionView) => ({ ...value, last_seq: 1 })],
  ] as const)("refuses a resumed response with a mismatched or backward %s", async (_label, mutate) => {
    const savedA = savedSession(SESSION_A, "Invalid response saved A", {
      history_revision: _label === "backward history revision" ? 2 : 0,
      last_event_seq: _label === "backward event head" ? 2 : 0,
    });
    const transport = durableTransport([savedA], async () => mutate(resumedView(savedA)));

    render(<AgentPage transport={transport} />);
    await selectSavedSession("Invalid response saved A");
    fireEvent.click(screen.getByRole("button", { name: "Resume chat" }));

    const safeResumeMessage = await screen.findByText(SAFE_RESUME_MESSAGE);
    expect(safeResumeMessage.closest('[role="status"]')).not.toBeNull();
    expect(screen.getByRole("button", { name: "Resume chat" })).toBeEnabled();
    expect(screen.queryByLabelText("Message to the agent")).toBeNull();
  });

  it("refuses a response behind the retained head actually read by the page", async () => {
    const savedA = savedSession(SESSION_A, "Read-head saved A");
    const retained = retainedPage(SESSION_A, 2);
    const transport = durableTransport([savedA], async () => ({
      ...resumedView(savedA),
      last_seq: 1,
    }));
    transport.getAgentPersistedEvents = vi.fn(async () => retained);

    render(<AgentPage transport={transport} />);
    await selectSavedSession("Read-head saved A");
    fireEvent.click(screen.getByRole("button", { name: "Resume chat" }));

    const safeResumeMessage = await screen.findByText(SAFE_RESUME_MESSAGE);
    expect(safeResumeMessage.closest('[role="status"]')).not.toBeNull();
    expect(screen.getByRole("button", { name: "Resume chat" })).toBeEnabled();
    expect(screen.queryByLabelText("Message to the agent")).toBeNull();
  });
});
