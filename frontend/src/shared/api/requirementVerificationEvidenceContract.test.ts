import { describe, expect, it } from "vitest";
import type { ModelRequirementVerificationEvidenceBinding } from "./contracts";
import {
  parseRequirementVerificationEvidenceMutation,
  parseRequirementVerificationEvidenceSnapshot,
  RequirementVerificationEvidencePayloadError,
} from "./requirementVerificationEvidenceContract";

const id = (character: string): string => character.repeat(64);
const sessionId = id("a");

type TestSnapshot = {
  evidence: {
    opportunities: {
      session_id: string;
      source_window_fingerprint: string;
      requirement_plan_confirmation_id: string;
      requirement_plan_proposal_id: string;
      requirement_plan_evidence_fingerprint: string;
      requirement_plan_schema_version: string;
      requirement_plan_policy_version: string;
      requirement_plan_review_rubric_version: string;
      issuer_version: string;
      evidence_schema_version: string;
      evidence_policy_version: string;
      complete_active_requirement_enumeration: boolean;
      opportunities: Array<{ opportunity_id: string; requirement_index: number; requirement_id: string; coordinate: { message_sequence: number; clause_index: number } }>;
      opportunity_set_fingerprint: string;
      local_only: boolean;
      content_persisted: boolean;
    };
    verification_results: Array<Record<string, unknown>>;
    acceptance_authorities: Array<Record<string, unknown>>;
    projection_version: string;
    evidence_schema_version: string;
    evidence_policy_version: string;
    evidence_set_fingerprint: string;
    local_only: boolean;
    content_persisted: boolean;
  };
  revision: number;
  authority_heads: Array<{ opportunity_id: string; authority_record_id: string; kind: "objective_result" | "native_acceptance"; revision: number }>;
  persistence_schema_version: string;
  local_only: boolean;
  content_persisted: boolean;
};

function emptySnapshot(): TestSnapshot {
  return {
    evidence: {
      opportunities: {
        session_id: sessionId,
        source_window_fingerprint: id("b"),
        requirement_plan_confirmation_id: id("c"),
        requirement_plan_proposal_id: id("d"),
        requirement_plan_evidence_fingerprint: id("e"),
        requirement_plan_schema_version: "requirement-plan-evidence-v1",
        requirement_plan_policy_version: "reviewed-requirement-plan-v1",
        requirement_plan_review_rubric_version: "active-requirement-plan-review-rubric-v1",
        issuer_version: "reviewed-r6-requirement-opportunity-issuer-v1",
        evidence_schema_version: "requirement-verification-evidence-v1",
        evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
        complete_active_requirement_enumeration: true,
        opportunities: [],
        opportunity_set_fingerprint: id("f"),
        local_only: true,
        content_persisted: false,
      },
      verification_results: [],
      acceptance_authorities: [],
      projection_version: "reviewed-requirement-verification-objective-projection-v1",
      evidence_schema_version: "requirement-verification-evidence-v1",
      evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
      evidence_set_fingerprint: id("0"),
      local_only: true,
      content_persisted: false,
    },
    revision: 0,
    authority_heads: [],
    persistence_schema_version: "requirement-verification-persistence-v1",
    local_only: true,
    content_persisted: false,
  };
}

function mixedSnapshot(): TestSnapshot {
  const snapshot = emptySnapshot();
  snapshot.evidence.opportunities.opportunities = [
    { opportunity_id: id("1"), requirement_index: 0, requirement_id: id("2"), coordinate: { message_sequence: 3, clause_index: 4 } },
    { opportunity_id: id("5"), requirement_index: 1, requirement_id: id("6"), coordinate: { message_sequence: 7, clause_index: 8 } },
  ];
  snapshot.evidence.verification_results = [{
    result_id: id("9"), opportunity_set_fingerprint: id("f"), opportunity_id: id("1"),
    requirement_id: id("2"), observed_sequence: 10, method: "test", outcome: "unknown",
    receipt_reference_ids: [id("b"), id("c")], authority_kind: "app_objective_verifier",
    issuer_version: "local-objective-verification-result-issuer-v1",
    evidence_schema_version: "requirement-verification-evidence-v1",
    evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
    result_fingerprint: id("d"), app_issued: true, local_only: true, content_persisted: false,
  }];
  snapshot.evidence.acceptance_authorities = [{
    acceptance_id: id("a"), opportunity_set_fingerprint: id("f"), opportunity_id: id("5"),
    requirement_id: id("6"), confirmation_id: id("e"), outcome: "unknown",
    authority_kind: "native_user_acceptance", issuer_version: "native-explicit-requirement-acceptance-issuer-v1",
    evidence_schema_version: "requirement-verification-evidence-v1",
    evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
    acceptance_fingerprint: id("0"), owned_native_action: true, local_only: true, content_persisted: false,
  }];
  snapshot.revision = 2;
  snapshot.authority_heads = [
    { opportunity_id: id("1"), authority_record_id: id("9"), kind: "objective_result", revision: 1 },
    { opportunity_id: id("5"), authority_record_id: id("a"), kind: "native_acceptance", revision: 2 },
  ];
  return snapshot;
}

