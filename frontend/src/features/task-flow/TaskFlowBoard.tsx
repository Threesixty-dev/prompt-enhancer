import { formatTimestamp, shortId } from "../../shared/lib/format";
import { Icon } from "../../shared/ui/Icon";
import { StatusPill, type PillTone } from "../../shared/ui/StatusPill";
import {
  TASK_FLOW_COLUMNS,
  TASK_FLOW_KIND_LABELS,
  TASK_FLOW_READINESS_LABELS,
  TASK_FLOW_SOURCE_LABELS,
  type TaskFlowItem,
} from "./taskFlowModel";

const READINESS_TONE: Readonly<Record<TaskFlowItem["readiness"]["state"], PillTone>> = {
  ready: "positive",
  partial: "warning",
  blocked: "danger",
  unknown: "neutral",
};

export function TaskFlowCard({ item, onOpen }: { item: TaskFlowItem; onOpen: (item: TaskFlowItem) => void }) {
  return (
    <li className="task-flow-card" data-kind={item.kind} data-readiness={item.readiness.state}>
      <article aria-labelledby={`${item.id}-title`}>
        <header>
          <StatusPill tone={item.kind === "candidate" ? "warning" : "positive"}>
            {TASK_FLOW_KIND_LABELS[item.kind]}
          </StatusPill>
          <small>{formatTimestamp(item.occurredAt)}</small>
        </header>
        <h4 id={`${item.id}-title`}>{item.title}</h4>
        <p className="task-flow-card__subtitle">{item.subtitle}</p>
        <dl>
          <div>
            <dt>Lifecycle</dt>
            <dd>
              <span className="task-flow-card__source">{TASK_FLOW_SOURCE_LABELS[item.lifecycle.source]}</span>
              {" · "}
              {item.lifecycle.label}
            </dd>
          </div>
          <div>
            <dt>Provenance</dt>
            <dd>
              {item.provenance.origin} · {item.provenance.version} · fingerprint <span className="mono">{shortId(item.provenance.fingerprint)}</span>
              {item.provenance.dataTier === null ? "" : ` · ${item.provenance.dataTier.replaceAll("_", " ")} tier`}
            </dd>
          </div>
          <div>
            <dt>Readiness</dt>
            <dd>
              <StatusPill tone={READINESS_TONE[item.readiness.state]}>{TASK_FLOW_READINESS_LABELS[item.readiness.state]} · {item.readiness.label}</StatusPill>
              <span className="task-flow-card__detail">{item.readiness.detail}</span>
            </dd>
          </div>
        </dl>
        <footer>
          <span>{item.sessionCount} session{item.sessionCount === 1 ? "" : "s"}{item.provider === null ? "" : ` · ${item.provider}`}</span>
          <button
            className="button button--secondary button--compact"
            disabled={item.route === null}
            onClick={() => onOpen(item)}
            type="button"
          >
            {item.kind === "candidate" ? "Open in Discovery" : "Open task"} <Icon name="arrow" />
          </button>
        </footer>
      </article>
    </li>
  );
}

/**
 * Kanban projection. Column membership is a property of each item's lifecycle
 * (candidate proposed / decided, task confirmed / analyzed); columns are fixed
 * and empty ones stay visible so the absence of work is legible.
 */
export function TaskFlowBoard({ items, onOpen }: { items: readonly TaskFlowItem[]; onOpen: (item: TaskFlowItem) => void }) {
  return (
    <div aria-label="Task flow board" className="task-flow-board" role="group">
      {TASK_FLOW_COLUMNS.map((column) => {
        const columnItems = items.filter((item) => item.column === column.id);
        const headingId = `task-flow-column-${column.id}`;
        return (
          <section aria-labelledby={headingId} className="task-flow-column" data-column={column.id} data-kind={column.kind} key={column.id}>
            <header>
              <div>
                <h3 id={headingId}>{column.label}</h3>
                <small>{column.description}</small>
              </div>
              <span aria-label={`${columnItems.length} ${columnItems.length === 1 ? "item" : "items"}`} className="task-flow-column__count">{columnItems.length}</span>
            </header>
            <ul>
              {columnItems.length === 0
                ? <li className="task-flow-column__empty">Nothing in this column for the current filters.</li>
                : columnItems.map((item) => <TaskFlowCard item={item} key={item.id} onOpen={onOpen} />)}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
