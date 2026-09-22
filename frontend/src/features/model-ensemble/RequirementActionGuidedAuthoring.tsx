import { useEffect, useRef, useState } from "react";
import type {
  PromptEnhancerTransport,
  RequirementActionEvidenceContract,
  RequirementActionGuidedAuthoringReview,
  RequirementActionProposal,
} from "../../shared/api/contracts";
import {
  parseRequirementActionGuidedAuthoringProposal,
  parseRequirementActionGuidedAuthoringReview,
} from "../../shared/api/requirementActionGuidedAuthoringContract";
import "./RequirementActionGuidedAuthoring.css";

type GuidedTransport = Pick<
  PromptEnhancerTransport,
  "reviewRequirementActionGuidedAuthoring" | "submitRequirementActionGuidedAuthoring"
>;

type Props = {
  sessionId: string;
  contract: RequirementActionEvidenceContract;
  transport: GuidedTransport;
  enabled: boolean;
  onCreated: (proposal: RequirementActionProposal) => void;
  onClosed: () => void;
};

type Owner = {
  binding: string;
  transport: GuidedTransport;
};

type Operation = {
  controller: AbortController;
  owner: Owner;
};

const key = (index: number) => String(index);
const createIdempotencyKey = () =>
  `requirement-action-guided-${crypto.randomUUID().replaceAll("-", "")}`;

function sameOwner(left: Owner | null, right: Owner): boolean {
  return left !== null && left.binding === right.binding && left.transport === right.transport;
}

