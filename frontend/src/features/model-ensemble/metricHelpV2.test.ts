import { describe, expect, it } from "vitest";
import { QUALITY_ANALYSIS_DEFINITIONS } from "../quality-profile/qualityProfile";
import {
  METRIC_HELP_V2,
  METRIC_HELP_V2_DIRECTIONS,
  METRIC_HELP_V2_KEYS,
  metricHelpV2,
  metricInspectorSentences,
} from "./metricHelpV2";

const KEYS = QUALITY_ANALYSIS_DEFINITIONS.map((definition) => definition.key);

describe("metricHelpV2 registry", () => {
  it("covers all twenty workspace metrics in EN and PL with complete fields", () => {
    expect(new Set(METRIC_HELP_V2_KEYS)).toEqual(new Set(KEYS));
    expect(METRIC_HELP_V2_KEYS).toHaveLength(20);
    for (const key of KEYS) {
      for (const locale of ["en", "pl"] as const) {
        const entry = METRIC_HELP_V2[locale][key];
        expect(entry, `${locale} ${key}`).toBeDefined();
        for (const field of ["meaning", "question", "observationUnit", "direction", "counts", "doesNotCount", "objectiveEvidence"] as const) {
          expect(entry[field].trim().length, `${locale} ${key} ${field}`).toBeGreaterThan(8);
        }
      }
      const definition = QUALITY_ANALYSIS_DEFINITIONS.find((candidate) => candidate.key === key)!;
      expect(METRIC_HELP_V2_DIRECTIONS[key]).toBe(definition.direction);
    }
  });

  it("falls back to English for unknown locales and reports it", () => {
    const polish = metricHelpV2("prompt.task_definition_coverage", "pl");
    expect(polish?.locale).toBe("pl");
    expect(polish?.fallback).toBe(false);
    const fallback = metricHelpV2("prompt.task_definition_coverage", "de" as never);
    expect(fallback?.locale).toBe("en");
    expect(fallback?.fallback).toBe(true);
    expect(metricHelpV2("prompt.not_a_metric")).toBeNull();
  });

  it("never calls uncalibrated ranges confidence or probability of success", () => {
    for (const locale of ["en", "pl"] as const) {
      for (const entry of Object.values(METRIC_HELP_V2[locale])) {
        expect(JSON.stringify(entry)).not.toMatch(/confidence|probability of success/i);
      }
    }
  });
});

describe("metricInspectorSentences", () => {
  const base = {
    metricKey: "prompt.task_definition_coverage",
    label: "Task definition coverage",
    direction: "higher_is_better" as const,
    numericValue: null,
    numerator: null,
    denominator: null,
  };

  it("produces distinct truthful copy per state without inventing factor evidence", () => {
    const pending = metricInspectorSentences({ ...base, state: "unknown", explanationCode: "episode_horizon_open" });
    const na = metricInspectorSentences({ ...base, state: "not_applicable" });
    const unknown = metricInspectorSentences({ ...base, state: "unknown" });
    const error = metricInspectorSentences({ ...base, state: "execution_error" });
    const missing = metricInspectorSentences({ ...base, state: "missing" });
    const experimental = metricInspectorSentences({ ...base, state: "unknown", experimentalVisible: true, experimentalMedian: 0.6 });
    const measured = metricInspectorSentences({ ...base, state: "known", numericValue: 0.5, numerator: 1, denominator: 2 });
    const strong = metricInspectorSentences({ ...base, state: "known", numericValue: 1, numerator: 3, denominator: 3 });
    const zero = metricInspectorSentences({ ...base, state: "known", numericValue: 0, numerator: 0, denominator: 3 });
    const kinds = [pending, na, unknown, error, missing, experimental, measured, strong, zero].map((sentence) => sentence.kind);
    expect(new Set(kinds).size).toBe(9);
    expect(pending.diagnosis).toMatch(/not a zero/);
    expect(na.diagnosis).toMatch(/nothing to score/);
    expect(unknown.diagnosis).toMatch(/not a low value/);
    expect(error.diagnosis).toMatch(/not a low score/);
    expect(missing.diagnosis).toMatch(/nothing was measured/);
    expect(experimental.diagnosis).toMatch(/uncalibrated model range/);
    expect(zero.diagnosis).toMatch(/radar center/);
    expect(strong.diagnosis).toMatch(/strong band/);
    expect(measured.diagnosis).not.toMatch(/factor distribution is weakest/);
    for (const sentence of [pending, na, unknown, error, missing, experimental, measured, strong, zero]) {
      expect(sentence.action).toMatch(/ — verify: /);
    }
  });

  it("grounds a measured diagnosis in receipt-backed factors only when supplied", () => {
    const grounded = metricInspectorSentences({
      ...base, state: "known", numericValue: 0.4, numerator: 2, denominator: 5,
      measuredFactorKeys: ["goal_cue", "target_cue"],
    });
    expect(grounded.diagnosis).toMatch(/weakest on goal cue and target cue/);
    const rework = metricInspectorSentences({
      metricKey: "collaboration.rework_candidate_rate", label: "Rework-candidate rate",
      direction: "lower_is_better", state: "known", numericValue: 0.1, numerator: 1, denominator: 10,
    });
    expect(rework.kind).toBe("strong");
    expect(rework.diagnosis).toMatch(/raw 10%/);
    expect(rework.diagnosis).toMatch(/radar quality is 90%/);
  });
});
