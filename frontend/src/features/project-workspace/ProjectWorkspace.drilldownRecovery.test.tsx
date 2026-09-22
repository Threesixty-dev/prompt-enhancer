import { act, fireEvent, render, screen } from "@testing-library/react";
import { useLayoutEffect } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  PromptEnhancerTransport,
  SessionAnalysisRunResponse,
  SessionMetric,
  SessionMetricReadinessReport,
  SessionMetricResponse,
} from "../../shared/api/contracts";
import {
  SYNTHETIC_QUALITY_PROJECT_ID,
  SYNTHETIC_QUALITY_SESSION_ID,
  SYNTHETIC_CURRENT_SESSION_QUALITY_RUN,
  SYNTHETIC_SESSION_METRIC_READINESS,
} from "../../shared/api/syntheticFixtures";
import { TransportError } from "../../shared/api/httpTransport";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { ProjectWorkspace } from "./ProjectWorkspace";

vi.mock("../session-radar/SessionRadarCard", () => ({
  SessionRadarCard: () => null,
}));

const SECOND_SESSION_ID = "6".repeat(64);
const STORED_LABEL = "Synthetic stored metric seventy three";
const NEXT_STORED_LABEL = "Synthetic replacement metric eighty nine";

function pending<T>(): Promise<T> {
  return new Promise<T>(() => undefined);
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}

async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function storedMetric(label = STORED_LABEL, value = 73): SessionMetric {
  return {
    key: "synthetic.tool_fixture_count",
    version: 1,
    dimension: "tools",
    display_name: label,
    numeric_value: value,
    text_value: null,
    unit: "count",
    source: "synthetic_fixture",
    observed_count: 3,
    eligible_count: 3,
    coverage: 1,
    confidence: 1,
    metric_pack_key: "synthetic.local.metrics",
    metric_pack_version: 1,
    metric_engine_version: "synthetic-engine-1",
    redactor_version: null,
    model_id: null,
    model_revision: null,
    tokenizer_id: null,
    prompt_version: null,
    rubric_version: null,
    computed_at: "2040-01-03T09:13:00Z",
  };
}

function metricsResponse(
  sessionId: string,
  label = STORED_LABEL,
  value = 73,
): SessionMetricResponse {
  return { session_id: sessionId, metrics: [storedMetric(label, value)] };
}

function qualityRun(sessionId = SYNTHETIC_QUALITY_SESSION_ID) {
  const response = structuredClone(SYNTHETIC_CURRENT_SESSION_QUALITY_RUN);
  response.run.session_id = sessionId;
  return response;
}

function readiness(sessionId = SYNTHETIC_QUALITY_SESSION_ID) {
  const response = structuredClone(SYNTHETIC_SESSION_METRIC_READINESS);
  response.session_id = sessionId;
  return response;
}

function workspace(
  transport: PromptEnhancerTransport,
  category: "tools" | "prompt-quality" = "tools",
  sessionId = SYNTHETIC_QUALITY_SESSION_ID,
) {
  return (
    <ProjectWorkspace
      navigate={vi.fn()}
      route={{
        name: "session_metrics",
        projectId: SYNTHETIC_QUALITY_PROJECT_ID,
        sessionId,
        category,
      }}
      transport={transport}
    />
  );
}

async function openLegacyDetails(details: HTMLDetailsElement): Promise<void> {
  await act(async () => {
    details.open = true;
    fireEvent(details, new Event("toggle", { bubbles: true }));
    await Promise.resolve();
  });
}

async function openLegacyProfile(): Promise<void> {
  const label = await screen.findByText("Legacy coaching profile");
  const details = label.closest("details");
  if (!(details instanceof HTMLDetailsElement)) throw new Error("Legacy profile disclosure is unavailable.");
  await openLegacyDetails(details);
  await settle();
}

