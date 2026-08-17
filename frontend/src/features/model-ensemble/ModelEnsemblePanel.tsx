import { useEffect, useRef, useState } from "react";
import type {
  ModelEnsembleRun,
  ModelEnsembleCanonicalHead,
  ModelEnsembleTrajectoryPage,
  ModelEnsembleWatchSnapshot,
  PromptEnhancerTransport,
  ProviderCompatibilityStatus,
  SessionTextAnalysisCapability,
} from "../../shared/api/contracts";
import { nextIdempotencyKey } from "../../shared/api/idempotency";
import type { MetricCategory } from "../../shared/platform/platform";
import { promptTextCompatibilityBlocker } from "../provider-compatibility";
import type { ModelEnsembleLensId, ModelEnsembleRadarData } from "./ModelEnsembleRadar";
import {
  MetricWorkspace,
  modelEnsembleTrajectoryRadarData,
} from "./MetricWorkspace";
import { MODEL_ENSEMBLE_DEFAULT_MAX_MESSAGES } from "./modelEnsembleConstants";

const TERMINAL_SOURCE_REASONS = new Set([
  "source_selection_limit",
  "source_provider_response_limit",
  "source_thread_structure_limit",
  "source_preview_window_limit",
  "source_resource_limit",
]);

function statusOf(error: unknown): number | null {
  return typeof error === "object" && error !== null && "status" in error &&
    typeof error.status === "number" ? error.status : null;
}

function reasonOf(error: unknown): string | null {
  return typeof error === "object" && error !== null && "reasonCode" in error &&
    typeof error.reasonCode === "string" ? error.reasonCode : null;
}

function runErrorCopy(error: unknown): string {
  const reason = reasonOf(error);
  if (reason === "redacted_content_consent_required") {
    return "Grant redacted-text access in Local sources before running the ensemble.";
  }
  if (reason === "session_not_in_safe_index") {
    return "This session is no longer in the safe index. Refresh Local sources first.";
  }
  if (reason === "provider_compatibility_blocked") {
    return "Installed Codex compatibility is not verified. Recheck it before running models.";
  }
  if (reason === "local_model_ensemble_execution_failed") {
    return "One or more pinned local models could not complete the serial pipeline. Verify the local model cache and runtime dependencies.";
  }
  if (reason === "model_ensemble_persistence_failed") {
    return "The content-free chunk and model receipts could not be stored locally.";
  }
  if (TERMINAL_SOURCE_REASONS.has(reason ?? "")) {
    return "The selected session is outside this adapter version's bounded local read. No shadow result was stored.";
  }
  if (reason === "source_timeout" || reason === "provider_unavailable") {
    return "The local Codex read timed out or became unavailable. Keep Codex open and retry once.";
  }
  if (statusOf(error) === 501) {
    return "The local probabilistic analysis is available only in the integrated local app.";
  }
  return "The local analysis did not complete. The error contains no session text.";
}

function blocker(
  capability: SessionTextAnalysisCapability | null,
  compatibility: ProviderCompatibilityStatus | null,
  compatibilityLoading: boolean,
): string | null {
  if (capability === null) return "Checking local redacted-text access.";
  if (!capability.available) {
    return capability.reason_code === "redacted_content_consent_required"
      ? "Grant redacted-text access in Local sources first."
      : "This installation cannot read the selected session through the bounded adapter.";
  }
  if (compatibilityLoading) return "Checking installed Codex compatibility.";
  return promptTextCompatibilityBlocker(compatibility) === null
    ? null
    : "Recheck installed Codex compatibility before running the ensemble.";
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}

