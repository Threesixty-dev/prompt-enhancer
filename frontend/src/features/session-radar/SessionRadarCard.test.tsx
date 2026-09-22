import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useLayoutEffect, type ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import type {
  ModelEnsembleRun,
  PromptEnhancerTransport,
  SessionMetric,
  SessionMetricResponse,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { parseModelEnsembleRun } from "../../shared/api/modelEnsembleContract";
import { MetricDefinitionsOutOfDateError } from "../../shared/api/metricPublicationV2Contract";
import { createSessionRadarRun } from "../../test/sessionRadarFixture";
import { SessionRadarCard } from "./SessionRadarCard";

const SESSION_ID = "a".repeat(64);
const OTHER_SESSION_ID = "b".repeat(64);

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((complete, fail) => {
    resolve = complete;
    reject = fail;
  });
  return { promise, resolve, reject };
}

function storedMetric(numericValue: number): SessionMetric {
  return {
    key: "prompt.task_definition_coverage",
    version: 1,
    dimension: "prompt",
    display_name: "Synthetic task definition coverage",
    numeric_value: numericValue,
    text_value: null,
    unit: "ratio",
    source: "synthetic_fixture",
    observed_count: 3,
    eligible_count: 5,
    coverage: 0.6,
    confidence: 1,
    metric_pack_key: "synthetic.local.metrics",
    metric_pack_version: 1,
    metric_engine_version: "synthetic-engine-1",
    redactor_version: "synthetic-redactor-1",
    model_id: null,
    model_revision: null,
    tokenizer_id: null,
    prompt_version: "synthetic-prompt-1",
    rubric_version: "synthetic-rubric-1",
    computed_at: "2040-01-03T09:13:00Z",
  };
}

type RadarTransport = ComponentProps<typeof SessionRadarCard>["transport"];

function radarTransport({
  latest,
  stored,
}: {
  latest?: RadarTransport["getLatestModelEnsemble"];
  stored: PromptEnhancerTransport["getSessionMetrics"];
}): {
  transport: RadarTransport;
  getLatestModelEnsemble?: RadarTransport["getLatestModelEnsemble"];
  getSessionMetrics: PromptEnhancerTransport["getSessionMetrics"];
} {
  return {
    transport: latest === undefined ? { getSessionMetrics: stored } : {
      getLatestModelEnsemble: latest,
      getSessionMetrics: stored,
    },
    getLatestModelEnsemble: latest,
    getSessionMetrics: stored,
  };
}

function hasRadar(): boolean {
  return screen.queryAllByRole("img").length > 0;
}

function LayoutObserver({ observe }: { observe: (text: string) => void }) {
  useLayoutEffect(() => { observe(document.body.textContent ?? ""); });
  return null;
}

function coreStoredMetric(): SessionMetric {
  return {
    ...storedMetric(1),
    key: "core.metadata.session",
    version: 4,
    dimension: "core",
    display_name: "User messages",
    numeric_value: 42,
    unit: "count",
    observed_count: 42,
    eligible_count: 42,
    coverage: 1,
  };
}

function storedResponse(metrics: SessionMetric[] = [], sessionId = SESSION_ID): SessionMetricResponse {
  return { session_id: sessionId, metrics };
}

function noStoredRead(): PromptEnhancerTransport["getSessionMetrics"] {
  return vi.fn(async () => storedResponse());
}

function parsedRadarRun(options?: Parameters<typeof createSessionRadarRun>[0]): ModelEnsembleRun {
  return parseModelEnsembleRun(createSessionRadarRun(options));
}

async function expectLatestRequest(
  latest: NonNullable<RadarTransport["getLatestModelEnsemble"]>,
  sessionId = SESSION_ID,
) {
  await waitFor(() => expect(latest).toHaveBeenCalledWith(sessionId, expect.any(AbortSignal)));
}

