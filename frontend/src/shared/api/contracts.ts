import type { components } from "./generated/openapi";

type Schemas = components["schemas"];

export type CandidateSignal = Schemas["CandidateSignalDto"];
export type TaskCandidate = Schemas["TaskCandidateDto"];
export type CandidateListItem = Schemas["CandidateListItemDto"];
export type CandidateListResponse = Schemas["CandidateListResponse"];
export type CandidateDecisionsResponse = Schemas["CandidateDecisionsResponse"];
export type TaskDecision = Schemas["TaskDecisionDto"];
export type DecisionRevisionLink = Schemas["DecisionRevisionLinkDto"];
export type TaskRevision = Schemas["TaskRevisionDto"];
export type TaskRevisionResponse = Schemas["TaskRevisionResponse"];
export type TaskRevisionListResponse = Schemas["TaskRevisionListResponse"];
export type TaskLifecycleState = Schemas["TaskLifecycleState"];
export type TaskLifecycleEvent = Schemas["TaskLifecycleEventDto"];
export type TaskLifecycleSnapshot = Schemas["TaskLifecycleSnapshotDto"];
export type TaskLifecycleListResponse = Schemas["TaskLifecycleListResponse"];
export type TaskLifecycleMutationResponse = Schemas["TaskLifecycleMutationResponse"];
export type AnalysisRun = Schemas["AnalysisRunDto"];
export type AnalysisResult = Schemas["AnalysisResultDto"];
export type AnalysisRunListResponse = Schemas["AnalysisRunListResponse"];
export type AnalysisRunResponse = Schemas["AnalysisRunResponse"];
export type ControlPlaneReadiness = Schemas["ControlPlaneReadiness"];
export type ControlPlaneReadinessGap = Schemas["ReadinessGap"];
export type SessionAnalysisRun = Schemas["SessionAnalysisRunDto"];
export type SessionAnalysisResult = Schemas["SessionAnalysisResultDto"];
export type SessionAnalysisEvidence = Schemas["SessionAnalysisEvidenceDto"];
export type SessionAnalysisSignal = Schemas["SessionAnalysisSignalDto"];
export type SessionMetricFraction = Schemas["SessionMetricFractionDto"];
export type SessionMetricScopeState = Schemas["SessionMetricScopeState"];
export type SessionQualityCompatibilityKey =
  Schemas["SessionQualityCompatibilityKey"];
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

export interface ContentFreeListPage {
  limit: number;
  offset: number;
}

export type VerificationKind = Schemas["VerificationKind"];
export type VerificationCapability = Schemas["VerificationCapability"];
export type CodexLocalSourceStatus = Schemas["CodexLocalSourceStatus"];
export type ClaudeCodeLocalSourceStatus = Schemas["ClaudeCodeLocalSourceStatus"];
export type IngestionReport = Schemas["IngestionReport"];
export type SessionTranscript = Schemas["SessionTranscript"];
export type SessionTimeline = Schemas["SessionTimeline"];
export type ProjectTimeline = Schemas["ProjectTimeline"];
export type LocalModelsOverview = Schemas["LocalModelsOverview"];
export type LocalModelStatus = Schemas["LocalModelStatus"];
export type LocalModelRecord = Schemas["LocalModelRecord"];
export type AddLocalModel = Schemas["AddLocalModel"];
export type ActivateLocalModel = Schemas["ActivateLocalModel"];
export type DownloadRequest = Schemas["DownloadRequest"];
export type DownloadStatus = Schemas["DownloadStatus"];
export type RemoteRepoFiles = Schemas["RemoteRepoFiles"];
export type ScanFolderResult = Schemas["ScanFolderResult"];

