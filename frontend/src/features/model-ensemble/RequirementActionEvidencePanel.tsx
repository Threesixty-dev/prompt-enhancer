import { useEffect, useMemo, useRef, useState } from "react";
import type {
  PromptEnhancerTransport,
  ModelRequirementActionEvidenceBinding,
  RequirementActionDecisionRequest,
  RequirementActionEvidenceContract,
  RequirementActionEvidencePreview,
  RequirementActionProposal,
  RequirementActionProposalReview,
} from "../../shared/api/contracts";
import {
  MAX_REQUIREMENT_ACTION_FILE_BYTES,
  REQUIREMENT_ACTION_DECISION_CONFIRMATION,
  REQUIREMENT_ACTION_IMPORT_CONFIRMATION,
  REQUIREMENT_ACTION_MEDIA_TYPE,
  REQUIREMENT_ACTION_REVIEW_CONFIRMATION,
  requirementActionProposalMatchesContract,
} from "../../shared/api/requirementActionEvidenceContract";
import "./MetricEvidenceFilePanel.css";

type RequirementActionTransport = Pick<PromptEnhancerTransport,
  | "getRequirementActionEvidenceContract"
  | "previewRequirementActionEvidence"
  | "importRequirementActionEvidence"
  | "listRequirementActionProposals"
  | "reviewRequirementActionProposal"
  | "decideRequirementActionProposal">
  & Partial<Pick<PromptEnhancerTransport, "getUserPresenceCapability">>;

type PendingDecision = { proposalId: string; decision: "confirm" | "reject" };

function idempotency(prefix: string): string {
  return `${prefix}-${crypto.randomUUID().replaceAll("-", "")}`;
}

function exactContractBinding(
  contract: RequirementActionEvidenceContract,
  sessionId: string,
  sourceRunId: string,
  sourceProjectionVersion: RequirementActionEvidenceContract["source_projection_version"],
): boolean {
  return contract.session_id === sessionId
    && contract.expected_source_run_id === sourceRunId
    && contract.source_projection_version === sourceProjectionVersion
    && contract.candidate_manifest.session_id === sessionId
    && contract.candidate_manifest.source_run_id === sourceRunId
    && contract.candidate_manifest.source_window_fingerprint === contract.source_window_fingerprint;
}

function proposalCurrent(
  proposal: RequirementActionProposal,
  contract: RequirementActionEvidenceContract,
): boolean {
  return requirementActionProposalMatchesContract(proposal, contract);
}

function reviewCurrent(
  review: RequirementActionProposalReview,
  proposal: RequirementActionProposal,
  contract: RequirementActionEvidenceContract,
): boolean {
  const expiry = Math.min(
    Date.parse(review.review_context_expires_at),
    Date.parse(review.review_receipt_expires_at),
  );
  return proposalCurrent(proposal, contract)
    && review.proposal_id === proposal.proposal_id
    && review.session_id === proposal.session_id
    && review.source_run_id === proposal.source_run_id
    && review.source_window_fingerprint === proposal.source_window_fingerprint
    && review.payload_sha256 === proposal.payload_sha256
    && review.requirement_plan_evidence_fingerprint === proposal.requirement_plan_evidence_fingerprint
    && review.candidate_manifest_fingerprint === proposal.candidate_manifest_fingerprint
    && review.review_visible_display_algorithm_version === contract.review_visible_display_algorithm_version
    && review.candidate_memberships.every((membership) => (
      membership.candidate_metadata_fingerprint_version === contract.candidate_metadata_fingerprint_version
      && /^[0-9a-f]{64}$/.test(membership.candidate_metadata_fingerprint)
    ))
    && review.all_requirements_and_candidates_displayed === true
    && expiry > Date.now();
}

function proposalSummary(proposal: RequirementActionProposal): string {
  const linked = proposal.links.filter((link) => link.action_ids.length > 0).length;
  const empty = proposal.links.length - linked;
  const links = proposal.links.reduce((sum, link) => sum + link.action_ids.length, 0);
  return `${proposal.requirements.length} requirements · ${proposal.candidates.length} action candidates · ${linked} linked · ${empty} explicit empty · ${links} memberships`;
}

