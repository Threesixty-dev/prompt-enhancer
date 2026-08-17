/**
 * Typed frontend port for a FUTURE canonical team control plane.
 *
 * Nothing in the shipped backend implements this port. The dashboard consumes
 * it only through two honest adapters:
 *
 * - a synthetic in-memory fixture (development preview, fictional cohort);
 * - an "unavailable" adapter for the local loopback runtime that reports the
 *   absence of any team, organization, sync, or billing service.
 *
 * Design rules carried by the types themselves:
 * - Team and organization views are aggregates over a cohort. Individual
 *   member rows exist only behind an explicit visibility grant.
 * - No ranking, leaderboard, or single employee/developer score can be
 *   expressed: aggregates carry cohort size, missingness, comparability,
 *   freshness, and uncertainty instead.
 * - Missing values stay unknown. Suppressed small cohorts stay suppressed.
 * - Every payload states its origin so a fixture can never be mistaken for a
 *   live account, sync, billing, or calibrated measurement.
 */
export const TEAM_CONTROL_PLANE_PORT_VERSION = "team-control-plane-port.v0" as const;

export type AnalyticsScope = "me" | "team" | "organization";

export const ANALYTICS_SCOPES: readonly AnalyticsScope[] = ["me", "team", "organization"];

export type TeamDataOrigin = "synthetic_fixture" | "local_loopback" | "team_control_plane";

export type ScopeAccessState = "allowed" | "denied" | "unavailable";

export type ScopeAccessReason =
  | "granted"
  | "personal_scope_served_locally"
  | "local_runtime_has_no_team_service"
  | "team_sync_not_configured"
  | "role_insufficient"
  | "organization_policy_disabled"
  | "consent_required";

export interface ScopeAccess {
  /** Opaque authorization principal; never a username, email, or account id. */
  principal_id: string;
  scope: AnalyticsScope;
  state: ScopeAccessState;
  reason: ScopeAccessReason;
  /** Human-safe cohort label supplied by the control plane; never a person's name. */
  cohort_label: string | null;
  /** Opaque pseudonymous identifiers bind grants and requests to one exact cohort. */
  cohort_id: string | null;
  team_id: string | null;
  organization_id: string | null;
  /** Immutable server-issued identity for the aggregate query in this scope. */
  aggregate_query_id: string | null;
}

export interface TeamAggregateRequest {
  principal_id: string;
  scope: AnalyticsScope;
  cohort_id: string;
  team_id: string | null;
  organization_id: string | null;
  query_id: string;
}

export type MemberVisibilityState = "allowed" | "denied" | "unavailable";

export type MemberVisibilityReason =
  | "granted_with_member_consent"
  | "permission_not_granted"
  | "member_consent_missing"
  | "cohort_below_minimum"
  | "unavailable_in_runtime";

export interface MemberVisibilityAudit {
  /** Role that issued the grant (never an identity), or null when no grant exists. */
  granted_by_role: string | null;
  granted_at: string | null;
  expires_at: string | null;
  /** True when opening the member view is written to an audit log. */
  access_logged: boolean;
  log_destination: "local_audit_log" | "team_control_plane" | null;
}

export interface MemberVisibilityGrant {
  /** Opaque principal to whom this grant was issued. */
  principal_id: string;
  /** Opaque grant and target identities; null means no usable grant exists. */
  grant_id: string | null;
  scope: Exclude<AnalyticsScope, "me"> | null;
  cohort_id: string | null;
  team_id: string | null;
  organization_id: string | null;
  state: MemberVisibilityState;
  reason: MemberVisibilityReason;
  audit: MemberVisibilityAudit;
}

export interface TeamMemberVisibilityRequest {
  principal_id: string;
  scope: Exclude<AnalyticsScope, "me">;
  cohort_id: string;
  team_id: string | null;
  organization_id: string | null;
  grant_id: string;
}

export type ReadinessCardId = "local" | "team_sync" | "deep_analysis" | "billing";

export type ReadinessState = "ready" | "partial" | "checking" | "not_configured" | "unavailable";

export type ReadinessReason =
  | "synthetic_fixture"
  | "loopback_service_checking"
  | "loopback_service_available"
  | "loopback_service_unavailable"
  | "no_team_sync_service_in_this_build"
  | "team_sync_not_configured"
  | "deep_analysis_not_in_synthetic_preview"
  | "deep_analysis_not_verified_by_this_view"
  | "no_billing_service_in_this_build";

export type ReadinessActionKind =
  | "none"
  | "open_local_sources"
  | "open_job_centre"
  | "open_methods_and_models";

export interface ReadinessCard {
  id: ReadinessCardId;
  state: ReadinessState;
  reason: ReadinessReason;
  checked_at: string | null;
  action: { kind: ReadinessActionKind; enabled: boolean };
}

