import type {
  MetricEvidenceCapability,
  MetricReadiness,
  MetricReadinessAction,
  MetricReadinessReason,
  MetricReadinessState,
} from "../../shared/api/contracts";
import type { QualityMetricObservation, QualityMetricState } from "./qualityProfile";

const CAPABILITY_LABELS: Record<MetricEvidenceCapability, string> = {
  request_text: "user request text",
  response_text: "agent response text",
  plan_text: "structured plan text",
  action_evidence: "typed ACTION evidence",
  decision_evidence: "typed DECISION evidence",
  feedback_text: "explicit FEEDBACK text",
  objective_verification: "objective VERIFICATION evidence",
};

const STATE_LABELS: Record<MetricReadinessState, string> = {
  known: "Measured",
  unknown: "Unknown",
  unsupported: "Unsupported",
  abstained: "Abstained",
  incompatible: "Incompatible",
  not_applicable: "Not applicable",
  failed: "Failed",
};

const REASON_COPY: Record<MetricReadinessReason, string> = {
  measured: "The latest compatible run produced a persisted metric value.",
  analysis_not_run: "No compatible local analysis has been run for this session.",
  analysis_in_progress: "The latest local analysis is still in progress.",
  result_unknown:
    "The analysis completed, but it could not establish a safe denominator or evidence boundary for this metric.",
  result_abstained:
    "The analyzer deliberately declined to estimate this metric from the available evidence.",
  explicitly_not_applicable:
    "The completed analysis explicitly determined that this metric does not apply to the selected window.",
  provider_capability_missing:
    "The reviewed provider projection does not expose every evidence channel this metric requires.",
  provider_adapter_unavailable:
    "No reviewed provider adapter is available for this metric surface.",
  provider_compatibility_unverified:
    "The installed provider schema has not been checked against the reviewed adapter.",
  provider_incompatible:
    "The installed provider schema is incompatible with the reviewed adapter.",
  provider_unavailable:
    "The provider was unavailable when its cached compatibility status was established.",
  analysis_failed: "The latest local analysis run failed before results were completed.",
  result_failed: "This metric failed inside an otherwise persisted analysis run.",
  result_missing:
    "The completed run did not contain the required result record for this metric.",
};

const COMPACT_REASON_COPY: Record<MetricReadinessReason, string> = {
  measured: "A stored value is available.",
  analysis_not_run: "This metric has not been analyzed yet.",
  analysis_in_progress: "Local analysis is still in progress.",
  result_unknown: "A safe denominator or evidence boundary was unavailable.",
  result_abstained: "The analyzer declined to estimate this metric.",
  explicitly_not_applicable: "The metric was explicitly marked not applicable.",
  provider_capability_missing: "Required provider evidence is not exposed.",
  provider_adapter_unavailable: "No reviewed provider adapter is available.",
  provider_compatibility_unverified: "Provider compatibility has not been checked.",
  provider_incompatible: "The provider schema is incompatible.",
  provider_unavailable: "The provider was unavailable during its cached check.",
  analysis_failed: "The latest local analysis failed.",
  result_failed: "This metric failed during analysis.",
  result_missing: "The completed run omitted this metric result.",
};

const ACTION_COPY: Record<MetricReadinessAction, string> = {
  none: "No user action is requested for this state.",
  run_local_analysis: "Run local analysis for this session.",
  check_provider_compatibility:
    "Check the installed provider schema against the reviewed adapter.",
  update_provider_adapter: "Update Prompt Enhancer's reviewed provider adapter.",
  collect_action_evidence: "Import typed ACTION evidence from a supported provider event.",
  collect_decision_evidence:
    "Import typed DECISION evidence from a supported provider event.",
  collect_feedback_evidence: "Include explicit FEEDBACK evidence in a supported source.",
  collect_objective_verification:
    "Provide objective VERIFICATION evidence such as tests, artifacts, or explicit acceptance.",
  review_applicability:
    "Review whether the metric applies and whether its denominator exists in this window.",
  review_evidence_coverage: "Review which required evidence channels were observed.",
  retry_analysis: "Retry local analysis after checking the local service and provider adapter.",
};

const COMPACT_ACTION_COPY: Record<MetricReadinessAction, string> = {
  none: "No action needed.",
  run_local_analysis: "Run local analysis.",
  check_provider_compatibility: "Check provider compatibility.",
  update_provider_adapter: "Update the reviewed adapter.",
  collect_action_evidence: "Add ACTION evidence.",
  collect_decision_evidence: "Add DECISION evidence.",
  collect_feedback_evidence: "Add FEEDBACK evidence.",
  collect_objective_verification: "Add objective VERIFICATION.",
  review_applicability: "Review applicability.",
  review_evidence_coverage: "Review evidence coverage.",
  retry_analysis: "Retry local analysis.",
};

