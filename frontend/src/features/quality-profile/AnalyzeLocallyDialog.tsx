import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { SessionQualityAnalysisRequest } from "../../shared/api/contracts";
import { nextIdempotencyKey } from "../../shared/api/idempotency";
import {
  COACHING_ANALYSIS_PRESET,
  COACHING_ANALYSIS_REQUEST,
} from "./standardEngineeringAnalysisPreset";

function statusOf(error: unknown): number | null {
  if (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    typeof error.status === "number"
  ) {
    return error.status;
  }
  return null;
}

function reasonCodeOf(error: unknown): string | null {
  if (
    typeof error === "object" &&
    error !== null &&
    "reasonCode" in error &&
    typeof error.reasonCode === "string"
  ) {
    return error.reasonCode;
  }
  return null;
}

function safeError(error: unknown): string {
  const reasonCode = reasonCodeOf(error);
  if (reasonCode === "redacted_content_consent_required") {
    return "Redacted-text access is not granted. Open Local sources, grant access, then retry.";
  }
  if (reasonCode === "session_not_in_safe_index") {
    return "This session is no longer in the bounded safe index. Refresh Local sources, then reopen the session.";
  }
  if (reasonCode === "analysis_idempotency_conflict") {
    return "This request conflicts with an earlier local run. Close this review, reopen it, and retry.";
  }
  if (
    reasonCode === "invalid_analysis_request" ||
    reasonCode === "confirmation_required"
  ) {
    return "The coaching analysis profile was rejected. Update and restart Prompt Enhancer, then retry.";
  }
  if (reasonCode === "source_schema_unsupported") {
    return "This Codex session uses a content schema this app version cannot safely read. Update Prompt Enhancer, restart it, and refresh the safe index.";
  }
  if (reasonCode === "selection_snapshot_miss") {
    return "The indexed session changed before the bounded read. Refresh the safe index, reopen this session, and retry.";
  }
  if (reasonCode === "source_resource_limit") {
    return "This session exceeds the coaching profile's fixed local safety limit. No partial score was created.";
  }
  if (reasonCode === "source_timeout") {
    return "The bounded local provider read timed out. Retry once; no provider content is included in this message.";
  }
  if (reasonCode === "provider_unavailable") {
    return "The Codex local provider is temporarily unavailable. Keep Codex running, then retry.";
  }
  if (reasonCode === "no_analyzable_text") {
    return "No analyzable prompt or response text was available in this bounded session. No metric score was created.";
  }
  if (reasonCode === "provider_protocol_rejected") {
    return "Installed schema compatibility passed, but Codex rejected this session read. Retry the analysis once. If it repeats, restart Codex and Prompt Enhancer; rechecking schema compatibility alone will not repair a live read failure.";
  }
  if (reasonCode === "provider_compatibility_blocked") {
    return "The installed-schema compatibility status changed after this review opened. Refresh that content-free status before trying this session again.";
  }
  if (reasonCode === "analysis_persistence_failed") {
    return "The content-free immutable result could not be stored. Check the local database and retry.";
  }
  if (reasonCode === "metric_execution_failed") {
    return "The local metric engine could not finish this run. Retry once or inspect the local application logs.";
  }
  const status = statusOf(error);
  if (status === 403) {
    return "This local analysis was not authorized. Review local-source access and try again.";
  }
  if (status === 404) {
    return "This session is no longer available in the safe local index.";
  }
  if (status === 409) {
    return "The selected session changed. Close this review, reopen it, and retry.";
  }
  if (status === 405) {
    return "Bounded text analysis is not available in this running app. Restart Prompt Enhancer after updating the local backend.";
  }
  if (status === 413 || status === 422) {
    return "The coaching analysis profile was rejected by the local service.";
  }
  if (status === 501) {
    return "New local analyses are disabled in the fictional preview. The canned immutable run remains available for inspection.";
  }
  if (status === 503) {
    return "The local analysis service is temporarily unavailable. Refresh the safe index and retry; no provider content is included in this message.";
  }
  if (status === null) {
    return "The browser lost the local analysis response. Refresh this page once and retry. If it repeats, the local app needs diagnostics; no transcript content is shown here.";
  }
  return "The bounded local analysis could not be completed. Refresh once and retry; no transcript content is shown in this error.";
}

