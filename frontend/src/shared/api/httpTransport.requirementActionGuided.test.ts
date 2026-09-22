import { describe, expect, it, vi } from "vitest";

import type {
  RequirementActionEvidenceContract,
  RequirementActionGuidedAuthoringCommand,
} from "./contracts";
import { createHttpTransport, TransportError } from "./httpTransport";

const id = (value: string) => value.repeat(64);
const SESSION = id("a");
const RUN = id("b");
const WINDOW = id("c");
const PLAN = id("d");
const PLAN_EVIDENCE = id("e");
const MANIFEST = id("f");
const ACTION = id("1");
const REQUIREMENT = id("2");
const NOW = () => new Date(Date.now() + 5 * 60_000).toISOString();

const provenance = {
  provider: "synthetic", provider_version: "synthetic-v1", adapter_version: "synthetic-adapter-v1",
  decoder_key: "safe-events", decoder_version: "1", source_schema_version: "synthetic-source-v1",
  evidence_schema_version: 2, extraction_complete: true,
} as const;
const candidate = {
  candidate_index: 0, action_id: ACTION, source_reference_id: id("3"), sequence: 1,
  event_kind: "tool_end", tool_category: "test", occurred_at: "2042-01-01T00:00:00Z",
  duration_ms: 1, family: "command", state: "completed",
} as const;
const requirement = {
  requirement_index: 0, requirement_id: REQUIREMENT, coordinate: { message_sequence: 1, clause_index: 0 },
} as const;
const contract = {
  session_id: SESSION, expected_source_run_id: RUN, source_window_fingerprint: WINDOW,
  requirement_plan_confirmation_id: PLAN, requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
  candidate_metadata_fingerprint_version: "requirement-action-candidate-metadata-v1",
  action_descriptor_algorithm_version: "provider-local-redacted-action-descriptor-v1",
  candidate_manifest: {
    session_id: SESSION, source_run_id: RUN, source_window_fingerprint: WINDOW, provenance,
    extraction_complete: true, enumeration_complete: true, actions: [candidate], manifest_fingerprint: MANIFEST,
  },
  requirements: [requirement], expected_predecessor_confirmation_id: null,
} as unknown as RequirementActionEvidenceContract;
const command: RequirementActionGuidedAuthoringCommand = {
  expected_source_run_id: RUN, source_window_fingerprint: WINDOW,
  requirement_plan_confirmation_id: PLAN, requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
  candidate_manifest_fingerprint: MANIFEST, expected_predecessor_confirmation_id: null,
  authoring_receipt_id: id("4"), links: [{ requirement_index: 0, action_candidate_indexes: [0] }],
  complete_requirement_link_classification_acknowledged: true,
};

function privateJson(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store, private",
      Pragma: "no-cache",
    },
  });
}

const auth = {
  csrf_token: "synthetic-csrf", expires_in_seconds: 300,
  user_presence_confirmation_available: true,
  user_presence_confirmation_mode: "native_bridge_bound_token",
};

function review() {
  return {
    contract_version: "requirement-action-guided-authoring-v1",
    session_id: SESSION, source_run_id: RUN, source_window_fingerprint: WINDOW,
    requirement_plan_confirmation_id: PLAN, requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
    candidate_manifest_fingerprint: MANIFEST, expected_predecessor_confirmation_id: null,
    authoring_receipt_id: command.authoring_receipt_id, descriptor_set_fingerprint: id("5"),
    requirements: [{ requirement_id: REQUIREMENT, coordinate: requirement.coordinate, text: "Synthetic requirement", linked_action_ids: [] }],
    candidates: [candidate],
    candidate_memberships: [{
      candidate, candidate_metadata_fingerprint_version: "requirement-action-candidate-metadata-v1",
      candidate_metadata_fingerprint: id("6"),
      descriptor_algorithm_version: "provider-local-redacted-action-descriptor-v1",
      tool_name: "synthetic-tool", invocation_preview: "synthetic invocation",
      result_or_effect_preview: "synthetic effect", invocation_truncated: false,
      result_or_effect_truncated: false, redactor_version: "synthetic-redactor-v1",
      linked_requirement_ids: [],
    }],
    review_context_expires_at: NOW(), authoring_receipt_expires_at: NOW(),
    all_requirements_and_candidates_included: true, raw_text_persisted: false, local_only: true,
  };
}

function proposal() {
  return {
    proposal_id: id("7"), session_id: SESSION, source_run_id: RUN, source_window_fingerprint: WINDOW,
    requirement_plan_confirmation_id: PLAN, requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
    candidate_manifest_fingerprint: MANIFEST, candidate_provenance: provenance,
    candidate_extraction_complete: true, candidate_enumeration_complete: true,
    expected_predecessor_confirmation_id: null, payload_sha256: id("8"),
    producer_receipt: {
      kind: "local_review_ui", claim_fingerprint: id("9"),
      authority: "untrusted_local_authoring_commitment", raw_claim_persisted: false,
    },
    review_rubric_version: "requirement-action-review-rubric-v2",
    requirements: [requirement], candidates: [candidate], links: [{ requirement_id: REQUIREMENT, action_ids: [ACTION] }],
    created_at: "2042-01-01T00:00:00Z", schema_version: "requirement-action-evidence-v1",
    policy_version: "reviewed-requirement-action-v1", status: "proposed",
    decision_id: null, decision: null, decided_at: null, confirmation_authority: null,
    local_only: true, content_persisted: false,
  };
}

