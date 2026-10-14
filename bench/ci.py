"""Publish Experiment definitions using existing immutable core images only."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from enhancement_bench.cli import validate_definitions
from enhancement_bench.core_images import VERSION, configured_image, resolve_existing
from enhancement_bench.definitions import Publication
from enhancement_bench.errors import BenchError
from enhancement_bench.protocol import Contracts

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository")
    parser.add_argument("--variant", choices=("default", "models"), default="default")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiments", type=Path, default=ROOT / "experiments")
    args = parser.parse_args()
    try:
        contracts = Contracts(ROOT / "contracts/enhancement")
        paths = sorted(args.experiments.glob("*.json"))
        definitions = validate_definitions(paths, contracts)
        catalog = json.loads(os.environ.get("BENCH_CORE_IMAGES", "{}"))
        if not isinstance(catalog, dict) or len(catalog) > 64:
            raise BenchError("registered_core_images_invalid")
        resolved = {}
        for version in sorted({d.enhancerVersion for d in definitions}):
            if not VERSION.fullmatch(version):
                raise BenchError("invalid_core_version")
            artifact = configured_image(version, args.variant, catalog)
            if artifact is None:
                if not args.repository:
                    raise BenchError("core_image_repository_required")
                artifact = resolve_existing(args.repository, variant=args.variant, version=version)
            resolved[version] = artifact
        args.output.mkdir(parents=True, exist_ok=True)
        # Import newest first so historical revisions cannot start during delivery.
        for position, definition in enumerate(sorted(definitions, key=lambda d: (d.stableId, -d.generation))):
            version, image, _ = resolved[definition.enhancerVersion]
            value = Publication(schemaVersion="bench-publication/v1", definition=definition, image=image, coreVersion=version)
            (args.output / f"{position:04d}-{definition.stableId}-{definition.revision}.json").write_text(value.model_dump_json(indent=2) + "\n")
        print(f"Validated {len(definitions)} Experiments using {len(resolved)} immutable core versions.")
    except (BenchError, ValueError, KeyError) as error:
        # Do not print subprocess output, credentials, remote names, or definitions.
        if isinstance(error, BenchError) and error.code == "core_release_required":
            raise SystemExit("core_release_required: use Publish Core before Publish Experiments") from None
        raise SystemExit("bench_publication_failed") from None


if __name__ == "__main__":
    main()
