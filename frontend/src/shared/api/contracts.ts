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
export type SharedFolder = Schemas["SharedFolder"];
export type SharedFolderList = Schemas["SharedFolderList"];
export type PeerLink = Schemas["PeerLink"];
export type PeerLinkList = Schemas["PeerLinkList"];
export type FolderSyncReport = Schemas["SyncReport"];
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
export type AgentWorkspaceTree = Schemas["WorkspaceTree"];
export type AgentWorkspaceEntry = Schemas["WorkspaceEntry"];
export type AgentWorkspaceFile = Schemas["WorkspaceFile"];
export type AgentWorkspacePreviewCommand = Schemas["WorkspacePreviewCommand"];
export type AgentWorkspaceEditPreview = Schemas["WorkspaceEditPreview"];
export type AgentWorkspaceApplyCommand = Schemas["WorkspaceApplyCommand"];
export type AgentWorkspaceApplyResult = Schemas["WorkspaceApplyResult"];
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

/**
 * Handwritten strict-narrowing seam over the generated r6 client. It preserves
 * historical projection unions while making the current receipt fields that
 * the runtime always serializes explicit to presentation code.
 */
export type MetricProjectionV2Version =
  | Schemas["MetricStateV2"]["projection_version"]
  | "metric-contract-v2-projection-6"
  | "metric-contract-v2-projection-7";
export type MetricStateV2 = Omit<Schemas["MetricStateV2"], "projection_version"> & {
  projection_version: MetricProjectionV2Version;
};
export type PublishedMetricV2 = Omit<Schemas["PublishedMetricV2"], "state"> & {
  state: MetricStateV2;
};
export type MetricPublicationV2Contract = Omit<
  Schemas["MetricPublicationV2"],
  "projection_version" | "metrics"
> & {
  projection_version: MetricProjectionV2Version;
  metrics: PublishedMetricV2[];
};

export interface ModelRequirementPlanEvidenceBinding {
  evidence_source: "unavailable" | "awaiting_review" | "reviewed_requirement_plan";
  confirmation_id: string | null;
  proposal_id: string | null;
  evidence_fingerprint: string;
  evidence_schema_version:
    | "requirement-plan-unavailable-v1"
    | "requirement-plan-awaiting-review-v1"
    | "requirement-plan-evidence-v1";
  evidence_policy_version: "reviewed-requirement-plan-v1";
  local_only: true;
  content_persisted: false;
}

export interface ModelRequirementActionEvidenceBinding {
  evidence_source:
    | "unavailable"
    | "awaiting_review"
    | "candidate_manifest_overflow"
    | "candidate_source_incomplete"
    | "binding_invalid"
    | "reviewed_requirement_action";
  source_run_id: string | null;
  requirement_plan_confirmation_id: string | null;
  requirement_plan_evidence_fingerprint: string | null;
  candidate_manifest_fingerprint: string | null;
  confirmation_id: string | null;
  proposal_id: string | null;
  reviewed_descriptor_set_fingerprint: string | null;
  evidence_fingerprint: string;
  evidence_schema_version:
    | "requirement-action-unavailable-v1"
    | "requirement-action-awaiting-review-v1"
    | "requirement-action-candidate-manifest-overflow-v1"
    | "requirement-action-candidate-source-incomplete-v1"
    | "requirement-action-binding-invalid-v1"
    | "requirement-action-evidence-v1";
  evidence_policy_version: "reviewed-requirement-action-v1";
  local_only: true;
  content_persisted: false;
}

export type ModelEnsembleRun = Omit<
  Schemas["ModelEnsembleRunDto"],
  | "metric_publication_v2"
  | "metric_evidence_readiness_v2"
  | "requirement_plan_evidence_binding"
  | "requirement_action_evidence_binding"
> & {
  metric_publication_v2: MetricPublicationV2Contract | null;
  metric_evidence_readiness_v2: MetricEvidenceReadinessProjectionV2 | null;
  requirement_plan_evidence_binding: ModelRequirementPlanEvidenceBinding | null;
  requirement_action_evidence_binding: ModelRequirementActionEvidenceBinding | null;
};

/** Manual bridge until the generated OpenAPI client includes the reviewed profile route. */
export type DeclaredTaskProfileConstraintKind =
  | "privacy"
  | "cost"
  | "platform"
  | "version"
  | "scope"
  | "performance"
  | "delivery"
  | "safety";