export function ModelEnsemblePanel({
  projectId,
  sessionId,
  category,
  transport,
  analysisCapability,
  providerCompatibility,
  compatibilityLoading = false,
}: {
  projectId: string;
  sessionId: string;
  category: MetricCategory;
  transport: PromptEnhancerTransport;
  analysisCapability: SessionTextAnalysisCapability | null;
  providerCompatibility: ProviderCompatibilityStatus | null;
  compatibilityLoading?: boolean;
}) {
  const [run, setRun] = useState<ModelEnsembleRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [watch, setWatch] = useState<ModelEnsembleWatchSnapshot | null>(null);
  const [canonicalHead, setCanonicalHead] = useState<ModelEnsembleCanonicalHead | null>(null);
  const [trajectory, setTrajectory] = useState<ModelEnsembleTrajectoryPage | null>(null);
  const [trajectoryError, setTrajectoryError] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [historicalRun, setHistoricalRun] = useState<ModelEnsembleRun | null>(null);
  const [watchChanging, setWatchChanging] = useState(false);
  const [lensId, setLensId] = useState<ModelEnsembleLensId>(
    category === "prompt-quality" ? "task-framing" : "reasoning-trace",
  );
  const controllerRef = useRef<AbortController | null>(null);
  const runRef = useRef<ModelEnsembleRun | null>(null);
  const canonicalHeadRef = useRef<ModelEnsembleCanonicalHead | null>(null);
  const followingLive = useRef(true);
  const blocked = blocker(analysisCapability, providerCompatibility, compatibilityLoading);
  const supportsCanonicalSnapshots = transport.getSessionModelEnsembleCanonicalHead !== undefined
    && transport.getModelEnsembleSnapshot !== undefined;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setRun(null);
    if (supportsCanonicalSnapshots) {
      return () => controller.abort();
    }
    transport.getLatestModelEnsemble(sessionId, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        const exactHead = canonicalHeadRef.current;
        if (
          exactHead?.watch.session_id === sessionId
          && exactHead.head_run_id !== value.run_id
        ) return;
        setRun(value);
      })
      .catch((loadError: unknown) => {
        if (!controller.signal.aborted && statusOf(loadError) !== 404) {
          setError("The stored shadow ensemble could not be validated or loaded.");
        }
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [sessionId, supportsCanonicalSnapshots, transport]);

  const trajectoryWatchId = watch?.watch.session_id === sessionId
    && watch.watch.state !== "disabled"
    ? watch.watch.watch_id
    : null;
  const trajectoryHeadRunId = run?.run_id ?? null;

  useEffect(() => {
    if (trajectoryWatchId === null || trajectoryHeadRunId === null || transport.getModelEnsembleTrajectory === undefined) {
      setTrajectory(null);
      setTrajectoryError(false);
      setSelectedRunId(null);
      followingLive.current = true;
      return;
    }
    if (followingLive.current) setSelectedRunId(trajectoryHeadRunId);
    const controller = new AbortController();
    transport.getModelEnsembleTrajectory(trajectoryWatchId, 24, undefined, controller.signal)
      .then((page) => {
        if (controller.signal.aborted || page.watch_id !== trajectoryWatchId) return;
        if (page.head_run_id !== trajectoryHeadRunId) {
          setTrajectoryError(page.head_run_id !== null);
          return;
        }
        setTrajectory(page);
        setTrajectoryError(false);
        setSelectedRunId((current) => {
          if (followingLive.current) return page.head_run_id;
          if (current !== null && page.points.some((point) => point.run_id === current)) return current;
          followingLive.current = true;
          return page.head_run_id;
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) setTrajectoryError(true);
      });
    return () => controller.abort();
  }, [trajectoryHeadRunId, trajectoryWatchId, transport]);

  useEffect(() => () => controllerRef.current?.abort(), []);
  useEffect(() => { runRef.current = run; }, [run]);

  useEffect(() => {
    setLensId(category === "prompt-quality" ? "task-framing" : "reasoning-trace");
  }, [category]);

  useEffect(() => {
    if (transport.getSessionModelEnsembleCanonicalHead === undefined && transport.getActiveModelEnsembleWatch === undefined) return;
    let stopped = false;
    let timer: number | undefined;
    const controller = new AbortController();
    const poll = async () => {
      try {
        if (transport.getSessionModelEnsembleCanonicalHead !== undefined && transport.getModelEnsembleSnapshot !== undefined) {
          const head = await transport.getSessionModelEnsembleCanonicalHead(sessionId, controller.signal);
          if (stopped) return;
          if (head.watch.session_id !== sessionId) throw new Error("durable_watch_identity_mismatch");
          canonicalHeadRef.current = head;
          let latestRun = runRef.current;
          if (head.head_run_id === null) {
            latestRun = null;
          } else if (latestRun?.run_id !== head.head_run_id) {
            latestRun = await transport.getModelEnsembleSnapshot(head.head_run_id!, controller.signal);
            if (stopped || latestRun.run_id !== head.head_run_id) return;
          }
          setCanonicalHead(head);
          setWatch({ watch: head.watch, latest_run: latestRun });
          setRun(latestRun);
          setLoading(false);
          timer = window.setTimeout(() => void poll(), head.latest_attempt?.state === "running" ? 2_000 : 15_000);
          return;
        }
        const snapshot = await transport.getActiveModelEnsembleWatch!(controller.signal);
        if (stopped) return;
        canonicalHeadRef.current = null;
        setWatch(snapshot);
        setCanonicalHead(null);
        if (snapshot.watch.session_id === sessionId) {
          setRun(snapshot.latest_run);
        }
        setLoading(false);
        timer = window.setTimeout(
          () => void poll(),
          snapshot.watch.state === "running" || snapshot.watch.state === "queued" ? 2_000 : 15_000,
        );
      } catch (watchError) {
        if (stopped || controller.signal.aborted) return;
        setLoading(false);
        if (statusOf(watchError) === 404) {
          canonicalHeadRef.current = null;
          setCanonicalHead(null);
          setWatch(null);
          if (supportsCanonicalSnapshots) setRun(null);
          setLoading(false);
        }
        timer = window.setTimeout(() => void poll(), 15_000);
      }
    };
    void poll();
    return () => {
      stopped = true;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [sessionId, supportsCanonicalSnapshots, transport]);

  async function start() {
    if (running || blocked !== null || durableAttemptRunning || watchQueued || legacyWatchBusy) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setRunning(true);
    setError("");
    try {
      if (transport.enqueueModelEnsembleAnalysis !== undefined) {
        let activeWatch = watch;
        if (
          activeWatch === null
          || activeWatch.watch.session_id !== sessionId
          || activeWatch.watch.state === "disabled"
        ) {
          if (transport.enableModelEnsembleWatch === undefined) throw new Error("durable_watch_unavailable");
          activeWatch = await transport.enableModelEnsembleWatch(sessionId, {
            project_id: projectId,
            max_messages: MODEL_ENSEMBLE_DEFAULT_MAX_MESSAGES,
            confirmation: "continuously_analyze_selected_redacted_session",
          }, controller.signal);
          if (controller.signal.aborted) return;
          setWatch(activeWatch);
        }
        const head = await transport.enqueueModelEnsembleAnalysis(activeWatch.watch.watch_id, controller.signal);
        if (controller.signal.aborted) return;
        if (head.watch.session_id !== sessionId) throw new Error("durable_watch_identity_mismatch");
        let exactRun = runRef.current;
        if (head.head_run_id === null) {
          exactRun = null;
        } else if (exactRun?.run_id !== head.head_run_id) {
          if (transport.getModelEnsembleSnapshot === undefined) throw new Error("durable_snapshot_unavailable");
          exactRun = await transport.getModelEnsembleSnapshot(head.head_run_id, controller.signal);
          if (controller.signal.aborted || exactRun.run_id !== head.head_run_id) return;
        }
        setCanonicalHead(head);
        canonicalHeadRef.current = head;
        setRun(exactRun);
        setWatch({ watch: head.watch, latest_run: exactRun });
        followingLive.current = true;
      } else {
        const outcome = await transport.startModelEnsemble(
          sessionId,
          { confirmation: "run_ten_local_models_on_selected_redacted_text" },
          nextIdempotencyKey("model-ensemble"),
          controller.signal,
        );
        if (!controller.signal.aborted) setRun(outcome.run);
      }
    } catch (runError) {
      if (!controller.signal.aborted) setError(runErrorCopy(runError));
    } finally {
      if (!controller.signal.aborted) setRunning(false);
      controllerRef.current = null;
    }
  }

  function cancelWait() {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setRunning(false);
  }

  async function cancelAnalysis() {
    if (
      running
      || canonicalHead?.latest_attempt?.state !== "running"
      || transport.cancelModelEnsembleAnalysis === undefined
    ) return;
    setRunning(true);
    setError("");
    try {
      const head = await transport.cancelModelEnsembleAnalysis(canonicalHead.watch.watch_id);
      if (head.watch.session_id !== sessionId) throw new Error("durable_watch_identity_mismatch");
      let exactRun = runRef.current;
      if (head.head_run_id === null) {
        exactRun = null;
      } else if (exactRun?.run_id !== head.head_run_id) {
        if (transport.getModelEnsembleSnapshot === undefined) throw new Error("durable_snapshot_unavailable");
        exactRun = await transport.getModelEnsembleSnapshot(head.head_run_id);
        if (exactRun.run_id !== head.head_run_id) throw new Error("durable_snapshot_identity_mismatch");
      }
      canonicalHeadRef.current = head;
      setCanonicalHead(head);
      setRun(exactRun);
      setWatch({ watch: head.watch, latest_run: exactRun });
    } catch {
      setError("Cancellation could not be confirmed. The latest sealed snapshot remains visible.");
    } finally {
      setRunning(false);
    }
  }

  async function toggleWatch() {
    if (watchChanging) return;
    setWatchChanging(true);
    setError("");
    try {
      const currentForSession = watch?.watch.session_id === sessionId && watch.watch.state !== "disabled";
      const snapshot = currentForSession
        ? await transport.disableModelEnsembleWatch?.(watch.watch.watch_id)
        : await transport.enableModelEnsembleWatch?.(sessionId, {
            project_id: projectId,
            max_messages: MODEL_ENSEMBLE_DEFAULT_MAX_MESSAGES,
            confirmation: "continuously_analyze_selected_redacted_session",
          });
      if (snapshot !== undefined) {
        setCanonicalHead(null);
        canonicalHeadRef.current = null;
        setWatch(snapshot.watch.state === "disabled" ? null : snapshot);
        setRun(snapshot.latest_run);
      } else {
        setError("Continuous local analysis is available only in the integrated desktop app.");
      }
    } catch {
      setError("The continuous local watch could not be changed. No session text was retained.");
    } finally {
      setWatchChanging(false);
    }
  }

  const durableAttemptRunning = canonicalHead?.watch.session_id === sessionId
    && canonicalHead.latest_attempt?.state === "running";
  const watchQueued = watch?.watch.session_id === sessionId
    && watch.watch.state === "queued"
    && !durableAttemptRunning;
  const legacyWatchBusy = canonicalHead === null
    && watch?.watch.session_id === sessionId
    && watch.watch.state === "running";
  const visibleTrajectory = trajectory?.watch_id === trajectoryWatchId ? trajectory : null;
  const trajectoryPoints = visibleTrajectory?.points ?? [];
  const selectedPointIndex = trajectoryPoints.findIndex((point) => point.run_id === selectedRunId);
  const selectedPoint = selectedPointIndex < 0 ? null : trajectoryPoints[selectedPointIndex];
  const historicalRunId = selectedPoint !== null && selectedPoint.run_id !== run?.run_id
    ? selectedPoint.run_id
    : null;
  useEffect(() => {
    if (historicalRunId === null || transport.getModelEnsembleSnapshot === undefined) {
      setHistoricalRun(null);
      return;
    }
    const controller = new AbortController();
    setHistoricalRun(null);
    transport.getModelEnsembleSnapshot(historicalRunId, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted && value.run_id === historicalRunId) setHistoricalRun(value);
      })
      .catch(() => { if (!controller.signal.aborted) setHistoricalRun(null); });
    return () => controller.abort();
  }, [historicalRunId, transport]);
  const selectedRadarRun: ModelEnsembleRadarData | null = selectedPoint === null
    ? run
    : selectedPoint.run_id === run?.run_id
      ? run
      : historicalRun?.run_id === selectedPoint.run_id
        ? historicalRun
        : modelEnsembleTrajectoryRadarData(selectedPoint);
  const comparisonPoint = selectedPointIndex >= 0
    ? trajectoryPoints[selectedPointIndex + 1] ?? null
    : null;
  const comparisonRadarRun = selectedPoint !== null
    && comparisonPoint !== null
    && selectedPoint.comparable_to_head
    && comparisonPoint.comparable_to_head
    && selectedPoint.max_messages === comparisonPoint.max_messages
    ? modelEnsembleTrajectoryRadarData(comparisonPoint)
    : null;

  function selectTrajectoryRun(runId: string) {
    followingLive.current = runId === trajectoryHeadRunId;
    setSelectedRunId(runId);
  }

  return (
    <section aria-labelledby="model-ensemble-title" className="model-ensemble">
      <header className="model-ensemble__header">
        <div>
          <p className="eyebrow">Typed evidence + experimental model ranges</p>
          <h2 id="model-ensemble-title">Measure the session, then estimate every eligible axis locally</h2>
          <p>
            Typed evidence forms the solid radar. A gated multilingual factor lane
            runs pinned small models one at a time to produce a separate experimental
            range. Each child exits before the next model can use RAM or GPU memory.
          </p>
        </div>
        {durableAttemptRunning ? (
          <button className="button button--secondary" disabled={running} onClick={() => void cancelAnalysis()} type="button">
            {running ? "Cancelling…" : "Cancel analysis"}
          </button>
        ) : watchQueued ? (
          <button className="button button--secondary" disabled type="button">Analysis queued</button>
        ) : legacyWatchBusy ? (
          <button className="button button--secondary" disabled type="button">Analysis active</button>
        ) : running ? (
          <button className="button button--secondary" onClick={cancelWait} type="button">
            {transport.enqueueModelEnsembleAnalysis === undefined ? "Cancel browser wait" : "Cancel queue request"}
          </button>
        ) : (
          <button className="button button--primary" disabled={blocked !== null} onClick={() => void start()} type="button">
            Analyze metric ranges
          </button>
        )}
      </header>
      <div className="model-ensemble__boundary" role="note">
          <strong>Solid measurements and model ranges stay separate</strong>
          <span>
          Versioned contracts supply evidence-backed numerators and denominators.
          Separate model markers are explicitly experimental until a metric passes
          calibration. They never erase evidence, turn missing states into zero, or
          treat prose as proof of an objective outcome.
        </span>
      </div>
      <div className="model-ensemble__watch">
        <div>
          <strong>Continuous local updates</strong>
          <span>
            {watch?.watch.session_id === sessionId
              ? watch.watch.state === "queued"
                ? "queued · waiting for the local model lane"
                : canonicalHead?.latest_attempt === null || canonicalHead?.latest_attempt === undefined
                ? `${watch.watch.state} · local pipeline ${watch.watch.progress_completed}/${watch.watch.progress_total}`
                : `${canonicalHead.latest_attempt.state} · ${canonicalHead.latest_attempt.progress_completed}/${canonicalHead.latest_attempt.progress_total} pipeline steps`
              : "Off for this session. One selected session can use the serial GPU/CPU lane."}
          </span>
        </div>
        <button
          className="button button--secondary"
          disabled={blocked !== null || watchChanging}
          onClick={() => void toggleWatch()}
          type="button"
        >
          {watchChanging
            ? "Updating…"
            : watch?.watch.session_id === sessionId && watch.watch.state !== "disabled"
              ? "Stop continuous updates"
              : "Watch this session"}
        </button>
      </div>
      <p aria-live="polite" className="model-ensemble__status" role="status">
        {durableAttemptRunning
          ? `Durable local analysis is running · ${canonicalHead.latest_attempt!.progress_completed}/${canonicalHead.latest_attempt!.progress_total} pipeline steps. The last sealed snapshot remains visible.`
          : watchQueued
            ? "Analysis is queued for the serial local model lane. The last sealed snapshot remains visible."
          : legacyWatchBusy
            ? `The local watch is ${watch!.watch.state}. The last sealed snapshot remains visible while canonical stage status loads.`
          : running
          ? transport.enqueueModelEnsembleAnalysis === undefined
            ? "Running the local factor pipeline one child at a time. Cancelling only stops this browser from waiting."
            : "Queueing a durable local analysis. The last sealed snapshot remains visible."
          : blocked ?? (run
            ? `Stored local analysis completed ${formatTimestamp(run.completed_at)}.`
            : "No measured + predictive analysis is stored for this session yet.")}
      </p>
      {error && <p className="model-ensemble__error" role="alert">{error}</p>}
      {loading ? (
        <p className="model-ensemble__empty">Loading stored content-free receipts…</p>
      ) : selectedRadarRun ? (
        <>
          {selectedPoint === null && run?.source_coverage_state === "incomplete_source" && (
            <p className="model-ensemble__error" role="note">
              The adapter could not prove the selected source window complete.
              This shadow shape reflects retained content only and is not a
              complete-session judgment.
            </p>
          )}
          <MetricWorkspace
            comparisonLabel="previous comparable publication"
            comparisonRun={comparisonRadarRun}
            history={visibleTrajectory === null ? undefined : {
              points: trajectoryPoints,
              headRunId: trajectoryHeadRunId ?? visibleTrajectory.head_run_id,
              selectedRunId: selectedPoint?.run_id ?? run?.run_id ?? null,
              onSelectRun: selectTrajectoryRun,
              error: trajectoryError,
            }}
            lensId={lensId}
            mode="full"
            onLensChange={setLensId}
            run={selectedRadarRun}
            runId={selectedPoint?.run_id ?? run?.run_id ?? ""}
            scopeLabel={selectedPoint !== null
              ? `Newest ${selectedPoint.max_messages} messages`
              : watch?.watch.session_id === sessionId
              ? `Newest ${watch.watch.max_messages} messages`
              : "Scope not exposed"}
            snapshotLabel={selectedPoint === null
              ? run?.source_coverage_state === "complete_window" ? "Sealed source window" : "Incomplete source window"
              : selectedPoint.run_id === visibleTrajectory?.head_run_id
                ? "Live published head"
                : "Earlier published snapshot"}
            stageRun={selectedPoint === null || selectedPoint.run_id === run?.run_id ? run : historicalRun}
            attemptStages={
              (selectedPoint === null || selectedPoint.run_id === run?.run_id)
              && canonicalHead?.watch.session_id === sessionId
                ? canonicalHead.stages
                : []
            }
            transport={transport}
          />
        </>
      ) : (
        <p className="model-ensemble__empty">
          Start one explicit run to create typed metric receipts plus content-free experimental ranges.
        </p>
      )}
    </section>
  );
}
