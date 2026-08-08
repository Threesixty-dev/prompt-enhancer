import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  CodexIngestionReport,
  CodexLabelEnrichmentReport,
  CodexLocalSourceStatus,
  CodexSession,
  DisplayLabelEntityKind,
  PromptEnhancerTransport,
  SessionMetric,
} from "../../shared/api/contracts";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { LocalSources } from "./LocalSources";

const PROJECT_A = "a".repeat(64);
const PROJECT_B = "b".repeat(64);
const SESSION_A = "c".repeat(64);
const SESSION_B = "d".repeat(64);
const SESSION_C = "e".repeat(64);

const SESSIONS: CodexSession[] = [
  {
    session_id: SESSION_A,
    installation_id: "1".repeat(64),
    project_id: PROJECT_A,
    project_display_name: "Example Workspace",
    session_display_name: "Synthetic verification task",
    project_display_name_origin: "provider",
    session_display_name_origin: "provider",
    project_manual_label_revision: 0,
    session_manual_label_revision: 0,
    provider: "codex",
    provider_version: "synthetic-version",
    adapter_version: "synthetic-adapter-v1",
    source_schema_version: "synthetic-schema-v1",
    started_at: "2040-01-02T10:00:00Z",
    ended_at: "2040-01-02T10:05:00Z",
    terminal_state: "completed",
    events_complete: true,
  },
  {
    session_id: SESSION_B,
    installation_id: "1".repeat(64),
    project_id: PROJECT_A,
    project_display_name: "Example Workspace",
    session_display_name: null,
    project_display_name_origin: "provider",
    session_display_name_origin: "unknown",
    project_manual_label_revision: 0,
    session_manual_label_revision: 0,
    provider: "codex",
    provider_version: "synthetic-version",
    adapter_version: "synthetic-adapter-v1",
    source_schema_version: "synthetic-schema-v1",
    started_at: "2040-01-03T10:00:00Z",
    ended_at: null,
    terminal_state: null,
    events_complete: false,
  },
  {
    session_id: SESSION_C,
    installation_id: "1".repeat(64),
    project_id: PROJECT_B,
    project_display_name: null,
    session_display_name: "Synthetic metrics review",
    project_display_name_origin: "unknown",
    session_display_name_origin: "provider",
    project_manual_label_revision: 0,
    session_manual_label_revision: 0,
    provider: "codex",
    provider_version: "synthetic-version",
    adapter_version: "synthetic-adapter-v1",
    source_schema_version: "synthetic-schema-v1",
    started_at: "2040-01-04T10:00:00Z",
    ended_at: "2040-01-04T10:05:00Z",
    terminal_state: "completed",
    events_complete: true,
  },
];

const REPORT: CodexIngestionReport = {
  provider: "codex",
  sessions_seen: 3,
  sessions_selected: 3,
  sessions_inserted: 3,
  sessions_updated: 0,
  events_seen: 6,
  events_inserted: 6,
  events_updated: 0,
  metrics_written: 3,
  truncated: false,
};

const LABEL_REPORT: CodexLabelEnrichmentReport = {
  provider: "codex",
  requested_sessions: 1,
  matched_sessions: 1,
  summary_reads: 1,
  project_labels_filled: 0,
  session_labels_filled: 1,
  labels_unavailable: 0,
  sessions_not_found: 0,
  truncated: false,
};

const METRIC: SessionMetric = {
  key: "session.efficiency.turn_count",
  version: 1,
  dimension: "efficiency",
  display_name: "Turn count",
  numeric_value: 4,
  text_value: null,
  unit: "turns",
  source: "deterministic",
  observed_count: 4,
  eligible_count: 4,
  coverage: 1,
  confidence: 1,
  metric_engine_version: "synthetic-engine-v1",
  redactor_version: null,
  model_id: null,
  model_revision: null,
  tokenizer_id: null,
  prompt_version: null,
  rubric_version: null,
  computed_at: "2040-01-04T10:06:00Z",
};

