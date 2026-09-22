"""Pack one hash-bound candidate with MakeAppx; never sign or install it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePath, PureWindowsPath
import stat
import sys
from typing import Callable
from zipfile import BadZipFile, ZipFile

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from prompt_enhancer.application.build_evidence.manifest import (  # noqa: E402
    BuildManifest,
    MAX_MANIFEST_BYTES,
    build_manifest,
    canonical_json,
)
from prompt_enhancer.application.owned_process import (  # noqa: E402
    OwnedProcessRunError,
    OwnedProcessResult,
    run_owned_process,
)
from prompt_enhancer.application.paths.policy import classify_windows_path_text  # noqa: E402
from prompt_enhancer.infrastructure.updates.msix_preflight import (  # noqa: E402
    _bounded_zip_central_directory,
    _leaf_snapshot,
    _same_path_and_open_file,
)


CONTRACT = "unsigned-msix-pack.v1"
SDK_PATH = Path("C:/Program Files (x86)/Windows Kits/10/bin/10.0.26100.0/x64/makeappx.exe")
SDK_SHA256 = "00fff202b71c1266b8c3899701e42b5468ea153b2b33a0a47215fe27695f16d0"
SDK_SIZE = 584_024
PACKAGE_NAME = "PromptEnhancer-unsigned.msix"
MAX_PACKAGE_BYTES = 8 * 1024 * 1024 * 1024
SDK_MEMBERS = frozenset({"[Content_Types].xml", "AppxBlockMap.xml"})
OWNED_FAILURE_CODES = frozenset({
    "owned_process_unavailable",
    "owned_process_stdout_limit",
    "owned_process_stderr_limit",
    "owned_process_timeout",
    "owned_process_cleanup_unconfirmed",
})
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HOME_ROOT = Path.home().resolve()


class PackError(ValueError):
    def __init__(
        self,
        code: str,
        *,
        stage: str = "preflight",
        owned_cleanup_confirmed: bool | None = None,
        sdk_exit_code: int | None = None,
        owned_failure_code: str | None = None,
        stdout_diagnostics: dict | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.stage = stage
        self.owned_cleanup_confirmed = owned_cleanup_confirmed
        self.sdk_exit_code = sdk_exit_code
        self.owned_failure_code = owned_failure_code
        self.stdout_diagnostics = stdout_diagnostics


class _ClosedParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise PackError("invalid_arguments")

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise PackError("invalid_arguments")


def _reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def _same_open_file(path: os.stat_result, descriptor: os.stat_result, suffix: str) -> bool:
    if os.name != "nt" or suffix.casefold() not in {".exe", ".bat", ".cmd", ".com"}:
        return _same_path_and_open_file(path, descriptor)
    path_mode = path.st_mode
    if path_mode == (descriptor.st_mode | 0o111):
        path_mode = descriptor.st_mode
    def snapshot(value: os.stat_result, mode: int) -> tuple[int, ...]:
        return (
            value.st_dev, value.st_ino, mode, value.st_nlink, value.st_size,
            value.st_mtime_ns, getattr(value, "st_birthtime_ns", value.st_ctime_ns),
            getattr(value, "st_file_attributes", 0),
        )
    return (
        bool(path.st_ino and descriptor.st_ino)
        and stat.S_ISREG(path.st_mode)
        and stat.S_ISREG(descriptor.st_mode)
        and not _reparse(path)
        and not _reparse(descriptor)
        and snapshot(path, path_mode) == snapshot(descriptor, descriptor.st_mode)
    )


def _safe_absolute(raw: str) -> Path:
    windows_path = PureWindowsPath(raw) if isinstance(raw, str) else PureWindowsPath()
    if (
        not isinstance(raw, str)
        or not raw
        or ".." in PurePath(raw).parts
        or ".." in PureWindowsPath(raw).parts
        or classify_windows_path_text(raw) is not None
        or (os.name == "nt" and bool(windows_path.root) and not windows_path.drive)
    ):
        raise PackError("unsafe_path")
    path = Path(raw)
    if not path.is_absolute():
        raise PackError("unsafe_path")
    return path


def _ordinary_ancestors(path: Path) -> None:
    current = path
    while True:
        try:
            metadata = current.lstat()
        except OSError as error:
            raise PackError("unsafe_path") from error
        if _reparse(metadata):
            raise PackError("unsafe_path")
        if current != path and not stat.S_ISDIR(metadata.st_mode):
            raise PackError("unsafe_path")
        if current.parent == current:
            return
        current = current.parent


def _read_regular(path: Path, maximum: int) -> bytes:
    _ordinary_ancestors(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= maximum:
        raise PackError("unsafe_file")
    try:
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if not _same_open_file(before, opened, path.suffix):
                raise PackError("unsafe_file")
            data = stream.read(maximum + 1)
            after_open = os.fstat(stream.fileno())
    except OSError as error:
        raise PackError("unsafe_file") from error
    after = path.lstat()
    if (
        len(data) != before.st_size
        or len(data) > maximum
        or _leaf_snapshot(before) != _leaf_snapshot(after)
        or _leaf_snapshot(opened) != _leaf_snapshot(after_open)
        or not _same_open_file(after, after_open, path.suffix)
    ):
        raise PackError("unsafe_file")
    return data


def _manifest(path: Path, expected_sha256: str) -> tuple[BuildManifest, bytes]:
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64 or any(character not in "0123456789abcdef" for character in expected_sha256):
        raise PackError("invalid_manifest_identity")
    raw = _read_regular(path, MAX_MANIFEST_BYTES)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise PackError("manifest_identity_mismatch")
    try:
        manifest = BuildManifest.model_validate_json(raw)
    except Exception:
        raise PackError("invalid_manifest") from None
    if canonical_json(manifest) != raw:
        raise PackError("manifest_not_canonical")
    return manifest, raw


def _verify_candidate(root: Path, manifest: BuildManifest, canonical: bytes) -> None:
    try:
        observed = build_manifest(
            root,
            git_revision=manifest.git_revision,
            tool_versions={item.name: item.version for item in manifest.tool_versions},
            lockfile_hashes={item.name: item.sha256 for item in manifest.lockfile_hashes},
        )
    except Exception:
        raise PackError("candidate_verification_failed") from None
    if canonical_json(observed) != canonical:
        raise PackError("candidate_manifest_mismatch")
    if any(item.relative_path.casefold() in {name.casefold() for name in SDK_MEMBERS} for item in manifest.files):
        raise PackError("candidate_reserved_member")


def _fresh_external_output(raw: str) -> Path:
    output = _safe_absolute(raw)
    if output.exists() or not output.name:
        raise PackError("unsafe_output")
    _ordinary_ancestors(output.parent)
    resolved = output.parent.resolve(strict=True) / output.name
    for protected in (REPOSITORY_ROOT.resolve(), HOME_ROOT.resolve()):
        if resolved == protected or resolved.is_relative_to(protected) or protected.is_relative_to(resolved):
            raise PackError("unsafe_output")
    return resolved


def _hash_package(path: Path) -> tuple[str, int]:
    _ordinary_ancestors(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= MAX_PACKAGE_BYTES:
        raise PackError("package_invalid", stage="post_pack", owned_cleanup_confirmed=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if not _same_open_file(before, opened, path.suffix):
                raise PackError("package_invalid", stage="post_pack", owned_cleanup_confirmed=True)
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_PACKAGE_BYTES:
                    raise PackError("package_invalid", stage="post_pack", owned_cleanup_confirmed=True)
                digest.update(chunk)
            after_open = os.fstat(stream.fileno())
    except OSError:
        raise PackError("package_invalid", stage="post_pack", owned_cleanup_confirmed=True) from None
    after = path.lstat()
    if (
        size != before.st_size
        or _leaf_snapshot(before) != _leaf_snapshot(after)
        or _leaf_snapshot(opened) != _leaf_snapshot(after_open)
        or not _same_open_file(after, after_open, path.suffix)
    ):
        raise PackError("package_invalid", stage="post_pack", owned_cleanup_confirmed=True)
    return digest.hexdigest(), size


def _verify_package(path: Path, manifest: BuildManifest) -> None:
    expected = {item.relative_path: item for item in manifest.files}
    _ordinary_ancestors(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= MAX_PACKAGE_BYTES:
        raise PackError("package_invalid")
    try:
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if not _same_open_file(before, opened, path.suffix) or not _bounded_zip_central_directory(stream.fileno(), size=before.st_size):
                raise PackError("package_envelope_invalid")
            stream.seek(0)
            with ZipFile(stream) as package:
                infos = package.infolist()
                names = [info.filename.replace("\\", "/") for info in infos if not info.is_dir()]
                if len(names) != len(infos) or len(names) != len(set(name.casefold() for name in names)):
                    raise PackError("package_members_invalid")
                if set(names) != set(expected) | SDK_MEMBERS:
                    raise PackError("package_coverage_mismatch")
                info_by_name = dict(zip(names, infos, strict=True))
                for name, item in expected.items():
                    info = info_by_name[name]
                    if info.file_size != item.size_bytes or info.flag_bits & 1:
                        raise PackError("package_member_mismatch")
                    digest = hashlib.sha256()
                    size = 0
                    with package.open(info) as member_stream:
                        while chunk := member_stream.read(1024 * 1024):
                            size += len(chunk)
                            if size > item.size_bytes:
                                raise PackError("package_member_mismatch")
                            digest.update(chunk)
                    if size != item.size_bytes or digest.hexdigest() != item.sha256:
                        raise PackError("package_member_mismatch")
                for name in SDK_MEMBERS:
                    info = info_by_name[name]
                    if info.flag_bits & 1 or not 0 < info.file_size <= 16 * 1024 * 1024:
                        raise PackError("package_sdk_member_invalid")
                    if len(package.read(info)) != info.file_size:
                        raise PackError("package_sdk_member_invalid")
            after_open = os.fstat(stream.fileno())
        after = path.lstat()
        if (
            _leaf_snapshot(before) != _leaf_snapshot(after)
            or _leaf_snapshot(opened) != _leaf_snapshot(after_open)
            or not _same_open_file(after, after_open, path.suffix)
        ):
            raise PackError("package_changed")
    except PackError:
        raise
    except (BadZipFile, KeyError, OSError, RuntimeError):
        raise PackError("package_invalid") from None


def pack_candidate(
    *,
    candidate_root: str,
    build_manifest_path: str,
    build_manifest_sha256: str,
    output_root: str,
    sdk_path: Path = SDK_PATH,
    sdk_sha256: str = SDK_SHA256,
    sdk_size: int = SDK_SIZE,
    runner: Callable[..., OwnedProcessResult] = run_owned_process,
) -> dict[str, object]:
    candidate = _safe_absolute(candidate_root)
    manifest_path = _safe_absolute(build_manifest_path)
    output = _fresh_external_output(output_root)
    sdk_path = _safe_absolute(os.fspath(sdk_path))
    _ordinary_ancestors(candidate)
    if not stat.S_ISDIR(candidate.lstat().st_mode):
        raise PackError("unsafe_path")
    candidate_resolved = candidate.resolve(strict=True)
    if output.is_relative_to(candidate_resolved) or candidate_resolved.is_relative_to(output):
        raise PackError("candidate_output_overlap")
    manifest, canonical = _manifest(manifest_path, build_manifest_sha256)
    _verify_candidate(candidate, manifest, canonical)
    sdk_before = _read_regular(sdk_path, 1024 * 1024)
    if len(sdk_before) != sdk_size or hashlib.sha256(sdk_before).hexdigest() != sdk_sha256:
        raise PackError("sdk_identity_mismatch")
    from msix_sdk_output import OutputPolicy, OutputError
    policy = OutputPolicy(str(candidate), str(output / PACKAGE_NAME), [item.relative_path for item in manifest.files])
    try:
        output.mkdir()
    except OSError as error:
        raise PackError("output_create_failed") from error
    package = output / PACKAGE_NAME
    environment = {
        "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
        "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
        "TEMP": str(output), "TMP": str(output),
        "HOME": str(output), "USERPROFILE": str(output),
        "PATH": str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"),
    }
    command = [str(sdk_path), "pack", "/d", str(candidate), "/p", str(package), "/h", "SHA256", "/no"]
    try:
        result = runner(
            command, cwd=output, env=environment, timeout=120,
            maximum_active_processes=1, stdout_limit=policy.byte_limit,
            stderr_limit=16 * 1024,
        )
    except OwnedProcessRunError as error:
        owned_code = error.code if error.code in OWNED_FAILURE_CODES else None
        cleanup = (
            False if owned_code == "owned_process_cleanup_unconfirmed"
            else True if owned_code in {
                "owned_process_stdout_limit", "owned_process_stderr_limit",
                "owned_process_timeout",
            }
            else None
        )
        raise PackError(
            "sdk_run_failed", stage="sdk", owned_cleanup_confirmed=cleanup,
            owned_failure_code=owned_code,
        ) from None
    except (OSError, ValueError):
        raise PackError("sdk_run_failed", stage="sdk", owned_cleanup_confirmed=None) from None
    if result.returncode != 0:
        raise PackError("sdk_pack_failed", stage="sdk", owned_cleanup_confirmed=True, sdk_exit_code=result.returncode)
    if result.stderr:
        raise PackError("sdk_stderr_not_empty", stage="sdk", owned_cleanup_confirmed=True, sdk_exit_code=0)
    try:
        stdout_receipt = policy.validate(result.stdout)
    except OutputError as error:
        raise PackError(str(error), stage="sdk", owned_cleanup_confirmed=True, sdk_exit_code=0,
                        stdout_diagnostics=error.diagnostics) from None
    try:
        if _read_regular(sdk_path, 1024 * 1024) != sdk_before:
            raise PackError("sdk_changed")
        if _read_regular(manifest_path, MAX_MANIFEST_BYTES) != canonical:
            raise PackError("manifest_changed")
        _verify_candidate(candidate, manifest, canonical)
        if sorted(item.name for item in output.iterdir()) != [PACKAGE_NAME]:
            raise PackError("output_files_unexpected")
        _verify_package(package, manifest)
        digest, size = _hash_package(package)
    except PackError as error:
        raise PackError(error.code, stage="post_pack", owned_cleanup_confirmed=True, sdk_exit_code=0) from None
    return {
        "contract": CONTRACT, "passed": True, "error_code": None,
        "artifact_sha256": digest, "artifact_size_bytes": size,
        "candidate_files_verified": len(manifest.files),
        "validation_enabled": True, "owned_cleanup_confirmed": True,
        "stage": "complete", "sdk_exit_code": 0,
        "owned_failure_code": None,
        "signed": False, "installed": False,
        **stdout_receipt,
    }


def _parser() -> argparse.ArgumentParser:
    parser = _ClosedParser(add_help=False)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--build-manifest", required=True)
    parser.add_argument("--build-manifest-sha256", required=True)
    parser.add_argument("--output-root", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        receipt = pack_candidate(
            candidate_root=arguments.candidate_root,
            build_manifest_path=arguments.build_manifest,
            build_manifest_sha256=arguments.build_manifest_sha256,
            output_root=arguments.output_root,
        )
    except PackError as error:
        receipt = {
            "contract": CONTRACT, "passed": False, "error_code": error.code,
            "artifact_sha256": None, "artifact_size_bytes": 0,
            "candidate_files_verified": 0, "validation_enabled": True,
            "owned_cleanup_confirmed": error.owned_cleanup_confirmed,
            "stage": error.stage, "sdk_exit_code": error.sdk_exit_code,
            "owned_failure_code": error.owned_failure_code,
            "stdout_diagnostics": error.stdout_diagnostics,
            "signed": False, "installed": False,
        }
    except Exception:
        receipt = {
            "contract": CONTRACT, "passed": False, "error_code": "internal_error",
            "artifact_sha256": None, "artifact_size_bytes": 0,
            "candidate_files_verified": 0, "validation_enabled": True,
            "owned_cleanup_confirmed": None, "stage": "internal",
            "sdk_exit_code": None, "owned_failure_code": None,
            "signed": False, "installed": False,
        }
    print("UNSIGNED_MSIX_PACK=" + json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
