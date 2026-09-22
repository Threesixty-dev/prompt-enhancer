import { describe, expect, it, vi } from "vitest";
import { createHttpTransport } from "./httpTransport";
import type { RequirementVerificationEvidenceSnapshot } from "./contracts";

const SESSION = "1".repeat(64);
const SET = "2".repeat(64);
const PLAN = "3".repeat(64);
const PROPOSAL = "4".repeat(64);
const PLAN_EVIDENCE = "5".repeat(64);
const WINDOW = "6".repeat(64);
const EVIDENCE = "7".repeat(64);
const auth = { csrf_token: "synthetic-csrf-token", expires_in_seconds: 300, user_presence_confirmation_available: false, user_presence_confirmation_mode: "unavailable" };
function snapshot(revision = 0, session = SESSION, set = SET): RequirementVerificationEvidenceSnapshot { return { revision, authority_heads: [], persistence_schema_version: "requirement-verification-persistence-v1", local_only: true, content_persisted: false, evidence: { evidence_set_fingerprint: EVIDENCE, projection_version: "reviewed-requirement-verification-objective-projection-v1", evidence_schema_version: "requirement-verification-evidence-v1", evidence_policy_version: "app-issued-reviewed-requirement-verification-v1", local_only: true, content_persisted: false, verification_results: [], acceptance_authorities: [], opportunities: { session_id: session, requirement_plan_confirmation_id: PLAN, requirement_plan_proposal_id: PROPOSAL, requirement_plan_evidence_fingerprint: PLAN_EVIDENCE, requirement_plan_schema_version: "requirement-plan-evidence-v1", requirement_plan_policy_version: "reviewed-requirement-plan-v1", requirement_plan_review_rubric_version: "active-requirement-plan-review-rubric-v1", source_window_fingerprint: WINDOW, complete_active_requirement_enumeration: true, opportunities: [], opportunity_set_fingerprint: set, issuer_version: "reviewed-r6-requirement-opportunity-issuer-v1", evidence_schema_version: "requirement-verification-evidence-v1", evidence_policy_version: "app-issued-reviewed-requirement-verification-v1", local_only: true, content_persisted: false } } }; }
function json(body: unknown, privateResponse = true, status = 200) { return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...(privateResponse ? { "Cache-Control": "no-store, private", Pragma: "no-cache" } : {}) } }); }
function review() { return { schema_version: "requirement-verification-native-review-v1", policy_version: "current-r8-reviewed-r6-clause-only-v1", session_id: SESSION, opportunity_set_fingerprint: SET, opportunity_id: "a".repeat(64), requirement_id: "b".repeat(64), coordinate: { message_sequence: 1, clause_index: 0 }, expected_source_run_id: "c".repeat(64), source_window_fingerprint: WINDOW, requirement_plan_confirmation_id: PLAN, requirement_plan_proposal_id: PROPOSAL, expected_predecessor_authority_id: null, through_revision: 0, review_receipt_id: "d".repeat(64), review_fingerprint: "e".repeat(64), review_expires_at: new Date(Date.now() + 60_000).toISOString(), requirement_text: "Synthetic clause", local_only: true, content_persisted: false }; }
function acceptanceMutation() { const value = snapshot(1); const opportunity = { opportunity_id: "a".repeat(64), requirement_id: "b".repeat(64), requirement_index: 0, coordinate: { message_sequence: 1, clause_index: 0 } }; value.evidence.opportunities.opportunities = [opportunity]; value.evidence.acceptance_authorities = [{ acceptance_id: "c".repeat(64), acceptance_fingerprint: "d".repeat(64), authority_kind: "native_user_acceptance", confirmation_id: "e".repeat(64), content_persisted: false, evidence_policy_version: "app-issued-reviewed-requirement-verification-v1", evidence_schema_version: "requirement-verification-evidence-v1", issuer_version: "native-explicit-requirement-acceptance-issuer-v1", local_only: true, opportunity_id: opportunity.opportunity_id, opportunity_set_fingerprint: SET, outcome: "accepted", owned_native_action: true, requirement_id: opportunity.requirement_id }]; value.authority_heads = [{ authority_record_id: "c".repeat(64), kind: "native_acceptance", opportunity_id: opportunity.opportunity_id, revision: 1 }]; return { applied: true, snapshot: value }; }
describe("requirement-verification HTTP transport", () => {
  it("uses body-bound native proof and private no-store policy for an explicit exact review", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({ ...auth, user_presence_confirmation_available: true, user_presence_confirmation_mode: "native_bridge_bound_token" })).mockResolvedValueOnce(json(review()));
    const approval = vi.fn().mockResolvedValue("A".repeat(32));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173", userPresenceApproval: approval, userPresenceBridgeAvailable: () => true });
    await api.reviewRequirementVerificationOpportunity!(SESSION, SET, "a".repeat(64), { expected_source_run_id: "c".repeat(64), through_revision: 0, expected_predecessor_authority_id: null, confirmation: "open_exact_local_requirement_verification_review" });
    expect(fetch.mock.calls[1][0]).toBe(`/v1/sessions/${SESSION}/requirement-verification-evidence/opportunity-sets/${SET}/opportunities/${"a".repeat(64)}/review`);
    expect(fetch.mock.calls[1][1]).toEqual(expect.objectContaining({ method: "POST", cache: "no-store", body: JSON.stringify({ expected_source_run_id: "c".repeat(64), through_revision: 0, expected_predecessor_authority_id: null, confirmation: "open_exact_local_requirement_verification_review" }) }));
    expect((fetch.mock.calls[1][1] as RequestInit).headers).toEqual(expect.objectContaining({ "X-Prompt-Enhancer-User-Presence": "A".repeat(32) }));
    expect(approval).toHaveBeenCalledOnce();
  });
  it("does not POST a review when native proof is unavailable and forwards abort", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173", userPresenceBridgeAvailable: () => false });
    await expect(api.reviewRequirementVerificationOpportunity!(SESSION, SET, "a".repeat(64), { expected_source_run_id: "c".repeat(64), through_revision: 0, expected_predecessor_authority_id: null, confirmation: "open_exact_local_requirement_verification_review" })).rejects.toMatchObject({ status: 503 });
    expect(fetch).toHaveBeenCalledTimes(1);
    const controller = new AbortController(); controller.abort();
    await expect(api.reviewRequirementVerificationOpportunity!(SESSION, SET, "a".repeat(64), { expected_source_run_id: "c".repeat(64), through_revision: 0, expected_predecessor_authority_id: null, confirmation: "open_exact_local_requirement_verification_review" }, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
  it("serializes the reviewed-only acceptance body with its stable idempotency key and native proof", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({ ...auth, user_presence_confirmation_available: true, user_presence_confirmation_mode: "native_bridge_bound_token" })).mockResolvedValueOnce(json(acceptanceMutation()));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173", userPresenceApproval: vi.fn().mockResolvedValue("A".repeat(32)), userPresenceBridgeAvailable: () => true });
    const body = { opportunity_set_fingerprint: SET, opportunity_id: "a".repeat(64), expected_predecessor_authority_id: null, outcome: "accepted" as const, confirmation: "record_explicit_native_requirement_acceptance" as const, review_receipt_id: "d".repeat(64), review_fingerprint: "e".repeat(64), expected_source_run_id: "c".repeat(64), source_window_fingerprint: WINDOW };
    await api.appendRequirementVerificationAcceptance!(SESSION, body, "synthetic-acceptance-key");
    expect(fetch.mock.calls[1][0]).toBe(`/v1/sessions/${SESSION}/requirement-verification-evidence/acceptances`);
    expect(fetch.mock.calls[1][1]).toEqual(expect.objectContaining({ method: "POST", cache: "no-store", body: JSON.stringify(body) }));
    expect((fetch.mock.calls[1][1] as RequestInit).headers).toEqual(expect.objectContaining({ "Idempotency-Key": "synthetic-acceptance-key", "X-Prompt-Enhancer-User-Presence": "A".repeat(32) }));
  });
  it("issues only on explicit POST and reads exact requested revisions", async () => { const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json({ snapshot: snapshot(), applied: true })).mockResolvedValueOnce(json(snapshot())); const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" }); await api.issueCurrentRequirementVerificationOpportunities!(SESSION); await api.getRequirementVerificationEvidenceSnapshot!(SESSION, SET, 0); expect(fetch.mock.calls.map((x) => x[0])).toEqual(["/auth/session", `/v1/sessions/${SESSION}/requirement-verification-evidence/opportunity-sets/current`, `/v1/sessions/${SESSION}/requirement-verification-evidence/opportunity-sets/${SET}?through_revision=0`]); expect(fetch.mock.calls[1][1]).toEqual(expect.objectContaining({ method: "POST", cache: "no-store" })); expect((fetch.mock.calls[1][1] as RequestInit).body).toBeUndefined(); expect(fetch.mock.calls[2][1]).toEqual(expect.objectContaining({ method: "GET", cache: "no-store" })); });
  it("omits revision, rejects invalid requests before fetch, and refuses unsafe or drifted responses", async () => { const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(snapshot(), false)); const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" }); await expect(api.getRequirementVerificationEvidenceSnapshot!(SESSION, SET)).rejects.toMatchObject({ status: 200 }); expect(fetch.mock.calls[1][0]).toBe(`/v1/sessions/${SESSION}/requirement-verification-evidence/opportunity-sets/${SET}`); const before = fetch.mock.calls.length; await expect(api.getRequirementVerificationEvidenceSnapshot!("bad", SET)).rejects.toMatchObject({ status: 422 }); await expect(api.getRequirementVerificationEvidenceSnapshot!(SESSION, SET, -1)).rejects.toMatchObject({ status: 422 }); expect(fetch).toHaveBeenCalledTimes(before); });
  it("does not expose error bodies and forwards abort signals", async () => { const controller = new AbortController(); const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json({ secret: "synthetic-secret-canary" }, true, 409)); const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" }); const error = await api.issueCurrentRequirementVerificationOpportunities!(SESSION, controller.signal).catch((value) => value); expect(error).toMatchObject({ status: 409 }); expect(String(error)).not.toContain("synthetic-secret-canary"); expect((fetch.mock.calls[1][1] as RequestInit).signal).toBe(controller.signal); });
  it.each([
    ["session", snapshot(0, "8".repeat(64))],
    ["set", snapshot(0, SESSION, "9".repeat(64))],
    ["revision", snapshot(1)],
  ])("rejects a drifted returned %s", async (_kind, body) => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(body));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    await expect(api.getRequirementVerificationEvidenceSnapshot!(SESSION, SET, 0)).rejects.toMatchObject({ status: 200 });
  });
  it("rejects malformed and unsafe snapshot parameters before fetch", async () => {
    const fetch = vi.fn();
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    for (const [set, revision] of [["bad", undefined], [SET, 0.5], [SET, 32_001], [SET, Number.MAX_SAFE_INTEGER + 1]] as const) {
      await expect(api.getRequirementVerificationEvidenceSnapshot!(SESSION, set, revision)).rejects.toMatchObject({ status: 422 });
    }
    expect(fetch).not.toHaveBeenCalled();
  });
});
