import type { Provider } from "../../shared/api/contracts";
import type { AppRoute } from "../../shared/platform/platform";

/**
 * Presentation model for the task flow board and timeline. Candidates and
 * confirmed tasks are different things: a candidate is a discovery grouping
 * proposed by a versioned heuristic and awaiting a human decision; a confirmed
 * task is an immutable revision created by that decision. The kind is carried
 * on every item and never inferred from position.
 */
export type TaskFlowKind = "candidate" | "confirmed";

export type TaskFlowColumnId = "proposed" | "confirmed" | "analyzed" | "resolved";

export interface TaskFlowColumn {
  id: TaskFlowColumnId;
  label: string;
  kind: TaskFlowKind;
  description: string;
}

export const TASK_FLOW_COLUMNS: readonly TaskFlowColumn[] = [
  {
    id: "proposed",
    label: "Proposed candidates",
    kind: "candidate",
    description: "Discovery groupings awaiting a human decision. Not tasks yet.",
  },
  {
    id: "confirmed",
    label: "Confirmed tasks",
    kind: "confirmed",
    description: "Reviewed task revisions without a completed analysis run.",
  },
  {
    id: "analyzed",
    label: "Analyzed tasks",
    kind: "confirmed",
    description: "Confirmed revisions with a completed immutable analysis run.",
  },
  {
    id: "resolved",
    label: "Decided candidates",
    kind: "candidate",
    description: "Candidates with a recorded decision; accepted ones continue as confirmed tasks.",
  },
];

export type TaskFlowLifecycleSource =
  | "discovery_candidate"
  | "review_decision"
  | "task_revision"
  | "analysis_run";

export type TaskFlowReadinessState = "ready" | "partial" | "blocked" | "unknown";

export interface TaskFlowLifecycle {
  source: TaskFlowLifecycleSource;
  /** Raw status token from the source record (never renamed). */
  status: string;
  label: string;
}

export interface TaskFlowProvenance {
  origin: string;
  version: string;
  fingerprint: string;
  dataTier: string | null;
}

export interface TaskFlowReadiness {
  state: TaskFlowReadinessState;
  label: string;
  detail: string;
}

export interface TaskFlowItem {
  id: string;
  kind: TaskFlowKind;
  column: TaskFlowColumnId;
  title: string;
  subtitle: string;
  projectId: string;
  /** Provider when the source record exposes it; task revisions do not. */
  provider: Provider | null;
  sessionCount: number;
  lifecycle: TaskFlowLifecycle;
  provenance: TaskFlowProvenance;
  readiness: TaskFlowReadiness;
  /** Timeline anchor (ISO). */
  occurredAt: string;
  endedAt: string | null;
  confidence: number | null;
  coverage: number | null;
  route: AppRoute | null;
}

export interface TaskFlowFilters {
  kind: "all" | TaskFlowKind;
  column: "all" | TaskFlowColumnId;
  readiness: "all" | TaskFlowReadinessState;
  projectId: "all" | string;
}

export const DEFAULT_TASK_FLOW_FILTERS: TaskFlowFilters = {
  kind: "all",
  column: "all",
  readiness: "all",
  projectId: "all",
};

export const TASK_FLOW_KIND_LABELS: Readonly<Record<TaskFlowKind, string>> = {
  candidate: "Candidate",
  confirmed: "Confirmed task",
};

export const TASK_FLOW_READINESS_LABELS: Readonly<Record<TaskFlowReadinessState, string>> = {
  ready: "Ready",
  partial: "Partial",
  blocked: "Blocked",
  unknown: "Unknown",
};

export const TASK_FLOW_SOURCE_LABELS: Readonly<Record<TaskFlowLifecycleSource, string>> = {
  discovery_candidate: "Discovery",
  review_decision: "Review decision",
  task_revision: "Task revision",
  analysis_run: "Analysis run",
};

export function applyTaskFlowFilters(
  items: readonly TaskFlowItem[],
  filters: TaskFlowFilters,
): TaskFlowItem[] {
  return items.filter((item) =>
    (filters.kind === "all" || item.kind === filters.kind)
    && (filters.column === "all" || item.column === filters.column)
    && (filters.readiness === "all" || item.readiness.state === filters.readiness)
    && (filters.projectId === "all" || item.projectId === filters.projectId));
}
