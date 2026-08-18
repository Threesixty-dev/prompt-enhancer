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
import { MetricDefinitionsOutOfDateError, type MetricDefinitionMismatch } from "../../shared/api/metricPublicationV2Contract";
import type { MetricCategory } from "../../shared/platform/platform";
import { promptTextCompatibilityBlocker } from "../provider-compatibility";
import type { ModelEnsembleLensId } from "./metricAxisModel";
import { METRIC_DEFINITIONS_OUT_OF_DATE_TITLE, MetricDefinitionsOutOfDateAlert } from "./MetricDefinitionsAlert";
import { MetricWorkspace } from "./MetricWorkspace";
import { MODEL_ENSEMBLE_DEFAULT_MAX_MESSAGES } from "./modelEnsembleConstants";
import { useTrajectorySelection } from "./useTrajectorySelection";
import {
  CANONICAL_POLL_IDLE_MS,
  CANONICAL_POLL_RETRY_MS,
  CANONICAL_POLL_WRONG_RUN_MS,
  TRAJECTORY_RETRY_LIMIT,
  TRAJECTORY_RETRY_MS,
  PollCoordinator,
  canonicalHeadIdentity,
  canonicalHeadPollDelay,
  httpStatusOf as statusOf,
  isStaleWatchHead,
  watchSnapshotIdentity,
  watchSnapshotPollDelay,
} from "./canonicalPolling";

