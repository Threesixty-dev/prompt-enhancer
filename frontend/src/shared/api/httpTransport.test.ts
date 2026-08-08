import { describe, expect, it, vi } from "vitest";
import { assertSameOriginRelativePath, createHttpTransport, TransportError } from "./httpTransport";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const AUTH_RESPONSE = { csrf_token: "synthetic-csrf-token", expires_in_seconds: 300 };

describe("same-origin HTTP transport", () => {
  it.each([
    "https://outside.invalid/v1/discovery/candidates",
    "//outside.invalid/v1/discovery/candidates",
    "v1/discovery/candidates",
    "/v1\\discovery\\candidates",
  ])("rejects unexpected target %s", (target) => {
    expect(() => assertSameOriginRelativePath(target, "http://127.0.0.1:4173")).toThrow(
      TransportError,
    );
  });

  it("bootstraps browser auth and uses relative URLs with included credentials", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) =>
      input === "/auth/session"
        ? jsonResponse(AUTH_RESPONSE)
        : jsonResponse({ candidates: [], limit: 100, offset: 0 }),
    ) as unknown as typeof fetch;
    const transport = createHttpTransport({
      fetch: fetchMock,
      origin: "http://127.0.0.1:4173",
    });

    await transport.listCandidates("undecided");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/auth/session",
      expect.objectContaining({
        credentials: "include",
        method: "GET",
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/discovery/candidates?status=undecided",
      expect.objectContaining({
        credentials: "include",
        method: "GET",
        redirect: "error",
        referrerPolicy: "no-referrer",
      }),
    );
  });

  it("does not parse an unexpected response type", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(
        new Response("not-json", {
          status: 200,
          headers: { "Content-Type": "text/plain" },
        }),
      ) as unknown as typeof fetch;
    const transport = createHttpTransport({
      fetch: fetchMock,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.listCandidates()).rejects.toMatchObject({ status: 200 });
  });

  it("keeps CSRF in memory and attaches it only to mutations", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(
        jsonResponse({
          consent_active: true,
          indexed_sessions: 0,
          indexed_projects: 0,
        }),
      );
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await transport.grantCodexLocalHistoryConsent();

    const mutationInit = fetchMock.mock.calls[1][1] as RequestInit;
    expect(mutationInit).toEqual(
      expect.objectContaining({ credentials: "include", method: "POST" }),
    );
    expect(mutationInit.headers).toEqual(
      expect.objectContaining({
        "X-Prompt-Enhancer-CSRF": "synthetic-csrf-token",
      }),
    );
    expect(mutationInit.headers).not.toEqual(
      expect.objectContaining({ "X-Prompt-Enhancer-Token": expect.anything() }),
    );
  });

  it("shares one browser bootstrap across concurrent initial requests", async () => {
    let resolveBootstrap: ((response: Response) => void) | undefined;
    const pendingBootstrap = new Promise<Response>((resolve) => {
      resolveBootstrap = resolve;
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) =>
      input === "/auth/session"
        ? pendingBootstrap
        : Promise.resolve(jsonResponse({ candidates: [], limit: 100, offset: 0 })),
    );
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    const first = transport.listCandidates();
    const second = transport.listCandidates();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolveBootstrap?.(jsonResponse(AUTH_RESPONSE));
    await Promise.all([first, second]);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(
      fetchMock.mock.calls.filter(([input]) => input === "/auth/session"),
    ).toHaveLength(1);
  });

  it("re-establishes in-memory browser auth once after a 401", async () => {
    const refreshedAuth = {
      csrf_token: "synthetic-refreshed-csrf-token",
      expires_in_seconds: 300,
    };
    const sourceStatus = {
      consent_active: true,
      indexed_sessions: 0,
      indexed_projects: 0,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse({ detail: "authentication required" }, 401))
      .mockResolvedValueOnce(jsonResponse(refreshedAuth))
      .mockResolvedValueOnce(jsonResponse(sourceStatus));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await transport.grantCodexLocalHistoryConsent();

    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(fetchMock.mock.calls[0][0]).toBe("/auth/session");
    expect(fetchMock.mock.calls[2][0]).toBe("/auth/session");
    const retriedMutation = fetchMock.mock.calls[3][1] as RequestInit;
    expect(retriedMutation.headers).toEqual(
      expect.objectContaining({
        "X-Prompt-Enhancer-CSRF": "synthetic-refreshed-csrf-token",
      }),
    );
  });
});
