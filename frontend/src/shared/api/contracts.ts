import type { components } from "./generated/openapi";

type Schemas = components["schemas"];

export type CandidateSignal = Schemas["CandidateSignalDto"];
export type TaskCandidate = Schemas["TaskCandidateDto"];
export type CandidateListItem = Schemas["CandidateListItemDto"];
export type CandidateListResponse = Schemas["CandidateListResponse"];
export type TaskRevision = Schemas["TaskRevisionDto"];
export type TaskRevisionResponse = Schemas["TaskRevisionResponse"];
export type TaskRevisionListResponse = Schemas["TaskRevisionListResponse"];
export type AnalysisRun = Schemas["AnalysisRunDto"];
export type AnalysisResult = Schemas["AnalysisResultDto"];
export type AnalysisRunListResponse = Schemas["AnalysisRunListResponse"];
export type AnalysisRunResponse = Schemas["AnalysisRunResponse"];
export type SessionAnalysisRun = Schemas["SessionAnalysisRunDto"];
export type SessionAnalysisResult = Schemas["SessionAnalysisResultDto"];
export type SessionAnalysisEvidence = Schemas["SessionAnalysisEvidenceDto"];
export type SessionAnalysisSignal = Schemas["SessionAnalysisSignalDto"];
export type SessionMetricFraction = Schemas["SessionMetricFractionDto"];
export type SessionAnalysisRunListResponse =
  Schemas["SessionAnalysisRunListResponse"];
export type SessionAnalysisRunResponse = Schemas["SessionAnalysisRunResponse"];
export type SessionCoachingProjection = Schemas["SessionCoachingProjection"];
export type SessionQualityAggregate = Schemas["SessionQualityAggregate"];
export type SessionQualityMetricAggregate =
  Schemas["SessionQualityMetricAggregate"];
export type SessionQualityAggregateRequest =
  Schemas["SessionQualityAggregateRequest"];
export type ProjectQualityAggregate = Schemas["ProjectQualityAggregate"];
export type ProjectQualityAggregateRequest =
  Schemas["ProjectQualityAggregateRequest"];
export type ProjectSessionQualityAggregate =
  Schemas["ProjectSessionQualityAggregate"];
export type ProjectQualityMetricAggregate =
  Schemas["ProjectQualityMetricAggregate"];
export type ProjectQualityCompatibilityCohort =
  Schemas["ProjectQualityCompatibilityCohort"];
export type TaskReviewResponse = Schemas["TaskReviewResponse"];
export type TaskAnalysisResponse = Schemas["TaskAnalysisResponse"];
export type TaskCategory = Schemas["AcceptTaskRequest"]["task_category"];
export type RejectionReason = Schemas["RejectTaskRequest"]["reason"];

export type ReviewCommand =
  | { action: "accept"; request: Schemas["AcceptTaskRequest"] }
  | { action: "reject"; request: Schemas["RejectTaskRequest"] }
  | { action: "merge"; request: Schemas["MergeTasksRequest"] }
  | { action: "split"; request: Schemas["SplitTaskRequest"] };

export type CandidateStatusFilter = "all" | "undecided" | "decided";

export type VerificationKind = Schemas["VerificationKind"];
export type VerificationCapability = Schemas["VerificationCapability"];
export type CodexLocalSourceStatus = Schemas["CodexLocalSourceStatus"];
export type Provider = Schemas["Provider"];
export type ProviderCapabilityReport = Schemas["ProviderCapabilityReport"];
export type ProviderMetricCapability = Schemas["ProviderMetricCapability"];
export type ProviderMetricCapabilityReason =
  Schemas["ProviderMetricCapabilityReason"];
export type ProviderMetricCapabilityState =
  Schemas["ProviderMetricCapabilityState"];
export type MetricEvidenceCapability = Schemas["MetricEvidenceCapability"];
export type MetricReadiness = Schemas["MetricReadiness"];
export type MetricReadinessAction = Schemas["MetricReadinessAction"];
export type MetricReadinessReason = Schemas["MetricReadinessReason"];
export type MetricReadinessState = Schemas["MetricReadinessState"];
export type MetricRadarPolicy = Schemas["MetricRadarPolicy"];
export type SessionMetricReadinessReport =
  Schemas["SessionMetricReadinessReport"];
export type TextAnalysisPresetId = Schemas["TextAnalysisPresetId"];

export type CodexSession = Schemas["SessionCatalogItemDto"];
export type CodexSessionListResponse = Schemas["SessionCatalogListResponse"];
export type ProjectSessionListResponse =
  Schemas["ProjectSessionCatalogResponse"];
export type TextAnalysisResearchCatalog =
  Schemas["TextAnalysisResearchCatalogDto"];
