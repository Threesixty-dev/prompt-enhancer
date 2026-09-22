import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  ModelRequirementVerificationEvidenceBinding,
  ObservedCheckAuthorityProvenance,
  ObservedCheckCandidateManifest,
  ObservedCheckCriterionReview,
  RequirementVerificationEvidenceSnapshot,
} from "../../shared/api/contracts";
import { RequirementVerificationEvidencePanel } from "./RequirementVerificationEvidencePanel";

const SESSION = "a".repeat(64);
const RUN = "b".repeat(64);
const PLAN_CONFIRMATION = "c".repeat(64);
const PLAN_PROPOSAL = "d".repeat(64);
const PLAN_FINGERPRINT = "e".repeat(64);
const OPPORTUNITIES = "f".repeat(64);
const EVIDENCE = "1".repeat(64);
const OBJECTIVE_RESULT = "6".repeat(64);
const RECEIPT = "7".repeat(64);
const RESULT_FINGERPRINT = "8".repeat(64);
const PROVENANCE_SOURCE = "0".repeat(64);
const PROVENANCE_COVERAGE = "9".repeat(64);

function binding(source: "awaiting_evidence" | "persisted_evidence"): ModelRequirementVerificationEvidenceBinding {
  return {
    evidence_source: source,
    requirement_plan_confirmation_id: PLAN_CONFIRMATION,
    requirement_plan_proposal_id: PLAN_PROPOSAL,
    requirement_plan_evidence_fingerprint: PLAN_FINGERPRINT,
    requirement_plan_schema_version: "requirement-plan-evidence-v1",
    requirement_plan_policy_version: "reviewed-requirement-plan-v1",
    requirement_plan_review_rubric_version: "active-requirement-plan-review-rubric-v1",
    opportunity_count: 1,
    opportunity_set_fingerprint: OPPORTUNITIES,
    evidence_set_fingerprint: source === "persisted_evidence" ? EVIDENCE : null,
    through_revision: source === "persisted_evidence" ? 1 : null,
    authority_head_count: source === "persisted_evidence" ? 0 : 0,
    objective_result_count: source === "persisted_evidence" ? 0 : 0,
    native_acceptance_count: source === "persisted_evidence" ? 0 : 0,
    resolved_opportunity_count: source === "persisted_evidence" ? 0 : 0,
    met_requirement_count: source === "persisted_evidence" ? 0 : 0,
    opportunity_issuer_version: "reviewed-r6-requirement-opportunity-issuer-v1",
    result_issuer_version: "local-objective-verification-result-issuer-v1",
    acceptance_issuer_version: "native-explicit-requirement-acceptance-issuer-v1",
    evidence_schema_version: "requirement-verification-evidence-v1",
    evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
    persistence_schema_version: "requirement-verification-persistence-v1",
    evidence_projection_version: "reviewed-requirement-verification-objective-projection-v1",
    objective_projection_version: "reviewed-requirement-verification-objective-projection-v1",
    binding_schema_version: "session-requirement-verification-evidence-binding-v1",
    binding_fingerprint: "2".repeat(64), local_only: true, content_persisted: false,
  };
}

function snapshot(): RequirementVerificationEvidenceSnapshot {
  return {
    revision: 1, local_only: true, content_persisted: false,
    persistence_schema_version: "requirement-verification-persistence-v1",
    authority_heads: [],
    evidence: {
      evidence_schema_version: "requirement-verification-evidence-v1",
      evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
      projection_version: "reviewed-requirement-verification-objective-projection-v1",
      evidence_set_fingerprint: EVIDENCE, local_only: true, content_persisted: false,
      verification_results: [], acceptance_authorities: [],
      opportunities: {
        session_id: SESSION, source_window_fingerprint: "3".repeat(64),
        requirement_plan_confirmation_id: PLAN_CONFIRMATION,
        requirement_plan_proposal_id: PLAN_PROPOSAL,
        requirement_plan_evidence_fingerprint: PLAN_FINGERPRINT,
        requirement_plan_schema_version: "requirement-plan-evidence-v1",
        requirement_plan_policy_version: "reviewed-requirement-plan-v1",
        requirement_plan_review_rubric_version: "active-requirement-plan-review-rubric-v1",
        opportunity_set_fingerprint: OPPORTUNITIES,
        opportunities: [{ opportunity_id: "4".repeat(64), requirement_id: "5".repeat(64), requirement_index: 0, coordinate: { message_sequence: 1, clause_index: 0 } }],
        complete_active_requirement_enumeration: true,
        issuer_version: "reviewed-r6-requirement-opportunity-issuer-v1",
        evidence_schema_version: "requirement-verification-evidence-v1",
        evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
        local_only: true, content_persisted: false,
      },
    },
  };
}

function advancedAwaitingSnapshot(): RequirementVerificationEvidenceSnapshot {
  const next = snapshot();
  const opportunity = next.evidence.opportunities.opportunities[0]!;
  next.revision = 2;
  next.evidence.evidence_set_fingerprint = "9".repeat(64);
  next.evidence.verification_results = [{
    app_issued: true,
    authority_kind: "app_objective_verifier",
    content_persisted: false,
    evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
    evidence_schema_version: "requirement-verification-evidence-v1",
    issuer_version: "local-objective-verification-result-issuer-v1",
    local_only: true,
    method: "test",
    observed_sequence: 0,
    opportunity_id: opportunity.opportunity_id,
    opportunity_set_fingerprint: OPPORTUNITIES,
    outcome: "passed",
    receipt_reference_ids: [RECEIPT],
    requirement_id: opportunity.requirement_id,
    result_fingerprint: RESULT_FINGERPRINT,
    result_id: OBJECTIVE_RESULT,
  }];
  next.authority_heads = [{
    authority_record_id: OBJECTIVE_RESULT,
    kind: "objective_result",
    opportunity_id: opportunity.opportunity_id,
    revision: 2,
  }];
  return next;
}

