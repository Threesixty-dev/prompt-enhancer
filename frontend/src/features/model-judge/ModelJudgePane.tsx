import { useCallback, useEffect, useState } from "react";
import type { PromptEnhancerTransport, SessionInterpretation, SessionJudgments } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import "./ModelJudgePane.css";

const LABEL_TEXT: Record<string, string> = {
  low: "low",
  medium: "medium",
  high: "high",
  cannot_judge: "cannot judge",
};

/**
 * What the local model judge said about this session, shown apart from the
 * metrics on purpose: three labels per model, the questions they answer, and
 * the standing caveat. No label here is ever a metric value.
 */
export function ModelJudgePane({
  sessionId,
  transport,
}: {
  sessionId: string;
  transport: Pick<PromptEnhancerTransport, "getModelJudgments"> & Partial<Pick<PromptEnhancerTransport, "judgeSessionWithModel" | "interpretSessionWithModel">>;
}) {
  const [data, setData] = useState<SessionJudgments | null>(null);
  const [reading, setReading] = useState<SessionInterpretation | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [state, setState] = useState<"loading" | "ready" | "unavailable" | "error">("loading");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const value = await transport.getModelJudgments(sessionId, signal);
      if (signal?.aborted) return;
      setData(value);
      setState("ready");
    } catch (caught) {
      if (signal?.aborted) return;
      setState(caught instanceof TransportError && caught.status === 404 ? "unavailable" : "error");
    }
  }, [sessionId, transport]);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    setMessage("");
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  async function explain() {
    if (!transport.interpretSessionWithModel) return;
    setExplaining(true);
    setMessage("");
    try {
      setReading(await transport.interpretSessionWithModel(sessionId));
    } catch (caught) {
      setMessage(caught instanceof TransportError && caught.status === 409
        ? "No local model is active - activate one on the Models page."
        : "The model could not explain this session right now.");
    } finally {
      setExplaining(false);
    }
  }

  async function judgeNow() {
    if (!transport.judgeSessionWithModel) return;
    setBusy(true);
    setMessage("");
    try {
      const outcome = await transport.judgeSessionWithModel(sessionId);
      setMessage(outcome.raw_valid ? `Judged by ${outcome.model_alias}.` : "The model did not answer in the required format.");
      await load();
    } catch (caught) {
      setMessage(caught instanceof TransportError && caught.message.includes("409")
        ? "No local model is active - activate one on the Models page."
        : "The model judge is not available right now.");
    } finally {
      setBusy(false);
    }
  }

  if (state === "unavailable") return null;
  if (state === "loading") return <section className="model-judge-pane" aria-busy="true"><p className="model-judge-pane__note">Looking for model judgments…</p></section>;
  if (state === "error" || !data) return <section className="model-judge-pane"><p className="model-judge-pane__note" role="alert">Model judgments could not be read.</p></section>;

  const byModel = new Map<string, SessionJudgments["judgments"]>();
  for (const judgment of data.judgments) {
    const list = byModel.get(judgment.model_alias) ?? [];
    list.push(judgment);
    byModel.set(judgment.model_alias, list);
  }
  const metricKeys = Object.keys(data.questions);

  return (
    <section aria-labelledby="model-judge-pane-title" className="model-judge-pane">
      <header className="model-judge-pane__head">
        <div>
          <p className="eyebrow">Model judge · experimental, not a metric</p>
          <h3 id="model-judge-pane-title">What the local model thinks of this session</h3>
        </div>
        <div className="model-judge-pane__actions">
          {transport.interpretSessionWithModel && (
            <button className="button button--primary" disabled={explaining || !data.active_model_alias} onClick={() => void explain()} title={data.active_model_alias ? `Ask ${data.active_model_alias} to explain this session` : "Activate a model on the Models page first"} type="button">
              {explaining ? "Explaining…" : "Explain this session"}
            </button>
          )}
          {transport.judgeSessionWithModel && (
            <button className="button button--ghost" disabled={busy || !data.active_model_alias} onClick={() => void judgeNow()} title={data.active_model_alias ? `Ask ${data.active_model_alias} now` : "Activate a model on the Models page first"} type="button">
              {busy ? "Judging…" : byModel.size > 0 ? "Judge again" : "Judge now"}
            </button>
          )}
        </div>
      </header>
      {byModel.size === 0 ? (
        <p className="model-judge-pane__note">
          {data.active_model_alias
            ? `No judgment stored yet; ${data.active_model_alias} judges new sessions automatically after each index.`
            : "No judgment stored and no local model is active."}
        </p>
      ) : (
        <div className="model-judge-pane__table-wrap">
          <table className="model-judge-pane__table">
            <thead>
              <tr>
                <th scope="col">Question</th>
                {[...byModel.keys()].map((alias) => <th key={alias} scope="col">{alias}{alias === data.active_model_alias ? " · active" : ""}</th>)}
              </tr>
            </thead>
            <tbody>
              {metricKeys.map((key) => (
                <tr key={key}>
                  <th scope="row"><span className="model-judge-pane__metric">{key}</span><span className="model-judge-pane__question">{data.questions[key]}</span></th>
                  {[...byModel.entries()].map(([alias, list]) => {
                    const hit = list.find((j) => j.metric_key === key);
                    return (
                      <td key={alias} data-label={hit?.label ?? "none"}>
                        {hit ? <span className={`model-judge-pane__label model-judge-pane__label--${hit.label}`}>{LABEL_TEXT[hit.label] ?? hit.label}</span> : <span className="model-judge-pane__none">—</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {reading && (
        <section className="model-judge-pane__reading" aria-label="Model interpretation">
          {reading.summary && <p className="model-judge-pane__reading-summary">{reading.summary}</p>}
          <div className="model-judge-pane__reading-grid">
            <div>
              <h4>What went well</h4>
              {reading.strengths.length ? <ul>{reading.strengths.map((s) => <li key={s}>{s}</li>)}</ul> : <p className="model-judge-pane__note">nothing singled out</p>}
            </div>
            <div>
              <h4>What to change next time</h4>
              {reading.improvements.length ? <ul>{reading.improvements.map((s) => <li key={s}>{s}</li>)}</ul> : <p className="model-judge-pane__note">nothing singled out</p>}
            </div>
          </div>
          {reading.reframed_prompt && (
            <div className="model-judge-pane__reframed">
              <h4>How the first request could have been phrased</h4>
              <pre>{reading.reframed_prompt}</pre>
            </div>
          )}
          <p className="model-judge-pane__caveat">{reading.caveat} ({reading.model_alias}, {reading.metrics_seen} metric readings)</p>
        </section>
      )}
      {message && <p className="model-judge-pane__note" aria-live="polite">{message}</p>}
      <p className="model-judge-pane__caveat">{data.caveat}</p>
    </section>
  );
}