export interface TeamCapabilityReport {
  port_version: typeof TEAM_CONTROL_PLANE_PORT_VERSION;
  origin: TeamDataOrigin;
  /** Opaque subject of every capability, request, and grant in this report. */
  principal_id: string;
  scopes: readonly ScopeAccess[];
  member_visibility: MemberVisibilityGrant;
  readiness: readonly ReadinessCard[];
  checked_at: string;
}

export type MetricDirection = "higher_is_better" | "lower_is_better";

/**
 * Aggregate value states. Suppression is a deliberate refusal to publish a
 * value that could re-identify a member; its typed reason distinguishes a
 * directly small cohort from overlap/differencing or identity protection.
 * `withheld_not_comparable` refuses a ratio-of-sums across incompatible
 * definitions or windows. Neither is unknown and neither is zero.
 */
export type TeamMetricValueState =
  | "known"
  | "suppressed_small_cohort"
  | "suppressed_privacy_policy"
  | "withheld_not_comparable"
  | "unknown"
  | "not_applicable"
  | "abstained"
  | "unavailable";

/** Measured typed receipts and experimental model ranges never merge silently. */
export type TeamMetricProvenance = "measured_typed" | "experimental_model";

export interface TeamMetricCohort {
  member_count: number | null;
  session_count: number | null;
  /** Minimum size of the described cohort itself. */
  minimum_member_count: number;
  /** Minimum distinct contributing members required to publish a value/count. */
  minimum_contributor_count: number;
}

export interface TeamMetricMissingness {
  members_with_value: number | null;
  members_in_cohort: number | null;
  sessions_without_receipt: number | null;
}

export type TeamMetricComparabilityState =
  | "comparable"
  | "mixed_definition_versions"
  | "mixed_windows"
  | "not_comparable";

export interface TeamMetricComparability {
  state: TeamMetricComparabilityState;
  definition_versions: readonly number[];
}

export interface TeamMetricFreshness {
  newest_receipt_at: string | null;
  oldest_receipt_at: string | null;
  stale_member_count: number | null;
  stale_after_days: number;
}

/**
 * `wilson_95` is a sampling interval on an exact measured fraction.
 * `model_range_90` is the central 90% range of an experimental model estimate;
 * it is a model judgment, never measured evidence, and is only valid together
 * with `provenance: "experimental_model"`.
 */
export interface TeamMetricUncertainty {
  kind: "interval" | "not_estimated";
  method: "wilson_95" | "model_range_90" | null;
  low: number | null;
  high: number | null;
}

export interface TeamMetricAggregate {
  metric_key: string;
  definition_version: number;
  direction: MetricDirection;
  value_state: TeamMetricValueState;
  /** Exact reason a value is suppressed; null for every published/non-suppressed state. */
  suppression_reason: TeamMetricSuppressionReason | null;
  /** Ratio-of-sums numerator across the cohort; never an average of member percentages. */
  numerator: number | null;
  denominator: number | null;
  numeric_value: number | null;
  provenance: TeamMetricProvenance;
  cohort: TeamMetricCohort;
  missingness: TeamMetricMissingness;
  comparability: TeamMetricComparability;
  freshness: TeamMetricFreshness;
  uncertainty: TeamMetricUncertainty;
}

export type TeamMetricSuppressionReason =
  | "small_cohort"
  | "overlap_or_differencing"
  | "query_identity_mismatch";

export interface TeamAggregateWindow {
  label: string;
  started_at: string;
  ended_at: string;
}

export interface TeamAggregateSnapshot {
  port_version: typeof TEAM_CONTROL_PLANE_PORT_VERSION;
  origin: TeamDataOrigin;
  principal_id: string;
  /** Exact immutable scope/cohort query evaluated for this response. */
  request: TeamAggregateRequest;
  scope: AnalyticsScope;
  cohort_label: string;
  window: TeamAggregateWindow;
  generated_at: string;
  /** Aggregates are the only shape this port can publish for a cohort. */
  publication_policy: "aggregate_only_no_ranking_no_universal_score";
  calibration: "uncalibrated_exact_fractions";
  /**
   * One entry per (metric_key, provenance). A measured entry and an
   * experimental entry for the same key stay separate rows; consumers must
   * never blend them into one value.
   */
  metrics: readonly TeamMetricAggregate[];
}

export interface TeamMemberMetricCell {
  metric_key: string;
  definition_version: number;
  value_state: "known" | "unknown" | "not_applicable" | "abstained";
  numerator: number | null;
  denominator: number | null;
  numeric_value: number | null;
  provenance: TeamMetricProvenance;
  newest_receipt_at: string | null;
}