export type DeclaredTaskProfileDeliverableSlot =
  | "artifact"
  | "format"
  | "location"
  | "audience"
  | "interface"
  | "compatibility";
export interface DeclaredTaskProfile {
  profile_id: string;
  provider: Provider;
  session_id: string;
  revision: number;
  previous_profile_id: string | null;
  constraint_kinds: readonly DeclaredTaskProfileConstraintKind[] | null;
  expected_outcome_count: number | null;
  deliverable_slots: readonly DeclaredTaskProfileDeliverableSlot[] | null;
  profile_fingerprint: string;
  confirmed_at: string;
  confirmation_authority: "authenticated_local_user";
  schema_version: "declared-task-profile-v1";
  policy_version: "authenticated-local-user-v1";
  local_only: true;
  content_persisted: false;
}
export interface DeclaredTaskProfileCurrent {
  session_id: string;
  profile: DeclaredTaskProfile | null;
  /** True only when a non-self-issuable user-presence adapter is composed. */
  confirmation_available: boolean;
}
export interface DeclaredTaskProfileCommand {
  expected_revision: number | null;
  constraint_kinds: readonly DeclaredTaskProfileConstraintKind[] | null;
  expected_outcome_count: number | null;
  deliverable_slots: readonly DeclaredTaskProfileDeliverableSlot[] | null;
  confirmation: "save_reviewed_declared_task_profile";
}
export interface DeclaredTaskProfileOutcome {
  profile: DeclaredTaskProfile;
  applied: boolean;
}
export type MetricEvidenceContributor =
  | Schemas["MetricEvidenceContributor"]
  | "reviewed_requirement_enumeration"
  | "reviewed_requirement_plan_disposition"
  | "reviewed_requirement_action_link"
  | "safe_action_candidate_enumeration";
export type MetricEvidenceReadinessReason =
  | Schemas["MetricEvidenceReadinessReason"]
  | "reviewed_requirement_plan_service_required"
  | "reviewed_requirement_plan_confirmation_required"
  | "reviewed_requirement_plan_binding_invalid"
  | "reviewed_requirement_action_service_required"
  | "reviewed_requirement_action_confirmation_required"
  | "reviewed_requirement_action_binding_invalid";
export type MetricEvidenceReadinessV2 = Omit<
  Schemas["MetricEvidenceReadinessV2"],
  "required_contributors" | "observed_contributors" | "missing_contributors" | "reason_code"
> & {
  required_contributors: MetricEvidenceContributor[];
  observed_contributors: MetricEvidenceContributor[];
  missing_contributors: MetricEvidenceContributor[];
  reason_code: MetricEvidenceReadinessReason;
};
export type MetricEvidenceReadinessProjectionV2 = Omit<
  Schemas["MetricEvidenceReadinessProjectionV2"],
  "catalog_version" | "metric_projection_version" | "metrics"
> & {
  catalog_version:
    | "metric-evidence-readiness-v2-2"
    | "metric-evidence-readiness-v2-3"
    | "metric-evidence-readiness-v2-4"
    | "metric-evidence-readiness-v2-5"
    | "metric-evidence-readiness-v2-6";
  metric_projection_version: MetricProjectionV2Version;
  metrics: MetricEvidenceReadinessV2[];
};
export type MetricEvidenceAvailabilityState =
  Schemas["MetricEvidenceAvailabilityState"];
export type MetricOperabilityEntry = Omit<
  Schemas["MetricOperabilityEntry"],
  "measured_path" | "next_step_code"
> & {
  measured_path:
    | Schemas["MetricOperabilityEntry"]["measured_path"]
    | "reviewed_requirement_plan"
    | "reviewed_requirement_action";
  next_step_code:
    | Schemas["MetricOperabilityEntry"]["next_step_code"]
    | "confirm_requirement_plan_evidence"
    | "compose_requirement_action_evidence";
};
export type MetricOperabilityCatalog = Omit<
  Schemas["MetricOperabilityCatalog"],
  "catalog_version" | "projection_version" | "readiness_catalog_version" | "entries"
> & {
  catalog_version: "metric-operability-v3";
  projection_version: "metric-contract-v2-projection-6";
  readiness_catalog_version: "metric-evidence-readiness-v2-5";
  entries: MetricOperabilityEntry[];
};

