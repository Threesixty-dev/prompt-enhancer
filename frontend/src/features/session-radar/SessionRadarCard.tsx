import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { ModelEnsembleRun, PromptEnhancerTransport } from "../../shared/api/contracts";
import { parseModelEnsembleRun } from "../../shared/api/modelEnsembleContract";
import { MetricDefinitionsOutOfDateError } from "../../shared/api/metricPublicationV2Contract";
import { PromptMetricRadar } from "../prompt-check/promptCheckPlots";
import {
  MODEL_ENSEMBLE_LENSES,
  modelEnsembleAxisCoverage,
  modelEnsembleAxisPlottedLabel,
  modelEnsembleAxisRawRateLabel,
  modelEnsembleMetricStateLabel,
  modelEnsembleRadarAxes,
  type ModelEnsembleLensId,
} from "../model-ensemble/metricAxisModel";
import "./SessionRadarCard.css";

const READ_DEADLINE_MS = 15_000;
const SAFE_PROVENANCE = /^[A-Za-z0-9][A-Za-z0-9._+:/-]{0,127}$/;

type RadarTransport = Pick<PromptEnhancerTransport, "getSessionMetrics"> &
  Partial<Pick<PromptEnhancerTransport, "getLatestModelEnsemble">>;
type Owner = { sessionId: string; transport: RadarTransport };
type StoredProvenance = {
  source: string;
  metricPackKey: string;
  metricPackVersion: number;
  metricEngineVersion: string;
  redactorVersion: string | null;
  computedAt: string;
};
type ReadResult =
  | { kind: "loading" }
  | { kind: "ensemble"; run: ModelEnsembleRun }
  | { kind: "empty" }
  | { kind: "data-gap"; provenance: StoredProvenance }
  | { kind: "cancelled" }
  | { kind: "definitions-out-of-date" }
  | { kind: "error"; reason: "timeout" | "unavailable" };
