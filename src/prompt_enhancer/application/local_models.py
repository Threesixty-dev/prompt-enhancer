"""Local model runtimes: registry, device choice, loopback endpoints (ADR 0013).

A person installs a model (GGUF weights), activates it on ``cpu``, ``gpu`` or
``split`` (partial GPU offload), and the app spawns one llama.cpp
``llama-server`` per active model on a loopback port. The app's authenticated
API proxies an OpenAI-compatible chat endpoint to it, so every installed
model is usable as a regular local LLM for small tasks and by the
model-judge lane. Inference stays on the machine and no runtime port is exposed
beyond loopback. Repository discovery and a user-confirmed model download are
explicit Hugging Face network operations. The automated path is public-only;
it passes ``token=False`` and never reads a cached Hugging Face login.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import hmac
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

from pydantic import Field, field_validator, model_validator

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
#: Chunk size for the post-download digest; the file is never held in memory.
DIGEST_CHUNK_BYTES = 4 * 1024 * 1024

#: A Hub commit oid: the only revision this app treats as immutable. Branch and
#: tag names ("main", "latest") are mutable and are never recorded as pinned.
COMMIT_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REPO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PORTABLE_GGUF_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,294}\.gguf$")
_WINDOWS_RESERVED_FILE_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)

#: Frozen repository admission policy for downloadable weights, version tagged so a
#: record says which revision of the policy admitted it. This is an operational
#: allow-list for *this* repository's automated downloader, not a legal conclusion:
#: it does not interpret licence terms, does not cover a repository's own extra
#: conditions, and says nothing about how model output may be used. Anything not
#: listed as admitted fails closed and needs a human to fetch the weights by hand.
LICENSE_POLICY_VERSION = "local-model-license-policy.v1"
#: Identifiers reviewed as permissive enough to fetch without a case-by-case decision.
ADMITTED_LICENSE_IDS = frozenset({
    "apache-2.0",
    "bsd-2-clause",
    "bsd-3-clause",
    "cc0-1.0",
    "cc-by-4.0",
    "mit",
    "mpl-2.0",
    "unlicense",
})
#: Identifiers reviewed and refused for the automated path: bespoke community terms,
#: non-commercial or no-derivative clauses, and the Hub's "no real identifier" values.
REFUSED_LICENSE_IDS = frozenset({
    "bigscience-openrail-m",
    "cc-by-nc-2.0",
    "cc-by-nc-4.0",
    "cc-by-nc-nd-4.0",
    "cc-by-nc-sa-4.0",
    "cc-by-nd-4.0",
    "creativeml-openrail-m",
    "deepfloyd-if-license",
    "gemma",
    "llama2",
    "llama3",
    "llama3.1",
    "llama3.2",
    "llama3.3",
    "llama4",
    "openrail",
    "openrail++",
    "other",
    "unknown",
})
_LICENSE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,39}$")


class ModelFormat(StrEnum):
    GGUF = "gguf"


class DeviceMode(StrEnum):
    CPU = "cpu"
    GPU = "gpu"
    SPLIT = "split"


class LicenseAdmission(StrEnum):
    """Outcome of the frozen repository admission policy for one repository."""

    #: The declared identifier is on the reviewed allow-list.
    ALLOWED = "allowed"
    #: The declared identifier was reviewed and refused for the automated path.
    NOT_ALLOWED = "not_allowed"
    #: A well-formed identifier nobody has reviewed for this repository yet.
    UNREVIEWED = "unreviewed"
    #: No identifier at all, or the repository contradicts itself about it.
    UNAVAILABLE = "unavailable"


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
    #: Immutable Hub commit the weights came from. None on a manually registered
    #: file and on registry entries written before provenance was recorded: the
    #: app shows those as "provenance unavailable" and never invents a value.
    source_revision: str | None = Field(default=None, pattern=COMMIT_REVISION_PATTERN.pattern)
    #: Repository licence identifier read from that same immutable revision.
    source_license: str | None = Field(default=None, max_length=40, pattern=_LICENSE_ID_PATTERN.pattern)
    #: Version of the frozen admission policy that admitted the download.
    source_license_policy: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$",
    )
    #: True only when this app downloaded the file and matched digest, size and
    #: GGUF identity against metadata bound to ``source_revision``.
    provenance_verified: bool = False
    default_device: DeviceMode = DeviceMode.SPLIT
    #: Remembered split offload (layers on the GPU); None = estimate from free VRAM.
    default_gpu_layers: int | None = Field(default=None, ge=0, le=4096)
    context_size: int = Field(default=DEFAULT_CONTEXT_SIZE, ge=512, le=MAX_CONTEXT_SIZE)
    layer_count: int | None = Field(default=None, ge=1, le=4096)
    added_at: datetime

    @model_validator(mode="after")
    def verified_provenance_is_complete(self) -> LocalModelRecord:
        """A verified flag is never accepted without the complete receipt.

        Older and manually registered rows may legitimately contain a partial
        source hint while ``provenance_verified`` is false. They remain
        readable, but cannot be relabelled as verified by editing one boolean.
        """

        if not self.provenance_verified:
            return self
        required = (
            self.source_repo,
            self.source_file,
            self.sha256,
            self.source_revision,
            self.source_license,
            self.source_license_policy,
        )
        if any(value is None for value in required) or self.size_bytes is None or self.size_bytes <= 0:
            raise ValueError("verified model provenance requires the complete artifact receipt")
        if REPO_ID_PATTERN.fullmatch(self.source_repo or "") is None:
            raise ValueError("verified model provenance requires a valid source repository")
        if not _plain_gguf_name(self.source_file or ""):
            raise ValueError("verified model provenance requires a portable GGUF file name")
        return self


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


class ScanFolderRequest(StrictModel):
    """Register every GGUF file found in a folder (one level deep) with a generated alias."""

    path: str = Field(min_length=1, max_length=1024)
    default_device: DeviceMode = DeviceMode.SPLIT


class ScanFolderResult(StrictModel):
    folder: str
    registered: tuple[LocalModelRecord, ...]
    skipped_existing: int = Field(ge=0)
    skipped_invalid: int = Field(ge=0)


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
    """A download the person confirmed after seeing the file, size, revision, digest and licence.

    Every ``confirmed_*`` field is what the browser displayed. The service does not
    trust any of them: it re-resolves the repository identity from the Hub and
    refuses the download unless the server's answer matches the confirmation
    exactly, so a caller cannot substitute a repository, file, revision, digest,
    size or licence, and a repository that moved since the person looked is
    refused rather than silently fetched.
    """

    repo_id: str = Field(min_length=3, max_length=200, pattern=REPO_ID_PATTERN.pattern)
    filename: str = Field(min_length=1, max_length=300)
    confirmed_size_bytes: int = Field(ge=1)
    confirmed_revision: str = Field(pattern=COMMIT_REVISION_PATTERN.pattern)
    confirmed_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    confirmed_license: str = Field(min_length=1, max_length=40)
    alias: str = Field(pattern=ALIAS_PATTERN.pattern)
    display_name: str | None = Field(default=None, max_length=120)
    default_device: DeviceMode = DeviceMode.SPLIT

    _alias_not_reserved = field_validator("alias")(_reject_reserved_alias)

    @field_validator("filename")
    @classmethod
    def plain_file_name(cls, value: str) -> str:
        if not _plain_gguf_name(value):
            raise ValueError("download must name one portable root-level .gguf file")
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
    #: The server-verified identity this download is bound to; two revisions or
    #: two digests of the same repository/file/alias are different downloads.
    revision: str | None = Field(default=None, pattern=COMMIT_REVISION_PATTERN.pattern)
    sha256: str | None = Field(default=None, pattern=SHA256_PATTERN.pattern)


class RemoteFile(StrictModel):
    filename: str
    size_bytes: int | None = None
    #: Expected content digest published for this file at ``RemoteRepoFiles.revision``.
    sha256: str | None = Field(default=None, pattern=SHA256_PATTERN.pattern)
    #: This app is willing to download the file: pinned revision, exact size, an
    #: expected digest bound to that revision, and an admitted licence.
    eligible: bool = False
    #: Closed code explaining an ineligible file; never repository text.
    ineligible_reason: str | None = None

    @model_validator(mode="after")
    def eligibility_is_coherent(self) -> RemoteFile:
        complete = self.size_bytes is not None and self.size_bytes > 0 and self.sha256 is not None
        if self.eligible != (complete and self.ineligible_reason is None):
            raise ValueError("remote file eligibility is inconsistent")
        if not self.eligible and self.ineligible_reason is None:
            raise ValueError("an ineligible remote file requires a closed reason")
        return self


class RemoteRepoFiles(StrictModel):
    repo_id: str
    #: Immutable commit oid the whole response is bound to, never a branch name.
    revision: str | None = Field(default=None, pattern=COMMIT_REVISION_PATTERN.pattern)
    #: True only when ``revision`` is a commit oid the Hub confirmed for itself.
    revision_pinned: bool = False
    license_id: str | None = Field(default=None, max_length=40)
    license_admission: LicenseAdmission = LicenseAdmission.UNAVAILABLE
    license_policy_version: str = LICENSE_POLICY_VERSION
    gated: bool | None = None
    #: Closed code set when the repository identity could not be resolved at all.
    unavailable_reason: str | None = None
    files: tuple[RemoteFile, ...] = ()

    @model_validator(mode="after")
    def repository_identity_is_coherent(self) -> RemoteRepoFiles:
        if self.revision_pinned:
            if self.revision is None or self.unavailable_reason is not None:
                raise ValueError("pinned repository identity is incomplete")
        elif self.revision is not None or self.files:
            raise ValueError("an unpinned repository cannot expose revision-bound files")
        if self.license_admission is LicenseAdmission.ALLOWED and self.license_id is None:
            raise ValueError("an admitted repository requires a license identifier")
        if any(file.eligible for file in self.files):
            if self.license_admission is not LicenseAdmission.ALLOWED or self.gated is True:
                raise ValueError("eligible files require an admitted, public repository")
        return self


@dataclass(slots=True)
class ChatUpstream:
    """One upstream chat reply: either a complete body or a line iterator over a server-sent event stream."""

    status_code: int
    content_type: str
    body: bytes | None = None
    lines: Iterator[bytes] | None = None
    cancel: Callable[[], None] | None = None


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


def admit_license(license_id: str | None) -> LicenseAdmission:
    """Apply the frozen repository admission policy to one declared identifier."""

    if license_id is None:
        return LicenseAdmission.UNAVAILABLE
    if license_id in ADMITTED_LICENSE_IDS:
        return LicenseAdmission.ALLOWED
    if license_id in REFUSED_LICENSE_IDS:
        return LicenseAdmission.NOT_ALLOWED
    return LicenseAdmission.UNREVIEWED


def _attribute(source: object, name: str) -> object:
    """Read one field from a Hub dataclass or from the mapping it also behaves as."""

    value = getattr(source, name, None)
    if value is None and isinstance(source, dict):
        value = source.get(name)
    return value


def _commit_oid(value: object) -> str | None:
    """A 40-hex commit oid, or None for a branch name, a tag or anything malformed."""

    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    return candidate if COMMIT_REVISION_PATTERN.fullmatch(candidate) else None


def _declared_license(info: object) -> str | None:
    """The one licence identifier the repository declares, or None when it declares
    none, several different ones, or something that is not an identifier."""

    declared: set[str] = set()
    card = _attribute(_attribute(info, "card_data") or {}, "license")
    for raw in (card if isinstance(card, list) else [card]):
        if isinstance(raw, str) and raw.strip():
            declared.add(raw.strip().lower())
    tags = _attribute(info, "tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("license:") and tag[8:].strip():
                declared.add(tag[8:].strip().lower())
    if len(declared) != 1:
        return None  # nothing declared, or the repository contradicts itself
    only = declared.pop()
    return only if _LICENSE_ID_PATTERN.fullmatch(only) else None


def _identity_unavailable(repo_id: str, reason: str) -> RemoteRepoFiles:
    """The fixed state returned whenever a repository's identity cannot be pinned.

    It is deliberately content-free: no revision, no files, one closed reason code.
    """

    return RemoteRepoFiles(
        repo_id=repo_id,
        revision=None,
        revision_pinned=False,
        license_id=None,
        license_admission=LicenseAdmission.UNAVAILABLE,
        gated=None,
        unavailable_reason=reason,
        files=(),
    )


def _plain_gguf_name(filename: str) -> bool:
    if PORTABLE_GGUF_NAME_PATTERN.fullmatch(filename) is None or ".." in filename:
        return False
    return filename.split(".", 1)[0].upper() not in _WINDOWS_RESERVED_FILE_STEMS


def resolve_repo_identity(repo_id: str, *, model_info: Callable[..., object]) -> RemoteRepoFiles:
    """Bind a repository's GGUF files to one immutable commit, with size, digest and licence.

    Two lookups: the first only to learn which commit the repository points at right
    now, the second addressed to that commit oid so every size, digest and licence in
    the answer comes from the exact revision a download would fetch. A repository that
    will not name a commit oid, or that answers a commit lookup with a different
    commit, yields the fixed unavailable state rather than a guess.
    """

    try:
        head = model_info(repo_id, files_metadata=True)
    except Exception:
        raise LocalModelError("remote_repo_unavailable") from None
    revision = _commit_oid(_attribute(head, "sha"))
    if revision is None:
        return _identity_unavailable(repo_id, "revision_not_immutable")
    try:
        pinned = model_info(repo_id, revision=revision, files_metadata=True)
    except Exception:
        raise LocalModelError("remote_repo_unavailable") from None
    if _commit_oid(_attribute(pinned, "sha")) != revision:
        return _identity_unavailable(repo_id, "revision_contradicted")

    license_id = _declared_license(pinned)
    admission = admit_license(license_id)
    gated_raw = _attribute(pinned, "gated")
    gated = bool(gated_raw) if gated_raw is not None else None
    siblings = _attribute(pinned, "siblings")
    files: list[RemoteFile] = []
    for sibling in siblings if isinstance(siblings, list) else []:
        name = _attribute(sibling, "rfilename")
        if not isinstance(name, str) or not name.endswith(".gguf"):
            continue
        size = _attribute(sibling, "size")
        digest = _attribute(_attribute(sibling, "lfs") or {}, "sha256")
        digest = digest.strip().lower() if isinstance(digest, str) else None
        if gated is True:
            reason = "repository_gated"
        elif admission is not LicenseAdmission.ALLOWED:
            reason = f"license_{admission.value}"
        elif not _plain_gguf_name(name):
            reason = "unsupported_file_path"
        elif not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            reason = "size_unavailable"
        elif digest is None or SHA256_PATTERN.fullmatch(digest) is None:
            reason = "digest_unavailable"
        else:
            reason = None
        files.append(
            RemoteFile(
                filename=name[:300],
                size_bytes=size if isinstance(size, int) and not isinstance(size, bool) and size >= 0 else None,
                sha256=digest if digest is not None and SHA256_PATTERN.fullmatch(digest) else None,
                eligible=reason is None,
                ineligible_reason=reason,
            )
        )
    return RemoteRepoFiles(
        repo_id=repo_id,
        revision=revision,
        revision_pinned=True,
        license_id=license_id,
        license_admission=admission,
        gated=gated,
        unavailable_reason=None,
        files=tuple(sorted(files, key=lambda item: item.filename)),
    )


@dataclass(frozen=True, slots=True)
class VerifiedArtifact:
    """One Hub file the server itself resolved: the only thing a download may fetch."""

    repo_id: str
    filename: str
    revision: str
    sha256: str
    size_bytes: int
    license_id: str


def _artifact_storage_directory(artifact: VerifiedArtifact) -> str:
    """A bounded directory identity that keeps mutable revisions apart."""

    identity = "\0".join((artifact.repo_id, artifact.revision)).encode("utf-8")
    return f"hf-{hashlib.sha256(identity).hexdigest()}"


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(DIGEST_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


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
        model_info: Callable[..., object] | None = None,
    ) -> None:
        self._registry = LocalModelRegistry(root)
        self._llama_server = llama_server
        self._hardware = hardware or (lambda binary: probe_hardware(llama_server=binary))
        self._popen = popen
        self._clock = clock
        self._health_timeout = health_timeout_seconds
        self._downloader = downloader
        self._model_info = model_info
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

    def scan_folder(self, request: ScanFolderRequest) -> ScanFolderResult:
        """Register the GGUF files in a folder; aliases come from the file names, existing paths are skipped."""

        folder = Path(request.path).expanduser()
        if not folder.is_dir():
            raise LocalModelError("folder_not_found")
        known_paths = {str(Path(record.path).resolve()) for record in self._registry.list()}
        known_aliases = {record.alias for record in self._registry.list()}
        registered: list[LocalModelRecord] = []
        skipped_existing = skipped_invalid = 0
        candidates = sorted(list(folder.glob("*.gguf")) + list(folder.glob("*/*.gguf")))[:200]
        for path in candidates:
            if not path.is_file():
                continue
            if str(path.resolve()) in known_paths:
                skipped_existing += 1
                continue
            base = re.sub(r"[^a-z0-9._-]+", "-", path.stem.lower()).strip("-.")[:56] or "model"
            alias = base
            counter = 2
            while alias in known_aliases:
                alias = f"{base}-{counter}"
                counter += 1
            try:
                record = self.add(AddLocalModel(alias=alias, path=str(path), default_device=request.default_device))
            except (LocalModelError, ValueError):
                skipped_invalid += 1
                continue
            known_aliases.add(alias)
            known_paths.add(str(path.resolve()))
            registered.append(record)
        return ScanFolderResult(folder=str(folder), registered=tuple(registered), skipped_existing=skipped_existing, skipped_invalid=skipped_invalid)

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
        def cancel() -> None:
            try:
                response.close()
            except (OSError, ValueError):
                pass

        return ChatUpstream(
            status_code=response.status,
            content_type="text/event-stream",
            lines=_relay_event_stream(response),
            cancel=cancel,
        )

    # ----- downloads -----

    def _hub_model_info(self) -> Callable[..., object]:
        if self._model_info is not None:
            return self._model_info
        try:
            from huggingface_hub import HfApi
        except Exception:
            raise LocalModelError("huggingface_hub_unavailable") from None
        # Public-only until a separately reviewed, explicit token workflow
        # exists. Merely opening the Models page never reads a cached login.
        return HfApi(token=False).model_info

    def remote_files(self, repo_id: str) -> RemoteRepoFiles:
        """Browse a repository's GGUF files bound to one immutable commit."""

        return resolve_repo_identity(repo_id, model_info=self._hub_model_info())

    def _verified_artifact(self, request: DownloadRequest) -> VerifiedArtifact:
        """Re-resolve the repository server-side and accept only an exact match.

        The confirmation the person gave is compared field by field with what the
        Hub says now. Nothing the caller sent is carried into the download or the
        registry: the values used are the server's own.
        """

        identity = resolve_repo_identity(request.repo_id, model_info=self._hub_model_info())
        if not identity.revision_pinned or identity.revision is None:
            raise LocalModelError("provenance_unavailable")
        remote = next((item for item in identity.files if item.filename == request.filename), None)
        if remote is None or not remote.eligible or remote.sha256 is None or remote.size_bytes is None:
            raise LocalModelError("file_not_eligible")
        if identity.license_admission is not LicenseAdmission.ALLOWED or identity.license_id is None:
            raise LocalModelError("file_not_eligible")
        confirmed = (
            request.confirmed_revision.lower(),
            request.confirmed_sha256.lower(),
            request.confirmed_license.strip().lower(),
            request.confirmed_size_bytes,
        )
        resolved = (identity.revision, remote.sha256, identity.license_id, remote.size_bytes)
        if confirmed != resolved:
            raise LocalModelError("provenance_mismatch")
        return VerifiedArtifact(
            repo_id=identity.repo_id,
            filename=remote.filename,
            revision=identity.revision,
            sha256=remote.sha256,
            size_bytes=remote.size_bytes,
            license_id=identity.license_id,
        )

    def start_download(self, request: DownloadRequest) -> DownloadStatus:
        if self._registry.get(request.alias) is not None:
            raise LocalModelError("alias_exists")
        artifact = self._verified_artifact(request)
        # The identity includes the immutable revision and digest, so two revisions
        # or two digests of the same repository/file/alias never share a download.
        download_id = hashlib.sha256(
            "\0".join(
                (
                    artifact.repo_id,
                    artifact.filename,
                    request.alias,
                    artifact.revision,
                    artifact.sha256,
                    artifact.license_id,
                    LICENSE_POLICY_VERSION,
                )
            ).encode("utf-8")
        ).hexdigest()
        with self._lock:
            existing = self._downloads.get(download_id)
            if existing is not None and existing.state in {"queued", "downloading"}:
                return existing
            if self._registry.get(request.alias) is not None or any(
                item.alias == request.alias and item.state in {"queued", "downloading"}
                for item in self._downloads.values()
            ):
                raise LocalModelError("alias_exists")
            status = DownloadStatus(
                download_id=download_id, repo_id=artifact.repo_id, filename=artifact.filename, alias=request.alias,
                state="queued", bytes_total=artifact.size_bytes, bytes_done=0, started_at=self._clock(),
                revision=artifact.revision, sha256=artifact.sha256,
            )
            self._downloads[download_id] = status
        worker = threading.Thread(
            target=self._run_download, args=(download_id, request, artifact),
            name=f"local-model-download-{request.alias}", daemon=True,
        )
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

    def _verify_downloaded_artifact(self, path: Path, artifact: VerifiedArtifact) -> Path:
        """Check what actually landed on disk against the reviewed Hub identity.

        Containment, regular-file and GGUF expectations first, then the exact byte
        count, then the streamed digest compared in constant time. Every failure
        raises a closed code; the caller deletes the file and registers nothing.
        """

        if path.is_symlink() or not path.is_file():
            raise LocalModelError("artifact_rejected")
        resolved = Path(os.path.realpath(path))
        weights_root = Path(os.path.realpath(self._registry.weights_dir))
        if not resolved.is_relative_to(weights_root) or resolved.name != artifact.filename:
            raise LocalModelError("artifact_rejected")
        if resolved.is_symlink() or not resolved.is_file():
            raise LocalModelError("artifact_rejected")
        size = resolved.stat().st_size
        if size != artifact.size_bytes:
            raise LocalModelError("size_mismatch")
        with resolved.open("rb") as handle:
            if handle.read(len(_GGUF_MAGIC)) != _GGUF_MAGIC:
                raise LocalModelError("not_a_gguf_file")
        if not hmac.compare_digest(_digest_file(resolved), artifact.sha256):
            raise LocalModelError("hash_mismatch")
        return resolved

    @staticmethod
    def _download_failure_code(error: BaseException) -> str:
        """Map a downloader failure to a closed code by exception type only.

        Hub exception messages can carry repository text, so they are never read.
        """

        names = {cls.__name__ for cls in type(error).__mro__}
        if names & {"GatedRepoError", "RepositoryNotFoundError", "RevisionNotFoundError", "EntryNotFoundError"}:
            return "gated_or_unauthorized"
        return "download_failed"

    def _run_download(self, download_id: str, request: DownloadRequest, artifact: VerifiedArtifact) -> None:
        self._update_download(download_id, state="downloading")
        target_dir = self._registry.weights_dir / _artifact_storage_directory(artifact)
        finished = threading.Event()
        sampler = threading.Thread(
            target=self._sample_download_progress, args=(download_id, target_dir, artifact.filename, finished),
            name=f"local-model-download-progress-{request.alias}", daemon=True,
        )
        landed: Path | None = None
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            sampler.start()
            if self._downloader is not None:
                path = self._downloader(
                    repo_id=artifact.repo_id, filename=artifact.filename,
                    local_dir=target_dir, revision=artifact.revision,
                )
            else:
                from huggingface_hub import hf_hub_download

                # Pinned to the commit oid; weights only, so no repository code is
                # fetched or executed and nothing is unpickled.
                path = Path(hf_hub_download(
                    repo_id=artifact.repo_id,
                    filename=artifact.filename,
                    revision=artifact.revision,
                    repo_type="model",
                    local_dir=str(target_dir),
                    token=False,
                ))
            landed = Path(path)
            verified_path = self._verify_downloaded_artifact(landed, artifact)
            record = LocalModelRecord(
                alias=request.alias,
                display_name=request.display_name or Path(artifact.filename).stem[:120],
                path=str(verified_path),
                source_repo=artifact.repo_id,
                source_file=artifact.filename,
                size_bytes=artifact.size_bytes,
                sha256=artifact.sha256,
                source_revision=artifact.revision,
                source_license=artifact.license_id,
                source_license_policy=LICENSE_POLICY_VERSION,
                provenance_verified=True,
                default_device=request.default_device,
                layer_count=read_gguf_layer_count(verified_path),
                added_at=self._clock(),
            )
            self._registry.upsert(record)
            self._update_download(
                download_id, state="completed", bytes_done=artifact.size_bytes,
                bytes_total=artifact.size_bytes, finished_at=self._clock(),
            )
        except Exception as error:  # noqa: BLE001 - reported as a closed code, never as text
            code = error.code if isinstance(error, LocalModelError) else self._download_failure_code(error)
            self._discard_unverified(landed)
            self._update_download(download_id, state="failed", error_code=code, finished_at=self._clock())
        finally:
            finished.set()

    def _discard_unverified(self, path: Path | None) -> None:
        """Delete a file that failed verification so nothing can later register it."""

        if path is None:
            return
        try:
            if path.is_symlink():
                path.unlink(missing_ok=True)
                return
            resolved = Path(os.path.realpath(path))
            if resolved.is_relative_to(Path(os.path.realpath(self._registry.weights_dir))):
                resolved.unlink(missing_ok=True)
        except OSError:
            pass


__all__ = (
    "ADMITTED_LICENSE_IDS",
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
    "LICENSE_POLICY_VERSION",
    "LLAMA_SERVER_ENV",
    "RUNTIME_DIR_NAME",
    "LOCAL_MODELS_CONTRACT_VERSION",
    "LicenseAdmission",
    "LocalModelError",
    "LocalModelRecord",
    "LocalModelRegistry",
    "LocalModelService",
    "LocalModelStatus",
    "LocalModelsOverview",
    "ModelFormat",
    "REFUSED_LICENSE_IDS",
    "RemoteFile",
    "RemoteRepoFiles",
    "ScanFolderRequest",
    "ScanFolderResult",
    "RuntimeState",
    "RuntimeStatus",
    "VerifiedArtifact",
    "admit_license",
    "detect_llama_server",
    "estimate_gpu_layers",
    "probe_hardware",
    "read_gguf_layer_count",
    "resolve_repo_identity",
)
