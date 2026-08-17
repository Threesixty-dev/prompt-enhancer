import type { ModelEnsembleRun } from "./contracts";

export class MetricPublicationV2PayloadError extends Error {
  constructor() {
    super("Canonical metric V2 publication was invalid");
    this.name = "MetricPublicationV2PayloadError";
  }
}

type Row = Record<string, unknown>;
export type MetricPublicationV2 = NonNullable<ModelEnsembleRun["metric_publication_v2"]>;

const HEX_64 = /^[0-9a-f]{64}$/;
const SAFE_LABEL = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
export const METRIC_CONTRACT_V2_SET_FINGERPRINT =
  "02eac63391eb48351f5c8c197d62897895234e2334d388a530d6e6812a18aa67";

export const METRIC_V2_KEYS = [
  "prompt.task_definition_coverage",
  "prompt.problem_evidence_quality",
  "prompt.context_sufficiency",
  "prompt.constraint_precision",
  "prompt.acceptance_testability",
  "prompt.deliverable_contract",
  "collaboration.ambiguity_resolution",
  "collaboration.clarification_yield",
  "collaboration.exploration_conversion",
  "collaboration.scope_change_discipline",
  "collaboration.rework_candidate_rate",
  "logic.decomposition_coverage",
  "logic.hypothesis_test_linkage",
  "logic.decision_rationale_coverage",
  "logic.requirement_action_traceability",
  "logic.open_loop_closure",
  "outcome.agent_claim_grounding",
  "outcome.verification_strategy_adequacy",
  "outcome.first_pass_verification",
  "outcome.verified_requirement_coverage",
] as const;

type MetricKeyV2 = typeof METRIC_V2_KEYS[number];
type ContractIdentity = {
  fingerprint: string;
  basis: typeof DENOMINATOR_BASES[number];
  unit: typeof UNIT_KINDS[number] | null;
  authority: "conversation" | "objective_receipt";
};

