import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createSyntheticTransport } from "../shared/api/syntheticTransport";
import type { AppRoute, PlatformAdapter, PlatformNavigationAttempt } from "../shared/platform/platform";
import { createRuntimeComposition } from "../shared/platform/runtimeMode";
import type { AgentExitRisk } from "../features/agent/agentExitRisk";

const agentHarness = vi.hoisted(() => ({ callbacks: [] as Array<(risk: AgentExitRisk) => void> }));

vi.mock("../features/agent/AgentPage", () => ({
  AgentPage: ({ onExitRiskChange, windowMode }: { onExitRiskChange?: (risk: AgentExitRisk) => void; windowMode?: boolean }) => {
    if (onExitRiskChange) agentHarness.callbacks.push(onExitRiskChange);
    return <section aria-label={windowMode ? "Dedicated Agent fixture" : "Agent navigation fixture"}>
      <input aria-label="Agent draft" defaultValue="synthetic draft" />
    </section>;
  },
}));
vi.mock("../features/overview/OverviewPage", () => ({ OverviewPage: () => <section aria-label="Overview navigation fixture" /> }));

import { App } from "./App";

type TestPlatform = PlatformAdapter & {
  readonly navigations: readonly AppRoute[];
  emitAttempt(route: AppRoute, canRestore: boolean): PlatformNavigationAttempt;
};

function platform(initial: AppRoute): TestPlatform {
  let route = initial;
  const navigations: AppRoute[] = [];
  const listeners = new Set<(route: AppRoute) => void>();
  const attempts = new Set<(attempt: PlatformNavigationAttempt) => boolean>();
  return {
    currentRoute: () => route,
    get navigations() { return navigations; },
    navigate(next) { route = next; navigations.push(next); listeners.forEach((listener) => listener(next)); },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    subscribeNavigationAttempt(listener) { attempts.add(listener); return () => attempts.delete(listener); },
    emitAttempt(next, canRestore) {
      const attempt = { canRestore, route: next, resume: vi.fn(), source: "history" as const };
      [...attempts].forEach((listener) => listener(attempt));
      return attempt;
    },
  };
}

function runtime() { return createRuntimeComposition("synthetic_demo", createSyntheticTransport()); }
function report(risk: AgentExitRisk) { act(() => agentHarness.callbacks.at(-1)?.(risk)); }
async function dialog() { return screen.findByRole("dialog", { name: "Keep Agent changes?" }); }

