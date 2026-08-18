import type { AnalysisRun, CandidateListItem, TaskRevision } from "../../shared/api/contracts";
import { candidateLabel } from "../../entities/discovery/model";
import { shortId, titleFromKey } from "../../shared/lib/format";
import type {
  TaskFlowAnalysisFact,
  TaskFlowAnalysisRunFact,
  TaskFlowEvidenceFact,
  TaskFlowItem,
} from "./taskFlowModel";

/**
 * Deterministic projection of content-free task records. Column membership is
 * based only on proposal/review/revision facts. Analysis status is deliberately
 * orthogonal: completing a metric run never moves or completes a task.
 */
export interface TaskFlowSources {
  candidates: readonly CandidateListItem[];
  tasks: readonly TaskRevision[];
  runs: readonly AnalysisRun[];
}

export interface TaskFlowProjectionContext {
  /** True only when the run index traversal observed its own final short page. */
  analysisIndexEnded: boolean;
}

function candidateEvidence(item: CandidateListItem): TaskFlowEvidenceFact {
  const { candidate } = item;
  const confidence = candidate.confidence == null
    ? "confidence unknown"
    : `confidence ${Math.round(candidate.confidence * 100)}%`;
  if (candidate.eligible_count === 0) {
    return {
      state: "no_eligible",
      label: "No eligible observations",
      detail: `The discovery contract recorded an exact zero eligible observations · ${confidence}`,
    };
  }
  const detail = `${candidate.observed_count} of ${candidate.eligible_count} eligible observations recorded · ${confidence}`;
  if (candidate.observed_count === 0) {
    return { state: "not_observed", label: "No evidence observed", detail };
  }
  if (candidate.coverage < 1) {
    return { state: "observed_partial", label: "Partial evidence observed", detail };
  }
  return { state: "observed_complete", label: "All eligible evidence observed", detail };
}

function candidateItem(item: CandidateListItem): TaskFlowItem {
  const { candidate } = item;
  const decided = item.decision_status === "decided";
  const action = item.decision_action;
  const column = !decided
    ? "proposed"
    : action === null
      ? "decided_unknown"
      : action === "reject"
        ? "rejected"
        : "reviewed";
  return {
    id: `candidate:${candidate.candidate_id}`,
    sourceId: candidate.candidate_id,
    kind: "candidate",
    column,
    title: candidateLabel(candidate.candidate_id),
    subtitle: `${candidate.session_ids.length} session${candidate.session_ids.length === 1 ? "" : "s"} · project ${shortId(candidate.project_id)}`,
    projectId: candidate.project_id,
    provider: candidate.provider,
    sessionCount: candidate.session_ids.length,
    lifecycle: decided
      ? {
        source: "review_decision",
        status: action ?? "unknown_action",
        label: `Human decision recorded · ${action === null ? "action not exposed" : titleFromKey(action)}`,
      }
      : {
        source: "discovery_candidate",
        status: item.decision_status,
        label: "Detected grouping · explicit review required",
      },
    provenance: {
      origin: "Task discovery",
      version: candidate.discovery_version,
      fingerprint: candidate.input_fingerprint,
      dataTier: null,
    },
    evidence: candidateEvidence(item),
    analysis: {
      state: "not_applicable",
      label: "Not a task revision",
      detail: "A proposal cannot have task analysis state before human confirmation.",
      runs: [],
    },
    occurredAt: candidate.created_at,
    taskStartedAt: null,
    taskFinishedAt: null,
    decisionId: item.decision_id,
    decisionAction: action,
    reviewDecisionRecorded: decided,
    confidence: candidate.confidence ?? null,
    coverage: candidate.coverage,
    route: { name: "discovery" },
  };
}

function matchingRuns(task: TaskRevision, runs: readonly AnalysisRun[]): AnalysisRun[] {
  return runs
    .filter((run) => run.task_id === task.task_id
      && run.task_revision === task.revision
      && run.input_fingerprint === task.input_fingerprint)
    .sort((left, right) => {
      const byTime = left.started_at.localeCompare(right.started_at);
      return byTime !== 0 ? byTime : left.run_id.localeCompare(right.run_id);
    });
}

function runFact(run: AnalysisRun): TaskFlowAnalysisRunFact {
  return {
    runId: run.run_id,
    status: run.status,
    startedAt: run.started_at,
    finishedAt: run.finished_at,
    failureCode: run.failure_code,
    provenance: {
      origin: run.metric_pack_key,
      version: `pack v${run.metric_pack_version} · engine ${run.metric_engine_version} · schema ${run.schema_version}`,
      fingerprint: run.input_fingerprint,
      dataTier: run.data_tier,
    },
  };
}

