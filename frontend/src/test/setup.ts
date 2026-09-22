import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  // Vitest globals stay disabled, so Testing Library never installs its own
  // automatic cleanup and detaching the DOM alone leaves every rendered root
  // mounted: it keeps polling, keeps its listeners and BroadcastChannels open
  // and keeps resolving transport promises into later tests in the same file.
  // Vitest runs afterEach hooks in reverse registration order, and this setup
  // file registers before any test module, so a suite's own hooks still run
  // first and can restore timers, spies and globals before this unmount.
  // cleanup() is synchronous and wraps unmount in a synchronous act(), so it is
  // also safe for a test that left fake timers installed.
  try {
    cleanup();
  } finally {
    // Containers a test attached by hand are outside Testing Library's registry,
    // so keep the original detach and history reset, even if an unmount throws.
    document.body.replaceChildren();
    window.history.replaceState(null, "", "/");
  }
});
