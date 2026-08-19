import { useEffect, useMemo, useState } from "react";
import type { PromptEnhancerTransport, SessionTimeline } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import "./SessionTimelinePane.css";

const CATEGORY_LABEL: Record<string, string> = {
  file_read: "Read",
  file_write: "Write",
  command: "Command",
  search: "Search",
  test: "Test",
  build: "Build",
  version_control: "Git",
  network: "Network",
  mcp: "MCP",
  subagent: "Subagent",
  other: "Other",
  unknown: "Unknown",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function safeTimeline(value: unknown): value is SessionTimeline {
  if (!isRecord(value) || value.contract_version !== "session-timeline.v1") return false;
  return typeof value.session_id === "string"
    && typeof value.started_at === "string"
    && Array.isArray(value.turns) && Array.isArray(value.tools) && Array.isArray(value.markers)
    && isRecord(value.counts) && isRecord(value.usage);
}

function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "–";
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function formatTokens(value: number | null | undefined): string {
  if (value === null || value === undefined) return "unknown";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

/**
 * Deterministic session timeline: turns, tool spans by category, verification
 * outcomes and markers on one time axis. Everything drawn comes from indexed
 * safe events - no text, no paths. Scales with its container (SVG viewBox).
 */
export function SessionTimelinePane({
  sessionId,
  transport,
}: {
  sessionId: string;
  transport: Pick<PromptEnhancerTransport, "getSessionTimeline">;
}) {
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">("loading");
  const [timeline, setTimeline] = useState<SessionTimeline | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    setTimeline(null);
    transport.getSessionTimeline(sessionId, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        if (!safeTimeline(value)) { setState("error"); return; }
        setTimeline(value);
        setState("ready");
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setState(caught instanceof TransportError && caught.status === 404 ? "missing" : "error");
      });
    return () => controller.abort();
  }, [sessionId, transport]);

  const model = useMemo(() => {
    if (!timeline) return null;
    const start = Date.parse(timeline.started_at);
    const candidates = [
      timeline.ended_at ? Date.parse(timeline.ended_at) : NaN,
      ...timeline.turns.map((turn) => Date.parse(turn.ended_at ?? turn.started_at)),
      ...timeline.tools.map((tool) => Date.parse(tool.ended_at ?? tool.started_at)),
      ...timeline.markers.map((marker) => Date.parse(marker.at)),
    ].filter((value) => Number.isFinite(value));
    const end = Math.max(start + 1000, ...candidates);
    const span = Math.max(1, end - start);
    const x = (iso: string) => Math.min(1, Math.max(0, (Date.parse(iso) - start) / span));
    return { start, end, span, x };
  }, [timeline]);

  if (state === "loading") return <section className="session-timeline" aria-busy="true"><p className="session-timeline__note">Drawing the timeline…</p></section>;
  if (state === "missing") return null;
  if (state === "error" || !timeline || !model) {
    return <section className="session-timeline"><p className="session-timeline__note" role="alert">The timeline could not be verified.</p></section>;
  }

  const { x, span } = model;
  const width = 1000;
  const laneHeight = 18;
  const lanes = ["Turns", "Tools", "Checks", "Markers"];
  const height = 12 + lanes.length * (laneHeight + 10) + 16;
  const laneY = (index: number) => 12 + index * (laneHeight + 10);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const verifications = timeline.tools.filter((tool) => tool.verification);
  const counts = timeline.counts;

  return (
    <section aria-labelledby="session-timeline-title" className="session-timeline">
      <header className="session-timeline__head">
        <div>
          <p className="eyebrow">Timeline · deterministic facts</p>
          <h2 id="session-timeline-title">What happened, when</h2>
        </div>
        <dl className="session-timeline__stats">
          <div><dt>Duration</dt><dd>{formatDuration(span)}</dd></div>
          <div><dt>Turns</dt><dd>{counts.turns}</dd></div>
          <div><dt>Tool calls</dt><dd>{counts.tools}{counts.tool_errors > 0 ? ` · ${counts.tool_errors} failed` : ""}</dd></div>
          <div>
            <dt>Checks</dt>
            <dd>
              {counts.verifications_passed + counts.verifications_failed + counts.verifications_unknown === 0
                ? "none observed"
                : `${counts.verifications_passed} passed · ${counts.verifications_failed} failed${counts.verifications_unknown ? ` · ${counts.verifications_unknown} unknown` : ""}`}
            </dd>
          </div>
          <div><dt>Tokens</dt><dd>{timeline.usage.requests === 0 ? "not reported" : `${formatTokens(timeline.usage.input_tokens)} in · ${formatTokens(timeline.usage.output_tokens)} out`}</dd></div>
        </dl>
      </header>
      <div className="session-timeline__chart" role="img" aria-label={`Timeline with ${counts.turns} turns, ${counts.tools} tool calls and ${verifications.length} checks`}>
        <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" width="100%" height={height}>
          {ticks.map((tick) => (
            <line key={tick} className="session-timeline__grid" x1={tick * width} x2={tick * width} y1={6} y2={height - 10} />
          ))}
          {timeline.turns.map((turn) => {
            const x1 = x(turn.started_at) * width;
            const x2 = turn.ended_at ? x(turn.ended_at) * width : x1 + 3;
            return <rect key={`turn-${turn.index}`} className="session-timeline__turn" x={x1} y={laneY(0)} width={Math.max(3, x2 - x1)} height={laneHeight} rx={3} />;
          })}
          {timeline.tools.map((tool, index) => {
            const x1 = x(tool.started_at) * width;
            const x2 = tool.ended_at ? x(tool.ended_at) * width : x1 + 2;
            const lane = tool.verification ? 2 : 1;
            const tone = tool.success === false ? "failed" : tool.success === true ? "passed" : "unknown";
            return (
              <rect
                key={`tool-${index}`}
                className={`session-timeline__tool session-timeline__tool--${tool.category} session-timeline__tool--${tone}`}
                data-category={tool.category}
                x={x1}
                y={laneY(lane) + (tool.verification ? 0 : 4)}
                width={Math.max(2, x2 - x1)}
                height={tool.verification ? laneHeight : laneHeight - 8}
                rx={2}
              >
                <title>{`${CATEGORY_LABEL[tool.category] ?? tool.category}${tool.verification ? ` check · ${tone}` : ""}${tool.duration_ms != null ? ` · ${formatDuration(tool.duration_ms)}` : ""}`}</title>
              </rect>
            );
          })}
          {timeline.markers.map((marker, index) => (
            <g key={`marker-${index}`} className={`session-timeline__marker session-timeline__marker--${marker.kind}`}>
              <line x1={x(marker.at) * width} x2={x(marker.at) * width} y1={laneY(3)} y2={laneY(3) + laneHeight} />
              <title>{marker.kind.replace("_", " ")}</title>
            </g>
          ))}
        </svg>
        <ol className="session-timeline__lanes" aria-hidden="true">
          {lanes.map((lane) => <li key={lane}>{lane}</li>)}
        </ol>
      </div>
      <p className="session-timeline__axis" aria-hidden="true">
        <span>{new Date(model.start).toLocaleTimeString()}</span>
        <span>{formatDuration(span)}</span>
        <span>{new Date(model.end).toLocaleTimeString()}</span>
      </p>
      {(timeline.truncated || !timeline.events_complete) && (
        <p className="session-timeline__note">
          {timeline.truncated ? "Long session: the drawing is bounded; counts cover what was drawn." : "The provider did not confirm this session's event stream is complete."}
        </p>
      )}
    </section>
  );
}
