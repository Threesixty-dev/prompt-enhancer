import { useEffect, useMemo, useRef, useState } from "react";
import type {
  PromptEnhancerTransport,
  RequirementPlanEvidenceContract,
  RequirementPlanGuidedAuthoringReview,
  RequirementPlanProposal,
} from "../../shared/api/contracts";
import { parseRequirementPlanGuidedAuthoringProposal, parseRequirementPlanGuidedAuthoringReview } from "../../shared/api/requirementPlanGuidedAuthoringContract";
import "./RequirementPlanGuidedAuthoring.css";

type Choice = {
  classification?:
    "active_requirement" | "excluded_from_active_requirement_denominator";
  disposition?: "linked" | "not_linked" | "pending";
  reason?:
    | "not_requirement"
    | "superseded"
    | "withdrawn"
    | "duplicate"
    | "out_of_scope"
    | "already_satisfied_or_closed";
  basis?: string;
  links: Set<string>;
};
const key = (c: { message_sequence: number; clause_index: number }) =>
  `${c.message_sequence}:${c.clause_index}`;
const coord = (value: string) => {
  const [message_sequence, clause_index] = value.split(":").map(Number);
  return { message_sequence, clause_index };
};
const after = (left: string, right: string) => {
  const a = coord(left), b = coord(right);
  return a.message_sequence > b.message_sequence || (a.message_sequence === b.message_sequence && a.clause_index > b.clause_index);
};
const reasons = [
  "not_requirement",
  "superseded",
  "withdrawn",
  "duplicate",
  "out_of_scope",
  "already_satisfied_or_closed",
] as const;
const idempotency = () =>
  `requirement-plan-guided-${crypto.randomUUID().replaceAll("-", "")}`;

