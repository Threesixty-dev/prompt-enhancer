import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import type { AgentAttachment, AgentSessionView } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { AgentPage } from "./AgentPage";

describe("Agent close-chat drafts", () => {
  it("discards the closed live chat draft while preserving the selected blank chat", async () => {
    const first = liveSession("synthetic-close-first", "First synthetic chat");
    const second = liveSession("synthetic-close-second", "Second synthetic chat");
    let sessions = [first, second];
    const risk = vi.fn();
    const transport = syntheticTransport(first, second);
    transport.listAgentSessions = vi.fn(async () => sessions);
    transport.deleteAgentSession = vi.fn(async (id: string) => {
      sessions = sessions.filter((session) => session.session_id !== id);
    });

    render(<AgentPage onExitRiskChange={risk} transport={transport} />);

    const composer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(composer, { target: { value: "Synthetic draft to discard with chat" } });
    await waitFor(() => expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false }));

    fireEvent.click(screen.getByRole("button", { name: /Second synthetic chat · 0 turns · live/u }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Message to the agent" })).toHaveValue(""));

    fireEvent.click(screen.getByRole("button", { name: "Close session First synthetic chat" }));
    const dialog = await screen.findByRole("dialog", { name: "Close live chat?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Close chat" }));

    await waitFor(() => expect(transport.deleteAgentSession).toHaveBeenCalledExactlyOnceWith(first.session_id));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Close session First synthetic chat" })).not.toBeInTheDocument());
    expect(screen.getByRole("textbox", { name: "Message to the agent" })).toHaveValue("");
    await waitFor(() => expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: false, hasActiveWork: false }));

    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(false);
  });

  it("discards a current text draft after authoritative 404 absence", async () => {
    const current = liveSession("synthetic-close-current", "Current synthetic chat");
    const risk = vi.fn();
    const transport = syntheticTransport(current);
    let sessions: AgentSessionView[] = [current];
    transport.listAgentSessions = vi.fn(async () => sessions);
    transport.deleteAgentSession = vi.fn(async () => {
      sessions = [];
      throw new TransportError("Synthetic already absent", 404);
    });
    render(<AgentPage onExitRiskChange={risk} transport={transport} />);

    fireEvent.change(await screen.findByRole("textbox", { name: "Message to the agent" }), { target: { value: "Current synthetic draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Close session Current synthetic chat" }));
    await confirmClose();

    await waitFor(() => expect(transport.deleteAgentSession).toHaveBeenCalledExactlyOnceWith(current.session_id));
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Message to the agent" })).not.toBeInTheDocument());
    expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: false, hasActiveWork: false });
  });

  it("discards a noncurrent attachment-only draft with its successfully closed chat", async () => {
    const first = liveSession("synthetic-close-attachment", "Attachment synthetic chat");
    const second = liveSession("synthetic-close-blank", "Blank synthetic chat");
    let sessions = [first, second];
    const risk = vi.fn();
    const transport = syntheticTransport(first, second);
    transport.listAgentSessions = vi.fn(async () => sessions);
    transport.listAgentAttachments = vi.fn(async (sessionId: string) => ({
      contract_version: "agent-attachment.v2" as const,
      session_id: sessionId,
      attachments: sessionId === first.session_id ? [stagedAttachment(first.session_id)] : [],
    }));
    transport.stageAgentAttachment = vi.fn();
    transport.deleteAgentAttachment = vi.fn();
    transport.deleteAgentSession = vi.fn(async (id: string) => {
      sessions = sessions.filter((session) => session.session_id !== id);
    });
    render(<AgentPage onExitRiskChange={risk} transport={transport} />);

    await waitFor(() => expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false }));
    fireEvent.click(screen.getByRole("button", { name: /Blank synthetic chat · 0 turns · live/u }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Message to the agent" })).toHaveValue(""));
    fireEvent.click(screen.getByRole("button", { name: "Close session Attachment synthetic chat" }));
    await confirmClose();

    await waitFor(() => expect(transport.deleteAgentSession).toHaveBeenCalledExactlyOnceWith(first.session_id));
    await waitFor(() => expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: false, hasActiveWork: false }));
    expect(screen.getByRole("textbox", { name: "Message to the agent" })).toHaveValue("");
  });

  it.each([
    ["generic rejection", new Error("Synthetic close rejection"), false],
    ["command cleanup quarantine", new TransportError("Synthetic cleanup", 409, "command_cleanup_unconfirmed"), true],
  ])("preserves a current draft when close has %s", async (_label, failure, hasActiveWork) => {
    const current = liveSession("synthetic-close-preserve", "Preserve synthetic chat");
    const risk = vi.fn();
    const transport = syntheticTransport(current);
    transport.deleteAgentSession = vi.fn(async () => { throw failure; });
    render(<AgentPage onExitRiskChange={risk} transport={transport} />);

    const composer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(composer, { target: { value: "Synthetic draft must survive failure" } });
    fireEvent.click(screen.getByRole("button", { name: "Close session Preserve synthetic chat" }));
    await confirmClose();

    await waitFor(() => expect(transport.deleteAgentSession).toHaveBeenCalledExactlyOnceWith(current.session_id));
    expect(screen.getByRole("textbox", { name: "Message to the agent" })).toHaveValue("Synthetic draft must survive failure");
    expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork });
  });

  it("keeps a noncurrent failed-close draft and gives the owner a visible failure alert", async () => {
    const first = liveSession("synthetic-close-alert-first", "Alert first synthetic chat");
    const second = liveSession("synthetic-close-alert-second", "Alert second synthetic chat");
    const risk = vi.fn();
    const transport = syntheticTransport(first, second);
    transport.deleteAgentSession = vi.fn(async () => { throw new Error("Synthetic noncurrent close rejection"); });
    render(<AgentPage onExitRiskChange={risk} transport={transport} />);

    fireEvent.change(await screen.findByRole("textbox", { name: "Message to the agent" }), { target: { value: "Synthetic noncurrent failed-close draft" } });
    fireEvent.click(screen.getByRole("button", { name: /Alert second synthetic chat · 0 turns · live/u }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Message to the agent" })).toHaveValue(""));
    fireEvent.click(screen.getByRole("button", { name: "Close session Alert first synthetic chat" }));
    await confirmClose();

    await waitFor(() => expect(transport.deleteAgentSession).toHaveBeenCalledExactlyOnceWith(first.session_id));
    const closeButton = screen.getByRole("button", { name: "Close session Alert first synthetic chat" });
    const row = closeButton.closest("li");
    expect(row).not.toBeNull();
    expect(await within(row!).findByText("Close was not confirmed. Its draft was kept. Try closing this chat again.")).toBeVisible();
    expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false });
  });

  it("keeps a draft when the owner cancels close confirmation", async () => {
    const current = liveSession("synthetic-close-cancel", "Cancel synthetic chat");
    const risk = vi.fn();
    const transport = syntheticTransport(current);
    transport.deleteAgentSession = vi.fn();
    render(<AgentPage onExitRiskChange={risk} transport={transport} />);

    const composer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(composer, { target: { value: "Synthetic cancelled close draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Close session Cancel synthetic chat" }));
    const dialog = await screen.findByRole("dialog", { name: "Close live chat?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Keep current state" }));

    expect(transport.deleteAgentSession).not.toHaveBeenCalled();
    expect(composer).toHaveValue("Synthetic cancelled close draft");
    expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false });
  });

  it("does not let a late close from a replaced transport clear a newer chat draft", async () => {
    const first = liveSession("synthetic-close-late-first", "Late first synthetic chat");
    const second = liveSession("synthetic-close-late-second", "Late second synthetic chat");
    const pending = deferred<void>();
    const firstTransport = syntheticTransport(first, second);
    firstTransport.deleteAgentSession = vi.fn(() => pending.promise);
    const secondTransport = syntheticTransport(first, second);
    const risk = vi.fn();
    const view = render(<AgentPage onExitRiskChange={risk} transport={firstTransport} />);

    const composer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(composer, { target: { value: "Synthetic old close draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Close session Late first synthetic chat" }));
    await confirmClose();
    await waitFor(() => expect(firstTransport.deleteAgentSession).toHaveBeenCalledExactlyOnceWith(first.session_id));

    view.rerender(<AgentPage onExitRiskChange={risk} transport={secondTransport} />);
    fireEvent.click(await screen.findByRole("button", { name: /Late second synthetic chat · 0 turns · live/u }));
    const newComposer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(newComposer, { target: { value: "Synthetic newer draft" } });

    await act(async () => {
      pending.resolve();
      await Promise.resolve();
    });
    await waitFor(() => expect(newComposer).toHaveValue("Synthetic newer draft"));
    expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false });
  });

  it("retains a pending close draft, then removes only that chat after success", async () => {
    const first = liveSession("synthetic-close-pending-first", "Pending first synthetic chat");
    const second = liveSession("synthetic-close-pending-second", "Pending second synthetic chat");
    let sessions = [first, second];
    const pending = deferred<void>();
    const risk = vi.fn();
    const transport = syntheticTransport(first, second);
    transport.listAgentSessions = vi.fn(async () => sessions);
    transport.deleteAgentSession = vi.fn(async (id: string) => {
      await pending.promise;
      sessions = sessions.filter((session) => session.session_id !== id);
    });
    render(<AgentPage onExitRiskChange={risk} transport={transport} />);

    const firstComposer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(firstComposer, { target: { value: "Synthetic pending-close draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Close session Pending first synthetic chat" }));
    await confirmClose();
    await waitFor(() => expect(transport.deleteAgentSession).toHaveBeenCalledExactlyOnceWith(first.session_id));
    expect(firstComposer).toHaveAttribute("readonly");
    expect(firstComposer).toBeEnabled();
    fireEvent.change(firstComposer, { target: { value: "Synthetic forbidden pending edit" } });
    expect(firstComposer).toHaveValue("Synthetic pending-close draft");
    expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false });

    fireEvent.click(screen.getByRole("button", { name: /Pending second synthetic chat · 0 turns · live/u }));
    const secondComposer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(secondComposer, { target: { value: "Synthetic second draft" } });

    fireEvent.click(screen.getByRole("button", { name: /^Pending first synthetic chat ·/u }));
    const lockedComposer = await screen.findByRole("textbox", { name: "Message to the agent" });
    expect(lockedComposer).toHaveValue("Synthetic pending-close draft");
    expect(lockedComposer).toHaveAttribute("readonly");
    fireEvent.click(screen.getByRole("button", { name: /Pending second synthetic chat · 0 turns · live/u }));

    await act(async () => {
      pending.resolve();
      await Promise.resolve();
    });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Close session Pending first synthetic chat" })).not.toBeInTheDocument());
    expect(secondComposer).toHaveValue("Synthetic second draft");
    expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false });
  });

  it("unlocks the exact draft after a deferred generic close failure", async () => {
    const current = liveSession("synthetic-close-unlock", "Unlock synthetic chat");
    const pending = deferred<void>();
    const transport = syntheticTransport(current);
    transport.deleteAgentSession = vi.fn(() => pending.promise);
    render(<AgentPage transport={transport} />);

    const composer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(composer, { target: { value: "Synthetic draft held while close is pending" } });
    fireEvent.click(screen.getByRole("button", { name: "Close session Unlock synthetic chat" }));
    await confirmClose();
    await waitFor(() => expect(transport.deleteAgentSession).toHaveBeenCalledExactlyOnceWith(current.session_id));
    expect(composer).toHaveAttribute("readonly");
    fireEvent.change(composer, { target: { value: "Synthetic forbidden pending replacement" } });
    expect(composer).toHaveValue("Synthetic draft held while close is pending");

    await act(async () => {
      pending.reject(new Error("Synthetic deferred close failure"));
      await Promise.resolve();
    });
    await waitFor(() => expect(composer).not.toHaveAttribute("readonly"));
    expect(composer).toHaveValue("Synthetic draft held while close is pending");
  });

  it("clears a noncurrent failure row and draft only after its retry succeeds", async () => {
    const first = liveSession("synthetic-close-retry-first", "Retry first synthetic chat");
    const second = liveSession("synthetic-close-retry-second", "Retry second synthetic chat");
    let sessions = [first, second];
    const risk = vi.fn();
    const transport = syntheticTransport(first, second);
    transport.listAgentSessions = vi.fn(async () => sessions);
    transport.deleteAgentSession = vi.fn()
      .mockRejectedValueOnce(new Error("Synthetic first close rejection"))
      .mockImplementationOnce(async (id: string) => { sessions = sessions.filter((session) => session.session_id !== id); });
    render(<AgentPage onExitRiskChange={risk} transport={transport} />);

    fireEvent.change(await screen.findByRole("textbox", { name: "Message to the agent" }), { target: { value: "Synthetic retry draft" } });
    fireEvent.click(screen.getByRole("button", { name: /Retry second synthetic chat · 0 turns · live/u }));
    await closeFallbackChat("Retry first synthetic chat");
    await rowCloseFailure("Retry first synthetic chat");
    expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: true, hasActiveWork: false });

    await closeFallbackChat("Retry first synthetic chat");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Close session Retry first synthetic chat" })).not.toBeInTheDocument());
    expect(screen.getByRole("textbox", { name: "Message to the agent" })).toHaveValue("");
    await waitFor(() => expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: false, hasActiveWork: false }));
  });

  it("keeps independent failed-close rows until each exact chat succeeds", async () => {
    const first = liveSession("synthetic-close-two-first", "Two first synthetic chat");
    const second = liveSession("synthetic-close-two-second", "Two second synthetic chat");
    const third = liveSession("synthetic-close-two-third", "Two third synthetic chat");
    let sessions = [first, second, third];
    const transport = syntheticTransport(first, second, third);
    const attempts = new Map<string, number>();
    transport.listAgentSessions = vi.fn(async () => sessions);
    transport.deleteAgentSession = vi.fn(async (id: string) => {
      const attempt = (attempts.get(id) ?? 0) + 1;
      attempts.set(id, attempt);
      if (id === first.session_id || id === third.session_id) {
        if (attempt === 1) {
          throw new Error(`Synthetic close failure for ${id}`);
        }
      }
      sessions = sessions.filter((session) => session.session_id !== id);
    });
    render(<AgentPage transport={transport} />);

    fireEvent.click(await screen.findByRole("button", { name: /Two second synthetic chat · 0 turns · live/u }));
    await closeFallbackChat("Two first synthetic chat");
    await closeFallbackChat("Two third synthetic chat");
    await rowCloseFailure("Two first synthetic chat");
    await rowCloseFailure("Two third synthetic chat");

    await closeFallbackChat("Two first synthetic chat");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Close session Two first synthetic chat" })).not.toBeInTheDocument());
    await rowCloseFailure("Two third synthetic chat");
  });

  it("does not show an old transport's late close failure on replacement rows", async () => {
    const first = liveSession("synthetic-close-late-failure", "Late failure synthetic chat");
    const second = liveSession("synthetic-close-late-replacement", "Replacement synthetic chat");
    const pending = deferred<void>();
    const firstTransport = syntheticTransport(first, second);
    firstTransport.deleteAgentSession = vi.fn(() => pending.promise);
    const secondTransport = syntheticTransport(first, second);
    const view = render(<AgentPage transport={firstTransport} />);

    await screen.findByRole("button", { name: "Close session Late failure synthetic chat" });
    await closeFallbackChat("Late failure synthetic chat");
    await waitFor(() => expect(firstTransport.deleteAgentSession).toHaveBeenCalledExactlyOnceWith(first.session_id));
    view.rerender(<AgentPage transport={secondTransport} />);
    await screen.findByRole("button", { name: /Replacement synthetic chat · 0 turns · live/u });
    await act(async () => {
      pending.reject(new Error("Synthetic late close failure"));
      await Promise.resolve();
    });

    expect(screen.queryByText("Close was not confirmed. Its draft was kept. Try closing this chat again.")).not.toBeInTheDocument();
  });

  it("does not let an old transport close lock block a replacement transport with the same chat id", async () => {
    const sessionId = "synthetic-close-same-id";
    const first = liveSession(sessionId, "Old same-id synthetic chat");
    const replacement = liveSession(sessionId, "Replacement same-id synthetic chat");
    const pending = deferred<void>();
    const firstTransport = syntheticTransport(first);
    firstTransport.deleteAgentSession = vi.fn(() => pending.promise);
    const replacementTransport = syntheticTransport(replacement);
    const risk = vi.fn();
    const view = render(<AgentPage onExitRiskChange={risk} transport={firstTransport} />);

    const firstComposer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(firstComposer, { target: { value: "Synthetic old transport draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Close session Old same-id synthetic chat" }));
    await confirmClose();
    await waitFor(() => expect(firstTransport.deleteAgentSession).toHaveBeenCalledExactlyOnceWith(sessionId));

    view.rerender(<AgentPage onExitRiskChange={risk} transport={replacementTransport} />);
    await screen.findByRole("button", { name: "Close session Replacement same-id synthetic chat" });
    const replacementComposer = await screen.findByRole("textbox", { name: "Message to the agent" });
    expect(replacementComposer).toHaveValue("");
    expect(risk).toHaveBeenLastCalledWith({ hasUnsavedChanges: false, hasActiveWork: false });
    expect(replacementComposer).not.toHaveAttribute("readonly");
    fireEvent.change(replacementComposer, { target: { value: "Synthetic replacement transport draft" } });
    expect(replacementComposer).toHaveValue("Synthetic replacement transport draft");

    await act(async () => {
      pending.reject(new Error("Synthetic old same-id close failure"));
      await Promise.resolve();
    });
    expect(replacementComposer).toHaveValue("Synthetic replacement transport draft");
    expect(replacementComposer).not.toHaveAttribute("readonly");
    expect(screen.queryByText("Close was not confirmed. Its draft was kept. Try closing this chat again.")).not.toBeInTheDocument();
    expect(screen.queryByText("Session closing")).not.toBeInTheDocument();
  });

  it("does not resurrect a draft when a same-id chat returns to its original transport", async () => {
    const sessionId = "synthetic-close-return-id";
    const first = liveSession(sessionId, "Original same-id synthetic chat");
    const replacement = liveSession(sessionId, "Replacement same-id synthetic chat");
    const firstTransport = syntheticTransport(first);
    const replacementTransport = syntheticTransport(replacement);
    const view = render(<AgentPage transport={firstTransport} />);

    const originalComposer = await screen.findByRole("textbox", { name: "Message to the agent" });
    fireEvent.change(originalComposer, { target: { value: "Synthetic original draft" } });
    view.rerender(<AgentPage transport={replacementTransport} />);
    await screen.findByRole("button", { name: "Close session Replacement same-id synthetic chat" });
    expect(await screen.findByRole("textbox", { name: "Message to the agent" })).toHaveValue("");

    view.rerender(<AgentPage transport={firstTransport} />);
    await screen.findByRole("button", { name: "Close session Original same-id synthetic chat" });
    expect(await screen.findByRole("textbox", { name: "Message to the agent" })).toHaveValue("");
  });
});