export interface TeamMemberRow {
  /** Pseudonymous member identifier (64 lowercase hex characters). */
  member_id: string;
  /** Neutral fixture handle such as "Member 03"; never a real name or account. */
  display_handle: string;
  consent: "granted" | "withheld";
  metrics: readonly TeamMemberMetricCell[];
}

export interface TeamMemberVisibilityPage {
  port_version: typeof TEAM_CONTROL_PLANE_PORT_VERSION;
  origin: TeamDataOrigin;
  principal_id: string;
  /** Exact authorization request the server evaluated for this page. */
  request: TeamMemberVisibilityRequest;
  grant: MemberVisibilityGrant;
  /** Rows are ordered by member identifier only; the port never orders by value. */
  ordering: "stable_member_id";
  members: readonly TeamMemberRow[];
  /** Members who withheld consent are counted, never listed. */
  withheld_member_count: number;
}

export type TeamControlPlaneErrorCode =
  | "scope_not_allowed"
  | "scope_not_served_by_this_runtime"
  | "member_visibility_not_granted"
  | "member_visibility_unavailable";

export class TeamControlPlaneError extends Error {
  readonly code: TeamControlPlaneErrorCode;

  constructor(code: TeamControlPlaneErrorCode, message: string) {
    super(message);
    this.name = "TeamControlPlaneError";
    this.code = code;
  }
}

export function isTeamControlPlaneError(value: unknown): value is TeamControlPlaneError {
  return value instanceof TeamControlPlaneError;
}

export interface TeamControlPlanePort {
  readonly portVersion: typeof TEAM_CONTROL_PLANE_PORT_VERSION;
  readonly origin: TeamDataOrigin;
  /** Immutable opaque principal for which this adapter was composed. */
  readonly principalId: string;
  getCapabilities(signal?: AbortSignal): Promise<TeamCapabilityReport>;
  getAggregate(request: TeamAggregateRequest, signal?: AbortSignal): Promise<TeamAggregateSnapshot>;
  getMemberVisibility(request: TeamMemberVisibilityRequest, signal?: AbortSignal): Promise<TeamMemberVisibilityPage>;
}

export interface TeamControlPlaneStampedResponse {
  port_version: typeof TEAM_CONTROL_PLANE_PORT_VERSION;
  origin: TeamDataOrigin;
  principal_id: string;
}

/**
 * A payload is usable only when its immutable version, origin, and opaque
 * principal match the exact port that returned it. In particular, a
 * local-loopback declaration can never launder a synthetic fixture response
 * or another principal's cached payload into an active surface.
 */
export function teamControlPlaneResponseMatchesPort(
  response: unknown,
  port: Pick<TeamControlPlanePort, "origin" | "portVersion" | "principalId">,
): boolean {
  return typeof response === "object"
    && response !== null
    && "port_version" in response
    && "origin" in response
    && "principal_id" in response
    && response.port_version === port.portVersion
    && response.origin === port.origin
    && response.principal_id === port.principalId;
}

const TEAM_IDENTITY = /^[0-9a-f]{64}$/;
const METRIC_KEY = /^[a-z][a-z0-9_.-]*$/;

export interface TeamReviewedMetricContract {
  metric_key: string;
  definition_version: number;
  direction: MetricDirection;
}

/** Exact reviewed metric contracts accepted by the v0 team port. A new key or
 * version requires an explicit frontend/port review rather than rendering by
 * accident. */
export const TEAM_REVIEWED_METRIC_CONTRACTS: readonly TeamReviewedMetricContract[] = [
  { metric_key: "prompt.task_definition_coverage", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "prompt.problem_evidence_quality", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "prompt.context_sufficiency", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "prompt.constraint_precision", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "prompt.acceptance_testability", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "prompt.deliverable_contract", definition_version: 3, direction: "higher_is_better" },
  { metric_key: "collaboration.ambiguity_resolution", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "collaboration.clarification_yield", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "collaboration.exploration_conversion", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "collaboration.scope_change_discipline", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "collaboration.rework_candidate_rate", definition_version: 2, direction: "lower_is_better" },
  { metric_key: "logic.decomposition_coverage", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "logic.decision_rationale_coverage", definition_version: 3, direction: "higher_is_better" },
  { metric_key: "logic.open_loop_closure", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "outcome.verification_strategy_adequacy", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "logic.hypothesis_test_linkage", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "logic.requirement_action_traceability", definition_version: 3, direction: "higher_is_better" },
  { metric_key: "outcome.agent_claim_grounding", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "outcome.first_pass_verification", definition_version: 2, direction: "higher_is_better" },
  { metric_key: "outcome.verified_requirement_coverage", definition_version: 2, direction: "higher_is_better" },
];

