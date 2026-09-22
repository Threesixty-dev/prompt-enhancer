import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  ModelEnsembleRun,
  ModelRequirementVerificationEvidenceBinding,
} from "../../shared/api/contracts";
import { syntheticMetricPublicationV2 } from "../../test/metricPublicationV2Fixture";
import { MetricWorkspace } from "./MetricWorkspace";
import {
  modelEnsembleAxisPlottedLabel,
  modelEnsembleAxisRawRateLabel,
  modelEnsembleMetricStateLabel,
  modelEnsembleRadarAxes,
  type ModelEnsembleRadarData,
} from "./metricAxisModel";

type TypedMetric = ModelEnsembleRun["typed_metrics"][number];
type CommitteeMetric = ModelEnsembleRun["metrics"][number];

function typedMetric(metricKey: string, patch: Partial<TypedMetric>): TypedMetric {
  return {
    metric_key: metricKey,
    value_state: "known",
    numeric_value: 0.5,
    numerator: 1,
    denominator: 2,
    coverage: 1,
    observed_message_count: 2,
    eligible_message_count: 2,
    projection_source: "deterministic_typed_contract",
    explanation_code: "typed_requirement_ratio",
    ...patch,
  } as unknown as TypedMetric;
}

function committeeMetric(metricKey: string, patch: Partial<CommitteeMetric> = {}): CommitteeMetric {
  return {
    metric_key: metricKey,
    value_state: "known",
    numerator: 1,
    denominator: 2,
    numeric_value: 0.5,
    known_chunk_count: 2,
    abstained_chunk_count: 0,
    unsupported_chunk_count: 0,
    failed_chunk_count: 0,
    total_chunk_count: 4,
    explanation_code: "example_ratio_of_chunks",
    calibration_state: "not_assessed",
    product_metric_eligible: false,
    ...patch,
  };
}

const run: ModelEnsembleRadarData = {
  metrics: [],
  chunk_metrics: [],
  typed_metrics: [
    typedMetric("collaboration.ambiguity_resolution", { numeric_value: 0.25, numerator: 1, denominator: 4 }),
    typedMetric("collaboration.clarification_yield", { value_state: "unknown", numeric_value: null, numerator: null, denominator: null, explanation_code: "episode_horizon_open" }),
    typedMetric("collaboration.exploration_conversion", { value_state: "not_applicable", numeric_value: null, numerator: null, denominator: null }),
    typedMetric("collaboration.rework_candidate_rate", { numeric_value: 0.02, numerator: 2, denominator: 100 }),
  ],
  predictive_metrics: [],
};

const transport = { getModelPredictiveMetricDetail: vi.fn(() => new Promise<never>(() => undefined)) };
const verificationBinding: ModelRequirementVerificationEvidenceBinding = {
  evidence_source: "awaiting_evidence",
  requirement_plan_confirmation_id: "a".repeat(64),
  requirement_plan_proposal_id: "b".repeat(64),
  requirement_plan_evidence_fingerprint: "c".repeat(64),
  requirement_plan_schema_version: "requirement-plan-evidence-v1",
  requirement_plan_policy_version: "reviewed-requirement-plan-v1",
  requirement_plan_review_rubric_version: "active-requirement-plan-review-rubric-v1",
  opportunity_count: 1,
  opportunity_set_fingerprint: "d".repeat(64),
  evidence_set_fingerprint: null,
  through_revision: null,
  authority_head_count: 0,
  objective_result_count: 0,
  native_acceptance_count: 0,
  resolved_opportunity_count: 0,
  met_requirement_count: 0,
  opportunity_issuer_version: "reviewed-r6-requirement-opportunity-issuer-v1",
  result_issuer_version: "local-objective-verification-result-issuer-v1",
  acceptance_issuer_version: "native-explicit-requirement-acceptance-issuer-v1",
  evidence_schema_version: "requirement-verification-evidence-v1",
  evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
  persistence_schema_version: "requirement-verification-persistence-v1",
  evidence_projection_version: "reviewed-requirement-verification-objective-projection-v1",
  objective_projection_version: "reviewed-requirement-verification-objective-projection-v1",
  binding_schema_version: "session-requirement-verification-evidence-binding-v1",
  binding_fingerprint: "e".repeat(64),
  local_only: true,
  content_persisted: false,
};

