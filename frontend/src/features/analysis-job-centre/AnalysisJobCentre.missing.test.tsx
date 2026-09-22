import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AnalysisJobPage, AnalysisJobRecord, PromptEnhancerTransport } from "../../shared/api/contracts";
import {
  parseAnalysisJobPage,
  parseAnalysisJobRecord,
  TransportError,
} from "../../shared/api/httpTransport";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { AnalysisJobCentre } from "./AnalysisJobCentre";

const JOB_A_ID = "a".repeat(64);
const JOB_B_ID = "b".repeat(64);

describe("AnalysisJobCentre authoritative absence", () => {
  it("removes only a cancelled job that is authoritatively absent", async () => {
    const jobA = queuedJob(JOB_A_ID, "c".repeat(64));
    const jobB = queuedJob(JOB_B_ID, "d".repeat(64));
    let jobs = [jobA, jobB];
    const listAnalysisJobs = vi.fn<PromptEnhancerTransport["listAnalysisJobs"]>(async (_state = null, limit = 25, offset = 0) =>
      parseAnalysisJobPage({ jobs, limit, offset }, limit, offset),
    );
    const getAnalysisJob = vi.fn<PromptEnhancerTransport["getAnalysisJob"]>(async (jobId) =>
      jobId === jobA.job_id ? jobA : jobB,
    );
    const cancelAnalysisJob = vi.fn<PromptEnhancerTransport["cancelAnalysisJob"]>(async () => {
      jobs = [jobB];
      throw new TransportError("Synthetic authoritative absence", 404, "analysis_job_not_found");
    });
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      listAnalysisJobs,
      getAnalysisJob,
      cancelAnalysisJob,
    };
    const { container } = render(
      <AnalysisJobCentre runtimeMode="local_real" serviceState="available" transport={transport} />,
    );

    await screen.findByText("2 on this page");
    const cards = container.querySelectorAll<HTMLButtonElement>("button.analysis-job-card");
    fireEvent.click(cards[0]);
    const detail = screen.getByRole("complementary", { name: "Selected job detail" });
    await within(detail).findByText(jobA.job_id);
    fireEvent.click(within(detail).getByRole("button", { name: "Cancel job" }));
    fireEvent.click(within(detail).getByRole("button", { name: "Confirm cancellation" }));

    await waitFor(() => expect(cancelAnalysisJob).toHaveBeenCalledExactlyOnceWith(jobA.job_id, expect.any(AbortSignal)));
    await waitFor(() => expect(screen.queryByText(jobA.job_id)).not.toBeInTheDocument());
    expect(within(detail).getByRole("heading", { name: "Select a job" })).toBeVisible();
    expect(within(detail).queryByRole("group", { name: "Confirm job cancellation" })).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("This job record is no longer available. Refresh the queue to view its current receipts.");
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    expect(await within(detail).findByText(jobB.job_id)).toBeVisible();
    expect(cancelAnalysisJob).toHaveBeenCalledTimes(1);
  });

  it("retires a selected job when its current detail is typed as authoritatively absent", async () => {
    const jobA = queuedJob(JOB_A_ID, "c".repeat(64));
    const jobB = queuedJob(JOB_B_ID, "d".repeat(64));
    const transport = jobTransport([jobA, jobB], vi.fn<PromptEnhancerTransport["getAnalysisJob"]>(async (jobId) => {
      if (jobId === jobA.job_id) throw new TransportError("Synthetic detail absence", 404, "analysis_job_not_found");
      return jobB;
    }));
    const { container } = renderCentre(transport);

    await screen.findByText("2 on this page");
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    const detail = screen.getByRole("complementary", { name: "Selected job detail" });
    await waitFor(() => expect(screen.queryByText(jobA.job_id)).not.toBeInTheDocument());
    expect(within(detail).getByRole("heading", { name: "Select a job" })).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("This job record is no longer available. Refresh the queue to view its current receipts.");
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    expect(await within(detail).findByText(jobB.job_id)).toBeVisible();
  });

  it.each([
    ["generic 404", new TransportError("Synthetic untyped absence", 404)],
    ["generic 503", new TransportError("Synthetic unavailable", 503)],
    ["503 with a not-found reason", new TransportError("Synthetic mismatched absence", 503, "analysis_job_not_found")],
  ])("preserves the selected job after a %s detail error", async (_label, failure) => {
    const jobA = queuedJob(JOB_A_ID, "c".repeat(64));
    const jobB = queuedJob(JOB_B_ID, "d".repeat(64));
    const transport = jobTransport([jobA, jobB], vi.fn<PromptEnhancerTransport["getAnalysisJob"]>(async () => { throw failure; }));
    const { container } = renderCentre(transport);

    await screen.findByText("2 on this page");
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    const detail = screen.getByRole("complementary", { name: "Selected job detail" });
    await within(detail).findByRole("alert");
    expect(within(detail).getByText(jobA.job_id)).toBeVisible();
    expect(container.querySelectorAll("button.analysis-job-card")).toHaveLength(2);
    expect(within(detail).getByRole("button", { name: "Cancel job" })).toBeEnabled();
  });

  it("blocks cancellation after a known identity drift until a valid detail is read", async () => {
    const jobA = queuedJob(JOB_A_ID, "c".repeat(64));
    const drifted = queuedJob(JOB_A_ID, "d".repeat(64));
    let currentDetail = drifted;
    const transport = jobTransport([jobA], vi.fn<PromptEnhancerTransport["getAnalysisJob"]>(async () => currentDetail));
    const { container } = renderCentre(transport);

    await screen.findByText("1 on this page");
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    const detail = screen.getByRole("complementary", { name: "Selected job detail" });
    await within(detail).findByRole("alert");
    const cancel = within(detail).getByRole<HTMLButtonElement>("button", { name: "Cancel job" });
    expect(cancel).toBeDisabled();
    expect(cancel).toHaveAttribute("aria-describedby", "analysis-job-identity-conflict");

    currentDetail = jobA;
    fireEvent.click(screen.getByRole("button", { name: "Refresh queue" }));
    await waitFor(() => expect(within(detail).getByRole("button", { name: "Cancel job" })).toBeEnabled());
  });

  it("does not let an old selected job's typed absence clear a newer selection", async () => {
    const jobA = queuedJob(JOB_A_ID, "c".repeat(64));
    const jobB = queuedJob(JOB_B_ID, "d".repeat(64));
    const pendingA = deferred<AnalysisJobRecord>();
    const transport = jobTransport([jobA, jobB], vi.fn<PromptEnhancerTransport["getAnalysisJob"]>(async (jobId) =>
      jobId === jobA.job_id ? pendingA.promise : jobB,
    ));
    const { container } = renderCentre(transport);

    await screen.findByText("2 on this page");
    const cards = container.querySelectorAll<HTMLButtonElement>("button.analysis-job-card");
    fireEvent.click(cards[0]);
    fireEvent.click(cards[1]);
    const detail = screen.getByRole("complementary", { name: "Selected job detail" });
    expect(await within(detail).findByText(jobB.job_id)).toBeVisible();

    await act(async () => {
      pendingA.reject(new TransportError("Synthetic stale absence", 404, "analysis_job_not_found"));
      await pendingA.promise.catch(() => undefined);
    });
    expect(within(detail).getByText(jobB.job_id)).toBeVisible();
    expect(screen.queryByText("This job record is no longer available. Refresh the queue to view its current receipts.")).not.toBeInTheDocument();
  });

  it("fences an old transport's late missing detail after replacement selection", async () => {
    const jobA = queuedJob(JOB_A_ID, "c".repeat(64));
    const jobB = queuedJob(JOB_B_ID, "d".repeat(64));
    const pendingA = deferred<AnalysisJobRecord>();
    const oldTransport = jobTransport([jobA], vi.fn<PromptEnhancerTransport["getAnalysisJob"]>(async () => pendingA.promise));
    const replacementTransport = jobTransport([jobB], vi.fn<PromptEnhancerTransport["getAnalysisJob"]>(async () => jobB));
    const view = renderCentre(oldTransport);

    await screen.findByText("1 on this page");
    fireEvent.click(view.container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    view.rerender(<AnalysisJobCentre runtimeMode="local_real" serviceState="available" transport={replacementTransport} />);
    await screen.findByText("1 on this page");
    fireEvent.click(view.container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    const detail = screen.getByRole("complementary", { name: "Selected job detail" });
    expect(await within(detail).findByText(jobB.job_id)).toBeVisible();

    await act(async () => {
      pendingA.reject(new TransportError("Synthetic old transport absence", 404, "analysis_job_not_found"));
      await pendingA.promise.catch(() => undefined);
    });
    expect(within(detail).getByText(jobB.job_id)).toBeVisible();
    expect(screen.queryByText("This job record is no longer available. Refresh the queue to view its current receipts.")).not.toBeInTheDocument();
  });

  it("admits an explicitly refreshed current receipt with the same deterministic job id", async () => {
    const original = queuedJob(JOB_A_ID, "c".repeat(64));
    const replacement = queuedJob(JOB_A_ID, "c".repeat(64), {
      available_at: "2040-01-01T00:01:00Z",
      updated_at: "2040-01-01T00:01:00Z",
    });
    let jobs = [original];
    const cancelAnalysisJob = vi.fn<PromptEnhancerTransport["cancelAnalysisJob"]>(async () => {
      jobs = [];
      throw new TransportError("Synthetic authoritative absence", 404, "analysis_job_not_found");
    });
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      listAnalysisJobs: vi.fn<PromptEnhancerTransport["listAnalysisJobs"]>(async (_state = null, limit = 25, offset = 0) =>
        parseAnalysisJobPage({ jobs, limit, offset }, limit, offset),
      ),
      getAnalysisJob: vi.fn<PromptEnhancerTransport["getAnalysisJob"]>(async () => jobs[0] ?? original),
      cancelAnalysisJob,
    };
    const { container } = renderCentre(transport);

    await screen.findByText("1 on this page");
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    const detail = screen.getByRole("complementary", { name: "Selected job detail" });
    await within(detail).findByText(original.job_id);
    fireEvent.click(within(detail).getByRole("button", { name: "Cancel job" }));
    fireEvent.click(within(detail).getByRole("button", { name: "Confirm cancellation" }));
    await waitFor(() => expect(screen.queryByText(original.job_id)).not.toBeInTheDocument());

    jobs = [replacement];
    fireEvent.click(screen.getByRole("button", { name: "Refresh queue" }));
    await waitFor(() => expect(container.querySelectorAll("button.analysis-job-card")).toHaveLength(1));
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    expect(await within(detail).findByText(replacement.identity.session_id)).toBeVisible();
  });

  it.each([
    ["generic 404", new TransportError("Synthetic untyped cancel absence", 404)],
    ["generic 503", new TransportError("Synthetic cancel unavailable", 503)],
    ["503 with a not-found reason", new TransportError("Synthetic mismatched cancel absence", 503, "analysis_job_not_found")],
  ])("retains the receipt when cancellation receives a %s", async (_label, failure) => {
    const jobA = queuedJob(JOB_A_ID, "c".repeat(64));
    const cancelAnalysisJob = vi.fn<PromptEnhancerTransport["cancelAnalysisJob"]>(async () => { throw failure; });
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      listAnalysisJobs: vi.fn<PromptEnhancerTransport["listAnalysisJobs"]>(async (_state = null, limit = 25, offset = 0) => parseAnalysisJobPage({ jobs: [jobA], limit, offset }, limit, offset)),
      getAnalysisJob: vi.fn<PromptEnhancerTransport["getAnalysisJob"]>(async () => jobA),
      cancelAnalysisJob,
    };
    const { container } = renderCentre(transport);

    await screen.findByText("1 on this page");
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    const detail = screen.getByRole("complementary", { name: "Selected job detail" });
    await within(detail).findByText(jobA.job_id);
    fireEvent.click(within(detail).getByRole("button", { name: "Cancel job" }));
    fireEvent.click(within(detail).getByRole("button", { name: "Confirm cancellation" }));

    await waitFor(() => expect(cancelAnalysisJob).toHaveBeenCalledExactlyOnceWith(jobA.job_id, expect.any(AbortSignal)));
    expect(await within(detail).findByRole("alert")).toBeVisible();
    expect(within(detail).getByText(jobA.job_id)).toBeVisible();
    expect(container.querySelectorAll("button.analysis-job-card")).toHaveLength(1);
  });

  it("does not restore a retired job from list and detail reads that began before cancellation absence", async () => {
    const jobA = queuedJob(JOB_A_ID, "c".repeat(64));
    const jobB = queuedJob(JOB_B_ID, "d".repeat(64));
    const pendingList = deferred<AnalysisJobPage>();
    const pendingDetail = deferred<AnalysisJobRecord>();
    const pendingCancel = deferred<AnalysisJobRecord>();
    let jobs = [jobA, jobB];
    let listCalls = 0;
    const listAnalysisJobs = vi.fn<PromptEnhancerTransport["listAnalysisJobs"]>(async (_state = null, limit = 25, offset = 0) => {
      listCalls += 1;
      return listCalls === 1
        ? parseAnalysisJobPage({ jobs, limit, offset }, limit, offset)
        : pendingList.promise;
    });
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      listAnalysisJobs,
      getAnalysisJob: vi.fn<PromptEnhancerTransport["getAnalysisJob"]>(async (jobId) => jobId === jobA.job_id ? pendingDetail.promise : jobB),
      cancelAnalysisJob: vi.fn<PromptEnhancerTransport["cancelAnalysisJob"]>(() => pendingCancel.promise),
    };
    const { container } = renderCentre(transport);

    await screen.findByText("2 on this page");
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.analysis-job-card")!);
    const detail = screen.getByRole("complementary", { name: "Selected job detail" });
    fireEvent.click(within(detail).getByRole("button", { name: "Cancel job" }));
    fireEvent.click(within(detail).getByRole("button", { name: "Confirm cancellation" }));
    await waitFor(() => expect(transport.cancelAnalysisJob).toHaveBeenCalledExactlyOnceWith(jobA.job_id, expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole("button", { name: "Refresh queue" }));
    await waitFor(() => expect(listAnalysisJobs).toHaveBeenCalledTimes(2));
    await act(async () => {
      jobs = [jobB];
      pendingCancel.reject(new TransportError("Synthetic authoritative absence", 404, "analysis_job_not_found"));
      await pendingCancel.promise.catch(() => undefined);
    });
    await waitFor(() => expect(screen.queryByText(jobA.job_id)).not.toBeInTheDocument());

    await act(async () => {
      pendingList.resolve(parseAnalysisJobPage({ jobs: [jobA, jobB], limit: 25, offset: 0 }, 25, 0));
      pendingDetail.resolve(jobA);
      await Promise.all([pendingList.promise, pendingDetail.promise]);
    });
    expect(screen.queryByText(jobA.job_id)).not.toBeInTheDocument();
    expect(within(detail).getByRole("heading", { name: "Select a job" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Refresh queue" })).toBeEnabled();
  });
});

function renderCentre(transport: PromptEnhancerTransport) {
  return render(<AnalysisJobCentre runtimeMode="local_real" serviceState="available" transport={transport} />);
}

function jobTransport(
  initialJobs: AnalysisJobRecord[],
  getAnalysisJob: PromptEnhancerTransport["getAnalysisJob"],
): PromptEnhancerTransport {
  return {
    ...createSyntheticTransport(),
    listAnalysisJobs: vi.fn<PromptEnhancerTransport["listAnalysisJobs"]>(async (_state = null, limit = 25, offset = 0) =>
      parseAnalysisJobPage({ jobs: initialJobs, limit, offset }, limit, offset),
    ),
    getAnalysisJob,
    cancelAnalysisJob: vi.fn<PromptEnhancerTransport["cancelAnalysisJob"]>(),
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((accept, decline) => { resolve = accept; reject = decline; });
  return { promise, reject, resolve };
}

function queuedJob(
  jobId: string,
  sessionId: string,
  overrides: Partial<AnalysisJobRecord> = {},
): AnalysisJobRecord {
  const record = parseAnalysisJobRecord({
    job_id: jobId,
    identity: {
      kind: "synthetic_validation",
      provider: "synthetic",
      project_id: "e".repeat(64),
      session_id: sessionId,
      input_fingerprint: "f".repeat(64),
      provenance_fingerprint: "1".repeat(64),
      metric_keys: ["prompt.goal_definition", "prompt.task_definition"],
      estimator_plan_version: "synthetic-plan-v1",
      redactor_version: "synthetic-redactor-v1",
      provider_schema_version: "synthetic-schema-v1",
      automation_grant_id: null,
      local_only: true,
    },
    state: "queued",
    stage_number: null,
    progress_completed: 0,
    progress_total: 4,
    attempt_count: 0,
    max_attempts: 3,
    available_at: "2040-01-01T00:00:00Z",
    cancel_requested: false,
    last_error_code: null,
    terminal_reason_code: null,
    created_at: "2040-01-01T00:00:00Z",
    updated_at: "2040-01-01T00:00:00Z",
    terminal_at: null,
  }, jobId);
  return { ...record, ...overrides };
}