export interface RequirementPlanCoordinate {
  message_sequence: number;
  clause_index: number;
}
export interface RequirementPlanEvidenceEntry {
  coordinate: RequirementPlanCoordinate;
  disposition: "linked" | "not_linked" | "pending";
  plan_indexes: number[];
}
export interface RequirementPlanProducer {
  kind: "local_coding_agent";
  producer_id: string;
  producer_version: string;
  model_id: string;
  authority: "untrusted_provenance_claim";
}
export type RequirementPlanClauseAlgorithmContract = Schemas["RequirementPlanClauseAlgorithmContract"];
export type RequirementPlanReviewRubric = Schemas["RequirementPlanReviewRubric"];
export type RequirementPlanExclusionReason = Schemas["RequirementPlanExclusionReason"];
export type RequirementPlanProducerReceipt = Schemas["RequirementPlanProducerReceipt"];
export type ExcludedRequirementClause = Omit<
  Schemas["ExcludedRequirementClause"],
  "basis_coordinate"
> & { basis_coordinate: RequirementPlanCoordinate | null };
export type RequirementPlanSourceManifest = Omit<
  Schemas["RequirementPlanSourceManifest"],
  "clause_algorithm_spec" | "review_rubric"
> & {
  clause_algorithm_spec: RequirementPlanClauseAlgorithmContract;
  review_rubric: RequirementPlanReviewRubric;
};
export interface RequirementPlanEvidenceContract {
  schema_version: "requirement-plan-evidence-file-v1";
  session_id: string;
  expected_source_run_id: string;
  source_window_fingerprint: string;
  expected_predecessor_confirmation_id: string | null;
  registry_version: "all-20-factor-contracts-v2";
  contract_set_fingerprint: string;
  metric_key: "logic.decomposition_coverage";
  metric_contract_fingerprint: string;
  source_projection_version:
    | "metric-contract-v2-projection-5"
    | "metric-contract-v2-projection-6"
    | "metric-contract-v2-projection-7";
  clause_algorithm: "message-clause-coordinates-en-pl-v1";
  clause_algorithm_spec: RequirementPlanClauseAlgorithmContract;
  review_rubric_version: "active-requirement-plan-review-rubric-v1";
  review_rubric: RequirementPlanReviewRubric;
  allowed_dispositions: ["linked", "not_linked", "pending"];
  allowed_user_clause_classifications: [
    "active_requirement", "excluded_from_active_requirement_denominator",
  ];
  allowed_exclusion_reasons: [
    "not_requirement", "superseded", "withdrawn", "duplicate", "out_of_scope",
    "already_satisfied_or_closed",
  ];
  max_reviewed_user_clause_count: 1000;
  max_active_requirement_count: 1000;
  max_excluded_user_clause_count: 1000;
  max_plan_item_count: 1000;
  max_link_count: 4000;
  max_file_bytes: 65536;
  max_json_depth: 8;
  max_json_items: 6000;
  max_clauses_per_message: 128;
  max_lifetime_seconds: 86400;
  canonical_json_required: true;
  canonicalization: "json-sort-keys-compact-ensure-ascii-v1";
  payload_digest: "sha256";
  utf8_without_bom_required: true;
  duplicate_keys_allowed: false;
  floating_point_values_allowed: false;
  candidate_unit: "reviewable_user_request_or_feedback_clause";
  opportunity_unit: "reviewed_active_requirement_clause";
  complete_user_clause_classification_required: true;
  compound_clause_coarsening_disclosed: true;
  one_active_requirement_coordinate_is_one_opportunity: true;
  excluded_user_clauses_are_excluded_from_metric: true;
  uncertain_classification_policy: "reject_or_leave_proposal_unconfirmed";
  import_creates_unconfirmed_proposal_only: true;
  native_confirmation_required_for_metric_authority: true;
  raw_payload_persisted: false;
  prose_allowed: false;
  scores_allowed: false;
  untrusted_structured_classification_proposals_allowed: true;
  authoritative_model_judgment_claims_allowed: false;
  raw_producer_claim_persisted: false;
  durable_producer_claim_shape: "installation_keyed_opaque_commitment_only";
  objective_receipt_claims_allowed: false;
  import_confirmation: "import_requirement_plan_evidence_as_unconfirmed_proposal";
  file_json_schema_sha256: string;
  file_json_schema: Record<string, unknown>;
  source_manifest: RequirementPlanSourceManifest;
  file_constraint_contract_version: "requirement-plan-file-constraints-v1";
  file_constraint_codes: readonly [
    "identifiers_match_current_contract",
    "producer_codes_match_safe_version_pattern",
    "expires_at_is_utc_after_validation_and_within_86400_seconds",
    "requirement_coordinates_are_sorted_unique",
    "plan_coordinates_are_sorted_unique",
    "plan_indexes_are_sorted_unique_non_negative",
    "linked_requires_nonempty_plan_indexes",
    "nonlinked_and_pending_require_empty_plan_indexes",
    "plan_indexes_reference_existing_plan_items",
    "total_plan_indexes_lte_4000",
    "requirement_coordinates_reference_user_request_or_feedback_clauses",
    "excluded_user_clause_coordinates_are_sorted_unique",
    "excluded_user_clause_reasons_use_closed_rubric",
    "exclusion_basis_coordinates_follow_reason_rules",
    "user_clauses_exactly_classified_as_active_or_excluded",
    "active_and_excluded_user_clause_coordinates_are_disjoint",
    "source_messages_fail_closed_above_128_normalized_clauses",
    "plan_coordinates_reference_agent_plan_clauses",
    "linked_plan_sequence_gte_requirement_sequence",
  ];
}
export interface RequirementPlanEvidencePreview {
  payload_sha256: string;
  session_id: string;
  expected_source_run_id: string;
  source_window_fingerprint: string;
  expected_predecessor_confirmation_id: string | null;
  reviewed_user_clause_count: number;
  active_requirement_count: number;
  excluded_user_clause_count: number;
  plan_item_count: number;
  linked_active_requirement_count: number;
  not_linked_active_requirement_count: number;
  pending_active_requirement_count: number;
  link_count: number;
  expires_at: string;
  producer: RequirementPlanProducer;
  creates_unconfirmed_proposal_only: true;
  native_confirmation_required_for_metric_authority: true;
  can_set_numeric_metric_on_import: false;
  raw_payload_persisted: false;
  raw_producer_claim_persisted: false;
}
export interface RequirementPlanProposal {
  proposal_id: string;
  session_id: string;
  source_run_id: string;
  source_window_fingerprint: string;
  expected_predecessor_confirmation_id: string | null;
  payload_sha256: string;
  producer_receipt: RequirementPlanProducerReceipt;
  review_rubric_version: "active-requirement-plan-review-rubric-v1";
  requirements: RequirementPlanEvidenceEntry[];
  excluded_user_clauses: ExcludedRequirementClause[];
  plan_items: RequirementPlanCoordinate[];
  created_at: string;
  schema_version: "requirement-plan-evidence-v1";
  policy_version: "reviewed-requirement-plan-v1";
  status: "proposed" | "confirmed" | "rejected";
  decision_id: string | null;
  decision: "confirm" | "reject" | null;
  decided_at: string | null;
  confirmation_authority: "owned_native_user_presence" | null;
  local_only: true;
  content_persisted: false;
}
export interface RequirementPlanImport {
  payload_sha256: string;
  proposal: RequirementPlanProposal;
  applied: boolean;
  creates_unconfirmed_proposal_only: true;
  native_confirmation_required_for_metric_authority: true;
  raw_payload_persisted: false;
}
export interface RequirementPlanProposalOutcome {
  proposal: RequirementPlanProposal;
  applied: boolean;
}
export type RequirementPlanProposalPageSnapshot = Schemas["RequirementPlanProposalPageSnapshot"];
export type RequirementPlanReviewClause = Omit<
  Schemas["RequirementPlanReviewClause"],
  "basis_coordinate" | "classification" | "disposition" | "exclusion_reason"