async function confirmClose(): Promise<void> {
  const dialog = await screen.findByRole("dialog", { name: "Close live chat?" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Close chat" }));
}

async function closeFallbackChat(title: string): Promise<void> {
  fireEvent.click(screen.getByRole("button", { name: `Close session ${title}` }));
  await confirmClose();
}

async function rowCloseFailure(title: string): Promise<void> {
  const closeButton = screen.getByRole("button", { name: `Close session ${title}` });
  const row = closeButton.closest("li");
  expect(row).not.toBeNull();
  expect(await within(row!).findByRole("alert")).toHaveTextContent("Close was not confirmed. Its draft was kept. Try closing this chat again.");
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((accept, decline) => { resolve = accept; reject = decline; });
  return { promise, reject, resolve };
}

function liveSession(sessionId: string, title: string): AgentSessionView {
  return {
    contract_version: "local-agent.v9",
    cleanup_unconfirmed: false,
    closing: false,
    stopping: false,
    session_id: sessionId,
    running: false,
    pending_approval_id: null,
    last_seq: 0,
    turns: 0,
    history_revision: 0,
    model_alias: null,
    created_at: "2040-01-01T00:00:00Z",
    recovered: false,
    authority_revalidated: true,
    history_write_failed: false,
    recovery_state: "current",
    settings: {
      workspace: "D:/synthetic/project",
      project_id: null,
      model_alias: null,
      parameters: { temperature: 0.2, top_p: 0.9, max_tokens: 100, enable_thinking: false },
      instructions: null,
      allow_writes: false,
      allow_commands: false,
      allow_web: false,
      max_steps: 1,
      command_timeout_seconds: 1,
      title,
      retention_policy: "metadata_only",
    },
  };
}

function stagedAttachment(sessionId: string): AgentAttachment {
  return {
    contract_version: "agent-attachment.v2",
    attachment_id: "a".repeat(32),
    session_id: sessionId,
    model_alias: "synthetic-close-attachment-model",
    capability_probe_version: "synthetic-probe.v1",
    display_name: "synthetic-close-note.md",
    kind: "document",
    media_type: "text/markdown",
    byte_size: 64,
    sha256: "b".repeat(64),
    width: null,
    height: null,
    duration_ms: null,
    sample_rate_hz: null,
    channels: null,
    routing: "local_text_projection",
    document_format: "markdown",
    projected_characters: 32,
    projection_truncated: false,
    omitted_features: [],
    context_tokens: null,
    context_cost_source: "runtime_unreported",
    source: "file",
    retention: "memory_only",
    state: "staged",
    created_at: "2040-01-01T00:00:00Z",
    expires_at: "2040-01-01T01:00:00Z",
    attached_event_seq: null,
  };
}

function syntheticTransport(...sessions: AgentSessionView[]): Parameters<typeof AgentPage>[0]["transport"] {
  const base = createSyntheticTransport();
  const transport = {
    ...base,
    listAgentSessions: vi.fn(async () => sessions),
    getAgentEvents: vi.fn(async (sessionId: string) => ({
      contract_version: "local-agent.v9" as const,
      cleanup_unconfirmed: false,
      closing: false,
      stopping: false,
      session_id: sessionId,
      events: [],
      running: false,
      pending_approval_id: null,
      last_seq: 0,
      first_seq: 0,
    })),
  } as Parameters<typeof AgentPage>[0]["transport"];
  Reflect.deleteProperty(transport, "listAgentProjects");
  Reflect.deleteProperty(transport, "createAgentProject");
  Reflect.deleteProperty(transport, "updateAgentProject");
  Reflect.deleteProperty(transport, "deleteAgentProject");
  Reflect.deleteProperty(transport, "listAgentCatalogSessions");
  Reflect.deleteProperty(transport, "updateAgentCatalogSession");
  Reflect.deleteProperty(transport, "deleteAgentCatalogSession");
  return transport;
}
