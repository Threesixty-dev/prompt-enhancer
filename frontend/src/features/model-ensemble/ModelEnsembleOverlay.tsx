import { useEffect, useMemo, useRef, useState } from "react";
import type {
  CodexSession,
  ModelEnsembleCanonicalHead,
  ModelEnsembleRun,
  ModelEnsembleTrajectoryPage,
  ModelEnsembleWatchSnapshot,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import {
  type ModelEnsembleLensId,
  type ModelEnsembleRadarData,
} from "./ModelEnsembleRadar";
import {
  MetricWorkspace,
  modelEnsembleTrajectoryRadarData,
} from "./MetricWorkspace";
import {
  MODEL_ENSEMBLE_DEFAULT_MAX_MESSAGES,
  MODEL_ENSEMBLE_MESSAGE_WINDOWS,
} from "./modelEnsembleConstants";

function statusOf(error: unknown): number | null {
  return typeof error === "object" && error !== null && "status" in error
    && typeof error.status === "number"
    ? error.status
    : null;
}

type CatalogWindow = "all" | "7" | "30" | "90";

function sessionDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

function sessionLabel(session: CodexSession): string {
  return `${session.session_display_name ?? "Unnamed session"} · ${sessionDate(session.started_at)}`;
}

function shortTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  }).format(parsed);
}

function snapshotTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  }).format(parsed);
}

function watchFailureCopy(code: string | null): string {
  switch (code) {
    case "source_timeout":
      return "the local source timed out";
    case "provider_unavailable":
    case "provider_protocol_rejected":
      return "the local provider adapter was unavailable";
    case "source_selection_limit":
    case "source_provider_response_limit":
    case "source_thread_structure_limit":
    case "source_preview_window_limit":
    case "source_resource_limit":
      return "the selected source exceeded a bounded adapter limit";
    case "redacted_content_consent_required":
      return "redacted-content consent is no longer active";
    case "provider_compatibility_blocked":
      return "provider compatibility is not verified";
    case "session_not_in_safe_index":
      return "the selected session is no longer in the safe index";
    case "model_ensemble_persistence_failed":
      return "the completed receipt could not be stored";
    case "local_model_ensemble_execution_failed":
    case "model_ensemble_watch_execution_failed":
      return "a local model stage did not complete";
    default:
      return "the previous local update did not complete";
  }
}

function watchStatus(snapshot: ModelEnsembleWatchSnapshot): string {
  switch (snapshot.watch.state) {
    case "queued": return "Waiting for the local model lane";
    case "running": return snapshot.watch.last_error_code === null
      ? `Updating · local pipeline ${snapshot.watch.progress_completed}/${snapshot.watch.progress_total}`
      : `Retrying · local pipeline ${snapshot.watch.progress_completed}/${snapshot.watch.progress_total}`;
    case "failed": return "Update failed · retaining the last valid receipt";
    case "idle": return snapshot.latest_run === null
      ? "Waiting for the first completed receipt"
      : `Up to date · completed ${shortTime(snapshot.latest_run.completed_at)} UTC`;
    default: return "Watch stopped";
  }
}

function watchDetail(snapshot: ModelEnsembleWatchSnapshot): string {
  const prefix = `Newest ${snapshot.watch.max_messages} messages`;
  if (snapshot.watch.state === "running") {
    const retry = snapshot.watch.last_error_code === null
      ? ""
      : ` · retrying after ${watchFailureCopy(snapshot.watch.last_error_code)}`;
    return `${prefix} · stage names are unavailable in this v1 status receipt${retry}`;
  }
  if (snapshot.watch.state === "queued") {
    const retry = snapshot.watch.last_error_code === null
      ? ""
      : ` · retry queued after ${watchFailureCopy(snapshot.watch.last_error_code)}`;
    return `${prefix} · waiting for the serial local model lane${retry}`;
  }
  if (snapshot.watch.state === "failed") {
    return `${prefix} · ${watchFailureCopy(snapshot.watch.last_error_code)} · automatic retry ${shortTime(snapshot.watch.next_check_at)} UTC`;
  }
  return `${prefix} · next observation ${shortTime(snapshot.watch.next_check_at)} UTC · serial local lane`;
}

