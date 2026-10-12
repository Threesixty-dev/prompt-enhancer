"""Own only selected enhancer containers; static consumer workers are external."""

from __future__ import annotations

import re
import subprocess
import os
import secrets
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .definitions import IMAGE
from .errors import BenchError
from .client import Endpoint

MODEL_CACHE_PATH = "/opt/enhancement/runtime/model-eval"
MODEL_CACHE_LABEL = "enhancement-bench.model-cache"
VARIANT_LABEL = "example.enhancement.build-variant"


@dataclass(frozen=True)
class DockerSettings:
    allowed_repositories: tuple[str, ...]
    network_namespace: str = "enhancement-bench-worker"
    config_source: str | None = None
    environment_keys: tuple[str, ...] = ()
    port: int = 8787
    memory: str = "1g"
    cpus: str = "1"
    docker: str = "docker"
    core_variant: str = "default"
    model_cache_volume: str | None = None
    config_path: Path | None = None
    model_device: str = "cpu"
    gpu_device: str | None = None

    def __post_init__(self):
        if not re.fullmatch(r"[1-9][0-9]{0,5}[mg]", self.memory):
            raise BenchError("invalid_core_memory")
        mib = int(self.memory[:-1]) * (1024 if self.memory[-1] == "g" else 1)
        try:
            cpus = Decimal(self.cpus)
        except (InvalidOperation, ValueError):
            raise BenchError("invalid_core_cpus") from None
        if not re.fullmatch(r"[0-9]{1,2}(?:\.[0-9]{1,2})?", self.cpus) or not Decimal("0.1") <= cpus <= 64:
            raise BenchError("invalid_core_cpus")
        if not 64 <= mib <= 131072:
            raise BenchError("invalid_core_memory")
        if self.core_variant not in {"default", "models"} or self.model_device not in {"cpu", "cuda"}:
            raise BenchError("unsupported_core_runtime")
        if self.core_variant == "default":
            if self.model_cache_volume or self.model_device != "cpu" or self.gpu_device:
                raise BenchError("model_runtime_requires_models_variant")
        elif (not self.model_cache_volume or not re.fullmatch(r"enhancement-bench-models-[a-z0-9][a-z0-9-]{0,47}", self.model_cache_volume)
              or not self.config_source or self.config_path is None):
            raise BenchError("reviewed_model_cache_and_config_required")
        if self.model_device == "cuda":
            if not self.gpu_device or not re.fullmatch(r"(?:[0-9]{1,2}|GPU-[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12})", self.gpu_device):
                raise BenchError("explicit_gpu_device_required")
        elif self.gpu_device:
            raise BenchError("gpu_device_requires_cuda")

    @classmethod
    def from_environment(cls, repositories, environment):
        config_path = environment.get("BENCH_CORE_CONFIG_PATH")
        return cls(repositories,
            network_namespace=environment.get("BENCH_WORKER_CONTAINER", "enhancement-bench-worker"),
            config_source=environment.get("BENCH_CORE_CONFIG_SOURCE"),
            environment_keys=tuple(filter(None, environment.get("BENCH_CORE_ENV_KEYS", "").split(","))),
            port=int(environment.get("BENCH_CORE_PORT", "8787")),
            memory=environment.get("BENCH_CORE_MEMORY", "1g"), cpus=environment.get("BENCH_CORE_CPUS", "1"),
            core_variant=environment.get("BENCH_CORE_VARIANT", "default"),
            model_cache_volume=environment.get("BENCH_MODEL_CACHE_VOLUME") or None,
            config_path=Path(config_path) if config_path else None,
            model_device=environment.get("BENCH_MODEL_DEVICE", "cpu"),
            gpu_device=environment.get("BENCH_GPU_DEVICE") or None)


