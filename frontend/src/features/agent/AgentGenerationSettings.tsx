import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { AgentSettings } from "../../shared/api/contracts";

import "./AgentGenerationSettings.css";

export type AgentGenerationParameters = AgentSettings["parameters"];

export type AgentGenerationSettingsProps = {
  parameters: AgentGenerationParameters;
  contextLimit: number | null;
  modelProvided?: boolean;
  disabled?: boolean;
  busy?: boolean;
  saveReady?: boolean;
  onSave: (parameters: AgentGenerationParameters, expectedParameters: AgentGenerationParameters) => Promise<boolean | void>;
  onReload?: () => Promise<AgentGenerationParameters | null>;
  retentionNote?: string;
};

function isConflictError(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const code = "reasonCode" in value ? value.reasonCode : "error_code" in value ? value.error_code : "code" in value ? value.code : undefined;
  return code === "agent_session_parameters_conflict" || code === "agent_catalog_session_revision_conflict" || code === "revision_conflict" || code === "stale_revision";
}

function sameParameters(a: AgentGenerationParameters, b: AgentGenerationParameters): boolean {
  return a.temperature === b.temperature
    && a.top_p === b.top_p
    && a.max_tokens === b.max_tokens
    && a.enable_thinking === b.enable_thinking;
}

