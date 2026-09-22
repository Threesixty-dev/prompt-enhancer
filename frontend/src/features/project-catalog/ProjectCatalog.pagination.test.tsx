import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CodexSession, CodexSessionListResponse, ProjectQualityAggregate, PromptEnhancerTransport } from "../../shared/api/contracts";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { SYNTHETIC_QUALITY_PROJECT_ID } from "../../shared/api/syntheticFixtures";
import { ProjectCatalog } from "./ProjectCatalog";

const PAGE = 100;
const key = (n: number) => n.toString(16).padStart(64, "0");

function row(n: number, name = `Fictional Project ${n}`): CodexSession {
  return {
    session_id: key(10_000 + n), installation_id: "1".repeat(64), project_id: key(20_000 + n),
    project_display_name: name, session_display_name: `Synthetic Session ${n}`, provider: "synthetic",
    project_display_name_origin: "provider", session_display_name_origin: "provider",
    project_manual_label_revision: 0, session_manual_label_revision: 0,
    provider_version: "example-provider-1", adapter_version: "example-adapter-1", source_schema_version: "example-schema-1",
    started_at: new Date(Date.parse("2040-12-31T09:00:00Z") - n * 60_000).toISOString(),
    ended_at: null, terminal_state: null, events_complete: n % 2 === 0,
  };
}
function page(sessions: CodexSession[], offset: number): CodexSessionListResponse { return { sessions, limit: PAGE, offset }; }
function transportFor(listCodexSessions: PromptEnhancerTransport["listCodexSessions"]): PromptEnhancerTransport { return { ...createSyntheticTransport(), listCodexSessions }; }
function loadNext() { return screen.getByRole("button", { name: `Load next ${PAGE} sessions` }); }
async function request(list: ReturnType<typeof vi.fn>, offset: number) {
  await waitFor(() => expect(list).toHaveBeenCalledWith(PAGE, offset, expect.any(AbortSignal)));
}