const TERMINAL_SOURCE_REASONS = new Set([
  "source_selection_limit",
  "source_provider_response_limit",
  "source_thread_structure_limit",
  "source_preview_window_limit",
  "source_resource_limit",
]);

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
  /** Compatibility-gate refusal: clears every retained value; never rendered as a load error. */
  const [definitionsOutOfDate, setDefinitionsOutOfDate] = useState<MetricDefinitionMismatch | null>(null);
  const [watch, setWatch] = useState<ModelEnsembleWatchSnapshot | null>(null);
  const [canonicalHead, setCanonicalHead] = useState<ModelEnsembleCanonicalHead | null>(null);
  const [trajectory, setTrajectory] = useState<ModelEnsembleTrajectoryPage | null>(null);
  const [trajectoryError, setTrajectoryError] = useState(false);
  /**
   * The history page (not the live head) was published under other definitions.
   * Scoped to the history so a compatible live receipt is neither hidden nor
   * flashed: the head poll owns `definitionsOutOfDate`, this owns the drawer.
   */
  const [trajectoryDefinitionsMismatch, setTrajectoryDefinitionsMismatch] = useState<MetricDefinitionMismatch | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [watchChanging, setWatchChanging] = useState(false);
  const [lensId, setLensId] = useState<ModelEnsembleLensId>(
    category === "prompt-quality" ? "task-framing" : "reasoning-trace",
  );
  const controllerRef = useRef<AbortController | null>(null);
  const runRef = useRef<ModelEnsembleRun | null>(null);
  const watchRef = useRef<ModelEnsembleWatchSnapshot | null>(null);
  const canonicalHeadRef = useRef<ModelEnsembleCanonicalHead | null>(null);
  const coordinatorRef = useRef<PollCoordinator | null>(null);
  const followingLive = useRef(true);
  const blocked = blocker(analysisCapability, providerCompatibility, compatibilityLoading);
  const supportsCanonicalSnapshots = transport.getSessionModelEnsembleCanonicalHead !== undefined
    && transport.getModelEnsembleSnapshot !== undefined;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setRun(null);
    runRef.current = null;
    setDefinitionsOutOfDate(null);
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
        setDefinitionsOutOfDate(null);
        setRun(value);
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) return;
        if (loadError instanceof MetricDefinitionsOutOfDateError) {
          setDefinitionsOutOfDate(loadError.mismatch);
          runRef.current = null;
          setRun(null);
          return;
        }
        if (statusOf(loadError) !== 404) {
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
      setTrajectoryDefinitionsMismatch(null);
      setSelectedRunId(null);
      followingLive.current = true;
      return;
    }
    if (followingLive.current) setSelectedRunId(trajectoryHeadRunId);
    const controller = new AbortController();
    let retryTimer: number | undefined;
    let attempts = 0;
    const fetchTrajectory = transport.getModelEnsembleTrajectory;
    const load = () => {
      attempts += 1;
      fetchTrajectory(trajectoryWatchId, 24, undefined, controller.signal)
        .then((page) => {
          if (controller.signal.aborted || page.watch_id !== trajectoryWatchId) return;
          if (page.head_run_id !== trajectoryHeadRunId) {
            // Publication race between the exact head and the trajectory index:
            // keep the previously loaded history and retry a bounded number of times.
            setTrajectoryError(page.head_run_id !== null);
            if (attempts < TRAJECTORY_RETRY_LIMIT) {
              retryTimer = window.setTimeout(() => {
                retryTimer = undefined;
                if (!controller.signal.aborted) load();
              }, TRAJECTORY_RETRY_MS);
            }
            return;
          }
          setTrajectory(page);
          setTrajectoryError(false);
          setTrajectoryDefinitionsMismatch(null);
          setSelectedRunId((current) => {
            if (followingLive.current) return page.head_run_id;
            if (current !== null && page.points.some((point) => point.run_id === current)) return current;
            followingLive.current = true;
            return page.head_run_id;
          });
        })
        .catch((trajectoryFailure: unknown) => {
          if (controller.signal.aborted) return;
          if (trajectoryFailure instanceof MetricDefinitionsOutOfDateError) {
            // History published under other definitions: withhold every history
            // point (no compact values, no comparison) and say why. The live head
            // stays governed by its own gate, so nothing compatible is hidden.
            setTrajectoryDefinitionsMismatch(trajectoryFailure.mismatch);
            setTrajectory(null);
            setSelectedRunId(trajectoryHeadRunId);
            followingLive.current = true;
          }
          setTrajectoryError(true);
        });
    };
    load();
    return () => {
      controller.abort();
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, [trajectoryHeadRunId, trajectoryWatchId, transport]);

  useEffect(() => () => controllerRef.current?.abort(), []);
  useEffect(() => { runRef.current = run; }, [run]);
  useEffect(() => { watchRef.current = watch; }, [watch]);
  useEffect(() => { canonicalHeadRef.current = canonicalHead; }, [canonicalHead]);

  /**
   * Applies head, watch, and run together so they can never disagree mid-render.
   * `nextRun === undefined` leaves the displayed run untouched (legacy watch
   * receipts for another session must not clear this session's stored run).
   */
  function applyCanonical(
    head: ModelEnsembleCanonicalHead | null,
    nextWatch: ModelEnsembleWatchSnapshot | null,
    nextRun: ModelEnsembleRun | null | undefined,
  ) {
    canonicalHeadRef.current = head;
    watchRef.current = nextWatch;
    setCanonicalHead(head);
    setWatch(nextWatch);
    if (nextRun !== undefined) {
      runRef.current = nextRun;
      setRun(nextRun);
    }
  }

  useEffect(() => {
    setLensId(category === "prompt-quality" ? "task-framing" : "reasoning-trace");
  }, [category]);

  useEffect(() => {
    if (transport.getSessionModelEnsembleCanonicalHead === undefined && transport.getActiveModelEnsembleWatch === undefined) return;
    const coordinator = new PollCoordinator(async (ticket) => {
      let head: ModelEnsembleCanonicalHead | null = null;
      let legacy: ModelEnsembleWatchSnapshot | null = null;
      try {
        if (supportsCanonicalSnapshots) {
          head = await transport.getSessionModelEnsembleCanonicalHead!(sessionId, ticket.signal);
        } else {
          legacy = await transport.getActiveModelEnsembleWatch!(ticket.signal);
        }
      } catch (watchError) {
        if (!ticket.isCurrent()) return;
        setLoading(false);
        if (watchError instanceof MetricDefinitionsOutOfDateError) {
          // Legacy watch snapshot embeds the run: a definitions mismatch clears
          // every retained value and is shown as a client-update state.
          setDefinitionsOutOfDate(watchError.mismatch);
          applyCanonical(null, null, null);
          coordinator.schedule(CANONICAL_POLL_IDLE_MS);
          return;
        }
        if (statusOf(watchError) === 404) {
          // Definitive: no durable watch or head for this session.
          // A missing *legacy watch* says nothing about the independently
          // stored latest run.  Pass `undefined` so an in-flight initial run
          // load cannot be overwritten through a stale ref.  The canonical
          // v2 route is authoritative for both head and run, so its 404 does
          // intentionally clear the displayed run — and with it any refused
          // publication: there is nothing left to be out of date about.
          if (supportsCanonicalSnapshots) setDefinitionsOutOfDate(null);
          applyCanonical(null, null, supportsCanonicalSnapshots ? null : undefined);
          coordinator.schedule(CANONICAL_POLL_IDLE_MS);
          return;
        }
        // Transport failure: keep the last complete snapshot and retry sooner.
        coordinator.schedule(CANONICAL_POLL_RETRY_MS);
        return;
      }
      if (!ticket.isCurrent()) return;
      if (head !== null) {
        if (head.watch.session_id !== sessionId) {
          // Never admit another session's head; keep the current view and retry.
          setLoading(false);
          coordinator.schedule(CANONICAL_POLL_RETRY_MS);
          return;
        }
        if (isStaleWatchHead(
          canonicalHeadRef.current === null ? null : canonicalHeadIdentity(canonicalHeadRef.current),
          canonicalHeadIdentity(head),
        )) {
          coordinator.schedule(canonicalHeadPollDelay(canonicalHeadRef.current!));
          return;
        }
        let latestRun = runRef.current;
        if (head.head_run_id === null) {
          latestRun = null;
        } else if (latestRun?.run_id !== head.head_run_id) {
          try {
            latestRun = await transport.getModelEnsembleSnapshot!(head.head_run_id, ticket.signal);
          } catch (snapshotError) {
            // The immutable snapshot is not readable (including 404): retain the
            // last complete run rather than presenting a head without it.
            if (!ticket.isCurrent()) return;
            setLoading(false);
            if (snapshotError instanceof MetricDefinitionsOutOfDateError) {
              // Client definitions are out of date for this exact head: clear
              // every retained value and guidance; keep polling at idle cadence.
              setDefinitionsOutOfDate(snapshotError.mismatch);
              applyCanonical(head, { watch: head.watch, latest_run: null }, null);
              coordinator.schedule(CANONICAL_POLL_IDLE_MS);
              return;
            }
            coordinator.schedule(CANONICAL_POLL_RETRY_MS);
            return;
          }
          if (!ticket.isCurrent()) return;
          if (latestRun.run_id !== head.head_run_id) {
            // Parser-valid snapshot for the wrong run: keep polling instead of stopping.
            setLoading(false);
            coordinator.schedule(CANONICAL_POLL_WRONG_RUN_MS);
            return;
          }
        }
        setDefinitionsOutOfDate(null);
        applyCanonical(head, { watch: head.watch, latest_run: latestRun }, latestRun);
        setLoading(false);
        coordinator.schedule(canonicalHeadPollDelay(head));
        return;
      }
      if (legacy !== null) {
        if (isStaleWatchHead(
          watchRef.current === null ? null : watchSnapshotIdentity(watchRef.current),
          watchSnapshotIdentity(legacy),
        )) {
          coordinator.schedule(watchSnapshotPollDelay(watchRef.current!));
          return;
        }
        if (legacy.watch.session_id === sessionId) setDefinitionsOutOfDate(null);
        applyCanonical(null, legacy, legacy.watch.session_id === sessionId ? legacy.latest_run : runRef.current);
        setLoading(false);
        coordinator.schedule(watchSnapshotPollDelay(legacy));
      }
    });
    coordinatorRef.current = coordinator;
    coordinator.pollNow();
    return () => {
      coordinator.stop();
      if (coordinatorRef.current === coordinator) coordinatorRef.current = null;
    };
  }, [sessionId, supportsCanonicalSnapshots, transport]);

  /**
   * A command result (start, enqueue, cancel, watch change) that the
   * compatibility gate refused. The refused publication is the newest truth
   * for this session, so the previously displayed run must not stay visible
   * beside a generic error: clear it and show the update-client state. A later
   * compatible poll or command clears the state again.
   */
  function refuseCommandDefinitions(mismatch: MetricDefinitionMismatch) {
    setDefinitionsOutOfDate(mismatch);
    runRef.current = null;
    setRun(null);
  }

  /**
   * Resolves the exact sealed run for a command's canonical head, refusing any
   * head or snapshot that does not belong to this session or head run id.
   */
  async function resolveCommandRun(
    head: ModelEnsembleCanonicalHead,
    signal?: AbortSignal,
  ): Promise<ModelEnsembleRun | null> {
    if (head.watch.session_id !== sessionId) throw new Error("durable_watch_identity_mismatch");
    if (head.head_run_id === null) return null;
    const current = runRef.current;
    if (current?.run_id === head.head_run_id) return current;
    if (transport.getModelEnsembleSnapshot === undefined) throw new Error("durable_snapshot_unavailable");
    const exactRun = await transport.getModelEnsembleSnapshot(head.head_run_id, signal);
    if (exactRun.run_id !== head.head_run_id) throw new Error("durable_snapshot_identity_mismatch");
    return exactRun;
  }

  async function start() {
    if (running || blocked !== null || durableAttemptRunning || watchQueued || legacyWatchBusy) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setRunning(true);
    setError("");
    const coordinator = coordinatorRef.current;
    coordinator?.beginCommand();
    let resumeDelay: number | undefined;
    try {
      if (transport.enqueueModelEnsembleAnalysis !== undefined) {
        let activeWatch = watchRef.current;
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
          watchRef.current = activeWatch;
          setWatch(activeWatch);
        }
        const head = await transport.enqueueModelEnsembleAnalysis(activeWatch.watch.watch_id, controller.signal);
        if (controller.signal.aborted) return;
        const exactRun = await resolveCommandRun(head, controller.signal);
        if (controller.signal.aborted) return;
        setDefinitionsOutOfDate(null);
        applyCanonical(head, { watch: head.watch, latest_run: exactRun }, exactRun);
        followingLive.current = true;
        resumeDelay = canonicalHeadPollDelay(head);
      } else {
        const outcome = await transport.startModelEnsemble(
          sessionId,
          { confirmation: "run_local_metric_cascade_on_selected_redacted_text" },
          nextIdempotencyKey("model-ensemble"),
          controller.signal,
        );
        if (!controller.signal.aborted) {
          setDefinitionsOutOfDate(null);
          runRef.current = outcome.run;
          setRun(outcome.run);
        }
      }
    } catch (runError) {
      if (controller.signal.aborted) return;
      if (runError instanceof MetricDefinitionsOutOfDateError) {
        refuseCommandDefinitions(runError.mismatch);
        return;
      }
      setError(runErrorCopy(runError));
    } finally {
      if (!controller.signal.aborted) setRunning(false);
      controllerRef.current = null;
      coordinator?.endCommand(resumeDelay);
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
    const coordinator = coordinatorRef.current;
    coordinator?.beginCommand();
    let resumeDelay: number | undefined;
    try {
      const head = await transport.cancelModelEnsembleAnalysis(canonicalHead.watch.watch_id);
      const exactRun = await resolveCommandRun(head);
      setDefinitionsOutOfDate(null);
      applyCanonical(head, { watch: head.watch, latest_run: exactRun }, exactRun);
      resumeDelay = canonicalHeadPollDelay(head);
    } catch (cancelError) {
      if (cancelError instanceof MetricDefinitionsOutOfDateError) {
        refuseCommandDefinitions(cancelError.mismatch);
      } else {
        setError("Cancellation could not be confirmed. The latest sealed snapshot remains visible.");
      }
    } finally {
      setRunning(false);
      coordinator?.endCommand(resumeDelay);
    }
  }

  async function toggleWatch() {
    if (watchChanging) return;
    setWatchChanging(true);
    setError("");
    const coordinator = coordinatorRef.current;
    coordinator?.beginCommand();
    let resumeDelay: number | undefined;
    try {
      const currentWatch = watchRef.current;
      const currentForSession = currentWatch?.watch.session_id === sessionId && currentWatch.watch.state !== "disabled";
      const snapshot = currentForSession
        ? await transport.disableModelEnsembleWatch?.(currentWatch.watch.watch_id)
        : await transport.enableModelEnsembleWatch?.(sessionId, {
            project_id: projectId,
            max_messages: MODEL_ENSEMBLE_DEFAULT_MAX_MESSAGES,
            confirmation: "continuously_analyze_selected_redacted_session",
          });
      if (snapshot !== undefined) {
        const disabled = snapshot.watch.state === "disabled";
        // A parsed run (or no watch at all) supersedes an earlier refusal.
        if (disabled || snapshot.latest_run !== null) setDefinitionsOutOfDate(null);
        applyCanonical(null, disabled ? null : snapshot, snapshot.latest_run);
        resumeDelay = disabled ? CANONICAL_POLL_IDLE_MS : watchSnapshotPollDelay(snapshot);
      } else {
        setError("Continuous local analysis is available only in the integrated desktop app.");
      }
    } catch (watchChangeError) {
      if (watchChangeError instanceof MetricDefinitionsOutOfDateError) {
        refuseCommandDefinitions(watchChangeError.mismatch);
      } else {
        setError("The continuous local watch could not be changed. No session text was retained.");
      }
    } finally {
      setWatchChanging(false);
      coordinator?.endCommand(resumeDelay);
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
  const {
    selectedPoint,
    historicalRun,
    historicalRunRefused,
    selectedRadarRun,
    comparisonRadarRun,
  } = useTrajectorySelection({ transport, points: trajectoryPoints, selectedRunId, headRun: run });

  function selectTrajectoryRun(runId: string) {
    followingLive.current = runId === trajectoryHeadRunId;
    setSelectedRunId(runId);
  }

  return (
    <section aria-labelledby="model-ensemble-title" className="model-ensemble">
      <header className="model-ensemble__header">
        <div>
          <p className="eyebrow">Typed evidence + experimental model ranges</p>
          <h2 id="model-ensemble-title">Measure the analyzed window, then estimate every eligible axis locally</h2>
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
          : definitionsOutOfDate !== null
            ? METRIC_DEFINITIONS_OUT_OF_DATE_TITLE
          : blocked ?? (run
            ? `Stored local analysis completed ${formatTimestamp(run.completed_at)}.`
            : "No measured + predictive analysis is stored for this session yet.")}
      </p>
      {error && <p className="model-ensemble__error" role="alert">{error}</p>}
      {loading ? (
        <p className="model-ensemble__empty">Loading stored content-free receipts…</p>
      ) : definitionsOutOfDate !== null ? (
        <MetricDefinitionsOutOfDateAlert mismatch={definitionsOutOfDate} />
      ) : selectedRadarRun ? (
        <>
          {selectedPoint === null && run?.source_coverage_state === "incomplete_source" && (
            <p className="model-ensemble__error" role="note">
              The adapter could not prove the selected source window complete.
              This shadow shape reflects retained content only and is not a
              complete-session judgment.
            </p>
          )}
          {trajectoryDefinitionsMismatch !== null && (
            <p className="model-ensemble__error" data-history-definitions="out_of_date" role="note">
              Snapshot history was published under other metric definitions and is withheld
              until this client is updated; no earlier point is shown or compared. The current
              sealed receipt passed the compatibility gate and remains visible.
            </p>
          )}
          {historicalRunRefused !== null && (
            <p className="model-ensemble__error" data-history-definitions="snapshot_out_of_date" role="note">
              The exact sealed snapshot for this earlier point was published under other metric
              definitions, so only its compact state facts are shown and no guidance receipt is
              read from it; update this client to open that snapshot.
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
            evidenceEnabled={selectedPoint === null || selectedPoint.run_id === run?.run_id}
            evidenceSessionId={sessionId}
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
