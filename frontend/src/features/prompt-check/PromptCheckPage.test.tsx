import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PromptCheckRecord, PromptCheckResult } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { PromptCheckPage, shortName } from "./PromptCheckPage";

const CHECK = "c".repeat(64);

function reading(key: string, value: number | null, extra: Partial<PromptCheckResult["metrics"][number]> = {}): PromptCheckResult["metrics"][number] {
  return {
    key,
    display_name: shortName(key),
    description: "",
    state: value === null ? "unknown" : "known",
    value,
    numerator: value === null ? null : Math.round(value * 3),
    denominator: value === null ? null : 3,
    higher_is_better: true,
    explanation_code: value === null ? "constraints_unobserved" : "cues",
    cues: value === null ? [] : [{ code: "task.action", label: "what to do", status: "detected", count: 1 }, { code: "task.outcome", label: "the intended result", status: "missing", count: 0 }],
    ...extra,
  };
}

function result(overrides: Partial<PromptCheckResult> = {}): PromptCheckResult {
  return {
    contract_version: "prompt-check.v1" as const,
    check_id: CHECK,
    created_at: "2026-08-19T12:00:00Z",
    provider: "other",
    agent_model: null,
    metrics: [
      reading("prompt.task_definition_coverage", 2 / 3),
      reading("prompt.problem_evidence_quality", null),
      reading("prompt.context_sufficiency", 1 / 3),
      reading("prompt.constraint_precision", null),
      reading("prompt.acceptance_testability", 1),
      reading("prompt.deliverable_contract", 0),
    ],
    context: {
      task_type: "implement", language: "en", prompt_chars: 120, prompt_words: 20, sentence_count: 2, bullet_count: 0, question_count: 0,
      file_references: 1, code_identifiers: 2, urls: 0, prior_context_supplied: 1, depends_on_prior_context: true, verification_requested: false,
      missing_elements: ["how the result should be verified (tests, build, inspection)"],
    },
    commentary: {
      state: "ok",
      model_alias: "orca27b-iq3m",
      prompt_version: "prompt-check-commentary-v1",
      findings: [{ aspect: "acceptance", severity: "high", why: "No done-when.", suggestion: "Say which test must pass." }],
      reformulated_prompt: "Add retries to the uploader in client.py; done when pytest passes.",
      reformulated_elements: [{ element: "acceptance", original: null, suggested: "Done when pytest tests/test_upload.py passes." }],
      notes: null,
      caveat: "Commentary and rewrites come from a local model; they are suggestions, not metrics, and may be wrong.",
    },
    summary: "Prompt check - Task definition: 2/3 (missing: the intended result).",
    engine_version: "coaching-rules-en-pl-2",
    rubric_version: "coaching-observables-rubric-2",
    dashboard_path: `/prompt-checks/${CHECK}`,
    other_metric_families_note: "Collaboration, logic and outcome metrics need the agent's replies.",
    ...overrides,
  };
}

function record(): PromptCheckRecord {
  const r = result();
  return {
    check_id: CHECK, created_at: r.created_at, provider: "claude_code", agent_model: "claude-opus-5", language: "en", task_type: "implement",
    prompt_chars: 120, prior_message_count: 1, depends_on_prior_context: true, verification_requested: false, metrics: r.metrics,
    commentary_state: "ok", commentary_model_alias: "orca27b-iq3m", prompt_fingerprint: "f".repeat(64),
  };
}

describe("PromptCheckPage", () => {
  it("checks a pasted prompt with earlier turns and shows cues, commentary, reformulation and history", async () => {
    const checkPrompt = vi.fn(async (_request: { prompt: string; prior_messages?: { role: string; content: string }[] | null; want_commentary?: boolean }) => result());
    const transport = {
      checkPrompt,
      getPromptCheckHistory: vi.fn(async () => ({ contract_version: "prompt-check.v1" as const, checks: [record()], limit: 60, offset: 0 })),
      getPromptCheck: vi.fn(async () => record()),
    };
    const navigate = vi.fn();
    render(<PromptCheckPage navigate={navigate} transport={transport} />);
    await screen.findByText("Your checks over time");
    fireEvent.change(screen.getByLabelText("Prompt to check"), { target: { value: "Add retries to the uploader" } });
    fireEvent.change(screen.getByLabelText("Earlier turns"), { target: { value: "user: we looked at it yesterday\nassistant: the loop is in client.py" } });
    fireEvent.click(screen.getByRole("button", { name: "Check prompt" }));
    await waitFor(() => expect(checkPrompt).toHaveBeenCalledTimes(1));
    const request = checkPrompt.mock.calls[0][0];
    expect(request.prompt).toBe("Add retries to the uploader");
    expect(request.prior_messages).toEqual([{ role: "user", content: "we looked at it yesterday" }, { role: "assistant", content: "the loop is in client.py" }]);
    expect(request.want_commentary).toBe(true);
    await screen.findByText("Result");
    expect(screen.getAllByText(/the intended result/).length).toBeGreaterThan(0);
    expect(screen.getByText("Say which test must pass.")).toBeTruthy();
    expect(screen.getByText(/Add retries to the uploader in client.py; done when pytest passes./)).toBeTruthy();
    expect(screen.getByText(/model output, not a metric/)).toBeTruthy();
    expect(screen.getByRole("img", { name: "Prompt metric radar" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Prompt metric trend across checks" })).toBeTruthy();
    expect(screen.getByText(/claude_code · claude-opus-5/)).toBeTruthy();
  });

  it("explains a missing model and hides itself when the feature is unavailable", async () => {
    const transport = {
      checkPrompt: vi.fn(async () => result({ commentary: { state: "no_active_model", model_alias: null, prompt_version: "v", findings: [], reformulated_prompt: null, reformulated_elements: [], notes: null, caveat: "c" } })),
      getPromptCheckHistory: vi.fn(async () => ({ contract_version: "prompt-check.v1" as const, checks: [], limit: 60, offset: 0 })),
      getPromptCheck: vi.fn(),
    };
    render(<PromptCheckPage navigate={vi.fn()} transport={transport} />);
    await screen.findByText(/No check yet/);
    fireEvent.change(screen.getByLabelText("Prompt to check"), { target: { value: "Refactor the parser" } });
    fireEvent.click(screen.getByRole("button", { name: "Check prompt" }));
    await screen.findByText(/No local model is active/);

    const unavailable = {
      checkPrompt: vi.fn(),
      getPromptCheckHistory: vi.fn(async () => { throw new TransportError("Local API request failed (404)", 404); }),
      getPromptCheck: vi.fn(),
    };
    render(<PromptCheckPage navigate={vi.fn()} transport={unavailable} />);
    await screen.findByText(/not available in this runtime/);
  });
});
