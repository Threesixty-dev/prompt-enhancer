import { useEffect, useId, useMemo, useRef, useState } from "react";
import type {
  ModelRequirementVerificationEvidenceBinding,
  ObservedCheckAuthorityProvenance,
  PromptEnhancerTransport,
  RequirementVerificationOpportunityReview,
  RequirementVerificationEvidenceSnapshot,
} from "../../shared/api/contracts";
import {
  parseRequirementVerificationEvidenceMutation,
  parseRequirementVerificationEvidenceSnapshot,
} from "../../shared/api/requirementVerificationEvidenceContract";
import { parseRequirementVerificationOpportunityReview } from "../../shared/api/requirementVerificationReviewContract";
import { ObservedCheckPayloadError, parseObservedCheckAuthorityProvenance } from "../../shared/api/observedCheckContract";
import { ObservedCheckEvidencePanel } from "./ObservedCheckEvidencePanel";
import "./RequirementVerificationEvidencePanel.css";

type VerificationTransport = Pick<PromptEnhancerTransport,
  | "issueCurrentRequirementVerificationOpportunities"
  | "getRequirementVerificationEvidenceSnapshot"
  | "reviewRequirementVerificationOpportunity"
  | "appendRequirementVerificationAcceptance"
  | "preflightRequirementVerificationObservedCheck"
  | "reviewRequirementVerificationObservedCheck"
  | "issueRequirementVerificationObservedCheck"
  | "getRequirementVerificationObservedCheckProvenance"
  | "getUserPresenceCapability">;

const HEX_64 = /^[0-9a-f]{64}$/;

type Owner = { identity: string; transport: VerificationTransport };

function sameOwner(left: Owner | null, right: Owner): boolean {
  return left !== null && left.identity === right.identity && left.transport === right.transport;
}

function abortOperation(controller: AbortController | null): void {
  if (controller !== null) controller.abort();
}

function bindingReady(binding: ModelRequirementVerificationEvidenceBinding): boolean {
  return (binding.evidence_source === "awaiting_evidence" || binding.evidence_source === "persisted_evidence")
    && binding.requirement_plan_confirmation_id !== null
    && binding.requirement_plan_proposal_id !== null
    && binding.requirement_plan_evidence_fingerprint !== null
    && binding.opportunity_count !== null
    && binding.opportunity_set_fingerprint !== null
    && HEX_64.test(binding.opportunity_set_fingerprint);
}

function snapshotMatches(
  value: unknown,
  binding: ModelRequirementVerificationEvidenceBinding,
  sessionId: string,
): boolean {
  try {
    parseRequirementVerificationEvidenceSnapshot(value, sessionId, binding);
  } catch {
    return false;
  }
  return bindingReady(binding);
}

function summary(snapshot: RequirementVerificationEvidenceSnapshot): string {
  const evidence = snapshot.evidence;
  const accepted = evidence.acceptance_authorities.length;
  const objective = evidence.verification_results.length;
  return `${evidence.opportunities.opportunities.length} requirements · ${objective} objective results · ${accepted} native acceptances · revision ${snapshot.revision}`;
}

type ObservedResult = RequirementVerificationEvidenceSnapshot["evidence"]["verification_results"][number];
type ProvenanceTransport = Pick<PromptEnhancerTransport, "getRequirementVerificationObservedCheckProvenance">;