const REVIEWED_METRIC_BY_KEY = new Map(
  TEAM_REVIEWED_METRIC_CONTRACTS.map((contract) => [contract.metric_key, contract]),
);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nullableIdentity(value: unknown): value is string | null {
  return value === null || (typeof value === "string" && TEAM_IDENTITY.test(value));
}

function nonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 0;
}

function nullableNonNegativeInteger(value: unknown): value is number | null {
  return value === null || nonNegativeInteger(value);
}

function boundedNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

function parseableInstant(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "";
}

function scopeReasonMatches(scope: AnalyticsScope, state: ScopeAccessState, reason: ScopeAccessReason): boolean {
  switch (reason) {
    case "granted": return state === "allowed";
    case "personal_scope_served_locally": return scope === "me" && state === "allowed";
    case "local_runtime_has_no_team_service": return scope !== "me" && state === "unavailable";
    case "team_sync_not_configured": return scope !== "me" && state === "unavailable";
    case "role_insufficient": return scope !== "me" && state === "denied";
    case "organization_policy_disabled": return scope === "organization" && (state === "denied" || state === "unavailable");
    case "consent_required": return scope !== "me" && state === "denied";
    default: return false;
  }
}

function scopeAccessIsValid(value: unknown): value is ScopeAccess {
  if (!isRecord(value)) return false;
  const scope = value.scope;
  const state = value.state;
  const reason = value.reason;
  if (
    typeof value.principal_id !== "string" || !TEAM_IDENTITY.test(value.principal_id)
    ||
    (scope !== "me" && scope !== "team" && scope !== "organization")
    || (state !== "allowed" && state !== "denied" && state !== "unavailable")
    || (reason !== "granted"
      && reason !== "personal_scope_served_locally"
      && reason !== "local_runtime_has_no_team_service"
      && reason !== "team_sync_not_configured"
      && reason !== "role_insufficient"
      && reason !== "organization_policy_disabled"
      && reason !== "consent_required")
    || !scopeReasonMatches(scope, state, reason)
  ) return false;
  if (state !== "allowed") {
    return value.cohort_label === null
      && value.cohort_id === null
      && value.team_id === null
      && value.organization_id === null
      && value.aggregate_query_id === null;
  }
  if (reason === "personal_scope_served_locally") {
    return value.cohort_label === null
      && value.cohort_id === null
      && value.team_id === null
      && value.organization_id === null
      && value.aggregate_query_id === null;
  }
  if (
    !nonEmptyString(value.cohort_label)
    || typeof value.cohort_id !== "string" || !TEAM_IDENTITY.test(value.cohort_id)
    || typeof value.aggregate_query_id !== "string" || !TEAM_IDENTITY.test(value.aggregate_query_id)
    || !nullableIdentity(value.team_id)
    || !nullableIdentity(value.organization_id)
  ) return false;
  if (scope === "me") return value.team_id === null && value.organization_id === null;
  if (scope === "team") return value.team_id !== null;
  return value.organization_id !== null;
}

/** Complete structural grant validator. Authorization still requires an exact
 * active request and an unexpired grant at the moment of reveal. */
export function teamMemberVisibilityGrantIsValid(value: unknown): value is MemberVisibilityGrant {
  if (!isRecord(value) || !isRecord(value.audit)) return false;
  const audit = value.audit;
  if (typeof value.principal_id !== "string" || !TEAM_IDENTITY.test(value.principal_id)) return false;
  if (value.state === "allowed") {
    if (
      value.reason !== "granted_with_member_consent"
      || (value.scope !== "team" && value.scope !== "organization")
      || typeof value.grant_id !== "string" || !TEAM_IDENTITY.test(value.grant_id)
      || typeof value.cohort_id !== "string" || !TEAM_IDENTITY.test(value.cohort_id)
      || !nullableIdentity(value.team_id)
      || !nullableIdentity(value.organization_id)
      || (value.scope === "team" && value.team_id === null)
      || (value.scope === "organization" && value.organization_id === null)
      || !nonEmptyString(audit.granted_by_role)
      || !parseableInstant(audit.granted_at)
      || !parseableInstant(audit.expires_at)
      || Date.parse(audit.granted_at) >= Date.parse(audit.expires_at)
      || audit.access_logged !== true
      || (audit.log_destination !== "local_audit_log" && audit.log_destination !== "team_control_plane")
    ) return false;
    return true;
  }
  if (value.state !== "denied" && value.state !== "unavailable") return false;
  const reasonMatches = value.state === "denied"
    ? value.reason === "permission_not_granted"
      || value.reason === "member_consent_missing"
      || value.reason === "cohort_below_minimum"
    : value.reason === "unavailable_in_runtime";
  return reasonMatches
    && value.grant_id === null
    && value.scope === null
    && value.cohort_id === null
    && value.team_id === null
    && value.organization_id === null
    && audit.granted_by_role === null
    && audit.granted_at === null
    && audit.expires_at === null
    && audit.access_logged === false
    && audit.log_destination === null;
}

