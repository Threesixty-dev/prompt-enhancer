import { describe, expect, it } from "vitest";
import { AgentEventPayloadError, parseAgentEvents } from "./agentEventContract";

const SESSION = "a".repeat(32);
const STREAM = "b".repeat(32);

function page() {
  return {
    contract_version: "local-agent.v2",
    session_id: SESSION,
    events: [
      {
        seq: 1,
        at: "2026-08-20T01:00:00Z",
        kind: "assistant_delta",
        text: "Hello",
        reasoning: null,
        stream_id: STREAM,
        stream_phase: "content",
        stream_status: null,
        tool: null,
        arguments: null,
        call_id: null,
        approval_id: null,
        ok: null,
        preview: null,
      },
      {
        seq: 2,
        at: "2026-08-20T01:00:01Z",
        kind: "assistant",
        text: "Hello",
        reasoning: null,
        stream_id: STREAM,
        stream_phase: null,
        stream_status: "complete",
        tool: null,
        arguments: null,
        call_id: null,
        approval_id: null,
        ok: null,
        preview: null,
      },
    ],
    running: false,
    pending_approval_id: null,
    last_seq: 2,
    first_seq: 1,
  };
}

describe("agent event contract", () => {
  it("accepts one exact v2 stream page", () => {
    const parsed = parseAgentEvents(page(), SESSION, 0);
    expect(parsed.events.map((event) => event.kind)).toEqual(["assistant_delta", "assistant"]);
    const emojiDense = page();
    emojiDense.events[0].text = "😀".repeat(192);
    expect(parseAgentEvents(emojiDense, SESSION, 0).events[0].text).toHaveLength(384);
  });

  it("rejects stale versions, foreign sessions, cursor replays, and forged stream states", () => {
    const attacks = [
      { ...page(), contract_version: "local-agent.v1" },
      { ...page(), session_id: "c".repeat(32) },
      { ...page(), events: [{ ...page().events[0], seq: 0 }] },
      { ...page(), events: [{ ...page().events[0], stream_status: "complete" }] },
      { ...page(), events: [{ ...page().events[1], stream_status: null }] },
      { ...page(), events: [{ ...page().events[1], extra: "content" }] },
    ];
    for (const attack of attacks) {
      expect(() => parseAgentEvents(attack, SESSION, 0)).toThrow(AgentEventPayloadError);
    }
    expect(() => parseAgentEvents(page(), SESSION, 1)).toThrow(AgentEventPayloadError);
  });
});
