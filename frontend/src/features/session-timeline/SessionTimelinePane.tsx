import { useEffect, useMemo, useRef, useState } from "react";
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
const MARKER_LABEL: Record<string, string> = {
  compaction: "compaction",
  plan: "plan",
  user_feedback: "user feedback",
  subagent_start: "subagent start",
  subagent_end: "subagent end",
  approval: "approval",
  permission_change: "permission change",
  session_end: "session end",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function safeTimeline(value: unknown): value is SessionTimeline {
  if (!isRecord(value) || value.contract_version !== "session-timeline.v1") return false;
  return typeof value.session_id === "string"
    && typeof value.started_at === "string"
    && Number.isFinite(Date.parse(value.started_at as string))
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

/** Greedy row packing so overlapping spans stack into rows instead of overplotting. */
export function packRows(items: { start: number; end: number }[], maxRows: number): number[] {
  const rowEnds: number[] = [];
  return items.map((item) => {
    for (let row = 0; row < rowEnds.length; row += 1) {
      if (item.start >= rowEnds[row]) {
        rowEnds[row] = item.end;
        return row;
      }
    }
    if (rowEnds.length < maxRows) {
      rowEnds.push(item.end);
      return rowEnds.length - 1;
    }
    // overflow: place on the last row (dense but never lost)
    rowEnds[rowEnds.length - 1] = Math.max(rowEnds[rowEnds.length - 1], item.end);
    return rowEnds.length - 1;
  });
}

/**
 * Deterministic session timeline v2: turns, waiting gaps (user prompt to first
 * action), tools packed into rows by category, checks, markers - with category
 * filters and drag-to-zoom. Everything drawn comes from indexed safe events -
 * no text, no paths.
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
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [view, setView] = useState<[number, number] | null>(null);
  const [brush, setBrush] = useState<[number, number] | null>(null);
  const chartRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    setTimeline(null);
    setView(null);
    setHidden(new Set());
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
    // waiting gaps: user turn start -> first tool at or after it (agent latency)
    const toolStarts = timeline.tools.map((tool) => Date.parse(tool.started_at)).filter(Number.isFinite).sort((a, b) => a - b);
    const gaps = timeline.turns.flatMap((turn) => {
      const at = Date.parse(turn.started_at);
      if (!Number.isFinite(at)) return [];
      const next = toolStarts.find((t) => t >= at);
      if (next === undefined || next <= at) return [];
      return [{ start: at, end: next, ms: next - at }];
    });
    return { start, end, span, gaps };
  }, [timeline]);

  if (state === "loading") return <section className="session-timeline" aria-busy="true"><p className="session-timeline__note">Drawing the timeline…</p></section>;
  if (state === "missing") return null;
  if (state === "error" || !timeline || !model) {
    return <section className="session-timeline"><p className="session-timeline__note" role="alert">The timeline could not be verified.</p></section>;
  }
  if (timeline.turns.length === 0 && timeline.tools.length === 0 && timeline.markers.length === 0) {
    return (
      <section className="session-timeline">
        <header className="session-timeline__head">
          <div>
            <p className="eyebrow">Timeline · deterministic facts</p>
            <h2>What happened, when</h2>
          </div>
        </header>
        <p className="session-timeline__note">No drawable events were indexed for this session (only usage or metadata records).</p>
      </section>
    );
  }

  const counts = timeline.counts;
  const [viewStart, viewEnd] = view ?? [model.start, model.end];
  const viewSpan = Math.max(1, viewEnd - viewStart);
  const x = (ms: number) => Math.min(1, Math.max(0, (ms - viewStart) / viewSpan));
  const inView = (startMs: number, endMs: number) => endMs >= viewStart && startMs <= viewEnd;
  const width = 1000;
  const laneHeight = 18;
  const toolRowHeight = 10;

  const categories = [...new Set(timeline.tools.filter((tool) => !tool.verification).map((tool) => tool.category))];
  const visibleTools = timeline.tools.filter((tool) => tool.verification || !hidden.has(tool.category));
  const plainTools = visibleTools
    .filter((tool) => !tool.verification)
    .map((tool) => ({ tool, start: Date.parse(tool.started_at), end: Math.max(Date.parse(tool.ended_at ?? tool.started_at), Date.parse(tool.started_at) + 1) }))
    .filter((item) => Number.isFinite(item.start))
    .sort((a, b) => a.start - b.start);
  const toolRowCount = Math.min(4, Math.max(1, plainTools.length ? 4 : 1));
  const rows = packRows(plainTools, toolRowCount);
  const usedRows = plainTools.length ? Math.max(...rows) + 1 : 1;
  const verifications = visibleTools.filter((tool) => tool.verification);

  const lanes: { key: string; label: string; height: number }[] = [
    { key: "turns", label: "Turns", height: laneHeight },
    { key: "waiting", label: "Latency", height: 8 },
    { key: "tools", label: "Tools", height: usedRows * (toolRowHeight + 2) },
    { key: "checks", label: "Checks", height: laneHeight },
    { key: "markers", label: "Markers", height: laneHeight },
  ];
  const laneTop = (key: string) => {
    let y = 12;
    for (const lane of lanes) {
      if (lane.key === key) return y;
      y += lane.height + 10;
    }
    return y;
  };
  const height = 12 + lanes.reduce((sum, lane) => sum + lane.height + 10, 0) + 8;
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  const beginBrush = (clientX: number) => {
    const node = chartRef.current?.querySelector("svg");
    if (!node) return;
    const rect = node.getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    setBrush([fraction, fraction]);
  };
  const moveBrush = (clientX: number) => {
    if (!brush) return;
    const node = chartRef.current?.querySelector("svg");
    if (!node) return;
    const rect = node.getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    setBrush([brush[0], fraction]);
  };
  const endBrush = () => {
    if (!brush) return;
    const [a, b] = [Math.min(...brush), Math.max(...brush)];
    setBrush(null);
    if (b - a < 0.02) return; // a click, not a drag
    setView([viewStart + a * viewSpan, viewStart + b * viewSpan]);
  };

  return (
    <section aria-labelledby="session-timeline-title" className="session-timeline">
      <header className="session-timeline__head">
        <div>
          <p className="eyebrow">Timeline · deterministic facts</p>
          <h2 id="session-timeline-title">What happened, when</h2>
        </div>
        <dl className="session-timeline__stats">
          <div><dt>Duration</dt><dd>{formatDuration(model.span)}</dd></div>
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
          {model.gaps.length > 0 && (
            <div><dt>Median wait</dt><dd>{formatDuration([...model.gaps.map((g) => g.ms)].sort((a, b) => a - b)[Math.floor(model.gaps.length / 2)])}</dd></div>
          )}
          <div><dt>Tokens</dt><dd>{timeline.usage.requests === 0 ? "not reported" : `${formatTokens(timeline.usage.input_tokens)} in · ${formatTokens(timeline.usage.output_tokens)} out`}</dd></div>
        </dl>
      </header>
      <div className="session-timeline__toolbar">
        <div aria-label="Show or hide tool categories" className="session-timeline__filters" role="group">
          {categories.map((category) => (
            <button
              aria-pressed={!hidden.has(category)}
              className={hidden.has(category) ? "session-timeline__filter" : "session-timeline__filter session-timeline__filter--on"}
              data-category={category}
              key={category}
              onClick={() => setHidden((prev) => { const next = new Set(prev); if (next.has(category)) next.delete(category); else next.add(category); return next; })}
              type="button"
            >
              <i aria-hidden="true" /> {CATEGORY_LABEL[category] ?? category}
            </button>
          ))}
        </div>
        {view && (
          <button className="session-timeline__reset" onClick={() => setView(null)} type="button">
            Showing {formatDuration(viewSpan)} of {formatDuration(model.span)} · reset zoom
          </button>
        )}
      </div>
      <div
        className="session-timeline__chart"
        ref={chartRef}
        role="group"
        aria-label={`Timeline with ${counts.turns} turns, ${counts.tools} tool calls and ${verifications.length} checks. Drag horizontally to zoom.`}
        onPointerDown={(event) => { if (event.button === 0) { event.currentTarget.setPointerCapture(event.pointerId); beginBrush(event.clientX); } }}
        onPointerMove={(event) => moveBrush(event.clientX)}
        onPointerUp={endBrush}
        onPointerCancel={() => setBrush(null)}
        onDoubleClick={() => setView(null)}
      >
        <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" width="100%" height={height}>
          {ticks.map((tick) => (
            <line key={tick} className="session-timeline__grid" x1={tick * width} x2={tick * width} y1={6} y2={height - 10} />
          ))}
          {timeline.turns.map((turn) => {
            const startMs = Date.parse(turn.started_at);
            const endMs = turn.ended_at ? Date.parse(turn.ended_at) : startMs + 1;
            if (!Number.isFinite(startMs) || !inView(startMs, endMs)) return null;
            const x1 = x(startMs) * width;
            const x2 = x(endMs) * width;
            return (
              <rect key={`turn-${turn.index}`} className="session-timeline__turn" x={x1} y={laneTop("turns")} width={Math.max(3, x2 - x1)} height={laneHeight} rx={3}>
                <title>{`Turn ${turn.index + 1}${turn.ended_at ? ` · ${formatDuration(endMs - startMs)}` : ""} · ${new Date(startMs).toLocaleTimeString()}`}</title>
              </rect>
            );
          })}
          {model.gaps.map((gap, index) => {
            if (!inView(gap.start, gap.end)) return null;
            const x1 = x(gap.start) * width;
            const x2 = x(gap.end) * width;
            return (
              <rect key={`gap-${index}`} className="session-timeline__gap" x={x1} y={laneTop("waiting")} width={Math.max(1.5, x2 - x1)} height={8} rx={2}>
                <title>{`Waited ${formatDuration(gap.ms)} before the first action`}</title>
              </rect>
            );
          })}
          {plainTools.map((item, index) => {
            if (!inView(item.start, item.end)) return null;
            const x1 = x(item.start) * width;
            const x2 = x(item.end) * width;
            const failed = item.tool.success === false;
            return (
              <rect
                key={`tool-${index}`}
                className={`session-timeline__tool session-timeline__tool--${item.tool.category}${failed ? " session-timeline__tool--error" : ""}`}
                data-category={item.tool.category}
                x={x1}
                y={laneTop("tools") + rows[index] * (toolRowHeight + 2)}
                width={Math.max(2, x2 - x1)}
                height={toolRowHeight}
                rx={2}
              >
                <title>{`${CATEGORY_LABEL[item.tool.category] ?? item.tool.category}${failed ? " · failed" : ""}${item.tool.duration_ms != null ? ` · ${formatDuration(item.tool.duration_ms)}` : ""} · ${new Date(item.start).toLocaleTimeString()}`}</title>
              </rect>
            );
          })}
          {verifications.map((tool, index) => {
            const startMs = Date.parse(tool.started_at);
            const endMs = Math.max(Date.parse(tool.ended_at ?? tool.started_at), startMs + 1);
            if (!Number.isFinite(startMs) || !inView(startMs, endMs)) return null;
            const tone = tool.success === false ? "failed" : tool.success === true ? "passed" : "unknown";
            return (
              <rect
                key={`check-${index}`}
                className={`session-timeline__check session-timeline__check--${tone}`}
                x={x(startMs) * width}
                y={laneTop("checks")}
                width={Math.max(3, (x(endMs) - x(startMs)) * width)}
                height={laneHeight}
                rx={3}
              >
                <title>{`${CATEGORY_LABEL[tool.category] ?? tool.category} check · ${tone}${tool.duration_ms != null ? ` · ${formatDuration(tool.duration_ms)}` : ""}`}</title>
              </rect>
            );
          })}
          {timeline.markers.map((marker, index) => {
            const at = Date.parse(marker.at);
            if (!Number.isFinite(at) || !inView(at, at)) return null;
            return (
              <g key={`marker-${index}`} className={`session-timeline__marker session-timeline__marker--${marker.kind}`}>
                <line x1={x(at) * width} x2={x(at) * width} y1={laneTop("markers")} y2={laneTop("markers") + laneHeight} />
                <title>{`${MARKER_LABEL[marker.kind] ?? marker.kind.replace(/_/g, " ")} · ${new Date(at).toLocaleTimeString()}`}</title>
              </g>
            );
          })}
          {brush && (
            <rect className="session-timeline__brush" x={Math.min(...brush) * width} y={4} width={Math.abs(brush[1] - brush[0]) * width} height={height - 12} />
          )}
        </svg>
        <ol className="session-timeline__lanes" aria-hidden="true">
          {lanes.map((lane) => <li key={lane.key} style={{ height: lane.height + 10 }}>{lane.label}</li>)}
        </ol>
      </div>
      <p className="session-timeline__axis" aria-hidden="true">
        <span>{new Date(viewStart).toLocaleTimeString()}</span>
        <span>{formatDuration(viewSpan)}{view ? " (zoomed)" : ""}</span>
        <span>{new Date(viewEnd).toLocaleTimeString()}</span>
      </p>
      {(timeline.truncated || !timeline.events_complete) && (
        <p className="session-timeline__note">
          {timeline.truncated ? "Long session: the drawing is bounded; counts cover what was drawn." : "The provider did not confirm this session's event stream is complete."}
        </p>
      )}
    </section>
  );
}