export function AgentGenerationSettings({ parameters, contextLimit, modelProvided = false, disabled = false, busy = false, saveReady = true, onSave, onReload, retentionNote }: AgentGenerationSettingsProps) {
  const [draft, setDraft] = useState(parameters);
  const [maxTokensText, setMaxTokensText] = useState(String(parameters.max_tokens));
  const [saving, setSaving] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState("");
  const [externalChange, setExternalChange] = useState(false);
  const [needsReload, setNeedsReload] = useState(false);
  const saveHelpId = useId();
  const cancelHelpId = useId();
  const baseParameters = useRef(parameters);
  const observedParameters = useRef(parameters);
  const draftRef = useRef(draft);
  const maxTokensTextRef = useRef(maxTokensText);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  draftRef.current = draft;
  maxTokensTextRef.current = maxTokensText;

  useEffect(() => {
    if (sameParameters(parameters, observedParameters.current)) return;
    observedParameters.current = parameters;
    if (!sameParameters(draftRef.current, baseParameters.current) || maxTokensTextRef.current !== String(baseParameters.current.max_tokens)) {
      setExternalChange(true);
      return;
    }
    setDraft(parameters);
    setMaxTokensText(String(parameters.max_tokens));
    baseParameters.current = parameters;
    setExternalChange(false);
    setError("");
  }, [parameters]);

  const dirty = !sameParameters(draft, baseParameters.current) || maxTokensText !== String(baseParameters.current.max_tokens);
  const parsedMaxTokens = /^\d+$/u.test(maxTokensText) ? Number(maxTokensText) : NaN;
  const budgetError = !/^\d+$/u.test(maxTokensText) || !Number.isSafeInteger(parsedMaxTokens) || parsedMaxTokens < 64 || parsedMaxTokens > 8192
    ? "Max output tokens must be an integer from 64 to 8,192."
    : contextLimit !== null && parsedMaxTokens >= contextLimit
      ? `Max output (${parsedMaxTokens.toLocaleString()}) must be below the ${contextLimit.toLocaleString()}-token context limit. Input and tools also consume context.`
      : "";
  const saveDisabled = disabled || busy || !saveReady || saving || reloading || !dirty || Boolean(budgetError) || externalChange || needsReload;
  const saveDisabledReason = disabled || busy
    ? "Save is unavailable while the session or runtime is busy."
    : !saveReady
      ? "Save is unavailable until the current generation settings load."
    : saving || reloading
      ? "Save is unavailable while settings are being updated."
      : externalChange || needsReload
        ? "Reload current settings before saving."
        : budgetError
          ? budgetError
          : "There are no unsaved generation changes.";
  const cancelDisabled = !dirty || saving || reloading;
  const cancelDisabledReason = saving || reloading
    ? "Cancel is unavailable while settings are being updated."
    : "There are no unsaved generation changes to discard.";
  const status = useMemo(() => contextLimit === null
    ? "Exact context capacity is unknown; Save does not claim a guaranteed fit."
    : "Output capacity is a candidate budget, not a guarantee: input and tools consume context.", [contextLimit]);

  async function save(): Promise<void> {
    if (saveDisabled || Boolean(budgetError) || externalChange) return;
    setSaving(true);
    setError("");
    try {
      const saved = { ...draft, max_tokens: parsedMaxTokens };
      if (await onSave(saved, baseParameters.current) === false) return;
      if (!mounted.current) return;
      setDraft(saved);
      setMaxTokensText(String(saved.max_tokens));
      baseParameters.current = saved;
      observedParameters.current = saved;
      setExternalChange(false);
      setNeedsReload(false);
    } catch (caught) {
      if (mounted.current) {
        const conflict = isConflictError(caught);
        if (conflict) setNeedsReload(true);
        setError(conflict
          ? "These settings changed elsewhere. Reload the current settings or cancel your edits before trying again."
          : "Generation settings could not be saved. Your edits remain here.");
      }
    } finally {
      if (mounted.current) setSaving(false);
    }
  }

  function cancel(): void {
    if (saving || reloading) return;
    setDraft(parameters);
    setMaxTokensText(String(parameters.max_tokens));
    baseParameters.current = parameters;
    observedParameters.current = parameters;
    setError("");
    setExternalChange(false);
    setNeedsReload(false);
  }

  async function reload(): Promise<void> {
    if (saving || reloading || onReload === undefined) return;
    setReloading(true);
    setError("");
    try {
      const refreshed = await onReload();
      if (!mounted.current || refreshed === null) return;
      setDraft(refreshed);
      setMaxTokensText(String(refreshed.max_tokens));
      baseParameters.current = refreshed;
      observedParameters.current = refreshed;
      setExternalChange(false);
      setNeedsReload(false);
      setError("");
    } catch {
      if (mounted.current) setError("Current generation settings could not be reloaded. Your edits remain here.");
    } finally {
      if (mounted.current) setReloading(false);
    }
  }

  return (
    <details className="agent-generation-settings__disclosure">
      <summary>Generation settings</summary>
    <fieldset aria-describedby="agent-generation-settings-note" className="agent-generation-settings" disabled={disabled || busy || saving || reloading} onKeyDown={(event) => {
      if (event.key === "Enter" && !(event.target instanceof HTMLButtonElement)) {
        event.preventDefault();
        event.stopPropagation();
      }
    }}>
      <legend className="sr-only">Generation settings</legend>
      <p className="agent-generation-settings__note" id="agent-generation-settings-note">{status}</p>
      {retentionNote && <p className="agent-generation-settings__note">{retentionNote}</p>}
      <label>
        <span>Temperature · {draft.temperature.toFixed(2)}</span>
        <input aria-label="Generation temperature" max={2} min={0} onChange={(event) => setDraft((value) => ({ ...value, temperature: Number(event.currentTarget.value) }))} step={0.05} type="range" value={draft.temperature} />
      </label>
      <label>
        <span>Top-p · {draft.top_p.toFixed(2)}</span>
        <input aria-label="Generation top-p" max={1} min={0.05} onChange={(event) => setDraft((value) => ({ ...value, top_p: Number(event.currentTarget.value) }))} step={0.05} type="range" value={draft.top_p} />
      </label>
      <label>
        <span>Max output tokens</span>
        <input aria-label="Generation max tokens" aria-invalid={Boolean(budgetError)} inputMode="numeric" onChange={(event) => setMaxTokensText(event.currentTarget.value)} type="text" value={maxTokensText} />
      </label>
      <label className="agent-generation-settings__toggle">
        <input aria-label="Generation thinking" checked={draft.enable_thinking} onChange={(event) => setDraft((value) => ({ ...value, enable_thinking: event.currentTarget.checked }))} type="checkbox" />
        <span>{modelProvided ? "Enable thinking for this model" : "Request model-provided reasoning (when supported)"}</span>
      </label>
      <p className="agent-generation-settings__note">Thinking is template/model dependent and does not guarantee reasoning.</p>
      {externalChange && <p className="agent-generation-settings__error" role="alert">Current settings changed elsewhere. Reload or Cancel before saving.</p>}
      {budgetError && <p className="agent-generation-settings__error" role="alert">{budgetError}</p>}
      {error && <p className="agent-generation-settings__error" role="alert">{error}</p>}
      <div className="agent-generation-settings__actions">
        <span className="sr-only" id={saveHelpId}>{saveDisabledReason}</span>
        <span className="sr-only" id={cancelHelpId}>{cancelDisabledReason}</span>
        <button aria-describedby={saveHelpId} className="button button--primary" disabled={saveDisabled} onClick={() => void save()} type="button">{saving ? "Saving…" : reloading ? "Reloading…" : "Save generation settings"}</button>
        {onReload !== undefined && <button className="button button--ghost" disabled={disabled || busy || saving || reloading} onClick={() => void reload()} type="button">{reloading ? "Reloading…" : "Reload current settings"}</button>}
        <button aria-describedby={cancelHelpId} className="button button--ghost" disabled={cancelDisabled} onClick={cancel} type="button">Cancel</button>
      </div>
    </fieldset>
    </details>
  );
}