function createLocalTransport(
  consentActive: boolean,
  sessionRows: CodexSession[] = SESSIONS,
): {
  transport: PromptEnhancerTransport;
  index: ReturnType<typeof vi.fn>;
  analyze: ReturnType<typeof vi.fn>;
  metrics: ReturnType<typeof vi.fn>;
  enrich: ReturnType<typeof vi.fn>;
  setManual: ReturnType<typeof vi.fn>;
  clearManual: ReturnType<typeof vi.fn>;
} {
  let status: CodexLocalSourceStatus = {
    consent_active: consentActive,
    indexed_sessions: sessionRows.length,
    indexed_projects: new Set(sessionRows.map((session) => session.project_id)).size,
  };
  const index = vi.fn(async () => REPORT);
  const analyze = vi.fn(async () => REPORT);
  const metrics = vi.fn(async (sessionId: string) => ({
    session_id: sessionId,
    metrics: [METRIC],
  }));
  const enrich = vi.fn(async () => LABEL_REPORT);
  const setManual = vi.fn(
    async (entityKind: DisplayLabelEntityKind, entityId: string) => ({
      entity_kind: entityKind,
      entity_id: entityId,
      revision: 1,
      changed: true,
    }),
  );
  const clearManual = vi.fn(
    async (entityKind: DisplayLabelEntityKind, entityId: string) => ({
      entity_kind: entityKind,
      entity_id: entityId,
      revision: 2,
      changed: true,
    }),
  );
  const transport: PromptEnhancerTransport = {
    ...createSyntheticTransport(),
    getCodexLocalSourceStatus: vi.fn(async () => status),
    grantCodexLocalHistoryConsent: vi.fn(async () => {
      status = { ...status, consent_active: true };
      return status;
    }),
    revokeCodexLocalHistoryConsent: vi.fn(async () => {
      status = { ...status, consent_active: false };
      return status;
    }),
    indexCodexLocalSessions: index,
    analyzeCodexLocalSessions: analyze,
    enrichCodexDisplayLabels: enrich,
    setManualDisplayLabel: setManual,
    clearManualDisplayLabel: clearManual,
    listCodexSessions: vi.fn(async (limit = 100, offset = 0) => ({
      sessions: sessionRows,
      limit,
      offset,
    })),
    getSessionMetrics: metrics,
  };
  return {
    transport,
    index,
    analyze,
    metrics,
    enrich,
    setManual,
    clearManual,
  };
}

