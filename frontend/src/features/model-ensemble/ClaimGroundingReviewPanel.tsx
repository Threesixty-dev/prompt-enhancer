import { useEffect, useId, useMemo, useRef, useState } from "react";
import type {
  ClaimGroundingBegin, ClaimGroundingConsumeRequest, PromptEnhancerTransport,
  RequirementPlanEvidenceContract,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { ClaimGroundingLinkReviewPanel } from "./ClaimGroundingLinkReviewPanel";

type Transport = Pick<PromptEnhancerTransport,
  "getRequirementPlanEvidenceContract" | "beginClaimGroundingReview" | "beginClaimGroundingLinkReview" | "persistClaimGroundingCensus" | "recoverClaimGroundingCensus" | "listClaimGroundingCensuses">
  & Partial<Pick<PromptEnhancerTransport, "getUserPresenceCapability">>;
type Choice = "material_claim" | "excluded";
type Owner = { key: string; transport: Transport };
const exclusionReasons = [
  "not_a_completion_or_verification_claim",
  "duplicate_or_superseded_claim",
  "non_assertive_status_or_qualification",
] as const;

function contractCurrent(contract: RequirementPlanEvidenceContract, sessionId: string, sourceRunId: string): boolean {
  const expiry = Date.parse(contract.source_manifest.review_context_expires_at);
  return contract.session_id === sessionId
    && contract.expected_source_run_id === sourceRunId
    && contract.source_manifest.session_id === sessionId
    && contract.source_manifest.source_run_id === sourceRunId
    && contract.source_manifest.source_window_fingerprint === contract.source_window_fingerprint
    && Number.isFinite(expiry) && expiry > Date.now();
}

export function ClaimGroundingReviewPanel({ sessionId, sourceRunId, transport }: {
  sessionId: string; sourceRunId: string; transport: Transport;
}) {
  const [open, setOpen] = useState(false);
  const [review, setReview] = useState<ClaimGroundingBegin | null>(null);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [reasons, setReasons] = useState<Record<string, typeof exclusionReasons[number]>>({});
  const [nativeReady, setNativeReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [saved, setSaved] = useState<Array<{ census_id: string; session_id: string; source_run_id: string; source_window_fingerprint: string; census_fingerprint: string; manifest_fingerprint: string; candidate_count: number }>>([]);
  const [savedOffset, setSavedOffset] = useState(0);
  const [snapshot, setSnapshot] = useState<{ snapshot_id: string; total: number; high_water_created_at: string | null; high_water_census_id: string | null } | undefined>();
  const [refresh, setRefresh] = useState(0);
  const [listLoading, setListLoading] = useState(false);
  const owner = useMemo<Owner>(() => ({ key: `${sessionId}:${sourceRunId}`, transport }), [sessionId, sourceRunId, transport]);
  const listPendingRef = useRef(false);
  const listOwnerRef = useRef(owner.key);
  const listGenerationRef = useRef(0);
  const renderedListOwnerRef = useRef(owner.key);
  const ownerChangedForList = renderedListOwnerRef.current !== owner.key;
  if (ownerChangedForList) { renderedListOwnerRef.current = owner.key; listOwnerRef.current = owner.key; listPendingRef.current = false; listGenerationRef.current += 1; }
  const ownerRef = useRef(owner); ownerRef.current = owner;
  const generationRef = useRef(0);
  const radioPrefix = useId();
  const abortRef = useRef<AbortController | null>(null);
  const pendingRef = useRef(false);
  const recoveryRef = useRef<{ key: string; sessionId: string; runId: string; window: string; manifest: string; count: number } | null>(null);
  const reset = () => { generationRef.current += 1; abortRef.current?.abort(); abortRef.current = null; pendingRef.current = false; setReview(null); setChoices({}); setReasons({}); setBusy(false); };

  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => { reset(); recoveryRef.current = null; listPendingRef.current = false; listOwnerRef.current = owner.key; setSaved([]); setSavedOffset(0); setSnapshot(undefined); setNotice(""); }, [owner]);
  useEffect(() => {
    if (!open || transport.listClaimGroundingCensuses === undefined || listPendingRef.current || listOwnerRef.current !== owner.key) return;
    listPendingRef.current = true;
    setListLoading(true);
    const generation = ++listGenerationRef.current;
    const controller = new AbortController();
    const requestOffset = ownerChangedForList ? 0 : savedOffset;
    const requestSnapshot = ownerChangedForList ? undefined : snapshot;
    void transport.listClaimGroundingCensuses(sessionId, { limit: 50, offset: requestOffset, snapshot: requestSnapshot }, controller.signal).then((page) => {
      if (!controller.signal.aborted && ownerRef.current === owner && listOwnerRef.current === owner.key && generation === listGenerationRef.current) { setSaved(page.items.map((item) => ({ census_id: item.census_id, session_id: item.session_id, source_run_id: item.source_run_id, source_window_fingerprint: item.source_window_fingerprint, census_fingerprint: item.census_fingerprint, manifest_fingerprint: item.manifest_fingerprint, candidate_count: item.candidate_count }))); setSnapshot({ snapshot_id: page.snapshot_id, total: page.total, high_water_created_at: page.high_water_created_at ?? null, high_water_census_id: page.high_water_census_id ?? null }); }
    }).catch(() => { if (!controller.signal.aborted && ownerRef.current === owner && generation === listGenerationRef.current) { setSaved([]); setNotice("Saved classification metadata could not be reloaded. Refresh to start a new list snapshot."); } }).finally(() => { if (generation === listGenerationRef.current) { listPendingRef.current = false; setListLoading(false); } });
    return () => {
      controller.abort();
      // Release only this generation. A late, abort-ignoring promise is then
      // permanently stale and cannot settle the next page request.
      if (generation === listGenerationRef.current) {
        listGenerationRef.current += 1;
        listPendingRef.current = false;
        setListLoading(false);
      }
    };
  }, [open, owner, sessionId, transport, savedOffset, refresh]);
  useEffect(() => {
    setNativeReady(false);
    if (!open || transport.getUserPresenceCapability === undefined) return;
    const controller = new AbortController();
    void transport.getUserPresenceCapability(controller.signal).then((capability) => {
      if (ownerRef.current === owner && !controller.signal.aborted) {
        setNativeReady(capability.confirmation_available === true && capability.mode === "native_bridge_bound_token");
      }
    }).catch(() => { if (ownerRef.current === owner && !controller.signal.aborted) setNativeReady(false); });
    return () => controller.abort();
  }, [open, owner, transport]);

  useEffect(() => {
    if (review === null) return;
    const delay = Date.parse(review.review_expires_at) - Date.now();
    if (!Number.isFinite(delay) || delay <= 0) { reset(); setNotice("Review expired. Begin again to see current local clauses."); return; }
    const timer = window.setTimeout(() => { reset(); setNotice("Review expired. Begin again to see current local clauses."); }, delay + 1);
    return () => window.clearTimeout(timer);
  }, [review]);

  const begin = async () => {
    if (pendingRef.current || recoveryRef.current !== null || !nativeReady || transport.getRequirementPlanEvidenceContract === undefined || transport.beginClaimGroundingReview === undefined) return;
    pendingRef.current = true; setBusy(true); setNotice("");
    const generation = ++generationRef.current;
    const controller = new AbortController(); abortRef.current = controller;
    try {
      const contract = await transport.getRequirementPlanEvidenceContract(sessionId, controller.signal);
      if (controller.signal.aborted || generation !== generationRef.current || !contractCurrent(contract, sessionId, sourceRunId) || ownerRef.current !== owner) throw new Error("The selected sealed source is no longer current. Refresh before reviewing.");
      const next = await transport.beginClaimGroundingReview(sessionId, {
        expected_source_run_id: contract.expected_source_run_id,
        expected_source_window_fingerprint: contract.source_window_fingerprint,
      }, controller.signal);
      if (ownerRef.current !== owner || controller.signal.aborted || generation !== generationRef.current) return;
      setReview(next); setChoices({}); setReasons({});
    } catch (error) {
      if (!controller.signal.aborted && ownerRef.current === owner) setNotice(error instanceof Error ? error.message : "Claim review could not be opened.");
    } finally { if (ownerRef.current === owner && generation === generationRef.current) { pendingRef.current = false; setBusy(false); } }
  };
  const complete = review !== null && review.candidates.every((candidate) => choices[candidate.candidate_id] !== undefined && (choices[candidate.candidate_id] !== "excluded" || exclusionReasons.includes(reasons[candidate.candidate_id] as typeof exclusionReasons[number])));
  const consume = async () => {
    if (review === null || !complete || !nativeReady || pendingRef.current || recoveryRef.current !== null || transport.persistClaimGroundingCensus === undefined || Date.parse(review.review_expires_at) <= Date.now()) return;
    pendingRef.current = true; setBusy(true); setNotice("");
    const generation = ++generationRef.current;
    const controller = new AbortController(); abortRef.current = controller;
    const request: ClaimGroundingConsumeRequest = {
      review_receipt_id: review.review_receipt_id, review_fingerprint: review.review_fingerprint,
      manifest_fingerprint: review.manifest.manifest_fingerprint,
      classifications: review.candidates.map((candidate) => ({ candidate_id: candidate.candidate_id, classification: choices[candidate.candidate_id]!, exclusion_reason: choices[candidate.candidate_id] === "excluded" ? reasons[candidate.candidate_id]! : null })),
    };
    const idempotencyKey = crypto.randomUUID();
    recoveryRef.current = { key: idempotencyKey, sessionId, runId: review.source_run_id, window: review.source_window_fingerprint, manifest: request.manifest_fingerprint, count: request.classifications.length };
    try {
      await transport.persistClaimGroundingCensus(sessionId, request, idempotencyKey, review.source_run_id, review.source_window_fingerprint, controller.signal);
      if (ownerRef.current !== owner || controller.signal.aborted || generation !== generationRef.current) return;
      reset(); recoveryRef.current = null; setNotice("Saved classification metadata · not a measured metric.");
    } catch (error) {
      if (!controller.signal.aborted && ownerRef.current === owner && generation === generationRef.current) {
        const declined = error instanceof TransportError
          && error.reasonCode === "native_confirmation_declined_before_dispatch";
        if (declined) recoveryRef.current = null;
        if (!declined) reset();
        setNotice(declined ? error.message : "Save outcome is uncertain. Claim prose and receipt were retired; use Check save status. It was not retried.");
      }
    } finally { if (ownerRef.current === owner && generation === generationRef.current) { pendingRef.current = false; setBusy(false); } }
  };
  const checkSaveStatus = async () => {
    const pending = recoveryRef.current;
    if (pending === null || pending.sessionId !== sessionId || pending.runId !== sourceRunId || transport.recoverClaimGroundingCensus === undefined || busy) return;
    setBusy(true); setNotice(""); const generation = ++generationRef.current;
    const controller = new AbortController(); abortRef.current = controller;
    try {
      const result = await transport.recoverClaimGroundingCensus(sessionId, pending.key, controller.signal);
      if (ownerRef.current !== owner || controller.signal.aborted || generation !== generationRef.current) return;
      if (result.source_run_id !== pending.runId || result.source_window_fingerprint !== pending.window || result.manifest_fingerprint !== pending.manifest || result.candidate_count !== pending.count || result.measured !== false || result.metric_authority_established !== false) { setNotice("Save status is unknown. The recovered record did not match this review."); return; }
      recoveryRef.current = null; setNotice("Saved classification metadata · not a measured metric.");
    } catch (error) {
      if (ownerRef.current === owner && !controller.signal.aborted && generation === generationRef.current) setNotice(error instanceof TransportError && error.reasonCode === "claim_grounding_census_conflict" ? "Save conflicted with the current source; it was not promoted." : error instanceof TransportError && error.status === 404 ? "No saved result was found yet. You may check again later." : "Save status is unknown. You may check again later.");
    } finally { if (ownerRef.current === owner && generation === generationRef.current) setBusy(false); }
  };

  const capabilities = transport.getRequirementPlanEvidenceContract !== undefined && transport.beginClaimGroundingReview !== undefined && transport.persistClaimGroundingCensus !== undefined;
  return <details className="requirement-plan-evidence" open={open}>
    <summary onClick={(event) => { event.preventDefault(); const next = !open; if (!next) reset(); setOpen(next); }}>Review assistant completion claims <small>Local classification metadata · no metric authority</small></summary>
    {!capabilities ? <p role="status">Claim review is unavailable in this local connection.</p> : !nativeReady ? <p role="status">Native user-presence confirmation is unavailable; claim prose stays closed.</p> : review === null ? <button type="button" disabled={busy || recoveryRef.current !== null} onClick={() => void begin()}>{busy ? "Opening native review…" : recoveryRef.current !== null ? "Check save status first" : "Begin review"}</button> : <>
      <p>{review.candidates.filter((candidate) => choices[candidate.candidate_id] !== undefined && (choices[candidate.candidate_id] !== "excluded" || exclusionReasons.includes(reasons[candidate.candidate_id] as typeof exclusionReasons[number]))).length} of {review.candidates.length} response clauses classified. No choice is preselected.</p>
      {review.candidates.map((candidate, index) => <fieldset key={candidate.candidate_id}>
        <legend>Response clause {index + 1}</legend><p>{candidate.text}</p>
        <label><input disabled={busy} type="radio" name={`${radioPrefix}-${candidate.candidate_id}`} checked={choices[candidate.candidate_id] === "material_claim"} onChange={() => setChoices((value) => ({ ...value, [candidate.candidate_id]: "material_claim" }))} /> Material completion or verification claim</label>
        <label><input disabled={busy} type="radio" name={`${radioPrefix}-${candidate.candidate_id}`} checked={choices[candidate.candidate_id] === "excluded"} onChange={() => setChoices((value) => ({ ...value, [candidate.candidate_id]: "excluded" }))} /> Exclude</label>
        {choices[candidate.candidate_id] === "excluded" && <label>Exclusion reason <select disabled={busy} value={reasons[candidate.candidate_id] ?? ""} onChange={(event) => setReasons((value) => ({ ...value, [candidate.candidate_id]: event.target.value as typeof exclusionReasons[number] }))}><option value="">Choose a reason</option>{exclusionReasons.map((reason) => <option key={reason} value={reason}>{reason.replaceAll("_", " ")}</option>)}</select></label>}
      </fieldset>)}
      <p>Saving stores sensitive local derived classification metadata. Candidate prose is not saved.</p>
      <button type="button" disabled={!complete || busy} onClick={() => void consume()}>{busy ? "Saving native review…" : "Save complete review"}</button>
    </>}
    {recoveryRef.current !== null && <button type="button" disabled={busy} onClick={() => void checkSaveStatus()}>Check save status</button>}
    <section aria-label="Saved claim classifications">{saved.length > 0 && <><p>Saved classification metadata · not a measured metric.</p><ul>{saved.map((item) => <li key={item.census_id}>Historical source {item.source_run_id.slice(0, 12)}… · {item.candidate_count} classified clauses</li>)}</ul></>}<button type="button" disabled={busy || listLoading} onClick={() => { setSnapshot(undefined); setSavedOffset(0); setRefresh((value) => value + 1); }}>Refresh saved metadata</button>{snapshot !== undefined && savedOffset + saved.length < snapshot.total && <button type="button" disabled={busy || listLoading} onClick={() => setSavedOffset((value) => value + 50)}>Next saved metadata</button>}</section>
    {open && saved.filter((item) => item.session_id === sessionId && item.source_run_id === sourceRunId).map((item) => <ClaimGroundingLinkReviewPanel key={item.census_id} sessionId={sessionId} sourceRunId={sourceRunId} census={item} transport={transport} />)}
    {notice !== "" && <p role="status">{notice}</p>}
  </details>;
}
