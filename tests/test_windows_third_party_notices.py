from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

from prompt_enhancer.application.build_evidence.manifest import build_manifest, canonical_json

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


INVENTORY = _load("prepare_windows_notice_inventory", "scripts/prepare_windows_notice_inventory.py")
RENDER = _load("render_windows_third_party_notices", "scripts/render_windows_third_party_notices.py")


def _metadata(name: str, version: str, *, expression: str | None = "MIT",
              license_file: str | None = "LICENSE") -> bytes:
    rows = ["Metadata-Version: 2.4", f"Name: {name}", f"Version: {version}"]
    if expression is not None:
        rows.append(f"License-Expression: {expression}")
    if license_file is not None:
        rows.append(f"License-File: {license_file}")
    return ("\n".join(rows) + "\n").encode()


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *,
             alpha_license: bytes | None = b"alpha synthetic terms\n",
             include_proxy: bool = True, application_licensed: bool = False) -> dict[str, object]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "LICENSE.txt").write_bytes(b"synthetic CPython terms\n")
    values = [
        ("alpha-1.0.dist-info", _metadata(
            "alpha", "1.0", license_file="LICENSE" if alpha_license is not None else None,
        ), alpha_license),
        ("prompt_enhancer-0.1.dist-info", _metadata(
            "prompt-enhancer", "0.1", expression="MIT" if application_licensed else None,
            license_file=None,
        ), None),
    ]
    if include_proxy:
        values.append(("proxy_tools-0.1.dist-info", _metadata(
            "proxy_tools", "0.1", expression="MIT", license_file=None,
        ), None))
    for stem, metadata, license_bytes in values:
        directory = stage / stem
        directory.mkdir()
        (directory / "METADATA").write_bytes(metadata)
        if license_bytes is not None:
            (directory / "licenses").mkdir()
            (directory / "licenses" / "LICENSE").write_bytes(license_bytes)
    manifest = build_manifest(stage, git_revision="a" * 40, tool_versions={}, lockfile_hashes={})
    manifest_raw = canonical_json(manifest)
    manifest_path = tmp_path / "stage-manifest.json"
    manifest_path.write_bytes(manifest_raw)
    inventory_path = tmp_path / "evidence" / "inventory.json"
    inventory_path.parent.mkdir()
    monkeypatch.setattr(INVENTORY, "ROOT", tmp_path / "repository")
    monkeypatch.setattr(INVENTORY, "HOME", tmp_path / "home")
    INVENTORY.inventory(
        stage_root=stage.resolve(), build_manifest_path=manifest_path.resolve(),
        build_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
        output_path=inventory_path.resolve(),
    )
    inventory_raw = inventory_path.read_bytes()
    output_dir = tmp_path / "rendered"
    output_dir.mkdir()
    return {
        "stage_root": stage.resolve(),
        "build_manifest_path": manifest_path.resolve(),
        "build_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "notice_inventory_path": inventory_path.resolve(),
        "notice_inventory_sha256": hashlib.sha256(inventory_raw).hexdigest(),
        "output_path": (output_dir / "THIRD_PARTY_NOTICES.txt").resolve(),
    }


def test_render_is_deterministic_and_explicitly_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    receipt = RENDER.render(**values)
    first = Path(values["output_path"]).read_bytes()
    assert receipt["distribution_count"] == 3
    assert receipt["license_file_count"] == 1
    assert receipt["source_files_verified"] == 5
    assert receipt["complete"] is False and receipt["release_accepted"] is False
    assert receipt["artifact_sha256"] == hashlib.sha256(first).hexdigest()
    text = first.decode("utf-8")
    assert "alpha synthetic terms" in text and "synthetic CPython terms" in text
    assert "application_license_missing" in text
    assert "proxy_tools_license_discrepancy_review_required" in text
    assert "frontend_notice_inventory_missing" in text
    values["output_path"] = (Path(values["output_path"]).parent / "second.txt").resolve()
    RENDER.render(**values)
    assert Path(values["output_path"]).read_bytes() == first


def test_inventory_or_manifest_identity_mismatch_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    values["notice_inventory_sha256"] = "0" * 64
    with pytest.raises(RENDER.RenderError, match="inventory_identity_mismatch"):
        RENDER.render(**values)
    values = _fixture(tmp_path / "second", monkeypatch)
    values["build_manifest_sha256"] = "0" * 64
    with pytest.raises(INVENTORY.InventoryError, match="manifest_identity_mismatch"):
        RENDER.render(**values)


def test_changed_stage_file_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch)
    (Path(values["stage_root"]) / "LICENSE.txt").write_bytes(b"changed\n")
    with pytest.raises(INVENTORY.InventoryError, match="stage_manifest_mismatch"):
        RENDER.render(**values)


