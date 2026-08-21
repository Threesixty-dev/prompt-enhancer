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

  it("keeps exact r1-r4 clause copy frozen and selects exact reviewed-profile copy only for r5", () => {
    const historical = {
      "prompt.constraint_precision": {
        meaning: "Share of detected constraint clauses that also match the shipped concrete-detail vocabulary or a numeric bound.",
        question: "How many detected constraints include a recognized platform, version, numeric threshold, unit, or concrete environment term?",
        observationUnit: "one detected constraint clause",
        direction: "Higher is better (radar plots the raw share).",
        counts: "A constraint clause with a recognized numeric limit, threshold, platform, version, unit, or concrete environment term.",
        doesNotCount: "Absent constraints (they yield Unknown, never zero), vague wording, and a generic prohibition such as 'must not write files' without another recognized concrete detail.",
        objectiveEvidence: "No objective receipt backs the candidate value; it is a versioned lexical review candidate and never proof of quality or task success.",
      },
      "prompt.acceptance_testability": {
        meaning: "Share of detected requirements that carry an observable pass-condition cue.",
        question: "How many detected requirements include an observable pass condition?",
        observationUnit: "one detected requirement clause",
        direction: "Higher is better (radar plots the raw share).",
        counts: "A requirement clause with a check, test, threshold, comparison, or explicit pass cue; a bare test word can satisfy the shipped legacy heuristic.",
        doesNotCount: "The cue is not proof of a complete or correct acceptance criterion; checks the agent added later are not counted.",
        objectiveEvidence: "No objective receipt backs the candidate value; it is a versioned lexical review candidate and never proof of quality or task success.",
      },
      "prompt.deliverable_contract": {
        meaning: "Share of detected deliverable clauses that also match the shipped format, interface, audience, compatibility, or platform-detail vocabulary.",
        question: "How many detected deliverables include a recognized format, interface, audience, compatibility, or platform detail?",
        observationUnit: "one detected deliverable clause",
        direction: "Higher is better (radar plots the raw share).",
        counts: "A deliverable clause with a recognized format, interface, audience, compatibility, or platform token.",
        doesNotCount: "A path or location alone is not recognized by the shipped detail heuristic; only detected deliverable clauses form the denominator.",
        objectiveEvidence: "No objective receipt backs the candidate value; it is a versioned lexical review candidate and never proof of quality or task success.",
      },
    } as const;
    const r5 = {
      "prompt.constraint_precision": {
        meaning: "Share of the exact constraint-kind slots declared in the reviewed task profile whose matching versioned cue appears in the canonical active user request.",
        question: "For each expected constraint kind in the reviewed profile, does the canonical active user request contain its matching versioned cue?",
        observationUnit: "one expected constraint-kind slot in the reviewed task profile",
        direction: "Higher is better (radar plots the raw share).",
        counts: "Numerator: one configured expected constraint kind whose matching versioned cue appears in the canonical active user request; each configured kind counts at most once.",
        doesNotCount: "Denominator: exactly the configured expected_constraint_kinds slots, not detected constraint clauses. Unconfigured kinds, cues outside the canonical active request, superseded requests, and agent prose do not count; no configured slots yields Unknown, never zero.",
        objectiveEvidence: "The value is a deterministic local, method-only comparison between the immutable reviewed task-profile revision and the canonical active user request; it is neither a model judgment nor objective proof of quality or task success.",
      },
      "prompt.acceptance_testability": {
        meaning: "Share of the exact expected-outcome slots declared in the reviewed task profile filled by distinct normalized checkable requirement clauses owned by the canonical active user request, capped at the declared count.",
        question: "How many reviewed expected-outcome slots are filled by distinct checkable requirement clauses in the canonical active user request?",
        observationUnit: "one expected-outcome slot in the reviewed task profile",
        direction: "Higher is better (radar plots the raw share).",
        counts: "Numerator: one slot per distinct normalized, non-question requirement clause in the canonical active user request that has an action-or-requirement cue and a recognized observable-check cue, capped at expected_outcome_count.",
        doesNotCount: "Denominator: exactly expected_outcome_count, not detected requirement clauses. Duplicate normalized clauses, questions, clauses outside the canonical active request, superseded requests, and checks added by the agent do not add slots; no declared count yields Unknown, never zero.",
        objectiveEvidence: "The value is a deterministic local, method-only comparison between the immutable reviewed task-profile revision and the canonical active user request; it is neither a model judgment nor objective proof of quality or task success.",
      },
      "prompt.deliverable_contract": {
        meaning: "Share of the exact deliverable slots declared in the reviewed task profile whose matching versioned cue appears in the canonical active user request.",
        question: "For each expected deliverable slot in the reviewed profile, does the canonical active user request contain its matching versioned cue?",
        observationUnit: "one expected deliverable slot in the reviewed task profile",
        direction: "Higher is better (radar plots the raw share).",
        counts: "Numerator: one configured expected deliverable slot whose matching versioned cue appears in the canonical active user request; each configured slot counts at most once.",
        doesNotCount: "Denominator: exactly the configured expected_deliverable_slots, not detected deliverable clauses. Unconfigured slots, cues outside the canonical active request, superseded requests, and agent prose do not count; no configured slots yields Unknown, never zero.",
        objectiveEvidence: "The value is a deterministic local, method-only comparison between the immutable reviewed task-profile revision and the canonical active user request; it is neither a model judgment nor objective proof of quality or task success.",
      },
    } as const;
    const historicalMeasurement = {
      "prompt.constraint_precision": {
        definitionVersion: 2,
        method: "Concrete constraint candidates divided by detected constraint clauses.",
        limitation: "Unknown task-specific constraints stay Unknown; absent constraints are never scored as zero.",
        objective: false,
      },
      "prompt.acceptance_testability": {
        definitionVersion: 2,
        method: "Requirements with check, threshold, comparison, or explicit pass cues divided by detected requirements.",
        limitation: "A test word is not proof of a complete or correct acceptance criterion.",
        objective: false,
      },
      "prompt.deliverable_contract": {
        definitionVersion: 3,
        method: "Detailed deliverable clauses divided by detected deliverable clauses.",
        limitation: "The v3 candidate avoids inventing a universal output-slot denominator.",
        objective: false,
      },
    } as const;
    const r5Measurement = {
      "prompt.constraint_precision": {
        definitionVersion: 2,
        method: "Configured expected constraint kinds with a matching versioned cue in the canonical active user request divided by the exact expected_constraint_kinds slots in the reviewed profile.",
        limitation: "This is lexical method-only evidence: an absent slot set stays Unknown, and a cue match does not prove that a constraint is correct or sufficient.",
        objective: false,
      },
      "prompt.acceptance_testability": {
        definitionVersion: 2,
        method: "Distinct normalized checkable requirement clauses owned by the canonical active user request, capped at expected_outcome_count, divided by that exact reviewed count.",
        limitation: "This is lexical method-only evidence: an absent reviewed count stays Unknown, duplicate clauses do not inflate the numerator, and a matched cue does not prove that an acceptance criterion is correct or complete.",
        objective: false,
      },
      "prompt.deliverable_contract": {
        definitionVersion: 3,
        method: "Configured expected deliverable slots with a matching versioned cue in the canonical active user request divided by the exact expected_deliverable_slots in the reviewed profile.",
        limitation: "This is lexical method-only evidence: an absent slot set stays Unknown, and a cue match does not prove that a deliverable contract is correct or sufficient.",
        objective: false,
      },
    } as const;

    for (const projection of [1, 2, 3, 4] as const) {
      for (const [key, entry] of Object.entries(historical)) {
        const resolved = metricHelpV2(key, "en", `metric-contract-v2-projection-${projection}`);
        expect(resolved?.definitionScope).toBe("historical_candidate");
        expect(resolved?.entry).toEqual(entry);
        expect(resolved?.measurement).toEqual(
          historicalMeasurement[key as keyof typeof historicalMeasurement],
        );
      }
    }
    for (const [key, entry] of Object.entries(r5)) {
      const resolved = metricHelpV2(key, "en", "metric-contract-v2-projection-5");
      expect(resolved?.definitionScope).toBe("r5_reviewed_profile");
      expect(resolved?.entry).toEqual(entry);
      expect(resolved?.measurement).toEqual(
        r5Measurement[key as keyof typeof r5Measurement],
      );
    }
  });

  it("keeps r1-r2 question-loop copy frozen and selects the exact explicit PLAN lifecycle from r3 onward", () => {
    const historical = {
      meaning: "Share of detected questions followed by a related opposite-role response and not reopened.",
      question: "Were detected questions followed by a related opposite-role response and not reopened?",
      observationUnit: "one detected question",
      direction: "Higher is better (radar plots the raw share).",
      counts: "A related closing response from the other role that is not reopened later.",
      doesNotCount: "Answer correctness; a linked response is not proof the answer is right.",
      objectiveEvidence: "No objective receipt backs the candidate value; it is a versioned lexical review candidate and never proof of quality or task success.",
    } as const;
    const explicitPlan = {
      meaning: "Share of documented agent PLAN episodes in the bounded analysis window explicitly closed by a later agent ACTION or VERIFICATION that names that exact PLAN message in supersedes_message_ids.",
      question: "For each documented agent PLAN message, does a later agent ACTION or VERIFICATION explicitly supersede that exact plan?",
      observationUnit: "one documented agent PLAN episode",
      direction: "Higher is better (radar plots the raw share).",
      counts: "Numerator: one PLAN episode with a later agent ACTION or VERIFICATION whose supersedes_message_ids names that exact PLAN message; the earliest valid closer owns the closure.",
      doesNotCount: "Denominator: exactly the provider-declared agent PLAN messages in the bounded window, not detected questions. Token overlap, topical similarity, adjacency, a shared event identity, unrelated later actions, and plans outside the window do not close an episode. An unclosed plan is right-censored pending, not failed; no PLAN capability or no observed PLAN yields Unknown, never zero or N/A.",
      objectiveEvidence: "The value comes from deterministic provider-declared message kinds and explicit supersedes_message_ids links in the bounded local window; no lexical similarity or model judgment supplies a closure, and the structural receipt is not objective proof that the plan or result was correct.",
    } as const;
    const historicalMeasurement = {
      definitionVersion: 2,
      method: "Closed question-response candidates divided by detected questions.",
      limitation: "A linked response does not establish that the answer is correct.",
      objective: false,
    } as const;
    const explicitPlanMeasurement = {
      definitionVersion: 2,
      method: "Documented agent PLAN episodes explicitly superseded by a later agent ACTION or VERIFICATION naming that exact PLAN message divided by the exact documented agent PLAN episodes in the bounded window.",
      limitation: "An unclosed plan is right-censored pending rather than failed; absent PLAN capability or an observed empty PLAN set remains Unknown, and an explicit link does not prove that the plan or result was correct.",
      objective: false,
    } as const;

    for (const projection of [1, 2] as const) {
      const resolved = metricHelpV2("logic.open_loop_closure", "en", `metric-contract-v2-projection-${projection}`);
      expect(resolved?.definitionScope).toBe("historical_candidate");
      expect(resolved?.entry).toEqual(historical);
      expect(resolved?.measurement).toEqual(historicalMeasurement);
    }
    for (const projection of [3, 4, 5] as const) {
      const resolved = metricHelpV2("logic.open_loop_closure", "en", `metric-contract-v2-projection-${projection}`);
      expect(resolved?.definitionScope).toBe("r3_explicit_plan_lifecycle");
      expect(resolved?.entry).toEqual(explicitPlan);
      expect(resolved?.measurement).toEqual(explicitPlanMeasurement);
    }
  });

  it("keeps r1-r3 collaboration copy frozen and selects exact confirmed lifecycle receipts for r4-r5", () => {
    const expected = {
      "collaboration.ambiguity_resolution": {
        historicalMeaning: "Share of detected ambiguity markers that were followed by a related clarification or explicit replacement.",
        historicalUnit: "one clause with an ambiguity marker",
        historicalMethod: "Related clarification or explicit replacement candidates divided by ambiguity-marker clauses.",
        meaning: "Share of the exact ambiguity opportunities in the authenticated local user's confirmed family enumeration whose confirmed ambiguity-resolution outcome is ambiguity_resolved.",
        unit: "one confirmed enumerated ambiguity opportunity",
        counts: "Numerator: one enumerated ambiguity opportunity with a confirmed ambiguity_resolution link whose outcome is ambiguity_resolved.",
        doesNotCount: "Denominator: exactly the authenticated local user's confirmed ambiguity enumeration, not detected ambiguity clauses. Proposed, rejected, undecided, or non-enumerated opportunities do not enter it; ambiguity_closed_unresolved is resolved not-met, while an enumerated opportunity without an outcome stays right-censored pending. Without an exact confirmed enumeration the metric is Unknown, never zero.",
        method: "Confirmed enumerated ambiguity opportunities with an ambiguity_resolution link whose outcome is ambiguity_resolved divided by the exact authenticated local-user confirmed ambiguity enumeration.",
        limitation: "A confirmed enumeration is mandatory; an enumerated opportunity without a confirmed outcome is right-censored pending, and local-user confirmation is not objective test proof.",
      },
      "collaboration.clarification_yield": {
        historicalMeaning: "Share of agent questions that received a later related, substantive user answer.",
        historicalUnit: "one agent question",
        historicalMethod: "Agent questions with a later related answer containing concrete task information divided by agent questions.",
        meaning: "Share of the exact clarification opportunities in the authenticated local user's confirmed family enumeration whose confirmed answer-incorporation outcome is clarification_incorporated.",
        unit: "one confirmed enumerated clarification opportunity",
        counts: "Numerator: one enumerated clarification opportunity with a confirmed clarification_answer_incorporation link whose outcome is clarification_incorporated.",
        doesNotCount: "Denominator: exactly the authenticated local user's confirmed clarification enumeration, not detected agent questions. Proposed, rejected, undecided, or non-enumerated opportunities do not enter it; clarification_not_incorporated is resolved not-met, while an enumerated opportunity without an outcome stays right-censored pending. Without an exact confirmed enumeration the metric is Unknown, never zero.",
        method: "Confirmed enumerated clarification opportunities with a clarification_answer_incorporation link whose outcome is clarification_incorporated divided by the exact authenticated local-user confirmed clarification enumeration.",
        limitation: "A confirmed enumeration is mandatory; an enumerated opportunity without a confirmed outcome is right-censored pending, and local-user confirmation is not objective test proof.",
      },
      "collaboration.exploration_conversion": {
        historicalMeaning: "Share of hypothesis or theorizing clauses that later converged into a related plan, decision, action, or verification item.",
        historicalUnit: "one hypothesis-marker clause",
        historicalMethod: "Hypothesis-marker clauses with a later related plan, decision, action, or verification item divided by hypotheses.",
        meaning: "Share of the exact exploration opportunities in the authenticated local user's confirmed family enumeration whose confirmed support-decision outcome is exploration_converted.",
        unit: "one confirmed enumerated exploration opportunity",
        counts: "Numerator: one enumerated exploration opportunity with a confirmed exploration_support_decision link whose outcome is exploration_converted.",
        doesNotCount: "Denominator: exactly the authenticated local user's confirmed exploration enumeration, not hypothesis-marker clauses. Proposed, rejected, undecided, or non-enumerated opportunities do not enter it; exploration_not_converted is resolved not-met, while an enumerated opportunity without an outcome stays right-censored pending. Without an exact confirmed enumeration the metric is Unknown, never zero.",
        method: "Confirmed enumerated exploration opportunities with an exploration_support_decision link whose outcome is exploration_converted divided by the exact authenticated local-user confirmed exploration enumeration.",
        limitation: "A confirmed enumeration is mandatory; an enumerated opportunity without a confirmed outcome is right-censored pending, and local-user confirmation is not objective test proof.",
      },
      "collaboration.scope_change_discipline": {
        historicalMeaning: "Share of explicit user scope-change clauses that were acknowledged in a related response or revised plan.",
        historicalUnit: "one explicit user scope-change clause",
        historicalMethod: "Acknowledged change candidates divided by explicit user scope-change clauses.",
        meaning: "Share of the exact scope-change opportunities in the authenticated local user's confirmed family enumeration whose confirmed impact-disposition outcome is scope_change_disciplined.",
        unit: "one confirmed enumerated scope-change opportunity",
        counts: "Numerator: one enumerated scope-change opportunity with a confirmed scope_change_impact_disposition link whose outcome is scope_change_disciplined.",
        doesNotCount: "Denominator: exactly the authenticated local user's confirmed scope-change enumeration, not detected scope-change clauses. Proposed, rejected, undecided, or non-enumerated opportunities do not enter it; scope_change_undisciplined is resolved not-met, while an enumerated opportunity without an outcome stays right-censored pending. Without an exact confirmed enumeration the metric is Unknown, never zero.",
        method: "Confirmed enumerated scope-change opportunities with a scope_change_impact_disposition link whose outcome is scope_change_disciplined divided by the exact authenticated local-user confirmed scope-change enumeration.",
        limitation: "A confirmed enumeration is mandatory; an enumerated opportunity without a confirmed outcome is right-censored pending, and local-user confirmation is not objective test proof.",
      },
      "collaboration.rework_candidate_rate": {
        historicalMeaning: "Share of user feedback clauses after an agent response that carry correction or misunderstanding markers.",
        historicalUnit: "one user feedback clause following an agent response",
        historicalMethod: "Correction-marker feedback clauses divided by user feedback clauses following an agent response.",
        meaning: "Share of the exact rework opportunities in the authenticated local user's confirmed family enumeration whose confirmed requirement-assessment outcome is rework_required; this is the raw lower-is-better rate.",
        unit: "one confirmed enumerated rework opportunity",
        counts: "Numerator: one enumerated rework opportunity with a confirmed rework_requirement_assessment link whose outcome is rework_required.",
        doesNotCount: "Denominator: exactly the authenticated local user's confirmed rework enumeration, not correction-marker feedback clauses. Proposed, rejected, undecided, or non-enumerated opportunities do not enter it; rework_not_required is resolved not-met, while an enumerated opportunity without an outcome stays right-censored pending. Without an exact confirmed enumeration the metric is Unknown, never zero.",
        method: "Confirmed enumerated rework opportunities with a rework_requirement_assessment link whose outcome is rework_required divided by the exact authenticated local-user confirmed rework enumeration.",
        limitation: "This publishes the raw lower-is-better rework-required rate. A confirmed enumeration is mandatory; an enumerated opportunity without a confirmed outcome is right-censored pending, and local-user confirmation is not objective test proof.",
      },
    } as const;

    for (const [key, copy] of Object.entries(expected)) {
      for (const projection of [1, 2, 3] as const) {
        const historical = metricHelpV2(key, "en", `metric-contract-v2-projection-${projection}`)!;
        expect(historical.definitionScope).toBe("historical_candidate");
        expect(historical.entry.meaning).toBe(copy.historicalMeaning);
        expect(historical.entry.observationUnit).toBe(copy.historicalUnit);
        expect(historical.measurement?.method).toBe(copy.historicalMethod);
      }
      for (const projection of [4, 5] as const) {
        const lifecycle = metricHelpV2(key, "en", `metric-contract-v2-projection-${projection}`)!;
        expect(lifecycle.definitionScope).toBe("r4_confirmed_lifecycle");
        expect(lifecycle.entry.meaning).toBe(copy.meaning);
        expect(lifecycle.entry.observationUnit).toBe(copy.unit);
        expect(lifecycle.entry.counts).toBe(copy.counts);
        expect(lifecycle.entry.doesNotCount).toBe(copy.doesNotCount);
        expect(lifecycle.entry.objectiveEvidence).toBe("Only content-free lifecycle records explicitly confirmed by an authenticated local user can supply the enumeration, opportunity, and family-specific outcome link; proposals, model judgments, and transcript wording alone are not evidence, and the confirmation is not objective test proof of task success.");
        expect(lifecycle.measurement).toEqual({
          definitionVersion: 2,
          method: copy.method,
          limitation: copy.limitation,
          objective: false,
        });
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
    evidenceAuthority: "Typed fixture receipts only",
  };

  it("produces distinct truthful copy per state without bands or invented factors", () => {
    const pending = metricInspectorSentences({ ...base, state: "unknown", explanationCode: "episode_horizon_open" });
    const pendingV2 = metricInspectorSentences({ ...base, state: "pending" });
    const na = metricInspectorSentences({ ...base, state: "not_applicable" });
    const unknown = metricInspectorSentences({ ...base, state: "unknown" });
    const abstained = metricInspectorSentences({ ...base, state: "abstained" });
    const suppressedSmall = metricInspectorSentences({ ...base, state: "suppressed", suppressionReason: "small_cohort" });
    const suppressedOverlap = metricInspectorSentences({ ...base, state: "suppressed", suppressionReason: "overlap_or_differencing" });
    const withheld = metricInspectorSentences({ ...base, state: "withheld", comparabilityState: "mixed_definition_versions" });
    const unavailable = metricInspectorSentences({ ...base, state: "unavailable", explanationCode: "capability_unavailable" });
    const objective = metricInspectorSentences({ ...base, metricKey: "outcome.agent_claim_grounding", label: "Agent claim grounding", state: "abstained" });
    const error = metricInspectorSentences({ ...base, state: "execution_error" });
    const missing = metricInspectorSentences({ ...base, state: "missing" });
    const experimental = metricInspectorSentences({ ...base, state: "unknown", experimentalVisible: true, experimentalMedian: 0.6 });
    const measured = metricInspectorSentences({ ...base, state: "known", numericValue: 0.5, numerator: 1, denominator: 2, experimentalFactorKeys: ["goal_cue"] });
    const zero = metricInspectorSentences({ ...base, state: "known", numericValue: 0, numerator: 0, denominator: 3 });
    const all = [pending, na, unknown, abstained, suppressedSmall, withheld, unavailable, error, missing, experimental, measured, zero];
    expect(new Set(all.map((sentence) => sentence.kind)).size).toBe(12);
    expect(pending.meaning).toMatch(/not a zero/);
    expect(pendingV2).toEqual(pending);
    expect(na.meaning).toMatch(/nothing to score/);
    expect(na.action).toMatch(/^No action for this window:/);
    expect(unknown.meaning).toMatch(/not a low value/);
    expect(unknown.meaning).not.toMatch(/No objective receipt/);
    expect(abstained.meaning).toMatch(/abstained instead of guessing/);
    expect(suppressedSmall.meaning).toMatch(/below the publication minimum/);
    expect(suppressedOverlap.meaning).toMatch(/minimum was met.*overlap or differencing/);
    expect(suppressedSmall.meaning).not.toBe(suppressedOverlap.meaning);
    expect(suppressedSmall.action).toMatch(/^No member-level action is justified:/);
    expect(withheld.meaning).toMatch(/mixes metric definition versions/);
    expect(withheld.action).toMatch(/^Do not compare or combine/);
    expect(unavailable.meaning).toMatch(/runtime does not expose/);
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
      expect(sentence.evidenceAuthority).toBe("Typed fixture receipts only");
    }
    expect(suppressedOverlap.suppressionReason).toBe("overlap_or_differencing");
    expect(withheld.comparabilityState).toBe("mixed_definition_versions");
    expect(unavailable.explanationCode).toBe("capability_unavailable");
  });

  it("never turns predictive factor keys into coaching evidence", () => {
    const withEstimate = metricInspectorSentences({
      ...base, state: "known", numericValue: 0.4, numerator: 2, denominator: 5,
      experimentalFactorKeys: ["goal_cue", "target_cue"], experimentalVisible: true, experimentalMedian: 0.5,
    });
    expect(withEstimate.meaning).not.toMatch(/goal cue|target cue|lowest for/);
    expect(withEstimate.meaning).toMatch(/not a validated quality band/);
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

  it("routes missing profile denominators to the shipped reviewed workflow", () => {
    for (const [metricKey, label] of [
      ["prompt.constraint_precision", "Constraint precision candidates"],
      ["prompt.acceptance_testability", "Acceptance testability"],
      ["prompt.deliverable_contract", "Deliverable contract"],
    ] as const) {
      const result = metricInspectorSentences({
        metricKey,
        label,
        projectionVersion: "metric-contract-v2-projection-5",
        direction: "higher_is_better",
        state: "unknown",
        numericValue: null,
        numerator: null,
        denominator: null,
        explanationCode: "opportunity_set_undetermined",
      });
      expect(result.meaning).toMatch(/reviewed task profile exposes no/i);
      expect(result.action).toMatch(/Reviewed metric denominators below/i);
      expect(result.action).toMatch(/immutable profile revision/i);
      expect(result.action).toMatch(/fresh analysis/i);
      expect(result.action).toMatch(/selected sealed r5 receipt exactly binds/i);
    }
    const historical = metricInspectorSentences({
      metricKey: "prompt.acceptance_testability",
      label: "Acceptance testability",
      projectionVersion: "metric-contract-v2-projection-4",
      direction: "higher_is_better",
      state: "unknown",
      numericValue: null,
      numerator: null,
      denominator: null,
      explanationCode: "opportunity_set_undetermined",
    });
    expect(historical.meaning).toMatch(/task profile did not declare the expected detected requirement clause set/i);
    expect(historical.action).toMatch(/separately confirmed task profile/i);
    expect(historical.action).not.toMatch(/selected sealed r5 receipt/i);
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
