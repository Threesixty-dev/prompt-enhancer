import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SessionJudgments } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { ModelJudgePane } from "./ModelJudgePane";

const SESSION = "a".repeat(64);

function judgments(overrides: Partial<SessionJudgments> = {}): SessionJudgments {
  return {
    contract_version: "model-judge.v1" as SessionJudgments["contract_version"],
    session_id: SESSION,
    active_model_alias: "orca27b-iq3m",
    questions: {
      "prompt.task_definition_coverage": "Did the person say clearly what they wanted done?",
      "prompt.context_sufficiency": "Did the prompts carry the context the agent needed?",
      "outcome.verification_strategy_adequacy": "Was the work checked before it was called done?",
    },
    judgments: [
      { session_id: SESSION, metric_key: "prompt.task_definition_coverage", label: "high", model_alias: "orca27b-iq3m", model_identity: "x.gguf", prompt_version: "judge-v1", window_fingerprint: "b".repeat(64), judged_at: "2026-08-19T10:00:00Z" },
      { session_id: SESSION, metric_key: "prompt.context_sufficiency", label: "medium", model_alias: "orca27b-iq3m", model_identity: "x.gguf", prompt_version: "judge-v1", window_fingerprint: "b".repeat(64), judged_at: "2026-08-19T10:00:00Z" },
      { session_id: SESSION, metric_key: "outcome.verification_strategy_adequacy", label: "cannot_judge", model_alias: "orca27b-iq3m", model_identity: "x.gguf", prompt_version: "judge-v1", window_fingerprint: "b".repeat(64), judged_at: "2026-08-19T10:00:00Z" },
    ],
    caveat: "Model judgments are labels from a local model, stored apart from metrics; they are never metric values.",
    ...overrides,
  };
}

describe("ModelJudgePane", () => {
  it("shows one label per question per model, apart from metrics, with the caveat", async () => {
    const transport = { getModelJudgments: vi.fn(async () => judgments()), judgeSessionWithModel: vi.fn() };
    render(<ModelJudgePane sessionId={SESSION} transport={transport} />);
    await screen.findByText("What the local model thinks of this session");
    expect(screen.getByText("orca27b-iq3m · active")).toBeTruthy();
    expect(screen.getByText("high")).toBeTruthy();
    expect(screen.getByText("medium")).toBeTruthy();
    expect(screen.getByText("cannot judge")).toBeTruthy();
    expect(screen.getByText(/never metric values/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Judge again" })).toBeTruthy();
  });

  it("offers to judge now when nothing is stored and a model is active, then reloads", async () => {
    let current = judgments({ judgments: [] });
    const judgeSessionWithModel = vi.fn(async () => {
      current = judgments();
      return { contract_version: "model-judge.v1" as const, session_id: SESSION, model_alias: "orca27b-iq3m", judgments: current.judgments, raw_valid: true };
    });
    const transport = { getModelJudgments: vi.fn(async () => current), judgeSessionWithModel };
    render(<ModelJudgePane sessionId={SESSION} transport={transport} />);
    await screen.findByText(/judges new sessions automatically/);
    fireEvent.click(screen.getByRole("button", { name: "Judge now" }));
    await waitFor(() => expect(judgeSessionWithModel).toHaveBeenCalledWith(SESSION));
    await screen.findByText("high");
    expect(screen.getByText("Judged by orca27b-iq3m.")).toBeTruthy();
  });

  it("renders nothing when the judge lane is not available", async () => {
    const transport = { getModelJudgments: vi.fn(async () => { throw new TransportError("Local API request failed (404)", 404); }) };
    const { container } = render(<ModelJudgePane sessionId={SESSION} transport={transport} />);
    await waitFor(() => expect(transport.getModelJudgments).toHaveBeenCalled());
    await waitFor(() => expect(container.querySelector(".model-judge-pane")).toBeNull());
  });
});