function humanCode(value: string): string {
  return value.replaceAll("_", " ");
}

function durationLabel(value: number | null): string {
  return value === null ? "duration unknown" : `${value} ms`;
}

function publicBindingIdentity(binding: ModelRequirementActionEvidenceBinding): string {
  return JSON.stringify([
    binding.evidence_source,
    binding.source_run_id,
    binding.requirement_plan_confirmation_id,
    binding.requirement_plan_evidence_fingerprint,
    binding.candidate_manifest_fingerprint,
    binding.confirmation_id,
    binding.proposal_id,
    binding.reviewed_descriptor_set_fingerprint,
    binding.evidence_fingerprint,
    binding.evidence_schema_version,
    binding.evidence_policy_version,
    binding.local_only,
    binding.content_persisted,
  ]);
}

export function RequirementActionEvidencePanel({
  compact,
  sessionId,
  sourceRunId,
  sourceProjectionVersion,
  publicEvidenceBinding,
  publicEvidenceSource,
  transport,
  onEvidenceChanged,
}: {
  compact: boolean;
  sessionId: string;
  sourceRunId: string;
  sourceProjectionVersion: RequirementActionEvidenceContract["source_projection_version"];
  /** Strictly parsed public DTO; production supplies it so same-source A→B authority resets are exact. */
  publicEvidenceBinding?: ModelRequirementActionEvidenceBinding;
  publicEvidenceSource: ModelRequirementActionEvidenceBinding["evidence_source"];
  transport: RequirementActionTransport;
  onEvidenceChanged?: () => void;
}) {
  const [contract, setContract] = useState<RequirementActionEvidenceContract | null>(null);
  const [proposals, setProposals] = useState<RequirementActionProposal[]>([]);
  const [preview, setPreview] = useState<RequirementActionEvidencePreview | null>(null);
  const [payload, setPayload] = useState<ArrayBuffer | null>(null);
  const [confirmationAvailable, setConfirmationAvailable] = useState(false);
  const [pendingDecision, setPendingDecision] = useState<PendingDecision | null>(null);
  const [review, setReview] = useState<RequirementActionProposalReview | null>(null);
  const [allItemsAcknowledged, setAllItemsAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const operationRef = useRef<AbortController | null>(null);
  const bindingRef = useRef("");
  const resolvedPublicEvidenceSource = publicEvidenceBinding?.evidence_source ?? publicEvidenceSource;
  const selectedBinding = `${sessionId}:${sourceRunId}:${sourceProjectionVersion}:${
    publicEvidenceBinding === undefined ? publicEvidenceSource : publicBindingIdentity(publicEvidenceBinding)
  }`;
  const bindingInvalid = resolvedPublicEvidenceSource === "binding_invalid";
  const reviewedMetadataBinding = useMemo(() => (
    review === null ? "" : review.candidate_memberships
      .map((membership) => (
        `${membership.candidate.action_id}:${membership.candidate_metadata_fingerprint_version}:${membership.candidate_metadata_fingerprint}`
      )).join("|")
  ), [review]);
  bindingRef.current = selectedBinding;

  const capabilities = transport.getRequirementActionEvidenceContract !== undefined
    && transport.previewRequirementActionEvidence !== undefined
    && transport.importRequirementActionEvidence !== undefined
    && transport.listRequirementActionProposals !== undefined
    && transport.reviewRequirementActionProposal !== undefined
    && transport.decideRequirementActionProposal !== undefined;

  useEffect(() => {
    operationRef.current?.abort();
    setContract(null);
    setProposals([]);
    setPreview(null);
    setPayload(null);
    setPendingDecision(null);
    setReview(null);
    setAllItemsAcknowledged(false);
    setConfirmationAvailable(false);
    setBusy(false);
    setError("");
    setCopyStatus("");
    if (!capabilities) return;
    const controller = new AbortController();
    operationRef.current = controller;
    const binding = selectedBinding;
    Promise.all([
      transport.getRequirementActionEvidenceContract!(sessionId, controller.signal),
      transport.listRequirementActionProposals!(sessionId, controller.signal),
      transport.getUserPresenceCapability === undefined
        ? Promise.resolve(null)
        : transport.getUserPresenceCapability(controller.signal),
    ]).then(([loadedContract, collection, presence]) => {
      if (controller.signal.aborted || bindingRef.current !== binding) return;
      if (!exactContractBinding(loadedContract, sessionId, sourceRunId, sourceProjectionVersion)) {
        setError("Requirement-action review is not bound to this exact sealed r7 run and source window.");
        return;
      }
      setContract(loadedContract);
      setProposals(collection.proposals.filter((proposal) => proposal.session_id === sessionId));
      setConfirmationAvailable(presence?.confirmation_available === true);
    }).catch(() => {
      if (!controller.signal.aborted && bindingRef.current === binding) {
        setError("Reviewed requirement-action evidence is temporarily unavailable.");
      }
    });
    return () => controller.abort();
  }, [capabilities, selectedBinding, sessionId, sourceProjectionVersion, sourceRunId, transport]);

  useEffect(() => {
    if (review === null) return;
    const expiresIn = Math.min(
      Date.parse(review.review_context_expires_at),
      Date.parse(review.review_receipt_expires_at),
    ) - Date.now();
    if (expiresIn <= 0) {
      setReview(null);
      setAllItemsAcknowledged(false);
      setPendingDecision(null);
      setError("The exact local requirement/action review receipt expired. Open a fresh review before confirming.");
      return;
    }
    const timer = window.setTimeout(() => {
      setReview(null);
      setAllItemsAcknowledged(false);
      setPendingDecision(null);
      setError("The exact local requirement/action review receipt expired. Open a fresh review before confirming.");
    }, Math.min(expiresIn, 2_147_483_647));
    return () => window.clearTimeout(timer);
  }, [review]);

  useEffect(() => {
    if (preview === null) return;
    const expiresIn = Date.parse(preview.expires_at) - Date.now();
    const expire = () => {
      setPreview(null);
      setPayload(null);
      setError("The exact local file preview expired. Preview the unchanged canonical bytes again before import.");
    };
    if (expiresIn <= 0) {
      expire();
      return;
    }
    const timer = window.setTimeout(expire, Math.min(expiresIn, 2_147_483_647));
    return () => window.clearTimeout(timer);
  }, [preview]);

  useEffect(() => {
    setAllItemsAcknowledged(false);
    setPendingDecision(null);
  }, [reviewedMetadataBinding]);

  const undecided = useMemo(
    () => proposals.filter((proposal) => proposal.status === "proposed"),
    [proposals],
  );
  const localAgentMetaprompt = useMemo(() => [
    "Prompt Enhancer local requirement-action proposal workflow (no metric authority)",
    "",
    `1. GET /v1/sessions/${sessionId}/requirement-action-evidence/contract using this app's local authenticated API.`,
    "2. Treat requirements and candidate_manifest.actions as the only authoritative set. Build one canonical JSON file matching file_json_schema exactly and preserve every returned source, r6-plan, candidate-manifest, and predecessor binding.",
    "3. Include every requirement_index exactly once, densely and in order. For each link, choose only action_candidate_indexes already issued by the contract, sorted and unique, or use [] as an explicit empty link. Do not invent or infer another candidate.",
    "4. Treat every proposed membership as a hypothesis. The person must cross-check each source_reference_id against the referenced safe event/session timeline before adopting a semantic link; coarse content-free metadata is not proof of relation or task success.",
    "5. Do not include action state claims, objective proof claims, metric values, commentary/prose, source text, file paths, commands, tool arguments, or tool output. Producer identity is an untrusted preview claim and never metric authority.",
    `6. POST the bytes to /v1/sessions/${sessionId}/requirement-action-evidence/preview with Content-Type: ${REQUIREMENT_ACTION_MEDIA_TYPE}. Inspect the returned counts, digest, expiry, and exact bindings.`,
    `7. Only after the person explicitly chooses import, POST the identical bytes to /v1/sessions/${sessionId}/requirement-action-evidence/import with the vendor Content-Type, a fresh Idempotency-Key, X-Requirement-Action-Payload-SHA256 from preview, and X-Requirement-Action-Confirmation: ${REQUIREMENT_ACTION_IMPORT_CONFIRMATION}.`,
    "8. Stop after import. The proposal is inert. Never call review or decision endpoints on the person's behalf; only the app's owned native window may display every item and establish authority.",
  ].join("\n"), [sessionId]);

  function beginOperation(): { controller: AbortController; binding: string } {
    operationRef.current?.abort();
    const controller = new AbortController();
    operationRef.current = controller;
    return { controller, binding: bindingRef.current };
  }

  function stillCurrent(controller: AbortController, binding: string): boolean {
    return !controller.signal.aborted && bindingRef.current === binding;
  }

  function clearReview(): void {
    setReview(null);
    setAllItemsAcknowledged(false);
    setPendingDecision(null);
  }

  async function copyLocalAgentWorkflow(): Promise<void> {
    try {
      await navigator.clipboard.writeText(localAgentMetaprompt);
      setCopyStatus("Local-agent workflow copied. It grants proposal creation only, never metric authority.");
    } catch {
      setCopyStatus("Copy was unavailable. Select the workflow text manually.");
    }
  }

  async function chooseFile(file: File | undefined) {
    setPreview(null);
    setPayload(null);
    clearReview();
    setError("");
    if (file === undefined || contract === null || transport.previewRequirementActionEvidence === undefined) return;
    if (file.size < 1 || file.size > MAX_REQUIREMENT_ACTION_FILE_BYTES) {
      setError("Choose one canonical requirement-action file no larger than 64 KiB.");
      return;
    }
    const { controller, binding } = beginOperation();
    setBusy(true);
    try {
      const bytes = await file.arrayBuffer();
      if (!stillCurrent(controller, binding)) return;
      const result = await transport.previewRequirementActionEvidence(sessionId, bytes, controller.signal);
      if (!stillCurrent(controller, binding)) return;
      if (
        result.session_id !== contract.session_id
        || result.expected_source_run_id !== contract.expected_source_run_id
        || result.source_window_fingerprint !== contract.source_window_fingerprint
        || result.requirement_plan_confirmation_id !== contract.requirement_plan_confirmation_id
        || result.requirement_plan_evidence_fingerprint !== contract.requirement_plan_evidence_fingerprint
        || result.candidate_manifest_fingerprint !== contract.candidate_manifest.manifest_fingerprint
        || result.expected_predecessor_confirmation_id !== contract.expected_predecessor_confirmation_id
        || result.requirement_count !== contract.requirements.length
        || result.candidate_count !== contract.candidate_manifest.actions.length
        || Date.parse(result.expires_at) <= Date.now()
      ) {
        setError("The file preview is expired or bound to another sealed source, plan, candidate set, or predecessor.");
        return;
      }
      setPayload(bytes);
      setPreview(result);
    } catch {
      if (stillCurrent(controller, binding)) {
        setError("The file failed strict local validation; no proposal was imported.");
      }
    } finally {
      if (stillCurrent(controller, binding)) setBusy(false);
    }
  }

  async function importPreview() {
    if (
      preview === null || payload === null || contract === null
      || transport.importRequirementActionEvidence === undefined
    ) return;
    if (Date.parse(preview.expires_at) <= Date.now()) {
      setPreview(null);
      setPayload(null);
      setError("The exact local file preview expired. Preview the unchanged canonical bytes again before import.");
      return;
    }
    const { controller, binding } = beginOperation();
    setBusy(true);
    setError("");
    clearReview();
    try {
      const result = await transport.importRequirementActionEvidence(
        sessionId,
        payload,
        preview,
        REQUIREMENT_ACTION_IMPORT_CONFIRMATION,
        idempotency("requirement-action-import"),
        controller.signal,
      );
      if (!stillCurrent(controller, binding)) return;
      if (!proposalCurrent(result.proposal, contract) || result.proposal.status !== "proposed") {
        setError("The imported proposal did not preserve the exact preview authority.");
        return;
      }
      setProposals((current) => [
        result.proposal,
        ...current.filter((item) => item.proposal_id !== result.proposal.proposal_id),
      ]);
      setPreview(null);
      setPayload(null);
    } catch {
      if (stillCurrent(controller, binding)) {
        setError("The preview binding changed or the proposal could not be imported.");
      }
    } finally {
      if (stillCurrent(controller, binding)) setBusy(false);
    }
  }

  async function openReview(proposal: RequirementActionProposal) {
    if (
      contract === null || !confirmationAvailable
      || transport.reviewRequirementActionProposal === undefined
      || !proposalCurrent(proposal, contract)
    ) return;
    const { controller, binding } = beginOperation();
    setBusy(true);
    setError("");
    clearReview();
    try {
      const loaded = await transport.reviewRequirementActionProposal(
        sessionId,
        proposal,
        contract,
        {
          expected_source_run_id: sourceRunId,
          confirmation: REQUIREMENT_ACTION_REVIEW_CONFIRMATION,
        },
        controller.signal,
      );
      if (!stillCurrent(controller, binding)) return;
      if (!reviewCurrent(loaded, proposal, contract)) {
        setError("The complete local requirement/action review is stale or expired; nothing can be confirmed.");
        return;
      }
      setReview(loaded);
    } catch {
      if (stillCurrent(controller, binding)) {
        clearReview();
        setError("The exact local review could not be opened; refresh the sealed run before confirming.");
      }
    } finally {
      if (stillCurrent(controller, binding)) setBusy(false);
    }
  }

  async function applyDecision(proposal: RequirementActionProposal, decision: "confirm" | "reject") {
    if (transport.decideRequirementActionProposal === undefined || !confirmationAvailable) return;
    const currentReview = contract !== null && review !== null && reviewCurrent(review, proposal, contract)
      ? review
      : null;
    if (decision === "confirm" && (currentReview === null || !allItemsAcknowledged)) return;
    const request: RequirementActionDecisionRequest = decision === "confirm" ? {
      expected_source_run_id: proposal.source_run_id,
      decision: "confirm",
      confirmation: REQUIREMENT_ACTION_DECISION_CONFIRMATION,
      review_receipt_id: currentReview!.review_receipt_id,
      reviewed_graph_fingerprint: currentReview!.reviewed_graph_fingerprint,
      candidate_manifest_fingerprint: currentReview!.candidate_manifest_fingerprint,
      reviewed_candidate_set_fingerprint: currentReview!.reviewed_candidate_set_fingerprint,
      reviewed_descriptor_set_fingerprint: currentReview!.reviewed_descriptor_set_fingerprint,
      complete_review_acknowledged: true,
      all_requirements_and_candidates_acknowledged: true,
      all_linked_action_semantics_reviewed: true,
    } : {
      expected_source_run_id: proposal.source_run_id,
      decision: "reject",
      confirmation: REQUIREMENT_ACTION_DECISION_CONFIRMATION,
    };
    const { controller, binding } = beginOperation();
    setBusy(true);
    setError("");
    try {
      const result = await transport.decideRequirementActionProposal(
        sessionId,
        proposal.proposal_id,
        request,
        idempotency(`requirement-action-${decision}`),
        controller.signal,
      );
      if (!stillCurrent(controller, binding)) return;
      setProposals((current) => current.map((item) => (
        item.proposal_id === result.proposal.proposal_id ? result.proposal : item
      )));
      if (decision === "confirm") onEvidenceChanged?.();
    } catch {
      if (stillCurrent(controller, binding)) {
        setError(decision === "reject"
          ? "The native rejection could not be recorded. The stale proposal remains inert."
          : "The source, predecessor, candidate set, or one-shot review receipt changed; open a fresh review.");
      }
    } finally {
      if (stillCurrent(controller, binding)) {
        clearReview();
        setBusy(false);
      }
    }
  }

  if (compact) {
    return (
      <section aria-label="Reviewed requirement-to-action evidence" className="metric-evidence-file metric-evidence-file--compact">
        <strong>Requirement-to-action evidence</strong>
        <span>{capabilities && contract !== null
          ? bindingInvalid
            ? `${undecided.filter((proposal) => proposalCurrent(proposal, contract)).length} current recovery proposal${undecided.filter((proposal) => proposalCurrent(proposal, contract)).length === 1 ? "" : "s"} · prior binding invalid`
            : `${undecided.length} proposal${undecided.length === 1 ? "" : "s"} awaiting native decision`
          : "Exact r7 review unavailable"}</span>
        <small>{confirmationAvailable
          ? "Open the full dashboard to inspect every requirement, content-free action receipt, and proposed membership."
          : "Review is fail-closed: this runtime cannot natively review or decide proposals."}</small>
        {error !== "" && <span role="alert">{error}</span>}
      </section>
    );
  }

  return (
    <section aria-label="Review requirement-to-action evidence" className="metric-evidence-file">
      <header>
        <div>
          <strong>Reviewed requirement-to-action evidence</strong>
          <span>Canonical file → strict preview → inert proposal → complete local review → native decision</span>
        </div>
        <small>This review appears only when the selected provider and sealed window expose complete safe-event plus ephemeral redacted-descriptor authority. It does not imply Codex support or shipped metric operability. Import can propose memberships; it cannot author state, proof, prose, paths, or a metric value.</small>
      </header>
      {!capabilities ? (
        <p>This local runtime does not expose the complete r7 requirement-action boundary.</p>
      ) : contract === null ? (
        <p role={error === "" ? "status" : "alert"}>{error === ""
          ? "Loading the exact content-free r7 contract…"
          : error}</p>
      ) : (
        <>
          <p>Bound to sealed run <strong>{sourceRunId.slice(0, 8)}…</strong>, reviewed r6 requirements, and {contract.candidate_manifest.actions.length} application-issued safe action candidate{contract.candidate_manifest.actions.length === 1 ? "" : "s"}. Unknown is never rendered as zero.</p>
          {bindingInvalid && (
            <p role="status">The prior sealed r7 requirement-action binding is invalid, not merely awaiting review. An exact current replacement proposal may be reviewed and confirmed as the recovery path; non-current proposals remain stale and rejection-only.</p>
          )}
          <details>
            <summary>Local coding-agent file workflow</summary>
            <p>This metaprompt lets a local agent propose only requirement-to-candidate-index memberships. Preview and import remain local and import remains non-authoritative.</p>
            <textarea aria-label="Requirement-action local-agent metaprompt" readOnly rows={10} value={localAgentMetaprompt} />
            <button onClick={() => void copyLocalAgentWorkflow()} type="button">Copy local-agent workflow</button>
            {copyStatus !== "" && <small role="status">{copyStatus}</small>}
          </details>
          <label>
            <span>Choose canonical requirement-action evidence file</span>
            <input
              accept={`.json,${REQUIREMENT_ACTION_MEDIA_TYPE}`}
              disabled={busy}
              onChange={(event) => void chooseFile(event.currentTarget.files?.[0])}
              type="file"
            />
          </label>
          {preview !== null && (
            <div className="metric-evidence-file__preview" role="status">
              <span><strong>{preview.requirement_count} requirements</strong> · {preview.candidate_count} candidates · {preview.linked_requirement_count} linked · {preview.unlinked_requirement_count} explicit empty · {preview.link_count} memberships</span>
              <small>Producer {preview.producer.producer_id} / {preview.producer.model_id} is an ephemeral, untrusted preview claim. Only an opaque keyed receipt persists.</small>
              <button disabled={busy} onClick={() => void importPreview()} type="button">Import as unconfirmed</button>
            </div>
          )}
          {undecided.length === 0 ? (
            <p>No inert requirement-action proposals await a native decision.</p>
          ) : (
            <ul aria-label="Requirement-action proposals awaiting native decision">
              {undecided.map((proposal) => {
                const current = proposalCurrent(proposal, contract);
                const proposalReview = review?.proposal_id === proposal.proposal_id
                  && reviewCurrent(review, proposal, contract) ? review : null;
                return (
                  <li className="metric-evidence-file__review-proposal" key={proposal.proposal_id}>
                    <div>
                      <strong>Proposal {proposal.proposal_id.slice(0, 8)}…</strong>
                      <span>{proposalSummary(proposal)}</span>
                      <small>{current
                        ? "Exact current source, r6 predecessor, candidate manifest, and predecessor decision."
                        : bindingInvalid
                          ? "Stale proposal: it does not match the fresh recovery contract, so only native rejection is available."
                          : "Stale proposal: it cannot be confirmed, but native rejection remains available and does not require a fresh source window."}</small>
                    </div>
                    <div>
                      {current && (
                        <button disabled={busy || !confirmationAvailable} onClick={() => void openReview(proposal)} type="button">
                          Inspect every item
                        </button>
                      )}
                      <button
                        disabled={busy || !confirmationAvailable}
                        onClick={() => setPendingDecision({ proposalId: proposal.proposal_id, decision: "reject" })}
                        type="button"
                      >Reject</button>
                    </div>
                    {proposalReview !== null && (
                      <section
                        aria-label={`Complete review for proposal ${proposal.proposal_id}`}
                        className="metric-evidence-file__clause-review"
                      >
                        <header>
                          <strong>Complete local review</strong>
                          <small>Receipt {proposalReview.review_receipt_id.slice(0, 12)}… · graph {proposalReview.reviewed_graph_fingerprint.slice(0, 12)}… · candidate set {proposalReview.reviewed_candidate_set_fingerprint.slice(0, 12)}… · descriptor set {proposalReview.reviewed_descriptor_set_fingerprint.slice(0, 12)}…</small>
                        </header>
                        <p>Requirement and descriptor text below is the exact one-pass, injective visible form. Backslash escapes are literal review characters—not instructions to decode—and no displayed value is truncated.</p>
                        <h4>Every active requirement clause</h4>
                        <ol>
                          {proposalReview.requirements.map((requirement, requirementIndex) => (
                            <li key={requirement.requirement_id}>
                              <p><strong>Requirement #{requirementIndex} · message {requirement.coordinate.message_sequence}, clause {requirement.coordinate.clause_index}</strong> · <code className="metric-evidence-file__opaque-id">{requirement.requirement_id}</code> — <span className="metric-evidence-file__exact-review-text">{requirement.text}</span></p>
                              {requirement.linked_action_ids.length === 0
                                ? <small>Explicit empty link: reviewed negative only after this complete native review.</small>
                                : (
                                  <small className="metric-evidence-file__membership-list">
                                    <span>Proposed action memberships:</span>
                                    {requirement.linked_action_ids.map((id) => {
                                      const linkedCandidate = proposalReview.candidates.find((candidate) => candidate.action_id === id)!;
                                      return <span key={id}>candidate #{linkedCandidate.candidate_index} · <code className="metric-evidence-file__opaque-id">{id}</code></span>;
                                    })}
                                  </small>
                                )}
                            </li>
                          ))}
                        </ol>
                        <h4>Every action candidate and ephemeral redacted descriptor</h4>
                        <p>Cross-check each source receipt and its redacted invocation/effect against the safe event in the selected session timeline before accepting a membership. The coarse receipt, descriptor, and application-issued state are review aids—not proof of semantic relevance or task success. Descriptors stay local to this native review and are not persisted.</p>
                        <ol>
                          {proposalReview.candidate_memberships.map((membership) => {
                            const { candidate, linked_requirement_ids } = membership;
                            return (
                            <li key={candidate.action_id}>
                              <article>
                                <p><strong>Candidate #{candidate.candidate_index}</strong> · action <code className="metric-evidence-file__opaque-id">{candidate.action_id}</code> · {humanCode(candidate.event_kind)} · {candidate.tool_category === null ? "no tool category" : humanCode(candidate.tool_category)} · {humanCode(candidate.family)} · state {humanCode(candidate.state)}</p>
                                <small className="metric-evidence-file__membership-list"><span>source receipt <code className="metric-evidence-file__opaque-id">{candidate.source_reference_id}</code> · <time dateTime={candidate.occurred_at}>{candidate.occurred_at}</time> · {durationLabel(candidate.duration_ms)} · sequence {candidate.sequence}</span>{linked_requirement_ids.length === 0
                                  ? <span>no proposed requirement membership</span>
                                  : linked_requirement_ids.map((id) => {
                                    const requirementIndex = proposalReview.requirements.findIndex((requirement) => requirement.requirement_id === id);
                                    return <span key={id}>requirement #{requirementIndex} · <code className="metric-evidence-file__opaque-id">{id}</code></span>;
                                  })}</small>
                                <dl>
                                  <div><dt>Tool name</dt><dd><span className="metric-evidence-file__exact-review-text">{membership.tool_name}</span></dd></div>
                                  <div><dt>Invocation preview</dt><dd><blockquote className="metric-evidence-file__exact-review-text">{membership.invocation_preview}</blockquote></dd></div>
                                  <div><dt>Result or effect preview</dt><dd>{membership.result_or_effect_preview === null
                                    ? "No result/effect preview: this is a started action, not a completed outcome."
                                    : <blockquote className="metric-evidence-file__exact-review-text">{membership.result_or_effect_preview}</blockquote>}</dd></div>
                                  <div><dt>Candidate metadata receipt</dt><dd><span aria-label={`Full candidate metadata fingerprint ${membership.candidate_metadata_fingerprint}`} title={membership.candidate_metadata_fingerprint}>{membership.candidate_metadata_fingerprint.slice(0, 12)}…</span> · {membership.candidate_metadata_fingerprint_version}</dd></div>
                                  <div><dt>Descriptor receipt</dt><dd>{membership.descriptor_algorithm_version} · redactor {membership.redactor_version} · invocation complete · effect complete</dd></div>
                                </dl>
                              </article>
                            </li>
                            );
                          })}
                        </ol>
                        <label>
                          <input
                            checked={allItemsAcknowledged}
                            onChange={(event) => setAllItemsAcknowledged(event.currentTarget.checked)}
                            type="checkbox"
                          />
                          <span>I cross-checked and reviewed every displayed requirement, every action candidate, every ephemeral redacted invocation and effect, every proposed semantic membership, and every explicit empty link in this exact receipt.</span>
                        </label>
                        <button
                          disabled={busy || !allItemsAcknowledged}
                          onClick={() => setPendingDecision({ proposalId: proposal.proposal_id, decision: "confirm" })}
                          type="button"
                        >Confirm exact reviewed graph</button>
                      </section>
                    )}
                    {pendingDecision?.proposalId === proposal.proposal_id && (
                      <div
                        aria-label={`${pendingDecision.decision === "confirm" ? "Confirm" : "Reject"} requirement-action proposal`}
                        className="metric-evidence-file__decision-confirmation"
                        role="group"
                      >
                        <p>{pendingDecision.decision === "confirm"
                          ? "Apply this one-shot receipt and the exact graph, candidate-manifest, candidate-set, and reviewed-descriptor-set fingerprints as metric authority?"
                          : "Reject this inert proposal? Rejection is independent of current source or predecessor authority."}</p>
                        <div>
                          <button disabled={busy} onClick={() => setPendingDecision(null)} type="button">Cancel</button>
                          <button disabled={busy} onClick={() => void applyDecision(proposal, pendingDecision.decision)} type="button">
                            {pendingDecision.decision === "confirm" ? "Apply exact confirmation" : "Apply rejection"}
                          </button>
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {!confirmationAvailable && (
            <p role="status">Owned native user presence is unavailable. Files may be previewed and imported as inert proposals, but review and decisions are disabled.</p>
          )}
          {error !== "" && <p role="alert">{error}</p>}
        </>
      )}
    </section>
  );
}