function transport(fetchMock: ReturnType<typeof vi.fn>, approval = vi.fn().mockResolvedValue("p".repeat(32))) {
  return createHttpTransport({
    fetch: fetchMock as unknown as typeof fetch,
    origin: "http://127.0.0.1:4173",
    userPresenceApproval: approval,
    userPresenceBridgeAvailable: () => true,
  });
}

describe("guided requirement-action HTTP transport", () => {
  it("opens the exact native review with the original contract and forwarded signal", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(privateJson(auth))
      .mockResolvedValueOnce(privateJson(review()));
    const approval = vi.fn().mockResolvedValue("p".repeat(32));
    const signal = new AbortController().signal;

    await transport(fetchMock, approval).reviewRequirementActionGuidedAuthoring!(SESSION, contract, {
      expected_source_run_id: RUN, source_window_fingerprint: WINDOW,
      requirement_plan_confirmation_id: PLAN, requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
      candidate_manifest_fingerprint: MANIFEST, expected_predecessor_confirmation_id: null,
      confirmation: "open_exact_local_requirement_action_guided_authoring",
    }, signal);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toBe(`/v1/sessions/${SESSION}/requirement-action-evidence/guided-authoring/review`);
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({
      method: "POST", cache: "no-store", signal,
    }));
    expect((fetchMock.mock.calls[1][1] as RequestInit).body).toBe(JSON.stringify({
      expected_source_run_id: RUN, source_window_fingerprint: WINDOW,
      requirement_plan_confirmation_id: PLAN, requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
      candidate_manifest_fingerprint: MANIFEST, expected_predecessor_confirmation_id: null,
      confirmation: "open_exact_local_requirement_action_guided_authoring",
    }));
    expect((fetchMock.mock.calls[1][1] as RequestInit).headers).toEqual(expect.objectContaining({
      "X-Prompt-Enhancer-CSRF": "synthetic-csrf",
      "X-Prompt-Enhancer-User-Presence": "p".repeat(32),
      "Content-Type": "application/json",
    }));
    expect(approval).toHaveBeenCalledWith(expect.objectContaining({
      method: "POST",
      path: `/v1/sessions/${SESSION}/requirement-action-evidence/guided-authoring/review`,
    }));
  });

  it("submits only the supplied local graph with its stable idempotency key and no native token", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(privateJson(auth))
      .mockResolvedValueOnce(privateJson({ proposal: proposal(), applied: true }));
    const approval = vi.fn().mockResolvedValue("p".repeat(32));
    const signal = new AbortController().signal;

    await transport(fetchMock, approval).submitRequirementActionGuidedAuthoring!(
      SESSION, contract, command, "synthetic-guided-idempotency", signal,
    );

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toBe(`/v1/sessions/${SESSION}/requirement-action-evidence/guided-authoring/proposals`);
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({
      method: "POST", cache: "no-store", signal, body: JSON.stringify(command),
    }));
    expect((fetchMock.mock.calls[1][1] as RequestInit).headers).toEqual(expect.objectContaining({
      "X-Prompt-Enhancer-CSRF": "synthetic-csrf",
      "Idempotency-Key": "synthetic-guided-idempotency",
      "Content-Type": "application/json",
    }));
    expect((fetchMock.mock.calls[1][1] as RequestInit).headers).not.toHaveProperty("X-Prompt-Enhancer-User-Presence");
    expect(approval).not.toHaveBeenCalled();
  });

  it.each([
    ["malformed review", { synthetic_secret: "do-not-reflect" }],
    ["stale review", { ...review(), source_window_fingerprint: id("0") }],
  ])("fails closed on a %s response without exposing its body", async (_label, response) => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(privateJson(auth))
      .mockResolvedValueOnce(privateJson(response));
    const error = await transport(fetchMock).reviewRequirementActionGuidedAuthoring!(SESSION, contract, {
      expected_source_run_id: RUN, source_window_fingerprint: WINDOW,
      requirement_plan_confirmation_id: PLAN, requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
      candidate_manifest_fingerprint: MANIFEST, expected_predecessor_confirmation_id: null,
      confirmation: "open_exact_local_requirement_action_guided_authoring",
    }).catch((value) => value);

    expect(error).toBeInstanceOf(TransportError);
    expect(error).toMatchObject({ status: 200 });
    expect(String(error)).not.toContain("do-not-reflect");
  });

  it("rejects a stale guided proposal outcome rather than adopting it", async () => {
    const stale = proposal();
    stale.candidate_manifest_fingerprint = id("0");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(privateJson(auth))
      .mockResolvedValueOnce(privateJson({ proposal: stale, applied: true }));

    await expect(transport(fetchMock).submitRequirementActionGuidedAuthoring!(
      SESSION, contract, command, "synthetic-stale-idempotency",
    )).rejects.toMatchObject({ status: 200 });
  });
});