@pytest.mark.parametrize("change", ("missing", "extra"))
def test_missing_or_extra_inventory_evidence_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    path = Path(values["notice_inventory_path"])
    report = json.loads(path.read_bytes())
    if change == "missing":
        report["distributions"][0]["license_files"] = []
    else:
        report["distributions"][0]["license_files"].append({
            "relative_path": "EXTRA", "size_bytes": 1, "sha256": "0" * 64,
            "declared": False,
        })
    raw = json.dumps(report, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"
    path.write_bytes(raw)
    values["notice_inventory_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(RENDER.RenderError, match="inventory_stage_mismatch"):
        RENDER.render(**values)


def test_absent_license_text_is_reported_without_invention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(tmp_path, monkeypatch, alpha_license=None)
    receipt = RENDER.render(**values)
    text = Path(values["output_path"]).read_text(encoding="utf-8")
    assert receipt["license_file_count"] == 0
    assert text.count("license_text_evidence: absent") == 3
    assert "alpha synthetic terms" not in text


def test_proxy_metadata_conflict_stays_an_unresolved_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    receipt = RENDER.render(**values)
    assert receipt["proxy_tools_license_discrepancy_review_required"] is True
    assert b"proxy_tools_license_discrepancy_review_required" in Path(values["output_path"]).read_bytes()


def test_licensed_non_proxy_fixture_has_no_false_gap_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(tmp_path, monkeypatch, include_proxy=False, application_licensed=True)
    receipt = RENDER.render(**values)
    text = Path(values["output_path"]).read_text(encoding="utf-8")
    assert receipt["application_license_missing"] is False
    assert receipt["proxy_tools_license_discrepancy_review_required"] is False
    assert "application_license_missing" not in text
    assert "proxy_tools_license_discrepancy_review_required" not in text
    assert "frontend_notice_inventory_missing" in text


def test_license_decoding_failure_is_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch, alpha_license=b"\xff\xfe")
    with pytest.raises(RENDER.RenderError, match="license_text_decode_failed"):
        RENDER.render(**values)


@pytest.mark.parametrize("kind", ("inside_stage", "existing", "overlap_inventory"))
def test_output_must_be_fresh_external_and_nonoverlapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    if kind == "inside_stage":
        values["output_path"] = Path(values["stage_root"]) / "notices.txt"
    elif kind == "existing":
        Path(values["output_path"]).write_bytes(b"preserve")
    else:
        values["output_path"] = values["notice_inventory_path"]
    with pytest.raises(RENDER.RenderError, match="unsafe_path|path_overlap"):
        RENDER.render(**values)


def test_output_overlap_is_rejected_before_input_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    values["output_path"] = Path(values["stage_root"]) / "notices.txt"
    monkeypatch.setattr(
        INVENTORY, "build_inventory_report",
        lambda **_kwargs: pytest.fail("input read before overlap rejection"),
    )
    with pytest.raises(RENDER.RenderError, match="path_overlap"):
        RENDER.render(**values)


def test_relative_input_path_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch)
    values["stage_root"] = Path("relative-stage")
    with pytest.raises(RENDER.RenderError, match="unsafe_path"):
        RENDER.render(**values)


@pytest.mark.skipif(not hasattr(os, "link"), reason="hard links unavailable")
def test_hardlinked_license_source_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _fixture(tmp_path, monkeypatch)
    license_path = Path(values["stage_root"]) / "alpha-1.0.dist-info" / "licenses" / "LICENSE"
    other = tmp_path / "other-license"
    try:
        os.link(license_path, other)
    except OSError:
        pytest.skip("hard links unavailable")
    with pytest.raises(INVENTORY.InventoryError, match="stage_verification_failed"):
        RENDER.render(**values)


def test_cli_argument_failure_does_not_echo_values(capsys: pytest.CaptureFixture[str]) -> None:
    assert RENDER.main(["--unknown", "synthetic-private-value"]) == 2
    captured = capsys.readouterr()
    assert "synthetic-private-value" not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "contract": RENDER.CONTRACT, "passed": False, "error_code": "invalid_arguments",
    }


def test_cli_maps_unknown_lowercase_error_to_closed_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        RENDER, "render",
        lambda **_kwargs: (_ for _ in ()).throw(RENDER.RenderError("lowercase_canary")),
    )
    arguments = [
        "--stage-root", str((tmp_path / "stage").resolve()),
        "--build-manifest", str((tmp_path / "manifest").resolve()),
        "--build-manifest-sha256", "0" * 64,
        "--notice-inventory", str((tmp_path / "inventory").resolve()),
        "--notice-inventory-sha256", "0" * 64,
        "--output", str((tmp_path / "output").resolve()),
    ]
    assert RENDER.main(arguments) == 2
    assert json.loads(capsys.readouterr().out)["error_code"] == "render_failed"
