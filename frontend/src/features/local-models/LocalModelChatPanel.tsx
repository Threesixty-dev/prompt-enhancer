import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type {
  LocalModelChatDelta,
  LocalModelChatMessage,
  LocalModelStatus,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { Dialog } from "../../shared/ui/Dialog";

const MAX_TURNS_KEPT = 12;
const MAX_PROMPT_CHARS = 20_000;

type Turn = {
  role: "user" | "assistant";
  content: string;
  reasoning?: string;
  elapsedMs?: number;
  model?: string;
  completion?: "complete" | "stopped" | "incomplete" | "failed";
};

/** One reply in flight. The id is what makes a late callback recognisable as stale. */
type ActiveReply = { id: number; controller: AbortController; reply: Turn };
type RetryTurn = { before: Turn[]; user: Turn };

function incompleteNotice(reason: string | null): string | null {
  if (reason === null || reason === "stop") return null;
  if (reason === "length") return "The model reached its response token limit before finishing. Ask for a smaller response, or retry.";
  if (reason === "content_filter") return "The local runtime filtered the response before it completed. You can revise your request.";
  if (reason === "tool_calls" || reason === "function_call") return "The model returned a tool request, but this chat cannot run tools. Use an Agent session for tool work.";
  return "The runtime returned an unrecognized completion reason. Check the model runtime before retrying.";
}

/**
 * A small chat box for the running local models: pick a model, type, and the
 * reply streams in through the app's loopback proxy. Thinking is off by default
 * so quick tasks answer quickly; the history stays in this tab only.
 */
export function LocalModelChatPanel({
  models,
  runtimeReadiness = "verified",
  transport,
  onOpenAgentChat,
  onTemporaryChatDirtyChange,
}: {
  models: readonly LocalModelStatus[];
  runtimeReadiness?: "verified" | "unverified";
  transport: Pick<PromptEnhancerTransport, "streamLocalModelChat">;
  onOpenAgentChat?: (modelAlias: string | null) => void;
  onTemporaryChatDirtyChange?: (dirty: boolean) => void;
}) {
  const running = models.filter((item) => item.runtime.state === "running");
  const [alias, setAlias] = useState<string>("");
  const [prompt, setPrompt] = useState("");
  const [thinking, setThinking] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState<Turn | null>(null);
  const [error, setError] = useState("");
  const [retryTurn, setRetryTurn] = useState<RetryTurn | null>(null);
  const [agentDialogOpen, setAgentDialogOpen] = useState(false);
  const [newConversationOpen, setNewConversationOpen] = useState(false);
  const agentTriggerRef = useRef<HTMLButtonElement | null>(null);
  const agentDialogOpeningRef = useRef(false);
  const newConversationTriggerRef = useRef<HTMLButtonElement | null>(null);
  const resettingRef = useRef(false);
  const activeRef = useRef<ActiveReply | null>(null);
  const lastDirtyRef = useRef<boolean | null>(null);
  const lastDirtyCallbackRef = useRef<typeof onTemporaryChatDirtyChange>(undefined);
  const mountedRef = useRef(false);
  const dirty = prompt.length > 0 || turns.length > 0 || draft !== null || activeRef.current !== null;
  const dirtyCallbackRef = useRef(onTemporaryChatDirtyChange);
  dirtyCallbackRef.current = onTemporaryChatDirtyChange;

  useLayoutEffect(() => {
    if (!onTemporaryChatDirtyChange) return;
    if (lastDirtyRef.current !== dirty || lastDirtyCallbackRef.current !== onTemporaryChatDirtyChange) {
      lastDirtyRef.current = dirty;
      lastDirtyCallbackRef.current = onTemporaryChatDirtyChange;
      onTemporaryChatDirtyChange(dirty);
    }
  }, [dirty, onTemporaryChatDirtyChange]);
  useLayoutEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      // Strict Mode immediately re-runs layout effects. Deferring lets its
      // replacement setup win, while a real unmount still reports false.
      queueMicrotask(() => {
        if (!mountedRef.current) {
          dirtyCallbackRef.current?.(false);
          lastDirtyRef.current = false;
        }
      });
    };
  }, []);

  useLayoutEffect(() => {
    if (!dirty) return undefined;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);
  const sendingRef = useRef(false);
  const idRef = useRef(0);
  const logRef = useRef<HTMLDivElement | null>(null);

  const selected = alias ? models.find((item) => item.record.alias === alias) ?? null : null;
  const chosen = selected && selected.runtime.state === "running" ? selected : null;
  const runtimeUnverified = runtimeReadiness === "unverified";
  const stoppedSelection = Boolean(alias) && !chosen && !runtimeUnverified;
  const unverifiedSelection = Boolean(alias) && !chosen && runtimeUnverified;
  const firstRunning = running[0]?.record.alias ?? "";
  const selectedAlias = alias || null;

  /** Drops ownership of the reply in flight, so its late callbacks find no owner. */
  function disown() {
    const active = activeRef.current;
    activeRef.current = null;
    sendingRef.current = false;
    return active;
  }

  // Only ever fills an empty choice: a model that stops stays selected, so the
  // next message can never go silently to a different model.
  useEffect(() => {
    if (!alias && firstRunning) setAlias(firstRunning);
  }, [alias, firstRunning]);

  // A reply belongs to the transport that started it: losing the component or
  // the transport ends it and disowns whatever is still in flight.
  useEffect(() => {
    setDraft(null);
    setRetryTurn(null);
    return () => {
      disown()?.controller.abort();
    };
  }, [transport]);

  useEffect(() => {
    const node = logRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [turns, draft]);

  /** Ends the reply now and keeps whatever was already on screen. */
  function stop() {
    const active = disown();
    if (!active) return;
    active.controller.abort();
    if (active.reply.content || active.reply.reasoning) {
      setTurns((prev) => [...prev, { ...active.reply, completion: "stopped" }]);
    }
    setDraft(null);
  }

  function reset() {
    disown()?.controller.abort();
    setTurns([]);
    setDraft(null);
    setError("");
    setPrompt("");
    setRetryTurn(null);
  }

  function requestReset() {
    if (prompt.length > 0 || turns.length > 0 || draft !== null || activeRef.current !== null) {
      resettingRef.current = false;
      setNewConversationOpen(true);
    }
    else reset();
  }

  function closeAgentDialog() {
    agentDialogOpeningRef.current = false;
    setAgentDialogOpen(false);
  }

  async function send(retry?: RetryTurn) {
    const text = retry?.user.content ?? prompt.trim();
    if (sendingRef.current || activeRef.current || !text) return;
    if (runtimeUnverified) {
      setError("Runtime status is unverified, so new messages and retries stay off until Refresh confirms the selected model. A reply already streaming can still be stopped.");
      return;
    }
    if (!chosen) return;
    sendingRef.current = true;
    const id = ++idRef.current;
    const mine = () => activeRef.current?.id === id;
    setError("");
    setRetryTurn(null);
    const before = retry?.before ?? turns;
    const history: LocalModelChatMessage[] = [
      ...before
        .filter((turn) => turn.content.trim() && (turn.role === "user" || turn.completion === "complete"))
        .slice(-MAX_TURNS_KEPT)
        .map((turn) => ({ role: turn.role, content: turn.content })),
      { role: "user", content: text },
    ];
    const userTurn: Turn = retry?.user ?? { role: "user", content: text };
    setTurns([...before, userTurn]);
    if (!retry) setPrompt("");
    const controller = new AbortController();
    // The label is taken now, so changing the model later cannot relabel this reply.
    const reply: Turn = { role: "assistant", content: "", reasoning: "", model: chosen.record.display_name };
    activeRef.current = { controller, id, reply };
    setDraft({ ...reply });
    const onDelta = (delta: LocalModelChatDelta) => {
      if (!mine()) return;
      if (delta.content) reply.content += delta.content;
      if (delta.reasoning) reply.reasoning = `${reply.reasoning ?? ""}${delta.reasoning}`;
      setDraft({ ...reply });
    };
    try {
      const result = await transport.streamLocalModelChat(
        chosen.record.alias,
        { messages: history, enable_thinking: thinking, temperature: 0.4 },
        onDelta,
        controller.signal,
      );
      if (!mine()) return;
      const content = reply.content || result.content;
      const reasoning = reply.reasoning || result.reasoning;
      const notice = incompleteNotice(result.finish_reason);
      const completion = notice || !content.trim() ? "incomplete" : "complete";
      if (content || reasoning) {
        setTurns((prev) => [...prev, { ...reply, content, elapsedMs: result.elapsed_ms, reasoning, completion }]);
      }
      if (notice) {
        setError(notice + " Your message and partial output are kept here; incomplete output is not sent as conversation history.");
        setRetryTurn({ before, user: userTurn });
      } else if (!content.trim()) {
        setError(reasoning
          ? "The model returned thinking but no final answer. Your message is kept here; you can retry it."
          : "The model finished without sending any text back. Your message is kept here; you can retry it.");
        setRetryTurn({ before, user: userTurn });
      }
    } catch (caught) {
      if (!mine()) return;
      const status = caught instanceof TransportError ? caught.status : null;
      setError(
        status === 409
          ? "That model is not running any more. Your message is kept here. Activate it or choose another model, then retry."
          : status === 400 || status === 413
            ? "The conversation was too long for this model's context window. Shorten the message or start a new conversation."
            : "The reply did not finish. Your message and any partial output are kept here. You can retry without losing your next draft.",
      );
      if (reply.content || reply.reasoning) setTurns((prev) => [...prev, { ...reply, completion: "failed" }]);
      setRetryTurn({ before, user: userTurn });
    } finally {
      if (mine()) {
        disown();
        setDraft(null);
      }
    }
  }

  // Only the untouched, no-model case is compact: a conversation stays on screen
  // even after every model stops.
  if (running.length === 0 && turns.length === 0 && !draft && !error && !prompt && !runtimeUnverified && !onOpenAgentChat) {
    return (
      <section aria-labelledby="local-chat-title" className="local-models__section">
        <h2 id="local-chat-title">Chat</h2>
        <p className="local-models__note">Activate a model above to chat with it here or from any OpenAI-compatible tool.</p>
        <p className="local-models__note">This chat is temporary and is not saved. Leaving Models, reloading, or closing the page discards the conversation.</p>
        {!onOpenAgentChat && <p className="local-models__hint">For saved chats, use Agent.</p>}
      </section>
    );
  }

  return (
    <section aria-labelledby="local-chat-title" className="local-models__section local-chat">
      <h2 id="local-chat-title">Chat</h2>
      <div className="local-chat__toolbar">
        <label>
          <span>Model</span>
          <select aria-label="Chat model" onChange={(e) => setAlias(e.currentTarget.value)} value={alias}>
            {!alias && <option value="">No model running</option>}
            {running.map((item) => (
              <option key={item.record.alias} value={item.record.alias}>
                {item.record.display_name} · {item.runtime.device}
              </option>
            ))}
            {stoppedSelection && <option value={alias}>{selected?.record.display_name ?? alias} · stopped</option>}
            {unverifiedSelection && <option value={alias}>{selected?.record.display_name ?? alias} · status unverified</option>}
          </select>
        </label>
        <label className="local-chat__toggle">
          <input checked={thinking} onChange={(e) => setThinking(e.currentTarget.checked)} type="checkbox" />
          <span>Allow thinking (slower, better for hard questions)</span>
        </label>
        <button className="button button--ghost" disabled={turns.length === 0 && !draft && !error && !prompt} onClick={requestReset} ref={newConversationTriggerRef} type="button">
          New conversation
        </button>
      </div>
      <Dialog
        onClose={() => setNewConversationOpen(false)}
        open={newConversationOpen}
        title="Start a new conversation?"
        footer={<><button className="button button--ghost" onClick={() => setNewConversationOpen(false)} type="button">Cancel</button><button className="button button--primary" onClick={() => { if (resettingRef.current) return; resettingRef.current = true; setNewConversationOpen(false); reset(); }} type="button">Start new conversation</button></>}
      >
        <p>This clears the temporary conversation, draft, and any active reply.</p>
      </Dialog>
      <p className="local-models__note">This chat is temporary and is not saved. Leaving Models, reloading, or closing the page discards the conversation.</p>
      {onOpenAgentChat ? (
        <>
          <button className="button button--ghost" onClick={() => {
            if (agentDialogOpeningRef.current) return;
            agentDialogOpeningRef.current = true;
            setAgentDialogOpen(true);
          }} ref={agentTriggerRef} type="button">Open saved Agent chat</button>
          <Dialog
            description="A saved Agent chat starts separately from this temporary conversation."
            footer={(
              <>
                <button className="button button--ghost" onClick={closeAgentDialog} type="button">Cancel</button>
                <button
                  className="button button--primary"
                  onClick={() => {
                    if (!agentDialogOpeningRef.current) return;
                    agentDialogOpeningRef.current = false;
                    setAgentDialogOpen(false);
                    onOpenAgentChat(selectedAlias);
                  }}
                  type="button"
                >Continue to Agent</button>
              </>
            )}
            onClose={closeAgentDialog}
            open={agentDialogOpen}
            title="Open a saved Agent chat?"
          >
            <p>This opens a NEW Agent setup. No messages, draft, reasoning, or history are copied.</p>
            <p>Leaving Models discards this temporary content and stops any active reply. Workspace and history retention are chosen next.</p>
          </Dialog>
        </>
      ) : <p className="local-models__hint">For saved chats, use Agent.</p>}
      {running.length === 0 && !runtimeUnverified && <p className="local-models__note">Activate a model above to chat with it here or from any OpenAI-compatible tool.</p>}
      {stoppedSelection && (
        <p className="local-models__error" role="alert">
          {selected?.record.display_name ?? alias} is not running, so sending is off. Activate it again to carry on here, or choose another model above.
        </p>
      )}
      {runtimeUnverified && (
        <p className="local-models__error" id="local-chat-runtime-unverified" role="alert">
          Runtime status is unverified. New messages and retries are disabled until the local model page refreshes it; an existing reply can still be stopped.
        </p>
      )}
      <div className="local-chat__log" ref={logRef} role="log" aria-live="off">
        {turns.length === 0 && !draft && (
          <p className="local-models__note">Nothing yet. Ask for a commit message, a regex, a summary of an error - whatever is handy. Stays on this machine.</p>
        )}
        {[...turns, ...(draft ? [draft] : [])].map((turn, index) => (
          <article key={`${index}-${turn.role}`} className={`local-chat__turn local-chat__turn--${turn.role}`} data-response-status={turn.completion} data-streaming={draft !== null && index === turns.length ? "true" : undefined}>
            <header>
              {turn.role === "user" ? "You" : turn.model ?? "Model"}
              {turn.elapsedMs !== undefined ? <small> · {(turn.elapsedMs / 1000).toFixed(1)} s</small> : null}
              {turn.completion ? <small> · {turn.completion === "failed" ? "interrupted" : turn.completion}</small> : null}
            </header>
            {turn.reasoning ? <details className="local-chat__reasoning"><summary>Thinking</summary><pre>{turn.reasoning}</pre></details> : null}
            <pre>{turn.content || (draft !== null && index === turns.length ? "…" : "")}</pre>
          </article>
        ))}
      </div>
      {error && <p className="local-models__error" role="alert">{error}</p>}
      {retryTurn && <button aria-describedby={runtimeUnverified ? "local-chat-runtime-unverified" : undefined} className="button button--ghost" disabled={!chosen || runtimeUnverified || draft !== null} onClick={() => void send(retryTurn)} type="button">Retry last message</button>}
      <form
        className="local-chat__compose"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <textarea
          aria-label="Message"
          maxLength={MAX_PROMPT_CHARS}
          onChange={(e) => setPrompt(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="Type a message - Ctrl+Enter sends"
          rows={3}
          value={prompt}
        />
        <div className="local-chat__buttons">
          {draft ? (
            <button className="button button--ghost" onClick={stop} type="button">Stop</button>
          ) : (
            <button aria-describedby={runtimeUnverified ? "local-chat-runtime-unverified" : undefined} className="button button--primary" disabled={!prompt.trim() || !chosen || runtimeUnverified} type="submit">Send</button>
          )}
        </div>
      </form>
      {chosen && (
        <p className="local-models__hint">
          Same model from other tools: base URL <code>{`${window.location.origin}/v1/local-models/${chosen.record.alias}/v1`}</code> with the app token as the API key
          (or <code>/v1/local-models/openai/v1</code> and pick the model by alias).
        </p>
      )}
    </section>
  );
}
