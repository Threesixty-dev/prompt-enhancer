import { createRef } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AgentWorkspaceEditor, type AgentWorkspaceEditorLineRequest } from "./AgentWorkspaceEditor";

const SESSION = "a".repeat(32);
const PATH = "src/example.ts";
const REVISION = "b".repeat(64);
const TRANSPORT = {};
const IDENTITY = { sessionId: SESSION, path: PATH, revision: REVISION, transport: TRANSPORT };

function renderEditor({
  value = "one\none\none\n",
  disabled = false,
  readOnly = false,
  identity = IDENTITY,
  lineRequest = null,
  onHandled = vi.fn<(token: number) => void>(),
  onParentKeyDown,
}: {
  value?: string;
  disabled?: boolean;
  readOnly?: boolean;
  identity?: typeof IDENTITY | null;
  lineRequest?: AgentWorkspaceEditorLineRequest | null;
  onHandled?: (token: number) => void;
  onParentKeyDown?: () => void;
} = {}) {
  const textareaRef = createRef<HTMLTextAreaElement>();
  const onChange = vi.fn();
  const editorElement = <AgentWorkspaceEditor
    disabled={disabled}
    identity={identity}
    lineRequest={lineRequest}
    onChange={onChange}
    onLineRequestHandled={onHandled}
    readOnly={readOnly}
    textareaRef={textareaRef}
    value={value}
  />;
  const view = render(onParentKeyDown ? <div onKeyDown={onParentKeyDown}>
    {editorElement}
  </div> : editorElement);
  const editor = screen.getByRole("textbox", { name: "Workspace file editor" }) as HTMLTextAreaElement;
  return { editor, onChange, onHandled, textareaRef, view };
}

function openTools() {
  fireEvent.click(screen.getByText("Find & go to line"));
}

