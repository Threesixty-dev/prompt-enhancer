from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_msix_manifest.py"
SPEC = importlib.util.spec_from_file_location("prepare_msix_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _args(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "identity": "Example.PromptEnhancer",
        "publisher": "CN=ExamplePublisher",
        "version": "1.2.3.4",
        "include_metrics": False,
    }
    values.update(changes)
    return values


def test_manifest_declares_fixed_full_trust_main_entry_and_provisional_floor() -> None:
    payload = MODULE.manifest_bytes(**_args())
    root = ET.fromstring(payload)
    ns = {"f": MODULE.FOUNDATION, "uap": MODULE.UAP, "uap10": MODULE.UAP10, "rescap": MODULE.RESCAP}
    identity = root.find("f:Identity", ns)
    application = root.find("f:Applications/f:Application", ns)
    visual = application.find("uap:VisualElements", ns)
    assert identity.attrib == {
        "Name": "Example.PromptEnhancer", "Publisher": "CN=ExamplePublisher",
        "Version": "1.2.3.4", "ProcessorArchitecture": "x64",
    }
    assert application.attrib["Executable"] == "PromptEnhancer.exe"
    assert "EntryPoint" not in application.attrib
    assert application.attrib[f"{{{MODULE.UAP10}}}RuntimeBehavior"] == "packagedClassicApp"
    assert application.attrib[f"{{{MODULE.UAP10}}}TrustLevel"] == "mediumIL"
    assert visual.attrib["Square44x44Logo"] == "Assets\\Square44x44Logo.png"
    assert visual.attrib["Square150x150Logo"] == "Assets\\Square150x150Logo.png"
    family = root.find("f:Dependencies/f:TargetDeviceFamily", ns)
    assert family.attrib["Name"] == "Windows.Desktop"
    assert family.attrib["MinVersion"] == "10.0.19041.0"
    assert root.find("f:Capabilities/rescap:Capability", ns).attrib == {"Name": "runFullTrust"}


def test_optional_metrics_entry_has_only_fixed_launcher_name() -> None:
    root = ET.fromstring(MODULE.manifest_bytes(**_args(include_metrics=True)))
    applications = root.findall(f"{{{MODULE.FOUNDATION}}}Applications/{{{MODULE.FOUNDATION}}}Application")
    assert [(item.attrib["Id"], item.attrib["Executable"]) for item in applications] == [
        ("PromptEnhancer", "PromptEnhancer.exe"),
        ("PromptEnhancerMetrics", "PromptEnhancerMetrics.exe"),
    ]


def test_xml_writer_escapes_parameterized_publisher() -> None:
    payload = MODULE.manifest_bytes(**_args(publisher="CN=Example & Publisher"))
    assert b"Example &amp; Publisher" in payload
    root = ET.fromstring(payload)
    identity = root.find(f"{{{MODULE.FOUNDATION}}}Identity")
    assert identity.attrib["Publisher"] == "CN=Example & Publisher"


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"identity": "bad/name"}, "invalid_identity"),
        ({"identity": "A"}, "invalid_identity"),
        ({"publisher": "O=Example"}, "invalid_publisher"),
        ({"publisher": "CN="}, "invalid_publisher"),
        ({"version": "1.2.3"}, "invalid_version"),
        ({"version": "65536.0.0.0"}, "invalid_version"),
        ({"version": 1}, "invalid_version"),
        ({"publisher": "CN=Example\ud800Publisher"}, "invalid_publisher"),
        ({"publisher": "CN=Example\ufffePublisher"}, "invalid_publisher"),
        ({"include_metrics": 1}, "invalid_entry_flags"),
    ],
)
def test_manifest_rejects_invalid_or_out_of_bounds_inputs(changes: dict[str, object], code: str) -> None:
    with pytest.raises(MODULE.PreparationError) as raised:
        MODULE.manifest_bytes(**_args(**changes))
    assert raised.value.code == code


@pytest.mark.parametrize(("name", "size"), [("Square44x44Logo.png", 44), ("Square150x150Logo.png", 150), ("StoreLogo.png", 50)])
def test_assets_are_deterministic_rgba_pngs_from_brand_glyph(name: str, size: int) -> None:
    first = MODULE.brand_png(size)
    assert first == MODULE.brand_png(size)
    assert first.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", first[16:24]) == (size, size)
    assert first.endswith(b"IEND\xaeB`\x82")
    assert MODULE.generated_files(**_args())[f"Assets/{name}"] == first


def test_generated_map_is_closed_and_contains_no_launcher() -> None:
    files = MODULE.generated_files(**_args())
    assert tuple(files) == MODULE.GENERATED_PATHS
    assert not any(path.lower().endswith(".exe") for path in files)


