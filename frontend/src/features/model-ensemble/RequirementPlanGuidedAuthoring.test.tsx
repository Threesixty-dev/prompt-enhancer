import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  PromptEnhancerTransport,
  RequirementPlanEvidenceContract,
  RequirementPlanGuidedAuthoringReview,
  RequirementPlanSourceManifest,
} from "../../shared/api/contracts";
import {
  REQUIREMENT_PLAN_CLAUSE_ALGORITHM_SPEC,
  REQUIREMENT_PLAN_FILE_CONSTRAINT_CODES,
  REQUIREMENT_PLAN_FILE_JSON_SCHEMA,
  REQUIREMENT_PLAN_FILE_SCHEMA_SHA256,
  REQUIREMENT_PLAN_REVIEW_RUBRIC,
} from "../../shared/api/requirementPlanEvidenceContract";
import { RequirementPlanGuidedAuthoring } from "./RequirementPlanGuidedAuthoring";

const id = (value: string) => value.repeat(64);
const SESSION_ID = id("a");
const SOURCE_RUN_ID = id("b");
const SOURCE_WINDOW = id("c");
const MANIFEST = id("d");
const REVIEW_EXPIRES = "2042-01-01T01:00:00Z";
const RECEIPT_EXPIRES = "2042-01-01T00:30:00Z";

type Message = RequirementPlanSourceManifest["messages"][number];
type GuidedMessage = {
  message_sequence: number;
  role: "user" | "agent";
  kind: "request" | "feedback" | "plan";
  clause_count: number;
};

const CLAUSE_ALGORITHM_SPEC = {
  ...REQUIREMENT_PLAN_CLAUSE_ALGORITHM_SPEC,
  operation_order: [
    "replace_nul",
    "split",
    "normalize_whitespace",
    "trim",
    "omit_empty",
    "overflow_check",
  ] as [
    "replace_nul",
    "split",
    "normalize_whitespace",
    "trim",
    "omit_empty",
    "overflow_check",
  ],
};
const REVIEW_RUBRIC = { ...REQUIREMENT_PLAN_REVIEW_RUBRIC };
const isGuidedMessage = (message: Message): message is GuidedMessage => (
  (message.role === "user" && (message.kind === "request" || message.kind === "feedback"))
  || (message.role === "agent" && message.kind === "plan")
);

function contract(messages: GuidedMessage[], runId = SOURCE_RUN_ID, manifest = MANIFEST): RequirementPlanEvidenceContract {
  const candidateClauseCount = messages
    .reduce((count, message) => count + message.clause_count, 0);
  return {
    schema_version: "requirement-plan-evidence-file-v1",
    session_id: SESSION_ID,
    expected_source_run_id: runId,
    source_window_fingerprint: SOURCE_WINDOW,
    expected_predecessor_confirmation_id: null,
    registry_version: "all-20-factor-contracts-v2",
    contract_set_fingerprint: id("e"),
    metric_key: "logic.decomposition_coverage",
    metric_contract_fingerprint: id("f"),
    source_projection_version: "metric-contract-v2-projection-8",
    clause_algorithm: "message-clause-coordinates-en-pl-v1",
    clause_algorithm_spec: CLAUSE_ALGORITHM_SPEC,
    review_rubric_version: "active-requirement-plan-review-rubric-v1",
    review_rubric: REVIEW_RUBRIC,
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
      session_id: SESSION_ID,
      source_run_id: runId,
      source_window_fingerprint: SOURCE_WINDOW,
      schema_version: "requirement-plan-source-manifest-v1",
      clause_algorithm: "message-clause-coordinates-en-pl-v1",
      clause_algorithm_spec: CLAUSE_ALGORITHM_SPEC,
      review_rubric_version: "active-requirement-plan-review-rubric-v1",
      review_rubric: REVIEW_RUBRIC,
      messages,
      message_count: messages.length,
      candidate_clause_count: candidateClauseCount,
      manifest_fingerprint: manifest,
      review_context_expires_at: REVIEW_EXPIRES,
      contains_text: false,
      local_only: true,
      content_persisted: false,
    },
    file_constraint_contract_version: "requirement-plan-file-constraints-v1",
    file_constraint_codes: [...REQUIREMENT_PLAN_FILE_CONSTRAINT_CODES],
  };
}

