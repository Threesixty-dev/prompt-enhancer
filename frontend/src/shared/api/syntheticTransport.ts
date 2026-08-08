import type {
  AnalysisRun,
  CandidateListItem,
  CandidateStatusFilter,
  PromptEnhancerTransport,
  ReviewCommand,
  TaskAnalysisResponse,
  TaskRevision,
  TaskReviewResponse,
} from "./contracts";
import {
  SYNTHETIC_CANDIDATES,
  SYNTHETIC_RESULTS,
  SYNTHETIC_RUN,
  SYNTHETIC_TASKS,
} from "./syntheticFixtures";
import { TransportError } from "./httpTransport";

function copy<T>(value: T): T {
  return structuredClone(value);
}

function safeId(sequence: number): string {
  return sequence.toString(16).padStart(64, "0");
}

function candidateIds(command: ReviewCommand): string[] {
  if (command.action === "merge") return command.request.candidate_ids;
  return [command.request.candidate_id];
}

export function createSyntheticTransport(): PromptEnhancerTransport {
  let candidates = copy(SYNTHETIC_CANDIDATES);
  const tasks = copy(SYNTHETIC_TASKS);
  const decisions = new Map<string, TaskReviewResponse>();
  const analyses = new Map<string, TaskAnalysisResponse>();
  const runs: AnalysisRun[] = [copy(SYNTHETIC_RUN)];
  const resultsByRun = new Map([
    [SYNTHETIC_RUN.run_id, copy(SYNTHETIC_RESULTS)],
  ]);
  let sequence = 32;

  const findCandidates = (command: ReviewCommand): CandidateListItem[] => {
    const found = candidateIds(command).map((id) =>
      candidates.find((item) => item.candidate.candidate_id === id),
    );
    if (found.some((item) => item === undefined)) {
      throw new TransportError("Synthetic candidate was not found", 404);
    }
    return found as CandidateListItem[];
  };

  const assertVersions = (command: ReviewCommand, items: CandidateListItem[]) => {
    if (
      items.some(
        (item) =>
          item.candidate.discovery_version !== command.request.expected_discovery_version,
      )
    ) {
      throw new TransportError("Synthetic candidate version is stale", 409);
    }
  };

  return {
    async getCodexLocalSourceStatus() {
      throw new TransportError("Local sources are unavailable in synthetic preview", 404);
    },
    async grantCodexLocalHistoryConsent() {
      throw new TransportError("Local sources are unavailable in synthetic preview", 404);
    },
    async revokeCodexLocalHistoryConsent() {
      throw new TransportError("Local sources are unavailable in synthetic preview", 404);
    },
    async indexCodexLocalSessions() {
      throw new TransportError("Local sources are unavailable in synthetic preview", 404);
    },
    async analyzeCodexLocalSessions() {
      throw new TransportError("Local sources are unavailable in synthetic preview", 404);
    },
    async enrichCodexDisplayLabels() {
      throw new TransportError("Local sources are unavailable in synthetic preview", 404);
    },
    async setManualDisplayLabel() {
      throw new TransportError("Local sources are unavailable in synthetic preview", 404);
    },
    async clearManualDisplayLabel() {
      throw new TransportError("Local sources are unavailable in synthetic preview", 404);
    },
    async listCodexSessions() {
      throw new TransportError("Local sources are unavailable in synthetic preview", 404);
    },
    async getSessionMetrics() {
      throw new TransportError("Local sources are unavailable in synthetic preview", 404);
    },
    async listCandidates(status: CandidateStatusFilter = "all") {
      const filtered =
        status === "all"
          ? candidates
          : candidates.filter((item) => item.decision_status === status);
      return { candidates: copy(filtered), limit: 100, offset: 0 };
    },
    async listTaskRevisions(taskId?: string) {
      const filtered = taskId ? tasks.filter((task) => task.task_id === taskId) : tasks;
      return { tasks: copy(filtered), limit: 100, offset: 0 };
    },
    async getTaskRevision(taskId: string, revision: number) {
      const task = tasks.find(
        (item) => item.task_id === taskId && item.revision === revision,
      );
      if (!task) throw new TransportError("Synthetic task revision was not found", 404);
      return { task: copy(task) };
    },
    async listAnalysisRuns(taskId?: string) {
      const filtered = taskId ? runs.filter((run) => run.task_id === taskId) : runs;
      return { runs: copy(filtered), limit: 100, offset: 0 };
    },
    async getAnalysisRun(runId: string) {
      const run = runs.find((item) => item.run_id === runId);
      const results = resultsByRun.get(runId);
      if (!run || !results) {
        throw new TransportError("Synthetic analysis run was not found", 404);
      }
      return { run: copy(run), results: copy(results) };
    },
    async review(command, idempotencyKey) {
      const cached = decisions.get(idempotencyKey);
      if (cached) return copy({ ...cached, applied: false });

      const items = findCandidates(command);
      assertVersions(command, items);
      if (items.some((item) => item.decision_status === "decided")) {
        throw new TransportError("Synthetic candidate was already decided", 409);
      }

      const decisionId = safeId(sequence++);
      const outputRevisions: { task_id: string; revision: number }[] = [];
      const createdTasks: TaskRevision[] = [];

      if (command.action === "accept" || command.action === "merge") {
        const taskId = safeId(sequence++);
        const sessions = items.flatMap((item) => item.candidate.session_ids);
        createdTasks.push({
          task_id: taskId,
          revision: 1,
          project_id: items[0].candidate.project_id,
          task_type: command.request.task_category,
          lifecycle_state: "reviewed",
          session_ids: sessions,
          input_fingerprint: safeId(sequence++),
          created_at: "2040-01-02T12:00:00Z",
        });
        outputRevisions.push({ task_id: taskId, revision: 1 });
      }

      if (command.action === "split") {
        command.request.partitions.forEach((sessions, index) => {
          const taskId = safeId(sequence++);
          createdTasks.push({
            task_id: taskId,
            revision: 1,
            project_id: items[0].candidate.project_id,
            task_type: command.request.task_categories[index] ?? "unknown",
            lifecycle_state: "reviewed",
            session_ids: [...sessions],
            input_fingerprint: safeId(sequence++),
            created_at: "2040-01-02T12:00:00Z",
          });
          outputRevisions.push({ task_id: taskId, revision: 1 });
        });
      }

      tasks.unshift(...createdTasks);
      const reviewedIds = new Set(items.map((item) => item.candidate.candidate_id));
      candidates = candidates.map((item) =>
        reviewedIds.has(item.candidate.candidate_id)
          ? {
              ...item,
              decision_status: "decided",
              decision_id: decisionId,
              decision_action: command.action,
            }
          : item,
      );

      const result: TaskReviewResponse = {
        decision_id: decisionId,
        action: command.action,
        output_revisions: outputRevisions,
        applied: true,
      };
      decisions.set(idempotencyKey, result);
      return copy(result);
    },
    async startAnalysis(taskId, revision, idempotencyKey) {
      const cached = analyses.get(idempotencyKey);
      if (cached) return copy({ ...cached, applied: false });
      const task = tasks.find(
        (item) => item.task_id === taskId && item.revision === revision,
      );
      if (!task) {
        throw new TransportError("Synthetic task revision was not found", 404);
      }

      const runId = safeId(sequence++);
      const run: AnalysisRun = {
        ...SYNTHETIC_RUN,
        run_id: runId,
        task_id: taskId,
        task_revision: revision,
        input_fingerprint: task.input_fingerprint,
        started_at: "2040-01-02T12:01:00Z",
        finished_at: "2040-01-02T12:01:02Z",
      };
      const results = SYNTHETIC_RESULTS.map((result) => {
        const sessionCount = result.key === "task.workflow.session_count";
        const sessionScoped =
          result.key.startsWith("task.workflow.") ||
          result.key.startsWith("task.efficiency.") ||
          result.key === "task.verification.observed_count";
        return {
          ...result,
          value_state: sessionCount ? "known" as const : "unknown" as const,
          numeric_value: sessionCount ? task.session_ids.length : null,
          observed_count: sessionCount ? task.session_ids.length : 0,
          eligible_count: sessionCount
            ? task.session_ids.length
            : sessionScoped
              ? task.session_ids.length
              : 0,
          coverage: sessionCount ? 1 : 0,
          confidence: sessionCount ? 1 : null,
          evidence_event_ids: [],
          computed_at: "2040-01-02T12:01:01Z",
        };
      });
      runs.unshift(run);
      resultsByRun.set(runId, results);

      const outcome: TaskAnalysisResponse = {
        run_id: runId,
        status: "completed",
        result_count: results.length,
        applied: true,
      };
      analyses.set(idempotencyKey, outcome);
      return copy(outcome);
    },
  };
}