export function AnalyzeLocallyDialog({
  onAnalyze,
  onCheckCompatibility,
  onClose,
  sessionDescriptor = "Selected session",
}: {
  onAnalyze: (
    request: SessionQualityAnalysisRequest,
    idempotencyKey: string,
    signal: AbortSignal,
  ) => Promise<void>;
  onCheckCompatibility?: (signal: AbortSignal) => Promise<void>;
  onClose: () => void;
  sessionDescriptor?: string;
}) {
  const [pendingAction, setPendingAction] = useState<
    "analysis" | "compatibility" | null
  >(null);
  const [error, setError] = useState("");
  const [failureReason, setFailureReason] = useState<string | null>(null);
  const primaryRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const requestControllerRef = useRef<AbortController | null>(null);
  const idempotencyKeyRef = useRef(nextIdempotencyKey("quality-analysis"));
  const onCloseRef = useRef(onClose);

  function close() {
    requestControllerRef.current?.abort();
    onCloseRef.current();
  }

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const appShell = document.querySelector<HTMLElement>(".app-shell");
    const wasInert = appShell?.inert ?? false;
    if (appShell) appShell.inert = true;
    primaryRef.current?.focus();

    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        close();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          "button:not([disabled]), [tabindex]:not([tabindex='-1'])",
        ),
      );
      const first = focusable[0];
      const last = focusable.at(-1);
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    window.addEventListener("keydown", keydown);
    return () => {
      window.removeEventListener("keydown", keydown);
      requestControllerRef.current?.abort();
      if (appShell) appShell.inert = wasInert;
      previous?.focus();
    };
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pendingAction !== null) return;
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setError("");
    setFailureReason(null);
    setPendingAction("analysis");
    cancelRef.current?.focus();
    try {
      await onAnalyze(
        COACHING_ANALYSIS_REQUEST,
        idempotencyKeyRef.current,
        controller.signal,
      );
      if (!controller.signal.aborted) onCloseRef.current();
    } catch (nextError) {
      if (!controller.signal.aborted) {
        setFailureReason(reasonCodeOf(nextError));
        setError(safeError(nextError));
      }
    } finally {
      if (!controller.signal.aborted) setPendingAction(null);
      requestControllerRef.current = null;
    }
  }

  async function recheckCompatibility() {
    if (!onCheckCompatibility || pendingAction !== null) return;
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setError("");
    setPendingAction("compatibility");
    cancelRef.current?.focus();
    try {
      await onCheckCompatibility(controller.signal);
      if (!controller.signal.aborted) onCloseRef.current();
    } catch {
      if (!controller.signal.aborted) {
        setError(
          "The content-free compatibility check could not be completed. Retry the check or close this review; no session content was included in this error.",
        );
      }
    } finally {
      if (!controller.signal.aborted) setPendingAction(null);
      requestControllerRef.current = null;
    }
  }

  const compatibilityBlocked = failureReason === "provider_compatibility_blocked";
  const pending = pendingAction !== null;
  const primaryLabel =
    pendingAction === "analysis"
      ? "Analyzing locally…"
      : pendingAction === "compatibility"
        ? "Rechecking compatibility…"
        : compatibilityBlocked
          ? onCheckCompatibility
            ? "Recheck compatibility"
            : "Close to compatibility status"
          : error
            ? "Retry analysis"
            : "Analyze this session";

  return createPortal(
    <div
      aria-describedby="analyze-locally-summary"
      aria-labelledby="analyze-locally-title"
      aria-modal="true"
      className="analysis-dialog"
      role="dialog"
    >
      <div className="analysis-dialog__scrim" />
      <section className="analysis-dialog__panel" ref={panelRef}>
        <header>
          <div>
            <p className="eyebrow">One session · local only</p>
            <h2 id="analyze-locally-title">Ready to analyze</h2>
            <p id="analyze-locally-summary">
              Review the fixed coaching profile, then start it—nothing to configure.
            </p>
          </div>
          <button
            aria-label="Close analysis review"
            className="share-dialog__close"
            disabled={pending}
            onClick={close}
            type="button"
          >
            Close
          </button>
        </header>

        <form onSubmit={(event) => void submit(event)}>
          <section className="analysis-dialog__preset" aria-labelledby="analysis-preset-title">
            <div className="analysis-dialog__preset-heading">
              <span aria-hidden="true">S1</span>
              <div>
                <strong id="analysis-preset-title">
                  {COACHING_ANALYSIS_PRESET.label} v{COACHING_ANALYSIS_PRESET.version}
                </strong>
                <small>Fixed scope; provenance is checked before comparison</small>
              </div>
            </div>
            <dl>
              <div>
                <dt>Session</dt>
                <dd>{sessionDescriptor}</dd>
              </div>
              <div>
                <dt>Coverage</dt>
                <dd>{COACHING_ANALYSIS_PRESET.metricAttempts} prompt, collaboration, logic, and outcome metric attempts</dd>
              </div>
              <div>
                <dt>Local limit</dt>
                <dd>
                  Up to {COACHING_ANALYSIS_PRESET.maxMessages} messages · {COACHING_ANALYSIS_PRESET.maxCharacters.toLocaleString("en")} redacted characters
                </dd>
              </div>
            </dl>
            <p>
              Missing evidence, unsupported capabilities, and unknown task-specific
              denominators stay Unknown or Abstained. They are never converted to zero.
            </p>
          </section>

          <div className="analysis-dialog__privacy" role="note">
            <strong>Private by default</strong>
            <span>
              The bounded provider read starts only when you press the analysis button.
              Processing stays local; the database stores content-free metrics and
              provenance, not prompts, responses, excerpts, paths, or tool output.
            </span>
          </div>

          {error && <p className="analysis-dialog__error" role="alert">{error}</p>}
          <p aria-live="polite" className="analysis-dialog__status" role="status">
            {pendingAction === "analysis"
              ? "Running the coaching profile locally…"
              : pendingAction === "compatibility"
                ? "Refreshing installed-schema compatibility without reading a session…"
                : compatibilityBlocked
                  ? "Session analysis is paused until the content-free compatibility status is refreshed."
                  : error
                    ? "The run did not complete. Review the message above before trying again."
                    : "Pressing Analyze is the explicit one-time confirmation for this session."}
          </p>
          <p className="analysis-dialog__cancel-note">
            Cancel stops this browser from waiting. A run already accepted locally may
            still finish and remain immutable.
          </p>
          <footer>
            <button
              className="button button--secondary"
              onClick={close}
              ref={cancelRef}
              type="button"
            >
              {pending ? "Cancel request" : "Cancel"}
            </button>
            <button
              className="button button--primary"
              disabled={pending}
              onClick={
                compatibilityBlocked
                  ? onCheckCompatibility
                    ? () => void recheckCompatibility()
                    : close
                  : undefined
              }
              ref={primaryRef}
              type={compatibilityBlocked ? "button" : "submit"}
            >
              {primaryLabel}
            </button>
          </footer>
        </form>
      </section>
    </div>,
    document.body,
  );
}
