import { describe, expect, it, vi } from "vitest";
import { createHttpTransport } from "./httpTransport";
import type { ObservedCheckAuthorityProvenance, ObservedCheckCandidateManifest, ObservedCheckCriterionReview } from "./contracts";

const id = (character: string): string => character.repeat(64);
const SESSION = id("a");
const SET = id("b");
const OPPORTUNITY = id("c");
const REQUIREMENT = id("d");
const RUN = id("e");
const WINDOW = id("f");
const PLAN = id("0");
const PROPOSAL = id("1");
const CANDIDATE = id("2");
const MANIFEST = id("3");
const RECEIPT = id("4");
const REVIEW_FINGERPRINT = id("5");
const auth = { csrf_token: "synthetic-csrf-token", expires_in_seconds: 300, user_presence_confirmation_available: true, user_presence_confirmation_mode: "native_bridge_bound_token" };
const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json", "Cache-Control": "no-store, private", Pragma: "no-cache" } });

function candidate() {
  return { candidate_id: CANDIDATE, observed_sequence: 3, check_kind: "test" as const, observed_outcome: "passed" as const, provider_execution_status: "completed" as const, exit_code: 0 as const, source_completion_schema_version: "observed-check-completion-v1" as const, outcome_interpreter_version: "pytest-exit-status-v1" as const, classifier_version: "local-command-rules-v1" as const, normalizer_version: "strict-shell-free-v2" as const, rule_id: "test.pytest" as const, local_only: true as const, content_persisted: false as const };
}
function manifest(): ObservedCheckCandidateManifest {
  return { session_id: SESSION, opportunity_set_fingerprint: SET, opportunity_id: OPPORTUNITY, requirement_id: REQUIREMENT, expected_source_run_id: RUN, source_window_fingerprint: WINDOW, requirement_plan_confirmation_id: PLAN, requirement_plan_proposal_id: PROPOSAL, expected_predecessor_authority_id: null, through_revision: 2, candidate_manifest_fingerprint: MANIFEST, candidates: [candidate()], schema_version: "requirement-observed-check-review-v1", local_only: true, content_persisted: false };
}
function review(): ObservedCheckCriterionReview {
  return { session_id: SESSION, opportunity_set_fingerprint: SET, opportunity_id: OPPORTUNITY, requirement_id: REQUIREMENT, expected_source_run_id: RUN, source_window_fingerprint: WINDOW, requirement_plan_confirmation_id: PLAN, requirement_plan_proposal_id: PROPOSAL, expected_predecessor_authority_id: null, through_revision: 2, candidate_manifest_fingerprint: MANIFEST, candidate: candidate(), requirement_text: "Synthetic requirement", check_tool_name: "pytest", check_invocation_preview: "pytest -q synthetic_test.py", check_effect_preview: "exit 0", review_receipt_id: RECEIPT, review_fingerprint: REVIEW_FINGERPRINT, review_expires_at: new Date(Date.now() + 60_000).toISOString(), full_criterion_coverage_acknowledgement_required: true, objective_result_issued: false, schema_version: "requirement-observed-check-review-v1", local_only: true, content_persisted: false };
}
function provenance(): ObservedCheckAuthorityProvenance {
  return { authority_record_id: id("6"), session_id: SESSION, opportunity_set_fingerprint: SET, opportunity_id: OPPORTUNITY, requirement_id: REQUIREMENT, source_run_id: RUN, source_window_fingerprint: WINDOW, requirement_plan_confirmation_id: PLAN, requirement_plan_proposal_id: PROPOSAL, candidate_manifest_fingerprint: MANIFEST, source_reference_id: id("7"), coverage_review_reference_id: id("8"), observed_sequence: 3, check_kind: "test", provider_execution_status: "completed", observed_outcome: "passed", exit_code: 0, source_completion_schema_version: "observed-check-completion-v1", outcome_interpreter_version: "pytest-exit-status-v1", classifier_version: "local-command-rules-v1", normalizer_version: "strict-shell-free-v2", rule_id: "test.pytest", coverage_review_version: "native-full-criterion-coverage-v1", full_criterion_coverage_acknowledged: true, provenance_fingerprint: id("9"), schema_version: "observed-check-authority-provenance-v1", local_only: true, content_persisted: false };
}

