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
  ManualDisplayLabelResult,
  ModelLinkAnnotation,
  ModelLinkAnnotationRequest,
  ModelLinkExperiment,
  ModelLinkExperimentOutcome,
  ModelLinkExperimentRequest,
  ProjectQualityAggregate,
  ProjectQualityAggregateRequest,
  ProjectSessionListResponse,
  ProviderCompatibilityProvider,
  ProviderCompatibilityStatus,
  ReviewCommand,
  SessionAnalysisRunResponse,
  SessionCoachingProjection,
  SessionMetricResponse,
  SessionQualityAnalysisOutcome,
  SessionQualityAnalysisRequest,
  SessionTextAnalysisCapability,
  SessionQualityAggregate,
  SessionQualityAggregateRequest,
  TaskRevisionListResponse,
  TaskRevisionResponse,
  TaskAnalysisResponse,
  TaskReviewResponse,
  TextAnalysisResearchCatalog,
} from "./contracts";
import type {
  LocalRuntimeTransport,
  RuntimeHealth,
} from "../platform/runtimeMode";

type FetchLike = typeof globalThis.fetch;

export class TransportError extends Error {
  readonly status: number;
  readonly reasonCode: SafeTransportReasonCode | null;

  constructor(
    message: string,
    status: number,
    reasonCode: SafeTransportReasonCode | null = null,
  ) {
    super(message);
    this.name = "TransportError";
    this.status = status;
    this.reasonCode = reasonCode;
  }
}

export type SafeTransportReasonCode =
  | "redacted_content_consent_required"
  | "session_not_in_safe_index"
  | "analysis_idempotency_conflict"
  | "invalid_analysis_request"
  | "confirmation_required"
  | "source_schema_unsupported"
  | "selection_snapshot_miss"
  | "source_resource_limit"
  | "source_timeout"
  | "provider_unavailable"
  | "no_analyzable_text"
  | "provider_protocol_rejected"
  | "provider_compatibility_blocked"
  | "analysis_persistence_failed"
  | "metric_execution_failed"
  | "invalid_model_link_request"
  | "model_link_confirmation_required"
  | "no_model_link_candidates"
  | "local_model_execution_failed"
  | "model_link_persistence_failed"
  | "model_link_revision_conflict";

