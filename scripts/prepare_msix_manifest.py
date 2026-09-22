"""Generate the deterministic manifest and brand assets for an unsigned MSIX.

This helper does not assemble a package, validate/copy a staged runtime, invoke
an SDK tool, or create a launcher.  Its output is only the four generated files
described by :func:`generated_files`.
"""

from __future__ import annotations

import argparse
import binascii
import json
import math
import os
from pathlib import Path, PurePath, PureWindowsPath
import re
import stat
import struct
import zlib
from xml.etree import ElementTree as ET


CONTRACT = "msix-generated-files.v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HOME_ROOT = Path.home().resolve()
FOUNDATION = "http://schemas.microsoft.com/appx/manifest/foundation/windows10"
UAP = "http://schemas.microsoft.com/appx/manifest/uap/windows10"
UAP10 = "http://schemas.microsoft.com/appx/manifest/uap/windows10/10"
RESCAP = "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
GENERATED_PATHS = (
    "AppxManifest.xml",
    "Assets/Square44x44Logo.png",
    "Assets/Square150x150Logo.png",
    "Assets/StoreLogo.png",
)
MAX_GENERATED_FILE_BYTES = 1024 * 1024
MAX_GENERATED_TOTAL_BYTES = 4 * 1024 * 1024
_IDENTITY = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{1,48}[A-Za-z0-9])?\Z")
_VERSION = re.compile(r"([0-9]{1,5})\.([0-9]{1,5})\.([0-9]{1,5})\.([0-9]{1,5})\Z")


