import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { OnboardingStatus } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { FirstRunPanel } from "./FirstRunPanel";

function status(overrides: Partial<OnboardingStatus> = {}): OnboardingStatus {
  return {
    contract_version: "onboarding.v1",
    providers: [
      { provider: "codex", installed: true, signal: "codex_cli_on_path", consent_active: false, indexed_sessions: 0, transcript_files: null },
      { provider: "claude_code", installed: true, signal: "claude_transcript_root", consent_active: false, indexed_sessions: 0, transcript_files: 52 },
    ],
    any_installed: true,
    needs_onboarding: true,
    refresh_interval_seconds: 600,
    last_refresh_at: null,
    last_refresh_error: false,
    claude_home_override_supported: true,
    ...overrides,
  };
}

describe("FirstRunPanel", () => {
  it("shows both detections and loads everything with one yes", async () => {
    sessionStorage.clear();
    const navigate = vi.fn();
    const acceptOnboarding = vi.fn(async () => ({ granted: ["codex", "claude_code"] as ("codex" | "claude_code")[], indexed_sessions: 60, status: status({ needs_onboarding: false }) }));
    render(<FirstRunPanel navigate={navigate} transport={{ getOnboardingStatus: vi.fn(async () => status()), acceptOnboarding }} />);
    expect(await screen.findByRole("heading", { name: "Load your projects and sessions" })).toBeInTheDocument();
    expect(screen.getByText("52 sessions on disk")).toBeInTheDocument();
    expect(screen.getByText("CLI found")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Yes, load everything" }));
    await waitFor(() => expect(acceptOnboarding).toHaveBeenCalledWith({ providers: ["codex", "claude_code"], claude_home: null }));
    expect(navigate).toHaveBeenCalledWith({ name: "sessions" });
  });

  it("asks for a folder when nothing is found and explains a bad one", async () => {
    sessionStorage.clear();
    const acceptOnboarding = vi.fn(async () => { throw new TransportError("claude_home_invalid", 422); });
    render(<FirstRunPanel navigate={vi.fn()} transport={{
      getOnboardingStatus: vi.fn(async () => status({ any_installed: false, providers: [
        { provider: "codex", installed: false, signal: "not_found", consent_active: false, indexed_sessions: 0, transcript_files: null },
        { provider: "claude_code", installed: false, signal: "not_found", consent_active: false, indexed_sessions: 0, transcript_files: null },
      ] })),
      acceptOnboarding,
    }} />);
    expect(await screen.findByRole("heading", { name: /could not find Codex or Claude Code/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Yes, load everything" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing to load yet");
    fireEvent.change(screen.getByLabelText("Claude Code folder"), { target: { value: "D:/not-a-home" } });
    await waitFor(() => expect((screen.getByLabelText("Claude Code folder") as HTMLInputElement).value).toBe("D:/not-a-home"));
    fireEvent.click(screen.getByRole("button", { name: "Yes, load everything" }));
    await waitFor(() => expect(acceptOnboarding).toHaveBeenCalledWith({ providers: ["claude_code"], claude_home: "D:/not-a-home" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("does not look like a Claude Code home");
  });

  it("renders nothing once onboarding is done or dismissed, or when the runtime lacks it", async () => {
    sessionStorage.clear();
    const done = render(<FirstRunPanel navigate={vi.fn()} transport={{ getOnboardingStatus: vi.fn(async () => status({ needs_onboarding: false })), acceptOnboarding: vi.fn() }} />);
    await waitFor(() => expect(done.container).toBeEmptyDOMElement());
    done.unmount();
    const absent = render(<FirstRunPanel navigate={vi.fn()} transport={{ getOnboardingStatus: vi.fn(async () => { throw new TransportError("missing", 404); }), acceptOnboarding: vi.fn() }} />);
    await waitFor(() => expect(absent.container).toBeEmptyDOMElement());
    absent.unmount();
    render(<FirstRunPanel navigate={vi.fn()} transport={{ getOnboardingStatus: vi.fn(async () => status()), acceptOnboarding: vi.fn() }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Not now" }));
    expect(screen.queryByRole("heading", { name: "Load your projects and sessions" })).toBeNull();
    expect(sessionStorage.getItem("prompt-enhancer.first-run.dismissed")).toBe("1");
  });
});