const SAFE_TRANSPORT_REASONS = new Set<SafeTransportReasonCode>([
  "redacted_content_consent_required",
  "session_not_in_safe_index",
  "analysis_idempotency_conflict",
  "invalid_analysis_request",
  "confirmation_required",
  "source_schema_unsupported",
  "selection_snapshot_miss",
  "source_resource_limit",
  "source_timeout",
  "provider_unavailable",
  "no_analyzable_text",
  "provider_protocol_rejected",
  "provider_compatibility_blocked",
  "analysis_persistence_failed",
  "metric_execution_failed",
  "invalid_model_link_request",
  "model_link_confirmation_required",
  "no_model_link_candidates",
  "local_model_execution_failed",
  "model_link_persistence_failed",
  "model_link_revision_conflict",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function allowlistedReason(value: unknown): SafeTransportReasonCode | null {
  return typeof value === "string" &&
    SAFE_TRANSPORT_REASONS.has(value as SafeTransportReasonCode)
    ? (value as SafeTransportReasonCode)
    : null;
}

function safeReasonFromErrorPayload(value: unknown): SafeTransportReasonCode | null {
  return isRecord(value) && isRecord(value.detail)
    ? allowlistedReason(value.detail.code)
    : null;
}

export function parseSessionTextAnalysisCapability(
  value: unknown,
): SessionTextAnalysisCapability {
  if (
    !isRecord(value) ||
    typeof value.session_text_analysis !== "boolean" ||
    !(
      value.session_text_analysis_data_tier === "redacted_content" ||
      value.session_text_analysis_data_tier === null
    ) ||
    value.session_text_content_persistence !== false ||
    typeof value.codex_local_source !== "boolean" ||
    value.network_inference !== false ||
    value.raw_transcripts !== false
  ) {
    throw new TransportError("Local analysis capability response was invalid", 200);
  }

  if (value.session_text_analysis) {
    if (
      value.session_text_analysis_data_tier !== "redacted_content" ||
      value.codex_local_source !== true
    ) {
      throw new TransportError("Local analysis capability response was invalid", 200);
    }
    return {
      available: true,
      reason_code: "available",
      data_tier: "redacted_content",
      content_persistence: false,
      network_inference: false,
      raw_transcripts: false,
    };
  }

  if (value.session_text_analysis_data_tier !== null) {
    throw new TransportError("Local analysis capability response was invalid", 200);
  }
  return {
    available: false,
    reason_code: value.codex_local_source
      ? "analysis_service_unavailable"
      : "local_source_unavailable",
    data_tier: null,
    content_persistence: false,
    network_inference: false,
    raw_transcripts: false,
  };
}

const COMPATIBILITY_KEYS = new Set([
  "provider",
  "capability",
  "state",
  "capability_state",
  "provider_family",
  "provider_version",
  "adapter_family",
  "adapter_version",
  "source_schema_family",
  "source_schema_version",
  "content_schema_family",
  "content_schema_version",
  "reason_code",
  "checked_at",
  "update_support",
  "update_target",
]);
const SAFE_COMPATIBILITY_FAMILY = /^[a-z0-9][a-z0-9._-]{0,63}$/;
const SAFE_COMPATIBILITY_VERSION = /^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$/;
const SAFE_COMPATIBILITY_DATE =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/;

function safeNullableVersion(value: unknown): value is string | null {
  return value === null ||
    (typeof value === "string" && SAFE_COMPATIBILITY_VERSION.test(value));
}

const COMPATIBILITY_FAMILIES = {
  codex: {
    provider: "codex_app_server",
    adapter: "codex_app_server",
    source: "codex_thread",
    content: "codex_thread_items",
  },
  claude_code: {
    provider: "claude_code",
    adapter: "claude_code",
    source: "claude_session",
    content: "claude_content_blocks",
  },
  synthetic: {
    provider: "synthetic_provider",
    adapter: "synthetic_adapter",
    source: "synthetic_session",
    content: "synthetic_content",
  },
} as const;

export function parseProviderCompatibilityStatus(
  value: unknown,
  expectedProvider?: ProviderCompatibilityProvider,
): ProviderCompatibilityStatus {
  if (
    !isRecord(value) ||
    Object.keys(value).length !== COMPATIBILITY_KEYS.size ||
    Object.keys(value).some((key) => !COMPATIBILITY_KEYS.has(key)) ||
    !["codex", "claude_code", "synthetic"].includes(value.provider as string) ||
    value.capability !== "session_text_analysis" ||
    ![
      "exact",
      "compatible",
      "degraded",
      "untested",
      "incompatible",
      "unavailable",
    ].includes(value.state as string) ||
    !["supported", "unsupported", "unknown"].includes(
      value.capability_state as string,
    ) ||
    ![value.provider_family, value.adapter_family, value.source_schema_family, value.content_schema_family].every(
      (item) => typeof item === "string" && SAFE_COMPATIBILITY_FAMILY.test(item),
    ) ||
    ![
      value.provider_version,
      value.adapter_version,
      value.source_schema_version,
      value.content_schema_version,
    ].every(safeNullableVersion) ||
    ![
      "exact_match",
      "compatible_version",
      "degraded_extraction",
      "not_checked",
      "provider_unavailable",
      "provider_version_unsupported",
      "adapter_outdated",
      "source_schema_unsupported",
      "content_schema_unsupported",
      "check_failed",
    ].includes(value.reason_code as string) ||
    !(
      value.checked_at === null ||
      (typeof value.checked_at === "string" &&
        SAFE_COMPATIBILITY_DATE.test(value.checked_at) &&
        !Number.isNaN(new Date(value.checked_at).valueOf()))
    ) ||
    !["supported", "unsupported", "unknown"].includes(
      value.update_support as string,
    ) ||
    !(
      value.update_target === null ||
      value.update_target === "prompt_enhancer" ||
      value.update_target === "provider"
    )
  ) {
    throw new TransportError("Provider compatibility response was invalid", 200);
  }

  const state = value.state as ProviderCompatibilityStatus["state"];
  const provider = value.provider as ProviderCompatibilityProvider;
  const capabilityState =
    value.capability_state as ProviderCompatibilityStatus["capability_state"];
  const reason = value.reason_code as ProviderCompatibilityStatus["reason_code"];
  const checkedAt = value.checked_at as string | null;
  const updateSupport =
    value.update_support as ProviderCompatibilityStatus["update_support"];
  const updateTarget =
    value.update_target as ProviderCompatibilityStatus["update_target"];
  const exactVersions = [
    value.provider_version,
    value.adapter_version,
    value.source_schema_version,
    value.content_schema_version,
  ].every((item) => typeof item === "string");
  const expectedFamilies = COMPATIBILITY_FAMILIES[provider];
  const coherent =
    ((state === "exact" &&
      capabilityState === "supported" &&
      reason === "exact_match" &&
      checkedAt !== null &&
      exactVersions) ||
      (state === "compatible" &&
        capabilityState === "supported" &&
        reason === "compatible_version" &&
        checkedAt !== null &&
        exactVersions) ||
      (state === "degraded" &&
        reason === "degraded_extraction" &&
        checkedAt !== null) ||
      (state === "untested" &&
        capabilityState === "unknown" &&
        reason === "not_checked" &&
        checkedAt === null &&
        updateSupport === "unknown") ||
      (state === "incompatible" &&
        capabilityState === "unsupported" &&
        [
          "provider_version_unsupported",
          "adapter_outdated",
          "source_schema_unsupported",
          "content_schema_unsupported",
        ].includes(reason) &&
        checkedAt !== null) ||
      (state === "unavailable" &&
        capabilityState === "unknown" &&
        ["provider_unavailable", "check_failed"].includes(reason) &&
        checkedAt !== null)) &&
    value.provider_family === expectedFamilies.provider &&
    value.adapter_family === expectedFamilies.adapter &&
    value.source_schema_family === expectedFamilies.source &&
    value.content_schema_family === expectedFamilies.content &&
    (updateSupport === "supported"
      ? updateTarget !== null
      : updateTarget === null);

  if (!coherent) {
    throw new TransportError("Provider compatibility response was invalid", 200);
  }
  if (expectedProvider !== undefined && value.provider !== expectedProvider) {
    throw new TransportError("Provider compatibility response was invalid", 200);
  }
  return value as unknown as ProviderCompatibilityStatus;
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

/** Parse the deliberately minimal, unauthenticated loopback health response. */
export function parseRuntimeHealth(value: unknown): RuntimeHealth {
  if (
    !isRecord(value) ||
    Object.keys(value).sort().join(",") !== "cost_mode,data_tier,status" ||
    value.status !== "ok" ||
    value.cost_mode !== "offline_only" ||
    value.data_tier !== "metadata"
  ) {
    throw new TransportError("Local runtime health response was invalid", 200);
  }
  return {
    status: "ok",
    costMode: "offline_only",
    dataTier: "metadata",
  };
}

export function createHttpTransport(options: {
  fetch?: FetchLike;
  origin?: string;
} = {}): LocalRuntimeTransport {
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
    readSafeAnalysisReason = false,
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
      let reasonCode: SafeTransportReasonCode | null = null;
      if (readSafeAnalysisReason && isJsonResponse(response)) {
        try {
          reasonCode = safeReasonFromErrorPayload(await response.json());
        } catch {
          // Malformed or unexpected server content is deliberately discarded.
        }
      }
      throw new TransportError(
        `Local API request failed (${response.status})`,
        response.status,
        reasonCode,
      );
    }
    if (!isJsonResponse(response)) {
      throw new TransportError("Local API returned an unexpected content type", response.status);
    }
    return (await response.json()) as T;
  }

  return {
    runtimeKind: "local_loopback",
    async getRuntimeHealth(signal) {
      signal?.throwIfAborted();
      const target = assertSameOriginRelativePath("/health", origin);
      const response = await fetchRequest(target, {
        method: "GET",
        credentials: "include",
        redirect: "error",
        referrerPolicy: "no-referrer",
        signal,
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new TransportError(
          `Local runtime health check failed (${response.status})`,
          response.status,
        );
      }
      if (!isJsonResponse(response)) {
        throw new TransportError(
          "Local runtime health returned an unexpected content type",
          response.status,
        );
      }
      return parseRuntimeHealth(await response.json());
    },
    getTextAnalysisResearch(signal) {
      return request<TextAnalysisResearchCatalog>(
        "/v1/research/text-analysis-methods",
        { method: "GET" },
        signal,
      );
    },
    getTextModelRuntime(signal) {
      return request(
        "/v1/research/text-model-runtime",
        { method: "GET" },
        signal,
      );
    },
    startTextModelEvaluation(body, signal) {
      return request(
        "/v1/research/text-model-evaluations",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        signal,
      );
    },
    getTextModelEvaluation(jobId, signal) {
      return request(
        `/v1/research/text-model-evaluations/${encodeURIComponent(jobId)}`,
        { method: "GET" },
        signal,
      );
    },
    async getSessionTextAnalysisCapability(signal) {
      const value = await request<unknown>(
        "/v1/capabilities",
        { method: "GET" },
        signal,
      );
      return parseSessionTextAnalysisCapability(value);
    },
    async getProviderCompatibility(provider, signal) {
      const value = await request<unknown>(
        `/v1/providers/${encodeURIComponent(provider)}/compatibility`,
        { method: "GET" },
        signal,
      );
      return parseProviderCompatibilityStatus(value, provider);
    },
    async checkProviderCompatibility(provider, signal) {
      const value = await request<unknown>(
        `/v1/providers/${encodeURIComponent(provider)}/compatibility/check`,
        { method: "POST" },
        signal,
      );
      return parseProviderCompatibilityStatus(value, provider);
    },
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
    listProjectSessions(projectId, limit = 100, offset = 0, signal) {
      return request<ProjectSessionListResponse>(
        `/v1/projects/${encodeURIComponent(projectId)}/sessions?provider=codex&limit=${limit}&offset=${offset}`,
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
    getLatestSessionQualityAnalysis(sessionId, signal) {
      return request<SessionAnalysisRunResponse>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/quality-analysis-runs/latest`,
        { method: "GET" },
        signal,
      );
    },
    getSessionQualityAnalysisRun(runId, signal) {
      return request<SessionAnalysisRunResponse>(
        `/v1/quality-analysis/runs/${encodeURIComponent(runId)}`,
        { method: "GET" },
        signal,
      );
    },
    getSessionCoachingSummary(runId, signal) {
      return request<SessionCoachingProjection>(
        `/v1/quality-analysis/runs/${encodeURIComponent(runId)}/coaching-summary`,
        { method: "GET" },
        signal,
      );
    },
    startSessionQualityAnalysis(
      sessionId,
      analysisRequest: SessionQualityAnalysisRequest,
      idempotencyKey,
      signal,
    ) {
      return request<SessionQualityAnalysisOutcome>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/quality-analysis-runs`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey,
          },
          body: JSON.stringify(analysisRequest),
        },
        signal,
        true,
      );
    },
    aggregateSessionQuality(
      aggregateRequest: SessionQualityAggregateRequest,
      signal,
    ) {
      return request<SessionQualityAggregate>(
        "/v1/quality-analysis/aggregate",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(aggregateRequest),
        },
        signal,
      );
    },
    aggregateProjectQuality(
      aggregateRequest: ProjectQualityAggregateRequest,
      signal,
    ) {
      return request<ProjectQualityAggregate>(
        "/v1/quality-analysis/aggregate-projects",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(aggregateRequest),
        },
        signal,
      );
    },
    getLatestModelLinkExperiment(sessionId, signal) {
      return request<ModelLinkExperiment>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/model-link-experiments/latest`,
        { method: "GET" },
        signal,
      );
    },
    startModelLinkExperiment(
      sessionId,
      experimentRequest: ModelLinkExperimentRequest,
      idempotencyKey,
      signal,
    ) {
      return request<ModelLinkExperimentOutcome>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/model-link-experiments`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey,
          },
          body: JSON.stringify(experimentRequest),
        },
        signal,
        true,
      );
    },
    annotateModelLink(
      runId,
      linkId,
      annotationRequest: ModelLinkAnnotationRequest,
      signal,
    ) {
      return request<ModelLinkAnnotation>(
        `/v1/model-link-experiments/${encodeURIComponent(runId)}/links/${encodeURIComponent(linkId)}/annotations`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(annotationRequest),
        },
        signal,
        true,
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
