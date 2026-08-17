import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  SYNTHETIC_CANDIDATES,
  SYNTHETIC_RUN,
  SYNTHETIC_TASKS,
} from "../../shared/api/syntheticFixtures";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { TaskFlowPage } from "./TaskFlowPage";
import { projectTaskFlow, taskFlowTimelineScale, timelinePosition } from "./taskFlowAdapter";
import { applyTaskFlowFilters, DEFAULT_TASK_FLOW_FILTERS } from "./taskFlowModel";

describe("projectTaskFlow", () => {
  it("keeps candidates and confirmed tasks distinct and places them by lifecycle", () => {
    const items = projectTaskFlow({ candidates: SYNTHETIC_CANDIDATES, tasks: SYNTHETIC_TASKS, runs: [SYNTHETIC_RUN] });
    expect(items.map((item) => [item.kind, item.column])).toEqual([
      ["candidate", "resolved"],
      ["confirmed", "analyzed"],
      ["candidate", "proposed"],
      ["candidate", "proposed"],
    ]);
    const proposed = items.filter((item) => item.column === "proposed");
    expect(proposed[0].lifecycle).toEqual({ source: "discovery_candidate", status: "undecided", label: "Proposed by discovery · needs review" });
    expect(proposed[0].readiness.state).toBe("ready");
    expect(proposed[0].provenance.version).toBe("synthetic.discovery.v1");
    expect(proposed[0].route).toEqual({ name: "discovery" });
    expect(proposed[1].readiness).toMatchObject({ state: "blocked", label: "No evidence observed" });
    expect(proposed[1].readiness.detail).toContain("confidence unknown");
    const decided = items.find((item) => item.column === "resolved")!;
    expect(decided.lifecycle.source).toBe("review_decision");
    expect(decided.lifecycle.status).toBe("accept");
    const analyzed = items.find((item) => item.kind === "confirmed")!;
    expect(analyzed.title).toBe("Feature Implementation · revision 1");
    expect(analyzed.lifecycle).toEqual({ source: "analysis_run", status: "completed", label: "Confirmed by review · analysis completed" });
    expect(analyzed.readiness.state).toBe("ready");
    expect(analyzed.provenance.origin).toBe("core.metadata.task");
    expect(analyzed.provenance.dataTier).toBe("metadata");
    expect(analyzed.endedAt).toBe(SYNTHETIC_RUN.finished_at);
    expect(analyzed.route).toEqual({ name: "task", taskId: SYNTHETIC_TASKS[0].task_id, revision: 1 });
    expect(analyzed.provider).toBeNull();
  });

  it("marks unanalyzed and failed revisions honestly", () => {
    const [task] = SYNTHETIC_TASKS;
    const [awaiting] = projectTaskFlow({ candidates: [], tasks: [task], runs: [] });
    expect(awaiting.column).toBe("confirmed");
    expect(awaiting.readiness).toMatchObject({ state: "partial", label: "Awaiting analysis" });
    expect(awaiting.lifecycle.source).toBe("task_revision");
    const [failed] = projectTaskFlow({ candidates: [], tasks: [task], runs: [{ ...SYNTHETIC_RUN, status: "failed", failure_code: "example_failure", finished_at: null }] });
    expect(failed.column).toBe("confirmed");
    expect(failed.readiness).toMatchObject({ state: "blocked", label: "Analysis failed" });
    expect(failed.readiness.detail).toContain("example_failure");
    expect(failed.endedAt).toBeNull();
  });

  it("ignores a run whose input fingerprint does not match the immutable task revision", () => {
    const [task] = SYNTHETIC_TASKS;
    const mismatchedRun = { ...SYNTHETIC_RUN, input_fingerprint: "f".repeat(64) };
    const [item] = projectTaskFlow({ candidates: [], tasks: [task], runs: [mismatchedRun] });
    expect(item.column).toBe("confirmed");
    expect(item.lifecycle.source).toBe("task_revision");
    expect(item.readiness.label).toBe("Awaiting analysis");
    expect(item.provenance.fingerprint).toBe(task.input_fingerprint);
  });

  it("filters both projections from one filter set", () => {
    const items = projectTaskFlow({ candidates: SYNTHETIC_CANDIDATES, tasks: SYNTHETIC_TASKS, runs: [SYNTHETIC_RUN] });
    expect(applyTaskFlowFilters(items, DEFAULT_TASK_FLOW_FILTERS)).toHaveLength(4);
    expect(applyTaskFlowFilters(items, { ...DEFAULT_TASK_FLOW_FILTERS, kind: "confirmed" })).toHaveLength(1);
    expect(applyTaskFlowFilters(items, { ...DEFAULT_TASK_FLOW_FILTERS, readiness: "blocked" })).toHaveLength(1);
    expect(applyTaskFlowFilters(items, { ...DEFAULT_TASK_FLOW_FILTERS, column: "resolved" })).toHaveLength(1);
    expect(applyTaskFlowFilters(items, { ...DEFAULT_TASK_FLOW_FILTERS, projectId: "0".repeat(64) })).toHaveLength(0);
  });

  it("builds a timeline scale from record timestamps only", () => {
    const items = projectTaskFlow({ candidates: SYNTHETIC_CANDIDATES, tasks: SYNTHETIC_TASKS, runs: [SYNTHETIC_RUN] });
    const scale = taskFlowTimelineScale(items)!;
    expect(scale.start).toBe(new Date("2040-01-01T14:00:00Z").getTime());
    expect(scale.end).toBe(new Date("2040-01-02T10:15:00Z").getTime());
    expect(scale.ticks).toHaveLength(5);
    expect(timelinePosition(scale, "2040-01-01T14:00:00Z")).toBe(0);
    expect(timelinePosition(scale, "2040-01-02T10:15:00Z")).toBe(1);
    expect(timelinePosition(scale, "not a date")).toBeNull();
    expect(taskFlowTimelineScale([])).toBeNull();
  });
});

