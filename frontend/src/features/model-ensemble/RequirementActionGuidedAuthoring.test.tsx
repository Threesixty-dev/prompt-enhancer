import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  PromptEnhancerTransport,
  RequirementActionCandidate,
  RequirementActionEvidenceContract,
  RequirementActionGuidedAuthoringCommand,
  RequirementActionGuidedAuthoringReview,
  RequirementActionProposal,
} from "../../shared/api/contracts";
import {
  REQUIREMENT_ACTION_FILE_JSON_SCHEMA,
  REQUIREMENT_ACTION_FILE_SCHEMA_SHA256,
} from "../../shared/api/requirementActionEvidenceContract";
import { RequirementActionGuidedAuthoring } from "./RequirementActionGuidedAuthoring";

const id = (value: string) => value.repeat(64);
const SESSION_ID = id("a");
const SOURCE_WINDOW = id("c");
const PLAN_CONFIRMATION_ID = id("d");
const PLAN_EVIDENCE = id("e");
const ACTION_TIME = "2042-01-01T00:00:00.000000Z";
const futureUtc = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString();

function fixture(label: string, runId = id("b"), manifestId = id("f")) {
  const candidates: RequirementActionCandidate[] = [
    {
      candidate_index: 0,
      action_id: id("1"),
      source_reference_id: id("2"),
      sequence: 10,
      event_kind: "tool_end",
      tool_category: "test",
      occurred_at: ACTION_TIME,
      duration_ms: 100,
      family: "command",
      state: "completed",
    },
    {
      candidate_index: 1,
      action_id: id("0"),
      source_reference_id: id("3"),
      sequence: 11,
      event_kind: "artifact",
      tool_category: "file_write",
      occurred_at: ACTION_TIME,
      duration_ms: null,
      family: "file_change",
      state: "completed",
    },
  ];
  const requirement = {
    requirement_index: 0,
    requirement_id: id("4"),
    coordinate: { message_sequence: 1, clause_index: 0 },
  };
  const provenance = {
    provider: "synthetic" as const,
    provider_version: "synthetic-provider-v1",
    adapter_version: "synthetic-adapter-v1",
    decoder_key: "synthetic-safe-events",
    decoder_version: "1",
    source_schema_version: "synthetic-safe-events-v1",
    evidence_schema_version: 2 as const,
    extraction_complete: true,
  };
  const contract: RequirementActionEvidenceContract = {
    action_descriptor_algorithm_version: "provider-local-redacted-action-descriptor-v1",
    action_descriptor_content_persisted: false,
    candidate_metadata_fingerprint_version: "requirement-action-candidate-metadata-v1",
    schema_version: "requirement-action-evidence-file-v1",
    session_id: SESSION_ID,
    expected_source_run_id: runId,
    source_window_fingerprint: SOURCE_WINDOW,
    source_projection_version: "metric-contract-v2-projection-8",
    requirement_plan_confirmation_id: PLAN_CONFIRMATION_ID,
    requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
    candidate_manifest: {
      session_id: SESSION_ID,
      source_run_id: runId,
      source_window_fingerprint: SOURCE_WINDOW,
      provenance,
      extraction_complete: true,
      enumeration_complete: true,
      actions: candidates,
      manifest_fingerprint: manifestId,
      schema_version: "requirement-action-candidate-manifest-v1",
      local_only: true,
      content_persisted: false,
    },
    requirements: [requirement],
    expected_predecessor_confirmation_id: null,
    metric_key: "logic.requirement_action_traceability",
    max_requirement_count: 1000,
    max_candidate_count: 4000,
    max_link_count: 8000,
    max_file_bytes: 65536,
    max_json_depth: 8,
    max_json_items: 8000,
    max_lifetime_seconds: 86400,
    canonicalization: "json-sort-keys-compact-ensure-ascii-v1",
    import_creates_unconfirmed_proposal_only: true,
    native_confirmation_required_for_metric_authority: true,
    all_linked_action_semantics_acknowledgement_required: true,
    native_review_displays_every_redacted_invocation_and_effect: true,
    review_visible_display_algorithm_version: "requirement-action-review-visible-display-v1",
    review_visible_display_is_injective_one_pass: true,
    review_visible_display_never_truncates: true,
    every_requirement_requires_one_link_classification: true,
    empty_action_links_are_explicit_reviewed_negative_links: true,
    action_states_are_application_issued: true,
    action_state_claims_allowed_in_file: false,
    objective_proof_claims_allowed_in_file: false,
    metric_values_allowed_in_file: false,
    raw_payload_persisted: false,
    raw_producer_claim_persisted: false,
    durable_producer_claim_shape: "installation_keyed_opaque_commitment_only",
    import_confirmation: "import_requirement_action_proposal_without_metric_authority",
    review_rubric_version: "requirement-action-review-rubric-v2",
    file_json_schema_sha256: REQUIREMENT_ACTION_FILE_SCHEMA_SHA256,
    file_json_schema: structuredClone(REQUIREMENT_ACTION_FILE_JSON_SCHEMA),
  };
  const review: RequirementActionGuidedAuthoringReview = {
    contract_version: "requirement-action-guided-authoring-v1",
    session_id: SESSION_ID,
    source_run_id: runId,
    source_window_fingerprint: SOURCE_WINDOW,
    requirement_plan_confirmation_id: PLAN_CONFIRMATION_ID,
    requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
    candidate_manifest_fingerprint: manifestId,
    expected_predecessor_confirmation_id: null,
    authoring_receipt_id: id("5"),
    descriptor_set_fingerprint: id("6"),
    requirements: [{
      requirement_id: requirement.requirement_id,
      coordinate: requirement.coordinate,
      text: `Synthetic ${label} requirement`,
      linked_action_ids: [],
    }],
    candidates,
    candidate_memberships: candidates.map((candidate) => ({
      candidate,
      candidate_metadata_fingerprint_version: "requirement-action-candidate-metadata-v1" as const,
      candidate_metadata_fingerprint: id("7"),
      descriptor_algorithm_version: "provider-local-redacted-action-descriptor-v1" as const,
      tool_name: candidate.candidate_index === 0 ? "alpha-tool" : "beta-tool",
      invocation_preview: candidate.candidate_index === 0 ? "alpha invocation" : "beta invocation",
      result_or_effect_preview: "synthetic completed effect",
      invocation_truncated: false as const,
      result_or_effect_truncated: false as const,
      redactor_version: "synthetic-redactor-v1",
      linked_requirement_ids: [],
    })),
    review_context_expires_at: futureUtc(10),
    authoring_receipt_expires_at: futureUtc(5),
    all_requirements_and_candidates_included: true,
    raw_text_persisted: false,
    local_only: true,
  };
  return { contract, review, candidates };
}