class DockerRuntime:
    def __init__(self, settings: DockerSettings):
        self.settings = settings

    def _model_mount(self, image):
        if self.settings.core_variant == "default":
            return []
        try:
            with self.settings.config_path.open("rb") as source:
                raw = source.read(256001)
            config = json.loads(raw) if len(raw) <= 256000 else None
            if not isinstance(config, dict) or not isinstance(config.get("evaluators"), list):
                raise ValueError
            for evaluator in config["evaluators"]:
                if (evaluator["cache_root"] != MODEL_CACHE_PATH
                        or evaluator.get("device", "cpu") != self.settings.model_device):
                    raise ValueError
        except (OSError, ValueError, KeyError, TypeError):
            raise BenchError("model_config_runtime_mismatch") from None
        label = self._command(["image", "inspect", "--format", '{{index .Config.Labels "' + VARIANT_LABEL + '"}}', image], capture=True)
        if label.stdout.strip() != b"models":
            raise BenchError("model_image_variant_unconfirmed")
        volume = self._command(["volume", "inspect", "--format", "{{json .}}", self.settings.model_cache_volume],
                               capture=True, allow_failure=True)
        try:
            value = json.loads(volume.stdout)
            if (volume.returncode or value["Name"] != self.settings.model_cache_volume
                    or value.get("Driver") != "local" or value.get("Options")
                    or (value.get("Labels") or {}).get(MODEL_CACHE_LABEL) != "reviewed-v1"):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise BenchError("model_cache_volume_unconfirmed") from None
        # Existing plain local volumes only: no host bind path or volume driver options.
        args = ["--mount", f"type=volume,src={self.settings.model_cache_volume},dst={MODEL_CACHE_PATH},readonly,volume-nocopy"]
        if self.settings.model_device == "cuda":
            args += ["--gpus", f"device={self.settings.gpu_device}"]
        return args

    def _command(self, args, timeout=30, capture=False, allow_failure=False, environment=None):
        try:
            result = subprocess.run([self.settings.docker, *args], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=timeout, check=False, env=environment)
        except (OSError, subprocess.TimeoutExpired):
            raise BenchError("container_operation_unconfirmed", 503) from None
        if result.returncode and not allow_failure:
            raise BenchError("container_operation_failed", 503)
        if capture and len(result.stdout) > 64000:
            raise BenchError("container_response_too_large", 503)
        return result

    def launch(self, run: dict) -> Endpoint:
        image, name = run["image"], run["container_name"]
        repository = image.split("@", 1)[0]
        if not IMAGE.fullmatch(image) or repository not in self.settings.allowed_repositories:
            raise BenchError("image_repository_not_allowed", 403)
        if not re.fullmatch(r"enhancement-bench-[a-f0-9-]{36}", name):
            raise BenchError("invalid_container_identity")
        local = self._command(["image", "inspect", "--format", "{{json .RepoDigests}}", image],
                              capture=True, allow_failure=True)
        if local.returncode:
            self._command(["pull", "--quiet", image], timeout=180)
            local = self._command(["image", "inspect", "--format", "{{json .RepoDigests}}", image], capture=True)
        try:
            if image not in json.loads(local.stdout):
                raise ValueError
        except (ValueError, TypeError):
            raise BenchError("image_digest_unconfirmed", 503) from None
        args = ["create", "--name", name, "--label", f"enhancement-bench.run={run['id']}",
                "--init", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--pids-limit=256", "--memory", self.settings.memory, "--cpus", self.settings.cpus,
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=128m", "--stop-timeout=10"]
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}", self.settings.network_namespace):
            raise BenchError("invalid_worker_namespace")
        args += ["--network", f"container:{self.settings.network_namespace}"]
        args += self._model_mount(image)
        if self.settings.config_source:
            args += ["--mount", f"type=bind,src={self.settings.config_source},dst=/run/secrets/enhancer-config.json,readonly"]
        token = secrets.token_urlsafe(32)
        args += ["--env", "ENHANCEMENT_API_TOKEN"]
        for key in self.settings.environment_keys:
            if not re.fullmatch(r"ENHANCEMENT_[A-Z0-9_]+", key) or key == "ENHANCEMENT_API_TOKEN":
                raise BenchError("invalid_core_environment_key")
            args += ["--env", key]
        # The exact command is checked against the B-owned image recipe in integration.
        args += [image, "--synthetic-benchmark", "--port", str(self.settings.port)]
        if self.settings.config_source:
            args += ["--config", "/run/secrets/enhancer-config.json"]
        self._command(args, environment=os.environ | {"ENHANCEMENT_API_TOKEN": token})
        self._command(["start", name])
        return Endpoint(f"http://127.0.0.1:{self.settings.port}", token)

    def cleanup(self, run_id: str, name: str):
        expected = f"enhancement-bench-{run_id}"
        if name != expected or not re.fullmatch(r"enhancement-bench-[a-f0-9-]{36}", name):
            raise BenchError("container_ownership_mismatch", 503)
        # Listing succeeds only if the daemon is reachable. An inspect failure alone
        # cannot distinguish an absent container from an unavailable daemon.
        listing = self._command(["ps", "-aq", "--filter", f"name=^/{name}$"], capture=True)
        if not listing.stdout.strip():
            return
        label = self._command(["inspect", "--format", '{{index .Config.Labels "enhancement-bench.run"}}', name], capture=True)
        if label.stdout.decode().strip() != run_id:
            raise BenchError("container_ownership_mismatch", 503)
        self._command(["rm", "--force", name], timeout=30)
        remaining = self._command(["ps", "-aq", "--filter", f"name=^/{name}$"], capture=True)
        if remaining.stdout.strip():
            raise BenchError("container_cleanup_unconfirmed", 503)
