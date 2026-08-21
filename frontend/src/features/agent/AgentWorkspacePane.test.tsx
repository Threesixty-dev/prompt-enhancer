import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AgentEvent, AgentWorkspaceFile } from "../../shared/api/contracts";
import { AgentWorkspacePane } from "./AgentWorkspacePane";

const SESSION = "a".repeat(32);
const OTHER_SESSION = "e".repeat(32);
const BASE = "b".repeat(64);
const PROPOSED = "c".repeat(64);
const PREVIEW = "d".repeat(32);

function file(path = "example.ts", content = "export const value = 1;\n", revision = BASE): AgentWorkspaceFile {
  return {
    contract_version: "local-agent-workspace.v1",
    session_id: SESSION,
    path,
    content,
    revision,
    byte_size: content.length,
    line_ending: "lf",
    editable: true,
  };
}

function transport() {
  return {
    getAgentWorkspaceTree: vi.fn(async (sessionId: string, path: string) => ({
      contract_version: "local-agent-workspace.v1" as const,
      session_id: sessionId,
      path,
      entries: [
        { path: "src", name: "src", kind: "directory" as const, byte_size: null, editable_candidate: false },
        { path: "example.ts", name: "example.ts", kind: "file" as const, byte_size: 24, editable_candidate: true },
        { path: "large.log", name: "large.log", kind: "file" as const, byte_size: 300_000, editable_candidate: false },
        { path: "linked", name: "linked", kind: "unavailable" as const, byte_size: null, editable_candidate: false },
      ],
      complete: true,
    })),
    getAgentWorkspaceFile: vi.fn(async () => file()),
    previewAgentWorkspaceEdit: vi.fn(async () => ({
      contract_version: "local-agent-workspace.v1" as const,
      session_id: SESSION,
      preview_id: PREVIEW,
      path: "example.ts",
      expected_revision: BASE,
      proposed_revision: PROPOSED,
      line_ending: "lf" as const,
      diff: "--- a/example.ts\n+++ b/example.ts\n@@ -1 +1 @@\n-1\n+2",
      expires_at: "2026-08-20T22:00:00Z",
    })),
    applyAgentWorkspaceEdit: vi.fn(async () => ({
      contract_version: "local-agent-workspace.v1" as const,
      session_id: SESSION,
      path: "example.ts",
      revision: PROPOSED,
      byte_size: 24,
      applied: true as const,
    })),
  };
}