class PreparationError(ValueError):
    """A closed, content-free validation failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _ClosedArgumentParser(argparse.ArgumentParser):
    """Keep untrusted command-line values out of usage/error output."""

    def error(self, message: str) -> None:
        raise PreparationError("invalid_arguments")

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise PreparationError("invalid_arguments")


def _validated_text(value: str, *, maximum: int, code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise PreparationError(code)
    if any(
        ord(character) < 32
        or ord(character) == 127
        or 0xD800 <= ord(character) <= 0xDFFF
        or ord(character) in {0xFFFE, 0xFFFF}
        for character in value
    ):
        raise PreparationError(code)
    return value


def _publisher_display_name(publisher: str) -> str:
    publisher = _validated_text(publisher, maximum=256, code="invalid_publisher")
    if not publisher.startswith("CN="):
        raise PreparationError("invalid_publisher")
    display = publisher[3:].split(",", 1)[0].strip()
    return _validated_text(display, maximum=128, code="invalid_publisher")


def _validated_inputs(identity: str, publisher: str, version: str) -> str:
    if not isinstance(identity, str) or not 3 <= len(identity) <= 50 or not _IDENTITY.fullmatch(identity):
        raise PreparationError("invalid_identity")
    if not isinstance(version, str):
        raise PreparationError("invalid_version")
    match = _VERSION.fullmatch(version)
    if match is None or any(int(part) > 65535 for part in match.groups()):
        raise PreparationError("invalid_version")
    return _publisher_display_name(publisher)


def manifest_bytes(
    *, identity: str, publisher: str, version: str, include_metrics: bool = False
) -> bytes:
    """Return deterministic UTF-8 XML for fixed, separately supplied launchers."""

    publisher_display = _validated_inputs(identity, publisher, version)
    if not isinstance(include_metrics, bool):
        raise PreparationError("invalid_entry_flags")
    for prefix, namespace in (
        ("", FOUNDATION), ("uap", UAP), ("uap10", UAP10), ("rescap", RESCAP)
    ):
        ET.register_namespace(prefix, namespace)
    package = ET.Element(f"{{{FOUNDATION}}}Package", {"IgnorableNamespaces": "uap uap10 rescap"})
    ET.SubElement(package, f"{{{FOUNDATION}}}Identity", {
        "Name": identity, "Publisher": publisher, "Version": version,
        "ProcessorArchitecture": "x64",
    })
    properties = ET.SubElement(package, f"{{{FOUNDATION}}}Properties")
    for tag, text in (
        ("DisplayName", "Prompt Enhancer"),
        ("PublisherDisplayName", publisher_display),
        ("Description", "Local-first coding-agent analytics"),
        ("Logo", "Assets\\StoreLogo.png"),
    ):
        ET.SubElement(properties, f"{{{FOUNDATION}}}{tag}").text = text
    resources = ET.SubElement(package, f"{{{FOUNDATION}}}Resources")
    ET.SubElement(resources, f"{{{FOUNDATION}}}Resource", {"Language": "en-us"})
    dependencies = ET.SubElement(package, f"{{{FOUNDATION}}}Dependencies")
    ET.SubElement(dependencies, f"{{{FOUNDATION}}}TargetDeviceFamily", {
        "Name": "Windows.Desktop", "MinVersion": "10.0.19041.0",
        "MaxVersionTested": "10.0.26100.0",
    })
    applications = ET.SubElement(package, f"{{{FOUNDATION}}}Applications")
    entries = [("PromptEnhancer", "PromptEnhancer.exe", "Prompt Enhancer")]
    if include_metrics:
        entries.append(("PromptEnhancerMetrics", "PromptEnhancerMetrics.exe", "Prompt Enhancer Metrics"))
    for app_id, executable, display_name in entries:
        application = ET.SubElement(applications, f"{{{FOUNDATION}}}Application", {
            "Id": app_id, "Executable": executable,
            f"{{{UAP10}}}RuntimeBehavior": "packagedClassicApp",
            f"{{{UAP10}}}TrustLevel": "mediumIL",
        })
        ET.SubElement(application, f"{{{UAP}}}VisualElements", {
            "AppListEntry": "default", "DisplayName": display_name,
            "Description": "Local-first coding-agent analytics",
            "Square44x44Logo": "Assets\\Square44x44Logo.png",
            "Square150x150Logo": "Assets\\Square150x150Logo.png",
            "BackgroundColor": "#176F65",
        })
    capabilities = ET.SubElement(package, f"{{{FOUNDATION}}}Capabilities")
    ET.SubElement(capabilities, f"{{{RESCAP}}}Capability", {"Name": "runFullTrust"})
    ET.indent(package, space="  ")
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(package, encoding="utf-8") + b"\n"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)


def _distance_to_segment(x: float, y: float, start: tuple[float, float], end: tuple[float, float]) -> float:
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    fraction = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (ax + fraction * dx), y - (ay + fraction * dy))


def brand_png(size: int) -> bytes:
    """Rasterize the caret/underline/spark from App.tsx's 36-unit brand glyph."""

    if size not in {44, 50, 150}:
        raise PreparationError("invalid_asset_size")
    scale = size / 36.0
    rows = bytearray()
    segments = (((11, 10), (19, 18)), ((19, 18), (11, 26)), ((17, 25.5), (25, 25.5)))
    spark = ((26.5, 7.5), (27.6, 11), (31, 12.1), (27.6, 13.2), (26.5, 16.7), (25.4, 13.2), (22, 12.1), (25.4, 11))
    for py in range(size):
        rows.append(0)
        for px in range(size):
            x, y = (px + 0.5) / scale, (py + 0.5) / scale
            inset_x = max(4 - x, 0, x - 32)
            inset_y = max(4 - y, 0, y - 32)
            background = math.hypot(inset_x, inset_y) <= 4
            glyph = any(_distance_to_segment(x, y, a, b) <= 1.25 for a, b in segments)
            # Even/odd polygon test for the source spark path.
            inside = False
            previous = spark[-1]
            for current in spark:
                if (current[1] > y) != (previous[1] > y):
                    crossing = (previous[0] - current[0]) * (y - current[1]) / (previous[1] - current[1]) + current[0]
                    if x < crossing:
                        inside = not inside
                previous = current
            if glyph or inside:
                rows.extend((238, 252, 249, 255))
            elif background:
                rows.extend((23, 111, 101, 255))
            else:
                rows.extend((0, 0, 0, 0))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + _chunk(b"IEND", b"")


