import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ModelEnsembleAttemptStage, ModelEnsembleRun } from "../../shared/api/contracts";
import { ModelConstellationDrawer } from "./ModelConstellationDrawer";

function sealedRun(): ModelEnsembleRun {
  const stage = (modelKey: string, repositoryId: string, status: "completed" | "failed" = "completed") => ({
    model_key: modelKey,
    repository_id: repositoryId,
    revision: "a".repeat(40),
    status,
    error_code: status === "completed" ? null : "example_stage_failure",
    device: status === "completed" ? "cpu" : null,
    quantization: "none",
    inference_latency_ms: 12,
    peak_accelerator_memory_mb: null,
    process_rss_mb: 256,
    unloaded_after_stage: true,
  });
  return {
    run_id: "b".repeat(64),
    experts: [],
    predictive_model_stages: [
      stage("mdeberta_xnli", "example-org/mdeberta-xnli"),
      stage("multilingual_minilmv2_l6_nli", "example-org/multilingual-minilmv2-l6-nli", "failed"),
      stage("qwen3_4b_rubric", "example-org/qwen3-4b-rubric"),
    ],
  } as unknown as ModelEnsembleRun;
}

function attemptStages(): ModelEnsembleAttemptStage[] {
  return [{
    stage_ordinal: 0,
    stage_key: "mdeberta_xnli",
    state: "completed",
    model_key: "mdeberta_xnli",
    repository_id: "example-org/mdeberta-xnli",
    revision: "c".repeat(40),
    error_code: null,
    device: "cuda",
    quantization: "none",
    inference_latency_ms: 40,
    peak_accelerator_memory_mb: 1024,
    process_rss_mb: 1536,
    evaluated_case_count: 20,
    contributed_case_count: 0,
    unloaded_after_stage: true,
    completed_at: "2040-01-02T10:00:01Z",
  }, {
    stage_ordinal: 1,
    stage_key: "qwen3_4b_rubric",
    state: "cancelled",
    model_key: "qwen3_4b_rubric",
    repository_id: "example-org/qwen3-4b-rubric",
    revision: null,
    error_code: "analysis_cancelled",
    device: null,
    quantization: "bitsandbytes_nf4",
    inference_latency_ms: null,
    peak_accelerator_memory_mb: null,
    process_rss_mb: null,
    evaluated_case_count: null,
    contributed_case_count: null,
    unloaded_after_stage: null,
    completed_at: "2040-01-02T10:00:02Z",
  }];
}