export const METRIC_V2_CONTRACT_IDENTITIES: Record<MetricKeyV2, ContractIdentity> = {
  "prompt.task_definition_coverage": { fingerprint: "176e2d092d19b1bffb719d7f3ce78673dd07fc14ed90415aa25454129042d7c2", basis: "rubric_factors", unit: "request_revision", authority: "conversation" },
  "prompt.problem_evidence_quality": { fingerprint: "c664f0e7941a944529cea65af5b9e6599d32ff7ad4362fd7dc93687b42e3d740", basis: "rubric_factors", unit: "request_revision", authority: "conversation" },
  "prompt.context_sufficiency": { fingerprint: "ac9d65a60a8c09c4dedf152510ea8c2b2e3e6c3764149331ea207b4e86197923", basis: "rubric_factors", unit: "request_revision", authority: "conversation" },
  "prompt.constraint_precision": { fingerprint: "c9665290720ebd1efbbd6eaeb760468b409525f4a4913cf600ca81269f23a79c", basis: "declared_profile_slots", unit: null, authority: "conversation" },
  "prompt.acceptance_testability": { fingerprint: "f7c05d2e7ab1637e63efe539f14bc1a287031b81eb0978f6935d7df8548871ce", basis: "declared_profile_slots", unit: null, authority: "conversation" },
  "prompt.deliverable_contract": { fingerprint: "2ed619d698730c3047b70c1fd572d6fb5dfc18b90fa5f6cec937d2fb8a5f8abd", basis: "declared_profile_slots", unit: null, authority: "conversation" },
  "collaboration.ambiguity_resolution": { fingerprint: "89a4c1bfb9efbc3a3b1f5d0c75e2d1e71a55e5df25bf46bf09c7bb5fd80dfb3b", basis: "semantic_unit_opportunities", unit: "ambiguity", authority: "conversation" },
  "collaboration.clarification_yield": { fingerprint: "c3bf3e69633063b5543489639d49966ac6eb0f509980a8d678ed6819db59f389", basis: "semantic_unit_opportunities", unit: "clarification", authority: "conversation" },
  "collaboration.exploration_conversion": { fingerprint: "3e4b9e79039694d1c79fa809d73e62674f32c1c19f7d9bd42ff97e57a554f560", basis: "semantic_unit_opportunities", unit: "hypothesis", authority: "conversation" },
  "collaboration.scope_change_discipline": { fingerprint: "308a3ee1a577a8f361627b9101021a50a12b63e05ca95865d5dadfa24ebd5326", basis: "semantic_unit_opportunities", unit: "scope_change", authority: "conversation" },
  "collaboration.rework_candidate_rate": { fingerprint: "3cfa3bbf472661329527e86b3248f5255bfe0307931d30042a87ec36cf1100a0", basis: "semantic_unit_opportunities", unit: "feedback", authority: "conversation" },
  "logic.decomposition_coverage": { fingerprint: "7a1941086fd7c37510ee04ccba28c4e35added3f0ca7bb933c0d8d066031c6af", basis: "semantic_unit_opportunities", unit: "requirement", authority: "conversation" },
  "logic.hypothesis_test_linkage": { fingerprint: "a21f8fd9431724967d264a9e34ba685c72339b1d9f81403a1ba23a3b5c09c1c0", basis: "objective_opportunities", unit: null, authority: "objective_receipt" },
  "logic.decision_rationale_coverage": { fingerprint: "12c8dfa3affe7e278b5e65af54b566a69b05ccc68dc27391384bb9dfca76aaaf", basis: "semantic_unit_opportunities", unit: "decision", authority: "conversation" },
  "logic.requirement_action_traceability": { fingerprint: "fdf6cf24b63e6c955099f1cd66ab989d3adc5aaef12b857e57dd54516bf80912", basis: "objective_opportunities", unit: null, authority: "objective_receipt" },
  "logic.open_loop_closure": { fingerprint: "1e0d49f883f23c5bc119d657190b2cb045d28e254eb2c6d7ba9217466a7495a6", basis: "semantic_unit_opportunities", unit: "open_loop", authority: "conversation" },
  "outcome.agent_claim_grounding": { fingerprint: "354c189507dadabe7418d3e404e5d2dd74ad9b13d567a93137daad84ef50e3d0", basis: "objective_opportunities", unit: null, authority: "objective_receipt" },
  "outcome.verification_strategy_adequacy": { fingerprint: "59ec9a0d1d65d1ea17b350e5e325e14eb0c1cd8a655ba6dbc1910f339ecb377e", basis: "semantic_unit_opportunities", unit: "request_revision", authority: "conversation" },
  "outcome.first_pass_verification": { fingerprint: "b17403508c53029c3c6a7dd9f9d17484f451a5e961a2ee18f0dd9a532b16b667", basis: "objective_opportunities", unit: null, authority: "objective_receipt" },
  "outcome.verified_requirement_coverage": { fingerprint: "4fcdd48c79e41c5e8e82e5de08c05dd4c4c6780550b2c27c78138d3ef2129be7", basis: "objective_opportunities", unit: null, authority: "objective_receipt" },
};

const VALUE_STATES = [
  "known", "pending", "unknown", "not_applicable", "abstained", "execution_error",
] as const;
const IMPLEMENTATION_STATES = [
  "live_measured", "compatibility_projected", "method_only_withheld",
  "objective_capability_missing", "objective_evidence_unresolved", "pending",
  "no_opportunity", "abstained", "error",
] as const;
const DENOMINATOR_BASES = [
  "rubric_factors", "semantic_unit_opportunities", "declared_profile_slots",
  "objective_opportunities",
] as const;
const UNIT_KINDS = [
  "request_revision", "requirement", "constraint", "deliverable", "ambiguity",
  "clarification", "scope_change", "feedback", "hypothesis", "decision",
  "open_loop", "action", "verification",
] as const;

