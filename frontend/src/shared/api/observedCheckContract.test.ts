import { describe, expect, it } from "vitest";
import {
  ObservedCheckPayloadError,
  parseObservedCheckCandidateManifest,
  parseObservedCheckCriterionReview,
  parseObservedCheckAuthorityProvenance,
} from "./observedCheckContract";

const id = (character: string): string => character.repeat(64);
const SESSION = id("a");

function candidate() {
  return {
    candidate_id: id("b"),
    observed_sequence: 3,
    check_kind: "test" as const,
    observed_outcome: "passed" as const,
    provider_execution_status: "completed" as const,
    exit_code: 0 as const,
    source_completion_schema_version: "observed-check-completion-v1" as const,
    outcome_interpreter_version: "pytest-exit-status-v1" as const,
    classifier_version: "local-command-rules-v1" as const,
    normalizer_version: "strict-shell-free-v2" as const,
    rule_id: "test.pytest" as const,
    local_only: true as const,
    content_persisted: false as const,
  };
}

function manifest() {
  return {
    session_id: SESSION,
    opportunity_set_fingerprint: id("c"),
    opportunity_id: id("d"),
    requirement_id: id("e"),
    expected_source_run_id: id("f"),
    source_window_fingerprint: id("0"),
    requirement_plan_confirmation_id: id("1"),
    requirement_plan_proposal_id: id("2"),
    expected_predecessor_authority_id: null,
    through_revision: 7,
    candidate_manifest_fingerprint: id("3"),
    candidates: [candidate()],
    schema_version: "requirement-observed-check-review-v1" as const,
    local_only: true as const,
    content_persisted: false as const,
  };
}

function review() {
  return {
    session_id: SESSION,
    opportunity_set_fingerprint: id("c"),
    opportunity_id: id("d"),
    requirement_id: id("e"),
    expected_source_run_id: id("f"),
    source_window_fingerprint: id("0"),
    requirement_plan_confirmation_id: id("1"),
    requirement_plan_proposal_id: id("2"),
    expected_predecessor_authority_id: null,
    through_revision: 7,
    candidate_manifest_fingerprint: id("3"),
    candidate: candidate(),
    requirement_text: "Synthetic requirement clause",
    check_tool_name: "pytest",
    check_invocation_preview: "pytest -q synthetic_test.py",
    check_effect_preview: "exit 0",
    review_receipt_id: id("4"),
    review_fingerprint: id("5"),
    review_expires_at: new Date(Date.now() + 60_000).toISOString(),
    full_criterion_coverage_acknowledgement_required: true as const,
    objective_result_issued: false as const,
    schema_version: "requirement-observed-check-review-v1" as const,
    local_only: true as const,
    content_persisted: false as const,
  };
}

function provenance() {
  return {
    authority_record_id: id("6"), session_id: SESSION, opportunity_set_fingerprint: id("c"),
    opportunity_id: id("d"), requirement_id: id("e"), source_run_id: id("f"),
    source_window_fingerprint: id("0"), requirement_plan_confirmation_id: id("1"),
    requirement_plan_proposal_id: id("2"), candidate_manifest_fingerprint: id("3"),
    source_reference_id: id("7"), coverage_review_reference_id: id("8"), observed_sequence: 3,
    check_kind: "test" as const, provider_execution_status: "completed" as const,
    observed_outcome: "passed" as const, exit_code: 0 as const,
    source_completion_schema_version: "observed-check-completion-v1" as const,
    outcome_interpreter_version: "pytest-exit-status-v1" as const,
    classifier_version: "local-command-rules-v1" as const,
    normalizer_version: "strict-shell-free-v2" as const, rule_id: "test.pytest" as const,
    coverage_review_version: "native-full-criterion-coverage-v1" as const,
    full_criterion_coverage_acknowledged: true as const, provenance_fingerprint: id("9"),
    schema_version: "observed-check-authority-provenance-v1" as const,
    local_only: true as const, content_persisted: false as const,
  };
}

describe("observed check review contract", () => {
  it("accepts server-derived direct-pytest candidates and exact native review", () => {
    expect(parseObservedCheckCandidateManifest(manifest(), SESSION)).toEqual(manifest());
    const value = review();
    expect(parseObservedCheckCriterionReview(value, SESSION)).toEqual(value);
  });

  it.each([
    (value: ReturnType<typeof manifest>) => { value.candidates[0].observed_sequence = 0.5; },
    (value: ReturnType<typeof manifest>) => { value.candidates[0].exit_code = 2 as never; },
    (value: ReturnType<typeof manifest>) => { value.candidates[0].observed_outcome = "unknown" as never; },
    (value: ReturnType<typeof manifest>) => { value.candidates.push({ ...value.candidates[0], observed_sequence: 4 }); },
    (value: ReturnType<typeof manifest>) => { (value as Record<string, unknown>).extra = true; },
  ])("rejects candidate payload drift", (alter) => {
    const value = structuredClone(manifest());
    alter(value);
    expect(() => parseObservedCheckCandidateManifest(value, SESSION)).toThrow(ObservedCheckPayloadError);
  });

  it.each([
    (value: ReturnType<typeof review>) => { value.objective_result_issued = true as never; },
    (value: ReturnType<typeof review>) => { value.full_criterion_coverage_acknowledgement_required = false as never; },
    (value: ReturnType<typeof review>) => { value.session_id = id("6"); },
    (value: ReturnType<typeof review>) => { value.review_expires_at = "2020-01-01T00:00:00Z"; },
    (value: ReturnType<typeof review>) => { (value as Record<string, unknown>).raw_text = "should not cross the boundary"; },
  ])("rejects review authority drift", (alter) => {
    const value = structuredClone(review());
    alter(value);
    expect(() => parseObservedCheckCriterionReview(value, SESSION)).toThrow(ObservedCheckPayloadError);
  });

  it("accepts a semantically identical candidate with reordered object keys", () => {
    const value = review();
    value.candidate = Object.fromEntries(
      Object.entries(value.candidate).reverse(),
    ) as typeof value.candidate;
    expect(parseObservedCheckCriterionReview(value, SESSION).candidate.candidate_id).toBe(id("b"));
  });

  it("accepts content-free observed provenance for the exact authority record", () => {
    const value = provenance();
    expect(parseObservedCheckAuthorityProvenance(value, SESSION, value.authority_record_id)).toEqual(value);
  });

  it.each([
    (value: ReturnType<typeof provenance>) => { value.session_id = id("9"); },
    (value: ReturnType<typeof provenance>) => { value.authority_record_id = id("a"); },
    (value: ReturnType<typeof provenance>) => { value.observed_outcome = "check_failed" as never; },
    (value: ReturnType<typeof provenance>) => { value.exit_code = 1 as never; },
    (value: ReturnType<typeof provenance>) => { (value as Record<string, unknown>).raw_command = "never persisted"; },
  ])("rejects provenance identity, outcome, and content drift", (alter) => {
    const value = structuredClone(provenance());
    alter(value);
    expect(() => parseObservedCheckAuthorityProvenance(value, SESSION, id("6"))).toThrow(ObservedCheckPayloadError);
  });
});
