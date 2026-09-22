import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createSyntheticTransport } from "../shared/api/syntheticTransport";
import type { AppRoute, PlatformAdapter, PlatformNavigationAttempt } from "../shared/platform/platform";
import { createRuntimeComposition } from "../shared/platform/runtimeMode";

const modelsHarness = vi.hoisted(() => ({
  callbacks: [] as Array<{
    onOpenAgentChat?: (modelAlias: string | null) => void;
    onTemporaryChatDirtyChange?: (dirty: boolean) => void;
  }>,
}));

vi.mock("../features/local-models/LocalModelsPage", () => ({
  LocalModelsPage: (props: {
    onOpenAgentChat?: (modelAlias: string | null) => void;
    onTemporaryChatDirtyChange?: (dirty: boolean) => void;
  }) => {
    modelsHarness.callbacks.push(props);
    return (
      <section aria-label="Models navigation fixture">
        <button onClick={() => props.onTemporaryChatDirtyChange?.(true)} type="button">Mark Models dirty</button>
        <button onClick={() => props.onOpenAgentChat?.("synthetic-model")} type="button">Continue saved Agent setup</button>
        <button type="button">Cancel saved Agent setup</button>
      </section>
    );
  },
}));

vi.mock("../features/overview/OverviewPage", () => ({
  OverviewPage: () => <section aria-label="Overview navigation fixture">Overview fixture</section>,
}));

vi.mock("../features/agent/AgentPage", () => ({
  AgentPage: () => <section aria-label="Agent navigation fixture">Agent fixture</section>,
}));

import { App } from "./App";

type AttemptResult = { attempt: PlatformNavigationAttempt; decisions: boolean[] };
type TestPlatform = PlatformAdapter & {
  readonly navigations: readonly AppRoute[];
  emitAttempt(route: AppRoute, canRestore: boolean): AttemptResult;
};

