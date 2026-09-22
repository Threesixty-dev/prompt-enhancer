import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type {
  MetricCoverageReport,
  PromptEnhancerTransport,
  Provider,
} from "../../shared/api/contracts";
import { parseMetricCoverageReport } from "../../shared/api/httpTransport";
import "./MetricCoveragePanel.css";

type CoverageOwner = {
  projectId?: string;
  provider: Provider;
  transport: PromptEnhancerTransport;
};

type CoverageState =
  | { owner: CoverageOwner; status: "loading" }
  | {
    owner: CoverageOwner;
    report: MetricCoverageReport;
    status: "ready";
    freshness:
      | "current"
      | "refreshing"
      | "failed"
      | "cancelled"
      | "timed_out";
  }
  | {
    owner: CoverageOwner;
    status: "error";
    reason: "failed" | "cancelled" | "timed_out";
  };

type CoverageAttempt = {
  controller: AbortController;
  generation: number;
  owner: CoverageOwner;
  snapshot?: MetricCoverageReport;
  timeoutId?: ReturnType<typeof setTimeout>;
};

const COVERAGE_REQUEST_TIMEOUT_MS = 15_000;
const REQUEST_NOT_DISPATCHED = Symbol("coverage request not dispatched");

function sameOwner(left: CoverageOwner, right: CoverageOwner): boolean {
  return left.transport === right.transport &&
    left.provider === right.provider && left.projectId === right.projectId;
}

function stateTotal(
  states: MetricCoverageReport["metrics"][number]["contract_compatible_result_states"],
): number {
  return states.known + states.unknown + states.not_applicable +
    states.abstained + states.execution_error;
}

