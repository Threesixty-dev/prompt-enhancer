import { useEffect, useRef, useState, type ReactNode } from "react";
import { formatPercent } from "../../shared/lib/format";
import type {
  ProviderCompatibilityStatus,
  SessionMetricReadinessReport,
  SessionQualityAnalysisPreview,
  SessionQualityAnalysisPreviewApprovalRequest,
  SessionQualityAnalysisPreviewRequest,
  SessionTextAnalysisCapability,
} from "../../shared/api/contracts";
import {
  promptTextCompatibilityBlocker,
  ProviderCompatibilityCard,
} from "../provider-compatibility";
import { AnalyzeLocallyDialog } from "./AnalyzeLocallyDialog";
import { MetricOpportunityMap } from "./MetricOpportunityMap";
import { ProfileShareDialog } from "./ProfileShareDialog";
import { QualityRadar } from "./QualityRadar";
import "./QualityProfileView.css";
import type {
  QualityMetricObservation,
  QualityMetricProfile,
  QualityMetricState,
  QualitySnapshotKind,
} from "./qualityProfile";

const STATE_LABELS: Record<QualityMetricState, string> = {
  observed: "Rule candidate",
  partial: "Partial rule candidate",
  unavailable: "Unknown",
  abstained: "Not measurable",
  "not-applicable": "Not applicable",
  "execution-error": "Execution error",
};

const SIGNAL_LABELS: Record<string, string> = {
  "goal.action": "Requested action cue",
  "goal.target": "Possible target after the action",
  "goal.outcome": "Purpose or intended-outcome connector",
  "constraint.expected_categories": "Applicable constraint categories",
  "completion.requirements": "Detected requirement clauses",
  "completion.checkable": "Clauses with an observable-check cue",
  "deliverable.expected_slots": "Applicable output-detail slots",
  "choices.prompt_clauses": "Analyzed user clauses",
  "choices.marker_clauses": "Clauses with unresolved-choice markers",
  "task.action": "Requested-action cue",
  "task.target": "Possible action target",
  "task.context": "Operating-context cue",
  "task.outcome": "Outcome or check cue",
  "problem.observed": "Observed-behavior cue",
  "problem.expected": "Expected-behavior cue",
  "problem.reproduction": "Reproduction-step cue",
  "problem.environment": "Environment cue",
  "context.artifact": "Artifact or component cue",
  "context.current_state": "Current-state cue",
  "context.environment": "Environment or version cue",
  "context.boundary": "Scope or boundary cue",
  "constraints.detected": "Detected constraint clauses",
  "constraints.precise": "Constraints with a concrete detail",
  "acceptance.requirements": "Detected requirement clauses",
  "acceptance.checkable": "Requirements with a check cue",
  "deliverables.detected": "Detected deliverable clauses",
  "deliverables.detailed": "Deliverables with an output-detail cue",
  "ambiguity.candidates": "Detected ambiguity candidates",
  "ambiguity.resolved": "Candidates followed by clarification",
  "clarification.questions": "Detected agent questions",
  "clarification.productive": "Questions followed by a substantive answer",
  "exploration.hypotheses": "Detected exploration or hypothesis clauses",
  "exploration.converted": "Clauses followed by plan or evidence",
  "scope.changes": "Detected scope changes",
  "scope.acknowledged": "Scope changes followed by acknowledgement",
  "rework.feedback_turns": "User feedback turns",
  "rework.candidates": "Correction-marker candidates",
};

function signalLabel(code: string): string {
  return SIGNAL_LABELS[code] ?? code.replaceAll(".", " ");
}

function signalValue(
  status: "detected" | "missing" | "counted" | "unknown",
  count: number | null,
): string {
  if (status === "detected") return "Detected";
  if (status === "missing") return "Missing";
  if (status === "unknown") return "Unknown";
  return `${count ?? 0}`;
}