function proposalFor(
  source: ReturnType<typeof fixture>,
  command: RequirementActionGuidedAuthoringCommand,
): RequirementActionProposal {
  return {
    proposal_id: id("8"),
    session_id: SESSION_ID,
    source_run_id: command.expected_source_run_id,
    source_window_fingerprint: SOURCE_WINDOW,
    requirement_plan_confirmation_id: PLAN_CONFIRMATION_ID,
    requirement_plan_evidence_fingerprint: PLAN_EVIDENCE,
    candidate_manifest_fingerprint: command.candidate_manifest_fingerprint,
    candidate_provenance: source.contract.candidate_manifest.provenance,
    candidate_extraction_complete: true,
    candidate_enumeration_complete: true,
    expected_predecessor_confirmation_id: null,
    payload_sha256: id("9"),
    producer_receipt: {
      kind: "local_review_ui",
      claim_fingerprint: id("0"),
      authority: "untrusted_local_authoring_commitment",
      raw_claim_persisted: false,
    },
    review_rubric_version: "requirement-action-review-rubric-v2",
    requirements: source.contract.requirements,
    candidates: source.candidates,
    links: command.links.map((link) => ({
      requirement_id: source.contract.requirements[link.requirement_index].requirement_id,
      action_ids: link.action_candidate_indexes
        .map((index) => source.candidates[index].action_id)
        .sort(),
    })),
    created_at: ACTION_TIME,
    schema_version: "requirement-action-evidence-v1",
    policy_version: "reviewed-requirement-action-v1",
    status: "proposed",
    decision_id: null,
    decision: null,
    decided_at: null,
    confirmation_authority: null,
    local_only: true,
    content_persisted: false,
  };
}