describe("SessionRadarCard", () => {
  it("keeps the shared ensemble fixture on the strict transport parser path", () => {
    const raw = createSessionRadarRun();
    expect(parseModelEnsembleRun(structuredClone(raw))).toEqual(raw);
  });

  it("charts the canonical V2 receipt before conflicting typed and committee values", async () => {
    const latest = vi.fn(async () => parsedRadarRun({ source: "v2" }));
    const stored = noStoredRead();
    const { transport } = radarTransport({ latest, stored });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    await expectLatestRequest(latest);
    expect(await screen.findByText(/Canonical V2 measured states/i)).toBeVisible();
    expect(screen.getAllByRole("img")).toHaveLength(1);
    const taskStates = screen.getByRole("list", { name: "Task framing metric states" });
    const taskDefinition = within(taskStates).getByText("Task", { exact: true }).closest("li");
    expect(taskDefinition).not.toBeNull();
    expect(taskDefinition).toHaveTextContent("75%");
    expect(taskDefinition).not.toHaveTextContent("25%");
    expect(taskStates).toHaveTextContent("coverage 100%");
    fireEvent.click(screen.getByText("Snapshot provenance"));
    expect(screen.getByText(`Endpoint-scoped session receipt · run ${"b".repeat(64)} · projection metric-contract-v2-projection-1 · calibration not assessed.`)).toBeVisible();
    expect(screen.getByRole("button", { name: "Task framing" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Collaboration flow" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Reasoning trace" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Evidence lane" })).toBeVisible();
    expect(stored).not.toHaveBeenCalled();
  });

  it("shows the raw lower-is-better rate separately from the radar direction", async () => {
    const latest = vi.fn(async () => parsedRadarRun({ source: "v2" }));
    const { transport } = radarTransport({ latest, stored: noStoredRead() });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    await screen.findByText(/Canonical V2 measured states/i);
    fireEvent.click(screen.getByRole("button", { name: "Collaboration flow" }));
    expect(screen.getByText("raw rate 0%")).toBeVisible();
    expect(screen.getAllByRole("img")).toHaveLength(1);
  });

  it("uses typed local measurements when no canonical V2 receipt exists", async () => {
    const latest = vi.fn(async () => parsedRadarRun({ source: "typed" }));
    const stored = noStoredRead();
    const { transport } = radarTransport({ latest, stored });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    await screen.findByText(/Typed local measurement/i);
    expect(screen.getAllByRole("img")).toHaveLength(1);
    const taskDefinition = within(screen.getByRole("list", { name: "Task framing metric states" }))
      .getByText("Task", { exact: true }).closest("li");
    expect(taskDefinition).not.toBeNull();
    expect(taskDefinition).toHaveTextContent("25%");
    expect(stored).not.toHaveBeenCalled();
  });

  it("uses the legacy committee shadow only when neither canonical nor typed receipts exist", async () => {
    const latest = vi.fn(async () => parsedRadarRun({ source: "committee" }));
    const stored = noStoredRead();
    const { transport } = radarTransport({ latest, stored });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    await screen.findByText(/Legacy committee shadow/i);
    expect(screen.getAllByRole("img")).toHaveLength(1);
    const taskDefinition = within(screen.getByRole("list", { name: "Task framing metric states" }))
      .getByText("Task", { exact: true }).closest("li");
    expect(taskDefinition).not.toBeNull();
    expect(taskDefinition).toHaveTextContent("100%");
    expect(stored).not.toHaveBeenCalled();
  });

  it("keeps an all-unknown canonical V2 receipt authoritative instead of consulting stored metrics", async () => {
    const latest = vi.fn(async () => parsedRadarRun({ source: "v2", canonicalState: "unknown" }));
    const stored = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(async () => storedResponse([coreStoredMetric()]));
    const { transport } = radarTransport({ latest, stored });
    const { container } = render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    await screen.findByText(/Canonical V2 measured states/i);
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(container.querySelectorAll(".prompt-plot__dot")).toHaveLength(0);
    expect(stored).not.toHaveBeenCalled();
  });

  it("does not chart a valid stored row returned for a different session", async () => {
    const response = deferred<SessionMetricResponse>();
    const getSessionMetrics = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(() => response.promise);
    const { transport } = radarTransport({ stored: getSessionMetrics });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);
    await waitFor(() => expect(getSessionMetrics).toHaveBeenCalledWith(SESSION_ID, expect.any(AbortSignal)));

    await act(async () => {
      response.resolve({ session_id: OTHER_SESSION_ID, metrics: [storedMetric(0.6)] });
      await Promise.resolve();
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Session radar could not be loaded.");
    expect(hasRadar()).toBe(false);
  });

  const invalidNumbers: readonly [string, number][] = [
    ["NaN", Number.NaN],
    ["positive infinity", Number.POSITIVE_INFINITY],
    ["below zero", -0.1],
    ["above one", 1.1],
  ];

  it.each(invalidNumbers)("does not chart a stored metric with %s numeric value", async (_label, numericValue) => {
    const response = deferred<SessionMetricResponse>();
    const getSessionMetrics = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(() => response.promise);
    const { transport } = radarTransport({ stored: getSessionMetrics });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);
    await waitFor(() => expect(getSessionMetrics).toHaveBeenCalledWith(SESSION_ID, expect.any(AbortSignal)));

    await act(async () => {
      response.resolve({ session_id: SESSION_ID, metrics: [storedMetric(numericValue)] });
      await Promise.resolve();
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Session radar could not be loaded.");
    expect(hasRadar()).toBe(false);
  });

  it("exposes an accessible cancellation control while the stored radar read is pending", async () => {
    const response = deferred<SessionMetricResponse>();
    const getSessionMetrics = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(() => response.promise);
    const { transport } = radarTransport({ stored: getSessionMetrics });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    await waitFor(() => expect(getSessionMetrics).toHaveBeenCalledWith(SESSION_ID, expect.any(AbortSignal)));
    expect(await screen.findByRole("button", { name: "Cancel session radar loading" })).toBeVisible();
  });

  it("uses stored metrics only after the latest ensemble endpoint attests absence", async () => {
    const latest = vi.fn(async () => { throw new TransportError("not found", 404); });
    const stored = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(async () => storedResponse([coreStoredMetric()]));
    const { transport } = radarTransport({ latest, stored });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    await screen.findByText("Stored session metrics are not a coaching radar snapshot.");
    expect(screen.getByText(/Stored source synthetic_fixture/i)).toBeVisible();
    expect(hasRadar()).toBe(false);
    expect(stored).toHaveBeenCalledWith(SESSION_ID, expect.any(AbortSignal));
  });

  it("treats a 404 with an empty stored response as absence rather than a failed chart", async () => {
    const latest = vi.fn(async () => { throw new TransportError("not found", 404); });
    const stored = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(async () => storedResponse());
    const { transport } = radarTransport({ latest, stored });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    await expectLatestRequest(latest);
    await waitFor(() => expect(stored).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(hasRadar()).toBe(false);
  });

  it("uses the stored-data gap when the latest ensemble method is unavailable", async () => {
    const stored = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(async () => storedResponse([coreStoredMetric()]));
    const { transport } = radarTransport({ stored });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    expect(await screen.findByText("Stored session metrics are not a coaching radar snapshot.")).toBeVisible();
    expect(stored).toHaveBeenCalledWith(SESSION_ID, expect.any(AbortSignal));
  });

  it("does not consult stored metrics after a latest-ensemble transport failure", async () => {
    const latest = vi.fn(async () => { throw new TransportError("synthetic private failure", 500); });
    const stored = noStoredRead();
    const { transport } = radarTransport({ latest, stored });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Session radar could not be loaded.");
    expect(screen.queryByText("synthetic private failure")).toBeNull();
    expect(stored).not.toHaveBeenCalled();
    expect(hasRadar()).toBe(false);
  });

  it.each([405, 501])("does not use stored metrics after latest endpoint status %i", async (status) => {
    const latest = vi.fn(async () => { throw new TransportError("not available", status); });
    const stored = noStoredRead();
    const { transport } = radarTransport({ latest, stored });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Session radar could not be loaded.");
    expect(stored).not.toHaveBeenCalled();
    expect(hasRadar()).toBe(false);
  });

  it("does not consult stored metrics after a malformed latest ensemble response", async () => {
    const latest = vi.fn(async () => ({ invalid: true } as unknown as ModelEnsembleRun));
    const stored = noStoredRead();
    const { transport } = radarTransport({ latest, stored });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Session radar could not be loaded.");
    expect(stored).not.toHaveBeenCalled();
    expect(hasRadar()).toBe(false);
  });

  it("shows safe update guidance for a canonical definitions mismatch without stored fallback", async () => {
    const latest = vi.fn(async () => { throw new MetricDefinitionsOutOfDateError("projection_version"); });
    const stored = noStoredRead();
    const { transport } = radarTransport({ latest, stored });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("This snapshot uses metric definitions this app cannot read. Update the app, then refresh the session radar.");
    expect(screen.getByRole("button", { name: "Refresh session radar" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Retry session radar" })).toBeNull();
    expect(stored).not.toHaveBeenCalled();
    expect(hasRadar()).toBe(false);
  });

  it("refuses a duplicate stored metric row without drawing a radar", async () => {
    const stored = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(async () => (
      storedResponse([coreStoredMetric(), coreStoredMetric()])
    ));
    const { transport } = radarTransport({ stored });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Session radar could not be loaded.");
    expect(hasRadar()).toBe(false);
  });

  it("does not let a synchronous latest read failure prevent an exact retry", async () => {
    const latest = vi.fn()
      .mockImplementationOnce(() => { throw new Error("synthetic latest failure"); })
      .mockResolvedValueOnce(parsedRadarRun({ source: "v2" }));
    const stored = noStoredRead();
    const { transport } = radarTransport({ latest, stored });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    const retry = await screen.findByRole("button", { name: "Retry session radar" });
    expect(stored).not.toHaveBeenCalled();
    fireEvent.click(retry);
    expect(await screen.findByText(/Canonical V2 measured states/i)).toBeVisible();
    expect(latest).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "Retry session radar" })).toBeNull();
  });

  it("cancels a pending read, aborts it, and retries only when explicitly requested", async () => {
    const first = deferred<ModelEnsembleRun>();
    const latest = vi.fn<NonNullable<RadarTransport["getLatestModelEnsemble"]>>()
      .mockImplementationOnce((_sessionId, signal) => first.promise)
      .mockResolvedValueOnce(parsedRadarRun({ source: "v2" }));
    const { transport } = radarTransport({ latest, stored: noStoredRead() });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    await expectLatestRequest(latest);
    const firstSignal = latest.mock.calls[0][1];
    fireEvent.click(await screen.findByRole("button", { name: "Cancel session radar loading" }));
    expect(firstSignal?.aborted).toBe(true);
    expect(await screen.findByText("Session radar loading was cancelled.")).toBeVisible();
    const retry = await screen.findByRole("button", { name: "Retry session radar" });
    expect(latest).toHaveBeenCalledTimes(1);
    fireEvent.click(retry);
    expect(await screen.findByText(/Canonical V2 measured states/i)).toBeVisible();
    expect(latest).toHaveBeenCalledTimes(2);
  });

  it("times out an unsettled latest read after fifteen seconds and retries a fresh attempt", async () => {
    vi.useFakeTimers();
    try {
      const first = deferred<ModelEnsembleRun>();
      const latest = vi.fn<NonNullable<RadarTransport["getLatestModelEnsemble"]>>()
        .mockImplementationOnce(() => first.promise)
        .mockResolvedValueOnce(parsedRadarRun({ source: "v2" }));
      const stored = noStoredRead();
      const { transport } = radarTransport({ latest, stored });
      render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(latest).toHaveBeenCalledTimes(1);
      expect(screen.getByRole("button", { name: "Cancel session radar loading" })).toBeVisible();
      await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
      expect(screen.getByRole("alert")).toHaveTextContent("Session radar request timed out after 15 seconds.");
      expect(stored).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: "Retry session radar" }));
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(latest).toHaveBeenCalledTimes(2);
      expect(screen.getByText(/Canonical V2 measured states/i)).toBeVisible();
    } finally {
      vi.useRealTimers();
    }
  });

  it("starts a fresh current read when the user refreshes a successful radar", async () => {
    const latest = vi.fn()
      .mockResolvedValueOnce(parsedRadarRun({ source: "v2" }))
      .mockResolvedValueOnce(parsedRadarRun({ source: "typed" }));
    const { transport } = radarTransport({ latest, stored: noStoredRead() });
    render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    expect(await screen.findByText(/Canonical V2 measured states/i)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Refresh session radar" }));
    expect(await screen.findByText(/Typed local measurement/i)).toBeVisible();
    expect(latest).toHaveBeenCalledTimes(2);
  });

  it("fences a late session-A completion after session B becomes the render owner", async () => {
    const earlier = deferred<ModelEnsembleRun>();
    const latest = vi.fn<NonNullable<RadarTransport["getLatestModelEnsemble"]>>((sessionId) => (
      sessionId === SESSION_ID ? earlier.promise : Promise.resolve(parsedRadarRun({ source: "v2" }))
    ));
    const { transport } = radarTransport({ latest, stored: noStoredRead() });
    const view = render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    await expectLatestRequest(latest);
    const earlierSignal = latest.mock.calls[0][1];
    view.rerender(<SessionRadarCard sessionId={OTHER_SESSION_ID} transport={transport} />);
    await expectLatestRequest(latest, OTHER_SESSION_ID);
    expect(await screen.findByText(/Canonical V2 measured states/i)).toBeVisible();
    expect(earlierSignal?.aborted).toBe(true);
    await act(async () => { earlier.resolve(parsedRadarRun({ source: "committee" })); await Promise.resolve(); });
    expect(screen.getByText(/Canonical V2 measured states/i)).toBeVisible();
    expect(screen.queryByText(/Legacy committee shadow/i)).toBeNull();
  });

  it("fences a late completion from a replaced transport", async () => {
    const earlier = deferred<ModelEnsembleRun>();
    const oldLatest = vi.fn<NonNullable<RadarTransport["getLatestModelEnsemble"]>>(() => earlier.promise);
    const oldTransport = radarTransport({ latest: oldLatest, stored: noStoredRead() }).transport;
    const newLatest = vi.fn(async () => parsedRadarRun({ source: "v2" }));
    const newTransport = radarTransport({ latest: newLatest, stored: noStoredRead() }).transport;
    const view = render(<SessionRadarCard sessionId={SESSION_ID} transport={oldTransport} />);

    await expectLatestRequest(oldLatest);
    const earlierSignal = oldLatest.mock.calls[0][1];
    view.rerender(<SessionRadarCard sessionId={SESSION_ID} transport={newTransport} />);
    await expectLatestRequest(newLatest);
    expect(await screen.findByText(/Canonical V2 measured states/i)).toBeVisible();
    expect(earlierSignal?.aborted).toBe(true);
    await act(async () => { earlier.resolve(parsedRadarRun({ source: "committee" })); await Promise.resolve(); });
    expect(screen.queryByText(/Legacy committee shadow/i)).toBeNull();
  });

  it("does not dispatch a pre-effect stale-owner request after an immediate rerender", async () => {
    const oldLatest = vi.fn<NonNullable<RadarTransport["getLatestModelEnsemble"]>>();
    const oldTransport = radarTransport({ latest: oldLatest, stored: noStoredRead() }).transport;
    const newLatest = vi.fn(async () => parsedRadarRun({ source: "v2" }));
    const newTransport = radarTransport({ latest: newLatest, stored: noStoredRead() }).transport;
    const view = render(<SessionRadarCard sessionId={SESSION_ID} transport={oldTransport} />);
    view.rerender(<SessionRadarCard sessionId={OTHER_SESSION_ID} transport={newTransport} />);

    await expectLatestRequest(newLatest, OTHER_SESSION_ID);
    expect(oldLatest).not.toHaveBeenCalled();
    expect(await screen.findByText(/Canonical V2 measured states/i)).toBeVisible();
  });

  it("does not expose a completed old-owner radar to a parent layout observer", async () => {
    const sessionB = "c".repeat(64);
    const latest = vi.fn<NonNullable<RadarTransport["getLatestModelEnsemble"]>>((sessionId) => (
      sessionId === SESSION_ID
        ? Promise.resolve(parsedRadarRun({ source: "v2" }))
        : new Promise<ModelEnsembleRun>(() => undefined)
    ));
    const { transport } = radarTransport({ latest, stored: noStoredRead() });
    const commits: string[] = [];
    const view = render(<><SessionRadarCard sessionId={SESSION_ID} transport={transport} /><LayoutObserver observe={(text) => commits.push(text)} /></>);

    expect(await screen.findByText(/Canonical V2 measured states/i)).toBeVisible();
    view.rerender(<><SessionRadarCard sessionId={sessionB} transport={transport} /><LayoutObserver observe={(text) => commits.push(text)} /></>);
    const lastCommit = commits[commits.length - 1] ?? "";
    expect(lastCommit).not.toContain("Canonical V2 measured states");
    expect(lastCommit).toContain("Cancel session radar loading");
  });

  it("aborts an in-flight read on unmount and ignores its late completion", async () => {
    const pending = deferred<ModelEnsembleRun>();
    const latest = vi.fn<NonNullable<RadarTransport["getLatestModelEnsemble"]>>(() => pending.promise);
    const { transport } = radarTransport({ latest, stored: noStoredRead() });
    const view = render(<SessionRadarCard sessionId={SESSION_ID} transport={transport} />);

    await expectLatestRequest(latest);
    const signal = latest.mock.calls[0][1];
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => { pending.resolve(parsedRadarRun({ source: "v2" })); await Promise.resolve(); });
    expect(view.container).toBeEmptyDOMElement();
  });
});
