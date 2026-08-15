import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  CodexSession,
  ModelEnsembleWatchSnapshot,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { ModelEnsembleOverlay } from "./ModelEnsembleOverlay";

async function settlePoll() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

afterEach(() => {
  Reflect.deleteProperty(window, "pywebview");
});

const PROJECT_A = "a".repeat(64);
const PROJECT_B = "b".repeat(64);
const SESSION_A = "1".repeat(64);
const SESSION_B = "2".repeat(64);

function catalogSession(
  projectId: string,
  sessionId: string,
  projectLabel: string,
  sessionLabel: string,
  startedAt: string,
): CodexSession {
  return {
    adapter_version: "example-adapter-v1",
    ended_at: null,
    events_complete: false,
    installation_id: "f".repeat(64),
    project_display_name: projectLabel,
    project_display_name_origin: "provider",
    project_id: projectId,
    project_manual_label_revision: 0,
    provider: "codex",
    provider_version: "example-provider-v1",
    session_display_name: sessionLabel,
    session_display_name_origin: "provider",
    session_id: sessionId,
    session_manual_label_revision: 0,
    source_schema_version: "example-schema-v1",
    started_at: startedAt,
    terminal_state: "unknown",
  };
}

function watchSnapshot(maxMessages = 25): ModelEnsembleWatchSnapshot {
  return {
    watch: {
      watch_id: "d".repeat(64),
      provider: "codex",
      project_id: PROJECT_B,
      session_id: SESSION_B,
      max_messages: maxMessages,
      state: "queued",
      generation: 0,
      progress_completed: 0,
      progress_total: 10,
      has_result: false,
      last_error_code: null,
      next_check_at: "2040-01-02T10:01:00Z",
      updated_at: "2040-01-02T10:00:00Z",
      serial_model_execution: true,
      process_isolated_model_release: true,
      cuda_resource_retry_on_cpu: true,
      content_persisted: false,
      calibrated_as_truth: false,
    },
    latest_run: null,
  };
}

describe("ModelEnsembleOverlay", () => {
  it("renders custom native chrome and delegates only window controls to the desktop bridge", async () => {
    const minimizeWindow = vi.fn(async () => undefined);
    const toggleMaximizeWindow = vi.fn()
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(false);
    const closeWindow = vi.fn(async () => undefined);
    Object.defineProperty(window, "pywebview", {
      configurable: true,
      value: {
        api: {
          minimize_window: minimizeWindow,
          toggle_maximize_window: toggleMaximizeWindow,
          close_window: closeWindow,
        },
      },
    });

    render(<ModelEnsembleOverlay transport={createSyntheticTransport()} />);

    expect(screen.getByText("Prompt Enhancer")).toBeVisible();
    expect(screen.getByText("Live intelligence")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Minimize window" }));
    fireEvent.click(screen.getByRole("button", { name: "Maximize window" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Restore window" })).toBeVisible());
    fireEvent.click(screen.getByRole("button", { name: "Restore window" }));
    fireEvent.click(screen.getByRole("button", { name: "Close window" }));

    await waitFor(() => {
      expect(minimizeWindow).toHaveBeenCalledOnce();
      expect(toggleMaximizeWindow).toHaveBeenCalledTimes(2);
      expect(closeWindow).toHaveBeenCalledOnce();
    });
  });

  it("renders an absent active watch as an idle choice, not a disconnection", async () => {
    const getActiveModelEnsembleWatch = vi.fn().mockRejectedValue({ status: 404 });
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getActiveModelEnsembleWatch,
    };

    render(<ModelEnsembleOverlay transport={transport} />);
    await waitFor(() => expect(getActiveModelEnsembleWatch).toHaveBeenCalledOnce());
    await settlePoll();

    expect(screen.getByText("No active watch")).toBeVisible();
    expect(screen.getByText(/No live watch is active/i)).toBeVisible();
    expect(screen.queryByText(/Disconnected/)).not.toBeInTheDocument();
  });

  it("reserves disconnected for an actual service failure", async () => {
    const getActiveModelEnsembleWatch = vi.fn().mockRejectedValue({ status: 503 });
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getActiveModelEnsembleWatch,
    };

    render(<ModelEnsembleOverlay transport={transport} />);

    expect(await screen.findByText(/Disconnected · retaining last receipt/i)).toBeVisible();
  });

  it("navigates indexed projects and sessions, filters catalog dates, and enables an exact message window", async () => {
    const recent = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    const old = new Date(Date.now() - 120 * 24 * 60 * 60 * 1000).toISOString();
    const sessions = [
      catalogSession(PROJECT_A, SESSION_A, "Example Alpha", "Older planning", old),
      catalogSession(PROJECT_B, SESSION_B, "Example Beta", "Recent implementation", recent),
    ];
    const enableModelEnsembleWatch = vi.fn(async () => watchSnapshot(25));
    const listCodexSessions = vi.fn(async () => ({ sessions, limit: 100, offset: 0 }));
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      listCodexSessions,
      getActiveModelEnsembleWatch: vi.fn().mockRejectedValue({ status: 404 }),
      enableModelEnsembleWatch,
    };

    render(<ModelEnsembleOverlay transport={transport} />);
    await waitFor(() => expect(listCodexSessions).toHaveBeenCalledWith(100, 0, expect.any(AbortSignal)));
    expect(enableModelEnsembleWatch).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Session catalog date"), { target: { value: "7" } });
    await waitFor(() => expect(screen.getByLabelText("Watch project")).toHaveValue(PROJECT_B));
    expect(screen.queryByRole("option", { name: "Example Alpha" })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Recent implementation/ })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Analysis message window"), { target: { value: "25" } });
    fireEvent.click(screen.getByRole("button", { name: "Watch selected session" }));

    await waitFor(() => expect(enableModelEnsembleWatch).toHaveBeenCalledWith(
      SESSION_B,
      {
        project_id: PROJECT_B,
        max_messages: 25,
        confirmation: "continuously_analyze_selected_redacted_session",
      },
    ));
    expect(await screen.findByText(/Newest 25 messages · generation 0/i)).toBeVisible();
    expect(screen.getByText(/exact within-session date cutoffs/i)).toBeVisible();
  });
});
