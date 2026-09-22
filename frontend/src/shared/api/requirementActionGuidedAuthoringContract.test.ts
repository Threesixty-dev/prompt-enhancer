import { describe, expect, it } from "vitest";
import type {
  RequirementActionCandidate,
  RequirementActionEvidenceContract,
  RequirementActionGuidedAuthoringCommand,
  RequirementActionGuidedAuthoringReview,
  RequirementActionProposal,
} from "./contracts";
import {
  REQUIREMENT_ACTION_FILE_JSON_SCHEMA,
  REQUIREMENT_ACTION_FILE_SCHEMA_SHA256,
} from "./requirementActionEvidenceContract";
import {
  parseRequirementActionGuidedAuthoringProposal,
  parseRequirementActionGuidedAuthoringReview,
} from "./requirementActionGuidedAuthoringContract";

const id = (value: string) => value.repeat(64);
const SESSION_ID = id("a");
const SOURCE_RUN_ID = id("b");
const SOURCE_WINDOW = id("c");
const PLAN_CONFIRMATION_ID = id("d");
const PLAN_EVIDENCE = id("e");
const MANIFEST_ID = id("f");
const ACTION_ID = id("1");
const REQUIREMENT_ID = id("2");
const ACTION_TIME = "2042-01-01T00:00:00.000000Z";
const futureUtc = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString();
const REVIEW_EXPIRES = futureUtc(10);
const RECEIPT_EXPIRES = futureUtc(5);

const candidate: RequirementActionCandidate = {
  candidate_index: 0,
  action_id: ACTION_ID,
  source_reference_id: id("3"),
  sequence: 10,
  event_kind: "tool_end",
  tool_category: "test",
  occurred_at: ACTION_TIME,
  duration_ms: 125,
  family: "command",
  state: "completed",
};
const requirement = {
  requirement_index: 0,
  requirement_id: REQUIREMENT_ID,
  coordinate: { message_sequence: 1, clause_index: 0 },
};
const provenance = {
  provider: "synthetic" as const,
  provider_version: "synthetic-provider-v1",
  adapter_version: "synthetic-adapter-v1",
  decoder_key: "synthetic-safe-events",
  decoder_version: "1",
  source_schema_version: "synthetic-safe-events-v1",
  evidence_schema_version: 2 as const,
  extraction_complete: true,
};
const manifest = {
  session_id: SESSION_ID,
  source_run_id: SOURCE_RUN_ID,
  source_window_fingerprint: SOURCE_WINDOW,
  provenance,
  extraction_complete: true,
  enumeration_complete: true,
  actions: [candidate],
  manifest_fingerprint: MANIFEST_ID,
  schema_version: "requirement-action-candidate-manifest-v1" as const,
  local_only: true as const,
  content_persisted: false as const,
};
const contract: RequirementActionEvidenceContract = {
  action_descriptor_algorithm_version: "provider-local-redacted-action-descriptor-v1",
  action_descriptor_content_persisted: false,
  candidate_metadata_fingerprint_version: "requirement-action-candidate-metadata-v1",
  schema_version: "requirement-action-evidence-file-v1",
  session_id: SESSION_ID,
  expected_source_run_id: SOURCE_RUN_ID,
  source_window_fingerprint: SOURCE_WINDOW,
  source_projection_version: "metric-contract-v2-projection-8",
  requirement_plan_confirmation_id: PLAN_CONFIRMATION_ID,
  requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
  candidate_manifest: manifest,
  requirements: [requirement],
  expected_predecessor_confirmation_id: null,
  metric_key: "logic.requirement_action_traceability",
  max_requirement_count: 1000,
  max_candidate_count: 4000,
  max_link_count: 8000,
  max_file_bytes: 65536,
  max_json_depth: 8,
  max_json_items: 8000,
  max_lifetime_seconds: 86400,
  canonicalization: "json-sort-keys-compact-ensure-ascii-v1",
  import_creates_unconfirmed_proposal_only: true,
  native_confirmation_required_for_metric_authority: true,
  all_linked_action_semantics_acknowledgement_required: true,
  native_review_displays_every_redacted_invocation_and_effect: true,
  review_visible_display_algorithm_version: "requirement-action-review-visible-display-v1",
  review_visible_display_is_injective_one_pass: true,
  review_visible_display_never_truncates: true,
  every_requirement_requires_one_link_classification: true,
  empty_action_links_are_explicit_reviewed_negative_links: true,
  action_states_are_application_issued: true,
  action_state_claims_allowed_in_file: false,
  objective_proof_claims_allowed_in_file: false,
  metric_values_allowed_in_file: false,
  raw_payload_persisted: false,
  raw_producer_claim_persisted: false,
  durable_producer_claim_shape: "installation_keyed_opaque_commitment_only",
  import_confirmation: "import_requirement_action_proposal_without_metric_authority",
  review_rubric_version: "requirement-action-review-rubric-v2",
  file_json_schema_sha256: REQUIREMENT_ACTION_FILE_SCHEMA_SHA256,
  file_json_schema: structuredClone(REQUIREMENT_ACTION_FILE_JSON_SCHEMA),
};

