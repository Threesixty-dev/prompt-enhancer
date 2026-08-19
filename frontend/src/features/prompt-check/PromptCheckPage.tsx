import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  PromptCheckRecord,
  PromptCheckRequest,
  PromptCheckResult,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import type { AppRoute } from "../../shared/platform/platform";
import { PromptMetricRadar, PromptMetricTrend } from "./promptCheckPlots";
import "./PromptCheckPage.css";

type Reading = PromptCheckResult["metrics"][number];

const SHORT_NAMES: Record<string, string> = {
  "prompt.task_definition_coverage": "Task definition",
  "prompt.problem_evidence_quality": "Problem evidence",
  "prompt.context_sufficiency": "Context cues",
  "prompt.constraint_precision": "Constraint precision",
  "prompt.acceptance_testability": "Acceptance checks",
  "prompt.deliverable_contract": "Deliverable",
};

export function shortName(key: string): string {
  return SHORT_NAMES[key] ?? key;
}

function parsePriorMessages(raw: string): PromptCheckRequest["prior_messages"] {
  const lines = raw.split(/\r?\n/);
  const messages: { role: "user" | "assistant"; content: string }[] = [];
  let current: { role: "user" | "assistant"; content: string } | null = null;
  for (const line of lines) {
    const match = line.match(/^\s*(user|assistant|you|agent|me|ai)\s*:\s*(.*)$/i);
    if (match) {
      if (current && current.content.trim()) messages.push({ ...current, content: current.content.trim() });
      const role = /^(user|you|me)$/i.test(match[1]) ? "user" : "assistant";
      current = { role, content: match[2] };
    } else if (current) {
      current.content += `\n${line}`;
    } else if (line.trim()) {
      current = { role: "user", content: line };
    }
  }
  if (current && current.content.trim()) messages.push({ ...current, content: current.content.trim() });
  return messages.slice(-24);
}

function readingValue(reading: Reading): number | null {
  return reading.state === "known" && typeof reading.value === "number" ? reading.value : null;
}

/**
 * Prompt check: paste the prompt you are about to send (and, if useful, the
 * earlier turns), get the same deterministic prompt cues the dashboard
 * computes for sessions, the local model's commentary and a reformulated
 * prompt, plus a history of your checks with trend plots. Only metrics are
 * stored; the text never is.
 */
