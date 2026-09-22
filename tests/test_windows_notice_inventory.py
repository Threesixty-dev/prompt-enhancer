from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from prompt_enhancer.application.build_evidence.manifest import build_manifest, canonical_json

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_windows_notice_inventory.py"
SPEC = importlib.util.spec_from_file_location("prepare_windows_notice_inventory", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
NOTICE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = NOTICE
SPEC.loader.exec_module(NOTICE)


def _metadata(name: str, version: str, *, license_value: str | None = "MIT",
              license_file: str | None = "LICENSE") -> bytes:
    rows = ["Metadata-Version: 2.4", f"Name: {name}", f"Version: {version}"]
    if license_value is not None:
        rows.append(f"License-Expression: {license_value}")
    if license_file is not None:
        rows.append(f"License-File: {license_file}")
    return ("\n".join(rows) + "\n").encode()


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "LICENSE.txt").write_bytes(b"synthetic runtime license\n")
    for stem, metadata, license_bytes in (
        ("alpha-1.0.dist-info", _metadata("alpha", "1.0"), b"alpha terms\n"),
        ("proxy_tools-0.1.0.dist-info", _metadata("proxy_tools", "0.1.0", license_file=None), None),
        ("prompt_enhancer-0.1.0.dist-info", _metadata("prompt-enhancer", "0.1.0", license_value=None, license_file=None), None),
    ):
        directory = stage / stem
        directory.mkdir()
        (directory / "METADATA").write_bytes(metadata)
        if license_bytes is not None:
            (directory / "licenses").mkdir()
            (directory / "licenses" / "LICENSE").write_bytes(license_bytes)
    manifest = build_manifest(stage, git_revision="a" * 40, tool_versions={}, lockfile_hashes={})
    raw = canonical_json(manifest)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(raw)
    monkeypatch.setattr(NOTICE, "ROOT", tmp_path / "repository")
    monkeypatch.setattr(NOTICE, "HOME", tmp_path / "home")
    return {"stage_root": stage.resolve(), "build_manifest_path": manifest_path.resolve(),
            "build_manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "output_path": (tmp_path / "output" / "notice-inventory.json").resolve()}


def _prepare(values: dict[str, object]) -> None:
    Path(values["output_path"]).parent.mkdir()


def test_inventory_is_deterministic_and_preserves_unknowns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    _prepare(values)
    receipt = NOTICE.inventory(**values)
    report = json.loads(Path(values["output_path"]).read_text())
    assert receipt["distribution_count"] == 3
    assert receipt["proxy_tools_license_discrepancy_review_required"] is True
    assert receipt["application_license_missing"] is True
    assert report["release_accepted"] is False and report["spdx_sbom_claimed"] is False
    assert report["unresolved_gaps"] == [
        "application_license_missing", "frontend_notice_inventory_missing",
        "proxy_tools_license_discrepancy_review_required", "rendered_third_party_notices_missing",
    ]
    app = next(item for item in report["distributions"] if item["name"] == "prompt-enhancer")
    assert app["license"] is None and app["license_expression"] is None
    encoded = Path(values["output_path"]).read_bytes()
    values["output_path"] = (tmp_path / "output" / "second.json").resolve()
    NOTICE.inventory(**values)
    assert Path(values["output_path"]).read_bytes() == encoded


def test_missing_declared_license_file_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch)
    missing = Path(values["stage_root"]) / "alpha-1.0.dist-info" / "licenses" / "LICENSE"
    missing.unlink()
    manifest = build_manifest(Path(values["stage_root"]), git_revision="a" * 40, tool_versions={}, lockfile_hashes={})
    raw = canonical_json(manifest); Path(values["build_manifest_path"]).write_bytes(raw)
    values["build_manifest_sha256"] = hashlib.sha256(raw).hexdigest(); _prepare(values)
    with pytest.raises(NOTICE.InventoryError, match="license_evidence_missing"):
        NOTICE.inventory(**values)


@pytest.mark.parametrize("value", ("../LICENSE", "/LICENSE", "folder\\LICENSE", "con/file"))
def test_unsafe_license_file_path_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    metadata = Path(values["stage_root"]) / "alpha-1.0.dist-info" / "METADATA"
    metadata.write_bytes(_metadata("alpha", "1.0", license_file=value))
    manifest = build_manifest(Path(values["stage_root"]), git_revision="a" * 40, tool_versions={}, lockfile_hashes={})
    raw = canonical_json(manifest); Path(values["build_manifest_path"]).write_bytes(raw)
    values["build_manifest_sha256"] = hashlib.sha256(raw).hexdigest(); _prepare(values)
    with pytest.raises(NOTICE.InventoryError, match="license_file_path_unsafe"):
        NOTICE.inventory(**values)


