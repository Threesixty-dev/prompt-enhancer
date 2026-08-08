import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  CodexIngestionReport,
  CodexLabelEnrichmentReport,
  CodexLocalSourceStatus,
  CodexSession,
  DisplayLabelEntityKind,
  PromptEnhancerTransport,
  SessionMetric,
} from "../../shared/api/contracts";
import { Icon } from "../../shared/ui/Icon";

const INDEX_LIMITS = [100, 250, 500] as const;
const ANALYSIS_LIMITS = [5, 10, 25] as const;
const LABEL_LIMITS = [5, 10, 25] as const;

function shortId(value: string): string {
  return value.length > 18
    ? `${value.slice(0, 10)}...${value.slice(-6)}`
    : value;
}

function displayName(value: string | null | undefined, fallback: string): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : fallback;
}

function safeDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Unknown time" : date.toLocaleString();
}

function reportSummary(report: CodexIngestionReport, action: "indexed" | "analyzed"): string {
  const count = action === "indexed" ? report.sessions_selected : report.metrics_written;
  const noun = action === "indexed" ? "sessions indexed" : "metrics written";
  return `${count} ${noun}${report.truncated ? " (bounded limit reached)" : ""}.`;
}
function labelReportSummary(report: CodexLabelEnrichmentReport): string {
  const filled =
    report.project_labels_filled + report.session_labels_filled;
  const readNoun = report.summary_reads === 1 ? "read" : "reads";
  if (report.requested_sessions === 0) {
    return "Selected items already have display labels.";
  }
  if (filled === 0) {
    return (
      "No additional labels were available from " +
      report.summary_reads +
      " summary " +
      readNoun +
      "."
    );
  }
  const labelNoun = filled === 1 ? "label" : "labels";
  return (
    filled +
    " missing " +
    labelNoun +
    " imported from " +
    report.summary_reads +
    " summary " +
    readNoun +
    (report.truncated ? " (bounded limit reached)" : "") +
    "."
  );
}

type DisplayLabelOrigin = "provider" | "manual" | "unknown";

function labelOriginText(origin: DisplayLabelOrigin): string {
  if (origin === "manual") return "Manual label";
  if (origin === "provider") return "Codex label";
  return "Missing label";
}

interface LabelEditorState {
  entityKind: DisplayLabelEntityKind;
  entityId: string;
  currentValue: string;
  origin: DisplayLabelOrigin;
  revision: number;
}

function metricValue(metric: SessionMetric): string {
  if (metric.numeric_value !== null) {
    const value = Number.isInteger(metric.numeric_value)
      ? metric.numeric_value.toString()
      : metric.numeric_value.toFixed(2);
    return metric.unit ? `${value} ${metric.unit}` : value;
  }
  return metric.text_value ?? "Unknown";
}

