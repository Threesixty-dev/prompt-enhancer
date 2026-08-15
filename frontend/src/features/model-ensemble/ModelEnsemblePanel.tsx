import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ModelEnsembleRun,
  PromptEnhancerTransport,
  ProviderCompatibilityStatus,
  SessionTextAnalysisCapability,
} from "../../shared/api/contracts";
import { nextIdempotencyKey } from "../../shared/api/idempotency";
import type { MetricCategory } from "../../shared/platform/platform";
import { QUALITY_ANALYSIS_DEFINITIONS } from "../quality-profile/qualityProfile";
import { promptTextCompatibilityBlocker } from "../provider-compatibility";

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
    return "The ten-model ensemble is available only in the integrated local app.";
  }
  return "The local ten-model run did not complete. The error contains no session text.";
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

function ShadowRadar({ run, category }: { run: ModelEnsembleRun; category: MetricCategory }) {
  const kind = category === "prompt-quality" ? "prompt" : "logic";
  const metrics = new Map(run.metrics.map((metric) => [metric.metric_key, metric]));
  const known = QUALITY_ANALYSIS_DEFINITIONS
    .filter((definition) => definition.kind === kind)
    .flatMap((definition) => {
      const metric = metrics.get(definition.key);
      if (metric?.value_state !== "known" || metric.numeric_value == null) return [];
      const plotted = definition.direction === "lower_is_better"
        ? 1 - metric.numeric_value
        : metric.numeric_value;
      return [{ definition, metric, plotted }];
    });
  if (known.length < 3) {
    return (
      <div className="model-ensemble__radar-empty" role="note">
        A radar needs at least three known chunk averages. Unknown, unsupported,
        failed, and abstained metrics are omitted—not plotted as zero.
      </div>
    );
  }
  const size = 360;
  const center = size / 2;
  const radius = 112;
  const point = (index: number, magnitude: number) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / known.length;
    return [
      center + Math.cos(angle) * radius * magnitude,
      center + Math.sin(angle) * radius * magnitude,
    ] as const;
  };
  const polygon = known.map((item, index) => point(index, item.plotted).join(",")).join(" ");
  return (
    <figure className="model-ensemble__radar">
      <svg aria-label="Direction-adjusted shadow model radar" role="img" viewBox={`0 0 ${size} ${size}`}>
        {[0.25, 0.5, 0.75, 1].map((level) => (
          <polygon
            className="model-ensemble__radar-ring"
            key={level}
            points={known.map((_, index) => point(index, level).join(",")).join(" ")}
          />
        ))}
        {known.map((item, index) => {
          const axis = point(index, 1);
          const label = point(index, 1.28);
          return (
            <g key={item.definition.key}>
              <line className="model-ensemble__radar-axis" x1={center} x2={axis[0]} y1={center} y2={axis[1]} />
              <text className="model-ensemble__radar-label" textAnchor="middle" x={label[0]} y={label[1]}>
                {item.definition.shortLabel}
              </text>
            </g>
          );
        })}
        <polygon className="model-ensemble__radar-value" points={polygon} />
      </svg>
      <figcaption>
        Known chunks only. Lower-is-better risk axes are inverted for this shape;
        the table keeps the raw model-supported fraction. Unknown, unsupported,
        failed, and abstained metrics are omitted—not converted to zero.
      </figcaption>
    </figure>
  );
}