function explanationLine(metric: QualityMetricObservation): string | null {
  if (
    metric.definition.key === "collaboration.exploration_conversion" &&
    metric.ratio === 0 &&
    metric.fractionDenominator !== null
  ) {
    return `The rule found ${metric.fractionDenominator} hypothesis-marker clause${metric.fractionDenominator === 1 ? "" : "s"}, but no later related structured plan, decision, action, or verification item. This is an uncalibrated lexical-link result—not zero exploration ability.`;
  }
  if (metric.explanationCode === "denominator_unknown") {
    return "Not measured: Standard engineering v1 cannot safely assume which task-specific factors apply. This is not a zero or a negative judgment.";
  }
  if (metric.explanationCode === "source_extraction_incomplete") {
    return "The provider projection was incomplete, so the extractor abstained instead of scoring partial evidence.";
  }
  if (metric.explanationCode === "unsupported_language") {
    return "The selected window did not contain enough supported English or Polish text for this rule set.";
  }
  if (metric.explanationCode === "message_kind_unavailable") {
    return "The provider cannot expose the message kind required by this metric.";
  }
  if (metric.explanationCode === "message_kind_unobserved") {
    return "The required message kind was supported but not observed in this window.";
  }
  if (metric.explanationCode === "diagnostic_task_not_detected") {
    return "No bug or diagnosis-task cue was detected, so problem-evidence quality stays Unknown instead of becoming zero.";
  }
  if (
    metric.explanationCode?.endsWith("_unobserved") ||
    metric.explanationCode?.endsWith("_unknown")
  ) {
    return "The metric-specific denominator was not observed in this window. The result stays Unknown, not zero.";
  }
  if (metric.explanationCode === "conversion_evidence_unavailable") {
    return "The provider does not expose a structured plan, decision, action, or verification item needed to assess conversion.";
  }
  if (
    metric.explanationCode === "objective_evidence_stream_required" ||
    metric.explanationCode === "objective_verification_stream_required" ||
    metric.explanationCode === "objective_verification_episode_required"
  ) {
    return "This metric requires structured objective evidence. Agent prose and completion claims are deliberately ignored, so the result abstains.";
  }
  return null;
}

function denominatorSource(metric: QualityMetricObservation): string {
  if (metric.definition.key === "prompt.goal_definition") {
    return "Fixed Standard engineering v1 slots: action, target, outcome.";
  }
  if (metric.definition.key === "prompt.completion_evaluability") {
    return "Requirement clauses conservatively detected by deterministic rules.";
  }
  if (metric.definition.key === "prompt.open_decision_load") {
    return "All analyzed user clauses in the bounded window.";
  }
  if (metric.definition.key === "prompt.task_definition_coverage") {
    return "Three focus-request factors: action, target, and intended outcome.";
  }
  if (metric.definition.key === "prompt.problem_evidence_quality") {
    return "Only diagnosis candidates: observed behavior, expected behavior, reproduction, and environment.";
  }
  if (metric.definition.key === "prompt.context_sufficiency") {
    return "Three focus-request factors: current state, environment or version, and boundary.";
  }
  if (metric.explanationCode === "denominator_unknown") {
    return "Unknown—the standard preset deliberately does not invent one.";
  }
  return "Versioned task profile or metric-specific observed candidates.";
}

