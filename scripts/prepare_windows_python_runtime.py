"""Prepare a pinned local CPython embeddable runtime; no download or execution."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(_SOURCE_ROOT) not in sys.path: sys.path.insert(0, str(_SOURCE_ROOT))
from prompt_enhancer.infrastructure.windows_python_runtime import prepare_windows_python_runtime  # noqa: E402

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path); parser.add_argument("--version", required=True)
    parser.add_argument("--architecture", required=True, choices=("amd64", "arm64")); parser.add_argument("--sha256", required=True)
    parser.add_argument("--size-bytes", required=True, type=int); parser.add_argument("--destination", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        print(json.dumps(asdict(prepare_windows_python_runtime(archive=arguments.archive, expected_version=arguments.version,
            expected_architecture=arguments.architecture, expected_sha256=arguments.sha256,
            expected_size_bytes=arguments.size_bytes, destination=arguments.destination)), sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        print("windows_python_runtime_preparation_failed", file=sys.stderr); return 2

if __name__ == "__main__": raise SystemExit(main())
