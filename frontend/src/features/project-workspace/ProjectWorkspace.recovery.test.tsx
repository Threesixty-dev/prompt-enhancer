import { act, fireEvent, render, screen } from "@testing-library/react";
import { useLayoutEffect } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PromptEnhancerTransport } from "../../shared/api/contracts";
import { SYNTHETIC_CODEX_SESSIONS, SYNTHETIC_QUALITY_PROJECT_ID } from "../../shared/api/syntheticFixtures";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { ProjectWorkspace } from "./ProjectWorkspace";

const route = { name: "project_overview" as const, projectId: SYNTHETIC_QUALITY_PROJECT_ID };

afterEach(() => vi.useRealTimers());

async function settle() {
  await act(async () => { await Promise.resolve(); });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, reject, resolve };
}

function session(id: string) {
  return { ...SYNTHETIC_CODEX_SESSIONS[0], session_id: id };
}

function page(rows: ReturnType<typeof session>[], offset: number, total: number, hasMore: boolean) {
  expect(rows).toHaveLength(Math.min(Math.max(0, total - offset), 100));
  expect(hasMore).toBe(offset + rows.length < total);
  return { sessions: rows, limit: 100, offset, total, has_more: hasMore };
}

describe("ProjectWorkspace recovery", () => {
  it("offers cancellation and recovery when the initial project catalog exceeds 15 seconds", async () => {
    vi.useFakeTimers();
    try {
      const transport = createSyntheticTransport();
      transport.listProjectSessions = vi.fn(() => new Promise(() => undefined)) as PromptEnhancerTransport["listProjectSessions"];
      render(<ProjectWorkspace navigate={vi.fn()} route={route} transport={transport} />);
      await settle();
      expect(screen.getByRole("heading", { name: "Loading project..." })).toBeVisible();
      expect(screen.getByRole("button", { name: "Cancel project session loading" })).toBeVisible();
      await act(async () => { vi.advanceTimersByTime(15_000); await Promise.resolve(); });
      expect(screen.getByRole("button", { name: "Retry project sessions" })).toBeVisible();
    } finally {
      vi.useRealTimers();
    }
  });

  it("hides a ready project identity before passive effects on same-project transport replacement", async () => {
    const readyTransport = createSyntheticTransport();
    const hangingTransport = createSyntheticTransport();
    hangingTransport.listProjectSessions = vi.fn(() => new Promise(() => undefined)) as PromptEnhancerTransport["listProjectSessions"];
    const observed: string[] = [];
    function Probe({ transport }: { transport: PromptEnhancerTransport }) {
      useLayoutEffect(() => { observed.push(document.body.textContent ?? ""); });
      return <ProjectWorkspace navigate={vi.fn()} route={route} transport={transport} />;
    }
    const view = render(<Probe transport={readyTransport} />);
    await screen.findByRole("heading", { name: "Synthetic Metric Lab" });
    expect(screen.getByText("1 indexed session")).toBeVisible();
    observed.length = 0;
    view.rerender(<Probe transport={hangingTransport} />);
    expect(observed.at(-1)).toContain("Loading project...");
    expect(observed.at(-1)).not.toContain("Synthetic Metric Lab");
    expect(observed.at(-1)).not.toContain("1 indexed session");
  });

  it("cancels a hanging initial read, ignores its late valid page, and retries the exact first page", async () => {
    const transport = createSyntheticTransport();
    const pending = deferred<ReturnType<typeof page>>();
    let signal: AbortSignal | undefined;
    const list = vi.fn((_project: string, _limit: number, _offset: number, requestSignal?: AbortSignal) => {
      signal = requestSignal;
      return list.mock.calls.length === 1 ? pending.promise : Promise.resolve(page([session("1".repeat(64))], 0, 1, false));
    });
    transport.listProjectSessions = list as PromptEnhancerTransport["listProjectSessions"];
    render(<ProjectWorkspace navigate={vi.fn()} route={route} transport={transport} />);
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Cancel project session loading" }));
    expect(signal?.aborted).toBe(true);
    await act(async () => { pending.resolve(page([session("2".repeat(64))], 0, 1, false)); await Promise.resolve(); });
    expect(screen.queryByText("Synthetic Metric Lab")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry project sessions" }));
    await screen.findByRole("heading", { name: "Synthetic Metric Lab" });
    expect(list).toHaveBeenLastCalledWith(SYNTHETIC_QUALITY_PROJECT_ID, 100, 0, expect.any(AbortSignal));
  });

  it("times out an initial dispatched request once at 15 seconds, fences its late page, and retries", async () => {
    vi.useFakeTimers();
    try {
      const transport = createSyntheticTransport();
      const late = deferred<ReturnType<typeof page>>();
      let signal: AbortSignal | undefined;
      const list = vi.fn((_project: string, _limit: number, _offset: number, requestSignal?: AbortSignal) => {
        signal = requestSignal;
        return list.mock.calls.length === 1 ? late.promise : Promise.resolve(page([session("3".repeat(64))], 0, 1, false));
      });
      transport.listProjectSessions = list as PromptEnhancerTransport["listProjectSessions"];
      render(<ProjectWorkspace navigate={vi.fn()} route={route} transport={transport} />);
      await settle();
      expect(list).toHaveBeenCalledTimes(1);
      await act(async () => { vi.advanceTimersByTime(15_000); await Promise.resolve(); });
      expect(signal?.aborted).toBe(true);
      expect(screen.getByRole("button", { name: "Retry project sessions" })).toBeVisible();
      await act(async () => { late.resolve(page([session("4".repeat(64))], 0, 1, false)); await Promise.resolve(); });
      expect(screen.queryByText("Synthetic Metric Lab")).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Retry project sessions" }));
      await settle();
      expect(screen.getByRole("heading", { name: "Synthetic Metric Lab" })).toBeVisible();
      expect(list).toHaveBeenCalledTimes(2);
    } finally { vi.useRealTimers(); }
  });

  it("fails closed on synchronous and malformed resolved catalog pages without exposing errors", async () => {
    for (const [result, action] of [
      [() => { throw new Error("SYNTHETIC-PROJECT-CANARY"); }, "Retry project sessions"],
      [() => Promise.resolve({ ...page([session("5".repeat(64))], 0, 1, false), extra: true }), "Refresh project sessions"],
      [() => Promise.resolve(page([session("6".repeat(64)), session("6".repeat(64))], 0, 2, false)), "Refresh project sessions"],
    ] as const) {
      const transport = createSyntheticTransport();
      transport.listProjectSessions = vi.fn(result) as PromptEnhancerTransport["listProjectSessions"];
      const view = render(<ProjectWorkspace navigate={vi.fn()} route={route} transport={transport} />);
      await screen.findByRole("button", { name: action });
      expect(document.body.textContent).not.toContain("SYNTHETIC-PROJECT-CANARY");
      view.unmount();
    }
  });

  it("keeps the admitted first page while an older lookup fails, then retries from its original offset", async () => {
    const selectedId = "f".repeat(64);
    const first = Array.from({ length: 100 }, (_, index) => session(index.toString(16).padStart(64, "0")));
    const transport = createSyntheticTransport();
    const list = vi.fn((_project: string, _limit: number, offset: number) => {
      if (offset === 0) return Promise.resolve(page(first, 0, 101, true));
      if (list.mock.calls.filter(([, , value]) => value === 100).length === 1) {
        return Promise.reject(new Error("SYNTHETIC-OLDER-LOOKUP-CANARY"));
      }
      return Promise.resolve(page([session(selectedId)], 100, 101, false));
    });
    transport.listProjectSessions = list as PromptEnhancerTransport["listProjectSessions"];
    render(
      <ProjectWorkspace
        navigate={vi.fn()}
        route={{ name: "session_metrics", projectId: SYNTHETIC_QUALITY_PROJECT_ID, sessionId: selectedId, category: "tools" }}
        transport={transport}
      />,
    );
    await screen.findByRole("button", { name: "Retry older session lookup" });
    expect(screen.getByText("101 indexed sessions")).toBeVisible();
    expect(document.body.textContent).not.toContain("SYNTHETIC-OLDER-LOOKUP-CANARY");
    fireEvent.click(screen.getByRole("button", { name: "Retry older session lookup" }));
    await settle();
    expect(list.mock.calls.filter(([, , offset]) => offset === 100)).toHaveLength(2);
  });

  it("does not carry a 1,000-session continuation cursor into a same-route transport replacement", async () => {
    const selectedId = "e".repeat(64);
    const rowsAt = (offset: number) => Array.from(
      { length: 100 },
      (_, index) => session((offset + index).toString(16).padStart(64, "0")),
    );
    const firstTransport = createSyntheticTransport();
    const continuation = deferred<ReturnType<typeof page>>();
    firstTransport.listProjectSessions = vi.fn((_project, _limit, offset = 0) =>
      offset === 1_000
        ? continuation.promise
        : Promise.resolve(page(rowsAt(offset), offset, 1_101, true)),
    ) as PromptEnhancerTransport["listProjectSessions"];
    const secondTransport = createSyntheticTransport();
    const newCalls: number[] = [];
    secondTransport.listProjectSessions = vi.fn((_project, _limit, offset = 0) => {
      newCalls.push(offset);
      return Promise.resolve(offset === 0
        ? page(rowsAt(0), 0, 101, true)
        : page([session(selectedId)], 100, 101, false));
    }) as PromptEnhancerTransport["listProjectSessions"];
    const props = { navigate: vi.fn(), route: { name: "session_metrics" as const, projectId: SYNTHETIC_QUALITY_PROJECT_ID, sessionId: selectedId, category: "tools" as const } };
    const view = render(<ProjectWorkspace {...props} transport={firstTransport} />);
    await screen.findByRole("button", { name: "Search next 1,000 sessions" });
    expect((firstTransport.listProjectSessions as ReturnType<typeof vi.fn>).mock.calls.map(([, , offset]) => offset))
      .toEqual([0, 100, 200, 300, 400, 500, 600, 700, 800, 900]);
    fireEvent.click(screen.getByRole("button", { name: "Search next 1,000 sessions" }));
    await settle();
    expect((firstTransport.listProjectSessions as ReturnType<typeof vi.fn>).mock.calls.at(-1)?.[2]).toBe(1_000);
    view.rerender(<ProjectWorkspace {...props} transport={secondTransport} />);
    await settle();
    expect(newCalls.slice(0, 2)).toEqual([0, 100]);
    expect(newCalls).not.toContain(1_000);
  });

  it("uses one 15-second deadline for an older multi-page batch and fences its late selected session", async () => {
    vi.useFakeTimers();
    try {
      const selectedId = "d".repeat(64);
      const transport = createSyntheticTransport();
      const second = deferred<ReturnType<typeof page>>();
      const later = deferred<ReturnType<typeof page>>();
      const first = Array.from({ length: 100 }, (_, index) => session(index.toString(16).padStart(64, "0")));
      const secondRows = Array.from({ length: 100 }, (_, index) => session((100 + index).toString(16).padStart(64, "0")));
      transport.listProjectSessions = vi.fn((_project, _limit, offset = 0) => {
        if (offset === 0) return Promise.resolve(page(first, 0, 201, true));
        if (offset === 100) return second.promise;
        return later.promise;
      }) as PromptEnhancerTransport["listProjectSessions"];
      const metrics = vi.fn(async (id: string) => ({ session_id: id, metrics: [] }));
      transport.getSessionMetrics = metrics as PromptEnhancerTransport["getSessionMetrics"];
      render(<ProjectWorkspace navigate={vi.fn()} route={{ name: "session_metrics", projectId: SYNTHETIC_QUALITY_PROJECT_ID, sessionId: selectedId, category: "tools" }} transport={transport} />);
      await settle();
      await act(async () => { vi.advanceTimersByTime(10_000); second.resolve(page(secondRows, 100, 201, true)); await Promise.resolve(); });
      await settle();
      expect((transport.listProjectSessions as ReturnType<typeof vi.fn>).mock.calls.map(([, , offset]) => offset)).toEqual([0, 100, 200]);
      expect(screen.getByRole("button", { name: "Cancel older session lookup" })).toBeVisible();
      await act(async () => { vi.advanceTimersByTime(5_000); await Promise.resolve(); });
      expect(screen.getByRole("button", { name: "Retry older session lookup" })).toBeVisible();
      await act(async () => { later.resolve(page([session(selectedId)], 200, 201, false)); await Promise.resolve(); });
      expect(metrics).not.toHaveBeenCalledWith(selectedId, expect.anything());
    } finally { vi.useRealTimers(); }
  });

  it("does not dispatch a catalog read after immediate unmount", async () => {
    const transport = createSyntheticTransport();
    const list = vi.fn(() => Promise.resolve(page([], 0, 0, false)));
    transport.listProjectSessions = list as PromptEnhancerTransport["listProjectSessions"];
    const view = render(<ProjectWorkspace navigate={vi.fn()} route={route} transport={transport} />);
    view.unmount();
    await settle();
    expect(list).not.toHaveBeenCalled();
  });

  it("aborts an already dispatched catalog request on unmount", async () => {
    const transport = createSyntheticTransport();
    let signal: AbortSignal | undefined;
    transport.listProjectSessions = vi.fn((_project, _limit, _offset, requestSignal) => {
      signal = requestSignal;
      return new Promise(() => undefined);
    }) as PromptEnhancerTransport["listProjectSessions"];
    const view = render(<ProjectWorkspace navigate={vi.fn()} route={route} transport={transport} />);
    await settle();
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("coalesces captured retry clicks into one replacement catalog request", async () => {
    const transport = createSyntheticTransport();
    const pending = deferred<ReturnType<typeof page>>();
    const list = vi.fn(() => list.mock.calls.length === 1
      ? Promise.reject(new Error("synthetic transient"))
      : pending.promise);
    transport.listProjectSessions = list as PromptEnhancerTransport["listProjectSessions"];
    render(<ProjectWorkspace navigate={vi.fn()} route={route} transport={transport} />);
    const retry = await screen.findByRole("button", { name: "Retry project sessions" });
    await act(async () => { fireEvent.click(retry); fireEvent.click(retry); await Promise.resolve(); });
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("retries a cancelled 1,000-session continuation at offset 1,000 without restarting the catalog", async () => {
    const selectedId = "a".repeat(63) + "f";
    const rowsAt = (offset: number) => Array.from({ length: 100 }, (_, index) => session((offset + index).toString(16).padStart(64, "0")));
    const pending = deferred<ReturnType<typeof page>>();
    const transport = createSyntheticTransport();
    const list = vi.fn((_project, _limit, offset = 0) => {
      if (offset < 1_000) return Promise.resolve(page(rowsAt(offset), offset, 1_001, true));
      return list.mock.calls.filter(([, , value]) => value === 1_000).length === 1
        ? pending.promise
        : Promise.resolve(page([session(selectedId)], 1_000, 1_001, false));
    });
    const metrics = vi.fn(async (id: string) => ({ session_id: id, metrics: [] }));
    transport.listProjectSessions = list as PromptEnhancerTransport["listProjectSessions"];
    transport.getSessionMetrics = metrics as PromptEnhancerTransport["getSessionMetrics"];
    render(<ProjectWorkspace navigate={vi.fn()} route={{ name: "session_metrics", projectId: SYNTHETIC_QUALITY_PROJECT_ID, sessionId: selectedId, category: "tools" }} transport={transport} />);
    const search = await screen.findByRole("button", { name: "Search next 1,000 sessions" });
    fireEvent.click(search);
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Cancel older session lookup" }));
    fireEvent.click(screen.getByRole("button", { name: "Retry older session lookup" }));
    await settle();
    expect(list.mock.calls.map(([, , offset]) => offset).filter((offset) => offset === 1_000)).toHaveLength(2);
    expect(list.mock.calls.map(([, , offset]) => offset).slice(-1)).toEqual([1_000]);
    await settle();
    expect(metrics).toHaveBeenCalledWith(selectedId, expect.any(AbortSignal));
  });

  it("fences a late valid older-session result after a same-base session change", async () => {
    const sessionA = "a".repeat(64);
    const sessionB = "b".repeat(64);
    const first = Array.from({ length: 100 }, (_, index) => session((100 + index).toString(16).padStart(64, "0")));
    const lateA = deferred<ReturnType<typeof page>>();
    const pendingB = deferred<ReturnType<typeof page>>();
    const transport = createSyntheticTransport();
    const list = vi.fn((_project, _limit, offset = 0) => {
      if (offset === 0) return Promise.resolve(page(first, 0, 101, true));
      return list.mock.calls.filter(([, , value]) => value === 100).length === 1 ? lateA.promise : pendingB.promise;
    });
    const metrics = vi.fn(async (id: string) => ({ session_id: id, metrics: [] }));
    transport.listProjectSessions = list as PromptEnhancerTransport["listProjectSessions"];
    transport.getSessionMetrics = metrics as PromptEnhancerTransport["getSessionMetrics"];
    const props = { navigate: vi.fn(), transport };
    const view = render(<ProjectWorkspace {...props} route={{ name: "session_metrics", projectId: SYNTHETIC_QUALITY_PROJECT_ID, sessionId: sessionA, category: "tools" }} />);
    await settle();
    view.rerender(<ProjectWorkspace {...props} route={{ name: "session_metrics", projectId: SYNTHETIC_QUALITY_PROJECT_ID, sessionId: sessionB, category: "tools" }} />);
    await act(async () => { lateA.resolve(page([session(sessionA)], 100, 101, false)); await Promise.resolve(); });
    expect(metrics).not.toHaveBeenCalledWith(sessionA, expect.anything());
    await act(async () => { pendingB.resolve(page([session(sessionB)], 100, 101, false)); await Promise.resolve(); });
    await settle();
    expect(metrics).toHaveBeenCalledWith(sessionB, expect.any(AbortSignal));
  });

  it("resets an inconsistent older lookup reason after refreshing the base and offers retry for a later cancellation", async () => {
    const selectedId = "c".repeat(64);
    const baseRows = Array.from({ length: 100 }, (_, index) => session(index.toString(16).padStart(64, "0")));
    const refreshedRows = Array.from({ length: 100 }, (_, index) => session((100 + index).toString(16).padStart(64, "0")));
    const pending = deferred<ReturnType<typeof page>>();
    const transport = createSyntheticTransport();
    const list = vi.fn((_project, _limit, offset = 0) => {
      const callsAtOffset = list.mock.calls.filter(([, , value]) => value === offset).length;
      if (offset === 0) return callsAtOffset === 1
        ? Promise.resolve(page(baseRows, 0, 101, true))
        : Promise.resolve(page(refreshedRows, 0, 101, true));
      if (callsAtOffset === 1) return Promise.resolve({ ...page([session(selectedId)], 100, 101, false), extra: true });
      if (callsAtOffset === 2) return pending.promise;
      return Promise.resolve(page([session(selectedId)], 100, 101, false));
    });
    const metrics = vi.fn(async (id: string) => ({ session_id: id, metrics: [] }));
    transport.listProjectSessions = list as PromptEnhancerTransport["listProjectSessions"];
    transport.getSessionMetrics = metrics as PromptEnhancerTransport["getSessionMetrics"];
    render(<ProjectWorkspace navigate={vi.fn()} route={{ name: "session_metrics", projectId: SYNTHETIC_QUALITY_PROJECT_ID, sessionId: selectedId, category: "tools" }} transport={transport} />);
    await screen.findByRole("button", { name: "Refresh project sessions" });
    fireEvent.click(screen.getByRole("button", { name: "Refresh project sessions" }));
    await settle();
    expect(screen.getByText("101 indexed sessions")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Cancel older session lookup" }));
    expect(screen.getByRole("button", { name: "Retry older session lookup" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Refresh project sessions" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry older session lookup" }));
    await settle();
    await settle();
    expect(metrics).toHaveBeenCalledWith(selectedId, expect.any(AbortSignal));
  });
});
