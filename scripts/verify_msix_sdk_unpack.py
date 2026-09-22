"""Independent SDK extraction verification, not installation acceptance."""
import hashlib
import json
import os
from pathlib import Path
import sys
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_msix_candidate as pack
from msix_sdk_output import UnpackPolicy, OutputError
from prompt_enhancer.application.owned_process import run_owned_process, OwnedProcessRunError
from prompt_enhancer.application.build_evidence.manifest import build_manifest
from prompt_enhancer.infrastructure.updates.msix_preflight import _unsafe_member


def verify(*, package, package_sha256, package_size, manifest_path, manifest_sha256, output,
           sdk_path=pack.SDK_PATH, sdk_sha256=pack.SDK_SHA256, sdk_size=pack.SDK_SIZE,
           runner=run_owned_process):
    package = pack._safe_absolute(str(package))
    output = pack._fresh_external_output(str(output))
    manifest_path = pack._safe_absolute(str(manifest_path))
    sdk_path = pack._safe_absolute(str(sdk_path))
    manifest, canonical = pack._manifest(manifest_path, manifest_sha256)
    if len(manifest.files) > 9998 or pack._hash_package(package) != (package_sha256, package_size):
        raise pack.PackError("input_identity_mismatch")
    pack._verify_package(package, manifest)
    sdk = pack._read_regular(sdk_path, 1024 * 1024)
    if len(sdk) != sdk_size or hashlib.sha256(sdk).hexdigest() != sdk_sha256:
        raise pack.PackError("sdk_identity_mismatch")
    expected = {item.relative_path: (item.size_bytes, item.sha256) for item in manifest.files}
    with ZipFile(package) as archive:
        if any(_unsafe_member(info) for info in archive.infolist()):
            raise pack.PackError("unsafe_archive_member")
        for name in pack.SDK_MEMBERS:
            info = archive.getinfo(name)
            if info.is_dir() or info.flag_bits & 1 or not 0 < info.file_size <= 16 * 1024 * 1024:
                raise pack.PackError("package_sdk_member_invalid")
            with archive.open(info) as stream:
                data = stream.read(16 * 1024 * 1024 + 1)
            if len(data) != info.file_size:
                raise pack.PackError("package_sdk_member_invalid")
            expected[name] = (len(data), hashlib.sha256(data).hexdigest())
    # Pinned SDK unpack intentionally omits this OPC footprint. It remains
    # mandatory in the verified archive and is protected by its unchanged hash.
    del expected["[Content_Types].xml"]
    policy = UnpackPolicy(str(package), str(output), expected)
    # Existing parent is an explicit synthetic workspace, not the extraction
    # directory; MakeAppx must create the latter without overwrite permission.
    environment = {"SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
                   "WINDIR": os.environ.get("SystemRoot", r"C:\Windows"),
                   **{key: str(output.parent) for key in ("TEMP", "TMP", "HOME", "USERPROFILE")},
                   "PATH": str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")}
    try:
        result = runner([str(sdk_path), "unpack", "/p", str(package), "/d", str(output), "/no"],
                        cwd=output.parent, env=environment, timeout=120, maximum_active_processes=1,
                        stdout_limit=policy.byte_limit, stderr_limit=16 * 1024)
    except OwnedProcessRunError as error:
        code = error.code if error.code in pack.OWNED_FAILURE_CODES else None
        cleanup = False if code == "owned_process_cleanup_unconfirmed" else True if code in {
            "owned_process_stdout_limit", "owned_process_stderr_limit", "owned_process_timeout"} else None
        raise pack.PackError("sdk_run_failed", stage="sdk", owned_failure_code=code,
                             owned_cleanup_confirmed=cleanup) from None
    if result.returncode != 0 or result.stderr:
        raise pack.PackError("sdk_unpack_failed", stage="sdk", owned_cleanup_confirmed=True, sdk_exit_code=result.returncode)
    try:
        stdout = policy.validate(result.stdout)
    except OutputError as error:
        raise pack.PackError(str(error), stage="sdk", owned_cleanup_confirmed=True, sdk_exit_code=0, stdout_diagnostics=error.diagnostics) from None
    try:
        if pack._read_regular(sdk_path, 1024 * 1024) != sdk or pack._read_regular(manifest_path, pack.MAX_MANIFEST_BYTES) != canonical:
            raise pack.PackError("input_changed")
        if pack._hash_package(package) != (package_sha256, package_size):
            raise pack.PackError("package_changed")
        observed = build_manifest(output, git_revision=manifest.git_revision, tool_versions={}, lockfile_hashes={})
        actual = {item.relative_path: (item.size_bytes, item.sha256) for item in observed.files}
        if actual != expected:
            raise pack.PackError("extracted_payload_mismatch")
    except Exception as error:
        code = error.code if isinstance(error, pack.PackError) else "extracted_verification_failed"
        raise pack.PackError(code, stage="post_unpack", owned_cleanup_confirmed=True, sdk_exit_code=0) from None
    return {"contract": "msix-sdk-unpack.v1", "passed": True, "payload_files": len(manifest.files),
            "archive_footprints_verified": len(pack.SDK_MEMBERS), "extracted_footprints": 1,
            "omitted_by_sdk": ["[Content_Types].xml"], "owned_cleanup_confirmed": True,
            "validation_enabled": True, "installability_claim": False, "signed": False,
            "installed": False, "launched": False, **stdout}


def main(argv=None):
    try:
        parser = pack._ClosedParser(add_help=False)
        for name in ("package", "package-sha256", "manifest-path", "manifest-sha256", "output"):
            parser.add_argument("--" + name, required=True)
        parser.add_argument("--package-size", type=int, required=True)
        receipt = verify(**vars(parser.parse_args(argv)))
    except Exception as error:
        receipt = {"contract": "msix-sdk-unpack.v1", "passed": False,
                   "error_code": error.code if isinstance(error, pack.PackError) else "unpack_verification_failed",
                   "owned_cleanup_confirmed": error.owned_cleanup_confirmed if isinstance(error, pack.PackError) else None,
                   "stage": error.stage if isinstance(error, pack.PackError) else "internal",
                   "sdk_exit_code": error.sdk_exit_code if isinstance(error, pack.PackError) else None,
                   "owned_failure_code": error.owned_failure_code if isinstance(error, pack.PackError) else None,
                   "stdout_diagnostics": error.stdout_diagnostics if isinstance(error, pack.PackError) else None}
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