function canonicalStatus(head: ModelEnsembleCanonicalHead | null, snapshot: ModelEnsembleWatchSnapshot): string {
  const attempt = head?.latest_attempt;
  if (attempt === null || attempt === undefined) return watchStatus(snapshot);
  if (attempt.state === "running") return `Updating · ${attempt.progress_completed}/${attempt.progress_total} pipeline steps`;
  if (snapshot.watch.state === "queued") return "Queued · waiting for the local model lane";
  if (attempt.state === "failed") return "Update failed · retaining the last valid snapshot";
  if (attempt.state === "cancelled") return "Analysis cancelled · last valid snapshot retained";
  if (attempt.state === "partial") return `Updated with ${attempt.warning_count} warning${attempt.warning_count === 1 ? "" : "s"}`;
  return snapshot.latest_run === null ? "Waiting for the first sealed snapshot" : `Up to date · completed ${shortTime(snapshot.latest_run.completed_at)} UTC`;
}

function canonicalDetail(head: ModelEnsembleCanonicalHead | null, snapshot: ModelEnsembleWatchSnapshot): string {
  const attempt = head?.latest_attempt;
  if (attempt?.state === "running") {
    const latestStage = head?.stages.at(-1);
    return latestStage === undefined
      ? "Preparing the first local measurement stage"
      : `Last completed: ${latestStage.stage_key.replaceAll("_", " ")} · ${latestStage.contributed_case_count ?? 0}/${latestStage.evaluated_case_count ?? 0} cases contributed`;
  }
  return watchDetail(snapshot);
}

type DesktopWindowApi = {
  close_window(): Promise<void>;
  minimize_window(): Promise<void>;
  toggle_maximize_window(): Promise<boolean>;
};

function desktopWindowApi(): DesktopWindowApi | null {
  const hostWindow = window as typeof window & {
    pywebview?: { api?: Partial<DesktopWindowApi> };
  };
  const api = hostWindow.pywebview?.api;
  return api !== undefined
    && typeof api.close_window === "function"
    && typeof api.minimize_window === "function"
    && typeof api.toggle_maximize_window === "function"
    ? api as DesktopWindowApi
    : null;
}

