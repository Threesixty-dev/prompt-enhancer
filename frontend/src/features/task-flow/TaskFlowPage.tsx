import { useCallback, useEffect, useMemo, useState } from "react";
import type { PromptEnhancerTransport } from "../../shared/api/contracts";
import type { AppRoute } from "../../shared/platform/platform";
import type { RuntimeDataMode } from "../../shared/platform/runtimeMode";
import { shortId } from "../../shared/lib/format";
import { ErrorState, LoadingState } from "../../shared/ui/AsyncState";
import { Icon } from "../../shared/ui/Icon";
import { TaskFlowBoard } from "./TaskFlowBoard";
import { TaskFlowTimeline } from "./TaskFlowTimeline";
import { projectTaskFlow } from "./taskFlowAdapter";
import {
  DEFAULT_TASK_FLOW_FILTERS,
  TASK_FLOW_COLUMNS,
  TASK_FLOW_KIND_LABELS,
  TASK_FLOW_READINESS_LABELS,
  applyTaskFlowFilters,
  type TaskFlowFilters,
  type TaskFlowItem,
} from "./taskFlowModel";
import "./TaskFlow.css";

/**
 * Task flow: Kanban plus timeline over the same content-free task records the
 * discovery inbox and reviewed-task screens already expose. Both projections
 * share one filter set, and every card states whether it is a proposed
 * candidate or a confirmed task revision.
 */
export function TaskFlowPage({
  transport,
  navigate,
  runtimeMode,
}: {
  transport: Pick<PromptEnhancerTransport, "listCandidates" | "listTaskRevisions" | "listAnalysisRuns">;
  navigate: (route: AppRoute) => void;
  runtimeMode: RuntimeDataMode;
}) {
  const [items, setItems] = useState<TaskFlowItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<TaskFlowFilters>(DEFAULT_TASK_FLOW_FILTERS);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    Promise.all([
      transport.listCandidates("all", controller.signal),
      transport.listTaskRevisions(undefined, controller.signal),
      transport.listAnalysisRuns(undefined, controller.signal),
    ])
      .then(([candidates, tasks, runs]) => {
        if (controller.signal.aborted) return;
        setItems(projectTaskFlow({ candidates: candidates.candidates, tasks: tasks.tasks, runs: runs.runs }));
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Task records could not be loaded");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [reloadToken, transport]);

  const projects = useMemo(() => [...new Set((items ?? []).map((item) => item.projectId))], [items]);
  const visible = useMemo(() => applyTaskFlowFilters(items ?? [], filters), [filters, items]);
  const counts = useMemo(() => ({
    candidates: visible.filter((item) => item.kind === "candidate").length,
    confirmed: visible.filter((item) => item.kind === "confirmed").length,
  }), [visible]);

  const open = useCallback((item: TaskFlowItem) => {
    if (item.route !== null) navigate(item.route);
  }, [navigate]);

  const update = (patch: Partial<TaskFlowFilters>) =>
    setFilters((current) => ({ ...current, ...patch }));

  return (
    <section aria-labelledby="task-flow-title" className="task-flow">
      <header className="page-header task-flow__header">
        <div>
          <p className="eyebrow">Task timeline</p>
          <h1 id="task-flow-title">Task flow</h1>
          <p>Proposed candidates and confirmed task revisions on one board and one timeline, with lifecycle source, provenance, and readiness on every card.</p>
        </div>
        <div className="page-header__meta">
          <span className="privacy-chip">
            <Icon name="lock" /> {runtimeMode === "synthetic_demo" ? "Local · synthetic records" : "Local · this installation only"}
          </span>
          <span className="count-summary"><strong>{counts.candidates}</strong> candidates · <strong>{counts.confirmed}</strong> confirmed</span>
        </div>
      </header>

      <form aria-label="Task flow filters" className="task-flow__filters" onSubmit={(event) => event.preventDefault()}>
        <label>
          <span>Kind</span>
          <select onChange={(event) => update({ kind: event.target.value as TaskFlowFilters["kind"] })} value={filters.kind}>
            <option value="all">Candidates and confirmed</option>
            <option value="candidate">{TASK_FLOW_KIND_LABELS.candidate}s only</option>
            <option value="confirmed">{TASK_FLOW_KIND_LABELS.confirmed}s only</option>
          </select>
        </label>
        <label>
          <span>Column</span>
          <select onChange={(event) => update({ column: event.target.value as TaskFlowFilters["column"] })} value={filters.column}>
            <option value="all">All columns</option>
            {TASK_FLOW_COLUMNS.map((column) => <option key={column.id} value={column.id}>{column.label}</option>)}
          </select>
        </label>
        <label>
          <span>Readiness</span>
          <select onChange={(event) => update({ readiness: event.target.value as TaskFlowFilters["readiness"] })} value={filters.readiness}>
            <option value="all">Any readiness</option>
            {(Object.keys(TASK_FLOW_READINESS_LABELS) as Array<keyof typeof TASK_FLOW_READINESS_LABELS>).map((state) => (
              <option key={state} value={state}>{TASK_FLOW_READINESS_LABELS[state]}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Project</span>
          <select onChange={(event) => update({ projectId: event.target.value })} value={filters.projectId}>
            <option value="all">All projects</option>
            {projects.map((projectId) => <option key={projectId} value={projectId}>Project {shortId(projectId)}</option>)}
          </select>
        </label>
        <button
          className="button button--secondary button--compact"
          disabled={filters === DEFAULT_TASK_FLOW_FILTERS}
          onClick={() => setFilters(DEFAULT_TASK_FLOW_FILTERS)}
          type="button"
        >
          Reset filters
        </button>
      </form>

      {error !== null && <ErrorState message={error} onRetry={() => setReloadToken((value) => value + 1)} />}
      {loading && items === null ? (
        <LoadingState label="Loading task records" />
      ) : items === null ? null : (
        <>
          <TaskFlowBoard items={visible} onOpen={open} />
          <details className="task-flow__timeline" open>
            <summary>
              <span>Timeline</span>
              <small>{visible.length} of {items.length} items placed by record time</small>
            </summary>
            <TaskFlowTimeline items={visible} onOpen={open} />
          </details>
        </>
      )}
    </section>
  );
}
