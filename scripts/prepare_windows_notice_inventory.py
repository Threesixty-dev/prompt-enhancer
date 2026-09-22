"""Inventory license evidence in one exact Windows stage; do not resolve it."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
from email.policy import compat32
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys

from packaging.utils import InvalidName, canonicalize_name
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "src", Path(__file__).resolve().parent):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from prompt_enhancer.application.build_evidence.manifest import (  # noqa: E402
    MAX_MANIFEST_BYTES, BuildManifest, _validate_staged_relative_path,
    build_manifest, canonical_json,
)
from prompt_enhancer.application.paths.policy import classify_windows_path_text  # noqa: E402
from pack_msix_candidate import _ordinary_ancestors, _read_regular  # noqa: E402

CONTRACT = "windows-notice-evidence-inventory.v1"
MAX_METADATA_BYTES = 1024 * 1024
MAX_LICENSE_BYTES = 16 * 1024 * 1024
MAX_LICENSE_FILES = 1024
MAX_REPORT_BYTES = 16 * 1024 * 1024
HOME = Path.home().resolve()


class InventoryError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise InventoryError("invalid_arguments")

    def exit(self, _status: int = 0, _message: str | None = None) -> None:
        raise InventoryError("invalid_arguments")


def _sha(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise InventoryError("invalid_manifest_identity")
    return value


def _safe_absolute(value: object) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise InventoryError("unsafe_path")
    raw = os.fspath(value)
    windows = PureWindowsPath(raw)
    if (not raw or ".." in Path(raw).parts or ".." in windows.parts
            or classify_windows_path_text(raw) is not None
            or (os.name == "nt" and windows.root and not windows.drive)):
        raise InventoryError("unsafe_path")
    path = Path(raw)
    if not path.is_absolute():
        raise InventoryError("unsafe_path")
    return path


def _output_path(value: object) -> Path:
    path = _safe_absolute(value)
    if path.exists() or path.is_symlink() or not path.name:
        raise InventoryError("unsafe_output")
    try:
        _ordinary_ancestors(path.parent)
        result = path.parent.resolve(strict=True) / path.name
    except Exception as error:
        raise InventoryError("unsafe_output") from error
    for protected in (ROOT.resolve(), HOME):
        if result == protected or result.is_relative_to(protected) or protected.is_relative_to(result):
            raise InventoryError("unsafe_output")
    return result


def _manifest(path: Path, expected_sha256: str) -> tuple[BuildManifest, bytes]:
    try:
        raw = _read_regular(_safe_absolute(path), MAX_MANIFEST_BYTES)
    except InventoryError:
        raise
    except Exception:
        raise InventoryError("manifest_unavailable") from None
    if hashlib.sha256(raw).hexdigest() != _sha(expected_sha256):
        raise InventoryError("manifest_identity_mismatch")
    try:
        manifest = BuildManifest.model_validate_json(raw)
    except Exception:
        raise InventoryError("invalid_manifest") from None
    if canonical_json(manifest) != raw:
        raise InventoryError("manifest_not_canonical")
    return manifest, raw


def _verified_files(stage: Path, manifest: BuildManifest, raw: bytes) -> dict[str, object]:
    stage = _safe_absolute(stage)
    try:
        observed = build_manifest(
            stage, git_revision=manifest.git_revision,
            tool_versions={item.name: item.version for item in manifest.tool_versions},
            lockfile_hashes={item.name: item.sha256 for item in manifest.lockfile_hashes},
        )
    except Exception:
        raise InventoryError("stage_verification_failed") from None
    if canonical_json(observed) != raw:
        raise InventoryError("stage_manifest_mismatch")
    return {item.relative_path: item for item in manifest.files}


def _read_bound(stage: Path, files: dict[str, object], relative: str, maximum: int) -> bytes:
    item = files.get(relative)
    if item is None:
        raise InventoryError("license_evidence_missing")
    if item.size_bytes > maximum:
        raise InventoryError("license_evidence_oversize")
    try:
        data = _read_regular(stage.joinpath(*relative.split("/")), maximum)
    except Exception:
        raise InventoryError("stage_file_changed") from None
    if len(data) != item.size_bytes or hashlib.sha256(data).hexdigest() != item.sha256:
        raise InventoryError("stage_file_changed")
    return data


def _one_header(message: object, name: str, *, required: bool = False) -> str | None:
    values = message.get_all(name) or []
    if len(values) > 1 or (required and len(values) != 1):
        raise InventoryError("metadata_invalid")
    value = values[0] if values else None
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise InventoryError("metadata_invalid")
    return value


def _license_relative(value: str) -> str:
    try:
        normalized = _validate_staged_relative_path(value)
    except Exception:
        raise InventoryError("license_file_path_unsafe") from None
    if PurePosixPath(normalized).is_absolute():
        raise InventoryError("license_file_path_unsafe")
    return normalized


def _distribution_identity(name: str, version: str) -> tuple[str, str]:
    if (len(name) > 128 or len(version) > 128
            or re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", name) is None):
        raise InventoryError("metadata_invalid")
    try:
        canonical_name = str(canonicalize_name(name, validate=True))
        canonical_version = str(Version(version))
    except (InvalidName, InvalidVersion, TypeError):
        raise InventoryError("metadata_invalid") from None
    return canonical_name, canonical_version


def _separate_inputs(stage: Path, manifest: Path, output: Path) -> None:
    if (stage == manifest or manifest.is_relative_to(stage) or stage.is_relative_to(manifest)
            or output == manifest or output == stage
            or output.is_relative_to(stage) or stage.is_relative_to(output)
            or output.is_relative_to(manifest) or manifest.is_relative_to(output)):
        raise InventoryError("path_overlap")


def build_inventory_report(*, stage_root: Path, build_manifest_path: Path,
                           build_manifest_sha256: str) -> tuple[dict[str, object], bytes]:
    stage = _safe_absolute(stage_root)
    manifest_path = _safe_absolute(build_manifest_path)
    if stage == manifest_path or manifest_path.is_relative_to(stage) or stage.is_relative_to(manifest_path):
        raise InventoryError("path_overlap")
    manifest, raw = _manifest(manifest_path, build_manifest_sha256)
    files = _verified_files(stage, manifest, raw)
    metadata_paths = sorted(
        path for path in files
        if path.count("/") == 1 and path.endswith(".dist-info/METADATA")
    )
    if not metadata_paths:
        raise InventoryError("distribution_inventory_empty")
    distributions: list[dict[str, object]] = []
    identities: set[str] = set()
    for metadata_path in metadata_paths:
        dist_info = metadata_path.rsplit("/", 1)[0]
        payload = _read_bound(stage, files, metadata_path, MAX_METADATA_BYTES)
        try:
            metadata = BytesParser(policy=compat32).parsebytes(payload)
            name = _one_header(metadata, "Name", required=True)
            version = _one_header(metadata, "Version", required=True)
            license_value = _one_header(metadata, "License")
            license_expression = _one_header(metadata, "License-Expression")
        except InventoryError:
            raise
        except Exception:
            raise InventoryError("metadata_invalid") from None
        assert name is not None and version is not None
        identity, normalized_version = _distribution_identity(name, version)
        if identity in identities:
            raise InventoryError("distribution_identity_duplicate")
        identities.add(identity)
        declared = tuple(_license_relative(value) for value in (metadata.get_all("License-File") or []))
        if len(declared) != len(set(item.casefold() for item in declared)):
            raise InventoryError("metadata_invalid")
        discovered = sorted(
            path for path in files if path.startswith(f"{dist_info}/licenses/")
            and path.count("/") >= 2
        )
        if len(discovered) > MAX_LICENSE_FILES:
            raise InventoryError("license_evidence_oversize")
        declared_installed = {f"{dist_info}/licenses/{value}" for value in declared}
        if not declared_installed <= set(discovered):
            raise InventoryError("license_evidence_missing")
        evidence = []
        for relative in discovered:
            data = _read_bound(stage, files, relative, MAX_LICENSE_BYTES)
            evidence.append({
                "relative_path": relative.removeprefix(f"{dist_info}/licenses/"),
                "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "declared": relative in declared_installed,
            })
        distributions.append({
            "name": name, "version": version,
            "normalized_name": identity, "normalized_version": normalized_version,
            "metadata_sha256": hashlib.sha256(payload).hexdigest(),
            "license": license_value, "license_expression": license_expression,
            "license_files": evidence,
        })
    runtime = _read_bound(stage, files, "LICENSE.txt", MAX_LICENSE_BYTES)
    by_name = {item["normalized_name"]: item for item in distributions}
    proxy = by_name.get("proxy-tools")
    application = by_name.get("prompt-enhancer")
    application_license_missing = bool(application is not None and not (
        application["license"] or application["license_expression"] or application["license_files"]))
    gaps = ["frontend_notice_inventory_missing", "rendered_third_party_notices_missing"]
    if proxy is not None:
        gaps.append("proxy_tools_license_discrepancy_review_required")
    if application_license_missing:
        gaps.append("application_license_missing")
    unknown_count = sum(
        not (item["license"] or item["license_expression"] or item["license_files"])
        for item in distributions
    )
    report: dict[str, object] = {
        "contract": CONTRACT,
        "stage_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "stage_files_verified": len(files),
        "distribution_count": len(distributions),
        "distributions_with_declared_license_count": sum(
            bool(item["license"] or item["license_expression"]) for item in distributions
        ),
        "distributions_with_license_files_count": sum(bool(item["license_files"]) for item in distributions),
        "unknown_license_distribution_count": unknown_count,
        "distributions": sorted(distributions, key=lambda item: (str(item["name"]).casefold(), str(item["version"]))),
        "runtime_license": {"relative_path": "LICENSE.txt", "size_bytes": len(runtime),
                            "sha256": hashlib.sha256(runtime).hexdigest()},
        "all_declared_license_files_present": True,
        "proxy_tools_license_discrepancy_review_required": proxy is not None,
        "application_license_missing": application_license_missing,
        "frontend_notice_inventory_missing": True,
        "rendered_third_party_notices_missing": True,
        "spdx_sbom_claimed": False,
        "unresolved_gaps": sorted(gaps),
        "complete": False,
        "release_accepted": False,
    }
    encoded = json.dumps(report, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"
    if len(encoded) > MAX_REPORT_BYTES:
        raise InventoryError("report_oversize")
    return report, encoded


def inventory(*, stage_root: Path, build_manifest_path: Path,
              build_manifest_sha256: str, output_path: Path) -> dict[str, object]:
    stage = _safe_absolute(stage_root)
    manifest_path = _safe_absolute(build_manifest_path)
    destination = _output_path(output_path)
    _separate_inputs(stage, manifest_path, destination)
    report, encoded = build_inventory_report(
        stage_root=stage,
        build_manifest_path=manifest_path,
        build_manifest_sha256=build_manifest_sha256,
    )
    try:
        with destination.open("xb") as stream:
            stream.write(encoded)
    except OSError as error:
        raise InventoryError("output_write_failed") from error
    try:
        if _read_regular(destination, MAX_REPORT_BYTES) != encoded:
            raise InventoryError("output_write_failed")
    except InventoryError:
        raise
    except Exception:
        raise InventoryError("output_write_failed") from None
    return {"contract": CONTRACT, "passed": True,
            "distribution_count": report["distribution_count"],
            "stage_files_verified": report["stage_files_verified"],
            "all_declared_license_files_present": True,
            "proxy_tools_license_discrepancy_review_required":
                report["proxy_tools_license_discrepancy_review_required"],
            "application_license_missing": report["application_license_missing"],
            "frontend_notice_inventory_missing": True, "complete": False,
            "release_accepted": False, "report_sha256": hashlib.sha256(encoded).hexdigest()}


def main(argv: list[str] | None = None) -> int:
    try:
        parser = Parser()
        parser.add_argument("--stage-root", type=Path, required=True)
        parser.add_argument("--build-manifest", type=Path, required=True)
        parser.add_argument("--build-manifest-sha256", required=True)
        parser.add_argument("--output", type=Path, required=True)
        arguments = parser.parse_args(argv)
        receipt = inventory(
            stage_root=arguments.stage_root,
            build_manifest_path=arguments.build_manifest,
            build_manifest_sha256=arguments.build_manifest_sha256,
            output_path=arguments.output,
        )
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 0
    except InventoryError as error:
        code = str(error) if re.fullmatch(r"[a-z_]+", str(error)) else "inventory_failed"
        print(json.dumps({"contract": CONTRACT, "passed": False, "error_code": code},
                         sort_keys=True, separators=(",", ":")))
        return 2
    except Exception:
        print(json.dumps({"contract": CONTRACT, "passed": False,
                          "error_code": "inventory_failed"},
                         sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