export function ModelEnsembleOverlay({ transport }: { transport: PromptEnhancerTransport }) {
  const [snapshot, setSnapshot] = useState<ModelEnsembleWatchSnapshot | null>(null);
  const [canonicalHead, setCanonicalHead] = useState<ModelEnsembleCanonicalHead | null>(null);
  const [trajectory, setTrajectory] = useState<ModelEnsembleTrajectoryPage | null>(null);
  const [trajectoryError, setTrajectoryError] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [historicalRun, setHistoricalRun] = useState<ModelEnsembleRun | null>(null);
  const [lensId, setLensId] = useState<ModelEnsembleLensId>("task-framing");
  const [disconnected, setDisconnected] = useState(false);
  const [sessions, setSessions] = useState<CodexSession[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [scopeError, setScopeError] = useState("");
  const [projectId, setProjectId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [catalogWindow, setCatalogWindow] = useState<CatalogWindow>("all");
  const [maxMessages, setMaxMessages] = useState(MODEL_ENSEMBLE_DEFAULT_MAX_MESSAGES);
  const [watchChanging, setWatchChanging] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [scopeExpanded, setScopeExpanded] = useState(true);
  const [nativeHost, setNativeHost] = useState(() => desktopWindowApi() !== null);
  const [maximized, setMaximized] = useState(false);
  const synchronizedWatch = useRef("");
  const followingLive = useRef(true);
  const snapshotRef = useRef<ModelEnsembleWatchSnapshot | null>(null);
  const failedPolls = useRef(0);
  const firstFailedPollAt = useRef<number | null>(null);

  useEffect(() => {
    const ready = () => setNativeHost(desktopWindowApi() !== null);
    window.addEventListener("pywebviewready", ready);
    ready();
    return () => window.removeEventListener("pywebviewready", ready);
  }, []);

  useEffect(() => { snapshotRef.current = snapshot; }, [snapshot]);

  useEffect(() => {
    const controller = new AbortController();
    setCatalogLoading(true);
    transport.listCodexSessions(100, 0, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return;
        setSessions(response.sessions);
        setCatalogError("");
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setCatalogError("The indexed session catalog is unavailable. The current receipt can still be viewed.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setCatalogLoading(false);
      });
    return () => controller.abort();
  }, [transport]);

  const trajectoryWatchId = snapshot?.watch.state === "disabled"
    ? null
    : snapshot?.watch.watch_id ?? null;
  const trajectoryHeadRunId = snapshot?.latest_run?.run_id ?? null;

  useEffect(() => {
    if (trajectoryWatchId === null || transport.getModelEnsembleTrajectory === undefined) {
      setTrajectory(null);
      setTrajectoryError(false);
      setSelectedRunId(null);
      followingLive.current = true;
      return;
    }
    if (followingLive.current && trajectoryHeadRunId !== null) setSelectedRunId(trajectoryHeadRunId);
    const controller = new AbortController();
    transport.getModelEnsembleTrajectory(trajectoryWatchId, 24, undefined, controller.signal)
      .then((page) => {
        if (controller.signal.aborted || page.watch_id !== trajectoryWatchId) return;
        if (page.head_run_id !== trajectoryHeadRunId) {
          setTrajectoryError(page.head_run_id !== null);
          return;
        }
        setTrajectory(page);
        setTrajectoryError(false);
        setSelectedRunId((current) => {
          if (followingLive.current) return page.head_run_id;
          if (current !== null && page.points.some((point) => point.run_id === current)) {
            return current;
          }
          followingLive.current = true;
          return page.head_run_id;
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) setTrajectoryError(true);
      });
    return () => controller.abort();
  }, [trajectoryHeadRunId, trajectoryWatchId, transport]);

  useEffect(() => {
    if (transport.getActiveModelEnsembleCanonicalHead === undefined && transport.getActiveModelEnsembleWatch === undefined) {
      setDisconnected(true);
      return;
    }
    let stopped = false;
    let timer: number | undefined;
    let controller: AbortController | null = null;
    const schedule = (delay: number) => {
      if (timer !== undefined) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        timer = undefined;
        void poll();
      }, delay);
    };
    const poll = async () => {
      if (timer !== undefined) {
        window.clearTimeout(timer);
        timer = undefined;
      }
      controller?.abort();
      const requestController = new AbortController();
      controller = requestController;
      try {
        if (transport.getActiveModelEnsembleCanonicalHead !== undefined && transport.getModelEnsembleSnapshot !== undefined) {
          const head = await transport.getActiveModelEnsembleCanonicalHead(requestController.signal);
          if (stopped || requestController.signal.aborted) return;
          const existingRun = snapshotRef.current?.latest_run ?? null;
          let nextRun = existingRun;
          if (head.head_run_id === null) {
            nextRun = null;
          } else if (existingRun?.run_id !== head.head_run_id) {
            nextRun = await transport.getModelEnsembleSnapshot(head.head_run_id, requestController.signal);
            if (stopped || requestController.signal.aborted || nextRun.run_id !== head.head_run_id) return;
          }
          setCanonicalHead(head);
          setSnapshot({ watch: head.watch, latest_run: nextRun });
          failedPolls.current = 0;
          firstFailedPollAt.current = null;
          setDisconnected(false);
          schedule(head.latest_attempt?.state === "running" || head.watch.state === "queued" ? 2_000 : 15_000);
          return;
        }
        const value = await transport.getActiveModelEnsembleWatch!(requestController.signal);
        if (stopped || requestController.signal.aborted) return;
        setCanonicalHead(null);
        setSnapshot(value);
        failedPolls.current = 0;
        firstFailedPollAt.current = null;
        setDisconnected(false);
        schedule(value.watch.state === "running" || value.watch.state === "queued" ? 2_000 : 15_000);
      } catch (error) {
        if (stopped || requestController.signal.aborted) return;
        if (statusOf(error) === 404) {
          setSnapshot(null);
          setCanonicalHead(null);
          failedPolls.current = 0;
          firstFailedPollAt.current = null;
          setDisconnected(false);
          schedule(15_000);
        } else {
          failedPolls.current += 1;
          firstFailedPollAt.current ??= Date.now();
          if (failedPolls.current >= 3 || Date.now() - firstFailedPollAt.current >= 10_000) {
            setDisconnected(true);
          }
          schedule(5_000);
        }
      }
    };
    const visible = () => {
      if (document.visibilityState === "visible") {
        if (timer !== undefined) window.clearTimeout(timer);
        timer = undefined;
        void poll();
      }
    };
    document.addEventListener("visibilitychange", visible);
    void poll();
    return () => {
      stopped = true;
      controller?.abort();
      if (timer !== undefined) window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [transport]);

  useEffect(() => {
    if (snapshot === null || snapshot.watch.state === "disabled") return;
    const key = `${snapshot.watch.watch_id}:${snapshot.watch.max_messages}`;
    if (synchronizedWatch.current === key) return;
    synchronizedWatch.current = key;
    setProjectId(snapshot.watch.project_id);
    setSessionId(snapshot.watch.session_id);
    setMaxMessages(snapshot.watch.max_messages);
    setScopeExpanded(false);
  }, [snapshot]);

  const filteredSessions = useMemo(() => {
    if (catalogWindow === "all") return sessions;
    const cutoff = Date.now() - Number(catalogWindow) * 24 * 60 * 60 * 1000;
    return sessions.filter((session) => {
      const started = new Date(session.started_at).getTime();
      return Number.isFinite(started) && started >= cutoff;
    });
  }, [catalogWindow, sessions]);

  const projects = useMemo(() => {
    const projectMap = new Map<string, string>();
    for (const session of filteredSessions) {
      if (!projectMap.has(session.project_id)) {
        projectMap.set(session.project_id, session.project_display_name ?? "Unnamed project");
      }
    }
    if (
      snapshot !== null
      && snapshot.watch.state !== "disabled"
      && !projectMap.has(snapshot.watch.project_id)
    ) {
      projectMap.set(snapshot.watch.project_id, "Current watched project");
    }
    return [...projectMap.entries()].map(([id, label]) => ({ id, label }));
  }, [filteredSessions, snapshot]);

  const projectSessions = useMemo(
    () => filteredSessions.filter((session) => session.project_id === projectId),
    [filteredSessions, projectId],
  );

  useEffect(() => {
    const selectionIsActive = snapshot !== null
      && snapshot.watch.state !== "disabled"
      && snapshot.watch.project_id === projectId
      && snapshot.watch.session_id === sessionId;
    if (selectionIsActive) return;
    if (filteredSessions.length === 0) {
      setProjectId("");
      setSessionId("");
      return;
    }
    const selected = filteredSessions.find((session) => session.session_id === sessionId);
    if (selected !== undefined && selected.project_id === projectId) return;
    const nextProject = projects.some((project) => project.id === projectId)
      ? projectId
      : projects[0]?.id ?? "";
    const nextSession = filteredSessions.find((session) => session.project_id === nextProject);
    setProjectId(nextProject);
    setSessionId(nextSession?.session_id ?? "");
  }, [filteredSessions, projectId, projects, sessionId, snapshot]);

  const activeForSelection = snapshot !== null
    && snapshot.watch.state !== "disabled"
    && snapshot.watch.project_id === projectId
    && snapshot.watch.session_id === sessionId
    && snapshot.watch.max_messages === maxMessages;
  const activeForSession = snapshot !== null
    && snapshot.watch.state !== "disabled"
    && snapshot.watch.session_id === sessionId;
  const activeSessionOutsideCatalog = activeForSession
    && !projectSessions.some((session) => session.session_id === sessionId);
  const linkProjectId = projectId || snapshot?.watch.project_id || "";
  const linkSessionId = sessionId || snapshot?.watch.session_id || "";
  const category = lensId === "task-framing" || lensId === "collaboration-flow"
    ? "prompt-quality"
    : "reasoning";
  const visibleTrajectory = trajectory?.watch_id === trajectoryWatchId ? trajectory : null;
  const trajectoryPoints = visibleTrajectory?.points ?? [];
  const selectedPointIndex = trajectoryPoints.findIndex((point) => point.run_id === selectedRunId);
  const selectedPoint = selectedPointIndex < 0 ? null : trajectoryPoints[selectedPointIndex];
  const historicalRunId = selectedPoint !== null && selectedPoint.run_id !== snapshot?.latest_run?.run_id
    ? selectedPoint.run_id
    : null;
  useEffect(() => {
    if (historicalRunId === null || transport.getModelEnsembleSnapshot === undefined) {
      setHistoricalRun(null);
      return;
    }
    const controller = new AbortController();
    setHistoricalRun(null);
    transport.getModelEnsembleSnapshot(historicalRunId, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted && value.run_id === historicalRunId) setHistoricalRun(value);
      })
      .catch(() => { if (!controller.signal.aborted) setHistoricalRun(null); });
    return () => controller.abort();
  }, [historicalRunId, transport]);
  const selectedRadarRun: ModelEnsembleRadarData | null = selectedPoint === null
    ? snapshot?.latest_run ?? null
    : selectedPoint.run_id === snapshot?.latest_run?.run_id
      ? snapshot.latest_run
      : historicalRun?.run_id === selectedPoint.run_id
        ? historicalRun
        : modelEnsembleTrajectoryRadarData(selectedPoint);
  const comparisonPoint = selectedPointIndex >= 0
    ? trajectoryPoints[selectedPointIndex + 1] ?? null
    : null;
  const comparisonRadarRun = selectedPoint !== null
    && comparisonPoint !== null
    && selectedPoint.comparable_to_head
    && comparisonPoint.comparable_to_head
    && selectedPoint.max_messages === comparisonPoint.max_messages
    ? modelEnsembleTrajectoryRadarData(comparisonPoint)
    : null;

  function selectTrajectoryRun(runId: string | null) {
    followingLive.current = runId !== null && runId === trajectoryHeadRunId;
    setSelectedRunId(runId);
  }

  async function changeWatch() {
    if (watchChanging || sessionId === "" || projectId === "") return;
    setWatchChanging(true);
    setScopeError("");
    try {
      if (activeForSelection && snapshot !== null) {
        if (transport.disableModelEnsembleWatch === undefined) throw new Error("unavailable");
        await transport.disableModelEnsembleWatch(snapshot.watch.watch_id);
        synchronizedWatch.current = "";
        followingLive.current = true;
        setSnapshot(null);
        setCanonicalHead(null);
      } else {
        if (transport.enableModelEnsembleWatch === undefined) throw new Error("unavailable");
        const next = await transport.enableModelEnsembleWatch(sessionId, {
          project_id: projectId,
          max_messages: maxMessages,
          confirmation: "continuously_analyze_selected_redacted_session",
        });
        setCanonicalHead(null);
        setSnapshot(next);
        followingLive.current = true;
        setScopeExpanded(false);
      }
    } catch {
      setScopeError("The live watch could not be changed. No session content was retained.");
    } finally {
      setWatchChanging(false);
    }
  }

  async function analyzeNow() {
    if (
      snapshot === null
      || snapshot.watch.state === "disabled"
      || snapshot.watch.state === "queued"
      || snapshot.watch.state === "running"
      || refreshing
    ) return;
    setRefreshing(true);
    setScopeError("");
    try {
      if (transport.enqueueModelEnsembleAnalysis !== undefined) {
        const head = await transport.enqueueModelEnsembleAnalysis(snapshot.watch.watch_id);
        if (
          head.watch.watch_id !== snapshot.watch.watch_id
          || head.watch.session_id !== snapshot.watch.session_id
        ) throw new Error("durable_watch_identity_mismatch");
        let exactRun = snapshot.latest_run;
        if (head.head_run_id === null) {
          exactRun = null;
        } else if (exactRun?.run_id !== head.head_run_id) {
          if (transport.getModelEnsembleSnapshot === undefined) throw new Error("durable_snapshot_unavailable");
          exactRun = await transport.getModelEnsembleSnapshot(head.head_run_id);
          if (exactRun.run_id !== head.head_run_id) throw new Error("durable_snapshot_identity_mismatch");
        }
        setCanonicalHead(head);
        setSnapshot({ watch: head.watch, latest_run: exactRun });
      } else {
        if (transport.refreshModelEnsembleWatch === undefined) throw new Error("unavailable");
        const next = await transport.refreshModelEnsembleWatch(snapshot.watch.watch_id);
        setSnapshot(next);
      }
      followingLive.current = true;
    } catch {
      setScopeError("Analysis could not be queued. The last complete receipt remains visible.");
    } finally {
      setRefreshing(false);
    }
  }

  async function cancelAnalysis() {
    if (snapshot === null || canonicalHead?.latest_attempt?.state !== "running" || refreshing) return;
    setRefreshing(true);
    setScopeError("");
    try {
      if (transport.cancelModelEnsembleAnalysis === undefined) throw new Error("unavailable");
      const next = await transport.cancelModelEnsembleAnalysis(snapshot.watch.watch_id);
      if (
        next.watch.watch_id !== snapshot.watch.watch_id
        || next.watch.session_id !== snapshot.watch.session_id
      ) throw new Error("durable_watch_identity_mismatch");
      let exactRun = snapshot.latest_run;
      if (next.head_run_id === null) {
        exactRun = null;
      } else if (exactRun?.run_id !== next.head_run_id) {
        if (transport.getModelEnsembleSnapshot === undefined) throw new Error("durable_snapshot_unavailable");
        exactRun = await transport.getModelEnsembleSnapshot(next.head_run_id);
        if (exactRun.run_id !== next.head_run_id) throw new Error("durable_snapshot_identity_mismatch");
      }
      setCanonicalHead(next);
      setSnapshot({ watch: next.watch, latest_run: exactRun });
    } catch {
      setScopeError("Cancellation could not be confirmed. The latest sealed snapshot remains visible.");
    } finally {
      setRefreshing(false);
    }
  }

  async function minimizeWindow() {
    try {
      await desktopWindowApi()?.minimize_window();
    } catch {
      setNativeHost(false);
    }
  }

  async function toggleMaximizeWindow() {
    try {
      const next = await desktopWindowApi()?.toggle_maximize_window();
      if (typeof next === "boolean") setMaximized(next);
    } catch {
      setNativeHost(false);
    }
  }

  async function closeWindow() {
    try {
      await desktopWindowApi()?.close_window();
    } catch {
      setNativeHost(false);
    }
  }

  return (
    <main className={`model-ensemble-overlay${nativeHost ? " model-ensemble-overlay--native" : ""}`}>
      <div className="model-ensemble-overlay__chrome" aria-label="Prompt Enhancer window">
        <div
          className="model-ensemble-overlay__drag pywebview-drag-region"
          onDoubleClick={() => void toggleMaximizeWindow()}
        >
          <span aria-hidden="true" className="model-ensemble-overlay__brand-mark">P</span>
          <span className="model-ensemble-overlay__brand-copy">
            <strong>Prompt Enhancer</strong>
            <small>Live intelligence</small>
          </span>
        </div>
        {nativeHost ? (
          <div className="model-ensemble-overlay__window-controls" aria-label="Window controls">
            <button aria-label="Minimize window" onClick={() => void minimizeWindow()} type="button">
              <svg aria-hidden="true" viewBox="0 0 12 12"><path d="M2 8.5h8" /></svg>
            </button>
            <button
              aria-label={maximized ? "Restore window" : "Maximize window"}
              onClick={() => void toggleMaximizeWindow()}
              type="button"
            >
              {maximized
                ? <svg aria-hidden="true" viewBox="0 0 12 12"><path d="M4 2.5h5.5V8M2.5 4H8v5.5H2.5z" /></svg>
                : <svg aria-hidden="true" viewBox="0 0 12 12"><path d="M2.5 2.5h7v7h-7z" /></svg>}
            </button>
            <button aria-label="Close window" className="is-close" onClick={() => void closeWindow()} type="button">
              <svg aria-hidden="true" viewBox="0 0 12 12"><path d="m3 3 6 6m0-6L3 9" /></svg>
            </button>
          </div>
        ) : null}
      </div>
      <header>
        <div>
          <p className="eyebrow">Continuous local measurement</p>
          <h1>Live metric watch</h1>
        </div>
        <span className={`model-ensemble-overlay__connection${disconnected ? " is-stale" : ""}`}>
          {disconnected
            ? "Reconnecting · last receipt retained"
            : snapshot === null ? "No active watch" : canonicalStatus(canonicalHead, snapshot)}
        </span>
      </header>
      <section aria-label="Live watch scope" className="model-ensemble-overlay__scope">
        <div className="model-ensemble-overlay__scope-title">
          <div>
            <strong>Watch scope</strong>
            <span>{snapshot === null ? "Choose one indexed session" : `Newest ${snapshot.watch.max_messages} messages`}</span>
          </div>
          {snapshot !== null ? (
            <button onClick={() => setScopeExpanded((value) => !value)} type="button">
              {scopeExpanded ? "Done" : "Change"}
            </button>
          ) : null}
        </div>
        {snapshot !== null && !scopeExpanded ? (
          <p className="model-ensemble-overlay__scope-summary">
            {projects.find((project) => project.id === snapshot.watch.project_id)?.label ?? "Indexed project"}
            <span>·</span>
            {sessions.find((session) => session.session_id === snapshot.watch.session_id)?.session_display_name ?? "Selected session"}
          </p>
        ) : (
          <>
            <div className="model-ensemble-overlay__scope-grid">
              <label>
                <span>Project</span>
                <select
                  aria-label="Watch project"
                  disabled={catalogLoading || projects.length === 0}
                  onChange={(event) => {
                    const nextProject = event.target.value;
                    setProjectId(nextProject);
                    setSessionId(filteredSessions.find((session) => session.project_id === nextProject)?.session_id ?? "");
                  }}
                  value={projectId}
                >
                  {projects.length === 0 ? <option value="">No indexed projects</option> : null}
                  {projects.map((project) => <option key={project.id} value={project.id}>{project.label}</option>)}
                </select>
              </label>
              <label>
                <span>Session</span>
                <select
                  aria-label="Watch session"
                  disabled={catalogLoading || projectSessions.length === 0}
                  onChange={(event) => setSessionId(event.target.value)}
                  value={sessionId}
                >
                  {projectSessions.length === 0 ? <option value="">No sessions in this filter</option> : null}
                  {activeSessionOutsideCatalog ? <option value={sessionId}>Current watched session · outside catalog page</option> : null}
                  {projectSessions.map((session) => (
                    <option key={session.session_id} value={session.session_id}>{sessionLabel(session)}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Session catalog date</span>
                <select
                  aria-label="Session catalog date"
                  onChange={(event) => setCatalogWindow(event.target.value as CatalogWindow)}
                  value={catalogWindow}
                >
                  <option value="all">All indexed dates</option>
                  <option value="7">Started in last 7 days</option>
                  <option value="30">Started in last 30 days</option>
                  <option value="90">Started in last 90 days</option>
                </select>
              </label>
              <label>
                <span>Analysis window</span>
                <select
                  aria-label="Analysis message window"
                  onChange={(event) => setMaxMessages(Number(event.target.value))}
                  value={maxMessages}
                >
                  {MODEL_ENSEMBLE_MESSAGE_WINDOWS.map((count) => <option key={count} value={count}>Newest {count} messages</option>)}
                </select>
              </label>
            </div>
            <p>
              The date control filters session choices. Analysis reads the newest {maxMessages} messages;
              exact within-session date cutoffs need complete provider timestamps and are not inferred.
            </p>
            {catalogError !== "" ? <p className="model-ensemble-overlay__scope-error" role="alert">{catalogError}</p> : null}
            {scopeError !== "" ? <p className="model-ensemble-overlay__scope-error" role="alert">{scopeError}</p> : null}
            <button
              className="model-ensemble-overlay__watch-button"
              disabled={watchChanging || sessionId === "" || projectId === ""}
              onClick={() => void changeWatch()}
              type="button"
            >
              {watchChanging
                ? "Updating…"
                : activeForSelection
                  ? "Stop this watch"
                  : activeForSession
                    ? "Apply message window"
                    : snapshot === null ? "Watch selected session" : "Switch live watch"}
            </button>
          </>
        )}
      </section>
      {snapshot === null ? (
        <section className="model-ensemble__empty" role="status">
          No live watch is active. Choose a project, session, and message window above;
          reading starts only after you explicitly enable it.
        </section>
      ) : (
        <>
          <section className="model-ensemble-overlay__progress" aria-live="polite">
            <strong>{canonicalStatus(canonicalHead, snapshot)}</strong>
            <span>{canonicalDetail(canonicalHead, snapshot)}</span>
            <progress
              max={canonicalHead?.latest_attempt?.progress_total ?? snapshot.watch.progress_total}
              value={canonicalHead?.latest_attempt?.progress_completed ?? snapshot.watch.progress_completed}
            />
            <button
              className="model-ensemble-overlay__watch-button"
              disabled={refreshing || (
                canonicalHead?.latest_attempt?.state !== "running"
                && (snapshot.watch.state === "queued" || snapshot.watch.state === "running")
              )}
              onClick={() => canonicalHead?.latest_attempt?.state === "running" ? void cancelAnalysis() : void analyzeNow()}
              type="button"
            >
              {refreshing
                ? canonicalHead?.latest_attempt?.state === "running" ? "Cancelling…" : "Queueing analysis…"
                : canonicalHead?.latest_attempt?.state === "running"
                  ? "Cancel analysis"
                  : snapshot.watch.state === "running"
                    ? `Analysis running · ${snapshot.watch.progress_completed}/${snapshot.watch.progress_total}`
                  : snapshot.watch.state === "queued"
                    ? "Analysis queued…"
                    : snapshot.watch.state === "failed" ? "Retry analysis" : "Analyze now"}
            </button>
          </section>
          {snapshot.latest_run === null ? (
            <p className="model-ensemble__empty">The first typed measurement and experimental model range have not completed yet.</p>
          ) : (
            <>
              {trajectoryError ? (
                <p className="model-ensemble-overlay__trajectory-error">Trajectory history is temporarily unavailable; the last live receipt remains visible.</p>
              ) : null}
              {selectedRadarRun !== null ? (
                <MetricWorkspace
                  comparisonLabel="previous comparable publication"
                  comparisonRun={comparisonRadarRun}
                  history={visibleTrajectory === null ? undefined : {
                    points: trajectoryPoints,
                    headRunId: trajectoryHeadRunId ?? visibleTrajectory.head_run_id,
                    selectedRunId: selectedPoint?.run_id ?? snapshot.latest_run.run_id,
                    onSelectRun: selectTrajectoryRun,
                    error: trajectoryError,
                  }}
                  lensId={lensId}
                  mode="compact"
                  onLensChange={setLensId}
                  run={selectedRadarRun}
                  runId={selectedPoint?.run_id ?? snapshot.latest_run.run_id}
                  scopeLabel={`Newest ${selectedPoint?.max_messages ?? snapshot.watch.max_messages} messages`}
                  snapshotLabel={selectedPoint === null
                    ? "Current sealed receipt"
                    : selectedPoint.run_id === visibleTrajectory?.head_run_id
                      ? "Live published head"
                      : "Earlier published snapshot"}
                  stageRun={selectedPoint === null || selectedPoint.run_id === snapshot.latest_run.run_id
                    ? snapshot.latest_run
                    : historicalRun}
                  attemptStages={selectedPoint === null || selectedPoint.run_id === snapshot.latest_run.run_id
                    ? canonicalHead?.stages ?? []
                    : []}
                  transport={transport}
                />
              ) : null}
            </>
          )}
        </>
      )}
      {linkProjectId !== "" && linkSessionId !== "" ? <a
        className="model-ensemble-overlay__open"
        href={`/projects/${linkProjectId}/sessions/${linkSessionId}/metrics/${category}`}
      >
        Open selected session in dashboard
      </a> : null}
      <footer>Typed local metrics + experimental model ranges · no text persisted · blocking work is not forcibly preempted</footer>
    </main>
  );
}