> & {
  basis_coordinate: RequirementPlanCoordinate | null;
  classification: "active_requirement" | "excluded_from_active_requirement_denominator" | null;
  disposition: "linked" | "not_linked" | "pending" | null;
  exclusion_reason: RequirementPlanExclusionReason | null;
};
export type RequirementPlanProposalReview = Omit<
  Schemas["RequirementPlanProposalReview"],
  "candidate_clauses"
> & { candidate_clauses: RequirementPlanReviewClause[] };
export interface RequirementPlanReviewRequest {
  expected_source_run_id: string;
  confirmation: "open_exact_local_requirement_plan_clause_review";
}
export interface RequirementPlanProposalPage {
  session_id: string;
  proposals: RequirementPlanProposal[];
  limit: number;
  offset: number;
  total: number;
  next_offset: number | null;
  complete: boolean;
  snapshot: RequirementPlanProposalPageSnapshot;
}
export interface RequirementPlanProposalCollection {
  session_id: string;
  proposals: RequirementPlanProposal[];
  total: number;
  complete: true;
  snapshot: RequirementPlanProposalPageSnapshot;
}
export interface RequirementPlanConfirmDecisionRequest {
  expected_source_run_id: string;
  decision: "confirm";
  confirmation: "apply_local_user_requirement_plan_evidence_decision";
  review_receipt_id: string;
  manifest_fingerprint: string;
  reviewed_graph_fingerprint: string;
  reviewed_candidate_set_fingerprint: string;
  complete_review_acknowledged: true;
}
export interface RequirementPlanRejectDecisionRequest {
  expected_source_run_id: string;
  decision: "reject";
  confirmation: "apply_local_user_requirement_plan_evidence_decision";
}
export type RequirementPlanDecisionRequest =
  | RequirementPlanConfirmDecisionRequest
  | RequirementPlanRejectDecisionRequest;

