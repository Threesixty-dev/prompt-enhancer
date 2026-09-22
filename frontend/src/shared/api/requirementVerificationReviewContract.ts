import type { RequirementVerificationOpportunityReview } from "./contracts";

const HEX = /^[a-f0-9]{64}$/;

export class RequirementVerificationReviewPayloadError extends Error {
  constructor() { super("Requirement-verification review response was invalid"); this.name = "RequirementVerificationReviewPayloadError"; }
}

function fail(): never { throw new RequirementVerificationReviewPayloadError(); }
function rec(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail();
  return value as Record<string, unknown>;
}
function keys(value: Record<string, unknown>, expected: readonly string[]): void {
  const actual = Object.keys(value).sort(); const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) fail();
}
function id(value: unknown): value is string { return typeof value === "string" && HEX.test(value); }
function integer(value: unknown, minimum: number, maximum: number): value is number { return typeof value === "number" && Number.isSafeInteger(value) && value >= minimum && value <= maximum; }

/** Strict parser for the one-time local clause reader. The text is never persisted here. */
export function parseRequirementVerificationOpportunityReview(value: unknown, sessionId: string): RequirementVerificationOpportunityReview {
  const review = rec(value);
  keys(review, ["content_persisted", "coordinate", "expected_predecessor_authority_id", "expected_source_run_id", "local_only", "opportunity_id", "opportunity_set_fingerprint", "policy_version", "requirement_id", "requirement_plan_confirmation_id", "requirement_plan_proposal_id", "requirement_text", "review_expires_at", "review_fingerprint", "review_receipt_id", "schema_version", "session_id", "source_window_fingerprint", "through_revision"]);
  const coordinate = rec(review.coordinate);
  keys(coordinate, ["clause_index", "message_sequence"]);
  const expiry = Date.parse(String(review.review_expires_at));
  if (review.schema_version !== "requirement-verification-native-review-v1" || review.policy_version !== "current-r8-reviewed-r6-clause-only-v1" || review.session_id !== sessionId || !id(sessionId) || !id(review.opportunity_set_fingerprint) || !id(review.opportunity_id) || !id(review.requirement_id) || !id(review.expected_source_run_id) || !id(review.source_window_fingerprint) || !id(review.requirement_plan_confirmation_id) || !id(review.requirement_plan_proposal_id) || !id(review.review_receipt_id) || !id(review.review_fingerprint) || (review.expected_predecessor_authority_id !== null && !id(review.expected_predecessor_authority_id)) || typeof review.requirement_text !== "string" || review.requirement_text.length === 0 || review.requirement_text.length > 32000 || typeof review.review_expires_at !== "string" || !Number.isFinite(expiry) || expiry <= Date.now() || expiry > Date.now() + 10 * 60_000 || !integer(review.through_revision, 0, 32000) || !integer(coordinate.message_sequence, 0, 1_000_000_000) || !integer(coordinate.clause_index, 0, 127) || review.local_only !== true || review.content_persisted !== false) fail();
  return review as unknown as RequirementVerificationOpportunityReview;
}
