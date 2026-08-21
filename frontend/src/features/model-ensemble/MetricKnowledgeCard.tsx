import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type FocusEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { MetricContextFactList } from "./MetricContextFactList";
import type { MetricContextFacts } from "./metricContextFacts";
import {
  metricHelpV2,
  metricHelpV2DefinitionLabel,
  type MetricHelpProjectionVersion,
  type MetricInspectorSentences,
} from "./metricHelpV2";

/**
 * One knowledge-card controller per workspace. A target is {surface, metricKey};
 * at most one card is visible across every trigger surface (axis strip and
 * exact-value board). Triggers get `aria-describedby` pointing at an always
 * present hidden one-sentence description, so semantics never depend on the
 * visible card. The visible card is a viewport-clamped overlay: opening it
 * never changes the radar/workspace layout.
 */
export type MetricKnowledgeSurface =
  | "strip"
  | "board"
  | "team-board"
  | "team-compact"
  | "team-members";
export interface MetricKnowledgeTarget { surface: MetricKnowledgeSurface; metricKey: string }

export interface MetricKnowledgeAnchor {
  bottom: number;
  left: number;
  right: number;
  top: number;
}

export interface MetricKnowledgeCardController {
  idPrefix: string;
  target: MetricKnowledgeTarget | null;
  pinned: boolean;
  /** Plain viewport coordinates only; never retain the originating DOM node. */
  anchor?: MetricKnowledgeAnchor | null;
  preview: (target: MetricKnowledgeTarget, anchor?: MetricKnowledgeAnchor) => void;
  unpreview: (target: MetricKnowledgeTarget) => void;
  togglePin: (target: MetricKnowledgeTarget, anchor?: MetricKnowledgeAnchor) => void;
  dismiss: () => void;
}

export const METRIC_KNOWLEDGE_CARD_LEAVE_DELAY_MS = 150;

/**
 * Rich, structured, pinnable explainer/knowledge content is a non-modal
 * `region` (named by `aria-label`), never a `tooltip`: tooltip content is
 * expected to be plain, transient text and is not navigable by assistive
 * technology, while these cards carry sections, definition lists and links.
 */
export const METRIC_CARD_ROLE = "region" as const;

const same = (left: MetricKnowledgeTarget | null, right: MetricKnowledgeTarget): boolean =>
  left !== null && left.surface === right.surface && left.metricKey === right.metricKey;

const anchorFromElement = (element: Element): MetricKnowledgeAnchor => {
  const rect = element.getBoundingClientRect();
  return { bottom: rect.bottom, left: rect.left, right: rect.right, top: rect.top };
};

/**
 * Position the card outside its trigger row. The earlier fixed bottom-right
 * placement could cover later axis controls, making valid metrics impossible
 * to select with a pointer even though keyboard/unit tests still passed.
 */
export function metricKnowledgeCardViewportStyle(
  controller: Pick<MetricKnowledgeCardController, "anchor">,
  preferredWidth = 360,
): CSSProperties | undefined {
  const anchor = controller.anchor;
  if (anchor == null || typeof window === "undefined") return undefined;
  const margin = 12;
  const gap = 8;
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const width = Math.max(0, Math.min(preferredWidth, viewportWidth - margin * 2));
  const left = Math.max(margin, Math.min(anchor.left, viewportWidth - margin - width));
  const below = Math.max(0, viewportHeight - anchor.bottom - gap - margin);
  const above = Math.max(0, anchor.top - gap - margin);
  const placeBelow = below >= Math.min(240, viewportHeight * 0.45) || below >= above;
  return {
    bottom: placeBelow ? "auto" : viewportHeight - anchor.top + gap,
    left,
    maxHeight: Math.max(96, placeBelow ? below : above),
    right: "auto",
    top: placeBelow ? anchor.bottom + gap : "auto",
  };
}