/** One turn sent to a local model's loopback endpoint (OpenAI chat shape). */
export type LocalModelChatMessage = { role: "system" | "user" | "assistant"; content: string };
export type LocalModelChatRequest = {
  messages: LocalModelChatMessage[];
  temperature?: number;
  max_tokens?: number;
  /** Qwen-style thinking; off by default so small tasks answer quickly. */
  enable_thinking?: boolean;
};
/** A streamed fragment: visible answer text and, when the model thinks aloud, its reasoning. */
export type LocalModelChatDelta = { content?: string; reasoning?: string };
export type LocalModelChatResult = {
  content: string;
  reasoning: string;
  finish_reason: string | null;
  elapsed_ms: number;
};
export type DeviceMode = Schemas["DeviceMode"];
export type JudgeOutcome = Schemas["JudgeOutcome"];
export type JudgeSweepStatus = Schemas["JudgeSweepStatus"];
export type JudgeAgreementReport = Schemas["JudgeAgreementReport"];
export type AnnotationAllowance = Schemas["AllowanceState"];
export type AnnotationMetaprompt = Schemas["Metaprompt"];
export type RemoteAnnotationResult = Schemas["RemoteSubmitResult"];
export type SessionJudgments = Schemas["SessionJudgments"];
export type SessionInterpretation = Schemas["SessionInterpretation"];
export type PromptCheckRequest = Schemas["PromptCheckRequest"];
export type PromptCheckResult = Schemas["PromptCheckResult"];
export type PromptCheckRecord = Schemas["PromptCheckRecord"];
export type PromptCheckHistory = Schemas["PromptCheckHistory"];
export type AgentSettings = Schemas["AgentSettings"];
export type AgentSessionView = Schemas["AgentSessionView"];
export type AgentEvents = Schemas["AgentEvents"];
export type AgentEvent = Schemas["AgentEvent"];
export type OnboardingStatus = Schemas["OnboardingStatus"];
export type ProviderDetection = Schemas["ProviderDetection"];
export type OnboardingAccept = Schemas["OnboardingAccept"];
export type OnboardingResult = Schemas["OnboardingResult"];
export type CalibrationSample = Schemas["CalibrationSample"];
export type CalibrationSampleMember = Schemas["CalibrationSampleMember"];
export type CalibrationRating = Schemas["CalibrationRating"];
export type CalibrationProgress = Schemas["CalibrationProgress"];
export type CalibrationExport = Schemas["CalibrationExport"];
export type RatingSubmission = Schemas["RatingSubmission"];
export type RatingLabel = Schemas["RatingLabel"];
export type SessionTranscriptTurn = Schemas["ReaderTurn"];
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
export type MetricCoverageMetric = Schemas["MetricCoverageMetric"];
export type MetricCoverageReport = Schemas["MetricCoverageReport"];
export type MetricCoverageScope = Schemas["MetricCoverageScope"];
export type MetricResultStateCounts = Schemas["MetricResultStateCounts"];
export type SessionMetricReadinessReport =
  Schemas["SessionMetricReadinessReport"];
export type TextAnalysisPresetId = Schemas["TextAnalysisPresetId"];

export type CodexSession = Schemas["SessionCatalogItemDto"];
/** Provider-neutral name for the same catalog row; `CodexSession` is the legacy alias. */
export type SessionCatalogItem = Schemas["SessionCatalogItemDto"];

/** Every provider whose sessions can appear in the local catalog. */
export const LOCAL_PROVIDERS = ["codex", "claude_code", "synthetic"] as const;
export type LocalProvider = (typeof LOCAL_PROVIDERS)[number];

export function isLocalProvider(value: unknown): value is LocalProvider {
  return typeof value === "string" && (LOCAL_PROVIDERS as readonly string[]).includes(value);
}

/** Human label for a provider; never derived from session content. */
export function providerLabel(provider: unknown): string {
  switch (provider) {
    case "codex":
      return "Codex";
    case "claude_code":
      return "Claude Code";
    case "synthetic":
      return "Synthetic";
    default:
      return "Unknown source";
  }
}
export type CodexSessionListResponse = Schemas["SessionCatalogListResponse"];
export type ProjectSessionListResponse =
  Schemas["ProjectSessionCatalogResponse"];
export type TextAnalysisResearchCatalog =
  Schemas["TextAnalysisResearchCatalogDto"];
export type ModelRuntimeInventory = Schemas["ModelRuntimeInventoryDto"];
export type ModelCompatibilityCatalog =
  Schemas["ModelCompatibilityCatalogDto"];
export type ModelCompatibilityEntry = Schemas["ModelCompatibilityEntryDto"];
export type ModelEvaluationRequest = Schemas["ModelEvaluationRequestDto"];
export type ModelEvaluationJob = Schemas["ModelEvaluationJobDto"];
export type ModelLabInventory = Schemas["ModelLabInventoryDto"];
export type ModelLabPlanSummary = Schemas["ModelLabPlanSummaryDto"];
export type ModelLinkExperiment = Schemas["ModelLinkExperimentDto"];
export type ModelLinkExperimentRequest = Schemas["ModelLinkExperimentRequest"];
export type ModelLinkExperimentOutcome =
  Schemas["ModelLinkExperimentCommandResponse"];
