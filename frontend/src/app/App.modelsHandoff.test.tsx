import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createSyntheticTransport } from "../shared/api/syntheticTransport";
import { routePath, type AppRoute, type PlatformAdapter } from "../shared/platform/platform";
import { createRuntimeComposition } from "../shared/platform/runtimeMode";

vi.mock("../features/local-models/LocalModelsPage", () => ({
  LocalModelsPage: ({ onOpenAgentChat, onTemporaryChatDirtyChange }: {
    onOpenAgentChat?: (modelAlias: string | null) => void;
    onTemporaryChatDirtyChange?: (dirty: boolean) => void;
  }) => (
    <>
      <button onClick={() => onOpenAgentChat?.("synthetic-handoff-model")} type="button">Open saved Agent setup</button>
      <button onClick={() => onTemporaryChatDirtyChange?.(true)} type="button">Mark temporary chat dirty</button>
    </>
  ),
}));

vi.mock("../features/agent/AgentPage", () => ({
  AgentPage: ({
    newChatIntent,
    onNewChatIntentConsumed,
    onExitRiskChange,
  }: {
    newChatIntent?: { requestId: number; modelAlias: string | null } | null;
    onNewChatIntentConsumed?: (requestId: number) => void;
    onExitRiskChange?: (risk: { hasUnsavedChanges: boolean; hasActiveWork: boolean }) => void;
  }) => (
    <section aria-label="Agent setup fixture">
      <output data-alias={newChatIntent?.modelAlias ?? ""} data-request={newChatIntent?.requestId ?? ""} />
      {newChatIntent && <button onClick={() => onNewChatIntentConsumed?.(newChatIntent.requestId)} type="button">Consume setup intent</button>}
      <button onClick={() => onExitRiskChange?.({ hasUnsavedChanges: true, hasActiveWork: false })} type="button">Mark Agent unsaved</button>
    </section>
  ),
}));

import { App } from "./App";

function memoryPlatform(initialRoute: AppRoute): PlatformAdapter & { readonly navigations: readonly AppRoute[] } {
  let route = initialRoute;
  const navigations: AppRoute[] = [];
  const listeners = new Set<(next: AppRoute) => void>();
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
  };
}

describe("Models to Agent setup handoff", () => {
  it("navigates with an in-memory alias only and opens explicit Agent setup", async () => {
    const platform = memoryPlatform({ name: "models" });
    const transport = createSyntheticTransport();
    render(<App platform={platform} runtime={createRuntimeComposition("synthetic_demo", transport)} />);

    fireEvent.click(await screen.findByRole("button", { name: "Open saved Agent setup" }));

    expect(platform.currentRoute()).toEqual({ name: "agent" });
    expect(platform.navigations).toEqual([{ name: "agent" }]);
    expect(routePath(platform.currentRoute())).toBe("/agent");
    const intent = (await screen.findByRole("region", { name: "Agent setup fixture" })).querySelector("output");
    expect(intent).not.toBeNull();
    expect(intent).toHaveAttribute("data-alias", "synthetic-handoff-model");
    expect(intent).toHaveAttribute("data-request", "1");
    fireEvent.click(screen.getByRole("button", { name: "Consume setup intent" }));
    expect(intent).toHaveAttribute("data-alias", "");
  });

  it("does not deliver a pending setup selection after its transport or platform is replaced", async () => {
    const firstPlatform = memoryPlatform({ name: "models" });
    const firstTransport = createSyntheticTransport();
    const firstRuntime = createRuntimeComposition("synthetic_demo", firstTransport);
    const view = render(<App platform={firstPlatform} runtime={firstRuntime} />);
    fireEvent.click(await screen.findByRole("button", { name: "Open saved Agent setup" }));
    expect((await screen.findByRole("region", { name: "Agent setup fixture" })).querySelector("output"))
      .toHaveAttribute("data-alias", "synthetic-handoff-model");

    const secondPlatform = memoryPlatform({ name: "agent" });
    view.rerender(<App platform={secondPlatform} runtime={createRuntimeComposition("synthetic_demo", createSyntheticTransport())} />);
    await waitFor(() => expect(screen.getByRole("region", { name: "Agent setup fixture" }).querySelector("output"))
      .toHaveAttribute("data-alias", ""));
  });

  it("drops an unconsumed intent when external history navigation leaves Agent", async () => {
    const platform = memoryPlatform({ name: "models" });
    render(<App platform={platform} runtime={createRuntimeComposition("synthetic_demo", createSyntheticTransport())} />);
    fireEvent.click(await screen.findByRole("button", { name: "Open saved Agent setup" }));
    expect((await screen.findByRole("region", { name: "Agent setup fixture" })).querySelector("output"))
      .toHaveAttribute("data-alias", "synthetic-handoff-model");

    platform.navigate({ name: "models" });
    await screen.findByRole("button", { name: "Open saved Agent setup" });
    platform.navigate({ name: "agent" });
    await waitFor(() => expect(screen.getByRole("region", { name: "Agent setup fixture" }).querySelector("output"))
      .toHaveAttribute("data-alias", ""));
  });

  it("keeps a dirty temporary Models chat mounted until explicit discard", async () => {
    const platform = memoryPlatform({ name: "models" });
    render(<App platform={platform} runtime={createRuntimeComposition("synthetic_demo", createSyntheticTransport())} />);
    fireEvent.click(await screen.findByRole("button", { name: "Mark temporary chat dirty" }));
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    const dialog = await screen.findByRole("dialog", { name: "Keep temporary Models chat?" });
    expect(platform.currentRoute()).toEqual({ name: "models" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Keep temporary chat" }));
    expect(screen.getByRole("button", { name: "Mark temporary chat dirty" })).toBeVisible();
    expect(platform.currentRoute()).toEqual({ name: "models" });
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    fireEvent.click(await screen.findByRole("button", { name: "Discard temporary chat and continue" }));
    await waitFor(() => expect(platform.currentRoute()).toEqual({ name: "overview" }));
  });

  it("guards unsaved Agent changes but not a same-Agent navigation", async () => {
    const platform = memoryPlatform({ name: "agent" });
    render(<App platform={platform} runtime={createRuntimeComposition("synthetic_demo", createSyntheticTransport())} />);
    fireEvent.click(await screen.findByRole("button", { name: "Mark Agent unsaved" }));
    fireEvent.click(screen.getByRole("button", { name: "Agent" }));
    expect(screen.queryByRole("dialog", { name: "Keep Agent changes?" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    expect(await screen.findByRole("dialog", { name: "Keep Agent changes?" })).toBeVisible();
  });
});
