from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from prompt_enhancer.application.build_evidence.manifest import build_manifest, canonical_json
from prompt_enhancer.application.owned_process import OwnedProcessResult, OwnedProcessRunError


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pack_msix_candidate.py"
SPEC = importlib.util.spec_from_file_location("pack_msix_candidate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PACK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PACK
SPEC.loader.exec_module(PACK)


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AppxManifest.xml").write_bytes(b"<Package>synthetic</Package>\n")
    (candidate / "PromptEnhancer.exe").write_bytes(b"synthetic-launcher")
    (candidate / "Assets").mkdir()
    (candidate / "Assets" / "StoreLogo.png").write_bytes(b"synthetic-logo")
    manifest = build_manifest(
        candidate, git_revision="a" * 40,
        tool_versions={"fixture": "1.0"}, lockfile_hashes={"fixture": "b" * 64},
    )
    raw_manifest = canonical_json(manifest)
    manifest_path = tmp_path / "candidate-build-manifest.json"
    manifest_path.write_bytes(raw_manifest)
    sdk = tmp_path / "makeappx.exe"
    sdk.write_bytes(b"synthetic-sdk")
    monkeypatch.setattr(PACK, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(PACK, "HOME_ROOT", tmp_path / "reserved-home")
    return {
        "candidate_root": str(candidate.resolve()),
        "build_manifest_path": str(manifest_path.resolve()),
        "build_manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "output_root": str((tmp_path / "output").resolve()),
        "sdk_path": sdk.resolve(),
        "sdk_sha256": hashlib.sha256(sdk.read_bytes()).hexdigest(),
        "sdk_size": sdk.stat().st_size,
    }


def _successful_runner(
    candidate: Path, *, omit: str | None = None, mutate: str | None = None,
    backslashes: bool = False,
):
    def run(command: list[str], **kwargs: object) -> OwnedProcessResult:
        assert command[1:] == [
            "pack", "/d", str(candidate), "/p", str(Path(kwargs["cwd"]) / PACK.PACKAGE_NAME),
            "/h", "SHA256", "/no",
        ]
        assert "/nv" not in command and "/v" not in command
        assert kwargs["timeout"] == 120
        assert kwargs["maximum_active_processes"] == 1
        assert kwargs["stderr_limit"] == 16 * 1024
        assert set(kwargs["env"]) == {"SystemRoot", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "PATH"}
        package = Path(kwargs["cwd"]) / PACK.PACKAGE_NAME
        with ZipFile(package, "w", ZIP_DEFLATED) as archive:
            for path in sorted(candidate.rglob("*")):
                if path.is_file() and path.relative_to(candidate).as_posix() != omit:
                    payload = path.read_bytes()
                    if path.relative_to(candidate).as_posix() == mutate:
                        payload += b"changed"
                    name = path.relative_to(candidate).as_posix()
                    archive.writestr(name.replace("/", "\\") if backslashes else name, payload)
            archive.writestr("[Content_Types].xml", b"<Types/>\n")
            archive.writestr("AppxBlockMap.xml", b"<BlockMap/>\n")
        from msix_sdk_output import OutputPolicy
        policy = OutputPolicy(str(candidate), str(package), [p.relative_to(candidate).as_posix() for p in candidate.rglob("*") if p.is_file()])
        assert kwargs["stdout_limit"] == policy.byte_limit
        selected = {}
        for line, key in policy.lines.items():
            if key != "success":
                selected.setdefault(key, line)
        stdout = ("\r\n".join(selected.values()) + "\r\nPackage creation succeeded.\r\n").encode()
        return OwnedProcessResult(returncode=0, stdout=stdout, stderr=b"")

    return run


def test_pack_uses_validation_no_overwrite_and_verifies_exact_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    candidate = Path(values["candidate_root"])
    receipt = PACK.pack_candidate(**values, runner=_successful_runner(candidate))
    package = Path(values["output_root"]) / PACK.PACKAGE_NAME
    assert receipt["passed"] is True
    assert receipt["validation_enabled"] is True
    assert receipt["candidate_files_verified"] == 3
    assert receipt["artifact_size_bytes"] == package.stat().st_size
    assert receipt["artifact_sha256"] == hashlib.sha256(package.read_bytes()).hexdigest()
    assert receipt["signed"] is False and receipt["installed"] is False
    assert receipt["stage"] == "complete" and receipt["sdk_exit_code"] == 0
    assert receipt["owned_failure_code"] is None


def test_package_member_map_accepts_sdk_backslash_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    candidate = Path(values["candidate_root"])
    receipt = PACK.pack_candidate(**values, runner=_successful_runner(candidate, backslashes=True))
    assert receipt["passed"] is True


def test_candidate_is_verified_again_after_sdk_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch)
    candidate = Path(values["candidate_root"])

    def runner(command: list[str], **kwargs: object) -> OwnedProcessResult:
        result = _successful_runner(candidate)(command, **kwargs)
        (candidate / "PromptEnhancer.exe").write_bytes(b"changed-after-pack")
        return result

    with pytest.raises(PACK.PackError, match="candidate_manifest_mismatch"):
        PACK.pack_candidate(**values, runner=runner)


@pytest.mark.parametrize(
    ("omit", "mutate", "code"),
    [
        ("PromptEnhancer.exe", None, "package_coverage_mismatch"),
        (None, "PromptEnhancer.exe", "package_member_mismatch"),
    ],
)
def test_package_member_coverage_and_hashes_are_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, omit: str | None, mutate: str | None, code: str
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    candidate = Path(values["candidate_root"])
    with pytest.raises(PACK.PackError, match=code):
        PACK.pack_candidate(**values, runner=_successful_runner(candidate, omit=omit, mutate=mutate))


def test_candidate_change_is_refused_before_sdk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch)
    (Path(values["candidate_root"]) / "extra.txt").write_bytes(b"unlisted")
    with pytest.raises(PACK.PackError, match="candidate_manifest_mismatch"):
        PACK.pack_candidate(
            **values,
            runner=lambda *args, **kwargs: pytest.fail("SDK must not run"),
        )