export type ModelLinkAnnotation = Schemas["ModelLinkAnnotationDto"];
export type ModelLinkAnnotationRequest = Schemas["ModelLinkAnnotationRequest"];
export type ModelEnsembleRequest = Schemas["ModelEnsembleRequest"];
export type ModelEnsembleRun = Schemas["ModelEnsembleRunDto"];
export type MetricEvidenceReadinessProjectionV2 =
  Schemas["MetricEvidenceReadinessProjectionV2"];
export type MetricEvidenceReadinessV2 = Schemas["MetricEvidenceReadinessV2"];
export type MetricEvidenceContributor = Schemas["MetricEvidenceContributor"];
export type MetricEvidenceAvailabilityState =
  Schemas["MetricEvidenceAvailabilityState"];
export type AgentMetricEvidencePreview = Schemas["AgentMetricEvidencePreviewDto"];
export type AgentMetricEvidenceImport = Schemas["AgentMetricEvidenceImportDto"];
export type MetricLifecycleProposal = Schemas["MetricLifecycleProposalDto"];
export type MetricLifecycleProposalList = Schemas["MetricLifecycleProposalListDto"];
export type MetricLifecycleProposalPage = Schemas["MetricLifecycleProposalPageDto"];
export type MetricLifecycleProposalOutcome = Schemas["MetricLifecycleProposalOutcomeDto"];
export type MetricLifecycleDecisionRequest = Schemas["MetricLifecycleDecisionCommand"];
export interface MetricLifecycleProposalCollection {
  session_id: string;
  proposals: MetricLifecycleProposal[];
  total: number;
  complete: boolean;
}
export type CapabilityKey = Schemas["CapabilityKey"];
export type ModelEnsembleOutcome = Schemas["ModelEnsembleOutcomeDto"];
export type ModelEnsembleWatchRequest = Schemas["ModelEnsembleWatchRequest"];
export type ModelEnsembleWatch = Schemas["ModelEnsembleWatchDto"];
export type ModelEnsembleWatchSnapshot = Schemas["ModelEnsembleWatchSnapshotDto"];
export type ModelEnsembleTrajectoryPage = Schemas["ModelEnsembleTrajectoryPage"];
export type ModelEnsembleTrajectoryPoint = Schemas["ModelEnsembleTrajectoryPoint"];
export type ModelPredictiveMetricDetail = Schemas["ModelPredictiveMetricDetailDto"];

export interface ModelEnsembleAttempt {
  attempt_id: string;
  watch_id: string;
  generation: number;
  state: "running" | "completed" | "partial" | "failed" | "cancelled";
  prior_head_run_id: string | null;
  published_run_id: string | null;
  progress_completed: number;
  progress_total: number;
  stage_count: number;
  warning_count: number;
  error_code: string | null;
  requested_at: string;
  started_at: string;
  completed_at: string | null;
  content_persisted: false;
}

export interface ModelEnsembleAttemptStage {
  stage_ordinal: number;
  stage_key: string;
  state: "completed" | "unavailable" | "resource_exhausted" | "failed" | "cancelled";
  model_key: string | null;
  repository_id: string | null;
  revision: string | null;
  error_code: string | null;
  device: "cpu" | "cuda" | "mps" | null;
  quantization: "none" | "bitsandbytes_nf4";
  inference_latency_ms: number | null;
  peak_accelerator_memory_mb: number | null;
  process_rss_mb: number | null;
  evaluated_case_count: number | null;
  contributed_case_count: number | null;
  unloaded_after_stage: boolean | null;
  completed_at: string;
}

export interface ModelEnsembleCanonicalHead {
  schema_version: "analysis-snapshot-v2";
  watch: ModelEnsembleWatch;
  head_run_id: string | null;
  head_generation: number | null;
  latest_attempt: ModelEnsembleAttempt | null;
  stages: ModelEnsembleAttemptStage[];
  content_persisted: false;
}