export type ModelRuntimeInventory = Schemas["ModelRuntimeInventoryDto"];
export type ModelEvaluationRequest = Schemas["ModelEvaluationRequestDto"];
export type ModelEvaluationJob = Schemas["ModelEvaluationJobDto"];
export type ModelLinkExperiment = Schemas["ModelLinkExperimentDto"];
export type ModelLinkExperimentRequest = Schemas["ModelLinkExperimentRequest"];
export type ModelLinkExperimentOutcome =
  Schemas["ModelLinkExperimentCommandResponse"];
export type ModelLinkAnnotation = Schemas["ModelLinkAnnotationDto"];
export type ModelLinkAnnotationRequest = Schemas["ModelLinkAnnotationRequest"];

export interface SessionMetric {
  key: string;
  version: number;
  dimension: string;
  display_name: string;
  numeric_value: number | null;
  text_value: string | null;
  unit: string | null;
  source: string;
  observed_count: number;
  eligible_count: number;
  coverage: number;
  confidence: number | null;
  metric_pack_key: string;
  metric_pack_version: number;
  metric_engine_version: string;
  redactor_version: string | null;
  model_id: string | null;
  model_revision: string | null;
  tokenizer_id: string | null;
  prompt_version: string | null;
  rubric_version: string | null;
  computed_at: string;
}

export interface SessionMetricResponse {
  session_id: string;
  metrics: SessionMetric[];
}

export type AnalysisJobKind = Schemas["AnalysisJobKind"];
export type AnalysisJobState = Schemas["AnalysisJobState"];

export interface AnalysisJobIdentity extends Omit<
  Schemas["AnalysisJobIdentity"],
  "automation_grant_id" | "local_only"
> {
  automation_grant_id: string | null;
  local_only: true;
}

/**
 * Validated browser-safe projection. The generated public DTO never includes
 * an internal dedupe key or worker lease credentials.
 */
export interface AnalysisJobRecord extends Omit<
  Schemas["AnalysisJobResponse"],
  "identity"
> {
  identity: AnalysisJobIdentity;
}

export interface AnalysisJobPage extends Omit<
  Schemas["AnalysisJobPageResponse"],
  "jobs"
> {
  jobs: AnalysisJobRecord[];
}

export type AutomationGrantState = Schemas["AutomationGrantState"];
export type AutomationRoute = Schemas["AutomationRoute"];
export type AutomationResourcePolicy = Schemas["AutomationResourcePolicy"];
export interface AutomationGrantCreateRequest extends Omit<
  Schemas["AutomationGrantCreateRequest"],
  "resource_policy"
> {
  resource_policy: AutomationResourcePolicy;
}
export interface AutomationGrantScope extends Omit<
  Schemas["AutomationGrantScope"],
  "resource_policy"
> {
  resource_policy: AutomationResourcePolicy;
}
export interface AutomationGrantRecord extends Omit<
  Schemas["AutomationGrantRecord"],
  "last_checked_at" | "last_error_code" | "revoked_at" | "scope"
> {
  last_checked_at: string | null;
  last_error_code: string | null;
  revoked_at: string | null;
  scope: AutomationGrantScope;
}
export type AutomationPollResult = Schemas["AutomationPollResult"];

export type SessionQualityAnalysisRequest =
  Schemas["SessionTextAnalysisRequest"];
export type SessionQualityAnalysisOutcome =
  Schemas["SessionTextAnalysisCommandResponse"];
export type RedactionPreviewBinding = Schemas["RedactionPreviewBinding"];
export type SessionQualityAnalysisPreviewRequest =
  Schemas["SessionTextAnalysisPreviewRequest"];
export type SessionQualityAnalysisPreview =
  Schemas["SessionTextAnalysisPreviewResponse"];
export type SessionQualityAnalysisPreviewApprovalRequest =
  Schemas["SessionTextAnalysisPreviewApprovalRequest"];

export type SessionTextAnalysisUnavailableReason =
  | "analysis_service_unavailable"
  | "local_source_unavailable"
  | "redacted_content_consent_required"
  | "consent_status_invalid"
  | "capability_response_invalid"
  | "synthetic_preview";

/**
 * Content-free projection of the server capability response. The HTTP adapter
 * validates all privacy invariants before constructing this value.
 */
export type SessionTextAnalysisCapability =
  | {
      available: true;
      reason_code: "available";
      data_tier: "redacted_content";
      content_persistence: false;
      network_inference: false;
      raw_transcripts: false;
    }
  | {
      available: false;
      reason_code: SessionTextAnalysisUnavailableReason;
      data_tier: null;
      content_persistence: false;
      network_inference: false;
      raw_transcripts: false;
    };