export function MetricCoveragePanel({
  transport,
  provider,
  projectId,
}: {
  transport: PromptEnhancerTransport;
  provider: Provider;
  projectId?: string;
}) {
  const owner = { projectId, provider, transport };
  const [state, setState] = useState<CoverageState>({
    owner,
    status: "loading",
  });
  const activeAttemptRef = useRef<CoverageAttempt | null>(null);
  const generationRef = useRef(0);
  const titleId = useId();
  const statusId = useId();

  const finishAttempt = useCallback((
    attempt: CoverageAttempt,
    reason: "failed" | "cancelled" | "timed_out",
  ) => {
    if (activeAttemptRef.current !== attempt) return;
    activeAttemptRef.current = null;
    clearTimeout(attempt.timeoutId);
    if (!attempt.controller.signal.aborted) attempt.controller.abort();
    if (attempt.snapshot) {
      setState({
        owner: attempt.owner,
        report: attempt.snapshot,
        status: "ready",
        freshness: reason,
      });
    } else {
      setState({ owner: attempt.owner, status: "error", reason });
    }
  }, []);

  const beginRequest = useCallback((snapshot?: MetricCoverageReport) => {
    if (activeAttemptRef.current !== null) return;

    const requestOwner = { projectId, provider, transport };
    const controller = new AbortController();
    const attempt: CoverageAttempt = {
      controller,
      generation: generationRef.current + 1,
      owner: requestOwner,
      snapshot,
    };
    generationRef.current = attempt.generation;
    activeAttemptRef.current = attempt;
    setState(snapshot
      ? {
        owner: requestOwner,
        report: snapshot,
        status: "ready",
        freshness: "refreshing",
      }
      : { owner: requestOwner, status: "loading" });

    attempt.timeoutId = setTimeout(() => {
      finishAttempt(attempt, "timed_out");
    }, COVERAGE_REQUEST_TIMEOUT_MS);

    void Promise.resolve()
      .then<MetricCoverageReport | typeof REQUEST_NOT_DISPATCHED>(() => {
        if (
          activeAttemptRef.current !== attempt ||
          generationRef.current !== attempt.generation ||
          controller.signal.aborted
        ) return REQUEST_NOT_DISPATCHED;
        return projectId === undefined
          ? transport.getMetricCoverage(provider, controller.signal)
          : transport.getProjectMetricCoverage(projectId, provider, controller.signal);
      })
      .then((value) => {
        if (
          value === REQUEST_NOT_DISPATCHED ||
          activeAttemptRef.current !== attempt ||
          generationRef.current !== attempt.generation ||
          controller.signal.aborted
        ) {
          return;
        }
        const report = parseMetricCoverageReport(
          value,
          provider,
          projectId === undefined ? "provider_catalog" : "one_project",
        );
        if (
          activeAttemptRef.current !== attempt ||
          generationRef.current !== attempt.generation ||
          controller.signal.aborted
        ) return;
        activeAttemptRef.current = null;
        clearTimeout(attempt.timeoutId);
        setState({
          owner: requestOwner,
          report,
          status: "ready",
          freshness: "current",
        });
      })
      .catch(() => {
        if (activeAttemptRef.current === attempt && !controller.signal.aborted) {
          finishAttempt(attempt, "failed");
        }
      });
  }, [finishAttempt, projectId, provider, transport]);

  const cancelRequest = useCallback(() => {
    const attempt = activeAttemptRef.current;
    const currentOwner = { projectId, provider, transport };
    if (attempt !== null && sameOwner(attempt.owner, currentOwner)) {
      finishAttempt(attempt, "cancelled");
    }
  }, [finishAttempt, projectId, provider, transport]);

  useEffect(() => {
    beginRequest();
    return () => {
      const attempt = activeAttemptRef.current;
      if (attempt !== null) {
        activeAttemptRef.current = null;
        clearTimeout(attempt.timeoutId);
        attempt.controller.abort();
      }
      generationRef.current += 1;
    };
  }, [beginRequest]);

  const visibleState = sameOwner(state.owner, owner)
    ? state
    : { owner, status: "loading" } as CoverageState;

  const totals = useMemo(() => {
    if (visibleState.status !== "ready") return null;
    return visibleState.report.metrics.reduce(
      (result, metric) => ({
        compatible: result.compatible +
          stateTotal(metric.contract_compatible_result_states),
        incompatible: result.incompatible + metric.contract_incompatible_result_count,
        cohorts: result.cohorts + metric.compatible_provenance_cohort_count,
      }),
      { compatible: 0, incompatible: 0, cohorts: 0 },
    );
  }, [visibleState]);

  if (visibleState.status === "loading") {
    return (
      <section className="metric-coverage-panel" aria-busy="true">
        <p className="eyebrow">Measurement coverage</p>
        <h2 id={titleId}>Checking the local metric snapshot...</h2>
        <p id={statusId} role="status">
          Reading content-free counts from the stored SQLite index.
        </p>
        <button
          className="button button--secondary button--compact"
          onClick={cancelRequest}
          type="button"
        >
          Cancel coverage request
        </button>
      </section>
    );
  }

  if (visibleState.status === "error") {
    const errorCopy = visibleState.reason === "cancelled"
      ? "The coverage request was cancelled."
      : visibleState.reason === "timed_out"
        ? "The coverage request timed out after 15 seconds."
        : "The content-free coverage report could not be verified.";
    return (
      <section className="metric-coverage-panel metric-coverage-panel--unknown">
        <p className="eyebrow">Measurement coverage</p>
        <h2 id={titleId}>Metric coverage: Unknown</h2>
        <p id={statusId} role="alert">
          {errorCopy} Existing project
          and session views remain available; no missing count is shown as zero.
        </p>
        <button
          className="button button--secondary button--compact"
          onClick={() => beginRequest()}
          type="button"
        >
          Retry coverage
        </button>
      </section>
    );
  }

  const { report } = visibleState;
  const attemptable = report.capability_report.structurally_attemptable_metric_count;
  return (
    <section
      aria-busy={visibleState.freshness === "refreshing"}
      aria-labelledby={titleId}
      className="metric-coverage-panel"
    >
      <header>
        <div>
          <p className="eyebrow">Measurement coverage</p>
          <h2 id={titleId}>Coaching metric coverage</h2>
          <p>
            {attemptable} of {report.metrics.length} metric definitions are structurally
            attemptable.
          </p>
        </div>
        <span className="status-pill status-pill--info">
          {visibleState.freshness === "current"
            ? "Exact SQLite counts"
            : "Previous verified snapshot"}
        </span>
      </header>

      <div
        className="metric-coverage-panel__request-status"
        id={statusId}
        role="status"
      >
        <p>Snapshot generated at <time dateTime={report.generated_at}>{report.generated_at}</time>.</p>
        {visibleState.freshness === "refreshing" && (
          <p>Refreshing coverage; displayed snapshot is stale.</p>
        )}
        {visibleState.freshness === "failed" && (
          <p>Coverage refresh failed; displayed snapshot is stale.</p>
        )}
        {visibleState.freshness === "cancelled" && (
          <p>Coverage refresh was cancelled; displayed snapshot is stale.</p>
        )}
        {visibleState.freshness === "timed_out" && (
          <p>Coverage refresh timed out after 15 seconds; displayed snapshot is stale.</p>
        )}
        {visibleState.freshness === "current" && (
          <p>Last verified snapshot. Refresh to check for newer data.</p>
        )}
      </div>
      <div className="metric-coverage-panel__actions">
        {visibleState.freshness === "refreshing" ? (
          <button
            className="button button--secondary button--compact"
            onClick={cancelRequest}
            type="button"
          >
            Cancel coverage request
          </button>
        ) : (
          <button
            className="button button--secondary button--compact"
            onClick={() => beginRequest(report)}
            type="button"
          >
            {visibleState.freshness === "current" ? "Refresh coverage" : "Retry coverage"}
          </button>
        )}
      </div>

      <p className="metric-coverage-panel__explanation">
        Structural support describes available provider evidence channels only. It does
        not mean {attemptable} metrics were measured in any session.
      </p>
      <dl className="metric-coverage-panel__totals" aria-label="Coverage snapshot counts" role="group">
        <div><dt>Indexed sessions</dt><dd>{report.indexed_session_count}</dd></div>
        <div><dt>Latest completed snapshots</dt><dd>{report.latest_completed_snapshot_count}</dd></div>
        <div><dt>Contract-compatible stored results</dt><dd>{totals?.compatible}</dd></div>
        <div><dt>Contract-incompatible selected snapshots</dt><dd>{totals?.incompatible}</dd></div>
        <div><dt>Per-metric provenance cohorts</dt><dd>{totals?.cohorts}</dd></div>
        <div><dt>Unrecognized stored result records</dt><dd>{report.unrecognized_result_record_count}</dd></div>
      </dl>
      <dl className="metric-coverage-panel__totals" aria-label="Latest analysis attempts" role="group">
        <div><dt>Latest attempt completed</dt><dd>{report.latest_profile_runs.completed}</dd></div>
        <div><dt>Latest attempt running</dt><dd>{report.latest_profile_runs.running}</dd></div>
        <div><dt>Latest attempt failed</dt><dd>{report.latest_profile_runs.failed}</dd></div>
        <div><dt>Never run</dt><dd>{report.latest_profile_runs.never_run}</dd></div>
      </dl>
      <dl className="metric-coverage-panel__totals" aria-label="Automation scope" role="group">
        <div><dt>Effective automation grants</dt><dd>{report.effective_automation_grant_count}</dd></div>
        <div><dt>Effective automation projects</dt><dd>{report.effective_automation_project_count}</dd></div>
      </dl>
      <p className="metric-coverage-panel__boundary" role="note">
        Automation is scoped to bounded newest sessions that are new or changed. Full
        catalog automation coverage is not guaranteed; grant and project totals do not
        mean every metric or session was scheduled.
      </p>

      <details className="metric-coverage-panel__details">
        <summary>Metric-by-metric counts</summary>
        <div className="metric-coverage-panel__table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col">Structure</th>
                <th scope="col">Selected</th>
                <th scope="col">Not selected</th>
                <th scope="col">Scope unknown</th>
                <th scope="col">Known</th>
                <th scope="col">Unknown</th>
                <th scope="col">Not applicable</th>
                <th scope="col">Abstained</th>
                <th scope="col">Execution error</th>
                <th scope="col">Incompatible selections</th>
                <th scope="col">Absent</th>
                <th scope="col">Cohorts</th>
                <th scope="col">Automation-selected projects</th>
              </tr>
            </thead>
            <tbody>
              {report.metrics.map((metric) => (
                <tr key={`${metric.metric_key}.v${metric.metric_version}`}>
                  <th scope="row">{metric.display_name}</th>
                  <td>{metric.structural_support}</td>
                  <td>{metric.selected_run_count}</td>
                  <td>{metric.not_selected_run_count}</td>
                  <td>{metric.unknown_scope_run_count}</td>
                  <td>{metric.contract_compatible_result_states.known}</td>
                  <td>{metric.contract_compatible_result_states.unknown}</td>
                  <td>{metric.contract_compatible_result_states.not_applicable}</td>
                  <td>{metric.contract_compatible_result_states.abstained}</td>
                  <td>{metric.contract_compatible_result_states.execution_error}</td>
                  <td>{metric.contract_incompatible_result_count}</td>
                  <td>{metric.expected_result_absent_count}</td>
                  <td>{metric.compatible_provenance_cohort_count}</td>
                  <td>{metric.effective_automation_selected_project_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <p className="metric-coverage-panel__boundary" role="note">
        These counts are exact for this SQLite snapshot, not for all provider history.
        Provider-history completeness is unknown and no authoritative provider snapshot
        or cursor is available, so no provider-history percentage is shown.
      </p>
      <p className="metric-coverage-panel__boundary" role="note">
        Contract-compatible means each stored result passed the current metric contract.
        Per-metric provenance cohorts are counted without being merged into one comparison.
      </p>
      <p className="metric-coverage-panel__boundary" role="note">
        The cached provider-capability report was not captured atomically with the SQLite
        counts, so structural support and stored-result counts are separate evidence axes.
      </p>
    </section>
  );
}
