import type {
  AnalysisJobIdentity,
  AnalysisJobPage,
  AnalysisJobRecord,
  AnalysisJobState,
  AnalysisRunListResponse,
  AnalysisRunResponse,
  AgentMetricEvidenceImport,
  AgentMetricEvidencePreview,
  AutomationGrantCreateRequest,
  AutomationGrantRecord,
  AutomationGrantScope,
  AutomationPollResult,
  AutomationResourcePolicy,
  CandidateListResponse,
  CandidateStatusFilter,
  CodexAnalysisSelection,
  CodexIngestionReport,
  CodexLabelEnrichmentReport,
  CodexLocalSourceStatus,
  CodexSessionListResponse,
  DisplayLabelEntityKind,
  ManualDisplayLabelResult,
  MetricCoverageReport,
  ModelLabInventory,
  ModelEnsembleCanonicalHead,
  ModelEnsembleAttemptSnapshot,
  ModelEnsembleRequest,
  ModelPredictiveMetricDetail,
  ModelEnsembleTrajectoryPage,
  ModelEnsembleWatchRequest,
  ModelLinkAnnotation,
  ModelLinkAnnotationRequest,
  ModelLinkExperiment,
  ModelLinkExperimentOutcome,
  ModelLinkExperimentRequest,
  ProjectQualityAggregate,
  ProjectQualityAggregateRequest,
  ProjectSessionListResponse,
  Provider,
  ProviderCapabilityReport,
  ProviderCompatibilityProvider,
  ProviderCompatibilityStatus,
  MetricEvidenceCapability,
  MetricLifecycleDecisionRequest,
  MetricLifecycleProposal,
  MetricReadiness,
  MetricReadinessAction,
  ReviewCommand,
  SessionAnalysisRunResponse,
  SessionCoachingProjection,
  SessionMetricResponse,
  SessionMetricReadinessReport,
  SessionQualityAnalysisOutcome,
  SessionQualityAnalysisPreview,
  SessionQualityAnalysisPreviewApprovalRequest,
  SessionQualityAnalysisPreviewRequest,
  SessionQualityAnalysisRequest,
  SessionTextAnalysisCapability,
  SessionQualityAggregate,
  SessionQualityAggregateRequest,
  TaskRevisionListResponse,
  TaskRevisionResponse,
  TaskLifecycleState,
  TaskAnalysisResponse,
  TaskReviewResponse,
  TextAnalysisResearchCatalog,
  TextAnalysisPresetId,
  ClaudeCodeLocalSourceStatus,
  IngestionReport,
  SessionTranscript,
  OnboardingAccept,
  OnboardingResult,
  OnboardingStatus,
} from "./contracts";
import {
  ModelEnsembleHeadPayloadError,
  parseModelEnsembleAttemptSnapshot,
  parseModelEnsembleCanonicalHead,
} from "./modelEnsembleHeadContract";
import {
  ModelEnsemblePayloadError,
  parseModelEnsembleOutcome,
  parseModelEnsembleRun,
} from "./modelEnsembleContract";
import {
  ModelEnsembleWatchPayloadError,
  parseModelEnsembleWatchSnapshot,
} from "./modelEnsembleWatchContract";
import {
  ModelEnsembleTrajectoryPayloadError,
  parseModelEnsembleTrajectoryPage,
} from "./modelEnsembleTrajectoryContract";
import {
  ModelPredictiveMetricDetailPayloadError,
  parseModelPredictiveMetricDetail,
} from "./modelPredictiveMetricDetailContract";
import {
  ModelCompatibilityPayloadError,
  parseModelCompatibilityCatalog,
} from "./modelCompatibilityContract";
import { parseControlPlaneReadiness } from "./controlPlaneReadiness";
import { parseCandidateDecisionsResponse } from "./taskDecisionContract";
import {
  TaskLifecyclePayloadError,
  parseTaskLifecycleListResponse,
  parseTaskLifecycleMutationResponse,
  parseTaskLifecycleSnapshot,
} from "./taskLifecycleContract";
import {
  AgentMetricEvidencePayloadError,
  parseAgentMetricEvidenceImport,
  parseAgentMetricEvidencePreview,
  parseMetricLifecycleProposalPage,
  parseMetricLifecycleProposalOutcome,
} from "./agentMetricEvidenceContract";
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
  | "source_selection_limit"
  | "source_provider_response_limit"
  | "source_thread_structure_limit"
  | "source_preview_window_limit"
  | "source_resource_limit"
  | "source_timeout"
  | "provider_unavailable"
  | "no_analyzable_text"
  | "provider_protocol_rejected"
  | "provider_compatibility_blocked"
  | "analysis_persistence_failed"
  | "metric_execution_failed"
  | "redaction_preview_not_found"
  | "redaction_preview_expired"
  | "redaction_preview_consumed"
  | "redaction_preview_binding_mismatch"
  | "redaction_preview_capacity_reached"
  | "analysis_job_not_found"
  | "analysis_job_conflict"
  | "automation_consent_required"
  | "automation_metric_unsupported"
  | "automation_project_not_indexed"
  | "automation_grant_conflict"
  | "automation_grant_not_found"
  | "automation_resource_policy_unsupported"
  | "invalid_model_link_request"
  | "model_link_confirmation_required"
  | "no_model_link_candidates"
  | "local_model_execution_failed"
  | "model_link_persistence_failed"
  | "model_link_revision_conflict"
  | "invalid_model_ensemble_request"
  | "model_ensemble_confirmation_required"
  | "local_model_ensemble_execution_failed"
  | "model_ensemble_persistence_failed"
  | "invalid_model_ensemble_watch_request"
  | "model_ensemble_watch_not_found"
  | "model_ensemble_watch_conflict";

const SAFE_TRANSPORT_REASONS = new Set<SafeTransportReasonCode>([
  "redacted_content_consent_required",
  "session_not_in_safe_index",
  "analysis_idempotency_conflict",
  "invalid_analysis_request",
  "confirmation_required",
  "source_schema_unsupported",
  "selection_snapshot_miss",
  "source_selection_limit",
  "source_provider_response_limit",
  "source_thread_structure_limit",
  "source_preview_window_limit",
  "source_resource_limit",
  "source_timeout",
  "provider_unavailable",
  "no_analyzable_text",
  "provider_protocol_rejected",
  "provider_compatibility_blocked",
  "analysis_persistence_failed",
  "metric_execution_failed",
  "redaction_preview_not_found",
  "redaction_preview_expired",
  "redaction_preview_consumed",
  "redaction_preview_binding_mismatch",
  "redaction_preview_capacity_reached",
  "analysis_job_not_found",
  "analysis_job_conflict",
  "automation_consent_required",
  "automation_metric_unsupported",
  "automation_project_not_indexed",
  "automation_grant_conflict",
  "automation_grant_not_found",
  "automation_resource_policy_unsupported",
  "invalid_model_link_request",
  "model_link_confirmation_required",
  "no_model_link_candidates",
  "local_model_execution_failed",
  "model_link_persistence_failed",
  "model_link_revision_conflict",
  "invalid_model_ensemble_request",
  "model_ensemble_confirmation_required",
  "local_model_ensemble_execution_failed",
  "model_ensemble_persistence_failed",
  "invalid_model_ensemble_watch_request",
  "model_ensemble_watch_not_found",
  "model_ensemble_watch_conflict",
]);

const MODEL_LAB_INVENTORY_KEYS = new Set([
  "contract_version", "scope", "session_data_read", "private_evidence_returned",
  "registered_plan_count", "synthetic_execution_count", "model_run_count",
  "model_vote_count", "metric_estimate_count", "activation_outcome",
  "activation_allowed", "plans",
]);
const MODEL_LAB_PLAN_KEYS = new Set([
  "plan_fingerprint", "plan_key", "plan_version", "route",
  "metric_question_count", "synthetic_execution_count", "model_run_count",
  "model_vote_count", "metric_estimate_count", "activation_outcome",
  "activation_allowed",
]);
const MODEL_LAB_PLAN_KEY = /^[a-z][a-z0-9_.:-]{0,127}$/;
const MODEL_LAB_SAFE_VERSION = /^[A-Za-z0-9][A-Za-z0-9._+:/-]{0,127}$/;
const MODEL_LAB_PSEUDONYM = /^[a-f0-9]{64}$/;
const MAX_MODEL_LAB_PLANS = 1_000;

function modelLabSafeInteger(value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) &&
    value >= 0 && value <= maximum;
}

function modelLabSafeVersion(value: unknown): value is string {
  return typeof value === "string" && MODEL_LAB_SAFE_VERSION.test(value) &&
    !value.startsWith("/") && !value.startsWith("\\") &&
    !/^[A-Za-z]:[/\\]/.test(value) && !value.includes("\\") &&
    !value.includes("://") && !value.split("/").includes("..");
}

function parseModelLabPlan(value: unknown): ModelLabInventory["plans"][number] {
  if (
    !isRecord(value) || !hasExactKeys(value, MODEL_LAB_PLAN_KEYS) ||
    typeof value.plan_fingerprint !== "string" ||
    !MODEL_LAB_PSEUDONYM.test(value.plan_fingerprint) ||
    typeof value.plan_key !== "string" || !MODEL_LAB_PLAN_KEY.test(value.plan_key) ||
    !modelLabSafeVersion(value.plan_version) ||
    !["fast", "balanced", "deep"].includes(value.route as string) ||
    !modelLabSafeInteger(value.metric_question_count, 100) ||
    (value.metric_question_count as number) < 1 ||
    !modelLabSafeInteger(value.synthetic_execution_count) ||
    !modelLabSafeInteger(value.model_run_count) ||
    !modelLabSafeInteger(value.model_vote_count) ||
    !modelLabSafeInteger(value.metric_estimate_count) ||
    value.activation_outcome !== "synthetic_or_insufficient" ||
    value.activation_allowed !== false
  ) {
    throw new TransportError("Model Lab inventory response was invalid", 200);
  }
  return value as unknown as ModelLabInventory["plans"][number];
}

/** Strict content-free projection. Invalid or partial inventory is never shown as zero. */
export function parseModelLabInventory(value: unknown): ModelLabInventory {
  if (
    !isRecord(value) || !hasExactKeys(value, MODEL_LAB_INVENTORY_KEYS) ||
    value.contract_version !== "model-lab-inventory-v1" ||
    value.scope !== "synthetic_only" || value.session_data_read !== false ||
    value.private_evidence_returned !== false ||
    !modelLabSafeInteger(value.registered_plan_count, MAX_MODEL_LAB_PLANS) ||
    !modelLabSafeInteger(value.synthetic_execution_count) ||
    !modelLabSafeInteger(value.model_run_count) ||
    !modelLabSafeInteger(value.model_vote_count) ||
    !modelLabSafeInteger(value.metric_estimate_count) ||
    value.activation_outcome !== "synthetic_or_insufficient" ||
    value.activation_allowed !== false || !Array.isArray(value.plans) ||
    value.plans.length > MAX_MODEL_LAB_PLANS
  ) {
    throw new TransportError("Model Lab inventory response was invalid", 200);
  }
  const plans = value.plans.map(parseModelLabPlan);
  const order = plans.map((plan) =>
    `${plan.plan_key}\u0000${plan.plan_version}\u0000${plan.plan_fingerprint}`
  );
  const totals = plans.reduce(
    (result, plan) => ({
      executions: result.executions + plan.synthetic_execution_count,
      runs: result.runs + plan.model_run_count,
      votes: result.votes + plan.model_vote_count,
      estimates: result.estimates + plan.metric_estimate_count,
    }),
    { executions: 0, runs: 0, votes: 0, estimates: 0 },
  );
  if (
    value.registered_plan_count !== plans.length ||
    new Set(plans.map((plan) => plan.plan_fingerprint)).size !== plans.length ||
    order.some((item, index) => index > 0 && order[index - 1] > item) ||
    !Object.values(totals).every(Number.isSafeInteger) ||
    value.synthetic_execution_count !== totals.executions ||
    value.model_run_count !== totals.runs || value.model_vote_count !== totals.votes ||
    value.metric_estimate_count !== totals.estimates
  ) {
    throw new TransportError("Model Lab inventory response was invalid", 200);
  }
  return { ...value, plans } as ModelLabInventory;
}

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
    typeof value.raw_transcripts !== "boolean"
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
      raw_transcripts: value.raw_transcripts as boolean,
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
    raw_transcripts: value.raw_transcripts as boolean,
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
    adapter: "claude_code_hooks",
    source: "claude_hook_ledger",
    content: "claude_hook_events",
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
    !["session_text_analysis", "operational_events"].includes(value.capability as string) ||
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
      isUtcCoverageTimestamp(value.checked_at)
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

