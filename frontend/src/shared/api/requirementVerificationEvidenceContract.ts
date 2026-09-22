import type {
  ModelRequirementVerificationEvidenceBinding,
  RequirementVerificationEvidenceMutation,
  RequirementVerificationEvidenceSnapshot,
} from "./contracts";

const HEX_64 = /^[a-f0-9]{64}$/;
const MAX_OPPORTUNITIES = 1_000;
const MAX_RECEIPTS = 16;
const MAX_REVISIONS = 32_000;
const MAX_OBSERVED_SEQUENCE = 2 ** 63 - 1;
const EVIDENCE_SCHEMA = "requirement-verification-evidence-v1";
const EVIDENCE_POLICY = "app-issued-reviewed-requirement-verification-v1";
const OPPORTUNITY_ISSUER = "reviewed-r6-requirement-opportunity-issuer-v1";
const RESULT_ISSUER = "local-objective-verification-result-issuer-v1";
const ACCEPTANCE_ISSUER = "native-explicit-requirement-acceptance-issuer-v1";
const PROJECTION = "reviewed-requirement-verification-objective-projection-v1";
const PERSISTENCE_SCHEMA = "requirement-verification-persistence-v1";

type JsonRecord = Record<string, unknown>;
type AuthorityKind = "objective_result" | "native_acceptance";
type AuthorityReference = { opportunityId: string; recordId: string; kind: AuthorityKind; resolved: boolean; met: boolean };

export type RequirementVerificationSnapshotExpectation = ModelRequirementVerificationEvidenceBinding;

export class RequirementVerificationEvidencePayloadError extends Error {
  constructor() {
    super("Requirement-verification evidence response was invalid");
    this.name = "RequirementVerificationEvidencePayloadError";
  }
}

function fail(): never { throw new RequirementVerificationEvidencePayloadError(); }
function record(value: unknown): JsonRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail();
  return value as JsonRecord;
}
function exactKeys(value: JsonRecord, expected: readonly string[]): void {
  const actual = Object.keys(value).sort();
  const sortedExpected = [...expected].sort();
  if (actual.length !== sortedExpected.length || actual.some((key, index) => key !== sortedExpected[index])) fail();
}
function pseudonym(value: unknown): value is string { return typeof value === "string" && HEX_64.test(value); }
function safeInteger(value: unknown, minimum: number, maximum: number): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= minimum && value <= maximum;
}
function isSortedUnique(values: readonly string[]): boolean {
  return values.every((value, index) => index === 0 || values[index - 1] < value);
}

