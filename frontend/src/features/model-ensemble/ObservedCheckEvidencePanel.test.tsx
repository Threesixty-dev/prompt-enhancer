import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  ModelRequirementVerificationEvidenceBinding,
  ObservedCheckCandidateManifest,
  ObservedCheckCriterionReview,
  PromptEnhancerTransport,
  RequirementVerificationEvidenceSnapshot,
} from "../../shared/api/contracts";
import { ObservedCheckEvidencePanel } from "./ObservedCheckEvidencePanel";
import { parseRequirementVerificationEvidenceMutation } from "../../shared/api/requirementVerificationEvidenceContract";

const id = (character: string): string => character.repeat(64);
const SESSION = id("a");
const RUN = id("b");
const SET = id("c");
const REQUIREMENT = id("d");
const OPPORTUNITY = id("e");
const WINDOW = id("f");
const PLAN = id("0");
const PROPOSAL = id("1");
const PLAN_EVIDENCE = id("2");
const CANDIDATE = id("3");
const MANIFEST = id("4");
const RECEIPT = id("5");
const REVIEW_FINGERPRINT = id("6");
const RESULT = id("7");
const RESULT_FINGERPRINT = id("8");
const SECOND_OPPORTUNITY = id("f");
const SECOND_REQUIREMENT = id("e");
const SECOND_CANDIDATE = id("a");
const SECOND_REVIEW_RECEIPT = id("b");
const SECOND_RESULT = id("c");

function binding(): ModelRequirementVerificationEvidenceBinding {
  return {
    evidence_source: "persisted_evidence", requirement_plan_confirmation_id: PLAN,
    requirement_plan_proposal_id: PROPOSAL, requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
    requirement_plan_schema_version: "requirement-plan-evidence-v1", requirement_plan_policy_version: "reviewed-requirement-plan-v1",
    requirement_plan_review_rubric_version: "active-requirement-plan-review-rubric-v1", opportunity_count: 1,
    opportunity_set_fingerprint: SET, evidence_set_fingerprint: id("9"), through_revision: 1,
    authority_head_count: 0, objective_result_count: 0, native_acceptance_count: 0,
    resolved_opportunity_count: 0, met_requirement_count: 0,
    opportunity_issuer_version: "reviewed-r6-requirement-opportunity-issuer-v1",
    result_issuer_version: "local-objective-verification-result-issuer-v1",
    acceptance_issuer_version: "native-explicit-requirement-acceptance-issuer-v1",
    evidence_schema_version: "requirement-verification-evidence-v1", evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
    persistence_schema_version: "requirement-verification-persistence-v1", evidence_projection_version: "reviewed-requirement-verification-objective-projection-v1",
    objective_projection_version: "reviewed-requirement-verification-objective-projection-v1", binding_schema_version: "session-requirement-verification-evidence-binding-v1",
    binding_fingerprint: id("a"), local_only: true, content_persisted: false,
  };
}

