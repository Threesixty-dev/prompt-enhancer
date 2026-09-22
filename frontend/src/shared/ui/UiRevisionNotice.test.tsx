import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DisposableUiRevisionGuard, UiRevisionSnapshot } from "../platform/uiRevisionGuard";
import { UiRevisionNotice } from "./UiRevisionNotice";

function createGuard(initial: UiRevisionSnapshot) {
  let snapshot = Object.freeze(initial);
  const listeners = new Set<() => void>();
  const guard: DisposableUiRevisionGuard = {
    getSnapshot: () => snapshot,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setReloadBlocked: vi.fn(),
    requestReload: vi.fn(() => true),
    dispose: vi.fn(),
  };
  return {
    guard,
    setSnapshot(next: UiRevisionSnapshot) {
      snapshot = Object.freeze(next);
      for (const listener of listeners) listener();
    },
  };
}

describe("UiRevisionNotice", () => {
  it("stays absent while no verified refresh is available", () => {
    const { guard } = createGuard({ status: "idle", reloadBlocked: false });
    render(<UiRevisionNotice guard={guard} />);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("offers one explicit accessible refresh and explains a blocked control", () => {
    const fixture = createGuard({ status: "available", reloadBlocked: true });
    render(<UiRevisionNotice guard={fixture.guard} />);
    const button = screen.getByRole("button", { name: "Refresh interface" });
    expect(screen.getByRole("status", { name: "Interface refresh available" })).toBeVisible();
    expect(button).toBeDisabled();
    expect(screen.getByText(/temporary work may be lost/i)).toBeVisible();

    act(() => fixture.setSnapshot({ status: "available", reloadBlocked: false }));
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(fixture.guard.requestReload).toHaveBeenCalledOnce();
  });

  it("reports a failed request honestly without offering a retry loop", () => {
    const { guard } = createGuard({ status: "reload_failed", reloadBlocked: false });
    render(<UiRevisionNotice guard={guard} />);
    expect(screen.getByRole("status")).toHaveTextContent("Interface refresh could not start.");
    expect(screen.queryByRole("button", { name: "Refresh interface" })).toBeNull();
  });

  it("does not claim a browser refresh completed after requesting one", () => {
    const { guard } = createGuard({ status: "reload_requested", reloadBlocked: false });
    render(<UiRevisionNotice guard={guard} />);
    expect(screen.getByRole("status")).toHaveTextContent(/browser cancels it, this page stays open/i);
    expect(screen.queryByRole("button", { name: "Refresh interface" })).toBeNull();
  });
});
