import { useEffect, useMemo, useState } from "react";
import type { PromptEnhancerTransport, SessionCatalogItem } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import type { AppRoute } from "../../shared/platform/platform";
import { routePath } from "../../shared/platform/platform";
import { ProviderBadge } from "../../shared/ui/ProviderBadge";
import { ProjectTimelinePane } from "../project-timeline/ProjectTimelinePane";
import { SessionTimelinePane } from "../session-timeline/SessionTimelinePane";
import "./LiveMiniWindow.css";

export const LIVE_REFRESH_SECONDS = 20;

type LiveTransport = Pick<
  PromptEnhancerTransport,
  "getProjectTimeline" | "getSessionTimeline" | "listProjectSessions" | "getLatestSessionQualityAnalysis" | "getLatestSessionAnalysisJob"
>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Opens (or focuses) a small browser window for one project or session; several can be open at once. */
export function openLiveWindow(route: Extract<AppRoute, { name: "live" }>): Window | null {
  const name = `pe-live-${route.projectId.slice(0, 12)}-${route.sessionId ? route.sessionId.slice(0, 12) : "project"}`;
  const features = "popup=yes,width=480,height=760,resizable=yes,scrollbars=yes";
  try {
    return window.open(routePath(route), name, features);
  } catch {
    return null;
  }
}

function summarizeRun(value: unknown): { status: string; known: number; total: number; firstPass: string | null } | null {
  if (!isRecord(value) || !isRecord(value.run) || !Array.isArray(value.results)) return null;
  const results = value.results.filter(isRecord);
  const known = results.filter((row) => row.value_state === "known").length;
  const fp = results.find((row) => row.key === "outcome.first_pass_verification");
  let firstPass: string | null = null;
  if (fp) {
    const fraction = isRecord(fp.fraction) ? fp.fraction : null;
    firstPass = fp.value_state === "known" && fraction
      ? `${String(fraction.numerator)}/${String(fraction.denominator)}`
      : String(fp.value_state ?? "unknown").replace("_", " ");
  }
  return { status: String(value.run.status ?? "unknown"), known, total: results.length, firstPass };
}

/**
 * Compact live view of one project or session: name, provider, the
 * deterministic timeline, the latest automatic analysis and job state.
 * Refreshes itself; meant to live in its own small window next to your work.
 */
export function LiveMiniWindow({
  projectId,
  sessionId,
  transport,
}: {
  projectId: string;
  sessionId?: string;
  transport: LiveTransport;
}) {
  const [tick, setTick] = useState(0);
  const [session, setSession] = useState<SessionCatalogItem | null>(null);
  const [projectName, setProjectName] = useState<string>("");
  const [run, setRun] = useState<ReturnType<typeof summarizeRun>>(null);
  const [job, setJob] = useState<string>("");
  const [paused, setPaused] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    if (paused) return;
    const handle = window.setInterval(() => setTick((value) => value + 1), LIVE_REFRESH_SECONDS * 1000);
    return () => window.clearInterval(handle);
  }, [paused]);

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const page = await transport.listProjectSessions(projectId, 100, 0, controller.signal);
        if (controller.signal.aborted) return;
        const sessions = isRecord(page) && Array.isArray(page.sessions) ? (page.sessions as SessionCatalogItem[]) : [];
        const current = sessionId ? sessions.find((item) => item.session_id === sessionId) ?? null : null;
        setSession(current);
        const named = sessions.find((item) => item.project_display_name);
        setProjectName(named?.project_display_name ?? "");
        if (sessionId) {
          const [latestRun, latestJob] = await Promise.allSettled([
            transport.getLatestSessionQualityAnalysis(sessionId, controller.signal),
            transport.getLatestSessionAnalysisJob(sessionId, controller.signal),
          ]);
          if (controller.signal.aborted) return;
          setRun(latestRun.status === "fulfilled" ? summarizeRun(latestRun.value) : null);
          if (latestJob.status === "fulfilled" && isRecord(latestJob.value)) {
            setJob(String(latestJob.value.state ?? ""));
          } else {
            setJob(latestJob.status === "rejected" && latestJob.reason instanceof TransportError && latestJob.reason.status === 404 ? "none" : "");
          }
        }
        setUpdatedAt(new Date());
      } catch {
        /* keep the last good view; the timestamp shows staleness */
      }
    })();
    return () => controller.abort();
  }, [projectId, sessionId, tick, transport]);

  const title = useMemo(() => {
    if (sessionId) return session?.session_display_name?.trim() || `Session ${sessionId.slice(0, 8)}`;
    return projectName || `Project ${projectId.slice(0, 8)}`;
  }, [projectId, projectName, session, sessionId]);

  const dashboardRoute: AppRoute = sessionId
    ? { name: "session_metrics", projectId, sessionId, category: "prompt-quality" }
    : { name: "project_overview", projectId };

  return (
    <section aria-labelledby="live-window-title" className="live-window" data-kind={sessionId ? "session" : "project"}>
      <header className="live-window__head">
        <div className="live-window__title">
          <p className="eyebrow">Live · {sessionId ? "session" : "project"}</p>
          <h1 id="live-window-title">{title}</h1>
          <p className="live-window__sub">
            {session ? <ProviderBadge provider={session.provider} /> : null}
            {sessionId && projectName ? <span>{projectName}</span> : null}
          </p>
        </div>
        <div className="live-window__controls">
          <button className="button button--ghost" onClick={() => setPaused((value) => !value)} type="button">
            {paused ? "Resume" : "Pause"}
          </button>
          <button className="button button--ghost" onClick={() => setTick((value) => value + 1)} type="button">Refresh</button>
          <a className="button button--ghost" href={routePath(dashboardRoute)} rel="opener" target="_blank">Open in dashboard</a>
        </div>
      </header>

      {sessionId && (
        <dl className="live-window__facts">
          <div><dt>Latest analysis</dt><dd>{run ? `${run.status} · ${run.known}/${run.total} known` : "none yet"}</dd></div>
          <div><dt>First-pass verification</dt><dd>{run?.firstPass ?? "—"}</dd></div>
          <div><dt>Analysis job</dt><dd>{job || "—"}</dd></div>
        </dl>
      )}

      <div className="live-window__body" key={`panes-${tick}`}>
        {sessionId
          ? <SessionTimelinePane sessionId={sessionId} transport={transport} />
          : <ProjectTimelinePane projectId={projectId} transport={transport} />}
      </div>

      <footer className="live-window__foot">
        <span aria-live="polite">
          {updatedAt ? `Updated ${updatedAt.toLocaleTimeString()}` : "Loading…"}{paused ? " · paused" : ` · every ${LIVE_REFRESH_SECONDS}s`}
        </span>
        <span>Local only</span>
      </footer>
    </section>
  );
}