function record(value: unknown): Row {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new MetricPublicationV2PayloadError();
  }
  return value as Row;
}

function exact(value: Row, keys: readonly string[]): void {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new MetricPublicationV2PayloadError();
  }
}

function integer(value: unknown, minimum: number, maximum: number): number {
  if (!Number.isInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    throw new MetricPublicationV2PayloadError();
  }
  return value as number;
}

function finite(value: unknown, minimum = 0, maximum = 1): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum || value > maximum) {
    throw new MetricPublicationV2PayloadError();
  }
  return value;
}

function optionalFinite(value: unknown): number | null {
  return value === null ? null : finite(value);
}

function safeLabel(value: unknown): string {
  if (typeof value !== "string" || !SAFE_LABEL.test(value)) {
    throw new MetricPublicationV2PayloadError();
  }
  return value;
}

function oneOf<T extends string>(value: unknown, choices: readonly T[]): T {
  if (typeof value !== "string" || !choices.includes(value as T)) {
    throw new MetricPublicationV2PayloadError();
  }
  return value as T;
}

function parseStatistics(value: unknown, metricKey: string) {
  const statistics = record(value);
  exact(statistics, [
    "metric_key", "denominator_basis", "opportunity_unit_kind",
    "capability_available", "source_complete", "eligible_count", "met_count",
    "not_met_count", "pending_count", "unknown_count",
    "superseded_excluded_count", "distinct_owner_count",
  ]);
  if (statistics.metric_key !== metricKey) throw new MetricPublicationV2PayloadError();
  const denominatorBasis = oneOf(statistics.denominator_basis, DENOMINATOR_BASES);
  const unitKind = statistics.opportunity_unit_kind === null
    ? null
    : oneOf(statistics.opportunity_unit_kind, UNIT_KINDS);
  if (
    (["rubric_factors", "semantic_unit_opportunities"].includes(denominatorBasis))
      !== (unitKind !== null)
  ) {
    throw new MetricPublicationV2PayloadError();
  }
  if (typeof statistics.capability_available !== "boolean" || typeof statistics.source_complete !== "boolean") {
    throw new MetricPublicationV2PayloadError();
  }
  const eligible = integer(statistics.eligible_count, 0, 1_000_000);
  const met = integer(statistics.met_count, 0, 1_000_000);
  const notMet = integer(statistics.not_met_count, 0, 1_000_000);
  const pending = integer(statistics.pending_count, 0, 1_000_000);
  const unknown = integer(statistics.unknown_count, 0, 1_000_000);
  integer(statistics.superseded_excluded_count, 0, 1_000_000);
  const owners = integer(statistics.distinct_owner_count, 0, 1_000_000);
  if (
    met + notMet + pending + unknown !== eligible
    || (!statistics.capability_available && eligible !== 0)
    || (denominatorBasis === "semantic_unit_opportunities" && owners !== eligible)
  ) {
    throw new MetricPublicationV2PayloadError();
  }
  return { statistics, denominatorBasis, eligible, met, notMet, pending, unknown };
}