function reviewFor(source: RequirementPlanEvidenceContract): RequirementPlanGuidedAuthoringReview {
  const clauses = source.source_manifest.messages.filter(isGuidedMessage).flatMap((message) => {
    const candidateKind = message.role === "user" && (message.kind === "request" || message.kind === "feedback")
      ? "user_clause" as const
      : message.role === "agent" && message.kind === "plan" ? "plan" as const : null;
    if (candidateKind === null) return [];
    return Array.from({ length: message.clause_count }, (_, clause_index) => ({
      message_sequence: message.message_sequence,
      clause_index,
      role: message.role,
      kind: message.kind,
      text: candidateKind === "plan"
        ? `Synthetic PLAN ${message.message_sequence}.${clause_index}`
        : `Synthetic user clause ${message.message_sequence}.${clause_index}`,
      candidate_kind: candidateKind,
    }));
  });
  return {
    contract_version: "requirement-plan-guided-authoring-v1",
    session_id: SESSION_ID,
    source_run_id: source.expected_source_run_id,
    source_window_fingerprint: SOURCE_WINDOW,
    expected_predecessor_confirmation_id: null,
    manifest_fingerprint: source.source_manifest.manifest_fingerprint,
    authoring_receipt_id: id("1"),
    candidate_clauses: clauses,
    review_context_expires_at: REVIEW_EXPIRES,
    authoring_receipt_expires_at: RECEIPT_EXPIRES,
    all_candidates_included: true,
    raw_text_persisted: false,
    local_only: true,
  };
}

const transportFor = (review: RequirementPlanGuidedAuthoringReview) => ({
  reviewRequirementPlanGuidedAuthoring: vi.fn(async () => review),
}) as Pick<PromptEnhancerTransport, "reviewRequirementPlanGuidedAuthoring">;

function renderGuided(
  source: RequirementPlanEvidenceContract,
  transport: Pick<PromptEnhancerTransport, "reviewRequirementPlanGuidedAuthoring">,
  enabled = true,
) {
  return render(
    <RequirementPlanGuidedAuthoring
      sessionId={SESSION_ID}
      contract={source}
      transport={transport}
      enabled={enabled}
      onCreated={vi.fn()}
      onClosed={vi.fn()}
    />,
  );
}