function syntheticR8Publication(): NonNullable<ModelEnsembleRun["metric_publication_v2"]> {
  const publication = syntheticMetricPublicationV2({
    "outcome.verified_requirement_coverage": {
      value_state: "known",
      numerator: 0,
      denominator: 1,
      explanation_code: "app_issued_requirement_verification_pending",
    },
  });
  publication.projection_version = "metric-contract-v2-projection-8";
  publication.metrics.forEach((item) => {
    item.state.projection_version = "metric-contract-v2-projection-8";
  });
  return publication;
}

const verificationRun: ModelEnsembleRadarData = {
  ...run,
  typed_metrics: [],
  metric_publication_v2: syntheticR8Publication(),
};
const claimRun: ModelEnsembleRadarData = {
  ...run,
  typed_metrics: [],
  metric_publication_v2: (() => {
    const publication = syntheticMetricPublicationV2({
      "outcome.agent_claim_grounding": { value_state: "known", numerator: 1, denominator: 2, explanation_code: "typed_requirement_ratio" },
    });
    publication.projection_version = "metric-contract-v2-projection-8";
    publication.metrics.forEach((item) => { item.state.projection_version = "metric-contract-v2-projection-8"; });
    return publication;
  })(),
};

function verificationStage(runId: string): ModelEnsembleRun {
  return {
    run_id: runId,
    requirement_verification_evidence_binding: verificationBinding,
  } as unknown as ModelEnsembleRun;
}

