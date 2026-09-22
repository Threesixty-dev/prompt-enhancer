import { describe, expect, it } from "vitest";
import { parseRequirementVerificationOpportunityReview, RequirementVerificationReviewPayloadError } from "./requirementVerificationReviewContract";

const SESSION = "1".repeat(64);
const review = () => ({
  schema_version: "requirement-verification-native-review-v1" as const, policy_version: "current-r8-reviewed-r6-clause-only-v1" as const,
  session_id: SESSION, opportunity_set_fingerprint: "2".repeat(64), opportunity_id: "3".repeat(64), requirement_id: "4".repeat(64),
  coordinate: { message_sequence: 2, clause_index: 1 }, expected_source_run_id: "5".repeat(64), source_window_fingerprint: "6".repeat(64),
  requirement_plan_confirmation_id: "7".repeat(64), requirement_plan_proposal_id: "8".repeat(64), expected_predecessor_authority_id: null,
  through_revision: 4, review_receipt_id: "9".repeat(64), review_fingerprint: "a".repeat(64), review_expires_at: new Date(Date.now() + 60_000).toISOString(),
  requirement_text: "Synthetic requirement clause", local_only: true, content_persisted: false,
});

describe("requirement verification review contract", () => {
  it("accepts only the exact ephemeral local review shape", () => { const value = review(); expect(parseRequirementVerificationOpportunityReview(value, SESSION)).toEqual(value); });
  it.each([
    (value: ReturnType<typeof review>) => { value.requirement_text = ""; },
    (value: ReturnType<typeof review>) => { value.session_id = "b".repeat(64); },
    (value: ReturnType<typeof review>) => { value.review_expires_at = "not-a-date"; },
    (value: ReturnType<typeof review>) => { (value as Record<string, unknown>).extra = true; },
  ])("rejects malformed or drifted review data", (alter) => {
    const value = review(); alter(value);
    expect(() => parseRequirementVerificationOpportunityReview(value, SESSION)).toThrow(RequirementVerificationReviewPayloadError);
  });
});
