import { useCallback, useEffect, useState } from "react";
import type {
  AnalysisResult,
  AnalysisRun,
  PromptEnhancerTransport,
  TaskRevision,
} from "../../shared/api/contracts";
import type { AppRoute } from "../../shared/platform/platform";
import { MetricObservationCard } from "../../entities/analysis/MetricObservationCard";
import { ProvenancePanel } from "../../entities/analysis/ProvenancePanel";
import { TaskSummary } from "../../entities/task/TaskSummary";
import { nextIdempotencyKey } from "../../shared/api/idempotency";
import { ErrorState, LoadingState } from "../../shared/ui/AsyncState";
import { Icon } from "../../shared/ui/Icon";

export function TaskDetail({
  taskId,
  revision,
  transport,
  navigate,
}: {
  taskId: string;
  revision: number;
  transport: PromptEnhancerTransport;
  navigate: (route: AppRoute) => void;
}) {
  const [task, setTask] = useState<TaskRevision | null>(null);
  const [run, setRun] = useState<AnalysisRun | null>(null);
  const [results, setResults] = useState<AnalysisResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [taskResponse, runsResponse] = await Promise.all([
        transport.getTaskRevision(taskId, revision),
        transport.listAnalysisRuns(taskId),
      ]);
      setTask(taskResponse.task);
      const matchingRun = runsResponse.runs.find((item) => item.task_revision === revision) ?? null;
      setRun(matchingRun);
      if (matchingRun) {
        const detail = await transport.getAnalysisRun(matchingRun.run_id);
        setResults(detail.results);
      } else {
        setResults([]);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Task detail could not be loaded");
    } finally {
      setLoading(false);
    }
  }, [revision, taskId, transport]);

  useEffect(() => {
    void load();
  }, [load]);

  async function runAnalysis() {
    setAnalyzing(true);
    setError(null);
    try {
      await transport.startAnalysis(taskId, revision, nextIdempotencyKey("analysis"));
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Task analysis could not be started");
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <div className="task-page">
      <button className="breadcrumb" onClick={() => navigate({ name: "discovery" })} type="button">
        <Icon name="chevron" /> Discovery inbox
      </button>
      {loading ? (
        <LoadingState label="Loading task analysis" />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : task ? (
        <>
          <TaskSummary task={task} />
          <section aria-labelledby="metrics-heading" className="metrics-section">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Latest immutable run</p>
                <h2 id="metrics-heading">Metric observations</h2>
                <p>Each result keeps its state, coverage, evidence, and definition version.</p>
              </div>
              {run && <span className={`run-status run-status--${run.status}`}>{run.status}</span>}
            </div>
            {run ? (
              <div className="metric-grid">
                {results.map((result) => (
                  <MetricObservationCard key={`${result.key}-${result.version}`} result={result} />
                ))}
              </div>
            ) : (
              <div className="no-analysis">
                <span><Icon name="activity" /></span>
                <div><h3>No analysis run yet</h3><p>The task revision exists; metrics remain unknown until an explicit run is created.</p></div>
                <button
                  className="button button--primary"
                  disabled={analyzing}
                  onClick={() => void runAnalysis()}
                  type="button"
                >
                  <Icon name="activity" /> {analyzing ? "Analyzing..." : "Run analysis"}
                </button>
              </div>
            )}
          </section>
          {run && <ProvenancePanel results={results} run={run} />}
        </>
      ) : null}
    </div>
  );
}