function binding(source: "awaiting_evidence" | "persisted_evidence", snapshot: TestSnapshot): ModelRequirementVerificationEvidenceBinding {
  const persisted = source === "persisted_evidence";
  return {
    evidence_source: source,
    requirement_plan_confirmation_id: snapshot.evidence.opportunities.requirement_plan_confirmation_id,
    requirement_plan_proposal_id: snapshot.evidence.opportunities.requirement_plan_proposal_id,
    requirement_plan_evidence_fingerprint: snapshot.evidence.opportunities.requirement_plan_evidence_fingerprint,
    requirement_plan_schema_version: "requirement-plan-evidence-v1",
    requirement_plan_policy_version: "reviewed-requirement-plan-v1",
    requirement_plan_review_rubric_version: "active-requirement-plan-review-rubric-v1",
    opportunity_count: 2,
    opportunity_set_fingerprint: snapshot.evidence.opportunities.opportunity_set_fingerprint,
    evidence_set_fingerprint: persisted ? snapshot.evidence.evidence_set_fingerprint : null,
    through_revision: persisted ? snapshot.revision : null,
    authority_head_count: persisted ? 2 : 0,
    objective_result_count: persisted ? 1 : 0,
    native_acceptance_count: persisted ? 1 : 0,
    resolved_opportunity_count: 0,
    met_requirement_count: 0,
    opportunity_issuer_version: "reviewed-r6-requirement-opportunity-issuer-v1",
    result_issuer_version: "local-objective-verification-result-issuer-v1",
    acceptance_issuer_version: "native-explicit-requirement-acceptance-issuer-v1",
    evidence_schema_version: "requirement-verification-evidence-v1",
    evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
    persistence_schema_version: "requirement-verification-persistence-v1",
    evidence_projection_version: "reviewed-requirement-verification-objective-projection-v1",
    objective_projection_version: "reviewed-requirement-verification-objective-projection-v1",
    binding_schema_version: "session-requirement-verification-evidence-binding-v1",
    binding_fingerprint: id("b"), local_only: true, content_persisted: false,
  };
}

