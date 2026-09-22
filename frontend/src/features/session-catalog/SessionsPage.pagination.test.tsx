import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CodexSession, CodexSessionListResponse, PromptEnhancerTransport } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { parseSessionCatalogPage, safeSessionCatalogRow } from "../../shared/api/sessionCatalogContract";
import { SessionsPage } from "./SessionsPage";

const PAGE = 100;
const key = (n: number) => n.toString(16).padStart(64, "0");

function session(n: number, title = `Synthetic session ${n}`): CodexSession {
  return {
    session_id: key(n), installation_id: "1".repeat(64), project_id: key(10_000 + n),
    project_display_name: `Fictional project ${n % 3}`, session_display_name: title,
    provider: n % 2 ? "codex" : "claude_code", project_display_name_origin: "provider", session_display_name_origin: "provider",
    project_manual_label_revision: 0, session_manual_label_revision: 0,
    provider_version: "example-provider-1", adapter_version: "example-adapter-1", source_schema_version: "example-schema-1",
    started_at: new Date(Date.parse("2040-12-31T09:00:00Z") - n * 60_000).toISOString(), ended_at: null,
    terminal_state: null, events_complete: false,
  };
}
function page(sessions: CodexSession[], offset: number): CodexSessionListResponse { return { sessions, limit: PAGE, offset }; }
function transport(listCodexSessions: PromptEnhancerTransport["listCodexSessions"]): Pick<PromptEnhancerTransport, "listCodexSessions"> { return { listCodexSessions }; }
function next() { return screen.getByRole("button", { name: "Load next 100 sessions" }); }
async function requested(list: ReturnType<typeof vi.fn>, offset: number) {
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(PAGE, offset, expect.any(AbortSignal)));
}

