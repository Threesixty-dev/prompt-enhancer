import type {
  ClaimGroundingBegin,
  ClaimGroundingConsumeRequest,
  ClaimGroundingProposal,
  ClaimGroundingBeginRequest,
  ReviewedClaimCensus,
} from "./contracts";

export class ClaimGroundingReviewPayloadError extends Error {
  constructor() { super("Claim-grounding review response was invalid"); }
}

const HEX = /^[a-f0-9]{64}$/;
const row = (value: unknown): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new ClaimGroundingReviewPayloadError();
  return value as Record<string, unknown>;
};
const exact = (value: Record<string, unknown>, keys: readonly string[]) => {
  if (Object.keys(value).sort().join("|") !== [...keys].sort().join("|")) throw new ClaimGroundingReviewPayloadError();
};
const id = (value: unknown): value is string => typeof value === "string" && HEX.test(value);
const utc = (value: unknown): value is string => typeof value === "string" && Number.isFinite(Date.parse(value));
type Candidate = { candidate_id: string; message_id: string; message_sequence: number; clause_index: number; text: string };
type ManifestCandidate = Omit<Candidate, "text">;

export function parseClaimGroundingBegin(value: unknown, expected: { sessionId: string; request: ClaimGroundingBeginRequest }): ClaimGroundingBegin {
  const item = row(value);
  exact(item, ["session_id", "source_run_id", "source_window_fingerprint", "manifest", "candidates", "review_receipt_id", "review_fingerprint", "review_expires_at", "local_only", "content_persisted"]);
  if (item.session_id !== expected.sessionId || item.source_run_id !== expected.request.expected_source_run_id || item.source_window_fingerprint !== expected.request.expected_source_window_fingerprint || !id(item.source_run_id) || !id(item.source_window_fingerprint) || !id(item.review_receipt_id) || !id(item.review_fingerprint) || !utc(item.review_expires_at) || Date.parse(String(item.review_expires_at)) <= Date.now() || item.local_only !== true || item.content_persisted !== false || !Array.isArray(item.candidates)) throw new ClaimGroundingReviewPayloadError();
  const manifest = row(item.manifest);
  if (manifest.session_id !== expected.sessionId || manifest.source_run_id !== item.source_run_id || manifest.source_window_fingerprint !== item.source_window_fingerprint || manifest.schema_version !== "claim-grounding-census-v1" || manifest.policy_version !== "native-reviewed-agent-claim-census-v1" || manifest.clause_algorithm !== "message-clause-coordinates-en-pl-v1" || typeof manifest.source_schema_version !== "string" || !/^[A-Za-z0-9._-]+$/.test(manifest.source_schema_version) || typeof manifest.text_adapter_version !== "string" || !/^[A-Za-z0-9._-]+$/.test(manifest.text_adapter_version) || manifest.local_only !== true || manifest.content_persisted !== false || !id(manifest.manifest_fingerprint) || manifest.text_extraction_complete !== true || !Array.isArray(manifest.candidates) || manifest.candidate_count !== manifest.candidates.length || manifest.candidate_count !== item.candidates.length || manifest.candidate_count > 12_800) throw new ClaimGroundingReviewPayloadError();
  const candidates: Candidate[] = item.candidates.map((raw): Candidate => {
    const candidate = row(raw); exact(candidate, ["candidate_id", "message_id", "message_sequence", "clause_index", "text"]);
    if (!id(candidate.candidate_id) || !id(candidate.message_id) || typeof candidate.message_sequence !== "number" || !Number.isInteger(candidate.message_sequence) || candidate.message_sequence < 0 || typeof candidate.clause_index !== "number" || !Number.isInteger(candidate.clause_index) || candidate.clause_index < 0 || candidate.clause_index >= 128 || typeof candidate.text !== "string" || candidate.text.length < 1 || candidate.text !== candidate.text.trim() || candidate.text.includes("\0")) throw new ClaimGroundingReviewPayloadError();
    return { candidate_id: candidate.candidate_id as string, message_id: candidate.message_id as string, message_sequence: candidate.message_sequence as number, clause_index: candidate.clause_index as number, text: candidate.text as string };
  });
  const manifestCandidates: ManifestCandidate[] = manifest.candidates.map((raw): ManifestCandidate => {
    const candidate = row(raw); exact(candidate, ["candidate_id", "message_id", "message_sequence", "clause_index"]);
    if (!id(candidate.candidate_id) || !id(candidate.message_id) || typeof candidate.message_sequence !== "number" || !Number.isInteger(candidate.message_sequence) || candidate.message_sequence < 0 || typeof candidate.clause_index !== "number" || !Number.isInteger(candidate.clause_index) || candidate.clause_index < 0 || candidate.clause_index >= 128) throw new ClaimGroundingReviewPayloadError();
    return { candidate_id: candidate.candidate_id, message_id: candidate.message_id, message_sequence: candidate.message_sequence, clause_index: candidate.clause_index };
  });
  if (candidates.some((candidate, index) => candidate.candidate_id !== manifestCandidates[index]?.candidate_id || candidate.message_id !== manifestCandidates[index]?.message_id || candidate.message_sequence !== manifestCandidates[index]?.message_sequence || candidate.clause_index !== manifestCandidates[index]?.clause_index)) throw new ClaimGroundingReviewPayloadError();
  if (new Set(candidates.map((candidate) => candidate.candidate_id)).size !== candidates.length || new Set(candidates.map((candidate) => `${candidate.message_id}:${candidate.clause_index}`)).size !== candidates.length) throw new ClaimGroundingReviewPayloadError();
  const messageSequences = new Map<string, number>(); const sequenceMessages = new Map<number, string>(); const byMessage = new Map<string, number[]>();
  candidates.forEach((candidate) => { if (messageSequences.has(candidate.message_id) && messageSequences.get(candidate.message_id) !== candidate.message_sequence) throw new ClaimGroundingReviewPayloadError(); if (sequenceMessages.has(candidate.message_sequence) && sequenceMessages.get(candidate.message_sequence) !== candidate.message_id) throw new ClaimGroundingReviewPayloadError(); messageSequences.set(candidate.message_id, candidate.message_sequence); sequenceMessages.set(candidate.message_sequence, candidate.message_id); byMessage.set(candidate.message_id, [...(byMessage.get(candidate.message_id) ?? []), candidate.clause_index]); });
  if (candidates.some((candidate, index) => index > 0 && (candidate.message_sequence < candidates[index - 1].message_sequence || (candidate.message_sequence === candidates[index - 1].message_sequence && candidate.clause_index < candidates[index - 1].clause_index))) || [...byMessage.values()].some((indexes) => indexes.some((value, index) => value !== index))) throw new ClaimGroundingReviewPayloadError();
  return item as unknown as ClaimGroundingBegin;
}

