import { useEffect, useMemo, useRef, useState } from "react";
import type {
  PromptEnhancerTransport,
  RequirementPlanDecisionRequest,
  RequirementPlanEvidenceContract,
  RequirementPlanEvidencePreview,
  RequirementPlanProposal,
  RequirementPlanProposalReview,
  RequirementPlanReviewClause,
} from "../../shared/api/contracts";
import {
  MAX_REQUIREMENT_PLAN_FILE_BYTES,
  REQUIREMENT_PLAN_DECISION_CONFIRMATION,
  REQUIREMENT_PLAN_IMPORT_CONFIRMATION,
  REQUIREMENT_PLAN_MEDIA_TYPE,
} from "../../shared/api/requirementPlanEvidenceContract";
import "./MetricEvidenceFilePanel.css";

type RequirementPlanTransport = Pick<PromptEnhancerTransport,
  | "getRequirementPlanEvidenceContract"
  | "previewRequirementPlanEvidence"
  | "importRequirementPlanEvidence"
  | "listRequirementPlanProposals"
  | "reviewRequirementPlanProposal"
  | "decideRequirementPlanProposal">
  & Partial<Pick<PromptEnhancerTransport, "getUserPresenceCapability">>;

type PendingDecision = { proposalId: string; decision: "confirm" | "reject" };

function idempotency(prefix: string): string {
  return `${prefix}-${crypto.randomUUID().replaceAll("-", "")}`;
}

function exactBinding(
  contract: RequirementPlanEvidenceContract,
  sessionId: string,
  sourceRunId: string,
  sourceProjectionVersion: RequirementPlanEvidenceContract["source_projection_version"],
): boolean {
  return contract.session_id === sessionId
    && contract.expected_source_run_id === sourceRunId
    && contract.source_projection_version === sourceProjectionVersion;
}

function contractReviewCurrent(contract: RequirementPlanEvidenceContract): boolean {
  return Date.parse(contract.source_manifest.review_context_expires_at) > Date.now();
}

function coordinateKey(value: { message_sequence: number; clause_index: number }): string {
  return `${value.message_sequence}:${value.clause_index}`;
}

function coordinateLabel(value: { message_sequence: number; clause_index: number }): string {
  return `message ${value.message_sequence}, clause ${value.clause_index}`;
}

function proposalSummary(proposal: RequirementPlanProposal): string {
  const linked = proposal.requirements.filter((item) => item.disposition === "linked").length;
  const notLinked = proposal.requirements.filter((item) => item.disposition === "not_linked").length;
  const pending = proposal.requirements.filter((item) => item.disposition === "pending").length;
  return `${proposal.requirements.length} active requirements · ${proposal.excluded_user_clauses.length} excluded user clauses · ${linked} linked · ${notLinked} not linked · ${pending} pending · ${proposal.plan_items.length} included plan clauses`;
}

function receiptCurrent(review: RequirementPlanProposalReview, proposal: RequirementPlanProposal): boolean {
  const expiry = Math.min(
    Date.parse(review.review_context_expires_at),
    Date.parse(review.review_receipt_expires_at),
  );
  return review.proposal_id === proposal.proposal_id
    && review.session_id === proposal.session_id
    && review.source_run_id === proposal.source_run_id
    && review.source_window_fingerprint === proposal.source_window_fingerprint
    && review.payload_sha256 === proposal.payload_sha256
    && expiry > Date.now();
}

function reasonLabel(reason: NonNullable<RequirementPlanReviewClause["exclusion_reason"]>): string {
  return reason.replaceAll("_", " ");
}

