import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentEvent, AgentSessionView, AgentSettings, LocalModelsOverview, PromptEnhancerTransport } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import "./AgentPage.css";

const POLL_MS = 700;
const IDLE_POLL_MS = 4000;
const TOOL_LABELS: Record<string, string> = {
  read_file: "Read file",
  list_dir: "List folder",
  search_text: "Search",
  write_file: "Write file",
  run_command: "Run command",
  fetch_url: "Fetch URL",
};

export function openAgentWindow(sessionId?: string): Window | null {
  const name = `pe-agent-${sessionId ? sessionId.slice(0, 12) : "new"}`;
  try {
    return window.open(sessionId ? `/agent/window/${sessionId}` : "/agent/window", name, "popup=yes,width=920,height=860,resizable=yes,scrollbars=yes");
  } catch {
    return null;
  }
}

function summarizeArguments(tool: string | null | undefined, args: Record<string, unknown> | null | undefined): string {
  if (!args) return "";
  if (tool === "read_file" || tool === "write_file") return String(args.path ?? "");
  if (tool === "list_dir") return String(args.path ?? ".");
  if (tool === "search_text") return `"${String(args.query ?? "")}"${args.glob ? ` in ${String(args.glob)}` : ""}`;
  if (tool === "run_command") return String(args.command ?? "");
  if (tool === "fetch_url") return String(args.url ?? "");
  return JSON.stringify(args).slice(0, 120);
}

type TransportSlice = Pick<
  PromptEnhancerTransport,
  "listAgentSessions" | "createAgentSession" | "getAgentSession" | "deleteAgentSession" | "sendAgentMessage" | "getAgentEvents" | "decideAgentApproval" | "stopAgentSession"
> & Partial<Pick<PromptEnhancerTransport, "getLocalModels">>;

/**
 * Agent workspace: a local model works inside one folder through tools. Reads
 * are free; writes (with a diff), commands and web fetches pause for your
 * approval. Everything stays on this machine; nothing is stored beyond the
 * server's memory.
 */
