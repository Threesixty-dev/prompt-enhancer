"""Synthetic mocked SDK extraction; never runs native tools."""
import hashlib
from pathlib import Path
import sys
from zipfile import ZipFile, ZipInfo
import stat

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_msix_sdk_unpack as helper
from prompt_enhancer.application.build_evidence.manifest import build_manifest, canonical_json
from prompt_enhancer.application.owned_process import OwnedProcessResult, OwnedProcessRunError


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(helper.pack, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(helper.pack, "HOME_ROOT", tmp_path / "reserved-home")
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AppxManifest.xml").write_bytes(b"synthetic")
    manifest = canonical_json(build_manifest(candidate, git_revision="a" * 40, tool_versions={}, lockfile_hashes={}))
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(manifest)
    package = tmp_path / "synthetic.msix"
    with ZipFile(package, "w") as archive:
        for name in ("AppxManifest.xml", *helper.pack.SDK_MEMBERS):
            archive.writestr(name, b"synthetic")
    sdk = tmp_path / "makeappx.exe"
    sdk.write_bytes(b"synthetic-sdk")
    return dict(package=package, package_sha256=hashlib.sha256(package.read_bytes()).hexdigest(), package_size=package.stat().st_size,
                manifest_path=manifest_path, manifest_sha256=hashlib.sha256(manifest).hexdigest(), output=tmp_path / "extracted",
                sdk_path=sdk, sdk_sha256=hashlib.sha256(sdk.read_bytes()).hexdigest(), sdk_size=sdk.stat().st_size)


def runner(mode="success"):
    def run(command, **kwargs):
        assert command[1] == "unpack" and command[-1] == "/no"
        assert not {"/nv", "/v", "/pfn"} & set(command)
        assert kwargs["timeout"] == 120 and kwargs["maximum_active_processes"] == 1
        assert kwargs["stderr_limit"] == 16 * 1024
        if mode == "cleanup":
            raise OwnedProcessRunError("owned_process_cleanup_unconfirmed")
        source, output = Path(command[3]), Path(command[5])
        output.mkdir()
        with ZipFile(source) as archive:
            for name in archive.namelist():
                if name == "[Content_Types].xml":
                    continue
                if mode == "missing" and name == "AppxManifest.xml":
                    continue
                (output / name).write_bytes(b"changed" if mode == "hash" else archive.read(name))
        if mode == "extra":
            (output / "extra.txt").write_bytes(b"synthetic")
        with ZipFile(source) as archive:
            names = [name for name in archive.namelist() if name != "[Content_Types].xml"]
        policy = helper.UnpackPolicy(str(source), str(output), names)
        assert kwargs["stdout_limit"] == policy.byte_limit
        selected = {}
        for line, key in policy.lines.items():
            if key != "success":
                selected[key] = line
        data = ("\r\r\n".join(selected.values()) + "\r\r\n" + policy.footer).encode()
        if mode == "unknown":
            data = b"unknown synthetic\n" + data
        if mode == "changed":
            source.write_bytes(b"changed")
        return OwnedProcessResult(returncode=1 if mode == "error" else 0, stdout=data, stderr=b"")
    return run


def test_verified_mock_extraction(tmp_path, monkeypatch):
    result = helper.verify(**fixture(tmp_path, monkeypatch), runner=runner())
    assert result["passed"] and result["payload_files"] == 1
    assert result["archive_footprints_verified"] == 2 and result["extracted_footprints"] == 1
    assert result["omitted_by_sdk"] == ["[Content_Types].xml"]
    assert result["installability_claim"] is False and result["launched"] is False


@pytest.mark.parametrize("mode", ["unknown", "error", "extra", "missing", "hash", "changed", "cleanup"])
def test_fail_closed(tmp_path, monkeypatch, mode):
    with pytest.raises(helper.pack.PackError):
        helper.verify(**fixture(tmp_path, monkeypatch), runner=runner(mode))


def test_existing_output_refused_before_sdk(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    args["output"].mkdir()
    with pytest.raises(helper.pack.PackError):
        helper.verify(**args, runner=lambda *a, **k: pytest.fail("no SDK"))


@pytest.mark.parametrize("code,cleanup", [("owned_process_stdout_limit", True), ("owned_process_stderr_limit", True),
    ("owned_process_timeout", True), ("owned_process_cleanup_unconfirmed", False), ("untrusted-canary", None)])
def test_owned_error_evidence(tmp_path, monkeypatch, code, cleanup):
    def fail(*args, **kwargs):
        raise OwnedProcessRunError(code)
    with pytest.raises(helper.pack.PackError) as caught:
        helper.verify(**fixture(tmp_path, monkeypatch), runner=fail)
    assert caught.value.owned_cleanup_confirmed is cleanup
    assert caught.value.owned_failure_code == (code if code in helper.pack.OWNED_FAILURE_CODES else None)


def test_sdk_nonzero_evidence(tmp_path, monkeypatch):
    with pytest.raises(helper.pack.PackError) as caught:
        helper.verify(**fixture(tmp_path, monkeypatch), runner=runner("error"))
    assert caught.value.sdk_exit_code == 1
    assert caught.value.owned_cleanup_confirmed is True


def test_symlink_metadata_refused_before_sdk(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    with ZipFile(args["package"], "w") as archive:
        for name in ("AppxManifest.xml", *helper.pack.SDK_MEMBERS):
            info = ZipInfo(name)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"synthetic")
    args["package_sha256"] = hashlib.sha256(args["package"].read_bytes()).hexdigest()
    args["package_size"] = args["package"].stat().st_size
    with pytest.raises(helper.pack.PackError, match="unsafe_archive_member"):
        helper.verify(**args, runner=lambda *a, **k: pytest.fail("no SDK"))


def test_archive_content_types_still_required(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    with ZipFile(args["package"], "w") as archive:
        archive.writestr("AppxManifest.xml", b"synthetic")
        archive.writestr("AppxBlockMap.xml", b"synthetic")
    args["package_sha256"] = hashlib.sha256(args["package"].read_bytes()).hexdigest()
    args["package_size"] = args["package"].stat().st_size
    with pytest.raises(helper.pack.PackError):
        helper.verify(**args, runner=lambda *a, **k: pytest.fail("no SDK"))


def test_extracted_blockmap_still_required(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    def missing_blockmap(command, **kwargs):
        result = runner()(command, **kwargs)
        (Path(command[5]) / "AppxBlockMap.xml").unlink()
        return result
    with pytest.raises(helper.pack.PackError, match="extracted_payload_mismatch"):
        helper.verify(**args, runner=missing_blockmap)
