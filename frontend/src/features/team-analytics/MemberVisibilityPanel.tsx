import { useEffect, useMemo, useState } from "react";
import {
  TEAM_REVIEWED_METRIC_CONTRACTS,
  isTeamControlPlaneError,
  teamMemberVisibilityGrantIsValid,
  teamControlPlaneResponseMatchesPort,
  type AnalyticsScope,
  type MemberVisibilityGrant,
  type ScopeAccess,
  type TeamControlPlanePort,
  type TeamMemberVisibilityRequest,
  type TeamMemberVisibilityPage,
} from "../../shared/api/teamControlPlane";
import { Icon } from "../../shared/ui/Icon";
import {
  MetricExplainerCardSlot,
  MetricExplainerDescriptions,
  metricExplainerTriggerProps,
  type MetricExplainerEntry,
} from "../model-ensemble/MetricExplainer";
import { useMetricKnowledgeCardController } from "../model-ensemble/MetricKnowledgeCard";
import { MODEL_ENSEMBLE_LENSES, moveRovingFocus, type ModelEnsembleLensId } from "../model-ensemble/ModelEnsembleRadar";
import { QUALITY_ANALYSIS_DEFINITIONS } from "../quality-profile/qualityProfile";
import { memberCellLabel, teamReviewedMetricContractsMatchLenses } from "./teamAggregatePresentation";
import { MEMBER_VISIBILITY_REASON_COPY, memberVisibilityAuditCopy, shortUtcDate } from "./teamAnalyticsCopy";

const DEFINITIONS = new Map(QUALITY_ANALYSIS_DEFINITIONS.map((definition) => [definition.key, definition]));
const REVIEWED_MEMBER_METRICS = new Map(TEAM_REVIEWED_METRIC_CONTRACTS.map((contract) => [contract.metric_key, contract]));
const PSEUDONYM = /^[0-9a-f]{64}$/;
const optionalPseudonym = (value: string | null): boolean => value === null || PSEUDONYM.test(value);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 0;
}