describe("SessionsPage explicit catalog pagination", () => {
  it("loads only the first 100 initially, then 200 and an explicit empty completion page", async () => {
    const list = vi.fn(async (_limit = PAGE, offset = 0) => page(offset < 200 ? Array.from({ length: PAGE }, (_, i) => session(offset + i)) : [], offset));
    render(<SessionsPage navigate={vi.fn()} transport={transport(list)} />);
    await screen.findByText("Synthetic session 0");
    expect(list).toHaveBeenCalledTimes(1); await requested(list, 0);
    expect(screen.getAllByRole("listitem")).toHaveLength(50);
    fireEvent.click(next()); await requested(list, 100);
    expect(screen.getByText(/200 loaded sessions/i)).toBeVisible();
    fireEvent.click(next()); await requested(list, 200);
    await waitFor(() => expect(screen.queryByRole("button", { name: /Load next/i })).toBeNull());
  });

  it("stops after a short second page, bounds rendering at 50, and searches only loaded rows", async () => {
    const first = Array.from({ length: PAGE }, (_, i) => session(i));
    const list = vi.fn(async (_limit = PAGE, offset = 0) => page(offset === 0 ? first : [session(100, "Needle after first page")], offset));
    render(<SessionsPage navigate={vi.fn()} transport={transport(list)} />);
    await screen.findByText("Synthetic session 0");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "needle" } });
    expect(screen.getByText("No sessions match")).toBeVisible(); expect(list).toHaveBeenCalledTimes(1);
    fireEvent.click(next()); await screen.findByText("Needle after first page");
    expect(list).toHaveBeenCalledTimes(2); expect(screen.queryByRole("button", { name: /Load next/i })).toBeNull();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "" } });
    expect(screen.getAllByRole("listitem")).toHaveLength(50);
    expect(screen.getByRole("navigation", { name: "Stored session pages" })).toHaveTextContent("Showing 1–50 of 101");
  });

  it.each([
    ["wrong limit", { sessions: [session(100)], limit: 99, offset: 100 }],
    ["wrong offset", { sessions: [session(100)], limit: PAGE, offset: 8 }],
    ["extra envelope key", { sessions: [session(100)], limit: PAGE, offset: 100, additional: true }],
    ["within-page duplicate", { sessions: [session(100), session(100)], limit: PAGE, offset: 100 }],
    ["cross-page duplicate", { sessions: [session(99), session(100)], limit: PAGE, offset: 100 }],
    ["invalid date", { sessions: [{ ...session(100), started_at: "not-a-date" }], limit: PAGE, offset: 100 }],
  ])("rejects a later %s without replacing the validated first page", async (_label, malformed) => {
    let calls = 0; const first = Array.from({ length: PAGE }, (_, i) => session(i));
    const list = vi.fn(async () => calls++ === 0 ? page(first, 0) : malformed);
    render(<SessionsPage navigate={vi.fn()} transport={transport(list as PromptEnhancerTransport["listCodexSessions"])} />);
    await screen.findByText("Synthetic session 0"); fireEvent.click(next());
    expect(await screen.findByRole("alert")).toHaveTextContent(/unchanged|verified|invalid/i);
    expect(screen.getByText("Synthetic session 0")).toBeVisible();
  });

  it("coalesces duplicate next clicks, cancels the request, and ignores its late page", async () => {
    let resolve!: (response: CodexSessionListResponse) => void;
    const list = vi.fn((_limit = PAGE, offset = 0) => offset === 0 ? Promise.resolve(page(Array.from({ length: PAGE }, (_, i) => session(i)), 0)) : new Promise<CodexSessionListResponse>((done) => { resolve = done; }));
    render(<SessionsPage navigate={vi.fn()} transport={transport(list)} />); await screen.findByText("Synthetic session 0");
    const action = next(); await act(async () => { fireEvent.click(action); fireEvent.click(action); }); await requested(list, 100); expect(list).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "Cancel catalog request" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/cancelled/i);
    await act(async () => { resolve(page([session(100, "Late cancelled session")], 100)); });
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "late cancelled" } });
    expect(screen.queryByText("Late cancelled session")).toBeNull();
  });

  it("fences a late old-page response and resets the old provider filter after transport replacement", async () => {
    let resolveOld!: (response: CodexSessionListResponse) => void;
    const oldList = vi.fn((_limit = PAGE, offset = 0) => offset === 0 ? Promise.resolve(page(Array.from({ length: PAGE }, (_, i) => session(i)), 0)) : new Promise<CodexSessionListResponse>((done) => { resolveOld = done; }));
    const { rerender } = render(<SessionsPage navigate={vi.fn()} transport={transport(oldList)} />); await screen.findByText("Synthetic session 0");
    fireEvent.click(screen.getByRole("button", { name: "Claude Code" })); fireEvent.click(next()); await requested(oldList, 100);
    const replacement = vi.fn(async (_limit = PAGE, offset = 0) => page([session(501, "Replacement Codex session")], offset));
    rerender(<SessionsPage navigate={vi.fn()} transport={transport(replacement)} />); await screen.findByText("Replacement Codex session");
    await act(async () => { resolveOld(page([session(100, "Stale old page")], 100)); });
    expect(screen.getByText("Replacement Codex session")).toBeVisible(); expect(screen.queryByText("Stale old page")).toBeNull();
    expect(screen.getByRole("button", { name: "All sources" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/1 of 1 session/)).toBeVisible();
  });

  it("cancels an initial request before deferred dispatch and reloads with a new offset-zero call", async () => {
    const list = vi.fn(async (_limit = PAGE, offset = 0) => page([session(offset, `Reload ${offset}`)], offset));
    render(<SessionsPage navigate={vi.fn()} transport={transport(list)} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel catalog request" }));
    await act(async () => { await Promise.resolve(); });
    expect(list).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Reload catalog" }));
    await screen.findByText("Reload 0"); await requested(list, 0);
  });

  it("surfaces a synchronous initial transport failure without rendering catalog data", async () => {
    const list: PromptEnhancerTransport["listCodexSessions"] = vi.fn(() => { throw new Error("synthetic synchronous failure"); });
    render(<SessionsPage navigate={vi.fn()} transport={transport(list)} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The stored session catalog could not be loaded.");
    expect(screen.queryByRole("listitem")).toBeNull();
  });

  it("uses the fixed sign-in message for an initial 401 and never exposes transport text", async () => {
    const list = vi.fn(async () => { throw new TransportError("synthetic secret canary", 401); });
    render(<SessionsPage navigate={vi.fn()} transport={transport(list)} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign in to the local service to list sessions.");
    expect(document.body.textContent).not.toContain("synthetic secret canary");
  });

  it("times out initial and later requests at 15 seconds and fences their late valid pages", async () => {
    let resolveInitial!: (value: CodexSessionListResponse) => void; let resolveLater!: (value: CodexSessionListResponse) => void;
    const list = vi.fn()
      .mockImplementationOnce(() => new Promise<CodexSessionListResponse>((done) => { resolveInitial = done; }))
      .mockImplementationOnce(async () => page(Array.from({ length: PAGE }, (_, i) => session(i)), 0))
      .mockImplementationOnce(() => new Promise<CodexSessionListResponse>((done) => { resolveLater = done; }));
    vi.useFakeTimers();
    try {
      render(<SessionsPage navigate={vi.fn()} transport={transport(list)} />); await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      await act(async () => { vi.advanceTimersByTime(15_000); }); expect(screen.getByRole("alert")).toHaveTextContent(/timed out/i);
      await act(async () => { resolveInitial(page([session(900, "Late initial")], 0)); }); expect(screen.queryByText("Late initial")).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Reload catalog" })); await act(async () => { await Promise.resolve(); await Promise.resolve(); }); expect(screen.getByText("Synthetic session 0")).toBeVisible();
      fireEvent.click(next()); await act(async () => { await Promise.resolve(); vi.advanceTimersByTime(15_000); });
      expect(screen.getByRole("alert")).toHaveTextContent(/next catalog page timed out/i); expect(screen.getByText(/100 of 100 sessions/)).toBeVisible();
      await act(async () => { resolveLater(page([session(901, "Late later")], 100)); }); fireEvent.change(screen.getByRole("searchbox"), { target: { value: "late later" } }); expect(screen.getByText(/0 of 100 sessions/)).toBeVisible();
    } finally { vi.useRealTimers(); }
  });

  it("retries a failed later page at the same offset and retains the first 100 until success", async () => {
    let calls = 0; const first = Array.from({ length: PAGE }, (_, i) => session(i));
    const list = vi.fn(async (_limit = PAGE, offset = 0) => offset === 0 ? page(first, 0) : calls++ === 0 ? Promise.reject(new Error("synthetic later failure")) : page([session(100, "Recovered page")], 100));
    render(<SessionsPage navigate={vi.fn()} transport={transport(list)} />); await screen.findByText("Synthetic session 0"); fireEvent.click(next());
    expect(await screen.findByRole("alert")).toHaveTextContent(/loaded sessions are unchanged/i); expect(screen.getByText(/100 of 100 sessions/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry next page" })); await waitFor(() => expect(screen.getByText(/101 of 101 sessions/)).toBeVisible()); fireEvent.change(screen.getByRole("searchbox"), { target: { value: "recovered page" } }); expect(screen.getByText("Recovered page")).toBeVisible();
    expect(list.mock.calls.slice(1).map((call) => call[1])).toEqual([100, 100]);
  });

  it("aborts an in-flight first page on unmount and never publishes its late response", async () => {
    let resolve!: (value: CodexSessionListResponse) => void; let signal: AbortSignal | undefined;
    const list = vi.fn((_limit = PAGE, _offset = 0, requestSignal?: AbortSignal) => { signal = requestSignal; return new Promise<CodexSessionListResponse>((done) => { resolve = done; }); });
    const view = render(<SessionsPage navigate={vi.fn()} transport={transport(list)} />); await requested(list, 0); view.unmount();
    expect(signal?.aborted).toBe(true); await act(async () => { resolve(page([session(700, "Late unmounted")], 0)); });
    expect(screen.queryByText("Late unmounted")).toBeNull();
  });

  it("reload clears captured calls, starts exactly one new offset-zero request, and fences an old page", async () => {
    let resolveOld!: (value: CodexSessionListResponse) => void; let first = true;
    const list = vi.fn((_limit = PAGE, offset = 0) => offset === 100 ? new Promise<CodexSessionListResponse>((done) => { resolveOld = done; }) : first ? (first = false, Promise.resolve(page(Array.from({ length: PAGE }, (_, i) => session(i)), 0))) : Promise.resolve(page([session(800, "Reload replacement")], 0)));
    render(<SessionsPage navigate={vi.fn()} transport={transport(list)} />); await screen.findByText("Synthetic session 0"); fireEvent.click(next()); await requested(list, 100);
    list.mockClear(); fireEvent.click(screen.getByRole("button", { name: "Reload catalog" })); await screen.findByText("Reload replacement");
    expect(list).toHaveBeenCalledTimes(1); await requested(list, 0); await act(async () => { resolveOld(page([session(100, "Late reload old page")], 100)); });
    expect(screen.queryByText("Late reload old page")).toBeNull();
  });

  it("requires exact full rows, provenance, dates, and envelopes before accepting a page", () => {
    const valid = session(1);
    expect(safeSessionCatalogRow(valid)).toBe(true); expect(parseSessionCatalogPage(page([valid], 0), 0)).toEqual([valid]);
    expect(safeSessionCatalogRow({ ...valid, project_display_name_origin: "invented" })).toBe(false);
    const missing = { ...valid }; delete (missing as Partial<CodexSession>).adapter_version;
    expect(safeSessionCatalogRow(missing)).toBe(false); expect(safeSessionCatalogRow({ ...valid, ended_at: "2040-02-30T10:00:00Z" })).toBe(false);
    expect(parseSessionCatalogPage({ ...page([valid], 0), extra: true }, 0)).toBeNull();
  });
});
