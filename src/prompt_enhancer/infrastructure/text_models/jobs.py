"""Bounded, content-free subprocess jobs for the synthetic model screen."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from threading import RLock, Thread
from types import MappingProxyType
from typing import Callable, Mapping

from .loader import repository_root
from .transformers_backends import LocalBackendError, resolve_device


_JOB_ID = re.compile(r"[0-9a-f]{32}\Z")
_CANDIDATES = frozenset(
    {
        "all",
        "session-link",
        "e5",
        "e5-base",
        "nli",
        "bge-m3",
        "bge-reranker",
        "qwen-embedding",
        "qwen-reranker",
        "qwen-rubric",
    }
)
_DEVICES = frozenset({"auto", "cpu", "cuda", "mps"})
_MODES = frozenset({"smoke", "full"})
_OUTCOME_STATUS = frozenset(
    {"evaluated", "not_completed", "blocked_before_download"}
)
_ERROR_CODES = frozenset(
    {
        "unsafe_pickle_only",
        "model_cache_missing_or_invalid",
        "batch_size_outside_manifest_bound",
        "cuda_unavailable",
        "mps_unavailable",
        "resource_exhausted",
        "evaluation_failed",
    }
)
_MODEL_KEYS = frozenset(
    {
        "multilingual_e5_small",
        "multilingual_e5_base",
        "mdeberta_xnli",
        "bge_m3",
        "bge_reranker_v2_m3",
        "qwen3_embedding_06b",
        "qwen3_reranker_06b",
        "qwen3_4b_rubric",
    }
)
_BACKEND_TO_MODEL = MappingProxyType(
    {
        "multilingual_e5_small_cosine_v1": "multilingual_e5_small",
        "multilingual_e5_base_cosine_v1": "multilingual_e5_base",
        "qwen3_embedding_last_token_v1": "qwen3_embedding_06b",
        "bge_reranker_sequence_classifier_v1": "bge_reranker_v2_m3",
        "qwen3_reranker_yes_no_v1": "qwen3_reranker_06b",
        "mdeberta_xnli_argmax_v1": "mdeberta_xnli",
        "qwen3_4b_structured_rubric_v1": "qwen3_4b_rubric",
    }
)


class ModelEvaluationError(RuntimeError):
    pass


class ModelEvaluationBusyError(ModelEvaluationError):
    pass


class ModelEvaluationNotFoundError(ModelEvaluationError):
    pass


@dataclass(frozen=True, slots=True)
class ModelEvaluationRequest:
    candidate: str = "all"
    device: str = "auto"
    mode: str = "smoke"
    allow_download: bool = False

    def __post_init__(self) -> None:
        if self.candidate not in _CANDIDATES:
            raise ValueError("unsupported model candidate selection")
        if self.device not in _DEVICES:
            raise ValueError("unsupported model device")
        if self.mode not in _MODES:
            raise ValueError("unsupported model evaluation mode")


@dataclass(frozen=True, slots=True)
class ModelRuntimeInventory:
    preferred_device: str
    cuda_available: bool
    mps_available: bool
    cpu_available: bool
    cuda_memory_mb: int | None
    one_model_at_a_time: bool = True
    subprocess_isolation: bool = True
    raw_session_data_accepted: bool = False


@dataclass(frozen=True, slots=True)
class CandidateEvaluationSummary:
    key: str
    status: str
    error_code: str | None
    primary_metric: str | None = None
    primary_value: float | None = None
    secondary_metric: str | None = None
    secondary_value: float | None = None
    critical_metric: str | None = None
    critical_value: float | None = None
    inference_latency_ms: float | None = None
    peak_accelerator_memory_mb: float | None = None


@dataclass(frozen=True, slots=True)
class ModelEvaluationJob:
    job_id: str
    status: str
    request: ModelEvaluationRequest
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    resolved_device: str | None = None
    error_code: str | None = None
    outcomes: tuple[CandidateEvaluationSummary, ...] = ()


Runner = Callable[[ModelEvaluationRequest], Mapping[str, object]]


def runtime_inventory() -> ModelRuntimeInventory:
    try:
        import torch

        cuda = bool(torch.cuda.is_available())
        mps = bool(getattr(torch.backends, "mps", None)) and bool(
            torch.backends.mps.is_available()
        )
        memory = (
            int(torch.cuda.get_device_properties(0).total_memory / (1024 * 1024))
            if cuda
            else None
        )
        preferred = resolve_device("auto")
    except (ImportError, LocalBackendError, RuntimeError):
        cuda = False
        mps = False
        memory = None
        preferred = "cpu"
    return ModelRuntimeInventory(
        preferred_device=preferred,
        cuda_available=cuda,
        mps_available=mps,
        cpu_available=True,
        cuda_memory_mb=memory,
    )


def _child_environment(root: Path) -> dict[str, str]:
    allowed: dict[str, str] = {}
    for name in (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "COMSPEC",
        "PATHEXT",
        "CUDA_VISIBLE_DEVICES",
    ):
        value = os.environ.get(name)
        if value:
            allowed[name] = value
    allowed.update(
        {
            "PYTHONPATH": str(root / "src"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
            "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "TRANSFORMERS_VERBOSITY": "error",
        }
    )
    return allowed


def run_model_evaluation_subprocess(request: ModelEvaluationRequest) -> Mapping[str, object]:
    root = repository_root()
    script = root / "scripts" / "evaluate_local_text_models.py"
    if not script.is_file():
        raise ModelEvaluationError("model evaluator unavailable")
    command = [
        sys.executable,
        str(script),
        "--candidate",
        request.candidate,
        "--device",
        request.device,
    ]
    if request.mode == "smoke":
        command.append("--smoke")
    if request.allow_download:
        command.append("--download")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=_child_environment(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=1_800,
            check=False,
            creationflags=creation_flags,
        )
    except subprocess.TimeoutExpired:
        raise ModelEvaluationError("model evaluation timed out") from None
    if len(completed.stdout) > 2 * 1024 * 1024:
        raise ModelEvaluationError("model evaluation output exceeded bound")
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ModelEvaluationError("model evaluation output invalid") from None
    if not isinstance(payload, dict):
        raise ModelEvaluationError("model evaluation output invalid")
    return payload


def _finite_ratio(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        return None
    return round(numeric, 6)


def _finite_nonnegative(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        return None
    return round(numeric, 3)


def _measurement_by_model(report: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    found: dict[str, Mapping[str, object]] = {}
    for bucket_name in ("retrieval", "reranking", "nli", "rubric"):
        bucket = report.get(bucket_name)
        if not isinstance(bucket, list):
            raise ModelEvaluationError("model evaluation output invalid")
        for item in bucket:
            if not isinstance(item, dict):
                raise ModelEvaluationError("model evaluation output invalid")
            backend = item.get("backend_key")
            if backend == "lexical_bm25_v1":
                continue
            model_key = _BACKEND_TO_MODEL.get(backend) if isinstance(backend, str) else None
            if model_key is None or model_key in found:
                raise ModelEvaluationError("model evaluation output invalid")
            found[model_key] = item
    return found


def summarize_model_report(report: Mapping[str, object]) -> tuple[str, tuple[CandidateEvaluationSummary, ...]]:
    device = report.get("device")
    if device not in {"cpu", "cuda", "mps"}:
        raise ModelEvaluationError("model evaluation output invalid")
    raw_outcomes = report.get("candidate_outcomes")
    if not isinstance(raw_outcomes, list) or len(raw_outcomes) > 8:
        raise ModelEvaluationError("model evaluation output invalid")
    measurements = _measurement_by_model(report)
    summaries: list[CandidateEvaluationSummary] = []
    for raw in raw_outcomes:
        if not isinstance(raw, dict) or set(raw) != {"key", "status", "error_code"}:
            raise ModelEvaluationError("model evaluation output invalid")
        key = raw["key"]
        status = raw["status"]
        error = raw["error_code"]
        if (
            key not in _MODEL_KEYS
            or status not in _OUTCOME_STATUS
            or (error is not None and error not in _ERROR_CODES)
        ):
            raise ModelEvaluationError("model evaluation output invalid")
        measurement = measurements.get(key)
        primary_metric = secondary_metric = critical_metric = None
        primary_value = secondary_value = critical_value = None
        if measurement is not None:
            if key in {
                "multilingual_e5_small",
                "multilingual_e5_base",
                "qwen3_embedding_06b",
                "bge_reranker_v2_m3",
                "qwen3_reranker_06b",
            }:
                primary_metric, secondary_metric = "top1_accuracy", "mean_reciprocal_rank"
            elif key == "mdeberta_xnli":
                primary_metric, secondary_metric, critical_metric = (
                    "three_way_accuracy",
                    "contradiction_detection_macro_f1",
                    "different_scope_false_positive_rate",
                )
            elif key == "qwen3_4b_rubric":
                primary_metric, secondary_metric, critical_metric = (
                    "exact_label_accuracy",
                    "json_schema_compliance_rate",
                    "abstention_macro_f1",
                )
            if primary_metric:
                primary_value = _finite_ratio(measurement.get(primary_metric))
            if secondary_metric:
                secondary_value = _finite_ratio(measurement.get(secondary_metric))
            if critical_metric:
                critical_value = _finite_ratio(measurement.get(critical_metric))
            runtime = measurement.get("runtime")
            if not isinstance(runtime, dict):
                runtime = {}
            peak = runtime.get("peak_cuda_allocated_mb")
            if peak is None:
                peak = runtime.get("mps_allocated_mb")
            latency = _finite_nonnegative(measurement.get("inference_latency_ms"))
            memory = _finite_nonnegative(peak)
        else:
            latency = memory = None
        summaries.append(
            CandidateEvaluationSummary(
                key=str(key),
                status=str(status),
                error_code=None if error is None else str(error),
                primary_metric=primary_metric,
                primary_value=primary_value,
                secondary_metric=secondary_metric,
                secondary_value=secondary_value,
                critical_metric=critical_metric,
                critical_value=critical_value,
                inference_latency_ms=latency,
                peak_accelerator_memory_mb=memory,
            )
        )
    return str(device), tuple(summaries)


class LocalTextModelEvaluationService:
    """One process-local model job at a time; no session input is accepted."""

    def __init__(self, runner: Runner = run_model_evaluation_subprocess) -> None:
        self._runner = runner
        self._lock = RLock()
        self._jobs: dict[str, ModelEvaluationJob] = {}
        self._active_job_id: str | None = None

    def inventory(self) -> ModelRuntimeInventory:
        return runtime_inventory()

    def start(self, request: ModelEvaluationRequest) -> ModelEvaluationJob:
        with self._lock:
            if self._active_job_id is not None:
                active = self._jobs.get(self._active_job_id)
                if active and active.status in {"queued", "running"}:
                    raise ModelEvaluationBusyError("model evaluation is already running")
            job_id = secrets.token_hex(16)
            job = ModelEvaluationJob(
                job_id=job_id,
                status="queued",
                request=request,
                created_at=datetime.now(UTC),
            )
            self._jobs[job_id] = job
            self._active_job_id = job_id
            self._trim_locked()
        Thread(target=self._execute, args=(job_id,), daemon=True).start()
        return job

    def get(self, job_id: str) -> ModelEvaluationJob:
        if _JOB_ID.fullmatch(job_id) is None:
            raise ModelEvaluationNotFoundError("model evaluation not found")
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise ModelEvaluationNotFoundError("model evaluation not found")
            return job

    def _execute(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job = replace(job, status="running", started_at=datetime.now(UTC))
            self._jobs[job_id] = job
        try:
            report = self._runner(job.request)
            device, outcomes = summarize_model_report(report)
            failed = any(item.status == "not_completed" for item in outcomes)
            final = replace(
                job,
                status="failed" if failed else "completed",
                completed_at=datetime.now(UTC),
                resolved_device=device,
                error_code="candidate_evaluation_incomplete" if failed else None,
                outcomes=outcomes,
            )
        except Exception:
            final = replace(
                job,
                status="failed",
                completed_at=datetime.now(UTC),
                error_code="model_evaluation_failed",
            )
        with self._lock:
            self._jobs[job_id] = final
            if self._active_job_id == job_id:
                self._active_job_id = None

    def _trim_locked(self) -> None:
        completed = sorted(
            (
                job
                for job in self._jobs.values()
                if job.status not in {"queued", "running"}
            ),
            key=lambda item: item.created_at,
        )
        for job in completed[:-7]:
            self._jobs.pop(job.job_id, None)
