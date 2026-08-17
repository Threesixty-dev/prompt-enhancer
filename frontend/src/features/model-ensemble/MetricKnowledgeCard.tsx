import { useCallback, useEffect, useId, useRef, useState } from "react";
import { metricHelpV2 } from "./metricHelpV2";

/**
 * One knowledge-card controller per workspace. A target is {surface, metricKey};
 * at most one card is visible across every trigger surface (axis strip and
 * exact-value board). Triggers get `aria-describedby` pointing at an always
 * present hidden one-sentence description, so semantics never depend on the
 * visible card. The visible card is an in-flow disclosure below its trigger
 * surface: it never moves the radar and cannot overflow its container.
 */
export type MetricKnowledgeSurface = "strip" | "board";
export interface MetricKnowledgeTarget { surface: MetricKnowledgeSurface; metricKey: string }

export interface MetricKnowledgeCardController {
  idPrefix: string;
  target: MetricKnowledgeTarget | null;
  pinned: boolean;
  preview: (target: MetricKnowledgeTarget) => void;
  unpreview: (target: MetricKnowledgeTarget) => void;
  togglePin: (target: MetricKnowledgeTarget) => void;
  dismiss: () => void;
}

export const METRIC_KNOWLEDGE_CARD_LEAVE_DELAY_MS = 150;

const same = (left: MetricKnowledgeTarget | null, right: MetricKnowledgeTarget): boolean =>
  left !== null && left.surface === right.surface && left.metricKey === right.metricKey;

export function useMetricKnowledgeCardController(): MetricKnowledgeCardController {
  const idPrefix = useId();
  const [state, setState] = useState<{ target: MetricKnowledgeTarget | null; pinned: boolean }>({ target: null, pinned: false });
  const leaveTimer = useRef<number | null>(null);
  const clearLeave = () => {
    if (leaveTimer.current !== null) {
      window.clearTimeout(leaveTimer.current);
      leaveTimer.current = null;
    }
  };
  const preview = useCallback((target: MetricKnowledgeTarget) => {
    clearLeave();
    setState((current) => current.pinned ? current : { target, pinned: false });
  }, []);
  const unpreview = useCallback((target: MetricKnowledgeTarget) => {
    clearLeave();
    leaveTimer.current = window.setTimeout(() => {
      setState((current) => current.pinned || !same(current.target, target) ? current : { target: null, pinned: false });
    }, METRIC_KNOWLEDGE_CARD_LEAVE_DELAY_MS);
  }, []);
  const togglePin = useCallback((target: MetricKnowledgeTarget) => {
    clearLeave();
    setState((current) => current.pinned && same(current.target, target)
      ? { target: null, pinned: false }
      : { target, pinned: true });
  }, []);
  const dismiss = useCallback(() => {
    clearLeave();
    setState({ target: null, pinned: false });
  }, []);
  useEffect(() => {
    if (state.target === null) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismiss();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [dismiss, state.target]);
  useEffect(() => () => clearLeave(), []);
  return { idPrefix, target: state.target, pinned: state.pinned, preview, unpreview, togglePin, dismiss };
}

export function metricKnowledgeDescriptionId(controller: Pick<MetricKnowledgeCardController, "idPrefix">, metricKey: string): string {
  return `${controller.idPrefix}help-${metricKey.replaceAll(".", "-")}`;
}

/** Trigger props for the accessible controls (buttons/tiles) that describe a metric. */
export function metricKnowledgeCardTriggerProps(
  controller: MetricKnowledgeCardController,
  surface: MetricKnowledgeSurface,
  metricKey: string,
) {
  const target = { surface, metricKey };
  const open = same(controller.target, target);
  return {
    "aria-describedby": metricKnowledgeDescriptionId(controller, metricKey),
    "data-help-open": open ? (controller.pinned ? "pinned" : "preview") : undefined,
    onPointerEnter: () => controller.preview(target),
    onPointerLeave: () => controller.unpreview(target),
    onFocus: () => controller.preview(target),
    onBlur: () => controller.unpreview(target),
  } as const;
}

export interface MetricKnowledgeEntry { key: string; label: string; status: string }

/** Always-present hidden one-sentence descriptions referenced by every trigger. */
export function MetricKnowledgeDescriptions({ controller, entries }: {
  controller: MetricKnowledgeCardController;
  entries: readonly MetricKnowledgeEntry[];
}) {
  return (
    <div className="metric-knowledge-descriptions" hidden>
      {entries.map((entry) => (
        <span id={metricKnowledgeDescriptionId(controller, entry.key)} key={entry.key}>
          {entry.label}: {metricHelpV2(entry.key)?.entry.meaning ?? "No knowledge card is registered for this metric key."}
        </span>
      ))}
    </div>
  );
}

/** In-flow disclosure slot for one surface; renders the single open card, if it targets this surface. */
export function MetricKnowledgeCardSlot({ controller, surface, entries, compact = false }: {
  controller: MetricKnowledgeCardController;
  surface: MetricKnowledgeSurface;
  entries: readonly MetricKnowledgeEntry[];
  compact?: boolean;
}) {
  const target = controller.target;
  const entry = target !== null && target.surface === surface
    ? entries.find((candidate) => candidate.key === target.metricKey) ?? null
    : null;
  if (entry === null) return <div className="metric-knowledge-slot" data-surface={surface} />;
  const help = metricHelpV2(entry.key, "en");
  const pinned = controller.pinned;
  return (
    <div className="metric-knowledge-slot" data-surface={surface}>
      <div
        aria-label={`${entry.label} knowledge card`}
        className={`metric-knowledge-card${compact ? " metric-knowledge-card--compact" : ""}`}
        data-metric-key={entry.key}
        data-pinned={pinned ? "true" : "false"}
        onPointerEnter={() => controller.preview({ surface, metricKey: entry.key })}
        onPointerLeave={() => controller.unpreview({ surface, metricKey: entry.key })}
        role="tooltip"
      >
        <header>
          <strong>{entry.label}</strong>
          <span>{entry.status}</span>
        </header>
        {help === null ? (
          <p>No knowledge card is registered for this metric key.</p>
        ) : (
          <>
            <p><b>Target definition.</b> {help.entry.meaning}</p>
            <dl>
              <div><dt>Question</dt><dd>{help.entry.question}</dd></div>
              <div><dt>Unit</dt><dd>{help.entry.observationUnit}</dd></div>
              <div><dt>Direction</dt><dd>{help.entry.direction}</dd></div>
              <div><dt>Counts</dt><dd>{help.entry.counts}</dd></div>
              <div><dt>Does not count</dt><dd>{help.entry.doesNotCount}</dd></div>
              <div><dt>Evidence</dt><dd>{help.entry.objectiveEvidence}</dd></div>
            </dl>
            {help.measurement !== null && (
              <p className="metric-knowledge-card__measurement">
                <b>Current measurement (shipped definition v{help.measurement.definitionVersion}).</b> {help.measurement.method} {help.measurement.limitation}
              </p>
            )}
          </>
        )}
        <footer>{pinned ? "Pinned · Esc closes" : "Click or tap the control to pin · Esc closes"} · {help?.version ?? "unversioned"} · target contract shown separately from the shipped measurement</footer>
      </div>
    </div>
  );
}
