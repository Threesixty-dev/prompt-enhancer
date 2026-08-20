import { useEffect, useMemo, useState } from "react";
import type {
  AgentMetricEvidencePreview,
  MetricLifecycleProposal,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import "./MetricEvidenceFilePanel.css";

const IMPORT_CONFIRMATION = "import_agent_metric_evidence_as_unconfirmed_proposal";
const DECISION_CONFIRMATION = "apply_local_user_metric_lifecycle_decision";
const MAX_FILE_BYTES = 64 * 1024;

type PendingDecision = {
  proposalId: string;
  decision: "confirm" | "reject";
};

type EvidenceTransport = Pick<PromptEnhancerTransport,
  | "previewAgentMetricEvidence"
  | "importAgentMetricEvidence"
  | "listMetricLifecycleProposals"
  | "decideMetricLifecycleProposal">;

function idempotency(prefix: string): string {
  return `${prefix}-${crypto.randomUUID().replaceAll("-", "")}`;
}

function proposalLabel(proposal: MetricLifecycleProposal): string {
  return `${proposal.family.replace("collaboration.", "").replaceAll("_", " ")} · ${proposal.proposal_kind}`;
}

export function MetricEvidenceFilePanel({
  compact,
  sessionId,
  sourceRunId,
  transport,
  onEvidenceChanged,
}: {
  compact: boolean;
  sessionId: string;
  sourceRunId: string;
  transport: EvidenceTransport;
  onEvidenceChanged?: () => void;
}) {
  const [proposals, setProposals] = useState<MetricLifecycleProposal[]>([]);
  const [preview, setPreview] = useState<AgentMetricEvidencePreview | null>(null);
  const [payload, setPayload] = useState<ArrayBuffer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pendingDecision, setPendingDecision] = useState<PendingDecision | null>(null);
  const capabilities = transport.previewAgentMetricEvidence !== undefined
    && transport.importAgentMetricEvidence !== undefined
    && transport.listMetricLifecycleProposals !== undefined
    && transport.decideMetricLifecycleProposal !== undefined;

  useEffect(() => {
    setPreview(null);
    setPayload(null);
    setError("");
    setPendingDecision(null);
    if (!capabilities) {
      setProposals([]);
      return;
    }
    const controller = new AbortController();
    transport.listMetricLifecycleProposals?.(sessionId, controller.signal)
      .then((page) => {
        if (!controller.signal.aborted) setProposals(page.proposals);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError("Confirmed-evidence proposals are temporarily unavailable.");
      });
    return () => controller.abort();
  }, [capabilities, sessionId, sourceRunId, transport]);

  const undecided = useMemo(
    () => proposals.filter((proposal) => proposal.status === "proposed"),
    [proposals],
  );

  async function chooseFile(file: File | undefined) {
    setPreview(null);
    setPayload(null);
    setError("");
    if (file === undefined) return;
    if (file.size < 1 || file.size > MAX_FILE_BYTES) {
      setError("Choose one canonical agent-evidence file no larger than 64 KiB.");
      return;
    }
    setBusy(true);
    try {
      const bytes = await file.arrayBuffer();
      const result = await transport.previewAgentMetricEvidence?.(sessionId, bytes);
      if (result === undefined || result.expected_source_run_id !== sourceRunId) {
        setError("The file is not bound to this exact sealed source run.");
        return;
      }
      setPayload(bytes);
      setPreview(result);
    } catch {
      setError("The file failed strict local validation; no proposal was imported.");
    } finally {
      setBusy(false);
    }
  }

  async function importPreview() {
    if (preview === null || payload === null || transport.importAgentMetricEvidence === undefined) return;
    setBusy(true);
    setError("");
    try {
      const result = await transport.importAgentMetricEvidence(
        sessionId,
        payload,
        preview.payload_sha256,
        IMPORT_CONFIRMATION,
        idempotency("agent-evidence-import"),
      );
      setProposals((current) => [
        ...current.filter((item) => item.proposal_id !== result.proposal.proposal_id),
        result.proposal,
      ]);
      setPreview(null);
      setPayload(null);
    } catch {
      setError("The preview binding changed or the proposal could not be imported.");
    } finally {
      setBusy(false);
    }
  }

  async function applyDecision(proposal: MetricLifecycleProposal, decision: "confirm" | "reject") {
    if (transport.decideMetricLifecycleProposal === undefined) return;
    setBusy(true);
    setError("");
    try {
      const result = await transport.decideMetricLifecycleProposal(
        sessionId,
        proposal.proposal_id,
        {
          expected_source_run_id: proposal.source_run_id,
          expected_proposal_revision: proposal.proposal_revision,
          decision,
          confirmation: DECISION_CONFIRMATION,
        },
        idempotency(`agent-evidence-${decision}`),
      );
      setProposals((current) => current.map((item) => (
        item.proposal_id === result.proposal.proposal_id ? result.proposal : item
      )));
      setPendingDecision(null);
      onEvidenceChanged?.();
    } catch {
      setError("The source window or proposal authority changed; refresh before deciding.");
    } finally {
      setBusy(false);
    }
  }

  if (compact) {
    return (
      <section aria-label="Confirmed metric evidence" className="metric-evidence-file metric-evidence-file--compact">
        <strong>Confirmed evidence</strong>
        <span>{capabilities ? `${undecided.length} proposal${undecided.length === 1 ? "" : "s"} awaiting review` : "Local evidence import unavailable"}</span>
        <small>Review and confirm typed agent files in the dashboard; this compact view never auto-approves evidence.</small>
      </section>
    );
  }

  return (
    <section aria-label="Import agent metric evidence" className="metric-evidence-file">
      <header>
        <div><strong>Import typed agent evidence</strong><span>Local file → strict preview → unconfirmed proposal → your decision</span></div>
        <small>Files cannot contain scores, prose, transcripts, paths, or objective-proof claims.</small>
      </header>
      {!capabilities ? (
        <p>This local runtime does not expose the reviewed evidence-file boundary.</p>
      ) : (
        <>
          <label>
            <span>Choose canonical evidence file</span>
            <input
              accept=".json,application/vnd.prompt-enhancer.agent-metric-evidence+json"
              disabled={busy}
              onChange={(event) => void chooseFile(event.currentTarget.files?.[0])}
              type="file"
            />
          </label>
          {preview !== null && (
            <div className="metric-evidence-file__preview" role="status">
              <span><strong>{preview.metric_key.replace("collaboration.", "").replaceAll("_", " ")}</strong> · {preview.proposal_kind}</span>
              <small>Producer claim: {preview.producer.producer_id} / {preview.producer.model_id} · not evidence authority</small>
              <button disabled={busy} onClick={() => void importPreview()} type="button">Import as unconfirmed</button>
            </div>
          )}
          {undecided.length > 0 && (
            <ul aria-label="Evidence proposals awaiting local decision">
              {undecided.map((proposal) => (
                <li key={proposal.proposal_id}>
                  <span><strong>{proposalLabel(proposal)}</strong><small>Bound to run {proposal.source_run_id.slice(0, 8)}…</small></span>
                  {pendingDecision?.proposalId === proposal.proposal_id ? (
                    <div
                      aria-label={`${pendingDecision.decision === "confirm" ? "Confirm" : "Reject"} ${proposalLabel(proposal)}`}
                      className="metric-evidence-file__decision-confirmation"
                      role="group"
                    >
                      <p>
                        {pendingDecision.decision === "confirm"
                          ? "This browser-session decision admits the typed lifecycle receipt into the next sealed metric denominator."
                          : "This browser-session decision permanently rejects this proposal revision."}
                      </p>
                      <div>
                        <button disabled={busy} onClick={() => setPendingDecision(null)} type="button">Cancel</button>
                        <button
                          disabled={busy}
                          onClick={() => void applyDecision(proposal, pendingDecision.decision)}
                          type="button"
                        >
                          {pendingDecision.decision === "confirm" ? "Apply confirmation" : "Apply rejection"}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <button disabled={busy} onClick={() => setPendingDecision({ proposalId: proposal.proposal_id, decision: "reject" })} type="button">Reject</button>
                      <button disabled={busy} onClick={() => setPendingDecision({ proposalId: proposal.proposal_id, decision: "confirm" })} type="button">Confirm evidence</button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
          {error !== "" && <p className="metric-evidence-file__error" role="alert">{error}</p>}
          <p>Confirmation records typed evidence only. Re-run the local metric analysis to publish the updated sealed snapshot.</p>
        </>
      )}
    </section>
  );
}