function snapshot(withResult = false): RequirementVerificationEvidenceSnapshot {
  const value: RequirementVerificationEvidenceSnapshot = {
    revision: withResult ? 2 : 1, local_only: true, content_persisted: false,
    persistence_schema_version: "requirement-verification-persistence-v1", authority_heads: [],
    evidence: {
      evidence_schema_version: "requirement-verification-evidence-v1", evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
      projection_version: "reviewed-requirement-verification-objective-projection-v1", evidence_set_fingerprint: id(withResult ? "b" : "9"),
      local_only: true, content_persisted: false, verification_results: [], acceptance_authorities: [],
      opportunities: {
        session_id: SESSION, source_window_fingerprint: WINDOW, requirement_plan_confirmation_id: PLAN,
        requirement_plan_proposal_id: PROPOSAL, requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
        requirement_plan_schema_version: "requirement-plan-evidence-v1", requirement_plan_policy_version: "reviewed-requirement-plan-v1",
        requirement_plan_review_rubric_version: "active-requirement-plan-review-rubric-v1", opportunity_set_fingerprint: SET,
        opportunities: [{ opportunity_id: OPPORTUNITY, requirement_id: REQUIREMENT, requirement_index: 0, coordinate: { message_sequence: 1, clause_index: 0 } }],
        complete_active_requirement_enumeration: true, issuer_version: "reviewed-r6-requirement-opportunity-issuer-v1",
        evidence_schema_version: "requirement-verification-evidence-v1", evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
        local_only: true, content_persisted: false,
      },
    },
  };
  if (withResult) {
    value.evidence.verification_results = [{
      app_issued: true, authority_kind: "app_objective_verifier", content_persisted: false,
      evidence_policy_version: "app-issued-reviewed-requirement-verification-v1", evidence_schema_version: "requirement-verification-evidence-v1",
      issuer_version: "local-objective-verification-result-issuer-v1", local_only: true, method: "test", observed_sequence: 3,
      opportunity_id: OPPORTUNITY, opportunity_set_fingerprint: SET, outcome: "passed", receipt_reference_ids: [CANDIDATE, RECEIPT],
      requirement_id: REQUIREMENT, result_fingerprint: RESULT_FINGERPRINT, result_id: RESULT,
    }];
    value.authority_heads = [{ authority_record_id: RESULT, kind: "objective_result", opportunity_id: OPPORTUNITY, revision: 2 }];
  }
  return value;
}

function manifest(): ObservedCheckCandidateManifest {
  return {
    session_id: SESSION, opportunity_set_fingerprint: SET, opportunity_id: OPPORTUNITY, requirement_id: REQUIREMENT,
    expected_source_run_id: RUN, source_window_fingerprint: WINDOW, requirement_plan_confirmation_id: PLAN,
    requirement_plan_proposal_id: PROPOSAL, expected_predecessor_authority_id: null, through_revision: 1,
    candidate_manifest_fingerprint: MANIFEST,
    candidates: [{ candidate_id: CANDIDATE, observed_sequence: 3, check_kind: "test", observed_outcome: "passed", provider_execution_status: "completed", exit_code: 0, source_completion_schema_version: "observed-check-completion-v1", outcome_interpreter_version: "pytest-exit-status-v1", classifier_version: "local-command-rules-v1", normalizer_version: "strict-shell-free-v2", rule_id: "test.pytest", local_only: true, content_persisted: false }],
    schema_version: "requirement-observed-check-review-v1", local_only: true, content_persisted: false,
  };
}

function largeManifest(): ObservedCheckCandidateManifest {
  const value = manifest();
  value.candidates = Array.from({ length: 26 }, (_, index) => ({
    ...value.candidates[0]!,
    candidate_id: index.toString(16).padStart(2, "0").repeat(32),
    observed_sequence: index + 1,
  }));
  return value;
}

function secondOpportunitySnapshot(): RequirementVerificationEvidenceSnapshot {
  const value = snapshot();
  value.evidence.opportunities.opportunities.push({ opportunity_id: SECOND_OPPORTUNITY, requirement_id: SECOND_REQUIREMENT, requirement_index: 1, coordinate: { message_sequence: 1, clause_index: 1 } });
  return value;
}

function secondManifest(): ObservedCheckCandidateManifest {
  const value = manifest();
  value.opportunity_id = SECOND_OPPORTUNITY;
  value.requirement_id = SECOND_REQUIREMENT;
  value.candidate_manifest_fingerprint = id("0");
  value.candidates = [{ ...value.candidates[0]!, candidate_id: SECOND_CANDIDATE, observed_outcome: "check_failed", exit_code: 1 }];
  return value;
}

function secondReview(): ObservedCheckCriterionReview {
  const value = review();
  value.opportunity_id = SECOND_OPPORTUNITY;
  value.requirement_id = SECOND_REQUIREMENT;
  value.candidate_manifest_fingerprint = id("0");
  value.candidate = secondManifest().candidates[0]!;
  value.review_receipt_id = SECOND_REVIEW_RECEIPT;
  value.review_fingerprint = id("c");
  value.check_effect_preview = "exit 1";
  return value;
}