const READINESS_REASON_CONTRACT: Readonly<Record<ReadinessReason, {
  id: ReadinessCardId;
  state: ReadinessState;
  action: ReadinessActionKind;
  enabled: boolean;
  checked: "required" | "absent";
}>> = {
  synthetic_fixture: { id: "local", state: "ready", action: "none", enabled: false, checked: "required" },
  loopback_service_checking: { id: "local", state: "checking", action: "open_local_sources", enabled: true, checked: "absent" },
  loopback_service_available: { id: "local", state: "ready", action: "open_local_sources", enabled: true, checked: "required" },
  loopback_service_unavailable: { id: "local", state: "unavailable", action: "open_local_sources", enabled: true, checked: "required" },
  no_team_sync_service_in_this_build: { id: "team_sync", state: "unavailable", action: "none", enabled: false, checked: "required" },
  team_sync_not_configured: { id: "team_sync", state: "not_configured", action: "none", enabled: false, checked: "required" },
  deep_analysis_not_in_synthetic_preview: { id: "deep_analysis", state: "unavailable", action: "open_methods_and_models", enabled: true, checked: "required" },
  deep_analysis_not_verified_by_this_view: { id: "deep_analysis", state: "not_configured", action: "open_job_centre", enabled: true, checked: "required" },
  no_billing_service_in_this_build: { id: "billing", state: "unavailable", action: "none", enabled: false, checked: "required" },
};

function readinessCardIsValid(value: unknown): value is ReadinessCard {
  if (!isRecord(value) || !isRecord(value.action) || typeof value.reason !== "string") return false;
  const contract = READINESS_REASON_CONTRACT[value.reason as ReadinessReason];
  if (contract === undefined) return false;
  return value.id === contract.id
    && value.state === contract.state
    && value.action.kind === contract.action
    && value.action.enabled === contract.enabled
    && (contract.checked === "required" ? parseableInstant(value.checked_at) : value.checked_at === null);
}

/** Fail-closed capability validator used before scope, grant, or readiness data
 * can enter component state. */
export function teamCapabilityReportIsValid(
  value: unknown,
  port: Pick<TeamControlPlanePort, "origin" | "portVersion" | "principalId">,
): value is TeamCapabilityReport {
  if (
    !isRecord(value)
    || !teamControlPlaneResponseMatchesPort(value, port)
    || typeof value.principal_id !== "string" || !TEAM_IDENTITY.test(value.principal_id)
    || !parseableInstant(value.checked_at)
    || !Array.isArray(value.scopes)
    || value.scopes.length !== ANALYTICS_SCOPES.length
    || !value.scopes.every(scopeAccessIsValid)
    || !teamMemberVisibilityGrantIsValid(value.member_visibility)
    || !Array.isArray(value.readiness)
    || value.readiness.length !== 4
    || !value.readiness.every(readinessCardIsValid)
  ) return false;
  const scopeNames = value.scopes.map((access) => access.scope);
  if (new Set(scopeNames).size !== ANALYTICS_SCOPES.length
    || !ANALYTICS_SCOPES.every((scope) => scopeNames.includes(scope))) return false;
  const readinessIds = value.readiness.map((card) => card.id);
  if (new Set(readinessIds).size !== 4
    || !(["local", "team_sync", "deep_analysis", "billing"] as const).every((id) => readinessIds.includes(id))) return false;
  const queryBearingScopes = value.scopes.filter((access) => access.state === "allowed" && access.cohort_id !== null);
  const cohortIds = queryBearingScopes.map((access) => access.cohort_id as string);
  const queryIds = queryBearingScopes.map((access) => access.aggregate_query_id as string);
  if (new Set(cohortIds).size !== cohortIds.length || new Set(queryIds).size !== queryIds.length) return false;
  const grant = value.member_visibility;
  if (!value.scopes.every((access) => access.principal_id === value.principal_id)
    || grant.principal_id !== value.principal_id) return false;
  if (grant.state !== "allowed") return true;
  const expectedAuditDestination = value.origin === "team_control_plane"
    ? "team_control_plane"
    : "local_audit_log";
  if (grant.audit.log_destination !== expectedAuditDestination) return false;
  const access = value.scopes.find((candidate) => candidate.scope === grant.scope);
  return access?.state === "allowed"
    && access.principal_id === grant.principal_id
    && access.cohort_id === grant.cohort_id
    && access.team_id === grant.team_id
    && access.organization_id === grant.organization_id;
}