export function RequirementPlanGuidedAuthoring({
  sessionId,
  contract,
  transport,
  enabled,
  onCreated,
  onClosed,
}: {
  sessionId: string;
  contract: RequirementPlanEvidenceContract;
  transport: Pick<
    PromptEnhancerTransport,
    | "reviewRequirementPlanGuidedAuthoring"
    | "submitRequirementPlanGuidedAuthoring"
  >;
  enabled: boolean;
  onCreated: (proposal: RequirementPlanProposal) => void;
  onClosed: () => void;
}) {
  const [review, setReview] =
    useState<RequirementPlanGuidedAuthoringReview | null>(null);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [index, setIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [linkQuery, setLinkQuery] = useState("");
  const [basisQuery, setBasisQuery] = useState("");
  const [linkPage, setLinkPage] = useState(0);
  const [basisPage, setBasisPage] = useState(0);
  const abort = useRef<AbortController | null>(null);
  const owner = JSON.stringify([contract, enabled]);
  const clear = () => {
    abort.current?.abort();
    abort.current = null;
    setBusy(false);
    setReview(null);
    setChoices({});
    setIndex(0);
    setLinkQuery(""); setBasisQuery(""); setLinkPage(0); setBasisPage(0); setError("");
  };
  useEffect(
    () => clear,
    [
      sessionId,
      owner, transport,
    ],
  );
  useEffect(() => {
    if (!review) return;
    const at =
      Math.min(
        Date.parse(review.review_context_expires_at),
        Date.parse(review.authoring_receipt_expires_at),
      ) - Date.now();
    const timer = window.setTimeout(
      () => {
        clear();
        onClosed();
        setError(
          "The guided authoring receipt expired. Open a fresh local review.",
        );
      },
      Math.min(Math.max(0, at), 2_147_483_647),
    );
    return () => window.clearTimeout(timer);
  }, [review]);
  const candidates = review?.candidate_clauses ?? [];
  const users = candidates.filter((c) => c.candidate_kind === "user_clause");
  const plans = candidates.filter((c) => c.candidate_kind === "plan");
  const current = candidates[index];
  const picker = <T extends { text: string }>(items: T[], query: string, page: number) => items.filter((item) => item.text.toLowerCase().includes(query.toLowerCase())).slice(page * 20, page * 20 + 20);
  const update = (k: string, value: Partial<Choice>) =>
    setChoices((old) => ({
      ...old,
      [k]: { ...old[k], links: old[k]?.links ?? new Set(), ...value },
    }));
  const complete = useMemo(
    () =>
      users.every((u) => {
        const c = choices[key(u)];
        const validLinks = [...(c?.links ?? [])].every((link) =>
          plans.some(
            (p) =>
              key(p) === link &&
              p.message_sequence >= u.message_sequence &&
              choices[link]?.classification === "active_requirement",
          ),
        );
        return c?.classification === "active_requirement"
          ? c.disposition !== undefined &&
              (c.disposition !== "linked" || (c.links.size > 0 && validLinks))
          : c?.classification ===
              "excluded_from_active_requirement_denominator" &&
              c.reason !== undefined && c.reason !== ("" as never) &&
              (!["superseded", "withdrawn", "duplicate"].includes(c.reason) ||
                (c.basis !== undefined && (c.reason === "duplicate"
                  ? choices[c.basis]?.classification === "active_requirement" && c.basis !== key(u)
                  : after(c.basis, key(u)))));
      }) && plans.every((p) => choices[key(p)]?.classification !== undefined),
    [choices, users, plans],
  );
  async function open() {
    if (!enabled || !transport.reviewRequirementPlanGuidedAuthoring) return;
    clear();
    const controller = new AbortController();
    abort.current = controller;
    setBusy(true);
    setError("");
    try {
      const next = await transport.reviewRequirementPlanGuidedAuthoring(
        sessionId,
        contract,
        {
          expected_source_run_id: contract.expected_source_run_id,
          source_window_fingerprint: contract.source_window_fingerprint,
          manifest_fingerprint: contract.source_manifest.manifest_fingerprint,
          expected_predecessor_confirmation_id:
            contract.expected_predecessor_confirmation_id,
          confirmation: "open_exact_local_requirement_plan_guided_authoring",
        },
        controller.signal,
      );
      const validated = parseRequirementPlanGuidedAuthoringReview(next, { sessionId, contract });
      if (!controller.signal.aborted) setReview(validated);
    } catch {
      if (!controller.signal.aborted)
        setError(
          "The exact local guided-authoring review could not be opened.",
        );
    } finally {
      if (abort.current === controller && !controller.signal.aborted) setBusy(false);
    }
  }
  async function submit() {
    if (!review || !complete || !transport.submitRequirementPlanGuidedAuthoring)
      return;
    const included = plans.filter(
      (p) => choices[key(p)]?.classification === "active_requirement",
    );
    const planIndex = new Map(included.map((p, i) => [key(p), i]));
    const requirements = users
      .filter((u) => choices[key(u)]?.classification === "active_requirement")
      .map((u) => {
        const c = choices[key(u)]!;
        return {
          coordinate: coord(key(u)),
          disposition: c.disposition!,
          plan_indexes: [...c.links]
            .map((x) => planIndex.get(x)!)
            .sort((a, b) => a - b),
        };
      });
    const excluded_user_clauses = users
      .filter(
        (u) =>
          choices[key(u)]?.classification ===
          "excluded_from_active_requirement_denominator",
      )
      .map((u) => {
        const c = choices[key(u)]!;
        return {
          coordinate: coord(key(u)),
          reason: c.reason!,
          basis_coordinate: c.basis ? coord(c.basis) : null,
        };
      });
    const controller = new AbortController();
    abort.current = controller;
    setBusy(true);
    try {
      const result = await transport.submitRequirementPlanGuidedAuthoring(
        sessionId,
        {
          expected_source_run_id: review.source_run_id,
          source_window_fingerprint: review.source_window_fingerprint,
          manifest_fingerprint: review.manifest_fingerprint,
          expected_predecessor_confirmation_id:
            review.expected_predecessor_confirmation_id,
          authoring_receipt_id: review.authoring_receipt_id,
          requirements,
          excluded_user_clauses,
          plan_items: included.map((p) => coord(key(p))),
          complete_user_clause_classification_acknowledged: true,
        },
        idempotency(),
        controller.signal,
      );
      const validated = parseRequirementPlanGuidedAuthoringProposal(result, { sessionId, command: { expected_source_run_id: review.source_run_id, source_window_fingerprint: review.source_window_fingerprint, manifest_fingerprint: review.manifest_fingerprint, expected_predecessor_confirmation_id: review.expected_predecessor_confirmation_id, authoring_receipt_id: review.authoring_receipt_id, requirements, excluded_user_clauses, plan_items: included.map((p) => coord(key(p))), complete_user_clause_classification_acknowledged: true } });
      if (!controller.signal.aborted) {
        clear();
        onCreated(validated.proposal);
      }
    } catch {
      if (!controller.signal.aborted) {
        clear();
        setError(
          "The proposal result is uncertain. Local text and draft were cleared; check proposal history, then start a fresh review if needed.",
        );
      }
    } finally {
      if (abort.current === controller && !controller.signal.aborted) setBusy(false);
    }
  }
  if (!review)
    return (
      <section className="requirement-plan-guided">
        <h4>Guided local authoring</h4>
        <p>
          Create an unconfirmed proposal directly in this local window. It calls
          no model and never confirms metric authority.
        </p>
        <button
          type="button"
          disabled={!enabled || busy}
          onClick={() => void open()}
        >
          Open guided clause review
        </button>
        {busy && <button type="button" onClick={() => { clear(); onClosed(); }}>Close and clear</button>}
        {error && <p role="alert">{error}</p>}
      </section>
    );
  const c = current;
  const currentKey = c && key(c);
  const choice = currentKey ? choices[currentKey] : undefined;
  const basisCandidates = users.filter((u) => {
    const k = key(u);
    if (!choice?.reason) return false;
    if (choice.reason === "duplicate")
      return (
        choices[k]?.classification === "active_requirement" && k !== currentKey
      );
    return (
      ["superseded", "withdrawn"].includes(choice.reason) && after(k, currentKey!)
    );
  });
  const selectedBasis = basisCandidates.find((item) => key(item) === choice?.basis);
  return (
    <section
      className="requirement-plan-guided"
      aria-label="Guided requirement plan authoring"
    >
      <header>
        <h4>Guided local authoring</h4>
        <span>
          {index + 1} of {candidates.length}
        </span>
        <button type="button" onClick={() => { clear(); onClosed(); }}>
          Close and clear
        </button>
      </header>
      {c && (
        <article>
          <strong>
            {c.candidate_kind === "plan" ? "PLAN clause" : "User clause"} —
            message {c.message_sequence}, clause {c.clause_index}
          </strong>
          <blockquote>{c.text}</blockquote>
          {c.candidate_kind === "plan" ? (
            <fieldset><legend>PLAN membership</legend><label><input name={`plan-${currentKey}`} type="radio" checked={choice?.classification === "active_requirement"} onChange={() => update(currentKey!, { classification: "active_requirement" })}/> Include</label><label><input name={`plan-${currentKey}`} type="radio" checked={choice?.classification === "excluded_from_active_requirement_denominator"} onChange={() => update(currentKey!, { classification: "excluded_from_active_requirement_denominator" })}/> Omit</label></fieldset>
          ) : (
            <>
              <fieldset>
                <legend>Classification</legend>
                <label>
                  <input
                    name={`classification-${currentKey}`} type="radio"
                    checked={choice?.classification === "active_requirement"}
                    onChange={() =>
                      update(currentKey!, {
                        classification: "active_requirement",
                      })
                    }
                  />{" "}
                  Active requirement
                </label>
                <label>
                  <input
                    name={`classification-${currentKey}`} type="radio"
                    checked={
                      choice?.classification ===
                      "excluded_from_active_requirement_denominator"
                    }
                    onChange={() =>
                      update(currentKey!, {
                        classification:
                          "excluded_from_active_requirement_denominator",
                      })
                    }
                  />{" "}
                  Exclude
                </label>
              </fieldset>
              {choice?.classification === "active_requirement" && (
                <fieldset>
                  <legend>Disposition</legend>
                  {["linked", "not_linked", "pending"].map((d) => (
                    <label key={d}>
                      <input
                        name={`disposition-${currentKey}`} type="radio"
                        checked={choice.disposition === d}
                        onChange={() =>
                          update(currentKey!, {
                            disposition: d as Choice["disposition"],
                            links: d === "linked" ? choice.links : new Set(),
                          })
                        }
                      />
                      {d.replaceAll("_", " ")}
                    </label>
                  ))}
                  {choice.disposition === "linked" &&
                    picker(plans
                      .filter(
                        (p) =>
                          choices[key(p)]?.classification ===
                            "active_requirement" &&
                          p.message_sequence >= c.message_sequence,
                      ), linkQuery, linkPage)
                      .map((p) => (
                        <label key={key(p)}>
                          <input
                            type="checkbox"
                            aria-label={`Link message ${p.message_sequence}, clause ${p.clause_index}`}
                            checked={choice.links.has(key(p))}
                            onChange={(e) => {
                              const links = new Set(choice.links);
                              e.currentTarget.checked
                                ? links.add(key(p))
                                : links.delete(key(p));
                              update(currentKey!, { links });
                            }}
                          />{" "}
                          Link message {p.message_sequence}, clause{" "}
                          {p.clause_index}<small>{p.text}</small>
                        </label>
                      ))}
                  {choice.disposition === "linked" && <><label>Search PLAN clauses<input aria-label="Search PLAN clauses" value={linkQuery} onChange={(e) => { setLinkQuery(e.currentTarget.value); setLinkPage(0); }} /></label><button type="button" disabled={linkPage === 0} onClick={() => setLinkPage((p) => p - 1)}>Previous PLAN page</button><button type="button" disabled={(linkPage + 1) * 20 >= plans.filter((p) => choices[key(p)]?.classification === "active_requirement" && p.message_sequence >= c.message_sequence && p.text.toLowerCase().includes(linkQuery.toLowerCase())).length} onClick={() => setLinkPage((p) => p + 1)}>Next PLAN page</button></>}
                </fieldset>
              )}
              {choice?.classification ===
                "excluded_from_active_requirement_denominator" && (
                <fieldset>
                  <legend>Exclusion reason</legend>
                  <select
                    aria-label="Exclusion reason"
                    value={choice.reason ?? ""}
                    onChange={(e) =>
                      update(currentKey!, {
                        reason: e.currentTarget.value as Choice["reason"],
                        basis: undefined,
                      })
                    }
                  >
                    <option value="">Choose a reason</option>
                    {reasons.map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </select>
                  {choice.reason &&
                    ["superseded", "withdrawn", "duplicate"].includes(
                      choice.reason,
                    ) && (<>
                      <select
                        aria-label="Exclusion basis"
                        value={choice.basis ?? ""}
                        onChange={(e) =>
                          update(currentKey!, {
                            basis: e.currentTarget.value || undefined,
                          })
                        }
                      >
                        <option value="">Choose required basis</option>
                        {selectedBasis !== undefined && !picker(basisCandidates, basisQuery, basisPage).some((item) => key(item) === key(selectedBasis)) && <option value={key(selectedBasis)}>message {selectedBasis.message_sequence}, clause {selectedBasis.clause_index} — {selectedBasis.text}</option>}
                        {picker(basisCandidates, basisQuery, basisPage).map((b) => (
                          <option key={key(b)} value={key(b)}>
                            message {b.message_sequence}, clause{" "}
                            {b.clause_index} — {b.text}
                          </option>
                        ))}
                      </select>
                      {selectedBasis !== undefined && <p>Selected basis: message {selectedBasis.message_sequence}, clause {selectedBasis.clause_index} — {selectedBasis.text}</p>}
                      <label>Search basis clauses<input aria-label="Search basis clauses" value={basisQuery} onChange={(e) => { setBasisQuery(e.currentTarget.value); setBasisPage(0); }} /></label><button type="button" disabled={basisPage === 0} onClick={() => setBasisPage((p) => p - 1)}>Previous basis page</button><button type="button" disabled={(basisPage + 1) * 20 >= basisCandidates.filter((b) => b.text.toLowerCase().includes(basisQuery.toLowerCase())).length} onClick={() => setBasisPage((p) => p + 1)}>Next basis page</button></>
                    )}
                </fieldset>
              )}
            </>
          )}
        </article>
      )}
      <footer>
        <button
          type="button"
          disabled={busy || index === 0}
          onClick={() => setIndex((n) => n - 1)}
        >
          Back
        </button>
        <button
          type="button"
          disabled={busy || index >= candidates.length - 1}
          onClick={() => setIndex((n) => n + 1)}
        >
          Next
        </button>
        <button
          type="button"
          disabled={busy || !complete}
          onClick={() => void submit()}
        >
          Create unconfirmed proposal
        </button>
      </footer>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
