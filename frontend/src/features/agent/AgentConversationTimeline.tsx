import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import type {
  AgentCatalogSession,
  AgentEvent,
  AgentMessageAttachment,
} from "../../shared/api/contracts";
import { AgentCopyButton } from "./AgentCopyButton";
import { AgentMessageContent } from "./AgentMessageContent";
import { AgentMcpToolActivity, collectAgentMcpCalls } from "./AgentMcpToolActivity";
import { AgentTurnDetails, type AgentTurnRevisionMode } from "./AgentTurnDetails";
import {
  isExternalWriteProposal,
  isExternalWriteTransactionProposal,
  summarizeArguments,
  TOOL_LABELS,
} from "./agentEventPresentation";

const TRANSCRIPT_EVENT_BATCH = 200;

export type TurnRevisionBusy = { mode: AgentTurnRevisionMode; turnId: string };

export function RetainedHistoryView({
  artifactsPanel,
  events,
  focusTurnRequest,
  exportBusy,
  forkBusy,
  forkSupported,
  message,
  onClear,
  onExport,
  onFork,
  onReviseTurn,
  onNewChat,
  onResume,
  resumeBusy,
  session,
  state,
  turnRevisionBusy,
}: {
  artifactsPanel: ReactNode;
  events: AgentEvent[];
  focusTurnRequest: { requestId: number; turnId: string } | null;
  exportBusy: boolean;
  forkBusy: boolean;
  forkSupported: boolean;
  message: string;
  onClear: () => void;
  onExport: () => void;
  onFork: (throughEventSeq?: number) => void;
  onReviseTurn?: (turnId: string, mode: AgentTurnRevisionMode) => void;
  onNewChat: (trigger: HTMLButtonElement) => void;
  onResume: () => void;
  resumeBusy: boolean;
  session: AgentCatalogSession;
  state: "idle" | "loading" | "ready" | "error";
  turnRevisionBusy: TurnRevisionBusy | null;
}) {
  const [branchPoint, setBranchPoint] = useState("latest");
  useEffect(() => setBranchPoint("latest"), [session.session_id]);
  let lastUser = 0;
  let lastDone = 0;
  for (const event of events) {
    if (event.kind === "user") lastUser = event.seq;
    if (event.kind === "done") lastDone = event.seq;
  }
  const interrupted = lastUser > lastDone;
  const donePoints = events.filter((event) => event.kind === "done");
  return (
    <article className="agent__retained" aria-labelledby="agent-retained-title">
      <header className="agent__retained-head">
        <div>
          <span className="agent__history-stub-badge">Saved locally · {session.turn_count} {session.turn_count === 1 ? "turn" : "turns"}</span>
          {session.lineage && (
            <span className="agent__history-stub-badge">
              Branch · {session.lineage.copied_turn_count} copied {session.lineage.copied_turn_count === 1 ? "turn" : "turns"}
            </span>
          )}
          <h2 id="agent-retained-title">{session.title}</h2>
          <p><code>{session.workspace}</code> · {session.model_alias ?? "No saved model"}</p>
        </div>
        <div className="agent__history-stub-actions">
          <button className="button button--primary" disabled={state !== "ready" || resumeBusy || Boolean(session.archived_at)} onClick={onResume} type="button">
            {resumeBusy ? "Resuming…" : session.archived_at ? "Restore chat before resuming" : "Resume chat"}
          </button>
          <button className="button button--ghost" disabled={state !== "ready" || exportBusy} onClick={onExport} type="button">
            {exportBusy ? "Exporting…" : "Export JSON"}
          </button>
        </div>
      </header>
      <p className="agent__retained-truth">
        Visible messages and bounded receipts were retained locally. Approval IDs, approval decisions, raw tool arguments/output, and reusable mutation authority were not restored.
      </p>
      {forkSupported && (
        <div className="agent__branch-controls">
          <label>
            <span>Branch point</span>
            <select
              aria-label="Branch point"
              disabled={state !== "ready" || forkBusy}
              onChange={(event) => setBranchPoint(event.currentTarget.value)}
              value={branchPoint}
            >
              <option value="latest">Latest completed turn</option>
              <option value="0">Before the first turn</option>
              {donePoints.map((event, index) => (
                <option key={event.seq} value={String(event.seq)}>
                  After turn {index + 1}
                </option>
              ))}
            </select>
          </label>
          <button
            className="button button--ghost"
            disabled={state !== "ready" || forkBusy || Boolean(session.archived_at)}
            onClick={() => onFork(branchPoint === "latest" ? undefined : Number(branchPoint))}
            type="button"
          >{forkBusy ? "Creating branch…" : "Fork chat"}</button>
          <small>Creates an inactive local branch with retained history only. Protected authority is never copied.</small>
        </div>
      )}
      {interrupted && state === "ready" && (
        <p className="agent__retained-warning" role="status">The last turn was interrupted before a settled receipt. No completion status was invented.</p>
      )}
      {state === "loading" ? (
        <p className="agent__status" role="status">Loading retained conversation…</p>
      ) : state === "error" ? (
        <p className="agent__error" role="alert">{message || "Retained history is unavailable."}</p>
      ) : state === "ready" ? (
        <div className="agent__log agent__log--retained" role="log" aria-live="off">
          <header className="agent__log-head">
            <span><small>Retained conversation</small><strong>Messages and settled activity</strong></span>
            <span className="agent__activity-badge" data-tone="idle">Saved</span>
          </header>
          <div aria-label="Retained agent activity" className="agent__timeline" role="region">
            {events.length === 0 && <p className="agent__status">No conversation turn was started in this chat.</p>}
            <TranscriptEventRows
              key={session.session_id}
              events={events}
              fileActionsDisabled
              focusTurnRequest={focusTurnRequest}
              interrupted={interrupted}
              onOpenFile={() => undefined}
              onReviseTurn={onReviseTurn}
              reasoningEnabled
              revisionActionsDisabled={state !== "ready" || forkBusy || Boolean(session.archived_at) || turnRevisionBusy !== null}
              turnRevisionBusy={turnRevisionBusy}
            />
            {artifactsPanel}
          </div>
        </div>
      ) : null}
      {message && state !== "error" && <p className="agent__status" role="status">{message}</p>}
      <footer className="agent__history-stub-actions">
        <button className="button button--ghost" onClick={(event) => onNewChat(event.currentTarget)} type="button">New chat in this project</button>
        <button className="button button--ghost" onClick={onClear} type="button">Clear selection</button>
      </footer>
    </article>
  );
}

