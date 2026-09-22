import { act, render, screen } from "@testing-library/react";
import { useEffect, useState } from "react";
import { describe, expect, it, vi } from "vitest";

// These cases are deliberately order dependent: each one leaves a root mounted
// and the next one asserts what the shared afterEach hook in ./setup.ts tore
// down. None of them may add a local cleanup() call, because that would prove
// the local hook instead of the centralized one.

const PING = "prompt-enhancer:probe-ping";

const teardown = { unmounts: 0 };
let pings = 0;
let lastRenderedBeats = 0;

function Probe({ label }: { label: string }) {
  const [beats, setBeats] = useState(0);

  useEffect(() => {
    const onPing = (): void => {
      pings += 1;
    };
    window.addEventListener(PING, onPing);
    const handle = window.setInterval(() => setBeats((count) => count + 1), 1_000);
    return () => {
      window.removeEventListener(PING, onPing);
      window.clearInterval(handle);
      teardown.unmounts += 1;
    };
  }, []);

  useEffect(() => {
    lastRenderedBeats = beats;
  }, [beats]);

  return <p>{`${label} beat ${beats}`}</p>;
}

function ping(): void {
  window.dispatchEvent(new Event(PING));
}

describe("shared test setup teardown", () => {
  it("keeps a mounted root live inside the test that rendered it", () => {
    render(<Probe label="first" />);

    expect(screen.getByText("first beat 0")).toBeVisible();
    ping();
    expect(pings).toBe(1);
    expect(teardown.unmounts).toBe(0);
  });

  it("unmounts the root the previous test left behind", () => {
    expect(teardown.unmounts).toBe(1);
    expect(document.body).toBeEmptyDOMElement();
    expect(screen.queryByText(/first beat/)).toBeNull();

    // The effect cleanup ran, so the window listener is gone with it.
    ping();
    expect(pings).toBe(1);
  });

  it("unmounts a root that a test abandoned with fake timers installed", () => {
    vi.useFakeTimers();
    render(<Probe label="timed" />);

    act(() => void vi.advanceTimersByTime(2_000));
    expect(screen.getByText("timed beat 2")).toBeVisible();
    expect(lastRenderedBeats).toBe(2);
    // Fake timers stay installed on purpose: the shared hook has to survive it.
  });

  it("unmounts across fake timers and stops the abandoned interval", () => {
    expect(vi.isFakeTimers()).toBe(true);
    vi.useRealTimers();

    expect(teardown.unmounts).toBe(2);
    expect(document.body).toBeEmptyDOMElement();
    expect(screen.queryByText(/timed beat/)).toBeNull();
    ping();
    expect(pings).toBe(1);
    // The interval was cleared at unmount, so no further beat was rendered.
    expect(lastRenderedBeats).toBe(2);
  });

  it("leaves a history entry behind for the next test", () => {
    window.history.pushState(null, "", "/example-cleanup-probe");

    expect(window.location.pathname).toBe("/example-cleanup-probe");
  });

  it("still resets history after unmounting rendered roots", () => {
    expect(window.location.pathname).toBe("/");
  });
});
