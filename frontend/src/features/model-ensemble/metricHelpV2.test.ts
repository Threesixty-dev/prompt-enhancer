import { describe, expect, it } from "vitest";
import { QUALITY_ANALYSIS_DEFINITIONS } from "../quality-profile/qualityProfile";
import {
  METRIC_HELP_V2,
  METRIC_HELP_V2_DIRECTIONS,
  METRIC_HELP_V2_KEYS,
  metricHelpV2,
  metricHelpV2IsObjective,
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

  it("marks exactly the five typed-evidence metrics as objective", () => {
    const objectiveKeys = KEYS.filter(metricHelpV2IsObjective);
    expect(objectiveKeys).toEqual([
      "logic.hypothesis_test_linkage",
      "logic.requirement_action_traceability",
      "outcome.agent_claim_grounding",
      "outcome.first_pass_verification",
      "outcome.verified_requirement_coverage",
    ]);
  });

  it("documents the shipped compatibility heuristic quirks instead of idealizing them", () => {
    expect(METRIC_HELP_V2.en["prompt.problem_evidence_quality"].counts).toMatch(/diagnostic keyword/i);
    expect(METRIC_HELP_V2.en["prompt.constraint_precision"].doesNotCount).toMatch(/generic prohibition/i);
    expect(METRIC_HELP_V2.en["prompt.deliverable_contract"].doesNotCount).toMatch(/path or location alone/i);
    expect(METRIC_HELP_V2.en["outcome.agent_claim_grounding"].observationUnit).toMatch(/every such clause/i);
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

  it("produces distinct truthful copy per state without bands or invented factors", () => {
    const pending = metricInspectorSentences({ ...base, state: "unknown", explanationCode: "episode_horizon_open" });
    const pendingV2 = metricInspectorSentences({ ...base, state: "pending" });
    const na = metricInspectorSentences({ ...base, state: "not_applicable" });
    const unknown = metricInspectorSentences({ ...base, state: "unknown" });
    const abstained = metricInspectorSentences({ ...base, state: "abstained" });
    const objective = metricInspectorSentences({ ...base, metricKey: "outcome.agent_claim_grounding", label: "Agent claim grounding", state: "abstained" });
    const error = metricInspectorSentences({ ...base, state: "execution_error" });
    const missing = metricInspectorSentences({ ...base, state: "missing" });
    const experimental = metricInspectorSentences({ ...base, state: "unknown", experimentalVisible: true, experimentalMedian: 0.6 });
    const measured = metricInspectorSentences({ ...base, state: "known", numericValue: 0.5, numerator: 1, denominator: 2, experimentalFactorKeys: ["goal_cue"] });
    const zero = metricInspectorSentences({ ...base, state: "known", numericValue: 0, numerator: 0, denominator: 3 });
    const all = [pending, na, unknown, abstained, error, missing, experimental, measured, zero];
    expect(new Set(all.map((sentence) => sentence.kind)).size).toBe(9);
    expect(pending.meaning).toMatch(/not a zero/);
    expect(pendingV2).toEqual(pending);
    expect(na.meaning).toMatch(/nothing to score/);
    expect(unknown.meaning).toMatch(/not a low value/);
    expect(unknown.meaning).not.toMatch(/No objective receipt/);
    expect(abstained.meaning).toMatch(/abstained instead of guessing/);
    expect(objective.meaning).toMatch(/authoritative typed links or receipts are missing/);
    expect(objective.meaning).not.toMatch(/denominator/);
    expect(error.meaning).toMatch(/not a low score/);
    expect(missing.meaning).toMatch(/nothing was measured/);
    expect(experimental.meaning).toMatch(/uncalibrated model range/);
    expect(zero.meaning).toMatch(/radar-quality zero/);
    expect(measured.meaning).toMatch(/exactly 50%/);
    expect(measured.meaning).not.toMatch(/weakest|measured evidence/);
    for (const sentence of all) {
      expect(sentence.meaning).not.toMatch(/strong band|75%/);
      expect(sentence.action).toMatch(/ — verify: /);
    }
  });

  it("labels predictive factor keys as model judgment only when an estimate is visible", () => {
    const withEstimate = metricInspectorSentences({
      ...base, state: "known", numericValue: 0.4, numerator: 2, denominator: 5,
      experimentalFactorKeys: ["goal_cue", "target_cue"], experimentalVisible: true, experimentalMedian: 0.5,
    });
    expect(withEstimate.meaning).toMatch(/model factor probabilities are lowest for goal cue and target cue — a model judgment, not measured evidence/);
    expect(withEstimate.action).toMatch(/^Safest next step: /);
    const complete = metricInspectorSentences({ ...base, state: "known", numericValue: 1, numerator: 3, denominator: 3 });
    expect(complete.action).toMatch(/^Nothing to change for this window/);
  });

  it("names the exact missing authority family for V2 unknown states", () => {
    const semantic = metricInspectorSentences({
      metricKey: "collaboration.ambiguity_resolution",
      label: "Ambiguity resolution",
      direction: "higher_is_better",
      state: "unknown",
      numericValue: null,
      numerator: null,
      denominator: null,
      explanationCode: "opportunity_family_unobservable",
    });
    expect(semantic.meaning).toMatch(/cannot yet own the typed opportunity family/i);
    expect(semantic.meaning).toMatch(/not counted as zero/i);

    const objective = metricInspectorSentences({
      metricKey: "outcome.verified_requirement_coverage",
      label: "Verified requirement coverage",
      direction: "higher_is_better",
      state: "unknown",
      numericValue: null,
      numerator: null,
      denominator: null,
      explanationCode: "typed_objective_authority_unavailable",
    });
    expect(objective.meaning).toMatch(/provider adapter does not expose/i);
    expect(objective.meaning).toMatch(/prose and model estimates cannot substitute/i);
  });

  it("explains lower-is-better values and the radar-quality center truthfully", () => {
    const rework = metricInspectorSentences({
      metricKey: "collaboration.rework_candidate_rate", label: "Rework-candidate rate",
      direction: "lower_is_better", state: "known", numericValue: 0.1, numerator: 1, denominator: 10,
    });
    expect(rework.kind).toBe("measured");
    expect(rework.meaning).toMatch(/raw rate of 10% \(radar quality 90% because lower is better\)/);
    const center = metricInspectorSentences({
      metricKey: "collaboration.rework_candidate_rate", label: "Rework-candidate rate",
      direction: "lower_is_better", state: "known", numericValue: 1, numerator: 10, denominator: 10,
    });
    expect(center.kind).toBe("zero");
    expect(center.meaning).toMatch(/raw 100%.*radar quality is 0%/);
  });
});