const READINESS_EVIDENCE_CAPABILITIES = [
  "request_text",
  "response_text",
  "plan_text",
  "action_evidence",
  "decision_evidence",
  "feedback_text",
  "objective_verification",
] as const satisfies readonly MetricEvidenceCapability[];

const READINESS_ACTIONS = new Set<MetricReadinessAction>([
  "none",
  "run_local_analysis",
  "check_provider_compatibility",
  "update_provider_adapter",
  "collect_action_evidence",
  "collect_decision_evidence",
  "collect_feedback_evidence",
  "collect_objective_verification",
  "review_applicability",
  "review_evidence_coverage",
  "retry_analysis",
  "select_metric_for_analysis",
]);

type ReadinessCatalogEntry = {
  version: number;
  dimension: "prompt" | "collaboration" | "logic" | "outcome";
  displayName: string;
  unit: "ratio" | "risk_ratio";
  direction: "higher_is_better" | "lower_is_better";
  capabilityGroups: readonly (readonly MetricEvidenceCapability[])[];
};

const REQUEST_OR_FEEDBACK = ["feedback_text", "request_text"] as const;
const COACHING_READINESS_CATALOG = {
  "prompt.task_definition_coverage": {
    version: 2, dimension: "prompt", displayName: "Task definition coverage",
    unit: "ratio", direction: "higher_is_better", capabilityGroups: [REQUEST_OR_FEEDBACK],
  },
  "prompt.problem_evidence_quality": {
    version: 2, dimension: "prompt", displayName: "Problem evidence quality",
    unit: "ratio", direction: "higher_is_better", capabilityGroups: [REQUEST_OR_FEEDBACK],
  },
  "prompt.context_sufficiency": {
    version: 2, dimension: "prompt", displayName: "Context cue coverage",
    unit: "ratio", direction: "higher_is_better", capabilityGroups: [REQUEST_OR_FEEDBACK],
  },
  "prompt.constraint_precision": {
    version: 2, dimension: "prompt", displayName: "Constraint precision candidates",
    unit: "ratio", direction: "higher_is_better", capabilityGroups: [REQUEST_OR_FEEDBACK],
  },
  "prompt.acceptance_testability": {
    version: 2, dimension: "prompt", displayName: "Acceptance testability cues",
    unit: "ratio", direction: "higher_is_better", capabilityGroups: [REQUEST_OR_FEEDBACK],
  },
  "prompt.deliverable_contract": {
    version: 3, dimension: "prompt", displayName: "Deliverable contract cues",
    unit: "ratio", direction: "higher_is_better", capabilityGroups: [REQUEST_OR_FEEDBACK],
  },
  "collaboration.ambiguity_resolution": {
    version: 2, dimension: "collaboration", displayName: "Ambiguity-resolution candidates",
    unit: "ratio", direction: "higher_is_better", capabilityGroups: [REQUEST_OR_FEEDBACK],
  },
  "collaboration.clarification_yield": {
    version: 2, dimension: "collaboration", displayName: "Clarification yield candidates",
    unit: "ratio", direction: "higher_is_better",
    capabilityGroups: [["response_text"], REQUEST_OR_FEEDBACK],
  },
  "collaboration.exploration_conversion": {
    version: 2, dimension: "collaboration", displayName: "Exploration-to-plan conversion",
    unit: "ratio", direction: "higher_is_better",
    capabilityGroups: [["plan_text", "request_text", "response_text"]],
  },
  "collaboration.scope_change_discipline": {
    version: 2, dimension: "collaboration", displayName: "Scope-change acknowledgement",
    unit: "ratio", direction: "higher_is_better", capabilityGroups: [REQUEST_OR_FEEDBACK],
  },
  "collaboration.rework_candidate_rate": {
    version: 2, dimension: "collaboration", displayName: "Rework-candidate rate",
    unit: "risk_ratio", direction: "lower_is_better",
    capabilityGroups: [["response_text"], ["feedback_text"]],
  },
  "logic.decomposition_coverage": {
    version: 2, dimension: "logic", displayName: "Requirement-to-plan coverage",
    unit: "ratio", direction: "higher_is_better",
    capabilityGroups: [REQUEST_OR_FEEDBACK, ["plan_text"]],
  },
  "logic.hypothesis_test_linkage": {
    version: 2, dimension: "logic", displayName: "Hypothesis-to-test linkage",
    unit: "ratio", direction: "higher_is_better",
    capabilityGroups: [["objective_verification"]],
  },
  "logic.decision_rationale_coverage": {
    version: 3, dimension: "logic", displayName: "Decision-rationale coverage",
    unit: "ratio", direction: "higher_is_better",
    capabilityGroups: [["decision_evidence"]],
  },
  "logic.requirement_action_traceability": {
    version: 3, dimension: "logic", displayName: "Requirement-to-action traceability",
    unit: "ratio", direction: "higher_is_better",
    capabilityGroups: [REQUEST_OR_FEEDBACK, ["action_evidence"]],
  },
  "logic.open_loop_closure": {
    version: 2, dimension: "logic", displayName: "Open-loop closure candidates",
    unit: "ratio", direction: "higher_is_better",
    capabilityGroups: [["feedback_text", "request_text", "response_text"]],
  },
  "outcome.agent_claim_grounding": {
    version: 2, dimension: "outcome", displayName: "Agent claim grounding",
    unit: "ratio", direction: "higher_is_better",
    capabilityGroups: [["response_text"], ["objective_verification"]],
  },
  "outcome.verification_strategy_adequacy": {
    version: 2, dimension: "outcome", displayName: "Verification-strategy coverage",
    unit: "ratio", direction: "higher_is_better",
    capabilityGroups: [
      REQUEST_OR_FEEDBACK,
      ["objective_verification", "plan_text", "response_text"],
    ],
  },
  "outcome.first_pass_verification": {
    version: 2, dimension: "outcome", displayName: "First-pass verification",
    unit: "ratio", direction: "higher_is_better",
    capabilityGroups: [["objective_verification"]],
  },
  "outcome.verified_requirement_coverage": {
    version: 2, dimension: "outcome", displayName: "Verified requirement coverage",
    unit: "ratio", direction: "higher_is_better",
    capabilityGroups: [REQUEST_OR_FEEDBACK, ["objective_verification"]],
  },
} as const satisfies Record<string, ReadinessCatalogEntry>;

const COACHING_READINESS_KEYS = Object.keys(COACHING_READINESS_CATALOG) as Array<
  keyof typeof COACHING_READINESS_CATALOG
>;
const COACHING_READINESS_KEY_SET = new Set<string>(COACHING_READINESS_KEYS);
const READINESS_SAFE_TOKEN = /^[A-Za-z0-9][A-Za-z0-9._+:/-]{0,127}$/;
const PSEUDONYM = /^[a-f0-9]{64}$/;

const PROVIDER_CAPABILITY_REPORT_KEYS = new Set([
  "provider", "surface", "catalog_version", "compatibility_state",
  "provider_version", "decoder_key", "decoder_version", "checked_at",
  "capabilities", "structurally_attemptable_metric_count",
  "structurally_unsupported_metric_count", "structurally_unknown_metric_count",
]);
const PROVIDER_METRIC_CAPABILITY_KEYS = new Set([
  "capability", "state", "reason_code",
]);
const SESSION_READINESS_REPORT_KEYS = new Set([
  "session_id", "provider", "preset_id", "analysis_profile_key",
  "analysis_profile_version", "metric_pack_key", "metric_pack_version",
  "capability_report", "metrics",
]);
const METRIC_READINESS_KEYS = new Set([
  "metric_key", "metric_version", "dimension", "display_name", "unit",
  "direction", "radar_policy", "evidence_tier", "state", "reason_code",
  "next_actions", "capability_groups", "available_capabilities",
  "missing_capabilities", "latest_run_id",
]);

function hasExactKeys(value: Record<string, unknown>, keys: Set<string>): boolean {
  return Object.keys(value).length === keys.size &&
    Object.keys(value).every((key) => keys.has(key));
}