function review(): RequirementActionGuidedAuthoringReview {
  return {
    contract_version: "requirement-action-guided-authoring-v1",
    session_id: SESSION_ID,
    source_run_id: SOURCE_RUN_ID,
    source_window_fingerprint: SOURCE_WINDOW,
    requirement_plan_confirmation_id: PLAN_CONFIRMATION_ID,
    requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
    candidate_manifest_fingerprint: MANIFEST_ID,
    expected_predecessor_confirmation_id: null,
    authoring_receipt_id: id("4"),
    descriptor_set_fingerprint: id("5"),
    requirements: [{
      requirement_id: REQUIREMENT_ID,
      coordinate: requirement.coordinate,
      text: "Synthetic requirement text",
      linked_action_ids: [],
    }],
    candidates: [candidate],
    candidate_memberships: [{
      candidate,
      candidate_metadata_fingerprint_version: "requirement-action-candidate-metadata-v1",
      candidate_metadata_fingerprint: id("6"),
      descriptor_algorithm_version: "provider-local-redacted-action-descriptor-v1",
      tool_name: "synthetic-test-tool",
      invocation_preview: "synthetic invocation",
      result_or_effect_preview: "synthetic completed effect",
      invocation_truncated: false,
      result_or_effect_truncated: false,
      redactor_version: "synthetic-redactor-v1",
      linked_requirement_ids: [],
    }],
    review_context_expires_at: REVIEW_EXPIRES,
    authoring_receipt_expires_at: RECEIPT_EXPIRES,
    all_requirements_and_candidates_included: true,
    raw_text_persisted: false,
    local_only: true,
  };
}

const command: RequirementActionGuidedAuthoringCommand = {
  expected_source_run_id: SOURCE_RUN_ID,
  source_window_fingerprint: SOURCE_WINDOW,
  requirement_plan_confirmation_id: PLAN_CONFIRMATION_ID,
  requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
  candidate_manifest_fingerprint: MANIFEST_ID,
  expected_predecessor_confirmation_id: null,
  authoring_receipt_id: id("4"),
  links: [{ requirement_index: 0, action_candidate_indexes: [0] }],
  complete_requirement_link_classification_acknowledged: true,
};

const proposalExpectation = (expectedCommand = command) => ({
  sessionId: SESSION_ID,
  command: expectedCommand,
  contract,
});