describe("requirement-verification evidence contract", () => {
  it("accepts empty, mixed, and current-head-only superseded snapshots", () => {
    expect(parseRequirementVerificationEvidenceSnapshot(emptySnapshot(), sessionId)).toEqual(emptySnapshot());
    const mixed = mixedSnapshot();
    expect(parseRequirementVerificationEvidenceSnapshot(mixed, sessionId, binding("persisted_evidence", mixed))).toEqual(mixed);
    const superseded = mixedSnapshot();
    superseded.evidence.verification_results[0] = { ...superseded.evidence.verification_results[0], result_id: id("8"), result_fingerprint: id("7"), outcome: "failed" };
    superseded.revision = 3;
    superseded.authority_heads[0] = { opportunity_id: id("1"), authority_record_id: id("8"), kind: "objective_result", revision: 3 };
    expect(parseRequirementVerificationEvidenceSnapshot(superseded, sessionId)).toEqual(superseded);
  });

  it("allows an awaiting binding to advance, but pins persisted evidence exactly", () => {
    const current = mixedSnapshot();
    expect(parseRequirementVerificationEvidenceSnapshot(current, sessionId, binding("awaiting_evidence", current))).toEqual(current);
    const expected = binding("persisted_evidence", current);
    const changed = mixedSnapshot();
    changed.revision = 3;
    expect(() => parseRequirementVerificationEvidenceSnapshot(changed, sessionId, expected)).toThrow(RequirementVerificationEvidencePayloadError);
  });

  it("rejects malformed records, cross-links, count drift, and private additions", () => {
    const base = mixedSnapshot();
    const invalid = [
      { ...base, unexpected: true },
      { ...base, revision: -1 },
      { ...base, authority_heads: [{ ...base.authority_heads[0], extra: true }, base.authority_heads[1]] },
      { ...base, evidence: { ...base.evidence, private_note: "no" } },
      { ...base, evidence: { ...base.evidence, verification_results: [{ ...base.evidence.verification_results[0], private_note: "no" }] } },
      { ...base, evidence: { ...base.evidence, acceptance_authorities: [{ ...base.evidence.acceptance_authorities[0], private_note: "no" }] } },
      { ...base, evidence: { ...base.evidence, opportunities: { ...base.evidence.opportunities, session_id: id("b") } } },
      { ...base, evidence: { ...base.evidence, opportunities: { ...base.evidence.opportunities, opportunities: [{ ...base.evidence.opportunities.opportunities[0], coordinate: { ...base.evidence.opportunities.opportunities[0].coordinate, private_note: "no" } }, base.evidence.opportunities.opportunities[1]] } } },
      { ...base, evidence: { ...base.evidence, opportunities: { ...base.evidence.opportunities, opportunities: [{ ...base.evidence.opportunities.opportunities[0], requirement_index: 1 }, base.evidence.opportunities.opportunities[1]] } } },
      { ...base, evidence: { ...base.evidence, opportunities: { ...base.evidence.opportunities, opportunities: [{ ...base.evidence.opportunities.opportunities[0], coordinate: { message_sequence: 1, clause_index: 128 } }, base.evidence.opportunities.opportunities[1]] } } },
      { ...base, evidence: { ...base.evidence, verification_results: [{ ...base.evidence.verification_results[0], opportunity_set_fingerprint: id("0") }] } },
      { ...base, evidence: { ...base.evidence, verification_results: [{ ...base.evidence.verification_results[0], requirement_id: id("6") }] } },
      { ...base, evidence: { ...base.evidence, verification_results: [{ ...base.evidence.verification_results[0], method: "human_review" }] } },
      { ...base, evidence: { ...base.evidence, verification_results: [{ ...base.evidence.verification_results[0], outcome: "accepted" }] } },
      { ...base, evidence: { ...base.evidence, verification_results: [{ ...base.evidence.verification_results[0], receipt_reference_ids: [] }] } },
      { ...base, evidence: { ...base.evidence, verification_results: [{ ...base.evidence.verification_results[0], receipt_reference_ids: [id("c"), id("b")] }] } },
      { ...base, evidence: { ...base.evidence, verification_results: [{ ...base.evidence.verification_results[0], authority_kind: "native_user_acceptance" }] } },
      { ...base, evidence: { ...base.evidence, acceptance_authorities: [{ ...base.evidence.acceptance_authorities[0], owned_native_action: false }] } },
      { ...base, evidence: { ...base.evidence, acceptance_authorities: [{ ...base.evidence.acceptance_authorities[0], opportunity_id: id("1"), requirement_id: id("2") }] } },
      { ...base, authority_heads: [base.authority_heads[1], base.authority_heads[0]] },
      { ...base, authority_heads: [{ ...base.authority_heads[0], authority_record_id: id("7") }, base.authority_heads[1]] },
      { ...base, authority_heads: [{ ...base.authority_heads[0], revision: 4 }, base.authority_heads[1]] },
      { snapshot: base, applied: "yes" },
    ];
    for (const candidate of invalid) {
      const parse = "snapshot" in candidate
        ? () => parseRequirementVerificationEvidenceMutation(candidate, sessionId)
        : () => parseRequirementVerificationEvidenceSnapshot(candidate, sessionId);
      expect(parse).toThrow(RequirementVerificationEvidencePayloadError);
      expect(parse).toThrow("Requirement-verification evidence response was invalid");
    }
    const expected = binding("persisted_evidence", base);
    for (const drift of [
      { ...expected, evidence_set_fingerprint: id("7") },
      { ...expected, authority_head_count: 1 },
      { ...expected, objective_result_count: 0 },
      { ...expected, native_acceptance_count: 0 },
      { ...expected, resolved_opportunity_count: 1 },
      { ...expected, met_requirement_count: 1 },
      { ...expected, requirement_plan_confirmation_id: id("7") },
      { ...expected, requirement_plan_proposal_id: id("7") },
      { ...expected, requirement_plan_evidence_fingerprint: id("7") },
      { ...expected, opportunity_set_fingerprint: id("7") },
      { ...expected, opportunity_count: 1 },
    ]) expect(() => parseRequirementVerificationEvidenceSnapshot(base, sessionId, drift)).toThrow(RequirementVerificationEvidencePayloadError);
  });
});