type ReadState = { owner: Owner | null; result: ReadResult };
type ReadAttempt = { cancel: () => void };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSafeText(value: unknown): value is string {
  return typeof value === "string" && SAFE_PROVENANCE.test(value);
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 1;
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isRatio(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

function isNullableSafeText(value: unknown): value is string | null {
  return value === null || isSafeText(value);
}

function isUtcTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function statusOf(error: unknown): number | null {
  return isRecord(error) && typeof error.status === "number" && Number.isInteger(error.status)
    ? error.status
    : null;
}

function canUseStoredFallback(error: unknown): boolean {
  return statusOf(error) === 404;
}

/**
 * Stored session metrics are normally the metadata-only ingestion pack. They
 * are never turned into a coaching radar; this validation only lets the UI
 * truthfully describe that incompatible stored snapshot as a data gap.
 */
function parseStoredMetricProvenance(value: unknown, sessionId: string): StoredProvenance | null {
  if (!isRecord(value) || value.session_id !== sessionId || !Array.isArray(value.metrics)) {
    throw new Error("invalid stored metric envelope");
  }
  if (value.metrics.length === 0) return null;

  let provenance: StoredProvenance | null = null;
  const identities = new Set<string>();
  for (const candidate of value.metrics) {
    if (!isRecord(candidate)) throw new Error("invalid stored metric row");
    const numericValue = candidate.numeric_value;
    const textValue = candidate.text_value;
    const unit = candidate.unit;
    const confidence = candidate.confidence;
    const observed = candidate.observed_count;
    const eligible = candidate.eligible_count;
    const coverage = candidate.coverage;
    if (
      !isSafeText(candidate.key)
      || !isPositiveInteger(candidate.version)
      || !isSafeText(candidate.dimension)
      || typeof candidate.display_name !== "string"
      || !(numericValue === null || (typeof numericValue === "number" && Number.isFinite(numericValue)))
      || !(textValue === null || typeof textValue === "string")
      || !(unit === null || isSafeText(unit))
      || !isSafeText(candidate.source)
      || !isNonNegativeInteger(observed)
      || !isNonNegativeInteger(eligible)
      || observed > eligible
      || !isRatio(coverage)
      || !(confidence === null || isRatio(confidence))
      || !isSafeText(candidate.metric_pack_key)
      || !isPositiveInteger(candidate.metric_pack_version)
      || !isSafeText(candidate.metric_engine_version)
      || !isNullableSafeText(candidate.redactor_version)
      || !isUtcTimestamp(candidate.computed_at)
    ) {
      throw new Error("invalid stored metric row");
    }
    if (unit === "ratio" && numericValue !== null && !isRatio(numericValue)) {
      throw new Error("invalid stored metric ratio");
    }
    const expectedCoverage = eligible === 0 ? 0 : observed / eligible;
    if (Math.abs(coverage - expectedCoverage) > 1e-12) {
      throw new Error("incoherent stored metric coverage");
    }
    const identity = `${candidate.key}@${candidate.version}`;
    if (identities.has(identity)) throw new Error("duplicate stored metric row");
    identities.add(identity);
    const rowProvenance: StoredProvenance = {
      source: candidate.source,
      metricPackKey: candidate.metric_pack_key,
      metricPackVersion: candidate.metric_pack_version,
      metricEngineVersion: candidate.metric_engine_version,
      redactorVersion: candidate.redactor_version,
      computedAt: candidate.computed_at,
    };
    if (
      provenance !== null
      && (
        provenance.source !== rowProvenance.source
        || provenance.metricPackKey !== rowProvenance.metricPackKey
        || provenance.metricPackVersion !== rowProvenance.metricPackVersion
        || provenance.metricEngineVersion !== rowProvenance.metricEngineVersion
        || provenance.redactorVersion !== rowProvenance.redactorVersion
        || provenance.computedAt !== rowProvenance.computedAt
      )
    ) {
      throw new Error("mixed stored metric provenance");
    }
    provenance = rowProvenance;
  }
  return provenance;
}

function sourceLabel(run: ModelEnsembleRun): string {
  if (run.metric_publication_v2 !== null) return "Canonical V2 measured states";
  if (run.typed_metrics.length > 0) return "Typed local measurement · legacy projection";
  return "Legacy committee shadow";
}

function projectionLabel(run: ModelEnsembleRun): string {
  return run.metric_publication_v2?.projection_version
    ?? run.metric_projection_version
    ?? "committee receipt only";
}

function axisVersionLabel(metric: ReturnType<typeof modelEnsembleRadarAxes>[number]["metric"]): string {
  if (metric === null) return "not observed";
  return "metric_version" in metric ? `v${metric.metric_version}` : "legacy committee receipt";
}

export function SessionRadarCard({
  sessionId,
  transport,
}: {
  sessionId: string;
  transport: RadarTransport;
}) {
  const owner = useMemo<Owner>(() => ({ sessionId, transport }), [sessionId, transport]);
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const attemptRef = useRef<ReadAttempt | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [selectedLensId, setSelectedLensId] = useState<ModelEnsembleLensId>("task-framing");
  const [readState, setReadState] = useState<ReadState>({ owner: null, result: { kind: "loading" } });

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;
    let settled = false;
    const isCurrent = () => !settled && ownerRef.current === owner && attemptRef.current === attempt;
    const clearDeadline = () => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };
    const settle = (next: ReadResult) => {
      if (!isCurrent()) return;
      settled = true;
      clearDeadline();
      if (attemptRef.current === attempt) attemptRef.current = null;
      setReadState({ owner, result: next });
    };
    const abortSilently = () => {
      if (settled) return;
      settled = true;
      clearDeadline();
      controller.abort();
      if (attemptRef.current === attempt) attemptRef.current = null;
    };
    const cancel = () => {
      if (!isCurrent()) return;
      controller.abort();
      settle({ kind: "cancelled" });
    };
    const attempt: ReadAttempt = { cancel };

    attemptRef.current?.cancel();
    attemptRef.current = attempt;
    setReadState({ owner, result: { kind: "loading" } });
    timer = setTimeout(() => {
      if (!isCurrent()) return;
      controller.abort();
      settle({ kind: "error", reason: "timeout" });
    }, READ_DEADLINE_MS);

    const readStoredFallback = async () => {
      if (!isCurrent()) return;
      try {
        const response = await transport.getSessionMetrics(sessionId, controller.signal);
        if (!isCurrent()) return;
        const provenance = parseStoredMetricProvenance(response, sessionId);
        settle(provenance === null ? { kind: "empty" } : { kind: "data-gap", provenance });
      } catch {
        if (isCurrent()) settle({ kind: "error", reason: "unavailable" });
      }
    };

    Promise.resolve().then(async () => {
      if (!isCurrent()) return;
      if (transport.getLatestModelEnsemble === undefined) {
        await readStoredFallback();
        return;
      }
      try {
        const response = await transport.getLatestModelEnsemble(sessionId, controller.signal);
        if (!isCurrent()) return;
        // HTTP already parses this; repeat the boundary check for injected transports.
        const run = parseModelEnsembleRun(response);
        settle({ kind: "ensemble", run });
      } catch (error) {
        if (!isCurrent()) return;
        if (error instanceof MetricDefinitionsOutOfDateError) {
          settle({ kind: "definitions-out-of-date" });
          return;
        }
        if (canUseStoredFallback(error)) {
          await readStoredFallback();
          return;
        }
        settle({ kind: "error", reason: "unavailable" });
      }
    });

    return abortSilently;
  }, [owner, refresh, sessionId, transport]);

  const visibleState: ReadResult = readState.owner === owner ? readState.result : { kind: "loading" };
  const retry = () => {
    if (ownerRef.current === owner && readState.owner === owner && attemptRef.current === null) {
      setRefresh((value) => value + 1);
    }
  };
  const cancel = () => {
    if (ownerRef.current === owner && readState.owner === owner && readState.result.kind === "loading") {
      attemptRef.current?.cancel();
    }
  };

  if (visibleState.kind === "loading") {
    return (
      <ReadShell>
        <div className="session-radar__state" role="status">
          <span aria-hidden="true" className="spinner" />
          <span>Loading the latest local metric snapshot…</span>
          <button className="button button--secondary button--compact" onClick={cancel} type="button">Cancel session radar loading</button>
        </div>
      </ReadShell>
    );
  }
  if (visibleState.kind === "error") {
    return (
      <ReadShell>
        <div className="session-radar__state" role="alert">
          <p>{visibleState.reason === "timeout" ? "Session radar request timed out after 15 seconds." : "Session radar could not be loaded."}</p>
          <button className="button button--secondary button--compact" onClick={retry} type="button">Retry session radar</button>
        </div>
      </ReadShell>
    );
  }
  if (visibleState.kind === "cancelled") {
    return (
      <ReadShell>
        <div className="session-radar__state" role="status">
          <p>Session radar loading was cancelled.</p>
          <button className="button button--secondary button--compact" onClick={retry} type="button">Retry session radar</button>
        </div>
      </ReadShell>
    );
  }
  if (visibleState.kind === "definitions-out-of-date") {
    return (
      <ReadShell>
        <div className="session-radar__state" role="alert">
          <p>This snapshot uses metric definitions this app cannot read. Update the app, then refresh the session radar.</p>
          <button className="button button--secondary button--compact" onClick={retry} type="button">Refresh session radar</button>
        </div>
      </ReadShell>
    );
  }
  if (visibleState.kind === "empty") {
    return (
      <ReadShell>
        <p className="session-radar__empty">No local metric snapshot exists for this session yet.</p>
        <p className="session-radar__empty">Open the local model analysis from the prompt-quality view to create a separate canonical snapshot.</p>
        <button className="button button--secondary button--compact" onClick={retry} type="button">Refresh session radar</button>
      </ReadShell>
    );
  }
  if (visibleState.kind === "data-gap") {
    const { provenance } = visibleState;
    return (
      <ReadShell>
        <p className="session-radar__empty">Stored session metrics are not a coaching radar snapshot.</p>
        <p className="session-radar__provenance">
          Stored source {provenance.source} · pack {provenance.metricPackKey}@{provenance.metricPackVersion}
          · engine {provenance.metricEngineVersion} · computed {provenance.computedAt}
          {provenance.redactorVersion === null ? " · redactor not recorded" : ` · redactor ${provenance.redactorVersion}`}
        </p>
        <p className="session-radar__empty">Open the local model analysis from the prompt-quality view to create a separate canonical snapshot.</p>
        <button className="button button--secondary button--compact" onClick={retry} type="button">Refresh session radar</button>
      </ReadShell>
    );
  }
  return <EnsembleRadar run={visibleState.run} selectedLensId={selectedLensId} onSelectedLensIdChange={setSelectedLensId} onRefresh={retry} />;
}