function parseState(value: unknown, expectedMetricKey: string) {
  const state = record(value);
  exact(state, [
    "metric_key", "registry_version", "contract_version", "contract_fingerprint",
    "evidence_authority", "value_state", "explanation_code", "numerator",
    "denominator", "numeric_value", "censoring_lower_bound",
    "censoring_upper_bound", "statistics", "projection_version",
    "product_metric_eligible",
  ]);
  const identity = METRIC_V2_CONTRACT_IDENTITIES[expectedMetricKey as MetricKeyV2];
  if (
    identity === undefined
    || state.metric_key !== expectedMetricKey
    || state.registry_version !== "all-20-factor-contracts-v2"
    || state.contract_version !== "probabilistic-metric-contract-v2"
    || typeof state.contract_fingerprint !== "string"
    || !HEX_64.test(state.contract_fingerprint)
    || state.contract_fingerprint !== identity.fingerprint
    || state.projection_version !== "metric-contract-v2-projection-1"
    || state.product_metric_eligible !== false
  ) {
    throw new MetricPublicationV2PayloadError();
  }
  const authority = oneOf(state.evidence_authority, ["conversation", "objective_receipt"] as const);
  const valueState = oneOf(state.value_state, VALUE_STATES);
  safeLabel(state.explanation_code);
  const numerator = state.numerator === null ? null : integer(state.numerator, 0, 1_000_000);
  const denominator = state.denominator === null ? null : integer(state.denominator, 1, 1_000_000);
  const numericValue = optionalFinite(state.numeric_value);
  const lower = optionalFinite(state.censoring_lower_bound);
  const upper = optionalFinite(state.censoring_upper_bound);
  const parsed = parseStatistics(state.statistics, expectedMetricKey);
  if (
    authority !== identity.authority
    || parsed.denominatorBasis !== identity.basis
    || parsed.statistics.opportunity_unit_kind !== identity.unit
    || (lower === null) !== (upper === null)
    || (lower !== null && upper !== null && lower > upper)
    || (valueState === "pending" && parsed.pending === 0)
    || (valueState === "not_applicable" && parsed.eligible !== 0)
    || (authority === "objective_receipt" && valueState === "known"
      && parsed.denominatorBasis !== "objective_opportunities")
  ) {
    throw new MetricPublicationV2PayloadError();
  }
  if (valueState === "known") {
    if (
      numerator === null || denominator === null || numerator > denominator || numericValue === null
      || Math.abs(numericValue - numerator / denominator) > 1e-9
      || lower !== numericValue || upper !== numericValue
      || !parsed.statistics.capability_available || !parsed.statistics.source_complete
      || denominator !== parsed.eligible || numerator !== parsed.met
      || parsed.pending !== 0 || parsed.unknown !== 0
      || parsed.notMet !== parsed.eligible - parsed.met
    ) {
      throw new MetricPublicationV2PayloadError();
    }
  } else if (numerator !== null || denominator !== null || numericValue !== null) {
    throw new MetricPublicationV2PayloadError();
  }
  return { state, authority, valueState, lower, upper, numerator, denominator, parsed };
}

/** Strict parser for one compact V2 trajectory state in registry order. */
export function parseMetricV2State(
  value: unknown,
  expectedMetricKey: string,
): MetricPublicationV2["metrics"][number]["state"] {
  return parseState(value, expectedMetricKey).state as MetricPublicationV2["metrics"][number]["state"];
}