function renderGuided(
  source: ReturnType<typeof fixture>,
  transport: Pick<PromptEnhancerTransport, "reviewRequirementActionGuidedAuthoring" | "submitRequirementActionGuidedAuthoring">,
  enabled = true,
) {
  return render(
    <RequirementActionGuidedAuthoring
      sessionId={SESSION_ID}
      contract={source.contract}
      transport={transport}
      enabled={enabled}
      onCreated={vi.fn()}
      onClosed={vi.fn()}
    />,
  );
}

describe("RequirementActionGuidedAuthoring", () => {
  it("submits the original candidate index after filtering", async () => {
    const source = fixture("filtered");
    const onCreated = vi.fn();
    const submit = vi.fn(async (
      _session: string,
      _contract: RequirementActionEvidenceContract,
      command: RequirementActionGuidedAuthoringCommand,
    ) => ({ proposal: proposalFor(source, command), applied: true }));
    const transport = {
      reviewRequirementActionGuidedAuthoring: vi.fn(async () => source.review),
      submitRequirementActionGuidedAuthoring: submit,
    } as Pick<PromptEnhancerTransport, "reviewRequirementActionGuidedAuthoring" | "submitRequirementActionGuidedAuthoring">;
    render(
      <RequirementActionGuidedAuthoring sessionId={SESSION_ID} contract={source.contract} transport={transport} enabled onCreated={onCreated} onClosed={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open guided action review" }));
    await screen.findByText("Synthetic filtered requirement");
    fireEvent.click(screen.getByRole("radio", { name: "Link selected actions" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Search actions" }), { target: { value: "beta" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Action 2" }));
    fireEvent.click(screen.getByRole("button", { name: "Create unconfirmed proposal" }));
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    expect(submit.mock.calls[0][2].links).toEqual([{ requirement_index: 0, action_candidate_indexes: [1] }]);
    expect(onCreated).toHaveBeenCalledOnce();
  });

  it("keeps Create disabled for selected mode with no actions and serializes explicit none as []", async () => {
    const source = fixture("empty");
    const submit = vi.fn(async (
      _session: string,
      _contract: RequirementActionEvidenceContract,
      command: RequirementActionGuidedAuthoringCommand,
    ) => ({ proposal: proposalFor(source, command), applied: true }));
    const transport = {
      reviewRequirementActionGuidedAuthoring: vi.fn(async () => source.review),
      submitRequirementActionGuidedAuthoring: submit,
    } as Pick<PromptEnhancerTransport, "reviewRequirementActionGuidedAuthoring" | "submitRequirementActionGuidedAuthoring">;
    renderGuided(source, transport);
    fireEvent.click(screen.getByRole("button", { name: "Open guided action review" }));
    await screen.findByText("Synthetic empty requirement");
    fireEvent.click(screen.getByRole("radio", { name: "Link selected actions" }));
    expect(screen.getByRole("button", { name: "Create unconfirmed proposal" })).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "No matching action" }));
    expect(screen.getByRole("button", { name: "Create unconfirmed proposal" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Create unconfirmed proposal" }));
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    expect(submit.mock.calls[0][2].links).toEqual([{ requirement_index: 0, action_candidate_indexes: [] }]);
  });

  it("ignores a late closed review and does not clear a newer review", async () => {
    const source = fixture("old");
    const newer = fixture("new", id("9"), id("8"));
    const resolvers: Array<(review: RequirementActionGuidedAuthoringReview) => void> = [];
    const signals: AbortSignal[] = [];
    const transport = {
      reviewRequirementActionGuidedAuthoring: vi.fn((_session: string, _contract: RequirementActionEvidenceContract, _request: unknown, signal?: AbortSignal) => {
        if (signal !== undefined) signals.push(signal);
        return new Promise<RequirementActionGuidedAuthoringReview>((resolve) => { resolvers.push(resolve); });
      }),
      submitRequirementActionGuidedAuthoring: vi.fn(),
    } as Pick<PromptEnhancerTransport, "reviewRequirementActionGuidedAuthoring" | "submitRequirementActionGuidedAuthoring">;
    const rendered = renderGuided(source, transport);
    fireEvent.click(screen.getByRole("button", { name: "Open guided action review" }));
    await waitFor(() => expect(transport.reviewRequirementActionGuidedAuthoring).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Close and clear" }));
    expect(signals[0].aborted).toBe(true);
    rendered.rerender(
      <RequirementActionGuidedAuthoring
        sessionId={SESSION_ID}
        contract={newer.contract}
        transport={transport}
        enabled
        onCreated={vi.fn()}
        onClosed={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open guided action review" }));
    await waitFor(() => expect(transport.reviewRequirementActionGuidedAuthoring).toHaveBeenCalledTimes(2));
    await act(async () => { resolvers[0](source.review); });
    expect(screen.queryByText("Synthetic old requirement")).toBeNull();
    await act(async () => { resolvers[1](newer.review); });
    await screen.findByText("Synthetic new requirement");
  });

  it("hides a review and ignores its late response when the transport is replaced", async () => {
    const source = fixture("transport replacement");
    let resolveOld: ((review: RequirementActionGuidedAuthoringReview) => void) | undefined;
    const transportA = {
      reviewRequirementActionGuidedAuthoring: vi.fn(() => new Promise<RequirementActionGuidedAuthoringReview>((resolve) => {
        resolveOld = resolve;
      })),
      submitRequirementActionGuidedAuthoring: vi.fn(),
    } as Pick<PromptEnhancerTransport, "reviewRequirementActionGuidedAuthoring" | "submitRequirementActionGuidedAuthoring">;
    const transportB = {
      reviewRequirementActionGuidedAuthoring: vi.fn(async () => source.review),
      submitRequirementActionGuidedAuthoring: vi.fn(),
    } as Pick<PromptEnhancerTransport, "reviewRequirementActionGuidedAuthoring" | "submitRequirementActionGuidedAuthoring">;
    const rendered = renderGuided(source, transportA);
    fireEvent.click(screen.getByRole("button", { name: "Open guided action review" }));
    await waitFor(() => expect(transportA.reviewRequirementActionGuidedAuthoring).toHaveBeenCalledOnce());
    rendered.rerender(
      <RequirementActionGuidedAuthoring
        sessionId={SESSION_ID}
        contract={source.contract}
        transport={transportB}
        enabled
        onCreated={vi.fn()}
        onClosed={vi.fn()}
      />,
    );
    await act(async () => { resolveOld?.(source.review); });
    expect(screen.queryByText("Synthetic transport replacement requirement")).toBeNull();
    expect(screen.getByRole("button", { name: "Open guided action review" })).toBeEnabled();
  });

  it("hides and ignores a pending review when guided authoring becomes disabled", async () => {
    const source = fixture("disabled owner");
    let resolveOld: ((review: RequirementActionGuidedAuthoringReview) => void) | undefined;
    const transport = {
      reviewRequirementActionGuidedAuthoring: vi.fn(() => new Promise<RequirementActionGuidedAuthoringReview>((resolve) => {
        resolveOld = resolve;
      })),
      submitRequirementActionGuidedAuthoring: vi.fn(),
    } as Pick<PromptEnhancerTransport, "reviewRequirementActionGuidedAuthoring" | "submitRequirementActionGuidedAuthoring">;
    const rendered = renderGuided(source, transport);
    fireEvent.click(screen.getByRole("button", { name: "Open guided action review" }));
    await waitFor(() => expect(transport.reviewRequirementActionGuidedAuthoring).toHaveBeenCalledOnce());
    rendered.rerender(
      <RequirementActionGuidedAuthoring
        sessionId={SESSION_ID}
        contract={source.contract}
        transport={transport}
        enabled={false}
        onCreated={vi.fn()}
        onClosed={vi.fn()}
      />,
    );
    await act(async () => { resolveOld?.(source.review); });
    expect(screen.queryByText("Synthetic disabled owner requirement")).toBeNull();
    expect(screen.getByRole("button", { name: "Open guided action review" })).toBeDisabled();
  });

  it("ignores a late review rejection without clearing a newer review", async () => {
    const source = fixture("rejection");
    const resolvers: Array<(review: RequirementActionGuidedAuthoringReview) => void> = [];
    const rejectors: Array<(reason?: unknown) => void> = [];
    const transport = {
      reviewRequirementActionGuidedAuthoring: vi.fn(() => new Promise<RequirementActionGuidedAuthoringReview>((resolve, reject) => {
        resolvers.push(resolve);
        rejectors.push(reject);
      })),
      submitRequirementActionGuidedAuthoring: vi.fn(),
    } as Pick<PromptEnhancerTransport, "reviewRequirementActionGuidedAuthoring" | "submitRequirementActionGuidedAuthoring">;
    renderGuided(source, transport);
    fireEvent.click(screen.getByRole("button", { name: "Open guided action review" }));
    await waitFor(() => expect(transport.reviewRequirementActionGuidedAuthoring).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Close and clear" }));
    fireEvent.click(screen.getByRole("button", { name: "Open guided action review" }));
    await waitFor(() => expect(transport.reviewRequirementActionGuidedAuthoring).toHaveBeenCalledTimes(2));
    await act(async () => { rejectors[0](new Error("late stale failure")); });
    expect(screen.queryByRole("alert")).toBeNull();
    await act(async () => { resolvers[1](source.review); });
    await screen.findByText("Synthetic rejection requirement");
  });

  it("guards duplicate proposal submissions while the first request is pending", async () => {
    const source = fixture("duplicate");
    let resolveSubmission: (() => void) | undefined;
    const onCreated = vi.fn();
    const submit = vi.fn((
      _session: string,
      _contract: RequirementActionEvidenceContract,
      command: RequirementActionGuidedAuthoringCommand,
    ) => new Promise<{ proposal: RequirementActionProposal; applied: true }>((resolve) => {
      resolveSubmission = () => resolve({ proposal: proposalFor(source, command), applied: true });
    }));
    const transport = {
      reviewRequirementActionGuidedAuthoring: vi.fn(async () => source.review),
      submitRequirementActionGuidedAuthoring: submit,
    } as Pick<PromptEnhancerTransport, "reviewRequirementActionGuidedAuthoring" | "submitRequirementActionGuidedAuthoring">;
    render(
      <RequirementActionGuidedAuthoring
        sessionId={SESSION_ID}
        contract={source.contract}
        transport={transport}
        enabled
        onCreated={onCreated}
        onClosed={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open guided action review" }));
    await screen.findByText("Synthetic duplicate requirement");
    fireEvent.click(screen.getByRole("radio", { name: "No matching action" }));
    const create = screen.getByRole("button", { name: "Create unconfirmed proposal" });
    fireEvent.click(create);
    fireEvent.click(create);
    expect(submit).toHaveBeenCalledOnce();
    await act(async () => { resolveSubmission?.(); });
    await waitFor(() => expect(onCreated).toHaveBeenCalledOnce());
  });

  it("clears the review and draft when the source contract changes", async () => {
    const source = fixture("before");
    const changed = fixture("after", id("9"), id("8"));
    const firstTransport = { reviewRequirementActionGuidedAuthoring: vi.fn(async () => source.review), submitRequirementActionGuidedAuthoring: vi.fn() } as Pick<PromptEnhancerTransport, "reviewRequirementActionGuidedAuthoring" | "submitRequirementActionGuidedAuthoring">;
    const rendered = renderGuided(source, firstTransport);
    fireEvent.click(screen.getByRole("button", { name: "Open guided action review" }));
    await screen.findByText("Synthetic before requirement");
    fireEvent.click(screen.getByRole("radio", { name: "Link selected actions" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Action 1" }));
    const secondTransport = { reviewRequirementActionGuidedAuthoring: vi.fn(async () => changed.review), submitRequirementActionGuidedAuthoring: vi.fn() } as Pick<PromptEnhancerTransport, "reviewRequirementActionGuidedAuthoring" | "submitRequirementActionGuidedAuthoring">;
    rendered.rerender(<RequirementActionGuidedAuthoring sessionId={SESSION_ID} contract={changed.contract} transport={secondTransport} enabled onCreated={vi.fn()} onClosed={vi.fn()} />);
    expect(screen.queryByText("Synthetic before requirement")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open guided action review" }));
    await screen.findByText("Synthetic after requirement");
    fireEvent.click(screen.getByRole("radio", { name: "Link selected actions" }));
    expect(screen.getByRole("checkbox", { name: "Action 1" })).not.toBeChecked();
  });
});