export function PromptCheckPage({
  checkId,
  navigate,
  transport,
}: {
  checkId?: string;
  navigate: (route: AppRoute) => void;
  transport: Pick<PromptEnhancerTransport, "checkPrompt" | "getPromptCheckHistory" | "getPromptCheck">;
}) {
  const [prompt, setPrompt] = useState("");
  const [prior, setPrior] = useState("");
  const [wantCommentary, setWantCommentary] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PromptCheckResult | null>(null);
  const [history, setHistory] = useState<PromptCheckRecord[]>([]);
  const [historyState, setHistoryState] = useState<"loading" | "ready" | "unavailable" | "error">("loading");
  const [stored, setStored] = useState<PromptCheckRecord | null>(null);
  const [copied, setCopied] = useState(false);

  const loadHistory = useCallback(async (signal?: AbortSignal) => {
    try {
      const page = await transport.getPromptCheckHistory(60, 0, signal);
      if (signal?.aborted) return;
      setHistory(page.checks);
      setHistoryState("ready");
    } catch (caught) {
      if (signal?.aborted) return;
      setHistoryState(caught instanceof TransportError && caught.status === 404 ? "unavailable" : "error");
    }
  }, [transport]);

  useEffect(() => {
    const controller = new AbortController();
    void loadHistory(controller.signal);
    return () => controller.abort();
  }, [loadHistory]);

  useEffect(() => {
    if (!checkId) { setStored(null); return; }
    setResult(null);
    const controller = new AbortController();
    transport.getPromptCheck(checkId, controller.signal).then((record) => { if (!controller.signal.aborted) setStored(record); }).catch(() => { if (!controller.signal.aborted) setStored(null); });
    return () => controller.abort();
  }, [checkId, transport]);

  async function run() {
    const text = prompt.trim();
    if (!text || busy) return;
    setBusy(true);
    setError("");
    setCopied(false);
    try {
      const value = await transport.checkPrompt({
        prompt: text,
        prior_messages: parsePriorMessages(prior),
        provider: "other",
        want_commentary: wantCommentary,
      });
      setResult(value);
      await loadHistory();
    } catch (caught) {
      setError(caught instanceof TransportError && caught.status === 422
        ? "The prompt or the earlier turns are too long or empty."
        : "The check did not run. Nothing was changed.");
    } finally {
      setBusy(false);
    }
  }

  const trend = useMemo(() => [...history].reverse(), [history]);

  if (historyState === "unavailable") {
    return <section className="prompt-check"><p className="prompt-check__note">Prompt checks are not available in this runtime.</p></section>;
  }

  return (
    <section aria-labelledby="prompt-check-title" className="prompt-check">
      <header className="prompt-check__head">
        <div>
          <p className="eyebrow">Prompt check · before you send it</p>
          <h1 id="prompt-check-title">Check a prompt</h1>
          <p className="prompt-check__lede">
            Paste the prompt you are about to give Claude Code, Codex or any model. You get the same deterministic cues the dashboard
            measures for whole sessions, what the local model would change, and a reformulated version - on this machine only. Agents can
            call the same check themselves (MCP tool <code>check_prompt</code>, Claude Code hook); only metrics are kept for the plots below.
          </p>
        </div>
      </header>

      <form
        className="prompt-check__form"
        onSubmit={(event) => { event.preventDefault(); void run(); }}
      >
        <label>
          <span>Prompt</span>
          <textarea aria-label="Prompt to check" maxLength={20000} onChange={(e) => setPrompt(e.currentTarget.value)} placeholder="The prompt you are about to send…" rows={6} value={prompt} />
        </label>
        <label>
          <span>Earlier turns (optional - one per line as <code>user: …</code> / <code>assistant: …</code>; the check reads them as context)</span>
          <textarea aria-label="Earlier turns" maxLength={40000} onChange={(e) => setPrior(e.currentTarget.value)} placeholder={"user: We looked at the uploader yesterday\nassistant: The retry loop is in client.py"} rows={3} value={prior} />
        </label>
        <div className="prompt-check__controls">
          <label className="prompt-check__toggle">
            <input checked={wantCommentary} onChange={(e) => setWantCommentary(e.currentTarget.checked)} type="checkbox" />
            <span>Ask the local model for commentary and a reformulation (slower)</span>
          </label>
          <button className="button button--primary" disabled={busy || !prompt.trim()} type="submit">{busy ? "Checking…" : "Check prompt"}</button>
        </div>
      </form>
      {error && <p className="prompt-check__error" role="alert">{error}</p>}

      {result && (
        <section aria-labelledby="prompt-check-result-title" className="prompt-check__result">
          <h2 id="prompt-check-result-title">Result</h2>
          <div className="prompt-check__result-grid">
            <article className="prompt-check__card">
              <h3>Prompt cues</h3>
              <PromptMetricRadar readings={result.metrics.map((m) => ({ key: m.key, label: shortName(m.key), value: readingValue(m), higherIsBetter: m.higher_is_better }))} />
              <ul className="prompt-check__metrics">
                {result.metrics.map((m) => (
                  <li key={m.key} data-state={m.state}>
                    <div className="prompt-check__metric-head">
                      <strong>{m.display_name}</strong>
                      <span className="prompt-check__metric-value">
                        {m.state === "known" && m.numerator !== null && m.numerator !== undefined ? `${m.numerator}/${m.denominator}` : m.state.replace(/_/g, " ")}
                      </span>
                    </div>
                    {m.cues.length > 0 && (
                      <ul className="prompt-check__cues">
                        {m.cues.map((cue) => (
                          <li key={cue.code} data-status={cue.status}>
                            <span aria-hidden="true">{cue.status === "detected" ? "✓" : cue.status === "missing" ? "✗" : "•"}</span>
                            {cue.label}{cue.status === "counted" && cue.count !== null && cue.count !== undefined ? ` · ${cue.count}` : ""}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
              <p className="prompt-check__note">{result.other_metric_families_note}</p>
            </article>
            <article className="prompt-check__card">
              <h3>Context read from the prompt</h3>
              <dl className="prompt-check__context">
                <div><dt>Task type</dt><dd>{result.context.task_type}</dd></div>
                <div><dt>Language</dt><dd>{result.context.language}</dd></div>
                <div><dt>Size</dt><dd>{result.context.prompt_words} words · {result.context.sentence_count} sentences · {result.context.bullet_count} bullets</dd></div>
                <div><dt>References</dt><dd>{result.context.file_references} files · {result.context.code_identifiers} identifiers · {result.context.urls} links</dd></div>
                <div><dt>Relies on earlier turns</dt><dd>{result.context.depends_on_prior_context ? "yes" : "no"}{result.context.prior_context_supplied ? ` · ${result.context.prior_context_supplied} supplied` : " · none supplied"}</dd></div>
                <div><dt>Verification asked for</dt><dd>{result.context.verification_requested ? "yes" : "no"}</dd></div>
              </dl>
              {result.context.missing_elements.length > 0 && (
                <>
                  <h4>Consider adding</h4>
                  <ul className="prompt-check__missing">
                    {result.context.missing_elements.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </>
              )}
              <p className="prompt-check__summary"><strong>Summary for an agent:</strong> {result.summary}</p>
            </article>
          </div>

          <article className="prompt-check__card prompt-check__commentary" data-state={result.commentary.state}>
            <h3>What the local model would change <small>· model output, not a metric</small></h3>
            {result.commentary.state === "ok" ? (
              <>
                {result.commentary.findings.length > 0 && (
                  <ul className="prompt-check__findings">
                    {result.commentary.findings.map((f, index) => (
                      <li key={`${f.aspect}-${index}`} data-severity={f.severity}>
                        <span className="prompt-check__severity">{f.severity}</span>
                        <div><strong>{f.aspect}</strong> - {f.why}<br /><em>{f.suggestion}</em></div>
                      </li>
                    ))}
                  </ul>
                )}
                {result.commentary.reformulated_elements.length > 0 && (
                  <table className="prompt-check__elements">
                    <thead><tr><th scope="col">Element</th><th scope="col">You wrote</th><th scope="col">Suggested</th></tr></thead>
                    <tbody>
                      {result.commentary.reformulated_elements.map((e, index) => (
                        <tr key={`${e.element}-${index}`}><th scope="row">{e.element}</th><td>{e.original ?? "—"}</td><td>{e.suggested}</td></tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {result.commentary.reformulated_prompt && (
                  <div className="prompt-check__reformulated">
                    <div className="prompt-check__reformulated-head">
                      <h4>Reformulated prompt</h4>
                      <button
                        className="button button--ghost"
                        onClick={() => {
                          void navigator.clipboard?.writeText(result.commentary.reformulated_prompt ?? "").then(() => setCopied(true)).catch(() => setCopied(false));
                        }}
                        type="button"
                      >
                        {copied ? "Copied" : "Copy"}
                      </button>
                    </div>
                    <pre>{result.commentary.reformulated_prompt}</pre>
                  </div>
                )}
                {result.commentary.notes && <p className="prompt-check__note">{result.commentary.notes}</p>}
                <p className="prompt-check__caveat">{result.commentary.caveat} ({result.commentary.model_alias})</p>
              </>
            ) : result.commentary.state === "no_active_model" ? (
              <p className="prompt-check__note">No local model is active. Activate one on the <button className="link-button" onClick={() => navigate({ name: "models" })} type="button">Models page</button> to get commentary and a reformulation; the cues above are complete without it.</p>
            ) : result.commentary.state === "skipped" ? (
              <p className="prompt-check__note">Commentary was not requested.</p>
            ) : (
              <p className="prompt-check__note">The model did not answer usably this time ({result.commentary.state.replace(/_/g, " ")}); the cues above stand.</p>
            )}
          </article>
        </section>
      )}

      {stored && (
        <section className="prompt-check__result" aria-label="Stored check">
          <h2>Stored check</h2>
          <p className="prompt-check__note">
            {new Date(stored.created_at).toLocaleString()} · {stored.provider}{stored.agent_model ? ` · ${stored.agent_model}` : ""} · {stored.task_type} · {stored.prompt_chars} characters.
            Only metrics were kept - the prompt itself was never stored.
          </p>
          <PromptMetricRadar readings={stored.metrics.map((m) => ({ key: m.key, label: shortName(m.key), value: readingValue(m as Reading), higherIsBetter: m.higher_is_better }))} />
        </section>
      )}

      <section aria-labelledby="prompt-check-history-title" className="prompt-check__history">
        <h2 id="prompt-check-history-title">Your checks over time</h2>
        {historyState === "loading" && <p className="prompt-check__note">Loading…</p>}
        {historyState === "error" && <p className="prompt-check__note" role="alert">The history could not be read.</p>}
        {historyState === "ready" && history.length === 0 && <p className="prompt-check__note">No check yet. The first one appears here with its plots.</p>}
        {historyState === "ready" && history.length > 0 && (
          <>
            <PromptMetricTrend
              series={Object.keys(SHORT_NAMES).map((key) => ({
                key,
                label: shortName(key),
                points: trend.map((record, index) => {
                  const reading = record.metrics.find((m) => m.key === key);
                  return { x: index, value: reading ? readingValue(reading as Reading) : null, at: record.created_at };
                }),
              }))}
            />
            <div className="prompt-check__table-wrap">
              <table className="prompt-check__table">
                <thead>
                  <tr><th scope="col">When</th><th scope="col">Via</th><th scope="col">Task</th><th scope="col">Size</th>{Object.keys(SHORT_NAMES).map((key) => <th key={key} scope="col">{shortName(key)}</th>)}<th scope="col">Model</th></tr>
                </thead>
                <tbody>
                  {history.map((record) => (
                    <tr key={record.check_id}>
                      <td><button className="link-button" onClick={() => navigate({ name: "prompt_checks", checkId: record.check_id })} type="button">{new Date(record.created_at).toLocaleString()}</button></td>
                      <td>{record.provider}{record.agent_model ? ` · ${record.agent_model}` : ""}</td>
                      <td>{record.task_type}</td>
                      <td>{record.prompt_chars}</td>
                      {Object.keys(SHORT_NAMES).map((key) => {
                        const reading = record.metrics.find((m) => m.key === key);
                        const value = reading ? readingValue(reading as Reading) : null;
                        return <td key={key} data-state={reading?.state ?? "unknown"}>{value === null ? "—" : `${Math.round(value * 100)}%`}</td>;
                      })}
                      <td>{record.commentary_state === "ok" ? record.commentary_model_alias : record.commentary_state.replace(/_/g, " ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </section>
  );
}
