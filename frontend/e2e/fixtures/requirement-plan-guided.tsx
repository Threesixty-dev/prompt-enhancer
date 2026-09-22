import { useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { RequirementPlanEvidencePanel } from "../../src/features/model-ensemble/RequirementPlanEvidencePanel";
import type {
  PromptEnhancerTransport,
  RequirementPlanEvidenceContract,
  RequirementPlanGuidedAuthoringCommand,
  RequirementPlanGuidedAuthoringReview,
  RequirementPlanProposal,
  RequirementPlanProposalCollection,
} from "../../src/shared/api/contracts";
import {
  REQUIREMENT_PLAN_CLAUSE_ALGORITHM_SPEC,
  REQUIREMENT_PLAN_FILE_CONSTRAINT_CODES,
  REQUIREMENT_PLAN_FILE_JSON_SCHEMA,
  REQUIREMENT_PLAN_FILE_SCHEMA_SHA256,
  REQUIREMENT_PLAN_REVIEW_RUBRIC,
} from "../../src/shared/api/requirementPlanEvidenceContract";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";
import "../../src/features/model-ensemble/MetricEvidenceFilePanel.css";
import "../../src/features/model-ensemble/RequirementPlanEvidencePanel.css";

const SESSION = "a".repeat(64);
const RUN_A = "b".repeat(64);
const RUN_B = "c".repeat(64);
const WINDOW = "d".repeat(64);
const MANIFEST = "e".repeat(64);
const RECEIPT = "f".repeat(64);
const PROPOSAL = "1".repeat(64);
const PAYLOAD = "2".repeat(64);
const REVIEW_CONTEXT_EXPIRES_AT = new Date(Date.now() + 10 * 60_000).toISOString();
const AUTHORING_RECEIPT_EXPIRES_AT = new Date(Date.now() + 5 * 60_000).toISOString();

function contract(runId: string = RUN_A): RequirementPlanEvidenceContract {
  return {
    schema_version: "requirement-plan-evidence-file-v1",
    session_id: SESSION,
    expected_source_run_id: runId,
    source_window_fingerprint: WINDOW,
    expected_predecessor_confirmation_id: null,
    registry_version: "all-20-factor-contracts-v2",
    contract_set_fingerprint: "3".repeat(64),
    metric_key: "logic.decomposition_coverage",
    metric_contract_fingerprint: "4".repeat(64),
    source_projection_version: "metric-contract-v2-projection-8",
    clause_algorithm: "message-clause-coordinates-en-pl-v1",
    clause_algorithm_spec: { ...REQUIREMENT_PLAN_CLAUSE_ALGORITHM_SPEC, operation_order: [...REQUIREMENT_PLAN_CLAUSE_ALGORITHM_SPEC.operation_order] },
    review_rubric_version: "active-requirement-plan-review-rubric-v1",
    review_rubric: structuredClone(REQUIREMENT_PLAN_REVIEW_RUBRIC),
    allowed_dispositions: ["linked", "not_linked", "pending"],
    allowed_user_clause_classifications: ["active_requirement", "excluded_from_active_requirement_denominator"],
    allowed_exclusion_reasons: ["not_requirement", "superseded", "withdrawn", "duplicate", "out_of_scope", "already_satisfied_or_closed"],
    max_reviewed_user_clause_count: 1000,
    max_active_requirement_count: 1000,
    max_excluded_user_clause_count: 1000,
    max_plan_item_count: 1000,
    max_link_count: 4000,
    max_file_bytes: 65536,
    max_json_depth: 8,
    max_json_items: 6000,
    max_clauses_per_message: 128,
    max_lifetime_seconds: 86400,
    canonical_json_required: true,
    canonicalization: "json-sort-keys-compact-ensure-ascii-v1",
    payload_digest: "sha256",
    utf8_without_bom_required: true,
    duplicate_keys_allowed: false,
    floating_point_values_allowed: false,
    candidate_unit: "reviewable_user_request_or_feedback_clause",
    opportunity_unit: "reviewed_active_requirement_clause",
    complete_user_clause_classification_required: true,
    compound_clause_coarsening_disclosed: true,
    one_active_requirement_coordinate_is_one_opportunity: true,
    excluded_user_clauses_are_excluded_from_metric: true,
    uncertain_classification_policy: "reject_or_leave_proposal_unconfirmed",
    import_creates_unconfirmed_proposal_only: true,
    native_confirmation_required_for_metric_authority: true,
    raw_payload_persisted: false,
    prose_allowed: false,
    scores_allowed: false,
    untrusted_structured_classification_proposals_allowed: true,
    authoritative_model_judgment_claims_allowed: false,
    raw_producer_claim_persisted: false,
    durable_producer_claim_shape: "installation_keyed_opaque_commitment_only",
    objective_receipt_claims_allowed: false,
    import_confirmation: "import_requirement_plan_evidence_as_unconfirmed_proposal",
    file_json_schema_sha256: REQUIREMENT_PLAN_FILE_SCHEMA_SHA256,
    file_json_schema: structuredClone(REQUIREMENT_PLAN_FILE_JSON_SCHEMA),
    source_manifest: {
      session_id: SESSION,
      source_run_id: runId,
      source_window_fingerprint: WINDOW,
      schema_version: "requirement-plan-source-manifest-v1",
      clause_algorithm: "message-clause-coordinates-en-pl-v1",
      clause_algorithm_spec: { ...REQUIREMENT_PLAN_CLAUSE_ALGORITHM_SPEC, operation_order: [...REQUIREMENT_PLAN_CLAUSE_ALGORITHM_SPEC.operation_order] },
      review_rubric_version: "active-requirement-plan-review-rubric-v1",
      review_rubric: structuredClone(REQUIREMENT_PLAN_REVIEW_RUBRIC),
      messages: [
        { message_sequence: 1, role: "user", kind: "request", clause_count: 2 },
        { message_sequence: 2, role: "agent", kind: "plan", clause_count: 1 },
      ],
      message_count: 2,
      candidate_clause_count: 3,
      manifest_fingerprint: MANIFEST,
      review_context_expires_at: REVIEW_CONTEXT_EXPIRES_AT,
      contains_text: false,
      local_only: true,
      content_persisted: false,
    },
    file_constraint_contract_version: "requirement-plan-file-constraints-v1",
    file_constraint_codes: [...REQUIREMENT_PLAN_FILE_CONSTRAINT_CODES],
  };
}

function authoringReview(runId: string = RUN_A): RequirementPlanGuidedAuthoringReview {
  return {
    contract_version: "requirement-plan-guided-authoring-v1",
    session_id: SESSION,
    source_run_id: runId,
    source_window_fingerprint: WINDOW,
    expected_predecessor_confirmation_id: null,
    manifest_fingerprint: MANIFEST,
    authoring_receipt_id: RECEIPT,
    candidate_clauses: [
      { message_sequence: 1, clause_index: 0, role: "user", kind: "request", text: "Create the synthetic output.", candidate_kind: "user_clause" },
      { message_sequence: 1, clause_index: 1, role: "user", kind: "request", text: "Treat the output as duplicate work.", candidate_kind: "user_clause" },
      { message_sequence: 2, clause_index: 0, role: "agent", kind: "plan", text: "Implement the synthetic output.", candidate_kind: "plan" },
    ],
    review_context_expires_at: REVIEW_CONTEXT_EXPIRES_AT,
    authoring_receipt_expires_at: AUTHORING_RECEIPT_EXPIRES_AT,
    all_candidates_included: true,
    raw_text_persisted: false,
    local_only: true,
  };
}

function proposal(command: RequirementPlanGuidedAuthoringCommand): RequirementPlanProposal {
  return {
    proposal_id: PROPOSAL,
    session_id: SESSION,
    source_run_id: command.expected_source_run_id,
    source_window_fingerprint: WINDOW,
    expected_predecessor_confirmation_id: null,
    payload_sha256: PAYLOAD,
    producer_receipt: { kind: "local_review_ui", claim_fingerprint: "5".repeat(64), authority: "untrusted_local_authoring_commitment", raw_claim_persisted: false },
    review_rubric_version: "active-requirement-plan-review-rubric-v1",
    requirements: command.requirements,
    excluded_user_clauses: command.excluded_user_clauses,
    plan_items: command.plan_items,
    created_at: "2042-01-01T00:10:00Z",
    schema_version: "requirement-plan-evidence-v1",
    policy_version: "reviewed-requirement-plan-v1",
    status: "proposed",
    decision_id: null,
    decision: null,
    decided_at: null,
    confirmation_authority: null,
    local_only: true,
    content_persisted: false,
  };
}

function Fixture() {
  const mode = new URLSearchParams(window.location.search).get("state") ?? "ready";
  const nativeAvailable = mode !== "native-unavailable";
  const [runId, setRunId] = useState(RUN_A);
  const [reviewReads, setReviewReads] = useState(0);
  const [submits, setSubmits] = useState(0);
  const [decisions, setDecisions] = useState(0);
  const [filePreviews, setFilePreviews] = useState(0);
  const [fileImports, setFileImports] = useState(0);
  const [lastCommand, setLastCommand] = useState<RequirementPlanGuidedAuthoringCommand | null>(null);
  const lateResolver = useRef<((value: RequirementPlanGuidedAuthoringReview) => void) | null>(null);
  const transport = useMemo<Pick<PromptEnhancerTransport, "getRequirementPlanEvidenceContract" | "listRequirementPlanProposals" | "previewRequirementPlanEvidence" | "importRequirementPlanEvidence" | "reviewRequirementPlanProposal" | "decideRequirementPlanProposal" | "getUserPresenceCapability" | "reviewRequirementPlanGuidedAuthoring" | "submitRequirementPlanGuidedAuthoring">>(() => ({
    getRequirementPlanEvidenceContract: async () => contract(runId),
    listRequirementPlanProposals: async (): Promise<RequirementPlanProposalCollection> => ({ session_id: SESSION, proposals: [], total: 0, complete: true, snapshot: { snapshot_id: "6".repeat(64), total: 0, decision_count: 0, high_water_created_at: null, high_water_proposal_id: null } }),
    previewRequirementPlanEvidence: async () => { setFilePreviews((value) => value + 1); throw new Error("guided fixture must not preview a file"); },
    importRequirementPlanEvidence: async () => { setFileImports((value) => value + 1); throw new Error("guided fixture must not import a file"); },
    reviewRequirementPlanProposal: async () => { throw new Error("guided fixture must not open the imported-file review"); },
    decideRequirementPlanProposal: async () => { setDecisions((value) => value + 1); throw new Error("guided fixture must not decide automatically"); },
    getUserPresenceCapability: async () => ({ contract_version: "native-user-presence-capability-v1", confirmation_available: nativeAvailable, mode: nativeAvailable ? "native_bridge_bound_token" : "unavailable" }),
    reviewRequirementPlanGuidedAuthoring: async () => {
      setReviewReads((value) => value + 1);
      if (mode === "late") return new Promise<RequirementPlanGuidedAuthoringReview>((resolve) => { lateResolver.current = resolve; });
      return authoringReview(runId);
    },
    submitRequirementPlanGuidedAuthoring: async (_session, command) => {
      setSubmits((value) => value + 1);
      setLastCommand(command);
      return { proposal: proposal(command), applied: true };
    },
  }), [mode, nativeAvailable, runId]);
  return <main>
    <div data-testid="fixture-counters">Guided reads: {reviewReads} · Guided proposals: {submits} · Native decisions: {decisions} · File previews: {filePreviews} · File imports: {fileImports}</div>
    <div data-testid="last-guided-command">{lastCommand === null ? "none" : JSON.stringify(lastCommand)}</div>
    <button type="button" onClick={() => setRunId((value) => value === RUN_A ? RUN_B : RUN_A)}>Switch synthetic source window</button>
    {mode === "late" && <button type="button" onClick={() => { lateResolver.current?.(authoringReview(runId)); lateResolver.current = null; }}>Resolve late source read</button>}
    <RequirementPlanEvidencePanel compact={false} sessionId={SESSION} sourceRunId={runId} sourceProjectionVersion="metric-contract-v2-projection-8" transport={transport} />
  </main>;
}

createRoot(document.getElementById("root")!).render(<Fixture />);
