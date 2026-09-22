import { describe, expect, it } from "vitest";
import {
  ClaimGroundingLinkReviewPayloadError,
  parseClaimGroundingLinkReview,
} from "./claimGroundingLinkReviewContract";

const id = (hex: string) => hex.repeat(64).slice(0, 64);
const SESSION = id("a");
const CENSUS = id("b");
const CANDIDATE = id("c");
const RUN = id("d");
const WINDOW = id("e");
const CENSUS_FP = id("f");
const MANIFEST_FP = id("0");
const REFERENCE = id("1");

const expected = {
  sessionId: SESSION,
  request: {
    census_id: CENSUS,
    candidate_id: CANDIDATE,
    selected_check_references: [REFERENCE],
  },
  source_run_id: RUN,
  source_window_fingerprint: WINDOW,
  census_fingerprint: CENSUS_FP,
  manifest_fingerprint: MANIFEST_FP,
};

function review(): Record<string, unknown> {
  return {
    session_id: SESSION,
    census_id: CENSUS,
    candidate_id: CANDIDATE,
    source_run_id: RUN,
    source_window_fingerprint: WINDOW,
    census_fingerprint: CENSUS_FP,
    manifest_fingerprint: MANIFEST_FP,
    observed_set_fingerprint: id("2"),
    review_receipt_id: id("3"),
    review_fingerprint: id("4"),
    review_expires_at: new Date(Date.now() + 60_000).toISOString(),
    claim_clause: "Synthetic claim clause.",
    observed_checks: [{
      source_reference_id: REFERENCE,
      observed_sequence: Number.MAX_SAFE_INTEGER,
      outcome: "passed",
      tool_name: "synthetic-check",
      invocation_preview: "synthetic invocation",
      effect_preview: null,
    }],
    proposal_only: true,
    measured: false,
    metric_authority_established: false,
    content_persisted: false,
  };
}

describe("claim grounding link review contract", () => {
  it("accepts an exact, content-free review", () => {
    expect(parseClaimGroundingLinkReview(review(), expected).observed_checks[0].observed_sequence)
      .toBe(Number.MAX_SAFE_INTEGER);
  });

  it.each([
    (value: Record<string, unknown>) => { (value.observed_checks as Record<string, unknown>[])[0].outcome = "unknown"; },
    (value: Record<string, unknown>) => { (value.observed_checks as Record<string, unknown>[])[0].observed_sequence = 1.5; },
    (value: Record<string, unknown>) => { (value.observed_checks as Record<string, unknown>[])[0].extra = true; },
    (value: Record<string, unknown>) => { value.review_receipt_id = 42; },
    (value: Record<string, unknown>) => { value.review_expires_at = "2999-01-01"; },
    (value: Record<string, unknown>) => { value.candidate_id = id("9"); },
  ])("rejects unsafe or drifting payloads", (alter) => {
    const value = structuredClone(review());
    alter(value);
    expect(() => parseClaimGroundingLinkReview(value, expected))
      .toThrow(ClaimGroundingLinkReviewPayloadError);
  });

  it("requires unique observed references to equal the selected references", () => {
    const value = review();
    (value.observed_checks as Record<string, unknown>[]).push({
      ...(value.observed_checks as Record<string, unknown>[])[0],
      source_reference_id: id("5"),
    });
    expect(() => parseClaimGroundingLinkReview(value, expected))
      .toThrow(ClaimGroundingLinkReviewPayloadError);
  });

  it("exposes only the generic parser error", () => {
    expect(() => parseClaimGroundingLinkReview({ ...review(), unexpected: true }, expected))
      .toThrowError(new ClaimGroundingLinkReviewPayloadError());
  });
});