describe("RequirementPlanGuidedAuthoring", () => {
  it("aborts a pending review when closed and ignores its late response", async () => {
    const source = contract([{ message_sequence: 1, role: "user", kind: "request", clause_count: 1 }]);
    let resolveReview!: (value: RequirementPlanGuidedAuthoringReview) => void;
    let seenSignal: AbortSignal | undefined;
    const pending = new Promise<RequirementPlanGuidedAuthoringReview>((resolve) => { resolveReview = resolve; });
    const transport = {
      reviewRequirementPlanGuidedAuthoring: vi.fn((_session: string, _contract: RequirementPlanEvidenceContract, _request: unknown, signal?: AbortSignal) => {
        seenSignal = signal;
        return pending;
      }),
    } as Pick<PromptEnhancerTransport, "reviewRequirementPlanGuidedAuthoring">;
    renderGuided(source, transport);

    fireEvent.click(screen.getByRole("button", { name: "Open guided clause review" }));
    await waitFor(() => expect(transport.reviewRequirementPlanGuidedAuthoring).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Close and clear" }));
    expect(seenSignal?.aborted).toBe(true);
    await act(async () => { resolveReview(reviewFor(source)); });
    expect(screen.queryByText("Synthetic user clause 1.0")).toBeNull();
    expect(screen.getByRole("button", { name: "Open guided clause review" })).toBeTruthy();
  });

  it("clears the receipt and ignores stale responses when transport, manifest, or enabled changes", async () => {
    const source = contract([{ message_sequence: 1, role: "user", kind: "request", clause_count: 1 }]);
    const changedManifest = contract(source.source_manifest.messages.filter(isGuidedMessage), SOURCE_RUN_ID, id("9"));
    const signals: AbortSignal[] = [];
    const pending: Array<{ resolve: (review: RequirementPlanGuidedAuthoringReview) => void }> = [];
    const makeTransport = () => ({
      reviewRequirementPlanGuidedAuthoring: vi.fn((_session: string, _contract: RequirementPlanEvidenceContract, _request: unknown, signal?: AbortSignal) => {
        if (signal !== undefined) signals.push(signal);
        return new Promise<RequirementPlanGuidedAuthoringReview>((resolve) => { pending.push({ resolve }); });
      }),
    }) as Pick<PromptEnhancerTransport, "reviewRequirementPlanGuidedAuthoring">;
    const first = makeTransport();
    const rendered = renderGuided(source, first);
    fireEvent.click(screen.getByRole("button", { name: "Open guided clause review" }));
    await waitFor(() => expect(first.reviewRequirementPlanGuidedAuthoring).toHaveBeenCalledOnce());

    const second = makeTransport();
    rendered.rerender(<RequirementPlanGuidedAuthoring sessionId={SESSION_ID} contract={source} transport={second} enabled onCreated={vi.fn()} onClosed={vi.fn()} />);
    expect(signals[0].aborted).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Open guided clause review" }));
    await waitFor(() => expect(second.reviewRequirementPlanGuidedAuthoring).toHaveBeenCalledOnce());

    rendered.rerender(<RequirementPlanGuidedAuthoring sessionId={SESSION_ID} contract={changedManifest} transport={second} enabled onCreated={vi.fn()} onClosed={vi.fn()} />);
    expect(signals[1].aborted).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Open guided clause review" }));
    await waitFor(() => expect(second.reviewRequirementPlanGuidedAuthoring).toHaveBeenCalledTimes(2));

    rendered.rerender(<RequirementPlanGuidedAuthoring sessionId={SESSION_ID} contract={changedManifest} transport={second} enabled={false} onCreated={vi.fn()} onClosed={vi.fn()} />);
    expect(signals[2].aborted).toBe(true);
    await act(async () => { pending.forEach(({ resolve }) => resolve(reviewFor(source))); });
    expect(screen.queryByText("Synthetic user clause 1.0")).toBeNull();
    expect(screen.getByRole("button", { name: "Open guided clause review" })).toBeDisabled();
  });

  it("keeps a linked PLAN checkbox selected across page 2 and back", async () => {
    const source = contract([
      { message_sequence: 1, role: "user", kind: "request", clause_count: 1 },
      { message_sequence: 2, role: "agent", kind: "plan", clause_count: 21 },
    ]);
    renderGuided(source, transportFor(reviewFor(source)));
    fireEvent.click(screen.getByRole("button", { name: "Open guided clause review" }));
    await screen.findByText("Synthetic user clause 1.0");
    fireEvent.click(screen.getByRole("radio", { name: "Active requirement" }));
    fireEvent.click(screen.getByRole("radio", { name: "linked" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    for (let index = 0; index < 21; index += 1) {
      fireEvent.click(screen.getByRole("radio", { name: "Include" }));
      if (index < 20) fireEvent.click(screen.getByRole("button", { name: "Next" }));
    }
    for (let index = 0; index < 21; index += 1) fireEvent.click(screen.getByRole("button", { name: "Back" }));
    fireEvent.click(screen.getByRole("radio", { name: "linked" }));
    fireEvent.click(screen.getByRole("button", { name: "Next PLAN page" }));
    const lastPlan = screen.getByRole("checkbox", { name: /message 2, clause 20/ });
    fireEvent.click(lastPlan);
    fireEvent.click(screen.getByRole("button", { name: "Previous PLAN page" }));
    fireEvent.click(screen.getByRole("button", { name: "Next PLAN page" }));
    expect(screen.getByRole("checkbox", { name: /message 2, clause 20/ })).toBeChecked();
  });

  it("keeps a page-2 exclusion basis selected through search and repagination", async () => {
    const source = contract(Array.from({ length: 22 }, (_, index) => ({
      message_sequence: index + 1,
      role: "user" as const,
      kind: "request" as const,
      clause_count: 1,
    })));
    renderGuided(source, transportFor(reviewFor(source)));
    fireEvent.click(screen.getByRole("button", { name: "Open guided clause review" }));
    await screen.findByText("Synthetic user clause 1.0");
    fireEvent.click(screen.getByRole("radio", { name: "Exclude" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Exclusion reason" }), { target: { value: "superseded" } });
    fireEvent.click(screen.getByRole("button", { name: "Next basis page" }));
    const basis = screen.getByRole("combobox", { name: "Exclusion basis" });
    fireEvent.change(basis, { target: { value: "22:0" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Search basis clauses" }), { target: { value: "Synthetic user" } });
    fireEvent.click(screen.getByRole("button", { name: "Previous basis page" }));
    fireEvent.click(screen.getByRole("button", { name: "Next basis page" }));
    expect(screen.getByRole("combobox", { name: "Exclusion basis" })).toHaveValue("22:0");
  });
});
