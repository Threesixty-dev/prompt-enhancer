import type { AgentAttachment, AgentMessageAttachment } from "../../shared/api/contracts";
import "./AgentAttachmentRetryChecklist.css";

export type AttachmentRetryRequirement = {
  attachment: AgentMessageAttachment;
  omitted: boolean;
};

function exactReplacement(
  requirement: AgentMessageAttachment,
  staged: AgentAttachment,
): boolean {
  return staged.kind === requirement.kind
    && staged.media_type === requirement.media_type
    && staged.byte_size === requirement.byte_size
    && staged.sha256 === requirement.sha256;
}

/** Resolve each original independently: one staged identity cannot satisfy two. */
export function unresolvedAttachmentRetryRequirements(
  requirements: readonly AttachmentRetryRequirement[],
  staged: readonly AgentAttachment[],
  sessionId: string,
): readonly AttachmentRetryRequirement[] {
  const available = staged.filter((attachment) => attachment.session_id === sessionId && attachment.state === "staged");
  const used = new Set<string>();
  return requirements.filter((requirement) => {
    if (requirement.omitted) return false;
    const match = available.find((attachment) => !used.has(attachment.attachment_id) && exactReplacement(requirement.attachment, attachment));
    if (match === undefined) return true;
    used.add(match.attachment_id);
    return false;
  });
}

export function AgentAttachmentRetryChecklist({
  requirements,
  sessionId,
  staged,
  onOmitChange,
}: {
  requirements: readonly AttachmentRetryRequirement[];
  sessionId: string;
  staged: readonly AgentAttachment[];
  onOmitChange: (attachmentId: string, omitted: boolean) => void;
}) {
  if (requirements.length === 0) return null;
  const unresolved = new Set(unresolvedAttachmentRetryRequirements(requirements, staged, sessionId).map((item) => item.attachment.attachment_id));
  return <section aria-label="Original attachments for this retry" className="agent-attachment-retry-checklist">
    <p><strong>Reattach the original files before sending.</strong> This branch did not copy attachments from the retried message.</p>
    <ul>
      {requirements.map((requirement) => {
        const id = requirement.attachment.attachment_id;
        const resolved = !requirement.omitted && !unresolved.has(id);
        return <li key={id}>
          <span>{requirement.attachment.display_name} · {requirement.attachment.kind} · {requirement.attachment.byte_size.toLocaleString("en-US")} bytes</span>
          {resolved
            ? <span className="agent-attachment-retry-checklist__matched">Exact file reattached</span>
            : <button
                aria-label={requirement.omitted ? `Require original ${requirement.attachment.display_name}` : `Omit original ${requirement.attachment.display_name}`}
                className="button button--ghost"
                onClick={() => onOmitChange(id, !requirement.omitted)}
                type="button"
              >{requirement.omitted ? "Require original" : "Omit this original"}</button>}
          {requirement.omitted && <span className="agent-attachment-retry-checklist__omitted">Original omitted</span>}
        </li>;
      })}
    </ul>
    {unresolved.size > 0 && <p className="agent-attachment-retry-checklist__warning">Choose each original file again, or explicitly send without it. A different file is never treated as the original.</p>}
  </section>;
}
