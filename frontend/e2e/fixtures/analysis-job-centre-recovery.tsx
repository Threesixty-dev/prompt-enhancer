import { useCallback, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { AnalysisJobCentre } from "../../src/features/analysis-job-centre/AnalysisJobCentre";
import type {
  AnalysisJobPage,
  AnalysisJobRecord,
  AnalysisJobState,
  PromptEnhancerTransport,
} from "../../src/shared/api/contracts";
import {
  parseAnalysisJobPage,
  parseAnalysisJobRecord,
  TransportError,
} from "../../src/shared/api/httpTransport";
import { createSyntheticTransport } from "../../src/shared/api/syntheticTransport";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";

const JOB_A_ID = "a".repeat(64);
const JOB_B_ID = "b".repeat(64);
type Mode = "cancel-absence" | "cancel-deferred-absence" | "cancel-fail-once" | "detail-absence";
type Counter = "list" | "detail" | "cancel";
type Counters = Record<Counter, number>;

function readMode(): Mode {
  const mode = new URLSearchParams(location.search).get("mode");
  return mode === "cancel-deferred-absence" || mode === "cancel-fail-once" || mode === "detail-absence"
    ? mode
    : "cancel-absence";
}

function job(
  jobId: string,
  sessionId: string,
  state: AnalysisJobState = "queued",
  inputFingerprint = "c".repeat(64),
  updatedAt = "2040-01-01T00:00:00Z",
): AnalysisJobRecord {
  const terminal = ["completed", "partial", "failed", "cancelled", "superseded"].includes(state);
  return parseAnalysisJobRecord({
    job_id: jobId,
    identity: {
      kind: "synthetic_validation",
      provider: "synthetic",
      project_id: "e".repeat(64),
      session_id: sessionId,
      input_fingerprint: inputFingerprint,
      provenance_fingerprint: "d".repeat(64),
      metric_keys: ["prompt.goal_definition", "prompt.task_definition"],
      estimator_plan_version: "synthetic-plan-v1",
      redactor_version: "synthetic-redactor-v1",
      provider_schema_version: "synthetic-schema-v1",
      automation_grant_id: null,
      local_only: true,
    },
    state,
    stage_number: null,
    progress_completed: state === "completed" ? 4 : state === "awaiting_approval" ? 2 : 0,
    progress_total: 4,
    attempt_count: 0,
    max_attempts: 3,
    available_at: "2040-01-01T00:00:00Z",
    cancel_requested: false,
    last_error_code: null,
    terminal_reason_code: terminal ? state : null,
    created_at: "2040-01-01T00:00:00Z",
    updated_at: updatedAt,
    terminal_at: terminal ? "2040-01-01T00:00:00Z" : null,
  }, jobId);
}

const ORIGINAL_A = job(JOB_A_ID, "1".repeat(64));
const RETAINED_B = job(JOB_B_ID, "2".repeat(64), "completed");
const CURRENT_A = job(
  JOB_A_ID,
  "1".repeat(64),
  "awaiting_approval",
  "c".repeat(64),
  "2040-01-01T00:01:00Z",
);

function Fixture() {
  const mode = readMode();
  const queueRef = useRef<AnalysisJobRecord[]>([ORIGINAL_A, RETAINED_B]);
  const cancelAttempts = useRef(0);
  const deferredCancel = useRef<(() => void) | null>(null);
  const detailAbsenceDelivered = useRef(false);
  const [counters, setCounters] = useState<Counters>({ list: 0, detail: 0, cancel: 0 });
  const [deferredCancelPending, setDeferredCancelPending] = useState(false);
  const base = useMemo(() => createSyntheticTransport(), []);
  const increment = useCallback((counter: Counter) => {
    setCounters((current) => ({ ...current, [counter]: current[counter] + 1 }));
  }, []);
  const transport = useMemo<PromptEnhancerTransport>(() => ({
    ...base,
    listAnalysisJobs: async (
      state: AnalysisJobState | null = null,
      limit = 25,
      offset = 0,
    ): Promise<AnalysisJobPage> => {
      increment("list");
      const jobs = queueRef.current.filter((item) => state === null || item.state === state);
      return parseAnalysisJobPage({ jobs, limit, offset }, limit, offset, state);
    },
    getAnalysisJob: async (jobId: string): Promise<AnalysisJobRecord> => {
      increment("detail");
      if (mode === "detail-absence" && jobId === JOB_A_ID && !detailAbsenceDelivered.current) {
        detailAbsenceDelivered.current = true;
        queueRef.current = [RETAINED_B];
        throw new TransportError("Synthetic detail absence", 404, "analysis_job_not_found");
      }
      const found = queueRef.current.find((item) => item.job_id === jobId);
      if (!found) throw new TransportError("Synthetic absent detail", 404, "analysis_job_not_found");
      return structuredClone(found);
    },
    cancelAnalysisJob: async (jobId: string): Promise<AnalysisJobRecord> => {
      increment("cancel");
      const found = queueRef.current.find((item) => item.job_id === jobId);
      if (!found) throw new TransportError("Synthetic absent cancellation", 404, "analysis_job_not_found");
      if (mode === "cancel-absence") {
        queueRef.current = queueRef.current.filter((item) => item.job_id !== jobId);
        throw new TransportError("Synthetic authoritative cancellation absence", 404, "analysis_job_not_found");
      }
      if (mode === "cancel-deferred-absence") {
        await new Promise<void>((resolve) => {
          deferredCancel.current = resolve;
          setDeferredCancelPending(true);
        });
        deferredCancel.current = null;
        setDeferredCancelPending(false);
        queueRef.current = queueRef.current.filter((item) => item.job_id !== jobId);
        throw new TransportError("Synthetic deferred cancellation absence", 404, "analysis_job_not_found");
      }
      if (mode === "cancel-fail-once" && cancelAttempts.current++ === 0) {
        throw new TransportError("Synthetic cancellation service unavailable", 503);
      }
      const cancelled = parseAnalysisJobRecord({
        ...found,
        state: "cancelled",
        terminal_reason_code: "cancellation_requested",
        terminal_at: "2040-01-01T00:01:00Z",
        updated_at: "2040-01-01T00:01:00Z",
      }, jobId);
      queueRef.current = queueRef.current.map((item) => item.job_id === jobId ? cancelled : item);
      return cancelled;
    },
  }), [base, increment, mode]);

  return (
    <main>
      <p className="eyebrow">Synthetic local-real analysis-job receipt fixture · parser-valid and content-free</p>
      {mode === "detail-absence" && (
        <button
          onClick={() => { queueRef.current = [CURRENT_A, RETAINED_B]; }}
          type="button"
        >
          Restore synthetic current receipt
        </button>
      )}
      {mode === "cancel-deferred-absence" && (
        <button
          disabled={!deferredCancelPending}
          onClick={() => deferredCancel.current?.()}
          type="button"
        >
          Release synthetic cancellation absence
        </button>
      )}
      <output data-testid="analysis-job-list-count">List reads: {counters.list}</output>
      <output data-testid="analysis-job-detail-count">Detail reads: {counters.detail}</output>
      <output data-testid="analysis-job-cancel-count">Cancel requests: {counters.cancel}</output>
      <AnalysisJobCentre
        runtimeMode="local_real"
        serviceState="available"
        transport={transport}
      />
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<Fixture />);