function memoryPlatform(initialRoute: AppRoute): TestPlatform {
  let route = initialRoute;
  const navigations: AppRoute[] = [];
  const listeners = new Set<(next: AppRoute) => void>();
  const attemptListeners = new Set<(attempt: PlatformNavigationAttempt) => boolean>();
  return {
    currentRoute: () => route,
    get navigations() { return navigations; },
    navigate(next) {
      route = next;
      navigations.push(next);
      listeners.forEach((listener) => listener(next));
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    subscribeNavigationAttempt(listener) {
      attemptListeners.add(listener);
      return () => attemptListeners.delete(listener);
    },
    emitAttempt(next, canRestore) {
      const attempt: PlatformNavigationAttempt = { canRestore, route: next, resume: vi.fn(), source: "history" };
      return { attempt, decisions: [...attemptListeners].map((listener) => listener(attempt)) };
    },
  };
}

function runtime() {
  return createRuntimeComposition("synthetic_demo", createSyntheticTransport());
}

function currentModelsCallbacks() {
  const callbacks = modelsHarness.callbacks.at(-1);
  if (!callbacks) throw new Error("Models callback fixture did not render");
  return callbacks;
}

async function guardDialog() {
  return screen.findByRole("dialog", { name: "Keep temporary Models chat?" });
}

describe("Models temporary-chat navigation ownership", () => {
  beforeEach(() => { modelsHarness.callbacks.length = 0; });

  it("drops a stale guard when its platform and transport owner are replaced, while an old false report cannot clear the new owner", async () => {
    const firstPlatform = memoryPlatform({ name: "models" });
    const firstRuntime = runtime();
    const view = render(<App platform={firstPlatform} runtime={firstRuntime} />);
    await screen.findByRole("region", { name: "Models navigation fixture" });
    const firstCallbacks = currentModelsCallbacks();
    act(() => firstCallbacks.onTemporaryChatDirtyChange?.(true));
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    const staleConfirm = within(await guardDialog()).getByRole("button", { name: "Discard temporary chat and continue" });

    const secondPlatform = memoryPlatform({ name: "models" });
    view.rerender(<App platform={secondPlatform} runtime={runtime()} />);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Keep temporary Models chat?" })).toBeNull());
    const secondCallbacks = currentModelsCallbacks();
    act(() => {
      secondCallbacks.onTemporaryChatDirtyChange?.(true);
      firstCallbacks.onTemporaryChatDirtyChange?.(false);
    });
    fireEvent.click(staleConfirm);
    expect(firstPlatform.navigations).toEqual([]);
    expect(secondPlatform.navigations).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    await expect(await guardDialog()).toBeVisible();
  });

  it("lets the handoff callback bypass the generic guard once, while a no-op handoff boundary leaves sidebar navigation guarded", async () => {
    const platform = memoryPlatform({ name: "models" });
    const handoffView = render(<App platform={platform} runtime={runtime()} />);
    await screen.findByRole("region", { name: "Models navigation fixture" });
    fireEvent.click(screen.getByRole("button", { name: "Mark Models dirty" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue saved Agent setup" }));
    await expect(await screen.findByRole("region", { name: "Agent navigation fixture" })).toBeVisible();
    expect(platform.navigations).toEqual([{ name: "agent" }]);
    expect(screen.queryByRole("dialog", { name: "Keep temporary Models chat?" })).toBeNull();
    handoffView.unmount();

    const guardedPlatform = memoryPlatform({ name: "models" });
    render(<App platform={guardedPlatform} runtime={runtime()} />);
    await screen.findByRole("region", { name: "Models navigation fixture" });
    fireEvent.click(screen.getByRole("button", { name: "Mark Models dirty" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel saved Agent setup" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Overview" }).at(-1)!);
    await expect(await guardDialog()).toBeVisible();
    expect(guardedPlatform.navigations).toEqual([]);
  });

  it("does not prompt when Models is selected again", async () => {
    const platform = memoryPlatform({ name: "models" });
    render(<App platform={platform} runtime={runtime()} />);
    await screen.findByRole("region", { name: "Models navigation fixture" });
    fireEvent.click(screen.getByRole("button", { name: "Mark Models dirty" }));
    fireEvent.click(screen.getByRole("button", { name: "Models" }));
    expect(screen.queryByRole("dialog", { name: "Keep temporary Models chat?" })).toBeNull();
    expect(platform.navigations).toEqual([{ name: "models" }]);
  });

  it("uses a retained direct-navigation confirmation once without falling back to Models", async () => {
    const platform = memoryPlatform({ name: "models" });
    render(<App platform={platform} runtime={runtime()} />);
    await screen.findByRole("region", { name: "Models navigation fixture" });
    fireEvent.click(screen.getByRole("button", { name: "Mark Models dirty" }));
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    const confirm = within(await guardDialog()).getByRole("button", { name: "Discard temporary chat and continue" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await expect(await screen.findByRole("region", { name: "Overview navigation fixture" })).toBeVisible();
    expect(platform.navigations).toEqual([{ name: "overview" }]);
  });

  it("keeps only the latest blocked history attempt and resumes only that attempt", async () => {
    const platform = memoryPlatform({ name: "models" });
    render(<App platform={platform} runtime={runtime()} />);
    await screen.findByRole("region", { name: "Models navigation fixture" });
    fireEvent.click(screen.getByRole("button", { name: "Mark Models dirty" }));
    let first!: AttemptResult;
    let second!: AttemptResult;
    act(() => {
      first = platform.emitAttempt({ name: "overview" }, true);
      second = platform.emitAttempt({ name: "agent" }, true);
    });
    expect(first.decisions).toEqual([false]);
    expect(second.decisions).toEqual([false]);
    fireEvent.click(within(await guardDialog()).getByRole("button", { name: "Discard temporary chat and continue" }));
    expect(first.attempt.resume).not.toHaveBeenCalled();
    expect(second.attempt.resume).toHaveBeenCalledTimes(1);
    expect(platform.navigations).toEqual([]);
  });

  it("keeps foreign-history notices actionable without discarding the dirty Models owner", async () => {
    const platform = memoryPlatform({ name: "models" });
    render(<App platform={platform} runtime={runtime()} />);
    await screen.findByRole("region", { name: "Models navigation fixture" });
    fireEvent.click(screen.getByRole("button", { name: "Mark Models dirty" }));
    let kept!: AttemptResult;
    act(() => { kept = platform.emitAttempt({ name: "overview" }, false); });
    fireEvent.click(within(await guardDialog()).getByRole("button", { name: "Keep temporary chat" }));
    expect(kept.attempt.resume).not.toHaveBeenCalled();
    await expect(screen.getByRole("button", { name: "Return to Models" })).toBeVisible();

    let escaped!: AttemptResult;
    act(() => { escaped = platform.emitAttempt({ name: "agent" }, false); });
    await expect(await guardDialog()).toBeVisible();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Keep temporary Models chat?" })).toBeNull());
    expect(escaped.attempt.resume).not.toHaveBeenCalled();
    const returnToModels = screen.getByRole("button", { name: "Return to Models" });
    fireEvent.click(returnToModels);
    expect(platform.navigations).toEqual([{ name: "models" }]);
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    await expect(await guardDialog()).toBeVisible();
  });
});
