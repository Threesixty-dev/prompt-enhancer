import { useEffect, useId, useMemo, useRef, useState } from "react";
import type {
  ModelRequirementVerificationEvidenceBinding,
  ObservedCheckCandidateManifest,
  ObservedCheckCriterionReview,
  PromptEnhancerTransport,
  RequirementVerificationEvidenceMutation,
  RequirementVerificationEvidenceSnapshot,
} from "../../shared/api/contracts";
import { parseRequirementVerificationEvidenceMutation } from "../../shared/api/requirementVerificationEvidenceContract";
import { parseRequirementVerificationEvidenceSnapshot } from "../../shared/api/requirementVerificationEvidenceContract";
import {
  parseObservedCheckCandidateManifest,
  parseObservedCheckCriterionReview,
} from "../../shared/api/observedCheckContract";
import "./ObservedCheckEvidencePanel.css";

type ObservedCheckTransport = Pick<PromptEnhancerTransport,
  | "preflightRequirementVerificationObservedCheck"
  | "reviewRequirementVerificationObservedCheck"
  | "issueRequirementVerificationObservedCheck"
  | "getRequirementVerificationEvidenceSnapshot"
>;

type Owner = { identity: string; transport: ObservedCheckTransport };
type ReconciliationSelection = {
  owner: Owner;
  opportunityId: string;
  candidateId: string;
  candidateSequence: number;
  candidateOutcome: "passed" | "check_failed";
  throughRevision: number;
};

function sameOwner(left: Owner | null, right: Owner): boolean {
  return left !== null && left.identity === right.identity && left.transport === right.transport;
}

function abort(controller: AbortController | null): void {
  controller?.abort();
}

function parseIssuedMutation(
  value: unknown,
  sessionId: string,
  opportunitySetFingerprint: string,
  sourceWindowFingerprint: string,
  opportunityId: string,
  candidateId: string,
  candidateSequence: number,
  candidateOutcome: "passed" | "check_failed",
  expectedThroughRevision: number,
): RequirementVerificationEvidenceMutation {
  const mutation = parseRequirementVerificationEvidenceMutation(value, sessionId);
  const set = mutation.snapshot.evidence.opportunities;
  const result = mutation.snapshot.evidence.verification_results.find((item) => item.opportunity_id === opportunityId);
  const head = mutation.snapshot.authority_heads.find((item) => item.opportunity_id === opportunityId);
  const expectedOutcome = candidateOutcome === "passed" ? "passed" : "failed";
  if (set.opportunity_set_fingerprint !== opportunitySetFingerprint
    || set.source_window_fingerprint !== sourceWindowFingerprint
    || result === undefined
    || !result.receipt_reference_ids.includes(candidateId)
    || result.method !== "test"
    || result.observed_sequence !== candidateSequence
    || result.outcome !== expectedOutcome
    || head?.kind !== "objective_result"
    || head.authority_record_id !== result.result_id
    || head.revision <= expectedThroughRevision
    || head.revision > mutation.snapshot.revision
    || mutation.snapshot.revision <= expectedThroughRevision) {
    throw new Error("Observed result authority did not match the selected opportunity.");
  }
  return mutation;
}

/**
 * Read-only provider outcome and explicit native full-criterion review. The
 * provider reports the observed test result; only the local person can attest
 * that the exact check covered the complete requirement criterion.
 */
