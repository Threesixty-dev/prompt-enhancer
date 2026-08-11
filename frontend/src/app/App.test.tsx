import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createSyntheticTransport } from "../shared/api/syntheticTransport";
import {
  SYNTHETIC_QUALITY_PROJECT_ID,
  SYNTHETIC_QUALITY_SESSION_ID,
} from "../shared/api/syntheticFixtures";
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
  it("exposes a responsive shell with a keyboard skip target", () => {
    const { container } = render(
      <App
        mode="synthetic"
        platform={createMemoryPlatform()}
        transport={createSyntheticTransport()}
      />,
    );

    expect(screen.getByRole("link", { name: "Skip to dashboard" })).toHaveAttribute(
      "href",
      "#main-content",
    );
    expect(container.querySelector(".app-shell")).toHaveAttribute(
      "data-layout",
      "responsive-shell",
    );
    expect(container.querySelector("#main-content")).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeVisible();
  });

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

  it("keeps fictional projects available in preview while local-source controls stay local", async () => {
    const { unmount } = render(
      <App
        mode="synthetic"
        platform={createMemoryPlatform()}
        transport={createSyntheticTransport()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Data source" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Projects" })).toBeVisible();
    unmount();

    render(
      <App
        mode="local"
        platform={createMemoryPlatform()}
        transport={createSyntheticTransport()}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Data source" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Projects" })).toBeVisible();
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

  it("opens the methods and models lab from primary navigation", async () => {
    render(
      <App
        mode="synthetic"
        platform={createMemoryPlatform()}
        transport={createSyntheticTransport()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Methods & models" }));
    expect(
      await screen.findByRole("heading", { name: "Build useful metrics, then earn trust" }),
    ).toBeVisible();
  });

  it("renders the fictional project catalog in synthetic preview", async () => {
    const transport = createSyntheticTransport();
    const listSpy = vi.spyOn(transport, "listCodexSessions");
    render(
      <App
        mode="synthetic"
        platform={createMemoryPlatform({ name: "projects" })}
        transport={transport}
      />,
    );

    expect(await screen.findByText("Synthetic Metric Lab")).toBeVisible();
    expect(listSpy).toHaveBeenCalledTimes(1);
  });

  it("supports a direct fictional quality-profile route for browser QA", async () => {
    render(
      <App
        mode="synthetic"
        platform={createMemoryPlatform({
          name: "session_metrics",
          projectId: SYNTHETIC_QUALITY_PROJECT_ID,
          sessionId: SYNTHETIC_QUALITY_SESSION_ID,
          category: "prompt-quality",
        })}
        transport={createSyntheticTransport()}
      />,
    );

    expect(await screen.findByText("Coherent metric pack v3")).toBeVisible();
    expect(
      screen.getByRole("img", { name: /6-axis 100% fixed-scale quality lens radar/i }),
    ).toBeVisible();
    expect(await screen.findByText("Verification passed")).toBeVisible();
    expect(screen.getByText("Watch for:")).toBeVisible();
    expect(await screen.findByRole("button", { name: "Analyze locally" })).toBeEnabled();
    expect(
      screen.getByRole("heading", { name: "Prompt & collaboration coaching" }),
    ).toBeVisible();
  });

  it("renders a project quality profile from one server-style aggregate call", async () => {
    const transport = createSyntheticTransport();
    const aggregate = vi.spyOn(transport, "aggregateSessionQuality");
    const latest = vi.spyOn(transport, "getLatestSessionQualityAnalysis");
    render(
      <App
        mode="synthetic"
        platform={createMemoryPlatform({
          name: "project_metrics",
          projectId: SYNTHETIC_QUALITY_PROJECT_ID,
          category: "prompt-quality",
        })}
        transport={transport}
      />,
    );

    expect(await screen.findByText("1 of 1 selected sessions have a compatible Coaching v1 run")).toBeVisible();
    expect(screen.getByText("Coherent metric pack v3")).toBeVisible();
    expect(
      screen.getByRole("img", { name: /6-axis 100% fixed-scale quality lens radar/i }),
    ).toBeVisible();
    expect(aggregate).toHaveBeenCalledWith(
      { session_ids: [SYNTHETIC_QUALITY_SESSION_ID] },
      expect.any(AbortSignal),
    );
    expect(latest).not.toHaveBeenCalled();
  });
});
