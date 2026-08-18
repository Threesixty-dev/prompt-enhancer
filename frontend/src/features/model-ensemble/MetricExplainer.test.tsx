import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MetricExplainerCardSlot,
  MetricExplainerDescriptions,
  metricExplainerDescriptionId,
  metricExplainerTriggerProps,
  type MetricExplainerEntry,
} from "./MetricExplainer";
import {
  METRIC_KNOWLEDGE_CARD_LEAVE_DELAY_MS,
  useMetricKnowledgeCardController,
} from "./MetricKnowledgeCard";
import { METRIC_HELP_V2_KEYS, metricExplainerSentences, metricHelpV2, metricInspectorSentences } from "./metricHelpV2";
import { metricDecisionGuidance } from "../quality-profile/metricGuidance";

afterEach(() => {
  vi.useRealTimers();
});

describe("metricExplainerSentences", () => {
  it("returns exactly two sentences from the canonical registry for every workspace metric", () => {
    for (const key of METRIC_HELP_V2_KEYS) {
      const sentences = metricExplainerSentences(key, { provenance: "measured", numericValue: 0.5 })!;
      expect(sentences).not.toBeNull();
      expect(sentences.explanation).toBe(metricHelpV2(key)!.entry.meaning.trim().replace(/[^.!?]$/u, (last) => `${last}.`));
      expect(sentences.explanation).toMatch(/[.!?]$/u);
      expect(sentences.improvement).toMatch(/[.!?]$/u);
      expect(sentences.improvement).toContain(metricDecisionGuidance(key).tryNext.replace(/[.\s]+$/u, ""));
      expect(sentences.provenanceLabel).toBe("Measured · typed evidence");
      expect(sentences.basis).toBe("measured");
    }
  });

  it("keeps experimental and missing provenance out of the measured voice", () => {
    const experimental = metricExplainerSentences("prompt.context_sufficiency", { provenance: "experimental" })!;
    expect(experimental.improvement).toMatch(/^If the experimental signal persists, /u);
    expect(experimental.provenanceLabel).toMatch(/not measured/u);
    expect(experimental.basis).toBe("experimental");
    const missing = metricExplainerSentences("outcome.first_pass_verification", { provenance: "not_measured" })!;
    expect(missing.improvement).toMatch(/receipt/u);
    expect(missing.provenanceLabel).toBe("Not measured in this scope");
    expect(missing.basis).toBe("readiness");
    const fullyMet = metricExplainerSentences("prompt.task_definition_coverage", { provenance: "measured", numericValue: 1 })!;
    expect(fullyMet.improvement).toMatch(/^Keep the observed practice/u);
  });

  it("returns null for an unregistered metric key", () => {
    expect(metricExplainerSentences("prompt.not_a_metric")).toBeNull();
  });
});

const ENTRIES: readonly MetricExplainerEntry[] = [
  { key: "prompt.task_definition_coverage", label: "Task definition coverage", provenance: "measured", numericValue: 0.72, valueLabel: "72% · 41/57" },
  { key: "logic.decision_rationale_coverage", label: "Decision rationale coverage", provenance: "experimental", numericValue: null, valueLabel: "Unknown" },
];

function Harness({ compact = false }: { compact?: boolean }) {
  const controller = useMetricKnowledgeCardController();
  return (
    <div>
      <MetricExplainerDescriptions controller={controller} entries={ENTRIES} surface="team-board" />
      {ENTRIES.map((entry) => (
        <button
          key={entry.key}
          {...metricExplainerTriggerProps(controller, "team-board", entry.key)}
          onClick={() => controller.togglePin({ surface: "team-board", metricKey: entry.key })}
          type="button"
        >
          {entry.label}
        </button>
      ))}
      <MetricExplainerCardSlot compact={compact} controller={controller} entries={ENTRIES} surface="team-board" />
    </div>
  );
}

describe("MetricExplainer affordance", () => {
  it("describes every trigger with both sentences even when no card is open", () => {
    render(<Harness />);
    expect(document.querySelectorAll('[role="region"][data-metric-key]')).toHaveLength(0);
    for (const entry of ENTRIES) {
      const trigger = screen.getByRole("button", { name: entry.label });
      const description = document.getElementById(trigger.getAttribute("aria-describedby")!);
      expect(description).not.toBeNull();
      const sentences = metricInspectorSentences({
        metricKey: entry.key,
        label: entry.label,
        state: entry.numericValue === null ? "missing" : "known",
        direction: "higher_is_better",
        numericValue: entry.numericValue,
        numerator: null,
        denominator: null,
        experimentalVisible: entry.provenance === "experimental",
      });
      expect(description!.textContent).toContain(sentences.meaning);
      expect(description!.textContent).toContain(sentences.action);
    }
  });

  it("opens one card on hover or focus, pins on click, and closes on Escape", () => {
    vi.useFakeTimers();
    render(<Harness compact />);
    const [first, second] = ENTRIES.map((entry) => screen.getByRole("button", { name: entry.label }));
    fireEvent.pointerEnter(first);
    let cards = document.querySelectorAll('[role="region"][data-metric-key]');
    expect(cards).toHaveLength(1);
    expect(cards[0]).toHaveAttribute("data-metric-key", "prompt.task_definition_coverage");
    expect(cards[0]).toHaveAttribute("data-provenance", "measured");
    expect(cards[0].className).toContain("metric-explainer-card--compact");
    expect(cards[0].querySelectorAll("p")).toHaveLength(2);
    expect(cards[0].textContent).toContain("Meaning");
    expect(cards[0].textContent).toContain("Next action");
    expect(cards[0].textContent).toContain("Evidence authority");

    fireEvent.pointerLeave(first);
    act(() => { vi.advanceTimersByTime(METRIC_KNOWLEDGE_CARD_LEAVE_DELAY_MS + 1); });
    expect(document.querySelectorAll('[role="region"][data-metric-key]')).toHaveLength(0);

    fireEvent.focus(second);
    cards = document.querySelectorAll('[role="region"][data-metric-key]');
    expect(cards).toHaveLength(1);
    expect(cards[0]).toHaveAttribute("data-provenance", "experimental");
    expect(cards[0].textContent).toContain("Experimental");

    fireEvent.click(second);
    expect(document.querySelector('[role="region"][data-metric-key]')).toHaveAttribute("data-pinned", "true");
    fireEvent.blur(second);
    act(() => { vi.advanceTimersByTime(METRIC_KNOWLEDGE_CARD_LEAVE_DELAY_MS + 1); });
    expect(document.querySelectorAll('[role="region"][data-metric-key]')).toHaveLength(1);
    fireEvent.pointerEnter(first);
    expect(document.querySelector('[role="region"][data-metric-key]')).toHaveAttribute("data-metric-key", "logic.decision_rationale_coverage");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.querySelectorAll('[role="region"][data-metric-key]')).toHaveLength(0);
  });

  it("uses distinct description ids per surface", () => {
    const controller = { idPrefix: ":x:" };
    expect(metricExplainerDescriptionId(controller, "team-board", "prompt.a.b"))
      .not.toBe(metricExplainerDescriptionId(controller, "team-compact", "prompt.a.b"));
    expect(metricExplainerDescriptionId(controller, "team-board", "prompt.a.b")).not.toContain(".");
  });
});
