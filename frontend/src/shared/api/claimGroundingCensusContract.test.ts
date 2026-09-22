import { describe, expect, it } from "vitest";
import {
  parseClaimGroundingCensus,
  parseClaimGroundingCensusList,
} from "./claimGroundingCensusContract";

const S = "1".repeat(64);
const R = "2".repeat(64);
const W = "3".repeat(64);
const M = "4".repeat(64);
const C = "5".repeat(64);
const F = "6".repeat(64);
const SNAP = "7".repeat(64);
const HIGH = "8".repeat(64);
const NOW = "2026-01-02T03:04:05.000Z";

const dto = (overrides: Record<string, unknown> = {}) => ({
  census_id: C,
  session_id: S,
  source_run_id: R,
  source_window_fingerprint: W,
  manifest_fingerprint: M,
  census_fingerprint: F,
  candidate_count: 2,
  metadata_persisted: true,
  candidate_prose_persisted: false,
  proposal_only: true,
  measured: false,
  metric_authority_established: false,
  ...overrides,
});

const snapshot = {
  snapshot_id: SNAP,
  total: 2,
  high_water_created_at: NOW,
  high_water_census_id: HIGH,
};

const list = (overrides: Record<string, unknown> = {}) => ({
  items: [dto()],
  snapshot_id: SNAP,
  total: 2,
  offset: 0,
  high_water_created_at: NOW,
  high_water_census_id: HIGH,
  ...overrides,
});

describe("claim grounding census parsers", () => {
  it.each([
    ["metadata_persisted", { metadata_persisted: false }],
    ["candidate_prose_persisted", { candidate_prose_persisted: true }],
    ["proposal_only", { proposal_only: false }],
    ["measured", { measured: true }],
    ["metric_authority_established", { metric_authority_established: true }],
    ["malformed id", { census_id: "not-an-id" }],
    ["candidate count over bound", { candidate_count: 12_801 }],
    ["extra prose", { prose: "synthetic prose" }],
  ])("rejects %s", (_label, override) => {
    expect(() => parseClaimGroundingCensus(dto(override), { sessionId: S })).toThrow();
  });

  it.each([
    ["source run", { sourceRunId: "9".repeat(64) }],
    ["source window", { sourceWindowFingerprint: "a".repeat(64) }],
    ["manifest", { manifestFingerprint: "b".repeat(64) }],
    ["candidate count", { candidateCount: 3 }],
  ])("rejects a mismatched expected %s", (_label, expected) => {
    expect(() => parseClaimGroundingCensus(dto(), { sessionId: S, ...expected })).toThrow();
  });

  it("accepts the maximum candidate count and list totals above that item bound", () => {
    expect(parseClaimGroundingCensus(dto({ candidate_count: 12_800 }), { sessionId: S })).toBeTruthy();
    expect(parseClaimGroundingCensusList(list({ total: 13_000 }), S, 1, 0)).toBeTruthy();
  });

  it("accepts exact positive and empty snapshots", () => {
    expect(parseClaimGroundingCensusList(list(), S, 1, 0, snapshot)).toBeTruthy();
    expect(parseClaimGroundingCensusList(list({ items: [], total: 0, high_water_created_at: null, high_water_census_id: null }), S, 1, 0, {
      snapshot_id: SNAP,
      total: 0,
      high_water_created_at: null,
      high_water_census_id: null,
    })).toBeTruthy();
  });

  it.each([
    ["snapshot_id", { snapshot_id: "9".repeat(64) }],
    ["total", { total: 3 }],
    ["high_water_created_at", { high_water_created_at: "2026-02-02T03:04:05.000Z" }],
    ["high_water_census_id", { high_water_census_id: "a".repeat(64) }],
  ])("rejects each mismatched snapshot %s", (_label, override) => {
    expect(() => parseClaimGroundingCensusList(list(), S, 1, 0, { ...snapshot, ...override })).toThrow();
  });

  it("rejects list limit overflow, duplicate census ids, and invalid offset contents", () => {
    expect(() => parseClaimGroundingCensusList(list({ items: [dto(), dto({ census_id: "9".repeat(64) })] }), S, 1, 0)).toThrow();
    expect(() => parseClaimGroundingCensusList(list({ items: [dto()] }), S, 0, 0)).toThrow();
    expect(parseClaimGroundingCensusList(list({ items: [], total: 1, offset: 2 }), S, 1, 2)).toBeTruthy();
    expect(() => parseClaimGroundingCensusList(list({ total: 1, offset: 2 }), S, 1, 2)).toThrow();
  });
});
