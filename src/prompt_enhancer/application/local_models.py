"""Local model runtimes: registry, device choice, loopback endpoints (ADR 0013).

A person installs a model (GGUF weights), activates it on ``cpu``, ``gpu`` or
``split`` (partial GPU offload), and the app spawns one llama.cpp
``llama-server`` per active model on a loopback port. The app's authenticated
API proxies an OpenAI-compatible chat endpoint to it, so every installed
model is usable as a regular local LLM for small tasks and by the
model-judge lane. Nothing leaves the machine; no runtime port is exposed
beyond loopback; the Hugging Face token, when a download needs one, is used by
``huggingface_hub`` from the person's own login and never read by this code.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from typing import Literal
import urllib.error
import urllib.request

from pydantic import Field, field_validator

from ..domain import StrictModel


LOCAL_MODELS_CONTRACT_VERSION = "local-models.v1"
REGISTRY_FILE_NAME = "registry.json"
WEIGHTS_DIR_NAME = "weights"
LLAMA_SERVER_ENV = "PROMPT_ENHANCER_LLAMA_SERVER"
ALIAS_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
DEFAULT_CONTEXT_SIZE = 8192
MAX_CONTEXT_SIZE = 131072
HEALTH_TIMEOUT_SECONDS = 240
CHAT_TIMEOUT_SECONDS = 600
MAX_CHAT_BODY_BYTES = 4 * 1024 * 1024
#: Upper bound on one streamed reply so a runaway runtime cannot stream forever.
MAX_CHAT_STREAM_BYTES = 16 * 1024 * 1024
#: Names that the HTTP surface uses for fixed routes under /v1/local-models.
RESERVED_ALIASES = frozenset({"openai", "downloads", "remote-files"})
#: How often the download worker samples the partial file for progress.
DOWNLOAD_PROGRESS_INTERVAL_SECONDS = 2.0
#: Rough per-layer budget used to estimate a split: weight bytes / layers plus
#: a fixed headroom for the KV cache and scratch buffers.
SPLIT_VRAM_HEADROOM_BYTES = 2 * 1024 ** 3


class ModelFormat(StrEnum):
    GGUF = "gguf"


class DeviceMode(StrEnum):
    CPU = "cpu"
    GPU = "gpu"
    SPLIT = "split"


class RuntimeState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"


class LocalModelRecord(StrictModel):
    alias: str = Field(pattern=ALIAS_PATTERN.pattern)
    display_name: str = Field(min_length=1, max_length=120)
    format: ModelFormat = ModelFormat.GGUF
    path: str = Field(min_length=1, max_length=1024)
    source_repo: str | None = Field(default=None, max_length=200)
    source_file: str | None = Field(default=None, max_length=300)
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    default_device: DeviceMode = DeviceMode.SPLIT
    #: Remembered split offload (layers on the GPU); None = estimate from free VRAM.
    default_gpu_layers: int | None = Field(default=None, ge=0, le=4096)
    context_size: int = Field(default=DEFAULT_CONTEXT_SIZE, ge=512, le=MAX_CONTEXT_SIZE)
    layer_count: int | None = Field(default=None, ge=1, le=4096)
    added_at: datetime


class HardwareSummary(StrictModel):
    gpu_name: str | None = None
    gpu_memory_mb: int | None = Field(default=None, ge=0)
    gpu_memory_free_mb: int | None = Field(default=None, ge=0)
    ram_mb: int | None = Field(default=None, ge=0)
    llama_server_path: str | None = None
    llama_server_version: str | None = None


class RuntimeStatus(StrictModel):
    state: RuntimeState = RuntimeState.STOPPED
    device: DeviceMode | None = None
    gpu_layers: int | None = Field(default=None, ge=0)
    context_size: int | None = None
    started_at: datetime | None = None
    last_error_code: str | None = None
    pid: int | None = None
    #: Flash attention + 8-bit KV cache were on (falls back to plain when the runtime refuses them).
    fast_attention: bool | None = None
    #: The runtime was started with its chat template engine, so OpenAI-style tool calls work.
    tool_calling: bool | None = None


class LocalModelStatus(StrictModel):
    record: LocalModelRecord
    runtime: RuntimeStatus
    endpoint_path: str


class LocalModelsOverview(StrictModel):
    contract_version: Literal[LOCAL_MODELS_CONTRACT_VERSION] = LOCAL_MODELS_CONTRACT_VERSION
    hardware: HardwareSummary
    runtime_available: bool
    storage_root: str
    models: tuple[LocalModelStatus, ...]
    downloads: tuple["DownloadStatus", ...]


def _reject_reserved_alias(value: str) -> str:
    if value in RESERVED_ALIASES:
        raise ValueError("alias is reserved")
    return value


class AddLocalModel(StrictModel):
    alias: str = Field(pattern=ALIAS_PATTERN.pattern)
    display_name: str | None = Field(default=None, max_length=120)
    path: str = Field(min_length=1, max_length=1024)
    default_device: DeviceMode = DeviceMode.SPLIT
    context_size: int = Field(default=DEFAULT_CONTEXT_SIZE, ge=512, le=MAX_CONTEXT_SIZE)
    layer_count: int | None = Field(default=None, ge=1, le=4096)

    _alias_not_reserved = field_validator("alias")(_reject_reserved_alias)


class ActivateLocalModel(StrictModel):
    device: DeviceMode | None = None
    gpu_layers: int | None = Field(default=None, ge=0, le=4096)
    context_size: int | None = Field(default=None, ge=512, le=MAX_CONTEXT_SIZE)
    #: Keep this device / layer choice as the model's default for next time.
    remember: bool = False
    #: Flash attention with an 8-bit KV cache: ~2x prompt processing and less VRAM on CUDA; retried without on failure.
    fast_attention: bool = True
    #: Start the runtime's chat-template engine (``--jinja``) so tool calls follow the model's own format.
    tool_calling: bool = True


class DownloadRequest(StrictModel):
    """A download the person confirmed after seeing the file name and size."""

    repo_id: str = Field(min_length=3, max_length=200, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    filename: str = Field(min_length=1, max_length=300)
    confirmed_size_bytes: int = Field(ge=1)
    alias: str = Field(pattern=ALIAS_PATTERN.pattern)
    display_name: str | None = Field(default=None, max_length=120)
    default_device: DeviceMode = DeviceMode.SPLIT

    _alias_not_reserved = field_validator("alias")(_reject_reserved_alias)

    @field_validator("filename")
    @classmethod
    def plain_file_name(cls, value: str) -> str:
        if "/" in value or "\\" in value or value.startswith(".") or not value.endswith(".gguf"):
            raise ValueError("download must name a single .gguf file")
        return value


class DownloadStatus(StrictModel):
    download_id: str
    repo_id: str
    filename: str
    alias: str
    state: Literal["queued", "downloading", "completed", "failed"]
    bytes_total: int = Field(ge=0)
    bytes_done: int = Field(ge=0)
    error_code: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class RemoteFile(StrictModel):
    filename: str
    size_bytes: int | None = None


class RemoteRepoFiles(StrictModel):
    repo_id: str
    gated: bool | None = None
    files: tuple[RemoteFile, ...]


@dataclass(slots=True)
class ChatUpstream:
    """One upstream chat reply: either a complete body or a line iterator over a server-sent event stream."""

    status_code: int
    content_type: str
    body: bytes | None = None
    lines: Iterator[bytes] | None = None


def _relay_event_stream(response: object) -> Iterator[bytes]:
    """Yield the runtime's SSE lines unchanged, bounded in size; close upstream when the consumer stops."""

    sent = 0
    try:
        with response:  # type: ignore[attr-defined]
            for line in response:  # type: ignore[attr-defined]
                sent += len(line)
                if sent > MAX_CHAT_STREAM_BYTES:
                    yield b"data: [DONE]\n\n"
                    return
                yield line
    except (OSError, ValueError):
        return


