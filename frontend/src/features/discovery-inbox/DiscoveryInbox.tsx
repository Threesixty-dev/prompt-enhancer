import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  CandidateListItem,
  CandidateStatusFilter,
  PromptEnhancerTransport,
  TaskReviewResponse,
} from "../../shared/api/contracts";
import type { AppRoute } from "../../shared/platform/platform";
import { CandidateCard } from "../../entities/discovery/CandidateCard";
import { ErrorState, LoadingState } from "../../shared/ui/AsyncState";
import { Icon } from "../../shared/ui/Icon";
import { nextIdempotencyKey } from "../../shared/api/idempotency";
import { CandidateReviewPanel, mergeCommand } from "../task-review";

export function DiscoveryInbox({
  transport,
  navigate,
  onUndecidedCountChange,
}: {
  transport: PromptEnhancerTransport;
  navigate: (route: AppRoute) => void;
  onUndecidedCountChange: (count: number) => void;
}) {
  const [items, setItems] = useState<CandidateListItem[]>([]);
  const [filter, setFilter] = useState<CandidateStatusFilter>("undecided");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string>("");
  const [merging, setMerging] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [reviewOutputs, setReviewOutputs] = useState<TaskReviewResponse["output_revisions"]>([]);
  const [undecidedCount, setUndecidedCount] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await transport.listCandidates(filter);
      const undecidedResponse =
        filter === "undecided"
          ? response
          : await transport.listCandidates("undecided");
      const nextUndecidedCount = undecidedResponse.candidates.length;
      setUndecidedCount(nextUndecidedCount);
      onUndecidedCountChange(nextUndecidedCount);
      setItems(response.candidates);
      setActiveId((current) =>
        response.candidates.some((item) => item.candidate.candidate_id === current)
          ? current
          : response.candidates[0]?.candidate.candidate_id ?? null,
      );
      setSelectedIds(new Set());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Discovery inbox could not be loaded");
    } finally {
      setLoading(false);
    }
  }, [filter, onUndecidedCountChange, transport]);

  useEffect(() => {
    void load();
  }, [load]);

  const active = items.find((item) => item.candidate.candidate_id === activeId) ?? null;
  const selected = useMemo(
    () => items.filter((item) => selectedIds.has(item.candidate.candidate_id)),
    [items, selectedIds],
  );

  async function reviewed(result: TaskReviewResponse) {
    setNotice(
      result.applied
        ? `${result.action} decision saved. Immutable task history was updated.`
        : `${result.action} decision was already applied.`,
    );
    setReviewOutputs(result.output_revisions);
    await load();
    const first = result.output_revisions[0];
    if (first) {
      setNotice(`${result.action} decision saved. The new task is ready for analysis.`);
    }
  }

  async function analyzeCreatedTasks() {
    if (reviewOutputs.length === 0) return;
    setAnalyzing(true);
    setError(null);
    try {
      for (const output of reviewOutputs) {
        await transport.startAnalysis(
          output.task_id,
          output.revision,
          nextIdempotencyKey("analysis"),
        );
      }
      const first = reviewOutputs[0];
      navigate({ name: "task", taskId: first.task_id, revision: first.revision });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Task analysis could not be started");
    } finally {
      setAnalyzing(false);
    }
  }

  async function mergeSelected() {
    setError(null);
    setMerging(true);
    try {
      const command = mergeCommand(selected);
      const result = await transport.review(command, nextIdempotencyKey("merge"));
      await reviewed(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Candidates could not be merged");
    } finally {
      setMerging(false);
    }
  }

  const counts = {
    visible: items.length,
    undecided: undecidedCount,
  };

  return (
    <div className="discovery-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Task discovery</p>
          <h1>Discovery inbox</h1>
          <p>Review metadata-based groupings before they become tasks.</p>
        </div>
        <div className="page-header__meta">
          <span className="privacy-chip"><Icon name="lock" /> Local - synthetic data</span>
          <span className="count-summary"><strong>{counts.undecided}</strong> need review</span>
        </div>
      </header>

      <div aria-live="polite" className="notice-region">
        {notice && (
          <div className="success-notice">
            <Icon name="check" />
            <span>{notice}</span>
            {reviewOutputs.length > 0 && (
              <button
                className="success-notice__action"
                disabled={analyzing}
                onClick={() => void analyzeCreatedTasks()}
                type="button"
              >
                <Icon name="activity" />
                {analyzing ? "Analyzing..." : `Analyze ${reviewOutputs.length > 1 ? `${reviewOutputs.length} tasks` : "task"}`}
              </button>
            )}
            <button aria-label="Dismiss notification" onClick={() => { setNotice(""); setReviewOutputs([]); }} type="button"><Icon name="x" /></button>
          </div>
        )}
      </div>

      <div className="inbox-toolbar">
        <div aria-label="Candidate status" className="segmented-control" role="group">
          {(["undecided", "decided", "all"] as CandidateStatusFilter[]).map((value) => (
            <button
              aria-pressed={filter === value}
              key={value}
              onClick={() => setFilter(value)}
              type="button"
            >
              {value === "all" ? "All" : value === "undecided" ? "Needs review" : "Reviewed"}
            </button>
          ))}
        </div>
        <div className="inbox-toolbar__actions">
          <span aria-live="polite">{selectedIds.size} selected</span>
          <button
            className="button button--secondary"
            disabled={selectedIds.size < 2 || merging}
            onClick={() => void mergeSelected()}
            type="button"
          >
            <Icon name="merge" /> {merging ? "Merging..." : "Merge selected"}
          </button>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {loading ? (
        <LoadingState label="Loading discovery candidates" />
      ) : items.length === 0 ? (
        <div className="empty-inbox">
          <span><Icon name="check" /></span>
          <h2>Nothing in this view</h2>
          <p>Try another filter, or run synthetic discovery again.</p>
        </div>
      ) : (
        <div className="inbox-layout">
          <section aria-label={`${counts.visible} discovery candidates`} className="candidate-list">
            {items.map((item) => (
              <CandidateCard
                active={item.candidate.candidate_id === activeId}
                item={item}
                key={item.candidate.candidate_id}
                onInspect={() => setActiveId(item.candidate.candidate_id)}
                onSelect={(selectedValue) =>
                  setSelectedIds((current) => {
                    const next = new Set(current);
                    if (selectedValue) next.add(item.candidate.candidate_id);
                    else next.delete(item.candidate.candidate_id);
                    return next;
                  })
                }
                selected={selectedIds.has(item.candidate.candidate_id)}
              />
            ))}
          </section>
          {active && (
            <CandidateReviewPanel
              item={active}
              onReviewed={reviewed}
              transport={transport}
            />
          )}
        </div>
      )}
    </div>
  );
}