function proposal(): RequirementActionProposal {
  return {
    proposal_id: id("7"),
    session_id: SESSION_ID,
    source_run_id: SOURCE_RUN_ID,
    source_window_fingerprint: SOURCE_WINDOW,
    requirement_plan_confirmation_id: PLAN_CONFIRMATION_ID,
    requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
    candidate_manifest_fingerprint: MANIFEST_ID,
    candidate_provenance: provenance,
    candidate_extraction_complete: true,
    candidate_enumeration_complete: true,
    expected_predecessor_confirmation_id: null,
    payload_sha256: id("8"),
    producer_receipt: {
      kind: "local_review_ui",
      claim_fingerprint: id("9"),
      authority: "untrusted_local_authoring_commitment",
      raw_claim_persisted: false,
    },
    review_rubric_version: "requirement-action-review-rubric-v2",
    requirements: [requirement],
    candidates: [candidate],
    links: [{ requirement_id: REQUIREMENT_ID, action_ids: [ACTION_ID] }],
    created_at: ACTION_TIME,
    schema_version: "requirement-action-evidence-v1",
    policy_version: "reviewed-requirement-action-v1",
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

describe("guided action authoring contract", () => {
  it("accepts a valid reordered review envelope", () => {
    const value = reverseKeys(review());
    expect(parseRequirementActionGuidedAuthoringReview(value, { sessionId: SESSION_ID, contract })).toMatchObject({
      session_id: SESSION_ID,
      requirements: [{ text: "Synthetic requirement text" }],
    });
  });

  it("compares receipt expiry instants rather than their UTC spellings", () => {
    const value = review();
    value.review_context_expires_at = "2042-01-01T00:30:00.000001Z";
    value.authoring_receipt_expires_at = "2042-01-01T00:30:00Z";
    expect(parseRequirementActionGuidedAuthoringReview(value, {
      sessionId: SESSION_ID, contract,
    }).authoring_receipt_expires_at).toBe(value.authoring_receipt_expires_at);
  });

  it.each([
    ["missing requirement text", (value: Record<string, unknown>) => {
      const requirements = value.requirements as Array<Record<string, unknown>>;
      delete requirements[0].text;
    }],
    ["bad candidate metadata", (value: Record<string, unknown>) => {
      const memberships = value.candidate_memberships as Array<Record<string, unknown>>;
      memberships[0].candidate_metadata_fingerprint = "not-a-fingerprint";
    }],
    ["extra nested membership key", (value: Record<string, unknown>) => {
      const memberships = value.candidate_memberships as Array<Record<string, unknown>>;
      memberships[0].unexpected = true;
    }],
    ["oversized requirement text", (value: Record<string, unknown>) => {
      const requirements = value.requirements as Array<Record<string, unknown>>;
      requirements[0].text = "x".repeat(32_001);
    }],
    ["missing completed effect", (value: Record<string, unknown>) => {
      const memberships = value.candidate_memberships as Array<Record<string, unknown>>;
      memberships[0].result_or_effect_preview = null;
    }],
  ] as const)("rejects %s", (_name, mutate) => {
    const value = review() as unknown as Record<string, unknown>;
    mutate(value);
    expect(() => parseRequirementActionGuidedAuthoringReview(value, { sessionId: SESSION_ID, contract })).toThrow();
  });

  it("accepts a valid linked proposal graph", () => {
    const value = { proposal: proposal(), applied: true };
    expect(parseRequirementActionGuidedAuthoringProposal(value, proposalExpectation())).toMatchObject({
      applied: true,
      proposal: { links: [{ requirement_id: REQUIREMENT_ID, action_ids: [ACTION_ID] }] },
    });
  });

  it("rejects a valid-shaped proposal whose submitted link graph differs from the command", () => {
    const altered = proposal();
    altered.links = [{ requirement_id: REQUIREMENT_ID, action_ids: [] }];
    expect(() => parseRequirementActionGuidedAuthoringProposal(
      { proposal: altered, applied: true },
      proposalExpectation(),
    )).toThrow();
  });

  it("accepts an explicit empty action-link classification", () => {
    const emptyCommand = {
      ...command,
      links: [{ requirement_index: 0, action_candidate_indexes: [] }],
    };
    const emptyProposal = proposal();
    emptyProposal.links = [{ requirement_id: REQUIREMENT_ID, action_ids: [] }];
    expect(parseRequirementActionGuidedAuthoringProposal(
      { proposal: emptyProposal, applied: true },
      proposalExpectation(emptyCommand),
    )).toMatchObject({ applied: true });
  });

  it("accepts sorted server action ids when candidate indexes use reverse lexical ids", () => {
    const reverseLexicalCandidate: RequirementActionCandidate = {
      ...candidate,
      candidate_index: 1,
      action_id: id("0"),
      source_reference_id: id("4"),
      sequence: 11,
    };
    const multiContract: RequirementActionEvidenceContract = {
      ...contract,
      candidate_manifest: {
        ...contract.candidate_manifest,
        actions: [candidate, reverseLexicalCandidate],
        manifest_fingerprint: id("5"),
      },
    };
    const multiCommand: RequirementActionGuidedAuthoringCommand = {
      ...command,
      candidate_manifest_fingerprint: id("5"),
      links: [{ requirement_index: 0, action_candidate_indexes: [0, 1] }],
    };
    const multiProposal = proposal();
    multiProposal.candidate_manifest_fingerprint = id("5");
    multiProposal.candidates = [candidate, reverseLexicalCandidate];
    multiProposal.links = [{ requirement_id: REQUIREMENT_ID, action_ids: [id("0"), ACTION_ID] }];
    expect(parseRequirementActionGuidedAuthoringProposal(
      { proposal: multiProposal, applied: true },
      { sessionId: SESSION_ID, command: multiCommand, contract: multiContract },
    )).toMatchObject({ applied: true });
  });

  it.each([
    ["session", (value: Record<string, unknown>) => { value.session_id = id("6"); }],
    ["source run", (value: Record<string, unknown>) => { value.source_run_id = id("7"); }],
    ["source window", (value: Record<string, unknown>) => { value.source_window_fingerprint = id("8"); }],
    ["plan confirmation", (value: Record<string, unknown>) => { value.requirement_plan_confirmation_id = id("9"); }],
    ["plan evidence", (value: Record<string, unknown>) => { value.requirement_plan_evidence_fingerprint = id("1"); }],
    ["candidate manifest", (value: Record<string, unknown>) => { value.candidate_manifest_fingerprint = id("3"); }],
    ["predecessor", (value: Record<string, unknown>) => { value.expected_predecessor_confirmation_id = id("4"); }],
  ] as const)("rejects %s source binding drift", (_name, mutate) => {
    const altered = proposal();
    mutate(altered as unknown as Record<string, unknown>);
    expect(() => parseRequirementActionGuidedAuthoringProposal(
      { proposal: altered, applied: true },
      proposalExpectation(),
    )).toThrow();
  });

  it("rejects a nonboolean applied field and an extra top-level field", () => {
    expect(() => parseRequirementActionGuidedAuthoringProposal(
      { proposal: proposal(), applied: "true" },
      proposalExpectation(),
    )).toThrow();
    expect(() => parseRequirementActionGuidedAuthoringProposal(
      { proposal: proposal(), applied: true, extra: true },
      proposalExpectation(),
    )).toThrow();
  });

  it("rejects invalid, expired, and out-of-order expiry metadata", () => {
    const cases = [
      (altered: RequirementActionGuidedAuthoringReview) => { altered.review_context_expires_at = "not-a-utc-timestamp"; },
      (altered: RequirementActionGuidedAuthoringReview) => { altered.review_context_expires_at = "2020-01-01T00:00:00.000Z"; altered.authoring_receipt_expires_at = "2020-01-01T00:00:00.000Z"; },
      (altered: RequirementActionGuidedAuthoringReview) => { altered.authoring_receipt_expires_at = futureUtc(15); },
    ];
    cases.forEach((mutate) => {
      const altered = review();
      mutate(altered);
      expect(() => parseRequirementActionGuidedAuthoringReview(
        altered,
        { sessionId: SESSION_ID, contract },
      )).toThrow();
    });
  });

  it("rejects a changed candidate ordinal even when its action id is unchanged", () => {
    const altered = proposal();
    altered.candidates[0].candidate_index = 1;
    expect(() => parseRequirementActionGuidedAuthoringProposal(
      { proposal: altered, applied: true },
      proposalExpectation(),
    )).toThrow();
  });

  it.each([
    ["changed requirements", (value: Record<string, unknown>) => {
      (value.proposal as Record<string, unknown>).requirements = [];
    }],
    ["changed candidates", (value: Record<string, unknown>) => {
      (value.proposal as Record<string, unknown>).candidates = [];
    }],
    ["changed links", (value: Record<string, unknown>) => {
      (value.proposal as Record<string, unknown>).links = [];
    }],
    ["terminal decision authority", (value: Record<string, unknown>) => {
      const item = value.proposal as Record<string, unknown>;
      item.status = "confirmed";
      item.decision_id = id("a");
      item.decision = "confirm";
      item.decided_at = ACTION_TIME;
      item.confirmation_authority = "owned_native_user_presence";
    }],
  ] as const)("rejects %s proposal drift", (_name, mutate) => {
    const value: Record<string, unknown> = { proposal: proposal(), applied: true };
    mutate(value);
    expect(() => parseRequirementActionGuidedAuthoringProposal(value, proposalExpectation())).toThrow();
  });
});