export function teamAggregateRequestsEqual(
  left: unknown,
  right: TeamAggregateRequest,
): left is TeamAggregateRequest {
  return isRecord(left)
    && left.principal_id === right.principal_id
    && left.scope === right.scope
    && left.cohort_id === right.cohort_id
    && left.team_id === right.team_id
    && left.organization_id === right.organization_id
    && left.query_id === right.query_id;
}

function validAggregateRequest(request: TeamAggregateRequest): boolean {
  if (
    !TEAM_IDENTITY.test(request.principal_id)
    || !ANALYTICS_SCOPES.includes(request.scope)
    || !TEAM_IDENTITY.test(request.cohort_id)
    || !TEAM_IDENTITY.test(request.query_id)
    || !nullableIdentity(request.team_id)
    || !nullableIdentity(request.organization_id)
  ) return false;
  if (request.scope === "me") return request.team_id === null && request.organization_id === null;
  if (request.scope === "team") return request.team_id !== null;
  return request.organization_id !== null;
}

/** Build the only aggregate request authorized by a capability row. */
export function teamAggregateRequestForAccess(access: ScopeAccess): TeamAggregateRequest | null {
  if (
    access.state !== "allowed"
    || !TEAM_IDENTITY.test(access.principal_id)
    || access.cohort_id === null
    || access.aggregate_query_id === null
    || !TEAM_IDENTITY.test(access.cohort_id)
    || !TEAM_IDENTITY.test(access.aggregate_query_id)
    || !nullableIdentity(access.team_id)
    || !nullableIdentity(access.organization_id)
  ) return null;
  if (access.scope === "me" && (access.team_id !== null || access.organization_id !== null)) return null;
  if (access.scope === "team" && access.team_id === null) return null;
  if (access.scope === "organization" && access.organization_id === null) return null;
  return {
    principal_id: access.principal_id,
    scope: access.scope,
    cohort_id: access.cohort_id,
    team_id: access.team_id,
    organization_id: access.organization_id,
    query_id: access.aggregate_query_id,
  };
}

