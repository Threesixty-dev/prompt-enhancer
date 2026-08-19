import { useCallback, useEffect, useState } from "react";
import type {
  DeviceMode,
  LocalModelStatus,
  LocalModelsOverview,
  PromptEnhancerTransport,
  RemoteRepoFiles,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { Icon } from "../../shared/ui/Icon";
import { LocalModelChatPanel } from "./LocalModelChatPanel";
import "./LocalModelsPage.css";

const RECOMMENDED_REPO = "mradermacher/Qwen3.8-27B-Uncensored-FP8-i1-GGUF";
/** Verified on 2026-08-19: ungated imatrix quantizations of orcarouter's unrestricted Qwen3.8-27B; the first fits a 16 GB card entirely. */
const RECOMMENDED: readonly { repo: string; file: string; alias: string; label: string; note: string; sizeGb: number; device: DeviceMode }[] = [
  { repo: "mradermacher/Qwen3.8-27B-Uncensored-FP8-i1-GGUF", file: "Qwen3.8-27B-Uncensored-FP8.i1-IQ3_M.gguf", alias: "orca27b-iq3m", label: "Qwen3.8-27B uncensored · IQ3_M", note: "12.8 GB - fully on a 16 GB GPU, ~25 tok/s; the default judge and agent model", sizeGb: 12.8, device: "gpu" },
  { repo: "mradermacher/Qwen3.8-27B-Uncensored-FP8-i1-GGUF", file: "Qwen3.8-27B-Uncensored-FP8.i1-IQ4_XS.gguf", alias: "orca27b-iq4xs", label: "Qwen3.8-27B uncensored · IQ4_XS", note: "15.3 GB - higher quality, needs a GPU/CPU split on 16 GB", sizeGb: 15.3, device: "split" },
  { repo: "mradermacher/Qwen3.8-27B-Uncensored-FP8-i1-GGUF", file: "Qwen3.8-27B-Uncensored-FP8.i1-Q4_K_M.gguf", alias: "orca27b-q4km", label: "Qwen3.8-27B uncensored · Q4_K_M", note: "16.8 GB - best quality of the three, split 62/65 layers ~14 tok/s", sizeGb: 16.8, device: "split" },
];
const DEVICES: readonly { value: DeviceMode; title: string; hint: string }[] = [
  { value: "gpu", title: "GPU", hint: "All layers on the GPU - only if the weights fit" },
  { value: "split", title: "GPU / CPU", hint: "Fits what it can on the GPU, rest on CPU" },
  { value: "cpu", title: "CPU", hint: "No offload; slow but always works" },
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function safeOverview(value: unknown): value is LocalModelsOverview {
  return isRecord(value) && value.contract_version === "local-models.v1" && Array.isArray(value.models) && isRecord(value.hardware);
}

function gb(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "unknown size";
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function mb(value: number | null | undefined): string {
  if (value === null || value === undefined) return "unknown";
  return `${(value / 1024).toFixed(1)} GB`;
}

function defaultAlias(filename: string): string {
  return filename.toLowerCase().replace(/\.gguf$/, "").replace(/[^a-z0-9._-]+/g, "-").replace(/^[^a-z0-9]+/, "").slice(0, 60) || "model";
}

/**
 * Installed local models: hardware, runtime detection, per-model device
 * activation and the loopback endpoint each model gets. Adding a model from
 * Hugging Face shows file sizes first and downloads only after a confirmation.
 */
export function LocalModelsPage({
  transport,
}: {
  transport: Pick<
    PromptEnhancerTransport,
    "getLocalModels" | "activateLocalModel" | "deactivateLocalModel" | "removeLocalModel" | "getLocalModelRemoteFiles" | "startLocalModelDownload" | "addLocalModel" | "streamLocalModelChat"
  > & Partial<Pick<PromptEnhancerTransport, "scanLocalModelFolder">>;
}) {
  const [overview, setOverview] = useState<LocalModelsOverview | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "unavailable" | "error">("loading");
  const [busy, setBusy] = useState<string>("");
  const [message, setMessage] = useState<string>("");
  const [devices, setDevices] = useState<Record<string, DeviceMode>>({});
  const [layers, setLayers] = useState<Record<string, string>>({});
  const [repoId, setRepoId] = useState(RECOMMENDED_REPO);
  const [remote, setRemote] = useState<RemoteRepoFiles | null>(null);
  const [remoteError, setRemoteError] = useState("");
  const [chosenFile, setChosenFile] = useState<string>("");
  const [alias, setAlias] = useState<string>("");
  const [localPath, setLocalPath] = useState<string>("");
  const [folderPath, setFolderPath] = useState<string>("");

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const value = await transport.getLocalModels(signal);
      if (signal?.aborted) return;
      if (!safeOverview(value)) { setState("error"); return; }
      setOverview(value);
      setState("ready");
    } catch (caught) {
      if (signal?.aborted) return;
      setState(caught instanceof TransportError && caught.status === 404 ? "unavailable" : "error");
    }
  }, [transport]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const handle = window.setInterval(() => void load(controller.signal), 5000);
    return () => { controller.abort(); window.clearInterval(handle); };
  }, [load]);

  async function run(label: string, action: () => Promise<unknown>, okMessage: string | null) {
    setBusy(label);
    setMessage("");
    try {
      await action();
      if (okMessage) setMessage(okMessage);
      await load();
    } catch (caught) {
      const status = caught instanceof TransportError ? caught.status : null;
      setMessage(status === 409 && label !== "download"
        ? "llama-server is not installed or not on PATH (or that alias already exists); see the runtime card."
        : status === 502
          ? "The runtime started but never became healthy - try fewer GPU layers or CPU."
          : status === 422
            ? "That is not a usable GGUF file or folder."
            : status === 409 ? "Hugging Face refused the download: accept the model's terms on its page while logged in, then retry."
              : "That did not work. Nothing was changed.");
    } finally {
      setBusy("");
    }
  }

  async function lookupRemote() {
    setRemoteError("");
    setRemote(null);
    setChosenFile("");
    try {
      const files = await transport.getLocalModelRemoteFiles(repoId.trim());
      setRemote(files);
      const fourBit = files.files.find((f) => /q4_k_m/i.test(f.filename)) ?? files.files.find((f) => /iq4|q4/i.test(f.filename)) ?? files.files[0];
      if (fourBit) { setChosenFile(fourBit.filename); setAlias(defaultAlias(fourBit.filename)); }
    } catch (caught) {
      setRemoteError(caught instanceof TransportError && caught.status === 409
        ? "huggingface_hub is not installed in this environment (pip install -e \".[models]\")."
        : "The repository could not be read. Check the id, or accept its terms on Hugging Face while logged in.");
    }
  }

  const selectedRemote = remote?.files.find((f) => f.filename === chosenFile) ?? null;

  if (state === "loading") return <section className="local-models"><p className="local-models__note">Looking at this machine…</p></section>;
  if (state === "unavailable") return <section className="local-models"><p className="local-models__note">Local models are not available in this runtime.</p></section>;
  if (state === "error" || !overview) return <section className="local-models"><p className="local-models__note" role="alert">The model list could not be verified.</p></section>;

  const hw = overview.hardware;
  return (
    <section aria-labelledby="local-models-title" className="local-models">
      <header className="local-models__head">
        <div>
          <p className="eyebrow">Local models · on this machine only</p>
          <h1 id="local-models-title">Models</h1>
          <p className="local-models__lede">
            Install a model once, activate it on the GPU, CPU, or split between them, and it gets its own local
            endpoint: usable as a regular LLM for small tasks and by the metric judge. Nothing leaves this machine.
          </p>
        </div>
      </header>

      <div className="local-models__grid">
        <article className="local-models__card">
          <h2>Hardware</h2>
          <dl>
            <div><dt>GPU</dt><dd>{hw.gpu_name ?? "none detected"}</dd></div>
            <div><dt>VRAM</dt><dd>{hw.gpu_memory_mb ? `${mb(hw.gpu_memory_free_mb)} free of ${mb(hw.gpu_memory_mb)}` : "—"}</dd></div>
            <div><dt>RAM</dt><dd>{mb(hw.ram_mb)}</dd></div>
          </dl>
          <p className="local-models__hint">
            A 27B model at 4-bit is about 16 GB of weights: use <strong>GPU / CPU</strong> on a 16 GB card; the app estimates how many layers fit and you can override it.
          </p>
          <p className="local-models__hint">Storage: <code>{overview.storage_root}</code> (set <code>PROMPT_ENHANCER_LOCAL_MODELS_DIR</code> or the <code>local-models.path</code> file in the app home to keep weights on another drive).</p>
        </article>
        <article className="local-models__card" data-state={overview.runtime_available ? "ok" : "missing"}>
          <h2>Runtime</h2>
          {overview.runtime_available ? (
            <dl>
              <div><dt>llama-server</dt><dd><code>{hw.llama_server_path}</code></dd></div>
              <div><dt>Version</dt><dd>{hw.llama_server_version ?? "unknown"}</dd></div>
            </dl>
          ) : (
            <>
              <p><strong>llama.cpp is not installed</strong> (no <code>llama-server</code> on PATH).</p>
              <p className="local-models__hint">
                Install the official llama.cpp release for Windows with CUDA, then either put <code>llama-server.exe</code> on your PATH or set
                <code> PROMPT_ENHANCER_LLAMA_SERVER</code> to its full path and restart the app. The app never downloads or runs a binary on its own.
              </p>
            </>
          )}
        </article>
      </div>

      <section aria-labelledby="installed-models-title" className="local-models__section">
        <h2 id="installed-models-title">Installed models</h2>
        {overview.models.length === 0 && <p className="local-models__note">No model yet. Add one below.</p>}
        <ul className="local-models__list">
          {overview.models.map((item: LocalModelStatus) => {
            const device = devices[item.record.alias] ?? item.record.default_device;
            const running = item.runtime.state === "running";
            return (
              <li key={item.record.alias} className="local-models__model" data-state={item.runtime.state}>
                <div className="local-models__model-head">
                  <div>
                    <strong>{item.record.display_name}</strong>
                    <small>{item.record.alias} · {gb(item.record.size_bytes)}{item.record.source_repo ? ` · ${item.record.source_repo}` : ""}</small>
                  </div>
                  <span className={`local-models__state local-models__state--${item.runtime.state}`}>
                    {item.runtime.state}{item.runtime.device ? ` · ${item.runtime.device}${item.runtime.gpu_layers !== null && item.runtime.gpu_layers !== undefined ? ` · ${item.runtime.gpu_layers} GPU layers` : ""}` : ""}
                  </span>
                </div>
                <div className="local-models__device" role="radiogroup" aria-label={`Device for ${item.record.display_name}`}>
                  {DEVICES.map((option) => (
                    <label key={option.value} className={device === option.value ? "is-chosen" : ""} title={option.hint}>
                      <input checked={device === option.value} name={`device-${item.record.alias}`} onChange={() => setDevices((prev) => ({ ...prev, [item.record.alias]: option.value }))} type="radio" value={option.value} />
                      <span>{option.title}</span>
                    </label>
                  ))}
                </div>
                {device === "split" && (
                  <label className="local-models__layers">
                    <span>GPU layers{item.record.layer_count ? ` of ${item.record.layer_count}` : ""} (blank = estimate{item.record.default_gpu_layers !== null && item.record.default_gpu_layers !== undefined ? `, remembered ${item.record.default_gpu_layers}` : ""})</span>
                    <input
                      aria-label={`GPU layers for ${item.record.display_name}`}
                      inputMode="numeric"
                      onChange={(e) => setLayers((prev) => ({ ...prev, [item.record.alias]: e.currentTarget.value }))}
                      placeholder={item.record.default_gpu_layers !== null && item.record.default_gpu_layers !== undefined ? String(item.record.default_gpu_layers) : "auto"}
                      type="text"
                      value={layers[item.record.alias] ?? ""}
                    />
                  </label>
                )}
                <div className="local-models__actions">
                  <button
                    className="button button--primary"
                    disabled={busy === item.record.alias || !overview.runtime_available}
                    onClick={() => {
                      const raw = (layers[item.record.alias] ?? "").trim();
                      const parsed = raw === "" ? null : Number.parseInt(raw, 10);
                      const request = { device, remember: true, fast_attention: true, tool_calling: true, ...(device === "split" && parsed !== null && Number.isFinite(parsed) ? { gpu_layers: parsed } : {}) };
                      void run(item.record.alias, () => transport.activateLocalModel(item.record.alias, request), `${item.record.display_name} is running on ${device}.`);
                    }}
                    type="button"
                  >
                    {busy === item.record.alias ? "Starting…" : running ? "Restart" : "Activate"}
                  </button>
                  <button className="button button--ghost" disabled={busy === item.record.alias || !running} onClick={() => void run(item.record.alias, () => transport.deactivateLocalModel(item.record.alias), `${item.record.display_name} stopped.`)} type="button">
                    Deactivate
                  </button>
                  <button className="button button--ghost" disabled={busy !== ""} onClick={() => { if (window.confirm(`Remove ${item.record.display_name} from the registry? The weights stay on disk.`)) void run(item.record.alias, () => transport.removeLocalModel(item.record.alias, false), "Removed."); }} type="button">
                    Remove
                  </button>
                </div>
                <p className="local-models__endpoint">
                  Endpoint: <code>POST {item.endpoint_path}</code> (OpenAI chat format, <code>stream: true</code> supported; app token as header or bearer) · base URL for OpenAI clients: <code>/v1/local-models/{item.record.alias}/v1</code>
                  {item.runtime.last_error_code ? <span className="local-models__error"> · last error: {item.runtime.last_error_code.replace(/_/g, " ")}</span> : null}
                </p>
              </li>
            );
          })}
        </ul>
      </section>

      <LocalModelChatPanel models={overview.models} transport={transport} />

      <section aria-labelledby="add-model-title" className="local-models__section">
        <h2 id="add-model-title">Add a model</h2>
        <div className="local-models__recommended">
          <h3>Recommended for this machine</h3>
          <ul>
            {RECOMMENDED.map((item) => {
              const installed = overview.models.some((m) => m.record.source_file === item.file || m.record.alias === item.alias);
              return (
                <li key={item.file}>
                  <div>
                    <strong>{item.label}</strong>
                    <small>{item.note} · {item.repo}</small>
                  </div>
                  <button
                    className="button button--ghost"
                    disabled={installed || busy !== ""}
                    onClick={() => {
                      if (!window.confirm(`Download ${item.file} (${item.sizeGb.toFixed(1)} GB) from ${item.repo} into the app's model folder?`)) return;
                      void run("download", () => transport.startLocalModelDownload({ repo_id: item.repo, filename: item.file, confirmed_size_bytes: Math.round(item.sizeGb * 1024 ** 3), alias: item.alias, default_device: item.device }), "Download started; it appears below and in the list when finished.");
                    }}
                    type="button"
                  >
                    {installed ? "Installed" : `Download ${item.sizeGb.toFixed(1)} GB`}
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="local-models__hint">Sizes are approximate; the exact byte count is confirmed server-side before the download completes. Other repositories: paste any GGUF repo id below.</p>
        </div>
        <div className="local-models__add">
          <label>
            <span>Hugging Face repository (GGUF)</span>
            <span className="local-models__inline">
              <input aria-label="Hugging Face repository" onChange={(e) => setRepoId(e.currentTarget.value)} type="text" value={repoId} />
              <button className="button button--ghost" onClick={() => void lookupRemote()} type="button">Show files</button>
            </span>
          </label>
          {remoteError && <p className="local-models__error" role="alert">{remoteError}</p>}
          {remote && (
            <>
              <label>
                <span>File (4-bit recommended on 16 GB)</span>
                <select aria-label="Model file" onChange={(e) => { setChosenFile(e.currentTarget.value); setAlias(defaultAlias(e.currentTarget.value)); }} value={chosenFile}>
                  {remote.files.map((f) => <option key={f.filename} value={f.filename}>{f.filename} · {gb(f.size_bytes)}</option>)}
                </select>
              </label>
              <label>
                <span>Alias (endpoint name)</span>
                <input aria-label="Alias" onChange={(e) => setAlias(e.currentTarget.value)} type="text" value={alias} />
              </label>
              {remote.gated && <p className="local-models__hint">This repository is gated: accept its terms on Hugging Face while logged in, or the download will be refused.</p>}
              <button
                className="button button--primary"
                disabled={!selectedRemote || !selectedRemote.size_bytes || !alias || busy !== ""}
                onClick={() => {
                  if (!selectedRemote?.size_bytes) return;
                  if (!window.confirm(`Download ${selectedRemote.filename} (${gb(selectedRemote.size_bytes)}) from ${remote.repo_id} into the app's model folder?`)) return;
                  void run("download", () => transport.startLocalModelDownload({ repo_id: remote.repo_id, filename: selectedRemote.filename, confirmed_size_bytes: selectedRemote.size_bytes ?? 0, alias, default_device: "split" }), "Download started; it appears below and in the list when finished.");
                }}
                type="button"
              >
                Download {selectedRemote ? gb(selectedRemote.size_bytes) : ""}
              </button>
            </>
          )}
          {transport.scanLocalModelFolder && (
            <label>
              <span>…or point at a folder: every GGUF in it (one level deep) gets registered, nothing is moved</span>
              <span className="local-models__inline">
                <input aria-label="Model folder" onChange={(e) => setFolderPath(e.currentTarget.value)} placeholder="for example D:\\models" type="text" value={folderPath} />
                <button className="button button--ghost" disabled={!folderPath.trim() || busy !== ""} onClick={() => void run("scan", async () => { const result = await transport.scanLocalModelFolder!(folderPath.trim()); setMessage(`${result.registered.length} registered, ${result.skipped_existing} already known, ${result.skipped_invalid} skipped.`); }, null)} type="button">Scan folder</button>
              </span>
            </label>
          )}
          <label>
            <span>…or register a GGUF file already on this machine</span>
            <span className="local-models__inline">
              <input aria-label="Local GGUF path" onChange={(e) => setLocalPath(e.currentTarget.value)} placeholder="for example D:\\models\\example-q4_k_m.gguf" type="text" value={localPath} />
              <button className="button button--ghost" disabled={!localPath.trim() || busy !== ""} onClick={() => void run("add", () => transport.addLocalModel({ alias: defaultAlias(localPath.trim().split(/[\\/]/).pop() ?? "model"), path: localPath.trim(), default_device: "split", context_size: 8192 }), "Registered.")} type="button">Register</button>
            </span>
          </label>
        </div>
        {overview.downloads.length > 0 && (
          <ul className="local-models__downloads" aria-label="Downloads">
            {overview.downloads.map((d) => (
              <li key={d.download_id} data-state={d.state}>
                <Icon name={d.state === "completed" ? "check" : d.state === "failed" ? "x" : "clock"} />
                <span>{d.filename} · {d.state}{d.bytes_total ? ` · ${gb(d.bytes_done)} of ${gb(d.bytes_total)}` : ""}{d.error_code ? ` · ${d.error_code.replace(/_/g, " ")}` : ""}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <p className="local-models__message" aria-live="polite" role="status">{message}</p>
    </section>
  );
}