/** Explicit r7 facade narrowed by the strict runtime parsers below the generated wire types. */
export interface RequirementActionEvidenceProvenance {
  provider: Provider;
  provider_version: string;
  adapter_version: string;
  decoder_key: string;
  decoder_version: string;
  source_schema_version: string;
  evidence_schema_version: 2;
  extraction_complete: boolean;
}
export type RequirementActionEventKind = "tool_start" | "tool_end" | "artifact";
export type RequirementActionToolCategory =
  | "file_read" | "file_write" | "command" | "search" | "test" | "build"
  | "version_control" | "network" | "mcp" | "subagent" | "other" | "unknown";
export type RequirementActionFamily = "tool" | "command" | "file_change" | "review" | "other_documented";
export type RequirementActionState = "started" | "completed" | "failed" | "cancelled" | "unknown";
export interface RequirementActionCandidate {
  candidate_index: number;
  action_id: string;
  source_reference_id: string;
  sequence: number;
  event_kind: RequirementActionEventKind;
  tool_category: RequirementActionToolCategory | null;
  occurred_at: string;
  duration_ms: number | null;
  family: RequirementActionFamily;
  state: RequirementActionState;
}
export interface RequirementActionCandidateManifest {
  session_id: string;
  source_run_id: string;
  source_window_fingerprint: string;
  provenance: RequirementActionEvidenceProvenance;
  extraction_complete: boolean;
  enumeration_complete: boolean;
  actions: RequirementActionCandidate[];
  manifest_fingerprint: string;
  schema_version: "requirement-action-candidate-manifest-v1";
  local_only: true;
  content_persisted: false;
}
export interface RequirementActionRequirement {
  requirement_index: number;
  requirement_id: string;
  coordinate: RequirementPlanCoordinate;
}
export interface RequirementActionEvidenceContract {
  action_descriptor_algorithm_version: "provider-local-redacted-action-descriptor-v1";
  action_descriptor_content_persisted: false;
  candidate_metadata_fingerprint_version: "requirement-action-candidate-metadata-v1";
  schema_version: "requirement-action-evidence-file-v1";
  session_id: string;
  expected_source_run_id: string;
  source_window_fingerprint: string;
  source_projection_version: "metric-contract-v2-projection-6" | "metric-contract-v2-projection-7";
  requirement_plan_confirmation_id: string;
  requirement_plan_evidence_fingerprint: string;
  candidate_manifest: RequirementActionCandidateManifest;
  requirements: RequirementActionRequirement[];
  expected_predecessor_confirmation_id: string | null;
  metric_key: "logic.requirement_action_traceability";
  max_requirement_count: 1000;
  max_candidate_count: 4000;
  max_link_count: 8000;
  max_file_bytes: 65536;
  max_json_depth: 8;
  max_json_items: 8000;
  max_lifetime_seconds: 86400;
  canonicalization: "json-sort-keys-compact-ensure-ascii-v1";
  import_creates_unconfirmed_proposal_only: true;
  native_confirmation_required_for_metric_authority: true;
  all_linked_action_semantics_acknowledgement_required: true;
  native_review_displays_every_redacted_invocation_and_effect: true;
  review_visible_display_algorithm_version: "requirement-action-review-visible-display-v1";
  review_visible_display_is_injective_one_pass: true;
  review_visible_display_never_truncates: true;
  every_requirement_requires_one_link_classification: true;
  empty_action_links_are_explicit_reviewed_negative_links: true;
  action_states_are_application_issued: true;
  action_state_claims_allowed_in_file: false;
  objective_proof_claims_allowed_in_file: false;
  metric_values_allowed_in_file: false;
  raw_payload_persisted: false;
  raw_producer_claim_persisted: false;
  durable_producer_claim_shape: "installation_keyed_opaque_commitment_only";
  import_confirmation: "import_requirement_action_proposal_without_metric_authority";
  review_rubric_version: "requirement-action-review-rubric-v2";
  file_json_schema_sha256: string;
  file_json_schema: Record<string, unknown>;
}
export interface RequirementActionEvidencePreview {
  payload_sha256: string;
  session_id: string;
  expected_source_run_id: string;
  source_window_fingerprint: string;
  requirement_plan_confirmation_id: string;
  requirement_plan_evidence_fingerprint: string;
  candidate_manifest_fingerprint: string;
  expected_predecessor_confirmation_id: string | null;
  requirement_count: number;
  candidate_count: number;
  linked_requirement_count: number;
  unlinked_requirement_count: number;
  link_count: number;
  expires_at: string;
  producer: RequirementPlanProducer;
  creates_unconfirmed_proposal_only: true;
  native_confirmation_required_for_metric_authority: true;
  can_set_numeric_metric_on_import: false;
  raw_payload_persisted: false;
  raw_producer_claim_persisted: false;
}
export interface RequirementActionLink {
  requirement_id: string;
  action_ids: string[];
}
export interface RequirementActionProposal {
  proposal_id: string;
  session_id: string;
  source_run_id: string;
  source_window_fingerprint: string;
  requirement_plan_confirmation_id: string;
  requirement_plan_evidence_fingerprint: string;
  candidate_manifest_fingerprint: string;
  candidate_provenance: RequirementActionEvidenceProvenance;
  candidate_extraction_complete: boolean;
  candidate_enumeration_complete: boolean;
  expected_predecessor_confirmation_id: string | null;
  payload_sha256: string;
  producer_receipt: RequirementPlanProducerReceipt;
  review_rubric_version: "requirement-action-review-rubric-v2";
  requirements: RequirementActionRequirement[];
  candidates: RequirementActionCandidate[];
  links: RequirementActionLink[];
  created_at: string;
  schema_version: "requirement-action-evidence-v1";
  policy_version: "reviewed-requirement-action-v1";
  status: "proposed" | "confirmed" | "rejected";
  decision_id: string | null;
  decision: "confirm" | "reject" | null;
  decided_at: string | null;
  confirmation_authority: "owned_native_user_presence" | null;
  local_only: true;
  content_persisted: false;
}
export interface RequirementActionImport {
  payload_sha256: string;
  proposal: RequirementActionProposal;
  applied: boolean;
  creates_unconfirmed_proposal_only: true;
  native_confirmation_required_for_metric_authority: true;
  raw_payload_persisted: false;
  raw_producer_claim_persisted: false;
}
export interface RequirementActionReviewRequirement {
  requirement_id: string;
  coordinate: RequirementPlanCoordinate;
  text: string;
  linked_action_ids: string[];
}
export interface RequirementActionReviewCandidate {
  candidate: RequirementActionCandidate;
  candidate_metadata_fingerprint_version: "requirement-action-candidate-metadata-v1";
  candidate_metadata_fingerprint: string;
  descriptor_algorithm_version: "provider-local-redacted-action-descriptor-v1";
  tool_name: string;
  invocation_preview: string;
  result_or_effect_preview: string | null;
  invocation_truncated: false;
  result_or_effect_truncated: false;
  redactor_version: string;
  linked_requirement_ids: string[];
}
export interface RequirementActionProposalReview {
  proposal_id: string;
  session_id: string;
  source_run_id: string;
  source_window_fingerprint: string;
  review_receipt_id: string;
  payload_sha256: string;
  requirement_plan_evidence_fingerprint: string;
  candidate_manifest_fingerprint: string;
  reviewed_graph_fingerprint: string;
  reviewed_candidate_set_fingerprint: string;
  reviewed_descriptor_set_fingerprint: string;
  review_visible_display_algorithm_version: "requirement-action-review-visible-display-v1";
  requirements: RequirementActionReviewRequirement[];
  candidates: RequirementActionCandidate[];
  candidate_memberships: RequirementActionReviewCandidate[];
  review_context_expires_at: string;
  review_receipt_expires_at: string;
  all_requirements_and_candidates_displayed: true;
  raw_text_persisted: false;
  local_only: true;
}
export interface RequirementActionProposalPageSnapshot {
  snapshot_id: string;
  total: number;
  decision_count: number;
  high_water_created_at: string | null;
  high_water_proposal_id: string | null;
}
export interface RequirementActionProposalPage {
  session_id: string;
  proposals: RequirementActionProposal[];
  limit: number;
  offset: number;
  total: number;
  snapshot: RequirementActionProposalPageSnapshot;
  next_offset: number | null;
  complete: boolean;
}
export interface RequirementActionProposalCollection {
  session_id: string;
  proposals: RequirementActionProposal[];
  total: number;
  complete: true;
  snapshot: RequirementActionProposalPageSnapshot;
}
export interface RequirementActionReviewRequest {
  expected_source_run_id: string;
  confirmation: "open_exact_local_requirement_action_review";
}
export interface RequirementActionConfirmDecisionRequest {
  expected_source_run_id: string;
  decision: "confirm";
  confirmation: "decide_exact_reviewed_requirement_action_proposal";
  review_receipt_id: string;
  reviewed_graph_fingerprint: string;
  candidate_manifest_fingerprint: string;
  reviewed_candidate_set_fingerprint: string;
  reviewed_descriptor_set_fingerprint: string;
  complete_review_acknowledged: true;
  all_requirements_and_candidates_acknowledged: true;
  all_linked_action_semantics_reviewed: true;
}
export interface RequirementActionRejectDecisionRequest {
  expected_source_run_id: string;
  decision: "reject";
  confirmation: "decide_exact_reviewed_requirement_action_proposal";
}
export type RequirementActionDecisionRequest =
  | RequirementActionConfirmDecisionRequest
  | RequirementActionRejectDecisionRequest;
