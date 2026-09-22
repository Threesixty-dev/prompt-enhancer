import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { AgentAttachment, AgentMessageAttachment } from "../../shared/api/contracts";
import { AgentAttachmentRetryChecklist, unresolvedAttachmentRetryRequirements } from "./AgentAttachmentRetryChecklist";

const original: AgentMessageAttachment = {
  contract_version: "agent-attachment.v2", attachment_id: "a".repeat(32), kind: "image", media_type: "image/png", display_name: "synthetic.png", sha256: "b".repeat(64), byte_size: 68,
  width: 1, height: 1, duration_ms: null, sample_rate_hz: null, channels: null, routing: "native_multimodal", document_format: null, projected_characters: null, projection_truncated: null, omitted_features: [], context_tokens: null, context_cost_source: "runtime_unreported",
};

function staged(overrides: Partial<AgentAttachment> = {}): AgentAttachment {
  return { ...original, session_id: "c".repeat(32), model_alias: "synthetic", capability_probe_version: "synthetic.v1", source: "file", state: "staged", retention: "memory_only", created_at: "2040-01-01T00:00:00Z", expires_at: "2040-01-01T01:00:00Z", attached_event_seq: null, ...overrides };
}

it("requires an exact, child-session staged replacement and never reuses one staged identity", () => {
  const requirements = [{ attachment: original, omitted: false }, { attachment: { ...original, attachment_id: "d".repeat(32) }, omitted: false }];
  expect(unresolvedAttachmentRetryRequirements(requirements, [staged()], "c".repeat(32))).toHaveLength(1);
  expect(unresolvedAttachmentRetryRequirements(requirements, [staged({ sha256: "e".repeat(64) })], "c".repeat(32))).toHaveLength(2);
  expect(unresolvedAttachmentRetryRequirements(requirements, [staged({ session_id: "f".repeat(32) })], "c".repeat(32))).toHaveLength(2);
  expect(unresolvedAttachmentRetryRequirements([{ attachment: original, omitted: true }], [], "c".repeat(32))).toHaveLength(0);
});

it.each([
  ["kind", { kind: "audio" as const, media_type: "audio/wav" as const, width: null, height: null, duration_ms: 1, sample_rate_hz: 8_000, channels: 1 }],
  ["media type", { media_type: "image/jpeg" as const }],
  ["byte size", { byte_size: 69 }],
  ["attached state", { state: "attached" as const, expires_at: null, attached_event_seq: 1 }],
])("does not accept a staged replacement with a different %s", (_label, overrides) => {
  expect(unresolvedAttachmentRetryRequirements([{ attachment: original, omitted: false }], [staged(overrides)], "c".repeat(32))).toHaveLength(1);
});

it("accepts distinct exact child staged identities and reblocks when one is removed", () => {
  const second = { ...original, attachment_id: "d".repeat(32) };
  const requirements = [{ attachment: original, omitted: false }, { attachment: second, omitted: false }];
  const first = staged();
  const secondStaged = staged({ attachment_id: "e".repeat(32) });
  expect(unresolvedAttachmentRetryRequirements(requirements, [first, secondStaged], "c".repeat(32))).toHaveLength(0);
  expect(unresolvedAttachmentRetryRequirements(requirements, [first], "c".repeat(32))).toHaveLength(1);
});

it("keeps keyboard focus on the stable omit control while toggling either direction", () => {
  const onOmitChange = vi.fn();
  const { rerender } = render(<AgentAttachmentRetryChecklist
    requirements={[{ attachment: original, omitted: false }]}
    sessionId={"c".repeat(32)}
    staged={[]}
    onOmitChange={onOmitChange}
  />);
  const omit = screen.getByRole("button", { name: "Omit original synthetic.png" });
  omit.focus();
  fireEvent.click(omit);
  expect(onOmitChange).toHaveBeenCalledWith(original.attachment_id, true);
  rerender(<AgentAttachmentRetryChecklist
    requirements={[{ attachment: original, omitted: true }]}
    sessionId={"c".repeat(32)}
    staged={[]}
    onOmitChange={onOmitChange}
  />);
  const requireOriginal = screen.getByRole("button", { name: "Require original synthetic.png" });
  expect(requireOriginal).toHaveFocus();
  fireEvent.click(requireOriginal);
  expect(onOmitChange).toHaveBeenLastCalledWith(original.attachment_id, false);
  rerender(<AgentAttachmentRetryChecklist
    requirements={[{ attachment: original, omitted: false }]}
    sessionId={"c".repeat(32)}
    staged={[]}
    onOmitChange={onOmitChange}
  />);
  expect(screen.getByRole("button", { name: "Omit original synthetic.png" })).toHaveFocus();
});