def generated_files(
    *, identity: str, publisher: str, version: str, include_metrics: bool = False
) -> dict[str, bytes]:
    result = {"AppxManifest.xml": manifest_bytes(
        identity=identity, publisher=publisher, version=version, include_metrics=include_metrics
    )}
    for name, size in (("Square44x44Logo.png", 44), ("Square150x150Logo.png", 150), ("StoreLogo.png", 50)):
        result[f"Assets/{name}"] = brand_png(size)
    return result


def _is_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def _unsafe_output_syntax(raw: object, *, windows: bool | None = None) -> bool:
    if not isinstance(raw, str) or not raw:
        return True
    if windows is None:
        windows = os.name == "nt"
    windows_path = PureWindowsPath(raw)
    # Reject UNC, device, and root-relative paths before any filesystem access;
    # inspecting one can otherwise trigger remote SMB I/O on Windows.
    return (
        raw.startswith(("\\\\", "//", "\\?\\", "\\.\\"))
        or windows_path.drive.startswith("\\\\")
        or (windows and bool(windows_path.root) and not windows_path.drive)
        or ".." in PurePath(raw).parts
        or ".." in windows_path.parts
    )


def _fresh_external_output(raw: str) -> Path:
    if _unsafe_output_syntax(raw):
        raise PreparationError("unsafe_output")
    candidate = Path(raw)
    if not candidate.is_absolute() or candidate.exists():
        raise PreparationError("unsafe_output")
    parent = candidate.parent
    current = parent
    while True:
        try:
            metadata = current.lstat()
        except OSError as error:
            raise PreparationError("unsafe_output") from error
        if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(metadata):
            raise PreparationError("unsafe_output")
        if current.parent == current:
            break
        current = current.parent
    resolved_parent = parent.resolve(strict=True)
    output = resolved_parent / candidate.name
    for protected in (REPOSITORY_ROOT.resolve(), HOME_ROOT.resolve()):
        if output == protected or output.is_relative_to(protected) or protected.is_relative_to(output):
            raise PreparationError("unsafe_output")
    return output


def write_generated_files(output_root: str, files: dict[str, bytes]) -> None:
    if (
        tuple(files) != GENERATED_PATHS
        or any(not isinstance(value, bytes) for value in files.values())
        or any(len(value) > MAX_GENERATED_FILE_BYTES for value in files.values())
        or sum(len(value) for value in files.values()) > MAX_GENERATED_TOTAL_BYTES
    ):
        raise PreparationError("invalid_generated_files")
    output = _fresh_external_output(output_root)
    try:
        output.mkdir()
        (output / "Assets").mkdir()
        for relative_path, payload in files.items():
            destination = output.joinpath(*relative_path.split("/"))
            with destination.open("xb") as stream:
                stream.write(payload)
    except OSError as error:
        raise PreparationError("write_failed") from error


def _parser() -> argparse.ArgumentParser:
    parser = _ClosedArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--package-identity", required=True)
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--include-metrics", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    error_code = None
    passed = False
    metrics = False
    try:
        arguments = _parser().parse_args(argv)
        metrics = arguments.include_metrics
        files = generated_files(
            identity=arguments.package_identity, publisher=arguments.publisher,
            version=arguments.version, include_metrics=metrics,
        )
        write_generated_files(arguments.output_root, files)
        passed = True
    except PreparationError as error:
        error_code = error.code
    receipt = {
        "contract": CONTRACT, "passed": passed, "error_code": error_code,
        "generated_file_count": 4 if passed else 0,
        "main_entry_declared": passed, "metrics_entry_declared": passed and metrics,
        "package_assembled": False, "signed": False,
        "min_os_provisional": passed,
    }
    print("MSIX_GENERATED_FILES=" + json.dumps(receipt, separators=(",", ":"), sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
