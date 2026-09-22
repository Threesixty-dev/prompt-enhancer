"""Render hash-bound Windows license evidence without resolving legal gaps."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
from email.policy import compat32
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "src", Path(__file__).resolve().parent):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import prepare_windows_notice_inventory as inventory_source  # noqa: E402

CONTRACT = "windows-third-party-notices-renderer.v1"
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
ERROR_CODES = frozenset({
    "distribution_identity_duplicate", "distribution_inventory_empty",
    "input_changed", "invalid_arguments", "invalid_identity", "invalid_manifest",
    "invalid_manifest_identity", "inventory_identity_mismatch", "inventory_invalid",
    "inventory_stage_mismatch", "inventory_unavailable", "license_evidence_mismatch",
    "license_evidence_missing", "license_evidence_oversize", "license_file_path_unsafe",
    "license_text_decode_failed", "manifest_identity_mismatch", "manifest_not_canonical",
    "manifest_unavailable", "metadata_invalid", "notice_output_oversize", "output_write_failed",
    "path_overlap", "report_oversize", "stage_file_changed", "stage_manifest_mismatch",
    "stage_verification_failed", "unsafe_output", "unsafe_path",
})


class RenderError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise RenderError("invalid_arguments")

    def exit(self, _status: int = 0, _message: str | None = None) -> None:
        raise RenderError("invalid_arguments")


def _sha(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise RenderError("invalid_identity")
    return value


def _paths(stage_root: Path, manifest_path: Path, inventory_path: Path,
           output_path: Path) -> tuple[Path, Path, Path, Path]:
    try:
        stage = inventory_source._safe_absolute(stage_root)
        manifest = inventory_source._safe_absolute(manifest_path)
        notice_inventory = inventory_source._safe_absolute(inventory_path)
        output = inventory_source._output_path(output_path)
    except Exception:
        raise RenderError("unsafe_path") from None
    inputs = (stage, manifest, notice_inventory)
    if any(
        left == right or left.is_relative_to(right) or right.is_relative_to(left)
        for index, left in enumerate(inputs) for right in inputs[index + 1:]
    ) or any(
        output == item or output.is_relative_to(item) or item.is_relative_to(output)
        for item in inputs
    ):
        raise RenderError("path_overlap")
    return stage, manifest, notice_inventory, output


def _read(path: Path, maximum: int, code: str) -> bytes:
    try:
        return inventory_source._read_regular(path, maximum)
    except Exception:
        raise RenderError(code) from None


def _text(payload: bytes) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        raise RenderError("license_text_decode_failed") from None


def _bounded_append(parts: list[str], value: str, size: list[int]) -> None:
    encoded_size = len(value.encode("utf-8"))
    if encoded_size > MAX_OUTPUT_BYTES - size[0]:
        raise RenderError("notice_output_oversize")
    parts.append(value)
    size[0] += encoded_size


def render(*, stage_root: Path, build_manifest_path: Path,
           build_manifest_sha256: str, notice_inventory_path: Path,
           notice_inventory_sha256: str, output_path: Path) -> dict[str, object]:
    stage, manifest_path, inventory_path, destination = _paths(
        stage_root, build_manifest_path, notice_inventory_path, output_path,
    )
    manifest_sha = _sha(build_manifest_sha256)
    inventory_sha = _sha(notice_inventory_sha256)
    raw_inventory = _read(
        inventory_path, inventory_source.MAX_REPORT_BYTES, "inventory_unavailable",
    )
    if hashlib.sha256(raw_inventory).hexdigest() != inventory_sha:
        raise RenderError("inventory_identity_mismatch")
    try:
        observed_report = json.loads(raw_inventory)
    except Exception:
        raise RenderError("inventory_invalid") from None
    if not isinstance(observed_report, dict):
        raise RenderError("inventory_invalid")
    expected_report, expected_bytes = inventory_source.build_inventory_report(
        stage_root=stage,
        build_manifest_path=manifest_path,
        build_manifest_sha256=manifest_sha,
    )
    if raw_inventory != expected_bytes or observed_report != expected_report:
        raise RenderError("inventory_stage_mismatch")

    manifest, raw_manifest = inventory_source._manifest(manifest_path, manifest_sha)
    files = inventory_source._verified_files(stage, manifest, raw_manifest)
    dist_info_by_name: dict[str, str] = {}
    for relative in sorted(
        path for path in files if path.count("/") == 1 and path.endswith(".dist-info/METADATA")
    ):
        payload = inventory_source._read_bound(
            stage, files, relative, inventory_source.MAX_METADATA_BYTES,
        )
        try:
            message = BytesParser(policy=compat32).parsebytes(payload)
            name = inventory_source._one_header(message, "Name", required=True)
            version = inventory_source._one_header(message, "Version", required=True)
            assert name is not None and version is not None
            normalized, _ = inventory_source._distribution_identity(name, version)
        except Exception:
            raise RenderError("metadata_invalid") from None
        if normalized in dist_info_by_name:
            raise RenderError("metadata_invalid")
        dist_info_by_name[normalized] = relative.rsplit("/", 1)[0]

    parts: list[str] = []
    size = [0]
    def append(value: str) -> None:
        _bounded_append(parts, value, size)

    append("PROMPT ENHANCER THIRD-PARTY NOTICE EVIDENCE\n")
    append("NOT A LEGAL, RELEASE-COMPLETENESS, OR INSTALLATION CLAIM\n")
    append(f"stage_manifest_sha256: {manifest_sha}\n")
    append(f"inventory_sha256: {inventory_sha}\n")
    append("complete: false\nrelease_accepted: false\n\n")
    append("UNRESOLVED WARNINGS\n")
    for warning in expected_report["unresolved_gaps"]:
        if warning != "rendered_third_party_notices_missing":
            append(f"- {warning}\n")
    append("\n")

    runtime = expected_report["runtime_license"]
    runtime_bytes = inventory_source._read_bound(
        stage, files, str(runtime["relative_path"]), inventory_source.MAX_LICENSE_BYTES,
    )
    if len(runtime_bytes) != runtime["size_bytes"] or hashlib.sha256(runtime_bytes).hexdigest() != runtime["sha256"]:
        raise RenderError("license_evidence_mismatch")
    append("CPYTHON RUNTIME LICENSE\n")
    append(f"source_sha256: {runtime['sha256']}\n----- BEGIN LICENSE TEXT -----\n")
    append(_text(runtime_bytes))
    if not runtime_bytes.endswith(b"\n"):
        append("\n")
    append("----- END LICENSE TEXT -----\n\n")

    license_count = 0
    distributions = expected_report["distributions"]
    for distribution in distributions:
        normalized = str(distribution["normalized_name"])
        dist_info = dist_info_by_name.get(normalized)
        if dist_info is None:
            raise RenderError("inventory_stage_mismatch")
        append("DISTRIBUTION\n")
        append(f"name: {json.dumps(distribution['name'], ensure_ascii=True)}\n")
        append(f"version: {json.dumps(distribution['version'], ensure_ascii=True)}\n")
        append(f"normalized_name: {normalized}\n")
        append(f"normalized_version: {distribution['normalized_version']}\n")
        append(f"metadata_sha256: {distribution['metadata_sha256']}\n")
        append(f"license: {json.dumps(distribution['license'], ensure_ascii=True)}\n")
        append(f"license_expression: {json.dumps(distribution['license_expression'], ensure_ascii=True)}\n")
        evidence = distribution["license_files"]
        if not evidence:
            append("license_text_evidence: absent\n\n")
            continue
        for item in evidence:
            relative = f"{dist_info}/licenses/{item['relative_path']}"
            payload = inventory_source._read_bound(
                stage, files, relative, inventory_source.MAX_LICENSE_BYTES,
            )
            digest = hashlib.sha256(payload).hexdigest()
            if len(payload) != item["size_bytes"] or digest != item["sha256"]:
                raise RenderError("license_evidence_mismatch")
            append(f"license_file: {json.dumps(item['relative_path'], ensure_ascii=True)}\n")
            append(f"source_sha256: {digest}\n")
            append(f"declared: {str(bool(item['declared'])).lower()}\n")
            append("----- BEGIN LICENSE TEXT -----\n")
            append(_text(payload))
            if not payload.endswith(b"\n"):
                append("\n")
            append("----- END LICENSE TEXT -----\n")
            license_count += 1
        append("\n")

    encoded = "".join(parts).encode("utf-8")
    if not encoded or len(encoded) > MAX_OUTPUT_BYTES:
        raise RenderError("notice_output_oversize")
    if _read(inventory_path, inventory_source.MAX_REPORT_BYTES, "input_changed") != raw_inventory:
        raise RenderError("input_changed")
    final_manifest, final_manifest_raw = inventory_source._manifest(manifest_path, manifest_sha)
    if final_manifest_raw != raw_manifest:
        raise RenderError("input_changed")
    try:
        inventory_source._verified_files(stage, final_manifest, final_manifest_raw)
    except Exception:
        raise RenderError("input_changed") from None
    try:
        with destination.open("xb") as stream:
            stream.write(encoded)
        if _read(destination, MAX_OUTPUT_BYTES, "output_write_failed") != encoded:
            raise RenderError("output_write_failed")
    except RenderError:
        raise
    except OSError:
        raise RenderError("output_write_failed") from None
    return {
        "contract": CONTRACT,
        "passed": True,
        "distribution_count": len(distributions),
        "license_file_count": license_count,
        "source_files_verified": len(distributions) + license_count + 1,
        "application_license_missing": bool(expected_report["application_license_missing"]),
        "proxy_tools_license_discrepancy_review_required": bool(
            expected_report["proxy_tools_license_discrepancy_review_required"]
        ),
        "frontend_notice_inventory_missing": True,
        "complete": False,
        "release_accepted": False,
        "artifact_sha256": hashlib.sha256(encoded).hexdigest(),
        "artifact_size_bytes": len(encoded),
    }


def main(argv: list[str] | None = None) -> int:
    try:
        parser = Parser()
        parser.add_argument("--stage-root", type=Path, required=True)
        parser.add_argument("--build-manifest", type=Path, required=True)
        parser.add_argument("--build-manifest-sha256", required=True)
        parser.add_argument("--notice-inventory", type=Path, required=True)
        parser.add_argument("--notice-inventory-sha256", required=True)
        parser.add_argument("--output", type=Path, required=True)
        args = parser.parse_args(argv)
        receipt = render(
            stage_root=args.stage_root,
            build_manifest_path=args.build_manifest,
            build_manifest_sha256=args.build_manifest_sha256,
            notice_inventory_path=args.notice_inventory,
            notice_inventory_sha256=args.notice_inventory_sha256,
            output_path=args.output,
        )
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 0
    except (RenderError, inventory_source.InventoryError) as error:
        value = str(error)
        code = value if value in ERROR_CODES else "render_failed"
        print(json.dumps({"contract": CONTRACT, "passed": False, "error_code": code},
                         sort_keys=True, separators=(",", ":")))
        return 2
    except Exception:
        print(json.dumps({"contract": CONTRACT, "passed": False, "error_code": "render_failed"},
                         sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
