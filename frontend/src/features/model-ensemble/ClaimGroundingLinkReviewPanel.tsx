import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ClaimGroundingLinkCandidateManifest,
  ClaimGroundingLinkReview,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";

type CandidateLoader = (
  sessionId: string,
  censusId: string,
  expected: { sourceRunId: string; sourceWindowFingerprint: string; censusFingerprint: string; manifestFingerprint: string },
  signal?: AbortSignal,
) => Promise<ClaimGroundingLinkCandidateManifest>;
type Transport = Partial<Pick<PromptEnhancerTransport, "getUserPresenceCapability" | "beginClaimGroundingLinkReview">> & { getClaimGroundingLinkCandidates?: CandidateLoader };
type SavedCensus = { census_id: string; session_id: string; source_run_id: string; source_window_fingerprint: string; census_fingerprint: string; manifest_fingerprint: string; candidate_count: number };

export function ClaimGroundingLinkReviewPanel({ sessionId, sourceRunId, census, transport }: { sessionId: string; sourceRunId: string; census: SavedCensus; transport: Transport }) {
  const [open, setOpen] = useState(false);
  const [nativeReady, setNativeReady] = useState(false);
  const [manifest, setManifest] = useState<ClaimGroundingLinkCandidateManifest | null>(null);
  const [candidateId, setCandidateId] = useState("");
  const [references, setReferences] = useState<string[]>([]);
  const [review, setReview] = useState<ClaimGroundingLinkReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [candidatePage, setCandidatePage] = useState(0);
  const [checkPage, setCheckPage] = useState(0);
  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const pendingRef = useRef(false);
  const owner = useMemo(() => ({ key: `${sessionId}:${sourceRunId}:${census.census_id}:${census.source_window_fingerprint}:${census.census_fingerprint}:${census.manifest_fingerprint}`, transport }), [sessionId, sourceRunId, census.census_id, census.source_window_fingerprint, census.census_fingerprint, census.manifest_fingerprint, transport]);
  const [stateOwner, setStateOwner] = useState(owner);
  const ownerChanged = stateOwner !== owner;

  const clear = () => { generationRef.current += 1; abortRef.current?.abort(); abortRef.current = null; pendingRef.current = false; setManifest(null); setCandidateId(""); setReferences([]); setReview(null); setCandidatePage(0); setCheckPage(0); setBusy(false); };
  const expireReview = () => { generationRef.current += 1; abortRef.current?.abort(); abortRef.current = null; setReview(null); pendingRef.current = false; setBusy(false); setNotice("Link review expired. Begin again to preview current local evidence."); };
  useEffect(() => {
    clear();
    setStateOwner(owner);
    return () => clear();
  }, [owner]);
  useEffect(() => {
    setNativeReady(false);
    if (!open || transport.getUserPresenceCapability === undefined) return;
    const controller = new AbortController();
    void transport.getUserPresenceCapability(controller.signal).then((capability) => { if (!controller.signal.aborted) setNativeReady(capability.confirmation_available === true && capability.mode === "native_bridge_bound_token"); }).catch(() => { if (!controller.signal.aborted) setNativeReady(false); });
    return () => controller.abort();
  }, [open, transport]);
  useEffect(() => {
    if (!open || transport.getClaimGroundingLinkCandidates === undefined || census.source_run_id !== sourceRunId) return;
    const controller = new AbortController(); const generation = ++generationRef.current;
    setBusy(true); setNotice(""); setManifest(null); setCandidateId(""); setReferences([]); setReview(null);
    void transport.getClaimGroundingLinkCandidates(sessionId, census.census_id, { sourceRunId: census.source_run_id, sourceWindowFingerprint: census.source_window_fingerprint, censusFingerprint: census.census_fingerprint, manifestFingerprint: census.manifest_fingerprint }, controller.signal).then((next) => { if (!controller.signal.aborted && generation === generationRef.current) setManifest(next); }).catch(() => { if (!controller.signal.aborted && generation === generationRef.current) setNotice("Current material candidates are unavailable."); }).finally(() => { if (generation === generationRef.current) setBusy(false); });
    return () => controller.abort();
  }, [open, owner, transport, sessionId, sourceRunId, census]);
  useEffect(() => {
    if (review === null) return;
    const delay = Date.parse(review.review_expires_at) - Date.now();
    if (!Number.isFinite(delay) || delay <= 0) { expireReview(); return; }
    const timer = window.setTimeout(expireReview, delay + 1);
    return () => window.clearTimeout(timer);
  }, [review]);
  const begin = () => {
    if (!nativeReady || !manifest || !candidateId || transport.beginClaimGroundingLinkReview === undefined || busy || pendingRef.current) return;
    pendingRef.current = true; setReview(null); const generation = ++generationRef.current; const controller = new AbortController(); abortRef.current = controller; setBusy(true); setNotice("");
    void transport.beginClaimGroundingLinkReview(sessionId, { census_id: census.census_id, candidate_id: candidateId, selected_check_references: references }, { source_run_id: manifest.source_run_id, source_window_fingerprint: manifest.source_window_fingerprint, census_fingerprint: manifest.census_fingerprint, manifest_fingerprint: manifest.manifest_fingerprint }, controller.signal).then((next) => { if (!controller.signal.aborted && generation === generationRef.current) setReview(next); }).catch(() => { if (!controller.signal.aborted && generation === generationRef.current) setNotice("Native link review could not be opened."); }).finally(() => { if (generation === generationRef.current) { pendingRef.current = false; setBusy(false); } });
  };
  const available = transport.getClaimGroundingLinkCandidates !== undefined && transport.beginClaimGroundingLinkReview !== undefined;
  const candidateRows = manifest?.material_candidates.slice(candidatePage * 50, candidatePage * 50 + 50) ?? [];
  const checkRows = manifest?.observed_checks.slice(checkPage * 50, checkPage * 50 + 50) ?? [];
  const displayedManifest = ownerChanged ? null : manifest;
  const displayedReview = ownerChanged ? null : review;
  const displayedNativeReady = !ownerChanged && nativeReady;
  return <details open={open}>
    <summary onClick={(event) => { event.preventDefault(); const next = !open; if (!next) clear(); setOpen(next); }}>Link a material claim to observed checks</summary>
    {!available ? <p role="status">Claim-link preview is unavailable in this connection.</p> : census.source_run_id !== sourceRunId ? <p role="status">This saved census is from a different source and cannot be linked here.</p> : busy && displayedManifest === null ? <p role="status">Loading content-free link choices…</p> : displayedManifest === null ? <p role="status">{notice || "No current link choices are available."}</p> : displayedReview === null ? <>
      {displayedManifest.material_candidates.length === 0 ? <p>No saved material claims are eligible for this source.</p> : <fieldset><legend>Material claim ({displayedManifest.material_candidates.length} available)</legend>{candidateRows.map((candidate) => <label key={candidate.candidate_id}><input type="radio" name={`material-${census.census_id}`} disabled={busy} checked={candidateId === candidate.candidate_id} onChange={() => setCandidateId(candidate.candidate_id)} /> Message {candidate.message_sequence}, clause {candidate.clause_index + 1}</label>)}{displayedManifest.material_candidates.length > 50 && <p><button type="button" disabled={busy || candidatePage === 0} onClick={() => setCandidatePage((page) => page - 1)}>Previous claims</button> <button type="button" disabled={busy || (candidatePage + 1) * 50 >= displayedManifest.material_candidates.length} onClick={() => setCandidatePage((page) => page + 1)}>Next claims</button></p>}</fieldset>}
      {displayedManifest.observed_checks.length === 0 ? <p>No observed checks are available for this source. You can preview the claim with no check references.</p> : <fieldset><legend>Observed checks ({references.length} selected of {displayedManifest.observed_checks.length})</legend>{checkRows.map((check) => <label key={check.source_reference_id}><input type="checkbox" disabled={busy} checked={references.includes(check.source_reference_id)} onChange={() => setReferences((current) => current.includes(check.source_reference_id) ? current.filter((value) => value !== check.source_reference_id) : current.length >= 128 ? current : [...current, check.source_reference_id])} /> Sequence {check.observed_sequence} · {check.outcome}</label>)}{displayedManifest.observed_checks.length > 50 && <p><button type="button" disabled={busy || checkPage === 0} onClick={() => setCheckPage((page) => page - 1)}>Previous checks</button> <button type="button" disabled={busy || (checkPage + 1) * 50 >= displayedManifest.observed_checks.length} onClick={() => setCheckPage((page) => page + 1)}>Next checks</button></p>}</fieldset>}
      {!displayedNativeReady && <p role="status">Native confirmation is unavailable; claim prose stays closed.</p>}<button type="button" disabled={busy || !candidateId || !displayedNativeReady} onClick={begin}>{busy ? "Opening native link review…" : "Begin native link preview"}</button>
      <p>Preview only. Nothing is saved or measured.</p>
    </> : <><p>{displayedReview.claim_clause}</p><ul>{displayedReview.observed_checks.map((check) => <li key={check.source_reference_id}>Sequence {check.observed_sequence} · {check.outcome} · {check.tool_name}: {check.invocation_preview}{check.effect_preview === null ? "" : ` · ${check.effect_preview}`}</li>)}</ul><p>Preview only. Not saved and not a measured metric.</p></>}
    {notice !== "" && <p role="status">{notice}</p>}
  </details>;
}
