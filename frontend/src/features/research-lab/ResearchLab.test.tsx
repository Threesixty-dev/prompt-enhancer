import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ModelRuntimeInventory } from "../../shared/api/contracts";
import { ModelCompatibilityPayloadError } from "../../shared/api/modelCompatibilityContract";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { ResearchLab } from "./ResearchLab";

describe("ResearchLab", () => {
  it("shows a compact metric roadmap without reading sessions or activating models", async () => {
    const transport = createSyntheticTransport();
    const inventorySpy = vi.spyOn(transport, "getModelLabInventory");
    const catalogSpy = vi.spyOn(transport, "getTextAnalysisResearch");
    const sessionSpy = vi.spyOn(transport, "listCodexSessions");
    const analysisSpy = vi.spyOn(transport, "startSessionQualityAnalysis");

    render(<ResearchLab transport={transport} />);

    expect(await screen.findByRole("heading", { name: "Build useful metrics, then earn trust" })).toBeVisible();
    expect(screen.getByText("One profile, not one developer score")).toBeVisible();
    expect(screen.getByText("Task definition")).toBeVisible();
    expect(screen.getByText("Clarification value")).toBeVisible();
    expect(screen.getByText("0").closest("div")).toHaveTextContent("neural models activated");
    expect(catalogSpy).toHaveBeenCalledTimes(1);
    expect(sessionSpy).not.toHaveBeenCalled();
    expect(analysisSpy).not.toHaveBeenCalled();
    expect(inventorySpy).not.toHaveBeenCalled();
  });

  it("separates methods and candidate decisions into fast views", async () => {
    const transport = createSyntheticTransport();
    const modelStart = vi.spyOn(transport, "startTextModelEvaluation");
    const inventorySpy = vi.spyOn(transport, "getModelLabInventory");
    const compatibilitySpy = vi.spyOn(transport, "getTextModelCompatibility");
    const sessionSpy = vi.spyOn(transport, "listCodexSessions");
    render(<ResearchLab transport={transport} />);
    await screen.findByRole("heading", { name: "Build useful metrics, then earn trust" });

    fireEvent.click(screen.getByRole("tab", { name: "Method stack" }));
    expect(screen.getByRole("heading", { name: "Multilingual semantic retrieval" })).toBeVisible();
    expect(screen.getByText("Blocked by validation")).toBeVisible();

    fireEvent.click(screen.getByRole("tab", { name: "Model candidates" }));
    expect(screen.getByRole("heading", { name: "Multilingual E5 small" })).toBeVisible();
    expect(screen.getAllByText("Rejected by gate").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Product use is off").length).toBeGreaterThan(0);
    expect(await screen.findByRole("heading", { name: "Synthetic evaluation inventory" })).toBeVisible();
    expect(inventorySpy).toHaveBeenCalledTimes(1);
    const compatibilityTitle = await screen.findByRole("heading", { name: "Model compatibility" });
    const compatibilityPanel = compatibilityTitle.closest("section");
    expect(compatibilityPanel).not.toBeNull();
    const compatibility = within(compatibilityPanel!);
    expect(compatibility.getByRole("heading", { name: "Structured rubric" })).toBeVisible();
    expect(compatibility.getAllByText("Qwen3 4B rubric")).toHaveLength(2);
    expect(compatibility.getByText("Full-precision CUDA screen")).toBeVisible();
    expect(compatibility.getByText("NF4 disposable-child diagnostic")).toBeVisible();
    expect(compatibility.getByText("Documented approximate GPU peak 3.84 GiB; child memory not measured.")).toBeVisible();
    expect(compatibility.getAllByText("Research only").length).toBeGreaterThan(0);
    expect(compatibility.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(compatibility.queryByRole("button")).not.toBeInTheDocument();
    expect(compatibility.queryByText("qwen3_4b_rubric_bitsandbytes_nf4_child_v1")).not.toBeInTheDocument();
    expect(compatibility.queryByText("resource_measurement_missing")).not.toBeInTheDocument();
    expect(compatibilitySpy).toHaveBeenCalledTimes(1);
    expect((await screen.findAllByText("CUDA")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Test cached session models" }));
    expect(await screen.findByText("Screen complete")).toBeVisible();
    expect(screen.getAllByText(/Top1 Accuracy 75%/).length).toBeGreaterThan(0);
    expect(modelStart).toHaveBeenCalledWith(
      {
        candidate: "session-link",
        device: "auto",
        mode: "smoke",
        allow_download: false,
      },
    );
    expect(sessionSpy).not.toHaveBeenCalled();
  });

  it("fails closed when the catalog capability is absent", async () => {
    const transport = createSyntheticTransport();
    transport.getTextAnalysisResearch = undefined;
    render(<ResearchLab transport={transport} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The methods catalog is unavailable",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("No session was read");
  });

  const cudaInventoryCases = [
    {
      name: "unknown",
      expected: "CUDA status unknown",
      patch: {
        preferred_device: "cpu",
        cuda_state: "unknown",
        cuda_available: null,
        cuda_vram_bucket: null,
        cuda_capability_bucket: null,
        discovery_reason_codes: ["cuda_inventory_unknown"],
      },
    },
    {
      name: "unavailable",
      expected: "CUDA unavailable",
      patch: {
        preferred_device: "cpu",
        cuda_state: "unavailable",
        cuda_available: false,
        cuda_vram_bucket: null,
        cuda_capability_bucket: null,
        discovery_reason_codes: [],
      },
    },
    {
      name: "available",
      expected: "16 GiB class",
      patch: {},
    },
  ] satisfies Array<{
    name: string;
    expected: string;
    patch: Partial<ModelRuntimeInventory>;
  }>;

  it.each(cudaInventoryCases)("renders a human CUDA label when discovery is $name", async ({ expected, patch }) => {
    const transport = createSyntheticTransport();
    const base = await transport.getTextModelRuntime!();
    const compatibility = await transport.getTextModelCompatibility!();
    transport.getTextModelRuntime = vi.fn().mockResolvedValue({
      ...base,
      ...patch,
    } satisfies ModelRuntimeInventory);
    transport.getTextModelCompatibility = vi.fn().mockResolvedValue({
      ...compatibility,
      inventory: {
        ...compatibility.inventory,
        ...patch,
      } satisfies ModelRuntimeInventory,
    });

    render(<ResearchLab transport={transport} />);
    await screen.findByRole("heading", { name: "Build useful metrics, then earn trust" });
    fireEvent.click(screen.getByRole("tab", { name: "Model candidates" }));

    expect((await screen.findAllByText(expected)).length).toBeGreaterThan(0);
    expect(screen.queryByText("Not detected")).not.toBeInTheDocument();
    expect(screen.queryByText("16_gib_class")).not.toBeInTheDocument();
  });

  it("renders a fixed compatibility error without exposing response detail", async () => {
    const transport = createSyntheticTransport();
    transport.getTextModelCompatibility = vi.fn().mockRejectedValue(
      new Error("SYNTHETIC_PRIVATE_CANARY"),
    );

    render(<ResearchLab transport={transport} />);
    await screen.findByRole("heading", { name: "Build useful metrics, then earn trust" });
    fireEvent.click(screen.getByRole("tab", { name: "Model candidates" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Model compatibility is unavailable. No local model action was taken.",
    );
    expect(screen.queryByText("SYNTHETIC_PRIVATE_CANARY")).not.toBeInTheDocument();
  });

  it("renders no model rows when strict compatibility validation rejects the response", async () => {
    const transport = createSyntheticTransport();
    transport.getTextModelCompatibility = vi.fn().mockRejectedValue(
      new ModelCompatibilityPayloadError(),
    );

    render(<ResearchLab transport={transport} />);
    await screen.findByRole("heading", { name: "Build useful metrics, then earn trust" });
    fireEvent.click(screen.getByRole("tab", { name: "Model candidates" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Model compatibility is unavailable. No local model action was taken.",
    );
    expect(screen.queryByText("Qwen3 4B rubric")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Documented approximate GPU peak 3.84 GiB; child memory not measured."),
    ).not.toBeInTheDocument();
  });

  it("aborts compatibility discovery when the models view unmounts", async () => {
    const transport = createSyntheticTransport();
    let observedSignal: AbortSignal | undefined;
    transport.getTextModelCompatibility = vi.fn((signal) => {
      observedSignal = signal;
      return new Promise<never>(() => undefined);
    });

    const rendered = render(<ResearchLab transport={transport} />);
    await screen.findByRole("heading", { name: "Build useful metrics, then earn trust" });
    fireEvent.click(screen.getByRole("tab", { name: "Model candidates" }));
    expect(await screen.findByRole("heading", { name: "Model compatibility" })).toBeVisible();
    expect(observedSignal?.aborted).toBe(false);

    rendered.unmount();
    expect(observedSignal?.aborted).toBe(true);
  });
});
