import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  AgentMetricEvidencePreview,
  MetricLifecycleProposal,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { MetricEvidenceFilePanel } from "./MetricEvidenceFilePanel";

const sessionId = "2".repeat(64);
const runId = "3".repeat(64);
const proposal: MetricLifecycleProposal = {
  proposal_id: "1".repeat(64),
  session_id: sessionId,
  source_run_id: runId,
  proposal_revision: 1,
  proposal_kind: "opportunity",
  family: "collaboration.ambiguity_resolution",
  opportunity_kind: "ambiguity",
  opportunity_id: "4".repeat(64),
  link_kind: null,
  outcome_kind: null,
  enumerated_opportunity_ids: [],
  status: "proposed",
  decision_id: null,
  decision: null,
  created_at: "2042-01-01T00:00:00+00:00",
  decided_at: null,
  schema_version: "metric-lifecycle-evidence-v1",
  policy_version: "explicit-local-confirmation-v1",
  local_only: true,
  content_persisted: false,
};
const preview: AgentMetricEvidencePreview = {
  schema_version: "agent-metric-evidence-file-v1",
  payload_sha256: "5".repeat(64),
  session_id: sessionId,
  expected_source_run_id: runId,
  source_window_fingerprint: "6".repeat(64),
  metric_key: "collaboration.ambiguity_resolution",
  proposal_kind: "opportunity",
  expires_at: "2042-01-01T01:00:00+00:00",
  producer: {
    kind: "local_coding_agent",
    producer_id: "example-agent",
    producer_version: "example-agent-v1",
    model_id: "example-model-v1",
    authority: "untrusted_provenance_claim",
  },
  creates_unconfirmed_proposal_only: true,
  requires_authenticated_local_user_confirmation: true,
  can_set_numeric_metric: false,
  objective_receipt_claims_accepted: false,
  raw_payload_persisted: false,
};

function transport(initial: MetricLifecycleProposal[] = []): Pick<PromptEnhancerTransport,
  "previewAgentMetricEvidence" | "importAgentMetricEvidence" | "listMetricLifecycleProposals" | "decideMetricLifecycleProposal"> {
  return {
    listMetricLifecycleProposals: vi.fn().mockResolvedValue({
      session_id: sessionId, proposals: initial, total: initial.length, complete: true,
    }),
    previewAgentMetricEvidence: vi.fn().mockResolvedValue(preview),
    importAgentMetricEvidence: vi.fn().mockResolvedValue({
      payload_sha256: preview.payload_sha256,
      proposal,
      applied: true,
      producer_claim_persisted: false,
      raw_payload_persisted: false,
      requires_authenticated_local_user_confirmation: true,
    }),
    decideMetricLifecycleProposal: vi.fn().mockImplementation(async (_session, _proposal, request) => ({
      proposal: {
        ...proposal,
        status: request.decision === "confirm" ? "confirmed" : "rejected",
        decision_id: "7".repeat(64),
        decision: request.decision,
        decided_at: "2042-01-01T00:01:00+00:00",
      },
      applied: true,
    })),
  };
}

describe("MetricEvidenceFilePanel", () => {
  it("keeps compact mode read-only while reporting pending local review", async () => {
    render(<MetricEvidenceFilePanel compact sessionId={sessionId} sourceRunId={runId} transport={transport([proposal])} />);
    expect(await screen.findByText("1 proposal awaiting review")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /confirm evidence/i })).not.toBeInTheDocument();
    expect(screen.getByText(/never auto-approves evidence/i)).toBeInTheDocument();
  });

  it("previews, imports, and requires a separate explicit confirmation", async () => {
    const local = transport();
    const changed = vi.fn();
    render(<MetricEvidenceFilePanel compact={false} onEvidenceChanged={changed} sessionId={sessionId} sourceRunId={runId} transport={local} />);
    const file = new File(["{}"], "example.json", { type: "application/json" });
    Object.defineProperty(file, "arrayBuffer", { value: async () => new TextEncoder().encode("{}").buffer });
    fireEvent.change(screen.getByLabelText("Choose canonical evidence file"), { target: { files: [file] } });

    expect(await screen.findByText(/Producer claim: example-agent/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm evidence" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Import as unconfirmed" }));
    expect(await screen.findByRole("button", { name: "Confirm evidence" })).toBeInTheDocument();
    expect(screen.getByText(/Confirmation records typed evidence only/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm evidence" }));
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
    expect(local.previewAgentMetricEvidence).toHaveBeenCalledTimes(1);
    expect(local.importAgentMetricEvidence).toHaveBeenCalledTimes(1);
    expect(local.decideMetricLifecycleProposal).toHaveBeenCalledTimes(1);
  });
});
