"""Offline explicit-file assembly only; this does not build, sign, or publish."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from prompt_enhancer.application.build_evidence.manifest import canonical_json
from prompt_enhancer.infrastructure.build_staging import (
    WindowsReleaseStagePlan, stage_windows_release,
)

_MAX_PLAN_BYTES = 16 * 1024 * 1024


class _SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: ARG002
        self.exit(2, "windows_release_staging_failed\n")


def _no_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _parser() -> argparse.ArgumentParser:
    parser = _SafeParser(description="Stage an explicit non-distributable Windows release tree.")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        # Deliberately do not echo file paths or validation errors: plan/source
        # names may be local-sensitive even though successful output is public.
        with arguments.plan.open("rb") as stream:
            payload = stream.read(_MAX_PLAN_BYTES + 1)
        if len(payload) > _MAX_PLAN_BYTES:
            raise ValueError("plan too large")
        raw = json.loads(payload.decode("utf-8"), object_pairs_hook=_no_duplicate_pairs)
        plan = WindowsReleaseStagePlan.model_validate(raw)
        manifest = stage_windows_release(plan=plan, source_root=arguments.source_root,
                                         destination=arguments.destination)
        sys.stdout.buffer.write(canonical_json(manifest))
        return 0
    except Exception:
        print("windows_release_staging_failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
