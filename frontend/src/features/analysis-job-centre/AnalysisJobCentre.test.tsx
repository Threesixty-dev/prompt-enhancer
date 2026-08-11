import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  AnalysisJobRecord,
  AnalysisJobState,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { AnalysisJobCentre, ANALYSIS_JOB_STATES } from "./AnalysisJobCentre";

function job(
  state: AnalysisJobState,
  index: number,
  overrides: Partial<AnalysisJobRecord> = {},
): AnalysisJobRecord {
  const terminal = ["completed", "partial", "failed", "cancelled", "superseded"]
    .includes(state);
  return {
    job_id: index.toString(16).repeat(64),
    identity: {
      kind: "session_quality",
      provider: "codex",
      project_id: "a".repeat(64),
      session_id: "b".repeat(64),
      input_fingerprint: "c".repeat(64),
      provenance_fingerprint: "d".repeat(64),
      metric_keys: ["logic.decomposition_coverage", "prompt.goal_definition"],
      estimator_plan_version: "example-plan-1",
      redactor_version: "example-redactor-1",
      provider_schema_version: "example-schema-1",
      automation_grant_id: null,
      local_only: true,
    },
    state,
    stage_number: state === "stage_n" ? 2 : null,
    progress_completed: state === "completed" ? 4 : index % 4,
    progress_total: 4,
    attempt_count: state === "queued" ? 0 : 1,
    max_attempts: 3,
    available_at: "2040-01-02T09:00:00Z",
    cancel_requested: false,
    last_error_code: null,
    terminal_reason_code: terminal ? state : null,
    created_at: "2040-01-02T08:00:00Z",
    updated_at: "2040-01-02T09:00:00Z",
    terminal_at: terminal ? "2040-01-02T09:00:00Z" : null,
    ...overrides,
  };
}

function localTransport(initialJobs: AnalysisJobRecord[]) {
  const transport = createSyntheticTransport();
  const listAnalysisJobs = vi.fn(async (
    state: AnalysisJobState | null = null,
    limit = 25,
    offset = 0,
  ) => ({
    jobs: initialJobs.filter((item) => state === null || item.state === state),
    limit,
    offset,
  }));
  const getAnalysisJob = vi.fn(async (jobId: string) => {
    const found = initialJobs.find((item) => item.job_id === jobId);
    if (!found) throw new TransportError("PRIVATE-DETAIL-CANARY", 404, "analysis_job_not_found");
    return found;
  });
  const cancelAnalysisJob = vi.fn(async (jobId: string) => {
    const found = initialJobs.find((item) => item.job_id === jobId);
    if (!found) throw new TransportError("PRIVATE-CANCEL-CANARY", 404, "analysis_job_not_found");
    return job("cancelled", Number.parseInt(jobId[0], 16), {
      job_id: found.job_id,
      identity: found.identity,
      terminal_reason_code: "cancellation_requested",
    });
  });
  transport.listAnalysisJobs = listAnalysisJobs;
  transport.getAnalysisJob = getAnalysisJob;
  transport.cancelAnalysisJob = cancelAnalysisJob;
  return { transport, listAnalysisJobs, getAnalysisJob, cancelAnalysisJob };
}

