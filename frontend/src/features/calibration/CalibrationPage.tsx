import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  CalibrationProgress,
  CalibrationRating,
  CalibrationSample,
  CalibrationSampleMember,
  JudgeAgreementReport,
  JudgeSweepStatus,
  PromptEnhancerTransport,
  RatingLabel,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { Icon } from "../../shared/ui/Icon";
import { ProviderBadge } from "../../shared/ui/ProviderBadge";
import { SessionTranscriptPane } from "../session-reader/SessionTranscriptPane";
import "./CalibrationPage.css";

const RATER_KEY = "prompt-enhancer.calibration.rater";
const LABELS: readonly { value: RatingLabel; title: string; hint: string }[] = [
  { value: "low", title: "Low", hint: "Clearly weak" },
  { value: "medium", title: "Medium", hint: "Mixed or partial" },
  { value: "high", title: "High", hint: "Clearly strong" },
  { value: "cannot_judge", title: "Can't judge", hint: "Not enough to tell" },
];

const METRIC_COPY: Record<string, { title: string; question: string }> = {
  "prompt.task_definition_coverage": {
    title: "Task definition",
    question: "Did the person say clearly what they wanted done - scope, deliverable, done-when?",
  },
  "prompt.context_sufficiency": {
    title: "Context given",
    question: "Did the prompts carry the context the agent needed (files, constraints, prior decisions) instead of leaving it to guess?",
  },
  "outcome.verification_strategy_adequacy": {
    title: "Verification strategy",
    question: "Was the work checked in a way that fits the change - tests, builds, inspection - before it was called done?",
  },
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function safeCalibrationSample(value: unknown): value is CalibrationSample {
  if (!isRecord(value) || value.contract_version !== "calibration-ratings.v1") return false;
  if (typeof value.sample_id !== "string" || !Array.isArray(value.members) || !Array.isArray(value.metric_keys)) return false;
  return value.members.every((member) =>
    isRecord(member)
    && typeof member.session_id === "string" && /^[a-f0-9]{64}$/.test(member.session_id)
    && typeof member.provider === "string"
    && Array.isArray(member.rated_metric_keys),
  );
}

function memberTitle(member: CalibrationSampleMember): string {
  return member.session_display_name?.trim() || `Session ${member.session_id.slice(0, 8)}`;
}

function memberSubtitle(member: CalibrationSampleMember): string {
  const project = member.project_display_name?.trim() || `Project ${member.project_id.slice(0, 8)}`;
  const when = member.started_at ? new Date(member.started_at).toLocaleString() : "";
  return when ? `${project} · ${when}` : project;
}

/**
 * Blind ratings over a frozen sample of your own sessions. The page never
 * shows model values for the session being rated; ratings are stored locally
 * under a rater pseudonym and export as labels only.
 */
export function CalibrationPage({
  transport,
}: {
  transport: Pick<
    PromptEnhancerTransport,
    "getCalibrationSample" | "submitCalibrationRatings" | "getCalibrationRatings" | "getCalibrationProgress" | "getCalibrationExport" | "getSessionTranscript"
  > & Partial<Pick<PromptEnhancerTransport, "judgeSessionWithModel" | "startModelJudgeSweep" | "getModelJudgeSweep" | "getModelJudgeAgreement">>;
}) {
  const [agreement, setAgreement] = useState<JudgeAgreementReport | null>(null);
  const [sweep, setSweep] = useState<JudgeSweepStatus | null>(null);
  const [judgeMessage, setJudgeMessage] = useState("");
  const [rater, setRater] = useState<string>(() => {
    try { return localStorage.getItem(RATER_KEY) ?? ""; } catch { return ""; }
  });
  const [draftRater, setDraftRater] = useState(rater);
  const [sample, setSample] = useState<CalibrationSample | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "empty" | "unavailable" | "error">("idle");
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, RatingLabel>>({});
  const [existing, setExisting] = useState<CalibrationRating[]>([]);
  const [progress, setProgress] = useState<CalibrationProgress | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [exportText, setExportText] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    // Keep the list on screen while a rater change refreshes the rated marks.
    setState((previous) => (previous === "ready" ? previous : "loading"));
    try {
      const value = await transport.getCalibrationSample(rater || null, signal);
      if (signal?.aborted) return;
      if (!safeCalibrationSample(value)) { setState("error"); return; }
      setSample(value);
      setState(value.members.length === 0 ? "empty" : "ready");
      const [ratings, current] = await Promise.all([
        rater ? transport.getCalibrationRatings(rater, signal) : Promise.resolve([] as CalibrationRating[]),
        transport.getCalibrationProgress(signal),
      ]);
      if (signal?.aborted) return;
      setExisting(Array.isArray(ratings) ? ratings : []);
      setProgress(current);
    } catch (caught) {
      if (signal?.aborted) return;
      if (caught instanceof TransportError && caught.status === 409) { setState("empty"); return; }
      if (caught instanceof TransportError && caught.status === 404) { setState("unavailable"); return; }
      setState("error");
    }
  }, [rater, transport]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const loadJudge = useCallback(async (signal?: AbortSignal) => {
    if (!transport.getModelJudgeAgreement || !transport.getModelJudgeSweep) return;
    try {
      const [report, status] = await Promise.all([transport.getModelJudgeAgreement(signal), transport.getModelJudgeSweep(signal)]);
      if (signal?.aborted) return;
      setAgreement(report);
      setSweep(status);
    } catch {
      /* judge lane absent in this runtime */
    }
  }, [transport]);

  useEffect(() => {
    const controller = new AbortController();
    void loadJudge(controller.signal);
    const handle = window.setInterval(() => void loadJudge(controller.signal), 15000);
    return () => { controller.abort(); window.clearInterval(handle); };
  }, [loadJudge]);

  async function judgeCurrent() {
    if (!current || !transport.judgeSessionWithModel) return;
    setJudgeMessage("");
    try {
      const outcome = await transport.judgeSessionWithModel(current.session_id);
      setJudgeMessage(outcome.raw_valid ? `Model judged this session (${outcome.model_alias}); your own rating stays blind to it.` : "The model did not answer in the required format.");
      await loadJudge();
    } catch (caught) {
      setJudgeMessage(caught instanceof TransportError && caught.message.includes("no_active_model") ? "No local model is active - activate one on the Models page." : "The model judge is not available right now.");
    }
  }

  async function judgeSample() {
    if (!transport.startModelJudgeSweep) return;
    setJudgeMessage("");
    try {
      const status = await transport.startModelJudgeSweep();
      setSweep(status);
      setJudgeMessage(status.total === 0 ? "Every sampled session is already judged by this model." : `Judging ${status.total} sessions in the background.`);
    } catch (caught) {
      setJudgeMessage(caught instanceof TransportError && caught.message.includes("no_active_model") ? "No local model is active - activate one on the Models page." : "The model judge is not available right now.");
    }
  }

  const members = sample?.members ?? [];
  const metricKeys = sample?.metric_keys ?? [];
  const current = useMemo(() => members.find((member) => member.session_id === selected) ?? null, [members, selected]);
  const nextUnrated = useMemo(
    () => members.find((member) => member.rated_metric_keys.length < metricKeys.length) ?? null,
    [members, metricKeys.length],
  );

  useEffect(() => {
    if (!current) { setDraft({}); return; }
    const mine: Record<string, RatingLabel> = {};
    for (const rating of existing) {
      if (rating.session_id === current.session_id) mine[rating.metric_key] = rating.label;
    }
    setDraft(mine);
    setMessage("");
  }, [current, existing]);

  function commitRater() {
    const value = draftRater.trim();
    try { localStorage.setItem(RATER_KEY, value); } catch { /* ignore */ }
    setRater(value);
  }

  async function save(advance: boolean) {
    if (!current || !rater || Object.keys(draft).length === 0) return;
    setSaving(true);
    setMessage("");
    try {
      const result = await transport.submitCalibrationRatings({ rater_label: rater, session_id: current.session_id, ratings: draft });
      setProgress(result);
      const refreshed = await transport.getCalibrationSample(rater);
      if (safeCalibrationSample(refreshed)) setSample(refreshed);
      setExisting(await transport.getCalibrationRatings(rater));
      setMessage("Saved.");
      if (advance) {
        const after = (refreshed && safeCalibrationSample(refreshed) ? refreshed.members : members)
          .find((member) => member.session_id !== current.session_id && member.rated_metric_keys.length < metricKeys.length);
        setSelected(after ? after.session_id : null);
      }
    } catch {
      setMessage("Could not save. Nothing was changed.");
    } finally {
      setSaving(false);
    }
  }

  async function exportRatings() {
    try {
      const value = await transport.getCalibrationExport();
      setExportText(JSON.stringify(value, null, 2));
    } catch {
      setExportText("");
      setMessage("Export is unavailable right now.");
    }
  }

  const ratedCount = members.filter((member) => member.rated_metric_keys.length >= metricKeys.length && metricKeys.length > 0).length;

  return (
    <section aria-labelledby="calibration-title" className="calibration">
      <header className="calibration__head">
        <div>
          <p className="eyebrow">Calibration · your own sessions, rated blind</p>
          <h1 id="calibration-title">Rate sessions</h1>
          <p className="calibration__lede">
            Read the session, answer three questions, move on. Model values are hidden here on purpose; your
            answers are the human reference the metrics are later checked against. Everything stays on this
            machine - the export is labels and pseudonyms only.
          </p>
        </div>
        <div className="calibration__rater">
          <label>
            <span>Rater name (kept local; stored as a pseudonym)</span>
            <input
              aria-label="Rater name"
              onBlur={commitRater}
              onChange={(event) => setDraftRater(event.currentTarget.value)}
              onKeyDown={(event) => { if (event.key === "Enter") commitRater(); }}
              placeholder="for example Alex"
              type="text"
              value={draftRater}
            />
          </label>
          {progress && (
            <p className="calibration__progress" aria-live="polite">
              {ratedCount} of {members.length} sessions fully rated · {progress.rater_count} rater{progress.rater_count === 1 ? "" : "s"}
            </p>
          )}
        </div>
      </header>

      {state === "loading" && <p className="calibration__note">Drawing the sample…</p>}
      {state === "empty" && (
        <p className="calibration__note">No sessions are indexed yet. Load your projects first (Discovery → first run), then come back.</p>
      )}
      {state === "unavailable" && <p className="calibration__note">Calibration is not available in this runtime.</p>}
      {state === "error" && <p className="calibration__note" role="alert">The sample could not be verified.</p>}

      {state === "ready" && (
        <div className="calibration__body">
          <aside className="calibration__list" aria-label="Calibration sample">
            <div className="calibration__list-head">
              <span>{members.length} sessions · frozen sample</span>
              {nextUnrated && (
                <button className="button button--ghost" onClick={() => setSelected(nextUnrated.session_id)} type="button">
                  Next unrated
                </button>
              )}
            </div>
            <ol>
              {members.map((member) => {
                const done = metricKeys.length > 0 && member.rated_metric_keys.length >= metricKeys.length;
                const partial = !done && member.rated_metric_keys.length > 0;
                return (
                  <li key={member.session_id}>
                    <button
                      aria-current={member.session_id === selected ? "true" : undefined}
                      className={member.session_id === selected ? "is-selected" : ""}
                      data-state={done ? "done" : partial ? "partial" : "todo"}
                      onClick={() => setSelected(member.session_id)}
                      type="button"
                    >
                      <span className="calibration__item-title">{memberTitle(member)}</span>
                      <span className="calibration__item-sub">
                        <ProviderBadge provider={member.provider} />
                        {memberSubtitle(member)}
                      </span>
                      <span className="calibration__item-state">
                        {done ? <Icon name="check" /> : partial ? `${member.rated_metric_keys.length}/${metricKeys.length}` : ""}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </aside>

          <div className="calibration__main">
            {!current && (
              <p className="calibration__note">Pick a session on the left{nextUnrated ? " or use “Next unrated”" : ""}.</p>
            )}
            {current && (
              <>
                <h2 className="calibration__session-title">{memberTitle(current)}</h2>
                <SessionTranscriptPane autoLoad sessionId={current.session_id} transport={transport} />
                <form
                  className="calibration__form"
                  onSubmit={(event) => { event.preventDefault(); void save(true); }}
                >
                  {!rater && (
                    <p className="calibration__note" role="alert">Enter a rater name above before saving; it is stored only as a pseudonym.</p>
                  )}
                  {metricKeys.map((metricKey) => {
                    const copy = METRIC_COPY[metricKey] ?? { title: metricKey, question: metricKey };
                    return (
                      <fieldset key={metricKey} className="calibration__metric">
                        <legend>
                          <strong>{copy.title}</strong>
                          <span>{copy.question}</span>
                        </legend>
                        <div className="calibration__choices" role="radiogroup" aria-label={copy.title}>
                          {LABELS.map((label) => (
                            <label key={label.value} className={draft[metricKey] === label.value ? "is-chosen" : ""}>
                              <input
                                checked={draft[metricKey] === label.value}
                                name={metricKey}
                                onChange={() => setDraft((previous) => ({ ...previous, [metricKey]: label.value }))}
                                type="radio"
                                value={label.value}
                              />
                              <span>{label.title}</span>
                              <small>{label.hint}</small>
                            </label>
                          ))}
                        </div>
                      </fieldset>
                    );
                  })}
                  <div className="calibration__actions">
                    <button className="button button--primary" disabled={saving || !rater || Object.keys(draft).length === 0} type="submit">
                      {saving ? "Saving…" : "Save and next"}
                    </button>
                    <button className="button button--ghost" disabled={saving || !rater || Object.keys(draft).length === 0} onClick={() => void save(false)} type="button">
                      Save
                    </button>
                    {message && <span className="calibration__message" aria-live="polite">{message}</span>}
                  </div>
                </form>
              </>
            )}
          </div>
        </div>
      )}

      {state === "ready" && agreement && (
        <section aria-labelledby="model-judge-title" className="calibration__judge">
          <div className="calibration__judge-head">
            <div>
              <p className="eyebrow">Model judge · experimental, never a product metric</p>
              <h2 id="model-judge-title">How often does the local model agree with you?</h2>
              <p className="calibration__note">
                {agreement.model_alias ? `Active model: ${agreement.model_alias} · ${agreement.judged_sessions} session${agreement.judged_sessions === 1 ? "" : "s"} judged.` : "No local model is active. Activate one on the Models page to compare."}
                {sweep?.running ? ` Sweep running: ${sweep.done}/${sweep.total}${sweep.failed ? ` (${sweep.failed} failed)` : ""}.` : ""}
              </p>
            </div>
            <div className="calibration__actions">
              <button className="button button--ghost" disabled={!current || !agreement.model_alias} onClick={() => void judgeCurrent()} type="button">Judge this session</button>
              <button className="button button--ghost" disabled={!agreement.model_alias || Boolean(sweep?.running)} onClick={() => void judgeSample()} type="button">Judge the whole sample</button>
            </div>
          </div>
          <table className="calibration__agreement">
            <thead><tr><th>Metric</th><th>Pairs</th><th>Agreement</th><th>Cohen's κ</th><th>State</th></tr></thead>
            <tbody>
              {agreement.metrics.map((m) => (
                <tr key={m.metric_key}>
                  <td>{METRIC_COPY[m.metric_key]?.title ?? m.metric_key}</td>
                  <td>{m.pairs}</td>
                  <td>{m.agreement_rate === null || m.agreement_rate === undefined ? "—" : `${Math.round(m.agreement_rate * 100)}%`}</td>
                  <td>{m.cohen_kappa === null || m.cohen_kappa === undefined ? "—" : m.cohen_kappa.toFixed(2)}</td>
                  <td>{m.state.replace(/_/g, " ")}{m.reason ? ` · ${m.reason.replace(/_/g, " ")}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="calibration__note">{agreement.caveat}</p>
          {judgeMessage && <p className="calibration__message" aria-live="polite">{judgeMessage}</p>}
        </section>
      )}

      {state === "ready" && (
        <footer className="calibration__export">
          <button className="button button--ghost" onClick={() => void exportRatings()} type="button">
            Show export (labels and pseudonyms only)
          </button>
          {exportText && (
            <textarea aria-label="Calibration export" readOnly rows={8} value={exportText} />
          )}
        </footer>
      )}
    </section>
  );
}