const EXPECTED_READINESS_STATES: Record<QualityMetricState, readonly MetricReadinessState[]> = {
  observed: ["known"],
  partial: ["known"],
  unavailable: ["unknown", "unsupported", "incompatible", "failed"],
  abstained: ["abstained"],
  "not-applicable": ["not_applicable"],
  "execution-error": ["failed"],
};

export interface MetricReadinessExplanation {
  readonly actionCopy: readonly string[];
  readonly compactActionCopy: string;
  readonly compactEvidenceCopy: string;
  readonly compactReasonCopy: string;
  readonly evidenceCopy: string;
  readonly label: string;
  readonly reasonCopy: string;
  readonly state: MetricReadinessState | "metadata_mismatch";
}

export function readinessIdentity(metric: {
  metric_key: string;
  metric_version: number;
}): string {
  return `${metric.metric_key}@${metric.metric_version}`;
}

export function indexMetricReadiness(
  metrics: readonly MetricReadiness[] | null | undefined,
): ReadonlyMap<string, MetricReadiness> {
  return new Map(
    (metrics ?? []).map((metric) => [readinessIdentity(metric), metric] as const),
  );
}

function capabilityList(capabilities: readonly MetricEvidenceCapability[]): string {
  return capabilities.map((capability) => CAPABILITY_LABELS[capability]).join(", ");
}

function capabilityRequirement(
  groups: readonly (readonly MetricEvidenceCapability[])[],
): string {
  return groups
    .map((group) => group.map((capability) => CAPABILITY_LABELS[capability]).join(" or "))
    .join("; plus ");
}

function evidenceCopy(readiness: MetricReadiness): string {
  if (readiness.missing_capabilities.length > 0) {
    return `Missing evidence channels: ${capabilityList(readiness.missing_capabilities)}.`;
  }
  if (readiness.state === "incompatible") {
    return "Evidence requirements cannot be checked until provider compatibility is resolved.";
  }
  if (readiness.state === "failed") {
    return "The stored evidence and prior metric state remain unchanged; no value was inferred from the failure.";
  }
  if (readiness.state === "not_applicable") {
    return "No additional evidence is requested for a metric explicitly marked not applicable.";
  }
  if (readiness.state === "known") {
    return "The persisted value remains the authoritative observation.";
  }
  return `Evidence requirement: ${capabilityRequirement(readiness.capability_groups)}.`;
}

function compactEvidenceCopy(readiness: MetricReadiness): string {
  if (readiness.missing_capabilities.length > 0) {
    return `Missing: ${capabilityList(readiness.missing_capabilities)}.`;
  }
  if (readiness.state === "incompatible") return "Resolve provider compatibility first.";
  if (readiness.state === "failed") return "No value was inferred from the failure.";
  if (readiness.state === "not_applicable") return "No further evidence is needed.";
  if (readiness.state === "known") return "Stored value is authoritative.";
  return `Needs: ${capabilityRequirement(readiness.capability_groups)}.`;
}

export function explainMetricReadiness(
  observation: QualityMetricObservation,
  readiness: MetricReadiness | null | undefined,
): MetricReadinessExplanation | null {
  if (readiness === null || readiness === undefined) return null;
  if (
    readiness.metric_key !== observation.definition.key ||
    readiness.metric_version !== observation.definition.version
  ) {
    return null;
  }

  if (!EXPECTED_READINESS_STATES[observation.state].includes(readiness.state)) {
    return {
      actionCopy: [
        "Refresh readiness metadata or rerun the compatible local analysis before acting on it.",
      ],
      compactActionCopy: "Refresh readiness metadata.",
      compactEvidenceCopy: "Stored value state is authoritative.",
      compactReasonCopy: "Stored value and readiness metadata disagree.",
      evidenceCopy:
        "The persisted metric state and value remain authoritative; readiness metadata cannot create, erase, or replace them.",
      label: "Readiness metadata mismatch",
      reasonCopy:
        "The explanatory readiness state does not match the stored metric result state.",
      state: "metadata_mismatch",
    };
  }

  return {
    actionCopy: readiness.next_actions.map((action) => ACTION_COPY[action]),
    compactActionCopy: COMPACT_ACTION_COPY[readiness.next_actions[0]],
    compactEvidenceCopy: compactEvidenceCopy(readiness),
    compactReasonCopy: COMPACT_REASON_COPY[readiness.reason_code],
    evidenceCopy: evidenceCopy(readiness),
    label: STATE_LABELS[readiness.state],
    reasonCopy: REASON_COPY[readiness.reason_code],
    state: readiness.state,
  };
}
