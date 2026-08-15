import { useEffect, useMemo, useRef, useState } from "react";
import type {
  CodexSession,
  ModelEnsembleWatchSnapshot,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import type { MetricCategory } from "../../shared/platform/platform";
import { QUALITY_ANALYSIS_DEFINITIONS } from "../quality-profile/qualityProfile";
import {
  ModelEnsembleRadar,
  modelEnsembleMetricPresentation,
} from "./ModelEnsembleRadar";

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
  const [category, setCategory] = useState<MetricCategory>("prompt-quality");
  const [disconnected, setDisconnected] = useState(false);
  const [sessions, setSessions] = useState<CodexSession[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [scopeError, setScopeError] = useState("");
  const [projectId, setProjectId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [catalogWindow, setCatalogWindow] = useState<CatalogWindow>("all");
  const [maxMessages, setMaxMessages] = useState(100);
  const [watchChanging, setWatchChanging] = useState(false);
  const [nativeHost, setNativeHost] = useState(() => desktopWindowApi() !== null);
  const [maximized, setMaximized] = useState(false);
  const synchronizedWatch = useRef("");

  useEffect(() => {
    const ready = () => setNativeHost(desktopWindowApi() !== null);
    window.addEventListener("pywebviewready", ready);
    ready();
    return () => window.removeEventListener("pywebviewready", ready);
  }, []);

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

  useEffect(() => {
    if (transport.getActiveModelEnsembleWatch === undefined) {
      setDisconnected(true);
      return;
    }
    let stopped = false;
    let timer: number | undefined;
    let controller: AbortController | null = null;
    const poll = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const value = await transport.getActiveModelEnsembleWatch!(controller.signal);
        if (stopped) return;
        setSnapshot(value);
        setDisconnected(false);
        timer = window.setTimeout(
          () => void poll(),
          value.watch.state === "running" || value.watch.state === "queued" ? 2_000 : 15_000,
        );
      } catch (error) {
        if (stopped || controller.signal.aborted) return;
        if (statusOf(error) === 404) {
          setSnapshot(null);
          setDisconnected(false);
          timer = window.setTimeout(() => void poll(), 15_000);
        } else {
          setDisconnected(true);
          timer = window.setTimeout(() => void poll(), 5_000);
        }
      }
    };
    const visible = () => {
      if (document.visibilityState === "visible") void poll();
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

  const selected = useMemo(() => {
    if (snapshot?.latest_run === null || snapshot === null) return [];
    const kind = category === "prompt-quality" ? "prompt" : "logic";
    const definitions = new Map(
      QUALITY_ANALYSIS_DEFINITIONS.filter((item) => item.kind === kind)
        .map((item) => [item.key, item]),
    );
    return snapshot.latest_run.metrics
      .filter((metric) => definitions.has(metric.metric_key))
      .map((metric) => ({ metric, definition: definitions.get(metric.metric_key)! }));
  }, [category, snapshot]);

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

  async function changeWatch() {
    if (watchChanging || sessionId === "" || projectId === "") return;
    setWatchChanging(true);
    setScopeError("");
    try {
      if (activeForSelection && snapshot !== null) {
        if (transport.disableModelEnsembleWatch === undefined) throw new Error("unavailable");
        await transport.disableModelEnsembleWatch(snapshot.watch.watch_id);
        synchronizedWatch.current = "";
        setSnapshot(null);
      } else {
        if (transport.enableModelEnsembleWatch === undefined) throw new Error("unavailable");
        const next = await transport.enableModelEnsembleWatch(sessionId, {
          project_id: projectId,
          max_messages: maxMessages,
          confirmation: "continuously_analyze_selected_redacted_session",
        });
        setSnapshot(next);
      }
    } catch {
      setScopeError("The live watch could not be changed. No session content was retained.");
    } finally {
      setWatchChanging(false);
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
          <p className="eyebrow">Continuous local ensemble</p>
          <h1>Live metric watch</h1>
        </div>
        <span className={`model-ensemble-overlay__connection${disconnected ? " is-stale" : ""}`}>
          {disconnected ? "Disconnected · retaining last receipt" : snapshot?.watch.state ?? "No active watch"}
        </span>
      </header>
      <section aria-label="Live watch scope" className="model-ensemble-overlay__scope">
        <div className="model-ensemble-overlay__scope-title">
          <strong>Watch scope</strong>
          <span>Newest indexed catalog page · up to 100 sessions</span>
        </div>
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
              {[10, 25, 50, 100].map((count) => <option key={count} value={count}>Newest {count} messages</option>)}
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
      </section>
      {snapshot === null ? (
        <section className="model-ensemble__empty" role="status">
          No live watch is active. Choose a project, session, and message window above;
          reading starts only after you explicitly enable it.
        </section>
      ) : (
        <>
          <section className="model-ensemble-overlay__progress" aria-live="polite">
            <strong>
              {snapshot.watch.state === "running"
                ? `Model ${snapshot.watch.progress_completed} of ${snapshot.watch.progress_total}`
                : snapshot.watch.state === "queued" ? "Update queued" : "Latest observed snapshot"}
            </strong>
            <span>Newest {snapshot.watch.max_messages} messages · generation {snapshot.watch.generation} · serial local lane</span>
            <progress max={snapshot.watch.progress_total} value={snapshot.watch.progress_completed} />
          </section>
          <div className="model-ensemble-overlay__tabs" role="group" aria-label="Radar lens">
            <button aria-pressed={category === "prompt-quality"} onClick={() => setCategory("prompt-quality")} type="button">Prompt</button>
            <button aria-pressed={category === "reasoning"} onClick={() => setCategory("reasoning")} type="button">Reasoning</button>
          </div>
          {snapshot.latest_run === null ? (
            <p className="model-ensemble__empty">The first ten-model update has not completed yet.</p>
          ) : (
            <>
              <ModelEnsembleRadar category={category} compact run={snapshot.latest_run} />
              <section aria-label="Metric states" className="model-ensemble-overlay__metrics">
                {selected.map(({ metric, definition }) => {
                  const presentation = modelEnsembleMetricPresentation(metric, definition.direction);
                  return (
                    <article key={metric.metric_key}>
                      <div><strong>{definition.shortLabel}</strong><span>{metric.value_state.replaceAll("_", " ")}</span></div>
                      <b>{presentation.value}</b>
                      <small>{presentation.detail}</small>
                      <small>known {metric.known_chunk_count}/{metric.total_chunk_count} · abstained {metric.abstained_chunk_count} · unsupported {metric.unsupported_chunk_count}</small>
                    </article>
                  );
                })}
              </section>
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
      <footer>Uncalibrated committee evidence · no text persisted · blocking work is not forcibly preempted</footer>
    </main>
  );
}
