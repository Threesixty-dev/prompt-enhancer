import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentEvent, AgentEvents, AgentSessionView, AgentSettings, LocalModelStatus, LocalModelsOverview, PromptCheckResult, PromptEnhancerTransport } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import {
  chooseNativeWorkspaceFolder,
  hasNativeWorkspaceFolderPicker,
} from "../../shared/platform/nativeDesktopBridge";
import type { LocalRuntimeTransport } from "../../shared/platform/runtimeMode";
import { TeamFoldersPanel } from "./TeamFoldersPanel";
import { AgentWorkspacePane } from "./AgentWorkspacePane";
import { AgentPromptCheckResult, agentPromptContext } from "./AgentPromptCheck";
import "./AgentPage.css";

const POLL_MS = 700;
const IDLE_POLL_MS = 4000;
const STREAM_RETRY_MS = 350;
const MAX_STREAM_RETRY_MS = 5600;
const MAX_STREAM_FAILURES = 5;
const MODEL_START_POLL_MS = 1500;
const MAX_MODEL_START_POLLS = 20;
const CONNECTION_POLL_MS = 3000;
type UserPresenceState = "checking" | "available" | "unavailable" | "error";
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
> & Partial<Pick<PromptEnhancerTransport, "streamAgentEvents" | "getLocalModels" | "activateLocalModel" | "deactivateLocalModel" | "checkPrompt" | "getUserPresenceCapability" | "shareFolder" | "listSharedFolders" | "revokeSharedFolder" | "joinSharedFolder" | "listPeerLinks" | "leavePeerLink" | "pullPeerLink" | "pushPeerLink">>
  & Partial<Pick<LocalRuntimeTransport, "getRuntimeHealth">>;

type ModelCatalogState = "unavailable" | "loading" | "ready" | "error";
type ModelFeedbackTarget = "selection" | "session";
type ModelActionKind = "start" | "stop" | null;
type SessionLookupState = "idle" | "loading" | "missing" | "error";
type ConnectionState = "unverified" | "checking" | "connected" | "disconnected";