function validMetricAggregate(value: unknown): value is TeamMetricAggregate {
  if (!isRecord(value)) return false;
  const provenance = value.provenance;
  const state = value.value_state;
  const reviewed = typeof value.metric_key === "string" ? REVIEWED_METRIC_BY_KEY.get(value.metric_key) : undefined;
  const suppressed = state === "suppressed_small_cohort" || state === "suppressed_privacy_policy";
  const validState = state === "known"
    || suppressed
    || state === "withheld_not_comparable"
    || state === "unknown"
    || state === "not_applicable"
    || state === "abstained"
    || state === "unavailable";
  if (
    typeof value.metric_key !== "string" || !METRIC_KEY.test(value.metric_key)
    || reviewed === undefined
    || !nonNegativeInteger(value.definition_version) || value.definition_version < 1
    || value.definition_version !== reviewed.definition_version
    || (value.direction !== "higher_is_better" && value.direction !== "lower_is_better")
    || value.direction !== reviewed.direction
    || (provenance !== "measured_typed" && provenance !== "experimental_model")
    || !validState
  ) return false;

  if (suppressed) {
    if (
      (state === "suppressed_small_cohort" && value.suppression_reason !== "small_cohort")
      || (state === "suppressed_privacy_policy"
        && value.suppression_reason !== "overlap_or_differencing"
        && value.suppression_reason !== "query_identity_mismatch")
    ) return false;
  } else if (value.suppression_reason !== null) return false;

  const numerator = value.numerator;
  const denominator = value.denominator;
  const numeric = value.numeric_value;
  if (state === "known") {
    if (!boundedNumber(numeric)) return false;
    if (provenance === "measured_typed") {
      if (
        typeof numerator !== "number" || !nonNegativeInteger(numerator)
        || typeof denominator !== "number" || !nonNegativeInteger(denominator) || denominator <= 0
        || numerator > denominator
        || Math.abs(numeric - numerator / denominator) > 1e-9
      ) return false;
    } else if (!(
      (numerator === null && denominator === null)
      || (typeof numerator === "number" && nonNegativeInteger(numerator)
        && typeof denominator === "number" && nonNegativeInteger(denominator)
        && denominator > 0 && numerator <= denominator
        && Math.abs(numeric - numerator / denominator) <= 1e-9)
    )) return false;
  } else if (numerator !== null || denominator !== null || numeric !== null) return false;

  const cohort = value.cohort;
  const missingness = value.missingness;
  if (
    !isRecord(cohort)
    || !nullableNonNegativeInteger(cohort.member_count)
    || !nullableNonNegativeInteger(cohort.session_count)
    || !nonNegativeInteger(cohort.minimum_member_count) || cohort.minimum_member_count < 1
    || !nonNegativeInteger(cohort.minimum_contributor_count) || cohort.minimum_contributor_count < 1
    || !isRecord(missingness)
    || !nullableNonNegativeInteger(missingness.members_with_value)
    || !nullableNonNegativeInteger(missingness.members_in_cohort)
    || !nullableNonNegativeInteger(missingness.sessions_without_receipt)
  ) return false;
  if (
    missingness.members_with_value !== null
    && (cohort.member_count === null
      || missingness.members_with_value > cohort.member_count
      || missingness.members_with_value < cohort.minimum_contributor_count)
  ) return false;
  if (missingness.members_in_cohort !== cohort.member_count) return false;
  if (
    missingness.sessions_without_receipt !== null
    && (cohort.session_count === null || missingness.sessions_without_receipt > cohort.session_count)
  ) return false;
  if (state === "known" && missingness.members_with_value === null) return false;
  if (state === "known" && cohort.member_count !== null && cohort.member_count < cohort.minimum_member_count) return false;
  if (suppressed && (missingness.members_with_value !== null || missingness.sessions_without_receipt !== null)) return false;

  const comparability = value.comparability;
  if (!isRecord(comparability) || !Array.isArray(comparability.definition_versions)) return false;
  if (
    comparability.state !== "comparable"
    && comparability.state !== "mixed_definition_versions"
    && comparability.state !== "mixed_windows"
    && comparability.state !== "not_comparable"
  ) return false;
  const versions = comparability.definition_versions;
  if (
    versions.length === 0
    || versions.some((version) => !nonNegativeInteger(version) || version < 1)
    || new Set(versions).size !== versions.length
    || !versions.includes(value.definition_version)
    || (comparability.state === "comparable" && (versions.length !== 1 || versions[0] !== value.definition_version))
    || (comparability.state === "mixed_definition_versions" && versions.length < 2)
    || ((state === "withheld_not_comparable") !== (comparability.state !== "comparable"))
  ) return false;

  const freshness = value.freshness;
  if (
    !isRecord(freshness)
    || (freshness.newest_receipt_at !== null && !parseableInstant(freshness.newest_receipt_at))
    || (freshness.oldest_receipt_at !== null && !parseableInstant(freshness.oldest_receipt_at))
    || !nullableNonNegativeInteger(freshness.stale_member_count)
    || !nonNegativeInteger(freshness.stale_after_days) || freshness.stale_after_days < 1
  ) return false;
  if (
    freshness.newest_receipt_at !== null
    && freshness.oldest_receipt_at !== null
    && Date.parse(freshness.oldest_receipt_at) > Date.parse(freshness.newest_receipt_at)
  ) return false;
  if (
    freshness.stale_member_count !== null
    && (cohort.member_count === null
      || freshness.stale_member_count > cohort.member_count
      || (missingness.members_with_value !== null && freshness.stale_member_count > missingness.members_with_value))
  ) return false;
  if ((freshness.newest_receipt_at === null) !== (freshness.oldest_receipt_at === null)) return false;
  if (suppressed && (
    freshness.newest_receipt_at !== null
    || freshness.oldest_receipt_at !== null
    || freshness.stale_member_count !== null
  )) return false;

  const uncertainty = value.uncertainty;
  if (!isRecord(uncertainty)) return false;
  if (uncertainty.kind === "not_estimated") {
    if (uncertainty.method !== null || uncertainty.low !== null || uncertainty.high !== null) return false;
  } else if (uncertainty.kind === "interval") {
    if (
      (uncertainty.method !== "wilson_95" && uncertainty.method !== "model_range_90")
      || !boundedNumber(uncertainty.low)
      || !boundedNumber(uncertainty.high)
      || uncertainty.low > uncertainty.high
      || !boundedNumber(numeric)
      || numeric < uncertainty.low
      || numeric > uncertainty.high
      || (provenance === "measured_typed" && uncertainty.method !== "wilson_95")
      || (provenance === "experimental_model" && uncertainty.method !== "model_range_90")
      || state !== "known"
    ) return false;
  } else return false;
  return true;
}

/**
 * Strict fail-closed aggregate response validator. It checks the immutable
 * query identity plus publication-shape, count, fraction, interval,
 * suppression, and comparability invariants before any value can render.
 */
