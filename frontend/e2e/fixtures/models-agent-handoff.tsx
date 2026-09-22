import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "../../src/app/App";
import { createSyntheticTransport } from "../../src/shared/api/syntheticTransport";
import { createBrowserPlatform } from "../../src/shared/platform/browserPlatform";
import { createRuntimeComposition } from "../../src/shared/platform/runtimeMode";
import type { SyntheticRuntimeTransport } from "../../src/shared/platform/runtimeMode";
import type { LocalModelsOverview, LocalModelStatus, LocalRuntimeCoordinatorStatus } from "../../src/shared/api/contracts";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";

const COUNTER_NAMES = [
  "createAgentSession",
  "activateLocalModel",
  "switchLocalRuntime",
  "switchAgentSessionModel",
  "sendAgentMessage",
  "resumeAgentSession",
  "streamLocalModelChat",
  "streamAbort",
] as const;

const counters = Object.fromEntries(COUNTER_NAMES.map((name) => [name, 0])) as Record<typeof COUNTER_NAMES[number], number>;
const publishCounters = () => {
  for (const name of COUNTER_NAMES) {
    document.documentElement.setAttribute(`data-handoff-${name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`, String(counters[name]));
  }
};

const model: LocalModelStatus = {
  record: { alias: "example-small-cpu", display_name: "Example Small CPU", path: "D:/example/models/example.gguf", added_at: "2040-01-01T00:00:00Z", context_size: 4096, default_device: "cpu", format: "gguf", provenance_verified: false },
  runtime: { state: "running", device: "cpu" },
  endpoint_path: "/v1/local-models/example-small-cpu/chat/completions",
  placement: { contract_version: "local-model-placement.v1", alias: "example-small-cpu", context_size: 4096, gpu_memory_free_mb: 12000, actual_offload_verified: false, options: [
    { device: "gpu", state: "available", reason_code: "gpu_estimate_fits", recommended_gpu_layers: 8, estimated_vram_required_mb: 6000 },
    { device: "split", state: "available", reason_code: "split_estimate_available", recommended_gpu_layers: 6, estimated_vram_required_mb: 5000 },
    { device: "cpu", state: "available", reason_code: "cpu_available", recommended_gpu_layers: 0, estimated_vram_required_mb: 0 },
  ] },
};
const overview: LocalModelsOverview = {
  contract_version: "local-models.v1", runtime_available: true, storage_root: "D:/example/models", storage_free_bytes: 64 * 1024 ** 3,
  download_reserve_bytes: 512 * 1024 ** 2, download_ledger_error_code: null, models: [model], downloads: [],
  hardware: { gpu_name: "Synthetic GPU", gpu_memory_mb: 16000, gpu_memory_free_mb: 12000, ram_mb: 32000, llama_server_path: "D:/example/runtime/llama-server.exe", llama_server_version: "example-v1" },
};
const base = createSyntheticTransport();
const coordinator: LocalRuntimeCoordinatorStatus = {
  contract_version: "local-runtime-coordinator.v2",
  revision: 7,
  state: "ready",
  requested: { alias: model.record.alias, device: "cpu", gpu_layers: 0, context_size: model.record.context_size },
  served: { alias: model.record.alias, device: "cpu", gpu_layers: 0, context_size: model.record.context_size, pid: 4242, started_at: "2040-01-01T00:00:00Z" },
  active_requests: 0,
  cleanup: { state: "not_required", process_exit_confirmed: true, gpu_memory_free_before_mb: null, gpu_memory_free_after_mb: null, gpu_memory_released_mb: null },
  capabilities: { probe_version: "local-runtime-multimodal-probe.v2", state: "verified", text: true, tools: true, structured_output: false, vision: false, audio: false, recording: false, error_code: null },
  context: { state: "unknown", used_tokens: null, limit_tokens: model.record.context_size, requested_output_tokens: null, available_output_tokens: null, source: "runtime_limit_only", scope: "runtime_limit", policy: "runtime_enforced", compacted_messages: 0, reason_code: "no_request_measured" },
  last_error_code: null,
};
window.history.replaceState(null, "", "/models");
const count = (name: typeof COUNTER_NAMES[number]) => {
  counters[name] += 1;
  publishCounters();
};
const stableTransport: SyntheticRuntimeTransport = {
  ...base,
  getLocalModels: async () => overview,
  getLocalRuntime: async () => coordinator,
  listAgentSessions: async () => [],
  listAgentProjects: async () => ({ contract_version: "agent-catalog.v2", projects: [] }),
  listAgentCatalogSessions: async () => ({ contract_version: "agent-catalog.v2", sessions: [] }),
  createAgentSession: async (settings, signal) => {
    count("createAgentSession");
    return base.createAgentSession(settings, signal);
  },
  activateLocalModel: async (alias, request, signal) => {
    count("activateLocalModel");
    return base.activateLocalModel(alias, request, signal);
  },
  switchLocalRuntime: async () => {
    count("switchLocalRuntime");
    return coordinator;
  },
  switchAgentSessionModel: async (sessionId, request, signal) => {
    count("switchAgentSessionModel");
    return base.switchAgentSessionModel(sessionId, request, signal);
  },
  sendAgentMessage: async (sessionId, text, attachmentIds, signal) => {
    count("sendAgentMessage");
    return base.sendAgentMessage(sessionId, text, attachmentIds, signal);
  },
  resumeAgentSession: async (projectId, sessionId, request, signal) => {
    count("resumeAgentSession");
    return base.resumeAgentSession(projectId, sessionId, request, signal);
  },
  streamLocalModelChat: async (_alias, _request, onDelta, signal) => {
    count("streamLocalModelChat");
    onDelta({ content: "Synthetic temporary reply." });
    return await new Promise<{ content: string; reasoning: string; elapsed_ms: number; finish_reason: "stop" }>((resolve) => {
      const finish = () => resolve({ content: "Synthetic temporary reply.", reasoning: "", elapsed_ms: 1, finish_reason: "stop" });
      if (signal?.aborted) finish();
      else signal?.addEventListener("abort", () => { count("streamAbort"); finish(); }, { once: true });
    });
  },
};
/* The explicit fixture transport is intentionally synthetic and never reaches a provider. */

publishCounters();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App
      platform={createBrowserPlatform()}
      runtime={createRuntimeComposition("synthetic_demo", stableTransport)}
    />
  </StrictMode>,
);
