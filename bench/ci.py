"""Publish version-referencing Experiment definitions without resolving images."""

from __future__ import annotations

import argparse
from pathlib import Path

from enhancement_bench.cli import validate_definitions
from enhancement_bench.core_images import VERSION
from enhancement_bench.definitions import Publication
from enhancement_bench.errors import BenchError
from enhancement_bench.protocol import Contracts

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    # Accepted during rollout of older Actions; image selection now belongs to Bench.
    parser.add_argument("--repository", help=argparse.SUPPRESS)
    parser.add_argument("--variant", choices=("default", "models"), help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiments", type=Path, default=ROOT / "experiments")
    args = parser.parse_args()
    try:
        contracts = Contracts(ROOT / "contracts/enhancement")
        paths = sorted(args.experiments.glob("*.json"))
        definitions = validate_definitions(paths, contracts)
        for version in {d.enhancerVersion for d in definitions}:
            if not VERSION.fullmatch(version):
                raise BenchError("invalid_core_version")
        args.output.mkdir(parents=True, exist_ok=True)
        # Import newest first so historical revisions cannot start during delivery.
        for position, definition in enumerate(sorted(definitions, key=lambda d: (d.stableId, -d.generation))):
            value = Publication(schemaVersion="bench-publication/v2", definition=definition)
            (args.output / f"{position:04d}-{definition.stableId}-{definition.revision}.json").write_text(value.model_dump_json(indent=2, exclude={"image", "coreVersion"}) + "\n")
        print(f"Validated {len(definitions)} version-referencing Experiments.")
    except (BenchError, ValueError, KeyError):
        # Do not print subprocess output, credentials, remote names, or definitions.
        raise SystemExit("bench_publication_failed") from None


if __name__ == "__main__":
    main()
