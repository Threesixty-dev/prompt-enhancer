import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ClaimGroundingLinkReviewPanel } from "./ClaimGroundingLinkReviewPanel";

const S = "1".repeat(64);
const RUN = "2".repeat(64);
const WINDOW = "3".repeat(64);
const CENSUS = "4".repeat(64);
const CENSUS_FINGERPRINT = "5".repeat(64);
const MANIFEST = "6".repeat(64);
const CANDIDATE = "7".repeat(64);
const CHECK = "8".repeat(64);

const census = (overrides: Record<string, unknown> = {}) => ({
  census_id: CENSUS,
  session_id: S,
  source_run_id: RUN,
  source_window_fingerprint: WINDOW,
  census_fingerprint: CENSUS_FINGERPRINT,
  manifest_fingerprint: MANIFEST,
  candidate_count: 1,
  ...overrides,
});
const candidates = (overrides: Record<string, unknown> = {}) => ({
  session_id: S,
  census_id: CENSUS,
  source_run_id: RUN,
  source_window_fingerprint: WINDOW,
  census_fingerprint: CENSUS_FINGERPRINT,
  manifest_fingerprint: MANIFEST,
  observed_set_fingerprint: "9".repeat(64),
  source_schema_version: "synthetic-v1",
  text_adapter_version: "synthetic-v1",
  observed_set_schema_version: "claim-grounding-observed-set-v1",
  observed_set_policy_version: "native-reviewed-claim-link-coverage-v1",
  material_candidates: [{ candidate_id: CANDIDATE, message_id: "a".repeat(64), message_sequence: 1, clause_index: 0 }],
  observed_checks: [{
    source_reference_id: CHECK, observed_sequence: 1, provider: "codex", check_kind: "test",
    outcome: "passed", provider_execution_status: "completed", exit_code: 0,
    source_completion_schema_version: "observed-check-completion-v1",
    outcome_interpreter_version: "pytest-exit-status-v1", classifier_version: "local-command-rules-v1",
    normalizer_version: "strict-shell-free-v2", rule_id: "test.pytest",
  }],
  proposal_only: true, measured: false, metric_authority_established: false, content_persisted: false,
  ...overrides,
});
const review = (expiresAt = new Date(Date.now() + 60_000).toISOString()) => ({
  ...candidates(), candidate_id: CANDIDATE, review_receipt_id: "b".repeat(64),
  review_fingerprint: "c".repeat(64), review_expires_at: expiresAt,
  claim_clause: "Synthetic old claim prose that must disappear.",
  observed_checks: [{ source_reference_id: CHECK, observed_sequence: 1, outcome: "passed", tool_name: "pytest", invocation_preview: "pytest -q", effect_preview: "exit 0" }],
});
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};
const transport = (overrides: Record<string, unknown> = {}) => ({
  getUserPresenceCapability: vi.fn().mockResolvedValue({ confirmation_available: true, mode: "native_bridge_bound_token" }),
  getClaimGroundingLinkCandidates: vi.fn().mockResolvedValue(candidates()),
  beginClaimGroundingLinkReview: vi.fn().mockResolvedValue(review()),
  ...overrides,
});
const open = () => fireEvent.click(screen.getByText("Link a material claim to observed checks"));

afterEach(() => vi.useRealTimers());

describe("ClaimGroundingLinkReviewPanel adversarial lifecycle", () => {
  it.each(["source", "census", "transport"])("never reveals an abort-ignoring old native preview after close, reopen, and %s replacement", async (replacement) => {
    const pending = deferred<any>();
    const local = transport({ beginClaimGroundingLinkReview: vi.fn().mockReturnValue(pending.promise) });
    const view = render(<ClaimGroundingLinkReviewPanel sessionId={S} sourceRunId={RUN} census={census()} transport={local as any} />);
    open();
    fireEvent.click(await screen.findByLabelText(/Message 1, clause 1/i));
    fireEvent.click(screen.getByRole("button", { name: "Begin native link preview" }));
    await waitFor(() => expect(local.beginClaimGroundingLinkReview).toHaveBeenCalledTimes(1));
    open();
    await waitFor(() => expect(screen.getByText("Link a material claim to observed checks").parentElement).not.toHaveAttribute("open"));
    open();
    const nextTransport = replacement === "transport" ? transport() : local;
    const nextRun = replacement === "source" ? "d".repeat(64) : RUN;
    const nextCensus = replacement === "census"
      ? census({ census_fingerprint: "d".repeat(64) })
      : census({ source_run_id: nextRun });
    view.rerender(<ClaimGroundingLinkReviewPanel sessionId={S} sourceRunId={nextRun} census={nextCensus} transport={nextTransport as any} />);
    await act(async () => pending.resolve(review()));
    expect(screen.queryByText("Synthetic old claim prose that must disappear.")).toBeNull();
  });

  it("expires a displayed preview and leaves an explicit usable restart path", async () => {
    const local = transport({
      beginClaimGroundingLinkReview: vi.fn().mockImplementation(() =>
        Promise.resolve(review(new Date(Date.now() + 60_000).toISOString())),
      ),
    });
    render(<ClaimGroundingLinkReviewPanel sessionId={S} sourceRunId={RUN} census={census()} transport={local as any} />);
    open();
    fireEvent.click(await screen.findByLabelText(/Message 1, clause 1/i));
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Begin native link preview" }));
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText("Synthetic old claim prose that must disappear.")).toBeInTheDocument();
    await act(async () => vi.advanceTimersByTimeAsync(60_001));
    expect(screen.getAllByText(/Link review expired/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("Synthetic old claim prose that must disappear.")).toBeNull();
    expect(screen.getAllByText(/Link review expired/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Begin native link preview" })).toBeEnabled();
  });

  it("keeps content-free candidate selection available without native capability but disables Begin", async () => {
    const local = transport({
      getUserPresenceCapability: vi.fn().mockResolvedValue({ confirmation_available: false, mode: "unavailable" }),
    });
    render(<ClaimGroundingLinkReviewPanel sessionId={S} sourceRunId={RUN} census={census()} transport={local as any} />);
    open();
    const choice = await screen.findByLabelText(/Message 1, clause 1/i);
    fireEvent.click(choice);
    expect(screen.getByText(/Native confirmation is unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Begin native link preview" })).toBeDisabled();
    expect(local.beginClaimGroundingLinkReview).not.toHaveBeenCalled();
  });
});
