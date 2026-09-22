import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  LocalModelChatDelta,
  LocalModelChatResult,
  LocalModelStatus,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { LocalModelChatPanel } from "./LocalModelChatPanel";

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void; reject: (reason?: unknown) => void };
type ChatRequest = Parameters<PromptEnhancerTransport["streamLocalModelChat"]>[1];
type Stream = {
  alias: string;
  request: ChatRequest;
  emit: (delta: LocalModelChatDelta) => void;
  signal?: AbortSignal;
  gate: Deferred<LocalModelChatResult>;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((accept, decline) => {
    resolve = accept;
    reject = decline;
  });
  return { promise, reject, resolve };
}

/** Every call is captured and stays in flight until the test settles it by hand. */
function chatTransport() {
  const streams: Stream[] = [];
  const streamLocalModelChat = vi.fn(
    (alias: string, request: ChatRequest, onDelta: (delta: LocalModelChatDelta) => void, signal?: AbortSignal) => {
      const gate = deferred<LocalModelChatResult>();
      streams.push({ alias, emit: onDelta, gate, request, signal });
      return gate.promise;
    },
  );
  return { streamLocalModelChat, streams, transport: { streamLocalModelChat } };
}

function result(content: string, over: Partial<LocalModelChatResult> = {}): LocalModelChatResult {
  return { content, elapsed_ms: 1200, finish_reason: "stop", reasoning: "", ...over };
}

function status(over: { alias?: string; display?: string; state?: LocalModelStatus["runtime"]["state"] } = {}): LocalModelStatus {
  const alias = over.alias ?? "example-small";
  const state = over.state ?? "running";
  return {
    record: {
      alias, display_name: over.display ?? "Example Small", format: "gguf", path: "D:/example/models/example.gguf",
      source_repo: "example-org/Example-GGUF", source_file: "example.gguf", size_bytes: 4 * 1024 ** 3,
      sha256: null, source_revision: null, source_license: null, source_license_policy: null, provenance_verified: false,
      default_device: "cpu", default_gpu_layers: null, context_size: 4096, layer_count: 32, added_at: "2040-01-01T00:00:00Z",
    },
    runtime: { state, device: state === "running" ? "cpu" : null, gpu_layers: null, context_size: state === "running" ? 4096 : null, started_at: null, last_error_code: null, pid: null },
    placement: {
      contract_version: "local-model-placement.v1",
      alias,
      context_size: 4096,
      gpu_memory_free_mb: null,
      actual_offload_verified: false,
      options: [
        { device: "gpu", state: "blocked", reason_code: "accelerator_evidence_unavailable", recommended_gpu_layers: null, estimated_vram_required_mb: null },
        { device: "split", state: "blocked", reason_code: "accelerator_evidence_unavailable", recommended_gpu_layers: null, estimated_vram_required_mb: null },
        { device: "cpu", state: "available", reason_code: "cpu_available", recommended_gpu_layers: 0, estimated_vram_required_mb: 0 },
      ],
    },
    endpoint_path: `/v1/local-models/${alias}/chat/completions`,
  };
}

