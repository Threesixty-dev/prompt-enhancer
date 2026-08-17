import { useCallback, useEffect, useRef, useState } from "react";
import { metricHelpV2, type MetricHelpLocale } from "./metricHelpV2";

/**
 * Shared open/pin state for the metric knowledge cards of one workspace. Pointer
 * hover previews, keyboard focus previews, click/tap pins, Escape dismisses.
 * Only one card is open at a time; the card content is hoverable and never
 * changes layout because it is absolutely positioned and always rendered
 * (hidden) so `aria-describedby` resolves for every trigger.
 */
export interface MetricKnowledgeCardController {
  openKey: string | null;
  pinned: boolean;
  preview: (key: string) => void;
  unpreview: (key: string) => void;
  togglePin: (key: string) => void;
  dismiss: () => void;
}

export const METRIC_KNOWLEDGE_CARD_LEAVE_DELAY_MS = 150;

export function useMetricKnowledgeCardController(): MetricKnowledgeCardController {
  const [state, setState] = useState<{ openKey: string | null; pinned: boolean }>({ openKey: null, pinned: false });
  const leaveTimer = useRef<number | null>(null);
  const clearLeave = () => {
    if (leaveTimer.current !== null) {
      window.clearTimeout(leaveTimer.current);
      leaveTimer.current = null;
    }
  };
  const preview = useCallback((key: string) => {
    clearLeave();
    setState((current) => current.pinned ? current : { openKey: key, pinned: false });
  }, []);
  const unpreview = useCallback((key: string) => {
    clearLeave();
    leaveTimer.current = window.setTimeout(() => {
      setState((current) => current.pinned || current.openKey !== key ? current : { openKey: null, pinned: false });
    }, METRIC_KNOWLEDGE_CARD_LEAVE_DELAY_MS);
  }, []);
  const togglePin = useCallback((key: string) => {
    clearLeave();
    setState((current) => current.pinned && current.openKey === key
      ? { openKey: null, pinned: false }
      : { openKey: key, pinned: true });
  }, []);
  const dismiss = useCallback(() => {
    clearLeave();
    setState({ openKey: null, pinned: false });
  }, []);
  useEffect(() => {
    if (state.openKey === null) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismiss();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [dismiss, state.openKey]);
  useEffect(() => () => clearLeave(), []);
  return { openKey: state.openKey, pinned: state.pinned, preview, unpreview, togglePin, dismiss };
}

export function metricKnowledgeCardId(scope: string, metricKey: string): string {
  return `metric-help-${scope}-${metricKey.replaceAll(".", "-")}`;
}

/** Trigger props for any element (button, tile, SVG group) that describes a metric. */
export function metricKnowledgeCardTriggerProps(
  controller: MetricKnowledgeCardController,
  scope: string,
  metricKey: string,
) {
  const id = metricKnowledgeCardId(scope, metricKey);
  return {
    "aria-describedby": id,
    "data-help-open": controller.openKey === metricKey ? (controller.pinned ? "pinned" : "preview") : undefined,
    onPointerEnter: () => controller.preview(metricKey),
    onPointerLeave: () => controller.unpreview(metricKey),
    onFocus: () => controller.preview(metricKey),
    onBlur: () => controller.unpreview(metricKey),
    onClick: () => controller.togglePin(metricKey),
  } as const;
}

export function MetricKnowledgeCard({
  controller,
  scope,
  metricKey,
  label,
  status,
  locale = "en",
  compact = false,
  style,
}: {
  controller: MetricKnowledgeCardController;
  scope: string;
  metricKey: string;
  label: string;
  status: string;
  locale?: MetricHelpLocale;
  compact?: boolean;
  style?: React.CSSProperties;
}) {
  const help = metricHelpV2(metricKey, locale);
  const open = controller.openKey === metricKey;
  const pinned = open && controller.pinned;
  return (
    <div
      className={`metric-knowledge-card${compact ? " metric-knowledge-card--compact" : ""}`}
      data-open={open ? "true" : "false"}
      data-pinned={pinned ? "true" : "false"}
      hidden={!open}
      id={metricKnowledgeCardId(scope, metricKey)}
      onPointerEnter={() => controller.preview(metricKey)}
      onPointerLeave={() => controller.unpreview(metricKey)}
      role="tooltip"
      style={style}
    >
      <header>
        <strong>{label}</strong>
        <span>{status}{help?.fallback ? " · EN" : ""}</span>
      </header>
      {help === null ? (
        <p>No knowledge card is registered for this metric key.</p>
      ) : (
        <>
          <p>{help.entry.meaning}</p>
          <dl>
            <div><dt>{locale === "pl" && !help.fallback ? "Pytanie" : "Question"}</dt><dd>{help.entry.question}</dd></div>
            <div><dt>{locale === "pl" && !help.fallback ? "Jednostka" : "Unit"}</dt><dd>{help.entry.observationUnit}</dd></div>
            <div><dt>{locale === "pl" && !help.fallback ? "Kierunek" : "Direction"}</dt><dd>{help.entry.direction}</dd></div>
            <div><dt>{locale === "pl" && !help.fallback ? "Liczy się" : "Counts"}</dt><dd>{help.entry.counts}</dd></div>
            <div><dt>{locale === "pl" && !help.fallback ? "Nie liczy się" : "Does not count"}</dt><dd>{help.entry.doesNotCount}</dd></div>
            <div><dt>{locale === "pl" && !help.fallback ? "Dowody" : "Evidence"}</dt><dd>{help.entry.objectiveEvidence}</dd></div>
          </dl>
        </>
      )}
      <footer>{pinned ? "Pinned · Esc closes" : "Click or tap to pin · Esc closes"} · {help?.version ?? "unversioned"}</footer>
    </div>
  );
}
