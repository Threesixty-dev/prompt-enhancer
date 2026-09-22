import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  AgentWorkspaceDiscovery,
  AgentWorkspaceFile,
  AgentWorkspaceSearchResult,
} from "../../shared/api/contracts";
import { AgentWorkspacePane } from "./AgentWorkspacePane";

const SESSION = "a".repeat(32);
const CONTENT = "const first = true;\nconst syntheticMatch = true;\nconst last = false;\n";
const OTHER_CONTENT = "const otherFirst = true;\nconst otherMatch = true;\n";
const MATCH_START = CONTENT.indexOf("const syntheticMatch = true;");
const MATCH_END = CONTENT.indexOf("\n", MATCH_START);

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((complete) => { resolve = complete; });
  return { promise, resolve };
}

function workspaceFile(
  path = "src/example.ts",
  content = CONTENT,
  sessionId = SESSION,
): AgentWorkspaceFile {
  return {
    contract_version: "local-agent-workspace.v1",
    session_id: sessionId,
    path,
    content,
    revision: "b".repeat(64),
    byte_size: new TextEncoder().encode(content).byteLength,
    line_ending: "lf",
    editable: true,
  };
}

function discovery(files: Record<string, AgentWorkspaceFile>): AgentWorkspaceDiscovery {
  const workspaceFiles = Object.values(files);
  return {
    contract_version: "local-agent-workspace-discovery.v1",
    session_id: SESSION,
    scope: "selected_workspace",
    inventory_coverage: "complete",
    inventory_reasons: [],
    scanned_entry_count: workspaceFiles.length,
    observed_file_count: workspaceFiles.length,
    files: workspaceFiles.map((file) => ({
      path: file.path,
      byte_size: file.byte_size,
      editable_candidate: file.editable,
    })),
    git_state: "not_repository",
    git_coverage: "not_applicable",
    git_reasons: [],
    git_change_count: 0,
    git_changes: [],
  };
}

function searchResult(
  matches: AgentWorkspaceSearchResult["matches"] = [{ path: "src/example.ts", line_number: 2, preview: "const syntheticMatch = true;" }],
): AgentWorkspaceSearchResult {
  return {
    contract_version: "local-agent-workspace-search.v1",
    session_id: SESSION,
    scope: "application_readable_utf8_text",
    coverage: "complete",
    reasons: [],
    reason_code: null,
    scanned_entry_count: 1,
    inspected_byte_count: workspaceFile().byte_size,
    skipped_entry_count: 0,
    match_count: matches.length,
    matches,
  };
}

function workspaceTransport({
  search = searchResult(),
  files = {
    "src/example.ts": workspaceFile(),
    "src/other.ts": workspaceFile("src/other.ts", OTHER_CONTENT),
  },
}: {
  search?: AgentWorkspaceSearchResult;
  files?: Record<string, AgentWorkspaceFile>;
} = {}) {
  return {
    getAgentWorkspaceTree: vi.fn(async (sessionId: string, path: string) => ({
      contract_version: "local-agent-workspace.v1" as const,
      session_id: sessionId,
      path,
      entries: [{ path: "src", name: "src", kind: "directory" as const, byte_size: null, editable_candidate: false }],
      complete: true,
    })),
    getAgentWorkspaceFile: vi.fn(async (_sessionId: string, path: string) => files[path] ?? workspaceFile()),
    previewAgentWorkspaceEdit: vi.fn(),
    applyAgentWorkspaceEdit: vi.fn(),
    getAgentWorkspaceDiscovery: vi.fn(async () => discovery(files)),
    getAgentWorkspaceSearch: vi.fn(async () => search),
  };
}

