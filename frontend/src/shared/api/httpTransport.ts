import type {
  AnalysisRunListResponse,
  AnalysisRunResponse,
  CandidateListResponse,
  CandidateStatusFilter,
  CodexAnalysisSelection,
  CodexIngestionReport,
  CodexLabelEnrichmentReport,
  CodexLocalSourceStatus,
  CodexSessionListResponse,
  DisplayLabelEntityKind,
  PromptEnhancerTransport,
  ManualDisplayLabelResult,
  ReviewCommand,
  SessionMetricResponse,
  TaskRevisionListResponse,
  TaskRevisionResponse,
  TaskAnalysisResponse,
  TaskReviewResponse,
} from "./contracts";

type FetchLike = typeof globalThis.fetch;

export class TransportError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "TransportError";
    this.status = status;
  }
}

/**
 * Return a request target only when the caller supplied a root-relative URL for
 * the current origin. Absolute, protocol-relative, credentialed, and cross-origin
 * targets are rejected before fetch is called.
 */
export function assertSameOriginRelativePath(path: string, origin: string): string {
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\")) {
    throw new TransportError("Only root-relative API paths are allowed", 0);
  }

  const expectedOrigin = new URL(origin).origin;
  const resolved = new URL(path, expectedOrigin);
  if (
    resolved.origin !== expectedOrigin ||
    resolved.username !== "" ||
    resolved.password !== ""
  ) {
    throw new TransportError("Unexpected API origin", 0);
  }
  return `${resolved.pathname}${resolved.search}`;
}

function isJsonResponse(response: Response): boolean {
  return response.headers.get("content-type")?.toLowerCase().includes("application/json") ?? false;
}

