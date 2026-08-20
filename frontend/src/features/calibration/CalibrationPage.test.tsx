import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CalibrationProgress,
  CalibrationRating,
  CalibrationSample,
  RatingSubmission,
  SessionTranscript,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { CalibrationPage, safeCalibrationSample } from "./CalibrationPage";

const SESSION_A = "a".repeat(64);
const SESSION_B = "b".repeat(64);
const PROJECT = "c".repeat(64);
const METRICS = ["prompt.task_definition_coverage", "prompt.context_sufficiency", "outcome.verification_strategy_adequacy"];

function sample(rated: Record<string, string[]> = {}): CalibrationSample {
  return {
    contract_version: "calibration-ratings.v1" as const,
    sample_id: "d".repeat(64),
    sample_version: "calibration-sample-v1",
    created_at: "2026-03-01T09:00:00Z",
    target_size: 96,
    metric_keys: METRICS,
    members: [
      { position: 0, session_id: SESSION_A, provider: "claude_code", project_id: PROJECT, project_display_name: "example-app", session_display_name: "Add retries to the uploader", started_at: "2026-03-01T09:00:00Z", rated_metric_keys: rated[SESSION_A] ?? [] },
      { position: 1, session_id: SESSION_B, provider: "codex", project_id: PROJECT, project_display_name: "example-app", session_display_name: null, started_at: null, rated_metric_keys: rated[SESSION_B] ?? [] },
    ],
  };
}

function progress(rated: number): CalibrationProgress {
  return {
    contract_version: "calibration-ratings.v1" as const,
    sample_id: "d".repeat(64),
    sample_size: 2,
    rated_sessions: rated,
    rater_count: rated > 0 ? 1 : 0,
    metrics: METRICS.map((metric_key) => ({ metric_key, rated_sessions: rated, low: 0, medium: rated, high: 0, cannot_judge: 0 })),
  };
}

const transcript: SessionTranscript = {
  contract_version: "session-transcript.v1",
  provider: "claude_code",
  session_id: SESSION_A,
  title: "Add retries to the uploader",
  turns: [{ role: "user", text: "Please add a retry", at: "2026-03-01T09:00:00Z", tool_name: null, truncated: false }],
  truncated: false,
  turn_count: 1,
} as unknown as SessionTranscript;

