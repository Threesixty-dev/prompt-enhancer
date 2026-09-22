from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

import prompt_enhancer.infrastructure.build_staging as staging_module
from prompt_enhancer.application.build_evidence.manifest import NamedDigest, PublicToolVersion
from prompt_enhancer.infrastructure.build_staging import (
    WindowsReleaseFile,
    WindowsReleaseStagePlan,
    WindowsReleaseStagingError,
    stage_windows_release,
)


def _cli_module():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[1] / "scripts" / "stage_windows_release.py"
    spec = importlib.util.spec_from_file_location("synthetic_stage_windows_release", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_plan(path: Path, plan: WindowsReleaseStagePlan) -> None:
    path.write_text(json.dumps(plan.model_dump(mode="json")), encoding="utf-8")


def _plan(source_name: str = "runtime/python.exe", destination_name: str = "runtime/python.exe", *, digest: str | None = None) -> WindowsReleaseStagePlan:
    payload = b"synthetic runtime bytes\n"
    return WindowsReleaseStagePlan(
        git_revision="a" * 40,
        tool_versions=(),
        lockfile_hashes=(),
        files=(WindowsReleaseFile(
            source_relative_path=source_name,
            destination_relative_path=destination_name,
            size_bytes=len(payload),
            sha256=digest or hashlib.sha256(payload).hexdigest(),
        ),),
    )


def _source(root: Path, *, extra: bool = False) -> None:
    (root / "runtime").mkdir(parents=True)
    (root / "runtime" / "python.exe").write_bytes(b"synthetic runtime bytes\n")
    if extra:
        (root / "private.txt").write_text("must not ship", encoding="utf-8")


@pytest.mark.parametrize("value", ["../secret.txt", "runtime/../secret.txt", "runtime\\python.exe", "runtime/python.exe:secret", "runtime/CON.txt", "runtime/name.", "runtime/name "])
def test_plan_rejects_traversal_ads_reserved_and_ambiguous_paths(value: str) -> None:
    with pytest.raises(ValidationError):
        _plan(source_name=value)


def test_plan_rejects_casefold_collisions_and_file_directory_collisions() -> None:
    with pytest.raises(ValidationError):
        WindowsReleaseStagePlan(
            git_revision="a" * 40, tool_versions=(), lockfile_hashes=(), files=(
                WindowsReleaseFile(source_relative_path="a.bin", destination_relative_path="Runtime/A.bin", size_bytes=1, sha256="0" * 64),
                WindowsReleaseFile(source_relative_path="b.bin", destination_relative_path="runtime/a.BIN", size_bytes=1, sha256="0" * 64),
            ),
        )


def test_plan_rejects_duplicate_public_tool_and_lock_names() -> None:
    file_item = WindowsReleaseFile(source_relative_path="a.bin", destination_relative_path="a.bin", size_bytes=1, sha256="0" * 64)
    with pytest.raises(ValidationError):
        WindowsReleaseStagePlan(
            git_revision="a" * 40,
            tool_versions=(PublicToolVersion(name="python", version="3.11"), PublicToolVersion(name="python", version="3.12")),
            lockfile_hashes=(), files=(file_item,),
        )
    with pytest.raises(ValidationError):
        WindowsReleaseStagePlan(
            git_revision="a" * 40,
            tool_versions=(),
            lockfile_hashes=(NamedDigest(name="lock", sha256="0" * 64), NamedDigest(name="lock", sha256="1" * 64)),
            files=(file_item,),
        )


def test_plan_rejects_truthy_schema_and_distributable_values() -> None:
    payload = {"git_revision": "a" * 40, "tool_versions": (), "lockfile_hashes": (), "files": (_plan().files[0],)}
    with pytest.raises(ValidationError):
        WindowsReleaseStagePlan.model_validate({**payload, "schema_version": True})
    with pytest.raises(ValidationError):
        WindowsReleaseStagePlan.model_validate({**payload, "distributable": 0})
    with pytest.raises(ValidationError):
        WindowsReleaseStagePlan(
            git_revision="a" * 40, tool_versions=(), lockfile_hashes=(), files=(
                WindowsReleaseFile(source_relative_path="a.bin", destination_relative_path="runtime", size_bytes=1, sha256="0" * 64),
                WindowsReleaseFile(source_relative_path="b.bin", destination_relative_path="runtime/b.bin", size_bytes=1, sha256="0" * 64),
            ),
        )


def test_source_and_destination_overlap_is_rejected_without_mutating_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _source(source)
    with pytest.raises(WindowsReleaseStagingError):
        stage_windows_release(plan=_plan(), source_root=source, destination=source / "out")
    assert (source / "runtime" / "python.exe").read_bytes() == b"synthetic runtime bytes\n"
    assert not (source / "out").exists()


def test_symlink_source_ancestor_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    _source(real)
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlink creation unavailable: {type(error).__name__}")
    with pytest.raises(WindowsReleaseStagingError):
        stage_windows_release(plan=_plan(), source_root=linked, destination=tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_nested_symlink_source_ancestor_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    (real / "runtime").mkdir(parents=True)
    (real / "runtime" / "python.exe").write_bytes(b"synthetic runtime bytes\n")
    source = tmp_path / "source"
    source.mkdir()
    try:
        (source / "runtime").symlink_to(real / "runtime", target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlink creation unavailable: {type(error).__name__}")
    with pytest.raises(WindowsReleaseStagingError):
        stage_windows_release(plan=_plan(), source_root=source, destination=tmp_path / "output")


def test_existing_output_is_preserved_and_not_replaced(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _source(source)
    output = tmp_path / "output"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("existing", encoding="utf-8")
    with pytest.raises(WindowsReleaseStagingError):
        stage_windows_release(plan=_plan(), source_root=source, destination=output)
    assert marker.read_text(encoding="utf-8") == "existing"


def test_wrong_hash_leaves_no_complete_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _source(source)
    with pytest.raises(WindowsReleaseStagingError):
        stage_windows_release(plan=_plan(digest="f" * 64), source_root=source, destination=tmp_path / "output")
    assert not (tmp_path / "output").exists()
    failed_stages = [item for item in tmp_path.iterdir() if item.name.startswith(".release-stage-")]
    assert len(failed_stages) == 1
    assert not (failed_stages[0] / "runtime" / "python.exe").exists()


@pytest.mark.skipif(os.name != "nt", reason="successful Windows release staging is Windows-only")
def test_unlisted_private_file_is_not_copied(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _source(source, extra=True)
    output = tmp_path / "output"
    result = stage_windows_release(plan=_plan(), source_root=source, destination=output)
    assert result.distributable is False
    assert (output / "runtime" / "python.exe").read_bytes() == b"synthetic runtime bytes\n"
    assert not (output / "private.txt").exists()


@pytest.mark.skipif(os.name != "nt", reason="successful Windows release staging is Windows-only")
def test_cli_success_emits_only_canonical_manifest_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "source"
    _source(source)
    plan_path = tmp_path / "plan.json"
    _write_plan(plan_path, _plan())
    output = tmp_path / "output"
    assert _cli_module().main([str(plan_path), "--source-root", str(source), "--destination", str(output)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    document = json.loads(captured.out)
    assert document["distributable"] is False
    assert document["schema_version"] == 1
    assert str(source) not in captured.out and str(output) not in captured.out


def test_cli_failure_is_content_free_and_hides_supplied_canary_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plan_path = tmp_path / "bad.json"
    plan_path.write_text("{not-json", encoding="utf-8")
    canary = tmp_path / "EXAMPLE_PRIVATE_CANARY_PATH"
    assert _cli_module().main([str(plan_path), "--source-root", str(canary), "--destination", str(tmp_path / "out")]) == 2
    captured = capsys.readouterr()
    assert "windows_release_staging_failed" in captured.err
    assert str(canary) not in captured.out + captured.err


def test_cli_rejects_duplicate_json_members(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plan_path = tmp_path / "duplicate.json"
    plan_path.write_text('{"git_revision":"' + "a" * 40 + '","git_revision":"' + "b" * 40 + '"}', encoding="utf-8")
    assert _cli_module().main([str(plan_path), "--source-root", str(tmp_path), "--destination", str(tmp_path / "out")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "windows_release_staging_failed"


def test_cli_rejects_oversized_plan_before_staging(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file_item = {"source_relative_path": "a.bin", "destination_relative_path": "a.bin", "size_bytes": 1, "sha256": "0" * 64}
    raw = {"git_revision": "a" * 40, "tool_versions": [], "lockfile_hashes": [], "files": [
        {**file_item, "source_relative_path": f"a-{index}.bin", "destination_relative_path": f"a-{index}.bin"}
        for index in range(50_001)
    ]}
    plan_path = tmp_path / "oversized.json"
    plan_path.write_text(json.dumps(raw), encoding="utf-8")
    assert _cli_module().main([str(plan_path), "--source-root", str(tmp_path), "--destination", str(tmp_path / "out")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "windows_release_staging_failed"
    assert not (tmp_path / "out").exists()


def test_late_created_output_is_not_clobbered(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "source"
    _source(source)
    output = tmp_path / "output"
    original_rename = staging_module.os.rename

    def race_rename(temporary: str | bytes | Path, target: str | bytes | Path) -> None:
        Path(target).mkdir()
        (Path(target) / "keep.txt").write_text("late", encoding="utf-8")
        original_rename(temporary, target)

    monkeypatch.setattr(staging_module.os, "rename", race_rename)
    with pytest.raises(WindowsReleaseStagingError):
        stage_windows_release(plan=_plan(), source_root=source, destination=output)
    assert (output / "keep.txt").read_text(encoding="utf-8") == "late"