describe("metric workspace surfaces share one axis presentation", () => {
  it("mounts verification evidence only for the active r8 requirement metric and its matching stage run", () => {
    const runId = "f".repeat(64);
    const props = {
      lensId: "outcome-evidence" as const,
      mode: "full" as const,
      onLensChange: vi.fn(),
      run: verificationRun,
      runId,
      snapshotLabel: "Synthetic",
      transport: { ...transport, issueCurrentRequirementVerificationOpportunities: vi.fn() },
      evidenceSessionId: "0".repeat(64),
      evidenceEnabled: true,
    };
    const view = render(<MetricWorkspace {...props} stageRun={verificationStage(runId)} />);
    expect(screen.getByRole("heading", { name: "Requirement verification evidence" })).toBeVisible();

    view.rerender(<MetricWorkspace {...props} stageRun={verificationStage("1".repeat(64))} />);
    expect(screen.queryByRole("heading", { name: "Requirement verification evidence" })).toBeNull();

    view.rerender(<MetricWorkspace {...props} lensId="task-framing" stageRun={verificationStage(runId)} />);
    expect(screen.queryByRole("heading", { name: "Requirement verification evidence" })).toBeNull();

    view.rerender(<MetricWorkspace {...props} evidenceEnabled={false} stageRun={verificationStage(runId)} />);
    expect(screen.queryByRole("heading", { name: "Requirement verification evidence" })).toBeNull();
  });

  it("mounts claim review only for the live active claim-grounding metric", () => {
    const runId = "c".repeat(64);
    const claimTransport = {
      ...transport,
      getUserPresenceCapability: vi.fn().mockResolvedValue({ confirmation_available: true, mode: "native_bridge_bound_token" }),
      getRequirementPlanEvidenceContract: vi.fn(), beginClaimGroundingReview: vi.fn(), consumeClaimGroundingReview: vi.fn(),
    };
    const props = { lensId: "outcome-evidence" as const, mode: "full" as const, onLensChange: vi.fn(), run: claimRun, runId, stageRun: { run_id: runId } as ModelEnsembleRun, snapshotLabel: "Synthetic", transport: claimTransport, evidenceSessionId: "0".repeat(64), evidenceEnabled: true };
    const view = render(<MetricWorkspace {...props} />);
    fireEvent.click(screen.getByRole("button", { name: /Agent claim grounding/i }));
    expect(screen.getByText(/Review assistant completion claims/i)).toBeVisible();
    view.rerender(<MetricWorkspace {...props} lensId="task-framing" />);
    expect(screen.queryByText(/Review assistant completion claims/i)).toBeNull();
    view.rerender(<MetricWorkspace {...props} evidenceEnabled={false} />);
    expect(screen.queryByText(/Review assistant completion claims/i)).toBeNull();
    view.rerender(<MetricWorkspace {...props} evidenceEnabled={true} runId={"d".repeat(64)} />);
    expect(screen.queryByText(/Review assistant completion claims/i)).toBeNull();
  });

  it("shows the production current-evidence notice after validated explicit R8 preparation without changing its saved run", async () => {
    const runId = "f".repeat(64);
    const savedRun = structuredClone(verificationRun);
    const issue = vi.fn().mockResolvedValue({ applied: true, snapshot: {
      revision: 1, local_only: true, content_persisted: false,
      persistence_schema_version: "requirement-verification-persistence-v1",
      authority_heads: [],
      evidence: {
        evidence_schema_version: "requirement-verification-evidence-v1",
        evidence_policy_version: "app-issued-reviewed-requirement-verification-v1",
        projection_version: "reviewed-requirement-verification-objective-projection-v1",
        evidence_set_fingerprint: "1".repeat(64), local_only: true, content_persisted: false,
        verification_results: [], acceptance_authorities: [],
        opportunities: {
          session_id: "0".repeat(64), source_window_fingerprint: "3".repeat(64),
          requirement_plan_confirmation_id: "a".repeat(64), requirement_plan_proposal_id: "b".repeat(64), requirement_plan_evidence_fingerprint: "c".repeat(64),
          requirement_plan_schema_version: "requirement-plan-evidence-v1", requirement_plan_policy_version: "reviewed-requirement-plan-v1", requirement_plan_review_rubric_version: "active-requirement-plan-review-rubric-v1",
          opportunity_set_fingerprint: "d".repeat(64), opportunities: [{ opportunity_id: "4".repeat(64), requirement_id: "5".repeat(64), requirement_index: 0, coordinate: { message_sequence: 1, clause_index: 0 } }],
          complete_active_requirement_enumeration: true, issuer_version: "reviewed-r6-requirement-opportunity-issuer-v1", evidence_schema_version: "requirement-verification-evidence-v1", evidence_policy_version: "app-issued-reviewed-requirement-verification-v1", local_only: true, content_persisted: false,
        },
      },
    } });
    const freshAnalysis = vi.fn()
      .mockRejectedValueOnce(new Error("synthetic fresh analysis failure"))
      .mockResolvedValue(undefined);
    const workspaceProps = { evidenceEnabled: true, evidenceSessionId: "0".repeat(64), lensId: "outcome-evidence" as const, mode: "full" as const, onLensChange: vi.fn(), run: verificationRun, runId, snapshotLabel: "Synthetic", stageRun: verificationStage(runId), transport: { ...transport, issueCurrentRequirementVerificationOpportunities: issue }, freshAnalysisAction: { onRun: freshAnalysis } };
    const view = render(<MetricWorkspace {...workspaceProps} />);
    const receiptSummaryBefore = screen.getByLabelText("20-contract receipt summary").textContent;
    const selectedMetricBefore = screen.getAllByText("Verified requirement coverage").map((node) => node.textContent);
    fireEvent.click(screen.getByRole("button", { name: "Prepare current reviewed requirements" }));
    await screen.findByText("Current evidence prepared; this analysis snapshot has not been changed.");
    expect(issue).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Current evidence changed for this session and run. Displayed metrics remain the saved analysis snapshot/).closest("[role=status]")).not.toBeNull();
    const freshButton = screen.getByRole("button", { name: "Run fresh analysis" });
    fireEvent.click(freshButton);
    fireEvent.click(freshButton);
    expect(freshAnalysis).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(freshAnalysis).toHaveBeenCalledTimes(1));
    fireEvent.click(freshButton);
    expect(freshAnalysis).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("region", { name: /metric workspace/i })).toHaveAttribute("data-run-id", runId);
    expect(screen.getByLabelText("20-contract receipt summary")).toHaveTextContent(receiptSummaryBefore ?? "");
    expect(screen.getAllByText("Verified requirement coverage").map((node) => node.textContent)).toEqual(selectedMetricBefore);
    expect(verificationRun).toEqual(savedRun);
    const throwing = vi.fn(() => { throw new Error("synthetic observer failure"); });
    view.rerender(<MetricWorkspace {...workspaceProps} onEvidenceChanged={throwing} />);
    fireEvent.click(screen.getByRole("button", { name: "Prepare current reviewed requirements" }));
    await waitFor(() => expect(throwing).toHaveBeenCalledTimes(1));
    const rejecting = vi.fn(() => Promise.reject(new Error("synthetic observer rejection")));
    view.rerender(<MetricWorkspace {...workspaceProps} onEvidenceChanged={rejecting} />);
    fireEvent.click(screen.getByRole("button", { name: "Prepare current reviewed requirements" }));
    await waitFor(() => expect(rejecting).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/Displayed metrics remain the saved analysis snapshot/)).toBeVisible();
    expect(screen.getByLabelText("20-contract receipt summary")).toHaveTextContent(receiptSummaryBefore ?? "");
    expect(screen.getAllByText("Verified requirement coverage").map((node) => node.textContent)).toEqual(selectedMetricBefore);
    expect(verificationRun).toEqual(savedRun);
    const nextRunId = "9".repeat(64);
    view.rerender(<MetricWorkspace {...workspaceProps} runId={nextRunId} stageRun={verificationStage(nextRunId)} />);
    fireEvent.click(freshButton);
    expect(freshAnalysis).toHaveBeenCalledTimes(2);
    expect(screen.queryByText(/Current evidence changed for this session and run/)).toBeNull();
  });

  it("partitions the canonical 20-contract receipt ledger without promoting state-only or missing entries", () => {
    render(
      <MetricWorkspace lensId="collaboration-flow" mode="full" onLensChange={vi.fn()} run={run} runId={"e".repeat(64)} snapshotLabel="Synthetic" transport={transport} />,
    );
    const summary = within(screen.getByLabelText("20-contract receipt summary"));
    expect(summary.getByText("Measured").nextElementSibling).toHaveTextContent("2/20");
    expect(summary.getByText("Legacy signals").nextElementSibling).toHaveTextContent("0");
    expect(summary.getByText("Pending").nextElementSibling).toHaveTextContent("1");
    expect(summary.getByText("N/A").nextElementSibling).toHaveTextContent("1");
    expect(summary.getByText("Unresolved").nextElementSibling).toHaveTextContent("0");
    expect(summary.getByText("No receipt").nextElementSibling).toHaveTextContent("16");
  });

  it("labels a legacy committee value as a signal instead of a typed measurement", () => {
    const legacyRun: ModelEnsembleRadarData = {
      ...run,
      metrics: [committeeMetric("collaboration.ambiguity_resolution")],
      typed_metrics: [],
    };
    render(
      <MetricWorkspace lensId="collaboration-flow" mode="full" onLensChange={vi.fn()} run={legacyRun} runId={"e".repeat(64)} snapshotLabel="Synthetic" transport={transport} />,
    );
    const summary = within(screen.getByLabelText("20-contract receipt summary"));
    expect(summary.getByText("Measured").nextElementSibling).toHaveTextContent("0/20");
    expect(summary.getByText("Legacy signals").nextElementSibling).toHaveTextContent("1");
    expect(summary.getByText("No receipt").nextElementSibling).toHaveTextContent("19");
    expect(within(screen.getByRole("region", { name: /exact metric values/i }))
      .getByRole("button", { name: /Ambiguity-resolution candidates/i })).toHaveTextContent("50% signal");
  });

  it("renders every nonnumeric state explicitly while preserving an authoritative numeric zero", () => {
    const stateRun: ModelEnsembleRadarData = {
      metrics: [],
      chunk_metrics: [],
      typed_metrics: [
        typedMetric("prompt.task_definition_coverage", { numeric_value: 0, numerator: 0, denominator: 2 }),
        typedMetric("prompt.problem_evidence_quality", { value_state: "unknown", numeric_value: null, numerator: null, denominator: null }),
        typedMetric("prompt.context_sufficiency", { value_state: "not_applicable", numeric_value: null, numerator: null, denominator: null }),
        typedMetric("prompt.constraint_precision", { value_state: "abstained", numeric_value: null, numerator: null, denominator: null }),
        typedMetric("prompt.acceptance_testability", { value_state: "execution_error", numeric_value: null, numerator: null, denominator: null }),
      ],
      predictive_metrics: [],
    };
    render(
      <MetricWorkspace lensId="task-framing" mode="full" onLensChange={vi.fn()} run={stateRun} runId={"e".repeat(64)} snapshotLabel="Synthetic" transport={transport} />,
    );
    const board = within(screen.getByRole("region", { name: /exact metric values/i }));
    expect(board.getByRole("button", { name: /Task definition coverage/i }).querySelector("b")).toHaveTextContent("0% measured");
    expect(board.getByRole("button", { name: /Problem evidence quality/i }).querySelector("b")).toHaveTextContent("Unknown");
    expect(board.getByRole("button", { name: /Context cue checks/i }).querySelector("b")).toHaveTextContent("N/A");
    expect(board.getByRole("button", { name: /Constraint precision candidates/i }).querySelector("b")).toHaveTextContent("Needs evidence");
    expect(board.getByRole("button", { name: /Acceptance testability cues/i }).querySelector("b")).toHaveTextContent("Error");
    expect(board.getByRole("button", { name: /Deliverable contract cues/i }).querySelector("b")).toHaveTextContent("No record");
  });

  it("defaults to authoritative evidence, preserves an explicit selection, and closes pinned context on snapshot change", () => {
    const mixedRun: ModelEnsembleRadarData = {
      metrics: [committeeMetric("prompt.task_definition_coverage")],
      chunk_metrics: [],
      typed_metrics: [typedMetric("prompt.problem_evidence_quality", {})],
      predictive_metrics: [],
    };
    const props = {
      lensId: "task-framing" as const,
      mode: "full" as const,
      onLensChange: vi.fn(),
      run: mixedRun,
      runId: "e".repeat(64),
      snapshotLabel: "Synthetic",
      transport,
    };
    const view = render(<MetricWorkspace {...props} />);
    const board = within(screen.getByRole("region", { name: /exact metric values/i }));
    expect(board.getByRole("button", { name: /Problem evidence quality/i })).toHaveAttribute("aria-pressed", "true");

    const chosen = board.getByRole("button", { name: /Context cue checks/i });
    fireEvent.click(chosen);
    expect(chosen).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("region", { name: "Context cue checks knowledge card" })).toBeVisible();

    view.rerender(<MetricWorkspace {...props} runId={"f".repeat(64)} />);
    expect(screen.queryByRole("region", { name: "Context cue checks knowledge card" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: /exact metric values/i }))
      .getByRole("button", { name: /Context cue checks/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("uses labeled regions and a grouped, keyboard-operable lens selector", () => {
    const onLensChange = vi.fn();
    render(
      <MetricWorkspace lensId="collaboration-flow" mode="full" onLensChange={onLensChange} run={run} runId={"e".repeat(64)} snapshotLabel="Synthetic" transport={transport} />,
    );
    expect(screen.getByRole("region", { name: /Metric workspace · Snapshot/i })).toBeVisible();
    expect(screen.getByRole("heading", { level: 3, name: /Metric workspace · Snapshot/i })).toBeVisible();
    expect(screen.getByRole("heading", { level: 4, name: /exact metric values/i })).toBeVisible();
    const lenses = screen.getByRole("group", { name: "Metric workspace view" });
    const buttons = within(lenses).getAllByRole("button");
    buttons[0].focus();
    expect(buttons[0]).toHaveFocus();
    fireEvent.keyDown(buttons[0], { key: "ArrowRight" });
    expect(onLensChange).toHaveBeenLastCalledWith("collaboration-flow");
    fireEvent.keyDown(buttons[0], { key: "End" });
    expect(onLensChange).toHaveBeenLastCalledWith("outcome-evidence");
    fireEvent.keyDown(buttons[3], { key: "Home" });
    expect(onLensChange).toHaveBeenLastCalledWith("task-framing");
  });

  it("describes comparison geometry only when the selected lens has comparable numeric values", () => {
    const stateOnlyComparison: ModelEnsembleRadarData = {
      metrics: [],
      chunk_metrics: [],
      typed_metrics: [typedMetric("collaboration.ambiguity_resolution", {
        value_state: "unknown", numeric_value: null, numerator: null, denominator: null,
      })],
      predictive_metrics: [],
    };
    const props = {
      comparisonLabel: "Reviewed baseline",
      comparisonRun: stateOnlyComparison,
      lensId: "collaboration-flow" as const,
      mode: "full" as const,
      onLensChange: vi.fn(),
      run,
      runId: "e".repeat(64),
      snapshotLabel: "Synthetic",
      transport,
    };
    const view = render(<MetricWorkspace {...props} />);
    expect(screen.getByText("No numeric comparison is available for Reviewed baseline in this lens.")).toBeVisible();
    expect(screen.queryByText(/Dashed geometry marks/i)).not.toBeInTheDocument();

    view.rerender(<MetricWorkspace {...props} comparisonRun={run} />);
    expect(screen.getByText("Dashed geometry marks Reviewed baseline where numeric values exist.")).toBeVisible();
  });

  it("lets the compact axis strip select every metric, including state-only axes", () => {
    render(
      <MetricWorkspace lensId="collaboration-flow" mode="compact" onLensChange={vi.fn()} run={run} runId={"e".repeat(64)} snapshotLabel="Synthetic" transport={transport} />,
    );
    const strip = within(screen.getByRole("navigation", { name: "Collaboration flow metric axes" })).getAllByRole("button");

    for (const button of strip) {
      fireEvent.click(button);
      expect(button).toHaveAttribute("aria-pressed", "true");
    }
  });

  it("keeps radar orientation in the plot and promotes the raw measured value in the exact-value board", () => {
    render(
      <MetricWorkspace lensId="collaboration-flow" mode="full" onLensChange={vi.fn()} run={run} runId={"e".repeat(64)} snapshotLabel="Synthetic" transport={transport} />,
    );
    const axes = modelEnsembleRadarAxes(run, "collaboration-flow");
    const strip = within(screen.getByRole("navigation", { name: "Collaboration flow metric axes" })).getAllByRole("button");
    const board = within(screen.getByRole("region", { name: /exact metric values/i })).getAllByRole("button");
    expect(strip).toHaveLength(axes.length);
    expect(board).toHaveLength(axes.length);

    axes.forEach((axis, index) => {
      const rawRate = modelEnsembleAxisRawRateLabel(axis);
      const stripValue = strip[index].querySelector("b")?.textContent;
      const stripSmalls = [...strip[index].querySelectorAll("small")].map((node) => node.textContent);
      const boardStatus = board[index].querySelector("small")?.textContent;
      expect(stripValue).toBe(modelEnsembleAxisPlottedLabel(axis));
      expect(strip[index]).toHaveClass(`is-${axis.metric === null ? "missing" : axis.metric.value_state === "unknown" && axis.metric.explanation_code === "episode_horizon_open" ? "pending" : axis.metric.value_state}`);
      const expectedStatus = modelEnsembleMetricStateLabel(axis.metric);
      const numericValue = axis.metric?.numeric_value;
      const boardCaption = rawRate === null || typeof numericValue !== "number"
        ? expectedStatus
        : `${expectedStatus} · radar orientation ${100 - Math.round(numericValue * 100)}%`;
      expect(boardStatus).toBe(boardCaption);
      if (rawRate === null) {
        expect(stripSmalls.some((text) => text?.startsWith("raw rate"))).toBe(false);
      } else {
        expect(stripSmalls).toContain(rawRate);
      }
      expect(strip[index].getAttribute("aria-describedby")).toBe(board[index].getAttribute("aria-describedby"));
    });

    const rework = axes.findIndex((axis) => axis.key === "collaboration.rework_candidate_rate");
    expect(strip[rework].querySelector("b")?.textContent).toBe("98% radar quality");
    expect(board[rework].querySelector("small")?.textContent).toBe("known · radar orientation 98%");
    expect(board[rework].querySelector("b")?.textContent).toBe("2% measured raw rate");
    const pending = axes.findIndex((axis) => axis.key === "collaboration.clarification_yield");
    expect(strip[pending].querySelector("b")?.textContent).toBe("Pending");
    expect(board[pending].querySelector("small")?.textContent).toBe("pending · horizon open");
    expect(board[pending].querySelector("b")?.textContent).toBe("Pending");
    const missing = axes.findIndex((axis) => axis.key === "collaboration.scope_change_discipline");
    expect(strip[missing].querySelector("b")?.textContent).toBe("No record");
    expect(board[missing].querySelector("b")?.textContent).toBe("No record");
    expect(board[missing].querySelector("small")?.textContent).toBe("not observed");
  });
});
