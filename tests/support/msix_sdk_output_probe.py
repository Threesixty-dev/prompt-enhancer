"""Bounded MakeAppx stdout diagnostic using two tiny synthetic candidates."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Callable


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOME_ROOT = Path.home().resolve()
SCRIPTS = REPOSITORY_ROOT / "scripts"
SOURCE = REPOSITORY_ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from prompt_enhancer.application.build_evidence.manifest import build_manifest, canonical_json  # noqa: E402
from prompt_enhancer.application.owned_process import OwnedProcessResult, run_owned_process  # noqa: E402


def _load(name: str):
    specification = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    if specification is None or specification.loader is None:
        raise RuntimeError("support_import_failed")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


PACK = _load("pack_msix_candidate")
MANIFEST = _load("prepare_msix_manifest")
CONTRACT = "msix-sdk-output-probe.v2"
RECEIPT_FILENAME = "diagnostic-receipt.json"
FIXTURE_COUNTS = (2, 6)
CLASSIFIER_LIMIT_BYTES = 16 * 1024
MAX_SDK_STDOUT_LIMIT_BYTES = 64 * 1024 * 1024
MAX_LINES = 512
MAX_LINE_BYTES = 1024
FIXED_MESSAGES = (
    re.compile(r"^Microsoft \(R\) MakeAppx Tool", re.IGNORECASE),
    re.compile(r"^Copyright ", re.IGNORECASE),
    re.compile(r"^Successfully created", re.IGNORECASE),
)
CLOSED_PACK_ERROR_CODES = frozenset({
    "sdk_run_failed", "sdk_pack_failed", "sdk_stderr_not_empty", "sdk_changed",
    "manifest_changed", "candidate_verification_failed", "candidate_manifest_mismatch",
    "output_files_unexpected", "package_envelope_invalid", "package_members_invalid",
    "package_coverage_mismatch", "package_member_mismatch", "package_sdk_member_invalid",
    "package_invalid", "package_changed",
    "sdk_stdout_bounds_invalid", "sdk_stdout_encoding_invalid",
    "sdk_stdout_truncated", "sdk_stdout_unknown", "sdk_stdout_duplicate",
    "sdk_stdout_incomplete",
})
PROBE_ERROR_CODES = frozenset({
    "stdout_limit", "sdk_nonzero", "sdk_stderr", "sdk_probe_failed",
    "stdout_bounds_invalid", "stdout_encoding_invalid", "stdout_line_bounds_invalid",
    "sdk_probe_incomplete", "internal_error",
})
RECEIPT_KEYS = frozenset({
    "contract", "passed", "error_code", "fixture_file_additions",
    "stdout_bytes", "stdout_lines", "fixed_lines", "known_path_lines",
    "error_lines", "unknown_lines", "sdk_exit_codes",
    "owned_cleanup_confirmed", "observed_fixture_file_additions",
    "pack_error_codes", "owned_failure_codes", "classifier_error_codes",
    "packer_passed", "classifier_limit_bytes", "sdk_stdout_limit_bytes",
    "diagnostic_only", "signed",
    "installed",
})


class ProbeError(ValueError):
    def __init__(self, code: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details or {}


class _ClosedParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ProbeError("invalid_arguments")

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise ProbeError("invalid_arguments")


def classify_stdout(payload: bytes, known_values: tuple[str, ...]) -> dict[str, int]:
    if not isinstance(payload, bytes) or len(payload) > CLASSIFIER_LIMIT_BYTES:
        raise ProbeError("stdout_bounds_invalid")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ProbeError("stdout_encoding_invalid") from None
    lines = text.splitlines()
    if len(lines) > MAX_LINES or any(len(line.encode("utf-8")) > MAX_LINE_BYTES for line in lines):
        raise ProbeError("stdout_line_bounds_invalid")
    counts = {"lines": len(lines), "fixed": 0, "known_path": 0, "error": 0, "unknown": 0}
    folded_known = tuple(value.casefold() for value in known_values if value)
    for line in lines:
        folded = line.casefold()
        if "error" in folded or re.search(r"\b0x[0-9a-f]{8}\b", folded):
            counts["error"] += 1
        elif any(pattern.search(line) for pattern in FIXED_MESSAGES):
            counts["fixed"] += 1
        elif any(value in folded for value in folded_known):
            counts["known_path"] += 1
        else:
            counts["unknown"] += 1
    counts["bytes"] = len(payload)
    return counts


def _receipt(fixture_counts: tuple[int, ...], *, passed: bool, error_code: str | None) -> dict[str, object]:
    return {
        "contract": CONTRACT, "passed": passed, "error_code": error_code,
        "fixture_file_additions": list(fixture_counts), "stdout_bytes": [],
        "stdout_lines": [], "fixed_lines": [], "known_path_lines": [],
        "error_lines": [], "unknown_lines": [], "sdk_exit_codes": [],
        "owned_cleanup_confirmed": [], "observed_fixture_file_additions": [],
        "pack_error_codes": [], "owned_failure_codes": [],
        "classifier_error_codes": [], "packer_passed": [],
        "classifier_limit_bytes": CLASSIFIER_LIMIT_BYTES,
        "sdk_stdout_limit_bytes": [], "diagnostic_only": True,
        "signed": False, "installed": False,
    }


def _validate_receipt(receipt: dict[str, object]) -> None:
    if (
        not isinstance(receipt, dict)
        or frozenset(receipt) != RECEIPT_KEYS
        or receipt["contract"] != CONTRACT
        or type(receipt["passed"]) is not bool
        or receipt["error_code"] not in ({None} | PROBE_ERROR_CODES)
        or receipt["fixture_file_additions"] not in ([2], [6], [2, 6])
        or receipt["classifier_limit_bytes"] != CLASSIFIER_LIMIT_BYTES
        or receipt["diagnostic_only"] is not True
        or receipt["signed"] is not False
        or receipt["installed"] is not False
    ):
        raise ProbeError("receipt_schema_invalid")
    for name in ("stdout_bytes", "stdout_lines", "fixed_lines", "known_path_lines", "error_lines", "unknown_lines"):
        values = receipt[name]
        maximum = CLASSIFIER_LIMIT_BYTES if name == "stdout_bytes" else MAX_LINES
        if not isinstance(values, list) or len(values) > 2 or any(
            type(value) is not int or not 0 <= value <= maximum for value in values
        ):
            raise ProbeError("receipt_schema_invalid")
    exits = receipt["sdk_exit_codes"]
    cleanup = receipt["owned_cleanup_confirmed"]
    observed = receipt["observed_fixture_file_additions"]
    pack_errors = receipt["pack_error_codes"]
    owned_errors = receipt["owned_failure_codes"]
    classifier_errors = receipt["classifier_error_codes"]
    packer_passed = receipt["packer_passed"]
    sdk_stdout_limits = receipt["sdk_stdout_limit_bytes"]
    if (
        not isinstance(exits, list) or len(exits) > 2
        or any(value is not None and (type(value) is not int or not -(2**31) <= value < 2**31) for value in exits)
        or not isinstance(cleanup, list) or any(value is not None and type(value) is not bool for value in cleanup)
        or not isinstance(observed, list) or any(value not in FIXTURE_COUNTS for value in observed)
        or not isinstance(pack_errors, list) or any(value is not None and value not in CLOSED_PACK_ERROR_CODES | {"other_closed_failure"} for value in pack_errors)
        or not isinstance(owned_errors, list) or any(value is not None and value not in PACK.OWNED_FAILURE_CODES for value in owned_errors)
        or not isinstance(classifier_errors, list) or any(value is not None and value not in PROBE_ERROR_CODES for value in classifier_errors)
        or not isinstance(packer_passed, list) or any(type(value) is not bool for value in packer_passed)
        or not isinstance(sdk_stdout_limits, list)
        or any(value is not None and (type(value) is not int or not 0 < value <= MAX_SDK_STDOUT_LIMIT_BYTES)
               for value in sdk_stdout_limits)
        or any(len(values) > 2 for values in (
            cleanup, observed, pack_errors, owned_errors, classifier_errors,
            packer_passed, sdk_stdout_limits,
        ))
    ):
        raise ProbeError("receipt_schema_invalid")
    observation_count = len(observed)
    metric_lengths = {
        len(receipt[name])
        for name in ("stdout_bytes", "stdout_lines", "fixed_lines", "known_path_lines", "error_lines", "unknown_lines")
    }
    expected_observed = list(receipt["fixture_file_additions"][:observation_count])
    if (
        len(metric_lengths) != 1
        or next(iter(metric_lengths)) > observation_count
        or observed != expected_observed
        or any(len(values) != observation_count for values in (
            exits, cleanup, pack_errors, owned_errors, classifier_errors,
            packer_passed, sdk_stdout_limits,
        ))
        or (receipt["passed"] is True and (
            receipt["error_code"] is not None
            or observation_count != len(receipt["fixture_file_additions"])
            or next(iter(metric_lengths)) != observation_count
            or exits != [0] * observation_count
            or cleanup != [True] * observation_count
            or pack_errors != [None] * observation_count
            or owned_errors != [None] * observation_count
            or classifier_errors != [None] * observation_count
            or packer_passed != [True] * observation_count
            or any(value is None for value in sdk_stdout_limits)
        ))
        or (receipt["passed"] is False and receipt["error_code"] is None)
    ):
        raise ProbeError("receipt_schema_invalid")


def _persist_receipt(fixture: Path, receipt: dict[str, object]) -> None:
    _validate_receipt(receipt)
    try:
        PACK._ordinary_ancestors(fixture)
        if not stat.S_ISDIR(fixture.lstat().st_mode):
            raise OSError
        payload = json.dumps(receipt, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
        destination = fixture / RECEIPT_FILENAME
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(destination, flags, 0o600)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError
                view = view[written:]
        finally:
            os.close(descriptor)
        if PACK._read_regular(destination, 64 * 1024) != payload:
            raise OSError
    except ProbeError:
        raise
    except (OSError, ValueError):
        raise ProbeError("receipt_persist_failed") from None


def _external_root(raw: str) -> Path:
    try:
        root = PACK._safe_absolute(raw)
        PACK._ordinary_ancestors(root)
        resolved = root.resolve(strict=True)
    except Exception:
        raise ProbeError("unsafe_artifact_root") from None
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ProbeError("unsafe_artifact_root")
    for protected in (REPOSITORY_ROOT.resolve(), HOME_ROOT.resolve()):
        if resolved == protected or resolved.is_relative_to(protected) or protected.is_relative_to(resolved):
            raise ProbeError("unsafe_artifact_root")
    return resolved


def _launcher(raw: str, sha256: str, size: int) -> bytes:
    if (
        not isinstance(sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", sha256) is None
        or isinstance(size, bool)
        or not isinstance(size, int)
        or not 0 < size <= 16 * 1024 * 1024
    ):
        raise ProbeError("launcher_identity_invalid")
    try:
        path = PACK._safe_absolute(raw)
        payload = PACK._read_regular(path, 16 * 1024 * 1024)
    except Exception:
        raise ProbeError("launcher_unavailable") from None
    if len(payload) != size or hashlib.sha256(payload).hexdigest() != sha256:
        raise ProbeError("launcher_identity_mismatch")
    return payload


def _candidate(root: Path, count: int, main: bytes, metrics: bytes) -> tuple[Path, Path, str, tuple[str, ...]]:
    candidate = root / f"candidate-{count}"
    candidate.mkdir()
    generated = MANIFEST.generated_files(
        identity="Example.PromptEnhancer", publisher="CN=ExamplePublisher",
        version="0.1.0.0", include_metrics=True,
    )
    for relative, payload in generated.items():
        destination = candidate.joinpath(*relative.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    (candidate / "PromptEnhancer.exe").write_bytes(main)
    (candidate / "PromptEnhancerMetrics.exe").write_bytes(metrics)
    diagnostics = candidate / "Diagnostic"
    diagnostics.mkdir()
    names = []
    for index in range(1, count + 1):
        name = f"Synthetic{index:02d}.txt"
        (diagnostics / name).write_bytes(f"reserved-example-{index:02d}\n".encode("ascii"))
        names.append(name)
    manifest = build_manifest(
        candidate, git_revision="0" * 40,
        tool_versions={"msix-sdk-output-probe": "1.0"},
        lockfile_hashes={"synthetic-fixture": "0" * 64},
    )
    raw = canonical_json(manifest)
    manifest_path = root / f"candidate-{count}-manifest.json"
    manifest_path.write_bytes(raw)
    known = tuple(generated) + ("PromptEnhancer.exe", "PromptEnhancerMetrics.exe", *names)
    return candidate, manifest_path, hashlib.sha256(raw).hexdigest(), known


def run_probe(
    *,
    artifact_root: str,
    main_launcher: str,
    main_sha256: str,
    main_size: int,
    metrics_launcher: str,
    metrics_sha256: str,
    metrics_size: int,
    fixture_counts: tuple[int, ...] = FIXTURE_COUNTS,
    packer: Callable[..., dict[str, object]] = PACK.pack_candidate,
    owned_runner: Callable[..., OwnedProcessResult] = run_owned_process,
) -> dict[str, object]:
    if fixture_counts not in {(2,), (6,), FIXTURE_COUNTS}:
        raise ProbeError("invalid_fixture_selection")
    base = _external_root(artifact_root)
    main = _launcher(main_launcher, main_sha256, main_size)
    metrics = _launcher(metrics_launcher, metrics_sha256, metrics_size)
    fixture = Path(tempfile.mkdtemp(prefix="msix-sdk-output-", dir=base))
    classifications = []
    cleanup = []
    exits = []
    pack_errors: list[str | None] = []
    owned_failures: list[str | None] = []
    classifier_errors: list[str | None] = []
    packer_passed: list[bool] = []
    observed_additions: list[int] = []
    sdk_stdout_limits: list[int | None] = []
    for count in fixture_counts:
        candidate, manifest, manifest_sha, filenames = _candidate(fixture, count, main, metrics)
        output = fixture / f"package-{count}"
        known = (
            str(candidate), str(output), str(PACK.SDK_PATH), PACK.PACKAGE_NAME,
            *filenames,
        )

        def capturing_runner(command: list[str], **kwargs: object) -> OwnedProcessResult:
            stdout_limit = kwargs.get("stdout_limit")
            if (type(stdout_limit) is not int
                    or not 0 < stdout_limit <= MAX_SDK_STDOUT_LIMIT_BYTES):
                classifier_errors.append("stdout_bounds_invalid")
                raise ProbeError("stdout_bounds_invalid")
            # Record the process limit selected by the packer before execution;
            # it is distinct from this probe's fixed classifier budget.
            sdk_stdout_limits.append(stdout_limit)
            result = owned_runner(command, **kwargs)
            exits.append(result.returncode)
            cleanup.append(True)
            observed_additions.append(count)
            try:
                classifications.append(classify_stdout(result.stdout, known))
                classifier_errors.append(None)
            except ProbeError as error:
                classifier_errors.append(error.code)
                raise
            return result

        try:
            packer(
                candidate_root=str(candidate), build_manifest_path=str(manifest),
                build_manifest_sha256=manifest_sha, output_root=str(output),
                runner=capturing_runner,
            )
            pack_errors.append(None)
            owned_failures.append(None)
            packer_passed.append(True)
        except PACK.PackError as error:
            pack_errors.append(
                error.code if error.code in CLOSED_PACK_ERROR_CODES
                else "other_closed_failure"
            )
            owned_failures.append(
                error.owned_failure_code
                if error.owned_failure_code in PACK.OWNED_FAILURE_CODES else None
            )
            packer_passed.append(False)
            if count not in observed_additions:
                observed_additions.append(count)
                exits.append(error.sdk_exit_code)
                cleanup.append(error.owned_cleanup_confirmed)
                if len(classifier_errors) < len(observed_additions):
                    classifier_errors.append(None)
                if len(sdk_stdout_limits) < len(observed_additions):
                    sdk_stdout_limits.append(None)
            details = {
                "stdout_bytes": [item["bytes"] for item in classifications],
                "stdout_lines": [item["lines"] for item in classifications],
                "fixed_lines": [item["fixed"] for item in classifications],
                "known_path_lines": [item["known_path"] for item in classifications],
                "error_lines": [item["error"] for item in classifications],
                "unknown_lines": [item["unknown"] for item in classifications],
                "sdk_exit_codes": exits,
                "owned_cleanup_confirmed": cleanup,
                "observed_fixture_file_additions": observed_additions,
                "pack_error_codes": pack_errors,
                "owned_failure_codes": owned_failures,
                "classifier_error_codes": classifier_errors,
                "packer_passed": packer_passed,
                "sdk_stdout_limit_bytes": sdk_stdout_limits,
            }
            classifier_code = next(
                (code for code in classifier_errors if code is not None), None
            )
            failure_code = (
                classifier_code
                or ("stdout_limit" if error.owned_failure_code == "owned_process_stdout_limit"
                    else "sdk_nonzero" if error.code == "sdk_pack_failed"
                    else "sdk_stderr" if error.code == "sdk_stderr_not_empty"
                    else "sdk_probe_failed")
            )
            failed_receipt = _receipt(fixture_counts, passed=False, error_code=failure_code)
            failed_receipt.update(details)
            _persist_receipt(fixture, failed_receipt)
            raise ProbeError(
                failure_code,
                details=details,
            ) from None
    if (
        len(classifications) != len(fixture_counts)
        or exits != [0] * len(fixture_counts)
        or cleanup != [True] * len(fixture_counts)
    ):
        details = {
            "stdout_bytes": [item["bytes"] for item in classifications],
            "stdout_lines": [item["lines"] for item in classifications],
            "fixed_lines": [item["fixed"] for item in classifications],
            "known_path_lines": [item["known_path"] for item in classifications],
            "error_lines": [item["error"] for item in classifications],
            "unknown_lines": [item["unknown"] for item in classifications],
            "sdk_exit_codes": exits, "owned_cleanup_confirmed": cleanup,
            "observed_fixture_file_additions": observed_additions,
            "pack_error_codes": pack_errors, "owned_failure_codes": owned_failures,
            "classifier_error_codes": classifier_errors, "packer_passed": packer_passed,
            "sdk_stdout_limit_bytes": sdk_stdout_limits,
        }
        failed_receipt = _receipt(
            fixture_counts, passed=False, error_code="sdk_probe_incomplete"
        )
        failed_receipt.update(details)
        _persist_receipt(fixture, failed_receipt)
        raise ProbeError("sdk_probe_incomplete", details=details)
    receipt = _receipt(fixture_counts, passed=True, error_code=None)
    receipt.update({
        "stdout_bytes": [item["bytes"] for item in classifications],
        "stdout_lines": [item["lines"] for item in classifications],
        "fixed_lines": [item["fixed"] for item in classifications],
        "known_path_lines": [item["known_path"] for item in classifications],
        "error_lines": [item["error"] for item in classifications],
        "unknown_lines": [item["unknown"] for item in classifications],
        "sdk_exit_codes": exits, "owned_cleanup_confirmed": cleanup,
        "observed_fixture_file_additions": observed_additions,
        "pack_error_codes": pack_errors, "owned_failure_codes": owned_failures,
        "classifier_error_codes": classifier_errors, "packer_passed": packer_passed,
        "sdk_stdout_limit_bytes": sdk_stdout_limits,
    })
    _persist_receipt(fixture, receipt)
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = _ClosedParser(add_help=False)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--main-launcher", required=True)
    parser.add_argument("--main-sha256", required=True)
    parser.add_argument("--main-size", required=True, type=int)
    parser.add_argument("--metrics-launcher", required=True)
    parser.add_argument("--metrics-sha256", required=True)
    parser.add_argument("--metrics-size", required=True, type=int)
    parser.add_argument("--fixture-count", choices=FIXTURE_COUNTS, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    selected_counts = FIXTURE_COUNTS
    try:
        arguments = _parser().parse_args(argv)
        selected_counts = (
            (arguments.fixture_count,) if arguments.fixture_count is not None
            else FIXTURE_COUNTS
        )
        receipt = run_probe(
            artifact_root=arguments.artifact_root,
            main_launcher=arguments.main_launcher, main_sha256=arguments.main_sha256,
            main_size=arguments.main_size, metrics_launcher=arguments.metrics_launcher,
            metrics_sha256=arguments.metrics_sha256, metrics_size=arguments.metrics_size,
            fixture_counts=selected_counts,
        )
    except ProbeError as error:
        receipt = {
            "contract": CONTRACT, "passed": False, "error_code": error.code,
            "fixture_file_additions": list(selected_counts), "stdout_bytes": [],
            "stdout_lines": [], "fixed_lines": [], "known_path_lines": [],
            "error_lines": [], "unknown_lines": [], "sdk_exit_codes": [],
            "owned_cleanup_confirmed": [], "classifier_limit_bytes": CLASSIFIER_LIMIT_BYTES,
            "sdk_stdout_limit_bytes": [],
            "observed_fixture_file_additions": [], "pack_error_codes": [],
            "owned_failure_codes": [], "classifier_error_codes": [],
            "packer_passed": [],
            "diagnostic_only": True, "signed": False, "installed": False,
        }
        receipt.update(error.details)
    except Exception:
        receipt = {
            "contract": CONTRACT, "passed": False, "error_code": "internal_error",
            "fixture_file_additions": list(selected_counts), "stdout_bytes": [],
            "stdout_lines": [], "fixed_lines": [], "known_path_lines": [],
            "error_lines": [], "unknown_lines": [], "sdk_exit_codes": [],
            "owned_cleanup_confirmed": [], "classifier_limit_bytes": CLASSIFIER_LIMIT_BYTES,
            "sdk_stdout_limit_bytes": [],
            "observed_fixture_file_additions": [], "pack_error_codes": [],
            "owned_failure_codes": [], "classifier_error_codes": [],
            "packer_passed": [],
            "diagnostic_only": True, "signed": False, "installed": False,
        }
    print("MSIX_SDK_OUTPUT_PROBE=" + json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