function parseGuidance(value: unknown, parsedState: ReturnType<typeof parseState>) {
  const guidance = record(value);
  exact(guidance, [
    "schema_version", "contract_version", "template_catalog_version", "template_version",
    "metric_key", "metric_version", "registry_version", "metric_contract_version",
    "metric_contract_fingerprint", "evidence_authority", "denominator_basis",
    "contract_factor_count", "audience", "role", "value_state", "state_class",
    "basis", "value_origin", "factor_evidence", "focus_factor_keys", "reason_code",
    "diagnosis_template_id", "action_template_id", "verification_template_id",
    "numerator", "denominator", "censoring_lower_bound", "censoring_upper_bound",
    "eligible_count", "met_count", "not_met_count", "pending_count", "unknown_count",
    "product_metric_eligible",
  ]);
  if (
    guidance.schema_version !== 1 || guidance.contract_version !== "metric-guidance-contract-v1"
    || guidance.template_catalog_version !== "metric-guidance-templates-v1"
    || integer(guidance.template_version, 1, 1) !== 1
    || guidance.metric_key !== parsedState.state.metric_key
    || integer(guidance.metric_version, 1, 1_000_000) < 1
    || guidance.registry_version !== "all-20-factor-contracts-v2"
    || guidance.metric_contract_version !== parsedState.state.contract_version
    || guidance.metric_contract_fingerprint !== parsedState.state.contract_fingerprint
    || guidance.evidence_authority !== parsedState.authority
    || guidance.denominator_basis !== parsedState.parsed.denominatorBasis
    || guidance.value_state !== parsedState.valueState
    || guidance.product_metric_eligible !== false
  ) {
    throw new MetricPublicationV2PayloadError();
  }
  integer(guidance.contract_factor_count, 1, 8);
  oneOf(guidance.audience, ["user", "agent", "workflow", "tooling"] as const);
  oneOf(guidance.role, [
    "specification_signal", "collaboration_signal", "traceability_signal",
    "outcome_evidence", "friction_signal",
  ] as const);
  const stateClass = oneOf(guidance.state_class, [
    "known_retain", "known_improve", "pending_closure", "objective_evidence_missing",
    "objective_evidence_unresolved", "evidence_unresolved", "no_opportunity",
    "evidence_coverage_abstained", "analysis_failed",
  ] as const);
  const basis = oneOf(guidance.basis, ["measured", "experimental", "readiness", "method-only"] as const);
  const valueOrigin = oneOf(guidance.value_origin, ["none", "deterministic_local", "typed_objective", "neural_uncalibrated"] as const);
  const factorEvidence = oneOf(guidance.factor_evidence, ["not_observed", "aggregate_only"] as const);
  if (!Array.isArray(guidance.focus_factor_keys) || guidance.focus_factor_keys.length !== 0) {
    throw new MetricPublicationV2PayloadError();
  }
  safeLabel(guidance.reason_code);
  safeLabel(guidance.diagnosis_template_id);
  safeLabel(guidance.action_template_id);
  safeLabel(guidance.verification_template_id);
  const optionalInteger = (candidate: unknown, minimum: number, maximum: number) => (
    candidate === null ? null : integer(candidate, minimum, maximum)
  );
  if (
    optionalInteger(guidance.numerator, 0, 1_000_000) !== parsedState.numerator
    || optionalInteger(guidance.denominator, 1, 1_000_000) !== parsedState.denominator
    || optionalFinite(guidance.censoring_lower_bound) !== parsedState.lower
    || optionalFinite(guidance.censoring_upper_bound) !== parsedState.upper
    || integer(guidance.eligible_count, 0, 1_000_000) !== parsedState.parsed.eligible
    || integer(guidance.met_count, 0, 1_000_000) !== parsedState.parsed.met
    || integer(guidance.not_met_count, 0, 1_000_000) !== parsedState.parsed.notMet
    || integer(guidance.pending_count, 0, 1_000_000) !== parsedState.parsed.pending
    || integer(guidance.unknown_count, 0, 1_000_000) !== parsedState.parsed.unknown
  ) {
    throw new MetricPublicationV2PayloadError();
  }

  // A canonical live publication consumes no model-stage output and persists
  // no per-factor receipts. Re-derive these labels rather than trusting a
  // structurally valid but semantically relabelled API response.
  const expectedStateClass = parsedState.valueState === "pending" ? "pending_closure"
    : parsedState.valueState === "not_applicable" ? "no_opportunity"
      : parsedState.valueState === "abstained" ? "evidence_coverage_abstained"
        : parsedState.valueState === "execution_error" ? "analysis_failed"
          : parsedState.valueState === "unknown"
            ? parsedState.authority === "objective_receipt"
              ? (parsedState.parsed.statistics.capability_available && parsedState.parsed.eligible > 0
                ? "objective_evidence_unresolved"
                : "objective_evidence_missing")
              : "evidence_unresolved"
            : null;
  if (
    factorEvidence !== "not_observed"
    || (parsedState.valueState === "known" && (
      !["known_retain", "known_improve"].includes(stateClass)
      || basis !== "measured"
      || valueOrigin !== (parsedState.authority === "objective_receipt" ? "typed_objective" : "deterministic_local")
    ))
    || (parsedState.valueState !== "known" && (
      stateClass !== expectedStateClass
      || valueOrigin !== "none"
      || basis !== (parsedState.valueState === "execution_error" ? "method-only" : "readiness")
    ))
  ) {
    throw new MetricPublicationV2PayloadError();
  }
}

