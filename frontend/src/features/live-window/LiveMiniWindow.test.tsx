import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TransportError } from "../../shared/api/httpTransport";
import { LiveMiniWindow, openLiveWindow } from "./LiveMiniWindow";

const PROJECT = "a".repeat(64);
const SESSION = "b".repeat(64);

describe("LiveMiniWindow", () => {
  it("opens one named popup per project or session", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    openLiveWindow({ name: "live", projectId: PROJECT });
    openLiveWindow({ name: "live", projectId: PROJECT, sessionId: SESSION });
    expect(open).toHaveBeenCalledTimes(2);
    expect(open.mock.calls[0][0]).toBe(`/live/projects/${PROJECT}`);
    expect(open.mock.calls[0][1]).toBe(`pe-live-${PROJECT.slice(0, 12)}-project`);
    expect(open.mock.calls[1][1]).toBe(`pe-live-${PROJECT.slice(0, 12)}-${SESSION.slice(0, 12)}`);
    expect(String(open.mock.calls[0][2])).toContain("width=480");
    open.mockRestore();
  });

  it("shows a session by name with its latest analysis, job and timeline", async () => {
    const transport = {
      listProjectSessions: vi.fn(async () => ({
        sessions: [{ session_id: SESSION, project_id: PROJECT, provider: "claude_code", session_display_name: "Add retries", project_display_name: "example-app" }],
        limit: 100, offset: 0, total: 1, has_more: false,
      })),
      getLatestSessionQualityAnalysis: vi.fn(async () => ({
        run: { run_id: "c".repeat(64), status: "completed" },
        results: [
          { key: "outcome.first_pass_verification", value_state: "known", fraction: { numerator: 1, denominator: 1 } },
          { key: "prompt.task_definition_coverage", value_state: "unknown", fraction: null },
        ],
      })),
      getLatestSessionAnalysisJob: vi.fn(async () => { throw new TransportError("none", 404); }),
      getSessionTimeline: vi.fn(async () => { throw new TransportError("none", 404); }),
      getProjectTimeline: vi.fn(async () => { throw new TransportError("none", 404); }),
    };
    render(<LiveMiniWindow projectId={PROJECT} sessionId={SESSION} transport={transport as never} />);
    await screen.findByRole("heading", { level: 1, name: "Add retries" });
    await screen.findByText("completed · 1/2 known");
    expect(screen.getByText("1/1")).toBeTruthy();
    await screen.findByText("none");
    expect(screen.getByRole("link", { name: "Open in dashboard" }).getAttribute("href")).toContain(`/projects/${PROJECT}/sessions/${SESSION}/metrics/prompt-quality`);
    expect(screen.getByText(/every 20s/)).toBeTruthy();
  });
});
