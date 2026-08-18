import type { Provider } from "../../shared/api/contracts";
import type { AppRoute } from "../../shared/platform/platform";

/** Discovery proposals and human-confirmed revisions are never interchangeable. */
export type TaskFlowKind = "candidate" | "confirmed";

/**
 * These columns describe immutable record kinds, not an inferred work state.
 * In particular, no backlog/in-progress/done column exists because the local
 * task contract has no authoritative events for those states.
 */
export type TaskFlowColumnId =
  | "proposed"
  | "confirmed"
  | "reviewed"
  | "rejected"
  | "decided_unknown";

export interface TaskFlowColumn {
  id: TaskFlowColumnId;
  label: string;
  kind: TaskFlowKind;
  description: string;
}

export const TASK_FLOW_COLUMNS: readonly TaskFlowColumn[] = [
  {
    id: "proposed",
    label: "Proposed groupings",
    kind: "candidate",
    description: "Detected groupings awaiting an explicit human decision. They are not tasks.",
  },
  {
    id: "confirmed",
    label: "Confirmed revisions",
    kind: "confirmed",
    description: "Immutable task revisions created by accept, merge, or split decisions.",
  },
  {
    id: "reviewed",
    label: "Accepted · merged · split",
    kind: "candidate",
    description: "Reviewed proposal receipts. Their output revisions appear separately.",
  },
  {
    id: "rejected",
    label: "Rejected proposals",
    kind: "candidate",
    description: "Explicitly rejected proposals. No successor task is implied.",
  },
  {
    id: "decided_unknown",
    label: "Decided · action unknown",
    kind: "candidate",
    description: "A decision is reported, but its action is not exposed. No outcome is inferred.",
  },
];

export type TaskFlowLifecycleSource =
  | "discovery_candidate"
  | "review_decision"
  | "task_revision";

export interface TaskFlowLifecycle {
  source: TaskFlowLifecycleSource;
  /** Raw status token from the source record (never renamed into a work state). */
  status: string;
  label: string;
}

export interface TaskFlowProvenance {
  origin: string;
  version: string;
  fingerprint: string;
  dataTier: string | null;
}

export type TaskFlowEvidenceState =
  | "observed_complete"
  | "observed_partial"
  | "not_observed"
  | "no_eligible"
  | "not_applicable";

export interface TaskFlowEvidenceFact {
  state: TaskFlowEvidenceState;
  label: string;
  detail: string;
}

export type TaskFlowAnalysisState =
  | "running"
  | "completed"
  | "failed"
  | "not_observed"
  | "unknown"
  | "not_applicable";

export interface TaskFlowAnalysisRunFact {
  runId: string;
  status: "running" | "completed" | "failed";
  startedAt: string;
  finishedAt: string | null;
  failureCode: string | null;
  provenance: TaskFlowProvenance;
}

export interface TaskFlowAnalysisFact {
  state: TaskFlowAnalysisState;
  label: string;
  detail: string;
  runs: readonly TaskFlowAnalysisRunFact[];
}

export interface TaskFlowItem {
  id: string;
  /** Pseudonymous candidate or task identity, retained for exact audit joins. */
  sourceId: string;
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
  evidence: TaskFlowEvidenceFact;
  analysis: TaskFlowAnalysisFact;
  /** Creation time of this exact immutable record, not task start time. */
  occurredAt: string;
  /** The current task contract records neither authoritative task time. */
  taskStartedAt: null;
  taskFinishedAt: null;
  decisionId: string | null;
  decisionAction: "accept" | "reject" | "merge" | "split" | null;
  /** Authoritative CandidateListItem decision_status, not inferred from nullable receipt fields. */
  reviewDecisionRecorded: boolean;
  confidence: number | null;
  coverage: number | null;
  route: AppRoute | null;
}

export interface TaskFlowFilters {
  kind: "all" | TaskFlowKind;
  column: "all" | TaskFlowColumnId;
  analysis: "all" | TaskFlowAnalysisState;
  projectId: "all" | string;
}

export const DEFAULT_TASK_FLOW_FILTERS: TaskFlowFilters = {
  kind: "all",
  column: "all",
  analysis: "all",
  projectId: "all",
};

export const TASK_FLOW_KIND_LABELS: Readonly<Record<TaskFlowKind, string>> = {
  candidate: "Proposal",
  confirmed: "Confirmed revision",
};

export const TASK_FLOW_ANALYSIS_LABELS: Readonly<Record<TaskFlowAnalysisState, string>> = {
  running: "Analysis running",
  completed: "Analysis completed",
  failed: "Analysis failed",
  not_observed: "No matching analysis observed",
  unknown: "Analysis history incomplete",
  not_applicable: "Not applicable to proposals",
};

export const TASK_FLOW_SOURCE_LABELS: Readonly<Record<TaskFlowLifecycleSource, string>> = {
  discovery_candidate: "Discovery proposal",
  review_decision: "Human review decision",
  task_revision: "Task revision",
};

export function applyTaskFlowFilters(
  items: readonly TaskFlowItem[],
  filters: TaskFlowFilters,
): TaskFlowItem[] {
  return items.filter((item) =>
    (filters.kind === "all" || item.kind === filters.kind)
    && (filters.column === "all" || item.column === filters.column)
    && (filters.analysis === "all" || item.analysis.state === filters.analysis)
    && (filters.projectId === "all" || item.projectId === filters.projectId));
}