function parseOpportunitySet(value: unknown, sessionId: string): { opportunities: Map<string, string>; scope: JsonRecord } {
  const scope = record(value);
  exactKeys(scope, ["complete_active_requirement_enumeration", "content_persisted", "evidence_policy_version", "evidence_schema_version", "issuer_version", "local_only", "opportunities", "opportunity_set_fingerprint", "requirement_plan_confirmation_id", "requirement_plan_evidence_fingerprint", "requirement_plan_policy_version", "requirement_plan_proposal_id", "requirement_plan_review_rubric_version", "requirement_plan_schema_version", "session_id", "source_window_fingerprint"]);
  if (
    scope.session_id !== sessionId || !pseudonym(scope.session_id)
    || !pseudonym(scope.source_window_fingerprint) || !pseudonym(scope.requirement_plan_confirmation_id)
    || !pseudonym(scope.requirement_plan_proposal_id) || !pseudonym(scope.requirement_plan_evidence_fingerprint)
    || !pseudonym(scope.opportunity_set_fingerprint) || scope.requirement_plan_schema_version !== "requirement-plan-evidence-v1"
    || scope.requirement_plan_policy_version !== "reviewed-requirement-plan-v1"
    || scope.requirement_plan_review_rubric_version !== "active-requirement-plan-review-rubric-v1"
    || scope.issuer_version !== OPPORTUNITY_ISSUER || scope.evidence_schema_version !== EVIDENCE_SCHEMA
    || scope.evidence_policy_version !== EVIDENCE_POLICY || scope.complete_active_requirement_enumeration !== true
    || scope.local_only !== true || scope.content_persisted !== false || !Array.isArray(scope.opportunities)
    || scope.opportunities.length > MAX_OPPORTUNITIES
  ) fail();
  const opportunities = new Map<string, string>();
  const requirementIds: string[] = [];
  for (let index = 0; index < scope.opportunities.length; index += 1) {
    const opportunity = record(scope.opportunities[index]);
    exactKeys(opportunity, ["coordinate", "opportunity_id", "requirement_id", "requirement_index"]);
    const coordinate = record(opportunity.coordinate);
    exactKeys(coordinate, ["clause_index", "message_sequence"]);
    if (
      !pseudonym(opportunity.opportunity_id) || !pseudonym(opportunity.requirement_id)
      || !safeInteger(opportunity.requirement_index, 0, MAX_OPPORTUNITIES - 1)
      || opportunity.requirement_index !== index || !safeInteger(coordinate.message_sequence, 0, 1_000_000_000)
      || !safeInteger(coordinate.clause_index, 0, 127) || opportunities.has(opportunity.opportunity_id)
    ) fail();
    opportunities.set(opportunity.opportunity_id, opportunity.requirement_id);
    requirementIds.push(opportunity.requirement_id);
  }
  if (!isSortedUnique(requirementIds)) fail();
  return { opportunities, scope };
}

function parseObjectiveAuthority(value: unknown, opportunities: Map<string, string>, opportunitySetFingerprint: string): AuthorityReference {
  const result = record(value);
  exactKeys(result, ["app_issued", "authority_kind", "content_persisted", "evidence_policy_version", "evidence_schema_version", "issuer_version", "local_only", "method", "observed_sequence", "opportunity_id", "opportunity_set_fingerprint", "outcome", "receipt_reference_ids", "requirement_id", "result_fingerprint", "result_id"]);
  if (
    !pseudonym(result.result_id) || !pseudonym(result.opportunity_set_fingerprint)
    || result.opportunity_set_fingerprint !== opportunitySetFingerprint || !pseudonym(result.opportunity_id)
    || !pseudonym(result.requirement_id) || opportunities.get(result.opportunity_id) !== result.requirement_id
    || !safeInteger(result.observed_sequence, 0, MAX_OBSERVED_SEQUENCE)
    || !["test", "static_check", "build", "artifact_inspection", "other_documented"].includes(result.method as string)
    || !["passed", "failed", "unknown"].includes(result.outcome as string)
    || !Array.isArray(result.receipt_reference_ids) || result.receipt_reference_ids.length < 1
    || result.receipt_reference_ids.length > MAX_RECEIPTS || !result.receipt_reference_ids.every(pseudonym)
    || !isSortedUnique(result.receipt_reference_ids) || result.authority_kind !== "app_objective_verifier"
    || result.issuer_version !== RESULT_ISSUER || result.evidence_schema_version !== EVIDENCE_SCHEMA
    || result.evidence_policy_version !== EVIDENCE_POLICY || !pseudonym(result.result_fingerprint)
    || result.app_issued !== true || result.local_only !== true || result.content_persisted !== false
  ) fail();
  return { opportunityId: result.opportunity_id, recordId: result.result_id, kind: "objective_result", resolved: result.outcome !== "unknown", met: result.outcome === "passed" };
}

