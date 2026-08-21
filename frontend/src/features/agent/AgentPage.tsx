import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentEvent, AgentEvents, AgentSessionView, AgentSettings, LocalModelsOverview, PromptCheckResult, PromptEnhancerTransport } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { TeamFoldersPanel } from "./TeamFoldersPanel";
import { AgentWorkspacePane } from "./AgentWorkspacePane";
import { AgentPromptCheckResult, agentPromptContext } from "./AgentPromptCheck";
import "./AgentPage.css";

const POLL_MS = 700;
const IDLE_POLL_MS = 4000;
const STREAM_RETRY_MS = 350;
const MAX_STREAM_RETRY_MS = 5600;
const MAX_STREAM_FAILURES = 5;
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
  "listAgentSessions" | "createAgentSession" | "getAgentSession" | "deleteAgentSession" | "sendAgentMessage" | "getAgentEvents" | "decideAgentApproval" | "stopAgentSession" | "getAgentWorkspaceTree" | "getAgentWorkspaceFile" | "previewAgentWorkspaceEdit" | "applyAgentWorkspaceEdit"
> & Partial<Pick<PromptEnhancerTransport, "streamAgentEvents" | "getLocalModels" | "checkPrompt" | "getUserPresenceCapability" | "shareFolder" | "listSharedFolders" | "revokeSharedFolder" | "joinSharedFolder" | "listPeerLinks" | "leavePeerLink" | "pullPeerLink" | "pushPeerLink">>;

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
  const [allowWrites, setAllowWrites] = useState(
    transport.getUserPresenceCapability === undefined,
  );
  const [allowCommands, setAllowCommands] = useState(
    transport.getUserPresenceCapability === undefined,
  );
  const [allowWeb, setAllowWeb] = useState(false);
  const [temperature, setTemperature] = useState(0.2);
  const [topP, setTopP] = useState(0.95);
  const [maxTokens, setMaxTokens] = useState(1400);
  const [thinking, setThinking] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [draft, setDraft] = useState("");
  const [promptCheckBusy, setPromptCheckBusy] = useState(false);
  const [promptCheckError, setPromptCheckError] = useState("");
  const [promptCheckNotice, setPromptCheckNotice] = useState("");
  const [promptCheckResult, setPromptCheckResult] = useState<PromptCheckResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [streamNotice, setStreamNotice] = useState("");
  const [streamRetryNonce, setStreamRetryNonce] = useState(0);
  const [historyGap, setHistoryGap] = useState(false);
  const [workspaceDirty, setWorkspaceDirty] = useState(false);
  const [userPresenceAvailable, setUserPresenceAvailable] = useState(
    transport.getUserPresenceCapability === undefined,
  );
  const lastSeq = useRef(0);
  const logRef = useRef<HTMLDivElement | null>(null);
  const approvalRef = useRef<HTMLDivElement | null>(null);
  const followOutput = useRef(true);
  const promptCheckController = useRef<AbortController | null>(null);

  const clearPromptCheck = useCallback((notice = "") => {
    promptCheckController.current?.abort();
    promptCheckController.current = null;
    setPromptCheckBusy(false);
    setPromptCheckError("");
    setPromptCheckNotice(notice);
    setPromptCheckResult(null);
  }, []);

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
    if (transport.getUserPresenceCapability === undefined) {
      setUserPresenceAvailable(true);
    } else {
      setUserPresenceAvailable(false);
      transport.getUserPresenceCapability(controller.signal)
        .then((value) => {
          if (!controller.signal.aborted) {
            setUserPresenceAvailable(value.confirmation_available);
            if (value.confirmation_available) {
              setAllowWrites(true);
              setAllowCommands(true);
            } else {
              setAllowWrites(false);
              setAllowCommands(false);
              setAllowWeb(false);
            }
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setUserPresenceAvailable(false);
            setAllowWrites(false);
            setAllowCommands(false);
            setAllowWeb(false);
          }
        });
    }
    return () => controller.abort();
  }, [refreshSessions, transport]);

  useEffect(() => () => promptCheckController.current?.abort(), []);

  useEffect(() => {
    clearPromptCheck();
  }, [clearPromptCheck, current?.session_id]);

  // Pick the session from the route, or the newest one.
  useEffect(() => {
    if (!sessions) return;
    const wanted = sessionId ? sessions.find((s) => s.session_id === sessionId) : current ? sessions.find((s) => s.session_id === current.session_id) : sessions[0];
    if (wanted && wanted.session_id !== current?.session_id) {
      setCurrent(wanted);
      setEvents([]);
      setHistoryGap(false);
      setStreamNotice("");
      lastSeq.current = 0;
      followOutput.current = true;
    }
  }, [sessions, sessionId, current]);

  const pending = useMemo(() => {
    if (!current?.pending_approval_id) return null;
    return [...events].reverse().find((event) => event.kind === "approval_required" && event.approval_id === current.pending_approval_id) ?? null;
  }, [events, current?.pending_approval_id]);

  useEffect(() => {
    if (pending) approvalRef.current?.focus();
  }, [pending]);

  // Prefer the private SSE event stream; retain polling for older/test transports.
  useEffect(() => {
    if (!current) return;
    let cancelled = false;
    const controller = new AbortController();
    let handle = 0;
    let streamFailures = 0;
    const acceptPage = (page: AgentEvents): boolean => {
      if (cancelled || page.session_id !== current.session_id) return false;
      streamFailures = 0;
      setStreamNotice("");
      const cursor = lastSeq.current;
      if (page.first_seq > cursor + 1) setHistoryGap(true);
      const fresh = page.events.filter((event) => event.seq > cursor);
      if (fresh.length > 0) {
        setEvents((previous) => {
          const priorSeq = previous.length > 0 ? previous[previous.length - 1].seq : 0;
          return compactTerminalDeltas([...previous, ...fresh.filter((event) => event.seq > priorSeq)]);
        });
        lastSeq.current = fresh[fresh.length - 1].seq;
      }
      setCurrent((previous) => previous && previous.session_id === page.session_id
        ? { ...previous, running: page.running, pending_approval_id: page.pending_approval_id ?? null, last_seq: page.last_seq }
        : previous);
      return page.running || Boolean(page.pending_approval_id) || fresh.length > 0;
    };

    if (transport.streamAgentEvents) {
      let streamActive = current.running;
      const connect = async () => {
        try {
          await transport.streamAgentEvents?.(
            current.session_id,
            lastSeq.current,
            (page) => { streamActive = acceptPage(page); },
            controller.signal,
          );
        } catch {
          if (!controller.signal.aborted) {
            streamFailures += 1;
            if (streamFailures >= 3) setStreamNotice("Live updates were interrupted; reconnecting on this machine…");
          }
        }
        if (cancelled) return;
        if (streamFailures >= MAX_STREAM_FAILURES) {
          setStreamNotice("Live updates paused after repeated connection failures. Retry when the local service is available.");
          return;
        }
        const delay = streamFailures > 0
          ? Math.min(STREAM_RETRY_MS * (2 ** (streamFailures - 1)), MAX_STREAM_RETRY_MS)
          : streamActive ? STREAM_RETRY_MS : IDLE_POLL_MS;
        handle = window.setTimeout(() => { void connect(); }, delay);
      };
      void connect();
    } else {
      const tick = async (): Promise<boolean> => {
        try {
          return acceptPage(await transport.getAgentEvents(current.session_id, lastSeq.current, controller.signal));
        } catch {
          return true;
        }
      };
      const schedule = (active: boolean) => {
        if (cancelled) return;
        handle = window.setTimeout(async () => {
          schedule(await tick());
        }, active ? POLL_MS : IDLE_POLL_MS);
      };
      void tick().then(schedule);
    }
    return () => { cancelled = true; controller.abort(); window.clearTimeout(handle); };
  }, [current?.session_id, current?.running, streamRetryNonce, transport]);

  useEffect(() => {
    const node = logRef.current;
    if (node && followOutput.current) node.scrollTop = node.scrollHeight;
  }, [events]);

  const runningModels = useMemo(() => (models?.models ?? []).filter((m) => m.runtime.state === "running"), [models]);
  const liveStreams = useMemo(() => coalesceLiveStreams(events), [events]);
  const handleWorkspaceDirty = useCallback((value: boolean) => setWorkspaceDirty(value), []);

  function mayLeaveWorkspace(): boolean {
    return !workspaceDirty || window.confirm("Discard the unsaved manual workspace edit?");
  }

  async function createSession() {
    const path = workspace.trim();
    if (!path) return;
    if (!mayLeaveWorkspace()) return;
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
      setHistoryGap(false);
      setStreamNotice("");
      lastSeq.current = 0;
      followOutput.current = true;
    } catch (caught) {
      const status = caught instanceof TransportError ? caught.status : null;
      setMessage(status === 422 ? "That is not an existing folder (use an absolute path, not a drive root)." : status === 403 ? "That folder is outside the allowed roots." : status === 409 ? "Too many open sessions - close one first." : "The session could not be created.");
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    const text = draft.trim();
    if (!current || !text || busy || promptCheckBusy) return;
    setBusy(true);
    setMessage("");
    followOutput.current = true;
    try {
      const view = await transport.sendAgentMessage(current.session_id, text);
      setCurrent(view);
      setDraft("");
      clearPromptCheck();
    } catch (caught) {
      const status = caught instanceof TransportError ? caught.status : null;
      setMessage(status === 409 ? "No local model is active (activate one on the Models page), or a turn is still running." : "The message could not be sent.");
    } finally {
      setBusy(false);
    }
  }

  function changeDraft(value: string) {
    clearPromptCheck();
    setDraft(value);
  }

  async function runPromptCheck() {
    const text = draft.trim();
    const checkPrompt = transport.checkPrompt;
    if (!current || !checkPrompt || !text || busy || promptCheckBusy || current.running) return;

    const controller = new AbortController();
    promptCheckController.current?.abort();
    promptCheckController.current = controller;
    setPromptCheckBusy(true);
    setPromptCheckError("");
    setPromptCheckNotice("");
    setPromptCheckResult(null);

    try {
      const result = await checkPrompt({
        prompt: text,
        prior_messages: agentPromptContext(events),
        session_id: null,
        provider: "other",
        agent_model: current.model_alias,
        want_commentary: true,
      }, controller.signal);
      if (!controller.signal.aborted) setPromptCheckResult(result);
    } catch (caught) {
      if (controller.signal.aborted) return;
      const status = caught instanceof TransportError ? caught.status : null;
      setPromptCheckError(status === 404
        ? "Prompt Check is not available in this runtime. Your draft was not changed."
        : status === 422
          ? "The draft or available conversation context exceeded the local check limits."
          : "The prompt check did not run. Your draft was not changed.");
    } finally {
      if (promptCheckController.current === controller) {
        promptCheckController.current = null;
        setPromptCheckBusy(false);
      }
    }
  }

  function usePromptRewrite(value: string) {
    if (!value.trim()) return;
    setDraft(value);
    clearPromptCheck("Suggested prompt applied. Check it again to validate the revised draft before sending.");
  }

  async function decide(approved: boolean) {
    if (!current || !pending?.approval_id || !userPresenceAvailable) return;
    try {
      const view = await transport.decideAgentApproval(current.session_id, pending.approval_id, approved);
      setCurrent(view);
    } catch (caught) {
      const status = caught instanceof TransportError ? caught.status : null;
      setMessage(status === 503
        ? "Native user-presence confirmation is unavailable in this app composition. The agent action remains pending."
        : status === 403
          ? "The native confirmation was declined or expired. The agent action remains pending."
          : "The decision did not reach the agent; refresh before deciding again.");
    }
  }

  async function stop() {
    if (!current) return;
    try { setCurrent(await transport.stopAgentSession(current.session_id)); } catch { /* ignore */ }
  }

  async function closeSession(id: string) {
    if (current?.session_id === id && !mayLeaveWorkspace()) return;
    try {
      await transport.deleteAgentSession(id);
      if (current?.session_id === id) { setCurrent(null); setEvents([]); setHistoryGap(false); setStreamNotice(""); lastSeq.current = 0; }
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
              <label className="agent__toggle"><input checked={allowWrites} disabled={!userPresenceAvailable} onChange={(e) => setAllowWrites(e.currentTarget.checked)} type="checkbox" /><span>May write files (each write needs approval, diff shown)</span></label>
              <label className="agent__toggle"><input checked={allowCommands} disabled={!userPresenceAvailable} onChange={(e) => setAllowCommands(e.currentTarget.checked)} type="checkbox" /><span>May run commands (each command needs approval)</span></label>
              <label className="agent__toggle"><input checked={allowWeb} disabled={!userPresenceAvailable} onChange={(e) => setAllowWeb(e.currentTarget.checked)} type="checkbox" /><span>May fetch web pages (each fetch needs approval)</span></label>
              {!userPresenceAvailable && <p className="agent__note">Native confirmation is unavailable in this server/window composition. New sessions stay read-only; protected actions cannot be approved here.</p>}
              <button className="button button--primary" disabled={busy || !workspace.trim()} type="submit">Start session</button>
              {message && !current && <p className="agent__error" role="alert">{message}</p>}
            </form>
            <section className="agent__sessions" aria-labelledby="agent-sessions-title">
              <h2 id="agent-sessions-title">Sessions</h2>
              {sessions === null ? <p className="agent__note">Loading…</p> : sessions.length === 0 ? <p className="agent__note">No session yet.</p> : (
                <ul>
                  {sessions.map((s) => (
                    <li key={s.session_id} data-current={s.session_id === current?.session_id ? "true" : undefined}>
                      <button className="agent__session-pick" onClick={() => { if (mayLeaveWorkspace()) { setCurrent(s); setEvents([]); setHistoryGap(false); setStreamNotice(""); lastSeq.current = 0; } }} type="button">
                        <strong>{s.settings.title || s.settings.workspace.split(/[\\/]/).filter(Boolean).pop()}</strong>
                        <small>{s.running ? "running" : s.pending_approval_id ? "waiting for you" : `${s.turns} turns`}{s.model_alias ? ` · ${s.model_alias}` : ""}</small>
                      </button>
                      <button aria-label={`Close session ${s.settings.title || s.settings.workspace.split(/[\\/]/).filter(Boolean).pop()}`} className="agent__session-close" onClick={() => { if (window.confirm("Close this session? The conversation and any unsaved manual edit are not stored and cannot be reopened.")) void closeSession(s.session_id); }} title="Close session" type="button">×</button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <TeamFoldersPanel onUseAsWorkspace={(path) => setWorkspace(path)} transport={transport} />
          </aside>
        )}

        <div className="agent__workbench" data-has-workspace={current ? "true" : "false"}>
          {current && (
            <AgentWorkspacePane
              key={current.session_id}
              onDirtyChange={handleWorkspaceDirty}
              pendingWrite={pending}
              userPresenceAvailable={userPresenceAvailable}
              sessionId={current.session_id}
              transport={transport}
            />
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
              <p className="sr-only" aria-live="polite">
                {pending
                  ? `Approval needed for ${TOOL_LABELS[pending.tool ?? ""] ?? pending.tool ?? "an agent action"}.`
                  : liveStreams.size > 0 ? "Agent response is streaming." : current.running ? "Agent is working." : ""}
              </p>
              <div
                className="agent__log"
                ref={logRef}
                role="log"
                aria-live="off"
                onScroll={(event) => {
                  const node = event.currentTarget;
                  followOutput.current = node.scrollHeight - node.scrollTop - node.clientHeight < 64;
                }}
              >
                {historyGap && <p className="agent__status" role="status">Earlier in-memory events expired; completed replies below remain authoritative.</p>}
                {events.map((event) => {
                  if (event.kind !== "assistant_delta") return <EventRow key={event.seq} event={event} />;
                  if (!event.stream_id) return null;
                  const live = liveStreams.get(event.stream_id);
                  return live && live.firstSeq === event.seq
                    ? <LiveAssistant key={event.stream_id} content={live.content} reasoning={live.reasoning} />
                    : null;
                })}
                {current.running && !pending && liveStreams.size === 0 && <p className="agent__thinking">Working…</p>}
              </div>
              {streamNotice && (
                <div className="agent__status">
                  <span role="status">{streamNotice}</span>{" "}
                  <button
                    className="button button--ghost"
                    onClick={() => {
                      setStreamNotice("");
                      setStreamRetryNonce((value) => value + 1);
                    }}
                    type="button"
                  >
                    Retry live updates
                  </button>
                </div>
              )}
              {pending && (
                <div
                  aria-label="Approval needed"
                  aria-modal="true"
                  className="agent__approval"
                  ref={approvalRef}
                  role="alertdialog"
                  tabIndex={-1}
                >
                  <p className="agent__approval-title">
                    <strong>{TOOL_LABELS[pending.tool ?? ""] ?? pending.tool}</strong> wants to {pending.tool === "write_file" ? "write" : pending.tool === "run_command" ? "run" : "fetch"}: <code>{summarizeArguments(pending.tool, pending.arguments as Record<string, unknown> | null)}</code>
                  </p>
                  {pending.preview && <pre className="agent__diff">{pending.preview}</pre>}
                  {!userPresenceAvailable && <p className="agent__note">This pending action cannot be decided until the app is opened in a native-confirmation composition.</p>}
                  <div className="agent__approval-actions">
                    <button className="button button--primary" disabled={!userPresenceAvailable} onClick={() => void decide(true)} type="button">Approve</button>
                    <button className="button button--ghost" disabled={!userPresenceAvailable} onClick={() => void decide(false)} type="button">Deny</button>
                  </div>
                </div>
              )}
              <form className="agent__compose" onSubmit={(event) => { event.preventDefault(); void send(); }}>
                <textarea
                  aria-label="Message to the agent"
                  disabled={current.running}
                  onChange={(e) => changeDraft(e.currentTarget.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void send(); } }}
                  placeholder={current.running ? "The agent is working…" : "What should the agent do? Ctrl+Enter sends"}
                  rows={3}
                  value={draft}
                />
                <div className="agent__compose-actions">
                  {transport.checkPrompt && (
                    <button
                      aria-expanded={Boolean(promptCheckResult)}
                      className="button button--ghost"
                      disabled={busy || promptCheckBusy || current.running || !draft.trim()}
                      onClick={() => void runPromptCheck()}
                      type="button"
                    >
                      {promptCheckBusy ? "Checking…" : "Check & improve"}
                    </button>
                  )}
                  <button className="button button--primary" disabled={busy || promptCheckBusy || current.running || !draft.trim()} type="submit">Send</button>
                </div>
                <div aria-live="polite" className="agent__prompt-check-status">
                  {promptCheckError && <p className="agent__error" role="alert">{promptCheckError}</p>}
                  {promptCheckNotice && <p className="agent__status">{promptCheckNotice}</p>}
                </div>
                {promptCheckResult && <AgentPromptCheckResult onUseRewrite={usePromptRewrite} result={promptCheckResult} />}
              </form>
            </>
          )}
          {message && <p className="agent__error" role="alert">{message}</p>}
          </section>
        </div>
      </div>
    </section>
  );
}

type LiveStreamView = { firstSeq: number; content: string; reasoning: string };

function compactTerminalDeltas(events: AgentEvent[]): AgentEvent[] {
  const terminalIds = new Set(
    events
      .filter((event) => event.kind === "assistant" && event.stream_id)
      .map((event) => event.stream_id as string),
  );
  return events.filter((event) => event.kind !== "assistant_delta" || !event.stream_id || !terminalIds.has(event.stream_id));
}

function coalesceLiveStreams(events: AgentEvent[]): Map<string, LiveStreamView> {
  const terminalIds = new Set(
    events
      .filter((event) => event.kind === "assistant" && event.stream_id)
      .map((event) => event.stream_id as string),
  );
  const live = new Map<string, LiveStreamView>();
  for (const event of events) {
    if (event.kind !== "assistant_delta" || !event.stream_id || terminalIds.has(event.stream_id) || !event.text) continue;
    const current = live.get(event.stream_id) ?? { firstSeq: event.seq, content: "", reasoning: "" };
    if (event.stream_phase === "reasoning") current.reasoning += event.text;
    else current.content += event.text;
    live.set(event.stream_id, current);
  }
  return live;
}

function LiveAssistant({ content, reasoning }: { content: string; reasoning: string }) {
  return (
    <article className="agent__turn agent__turn--assistant agent__turn--live" aria-label="Agent response streaming">
      <header>Agent · streaming</header>
      {reasoning && <details className="agent__reasoning" open><summary>Model reasoning · thinking mode</summary><pre>{reasoning}</pre></details>}
      {content && <pre>{content}</pre>}
    </article>
  );
}

function EventRow({ event }: { event: AgentEvent }) {
  if (event.kind === "user") return <article className="agent__turn agent__turn--user"><header>You</header><pre>{event.text}</pre></article>;
  if (event.kind === "assistant") {
    const suffix = event.stream_status === "stopped" ? " · stopped" : event.stream_status === "failed" ? " · interrupted" : "";
    return (
      <article className="agent__turn agent__turn--assistant" data-stream-status={event.stream_status ?? "whole"}>
        <header>Agent{suffix}</header>
        {event.reasoning && <details className="agent__reasoning"><summary>Model reasoning · thinking mode</summary><pre>{event.reasoning}</pre></details>}
        {event.text ? <pre>{event.text}</pre> : !event.reasoning ? <p className="agent__status">No assistant text was completed.</p> : null}
      </article>
    );
  }
  if (event.kind === "assistant_delta") return null;
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