describe("AgentWorkspaceEditor navigation", () => {
  it("takes an initial Find previous to the last literal match, not the penultimate one", async () => {
    const { editor } = renderEditor();
    openTools();
    fireEvent.change(screen.getByRole("searchbox", { name: "Find in open file" }), { target: { value: "one" } });
    fireEvent.click(screen.getByRole("button", { name: "Find previous" }));

    await waitFor(() => {
      expect(editor.selectionStart).toBe(8);
      expect(editor.selectionEnd).toBe(11);
      expect(screen.getByRole("status")).toHaveTextContent("Match 3 of 3 selected.");
    });
  });

  it("supports Enter and Shift+Enter in find controls without moving focus outside the editor tools", async () => {
    const { editor } = renderEditor();
    openTools();
    const find = screen.getByRole("searchbox", { name: "Find in open file" });
    fireEvent.change(find, { target: { value: "one" } });
    fireEvent.keyDown(find, { key: "Enter" });
    await waitFor(() => expect(editor.selectionStart).toBe(0));
    fireEvent.keyDown(find, { key: "Enter", shiftKey: true });
    await waitFor(() => {
      expect(editor.selectionStart).toBe(8);
      expect(screen.getByRole("status")).toHaveTextContent("Match 3 of 3 selected.");
    });
  });

  it("clears an old find selection claim when the draft changes", async () => {
    const { view } = renderEditor({ value: "one\ntwo\n" });
    openTools();
    fireEvent.change(screen.getByRole("searchbox", { name: "Find in open file" }), { target: { value: "one" } });
    fireEvent.click(screen.getByRole("button", { name: "Find next" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Match 1 of 1 selected.");

    view.rerender(<AgentWorkspaceEditor
      disabled={false}
      identity={IDENTITY}
      lineRequest={null}
      onChange={vi.fn()}
      onLineRequestHandled={vi.fn()}
      readOnly={false}
      textareaRef={createRef<HTMLTextAreaElement>()}
      value="two\n"
    />);
    expect(screen.getByRole("status")).not.toHaveTextContent("Match 1 of 1 selected.");
  });

  it("resets tools on a different editor identity without a queued focus steal", async () => {
    const { editor, textareaRef, view } = renderEditor();
    editor.focus();
    fireEvent.keyDown(editor, { key: "f", ctrlKey: true });
    const nextIdentity = { ...IDENTITY, path: "src/other.ts", revision: "c".repeat(64) };
    view.rerender(<AgentWorkspaceEditor
      disabled={false}
      identity={nextIdentity}
      lineRequest={null}
      onChange={vi.fn()}
      onLineRequestHandled={vi.fn()}
      readOnly={false}
      textareaRef={textareaRef}
      value="other\n"
    />);

    await new Promise((resolve) => requestAnimationFrame(resolve));
    expect(screen.getByRole("textbox", { name: "Workspace file editor" })).toHaveFocus();
    const tools = screen.getByText("Find & go to line").closest("details");
    expect(tools).not.toHaveAttribute("open");
    expect(screen.getByRole("searchbox", { name: "Find in open file", hidden: true })).not.toBeVisible();
  });

  it("closes local tools on Escape after Find next while retaining editor focus", async () => {
    const onParentKeyDown = vi.fn();
    const { editor } = renderEditor({ onParentKeyDown });
    openTools();
    fireEvent.change(screen.getByRole("searchbox", { name: "Find in open file" }), { target: { value: "one" } });
    fireEvent.click(screen.getByRole("button", { name: "Find next" }));
    await waitFor(() => expect(editor).toHaveFocus());
    fireEvent.keyDown(editor, { key: "Escape" });

    const tools = screen.getByText("Find & go to line").closest("details");
    expect(tools).not.toHaveAttribute("open");
    expect(screen.getByRole("searchbox", { name: "Find in open file", hidden: true })).not.toBeVisible();
    expect(editor).toHaveFocus();
    expect(onParentKeyDown).not.toHaveBeenCalled();
  });

  it("disables local navigation only when the editor is disabled, not when it is read-only", async () => {
    const { view } = renderEditor({ disabled: true });
    openTools();
    expect(screen.getByRole("searchbox", { name: "Find in open file" })).toBeDisabled();
    expect(screen.getByRole("spinbutton", { name: "Go to line" })).toBeDisabled();
    view.unmount();

    const { editor } = renderEditor({ readOnly: true });
    openTools();
    const find = screen.getByRole("searchbox", { name: "Find in open file" });
    expect(find).toBeEnabled();
    fireEvent.change(find, { target: { value: "one" } });
    fireEvent.click(screen.getByRole("button", { name: "Find next" }));
    await waitFor(() => expect(editor.selectionStart).toBe(0));
  });

  it("ignores a duplicate line request token but honors a new token for the same line", async () => {
    const request: AgentWorkspaceEditorLineRequest = { token: 7, line: 2, owner: IDENTITY };
    const onHandled = vi.fn();
    const { editor, view } = renderEditor({ lineRequest: request, onHandled });
    await waitFor(() => expect(onHandled).toHaveBeenCalledExactlyOnceWith(7));
    expect(editor.selectionStart).toBe(4);
    expect(editor.selectionEnd).toBe(7);

    view.rerender(<AgentWorkspaceEditor
      disabled={false}
      identity={IDENTITY}
      lineRequest={{ ...request }}
      onChange={vi.fn()}
      onLineRequestHandled={onHandled}
      readOnly={false}
      textareaRef={createRef<HTMLTextAreaElement>()}
      value={"one\none\none\n"}
    />);
    expect(onHandled).toHaveBeenCalledTimes(1);

    view.rerender(<AgentWorkspaceEditor
      disabled={false}
      identity={IDENTITY}
      lineRequest={{ ...request, token: 8 }}
      onChange={vi.fn()}
      onLineRequestHandled={onHandled}
      readOnly={false}
      textareaRef={createRef<HTMLTextAreaElement>()}
      value={"one\none\none\n"}
    />);
    await waitFor(() => expect(onHandled).toHaveBeenCalledTimes(2));
    expect(onHandled).toHaveBeenLastCalledWith(8);
    expect(editor.selectionStart).toBe(4);
    expect(editor.selectionEnd).toBe(7);
  });
});
