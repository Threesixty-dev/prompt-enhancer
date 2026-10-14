"""Release one code-owned core version without importing or running Experiments."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from enhancement_bench import core_images
from enhancement_bench.errors import BenchError


def check_inputs(repository: str, version: str, source_revision: str, variant: str):
    if not re.fullmatch(r"[a-z0-9][a-z0-9./_-]{1,220}", repository):
        raise BenchError("invalid_image_repository")
    if not core_images.VERSION.fullmatch(version) or version != core_images.core_version():
        raise BenchError("release_version_must_match_source")
    if not re.fullmatch(r"[a-f0-9]{40}", source_revision):
        raise BenchError("release_source_revision_invalid")
    actual = core_images.command(["git", "rev-parse", "HEAD"], timeout=10).stdout.decode().strip()
    if actual != source_revision:
        raise BenchError("release_source_revision_mismatch")
    core_images.variant_arguments(variant)


def verify_runtime(image: str, version: str, variant: str):
    name = "enhancement-core-release-" + uuid4().hex
    probe = (
        "import importlib, sys; "
        "from prompt_enhancer.enhancement import CORE_VERSION, PROTOCOL_VERSION; "
        "assert CORE_VERSION == sys.argv[1]; "
        "assert PROTOCOL_VERSION == 'enhancement.v1'; "
        "[(importlib.import_module(module)) for module in "
        "(['torch', 'transformers'] if sys.argv[2] == 'models' else [])]"
    )
    try:
        core_images.command([
            "docker", "run", "--rm", "--name", name, "--network", "none", "--read-only",
            "--cap-drop=ALL", "--security-opt", "no-new-privileges", "--pids-limit", "64",
            "--memory", "2g", "--cpus", "1", "--entrypoint", "python", image,
            "-c", probe, version, variant,
        ], timeout=60)
    finally:
        core_images.command(["docker", "rm", "--force", name], timeout=30, allow_failure=True)
        remaining = core_images.command([
            "docker", "ps", "--all", "--filter", "name=^/" + name + "$", "--format", "{{.Names}}",
        ], timeout=30)
        if remaining.stdout.strip():
            raise BenchError("release_probe_cleanup_unconfirmed")


def release(repository: str, version: str, source_revision: str, variant: str):
    check_inputs(repository, version, source_revision, variant)
    version, image, action = core_images.resolve_or_publish(
        repository, version=version, variant=variant, allow_publish=True,
    )
    verify_runtime(image, version, variant)
    return {
        "schemaVersion": "core-release/v1", "coreVersion": version, "variant": variant,
        "image": image, "buildInputSha256": core_images.build_hash(variant=variant),
        "validatedSourceRevision": source_revision, "action": action, "runtimeVerified": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--variant", choices=("default", "models"), default="default")
    parser.add_argument("--output", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--allow-publish", action="store_true")
    args = parser.parse_args()
    try:
        if args.check:
            check_inputs(args.repository, args.version, args.source_revision, args.variant)
            print("Core release inputs verified; no image published.")
            return
        if args.output is None:
            raise BenchError("release_receipt_path_required")
        receipt = release(args.repository, args.version, args.source_revision, args.variant)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            digest = receipt["image"].split("@", 1)[1]
            with Path(summary).open("a") as stream:
                stream.write(
                    "## Core release\n\n"
                    f"- Version: `{receipt['coreVersion']}`\n"
                    f"- Variant: `{receipt['variant']}`\n"
                    f"- Immutable digest: `{digest}`\n"
                    f"- Validated source: `{receipt['validatedSourceRevision']}`\n"
                    f"- Build inputs: `{receipt['buildInputSha256']}`\n"
                    f"- Image: {receipt['action']}; offline runtime identity verified.\n\n"
                    "No Experiment was imported or run. Worker availability and model qualification are separate.\n"
                )
        print("Core image release and offline runtime verification completed.")
    except (BenchError, OSError, ValueError, KeyError):
        raise SystemExit("core_release_failed") from None


if __name__ == "__main__":
    main()