export type ProviderCompatibilityProvider = "codex" | "claude_code" | "synthetic";
export type ProviderCompatibilityState =
  | "exact"
  | "compatible"
  | "degraded"
  | "untested"
  | "incompatible"
  | "unavailable";
export type ProviderTextCapabilityState = "supported" | "unsupported" | "unknown";
export type ProviderCompatibilityReason =
  | "exact_match"
  | "compatible_version"
  | "degraded_extraction"
  | "not_checked"
  | "provider_unavailable"
  | "provider_version_unsupported"
  | "adapter_outdated"
  | "source_schema_unsupported"
  | "content_schema_unsupported"
  | "check_failed";
export type ProviderUpdateSupport = "supported" | "unsupported" | "unknown";
export type ProviderUpdateTarget = "prompt_enhancer" | "provider";

/** Content-free, closed projection of one provider compatibility check. */
export interface ProviderCompatibilityStatus {
  provider: ProviderCompatibilityProvider;
  capability: "session_text_analysis";
  state: ProviderCompatibilityState;
  capability_state: ProviderTextCapabilityState;
  provider_family: string;
  provider_version: string | null;
  adapter_family: string;
  adapter_version: string | null;
  source_schema_family: string;
  source_schema_version: string | null;
  content_schema_family: string;
  content_schema_version: string | null;
  reason_code: ProviderCompatibilityReason;
  checked_at: string | null;
  update_support: ProviderUpdateSupport;
  update_target: ProviderUpdateTarget | null;
}

export interface CodexIngestionReport {
  provider: "codex";
  sessions_seen: number;
  sessions_selected: number;
  sessions_inserted: number;
  sessions_updated: number;
  events_seen: number;
  events_inserted: number;
  events_updated: number;
  metrics_written: number;
  truncated: boolean;
}

export interface CodexAnalysisSelection {
  project_ids: string[];
  session_ids: string[];
  max_sessions: number;
}

export interface CodexLabelEnrichmentReport {
  provider: "codex";
  requested_sessions: number;
  matched_sessions: number;
  summary_reads: number;
  project_labels_filled: number;
  session_labels_filled: number;
  labels_unavailable: number;
  sessions_not_found: number;
  truncated: boolean;
}

export interface ManualDisplayLabelResult {
  entity_kind: "project" | "session";
  entity_id: string;
  revision: number;
  changed: boolean;
}

export type DisplayLabelEntityKind = "project" | "session";

