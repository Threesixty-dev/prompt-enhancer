import { useEffect, useMemo, useState } from "react";
import type {
  ModelEnsembleWatchSnapshot,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import type { MetricCategory } from "../../shared/platform/platform";
import { QUALITY_ANALYSIS_DEFINITIONS } from "../quality-profile/qualityProfile";
import { ModelEnsembleRadar } from "./ModelEnsembleRadar";

export function ModelEnsembleOverlay({ transport }: { transport: PromptEnhancerTransport }) {
  const [snapshot, setSnapshot] = useState<ModelEnsembleWatchSnapshot | null>(null);
  const [category, setCategory] = useState<MetricCategory>("prompt-quality");
  const [disconnected, setDisconnected] = useState(false);

  useEffect(() => {
    if (transport.getActiveModelEnsembleWatch === undefined) {
      setDisconnected(true);
      return;
    }
    let stopped = false;
    let timer: number | undefined;
    let controller: AbortController | null = null;
    const poll = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const value = await transport.getActiveModelEnsembleWatch!(controller.signal);
        if (stopped) return;
        setSnapshot(value);
        setDisconnected(false);
        timer = window.setTimeout(
          () => void poll(),
          value.watch.state === "running" || value.watch.state === "queued" ? 2_000 : 15_000,
        );
      } catch {
        if (stopped || controller.signal.aborted) return;
        setDisconnected(true);
        timer = window.setTimeout(() => void poll(), 5_000);
      }
    };
    const visible = () => {
      if (document.visibilityState === "visible") void poll();
    };
    document.addEventListener("visibilitychange", visible);
    void poll();
    return () => {
      stopped = true;
      controller?.abort();
      if (timer !== undefined) window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [transport]);

  const selected = useMemo(() => {
    if (snapshot?.latest_run === null || snapshot === null) return [];
    const kind = category === "prompt-quality" ? "prompt" : "logic";
    const definitions = new Map(
      QUALITY_ANALYSIS_DEFINITIONS.filter((item) => item.kind === kind)
        .map((item) => [item.key, item]),
    );
    return snapshot.latest_run.metrics
      .filter((metric) => definitions.has(metric.metric_key))
      .map((metric) => ({ metric, definition: definitions.get(metric.metric_key)! }));
  }, [category, snapshot]);

  return (
    <main className="model-ensemble-overlay">
      <header>
        <div>
          <p className="eyebrow">Continuous local ensemble</p>
          <h1>Live metric watch</h1>
        </div>
        <span className={`model-ensemble-overlay__connection${disconnected ? " is-stale" : ""}`}>
          {disconnected ? "Disconnected · retaining last receipt" : snapshot?.watch.state ?? "No active watch"}
        </span>
      </header>
      {snapshot === null ? (
        <section className="model-ensemble__empty" role="status">
          Choose “Watch this session” in the full dashboard. This window never
          selects or reads a session on its own.
        </section>
      ) : (
        <>
          <section className="model-ensemble-overlay__progress" aria-live="polite">
            <strong>
              {snapshot.watch.state === "running"
                ? `Model ${snapshot.watch.progress_completed} of ${snapshot.watch.progress_total}`
                : snapshot.watch.state === "queued" ? "Update queued" : "Latest observed snapshot"}
            </strong>
            <span>Generation {snapshot.watch.generation} · serial local lane</span>
            <progress max={snapshot.watch.progress_total} value={snapshot.watch.progress_completed} />
          </section>
          <div className="model-ensemble-overlay__tabs" role="group" aria-label="Radar lens">
            <button aria-pressed={category === "prompt-quality"} onClick={() => setCategory("prompt-quality")} type="button">Prompt</button>
            <button aria-pressed={category === "reasoning"} onClick={() => setCategory("reasoning")} type="button">Reasoning</button>
          </div>
          {snapshot.latest_run === null ? (
            <p className="model-ensemble__empty">The first ten-model update has not completed yet.</p>
          ) : (
            <>
              <ModelEnsembleRadar category={category} compact run={snapshot.latest_run} />
              <section aria-label="Metric states" className="model-ensemble-overlay__metrics">
                {selected.map(({ metric, definition }) => (
                  <article key={metric.metric_key}>
                    <div><strong>{definition.shortLabel}</strong><span>{metric.value_state.replaceAll("_", " ")}</span></div>
                    <b>{metric.numeric_value == null ? "—" : `${Math.round(metric.numeric_value * 100)}%`}</b>
                    <small>known {metric.known_chunk_count}/{metric.total_chunk_count} · abstained {metric.abstained_chunk_count} · unsupported {metric.unsupported_chunk_count}</small>
                  </article>
                ))}
              </section>
            </>
          )}
          <a
            className="model-ensemble-overlay__open"
            href={`/projects/${snapshot.watch.project_id}/sessions/${snapshot.watch.session_id}/metrics/${category}`}
          >
            Open full local dashboard
          </a>
        </>
      )}
      <footer>Uncalibrated committee evidence · no text persisted · blocking work is not forcibly preempted</footer>
    </main>
  );
}
