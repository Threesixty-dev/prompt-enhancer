import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CodexSession } from "../../shared/api/contracts";
import { SessionsPage, durationLabel, safeSessionRow } from "./SessionsPage";

function row(input: {
  id: string;
  project: string;
  projectName: string | null;
  title: string | null;
  provider: CodexSession["provider"];
  started: string;
  ended?: string | null;
}): CodexSession {
  return {
    session_id: input.id.repeat(64).slice(0, 64),
    installation_id: "1".repeat(64),
    project_id: input.project.repeat(64).slice(0, 64),
    project_display_name: input.projectName,
    session_display_name: input.title,
    provider: input.provider,
    project_display_name_origin: input.projectName ? "provider" : "unknown",
    session_display_name_origin: input.title ? "provider" : "unknown",
    project_manual_label_revision: 0,
    session_manual_label_revision: 0,
    provider_version: "example-provider-1",
    adapter_version: "example-adapter-1",
    source_schema_version: "example-schema-1",
    started_at: input.started,
    ended_at: input.ended ?? null,
    terminal_state: null,
    events_complete: false,
  };
}

const ROWS: CodexSession[] = [
  row({ id: "a", project: "1", projectName: "prompt-enhancer", title: "Add retries to the uploader", provider: "claude_code", started: "2040-02-02T09:00:00Z", ended: "2040-02-02T09:42:00Z" }),
  row({ id: "b", project: "1", projectName: "prompt-enhancer", title: "Refactor discovery inbox", provider: "codex", started: "2040-02-01T09:00:00Z", ended: "2040-02-01T12:05:00Z" }),
  row({ id: "c", project: "2", projectName: "example-observatory", title: null, provider: "codex", started: "2040-01-30T09:00:00Z" }),
];

function transportWith(rows: CodexSession[]) {
  return { listCodexSessions: vi.fn(async (_limit: number, _offset: number) => ({ sessions: rows, limit: 100, offset: 0 })) };
}

describe("SessionsPage", () => {
  it("lists every session newest first by name, never by identifier", async () => {
    const transport = transportWith(ROWS);
    render(<SessionsPage navigate={vi.fn()} transport={transport} />);
    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(within(items[0]).getByText("Add retries to the uploader")).toBeInTheDocument();
    expect(within(items[0]).getByText("prompt-enhancer")).toBeInTheDocument();
    expect(within(items[0]).getByLabelText("Source: Claude Code")).toBeInTheDocument();
    expect(within(items[0]).getByText("42 min")).toBeInTheDocument();
    expect(within(items[1]).getByText("3 h 5 min")).toBeInTheDocument();
    expect(within(items[2]).getByText("Untitled session")).toBeInTheDocument();
    expect(within(items[2]).getByText("End not recorded")).toBeInTheDocument();
    expect(screen.getByText(/3 of 3 sessions · 1 without a title/)).toBeInTheDocument();
    for (const r of ROWS) {
      expect(document.body.textContent).not.toContain(r.session_id);
      expect(document.body.textContent).not.toContain(r.project_id);
    }
  });

  it("filters by source and searches by project or title, and opens the session route", async () => {
    const navigate = vi.fn();
    render(<SessionsPage navigate={navigate} transport={transportWith(ROWS)} />);
    await screen.findAllByRole("listitem");
    fireEvent.click(screen.getByRole("button", { name: "Claude Code" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "All sources" }));
    fireEvent.change(screen.getByLabelText("Search sessions by project or title"), { target: { value: "observatory" } });
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(1);
    fireEvent.click(within(items[0]).getAllByRole("button")[0]);
    expect(navigate).toHaveBeenCalledWith({
      name: "session_metrics",
      projectId: ROWS[2].project_id,
      sessionId: ROWS[2].session_id,
      category: "readiness",
    });
  });

  it("fails closed on an invalid catalog row and explains an empty store", async () => {
    render(<SessionsPage navigate={vi.fn()} transport={transportWith([{ ...ROWS[0], session_id: "not-a-pseudonym" }])} />);
    await waitFor(() => expect(screen.getByText(/response was invalid/)).toBeInTheDocument());
    expect(safeSessionRow({ ...ROWS[0], provider: "mystery" })).toBe(false);
    expect(safeSessionRow({ ...ROWS[0], session_display_name: "line\nbreak" })).toBe(false);
    expect(durationLabel("2040-01-01T00:00:00Z", "2040-01-01T00:00:30Z")).toBe("30s");
    expect(durationLabel("bad", null)).toBe("Start unknown");
  });

  it("shows an empty state that points at the Data source page", async () => {
    render(<SessionsPage navigate={vi.fn()} transport={transportWith([])} />);
    expect(await screen.findByText("No sessions captured yet")).toBeInTheDocument();
    expect(screen.getByText(/Data source page/)).toBeInTheDocument();
  });
});
