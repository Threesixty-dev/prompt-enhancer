import { useEffect, useRef, useState } from "react";
import type {
  LocalModelChatDelta,
  LocalModelChatMessage,
  LocalModelStatus,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";

const MAX_TURNS_KEPT = 12;
const MAX_PROMPT_CHARS = 20_000;

type Turn = { role: "user" | "assistant"; content: string; reasoning?: string; elapsedMs?: number };

/**
 * A small chat box for the running local models: pick a model, type, and the
 * reply streams in through the app's loopback proxy. Thinking is off by default
 * so quick tasks answer quickly; the history stays in this tab only.
 */
export function LocalModelChatPanel({
  models,
  transport,
}: {
  models: readonly LocalModelStatus[];
  transport: Pick<PromptEnhancerTransport, "streamLocalModelChat">;
}) {
  const running = models.filter((item) => item.runtime.state === "running");
  const [alias, setAlias] = useState<string>("");
  const [prompt, setPrompt] = useState("");
  const [thinking, setThinking] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState<Turn | null>(null);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);

  const chosen = alias ? running.find((item) => item.record.alias === alias) ?? null : running[0] ?? null;
  const lostModel = Boolean(alias) && running.length > 0 && !running.some((item) => item.record.alias === alias);

  useEffect(() => {
    if (!alias && running[0]) setAlias(running[0].record.alias);
  }, [alias, running]);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    const node = logRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [turns, draft]);

  async function send() {
    const text = prompt.trim();
    if (!chosen || !text || draft) return;
    setError("");
    const history: LocalModelChatMessage[] = [
      ...turns.slice(-MAX_TURNS_KEPT).map((turn) => ({ role: turn.role, content: turn.content })),
      { role: "user", content: text },
    ];
    const userTurn: Turn = { role: "user", content: text };
    setTurns((prev) => [...prev, userTurn]);
    setPrompt("");
    const controller = new AbortController();
    abortRef.current = controller;
    const reply: Turn = { role: "assistant", content: "", reasoning: "" };
    setDraft({ ...reply });
    const onDelta = (delta: LocalModelChatDelta) => {
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
      reply.elapsedMs = result.elapsed_ms;
      if (!reply.content && result.content) reply.content = result.content;
      setTurns((prev) => [...prev, { ...reply }]);
    } catch (caught) {
      if (controller.signal.aborted) {
        if (reply.content) setTurns((prev) => [...prev, { ...reply }]);
      } else {
        const status = caught instanceof TransportError ? caught.status : null;
        setError(
          status === 409
            ? "That model is not running any more - activate it and try again."
            : status === 400 || status === 413
              ? "The request was too long for the model's context window. Shorten it or start a new conversation."
              : "The model did not answer. Nothing was kept.",
        );
      }
    } finally {
      abortRef.current = null;
      setDraft(null);
    }
  }

  if (running.length === 0) {
    return (
      <section aria-labelledby="local-chat-title" className="local-models__section">
        <h2 id="local-chat-title">Chat</h2>
        <p className="local-models__note">Activate a model above to chat with it here or from any OpenAI-compatible tool.</p>
      </section>
    );
  }

  return (
    <section aria-labelledby="local-chat-title" className="local-models__section local-chat">
      <h2 id="local-chat-title">Chat</h2>
      <div className="local-chat__toolbar">
        <label>
          <span>Model</span>
          <select aria-label="Chat model" onChange={(e) => setAlias(e.currentTarget.value)} value={chosen?.record.alias ?? ""}>
            {running.map((item) => (
              <option key={item.record.alias} value={item.record.alias}>
                {item.record.display_name} · {item.runtime.device}
              </option>
            ))}
          </select>
        </label>
        <label className="local-chat__toggle">
          <input checked={thinking} onChange={(e) => setThinking(e.currentTarget.checked)} type="checkbox" />
          <span>Allow thinking (slower, better for hard questions)</span>
        </label>
        <button className="button button--ghost" disabled={turns.length === 0 && !draft} onClick={() => { abortRef.current?.abort(); setTurns([]); setError(""); }} type="button">
          New conversation
        </button>
      </div>
      {lostModel && <p className="local-models__error" role="alert">{alias} is no longer running. Pick another model above or activate it again.</p>}
      <div className="local-chat__log" ref={logRef} role="log" aria-live="off">
        {turns.length === 0 && !draft && (
          <p className="local-models__note">Nothing yet. Ask for a commit message, a regex, a summary of an error - whatever is handy. Stays on this machine.</p>
        )}
        {[...turns, ...(draft ? [draft] : [])].map((turn, index) => (
          <article key={`${index}-${turn.role}`} className={`local-chat__turn local-chat__turn--${turn.role}`} data-streaming={draft !== null && index === turns.length ? "true" : undefined}>
            <header>{turn.role === "user" ? "You" : chosen?.record.display_name ?? "Model"}{turn.elapsedMs !== undefined ? <small> · {(turn.elapsedMs / 1000).toFixed(1)} s</small> : null}</header>
            {turn.reasoning ? <details className="local-chat__reasoning"><summary>Thinking</summary><pre>{turn.reasoning}</pre></details> : null}
            <pre>{turn.content || (draft !== null && index === turns.length ? "…" : "")}</pre>
          </article>
        ))}
      </div>
      {error && <p className="local-models__error" role="alert">{error}</p>}
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
            <button className="button button--ghost" onClick={() => abortRef.current?.abort()} type="button">Stop</button>
          ) : (
            <button className="button button--primary" disabled={!prompt.trim() || !chosen} type="submit">Send</button>
          )}
        </div>
      </form>
      <p className="local-models__hint">
        Same model from other tools: base URL <code>{`${window.location.origin}/v1/local-models/${chosen?.record.alias ?? "<alias>"}/v1`}</code> with the app token as the API key
        (or <code>/v1/local-models/openai/v1</code> and pick the model by alias).
      </p>
    </section>
  );
}
