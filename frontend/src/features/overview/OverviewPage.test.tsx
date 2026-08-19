import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CodexSession } from "../../shared/api/contracts";
import { OverviewPage, sessionsPerDay } from "./OverviewPage";

const NOW = new Date("2026-08-19T12:00:00Z");

function session(startedAt: string, provider = "codex"): CodexSession {
  return {
    session_id: "a".repeat(64), installation_id: "b".repeat(64), project_id: "c".repeat(64), provider,
    provider_version: "1", adapter_version: "1", source_schema_version: "1", started_at: startedAt, ended_at: null,
    terminal_state: "unknown", events_complete: false, project_display_name: "Example", session_display_name: "Example session",
    project_display_name_origin: "provider", session_display_name_origin: "provider", project_manual_label_revision: 0, session_manual_label_revision: 0,
  } as unknown as CodexSession;
}

describe("OverviewPage", () => {
  it("buckets sessions per day with today on the right", () => {
    const counts = sessionsPerDay([session("2026-08-19T08:00:00Z"), session("2026-08-19T09:00:00Z"), session("2026-08-18T10:00:00Z"), session("2026-06-01T00:00:00Z")], 30, NOW);
    expect(counts.length).toBe(30);
    expect(counts[29]).toBe(2);
    expect(counts[28]).toBe(1);
    expect(counts.reduce((a, b) => a + b, 0)).toBe(3);
  });

  it("shows the four tiles from the app's own endpoints and suggests what to do next", async () => {
    const navigate = vi.fn();
    const transport = {
      getOnboardingStatus: vi.fn(async () => ({
        contract_version: "onboarding.v1" as const, any_installed: true, needs_onboarding: false, refresh_interval_seconds: 600,
        last_refresh_at: "2026-08-19T11:00:00Z", last_refresh_error: false, claude_home_override_supported: true,
        providers: [
          { provider: "codex" as const, installed: true, signal: "codex_cli_on_path" as const, consent_active: true, indexed_sessions: 62, transcript_files: null },
          { provider: "claude_code" as const, installed: true, signal: "claude_transcript_root" as const, consent_active: false, indexed_sessions: 0, transcript_files: 200 },
        ],
      })),
      listCodexSessions: vi.fn(async () => ({ limit: 100, offset: 0, sessions: [session("2026-08-19T08:00:00Z"), session("2026-08-17T08:00:00Z", "claude_code")] })),
      getCalibrationSample: vi.fn(async () => ({ contract_version: "calibration.v1", frozen_at: "2026-08-19T00:00:00Z", metric_keys: ["a", "b", "c"], members: [{ session_id: "d".repeat(64), project_id: "c".repeat(64), provider: "codex", project_display_name: null, session_display_name: null, started_at: "2026-08-01T00:00:00Z", rated_metric_keys: ["a", "b", "c"] }, { session_id: "e".repeat(64), project_id: "c".repeat(64), provider: "codex", project_display_name: null, session_display_name: null, started_at: "2026-08-02T00:00:00Z", rated_metric_keys: [] }] }) as never),
      getModelJudgeAgreement: vi.fn(async () => ({ contract_version: "model-judge.v1" as const, model_alias: "orca27b-iq3m", judged_sessions: 62, metrics: [{ metric_key: "a", pairs: 1, agreement_rate: 1, cohen_kappa: null, state: "insufficient_data", reason: null }], caveat: "c" }) as never),
      getLocalModels: vi.fn(async () => ({ contract_version: "local-models.v1" as const, runtime_available: true, storage_root: "D:/x", downloads: [], hardware: { gpu_name: "Example GPU", gpu_memory_mb: 16384, gpu_memory_free_mb: 4096, ram_mb: 32768, llama_server_path: "x", llama_server_version: "b1" }, models: [] })),
      getPromptCheckHistory: vi.fn(async () => ({ contract_version: "prompt-check.v1" as const, limit: 60, offset: 0, checks: [] })),
    };
    render(<OverviewPage navigate={navigate} now={() => NOW} transport={transport} />);
    await screen.findByText("62");
    expect(screen.getByText(/Codex 62/)).toBeTruthy();
    expect(screen.getByText("1/2")).toBeTruthy();
    expect(screen.getByText(/orca27b-iq3m judged 62 sessions/)).toBeTruthy();
    expect(screen.getByText("none active")).toBeTruthy();
    expect(screen.getByText(/not loaded yet/)).toBeTruthy();
    expect(screen.getByText(/No local model is active/)).toBeTruthy();
    expect(screen.getByText(/Rate sessions blind/)).toBeTruthy();
    expect(screen.getByRole("img", { name: /Sessions per day/ })).toBeTruthy();
    fireEvent.click(screen.getByText(/No local model is active/));
    expect(navigate).toHaveBeenCalledWith({ name: "models" });
    fireEvent.click(screen.getByText("Prompt checks").closest("button") as HTMLButtonElement);
    expect(navigate).toHaveBeenCalledWith({ name: "prompt_checks" });
  });
});
