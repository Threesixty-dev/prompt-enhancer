import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { LocalModelStatus, LocalModelsOverview } from "../../shared/api/contracts";
import { LocalModelsPage, safeOverview } from "./LocalModelsPage";

function model(state: LocalModelStatus["runtime"]["state"] = "stopped"): LocalModelStatus {
  return {
    record: {
      alias: "qwen-27b-q4", display_name: "Qwen 27B Q4", format: "gguf", path: "D:/models/qwen.gguf",
      source_repo: "example-org/Example-GGUF", source_file: "qwen-q4_k_m.gguf", size_bytes: 16 * 1024 ** 3,
      sha256: null, default_device: "split", context_size: 8192, layer_count: 64, added_at: "2026-03-04T09:00:00Z",
    },
    runtime: { state, device: state === "running" ? "split" : null, gpu_layers: state === "running" ? 52 : null, context_size: state === "running" ? 8192 : null, started_at: null, last_error_code: null, pid: null },
    endpoint_path: "/v1/local-models/qwen-27b-q4/chat/completions",
  };
}

function overview(models: LocalModelStatus[] = [model()], runtime = true): LocalModelsOverview {
  return {
    contract_version: "local-models.v1" as const,
    hardware: { gpu_name: "Example GPU", gpu_memory_mb: 16384, gpu_memory_free_mb: 15000, ram_mb: 32768, llama_server_path: runtime ? "C:/tools/llama-server.exe" : null, llama_server_version: runtime ? "b1234" : null },
    runtime_available: runtime,
    storage_root: "D:/example/local-models",
    models,
    downloads: [],
  };
}

describe("LocalModelsPage", () => {
  it("validates the overview contract", () => {
    expect(safeOverview(overview())).toBe(true);
    expect(safeOverview({ contract_version: "other" })).toBe(false);
  });

  it("shows hardware, the model with its endpoint, and activates on the chosen device", async () => {
    let current = overview();
    const activateLocalModel = vi.fn(async (_alias: string, _request: { device?: "cpu" | "gpu" | "split" | null }) => {
      current = overview([model("running")]);
      return model("running");
    });
    const transport = {
      getLocalModels: vi.fn(async () => current),
      activateLocalModel,
      deactivateLocalModel: vi.fn(async () => model()),
      removeLocalModel: vi.fn(async () => undefined),
      getLocalModelRemoteFiles: vi.fn(async () => ({ repo_id: "example-org/Example-GGUF", gated: true, files: [{ filename: "qwen-q4_k_m.gguf", size_bytes: 16 * 1024 ** 3 }, { filename: "qwen-q8_0.gguf", size_bytes: 28 * 1024 ** 3 }] })),
      startLocalModelDownload: vi.fn(),
      addLocalModel: vi.fn(),
    };
    render(<LocalModelsPage transport={transport} />);
    await screen.findByText("Example GPU");
    expect(screen.getByText("Qwen 27B Q4")).toBeTruthy();
    expect(screen.getByText("POST /v1/local-models/qwen-27b-q4/chat/completions")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Device for Qwen 27B Q4").querySelector("input[value='gpu']") as HTMLInputElement);
    fireEvent.click(screen.getByRole("button", { name: "Activate" }));
    await waitFor(() => expect(activateLocalModel).toHaveBeenCalledWith("qwen-27b-q4", { device: "gpu" }));
    await screen.findByText(/running · split · 52 GPU layers/);

    // Adding from Hugging Face shows sizes and picks the 4-bit file by default.
    fireEvent.click(screen.getByRole("button", { name: "Show files" }));
    await screen.findByLabelText("Model file");
    expect((screen.getByLabelText("Model file") as HTMLSelectElement).value).toBe("qwen-q4_k_m.gguf");
    expect(screen.getByRole("button", { name: /Download 16.0 GB/ })).toBeTruthy();
    expect(screen.getByText(/This repository is gated/)).toBeTruthy();
  });

  it("explains a missing runtime", async () => {
    const transport = {
      getLocalModels: vi.fn(async () => overview([], false)),
      activateLocalModel: vi.fn(), deactivateLocalModel: vi.fn(), removeLocalModel: vi.fn(),
      getLocalModelRemoteFiles: vi.fn(), startLocalModelDownload: vi.fn(), addLocalModel: vi.fn(),
    };
    render(<LocalModelsPage transport={transport} />);
    await screen.findByText(/llama.cpp is not installed/);
    expect(screen.getByText(/No model yet/)).toBeTruthy();
  });
});
