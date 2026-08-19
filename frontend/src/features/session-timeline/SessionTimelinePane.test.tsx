import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SessionTimeline } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { SessionTimelinePane, safeTimeline } from "./SessionTimelinePane";

const SESSION = "a".repeat(64);

function timeline(): SessionTimeline {
  return {
    contract_version: "session-timeline.v1" as const,
    session_id: SESSION,
    provider: "claude_code",
    project_id: "b".repeat(64),
    project_display_name: "example-app",
    session_display_name: "Add retries to the uploader",
    started_at: "2026-03-02T09:00:00Z",
    ended_at: "2026-03-02T09:10:00Z",
    events_complete: true,
    truncated: false,
    turns: [
      { index: 0, started_at: "2026-03-02T09:00:00Z", ended_at: "2026-03-02T09:04:00Z" },
      { index: 1, started_at: "2026-03-02T09:05:00Z", ended_at: null },
    ],
    tools: [
      { started_at: "2026-03-02T09:01:00Z", ended_at: "2026-03-02T09:01:30Z", category: "file_write", success: null, duration_ms: 30000, verification: false },
      { started_at: "2026-03-02T09:02:00Z", ended_at: "2026-03-02T09:03:00Z", category: "test", success: true, duration_ms: 60000, verification: true },
      { started_at: "2026-03-02T09:06:00Z", ended_at: "2026-03-02T09:07:00Z", category: "test", success: false, duration_ms: 60000, verification: true },
    ],
    markers: [{ at: "2026-03-02T09:08:00Z", kind: "compaction" }],
    usage: { requests: 3, input_tokens: 12000, output_tokens: 800, cached_input_tokens: null },
    counts: { events: 12, turns: 2, tools: 3, verifications_passed: 1, verifications_failed: 1, verifications_unknown: 0, tool_errors: 1 },
  };
}

describe("SessionTimelinePane", () => {
  it("validates the contract", () => {
    expect(safeTimeline(timeline())).toBe(true);
    expect(safeTimeline({ ...timeline(), contract_version: "nope" })).toBe(false);
  });

  it("draws turns, tools, checks and markers with honest counts", async () => {
    const getSessionTimeline = vi.fn(async (_id: string, _signal?: AbortSignal) => timeline());
    const { container } = render(<SessionTimelinePane sessionId={SESSION} transport={{ getSessionTimeline }} />);
    await screen.findByRole("heading", { name: "What happened, when" });
    expect(getSessionTimeline).toHaveBeenCalledWith(SESSION, expect.anything());
    expect(screen.getAllByText("10m 0s").length).toBeGreaterThan(0);
    expect(screen.getByText("1 passed · 1 failed")).toBeTruthy();
    expect(screen.getByText("3 · 1 failed")).toBeTruthy();
    expect(screen.getByText("12.0k in · 800 out")).toBeTruthy();
    expect(container.querySelectorAll(".session-timeline__turn").length).toBe(2);
    expect(container.querySelectorAll(".session-timeline__tool").length).toBe(3);
    expect(container.querySelectorAll(".session-timeline__tool--passed").length).toBe(1);
    expect(container.querySelectorAll(".session-timeline__tool--failed").length).toBe(1);
    expect(container.querySelectorAll(".session-timeline__marker--compaction").length).toBe(1);
    // Nothing textual beyond labels: no command, path or prompt text is rendered.
    expect(container.textContent).not.toMatch(/pytest|\/srv\//);
  });

  it("hides itself when the runtime has no timeline and reports verification failures", async () => {
    const missing = vi.fn(async () => { throw new TransportError("nope", 404); });
    const { container, unmount } = render(<SessionTimelinePane sessionId={SESSION} transport={{ getSessionTimeline: missing }} />);
    await vi.waitFor(() => expect(missing).toHaveBeenCalled());
    await vi.waitFor(() => expect(container.textContent).toBe(""));
    unmount();
    const broken = vi.fn(async () => ({ contract_version: "other" }));
    render(<SessionTimelinePane sessionId={SESSION} transport={{ getSessionTimeline: broken as never }} />);
    await screen.findByRole("alert");
  });
});
