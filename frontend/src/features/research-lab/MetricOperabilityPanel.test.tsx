import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import {
  createSyntheticMetricOperabilityCatalog,
  MetricOperabilityDefinitionsOutOfDateError,
} from "../../shared/api/metricOperabilityContract";
import { TransportError } from "../../shared/api/httpTransport";
import { MetricOperabilityPanel } from "./MetricOperabilityPanel";

describe("MetricOperabilityPanel", () => {
  function deferred<T>() {
    let resolve!: (value: T) => void;
    let reject!: (error: unknown) => void;
    const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
  }

  function requiredSignal(signal: AbortSignal | undefined): AbortSignal {
    expect(signal).toBeDefined();
    if (signal === undefined) throw new Error("Expected catalog request signal");
    return signal;
  }

  it("shows the exact v6 18/0/2 partition and keeps model estimates separate", async () => {
    const transport = createSyntheticTransport();
    const sessions = vi.spyOn(transport, "listCodexSessions");

    const rendered = render(<MetricOperabilityPanel transport={transport} />);

    expect(await screen.findByRole("heading", {
      name: "What can produce measured evidence today",
    })).toBeVisible();
    const summary = screen.getByLabelText("Metric operability summary");
    expect(within(summary).getByText("Measured paths shipped").closest("div")).toHaveTextContent("18");
    expect(within(summary).getByText("Need project profile").closest("div")).toHaveTextContent("0");
    expect(screen.queryByRole("heading", { name: "Project profile needed" })).toBeNull();
    expect(within(summary).getByText("Need source adapter").closest("div")).toHaveTextContent("2");
    expect(screen.getByRole("heading", { name: "Unavailable pending provider adapter" })).toBeVisible();
    expect(screen.getByText(/are explicitly unavailable pending a provider adapter/i)).toBeVisible();
    expect(within(summary).getByText("Model-authored metrics").closest("div")).toHaveTextContent("0");
    expect(screen.getByText("Constraint precision").closest("li")).toHaveAttribute(
      "data-operability-state",
      "available_when_evidence_exists",
    );
    expect(screen.getByText("Agent claim grounding").closest("li")).toHaveAttribute(
      "data-operability-state",
      "provider_adapter_required",
    );
    expect(screen.getAllByText("Separate experimental estimate may be available")).toHaveLength(8);
    expect(screen.getByText("20/20 contracts bound to the current client")).toBeVisible();
    expect(sessions).not.toHaveBeenCalled();
  });

  it("shows the v6 reviewed-verification scope without admitting unsupported success", async () => {
    const transport = createSyntheticTransport();
    const catalog = createSyntheticMetricOperabilityCatalog();
    transport.getMetricOperabilityCatalog = vi.fn(async () => catalog);

    render(<MetricOperabilityPanel transport={transport} />);

    expect(await screen.findByText("All-20 release gate · metric-operability-v6")).toBeVisible();
    const summary = screen.getByLabelText("Metric operability summary");
    expect(within(summary).getByText("Measured paths shipped").closest("div")).toHaveTextContent("18");
    expect(within(summary).getByText("Need source adapter").closest("div")).toHaveTextContent("2");
    const row = screen.getByText("Requirement action traceability").closest("li");
    expect(row).not.toBeNull();
    expect(row).toHaveAttribute("data-operability-state", "available_when_evidence_exists");
    expect(row).toHaveTextContent("No model estimate is used");
    expect(row).toHaveTextContent(/complete compatible Claude transcript/i);
    expect(row).toHaveTextContent(/confirmed requirement plan/i);
    expect(row).toHaveTextContent(/reviewed requirement-action links/i);
    expect(row).toHaveTextContent(/hook-only.*not admitted/i);
    expect(row).toHaveTextContent(/incomplete histories.*not admitted/i);
    expect(row).not.toHaveTextContent(/automatic numeric value/i);
    const verification = screen.getByText("Verified requirement coverage").closest("li");
    expect(verification).not.toBeNull();
    expect(verification).toHaveAttribute("data-operability-state", "available_when_evidence_exists");
    expect(verification).toHaveTextContent(/native-reviewed plan/i);
    expect(verification).toHaveTextContent(/observed check/i);
    expect(verification).toHaveTextContent(/fresh analysis/i);
    expect(verification).toHaveTextContent(/not a human coverage acknowledgment/i);
  });

  it("fails closed without the endpoint and never reads a session", async () => {
    const transport = createSyntheticTransport();
    const sessions = vi.spyOn(transport, "listCodexSessions");
    transport.getMetricOperabilityCatalog = undefined;

    render(<MetricOperabilityPanel transport={transport} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Metric operability is unavailable");
    expect(screen.getByRole("alert")).toHaveTextContent("No session was read");
    expect(sessions).not.toHaveBeenCalled();
  });

  it("shows an update boundary for a newer contract identity", async () => {
    const transport = createSyntheticTransport();
    transport.getMetricOperabilityCatalog = vi.fn().mockRejectedValue(
      new MetricOperabilityDefinitionsOutOfDateError(),
    );

    render(<MetricOperabilityPanel transport={transport} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Metric definitions are newer than this app",
    );
    expect(screen.queryByText("Measured paths shipped")).not.toBeInTheDocument();
  });

  it("aborts the actual pending catalog request when the panel unmounts", async () => {
    const transport = createSyntheticTransport();
    const pending = deferred<ReturnType<typeof createSyntheticMetricOperabilityCatalog>>();
    const load = vi.fn((_signal?: AbortSignal) => pending.promise);
    transport.getMetricOperabilityCatalog = load;

    const rendered = render(<MetricOperabilityPanel transport={transport} />);
    await act(async () => undefined);
    expect(load).toHaveBeenCalledTimes(1);
    const signal = requiredSignal(load.mock.calls[0][0]);
    expect(signal.aborted).toBe(false);
    rendered.unmount();
    expect(signal.aborted).toBe(true);
  });

  it("offers one retry after an initial transient failure", async () => {
    const transport = createSyntheticTransport();
    const load = vi.fn()
      .mockRejectedValueOnce(new Error("temporary transport failure"))
      .mockResolvedValueOnce(createSyntheticMetricOperabilityCatalog());
    transport.getMetricOperabilityCatalog = load;

    render(<MetricOperabilityPanel transport={transport} />);
    expect(await screen.findByRole("button", { name: "Retry" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "What can produce measured evidence today" })).toBeVisible();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("keeps the last validated map visible while refresh is pending or fails", async () => {
    const transport = createSyntheticTransport();
    let rejectRefresh!: (error: unknown) => void;
    const refresh = new Promise<never>((_resolve, reject) => { rejectRefresh = reject; });
    const load = vi.fn()
      .mockResolvedValueOnce(createSyntheticMetricOperabilityCatalog())
      .mockReturnValueOnce(refresh)
      .mockResolvedValueOnce(createSyntheticMetricOperabilityCatalog());
    transport.getMetricOperabilityCatalog = load;

    render(<MetricOperabilityPanel transport={transport} />);
    expect(await screen.findByRole("button", { name: "Refresh metric map" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Refresh metric map" }));
    expect(screen.getByRole("status")).toHaveTextContent("last validated map");
    expect(screen.getByText("20/20 contracts bound to the current client")).toBeVisible();
    rejectRefresh(new Error("temporary refresh failure"));
    expect(await screen.findByRole("button", { name: "Retry" })).toBeVisible();
    expect(screen.getByText("20/20 contracts bound to the current client")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("button", { name: "Refresh metric map" })).toBeVisible();
    expect(load).toHaveBeenCalledTimes(3);
  });

  it("hides the old map when refresh reports newer definitions", async () => {
    const transport = createSyntheticTransport();
    transport.getMetricOperabilityCatalog = vi.fn()
      .mockResolvedValueOnce(createSyntheticMetricOperabilityCatalog())
      .mockRejectedValueOnce(new MetricOperabilityDefinitionsOutOfDateError());
    render(<MetricOperabilityPanel transport={transport} />);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh metric map" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Metric definitions are newer");
    expect(screen.queryByText("20/20 contracts bound to the current client")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("treats the real status-200 invalid-payload transport wrapper as unavailable without retry", async () => {
    const transport = createSyntheticTransport();
    transport.getMetricOperabilityCatalog = vi.fn().mockRejectedValue(
      new TransportError("Metric catalog response was invalid", 200),
    );
    render(<MetricOperabilityPanel transport={transport} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("response was invalid");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it.each(["resolve", "reject"] as const)("ignores late %s from a replaced transport", async (settlement) => {
    const a = deferred<ReturnType<typeof createSyntheticMetricOperabilityCatalog>>();
    const b = deferred<ReturnType<typeof createSyntheticMetricOperabilityCatalog>>();
    const transportA = createSyntheticTransport();
    const transportB = createSyntheticTransport();
    transportA.getMetricOperabilityCatalog = vi.fn((_signal?: AbortSignal) => a.promise);
    transportB.getMetricOperabilityCatalog = vi.fn((_signal?: AbortSignal) => b.promise);
    const rendered = render(<MetricOperabilityPanel transport={transportA} />);
    await act(async () => undefined);
    expect(transportA.getMetricOperabilityCatalog).toHaveBeenCalledTimes(1);
    const firstSignal = requiredSignal(vi.mocked(transportA.getMetricOperabilityCatalog).mock.calls[0][0]);
    rendered.rerender(<MetricOperabilityPanel transport={transportB} />);
    await act(async () => undefined);
    expect(transportB.getMetricOperabilityCatalog).toHaveBeenCalledTimes(1);
    expect(firstSignal.aborted).toBe(true);
    const secondSignal = requiredSignal(vi.mocked(transportB.getMetricOperabilityCatalog).mock.calls[0][0]);
    expect(secondSignal.aborted).toBe(false);
    await act(async () => { b.resolve(createSyntheticMetricOperabilityCatalog()); });
    expect(await screen.findByRole("heading", { name: "What can produce measured evidence today" })).toBeVisible();
    await act(async () => {
      if (settlement === "resolve") a.resolve(createSyntheticMetricOperabilityCatalog());
      else a.reject(new Error("late failure"));
    });
    expect(screen.getByText("20/20 contracts bound to the current client")).toBeVisible();
  });

  it("does not retain a ready map when its endpoint is removed", async () => {
    const transport = createSyntheticTransport();
    const rendered = render(<MetricOperabilityPanel transport={transport} />);
    expect(await screen.findByRole("button", { name: "Refresh metric map" })).toBeVisible();
    transport.getMetricOperabilityCatalog = undefined;
    // A replacement transport identity is required to re-run the owner-bound effect.
    const replacement = { ...transport };
    rendered.rerender(<MetricOperabilityPanel transport={replacement} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("endpoint is unavailable");
    expect(screen.queryByText("20/20 contracts bound to the current client")).not.toBeInTheDocument();
    rendered.unmount();
  });

  it.each(["resolve", "reject"] as const)("recovers from a synchronous throw and ignores %s after unmount", async (settlement) => {
    const transport = createSyntheticTransport();
    const load = vi.fn()
      .mockImplementationOnce(() => { throw new Error("temporary sync failure"); })
      .mockResolvedValueOnce(createSyntheticMetricOperabilityCatalog());
    transport.getMetricOperabilityCatalog = load;
    const rendered = render(<MetricOperabilityPanel transport={transport} />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "What can produce measured evidence today" })).toBeVisible();
    const pending = deferred<ReturnType<typeof createSyntheticMetricOperabilityCatalog>>();
    const replacement = { ...transport, getMetricOperabilityCatalog: vi.fn((_signal?: AbortSignal) => pending.promise) };
    rendered.rerender(<MetricOperabilityPanel transport={replacement} />);
    await act(async () => undefined);
    expect(replacement.getMetricOperabilityCatalog).toHaveBeenCalledTimes(1);
    const signal = requiredSignal(vi.mocked(replacement.getMetricOperabilityCatalog).mock.calls[0][0]);
    rendered.unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => {
      if (settlement === "resolve") pending.resolve(createSyntheticMetricOperabilityCatalog());
      else pending.reject(new Error("late failure"));
    });
    expect(screen.queryByText("20/20 contracts bound to the current client")).not.toBeInTheDocument();
  });

  it("does not start a second request on rapid retry clicks in one uncommitted act", async () => {
    const transport = createSyntheticTransport();
    const retry = deferred<ReturnType<typeof createSyntheticMetricOperabilityCatalog>>();
    let attempt = 0;
    const load = vi.fn((_signal?: AbortSignal) => {
      attempt += 1;
      return attempt === 1 ? Promise.reject(new Error("temporary")) : retry.promise;
    });
    transport.getMetricOperabilityCatalog = load;
    render(<MetricOperabilityPanel transport={transport} />);
    const button = await screen.findByRole("button", { name: "Retry" });
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(load).toHaveBeenCalledTimes(2);
    const signal = requiredSignal(load.mock.calls[1][0]);
    expect(signal.aborted).toBe(false);
    await act(async () => { retry.resolve(createSyntheticMetricOperabilityCatalog()); });
    expect(await screen.findByRole("heading", { name: "What can produce measured evidence today" })).toBeVisible();
  });

  it("keeps the StrictMode-aborted first request separate from the live second request", async () => {
    const first = deferred<ReturnType<typeof createSyntheticMetricOperabilityCatalog>>();
    const second = deferred<ReturnType<typeof createSyntheticMetricOperabilityCatalog>>();
    const transport = createSyntheticTransport();
    let attempt = 0;
    const load = vi.fn((_signal?: AbortSignal) => {
      attempt += 1;
      return attempt === 1 ? first.promise : second.promise;
    });
    transport.getMetricOperabilityCatalog = load;
    render(<StrictMode><MetricOperabilityPanel transport={transport} /></StrictMode>);
    await act(async () => undefined);
    expect(load).toHaveBeenCalledTimes(2);
    const firstSignal = requiredSignal(load.mock.calls[0][0]);
    const secondSignal = requiredSignal(load.mock.calls[1][0]);
    expect(firstSignal.aborted).toBe(true);
    expect(secondSignal.aborted).toBe(false);
    await act(async () => { second.resolve(createSyntheticMetricOperabilityCatalog()); });
    expect(await screen.findByRole("heading", { name: "What can produce measured evidence today" })).toBeVisible();
  });
});