function provenanceSnapshot(): RequirementVerificationEvidenceSnapshot {
  const next = snapshot();
  const opportunity = next.evidence.opportunities.opportunities[0]!;
  next.revision = 2;
  next.evidence.evidence_set_fingerprint = "9".repeat(64);
  next.evidence.verification_results = [{
    app_issued: true, authority_kind: "app_objective_verifier", content_persisted: false,
    evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
    evidence_schema_version: "requirement-verification-evidence-v1",
    issuer_version: "local-objective-verification-result-issuer-v1", local_only: true,
    method: "test", observed_sequence: 3, opportunity_id: opportunity.opportunity_id,
    opportunity_set_fingerprint: OPPORTUNITIES, outcome: "passed",
    receipt_reference_ids: [PROVENANCE_SOURCE, PROVENANCE_COVERAGE], requirement_id: opportunity.requirement_id,
    result_fingerprint: RESULT_FINGERPRINT, result_id: OBJECTIVE_RESULT,
  }];
  next.authority_heads = [{ authority_record_id: OBJECTIVE_RESULT, kind: "objective_result", opportunity_id: opportunity.opportunity_id, revision: 2 }];
  return next;
}

function provenance(): ObservedCheckAuthorityProvenance {
  const opportunity = snapshot().evidence.opportunities.opportunities[0]!;
  return {
    authority_record_id: OBJECTIVE_RESULT, session_id: SESSION, opportunity_set_fingerprint: OPPORTUNITIES,
    opportunity_id: opportunity.opportunity_id, requirement_id: opportunity.requirement_id, source_run_id: RUN,
    source_window_fingerprint: "3".repeat(64), requirement_plan_confirmation_id: PLAN_CONFIRMATION,
    requirement_plan_proposal_id: PLAN_PROPOSAL, candidate_manifest_fingerprint: "4".repeat(64),
    source_reference_id: PROVENANCE_SOURCE, coverage_review_reference_id: PROVENANCE_COVERAGE,
    observed_sequence: 3, check_kind: "test", provider_execution_status: "completed",
    observed_outcome: "passed", exit_code: 0, source_completion_schema_version: "observed-check-completion-v1",
    outcome_interpreter_version: "pytest-exit-status-v1", classifier_version: "local-command-rules-v1",
    normalizer_version: "strict-shell-free-v2", rule_id: "test.pytest",
    coverage_review_version: "native-full-criterion-coverage-v1", full_criterion_coverage_acknowledged: true,
    provenance_fingerprint: "5".repeat(64), schema_version: "observed-check-authority-provenance-v1",
    local_only: true, content_persisted: false,
  };
}

function provenanceBinding(): ModelRequirementVerificationEvidenceBinding {
  return {
    ...binding("persisted_evidence"), evidence_set_fingerprint: "9".repeat(64), through_revision: 2,
    authority_head_count: 1, objective_result_count: 1, resolved_opportunity_count: 1, met_requirement_count: 1,
  };
}

