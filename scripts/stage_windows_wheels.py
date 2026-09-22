"""Stage local reviewed wheels beside a reviewed embeddable runtime; offline."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from prompt_enhancer.infrastructure.windows_python_runtime import WindowsPythonRuntimeFile  # noqa: E402
from prompt_enhancer.infrastructure.windows_wheel_inventory import WindowsWheelArtifact, WindowsWheelTarget  # noqa: E402
from prompt_enhancer.infrastructure.windows_wheel_staging import stage_windows_wheels  # noqa: E402


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        self.exit(2, "windows_wheel_staging_failed\n")


def _json(path: Path) -> dict[str, object]:
    maximum = 4 * 1024 * 1024
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or getattr(before, "st_file_attributes", 0) & 0x400 or before.st_nlink != 1
            or before.st_size > maximum):
        raise ValueError("unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns):
            raise ValueError("changed")
        data = source.read(maximum + 1)
    after = path.lstat()
    if len(data) > maximum or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns):
        raise ValueError("changed")
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = _Parser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--wheel-inventory", type=Path, required=True)
    parser.add_argument("--wheel-directory", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        runtime = _json(arguments.runtime_manifest)
        inventory = _json(arguments.wheel_inventory)
        target = WindowsWheelTarget(**inventory["target"])
        artifacts = tuple(WindowsWheelArtifact(**item) for item in inventory["artifacts"])
        files = tuple(WindowsPythonRuntimeFile(**item) for item in runtime["files"])
        # Preserve the runtime-preparation uncertainty rather than making an
        # installation or release-readiness claim at this purely file-level step.
        if (runtime.get("complete") is not False or runtime.get("declared_python_version") != target.python_full_version
                or runtime.get("architecture") != target.architecture
                or runtime.get("native_dll_dependencies_unresolved") is not True
                or runtime.get("runtime_execution_unproven") is not True
                or inventory.get("complete") is not True):
            raise ValueError("provenance")
        result = stage_windows_wheels(runtime_root=arguments.runtime_root, runtime_files=files,
            artifacts=artifacts, wheel_files={item.filename: arguments.wheel_directory / item.filename for item in artifacts},
            target=target, destination=arguments.destination)
        print(json.dumps({"files": [{"relative_path": name, "size_bytes": size, "sha256": digest} for name, size, digest in result.files],
            "native_dll_dependencies_unresolved": True, "runtime_execution_unproven": True,
            "installable_product_unproven": True, "complete": False}, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        print("windows_wheel_staging_failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