function analysisFact(
  task: TaskRevision,
  runs: readonly AnalysisRun[],
  analysisIndexEnded: boolean,
): TaskFlowAnalysisFact {
  const matching = matchingRuns(task, runs).map(runFact);
  if (matching.length === 0) {
    return analysisIndexEnded
      ? {
        state: "not_observed",
        label: "No matching analysis observed",
        detail: "The separate bounded run index reached its page end; refresh after activity because the indexes are not one atomic snapshot.",
        runs: [],
      }
      : {
        state: "unknown",
        label: "Analysis history incomplete",
        detail: "The run index did not prove its end, so absence of a matching run is unknown.",
        runs: [],
      };
  }
  const latest = matching.at(-1)!;
  const suffix = matching.length === 1 ? "1 matching run" : `${matching.length} matching runs`;
  return {
    state: latest.status,
    label: `Latest analysis ${latest.status}`,
    detail: `${suffix}; this is analysis state only and never task completion.`,
    runs: matching,
  };
}

function taskItem(
  task: TaskRevision,
  runs: readonly AnalysisRun[],
  context: TaskFlowProjectionContext,
): TaskFlowItem {
  return {
    id: `task:${task.task_id}:${task.revision}`,
    sourceId: task.task_id,
    kind: "confirmed",
    column: "confirmed",
    title: `${titleFromKey(task.task_type)} · revision ${task.revision}`,
    subtitle: `${task.session_ids.length} session${task.session_ids.length === 1 ? "" : "s"} · project ${shortId(task.project_id)}`,
    projectId: task.project_id,
    provider: null,
    sessionCount: task.session_ids.length,
    lifecycle: {
      source: "task_revision",
      status: task.lifecycle_state,
      label: `Raw revision state · ${titleFromKey(task.lifecycle_state)}`,
    },
    provenance: {
      origin: "Task revision",
      version: `revision ${task.revision}`,
      fingerprint: task.input_fingerprint,
      dataTier: null,
    },
    evidence: {
      state: "not_applicable",
      label: "Discovery evidence is separate",
      detail: "The immutable revision fingerprint is retained; candidate evidence is not re-scored here.",
    },
    analysis: analysisFact(task, runs, context.analysisIndexEnded),
    occurredAt: task.created_at,
    taskStartedAt: null,
    taskFinishedAt: null,
    decisionId: null,
    decisionAction: null,
    reviewDecisionRecorded: false,
    confidence: null,
    coverage: null,
    route: { name: "task", taskId: task.task_id, revision: task.revision },
  };
}

/** Items in stable record-creation order (occurredAt, then id). */
export function projectTaskFlow(
  sources: TaskFlowSources,
  context: TaskFlowProjectionContext,
): TaskFlowItem[] {
  const items = [
    ...sources.candidates.map(candidateItem),
    ...sources.tasks.map((task) => taskItem(task, sources.runs, context)),
  ];
  return items.sort((left, right) => {
    const byTime = left.occurredAt.localeCompare(right.occurredAt);
    return byTime !== 0 ? byTime : left.id.localeCompare(right.id);
  });
}

export interface TaskFlowTimelineScale {
  start: number;
  end: number;
  ticks: readonly { at: number; label: string }[];
}

function timelineDate(value: number): string {
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" }).format(new Date(value));
}

/** Time scale over explicit event timestamps. Invalid or absent times are omitted. */
export function taskFlowTimelineScale(
  events: readonly { occurredAt: string | null }[],
): TaskFlowTimelineScale | null {
  const stamps = events
    .map((event) => event.occurredAt)
    .filter((value): value is string => value !== null)
    .map((value) => new Date(value).getTime())
    .filter((value) => Number.isFinite(value));
  if (stamps.length === 0) return null;
  let start = Math.min(...stamps);
  let end = Math.max(...stamps);
  if (end - start < 60 * 60 * 1000) {
    start -= 12 * 60 * 60 * 1000;
    end += 12 * 60 * 60 * 1000;
  }
  const tickCount = 5;
  const ticks = Array.from({ length: tickCount }, (_, index) => {
    const at = start + ((end - start) * index) / (tickCount - 1);
    return { at, label: timelineDate(at) };
  });
  return { start, end, ticks };
}

export function timelinePosition(scale: TaskFlowTimelineScale, value: string): number | null {
  const time = new Date(value).getTime();
  if (!Number.isFinite(time) || scale.end === scale.start) return null;
  return Math.max(0, Math.min(1, (time - scale.start) / (scale.end - scale.start)));
}
