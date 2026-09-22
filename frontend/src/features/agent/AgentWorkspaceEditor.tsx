import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, RefObject } from "react";
import { findLiteralMatches, lineColumnAt, lineRangeAt } from "./agentEditorNavigation";
import "./AgentWorkspaceEditor.css";

export type AgentWorkspaceEditorLineRequest = {
  token: number;
  line: number;
  owner: {
    sessionId: string;
    path: string;
    revision: string;
    transport: unknown;
  };
};

type EditorIdentity = AgentWorkspaceEditorLineRequest["owner"];

function sameEditorIdentity(left: EditorIdentity | null, right: EditorIdentity | null): boolean {
  return left === right || Boolean(
    left
    && right
    && left.sessionId === right.sessionId
    && left.path === right.path
    && left.revision === right.revision
    && left.transport === right.transport,
  );
}

function measureTextareaText(text: string, style: CSSStyleDeclaration): number | null {
  if (!document.body) return null;
  if (text === "") return 0;
  const probe = document.createElement("span");
  probe.setAttribute("aria-hidden", "true");
  Object.assign(probe.style, {
    position: "fixed",
    visibility: "hidden",
    pointerEvents: "none",
    whiteSpace: "pre",
    fontFamily: style.fontFamily,
    fontSize: style.fontSize,
    fontStyle: style.fontStyle,
    fontVariant: style.fontVariant,
    fontWeight: style.fontWeight,
    letterSpacing: style.letterSpacing,
    tabSize: style.tabSize,
  });
  probe.textContent = text;
  document.body.appendChild(probe);
  try {
    const width = probe.getBoundingClientRect().width;
    return Number.isFinite(width) && width > 0 ? width : null;
  } finally {
    probe.remove();
  }
}

