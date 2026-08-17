import {
  TEAM_CONTROL_PLANE_PORT_VERSION,
  TEAM_REVIEWED_METRIC_CONTRACTS,
  TeamControlPlaneError,
  teamAggregateRequestsEqual,
  wilsonInterval,
  type AnalyticsScope,
  type MemberVisibilityGrant,
  type MetricDirection,
  type ReadinessCard,
  type ScopeAccess,
  type TeamAggregateSnapshot,
  type TeamAggregateRequest,
  type TeamCapabilityReport,
  type TeamControlPlanePort,
  type TeamMemberMetricCell,
  type TeamMemberRow,
  type TeamMemberVisibilityRequest,
  type TeamMemberVisibilityPage,
  type TeamMetricAggregate,
  type TeamMetricSuppressionReason,
  type TeamMetricValueState,
} from "./teamControlPlane";

/**
 * Fictional, content-free team fixture for the synthetic development preview.
 *
 * Every identifier is a reserved pseudonym, every handle is a neutral
 * placeholder, and every payload is stamped `origin: "synthetic_fixture"`.
 * The fixture deliberately exercises each aggregate state (known, suppressed,
 * withheld, unknown, not applicable, abstained) so the UI can be tested without
 * a backend and without pretending a team service exists.
 */

const FIXTURE_NOW = "2040-01-31T09:00:00Z";
const WINDOW_START = "2040-01-01T00:00:00Z";
const WINDOW_END = "2040-01-31T00:00:00Z";
const STALE_AFTER_DAYS = 14;
const MINIMUM_TEAM_MEMBERS = 3;
const SYNTHETIC_COHORT_ID = "19".repeat(32);
const SYNTHETIC_ME_COHORT_ID = "08".repeat(32);
const SYNTHETIC_TEAM_ID = "2a".repeat(32);
const SYNTHETIC_ORGANIZATION_ID = "3b".repeat(32);
const SYNTHETIC_MEMBER_VISIBILITY_GRANT_ID = "4c".repeat(32);
const SYNTHETIC_ME_QUERY_ID = "5d".repeat(32);
const SYNTHETIC_TEAM_QUERY_ID = "6e".repeat(32);
export const SYNTHETIC_PRINCIPAL_ID = "7f".repeat(32);
const LOCAL_RUNTIME_PRINCIPAL_ID = "90".repeat(32);

export interface SyntheticMemberRevealAuditEvent {
  event: "member_visibility_revealed";
  occurred_at: string;
  destination: "local_audit_log";
  grant_reason: "granted_with_member_consent";
  principal_id: string;
  grant_id: string;
  scope: Exclude<AnalyticsScope, "me">;
  cohort_id: string;
  team_id: string | null;
  organization_id: string | null;
  returned_member_count: number;
  withheld_member_count: number;
}

export interface SyntheticTeamControlPlanePort extends TeamControlPlanePort {
  /** Content-free in-memory events for proving the fictional reveal is audited. */
  getRevealAuditEvents(): readonly SyntheticMemberRevealAuditEvent[];
}

export const SYNTHETIC_TEAM_COHORT_LABEL = "Synthetic platform guild (fixture cohort)";
export const SYNTHETIC_ME_COHORT_LABEL = "This installation only (fixture)";
export const SYNTHETIC_TEAM_WINDOW_LABEL = "Newest 30 days · fixture window";

/** Pseudonymous member identifiers: 64 lowercase hex characters each. */
export const SYNTHETIC_TEAM_MEMBER_IDS: readonly string[] = [
  "a1".repeat(32),
  "b2".repeat(32),
  "c3".repeat(32),
  "d4".repeat(32),
  "e5".repeat(32),
];

interface MetricSeed {
  key: string;
  version: number;
  direction: MetricDirection;
}

/** Metric identities mirror the shipped coaching lens definitions (versions included). */
export const SYNTHETIC_TEAM_METRIC_SEEDS: readonly MetricSeed[] = [
  ...TEAM_REVIEWED_METRIC_CONTRACTS.map((contract) => ({
    key: contract.metric_key,
    version: contract.definition_version,
    direction: contract.direction,
  })),
];

type MeasuredStory =
  | { kind: "known"; numerator: number; denominator: number; membersWithValue: number; staleMembers: number; oldest: string; newest: string }
  | { kind: "suppressed"; membersWithValue: number }
  | { kind: "withheld"; versions: readonly number[] }
  | { kind: "unknown" }
  | { kind: "not_applicable"; sessionsWithoutReceipt: 0 | null }
  | { kind: "abstained"; membersWithValue: number };

interface ExperimentalStory {
  median: number;
  low: number;
  high: number;
}

