import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createSyntheticTransport } from "../shared/api/syntheticTransport";
import { createSyntheticTeamControlPlanePort } from "../shared/api/teamControlPlaneSynthetic";
import type { TeamControlPlanePort } from "../shared/api/teamControlPlane";
import type { AppRoute, PlatformAdapter } from "../shared/platform/platform";
import { parseRoute, routePath } from "../shared/platform/platform";
import { createRuntimeComposition } from "../shared/platform/runtimeMode";
import type { LocalRuntimeTransport } from "../shared/platform/runtimeMode";
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

describe("scoped analytics and task flow routes", () => {
  it("round-trips the new routes through the platform paths", () => {
    expect(routePath({ name: "team" })).toBe("/team");
    expect(routePath({ name: "task_flow" })).toBe("/tasks/flow");
    expect(parseRoute("/team")).toEqual({ name: "team" });
    expect(parseRoute("/tasks/flow/")).toEqual({ name: "task_flow" });
    expect(parseRoute("/tasks/flow/extra")).toEqual({ name: "discovery" });
  });

  it("navigates to Team analytics with the synthetic port and a scoped trail", async () => {
    render(
      <App
        platform={createMemoryPlatform()}
        runtime={createRuntimeComposition("synthetic_demo", createSyntheticTransport())}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Team analytics" }));
    expect(await screen.findByRole(
      "heading",
      { level: 1, name: "Me · Team · Organization" },
      { timeout: 5_000 },
    )).toBeVisible();
    expect(screen.getByLabelText("Current location").textContent).toContain("Scoped workspace");
    expect(await screen.findByRole("group", { name: "Analytics scope" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Team analytics" })).toHaveAttribute("aria-current", "page");
  });

  it("navigates to Task flow and keeps the personal trail", async () => {
    render(
      <App
        platform={createMemoryPlatform()}
        runtime={createRuntimeComposition("synthetic_demo", createSyntheticTransport())}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Task flow" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Task flow" })).toBeVisible();
    expect(screen.getByLabelText("Current location").textContent).toContain("Personal workspace");
    expect(await screen.findByRole("group", { name: "Task flow board" })).toBeVisible();
  });

  it("does not compose even a fully relabelled synthetic team port into local-real mode", async () => {
    const fixtureBackedLoopbackStub: LocalRuntimeTransport = {
      ...createSyntheticTransport(),
      runtimeKind: "local_loopback",
      getRuntimeHealth: async () => ({ status: "ok", costMode: "offline_only", dataTier: "metadata" }),
    };
    const fixture = createSyntheticTeamControlPlanePort();
    const relabelledFixture: TeamControlPlanePort = {
      portVersion: fixture.portVersion,
      origin: "local_loopback",
      principalId: fixture.principalId,
      async getCapabilities(signal) {
        return { ...await fixture.getCapabilities(signal), origin: "local_loopback" };
      },
      async getAggregate(scope, signal) {
        return { ...await fixture.getAggregate(scope, signal), origin: "local_loopback" };
      },
      async getMemberVisibility(request, signal) {
        return { ...await fixture.getMemberVisibility(request, signal), origin: "local_loopback" };
      },
    };
    render(
      <App
        platform={createMemoryPlatform({ name: "team" })}
        runtime={createRuntimeComposition("local_real", fixtureBackedLoopbackStub)}
        teamControlPlane={relabelledFixture}
      />,
    );
    expect(await screen.findByText("Me scope is not served here")).toBeVisible();
    expect(screen.queryByText(/Synthetic platform guild/)).toBeNull();
    expect(screen.getByText(/exact immutable scope and cohort query identity/)).toBeVisible();
  });
});
