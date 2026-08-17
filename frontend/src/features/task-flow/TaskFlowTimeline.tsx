import { useMemo } from "react";
import { formatTimestamp } from "../../shared/lib/format";
import { taskFlowTimelineScale, timelinePosition } from "./taskFlowAdapter";
import {
  TASK_FLOW_KIND_LABELS,
  TASK_FLOW_READINESS_LABELS,
  type TaskFlowItem,
  type TaskFlowKind,
} from "./taskFlowModel";

const LANES: readonly { kind: TaskFlowKind; label: string }[] = [
  { kind: "candidate", label: "Candidates (proposed / decided)" },
  { kind: "confirmed", label: "Confirmed tasks (revisions / analysis)" },
];

/**
 * Timeline projection of the same items: two lanes keep candidates and
 * confirmed tasks apart, every marker is a real button (keyboard reachable,
 * labelled with title and time), and the underlying list is rendered as an
 * ordered list for assistive technology. Positions come from record timestamps
 * only; a missing timestamp yields no marker rather than a marker at the start.
 */
export function TaskFlowTimeline({ items, onOpen }: { items: readonly TaskFlowItem[]; onOpen: (item: TaskFlowItem) => void }) {
  const scale = useMemo(() => taskFlowTimelineScale(items), [items]);
  if (scale === null) {
    return <p className="task-flow-timeline__empty" role="status">No dated items match the current filters, so there is nothing to place on the timeline.</p>;
  }
  return (
    <div className="task-flow-timeline">
      <div aria-hidden="true" className="task-flow-timeline__axis">
        {scale.ticks.map((tick, index) => (
          <span key={tick.at} style={{ left: `${(index / (scale.ticks.length - 1)) * 100}%` }}>{tick.label}</span>
        ))}
      </div>
      {LANES.map((lane) => {
        const laneItems = items.filter((item) => item.kind === lane.kind);
        return (
          <section aria-label={lane.label} className="task-flow-lane" data-kind={lane.kind} key={lane.kind}>
            <header><strong>{lane.label}</strong><small>{laneItems.length} item{laneItems.length === 1 ? "" : "s"}</small></header>
            <ol className="task-flow-lane__track">
              {laneItems.map((item) => {
                const start = timelinePosition(scale, item.occurredAt);
                if (start === null) return null;
                const end = item.endedAt === null ? null : timelinePosition(scale, item.endedAt);
                const width = end === null ? 0 : Math.max(0, end - start);
                return (
                  <li key={item.id} style={{ left: `${start * 100}%`, width: width === 0 ? undefined : `${width * 100}%` }}>
                    <button
                      aria-label={`${TASK_FLOW_KIND_LABELS[item.kind]} · ${item.title} · ${formatTimestamp(item.occurredAt)} · ${TASK_FLOW_READINESS_LABELS[item.readiness.state]}`}
                      data-column={item.column}
                      data-readiness={item.readiness.state}
                      onClick={() => onOpen(item)}
                      type="button"
                    >
                      <i aria-hidden="true" />
                      <span>{item.title}</span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </section>
        );
      })}
      <p className="task-flow-timeline__legend">
        Markers sit at record creation time; a bar extends to the analysis finish time when one exists. Candidates and confirmed tasks never share a lane.
      </p>
    </div>
  );
}