describe("observed-check HTTP transport", () => {
  it("posts an exact preflight request and parses the content-free candidate manifest", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(manifest()));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    const value = await api.preflightRequirementVerificationObservedCheck!(SESSION, SET, OPPORTUNITY, { expected_source_run_id: RUN, through_revision: 2, expected_predecessor_authority_id: null });
    expect(value).toEqual(manifest());
    expect(fetch.mock.calls[1]?.[0]).toBe(`/v1/sessions/${SESSION}/requirement-verification-evidence/opportunity-sets/${SET}/opportunities/${OPPORTUNITY}/observed-checks/preflight`);
    expect((fetch.mock.calls[1]?.[1] as RequestInit).body).toBe(JSON.stringify({ expected_source_run_id: RUN, through_revision: 2, expected_predecessor_authority_id: null }));
  });

  it("requires the native proof for exact candidate review and rejects malformed server payloads", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(review()));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173", userPresenceApproval: vi.fn().mockResolvedValue(id("6")), userPresenceBridgeAvailable: () => true });
    const expected = review();
    fetch.mockReset();
    fetch.mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(expected));
    const value = await api.reviewRequirementVerificationObservedCheck!(SESSION, SET, OPPORTUNITY, CANDIDATE, { expected_source_run_id: RUN, through_revision: 2, expected_predecessor_authority_id: null, candidate_manifest_fingerprint: MANIFEST, confirmation: "open_exact_local_requirement_observed_check_review" });
    expect(value).toEqual(expected);
    expect(fetch.mock.calls[1]?.[0]).toContain(`/observed-checks/${CANDIDATE}/review`);
    expect((fetch.mock.calls[1]?.[1] as RequestInit).body).not.toContain(CANDIDATE);

    const malformed = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json({ ...manifest(), candidates: [{ ...candidate(), exit_code: 2 }] }));
    const malformedApi = createHttpTransport({ fetch: malformed as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    await expect(malformedApi.preflightRequirementVerificationObservedCheck!(SESSION, SET, OPPORTUNITY, { expected_source_run_id: RUN, through_revision: 2, expected_predecessor_authority_id: null })).rejects.toMatchObject({ status: 200 });
  });

  it("does not permit a client-selected outcome or method in the issue command", async () => {
    const fetch = vi.fn();
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    await expect(api.issueRequirementVerificationObservedCheck!(SESSION, SET, OPPORTUNITY, CANDIDATE, {
      expected_source_run_id: RUN, source_window_fingerprint: WINDOW, through_revision: 2, expected_predecessor_authority_id: null,
      candidate_manifest_fingerprint: MANIFEST, review_receipt_id: RECEIPT, review_fingerprint: REVIEW_FINGERPRINT,
      full_criterion_coverage_acknowledged: false as never, confirmation: "issue_exact_local_requirement_observed_check_result",
    }, "synthetic-observed-check-key")).rejects.toMatchObject({ status: 422 });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("reads only the requested provenance record and rejects foreign payload identity", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(provenance()));
    const api = createHttpTransport({ fetch: fetch as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    const value = await api.getRequirementVerificationObservedCheckProvenance!(SESSION, id("6"));
    expect(value).toEqual(provenance());
    expect(fetch.mock.calls[1]?.[0]).toBe(`/v1/sessions/${SESSION}/requirement-verification-evidence/objective-results/${id("6")}/observed-check-provenance`);

    const foreign = { ...provenance(), session_id: id("9") };
    const malformed = vi.fn().mockResolvedValueOnce(json(auth)).mockResolvedValueOnce(json(foreign));
    const malformedApi = createHttpTransport({ fetch: malformed as unknown as typeof globalThis.fetch, origin: "http://127.0.0.1:4173" });
    await expect(malformedApi.getRequirementVerificationObservedCheckProvenance!(SESSION, id("6"))).rejects.toMatchObject({ status: 200 });
  });
});
