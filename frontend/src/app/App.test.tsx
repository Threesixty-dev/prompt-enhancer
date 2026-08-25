import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createSyntheticTransport } from "../shared/api/syntheticTransport";
import {
  SYNTHETIC_QUALITY_PROJECT_ID,
  SYNTHETIC_QUALITY_SESSION_ID,
} from "../shared/api/syntheticFixtures";
import type { AppRoute, PlatformAdapter } from "../shared/platform/platform";
import {
  createRuntimeComposition,
  type LocalRuntimeTransport,
  type RuntimeHealth,
  type RuntimeComposition,
  type SyntheticRuntimeTransport,
} from "../shared/platform/runtimeMode";
import { App, RouteErrorBoundary } from "./App";

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((accept, decline) => {
    resolve = accept;
    reject = decline;
  });
  return { promise, reject, resolve };
}

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

const HEALTHY_LOCAL_RUNTIME: RuntimeHealth = {
  status: "ok",
  costMode: "offline_only",
  dataTier: "metadata",
};

function syntheticRuntime(
  transport: SyntheticRuntimeTransport = createSyntheticTransport(),
): RuntimeComposition {
  return createRuntimeComposition("synthetic_demo", transport);
}

function localFixtureTransport(
  getRuntimeHealth: LocalRuntimeTransport["getRuntimeHealth"],
): LocalRuntimeTransport {
  return {
    ...createSyntheticTransport(),
    runtimeKind: "local_loopback",
    getRuntimeHealth,
  };
}