export function RequirementPlanEvidencePanel({
  compact,
  sessionId,
  sourceRunId,
  sourceProjectionVersion,
  transport,
  onEvidenceChanged,
}: {
  compact: boolean;
  sessionId: string;
  sourceRunId: string;
  sourceProjectionVersion: RequirementPlanEvidenceContract["source_projection_version"];
  transport: RequirementPlanTransport;
  onEvidenceChanged?: () => void;
}) {
  const [contract, setContract] = useState<RequirementPlanEvidenceContract | null>(null);
  const [proposals, setProposals] = useState<RequirementPlanProposal[]>([]);
  const [preview, setPreview] = useState<RequirementPlanEvidencePreview | null>(null);
  const [payload, setPayload] = useState<ArrayBuffer | null>(null);
  const [confirmationAvailable, setConfirmationAvailable] = useState(false);
  const [pendingDecision, setPendingDecision] = useState<PendingDecision | null>(null);
  const [review, setReview] = useState<RequirementPlanProposalReview | null>(null);
  const [reviewAcknowledged, setReviewAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const operationRef = useRef<AbortController | null>(null);
  const bindingRef = useRef(`${sessionId}:${sourceRunId}:${sourceProjectionVersion}`);
  bindingRef.current = `${sessionId}:${sourceRunId}:${sourceProjectionVersion}`;

  const capabilities = transport.getRequirementPlanEvidenceContract !== undefined
    && transport.previewRequirementPlanEvidence !== undefined
    && transport.importRequirementPlanEvidence !== undefined
    && transport.listRequirementPlanProposals !== undefined
    && transport.reviewRequirementPlanProposal !== undefined
    && transport.decideRequirementPlanProposal !== undefined;

  useEffect(() => {
    operationRef.current?.abort();
    setContract(null);
    setProposals([]);
    setPreview(null);
    setPayload(null);
    setPendingDecision(null);
    setReview(null);
    setReviewAcknowledged(false);
    setConfirmationAvailable(false);
    setBusy(false);
    setError("");
    if (!capabilities) return;
    const controller = new AbortController();
    operationRef.current = controller;
    const binding = `${sessionId}:${sourceRunId}:${sourceProjectionVersion}`;
    Promise.all([
      transport.getRequirementPlanEvidenceContract!(sessionId, controller.signal),
      transport.listRequirementPlanProposals!(sessionId, controller.signal),
      transport.getUserPresenceCapability === undefined
        ? Promise.resolve(null)
        : transport.getUserPresenceCapability(controller.signal),
    ]).then(([loadedContract, collection, presence]) => {
      if (controller.signal.aborted || bindingRef.current !== binding) return;
      if (
        !exactBinding(loadedContract, sessionId, sourceRunId, sourceProjectionVersion)
        || !contractReviewCurrent(loadedContract)
      ) {
        setError("Requirement-plan review is not bound to a current exact sealed r5/r6/r7 source window.");
        return;
      }
      setContract(loadedContract);
      setProposals(collection.proposals.filter((proposal) => (
        proposal.session_id === sessionId
        && proposal.source_run_id === sourceRunId
        && proposal.source_window_fingerprint === loadedContract.source_window_fingerprint
      )));
      setConfirmationAvailable(presence?.confirmation_available === true);
    }).catch(() => {
      if (!controller.signal.aborted && bindingRef.current === binding) {
        setError("Reviewed requirement-plan evidence is temporarily unavailable.");
      }
    });
    return () => controller.abort();
  }, [capabilities, sessionId, sourceProjectionVersion, sourceRunId, transport]);

  useEffect(() => {
    if (review === null) return;
    const expiresIn = Math.min(
      Date.parse(review.review_context_expires_at),
      Date.parse(review.review_receipt_expires_at),
    ) - Date.now();
    if (expiresIn <= 0) {
      setReview(null);
      setReviewAcknowledged(false);
      setPendingDecision(null);
      setError("The exact local clause-review receipt expired. Open a fresh review before confirming.");
      return;
    }
    const timer = window.setTimeout(() => {
      setReview(null);
      setReviewAcknowledged(false);
      setPendingDecision(null);
      setError("The exact local clause-review receipt expired. Open a fresh review before confirming.");
    }, Math.min(expiresIn, 2_147_483_647));
    return () => window.clearTimeout(timer);
  }, [review]);

  const undecided = useMemo(
    () => proposals.filter((proposal) => proposal.status === "proposed"),
    [proposals],
  );

  function beginOperation(): { controller: AbortController; binding: string } {
    operationRef.current?.abort();
    const controller = new AbortController();
    operationRef.current = controller;
    return { controller, binding: `${sessionId}:${sourceRunId}:${sourceProjectionVersion}` };
  }

  function stillCurrent(controller: AbortController, binding: string): boolean {
    return !controller.signal.aborted && bindingRef.current === binding;
  }

  function clearReview(): void {
    setReview(null);
    setReviewAcknowledged(false);
    setPendingDecision(null);
  }

  async function chooseFile(file: File | undefined) {
    setPreview(null);
    setPayload(null);
    clearReview();
    setError("");
    if (file === undefined || contract === null || transport.previewRequirementPlanEvidence === undefined) return;
    if (!contractReviewCurrent(contract)) {
      setError("The exact local source review window expired; refresh before selecting a file.");
      return;
    }
    if (file.size < 1 || file.size > MAX_REQUIREMENT_PLAN_FILE_BYTES) {
      setError("Choose one canonical requirement-plan file no larger than 64 KiB.");
      return;
    }
    const { controller, binding } = beginOperation();
    setBusy(true);
    try {
      const bytes = await file.arrayBuffer();
      if (!stillCurrent(controller, binding)) return;
      const result = await transport.previewRequirementPlanEvidence(sessionId, bytes, controller.signal);
      if (!stillCurrent(controller, binding)) return;
      if (
        result.session_id !== contract.session_id
        || result.expected_source_run_id !== contract.expected_source_run_id
        || result.source_window_fingerprint !== contract.source_window_fingerprint
        || result.expected_predecessor_confirmation_id !== contract.expected_predecessor_confirmation_id
        || Date.parse(result.expires_at) <= Date.now()
      ) {
        setError("The file preview is stale or bound to another sealed source window.");
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
      || transport.importRequirementPlanEvidence === undefined
    ) return;
    const { controller, binding } = beginOperation();
    setBusy(true);
    setError("");
    clearReview();
    try {
      const result = await transport.importRequirementPlanEvidence(
        sessionId,
        payload,
        preview,
        REQUIREMENT_PLAN_IMPORT_CONFIRMATION,
        idempotency("requirement-plan-import"),
        controller.signal,
      );
      if (!stillCurrent(controller, binding)) return;
      const proposal = result.proposal;
      if (
        proposal.source_run_id !== sourceRunId
        || proposal.source_window_fingerprint !== contract.source_window_fingerprint
        || proposal.expected_predecessor_confirmation_id
          !== contract.expected_predecessor_confirmation_id
        || proposal.status !== "proposed"
      ) {
        setError("The imported proposal did not preserve the exact preview binding.");
        return;
      }
      setProposals((current) => [
        proposal,
        ...current.filter((item) => item.proposal_id !== proposal.proposal_id),
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

  async function openReview(proposal: RequirementPlanProposal) {
    if (
      contract === null || !confirmationAvailable
      || !contractReviewCurrent(contract)
      || transport.reviewRequirementPlanProposal === undefined
      || proposal.session_id !== sessionId || proposal.source_run_id !== sourceRunId
      || proposal.source_window_fingerprint !== contract.source_window_fingerprint
      || proposal.expected_predecessor_confirmation_id
        !== contract.expected_predecessor_confirmation_id
    ) return;
    const { controller, binding } = beginOperation();
    setBusy(true);
    setError("");
    clearReview();
    try {
      const loaded = await transport.reviewRequirementPlanProposal(
        sessionId,
        proposal,
        contract,
        {
          expected_source_run_id: sourceRunId,
          confirmation: "open_exact_local_requirement_plan_clause_review",
        },
        controller.signal,
      );
      if (!stillCurrent(controller, binding)) return;
      if (!receiptCurrent(loaded, proposal)) {
        setError("The exact local clause review is stale or expired; nothing can be confirmed.");
        return;
      }
      setReview(loaded);
    } catch {
      if (stillCurrent(controller, binding)) {
        clearReview();
        setError("The exact local clause review could not be opened; refresh the sealed run before confirming.");
      }
    } finally {
      if (stillCurrent(controller, binding)) setBusy(false);
    }
  }

  async function applyDecision(proposal: RequirementPlanProposal, decision: "confirm" | "reject") {
    const currentReview = review !== null && receiptCurrent(review, proposal) ? review : null;
    if (
      transport.decideRequirementPlanProposal === undefined
      || !confirmationAvailable
      || proposal.source_run_id !== sourceRunId
      || contract === null
      || proposal.source_window_fingerprint !== contract.source_window_fingerprint
      || (decision === "confirm" && proposal.expected_predecessor_confirmation_id
        !== contract.expected_predecessor_confirmation_id)
      || (decision === "confirm" && (currentReview === null || !reviewAcknowledged))
    ) return;
    const request: RequirementPlanDecisionRequest = decision === "confirm" ? {
      expected_source_run_id: sourceRunId,
      decision: "confirm",
      confirmation: REQUIREMENT_PLAN_DECISION_CONFIRMATION,
      review_receipt_id: currentReview!.review_receipt_id,
      manifest_fingerprint: currentReview!.manifest_fingerprint,
      reviewed_graph_fingerprint: currentReview!.reviewed_graph_fingerprint,
      reviewed_candidate_set_fingerprint: currentReview!.reviewed_candidate_set_fingerprint,
      complete_review_acknowledged: true,
    } : {
      expected_source_run_id: sourceRunId,
      decision: "reject",
      confirmation: REQUIREMENT_PLAN_DECISION_CONFIRMATION,
    };
    const { controller, binding } = beginOperation();
    setBusy(true);
    setError("");
    try {
      const result = await transport.decideRequirementPlanProposal(
        sessionId,
        proposal.proposal_id,
        request,
        idempotency(`requirement-plan-${decision}`),
        controller.signal,
      );
      if (!stillCurrent(controller, binding)) return;
      setProposals((current) => current.map((item) => (
        item.proposal_id === result.proposal.proposal_id ? result.proposal : item
      )));
      if (decision === "confirm") onEvidenceChanged?.();
    } catch {
      if (stillCurrent(controller, binding)) {
        setError("The source window, review receipt, or native decision authority changed; open a fresh review before deciding.");
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
      <section aria-label="Reviewed requirement-to-plan evidence" className="metric-evidence-file metric-evidence-file--compact">
        <strong>Requirement-to-plan evidence</strong>
        <span>{capabilities && contract !== null
          ? `${undecided.length} proposal${undecided.length === 1 ? "" : "s"} awaiting review`
          : "Exact r5/r6/r7 review unavailable"}</span>
        <small>{confirmationAvailable
          ? "Open the full dashboard to inspect every local source clause and natively confirm or reject its proposal."
          : "Review is fail-closed: this server/window composition cannot natively review or confirm proposals."}</small>
        {error !== "" && <span role="alert">{error}</span>}
      </section>
    );
  }

  return (
    <section aria-label="Review requirement-to-plan evidence" className="metric-evidence-file">
      <header>
        <div>
          <strong>Reviewed requirement-to-plan evidence</strong>
          <span>Canonical file → strict preview → unconfirmed proposal → exact local clause review → native decision</span>
        </div>
        <small>Coordinates, classifications, dispositions, exclusion evidence, opaque producer commitment, and bindings persist. Clause text appears only in the expiring local review and is never persisted.</small>
      </header>
      {!capabilities ? (
        <p>This local runtime does not expose the complete reviewed requirement-plan boundary.</p>
      ) : contract === null ? (
        <p role={error === "" ? "status" : "alert"}>{error === ""
          ? "Loading the exact content-free r5/r6/r7 contract…"
          : error}</p>
      ) : (
        <>
          <p>Bound to sealed run <strong>{sourceRunId.slice(0, 8)}…</strong>. Import alone can never set a metric value; only active requirement clauses enter the denominator after exact native review and a fresh analysis for this selected projection.</p>
          <p>Every reviewable user request/feedback clause must be classified as active or excluded. A compound active clause remains one opportunity and may coarsen multiple requirements; excluded clauses never enter the metric.</p>
          <label>
            <span>Choose canonical requirement-plan evidence file</span>
            <input
              accept={`.json,${REQUIREMENT_PLAN_MEDIA_TYPE}`}
              disabled={busy}
              onChange={(event) => void chooseFile(event.currentTarget.files?.[0])}
              type="file"
            />
          </label>
          {preview !== null && (
            <div className="metric-evidence-file__preview" role="status">
              <span><strong>{preview.active_requirement_count} proposed active requirements</strong> · {preview.excluded_user_clause_count} proposed exclusions · {preview.reviewed_user_clause_count} reviewed user clauses · {preview.plan_item_count} included plan clauses · {preview.link_count} links</span>
              <small>{preview.linked_active_requirement_count} linked · {preview.not_linked_active_requirement_count} not linked · {preview.pending_active_requirement_count} pending. Producer {preview.producer.producer_id} / {preview.producer.model_id} is ephemeral, untrusted provenance; only an opaque commitment persists.</small>
              <button disabled={busy} onClick={() => void importPreview()} type="button">Import as unconfirmed</button>
            </div>
          )}
          {undecided.length > 0 && (
            <ul aria-label="Requirement-plan proposals awaiting native decision">
              {undecided.map((proposal) => {
                const currentPredecessor = proposal.expected_predecessor_confirmation_id
                  === contract.expected_predecessor_confirmation_id;
                const proposalReview = review?.proposal_id === proposal.proposal_id && receiptCurrent(review, proposal)
                  ? review
                  : null;
                const clausesByCoordinate = new Map(
                  proposalReview?.candidate_clauses.map((clause) => [coordinateKey(clause), clause]) ?? [],
                );
                return (
                  <li className="metric-evidence-file__review-proposal" key={proposal.proposal_id}>
                    <span>
                      <strong>Content-free proposal {proposal.proposal_id.slice(0, 8)}…</strong>
                      <small>{proposalSummary(proposal)}</small>
                      <small>Producer provenance is stored only as opaque commitment {proposal.producer_receipt.claim_fingerprint.slice(0, 8)}…; no raw producer labels persist.</small>
                      {!currentPredecessor && <small>This proposal targets an older confirmation head. It cannot be reviewed or confirmed; native rejection remains available.</small>}
                    </span>
                    <div>
                      <button disabled={busy || !confirmationAvailable} onClick={() => setPendingDecision({ proposalId: proposal.proposal_id, decision: "reject" })} type="button">Reject</button>
                      <button disabled={busy || !confirmationAvailable || !currentPredecessor} onClick={() => void openReview(proposal)} type="button">Open exact local clause review</button>
                    </div>
                    {proposalReview !== null && (
                      <section aria-label={`Exact clause review for proposal ${proposal.proposal_id.slice(0, 8)}`} className="metric-evidence-file__clause-review">
                        <p><strong>Every eligible source clause is shown below.</strong> User clauses show their active/excluded classification; agent PLAN clauses show whether the proposal included or omitted them.</p>
                        <ol>
                          {proposalReview.candidate_clauses.map((clause) => {
                            const key = coordinateKey(clause);
                            const basis = clause.basis_coordinate === null
                              ? null
                              : clausesByCoordinate.get(coordinateKey(clause.basis_coordinate));
                            return (
                              <li key={key}>
                                <article>
                                  <strong>{clause.candidate_kind === "plan" ? "Agent PLAN clause" : "User request/feedback clause"} — {coordinateLabel(clause)}</strong>
                                  <blockquote>{clause.text}</blockquote>
                                  {clause.candidate_kind === "plan" ? (
                                    <p>Proposal membership: <strong>{clause.included_in_proposal ? "included plan clause" : "omitted plan clause"}</strong>.</p>
                                  ) : clause.classification === "active_requirement" ? (
                                    <dl>
                                      <div><dt>Classification</dt><dd>active requirement — included in the denominator</dd></div>
                                      <div><dt>Disposition</dt><dd>{clause.disposition?.replaceAll("_", " ")}</dd></div>
                                      <div><dt>Plan links</dt><dd>{clause.linked_plan_coordinates.length === 0 ? "none" : clause.linked_plan_coordinates.map(coordinateLabel).join("; ")}</dd></div>
                                    </dl>
                                  ) : (
                                    <dl>
                                      <div><dt>Classification</dt><dd>excluded from active-requirement denominator</dd></div>
                                      <div><dt>Exclusion reason</dt><dd>{reasonLabel(clause.exclusion_reason!)}</dd></div>
                                      <div><dt>Basis source clause</dt><dd>{clause.basis_coordinate === null
                                        ? "none — this reason does not use a basis coordinate"
                                        : <>{coordinateLabel(clause.basis_coordinate)} — “{basis?.text}”</>}</dd></div>
                                    </dl>
                                  )}
                                </article>
                              </li>
                            );
                          })}
                        </ol>
                        <p>One-shot receipt expires <time dateTime={proposalReview.review_receipt_expires_at}>{proposalReview.review_receipt_expires_at}</time>. Refreshing, changing runs/proposals, errors, or expiry clears this review and its acknowledgement.</p>
                        <label>
                          <input checked={reviewAcknowledged} disabled={busy} onChange={(event) => setReviewAcknowledged(event.currentTarget.checked)} type="checkbox" />
                          <span>I reviewed every displayed user and PLAN clause, every active disposition and link, every exclusion reason and basis source clause, and every included or omitted plan candidate for this exact receipt.</span>
                        </label>
                        <button disabled={busy || !confirmationAvailable || !reviewAcknowledged} onClick={() => setPendingDecision({ proposalId: proposal.proposal_id, decision: "confirm" })} type="button">Confirm evidence</button>
                      </section>
                    )}
                    {pendingDecision?.proposalId === proposal.proposal_id && (
                      <div aria-label={`${pendingDecision.decision === "confirm" ? "Confirm" : "Reject"} requirement-plan proposal`} className="metric-evidence-file__decision-confirmation" role="group">
                        <p>{pendingDecision.decision === "confirm"
                          ? "Native confirmation consumes this exact one-shot review receipt. It makes only the reviewed active-requirement classification and dispositions eligible for a fresh sealed analysis of this selected projection; it does not prove plan quality or atomic requirement coverage."
                          : "Native rejection permanently excludes this proposal from metric authority."}</p>
                        <div>
                          <button disabled={busy} onClick={() => setPendingDecision(null)} type="button">Cancel</button>
                          <button disabled={busy || !confirmationAvailable || (pendingDecision.decision === "confirm" && (proposalReview === null || !reviewAcknowledged))} onClick={() => void applyDecision(proposal, pendingDecision.decision)} type="button">{pendingDecision.decision === "confirm" ? "Apply native confirmation" : "Apply native rejection"}</button>
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {!confirmationAvailable && undecided.length > 0 && (
            <p role="status">Native user-presence review is unavailable. Proposals remain unconfirmed and cannot affect the metric.</p>
          )}
          {error !== "" && <p className="metric-evidence-file__error" role="alert">{error}</p>}
          <p>After confirmation, run a fresh local analysis and verify that its sealed requirement-plan binding names the confirmed proposal.</p>
        </>
      )}
    </section>
  );
}
