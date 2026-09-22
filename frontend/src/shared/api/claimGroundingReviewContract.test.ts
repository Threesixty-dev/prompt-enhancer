import { describe, expect, it } from "vitest";
import { parseClaimGroundingBegin, parseClaimGroundingProposal } from "./claimGroundingReviewContract";

const SESSION = "1".repeat(64); const RUN = "2".repeat(64); const WINDOW = "3".repeat(64);
const CANDIDATE = "4".repeat(64); const MESSAGE = "5".repeat(64); const MANIFEST = "6".repeat(64);
const RECEIPT = "7".repeat(64); const REVIEW = "8".repeat(64); const CENSUS = "9".repeat(64);
const candidate = (text = "Synthetic bounded claim") => ({ candidate_id: CANDIDATE, message_id: MESSAGE, message_sequence: 0, clause_index: 0, text });
const begin = () => ({ session_id: SESSION, source_run_id: RUN, source_window_fingerprint: WINDOW, manifest: { session_id: SESSION, source_run_id: RUN, source_window_fingerprint: WINDOW, source_schema_version: "synthetic-source-v1", text_adapter_version: "synthetic-adapter-v1", clause_algorithm: "message-clause-coordinates-en-pl-v1", text_extraction_complete: true, candidates: [{ candidate_id: CANDIDATE, message_id: MESSAGE, message_sequence: 0, clause_index: 0 }], candidate_count: 1, manifest_fingerprint: MANIFEST, schema_version: "claim-grounding-census-v1", policy_version: "native-reviewed-agent-claim-census-v1", local_only: true, content_persisted: false }, candidates: [candidate()], review_receipt_id: RECEIPT, review_fingerprint: REVIEW, review_expires_at: new Date(Date.now() + 60_000).toISOString(), local_only: true, content_persisted: false });
const request = { expected_source_run_id: RUN, expected_source_window_fingerprint: WINDOW };
const proposal = (classification: "material_claim" | "excluded" = "material_claim") => ({ reviewed_census: { session_id: SESSION, source_run_id: RUN, source_window_fingerprint: WINDOW, manifest_fingerprint: MANIFEST, classifications: [{ candidate_id: CANDIDATE, classification, exclusion_reason: classification === "excluded" ? "duplicate_or_superseded_claim" : null }], complete_candidate_classification_acknowledged: true, census_fingerprint: CENSUS, issuer_version: "reviewed-agent-response-census-v1", schema_version: "claim-grounding-census-v1", policy_version: "native-reviewed-agent-claim-census-v1", local_only: true, content_persisted: false }, proposal_only: true, measured: false, metric_authority_established: false, content_persisted: false });
describe("claim grounding review contract", () => {
  it("accepts a complete backend-shaped begin and proposal", () => {
    const started = parseClaimGroundingBegin(begin(), { sessionId: SESSION, request });
    expect(started.source_window_fingerprint).toBe(WINDOW);
    expect(parseClaimGroundingProposal(proposal(), { sessionId: SESSION, request: { review_receipt_id: RECEIPT, review_fingerprint: REVIEW, manifest_fingerprint: MANIFEST, classifications: [{ candidate_id: CANDIDATE, classification: "material_claim", exclusion_reason: null }] }, sourceRunId: RUN, sourceWindowFingerprint: WINDOW }).proposal_only).toBe(true);
  });
  it.each([
    ["cross-owner begin", () => ({ ...begin(), source_run_id: "a".repeat(64) })],
    ["duplicate candidate", () => ({ ...begin(), candidates: [candidate(), candidate()], manifest: { ...begin().manifest, candidates: [begin().manifest.candidates[0], begin().manifest.candidates[0]], candidate_count: 2 } })],
    ["unknown version", () => ({ ...begin(), manifest: { ...begin().manifest, schema_version: "unknown" } })],
  ])("rejects %s", (_name, make) => expect(() => parseClaimGroundingBegin(make(), { sessionId: SESSION, request })).toThrow());
  it("rejects changed or duplicate classifications", () => {
    const expected = { review_receipt_id: RECEIPT, review_fingerprint: REVIEW, manifest_fingerprint: MANIFEST, classifications: [{ candidate_id: CANDIDATE, classification: "material_claim" as const, exclusion_reason: null }] };
    expect(() => parseClaimGroundingProposal(proposal("excluded"), { sessionId: SESSION, request: expected, sourceRunId: RUN, sourceWindowFingerprint: WINDOW })).toThrow();
    expect(() => parseClaimGroundingProposal({ ...proposal(), reviewed_census: { ...proposal().reviewed_census, classifications: [{ ...proposal().reviewed_census.classifications[0] }, { ...proposal().reviewed_census.classifications[0] }] } }, { sessionId: SESSION, request: expected, sourceRunId: RUN, sourceWindowFingerprint: WINDOW })).toThrow();
  });
  it("accepts backend-sorted classifications independent of submitted order", () => {
    const second = { candidate_id: "a".repeat(64), message_id: "b".repeat(64), message_sequence: 1, clause_index: 0, text: "Second synthetic claim" };
    const started = begin(); started.candidates.push(second); started.manifest.candidates.push({ candidate_id: second.candidate_id, message_id: second.message_id, message_sequence: 1, clause_index: 0 }); started.manifest.candidate_count = 2;
    parseClaimGroundingBegin(started, { sessionId: SESSION, request });
    const classifications = [{ candidate_id: CANDIDATE, classification: "material_claim" as const, exclusion_reason: null }, { candidate_id: second.candidate_id, classification: "excluded" as const, exclusion_reason: "duplicate_or_superseded_claim" as const }];
    const census = { ...proposal().reviewed_census, classifications: [...classifications].reverse() };
    expect(parseClaimGroundingProposal({ ...proposal(), reviewed_census: census }, { sessionId: SESSION, request: { review_receipt_id: RECEIPT, review_fingerprint: REVIEW, manifest_fingerprint: MANIFEST, classifications }, sourceRunId: RUN, sourceWindowFingerprint: WINDOW })).toBeDefined();
  });
});
