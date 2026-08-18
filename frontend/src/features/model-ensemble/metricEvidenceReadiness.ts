import {
  METRIC_CONTRACT_V2_PROJECTION_VERSIONS,
  METRIC_CONTRACT_V2_REGISTRY_VERSION,
  METRIC_CONTRACT_V2_SET_FINGERPRINT,
  METRIC_V2_KEYS,
  type MetricPublicationV2,
} from "../../shared/api/metricPublicationV2Contract";
import type {
  CapabilityKey,
  MetricEvidenceAvailabilityState,
  MetricEvidenceContributor,
  MetricEvidenceReadinessProjectionV2,
  MetricEvidenceReadinessV2,
} from "../../shared/api/contracts";

export type { MetricEvidenceAvailabilityState, MetricEvidenceContributor };

/** Closed adapter authorities used by the five objective V2 contracts. */
export type MetricEvidenceAdapterCapability = Extract<CapabilityKey,
  | "tool_events"
  | "decision_events"
  | "verification_events"
  | "requirement_opportunities"
  | "hypothesis_opportunities"
  | "material_claim_opportunities"
  | "verification_task_opportunities"
  | "requirement_evidence_links"
  | "hypothesis_evidence_links"
  | "material_claim_evidence_links"
  | "verification_task_evidence_links">;

const OBJECTIVE_ADAPTER_CAPABILITIES: Readonly<Record<string, readonly MetricEvidenceAdapterCapability[]>> = {
  "logic.hypothesis_test_linkage": [
    "hypothesis_opportunities", "hypothesis_evidence_links", "tool_events",
    "decision_events", "verification_events",
  ],
  "logic.requirement_action_traceability": [
    "requirement_opportunities", "requirement_evidence_links", "tool_events",
  ],
  "outcome.agent_claim_grounding": [
    "material_claim_opportunities", "material_claim_evidence_links", "verification_events",
  ],
  "outcome.first_pass_verification": [
    "verification_task_opportunities", "verification_task_evidence_links", "verification_events",
  ],
  "outcome.verified_requirement_coverage": [
    "requirement_opportunities", "requirement_evidence_links", "verification_events",
  ],
};

const METRIC_EVIDENCE_CONTRIBUTORS: Readonly<Record<string, readonly MetricEvidenceContributor[]>> = {
  "prompt.task_definition_coverage": ["focus_owned_request_revision", "rubric_factor_calculator"],
  "prompt.problem_evidence_quality": ["focus_owned_request_revision", "rubric_factor_calculator"],
  "prompt.context_sufficiency": ["focus_owned_request_revision", "rubric_factor_calculator"],
  "prompt.constraint_precision": ["declared_task_profile", "canonical_request_text"],
  "prompt.acceptance_testability": ["declared_task_profile", "canonical_request_text"],
  "prompt.deliverable_contract": ["declared_task_profile", "canonical_request_text"],
  "collaboration.ambiguity_resolution": ["semantic_unit_heads", "agent_response_text"],
  "collaboration.clarification_yield": ["semantic_unit_heads", "agent_response_text"],
  "collaboration.exploration_conversion": ["semantic_unit_heads", "typed_action_evidence"],
  "collaboration.scope_change_discipline": ["semantic_unit_heads", "agent_response_text"],
  "collaboration.rework_candidate_rate": ["semantic_unit_heads", "feedback_classification"],
  "logic.decomposition_coverage": ["semantic_unit_heads", "agent_response_text"],
  "logic.hypothesis_test_linkage": [
    "declared_objective_opportunity_set", "typed_action_evidence",
    "typed_decision_evidence", "typed_verification_receipt",
  ],
  "logic.decision_rationale_coverage": ["semantic_unit_heads", "agent_response_text"],
  "logic.requirement_action_traceability": ["declared_objective_opportunity_set", "typed_action_evidence"],
  "logic.open_loop_closure": ["semantic_unit_heads", "agent_response_text"],
  "outcome.agent_claim_grounding": ["declared_objective_opportunity_set", "typed_verification_receipt"],
  "outcome.verification_strategy_adequacy": ["semantic_unit_heads", "agent_response_text"],
  "outcome.first_pass_verification": ["declared_objective_opportunity_set", "typed_verification_receipt"],
  "outcome.verified_requirement_coverage": ["declared_objective_opportunity_set", "typed_verification_receipt"],
};

