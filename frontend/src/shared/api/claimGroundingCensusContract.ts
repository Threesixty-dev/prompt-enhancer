import type {
  ClaimGroundingCensus,
  ClaimGroundingCensusList,
  ClaimGroundingConsumeRequest,
} from "./contracts";

export class ClaimGroundingCensusPayloadError extends Error {
  constructor() { super("Claim-grounding census response was invalid"); }
}

const HEX = /^[a-f0-9]{64}$/u;
const row = (value: unknown): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new ClaimGroundingCensusPayloadError();
  return value as Record<string, unknown>;
};
const exact = (value: Record<string, unknown>, keys: readonly string[]) => {
  if (Object.keys(value).sort().join("|") !== [...keys].sort().join("|")) throw new ClaimGroundingCensusPayloadError();
};
const id = (value: unknown): value is string => typeof value === "string" && HEX.test(value);
const nonNegativeInt = (value: unknown, max = Number.MAX_SAFE_INTEGER): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= max;
const timestamp = (value: unknown): value is string => typeof value === "string" && Number.isFinite(Date.parse(value));

const DTO_KEYS = ["census_id", "session_id", "source_run_id", "source_window_fingerprint", "manifest_fingerprint", "census_fingerprint", "candidate_count", "metadata_persisted", "candidate_prose_persisted", "proposal_only", "measured", "metric_authority_established"] as const;

function parseItem(value: unknown, expectedSessionId: string): ClaimGroundingCensus {
  const item = row(value); exact(item, DTO_KEYS);
  if (item.session_id !== expectedSessionId || !id(item.census_id) || !id(item.session_id) || !id(item.source_run_id) || !id(item.source_window_fingerprint) || !id(item.manifest_fingerprint) || !id(item.census_fingerprint) || !nonNegativeInt(item.candidate_count, 12_800) || item.metadata_persisted !== true || item.candidate_prose_persisted !== false || item.proposal_only !== true || item.measured !== false || item.metric_authority_established !== false) throw new ClaimGroundingCensusPayloadError();
  return item as unknown as ClaimGroundingCensus;
}

export function parseClaimGroundingCensus(value: unknown, expected: { sessionId: string; censusId?: string; sourceRunId?: string; sourceWindowFingerprint?: string; manifestFingerprint?: string; candidateCount?: number }): ClaimGroundingCensus {
  const item = parseItem(value, expected.sessionId);
  if ((expected.censusId !== undefined && item.census_id !== expected.censusId) || (expected.sourceRunId !== undefined && item.source_run_id !== expected.sourceRunId) || (expected.sourceWindowFingerprint !== undefined && item.source_window_fingerprint !== expected.sourceWindowFingerprint) || (expected.manifestFingerprint !== undefined && item.manifest_fingerprint !== expected.manifestFingerprint) || (expected.candidateCount !== undefined && item.candidate_count !== expected.candidateCount)) throw new ClaimGroundingCensusPayloadError();
  return item;
}

export function parseClaimGroundingCensusList(value: unknown, expectedSessionId: string, expectedLimit: number, expectedOffset: number, expectedSnapshot?: { snapshot_id: string; total: number; high_water_created_at: string | null; high_water_census_id: string | null }): ClaimGroundingCensusList {
  const item = row(value); exact(item, ["items", "snapshot_id", "total", "offset", "high_water_created_at", "high_water_census_id"]);
  if (!Array.isArray(item.items) || !id(item.snapshot_id) || !nonNegativeInt(item.total) || !nonNegativeInt(item.offset, 1_000_000) || item.offset !== expectedOffset || item.items.length > expectedLimit || (item.high_water_created_at !== null && !timestamp(item.high_water_created_at)) || (item.high_water_census_id !== null && !id(item.high_water_census_id))) throw new ClaimGroundingCensusPayloadError();
  const items = item.items.map((entry) => parseItem(entry, expectedSessionId));
  if (items.length > 200 || new Set(items.map((entry) => entry.census_id)).size !== items.length || (item.total === 0 ? item.high_water_created_at !== null || item.high_water_census_id !== null : item.high_water_created_at === null || item.high_water_census_id === null) || (item.offset > item.total && items.length !== 0)) throw new ClaimGroundingCensusPayloadError();
  if ((item.offset <= item.total && items.length > item.total - item.offset) || (items.length > 0 && items.some((entry) => entry.session_id !== expectedSessionId)) || (expectedSnapshot !== undefined && (item.snapshot_id !== expectedSnapshot.snapshot_id || item.total !== expectedSnapshot.total || item.high_water_created_at !== expectedSnapshot.high_water_created_at || item.high_water_census_id !== expectedSnapshot.high_water_census_id))) throw new ClaimGroundingCensusPayloadError();
  return item as unknown as ClaimGroundingCensusList;
}

export type { ClaimGroundingCensus, ClaimGroundingCensusList, ClaimGroundingConsumeRequest };