function ObservedCheckProvenanceDetails({
  sessionId,
  sourceRunId,
  sourceWindowFingerprint,
  opportunitySetFingerprint,
  requirementPlanConfirmationId,
  requirementPlanProposalId,
  result,
  ownerIdentity,
  transport,
}: {
  sessionId: string;
  sourceRunId: string;
  sourceWindowFingerprint: string;
  opportunitySetFingerprint: string;
  requirementPlanConfirmationId: string;
  requirementPlanProposalId: string;
  result: ObservedResult;
  ownerIdentity: string;
  transport: ProvenanceTransport;
}) {
  const [open, setOpen] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "unavailable" | "error">("idle");
  const [provenance, setProvenance] = useState<ObservedCheckAuthorityProvenance | null>(null);
  const operation = useRef<AbortController | null>(null);
  const supportsProvenance = result.method === "test" && result.outcome !== "unknown";

  useEffect(() => {
    abortOperation(operation.current);
    operation.current = null;
    setOpen(false);
    setAttempt(0);
    setState("idle");
    setProvenance(null);
    return () => abortOperation(operation.current);
  }, [ownerIdentity, result.result_id, transport]);

  useEffect(() => {
    if (!supportsProvenance || !open || transport.getRequirementVerificationObservedCheckProvenance === undefined) return undefined;
    abortOperation(operation.current);
    const controller = new AbortController();
    operation.current = controller;
    setState("loading");
    setProvenance(null);
    const timeout = window.setTimeout(() => {
      if (operation.current === controller) {
        controller.abort();
        operation.current = null;
        setState("error");
      }
    }, 10_000);
    void transport.getRequirementVerificationObservedCheckProvenance(sessionId, result.result_id, controller.signal)
      .then((value) => {
        if (controller.signal.aborted || operation.current !== controller) return;
        const parsed = parseObservedCheckAuthorityProvenance(value, sessionId, result.result_id);
        const expectedOutcome = result.outcome === "passed" ? "passed" : result.outcome === "failed" ? "check_failed" : null;
        if (parsed.source_run_id !== sourceRunId
          || parsed.source_window_fingerprint !== sourceWindowFingerprint
          || parsed.opportunity_set_fingerprint !== opportunitySetFingerprint
          || parsed.requirement_plan_confirmation_id !== requirementPlanConfirmationId
          || parsed.requirement_plan_proposal_id !== requirementPlanProposalId
          || parsed.opportunity_id !== result.opportunity_id
          || parsed.requirement_id !== result.requirement_id
          || parsed.observed_sequence !== result.observed_sequence
          || result.method !== "test"
          || expectedOutcome === null
          || parsed.observed_outcome !== expectedOutcome
          || parsed.exit_code !== (expectedOutcome === "passed" ? 0 : 1)
          || !result.receipt_reference_ids.includes(parsed.source_reference_id)
          || !result.receipt_reference_ids.includes(parsed.coverage_review_reference_id)) throw new ObservedCheckPayloadError();
        setProvenance(parsed);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || operation.current !== controller) return;
        setState((error as { status?: number }).status === 404 ? "unavailable" : "error");
      })
      .finally(() => {
        window.clearTimeout(timeout);
        if (operation.current === controller) operation.current = null;
      });
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [attempt, opportunitySetFingerprint, open, requirementPlanConfirmationId, requirementPlanProposalId, result, sessionId, sourceRunId, sourceWindowFingerprint, supportsProvenance, transport]);

  return (
    !supportsProvenance
      ? <p role="status">Direct observed-check provenance is unavailable for this objective result; this is not a failed check.</p>
      : <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Observed-check provenance</summary>
      {transport.getRequirementVerificationObservedCheckProvenance === undefined && <p role="status">Observed-check provenance is unavailable in this client.</p>}
      {state === "idle" && transport.getRequirementVerificationObservedCheckProvenance !== undefined && <p role="status">Open this section to read the content-free provenance for this objective result.</p>}
      {state === "loading" && <p role="status" aria-busy="true">Loading observed-check provenance…</p>}
      {state === "unavailable" && <p role="status">Provenance is unavailable for this historical result; this is not a failed check.</p>}
      {state === "error" && <div role="alert"><p>Observed-check provenance could not be read. No check outcome was changed.</p><button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry provenance</button></div>}
      {provenance !== null && state === "ready" && (
        <dl>
          <div><dt>Provider-reported outcome</dt><dd>{provenance.observed_outcome === "passed" ? "passed" : "check failed"} (exit code {provenance.exit_code})</dd></div>
          <div><dt>Observed sequence</dt><dd>{provenance.observed_sequence}</dd></div>
          <div><dt>Source reference</dt><dd><code>{provenance.source_reference_id}</code></dd></div>
          <div><dt>Coverage review reference</dt><dd><code>{provenance.coverage_review_reference_id}</code></dd></div>
          <div><dt>Coverage review</dt><dd>Human full-criterion coverage acknowledged separately; this record does not itself claim task success.</dd></div>
          <div><dt>Definitions</dt><dd>Completion {provenance.source_completion_schema_version}; interpreter {provenance.outcome_interpreter_version}; classifier {provenance.classifier_version}; normalizer {provenance.normalizer_version}; review {provenance.coverage_review_version}.</dd></div>
        </dl>
      )}
        </details>
  );
}

/**
 * The only active objective-evidence acquisition and inspection surface.
 * It issues opportunities only after a person explicitly asks, and intentionally
 * contains no result or native-acceptance authoring controls.
 */