const METRIC_EVIDENCE_CONTRIBUTORS_R3: Readonly<Record<string, readonly MetricEvidenceContributor[]>> = {
  "logic.open_loop_closure": ["documented_plan_message", "explicit_plan_supersession_link"],
};

const OBJECTIVE_CAPABILITY_MISSING_REASONS: Readonly<Record<string, MetricEvidenceReadinessV2["reason_code"]>> = {
  "logic.hypothesis_test_linkage": "hypothesis_chain_adapter_capabilities_required",
  "logic.requirement_action_traceability": "requirement_action_adapter_capabilities_required",
  "outcome.agent_claim_grounding": "material_claim_verification_adapter_capabilities_required",
  "outcome.first_pass_verification": "verification_task_outcome_adapter_capabilities_required",
  "outcome.verified_requirement_coverage": "requirement_verification_adapter_capabilities_required",
};

export function metricEvidenceRequirementFor(
  metricKey: string,
  projectionVersion: MetricPublicationV2["projection_version"],
): {
  requiredContributors: readonly MetricEvidenceContributor[];
  requiredAdapterCapabilities: readonly MetricEvidenceAdapterCapability[];
  capabilityMissingReason: MetricEvidenceReadinessV2["reason_code"] | null;
} {
  const projectionContributors = projectionVersion === "metric-contract-v2-projection-3"
    ? METRIC_EVIDENCE_CONTRIBUTORS_R3[metricKey]
    : undefined;
  return {
    requiredContributors: projectionContributors ?? METRIC_EVIDENCE_CONTRIBUTORS[metricKey] ?? [],
    requiredAdapterCapabilities: OBJECTIVE_ADAPTER_CAPABILITIES[metricKey] ?? [],
    capabilityMissingReason: OBJECTIVE_CAPABILITY_MISSING_REASONS[metricKey] ?? null,
  };
}

export type MetricEvidenceReadinessRowV2 = MetricEvidenceReadinessV2;
export type { MetricEvidenceReadinessProjectionV2 };

const HEX_64 = /^[0-9a-f]{64}$/;
const SAFE_CODE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const CONTRIBUTORS: readonly MetricEvidenceContributor[] = [
  "focus_owned_request_revision", "canonical_request_text", "declared_task_profile",
  "rubric_factor_calculator", "semantic_unit_heads", "agent_response_text",
  "feedback_classification", "declared_objective_opportunity_set", "documented_plan_message",
  "explicit_plan_supersession_link", "typed_action_evidence",
  "typed_decision_evidence", "typed_verification_receipt",
];
const AVAILABILITY: readonly MetricEvidenceAvailabilityState[] = [
  "measured", "pending_right_censored", "no_opportunity", "capability_missing",
  "source_incomplete", "evidence_unresolved", "abstained", "execution_error",
];