describe("AnalysisJobCentre", () => {
  it("fails closed in synthetic demo and never asks the fictional transport for queue history", () => {
    const { transport, listAnalysisJobs } = localTransport([]);
    render(
      <AnalysisJobCentre
        runtimeMode="synthetic_demo"
        serviceState="available"
        transport={transport}
      />,
    );

    expect(screen.getByRole("heading", { name: "Analysis Job Centre" })).toBeVisible();
    expect(screen.getByText("No jobs ran")).toBeVisible();
    expect(screen.getByText(/does not invent queue history/i)).toBeVisible();
    expect(listAnalysisJobs).not.toHaveBeenCalled();
  });

  it.each(["checking", "unavailable"] as const)(
    "does not query jobs while local service health is %s",
    (serviceState) => {
      const { transport, listAnalysisJobs } = localTransport([]);
      render(
        <AnalysisJobCentre
          runtimeMode="local_real"
          serviceState={serviceState}
          transport={transport}
        />,
      );
      expect(screen.getByRole("status")).toHaveTextContent(
        serviceState === "checking" ? /checking the local service/i : /local service unavailable/i,
      );
      expect(listAnalysisJobs).not.toHaveBeenCalled();
    },
  );

  it("renders every closed queue state, exact progress, and restart recovery truthfully", async () => {
    const jobs = ANALYSIS_JOB_STATES.map((state, index) =>
      state === "queued"
        ? job(state, index + 1, {
            attempt_count: 1,
            last_error_code: "lease_expired",
          })
        : job(state, index + 1),
    );
    const { transport } = localTransport(jobs);
    const { container } = render(
      <AnalysisJobCentre
        runtimeMode="local_real"
        serviceState="available"
        transport={transport}
      />,
    );

    expect(await screen.findByText("9 on this page")).toBeVisible();
    expect(container.querySelectorAll("button.analysis-job-card")).toHaveLength(9);
    expect(screen.getAllByRole("progressbar")).toHaveLength(9);
    const stateLabels: Record<(typeof ANALYSIS_JOB_STATES)[number], string> = {
      queued: "Queued",
      preprocessing: "Preprocessing",
      stage_n: "Running stage",
      awaiting_approval: "Awaiting approval",
      completed: "Completed",
      partial: "Partial",
      failed: "Failed",
      cancelled: "Cancelled",
      superseded: "Superseded",
    };
    for (const state of ANALYSIS_JOB_STATES) {
      const option = screen.getByRole("option", {
        name: stateLabels[state],
      });
      expect(option).toBeInTheDocument();
    }
    expect(screen.getByText(/recovered after restart · bounded retry pending/i)).toBeVisible();
    expect(container.querySelector(".analysis-job-centre__layout")).not.toBeNull();
  });

  it("filters through the authenticated list route and opens verified detail with keyboard-focusable controls", async () => {
    const queued = job("queued", 1);
    const completed = job("completed", 2);
    const { transport, listAnalysisJobs, getAnalysisJob } = localTransport([
      queued,
      completed,
    ]);
    const { container } = render(
      <AnalysisJobCentre
        runtimeMode="local_real"
        serviceState="available"
        transport={transport}
      />,
    );
    await screen.findByText("2 on this page");
    const filter = screen.getByRole("combobox", { name: "Queue state" });
    filter.focus();
    expect(filter).toHaveFocus();
    fireEvent.change(filter, { target: { value: "completed" } });

    await waitFor(() => expect(listAnalysisJobs).toHaveBeenLastCalledWith(
      "completed",
      25,
      0,
      expect.any(AbortSignal),
    ));
    const card = container.querySelector<HTMLButtonElement>("button.analysis-job-card");
    expect(card).not.toBeNull();
    card?.focus();
    expect(card).toHaveFocus();
    fireEvent.click(card!);

    await waitFor(() => expect(getAnalysisJob).toHaveBeenCalledWith(
      completed.job_id,
      expect.any(AbortSignal),
    ));
    const detail = screen.getByRole("complementary", { name: "Selected job detail" });
    expect(within(detail).getByText(completed.job_id)).toBeVisible();
    expect(within(detail).getByText("logic.decomposition_coverage")).toBeVisible();
    expect(within(detail).getByText(/all scheduled local stages completed/i)).toBeVisible();
    expect(within(detail).queryByRole("button", { name: /cancel job/i })).not.toBeInTheDocument();
  });

  it("presents recovered retry timing and awaiting-approval boundaries without claiming execution", async () => {
    const recovered = job("queued", 1, {
      attempt_count: 1,
      last_error_code: "lease_expired",
    });
    const approval = job("awaiting_approval", 2, {
      progress_completed: 2,
    });
    const { transport } = localTransport([recovered, approval]);
    const { container } = render(
      <AnalysisJobCentre runtimeMode="local_real" serviceState="available" transport={transport} />,
    );
    await screen.findByText("2 on this page");
    const cards = container.querySelectorAll<HTMLButtonElement>("button.analysis-job-card");
    fireEvent.click(cards[0]);
    expect(await screen.findByText(/recovered after restart or an expired worker lease/i)).toBeVisible();
    fireEvent.click(cards[1]);
    expect(await screen.findByText(/paused at an explicit approval gate/i)).toBeVisible();
    expect(screen.getByText(/background consent never authorizes a remote call/i)).toBeVisible();
  });

  it("requires confirmation, cancels the exact job, and preserves its content-free receipt", async () => {
    const queued = job("queued", 1);
    const { transport, cancelAnalysisJob } = localTransport([queued]);
    const { container } = render(
      <AnalysisJobCentre runtimeMode="local_real" serviceState="available" transport={transport} />,
    );
    await screen.findByText("1 on this page");
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    const cancel = await screen.findByRole("button", { name: "Cancel job" });
    fireEvent.click(cancel);
    const confirmation = screen.getByRole("group", { name: "Confirm job cancellation" });
    expect(within(confirmation).getByRole("button", { name: "Keep job" })).toBeVisible();
    fireEvent.click(within(confirmation).getByRole("button", { name: "Confirm cancellation" }));

    await waitFor(() => expect(cancelAnalysisJob).toHaveBeenCalledWith(queued.job_id));
    expect(await screen.findByText(/cancellation was requested by the local user/i)).toBeVisible();
    expect(screen.getAllByText("Cancelled").length).toBeGreaterThan(0);
    expect(screen.getByText(queued.job_id)).toBeVisible();
  });

  it("suppresses raw detail and cancellation errors", async () => {
    const queued = job("queued", 1);
    const { transport } = localTransport([queued]);
    transport.getAnalysisJob = vi.fn(async () => {
      throw new TransportError("PRIVATE-DETAIL-CANARY", 503);
    });
    transport.cancelAnalysisJob = vi.fn(async () => {
      throw new TransportError("PRIVATE-CANCEL-CANARY", 409, "analysis_job_conflict");
    });
    const { container } = render(
      <AnalysisJobCentre runtimeMode="local_real" serviceState="available" transport={transport} />,
    );
    await screen.findByText("1 on this page");
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    expect(await screen.findByText(/job detail could not be verified/i)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm cancellation" }));
    expect(await screen.findByText(/changed before cancellation was applied/i)).toBeVisible();
    expect(document.body.textContent).not.toContain("PRIVATE-DETAIL-CANARY");
    expect(document.body.textContent).not.toContain("PRIVATE-CANCEL-CANARY");
  });

  it("suppresses raw queue errors and labels a retained response as potentially stale", async () => {
    const queued = job("queued", 1);
    const { transport, listAnalysisJobs } = localTransport([queued]);
    listAnalysisJobs
      .mockResolvedValueOnce({ jobs: [queued], limit: 25, offset: 0 })
      .mockRejectedValueOnce(new TransportError("PRIVATE-LIST-CANARY", 503));
    const { container } = render(
      <AnalysisJobCentre runtimeMode="local_real" serviceState="available" transport={transport} />,
    );
    await screen.findByText("1 on this page");
    fireEvent.click(screen.getByRole("button", { name: "Refresh queue" }));

    expect(await screen.findByText(/local job queue could not be verified/i)).toBeVisible();
    expect(screen.getByText(/last verified response and may now be stale/i)).toBeVisible();
    expect(container.querySelectorAll("button.analysis-job-card")).toHaveLength(1);
    expect(document.body.textContent).not.toContain("PRIVATE-LIST-CANARY");
  });

  it("fails closed when verified detail drifts from the selected session identity", async () => {
    const queued = job("queued", 1);
    const driftedSessionId = "e".repeat(64);
    const { transport } = localTransport([queued]);
    transport.getAnalysisJob = vi.fn(async () => job("queued", 1, {
      job_id: queued.job_id,
      identity: { ...queued.identity, session_id: driftedSessionId },
    }));
    const { container } = render(
      <AnalysisJobCentre runtimeMode="local_real" serviceState="available" transport={transport} />,
    );
    await screen.findByText("1 on this page");
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);

    expect(await screen.findByText(/job identity changed unexpectedly/i)).toBeVisible();
    expect(document.body.textContent).not.toContain(driftedSessionId);
    expect(screen.getByText(queued.identity.session_id)).toBeVisible();
  });

  it("never renders an unrecognized terminal reason as raw error copy", async () => {
    const failed = job("failed", 1, {
      terminal_reason_code: "PRIVATE_ERROR_CANARY",
    });
    const { transport } = localTransport([failed]);
    const { container } = render(
      <AnalysisJobCentre runtimeMode="local_real" serviceState="available" transport={transport} />,
    );
    await screen.findByText("1 on this page");
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    expect(await screen.findByText(/raw worker errors remain hidden/i)).toBeVisible();
    expect(document.body.textContent).not.toContain("PRIVATE_ERROR_CANARY");
  });
});