describe("TaskFlowPage", () => {
  it("renders four fixed columns, filters, and a timeline with candidate and confirmed lanes", async () => {
    const navigate = vi.fn();
    render(<TaskFlowPage navigate={navigate} runtimeMode="synthetic_demo" transport={createSyntheticTransport()} />);
    const board = await screen.findByRole("group", { name: "Task flow board" });
    const columns = within(board).getAllByRole("region");
    expect(columns.map((column) => column.getAttribute("data-column"))).toEqual(["proposed", "confirmed", "analyzed", "resolved"]);
    expect(within(columns[0]).getAllByRole("article")).toHaveLength(2);
    expect(within(columns[1]).getByText(/Nothing in this column/)).toBeInTheDocument();
    expect(within(columns[2]).getAllByRole("article")).toHaveLength(1);
    expect(within(columns[3]).getAllByRole("article")).toHaveLength(1);
    expect(within(columns[0]).getAllByText("Candidate")).toHaveLength(2);
    expect(within(columns[2]).getByText("Confirmed task")).toBeInTheDocument();
    expect(within(columns[2]).getByText(/Provenance/)).toBeInTheDocument();
    expect(within(columns[2]).getByText(/Ready · Analysis completed/)).toBeInTheDocument();

    const timeline = screen.getByRole("region", { name: /Candidates \(proposed/ });
    expect(within(timeline).getAllByRole("button")).toHaveLength(3);
    expect(within(screen.getByRole("region", { name: /Confirmed tasks \(revisions/ })).getAllByRole("button")).toHaveLength(1);

    fireEvent.change(screen.getByRole("combobox", { name: "Kind" }), { target: { value: "confirmed" } });
    expect(within(columns[0]).queryAllByRole("article")).toHaveLength(0);
    expect(within(columns[2]).getAllByRole("article")).toHaveLength(1);
    expect(document.querySelector(".count-summary")?.textContent).toBe("0 candidates · 1 confirmed");
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(within(columns[0]).getAllByRole("article")).toHaveLength(2);

    fireEvent.click(within(columns[2]).getByRole("button", { name: /Open task/ }));
    expect(navigate).toHaveBeenCalledWith({ name: "task", taskId: SYNTHETIC_TASKS[0].task_id, revision: 1 });
    fireEvent.click(within(columns[0]).getAllByRole("button", { name: /Open in Discovery/ })[0]);
    expect(navigate).toHaveBeenCalledWith({ name: "discovery" });
  });
});