function parseNativeAcceptance(value: unknown, opportunities: Map<string, string>, opportunitySetFingerprint: string): AuthorityReference {
  const acceptance = record(value);
  exactKeys(acceptance, ["acceptance_fingerprint", "acceptance_id", "authority_kind", "confirmation_id", "content_persisted", "evidence_policy_version", "evidence_schema_version", "issuer_version", "local_only", "opportunity_id", "opportunity_set_fingerprint", "outcome", "owned_native_action", "requirement_id"]);
  if (
    !pseudonym(acceptance.acceptance_id) || !pseudonym(acceptance.opportunity_set_fingerprint)
    || acceptance.opportunity_set_fingerprint !== opportunitySetFingerprint || !pseudonym(acceptance.opportunity_id)
    || !pseudonym(acceptance.requirement_id) || opportunities.get(acceptance.opportunity_id) !== acceptance.requirement_id
    || !pseudonym(acceptance.confirmation_id) || !["accepted", "rejected", "unknown"].includes(acceptance.outcome as string)
    || acceptance.authority_kind !== "native_user_acceptance" || acceptance.issuer_version !== ACCEPTANCE_ISSUER
    || acceptance.evidence_schema_version !== EVIDENCE_SCHEMA || acceptance.evidence_policy_version !== EVIDENCE_POLICY
    || !pseudonym(acceptance.acceptance_fingerprint) || acceptance.owned_native_action !== true
    || acceptance.local_only !== true || acceptance.content_persisted !== false
  ) fail();
  return { opportunityId: acceptance.opportunity_id, recordId: acceptance.acceptance_id, kind: "native_acceptance", resolved: acceptance.outcome !== "unknown", met: acceptance.outcome === "accepted" };
}

function parseEvidence(value: unknown, sessionId: string): { authorities: AuthorityReference[]; opportunityCount: number; scope: JsonRecord; evidenceSetFingerprint: string } {
  const evidence = record(value);
  exactKeys(evidence, ["acceptance_authorities", "content_persisted", "evidence_policy_version", "evidence_schema_version", "evidence_set_fingerprint", "local_only", "opportunities", "projection_version", "verification_results"]);
  if (evidence.projection_version !== PROJECTION || evidence.evidence_schema_version !== EVIDENCE_SCHEMA || evidence.evidence_policy_version !== EVIDENCE_POLICY || !pseudonym(evidence.evidence_set_fingerprint) || evidence.local_only !== true || evidence.content_persisted !== false || !Array.isArray(evidence.verification_results) || !Array.isArray(evidence.acceptance_authorities) || evidence.verification_results.length > MAX_OPPORTUNITIES || evidence.acceptance_authorities.length > MAX_OPPORTUNITIES) fail();
  const { opportunities, scope } = parseOpportunitySet(evidence.opportunities, sessionId);
  const opportunitySetFingerprint = scope.opportunity_set_fingerprint;
  if (!pseudonym(opportunitySetFingerprint)) fail();
  const results = evidence.verification_results.map((item) => parseObjectiveAuthority(item, opportunities, opportunitySetFingerprint));
  const acceptances = evidence.acceptance_authorities.map((item) => parseNativeAcceptance(item, opportunities, opportunitySetFingerprint));
  if (!isSortedUnique(results.map(({ opportunityId }) => opportunityId)) || !isSortedUnique(acceptances.map(({ opportunityId }) => opportunityId))) fail();
  const seen = new Set<string>();
  for (const authority of [...results, ...acceptances]) { if (seen.has(authority.opportunityId)) fail(); seen.add(authority.opportunityId); }
  return { authorities: [...results, ...acceptances], opportunityCount: opportunities.size, scope, evidenceSetFingerprint: evidence.evidence_set_fingerprint };
}