export function AgentPage({
  sessionId,
  transport,
  windowMode = false,
}: {
  sessionId?: string;
  transport: TransportSlice;
  windowMode?: boolean;
}) {
  const [sessions, setSessions] = useState<AgentSessionView[] | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [current, setCurrent] = useState<AgentSessionView | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [models, setModels] = useState<LocalModelsOverview | null>(null);
  const [workspace, setWorkspace] = useState("");
  const [modelAlias, setModelAlias] = useState("");
  const [allowWrites, setAllowWrites] = useState(true);
  const [allowCommands, setAllowCommands] = useState(true);
  const [allowWeb, setAllowWeb] = useState(false);
  const [temperature, setTemperature] = useState(0.2);
  const [topP, setTopP] = useState(0.95);
  const [maxTokens, setMaxTokens] = useState(1400);
  const [thinking, setThinking] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const lastSeq = useRef(0);
  const logRef = useRef<HTMLDivElement | null>(null);

  const refreshSessions = useCallback(async (signal?: AbortSignal) => {
    try {
      const list = await transport.listAgentSessions(signal);
      if (signal?.aborted) return;
      setSessions(list);
      setUnavailable(false);
    } catch (caught) {
      if (signal?.aborted) return;
      if (caught instanceof TransportError && caught.status === 404) setUnavailable(true);
      else setSessions([]);
    }
  }, [transport]);

  useEffect(() => {
    const controller = new AbortController();
    void refreshSessions(controller.signal);
    transport.getLocalModels?.(controller.signal).then((value) => { if (!controller.signal.aborted) setModels(value); }).catch(() => undefined);
    return () => controller.abort();
  }, [refreshSessions, transport]);

  // Pick the session from the route, or the newest one.
  useEffect(() => {
    if (!sessions) return;
    const wanted = sessionId ? sessions.find((s) => s.session_id === sessionId) : current ? sessions.find((s) => s.session_id === current.session_id) : sessions[0];
    if (wanted && wanted.session_id !== current?.session_id) {
      setCurrent(wanted);
      setEvents([]);
      lastSeq.current = 0;
    }
  }, [sessions, sessionId, current]);

  // Poll events while a session is open; faster while it runs or waits for approval.
  useEffect(() => {
    if (!current) return;
    let cancelled = false;
    const controller = new AbortController();
    const tick = async (): Promise<boolean> => {
      try {
        const page = await transport.getAgentEvents(current.session_id, lastSeq.current, controller.signal);
        if (cancelled) return false;
        if (page.events.length > 0) {
          setEvents((prev) => [...prev, ...page.events]);
          lastSeq.current = page.events[page.events.length - 1].seq;
        }
        setCurrent((prev) => prev && prev.session_id === page.session_id ? { ...prev, running: page.running, pending_approval_id: page.pending_approval_id ?? null, last_seq: page.last_seq } : prev);
        return page.running || Boolean(page.pending_approval_id) || page.events.length > 0;
      } catch {
        return true; // transient; keep polling at the active rate
      }
    };
    let handle = 0;
    const schedule = (active: boolean) => {
      if (cancelled) return;
      handle = window.setTimeout(async () => {
        schedule(await tick());
      }, active ? POLL_MS : IDLE_POLL_MS);
    };
    void tick().then(schedule);
    return () => { cancelled = true; controller.abort(); window.clearTimeout(handle); };
  }, [current?.session_id, transport]);

  useEffect(() => {
    const node = logRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [events]);

  const runningModels = useMemo(() => (models?.models ?? []).filter((m) => m.runtime.state === "running"), [models]);
  const pending = useMemo(() => {
    if (!current?.pending_approval_id) return null;
    return [...events].reverse().find((e) => e.kind === "approval_required" && e.approval_id === current.pending_approval_id) ?? null;
  }, [events, current?.pending_approval_id]);

  async function createSession() {
    const path = workspace.trim();
    if (!path) return;
    setBusy(true);
    setMessage("");
    try {
      const settings: AgentSettings = {
        workspace: path,
        model_alias: modelAlias || null,
        parameters: { temperature, top_p: topP, max_tokens: maxTokens, enable_thinking: thinking },
        instructions: instructions.trim() || null,
        allow_writes: allowWrites,
        allow_commands: allowCommands,
        allow_web: allowWeb,
        max_steps: 10,
        command_timeout_seconds: 120,
      };
      const created = await transport.createAgentSession(settings);
      await refreshSessions();
      setCurrent(created);
      setEvents([]);
      lastSeq.current = 0;
    } catch (caught) {
      const status = caught instanceof TransportError ? caught.status : null;
      setMessage(status === 422 ? "That is not an existing folder (use an absolute path, not a drive root)." : status === 403 ? "That folder is outside the allowed roots." : status === 409 ? "Too many open sessions - close one first." : "The session could not be created.");
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    const text = draft.trim();
    if (!current || !text || busy) return;
    setBusy(true);
    setMessage("");
    try {
      const view = await transport.sendAgentMessage(current.session_id, text);
      setCurrent(view);
      setDraft("");
    } catch (caught) {
      const status = caught instanceof TransportError ? caught.status : null;
      setMessage(status === 409 ? "No local model is active (activate one on the Models page), or a turn is still running." : "The message could not be sent.");
    } finally {
      setBusy(false);
    }
  }

  async function decide(approved: boolean) {
    if (!current || !pending?.approval_id) return;
    try {
      const view = await transport.decideAgentApproval(current.session_id, pending.approval_id, approved);
      setCurrent(view);
    } catch {
      setMessage("The decision did not reach the agent; it may have moved on.");
    }
  }

  async function stop() {
    if (!current) return;
    try { setCurrent(await transport.stopAgentSession(current.session_id)); } catch { /* ignore */ }
  }

  async function closeSession(id: string) {
    try {
      await transport.deleteAgentSession(id);
      if (current?.session_id === id) { setCurrent(null); setEvents([]); lastSeq.current = 0; }
      await refreshSessions();
    } catch {
      setMessage("The session could not be closed.");
    }
  }

  if (unavailable) {
    return <section className="agent"><p className="agent__note">The local agent is not available in this runtime.</p></section>;
  }

  return (
    <section aria-labelledby="agent-title" className={`agent${windowMode ? " agent--window" : ""}`}>
      <header className="agent__head">
        <div>
          <p className="eyebrow">Agent · a local model working in one folder</p>
          <h1 id="agent-title">{current ? (current.settings.title || current.settings.workspace.split(/[\\/]/).filter(Boolean).pop()) : "Agent workspace"}</h1>
          {!windowMode && (
            <p className="agent__lede">
              Point the active local model at a folder. It reads, searches and proposes; every file write (with a diff), command and web fetch waits for your approval.
              Nothing leaves this machine and nothing is stored beyond the server's memory.
            </p>
          )}
        </div>
        <div className="agent__head-actions">
          {current && !windowMode && <button className="button button--ghost" onClick={() => { openAgentWindow(current.session_id); }} type="button">Open in its own window</button>}
          {current && current.running && <button className="button button--ghost" onClick={() => void stop()} type="button">Stop</button>}
        </div>
      </header>

      <div className={`agent__layout${windowMode ? " agent__layout--window" : ""}`}>
        {!windowMode && (
          <aside className="agent__side">
            <form className="agent__new" onSubmit={(event) => { event.preventDefault(); void createSession(); }}>
              <h2>New session</h2>
              <label>
                <span>Workspace folder (absolute path)</span>
                <input aria-label="Workspace folder" onChange={(e) => setWorkspace(e.currentTarget.value)} placeholder="D:\\projects\\example" type="text" value={workspace} />
              </label>
              <label>
                <span>Model</span>
                <select aria-label="Agent model" onChange={(e) => setModelAlias(e.currentTarget.value)} value={modelAlias}>
                  <option value="">Active model{runningModels.length ? ` (${runningModels[0].record.alias})` : ""}</option>
                  {(models?.models ?? []).map((m) => <option key={m.record.alias} value={m.record.alias}>{m.record.display_name}{m.runtime.state === "running" ? " · running" : ""}</option>)}
                </select>
              </label>
              <details className="agent__parameters">
                <summary>Model parameters</summary>
                <div className="agent__parameters-grid">
                  <label>
                    <span>Temperature · {temperature.toFixed(2)}</span>
                    <input aria-label="Temperature" max={2} min={0} onChange={(e) => setTemperature(Number(e.currentTarget.value))} step={0.05} type="range" value={temperature} />
                  </label>
                  <label>
                    <span>Top-p · {topP.toFixed(2)}</span>
                    <input aria-label="Top-p" max={1} min={0.05} onChange={(e) => setTopP(Number(e.currentTarget.value))} step={0.05} type="range" value={topP} />
                  </label>
                  <label>
                    <span>Max tokens per step</span>
                    <input aria-label="Max tokens" max={8192} min={64} onChange={(e) => setMaxTokens(Math.max(64, Math.min(8192, Number(e.currentTarget.value) || 1400)))} step={1} type="number" value={maxTokens} />
                  </label>
                  <label className="agent__toggle"><input checked={thinking} onChange={(e) => setThinking(e.currentTarget.checked)} type="checkbox" /><span>Thinking mode (models that support it reason before answering; slower)</span></label>
                </div>
                <label>
                  <span>Standing instructions (optional, kept for the whole session)</span>
                  <textarea aria-label="Standing instructions" onChange={(e) => setInstructions(e.currentTarget.value)} placeholder="e.g. Answer in Polish. Keep documents as Markdown in docs/." rows={2} value={instructions} />
                </label>
              </details>
              <label className="agent__toggle"><input checked={allowWrites} onChange={(e) => setAllowWrites(e.currentTarget.checked)} type="checkbox" /><span>May write files (each write needs approval, diff shown)</span></label>
              <label className="agent__toggle"><input checked={allowCommands} onChange={(e) => setAllowCommands(e.currentTarget.checked)} type="checkbox" /><span>May run commands (each command needs approval)</span></label>
              <label className="agent__toggle"><input checked={allowWeb} onChange={(e) => setAllowWeb(e.currentTarget.checked)} type="checkbox" /><span>May fetch web pages (each fetch needs approval)</span></label>
              <button className="button button--primary" disabled={busy || !workspace.trim()} type="submit">Start session</button>
              {message && !current && <p className="agent__error" role="alert">{message}</p>}
            </form>
            <section className="agent__sessions" aria-labelledby="agent-sessions-title">
              <h2 id="agent-sessions-title">Sessions</h2>
              {sessions === null ? <p className="agent__note">Loading…</p> : sessions.length === 0 ? <p className="agent__note">No session yet.</p> : (
                <ul>
                  {sessions.map((s) => (
                    <li key={s.session_id} data-current={s.session_id === current?.session_id ? "true" : undefined}>
                      <button className="agent__session-pick" onClick={() => { setCurrent(s); setEvents([]); lastSeq.current = 0; }} type="button">
                        <strong>{s.settings.title || s.settings.workspace.split(/[\\/]/).filter(Boolean).pop()}</strong>
                        <small>{s.running ? "running" : s.pending_approval_id ? "waiting for you" : `${s.turns} turns`}{s.model_alias ? ` · ${s.model_alias}` : ""}</small>
                      </button>
                      <button aria-label={`Close session ${s.settings.title || s.settings.workspace.split(/[\\/]/).filter(Boolean).pop()}`} className="agent__session-close" onClick={() => { if (window.confirm("Close this session? The conversation is not stored anywhere and cannot be reopened.")) void closeSession(s.session_id); }} title="Close session" type="button">×</button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </aside>
        )}

        <section className="agent__main" aria-label="Agent conversation">
          {!current ? (
            <p className="agent__note">{windowMode ? "This window has no session. Open one from the Agent page." : "Start a session on the left, then ask for something: explore the repo, fix a failing test, draft a document."}</p>
          ) : (
            <>
              <div className="agent__meta">
                <code>{current.settings.workspace}</code>
                <span>
                  {current.model_alias ?? "no model"}
                  {current.settings.parameters ? " · t=" + current.settings.parameters.temperature.toFixed(2) + " · " + String(current.settings.parameters.max_tokens) + " tok" + (current.settings.parameters.enable_thinking ? " · thinking" : "") : ""}
                  {" · "}{current.settings.allow_writes ? "writes" : "no writes"} · {current.settings.allow_commands ? "commands" : "no commands"} · {current.settings.allow_web ? "web" : "no web"}
                </span>
              </div>
              <div className="agent__log" ref={logRef} role="log" aria-live="off">
                {events.map((event) => <EventRow key={event.seq} event={event} />)}
                {current.running && !pending && <p className="agent__thinking">Working…</p>}
              </div>
              {pending && (
                <div className="agent__approval" role="alertdialog" aria-label="Approval needed">
                  <p className="agent__approval-title">
                    <strong>{TOOL_LABELS[pending.tool ?? ""] ?? pending.tool}</strong> wants to {pending.tool === "write_file" ? "write" : pending.tool === "run_command" ? "run" : "fetch"}: <code>{summarizeArguments(pending.tool, pending.arguments as Record<string, unknown> | null)}</code>
                  </p>
                  {pending.preview && <pre className="agent__diff">{pending.preview}</pre>}
                  <div className="agent__approval-actions">
                    <button className="button button--primary" onClick={() => void decide(true)} type="button">Approve</button>
                    <button className="button button--ghost" onClick={() => void decide(false)} type="button">Deny</button>
                  </div>
                </div>
              )}
              <form className="agent__compose" onSubmit={(event) => { event.preventDefault(); void send(); }}>
                <textarea
                  aria-label="Message to the agent"
                  disabled={current.running}
                  onChange={(e) => setDraft(e.currentTarget.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void send(); } }}
                  placeholder={current.running ? "The agent is working…" : "What should the agent do? Ctrl+Enter sends"}
                  rows={3}
                  value={draft}
                />
                <button className="button button--primary" disabled={busy || current.running || !draft.trim()} type="submit">Send</button>
              </form>
            </>
          )}
          {message && <p className="agent__error" role="alert">{message}</p>}
        </section>
      </div>
    </section>
  );
}

function EventRow({ event }: { event: AgentEvent }) {
  if (event.kind === "user") return <article className="agent__turn agent__turn--user"><header>You</header><pre>{event.text}</pre></article>;
  if (event.kind === "assistant") return <article className="agent__turn agent__turn--assistant"><header>Agent</header><pre>{event.text}</pre></article>;
  if (event.kind === "tool_call") {
    return (
      <article className="agent__tool" data-tool={event.tool ?? ""}>
        <span className="agent__tool-name">{TOOL_LABELS[event.tool ?? ""] ?? event.tool}</span>
        <code>{summarizeArguments(event.tool, event.arguments as Record<string, unknown> | null)}</code>
      </article>
    );
  }
  if (event.kind === "tool_result") {
    return (
      <details className="agent__result" data-ok={event.ok ? "true" : "false"}>
        <summary>{event.ok ? "result" : "failed"} · {TOOL_LABELS[event.tool ?? ""] ?? event.tool}</summary>
        <pre>{event.text}</pre>
      </details>
    );
  }
  if (event.kind === "approval_required") return <p className="agent__status">Waiting for your approval: {TOOL_LABELS[event.tool ?? ""] ?? event.tool}</p>;
  if (event.kind === "approval_resolved") return <p className="agent__status">{event.ok ? "Approved" : "Denied"}: {TOOL_LABELS[event.tool ?? ""] ?? event.tool}{event.text ? ` (${event.text})` : ""}</p>;
  if (event.kind === "error") return <p className="agent__error" role="alert">{event.text}</p>;
  if (event.kind === "status") return <p className="agent__status">{event.text}</p>;
  return null;
}