function summary(metrics: readonly QualityMetricObservation[]): string {
  const observed = metrics.filter((metric) => metric.state === "observed").length;
  const partial = metrics.filter((metric) => metric.state === "partial").length;
  const unavailable = metrics.filter((metric) => metric.state === "unavailable").length;
  const abstained = metrics.filter((metric) => metric.state === "abstained").length;
  const failed = metrics.filter((metric) => metric.state === "execution-error").length;
  const notApplicable = metrics.filter((metric) => metric.state === "not-applicable").length;
  return [
    `${observed} assessable`,
    partial > 0 ? `${partial} partial` : null,
    unavailable > 0 ? `${unavailable} unavailable` : null,
    abstained > 0 ? `${abstained} not measurable` : null,
    failed > 0 ? `${failed} failed` : null,
    notApplicable > 0 ? `${notApplicable} not applicable` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function coverageLine(metric: QualityMetricObservation): string {
  if (metric.eligible === 0) return "No eligible observations were available for this snapshot.";
  return `${metric.observed} of ${metric.eligible} eligible observations were usable (${formatPercent(metric.coverage)} coverage).`;
}

function fractionLine(metric: QualityMetricObservation): string {
  if (
    metric.fractionNumerator === null ||
    metric.fractionDenominator === null
  ) {
    return "No metric fraction was produced for this state.";
  }
  return `${metric.fractionNumerator} of ${metric.fractionDenominator} metric-specific items satisfied the candidate definition.`;
}

export interface AnalyzeLocallyHandler {
  exactSessionId: string;
  preparePreview: (
    sessionId: string,
    request: SessionQualityAnalysisPreviewRequest,
    signal: AbortSignal,
  ) => Promise<SessionQualityAnalysisPreview>;
  approvePreview: (
    sessionId: string,
    previewId: string,
    request: SessionQualityAnalysisPreviewApprovalRequest,
    idempotencyKey: string,
    signal: AbortSignal,
  ) => Promise<void>;
}

function analysisCapabilityCopy(
  capability: SessionTextAnalysisCapability,
): string | null {
  if (capability.available) return null;
  if (capability.reason_code === "local_source_unavailable") {
    return "Analyze is unavailable because the Codex local-source adapter is not active.";
  }
  if (capability.reason_code === "analysis_service_unavailable") {
    return "This running app does not expose bounded text analysis. Restart after updating the local backend.";
  }
  if (capability.reason_code === "redacted_content_consent_required") {
    return "Redacted-text consent is not active. Open Local sources and grant access before analyzing.";
  }
  if (capability.reason_code === "consent_status_invalid") {
    return "Consent status could not be verified, so local analysis stays disabled.";
  }
  if (capability.reason_code === "synthetic_preview") {
    return "New local analyses are disabled in the fictional preview.";
  }
  return "Capability status could not be verified, so local analysis stays disabled.";
}

export function QualityProfileView({
  profile,
  onAnalyzeLocally,
  analysisCapability,
  onRetryMetricReadiness,
  providerCompatibility,
  compatibilityLoading = false,
  onCheckProviderCompatibility,
  onUpdateProvider,
  primaryContent,
  metricReadiness,
  metricReadinessError = "",
  metricReadinessLoading = false,
  sessionDescriptor,
}: {
  profile: QualityMetricProfile;
  onAnalyzeLocally?: AnalyzeLocallyHandler;
  /** Null or omitted means capability has not been verified yet. */
  analysisCapability?: SessionTextAnalysisCapability | null;
  providerCompatibility?: ProviderCompatibilityStatus | null;
  compatibilityLoading?: boolean;
  onCheckProviderCompatibility?: (signal: AbortSignal) => Promise<void>;
  onRetryMetricReadiness?: () => void;
  onUpdateProvider?: () => void;
  /** Cached, content-free explanation metadata. It never supplies metric values. */
  metricReadiness?: SessionMetricReadinessReport | null;
  metricReadinessError?: string;
  metricReadinessLoading?: boolean;
  /** Optional compact coaching deck rendered below the collapsible radar. */
  primaryContent?: ReactNode;
  /** Content-free identity shown before a real provider read begins. */
  sessionDescriptor?: string;
}) {
  const [snapshotKind, setSnapshotKind] = useState<QualitySnapshotKind>("latest");
  const [shareOpen, setShareOpen] = useState(false);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const snapshot = snapshotKind === "initial" ? profile.initial : profile.latest;
  const initialAvailable = profile.initial.integrity !== "unavailable";
  // Every current qualitative pack is explicitly uncalibrated. Export stays
  // disabled until a future human-calibrated profile has its own closed DTO.
  const shareBlocked = true;
  const integrityBlocked =
    snapshot.integrity === "invalid-contract" ||
    snapshot.integrity === "mixed-provenance";
  const stalePack = snapshot.integrity === "stale-pack";
  const shareBlockedTitle =
    snapshot.integrity === "unavailable" || stalePack
      ? "Run Coaching v1 analysis before sharing"
      : snapshot.integrity !== "coherent"
        ? "Sharing is blocked until metric provenance is coherent"
        : "Sharing is blocked until coaching candidates are human calibrated";
  const capabilityMessage =
    analysisCapability == null
      ? "Checking whether this local installation supports bounded text analysis."
      : analysisCapabilityCopy(analysisCapability);
  const compatibilityMessage = compatibilityLoading
    ? "Provider compatibility is being checked, so prompt-text analysis stays disabled."
    : promptTextCompatibilityBlocker(providerCompatibility ?? null);
  const analysisBlocker = capabilityMessage ?? compatibilityMessage;
  const analysisDisabled = analysisBlocker !== null;

  useEffect(() => {
    const previousTitle = document.title;
    const profileTitle = `${profile.title} · Prompt Enhancer`;
    document.title = profileTitle;
    headingRef.current?.focus();
    return () => {
      if (document.title === profileTitle) document.title = previousTitle;
    };
  }, [profile.title]);

  useEffect(() => {
    setSnapshotKind("latest");
  }, [profile.kind]);

  return (
    <section className={`quality-profile quality-profile--${profile.kind}`} aria-labelledby="quality-profile-title">
      <header className="quality-profile__header">
        <div>
          <p className="eyebrow">{profile.eyebrow}</p>
          <h2 id="quality-profile-title" ref={headingRef} tabIndex={-1}>{profile.title}</h2>
          <p>{profile.question}</p>
        </div>
        <div className="quality-profile__actions">
          {initialAvailable && (
            <div aria-label="Specification point" className="quality-profile__switch" role="group">
              <button
                aria-pressed={snapshotKind === "initial"}
                onClick={() => setSnapshotKind("initial")}
                type="button"
              >
                {profile.initialLabel}
              </button>
              <button
                aria-pressed={snapshotKind === "latest"}
                onClick={() => setSnapshotKind("latest")}
                type="button"
              >
                {profile.latestLabel}
              </button>
            </div>
          )}
          {onAnalyzeLocally && compatibilityMessage && onCheckProviderCompatibility && (
            <button
              className="button button--secondary button--compact"
              disabled={compatibilityLoading}
              onClick={() => {
                const controller = new AbortController();
                void onCheckProviderCompatibility(controller.signal).catch(() => undefined);
              }}
              title="Check the installed provider schema before local analysis"
              type="button"
            >
              {compatibilityLoading ? "Checking provider…" : "Check provider"}
            </button>
          )}
          {onAnalyzeLocally && (
            <div className="quality-profile__analysis-action">
              <button
                aria-describedby={analysisDisabled ? "quality-analysis-capability" : undefined}
                className="button button--primary button--compact"
                disabled={analysisDisabled}
                onClick={() => setAnalysisOpen(true)}
                title={analysisBlocker ?? undefined}
                type="button"
              >
                Analyze locally
              </button>
              {analysisBlocker && (
                <span id="quality-analysis-capability" role="status">
                  {analysisBlocker}
                </span>
              )}
            </div>
          )}
          <button
            className="button button--secondary button--compact"
            disabled={shareBlocked}
            onClick={() => setShareOpen(true)}
            title={shareBlocked ? shareBlockedTitle : undefined}
            type="button"
          >
            Share profile
          </button>
        </div>
      </header>
      <div className="quality-profile__snapshot-line">
        <span>{snapshotKind === "initial" ? profile.initialLabel : profile.latestLabel}</span>
        <span>{summary(snapshot.metrics)}</span>
        {snapshot.scope && (
          <span>
            {snapshot.scope.completedRuns} of {snapshot.scope.selectedSessions} selected
            sessions have a compatible Coaching v1 run
            {snapshot.scope.missingRuns > 0
              ? ` · ${snapshot.scope.missingRuns} need analysis`
              : ""}
          </span>
        )}
        {snapshot.integrity === "coherent" && (
          <span className="quality-profile__snapshot-provenance">
            Coherent metric pack{snapshot.metricPackVersion ? ` v${snapshot.metricPackVersion}` : ""}
          </span>
        )}
        {stalePack && (
          <span className="quality-profile__snapshot-refresh">
            Re-analysis required · stored pack v{snapshot.metricPackVersion}
          </span>
        )}
        {integrityBlocked && (
          <span className="quality-profile__snapshot-alert">
            {snapshot.integrity === "mixed-provenance"
              ? "Mixed provenance blocked"
              : "Invalid metric contract"}
          </span>
        )}
        {snapshotKind === "latest" && metricReadinessLoading && (
          <span>Checking content-free metric readiness</span>
        )}
        {snapshotKind === "latest" && metricReadinessError && (
          <span className="quality-profile__snapshot-alert">
            {metricReadinessError} Stored metric values are unchanged.
            {onRetryMetricReadiness && (
              <button
                className="button button--secondary button--compact"
                onClick={onRetryMetricReadiness}
                type="button"
              >
                Retry readiness
              </button>
            )}
          </span>
        )}
      </div>
      <details className="quality-profile__radar-panel" open>
        <summary>
          <span className="quality-profile__radar-summary-copy">
            <span className="quality-profile__radar-kicker">Visual overview</span>
            <strong>{profile.kind === "prompt" ? "Prompt-quality radar" : "Logic & decisions radar"}</strong>
            <small>Measured axes only · one shared 0–100% scale</small>
          </span>
          <span aria-hidden="true" className="quality-profile__radar-toggle">
            <span className="quality-profile__radar-toggle--open">Hide radar</span>
            <span className="quality-profile__radar-toggle--closed">Show radar</span>
          </span>
        </summary>
        <div className="quality-profile__radar-content">
          <QualityRadar
            metrics={snapshot.metrics}
            readiness={snapshotKind === "latest" ? metricReadiness?.metrics : null}
          />
        </div>
      </details>
      {primaryContent !== undefined && (
        <div className="quality-profile__layout">
          <div className="quality-profile__visual">{primaryContent}</div>
        </div>
      )}
      <MetricOpportunityMap />
      <details className="quality-profile__method-boundary">
        <summary>
          <span>
            <strong>Methods &amp; details</strong>
            <small>Receipts, denominators, limitations, provenance and provider readiness</small>
          </span>
          <span>Optional</span>
        </summary>
        <div className="quality-profile__method-content">
          <div className="quality-profile__method-grid">
            <div>
              <strong>Experimental baseline</strong>
              <span>Deterministic English/Polish candidate rules, not model scores.</span>
            </div>
            <div>
              <strong>Accuracy not calibrated</strong>
              <span>Repeatable arithmetic does not establish that a detected cue is correct.</span>
            </div>
            <div>
              <strong>Conversation-window scope</strong>
              <span>Up to 100 messages and 100,000 redacted characters around the latest user message.</span>
            </div>
          </div>

          <section aria-labelledby="quality-pipeline-title" className="quality-pipeline">
            <header>
              <p className="eyebrow">Active scoring path</p>
              <h3 id="quality-pipeline-title">How these percentages are produced</h3>
            </header>
            <ol>
              <li><strong>Bounded read</strong><span>One selected session, up to 100 messages and 100,000 redacted characters.</span></li>
              <li><strong>Safe projection</strong><span>User, agent-response, and plan text only; reasoning, commands, paths, and tool output are excluded.</span></li>
              <li><strong>Local preparation</strong><span>Best-effort redaction, English/Polish detection, and clause segmentation.</span></li>
              <li><strong>Candidate rules</strong><span>Versioned lexical and transition rules mark observable cues and candidate links.</span></li>
              <li><strong>Ratio</strong><span>Matched rule-defined items divided by eligible rule-defined items; missing denominators abstain.</span></li>
              <li><strong>Content-free storage</strong><span>Only states, counts, fractions, receipts, and pinned provenance are persisted.</span></li>
            </ol>
            <p>
              <strong>Active coaching model: none.</strong> Qwen3 Embedding 0.6B and BGE Reranker v2 M3 belong to a separate request-to-response linkage experiment and do not change these percentages.
            </p>
          </section>

          <div className="quality-profile__provenance-detail">
            <span>{profile.summary}</span>
            {profile.analysisProfile && <span>{profile.analysisProfile.label}</span>}
          </div>

          <section aria-labelledby="quality-metric-details-title" className="quality-methods">
            <header>
              <p className="eyebrow">Metric receipts</p>
              <h3 id="quality-metric-details-title">How each value was produced</h3>
            </header>
            <div className="quality-methods__grid">
              {snapshot.metrics.map((metric) => (
                <article className="quality-method" key={metric.definition.key}>
                  <header>
                    <div>
                      <strong>{metric.definition.label}</strong>
                      <span>{metric.definition.question}</span>
                    </div>
                    <b>{metric.ratio === null ? "—" : formatPercent(metric.ratio)}</b>
                    <small>{STATE_LABELS[metric.state]}</small>
                  </header>

                  {metric.signals.length > 0 && (
                    <ul aria-label={`${metric.definition.label} evidence receipt`} className="quality-method__signals">
                      {metric.signals.map((signal) => (
                        <li className={`quality-signal quality-signal--${signal.status}`} key={signal.code}>
                          <span aria-hidden="true">
                            {signal.status === "detected"
                              ? "✓"
                              : signal.status === "missing"
                                ? "○"
                                : signal.status === "unknown"
                                  ? "—"
                                  : "#"}
                          </span>
                          <span>{signalLabel(signal.code)}</span>
                          <strong>{signalValue(signal.status, signal.count)}</strong>
                        </li>
                      ))}
                    </ul>
                  )}

                  {explanationLine(metric) && (
                    <p className="quality-method__explanation" role="note">
                      {explanationLine(metric)}
                    </p>
                  )}
                  <dl>
                    <div><dt>Fraction</dt><dd>{fractionLine(metric)}</dd></div>
                    <div><dt>Window coverage</dt><dd>{coverageLine(metric)}</dd></div>
                    <div><dt>Denominator</dt><dd>{denominatorSource(metric)}</dd></div>
                    <div><dt>Extractor</dt><dd>{metric.modelId === null ? "Deterministic EN/PL rules · no model" : "Model-assisted result with pinned provenance"}</dd></div>
                    <div><dt>Method</dt><dd>{metric.definition.method}</dd></div>
                    <div><dt>Limit</dt><dd>{metric.definition.limitation}</dd></div>
                  </dl>
                </article>
              ))}
            </div>
          </section>

          {onAnalyzeLocally && (
            <ProviderCompatibilityCard
              loading={compatibilityLoading}
              onCheck={onCheckProviderCompatibility}
              onUpdate={onUpdateProvider}
              status={providerCompatibility ?? null}
            />
          )}

        </div>
      </details>
      {snapshot.metrics.every((metric) => metric.state === "unavailable") && (
        <div className="quality-profile__calibration" role="note">
          <strong>
            {stalePack
              ? "This profile was produced by an older immutable metric pack"
              : "No compatible Coaching v1 analysis run is available"}
          </strong>
          <span>
            {stalePack
              ? "The old result remains preserved, but its values are not relabeled as current metrics. Run the one-click local analysis to create a Coaching pack v3 profile."
              : "Older analysis packs remain preserved but are never mixed with this profile. Analyze the selected sessions with Coaching v1 to create comparable versioned receipts; no placeholder values are generated."}
          </span>
        </div>
      )}
      {integrityBlocked && (
        <div className="quality-profile__integrity-error" role="alert">
          <strong>Profile comparison and sharing are blocked</strong>
          <span>
            Stored rows do not form one coherent, valid metric-pack snapshot. No axis values are presented until the provenance boundary is repaired.
          </span>
        </div>
      )}
      <footer className="quality-profile__boundary">
        These are observable text signals—not a developer ranking, cognitive-skill measurement, hidden chain-of-thought inference, or overall score.
      </footer>
      {shareOpen && (
        <ProfileShareDialog
          onClose={() => setShareOpen(false)}
          profile={profile}
          snapshotKind={snapshotKind}
        />
      )}
      {analysisOpen && onAnalyzeLocally && (
        <AnalyzeLocallyDialog
          exactSessionId={onAnalyzeLocally.exactSessionId}
          onApprovePreview={onAnalyzeLocally.approvePreview}
          onCheckCompatibility={onCheckProviderCompatibility}
          onClose={() => setAnalysisOpen(false)}
          onPreparePreview={onAnalyzeLocally.preparePreview}
          sessionDescriptor={sessionDescriptor}
        />
      )}
    </section>
  );
}