def test_noncanonical_or_wrong_manifest_identity_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    with pytest.raises(PACK.PackError, match="manifest_identity_mismatch"):
        PACK.pack_candidate(**{**values, "build_manifest_sha256": "0" * 64}, runner=lambda *args, **kwargs: None)
    manifest_path = Path(values["build_manifest_path"])
    parsed = json.loads(manifest_path.read_text(encoding="ascii"))
    manifest_path.write_text(json.dumps(parsed, indent=2), encoding="ascii")
    values["build_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    with pytest.raises(PACK.PackError, match="manifest_not_canonical"):
        PACK.pack_candidate(**values, runner=lambda *args, **kwargs: None)


def test_sdk_identity_and_fresh_external_output_are_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    with pytest.raises(PACK.PackError, match="sdk_identity_mismatch"):
        PACK.pack_candidate(**{**values, "sdk_sha256": "0" * 64}, runner=lambda *args, **kwargs: None)
    Path(values["output_root"]).mkdir()
    with pytest.raises(PACK.PackError, match="unsafe_output"):
        PACK.pack_candidate(**values, runner=lambda *args, **kwargs: None)


def test_candidate_and_output_must_not_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch)
    values["output_root"] = str((Path(values["candidate_root"]) / "output").resolve())
    with pytest.raises(PACK.PackError, match="candidate_output_overlap"):
        PACK.pack_candidate(**values, runner=lambda *args, **kwargs: pytest.fail("SDK must not run"))


def test_candidate_reparse_is_refused_before_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    candidate = Path(values["candidate_root"])
    original = PACK._ordinary_ancestors
    resolve_called = False

    def ancestors(path: Path) -> None:
        if path == candidate:
            raise PACK.PackError("unsafe_path")
        original(path)

    original_resolve = Path.resolve

    def resolve(path: Path, *args: object, **kwargs: object) -> Path:
        nonlocal resolve_called
        if path == candidate:
            resolve_called = True
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(PACK, "_ordinary_ancestors", ancestors)
    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(PACK.PackError, match="unsafe_path"):
        PACK.pack_candidate(**values, runner=lambda *args, **kwargs: pytest.fail("SDK must not run"))
    assert resolve_called is False


