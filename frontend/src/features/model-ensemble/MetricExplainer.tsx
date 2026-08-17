import { useEffect } from "react";
import {
  METRIC_EXPLAINER_PROVENANCE_LABELS,
  METRIC_HELP_V2_VERSION,
  metricInspectorSentences,
  type MetricInspectorInput,
  type MetricExplainerProvenance,
} from "./metricHelpV2";
import type {
  MetricKnowledgeCardController,
  MetricKnowledgeSurface,
  MetricKnowledgeTarget,
} from "./MetricKnowledgeCard";
import "./MetricExplainer.css";

/**
 * Two-sentence metric explainer: one shared controller per surface, one
 * visible card at a time, opened by pointer hover, keyboard focus, or a click
 * that pins it. Every trigger also carries `aria-describedby` to an always
 * present hidden copy of the same two sentences, so nothing is hover-only. The
 * visible card is a viewport-clamped overlay: opening it never reflows the
 * surface it describes. Copy comes from the canonical metric-help-v2 registry
 * and decision guidance, so full and compact modes can never drift apart.
 */
export interface MetricExplainerEntry {
  key: string;
  label: string;
  provenance: MetricExplainerProvenance;
  /** Raw fraction in the metric's own direction, when a value exists. */
  numericValue: number | null;
  /** Short value or state text shown in the card header ("72% · 41/57", "Suppressed"). */
  valueLabel: string;
  state?: MetricInspectorInput["state"];
  direction?: MetricInspectorInput["direction"];
  numerator?: number | null;
  denominator?: number | null;
  explanationCode?: string | null;
  evidenceAuthority?: string | null;
  suppressionReason?: MetricInspectorInput["suppressionReason"];
  comparabilityState?: MetricInspectorInput["comparabilityState"];
}

function guidanceFor(entry: MetricExplainerEntry) {
  return metricInspectorSentences({
    metricKey: entry.key,
    label: entry.label,
    state: entry.state ?? (entry.provenance === "measured" && entry.numericValue !== null ? "known" : "missing"),
    direction: entry.direction ?? "higher_is_better",
    numericValue: entry.numericValue,
    numerator: entry.numerator ?? null,
    denominator: entry.denominator ?? null,
    explanationCode: entry.explanationCode ?? null,
    evidenceAuthority: entry.evidenceAuthority ?? null,
    suppressionReason: entry.suppressionReason ?? null,
    comparabilityState: entry.comparabilityState ?? null,
    experimentalVisible: entry.provenance === "experimental",
  });
}

const sameTarget = (left: MetricKnowledgeTarget | null, right: MetricKnowledgeTarget): boolean =>
  left !== null && left.surface === right.surface && left.metricKey === right.metricKey;

export function metricExplainerDescriptionId(
  controller: Pick<MetricKnowledgeCardController, "idPrefix">,
  surface: MetricKnowledgeSurface,
  metricKey: string,
): string {
  return `${controller.idPrefix}explain-${surface}-${metricKey.replaceAll(".", "-")}`;
}

/** Trigger props for the accessible control (button/tile) that a metric explainer describes. */
export function metricExplainerTriggerProps(
  controller: MetricKnowledgeCardController,
  surface: MetricKnowledgeSurface,
  metricKey: string,
) {
  const target: MetricKnowledgeTarget = { surface, metricKey };
  const open = sameTarget(controller.target, target);
  return {
    "aria-describedby": metricExplainerDescriptionId(controller, surface, metricKey),
    "data-explainer-open": open ? (controller.pinned ? "pinned" : "preview") : undefined,
    onPointerEnter: () => controller.preview(target),
    onPointerLeave: () => controller.unpreview(target),
    onFocus: () => controller.preview(target),
    onBlur: () => controller.unpreview(target),
  } as const;
}

/** Always-present hidden two-sentence descriptions referenced by every trigger. */
export function MetricExplainerDescriptions({ controller, surface, entries }: {
  controller: Pick<MetricKnowledgeCardController, "idPrefix">;
  surface: MetricKnowledgeSurface;
  entries: readonly MetricExplainerEntry[];
}) {
  return (
    <div className="metric-explainer-descriptions" hidden>
      {entries.map((entry) => {
        const sentences = guidanceFor(entry);
        return (
          <span id={metricExplainerDescriptionId(controller, surface, entry.key)} key={entry.key}>
            {entry.label} ({METRIC_EXPLAINER_PROVENANCE_LABELS[entry.provenance]}): {sentences.meaning} {sentences.action}
          </span>
        );
      })}
    </div>
  );
}

/** Viewport overlay slot for one surface; renders the single open explainer card, if it targets this surface. */
export function MetricExplainerCardSlot({ controller, surface, entries, compact = false }: {
  controller: MetricKnowledgeCardController;
  surface: MetricKnowledgeSurface;
  entries: readonly MetricExplainerEntry[];
  compact?: boolean;
}) {
  const target = controller.target;
  const entry = target !== null && target.surface === surface
    ? entries.find((candidate) => candidate.key === target.metricKey) ?? null
    : null;
  const staleTarget = target !== null && target.surface === surface && entry === null;
  const dismiss = controller.dismiss;
  useEffect(() => {
    // The pinned key can disappear when the lens or scope changes; dismiss it so
    // the next pointer/focus preview is never blocked by an invisible target.
    if (staleTarget) dismiss();
  }, [dismiss, staleTarget]);
  if (entry === null) return <div className="metric-explainer-slot" data-surface={surface} />;
  const sentences = guidanceFor(entry);
  const pinned = controller.pinned;
  return (
    <div className="metric-explainer-slot" data-surface={surface}>
      <div
        aria-label={`${entry.label} explainer`}
        className={`metric-explainer-card metric-explainer-card--viewport${compact ? " metric-explainer-card--compact" : ""}`}
        data-metric-key={entry.key}
        data-pinned={pinned ? "true" : "false"}
        data-provenance={entry.provenance}
        data-state={sentences.state}
        data-suppression-reason={sentences.suppressionReason ?? undefined}
        data-comparability={sentences.comparabilityState ?? undefined}
        onPointerEnter={() => controller.preview({ surface, metricKey: entry.key })}
        onPointerLeave={() => controller.unpreview({ surface, metricKey: entry.key })}
        role="tooltip"
      >
        <header>
          <div>
            <strong>{entry.label}</strong>
            <span>{entry.valueLabel}</span>
          </div>
          <b data-provenance={entry.provenance}>{METRIC_EXPLAINER_PROVENANCE_LABELS[entry.provenance]}</b>
        </header>
        <p><span>Meaning</span>{sentences.meaning}</p>
        <p><span>Next action</span>{sentences.action}</p>
        <dl className="metric-explainer-card__authority">
          <div><dt>Evidence authority</dt><dd>{sentences.evidenceAuthority ?? "Not reported by this receipt"}</dd></div>
          <div><dt>Explanation code</dt><dd>{sentences.explanationCode ?? "None"}</dd></div>
          <div><dt>Suppression</dt><dd>{sentences.suppressionReason ?? "None"}</dd></div>
          <div><dt>Comparability</dt><dd>{sentences.comparabilityState ?? "Not exposed"}</dd></div>
        </dl>
        <footer>
          {pinned ? "Pinned · Esc closes" : "Click or tap to pin · Esc closes"}
          {" · "}
          {METRIC_HELP_V2_VERSION}
        </footer>
      </div>
    </div>
  );
}
