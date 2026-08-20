import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { LocalModelRecord, LocalModelStatus, LocalModelsOverview, RemoteRepoFiles } from "../../shared/api/contracts";
import { LocalModelsPage, provenanceLine, safeOverview } from "./LocalModelsPage";

const REVISION = "0123456789abcdef0123456789abcdef01234567";
const DIGEST = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

function model(state: LocalModelStatus["runtime"]["state"] = "stopped"): LocalModelStatus {
  return {
    record: {
      alias: "qwen-27b-q4", display_name: "Qwen 27B Q4", format: "gguf", path: "D:/models/qwen.gguf",
      source_repo: "example-org/Example-GGUF", source_file: "qwen-q4_k_m.gguf", size_bytes: 16 * 1024 ** 3,
      sha256: null, source_revision: null, source_license: null, source_license_policy: null, provenance_verified: false,
      default_device: "split", default_gpu_layers: null, context_size: 8192, layer_count: 64, added_at: "2026-03-04T09:00:00Z",
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

function remoteFiles(overrides: Partial<RemoteRepoFiles> = {}): RemoteRepoFiles {
  return {
    repo_id: "example-org/Example-GGUF",
    revision: REVISION,
    revision_pinned: true,
    license_id: "apache-2.0",
    license_admission: "allowed",
    license_policy_version: "local-model-license-policy.v1",
    gated: false,
    unavailable_reason: null,
    files: [
      { filename: "qwen-q4_k_m.gguf", size_bytes: 16 * 1024 ** 3, sha256: DIGEST, eligible: true, ineligible_reason: null },
      { filename: "qwen-q8_0.gguf", size_bytes: 28 * 1024 ** 3, sha256: null, eligible: false, ineligible_reason: "digest_unavailable" },
    ],
    ...overrides,
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
      getLocalModelRemoteFiles: vi.fn(async () => remoteFiles()),
      startLocalModelDownload: vi.fn(),
      addLocalModel: vi.fn(),
      streamLocalModelChat: vi.fn(),
    };
    render(<LocalModelsPage transport={transport} />);
    await screen.findByText("Example GPU");
    expect(screen.getByText("Qwen 27B Q4")).toBeTruthy();
    expect(screen.getByText("POST /v1/local-models/qwen-27b-q4/chat/completions")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Device for Qwen 27B Q4").querySelector("input[value='gpu']") as HTMLInputElement);
    fireEvent.click(screen.getByRole("button", { name: "Activate" }));
    await waitFor(() => expect(activateLocalModel).toHaveBeenCalledWith("qwen-27b-q4", { device: "gpu", remember: true, fast_attention: true, tool_calling: true }));
    await screen.findByText(/running · split · 52 GPU layers/);

    // Adding from Hugging Face shows sizes and picks the 4-bit file by default.
    fireEvent.click(screen.getByRole("button", { name: "Show files" }));
    await screen.findByLabelText("Model file");
    expect((screen.getByLabelText("Model file") as HTMLSelectElement).value).toBe("qwen-q4_k_m.gguf");
    expect(screen.getByRole("button", { name: /Download 16.0 GB/ })).toBeTruthy();
    // The immutable revision, digest and licence the person is confirming are all on screen.
    expect(screen.getByText(REVISION)).toBeTruthy();
    expect(screen.getByText(new RegExp(DIGEST))).toBeTruthy();
    expect(screen.getByText(/apache-2\.0 . admitted by this app's frozen download policy/)).toBeTruthy();
    // An installed model with nothing verified says so instead of implying safety.
    expect(screen.getByText(/Provenance unavailable/)).toBeTruthy();
  });

  it("passes the displayed revision, digest and licence back as the confirmation", async () => {
    const startLocalModelDownload = vi.fn(async () => ({}) as never);
    const transport = {
      getLocalModels: vi.fn(async () => overview()),
      activateLocalModel: vi.fn(), deactivateLocalModel: vi.fn(), removeLocalModel: vi.fn(),
      getLocalModelRemoteFiles: vi.fn(async () => remoteFiles()),
      startLocalModelDownload, addLocalModel: vi.fn(), streamLocalModelChat: vi.fn(),
    };
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<LocalModelsPage transport={transport} />);
    await screen.findByText("Example GPU");
    fireEvent.click(screen.getByRole("button", { name: "Show files" }));
    await screen.findByLabelText("Model file");
    fireEvent.click(screen.getByRole("button", { name: /Download 16.0 GB/ }));
    await waitFor(() => expect(startLocalModelDownload).toHaveBeenCalledTimes(1));
    expect(startLocalModelDownload.mock.calls[0][0]).toEqual({
      repo_id: "example-org/Example-GGUF",
      filename: "qwen-q4_k_m.gguf",
      confirmed_size_bytes: 16 * 1024 ** 3,
      confirmed_revision: REVISION,
      confirmed_sha256: DIGEST,
      confirmed_license: "apache-2.0",
      alias: "qwen-q4_k_m",
      default_device: "split",
    });
    expect(confirm.mock.calls[0][0]).toContain(REVISION);
    expect(confirm.mock.calls[0][0]).toContain(DIGEST);
    expect(confirm.mock.calls[0][0]).toContain("apache-2.0");
    confirm.mockRestore();
  });

  it("refuses to offer a download when the licence is not admitted", async () => {
    const transport = {
      getLocalModels: vi.fn(async () => overview()),
      activateLocalModel: vi.fn(), deactivateLocalModel: vi.fn(), removeLocalModel: vi.fn(),
      getLocalModelRemoteFiles: vi.fn(async () => remoteFiles({ license_id: "example-community-1.0", license_admission: "unreviewed" })),
      startLocalModelDownload: vi.fn(), addLocalModel: vi.fn(), streamLocalModelChat: vi.fn(),
    };
    render(<LocalModelsPage transport={transport} />);
    await screen.findByText("Example GPU");
    fireEvent.click(screen.getByRole("button", { name: "Show files" }));
    await screen.findByLabelText("Model file");
    const button = screen.getByRole("button", { name: "Download unavailable" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it("keeps gated repositories on the manual registration path", async () => {
    const transport = {
      getLocalModels: vi.fn(async () => overview()),
      activateLocalModel: vi.fn(), deactivateLocalModel: vi.fn(), removeLocalModel: vi.fn(),
      getLocalModelRemoteFiles: vi.fn(async () => remoteFiles({
        gated: true,
        files: [{ filename: "qwen-q4_k_m.gguf", size_bytes: 16 * 1024 ** 3, sha256: DIGEST, eligible: false, ineligible_reason: "repository_gated" }],
      })),
      startLocalModelDownload: vi.fn(), addLocalModel: vi.fn(), streamLocalModelChat: vi.fn(),
    };
    render(<LocalModelsPage transport={transport} />);
    await screen.findByText("Example GPU");
    fireEvent.click(screen.getByRole("button", { name: "Show files" }));
    await screen.findByText(/automated downloader is public-only/);
    expect((screen.getByRole("button", { name: "Download unavailable" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/cached Hugging Face login/)).toBeTruthy();
  });

  it("shows a repository that cannot be pinned as undownloadable", async () => {
    const transport = {
      getLocalModels: vi.fn(async () => overview()),
      activateLocalModel: vi.fn(), deactivateLocalModel: vi.fn(), removeLocalModel: vi.fn(),
      getLocalModelRemoteFiles: vi.fn(async () => remoteFiles({
        revision: null, revision_pinned: false, license_id: null, license_admission: "unavailable",
        unavailable_reason: "revision_not_immutable", files: [],
      })),
      startLocalModelDownload: vi.fn(), addLocalModel: vi.fn(), streamLocalModelChat: vi.fn(),
    };
    render(<LocalModelsPage transport={transport} />);
    await screen.findByText("Example GPU");
    fireEvent.click(screen.getByRole("button", { name: "Show files" }));
    await screen.findByText(/did not name an immutable commit/);
    expect(screen.queryByLabelText("Model file")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Download/ })).toBeNull();
  });

  it("never claims provenance it does not have", () => {
    const base = model().record;
    expect(provenanceLine(base)).toMatch(/Provenance unavailable/);
    // A record carrying a digest but no verification is still unavailable, never "verified".
    expect(provenanceLine({ ...base, sha256: DIGEST, source_revision: REVISION } as LocalModelRecord)).toMatch(/Provenance unavailable/);
    const verified = { ...base, sha256: DIGEST, source_revision: REVISION, source_license: "apache-2.0", source_license_policy: "local-model-license-policy.v1", provenance_verified: true } as LocalModelRecord;
    expect(provenanceLine(verified)).toBe("Verified when downloaded · revision 0123456789ab · sha256 0123456789ab · licence apache-2.0 · policy local-model-license-policy.v1");
  });

  it("explains a missing runtime", async () => {
    const transport = {
      getLocalModels: vi.fn(async () => overview([], false)),
      activateLocalModel: vi.fn(), deactivateLocalModel: vi.fn(), removeLocalModel: vi.fn(),
      getLocalModelRemoteFiles: vi.fn(), startLocalModelDownload: vi.fn(), addLocalModel: vi.fn(), streamLocalModelChat: vi.fn(),
    };
    render(<LocalModelsPage transport={transport} />);
    await screen.findByText(/llama.cpp is not installed/);
    expect(screen.getByText(/No model yet/)).toBeTruthy();
    expect(screen.getByText(/Activate a model above to chat/)).toBeTruthy();
  });

  it("streams a chat reply from the running model with thinking off by default", async () => {
    const streamLocalModelChat = vi.fn(
      async (
        _alias: string,
        _request: { messages: { role: string; content: string }[]; enable_thinking?: boolean },
        onDelta: (delta: { content?: string; reasoning?: string }) => void,
      ) => {
        onDelta({ content: "feat: " });
        onDelta({ content: "add chat" });
        return { content: "feat: add chat", reasoning: "", finish_reason: "stop", elapsed_ms: 1200 };
      },
    );
    const transport = {
      getLocalModels: vi.fn(async () => overview([model("running")])),
      activateLocalModel: vi.fn(), deactivateLocalModel: vi.fn(), removeLocalModel: vi.fn(),
      getLocalModelRemoteFiles: vi.fn(), startLocalModelDownload: vi.fn(), addLocalModel: vi.fn(),
      streamLocalModelChat,
    };
    render(<LocalModelsPage transport={transport} />);
    await screen.findByLabelText("Chat model");
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Write a commit message" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("feat: add chat");
    expect(streamLocalModelChat).toHaveBeenCalledTimes(1);
    const [alias, request] = streamLocalModelChat.mock.calls[0];
    expect(alias).toBe("qwen-27b-q4");
    expect(request.enable_thinking).toBe(false);
    expect(request.messages).toEqual([{ role: "user", content: "Write a commit message" }]);
    expect(screen.getByText(/1\.2 s/)).toBeTruthy();
    expect(screen.getAllByText(/\/v1\/local-models\/qwen-27b-q4\/v1/).length).toBeGreaterThanOrEqual(2);
  });
});