export interface RequirementActionProposalOutcome {
  proposal: RequirementActionProposal;
  applied: boolean;
}
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
export type ModelEnsembleOutcome = Omit<Schemas["ModelEnsembleOutcomeDto"], "run"> & {
  run: ModelEnsembleRun;
};
export type ModelEnsembleWatchRequest = Schemas["ModelEnsembleWatchRequest"];
export type ModelEnsembleWatch = Schemas["ModelEnsembleWatchDto"];
export type ModelEnsembleWatchSnapshot = Omit<Schemas["ModelEnsembleWatchSnapshotDto"], "latest_run"> & {
  latest_run: ModelEnsembleRun | null;
};
export type ModelEnsembleTrajectoryPoint = Omit<Schemas["ModelEnsembleTrajectoryPoint"], "metric_states_v2"> & {
  metric_states_v2: MetricStateV2[];
};
export type ModelEnsembleTrajectoryPage = Omit<Schemas["ModelEnsembleTrajectoryPage"], "points"> & {
  points: ModelEnsembleTrajectoryPoint[];
};
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

export interface UserPresenceCapability {
  contract_version: "native-user-presence-capability-v1";
  confirmation_available: boolean;
  mode: "unavailable" | "native_bridge_bound_token";
}

export interface PromptEnhancerTransport {
  /**
   * Whether this exact server/window composition can perform a native,
   * non-self-issuable confirmation for protected local decisions.
   */
  getUserPresenceCapability?(
    signal?: AbortSignal,
  ): Promise<UserPresenceCapability>;
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
  /** Content-free all-twenty release map; never reads a project or session. */
  getMetricOperabilityCatalog?(
    signal?: AbortSignal,
  ): Promise<MetricOperabilityCatalog>;
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
  streamAgentEvents(sessionId: string, after: number, onPage: (page: AgentEvents) => void, signal?: AbortSignal): Promise<void>;
  decideAgentApproval(sessionId: string, approvalId: string, approved: boolean, signal?: AbortSignal): Promise<AgentSessionView>;
  stopAgentSession(sessionId: string, signal?: AbortSignal): Promise<AgentSessionView>;
  getAgentWorkspaceTree(sessionId: string, path: string, signal?: AbortSignal): Promise<AgentWorkspaceTree>;
  getAgentWorkspaceFile(sessionId: string, path: string, signal?: AbortSignal): Promise<AgentWorkspaceFile>;
  previewAgentWorkspaceEdit(sessionId: string, request: AgentWorkspacePreviewCommand, signal?: AbortSignal): Promise<AgentWorkspaceEditPreview>;
  applyAgentWorkspaceEdit(sessionId: string, previewId: string, request: AgentWorkspaceApplyCommand, signal?: AbortSignal): Promise<AgentWorkspaceApplyResult>;
  startModelJudgeSweep(signal?: AbortSignal, scope?: "sample" | "all"): Promise<JudgeSweepStatus>;
  getModelJudgeSweep(signal?: AbortSignal): Promise<JudgeSweepStatus>;
  getModelJudgeAgreement(signal?: AbortSignal): Promise<JudgeAgreementReport>;
  /** Annotation paths (ADR 0017): agent allowance switch, metaprompt, and the explicit "annotate remotely" action. */
  getAnnotationAllowance(signal?: AbortSignal): Promise<AnnotationAllowance>;
  setAnnotationAllowance(agentAllowed: boolean, signal?: AbortSignal): Promise<AnnotationAllowance>;
  getAnnotationMetaprompt(signal?: AbortSignal): Promise<AnnotationMetaprompt>;
  annotateRemotely(limit: number, signal?: AbortSignal): Promise<RemoteAnnotationResult>;
  /** Shared team folders (ADR 0018): share, revoke, join a peer's folder, pull/push. */
  shareFolder(path: string, name: string, signal?: AbortSignal): Promise<SharedFolder>;
  listSharedFolders(signal?: AbortSignal): Promise<SharedFolderList>;
  revokeSharedFolder(shareId: string, signal?: AbortSignal): Promise<void>;
  joinSharedFolder(url: string, shareId: string, shareToken: string, target: string, signal?: AbortSignal): Promise<PeerLink>;
  listPeerLinks(signal?: AbortSignal): Promise<PeerLinkList>;
  leavePeerLink(linkId: string, signal?: AbortSignal): Promise<void>;
  pullPeerLink(linkId: string, signal?: AbortSignal): Promise<FolderSyncReport>;
  pushPeerLink(linkId: string, peerName: string, signal?: AbortSignal): Promise<FolderSyncReport>;
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
  /** Reviewed, content-free denominators for future r5 metric publications. */
  getDeclaredTaskProfile?(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<DeclaredTaskProfileCurrent>;
  saveDeclaredTaskProfile?(
    sessionId: string,
    request: DeclaredTaskProfileCommand,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<DeclaredTaskProfileOutcome>;
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
  /** Content-free, native-reviewed requirement-to-plan denominator for r6. */
  getRequirementPlanEvidenceContract?(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<RequirementPlanEvidenceContract>;
  previewRequirementPlanEvidence?(
    sessionId: string,
    payload: ArrayBuffer,
    signal?: AbortSignal,
  ): Promise<RequirementPlanEvidencePreview>;
  importRequirementPlanEvidence?(
    sessionId: string,
    payload: ArrayBuffer,
    preview: RequirementPlanEvidencePreview,
    confirmation: RequirementPlanEvidenceContract["import_confirmation"],
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<RequirementPlanImport>;
  listRequirementPlanProposals?(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<RequirementPlanProposalCollection>;
  reviewRequirementPlanProposal?(
    sessionId: string,
    proposal: RequirementPlanProposal,
    contract: RequirementPlanEvidenceContract,
    request: RequirementPlanReviewRequest,
    signal?: AbortSignal,
  ): Promise<RequirementPlanProposalReview>;
  decideRequirementPlanProposal?(
    sessionId: string,
    proposalId: string,
    request: RequirementPlanDecisionRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<RequirementPlanProposalOutcome>;
  /** Content-free, native-reviewed requirement-to-action authority for r7. */
  getRequirementActionEvidenceContract?(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<RequirementActionEvidenceContract>;
  previewRequirementActionEvidence?(
    sessionId: string,
    payload: ArrayBuffer,
    signal?: AbortSignal,
  ): Promise<RequirementActionEvidencePreview>;
  importRequirementActionEvidence?(
    sessionId: string,
    payload: ArrayBuffer,
    preview: RequirementActionEvidencePreview,
    confirmation: RequirementActionEvidenceContract["import_confirmation"],
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<RequirementActionImport>;
  listRequirementActionProposals?(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<RequirementActionProposalCollection>;
  reviewRequirementActionProposal?(
    sessionId: string,
    proposal: RequirementActionProposal,
    contract: RequirementActionEvidenceContract,
    request: RequirementActionReviewRequest,
    signal?: AbortSignal,
  ): Promise<RequirementActionProposalReview>;
  decideRequirementActionProposal?(
    sessionId: string,
    proposalId: string,
    request: RequirementActionDecisionRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<RequirementActionProposalOutcome>;
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
