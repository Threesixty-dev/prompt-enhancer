import type {
  ClaimGroundingLinkBeginRequest,
  ClaimGroundingLinkObservedCheck,
  ClaimGroundingLinkReview,
} from "./contracts";

export class ClaimGroundingLinkReviewPayloadError extends Error {
  constructor() {
    super("Claim-grounding link review response was invalid");
    this.name = "ClaimGroundingLinkReviewPayloadError";
  }
}

type JsonRecord = Record<string, unknown>;
const ID = /^[a-f0-9]{64}$/u;
const TOP_LEVEL_KEYS = ["session_id", "census_id", "candidate_id", "source_run_id", "source_window_fingerprint", "census_fingerprint", "manifest_fingerprint", "observed_set_fingerprint", "review_receipt_id", "review_fingerprint", "review_expires_at", "claim_clause", "observed_checks", "proposal_only", "measured", "metric_authority_established", "content_persisted"] as const;
const OBSERVED_CHECK_KEYS = ["source_reference_id", "observed_sequence", "outcome", "tool_name", "invocation_preview", "effect_preview"] as const;

function fail(): never { throw new ClaimGroundingLinkReviewPayloadError(); }
function record(value: unknown): JsonRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail();
  return value as JsonRecord;
}
function exactKeys(value: JsonRecord, keys: readonly string[]): void {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) fail();
}
function id(value: unknown): value is string { return typeof value === "string" && ID.test(value); }
function futureIsoTimestamp(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/u.test(value)) return false;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) && timestamp > Date.now();
}
function parseObservedCheck(value: unknown): ClaimGroundingLinkObservedCheck {
  const check = record(value);
  exactKeys(check, OBSERVED_CHECK_KEYS);
  if (!id(check.source_reference_id) || typeof check.observed_sequence !== "number" || !Number.isSafeInteger(check.observed_sequence) || check.observed_sequence < 0 || (check.outcome !== "passed" && check.outcome !== "check_failed") || typeof check.tool_name !== "string" || typeof check.invocation_preview !== "string" || (check.effect_preview !== null && typeof check.effect_preview !== "string")) fail();
  return {
    source_reference_id: check.source_reference_id,
    observed_sequence: check.observed_sequence,
    outcome: check.outcome,
    tool_name: check.tool_name,
    invocation_preview: check.invocation_preview,
    effect_preview: check.effect_preview,
  };
}

export function parseClaimGroundingLinkReview(value: unknown, expected: { sessionId: string; request: ClaimGroundingLinkBeginRequest; source_run_id: string; source_window_fingerprint: string; census_fingerprint: string; manifest_fingerprint: string }): ClaimGroundingLinkReview {
  const review = record(value);
  exactKeys(review, TOP_LEVEL_KEYS);
  const selected = expected.request.selected_check_references;
  if (!id(expected.sessionId) || !id(expected.request.census_id) || !id(expected.request.candidate_id) || !id(expected.source_run_id) || !id(expected.source_window_fingerprint) || !id(expected.census_fingerprint) || !id(expected.manifest_fingerprint) || !Array.isArray(selected) || selected.length > 128 || selected.some((reference) => !id(reference)) || new Set(selected).size !== selected.length || review.session_id !== expected.sessionId || review.census_id !== expected.request.census_id || review.candidate_id !== expected.request.candidate_id || review.source_run_id !== expected.source_run_id || review.source_window_fingerprint !== expected.source_window_fingerprint || review.census_fingerprint !== expected.census_fingerprint || review.manifest_fingerprint !== expected.manifest_fingerprint || !id(review.observed_set_fingerprint) || !id(review.review_receipt_id) || !id(review.review_fingerprint) || !futureIsoTimestamp(review.review_expires_at) || typeof review.claim_clause !== "string" || !Array.isArray(review.observed_checks) || review.observed_checks.length > 128 || review.proposal_only !== true || review.measured !== false || review.metric_authority_established !== false || review.content_persisted !== false) fail();
  const checks = review.observed_checks.map(parseObservedCheck);
  const references = checks.map((check) => check.source_reference_id);
  if (new Set(references).size !== references.length || references.length !== selected.length || selected.some((reference) => !references.includes(reference))) fail();
  return {
    session_id: review.session_id,
    census_id: review.census_id,
    candidate_id: review.candidate_id,
    source_run_id: review.source_run_id,
    source_window_fingerprint: review.source_window_fingerprint,
    census_fingerprint: review.census_fingerprint,
    manifest_fingerprint: review.manifest_fingerprint,
    observed_set_fingerprint: review.observed_set_fingerprint,
    review_receipt_id: review.review_receipt_id,
    review_fingerprint: review.review_fingerprint,
    review_expires_at: review.review_expires_at,
    claim_clause: review.claim_clause,
    observed_checks: checks,
    proposal_only: true,
    measured: false,
    metric_authority_established: false,
    content_persisted: false,
  };
}
