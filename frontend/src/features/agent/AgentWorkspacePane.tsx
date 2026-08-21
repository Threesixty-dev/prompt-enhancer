import { useEffect, useMemo, useRef, useState } from "react";
import type {
  AgentEvent,
  AgentWorkspaceEditPreview,
  AgentWorkspaceFile,
  AgentWorkspaceTree,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { AGENT_WORKSPACE_MAX_FILE_BYTES } from "../../shared/api/agentWorkspaceContract";
import { TransportError } from "../../shared/api/httpTransport";

type WorkspaceTransport = Pick<
  PromptEnhancerTransport,
  | "getAgentWorkspaceTree"
  | "getAgentWorkspaceFile"
  | "previewAgentWorkspaceEdit"
  | "applyAgentWorkspaceEdit"
>;

const APPLY_CONFIRMATION = "apply_reviewed_workspace_edit" as const;

function parentFolder(path: string): string {
  if (path === ".") return ".";
  const index = path.lastIndexOf("/");
  return index < 0 ? "." : path.slice(0, index);
}

function friendlyError(caught: unknown): string {
  const status = caught instanceof TransportError ? caught.status : null;
  if (status === 404) return "That file or folder is no longer available.";
  if (status === 409) return "The file or preview changed. Reopen the file and review a fresh diff.";
  if (status === 413) return "This edit is too large for one safe review.";
  if (status === 415) return "Only strict UTF-8 text files can be edited here.";
  if (status === 403) return "The native approval was declined, expired, or the path is protected. Nothing was applied.";
  if (status === 503) return "Native user-presence confirmation is unavailable in this app composition. Nothing was applied.";
  if (status === 200) return "The local service returned an invalid workspace response. Nothing was applied.";
  if (status === 422) return "This file cannot be safely edited in the current workspace.";
  return "The local workspace operation did not complete.";
}

function nonEditableReason(byteSize: number | null | undefined): string {
  return byteSize !== null && byteSize !== undefined && byteSize > AGENT_WORKSPACE_MAX_FILE_BYTES
    ? `too large to edit (${AGENT_WORKSPACE_MAX_FILE_BYTES / 1000} KB limit)`
    : "not editable in the bounded editor";
}

export function AgentWorkspacePane({
  sessionId,
  transport,
  pendingWrite,
  onDirtyChange,
  userPresenceAvailable = true,
}: {
  sessionId: string;
  transport: WorkspaceTransport;
  pendingWrite: AgentEvent | null;
  onDirtyChange?: (dirty: boolean) => void;
  userPresenceAvailable?: boolean;
}) {
  const [folder, setFolder] = useState(".");
  const [tree, setTree] = useState<AgentWorkspaceTree | null>(null);
  const [opened, setOpened] = useState<AgentWorkspaceFile | null>(null);
  const [draft, setDraft] = useState("");
  const [preview, setPreview] = useState<AgentWorkspaceEditPreview | null>(null);
  const [previewDraft, setPreviewDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [notice, setNotice] = useState("");
  const activeSession = useRef(sessionId);
  const operationVersion = useRef(0);

  if (activeSession.current !== sessionId) {
    activeSession.current = sessionId;
    operationVersion.current += 1;
  }

  const dirty = opened !== null && draft !== opened.content;
  const previewIsCurrent = preview !== null && previewDraft === draft;
  const pendingPath = pendingWrite?.tool === "write_file" && typeof pendingWrite.arguments?.path === "string"
    ? pendingWrite.arguments.path
    : null;

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => {
    return () => { operationVersion.current += 1; };
  }, [sessionId]);

  useEffect(() => {
    setFolder(".");
    setTree(null);
    setOpened(null);
    setDraft("");
    setPreview(null);
    setPreviewDraft("");
    setMessage("");
    setNotice("");
  }, [sessionId]);

  useEffect(() => {
    const controller = new AbortController();
    const requestedSession = sessionId;
    setLoading(true);
    transport.getAgentWorkspaceTree(sessionId, folder, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted && activeSession.current === requestedSession) {
          setTree(value);
          setMessage("");
        }
      })
      .catch((caught) => {
        if (!controller.signal.aborted && activeSession.current === requestedSession) {
          setTree(null);
          setMessage(friendlyError(caught));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted && activeSession.current === requestedSession) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [folder, sessionId, transport]);

  function mayDiscardDraft(): boolean {
    return !dirty || window.confirm("Discard the unsaved manual edit?");
  }

  async function openFile(path: string) {
    if (!mayDiscardDraft()) return;
    const requestedSession = sessionId;
    const version = ++operationVersion.current;
    setLoading(true);
    setMessage("");
    setNotice("");
    try {
      const file = await transport.getAgentWorkspaceFile(sessionId, path);
      if (activeSession.current !== requestedSession || operationVersion.current !== version) return;
      setOpened(file);
      setDraft(file.content);
      setPreview(null);
      setPreviewDraft("");
    } catch (caught) {
      if (activeSession.current !== requestedSession || operationVersion.current !== version) return;
      setMessage(friendlyError(caught));
    } finally {
      if (activeSession.current === requestedSession && operationVersion.current === version) {
        setLoading(false);
      }
    }
  }

  function openFolder(path: string) {
    if (!mayDiscardDraft()) return;
    operationVersion.current += 1;
    setOpened(null);
    setDraft("");
    setPreview(null);
    setPreviewDraft("");
    setFolder(path);
  }

  async function createPreview() {
    if (!opened || !dirty || loading) return;
    const requestedSession = sessionId;
    const version = ++operationVersion.current;
    setLoading(true);
    setMessage("");
    setNotice("");
    try {
      const value = await transport.previewAgentWorkspaceEdit(sessionId, {
        path: opened.path,
        content: draft,
        expected_revision: opened.revision,
        line_ending: opened.line_ending,
      });
      if (activeSession.current !== requestedSession || operationVersion.current !== version) return;
      setPreview(value);
      setPreviewDraft(draft);
    } catch (caught) {
      if (activeSession.current !== requestedSession || operationVersion.current !== version) return;
      setPreview(null);
      setPreviewDraft("");
      setMessage(friendlyError(caught));
    } finally {
      if (activeSession.current === requestedSession && operationVersion.current === version) {
        setLoading(false);
      }
    }
  }

  async function applyPreview() {
    if (!opened || !preview || !previewIsCurrent || loading || !userPresenceAvailable) return;
    const requestedSession = sessionId;
    const version = ++operationVersion.current;
    setLoading(true);
    setMessage("");
    setNotice("");
    try {
      await transport.applyAgentWorkspaceEdit(sessionId, preview.preview_id, {
        path: preview.path,
        content: draft,
        expected_revision: preview.expected_revision,
        proposed_revision: preview.proposed_revision,
        line_ending: preview.line_ending,
        confirmation: APPLY_CONFIRMATION,
      });
      if (activeSession.current !== requestedSession || operationVersion.current !== version) return;
      const refreshed = await transport.getAgentWorkspaceFile(sessionId, preview.path);
      if (activeSession.current !== requestedSession || operationVersion.current !== version) return;
      setOpened(refreshed);
      setDraft(refreshed.content);
      setPreview(null);
      setPreviewDraft("");
      setNotice("Applied the reviewed edit. The server rechecked the file revision before writing.");
    } catch (caught) {
      if (activeSession.current !== requestedSession || operationVersion.current !== version) return;
      setPreview(null);
      setPreviewDraft("");
      setMessage(friendlyError(caught));
    } finally {
      if (activeSession.current === requestedSession && operationVersion.current === version) {
        setLoading(false);
      }
    }
  }

  const folderLabel = folder === "." ? "Workspace root" : folder;
  const agentDiffForOpened = pendingPath && opened?.path === pendingPath ? pendingWrite?.preview : null;
  const summary = useMemo(() => {
    if (!opened) return "Choose an editable UTF-8 file.";
    return `${opened.byte_size.toLocaleString()} bytes · ${opened.line_ending.toUpperCase()} · revision ${opened.revision.slice(0, 8)}`;
  }, [opened]);

  return (
    <section aria-labelledby="agent-workspace-title" className="agent-workspace">
      <header className="agent-workspace__head">
        <div>
          <p className="eyebrow">Workspace · manual editor</p>
          <h2 id="agent-workspace-title">Files and reviewed changes</h2>
        </div>
        <button
          className="button button--ghost"
          disabled={folder === "." || loading}
          onClick={() => openFolder(parentFolder(folder))}
          type="button"
        >
          Up
        </button>
      </header>
      <p className="agent-workspace__truth">
        Your manual edits require native user-presence confirmation and do not depend on whether the model may write. Existing UTF-8 text files up to {AGENT_WORKSPACE_MAX_FILE_BYTES / 1000} KB only in this first version.
      </p>

      <div className="agent-workspace__tree" aria-busy={loading} aria-label={folderLabel}>
        <div className="agent-workspace__path"><code>{folderLabel}</code></div>
        {tree?.entries.length === 0 && <p className="agent__note">This folder is empty.</p>}
        {tree && (
          <ul>
            {tree.entries.map((entry) => (
              <li key={entry.path} data-kind={entry.kind}>
                {entry.kind === "directory" ? (
                  <button onClick={() => openFolder(entry.path)} type="button"><span aria-hidden="true">📁</span><span>{entry.name}</span></button>
                ) : entry.kind === "file" ? (
                  <button
                    aria-label={entry.editable_candidate ? undefined : `${entry.name} — ${nonEditableReason(entry.byte_size)}`}
                    disabled={!entry.editable_candidate}
                    onClick={() => void openFile(entry.path)}
                    type="button"
                  >
                    <span aria-hidden="true">📄</span><span>{entry.name}</span>
                    {!entry.editable_candidate && <small>{nonEditableReason(entry.byte_size)}</small>}
                  </button>
                ) : (
                  <span role="note"><span aria-hidden="true">⛔</span><span>{entry.name}</span><small>Unavailable — not opened or followed</small></span>
                )}
              </li>
            ))}
          </ul>
        )}
        {tree && !tree.complete && <p className="agent__note" role="status">This bounded folder view is incomplete; at most the first 400 representable entries are shown.</p>}
      </div>

      <div className="agent-workspace__editor">
        <div className="agent-workspace__editor-head">
          <strong>{opened?.path ?? "No file open"}</strong>
          <small>{summary}</small>
        </div>
        <textarea
          aria-label="Workspace file editor"
          disabled={!opened || loading}
          onChange={(event) => {
            setDraft(event.currentTarget.value);
            setNotice("");
          }}
          placeholder="Choose a file from the tree"
          rows={16}
          spellCheck={false}
          value={draft}
        />
        <div className="agent-workspace__actions">
          <button className="button button--primary" disabled={!dirty || loading} onClick={() => void createPreview()} type="button">Review diff</button>
          <button className="button button--ghost" disabled={!dirty || loading} onClick={() => { if (opened && mayDiscardDraft()) { setDraft(opened.content); setPreview(null); setPreviewDraft(""); } }} type="button">Discard draft</button>
        </div>
      </div>

      {agentDiffForOpened && (
        <section aria-label="Agent proposed diff" className="agent-workspace__agent-diff">
          <h3>Agent proposal for this file</h3>
          <pre>{agentDiffForOpened}</pre>
          <p>The agent still needs approval in the conversation. This view does not apply it.</p>
        </section>
      )}

      {preview && (
        <section aria-label="Manual edit review" className="agent-workspace__review">
          <h3>Review manual edit</h3>
          <pre>{preview.diff}</pre>
          {!previewIsCurrent && <p role="status">The draft changed after this preview. Review a fresh diff before applying.</p>}
          {!userPresenceAvailable && <p role="status">This preview is read-only here because native user-presence confirmation is unavailable.</p>}
          <button className="button button--primary" disabled={!previewIsCurrent || loading || !userPresenceAvailable} onClick={() => void applyPreview()} type="button">Apply reviewed edit</button>
        </section>
      )}

      {message && <p className="agent__error" role="alert">{message}</p>}
      {notice && <p className="agent-workspace__notice" role="status">{notice}</p>}
    </section>
  );
}