export function useMetricKnowledgeCardController(): MetricKnowledgeCardController {
  const idPrefix = useId();
  const [state, setState] = useState<{
    target: MetricKnowledgeTarget | null;
    pinned: boolean;
    anchor: MetricKnowledgeAnchor | null;
  }>({ target: null, pinned: false, anchor: null });
  const leaveTimer = useRef<number | null>(null);
  const clearLeave = () => {
    if (leaveTimer.current !== null) {
      window.clearTimeout(leaveTimer.current);
      leaveTimer.current = null;
    }
  };
  const preview = useCallback((target: MetricKnowledgeTarget, anchor?: MetricKnowledgeAnchor) => {
    clearLeave();
    setState((current) => current.pinned ? current : {
      target,
      pinned: false,
      anchor: anchor ?? (same(current.target, target) ? current.anchor : null),
    });
  }, []);
  const unpreview = useCallback((target: MetricKnowledgeTarget) => {
    clearLeave();
    leaveTimer.current = window.setTimeout(() => {
      setState((current) => current.pinned || !same(current.target, target)
        ? current
        : { target: null, pinned: false, anchor: null });
    }, METRIC_KNOWLEDGE_CARD_LEAVE_DELAY_MS);
  }, []);
  const togglePin = useCallback((target: MetricKnowledgeTarget, anchor?: MetricKnowledgeAnchor) => {
    clearLeave();
    setState((current) => current.pinned && same(current.target, target)
      ? { target: null, pinned: false, anchor: null }
      : {
        target,
        pinned: true,
        anchor: anchor ?? (same(current.target, target) ? current.anchor : null),
      });
  }, []);
  const dismiss = useCallback(() => {
    clearLeave();
    setState({ target: null, pinned: false, anchor: null });
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
  return {
    idPrefix,
    target: state.target,
    pinned: state.pinned,
    anchor: state.anchor,
    preview,
    unpreview,
    togglePin,
    dismiss,
  };
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
    onPointerEnter: (event: ReactPointerEvent<HTMLElement>) =>
      controller.preview(target, anchorFromElement(event.currentTarget)),
    onPointerLeave: () => controller.unpreview(target),
    onFocus: (event: FocusEvent<HTMLElement>) =>
      controller.preview(target, anchorFromElement(event.currentTarget)),
    onBlur: () => controller.unpreview(target),
  } as const;
}

export interface MetricKnowledgeEntry {
  key: string;
  label: string;
  status: string;
  /** Exact sealed projection selecting frozen historical or current r5 help. */
  projectionVersion?: MetricHelpProjectionVersion | null;
  /** Exact receipt state and authority projected by metricAxisModel. */
  guidance?: MetricInspectorSentences;
  /** Scope · contributors · model · evidence context; rendered in full and compact cards alike. */
  context?: MetricContextFacts;
}

/** Always-present hidden one-sentence descriptions referenced by every trigger. */
export function MetricKnowledgeDescriptions({ controller, entries }: {
  controller: MetricKnowledgeCardController;
  entries: readonly MetricKnowledgeEntry[];
}) {
  return (
    <div className="metric-knowledge-descriptions" hidden>
      {entries.map((entry) => (
        <span id={metricKnowledgeDescriptionId(controller, entry.key)} key={entry.key}>
          {entry.label}: {entry.guidance === undefined
            ? metricHelpV2(entry.key, "en", entry.projectionVersion ?? null)?.entry.meaning ?? "No knowledge card is registered for this metric key."
            : `${entry.guidance.meaning} ${entry.guidance.action}`}
          {entry.context === undefined ? "" : ` Scope: ${entry.context.label}.`}
        </span>
      ))}
    </div>
  );
}

/** Viewport overlay slot for one surface; renders the single open card, if it targets this surface. */
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
  const staleTarget = target !== null && target.surface === surface && entry === null;
  useEffect(() => {
    // A pinned key can disappear when the user changes lens.  Dismiss it so
    // the next pointer/focus preview is never blocked by an invisible target.
    if (staleTarget) controller.dismiss();
  }, [controller.dismiss, staleTarget]);
  if (entry === null) return <div className="metric-knowledge-slot" data-surface={surface} />;
  const help = metricHelpV2(entry.key, "en", entry.projectionVersion ?? null);
  const definitionLabel = help === null ? null : metricHelpV2DefinitionLabel(help);
  const definitionHeading = definitionLabel === null
    ? null
    : `${definitionLabel.charAt(0).toUpperCase()}${definitionLabel.slice(1)}`;
  const pinned = controller.pinned;
  return (
    <div className="metric-knowledge-slot" data-surface={surface}>
      <div
        aria-label={`${entry.label} knowledge card`}
        className={`metric-knowledge-card metric-knowledge-card--viewport${compact ? " metric-knowledge-card--compact" : ""}`}
        data-metric-key={entry.key}
        data-pinned={pinned ? "true" : "false"}
        data-projection-version={entry.projectionVersion ?? undefined}
        data-state={entry.guidance?.state}
        data-suppression-reason={entry.guidance?.suppressionReason ?? undefined}
        data-comparability={entry.guidance?.comparabilityState ?? undefined}
        onPointerEnter={() => controller.preview({ surface, metricKey: entry.key })}
        onPointerLeave={() => controller.unpreview({ surface, metricKey: entry.key })}
        role={METRIC_CARD_ROLE}
        style={metricKnowledgeCardViewportStyle(controller, compact ? 320 : 360)}
      >
        <header>
          <strong>{entry.label}</strong>
          <span>{entry.status}</span>
        </header>
        {entry.guidance !== undefined && (
          <section aria-label="Current metric guidance" className="metric-knowledge-card__guidance">
            <p><b>Current state.</b> {entry.guidance.meaning}</p>
            <p><b>Next action.</b> {entry.guidance.action}</p>
            <dl>
              <div><dt>Guidance basis</dt><dd>{entry.guidance.basis}</dd></div>
              <div><dt>Evidence authority</dt><dd>{entry.guidance.evidenceAuthority ?? "Not reported by this receipt"}</dd></div>
              <div><dt>Explanation code</dt><dd>{entry.guidance.explanationCode ?? "None"}</dd></div>
              <div><dt>Suppression</dt><dd>{entry.guidance.suppressionReason ?? "None"}</dd></div>
              <div><dt>Comparability</dt><dd>{entry.guidance.comparabilityState ?? "Not exposed"}</dd></div>
            </dl>
          </section>
        )}
        {entry.context !== undefined && <MetricContextFactList compact={compact} context={entry.context} />}
        {help === null ? (
          <p>No knowledge card is registered for this metric key.</p>
        ) : (
          <>
            <p>
              <b>{definitionHeading} definition.</b> {help.entry.meaning}
            </p>
            <dl>
              <div><dt>Question</dt><dd>{help.entry.question}</dd></div>
              <div><dt>Unit</dt><dd>{help.entry.observationUnit}</dd></div>
              <div><dt>Direction</dt><dd>{help.entry.direction}</dd></div>
              <div><dt>Counts</dt><dd>{help.entry.counts}</dd></div>
              <div><dt>Does not count</dt><dd>{help.entry.doesNotCount}</dd></div>
              {entry.guidance === undefined && (
                <div><dt>Candidate definition evidence notes</dt><dd>{help.entry.objectiveEvidence}</dd></div>
              )}
            </dl>
            {help.measurement !== null && (
              <p className="metric-knowledge-card__measurement">
                <b>{help.definitionScope !== "historical_candidate"
                  ? `${definitionHeading} measurement (definition v${help.measurement.definitionVersion}).`
                  : `Current measurement (shipped definition v${help.measurement.definitionVersion}).`}</b> {help.measurement.method} {help.measurement.limitation}
              </p>
            )}
          </>
        )}
        <footer>{pinned ? "Pinned · Esc closes" : "Click or tap the control to pin · Esc closes"} · {help?.version ?? "unversioned"} · {help?.definitionScope === "historical_candidate" || help === null ? "candidate definition shown separately from its shipped measurement method" : `${definitionLabel} definition shown with projection-specific measurement metadata`}</footer>
      </div>
    </div>
  );
}