function ReadShell({ children }: { children: ReactNode }) {
  return (
    <section aria-labelledby="session-radar-title" className="session-radar">
      <h3 id="session-radar-title">Session radar</h3>
      {children}
    </section>
  );
}

function EnsembleRadar({ run, selectedLensId, onSelectedLensIdChange, onRefresh }: {
  run: ModelEnsembleRun;
  selectedLensId: ModelEnsembleLensId;
  onSelectedLensIdChange: (lensId: ModelEnsembleLensId) => void;
  onRefresh: () => void;
}) {
  const lens = MODEL_ENSEMBLE_LENSES.find((candidate) => candidate.id === selectedLensId)!;
  const axes = useMemo(() => modelEnsembleRadarAxes(run, lens.id), [lens.id, run]);
  const readings = axes.map((axis) => ({
    key: axis.key,
    label: axis.shortLabel,
    value: axis.metric?.value_state === "known" && isRatio(axis.metric.numeric_value) ? axis.metric.numeric_value : null,
    higherIsBetter: axis.direction === "higher_is_better",
    stateLabel: axis.metric === null ? "Not observed" : modelEnsembleMetricStateLabel(axis.metric),
  }));
  const known = readings.filter((reading) => reading.value !== null).length;

  return (
    <section aria-labelledby="session-radar-title" className="session-radar">
      <header>
        <div>
          <p className="eyebrow">{sourceLabel(run)} · completed {run.completed_at}</p>
          <h3 id="session-radar-title">Session radar</h3>
        </div>
        <span className="session-radar__count">{known} of {axes.length} numeric in this group</span>
      </header>
      <div aria-label="Session radar groups" className="session-radar__groups" role="group">
        {MODEL_ENSEMBLE_LENSES.map((candidate) => (
          <button
            aria-pressed={candidate.id === lens.id}
            className="button button--secondary button--compact"
            key={candidate.id}
            onClick={() => onSelectedLensIdChange(candidate.id)}
            type="button"
          >
            {candidate.label}
          </button>
        ))}
      </div>
      <p className="session-radar__question">{lens.question}</p>
      <PromptMetricRadar chartLabel={`${lens.label} session radar`} readings={readings} />
      <ul aria-label={`${lens.label} metric states`} className="session-radar__states">
        {axes.map((axis) => {
          const rawRate = modelEnsembleAxisRawRateLabel(axis);
          const coverage = axis.metric === null ? null : modelEnsembleAxisCoverage(axis);
          return (
            <li key={axis.key}>
              <strong>{axis.shortLabel}</strong>
              <span>{modelEnsembleAxisPlottedLabel(axis)}</span>
              {rawRate !== null && <small>{rawRate}</small>}
              {coverage !== null && <small>{axisVersionLabel(axis.metric)} · {modelEnsembleMetricStateLabel(axis.metric)} · coverage {Math.round(coverage * 100)}%</small>}
            </li>
          );
        })}
      </ul>
      <p className="session-radar__boundary">{lens.boundary}</p>
      <details className="session-radar__details">
        <summary>Snapshot provenance</summary>
        <p>Endpoint-scoped session receipt · run {run.run_id} · projection {projectionLabel(run)} · calibration not assessed.</p>
      </details>
      <button className="button button--secondary button--compact" onClick={onRefresh} type="button">Refresh session radar</button>
    </section>
  );
}
