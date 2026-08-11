import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ProviderCompatibilityStatus } from "../../shared/api/contracts";
import {
  isPromptTextCompatible,
  promptTextCompatibilityBlocker,
  ProviderCompatibilityCard,
} from "./ProviderCompatibilityCard";

const EXACT: ProviderCompatibilityStatus = {
  provider: "codex",
  capability: "session_text_analysis",
  state: "exact",
  capability_state: "supported",
  provider_family: "codex_app_server",
  provider_version: "1.2.3",
  adapter_family: "codex_app_server",
  adapter_version: "2.0.0",
  source_schema_family: "codex_thread",
  source_schema_version: "1",
  content_schema_family: "codex_thread_items",
  content_schema_version: "1",
  reason_code: "exact_match",
  checked_at: "2040-01-01T10:00:00Z",
  update_support: "unsupported",
  update_target: null,
};

describe("ProviderCompatibilityCard", () => {
  it("shows only content-free family/version status and an explicit check", () => {
    render(
      <ProviderCompatibilityCard
        onCheck={vi.fn(async () => undefined)}
        status={EXACT}
      />,
    );

    expect(screen.getByText("Exact match")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Installed schema compatibility" })).toBeVisible();
    expect(screen.getAllByText(/does not test an individual session read/i)).toHaveLength(2);
    expect(screen.getByText("codex_app_server · 1.2.3")).toBeVisible();
    expect(screen.getByText("codex_thread_items · 1")).toBeVisible();
    expect(screen.getByRole("button", { name: "Check compatibility" })).toBeVisible();
    expect(screen.queryByRole("button", { name: /continue/i })).not.toBeInTheDocument();
    expect(isPromptTextCompatible(EXACT)).toBe(true);
    expect(promptTextCompatibilityBlocker(EXACT)).toBeNull();
  });

  it("fails closed for untested and degraded text extraction", () => {
    const degraded: ProviderCompatibilityStatus = {
      ...EXACT,
      state: "degraded",
      capability_state: "supported",
      reason_code: "degraded_extraction",
    };

    expect(isPromptTextCompatible(null)).toBe(false);
    expect(promptTextCompatibilityBlocker(null)).toMatch(/has not been checked/i);
    expect(isPromptTextCompatible(degraded)).toBe(false);
    expect(promptTextCompatibilityBlocker(degraded)).toMatch(/degraded/i);
  });

  it("locks a pending check and sanitizes failures", async () => {
    let signal: AbortSignal | undefined;
    const onCheck = vi.fn((nextSignal: AbortSignal) => {
      signal = nextSignal;
      return Promise.reject(new Error("PRIVATE-PROVIDER-CANARY"));
    });
    render(<ProviderCompatibilityCard onCheck={onCheck} status={null} />);

    const check = screen.getByRole("button", { name: "Check compatibility" });
    fireEvent.click(check);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The local compatibility check could not be completed.",
    );
    expect(document.body.textContent).not.toContain("PRIVATE-PROVIDER-CANARY");
    expect(signal).toBeInstanceOf(AbortSignal);
    await waitFor(() => expect(check).toBeEnabled());
  });

  it("shows an update action only when support, target, and handler are explicit", () => {
    const onUpdate = vi.fn();
    const { rerender } = render(
      <ProviderCompatibilityCard onUpdate={onUpdate} status={EXACT} />,
    );
    expect(screen.queryByRole("button", { name: /update/i })).not.toBeInTheDocument();

    rerender(
      <ProviderCompatibilityCard
        onUpdate={onUpdate}
        status={{
          ...EXACT,
          state: "incompatible",
          capability_state: "unsupported",
          reason_code: "adapter_outdated",
          update_support: "supported",
          update_target: "prompt_enhancer",
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Update Prompt Enhancer" }));
    expect(onUpdate).toHaveBeenCalledTimes(1);
  });

  it("announces the result of an explicit successful check without version noise", async () => {
    function Harness() {
      const [status, setStatus] = useState<ProviderCompatibilityStatus | null>(null);
      return (
        <ProviderCompatibilityCard
          onCheck={async () => setStatus(EXACT)}
          status={status}
        />
      );
    }
    render(<Harness />);

    const announcement = screen.getByRole("status");
    expect(announcement).toHaveTextContent(/not checked.*no verified compatibility/i);
    fireEvent.click(screen.getByRole("button", { name: "Check compatibility" }));

    await waitFor(() =>
      expect(announcement).toHaveTextContent(
        /exact match.*installed provider schemas exactly match/i,
      ),
    );
    expect(announcement).not.toHaveTextContent("1.2.3");
  });
});
