import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  AgentSessionContextStatus,
  AgentSessionView,
  AgentCatalogSession,
  DeviceMode,
  LocalModelPlacementAdmission,
  LocalModelsOverview,
  LocalRuntimeCoordinatorStatus,
  PromptEnhancerTransport,
  RuntimeContextStatus,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { Icon } from "../../shared/ui/Icon";
import { AgentGenerationSettings, type AgentGenerationParameters } from "./AgentGenerationSettings";
import "./AgentRuntimeControl.css";

type RuntimeControlTransport = Partial<Pick<
  PromptEnhancerTransport,
  "getLocalRuntime" | "switchLocalRuntime" | "stopLocalRuntime"
  | "getLocalModelPlacement"
  | "getAgentCatalogSession" | "getAgentSessionContext" | "switchAgentSessionModel"
  | "updateAgentSessionParameters" | "getAgentSession"
>>;

type Props = {
  current: AgentSessionView | null;
  disabled: boolean;
  focusRequestKey?: number;
  liveSessions: AgentSessionView[] | null;
  models: LocalModelsOverview | null;
  onBusyChange: (busy: boolean) => void;
  onModelSelected: (alias: string) => void;
  onModelsRefresh: () => Promise<LocalModelsOverview | null | undefined>;
  onRuntimeStatus?: (runtime: LocalRuntimeCoordinatorStatus | null) => void;
  onSessionUpdated: (session: AgentSessionView) => void;
  variant?: "panel" | "composer";
  transport: RuntimeControlTransport;
};

type RuntimeReadRequest = {
  controller: AbortController;
  timeout?: number | null;
  transport: RuntimeControlTransport;
};

type ContextReadRequest = RuntimeReadRequest & {
  attempt: ContextAttempt;
  expectedTurnNumber: number | null;
  modelAlias: string | null;
  sessionId: string;
};

type ContextAttempt = {
  deadline: number | null;
  expired: boolean;
  expiration: Promise<typeof CONTEXT_ATTEMPT_EXPIRED>;
  expire: () => void;
  expectedTurnNumber: number | null;
  modelAlias: string | null;
  sessionId: string;
  transport: RuntimeControlTransport;
};

type RuntimeOperation = RuntimeReadRequest & {
  kind: "apply" | "stop" | "settings";
  lifecycle: number;
};

type PlacementReadRequest = RuntimeReadRequest & {
  alias: string;
  contextSize: number;
};
type SettingsReadRequest = RuntimeReadRequest & { key: string; lifecycle: number; sessionId: string };

const CONTEXT_OPTIONS = [4096, 8192, 16384, 32768, 65536] as const;
const CONTEXT_PENDING_POLL_MS = 500;
const CONTEXT_READ_TIMEOUT_MS = 10_000;
const RUNTIME_READ_TIMEOUT_MS = 10_000;
const CONTEXT_ATTEMPT_EXPIRED = Symbol("context-attempt-expired");

function stateLabel(state: LocalRuntimeCoordinatorStatus["state"]): string {
  return {
    idle: "Stopped",
    draining: "Waiting for active request",
    unloading: "Unloading",
    loading: "Loading",
    ready: "Ready",
    failed: "Needs attention",
    cleanup_unknown: "Cleanup unconfirmed",
    quarantined: "Runtime quarantined",
  }[state];
}

function placementLabel(device: DeviceMode): string {
  return device === "gpu" ? "GPU" : device === "split" ? "GPU + CPU" : "CPU";
}

function placementReasonLabel(reason: string): string {
  return {
    cpu_available: "CPU execution is available without GPU offload.",
    accelerator_evidence_unavailable: "No current accelerator and free-memory evidence was detected.",
    model_size_unavailable: "Model size is unavailable, so VRAM fit cannot be estimated.",
    layer_count_unavailable: "GGUF layer count is unavailable, so split placement cannot be bounded.",
    context_exceeds_model_metadata: "This context exceeds the model's verified GGUF metadata.",
    gpu_estimate_fits: "The conservative full-GPU estimate fits current free VRAM.",
    gpu_estimate_exceeds_free_memory: "Estimated weights, context and safety headroom exceed free VRAM.",
    split_estimate_available: "A bounded GPU-layer estimate is available.",
    split_estimate_exceeds_free_memory: "No layer fits after context and safety headroom.",
    owned_runtime_requires_cleanup_recheck: "The app must unload its current GPU runtime, verify cleanup, and recheck.",
  }[reason] ?? "Placement evidence is unavailable.";
}

function measuredContextLabel(context: RuntimeContextStatus | null | undefined): string {
  if (!context?.limit_tokens) return "Unknown · no token estimate";
  if (context.state !== "known" || context.used_tokens == null) {
    return `Unknown · no token estimate / ${context.limit_tokens.toLocaleString()} limit`;
  }
  const used = context.used_tokens.toLocaleString();
  const limit = context.limit_tokens.toLocaleString();
  const available = context.available_output_tokens ?? context.limit_tokens - context.used_tokens;
  if (context.policy === "exact_refused") {
    if (available < 0) {
      return `${used} input / ${limit} · ${Math.abs(available).toLocaleString()} over limit · refused`;
    }
    const requested = context.requested_output_tokens ?? 0;
    const shortfall = Math.max(0, requested - available);
    return `${used} input / ${limit} · ${shortfall.toLocaleString()} output tokens short · refused`;
  }
  const compacted = context.policy === "exact_compacted"
    ? ` · ${context.compacted_messages.toLocaleString()} earlier message${context.compacted_messages === 1 ? "" : "s"} omitted`
    : "";
  return `${used} input / ${limit} · ${available.toLocaleString()} available${compacted}`;
}

function unmeasuredContextLabel(context: AgentSessionContextStatus): string {
  const turn = context.turn_number ? ` · turn ${context.turn_number}` : "";
  return {
    no_request_measured: "not measured for this chat",
    recovered_without_context_receipt: "Unknown after restart · no token estimate",
    turn_pending_preflight: `Measuring exact context${turn}…`,
    turn_ended_before_preflight: `Unknown · turn ended before measurement${turn}`,
    turn_start_failed: `Unknown · turn did not start${turn}`,
    preflight_unavailable: `Unknown · exact counter unavailable${turn}`,
    preflight_failed: `Unknown · exact counter failed${turn}`,
    request_body_too_large: `Unknown · request body exceeded preflight limit${turn}`,
    model_changed: "Unknown · model changed; no token estimate",
  }[context.unknown_reason ?? "no_request_measured"];
}

function contextLabel(
  runtime: LocalRuntimeCoordinatorStatus | null,
  sessionContext: AgentSessionContextStatus | null,
  hasCurrentChat: boolean,
  contextReadFailed: boolean,
  contextLoading: boolean,
  contextPendingExpired: boolean,
): string {
  if (!hasCurrentChat) return `${measuredContextLabel(runtime?.context)} · runtime`;
  if (contextPendingExpired) {
    if (sessionContext?.binding_state === "bound") {
      return `${measuredContextLabel(sessionContext.context)} · turn ${sessionContext.turn_number} · last confirmed · refresh did not settle`;
    }
    return "Unknown · exact preflight did not settle · Refresh to retry";
  }
  if (contextLoading && sessionContext === null) return "checking this chat's context evidence";
  if (sessionContext === null) return contextReadFailed
    ? "Unknown · context evidence unavailable · Refresh to retry"
    : "not measured for this chat";
  if (sessionContext.binding_state !== "bound") return unmeasuredContextLabel(sessionContext);
  const freshness = contextReadFailed
    ? " · last confirmed · refresh failed"
    : contextLoading ? " · checking latest" : "";
  return `${measuredContextLabel(sessionContext.context)} · turn ${sessionContext.turn_number}${freshness}`;
}

function exactContextPercentage(context: RuntimeContextStatus | null | undefined): number | null {
  if (context?.state !== "known" || context.used_tokens == null || context.limit_tokens == null) return null;
  return Math.round((context.used_tokens / context.limit_tokens) * 100);
}

function contextTone(
  context: RuntimeContextStatus | null | undefined,
  stale: boolean,
): "exact" | "unknown" | "caution" | "critical" | "stale" {
  if (stale) return "stale";
  const percentage = exactContextPercentage(context);
  if (percentage === null) return "unknown";
  if (context?.policy === "exact_refused" || percentage >= 90) return "critical";
  if (context?.policy === "exact_compacted" || percentage >= 75) return "caution";
  return "exact";
}

function operationError(error: unknown, switchedRuntime: boolean): string {
  const reason = error instanceof TransportError ? error.reasonCode : null;
  if (switchedRuntime) {
    return "The new model is running, but this chat binding did not update. Apply again to rebind this chat; its draft and conversation are unchanged.";
  }
  if (reason === "runtime_busy" || reason === "turn_in_progress") {
    return "A response is still active. Stop or finish it before changing the shared model runtime.";
  }
  if (reason === "runtime_revision_conflict") {
    return "Runtime state changed in another view. Status was refreshed; review it and apply again.";
  }
  if (reason === "runtime_cleanup_unconfirmed") {
    return "The old process exited, but GPU-memory cleanup could not be verified. No replacement model was loaded.";
  }
  if (reason === "runtime_quarantined" || reason === "runtime_stop_failed") {
    return "The previous runtime did not confirm a safe stop. Model loading is quarantined until cleanup is resolved.";
  }
  if (reason === "runtime_capability_probe_failed" || reason === "runtime_not_healthy") {
    return "The model process started but did not pass its local text-capability check, so it was not marked ready.";
  }
  if (reason === "runtime_placement_unavailable") {
    return "Placement was refused by the latest hardware preflight. Review the device estimate and choose an admitted option.";
  }
  if (reason === "runtime_gpu_layers_invalid") {
    return "The GPU-layer request is not coherent with this model's verified layer metadata.";
  }
  if (reason === "runtime_context_unsupported") {
    return "That context limit exceeds this model's verified GGUF context metadata.";
  }
  if (reason === "model_not_ready") {
    return "The chat was not rebound because the selected model is not the verified served runtime.";
  }
  return "The runtime change did not complete. Status was refreshed; no draft or conversation content was changed.";
}