function runtimeStateLabel(state: LocalModelStatus["runtime"]["state"]): string {
  return state === "running" ? "running" : state === "starting" ? "starting" : state === "failed" ? "failed" : "stopped";
}

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
  const [connectionState, setConnectionState] = useState<ConnectionState>(
    transport.getRuntimeHealth === undefined ? "unverified" : "checking",
  );
  const [current, setCurrent] = useState<AgentSessionView | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [models, setModels] = useState<LocalModelsOverview | null>(null);
  const [modelCatalogState, setModelCatalogState] = useState<ModelCatalogState>(
    transport.getLocalModels === undefined ? "unavailable" : "loading",
  );
  const [modelActionAlias, setModelActionAlias] = useState("");
  const [modelActionKind, setModelActionKind] = useState<ModelActionKind>(null);
  const [modelRefreshBusy, setModelRefreshBusy] = useState(false);
  const [modelFeedbackTarget, setModelFeedbackTarget] = useState<ModelFeedbackTarget>("selection");
  const [modelNotice, setModelNotice] = useState("");
  const [modelError, setModelError] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [folderPickerAvailable, setFolderPickerAvailable] = useState(
    hasNativeWorkspaceFolderPicker,
  );
  const [folderPickerBusy, setFolderPickerBusy] = useState(false);
  const [folderPickerNotice, setFolderPickerNotice] = useState("");
  const [modelAlias, setModelAlias] = useState("");
  const [allowWrites, setAllowWrites] = useState(false);
  const [allowCommands, setAllowCommands] = useState(false);
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
  const [creatingSession, setCreatingSession] = useState(false);
  const [createMessage, setCreateMessage] = useState("");
  const [conversationMessage, setConversationMessage] = useState("");
  const [sessionLookupState, setSessionLookupState] = useState<SessionLookupState>(sessionId ? "loading" : "idle");
  const [streamNotice, setStreamNotice] = useState("");
  const [streamRetryNonce, setStreamRetryNonce] = useState(0);
  const [composerFocusNonce, setComposerFocusNonce] = useState(0);
  const [historyGap, setHistoryGap] = useState(false);
  const [workspaceDirty, setWorkspaceDirty] = useState(false);
  const [userPresenceState, setUserPresenceState] = useState<UserPresenceState>(
    transport.getUserPresenceCapability === undefined ? "unavailable" : "checking",
  );
  const [userPresenceRetryNonce, setUserPresenceRetryNonce] = useState(0);
  const lastSeq = useRef(0);
  const logRef = useRef<HTMLDivElement | null>(null);
  const approvalRef = useRef<HTMLDivElement | null>(null);
  const workspaceInputRef = useRef<HTMLInputElement | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);
  const modelStartPolls = useRef(0);
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
      else setSessions((previous) => previous ?? []);
    }
  }, [transport]);

  const refreshModels = useCallback(async (signal?: AbortSignal): Promise<LocalModelsOverview | null> => {
    const getLocalModels = transport.getLocalModels;
    if (getLocalModels === undefined) {
      setModelCatalogState("unavailable");
      return null;
    }
    try {
      const value = await getLocalModels(signal);
      if (signal?.aborted) return null;
      setModels(value);
      setModelCatalogState("ready");
      return value;
    } catch {
      if (signal?.aborted) return null;
      setModelCatalogState("error");
      return null;
    }
  }, [transport]);

  useEffect(() => {
    const controller = new AbortController();
    void refreshSessions(controller.signal);
    void refreshModels(controller.signal);
    return () => controller.abort();
  }, [refreshModels, refreshSessions]);

  useEffect(() => {
    const getRuntimeHealth = transport.getRuntimeHealth;
    if (getRuntimeHealth === undefined) {
      setConnectionState("unverified");
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    let handle = 0;
    let wasDisconnected = false;

    const check = async () => {
      try {
        await getRuntimeHealth(controller.signal);
        if (cancelled) return;
        const recovered = wasDisconnected;
        wasDisconnected = false;
        setConnectionState("connected");
        if (recovered) {
          void refreshSessions();
          void refreshModels();
        }
      } catch {
        if (cancelled || controller.signal.aborted) return;
        wasDisconnected = true;
        setConnectionState("disconnected");
      }
      if (!cancelled) handle = window.setTimeout(() => { void check(); }, CONNECTION_POLL_MS);
    };

    void check();
    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(handle);
    };
  }, [refreshModels, refreshSessions, transport.getRuntimeHealth]);

  useEffect(() => {
    if (transport.getLocalModels === undefined) return;
    const handleFocus = () => { void refreshModels(); };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [refreshModels, transport.getLocalModels]);

  useEffect(() => {
    const hasStartingModel = modelCatalogState === "ready"
      && (models?.models ?? []).some((model) => model.runtime.state === "starting");
    if (!hasStartingModel) {
      modelStartPolls.current = 0;
      return;
    }
    if (modelStartPolls.current >= MAX_MODEL_START_POLLS) return;
    const handle = window.setTimeout(() => {
      modelStartPolls.current += 1;
      void refreshModels();
    }, MODEL_START_POLL_MS);
    return () => window.clearTimeout(handle);
  }, [modelCatalogState, models, refreshModels]);

  useEffect(() => {
    const getCapability = transport.getUserPresenceCapability;
    if (getCapability === undefined) {
      setUserPresenceState("unavailable");
      setAllowWrites(false);
      setAllowCommands(false);
      setAllowWeb(false);
      return;
    }
    const controller = new AbortController();
    setUserPresenceState("checking");
    getCapability(controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        const available = value.contract_version === "native-user-presence-capability-v1"
          && value.confirmation_available === true
          && value.mode === "native_bridge_bound_token";
        setUserPresenceState(available ? "available" : "unavailable");
        if (!available) {
          setAllowWrites(false);
          setAllowCommands(false);
          setAllowWeb(false);
        }
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setUserPresenceState("error");
        setAllowWrites(false);
        setAllowCommands(false);
        setAllowWeb(false);
      });
    return () => controller.abort();
  }, [transport, userPresenceRetryNonce]);

  useEffect(() => {
    const handleNativeBridgeReady = () => {
      setFolderPickerAvailable(hasNativeWorkspaceFolderPicker());
      setUserPresenceRetryNonce((value) => value + 1);
    };
    window.addEventListener("pywebviewready", handleNativeBridgeReady);
    // Close the render/effect registration race without polling.
    setFolderPickerAvailable(hasNativeWorkspaceFolderPicker());
    return () => window.removeEventListener("pywebviewready", handleNativeBridgeReady);
  }, []);

  const userPresenceAvailable = userPresenceState === "available";

  useEffect(() => () => promptCheckController.current?.abort(), []);

  useEffect(() => {
    clearPromptCheck();
    setConversationMessage("");
  }, [clearPromptCheck, current?.session_id]);

  useEffect(() => {
    if (!current || composerFocusNonce === 0) return;
    const composer = composerInputRef.current;
    composer?.scrollIntoView?.({ block: "nearest" });
    composer?.focus({ preventScroll: true });
  }, [composerFocusNonce, current?.session_id]);

  // Pick the session from the route, or the newest one.
  useEffect(() => {
    if (!sessions) return;
    const currentFromList = current ? sessions.find((s) => s.session_id === current.session_id) : undefined;
    const wanted = sessionId
      ? sessions.find((s) => s.session_id === sessionId)
      : currentFromList ?? sessions[0];
    if (wanted && wanted.session_id !== current?.session_id) {
      setCurrent(wanted);
      setEvents([]);
      setHistoryGap(false);
      setStreamNotice("");
      lastSeq.current = 0;
      followOutput.current = true;
    }
    if (!wanted && !sessionId && current) {
      setCurrent(null);
      setEvents([]);
      setHistoryGap(false);
      setStreamNotice("");
      lastSeq.current = 0;
      followOutput.current = true;
    }
    if (wanted) setSessionLookupState("idle");
  }, [sessions, sessionId, current]);

  // A dedicated Agent window addresses one session directly. If the session
  // list is stale or bounded, resolve that route explicitly and report why it
  // cannot be restored instead of rendering an unexplained empty card.
  useEffect(() => {
    if (!sessionId) {
      setSessionLookupState("idle");
      return;
    }
    if (sessions === null) {
      setSessionLookupState("loading");
      return;
    }
    if (sessions.some((session) => session.session_id === sessionId)) return;

    const controller = new AbortController();
    setSessionLookupState("loading");
    void Promise.resolve(transport.getAgentSession(sessionId, controller.signal))
      .then((view) => {
        if (controller.signal.aborted) return;
        if (!view || view.session_id !== sessionId) {
          setCurrent(null);
          setSessionLookupState("missing");
          return;
        }
        setCurrent(view);
        setEvents([]);
        setHistoryGap(false);
        setStreamNotice("");
        lastSeq.current = 0;
        followOutput.current = true;
        setSessionLookupState("idle");
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        const missing = caught instanceof TransportError && caught.status === 404;
        if (missing) setCurrent(null);
        setSessionLookupState(missing ? "missing" : "error");
      });
    return () => controller.abort();
  }, [sessionId, sessions, transport]);

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
        if (fresh.some((event) => event.kind === "error")) void refreshModels();
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
  }, [current?.session_id, current?.running, refreshModels, streamRetryNonce, transport]);

  useEffect(() => {
    const node = logRef.current;
    if (node && followOutput.current) node.scrollTop = node.scrollHeight;
  }, [events]);

  const runningModels = useMemo(() => (models?.models ?? []).filter((m) => m.runtime.state === "running"), [models]);
  const selectedModel = useMemo(
    () => modelAlias
      ? (models?.models ?? []).find((model) => model.record.alias === modelAlias) ?? null
      : runningModels[0] ?? null,
    [modelAlias, models, runningModels],
  );
  const currentModelAlias = current?.model_alias ?? current?.settings.model_alias ?? null;
  const currentModel = useMemo(() => {
    if (!current) return null;
    return currentModelAlias
      ? (models?.models ?? []).find((model) => model.record.alias === currentModelAlias) ?? null
      : runningModels[0] ?? null;
  }, [current, currentModelAlias, models, runningModels]);
  const connectionDisconnected = connectionState === "disconnected";
  const selectedModelBlocked = connectionDisconnected || modelCatalogState === "loading"
    || (modelCatalogState === "ready" && selectedModel?.runtime.state !== "running");
  const currentModelBlocked = connectionDisconnected || modelCatalogState === "loading"
    || (modelCatalogState === "ready" && currentModel?.runtime.state !== "running");
  const liveStreams = useMemo(() => coalesceLiveStreams(events), [events]);
  const reasoningEnabled = current?.settings.parameters.enable_thinking ?? false;
  const hasLiveReasoning = [...liveStreams.values()].some((stream) => Boolean(stream.reasoning));
  const hasVisibleReasoning = events.some((event) => Boolean(event.reasoning)) || hasLiveReasoning;
  const toolCallCount = events.filter((event) => event.kind === "tool_call").length;
  const lastActivity = [...events].reverse().find((event) => event.kind !== "done" && event.kind !== "assistant_delta");
  const activityState = pending
    ? { detail: "A protected action needs your decision.", label: "Approval needed", tone: "attention" }
    : current?.running
      ? hasLiveReasoning
        ? { detail: "The model reasoning stream is visible below.", label: "Reasoning", tone: "working" }
        : liveStreams.size > 0
          ? { detail: "The response is streaming below.", label: "Responding", tone: "working" }
          : { detail: "Waiting for the next model or tool event.", label: "Working", tone: "working" }
      : modelCatalogState === "loading"
        ? { detail: "Verifying the exact session model runtime.", label: "Checking model", tone: "paused" }
        : modelCatalogState === "error" || modelCatalogState === "unavailable"
          ? { detail: "The model will be verified again before the next turn.", label: "Model unverified", tone: "attention" }
          : currentModelBlocked
            ? { detail: "Start the session model to continue.", label: "Model stopped", tone: "paused" }
            : lastActivity?.kind === "error"
              ? { detail: "The last run needs attention before retrying.", label: "Needs attention", tone: "error" }
              : { detail: "Ready for your next request.", label: "Ready", tone: "ready" };
  const handleWorkspaceDirty = useCallback((value: boolean) => setWorkspaceDirty(value), []);

  useEffect(() => {
    if (!windowMode || !current || current.running || currentModelBlocked) return;
    const composer = composerInputRef.current;
    composer?.scrollIntoView?.({ block: "nearest" });
    composer?.focus({ preventScroll: true });
  }, [current?.session_id, current?.running, currentModelBlocked, windowMode]);

  function mayLeaveWorkspace(): boolean {
    return !workspaceDirty || window.confirm("Discard the unsaved manual workspace edit?");
  }

  function changeWorkspace(value: string): void {
    setWorkspace(value);
    setWorkspaceError("");
    setFolderPickerNotice("");
  }

  async function browseForWorkspace(): Promise<void> {
    if (folderPickerBusy || !folderPickerAvailable) return;
    setFolderPickerBusy(true);
    setWorkspaceError("");
    setFolderPickerNotice("");
    try {
      const selected = await chooseNativeWorkspaceFolder();
      if (selected.status === "selected") {
        setWorkspace(selected.path);
        setFolderPickerNotice("Workspace folder selected.");
      } else if (selected.status === "cancelled") {
        setFolderPickerNotice("Folder selection cancelled. The workspace path was not changed.");
      } else {
        setFolderPickerAvailable(false);
        setFolderPickerNotice("Native folder selection is unavailable here. Enter or paste an absolute path.");
      }
    } catch {
      setWorkspaceError("The native folder picker did not return a valid folder. Enter or paste an absolute path.");
      workspaceInputRef.current?.focus();
    } finally {
      setFolderPickerBusy(false);
    }
  }

  async function activateModel(alias: string, target: ModelFeedbackTarget): Promise<void> {
    const activate = transport.activateLocalModel;
    if (!activate || !alias || modelActionAlias) return;
    setModelActionAlias(alias);
    setModelActionKind("start");
    setModelFeedbackTarget(target);
    setModelError("");
    setModelNotice("");
    try {
      const status = await activate(alias, {
        remember: true,
        fast_attention: true,
        tool_calling: true,
      });
      if (status.record.alias !== alias || status.runtime.state !== "running") {
        throw new Error("model_activation_incomplete");
      }
      setModels((previous) => previous === null ? previous : {
        ...previous,
        models: previous.models.map((model) => model.record.alias === alias ? status : model),
      });
      setModelCatalogState("ready");
      setModelNotice(`${status.record.display_name} is running and ready for the agent.`);
      setCreateMessage("");
      setConversationMessage("");
    } catch {
      setModelError("The model could not be started. Review its runtime settings on the Models page, then retry.");
    } finally {
      setModelActionAlias("");
      setModelActionKind(null);
    }
  }

  async function deactivateModel(alias: string, target: ModelFeedbackTarget): Promise<void> {
    const deactivate = transport.deactivateLocalModel;
    if (!deactivate || !alias || modelActionAlias) return;
    if (target === "session" && current?.running) {
      setModelFeedbackTarget("session");
      setModelError("Stop the active response before stopping its model.");
      return;
    }
    setModelActionAlias(alias);
    setModelActionKind("stop");
    setModelFeedbackTarget(target);
    setModelError("");
    setModelNotice("");
    try {
      const openSessions = await transport.listAgentSessions();
      setSessions(openSessions);
      const modelHasActiveTurn = openSessions.some((session) => (
        session.model_alias ?? session.settings.model_alias
      ) === alias && session.running);
      if (modelHasActiveTurn) {
        setModelError("Stop every active response using this model before stopping its shared runtime.");
        return;
      }
      const status = await deactivate(alias);
      if (status.record.alias !== alias || status.runtime.state !== "stopped") {
        throw new Error("model_deactivation_incomplete");
      }
      setModels((previous) => previous === null ? previous : {
        ...previous,
        models: previous.models.map((model) => model.record.alias === alias ? status : model),
      });
      setModelCatalogState("ready");
      setModelNotice(`${status.record.display_name} stopped. Sessions using it remain open but cannot send until it is restarted.`);
      setCreateMessage("");
      setConversationMessage("");
    } catch {
      setModelError("The model could not be stopped. Review its runtime on the Models page, then retry.");
    } finally {
      setModelActionAlias("");
      setModelActionKind(null);
    }
  }

  async function refreshModelStatus(target: ModelFeedbackTarget): Promise<void> {
    if (modelRefreshBusy || transport.getLocalModels === undefined) return;
    setModelRefreshBusy(true);
    setModelFeedbackTarget(target);
    setModelError("");
    setModelNotice("");
    try {
      const overview = await refreshModels();
      if (overview === null) {
        setModelError("Model status could not be refreshed. Check the Models page or retry here.");
      }
    } finally {
      setModelRefreshBusy(false);
    }
  }

  async function createSession() {
    const path = workspace.trim();
    if (!path || busy || creatingSession || userPresenceState === "checking" || selectedModelBlocked) return;
    if (!mayLeaveWorkspace()) return;
    setBusy(true);
    setCreatingSession(true);
    setCreateMessage("");
    setModelFeedbackTarget("selection");
    setModelError("");
    setWorkspaceError("");
    try {
      const protectedActionsAvailable = userPresenceState === "available";
      const settings: AgentSettings = {
        workspace: path,
        model_alias: modelAlias || selectedModel?.record.alias || null,
        parameters: { temperature, top_p: topP, max_tokens: maxTokens, enable_thinking: thinking },
        instructions: instructions.trim() || null,
        allow_writes: protectedActionsAvailable && allowWrites,
        allow_commands: protectedActionsAvailable && allowCommands,
        allow_web: protectedActionsAvailable && allowWeb,
        max_steps: 10,
        command_timeout_seconds: 120,
      };
      const created = await transport.createAgentSession(settings);
      await refreshSessions();
      setCurrent(created);
      setComposerFocusNonce((value) => value + 1);
      setEvents([]);
      setHistoryGap(false);
      setStreamNotice("");
      lastSeq.current = 0;
      followOutput.current = true;
    } catch (caught) {
      const status = caught instanceof TransportError ? caught.status : null;
      const reason = caught instanceof TransportError ? caught.reasonCode : null;
      if (caught instanceof TypeError && transport.getRuntimeHealth !== undefined) {
        setConnectionState("disconnected");
        setCreateMessage("The local app disconnected before the session could start. Reopen the protected Agent window; this page will reconnect automatically.");
      } else if (status === 422 || status === 403) {
        setWorkspaceError(status === 422
          ? "That is not an existing folder. Use an absolute path, not a drive root."
          : "That folder is outside the allowed workspace roots.");
        workspaceInputRef.current?.focus();
      } else if (reason === "model_not_ready" || reason === "no_active_model") {
        void refreshModels();
        setModelError(reason === "model_not_ready"
          ? "The selected model is not running. Start it here, then create the session."
          : "No local model is running. Choose an installed model and start it first.");
      } else {
        setCreateMessage(reason === "too_many_sessions"
          ? "Too many open sessions - close one first."
          : status === 409
            ? "Local state changed while the session was starting. Refresh the model status and retry."
            : "The session could not be created.");
      }
    } finally {
      setCreatingSession(false);
      setBusy(false);
    }
  }

  async function send() {
    const text = draft.trim();
    if (!current || !text || busy || promptCheckBusy || currentModelBlocked) return;
    setBusy(true);
    setConversationMessage("");
    followOutput.current = true;
    try {
      const view = await transport.sendAgentMessage(current.session_id, text);
      setCurrent(view);
      setDraft("");
      clearPromptCheck();
    } catch (caught) {
      const reason = caught instanceof TransportError ? caught.reasonCode : null;
      if (caught instanceof TypeError && transport.getRuntimeHealth !== undefined) {
        setConnectionState("disconnected");
        setConversationMessage("The local app disconnected before it received this message. Your draft is still here; reopen the protected Agent window and retry after reconnection.");
      } else {
        if (reason === "model_not_ready" || reason === "no_active_model") void refreshModels();
        setConversationMessage(reason === "model_not_ready"
          ? "This session's model is stopped. Start the session model, then send again."
          : reason === "no_active_model"
            ? "No local model is running. Start a model, then send again."
            : reason === "turn_in_progress"
              ? "The agent is already working on a turn. Wait for it to finish or stop it first."
              : "The message could not be sent.");
      }
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
      setConversationMessage(status === 503
        ? "Native user-presence confirmation is unavailable in this app composition. The agent action remains pending."
        : status === 403
          ? "The native confirmation was declined or expired. The agent action remains pending."
          : "The decision did not reach the agent; refresh before deciding again.");
    }
  }

  async function stop() {
    if (!current) return;
    try {
      setConversationMessage("");
      setCurrent(await transport.stopAgentSession(current.session_id));
    } catch {
      setConversationMessage("The active response could not be stopped. Its live status will continue to refresh.");
    }
  }

  function openCurrentWindow(): void {
    if (!current) return;
    const opened = openAgentWindow(current.session_id);
    if (!opened) setConversationMessage("The separate Agent window could not be opened. Allow popups for this local app, then retry.");
  }

  async function closeSession(id: string) {
    if (current?.session_id === id && !mayLeaveWorkspace()) return;
    try {
      await transport.deleteAgentSession(id);
      if (current?.session_id === id) { setCurrent(null); setEvents([]); setHistoryGap(false); setStreamNotice(""); lastSeq.current = 0; }
      await refreshSessions();
    } catch {
      setConversationMessage("The session could not be closed.");
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
      </header>

      {connectionDisconnected && (
        <div className="agent__connection-error" role="alert">
          <strong>Local app disconnected</strong>
          <span>
            The page is still visible, but its local server is no longer running. Reopen the protected Agent desktop window and keep it open; this page will reconnect automatically. Sessions held by the closed process cannot be restored.
          </span>
        </div>
      )}

      <div className={`agent__layout${windowMode ? " agent__layout--window" : ""}${current ? " agent__layout--session" : ""}`}>
        {!windowMode && (
          <aside className="agent__side">
            <form aria-busy={creatingSession} className="agent__new" onSubmit={(event) => { event.preventDefault(); void createSession(); }}>
              <h2>New session</h2>
              <div className="agent__workspace-field">
                <label htmlFor="agent-workspace-folder">Workspace folder (absolute path)</label>
                <div className="agent__workspace-entry">
                  <input
                    aria-describedby="agent-workspace-help agent-workspace-picker-status"
                    aria-errormessage={workspaceError ? "agent-workspace-error" : undefined}
                    aria-invalid={workspaceError ? "true" : undefined}
                    aria-label="Workspace folder"
                    autoComplete="off"
                    id="agent-workspace-folder"
                    onChange={(event) => changeWorkspace(event.currentTarget.value)}
                    placeholder="D:\\projects\\example"
                    ref={workspaceInputRef}
                    spellCheck={false}
                    type="text"
                    value={workspace}
                  />
                  <button
                    className="button button--ghost"
                    disabled={!folderPickerAvailable || folderPickerBusy || creatingSession}
                    onClick={() => void browseForWorkspace()}
                    title={folderPickerAvailable ? "Choose a local workspace folder" : "Available in the native desktop window"}
                    type="button"
                  >
                    {folderPickerBusy ? "Choosing…" : "Browse…"}
                  </button>
                </div>
                <p className="agent__note" id="agent-workspace-help">
                  {folderPickerAvailable
                    ? "Choose a folder, or enter or paste its absolute path. The picker does not read its files."
                    : "Folder browsing is unavailable in this browser. Enter or paste an absolute path."}
                </p>
                <p className="agent__note" id="agent-workspace-picker-status" role="status">
                  {folderPickerNotice}
                </p>
                {workspaceError && <p className="agent__error" id="agent-workspace-error" role="alert">{workspaceError}</p>}
              </div>
              <div className="agent__model-control">
                <label>
                  <span>Model</span>
                  <select
                    aria-describedby="agent-model-status"
                    aria-label="Agent model"
                    onChange={(event) => {
                      setModelAlias(event.currentTarget.value);
                      setModelFeedbackTarget("selection");
                      setModelError("");
                      setModelNotice("");
                    }}
                    value={modelAlias}
                  >
                    <option value="">
                      {modelCatalogState === "loading"
                        ? "Checking active model…"
                        : runningModels.length > 0
                          ? `Active model · ${runningModels[0].record.display_name} · running`
                          : "No active model running"}
                    </option>
                    {(models?.models ?? []).map((model) => (
                      <option key={model.record.alias} value={model.record.alias}>
                        {model.record.display_name} · {runtimeStateLabel(model.runtime.state)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="agent__model-state" id="agent-model-status">
                  <p className="agent__note" role="status">
                    {connectionDisconnected
                      ? "The local app is disconnected; cached model status is not usable."
                      : modelCatalogState === "loading"
                      ? "Checking which local models are ready…"
                      : modelCatalogState === "error"
                        ? "Model status could not be refreshed. The server will verify it before the first message."
                        : modelCatalogState === "unavailable"
                          ? "Model status will be verified when the session starts."
                            : selectedModel === null
                            ? modelAlias
                              ? "That model is not registered. Choose an installed model."
                              : "No model is running. Choose an installed model, then start it."
                            : selectedModel.runtime.state === "running"
                              ? `${selectedModel.record.display_name} is running and ready.`
                              : `${selectedModel.record.display_name} is ${runtimeStateLabel(selectedModel.runtime.state)} and cannot run a session yet.`}
                  </p>
                  {modelAlias && selectedModel && selectedModel.runtime.state !== "running" && transport.activateLocalModel && (
                    <button
                      className="button button--ghost"
                      disabled={connectionDisconnected || Boolean(modelActionAlias) || selectedModel.runtime.state === "starting"}
                      onClick={() => void activateModel(selectedModel.record.alias, "selection")}
                      type="button"
                    >
                      {modelActionAlias === selectedModel.record.alias && modelActionKind === "start" ? "Starting model…" : "Start selected model"}
                    </button>
                  )}
                  {(modelCatalogState === "error" || selectedModel?.runtime.state === "starting") && transport.getLocalModels && (
                    <button
                      className="button button--ghost"
                      disabled={modelRefreshBusy}
                      onClick={() => void refreshModelStatus("selection")}
                      type="button"
                    >
                      {modelRefreshBusy ? "Refreshing…" : "Refresh model status"}
                    </button>
                  )}
                  {modelCatalogState === "ready" && selectedModel === null && (
                    <a className="button button--ghost" href="/models">Open Models</a>
                  )}
                  {modelFeedbackTarget === "selection" && modelError && <p className="agent__error" role="alert">{modelError}</p>}
                  {modelFeedbackTarget === "selection" && modelNotice && <p className="agent__notice" role="status">{modelNotice}</p>}
                </div>
              </div>
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
              <fieldset
                aria-describedby="agent-permission-status"
                className="agent__permissions"
                disabled={!userPresenceAvailable}
              >
                <legend>Protected actions</legend>
                <label className="agent__toggle"><input checked={allowWrites} onChange={(e) => setAllowWrites(e.currentTarget.checked)} type="checkbox" /><span>May write files (each write needs approval, diff shown)</span></label>
                <label className="agent__toggle"><input checked={allowCommands} onChange={(e) => setAllowCommands(e.currentTarget.checked)} type="checkbox" /><span>May run commands (each command needs approval)</span></label>
                <label className="agent__toggle"><input checked={allowWeb} onChange={(e) => setAllowWeb(e.currentTarget.checked)} type="checkbox" /><span>May fetch web pages (each fetch needs approval)</span></label>
              </fieldset>
              <div className="agent__permission-state">
                <p
                  className="agent__note"
                  id="agent-permission-status"
                  role={userPresenceState === "error" ? "alert" : "status"}
                >
                  {userPresenceState === "checking"
                    ? "Checking whether native confirmation is available…"
                    : userPresenceState === "available"
                      ? "Optional. Every selected protected action still requires a separate native confirmation. Keep this protected Agent window open; closing it stops its models and in-memory sessions."
                      : userPresenceState === "error"
                        ? "Native confirmation could not be verified. New sessions stay read-only."
                        : <>
                            This browser can start read-only sessions. For Browse and protected actions on Windows, stop the current <code>serve</code> process and run <code>prompt-enhancer agent-desktop</code>.
                          </>}
                </p>
                {userPresenceState === "error" && transport.getUserPresenceCapability && (
                  <button className="button button--ghost" onClick={() => setUserPresenceRetryNonce((value) => value + 1)} type="button">
                    Retry confirmation check
                  </button>
                )}
              </div>
              <button
                aria-describedby={createMessage ? "agent-create-error" : undefined}
                className="button button--primary"
                disabled={busy || creatingSession || folderPickerBusy || userPresenceState === "checking" || selectedModelBlocked || !workspace.trim()}
                type="submit"
              >
                {creatingSession
                  ? "Starting session…"
                  : connectionDisconnected
                    ? "Local app disconnected"
                    : selectedModelBlocked
                    ? "Start model first"
                    : userPresenceAvailable ? "Start session" : "Start read-only session"}
              </button>
              {createMessage && <p className="agent__error" id="agent-create-error" role="alert">{createMessage}</p>}
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
            <TeamFoldersPanel onUseAsWorkspace={changeWorkspace} transport={transport} />
          </aside>
        )}

        <div className="agent__workbench" data-has-workspace={current && !windowMode ? "true" : "false"}>
          {current && !windowMode && (
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
            <div className="agent__empty">
              <p className="agent__note" role="status">
                {windowMode && sessionLookupState === "loading"
                  ? "Opening this Agent session…"
                  : windowMode && sessionLookupState === "missing"
                    ? "This in-memory session is no longer available. It may have been closed or cleared when the local app restarted."
                    : windowMode && sessionLookupState === "error"
                      ? "This Agent window could not reach its session. Return to the Agent page and open it again."
                      : windowMode
                        ? "This window has no session. Open one from the Agent page."
                        : "Start a session on the left, then ask for something: explore the repo, fix a failing test, draft a document."}
              </p>
              {windowMode && (sessionLookupState === "missing" || sessionLookupState === "error") && (
                <a className="button button--ghost" href="/agent">Return to Agent</a>
              )}
            </div>
          ) : (
            <>
              <div className="agent__session-header">
                <div className="agent__meta">
                  <code>{current.settings.workspace}</code>
                  <span>
                    {current.model_alias ?? "no model"}
                    {current.settings.parameters ? " · t=" + current.settings.parameters.temperature.toFixed(2) + " · " + String(current.settings.parameters.max_tokens) + " tok" + (current.settings.parameters.enable_thinking ? " · thinking" : "") : ""}
                    {" · "}{current.settings.allow_writes ? "writes" : "no writes"} · {current.settings.allow_commands ? "commands" : "no commands"} · {current.settings.allow_web ? "web" : "no web"}
                  </span>
                </div>
                <section aria-label="Agent activity status" className="agent__activity-overview">
                  <div className="agent__run-state" data-tone={activityState.tone}>
                    <span aria-hidden="true" className="agent__run-dot" />
                    <span>
                      <strong>{activityState.label}</strong>
                      <small>{activityState.detail}</small>
                    </span>
                  </div>
                  <div aria-label="Session activity facts" className="agent__run-facts">
                    <span>{current.turns} {current.turns === 1 ? "turn" : "turns"}</span>
                    <span>{toolCallCount} {toolCallCount === 1 ? "action" : "actions"}</span>
                    <span data-reasoning={hasVisibleReasoning ? "visible" : reasoningEnabled ? "enabled" : "off"}>
                      {hasVisibleReasoning ? "Reasoning visible" : reasoningEnabled ? "Reasoning enabled" : "Reasoning off"}
                    </span>
                  </div>
                  <div className="agent__run-actions">
                    {!windowMode && (
                      <button className="button button--ghost" onClick={openCurrentWindow} type="button">Open separate window</button>
                    )}
                  </div>
                </section>
                <div
                  className="agent__model-readiness"
                  data-state={currentModel?.runtime.state ?? modelCatalogState}
                >
                  <span id="agent-session-model-status" role="status">
                    {connectionDisconnected
                      ? "The local app is disconnected. Reopen the protected Agent desktop window before sending."
                      : modelCatalogState === "loading"
                      ? "Checking the session model…"
                      : modelCatalogState === "error"
                        ? "Model status could not be refreshed; it will be verified before the next turn."
                        : modelCatalogState === "unavailable"
                          ? "The session model will be verified before the next turn."
                          : currentModel === null
                            ? currentModelAlias
                              ? "The session model is not registered and cannot receive a message."
                              : "No local model is running for this session. Start one on the Models page."
                            : currentModel.runtime.state === "running"
                              ? `${currentModel.record.display_name} · running · ready for messages`
                              : `${currentModel.record.display_name} · ${runtimeStateLabel(currentModel.runtime.state)} · start it before sending`}
                  </span>
                  <div className="agent__model-actions">
                    {currentModel && currentModel.runtime.state !== "running" && transport.activateLocalModel && (
                      <button
                        className="button button--ghost"
                        disabled={Boolean(modelActionAlias) || currentModel.runtime.state === "starting"}
                        onClick={() => void activateModel(currentModel.record.alias, "session")}
                        type="button"
                      >
                        {modelActionAlias === currentModel.record.alias && modelActionKind === "start" ? "Starting model…" : "Start session model"}
                      </button>
                    )}
                    {currentModel?.runtime.state === "running" && transport.deactivateLocalModel && (
                      <button
                        className="button button--ghost"
                        disabled={Boolean(modelActionAlias) || current.running}
                        onClick={() => void deactivateModel(currentModel.record.alias, "session")}
                        title={current.running ? "Stop the active response first" : "Stop this shared local runtime; sessions stay open"}
                        type="button"
                      >
                        {modelActionAlias === currentModel.record.alias && modelActionKind === "stop" ? "Stopping model…" : "Stop model"}
                      </button>
                    )}
                    {(modelCatalogState === "error" || currentModel?.runtime.state === "starting") && transport.getLocalModels && (
                      <button
                        className="button button--ghost"
                        disabled={modelRefreshBusy}
                        onClick={() => void refreshModelStatus("session")}
                        type="button"
                      >
                        {modelRefreshBusy ? "Refreshing…" : "Refresh model status"}
                      </button>
                    )}
                    {modelCatalogState === "ready" && currentModel === null && (
                      <a className="button button--ghost" href="/models">Open Models</a>
                    )}
                  </div>
                  {current.running && currentModel?.runtime.state === "running" && transport.deactivateLocalModel && (
                    <span className="agent__action-note">Stop the active response before stopping its model.</span>
                  )}
                  {modelFeedbackTarget === "session" && modelError && <p className="agent__error" role="alert">{modelError}</p>}
                  {modelFeedbackTarget === "session" && modelNotice && <p className="agent__notice" role="status">{modelNotice}</p>}
                </div>
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
                <header className="agent__log-head">
                  <span>
                    <small>Conversation</small>
                    <strong>Messages and agent activity</strong>
                  </span>
                  <span className="agent__activity-badge" data-tone={activityState.tone}>{activityState.label}</span>
                </header>
                <div aria-label="Agent activity" className="agent__timeline" role="region">
                  {historyGap && <p className="agent__status" role="status">Earlier in-memory events expired; completed replies below remain authoritative.</p>}
                  {events.map((event) => {
                    if (event.kind !== "assistant_delta") return <EventRow key={event.seq} event={event} reasoningEnabled={reasoningEnabled} />;
                    if (!event.stream_id) return null;
                    const live = liveStreams.get(event.stream_id);
                    return live && live.firstSeq === event.seq
                      ? <LiveAssistant key={event.stream_id} content={live.content} reasoning={live.reasoning} />
                      : null;
                  })}
                  {current.turns === 0 && !current.running && !pending && !events.some((event) => event.kind === "user" || event.kind === "assistant" || event.kind === "assistant_delta") && (
                    <p className="agent__status">
                      {modelCatalogState === "loading"
                        ? "Session created. Checking the model before your first message…"
                        : currentModelBlocked
                          ? currentModel === null
                            ? "Session created. Open Models and start a local model to continue."
                            : "Session created. Start the session model above to continue."
                          : reasoningEnabled
                            ? "Session ready. Reasoning will appear here when the model exposes it. Write your first request below."
                            : "Session ready. Write your first request below. Reasoning is off for this session."}
                    </p>
                  )}
                  {current.running && !pending && liveStreams.size === 0 && <p className="agent__thinking">Working… waiting for model activity</p>}
                </div>
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
              <form aria-label="Message composer" className="agent__compose" onSubmit={(event) => { event.preventDefault(); void send(); }}>
                <label className="agent__compose-label" htmlFor="agent-message">Message to the agent</label>
                <textarea
                  aria-describedby={`agent-session-model-status${conversationMessage ? " agent-message-error" : ""}`}
                  disabled={current.running || currentModelBlocked}
                  id="agent-message"
                  onChange={(e) => changeDraft(e.currentTarget.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void send(); } }}
                  placeholder={current.running
                    ? "The agent is working…"
                    : connectionDisconnected
                      ? "The local app is disconnected; reopen it before writing a message"
                      : currentModelBlocked
                      ? currentModel === null
                        ? "Open Models and start a local model to write a message"
                        : "Start the session model to write a message"
                      : "What should the agent do? Ctrl+Enter sends"}
                  ref={composerInputRef}
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
                  {current.running ? (
                    <button className="button button--danger-ghost" onClick={() => void stop()} type="button">Stop response</button>
                  ) : (
                    <button className="button button--primary" disabled={busy || promptCheckBusy || currentModelBlocked || !draft.trim()} type="submit">Send</button>
                  )}
                </div>
                <div aria-live="polite" className="agent__prompt-check-status">
                  {promptCheckError && <p className="agent__error" role="alert">{promptCheckError}</p>}
                  {promptCheckNotice && <p className="agent__status">{promptCheckNotice}</p>}
                </div>
                {promptCheckResult && <AgentPromptCheckResult onUseRewrite={usePromptRewrite} result={promptCheckResult} />}
              </form>
            </>
          )}
          {conversationMessage && <p className="agent__error" id="agent-message-error" role="alert">{conversationMessage}</p>}
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
      <header><span>Agent</span><span className="agent__event-badge">Streaming</span></header>
      {reasoning && <details className="agent__reasoning" open><summary><span>Reasoning</span><small>live · model-provided</small></summary><pre>{reasoning}</pre></details>}
      {content && <pre>{content}</pre>}
    </article>
  );
}

function EventRow({ event, reasoningEnabled }: { event: AgentEvent; reasoningEnabled: boolean }) {
  if (event.kind === "user") return <article className="agent__turn agent__turn--user"><header>You</header><pre>{event.text}</pre></article>;
  if (event.kind === "assistant") {
    const status = event.stream_status === "stopped" ? "Stopped" : event.stream_status === "failed" ? "Interrupted" : "Complete";
    return (
      <article className="agent__turn agent__turn--assistant" data-stream-status={event.stream_status ?? "whole"}>
        <header><span>Agent</span><span className="agent__event-badge">{status}</span></header>
        {event.reasoning && <details className="agent__reasoning"><summary><span>Reasoning</span><small>model-provided · expand</small></summary><pre>{event.reasoning}</pre></details>}
        {!event.reasoning && reasoningEnabled && <p className="agent__reasoning-inline">No separate reasoning trace was exposed for this response.</p>}
        {event.text ? <pre>{event.text}</pre> : !event.reasoning ? <p className="agent__status">No assistant text was completed.</p> : null}
      </article>
    );
  }
  if (event.kind === "assistant_delta") return null;
  if (event.kind === "tool_call") {
    return (
      <article aria-label={`Agent action: ${TOOL_LABELS[event.tool ?? ""] ?? event.tool ?? "tool"}`} className="agent__tool" data-tool={event.tool ?? ""}>
        <span className="agent__event-badge">Action</span>
        <span className="agent__tool-name">{TOOL_LABELS[event.tool ?? ""] ?? event.tool}</span>
        <code>{summarizeArguments(event.tool, event.arguments as Record<string, unknown> | null)}</code>
      </article>
    );
  }
  if (event.kind === "tool_result") {
    return (
      <details className="agent__result" data-ok={event.ok ? "true" : "false"}>
        <summary><span className="agent__event-badge">{event.ok ? "Completed" : "Failed"}</span><span>{TOOL_LABELS[event.tool ?? ""] ?? event.tool}</span></summary>
        <pre>{event.text}</pre>
      </details>
    );
  }
  if (event.kind === "approval_required") return <p className="agent__activity-event" data-tone="attention"><span className="agent__event-badge">Approval</span>Waiting for your decision: {TOOL_LABELS[event.tool ?? ""] ?? event.tool}</p>;
  if (event.kind === "approval_resolved") return <p className="agent__activity-event" data-tone={event.ok ? "ready" : "attention"}><span className="agent__event-badge">{event.ok ? "Approved" : "Denied"}</span>{TOOL_LABELS[event.tool ?? ""] ?? event.tool}{event.text ? ` (${event.text})` : ""}</p>;
  if (event.kind === "error") return <p className="agent__activity-event agent__error" data-tone="error" role="alert"><span className="agent__event-badge">Error</span>{event.text}</p>;
  if (event.kind === "status") return <p className="agent__activity-event agent__status"><span className="agent__event-badge">Status</span>{event.text}</p>;
  return null;
}
