import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ApplicationUpdateStatus, PromptEnhancerTransport } from "../shared/api/contracts";
import { ApplicationUpdateControl } from "./ApplicationUpdateControl";

const UNCONFIGURED: ApplicationUpdateStatus = {
  contract_version: "application-update-status.v1",
  contains_private_data: false,
  installed_version: "1.2.3",
  channel: "stable",
  state: "unconfigured",
  available_version: null,
  artifact_size_bytes: null,
  downloaded_bytes: null,
  last_checked_at: null,
  reason_code: "release_feed_unconfigured",
  verification_code: null,
  can_check: false,
  can_stage: false,
  can_cancel: false,
  can_apply: false,
};

const CURRENT: ApplicationUpdateStatus = {
  ...UNCONFIGURED,
  state: "current",
  reason_code: null,
  last_checked_at: "2040-01-02T03:04:05Z",
  can_check: true,
};

function transport(status: ApplicationUpdateStatus) {
  return {
    getApplicationUpdateStatus: vi.fn(async () => status),
    checkApplicationUpdate: vi.fn(async () => status),
  } satisfies Pick<PromptEnhancerTransport, "getApplicationUpdateStatus" | "checkApplicationUpdate">;
}

describe("ApplicationUpdateControl", () => {
  it("shows a truthful disabled state when no signed release channel is connected", async () => {
    const api = transport(UNCONFIGURED);
    render(<ApplicationUpdateControl transport={api} variant="sidebar" />);

    const button = await screen.findByRole("button", { name: /updates not connected/i });
    expect(button).toBeDisabled();
    expect(within(button).getByText(/version 1\.2\.3 · stable/i)).toBeVisible();
    expect(api.checkApplicationUpdate).not.toHaveBeenCalled();
  });

  it("checks only after an enabled owner action and exposes pending state", async () => {
    let finish!: (value: ApplicationUpdateStatus) => void;
    const pending = new Promise<ApplicationUpdateStatus>((resolve) => { finish = resolve; });
    const api = transport(CURRENT);
    api.checkApplicationUpdate.mockReturnValueOnce(pending);
    render(<ApplicationUpdateControl transport={api} variant="sidebar" />);
    const button = await screen.findByRole("button", { name: /software is current/i });

    fireEvent.click(button);

    expect(api.checkApplicationUpdate).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: /checking for updates/i })).toBeDisabled();
    finish(CURRENT);
    await waitFor(() => expect(screen.getByRole("button", { name: /software is current/i })).toBeEnabled());
  });

  it("renders bounded release facts without exposing a URL or path", async () => {
    const available: ApplicationUpdateStatus = {
      ...CURRENT,
      state: "available",
      available_version: "2.0.0",
      artifact_size_bytes: 25 * 1024 ** 2,
      downloaded_bytes: 0,
      can_stage: false,
    };
    render(<ApplicationUpdateControl transport={transport(available)} variant="drawer" />);

    const button = await screen.findByRole("button", { name: /version 2\.0\.0 available/i });
    expect(button).toBeDisabled();
    expect(within(button).getByText(/25 MiB · download not connected/i)).toBeVisible();
    expect(document.body.textContent).not.toMatch(/https?:|[A-Z]:\\/u);
  });

  it("fails closed with fixed copy when the local status cannot be read", async () => {
    const api = transport(CURRENT);
    api.getApplicationUpdateStatus.mockRejectedValueOnce(new Error("synthetic private-shaped failure"));
    render(<ApplicationUpdateControl transport={api} variant="sidebar" />);

    expect(await screen.findByRole("button", { name: /update status unavailable/i })).toBeDisabled();
    expect(document.body).not.toHaveTextContent("synthetic private-shaped failure");
  });
});