def test_bounded_central_directory_check_precedes_zip_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    candidate = Path(values["candidate_root"])
    monkeypatch.setattr(PACK, "_bounded_zip_central_directory", lambda descriptor, size: False)
    with pytest.raises(PACK.PackError, match="package_envelope_invalid"):
        PACK.pack_candidate(**values, runner=_successful_runner(candidate))


def test_sdk_stderr_and_failure_are_closed_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch)
    for result, code in (
        (OwnedProcessResult(returncode=7, stderr=b"private diagnostic"), "sdk_pack_failed"),
        (OwnedProcessResult(returncode=0, stderr=b"private diagnostic"), "sdk_stderr_not_empty"),
    ):
        output = Path(values["output_root"])
        if output.exists():
            values["output_root"] = str((tmp_path / f"output-{code}").resolve())
        with pytest.raises(PACK.PackError, match=code) as raised:
            PACK.pack_candidate(**values, runner=lambda *args, result=result, **kwargs: result)
        assert raised.value.stage == "sdk"
        assert raised.value.owned_cleanup_confirmed is True
        assert raised.value.sdk_exit_code == result.returncode
        assert output.exists()


@pytest.mark.parametrize(
    ("owned_code", "cleanup"),
    [
        ("owned_process_unavailable", None),
        ("owned_process_timeout", True),
        ("owned_process_cleanup_unconfirmed", False),
        ("forged_private_failure", None),
    ],
)
def test_owned_process_failure_code_is_preserved_without_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    owned_code: str,
    cleanup: bool | None,
) -> None:
    values = _fixture(tmp_path, monkeypatch)

    def runner(*args: object, **kwargs: object) -> OwnedProcessResult:
        raise OwnedProcessRunError(owned_code)

    with pytest.raises(PACK.PackError, match="sdk_run_failed") as raised:
        PACK.pack_candidate(**values, runner=runner)
    assert raised.value.owned_failure_code == (
        owned_code if owned_code in PACK.OWNED_FAILURE_CODES else None
    )
    assert raised.value.owned_cleanup_confirmed is cleanup
    assert raised.value.sdk_exit_code is None


def test_cli_argument_error_emits_no_untrusted_value(capsys: pytest.CaptureFixture[str]) -> None:
    private = "PRIVATE_ARGUMENT_CANARY"
    assert PACK.main(["--unknown", private]) == 1
    captured = capsys.readouterr()
    assert private not in captured.out and captured.err == ""
    receipt = json.loads(captured.out.removeprefix("UNSIGNED_MSIX_PACK="))
    assert receipt["passed"] is False
    assert receipt["error_code"] == "invalid_arguments"
    assert receipt["owned_cleanup_confirmed"] is None
    assert receipt["owned_failure_code"] is None
    assert receipt["stage"] == "preflight"
    assert receipt["signed"] is False and receipt["installed"] is False


def test_cli_receipt_forwards_only_closed_owned_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(**kwargs: object) -> dict[str, object]:
        raise PACK.PackError(
            "sdk_run_failed", stage="sdk", owned_cleanup_confirmed=True,
            owned_failure_code="owned_process_timeout",
        )

    monkeypatch.setattr(PACK, "pack_candidate", fail)
    assert PACK.main([
        "--candidate-root", "synthetic", "--build-manifest", "synthetic",
        "--build-manifest-sha256", "0" * 64, "--output-root", "synthetic",
    ]) == 1
    receipt = json.loads(capsys.readouterr().out.removeprefix("UNSIGNED_MSIX_PACK="))
    assert receipt["error_code"] == "sdk_run_failed"
    assert receipt["owned_failure_code"] == "owned_process_timeout"
    assert receipt["owned_cleanup_confirmed"] is True
    assert receipt["sdk_exit_code"] is None