export function RequirementVerificationEvidencePanel({
  compact,
  sessionId,
  sourceRunId,
  binding: receivedBinding,
  transport,
  onEvidenceChanged,
}: {
  compact: boolean;
  sessionId: string;
  sourceRunId: string;
  binding: ModelRequirementVerificationEvidenceBinding;
  transport: VerificationTransport;
  /** Notifies current evidence changed; selected-run metrics and readiness remain immutable. */
  onEvidenceChanged?: () => void;
}) {
  const [snapshot, setSnapshot] = useState<{ owner: Owner; value: RequirementVerificationEvidenceSnapshot } | null>(null);
  const [currentSnapshot, setCurrentSnapshot] = useState<{ owner: Owner; value: RequirementVerificationEvidenceSnapshot } | null>(null);
  const [busyOwner, setBusyOwner] = useState<Owner | null>(null);
  const [error, setError] = useState<{ owner: Owner; message: string } | null>(null);
  const [retry, setRetry] = useState(0);
  const operation = useRef<AbortController | null>(null);
  const latestEvidenceChangedRef = useRef(onEvidenceChanged);
  latestEvidenceChangedRef.current = onEvidenceChanged;
  const reviewOperation = useRef<AbortController | null>(null);
  const acceptanceOperation = useRef<AbortController | null>(null);
  const [review, setReview] = useState<{ owner: Owner; value: RequirementVerificationOpportunityReview } | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [acceptanceBusy, setAcceptanceBusy] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [outcome, setOutcome] = useState<"accepted" | "rejected" | "unknown" | "">("");
  const [nativeAvailable, setNativeAvailable] = useState<boolean | null>(null);
  const [reviewError, setReviewError] = useState("");
  const [recordedReceipt, setRecordedReceipt] = useState<{ owner: Owner; message: string } | null>(null);
  const [reconciliationNeeded, setReconciliationNeeded] = useState<{
    owner: Owner;
    opportunityId: string;
    outcome: "accepted" | "rejected" | "unknown";
    throughRevision: number;
  } | null>(null);
  const bindingIdentity = JSON.stringify(receivedBinding);
  const binding = useMemo(() => receivedBinding, [bindingIdentity]);
  const identity = JSON.stringify([
    sessionId, sourceRunId, bindingIdentity,
  ]);
  const owner = useMemo<Owner>(() => ({ identity, transport }), [identity, transport]);
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const eligible = bindingReady(binding);
  const canIssue = eligible && binding.evidence_source === "awaiting_evidence"
    && transport.issueCurrentRequirementVerificationOpportunities !== undefined;
  const canInspect = eligible && binding.evidence_source === "persisted_evidence"
    && transport.getRequirementVerificationEvidenceSnapshot !== undefined;
  const busy = sameOwner(busyOwner, owner);
  const visibleSnapshot = snapshot !== null && sameOwner(snapshot.owner, owner) ? snapshot.value : null;
  const reviewBasis = currentSnapshot !== null && sameOwner(currentSnapshot.owner, owner) ? currentSnapshot.value : visibleSnapshot;
  const nativeReasonId = useId();
  const outcomeName = useId();
  const visibleError = error !== null && sameOwner(error.owner, owner) ? error.message : "";
  const visibleReview = review !== null && sameOwner(review.owner, owner) ? review.value : null;
  const nativeReason = nativeAvailable === false ? "Native confirmation is unavailable in this local session." : nativeAvailable === null ? "Checking native confirmation capability…" : "";

  // A parent notification is advisory. A throwing/rejecting observer must not turn a
  // validated native receipt into an apparently failed or unknown mutation.
  const notifyEvidenceChanged = () => {
    try {
      void Promise.resolve(latestEvidenceChangedRef.current?.()).catch(() => undefined);
    } catch {
      // Keep the validated receipt authoritative even if the parent refresh fails.
    }
  };

  useEffect(() => () => {
    abortOperation(operation.current);
    abortOperation(reviewOperation.current);
    abortOperation(acceptanceOperation.current);
  }, []);

  useEffect(() => {
    abortOperation(reviewOperation.current); abortOperation(acceptanceOperation.current);
    reviewOperation.current = null; acceptanceOperation.current = null;
    setReview(null); setCurrentSnapshot(null); setAcknowledged(false); setOutcome(""); setReviewError(""); setRecordedReceipt(null); setReconciliationNeeded(null); setReviewBusy(false); setAcceptanceBusy(false); setNativeAvailable(null);
    if (transport.getUserPresenceCapability === undefined) { setNativeAvailable(false); return undefined; }
    const controller = new AbortController();
    void transport.getUserPresenceCapability(controller.signal).then((capability) => {
      if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) setNativeAvailable(capability.confirmation_available === true && capability.mode === "native_bridge_bound_token");
    }).catch(() => { if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) setNativeAvailable(false); });
    return () => controller.abort();
  }, [owner, transport]);

  useEffect(() => {
    if (visibleReview === null) return undefined;
    const delay = Date.parse(visibleReview.review_expires_at) - Date.now();
    if (!Number.isFinite(delay) || delay <= 0) { closeReview(); setReviewError("The exact local review expired. Open it again before recording a human decision."); return undefined; }
    const timeout = window.setTimeout(() => { closeReview(); setReviewError("The exact local review expired. Open it again before recording a human decision."); }, delay);
    return () => window.clearTimeout(timeout);
  }, [visibleReview]);

  useEffect(() => {
    abortOperation(operation.current);
    operation.current = null;
    setBusyOwner(null);
    if (!canInspect || binding.opportunity_set_fingerprint === null || binding.through_revision === null) return undefined;
    const controller = new AbortController();
    operation.current = controller;
    setBusyOwner(owner);
    setSnapshot(null);
    setError(null);
    void Promise.resolve().then(() => {
      if (controller.signal.aborted || !sameOwner(ownerRef.current, owner)) return undefined;
      return transport.getRequirementVerificationEvidenceSnapshot!(
        sessionId, binding.opportunity_set_fingerprint!, binding.through_revision!, controller.signal,
      );
    }).then((next) => {
      if (next === undefined || controller.signal.aborted || !sameOwner(ownerRef.current, owner)) return;
      if (!snapshotMatches(next, binding, sessionId)) {
        setError({ owner, message: "The persisted evidence no longer matches this bound identity. Refresh analysis before inspecting it." });
        return;
      }
      setSnapshot({ owner, value: next });
      setCurrentSnapshot({ owner, value: next });
    }).catch(() => {
      if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) {
        setError({ owner, message: "Verification evidence could not be loaded. Retry reads only this exact persisted revision." });
      }
    }).finally(() => {
      if (operation.current === controller) operation.current = null;
      if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) setBusyOwner(null);
    });
    return () => controller.abort();
  }, [binding, canInspect, owner, retry, sessionId, transport]);

  const issue = () => {
    if (!canIssue || busy || operation.current !== null || transport.issueCurrentRequirementVerificationOpportunities === undefined) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusyOwner(owner);
    setSnapshot(null);
    setError(null);
    void Promise.resolve().then(() => {
      if (controller.signal.aborted || !sameOwner(ownerRef.current, owner)) return undefined;
      return transport.issueCurrentRequirementVerificationOpportunities!(sessionId, controller.signal);
    })
      .then((result) => {
        if (controller.signal.aborted || !sameOwner(ownerRef.current, owner)) return;
        try {
          const mutation = parseRequirementVerificationEvidenceMutation(result, sessionId, binding);
          setSnapshot({ owner, value: mutation.snapshot });
          setCurrentSnapshot({ owner, value: mutation.snapshot });
          // `applied: false` is an idempotent receipt, not evidence that the
          // current workspace is already fresh. Its validated snapshot can
          // still expose a mutation completed before this request.
          notifyEvidenceChanged();
        } catch {
          setError({ owner, message: "Current evidence differs from this snapshot. Refresh analysis to inspect current requirements." });
        }
      }).catch(() => {
        if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) {
          setError({ owner, message: "Verification opportunities could not be prepared. Prepare current reviewed requirements again after checking the current run." });
        }
      }).finally(() => {
      if (operation.current === controller) operation.current = null;
      if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) setBusyOwner(null);
      });
  };

  const closeReview = () => { abortOperation(reviewOperation.current); abortOperation(acceptanceOperation.current); reviewOperation.current = null; acceptanceOperation.current = null; setReview(null); setAcknowledged(false); setOutcome(""); setReviewBusy(false); setAcceptanceBusy(false); };
  const openReview = (opportunityId: string) => {
    if (reviewBasis === null || nativeAvailable !== true || reviewBusy || acceptanceBusy || reviewOperation.current !== null || transport.reviewRequirementVerificationOpportunity === undefined) return;
    const head = reviewBasis.authority_heads.find((item) => item.opportunity_id === opportunityId);
    const opportunity = reviewBasis.evidence.opportunities.opportunities.find((item) => item.opportunity_id === opportunityId);
    if (opportunity === undefined) return;
    closeReview();
    const controller = new AbortController(); reviewOperation.current = controller; setReviewBusy(true); setReviewError("");
    const set = reviewBasis.evidence.opportunities;
    void Promise.resolve().then(() => {
      if (controller.signal.aborted || !sameOwner(ownerRef.current, owner)) return undefined;
      return transport.reviewRequirementVerificationOpportunity!(sessionId, set.opportunity_set_fingerprint, opportunityId, { expected_source_run_id: sourceRunId, through_revision: reviewBasis.revision, expected_predecessor_authority_id: head?.authority_record_id ?? null, confirmation: "open_exact_local_requirement_verification_review" }, controller.signal);
    }).then((value) => {
      if (value === undefined) return;
      if (controller.signal.aborted || !sameOwner(ownerRef.current, owner)) return;
      const parsed = parseRequirementVerificationOpportunityReview(value, sessionId);
      if (parsed.expected_source_run_id !== sourceRunId || parsed.through_revision !== reviewBasis.revision || parsed.opportunity_set_fingerprint !== set.opportunity_set_fingerprint || parsed.opportunity_id !== opportunityId || parsed.requirement_id !== opportunity.requirement_id || parsed.source_window_fingerprint !== set.source_window_fingerprint || parsed.requirement_plan_confirmation_id !== set.requirement_plan_confirmation_id || parsed.requirement_plan_proposal_id !== set.requirement_plan_proposal_id || parsed.coordinate.message_sequence !== opportunity.coordinate.message_sequence || parsed.coordinate.clause_index !== opportunity.coordinate.clause_index || parsed.expected_predecessor_authority_id !== (head?.authority_record_id ?? null) || Date.parse(parsed.review_expires_at) <= Date.now()) throw new Error("stale");
      setReview({ owner, value: parsed });
    }).catch(() => { if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) setReviewError("The exact local requirement could not be opened. It may be stale; refresh the current evidence before trying again."); }).finally(() => { if (reviewOperation.current === controller) reviewOperation.current = null; if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) setReviewBusy(false); });
  };
  const accept = () => {
    if (visibleReview === null || !acknowledged || outcome === "" || nativeAvailable !== true || acceptanceBusy || acceptanceOperation.current !== null || transport.appendRequirementVerificationAcceptance === undefined) return;
    const controller = new AbortController(); acceptanceOperation.current = controller; setAcceptanceBusy(true); setReviewError("");
    const key = `rv-${visibleReview.review_receipt_id.slice(0, 48)}-${outcome}`;
    void Promise.resolve().then(() => {
      if (controller.signal.aborted || !sameOwner(ownerRef.current, owner)) return undefined;
      return transport.appendRequirementVerificationAcceptance!(sessionId, { opportunity_set_fingerprint: visibleReview.opportunity_set_fingerprint, opportunity_id: visibleReview.opportunity_id, expected_predecessor_authority_id: visibleReview.expected_predecessor_authority_id, outcome, confirmation: "record_explicit_native_requirement_acceptance", review_receipt_id: visibleReview.review_receipt_id, review_fingerprint: visibleReview.review_fingerprint, expected_source_run_id: visibleReview.expected_source_run_id, source_window_fingerprint: visibleReview.source_window_fingerprint }, key, controller.signal);
    }).then((result) => {
      if (result === undefined) return;
      if (controller.signal.aborted || !sameOwner(ownerRef.current, owner)) return;
      const mutation = parseRequirementVerificationEvidenceMutation(result, sessionId);
      const set = mutation.snapshot.evidence.opportunities;
      const acceptance = mutation.snapshot.evidence.acceptance_authorities.find((item) => item.opportunity_id === visibleReview.opportunity_id && item.outcome === outcome);
      const head = mutation.snapshot.authority_heads.find((item) => item.opportunity_id === visibleReview.opportunity_id);
      if (mutation.snapshot.revision !== visibleReview.through_revision + 1 || set.opportunity_set_fingerprint !== visibleReview.opportunity_set_fingerprint || set.source_window_fingerprint !== visibleReview.source_window_fingerprint || set.requirement_plan_confirmation_id !== visibleReview.requirement_plan_confirmation_id || set.requirement_plan_proposal_id !== visibleReview.requirement_plan_proposal_id || acceptance === undefined || acceptance.requirement_id !== visibleReview.requirement_id || head?.authority_record_id !== acceptance.acceptance_id || head.kind !== "native_acceptance" || head.revision !== mutation.snapshot.revision) throw new Error("invalid acceptance");
      setCurrentSnapshot({ owner, value: mutation.snapshot }); setRecordedReceipt({ owner, message: `Recorded current native human disposition: ${outcome}. The selected analysis snapshot remains unchanged.` }); closeReview(); notifyEvidenceChanged();
    }).catch(() => { if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) { setReconciliationNeeded({ owner, opportunityId: visibleReview.opportunity_id, outcome, throughRevision: visibleReview.through_revision }); setReviewError("The acceptance outcome is unconfirmed. Inspect current evidence before starting a fresh review."); } }).finally(() => { if (acceptanceOperation.current === controller) acceptanceOperation.current = null; if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) setAcceptanceBusy(false); });
  };
  const reconcileCurrent = () => {
    if (reviewBasis === null || transport.getRequirementVerificationEvidenceSnapshot === undefined || reviewBusy || acceptanceBusy || reviewOperation.current !== null || reconciliationNeeded === null || !sameOwner(reconciliationNeeded.owner, owner)) return;
    closeReview();
    const controller = new AbortController(); reviewOperation.current = controller; setReviewBusy(true);
    void Promise.resolve().then(() => {
      if (controller.signal.aborted || !sameOwner(ownerRef.current, owner)) return undefined;
      return transport.getRequirementVerificationEvidenceSnapshot!(sessionId, reviewBasis.evidence.opportunities.opportunity_set_fingerprint, undefined, controller.signal);
    }).then((value) => {
      if (value === undefined) return;
      if (controller.signal.aborted || !sameOwner(ownerRef.current, owner)) return;
      const next = parseRequirementVerificationEvidenceSnapshot(value, sessionId);
      const expected = reviewBasis.evidence.opportunities; const actual = next.evidence.opportunities;
      if (actual.opportunity_set_fingerprint !== expected.opportunity_set_fingerprint || actual.source_window_fingerprint !== expected.source_window_fingerprint || actual.requirement_plan_confirmation_id !== expected.requirement_plan_confirmation_id || actual.requirement_plan_proposal_id !== expected.requirement_plan_proposal_id || next.revision < reviewBasis.revision) throw new Error("stale");
      const acceptance = next.evidence.acceptance_authorities.find((item) => item.opportunity_id === reconciliationNeeded.opportunityId && item.outcome === reconciliationNeeded.outcome);
      const head = next.authority_heads.find((item) => item.opportunity_id === reconciliationNeeded.opportunityId);
      if (next.revision <= reconciliationNeeded.throughRevision) throw new Error("unconfirmed");
      const observedRequestedAcceptance = acceptance !== undefined && head?.authority_record_id === acceptance.acceptance_id && head.kind === "native_acceptance";
      setCurrentSnapshot({ owner, value: next });
      if (observedRequestedAcceptance) setRecordedReceipt({ owner, message: `Observed current native human disposition: ${reconciliationNeeded.outcome}. The selected analysis snapshot remains unchanged.` });
      setReconciliationNeeded(null);
      setReviewError(observedRequestedAcceptance ? "" : "Current evidence advanced, but it does not prove the requested human disposition was recorded.");
      notifyEvidenceChanged();
    }).catch(() => { if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) setReviewError("Current evidence could not be reconciled. No acceptance outcome is assumed."); }).finally(() => { if (reviewOperation.current === controller) reviewOperation.current = null; if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) setReviewBusy(false); });
  };

  return (
    <section className="requirement-verification-evidence" data-state={visibleError ? "error" : visibleSnapshot ? "ready" : binding.evidence_source}>
      <header>
        <div>
          <span>Objective evidence</span>
          <h4>Requirement verification evidence</h4>
        </div>
        <code>{sourceRunId.slice(0, 12)}</code>
      </header>
      <p>Prepare the current reviewed requirements for verification, or inspect existing app-issued evidence. Preparing a list is not a verified result.</p>
      {!eligible && <p role="status">The selected run has no bounded verification opportunity set to prepare or inspect.</p>}
      {canIssue && (
        <div className="requirement-verification-evidence__actions">
          <button disabled={busy} onClick={issue} type="button">{busy ? "Preparing current reviewed requirements…" : "Prepare current reviewed requirements"}</button>
          <small>Explicit request only. This creates the current opportunity set; it does not set a metric value.</small>
        </div>
      )}
      {binding.evidence_source === "awaiting_evidence" && !canIssue && eligible && <p role="status">Preparing verification evidence is unavailable in this client.</p>}
      {binding.evidence_source === "persisted_evidence" && !canInspect && eligible && <p role="status">Inspecting persisted verification evidence is unavailable in this client.</p>}
      {busy && canInspect && <p role="status">Loading the exact persisted evidence revision…</p>}
      {visibleError && <div className="requirement-verification-evidence__error" role="alert"><p>{visibleError}</p>{canInspect && <button disabled={busy} onClick={() => setRetry((value) => value + 1)} type="button">Retry exact read</button>}</div>}
      {visibleSnapshot !== null && (
        <div className="requirement-verification-evidence__details">
          <p>{summary(visibleSnapshot)}</p>
          {binding.evidence_source === "awaiting_evidence" && <p>Current evidence prepared; this analysis snapshot has not been changed.</p>}
          <div className="requirement-verification-evidence__requirements">
            <h5>Reviewed requirements</h5>
            <p>Open one exact local clause only when you are ready to review it. This does not run a model or mark it passed.</p>
            <ul>{visibleSnapshot.evidence.opportunities.opportunities.map((item) => <li key={item.opportunity_id}><span>Requirement {item.requirement_index + 1}</span> <button aria-describedby={nativeReason ? nativeReasonId : undefined} disabled={nativeAvailable !== true || reviewBusy || acceptanceBusy || transport.reviewRequirementVerificationOpportunity === undefined} onClick={() => openReview(item.opportunity_id)} type="button">Read exact requirement</button></li>)}</ul>
            {nativeReason && <p id={nativeReasonId} role="status">{nativeReason}</p>}
          </div>
          <ObservedCheckEvidencePanel
            binding={binding}
            nativeAvailable={nativeAvailable}
            onEvidenceChanged={(mutation, reconciledSnapshot, opportunityId) => {
              const nextSnapshot = mutation?.snapshot ?? reconciledSnapshot;
              if (nextSnapshot !== undefined) {
                setCurrentSnapshot({ owner, value: nextSnapshot });
                const observed = opportunityId === undefined
                  ? undefined
                  : nextSnapshot.evidence.verification_results.find((item) => item.opportunity_id === opportunityId);
                if (observed !== undefined) setRecordedReceipt({ owner, message: `Recorded server-issued observed test result: ${observed.outcome}. The selected analysis snapshot remains unchanged.` });
              }
              notifyEvidenceChanged();
            }}
            sessionId={sessionId}
            snapshot={reviewBasis ?? visibleSnapshot}
            sourceRunId={sourceRunId}
            transport={transport}
          />
          <details>
            <summary>Evidence identity and authority details</summary>
            <dl>
              <div><dt>Opportunity set</dt><dd><code>{visibleSnapshot.evidence.opportunities.opportunity_set_fingerprint}</code></dd></div>
              <div><dt>Bound source identity</dt><dd><code>{visibleSnapshot.evidence.opportunities.source_window_fingerprint}</code></dd></div>
              <div><dt>Authority heads</dt><dd>{visibleSnapshot.authority_heads.length}</dd></div>
              <div><dt>Resolved / met in this binding</dt><dd>{binding.resolved_opportunity_count ?? "unknown"} / {binding.met_requirement_count ?? "unknown"}</dd></div>
            </dl>
            <ul>
              {visibleSnapshot.authority_heads.map((item) => <li key={item.authority_record_id}><code>{item.opportunity_id}</code> · {item.kind} · revision {item.revision}</li>)}
            </ul>
            <h5>App-issued objective receipts</h5>
            <ul>
              {visibleSnapshot.evidence.verification_results.map((item) => <li key={item.result_id}>
                <div><code>{item.opportunity_id}</code> · objective {item.method}: {item.outcome}</div>
                <ObservedCheckProvenanceDetails
                  key={`${owner.identity}:${item.result_id}`}
                  opportunitySetFingerprint={visibleSnapshot.evidence.opportunities.opportunity_set_fingerprint}
                  ownerIdentity={owner.identity}
                  result={item}
                  requirementPlanConfirmationId={visibleSnapshot.evidence.opportunities.requirement_plan_confirmation_id}
                  requirementPlanProposalId={visibleSnapshot.evidence.opportunities.requirement_plan_proposal_id}
                  sessionId={sessionId}
                  sourceRunId={sourceRunId}
                  sourceWindowFingerprint={visibleSnapshot.evidence.opportunities.source_window_fingerprint}
                  transport={transport}
                />
              </li>)}
            </ul>
            {currentSnapshot !== null && sameOwner(currentSnapshot.owner, owner) && currentSnapshot.value.revision !== visibleSnapshot.revision && (() => {
              const historicalResultIds = new Set(visibleSnapshot.evidence.verification_results.map((item) => item.result_id));
              const currentResults = currentSnapshot.value.evidence.verification_results.filter((item) => !historicalResultIds.has(item.result_id));
              if (currentResults.length === 0) return null;
              return <>
                <h5>Current authority objective receipts</h5>
                <p role="status">These newly issued receipts belong to current authority evidence; the selected analysis above remains unchanged.</p>
                <ul>
                  {currentResults.map((item) => <li key={item.result_id}>
                    <div><code>{item.opportunity_id}</code> · objective {item.method}: {item.outcome}</div>
                    <ObservedCheckProvenanceDetails
                      key={`${owner.identity}:current:${item.result_id}`}
                      opportunitySetFingerprint={currentSnapshot.value.evidence.opportunities.opportunity_set_fingerprint}
                      ownerIdentity={`${owner.identity}:current:${currentSnapshot.value.revision}`}
                      requirementPlanConfirmationId={currentSnapshot.value.evidence.opportunities.requirement_plan_confirmation_id}
                      requirementPlanProposalId={currentSnapshot.value.evidence.opportunities.requirement_plan_proposal_id}
                      result={item}
                      sessionId={sessionId}
                      sourceRunId={sourceRunId}
                      sourceWindowFingerprint={currentSnapshot.value.evidence.opportunities.source_window_fingerprint}
                      transport={transport}
                    />
                  </li>)}
                </ul>
              </>;
            })()}
            <h5>Native acceptance authorities</h5>
            <ul>
              {visibleSnapshot.evidence.acceptance_authorities.map((item) => <li key={item.acceptance_id}><code>{item.opportunity_id}</code> · native acceptance: {item.outcome}</li>)}
            </ul>
          </details>
          {reconciliationNeeded !== null && sameOwner(reconciliationNeeded.owner, owner) && <div className="requirement-verification-evidence__error" role="alert"><p>{reviewError}</p><button disabled={reviewBusy || transport.getRequirementVerificationEvidenceSnapshot === undefined} onClick={reconcileCurrent} type="button">{reviewBusy ? "Inspecting current evidence…" : "Inspect current evidence"}</button></div>}
          {reviewError && (reconciliationNeeded === null || !sameOwner(reconciliationNeeded.owner, owner)) && <div className="requirement-verification-evidence__error" role="alert"><p>{reviewError}</p></div>}
          {recordedReceipt !== null && sameOwner(recordedReceipt.owner, owner) && <p role="status">{recordedReceipt.message}</p>}
          {currentSnapshot !== null && sameOwner(currentSnapshot.owner, owner) && currentSnapshot.value.revision !== visibleSnapshot.revision && <p role="status">Current authority evidence is revision {currentSnapshot.value.revision}; the selected analysis remains revision {visibleSnapshot.revision}.</p>}
          {visibleReview !== null && <div className="requirement-verification-evidence__review" aria-live="polite"><h5>Exact local requirement review</h5><p>Clause {visibleReview.coordinate.clause_index + 1}, message {visibleReview.coordinate.message_sequence}</p><pre>{visibleReview.requirement_text}</pre><label><input checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} type="checkbox" /> I have read this exact local requirement.</label><fieldset disabled={!acknowledged || acceptanceBusy || nativeAvailable !== true}><legend>Human disposition</legend>{(["accepted", "rejected", "unknown"] as const).map((value) => <label key={value}><input checked={outcome === value} name={outcomeName} onChange={() => setOutcome(value)} type="radio" value={value} /> {value}</label>)}</fieldset>{nativeReason && <p role="status">{nativeReason}</p>}<button aria-describedby={nativeReason ? nativeReasonId : undefined} disabled={!acknowledged || outcome === "" || nativeAvailable !== true || acceptanceBusy || transport.appendRequirementVerificationAcceptance === undefined} onClick={accept} type="button">{acceptanceBusy ? "Waiting for native confirmation…" : "Confirm human disposition"}</button>{transport.appendRequirementVerificationAcceptance === undefined && <p role="status">Recording a native human disposition is unavailable in this client.</p>}<button disabled={acceptanceBusy} onClick={closeReview} type="button">Cancel review</button></div>}
          <p className="requirement-verification-evidence__absence">A human acceptance is separate from an objective passed check and does not change this selected analysis run.</p>
        </div>
      )}
      {compact && <small>Inspection remains bound to this selected session, run, opportunity set, and revision.</small>}
    </section>
  );
}
