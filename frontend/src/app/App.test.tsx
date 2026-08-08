import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createSyntheticTransport } from "../shared/api/syntheticTransport";
import type { AppRoute, PlatformAdapter } from "../shared/platform/platform";
import { App } from "./App";

function createMemoryPlatform(initialRoute: AppRoute = { name: "discovery" }): PlatformAdapter {
  let route: AppRoute = initialRoute;
  const listeners = new Set<(next: AppRoute) => void>();
  return {
    currentRoute: () => route,
    navigate(next) {
      route = next;
      listeners.forEach((listener) => listener(next));
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

describe("App discovery navigation", () => {
  it("keeps the sidebar review count synchronized after a decision", async () => {
    render(
      <App
        mode="synthetic"
        platform={createMemoryPlatform()}
        transport={createSyntheticTransport()}
      />,
    );

    expect(await screen.findByLabelText("2 candidates need review")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Accept as one task" }));
    expect(await screen.findByLabelText("1 candidate needs review")).toBeVisible();
  });

  it("shows Local sources navigation only in integrated local mode", async () => {
    const { unmount } = render(
      <App
        mode="synthetic"
        platform={createMemoryPlatform()}
        transport={createSyntheticTransport()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Local sources" }),
    ).not.toBeInTheDocument();
    unmount();

    render(
      <App
        mode="local"
        platform={createMemoryPlatform()}
        transport={createSyntheticTransport()}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Local sources" }),
    ).toBeVisible();
  });

  it("does not contact local-source APIs for a synthetic direct route", () => {
    const transport = createSyntheticTransport();
    const statusSpy = vi.spyOn(transport, "getCodexLocalSourceStatus");
    render(
      <App
        mode="synthetic"
        platform={createMemoryPlatform({ name: "local_sources" })}
        transport={transport}
      />,
    );

    expect(
      screen.getByText("Local sources are disabled in synthetic preview"),
    ).toBeVisible();
    expect(statusSpy).not.toHaveBeenCalled();
  });
});
