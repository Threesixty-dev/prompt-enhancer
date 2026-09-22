import { useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { RequirementVerificationEvidencePanel } from "../../src/features/model-ensemble/RequirementVerificationEvidencePanel";
import type {
  ModelRequirementVerificationEvidenceBinding,
  ObservedCheckAuthorityProvenance,
  ObservedCheckCandidateManifest,
  ObservedCheckCriterionReview,
  PromptEnhancerTransport,
  RequirementVerificationEvidenceMutation,
  RequirementVerificationEvidenceSnapshot,
  RequirementVerificationOpportunityReview,
  UserPresenceCapability,
} from "../../src/shared/api/contracts";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";
import "../../src/features/model-ensemble/RequirementVerificationEvidencePanel.css";

const SESSION = "a".repeat(64);
const RUN = "b".repeat(64);
const PLAN_CONFIRMATION = "c".repeat(64);
const PLAN_PROPOSAL = "d".repeat(64);
const PLAN_FINGERPRINT = "e".repeat(64);
const OPPORTUNITIES = "f".repeat(64);
const WINDOW = "1".repeat(64);
const EVIDENCE = "2".repeat(64);
const OPPORTUNITY_A = "3".repeat(64);
const OPPORTUNITY_B = "4".repeat(64);
const REQUIREMENT_A = "5".repeat(64);
const REQUIREMENT_B = "6".repeat(64);
const RESULT = "7".repeat(64);
const ACCEPTANCE = "8".repeat(64);
const RECEIPT = "9".repeat(64);
const OBSERVED_CANDIDATE = "0".repeat(64);
const OBSERVED_REVIEW_RECEIPT = "1".repeat(64);
const OBSERVED_RESULT = "2".repeat(64);
const OBSERVED_MANIFEST = "3".repeat(64);
const OBSERVED_REVIEW_FINGERPRINT = "4".repeat(64);

function binding(source: "awaiting_evidence" | "persisted_evidence", observed = false): ModelRequirementVerificationEvidenceBinding {
  return {
    evidence_source: source,
    requirement_plan_confirmation_id: PLAN_CONFIRMATION,
    requirement_plan_proposal_id: PLAN_PROPOSAL,
    requirement_plan_evidence_fingerprint: PLAN_FINGERPRINT,
    requirement_plan_schema_version: "requirement-plan-evidence-v1",
    requirement_plan_policy_version: "reviewed-requirement-plan-v1",
    requirement_plan_review_rubric_version: "active-requirement-plan-review-rubric-v1",
    opportunity_count: 2,
    opportunity_set_fingerprint: OPPORTUNITIES,
    evidence_set_fingerprint: source === "persisted_evidence" ? EVIDENCE : null,
    through_revision: source === "persisted_evidence" ? 2 : null,
    authority_head_count: source === "persisted_evidence" && !observed ? 2 : 0,
    objective_result_count: source === "persisted_evidence" && !observed ? 1 : 0,
    native_acceptance_count: source === "persisted_evidence" && !observed ? 1 : 0,
    resolved_opportunity_count: source === "persisted_evidence" && !observed ? 2 : 0,
    met_requirement_count: source === "persisted_evidence" && !observed ? 2 : 0,
    opportunity_issuer_version: "reviewed-r6-requirement-opportunity-issuer-v1",
    result_issuer_version: "local-objective-verification-result-issuer-v1",
    acceptance_issuer_version: "native-explicit-requirement-acceptance-issuer-v1",
    evidence_schema_version: "requirement-verification-evidence-v1",
    evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
    persistence_schema_version: "requirement-verification-persistence-v1",
    evidence_projection_version: "reviewed-requirement-verification-objective-projection-v1",
    objective_projection_version: "reviewed-requirement-verification-objective-projection-v1",
    binding_schema_version: "session-requirement-verification-evidence-binding-v1",
    binding_fingerprint: "8".repeat(64),
    local_only: true,
    content_persisted: false,
  };
}

function snapshot(
  persisted: boolean,
  acceptedOutcome: "accepted" | "rejected" | "unknown" = "accepted",
  acceptanceOpportunity: string | null = persisted ? OPPORTUNITY_B : null,
  acceptanceRevision = 2,
): RequirementVerificationEvidenceSnapshot {
  return {
    revision: acceptanceOpportunity === null ? (persisted ? 2 : 0) : acceptanceRevision,
    local_only: true,
    content_persisted: false,
    persistence_schema_version: "requirement-verification-persistence-v1",
    authority_heads: persisted ? [
      { authority_record_id: RESULT, kind: "objective_result", opportunity_id: OPPORTUNITY_A, revision: 1 },
      { authority_record_id: ACCEPTANCE, kind: "native_acceptance", opportunity_id: OPPORTUNITY_B, revision: 2 },
    ] : acceptanceOpportunity === null ? [] : [
      { authority_record_id: ACCEPTANCE, kind: "native_acceptance", opportunity_id: acceptanceOpportunity, revision: acceptanceRevision },
    ],
    evidence: {
      evidence_schema_version: "requirement-verification-evidence-v1",
      evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
      projection_version: "reviewed-requirement-verification-objective-projection-v1",
      evidence_set_fingerprint: EVIDENCE,
      local_only: true,
      content_persisted: false,
      opportunities: {
        session_id: SESSION,
        source_window_fingerprint: WINDOW,
        requirement_plan_confirmation_id: PLAN_CONFIRMATION,
        requirement_plan_proposal_id: PLAN_PROPOSAL,
        requirement_plan_evidence_fingerprint: PLAN_FINGERPRINT,
        requirement_plan_schema_version: "requirement-plan-evidence-v1",
        requirement_plan_policy_version: "reviewed-requirement-plan-v1",
        requirement_plan_review_rubric_version: "active-requirement-plan-review-rubric-v1",
        opportunity_set_fingerprint: OPPORTUNITIES,
        opportunities: [
          { opportunity_id: OPPORTUNITY_A, requirement_id: REQUIREMENT_A, requirement_index: 0, coordinate: { message_sequence: 1, clause_index: 0 } },
          { opportunity_id: OPPORTUNITY_B, requirement_id: REQUIREMENT_B, requirement_index: 1, coordinate: { message_sequence: 1, clause_index: 1 } },
        ],
        complete_active_requirement_enumeration: true,
        issuer_version: "reviewed-r6-requirement-opportunity-issuer-v1",
        evidence_schema_version: "requirement-verification-evidence-v1",
        evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
        local_only: true,
        content_persisted: false,
      },
      verification_results: persisted ? [{
        app_issued: true,
        authority_kind: "app_objective_verifier",
        content_persisted: false,
        evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
        evidence_schema_version: "requirement-verification-evidence-v1",
        issuer_version: "local-objective-verification-result-issuer-v1",
        local_only: true,
        method: "static_check",
        observed_sequence: 1,
        opportunity_id: OPPORTUNITY_A,
        opportunity_set_fingerprint: OPPORTUNITIES,
        outcome: "passed",
        receipt_reference_ids: [RECEIPT],
        requirement_id: REQUIREMENT_A,
        result_fingerprint: "9".repeat(64),
        result_id: RESULT,
      }] : [],
      acceptance_authorities: acceptanceOpportunity !== null ? [{
        acceptance_fingerprint: "a".repeat(64),
        acceptance_id: ACCEPTANCE,
        authority_kind: "native_user_acceptance",
        confirmation_id: PLAN_CONFIRMATION,
        content_persisted: false,
        evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
        evidence_schema_version: "requirement-verification-evidence-v1",
        issuer_version: "native-explicit-requirement-acceptance-issuer-v1",
        local_only: true,
        opportunity_id: acceptanceOpportunity,
        opportunity_set_fingerprint: OPPORTUNITIES,
        outcome: acceptedOutcome,
        owned_native_action: true,
        requirement_id: acceptanceOpportunity === OPPORTUNITY_A ? REQUIREMENT_A : REQUIREMENT_B,
      }] : [],
    },
  };
}

function observedBaseSnapshot(): RequirementVerificationEvidenceSnapshot {
  const value = snapshot(false);
  value.revision = 2;
  return value;
}

function observedCandidate() {
  return {
    candidate_id: OBSERVED_CANDIDATE,
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

function observedManifest(throughRevision: number, predecessor: string | null): ObservedCheckCandidateManifest {
  return {
    session_id: SESSION,
    opportunity_set_fingerprint: OPPORTUNITIES,
    opportunity_id: OPPORTUNITY_B,
    requirement_id: REQUIREMENT_B,
    expected_source_run_id: RUN,
    source_window_fingerprint: WINDOW,
    requirement_plan_confirmation_id: PLAN_CONFIRMATION,
    requirement_plan_proposal_id: PLAN_PROPOSAL,
    expected_predecessor_authority_id: predecessor,
    through_revision: throughRevision,
    candidate_manifest_fingerprint: OBSERVED_MANIFEST,
    candidates: [observedCandidate()],
    schema_version: "requirement-observed-check-review-v1",
    local_only: true,
    content_persisted: false,
  };
}

function observedReview(): ObservedCheckCriterionReview {
  return {
    session_id: SESSION,
    opportunity_set_fingerprint: OPPORTUNITIES,
    opportunity_id: OPPORTUNITY_B,
    requirement_id: REQUIREMENT_B,
    expected_source_run_id: RUN,
    source_window_fingerprint: WINDOW,
    requirement_plan_confirmation_id: PLAN_CONFIRMATION,
    requirement_plan_proposal_id: PLAN_PROPOSAL,
    expected_predecessor_authority_id: null,
    through_revision: 2,
    candidate_manifest_fingerprint: OBSERVED_MANIFEST,
    candidate: observedCandidate(),
    requirement_text: "The response must include a bounded verification result.",
    check_tool_name: "pytest",
    check_invocation_preview: "pytest -q synthetic_requirement_test.py",
    check_effect_preview: "exit 0",
    review_receipt_id: OBSERVED_REVIEW_RECEIPT,
    review_fingerprint: OBSERVED_REVIEW_FINGERPRINT,
    review_expires_at: new Date(Date.now() + 120_000).toISOString(),
    full_criterion_coverage_acknowledgement_required: true,
    objective_result_issued: false,
    schema_version: "requirement-observed-check-review-v1",
    local_only: true,
    content_persisted: false,
  };
}

function observedMutation(): RequirementVerificationEvidenceMutation {
  const value = observedBaseSnapshot();
  value.revision = 3;
  value.evidence.verification_results = [{
    app_issued: true,
    authority_kind: "app_objective_verifier",
    content_persisted: false,
    evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
    evidence_schema_version: "requirement-verification-evidence-v1",
    issuer_version: "local-objective-verification-result-issuer-v1",
    local_only: true,
    method: "test",
    observed_sequence: 3,
    opportunity_id: OPPORTUNITY_B,
    opportunity_set_fingerprint: OPPORTUNITIES,
    outcome: "passed",
    receipt_reference_ids: [OBSERVED_CANDIDATE, OBSERVED_REVIEW_RECEIPT],
    requirement_id: REQUIREMENT_B,
    result_fingerprint: "5".repeat(64),
    result_id: OBSERVED_RESULT,
  }];
  value.authority_heads = [{ authority_record_id: OBSERVED_RESULT, kind: "objective_result", opportunity_id: OPPORTUNITY_B, revision: 3 }];
  return { applied: true, snapshot: value };
}

function observedProvenance(): ObservedCheckAuthorityProvenance {
  return {
    authority_record_id: OBSERVED_RESULT,
    session_id: SESSION,
    opportunity_set_fingerprint: OPPORTUNITIES,
    opportunity_id: OPPORTUNITY_B,
    requirement_id: REQUIREMENT_B,
    source_run_id: RUN,
    source_window_fingerprint: WINDOW,
    requirement_plan_confirmation_id: PLAN_CONFIRMATION,
    requirement_plan_proposal_id: PLAN_PROPOSAL,
    candidate_manifest_fingerprint: OBSERVED_MANIFEST,
    source_reference_id: OBSERVED_CANDIDATE,
    coverage_review_reference_id: OBSERVED_REVIEW_RECEIPT,
    observed_sequence: 3,
    check_kind: "test",
    provider_execution_status: "completed",
    observed_outcome: "passed",
    exit_code: 0,
    source_completion_schema_version: "observed-check-completion-v1",
    outcome_interpreter_version: "pytest-exit-status-v1",
    classifier_version: "local-command-rules-v1",
    normalizer_version: "strict-shell-free-v2",
    rule_id: "test.pytest",
    coverage_review_version: "native-full-criterion-coverage-v1",
    full_criterion_coverage_acknowledged: true,
    provenance_fingerprint: "6".repeat(64),
    schema_version: "observed-check-authority-provenance-v1",
    local_only: true,
    content_persisted: false,
  };
}

function Fixture() {
  const state = new URLSearchParams(window.location.search).get("state") ?? "awaiting";
  const observed = state === "observed" || state === "observed-native-unavailable";
  const persisted = ["persisted", "error", "native-unavailable", "mismatch", "stale", "observed", "observed-native-unavailable"].includes(state);
  const failFirstRead = state === "error";
  const nativeUnavailable = state === "native-unavailable" || state === "observed-native-unavailable";
  const mismatch = state === "mismatch";
  const stale = state === "stale";
  const [invocations, setInvocations] = useState(0);
  const [reads, setReads] = useState(0);
  const [reviewReads, setReviewReads] = useState(0);
  const [acceptances, setAcceptances] = useState(0);
  const [observedPreflights, setObservedPreflights] = useState(0);
  const [observedReviews, setObservedReviews] = useState(0);
  const [observedIssues, setObservedIssues] = useState(0);
  const [observedProvenanceReads, setObservedProvenanceReads] = useState(0);
  const [evidenceChanges, setEvidenceChanges] = useState(0);
  const [requestedRevision, setRequestedRevision] = useState<number | null>(null);
  const readAttempt = useRef(0);
  const observedPreflightAttempt = useRef(0);
  const fixtureBinding = useMemo(() => binding(persisted ? "persisted_evidence" : "awaiting_evidence", observed), [observed, persisted]);
  const transport = useMemo<Pick<PromptEnhancerTransport, "issueCurrentRequirementVerificationOpportunities" | "getRequirementVerificationEvidenceSnapshot" | "reviewRequirementVerificationOpportunity" | "appendRequirementVerificationAcceptance" | "getUserPresenceCapability" | "preflightRequirementVerificationObservedCheck" | "reviewRequirementVerificationObservedCheck" | "issueRequirementVerificationObservedCheck" | "getRequirementVerificationObservedCheckProvenance">>(() => ({
    issueCurrentRequirementVerificationOpportunities: async (): Promise<RequirementVerificationEvidenceMutation> => {
      setInvocations((value) => value + 1);
      return { applied: true, snapshot: snapshot(false) };
    },
    getRequirementVerificationEvidenceSnapshot: async (_session, _opportunitySet, throughRevision): Promise<RequirementVerificationEvidenceSnapshot> => {
      setRequestedRevision(throughRevision ?? null);
      setReads((value) => value + 1);
      readAttempt.current += 1;
      if (failFirstRead && readAttempt.current === 1) throw new Error("synthetic read failure");
      return observed ? observedBaseSnapshot() : snapshot(true);
    },
    getUserPresenceCapability: async (): Promise<UserPresenceCapability> => ({
      contract_version: "native-user-presence-capability-v1",
      confirmation_available: !nativeUnavailable,
      mode: nativeUnavailable ? "unavailable" : "native_bridge_bound_token",
    }),
    reviewRequirementVerificationOpportunity: async (sessionId, opportunitySetFingerprint, opportunityId, request): Promise<RequirementVerificationOpportunityReview> => {
      setReviewReads((value) => value + 1);
      if (sessionId !== SESSION || opportunitySetFingerprint !== OPPORTUNITIES || request.expected_source_run_id !== RUN) throw new Error("request identity mismatch");
      const reviewRevision = persisted ? 2 : 0;
      const expectedHead = persisted && opportunityId === OPPORTUNITY_A ? RESULT : null;
      if (request.through_revision !== reviewRevision || request.expected_predecessor_authority_id !== expectedHead) throw new Error("request revision mismatch");
      return {
        schema_version: "requirement-verification-native-review-v1",
        policy_version: "current-r8-reviewed-r6-clause-only-v1",
        session_id: SESSION,
        opportunity_set_fingerprint: OPPORTUNITIES,
        opportunity_id: mismatch ? OPPORTUNITY_B : opportunityId,
        requirement_id: REQUIREMENT_A,
        coordinate: { message_sequence: 1, clause_index: 0 },
        expected_source_run_id: mismatch ? "0".repeat(64) : RUN,
        source_window_fingerprint: WINDOW,
        requirement_plan_confirmation_id: PLAN_CONFIRMATION,
        requirement_plan_proposal_id: PLAN_PROPOSAL,
        expected_predecessor_authority_id: expectedHead,
        through_revision: reviewRevision,
        review_receipt_id: RECEIPT,
        review_fingerprint: "a".repeat(64),
        review_expires_at: stale ? "2000-01-01T00:00:00Z" : new Date(Date.now() + 120_000).toISOString(),
        requirement_text: "The response must include a bounded verification result.",
        local_only: true,
        content_persisted: false,
      };
    },
    appendRequirementVerificationAcceptance: async (sessionId, request): Promise<RequirementVerificationEvidenceMutation> => {
      if (sessionId !== SESSION || request.opportunity_set_fingerprint !== OPPORTUNITIES || request.expected_source_run_id !== RUN) throw new Error("acceptance identity mismatch");
      setAcceptances((value) => value + 1);
      return { applied: true, snapshot: snapshot(false, request.outcome, request.opportunity_id, 1) };
    },
    ...(observed ? {
      preflightRequirementVerificationObservedCheck: async (sessionId, opportunitySetFingerprint, opportunityId, request): Promise<ObservedCheckCandidateManifest> => {
        const attempt = observedPreflightAttempt.current + 1;
        observedPreflightAttempt.current = attempt;
        setObservedPreflights(attempt);
        const expectedPredecessor = attempt === 1 ? null : OBSERVED_RESULT;
        const expectedRevision = attempt === 1 ? 2 : 3;
        if (sessionId !== SESSION || opportunitySetFingerprint !== OPPORTUNITIES || opportunityId !== OPPORTUNITY_B
          || request.expected_source_run_id !== RUN || request.through_revision !== expectedRevision
          || request.expected_predecessor_authority_id !== expectedPredecessor) throw new Error("observed preflight identity mismatch");
        return observedManifest(request.through_revision, request.expected_predecessor_authority_id);
      },
      reviewRequirementVerificationObservedCheck: async (sessionId, opportunitySetFingerprint, opportunityId, candidateId, request): Promise<ObservedCheckCriterionReview> => {
        setObservedReviews((value) => value + 1);
        if (sessionId !== SESSION || opportunitySetFingerprint !== OPPORTUNITIES || opportunityId !== OPPORTUNITY_B || candidateId !== OBSERVED_CANDIDATE
          || request.expected_source_run_id !== RUN || request.through_revision !== 2 || request.expected_predecessor_authority_id !== null
          || request.candidate_manifest_fingerprint !== OBSERVED_MANIFEST) throw new Error("observed review identity mismatch");
        return observedReview();
      },
      issueRequirementVerificationObservedCheck: async (sessionId, opportunitySetFingerprint, opportunityId, candidateId, request, idempotencyKey): Promise<RequirementVerificationEvidenceMutation> => {
        setObservedIssues((value) => value + 1);
        if (sessionId !== SESSION || opportunitySetFingerprint !== OPPORTUNITIES || opportunityId !== OPPORTUNITY_B || candidateId !== OBSERVED_CANDIDATE
          || request.expected_source_run_id !== RUN || request.source_window_fingerprint !== WINDOW || request.through_revision !== 2
          || request.expected_predecessor_authority_id !== null || request.candidate_manifest_fingerprint !== OBSERVED_MANIFEST
          || request.review_receipt_id !== OBSERVED_REVIEW_RECEIPT || request.full_criterion_coverage_acknowledged !== true
          || request.confirmation !== "issue_exact_local_requirement_observed_check_result" || idempotencyKey.length === 0
          || Object.prototype.hasOwnProperty.call(request, "candidate_id") || Object.prototype.hasOwnProperty.call(request, "outcome")
          || Object.prototype.hasOwnProperty.call(request, "method")) throw new Error("observed issue contract mismatch");
        return observedMutation();
      },
      getRequirementVerificationObservedCheckProvenance: async (sessionId, authorityRecordId, signal): Promise<ObservedCheckAuthorityProvenance> => {
        setObservedProvenanceReads((value) => value + 1);
        if (signal?.aborted || sessionId !== SESSION || authorityRecordId !== OBSERVED_RESULT) throw new Error("observed provenance identity mismatch");
        return observedProvenance();
      },
    } : {}),
  }), [failFirstRead, mismatch, nativeUnavailable, observed, stale]);
  return (
    <main>
      <p data-testid="fixture-counters">Issue invocations: {invocations} · Snapshot reads: {reads} · Review reads: {reviewReads} · Acceptance invocations: {acceptances} · Observed preflights: {observedPreflights} · Observed reviews: {observedReviews} · Observed issues: {observedIssues} · Observed provenance reads: {observedProvenanceReads} · Evidence refresh callbacks: {evidenceChanges} · Requested revision: {requestedRevision ?? "none"}</p>
      <RequirementVerificationEvidencePanel compact={false} onEvidenceChanged={() => setEvidenceChanges((value) => value + 1)} sessionId={SESSION} sourceRunId={RUN} binding={fixtureBinding} transport={transport} />
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<Fixture />);
