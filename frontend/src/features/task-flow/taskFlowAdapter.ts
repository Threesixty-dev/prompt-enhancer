import type { AnalysisRun, CandidateListItem, TaskRevision } from "../../shared/api/contracts";
import { candidateLabel } from "../../entities/discovery/model";
import { shortId, titleFromKey } from "../../shared/lib/format";
import type { TaskFlowItem, TaskFlowReadiness } from "./taskFlowModel";

/**
 * Deterministic projection of the existing content-free task records onto the
 * board/timeline model. It reads only DTO fields the transport already exposes;
 * it never invents dates, outcomes, or decisions. Missing evidence stays
 * "unknown"; it is never rendered as blocked or complete.
 */
export interface TaskFlowSources {
  candidates: readonly CandidateListItem[];
  tasks: readonly TaskRevision[];
  runs: readonly AnalysisRun[];
}

function candidateReadiness(item: CandidateListItem): TaskFlowReadiness {
  const { candidate } = item;
  const confidence = candidate.confidence == null ? "confidence unknown" : `confidence ${Math.round(candidate.confidence * 100)}%`;
  if (candidate.eligible_count === 0) {
    return { state: "unknown", label: "No eligible evidence", detail: `No eligible observation was recorded · ${confidence}` };
  }
  const detail = `${candidate.observed_count} of ${candidate.eligible_count} observations · ${confidence}`;
  if (candidate.coverage >= 1) return { state: "ready", label: "Evidence complete", detail };
  if (candidate.coverage > 0) return { state: "partial", label: "Evidence partial", detail };
  return { state: "blocked", label: "No evidence observed", detail };
}

function candidateItem(item: CandidateListItem): TaskFlowItem {
  const { candidate } = item;
  const decided = item.decision_status === "decided";
  const action = item.decision_action;
  return {
    id: `candidate:${candidate.candidate_id}`,
    kind: "candidate",
    column: decided ? "resolved" : "proposed",
    title: candidateLabel(candidate.candidate_id),
    subtitle: `${candidate.session_ids.length} session${candidate.session_ids.length === 1 ? "" : "s"} · project ${shortId(candidate.project_id)}`,
    projectId: candidate.project_id,
    provider: candidate.provider,
    sessionCount: candidate.session_ids.length,
    lifecycle: decided
      ? {
        source: "review_decision",
        status: action ?? "decided",
        label: `Decision recorded · ${action === null ? "action not exposed" : titleFromKey(action)}`,
      }
      : { source: "discovery_candidate", status: item.decision_status, label: "Proposed by discovery · needs review" },
    provenance: {
      origin: "Task discovery",
      version: candidate.discovery_version,
      fingerprint: candidate.input_fingerprint,
      dataTier: null,
    },
    readiness: candidateReadiness(item),
    occurredAt: candidate.created_at,
    endedAt: null,
    confidence: candidate.confidence ?? null,
    coverage: candidate.coverage,
    route: { name: "discovery" },
  };
}

function latestRunFor(task: TaskRevision, runs: readonly AnalysisRun[]): AnalysisRun | null {
  const matching = runs
    .filter((run) => run.task_id === task.task_id
      && run.task_revision === task.revision
      && run.input_fingerprint === task.input_fingerprint)
    .sort((left, right) => right.started_at.localeCompare(left.started_at));
  return matching[0] ?? null;
}

function taskReadiness(run: AnalysisRun | null): TaskFlowReadiness {
  if (run === null) {
    return { state: "partial", label: "Awaiting analysis", detail: "Analysis is a separate explicit action; nothing has run for this revision." };
  }
  switch (run.status) {
    case "completed":
      return { state: "ready", label: "Analysis completed", detail: `${run.metric_pack_key} v${run.metric_pack_version} · ${run.data_tier.replaceAll("_", " ")} tier` };
    case "running":
      return { state: "partial", label: "Analysis running", detail: `${run.metric_pack_key} v${run.metric_pack_version} · started, not finished` };
    case "failed":
    default:
      return { state: "blocked", label: "Analysis failed", detail: `Failure code ${run.failure_code ?? "not exposed"} · the revision itself is unchanged` };
  }
}

function taskItem(task: TaskRevision, runs: readonly AnalysisRun[]): TaskFlowItem {
  const run = latestRunFor(task, runs);
  const analyzed = run !== null && run.status === "completed";
  return {
    id: `task:${task.task_id}:${task.revision}`,
    kind: "confirmed",
    column: analyzed ? "analyzed" : "confirmed",
    title: `${titleFromKey(task.task_type)} · revision ${task.revision}`,
    subtitle: `${task.session_ids.length} session${task.session_ids.length === 1 ? "" : "s"} · project ${shortId(task.project_id)}`,
    projectId: task.project_id,
    provider: null,
    sessionCount: task.session_ids.length,
    lifecycle: run === null
      ? { source: "task_revision", status: task.lifecycle_state, label: `Confirmed by review · ${titleFromKey(task.lifecycle_state)}` }
      : { source: "analysis_run", status: run.status, label: `Confirmed by review · analysis ${run.status}` },
    provenance: run === null
      ? { origin: "Task revision", version: `revision ${task.revision}`, fingerprint: task.input_fingerprint, dataTier: null }
      : { origin: run.metric_pack_key, version: `pack v${run.metric_pack_version} · engine ${run.metric_engine_version} · schema ${run.schema_version}`, fingerprint: run.input_fingerprint, dataTier: run.data_tier },
    readiness: taskReadiness(run),
    occurredAt: task.created_at,
    endedAt: run?.finished_at ?? null,
    confidence: null,
    coverage: null,
    route: { name: "task", taskId: task.task_id, revision: task.revision },
  };
}

/** Items in stable chronological order (occurredAt, then id). */
export function projectTaskFlow(sources: TaskFlowSources): TaskFlowItem[] {
  const items = [
    ...sources.candidates.map(candidateItem),
    ...sources.tasks.map((task) => taskItem(task, sources.runs)),
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

/** Time scale over every valid item timestamp; degenerate ranges get a padded day so items still separate. */
export function taskFlowTimelineScale(items: readonly TaskFlowItem[]): TaskFlowTimelineScale | null {
  const stamps = items
    .flatMap((item) => [item.occurredAt, item.endedAt])
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
