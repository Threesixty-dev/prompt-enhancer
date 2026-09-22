import { describe, expect, it, vi } from "vitest";
import { createHttpTransport, TransportError } from "./httpTransport";

const S = "1".repeat(64);
const CENSUS = "2".repeat(64);
const RUN = "3".repeat(64);
const WINDOW = "4".repeat(64);
const CENSUS_FINGERPRINT = "5".repeat(64);
const MANIFEST = "6".repeat(64);
const CANDIDATE = "7".repeat(64);
const MESSAGE = "8".repeat(64);
const CHECK = "9".repeat(64);
const expected = {
  sourceRunId: RUN,
  sourceWindowFingerprint: WINDOW,
  censusFingerprint: CENSUS_FINGERPRINT,
  manifestFingerprint: MANIFEST,
};
const auth = {
  csrf_token: "synthetic-csrf",
  expires_in_seconds: 300,
  user_presence_confirmation_available: false,
  user_presence_confirmation_mode: "unavailable",
};
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status,
  headers: { "Content-Type": "application/json", "Cache-Control": "no-store, private", Pragma: "no-cache" },
});
const manifest = (overrides: Record<string, unknown> = {}) => ({
  session_id: S, census_id: CENSUS, source_run_id: RUN,
  source_window_fingerprint: WINDOW, census_fingerprint: CENSUS_FINGERPRINT,
  manifest_fingerprint: MANIFEST, observed_set_fingerprint: "a".repeat(64),
  source_schema_version: "synthetic-v1", text_adapter_version: "synthetic-v1",
  observed_set_schema_version: "claim-grounding-observed-set-v1",
  observed_set_policy_version: "native-reviewed-claim-link-coverage-v1",
  material_candidates: [{ candidate_id: CANDIDATE, message_id: MESSAGE, message_sequence: 1, clause_index: 0 }],
  observed_checks: [{
    source_reference_id: CHECK, observed_sequence: 1, provider: "codex", check_kind: "test",
    outcome: "passed", provider_execution_status: "completed", exit_code: 0,
    source_completion_schema_version: "observed-check-completion-v1",
    outcome_interpreter_version: "pytest-exit-status-v1", classifier_version: "local-command-rules-v1",
    normalizer_version: "strict-shell-free-v2", rule_id: "test.pytest",
  }],
  proposal_only: true, measured: false, metric_authority_established: false, content_persisted: false,
  ...overrides,
});

describe("claim grounding link-candidates HTTP transport", () => {
  it("gets the exact read-only binding once without native confirmation", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(manifest()));
    const approval = vi.fn();
    const api = createHttpTransport({
      fetch: fetch as unknown as typeof globalThis.fetch,
      origin: "http://127.0.0.1:4173",
      userPresenceApproval: approval,
      userPresenceBridgeAvailable: () => false,
    });

    await expect(api.getClaimGroundingLinkCandidates!(S, CENSUS, expected)).resolves.toMatchObject({
      census_id: CENSUS, manifest_fingerprint: MANIFEST,
    });
    expect(approval).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(String(fetch.mock.calls[1][0])).toContain(
      `/v1/sessions/${S}/claim-grounding-review/links/candidates/${CENSUS}`,
    );
    expect(fetch.mock.calls[1][1]).toMatchObject({ method: "GET" });
  });

  it("rejects invalid expected binding before any fetch", async () => {
    const fetch = vi.fn();
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    await expect(api.getClaimGroundingLinkCandidates!(S, CENSUS, { ...expected, manifestFingerprint: "bad" })).rejects.toMatchObject({
      status: 422,
      message: "Claim-grounding link candidates request was invalid",
    });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("does not coerce malformed runtime identities before dispatch", async () => {
    const fetch = vi.fn();
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    const deceptive = { toString: () => MANIFEST };
    await expect(api.getClaimGroundingLinkCandidates!(S, CENSUS, {
      ...expected, manifestFingerprint: deceptive as unknown as string,
    })).rejects.toMatchObject({ status: 422 });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("preserves aborts without dispatch", async () => {
    const fetch = vi.fn();
    const controller = new AbortController(); controller.abort();
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    await expect(api.getClaimGroundingLinkCandidates!(S, CENSUS, expected, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects stale or malformed responses safely without retries", async () => {
    const staleFetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(manifest({ census_fingerprint: "b".repeat(64) })));
    const staleApi = createHttpTransport({ fetch: staleFetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    await expect(staleApi.getClaimGroundingLinkCandidates!(S, CENSUS, expected)).rejects.toMatchObject({
      name: "TransportError", status: 200, message: "Claim-grounding link candidates response was invalid",
    });
    expect(staleFetch).toHaveBeenCalledTimes(2);

    const badFetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(manifest({ unexpected: "synthetic private preview" })));
    const badApi = createHttpTransport({ fetch: badFetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    await expect(badApi.getClaimGroundingLinkCandidates!(S, CENSUS, expected)).rejects.toMatchObject({
      name: "TransportError", status: 200, reasonCode: null,
      message: "Claim-grounding link candidates response was invalid",
    });
    expect(badFetch).toHaveBeenCalledTimes(2);
  });
});