export function LocalSources({
  transport,
}: {
  transport: PromptEnhancerTransport;
}) {
  const [status, setStatus] = useState<CodexLocalSourceStatus | null>(null);
  const [sessions, setSessions] = useState<CodexSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [operation, setOperation] = useState<
    "grant" | "revoke" | "index" | "analyze" | "labels" | "manual-label" | null
  >(null);
  const [indexMaxSessions, setIndexMaxSessions] = useState<number>(100);
  const [analysisMaxSessions, setAnalysisMaxSessions] = useState<number>(10);
  const [labelMaxSessions, setLabelMaxSessions] = useState<number>(10);
  const [labelEditor, setLabelEditor] = useState<LabelEditorState | null>(null);
  const [labelDraft, setLabelDraft] = useState("");
  const [selectedProjects, setSelectedProjects] = useState<Set<string>>(
    () => new Set(),
  );
  const [selectedSessions, setSelectedSessions] = useState<Set<string>>(
    () => new Set(),
  );
  const [focusedSession, setFocusedSession] = useState<string | null>(null);
  const [metricsBySession, setMetricsBySession] = useState<
    Record<string, SessionMetric[]>
  >({});
  const [metricsLoading, setMetricsLoading] = useState<string | null>(null);
  const [metricsError, setMetricsError] = useState("");

  const refreshOverview = useCallback(
    async (signal?: AbortSignal) => {
      const [nextStatus, response] = await Promise.all([
        transport.getCodexLocalSourceStatus(signal),
        transport.listCodexSessions(100, 0, signal),
      ]);
      setStatus(nextStatus);
      setSessions(response.sessions);
    },
    [transport],
  );

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    refreshOverview(controller.signal)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError("The local Codex source could not be loaded.");
          console.error("Local source overview failed", reason);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [refreshOverview]);

  const groupedSessions = useMemo(() => {
    const groups = new Map<string, CodexSession[]>();
    for (const session of sessions) {
      const group = groups.get(session.project_id) ?? [];
      group.push(session);
      groups.set(session.project_id, group);
    }
    return [...groups.entries()];
  }, [sessions]);

  const selectedSessionIds = useMemo(() => {
    const ids = new Set(selectedSessions);
    for (const session of sessions) {
      if (selectedProjects.has(session.project_id)) ids.add(session.session_id);
    }
    return [...ids];
  }, [selectedProjects, selectedSessions, sessions]);

  const focusedMetrics = focusedSession
    ? metricsBySession[focusedSession]
    : undefined;
  const focusedSessionRecord = focusedSession
    ? sessions.find((session) => session.session_id === focusedSession)
    : undefined;


  async function runStatusAction(action: "grant" | "revoke") {
    setOperation(action);
    setError("");
    setNotice("");
    try {
      const nextStatus =
        action === "grant"
          ? await transport.grantCodexLocalHistoryConsent()
          : await transport.revokeCodexLocalHistoryConsent();
      setStatus(nextStatus);
      if (action === "revoke") {
        setSelectedProjects(new Set());
        setSelectedSessions(new Set());
      }
      setNotice(
        action === "grant"
          ? "Local-history access granted for this source."
          : "Local-history access revoked. Indexed metadata remains local.",
      );
    } catch {
      setError(
        action === "grant"
          ? "Consent could not be granted."
          : "Consent could not be revoked.",
      );
    } finally {
      setOperation(null);
    }
  }

  async function indexSessions() {
    setOperation("index");
    setError("");
    setNotice("");
    try {
      const report = await transport.indexCodexLocalSessions(indexMaxSessions);
      await refreshOverview();
      setNotice(reportSummary(report, "indexed"));
    } catch {
      setError("The bounded Codex index could not be refreshed.");
    } finally {
      setOperation(null);
    }
  }

  const loadMetrics = useCallback(
    async (sessionId: string) => {
      setFocusedSession(sessionId);
      setMetricsLoading(sessionId);
      setMetricsError("");
      try {
        const response = await transport.getSessionMetrics(sessionId);
        setMetricsBySession((current) => ({
          ...current,
          [sessionId]: response.metrics,
        }));
      } catch {
        setMetricsError("Deterministic metrics could not be loaded.");
      } finally {
        setMetricsLoading(null);
      }
    },
    [transport],
  );

  async function analyzeSelection() {
    if (selectedProjects.size === 0 && selectedSessions.size === 0) {
      setError("Select at least one project or session.");
      return;
    }
    setOperation("analyze");
    setError("");
    setNotice("");
    try {
      const report = await transport.analyzeCodexLocalSessions({
        project_ids: [...selectedProjects],
        session_ids: [...selectedSessions],
        max_sessions: analysisMaxSessions,
      });
      setNotice(reportSummary(report, "analyzed"));
      const firstVisibleTarget = selectedSessionIds[0];
      if (firstVisibleTarget !== undefined) {
        // Analysis can cover hundreds of sessions. Refresh one visible result
        // eagerly and leave the rest behind each session's explicit Metrics
        // action so the browser never creates an unbounded request burst.
        const response = await transport.getSessionMetrics(firstVisibleTarget);
        setMetricsBySession((current) => ({
          ...current,
          [response.session_id]: response.metrics,
        }));
        setFocusedSession(firstVisibleTarget);
      }
      await refreshOverview();
    } catch {
      setError("The bounded deterministic analysis could not be completed.");
    } finally {
      setOperation(null);
    }
  }
  async function enrichLabels() {
    if (selectedProjects.size === 0 && selectedSessions.size === 0) {
      setError("Select at least one project or session.");
      return;
    }
    setOperation("labels");
    setError("");
    setNotice("");
    try {
      const report = await transport.enrichCodexDisplayLabels({
        project_ids: [...selectedProjects],
        session_ids: [...selectedSessions],
        max_sessions: labelMaxSessions,
      });
      await refreshOverview();
      setNotice(labelReportSummary(report));
    } catch {
      setError("Missing Codex labels could not be read from bounded summaries.");
    } finally {
      setOperation(null);
    }
  }

  function beginLabelEdit(
    entityKind: DisplayLabelEntityKind,
    entityId: string,
    currentValue: string,
    origin: DisplayLabelOrigin,
    revision: number,
  ) {
    setError("");
    setLabelDraft(currentValue);
    setLabelEditor({
      entityKind,
      entityId,
      currentValue,
      origin,
      revision,
    });
  }

  async function saveManualLabel() {
    if (!labelEditor) return;
    const value = labelDraft.trim();
    const maxLength = labelEditor.entityKind === "project" ? 120 : 160;
    if (value.length === 0 || value.length > maxLength) {
      setError("Enter a short local label before saving.");
      return;
    }

    setOperation("manual-label");
    setError("");
    setNotice("");
    try {
      await transport.setManualDisplayLabel(
        labelEditor.entityKind,
        labelEditor.entityId,
        value,
        labelEditor.revision,
      );
      await refreshOverview();
      setLabelEditor(null);
      setLabelDraft("");
      setNotice(
        "Local " +
          labelEditor.entityKind +
          " label saved. The Codex task was not renamed.",
      );
    } catch {
      setError("The local label could not be saved. Reopen it and try again.");
    } finally {
      setOperation(null);
    }
  }

  async function clearManualLabel() {
    if (!labelEditor || labelEditor.origin !== "manual") return;

    setOperation("manual-label");
    setError("");
    setNotice("");
    try {
      await transport.clearManualDisplayLabel(
        labelEditor.entityKind,
        labelEditor.entityId,
        labelEditor.revision,
      );
      await refreshOverview();
      setLabelEditor(null);
      setLabelDraft("");
      setNotice(
        "Manual " +
          labelEditor.entityKind +
          " label cleared. Any available Codex label is visible again.",
      );
    } catch {
      setError("The local label could not be cleared. Reopen it and try again.");
    } finally {
      setOperation(null);
    }
  }

  function toggleProject(projectId: string, checked: boolean) {
    setSelectedProjects((current) => {
      const next = new Set(current);
      if (checked) next.add(projectId);
      else next.delete(projectId);
      return next;
    });
    if (checked) {
      const projectSessionIds = new Set(
        sessions
          .filter((session) => session.project_id === projectId)
          .map((session) => session.session_id),
      );
      setSelectedSessions(
        (current) => new Set([...current].filter((id) => !projectSessionIds.has(id))),
      );
    }
  }

  function toggleSession(sessionId: string, checked: boolean) {
    setSelectedSessions((current) => {
      const next = new Set(current);
      if (checked) next.add(sessionId);
      else next.delete(sessionId);
      return next;
    });
  }

  if (loading) {
    return (
      <section className="local-sources-page">
        <div className="async-state" role="status">
          <span className="spinner" />
          <span>Loading local-source metadata...</span>
        </div>
      </section>
    );
  }

  if (!status) {
    return (
      <section className="local-sources-page">
        <div className="async-state async-state--error" role="alert">
          <span className="async-state__icon"><Icon name="x" /></span>
          <div>
            <strong>Local source unavailable</strong>
            <p>{error || "The loopback service did not return source status."}</p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="local-sources-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Private local workflow</p>
          <h1>Local sources</h1>
          <p>Choose exactly which Codex projects or sessions receive deterministic analysis.</p>
        </div>
        <div className="page-header__meta">
          <span className="privacy-chip"><Icon name="lock" /> Loopback only</span>
        </div>
      </header>

      <div className="source-safety-note" role="note">
        <span className="source-safety-note__icon"><Icon name="lock" /></span>
        <div>
          <strong>Content-discarding index</strong>
          <p>
            The index keeps pseudonymous IDs and any available display labels.
            Optional bounded summary reads can fill only a project-folder basename
            and explicit task title. Full paths, previews, prompts, responses, and
            tool output are never stored; nothing is sent online.
          </p>
        </div>
      </div>

      <div aria-live="polite" className="notice-region">
        {notice && <div className="success-notice local-source-notice"><Icon name="check" /><span>{notice}</span></div>}
        {error && <p className="local-source-error" role="alert">{error}</p>}
      </div>

      <div className="source-overview">
        <article className="source-card">
          <div className="source-card__heading">
            <div className="source-card__identity">
              <span className="source-card__mark">CX</span>
              <div>
                <p className="eyebrow">Provider adapter</p>
                <h2>Codex local history</h2>
              </div>
            </div>
            <span className={`status-pill ${status.consent_active ? "status-pill--positive" : "status-pill--warning"}`}>
              {status.consent_active ? "Access granted" : "Consent required"}
            </span>
          </div>
          <p className="source-card__description">
            Read-only access is explicit and revocable. Private display labels and
            metrics stay in the local database; provider credentials, prompts,
            responses, and tool output are never persisted.
          </p>
          <dl className="source-card__facts">
            <div><dt>Indexed sessions</dt><dd>{status.indexed_sessions}</dd></div>
            <div><dt>Safe projects</dt><dd>{status.indexed_projects}</dd></div>
            <div><dt>Data path</dt><dd>Local only</dd></div>
          </dl>
          <div className="source-card__actions">
            {status.consent_active ? (
              <button
                className="button button--danger-ghost"
                disabled={operation !== null}
                onClick={() => void runStatusAction("revoke")}
                type="button"
              >
                {operation === "revoke" ? "Revoking..." : "Revoke access"}
              </button>
            ) : (
              <button
                className="button button--primary"
                disabled={operation !== null}
                onClick={() => void runStatusAction("grant")}
                type="button"
              >
                {operation === "grant" ? "Granting..." : "Grant local-history access"}
              </button>
            )}
          </div>
        </article>

        <aside className="bounded-controls" aria-label="Bounded source controls">
          <div>
            <p className="eyebrow">Safety boundary</p>
            <h2>Bound every read</h2>
            <p>Indexing and detailed analysis have separate limits. Every provider read needs active consent.</p>
          </div>
          <label className="field">
            <span>Maximum index sessions</span>
            <select
              aria-label="Maximum index sessions"
              disabled={operation !== null}
              onChange={(event) => setIndexMaxSessions(Number(event.target.value))}
              value={indexMaxSessions}
            >
              {INDEX_LIMITS.map((limit) => <option key={limit} value={limit}>{limit}</option>)}
            </select>
          </label>
          <button
            className="button button--secondary button--full"
            disabled={!status.consent_active || operation !== null}
            onClick={() => void indexSessions()}
            type="button"
          >
            {operation === "index" ? "Indexing metadata..." : "Refresh content-discarding index"}
          </button>
          {!status.consent_active && <small>Grant access before reading the provider source.</small>}
        </aside>
      </div>

      <section className="source-selection" aria-labelledby="source-selection-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Analysis scope</p>
            <h2 id="source-selection-title">Select projects and sessions</h2>
            <p>Project selection includes its listed sessions. Individual selections stay independent.</p>
          </div>
          <div className="selection-actions">
            <span>{selectedSessionIds.length} visible {selectedSessionIds.length === 1 ? "session" : "sessions"} selected</span>
            <label className="field selection-limit">
              <span>Maximum analysis sessions</span>
              <select
                aria-label="Maximum analysis sessions"
                disabled={operation !== null}
                onChange={(event) => setAnalysisMaxSessions(Number(event.target.value))}
                value={analysisMaxSessions}
              >
                {ANALYSIS_LIMITS.map((limit) => <option key={limit} value={limit}>{limit}</option>)}
              </select>
            </label>
            <button
              className="button button--primary"
              disabled={
                !status.consent_active ||
                operation !== null ||
                (selectedProjects.size === 0 && selectedSessions.size === 0)
              }
              onClick={() => void analyzeSelection()}
              type="button"
            >
              {operation === "analyze" ? "Analyzing..." : "Analyze selection"}
            </button>
          </div>
        </div>
        <div className="label-discovery" role="note">
          <div className="label-discovery__copy">
            <span className="label-discovery__icon"><Icon name="search" /></span>
            <div>
              <strong>Find missing Codex labels</strong>
              <p>
                For the selected scope, read at most 25 already-indexed task
                summaries. Only the explicit task name and project-folder basename
                can be retained; turns and transcript content are rejected.
              </p>
            </div>
          </div>
          <div className="label-discovery__controls">
            <label className="field selection-limit">
              <span>Maximum summary reads</span>
              <select
                aria-label="Maximum label summary reads"
                disabled={operation !== null}
                onChange={(event) => setLabelMaxSessions(Number(event.target.value))}
                value={labelMaxSessions}
              >
                {LABEL_LIMITS.map((limit) => (
                  <option key={limit} value={limit}>{limit}</option>
                ))}
              </select>
            </label>
            <button
              className="button button--secondary"
              disabled={
                !status.consent_active ||
                operation !== null ||
                (selectedProjects.size === 0 && selectedSessions.size === 0)
              }
              onClick={() => void enrichLabels()}
              type="button"
            >
              {operation === "labels" ? "Reading summaries..." : "Find missing labels"}
            </button>
          </div>
        </div>

        {labelEditor && (
          <form
            className="label-editor"
            onSubmit={(event) => {
              event.preventDefault();
              void saveManualLabel();
            }}
          >
            <div>
              <strong>
                Edit local {labelEditor.entityKind} label
              </strong>
              <p>
                Stored only in Prompt Enhancer. Saving does not rename the Codex
                project or task.
              </p>
            </div>
            <label className="field label-editor__field">
              <span>Local display label</span>
              <input
                aria-label="Local display label"
                autoFocus
                maxLength={labelEditor.entityKind === "project" ? 120 : 160}
                onChange={(event) => setLabelDraft(event.target.value)}
                value={labelDraft}
              />
            </label>
            <div className="label-editor__actions">
              {labelEditor.origin === "manual" && (
                <button
                  className="button button--danger-ghost"
                  disabled={operation !== null}
                  onClick={() => void clearManualLabel()}
                  type="button"
                >
                  Clear override
                </button>
              )}
              <button
                className="button button--secondary"
                disabled={operation !== null}
                onClick={() => {
                  setLabelEditor(null);
                  setLabelDraft("");
                }}
                type="button"
              >
                Cancel
              </button>
              <button
                className="button button--primary"
                disabled={operation !== null || labelDraft.trim().length === 0}
                type="submit"
              >
                {operation === "manual-label" ? "Saving..." : "Save locally"}
              </button>
            </div>
          </form>
        )}

        {groupedSessions.length === 0 ? (
          <div className="empty-inbox">
            <span><Icon name="search" /></span>
            <h2>No indexed Codex sessions</h2>
            <p>Grant access, then run a bounded metadata index.</p>
          </div>
        ) : (
          <div className="project-groups">
            {groupedSessions.map(([projectId, projectSessions]) => {
              const projectSelected = selectedProjects.has(projectId);
              const rawProjectName = projectSessions[0]?.project_display_name;
              const projectName = displayName(rawProjectName, "Unnamed project");
              const projectOrigin =
                projectSessions[0]?.project_display_name_origin ?? "unknown";
              const projectRevision =
                projectSessions[0]?.project_manual_label_revision ?? 0;

              return (
                <article className="project-group" key={projectId}>
                  <header className="project-group__header">
                    <label>
                      <input
                        checked={projectSelected}
                        onChange={(event) => toggleProject(projectId, event.target.checked)}
                        type="checkbox"
                        value={projectId}
                      />
                      <span>
                        <strong>{projectName}</strong>
                        <small>
                          Project ID <span className="mono">{shortId(projectId)}</span> - {projectSessions.length} indexed{" "}
                          {projectSessions.length === 1 ? "session" : "sessions"}
                        </small>
                      </span>
                    </label>
                    <div className="label-meta-actions">
                      <span className="status-pill status-pill--info">
                        {labelOriginText(projectOrigin)}
                      </span>
                      <button
                        aria-label="Edit local project label"
                        className="button button--secondary button--compact"
                        disabled={operation !== null}
                        onClick={() =>
                          beginLabelEdit(
                            "project",
                            projectId,
                            rawProjectName ?? "",
                            projectOrigin,
                            projectRevision,
                          )
                        }
                        type="button"
                      >
                        Edit label
                      </button>
                    </div>
                  </header>
                  <ul className="source-session-list">
                    {projectSessions.map((session) => (
                      <li key={session.session_id}>
                        <label>
                          <input
                            checked={projectSelected || selectedSessions.has(session.session_id)}
                            disabled={projectSelected}
                            onChange={(event) => toggleSession(session.session_id, event.target.checked)}
                            type="checkbox"
                            value={session.session_id}
                          />
                          <span>
                            <strong>{displayName(session.session_display_name, "Unnamed session")}</strong>
                            <small>
                              Session ID <span className="mono">{shortId(session.session_id)}</span> - {safeDate(session.started_at)} -{" "}
                              {session.events_complete ? "Complete event set" : "Partial event set"}
                            </small>
                          </span>
                        </label>
                        <div className="label-meta-actions label-meta-actions--session">
                          <span className="status-pill status-pill--info">
                            {labelOriginText(session.session_display_name_origin)}
                          </span>
                          <button
                            aria-label="Edit local session label"
                            className="button button--secondary button--compact"
                            disabled={operation !== null}
                            onClick={() =>
                              beginLabelEdit(
                                "session",
                                session.session_id,
                                session.session_display_name ?? "",
                                session.session_display_name_origin,
                                session.session_manual_label_revision,
                              )
                            }
                            type="button"
                          >
                            Edit label
                          </button>
                        </div>
                        <span className="status-pill">{session.terminal_state ?? "State unknown"}</span>
                        <button
                          className="button button--secondary"
                          onClick={() => void loadMetrics(session.session_id)}
                          type="button"
                        >
                          Metrics
                        </button>
                      </li>
                    ))}
                  </ul>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {focusedSession && (
        <section className="session-metrics" aria-labelledby="session-metrics-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Deterministic output</p>
              <h2 id="session-metrics-title">{displayName(focusedSessionRecord?.session_display_name, "Unnamed session")}</h2>
              <p>Session metrics - <span className="mono">Session ID {shortId(focusedSession)}</span></p>
            </div>
            <button
              className="button button--secondary"
              disabled={metricsLoading === focusedSession}
              onClick={() => void loadMetrics(focusedSession)}
              type="button"
            >
              {metricsLoading === focusedSession ? "Refreshing..." : "Refresh metrics"}
            </button>
          </div>
          {metricsError && <p className="local-source-error" role="alert">{metricsError}</p>}
          {metricsLoading === focusedSession && focusedMetrics === undefined ? (
            <div className="async-state" role="status"><span className="spinner" /><span>Loading deterministic metrics...</span></div>
          ) : focusedMetrics?.length ? (
            <div className="local-metric-grid">
              {focusedMetrics.map((metric) => (
                <article className="local-metric-card" key={`${metric.key}@${metric.version}`}>
                  <div>
                    <span className="status-pill">{metric.dimension}</span>
                    <small>{metric.source}</small>
                  </div>
                  <h3>{metric.display_name}</h3>
                  <strong className="local-metric-card__value">{metricValue(metric)}</strong>
                  <dl>
                    <div><dt>Coverage</dt><dd>{Math.round(metric.coverage * 100)}%</dd></div>
                    <div><dt>Observed</dt><dd>{metric.observed_count}/{metric.eligible_count}</dd></div>
                    <div><dt>Definition</dt><dd>v{metric.version}</dd></div>
                  </dl>
                  <p className="mono">{metric.key}</p>
                </article>
              ))}
            </div>
          ) : (
            <div className="no-analysis">
              <span><Icon name="activity" /></span>
              <div>
                <h3>No metrics stored for this session</h3>
                <p>Select it for analysis, or refresh after a completed run.</p>
              </div>
            </div>
          )}
        </section>
      )}
    </section>
  );
}
