"""Acquire lock-pinned Windows registry wheels; it never installs them."""
from __future__ import annotations
import argparse, json, os, stat, sys
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(_SOURCE_ROOT) not in sys.path: sys.path.insert(0, str(_SOURCE_ROOT))
from prompt_enhancer.infrastructure.windows_dependency_preparation import (  # noqa: E402
    PreparedSourceWheel, SourceBuildRequirement, WindowsDependencyPreparationReport,
)
from prompt_enhancer.infrastructure.windows_wheel_acquisition import acquire_windows_wheels  # noqa: E402
from prompt_enhancer.infrastructure.windows_wheel_inventory import WindowsWheelArtifact, WindowsWheelInventory, WindowsWheelTarget  # noqa: E402

class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message; self.exit(2, "windows_wheel_acquisition_failed\n")

def _load(path: Path) -> dict[str, object]:
    maximum = 4 * 1024 * 1024
    current = path.parent
    while True:
        value = current.lstat()
        if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode) or getattr(value, "st_file_attributes", 0) & 0x400: raise ValueError
        if current.parent == current: break
        current = current.parent
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or getattr(before, "st_file_attributes", 0) & 0x400 or before.st_nlink != 1 or before.st_size > maximum): raise ValueError
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns): raise ValueError
        data = stream.read(maximum + 1)
    after = path.lstat()
    if len(data) > maximum or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns): raise ValueError
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result = {}
        for key, item in items:
            if key in result: raise ValueError
            result[key] = item
        return result
    value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    if not isinstance(value, dict): raise ValueError
    return value

def main(argv: list[str] | None = None, *, acquire=acquire_windows_wheels) -> int:
    parser = _Parser(); parser.add_argument("--report", type=Path, required=True); parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--lockfile", type=Path, required=True); parser.add_argument("--destination", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        report_data, inventory_data = _load(arguments.report), _load(arguments.inventory)
        inventory_target = WindowsWheelTarget(**inventory_data["target"]); report_target = WindowsWheelTarget(**report_data["target"])
        inventory = WindowsWheelInventory(inventory_target, tuple(WindowsWheelArtifact(**item) for item in inventory_data["artifacts"]), inventory_data["export_fingerprint"], inventory_data["lockfile_sha256"], inventory_data["pyproject_sha256"], inventory_data["complete"])
        report = WindowsDependencyPreparationReport(report_target, tuple(WindowsWheelArtifact(**item) for item in report_data["registry_wheels"]), tuple(SourceBuildRequirement(**item) for item in report_data["source_build_requirements"]), tuple(PreparedSourceWheel(**item) for item in report_data["prepared_source_wheels"]), report_data["pyproject_sha256"], report_data["lockfile_sha256"], report_data["export_fingerprint"], report_data["registry_export_fingerprint"], tuple(report_data["unresolved_blockers"]), report_data["complete"], report_data["release_accepted"])
        if report_target != inventory_target: raise ValueError
        result = acquire(report=report, inventory=inventory, lockfile=arguments.lockfile, destination=arguments.destination)
        print(json.dumps({"files": [{"filename": n, "size_bytes": s, "sha256": h} for n,s,h in result.files], "unresolved_blockers": result.unresolved_blockers, "source_license_discrepancy_review_required": result.source_license_discrepancy_review_required, "source_network_isolation_not_proven": result.source_network_isolation_not_proven, "source_python_runtime_dependencies_not_pinned": result.source_python_runtime_dependencies_not_pinned, "complete": False, "release_accepted": False}, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        print("windows_wheel_acquisition_failed", file=sys.stderr); return 2
if __name__ == "__main__": raise SystemExit(main())
