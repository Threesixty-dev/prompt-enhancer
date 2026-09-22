import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState, type ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { RetryableLazyFeature } from "./RetryableLazyFeature";

describe("RetryableLazyFeature", () => {
  it("does not start loading until its optional surface is mounted", () => {
    const load = vi.fn(async () => ({ default: () => <p>Synthetic feature</p> }));
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <main>
          <p>Primary agent conversation remains available</p>
          <button onClick={() => setOpen(true)} type="button">Open optional surface</button>
          {open && <RetryableLazyFeature label="Synthetic panel" load={load}>
            {(Feature) => <Feature />}
          </RetryableLazyFeature>}
        </main>
      );
    }
    render(<Harness />);

    expect(load).not.toHaveBeenCalled();
    expect(screen.getByText("Primary agent conversation remains available")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Open optional surface" }));
    expect(load).toHaveBeenCalledOnce();
  });

  it("shows a scoped loading state and renders the loaded optional feature", async () => {
    let resolve: ((value: { default: () => ReactElement }) => void) | undefined;
    const load = vi.fn(() => new Promise<{ default: () => ReactElement }>((done) => { resolve = done; }));
    render(
      <RetryableLazyFeature label="Synthetic panel" load={load}>
        {(Feature) => <Feature />}
      </RetryableLazyFeature>,
    );

    expect(load).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveTextContent("Loading Synthetic panel…");
    resolve?.({ default: () => <p>Loaded synthetic panel</p> });
    expect(await screen.findByText("Loaded synthetic panel")).toBeVisible();
  });

  it("contains a rejected download without advertising an in-place retry", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const load = vi.fn().mockRejectedValue(new Error("SYNTHETIC_CHUNK_FAILURE"));
    render(
      <main>
        <p>Agent conversation still usable</p>
        <RetryableLazyFeature label="Synthetic panel" load={load}>
          {(Feature) => <Feature />}
        </RetryableLazyFeature>
      </main>,
    );

    const failure = await screen.findByRole("alert");
    expect(failure).toHaveTextContent("Unable to load Synthetic panel");
    expect(failure).not.toHaveTextContent("SYNTHETIC_CHUNK_FAILURE");
    expect(failure).toHaveTextContent("Preserve or copy unsent drafts and unsaved file work before explicitly reloading the app.");
    expect(screen.getByText("Agent conversation still usable")).toBeVisible();
    expect(load).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /Retry|Reload/u })).toBeNull();
    consoleError.mockRestore();
  });

  it("keeps a loaded feature mounted across ordinary parent rerenders", async () => {
    const load = vi.fn(async () => ({ default: function StatefulFeature() {
      const [count, setCount] = useState(0);
      return <button onClick={() => setCount((value) => value + 1)} type="button">Feature state {count}</button>;
    } }));
    const { rerender } = render(
      <RetryableLazyFeature label="Synthetic panel" load={load}>
        {(Feature) => <Feature />}
      </RetryableLazyFeature>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Feature state 0" }));
    rerender(
      <RetryableLazyFeature label="Renamed synthetic panel" load={load}>
        {(Feature) => <Feature />}
      </RetryableLazyFeature>,
    );
    expect(screen.getByRole("button", { name: "Feature state 1" })).toBeVisible();
    expect(load).toHaveBeenCalledOnce();
  });

  it("retries one failed boundary without resetting a neighboring loaded feature", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    let renderFailure = true;
    const failedLoad = vi.fn(async () => ({ default: () => {
      if (renderFailure) throw new Error("SYNTHETIC_LEFT_RENDER_FAILURE");
      return <p>Recovered left feature</p>;
    } }));
    const healthyLoad = vi.fn(async () => ({ default: function HealthyFeature() {
      const [count, setCount] = useState(0);
      return <button onClick={() => setCount((value) => value + 1)} type="button">Healthy feature {count}</button>;
    } }));
    render(
      <>
        <RetryableLazyFeature label="Left feature" load={failedLoad}>{(Feature) => <Feature />}</RetryableLazyFeature>
        <RetryableLazyFeature label="Right feature" load={healthyLoad}>{(Feature) => <Feature />}</RetryableLazyFeature>
      </>,
    );

    await screen.findByRole("alert");
    fireEvent.click(await screen.findByRole("button", { name: "Healthy feature 0" }));
    renderFailure = false;
    fireEvent.click(within(screen.getByRole("alert")).getByRole("button", { name: "Retry Left feature" }));
    expect(await screen.findByText("Recovered left feature")).toBeVisible();
    expect(screen.getByRole("button", { name: "Healthy feature 1" })).toBeVisible();
    expect(healthyLoad).toHaveBeenCalledOnce();
    consoleError.mockRestore();
  });

  it("uses the latest loader after a failed optional feature is replaced", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const rejected = vi.fn().mockRejectedValue(new Error("SYNTHETIC_STALE_FAILURE"));
    const replacement = vi.fn(async () => ({ default: () => <p>Latest feature props rendered</p> }));
    const { rerender } = render(
      <RetryableLazyFeature label="Synthetic panel" load={rejected}>{(Feature) => <Feature />}</RetryableLazyFeature>,
    );

    await screen.findByRole("alert");
    rerender(
      <RetryableLazyFeature label="Replacement panel" load={replacement}>{(Feature) => <Feature />}</RetryableLazyFeature>,
    );
    expect(await screen.findByText("Latest feature props rendered")).toBeVisible();
    expect(replacement).toHaveBeenCalledOnce();
    consoleError.mockRestore();
  });

  it("ignores a pending optional import after its surface closes", async () => {
    let resolve: ((value: { default: () => ReactElement }) => void) | undefined;
    const rendered = vi.fn(() => <p>Closed feature must not render</p>);
    const load = vi.fn(() => new Promise<{ default: () => ReactElement }>((done) => { resolve = done; }));
    const { unmount } = render(
      <RetryableLazyFeature label="Closing panel" load={load}>{(Feature) => <Feature />}</RetryableLazyFeature>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Loading Closing panel…");
    unmount();
    resolve?.({ default: rendered });
    await waitFor(() => expect(rendered).not.toHaveBeenCalled());
    expect(document.body).not.toHaveTextContent("Closed feature must not render");
  });
});