async function runWorkspaceSearch() {
  const query = await screen.findByRole("searchbox", { name: "Search workspace contents" });
  fireEvent.change(query, { target: { value: "syntheticMatch" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
}

async function openSearchResult(path: string, line: number) {
  fireEvent.click(await screen.findByRole("button", { name: `Open search result ${path} line ${line}` }));
  const editor = await screen.findByRole("textbox", { name: "Workspace file editor" }) as HTMLTextAreaElement;
  const expectedContent = path === "src/other.ts" ? OTHER_CONTENT : CONTENT;
  const lineStart = expectedContent.split("\n").slice(0, line - 1).join("\n").length + (line > 1 ? 1 : 0);
  const lineEnd = expectedContent.indexOf("\n", lineStart);
  await waitFor(() => {
    expect(editor).toBeEnabled();
    expect(editor).toHaveValue(expectedContent);
    expect(editor).toHaveFocus();
    expect(editor.selectionStart).toBe(lineStart);
    expect(editor.selectionEnd).toBe(lineEnd < 0 ? expectedContent.length : lineEnd);
  });
  return editor;
}

function openEditorNavigationTools() {
  fireEvent.click(screen.getByText("Find & go to line"));
}

describe("AgentWorkspacePane workspace-search navigation", () => {
  it("opens a search result at its exact line and focuses the selected editor range", async () => {
    const transport = workspaceTransport();
    render(<AgentWorkspacePane pendingWrite={null} sessionId={SESSION} transport={transport} />);

    await runWorkspaceSearch();
    const editor = await openSearchResult("src/example.ts", 2);
    expect(editor).toHaveValue(CONTENT);
    await waitFor(() => {
      expect(editor).toHaveFocus();
      expect(editor.selectionStart).toBe(MATCH_START);
      expect(editor.selectionEnd).toBe(MATCH_END);
    });
  });

  it("navigates within a dirty open file without reading it again or discarding the draft", async () => {
    const transport = workspaceTransport();
    render(<AgentWorkspacePane pendingWrite={null} sessionId={SESSION} transport={transport} />);

    await runWorkspaceSearch();
    const editor = await openSearchResult("src/example.ts", 2);
    fireEvent.change(editor, { target: { value: `${CONTENT}// unsaved synthetic note\n` } });
    const callsBeforeNavigation = transport.getAgentWorkspaceFile.mock.calls.length;
    const lastLineStart = CONTENT.indexOf("const last = false;");
    const lastLineEnd = CONTENT.indexOf("\n", lastLineStart);
    openEditorNavigationTools();
    fireEvent.change(screen.getByRole("spinbutton", { name: "Go to line" }), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Go to line" }));

    await waitFor(() => {
      expect(editor).toHaveValue(`${CONTENT}// unsaved synthetic note\n`);
      expect(editor.selectionStart).toBe(lastLineStart);
      expect(editor.selectionEnd).toBe(lastLineEnd);
    });
    expect(transport.getAgentWorkspaceFile).toHaveBeenCalledTimes(callsBeforeNavigation);
    expect(screen.queryByRole("dialog", { name: "Discard workspace changes?" })).toBeNull();
  });

  it("keeps a dirty draft on cancel, then discards it only before opening a different search result at its line", async () => {
    const transport = workspaceTransport({ search: searchResult([
      { path: "src/example.ts", line_number: 2, preview: "const syntheticMatch = true;" },
      { path: "src/other.ts", line_number: 2, preview: "const otherMatch = true;" },
    ]) });
    render(<AgentWorkspacePane pendingWrite={null} sessionId={SESSION} transport={transport} />);

    await runWorkspaceSearch();
    const editor = await openSearchResult("src/example.ts", 2);
    fireEvent.change(editor, { target: { value: "// dirty fictional draft\n" } });
    const callsBeforeOther = transport.getAgentWorkspaceFile.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Open search result src/other.ts line 2" }));
    fireEvent.click(await screen.findByRole("button", { name: "Keep draft" }));
    expect(editor).toHaveValue("// dirty fictional draft\n");
    expect(transport.getAgentWorkspaceFile).toHaveBeenCalledTimes(callsBeforeOther);

    fireEvent.click(screen.getByRole("button", { name: "Open search result src/other.ts line 2" }));
    fireEvent.click(await screen.findByRole("button", { name: "Discard and open file" }));
    const otherStart = OTHER_CONTENT.indexOf("const otherMatch = true;");
    const otherEnd = OTHER_CONTENT.indexOf("\n", otherStart);
    await waitFor(() => {
      expect(editor).toHaveValue(OTHER_CONTENT);
      expect(editor).toHaveFocus();
      expect(editor.selectionStart).toBe(otherStart);
      expect(editor.selectionEnd).toBe(otherEnd);
    });
  });

  it("rejects invalid and out-of-range line requests without claiming an exact selection", async () => {
    const transport = workspaceTransport();
    render(<AgentWorkspacePane pendingWrite={null} sessionId={SESSION} transport={transport} />);

    await runWorkspaceSearch();
    const editor = await openSearchResult("src/example.ts", 2);
    const originalStart = editor.selectionStart;
    openEditorNavigationTools();
    const line = screen.getByRole("spinbutton", { name: "Go to line" });
    fireEvent.change(line, { target: { value: "999" } });
    fireEvent.click(screen.getByRole("button", { name: "Go to line" }));

    expect(await screen.findByText("Enter a whole line number from 1 to 4.")).toBeVisible();
    expect(screen.queryByText("Line 999 selected.")).toBeNull();
    expect(editor.selectionStart).toBe(originalStart);
  });

  it("allows local find and line navigation in a read-only retained draft without a write", async () => {
    const transport = workspaceTransport();
    render(<AgentWorkspacePane blockedReason="Synthetic navigation lock" pendingWrite={null} sessionId={SESSION} transport={transport} />);

    await runWorkspaceSearch();
    const editor = await openSearchResult("src/example.ts", 2);
    expect(editor).toHaveAttribute("readonly");
    openEditorNavigationTools();
    expect(screen.getByRole("searchbox", { name: "Find in open file" })).toBeEnabled();
    expect(screen.getByRole("spinbutton", { name: "Go to line" })).toBeEnabled();
    fireEvent.change(screen.getByRole("spinbutton", { name: "Go to line" }), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Go to line" }));
    await waitFor(() => expect(editor.selectionStart).toBe(CONTENT.indexOf("const last = false;")));
    expect(transport.previewAgentWorkspaceEdit).not.toHaveBeenCalled();
    expect(transport.applyAgentWorkspaceEdit).not.toHaveBeenCalled();
  });

  it.each(["session", "transport"] as const)("ignores a stale workspace read after its %s owner is replaced", async (replacement) => {
    const pending = deferred<AgentWorkspaceFile>();
    const oldTransport = workspaceTransport();
    oldTransport.getAgentWorkspaceFile.mockImplementationOnce(() => pending.promise);
    const newTransport = workspaceTransport();
    const view = render(<AgentWorkspacePane pendingWrite={null} sessionId={SESSION} transport={oldTransport} />);

    await runWorkspaceSearch();
    fireEvent.click(await screen.findByRole("button", { name: "Open search result src/example.ts line 2" }));
    await waitFor(() => expect(oldTransport.getAgentWorkspaceFile).toHaveBeenCalledTimes(1));
    view.rerender(<AgentWorkspacePane
      pendingWrite={null}
      sessionId={replacement === "session" ? "c".repeat(32) : SESSION}
      transport={replacement === "transport" ? newTransport : oldTransport}
    />);

    await waitFor(() => expect((screen.getByRole("textbox", { name: "Workspace file editor" }) as HTMLTextAreaElement).value).toBe(""));
    await act(async () => { pending.resolve(workspaceFile()); await Promise.resolve(); });
    expect(screen.getByRole("textbox", { name: "Workspace file editor" })).toHaveValue("");
    expect(newTransport.getAgentWorkspaceFile).not.toHaveBeenCalled();
  });
});