function ask(text: string) {
  fireEvent.change(screen.getByLabelText("Message"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}

function bubbles() {
  return Array.from(document.querySelectorAll(".local-chat__turn"));
}

function composer() {
  return screen.getByLabelText("Message") as HTMLTextAreaElement;
}

async function settle(stream: Stream, value: LocalModelChatResult) {
  await act(async () => {
    stream.gate.resolve(value);
    await stream.gate.promise;
  });
}

async function fail(stream: Stream, reason: unknown) {
  await act(async () => {
    stream.gate.reject(reason);
    await stream.gate.promise.catch(() => undefined);
  });
}

describe("LocalModelChatPanel", () => {
  it("reports whitespace drafts and zero-output in-flight replies as dirty", () => {
    const { streams, transport } = chatTransport();
    const dirty = vi.fn();
    render(<LocalModelChatPanel models={[status()]} onTemporaryChatDirtyChange={dirty} transport={transport} />);
    fireEvent.change(composer(), { target: { value: "   " } });
    expect(dirty).toHaveBeenLastCalledWith(true);
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(streams).toHaveLength(0);
    fireEvent.change(composer(), { target: { value: "request" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(dirty).toHaveBeenLastCalledWith(true);
  });

  it("reopens New conversation after Cancel and Escape while preserving the active draft", () => {
    const { streams, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);
    ask("partial request"); act(() => streams[0].emit({ content: "partial" }));
    fireEvent.change(composer(), { target: { value: "next draft" } });
    const trigger = screen.getByRole("button", { name: "New conversation" }); trigger.focus(); fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Start a new conversation?" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog", { name: "Start a new conversation?" })).not.toBeInTheDocument();
    expect(document.activeElement).toBe(trigger);
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Start a new conversation?" })).toBeVisible();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Start a new conversation?" })).not.toBeInTheDocument();
    expect(screen.getByText("partial")).toBeVisible(); expect(composer()).toHaveValue("next draft");
    expect(streams[0].signal?.aborted).toBe(false); expect(document.activeElement).toBe(trigger);
  });

  it("prevents unload only while temporary content is dirty, then removes the listener", async () => {
    const { streams, transport } = chatTransport();
    const view = render(<LocalModelChatPanel models={[status()]} transport={transport} />);
    const empty = new Event("beforeunload", { cancelable: true }); window.dispatchEvent(empty); expect(empty.defaultPrevented).toBe(false);
    fireEvent.change(composer(), { target: { value: "   " } });
    const draftEvent = new Event("beforeunload", { cancelable: true }); window.dispatchEvent(draftEvent); expect(draftEvent.defaultPrevented).toBe(true);
    ask("history request");
    await settle(streams[0], result("history reply"));
    const historyEvent = new Event("beforeunload", { cancelable: true }); window.dispatchEvent(historyEvent); expect(historyEvent.defaultPrevented).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
    fireEvent.click(screen.getByRole("button", { name: "Start new conversation" }));
    const resetEvent = new Event("beforeunload", { cancelable: true }); window.dispatchEvent(resetEvent); expect(resetEvent.defaultPrevented).toBe(false);
    fireEvent.change(composer(), { target: { value: "draft before unmount" } });
    view.unmount();
    const unmountedEvent = new Event("beforeunload", { cancelable: true }); window.dispatchEvent(unmountedEvent); expect(unmountedEvent.defaultPrevented).toBe(false);
  });

  it("reports history dirty and gives a replacement callback the current state", async () => {
    const first = vi.fn();
    const second = vi.fn();
    const { streams, transport } = chatTransport();
    const view = render(<LocalModelChatPanel models={[status()]} onTemporaryChatDirtyChange={first} transport={transport} />);
    ask("history request");
    await settle(streams[0], result("history reply"));
    expect(first).toHaveBeenLastCalledWith(true);
    expect(first.mock.calls).toEqual([[false], [true]]);
    view.rerender(<LocalModelChatPanel models={[status()]} onTemporaryChatDirtyChange={second} transport={transport} />);
    expect(second.mock.calls).toEqual([[true]]);
    view.unmount();
    await act(async () => { await Promise.resolve(); });
    expect(second.mock.calls).toEqual([[true], [false]]);
  });

  it("shows the temporary lifetime note in empty chat and hides the CTA without a callback", () => {
    const { transport } = chatTransport();
    render(<LocalModelChatPanel models={[]} transport={transport} />);
    expect(screen.getByText(/temporary and is not saved/i)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Open saved Agent chat" })).toBeNull();
  });

  it("confirms a new Agent setup once with the selected alias and makes no transport call", () => {
    const { transport } = chatTransport();
    const onOpenAgentChat = vi.fn();
    render(<LocalModelChatPanel models={[status()]} onOpenAgentChat={onOpenAgentChat} transport={transport} />);
    fireEvent.click(screen.getByRole("button", { name: "Open saved Agent chat" }));
    expect(screen.getByRole("dialog")).toHaveTextContent(/NEW Agent setup/);
    const continueButton = screen.getByRole("button", { name: "Continue to Agent" });
    fireEvent.click(continueButton);
    fireEvent.click(continueButton);
    expect(onOpenAgentChat).toHaveBeenCalledTimes(1);
    expect(onOpenAgentChat).toHaveBeenCalledWith("example-small");
    expect(transport.streamLocalModelChat).not.toHaveBeenCalled();
  });

  it("confirms with a null alias when no model is selected", () => {
    const { transport } = chatTransport();
    const onOpenAgentChat = vi.fn();
    render(<LocalModelChatPanel models={[]} onOpenAgentChat={onOpenAgentChat} transport={transport} />);
    expect(screen.getByText(/Activate a model above/i)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Open saved Agent chat" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue to Agent" }));
    expect(onOpenAgentChat).toHaveBeenCalledWith(null);
  });

  it("keeps partial stream and next draft on Cancel/Escape, restoring focus", () => {
    const { streams, transport } = chatTransport();
    const onOpenAgentChat = vi.fn();
    render(<LocalModelChatPanel models={[status()]} onOpenAgentChat={onOpenAgentChat} transport={transport} />);
    ask("stream request");
    act(() => streams[0].emit({ content: "partial synthetic reply" }));
    fireEvent.change(composer(), { target: { value: "next synthetic draft" } });
    const trigger = screen.getByRole("button", { name: "Open saved Agent chat" });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("partial synthetic reply")).toBeVisible();
    expect(composer()).toHaveValue("next synthetic draft");
    expect(document.activeElement).toBe(trigger);
    expect(streams[0].signal?.aborted).toBe(false);
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog")).toBeVisible();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(composer()).toHaveValue("next synthetic draft");
    expect(streams[0].signal?.aborted).toBe(false);
    expect(onOpenAgentChat).not.toHaveBeenCalled();
  });

  it.each([
    ["length", /response token limit/i],
    ["content_filter", /runtime filtered/i],
    ["tool_calls", /tool request/i],
    ["EXAMPLE_PRIVATE_FINISH_CANARY", /unrecognized completion/i],
  ])("keeps a %s reply visibly incomplete and out of the next model history", async (finish, notice) => {
    const { streams, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);
    ask("Example first request");
    act(() => streams[0].emit({ content: "Example unfinished answer" }));
    fireEvent.change(composer(), { target: { value: "Example next draft" } });
    await settle(streams[0], result("Example unfinished answer", { finish_reason: String(finish) }));

    expect(screen.getByRole("alert")).toHaveTextContent(notice);
    expect(screen.getByText("Example unfinished answer")).toBeVisible();
    expect(bubbles()[1]).toHaveAttribute("data-response-status", "incomplete");
    expect(screen.getByRole("button", { name: "Retry last message" })).toBeEnabled();
    expect(composer()).toHaveValue("Example next draft");
    expect(document.body.textContent).not.toContain("EXAMPLE_PRIVATE_FINISH_CANARY");
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(streams[1].request.messages).toEqual([
      { role: "user", content: "Example first request" },
      { role: "user", content: "Example next draft" },
    ]);
    expect(screen.getByText("Example unfinished answer")).toBeVisible();
    await settle(streams[1], result("Example completed answer"));
    expect(bubbles().at(-1)).toHaveAttribute("data-response-status", "complete");
  });

  it.each(["stop", "failure"])("keeps a partial %s reply out of follow-up history", async (ending) => {
    const { streams, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);
    ask("Example complete request");
    await settle(streams[0], result("Example complete answer"));
    ask("Example interrupted request");
    act(() => streams[1].emit({ content: "Example unfinished answer" }));
    if (ending === "stop") fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    else await fail(streams[1], new Error("Example interrupted connection"));
    expect(screen.getByText("Example unfinished answer")).toBeVisible();
    ask("Example follow-up request");
    expect(streams[2].request.messages).toEqual([
      { role: "user", content: "Example complete request" },
      { role: "assistant", content: "Example complete answer" },
      { role: "user", content: "Example interrupted request" },
      { role: "user", content: "Example follow-up request" },
    ]);
    expect(bubbles()[3]).toHaveAttribute("data-response-status", ending === "stop" ? "stopped" : "failed");
    await settle(streams[2], result("Example follow-up answer"));
  });

  it("retries a token-limited message exactly once while keeping the next draft", async () => {
    const { streams, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);
    ask("Example bounded request");
    fireEvent.change(composer(), { target: { value: "Example next draft" } });
    await settle(streams[0], result("Example unfinished answer", { finish_reason: "length" }));
    fireEvent.click(screen.getByRole("button", { name: "Retry last message" }));
    expect(streams).toHaveLength(2);
    expect(streams[1].request.messages).toEqual([{ role: "user", content: "Example bounded request" }]);
    expect(composer()).toHaveValue("Example next draft");
    await settle(streams[1], result("Example recovered answer"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry last message" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Example bounded request")).toHaveLength(1);
  });

  it("streams content and reasoning into the log", async () => {
    const { streamLocalModelChat, streams, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);

    ask("Summarise this log line");
    expect(streamLocalModelChat).toHaveBeenCalledTimes(1);
    expect(streams[0].alias).toBe("example-small");
    expect(streams[0].request.enable_thinking).toBe(false);
    expect(streams[0].request.messages).toEqual([{ role: "user", content: "Summarise this log line" }]);

    act(() => {
      streams[0].emit({ reasoning: "weighing two options" });
      streams[0].emit({ content: "one line" });
    });
    expect(screen.getByText("one line")).toBeInTheDocument();
    expect(screen.getByText("weighing two options")).toBeInTheDocument();

    await settle(streams[0], result("one line", { elapsed_ms: 2400, reasoning: "weighing two options" }));
    expect(screen.getByText(/2\.4 s/)).toBeInTheDocument();
    expect(bubbles()).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
  });

  it("keeps partial output when Stop is pressed and takes the next message straight away", async () => {
    const { streamLocalModelChat, streams, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);

    ask("Think about this");
    act(() => streams[0].emit({ reasoning: "still weighing it up" }));
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));

    expect(streams[0].signal?.aborted).toBe(true);
    // Reasoning-only output was really produced, so it stays on screen.
    expect(screen.getByText("still weighing it up")).toBeInTheDocument();
    expect(bubbles()).toHaveLength(2);

    // The next prompt goes out without waiting for the abandoned call to settle.
    ask("Next question");
    expect(streamLocalModelChat).toHaveBeenCalledTimes(2);

    await settle(streams[0], result("resurrected text"));
    expect(screen.queryByText("resurrected text")).toBeNull();
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();

    act(() => streams[1].emit({ content: "second reply" }));
    await settle(streams[1], result("second reply"));
    expect(screen.getByText("second reply")).toBeInTheDocument();
  });

  it("ignores a late delta and a late success from a conversation that was reset", async () => {
    const { streams, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);

    ask("First message");
    act(() => streams[0].emit({ content: "partial one" }));
    fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
    const abort = vi.spyOn(AbortController.prototype, "abort");
    const confirm = screen.getByRole("button", { name: "Start new conversation" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    expect(streams[0].signal?.aborted).toBe(true);
    expect(abort).toHaveBeenCalledTimes(1);
    abort.mockRestore();
    expect(screen.queryByText("partial one")).toBeNull();
    expect(bubbles()).toHaveLength(0);

    ask("Second message");
    expect(streams).toHaveLength(2);
    act(() => {
      streams[0].emit({ content: " and more" });
      streams[1].emit({ content: "second partial" });
    });
    expect(screen.queryByText(/and more/)).toBeNull();
    expect(screen.getByText("second partial")).toBeInTheDocument();

    await settle(streams[0], result("stale reply"));
    expect(screen.queryByText("stale reply")).toBeNull();
    expect(screen.getByText("second partial")).toBeInTheDocument();

    await settle(streams[1], result("second partial"));
    expect(bubbles()).toHaveLength(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("ignores a late failure from a replaced stream", async () => {
    const { streams, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);

    ask("First message");
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    ask("Second message");

    await fail(streams[0], new TransportError("aborted", 500));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(composer().value).toBe("");

    act(() => streams[1].emit({ content: "healthy reply" }));
    await settle(streams[1], result("healthy reply"));
    expect(screen.getByText("healthy reply")).toBeInTheDocument();
  });

  it("labels every reply with the model that produced it", async () => {
    const { streams, transport } = chatTransport();
    render(
      <LocalModelChatPanel
        models={[status(), status({ alias: "example-mini", display: "Example Mini" })]}
        transport={transport}
      />,
    );

    ask("Which model is this");
    await settle(streams[0], result("small reply"));
    fireEvent.change(screen.getByLabelText("Chat model"), { target: { value: "example-mini" } });

    expect((screen.getByLabelText("Chat model") as HTMLSelectElement).value).toBe("example-mini");
    expect(bubbles()[1].textContent).toContain("Example Small");
    expect(bubbles()[1].textContent).not.toContain("Example Mini");
  });

  it("keeps a stopped selection and disables Send instead of picking another model", () => {
    const { streamLocalModelChat, transport } = chatTransport();
    const view = render(
      <LocalModelChatPanel
        models={[status(), status({ alias: "example-mini", display: "Example Mini" })]}
        transport={transport}
      />,
    );

    fireEvent.change(screen.getByLabelText("Chat model"), { target: { value: "example-mini" } });
    view.rerender(
      <LocalModelChatPanel
        models={[status(), status({ alias: "example-mini", display: "Example Mini", state: "stopped" })]}
        transport={transport}
      />,
    );

    fireEvent.change(composer(), { target: { value: "Anyone there" } });
    expect((screen.getByLabelText("Chat model") as HTMLSelectElement).value).toBe("example-mini");
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Example Mini is not running, so sending is off/)).toBeInTheDocument();
    expect(streamLocalModelChat).not.toHaveBeenCalled();
  });

  it("keeps the conversation visible when every model stops", async () => {
    const { streams, transport } = chatTransport();
    const view = render(<LocalModelChatPanel models={[status()]} transport={transport} />);

    ask("Remember this");
    await settle(streams[0], result("kept reply"));
    view.rerender(<LocalModelChatPanel models={[status({ state: "stopped" })]} transport={transport} />);

    expect(screen.getByRole("log")).toBeInTheDocument();
    expect(screen.getByText("Remember this")).toBeInTheDocument();
    expect(screen.getByText("kept reply")).toBeInTheDocument();
    // No endpoint is offered for a model that is not running.
    expect(document.body.textContent).not.toContain("<alias>");
    expect(document.body.textContent).not.toContain("/v1/local-models/example-small/v1");
  });

  it("shows the compact note only when nothing has been said and nothing runs", () => {
    const { transport } = chatTransport();
    render(<LocalModelChatPanel models={[status({ state: "stopped" })]} transport={transport} />);

    expect(screen.getByText(/Activate a model above to chat/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Message")).toBeNull();
  });

  it("keeps an editable draft blocked when runtime status is unverified", () => {
    const { streamLocalModelChat, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} runtimeReadiness="unverified" transport={transport} />);

    fireEvent.change(composer(), { target: { value: "Keep this while status recovers" } });
    expect(composer()).toHaveValue("Keep this while status recovers");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    fireEvent.keyDown(composer(), { key: "Enter", ctrlKey: true });
    expect(streamLocalModelChat).not.toHaveBeenCalled();
    expect(composer()).toHaveValue("Keep this while status recovers");
    expect(screen.getByText(/unverified, so new messages/i)).toBeVisible();
  });

  it("keeps an active synthetic stream stoppable after runtime status becomes unverified", async () => {
    const { streams, transport } = chatTransport();
    const view = render(<LocalModelChatPanel models={[status()]} transport={transport} />);

    ask("Keep streaming through a read failure");
    act(() => streams[0].emit({ content: "partial before failure" }));
    view.rerender(<LocalModelChatPanel models={[status()]} runtimeReadiness="unverified" transport={transport} />);

    expect(screen.getByText("partial before failure")).toBeVisible();
    expect(screen.getByRole("button", { name: "Stop" })).toBeEnabled();
    fireEvent.change(composer(), { target: { value: "A draft kept during failure" } });
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(streams[0].signal?.aborted).toBe(true);
    expect(screen.getByText("partial before failure")).toBeVisible();
    expect(composer()).toHaveValue("A draft kept during failure");
    expect(streams).toHaveLength(1);
    await settle(streams[0], result("late stream result"));
    expect(screen.queryByText("late stream result")).toBeNull();
  });

  it("keeps the message and the history when the model fails, without sending it twice", async () => {
    const { streams, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);

    ask("First message");
    await settle(streams[0], result("first reply"));
    ask("Second message");
    await fail(streams[1], new TransportError("model gone", 409));

    expect(screen.getByRole("alert").textContent).toContain("not running any more");
    expect(composer().value).toBe("");
    expect(screen.getByText("First message")).toBeInTheDocument();
    expect(screen.getByText("first reply")).toBeInTheDocument();
    expect(screen.getByText("Second message")).toBeInTheDocument();
    expect(bubbles()).toHaveLength(3);

    fireEvent.click(screen.getByRole("button", { name: "Retry last message" }));
    expect(streams[2].request.messages).toEqual([
      { role: "user", content: "First message" },
      { role: "assistant", content: "first reply" },
      { role: "user", content: "Second message" },
    ]);
  });

  it("gates Retry while runtime status is unverified and restores it only after explicit recovery", async () => {
    const { streams, transport } = chatTransport();
    const view = render(<LocalModelChatPanel models={[status()]} transport={transport} />);

    ask("Original request kept for retry");
    fireEvent.change(composer(), { target: { value: "Next draft kept aside" } });
    await fail(streams[0], new TransportError("synthetic runtime stopped", 409, "runtime_unavailable"));

    const retry = screen.getByRole("button", { name: "Retry last message" });
    expect(retry).toBeEnabled();
    view.rerender(<LocalModelChatPanel models={[status()]} runtimeReadiness="unverified" transport={transport} />);
    expect(screen.getByRole("button", { name: "Retry last message" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Retry last message" })).toHaveAttribute("aria-describedby", "local-chat-runtime-unverified");
    expect(composer()).toHaveValue("Next draft kept aside");
    expect(streams).toHaveLength(1);

    view.rerender(<LocalModelChatPanel models={[status()]} transport={transport} />);
    expect(screen.getByRole("button", { name: "Retry last message" })).toBeEnabled();
    expect(composer()).toHaveValue("Next draft kept aside");
    expect(streams).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Retry last message" }));
    expect(streams).toHaveLength(2);
    expect(streams[1].request.messages).toEqual([{ role: "user", content: "Original request kept for retry" }]);
    expect(composer()).toHaveValue("Next draft kept aside");
    await settle(streams[1], result("Recovered original reply"));
    expect(screen.getByText("Recovered original reply")).toBeVisible();
  });

  it("says so when the model finishes without any text", async () => {
    const { streams, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);

    ask("Say nothing");
    await settle(streams[0], result("", { finish_reason: "stop" }));

    expect(screen.getByRole("alert").textContent).toContain("without sending any text back");
    expect(bubbles()).toHaveLength(1);
    expect(screen.getByText("Say nothing")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry last message" }));
    expect(streams[1].request.messages).toEqual([{ role: "user", content: "Say nothing" }]);
  });

  it("preserves the next draft and partial output on failure, without duplicating a retried prompt", async () => {
    const { streams, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);
    ask("Example first prompt");
    act(() => streams[0].emit({ content: "Example partial answer" }));
    fireEvent.change(composer(), { target: { value: "Example next draft" } });
    await fail(streams[0], new Error("example-stream-error"));
    expect(screen.getByText("Example first prompt")).toBeVisible();
    expect(screen.getByText("Example partial answer")).toBeVisible();
    expect(composer()).toHaveValue("Example next draft");
    fireEvent.click(screen.getByRole("button", { name: "Retry last message" }));
    expect(streams[1].request.messages).toEqual([{ role: "user", content: "Example first prompt" }]);
    expect(composer()).toHaveValue("Example next draft");
    await settle(streams[1], result("Example final answer"));
    expect(screen.getAllByText("Example first prompt")).toHaveLength(1);
    expect(screen.queryByText("Example partial answer")).not.toBeInTheDocument();
  });

  it("clears an unsent draft on New conversation and leaves no old content to resend", () => {
    const { transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);
    fireEvent.change(composer(), { target: { value: "Example unsent draft" } });
    fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
    fireEvent.click(screen.getByRole("button", { name: "Start new conversation" }));
    expect(composer()).toHaveValue("");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("does not send an empty assistant history entry after stopping reasoning-only output", () => {
    const { streams, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);
    ask("Example first prompt");
    act(() => streams[0].emit({ reasoning: "Example model output" }));
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    ask("Example next prompt");
    expect(streams[1].request.messages.every((turn) => turn.content.trim().length > 0)).toBe(true);
    expect(streams[1].request.messages.some((turn) => turn.content === "Example model output")).toBe(false);
  });

  it("sends once when the form is submitted twice before React re-renders", async () => {
    const { streamLocalModelChat, transport } = chatTransport();
    render(<LocalModelChatPanel models={[status()]} transport={transport} />);

    fireEvent.change(composer(), { target: { value: "Only once" } });
    const form = composer().closest("form") as HTMLFormElement;
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(streamLocalModelChat).toHaveBeenCalledTimes(1);
  });

  it("aborts and disowns the reply when the panel unmounts", async () => {
    const { streams, transport } = chatTransport();
    const view = render(<LocalModelChatPanel models={[status()]} transport={transport} />);

    ask("Going away");
    act(() => streams[0].emit({ content: "partial" }));
    view.unmount();

    expect(streams[0].signal?.aborted).toBe(true);
    await settle(streams[0], result("late reply"));
    expect(document.body.textContent).not.toContain("late reply");
  });

  it("aborts and disowns the reply when the transport changes", async () => {
    const first = chatTransport();
    const second = chatTransport();
    const view = render(<LocalModelChatPanel models={[status()]} transport={first.transport} />);

    ask("Before the swap");
    act(() => first.streams[0].emit({ content: "half a reply" }));
    view.rerender(<LocalModelChatPanel models={[status()]} transport={second.transport} />);

    expect(first.streams[0].signal?.aborted).toBe(true);
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();

    await settle(first.streams[0], result("stale reply"));
    expect(screen.queryByText("stale reply")).toBeNull();

    ask("After the swap");
    expect(second.streams).toHaveLength(1);
    await settle(second.streams[0], result("fresh reply"));
    expect(screen.getByText("fresh reply")).toBeInTheDocument();
  });
});