export function createHttpTransport(options: {
  fetch?: FetchLike;
  origin?: string;
} = {}): PromptEnhancerTransport {
  const fetchRequest = options.fetch ?? globalThis.fetch.bind(globalThis);
  const origin = options.origin ?? globalThis.location.origin;
  let sessionAuth: { csrfToken: string; refreshAfter: number } | undefined;
  let sessionBootstrap: Promise<string> | undefined;

  async function bootstrapBrowserSession(): Promise<string> {
    const target = assertSameOriginRelativePath("/auth/session", origin);
    const response = await fetchRequest(target, {
      method: "GET",
      credentials: "include",
      redirect: "error",
      referrerPolicy: "no-referrer",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new TransportError(
        `Local browser session could not be created (${response.status})`,
        response.status,
      );
    }
    if (!isJsonResponse(response)) {
      throw new TransportError(
        "Local browser session returned an unexpected content type",
        response.status,
      );
    }

    const payload = (await response.json()) as {
      csrf_token?: unknown;
      expires_in_seconds?: unknown;
    };
    if (
      typeof payload.csrf_token !== "string" ||
      payload.csrf_token.length === 0 ||
      typeof payload.expires_in_seconds !== "number" ||
      payload.expires_in_seconds <= 0
    ) {
      throw new TransportError("Local browser session response was invalid", response.status);
    }
    sessionAuth = {
      csrfToken: payload.csrf_token,
      refreshAfter: Date.now() + Math.max(1, payload.expires_in_seconds - 5) * 1000,
    };
    return sessionAuth.csrfToken;
  }

  async function ensureBrowserSession(signal?: AbortSignal): Promise<string> {
    signal?.throwIfAborted();
    if (sessionAuth && Date.now() < sessionAuth.refreshAfter) {
      return sessionAuth.csrfToken;
    }

    if (sessionBootstrap === undefined) {
      sessionBootstrap = bootstrapBrowserSession().finally(() => {
        sessionBootstrap = undefined;
      });
    }
    const csrfToken = await sessionBootstrap;
    signal?.throwIfAborted();
    return csrfToken;
  }

  async function request<T>(
    path: string,
    init: RequestInit,
    signal?: AbortSignal,
  ): Promise<T> {
    const target = assertSameOriginRelativePath(path, origin);
    const method = (init.method ?? "GET").toUpperCase();
    const mutation = !["GET", "HEAD", "OPTIONS"].includes(method);
    let csrfToken = await ensureBrowserSession(signal);
    const send = (csrf: string) =>
      fetchRequest(target, {
        ...init,
        credentials: "include",
        redirect: "error",
        referrerPolicy: "no-referrer",
        signal,
        headers: {
          Accept: "application/json",
          ...(mutation ? { "X-Prompt-Enhancer-CSRF": csrf } : {}),
          ...init.headers,
        },
      });
    let response = await send(csrfToken);
    if (response.status === 401) {
      if (sessionAuth?.csrfToken === csrfToken) sessionAuth = undefined;
      csrfToken = await ensureBrowserSession(signal);
      response = await send(csrfToken);
    }

    if (!response.ok) {
      throw new TransportError(`Local API request failed (${response.status})`, response.status);
    }
    if (!isJsonResponse(response)) {
      throw new TransportError("Local API returned an unexpected content type", response.status);
    }
    return (await response.json()) as T;
  }

  return {
    getCodexLocalSourceStatus(signal) {
      return request<CodexLocalSourceStatus>(
        "/v1/local-sources/codex",
        { method: "GET" },
        signal,
      );
    },
    grantCodexLocalHistoryConsent(signal) {
      return request<CodexLocalSourceStatus>(
        "/v1/local-sources/codex/consents/local-history",
        { method: "POST" },
        signal,
      );
    },
    revokeCodexLocalHistoryConsent(signal) {
      return request<CodexLocalSourceStatus>(
        "/v1/local-sources/codex/consents/local-history",
        { method: "DELETE" },
        signal,
      );
    },
    indexCodexLocalSessions(maxSessions, signal) {
      return request<CodexIngestionReport>(
        "/v1/local-sources/codex/index",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ max_sessions: maxSessions }),
        },
        signal,
      );
    },
    analyzeCodexLocalSessions(selection: CodexAnalysisSelection, signal) {
      return request<CodexIngestionReport>(
        "/v1/local-sources/codex/analysis",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(selection),
        },
        signal,
      );
    },
    enrichCodexDisplayLabels(selection: CodexAnalysisSelection, signal) {
      return request<CodexLabelEnrichmentReport>(
        "/v1/local-sources/codex/display-labels/enrich",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(selection),
        },
        signal,
      );
    },
    setManualDisplayLabel(
      entityKind: DisplayLabelEntityKind,
      entityId,
      value,
      expectedRevision,
      signal,
    ) {
      const collection = entityKind === "project" ? "projects" : "sessions";
      return request<ManualDisplayLabelResult>(
        `/v1/catalog/${collection}/${encodeURIComponent(entityId)}/display-label`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            value,
            expected_revision: expectedRevision,
          }),
        },
        signal,
      );
    },
    clearManualDisplayLabel(
      entityKind: DisplayLabelEntityKind,
      entityId,
      expectedRevision,
      signal,
    ) {
      const collection = entityKind === "project" ? "projects" : "sessions";
      return request<ManualDisplayLabelResult>(
        `/v1/catalog/${collection}/${encodeURIComponent(entityId)}/display-label?expected_revision=${expectedRevision}`,
        { method: "DELETE" },
        signal,
      );
    },
    listCodexSessions(limit = 100, offset = 0, signal) {
      return request<CodexSessionListResponse>(
        `/v1/sessions?provider=codex&limit=${limit}&offset=${offset}`,
        { method: "GET" },
        signal,
      );
    },
    getSessionMetrics(sessionId, signal) {
      return request<SessionMetricResponse>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/metrics`,
        { method: "GET" },
        signal,
      );
    },
    listCandidates(status = "all", signal) {
      const query = status === "all" ? "" : `?status=${encodeURIComponent(status)}`;
      return request<CandidateListResponse>(`/v1/discovery/candidates${query}`, { method: "GET" }, signal);
    },
    listTaskRevisions(taskId, signal) {
      const query = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
      return request<TaskRevisionListResponse>(`/v1/task-revisions${query}`, { method: "GET" }, signal);
    },
    getTaskRevision(taskId, revision, signal) {
      return request<TaskRevisionResponse>(
        `/v1/tasks/${encodeURIComponent(taskId)}/revisions/${revision}`,
        { method: "GET" },
        signal,
      );
    },
    listAnalysisRuns(taskId, signal) {
      const query = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
      return request<AnalysisRunListResponse>(`/v1/analysis/runs${query}`, { method: "GET" }, signal);
    },
    getAnalysisRun(runId, signal) {
      return request<AnalysisRunResponse>(
        `/v1/analysis/runs/${encodeURIComponent(runId)}`,
        { method: "GET" },
        signal,
      );
    },
    review(command, idempotencyKey, signal) {
      return request<TaskReviewResponse>(
        `/v1/task-decisions/${command.action}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey,
          },
          body: JSON.stringify(command.request),
        },
        signal,
      );
    },
    startAnalysis(taskId, revision, idempotencyKey, signal) {
      return request<TaskAnalysisResponse>(
        `/v1/tasks/${encodeURIComponent(taskId)}/revisions/${revision}/analysis-runs`,
        {
          method: "POST",
          headers: { "Idempotency-Key": idempotencyKey },
        },
        signal,
      );
    },
  };
}
