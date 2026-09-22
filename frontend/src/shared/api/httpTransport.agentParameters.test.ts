import { describe, expect, it, vi } from "vitest";

import { exampleAgentSession } from "./agentSession.test-support";
import type { UpdateAgentSessionParameters } from "./contracts";
import { createHttpTransport, TransportError } from "./httpTransport";

const SESSION_ID = "a".repeat(32);
const PROJECT_ID = "b".repeat(32);
const parameters = {
  temperature: 0.35,
  top_p: 0.8,
  max_tokens: 2048,
  enable_thinking: true,
} as const;
const request: UpdateAgentSessionParameters = {
  expected_project_id: PROJECT_ID,
  expected_revision: 7,
  expected_parameters: { ...parameters, max_tokens: 1400, enable_thinking: false },
  parameters,
};

function responseSession(overrides: Parameters<typeof exampleAgentSession>[0] = {}) {
  return exampleAgentSession({
    session_id: SESSION_ID,
    settings: {
      ...exampleAgentSession().settings,
      project_id: PROJECT_ID,
      parameters,
    },
    ...overrides,
  });
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function transport(fetchMock: ReturnType<typeof vi.fn>) {
  return createHttpTransport({
    fetch: fetchMock as unknown as typeof fetch,
    origin: "http://127.0.0.1:4173",
  });
}

describe("updateAgentSessionParameters HTTP transport", () => {
  it("sends the exact PUT route/body and forwards AbortSignal", async () => {
    const signal = new AbortController().signal;
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        csrf_token: "synthetic-csrf-token",
        expires_in_seconds: 300,
        user_presence_confirmation_available: false,
        user_presence_confirmation_mode: "unavailable",
      }))
      .mockResolvedValueOnce(jsonResponse(responseSession()));
    await transport(fetchMock).updateAgentSessionParameters(SESSION_ID, request, signal);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toBe(`/v1/agent/sessions/${SESSION_ID}/parameters`);
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({
      method: "PUT",
      signal,
      body: JSON.stringify(request),
    }));
  });

  it.each([
    ["wrong session", () => responseSession({ session_id: "c".repeat(32) })],
    ["wrong project", () => responseSession({ settings: { ...responseSession().settings, project_id: "d".repeat(32) } })],
    ["wrong desired parameters", () => responseSession({ settings: { ...responseSession().settings, parameters: { ...parameters, max_tokens: 1024 } } })],
  ])("rejects a %s response", async (_label, makeResponse) => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        csrf_token: "synthetic-csrf-token",
        expires_in_seconds: 300,
        user_presence_confirmation_available: false,
        user_presence_confirmation_mode: "unavailable",
      }))
      .mockResolvedValueOnce(jsonResponse(makeResponse()));
    await expect(transport(fetchMock).updateAgentSessionParameters(SESSION_ID, request)).rejects.toMatchObject({
      status: 200,
    });
  });

  it("rejects a malformed response", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        csrf_token: "synthetic-csrf-token",
        expires_in_seconds: 300,
        user_presence_confirmation_available: false,
        user_presence_confirmation_mode: "unavailable",
      }))
      .mockResolvedValueOnce(jsonResponse({ session_id: SESSION_ID, settings: { parameters } }));
    await expect(transport(fetchMock).updateAgentSessionParameters(SESSION_ID, request)).rejects.toBeInstanceOf(TransportError);
  });

  it("preserves the structured revision-conflict error", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        csrf_token: "synthetic-csrf-token",
        expires_in_seconds: 300,
        user_presence_confirmation_available: false,
        user_presence_confirmation_mode: "unavailable",
      }))
      .mockResolvedValueOnce(jsonResponse({ detail: { code: "agent_catalog_session_revision_conflict" } }, 409));
    await expect(transport(fetchMock).updateAgentSessionParameters(SESSION_ID, request)).rejects.toMatchObject({
      status: 409,
      reasonCode: "agent_catalog_session_revision_conflict",
    });
  });
});
