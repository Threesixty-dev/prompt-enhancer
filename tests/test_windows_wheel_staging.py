import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from prompt_enhancer.infrastructure.windows_python_runtime import WindowsPythonRuntimeFile
from prompt_enhancer.infrastructure.windows_wheel_inventory import WindowsWheelArtifact, WindowsWheelTarget
from prompt_enhancer.infrastructure.windows_wheel_staging import (
    StagedWindowsWheels, WindowsWheelStagingError, stage_windows_wheels,
)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def _record_rows(rows: list[tuple[str, str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _runtime(tmp_path: Path) -> tuple[Path, tuple[WindowsPythonRuntimeFile, ...]]:
    root = tmp_path / "runtime"; root.mkdir(parents=True, exist_ok=True)
    pe = bytearray(72); pe[:2] = b"MZ"; pe[0x3c:0x40] = (64).to_bytes(4, "little"); pe[64:68] = b"PE\0\0"; pe[68:70] = (0x8664).to_bytes(2, "little")
    values = {"python.exe": bytes(pe), "pythonw.exe": bytes(pe), "python313.dll": bytes(pe), "python3.dll": bytes(pe),
        "vcruntime140.dll": bytes(pe), "vcruntime140_1.dll": bytes(pe), "python313._pth": b"python313.zip\n.\n",
        "python313.zip": b"stdlib", "LICENSE.txt": b"synthetic license"}
    for name, value in values.items(): (root / name).write_bytes(value)
    return root, tuple(WindowsPythonRuntimeFile(name, len(value), _hash(value)) for name, value in values.items())


def _wheel(tmp_path: Path, *, metadata_name: str = "demo", record: bool = True,
           extra: dict[str, bytes] | None = None, tag: str = "py3-none-any",
           metadata_body: str = "") -> tuple[WindowsWheelArtifact, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    name = f"demo-1.0-{tag}.whl"; path = tmp_path / name
    files = {"demo/__init__.py": b"value = 1\n", "demo-1.0.dist-info/WHEEL": f"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: {tag}\n".encode(),
        "demo-1.0.dist-info/METADATA": (f"Metadata-Version: 2.1\nName: {metadata_name}\nVersion: 1.0\n{metadata_body}").encode()}
    files.update(extra or {})
    if record:
        files["demo-1.0.dist-info/RECORD"] = _record_rows([
            *( (item, _record(value), str(len(value))) for item, value in files.items()),
            ("demo-1.0.dist-info/RECORD", "", ""),
        ])
    with zipfile.ZipFile(path, "w") as archive:
        for item, value in files.items(): archive.writestr(item, value)
    data = path.read_bytes()
    return WindowsWheelArtifact("demo", "1.0", name, _hash(data), len(data)), path


def _stage(tmp_path: Path, artifact: WindowsWheelArtifact, wheel: Path, **changes: object):
    root, files = _runtime(tmp_path)
    values = {"runtime_root": root, "runtime_files": files, "artifacts": (artifact,), "wheel_files": {artifact.filename: wheel},
              "target": WindowsWheelTarget("3.13.0", "amd64"), "destination": tmp_path / "result"}
    values.update(changes)
    return stage_windows_wheels(**values)


def test_staging_purelib_and_native_layouts_are_expanded_offline(tmp_path: Path):
    artifact, wheel = _wheel(tmp_path, extra={"demo-1.0.data/purelib/relocated.py": b"pure", "demo-1.0.data/scripts/demo-tool.py": b"#! inert\n", "demo.pyd": b"native"})
    result = _stage(tmp_path, artifact, wheel)
    assert (tmp_path / "result" / "relocated.py").read_bytes() == b"pure"
    assert (tmp_path / "result" / "demo.pyd").read_bytes() == b"native"
    assert (tmp_path / "result" / "Scripts" / "demo-tool.py").read_bytes() == b"#! inert\n"
    record_path = tmp_path / "result" / "demo-1.0.dist-info" / "RECORD"
    installed_record = record_path.read_text()
    assert "relocated.py," in installed_record and "Scripts/demo-tool.py," in installed_record and ".data/purelib/relocated.py" not in installed_record
    for name, digest, size in csv.reader(installed_record.splitlines()):
        if name == "demo-1.0.dist-info/RECORD":
            assert (digest, size) == ("", "")
        else:
            payload = (tmp_path / "result" / Path(name)).read_bytes()
            assert (digest, size) == (_record(payload), str(len(payload)))
    assert result.complete is False and result.installable_product_unproven is True


def test_native_targeted_wheel_is_accepted_for_the_reviewed_target(tmp_path: Path):
    artifact, wheel = _wheel(tmp_path, tag="cp313-cp313-win_amd64", extra={"demo.pyd": b"synthetic native"})
    _stage(tmp_path, artifact, wheel)
    assert (tmp_path / "result" / "demo.pyd").read_bytes() == b"synthetic native"


def test_metadata_description_body_and_csv_escaped_installed_record_are_supported(tmp_path: Path):
    artifact, wheel = _wheel(tmp_path, metadata_body="\nA realistic description: with a colon.\n\nSecond paragraph.\n",
        extra={"demo/with,comma.py": b"valid Windows filename"})
    _stage(tmp_path, artifact, wheel)
    rows = list(csv.reader((tmp_path / "result" / "demo-1.0.dist-info" / "RECORD").read_text().splitlines()))
    comma_row = next(row for row in rows if row[0] == "demo/with,comma.py")
    assert comma_row == ["demo/with,comma.py", _record(b"valid Windows filename"), str(len(b"valid Windows filename"))]


@pytest.mark.parametrize("kwargs", [
    {"tag": "cp312-cp312-win_amd64"},
    {"metadata_name": "other"},
    {"record": False},
])
def test_wheel_target_metadata_and_record_are_required(tmp_path: Path, kwargs: dict[str, object]):
    artifact, wheel = _wheel(tmp_path, **kwargs)
    with pytest.raises(WindowsWheelStagingError): _stage(tmp_path, artifact, wheel)
    assert not list(tmp_path.glob(".wheel-stage-incomplete-*"))


def test_distribution_bound_dist_info_and_data_prefixes_are_required(tmp_path: Path):
    artifact, wheel = _wheel(tmp_path, extra={"other-1.0.dist-info/unrelated": b"x"})
    with pytest.raises(WindowsWheelStagingError): _stage(tmp_path, artifact, wheel)
    artifact, wheel = _wheel(tmp_path / "other", extra={"other-1.0.data/purelib/value.py": b"x"})
    with pytest.raises(WindowsWheelStagingError): _stage(tmp_path / "other", artifact, wheel)


def test_app_local_script_collision_is_rejected(tmp_path: Path):
    artifact, wheel = _wheel(tmp_path, extra={"Scripts/tool.py": b"root", "demo-1.0.data/scripts/tool.py": b"script"})
    with pytest.raises(WindowsWheelStagingError): _stage(tmp_path, artifact, wheel)


def test_inventory_hash_missing_duplicate_and_runtime_tamper_are_rejected(tmp_path: Path):
    artifact, wheel = _wheel(tmp_path)
    wrong = WindowsWheelArtifact("demo", "1.0", artifact.filename, "0" * 64, artifact.size_bytes)
    with pytest.raises(WindowsWheelStagingError): _stage(tmp_path, wrong, wheel)
    with pytest.raises(WindowsWheelStagingError): _stage(tmp_path, artifact, wheel, wheel_files={})
    with pytest.raises(WindowsWheelStagingError): _stage(tmp_path, artifact, wheel, artifacts=(artifact, artifact))
    root, files = _runtime(tmp_path / "tampered")
    (root / "python.exe").write_bytes(b"changed")
    with pytest.raises(WindowsWheelStagingError):
        stage_windows_wheels(runtime_root=root, runtime_files=files, artifacts=(artifact,), wheel_files={artifact.filename: wheel},
            target=WindowsWheelTarget("3.13.0", "amd64"), destination=tmp_path / "tampered" / "result")


def test_runtime_manifest_requires_preparer_component_set_and_architecture(tmp_path: Path):
    artifact, wheel = _wheel(tmp_path)
    root, files = _runtime(tmp_path)
    with pytest.raises(WindowsWheelStagingError): _stage(tmp_path, artifact, wheel, runtime_root=root, runtime_files=files[:-1])
    broken = root / "python3.dll"; contents = bytearray(broken.read_bytes()); contents[68:70] = (0xAA64).to_bytes(2, "little"); broken.write_bytes(contents)
    with pytest.raises(WindowsWheelStagingError):
        stage_windows_wheels(runtime_root=root, runtime_files=files, artifacts=(artifact,), wheel_files={artifact.filename: wheel},
            target=WindowsWheelTarget("3.13.0", "amd64"), destination=tmp_path / "architecture-result")


@pytest.mark.parametrize("member", ["../escape.py", "CON.py", "folder/file. ", "folder\\file.py"])
def test_windows_path_boundaries_and_unsupported_data_are_rejected(tmp_path: Path, member: str):
    artifact, wheel = _wheel(tmp_path, extra={member: b"x"})
    with pytest.raises(WindowsWheelStagingError): _stage(tmp_path, artifact, wheel)
    artifact, wheel = _wheel(tmp_path / "data", extra={"demo-1.0.data/data/tool.exe": b"x"})
    with pytest.raises(WindowsWheelStagingError): _stage(tmp_path / "data", artifact, wheel)


def test_no_overwrite_and_cli_end_to_end(tmp_path: Path):
    artifact, wheel = _wheel(tmp_path)
    root, files = _runtime(tmp_path)
    destination = tmp_path / "out"; destination.mkdir()
    with pytest.raises(WindowsWheelStagingError): _stage(tmp_path, artifact, wheel, runtime_root=root, runtime_files=files, destination=destination)
    destination.rmdir()
    manifest = tmp_path / "runtime.json"; inventory = tmp_path / "inventory.json"
    manifest.write_text(json.dumps({"declared_python_version": "3.13.0", "architecture": "amd64", "files": [item.__dict__ if hasattr(item, "__dict__") else {"relative_path": item.relative_path, "size_bytes": item.size_bytes, "sha256": item.sha256} for item in files], "native_dll_dependencies_unresolved": True, "runtime_execution_unproven": True, "complete": False}))
    inventory.write_text(json.dumps({"target": {"python_full_version": "3.13.0", "architecture": "amd64"}, "artifacts": [{"package": artifact.package, "version": artifact.version, "filename": artifact.filename, "sha256": artifact.sha256, "size_bytes": artifact.size_bytes}], "complete": True}))
    command = [sys.executable, "scripts/stage_windows_wheels.py", "--runtime-root", str(root), "--runtime-manifest", str(manifest), "--wheel-inventory", str(inventory), "--wheel-directory", str(tmp_path), "--destination", str(destination)]
    run = subprocess.run(command, cwd=Path(__file__).parents[1], capture_output=True, text=True, check=False)
    assert run.returncode == 0 and json.loads(run.stdout)["complete"] is False


def test_staging_never_claims_complete_product():
    value = StagedWindowsWheels(())
    assert value.complete is False and value.installable_product_unproven is True