function multiOpportunityMutation(): { applied: true; snapshot: RequirementVerificationEvidenceSnapshot } {
  const value = secondOpportunitySnapshot();
  value.revision = 4;
  const first = snapshot(true).evidence.verification_results[0]!;
  const selected = {
    ...first,
    opportunity_id: SECOND_OPPORTUNITY,
    requirement_id: SECOND_REQUIREMENT,
    result_id: SECOND_RESULT,
    result_fingerprint: id("d"),
    method: "test" as const,
    observed_sequence: 3,
    outcome: "failed" as const,
    receipt_reference_ids: [SECOND_CANDIDATE, SECOND_REVIEW_RECEIPT],
  };
  value.evidence.verification_results = [first, selected];
  value.authority_heads = [
    { authority_record_id: first.result_id, kind: "objective_result", opportunity_id: first.opportunity_id, revision: 4 },
    { authority_record_id: selected.result_id, kind: "objective_result", opportunity_id: SECOND_OPPORTUNITY, revision: 3 },
  ];
  return { applied: true, snapshot: value };
}

function review(): ObservedCheckCriterionReview {
  return {
    session_id: SESSION, opportunity_set_fingerprint: SET, opportunity_id: OPPORTUNITY, requirement_id: REQUIREMENT,
    expected_source_run_id: RUN, source_window_fingerprint: WINDOW, requirement_plan_confirmation_id: PLAN,
    requirement_plan_proposal_id: PROPOSAL, expected_predecessor_authority_id: null, through_revision: 1,
    candidate_manifest_fingerprint: MANIFEST, candidate: manifest().candidates[0]!, requirement_text: "Synthetic requirement criterion",
    check_tool_name: "pytest", check_invocation_preview: "pytest -q synthetic_test.py", check_effect_preview: "exit 0",
    review_receipt_id: RECEIPT, review_fingerprint: REVIEW_FINGERPRINT, review_expires_at: new Date(Date.now() + 60_000).toISOString(),
    full_criterion_coverage_acknowledgement_required: true, objective_result_issued: false,
    schema_version: "requirement-observed-check-review-v1", local_only: true, content_persisted: false,
  };
}

type TestTransport = Pick<PromptEnhancerTransport, "preflightRequirementVerificationObservedCheck" | "reviewRequirementVerificationObservedCheck" | "issueRequirementVerificationObservedCheck" | "getRequirementVerificationEvidenceSnapshot">;

function transport(overrides: Partial<TestTransport> = {}): TestTransport {
  return {
    preflightRequirementVerificationObservedCheck: vi.fn().mockResolvedValue(manifest()),
    reviewRequirementVerificationObservedCheck: vi.fn().mockResolvedValue(review()),
    issueRequirementVerificationObservedCheck: vi.fn().mockResolvedValue({ applied: true, snapshot: snapshot(true) }),
    ...overrides,
  };
}

function renderPanel(testTransport: TestTransport, nativeAvailable: boolean | null = true) {
  return render(<ObservedCheckEvidencePanel binding={binding()} nativeAvailable={nativeAvailable} onEvidenceChanged={vi.fn()} sessionId={SESSION} snapshot={snapshot()} sourceRunId={RUN} transport={testTransport} />);
}