export type LiveStreamView = { firstSeq: number; content: string; reasoning: string };

function transcriptStartIndex(
  events: readonly AgentEvent[],
  windowEnd: number,
): number {
  const cutoff = Math.max(0, windowEnd - TRANSCRIPT_EVENT_BATCH);
  if (cutoff === 0) return 0;
  const earliestBoundary = Math.max(0, cutoff - 50);
  for (let index = cutoff; index >= earliestBoundary; index -= 1) {
    if (events[index]?.kind === "user") return index;
  }
  return cutoff;
}

export function TranscriptEventRows({
  events,
  fileActionsDisabled,
  focusTurnRequest,
  liveStreams,
  onOpenFile,
  onReviseTurn,
  interrupted = false,
  reasoningEnabled,
  revisionActionsDisabled = false,
  stopping = false,
  turnRevisionBusy = null,
}: {
  events: AgentEvent[];
  fileActionsDisabled: boolean;
  focusTurnRequest?: { requestId: number; turnId: string } | null;
  liveStreams?: Map<string, LiveStreamView>;
  onOpenFile: (path: string) => void;
  onReviseTurn?: (turnId: string, mode: AgentTurnRevisionMode) => void;
  interrupted?: boolean;
  reasoningEnabled: boolean;
  revisionActionsDisabled?: boolean;
  stopping?: boolean;
  turnRevisionBusy?: TurnRevisionBusy | null;
}) {
  const [windowEnd, setWindowEnd] = useState(events.length);
  const previousEventCount = useRef(events.length);
  useEffect(() => {
    const previous = previousEventCount.current;
    previousEventCount.current = events.length;
    setWindowEnd((value) => (
      value >= previous ? events.length : Math.min(value, events.length)
    ));
  }, [events.length]);
  useEffect(() => {
    if (focusTurnRequest === null || focusTurnRequest === undefined) return;
    const targetIndex = events.findIndex((event) => (
      event.kind === "done" && event.turn_id === focusTurnRequest.turnId
    ));
    if (targetIndex < 0) return;
    setWindowEnd(Math.min(events.length, targetIndex + 1));
  }, [focusTurnRequest?.requestId]);
  useEffect(() => {
    if (focusTurnRequest === null || focusTurnRequest === undefined) return;
    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById(`agent-turn-${focusTurnRequest.turnId}`);
      if (!(target instanceof HTMLDetailsElement)) return;
      target.open = true;
      if (typeof target.scrollIntoView === "function") target.scrollIntoView({ block: "center" });
      target.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [focusTurnRequest?.requestId, windowEnd]);
  const effectiveWindowEnd = events.length !== previousEventCount.current
    ? windowEnd >= previousEventCount.current
      ? events.length
      : Math.min(windowEnd, events.length)
    : windowEnd;
  const boundedEnd = Math.max(0, Math.min(events.length, effectiveWindowEnd));
  const start = transcriptStartIndex(events, boundedEnd);
  const visible = events.slice(start, boundedEnd);
  const mcpCalls = collectAgentMcpCalls(events);
  const visibleMcpAnchor = new Map<string, number>();
  for (const event of visible) {
    const callId = event.call_id ?? null;
    if (callId && mcpCalls.has(callId) && !visibleMcpAnchor.has(callId)) {
      visibleMcpAnchor.set(callId, event.seq);
    }
  }
  const sourceUsers = new Map<string, AgentEvent>();
  for (const event of events) {
    if (event.kind === "user" && event.turn_id) sourceUsers.set(event.turn_id, event);
  }
  const firstVisibleDelta = new Map<string, number>();
  for (const event of visible) {
    if (event.kind === "assistant_delta" && event.stream_id && !firstVisibleDelta.has(event.stream_id)) {
      firstVisibleDelta.set(event.stream_id, event.seq);
    }
  }

  return (
    <>
      {(start > 0 || boundedEnd < events.length) && (
        <nav aria-label="Agent activity pages" className="agent__transcript-window">
          <span aria-live="polite">
            Showing activity {(start + 1).toLocaleString("en-US")}–{boundedEnd.toLocaleString("en-US")} of {events.length.toLocaleString("en-US")} events.
          </span>
          <span className="agent__transcript-window-actions">
            {start > 0 && (
              <button
                className="button button--ghost"
                onClick={() => setWindowEnd(start)}
                type="button"
              >Earlier {Math.min(TRANSCRIPT_EVENT_BATCH, start).toLocaleString("en-US")}</button>
            )}
            {boundedEnd < events.length && (
              <button
                className="button button--ghost"
                onClick={() => setWindowEnd(Math.min(
                  events.length,
                  boundedEnd + TRANSCRIPT_EVENT_BATCH,
                ))}
                type="button"
              >Later</button>
            )}
            {boundedEnd < events.length && (
              <button
                className="button button--ghost"
                onClick={() => setWindowEnd(events.length)}
                type="button"
              >Latest</button>
            )}
          </span>
        </nav>
      )}
      {visible.map((event, index) => {
        const globalIndex = start + index;
        const mcpCall = event.call_id ? mcpCalls.get(event.call_id) : undefined;
        if (mcpCall) {
          return visibleMcpAnchor.get(mcpCall.callId) === event.seq
            ? <AgentMcpToolActivity call={mcpCall} interrupted={interrupted} key={`mcp-${mcpCall.callId}`} stopping={stopping} />
            : null;
        }
        if (event.kind === "assistant" && event.stream_status === "complete"
          && !event.text?.trim() && !event.reasoning?.trim()
          && events[globalIndex + 1]?.kind === "tool_call") return null;
        if (event.kind !== "assistant_delta") {
          return (
            <EventRow
              key={event.seq}
              event={event}
              fileActionsDisabled={fileActionsDisabled}
              onOpenFile={onOpenFile}
              onReviseTurn={onReviseTurn}
              reasoningEnabled={reasoningEnabled}
              revisionActionsDisabled={revisionActionsDisabled}
              sourceUser={event.turn_id ? sourceUsers.get(event.turn_id) : undefined}
              turnRevisionBusy={turnRevisionBusy}
            />
          );
        }
        if (!event.stream_id || liveStreams === undefined) return null;
        const live = liveStreams.get(event.stream_id);
        return live && firstVisibleDelta.get(event.stream_id) === event.seq
          ? <LiveAssistant key={event.stream_id} content={live.content} reasoning={live.reasoning} onOpenFile={onOpenFile} />
          : null;
      })}
    </>
  );
}

export function compactTerminalDeltas(events: AgentEvent[]): AgentEvent[] {
  const terminalIds = new Set(
    events
      .filter((event) => event.kind === "assistant" && event.stream_id)
      .map((event) => event.stream_id as string),
  );
  return events.filter((event) => event.kind !== "assistant_delta" || !event.stream_id || !terminalIds.has(event.stream_id));
}

export function coalesceLiveStreams(events: AgentEvent[]): Map<string, LiveStreamView> {
  const terminalIds = new Set(
    events
      .filter((event) => event.kind === "assistant" && event.stream_id)
      .map((event) => event.stream_id as string),
  );
  const live = new Map<string, LiveStreamView>();
  for (const event of events) {
    if (event.kind !== "assistant_delta" || !event.stream_id || terminalIds.has(event.stream_id) || !event.text) continue;
    const current = live.get(event.stream_id) ?? { firstSeq: event.seq, content: "", reasoning: "" };
    if (event.stream_phase === "reasoning") current.reasoning += event.text;
    else current.content += event.text;
    live.set(event.stream_id, current);
  }
  return live;
}

function LiveAssistant({ content, reasoning, onOpenFile }: { content: string; reasoning: string; onOpenFile: (path: string) => void }) {
  return (
    <article className="agent__turn agent__turn--assistant agent__turn--live" aria-label="Agent response streaming">
      <header><span>Agent</span><span className="agent__event-badge">Streaming</span></header>
      {reasoning && <ReasoningPanel content={reasoning} live />}
      {content && <AgentMessageContent content={content} onOpenWorkspaceFile={onOpenFile} />}
    </article>
  );
}

function ReasoningPanel({ content, live = false }: { content: string; live?: boolean }) {
  return (
    <details className="agent__reasoning" open={live || undefined}>
      <summary><span>Model reasoning</span><small>{live ? "live · model-provided" : "model-provided · expand"}</small></summary>
      <p className="agent__reasoning-truth">Only reasoning text explicitly exposed by the model is shown. Hidden chain of thought is not reconstructed.</p>
      {!live && <AgentCopyButton className="agent__reasoning-copy" label="Copy model reasoning" value={content} />}
      <AgentMessageContent content={content} variant="reasoning" />
    </details>
  );
}

function formatAttachmentBytes(value: number): string {
  return value < 1024 * 1024
    ? `${Math.ceil(value / 1024)} KB`
    : `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function attachmentDetail(attachment: AgentMessageAttachment): string {
  if (attachment.kind === "image" && attachment.width && attachment.height) {
    return `${attachment.width} × ${attachment.height}`;
  }
  if (attachment.kind === "audio" && attachment.duration_ms !== null && attachment.duration_ms !== undefined) {
    return `${Math.max(1, Math.round(attachment.duration_ms / 1000))} s`;
  }
  if (attachment.kind === "document" && attachment.document_format) {
    const projected = attachment.projected_characters === null
      || attachment.projected_characters === undefined
      ? "projection size unknown"
      : `${attachment.projected_characters.toLocaleString()} projected characters`;
    const truncated = attachment.projection_truncated ? " · truncated" : "";
    const omitted = attachment.omitted_features.length > 0
      ? ` · omitted ${attachment.omitted_features.join(", ")}`
      : "";
    return `${attachment.document_format.toUpperCase()} · ${projected}${truncated}${omitted}`;
  }
  return attachment.media_type;
}

function MessageAttachments({ attachments }: { attachments: AgentMessageAttachment[] }) {
  return (
    <ul aria-label="Message attachments" className="agent__message-attachments">
      {attachments.map((attachment) => (
        <li key={attachment.attachment_id}>
          <span aria-hidden="true" className="agent__attachment-kind">
            {attachment.kind === "image" ? "Image" : attachment.kind === "audio" ? "Audio" : "Document"}
          </span>
          <span>
            <strong>{attachment.display_name}</strong>
            <small>{attachmentDetail(attachment)} · {formatAttachmentBytes(attachment.byte_size)} · context cost unknown</small>
          </span>
        </li>
      ))}
    </ul>
  );
}

function EventRow({
  event,
  reasoningEnabled,
  onOpenFile,
  onReviseTurn,
  fileActionsDisabled,
  revisionActionsDisabled,
  sourceUser,
  turnRevisionBusy,
}: {
  event: AgentEvent;
  reasoningEnabled: boolean;
  onOpenFile: (path: string) => void;
  onReviseTurn?: (turnId: string, mode: AgentTurnRevisionMode) => void;
  fileActionsDisabled: boolean;
  revisionActionsDisabled: boolean;
  sourceUser?: AgentEvent;
  turnRevisionBusy: TurnRevisionBusy | null;
}) {
  if (event.kind === "done") return event.turn_summary && event.turn_id
    ? <AgentTurnDetails
        summary={event.turn_summary}
        turnId={event.turn_id}
        onOpenFile={onOpenFile}
        fileActionsDisabled={fileActionsDisabled}
        onRevise={onReviseTurn && sourceUser?.text?.trim()
          ? (mode) => onReviseTurn(event.turn_id as string, mode)
          : undefined}
        revisionBusyMode={turnRevisionBusy?.turnId === event.turn_id ? turnRevisionBusy.mode : null}
        revisionDisabled={revisionActionsDisabled}
        sourceHasAttachments={Boolean(sourceUser?.attachments.length)}
      />
    : <p className="agent__status">Turn details were not reported for this run.</p>;
  if (event.kind === "user") return (
    <article className="agent__turn agent__turn--user">
      <header><span>You</span>{event.text && <AgentCopyButton label="Copy message" value={event.text} />}</header>
      {event.text ? <AgentMessageContent content={event.text} variant="user" /> : null}
      {event.attachments.length > 0 ? <MessageAttachments attachments={event.attachments} /> : null}
    </article>
  );
  if (event.kind === "assistant") {
    const status = event.stream_status === "stopped" ? "Stopped" : event.stream_status === "failed" ? "Interrupted" : "Complete";
    return (
      <article className="agent__turn agent__turn--assistant" data-stream-status={event.stream_status ?? "whole"}>
        <header><span>Agent</span><span className="agent__event-badge">{status}</span>{event.text && <AgentCopyButton label="Copy agent response" value={event.text} />}</header>
        {event.reasoning && <ReasoningPanel content={event.reasoning} />}
        {!event.reasoning && reasoningEnabled && <p className="agent__reasoning-inline">No separate reasoning trace was exposed for this response.</p>}
        {event.text ? <AgentMessageContent content={event.text} onOpenWorkspaceFile={fileActionsDisabled ? undefined : onOpenFile} /> : !event.reasoning ? <p className="agent__status">No assistant text was completed.</p> : null}
      </article>
    );
  }
  if (event.kind === "assistant_delta") return null;
  if (event.kind === "tool_call") {
    return (
      <article aria-label={`Agent action: ${TOOL_LABELS[event.tool ?? ""] ?? event.tool ?? "tool"}`} className="agent__tool" data-tool={event.tool ?? ""}>
        <span className="agent__event-badge">{isExternalWriteTransactionProposal(event) ? "Controller change set" : isExternalWriteProposal(event) ? "Controller proposal" : "Action"}</span>
        <span className="agent__tool-name">{TOOL_LABELS[event.tool ?? ""] ?? event.tool}</span>
        <code>{summarizeArguments(event.tool, event.arguments as Record<string, unknown> | null)}</code>
      </article>
    );
  }
  if (event.kind === "tool_result") {
    const label = event.tool_state ? { succeeded: "Completed", failed: "Failed", not_approved: "Not approved", cancelled: "Cancelled", unverified: "Effect unverified" }[event.tool_state]
      : event.ok === true ? "Completed" : event.ok === false ? "Failed" : "Outcome unknown";
    const receipt = event.execution_receipt;
    const approvalLabel = receipt ? {
      not_required: "Not required",
      not_requested: "Not requested",
      approved: "Approved",
      denied: "Denied",
      timed_out: "Timed out",
      cancelled_before_decision: "Cancelled before decision",
    }[receipt.approval_state] : null;
    const evidenceLabel = receipt ? {
      read_only_observation: "Read-only observation",
      verified_workspace_effect: "Verified workspace effect",
      unverified_workspace_effect: "Unverified workspace effect",
      untracked_external_effect: "Untracked external effect",
      no_effect: "No effect",
      unknown: "Effect unknown",
    }[receipt.evidence_state] : null;
    const elapsedLabel = !receipt
      ? null
      : receipt.elapsed_ms == null
      ? "Elapsed unknown"
      : receipt.elapsed_ms < 1_000
      ? `${Number(receipt.elapsed_ms.toFixed(receipt.elapsed_ms < 10 ? 1 : 0))} ms`
      : `${Number((receipt.elapsed_ms / 1_000).toFixed(2))} s`;
    return (
      <details className="agent__result" data-ok={event.ok == null ? "unknown" : event.ok ? "true" : "false"}>
        <summary>
          <span className="agent__event-badge">{label}</span>
          <span>{TOOL_LABELS[event.tool ?? ""] ?? event.tool}</span>
          {receipt ? (
            <span className="agent__result-facts" aria-label="Action execution facts">
              <span className="agent__result-fact" title="Elapsed from action request to terminal result; approval waiting is included.">{elapsedLabel}</span>
              <span className="agent__result-fact" title="Native approval outcome">{approvalLabel}</span>
              <span className="agent__result-fact" title="Effect evidence state">{evidenceLabel}</span>
            </span>
          ) : <span className="agent__result-facts agent__result-facts--legacy">Execution details unavailable</span>}
        </summary>
        {event.text ? (
          <div className="agent__result-body">
            <AgentCopyButton label={`Copy ${TOOL_LABELS[event.tool ?? ""] ?? event.tool ?? "tool"} output`} value={event.text} />
            <pre>{event.text}</pre>
          </div>
        ) : <p className="agent__status">No raw tool output was included in this event.</p>}
      </details>
    );
  }
  if (event.kind === "approval_required") return <p className="agent__activity-event" data-tone="attention"><span className="agent__event-badge">{isExternalWriteTransactionProposal(event) ? "Controller change set" : isExternalWriteProposal(event) ? "Controller proposal" : "Approval"}</span>Waiting for your decision: {TOOL_LABELS[event.tool ?? ""] ?? event.tool}</p>;
  if (event.kind === "approval_resolved") return <p className="agent__activity-event" data-tone={event.ok ? "ready" : "attention"}><span className="agent__event-badge">{event.ok ? "Approved" : "Denied"}</span>{TOOL_LABELS[event.tool ?? ""] ?? event.tool}{event.text ? ` (${event.text})` : ""}</p>;
  if (event.kind === "error") return <p className="agent__activity-event agent__error" data-tone="error" role="alert"><span className="agent__event-badge">Error</span>{event.text}</p>;
  if (event.kind === "status") return <p className="agent__activity-event agent__status"><span className="agent__event-badge">Status</span>{event.text}</p>;
  return null;
}