export function AgentWorkspaceEditor({
  value,
  disabled,
  readOnly,
  onChange,
  textareaRef,
  identity,
  lineRequest,
  onLineRequestHandled,
}: {
  value: string;
  disabled: boolean;
  readOnly: boolean;
  onChange: (value: string) => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  identity: EditorIdentity | null;
  lineRequest: AgentWorkspaceEditorLineRequest | null;
  onLineRequestHandled: (token: number) => void;
}) {
  const findInputId = useId();
  const lineInputId = useId();
  const findInputRef = useRef<HTMLInputElement | null>(null);
  const lineInputRef = useRef<HTMLInputElement | null>(null);
  const handledRequest = useRef<number | null>(null);
  const focusFrame = useRef<number | null>(null);
  const focusGeneration = useRef(0);
  const latestIdentity = useRef<EditorIdentity | null>(identity);
  if (
    latestIdentity.current?.sessionId !== identity?.sessionId
    || latestIdentity.current?.path !== identity?.path
    || latestIdentity.current?.revision !== identity?.revision
    || latestIdentity.current?.transport !== identity?.transport
  ) {
    latestIdentity.current = identity;
    focusGeneration.current += 1;
    if (focusFrame.current !== null) cancelAnimationFrame(focusFrame.current);
    focusFrame.current = null;
  }
  const [toolsOpen, setToolsOpen] = useState(false);
  const [findQuery, setFindQuery] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [selectedMatch, setSelectedMatch] = useState(-1);
  const [lineInput, setLineInput] = useState("");
  const [navigationStatus, setNavigationStatus] = useState("");
  const [position, setPosition] = useState(() => lineColumnAt(value, 0));
  const [navigationOwner, setNavigationOwner] = useState<EditorIdentity | null>(identity);
  const matches = useMemo(
    () => findLiteralMatches(value, findQuery, matchCase),
    [findQuery, matchCase, value],
  );
  const editorEnabled = identity !== null && !disabled;
  const navigationStateCurrent = sameEditorIdentity(navigationOwner, identity);
  const visiblePosition = navigationStateCurrent ? position : lineColumnAt(value, 0);

  const updatePosition = useCallback((offset: number) => {
    setPosition(lineColumnAt(value, offset));
  }, [value]);

  const scheduleFocus = useCallback((target: "editor" | "find" | "line") => {
    if (focusFrame.current !== null) cancelAnimationFrame(focusFrame.current);
    const generation = focusGeneration.current;
    focusFrame.current = requestAnimationFrame(() => {
      focusFrame.current = null;
      if (generation !== focusGeneration.current) return;
      if (target === "editor") textareaRef.current?.focus({ preventScroll: true });
      else if (target === "find") findInputRef.current?.focus();
      else lineInputRef.current?.focus();
    });
  }, [textareaRef]);

  const restoreEditorFocus = useCallback(() => {
    scheduleFocus("editor");
  }, [scheduleFocus]);

  const selectRange = useCallback((start: number, end: number) => {
    const editor = textareaRef.current;
    if (!editor) return;
    editor.focus({ preventScroll: true });
    // Applying the selection after focus lets the native textarea reveal an
    // off-screen horizontal match; the explicit vertical adjustment follows.
    editor.setSelectionRange(start, end);
    const selected = lineColumnAt(value, start);
    const style = getComputedStyle(editor);
    const rawLineHeight = Number.parseFloat(style.lineHeight);
    const fontSize = Number.parseFloat(style.fontSize);
    const lineHeight = Number.isFinite(rawLineHeight) && rawLineHeight > 0
      ? rawLineHeight < 4 && Number.isFinite(fontSize) ? rawLineHeight * fontSize : rawLineHeight
      : Number.isFinite(fontSize) ? fontSize * 1.5 : 18;
    // setSelectionRange does not consistently scroll a textarea vertically.
    editor.scrollTop = Math.max(0, (selected.line - 3) * lineHeight);
    const currentLineRange = lineRangeAt(value, selected.line);
    const lineStart = currentLineRange?.start ?? 0;
    const lineEnd = value.indexOf("\n", lineStart);
    const currentLine = value.slice(lineStart, lineEnd < 0 ? value.length : lineEnd);
    if (currentLine && editor.scrollWidth > editor.clientWidth) {
      // This measures the current line, not textarea.scrollWidth (which is
      // based on the longest line and can be unrelated to this selection).
      const selectionPrefix = measureTextareaText(value.slice(lineStart, start), style);
      const selectionEnd = measureTextareaText(value.slice(lineStart, end), style);
      if (selectionPrefix !== null && selectionEnd !== null) {
        const selectionLeft = selectionPrefix;
        const selectionRight = Math.max(selectionLeft, selectionEnd);
        const selectionWidth = selectionRight - selectionLeft;
        const inset = Math.min(16, Math.max(4, selectionWidth / 2));
        if (selectionWidth >= editor.clientWidth) editor.scrollLeft = Math.max(0, selectionLeft - inset);
        else if (selectionLeft < editor.scrollLeft) editor.scrollLeft = Math.max(0, selectionLeft - inset);
        else if (selectionRight > editor.scrollLeft + editor.clientWidth) {
          editor.scrollLeft = Math.max(0, selectionRight - editor.clientWidth + inset);
        }
      }
    }
    updatePosition(start);
  }, [textareaRef, updatePosition, value]);

  const selectLine = useCallback((line: number, source: "go" | "search"): boolean => {
    const range = lineRangeAt(value, line);
    if (!range) {
      const count = lineColumnAt(value, 0).lineCount;
      setNavigationStatus(source === "search"
        ? `Recorded search position line ${line} is unavailable; this file has ${count} lines.`
        : `Enter a whole line number from 1 to ${count}.`);
      return false;
    }
    selectRange(range.start, range.end);
    setNavigationStatus(source === "search"
      ? `Recorded search position line ${line} selected; match text was not rechecked.`
      : `Line ${line} selected.`);
    return true;
  }, [selectRange, value]);

  const openTools = useCallback((target: "find" | "line") => {
    setToolsOpen(true);
    scheduleFocus(target);
  }, [scheduleFocus]);

  const closeTools = useCallback(() => {
    setToolsOpen(false);
    restoreEditorFocus();
  }, [restoreEditorFocus]);

  const selectMatch = useCallback((nextIndex: number) => {
    if (!findQuery || matches.length === 0) {
      setSelectedMatch(-1);
      setNavigationStatus(findQuery ? "No literal matches in the open file." : "Enter text to find in the open file.");
      return;
    }
    const bounded = ((nextIndex % matches.length) + matches.length) % matches.length;
    selectRange(matches[bounded], matches[bounded] + findQuery.length);
    setSelectedMatch(bounded);
    setNavigationStatus(`Match ${bounded + 1} of ${matches.length} selected.`);
  }, [findQuery, matches, selectRange]);

  const selectAdjacentMatch = useCallback((direction: -1 | 1) => {
    const next = selectedMatch < 0
      ? direction < 0 ? matches.length - 1 : 0
      : selectedMatch + direction;
    selectMatch(next);
  }, [matches.length, selectMatch, selectedMatch]);

  function handleGoToLine(): void {
    const requested = Number(lineInput);
    if (!Number.isSafeInteger(requested) || requested < 1) {
      const count = lineColumnAt(value, 0).lineCount;
      setNavigationStatus(`Enter a whole line number from 1 to ${count}.`);
      return;
    }
    selectLine(requested, "go");
  }

  function handleFindKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
    if (event.key !== "Enter") return;
    event.preventDefault();
    selectAdjacentMatch(event.shiftKey ? -1 : 1);
  }

  function handleEditorKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.altKey || (!event.ctrlKey && !event.metaKey)) return;
    const key = event.key.toLocaleLowerCase();
    if (key === "f") {
      event.preventDefault();
      openTools("find");
    } else if (key === "g") {
      event.preventDefault();
      openTools("line");
    }
  }

  function handleNavigationKeyDown(event: KeyboardEvent<HTMLElement>): void {
    if (event.key !== "Escape" || !toolsOpen) return;
    event.preventDefault();
    event.stopPropagation();
    closeTools();
  }

  useEffect(() => {
    setToolsOpen(false);
    setFindQuery("");
    setMatchCase(false);
    setSelectedMatch(-1);
    setLineInput("");
    setNavigationStatus("");
    setPosition(lineColumnAt(value, 0));
    setNavigationOwner(identity);
    handledRequest.current = null;
  }, [identity?.path, identity?.revision, identity?.sessionId, identity?.transport]);

  useEffect(() => {
    setSelectedMatch(-1);
    setNavigationStatus("");
    setPosition(lineColumnAt(value, textareaRef.current?.selectionStart ?? 0));
  }, [textareaRef, value]);

  useEffect(() => () => {
    focusGeneration.current += 1;
    if (focusFrame.current !== null) cancelAnimationFrame(focusFrame.current);
  }, []);

  useEffect(() => {
    if (!lineRequest || handledRequest.current === lineRequest.token) return;
    if (
      identity === null
      || identity.sessionId !== lineRequest.owner.sessionId
      || identity.path !== lineRequest.owner.path
      || identity.revision !== lineRequest.owner.revision
      || identity.transport !== lineRequest.owner.transport
    ) return;
    handledRequest.current = lineRequest.token;
    selectLine(lineRequest.line, "search");
    onLineRequestHandled(lineRequest.token);
  }, [identity, lineRequest, onLineRequestHandled, selectLine]);

  return <div className="agent-workspace-editor" onKeyDown={handleNavigationKeyDown}>
    <details
      className="agent-workspace-editor__tools"
      onToggle={(event) => setToolsOpen((event.currentTarget as HTMLDetailsElement).open)}
      open={navigationStateCurrent && toolsOpen}
    >
      <summary>Find &amp; go to line</summary>
      <div className="agent-workspace-editor__tools-body">
        <label htmlFor={findInputId}>
          <span>Find in open file</span>
          <input
            aria-label="Find in open file"
            disabled={!editorEnabled}
            id={findInputId}
            maxLength={1024}
            onChange={(event) => { setFindQuery(event.currentTarget.value); setSelectedMatch(-1); setNavigationStatus(""); }}
            onKeyDown={handleFindKeyDown}
            ref={findInputRef}
            type="search"
            value={navigationStateCurrent ? findQuery : ""}
          />
        </label>
        <div className="agent-workspace-editor__find-actions">
          <button className="button button--ghost" disabled={!editorEnabled} onClick={() => selectAdjacentMatch(-1)} type="button">Find previous</button>
          <button className="button button--ghost" disabled={!editorEnabled} onClick={() => selectAdjacentMatch(1)} type="button">Find next</button>
        </div>
        <div className="agent-workspace-editor__goto">
          <label htmlFor={lineInputId}>
            <span>Go to line</span>
            <input
              aria-label="Go to line"
              disabled={!editorEnabled}
              id={lineInputId}
              inputMode="numeric"
              min={1}
              onChange={(event) => setLineInput(event.currentTarget.value)}
              onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); handleGoToLine(); } }}
              ref={lineInputRef}
              step={1}
              type="number"
              value={navigationStateCurrent ? lineInput : ""}
            />
          </label>
          <button className="button button--ghost" disabled={!editorEnabled} onClick={handleGoToLine} type="button">Go to line</button>
        </div>
        <label className="agent-workspace-editor__case">
          <input
            aria-label="Match case"
            checked={navigationStateCurrent && matchCase}
            disabled={!editorEnabled}
            onChange={(event) => { setMatchCase(event.currentTarget.checked); setSelectedMatch(-1); setNavigationStatus(""); }}
            type="checkbox"
          />
          <span>Match case</span>
        </label>
      </div>
    </details>
    <textarea
      ref={textareaRef}
      aria-label="Workspace file editor"
      disabled={disabled}
      onChange={(event) => onChange(event.currentTarget.value)}
      onKeyDown={handleEditorKeyDown}
      onSelect={(event) => updatePosition(event.currentTarget.selectionStart ?? 0)}
      placeholder="Choose a file from the tree"
      readOnly={readOnly}
      rows={16}
      spellCheck={false}
      value={value}
    />
    {identity ? <>
      <p
        aria-label={`Cursor position: line ${visiblePosition.line}, column ${visiblePosition.column}; ${visiblePosition.lineCount} lines`}
        className="agent-workspace-editor__status agent-workspace-editor__position"
        title="Columns use native textarea UTF-16 positions."
      >Line {visiblePosition.line}, column {visiblePosition.column} · {visiblePosition.lineCount} lines</p>
      <p aria-live="polite" className="agent-workspace-editor__status" role="status">{navigationStateCurrent ? navigationStatus : ""}</p>
    </> : <p className="agent-workspace-editor__status">Choose a file to use find or line navigation.</p>}
  </div>;
}
