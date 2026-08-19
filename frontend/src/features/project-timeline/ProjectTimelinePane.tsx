import { useEffect, useMemo, useState } from "react";
import type { ProjectTimeline, PromptEnhancerTransport } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { ProviderBadge } from "../../shared/ui/ProviderBadge";
import "./ProjectTimelinePane.css";

const DAY = 86_400_000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function safeProjectTimeline(value: unknown): value is ProjectTimeline {
  if (!isRecord(value) || value.contract_version !== "project-timeline.v1") return false;
  return typeof value.project_id === "string"
    && Array.isArray(value.sessions) && Array.isArray(value.tasks) && Array.isArray(value.activity) && Array.isArray(value.providers);
}

function formatSpan(ms: number): string {
  const days = ms / DAY;
  if (days < 1) return `${Math.max(1, Math.round(ms / 3_600_000))}h`;
  if (days < 60) return `${Math.round(days)} days`;
  return `${Math.round(days / 30)} months`;
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * Project timeline: reviewed task windows (start → stop) and sessions on one
 * calendar axis, plus activity by day. Everything is from indexed metadata;
 * a click on a session opens it in the session view.
 */
export function ProjectTimelinePane({
  projectId,
  transport,
  onOpenSession,
}: {
  projectId: string;
  transport: Pick<PromptEnhancerTransport, "getProjectTimeline">;
  onOpenSession?: (sessionId: string) => void;
}) {
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">("loading");
  const [timeline, setTimeline] = useState<ProjectTimeline | null>(null);
  const [range, setRange] = useState<"all" | "90d" | "30d">("all");

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    setTimeline(null);
    transport.getProjectTimeline(projectId, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        if (!safeProjectTimeline(value)) { setState("error"); return; }
        setTimeline(value);
        setState("ready");
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setState(caught instanceof TransportError && caught.status === 404 ? "missing" : "error");
      });
    return () => controller.abort();
  }, [projectId, transport]);

  const model = useMemo(() => {
    if (!timeline || timeline.sessions.length === 0) return null;
    const ends = timeline.sessions.map((s) => Date.parse(s.ended_at ?? s.started_at));
    const starts = timeline.sessions.map((s) => Date.parse(s.started_at));
    const fullEnd = Math.max(...ends, ...starts);
    const fullStart = Math.min(...starts);
    const windowStart = range === "all" ? fullStart : Math.max(fullStart, fullEnd - (range === "90d" ? 90 : 30) * DAY);
    const start = windowStart;
    const end = Math.max(fullEnd, start + DAY);
    const span = end - start;
    const x = (iso: string) => Math.min(1, Math.max(0, (Date.parse(iso) - start) / span));
    const visibleSessions = timeline.sessions.filter((s) => Date.parse(s.ended_at ?? s.started_at) >= start);
    const visibleTasks = timeline.tasks.filter((t) => t.ended_at !== null && t.ended_at !== undefined && Date.parse(t.ended_at) >= start);
    const maxActivity = Math.max(1, ...timeline.activity.map((d) => d.sessions));
    return { start, end, span, x, visibleSessions, visibleTasks, maxActivity };
  }, [timeline, range]);

  if (state === "loading") return <section className="project-timeline" aria-busy="true"><p className="project-timeline__note">Drawing the project timeline…</p></section>;
  if (state === "missing") return null;
  if (state === "error" || !timeline || !model) {
    return <section className="project-timeline"><p className="project-timeline__note" role="alert">The project timeline could not be verified.</p></section>;
  }

  const { x, span, visibleSessions, visibleTasks, maxActivity } = model;
  const width = 1000;
  const rowHeight = 14;
  const taskRows = visibleTasks.slice(0, 60);
  const sessionRows = visibleSessions.slice(-120);
  const taskTop = 8;
  const sessionTop = taskTop + taskRows.length * (rowHeight + 4) + 14;
  const activityTop = sessionTop + rowHeight + 4 + 12;
  const activityHeight = 28;
  const height = activityTop + activityHeight + 8;
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <section aria-labelledby="project-timeline-title" className="project-timeline">
      <header className="project-timeline__head">
        <div>
          <p className="eyebrow">Timeline · start and stop of reviewed work</p>
          <h2 id="project-timeline-title">Tasks and sessions over time</h2>
          <p className="project-timeline__lede">
            Each task bar spans its sessions from first start to last stop; sessions are the thin bars beneath;
            the strip at the bottom is sessions per day. Multi-session groupings appear once you accept them.
          </p>
        </div>
        <div className="project-timeline__controls">
          <div className="project-timeline__badges">
            {timeline.providers.map((provider) => <ProviderBadge key={provider} provider={provider} />)}
          </div>
          <div className="project-timeline__range" role="group" aria-label="Time range">
            {(["all", "90d", "30d"] as const).map((value) => (
              <button
                key={value}
                aria-pressed={range === value}
                className={range === value ? "is-active" : ""}
                onClick={() => setRange(value)}
                type="button"
              >
                {value === "all" ? "All" : value === "90d" ? "90 days" : "30 days"}
              </button>
            ))}
          </div>
        </div>
      </header>
      <dl className="project-timeline__stats">
        <div><dt>Span</dt><dd>{formatSpan(span)}</dd></div>
        <div><dt>Tasks</dt><dd>{visibleTasks.length}{timeline.tasks.length !== visibleTasks.length ? ` of ${timeline.tasks.length}` : ""}</dd></div>
        <div><dt>Sessions</dt><dd>{visibleSessions.length}{timeline.truncated ? "+" : ""}</dd></div>
        <div><dt>Active days</dt><dd>{timeline.activity.length}</dd></div>
      </dl>
      <div className="project-timeline__chart" role="img" aria-label={`${visibleTasks.length} task windows and ${visibleSessions.length} sessions over ${formatSpan(span)}`}>
        <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" width="100%" height={height}>
          {ticks.map((tick) => (
            <line key={tick} className="project-timeline__grid" x1={tick * width} x2={tick * width} y1={4} y2={height - 4} />
          ))}
          {taskRows.map((task, index) => {
            const x1 = x(task.started_at ?? task.ended_at ?? timeline.first_started_at ?? "") * width;
            const x2 = x(task.ended_at ?? task.started_at ?? "") * width;
            return (
              <g key={task.task_id} className={`project-timeline__task project-timeline__task--${task.lifecycle_state}`}>
                <rect x={x1} y={taskTop + index * (rowHeight + 4)} width={Math.max(4, x2 - x1)} height={rowHeight} rx={3} />
                <title>{`${task.display_name ?? "Task"} · ${task.session_ids.length} session${task.session_ids.length === 1 ? "" : "s"} · ${task.lifecycle_state}`}</title>
              </g>
            );
          })}
          {sessionRows.map((session) => {
            const x1 = x(session.started_at) * width;
            const x2 = x(session.ended_at ?? session.started_at) * width;
            return (
              <g
                key={session.session_id}
                className={`project-timeline__session project-timeline__session--${session.provider}${onOpenSession ? " is-clickable" : ""}`}
                onClick={onOpenSession ? () => onOpenSession(session.session_id) : undefined}
                role={onOpenSession ? "button" : undefined}
                tabIndex={onOpenSession ? 0 : undefined}
                onKeyDown={onOpenSession ? (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onOpenSession(session.session_id); } } : undefined}
              >
                <rect x={x1} y={sessionTop} width={Math.max(3, x2 - x1)} height={rowHeight} rx={2} />
                <title>{`${session.display_name ?? "Session"} · ${shortDate(session.started_at)}`}</title>
              </g>
            );
          })}
          {timeline.activity.map((day) => {
            const dayStart = Date.parse(`${day.day}T00:00:00Z`);
            if (dayStart + DAY < model.start) return null;
            const x1 = x(new Date(dayStart).toISOString()) * width;
            const x2 = x(new Date(dayStart + DAY).toISOString()) * width;
            const h = Math.max(2, (day.sessions / maxActivity) * activityHeight);
            return (
              <rect key={day.day} className="project-timeline__activity" x={x1} y={activityTop + activityHeight - h} width={Math.max(2, x2 - x1)} height={h}>
                <title>{`${day.day} · ${day.sessions} session${day.sessions === 1 ? "" : "s"}`}</title>
              </rect>
            );
          })}
        </svg>
      </div>
      <p className="project-timeline__axis" aria-hidden="true">
        <span>{shortDate(new Date(model.start).toISOString())}</span>
        <span>{formatSpan(span)}</span>
        <span>{shortDate(new Date(model.end).toISOString())}</span>
      </p>
      {(timeline.truncated || visibleTasks.length > taskRows.length) && (
        <p className="project-timeline__note">
          {timeline.truncated ? "Large project: the newest 500 sessions are drawn." : `Showing the first ${taskRows.length} task windows.`}
        </p>
      )}
    </section>
  );
}