describe("App discovery navigation", () => {
  it("exposes a responsive shell with a keyboard skip target", () => {
    const { container } = render(
      <App
        runtime={syntheticRuntime()}
        platform={createMemoryPlatform()}
      />,
    );

    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute(
      "href",
      "#main-content",
    );
    expect(container.querySelector(".app-shell")).toHaveAttribute(
      "data-layout",
      "responsive-shell",
    );
    expect(container.querySelector("#main-content")).toHaveAttribute("tabindex", "-1");
    const primaryNavigation = screen.getByRole("navigation", { name: "Primary" });
    expect(primaryNavigation).toBeVisible();
    expect(within(primaryNavigation).getAllByRole("group")).toHaveLength(4);
    const navigationGlyphs = within(primaryNavigation).getAllByRole("button").map(
      (button) => button.querySelector("svg")?.innerHTML,
    );
    expect(navigationGlyphs.every(Boolean)).toBe(true);
    expect(new Set(navigationGlyphs).size).toBe(navigationGlyphs.length);
    expect(screen.getByLabelText("Synthetic demo fixture ready")).toBeVisible();
    expect(screen.getByText("Synthetic demo · Fixture ready")).toBeVisible();
    expect(
      screen.getByLabelText(/Private by default\. Mobile runtime status: Synthetic demo fixture ready/),
    ).toBeInTheDocument();
  });

  it("opens a grouped mobile navigation dialog and initially focuses the current destination", async () => {
    render(
      <App
        runtime={syntheticRuntime()}
        platform={createMemoryPlatform({ name: "overview" })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    const dialog = screen.getByRole("dialog", { name: "Navigate Prompt Enhancer" });
    const mobileNavigation = within(dialog).getByRole("navigation", { name: "Mobile primary" });
    expect(within(mobileNavigation).getAllByRole("group")).toHaveLength(4);
    const overview = within(mobileNavigation).getByRole("button", { name: "Overview" });
    expect(overview).toHaveAttribute("aria-current", "page");
    await waitFor(() => expect(overview).toHaveFocus());

    fireEvent.click(within(mobileNavigation).getByRole("button", { name: "Sessions" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sessions" })).toBeVisible();
    expect(screen.queryByRole("dialog", { name: "Navigate Prompt Enhancer" })).not.toBeInTheDocument();
  });

  it("keeps reviewed-task progress visible after the mobile drawer closes", async () => {
    const transport = createSyntheticTransport();
    const response = await transport.listTaskRevisions();
    const pending = deferred<typeof response>();
    transport.listTaskRevisions = vi.fn(() => pending.promise);
    render(
      <App
        runtime={syntheticRuntime(transport)}
        platform={createMemoryPlatform({ name: "overview" })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    const dialog = screen.getByRole("dialog", { name: "Navigate Prompt Enhancer" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Reviewed tasks" }));

    await waitFor(() => expect(transport.listTaskRevisions).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("dialog", { name: "Navigate Prompt Enhancer" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Opening reviewed task$/ })).toHaveTextContent(
      "Opening…",
    );
    expect(
      screen.getAllByRole("status").some((status) => status.textContent === "Opening reviewed task…"),
    ).toBe(true);

    await act(async () => {
      pending.resolve(response);
      await pending.promise;
    });
  });

  it("sets an exact initial title without stealing focus, then focuses main on click navigation only", async () => {
    document.title = "Prompt Enhancer";
    render(
      <App
        runtime={syntheticRuntime()}
        platform={createMemoryPlatform()}
      />,
    );

    const main = document.querySelector<HTMLElement>("#main-content")!;
    expect(document.title).toBe("Discovery · Prompt Enhancer");
    expect(main).not.toHaveFocus();
    await screen.findByRole("heading", { name: "Discovery inbox" }, { timeout: 5_000 });

    const sessionsNavigation = screen.getByRole("button", { name: "Sessions" });
    sessionsNavigation.focus();
    fireEvent.click(sessionsNavigation);

    expect(await screen.findByRole("heading", { level: 1, name: "Sessions" }, { timeout: 5_000 })).toBeVisible();
    await waitFor(() => expect(main).toHaveFocus());
    expect(document.title).toBe("Sessions · Prompt Enhancer");

    const search = screen.getByRole("searchbox", { name: "Search sessions by project or title" });
    search.focus();
    fireEvent.change(search, { target: { value: "fictional" } });
    expect(search).toHaveFocus();
    expect(document.title).toBe("Sessions · Prompt Enhancer");
  }, 10_000);

  it("leaves project-workspace titles and subsequent heading focus to the finer route policy", async () => {
    render(
      <App
        platform={createMemoryPlatform({
          name: "project_overview",
          projectId: SYNTHETIC_QUALITY_PROJECT_ID,
        })}
        runtime={syntheticRuntime()}
      />,
    );

    const deckHeading = await screen.findByRole(
      "heading",
      { name: "What do you want to review?" },
      { timeout: 5_000 },
    );
    await waitFor(() => expect(document.title).toBe("Metric deck · Synthetic Metric Lab · Prompt Enhancer"));
    expect(deckHeading).not.toHaveFocus();

    const projectNavigation = screen.getByRole("navigation", { name: "Project sections" });
    fireEvent.click(within(projectNavigation).getByRole("link", { name: /Sessions, 1 indexed/ }));

    const sessionsHeading = await screen.findByRole(
      "heading",
      { level: 2, name: "Sessions" },
      { timeout: 5_000 },
    );
    await waitFor(() => expect(sessionsHeading).toHaveFocus());
    expect(document.title).toBe("Sessions · Synthetic Metric Lab · Prompt Enhancer");
  }, 10_000);

  it("keeps the sidebar review count synchronized after a decision", async () => {
    render(
      <App
        platform={createMemoryPlatform()}
        runtime={syntheticRuntime()}
      />,
    );

    expect(await screen.findByLabelText("2 candidates need review")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Accept as one task" }));
    expect(await screen.findByLabelText("1 candidate needs review")).toBeVisible();
  });

  it("announces a reviewed-task navigation result in one live status region", async () => {
    const transport = createSyntheticTransport();
    transport.listTaskRevisions = vi.fn(async () => ({ limit: 100, offset: 0, tasks: [] }));
    render(
      <App
        platform={createMemoryPlatform()}
        runtime={syntheticRuntime(transport)}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Reviewed tasks" }));

    const notices = await screen.findAllByText("No reviewed task is available yet.");
    expect(notices).toHaveLength(1);
    expect(notices[0]).toHaveAttribute("role", "status");

    fireEvent.click(screen.getByRole("button", { name: "Sessions" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sessions" })).toBeVisible();
    expect(screen.queryByText("No reviewed task is available yet.")).toBeNull();
  });

  it("aborts a pending reviewed-task lookup when newer navigation wins", async () => {
    const transport = createSyntheticTransport();
    const response = await transport.listTaskRevisions();
    const pending = deferred<typeof response>();
    transport.listTaskRevisions = vi.fn((_taskId?: string, _signal?: AbortSignal) => pending.promise);
    render(
      <App
        platform={createMemoryPlatform()}
        runtime={syntheticRuntime(transport)}
      />,
    );

    const reviewedTasks = screen.getByRole("button", { name: "Reviewed tasks" });
    fireEvent.click(reviewedTasks);
    await waitFor(() => expect(transport.listTaskRevisions).toHaveBeenCalledTimes(1));
    expect(reviewedTasks).toBeDisabled();
    expect(reviewedTasks).toHaveAttribute("aria-busy", "true");
    expect(reviewedTasks).toHaveTextContent("Opening reviewed task…");
    const signal = vi.mocked(transport.listTaskRevisions).mock.calls[0][1];
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal?.aborted).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Sessions" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sessions" })).toBeVisible();
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      pending.resolve(response);
      await pending.promise;
    });
    expect(screen.getByRole("heading", { level: 1, name: "Sessions" })).toBeVisible();
    expect(screen.queryByText(/reviewed task is available|task index could not be loaded/i)).toBeNull();
  });

  it("keeps fictional projects available in preview while local-source controls stay local", async () => {
    const { unmount } = render(
      <App
        platform={createMemoryPlatform()}
        runtime={syntheticRuntime()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Data source" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Projects" })).toBeVisible();
    unmount();

    const local = localFixtureTransport(async () => HEALTHY_LOCAL_RUNTIME);
    render(
      <App
        platform={createMemoryPlatform()}
        runtime={createRuntimeComposition("local_real", local)}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Data source" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Projects" })).toBeVisible();
    expect(
      await screen.findByLabelText("Local loopback service available"),
    ).toBeVisible();
  });

  it("shows an accessible deterministic fallback while a route bundle loads", async () => {
    render(
      <App
        platform={createMemoryPlatform({ name: "research" })}
        runtime={syntheticRuntime()}
      />,
    );

    const fallback = screen.getByText("Loading Methods & models…").closest(".async-state");
    expect(fallback).toHaveAttribute("role", "status");
    expect(fallback).toHaveAttribute("aria-atomic", "true");
    expect(fallback).toHaveAttribute("aria-live", "polite");
    expect(screen.getByLabelText("Current location")).toHaveTextContent("Methods & models");
    expect(
      await screen.findByRole("heading", { name: "Build useful metrics, then earn trust" }),
    ).toBeVisible();
  });

  it("reports local service checking before a successful health response", async () => {
    let resolveHealth!: (health: RuntimeHealth) => void;
    const getRuntimeHealth = vi.fn(
      () =>
        new Promise<RuntimeHealth>((resolve) => {
          resolveHealth = resolve;
        }),
    );
    const local = localFixtureTransport(getRuntimeHealth);

    render(
      <App
        platform={createMemoryPlatform()}
        runtime={createRuntimeComposition("local_real", local)}
      />,
    );

    expect(
      screen.getByLabelText("Local loopback service is being checked"),
    ).toBeVisible();
    expect(screen.getByText("Local real · Checking service")).toBeVisible();

    await act(async () => resolveHealth(HEALTHY_LOCAL_RUNTIME));

    expect(
      await screen.findByLabelText("Local loopback service available"),
    ).toBeVisible();
    expect(getRuntimeHealth).toHaveBeenCalledTimes(1);
  });

  it("reports local service unavailable when the health check fails", async () => {
    const getRuntimeHealth = vi.fn().mockRejectedValue(new Error("offline"));
    const local = localFixtureTransport(getRuntimeHealth);

    render(
      <App
        platform={createMemoryPlatform()}
        runtime={createRuntimeComposition("local_real", local)}
      />,
    );

    expect(
      await screen.findByLabelText("Local loopback service unavailable"),
    ).toBeVisible();
    expect(screen.getByText("Local real · Service unavailable")).toBeVisible();
    expect(getRuntimeHealth).toHaveBeenCalledTimes(1);
  });

  it("does not contact local-source APIs for a synthetic direct route", () => {
    const transport = createSyntheticTransport();
    const statusSpy = vi.spyOn(transport, "getCodexLocalSourceStatus");
    render(
      <App
        platform={createMemoryPlatform({ name: "local_sources" })}
        runtime={syntheticRuntime(transport)}
      />,
    );

    expect(
      screen.getByText("Local sources are disabled in synthetic preview"),
    ).toBeVisible();
    const closedState = screen.getByText("Local sources are disabled in synthetic preview")
      .closest(".ui-empty-state");
    expect(closedState).toHaveAttribute("data-tone", "closed");
    expect(closedState).toHaveAttribute("role", "status");
    expect(statusSpy).not.toHaveBeenCalled();
  });

  it("opens the methods and models lab from primary navigation", async () => {
    render(
      <App
        platform={createMemoryPlatform()}
        runtime={syntheticRuntime()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Methods & models" }));
    expect(
      await screen.findByRole("heading", { name: "Build useful metrics, then earn trust" }),
    ).toBeVisible();
  });

  it("opens a truthful synthetic job centre without inventing queue records", async () => {
    const transport = createSyntheticTransport();
    const listJobs = vi.spyOn(transport, "listAnalysisJobs");
    render(
      <App
        platform={createMemoryPlatform()}
        runtime={syntheticRuntime(transport)}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Job centre" }));
    expect(await screen.findByRole("heading", { name: "Analysis Job Centre" })).toBeVisible();
    expect(screen.getByText("No jobs ran")).toBeVisible();
    expect(listJobs).not.toHaveBeenCalled();
  });

  it("loads the authenticated job centre only after local health succeeds", async () => {
    const local = localFixtureTransport(async () => HEALTHY_LOCAL_RUNTIME);
    const listJobs = vi.fn(async () => ({ jobs: [], limit: 25, offset: 0 }));
    local.listAnalysisJobs = listJobs;
    render(
      <App
        platform={createMemoryPlatform({ name: "analysis_jobs" })}
        runtime={createRuntimeComposition("local_real", local)}
      />,
    );

    expect(await screen.findByLabelText("Local loopback service available")).toBeVisible();
    expect(await screen.findByText(/no durable jobs match this filter/i)).toBeVisible();
    expect(listJobs).toHaveBeenCalledWith(null, 25, 0, expect.any(AbortSignal));
  });

  it("renders project automation as explicitly non-operational in synthetic mode", async () => {
    const transport = createSyntheticTransport();
    const listGrants = vi.spyOn(transport, "listAutomationGrants");
    const listSessions = vi.spyOn(transport, "listProjectSessions");
    render(
      <App
        platform={createMemoryPlatform({
          name: "project_automation",
          projectId: SYNTHETIC_QUALITY_PROJECT_ID,
        })}
        runtime={syntheticRuntime(transport)}
      />,
    );

    expect(await screen.findByRole("heading", { name: "Project automation" })).toBeVisible();
    expect(screen.getByText("Automation is not running")).toBeVisible();
    expect(screen.getByRole("button", { name: "Projects" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(listGrants).not.toHaveBeenCalled();
    expect(listSessions).not.toHaveBeenCalled();
  });

  it("isolates a failed route, offers a truthful exit, and retries the same route", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const onExit = vi.fn();
    let shouldFail = true;
    function FailingRoute() {
      if (shouldFail) throw new Error("SYNTHETIC_ROUTE_FAILURE_CANARY");
      return <p>Recovered route</p>;
    }

    render(
      <main id="main-content" tabIndex={-1}>
        <RouteErrorBoundary exitLabel="Return to Discovery" onExit={onExit} resetKey="/failed-route">
          <FailingRoute />
        </RouteErrorBoundary>
      </main>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("This screen could not be loaded");
    expect(screen.getByRole("alert")).toHaveTextContent(/No provider error or session content is shown/);
    expect(document.body.textContent).not.toContain("SYNTHETIC_ROUTE_FAILURE_CANARY");
    fireEvent.click(screen.getByRole("button", { name: "Return to Discovery" }));
    expect(onExit).toHaveBeenCalledTimes(1);

    shouldFail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry screen" }));
    expect(await screen.findByText("Recovered route")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(document.getElementById("main-content")).toHaveFocus();
    consoleError.mockRestore();
  });

  it("omits a circular exit action when retry is the only truthful route recovery", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    function FailingRoute(): never {
      throw new Error("SYNTHETIC_DISCOVERY_FAILURE_CANARY");
    }

    render(
      <RouteErrorBoundary resetKey="/">
        <FailingRoute />
      </RouteErrorBoundary>,
    );

    expect(screen.getByRole("button", { name: "Retry screen" })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Return|Leave/ })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("SYNTHETIC_DISCOVERY_FAILURE_CANARY");
    consoleError.mockRestore();
  });

  it("renders the fictional project catalog in synthetic preview", async () => {
    const transport = createSyntheticTransport();
    const listSpy = vi.spyOn(transport, "listCodexSessions");
    const coverageSpy = vi.spyOn(transport, "getMetricCoverage");
    render(
      <App
        platform={createMemoryPlatform({ name: "projects" })}
        runtime={syntheticRuntime(transport)}
      />,
    );

    expect(await screen.findByText("Synthetic Metric Lab")).toBeVisible();
    expect(listSpy).toHaveBeenCalledTimes(1);
    expect(coverageSpy).toHaveBeenCalledWith("synthetic", expect.any(AbortSignal));
  });

  it("selects codex coverage for the local runtime", async () => {
    const local = localFixtureTransport(async () => HEALTHY_LOCAL_RUNTIME);
    local.listCodexSessions = vi.fn(async () => ({ sessions: [], limit: 100, offset: 0 }));
    const coverage = vi.spyOn(local, "getMetricCoverage").mockRejectedValue(
      new Error("Synthetic local coverage failure"),
    );
    render(
      <App
        platform={createMemoryPlatform({ name: "projects" })}
        runtime={createRuntimeComposition("local_real", local)}
      />,
    );

    expect(await screen.findByRole("heading", { name: "Metric coverage: Unknown" }))
      .toBeVisible();
    expect(coverage).toHaveBeenCalledWith("codex", expect.any(AbortSignal));
  });

  it("supports a direct fictional canonical metric route with an optional legacy QA disclosure", async () => {
    render(
      <App
        platform={createMemoryPlatform({
          name: "session_metrics",
          projectId: SYNTHETIC_QUALITY_PROJECT_ID,
          sessionId: SYNTHETIC_QUALITY_SESSION_ID,
          category: "prompt-quality",
        })}
        runtime={syntheticRuntime()}
      />,
    );

    expect(await screen.findByRole("heading", {
      name: "Measure the analyzed window, then estimate every eligible axis locally",
    })).toBeVisible();
    fireEvent.click(screen.getByText("Legacy coaching profile"));
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
        platform={createMemoryPlatform({
          name: "project_metrics",
          projectId: SYNTHETIC_QUALITY_PROJECT_ID,
          category: "prompt-quality",
        })}
        runtime={syntheticRuntime(transport)}
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