describe("Agent exit-risk navigation", () => {
  beforeEach(() => { agentHarness.callbacks.length = 0; });

  it("allows clean navigation, but keeps dirty Agent work mounted on keep or Escape", async () => {
    const memory = platform({ name: "agent" });
    const cleanView = render(<App platform={memory} runtime={runtime()} />);
    const draft = await screen.findByRole("textbox", { name: "Agent draft" });
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    expect(memory.navigations).toEqual([{ name: "overview" }]);
    cleanView.unmount();

    const dirtyMemory = platform({ name: "agent" });
    render(<App platform={dirtyMemory} runtime={runtime()} />);
    const dirtyDraft = (await screen.findAllByRole("textbox", { name: "Agent draft" })).at(-1)!;
    dirtyDraft.focus();
    report({ hasActiveWork: false, hasUnsavedChanges: true });
    fireEvent.click(screen.getAllByRole("button", { name: "Overview" }).at(-1)!);
    fireEvent.click(within(await dialog()).getByRole("button", { name: "Keep Agent changes" }));
    expect(document.activeElement).toBe(dirtyDraft);
    expect(dirtyMemory.navigations).toEqual([]);
    fireEvent.click(screen.getAllByRole("button", { name: "Overview" }).at(-1)!);
    await dialog();
    expect(screen.getAllByRole("dialog", { hidden: true })).toHaveLength(1);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(dirtyMemory.navigations).toEqual([]);
    expect(screen.getAllByRole("textbox", { name: "Agent draft" }).at(-1)).toBe(dirtyDraft);
  });

  it("confirms direct and managed history navigation exactly once, with actionable foreign Agent copy", async () => {
    const memory = platform({ name: "agent" });
    const directView = render(<App platform={memory} runtime={runtime()} />);
    await screen.findByRole("region", { name: "Agent navigation fixture" });
    report({ hasActiveWork: false, hasUnsavedChanges: true });
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    const confirm = within(await dialog()).getByRole("button", { name: "Discard Agent changes and continue" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await screen.findByRole("region", { name: "Overview navigation fixture" });
    expect(memory.navigations).toEqual([{ name: "overview" }]);
    directView.unmount();

    const history = platform({ name: "agent" });
    const historyView = render(<App platform={history} runtime={runtime()} />);
    await screen.findByRole("region", { name: "Agent navigation fixture" });
    report({ hasActiveWork: false, hasUnsavedChanges: true });
    const managed = history.emitAttempt({ name: "overview" }, true);
    fireEvent.click(within(await dialog()).getByRole("button", { name: "Discard Agent changes and continue" }));
    expect(managed.resume).toHaveBeenCalledTimes(1);
    historyView.unmount();

    const foreign = platform({ name: "agent" });
    render(<App platform={foreign} runtime={runtime()} />);
    await screen.findByRole("region", { name: "Agent navigation fixture" });
    report({ hasActiveWork: false, hasUnsavedChanges: true });
    foreign.emitAttempt({ name: "overview" }, false);
    fireEvent.click(within(await dialog()).getByRole("button", { name: "Keep Agent changes" }));
    expect(screen.getAllByRole("button", { name: "Return to Agent" }).at(-1)).toBeVisible();
    act(() => {
      foreign.navigate({ name: "overview" });
      foreign.navigate({ name: "agent" });
    });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Return to Agent" })).toBeNull());
    report({ hasActiveWork: false, hasUnsavedChanges: true });
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    await dialog();
  });

  it("blocks refresh for unknown or active Agent work, without blocking active-only navigation", async () => {
    const reloads: boolean[] = [];
    const memory = platform({ name: "agent" });
    render(<App onReloadBlockedChange={(blocked) => reloads.push(blocked)} platform={memory} runtime={runtime()} />);
    expect(reloads.at(-1)).toBe(true);
    report({ hasActiveWork: true, hasUnsavedChanges: false });
    expect(reloads.at(-1)).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    await screen.findByRole("region", { name: "Overview navigation fixture" });
  });

  it("does not guard same Agent screens, but does guard a normal-to-dedicated replacement and ignores stale callbacks", async () => {
    const memory = platform({ name: "agent" });
    const view = render(<App platform={memory} runtime={runtime()} />);
    await screen.findByRole("region", { name: "Agent navigation fixture" });
    const stale = agentHarness.callbacks.at(-1)!;
    report({ hasActiveWork: false, hasUnsavedChanges: true });
    memory.navigate({ name: "agent" });
    expect(screen.queryByRole("dialog", { name: "Keep Agent changes?" })).toBeNull();
    memory.emitAttempt({ name: "agent", window: true }, true);
    await dialog();

    const replacement = platform({ name: "agent" });
    view.rerender(<App platform={replacement} runtime={runtime()} />);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Keep Agent changes?" })).toBeNull());
    report({ hasActiveWork: false, hasUnsavedChanges: true });
    act(() => stale({ hasActiveWork: false, hasUnsavedChanges: false }));
    fireEvent.click(screen.getAllByRole("button", { name: "Overview" }).at(-1)!);
    await dialog();
    expect(replacement.navigations).toEqual([]);
  });

  it("keeps the refresh notice and Agent exit guard available in a dedicated window", async () => {
    const memory = platform({ name: "agent", window: true });
    render(<App interfaceRefreshNotice={<div>Synthetic refresh notice</div>} platform={memory} runtime={runtime()} />);
    await screen.findByRole("region", { name: "Dedicated Agent fixture" });
    expect(screen.getByText("Synthetic refresh notice")).toBeVisible();
    report({ hasActiveWork: false, hasUnsavedChanges: true });
    memory.emitAttempt({ name: "overview" }, false);
    fireEvent.click(within(await dialog()).getByRole("button", { name: "Keep Agent changes" }));
    fireEvent.click(screen.getByRole("button", { name: "Return to Agent" }));
    expect(memory.navigations).toEqual([{ name: "agent", window: true }]);
  });
});