export function ModelEnsemblePanel({
  sessionId,
  category,
  transport,
  analysisCapability,
  providerCompatibility,
  compatibilityLoading = false,
}: {
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
  const controllerRef = useRef<AbortController | null>(null);
  const blocked = blocker(analysisCapability, providerCompatibility, compatibilityLoading);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setRun(null);
    transport.getLatestModelEnsemble(sessionId, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setRun(value); })
      .catch((loadError: unknown) => {
        if (!controller.signal.aborted && statusOf(loadError) !== 404) {
          setError("The stored shadow ensemble could not be validated or loaded.");
        }
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [sessionId, transport]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  async function start() {
    if (running || blocked !== null) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setRunning(true);
    setError("");
    try {
      const outcome = await transport.startModelEnsemble(
        sessionId,
        { confirmation: "run_ten_local_models_on_selected_redacted_text" },
        nextIdempotencyKey("model-ensemble"),
        controller.signal,
      );
      if (!controller.signal.aborted) setRun(outcome.run);
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

  const selectedDefinitions = useMemo(() => {
    const kind = category === "prompt-quality" ? "prompt" : "logic";
    const definitions = new Map(
      QUALITY_ANALYSIS_DEFINITIONS.filter((item) => item.kind === kind)
        .map((item) => [item.key, item]),
    );
    return run?.metrics
      .filter((metric) => definitions.has(metric.metric_key))
      .map((metric) => ({ metric, definition: definitions.get(metric.metric_key)! })) ?? [];
  }, [category, run]);
  const completedExperts = run?.experts.filter((expert) => expert.status === "completed").length ?? 0;

  return (
    <section aria-labelledby="model-ensemble-title" className="model-ensemble">
      <header className="model-ensemble__header">
        <div>
          <p className="eyebrow">Ten-model local shadow ensemble</p>
          <h2 id="model-ensemble-title">Chunk the bounded session, then ask ten pinned experts in series</h2>
          <p>
            Four retrieval models find evidence, two rerank it, three NLI models
            check scope, and one structured rubric model decides. Each model runs
            in its own process; process exit releases its RAM and GPU allocation.
          </p>
        </div>
        {running ? (
          <button className="button button--secondary" onClick={cancelWait} type="button">Cancel browser wait</button>
        ) : (
          <button className="button button--primary" disabled={blocked !== null} onClick={() => void start()} type="button">
            Run 10 models locally
          </button>
        )}
      </header>
      <div className="model-ensemble__boundary" role="note">
        <strong>Shadow result—not a product score</strong>
        <span>
          Models see only the selected redacted window, split into at most eight
          exhaustive chunks. Text is never stored. Per-chunk votes and averages are
          uncalibrated and cannot replace objective verification or the deterministic metric pack.
        </span>
      </div>
      <p aria-live="polite" className="model-ensemble__status" role="status">
        {running
          ? "Running ten local child processes one at a time. This may take several minutes; cancelling only stops this browser from waiting."
          : blocked ?? (run
            ? `Stored shadow run completed ${formatTimestamp(run.completed_at)}.`
            : "No ten-model shadow run is stored for this session yet.")}
      </p>
      {error && <p className="model-ensemble__error" role="alert">{error}</p>}
      {loading ? (
        <p className="model-ensemble__empty">Loading stored content-free receipts…</p>
      ) : run ? (
        <>
          <dl aria-label="Shadow ensemble facts" className="model-ensemble__facts">
            <div><dt>Chunks</dt><dd>{run.chunk_count}</dd></div>
            <div><dt>Models completed</dt><dd>{completedExperts} / 10</dd></div>
            <div><dt>Metric definitions</dt><dd>{run.metrics.length}</dd></div>
            <div>
              <dt>Source coverage</dt>
              <dd>{run.source_coverage_state === "complete_window" ? "Complete selected window" : "Incomplete source window"}</dd>
            </div>
            <div><dt>Persisted text</dt><dd>None</dd></div>
          </dl>
          {run.source_coverage_state === "incomplete_source" && (
            <p className="model-ensemble__error" role="note">
              The adapter could not prove the selected source window complete.
              This shadow shape reflects retained content only and is not a
              complete-session judgment.
            </p>
          )}
          <div className="model-ensemble__results">
            <ShadowRadar category={category} run={run} />
            <div className="model-ensemble__metric-list">
              {selectedDefinitions.map(({ metric, definition }) => (
                <article key={metric.metric_key}>
                  <div><strong>{definition.label}</strong><small>{metric.value_state.replaceAll("_", " ")}</small></div>
                  <b>{metric.numeric_value == null ? "—" : `${Math.round(metric.numeric_value * 100)}%`}</b>
                  <p>
                    Known {metric.known_chunk_count}/{metric.total_chunk_count} ·
                    {" "}abstained {metric.abstained_chunk_count} · unsupported {metric.unsupported_chunk_count} · failed {metric.failed_chunk_count}
                  </p>
                </article>
              ))}
            </div>
          </div>
          <details className="model-ensemble__models">
            <summary>Ten pinned model receipts and resource release</summary>
            <ol>
              {run.experts.map((expert) => (
                <li key={expert.model_key}>
                  <span><strong>{expert.ordinal + 1}. {expert.repository_id}</strong><small>{expert.role.replaceAll("_", " ")} · {expert.license_spdx}</small></span>
                  <span>{expert.status} · {expert.device?.toUpperCase() ?? "no device"} · unloaded {expert.unloaded_after_stage ? "yes" : "no"}</span>
                </li>
              ))}
            </ol>
          </details>
        </>
      ) : (
        <p className="model-ensemble__empty">
          Start one explicit run to create content-free chunk, expert, vote, and aggregate receipts.
        </p>
      )}
    </section>
  );
}