export interface ModelEnsembleAttemptSnapshot {
  attempt: ModelEnsembleAttempt;
  stages: ModelEnsembleAttemptStage[];
}

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
export interface ReviewedAutomationResourcePolicyRequest {
  route: "balanced";
  max_gpu_workers: 1;
  max_cpu_workers: 1;
  pause_on_battery: true;
  maximum_session_seconds: 1_800;
}
export interface AutomationGrantCreateRequest extends Omit<
  Schemas["AutomationGrantCreateRequest"],
  "resource_policy"
> {
  resource_policy: ReviewedAutomationResourcePolicyRequest;
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
export interface AutomationPollResult {
  grants_checked: number;
  grants_revoked: number;
  grants_power_paused: number;
  grants_policy_unsupported: number;
  power_external_observations: number;
  power_battery_observations: number;
  power_unknown_observations: number;
  candidates_seen: number;
  jobs_created: number;
  jobs_reused: number;
  jobs_superseded: number;
  failures: number;
  maximum_session_runtime_deadline_enforced: false;
  session_quality_result_publication_deadline_enforced: true;
  blocking_execution_preemption_enforced: false;
}

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
      /** True only when the owner enabled the on-demand session reader. */
      raw_transcripts: boolean;
    }
  | {
      available: false;
      reason_code: SessionTextAnalysisUnavailableReason;
      data_tier: null;
      content_persistence: false;
      network_inference: false;
      raw_transcripts: boolean;
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
  capability: "session_text_analysis" | "operational_events";
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
  /**
   * Read the optional, default-off loopback development control-plane status.
   * This never carries the separate credential used by privileged data routes.
   */
  getControlPlaneReadiness(signal?: AbortSignal): Promise<ControlPlaneReadiness>;
  getTextAnalysisResearch?(
    signal?: AbortSignal,
  ): Promise<TextAnalysisResearchCatalog>;
  getTextModelRuntime?(signal?: AbortSignal): Promise<ModelRuntimeInventory>;
  getTextModelCompatibility?(
    signal?: AbortSignal,
  ): Promise<ModelCompatibilityCatalog>;
  getModelLabInventory?(signal?: AbortSignal): Promise<ModelLabInventory>;
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
  getMetricCoverage(
    provider: Provider,
    signal?: AbortSignal,
  ): Promise<MetricCoverageReport>;
  getProjectMetricCoverage(
    projectId: string,
    provider: Provider,
    signal?: AbortSignal,
  ): Promise<MetricCoverageReport>;
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
  /** Owner-authorized on-demand read of one session (ADR 0011); nothing is stored. */
  getSessionTranscript(sessionId: string, signal?: AbortSignal): Promise<SessionTranscript>;
  /** Deterministic, content-free timeline of one session's indexed events. */
  getSessionTimeline(sessionId: string, signal?: AbortSignal): Promise<SessionTimeline>;
  /** Sessions and reviewed task windows of one project over calendar time. */
  getProjectTimeline(projectId: string, signal?: AbortSignal): Promise<ProjectTimeline>;
  /** Local model runtimes (ADR 0013): registry, activation on cpu/gpu/split, per-model endpoint. */
  getLocalModels(signal?: AbortSignal): Promise<LocalModelsOverview>;
  addLocalModel(request: AddLocalModel, signal?: AbortSignal): Promise<LocalModelRecord>;
  activateLocalModel(alias: string, request: ActivateLocalModel, signal?: AbortSignal): Promise<LocalModelStatus>;
  deactivateLocalModel(alias: string, signal?: AbortSignal): Promise<LocalModelStatus>;
  removeLocalModel(alias: string, deleteWeights: boolean, signal?: AbortSignal): Promise<void>;
  getLocalModelRemoteFiles(repoId: string, signal?: AbortSignal): Promise<RemoteRepoFiles>;
  startLocalModelDownload(request: DownloadRequest, signal?: AbortSignal): Promise<DownloadStatus>;
  /** Register every GGUF found in a folder (one level deep). */
  scanLocalModelFolder(path: string, signal?: AbortSignal): Promise<ScanFolderResult>;
  /** Stream one chat completion from a running local model; `onDelta` receives fragments as they arrive. */
  streamLocalModelChat(
    alias: string,
    request: LocalModelChatRequest,
    onDelta: (delta: LocalModelChatDelta) => void,
    signal?: AbortSignal,
  ): Promise<LocalModelChatResult>;
  /** Model-judge lane: the active local model answers the calibration questions (judgments, not metrics). */
  judgeSessionWithModel(sessionId: string, signal?: AbortSignal): Promise<JudgeOutcome>;
  /** Stored judgments for one session (labels only; never metric values). */
  getModelJudgments(sessionId: string, signal?: AbortSignal): Promise<SessionJudgments>;
  /** Plain-language reading of a session's metrics by the local model (commentary, not a metric). */
  interpretSessionWithModel(sessionId: string, signal?: AbortSignal): Promise<SessionInterpretation>;
  /** Prompt check (ADR 0015): validate a prompt in context; only metrics are stored. */
  checkPrompt(request: PromptCheckRequest, signal?: AbortSignal): Promise<PromptCheckResult>;
  getPromptCheckHistory(limit: number, offset: number, signal?: AbortSignal): Promise<PromptCheckHistory>;
  getPromptCheck(checkId: string, signal?: AbortSignal): Promise<PromptCheckRecord>;
  /** Local agent workspace (ADR 0016): sessions, turns, events, approvals. */
  listAgentSessions(signal?: AbortSignal): Promise<AgentSessionView[]>;
  createAgentSession(settings: AgentSettings, signal?: AbortSignal): Promise<AgentSessionView>;
  getAgentSession(sessionId: string, signal?: AbortSignal): Promise<AgentSessionView>;
  deleteAgentSession(sessionId: string, signal?: AbortSignal): Promise<void>;
  sendAgentMessage(sessionId: string, text: string, signal?: AbortSignal): Promise<AgentSessionView>;
  getAgentEvents(sessionId: string, after: number, signal?: AbortSignal): Promise<AgentEvents>;
  decideAgentApproval(sessionId: string, approvalId: string, approved: boolean, signal?: AbortSignal): Promise<AgentSessionView>;
  stopAgentSession(sessionId: string, signal?: AbortSignal): Promise<AgentSessionView>;
  startModelJudgeSweep(signal?: AbortSignal, scope?: "sample" | "all"): Promise<JudgeSweepStatus>;
  getModelJudgeSweep(signal?: AbortSignal): Promise<JudgeSweepStatus>;
  getModelJudgeAgreement(signal?: AbortSignal): Promise<JudgeAgreementReport>;
  /** Annotation paths (ADR 0017): agent allowance switch, metaprompt, and the explicit "annotate remotely" action. */
  getAnnotationAllowance(signal?: AbortSignal): Promise<AnnotationAllowance>;
  setAnnotationAllowance(agentAllowed: boolean, signal?: AbortSignal): Promise<AnnotationAllowance>;
  getAnnotationMetaprompt(signal?: AbortSignal): Promise<AnnotationMetaprompt>;
  annotateRemotely(limit: number, signal?: AbortSignal): Promise<RemoteAnnotationResult>;
  getOnboardingStatus(signal?: AbortSignal): Promise<OnboardingStatus>;
  acceptOnboarding(request: OnboardingAccept, signal?: AbortSignal): Promise<OnboardingResult>;
  /** Blind calibration ratings over a frozen sample of the owner's own sessions. */
  getCalibrationSample(raterLabel: string | null, signal?: AbortSignal): Promise<CalibrationSample>;
  submitCalibrationRatings(request: RatingSubmission, signal?: AbortSignal): Promise<CalibrationProgress>;
  getCalibrationRatings(raterLabel: string, signal?: AbortSignal): Promise<CalibrationRating[]>;
  getCalibrationProgress(signal?: AbortSignal): Promise<CalibrationProgress>;
  getCalibrationExport(signal?: AbortSignal): Promise<CalibrationExport>;
  getClaudeLocalSourceStatus(signal?: AbortSignal): Promise<ClaudeCodeLocalSourceStatus>;
  grantClaudeLocalHistoryConsent(signal?: AbortSignal): Promise<ClaudeCodeLocalSourceStatus>;
  revokeClaudeLocalHistoryConsent(signal?: AbortSignal): Promise<ClaudeCodeLocalSourceStatus>;
  indexClaudeLocalSessions(
    maxSessions: number,
    signal?: AbortSignal,
  ): Promise<IngestionReport>;
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
  getLatestModelEnsemble(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<ModelEnsembleRun>;
  startModelEnsemble(
    sessionId: string,
    request: ModelEnsembleRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<ModelEnsembleOutcome>;
  getActiveModelEnsembleWatch?(
    signal?: AbortSignal,
  ): Promise<ModelEnsembleWatchSnapshot>;
  getActiveModelEnsembleCanonicalHead?(
    signal?: AbortSignal,
  ): Promise<ModelEnsembleCanonicalHead>;
  getSessionModelEnsembleCanonicalHead?(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<ModelEnsembleCanonicalHead>;
  getModelEnsembleSnapshot?(
    runId: string,
    signal?: AbortSignal,
  ): Promise<ModelEnsembleRun>;
  enqueueModelEnsembleAnalysis?(
    watchId: string,
    signal?: AbortSignal,
  ): Promise<ModelEnsembleCanonicalHead>;
  cancelModelEnsembleAnalysis?(
    watchId: string,
    signal?: AbortSignal,
  ): Promise<ModelEnsembleCanonicalHead>;
  getModelEnsembleAttempt?(
    attemptId: string,
    signal?: AbortSignal,
  ): Promise<ModelEnsembleAttemptSnapshot>;
  enableModelEnsembleWatch?(
    sessionId: string,
    request: ModelEnsembleWatchRequest,
    signal?: AbortSignal,
  ): Promise<ModelEnsembleWatchSnapshot>;
  disableModelEnsembleWatch?(
    watchId: string,
    signal?: AbortSignal,
  ): Promise<ModelEnsembleWatchSnapshot>;
  refreshModelEnsembleWatch?(
    watchId: string,
    signal?: AbortSignal,
  ): Promise<ModelEnsembleWatchSnapshot>;
  getModelEnsembleTrajectory?(
    watchId: string,
    limit?: number,
    beforeGeneration?: number,
    signal?: AbortSignal,
  ): Promise<ModelEnsembleTrajectoryPage>;
  getModelPredictiveMetricDetail?(
    runId: string,
    metricKey: string,
    signal?: AbortSignal,
  ): Promise<ModelPredictiveMetricDetail>;
  previewAgentMetricEvidence?(
    sessionId: string,
    payload: ArrayBuffer,
    signal?: AbortSignal,
  ): Promise<AgentMetricEvidencePreview>;
  importAgentMetricEvidence?(
    sessionId: string,
    payload: ArrayBuffer,
    expectedPayloadSha256: string,
    confirmation: string,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AgentMetricEvidenceImport>;
  listMetricLifecycleProposals?(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<MetricLifecycleProposalCollection>;
  decideMetricLifecycleProposal?(
    sessionId: string,
    proposalId: string,
    request: MetricLifecycleDecisionRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<MetricLifecycleProposalOutcome>;
  listCandidates(
    status?: CandidateStatusFilter,
    signal?: AbortSignal,
    page?: ContentFreeListPage,
  ): Promise<CandidateListResponse>;
  listTaskRevisions(
    taskId?: string,
    signal?: AbortSignal,
    page?: ContentFreeListPage,
  ): Promise<TaskRevisionListResponse>;
  getCandidateDecisions(
    candidateId: string,
    signal?: AbortSignal,
  ): Promise<CandidateDecisionsResponse>;
  getTaskRevision(
    taskId: string,
    revision: number,
    signal?: AbortSignal,
  ): Promise<TaskRevisionResponse>;
  listTaskLifecycles(
    signal?: AbortSignal,
    page?: ContentFreeListPage,
    eventLimit?: number,
  ): Promise<TaskLifecycleListResponse>;
  getTaskLifecycle(
    taskId: string,
    revision: number,
    eventLimit?: number,
    eventOffset?: number,
    signal?: AbortSignal,
  ): Promise<TaskLifecycleSnapshot>;
  transitionTaskLifecycle(
    taskId: string,
    revision: number,
    expectedHeadEventId: string | null,
    state: TaskLifecycleState,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<TaskLifecycleMutationResponse>;
  correctTaskLifecycle(
    taskId: string,
    revision: number,
    expectedHeadEventId: string,
    expectedPriorState: TaskLifecycleState | null,
    expectedResultingState: TaskLifecycleState | null,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<TaskLifecycleMutationResponse>;
  listAnalysisRuns(
    taskId?: string,
    signal?: AbortSignal,
    page?: ContentFreeListPage,
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
