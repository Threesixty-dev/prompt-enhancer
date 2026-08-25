import { afterEach, describe, expect, it, vi } from "vitest";
import { createBrowserPlatform } from "./browserPlatform";

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
    platform.subscribe(listener);

    platform.navigate({ name: "overview" });

    expect(pushState).not.toHaveBeenCalled();
    expect(listener).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe("/overview/");
  });

  it("pushes and emits exactly once for a different destination", () => {
    window.history.replaceState(null, "", "/overview");
    const pushState = vi.spyOn(window.history, "pushState");
    const listener = vi.fn();
    const platform = createBrowserPlatform(window);
    platform.subscribe(listener);

    platform.navigate({ name: "sessions" });

    expect(pushState).toHaveBeenCalledWith(null, "", "/sessions");
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith({ name: "sessions" });
    expect(window.location.pathname).toBe("/sessions");
  });

  it("repairs a malformed path with multiple trailing slashes", () => {
    window.history.replaceState(null, "", "/overview//");
    const pushState = vi.spyOn(window.history, "pushState");
    const listener = vi.fn();
    const platform = createBrowserPlatform(window);
    platform.subscribe(listener);

    platform.navigate({ name: "overview" });

    expect(pushState).toHaveBeenCalledWith(null, "", "/overview");
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith({ name: "overview" });
    expect(window.location.pathname).toBe("/overview");
  });
});