describe("LocalSources", () => {
  it("shows explicit consent state and groups only safe session metadata", async () => {
    const { transport } = createLocalTransport(false);
    render(<LocalSources transport={transport} />);

    expect(await screen.findByRole("heading", { name: "Codex local history" })).toBeVisible();
    expect(screen.getByText("Consent required")).toBeVisible();
    expect(screen.getByText("Example Workspace")).toBeVisible();
    expect(screen.getByText("Synthetic verification task")).toBeVisible();
    expect(screen.getByText("Unnamed project")).toBeVisible();
    expect(screen.getByText("Unnamed session")).toBeVisible();
    expect(screen.getAllByText("Codex label")).toHaveLength(3);
    expect(screen.getAllByText("Missing label")).toHaveLength(2);
    expect(screen.getAllByRole("checkbox")).toHaveLength(5);
    expect(screen.getByText(/Full paths, previews, prompts/i)).toBeVisible();
  });

  it("requires an explicit grant before a bounded index", async () => {
    const { transport, index } = createLocalTransport(false);
    render(<LocalSources transport={transport} />);

    const indexButton = await screen.findByRole("button", {
      name: "Refresh content-discarding index",
    });
    expect(indexButton).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Maximum index sessions" })).toHaveValue("100");
    expect(
      screen.getByRole("combobox", { name: "Maximum analysis sessions" }),
    ).toHaveValue("10");

    fireEvent.click(
      screen.getByRole("button", { name: "Grant local-history access" }),
    );
    expect(await screen.findByText("Access granted")).toBeVisible();
    fireEvent.click(indexButton);

    await waitFor(() => expect(index).toHaveBeenCalledWith(100));
    expect(await screen.findByText("3 sessions indexed.")).toBeVisible();
  });

  it("analyzes a project selection and eagerly refreshes only one session", async () => {
    const { transport, analyze, metrics } = createLocalTransport(true);
    render(<LocalSources transport={transport} />);

    fireEvent.click(
      await screen.findByRole("checkbox", { name: /Example Workspace/ }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Analyze selection" }),
    );

    await waitFor(() =>
      expect(analyze).toHaveBeenCalledWith({
        project_ids: [PROJECT_A],
        session_ids: [],
        max_sessions: 10,
      }),
    );
    expect(await screen.findByText("Turn count")).toBeVisible();
    expect(metrics).toHaveBeenCalledTimes(1);
    expect(metrics).toHaveBeenCalledWith(SESSION_A);

    fireEvent.click(screen.getByRole("button", { name: "Refresh metrics" }));
    await waitFor(() => expect(metrics).toHaveBeenCalledTimes(2));
  });

  it("uses an explicit bounded selection to find missing labels", async () => {
    const { transport, enrich } = createLocalTransport(true);
    render(<LocalSources transport={transport} />);

    fireEvent.click(
      await screen.findByRole("checkbox", { name: /Unnamed session/ }),
    );
    fireEvent.change(
      screen.getByRole("combobox", { name: "Maximum label summary reads" }),
      { target: { value: "5" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Find missing labels" }),
    );

    await waitFor(() =>
      expect(enrich).toHaveBeenCalledWith({
        project_ids: [],
        session_ids: [SESSION_B],
        max_sessions: 5,
      }),
    );
    expect(
      await screen.findByText(/1 missing label imported from 1 summary read/i),
    ).toBeVisible();
  });

  it("stores a manual session label locally without renaming Codex", async () => {
    const { transport, setManual } = createLocalTransport(true);
    render(<LocalSources transport={transport} />);

    const editButtons = await screen.findAllByRole("button", {
      name: "Edit local session label",
    });
    fireEvent.click(editButtons[1]);
    fireEvent.change(screen.getByRole("textbox", { name: "Local display label" }), {
      target: { value: "Local review label" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save locally" }));

    await waitFor(() =>
      expect(setManual).toHaveBeenCalledWith(
        "session",
        SESSION_B,
        "Local review label",
        0,
      ),
    );
    expect(
      await screen.findByText(/The Codex task was not renamed/i),
    ).toBeVisible();
  });

  it("clears only the local manual override by revision", async () => {
    const rows = SESSIONS.map((session) =>
      session.session_id === SESSION_B
        ? {
            ...session,
            session_display_name: "Local review label",
            session_display_name_origin: "manual" as const,
            session_manual_label_revision: 7,
          }
        : session,
    );
    const { transport, clearManual } = createLocalTransport(true, rows);
    render(<LocalSources transport={transport} />);

    const editButtons = await screen.findAllByRole("button", {
      name: "Edit local session label",
    });
    fireEvent.click(editButtons[1]);
    fireEvent.click(screen.getByRole("button", { name: "Clear override" }));

    await waitFor(() =>
      expect(clearManual).toHaveBeenCalledWith("session", SESSION_B, 7),
    );
    expect(
      await screen.findByText(/Any available Codex label is visible again/i),
    ).toBeVisible();
  });

  it("keeps duplicate display names separate through full pseudonymous IDs", async () => {
    const duplicateRows: CodexSession[] = [
      {
        ...SESSIONS[0],
        project_display_name: "Shared Workspace",
        session_display_name: "Shared Task",
      },
      {
        ...SESSIONS[2],
        project_display_name: "Shared Workspace",
        session_display_name: "Shared Task",
      },
    ];

    const { transport, analyze } = createLocalTransport(true, duplicateRows);
    render(<LocalSources transport={transport} />);

    const projectCheckboxes = await screen.findAllByRole("checkbox", {
      name: /Shared Workspace/,
    });
    expect(projectCheckboxes).toHaveLength(2);
    expect((projectCheckboxes[0] as HTMLInputElement).value).toBe(PROJECT_A);
    expect((projectCheckboxes[1] as HTMLInputElement).value).toBe(PROJECT_B);
    expect(screen.getAllByRole("checkbox", { name: /Shared Task/ })).toHaveLength(2);

    fireEvent.click(projectCheckboxes[1]);
    fireEvent.click(screen.getByRole("button", { name: "Analyze selection" }));

    await waitFor(() =>
      expect(analyze).toHaveBeenCalledWith({
        project_ids: [PROJECT_B],
        session_ids: [],
        max_sessions: 10,
      }),
    );
  });
});