function row(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function contributorList(value: unknown): readonly MetricEvidenceContributor[] | null {
  return Array.isArray(value)
    && value.every((item) => typeof item === "string" && CONTRIBUTORS.includes(item as MetricEvidenceContributor))
    && new Set(value).size === value.length
    ? value as MetricEvidenceContributor[]
    : null;
}

function capabilityList(value: unknown): readonly MetricEvidenceAdapterCapability[] | null {
  return Array.isArray(value)
    && value.every((item) => typeof item === "string")
    && new Set(value).size === value.length
    ? value as MetricEvidenceAdapterCapability[]
    : null;
}

function sameOrderedValues(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function integer(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 0 && (value as number) <= 1_000_000;
}

function optionalBound(value: unknown): value is number | null | undefined {
  return value === null || value === undefined
    || (typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1);
}

/**
 * Presentation-side cross-binding for the additive readiness projection. The
 * API parser remains authoritative; this guard ensures contributor prose is
 * never shown unless all twenty rows describe the exact sealed publication.
 */
export function metricEvidenceReadinessForPublication(
  value: unknown,
  publication: MetricPublicationV2 | null | undefined,
): MetricEvidenceReadinessProjectionV2 | null {
  const candidate = row(value);
  if (candidate === null || publication === null || publication === undefined) return null;
  if (
    candidate.projection_key !== "metric.contract-v2.evidence-readiness"
    || candidate.projection_version !== 1
    || candidate.catalog_version !== "metric-evidence-readiness-v2-2"
    || candidate.registry_version !== METRIC_CONTRACT_V2_REGISTRY_VERSION
    || candidate.registry_version !== publication.registry_version
    || candidate.publication_key !== publication.publication_key
    || candidate.publication_version !== publication.publication_version
    || candidate.publication_source !== publication.source
    || candidate.canonical_live_snapshot !== publication.canonical_live_snapshot
    || candidate.compatibility_preview !== publication.compatibility_preview
    || candidate.contract_set_fingerprint !== METRIC_CONTRACT_V2_SET_FINGERPRINT
    || candidate.contract_set_fingerprint !== publication.contract_set_fingerprint
    || typeof candidate.publication_fingerprint !== "string"
    || !HEX_64.test(candidate.publication_fingerprint)
    || !METRIC_CONTRACT_V2_PROJECTION_VERSIONS.includes(candidate.metric_projection_version as typeof METRIC_CONTRACT_V2_PROJECTION_VERSIONS[number])
    || candidate.metric_projection_version !== publication.projection_version
    || candidate.local_only !== true || candidate.content_persisted !== false
    || candidate.calibration_state !== "not_assessed" || candidate.product_metric_eligible !== false
    || !Array.isArray(candidate.metrics) || candidate.metrics.length !== METRIC_V2_KEYS.length
  ) return null;
  for (const field of ["provider", "provider_version", "adapter_version", "source_schema_version"] as const) {
    if (typeof candidate[field] !== "string" || !SAFE_CODE.test(candidate[field])) return null;
  }
  const availabilityCounts = new Map<MetricEvidenceAvailabilityState, number>(AVAILABILITY.map((state) => [state, 0]));
  let objectiveMeasurableCount = 0;
  let objectiveMeasuredCount = 0;
  let objectiveMetricCount = 0;
  for (let index = 0; index < METRIC_V2_KEYS.length; index += 1) {
    const readiness = row(candidate.metrics[index]);
    const sealed = publication.metrics[index].state;
    if (readiness === null) return null;
    const required = contributorList(readiness.required_contributors);
    const observed = contributorList(readiness.observed_contributors);
    const missing = contributorList(readiness.missing_contributors);
    const adapterCapabilities = capabilityList(readiness.required_adapter_capabilities);
    const requirement = metricEvidenceRequirementFor(
      sealed.metric_key,
      publication.projection_version,
    );
    const expectedAvailability: MetricEvidenceAvailabilityState = sealed.value_state === "known" ? "measured"
      : sealed.value_state === "pending" ? "pending_right_censored"
        : sealed.value_state === "not_applicable" ? "no_opportunity"
          : sealed.value_state === "abstained" ? "abstained"
            : sealed.value_state === "execution_error" ? "execution_error"
              : !sealed.statistics.capability_available ? "capability_missing"
                : !sealed.statistics.source_complete ? "source_incomplete"
                  : "evidence_unresolved";
    if (
      readiness.metric_key !== METRIC_V2_KEYS[index]
      || readiness.metric_key !== sealed.metric_key
      || readiness.contract_version !== sealed.contract_version
      || readiness.contract_fingerprint !== sealed.contract_fingerprint
      || readiness.evidence_authority !== sealed.evidence_authority
      || readiness.denominator_basis !== sealed.statistics.denominator_basis
      || readiness.opportunity_unit_kind !== sealed.statistics.opportunity_unit_kind
      || readiness.value_state !== sealed.value_state
      || typeof readiness.availability_state !== "string"
      || !AVAILABILITY.includes(readiness.availability_state as MetricEvidenceAvailabilityState)
      || readiness.availability_state !== expectedAvailability
      || typeof readiness.reason_code !== "string" || !SAFE_CODE.test(readiness.reason_code)
      || required === null || required.length === 0 || observed === null || missing === null
      || !sameOrderedValues(required, requirement.requiredContributors)
      || observed.some((item) => !required.includes(item))
      || missing.length !== required.filter((item) => !observed.includes(item)).length
      || missing.some((item) => observed.includes(item) || !required.includes(item))
      || adapterCapabilities === null
      || !sameOrderedValues(adapterCapabilities, requirement.requiredAdapterCapabilities)
      || (expectedAvailability === "capability_missing"
        && requirement.capabilityMissingReason !== null
        && readiness.reason_code !== requirement.capabilityMissingReason)
      || readiness.capability_available !== sealed.statistics.capability_available
      || readiness.source_complete !== sealed.statistics.source_complete
      || readiness.eligible_count !== sealed.statistics.eligible_count
      || readiness.met_count !== sealed.statistics.met_count
      || readiness.not_met_count !== sealed.statistics.not_met_count
      || readiness.pending_count !== sealed.statistics.pending_count
      || readiness.unknown_count !== sealed.statistics.unknown_count
      || readiness.resolved_count !== sealed.statistics.met_count + sealed.statistics.not_met_count
      || !optionalBound(readiness.censoring_lower_bound) || !optionalBound(readiness.censoring_upper_bound)
      || (readiness.censoring_lower_bound ?? null) !== (sealed.censoring_lower_bound ?? null)
      || (readiness.censoring_upper_bound ?? null) !== (sealed.censoring_upper_bound ?? null)
      || readiness.calibration_state !== "not_assessed" || readiness.product_metric_eligible !== false
    ) return null;
    const state = readiness.availability_state as MetricEvidenceAvailabilityState;
    availabilityCounts.set(state, (availabilityCounts.get(state) ?? 0) + 1);
    if (sealed.evidence_authority === "objective_receipt") {
      objectiveMetricCount += 1;
      if (readiness.capability_available === true) objectiveMeasurableCount += 1;
      if (state === "measured") objectiveMeasuredCount += 1;
    }
  }
  const summary: Readonly<Record<MetricEvidenceAvailabilityState, string>> = {
    measured: "measured_count",
    pending_right_censored: "pending_count",
    no_opportunity: "no_opportunity_count",
    capability_missing: "capability_missing_count",
    source_incomplete: "source_incomplete_count",
    evidence_unresolved: "evidence_unresolved_count",
    abstained: "abstained_count",
    execution_error: "execution_error_count",
  };
  for (const state of AVAILABILITY) {
    const field = summary[state];
    if (!integer(candidate[field]) || candidate[field] !== availabilityCounts.get(state)) return null;
  }
  if (
    candidate.objective_metric_count !== 5
    || objectiveMetricCount !== candidate.objective_metric_count
    || !integer(candidate.objective_measurable_count)
    || candidate.objective_measurable_count !== objectiveMeasurableCount
    || !integer(candidate.objective_measured_count)
    || candidate.objective_measured_count !== objectiveMeasuredCount
    || candidate.objective_measured_count !== publication.objective_measured_count
  ) return null;
  return candidate as unknown as MetricEvidenceReadinessProjectionV2;
}

export function readableEvidenceContributor(value: string): string {
  return value.replaceAll("_", " ");
}

export function readableEvidenceAvailability(value: string): string {
  return value.replaceAll("_", " ");
}

export function readableAdapterCapability(value: string): string {
  return value.replaceAll("_", " ");
}