class LocalModelError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _utc_now() -> datetime:
    return datetime.now(UTC)


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


RUNTIME_DIR_NAME = "runtimes"


def detect_llama_server(environment: dict[str, str] | None = None, *, app_home: Path | None = None, models_root: Path | None = None) -> Path | None:
    """Explicit path, then the models folder's runtimes, then the app home's, then PATH."""

    env = os.environ if environment is None else environment
    explicit = env.get(LLAMA_SERVER_ENV)
    if explicit:
        candidate = Path(explicit).expanduser()
        return candidate if candidate.is_file() else None
    for root in (models_root, app_home):
        if root is None:
            continue
        for name in ("llama-server.exe", "llama-server"):
            candidate = root / RUNTIME_DIR_NAME / "llama.cpp" / name
            if candidate.is_file():
                return candidate
    for name in ("llama-server", "llama-server.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def probe_hardware(*, llama_server: Path | None, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> HardwareSummary:
    gpu_name = gpu_total = gpu_free = None
    try:
        result = run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = [p.strip() for p in result.stdout.strip().splitlines()[0].split(",")]
            if len(parts) >= 3:
                gpu_name = parts[0][:80]
                gpu_total = int(float(parts[1]))
                gpu_free = int(float(parts[2]))
    except Exception:
        pass
    ram_mb = None
    try:
        if sys.platform == "win32":
            import ctypes

            class _MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            status = _MemoryStatus()
            status.dwLength = ctypes.sizeof(_MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
                ram_mb = int(status.ullTotalPhys // (1024 * 1024))
        else:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            ram_mb = int(pages * page_size // (1024 * 1024))
    except Exception:
        ram_mb = None
    version = None
    if llama_server is not None:
        try:
            result = run([str(llama_server), "--version"], capture_output=True, text=True, timeout=10, check=False)
            text = (result.stdout or result.stderr or "").strip().splitlines()
            version = text[0][:80] if text else None
        except Exception:
            version = None
    return HardwareSummary(
        gpu_name=gpu_name,
        gpu_memory_mb=gpu_total,
        gpu_memory_free_mb=gpu_free,
        ram_mb=ram_mb,
        llama_server_path=str(llama_server) if llama_server else None,
        llama_server_version=version,
    )


def estimate_gpu_layers(*, size_bytes: int | None, layer_count: int | None, gpu_memory_free_mb: int | None, context_size: int) -> int:
    """Layers that should fit the free VRAM minus headroom; 0 when unknown."""

    if not size_bytes or not layer_count or not gpu_memory_free_mb:
        return 0
    per_layer = max(1, size_bytes // layer_count)
    headroom = SPLIT_VRAM_HEADROOM_BYTES + int(context_size) * 64 * 1024  # coarse KV allowance
    budget = gpu_memory_free_mb * 1024 * 1024 - headroom
    if budget <= 0:
        return 0
    return max(0, min(layer_count, int(budget // per_layer)))


_GGUF_MAGIC = b"GGUF"
_GGUF_HEADER_READ_LIMIT = 64 * 1024 * 1024


def read_gguf_layer_count(path: Path) -> int | None:
    """Block count from the GGUF header (``<arch>.block_count``), or None.

    A minimal, dependency-free reader: it walks the key/value metadata in
    order and stops at the first ``*.block_count``; nothing else is kept.
    Bounded so a hostile or truncated file cannot make it read forever.
    """

    import struct

    try:
        with path.open("rb") as handle:
            if handle.read(4) != _GGUF_MAGIC:
                return None
            version = struct.unpack("<I", handle.read(4))[0]
            if version < 2:
                return None
            _tensor_count, kv_count = struct.unpack("<QQ", handle.read(16))
            consumed = [24]

            def take(count: int) -> bytes:
                if count < 0 or consumed[0] + count > _GGUF_HEADER_READ_LIMIT:
                    raise ValueError("gguf header read limit")
                data = handle.read(count)
                if len(data) != count:
                    raise ValueError("gguf header truncated")
                consumed[0] += count
                return data

            def read_string() -> str:
                length = struct.unpack("<Q", take(8))[0]
                return take(length).decode("utf-8", errors="replace")

            sizes = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
            formats = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}

            def read_value(value_type: int):
                if value_type == 8:
                    return read_string()
                if value_type == 9:
                    element_type, count = struct.unpack("<IQ", take(12))
                    for _ in range(count):
                        read_value(element_type)
                    return None
                size = sizes.get(value_type)
                if size is None:
                    raise ValueError("unknown gguf value type")
                return struct.unpack(formats[value_type], take(size))[0]

            for _ in range(kv_count):
                key = read_string()
                value_type = struct.unpack("<I", take(4))[0]
                value = read_value(value_type)
                if key.endswith(".block_count") and isinstance(value, int) and not isinstance(value, bool):
                    return int(value) if 1 <= int(value) <= 4096 else None
    except (OSError, ValueError, struct.error):
        return None
    return None


class LocalModelRegistry:
    """JSON registry under the app home; aliases are the only identity."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._file = root / REGISTRY_FILE_NAME
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def weights_dir(self) -> Path:
        return self._root / WEIGHTS_DIR_NAME

    def _read(self) -> dict[str, LocalModelRecord]:
        if not self._file.is_file():
            return {}
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        records: dict[str, LocalModelRecord] = {}
        for item in payload.get("models", []) if isinstance(payload, dict) else []:
            try:
                record = LocalModelRecord.model_validate(item)
            except Exception:
                continue
            records[record.alias] = record
        return records

    def _write(self, records: dict[str, LocalModelRecord]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        payload = {"contract_version": LOCAL_MODELS_CONTRACT_VERSION, "models": [r.model_dump(mode="json") for r in records.values()]}
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self._file)

    def list(self) -> tuple[LocalModelRecord, ...]:
        with self._lock:
            return tuple(sorted(self._read().values(), key=lambda r: r.alias))

    def get(self, alias: str) -> LocalModelRecord | None:
        with self._lock:
            return self._read().get(alias)

    def upsert(self, record: LocalModelRecord) -> None:
        with self._lock:
            records = self._read()
            records[record.alias] = record
            self._write(records)

    def remove(self, alias: str) -> bool:
        with self._lock:
            records = self._read()
            if alias not in records:
                return False
            del records[alias]
            self._write(records)
            return True


class LlamaServerProcess:
    """One running llama-server bound to loopback."""

    def __init__(self, *, process: subprocess.Popen, port: int, status: RuntimeStatus) -> None:
        self.process = process
        self.port = port
        self.status = status

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


class LocalModelService:
    def __init__(
        self,
        root: Path,
        *,
        llama_server: Callable[[], Path | None] = detect_llama_server,
        hardware: Callable[[Path | None], HardwareSummary] | None = None,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        clock: Callable[[], datetime] = _utc_now,
        health_timeout_seconds: float = HEALTH_TIMEOUT_SECONDS,
        downloader: Callable[..., Path] | None = None,
    ) -> None:
        self._registry = LocalModelRegistry(root)
        self._llama_server = llama_server
        self._hardware = hardware or (lambda binary: probe_hardware(llama_server=binary))
        self._popen = popen
        self._clock = clock
        self._health_timeout = health_timeout_seconds
        self._downloader = downloader
        self._processes: dict[str, LlamaServerProcess] = {}
        self._failures: dict[str, str] = {}
        self._downloads: dict[str, DownloadStatus] = {}
        self._lock = threading.RLock()

    # ----- registry -----

    @property
    def registry(self) -> LocalModelRegistry:
        return self._registry

    def add(self, request: AddLocalModel) -> LocalModelRecord:
        path = Path(request.path).expanduser()
        if not path.is_file() or path.suffix.lower() != ".gguf":
            raise LocalModelError("model_file_invalid")
        if self._registry.get(request.alias) is not None:
            raise LocalModelError("alias_exists")
        record = LocalModelRecord(
            alias=request.alias,
            display_name=request.display_name or path.stem[:120],
            path=str(path),
            size_bytes=path.stat().st_size,
            default_device=request.default_device,
            context_size=request.context_size,
            layer_count=request.layer_count or read_gguf_layer_count(path),
            added_at=self._clock(),
        )
        self._registry.upsert(record)
        return record

    def remove(self, alias: str, *, delete_weights: bool = False) -> None:
        with self._lock:
            self.deactivate(alias)
            record = self._registry.get(alias)
            if record is None:
                raise LocalModelError("model_not_found")
            self._registry.remove(alias)
            if delete_weights:
                path = Path(record.path)
                try:
                    if self._registry.weights_dir.resolve() in path.resolve().parents:
                        path.unlink(missing_ok=True)
                except OSError:
                    pass

    # ----- hardware / overview -----

    def hardware(self) -> HardwareSummary:
        return self._hardware(self._llama_server())

    def overview(self) -> LocalModelsOverview:
        binary = self._llama_server()
        hardware = self._hardware(binary)
        return LocalModelsOverview(
            hardware=hardware,
            runtime_available=binary is not None,
            storage_root=str(self._registry.root),
            models=tuple(self.status(record.alias, record=record) for record in self._registry.list()),
            downloads=tuple(sorted(self._downloads.values(), key=lambda d: d.started_at)),
        )

    def status(self, alias: str, *, record: LocalModelRecord | None = None) -> LocalModelStatus:
        record = record or self._registry.get(alias)
        if record is None:
            raise LocalModelError("model_not_found")
        with self._lock:
            process = self._processes.get(alias)
            if process is not None:
                if process.process.poll() is not None:
                    self._failures[alias] = "runtime_exited"
                    del self._processes[alias]
                    runtime = RuntimeStatus(state=RuntimeState.FAILED, last_error_code="runtime_exited")
                else:
                    runtime = process.status
            else:
                failure = self._failures.get(alias)
                runtime = RuntimeStatus(state=RuntimeState.FAILED, last_error_code=failure) if failure else RuntimeStatus()
        return LocalModelStatus(record=record, runtime=runtime, endpoint_path=f"/v1/local-models/{alias}/chat/completions")

    # ----- runtime -----

    def activate(self, alias: str, request: ActivateLocalModel | None = None) -> LocalModelStatus:
        request = request or ActivateLocalModel()
        record = self._registry.get(alias)
        if record is None:
            raise LocalModelError("model_not_found")
        binary = self._llama_server()
        if binary is None:
            raise LocalModelError("runtime_unavailable")
        path = Path(record.path)
        if not path.is_file():
            raise LocalModelError("model_file_missing")
        device = request.device or record.default_device
        context = request.context_size or record.context_size
        hardware = self._hardware(binary)
        if device is DeviceMode.CPU:
            gpu_layers = 0
        elif device is DeviceMode.GPU:
            gpu_layers = request.gpu_layers if request.gpu_layers is not None else 999
        else:
            if request.gpu_layers is not None:
                gpu_layers = request.gpu_layers
            elif record.default_gpu_layers is not None:
                gpu_layers = record.default_gpu_layers
            else:
                gpu_layers = estimate_gpu_layers(
                    size_bytes=record.size_bytes,
                    layer_count=record.layer_count,
                    gpu_memory_free_mb=hardware.gpu_memory_free_mb,
                    context_size=context,
                )
        if request.remember:
            self._registry.upsert(
                record.model_copy(
                    update={
                        "default_device": device,
                        "default_gpu_layers": gpu_layers if device is DeviceMode.SPLIT else record.default_gpu_layers,
                        "context_size": context,
                    }
                )
            )
            record = self._registry.get(alias) or record
        attempts = [(request.fast_attention, request.tool_calling)]
        if request.fast_attention:
            attempts.append((False, request.tool_calling))  # older builds or CPU-only: retry plain
        last_error = "runtime_not_healthy"
        for fast_attention, tool_calling in attempts:
            with self._lock:
                self.deactivate(alias)
                port = free_loopback_port()
                command = [
                    str(binary), "-m", str(path), "--host", "127.0.0.1", "--port", str(port),
                    "-ngl", str(gpu_layers), "-c", str(context), "--no-webui",
                ]
                if fast_attention:
                    command += ["-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0"]
                if tool_calling:
                    command.append("--jinja")
                started_at = self._clock()
                try:
                    process = self._popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                except OSError:
                    self._failures[alias] = "runtime_spawn_failed"
                    raise LocalModelError("runtime_spawn_failed") from None
                handle = LlamaServerProcess(
                    process=process,
                    port=port,
                    status=RuntimeStatus(
                        state=RuntimeState.STARTING, device=device, gpu_layers=gpu_layers, context_size=context,
                        started_at=started_at, pid=process.pid, fast_attention=fast_attention, tool_calling=tool_calling,
                    ),
                )
                self._processes[alias] = handle
                self._failures.pop(alias, None)
            if self._wait_healthy(handle):
                handle.status = handle.status.model_copy(update={"state": RuntimeState.RUNNING})
                return self.status(alias, record=record)
            with self._lock:
                self._stop(handle)
                self._processes.pop(alias, None)
                self._failures[alias] = last_error
        raise LocalModelError(last_error)

    def _wait_healthy(self, handle: LlamaServerProcess) -> bool:
        deadline = time.monotonic() + self._health_timeout
        while time.monotonic() < deadline:
            if handle.process.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(f"{handle.base_url}/health", timeout=2) as response:  # noqa: S310 - loopback only
                    if response.status == 200:
                        return True
            except (urllib.error.URLError, OSError, ValueError):
                pass
            time.sleep(0.5)
        return False

    def deactivate(self, alias: str) -> None:
        with self._lock:
            handle = self._processes.pop(alias, None)
            if handle is not None:
                self._stop(handle)
            self._failures.pop(alias, None)

    @staticmethod
    def _stop(handle: LlamaServerProcess) -> None:
        process = handle.process
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=10)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    def shutdown(self) -> None:
        with self._lock:
            for alias in list(self._processes):
                self.deactivate(alias)

    # ----- chat proxy -----

    def running_aliases(self) -> tuple[str, ...]:
        """Aliases whose runtime is healthy right now (for the OpenAI-style model list)."""

        with self._lock:
            return tuple(sorted(alias for alias, handle in self._processes.items() if handle.status.state is RuntimeState.RUNNING))

    def _prepare_chat(self, alias: str, body: bytes) -> tuple[LlamaServerProcess, dict[str, object]]:
        if len(body) > MAX_CHAT_BODY_BYTES:
            raise LocalModelError("chat_body_too_large")
        with self._lock:
            handle = self._processes.get(alias)
        if handle is None or handle.status.state is not RuntimeState.RUNNING:
            raise LocalModelError("model_not_active")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise LocalModelError("chat_body_invalid") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            raise LocalModelError("chat_body_invalid")
        payload["model"] = alias
        return handle, payload

    def chat(self, alias: str, body: bytes) -> tuple[int, bytes, str]:
        """Forward one OpenAI-compatible chat completion to the model's runtime (never streamed)."""

        handle, payload = self._prepare_chat(alias, body)
        payload["stream"] = False
        request = urllib.request.Request(
            f"{handle.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=CHAT_TIMEOUT_SECONDS) as response:  # noqa: S310 - loopback only
                return response.status, response.read(), response.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers.get("Content-Type", "application/json") if error.headers else "application/json"
        except (urllib.error.URLError, OSError):
            raise LocalModelError("runtime_unreachable") from None

    def open_chat(self, alias: str, body: bytes) -> ChatUpstream:
        """Forward a chat completion; when the caller asked for ``stream`` the reply is relayed chunk by chunk.

        The upstream status and headers are read synchronously so failures (for example a context overflow,
        which llama.cpp reports as HTTP 400) come back as ordinary JSON errors rather than a broken stream.
        """

        handle, payload = self._prepare_chat(alias, body)
        wants_stream = payload.get("stream") is True
        if not wants_stream:
            status_code, reply, content_type = self.chat(alias, json.dumps(payload).encode("utf-8"))
            return ChatUpstream(status_code=status_code, content_type=content_type, body=reply)
        request = urllib.request.Request(
            f"{handle.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=CHAT_TIMEOUT_SECONDS)  # noqa: S310 - loopback only
        except urllib.error.HTTPError as error:
            return ChatUpstream(
                status_code=error.code,
                content_type=error.headers.get("Content-Type", "application/json") if error.headers else "application/json",
                body=error.read(),
            )
        except (urllib.error.URLError, OSError):
            raise LocalModelError("runtime_unreachable") from None
        content_type = response.headers.get("Content-Type", "text/event-stream")
        if "text/event-stream" not in content_type:
            with response:
                return ChatUpstream(status_code=response.status, content_type=content_type, body=response.read())
        return ChatUpstream(status_code=response.status, content_type="text/event-stream", lines=_relay_event_stream(response))

    # ----- downloads -----

    def remote_files(self, repo_id: str) -> RemoteRepoFiles:
        try:
            from huggingface_hub import HfApi
        except Exception:
            raise LocalModelError("huggingface_hub_unavailable") from None
        try:
            info = HfApi().model_info(repo_id, files_metadata=True)
        except Exception:
            raise LocalModelError("remote_repo_unavailable") from None
        files = tuple(
            RemoteFile(filename=sibling.rfilename, size_bytes=getattr(sibling, "size", None))
            for sibling in (info.siblings or [])
            if sibling.rfilename.endswith(".gguf")
        )
        gated = getattr(info, "gated", None)
        return RemoteRepoFiles(repo_id=repo_id, gated=bool(gated) if gated is not None else None, files=files)

    def start_download(self, request: DownloadRequest) -> DownloadStatus:
        if self._registry.get(request.alias) is not None:
            raise LocalModelError("alias_exists")
        download_id = hashlib.sha256(f"{request.repo_id}/{request.filename}/{request.alias}".encode("utf-8")).hexdigest()
        with self._lock:
            existing = self._downloads.get(download_id)
            if existing is not None and existing.state in {"queued", "downloading"}:
                return existing
            status = DownloadStatus(
                download_id=download_id, repo_id=request.repo_id, filename=request.filename, alias=request.alias,
                state="queued", bytes_total=request.confirmed_size_bytes, bytes_done=0, started_at=self._clock(),
            )
            self._downloads[download_id] = status
        worker = threading.Thread(target=self._run_download, args=(download_id, request), name=f"local-model-download-{request.alias}", daemon=True)
        worker.start()
        return status

    def _update_download(self, download_id: str, **changes: object) -> None:
        with self._lock:
            current = self._downloads.get(download_id)
            if current is not None:
                self._downloads[download_id] = current.model_copy(update=changes)

    def _sample_download_progress(self, download_id: str, target_dir: Path, filename: str, done: threading.Event) -> None:
        """Report partial bytes while huggingface_hub writes its ``.incomplete`` file next to the target."""

        partial_dir = target_dir / ".cache" / "huggingface" / "download"
        while not done.wait(DOWNLOAD_PROGRESS_INTERVAL_SECONDS):
            best = 0
            try:
                candidates = [target_dir / filename, *partial_dir.glob(f"{filename}*.incomplete")] if partial_dir.exists() else [target_dir / filename]
                for candidate in candidates:
                    try:
                        best = max(best, candidate.stat().st_size)
                    except OSError:
                        continue
            except OSError:
                best = 0
            if best:
                self._update_download(download_id, bytes_done=best)

    def _run_download(self, download_id: str, request: DownloadRequest) -> None:
        self._update_download(download_id, state="downloading")
        target_dir = self._registry.weights_dir / request.repo_id.replace("/", "__")
        finished = threading.Event()
        sampler = threading.Thread(
            target=self._sample_download_progress, args=(download_id, target_dir, request.filename, finished),
            name=f"local-model-download-progress-{request.alias}", daemon=True,
        )
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            sampler.start()
            if self._downloader is not None:
                path = self._downloader(repo_id=request.repo_id, filename=request.filename, local_dir=target_dir)
            else:
                from huggingface_hub import hf_hub_download

                path = Path(hf_hub_download(repo_id=request.repo_id, filename=request.filename, local_dir=str(target_dir)))
            size = Path(path).stat().st_size
            if abs(size - request.confirmed_size_bytes) > max(1024 * 1024, request.confirmed_size_bytes // 100):
                self._update_download(download_id, state="failed", error_code="size_mismatch", bytes_done=size, finished_at=self._clock())
                return
            record = LocalModelRecord(
                alias=request.alias,
                display_name=request.display_name or Path(request.filename).stem[:120],
                path=str(path),
                source_repo=request.repo_id,
                source_file=request.filename,
                size_bytes=size,
                default_device=request.default_device,
                layer_count=read_gguf_layer_count(Path(path)),
                added_at=self._clock(),
            )
            self._registry.upsert(record)
            self._update_download(download_id, state="completed", bytes_done=size, bytes_total=size, finished_at=self._clock())
        except Exception as error:  # noqa: BLE001 - reported as a closed code, never as text
            code = "gated_or_unauthorized" if "401" in str(error) or "403" in str(error) or "gated" in str(error).lower() else "download_failed"
            self._update_download(download_id, state="failed", error_code=code, finished_at=self._clock())
        finally:
            finished.set()


__all__ = (
    "ALIAS_PATTERN",
    "ActivateLocalModel",
    "ChatUpstream",
    "MAX_CHAT_STREAM_BYTES",
    "RESERVED_ALIASES",
    "AddLocalModel",
    "DeviceMode",
    "DownloadRequest",
    "DownloadStatus",
    "HardwareSummary",
    "LLAMA_SERVER_ENV",
    "RUNTIME_DIR_NAME",
    "LOCAL_MODELS_CONTRACT_VERSION",
    "LocalModelError",
    "LocalModelRecord",
    "LocalModelRegistry",
    "LocalModelService",
    "LocalModelStatus",
    "LocalModelsOverview",
    "ModelFormat",
    "RemoteFile",
    "RemoteRepoFiles",
    "RuntimeState",
    "RuntimeStatus",
    "detect_llama_server",
    "estimate_gpu_layers",
    "probe_hardware",
    "read_gguf_layer_count",
)