export function RequirementActionGuidedAuthoring({
  sessionId,
  contract,
  transport,
  enabled,
  onCreated,
  onClosed,
}: Props) {
  const [review, setReview] = useState<RequirementActionGuidedAuthoringReview | null>(null);
  const [requirementIndex, setRequirementIndex] = useState(0);
  const [links, setLinks] = useState<Record<string, number[] | null>>({});
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = useRef<Operation | null>(null);
  const busyRef = useRef(false);
  const ownerBinding = JSON.stringify([sessionId, contract, enabled]);
  const currentOwner: Owner = { binding: ownerBinding, transport };
  const ownerRef = useRef<Owner>(currentOwner);
  ownerRef.current = currentOwner;
  const reviewOwner = useRef<Owner | null>(null);

  function operationCurrent(operation: Operation): boolean {
    return active.current === operation
      && !operation.controller.signal.aborted
      && sameOwner(operation.owner, ownerRef.current);
  }

  function setOperationBusy(value: boolean) {
    busyRef.current = value;
    setBusy(value);
  }

  function clear() {
    active.current?.controller.abort();
    active.current = null;
    reviewOwner.current = null;
    setReview(null);
    setRequirementIndex(0);
    setLinks({});
    setQuery("");
    setPage(0);
    setOperationBusy(false);
  }

  useEffect(() => {
    clear();
  }, [ownerBinding, transport]);

  useEffect(() => () => {
    clear();
  }, []);

  useEffect(() => {
    const reviewOwnerSnapshot = reviewOwner.current;
    if (!review || reviewOwnerSnapshot === null || !sameOwner(reviewOwnerSnapshot, ownerRef.current)) return undefined;
    const expiresIn = Math.min(
      Date.parse(review.review_context_expires_at),
      Date.parse(review.authoring_receipt_expires_at),
    ) - Date.now();
    const timeout = window.setTimeout(() => {
      if (!sameOwner(reviewOwnerSnapshot, ownerRef.current) || reviewOwner.current !== reviewOwnerSnapshot) return;
      clear();
      onClosed();
    }, Math.min(Math.max(0, expiresIn), 2_147_483_647));
    return () => window.clearTimeout(timeout);
  }, [review]);

  const currentReview = review !== null && sameOwner(reviewOwner.current, currentOwner) ? review : null;
  const currentRequirement = currentReview?.requirements[requirementIndex];
  const candidates = currentReview?.candidate_memberships ?? [];
  const normalizedQuery = query.toLowerCase();
  const filteredCandidates = candidates.filter((item) =>
    `${item.tool_name} ${item.invocation_preview} ${item.result_or_effect_preview ?? ""} ${item.candidate.state}`
      .toLowerCase()
      .includes(normalizedQuery),
  );
  const visibleCandidates = filteredCandidates.slice(page * 20, page * 20 + 20);
  const complete = currentReview !== null && currentReview.requirements.every((_, index) => {
    const selected = links[key(index)];
    return selected === null || (selected?.length ?? 0) > 0;
  });

  async function open() {
    const reviewTransport = transport.reviewRequirementActionGuidedAuthoring;
    if (!sameOwner(currentOwner, ownerRef.current) || !enabled || !reviewTransport || busyRef.current) return;

    clear();
    const controller = new AbortController();
    const operation: Operation = { controller, owner: currentOwner };
    active.current = operation;
    setOperationBusy(true);
    setError("");

    try {
      const response = await reviewTransport(
        sessionId,
        contract,
        {
          expected_source_run_id: contract.expected_source_run_id,
          source_window_fingerprint: contract.source_window_fingerprint,
          requirement_plan_confirmation_id: contract.requirement_plan_confirmation_id,
          requirement_plan_evidence_fingerprint: contract.requirement_plan_evidence_fingerprint,
          candidate_manifest_fingerprint: contract.candidate_manifest.manifest_fingerprint,
          expected_predecessor_confirmation_id: contract.expected_predecessor_confirmation_id,
          confirmation: "open_exact_local_requirement_action_guided_authoring",
        },
        controller.signal,
      );
      if (operationCurrent(operation)) {
        const parsedReview = parseRequirementActionGuidedAuthoringReview(response, { sessionId, contract });
        reviewOwner.current = operation.owner;
        setReview(parsedReview);
      }
    } catch {
      if (operationCurrent(operation)) {
        clear();
        setError("The exact local action review could not be opened.");
      }
    } finally {
      if (operationCurrent(operation)) setOperationBusy(false);
    }
  }

  async function submit() {
    const submitTransport = transport.submitRequirementActionGuidedAuthoring;
    if (!sameOwner(currentOwner, ownerRef.current) || !currentReview || !complete || !submitTransport || busyRef.current) return;
    const now = Date.now();
    const reviewIsCurrent =
      sameOwner(reviewOwner.current, currentOwner) &&
      Date.parse(currentReview.review_context_expires_at) > now &&
      Date.parse(currentReview.authoring_receipt_expires_at) > now;
    if (!enabled || !reviewIsCurrent) {
      clear();
      onClosed();
      return;
    }

    const controller = new AbortController();
    const operation: Operation = { controller, owner: currentOwner };
    active.current = operation;
    setOperationBusy(true);
    const command = {
      expected_source_run_id: currentReview.source_run_id,
      source_window_fingerprint: currentReview.source_window_fingerprint,
      requirement_plan_confirmation_id: currentReview.requirement_plan_confirmation_id,
      requirement_plan_evidence_fingerprint: currentReview.requirement_plan_evidence_fingerprint,
      candidate_manifest_fingerprint: currentReview.candidate_manifest_fingerprint,
      expected_predecessor_confirmation_id: currentReview.expected_predecessor_confirmation_id,
      authoring_receipt_id: currentReview.authoring_receipt_id,
      links: currentReview.requirements.map((_, index) => ({
        requirement_index: index,
        action_candidate_indexes: (links[key(index)] ?? []).slice().sort((a, b) => a - b),
      })),
      complete_requirement_link_classification_acknowledged: true as const,
    };

    try {
      const response = await submitTransport(
        sessionId,
        contract,
        command,
        createIdempotencyKey(),
        controller.signal,
      );
      if (operationCurrent(operation)) {
        const proposal = parseRequirementActionGuidedAuthoringProposal(response, {
          sessionId,
          contract,
          command,
        });
        clear();
        onCreated(proposal.proposal);
      }
    } catch {
      if (operationCurrent(operation)) {
        clear();
        setError(
          "The proposal result is uncertain. Local selections were cleared; check proposal history before starting a fresh review.",
        );
      }
    } finally {
      if (operationCurrent(operation)) setOperationBusy(false);
    }
  }

  if (!currentReview) {
    return (
      <section className="requirement-action-guided" aria-busy={busy}>
        <h4>Guided action matching</h4>
        <button disabled={!enabled || busy} onClick={() => void open()}>
          Open guided action review
        </button>
        {busy && (
          <button onClick={() => { clear(); onClosed(); }}>
            Close and clear
          </button>
        )}
        {error && <p role="alert">{error}</p>}
      </section>
    );
  }

  const selected = links[key(requirementIndex)];

  return (
    <section className="requirement-action-guided" aria-busy={busy}>
      <header className="requirement-action-guided__header">
        <h4>Guided action matching</h4>
        <span>{requirementIndex + 1} of {currentReview.requirements.length}</span>
        <button onClick={() => { clear(); onClosed(); }}>
          Close and clear
        </button>
      </header>

      {currentRequirement && (
        <>
          <div className="requirement-action-guided__text">
            {currentRequirement.text}
          </div>
          <fieldset disabled={busy} className="requirement-action-guided__mode">
            <legend>Link classification</legend>
            <label>
              <input
                name={`mode-${requirementIndex}`}
                type="radio"
                checked={selected !== null && selected !== undefined}
                onChange={() => setLinks({ ...links, [key(requirementIndex)]: selected ?? [] })}
              />
              Link selected actions
            </label>
            <label>
              <input
                name={`mode-${requirementIndex}`}
                type="radio"
                checked={selected === null}
                onChange={() => setLinks({ ...links, [key(requirementIndex)]: null })}
              />
              No matching action
            </label>
          </fieldset>

          {selected !== null && selected !== undefined && (
            <div className="requirement-action-guided__selection">
              <label>
                Search actions
                <input
                  value={query}
                  disabled={busy}
                  onChange={(event) => { setQuery(event.target.value); setPage(0); }}
                />
              </label>
              <div className="requirement-action-guided__candidates" aria-label="Available actions">
                {visibleCandidates.map((item) => {
                  const candidateNumber = item.candidate.candidate_index + 1;
                  return (
                    <label
                      className="requirement-action-guided__candidate"
                      key={item.candidate.action_id}
                    >
                      <input
                        aria-label={`Action ${candidateNumber}`}
                        type="checkbox"
                        disabled={busy}
                        checked={selected.includes(item.candidate.candidate_index)}
                        onChange={(event) => {
                          const candidateIndex = item.candidate.candidate_index;
                          setLinks({
                            ...links,
                            [key(requirementIndex)]: event.target.checked
                              ? [...selected, candidateIndex]
                              : selected.filter((index) => index !== candidateIndex),
                          });
                        }}
                      />
                      <span className="requirement-action-guided__candidate-content">
                        <strong>{item.tool_name} · Action {candidateNumber}</strong>
                        <dl>
                          <div>
                            <dt>State</dt>
                            <dd>{item.candidate.state}</dd>
                          </div>
                          <div>
                            <dt>Invocation</dt>
                            <dd>{item.invocation_preview}</dd>
                          </div>
                          <div>
                            <dt>Result/effect</dt>
                            <dd>{item.result_or_effect_preview ?? "No result or effect recorded"}</dd>
                          </div>
                        </dl>
                      </span>
                    </label>
                  );
                })}
              </div>
              <nav aria-label="Action pages" className="requirement-action-guided__pagination">
                <button disabled={busy || page === 0} onClick={() => setPage(page - 1)}>
                  Previous actions
                </button>
                <button
                  disabled={busy || (page + 1) * 20 >= filteredCandidates.length}
                  onClick={() => setPage(page + 1)}
                >
                  Next actions
                </button>
              </nav>
            </div>
          )}
        </>
      )}

      <footer className="requirement-action-guided__footer">
        <button
          disabled={busy || requirementIndex === 0}
          onClick={() => setRequirementIndex(requirementIndex - 1)}
        >
          Previous requirement
        </button>
        <button
          disabled={busy || requirementIndex >= currentReview.requirements.length - 1}
          onClick={() => setRequirementIndex(requirementIndex + 1)}
        >
          Next requirement
        </button>
        <button disabled={!complete || busy} onClick={() => void submit()}>
          Create unconfirmed proposal
        </button>
      </footer>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