describe("ModelConstellationDrawer", () => {
  it("states that model stages cannot author measured metric values", () => {
    render(<ModelConstellationDrawer attemptStages={[]} compact={false} run={sealedRun()} />);

    expect(screen.getByRole("note")).toHaveTextContent(
      /experimental evidence helpers, not metric authorities/i,
    );
    expect(screen.getByRole("note")).toHaveTextContent(
      /sealed measured publication.*never from model agreement/i,
    );
    expect(screen.getByText("Measured-metric authority").nextElementSibling)
      .toHaveTextContent("none");
  });

  it("groups sealed stages, keeps a single pressed node, and inspects receipts without inventing counts", () => {
    render(<ModelConstellationDrawer attemptStages={[]} compact={false} run={sealedRun()} />);
    expect(screen.getByText("Models").parentElement).toHaveTextContent("Sealed snapshot · 2/3 stages completed");
    fireEvent.click(screen.getByText("Models"));

    const factorGroup = screen.getByText("Factor models").closest("section")!;
    const deepGroup = screen.getByText("Deep judge").closest("section")!;
    expect(within(factorGroup).getAllByRole("button")).toHaveLength(2);
    expect(within(deepGroup).getAllByRole("button")).toHaveLength(1);
    expect(screen.queryByText("Challengers")).not.toBeInTheDocument();
    expect(screen.queryByText("Legacy stages")).not.toBeInTheDocument();

    const pressed = document.querySelectorAll('.model-constellation__nodes button[aria-pressed="true"]');
    expect(pressed).toHaveLength(1);
    expect(pressed[0]).toHaveTextContent("mdeberta-xnli");
    expect(document.querySelector('.model-constellation__nodes button[data-status="failed"]')).toHaveTextContent("failed");

    const inspector = document.querySelector(".model-constellation__inspector")!;
    expect(inspector).toHaveAttribute("aria-live", "polite");
    expect(within(inspector as HTMLElement).getByText("Peak VRAM").parentElement).toHaveTextContent("not recorded");
    expect(within(inspector as HTMLElement).getByText("Peak RAM").parentElement).toHaveTextContent("256 MiB");
    expect(within(inspector as HTMLElement).getByText("Experimental cases evaluated").parentElement).toHaveTextContent("unavailable");
    expect(within(inspector as HTMLElement).getByText("Experimental cases contributed").parentElement).toHaveTextContent("unavailable");
    expect(inspector).toHaveTextContent(/they are not zero/i);

    fireEvent.click(within(deepGroup).getByRole("button"));
    expect(document.querySelector(".model-constellation__inspector header")).toHaveTextContent("example-org/qwen3-4b-rubric");
    expect(document.querySelector(".model-constellation__inspector header")).toHaveTextContent("Selective disagreement adjudicator");
    expect(document.querySelectorAll('.model-constellation__nodes button[aria-pressed="true"]')).toHaveLength(1);
  });

  it("prefers latest-attempt rows, renders zero and null case counts differently, and omits memory in compact mode", () => {
    render(<ModelConstellationDrawer attemptStages={attemptStages()} compact={true} run={sealedRun()} />);
    expect(screen.getByText("Models").parentElement).toHaveTextContent("Latest attempt · 1/2 stages completed");
    fireEvent.click(screen.getByText("Models"));

    expect(screen.queryByText("Peak VRAM")).not.toBeInTheDocument();
    expect(screen.queryByText("Peak RAM")).not.toBeInTheDocument();
    expect(screen.getByText("Experimental cases evaluated").parentElement).toHaveTextContent("20");
    expect(screen.getByText("Experimental cases contributed").parentElement).toHaveTextContent("0");
    expect(screen.queryByText(/they are not zero/i)).not.toBeInTheDocument();

    fireEvent.click(document.querySelector('.model-constellation__nodes button[data-status="cancelled"]')!);
    expect(screen.getByRole("alert")).toHaveTextContent("analysis cancelled");
    expect(screen.getByText("Revision").parentElement).toHaveTextContent("not-recorded");
    expect(screen.getByText("Latency").parentElement).toHaveTextContent("not recorded");
    expect(screen.getByText("Released").parentElement).toHaveTextContent("not confirmed");
    expect(screen.getByText("Device").parentElement).toHaveTextContent("none");
    expect(screen.getByText("Quantization").parentElement).toHaveTextContent("bitsandbytes nf4");
    expect(screen.getByText("Experimental cases evaluated").parentElement).toHaveTextContent("unavailable");
    expect(screen.getByText(/they are not zero/i)).toBeInTheDocument();
  });

  it("supports arrow-key movement between stage nodes and states when receipts are not exposed", () => {
    const view = render(<ModelConstellationDrawer attemptStages={[]} compact={false} run={sealedRun()} />);
    fireEvent.click(screen.getByText("Models"));
    const factorNodes = screen.getByText("Factor models").closest("section")!.querySelector(".model-constellation__nodes")!;
    const [first, second] = [...factorNodes.querySelectorAll("button")];
    first.focus();
    fireEvent.keyDown(factorNodes, { key: "ArrowRight" });
    expect(second).toHaveFocus();
    fireEvent.keyDown(factorNodes, { key: "Home" });
    expect(first).toHaveFocus();
    view.unmount();

    render(<ModelConstellationDrawer attemptStages={[]} compact={false} run={null} />);
    expect(screen.getByText("Models").parentElement).toHaveTextContent("Stage receipts not exposed");
    fireEvent.click(screen.getByText("Models"));
    expect(screen.getByText(/not exposed for this sealed receipt/i)).toBeInTheDocument();
    expect(document.querySelector(".model-constellation__inspector")).toBeNull();
  });
});
