import { describe, expect, it, vi } from "vitest";
import { createHttpTransport } from "./httpTransport";
import { ClaimGroundingReviewPayloadError } from "./claimGroundingReviewContract";

const S = "1".repeat(64); const R = "2".repeat(64); const W = "3".repeat(64);
const auth = { csrf_token: "synthetic-csrf", expires_in_seconds: 300, user_presence_confirmation_available: true, user_presence_confirmation_mode: "native_bridge_bound_token" };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store, private", Pragma: "no-cache" } });
const badBegin = { session_id: S, source_run_id: R, source_window_fingerprint: W, manifest: {}, candidates: [], review_receipt_id: "4".repeat(64), review_fingerprint: "5".repeat(64), review_expires_at: new Date(Date.now() + 60_000).toISOString(), local_only: true, content_persisted: false };
describe("claim grounding HTTP transport", () => {
  it("declines native confirmation before dispatch", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({ ...auth }));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173", userPresenceApproval: vi.fn().mockRejectedValue(new Error("declined")), userPresenceBridgeAvailable: () => true });
    await expect(api.beginClaimGroundingReview!(S, { expected_source_run_id: R, expected_source_window_fingerprint: W })).rejects.toThrow("declined");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("does not retry or reinterpret an invalid 200 consume response", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({ ...auth })).mockResolvedValueOnce(json({ nope: true }));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173", userPresenceApproval: vi.fn().mockResolvedValue("A".repeat(32)), userPresenceBridgeAvailable: () => true });
    const request = { review_receipt_id: "4".repeat(64), review_fingerprint: "5".repeat(64), manifest_fingerprint: "6".repeat(64), classifications: [] };
    await expect(api.consumeClaimGroundingReview!(S, request, R, W)).rejects.toMatchObject({ status: 200 });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(ClaimGroundingReviewPayloadError).toBeDefined();
  });
  it("does not retry a network failure after consume dispatch", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({ ...auth })).mockRejectedValueOnce(new TypeError("synthetic network failure"));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173", userPresenceApproval: vi.fn().mockResolvedValue("A".repeat(32)), userPresenceBridgeAvailable: () => true });
    const request = { review_receipt_id: "4".repeat(64), review_fingerprint: "5".repeat(64), manifest_fingerprint: "6".repeat(64), classifications: [] };
    await expect(api.consumeClaimGroundingReview!(S, request, R, W)).rejects.toThrow("synthetic network failure");
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