describe("ObservedCheckEvidencePanel", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps provider outcome separate and issues only after explicit full-criterion acknowledgement", async () => {
    const testTransport = transport();
    renderPanel(testTransport);
    fireEvent.click(screen.getByRole("button", { name: "Find eligible direct-pytest checks" }));
    await screen.findByText("passed", { exact: true });
    fireEvent.click(screen.getByRole("button", { name: "Review exact criterion" }));
    await screen.findByText("Synthetic requirement criterion");
    const issue = screen.getByRole("button", { name: "Issue server-derived observed result" });
    expect(issue).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /acknowledge full-criterion coverage/i }));
    expect(issue).not.toBeDisabled();
    fireEvent.click(issue);
    await screen.findByText(/Server-issued observed test result: passed/i);
    expect(testTransport.issueRequirementVerificationObservedCheck).toHaveBeenCalledWith(
      SESSION, SET, OPPORTUNITY, CANDIDATE,
      expect.objectContaining({ full_criterion_coverage_acknowledged: true, confirmation: "issue_exact_local_requirement_observed_check_result" }),
      expect.stringContaining("observed-check-"), expect.any(AbortSignal),
    );
  });

  it("does not offer an alternate path when native capability is unknown or unavailable", async () => {
    const testTransport = transport();
    renderPanel(testTransport, false);
    fireEvent.click(screen.getByRole("button", { name: "Find eligible direct-pytest checks" }));
    await screen.findByText("passed", { exact: true });
    const reviewButton = screen.getByRole("button", { name: "Review exact criterion" });
    expect(reviewButton).toBeDisabled();
    const unavailable = screen.getByText(/no alternate result path/i);
    expect(unavailable.closest("[role=status]")).not.toBeNull();
    expect(testTransport.reviewRequirementVerificationObservedCheck).not.toHaveBeenCalled();
  });

  it("ignores a late preflight response from a replaced transport owner", async () => {
    let resolveA: ((value: ObservedCheckCandidateManifest) => void) | undefined;
    const first = transport({ preflightRequirementVerificationObservedCheck: vi.fn().mockImplementation(() => new Promise((resolve) => { resolveA = resolve; })) });
    const second = transport();
    const view = renderPanel(first);
    fireEvent.click(screen.getByRole("button", { name: "Find eligible direct-pytest checks" }));
    view.rerender(<ObservedCheckEvidencePanel binding={binding()} nativeAvailable={true} onEvidenceChanged={vi.fn()} sessionId={SESSION} snapshot={snapshot()} sourceRunId={RUN} transport={second} />);
    resolveA?.(manifest());
    await waitFor(() => expect(screen.queryByText(/provider-reported result/i)).not.toBeInTheDocument());
    expect(second.preflightRequirementVerificationObservedCheck).not.toHaveBeenCalled();
  });

  it("rejects a manifest whose requirement or source window is not the selected authority", async () => {
    const foreign = manifest();
    foreign.requirement_id = id("a");
    const testTransport = transport({ preflightRequirementVerificationObservedCheck: vi.fn().mockResolvedValue(foreign) });
    renderPanel(testTransport);
    fireEvent.click(screen.getByRole("button", { name: "Find eligible direct-pytest checks" }));
    await screen.findByRole("alert");
    expect(screen.queryByText("Observed sequence 3")).not.toBeInTheDocument();
  });

  it("rejects an issued receipt that does not reference the selected observed candidate", async () => {
    const foreignResult = snapshot(true);
    foreignResult.evidence.verification_results[0]!.receipt_reference_ids = [RECEIPT];
    const testTransport = transport({ issueRequirementVerificationObservedCheck: vi.fn().mockResolvedValue({ applied: true, snapshot: foreignResult }) });
    renderPanel(testTransport);
    fireEvent.click(screen.getByRole("button", { name: "Find eligible direct-pytest checks" }));
    await screen.findByText("passed", { exact: true });
    fireEvent.click(screen.getByRole("button", { name: "Review exact criterion" }));
    await screen.findByText("Synthetic requirement criterion");
    fireEvent.click(screen.getByRole("checkbox", { name: /acknowledge full-criterion coverage/i }));
    fireEvent.click(screen.getByRole("button", { name: "Issue server-derived observed result" }));
    await screen.findByRole("alert");
    expect(screen.queryByText(/Server-issued observed test result/i)).not.toBeInTheDocument();
  });

  it("bounds a hung native review request and leaves no result assumed", async () => {
    const testTransport = transport({ reviewRequirementVerificationObservedCheck: vi.fn().mockImplementation(() => new Promise(() => undefined)) });
    renderPanel(testTransport);
    fireEvent.click(screen.getByRole("button", { name: "Find eligible direct-pytest checks" }));
    await screen.findByText("passed", { exact: true });
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Review exact criterion" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/did not settle within 10 seconds/i);
    expect(screen.queryByText("Synthetic requirement criterion")).not.toBeInTheDocument();
  });

  it("pages and filters large candidate manifests while preserving observed sequence identity", async () => {
    const testTransport = transport({ preflightRequirementVerificationObservedCheck: vi.fn().mockResolvedValue(largeManifest()) });
    renderPanel(testTransport);
    fireEvent.click(screen.getByRole("button", { name: "Find eligible direct-pytest checks" }));
    expect(await screen.findByText(/^Observed sequence 1 ·/)).toBeVisible();
    expect(screen.queryByText(/^Observed sequence 26 ·/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next check page" }));
    expect(await screen.findByText(/^Observed sequence 26 ·/)).toBeVisible();
    fireEvent.change(screen.getByRole("textbox", { name: "Filter eligible checks" }), { target: { value: "26" } });
    expect(screen.getByText(/^Observed sequence 26 ·/)).toBeVisible();
    expect(screen.queryByText(/^Observed sequence 25 ·/)).not.toBeInTheDocument();
  });

  it("uses the selected candidate outcome when another opportunity has a newer head", async () => {
    const received = vi.fn();
    const testTransport = transport({
      preflightRequirementVerificationObservedCheck: vi.fn().mockResolvedValue(secondManifest()),
      reviewRequirementVerificationObservedCheck: vi.fn().mockResolvedValue(secondReview()),
      issueRequirementVerificationObservedCheck: vi.fn().mockResolvedValue(multiOpportunityMutation()),
    });
    const selectedSnapshot = secondOpportunitySnapshot();
    expect(() => parseRequirementVerificationEvidenceMutation(multiOpportunityMutation(), SESSION)).not.toThrow();
    render(<ObservedCheckEvidencePanel binding={binding()} nativeAvailable={true} onEvidenceChanged={received} sessionId={SESSION} snapshot={selectedSnapshot} sourceRunId={RUN} transport={testTransport} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Find eligible direct-pytest checks" })[1]!);
    await screen.findByText("check failed", { exact: true });
    fireEvent.click(screen.getByRole("button", { name: "Review exact criterion" }));
    await screen.findByText("Synthetic requirement criterion");
    fireEvent.click(screen.getByRole("checkbox", { name: /acknowledge full-criterion coverage/i }));
    fireEvent.click(screen.getByRole("button", { name: "Issue server-derived observed result" }));
    await screen.findByText(/Server-issued observed test result: failed/i);
    expect(received.mock.calls[0]?.[2]).toBe(SECOND_OPPORTUNITY);
  });

  it("propagates an explicitly reconciled current snapshot to its owner callback", async () => {
    const received = vi.fn();
    const testTransport = transport({
      issueRequirementVerificationObservedCheck: vi.fn().mockImplementation(() => new Promise(() => undefined)),
      getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(snapshot(true)),
    });
    render(<ObservedCheckEvidencePanel binding={binding()} nativeAvailable={true} onEvidenceChanged={received} sessionId={SESSION} snapshot={snapshot()} sourceRunId={RUN} transport={testTransport} />);
    fireEvent.click(screen.getByRole("button", { name: "Find eligible direct-pytest checks" }));
    await screen.findByText("passed", { exact: true });
    fireEvent.click(screen.getByRole("button", { name: "Review exact criterion" }));
    await screen.findByText("Synthetic requirement criterion");
    fireEvent.click(screen.getByRole("checkbox", { name: /acknowledge full-criterion coverage/i }));
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Issue server-derived observed result" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    fireEvent.click(screen.getByRole("button", { name: "Inspect current evidence" }));
    await act(async () => { await Promise.resolve(); });
    expect(received.mock.calls[0]?.[1]).toMatchObject({ revision: 2 });
    expect(received.mock.calls[0]?.[2]).toBe(OPPORTUNITY);
  });
});