describe("RequirementVerificationEvidencePanel", () => {
  it("retains an uncertain native outcome for explicit current reconciliation without rewriting the selected snapshot", async () => {
    const base = snapshot(); const op = base.evidence.opportunities.opportunities[0]!; const current = snapshot(); current.revision = 2; current.evidence.evidence_set_fingerprint = "9".repeat(64);
    current.evidence.acceptance_authorities = [{ acceptance_id: "c".repeat(64), acceptance_fingerprint: "d".repeat(64), authority_kind: "native_user_acceptance", confirmation_id: "e".repeat(64), content_persisted: false, evidence_policy_version: "app-issued-reviewed-requirement-verification-v1", evidence_schema_version: "requirement-verification-evidence-v1", issuer_version: "native-explicit-requirement-acceptance-issuer-v1", local_only: true, opportunity_id: op.opportunity_id, opportunity_set_fingerprint: OPPORTUNITIES, outcome: "accepted", owned_native_action: true, requirement_id: op.requirement_id }];
    current.authority_heads = [{ authority_record_id: "c".repeat(64), kind: "native_acceptance", opportunity_id: op.opportunity_id, revision: 2 }];
    const get = vi.fn().mockResolvedValueOnce(base).mockResolvedValueOnce(current);
    const review = { schema_version: "requirement-verification-native-review-v1" as const, policy_version: "current-r8-reviewed-r6-clause-only-v1" as const, session_id: SESSION, opportunity_set_fingerprint: OPPORTUNITIES, opportunity_id: op.opportunity_id, requirement_id: op.requirement_id, coordinate: op.coordinate, expected_source_run_id: RUN, source_window_fingerprint: "3".repeat(64), requirement_plan_confirmation_id: PLAN_CONFIRMATION, requirement_plan_proposal_id: PLAN_PROPOSAL, expected_predecessor_authority_id: null, through_revision: 1, review_receipt_id: "a".repeat(64), review_fingerprint: "b".repeat(64), review_expires_at: new Date(Date.now() + 60_000).toISOString(), requirement_text: "Synthetic clause", local_only: true as const, content_persisted: false as const };
    const changed = vi.fn();
    render(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={changed} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={{ getRequirementVerificationEvidenceSnapshot: get, getUserPresenceCapability: vi.fn().mockResolvedValue({ contract_version: "native-user-presence-capability-v1", confirmation_available: true, mode: "native_bridge_bound_token" }), reviewRequirementVerificationOpportunity: vi.fn().mockResolvedValue(review), appendRequirementVerificationAcceptance: vi.fn().mockRejectedValue(new Error("uncertain")) }} />);
    const read = await screen.findByRole("button", { name: "Read exact requirement" }); await waitFor(() => expect(read).not.toBeDisabled()); fireEvent.click(read); await screen.findByText("Synthetic clause"); fireEvent.click(screen.getByRole("checkbox", { name: /I have read/i })); fireEvent.click(screen.getByRole("radio", { name: "accepted" })); fireEvent.click(screen.getByRole("button", { name: "Confirm human disposition" }));
    const reconcile = await screen.findByRole("button", { name: "Inspect current evidence" }); fireEvent.click(reconcile);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2)); expect(get.mock.calls[1]?.slice(1, 3)).toEqual([OPPORTUNITIES, undefined]);
    expect(await screen.findByText(/Current authority evidence is revision 2/i)).toBeVisible(); expect(screen.getByText("1 requirements · 0 objective results · 0 native acceptances · revision 1")).toBeVisible(); expect(changed).toHaveBeenCalledTimes(1);
  });
  it("reports compatible advanced reconciliation as current evidence without claiming the requested acceptance", async () => {
    const base = snapshot(); const op = base.evidence.opportunities.opportunities[0]!; const current = advancedAwaitingSnapshot();
    const review = { schema_version: "requirement-verification-native-review-v1" as const, policy_version: "current-r8-reviewed-r6-clause-only-v1" as const, session_id: SESSION, opportunity_set_fingerprint: OPPORTUNITIES, opportunity_id: op.opportunity_id, requirement_id: op.requirement_id, coordinate: op.coordinate, expected_source_run_id: RUN, source_window_fingerprint: "3".repeat(64), requirement_plan_confirmation_id: PLAN_CONFIRMATION, requirement_plan_proposal_id: PLAN_PROPOSAL, expected_predecessor_authority_id: null, through_revision: 1, review_receipt_id: "a".repeat(64), review_fingerprint: "b".repeat(64), review_expires_at: new Date(Date.now() + 60_000).toISOString(), requirement_text: "Synthetic clause", local_only: true as const, content_persisted: false as const };
    const changed = vi.fn(); const get = vi.fn().mockResolvedValueOnce(base).mockResolvedValueOnce(current);
    render(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={changed} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={{ getRequirementVerificationEvidenceSnapshot: get, getUserPresenceCapability: vi.fn().mockResolvedValue({ contract_version: "native-user-presence-capability-v1", confirmation_available: true, mode: "native_bridge_bound_token" }), reviewRequirementVerificationOpportunity: vi.fn().mockResolvedValue(review), appendRequirementVerificationAcceptance: vi.fn().mockRejectedValue(new Error("uncertain")) }} />);
    const read = await screen.findByRole("button", { name: "Read exact requirement" }); await waitFor(() => expect(read).not.toBeDisabled()); fireEvent.click(read); await screen.findByText("Synthetic clause"); fireEvent.click(screen.getByRole("checkbox", { name: /I have read/i })); fireEvent.click(screen.getByRole("radio", { name: "accepted" })); fireEvent.click(screen.getByRole("button", { name: "Confirm human disposition" }));
    fireEvent.click(await screen.findByRole("button", { name: "Inspect current evidence" }));
    expect(await screen.findByText(/Current evidence advanced, but it does not prove the requested human disposition was recorded/i)).toBeVisible();
    expect(screen.getByText(/Current authority evidence is revision 2/i)).toBeVisible(); expect(screen.queryByText(/Observed current native human disposition/i)).toBeNull(); expect(changed).toHaveBeenCalledTimes(1);
  });
  it("does not notify when explicit reconciliation returns the same evidence revision", async () => {
    const base = snapshot(); const op = base.evidence.opportunities.opportunities[0]!;
    const review = { schema_version: "requirement-verification-native-review-v1" as const, policy_version: "current-r8-reviewed-r6-clause-only-v1" as const, session_id: SESSION, opportunity_set_fingerprint: OPPORTUNITIES, opportunity_id: op.opportunity_id, requirement_id: op.requirement_id, coordinate: op.coordinate, expected_source_run_id: RUN, source_window_fingerprint: "3".repeat(64), requirement_plan_confirmation_id: PLAN_CONFIRMATION, requirement_plan_proposal_id: PLAN_PROPOSAL, expected_predecessor_authority_id: null, through_revision: 1, review_receipt_id: "a".repeat(64), review_fingerprint: "b".repeat(64), review_expires_at: new Date(Date.now() + 60_000).toISOString(), requirement_text: "Synthetic clause", local_only: true as const, content_persisted: false as const };
    const changed = vi.fn(); const get = vi.fn().mockResolvedValue(base);
    render(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={changed} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={{ getRequirementVerificationEvidenceSnapshot: get, getUserPresenceCapability: vi.fn().mockResolvedValue({ contract_version: "native-user-presence-capability-v1", confirmation_available: true, mode: "native_bridge_bound_token" }), reviewRequirementVerificationOpportunity: vi.fn().mockResolvedValue(review), appendRequirementVerificationAcceptance: vi.fn().mockRejectedValue(new Error("uncertain")) }} />);
    const read = await screen.findByRole("button", { name: "Read exact requirement" }); await waitFor(() => expect(read).not.toBeDisabled()); fireEvent.click(read); await screen.findByText("Synthetic clause"); fireEvent.click(screen.getByRole("checkbox", { name: /I have read/i })); fireEvent.click(screen.getByRole("radio", { name: "accepted" })); fireEvent.click(screen.getByRole("button", { name: "Confirm human disposition" }));
    fireEvent.click(await screen.findByRole("button", { name: "Inspect current evidence" }));
    expect(await screen.findByText(/Current evidence could not be reconciled/i)).toBeVisible(); expect(screen.queryByText(/Observed current native human disposition/i)).toBeNull(); expect(changed).not.toHaveBeenCalled();
  });
  it("uses the separately recorded current revision for a second explicit review without rewriting the selected snapshot", async () => {
    const base = snapshot(); const op = base.evidence.opportunities.opportunities[0]!;
    const current = snapshot(); current.revision = 2; current.evidence.evidence_set_fingerprint = "c".repeat(64);
    current.evidence.acceptance_authorities = [{ acceptance_id: "d".repeat(64), acceptance_fingerprint: "e".repeat(64), authority_kind: "native_user_acceptance", confirmation_id: "f".repeat(64), content_persisted: false, evidence_policy_version: "app-issued-reviewed-requirement-verification-v1", evidence_schema_version: "requirement-verification-evidence-v1", issuer_version: "native-explicit-requirement-acceptance-issuer-v1", local_only: true, opportunity_id: op.opportunity_id, opportunity_set_fingerprint: OPPORTUNITIES, outcome: "accepted", owned_native_action: true, requirement_id: op.requirement_id }];
    current.authority_heads = [{ authority_record_id: "d".repeat(64), kind: "native_acceptance", opportunity_id: op.opportunity_id, revision: 2 }];
    const makeReview = (revision: number, previous: string | null) => ({ schema_version: "requirement-verification-native-review-v1" as const, policy_version: "current-r8-reviewed-r6-clause-only-v1" as const, session_id: SESSION, opportunity_set_fingerprint: OPPORTUNITIES, opportunity_id: op.opportunity_id, requirement_id: op.requirement_id, coordinate: op.coordinate, expected_source_run_id: RUN, source_window_fingerprint: "3".repeat(64), requirement_plan_confirmation_id: PLAN_CONFIRMATION, requirement_plan_proposal_id: PLAN_PROPOSAL, expected_predecessor_authority_id: previous, through_revision: revision, review_receipt_id: `${revision}`.repeat(64), review_fingerprint: "a".repeat(64), review_expires_at: new Date(Date.now() + 60_000).toISOString(), requirement_text: "Synthetic clause", local_only: true as const, content_persisted: false as const });
    const review = vi.fn().mockResolvedValueOnce(makeReview(1, null)).mockResolvedValueOnce(makeReview(2, "d".repeat(64)));
    const changed = vi.fn();
    render(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={changed} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={{ getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(base), getUserPresenceCapability: vi.fn().mockResolvedValue({ contract_version: "native-user-presence-capability-v1", confirmation_available: true, mode: "native_bridge_bound_token" }), reviewRequirementVerificationOpportunity: review, appendRequirementVerificationAcceptance: vi.fn().mockResolvedValue({ applied: false, snapshot: current }) }} />);
    const read = await screen.findByRole("button", { name: "Read exact requirement" }); await waitFor(() => expect(read).not.toBeDisabled()); fireEvent.click(read); await screen.findByText("Synthetic clause"); fireEvent.click(screen.getByRole("checkbox", { name: /I have read/i })); fireEvent.click(screen.getByRole("radio", { name: "accepted" })); fireEvent.click(screen.getByRole("button", { name: "Confirm human disposition" })); await screen.findByText(/selected analysis snapshot remains unchanged/i);
    fireEvent.click(read); await waitFor(() => expect(review).toHaveBeenCalledTimes(2)); expect(review.mock.calls[1]?.[3]).toMatchObject({ through_revision: 2, expected_predecessor_authority_id: "d".repeat(64) });
    expect(changed).toHaveBeenCalledTimes(1);
    expect(screen.getByText("1 requirements · 0 objective results · 0 native acceptances · revision 1")).toBeVisible();
  });
  it("requires explicit read, acknowledgement, disposition, and native confirmation before recording a human outcome", async () => {
    const opportunity = snapshot().evidence.opportunities.opportunities[0]!;
    const review = {
      schema_version: "requirement-verification-native-review-v1" as const, policy_version: "current-r8-reviewed-r6-clause-only-v1" as const,
      session_id: SESSION, opportunity_set_fingerprint: OPPORTUNITIES, opportunity_id: opportunity.opportunity_id, requirement_id: opportunity.requirement_id,
      coordinate: opportunity.coordinate, expected_source_run_id: RUN, source_window_fingerprint: "3".repeat(64), requirement_plan_confirmation_id: PLAN_CONFIRMATION,
      requirement_plan_proposal_id: PLAN_PROPOSAL, expected_predecessor_authority_id: null, through_revision: 1, review_receipt_id: "a".repeat(64), review_fingerprint: "b".repeat(64), review_expires_at: new Date(Date.now() + 60_000).toISOString(), requirement_text: "Synthetic requirement clause", local_only: true as const, content_persisted: false as const,
    };
    const accept = vi.fn().mockResolvedValue({ applied: true, snapshot: snapshot() });
    render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={{ getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(snapshot()), getUserPresenceCapability: vi.fn().mockResolvedValue({ contract_version: "native-user-presence-capability-v1", confirmation_available: true, mode: "native_bridge_bound_token" }), reviewRequirementVerificationOpportunity: vi.fn().mockResolvedValue(review), appendRequirementVerificationAcceptance: accept }} />);
    const read = await screen.findByRole("button", { name: "Read exact requirement" });
    await waitFor(() => expect(read).not.toBeDisabled());
    fireEvent.click(read);
    expect(await screen.findByText("Synthetic requirement clause")).toBeVisible();
    const confirm = screen.getByRole("button", { name: "Confirm human disposition" });
    expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /I have read/i }));
    fireEvent.click(screen.getByRole("radio", { name: "accepted" }));
    await waitFor(() => expect(confirm).not.toBeDisabled());
    fireEvent.click(confirm);
    await waitFor(() => expect(accept).toHaveBeenCalledOnce());
    expect(accept.mock.calls[0]?.[1]).toMatchObject({ outcome: "accepted", review_receipt_id: "a".repeat(64), expected_source_run_id: RUN });
  });
  it("never issues opportunities automatically and only does so after an explicit click", async () => {
    const issue = vi.fn().mockResolvedValue({ applied: true, snapshot: snapshot() });
    const changed = vi.fn();
    render(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={changed} sessionId={SESSION} sourceRunId={RUN} binding={binding("awaiting_evidence")} transport={{ issueCurrentRequirementVerificationOpportunities: issue }} />);
    expect(issue).not.toHaveBeenCalled();
    expect(changed).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Prepare current reviewed requirements" }));
    await waitFor(() => expect(issue).toHaveBeenCalledWith(SESSION, expect.any(AbortSignal)));
    expect(changed).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/human acceptance is separate from an objective passed check/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm human disposition" })).toBeNull();
  });

  it("keeps a validated prepare receipt successful when the advisory refresh observer throws", async () => {
    const issue = vi.fn().mockResolvedValue({ applied: true, snapshot: snapshot() });
    render(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={() => { throw new Error("synthetic observer failure"); }} sessionId={SESSION} sourceRunId={RUN} binding={binding("awaiting_evidence")} transport={{ issueCurrentRequirementVerificationOpportunities: issue }} />);
    fireEvent.click(screen.getByRole("button", { name: "Prepare current reviewed requirements" }));
    expect(await screen.findByText("Current evidence prepared; this analysis snapshot has not been changed.")).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps a validated prepare receipt successful when the advisory refresh observer rejects", async () => {
    const issue = vi.fn().mockResolvedValue({ applied: true, snapshot: snapshot() });
    render(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={() => Promise.reject(new Error("synthetic observer rejection"))} sessionId={SESSION} sourceRunId={RUN} binding={binding("awaiting_evidence")} transport={{ issueCurrentRequirementVerificationOpportunities: issue }} />);
    fireEvent.click(screen.getByRole("button", { name: "Prepare current reviewed requirements" }));
    expect(await screen.findByText("Current evidence prepared; this analysis snapshot has not been changed.")).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("reads exactly the binding revision for persisted evidence", async () => {
    const get = vi.fn().mockResolvedValue(snapshot());
    render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={{ getRequirementVerificationEvidenceSnapshot: get }} />);
    await waitFor(() => expect(get).toHaveBeenCalledWith(SESSION, OPPORTUNITIES, 1, expect.any(AbortSignal)));
    expect(screen.getByText("1 requirements · 0 objective results · 0 native acceptances · revision 1")).toBeInTheDocument();
  });

  it("offers a retry only for an exact persisted read", async () => {
    const get = vi.fn().mockRejectedValueOnce(new Error("synthetic failure")).mockResolvedValue(snapshot());
    render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={{ getRequirementVerificationEvidenceSnapshot: get }} />);
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Retry exact read" }));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(get.mock.calls[1]?.slice(0, 3)).toEqual([SESSION, OPPORTUNITIES, 1]);
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("does not expose a mutation control for an unavailable binding", () => {
    render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={{ ...binding("awaiting_evidence"), evidence_source: "unavailable", requirement_plan_confirmation_id: null, requirement_plan_proposal_id: null, requirement_plan_evidence_fingerprint: null, opportunity_count: null, opportunity_set_fingerprint: null }} transport={{ issueCurrentRequirementVerificationOpportunities: vi.fn() }} />);
    expect(screen.queryByRole("button", { name: /prepare current/i })).toBeNull();
  });

  it("prevents duplicate prepare clicks while one explicit request is active", async () => {
    type Mutation = { applied: boolean; snapshot: RequirementVerificationEvidenceSnapshot };
    let resolve!: (value: Mutation) => void;
    const issue = vi.fn(() => new Promise<Mutation>((next) => { resolve = next; }));
    render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("awaiting_evidence")} transport={{ issueCurrentRequirementVerificationOpportunities: issue }} />);
    const button = screen.getByRole("button", { name: "Prepare current reviewed requirements" });
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(issue).toHaveBeenCalledTimes(1));
    resolve({ applied: true, snapshot: snapshot() });
    expect(await screen.findByText("1 requirements · 0 objective results · 0 native acceptances · revision 1")).toBeVisible();
    expect(issue).toHaveBeenCalledTimes(1);
  });

  it("shows an explicitly prepared current set even when its counts have advanced beyond awaiting analysis", async () => {
    const issue = vi.fn().mockResolvedValue({ applied: true, snapshot: advancedAwaitingSnapshot() });
    render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("awaiting_evidence")} transport={{ issueCurrentRequirementVerificationOpportunities: issue }} />);
    fireEvent.click(screen.getByRole("button", { name: "Prepare current reviewed requirements" }));
    expect(await screen.findByText("1 requirements · 1 objective results · 0 native acceptances · revision 2")).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("loads content-free provenance on demand without changing the historical receipt", async () => {
    const readProvenance = vi.fn().mockResolvedValue(provenance());
    const historical = provenanceSnapshot();
    render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={provenanceBinding()} transport={{
      getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(historical),
      getRequirementVerificationObservedCheckProvenance: readProvenance,
    }} />);
    await screen.findByText("1 requirements · 1 objective results · 0 native acceptances · revision 2");
    expect(readProvenance).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Evidence identity and authority details"));
    fireEvent.click(screen.getByText("Observed-check provenance"));
    expect(await screen.findByText("Source reference")).toBeVisible();
    expect(readProvenance).toHaveBeenCalledWith(SESSION, OBJECTIVE_RESULT, expect.any(AbortSignal));
    expect(screen.getByText(PROVENANCE_SOURCE)).toBeVisible();
    expect(screen.getByText(/Human full-criterion coverage acknowledged separately/i)).toBeVisible();
    expect(screen.queryByText(/raw command/i)).toBeNull();
    expect(screen.getByText(/provider-reported outcome/i)).toBeVisible();
  });

  it("treats a historical 404 as unavailable provenance, not as a failed check", async () => {
    const missing = Object.assign(new Error("gone"), { status: 404 });
    const readProvenance = vi.fn().mockRejectedValue(missing);
    render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={provenanceBinding()} transport={{
      getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(provenanceSnapshot()),
      getRequirementVerificationObservedCheckProvenance: readProvenance,
    }} />);
    await screen.findByText("1 requirements · 1 objective results · 0 native acceptances · revision 2");
    fireEvent.click(screen.getByText("Evidence identity and authority details"));
    fireEvent.click(screen.getByText("Observed-check provenance"));
    expect(await screen.findByText(/Provenance is unavailable for this historical result/i)).toBeVisible();
    expect(screen.getByText(/this is not a failed check/i)).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it.each([
    { method: "static_check", outcome: "passed" },
    { method: "test", outcome: "unknown" },
  ] as const)("explains why $method/$outcome has no direct-pytest provenance disclosure", async ({ method, outcome }) => {
    const unsupported = provenanceSnapshot();
    const result = unsupported.evidence.verification_results[0]!;
    result.method = method;
    result.outcome = outcome;
    const readProvenance = vi.fn().mockResolvedValue(provenance());
    const receiptBinding = outcome === "unknown"
      ? { ...provenanceBinding(), resolved_opportunity_count: 0, met_requirement_count: 0 }
      : provenanceBinding();
    render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={receiptBinding} transport={{
      getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(unsupported),
      getRequirementVerificationObservedCheckProvenance: readProvenance,
    }} />);
    await screen.findByText("1 requirements · 1 objective results · 0 native acceptances · revision 2");
    fireEvent.click(screen.getByText("Evidence identity and authority details"));
    expect(await screen.findByText(/Direct observed-check provenance is unavailable for this objective result; this is not a failed check/i)).toBeVisible();
    expect(screen.queryByText("Observed-check provenance")).toBeNull();
    expect(readProvenance).not.toHaveBeenCalled();
  });

  it("rejects a provenance response for a different opportunity without exposing receipt details", async () => {
    const foreign = { ...provenance(), opportunity_id: "a".repeat(64) };
    const readProvenance = vi.fn().mockResolvedValue(foreign);
    render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={provenanceBinding()} transport={{
      getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(provenanceSnapshot()),
      getRequirementVerificationObservedCheckProvenance: readProvenance,
    }} />);
    await screen.findByText("1 requirements · 1 objective results · 0 native acceptances · revision 2");
    fireEvent.click(screen.getByText("Evidence identity and authority details"));
    fireEvent.click(screen.getByText("Observed-check provenance"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be read/i);
    expect(screen.queryByText(PROVENANCE_SOURCE)).toBeNull();
  });

  it("retries a bounded provenance read after a non-not-found failure", async () => {
    const readProvenance = vi.fn()
      .mockRejectedValueOnce(new Error("synthetic timeout"))
      .mockResolvedValueOnce(provenance());
    render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={provenanceBinding()} transport={{
      getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(provenanceSnapshot()),
      getRequirementVerificationObservedCheckProvenance: readProvenance,
    }} />);
    await screen.findByText("1 requirements · 1 objective results · 0 native acceptances · revision 2");
    fireEvent.click(screen.getByText("Evidence identity and authority details"));
    fireEvent.click(screen.getByText("Observed-check provenance"));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Retry provenance" }));
    await waitFor(() => expect(readProvenance).toHaveBeenCalledTimes(2));
    if (!screen.getByText(PROVENANCE_SOURCE).closest("details")?.open) fireEvent.click(screen.getByText("Observed-check provenance"));
    expect(await screen.findByText(PROVENANCE_SOURCE)).toBeVisible();
  });

  it("ignores a late provenance response after transport replacement", async () => {
    let resolveOld!: (value: ObservedCheckAuthorityProvenance) => void;
    const oldRead = vi.fn().mockImplementation(() => new Promise<ObservedCheckAuthorityProvenance>((resolve) => { resolveOld = resolve; }));
    const historical = provenanceSnapshot();
    const transportA = { getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(historical), getRequirementVerificationObservedCheckProvenance: oldRead };
    const transportB = { getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(historical), getRequirementVerificationObservedCheckProvenance: vi.fn().mockResolvedValue(provenance()) };
    const view = render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={provenanceBinding()} transport={transportA} />);
    await screen.findByText("1 requirements · 1 objective results · 0 native acceptances · revision 2");
    fireEvent.click(screen.getByText("Observed-check provenance"));
    await waitFor(() => expect(oldRead).toHaveBeenCalledOnce());
    view.rerender(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={provenanceBinding()} transport={transportB} />);
    resolveOld(provenance());
    await waitFor(() => expect(screen.queryByText(PROVENANCE_SOURCE)).toBeNull());
  });

  it("withholds a mismatched persisted snapshot instead of showing stale success", async () => {
    const bad = snapshot();
    bad.evidence.opportunities.opportunities = [];
    render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={{ getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(bad) }} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The persisted evidence no longer matches this bound identity.");
    expect(screen.queryByText(/1 requirements ·/)).toBeNull();
  });

  it("surfaces a synchronous transport failure without leaving preparation active", async () => {
    const issue = vi.fn(() => { throw new Error("synthetic synchronous failure"); });
    const changed = vi.fn();
    render(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={changed} sessionId={SESSION} sourceRunId={RUN} binding={binding("awaiting_evidence")} transport={{ issueCurrentRequirementVerificationOpportunities: issue }} />);
    fireEvent.click(screen.getByRole("button", { name: "Prepare current reviewed requirements" }));
    await screen.findByRole("alert");
    await waitFor(() => expect(screen.getByRole("button", { name: "Prepare current reviewed requirements" })).not.toBeDisabled());
    expect(changed).not.toHaveBeenCalled();
  });

  it("aborts a pending exact read and ignores its late completion after changing to awaiting evidence", async () => {
    let resolve!: (value: RequirementVerificationEvidenceSnapshot) => void;
    let signal: AbortSignal | undefined;
    const get = vi.fn((_session: string, _set: string, _revision: number, nextSignal: AbortSignal) => new Promise<RequirementVerificationEvidenceSnapshot>((next) => { signal = nextSignal; resolve = next; }));
    const view = render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={{ getRequirementVerificationEvidenceSnapshot: get }} />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    view.rerender(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("awaiting_evidence")} transport={{ issueCurrentRequirementVerificationOpportunities: vi.fn() }} />);
    expect(signal?.aborted).toBe(true);
    expect(screen.getByRole("button", { name: "Prepare current reviewed requirements" })).not.toBeDisabled();
    resolve(snapshot());
    await Promise.resolve();
    expect(screen.queryByText(/1 requirements ·/)).toBeNull();
  });

  it("keeps a pending exact read when a parent refreshes an equivalent binding object", async () => {
    let resolve!: (value: RequirementVerificationEvidenceSnapshot) => void;
    let signal: AbortSignal | undefined;
    const get = vi.fn((_session: string, _set: string, _revision: number, nextSignal: AbortSignal) => new Promise<RequirementVerificationEvidenceSnapshot>((next) => {
      signal = nextSignal;
      resolve = next;
    }));
    const stableTransport = { getRequirementVerificationEvidenceSnapshot: get };
    const initialBinding = binding("persisted_evidence");
    const firstChanged = vi.fn(); const secondChanged = vi.fn();
    const view = render(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={firstChanged} sessionId={SESSION} sourceRunId={RUN} binding={initialBinding} transport={stableTransport} />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    view.rerender(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={secondChanged} sessionId={SESSION} sourceRunId={RUN} binding={{ ...initialBinding }} transport={stableTransport} />);
    expect(signal?.aborted).toBe(false);
    expect(get).toHaveBeenCalledTimes(1);
    expect(firstChanged).not.toHaveBeenCalled(); expect(secondChanged).not.toHaveBeenCalled();
    resolve(snapshot());
    expect(await screen.findByText("1 requirements · 0 objective results · 0 native acceptances · revision 1")).toBeVisible();
  });

  it("keeps a pending explicit prepare when a parent refreshes an equivalent binding object", async () => {
    type Mutation = { applied: boolean; snapshot: RequirementVerificationEvidenceSnapshot };
    let resolve!: (value: Mutation) => void;
    let signal: AbortSignal | undefined;
    const issue = vi.fn((_session: string, nextSignal: AbortSignal) => new Promise<Mutation>((next) => {
      signal = nextSignal;
      resolve = next;
    }));
    const stableTransport = { issueCurrentRequirementVerificationOpportunities: issue };
    const initialBinding = binding("awaiting_evidence");
    const view = render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={initialBinding} transport={stableTransport} />);
    fireEvent.click(screen.getByRole("button", { name: "Prepare current reviewed requirements" }));
    await waitFor(() => expect(issue).toHaveBeenCalledTimes(1));
    view.rerender(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={{ ...initialBinding }} transport={stableTransport} />);
    expect(signal?.aborted).toBe(false);
    expect(issue).toHaveBeenCalledTimes(1);
    resolve({ applied: true, snapshot: snapshot() });
    expect(await screen.findByText("Current evidence prepared; this analysis snapshot has not been changed.")).toBeVisible();
  });

  it("aborts pending POST work on unmount", async () => {
    let signal: AbortSignal | undefined;
    const issue = vi.fn((_session: string, nextSignal: AbortSignal) => new Promise<never>(() => { signal = nextSignal; }));
    const changed = vi.fn();
    const view = render(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={changed} sessionId={SESSION} sourceRunId={RUN} binding={binding("awaiting_evidence")} transport={{ issueCurrentRequirementVerificationOpportunities: issue }} />);
    fireEvent.click(screen.getByRole("button", { name: "Prepare current reviewed requirements" }));
    await waitFor(() => expect(issue).toHaveBeenCalledTimes(1));
    view.unmount();
    expect(signal?.aborted).toBe(true);
    expect(changed).not.toHaveBeenCalled();
  });

  it("does not invoke the deferred prepare transport after an immediate unmount", async () => {
    const issue = vi.fn();
    const view = render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("awaiting_evidence")} transport={{ issueCurrentRequirementVerificationOpportunities: issue }} />);
    fireEvent.click(screen.getByRole("button", { name: "Prepare current reviewed requirements" }));
    view.unmount();
    await Promise.resolve();
    expect(issue).not.toHaveBeenCalled();
  });

  it("ignores a late POST rejection after its selected session changes", async () => {
    let reject!: (reason?: unknown) => void;
    let signal: AbortSignal | undefined;
    const issue = vi.fn((_session: string, nextSignal: AbortSignal) => new Promise<never>((_resolve, nextReject) => {
      signal = nextSignal;
      reject = nextReject;
    }));
    const view = render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("awaiting_evidence")} transport={{ issueCurrentRequirementVerificationOpportunities: issue }} />);
    fireEvent.click(screen.getByRole("button", { name: "Prepare current reviewed requirements" }));
    await waitFor(() => expect(issue).toHaveBeenCalledTimes(1));
    view.rerender(<RequirementVerificationEvidencePanel compact={false} sessionId={"0".repeat(64)} sourceRunId={"d".repeat(64)} binding={binding("awaiting_evidence")} transport={{ issueCurrentRequirementVerificationOpportunities: issue }} />);
    expect(signal?.aborted).toBe(true);
    reject(new Error("synthetic late rejection"));
    await Promise.resolve();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: "Prepare current reviewed requirements" })).not.toBeDisabled();
  });

  it("aborts pending GET work on unmount", async () => {
    let signal: AbortSignal | undefined;
    const get = vi.fn((_session: string, _set: string, _revision: number, nextSignal: AbortSignal) => new Promise<never>(() => { signal = nextSignal; }));
    const view = render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={{ getRequirementVerificationEvidenceSnapshot: get }} />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("does not show an old transport result after swapping transport with the same identity", async () => {
    let resolve!: (value: RequirementVerificationEvidenceSnapshot) => void;
    const first = { getRequirementVerificationEvidenceSnapshot: vi.fn(() => new Promise<RequirementVerificationEvidenceSnapshot>((next) => { resolve = next; })) };
    const second = { getRequirementVerificationEvidenceSnapshot: vi.fn().mockRejectedValue(new Error("synthetic second transport")) };
    const view = render(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={first} />);
    await waitFor(() => expect(first.getRequirementVerificationEvidenceSnapshot).toHaveBeenCalledTimes(1));
    view.rerender(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={second} />);
    await screen.findByRole("alert");
    resolve(snapshot());
    await Promise.resolve();
    expect(screen.queryByText(/1 requirements ·/)).toBeNull();
  });

  it("withholds revision and authority-count mismatches", async () => {
    const wrongRevision = snapshot(); wrongRevision.revision = 2;
    const wrongCount = { ...binding("persisted_evidence"), authority_head_count: 1 };
    const changed = vi.fn();
    const view = render(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={changed} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={{ getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(wrongRevision) }} />);
    await screen.findByRole("alert");
    view.rerender(<RequirementVerificationEvidencePanel compact={false} sessionId={SESSION} sourceRunId={RUN} binding={wrongCount} transport={{ getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(snapshot()) }} />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
    expect(screen.queryByText(/1 requirements ·/)).toBeNull();
    expect(changed).not.toHaveBeenCalled();
  });

  it("retains an observed receipt while using its current revision for the next check lookup", async () => {
    const base = snapshot();
    const opportunity = base.evidence.opportunities.opportunities[0]!;
    const candidateId = "9".repeat(64);
    const reviewReceipt = "a".repeat(64);
    const resultId = "b".repeat(64);
    const candidate = {
      candidate_id: candidateId, observed_sequence: 3, check_kind: "test" as const, observed_outcome: "passed" as const,
      provider_execution_status: "completed" as const, exit_code: 0 as const, source_completion_schema_version: "observed-check-completion-v1" as const,
      outcome_interpreter_version: "pytest-exit-status-v1" as const, classifier_version: "local-command-rules-v1" as const,
      normalizer_version: "strict-shell-free-v2" as const, rule_id: "test.pytest" as const, local_only: true as const, content_persisted: false as const,
    };
    const makeManifest = (throughRevision: number, predecessor: string | null): ObservedCheckCandidateManifest => ({
      session_id: SESSION, opportunity_set_fingerprint: OPPORTUNITIES, opportunity_id: opportunity.opportunity_id, requirement_id: opportunity.requirement_id,
      expected_source_run_id: RUN, source_window_fingerprint: "3".repeat(64), requirement_plan_confirmation_id: PLAN_CONFIRMATION,
      requirement_plan_proposal_id: PLAN_PROPOSAL, expected_predecessor_authority_id: predecessor, through_revision: throughRevision,
      candidate_manifest_fingerprint: "c".repeat(64), candidates: [candidate], schema_version: "requirement-observed-check-review-v1", local_only: true, content_persisted: false,
    });
    const review: ObservedCheckCriterionReview = {
      session_id: SESSION, opportunity_set_fingerprint: OPPORTUNITIES, opportunity_id: opportunity.opportunity_id, requirement_id: opportunity.requirement_id,
      expected_source_run_id: RUN, source_window_fingerprint: "3".repeat(64), requirement_plan_confirmation_id: PLAN_CONFIRMATION, requirement_plan_proposal_id: PLAN_PROPOSAL,
      expected_predecessor_authority_id: null, through_revision: 1, candidate_manifest_fingerprint: "c".repeat(64), candidate,
      requirement_text: "Synthetic criterion", check_tool_name: "pytest", check_invocation_preview: "pytest -q synthetic.py", check_effect_preview: null,
      review_receipt_id: reviewReceipt, review_fingerprint: "d".repeat(64), review_expires_at: new Date(Date.now() + 60_000).toISOString(),
      full_criterion_coverage_acknowledgement_required: true, objective_result_issued: false, schema_version: "requirement-observed-check-review-v1", local_only: true, content_persisted: false,
    };
    const current = snapshot();
    current.revision = 2;
    current.evidence.evidence_set_fingerprint = "e".repeat(64);
    current.evidence.verification_results = [{
      app_issued: true, authority_kind: "app_objective_verifier", content_persisted: false,
      evidence_policy_version: "app-issued-reviewed-requirement-verification-v1", evidence_schema_version: "requirement-verification-evidence-v1",
      issuer_version: "local-objective-verification-result-issuer-v1", local_only: true, method: "test", observed_sequence: 3,
      opportunity_id: opportunity.opportunity_id, opportunity_set_fingerprint: OPPORTUNITIES, outcome: "passed",
      receipt_reference_ids: [candidateId, reviewReceipt].sort(), requirement_id: opportunity.requirement_id, result_fingerprint: "f".repeat(64), result_id: resultId,
    }];
    current.authority_heads = [{ authority_record_id: resultId, kind: "objective_result", opportunity_id: opportunity.opportunity_id, revision: 2 }];
    const currentProvenance: ObservedCheckAuthorityProvenance = {
      authority_record_id: resultId, session_id: SESSION, opportunity_set_fingerprint: OPPORTUNITIES,
      opportunity_id: opportunity.opportunity_id, requirement_id: opportunity.requirement_id, source_run_id: RUN,
      source_window_fingerprint: "3".repeat(64), requirement_plan_confirmation_id: PLAN_CONFIRMATION,
      requirement_plan_proposal_id: PLAN_PROPOSAL, candidate_manifest_fingerprint: "c".repeat(64),
      source_reference_id: candidateId, coverage_review_reference_id: reviewReceipt, observed_sequence: 3,
      check_kind: "test", provider_execution_status: "completed", observed_outcome: "passed", exit_code: 0,
      source_completion_schema_version: "observed-check-completion-v1", outcome_interpreter_version: "pytest-exit-status-v1",
      classifier_version: "local-command-rules-v1", normalizer_version: "strict-shell-free-v2", rule_id: "test.pytest",
      coverage_review_version: "native-full-criterion-coverage-v1", full_criterion_coverage_acknowledged: true,
      provenance_fingerprint: "0".repeat(64), schema_version: "observed-check-authority-provenance-v1", local_only: true, content_persisted: false,
    };
    const preflight = vi.fn().mockResolvedValueOnce(makeManifest(1, null)).mockResolvedValueOnce(makeManifest(2, resultId));
    const changed = vi.fn();
    render(<RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={changed} sessionId={SESSION} sourceRunId={RUN} binding={binding("persisted_evidence")} transport={{
      getRequirementVerificationEvidenceSnapshot: vi.fn().mockResolvedValue(base),
      getUserPresenceCapability: vi.fn().mockResolvedValue({ contract_version: "native-user-presence-capability-v1", confirmation_available: true, mode: "native_bridge_bound_token" }),
      preflightRequirementVerificationObservedCheck: preflight,
      reviewRequirementVerificationObservedCheck: vi.fn().mockResolvedValue(review),
      issueRequirementVerificationObservedCheck: vi.fn().mockResolvedValue({ applied: true, snapshot: current }),
      getRequirementVerificationObservedCheckProvenance: vi.fn().mockResolvedValue(currentProvenance),
    }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Find eligible direct-pytest checks" }));
    await screen.findByText(/provider-reported result:/);
    fireEvent.click(screen.getByRole("button", { name: "Review exact criterion" }));
    await screen.findByText("Synthetic criterion");
    fireEvent.click(screen.getByRole("checkbox", { name: /acknowledge full-criterion coverage/i }));
    fireEvent.click(screen.getByRole("button", { name: "Issue server-derived observed result" }));
    expect(await screen.findByText(/Recorded server-issued observed test result: passed/i)).toBeVisible();
    fireEvent.click(screen.getByText("Evidence identity and authority details"));
    expect(await screen.findByText("Current authority objective receipts")).toBeVisible();
    fireEvent.click(screen.getByText("Observed-check provenance"));
    expect(await screen.findByText(candidateId)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Find eligible direct-pytest checks" }));
    await waitFor(() => expect(preflight).toHaveBeenCalledTimes(2));
    expect(preflight.mock.calls[1]?.[3]).toMatchObject({ through_revision: 2, expected_predecessor_authority_id: resultId });
    expect(screen.getByText("1 requirements · 0 objective results · 0 native acceptances · revision 1")).toBeVisible();
  });
});
