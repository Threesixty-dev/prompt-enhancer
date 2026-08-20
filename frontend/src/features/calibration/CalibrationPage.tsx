import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  CalibrationProgress,
  CalibrationRating,
  CalibrationSample,
  CalibrationSampleMember,
  AnnotationAllowance,
  JudgeAgreementReport,
  RemoteAnnotationResult,
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
  > & Partial<Pick<PromptEnhancerTransport, "judgeSessionWithModel" | "startModelJudgeSweep" | "getModelJudgeSweep" | "getModelJudgeAgreement" | "getAnnotationAllowance" | "setAnnotationAllowance" | "getAnnotationMetaprompt" | "annotateRemotely">>;
}) {
  const [agreement, setAgreement] = useState<JudgeAgreementReport | null>(null);
  const [sweep, setSweep] = useState<JudgeSweepStatus | null>(null);
  const [judgeMessage, setJudgeMessage] = useState("");
  const [allowance, setAllowance] = useState<AnnotationAllowance | null>(null);
  const [annotationMessage, setAnnotationMessage] = useState("");
  const [remoteConfirm, setRemoteConfirm] = useState(false);
  const [remoteBusy, setRemoteBusy] = useState(false);
  const [remoteResult, setRemoteResult] = useState<RemoteAnnotationResult | null>(null);
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
      if (transport.getAnnotationAllowance) {
        try {
          setAllowance(await transport.getAnnotationAllowance(signal));
        } catch {
          setAllowance(null);
        }
      }
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

  async function judgeSample(scope: "sample" | "all" = "sample") {
    if (!transport.startModelJudgeSweep) return;
    setJudgeMessage("");
    try {
      const status = await transport.startModelJudgeSweep(undefined, scope);
      setSweep(status);
      setJudgeMessage(status.total === 0 ? (scope === "all" ? "Every indexed session is already judged by this model." : "Every sampled session is already judged by this model.") : `Judging ${status.total} sessions in the background.`);
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

  const toggleAllowance = async () => {
    if (!transport.setAnnotationAllowance || !allowance) return;
    try {
      setAllowance(await transport.setAnnotationAllowance(!allowance.agent_allowed));
      setAnnotationMessage("");
    } catch (error) {
      setAnnotationMessage(error instanceof Error ? error.message : "Could not update the allowance.");
    }
  };

  const copyAgentInstructions = async () => {
    if (!transport.getAnnotationMetaprompt) return;
    try {
      const meta = await transport.getAnnotationMetaprompt();
      const base = window.location.origin;
      const text = [
        "Annotate my coding-agent sessions through the Prompt Enhancer API.",
        `Base URL: ${base} - send the app token from api.token (in the Prompt Enhancer home folder) as the X-Prompt-Enhancer-Token header on every request.`,
        "",
        "1. GET /v1/annotation/metaprompt - read the system prompt, the questions and the allowed labels.",
        "2. GET /v1/annotation/work?model=<your-model-name> - session ids you have not annotated yet.",
        "3. For each id: GET /v1/annotation/work/{session_id} - the redacted transcript window plus its window_fingerprint.",
        "4. Judge only what the window shows, then POST /v1/annotation/annotations with",
        '   {"session_id": "<id>", "model_name": "<your-model-name>", "window_fingerprint": "<the fingerprint from step 3>", "labels": {"<metric_key>": "<label>"}}.',
        "   Echo the fingerprint unchanged; if the session has grown since you read it the submission is refused, so re-read the window and judge it again.",
        "",
        `System prompt to follow:\n${meta.system_prompt}`,
        "",
        "Questions:",
        ...Object.entries(meta.questions).map(([key, question]) => `- ${key}: ${question}`),
        "",
        `Allowed labels: ${meta.labels.join(", ")}. ${meta.reply_format}`,
      ].join("\n");
      await navigator.clipboard.writeText(text);
      setAnnotationMessage("Agent instructions copied - paste them into Codex, Claude Code, or any agent you drive.");
    } catch (error) {
      setAnnotationMessage(error instanceof Error ? error.message : "Could not copy the instructions.");
    }
  };

  const annotateRemotely = async () => {
    if (!transport.annotateRemotely) return;
    setRemoteBusy(true);
    setAnnotationMessage("");
    try {
      const result = await transport.annotateRemotely(5);
      setRemoteResult(result);
      setRemoteConfirm(false);
      setAnnotationMessage(
        result.submitted === 0
          ? "Nothing left to submit - every session already has a central annotation."
          : `Sent ${result.submitted} session${result.submitted === 1 ? "" : "s"} to ${result.destination}; ${result.annotated} annotated by ${result.model_identity ?? "the central model"}.`,
      );
      void loadJudge();
    } catch (error) {
      setAnnotationMessage(error instanceof Error ? error.message : "Remote annotation failed.");
    } finally {
      setRemoteBusy(false);
    }
  };

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
              <button className="button button--ghost" disabled={!agreement.model_alias || Boolean(sweep?.running)} onClick={() => void judgeSample("all")} type="button">Judge every session</button>
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

      {state === "ready" && allowance && (
        <section aria-labelledby="annotation-paths-title" className="calibration__judge calibration__annotation">
          <div className="calibration__judge-head">
            <div>
              <p className="eyebrow">More ways to annotate</p>
              <h2 id="annotation-paths-title">Let a model you drive - or the central server - annotate for you</h2>
            </div>
          </div>
          <div className="calibration__annotation-paths">
            <div className="calibration__annotation-path">
              <h3>Your own agents, through this app&apos;s endpoint</h3>
              <p className="calibration__note">{allowance.note}</p>
              <div className="calibration__actions">
                <button className={allowance.agent_allowed ? "button" : "button button--ghost"} onClick={() => void toggleAllowance()} type="button">
                  {allowance.agent_allowed ? "Agent annotation is ON - click to stop" : "Allow agent annotation"}
                </button>
                {allowance.agent_allowed && (
                  <button className="button button--ghost" onClick={() => void copyAgentInstructions()} type="button">
                    Copy agent instructions
                  </button>
                )}
              </div>
              {allowance.agent_allowed && (
                <p className="calibration__note">
                  Paste the instructions into Codex, Claude Code, or a local model chat. Labels come back as <code>agent:&lt;name&gt;</code> judgments in the table above.
                </p>
              )}
            </div>
            <div className="calibration__annotation-path">
              <h3>Annotate remotely on the central server</h3>
              <p className="calibration__note">
                Sends up to 5 not-yet-submitted sessions - redacted windows plus pseudonymous session and project ids, never raw transcripts - to the central annotation server, which annotates them with its strongest model and keeps the submissions as the training dataset.
              </p>
              {!remoteConfirm ? (
                <div className="calibration__actions">
                  <button className="button button--ghost" disabled={remoteBusy} onClick={() => setRemoteConfirm(true)} type="button">
                    Annotate remotely…
                  </button>
                </div>
              ) : (
                <div className="calibration__actions" role="alertdialog" aria-label="Confirm remote annotation">
                  <span className="calibration__note">Destination: embedded central server (this machine). Send now?</span>
                  <button className="button" disabled={remoteBusy} onClick={() => void annotateRemotely()} type="button">
                    {remoteBusy ? "Sending…" : "Send"}
                  </button>
                  <button className="button button--ghost" disabled={remoteBusy} onClick={() => setRemoteConfirm(false)} type="button">
                    Cancel
                  </button>
                </div>
              )}
              {remoteResult && remoteResult.stored_locally_as && (
                <p className="calibration__note">Central labels stored locally as <code>{remoteResult.stored_locally_as}</code>.</p>
              )}
            </div>
          </div>
          {annotationMessage && <p className="calibration__message" aria-live="polite">{annotationMessage}</p>}
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
