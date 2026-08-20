import type { AgentEvent, AgentEvents } from "./contracts";

const CONTRACT_VERSION = "local-agent.v2";
const MAX_EVENT_PAGE = 500;
const MAX_DELTA_CHARS = 192;
const ID = /^[0-9a-f]{32}$/u;
const KINDS = new Set<AgentEvent["kind"]>([
  "user",
  "assistant",
  "assistant_delta",
  "tool_call",
  "tool_result",
  "approval_required",
  "approval_resolved",
  "status",
  "error",
  "done",
]);
const EVENT_KEYS = new Set([
  "approval_id",
  "arguments",
  "at",
  "call_id",
  "kind",
  "ok",
  "preview",
  "reasoning",
  "seq",
  "stream_id",
  "stream_phase",
  "stream_status",
  "text",
  "tool",
]);

export class AgentEventPayloadError extends Error {
  constructor() {
    super("Local agent event payload was invalid");
    this.name = "AgentEventPayloadError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nullableString(value: unknown, maxLength: number): value is string | null | undefined {
  return value === null || value === undefined || (typeof value === "string" && Array.from(value).length <= maxLength);
}

function parseEvent(value: unknown): AgentEvent {
  if (!isRecord(value) || Object.keys(value).some((key) => !EVENT_KEYS.has(key))) {
    throw new AgentEventPayloadError();
  }
  const kind = value.kind;
  if (
    typeof kind !== "string" ||
    !KINDS.has(kind as AgentEvent["kind"]) ||
    !Number.isSafeInteger(value.seq) ||
    (value.seq as number) <= 0 ||
    typeof value.at !== "string" ||
    !Number.isFinite(Date.parse(value.at)) ||
    !nullableString(value.text, 120_000) ||
    !nullableString(value.reasoning, 120_000) ||
    !nullableString(value.tool, 256) ||
    !nullableString(value.call_id, 256) ||
    !nullableString(value.approval_id, 64) ||
    !nullableString(value.preview, 60_000) ||
    !(value.ok === null || value.ok === undefined || typeof value.ok === "boolean") ||
    !(value.arguments === null || value.arguments === undefined || isRecord(value.arguments))
  ) {
    throw new AgentEventPayloadError();
  }
  const streamId = value.stream_id;
  const streamPhase = value.stream_phase;
  const streamStatus = value.stream_status;
  if (kind === "assistant_delta") {
    if (
      typeof streamId !== "string" ||
      !ID.test(streamId) ||
      (streamPhase !== "content" && streamPhase !== "reasoning") ||
      streamStatus != null ||
      typeof value.text !== "string" ||
      value.text.length === 0 ||
      Array.from(value.text).length > MAX_DELTA_CHARS ||
      value.reasoning != null
    ) {
      throw new AgentEventPayloadError();
    }
  } else if (kind === "assistant") {
    const hasStream = typeof streamId === "string" && ID.test(streamId);
    const hasStatus = streamStatus === "complete" || streamStatus === "stopped" || streamStatus === "failed";
    if (streamPhase != null || hasStream !== hasStatus || (streamId != null && !hasStream) || (streamStatus != null && !hasStatus)) {
      throw new AgentEventPayloadError();
    }
  } else if (streamId != null || streamPhase != null || streamStatus != null || value.reasoning != null) {
    throw new AgentEventPayloadError();
  }
  return value as AgentEvent;
}

export function parseAgentEvents(
  value: unknown,
  expectedSessionId?: string,
  after = 0,
): AgentEvents {
  if (
    !isRecord(value) ||
    Object.keys(value).sort().join(",") !==
      "contract_version,events,first_seq,last_seq,pending_approval_id,running,session_id" ||
    value.contract_version !== CONTRACT_VERSION ||
    typeof value.session_id !== "string" ||
    !ID.test(value.session_id) ||
    (expectedSessionId !== undefined && value.session_id !== expectedSessionId) ||
    !Array.isArray(value.events) ||
    value.events.length > MAX_EVENT_PAGE ||
    typeof value.running !== "boolean" ||
    !(value.pending_approval_id === null || (typeof value.pending_approval_id === "string" && ID.test(value.pending_approval_id))) ||
    !Number.isSafeInteger(value.last_seq) ||
    (value.last_seq as number) < 0 ||
    !Number.isSafeInteger(value.first_seq) ||
    (value.first_seq as number) < 0 ||
    ((value.last_seq as number) === 0) !== ((value.first_seq as number) === 0)
  ) {
    throw new AgentEventPayloadError();
  }
  const events = value.events.map(parseEvent);
  let cursor = after;
  for (const event of events) {
    if (event.seq <= cursor || event.seq > (value.last_seq as number)) {
      throw new AgentEventPayloadError();
    }
    cursor = event.seq;
  }
  if (
    events.length > 0 &&
    ((value.first_seq as number) > events[0].seq || events.at(-1)?.seq !== cursor)
  ) {
    throw new AgentEventPayloadError();
  }
  return { ...value, events } as AgentEvents;
}
