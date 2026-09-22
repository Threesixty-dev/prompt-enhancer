import type {
  RequirementPlanEvidenceContract,
  RequirementPlanGuidedAuthoringCommand,
  RequirementPlanGuidedAuthoringReview,
  RequirementPlanProposal,
} from "./contracts";
import { parseRequirementPlanProposal } from "./requirementPlanEvidenceContract";

export class RequirementPlanGuidedAuthoringPayloadError extends Error {
  constructor() { super("Guided requirement-plan authoring response was invalid"); }
}

const HEX = /^[a-f0-9]{64}$/;
const utc = (value: unknown): value is string => typeof value === "string"
  && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z$/.test(value)
  && Number.isFinite(Date.parse(value));
const row = (value: unknown): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new RequirementPlanGuidedAuthoringPayloadError();
  return value as Record<string, unknown>;
};
const exact = (value: Record<string, unknown>, keys: readonly string[]) => {
  if (Object.keys(value).sort().join("|") !== [...keys].sort().join("|")) throw new RequirementPlanGuidedAuthoringPayloadError();
};
const key = (value: { message_sequence: number; clause_index: number }) => `${value.message_sequence}:${value.clause_index}`;
const canonical = (value: unknown): string => Array.isArray(value) ? `[${value.map(canonical).join(",")}]` : value !== null && typeof value === "object" ? `{${Object.keys(value as Record<string, unknown>).sort().map((k) => `${JSON.stringify(k)}:${canonical((value as Record<string, unknown>)[k])}`).join(",")}}` : JSON.stringify(value);

/** Parse the ephemeral source-text receipt; raw text never crosses into a proposal. */
export function parseRequirementPlanGuidedAuthoringReview(
  value: unknown, expected: { sessionId: string; contract: RequirementPlanEvidenceContract },
): RequirementPlanGuidedAuthoringReview {
  const item = row(value);
  exact(item, ["contract_version", "session_id", "source_run_id", "source_window_fingerprint", "expected_predecessor_confirmation_id", "manifest_fingerprint", "authoring_receipt_id", "candidate_clauses", "review_context_expires_at", "authoring_receipt_expires_at", "all_candidates_included", "raw_text_persisted", "local_only"]);
  const { contract } = expected;
  if (item.contract_version !== "requirement-plan-guided-authoring-v1" || item.session_id !== expected.sessionId
    || item.source_run_id !== contract.expected_source_run_id || item.source_window_fingerprint !== contract.source_window_fingerprint
    || item.expected_predecessor_confirmation_id !== contract.expected_predecessor_confirmation_id
    || item.manifest_fingerprint !== contract.source_manifest.manifest_fingerprint || typeof item.authoring_receipt_id !== "string" || !HEX.test(item.authoring_receipt_id)
    || !Array.isArray(item.candidate_clauses) || item.candidate_clauses.length !== contract.source_manifest.candidate_clause_count
    || item.review_context_expires_at !== contract.source_manifest.review_context_expires_at || !utc(item.review_context_expires_at) || !utc(item.authoring_receipt_expires_at)
    || Date.parse(item.authoring_receipt_expires_at) > Date.parse(item.review_context_expires_at) || Date.parse(item.authoring_receipt_expires_at) <= Date.now() || item.all_candidates_included !== true || item.raw_text_persisted !== false || item.local_only !== true) throw new RequirementPlanGuidedAuthoringPayloadError();
  const expectedClauses = contract.source_manifest.messages.flatMap((message) => ((message.role === "user" && (message.kind === "request" || message.kind === "feedback")) || (message.role === "agent" && message.kind === "plan"))
    ? Array.from({ length: message.clause_count }, (_, clause_index) => ({ message_sequence: message.message_sequence, clause_index, role: message.role, kind: message.kind })) : []);
  const clauses = item.candidate_clauses.map((raw, index) => {
    const clause = row(raw); exact(clause, ["message_sequence", "clause_index", "role", "kind", "text", "candidate_kind"]);
    const wanted = expectedClauses[index];
    if (!wanted || clause.message_sequence !== wanted.message_sequence || clause.clause_index !== wanted.clause_index || clause.role !== wanted.role || clause.kind !== wanted.kind
      || typeof clause.text !== "string" || clause.text.length < 1 || clause.text.length > 16_384 || clause.text !== clause.text.trim() || clause.text.includes("\0")
      || clause.candidate_kind !== (wanted.role === "user" ? "user_clause" : "plan")) throw new RequirementPlanGuidedAuthoringPayloadError();
    return clause;
  });
  if (new Set(clauses.map((clause) => key(clause as { message_sequence: number; clause_index: number }))).size !== clauses.length) throw new RequirementPlanGuidedAuthoringPayloadError();
  return { ...item, candidate_clauses: clauses } as unknown as RequirementPlanGuidedAuthoringReview;
}

/** Validates the inert, local-user authored proposal before it can enter UI state. */
export function parseRequirementPlanGuidedAuthoringProposal(
  value: unknown, expected: { sessionId: string; command: RequirementPlanGuidedAuthoringCommand },
): { proposal: RequirementPlanProposal; applied: boolean } {
  const item = row(value); exact(item, ["proposal", "applied"]);
  if (typeof item.applied !== "boolean") throw new RequirementPlanGuidedAuthoringPayloadError();
  const proposal = parseRequirementPlanProposal(item.proposal);
  const c = expected.command;
  if (proposal.session_id !== expected.sessionId || proposal.source_run_id !== c.expected_source_run_id || proposal.source_window_fingerprint !== c.source_window_fingerprint || proposal.expected_predecessor_confirmation_id !== c.expected_predecessor_confirmation_id || proposal.status !== "proposed" || proposal.decision !== null || proposal.decision_id !== null || proposal.decided_at !== null || proposal.confirmation_authority !== null || proposal.producer_receipt.kind !== "local_review_ui" || proposal.producer_receipt.authority !== "untrusted_local_authoring_commitment" || proposal.producer_receipt.raw_claim_persisted !== false || canonical(proposal.requirements) !== canonical(c.requirements) || canonical(proposal.excluded_user_clauses) !== canonical(c.excluded_user_clauses) || canonical(proposal.plan_items) !== canonical(c.plan_items)) throw new RequirementPlanGuidedAuthoringPayloadError();
  return { proposal, applied: item.applied };
}