async function waitForStoredMetric(label = STORED_LABEL): Promise<void> {
  expect(await screen.findByText(label)).toBeVisible();
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("ProjectWorkspace drilldown recovery", () => {
  it("offers cancellation while a stored-metrics read is pending", async () => {
    const transport = createSyntheticTransport();
    transport.getSessionMetrics = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(() => pending());

    render(workspace(transport));

    expect(await screen.findByRole("button", { name: "Cancel stored metrics loading" })).toBeVisible();
  });

  it("cancels a stored-metrics read, fences its late response, and visibly retries", async () => {
    const transport = createSyntheticTransport();
    const late = deferred<SessionMetricResponse>();
    let signal: AbortSignal | undefined;
    const read = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>((sessionId, requestSignal): Promise<SessionMetricResponse> => {
      signal = requestSignal;
      return read.mock.calls.length === 1
        ? late.promise
        : Promise.resolve(metricsResponse(sessionId));
    });
    transport.getSessionMetrics = read;
    render(workspace(transport));

    fireEvent.click(await screen.findByRole("button", { name: "Cancel stored metrics loading" }));
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      late.resolve(metricsResponse(SYNTHETIC_QUALITY_SESSION_ID, "Late cancelled metric", 17));
      await Promise.resolve();
    });
    expect(screen.queryByText("Late cancelled metric")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry stored metrics" }));
    await waitForStoredMetric();
    expect(read).toHaveBeenLastCalledWith(SYNTHETIC_QUALITY_SESSION_ID, expect.any(AbortSignal));
  });

  it("dispatches before a fake 15-second stored-metrics deadline and retries visibly", async () => {
    vi.useFakeTimers();
    const transport = createSyntheticTransport();
    let signal: AbortSignal | undefined;
    const read = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>((sessionId, requestSignal): Promise<SessionMetricResponse> => {
      signal = requestSignal;
      return read.mock.calls.length === 1 ? pending() : Promise.resolve(metricsResponse(sessionId));
    });
    transport.getSessionMetrics = read;
    render(workspace(transport));
    await settle();

    expect(read).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(15_000);
      await Promise.resolve();
    });
    expect(signal?.aborted).toBe(true);
    expect(screen.getByRole("button", { name: "Retry stored metrics" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Retry stored metrics" }));
    await settle();
    expect(screen.getByText(STORED_LABEL)).toBeVisible();
  });

  it("contains a synchronous stored-metrics failure and visibly recovers", async () => {
    const transport = createSyntheticTransport();
    const read = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>((sessionId) => {
      if (read.mock.calls.length === 1) throw new Error("SYNTHETIC-STORED-METRICS-CANARY");
      return Promise.resolve(metricsResponse(sessionId));
    });
    transport.getSessionMetrics = read;
    render(workspace(transport));

    expect(await screen.findByRole("button", { name: "Retry stored metrics" })).toBeVisible();
    expect(document.body.textContent).not.toContain("SYNTHETIC-STORED-METRICS-CANARY");
    fireEvent.click(screen.getByRole("button", { name: "Retry stored metrics" }));
    await waitForStoredMetric();
  });

  it("coalesces synchronous double stored-metrics retries", async () => {
    const transport = createSyntheticTransport();
    const read = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(() => {
      if (read.mock.calls.length === 1) throw new Error("synthetic failure");
      return pending();
    });
    transport.getSessionMetrics = read;
    render(workspace(transport));

    const retry = await screen.findByRole("button", { name: "Retry stored metrics" });
    await act(async () => {
      fireEvent.click(retry);
      fireEvent.click(retry);
      await Promise.resolve();
    });
    expect(read).toHaveBeenCalledTimes(2);
  });

  it("clears a previously rendered stored metric in the parent layout phase on session change", async () => {
    const transport = createSyntheticTransport();
    const baseSessions = (await transport.listProjectSessions(SYNTHETIC_QUALITY_PROJECT_ID)).sessions;
    const second = { ...baseSessions[0], session_id: SECOND_SESSION_ID, session_display_name: "Synthetic replacement session" };
    transport.listProjectSessions = vi.fn(async () => ({
      sessions: [baseSessions[0], second], limit: 100, offset: 0, total: 2, has_more: false,
    }));
    transport.getSessionMetrics = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(async (sessionId) =>
      metricsResponse(sessionId, sessionId === SECOND_SESSION_ID ? NEXT_STORED_LABEL : STORED_LABEL, sessionId === SECOND_SESSION_ID ? 89 : 73),
    );
    const snapshots: string[] = [];
    function Probe({ sessionId }: { sessionId: string }) {
      useLayoutEffect(() => { snapshots.push(document.body.textContent ?? ""); });
      return workspace(transport, "tools", sessionId);
    }
    const view = render(<Probe sessionId={SYNTHETIC_QUALITY_SESSION_ID} />);
    await waitForStoredMetric();

    snapshots.length = 0;
    view.rerender(<Probe sessionId={SECOND_SESSION_ID} />);
    expect(snapshots.at(-1)).not.toContain(STORED_LABEL);
    await waitForStoredMetric(NEXT_STORED_LABEL);
  });

  it("fences a late old-session result after the selected session changes", async () => {
    const transport = createSyntheticTransport();
    const baseSessions = (await transport.listProjectSessions(SYNTHETIC_QUALITY_PROJECT_ID)).sessions;
    const second = { ...baseSessions[0], session_id: SECOND_SESSION_ID };
    transport.listProjectSessions = vi.fn(async () => ({
      sessions: [baseSessions[0], second], limit: 100, offset: 0, total: 2, has_more: false,
    }));
    const old = deferred<SessionMetricResponse>();
    transport.getSessionMetrics = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>((sessionId) =>
      sessionId === SYNTHETIC_QUALITY_SESSION_ID
        ? old.promise
        : Promise.resolve(metricsResponse(sessionId, NEXT_STORED_LABEL, 89)),
    );
    const view = render(workspace(transport));
    await screen.findByRole("button", { name: "Cancel stored metrics loading" });

    view.rerender(workspace(transport, "tools", SECOND_SESSION_ID));
    await act(async () => {
      old.resolve(metricsResponse(SYNTHETIC_QUALITY_SESSION_ID, "Late old-session metric", 17));
      await Promise.resolve();
    });
    await waitForStoredMetric(NEXT_STORED_LABEL);
    expect(screen.queryByText("Late old-session metric")).not.toBeInTheDocument();
  });

  it("fences a late stored result when the category changes", async () => {
    const transport = createSyntheticTransport();
    const old = deferred<SessionMetricResponse>();
    transport.getSessionMetrics = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(() => old.promise);
    const view = render(workspace(transport));
    await screen.findByRole("button", { name: "Cancel stored metrics loading" });

    view.rerender(workspace(transport, "prompt-quality"));
    await act(async () => {
      old.resolve(metricsResponse(SYNTHETIC_QUALITY_SESSION_ID, "Late category metric", 17));
      await Promise.resolve();
    });
    expect(screen.queryByText("Late category metric")).not.toBeInTheDocument();
  });

  it("fences a late stored result after transport replacement", async () => {
    const oldTransport = createSyntheticTransport();
    const old = deferred<SessionMetricResponse>();
    oldTransport.getSessionMetrics = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(() => old.promise);
    const newTransport = createSyntheticTransport();
    newTransport.getSessionMetrics = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(() => pending());
    const view = render(workspace(oldTransport));
    await screen.findByRole("button", { name: "Cancel stored metrics loading" });

    view.rerender(workspace(newTransport));
    await act(async () => {
      old.resolve(metricsResponse(SYNTHETIC_QUALITY_SESSION_ID, "Late transport metric", 17));
      await Promise.resolve();
    });
    expect(screen.queryByText("Late transport metric")).not.toBeInTheDocument();
  });

  it("aborts a dispatched stored-metrics read on unmount", async () => {
    const transport = createSyntheticTransport();
    let signal: AbortSignal | undefined;
    transport.getSessionMetrics = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>((_sessionId, requestSignal) => {
      signal = requestSignal;
      return pending();
    });
    const view = render(workspace(transport));
    await screen.findByRole("button", { name: "Cancel stored metrics loading" });

    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("starts quality and readiness reads only after the optional legacy profile opens", async () => {
    const transport = createSyntheticTransport();
    const quality = vi.fn<PromptEnhancerTransport["getLatestSessionQualityAnalysis"]>(() => pending());
    const readinessRead = vi.fn<PromptEnhancerTransport["getSessionMetricReadiness"]>(() => pending());
    transport.getLatestSessionQualityAnalysis = quality;
    transport.getSessionMetricReadiness = readinessRead;
    render(workspace(transport, "prompt-quality"));
    await screen.findByText("Legacy coaching profile");
    expect(quality).not.toHaveBeenCalled();
    expect(readinessRead).not.toHaveBeenCalled();

    await openLegacyProfile();
    expect(await screen.findByRole("button", { name: "Cancel quality loading" })).toBeVisible();
    expect(readinessRead).toHaveBeenCalledTimes(1);
  });

  it("cancels quality, fences its late result, and retries to a visible profile", async () => {
    const transport = createSyntheticTransport();
    const late = deferred<ReturnType<typeof qualityRun>>();
    const quality = vi.fn<PromptEnhancerTransport["getLatestSessionQualityAnalysis"]>((): Promise<SessionAnalysisRunResponse> =>
      quality.mock.calls.length === 1 ? late.promise : Promise.resolve(qualityRun()),
    );
    transport.getLatestSessionQualityAnalysis = quality;
    transport.getSessionMetricReadiness = vi.fn<PromptEnhancerTransport["getSessionMetricReadiness"]>(async () => readiness());
    render(workspace(transport, "prompt-quality"));
    await openLegacyProfile();

    fireEvent.click(await screen.findByRole("button", { name: "Cancel quality loading" }));
    await act(async () => {
      late.resolve(qualityRun());
      await Promise.resolve();
    });
    expect(screen.queryByText("Coherent metric pack v3")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry quality loading" }));
    expect(await screen.findByText("Coherent metric pack v3")).toBeVisible();
  });

  it("dispatches quality before its fake 15-second deadline and retries visibly", async () => {
    vi.useFakeTimers();
    const transport = createSyntheticTransport();
    const quality = vi.fn<PromptEnhancerTransport["getLatestSessionQualityAnalysis"]>((): Promise<SessionAnalysisRunResponse> =>
      quality.mock.calls.length === 1 ? pending() : Promise.resolve(qualityRun()),
    );
    transport.getLatestSessionQualityAnalysis = quality;
    transport.getSessionMetricReadiness = vi.fn<PromptEnhancerTransport["getSessionMetricReadiness"]>(async () => readiness());
    render(workspace(transport, "prompt-quality"));
    await settle();
    const legacy = screen.getByText("Legacy coaching profile");
    const details = legacy.closest("details");
    if (!(details instanceof HTMLDetailsElement)) throw new Error("Legacy profile disclosure is unavailable.");
    await openLegacyDetails(details);
    await settle();
    expect(quality).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(15_000);
      await Promise.resolve();
    });
    expect(screen.getByRole("button", { name: "Retry quality loading" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry quality loading" }));
    await settle();
    expect(screen.getByText("Coherent metric pack v3")).toBeVisible();
  });

  it.each([
    [404, false],
    [500, true],
  ] as const)("treats latest quality HTTP %s as %s error state without exposing failure text", async (status, hasError) => {
    const transport = createSyntheticTransport();
    transport.getLatestSessionQualityAnalysis = vi.fn<PromptEnhancerTransport["getLatestSessionQualityAnalysis"]>(async () => {
      throw new TransportError("SYNTHETIC-QUALITY-CANARY", status);
    });
    transport.getSessionMetricReadiness = vi.fn<PromptEnhancerTransport["getSessionMetricReadiness"]>(async () => readiness());
    render(workspace(transport, "prompt-quality"));
    await openLegacyProfile();

    if (hasError) {
      expect(await screen.findByRole("button", { name: "Retry quality loading" })).toBeVisible();
    } else {
      expect(await screen.findByText(/No compatible Coaching v1 analysis run is available/i)).toBeVisible();
    }
    expect(document.body.textContent).not.toContain("SYNTHETIC-QUALITY-CANARY");
  });

  it("cancels readiness independently and retries while quality stays visible", async () => {
    const transport = createSyntheticTransport();
    transport.getLatestSessionQualityAnalysis = vi.fn<PromptEnhancerTransport["getLatestSessionQualityAnalysis"]>(async () => qualityRun());
    const pendingReadiness = deferred<ReturnType<typeof readiness>>();
    const readinessRead = vi.fn<PromptEnhancerTransport["getSessionMetricReadiness"]>((): Promise<SessionMetricReadinessReport> =>
      readinessRead.mock.calls.length === 1 ? pendingReadiness.promise : Promise.resolve(readiness()),
    );
    transport.getSessionMetricReadiness = readinessRead;
    render(workspace(transport, "prompt-quality"));
    await openLegacyProfile();
    expect(await screen.findByText("Coherent metric pack v3")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Cancel readiness loading" }));
    expect(screen.getByRole("button", { name: "Retry readiness" })).toBeVisible();
    expect(screen.getByText("Coherent metric pack v3")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry readiness" }));
    await settle();
    expect(readinessRead).toHaveBeenCalledTimes(2);
  });

  it("dispatches readiness before its fake 15-second deadline and retries independently", async () => {
    vi.useFakeTimers();
    const transport = createSyntheticTransport();
    transport.getLatestSessionQualityAnalysis = vi.fn<PromptEnhancerTransport["getLatestSessionQualityAnalysis"]>(async () => qualityRun());
    const readinessRead = vi.fn<PromptEnhancerTransport["getSessionMetricReadiness"]>((): Promise<SessionMetricReadinessReport> =>
      readinessRead.mock.calls.length === 1 ? pending() : Promise.resolve(readiness()),
    );
    transport.getSessionMetricReadiness = readinessRead;
    render(workspace(transport, "prompt-quality"));
    await settle();
    const legacy = screen.getByText("Legacy coaching profile");
    const details = legacy.closest("details");
    if (!(details instanceof HTMLDetailsElement)) throw new Error("Legacy profile disclosure is unavailable.");
    await openLegacyDetails(details);
    await settle();
    expect(readinessRead).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(15_000);
      await Promise.resolve();
    });
    expect(screen.getByRole("button", { name: "Retry readiness" })).toBeVisible();
    expect(screen.getByText("Coherent metric pack v3")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry readiness" }));
    await settle();
    expect(readinessRead).toHaveBeenCalledTimes(2);
  });

  it("contains a synchronous readiness failure and allows a content-free retry", async () => {
    const transport = createSyntheticTransport();
    transport.getLatestSessionQualityAnalysis = vi.fn<PromptEnhancerTransport["getLatestSessionQualityAnalysis"]>(async () => qualityRun());
    const readinessRead = vi.fn<PromptEnhancerTransport["getSessionMetricReadiness"]>(() => {
      if (readinessRead.mock.calls.length === 1) throw new Error("SYNTHETIC-READINESS-CANARY");
      return Promise.resolve(readiness());
    });
    transport.getSessionMetricReadiness = readinessRead;
    render(workspace(transport, "prompt-quality"));
    await openLegacyProfile();

    expect(await screen.findByRole("button", { name: "Retry readiness" })).toBeVisible();
    expect(document.body.textContent).not.toContain("SYNTHETIC-READINESS-CANARY");
    fireEvent.click(screen.getByRole("button", { name: "Retry readiness" }));
    await settle();
    expect(readinessRead).toHaveBeenCalledTimes(2);
  });

  it("fences a late quality result when the legacy owner changes transport", async () => {
    const oldTransport = createSyntheticTransport();
    const late = deferred<ReturnType<typeof qualityRun>>();
    oldTransport.getLatestSessionQualityAnalysis = vi.fn<PromptEnhancerTransport["getLatestSessionQualityAnalysis"]>(() => late.promise);
    oldTransport.getSessionMetricReadiness = vi.fn<PromptEnhancerTransport["getSessionMetricReadiness"]>(async () => readiness());
    const nextTransport = createSyntheticTransport();
    nextTransport.getLatestSessionQualityAnalysis = vi.fn<PromptEnhancerTransport["getLatestSessionQualityAnalysis"]>(() => pending());
    nextTransport.getSessionMetricReadiness = vi.fn<PromptEnhancerTransport["getSessionMetricReadiness"]>(() => pending());
    const view = render(workspace(oldTransport, "prompt-quality"));
    await openLegacyProfile();
    await screen.findByRole("button", { name: "Cancel quality loading" });

    view.rerender(workspace(nextTransport, "prompt-quality"));
    await act(async () => {
      late.resolve(qualityRun());
      await Promise.resolve();
    });
    expect(screen.queryByText("Coherent metric pack v3")).not.toBeInTheDocument();
  });

  it.each([
    ["a null stored metrics collection", () => ({ session_id: SYNTHETIC_QUALITY_SESSION_ID, metrics: null })],
    ["a malformed stored metric row", () => ({
      session_id: SYNTHETIC_QUALITY_SESSION_ID,
      metrics: [{ ...storedMetric(), numeric_value: Number.NaN, metric_pack_key: null }],
    })],
  ])("rejects %s without fabricating a metric", async (_label, response) => {
    const transport = createSyntheticTransport();
    transport.getSessionMetrics = vi.fn<PromptEnhancerTransport["getSessionMetrics"]>(async () =>
      response() as unknown as SessionMetricResponse,
    );
    render(workspace(transport));

    expect(await screen.findByRole("button", { name: "Retry stored metrics" })).toBeVisible();
    expect(screen.queryByText(STORED_LABEL)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("NaN");
  });

  it("rejects malformed immutable quality results without rendering a profile", async () => {
    const transport = createSyntheticTransport();
    transport.getLatestSessionQualityAnalysis = vi.fn<PromptEnhancerTransport["getLatestSessionQualityAnalysis"]>(async () =>
      ({ ...qualityRun(), results: [null] } as unknown as ReturnType<typeof qualityRun>),
    );
    transport.getSessionMetricReadiness = vi.fn<PromptEnhancerTransport["getSessionMetricReadiness"]>(async () => readiness());
    render(workspace(transport, "prompt-quality"));
    await openLegacyProfile();

    expect(await screen.findByRole("button", { name: "Retry quality loading" })).toBeVisible();
    expect(screen.queryByText("Coherent metric pack v3")).not.toBeInTheDocument();
  });

  it("rejects malformed content-free readiness without fabricating readiness", async () => {
    const transport = createSyntheticTransport();
    transport.getLatestSessionQualityAnalysis = vi.fn<PromptEnhancerTransport["getLatestSessionQualityAnalysis"]>(async () => qualityRun());
    transport.getSessionMetricReadiness = vi.fn<PromptEnhancerTransport["getSessionMetricReadiness"]>(async () =>
      ({ ...readiness(), metrics: [null] } as unknown as ReturnType<typeof readiness>),
    );
    render(workspace(transport, "prompt-quality"));
    await openLegacyProfile();

    expect(await screen.findByRole("button", { name: "Retry readiness" })).toBeVisible();
    expect(screen.getByText("Coherent metric pack v3")).toBeVisible();
  });
});
