import type {
  AnalysisJobIdentity,
  AnalysisJobPage,
  AnalysisJobRecord,
  AnalysisJobState,
  AnalysisRunListResponse,
  AnalysisRunResponse,
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
  TaskAnalysisResponse,
  TaskReviewResponse,
  TextAnalysisResearchCatalog,
  TextAnalysisPresetId,
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
      (typeof value.checked_at === "string" &&
        SAFE_COMPATIBILITY_DATE.test(value.checked_at) &&
        !Number.isNaN(new Date(value.checked_at).valueOf()))
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

const READINESS_STATE_REASON_ACTION = new Map<string, readonly MetricReadinessAction[]>([
  ["known:measured", ["none"]],
  ["unknown:analysis_not_run", ["run_local_analysis"]],
  ["unknown:analysis_in_progress", ["none"]],
  ["unknown:result_unknown", ["review_applicability"]],
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
      "result_failed", "result_missing",
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
  "grants_checked", "grants_revoked", "candidates_seen", "jobs_created",
  "jobs_reused", "jobs_superseded", "failures",
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
  return {
    provider: scope.provider,
    project_id: scope.project_id,
    metric_keys: scope.metric_keys,
    newest_session_limit: scope.newest_session_limit,
    check_interval_seconds: scope.check_interval_seconds,
    resource_policy: scope.resource_policy,
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
  if (
    !isRecord(value) || !hasExactKeys(value, AUTOMATION_POLL_RESULT_KEYS) ||
    [...AUTOMATION_POLL_RESULT_KEYS].some((key) =>
      !Number.isSafeInteger(value[key]) || (value[key] as number) < 0
    )
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
    async getProviderMetricCapabilities(provider, signal) {
      const value = await request<unknown>(
        `/v1/providers/${encodeURIComponent(provider)}/capabilities`,
        { method: "GET" },
        signal,
      );
      return parseProviderCapabilityReport(value, provider);
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