describe("ProjectCatalog pagination contract", () => {
  it("loads 100, 200, then an empty page; only the empty page marks the current index complete", async () => {
    const list = vi.fn(async (_limit = PAGE, offset = 0) => page(offset < 200 ? Array.from({ length: PAGE }, (_, i) => row(offset + i)) : [], offset));
    render(<ProjectCatalog navigate={vi.fn()} transport={transportFor(list)} />);
    await screen.findByText("Fictional Project 27");
    expect(screen.getByLabelText("Loaded catalog coverage")).toHaveTextContent("100 sessions");
    fireEvent.click(loadNext());
    await request(list, 100);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "project 100" } });
    expect(await screen.findByText("Fictional Project 100")).toBeVisible();
    expect(screen.getByLabelText("Loaded catalog coverage")).toHaveTextContent("200 sessions");
    fireEvent.click(loadNext());
    await request(list, 200);
    await waitFor(() => expect(screen.getByLabelText("Loaded catalog coverage")).toHaveTextContent("End of the current index reached"));
    expect(screen.queryByRole("button", { name: /Load next/i })).toBeNull();
  });

  it("keeps the 30-card bound and selection across a page append and filter", async () => {
    const list = vi.fn(async (_limit = PAGE, offset = 0) => page(offset === 0 ? Array.from({ length: PAGE }, (_, i) => row(i)) : [row(100, "Needle Project")], offset));
    render(<ProjectCatalog navigate={vi.fn()} transport={transportFor(list)} />);
    await screen.findByText("Fictional Project 27");
    expect(document.querySelectorAll(".project-catalog-card")).toHaveLength(30);
    fireEvent.click(screen.getByRole("checkbox", { name: /Select Fictional Project 27/ }));
    fireEvent.click(loadNext());
    await request(list, 100);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "needle" } });
    expect(await screen.findByText("Needle Project")).toBeVisible();
    const selection = screen.getByRole("complementary", { name: "Project aggregate selection" });
    expect(within(selection).getByRole("status")).toHaveTextContent("1 hidden by the current filter");
  });

  it("leaves the explicit next-page action reachable when a filter has no loaded matches", async () => {
    const list = vi.fn(async (_limit = PAGE, offset = 0) => page(offset === 0 ? Array.from({ length: PAGE }, (_, i) => row(i)) : [row(100, "Needle Project")], offset));
    render(<ProjectCatalog navigate={vi.fn()} transport={transportFor(list)} />);
    await screen.findByText("Fictional Project 27");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "needle" } });
    expect(screen.getByText("No matching projects")).toBeVisible();
    fireEvent.click(loadNext());
    expect(await screen.findByText("Needle Project")).toBeVisible();
  });

  it.each([
    ["wrong limit", { sessions: [row(1, "Malformed Page")], limit: 99, offset: 100 }],
    ["wrong offset", { sessions: [row(1, "Malformed Page")], limit: PAGE, offset: 7 }],
    ["additional key", { sessions: [row(1, "Malformed Page")], limit: PAGE, offset: 100, extra: true }],
    ["within-page duplicate", { sessions: [row(1), row(1)], limit: PAGE, offset: 100 }],
    ["cross-page duplicate", { sessions: [row(99), row(100)], limit: PAGE, offset: 100 }],
    ["invalid row", { sessions: [{ ...row(1), project_id: "not-a-pseudonym" }], limit: PAGE, offset: 100 }],
  ])("rejects a later %s and retains the preceding validated catalog", async (_label, malformed) => {
    const first = Array.from({ length: PAGE }, (_, i) => row(i)); let calls = 0;
    const list = vi.fn(async () => calls++ === 0 ? page(first, 0) : malformed);
    render(<ProjectCatalog navigate={vi.fn()} transport={transportFor(list as PromptEnhancerTransport["listCodexSessions"])} />);
    await screen.findByText("Fictional Project 27"); fireEvent.click(loadNext());
    expect(await screen.findByRole("alert")).toHaveTextContent(/unchanged|verified/i);
    expect(screen.getByText("Fictional Project 27")).toBeVisible();
    expect(screen.queryByText("Malformed Page")).toBeNull();
  });

  it.each([
    ["wrong first-page limit", { sessions: [row(1)], limit: 99, offset: 0 }],
    ["duplicate first-page row", { sessions: [row(1), row(1)], limit: PAGE, offset: 0 }],
  ])("fails closed before rendering an invalid %s", async (_label, malformed) => {
    const list = vi.fn(async () => malformed);
    render(<ProjectCatalog navigate={vi.fn()} transport={transportFor(list as PromptEnhancerTransport["listCodexSessions"])} />);
    expect(await screen.findByText("The locally indexed project catalog response was invalid.")).toBeVisible();
  });

  it("coalesces duplicate clicks and retries the same offset", async () => {
    let resolveSecond!: (value: CodexSessionListResponse) => void; let calls = 0;
    const list = vi.fn((_limit = PAGE, offset = 0) => {
      calls += 1;
      if (offset === 0) return Promise.resolve(page(Array.from({ length: PAGE }, (_, i) => row(i)), 0));
      if (calls === 2) return new Promise<CodexSessionListResponse>((resolve) => { resolveSecond = resolve; });
      return Promise.reject(new Error("synthetic page failure"));
    });
    render(<ProjectCatalog navigate={vi.fn()} transport={transportFor(list)} />);
    await screen.findByText("Fictional Project 27");
    const next = loadNext(); fireEvent.click(next); fireEvent.click(next);
    await request(list, 100); expect(list).toHaveBeenCalledTimes(2);
    await act(async () => { resolveSecond(page(Array.from({ length: PAGE }, (_, i) => row(100 + i)), 100)); });
    await waitFor(() => expect(screen.getByLabelText("Loaded catalog coverage")).toHaveTextContent("200 sessions"));
    fireEvent.click(loadNext());
    expect(await screen.findByText("More projects could not be loaded. Loaded projects are unchanged; try again or reload the catalog.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry next page" }));
    await waitFor(() => {
      expect(list).toHaveBeenCalledTimes(4);
      expect(list).toHaveBeenLastCalledWith(PAGE, 200, expect.any(AbortSignal));
    });
  });

  it("cancels a pending page and ignores its late result", async () => {
    let resolvePage!: (value: CodexSessionListResponse) => void;
    const list = vi.fn((_limit = PAGE, offset = 0) => offset === 0 ? Promise.resolve(page(Array.from({ length: PAGE }, (_, i) => row(i)), 0)) : new Promise<CodexSessionListResponse>((resolve) => { resolvePage = resolve; }));
    render(<ProjectCatalog navigate={vi.fn()} transport={transportFor(list)} />);
    await screen.findByText("Fictional Project 27"); fireEvent.click(loadNext()); await request(list, 100);
    fireEvent.click(screen.getByRole("button", { name: "Cancel catalog request" }));
    expect(await screen.findByText(/next catalog page was cancelled/i)).toBeVisible();
    await act(async () => { resolvePage(page([row(100, "Late Cancelled Project")], 100)); });
    expect(screen.getByLabelText("Loaded catalog coverage")).toHaveTextContent("100 sessions");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "late cancelled" } });
    expect(screen.queryByText("Late Cancelled Project")).toBeNull();
  });

  it("times out a pending page at 15 seconds and ignores its late result", async () => {
    let resolvePage!: (value: CodexSessionListResponse) => void;
    const list = vi.fn((_limit = PAGE, offset = 0) => offset === 0 ? Promise.resolve(page(Array.from({ length: PAGE }, (_, i) => row(i)), 0)) : new Promise<CodexSessionListResponse>((resolve) => { resolvePage = resolve; }));
    render(<ProjectCatalog navigate={vi.fn()} transport={transportFor(list)} />); await screen.findByText("Fictional Project 27");
    vi.useFakeTimers();
    try {
      fireEvent.click(loadNext()); await act(async () => { await Promise.resolve(); }); expect(list).toHaveBeenCalledTimes(2);
      await act(async () => { vi.advanceTimersByTime(15_000); }); expect(screen.getByText(/next catalog page timed out/i)).toBeVisible();
      await act(async () => { resolvePage(page([row(100, "Late Timed Out Project")], 100)); });
      expect(screen.getByLabelText("Loaded catalog coverage")).toHaveTextContent("100 sessions");
      fireEvent.change(screen.getByRole("searchbox"), { target: { value: "late timed out" } }); expect(screen.queryByText("Late Timed Out Project")).toBeNull();
    } finally { vi.useRealTimers(); }
  });

  it("surfaces a synchronous transport throw as a fixed catalog error", async () => {
    const list: PromptEnhancerTransport["listCodexSessions"] = vi.fn(() => { throw new Error("synthetic synchronous failure"); });
    render(<ProjectCatalog navigate={vi.fn()} transport={transportFor(list)} />);
    expect(await screen.findByText("The locally indexed project catalog could not be loaded.")).toBeVisible();
  });

  it("reload clears selection, aborts a pending aggregate, and requests offset zero again", async () => {
    const list = vi.fn(async (_limit = PAGE, offset = 0) => page([row(0, "Reloadable Project")], offset)); const transport = transportFor(list);
    let aggregateSignal: AbortSignal | undefined;
    transport.aggregateProjectQuality = vi.fn((_request, signal) => { aggregateSignal = signal; return new Promise<never>(() => undefined); });
    render(<ProjectCatalog navigate={vi.fn()} transport={transport} />); await screen.findByText("Reloadable Project");
    fireEvent.click(screen.getByRole("checkbox", { name: /Select Reloadable Project/ })); fireEvent.click(screen.getByRole("button", { name: "Combine selected" }));
    await waitFor(() => expect(aggregateSignal).toBeDefined()); fireEvent.click(screen.getByRole("button", { name: "Reload catalog" }));
    expect(aggregateSignal?.aborted).toBe(true); await request(list, 0);
    expect(screen.queryByRole("complementary", { name: "Project aggregate selection" })).toBeNull();
  });

  it("fences a late page and a valid late aggregate after transport replacement", async () => {
    let resolvePage!: (value: CodexSessionListResponse) => void; let resolveAggregate!: (value: ProjectQualityAggregate) => void;
    const synthetic = createSyntheticTransport(); const validAggregate = await synthetic.aggregateProjectQuality({ project_ids: [SYNTHETIC_QUALITY_PROJECT_ID], selection_mode: "all_analyzed_work" });
    const selected = { ...row(0, "Old Project"), project_id: SYNTHETIC_QUALITY_PROJECT_ID };
    const oldList = vi.fn((_limit = PAGE, offset = 0) => offset === 0 ? Promise.resolve(page(Array.from({ length: PAGE }, (_, i) => i === 0 ? selected : row(i)), 0)) : new Promise<CodexSessionListResponse>((resolve) => { resolvePage = resolve; }));
    const old = transportFor(oldList); old.aggregateProjectQuality = vi.fn(() => new Promise<ProjectQualityAggregate>((resolve) => { resolveAggregate = resolve; }));
    const { rerender } = render(<ProjectCatalog navigate={vi.fn()} transport={old} />); await screen.findByText("Old Project");
    fireEvent.click(screen.getByRole("checkbox", { name: /Select Old Project/ })); fireEvent.click(screen.getByRole("button", { name: "Combine selected" }));
    await waitFor(() => expect(old.aggregateProjectQuality).toHaveBeenCalled()); fireEvent.click(loadNext()); await request(oldList, 100);
    const replacement = transportFor(vi.fn(async (_limit = PAGE, offset = 0) => page([row(500, "Replacement Project")], offset)));
    rerender(<ProjectCatalog navigate={vi.fn()} transport={replacement} />); await screen.findByText("Replacement Project");
    await act(async () => { resolvePage(page([row(100, "Stale Project")], 100)); resolveAggregate(validAggregate); });
    expect(screen.getByText("Replacement Project")).toBeVisible();
    expect(screen.getByLabelText("Loaded catalog coverage")).toHaveTextContent("1 session");
    expect(screen.queryByText("Stale Project")).toBeNull(); expect(screen.queryByRole("heading", { name: "Combined project signal profile" })).toBeNull();
    expect(screen.queryByRole("complementary", { name: "Project aggregate selection" })).toBeNull();
  });

  it("renders an honest empty initial index without a next-page action", async () => {
    const list = vi.fn(async (_limit = PAGE, offset = 0) => page([], offset));
    render(<ProjectCatalog navigate={vi.fn()} transport={transportFor(list)} />);
    expect(await screen.findByText("No indexed projects")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Load next/i })).toBeNull();
  });
});