export function ObservedCheckEvidencePanel({
  sessionId,
  sourceRunId,
  snapshot,
  binding,
  transport,
  nativeAvailable,
  onEvidenceChanged,
}: {
  sessionId: string;
  sourceRunId: string;
  snapshot: RequirementVerificationEvidenceSnapshot;
  binding: ModelRequirementVerificationEvidenceBinding;
  transport: ObservedCheckTransport;
  nativeAvailable: boolean | null;
  onEvidenceChanged?: (mutation?: RequirementVerificationEvidenceMutation, reconciledSnapshot?: RequirementVerificationEvidenceSnapshot, opportunityId?: string) => void;
}) {
  const identity = JSON.stringify([
    sessionId,
    sourceRunId,
    binding.binding_fingerprint,
    snapshot.revision,
    snapshot.evidence.opportunities.opportunity_set_fingerprint,
    snapshot.evidence.opportunities.source_window_fingerprint,
    snapshot.authority_heads.map((head) => [head.opportunity_id, head.authority_record_id, head.kind, head.revision]),
  ]);
  const owner = useMemo<Owner>(() => ({ identity, transport }), [identity, transport]);
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const operation = useRef<AbortController | null>(null);
  const [manifest, setManifest] = useState<{ owner: Owner; value: ObservedCheckCandidateManifest; opportunityId: string } | null>(null);
  const [review, setReview] = useState<{ owner: Owner; value: ObservedCheckCriterionReview; opportunityId: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [issued, setIssued] = useState("");
  const [needsReconciliation, setNeedsReconciliation] = useState(false);
  const reconciliationSelection = useRef<ReconciliationSelection | null>(null);
  const [candidateQuery, setCandidateQuery] = useState("");
  const [candidatePage, setCandidatePage] = useState(0);
  const ackId = useId();

  const visibleManifest = manifest !== null && sameOwner(manifest.owner, owner) ? manifest : null;
  const visibleReview = review !== null && sameOwner(review.owner, owner) ? review : null;
  const isNativeUnavailable = nativeAvailable !== true;

  useEffect(() => {
    abort(operation.current);
    operation.current = null;
    setManifest(null);
    setReview(null);
    setBusy(false);
    setError("");
    setAcknowledged(false);
    setIssued("");
    setNeedsReconciliation(false);
    reconciliationSelection.current = null;
    setCandidateQuery("");
    setCandidatePage(0);
  }, [owner]);

  useEffect(() => () => abort(operation.current), []);

  useEffect(() => {
    if (visibleReview === null) return undefined;
    const delay = Date.parse(visibleReview.value.review_expires_at) - Date.now();
    if (!Number.isFinite(delay) || delay <= 0) {
      setReview(null);
      setAcknowledged(false);
      setError("The exact observed-check review expired. Open it again before issuing a result.");
      return undefined;
    }
    const timer = window.setTimeout(() => {
      if (sameOwner(ownerRef.current, owner)) {
        setReview(null);
        setAcknowledged(false);
        setError("The exact observed-check review expired. Open it again before issuing a result.");
      }
    }, delay);
    return () => window.clearTimeout(timer);
  }, [owner, visibleReview]);

  const currentSet = snapshot.evidence.opportunities;
  const runOperation = (work: (signal: AbortSignal) => Promise<void>, ambiguous = false) => {
    if (busy || operation.current !== null) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true);
    setError("");
    const timeout = window.setTimeout(() => {
      if (operation.current === controller && sameOwner(ownerRef.current, owner)) {
        controller.abort();
        operation.current = null;
        setBusy(false);
        setError("The observed-check request did not settle within 10 seconds. No result was assumed; retry this exact selection.");
        if (ambiguous) setNeedsReconciliation(true);
      }
    }, 10_000);
    void work(controller.signal).catch(() => {
      if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) {
        setError("The observed-check review could not be completed. No result was assumed; retry this exact selection.");
        if (ambiguous) setNeedsReconciliation(true);
      }
    }).finally(() => {
      window.clearTimeout(timeout);
      if (operation.current === controller) operation.current = null;
      if (!controller.signal.aborted && sameOwner(ownerRef.current, owner)) setBusy(false);
    });
  };

  const preflight = (opportunityId: string) => {
    if (transport.preflightRequirementVerificationObservedCheck === undefined) return;
    const head = snapshot.authority_heads.find((item) => item.opportunity_id === opportunityId);
    setManifest(null);
    setReview(null);
    setAcknowledged(false);
    setIssued("");
    setNeedsReconciliation(false);
    reconciliationSelection.current = null;
    setCandidateQuery("");
    setCandidatePage(0);
    runOperation(async (signal) => {
      const value = await transport.preflightRequirementVerificationObservedCheck!(
        sessionId,
        currentSet.opportunity_set_fingerprint,
        opportunityId,
        {
          expected_source_run_id: sourceRunId,
          through_revision: snapshot.revision,
          expected_predecessor_authority_id: head?.authority_record_id ?? null,
        },
        signal,
      );
      if (signal.aborted || !sameOwner(ownerRef.current, owner)) return;
      const parsed = parseObservedCheckCandidateManifest(value, sessionId);
      const opportunity = currentSet.opportunities.find((item) => item.opportunity_id === opportunityId);
      if (opportunity === undefined
        || parsed.opportunity_set_fingerprint !== currentSet.opportunity_set_fingerprint
        || parsed.opportunity_id !== opportunityId || parsed.requirement_id !== opportunity.requirement_id
        || parsed.expected_source_run_id !== sourceRunId || parsed.source_window_fingerprint !== currentSet.source_window_fingerprint
        || parsed.requirement_plan_confirmation_id !== currentSet.requirement_plan_confirmation_id
        || parsed.requirement_plan_proposal_id !== currentSet.requirement_plan_proposal_id
        || parsed.through_revision !== snapshot.revision
        || parsed.expected_predecessor_authority_id !== (head?.authority_record_id ?? null)) {
        throw new Error("Observed-check candidates were returned for another authority.");
      }
      setManifest({ owner, value: parsed, opportunityId });
      setReview(null);
      setAcknowledged(false);
      setIssued("");
      setNeedsReconciliation(false);
    });
  };

  const openReview = (candidateId: string) => {
    if (visibleManifest === null || isNativeUnavailable || transport.reviewRequirementVerificationObservedCheck === undefined) return;
    const { value: candidateManifest, opportunityId } = visibleManifest;
    setReview(null);
    setAcknowledged(false);
    setIssued("");
    setNeedsReconciliation(false);
    reconciliationSelection.current = null;
    runOperation(async (signal) => {
      const value = await transport.reviewRequirementVerificationObservedCheck!(
        sessionId,
        candidateManifest.opportunity_set_fingerprint,
        opportunityId,
        candidateId,
        {
          expected_source_run_id: sourceRunId,
          through_revision: candidateManifest.through_revision,
          expected_predecessor_authority_id: candidateManifest.expected_predecessor_authority_id,
          candidate_manifest_fingerprint: candidateManifest.candidate_manifest_fingerprint,
          confirmation: "open_exact_local_requirement_observed_check_review",
        },
        signal,
      );
      if (signal.aborted || !sameOwner(ownerRef.current, owner)) return;
      const parsed = parseObservedCheckCriterionReview(value, sessionId);
      const candidate = candidateManifest.candidates.find((item) => item.candidate_id === candidateId);
      if (parsed.opportunity_set_fingerprint !== candidateManifest.opportunity_set_fingerprint
        || candidate === undefined || parsed.opportunity_id !== opportunityId || parsed.requirement_id !== candidateManifest.requirement_id
        || parsed.candidate.candidate_id !== candidateId || parsed.candidate.observed_sequence !== candidate.observed_sequence
        || parsed.candidate.observed_outcome !== candidate.observed_outcome || parsed.expected_source_run_id !== sourceRunId
        || parsed.source_window_fingerprint !== candidateManifest.source_window_fingerprint
        || parsed.through_revision !== candidateManifest.through_revision
        || parsed.expected_predecessor_authority_id !== candidateManifest.expected_predecessor_authority_id
        || parsed.candidate_manifest_fingerprint !== candidateManifest.candidate_manifest_fingerprint
        || parsed.requirement_plan_confirmation_id !== candidateManifest.requirement_plan_confirmation_id
        || parsed.requirement_plan_proposal_id !== candidateManifest.requirement_plan_proposal_id) {
        throw new Error("Observed-check review did not match the selected candidate.");
      }
      setReview({ owner, value: parsed, opportunityId });
      setAcknowledged(false);
    });
  };

  const issue = () => {
    if (visibleReview === null || !acknowledged || isNativeUnavailable || transport.issueRequirementVerificationObservedCheck === undefined) return;
    const { value, opportunityId } = visibleReview;
    reconciliationSelection.current = {
      owner,
      opportunityId,
      candidateId: value.candidate.candidate_id,
      candidateSequence: value.candidate.observed_sequence,
      candidateOutcome: value.candidate.observed_outcome,
      throughRevision: value.through_revision,
    };
    runOperation(async (signal) => {
      const result = await transport.issueRequirementVerificationObservedCheck!(
        sessionId,
        value.opportunity_set_fingerprint,
        opportunityId,
        value.candidate.candidate_id,
        {
          expected_source_run_id: value.expected_source_run_id,
          source_window_fingerprint: value.source_window_fingerprint,
          through_revision: value.through_revision,
          expected_predecessor_authority_id: value.expected_predecessor_authority_id,
          candidate_manifest_fingerprint: value.candidate_manifest_fingerprint,
          review_receipt_id: value.review_receipt_id,
          review_fingerprint: value.review_fingerprint,
          full_criterion_coverage_acknowledged: true,
          confirmation: "issue_exact_local_requirement_observed_check_result",
        },
        `observed-check-${value.review_receipt_id.slice(0, 48)}`,
        signal,
      );
      if (signal.aborted || !sameOwner(ownerRef.current, owner)) return;
      const mutation = parseIssuedMutation(
        result,
        sessionId,
        value.opportunity_set_fingerprint,
        value.source_window_fingerprint,
        opportunityId,
        value.candidate.candidate_id,
        value.candidate.observed_sequence,
        value.candidate.observed_outcome,
        value.through_revision,
      );
      const observed = mutation.snapshot.evidence.verification_results.find((item) => item.opportunity_id === opportunityId);
      if (observed === undefined) throw new Error("Observed result was not returned by the server.");
      setIssued(`Server-issued observed test result: ${observed.outcome}. Human full-criterion coverage was acknowledged separately.`);
      setReview(null);
      setAcknowledged(false);
      setNeedsReconciliation(false);
      reconciliationSelection.current = null;
      try {
        void Promise.resolve(onEvidenceChanged?.(mutation, undefined, opportunityId)).catch(() => undefined);
      } catch {
        // A parent refresh failure cannot turn a validated server receipt into an error.
      }
    }, true);
  };

  const reconcile = () => {
    const selection = reconciliationSelection.current;
    if (!needsReconciliation || selection === null || !sameOwner(selection.owner, owner)
      || transport.getRequirementVerificationEvidenceSnapshot === undefined) return;
    runOperation(async (signal) => {
      const value = await transport.getRequirementVerificationEvidenceSnapshot!(
        sessionId,
        currentSet.opportunity_set_fingerprint,
        undefined,
        signal,
      );
      if (signal.aborted || !sameOwner(ownerRef.current, owner)) return;
      const next = parseRequirementVerificationEvidenceSnapshot(value, sessionId);
      const nextSet = next.evidence.opportunities;
      const result = next.evidence.verification_results.find((item) => item.opportunity_id === selection.opportunityId);
      const head = next.authority_heads.find((item) => item.opportunity_id === selection.opportunityId);
      const expectedOutcome = selection.candidateOutcome === "passed" ? "passed" : "failed";
      if (nextSet.opportunity_set_fingerprint !== currentSet.opportunity_set_fingerprint
        || nextSet.source_window_fingerprint !== currentSet.source_window_fingerprint
        || result === undefined
        || !result.receipt_reference_ids.includes(selection.candidateId)
        || result.method !== "test"
        || result.observed_sequence !== selection.candidateSequence
        || result.outcome !== expectedOutcome
        || head === undefined
        || head.authority_record_id !== result.result_id
        || head.kind !== "objective_result"
        || next.revision <= selection.throughRevision
        || head.revision <= selection.throughRevision) {
        throw new Error("Current evidence did not confirm the selected observed result.");
      }
      setNeedsReconciliation(false);
      reconciliationSelection.current = null;
      setIssued(`Current evidence confirms the server-issued observed test result: ${result.outcome}. Human full-criterion coverage remains separate.`);
      try {
        void Promise.resolve(onEvidenceChanged?.(undefined, next, selection.opportunityId)).catch(() => undefined);
      } catch {
        // A parent refresh failure does not change the validated read.
      }
    });
  };

  return (
    <section className="observed-check-evidence" aria-labelledby={`${ackId}-heading`}>
      <header>
        <h5 id={`${ackId}-heading`}>Observed direct-pytest checks</h5>
        <p>Provider-reported test outcomes are separate from human-reviewed full-criterion coverage.</p>
      </header>
      {nativeAvailable === null && <p role="status">Checking native review capability…</p>}
      {nativeAvailable === false && <p role="status">Native review is unavailable in this local session. No alternate result path is offered.</p>}
      {transport.preflightRequirementVerificationObservedCheck === undefined && <p role="status">Observed direct-pytest checks are unavailable in this client.</p>}
      <ul>
        {currentSet.opportunities.map((opportunity) => (
          <li key={opportunity.opportunity_id}>
            <span>Requirement {opportunity.requirement_index + 1}</span>
            <button type="button" disabled={busy || transport.preflightRequirementVerificationObservedCheck === undefined} onClick={() => preflight(opportunity.opportunity_id)}>
              {busy && visibleManifest?.opportunityId === opportunity.opportunity_id ? "Finding eligible checks…" : "Find eligible direct-pytest checks"}
            </button>
          </li>
        ))}
      </ul>
      {visibleManifest !== null && (
        <div className="observed-check-evidence__candidates">
          <h6>Eligible checks for requirement {(currentSet.opportunities.find((item) => item.opportunity_id === visibleManifest.opportunityId)?.requirement_index ?? 0) + 1}</h6>
          {visibleManifest.value.candidates.length === 0 && <p role="status">No eligible direct-pytest checks are available for this exact requirement.</p>}
          {visibleManifest.value.candidates.length > 0 && (
            <label className="observed-check-evidence__filter">
              Filter eligible checks
              <input
                aria-label="Filter eligible checks"
                value={candidateQuery}
                onChange={(event) => { setCandidateQuery(event.target.value); setCandidatePage(0); }}
              />
            </label>
          )}
          {(() => {
            const query = candidateQuery.trim().toLowerCase();
            const filtered = visibleManifest.value.candidates.filter((candidate) => (
              `${candidate.rule_id} ${candidate.observed_outcome} ${candidate.observed_sequence}`.toLowerCase().includes(query)
            ));
            const pageSize = 25;
            const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
            const page = Math.min(candidatePage, pageCount - 1);
            const pageCandidates = filtered.slice(page * pageSize, (page + 1) * pageSize);
            return (
              <>
                {filtered.length === 0 && visibleManifest.value.candidates.length > 0 && <p role="status">No eligible checks match this filter.</p>}
                {pageCandidates.map((candidate) => (
            <div className="observed-check-evidence__candidate" key={candidate.candidate_id}>
              <span>Observed sequence {candidate.observed_sequence} · {candidate.rule_id} · provider-reported result: <strong>{candidate.observed_outcome === "passed" ? "passed" : "check failed"}</strong></span>
              <button type="button" disabled={busy || isNativeUnavailable || transport.reviewRequirementVerificationObservedCheck === undefined} onClick={() => openReview(candidate.candidate_id)}>Review exact criterion</button>
            </div>
                ))}
                {filtered.length > pageSize && (
                  <nav aria-label="Eligible check pages" className="observed-check-evidence__pages">
                    <button type="button" disabled={page === 0 || busy} onClick={() => setCandidatePage((current) => Math.max(0, current - 1))}>Previous check page</button>
                    <span>Candidate page {page + 1} of {pageCount}</span>
                    <button type="button" disabled={page >= pageCount - 1 || busy} onClick={() => setCandidatePage((current) => Math.min(pageCount - 1, current + 1))}>Next check page</button>
                  </nav>
                )}
              </>
            );
          })()}
        </div>
      )}
      {error && <p role="alert">{error}</p>}
      {needsReconciliation && transport.getRequirementVerificationEvidenceSnapshot !== undefined && <button type="button" disabled={busy} onClick={reconcile}>{busy ? "Inspecting current evidence…" : "Inspect current evidence"}</button>}
      {visibleReview !== null && (
        <div className="observed-check-evidence__review" aria-live="polite">
          <h6>Human-reviewed full-criterion coverage</h6>
          <p>Requirement criterion</p>
          <pre>{visibleReview.value.requirement_text}</pre>
          <p>Observed provider check: {visibleReview.value.check_tool_name}</p>
          <pre>{visibleReview.value.check_invocation_preview}</pre>
          {visibleReview.value.check_effect_preview !== null && <pre>{visibleReview.value.check_effect_preview}</pre>}
          <label htmlFor={ackId}>I reviewed the exact requirement and check evidence and acknowledge full-criterion coverage.</label>
          <input id={ackId} type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} disabled={busy || isNativeUnavailable} />
          <button type="button" disabled={!acknowledged || busy || isNativeUnavailable || transport.issueRequirementVerificationObservedCheck === undefined} onClick={issue}>Issue server-derived observed result</button>
          <p role="status">No outcome or verification method can be selected in this client; the server derives the result from the selected observed receipt.</p>
        </div>
      )}
      {issued && <p role="status">{issued}</p>}
    </section>
  );
}