export function parseMetricPublicationV2(value: unknown): MetricPublicationV2 {
  const publication = record(value);
  exact(publication, [
    "publication_key", "publication_version", "registry_version",
    "contract_set_fingerprint", "projection_version", "guidance_contract_version",
    "guidance_template_catalog_version", "source", "canonical_live_snapshot",
    "model_stage_consumed", "compatibility_preview", "metrics", "known_count",
    "pending_count", "unknown_count", "not_applicable_count", "abstained_count",
    "execution_error_count", "objective_measured_count", "product_metric_eligible",
  ]);
  if (
    publication.publication_key !== "metric.contract-v2.publication"
    || publication.publication_version !== 2
    || publication.registry_version !== "all-20-factor-contracts-v2"
    || publication.contract_set_fingerprint !== METRIC_CONTRACT_V2_SET_FINGERPRINT
    || publication.projection_version !== "metric-contract-v2-projection-1"
    || publication.guidance_contract_version !== "metric-guidance-contract-v1"
    || publication.guidance_template_catalog_version !== "metric-guidance-templates-v1"
    || publication.source !== "live_projection"
    || publication.canonical_live_snapshot !== true
    || publication.model_stage_consumed !== false
    || publication.compatibility_preview !== false
    || publication.product_metric_eligible !== false
    || !Array.isArray(publication.metrics)
    || publication.metrics.length !== METRIC_V2_KEYS.length
  ) {
    throw new MetricPublicationV2PayloadError();
  }
  const counts = new Map<string, number>();
  let objectiveMeasured = 0;
  publication.metrics.forEach((candidate, ordinal) => {
    const item = record(candidate);
    exact(item, ["state", "guidance", "implementation_state"]);
    const parsedState = parseState(item.state, METRIC_V2_KEYS[ordinal]);
    parseGuidance(item.guidance, parsedState);
    const implementation = oneOf(item.implementation_state, IMPLEMENTATION_STATES);
    const expected = parsedState.valueState === "known" ? "live_measured"
      : parsedState.valueState === "pending" ? "pending"
        : parsedState.valueState === "not_applicable" ? "no_opportunity"
          : parsedState.valueState === "abstained" ? "abstained"
            : parsedState.valueState === "execution_error" ? "error" : null;
    if (expected !== null && implementation !== expected) {
      throw new MetricPublicationV2PayloadError();
    }
    const expectedUnknownImplementation = parsedState.authority === "objective_receipt"
      ? (parsedState.parsed.statistics.capability_available && parsedState.parsed.eligible > 0
        ? "objective_evidence_unresolved"
        : "objective_capability_missing")
      : "method_only_withheld";
    if (
      parsedState.valueState === "unknown"
      && implementation !== expectedUnknownImplementation
    ) {
      throw new MetricPublicationV2PayloadError();
    }
    counts.set(parsedState.valueState, (counts.get(parsedState.valueState) ?? 0) + 1);
    if (parsedState.authority === "objective_receipt" && parsedState.valueState === "known") {
      objectiveMeasured += 1;
    }
  });
  const declared = [
    ["known", publication.known_count], ["pending", publication.pending_count],
    ["unknown", publication.unknown_count], ["not_applicable", publication.not_applicable_count],
    ["abstained", publication.abstained_count], ["execution_error", publication.execution_error_count],
  ] as const;
  let total = 0;
  for (const [state, candidate] of declared) {
    const count = integer(candidate, 0, 20);
    if (count !== (counts.get(state) ?? 0)) throw new MetricPublicationV2PayloadError();
    total += count;
  }
  if (total !== 20 || integer(publication.objective_measured_count, 0, 5) !== objectiveMeasured) {
    throw new MetricPublicationV2PayloadError();
  }
  return value as MetricPublicationV2;
}
