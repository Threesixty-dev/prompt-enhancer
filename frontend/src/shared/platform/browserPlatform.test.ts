import { afterEach, describe, expect, it, vi } from "vitest";
import { createBrowserPlatform } from "./browserPlatform";
import type { PlatformNavigationAttempt } from "./platform";

afterEach(() => {
  window.history.replaceState(null, "", "/");
  vi.restoreAllMocks();
});

describe("createBrowserPlatform", () => {
  it("does not add a history entry or emit when the requested path is already current", () => {
    window.history.replaceState(null, "", "/overview/");
    const pushState = vi.spyOn(window.history, "pushState");
    const listener = vi.fn();
    const platform = createBrowserPlatform(window);
    const unsubscribe = platform.subscribe(listener);

    platform.navigate({ name: "overview" });

    expect(pushState).not.toHaveBeenCalled();
    expect(listener).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe("/overview/");
    unsubscribe();
  });

  it("pushes and emits exactly once for a different destination", () => {
    window.history.replaceState(null, "", "/overview");
    const pushState = vi.spyOn(window.history, "pushState");
    const listener = vi.fn();
    const platform = createBrowserPlatform(window);
    const unsubscribe = platform.subscribe(listener);

    platform.navigate({ name: "sessions" });

    expect(pushState).toHaveBeenCalledWith(expect.objectContaining({ __prompt_enhancer_route_index_v1: 1 }), "", "/sessions");
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith({ name: "sessions" });
    expect(window.location.pathname).toBe("/sessions");
    unsubscribe();
  });

  it("repairs a malformed path with multiple trailing slashes", () => {
    window.history.replaceState(null, "", "/overview//");
    const pushState = vi.spyOn(window.history, "pushState");
    const listener = vi.fn();
    const platform = createBrowserPlatform(window);
    const unsubscribe = platform.subscribe(listener);

    platform.navigate({ name: "overview" });

    expect(pushState).toHaveBeenCalledWith(expect.objectContaining({ __prompt_enhancer_route_index_v1: 1 }), "", "/overview");
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith({ name: "overview" });
    expect(window.location.pathname).toBe("/overview");
    unsubscribe();
  });

  it("keeps an unknown address in a content-free recovery route until the user leaves it", () => {
    window.history.replaceState(null, "", "/unexpected/private-shaped-value");
    const platform = createBrowserPlatform(window);

    expect(platform.currentRoute()).toEqual({ name: "not_found" });

    platform.navigate({ name: "overview" });

    expect(window.location.pathname).toBe("/overview");
    expect(platform.currentRoute()).toEqual({ name: "overview" });
  });

  it("emits allowlisted and content-free recovery routes for browser back/forward events", () => {
    window.history.replaceState(null, "", "/overview");
    const platform = createBrowserPlatform(window);
    const listener = vi.fn();
    const unsubscribe = platform.subscribe(listener);

    window.history.replaceState(null, "", "/sessions");
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(listener).toHaveBeenLastCalledWith({ name: "sessions" });

    window.history.replaceState(null, "", "/unexpected/private-shaped-value");
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(listener).toHaveBeenLastCalledWith({ name: "not_found" });
    expect(listener.mock.lastCall?.[0]).toEqual({ name: "not_found" });
    unsubscribe();
  });

  it("owns one popstate listener only while at least one subscriber exists", () => {
    const add = vi.spyOn(window, "addEventListener");
    const remove = vi.spyOn(window, "removeEventListener");
    const platform = createBrowserPlatform(window);
    const unsubscribeA = platform.subscribe(() => undefined);
    const unsubscribeB = platform.subscribe(() => undefined);

    expect(add.mock.calls.filter(([type]) => type === "popstate")).toHaveLength(1);
    unsubscribeA();
    expect(remove.mock.calls.filter(([type]) => type === "popstate")).toHaveLength(0);
    unsubscribeB();
    expect(remove.mock.calls.filter(([type]) => type === "popstate")).toHaveLength(1);
  });

  it("restores an owned Back entry before confirmation, then resumes the exact original delta", () => {
    window.history.replaceState(null, "", "/models");
    const platform = createBrowserPlatform(window);
    const routes = vi.fn();
    const unsubscribe = platform.subscribe(routes);
    const chain = (window.history.state as Record<string, unknown>).__prompt_enhancer_route_chain_v1 as string;
    platform.navigate({ name: "overview" });
    const attempts: PlatformNavigationAttempt[] = [];
    const attemptListener = vi.fn((attempt: PlatformNavigationAttempt) => {
      attempts.push(attempt);
      return false;
    });
    const removeAttempt = platform.subscribeNavigationAttempt!(attemptListener);
    const go = vi.spyOn(window.history, "go").mockImplementation(() => undefined);

    window.history.replaceState({ __prompt_enhancer_route_chain_v1: chain, __prompt_enhancer_route_index_v1: 0 }, "", "/models");
    window.dispatchEvent(new PopStateEvent("popstate", { state: { __prompt_enhancer_route_chain_v1: chain, __prompt_enhancer_route_index_v1: 0 } }));
    expect(attemptListener).toHaveBeenCalledOnce();
    expect(routes).toHaveBeenCalledTimes(1); // only direct navigate emitted
    expect(go).toHaveBeenLastCalledWith(1);

    const attempt = attempts[0]!;
    window.history.replaceState({ __prompt_enhancer_route_chain_v1: chain, __prompt_enhancer_route_index_v1: 1 }, "", "/overview");
    window.dispatchEvent(new PopStateEvent("popstate", { state: { __prompt_enhancer_route_chain_v1: chain, __prompt_enhancer_route_index_v1: 1 } }));
    attempt.resume();
    expect(go).toHaveBeenLastCalledWith(-1);
    window.history.replaceState({ __prompt_enhancer_route_chain_v1: chain, __prompt_enhancer_route_index_v1: 0 }, "", "/models");
    window.dispatchEvent(new PopStateEvent("popstate", { state: { __prompt_enhancer_route_chain_v1: chain, __prompt_enhancer_route_index_v1: 0 } }));
    expect(routes).toHaveBeenLastCalledWith({ name: "models" });
    removeAttempt();
    unsubscribe();
  });

  it("holds a foreign primitive-state pop without overwriting it or emitting a route", () => {
    window.history.replaceState("foreign-state", "", "/models");
    const platform = createBrowserPlatform(window);
    const routes = vi.fn();
    const unsubscribe = platform.subscribe(routes);
    const attempts: PlatformNavigationAttempt[] = [];
    const attemptListener = vi.fn((attempt: PlatformNavigationAttempt) => {
      attempts.push(attempt);
      return false;
    });
    const removeAttempt = platform.subscribeNavigationAttempt!(attemptListener);
    const go = vi.spyOn(window.history, "go").mockImplementation(() => undefined);

    window.history.replaceState("foreign-state", "", "/overview");
    window.dispatchEvent(new PopStateEvent("popstate", { state: "foreign-state" }));
    expect(attemptListener).toHaveBeenCalledOnce();
    expect(attempts[0]?.canRestore).toBe(false);
    expect(window.history.state).toBe("foreign-state");
    expect(go).not.toHaveBeenCalled();
    expect(routes).not.toHaveBeenCalled();
    removeAttempt();
    unsubscribe();
  });

  it("treats a same-index different-path pop as foreign and never calls history.go(0)", () => {
    window.history.replaceState(null, "", "/models");
    const platform = createBrowserPlatform(window);
    const unsubscribe = platform.subscribe(() => undefined);
    const chain = (window.history.state as Record<string, unknown>).__prompt_enhancer_route_chain_v1 as string;
    const attempts: PlatformNavigationAttempt[] = [];
    const removeAttempt = platform.subscribeNavigationAttempt!((attempt) => { attempts.push(attempt); return false; });
    const go = vi.spyOn(window.history, "go").mockImplementation(() => undefined);
    window.history.replaceState({ __prompt_enhancer_route_chain_v1: chain, __prompt_enhancer_route_index_v1: 0 }, "", "/overview");
    window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
    expect(attempts[0]?.canRestore).toBe(false);
    expect(go).not.toHaveBeenCalled();
    removeAttempt();
    unsubscribe();
  });
});