def test_writer_uses_only_a_fresh_external_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(MODULE, "HOME_ROOT", tmp_path / "reserved-home")
    output = tmp_path / "generated"
    files = MODULE.generated_files(**_args())
    MODULE.write_generated_files(str(output), files)
    assert sorted(path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()) == sorted(files)
    assert all((output / Path(relative)).read_bytes() == payload for relative, payload in files.items())
    with pytest.raises(MODULE.PreparationError, match="unsafe_output"):
        MODULE.write_generated_files(str(output), files)


def test_writer_rejects_relative_traversal_and_protected_ancestor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE, "REPOSITORY_ROOT", tmp_path / "repository")
    monkeypatch.setattr(MODULE, "HOME_ROOT", tmp_path / "home")
    (tmp_path / "repository").mkdir()
    (tmp_path / "home").mkdir()
    files = MODULE.generated_files(**_args())
    for candidate in ("relative-output", str(tmp_path / "part" / ".." / "escape"), str(tmp_path / "repository" / "output")):
        with pytest.raises(MODULE.PreparationError, match="unsafe_output"):
            MODULE.write_generated_files(candidate, files)


@pytest.mark.parametrize("candidate", [r"\\server\share\output", "//server/share/output", r"\\?\C:\output", r"\\.\C:\output", r"\root-relative"])
def test_writer_rejects_network_device_and_root_relative_paths_without_io(
    candidate: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_lstat(self: Path) -> object:
        raise AssertionError("unsafe path reached the filesystem")

    monkeypatch.setattr(Path, "lstat", forbidden_lstat)
    with pytest.raises(MODULE.PreparationError, match="unsafe_output"):
        MODULE.write_generated_files(candidate, MODULE.generated_files(**_args()))


def test_output_syntax_classifier_preserves_posix_absolute_paths() -> None:
    assert MODULE._unsafe_output_syntax("/tmp/generated", windows=False) is False
    assert MODULE._unsafe_output_syntax("/tmp/generated", windows=True) is True
    assert MODULE._unsafe_output_syntax(r"C:\external\generated", windows=True) is False
    assert MODULE._unsafe_output_syntax(r"\\server\share\generated", windows=False) is True


def test_writer_rejects_reparse_ancestor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(MODULE, "HOME_ROOT", tmp_path / "reserved-home")
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("directory links are unavailable")
    with pytest.raises(MODULE.PreparationError, match="unsafe_output"):
        MODULE.write_generated_files(str(link / "generated"), MODULE.generated_files(**_args()))


def test_reparse_detection_covers_windows_attribute_without_a_real_link() -> None:
    metadata = SimpleNamespace(st_mode=0o040755, st_file_attributes=0x400)
    assert MODULE._is_reparse(metadata) is True


def test_writer_rejects_missing_duplicate_or_unexpected_generated_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(MODULE, "HOME_ROOT", tmp_path / "reserved-home")
    valid = MODULE.generated_files(**_args())
    variants = [
        {key: value for key, value in valid.items() if key != "AppxManifest.xml"},
        {**valid, "assets/square44x44logo.png": b"duplicate"},
        {**valid, "PromptEnhancer.exe": b"not a launcher generator"},
        {**valid, "AppxManifest.xml": b"x" * (MODULE.MAX_GENERATED_FILE_BYTES + 1)},
    ]
    for index, files in enumerate(variants):
        with pytest.raises(MODULE.PreparationError, match="invalid_generated_files"):
            MODULE.write_generated_files(str(tmp_path / f"output-{index}"), files)


def test_cli_receipt_is_closed_and_does_not_claim_a_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(MODULE, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(MODULE, "HOME_ROOT", tmp_path / "reserved-home")
    code = MODULE.main([
        "--output-root", str(tmp_path / "generated"), "--version", "1.0.0.0",
        "--package-identity", "Example.PromptEnhancer", "--publisher", "CN=ExamplePublisher",
    ])
    line = capsys.readouterr().out.strip()
    receipt = json.loads(line.removeprefix("MSIX_GENERATED_FILES="))
    assert code == 0
    assert receipt == {
        "contract": MODULE.CONTRACT, "error_code": None, "generated_file_count": 4,
        "main_entry_declared": True, "metrics_entry_declared": False,
        "min_os_provisional": True, "package_assembled": False,
        "passed": True, "signed": False,
    }


def test_cli_argument_errors_emit_only_a_closed_receipt(capsys: pytest.CaptureFixture[str]) -> None:
    private_canary = "PRIVATE_ARGUMENT_CANARY"
    code = MODULE.main(["--unknown", private_canary])
    captured = capsys.readouterr()
    assert code == 1
    assert private_canary not in captured.out
    assert captured.err == ""
    receipt = json.loads(captured.out.strip().removeprefix("MSIX_GENERATED_FILES="))
    assert receipt["passed"] is False
    assert receipt["error_code"] == "invalid_arguments"