function isSafeNullableReadinessToken(value: unknown): value is string | null {
  return value === null ||
    (typeof value === "string" && READINESS_SAFE_TOKEN.test(value));
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function sameArray(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function sortedUniqueCapabilities(value: unknown): value is MetricEvidenceCapability[] {
  return Array.isArray(value) &&
    value.every((item) => READINESS_EVIDENCE_CAPABILITIES.includes(item)) &&
    sameArray(value, [...new Set(value)].sort());
}

function exactCapabilityGroups(
  value: unknown,
  expected: readonly (readonly MetricEvidenceCapability[])[],
): value is MetricEvidenceCapability[][] {
  return Array.isArray(value) && value.length === expected.length &&
    value.every((group, index) =>
      sortedUniqueCapabilities(group) && sameArray(group, expected[index]),
    );
}

function readinessRequirementsSatisfied(
  entry: ReadinessCatalogEntry,
  available: ReadonlySet<MetricEvidenceCapability>,
): boolean {
  return entry.capabilityGroups.every((group) =>
    group.some((capability) => available.has(capability)),
  );
}

export function parseProviderCapabilityReport(
  value: unknown,
  expectedProvider?: Provider,
): ProviderCapabilityReport {
  if (
    !isRecord(value) || !hasExactKeys(value, PROVIDER_CAPABILITY_REPORT_KEYS) ||
    !["codex", "claude_code", "synthetic"].includes(value.provider as string) ||
    (expectedProvider !== undefined && value.provider !== expectedProvider) ||
    value.surface !== "text_window" ||
    value.catalog_version !== "coaching-evidence-capabilities-v1" ||
    !["exact", "compatible", "degraded", "untested", "incompatible", "unavailable"]
      .includes(value.compatibility_state as string) ||
    !isSafeNullableReadinessToken(value.provider_version) ||
    !isSafeNullableReadinessToken(value.decoder_key) ||
    !isSafeNullableReadinessToken(value.decoder_version) ||
    !(
      value.checked_at === null ||
      isUtcCoverageTimestamp(value.checked_at)
    ) ||
    !isNonNegativeInteger(value.structurally_attemptable_metric_count) ||
    !isNonNegativeInteger(value.structurally_unsupported_metric_count) ||
    !isNonNegativeInteger(value.structurally_unknown_metric_count) ||
    !Array.isArray(value.capabilities) ||
    value.capabilities.length !== READINESS_EVIDENCE_CAPABILITIES.length
  ) {
    throw new TransportError("Provider metric capability response was invalid", 200);
  }

  const seen = new Set<string>();
  for (const item of value.capabilities) {
    if (
      !isRecord(item) || !hasExactKeys(item, PROVIDER_METRIC_CAPABILITY_KEYS) ||
      !READINESS_EVIDENCE_CAPABILITIES.includes(item.capability as MetricEvidenceCapability) ||
      !["supported", "unsupported", "unknown"].includes(item.state as string) ||
      ![
        "verified_by_compatible_decoder", "not_declared_by_decoder",
        "provider_adapter_unavailable", "compatibility_not_checked",
        "provider_incompatible", "capability_not_observed", "capability_unverified",
      ].includes(item.reason_code as string) ||
      seen.has(item.capability as string)
    ) {
      throw new TransportError("Provider metric capability response was invalid", 200);
    }
    seen.add(item.capability as string);
    const coherent =
      (item.state === "supported" && item.reason_code === "verified_by_compatible_decoder") ||
      (item.state === "unsupported" &&
        ["not_declared_by_decoder", "capability_not_observed"].includes(item.reason_code as string)) ||
      (item.state === "unknown" &&
        [
          "provider_adapter_unavailable", "compatibility_not_checked",
          "provider_incompatible", "capability_unverified",
        ].includes(item.reason_code as string));
    if (!coherent) {
      throw new TransportError("Provider metric capability response was invalid", 200);
    }
  }
  if (!READINESS_EVIDENCE_CAPABILITIES.every((item) => seen.has(item))) {
    throw new TransportError("Provider metric capability response was invalid", 200);
  }

  const compatibility = value.compatibility_state as ProviderCapabilityReport["compatibility_state"];
  const capabilities = value.capabilities as Array<{
    capability: MetricEvidenceCapability;
    state: "supported" | "unsupported" | "unknown";
    reason_code: string;
  }>;
  const noDecoder = value.decoder_key === null;
  const reportShapeCoherent = noDecoder
    ? value.decoder_version === null && value.provider_version === null &&
      value.checked_at === null && compatibility === "untested" &&
      capabilities.every((item) =>
        item.state === "unknown" && item.reason_code === "provider_adapter_unavailable")
    : typeof value.decoder_version === "string" &&
      (compatibility === "untested"
        ? value.provider_version === null && value.checked_at === null &&
          capabilities.every((item) =>
            item.reason_code === "not_declared_by_decoder" ||
            item.reason_code === "compatibility_not_checked")
        : typeof value.provider_version === "string" &&
          typeof value.checked_at === "string" &&
          (compatibility === "exact" || compatibility === "compatible"
            ? capabilities.every((item) => [
                "verified_by_compatible_decoder", "not_declared_by_decoder",
                "capability_not_observed", "capability_unverified",
              ].includes(item.reason_code))
            : capabilities.every((item) =>
                item.reason_code === "not_declared_by_decoder" ||
                item.reason_code === "provider_incompatible")));
  if (!reportShapeCoherent) {
    throw new TransportError("Provider metric capability response was invalid", 200);
  }

  const structurallyAvailable = new Set(
    capabilities
      .filter((item) =>
        item.reason_code !== "not_declared_by_decoder" &&
        item.reason_code !== "provider_adapter_unavailable")
      .map((item) => item.capability),
  );
  const attemptable = Object.values(COACHING_READINESS_CATALOG).filter((entry) =>
    readinessRequirementsSatisfied(entry, structurallyAvailable),
  ).length;
  const expectedUnknown = noDecoder ? COACHING_READINESS_KEYS.length : 0;
  const expectedUnsupported = noDecoder ? 0 : COACHING_READINESS_KEYS.length - attemptable;
  if (
    value.structurally_attemptable_metric_count !== attemptable ||
    value.structurally_unsupported_metric_count !== expectedUnsupported ||
    value.structurally_unknown_metric_count !== expectedUnknown ||
    attemptable + expectedUnsupported + expectedUnknown !== COACHING_READINESS_KEYS.length
  ) {
    throw new TransportError("Provider metric capability response was invalid", 200);
  }
  return value as unknown as ProviderCapabilityReport;
}

const METRIC_COVERAGE_REPORT_KEYS = new Set([
  "contract_version", "scope", "provider", "generated_at",
  "analysis_profile_key", "analysis_profile_version", "metric_pack_key",
  "metric_pack_version", "metric_catalog_version", "indexed_project_count",
  "indexed_session_count", "latest_profile_runs",
  "latest_completed_snapshot_count", "effective_automation_grant_count",
  "effective_automation_project_count", "unrecognized_result_record_count",
  "automation_scheduling_scope", "metrics", "capability_report",
  "local_index_snapshot_exact", "provider_history_completeness",
  "provider_snapshot_authority", "stored_result_contract_validation_performed",
  "provider_capability_snapshot_atomic",
  "full_catalog_automation_coverage_guaranteed", "metric_values_included",
  "product_source_authority", "population_completeness_verified",
  "comparison_authority", "snapshot_materialization_allowed",
  "recommendation_authority",
]);
const METRIC_COVERAGE_METRIC_KEYS = new Set([
  "metric_key", "metric_version", "latest_completed_run_count",
  "selected_run_count", "not_selected_run_count", "unknown_scope_run_count",
  "completed_selected_run_count", "contract_compatible_result_states",
  "contract_incompatible_result_count", "expected_result_absent_count",
  "compatible_provenance_cohort_count",
  "effective_automation_selected_project_count", "dimension", "display_name",
  "structural_support", "required_evidence",
]);
const LATEST_PROFILE_RUN_KEYS = new Set([
  "completed", "running", "failed", "never_run",
]);
const METRIC_RESULT_STATE_KEYS = new Set([
  "known", "unknown", "not_applicable", "abstained", "execution_error",
]);

function safeCountSum(values: readonly unknown[]): number | null {
  if (!values.every(isNonNegativeInteger)) return null;
  const total = (values as number[]).reduce((sum, value) => sum + value, 0);
  return Number.isSafeInteger(total) ? total : null;
}

function isUtcCoverageTimestamp(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|[+-]00:00)$/.exec(value);
  if (match === null) return false;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const maxDay = year >= 1 && month >= 1 && month <= 12
    ? new Date(Date.UTC(year, month, 0)).getUTCDate()
    : 0;
  return day >= 1 && day <= maxDay && Number(hourText) <= 23 &&
    Number(minuteText) <= 59 && Number(secondText) <= 59 &&
    !Number.isNaN(new Date(value).valueOf());
}

function invalidMetricCoverage(): never {
  throw new TransportError("Metric coverage response was invalid", 200);
}

/** Strict identifier-free projection of exact local-index coverage counts. */
export function parseMetricCoverageReport(
  value: unknown,
  expectedProvider?: Provider,
  expectedScope?: MetricCoverageReport["scope"],
): MetricCoverageReport {
  if (
    !isRecord(value) || !hasExactKeys(value, METRIC_COVERAGE_REPORT_KEYS) ||
    value.contract_version !== "metric-coverage-report-v1" ||
    !["provider_catalog", "one_project"].includes(value.scope as string) ||
    !["codex", "claude_code", "synthetic"].includes(value.provider as string) ||
    (expectedProvider !== undefined && value.provider !== expectedProvider) ||
    (expectedScope !== undefined && value.scope !== expectedScope) ||
    !isUtcCoverageTimestamp(value.generated_at) ||
    value.analysis_profile_key !== "coaching_profile" ||
    value.analysis_profile_version !== 1 ||
    value.metric_pack_key !== "experimental.redacted-text.coaching" ||
    value.metric_pack_version !== 3 ||
    value.metric_catalog_version !== "coaching-evidence-capabilities-v1" ||
    safeCountSum([
      value.indexed_project_count, value.indexed_session_count,
      value.latest_completed_snapshot_count, value.effective_automation_grant_count,
      value.effective_automation_project_count, value.unrecognized_result_record_count,
    ]) === null ||
    value.automation_scheduling_scope !== "new_or_changed_newest_bounded" ||
    !Array.isArray(value.metrics) ||
    value.metrics.length !== COACHING_READINESS_KEYS.length ||
    value.local_index_snapshot_exact !== true ||
    value.provider_history_completeness !== "unknown" ||
    value.provider_snapshot_authority !== "unavailable" ||
    value.stored_result_contract_validation_performed !== true ||
    value.provider_capability_snapshot_atomic !== false ||
    value.full_catalog_automation_coverage_guaranteed !== false ||
    value.metric_values_included !== false ||
    value.product_source_authority !== false ||
    value.population_completeness_verified !== false ||
    value.comparison_authority !== false ||
    value.snapshot_materialization_allowed !== false ||
    value.recommendation_authority !== false ||
    !isRecord(value.latest_profile_runs) ||
    !hasExactKeys(value.latest_profile_runs, LATEST_PROFILE_RUN_KEYS)
  ) {
    return invalidMetricCoverage();
  }

  const provider = value.provider as Provider;
  const capabilityReport = parseProviderCapabilityReport(
    value.capability_report,
    provider,
  );
  const runCount = safeCountSum([
    value.latest_profile_runs.completed, value.latest_profile_runs.running,
    value.latest_profile_runs.failed, value.latest_profile_runs.never_run,
  ]);
  const attemptedRunCount = safeCountSum([
    value.latest_profile_runs.completed, value.latest_profile_runs.running,
    value.latest_profile_runs.failed,
  ]);
  if (
    runCount === null || attemptedRunCount === null ||
    runCount !== value.indexed_session_count ||
    (value.latest_profile_runs.completed as number) >
      (value.latest_completed_snapshot_count as number) ||
    (value.latest_completed_snapshot_count as number) > attemptedRunCount ||
    (value.latest_completed_snapshot_count as number) >
      (value.indexed_session_count as number) ||
    (value.scope === "one_project" && value.indexed_project_count !== 1) ||
    (value.effective_automation_project_count as number) >
      (value.indexed_project_count as number) ||
    (value.effective_automation_project_count as number) >
      (value.effective_automation_grant_count as number) ||
    capabilityReport.catalog_version !== value.metric_catalog_version
  ) {
    return invalidMetricCoverage();
  }

  const declaredCapabilities = new Set(
    capabilityReport.capabilities
      .filter((item) =>
        item.reason_code !== "not_declared_by_decoder" &&
        item.reason_code !== "provider_adapter_unavailable")
      .map((item) => item.capability),
  );
  const allStructurallyUnknown =
    capabilityReport.structurally_unknown_metric_count ===
    COACHING_READINESS_KEYS.length;
  const supportCounts = { attemptable: 0, unsupported: 0, unknown: 0 };

  for (let index = 0; index < value.metrics.length; index += 1) {
    const metricCandidate: unknown = value.metrics[index];
    const metricKey = COACHING_READINESS_KEYS[index];
    const definition = COACHING_READINESS_CATALOG[metricKey];
    if (
      !isRecord(metricCandidate) ||
      !hasExactKeys(metricCandidate, METRIC_COVERAGE_METRIC_KEYS)
    ) {
      return invalidMetricCoverage();
    }
    const metric: Record<string, unknown> = metricCandidate;
    if (
      metric.metric_key !== metricKey || metric.metric_version !== definition.version ||
      metric.dimension !== definition.dimension ||
      metric.display_name !== definition.displayName ||
      !["attemptable", "unsupported", "unknown"].includes(
        metric.structural_support as string,
      ) ||
      !exactCapabilityGroups(metric.required_evidence, definition.capabilityGroups) ||
      safeCountSum([
        metric.latest_completed_run_count, metric.selected_run_count,
        metric.not_selected_run_count, metric.unknown_scope_run_count,
        metric.completed_selected_run_count,
        metric.contract_incompatible_result_count,
        metric.expected_result_absent_count,
        metric.compatible_provenance_cohort_count,
        metric.effective_automation_selected_project_count,
      ]) === null ||
      !isRecord(metric.contract_compatible_result_states) ||
      !hasExactKeys(metric.contract_compatible_result_states, METRIC_RESULT_STATE_KEYS)
    ) {
      return invalidMetricCoverage();
    }
    const compatibleResultCount = safeCountSum([
      metric.contract_compatible_result_states.known,
      metric.contract_compatible_result_states.unknown,
      metric.contract_compatible_result_states.not_applicable,
      metric.contract_compatible_result_states.abstained,
      metric.contract_compatible_result_states.execution_error,
    ]);
    const selectionTotal = safeCountSum([
      metric.selected_run_count, metric.not_selected_run_count,
      metric.unknown_scope_run_count,
    ]);
    const resultTotal = safeCountSum([
      compatibleResultCount, metric.contract_incompatible_result_count,
      metric.expected_result_absent_count,
    ]);
    const expectedSupport = allStructurallyUnknown
      ? "unknown"
      : definition.capabilityGroups.every((group) =>
          group.some((capability) => declaredCapabilities.has(capability)))
        ? "attemptable"
        : "unsupported";
    if (
      compatibleResultCount === null || selectionTotal === null || resultTotal === null ||
      metric.latest_completed_run_count !== value.latest_completed_snapshot_count ||
      selectionTotal !== metric.latest_completed_run_count ||
      metric.completed_selected_run_count !== metric.selected_run_count ||
      resultTotal !== metric.completed_selected_run_count ||
      (metric.compatible_provenance_cohort_count as number) > compatibleResultCount ||
      ((compatibleResultCount === 0) !==
        (metric.compatible_provenance_cohort_count === 0)) ||
      (metric.effective_automation_selected_project_count as number) >
        (value.effective_automation_project_count as number) ||
      metric.structural_support !== expectedSupport
    ) {
      return invalidMetricCoverage();
    }
    supportCounts[expectedSupport] += 1;
  }

  if (
    supportCounts.attemptable !==
      capabilityReport.structurally_attemptable_metric_count ||
    supportCounts.unsupported !==
      capabilityReport.structurally_unsupported_metric_count ||
    supportCounts.unknown !== capabilityReport.structurally_unknown_metric_count
  ) {
    return invalidMetricCoverage();
  }
  return value as unknown as MetricCoverageReport;
}

const READINESS_STATE_REASON_ACTION = new Map<string, readonly MetricReadinessAction[]>([
  ["known:measured", ["none"]],
  ["unknown:analysis_not_run", ["run_local_analysis"]],
  ["unknown:analysis_in_progress", ["none"]],
  ["unknown:result_unknown", ["review_applicability"]],
  ["unknown:metric_not_selected", ["select_metric_for_analysis"]],
  ["unknown:metric_scope_unknown", ["select_metric_for_analysis"]],
  ["unknown:provider_compatibility_unverified", ["check_provider_compatibility"]],
  ["unsupported:provider_adapter_unavailable", ["update_provider_adapter"]],
  ["abstained:result_abstained", ["review_evidence_coverage"]],
  ["incompatible:provider_incompatible", ["update_provider_adapter"]],
  ["not_applicable:explicitly_not_applicable", ["none"]],
  ["failed:provider_unavailable", ["check_provider_compatibility"]],
  ["failed:analysis_failed", ["retry_analysis"]],
  ["failed:result_failed", ["retry_analysis"]],
  ["failed:result_missing", ["retry_analysis"]],
]);

function actionsForMissingCapabilities(
  capabilities: readonly MetricEvidenceCapability[],
): MetricReadinessAction[] {
  const actionForCapability: Record<MetricEvidenceCapability, MetricReadinessAction> = {
    action_evidence: "collect_action_evidence",
    decision_evidence: "collect_decision_evidence",
    feedback_text: "collect_feedback_evidence",
    objective_verification: "collect_objective_verification",
    plan_text: "update_provider_adapter",
    request_text: "update_provider_adapter",
    response_text: "update_provider_adapter",
  };
  const mapped = capabilities.map((capability) => actionForCapability[capability]);
  return [...new Set(mapped)];
}

function parseMetricReadiness(
  value: unknown,
  entry: ReadinessCatalogEntry,
  expectedKey: string,
  capabilityReport: ProviderCapabilityReport,
): MetricReadiness {
  const expectedRadarPolicy = entry.direction === "higher_is_better"
    ? "direct_bounded_ratio"
    : "exact_value_only_unnormalized_lower_is_better";
  if (
    !isRecord(value) || !hasExactKeys(value, METRIC_READINESS_KEYS) ||
    value.metric_key !== expectedKey || value.metric_version !== entry.version ||
    value.dimension !== entry.dimension || value.display_name !== entry.displayName ||
    value.unit !== entry.unit || value.direction !== entry.direction ||
    value.radar_policy !== expectedRadarPolicy || value.evidence_tier !== "redacted_content" ||
    !["known", "unknown", "unsupported", "abstained", "incompatible", "not_applicable", "failed"]
      .includes(value.state as string) ||
    ![
      "measured", "analysis_not_run", "analysis_in_progress", "result_unknown",
      "result_abstained", "explicitly_not_applicable", "provider_capability_missing",
      "provider_adapter_unavailable", "provider_compatibility_unverified",
      "provider_incompatible", "provider_unavailable", "analysis_failed",
      "result_failed", "result_missing", "metric_not_selected",
      "metric_scope_unknown",
    ].includes(value.reason_code as string) ||
    !Array.isArray(value.next_actions) || value.next_actions.length < 1 ||
    value.next_actions.some((item) => !READINESS_ACTIONS.has(item as MetricReadinessAction)) ||
    new Set(value.next_actions).size !== value.next_actions.length ||
    !exactCapabilityGroups(value.capability_groups, entry.capabilityGroups) ||
    !sortedUniqueCapabilities(value.available_capabilities) ||
    !sortedUniqueCapabilities(value.missing_capabilities) ||
    !(value.latest_run_id === null ||
      (typeof value.latest_run_id === "string" && PSEUDONYM.test(value.latest_run_id)))
  ) {
    throw new TransportError("Session metric readiness response was invalid", 200);
  }

  const stateReason = `${String(value.state)}:${String(value.reason_code)}`;
  let expectedActions = READINESS_STATE_REASON_ACTION.get(stateReason);
  if (stateReason === "unsupported:provider_capability_missing") {
    expectedActions = actionsForMissingCapabilities(
      value.missing_capabilities as MetricEvidenceCapability[],
    );
  }
  if (!expectedActions || !sameArray(value.next_actions as string[], expectedActions)) {
    throw new TransportError("Session metric readiness response was invalid", 200);
  }

  const capabilityIndex = new Map(
    capabilityReport.capabilities.map((item) => [item.capability, item.state]),
  );
  const required = [...new Set(entry.capabilityGroups.flat())].sort();
  const expectedAvailable = required.filter(
    (capability) => capabilityIndex.get(capability) === "supported",
  );
  if (!sameArray(value.available_capabilities as string[], expectedAvailable)) {
    throw new TransportError("Session metric readiness response was invalid", 200);
  }
  let expectedMissing: MetricEvidenceCapability[] = [];
  if (value.reason_code === "provider_adapter_unavailable") {
    expectedMissing = required;
  } else if (value.reason_code === "provider_capability_missing") {
    expectedMissing = [...new Set(
      entry.capabilityGroups
        .filter((group) => !group.some((item) => capabilityIndex.get(item) === "supported"))
        .flat(),
    )].sort();
  }
  if (!sameArray(value.missing_capabilities as string[], expectedMissing)) {
    throw new TransportError("Session metric readiness response was invalid", 200);
  }

  const globalOverride = capabilityReport.decoder_key === null
    ? "unsupported:provider_adapter_unavailable"
    : capabilityReport.compatibility_state === "untested"
      ? "unknown:provider_compatibility_unverified"
      : capabilityReport.compatibility_state === "unavailable"
        ? "failed:provider_unavailable"
        : ["exact", "compatible"].includes(capabilityReport.compatibility_state)
          ? null
          : "incompatible:provider_incompatible";
  if (globalOverride !== null && stateReason !== globalOverride) {
    throw new TransportError("Session metric readiness response was invalid", 200);
  }
  if (value.reason_code === "analysis_not_run" && value.latest_run_id !== null) {
    throw new TransportError("Session metric readiness response was invalid", 200);
  }
  if ([
    "measured", "analysis_in_progress", "result_unknown", "result_abstained",
    "explicitly_not_applicable", "analysis_failed", "result_failed", "result_missing",
    "metric_not_selected", "metric_scope_unknown",
  ].includes(value.reason_code as string) && value.latest_run_id === null) {
    throw new TransportError("Session metric readiness response was invalid", 200);
  }
  return value as unknown as MetricReadiness;
}

export function parseSessionMetricReadinessReport(
  value: unknown,
  expectedSessionId?: string,
  expectedPresetId: TextAnalysisPresetId = "coaching_profile_v1",
): SessionMetricReadinessReport {
  if (
    !isRecord(value) || !hasExactKeys(value, SESSION_READINESS_REPORT_KEYS) ||
    typeof value.session_id !== "string" || !PSEUDONYM.test(value.session_id) ||
    (expectedSessionId !== undefined && value.session_id !== expectedSessionId) ||
    !["codex", "claude_code", "synthetic"].includes(value.provider as string) ||
    value.preset_id !== expectedPresetId || value.preset_id !== "coaching_profile_v1" ||
    value.analysis_profile_key !== "coaching_profile" ||
    value.analysis_profile_version !== 1 ||
    value.metric_pack_key !== "experimental.redacted-text.coaching" ||
    value.metric_pack_version !== 3 || !Array.isArray(value.metrics) ||
    value.metrics.length !== COACHING_READINESS_KEYS.length
  ) {
    throw new TransportError("Session metric readiness response was invalid", 200);
  }
  const provider = value.provider as Provider;
  const capabilityReport = parseProviderCapabilityReport(value.capability_report, provider);
  const metrics = value.metrics.map((metric, index) => {
    const expectedKey = COACHING_READINESS_KEYS[index];
    return parseMetricReadiness(
      metric,
      COACHING_READINESS_CATALOG[expectedKey],
      expectedKey,
      capabilityReport,
    );
  });
  if (
    new Set(metrics.map((metric) => `${metric.metric_key}.v${metric.metric_version}`)).size !==
    COACHING_READINESS_KEYS.length ||
    metrics.some((metric) => !COACHING_READINESS_KEY_SET.has(metric.metric_key))
  ) {
    throw new TransportError("Session metric readiness response was invalid", 200);
  }
  return value as unknown as SessionMetricReadinessReport;
}

const ANALYSIS_JOB_STATES = new Set<AnalysisJobState>([
  "queued", "preprocessing", "stage_n", "awaiting_approval", "completed",
  "partial", "failed", "cancelled", "superseded",
]);
const TERMINAL_ANALYSIS_JOB_STATES = new Set<AnalysisJobState>([
  "completed", "partial", "failed", "cancelled", "superseded",
]);
const ANALYSIS_JOB_PAGE_KEYS = new Set(["jobs", "limit", "offset"]);
const ANALYSIS_JOB_RECORD_KEYS = new Set([
  "job_id", "identity", "state", "stage_number",
  "progress_completed", "progress_total", "attempt_count", "max_attempts",
  "available_at", "cancel_requested", "last_error_code", "terminal_reason_code",
  "created_at", "updated_at", "terminal_at",
]);
const ANALYSIS_JOB_IDENTITY_KEYS = new Set([
  "kind", "provider", "project_id", "session_id", "input_fingerprint",
  "provenance_fingerprint", "metric_keys", "estimator_plan_version",
  "redactor_version", "provider_schema_version", "automation_grant_id",
  "local_only",
]);

function isSafeJobCode(value: unknown): value is string | null {
  return value === null ||
    (typeof value === "string" && READINESS_SAFE_TOKEN.test(value));
}

function isUtcJobTimestamp(value: unknown): value is string {
  return typeof value === "string" &&
    /(?:Z|\+00:00)$/.test(value) &&
    Number.isFinite(Date.parse(value));
}

function parseAnalysisJobIdentity(value: unknown): AnalysisJobIdentity {
  if (
    !isRecord(value) || !hasExactKeys(value, ANALYSIS_JOB_IDENTITY_KEYS) ||
    !["session_quality", "synthetic_validation"].includes(value.kind as string) ||
    !["codex", "claude_code", "synthetic"].includes(value.provider as string) ||
    typeof value.project_id !== "string" || !PSEUDONYM.test(value.project_id) ||
    typeof value.session_id !== "string" || !PSEUDONYM.test(value.session_id) ||
    typeof value.input_fingerprint !== "string" || !PSEUDONYM.test(value.input_fingerprint) ||
    typeof value.provenance_fingerprint !== "string" || !PSEUDONYM.test(value.provenance_fingerprint) ||
    !Array.isArray(value.metric_keys) || value.metric_keys.length < 1 ||
    value.metric_keys.length > 100 ||
    value.metric_keys.some((key) => typeof key !== "string" || !READINESS_SAFE_TOKEN.test(key)) ||
    new Set(value.metric_keys).size !== value.metric_keys.length ||
    !sameArray(value.metric_keys, [...value.metric_keys].sort()) ||
    typeof value.estimator_plan_version !== "string" ||
    !READINESS_SAFE_TOKEN.test(value.estimator_plan_version) ||
    typeof value.redactor_version !== "string" ||
    !READINESS_SAFE_TOKEN.test(value.redactor_version) ||
    typeof value.provider_schema_version !== "string" ||
    !READINESS_SAFE_TOKEN.test(value.provider_schema_version) ||
    !(
      value.automation_grant_id === null ||
      (typeof value.automation_grant_id === "string" &&
        PSEUDONYM.test(value.automation_grant_id))
    ) ||
    value.local_only !== true
  ) {
    throw new TransportError("Analysis job response was invalid", 200);
  }
  return {
    kind: value.kind as AnalysisJobIdentity["kind"],
    provider: value.provider as Provider,
    project_id: value.project_id,
    session_id: value.session_id,
    input_fingerprint: value.input_fingerprint,
    provenance_fingerprint: value.provenance_fingerprint,
    metric_keys: [...value.metric_keys] as string[],
    estimator_plan_version: value.estimator_plan_version,
    redactor_version: value.redactor_version,
    provider_schema_version: value.provider_schema_version,
    automation_grant_id: value.automation_grant_id as string | null,
    local_only: true,
  };
}

/** Strictly validate the browser-safe durable job response. */
export function parseAnalysisJobRecord(
  value: unknown,
  expectedJobId?: string,
): AnalysisJobRecord {
  if (
    !isRecord(value) || !hasExactKeys(value, ANALYSIS_JOB_RECORD_KEYS) ||
    typeof value.job_id !== "string" || !PSEUDONYM.test(value.job_id) ||
    (expectedJobId !== undefined && value.job_id !== expectedJobId) ||
    !ANALYSIS_JOB_STATES.has(value.state as AnalysisJobState) ||
    !Number.isInteger(value.progress_completed) ||
    (value.progress_completed as number) < 0 ||
    !Number.isInteger(value.progress_total) ||
    (value.progress_total as number) < 1 ||
    (value.progress_total as number) > 1_000_000 ||
    (value.progress_completed as number) > (value.progress_total as number) ||
    !Number.isInteger(value.attempt_count) ||
    (value.attempt_count as number) < 0 || (value.attempt_count as number) > 5 ||
    !Number.isInteger(value.max_attempts) ||
    (value.max_attempts as number) < 1 || (value.max_attempts as number) > 5 ||
    (value.attempt_count as number) > (value.max_attempts as number) ||
    typeof value.cancel_requested !== "boolean" ||
    !isUtcJobTimestamp(value.available_at) ||
    !isUtcJobTimestamp(value.created_at) ||
    !isUtcJobTimestamp(value.updated_at) ||
    Date.parse(value.updated_at) < Date.parse(value.created_at) ||
    !isSafeJobCode(value.last_error_code) ||
    !isSafeJobCode(value.terminal_reason_code)
  ) {
    throw new TransportError("Analysis job response was invalid", 200);
  }
  const state = value.state as AnalysisJobState;
  const terminal = TERMINAL_ANALYSIS_JOB_STATES.has(state);
  const stageValid = state === "stage_n"
    ? Number.isInteger(value.stage_number) &&
      (value.stage_number as number) >= 1 && (value.stage_number as number) <= 32
    : value.stage_number === null;
  const terminalValid = terminal
    ? isUtcJobTimestamp(value.terminal_at) &&
      typeof value.terminal_reason_code === "string" &&
      Date.parse(value.terminal_at) >= Date.parse(value.created_at)
    : value.terminal_at === null && value.terminal_reason_code === null;
  if (!stageValid || !terminalValid) {
    throw new TransportError("Analysis job response was invalid", 200);
  }
  const identity = parseAnalysisJobIdentity(value.identity);
  return {
    job_id: value.job_id,
    identity,
    state,
    stage_number: value.stage_number as number | null,
    progress_completed: value.progress_completed as number,
    progress_total: value.progress_total as number,
    attempt_count: value.attempt_count as number,
    max_attempts: value.max_attempts as number,
    available_at: value.available_at,
    cancel_requested: value.cancel_requested,
    last_error_code: value.last_error_code as string | null,
    terminal_reason_code: value.terminal_reason_code as string | null,
    created_at: value.created_at,
    updated_at: value.updated_at,
    terminal_at: value.terminal_at as string | null,
  };
}

export function parseAnalysisJobPage(
  value: unknown,
  expectedLimit: number,
  expectedOffset: number,
  expectedState: AnalysisJobState | null = null,
): AnalysisJobPage {
  if (
    !isRecord(value) || !hasExactKeys(value, ANALYSIS_JOB_PAGE_KEYS) ||
    value.limit !== expectedLimit || value.offset !== expectedOffset ||
    !Array.isArray(value.jobs) || value.jobs.length > expectedLimit
  ) {
    throw new TransportError("Analysis job page response was invalid", 200);
  }
  const jobs = value.jobs.map((job) => parseAnalysisJobRecord(job));
  if (
    new Set(jobs.map((job) => job.job_id)).size !== jobs.length ||
    (expectedState !== null && jobs.some((job) => job.state !== expectedState))
  ) {
    throw new TransportError("Analysis job page response was invalid", 200);
  }
  return { jobs, limit: expectedLimit, offset: expectedOffset };
}

const AUTOMATION_GRANT_RECORD_KEYS = new Set([
  "created_at", "expires_at", "grant_id", "last_checked_at",
  "last_error_code", "next_check_at", "renewed_at", "revision",
  "revoked_at", "scope", "state",
]);
const AUTOMATION_GRANT_SCOPE_KEYS = new Set([
  "provider", "project_id", "metric_keys", "newest_session_limit",
  "check_interval_seconds", "resource_policy", "local_only",
  "remote_requires_fresh_approval",
]);
const AUTOMATION_RESOURCE_POLICY_KEYS = new Set([
  "route", "max_gpu_workers", "max_cpu_workers", "pause_on_battery",
  "maximum_session_seconds",
]);
const AUTOMATION_GRANT_CREATE_KEYS = new Set([
  "provider", "project_id", "metric_keys", "newest_session_limit",
  "check_interval_seconds", "resource_policy",
]);
const AUTOMATION_POLL_RESULT_KEYS = new Set([
  "grants_checked", "grants_revoked",
  "grants_power_paused", "grants_policy_unsupported", "candidates_seen",
  "power_external_observations", "power_battery_observations",
  "power_unknown_observations",
  "jobs_created", "jobs_reused", "jobs_superseded", "failures",
  "maximum_session_runtime_deadline_enforced",
  "session_quality_result_publication_deadline_enforced",
  "blocking_execution_preemption_enforced",
]);
const AUTOMATION_GRANT_LIFETIME_MS = 30 * 24 * 60 * 60 * 1_000;

function parseAutomationResourcePolicy(value: unknown): AutomationResourcePolicy {
  if (
    !isRecord(value) || !hasExactKeys(value, AUTOMATION_RESOURCE_POLICY_KEYS) ||
    !["fast", "balanced", "deep"].includes(value.route as string) ||
    value.max_gpu_workers !== 1 ||
    !Number.isInteger(value.max_cpu_workers) ||
    (value.max_cpu_workers as number) < 1 || (value.max_cpu_workers as number) > 4 ||
    typeof value.pause_on_battery !== "boolean" ||
    !Number.isInteger(value.maximum_session_seconds) ||
    (value.maximum_session_seconds as number) < 60 ||
    (value.maximum_session_seconds as number) > 14_400
  ) {
    throw new TransportError("Automation resource policy response was invalid", 200);
  }
  return {
    route: value.route as AutomationResourcePolicy["route"],
    max_gpu_workers: 1,
    max_cpu_workers: value.max_cpu_workers as number,
    pause_on_battery: value.pause_on_battery,
    maximum_session_seconds: value.maximum_session_seconds as number,
  };
}

function parseAutomationGrantScope(value: unknown): AutomationGrantScope {
  if (
    !isRecord(value) || !hasExactKeys(value, AUTOMATION_GRANT_SCOPE_KEYS) ||
    !["codex", "claude_code", "synthetic"].includes(value.provider as string) ||
    typeof value.project_id !== "string" || !PSEUDONYM.test(value.project_id) ||
    !Array.isArray(value.metric_keys) || value.metric_keys.length < 1 ||
    value.metric_keys.length > 100 ||
    value.metric_keys.some((key) =>
      typeof key !== "string" || !READINESS_SAFE_TOKEN.test(key)
    ) ||
    new Set(value.metric_keys).size !== value.metric_keys.length ||
    !sameArray(value.metric_keys, [...value.metric_keys].sort()) ||
    !Number.isInteger(value.newest_session_limit) ||
    (value.newest_session_limit as number) < 1 ||
    (value.newest_session_limit as number) > 100 ||
    !Number.isInteger(value.check_interval_seconds) ||
    (value.check_interval_seconds as number) < 60 ||
    (value.check_interval_seconds as number) > 86_400 ||
    value.local_only !== true || value.remote_requires_fresh_approval !== true
  ) {
    throw new TransportError("Automation grant scope response was invalid", 200);
  }
  return {
    provider: value.provider as Provider,
    project_id: value.project_id,
    metric_keys: [...value.metric_keys] as string[],
    newest_session_limit: value.newest_session_limit as number,
    check_interval_seconds: value.check_interval_seconds as number,
    resource_policy: parseAutomationResourcePolicy(value.resource_policy),
    local_only: true,
    remote_requires_fresh_approval: true,
  };
}

function sameAutomationResourcePolicy(
  left: AutomationResourcePolicy,
  right: AutomationResourcePolicy,
): boolean {
  return left.route === right.route &&
    left.max_gpu_workers === right.max_gpu_workers &&
    left.max_cpu_workers === right.max_cpu_workers &&
    left.pause_on_battery === right.pause_on_battery &&
    left.maximum_session_seconds === right.maximum_session_seconds;
}

export function sameAutomationGrantScope(
  left: AutomationGrantScope,
  right: AutomationGrantScope,
): boolean {
  return left.provider === right.provider &&
    left.project_id === right.project_id &&
    sameArray(left.metric_keys, right.metric_keys) &&
    left.newest_session_limit === right.newest_session_limit &&
    left.check_interval_seconds === right.check_interval_seconds &&
    left.local_only === right.local_only &&
    left.remote_requires_fresh_approval === right.remote_requires_fresh_approval &&
    sameAutomationResourcePolicy(left.resource_policy, right.resource_policy);
}

function parseAutomationGrantCreateRequest(
  value: unknown,
): AutomationGrantCreateRequest {
  if (!isRecord(value) || !hasExactKeys(value, AUTOMATION_GRANT_CREATE_KEYS)) {
    throw new TransportError("Automation grant request was invalid", 400);
  }
  const scope = parseAutomationGrantScope({
    ...value,
    local_only: true,
    remote_requires_fresh_approval: true,
  });
  if (
    scope.resource_policy.route !== "balanced" ||
    scope.resource_policy.max_gpu_workers !== 1 ||
    scope.resource_policy.max_cpu_workers !== 1 ||
    scope.resource_policy.pause_on_battery !== true ||
    scope.resource_policy.maximum_session_seconds !== 1_800
  ) {
    throw new TransportError("Automation grant request was invalid", 400);
  }
  return {
    provider: scope.provider,
    project_id: scope.project_id,
    metric_keys: scope.metric_keys,
    newest_session_limit: scope.newest_session_limit,
    check_interval_seconds: scope.check_interval_seconds,
    resource_policy: {
      route: "balanced",
      max_gpu_workers: 1,
      max_cpu_workers: 1,
      pause_on_battery: true,
      maximum_session_seconds: 1_800,
    },
  };
}

function scopeForAutomationRequest(
  request: AutomationGrantCreateRequest,
): AutomationGrantScope {
  return {
    ...request,
    local_only: true,
    remote_requires_fresh_approval: true,
  };
}

/** Strictly validate a content-free renewable automation grant. */
export function parseAutomationGrantRecord(
  value: unknown,
  expectedGrantId?: string,
  expectedScope?: AutomationGrantScope,
): AutomationGrantRecord {
  if (
    !isRecord(value) || !hasExactKeys(value, AUTOMATION_GRANT_RECORD_KEYS) ||
    typeof value.grant_id !== "string" || !PSEUDONYM.test(value.grant_id) ||
    (expectedGrantId !== undefined && value.grant_id !== expectedGrantId) ||
    !Number.isSafeInteger(value.revision) || (value.revision as number) < 1 ||
    !["active", "revoked", "expired"].includes(value.state as string) ||
    !isUtcJobTimestamp(value.created_at) ||
    !isUtcJobTimestamp(value.renewed_at) ||
    !isUtcJobTimestamp(value.expires_at) ||
    !isUtcJobTimestamp(value.next_check_at) ||
    Date.parse(value.renewed_at) < Date.parse(value.created_at) ||
    Date.parse(value.expires_at) - Date.parse(value.renewed_at) !==
      AUTOMATION_GRANT_LIFETIME_MS ||
    Date.parse(value.next_check_at) < Date.parse(value.created_at) ||
    !(
      value.last_checked_at === null ||
      (isUtcJobTimestamp(value.last_checked_at) &&
        Date.parse(value.last_checked_at) >= Date.parse(value.created_at))
    ) ||
    !(
      value.revoked_at === null ||
      (isUtcJobTimestamp(value.revoked_at) &&
        Date.parse(value.revoked_at) >= Date.parse(value.created_at))
    ) ||
    !isSafeJobCode(value.last_error_code) ||
    ((value.state === "revoked") !== (value.revoked_at !== null))
  ) {
    throw new TransportError("Automation grant response was invalid", 200);
  }
  const scope = parseAutomationGrantScope(value.scope);
  if (expectedScope !== undefined && !sameAutomationGrantScope(scope, expectedScope)) {
    throw new TransportError("Automation grant response was invalid", 200);
  }
  return {
    grant_id: value.grant_id,
    revision: value.revision as number,
    scope,
    state: value.state as AutomationGrantRecord["state"],
    created_at: value.created_at,
    renewed_at: value.renewed_at,
    expires_at: value.expires_at,
    next_check_at: value.next_check_at,
    last_checked_at: value.last_checked_at as string | null,
    revoked_at: value.revoked_at as string | null,
    last_error_code: value.last_error_code as string | null,
  };
}

export function parseAutomationGrantList(
  value: unknown,
  expectedProvider: Provider,
): AutomationGrantRecord[] {
  if (!Array.isArray(value) || value.length > 1_000) {
    throw new TransportError("Automation grant list response was invalid", 200);
  }
  const records = value.map((record) => parseAutomationGrantRecord(record));
  if (
    new Set(records.map((record) => record.grant_id)).size !== records.length ||
    records.some((record) => record.scope.provider !== expectedProvider)
  ) {
    throw new TransportError("Automation grant list response was invalid", 200);
  }
  return records;
}

export function parseAutomationPollResult(value: unknown): AutomationPollResult {
  const countKeys = [...AUTOMATION_POLL_RESULT_KEYS].filter((key) => ![
    "maximum_session_runtime_deadline_enforced",
    "session_quality_result_publication_deadline_enforced",
    "blocking_execution_preemption_enforced",
  ].includes(key));
  if (
    !isRecord(value) || !hasExactKeys(value, AUTOMATION_POLL_RESULT_KEYS) ||
    value.maximum_session_runtime_deadline_enforced !== false ||
    value.session_quality_result_publication_deadline_enforced !== true ||
    value.blocking_execution_preemption_enforced !== false ||
    countKeys.some((key) =>
      !Number.isSafeInteger(value[key]) || (value[key] as number) < 0
    ) ||
    (value.grants_revoked as number) +
      (value.grants_power_paused as number) +
      (value.grants_policy_unsupported as number) >
      (value.grants_checked as number) ||
    (value.grants_policy_unsupported as number) > (value.failures as number) ||
    (value.power_external_observations as number) +
      (value.power_battery_observations as number) +
      (value.power_unknown_observations as number) +
      (value.grants_policy_unsupported as number) +
      (value.grants_revoked as number) !==
      (value.grants_checked as number) ||
    (value.grants_power_paused as number) !==
      (value.power_battery_observations as number) +
      (value.power_unknown_observations as number) ||
    (value.jobs_created as number) + (value.jobs_reused as number) >
      (value.candidates_seen as number) ||
    (value.jobs_superseded as number) >
      (value.jobs_created as number) + (value.jobs_reused as number)
  ) {
    throw new TransportError("Automation poll response was invalid", 200);
  }
  return value as unknown as AutomationPollResult;
}

const PREVIEW_KEYS = new Set([
  "preview_id", "created_at", "expires_at", "binding", "messages",
]);
const PREVIEW_BINDING_KEYS = new Set([
  "provider", "session_id", "analysis_window_fingerprint", "metric_keys",
  "destination", "exact_model", "estimator_plan_version", "redactor_version",
  "retention_class", "message_count", "character_count", "cost_state",
  "estimated_cost_microunits", "cost_currency",
]);
const PREVIEW_MESSAGE_KEYS = new Set(["role", "kind", "language", "text"]);
const ANALYSIS_OUTCOME_KEYS = new Set([
  "run_id", "status", "result_count", "applied", "analysis_profile_key",
  "analysis_profile_version",
]);
const SESSION_ANALYSIS_RESPONSE_KEYS = new Set(["run", "results"]);
const SESSION_ANALYSIS_RUN_KEYS = new Set([
  "adapter_version", "analysis_profile_key", "analysis_profile_version",
  "consent_policy_version", "consent_purpose", "content_schema_version",
  "data_tier", "failure_code", "finished_at", "input_fingerprint",
  "local_only", "metric_engine_version", "metric_pack_key",
  "metric_pack_version", "metric_scope_state", "model_plan_fingerprint",
  "provider", "provider_version", "redactor_version", "request_fingerprint",
  "run_id", "schema_version", "selected_metric_keys", "session_id",
  "source_schema_version", "started_at", "status",
]);
const SESSION_ANALYSIS_RESULT_REQUIRED_KEYS = new Set([
  "aggregation_method", "algorithm_id", "algorithm_version", "applicability",
  "computed_at", "coverage", "direction", "eligible_count", "error_code",
  "evidence", "evidence_data_tier", "explanation_code", "fraction", "key",
  "metric_schema_version", "model_id", "model_license", "model_revision",
  "numeric_value", "observed_count", "prompt_version", "rubric_version",
  "signals", "source", "tokenizer_id", "unit", "value_state", "version",
]);
const SESSION_ANALYSIS_RESULT_OPTIONAL_KEYS = new Set([
  "confidence", "description", "dimension", "display_name",
]);
const PREVIEW_MESSAGE_KINDS = new Set([
  "request", "response", "plan", "action", "verification", "decision",
  "feedback", "summary",
]);
const PREVIEW_LANGUAGES = new Set(["en", "pl", "mixed", "unknown"]);

function isUtcTimestamp(value: unknown): value is string {
  return typeof value === "string" &&
    /(?:Z|\+00:00)$/.test(value) &&
    Number.isFinite(Date.parse(value));
}

function parseLocalPreviewBinding(
  value: unknown,
  expectedSessionId: string,
  expectedPresetId: TextAnalysisPresetId,
) {
  if (
    !isRecord(value) || !hasExactKeys(value, PREVIEW_BINDING_KEYS) ||
    value.provider !== "codex" ||
    value.session_id !== expectedSessionId || !PSEUDONYM.test(expectedSessionId) ||
    typeof value.analysis_window_fingerprint !== "string" ||
    !PSEUDONYM.test(value.analysis_window_fingerprint) ||
    !Array.isArray(value.metric_keys) || value.metric_keys.length < 1 ||
    value.metric_keys.length > 100 ||
    value.metric_keys.some((key) => typeof key !== "string" || !READINESS_SAFE_TOKEN.test(key)) ||
    new Set(value.metric_keys).size !== value.metric_keys.length ||
    value.destination !== "local" || value.exact_model !== "none" ||
    typeof value.estimator_plan_version !== "string" ||
    !READINESS_SAFE_TOKEN.test(value.estimator_plan_version) ||
    typeof value.redactor_version !== "string" ||
    !READINESS_SAFE_TOKEN.test(value.redactor_version) ||
    value.retention_class !== "local_ephemeral" ||
    !Number.isInteger(value.message_count) ||
    (value.message_count as number) < 1 || (value.message_count as number) > 500 ||
    !Number.isInteger(value.character_count) ||
    (value.character_count as number) < 1 || (value.character_count as number) > 500_000 ||
    value.cost_state !== "not_applicable" ||
    value.estimated_cost_microunits !== null || value.cost_currency !== null
  ) {
    throw new TransportError("Redaction preview response was invalid", 200);
  }
  if (expectedPresetId === "coaching_profile_v1") {
    const keys = value.metric_keys as string[];
    if (
      keys.length !== COACHING_READINESS_KEYS.length ||
      keys.some((key) => !COACHING_READINESS_KEY_SET.has(key))
    ) {
      throw new TransportError("Redaction preview response was invalid", 200);
    }
  }
  return value;
}

/**
 * Validate the only secret-bearing browser DTO. Unknown fields and every
 * remote/cost-bearing shape fail closed before preview text reaches React.
 */
export function parseSessionQualityAnalysisPreview(
  value: unknown,
  expectedSessionId: string,
  expectedPresetId: TextAnalysisPresetId = "coaching_profile_v1",
): SessionQualityAnalysisPreview {
  if (
    !isRecord(value) || !hasExactKeys(value, PREVIEW_KEYS) ||
    typeof value.preview_id !== "string" || !PSEUDONYM.test(value.preview_id) ||
    !isUtcTimestamp(value.created_at) || !isUtcTimestamp(value.expires_at) ||
    Date.parse(value.expires_at) - Date.parse(value.created_at) !== 600_000 ||
    !Array.isArray(value.messages)
  ) {
    throw new TransportError("Redaction preview response was invalid", 200);
  }
  const binding = parseLocalPreviewBinding(
    value.binding,
    expectedSessionId,
    expectedPresetId,
  );
  const messages = value.messages;
  if (messages.length !== binding.message_count) {
    throw new TransportError("Redaction preview response was invalid", 200);
  }
  let characterCount = 0;
  for (const message of messages) {
    if (
      !isRecord(message) || !hasExactKeys(message, PREVIEW_MESSAGE_KEYS) ||
      !["user", "agent"].includes(message.role as string) ||
      !PREVIEW_MESSAGE_KINDS.has(message.kind as string) ||
      !PREVIEW_LANGUAGES.has(message.language as string) ||
      typeof message.text !== "string" || message.text.length < 1 ||
      Array.from(message.text).length > 32_000
    ) {
      throw new TransportError("Redaction preview response was invalid", 200);
    }
    characterCount += Array.from(message.text).length;
  }
  if (characterCount !== binding.character_count) {
    throw new TransportError("Redaction preview response was invalid", 200);
  }
  return value as unknown as SessionQualityAnalysisPreview;
}

export function parseSessionQualityAnalysisOutcome(
  value: unknown,
): SessionQualityAnalysisOutcome {
  if (
    !isRecord(value) || !hasExactKeys(value, ANALYSIS_OUTCOME_KEYS) ||
    typeof value.run_id !== "string" || !PSEUDONYM.test(value.run_id) ||
    !["running", "completed", "failed"].includes(value.status as string) ||
    !Number.isInteger(value.result_count) ||
    (value.result_count as number) < 0 || (value.result_count as number) > 100 ||
    typeof value.applied !== "boolean" ||
    typeof value.analysis_profile_key !== "string" ||
    !READINESS_SAFE_TOKEN.test(value.analysis_profile_key) ||
    !Number.isInteger(value.analysis_profile_version) ||
    (value.analysis_profile_version as number) < 1
  ) {
    throw new TransportError("Local analysis response was invalid", 200);
  }
  return value as unknown as SessionQualityAnalysisOutcome;
}

function hasRequiredAndAllowedKeys(
  value: Record<string, unknown>,
  required: ReadonlySet<string>,
  optional: ReadonlySet<string>,
): boolean {
  return [...required].every((key) => Object.hasOwn(value, key)) &&
    Object.keys(value).every((key) => required.has(key) || optional.has(key));
}

/**
 * Validate content-free run scope before any quality adapter sees the response.
 * Exact scopes are canonical and must match completed result keys one-for-one;
 * legacy rows deliberately keep an empty selection because their omission
 * provenance is unknowable.
 */
export function parseSessionAnalysisRunResponse(
  value: unknown,
  expected: { sessionId?: string; runId?: string } = {},
): SessionAnalysisRunResponse {
  if (
    !isRecord(value) || !hasExactKeys(value, SESSION_ANALYSIS_RESPONSE_KEYS) ||
    !isRecord(value.run) || !hasExactKeys(value.run, SESSION_ANALYSIS_RUN_KEYS) ||
    !Array.isArray(value.results) || value.results.length > 100
  ) {
    throw new TransportError("Quality analysis response was invalid", 200);
  }
  const run = value.run;
  const positiveInteger = (candidate: unknown) =>
    Number.isSafeInteger(candidate) && (candidate as number) > 0;
  const safeVersion = (candidate: unknown) =>
    typeof candidate === "string" && READINESS_SAFE_TOKEN.test(candidate);
  if (
    typeof run.run_id !== "string" || !PSEUDONYM.test(run.run_id) ||
    typeof run.session_id !== "string" || !PSEUDONYM.test(run.session_id) ||
    (expected.runId !== undefined && run.run_id !== expected.runId) ||
    (expected.sessionId !== undefined && run.session_id !== expected.sessionId) ||
    ![run.request_fingerprint, run.input_fingerprint, run.model_plan_fingerprint]
      .every((item) => typeof item === "string" && PSEUDONYM.test(item)) ||
    ![run.analysis_profile_key, run.metric_pack_key, run.consent_policy_version,
      run.provider_version, run.adapter_version, run.source_schema_version,
      run.content_schema_version, run.metric_engine_version, run.redactor_version]
      .every(safeVersion) ||
    !positiveInteger(run.analysis_profile_version) ||
    !positiveInteger(run.metric_pack_version) ||
    !positiveInteger(run.schema_version) ||
    run.data_tier !== "redacted_content" || run.consent_purpose !== "text_analysis" ||
    run.local_only !== true ||
    !["codex", "claude_code", "synthetic"].includes(run.provider as string) ||
    !["running", "completed", "failed"].includes(run.status as string) ||
    !isUtcTimestamp(run.started_at) ||
    (run.finished_at !== null && !isUtcTimestamp(run.finished_at)) ||
    (run.failure_code !== null && !safeVersion(run.failure_code)) ||
    !Array.isArray(run.selected_metric_keys) || run.selected_metric_keys.length > 100 ||
    run.selected_metric_keys.some((key) => !safeVersion(key)) ||
    !sameArray(
      run.selected_metric_keys as string[],
      [...new Set(run.selected_metric_keys as string[])].sort(),
    ) ||
    !(
      (run.metric_scope_state === "exact" && run.selected_metric_keys.length > 0) ||
      (run.metric_scope_state === "legacy_unknown" && run.selected_metric_keys.length === 0)
    ) ||
    (run.status === "completed" && (run.finished_at === null || run.failure_code !== null)) ||
    (run.status === "running" && (run.finished_at !== null || run.failure_code !== null)) ||
    (run.status === "failed" && (run.finished_at === null || run.failure_code === null))
  ) {
    throw new TransportError("Quality analysis response was invalid", 200);
  }

  const resultKeys: string[] = [];
  const resultIdentities = new Set<string>();
  for (const result of value.results) {
    if (
      !isRecord(result) ||
      !hasRequiredAndAllowedKeys(
        result,
        SESSION_ANALYSIS_RESULT_REQUIRED_KEYS,
        SESSION_ANALYSIS_RESULT_OPTIONAL_KEYS,
      ) ||
      typeof result.key !== "string" || !READINESS_SAFE_TOKEN.test(result.key) ||
      !positiveInteger(result.version)
    ) {
      throw new TransportError("Quality analysis response was invalid", 200);
    }
    const identity = `${result.key}@${String(result.version)}`;
    if (resultIdentities.has(identity)) {
      throw new TransportError("Quality analysis response was invalid", 200);
    }
    resultIdentities.add(identity);
    resultKeys.push(result.key);
  }
  if (
    (run.status === "completed" && run.metric_scope_state === "exact" &&
      !sameArray([...new Set(resultKeys)].sort(), run.selected_metric_keys as string[]))
  ) {
    throw new TransportError("Quality analysis response was invalid", 200);
  }
  return value as unknown as SessionAnalysisRunResponse;
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
    requirePrivateNoStore = false,
  ): Promise<T> {
    const target = assertSameOriginRelativePath(path, origin);
    const method = (init.method ?? "GET").toUpperCase();
    const mutation = !["GET", "HEAD", "OPTIONS"].includes(method);
    let csrfToken = await ensureBrowserSession(signal);
    const send = (csrf: string) =>
      fetchRequest(target, {
        ...init,
        cache: requirePrivateNoStore ? "no-store" : init.cache,
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
    if (
      requirePrivateNoStore &&
      (
        response.headers.get("cache-control") !== "no-store, private" ||
        response.headers.get("pragma") !== "no-cache"
      )
    ) {
      throw new TransportError("Private local response was not cache-safe", response.status);
    }
    if (!isJsonResponse(response)) {
      throw new TransportError("Local API returned an unexpected content type", response.status);
    }
    return (await response.json()) as T;
  }

  return {
    runtimeKind: "local_loopback",
    async getControlPlaneReadiness(signal) {
      const value = await request<unknown>(
        "/v1/control-plane/readiness",
        { method: "GET" },
        signal,
        false,
        true,
      );
      return parseControlPlaneReadiness(value);
    },
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
    async getTextModelCompatibility(signal) {
      const value = await request<unknown>(
        "/v1/research/text-model-compatibility",
        { method: "GET" },
        signal,
        false,
        true,
      );
      try {
        return parseModelCompatibilityCatalog(value);
      } catch (error) {
        if (error instanceof ModelCompatibilityPayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    async getModelLabInventory(signal) {
      const value = await request<unknown>(
        "/v1/estimators/plans",
        { method: "GET" },
        signal,
        false,
        true,
      );
      return parseModelLabInventory(value);
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
    async getProviderMetricCapabilities(provider, signal) {
      const value = await request<unknown>(
        `/v1/providers/${encodeURIComponent(provider)}/capabilities`,
        { method: "GET" },
        signal,
      );
      return parseProviderCapabilityReport(value, provider);
    },
    async getMetricCoverage(provider, signal) {
      const value = await request<unknown>(
        `/v1/metric-coverage?provider=${encodeURIComponent(provider)}`,
        { method: "GET" },
        signal,
        false,
        true,
      );
      return parseMetricCoverageReport(value, provider, "provider_catalog");
    },
    async getProjectMetricCoverage(projectId, provider, signal) {
      const value = await request<unknown>(
        `/v1/projects/${encodeURIComponent(projectId)}/metric-coverage?provider=${encodeURIComponent(provider)}`,
        { method: "GET" },
        signal,
        false,
        true,
      );
      return parseMetricCoverageReport(value, provider, "one_project");
    },
    async getSessionMetricReadiness(
      sessionId,
      presetId = "coaching_profile_v1",
      signal,
    ) {
      const value = await request<unknown>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/metric-readiness?preset_id=${encodeURIComponent(presetId)}`,
        { method: "GET" },
        signal,
      );
      return parseSessionMetricReadinessReport(value, sessionId, presetId);
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
    getOnboardingStatus(signal) {
      return request<OnboardingStatus>("/v1/onboarding", { method: "GET" }, signal);
    },
    acceptOnboarding(payload, signal) {
      return request<OnboardingResult>(
        "/v1/onboarding/accept",
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
        signal,
      );
    },
    getSessionTranscript(sessionId, signal) {
      return request<SessionTranscript>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/transcript`,
        { method: "GET" },
        signal,
      );
    },
    getClaudeLocalSourceStatus(signal) {
      return request<ClaudeCodeLocalSourceStatus>(
        "/v1/local-sources/claude-code",
        { method: "GET" },
        signal,
      );
    },
    grantClaudeLocalHistoryConsent(signal) {
      return request<ClaudeCodeLocalSourceStatus>(
        "/v1/local-sources/claude-code/consents/local-history",
        { method: "POST" },
        signal,
      );
    },
    revokeClaudeLocalHistoryConsent(signal) {
      return request<ClaudeCodeLocalSourceStatus>(
        "/v1/local-sources/claude-code/consents/local-history",
        { method: "DELETE" },
        signal,
      );
    },
    indexClaudeLocalSessions(maxSessions, signal) {
      return request<IngestionReport>(
        "/v1/local-sources/claude-code/index",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ max_sessions: maxSessions }),
        },
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
    // Despite the legacy name this lists every local provider's sessions;
    // a provider filter here silently hid hook-captured Claude Code sessions.
    listCodexSessions(limit = 100, offset = 0, signal) {
      return request<CodexSessionListResponse>(
        `/v1/sessions?limit=${limit}&offset=${offset}`,
        { method: "GET" },
        signal,
      );
    },
    listProjectSessions(projectId, limit = 100, offset = 0, signal) {
      return request<ProjectSessionListResponse>(
        `/v1/projects/${encodeURIComponent(projectId)}/sessions?limit=${limit}&offset=${offset}`,
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
    async listAnalysisJobs(state = null, limit = 100, offset = 0, signal) {
      const query = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
      });
      if (state !== null) query.set("state", state);
      const value = await request<unknown>(
        `/v1/analysis-jobs?${query.toString()}`,
        { method: "GET" },
        signal,
        true,
        true,
      );
      return parseAnalysisJobPage(value, limit, offset, state);
    },
    async getAnalysisJob(jobId, signal) {
      const value = await request<unknown>(
        `/v1/analysis-jobs/${encodeURIComponent(jobId)}`,
        { method: "GET" },
        signal,
        true,
        true,
      );
      return parseAnalysisJobRecord(value, jobId);
    },
    async getLatestSessionAnalysisJob(sessionId, signal) {
      const value = await request<unknown>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/analysis-jobs/latest`,
        { method: "GET" },
        signal,
        true,
        true,
      );
      const job = parseAnalysisJobRecord(value);
      if (job.identity.session_id !== sessionId) {
        throw new TransportError("Analysis job response was invalid", 200);
      }
      return job;
    },
    async cancelAnalysisJob(jobId, signal) {
      const value = await request<unknown>(
        `/v1/analysis-jobs/${encodeURIComponent(jobId)}/cancellation`,
        { method: "POST" },
        signal,
        true,
        true,
      );
      return parseAnalysisJobRecord(value, jobId);
    },
    async listAutomationGrants(provider, activeOnly = false, signal) {
      if (!["codex", "claude_code", "synthetic"].includes(provider)) {
        throw new TransportError("Automation provider was invalid", 400);
      }
      const query = new URLSearchParams({
        provider,
        active_only: String(activeOnly),
      });
      const value = await request<unknown>(
        `/v1/automation-grants?${query.toString()}`,
        { method: "GET" },
        signal,
        true,
        true,
      );
      return parseAutomationGrantList(value, provider);
    },
    async getAutomationGrant(grantId, expectedScope, signal) {
      if (!PSEUDONYM.test(grantId)) {
        throw new TransportError("Automation grant identifier was invalid", 400);
      }
      const canonicalScope = parseAutomationGrantScope(expectedScope);
      const value = await request<unknown>(
        `/v1/automation-grants/${encodeURIComponent(grantId)}`,
        { method: "GET" },
        signal,
        true,
        true,
      );
      return parseAutomationGrantRecord(value, grantId, canonicalScope);
    },
    async createAutomationGrant(automationRequest, signal) {
      const canonicalRequest = parseAutomationGrantCreateRequest(automationRequest);
      const value = await request<unknown>(
        "/v1/automation-grants",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(canonicalRequest),
        },
        signal,
        true,
        true,
      );
      return parseAutomationGrantRecord(
        value,
        undefined,
        scopeForAutomationRequest(canonicalRequest),
      );
    },
    async renewAutomationGrant(grantId, expectedScope, signal) {
      if (!PSEUDONYM.test(grantId)) {
        throw new TransportError("Automation grant identifier was invalid", 400);
      }
      const canonicalScope = parseAutomationGrantScope(expectedScope);
      const value = await request<unknown>(
        `/v1/automation-grants/${encodeURIComponent(grantId)}/renewal`,
        { method: "POST" },
        signal,
        true,
        true,
      );
      return parseAutomationGrantRecord(value, grantId, canonicalScope);
    },
    async revokeAutomationGrant(grantId, expectedScope, signal) {
      if (!PSEUDONYM.test(grantId)) {
        throw new TransportError("Automation grant identifier was invalid", 400);
      }
      const canonicalScope = parseAutomationGrantScope(expectedScope);
      const value = await request<unknown>(
        `/v1/automation-grants/${encodeURIComponent(grantId)}/revocation`,
        { method: "POST" },
        signal,
        true,
        true,
      );
      return parseAutomationGrantRecord(value, grantId, canonicalScope);
    },
    async pollAutomationGrants(signal) {
      const value = await request<unknown>(
        "/v1/automation-grants/poll",
        { method: "POST" },
        signal,
        true,
        true,
      );
      return parseAutomationPollResult(value);
    },
    async getLatestSessionQualityAnalysis(sessionId, signal) {
      if (!PSEUDONYM.test(sessionId)) {
        throw new TransportError("Session identifier was invalid", 400);
      }
      const value = await request<unknown>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/quality-analysis-runs/latest`,
        { method: "GET" },
        signal,
      );
      return parseSessionAnalysisRunResponse(value, { sessionId });
    },
    async getSessionQualityAnalysisRun(runId, signal) {
      if (!PSEUDONYM.test(runId)) {
        throw new TransportError("Quality analysis run identifier was invalid", 400);
      }
      const value = await request<unknown>(
        `/v1/quality-analysis/runs/${encodeURIComponent(runId)}`,
        { method: "GET" },
        signal,
      );
      return parseSessionAnalysisRunResponse(value, { runId });
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
      return request<unknown>(
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
      ).then(parseSessionQualityAnalysisOutcome);
    },
    async prepareSessionQualityAnalysisPreview(
      sessionId,
      previewRequest: SessionQualityAnalysisPreviewRequest,
      signal,
    ) {
      const value = await request<unknown>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/quality-analysis-previews`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(previewRequest),
        },
        signal,
        true,
        true,
      );
      return parseSessionQualityAnalysisPreview(
        value,
        sessionId,
        previewRequest.preset_id,
      );
    },
    async approveSessionQualityAnalysisPreview(
      previewId,
      approvalRequest: SessionQualityAnalysisPreviewApprovalRequest,
      idempotencyKey,
      signal,
    ) {
      const value = await request<unknown>(
        `/v1/quality-analysis-previews/${encodeURIComponent(previewId)}/approval`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey,
          },
          body: JSON.stringify(approvalRequest),
        },
        signal,
        true,
        true,
      );
      return parseSessionQualityAnalysisOutcome(value);
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
    async getLatestModelEnsemble(sessionId, signal) {
      const value = await request<unknown>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/model-ensemble-runs/latest`,
        { method: "GET" },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleRun(value);
      } catch (error) {
        if (error instanceof ModelEnsemblePayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    async startModelEnsemble(
      sessionId,
      ensembleRequest: ModelEnsembleRequest,
      idempotencyKey,
      signal,
    ) {
      const value = await request<unknown>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/model-ensemble-runs`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey,
          },
          body: JSON.stringify(ensembleRequest),
        },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleOutcome(value);
      } catch (error) {
        if (error instanceof ModelEnsemblePayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    async getModelPredictiveMetricDetail(runId, metricKey, signal) {
      const value = await request<unknown>(
        `/v1/model-ensemble-runs/${encodeURIComponent(runId)}/metrics/${encodeURIComponent(metricKey)}/predictive-detail`,
        { method: "GET" },
        signal,
        true,
        true,
      );
      try {
        return parseModelPredictiveMetricDetail(value) as ModelPredictiveMetricDetail;
      } catch (error) {
        if (error instanceof ModelPredictiveMetricDetailPayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    async previewAgentMetricEvidence(sessionId, payload, signal) {
      const value = await request<unknown>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/agent-metric-evidence/preview`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/vnd.prompt-enhancer.agent-metric-evidence+json",
          },
          body: payload,
        },
        signal,
        true,
        true,
      );
      try { return parseAgentMetricEvidencePreview(value); }
      catch (error) {
        if (error instanceof AgentMetricEvidencePayloadError) throw new TransportError(error.message, 200);
        throw error;
      }
    },
    async importAgentMetricEvidence(
      sessionId,
      payload,
      expectedPayloadSha256,
      confirmation,
      idempotencyKey,
      signal,
    ) {
      const value = await request<unknown>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/agent-metric-evidence/import`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/vnd.prompt-enhancer.agent-metric-evidence+json",
            "Idempotency-Key": idempotencyKey,
            "X-Agent-Evidence-Confirmation": confirmation,
            "X-Agent-Evidence-Payload-SHA256": expectedPayloadSha256,
          },
          body: payload,
        },
        signal,
        true,
        true,
      );
      try { return parseAgentMetricEvidenceImport(value); }
      catch (error) {
        if (error instanceof AgentMetricEvidencePayloadError) throw new TransportError(error.message, 200);
        throw error;
      }
    },
    async listMetricLifecycleProposals(sessionId, signal) {
      const limit = 200;
      let offset = 0;
      let total: number | null = null;
      const proposals: MetricLifecycleProposal[] = [];
      const identities = new Set<string>();
      for (let pageIndex = 0; pageIndex < 120; pageIndex += 1) {
        const value = await request<unknown>(
          `/v1/sessions/${encodeURIComponent(sessionId)}/metric-lifecycle-evidence/proposal-page?limit=${limit}&offset=${offset}`,
          { method: "GET" },
          signal,
          true,
          true,
        );
        try {
          const page = parseMetricLifecycleProposalPage(value, sessionId, limit, offset);
          if (total !== null && page.total !== total) throw new AgentMetricEvidencePayloadError();
          total = page.total;
          for (const proposal of page.proposals) {
            if (identities.has(proposal.proposal_id)) throw new AgentMetricEvidencePayloadError();
            identities.add(proposal.proposal_id);
            proposals.push(proposal);
          }
          if (page.complete) return { session_id: sessionId, proposals, total, complete: true };
          if (typeof page.next_offset !== "number") throw new AgentMetricEvidencePayloadError();
          offset = page.next_offset;
        } catch (error) {
          if (error instanceof AgentMetricEvidencePayloadError) throw new TransportError(error.message, 200);
          throw error;
        }
      }
      throw new TransportError("Metric lifecycle proposal list exceeded the reviewed page budget", 200);
    },
    async decideMetricLifecycleProposal(
      sessionId,
      proposalId,
      decisionRequest: MetricLifecycleDecisionRequest,
      idempotencyKey,
      signal,
    ) {
      const value = await request<unknown>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/metric-lifecycle-evidence/proposals/${encodeURIComponent(proposalId)}/decision`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey,
          },
          body: JSON.stringify(decisionRequest),
        },
        signal,
        true,
        true,
      );
      try { return parseMetricLifecycleProposalOutcome(value); }
      catch (error) {
        if (error instanceof AgentMetricEvidencePayloadError) throw new TransportError(error.message, 200);
        throw error;
      }
    },
    async getActiveModelEnsembleWatch(signal) {
      const value = await request<unknown>(
        "/v1/model-ensemble-watch/active",
        { method: "GET" },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleWatchSnapshot(value);
      } catch (error) {
        if (error instanceof ModelEnsembleWatchPayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    async getActiveModelEnsembleCanonicalHead(signal) {
      const value = await request<unknown>(
        "/v2/model-ensemble-watch/active/head",
        { method: "GET" },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleCanonicalHead(value) as ModelEnsembleCanonicalHead;
      } catch (error) {
        if (error instanceof ModelEnsembleHeadPayloadError) throw new TransportError(error.message, 200);
        throw error;
      }
    },
    async getSessionModelEnsembleCanonicalHead(sessionId, signal) {
      const value = await request<unknown>(
        `/v2/sessions/${encodeURIComponent(sessionId)}/model-ensemble-head`,
        { method: "GET" },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleCanonicalHead(value) as ModelEnsembleCanonicalHead;
      } catch (error) {
        if (error instanceof ModelEnsembleHeadPayloadError) throw new TransportError(error.message, 200);
        throw error;
      }
    },
    async getModelEnsembleSnapshot(runId, signal) {
      const value = await request<unknown>(
        `/v2/model-ensemble-snapshots/${encodeURIComponent(runId)}`,
        { method: "GET" },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleRun(value);
      } catch (error) {
        if (error instanceof ModelEnsemblePayloadError) throw new TransportError(error.message, 200);
        throw error;
      }
    },
    async enqueueModelEnsembleAnalysis(watchId, signal) {
      const value = await request<unknown>(
        `/v2/model-ensemble-watches/${encodeURIComponent(watchId)}/analysis`,
        { method: "POST" },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleCanonicalHead(value) as ModelEnsembleCanonicalHead;
      } catch (error) {
        if (error instanceof ModelEnsembleHeadPayloadError) throw new TransportError(error.message, 200);
        throw error;
      }
    },
    async cancelModelEnsembleAnalysis(watchId, signal) {
      const value = await request<unknown>(
        `/v2/model-ensemble-watches/${encodeURIComponent(watchId)}/attempts/active`,
        { method: "DELETE" },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleCanonicalHead(value) as ModelEnsembleCanonicalHead;
      } catch (error) {
        if (error instanceof ModelEnsembleHeadPayloadError) throw new TransportError(error.message, 200);
        throw error;
      }
    },
    async getModelEnsembleAttempt(attemptId, signal) {
      const value = await request<unknown>(
        `/v2/model-ensemble-attempts/${encodeURIComponent(attemptId)}`,
        { method: "GET" },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleAttemptSnapshot(value) as ModelEnsembleAttemptSnapshot;
      } catch (error) {
        if (error instanceof ModelEnsembleHeadPayloadError) throw new TransportError(error.message, 200);
        throw error;
      }
    },
    async enableModelEnsembleWatch(
      sessionId,
      watchRequest: ModelEnsembleWatchRequest,
      signal,
    ) {
      const value = await request<unknown>(
        `/v1/sessions/${encodeURIComponent(sessionId)}/model-ensemble-watch`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(watchRequest),
        },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleWatchSnapshot(value);
      } catch (error) {
        if (error instanceof ModelEnsembleWatchPayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    async disableModelEnsembleWatch(watchId, signal) {
      const value = await request<unknown>(
        `/v1/model-ensemble-watches/${encodeURIComponent(watchId)}`,
        { method: "DELETE" },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleWatchSnapshot(value);
      } catch (error) {
        if (error instanceof ModelEnsembleWatchPayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    async refreshModelEnsembleWatch(watchId, signal) {
      const value = await request<unknown>(
        `/v1/model-ensemble-watches/${encodeURIComponent(watchId)}/refresh`,
        { method: "POST" },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleWatchSnapshot(value);
      } catch (error) {
        if (error instanceof ModelEnsembleWatchPayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    async getModelEnsembleTrajectory(watchId, limit = 12, beforeGeneration, signal) {
      const query = new URLSearchParams({ limit: String(limit) });
      if (beforeGeneration !== undefined) {
        query.set("before_generation", String(beforeGeneration));
      }
      const value = await request<unknown>(
        `/v1/model-ensemble-watches/${encodeURIComponent(watchId)}/trajectory?${query.toString()}`,
        { method: "GET" },
        signal,
        true,
        true,
      );
      try {
        return parseModelEnsembleTrajectoryPage(
          value,
          beforeGeneration === undefined,
        ) as ModelEnsembleTrajectoryPage;
      } catch (error) {
        if (error instanceof ModelEnsembleTrajectoryPayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    listCandidates(status = "all", signal, page) {
      const query = new URLSearchParams();
      if (status !== "all") query.set("status", status);
      if (page !== undefined) {
        query.set("limit", String(page.limit));
        query.set("offset", String(page.offset));
      }
      const suffix = query.size === 0 ? "" : `?${query.toString()}`;
      return request<CandidateListResponse>(`/v1/discovery/candidates${suffix}`, { method: "GET" }, signal);
    },
    listTaskRevisions(taskId, signal, page) {
      const query = new URLSearchParams();
      if (taskId) query.set("task_id", taskId);
      if (page !== undefined) {
        query.set("limit", String(page.limit));
        query.set("offset", String(page.offset));
      }
      const suffix = query.size === 0 ? "" : `?${query.toString()}`;
      return request<TaskRevisionListResponse>(`/v1/task-revisions${suffix}`, { method: "GET" }, signal);
    },
    async getCandidateDecisions(candidateId, signal) {
      const response = await request<unknown>(
        `/v1/discovery/candidates/${encodeURIComponent(candidateId)}/decisions`,
        { method: "GET" },
        signal,
      );
      return parseCandidateDecisionsResponse(response, candidateId);
    },
    getTaskRevision(taskId, revision, signal) {
      return request<TaskRevisionResponse>(
        `/v1/tasks/${encodeURIComponent(taskId)}/revisions/${revision}`,
        { method: "GET" },
        signal,
      );
    },
    async listTaskLifecycles(signal, page, eventLimit = 100) {
      const limit = page?.limit ?? 100;
      const offset = page?.offset ?? 0;
      const query = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
        event_limit: String(eventLimit),
      });
      const value = await request<unknown>(
        `/v1/task-lifecycles?${query.toString()}`,
        { method: "GET" },
        signal,
        false,
        true,
      );
      try {
        return parseTaskLifecycleListResponse(value, { limit, offset });
      } catch (error) {
        if (error instanceof TaskLifecyclePayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    async getTaskLifecycle(taskId, revision, eventLimit = 100, eventOffset = 0, signal) {
      const query = new URLSearchParams({
        event_limit: String(eventLimit),
        event_offset: String(eventOffset),
      });
      const value = await request<unknown>(
        `/v1/tasks/${encodeURIComponent(taskId)}/revisions/${revision}/lifecycle?${query.toString()}`,
        { method: "GET" },
        signal,
        false,
        true,
      );
      try {
        return parseTaskLifecycleSnapshot(value, { taskId, revision });
      } catch (error) {
        if (error instanceof TaskLifecyclePayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    async transitionTaskLifecycle(
      taskId,
      revision,
      expectedHeadEventId,
      state: TaskLifecycleState,
      idempotencyKey,
      signal,
    ) {
      const value = await request<unknown>(
        `/v1/tasks/${encodeURIComponent(taskId)}/revisions/${revision}/lifecycle/transitions`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey,
          },
          body: JSON.stringify({
            expected_head_event_id: expectedHeadEventId,
            state,
          }),
        },
        signal,
        false,
        true,
      );
      try {
        return parseTaskLifecycleMutationResponse(value, {
          taskId,
          revision,
          eventKind: "transition",
          expectedHeadEventId,
          requestedState: state,
        });
      } catch (error) {
        if (error instanceof TaskLifecyclePayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    async correctTaskLifecycle(
      taskId,
      revision,
      expectedHeadEventId,
      expectedPriorState,
      expectedResultingState,
      idempotencyKey,
      signal,
    ) {
      const value = await request<unknown>(
        `/v1/tasks/${encodeURIComponent(taskId)}/revisions/${revision}/lifecycle/corrections`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey,
          },
          body: JSON.stringify({
            expected_head_event_id: expectedHeadEventId,
            supersedes_event_id: expectedHeadEventId,
          }),
        },
        signal,
        false,
        true,
      );
      try {
        return parseTaskLifecycleMutationResponse(value, {
          taskId,
          revision,
          eventKind: "correction",
          expectedHeadEventId,
          correctionPriorState: expectedPriorState,
          correctionResultingState: expectedResultingState,
        });
      } catch (error) {
        if (error instanceof TaskLifecyclePayloadError) {
          throw new TransportError(error.message, 200);
        }
        throw error;
      }
    },
    listAnalysisRuns(taskId, signal, page) {
      const query = new URLSearchParams();
      if (taskId) query.set("task_id", taskId);
      if (page !== undefined) {
        query.set("limit", String(page.limit));
        query.set("offset", String(page.offset));
      }
      const suffix = query.size === 0 ? "" : `?${query.toString()}`;
      return request<AnalysisRunListResponse>(`/v1/analysis/runs${suffix}`, { method: "GET" }, signal);
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
