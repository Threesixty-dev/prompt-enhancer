import { describe, expect, it, vi } from "vitest";
import { createHttpTransport, TransportError } from "./httpTransport";
import { parseClaimGroundingCensus, parseClaimGroundingCensusList } from "./claimGroundingCensusContract";

const S = "1".repeat(64); const R = "2".repeat(64); const W = "3".repeat(64); const M = "4".repeat(64); const C = "5".repeat(64);
const HIGH_WATER = "2026-01-02T03:04:05.000Z";
const auth = { csrf_token: "synthetic-csrf", expires_in_seconds: 300, user_presence_confirmation_available: true, user_presence_confirmation_mode: "native_bridge_bound_token" };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store, private", Pragma: "no-cache" } });
const dto = (overrides: Record<string, unknown> = {}) => ({ census_id: C, session_id: S, source_run_id: R, source_window_fingerprint: W, manifest_fingerprint: M, census_fingerprint: "6".repeat(64), candidate_count: 2, metadata_persisted: true, candidate_prose_persisted: false, proposal_only: true, measured: false, metric_authority_established: false, ...overrides });
const list = (overrides: Record<string, unknown> = {}) => ({ items: [dto()], snapshot_id: "7".repeat(64), total: 1, offset: 0, high_water_created_at: HIGH_WATER, high_water_census_id: C, ...overrides });

describe("claim grounding census HTTP transport", () => {
  it("persists with native confirmation and an idempotency header", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(dto({ candidate_count: 0 })));
    const approval = vi.fn().mockResolvedValue("A".repeat(32));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173", userPresenceApproval: approval, userPresenceBridgeAvailable: () => true });
    await expect(api.persistClaimGroundingCensus!(S, { review_receipt_id: "8".repeat(64), review_fingerprint: "9".repeat(64), manifest_fingerprint: M, classifications: [] }, "synthetic-key-123456", R, W)).resolves.toMatchObject({ census_id: C });
    expect(approval).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[1][1].headers).toMatchObject({ "Idempotency-Key": "synthetic-key-123456" });
  });

  it("rejects malformed flags and ownership without accepting prose", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(dto({ measured: true })));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    await expect(api.getClaimGroundingCensus!(S, C)).rejects.toMatchObject({ status: 200 });
    const fetch2 = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(dto({ session_id: "a".repeat(64) })));
    const api2 = createHttpTransport({ fetch: fetch2 as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    await expect(api2.getClaimGroundingCensus!(S, C)).rejects.toBeInstanceOf(TransportError);
  });

  it("declines native confirmation before persist dispatch", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173", userPresenceApproval: vi.fn().mockRejectedValue(new TransportError("declined", 403, "native_confirmation_declined_before_dispatch")), userPresenceBridgeAvailable: () => true });
    await expect(api.persistClaimGroundingCensus!(S, { review_receipt_id: "8".repeat(64), review_fingerprint: "9".repeat(64), manifest_fingerprint: M, classifications: [] }, "synthetic-key-123456", R, W)).rejects.toMatchObject({ reasonCode: "native_confirmation_declined_before_dispatch" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("does not retry a persist network failure", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockRejectedValueOnce(new TypeError("synthetic network failure"));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173", userPresenceApproval: vi.fn().mockResolvedValue("A".repeat(32)), userPresenceBridgeAvailable: () => true });
    await expect(api.persistClaimGroundingCensus!(S, { review_receipt_id: "8".repeat(64), review_fingerprint: "9".repeat(64), manifest_fingerprint: M, classifications: [] }, "synthetic-key-123456", R, W)).rejects.toThrow("synthetic network failure");
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("recovers without native confirmation and sends the key as a header", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(dto()));
    const approval = vi.fn();
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173", userPresenceApproval: approval, userPresenceBridgeAvailable: () => true });
    await expect(api.recoverClaimGroundingCensus!(S, "synthetic-key-123456")).resolves.toMatchObject({ census_id: C });
    expect(approval).not.toHaveBeenCalled();
    expect(fetch.mock.calls[1][1].headers).toMatchObject({ "Idempotency-Key": "synthetic-key-123456" });
    expect(String(fetch.mock.calls[1][0])).not.toContain("synthetic-key-123456");
  });

  it("validates list snapshot high-water metadata and duplicate ownership", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(list({ items: [dto(), dto()] })));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    await expect(api.listClaimGroundingCensuses!(S, { limit: 50, offset: 0 })).rejects.toMatchObject({ status: 200 });
    const emptyFetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(list({ items: [], total: 0, high_water_created_at: null, high_water_census_id: null })));
    const emptyApi = createHttpTransport({ fetch: emptyFetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    await expect(emptyApi.listClaimGroundingCensuses!(S)).resolves.toMatchObject({ total: 0 });
    expect(parseClaimGroundingCensus(dto(), { sessionId: S, sourceRunId: R, sourceWindowFingerprint: W, manifestFingerprint: M, candidateCount: 2 })).toBeTruthy();
    expect(() => parseClaimGroundingCensus({ ...dto(), prose: "forbidden" }, { sessionId: S })).toThrow();
    expect(() => parseClaimGroundingCensusList({ ...list({ items: [dto()], total: 0 }) }, S, 1, 0)).toThrow();
    expect(() => parseClaimGroundingCensusList({ ...list({ items: [dto()], offset: 2, total: 1 }) }, S, 1, 2)).toThrow();
    const snapshot = { snapshot_id: "7".repeat(64), total: 1, high_water_created_at: list().high_water_created_at, high_water_census_id: C };
    expect(() => parseClaimGroundingCensusList(list(), S, 1, 0, { ...snapshot, snapshot_id: "8".repeat(64) })).toThrow();
  });

  it("serializes a second page with the complete snapshot and omits empty high-water nulls", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(json(auth))
      .mockResolvedValueOnce(json(list({ total: 3, offset: 2 })))
      .mockResolvedValueOnce(json(list({ items: [], snapshot_id: "9".repeat(64), total: 0, high_water_created_at: null, high_water_census_id: null })));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    const pageSnapshot = { snapshot_id: "7".repeat(64), total: 3, high_water_created_at: list().high_water_created_at, high_water_census_id: C };
    await expect(api.listClaimGroundingCensuses!(S, { limit: 2, offset: 2, snapshot: pageSnapshot })).resolves.toMatchObject({ total: 3, offset: 2 });
    const url = String(fetch.mock.calls[1][0]);
    expect(url).toContain("snapshot_id=" + "7".repeat(64));
    expect(url).toContain("snapshot_total=3");
    expect(url).toContain("high_water_created_at=" + encodeURIComponent(pageSnapshot.high_water_created_at));
    expect(url).toContain("high_water_census_id=" + C);

    await expect(api.listClaimGroundingCensuses!(S, { limit: 2, offset: 0, snapshot: { snapshot_id: "9".repeat(64), total: 0, high_water_created_at: null, high_water_census_id: null } })).resolves.toMatchObject({ total: 0 });
    const emptyUrl = String(fetch.mock.calls[2][0]);
    expect(emptyUrl).toContain("snapshot_total=0");
    expect(emptyUrl).not.toContain("high_water_created_at");
    expect(emptyUrl).not.toContain("high_water_census_id");
  });
});