def test_declared_licenses_prefix_is_exactly_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch)
    directory = Path(values["stage_root"]) / "alpha-1.0.dist-info"
    (directory / "METADATA").write_bytes(_metadata("alpha", "1.0", license_file="licenses/LICENSE"))
    nested = directory / "licenses" / "licenses"
    nested.mkdir(); (nested / "LICENSE").write_bytes(b"nested terms\n")
    manifest = build_manifest(Path(values["stage_root"]), git_revision="a" * 40, tool_versions={}, lockfile_hashes={})
    raw = canonical_json(manifest); Path(values["build_manifest_path"]).write_bytes(raw)
    values["build_manifest_sha256"] = hashlib.sha256(raw).hexdigest(); _prepare(values)
    NOTICE.inventory(**values)
    report = json.loads(Path(values["output_path"]).read_text())
    alpha = next(item for item in report["distributions"] if item["name"] == "alpha")
    nested_evidence = next(item for item in alpha["license_files"] if item["relative_path"] == "licenses/LICENSE")
    assert nested_evidence["declared"] is True


def test_stage_hash_mismatch_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch); _prepare(values)
    (Path(values["stage_root"]) / "LICENSE.txt").write_bytes(b"changed\n")
    with pytest.raises(NOTICE.InventoryError, match="stage_manifest_mismatch"):
        NOTICE.inventory(**values)


def test_manifest_hash_mismatch_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch); _prepare(values)
    values["build_manifest_sha256"] = "0" * 64
    with pytest.raises(NOTICE.InventoryError, match="manifest_identity_mismatch"):
        NOTICE.inventory(**values)


@pytest.mark.parametrize("duplicate_name", ("ALPHA_PKG", "alpha.pkg", "alpha-pkg"))
def test_duplicate_distribution_identity_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, duplicate_name: str
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    duplicate = Path(values["stage_root"]) / "other-1.0.dist-info"
    original = Path(values["stage_root"]) / "alpha-1.0.dist-info" / "METADATA"
    original.write_bytes(_metadata("alpha_pkg", "1.0", license_file="LICENSE"))
    duplicate.mkdir(); (duplicate / "METADATA").write_bytes(_metadata(duplicate_name, "2.0", license_file=None))
    manifest = build_manifest(Path(values["stage_root"]), git_revision="a" * 40, tool_versions={}, lockfile_hashes={})
    raw = canonical_json(manifest); Path(values["build_manifest_path"]).write_bytes(raw)
    values["build_manifest_sha256"] = hashlib.sha256(raw).hexdigest(); _prepare(values)
    with pytest.raises(NOTICE.InventoryError, match="distribution_identity_duplicate"):
        NOTICE.inventory(**values)


@pytest.mark.parametrize(("name", "version"), (("bad name", "1.0"), ("alpha", "not a version"), ("-alpha", "1.0")))
def test_invalid_distribution_identity_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, version: str
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    metadata = Path(values["stage_root"]) / "alpha-1.0.dist-info" / "METADATA"
    metadata.write_bytes(_metadata(name, version))
    manifest = build_manifest(Path(values["stage_root"]), git_revision="a" * 40, tool_versions={}, lockfile_hashes={})
    raw = canonical_json(manifest); Path(values["build_manifest_path"]).write_bytes(raw)
    values["build_manifest_sha256"] = hashlib.sha256(raw).hexdigest(); _prepare(values)
    with pytest.raises(NOTICE.InventoryError, match="metadata_invalid"):
        NOTICE.inventory(**values)


@pytest.mark.parametrize("kind", ("output_inside_stage", "manifest_inside_stage", "output_equals_manifest"))
def test_paths_must_not_overlap_before_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    if kind == "output_inside_stage":
        values["output_path"] = Path(values["stage_root"]) / "inventory.json"
    elif kind == "manifest_inside_stage":
        target = Path(values["stage_root"]) / "manifest.json"
        target.write_bytes(Path(values["build_manifest_path"]).read_bytes())
        values["build_manifest_path"] = target
    else:
        values["output_path"] = values["build_manifest_path"]
    monkeypatch.setattr(NOTICE, "_manifest", lambda *_args, **_kwargs: pytest.fail("read before overlap check"))
    with pytest.raises(NOTICE.InventoryError, match="path_overlap|unsafe_output"):
        NOTICE.inventory(**values)


def test_output_is_exclusive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch); _prepare(values)
    NOTICE.inventory(**values)
    with pytest.raises(NOTICE.InventoryError, match="unsafe_output"):
        NOTICE.inventory(**values)


def test_cli_argument_failure_is_closed(capsys: pytest.CaptureFixture[str]) -> None:
    assert NOTICE.main(["--unknown", "synthetic-private-value"]) == 2
    captured = capsys.readouterr()
    assert "synthetic-private-value" not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "contract": NOTICE.CONTRACT, "passed": False, "error_code": "invalid_arguments",
    }