export function teamAggregateSnapshotIsValid(
  value: unknown,
  request: TeamAggregateRequest,
  port: Pick<TeamControlPlanePort, "origin" | "portVersion" | "principalId">,
): value is TeamAggregateSnapshot {
  if (
    !isRecord(value)
    || !validAggregateRequest(request)
    || request.principal_id !== port.principalId
    || !teamControlPlaneResponseMatchesPort(value, port)
    || !teamAggregateRequestsEqual(value.request, request)
    || value.scope !== request.scope
    || typeof value.cohort_label !== "string" || value.cohort_label.trim() === ""
    || value.publication_policy !== "aggregate_only_no_ranking_no_universal_score"
    || value.calibration !== "uncalibrated_exact_fractions"
    || !parseableInstant(value.generated_at)
    || !isRecord(value.window)
    || typeof value.window.label !== "string" || value.window.label.trim() === ""
    || !parseableInstant(value.window.started_at)
    || !parseableInstant(value.window.ended_at)
    || Date.parse(value.window.started_at) > Date.parse(value.window.ended_at)
    || Date.parse(value.generated_at) < Date.parse(value.window.ended_at)
    || !Array.isArray(value.metrics) || value.metrics.length === 0
    || !value.metrics.every(validMetricAggregate)
  ) return false;
  const validatedWindow = value.window as unknown as TeamAggregateWindow;
  const windowStart = Date.parse(validatedWindow.started_at);
  const windowEnd = Date.parse(validatedWindow.ended_at);
  const identities = value.metrics.map((metric) => JSON.stringify([metric.metric_key, metric.provenance]));
  if (new Set(identities).size !== identities.length) return false;
  const first = value.metrics[0].cohort;
  if (!value.metrics.every((metric) =>
    metric.cohort.member_count === first.member_count
    && metric.cohort.session_count === first.session_count
    && metric.cohort.minimum_member_count === first.minimum_member_count
    && metric.cohort.minimum_contributor_count === first.minimum_contributor_count
    && (metric.freshness.oldest_receipt_at === null
      || (Date.parse(metric.freshness.oldest_receipt_at) >= windowStart
        && Date.parse(metric.freshness.oldest_receipt_at) <= windowEnd))
    && (metric.freshness.newest_receipt_at === null
      || (Date.parse(metric.freshness.newest_receipt_at) >= windowStart
        && Date.parse(metric.freshness.newest_receipt_at) <= windowEnd)))) return false;
  const metricDefinitions = new Map<string, { definitionVersion: number; direction: MetricDirection; measured: boolean }>();
  for (const metric of value.metrics) {
    const existing = metricDefinitions.get(metric.metric_key);
    if (existing === undefined) {
      metricDefinitions.set(metric.metric_key, {
        definitionVersion: metric.definition_version,
        direction: metric.direction,
        measured: metric.provenance === "measured_typed",
      });
      continue;
    }
    if (existing.definitionVersion !== metric.definition_version || existing.direction !== metric.direction) return false;
    if (metric.provenance === "measured_typed") existing.measured = true;
  }
  const measuredByKey = new Map(
    value.metrics
      .filter((metric) => metric.provenance === "measured_typed")
      .map((metric) => [metric.metric_key, metric]),
  );
  return value.metrics.every((metric) => {
    if (metric.provenance !== "experimental_model") return true;
    const measured = measuredByKey.get(metric.metric_key);
    if (measured === undefined || metricDefinitions.get(metric.metric_key)?.measured !== true) return false;
    if (measured.value_state === "suppressed_small_cohort" || measured.value_state === "suppressed_privacy_policy") {
      return metric.value_state === measured.value_state
        && metric.suppression_reason === measured.suppression_reason;
    }
    if (measured.value_state === "withheld_not_comparable") {
      return metric.value_state === "withheld_not_comparable"
        && metric.comparability.state === measured.comparability.state
        && JSON.stringify(metric.comparability.definition_versions) === JSON.stringify(measured.comparability.definition_versions);
    }
    return true;
  });
}

/**
 * Wilson score interval for a binomial fraction. It describes sampling
 * uncertainty of an exact cohort fraction; it is not calibration and it never
 * turns a missing value into a number.
 */
export function wilsonInterval(
  numerator: number,
  denominator: number,
  z = 1.96,
): { low: number; high: number } | null {
  if (
    !Number.isFinite(numerator)
    || !Number.isFinite(denominator)
    || denominator <= 0
    || numerator < 0
    || numerator > denominator
  ) return null;
  const p = numerator / denominator;
  const z2 = z * z;
  const centre = (p + z2 / (2 * denominator)) / (1 + z2 / denominator);
  const spread = (z * Math.sqrt((p * (1 - p)) / denominator + z2 / (4 * denominator * denominator)))
    / (1 + z2 / denominator);
  return {
    low: Math.max(0, Math.min(1, centre - spread)),
    high: Math.max(0, Math.min(1, centre + spread)),
  };
}