export function AgentRuntimeControl({
  current,
  disabled,
  focusRequestKey = 0,
  liveSessions,
  models,
  onBusyChange,
  onModelSelected,
  onModelsRefresh,
  onRuntimeStatus,
  onSessionUpdated,
  transport,
  variant = "panel",
}: Props) {
  const available = transport.getLocalRuntime !== undefined
    && transport.switchLocalRuntime !== undefined
    && transport.stopLocalRuntime !== undefined;
  const [runtime, setRuntime] = useState<LocalRuntimeCoordinatorStatus | null>(null);
  const [sessionContext, setSessionContext] = useState<AgentSessionContextStatus | null>(null);
  const [contextReadFailed, setContextReadFailed] = useState(false);
  const [contextLoading, setContextLoading] = useState(false);
  const [contextPendingExpired, setContextPendingExpired] = useState(false);
  const [contextPendingPollKey, setContextPendingPollKey] = useState(0);
  const [placement, setPlacement] = useState<LocalModelPlacementAdmission | null>(null);
  const [placementLoading, setPlacementLoading] = useState(false);
  const [placementReadFailed, setPlacementReadFailed] = useState(false);
  const [placementRefreshKey, setPlacementRefreshKey] = useState(0);
  const [runtimeReadFailed, setRuntimeReadFailed] = useState(false);
  const [loading, setLoading] = useState(available);
  const [busy, setBusy] = useState(false);
  const [alias, setAlias] = useState("");
  const [device, setDevice] = useState<DeviceMode>("split");
  const [contextSize, setContextSize] = useState(8192);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [settingsCatalog, setSettingsCatalog] = useState<AgentCatalogSession | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const settingsRead = useRef<SettingsReadRequest | null>(null);
  const settingsIdentity = useRef("");
  const settingsDisclosureToggleFromClick = useRef(false);
  const composerDetailsRef = useRef<HTMLDetailsElement | null>(null);
  const modelSelectRef = useRef<HTMLSelectElement | null>(null);
  const runtimeDraftDirty = useRef(false);
  const runtimeRead = useRef<RuntimeReadRequest | null>(null);
  const contextRead = useRef<ContextReadRequest | null>(null);
  const contextAttempt = useRef<ContextAttempt | null>(null);
  const placementRead = useRef<PlacementReadRequest | null>(null);
  const contextIdentity = useRef("");
  const contextRefreshDeferred = useRef(false);
  const operation = useRef<RuntimeOperation | null>(null);
  const lifecycle = useRef(0);
  const runtimeState = useRef<LocalRuntimeCoordinatorStatus | null>(null);
  const sessionContextState = useRef<AgentSessionContextStatus | null>(null);
  const currentModelAlias = current?.model_alias ?? current?.settings.model_alias ?? null;
  const settingsParameters = current?.settings.parameters;
  const settingsProjectId = current?.settings.project_id ?? null;
  const expectedContextTurnNumber = current === null
    ? null
    : current.turns;
  const callbacks = useRef({ onBusyChange, onRuntimeStatus });
  callbacks.current = { onBusyChange, onRuntimeStatus };
  const requestContext = useRef({
    expectedTurnNumber: expectedContextTurnNumber,
    modelAlias: currentModelAlias,
    sessionId: current?.session_id ?? null,
    transport,
  });
  requestContext.current = {
    expectedTurnNumber: expectedContextTurnNumber,
    modelAlias: currentModelAlias,
    sessionId: current?.session_id ?? null,
    transport,
  };
  const settingsKey = `${current?.session_id ?? ""}:${settingsProjectId ?? ""}`;
  const settingsCatalogReady = settingsCatalog !== null
    && settingsCatalog.session_id === current?.session_id
    && settingsCatalog.project_id === settingsProjectId
    && settingsIdentity.current === settingsKey
    && transport.updateAgentSessionParameters !== undefined;
  useEffect(() => {
    if (settingsIdentity.current === settingsKey) return;
    settingsIdentity.current = settingsKey;
    settingsRead.current?.controller.abort();
    if (settingsRead.current?.timeout != null) window.clearTimeout(settingsRead.current.timeout);
    settingsRead.current = null;
    setSettingsLoading(false);
    setSettingsCatalog(null);
  }, [settingsKey]);
  runtimeState.current = runtime;
  sessionContextState.current = sessionContext;

  const matchesContextAttempt = useCallback((attempt: ContextAttempt) => (
    requestContext.current.transport === attempt.transport
    && requestContext.current.sessionId === attempt.sessionId
    && requestContext.current.modelAlias === attempt.modelAlias
    && requestContext.current.expectedTurnNumber === attempt.expectedTurnNumber
  ), []);

  const ownsContextAttempt = useCallback((attempt: ContextAttempt) => (
    contextAttempt.current === attempt
    && !attempt.expired
    && matchesContextAttempt(attempt)
  ), [matchesContextAttempt]);

  const clearContextAttempt = useCallback((attempt: ContextAttempt | null, abortRead: boolean) => {
    if (attempt === null) return;
    if (attempt.deadline !== null) window.clearTimeout(attempt.deadline);
    attempt.deadline = null;
    attempt.expired = true;
    attempt.expire();
    if (abortRead && contextRead.current?.attempt === attempt) {
      contextRead.current.controller.abort();
      contextRead.current = null;
    }
    if (contextAttempt.current === attempt) contextAttempt.current = null;
  }, []);

  const startContextAttempt = useCallback((reset: boolean): ContextAttempt | null => {
    const { expectedTurnNumber, modelAlias, sessionId, transport: requestTransport } = requestContext.current;
    const existing = contextAttempt.current;
    if (existing !== null && matchesContextAttempt(existing) && !reset) {
      return existing.expired ? null : existing;
    }
    clearContextAttempt(existing, true);
    if (sessionId === null || requestTransport.getAgentSessionContext === undefined) return null;
    let resolveExpiration: (value: typeof CONTEXT_ATTEMPT_EXPIRED) => void = () => undefined;
    const attempt: ContextAttempt = {
      deadline: null,
      expired: false,
      expiration: new Promise<typeof CONTEXT_ATTEMPT_EXPIRED>((resolve) => { resolveExpiration = resolve; }),
      expire: () => resolveExpiration(CONTEXT_ATTEMPT_EXPIRED),
      expectedTurnNumber,
      modelAlias,
      sessionId,
      transport: requestTransport,
    };
    contextAttempt.current = attempt;
    setContextPendingExpired(false);
    attempt.deadline = window.setTimeout(() => {
      if (!ownsContextAttempt(attempt)) return;
      attempt.deadline = null;
      attempt.expired = true;
      attempt.expire();
      if (contextRead.current?.attempt === attempt) {
        contextRead.current.controller.abort();
        contextRead.current = null;
      }
      // A known bound receipt remains useful only as explicitly stale evidence;
      // an unmeasured pending receipt stays unknown rather than becoming zero.
      setContextReadFailed(false);
      setContextPendingExpired(true);
      setContextLoading(false);
    }, CONTEXT_READ_TIMEOUT_MS);
    return attempt;
  }, [clearContextAttempt, matchesContextAttempt, ownsContextAttempt]);

  const refreshContext = useCallback(async (owner?: RuntimeOperation, resetAttempt = false) => {
    const {
      expectedTurnNumber,
      modelAlias,
      sessionId,
      transport: requestTransport,
    } = requestContext.current;
    const getSessionContext = requestTransport.getAgentSessionContext;
    if (sessionId === null || getSessionContext === undefined) {
      clearContextAttempt(contextAttempt.current, true);
      contextRefreshDeferred.current = false;
      sessionContextState.current = null;
      setSessionContext(null);
      setContextReadFailed(sessionId !== null && getSessionContext === undefined);
      setContextPendingExpired(false);
      setContextLoading(false);
      return null;
    }
    if (operation.current !== null && operation.current !== owner) {
      // A runtime operation owns context reads while it runs. Remember the
      // skipped read so a chat identity change during the operation is measured
      // once it settles instead of leaving the panel stuck on "checking".
      contextRefreshDeferred.current = true;
      return null;
    }
    contextRefreshDeferred.current = false;
    const attempt = startContextAttempt(resetAttempt || owner !== undefined);
    if (attempt === null) return null;
    const request: ContextReadRequest = {
      attempt,
      controller: new AbortController(),
      expectedTurnNumber,
      modelAlias,
      sessionId,
      transport: requestTransport,
    };
    contextRead.current?.controller.abort();
    contextRead.current = request;
    setContextLoading(true);
    setContextReadFailed(false);
    try {
      const value = await Promise.race([
        Promise.resolve().then(() => getSessionContext(sessionId, request.controller.signal)),
        attempt.expiration,
      ]);
      if (value === CONTEXT_ATTEMPT_EXPIRED) return null;
      if (
        contextRead.current !== request
        || request.controller.signal.aborted
        || !ownsContextAttempt(attempt)
      ) return null;
      const turnMatches = value.turn_number === null
        || value.turn_number === request.expectedTurnNumber;
      if (
        value.session_id !== request.sessionId
        || !turnMatches
        || value.binding_state === "bound" && (
          value.model_alias !== request.modelAlias
          || value.turn_number !== request.expectedTurnNumber
        )
      ) {
        sessionContextState.current = null;
        setSessionContext(null);
        setContextReadFailed(true);
        clearContextAttempt(attempt, false);
        return null;
      }
      const previous = sessionContextState.current;
      if (previous?.session_id === value.session_id && previous.revision > value.revision) {
        if (
          previous.binding_state === "unmeasured"
          && previous.unknown_reason === "turn_pending_preflight"
        ) {
          setContextPendingPollKey((key) => key + 1);
        } else {
          clearContextAttempt(attempt, false);
        }
        return previous;
      }
      sessionContextState.current = value;
      setSessionContext(value);
      setContextReadFailed(false);
      if (value.binding_state === "unmeasured" && value.unknown_reason === "turn_pending_preflight") {
        // A lower/equal pending receipt can retain the same React state object.
        // Tick separately so its next bounded poll is not lost to batched loading
        // transitions, while the attempt deadline remains unchanged.
        setContextPendingPollKey((key) => key + 1);
      } else {
        clearContextAttempt(attempt, false);
      }
      return value;
    } catch {
      if (
        contextRead.current === request
        && !request.controller.signal.aborted
        && ownsContextAttempt(attempt)
      ) {
        if (
          sessionContextState.current?.binding_state === "unmeasured"
          && sessionContextState.current.unknown_reason === "turn_pending_preflight"
        ) {
          sessionContextState.current = null;
          setSessionContext(null);
        }
        setContextReadFailed(true);
        clearContextAttempt(attempt, false);
      }
      return null;
    } finally {
      if (contextRead.current === request) {
        contextRead.current = null;
        setContextLoading(false);
      }
    }
  }, [clearContextAttempt, ownsContextAttempt, startContextAttempt]);

  const refresh = useCallback(async (owner?: RuntimeOperation) => {
    const requestTransport = requestContext.current.transport;
    const getRuntime = requestTransport.getLocalRuntime;
    if (getRuntime === undefined) {
      if (runtimeRead.current?.timeout != null) window.clearTimeout(runtimeRead.current.timeout);
      runtimeRead.current?.controller.abort();
      runtimeRead.current = null;
      setLoading(false);
      return null;
    }
    if (operation.current !== null && operation.current !== owner) return null;
    const request: RuntimeReadRequest = {
      controller: new AbortController(),
      timeout: null,
      transport: requestTransport,
    };
    if (runtimeRead.current?.timeout != null) window.clearTimeout(runtimeRead.current.timeout);
    runtimeRead.current?.controller.abort();
    runtimeRead.current = request;
    setLoading(true);
    let timedOut = false;
    try {
      const timeout = new Promise<never>((_resolve, reject) => {
        request.timeout = window.setTimeout(() => {
          timedOut = true;
          request.controller.abort();
          reject(new Error("runtime status read timed out"));
        }, RUNTIME_READ_TIMEOUT_MS);
      });
      const value = await Promise.race([getRuntime(request.controller.signal), timeout]);
      if (
        runtimeRead.current !== request
        || request.controller.signal.aborted
        || requestContext.current.transport !== request.transport
      ) return null;
      const previous = runtimeState.current;
      if (previous !== null && previous.revision > value.revision) return previous;
      runtimeState.current = value;
      setRuntime(value);
      setRuntimeReadFailed(false);
      callbacks.current.onRuntimeStatus?.(value);
      return value;
    } catch {
      if (
        runtimeRead.current === request
        && (timedOut || !request.controller.signal.aborted)
        && requestContext.current.transport === request.transport
      ) {
        // Keep the last confirmed snapshot so a deliberate Stop can still send
        // its exact alias and revision, but do not present it as current
        // evidence or permit a replacement/start from it.
        setRuntimeReadFailed(true);
        callbacks.current.onRuntimeStatus?.(null);
      }
      return null;
    } finally {
      if (request.timeout != null) window.clearTimeout(request.timeout);
      request.timeout = null;
      if (runtimeRead.current === request) {
        runtimeRead.current = null;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    lifecycle.current += 1;
    setBusy(false);
    const requestTransport = transport;
    return () => {
      lifecycle.current += 1;
      if (runtimeRead.current?.transport === requestTransport) {
        if (runtimeRead.current.timeout != null) window.clearTimeout(runtimeRead.current.timeout);
        runtimeRead.current.controller.abort();
        runtimeRead.current = null;
      }
      if (contextAttempt.current?.transport === requestTransport) {
        clearContextAttempt(contextAttempt.current, true);
        setContextLoading(false);
      }
      if (placementRead.current?.transport === requestTransport) {
        placementRead.current.controller.abort();
        placementRead.current = null;
      }
      if (settingsRead.current?.transport === requestTransport) {
        if (settingsRead.current.timeout != null) window.clearTimeout(settingsRead.current.timeout);
        settingsRead.current.controller.abort();
        settingsRead.current = null;
        setSettingsLoading(false);
      }
      setSettingsCatalog(null);
      if (operation.current?.transport === requestTransport) {
        operation.current.controller.abort();
        operation.current = null;
        callbacks.current.onBusyChange(false);
      }
    };
  }, [clearContextAttempt, transport]);

  useEffect(() => {
    runtimeRead.current?.controller.abort();
    if (runtimeRead.current?.timeout != null) window.clearTimeout(runtimeRead.current.timeout);
    runtimeRead.current = null;
    runtimeState.current = null;
    setRuntime(null);
    setRuntimeReadFailed(false);
    callbacks.current.onRuntimeStatus?.(null);
    setLoading(available);
    setNotice("");
    setError("");
    void refresh();
  }, [available, refresh, transport]);

  useEffect(() => {
    const identity = current === null
      ? ""
      : `${current.session_id}:${currentModelAlias ?? ""}:${expectedContextTurnNumber ?? 0}`;
    const changed = contextIdentity.current !== identity;
    contextIdentity.current = identity;
    if (changed) {
      clearContextAttempt(contextAttempt.current, true);
      sessionContextState.current = null;
      setSessionContext(null);
      setContextReadFailed(false);
      setContextPendingExpired(false);
      setContextLoading(current !== null && transport.getAgentSessionContext !== undefined);
    }
    void refreshContext();
  }, [
    current?.running,
    current?.session_id,
    currentModelAlias,
    expectedContextTurnNumber,
    clearContextAttempt,
    refreshContext,
    transport,
  ]);

  useEffect(() => {
    if (
      !current?.running
      || contextLoading
      || contextReadFailed
      || contextPendingExpired
      || sessionContext?.binding_state !== "unmeasured"
      || sessionContext.unknown_reason !== "turn_pending_preflight"
    ) return;
    const handle = window.setTimeout(() => { void refreshContext(); }, CONTEXT_PENDING_POLL_MS);
    return () => window.clearTimeout(handle);
  }, [
    contextLoading,
    contextReadFailed,
    contextPendingExpired,
    contextPendingPollKey,
    current?.running,
    refreshContext,
    sessionContext?.binding_state,
    sessionContext?.revision,
    sessionContext?.unknown_reason,
  ]);

  useEffect(() => {
    const handleFocus = () => {
      void refresh();
      void refreshContext();
    };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [refresh, refreshContext]);

  useEffect(() => {
    runtimeDraftDirty.current = false;
  }, [current?.session_id]);

  useEffect(() => {
    // Runtime and model-catalog refreshes can resolve independently. Once the
    // user has edited a pending selection, keep that draft intact until it is
    // applied or the active chat changes instead of snapping back to served.
    if (runtimeDraftDirty.current) return;
    if (runtime?.served) {
      setAlias(runtime.served.alias);
      setDevice(runtime.served.device);
      setContextSize(runtime.served.context_size);
      onModelSelected(runtime.served.alias);
      return;
    }
    const currentAlias = current?.model_alias ?? current?.settings.model_alias ?? "";
    const record = models?.models.find((model) => model.record.alias === currentAlias);
    if (currentAlias) setAlias(currentAlias);
    if (record) {
      setDevice(record.record.default_device);
      setContextSize(record.record.context_size);
    }
  }, [current?.session_id, current?.settings.model_alias, current?.model_alias, models, onModelSelected, runtime?.revision]);

  useEffect(() => {
    const transitional = runtime?.state === "draining"
      || runtime?.state === "unloading"
      || runtime?.state === "loading";
    if (!transitional || busy) return;
    const handle = window.setTimeout(() => { void refresh(); }, 1000);
    return () => window.clearTimeout(handle);
  }, [busy, refresh, runtime?.state, runtime?.revision]);

  const selected = useMemo(
    () => models?.models.find((model) => model.record.alias === alias) ?? null,
    [alias, models],
  );
  useEffect(() => {
    const getPlacement = transport.getLocalModelPlacement;
    placementRead.current?.controller.abort();
    placementRead.current = null;
    setPlacementReadFailed(false);
    setPlacement(null);
    if (!alias || selected === null || getPlacement === undefined) {
      setPlacementLoading(false);
      return;
    }
    const request: PlacementReadRequest = {
      alias,
      contextSize,
      controller: new AbortController(),
      transport,
    };
    placementRead.current = request;
    setPlacementLoading(true);
    void getPlacement(alias, contextSize, request.controller.signal).then((value) => {
      if (
        placementRead.current !== request
        || request.controller.signal.aborted
        || requestContext.current.transport !== request.transport
        || value.alias !== request.alias
        || value.context_size !== request.contextSize
      ) return;
      setPlacement(value);
      setDevice((currentDevice) => {
        const currentOption = value.options.find((option) => option.device === currentDevice);
        if (currentOption?.state !== "blocked") return currentDevice;
        return value.options.find((option) => option.state !== "blocked")?.device ?? currentDevice;
      });
    }).catch(() => {
      if (
        placementRead.current === request
        && !request.controller.signal.aborted
        && requestContext.current.transport === request.transport
      ) {
        setPlacement(null);
        setPlacementReadFailed(true);
      }
    }).finally(() => {
      if (placementRead.current === request) {
        placementRead.current = null;
        setPlacementLoading(false);
      }
    });
    return () => {
      request.controller.abort();
      if (placementRead.current === request) placementRead.current = null;
    };
  }, [alias, contextSize, selected?.record.alias, transport, placementRefreshKey]);
  const placementAdmission = placement
    ?? (selected?.placement?.context_size === contextSize ? selected.placement : null);
  useEffect(() => {
    if (placementAdmission === null) return;
    const currentOption = placementAdmission.options.find((option) => option.device === device);
    if (currentOption?.state !== "blocked") return;
    const fallback = placementAdmission.options.find((option) => option.state !== "blocked");
    if (fallback !== undefined && fallback.device !== device) setDevice(fallback.device);
  }, [device, placementAdmission]);
  const selectedPlacement = placementAdmission?.options.find(
    (option) => option.device === device,
  ) ?? null;
  const livePlacementUnavailable = alias !== ""
    && selected !== null
    && (
      placementLoading
      || placementReadFailed
      || placementAdmission === null
      || transport.getLocalModelPlacement !== undefined && placement === null
    );
  const blockedPlacementSummary = placementAdmission?.options
    .filter((option) => option.state === "blocked")
    .map((option) => `${placementLabel(option.device)} unavailable: ${placementReasonLabel(option.reason_code)}`)
    .join(" ") ?? "";
  const anyTurnRunning = Boolean(liveSessions?.some((session) => session.running));
  const matchesRuntimeSnapshot = runtime?.state === "ready"
    && runtime.served?.alias === alias
    && runtime.served.device === device
    && runtime.served.context_size === contextSize;
  const exactSelection = matchesRuntimeSnapshot && !runtimeReadFailed;
  const chatNeedsRebind = Boolean(current && currentModelAlias !== alias);
  const transitionBlocked = runtime?.state === "draining"
    || runtime?.state === "unloading"
    || runtime?.state === "loading";
  const cleanupBlocked = runtime?.state === "cleanup_unknown" || runtime?.state === "quarantined";
  const blocked = disabled
    || busy
    || loading
    || runtimeReadFailed
    || anyTurnRunning
    || transitionBlocked
    || cleanupBlocked
    || runtime === null
    || selected === null
    || livePlacementUnavailable
    || selectedPlacement?.state === "blocked";
  const applyDisabled = blocked || (exactSelection && !chatNeedsRebind);
  const stopDisabled = disabled
    || busy
    || anyTurnRunning
    || transitionBlocked
    || cleanupBlocked
    || runtime?.served === null
    || runtime?.served === undefined;
  const applyDisabledReason = disabled
    ? "Model changes are unavailable while this Agent session is disconnected, closing, or awaiting safe cleanup."
    : busy
      ? "Wait for the current model operation to finish."
      : runtimeReadFailed
        ? "Runtime status could not be refreshed. Apply stays disabled; use Refresh to retry the check."
      : loading || runtime === null
        ? "Wait for the shared runtime status to finish loading."
        : anyTurnRunning
          ? "Finish or stop active responses before changing the shared runtime."
          : transitionBlocked
            ? "Wait for the shared runtime transition to settle."
            : cleanupBlocked
              ? "Resolve the unconfirmed runtime cleanup before starting or switching models."
              : selected === null
                ? "Choose an installed model before applying runtime settings."
                : livePlacementUnavailable
                  ? "Wait for verified placement admission or retry its check."
                  : selectedPlacement?.state === "blocked"
                    ? "Choose a placement admitted by the current hardware preflight."
                    : exactSelection && !chatNeedsRebind
                      ? "These model, placement, and context settings are already applied."
                      : "Model settings are temporarily unavailable.";
  const stopDisabledReason = disabled
    ? "Stopping is unavailable while this Agent session is disconnected, closing, or awaiting safe cleanup."
    : busy
      ? "Wait for the current model operation to finish."
      : anyTurnRunning
        ? "Finish or stop active responses before stopping the shared runtime."
        : transitionBlocked
          ? "Wait for the shared runtime transition to settle."
          : cleanupBlocked
            ? "The runtime already has unconfirmed cleanup and cannot be stopped again."
            : "No shared model runtime is currently loaded.";
  // The three selects share one gate pair (an in-flight operation, or a live
  // response that owns the runtime). Describe that gate directly instead of
  // reusing the Apply reason, which can be truthful for Apply and wrong here.
  const selectionDisabled = busy || anyTurnRunning;
  const selectionDisabledReason = operation.current?.kind === "stop"
    ? "A runtime stop is in progress. Model, placement, and context choices reopen when it settles."
    : "A model change is in progress. Model, placement, and context choices reopen when it settles.";
  const selectionDisabledReasonId = !selectionDisabled
    ? undefined
    : busy
      ? "agent-runtime-selection-disabled-reason"
      : "agent-runtime-active-turn-hint";
  const applyDisabledReasonId = !applyDisabled
    ? undefined
    : anyTurnRunning
      ? "agent-runtime-active-turn-hint"
      : transitionBlocked
        ? "agent-runtime-transition-hint"
        : cleanupBlocked
          ? "agent-runtime-cleanup-hint"
          : "agent-runtime-apply-disabled-reason";
  const stopDisabledReasonId = !stopDisabled
    ? undefined
    : anyTurnRunning
      ? "agent-runtime-active-turn-hint"
      : transitionBlocked
        ? "agent-runtime-transition-hint"
        : cleanupBlocked
          ? "agent-runtime-cleanup-hint"
          : "agent-runtime-stop-disabled-reason";

  useEffect(() => {
    if (!available || focusRequestKey < 1) return;
    if (variant === "composer" && composerDetailsRef.current !== null) {
      composerDetailsRef.current.open = true;
    }
    const control = modelSelectRef.current;
    if (control === null) return;
    control.scrollIntoView?.({ block: "nearest" });
    control.focus({ preventScroll: true });
  }, [available, focusRequestKey, variant]);

  const closeComposerDisclosure = useCallback((restoreFocus = false) => {
    const disclosure = composerDetailsRef.current;
    if (disclosure === null || !disclosure.open) return;
    disclosure.open = false;
    settingsDisclosureToggleFromClick.current = false;
    if (restoreFocus) disclosure.querySelector<HTMLElement>("summary")?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    if (variant !== "composer") return;
    const closeFromOutside = (event: PointerEvent) => {
      const disclosure = composerDetailsRef.current;
      if (disclosure === null || !disclosure.open || !(event.target instanceof Node) || disclosure.contains(event.target)) return;
      closeComposerDisclosure(false);
    };
    const closeFromEscape = (event: KeyboardEvent) => {
      const disclosure = composerDetailsRef.current;
      if (event.key !== "Escape" || disclosure?.open !== true) return;
      event.preventDefault();
      event.stopPropagation();
      // Return focus to the summary only when the keyboard user is still inside
      // the popover. After tabbing back out to the composer, Escape must dismiss
      // the popover without pulling focus away from the current field.
      closeComposerDisclosure(disclosure.contains(document.activeElement));
    };
    document.addEventListener("pointerdown", closeFromOutside, true);
    document.addEventListener("keydown", closeFromEscape);
    return () => {
      document.removeEventListener("pointerdown", closeFromOutside, true);
      document.removeEventListener("keydown", closeFromEscape);
    };
  }, [closeComposerDisclosure, variant]);

  function changeModelSelection(nextAlias: string): void {
    runtimeDraftDirty.current = true;
    setAlias(nextAlias);
    onModelSelected(nextAlias);
    setError("");
    setNotice("");
    const record = models?.models.find((model) => model.record.alias === nextAlias);
    if (record && runtime?.served?.alias !== nextAlias) {
      setDevice(record.record.default_device);
      setContextSize(record.record.context_size);
    }
  }

  function isCurrentSettingsRead(request: SettingsReadRequest): boolean {
    return settingsRead.current === request
      && request.lifecycle === lifecycle.current
      && requestContext.current.transport === request.transport
      && requestContext.current.sessionId === request.sessionId
      && settingsIdentity.current === request.key;
  }

  function ownsSettingsRead(request: SettingsReadRequest): boolean {
    return isCurrentSettingsRead(request) && !request.controller.signal.aborted;
  }

  async function loadSettingsCatalog(owner?: RuntimeOperation, propagateFailure = false): Promise<AgentCatalogSession | null> {
    const key = settingsKey;
    // A disclosure can be reopened in the same event turn that replaces the
    // chat. Effects have not necessarily run yet, so make the read boundary
    // own the identity handoff rather than briefly retaining the previous
    // chat's request or catalog.
    const identityChanged = settingsIdentity.current !== key;
    if (identityChanged) {
      settingsIdentity.current = key;
      settingsRead.current?.controller.abort();
      if (settingsRead.current?.timeout != null) window.clearTimeout(settingsRead.current.timeout);
      settingsRead.current = null;
      setSettingsLoading(false);
      setSettingsCatalog(null);
    }
    if (current === null || transport.getAgentCatalogSession === undefined || !identityChanged && settingsLoading || settingsRead.current !== null || (operation.current !== null && operation.current !== owner)) {
      if (propagateFailure) throw new TransportError("Generation settings cannot reload right now", 409);
      return null;
    }
    const sessionId = current.session_id;
    const projectId = current.settings.project_id;
    const request: SettingsReadRequest = {
      controller: new AbortController(),
      key,
      lifecycle: lifecycle.current,
      sessionId,
      transport,
      timeout: null,
    };
    settingsRead.current = request;
    setSettingsLoading(true);
    let timedOut = false;
    const deadline = new Promise<never>((_resolve, reject) => {
      request.timeout = window.setTimeout(() => {
        if (!ownsSettingsRead(request)) return;
        timedOut = true;
        request.controller.abort();
        reject(new TransportError("Generation settings read timed out", 408));
      }, RUNTIME_READ_TIMEOUT_MS);
    });
    try {
      const record = await Promise.race([transport.getAgentCatalogSession(sessionId, request.controller.signal), deadline]);
      if (ownsSettingsRead(request) && record.session_id === sessionId && record.project_id === projectId) {
        setSettingsCatalog(record);
        return record;
      }
      return null;
    } catch (caught) {
      if (isCurrentSettingsRead(request) && (timedOut || !request.controller.signal.aborted)) {
        setError("Generation settings could not load. Retry after the current model operation finishes.");
        if (propagateFailure) throw caught;
      }
      return null;
    } finally {
      if (settingsRead.current === request) {
        if (request.timeout != null) window.clearTimeout(request.timeout);
        settingsRead.current = null;
        setSettingsLoading(false);
      }
    }
  }

  async function saveSettings(parameters: AgentGenerationParameters, expectedParameters: AgentGenerationParameters): Promise<boolean> {
    if (current === null || disabled || current.running || current.closing || current.cleanup_unconfirmed || current.pending_approval_id !== null || current.history_write_failed || settingsCatalog === null || !settingsCatalogReady || transport.updateAgentSessionParameters === undefined || operation.current !== null || settingsLoading) {
      throw new TransportError("Generation settings are not ready to save", 409);
    }
    const key = settingsKey;
    const sessionId = current.session_id;
    const expectedProjectId = settingsCatalog.project_id;
    const expectedRevision = settingsCatalog.revision;
    const request: RuntimeOperation = {
      controller: new AbortController(),
      kind: "settings",
      lifecycle: lifecycle.current,
      transport,
    };
    operation.current = request;
    setBusy(true);
    callbacks.current.onBusyChange(true);
    try {
      const updated = await transport.updateAgentSessionParameters(sessionId, {
        expected_project_id: expectedProjectId,
        expected_revision: expectedRevision,
        expected_parameters: expectedParameters,
        parameters,
      }, request.controller.signal);
      if (!ownsOperation(request) || settingsIdentity.current !== key || requestContext.current.sessionId !== sessionId) return false;
      setSettingsCatalog((previous) => previous === null ? previous : { ...previous, revision: expectedRevision + 1 });
      onSessionUpdated(updated);
      return true;
    } catch (caught) {
      if (ownsOperation(request)) throw caught;
      return false;
    } finally {
      settleOperation(request);
    }
  }

  async function reloadSettings(): Promise<AgentGenerationParameters | null> {
    if (current === null || transport.getAgentSession === undefined || operation.current !== null) {
      throw new TransportError("Generation settings cannot reload right now", 409);
    }
    const key = settingsKey;
    const sessionId = current.session_id;
    const projectId = current.settings.project_id;
    const request: RuntimeOperation = {
      controller: new AbortController(),
      kind: "settings",
      lifecycle: lifecycle.current,
      transport,
    };
    operation.current = request;
    setBusy(true);
    callbacks.current.onBusyChange(true);
    const sessionController = new AbortController();
    const abortSessionRead = () => sessionController.abort();
    request.controller.signal.addEventListener("abort", abortSessionRead, { once: true });
    let timeout: number | null = null;
    try {
      const catalog = await loadSettingsCatalog(request, true);
      if (catalog === null || !ownsOperation(request) || settingsIdentity.current !== key) return null;
      const deadline = new Promise<never>((_resolve, reject) => {
        timeout = window.setTimeout(() => {
          sessionController.abort();
          reject(new TransportError("Generation settings reload timed out", 408));
        }, RUNTIME_READ_TIMEOUT_MS);
      });
      const refreshed = await Promise.race([
        transport.getAgentSession(sessionId, sessionController.signal),
        deadline,
      ]);
      if (
        !ownsOperation(request)
        || sessionController.signal.aborted
        || settingsIdentity.current !== key
        || requestContext.current.sessionId !== sessionId
        || refreshed.session_id !== sessionId
        || refreshed.settings.project_id !== projectId
      ) return null;
      onSessionUpdated(refreshed);
      return refreshed.settings.parameters;
    } catch (caught) {
      if (ownsOperation(request)) {
        if (timeout !== null) window.clearTimeout(timeout);
        if ((caught instanceof TransportError && caught.status === 408) || !sessionController.signal.aborted) {
          setError("Generation settings could not load. Retry after the current model operation finishes.");
          throw caught;
        }
      }
      return null;
    } finally {
      if (timeout !== null) window.clearTimeout(timeout);
      request.controller.signal.removeEventListener("abort", abortSessionRead);
      settleOperation(request);
    }
  }

  function ownsOperation(request: RuntimeOperation): boolean {
    return operation.current === request
      && !request.controller.signal.aborted
      && request.lifecycle === lifecycle.current
      && requestContext.current.transport === request.transport;
  }

  function settleOperation(request: RuntimeOperation): void {
    if (operation.current !== request) return;
    operation.current = null;
    setBusy(false);
    callbacks.current.onBusyChange(false);
    if (contextRefreshDeferred.current) void refreshContext();
  }

  async function applyRuntime(): Promise<void> {
    const requestTransport = transport;
    const switchRuntime = requestTransport.switchLocalRuntime;
    if (
      operation.current !== null
      || blocked
      || switchRuntime === undefined
      || runtime === null
      || selected === null
    ) return;
    if (current !== null && current.settings.parameters.max_tokens >= contextSize) {
      setError("Reduce max output tokens below the selected context limit in Generation settings before applying this runtime.");
      return;
    }
    if (current && (
      requestTransport.getAgentCatalogSession === undefined
      || requestTransport.switchAgentSessionModel === undefined
    )) {
      setError("This runtime cannot safely rebind an existing chat. Open a new chat or update the local app.");
      return;
    }
    const request: RuntimeOperation = {
      controller: new AbortController(),
      kind: "apply",
      lifecycle: lifecycle.current,
      transport: requestTransport,
    };
    const requestedAlias = alias;
    const requestedContextSize = contextSize;
    const requestedDevice = device;
    const requestedModel = selected;
    const runtimeSnapshot = runtime;
    const sessionSnapshot = current;
    const sessionModelSnapshot = currentModelAlias;
    const selectionAlreadyServed = exactSelection;
    if (runtimeRead.current?.timeout != null) window.clearTimeout(runtimeRead.current.timeout);
    runtimeRead.current?.controller.abort();
    runtimeRead.current = null;
    contextRead.current?.controller.abort();
    contextRead.current = null;
    operation.current = request;
    setLoading(false);
    setContextLoading(false);
    setBusy(true);
    callbacks.current.onBusyChange(true);
    setError("");
    setNotice("");
    let switchedRuntime = false;
    try {
      let next = runtimeSnapshot;
      if (!selectionAlreadyServed) {
        next = await switchRuntime({
          alias: requestedAlias,
          expected_revision: runtimeSnapshot.revision,
          device: requestedDevice,
          gpu_layers: requestedDevice === "cpu" ? 0 : null,
          context_size: requestedContextSize,
          remember: true,
          fast_attention: true,
          tool_calling: true,
        }, request.controller.signal);
        if (!ownsOperation(request)) return;
        switchedRuntime = true;
        const previous = runtimeState.current;
        if (previous === null || next.revision >= previous.revision) {
          runtimeState.current = next;
          setRuntime(next);
          setRuntimeReadFailed(false);
          callbacks.current.onRuntimeStatus?.(next);
        }
      }
      if (sessionSnapshot && sessionModelSnapshot !== requestedAlias) {
        const catalog = await requestTransport.getAgentCatalogSession!(
          sessionSnapshot.session_id,
          request.controller.signal,
        );
        if (!ownsOperation(request)) return;
        const updated = await requestTransport.switchAgentSessionModel!(sessionSnapshot.session_id, {
          model_alias: requestedAlias,
          expected_revision: catalog.revision,
        }, request.controller.signal);
        if (!ownsOperation(request)) return;
        onSessionUpdated(updated);
      }
      if (!ownsOperation(request)) return;
      onModelSelected(requestedAlias);
      runtimeDraftDirty.current = false;
      await onModelsRefresh();
      if (!ownsOperation(request)) return;
      await refreshContext(request, true);
      if (!ownsOperation(request)) return;
      const sessionStillCurrent = sessionSnapshot !== null
        && requestContext.current.sessionId === sessionSnapshot.session_id;
      const bindingNotice = sessionSnapshot === null
        ? "New chats can use it."
        : sessionStillCurrent
          ? "This chat is bound to it."
          : "The original chat binding completed; the current chat was not changed.";
      setNotice(
        `${requestedModel.record.display_name} is serving text with requested ${placementLabel(requestedDevice)} placement. Actual tensor offload is not measured. ${bindingNotice}`,
      );
    } catch (caught) {
      if (!ownsOperation(request)) return;
      setError(operationError(caught, switchedRuntime));
      await refresh(request);
      if (!ownsOperation(request)) return;
      await refreshContext(request, true);
      if (!ownsOperation(request)) return;
      await onModelsRefresh();
    } finally {
      settleOperation(request);
    }
  }

  async function stopRuntime(): Promise<void> {
    const requestTransport = transport;
    const stop = requestTransport.stopLocalRuntime;
    const served = runtime?.served;
    if (
      operation.current !== null
      || disabled
      || busy
      || anyTurnRunning
      || transitionBlocked
      || stop === undefined
      || runtime === null
      || served == null
    ) return;
    const request: RuntimeOperation = {
      controller: new AbortController(),
      kind: "stop",
      lifecycle: lifecycle.current,
      transport: requestTransport,
    };
    const runtimeSnapshot = runtime;
    const servedAlias = served.alias;
    if (runtimeRead.current?.timeout != null) window.clearTimeout(runtimeRead.current.timeout);
    runtimeRead.current?.controller.abort();
    runtimeRead.current = null;
    contextRead.current?.controller.abort();
    contextRead.current = null;
    operation.current = request;
    setLoading(false);
    setContextLoading(false);
    setBusy(true);
    callbacks.current.onBusyChange(true);
    setError("");
    setNotice("");
    try {
      const stopped = await stop({
        alias: servedAlias,
        expected_revision: runtimeSnapshot.revision,
      }, request.controller.signal);
      if (!ownsOperation(request)) return;
      const previous = runtimeState.current;
      if (previous === null || stopped.revision >= previous.revision) {
        runtimeState.current = stopped;
        setRuntime(stopped);
        setRuntimeReadFailed(false);
        callbacks.current.onRuntimeStatus?.(stopped);
      }
      await onModelsRefresh();
      if (!ownsOperation(request)) return;
      setNotice("The shared model runtime stopped. Chats remain open; their drafts and messages were not changed.");
    } catch (caught) {
      if (!ownsOperation(request)) return;
      setError(operationError(caught, false));
      await refresh(request);
      if (!ownsOperation(request)) return;
      await onModelsRefresh();
    } finally {
      settleOperation(request);
    }
  }

  if (!available) {
    return (
      <section className={`agent-runtime${variant === "composer" ? " agent-runtime--composer" : ""}`} data-state="unavailable">
        {variant === "composer" && (
          <span aria-live="polite" className="sr-only" data-agent-runtime-announcer="true">
            Model runtime unavailable. Update the local app to use coordinated model and context controls.
          </span>
        )}
        <strong>Model runtime</strong>
        <small>Update the local app to use coordinated placement and context controls here.</small>
      </section>
    );
  }

  const displayedContext = contextLabel(
    runtime,
    sessionContext,
    current !== null,
    contextReadFailed,
    contextLoading,
    contextPendingExpired,
  );
  const displayedContextEvidence = current === null
    ? runtime?.context ?? null
    : sessionContext?.binding_state === "bound"
      ? sessionContext.context
      : null;
  const contextStale = current !== null
    && (contextReadFailed || contextPendingExpired)
    && sessionContext?.binding_state === "bound";
  const contextRefreshing = current !== null && contextLoading && sessionContext !== null;
  const contextPercentage = exactContextPercentage(displayedContextEvidence);
  const contextMeterValue = contextPercentage === null
    ? null
    : Math.min(100, Math.max(0, contextPercentage));
  const displayedContextTone = contextTone(displayedContextEvidence, contextStale || contextRefreshing);
  const contextEvidence = current === null
    ? "Runtime-wide last request"
    : contextPendingExpired
      ? sessionContext?.binding_state === "bound"
        ? `Last confirmed · This chat · turn ${sessionContext.turn_number} · preflight did not settle`
        : "Unresolved for this chat · Refresh to retry"
    : contextLoading && sessionContext === null
      ? "Checking this chat"
      : contextReadFailed && sessionContext === null
      ? "Unavailable for this chat"
      : sessionContext?.binding_state === "bound"
        ? contextStale
          ? `Last confirmed · This chat · turn ${sessionContext.turn_number} · refresh failed`
          : contextRefreshing
            ? `Last confirmed · This chat · turn ${sessionContext.turn_number} · checking latest`
          : `This chat · turn ${sessionContext.turn_number}`
        : "Not measured for this chat";
  const contextMeasurement = contextPendingExpired && displayedContextEvidence === null
    ? "Unknown · preflight did not settle"
    : contextLoading && displayedContextEvidence === null
    ? "Checking"
    : displayedContextEvidence?.state === "known"
      ? contextStale
        ? "Exact runtime preflight · stale"
        : contextRefreshing ? "Exact runtime preflight · checking latest" : "Exact runtime preflight"
      : displayedContextEvidence !== null
        ? "Unknown · no estimate"
        : current !== null && sessionContext?.binding_state === "unmeasured"
          ? "Not measured · no estimate"
          : "Unknown · no estimate";
  const contextAdmission = current === null
    ? runtime?.context.policy.replaceAll("_", " ") ?? "unknown"
    : contextPendingExpired
      ? "unresolved"
    : contextLoading && sessionContext === null
      ? "checking"
      : contextReadFailed && sessionContext === null
        ? "unavailable"
      : sessionContext?.binding_state === "bound"
        ? sessionContext.context?.policy.replaceAll("_", " ") ?? "unknown"
        : "not measured for this chat";
  const contextMessages: Array<{ role?: "alert" | "status"; text: string }> = [];
  const contextFailureMessage = "Context evidence could not be refreshed. It remains unknown; use Refresh to retry.";
  const contextExpiryMessage = sessionContext?.binding_state === "bound"
    ? "Showing last-confirmed context evidence because the latest preflight did not settle within 10 seconds. It is not presented as current; use Refresh to retry."
    : "Exact context preflight did not settle within 10 seconds. Context remains unknown; use Refresh to retry.";
  if (contextPendingExpired) {
    contextMessages.push({ role: "status", text: contextExpiryMessage });
  } else if (contextReadFailed && sessionContext === null) {
    contextMessages.push({ role: "status", text: contextFailureMessage });
  } else if (contextStale) {
    contextMessages.push({
      role: "status",
      text: "Showing last-confirmed context evidence because the latest refresh failed. It is not presented as current.",
    });
  } else if (contextRefreshing) {
    contextMessages.push({
      role: "status",
      text: "Showing last-confirmed context evidence while checking the latest receipt.",
    });
  }
  if (displayedContextEvidence?.state === "unknown") {
    contextMessages.push({
      text: "The exact chat-template token count is unavailable. No tokenizer estimate was substituted.",
    });
  } else if (displayedContextEvidence?.policy === "exact_refused") {
    contextMessages.push({
      role: "alert",
      text: "The exact preflight refused this request because it exceeded the context limit.",
    });
  } else if (displayedContextEvidence?.policy === "exact_compacted") {
    const omitted = displayedContextEvidence.compacted_messages;
    contextMessages.push({
      role: "status",
      text: `The exact preflight omitted ${omitted.toLocaleString()} earlier conversation message${omitted === 1 ? "" : "s"} before admission.`,
    });
  } else if (contextPercentage !== null && contextPercentage >= 90) {
    contextMessages.push({
      role: "status",
      text: `Exact input occupies ${contextPercentage}% of the context limit. Start a new chat or reduce input before the next large request.`,
    });
  } else if (contextPercentage !== null && contextPercentage >= 75) {
    contextMessages.push({
      role: "status",
      text: `Exact input occupies ${contextPercentage}% of the context limit. Remaining output capacity is becoming limited.`,
    });
  }
  const composerEvidenceMessages = contextPendingExpired || contextReadFailed && sessionContext === null
    ? []
    : contextMessages;

  const runtimeActionLabel = busy
    ? operation.current?.kind === "stop" ? "Stopping…" : "Applying…"
    : exactSelection && chatNeedsRebind
      ? "Bind this chat"
      : exactSelection
        ? "Applied"
        : runtime?.served
          ? "Switch model"
          : "Start model";
  const compactModelName = selected?.record.display_name
    ?? runtime?.served?.alias
    ?? currentModelAlias
    ?? "Choose a model";
  const compactRuntimeState = loading ? "Checking" : runtimeReadFailed || runtime === null ? "Unavailable" : stateLabel(runtime.state);
  const compactSelectionState = runtimeReadFailed
    ? "Status unverified"
    : runtime?.served && !exactSelection
    ? "Pending change"
    : runtime?.served && chatNeedsRebind
      ? "Chat binding pending"
      : compactRuntimeState;
  const compactContextLabel = contextPendingExpired
    ? contextPercentage !== null
      ? `${contextPercentage}% context · stale · Refresh`
      : "Context unresolved · Refresh to retry"
    : contextReadFailed && sessionContext === null
      ? "Context unavailable · Refresh to retry"
    : contextPercentage !== null
    ? `${contextPercentage}% context${contextStale ? " · stale" : contextRefreshing ? " · checking" : ""}`
    : contextLoading
      ? "Checking context"
      : contextStale
        ? "Context stale · unknown"
        : current !== null && sessionContext?.binding_state === "unmeasured"
          ? "Context unmeasured"
          : "Context unknown";
  const runtimeDecisionState = runtimeReadFailed
    ? "blocked"
    : selected === null
    ? "attention"
    : livePlacementUnavailable
      ? "blocked"
      : exactSelection && !chatNeedsRebind
        ? "current"
        : applyDisabled
          ? "blocked"
          : "ready";
  const runtimeDecisionMessage = runtimeReadFailed
    ? "Runtime status could not be refreshed. Apply stays disabled; use Refresh to retry the check."
    : selected === null
    ? "Choose an installed model. Nothing is loaded until you apply the selection."
    : placementLoading
      ? "Checking verified placement admission. Apply stays disabled until it returns."
      : placementReadFailed
        ? "Placement admission could not be refreshed. Apply stays disabled; use Refresh to retry the check."
      : exactSelection && !chatNeedsRebind
        ? "This chat already uses this model, placement, and context configuration."
        : applyDisabled
          ? applyDisabledReason
          : runtime?.served
            ? "Ready to switch the shared runtime and bind this chat after startup succeeds."
            : "Ready to start this model and bind it to this chat after startup succeeds.";

  if (variant === "composer") {
    return (
      <section
        aria-busy={busy || loading || contextLoading || placementLoading}
        aria-label="Shared local model runtime"
        className="agent-runtime agent-runtime--composer"
        data-state={runtimeReadFailed ? "unavailable" : runtime?.state ?? "loading"}
        id="agent-runtime-controls"
      >
        <span aria-live="polite" className="sr-only" data-agent-runtime-announcer="true">
          {compactModelName}. {compactContextLabel}. {compactSelectionState}.
        </span>
        <details className="agent-runtime__composer-disclosure" onClick={() => {
          if (!composerDetailsRef.current?.open) {
            settingsDisclosureToggleFromClick.current = true;
            void loadSettingsCatalog();
          }
        }} onToggle={(event) => {
          if (!event.currentTarget.open) {
            settingsDisclosureToggleFromClick.current = false;
          } else if (settingsDisclosureToggleFromClick.current) {
            settingsDisclosureToggleFromClick.current = false;
          } else {
            void loadSettingsCatalog();
          }
        }} ref={composerDetailsRef}>
          <summary
            aria-label={`Model and context settings. ${compactModelName}. ${compactContextLabel}. ${compactSelectionState}.`}
            data-context-tone={displayedContextTone}
            data-pending-selection={!matchesRuntimeSnapshot || chatNeedsRebind ? "true" : "false"}
          >
            <span aria-hidden="true" className="agent-runtime__composer-dot" />
            <span className="agent-runtime__composer-model">
              <strong>{compactModelName}</strong>
              <small>{compactSelectionState}</small>
            </span>
            <span className="agent-runtime__composer-context">
              {contextMeterValue !== null && (
                <span aria-hidden="true" className="agent-runtime__composer-context-meter">
                  <span style={{ width: `${contextMeterValue}%` }} />
                </span>
              )}
              <span>{compactContextLabel}</span>
            </span>
            <Icon name="sliders" />
          </summary>

          <div aria-label="Choose model and runtime settings" className="agent-runtime__composer-panel" role="dialog">
            <header className="agent-runtime__head agent-runtime__composer-panel-head">
              <span>
                <small>Chat runtime</small>
                <strong>Choose model &amp; context</strong>
              </span>
              <span className="agent-runtime__composer-panel-actions">
                <span className="agent-runtime__state">Runtime {compactRuntimeState.toLowerCase()}</span>
                <button
                  aria-label="Close model and context settings"
                  className="button button--ghost agent-runtime__composer-close"
                  onClick={() => closeComposerDisclosure(true)}
                  title="Close model and context settings"
                  type="button"
                ><Icon name="x" /></button>
              </span>
            </header>
            <p className="agent-runtime__composer-guidance">
              Choose a model, device placement, and context limit. Nothing changes until Apply succeeds.
            </p>

            <label>
              <span>Model</span>
              <select
                aria-describedby={selectionDisabledReasonId}
                aria-label="Model"
                disabled={selectionDisabled}
                id="agent-runtime-model"
                onChange={(event) => changeModelSelection(event.currentTarget.value)}
                ref={modelSelectRef}
                value={alias}
              >
                <option value="">Choose an installed model</option>
                {(models?.models ?? []).map((model) => (
                  <option key={model.record.alias} value={model.record.alias}>{model.record.display_name}</option>
                ))}
              </select>
            </label>

            <div className="agent-runtime__placement">
              <label>
                <span>Placement</span>
                <select aria-describedby={selectionDisabledReasonId} aria-label="Model placement" disabled={selectionDisabled} onChange={(event) => {
                  runtimeDraftDirty.current = true;
                  setDevice(event.currentTarget.value as DeviceMode);
                }} value={device}>
                  {(["gpu", "split", "cpu"] as const).map((value) => {
                    const option = placementAdmission?.options.find((candidate) => candidate.device === value);
                    return (
                      <option disabled={option?.state === "blocked"} key={value} value={value}>
                        {placementLabel(value)}{option?.state === "blocked" ? " · unavailable" : option?.state === "recheck_required" ? " · recheck after unload" : ""}
                      </option>
                    );
                  })}
                </select>
              </label>
              <label>
                <span>Context limit</span>
                <select aria-describedby={selectionDisabledReasonId} aria-label="Context limit" disabled={selectionDisabled} onChange={(event) => {
                  runtimeDraftDirty.current = true;
                  setContextSize(Number(event.currentTarget.value));
                }} value={contextSize}>
                  {!CONTEXT_OPTIONS.includes(contextSize as (typeof CONTEXT_OPTIONS)[number]) && (
                    <option value={contextSize}>{contextSize.toLocaleString()}</option>
                  )}
                  {CONTEXT_OPTIONS.map((value) => (
                    <option
                      disabled={selected?.record.training_context_size !== null
                        && selected?.record.training_context_size !== undefined
                        && value > selected.record.training_context_size}
                      key={value}
                      value={value}
                    >
                      {Math.round(value / 1024)}K
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {current !== null && settingsParameters !== undefined && (
              <AgentGenerationSettings
                busy={busy || settingsLoading}
                contextLimit={selected !== null ? contextSize : runtime?.served?.context_size ?? null}
                disabled={disabled || current.closing || current.running || current.cleanup_unconfirmed || current.pending_approval_id !== null || current.history_write_failed}
                modelProvided={selected !== null || currentModelAlias !== null}
                onSave={saveSettings}
                onReload={reloadSettings}
                parameters={settingsParameters}
                saveReady={settingsCatalogReady}
                key={settingsKey}
                retentionNote={current.settings.retention_policy === "local_history" ? "These settings are saved with this locally retained chat." : "These settings apply to this run only and are not retained after restart."}
              />
            )}

            <p className="agent-runtime__decision-note" data-state={runtimeDecisionState}>
              <Icon name="info" />
              <span>{runtimeDecisionMessage}</span>
            </p>
            {(contextPendingExpired || contextReadFailed && sessionContext === null) && (
              <p className="agent-runtime__context-note" role="status">
                {contextPendingExpired ? contextExpiryMessage : contextFailureMessage}
              </p>
            )}

            <div className="agent-runtime__actions agent-runtime__composer-actions">
              <button
                aria-describedby={applyDisabledReasonId}
                className="button button--primary"
                disabled={applyDisabled}
                onClick={() => void applyRuntime()}
                type="button"
              >{runtimeActionLabel}</button>
              <button className="button button--ghost" disabled={busy || loading} onClick={() => {
                setPlacementRefreshKey((value) => value + 1);
                void refresh();
                void refreshContext(undefined, true);
              }} type="button">Refresh</button>
              <button
                aria-describedby={stopDisabledReasonId}
                className="button button--ghost"
                disabled={stopDisabled}
                onClick={() => void stopRuntime()}
                type="button"
              >Stop runtime</button>
            </div>

            <details className="agent-runtime__composer-evidence">
              <summary><span>Context, compatibility &amp; runtime evidence</span>{runtimeReadFailed && <small> · last confirmed</small>}</summary>
              <div className="agent-runtime__composer-evidence-body">
                <p className="agent-runtime__placement-note" data-state={selectedPlacement?.state ?? "unknown"}>
                  {placementLoading
                    ? "Checking current placement admission…"
                    : placementReadFailed
                      ? "Placement admission could not be refreshed; Apply stays disabled."
                      : selectedPlacement
                        ? `${placementReasonLabel(selectedPlacement.reason_code)}${selectedPlacement.recommended_gpu_layers != null && selectedPlacement.recommended_gpu_layers > 0 ? ` Recommended maximum: ${selectedPlacement.recommended_gpu_layers} GPU layers.` : ""} Actual tensor offload is not measured.`
                        : selected !== null
                          ? "Placement evidence is unavailable; Apply stays disabled. Refresh models or retry the placement check."
                          : "Choose a model to check placement admission."}
                  {blockedPlacementSummary ? ` ${blockedPlacementSummary}` : ""}
                </p>

                <div className="agent-runtime__context-card" data-tone={displayedContextTone}>
                  <p className="agent-runtime__context">
                    <span>Context use</span>
                    <strong>{displayedContext}</strong>
                  </p>
                  {contextMeterValue !== null && (
                    <div
                      aria-label="Exact context use"
                      aria-valuemax={100}
                      aria-valuemin={0}
                      aria-valuenow={contextMeterValue}
                      aria-valuetext={`${contextPercentage}% exact input utilization · ${displayedContextEvidence?.policy.replaceAll("_", " ")}`}
                      className="agent-runtime__context-meter"
                      data-tone={displayedContextTone}
                      role="progressbar"
                    >
                      <span style={{ width: `${contextMeterValue}%` }} />
                    </div>
                  )}
                  {composerEvidenceMessages.map((message, index) => (
                    <p className="agent-runtime__context-note" key={`${message.text}-${index}`} role={message.role}>{message.text}</p>
                  ))}
                </div>

                <details className="agent-runtime__details">
                  <summary>Runtime evidence &amp; capabilities</summary>
                  <div className="agent-runtime__details-body">
                    <dl className="agent-runtime__facts">
                      <div><dt>Requested</dt><dd>{runtime?.requested?.alias ?? "None"}</dd></div>
                      <div><dt>Served</dt><dd>{runtime?.served?.alias ?? "None"}</dd></div>
                      <div><dt>Context</dt><dd>{displayedContext}</dd></div>
                      <div><dt>Evidence</dt><dd>{contextEvidence}</dd></div>
                      <div><dt>Measurement</dt><dd>{contextMeasurement}</dd></div>
                      <div><dt>Admission</dt><dd>{contextAdmission}</dd></div>
                      <div><dt>Placement request</dt><dd>{runtime?.served ? placementLabel(runtime.served.device) : "None"}</dd></div>
                      <div><dt>Offload evidence</dt><dd>Not measured · runtime arguments only</dd></div>
                      <div><dt>Cleanup</dt><dd>{runtime?.cleanup.state.replaceAll("_", " ") ?? "unknown"}</dd></div>
                    </dl>
                    <div className="agent-runtime__capabilities" aria-label="Model capability status">
                      <span data-supported={runtime?.capabilities.text ? "true" : "false"}>Text {runtime?.capabilities.text ? "verified" : "unverified"}</span>
                      <span data-supported={runtime?.capabilities.tools ? "true" : "false"}>Tools {runtime?.capabilities.tools ? "configured" : "not verified"}</span>
                      <span data-supported={runtime?.capabilities.vision ? "true" : "false"}>Vision {runtime?.capabilities.vision ? "verified" : "not verified"}</span>
                      <span data-supported={runtime?.capabilities.audio ? "true" : "false"}>Audio {runtime?.capabilities.audio ? "verified · experimental" : "not verified"}</span>
                      <span data-supported={runtime?.capabilities.recording ? "true" : "false"}>Microphone {runtime?.capabilities.recording ? "eligible in supported windows" : "not verified"}</span>
                    </div>
                  </div>
                </details>
              </div>
            </details>
            {selectionDisabledReasonId === "agent-runtime-selection-disabled-reason" && <span className="sr-only" id="agent-runtime-selection-disabled-reason">{selectionDisabledReason}</span>}
            {applyDisabledReasonId === "agent-runtime-apply-disabled-reason" && <span className="sr-only" id="agent-runtime-apply-disabled-reason">{applyDisabledReason}</span>}
            {stopDisabledReasonId === "agent-runtime-stop-disabled-reason" && <span className="sr-only" id="agent-runtime-stop-disabled-reason">{stopDisabledReason}</span>}
            {anyTurnRunning && <p className="agent-runtime__hint" id="agent-runtime-active-turn-hint">Finish or stop active responses before changing the shared runtime.</p>}
            {transitionBlocked && <p className="agent-runtime__hint" id="agent-runtime-transition-hint">Wait for the shared runtime transition to settle before starting another model operation.</p>}
            {cleanupBlocked && <p className="agent-runtime__hint" id="agent-runtime-cleanup-hint">Runtime cleanup is unconfirmed. Starting or switching stays disabled until cleanup is resolved.</p>}
            {runtime?.active_requests ? <p className="agent-runtime__hint">{runtime.active_requests} runtime request active.</p> : null}
            {runtimeReadFailed && runtime?.served && <p className="agent-runtime__hint">Runtime status is unavailable. Stop will target the last confirmed {runtime.served.alias} runtime at revision {runtime.revision}; the local service will verify it again.</p>}
            {runtimeReadFailed && <p className="agent-runtime__error" role="alert">Runtime status is unavailable. Retry after the local service reconnects.</p>}
            {error && <p className="agent-runtime__error" role="alert">{error}</p>}
            {notice && <p className="agent-runtime__notice" role="status">{notice}</p>}
          </div>
        </details>
      </section>
    );
  }

  return (
    <section aria-busy={busy || loading || contextLoading || placementLoading} aria-label="Shared local model runtime" className="agent-runtime" data-state={runtimeReadFailed ? "unavailable" : runtime?.state ?? "loading"} id="agent-runtime-controls">
      <header className="agent-runtime__head">
        <span>
          <small>Shared runtime</small>
          <strong>Model &amp; context</strong>
        </span>
        <span className="agent-runtime__state">{loading ? "Checking" : runtimeReadFailed || runtime === null ? "Unavailable" : stateLabel(runtime.state)}</span>
      </header>

      <label>
        <span>Model</span>
        <select
          aria-describedby={selectionDisabledReasonId}
          id="agent-runtime-model"
          disabled={selectionDisabled}
          onChange={(event) => changeModelSelection(event.currentTarget.value)}
          ref={modelSelectRef}
          value={alias}
        >
          <option value="">Choose an installed model</option>
          {(models?.models ?? []).map((model) => (
            <option key={model.record.alias} value={model.record.alias}>{model.record.display_name}</option>
          ))}
        </select>
      </label>

      <div className="agent-runtime__placement">
        <label>
          <span>Placement</span>
          <select aria-describedby={selectionDisabledReasonId} disabled={selectionDisabled} onChange={(event) => {
            runtimeDraftDirty.current = true;
            setDevice(event.currentTarget.value as DeviceMode);
          }} value={device}>
            {(["gpu", "split", "cpu"] as const).map((value) => {
              const option = placementAdmission?.options.find((candidate) => candidate.device === value);
              return (
                <option disabled={option?.state === "blocked"} key={value} value={value}>
                  {placementLabel(value)}{option?.state === "blocked" ? " · unavailable" : option?.state === "recheck_required" ? " · recheck after unload" : ""}
                </option>
              );
            })}
          </select>
        </label>
        <label>
          <span>Context limit</span>
          <select aria-describedby={selectionDisabledReasonId} disabled={selectionDisabled} onChange={(event) => {
            runtimeDraftDirty.current = true;
            setContextSize(Number(event.currentTarget.value));
          }} value={contextSize}>
            {!CONTEXT_OPTIONS.includes(contextSize as (typeof CONTEXT_OPTIONS)[number]) && (
              <option value={contextSize}>{contextSize.toLocaleString()}</option>
            )}
            {CONTEXT_OPTIONS.map((value) => (
              <option
                disabled={selected?.record.training_context_size !== null
                  && selected?.record.training_context_size !== undefined
                  && value > selected.record.training_context_size}
                key={value}
                value={value}
              >
                {Math.round(value / 1024)}K
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="agent-runtime__placement-note" data-state={selectedPlacement?.state ?? "unknown"}>
        {placementLoading
          ? "Checking current placement admission…"
          : placementReadFailed
            ? "Placement admission could not be refreshed; Apply stays disabled."
            : selectedPlacement
              ? `${placementReasonLabel(selectedPlacement.reason_code)}${selectedPlacement.recommended_gpu_layers != null && selectedPlacement.recommended_gpu_layers > 0 ? ` Recommended maximum: ${selectedPlacement.recommended_gpu_layers} GPU layers.` : ""} Actual tensor offload is not measured.`
              : selected !== null
                ? "Placement evidence is unavailable; Apply stays disabled. Refresh models or retry the placement check."
                : "Choose a model to check placement admission."}
        {blockedPlacementSummary ? ` ${blockedPlacementSummary}` : ""}
      </p>

      <div className="agent-runtime__context-card" data-tone={displayedContextTone}>
        <p className="agent-runtime__context">
          <span>Context use</span>
          <strong>{displayedContext}</strong>
        </p>
        {contextMeterValue !== null && (
          <div
            aria-label="Exact context use"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={contextMeterValue}
            aria-valuetext={`${contextPercentage}% exact input utilization · ${displayedContextEvidence?.policy.replaceAll("_", " ")}`}
            className="agent-runtime__context-meter"
            data-tone={displayedContextTone}
            role="progressbar"
          >
            <span style={{ width: `${contextMeterValue}%` }} />
          </div>
        )}
        {contextMessages.map((message, index) => (
          <p className="agent-runtime__context-note" key={`${message.text}-${index}`} role={message.role}>{message.text}</p>
        ))}
      </div>

      <details className="agent-runtime__details">
          <summary><span>Runtime details</span>{runtimeReadFailed && <small> · last confirmed</small>}</summary>
        <div className="agent-runtime__details-body">
          <dl className="agent-runtime__facts">
            <div><dt>Requested</dt><dd>{runtime?.requested?.alias ?? "None"}</dd></div>
            <div><dt>Served</dt><dd>{runtime?.served?.alias ?? "None"}</dd></div>
            <div><dt>Context</dt><dd>{displayedContext}</dd></div>
            <div><dt>Evidence</dt><dd>{contextEvidence}</dd></div>
            <div><dt>Measurement</dt><dd>{contextMeasurement}</dd></div>
            <div><dt>Admission</dt><dd>{contextAdmission}</dd></div>
            <div><dt>Placement request</dt><dd>{runtime?.served ? placementLabel(runtime.served.device) : "None"}</dd></div>
            <div><dt>Offload evidence</dt><dd>Not measured · runtime arguments only</dd></div>
            <div><dt>Cleanup</dt><dd>{runtime?.cleanup.state.replaceAll("_", " ") ?? "unknown"}</dd></div>
          </dl>

          <div className="agent-runtime__capabilities" aria-label="Model capability status">
            <span data-supported={runtime?.capabilities.text ? "true" : "false"}>Text {runtime?.capabilities.text ? "verified" : "unverified"}</span>
            <span data-supported={runtime?.capabilities.tools ? "true" : "false"}>Tools {runtime?.capabilities.tools ? "configured" : "not verified"}</span>
            <span data-supported={runtime?.capabilities.vision ? "true" : "false"}>Vision {runtime?.capabilities.vision ? "verified" : "not verified"}</span>
            <span data-supported={runtime?.capabilities.audio ? "true" : "false"}>Audio {runtime?.capabilities.audio ? "verified · experimental" : "not verified"}</span>
            <span data-supported={runtime?.capabilities.recording ? "true" : "false"}>Microphone {runtime?.capabilities.recording ? "eligible in supported windows" : "not verified"}</span>
          </div>
        </div>
      </details>

      <div className="agent-runtime__actions">
        <button
          aria-describedby={applyDisabledReasonId}
          className="button button--primary"
          disabled={applyDisabled}
          onClick={() => void applyRuntime()}
          type="button"
        >
          {runtimeActionLabel}
        </button>
        <button
          aria-describedby={stopDisabledReasonId}
          className="button button--ghost"
          disabled={stopDisabled}
          onClick={() => void stopRuntime()}
          type="button"
        >Stop</button>
        <button className="button button--ghost" disabled={busy || loading} onClick={() => {
          setPlacementRefreshKey((value) => value + 1);
          void refresh();
          void refreshContext(undefined, true);
        }} type="button">Refresh</button>
      </div>
      {selectionDisabledReasonId === "agent-runtime-selection-disabled-reason" && <span className="sr-only" id="agent-runtime-selection-disabled-reason">{selectionDisabledReason}</span>}
      {applyDisabledReasonId === "agent-runtime-apply-disabled-reason" && <span className="sr-only" id="agent-runtime-apply-disabled-reason">{applyDisabledReason}</span>}
      {stopDisabledReasonId === "agent-runtime-stop-disabled-reason" && <span className="sr-only" id="agent-runtime-stop-disabled-reason">{stopDisabledReason}</span>}

      {anyTurnRunning && <p className="agent-runtime__hint" id="agent-runtime-active-turn-hint">Finish or stop active responses before changing the shared runtime.</p>}
      {transitionBlocked && <p className="agent-runtime__hint" id="agent-runtime-transition-hint">Wait for the shared runtime transition to settle before starting another model operation.</p>}
      {cleanupBlocked && <p className="agent-runtime__hint" id="agent-runtime-cleanup-hint">Runtime cleanup is unconfirmed. Starting or switching stays disabled until cleanup is resolved.</p>}
      {runtime?.active_requests ? <p className="agent-runtime__hint">{runtime.active_requests} runtime request active.</p> : null}
      {runtimeReadFailed && runtime?.served && <p className="agent-runtime__hint">Runtime status is unavailable. Stop will target the last confirmed {runtime.served.alias} runtime at revision {runtime.revision}; the local service will verify it again.</p>}
      {runtimeReadFailed && <p className="agent-runtime__error" role="alert">Runtime status is unavailable. Retry after the local service reconnects.</p>}
      {error && <p className="agent-runtime__error" role="alert">{error}</p>}
      {notice && <p className="agent-runtime__notice" role="status">{notice}</p>}
    </section>
  );
}