export function parseClaimGroundingProposal(value: unknown, expected: { sessionId: string; request: ClaimGroundingConsumeRequest; sourceRunId: string; sourceWindowFingerprint: string }): ClaimGroundingProposal {
  const item = row(value); exact(item, ["reviewed_census", "proposal_only", "measured", "metric_authority_established", "content_persisted"]);
  if (item.proposal_only !== true || item.measured !== false || item.metric_authority_established !== false || item.content_persisted !== false) throw new ClaimGroundingReviewPayloadError();
  const census = row(item.reviewed_census);
  exact(census, ["session_id", "source_run_id", "source_window_fingerprint", "manifest_fingerprint", "classifications", "census_fingerprint", "issuer_version", "schema_version", "policy_version", "complete_candidate_classification_acknowledged", "local_only", "content_persisted"]);
  if (census.session_id !== expected.sessionId || census.source_run_id !== expected.sourceRunId || census.source_window_fingerprint !== expected.sourceWindowFingerprint || census.manifest_fingerprint !== expected.request.manifest_fingerprint || census.schema_version !== "claim-grounding-census-v1" || census.policy_version !== "native-reviewed-agent-claim-census-v1" || census.issuer_version !== "reviewed-agent-response-census-v1" || !id(census.census_fingerprint) || census.complete_candidate_classification_acknowledged !== true || census.local_only !== true || census.content_persisted !== false || !Array.isArray(census.classifications) || census.classifications.length !== expected.request.classifications.length) throw new ClaimGroundingReviewPayloadError();
  census.classifications.forEach((raw, index) => {
    const classification = row(raw); exact(classification, ["candidate_id", "classification", "exclusion_reason"]);
    if (!id(classification.candidate_id) || !["material_claim", "excluded"].includes(String(classification.classification)) || (classification.classification === "excluded" ? !["not_a_completion_or_verification_claim", "duplicate_or_superseded_claim", "non_assertive_status_or_qualification"].includes(String(classification.exclusion_reason)) : classification.exclusion_reason !== null)) throw new ClaimGroundingReviewPayloadError();
  });
  const expectedClassifications = new Map(expected.request.classifications.map((classification) => [classification.candidate_id, `${classification.classification}:${classification.exclusion_reason ?? "-"}`]));
  const actualClassifications = new Map(census.classifications.map((classification) => [String(classification.candidate_id), `${classification.classification}:${classification.exclusion_reason ?? "-"}`]));
  if (expectedClassifications.size !== expected.request.classifications.length || actualClassifications.size !== census.classifications.length || expectedClassifications.size !== actualClassifications.size || [...expectedClassifications].some(([candidateId, value]) => actualClassifications.get(candidateId) !== value)) throw new ClaimGroundingReviewPayloadError();
  return item as unknown as ClaimGroundingProposal;
}

export type { ClaimGroundingBegin, ClaimGroundingProposal, ReviewedClaimCensus };
