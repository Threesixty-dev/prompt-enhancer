import { act, fireEvent, render, screen } from "@testing-library/react";
import { useLayoutEffect } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MetricCoverageReport, Provider } from "../../shared/api/contracts";
import { parseMetricCoverageReport } from "../../shared/api/httpTransport";
import { SYNTHETIC_METRIC_COVERAGE } from "../../shared/api/syntheticFixtures";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { MetricCoveragePanel } from "./MetricCoveragePanel";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, reject, resolve };
}

function coverage(count = 1, generatedAt = "2040-01-03T09:13:00Z"): MetricCoverageReport {
  const report = structuredClone(SYNTHETIC_METRIC_COVERAGE);
  report.generated_at = generatedAt;
  report.indexed_session_count = count;
  report.latest_completed_snapshot_count = count;
  report.latest_profile_runs = { completed: count, running: 0, failed: 0, never_run: 0 };
  for (const metric of report.metrics) {
    metric.latest_completed_run_count = count;
    metric.selected_run_count = count;
    metric.completed_selected_run_count = count;
    metric.contract_compatible_result_states = {
      known: count, unknown: 0, not_applicable: 0, abstained: 0, execution_error: 0,
    };
    metric.compatible_provenance_cohort_count = count === 0 ? 0 : 1;
  }
  // Keep test fixtures admitted by the same strict parser used at the HTTP boundary.
  expect(() => parseMetricCoverageReport(report, report.provider, report.scope)).not.toThrow();
  return report;
}

function displayedCount(label: string): string {
  const row = screen.getByText(label).parentElement;
  expect(row?.querySelector("dd")).not.toBeNull();
  return row!.querySelector("dd")!.textContent!;
}

async function settle() {
  await act(async () => { await Promise.resolve(); });
}

afterEach(() => vi.useRealTimers());