export interface PromptEnhancerTransport {
  getTextAnalysisResearch?(
    signal?: AbortSignal,
  ): Promise<TextAnalysisResearchCatalog>;
  getTextModelRuntime?(signal?: AbortSignal): Promise<ModelRuntimeInventory>;
  startTextModelEvaluation?(
    request: ModelEvaluationRequest,
    signal?: AbortSignal,
  ): Promise<ModelEvaluationJob>;
  getTextModelEvaluation?(
    jobId: string,
    signal?: AbortSignal,
  ): Promise<ModelEvaluationJob>;
  getSessionTextAnalysisCapability(
    signal?: AbortSignal,
  ): Promise<SessionTextAnalysisCapability>;
  getProviderCompatibility?(
    provider: ProviderCompatibilityProvider,
    signal?: AbortSignal,
  ): Promise<ProviderCompatibilityStatus>;
  getProviderMetricCapabilities(
    provider: Provider,
    signal?: AbortSignal,
  ): Promise<ProviderCapabilityReport>;
  getSessionMetricReadiness(
    sessionId: string,
    presetId?: TextAnalysisPresetId,
    signal?: AbortSignal,
  ): Promise<SessionMetricReadinessReport>;
  checkProviderCompatibility?(
    provider: ProviderCompatibilityProvider,
    signal?: AbortSignal,
  ): Promise<ProviderCompatibilityStatus>;
  getCodexLocalSourceStatus(signal?: AbortSignal): Promise<CodexLocalSourceStatus>;
  grantCodexLocalHistoryConsent(signal?: AbortSignal): Promise<CodexLocalSourceStatus>;
  revokeCodexLocalHistoryConsent(signal?: AbortSignal): Promise<CodexLocalSourceStatus>;
  indexCodexLocalSessions(
    maxSessions: number,
    signal?: AbortSignal,
  ): Promise<CodexIngestionReport>;
  analyzeCodexLocalSessions(
    selection: CodexAnalysisSelection,
    signal?: AbortSignal,
  ): Promise<CodexIngestionReport>;
  enrichCodexDisplayLabels(
    selection: CodexAnalysisSelection,
    signal?: AbortSignal,
  ): Promise<CodexLabelEnrichmentReport>;
  setManualDisplayLabel(
    entityKind: DisplayLabelEntityKind,
    entityId: string,
    value: string,
    expectedRevision: number,
    signal?: AbortSignal,
  ): Promise<ManualDisplayLabelResult>;
  clearManualDisplayLabel(
    entityKind: DisplayLabelEntityKind,
    entityId: string,
    expectedRevision: number,
    signal?: AbortSignal,
  ): Promise<ManualDisplayLabelResult>;
  listCodexSessions(
    limit?: number,
    offset?: number,
    signal?: AbortSignal,
  ): Promise<CodexSessionListResponse>;
  listProjectSessions(
    projectId: string,
    limit?: number,
    offset?: number,
    signal?: AbortSignal,
  ): Promise<ProjectSessionListResponse>;
  getSessionMetrics(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<SessionMetricResponse>;
  listAnalysisJobs(
    state?: AnalysisJobState | null,
    limit?: number,
    offset?: number,
    signal?: AbortSignal,
  ): Promise<AnalysisJobPage>;
  getAnalysisJob(
    jobId: string,
    signal?: AbortSignal,
  ): Promise<AnalysisJobRecord>;
  getLatestSessionAnalysisJob(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<AnalysisJobRecord>;
  cancelAnalysisJob(
    jobId: string,
    signal?: AbortSignal,
  ): Promise<AnalysisJobRecord>;
  listAutomationGrants(
    provider: Provider,
    activeOnly?: boolean,
    signal?: AbortSignal,
  ): Promise<AutomationGrantRecord[]>;
  getAutomationGrant(
    grantId: string,
    expectedScope: AutomationGrantScope,
    signal?: AbortSignal,
  ): Promise<AutomationGrantRecord>;
  createAutomationGrant(
    request: AutomationGrantCreateRequest,
    signal?: AbortSignal,
  ): Promise<AutomationGrantRecord>;
  renewAutomationGrant(
    grantId: string,
    expectedScope: AutomationGrantScope,
    signal?: AbortSignal,
  ): Promise<AutomationGrantRecord>;
  revokeAutomationGrant(
    grantId: string,
    expectedScope: AutomationGrantScope,
    signal?: AbortSignal,
  ): Promise<AutomationGrantRecord>;
  pollAutomationGrants(signal?: AbortSignal): Promise<AutomationPollResult>;
  getLatestSessionQualityAnalysis(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<SessionAnalysisRunResponse>;
  getSessionQualityAnalysisRun(
    runId: string,
    signal?: AbortSignal,
  ): Promise<SessionAnalysisRunResponse>;
  getSessionCoachingSummary?(
    runId: string,
    signal?: AbortSignal,
  ): Promise<SessionCoachingProjection>;
  startSessionQualityAnalysis(
    sessionId: string,
    request: SessionQualityAnalysisRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<SessionQualityAnalysisOutcome>;
  prepareSessionQualityAnalysisPreview(
    sessionId: string,
    request: SessionQualityAnalysisPreviewRequest,
    signal?: AbortSignal,
  ): Promise<SessionQualityAnalysisPreview>;
  approveSessionQualityAnalysisPreview(
    previewId: string,
    request: SessionQualityAnalysisPreviewApprovalRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<SessionQualityAnalysisOutcome>;
  aggregateSessionQuality(
    request: SessionQualityAggregateRequest,
    signal?: AbortSignal,
  ): Promise<SessionQualityAggregate>;
  aggregateProjectQuality(
    request: ProjectQualityAggregateRequest,
    signal?: AbortSignal,
  ): Promise<ProjectQualityAggregate>;
  getLatestModelLinkExperiment(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<ModelLinkExperiment>;
  startModelLinkExperiment(
    sessionId: string,
    request: ModelLinkExperimentRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<ModelLinkExperimentOutcome>;
  annotateModelLink(
    runId: string,
    linkId: string,
    request: ModelLinkAnnotationRequest,
    signal?: AbortSignal,
  ): Promise<ModelLinkAnnotation>;
  listCandidates(
    status?: CandidateStatusFilter,
    signal?: AbortSignal,
  ): Promise<CandidateListResponse>;
  listTaskRevisions(
    taskId?: string,
    signal?: AbortSignal,
  ): Promise<TaskRevisionListResponse>;
  getTaskRevision(
    taskId: string,
    revision: number,
    signal?: AbortSignal,
  ): Promise<TaskRevisionResponse>;
  listAnalysisRuns(
    taskId?: string,
    signal?: AbortSignal,
  ): Promise<AnalysisRunListResponse>;
  getAnalysisRun(runId: string, signal?: AbortSignal): Promise<AnalysisRunResponse>;
  review(
    command: ReviewCommand,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<TaskReviewResponse>;
  startAnalysis(
    taskId: string,
    revision: number,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<TaskAnalysisResponse>;
}
