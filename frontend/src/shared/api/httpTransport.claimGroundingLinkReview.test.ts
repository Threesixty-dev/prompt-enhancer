import { describe, expect, it, vi } from "vitest";
import { createHttpTransport, TransportError } from "./httpTransport";

const S = "1".repeat(64);
const CENSUS = "2".repeat(64);
const CANDIDATE = "3".repeat(64);
const RUN = "4".repeat(64);
const WINDOW = "5".repeat(64);
const CENSUS_FINGERPRINT = "6".repeat(64);
const MANIFEST = "7".repeat(64);
const OBSERVED = "8".repeat(64);
const CHECK = "9".repeat(64);
const RECEIPT = "a".repeat(64);
const REVIEW = "b".repeat(64);
const auth = {
  csrf_token: "synthetic-csrf",
  expires_in_seconds: 300,
  user_presence_confirmation_available: true,
  user_presence_confirmation_mode: "native_bridge_bound_token",
};
const request = {
  census_id: CENSUS,
  candidate_id: CANDIDATE,
  selected_check_references: [CHECK],
};
const expected = {
  source_run_id: RUN,
  source_window_fingerprint: WINDOW,
  census_fingerprint: CENSUS_FINGERPRINT,
  manifest_fingerprint: MANIFEST,
};
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status,
  headers: {
    "Content-Type": "application/json",
    "Cache-Control": "no-store, private",
    Pragma: "no-cache",
  },
});
const review = (overrides: Record<string, unknown> = {}) => ({
  session_id: S,
  census_id: CENSUS,
  candidate_id: CANDIDATE,
  source_run_id: RUN,
  source_window_fingerprint: WINDOW,
  census_fingerprint: CENSUS_FINGERPRINT,
  manifest_fingerprint: MANIFEST,
  observed_set_fingerprint: OBSERVED,
  review_receipt_id: RECEIPT,
  review_fingerprint: REVIEW,
  review_expires_at: new Date(Date.now() + 60_000).toISOString(),
  claim_clause: "synthetic private preview",
  observed_checks: [{
    source_reference_id: CHECK,
    observed_sequence: 1,
    outcome: "passed",
    tool_name: "pytest",
    invocation_preview: "pytest -q",
    effect_preview: "exit 0",
  }],
  proposal_only: true,
  measured: false,
  metric_authority_established: false,
  content_persisted: false,
  ...overrides,
});

describe("claim grounding link-review HTTP transport", () => {
  it("declines native confirmation before the link endpoint dispatches", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth));
    const api = createHttpTransport({
      fetch: fetch as unknown as typeof globalThis.fetch,
      origin: "http://127.0.0.1:4173",
      userPresenceApproval: vi.fn().mockRejectedValue(
        new TransportError("declined", 403, "native_confirmation_declined_before_dispatch"),
      ),
      userPresenceBridgeAvailable: () => true,
    });

    await expect(api.beginClaimGroundingLinkReview!(S, request, expected)).rejects.toMatchObject({
      reasonCode: "native_confirmation_declined_before_dispatch",
    });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(String(fetch.mock.calls[0][0])).not.toContain("/links/begin");
  });

  it("posts the exact immutable binding once after native approval", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(review()));
    const approval = vi.fn().mockResolvedValue("A".repeat(32));
    const api = createHttpTransport({
      fetch: fetch as unknown as typeof globalThis.fetch,
      origin: "http://127.0.0.1:4173",
      userPresenceApproval: approval,
      userPresenceBridgeAvailable: () => true,
    });

    await expect(api.beginClaimGroundingLinkReview!(S, request, expected)).resolves.toMatchObject({
      review_receipt_id: RECEIPT,
      census_fingerprint: CENSUS_FINGERPRINT,
      manifest_fingerprint: MANIFEST,
    });
    expect(approval).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(String(fetch.mock.calls[1][0])).toContain(`/v1/sessions/${S}/claim-grounding-review/links/begin`);
    expect(fetch.mock.calls[1][1]).toMatchObject({
      method: "POST",
      body: JSON.stringify(request),
      headers: expect.objectContaining({
        "X-Prompt-Enhancer-CSRF": "synthetic-csrf",
        "X-Prompt-Enhancer-User-Presence": "A".repeat(32),
      }),
    });
  });

  it("preserves aborts without a dispatch", async () => {
    const fetch = vi.fn();
    const controller = new AbortController();
    controller.abort();
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });

    await expect(api.beginClaimGroundingLinkReview!(S, request, expected, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects malformed previews with a fixed error and never retries", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(review({ unexpected: "synthetic private preview" })));
    const api = createHttpTransport({
      fetch: fetch as unknown as typeof globalThis.fetch,
      origin: "http://127.0.0.1:4173",
      userPresenceApproval: vi.fn().mockResolvedValue("A".repeat(32)),
      userPresenceBridgeAvailable: () => true,
    });

    await expect(api.beginClaimGroundingLinkReview!(S, request, expected)).rejects.toMatchObject({
      name: "TransportError",
      status: 200,
      reasonCode: null,
      message: "Claim-grounding link review response was invalid",
    });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("keeps the fixed link conflict reason code", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json({ detail: { code: "claim_grounding_link_review_conflict" } }, 409));
    const api = createHttpTransport({
      fetch: fetch as unknown as typeof globalThis.fetch,
      origin: "http://127.0.0.1:4173",
      userPresenceApproval: vi.fn().mockResolvedValue("A".repeat(32)),
      userPresenceBridgeAvailable: () => true,
    });

    await expect(api.beginClaimGroundingLinkReview!(S, request, expected)).rejects.toMatchObject({
      status: 409,
      reasonCode: "claim_grounding_link_review_conflict",
    });
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