describe("MetricCoveragePanel recovery", () => {
  it("shows an admitted initial snapshot, its timestamp, then refreshes changed exact counts", async () => {
    const transport = createSyntheticTransport();
    const first = coverage(1, "2040-01-03T09:13:00Z");
    const second = coverage(2, "2040-01-04T10:14:00Z");
    transport.getMetricCoverage = vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce(second);
    render(<MetricCoveragePanel provider="synthetic" transport={transport} />);
    await screen.findByRole("heading", { name: "Coaching metric coverage" });
    expect(screen.getByText(/2040-01-03T09:13:00Z/)).toBeVisible();
    expect(displayedCount("Indexed sessions")).toBe("1");

    fireEvent.click(screen.getByRole("button", { name: "Refresh coverage" }));
    expect(screen.getByRole("status")).toHaveTextContent(/Refreshing coverage; displayed snapshot is stale/i);
    await screen.findByText(/2040-01-04T10:14:00Z/);
    expect(displayedCount("Indexed sessions")).toBe("2");
    expect(transport.getMetricCoverage).toHaveBeenCalledTimes(2);
  });

  it("keeps a labelled prior snapshot through rejected, cancelled, and timed-out refreshes", async () => {
    vi.useFakeTimers();
    const transport = createSyntheticTransport();
    const cancelled = deferred<MetricCoverageReport>();
    const timedOut = deferred<MetricCoverageReport>();
    transport.getMetricCoverage = vi.fn()
      .mockResolvedValueOnce(coverage(3))
      .mockRejectedValueOnce(new Error("synthetic refresh rejection"))
      .mockReturnValueOnce(cancelled.promise)
      .mockReturnValueOnce(timedOut.promise)
      .mockResolvedValueOnce(coverage(4));
    render(<MetricCoveragePanel provider="synthetic" transport={transport} />);
    await settle();
    expect(displayedCount("Indexed sessions")).toBe("3");
    fireEvent.click(screen.getByRole("button", { name: "Refresh coverage" }));
    await settle();
    expect(screen.getByRole("status")).toHaveTextContent(/failed.*stale/i);
    expect(displayedCount("Indexed sessions")).toBe("3");

    fireEvent.click(screen.getByRole("button", { name: "Retry coverage" }));
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Cancel coverage request" }));
    expect(screen.getByRole("status")).toHaveTextContent(/cancelled.*stale/i);
    await act(async () => { cancelled.resolve(coverage(8)); await Promise.resolve(); });
    expect(displayedCount("Indexed sessions")).toBe("3");

    fireEvent.click(screen.getByRole("button", { name: "Retry coverage" }));
    await settle();
    expect(transport.getMetricCoverage).toHaveBeenCalledTimes(4);
    await act(async () => { vi.advanceTimersByTime(15_000); await Promise.resolve(); });
    expect(screen.getByRole("status")).toHaveTextContent(/timed out.*stale/i);
    await act(async () => { timedOut.resolve(coverage(9)); await Promise.resolve(); });
    expect(displayedCount("Indexed sessions")).toBe("3");
    fireEvent.click(screen.getByRole("button", { name: "Retry coverage" }));
    await settle();
    expect(displayedCount("Indexed sessions")).toBe("4");
  });

  it("contains initial failures and parser-invalid resolved reports as unknown", async () => {
    const invalidReports: unknown[] = [
      { ...coverage(), provider: "codex" },
      { ...coverage(), scope: "one_project" },
      { ...coverage(), unexpected_synthetic_field: true },
      { ...coverage(), indexed_session_count: -1 },
    ];
    for (const failure of [
      new Error("SYNTHETIC-PRIVATE-CANARY"),
      Object.assign(new Error("unauthorized"), { status: 401 }),
    ]) {
      const transport = createSyntheticTransport();
      transport.getMetricCoverage = vi.fn(() => { throw failure; });
      const view = render(<MetricCoveragePanel provider="synthetic" transport={transport} />);
      await screen.findByRole("heading", { name: "Metric coverage: Unknown" });
      expect(screen.queryByText("Indexed sessions")).not.toBeInTheDocument();
      expect(document.body.textContent).not.toContain("SYNTHETIC-PRIVATE-CANARY");
      view.unmount();
    }
    for (const report of invalidReports) {
      const transport = createSyntheticTransport();
      transport.getMetricCoverage = vi.fn().mockResolvedValue(report);
      const view = render(<MetricCoveragePanel provider="synthetic" transport={transport} />);
      await screen.findByRole("heading", { name: "Metric coverage: Unknown" });
      expect(screen.queryByText("Indexed sessions")).not.toBeInTheDocument();
      view.unmount();
    }
  });

  it("fails closed immediately when a transport resolves no report", async () => {
    const transport = createSyntheticTransport();
    transport.getMetricCoverage = vi.fn(() => undefined) as unknown as typeof transport.getMetricCoverage;
    render(<MetricCoveragePanel provider="synthetic" transport={transport} />);
    await screen.findByRole("heading", { name: "Metric coverage: Unknown" });
    expect(transport.getMetricCoverage).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Indexed sessions")).not.toBeInTheDocument();
  });

  it("times out an initial request at 15 seconds, ignores its late valid result, and recovers", async () => {
    vi.useFakeTimers();
    const transport = createSyntheticTransport();
    const late = deferred<MetricCoverageReport>();
    transport.getMetricCoverage = vi.fn().mockReturnValueOnce(late.promise).mockResolvedValueOnce(coverage(7));
    render(<MetricCoveragePanel provider="synthetic" transport={transport} />);
    await settle();
    expect(transport.getMetricCoverage).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(15_000); await Promise.resolve(); });
    expect(screen.getByRole("heading", { name: "Metric coverage: Unknown" })).toBeVisible();
    await act(async () => { late.resolve(coverage(8)); await Promise.resolve(); });
    expect(screen.queryByText("Indexed sessions")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry coverage" }));
    await settle();
    expect(displayedCount("Indexed sessions")).toBe("7");
  });

  it("retries with the exact provider request after an initial error", async () => {
    const transport = createSyntheticTransport();
    const getMetricCoverage = vi.fn().mockRejectedValueOnce(new Error("synthetic"))
      .mockResolvedValueOnce(coverage(4));
    transport.getMetricCoverage = getMetricCoverage;
    render(<MetricCoveragePanel provider="synthetic" transport={transport} />);
    await screen.findByRole("button", { name: "Retry coverage" });
    fireEvent.click(screen.getByRole("button", { name: "Retry coverage" }));
    await screen.findByRole("heading", { name: "Coaching metric coverage" });
    expect(getMetricCoverage).toHaveBeenCalledTimes(2);
    expect(getMetricCoverage.mock.calls.every(([provider, signal]) =>
      provider === "synthetic" && signal instanceof AbortSignal)).toBe(true);
  });

  it("coalesces double refresh clicks into one request", async () => {
    const transport = createSyntheticTransport();
    const pending = deferred<MetricCoverageReport>();
    transport.getMetricCoverage = vi.fn().mockResolvedValueOnce(coverage()).mockReturnValueOnce(pending.promise);
    render(<MetricCoveragePanel provider="synthetic" transport={transport} />);
    await screen.findByRole("button", { name: "Refresh coverage" });
    const refresh = screen.getByRole("button", { name: "Refresh coverage" });
    await act(async () => { fireEvent.click(refresh); fireEvent.click(refresh); await Promise.resolve(); });
    expect(transport.getMetricCoverage).toHaveBeenCalledTimes(2);
  });

  it("immediately fences valid late reports when provider, transport, or project scope changes", async () => {
    const firstTransport = createSyntheticTransport();
    const providerLate = deferred<MetricCoverageReport>();
    firstTransport.getMetricCoverage = vi.fn()
      .mockReturnValueOnce(providerLate.promise)
      .mockReturnValue(new Promise<MetricCoverageReport>(() => undefined));
    const view = render(<MetricCoveragePanel provider="synthetic" transport={firstTransport} />);
    await settle();
    view.rerender(<MetricCoveragePanel provider={"codex" as Provider} transport={firstTransport} />);
    expect(screen.queryByText("Indexed sessions")).not.toBeInTheDocument();
    const validOldProviderReport = coverage(5);
    expect(() => parseMetricCoverageReport(validOldProviderReport, "synthetic", "provider_catalog")).not.toThrow();
    await act(async () => { providerLate.resolve(validOldProviderReport); await Promise.resolve(); });
    expect(screen.queryByText("Indexed sessions")).not.toBeInTheDocument();

    const secondTransport = createSyntheticTransport();
    const transportLate = deferred<MetricCoverageReport>();
    secondTransport.getMetricCoverage = vi.fn().mockReturnValue(transportLate.promise);
    view.rerender(<MetricCoveragePanel provider="synthetic" transport={secondTransport} />);
    await settle();
    view.rerender(<MetricCoveragePanel provider="synthetic" transport={firstTransport} />);
    await act(async () => { transportLate.resolve(coverage(6)); await Promise.resolve(); });
    expect(screen.queryByText("Indexed sessions")).not.toBeInTheDocument();

    const projectA = "a".repeat(64);
    const projectB = "b".repeat(64);
    const lateProjectA = deferred<MetricCoverageReport>();
    const currentProjectB = deferred<MetricCoverageReport>();
    firstTransport.getProjectMetricCoverage = vi.fn()
      .mockReturnValueOnce(lateProjectA.promise)
      .mockReturnValueOnce(currentProjectB.promise);
    view.rerender(<MetricCoveragePanel provider="synthetic" projectId={projectA} transport={firstTransport} />);
    await settle();
    view.rerender(<MetricCoveragePanel provider="synthetic" projectId={projectB} transport={firstTransport} />);
    expect(screen.queryByText("Indexed sessions")).not.toBeInTheDocument();
    const validOldProjectReport = { ...coverage(8), scope: "one_project" as const, indexed_project_count: 1 };
    expect(() => parseMetricCoverageReport(validOldProjectReport, "synthetic", "one_project")).not.toThrow();
    await act(async () => { lateProjectA.resolve(validOldProjectReport); await Promise.resolve(); });
    expect(screen.queryByText("Indexed sessions")).not.toBeInTheDocument();
    await act(async () => {
      currentProjectB.resolve({ ...coverage(9), scope: "one_project" as const, indexed_project_count: 1 });
      await Promise.resolve();
    });
    expect(displayedCount("Indexed sessions")).toBe("9");
  });

  it("does not dispatch a request when unmounted before the effect microtask", async () => {
    const transport = createSyntheticTransport();
    transport.getMetricCoverage = vi.fn().mockResolvedValue(coverage());
    const view = render(<MetricCoveragePanel provider="synthetic" transport={transport} />);
    view.unmount();
    await settle();
    expect(transport.getMetricCoverage).not.toHaveBeenCalled();
  });

  it("aborts a request that has already dispatched when unmounted", async () => {
    const transport = createSyntheticTransport();
    let signal: AbortSignal | undefined;
    transport.getMetricCoverage = vi.fn((_provider, requestSignal) => {
      signal = requestSignal;
      return new Promise<MetricCoverageReport>(() => undefined);
    });
    const view = render(<MetricCoveragePanel provider="synthetic" transport={transport} />);
    await settle();
    expect(transport.getMetricCoverage).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("hides a ready old snapshot before provider change and keeps it hidden on project change", async () => {
    const transport = createSyntheticTransport();
    transport.getMetricCoverage = vi.fn().mockResolvedValue(coverage(5));
    transport.getProjectMetricCoverage = vi.fn().mockReturnValue(new Promise<MetricCoverageReport>(() => undefined));
    const observations: string[] = [];
    function Probe({ provider, projectId }: { provider: Provider; projectId?: string }) {
      useLayoutEffect(() => {
        observations.push(document.body.textContent ?? "");
      });
      return <MetricCoveragePanel provider={provider} projectId={projectId} transport={transport} />;
    }
    const view = render(<Probe provider="synthetic" />);
    await screen.findByRole("heading", { name: "Coaching metric coverage" });
    expect(displayedCount("Indexed sessions")).toBe("5");

    observations.length = 0;
    view.rerender(<Probe provider={"codex" as Provider} />);
    expect(observations.at(-1)).toContain("Checking the local metric snapshot...");
    expect(observations.at(-1)).not.toContain("Indexed sessions");

    observations.length = 0;
    view.rerender(<Probe provider="synthetic" projectId={"a".repeat(64)} />);
    expect(observations.at(-1)).toContain("Checking the local metric snapshot...");
    expect(observations.at(-1)).not.toContain("Indexed sessions");
  });

  it("gives multiple panels distinct title and status references", async () => {
    const first = createSyntheticTransport();
    const second = createSyntheticTransport();
    first.getMetricCoverage = vi.fn().mockResolvedValue(coverage(1));
    second.getMetricCoverage = vi.fn().mockResolvedValue(coverage(2));
    render(<>
      <MetricCoveragePanel provider="synthetic" transport={first} />
      <MetricCoveragePanel provider="synthetic" transport={second} />
    </>);
    await screen.findAllByRole("heading", { name: "Coaching metric coverage" });
    const panels = screen.getAllByRole("heading", { name: "Coaching metric coverage" })
      .map((heading) => heading.closest("section")!);
    const labelledBy = panels.map((panel) => panel.getAttribute("aria-labelledby"));
    expect(new Set(labelledBy).size).toBe(2);
    for (const panel of panels) {
      expect(document.getElementById(panel.getAttribute("aria-labelledby")!)).toBeTruthy();
    }
    const statuses = screen.getAllByRole("status").map((status) => status.id);
    expect(new Set(statuses).size).toBe(2);
    expect(statuses.every(Boolean)).toBe(true);
  });
});