function parseableInstant(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function requestsEqual(left: unknown, right: TeamMemberVisibilityRequest): left is TeamMemberVisibilityRequest {
  return isRecord(left)
    && left.principal_id === right.principal_id
    && left.scope === right.scope
    && left.cohort_id === right.cohort_id
    && left.team_id === right.team_id
    && left.organization_id === right.organization_id
    && left.grant_id === right.grant_id;
}

function requestForActiveScope(
  scope: AnalyticsScope,
  access: ScopeAccess | null,
  grant: MemberVisibilityGrant,
): TeamMemberVisibilityRequest | null {
  if (
    scope === "me"
    || access === null
    || access.scope !== scope
    || access.state !== "allowed"
    || access.cohort_id === null
    || grant.grant_id === null
    || access.principal_id !== grant.principal_id
  ) return null;
  const request: TeamMemberVisibilityRequest = {
    principal_id: access.principal_id,
    scope,
    cohort_id: access.cohort_id,
    team_id: access.team_id,
    organization_id: access.organization_id,
    grant_id: grant.grant_id,
  };
  if (!PSEUDONYM.test(request.principal_id) || !PSEUDONYM.test(request.cohort_id) || !optionalPseudonym(request.team_id) || !optionalPseudonym(request.organization_id)) {
    return null;
  }
  return request.scope === "team"
    ? request.team_id !== null && PSEUDONYM.test(request.team_id) ? request : null
    : request.organization_id !== null && PSEUDONYM.test(request.organization_id) ? request : null;
}

export function memberVisibilityGrantIsUsable(
  grant: MemberVisibilityGrant,
  request: TeamMemberVisibilityRequest | null,
  expectedPrincipalId: string,
  now = Date.now(),
): boolean {
  const expiry = grant.audit.expires_at === null ? Number.NaN : Date.parse(grant.audit.expires_at);
  const grantedAt = grant.audit.granted_at === null ? Number.NaN : Date.parse(grant.audit.granted_at);
  return request !== null
    && PSEUDONYM.test(expectedPrincipalId)
    && request.principal_id === expectedPrincipalId
    && teamMemberVisibilityGrantIsValid(grant)
    && grant.state === "allowed"
    && grant.reason === "granted_with_member_consent"
    && grant.grant_id !== null
    && PSEUDONYM.test(grant.grant_id)
    && grant.grant_id === request.grant_id
    && grant.principal_id === request.principal_id
    && PSEUDONYM.test(request.principal_id)
    && PSEUDONYM.test(request.grant_id)
    && grant.scope === request.scope
    && grant.cohort_id === request.cohort_id
    && PSEUDONYM.test(request.cohort_id)
    && grant.team_id === request.team_id
    && grant.organization_id === request.organization_id
    && typeof grant.audit.granted_by_role === "string"
    && grant.audit.granted_by_role.trim() !== ""
    && Number.isFinite(grantedAt)
    && grant.audit.access_logged === true
    && (grant.audit.log_destination === "local_audit_log" || grant.audit.log_destination === "team_control_plane")
    && Number.isFinite(expiry)
    && grantedAt < expiry
    && grantedAt <= now
    && expiry > now;
}

function grantsEqual(left: unknown, right: MemberVisibilityGrant): left is MemberVisibilityGrant {
  return isRecord(left)
    && isRecord(left.audit)
    && left.principal_id === right.principal_id
    && left.grant_id === right.grant_id
    && left.scope === right.scope
    && left.cohort_id === right.cohort_id
    && left.team_id === right.team_id
    && left.organization_id === right.organization_id
    && left.state === right.state
    && left.reason === right.reason
    && left.audit.granted_by_role === right.audit.granted_by_role
    && left.audit.granted_at === right.audit.granted_at
    && left.audit.expires_at === right.audit.expires_at
    && left.audit.access_logged === right.audit.access_logged
    && left.audit.log_destination === right.audit.log_destination;
}

function snapshotGrant(grant: MemberVisibilityGrant): MemberVisibilityGrant {
  return { ...grant, audit: { ...grant.audit } };
}

function snapshotRequest(request: TeamMemberVisibilityRequest): TeamMemberVisibilityRequest {
  return { ...request };
}

export function memberVisibilityGrantIdentity(grant: MemberVisibilityGrant): string {
  // JSON string escaping makes this canonical field tuple injective even when
  // arbitrary string fields themselves contain delimiters such as "|".
  return JSON.stringify({
    principal_id: grant.principal_id,
    grant_id: grant.grant_id,
    scope: grant.scope,
    cohort_id: grant.cohort_id,
    team_id: grant.team_id,
    organization_id: grant.organization_id,
    state: grant.state,
    reason: grant.reason,
    audit: {
      granted_by_role: grant.audit.granted_by_role,
      granted_at: grant.audit.granted_at,
      expires_at: grant.audit.expires_at,
      access_logged: grant.audit.access_logged,
      log_destination: grant.audit.log_destination,
    },
  });
}

function memberMetricIsValid(value: unknown): boolean {
  if (!isRecord(value) || typeof value.metric_key !== "string") return false;
  const contract = REVIEWED_MEMBER_METRICS.get(value.metric_key);
  if (
    contract === undefined
    || value.definition_version !== contract.definition_version
    || value.provenance !== "measured_typed"
    || (value.value_state !== "known"
      && value.value_state !== "unknown"
      && value.value_state !== "not_applicable"
      && value.value_state !== "abstained")
    || (value.newest_receipt_at !== null && !parseableInstant(value.newest_receipt_at))
  ) return false;
  if (value.value_state === "known") {
    return nonNegativeInteger(value.numerator)
      && nonNegativeInteger(value.denominator)
      && value.denominator > 0
      && value.numerator <= value.denominator
      && typeof value.numeric_value === "number"
      && Number.isFinite(value.numeric_value)
      && value.numeric_value >= 0
      && value.numeric_value <= 1
      && Math.abs(value.numeric_value - value.numerator / value.denominator) <= 1e-9;
  }
  return value.numerator === null
    && value.denominator === null
    && value.numeric_value === null
    && value.newest_receipt_at === null;
}

function memberRowsAreValid(members: unknown): boolean {
  if (!Array.isArray(members)) return false;
  const ids = new Set<string>();
  const handles = new Set<string>();
  let previousId: string | null = null;
  for (const member of members) {
    if (
      !isRecord(member)
      ||
      typeof member.member_id !== "string"
      || !PSEUDONYM.test(member.member_id)
      || ids.has(member.member_id)
      || typeof member.display_handle !== "string"
      || member.display_handle.trim() === ""
      || handles.has(member.display_handle)
      || member.consent !== "granted"
      || (previousId !== null && previousId >= member.member_id)
      || !Array.isArray(member.metrics)
      || member.metrics.length !== TEAM_REVIEWED_METRIC_CONTRACTS.length
      || !member.metrics.every(memberMetricIsValid)
    ) return false;
    const metricKeys = member.metrics.map((metric) => (metric as Record<string, unknown>).metric_key);
    if (new Set(metricKeys).size !== TEAM_REVIEWED_METRIC_CONTRACTS.length
      || !TEAM_REVIEWED_METRIC_CONTRACTS.every((contract) => metricKeys.includes(contract.metric_key))) return false;
    ids.add(member.member_id);
    handles.add(member.display_handle);
    previousId = member.member_id;
  }
  return true;
}

/** Full fail-closed runtime validator for the member page. It validates the
 * exact request/grant plus every row and metric before React can retain or
 * render the payload. */
export function memberVisibilityPageIsValid(
  page: unknown,
  requestedGrant: MemberVisibilityGrant,
  requested: TeamMemberVisibilityRequest,
  port: TeamControlPlanePort,
): page is TeamMemberVisibilityPage {
  return isRecord(page)
    && teamControlPlaneResponseMatchesPort(page, port)
    && requestsEqual(page.request, requested)
    && grantsEqual(page.grant, requestedGrant)
    && memberVisibilityGrantIsUsable(page.grant, requested, port.principalId)
    && page.ordering === "stable_member_id"
    && nonNegativeInteger(page.withheld_member_count)
    && memberRowsAreValid(page.members)
    && page.grant.audit.log_destination === (port.origin === "team_control_plane" ? "team_control_plane" : "local_audit_log");
}

/**
 * Individual member visibility. The panel is closed by default and opens only
 * through an explicit action that the copy describes as audited. Without an
 * allowing grant the action stays disabled and the reason is visible. Rows are
 * ordered by pseudonymous member identifier, cells never sum to a member score,
 * and members who withheld consent are counted but never listed.
 */
export function MemberVisibilityPanel({
  grant,
  port,
  lensId,
  scope,
  scopeAccess,
}: {
  grant: MemberVisibilityGrant;
  port: TeamControlPlanePort;
  lensId: ModelEnsembleLensId;
  scope: Exclude<AnalyticsScope, "me">;
  scopeAccess: ScopeAccess | null;
}) {
  const [revealBinding, setRevealBinding] = useState<{
    port: TeamControlPlanePort;
    grant: MemberVisibilityGrant;
    request: TeamMemberVisibilityRequest;
  } | null>(null);
  const [pageBinding, setPageBinding] = useState<{
    port: TeamControlPlanePort;
    grant: MemberVisibilityGrant;
    request: TeamMemberVisibilityRequest;
    page: TeamMemberVisibilityPage;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clockNow, setClockNow] = useState(() => Date.now());
  const explainer = useMetricKnowledgeCardController();
  const grantIdentity = memberVisibilityGrantIdentity(grant);
  const request = scopeAccess?.principal_id === port.principalId
    ? requestForActiveScope(scope, scopeAccess, grant)
    : null;
  const requestIdentity = JSON.stringify(request);
  const allowed = memberVisibilityGrantIsUsable(grant, request, port.principalId, clockNow);
  const revealed = allowed
    && request !== null
    && revealBinding?.port === port
    && grantsEqual(revealBinding.grant, grant)
    && requestsEqual(revealBinding.request, request);
  const page = revealed
    && request !== null
    && pageBinding?.port === port
    && grantsEqual(pageBinding.grant, grant)
    && requestsEqual(pageBinding.request, request)
    ? pageBinding.page
    : null;
  const lens = MODEL_ENSEMBLE_LENSES.find((candidate) => candidate.id === lensId);
  const columns = useMemo(() => (teamReviewedMetricContractsMatchLenses() ? lens?.metrics ?? [] : []).map(({ key }) => {
    const definition = DEFINITIONS.get(key);
    return {
      key,
      label: definition?.label ?? key,
      shortLabel: definition?.shortLabel ?? key,
      direction: definition?.direction ?? "higher_is_better",
    };
  }), [lens]);
  const entries: MetricExplainerEntry[] = columns.map((column) => ({
    key: column.key,
    label: column.label,
    provenance: "measured",
    numericValue: null,
    valueLabel: "Per-member cells",
  }));

  useEffect(() => {
    setClockNow(Date.now());
    setRevealBinding(null);
    setPageBinding(null);
    setLoading(false);
    setError(null);
  }, [grantIdentity, port, requestIdentity]);

  useEffect(() => {
    const expiry = grant.audit.expires_at === null ? Number.NaN : Date.parse(grant.audit.expires_at);
    if (!Number.isFinite(expiry)) return undefined;
    if (clockNow >= expiry) return undefined;
    const checkExpiry = () => {
      const nextNow = Date.now();
      setClockNow(nextNow);
      if (nextNow >= expiry) {
        setRevealBinding(null);
        setPageBinding(null);
        setLoading(false);
        setError(null);
      }
    };
    const delay = Math.max(0, Math.min(expiry - Date.now(), 2_147_000_000));
    const timer = window.setTimeout(checkExpiry, delay);
    return () => window.clearTimeout(timer);
  }, [grant.audit.expires_at, grantIdentity, port, clockNow]);

  useEffect(() => {
    if (!revealed || !allowed || request === null) return undefined;
    const controller = new AbortController();
    setPageBinding(null);
    setLoading(true);
    setError(null);
    port.getMemberVisibility(request, controller.signal)
      .then((next) => {
        if (controller.signal.aborted) return;
        if (!memberVisibilityPageIsValid(next, grant, request, port)) {
          setPageBinding(null);
          setError("Member rows were withheld because the returned page did not match the exact active, audited consent grant.");
          return;
        }
        setPageBinding({
          port,
          grant: snapshotGrant(grant),
          request: snapshotRequest(request),
          page: structuredClone(next),
        });
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setPageBinding(null);
        setError(isTeamControlPlaneError(reason)
          ? MEMBER_VISIBILITY_REASON_COPY[reason.code === "member_visibility_unavailable" ? "unavailable_in_runtime" : "permission_not_granted"]
          : "Member visibility could not be loaded. Aggregates remain available.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [allowed, grantIdentity, port, requestIdentity, revealed]);

  function toggleReveal() {
    if (!allowed) return;
    setPageBinding(null);
    setError(null);
    if (request === null) return;
    setRevealBinding(revealed ? null : {
      port,
      grant: snapshotGrant(grant),
      request: snapshotRequest(request),
    });
  }

  return (
    <section aria-labelledby="member-visibility-title" className="member-visibility" data-grant={grant.state}>
      <header className="member-visibility__header">
        <div>
          <p className="eyebrow">Individual members</p>
          <h3 id="member-visibility-title">Member visibility</h3>
          <p className="member-visibility__audit">
            {request === null && grant.state === "allowed"
              ? "The available member grant is bound to a different scope or cohort; it does not authorize this context."
              : memberVisibilityAuditCopy(grant)}
          </p>
        </div>
        <button
          aria-describedby="member-visibility-readiness"
          aria-expanded={allowed ? revealed : undefined}
          className={`button ${revealed ? "button--secondary" : "button--primary"}`}
          disabled={!allowed}
          onClick={toggleReveal}
          type="button"
        >
          <Icon name={revealed ? "x" : "users"} />
          {revealed ? "Hide individual members" : "Reveal individual members"}
        </button>
      </header>
      <p className="member-visibility__readiness" id="member-visibility-readiness">
        {allowed
          ? `Ready to reveal · the reveal is written to the ${grant.audit.log_destination?.replaceAll("_", " ")} · grant valid until ${shortUtcDate(grant.audit.expires_at!)} · rows are ordered by pseudonymous member id and never ranked`
          : `Not ready · ${grant.state === "denied" ? "no grant permits individual visibility" : grant.state === "unavailable" ? "no team control plane exists in this runtime" : "the grant lacks the exact active scope/cohort binding, consent, audit logging, grant id, or an unexpired expiry"} · aggregates stay available`}
      </p>
      {revealed && allowed && (
        <div aria-live="polite" className="member-visibility__body">
          {loading && <p className="member-visibility__status" role="status">Loading consented member rows…</p>}
          {error !== null && <p className="member-visibility__status" role="alert">{error}</p>}
          {page !== null && (
            <>
              <MetricExplainerDescriptions controller={explainer} entries={entries} surface="team-members" />
              <div className="member-visibility__scroll">
                <table className="member-visibility__table">
                  <caption>
                    <span>{lens?.label ?? "Metrics"} · {page.members.length} consented member{page.members.length === 1 ? "" : "s"} · {page.withheld_member_count} withheld consent and {page.withheld_member_count === 1 ? "is" : "are"} not listed · ordering: {page.ordering.replaceAll("_", " ")}</span>
                  </caption>
                  <thead>
                    <tr onKeyDown={(event) => moveRovingFocus(event)}>
                      <th scope="col">Member</th>
                      {columns.map((column) => (
                        <th key={column.key} scope="col">
                          <button
                            {...metricExplainerTriggerProps(explainer, "team-members", column.key)}
                            onClick={() => explainer.togglePin({ surface: "team-members", metricKey: column.key })}
                            type="button"
                          >
                            {column.shortLabel}
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {page.members.map((member) => (
                      <tr key={member.member_id}>
                        <th scope="row">
                          <strong>{member.display_handle}</strong>
                          <small className="mono">{member.member_id.slice(0, 8)}…</small>
                        </th>
                        {columns.map((column) => {
                          const cell = member.metrics.find((candidate) => candidate.metric_key === column.key) ?? null;
                          return (
                            <td data-state={cell?.value_state ?? "missing"} key={column.key}>
                              {memberCellLabel(cell, column.direction)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="member-visibility__footnote">
                Cells are exact per-member fractions for the selected lens. No row total, average, or rank is computed; a member score does not exist in this product.
              </p>
              <MetricExplainerCardSlot controller={explainer} entries={entries} surface="team-members" />
            </>
          )}
        </div>
      )}
    </section>
  );
}