function validateHeads(value: unknown, revision: number, authorities: readonly AuthorityReference[]): void {
  if (!Array.isArray(value) || value.length > MAX_OPPORTUNITIES) fail();
  const expected = new Map(authorities.map(({ opportunityId, recordId, kind }) => [opportunityId, { recordId, kind }]));
  const actual = new Map<string, { recordId: string; kind: AuthorityKind }>();
  const opportunityIds: string[] = [];
  for (const item of value) {
    const head = record(item);
    exactKeys(head, ["authority_record_id", "kind", "opportunity_id", "revision"]);
    if (!pseudonym(head.authority_record_id) || !pseudonym(head.opportunity_id) || (head.kind !== "objective_result" && head.kind !== "native_acceptance") || !safeInteger(head.revision, 1, MAX_REVISIONS) || head.revision > revision || actual.has(head.opportunity_id)) fail();
    actual.set(head.opportunity_id, { recordId: head.authority_record_id, kind: head.kind });
    opportunityIds.push(head.opportunity_id);
  }
  if (!isSortedUnique(opportunityIds) || actual.size !== expected.size) fail();
  for (const [opportunityId, expectedHead] of expected) {
    const actualHead = actual.get(opportunityId);
    if (actualHead === undefined || actualHead.recordId !== expectedHead.recordId || actualHead.kind !== expectedHead.kind) fail();
  }
}

function validateExpected(expected: RequirementVerificationSnapshotExpectation | undefined, evidence: { authorities: AuthorityReference[]; opportunityCount: number; scope: JsonRecord; evidenceSetFingerprint: string }, revision: number): void {
  if (expected === undefined) return;
  const scopeMatches = expected.requirement_plan_confirmation_id === evidence.scope.requirement_plan_confirmation_id && expected.requirement_plan_proposal_id === evidence.scope.requirement_plan_proposal_id && expected.requirement_plan_evidence_fingerprint === evidence.scope.requirement_plan_evidence_fingerprint && expected.opportunity_set_fingerprint === evidence.scope.opportunity_set_fingerprint && expected.opportunity_count === evidence.opportunityCount;
  if (!scopeMatches) fail();
  if (expected.evidence_source === "awaiting_evidence") return;
  if (expected.evidence_source !== "persisted_evidence") fail();
  const objectiveCount = evidence.authorities.filter(({ kind }) => kind === "objective_result").length;
  const nativeCount = evidence.authorities.length - objectiveCount;
  const resolvedCount = evidence.authorities.filter(({ resolved }) => resolved).length;
  const metCount = evidence.authorities.filter(({ met }) => met).length;
  if (expected.through_revision !== revision || expected.evidence_set_fingerprint !== evidence.evidenceSetFingerprint || expected.authority_head_count !== evidence.authorities.length || expected.objective_result_count !== objectiveCount || expected.native_acceptance_count !== nativeCount || expected.resolved_opportunity_count !== resolvedCount || expected.met_requirement_count !== metCount) fail();
}

export function parseRequirementVerificationEvidenceSnapshot(value: unknown, sessionId: string, expected?: RequirementVerificationSnapshotExpectation): RequirementVerificationEvidenceSnapshot {
  if (!pseudonym(sessionId)) fail();
  const snapshot = record(value);
  exactKeys(snapshot, ["authority_heads", "content_persisted", "evidence", "local_only", "persistence_schema_version", "revision"]);
  if (!safeInteger(snapshot.revision, 0, MAX_REVISIONS) || snapshot.persistence_schema_version !== PERSISTENCE_SCHEMA || snapshot.local_only !== true || snapshot.content_persisted !== false) fail();
  const evidence = parseEvidence(snapshot.evidence, sessionId);
  validateHeads(snapshot.authority_heads, snapshot.revision, evidence.authorities);
  validateExpected(expected, evidence, snapshot.revision);
  return snapshot as unknown as RequirementVerificationEvidenceSnapshot;
}

export function parseRequirementVerificationEvidenceMutation(value: unknown, sessionId: string, expected?: RequirementVerificationSnapshotExpectation): RequirementVerificationEvidenceMutation {
  const mutation = record(value);
  exactKeys(mutation, ["applied", "snapshot"]);
  if (typeof mutation.applied !== "boolean") fail();
  return { applied: mutation.applied, snapshot: parseRequirementVerificationEvidenceSnapshot(mutation.snapshot, sessionId, expected) };
}
