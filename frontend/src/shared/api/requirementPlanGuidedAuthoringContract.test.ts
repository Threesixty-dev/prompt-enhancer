import { describe, expect, it } from "vitest";
import type {
  ExcludedRequirementClause,
  RequirementPlanEvidenceEntry,
  RequirementPlanGuidedAuthoringCommand,
  RequirementPlanProposal,
} from "./contracts";
import { parseRequirementPlanGuidedAuthoringProposal } from "./requirementPlanGuidedAuthoringContract";

const id = (value: string) => value.repeat(64);
const SESSION_ID = id("a");
const SOURCE_RUN_ID = id("b");
const SOURCE_WINDOW = id("c");
const RECEIPT_ID = id("d");

const requirements: RequirementPlanEvidenceEntry[] = [{
  coordinate: { message_sequence: 1, clause_index: 0 },
  disposition: "linked",
  plan_indexes: [0],
}];
const excludedUserClauses: ExcludedRequirementClause[] = [{
  coordinate: { message_sequence: 1, clause_index: 1 },
  reason: "duplicate",
  basis_coordinate: { message_sequence: 1, clause_index: 0 },
}];
const planItems = [{ message_sequence: 2, clause_index: 0 }];
const command: RequirementPlanGuidedAuthoringCommand = {
  expected_source_run_id: SOURCE_RUN_ID,
  source_window_fingerprint: SOURCE_WINDOW,
  manifest_fingerprint: id("e"),
  expected_predecessor_confirmation_id: null,
  authoring_receipt_id: RECEIPT_ID,
  requirements,
  excluded_user_clauses: excludedUserClauses,
  plan_items: planItems,
  complete_user_clause_classification_acknowledged: true,
};

function proposal(): RequirementPlanProposal {
  return {
    proposal_id: id("f"),
    session_id: SESSION_ID,
    source_run_id: SOURCE_RUN_ID,
    source_window_fingerprint: SOURCE_WINDOW,
    expected_predecessor_confirmation_id: null,
    payload_sha256: id("1"),
    producer_receipt: {
      kind: "local_review_ui",
      claim_fingerprint: id("2"),
      authority: "untrusted_local_authoring_commitment",
      raw_claim_persisted: false,
    },
    review_rubric_version: "active-requirement-plan-review-rubric-v1",
    requirements,
    excluded_user_clauses: excludedUserClauses,
    plan_items: planItems,
    created_at: "2042-01-01T00:00:00Z",
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

function reverseKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(reverseKeys);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .reverse()
        .map(([key, item]) => [key, reverseKeys(item)]),
    );
  }
  return value;
}

describe("guided authoring proposal contract", () => {
  it("accepts a reordered linked and excluded graph with paired local authority", () => {
    const value = reverseKeys({ proposal: proposal(), applied: true });
    expect(parseRequirementPlanGuidedAuthoringProposal(value, { sessionId: SESSION_ID, command })).toMatchObject({
      applied: true,
      proposal: {
        requirements,
        excluded_user_clauses: excludedUserClauses,
        plan_items: planItems,
      },
    });
  });

  it.each([
    ["session binding", (value: Record<string, unknown>) => { value.session_id = id("9"); }],
    ["source run binding", (value: Record<string, unknown>) => { value.source_run_id = id("8"); }],
    ["source window binding", (value: Record<string, unknown>) => { value.source_window_fingerprint = id("7"); }],
    ["predecessor binding", (value: Record<string, unknown>) => { value.expected_predecessor_confirmation_id = id("6"); }],
    ["local producer authority", (value: Record<string, unknown>) => {
      value.producer_receipt = {
        ...(value.producer_receipt as Record<string, unknown>),
        authority: "untrusted_provenance_claim_commitment",
      };
    }],
    ["producer kind and authority pairing", (value: Record<string, unknown>) => {
      value.producer_receipt = {
        ...(value.producer_receipt as Record<string, unknown>),
        kind: "local_coding_agent",
      };
    }],
  ] as const)("rejects %s drift", (_name, mutate) => {
    const envelope = { proposal: proposal(), applied: true };
    mutate(envelope.proposal as unknown as Record<string, unknown>);
    expect(() => parseRequirementPlanGuidedAuthoringProposal(envelope, { sessionId: SESSION_ID, command })).toThrow();
  });

  it.each([
    ["changed requirements", (envelope: Record<string, unknown>) => {
      (envelope.proposal as Record<string, unknown>).requirements = [];
    }],
    ["changed excluded clauses", (envelope: Record<string, unknown>) => {
      (envelope.proposal as Record<string, unknown>).excluded_user_clauses = [];
    }],
    ["changed plan items", (envelope: Record<string, unknown>) => {
      (envelope.proposal as Record<string, unknown>).plan_items = [];
    }],
    ["terminal decision and authority", (envelope: Record<string, unknown>) => {
      const item = envelope.proposal as Record<string, unknown>;
      item.status = "confirmed";
      item.decision_id = id("9");
      item.decision = "confirm";
      item.decided_at = "2042-01-01T00:00:01Z";
      item.confirmation_authority = "owned_native_user_presence";
    }],
    ["extra envelope field", (envelope: Record<string, unknown>) => {
      envelope.extra = true;
    }],
    ["nonboolean applied field", (envelope: Record<string, unknown>) => {
      envelope.applied = "true";
    }],
  ] as const)("rejects %s", (_name, mutate) => {
    const envelope: Record<string, unknown> = { proposal: proposal(), applied: true };
    mutate(envelope);
    expect(() => parseRequirementPlanGuidedAuthoringProposal(envelope, { sessionId: SESSION_ID, command })).toThrow();
  });
});