/** Hand-authored fictional cohort story per metric key (team scope). */
const TEAM_STORIES: Readonly<Record<string, MeasuredStory>> = {
  "prompt.task_definition_coverage": { kind: "known", numerator: 41, denominator: 57, membersWithValue: 5, staleMembers: 0, oldest: "2040-01-04T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "prompt.problem_evidence_quality": { kind: "known", numerator: 12, denominator: 28, membersWithValue: 3, staleMembers: 1, oldest: "2040-01-03T08:10:00Z", newest: "2040-01-29T11:05:00Z" },
  "prompt.context_sufficiency": { kind: "known", numerator: 33, denominator: 57, membersWithValue: 5, staleMembers: 0, oldest: "2040-01-04T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "prompt.constraint_precision": { kind: "suppressed", membersWithValue: 2 },
  "prompt.acceptance_testability": { kind: "known", numerator: 9, denominator: 31, membersWithValue: 4, staleMembers: 0, oldest: "2040-01-05T09:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "prompt.deliverable_contract": { kind: "withheld", versions: [1, 3] },
  "collaboration.ambiguity_resolution": { kind: "known", numerator: 14, denominator: 22, membersWithValue: 4, staleMembers: 0, oldest: "2040-01-06T12:00:00Z", newest: "2040-01-28T15:40:00Z" },
  "collaboration.clarification_yield": { kind: "known", numerator: 6, denominator: 9, membersWithValue: 3, staleMembers: 0, oldest: "2040-01-09T12:00:00Z", newest: "2040-01-27T10:15:00Z" },
  "collaboration.exploration_conversion": { kind: "not_applicable", sessionsWithoutReceipt: 0 },
  "collaboration.scope_change_discipline": { kind: "abstained", membersWithValue: 1 },
  "collaboration.rework_candidate_rate": { kind: "known", numerator: 7, denominator: 64, membersWithValue: 5, staleMembers: 0, oldest: "2040-01-04T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "logic.decomposition_coverage": { kind: "known", numerator: 19, denominator: 26, membersWithValue: 4, staleMembers: 0, oldest: "2040-01-05T09:00:00Z", newest: "2040-01-29T11:05:00Z" },
  "logic.decision_rationale_coverage": { kind: "unknown" },
  "logic.open_loop_closure": { kind: "known", numerator: 21, denominator: 30, membersWithValue: 5, staleMembers: 2, oldest: "2040-01-02T08:00:00Z", newest: "2040-01-25T09:30:00Z" },
  "outcome.verification_strategy_adequacy": { kind: "known", numerator: 15, denominator: 26, membersWithValue: 4, staleMembers: 0, oldest: "2040-01-05T09:00:00Z", newest: "2040-01-29T11:05:00Z" },
  "logic.hypothesis_test_linkage": { kind: "unknown" },
  "logic.requirement_action_traceability": { kind: "known", numerator: 24, denominator: 33, membersWithValue: 5, staleMembers: 0, oldest: "2040-01-04T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "outcome.agent_claim_grounding": { kind: "known", numerator: 40, denominator: 118, membersWithValue: 5, staleMembers: 0, oldest: "2040-01-04T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "outcome.first_pass_verification": { kind: "known", numerator: 11, denominator: 17, membersWithValue: 4, staleMembers: 1, oldest: "2040-01-03T08:10:00Z", newest: "2040-01-28T15:40:00Z" },
  "outcome.verified_requirement_coverage": { kind: "known", numerator: 13, denominator: 33, membersWithValue: 4, staleMembers: 0, oldest: "2040-01-05T09:00:00Z", newest: "2040-01-30T16:20:00Z" },
};

/** Experimental model ranges exist only where a fictional model projection ran; they never replace a measured row. */
const TEAM_EXPERIMENTAL: Readonly<Record<string, ExperimentalStory>> = {
  "prompt.task_definition_coverage": { median: 0.69, low: 0.55, high: 0.81 },
  "logic.decision_rationale_coverage": { median: 0.44, low: 0.31, high: 0.58 },
  "logic.hypothesis_test_linkage": { median: 0.52, low: 0.34, high: 0.69 },
};

/** Personal (single-installation) story; smaller denominators, no suppression floor. */
const ME_STORIES: Readonly<Record<string, MeasuredStory>> = {
  "prompt.task_definition_coverage": { kind: "known", numerator: 7, denominator: 9, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "prompt.problem_evidence_quality": { kind: "known", numerator: 3, denominator: 8, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-29T11:05:00Z" },
  "prompt.context_sufficiency": { kind: "known", numerator: 5, denominator: 9, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "prompt.constraint_precision": { kind: "known", numerator: 2, denominator: 5, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "prompt.acceptance_testability": { kind: "known", numerator: 1, denominator: 6, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "prompt.deliverable_contract": { kind: "known", numerator: 4, denominator: 7, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "collaboration.ambiguity_resolution": { kind: "known", numerator: 3, denominator: 4, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-12T12:00:00Z", newest: "2040-01-28T15:40:00Z" },
  "collaboration.clarification_yield": { kind: "not_applicable", sessionsWithoutReceipt: null },
  "collaboration.exploration_conversion": { kind: "not_applicable", sessionsWithoutReceipt: null },
  "collaboration.scope_change_discipline": { kind: "abstained", membersWithValue: 0 },
  "collaboration.rework_candidate_rate": { kind: "known", numerator: 2, denominator: 11, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "logic.decomposition_coverage": { kind: "known", numerator: 5, denominator: 5, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-29T11:05:00Z" },
  "logic.decision_rationale_coverage": { kind: "unknown" },
  "logic.open_loop_closure": { kind: "known", numerator: 4, denominator: 6, membersWithValue: 1, staleMembers: 1, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-15T09:30:00Z" },
  "outcome.verification_strategy_adequacy": { kind: "known", numerator: 3, denominator: 5, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-29T11:05:00Z" },
  "logic.hypothesis_test_linkage": { kind: "unknown" },
  "logic.requirement_action_traceability": { kind: "known", numerator: 6, denominator: 7, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "outcome.agent_claim_grounding": { kind: "known", numerator: 9, denominator: 21, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
  "outcome.first_pass_verification": { kind: "known", numerator: 0, denominator: 3, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-28T15:40:00Z" },
  "outcome.verified_requirement_coverage": { kind: "known", numerator: 3, denominator: 7, membersWithValue: 1, staleMembers: 0, oldest: "2040-01-08T10:00:00Z", newest: "2040-01-30T16:20:00Z" },
};

const ME_EXPERIMENTAL: Readonly<Record<string, ExperimentalStory>> = {
  "logic.decision_rationale_coverage": { median: 0.41, low: 0.22, high: 0.63 },
};

interface FixtureCohort {
  members: number;
  sessions: number;
  minimum: number;
}

export type ContributionDisclosureState = "released" | "suppressed";

export interface ContributionDisclosureDecision {
  state: ContributionDisclosureState;
  suppressionReason: TeamMetricSuppressionReason | null;
}

export interface ContributionDisclosureQuery {
  /** Same metric/definition/window family whose overlapping releases can be differenced. */
  family: string;
  /** Immutable scope/window identity. Reusing it with different members fails closed. */
  queryId: string;
  contributorIds: readonly string[];
  minimumContributorCount: number;
}

interface ContributionDisclosureRecord {
  family: string;
  state: ContributionDisclosureState;
  suppressionReason: TeamMetricSuppressionReason | null;
  blockedByIdentityReuse: boolean;
  signature: string;
  contributors: ReadonlySet<string>;
  minimum: number;
}

/**
 * In-memory synthetic disclosure guard. Decisions are sticky by immutable
 * query identity, and a new overlapping release is suppressed whenever
 * subtracting either released set would expose a non-empty sub-k remainder.
 */
export class StickyContributionDisclosurePolicy {
  private readonly records = new Map<string, ContributionDisclosureRecord>();

  decide(query: ContributionDisclosureQuery): ContributionDisclosureDecision {
    const contributors = new Set(query.contributorIds);
    const signature = JSON.stringify([...contributors].sort());
    const key = JSON.stringify({ family: query.family, queryId: query.queryId });
    const existing = this.records.get(key);
    if (existing !== undefined) {
      if (existing.signature !== signature || existing.minimum !== query.minimumContributorCount) {
        existing.blockedByIdentityReuse = true;
      }
      return existing.blockedByIdentityReuse
        ? { state: "suppressed", suppressionReason: "query_identity_mismatch" }
        : { state: existing.state, suppressionReason: existing.suppressionReason };
    }
    let state: ContributionDisclosureState = contributors.size < query.minimumContributorCount
      ? "suppressed"
      : "released";
    let suppressionReason: TeamMetricSuppressionReason | null = state === "suppressed"
      ? "small_cohort"
      : null;
    if (state === "released") {
      for (const prior of this.records.values()) {
        if (prior.family !== query.family || prior.state !== "released") continue;
        const overlaps = [...contributors].some((id) => prior.contributors.has(id));
        if (!overlaps) continue;
        const currentOnly = [...contributors].filter((id) => !prior.contributors.has(id)).length;
        const priorOnly = [...prior.contributors].filter((id) => !contributors.has(id)).length;
        if (
          (currentOnly > 0 && currentOnly < query.minimumContributorCount)
          || (priorOnly > 0 && priorOnly < prior.minimum)
        ) {
          state = "suppressed";
          suppressionReason = "overlap_or_differencing";
          break;
        }
      }
    }
    this.records.set(key, {
      family: query.family,
      state,
      suppressionReason,
      blockedByIdentityReuse: false,
      signature,
      contributors,
      minimum: query.minimumContributorCount,
    });
    return { state, suppressionReason };
  }
}

/** Sessions that carried no receipt for a metric, proportional to the members without a value. */
function sessionsWithoutReceipt(cohort: FixtureCohort, membersWithValue: number): number {
  if (cohort.members <= 0) return cohort.sessions;
  return Math.round(cohort.sessions * (1 - Math.min(cohort.members, membersWithValue) / cohort.members));
}

function measuredAggregate(
  seed: MetricSeed,
  story: MeasuredStory,
  cohort: FixtureCohort,
  disclosure: ContributionDisclosureDecision | null,
): TeamMetricAggregate {
  const base = {
    metric_key: seed.key,
    definition_version: seed.version,
    direction: seed.direction,
    provenance: "measured_typed" as const,
    suppression_reason: null as TeamMetricSuppressionReason | null,
    cohort: {
      member_count: cohort.members,
      session_count: cohort.sessions,
      minimum_member_count: cohort.minimum,
      minimum_contributor_count: cohort.minimum,
    },
    comparability: { state: "comparable" as const, definition_versions: [seed.version] },
  };
  const unknownFreshness = {
    newest_receipt_at: null,
    oldest_receipt_at: null,
    stale_member_count: null,
    stale_after_days: STALE_AFTER_DAYS,
  };
  const noValue = { numerator: null, denominator: null, numeric_value: null };
  const notEstimated = { kind: "not_estimated" as const, method: null, low: null, high: null };
  switch (story.kind) {
    case "known": {
      if (disclosure?.state === "suppressed") {
        return {
          ...base,
          value_state: disclosure.suppressionReason === "small_cohort"
            ? "suppressed_small_cohort"
            : "suppressed_privacy_policy",
          suppression_reason: disclosure.suppressionReason,
          ...noValue,
          missingness: {
            members_with_value: null,
            members_in_cohort: cohort.members,
            sessions_without_receipt: null,
          },
          freshness: unknownFreshness,
          uncertainty: notEstimated,
        };
      }
      const interval = wilsonInterval(story.numerator, story.denominator);
      return {
        ...base,
        value_state: "known",
        numerator: story.numerator,
        denominator: story.denominator,
        numeric_value: story.numerator / story.denominator,
        missingness: {
          members_with_value: story.membersWithValue,
          members_in_cohort: cohort.members,
          sessions_without_receipt: sessionsWithoutReceipt(cohort, story.membersWithValue),
        },
        freshness: {
          newest_receipt_at: story.newest,
          oldest_receipt_at: story.oldest,
          stale_member_count: story.staleMembers,
          stale_after_days: STALE_AFTER_DAYS,
        },
        uncertainty: interval === null
          ? notEstimated
          : { kind: "interval", method: "wilson_95", low: interval.low, high: interval.high },
      };
    }
    case "suppressed":
      return {
        ...base,
        value_state: "suppressed_small_cohort",
        suppression_reason: disclosure?.suppressionReason ?? "small_cohort",
        ...noValue,
        // Keep the public cohort size, but do not disclose the sub-k contributor
        // or missing-receipt counts that caused suppression.
        missingness: {
          members_with_value: null,
          members_in_cohort: cohort.members,
          sessions_without_receipt: null,
        },
        freshness: unknownFreshness,
        uncertainty: notEstimated,
      };
    case "withheld":
      return {
        ...base,
        value_state: "withheld_not_comparable",
        ...noValue,
        comparability: { state: "mixed_definition_versions", definition_versions: story.versions },
        missingness: {
          members_with_value: cohort.members,
          members_in_cohort: cohort.members,
          sessions_without_receipt: 0,
        },
        freshness: unknownFreshness,
        uncertainty: notEstimated,
      };
    case "abstained":
      return {
        ...base,
        value_state: "abstained",
        ...noValue,
        missingness: {
          members_with_value: story.membersWithValue < cohort.minimum ? null : story.membersWithValue,
          members_in_cohort: cohort.members,
          sessions_without_receipt: story.membersWithValue < cohort.minimum
            ? null
            : sessionsWithoutReceipt(cohort, story.membersWithValue),
        },
        freshness: unknownFreshness,
        uncertainty: notEstimated,
      };
    case "not_applicable":
      return {
        ...base,
        value_state: "not_applicable",
        ...noValue,
        missingness: {
          members_with_value: null,
          members_in_cohort: cohort.members,
          sessions_without_receipt: story.sessionsWithoutReceipt,
        },
        freshness: unknownFreshness,
        uncertainty: notEstimated,
      };
    case "unknown":
    default:
      return {
        ...base,
        value_state: "unknown",
        ...noValue,
        missingness: { members_with_value: null, members_in_cohort: cohort.members, sessions_without_receipt: null },
        freshness: unknownFreshness,
        uncertainty: notEstimated,
      };
  }
}

function experimentalAggregate(
  seed: MetricSeed,
  story: ExperimentalStory,
  cohort: FixtureCohort,
): TeamMetricAggregate {
  return {
    metric_key: seed.key,
    definition_version: seed.version,
    direction: seed.direction,
    value_state: "known",
    suppression_reason: null,
    numerator: null,
    denominator: null,
    numeric_value: story.median,
    provenance: "experimental_model",
    cohort: {
      member_count: cohort.members,
      session_count: cohort.sessions,
      minimum_member_count: cohort.minimum,
      minimum_contributor_count: cohort.minimum,
    },
    missingness: { members_with_value: cohort.members, members_in_cohort: cohort.members, sessions_without_receipt: 0 },
    comparability: { state: "comparable", definition_versions: [seed.version] },
    freshness: {
      newest_receipt_at: "2040-01-30T16:20:00Z",
      oldest_receipt_at: "2040-01-04T10:00:00Z",
      stale_member_count: 0,
      stale_after_days: STALE_AFTER_DAYS,
    },
    uncertainty: { kind: "interval", method: "model_range_90", low: story.low, high: story.high },
  };
}

function buildSnapshot(
  scope: "me" | "team",
  disclosurePolicy: StickyContributionDisclosurePolicy,
  request: TeamAggregateRequest,
): TeamAggregateSnapshot {
  const cohort = scope === "team"
    ? { members: SYNTHETIC_TEAM_MEMBER_IDS.length, sessions: 23, minimum: MINIMUM_TEAM_MEMBERS }
    : { members: 1, sessions: 9, minimum: 1 };
  const stories = scope === "team" ? TEAM_STORIES : ME_STORIES;
  const experimental = scope === "team" ? TEAM_EXPERIMENTAL : ME_EXPERIMENTAL;
  const metrics: TeamMetricAggregate[] = [];
  for (const seed of SYNTHETIC_TEAM_METRIC_SEEDS) {
    const story = stories[seed.key] ?? { kind: "unknown" as const };
    const contributorCount = story.kind === "known" || story.kind === "suppressed"
      ? story.membersWithValue
      : null;
    const contributorIds = contributorCount === null
      ? []
      : (scope === "me" ? SYNTHETIC_TEAM_MEMBER_IDS.slice(0, 1) : SYNTHETIC_TEAM_MEMBER_IDS)
        .slice(0, contributorCount);
    const disclosure = contributorCount === null
      ? null
      : disclosurePolicy.decide({
        family: `${seed.key}:v${seed.version}:${SYNTHETIC_TEAM_WINDOW_LABEL}`,
        queryId: scope,
        contributorIds,
        minimumContributorCount: cohort.minimum,
      });
    metrics.push(measuredAggregate(seed, story, cohort, disclosure));
    const range = experimental[seed.key];
    if (range !== undefined) metrics.push(experimentalAggregate(seed, range, cohort));
  }
  return {
    port_version: TEAM_CONTROL_PLANE_PORT_VERSION,
    origin: "synthetic_fixture",
    principal_id: request.principal_id,
    request,
    scope,
    cohort_label: scope === "team" ? SYNTHETIC_TEAM_COHORT_LABEL : SYNTHETIC_ME_COHORT_LABEL,
    window: { label: SYNTHETIC_TEAM_WINDOW_LABEL, started_at: WINDOW_START, ended_at: WINDOW_END },
    generated_at: FIXTURE_NOW,
    publication_policy: "aggregate_only_no_ranking_no_universal_score",
    calibration: "uncalibrated_exact_fractions",
    metrics,
  };
}

/** Deterministic, content-free per-member cells derived from the team story; never sorted by value. */
function memberCell(memberIndex: number, seed: MetricSeed, seedIndex: number): TeamMemberMetricCell {
  const story = TEAM_STORIES[seed.key] ?? { kind: "unknown" as const };
  const stamp = "2040-01-2" + String((memberIndex + seedIndex) % 9) + "T10:00:00Z";
  const cellBase = {
    metric_key: seed.key,
    definition_version: seed.version,
    provenance: "measured_typed" as const,
  };
  const empty = { numerator: null, denominator: null, numeric_value: null };
  switch (story.kind) {
    case "known": {
      if (memberIndex >= story.membersWithValue) {
        return { ...cellBase, value_state: "unknown", ...empty, newest_receipt_at: null };
      }
      const denominator = 3 + ((memberIndex * 5 + seedIndex * 3) % 7);
      const ratio = story.numerator / story.denominator;
      const drift = (memberIndex - 2) * 0.08;
      const numerator = Math.max(0, Math.min(denominator, Math.round((ratio + drift) * denominator)));
      return {
        ...cellBase,
        value_state: "known",
        numerator,
        denominator,
        numeric_value: numerator / denominator,
        newest_receipt_at: stamp,
      };
    }
    case "suppressed": {
      if (memberIndex === 0 || memberIndex === 3) {
        const denominator = 4 + memberIndex;
        const numerator = 1 + memberIndex;
        return { ...cellBase, value_state: "known", numerator, denominator, numeric_value: numerator / denominator, newest_receipt_at: stamp };
      }
      return { ...cellBase, value_state: "unknown", ...empty, newest_receipt_at: null };
    }
    case "abstained":
      return memberIndex < story.membersWithValue
        ? { ...cellBase, value_state: "known", numerator: 2, denominator: 3, numeric_value: 2 / 3, newest_receipt_at: stamp }
        : { ...cellBase, value_state: "abstained", ...empty, newest_receipt_at: null };
    case "not_applicable":
      return { ...cellBase, value_state: "not_applicable", ...empty, newest_receipt_at: null };
    case "withheld":
      // Mixed definitions per member still yield a per-member value; the aggregate withholds the cross-member ratio.
      return { ...cellBase, value_state: "known", numerator: 2 + memberIndex, denominator: 5 + memberIndex, numeric_value: (2 + memberIndex) / (5 + memberIndex), newest_receipt_at: stamp };
    case "unknown":
    default:
      return { ...cellBase, value_state: "unknown", ...empty, newest_receipt_at: null };
  }
}

function buildMembers(): TeamMemberRow[] {
  return SYNTHETIC_TEAM_MEMBER_IDS.map((memberId, memberIndex) => ({
    member_id: memberId,
    display_handle: `Member ${String(memberIndex + 1).padStart(2, "0")}`,
    consent: memberIndex === 4 ? "withheld" : "granted",
    metrics: SYNTHETIC_TEAM_METRIC_SEEDS.map((seed, seedIndex) => memberCell(memberIndex, seed, seedIndex)),
  }));
}

export interface SyntheticTeamControlPlaneOptions {
  /** Team scope access; "denied" demonstrates the permission-aware disabled state. */
  team?: "allowed" | "denied";
  /** Organization scope access; the fixture has no organization service. */
  organization?: "denied" | "unavailable";
  /** Individual member visibility grant. */
  memberVisibility?: "allowed" | "denied" | "unavailable";
  /** Reserved opaque test principal; never a real account identity. */
  principalId?: string;
  /** Injectable fixture clock for deterministic synthetic-only tests. */
  now?: () => string;
}

function scopeAccess(options: Required<SyntheticTeamControlPlaneOptions>): ScopeAccess[] {
  return [
    {
      principal_id: options.principalId,
      scope: "me",
      state: "allowed",
      reason: "granted",
      cohort_label: SYNTHETIC_ME_COHORT_LABEL,
      cohort_id: SYNTHETIC_ME_COHORT_ID,
      team_id: null,
      organization_id: null,
      aggregate_query_id: SYNTHETIC_ME_QUERY_ID,
    },
    options.team === "allowed"
      ? {
        principal_id: options.principalId,
        scope: "team",
        state: "allowed",
        reason: "granted",
        cohort_label: SYNTHETIC_TEAM_COHORT_LABEL,
        cohort_id: SYNTHETIC_COHORT_ID,
        team_id: SYNTHETIC_TEAM_ID,
        organization_id: SYNTHETIC_ORGANIZATION_ID,
        aggregate_query_id: SYNTHETIC_TEAM_QUERY_ID,
      }
      : {
        principal_id: options.principalId,
        scope: "team",
        state: "denied",
        reason: "role_insufficient",
        cohort_label: null,
        cohort_id: null,
        team_id: null,
        organization_id: null,
        aggregate_query_id: null,
      },
    options.organization === "denied"
      ? {
        principal_id: options.principalId,
        scope: "organization",
        state: "denied",
        reason: "role_insufficient",
        cohort_label: null,
        cohort_id: null,
        team_id: null,
        organization_id: null,
        aggregate_query_id: null,
      }
      : {
        principal_id: options.principalId,
        scope: "organization",
        state: "unavailable",
        reason: "organization_policy_disabled",
        cohort_label: null,
        cohort_id: null,
        team_id: null,
        organization_id: null,
        aggregate_query_id: null,
      },
  ];
}

function memberVisibilityGrant(
  state: Required<SyntheticTeamControlPlaneOptions>["memberVisibility"],
  principalId: string,
  composedAt: string,
): MemberVisibilityGrant {
  const composedAtMs = Date.parse(composedAt);
  if (!Number.isFinite(composedAtMs)) throw new Error("Synthetic fixture clock must return an ISO timestamp");
  if (state === "allowed") {
    return {
      principal_id: principalId,
      grant_id: SYNTHETIC_MEMBER_VISIBILITY_GRANT_ID,
      scope: "team",
      cohort_id: SYNTHETIC_COHORT_ID,
      team_id: SYNTHETIC_TEAM_ID,
      organization_id: SYNTHETIC_ORGANIZATION_ID,
      state: "allowed",
      reason: "granted_with_member_consent",
      audit: {
        granted_by_role: "team_admin (fixture role)",
        granted_at: new Date(composedAtMs - 60_000).toISOString(),
        expires_at: new Date(composedAtMs + 30 * 24 * 60 * 60 * 1_000).toISOString(),
        access_logged: true,
        log_destination: "local_audit_log",
      },
    };
  }
  if (state === "denied") {
    return {
      principal_id: principalId,
      grant_id: null,
      scope: null,
      cohort_id: null,
      team_id: null,
      organization_id: null,
      state: "denied",
      reason: "permission_not_granted",
      audit: { granted_by_role: null, granted_at: null, expires_at: null, access_logged: false, log_destination: null },
    };
  }
  return {
    principal_id: principalId,
    grant_id: null,
    scope: null,
    cohort_id: null,
    team_id: null,
    organization_id: null,
    state: "unavailable",
    reason: "unavailable_in_runtime",
    audit: { granted_by_role: null, granted_at: null, expires_at: null, access_logged: false, log_destination: null },
  };
}

function syntheticReadiness(checkedAt: string): readonly ReadinessCard[] {
  return [
    { id: "local", state: "ready", reason: "synthetic_fixture", checked_at: checkedAt, action: { kind: "none", enabled: false } },
    { id: "team_sync", state: "unavailable", reason: "no_team_sync_service_in_this_build", checked_at: checkedAt, action: { kind: "none", enabled: false } },
    { id: "deep_analysis", state: "unavailable", reason: "deep_analysis_not_in_synthetic_preview", checked_at: checkedAt, action: { kind: "open_methods_and_models", enabled: true } },
    { id: "billing", state: "unavailable", reason: "no_billing_service_in_this_build", checked_at: checkedAt, action: { kind: "none", enabled: false } },
  ];
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

export function createSyntheticTeamControlPlanePort(
  options: SyntheticTeamControlPlaneOptions = {},
): SyntheticTeamControlPlanePort {
  const team = options.team ?? "allowed";
  const resolved: Required<SyntheticTeamControlPlaneOptions> = {
    team,
    organization: options.organization ?? "denied",
    memberVisibility: team === "allowed" ? options.memberVisibility ?? "allowed" : "denied",
    principalId: options.principalId ?? SYNTHETIC_PRINCIPAL_ID,
    now: options.now ?? (() => new Date().toISOString()),
  };
  const composedAt = resolved.now();
  const scopes = scopeAccess(resolved);
  const grant = memberVisibilityGrant(resolved.memberVisibility, resolved.principalId, composedAt);
  const capabilities: TeamCapabilityReport = {
    port_version: TEAM_CONTROL_PLANE_PORT_VERSION,
    origin: "synthetic_fixture",
    principal_id: resolved.principalId,
    scopes,
    member_visibility: grant,
    readiness: syntheticReadiness(composedAt),
    checked_at: composedAt,
  };
  const disclosurePolicy = new StickyContributionDisclosurePolicy();
  const aggregateRequests: Record<"me" | "team", TeamAggregateRequest> = {
    me: {
      principal_id: resolved.principalId,
      scope: "me",
      cohort_id: SYNTHETIC_ME_COHORT_ID,
      team_id: null,
      organization_id: null,
      query_id: SYNTHETIC_ME_QUERY_ID,
    },
    team: {
      principal_id: resolved.principalId,
      scope: "team",
      cohort_id: SYNTHETIC_COHORT_ID,
      team_id: SYNTHETIC_TEAM_ID,
      organization_id: SYNTHETIC_ORGANIZATION_ID,
      query_id: SYNTHETIC_TEAM_QUERY_ID,
    },
  };
  const snapshots: Record<"me" | "team", TeamAggregateSnapshot> = {
    me: buildSnapshot("me", disclosurePolicy, aggregateRequests.me),
    team: buildSnapshot("team", disclosurePolicy, aggregateRequests.team),
  };
  const members = buildMembers();
  const revealAuditEvents: SyntheticMemberRevealAuditEvent[] = [];
  return {
    portVersion: TEAM_CONTROL_PLANE_PORT_VERSION,
    origin: "synthetic_fixture",
    principalId: resolved.principalId,
    async getCapabilities() {
      return clone(capabilities);
    },
    async getAggregate(request: TeamAggregateRequest) {
      const access = scopes.find((candidate) => candidate.scope === request.scope);
      if (access === undefined || access.state !== "allowed" || request.scope === "organization") {
        throw new TeamControlPlaneError("scope_not_allowed", `The ${request.scope} scope is not allowed for this fixture identity.`);
      }
      const expected = aggregateRequests[request.scope];
      if (!teamAggregateRequestsEqual(request, expected)) {
        throw new TeamControlPlaneError("scope_not_allowed", "The aggregate request does not match the exact immutable scope and cohort query.");
      }
      return clone(snapshots[request.scope]);
    },
    async getMemberVisibility(request: TeamMemberVisibilityRequest) {
      if (grant.state === "unavailable") {
        throw new TeamControlPlaneError("member_visibility_unavailable", "Member visibility is unavailable in this runtime.");
      }
      if (grant.state !== "allowed") {
        throw new TeamControlPlaneError("member_visibility_not_granted", "Member visibility has not been granted.");
      }
      const occurredAt = resolved.now();
      const occurredAtMs = Date.parse(occurredAt);
      const grantedAtMs = Date.parse(grant.audit.granted_at!);
      const expiresAtMs = Date.parse(grant.audit.expires_at!);
      if (!Number.isFinite(occurredAtMs) || occurredAtMs < grantedAtMs || occurredAtMs >= expiresAtMs) {
        throw new TeamControlPlaneError(
          "member_visibility_not_granted",
          "Member visibility grant is not active at the fixture server clock.",
        );
      }
      if (
        request.principal_id !== grant.principal_id
        || request.scope !== grant.scope
        || request.cohort_id !== grant.cohort_id
        || request.team_id !== grant.team_id
        || request.organization_id !== grant.organization_id
        || request.grant_id !== grant.grant_id
      ) {
        throw new TeamControlPlaneError(
          "member_visibility_not_granted",
          "Member visibility request does not match the exact active scope, cohort, and grant.",
        );
      }
      const page: TeamMemberVisibilityPage = {
        port_version: TEAM_CONTROL_PLANE_PORT_VERSION,
        origin: "synthetic_fixture",
        principal_id: request.principal_id,
        request,
        grant,
        ordering: "stable_member_id",
        members: members.filter((member) => member.consent === "granted"),
        withheld_member_count: members.filter((member) => member.consent === "withheld").length,
      };
      revealAuditEvents.push({
        event: "member_visibility_revealed",
        occurred_at: occurredAt,
        destination: "local_audit_log",
        grant_reason: "granted_with_member_consent",
        principal_id: request.principal_id,
        grant_id: request.grant_id,
        scope: request.scope,
        cohort_id: request.cohort_id,
        team_id: request.team_id,
        organization_id: request.organization_id,
        returned_member_count: page.members.length,
        withheld_member_count: page.withheld_member_count,
      });
      return clone(page);
    },
    getRevealAuditEvents() {
      return clone(revealAuditEvents);
    },
  };
}

/**
 * Honest adapter for runtimes without any team control plane. It never
 * fabricates a cohort: personal metrics stay in the local project workspace,
 * and team, organization, sync, and billing report themselves as absent.
 */
export function createUnavailableTeamControlPlanePort(
  now: () => string = () => new Date().toISOString(),
): TeamControlPlanePort {
  const capabilities = (): TeamCapabilityReport => ({
    port_version: TEAM_CONTROL_PLANE_PORT_VERSION,
    origin: "local_loopback",
    principal_id: LOCAL_RUNTIME_PRINCIPAL_ID,
    scopes: [
      { principal_id: LOCAL_RUNTIME_PRINCIPAL_ID, scope: "me", state: "allowed", reason: "personal_scope_served_locally", cohort_label: null, cohort_id: null, team_id: null, organization_id: null, aggregate_query_id: null },
      { principal_id: LOCAL_RUNTIME_PRINCIPAL_ID, scope: "team", state: "unavailable", reason: "local_runtime_has_no_team_service", cohort_label: null, cohort_id: null, team_id: null, organization_id: null, aggregate_query_id: null },
      { principal_id: LOCAL_RUNTIME_PRINCIPAL_ID, scope: "organization", state: "unavailable", reason: "local_runtime_has_no_team_service", cohort_label: null, cohort_id: null, team_id: null, organization_id: null, aggregate_query_id: null },
    ],
    member_visibility: {
      principal_id: LOCAL_RUNTIME_PRINCIPAL_ID,
      grant_id: null,
      scope: null,
      cohort_id: null,
      team_id: null,
      organization_id: null,
      state: "unavailable",
      reason: "unavailable_in_runtime",
      audit: { granted_by_role: null, granted_at: null, expires_at: null, access_logged: false, log_destination: null },
    },
    readiness: [
      { id: "local", state: "checking", reason: "loopback_service_checking", checked_at: null, action: { kind: "open_local_sources", enabled: true } },
      { id: "team_sync", state: "unavailable", reason: "no_team_sync_service_in_this_build", checked_at: now(), action: { kind: "none", enabled: false } },
      { id: "deep_analysis", state: "not_configured", reason: "deep_analysis_not_verified_by_this_view", checked_at: now(), action: { kind: "open_job_centre", enabled: true } },
      { id: "billing", state: "unavailable", reason: "no_billing_service_in_this_build", checked_at: now(), action: { kind: "none", enabled: false } },
    ],
    checked_at: now(),
  });
  return {
    portVersion: TEAM_CONTROL_PLANE_PORT_VERSION,
    origin: "local_loopback",
    principalId: LOCAL_RUNTIME_PRINCIPAL_ID,
    async getCapabilities() {
      return capabilities();
    },
    async getAggregate(request: TeamAggregateRequest) {
      throw new TeamControlPlaneError(
        "scope_not_served_by_this_runtime",
        `No team control plane serves the ${request.scope} scope in this runtime.`,
      );
    },
    async getMemberVisibility(_request: TeamMemberVisibilityRequest) {
      throw new TeamControlPlaneError("member_visibility_unavailable", "Member visibility is unavailable in this runtime.");
    },
  };
}

/** Value states that carry a plottable numeric fraction. */
export function teamMetricHasValue(state: TeamMetricValueState): boolean {
  return state === "known";
}