describe("CalibrationPage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("validates the sample shape", () => {
    expect(safeCalibrationSample(sample())).toBe(true);
    expect(safeCalibrationSample({ ...sample(), contract_version: "other" })).toBe(false);
    expect(safeCalibrationSample({ ...sample(), members: [{ session_id: "nope" }] })).toBe(false);
  });

  it("lists the frozen sample, rates a session blind, and advances", async () => {
    let current = sample();
    const submitCalibrationRatings = vi.fn(async (_request: RatingSubmission) => {
      current = sample({ [SESSION_A]: METRICS });
      return progress(1);
    });
    const ratings: CalibrationRating[] = [];
    const transport = {
      getCalibrationSample: vi.fn(async (_raterLabel: string | null, _signal?: AbortSignal) => current),
      submitCalibrationRatings,
      getCalibrationRatings: vi.fn(async () => ratings),
      getCalibrationProgress: vi.fn(async () => progress(0)),
      getCalibrationExport: vi.fn(async () => ({ contract_version: "calibration-ratings.v1" as const, sample_id: "d".repeat(64), sample_version: "calibration-sample-v1", rating_version: "calibration-rating-v1", exported_at: "2026-03-01T10:00:00Z", rows: [] })),
      getSessionTranscript: vi.fn(async () => transcript),
    };
    render(<CalibrationPage transport={transport} />);

    await screen.findByText("Add retries to the uploader", { selector: ".calibration__item-title" });
    expect(screen.getByText(/2 sessions · frozen sample/)).toBeTruthy();
    // Rater name is required and stored locally.
    const rater = screen.getByLabelText("Rater name");
    fireEvent.change(rater, { target: { value: "Owner" } });
    fireEvent.blur(rater);
    expect(localStorage.getItem("prompt-enhancer.calibration.rater")).toBe("Owner");

    await waitFor(() => expect(transport.getCalibrationSample.mock.calls.map((call) => call[0])).toContain("Owner"));
    fireEvent.click(await screen.findByRole("button", { name: /Next unrated/ }));
    await screen.findByRole("heading", { level: 2, name: "Add retries to the uploader" });
    // The reader shows the session; no metric value for it is rendered anywhere.
    await waitFor(() => expect(transport.getSessionTranscript).toHaveBeenCalledWith(SESSION_A));
    expect(document.body.textContent).not.toMatch(/0\.\d\d/);

    fireEvent.click(screen.getByLabelText("Task definition").querySelector("input[value='high']") as HTMLInputElement);
    fireEvent.click(screen.getByLabelText("Context given").querySelector("input[value='cannot_judge']") as HTMLInputElement);
    fireEvent.click(screen.getByRole("button", { name: "Save and next" }));
    await waitFor(() => expect(submitCalibrationRatings).toHaveBeenCalledTimes(1));
    expect(submitCalibrationRatings.mock.calls[0][0]).toEqual({
      rater_label: "Owner",
      session_id: SESSION_A,
      ratings: { "prompt.task_definition_coverage": "high", "prompt.context_sufficiency": "cannot_judge" },
    });
    // Advances to the next unrated member (the Codex one, titled by its short id).
    await screen.findByRole("heading", { level: 2, name: `Session ${SESSION_B.slice(0, 8)}` });
  });

  it("explains an empty catalog and an unavailable runtime", async () => {
    const base = {
      submitCalibrationRatings: vi.fn(),
      getCalibrationRatings: vi.fn(async () => []),
      getCalibrationProgress: vi.fn(async () => progress(0)),
      getCalibrationExport: vi.fn(),
      getSessionTranscript: vi.fn(),
    };
    const { unmount } = render(
      <CalibrationPage transport={{ ...base, getCalibrationSample: vi.fn(async () => { throw new TransportError("empty", 409); }) }} />,
    );
    await screen.findByText(/No sessions are indexed yet/);
    unmount();
    render(
      <CalibrationPage transport={{ ...base, getCalibrationSample: vi.fn(async () => { throw new TransportError("nope", 404); }) }} />,
    );
    await screen.findByText(/not available in this runtime/);
  });

  it("gates the agent path on the allowance and confirms before annotating remotely", async () => {
    const agreement = {
      contract_version: "model-judge.v1",
      model_alias: null,
      judged_sessions: 0,
      metrics: [],
      caveat: "Judgments are opinions, never product metrics.",
    };
    let allowed = false;
    const setAnnotationAllowance = vi.fn(async (next: boolean) => {
      allowed = next;
      return { contract_version: "annotation.v1" as const, agent_allowed: allowed, note: "Whatever model the agent runs on will see that content." };
    });
    const annotateRemotely = vi.fn(async (_limit: number) => ({
      contract_version: "annotation.v1" as const,
      destination: "embedded central server (this machine)",
      submitted: 2,
      annotated: 2,
      model_identity: "orca27b-iq3m",
      stored_locally_as: "central:orca27b-iq3m",
    }));
    const transport = {
      getCalibrationSample: vi.fn(async () => sample()),
      submitCalibrationRatings: vi.fn(),
      getCalibrationRatings: vi.fn(async () => []),
      getCalibrationProgress: vi.fn(async () => progress(0)),
      getCalibrationExport: vi.fn(),
      getSessionTranscript: vi.fn(async () => transcript),
      getModelJudgeAgreement: vi.fn(async () => agreement),
      getModelJudgeSweep: vi.fn(async () => ({ contract_version: "model-judge.v1", running: false, total: 0, done: 0, failed: 0 })),
      getAnnotationAllowance: vi.fn(async () => ({ contract_version: "annotation.v1" as const, agent_allowed: allowed, note: "Whatever model the agent runs on will see that content." })),
      setAnnotationAllowance,
      getAnnotationMetaprompt: vi.fn(),
      annotateRemotely,
    } as never;

    render(<CalibrationPage transport={transport} />);
    await screen.findByText(/More ways to annotate/);

    // Allowance off: the toggle invites, no copy button yet.
    const toggle = screen.getByRole("button", { name: /Allow agent annotation/ });
    expect(screen.queryByRole("button", { name: /Copy agent instructions/ })).toBeNull();
    fireEvent.click(toggle);
    await screen.findByRole("button", { name: /Agent annotation is ON/ });
    expect(setAnnotationAllowance).toHaveBeenCalledWith(true);
    expect(screen.getByRole("button", { name: /Copy agent instructions/ })).toBeTruthy();

    // Annotate remotely: explicit confirm with the destination named before anything is sent.
    fireEvent.click(screen.getByRole("button", { name: /Annotate remotely/ }));
    expect(annotateRemotely).not.toHaveBeenCalled();
    await screen.findByText(/Destination: embedded central server \(this machine\)/);
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(annotateRemotely).toHaveBeenCalledWith(5));
    await screen.findByText(/Sent 2 sessions to embedded central server/);
    await screen.findByText("central:orca27b-iq3m");
  });
});