describe("AgentWorkspacePane", () => {
  it("opens a file, reviews the server diff, and applies only the reviewed draft", async () => {
    const api = transport();
    api.getAgentWorkspaceFile
      .mockResolvedValueOnce(file())
      .mockResolvedValueOnce(file("example.ts", "export const value = 2;\n", PROPOSED));
    const dirty = vi.fn();
    render(<AgentWorkspacePane onDirtyChange={dirty} pendingWrite={null} sessionId={SESSION} transport={api} />);

    expect(await screen.findByText("example.ts")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /example.ts/u }));
    const editor = await screen.findByLabelText("Workspace file editor") as HTMLTextAreaElement;
    expect(editor.value).toContain("value = 1");
    fireEvent.change(editor, { target: { value: "export const value = 2;\n" } });
    await waitFor(() => expect(dirty).toHaveBeenLastCalledWith(true));
    fireEvent.click(screen.getByRole("button", { name: "Review diff" }));
    expect(await screen.findByRole("region", { name: "Manual edit review" })).toBeTruthy();
    expect(screen.getByText(/\+2/u)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Apply reviewed edit" }));
    await waitFor(() => expect(api.applyAgentWorkspaceEdit).toHaveBeenCalledWith(
      SESSION,
      PREVIEW,
      {
        path: "example.ts",
        content: "export const value = 2;\n",
        expected_revision: BASE,
        proposed_revision: PROPOSED,
        line_ending: "lf",
        confirmation: "apply_reviewed_workspace_edit",
      },
    ));
    expect(await screen.findByText(/Applied the reviewed edit/u)).toBeTruthy();
    expect(editor.value).toContain("value = 2");
  });

  it("shows the agent diff without applying it and protects an unsaved manual draft", async () => {
    const api = transport();
    const pending: AgentEvent = {
      seq: 3,
      at: "2026-08-20T20:00:00Z",
      kind: "approval_required",
      text: null,
      reasoning: null,
      stream_id: null,
      stream_phase: null,
      stream_status: null,
      tool: "write_file",
      arguments: { path: "example.ts" },
      call_id: "call-example",
      approval_id: "e".repeat(32),
      ok: null,
      preview: "--- a/example.ts\n+++ b/example.ts\n-agent\n+proposal",
    };
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    try {
      render(<AgentWorkspacePane pendingWrite={pending} sessionId={SESSION} transport={api} />);
      fireEvent.click(await screen.findByRole("button", { name: /example.ts/u }));
      expect(screen.getByRole("button", { name: "large.log — too large to edit (256 KB limit)" })).toBeDisabled();
      expect(screen.getByRole("note")).toHaveTextContent(/linked.*Unavailable — not opened or followed/u);
      const editor = await screen.findByLabelText("Workspace file editor") as HTMLTextAreaElement;
      fireEvent.change(editor, { target: { value: "unsaved\n" } });
      expect(screen.getByRole("region", { name: "Agent proposed diff" })).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: /src/u }));
      expect(confirm).toHaveBeenCalledWith("Discard the unsaved manual edit?");
      expect(api.getAgentWorkspaceTree).toHaveBeenCalledTimes(1);
      expect(editor.value).toBe("unsaved\n");
      expect(api.applyAgentWorkspaceEdit).not.toHaveBeenCalled();
    } finally {
      confirm.mockRestore();
    }
  });

  it("invalidates the apply button when the draft changes after preview", async () => {
    const api = transport();
    render(<AgentWorkspacePane pendingWrite={null} sessionId={SESSION} transport={api} />);
    fireEvent.click(await screen.findByRole("button", { name: /example.ts/u }));
    const editor = await screen.findByLabelText("Workspace file editor") as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: "export const value = 2;\n" } });
    fireEvent.click(screen.getByRole("button", { name: "Review diff" }));
    await screen.findByRole("region", { name: "Manual edit review" });
    fireEvent.change(editor, { target: { value: "export const value = 3;\n" } });
    expect(screen.getByText(/draft changed after this preview/u)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Apply reviewed edit" })).toBeDisabled();
  });

  it("keeps a reviewed preview read-only without native user presence", async () => {
    const api = transport();
    render(
      <AgentWorkspacePane
        pendingWrite={null}
        sessionId={SESSION}
        transport={api}
        userPresenceAvailable={false}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: /example.ts/u }));
    const editor = await screen.findByLabelText("Workspace file editor");
    await waitFor(() => expect(editor).toHaveValue("export const value = 1;\n"));
    fireEvent.change(editor, {
      target: { value: "export const value = 2;\n" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Review diff" }));
    await screen.findByRole("region", { name: "Manual edit review" });

    expect(screen.getByText(/preview is read-only here/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Apply reviewed edit" })).toBeDisabled();
    expect(api.applyAgentWorkspaceEdit).not.toHaveBeenCalled();
  });

  it("drops an in-flight file response when the selected session changes", async () => {
    const api = transport();
    let resolveFile!: (value: AgentWorkspaceFile) => void;
    api.getAgentWorkspaceFile.mockImplementationOnce(() => new Promise((resolve) => {
      resolveFile = resolve;
    }));
    const view = render(
      <AgentWorkspacePane pendingWrite={null} sessionId={SESSION} transport={api} />,
    );
    fireEvent.click(await screen.findByRole("button", { name: /example.ts/u }));

    view.rerender(
      <AgentWorkspacePane pendingWrite={null} sessionId={OTHER_SESSION} transport={api} />,
    );
    resolveFile(file());

    await waitFor(() => expect(api.getAgentWorkspaceTree).toHaveBeenCalledWith(
      OTHER_SESSION,
      ".",
      expect.any(AbortSignal),
    ));
    expect(screen.getByText("No file open")).toBeVisible();
    expect((screen.getByLabelText("Workspace file editor") as HTMLTextAreaElement).value).toBe("");
  });
});
