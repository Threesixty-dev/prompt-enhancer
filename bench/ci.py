"""Manual CI publication: reuse an immutable core version, then deliver definitions."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from enhancement_bench.cli import validate_definition
from enhancement_bench.definitions import Publication
from enhancement_bench.errors import BenchError
from enhancement_bench.protocol import Contracts
from enhancement_bench.runtime import VARIANT_LABEL

ROOT = Path(__file__).resolve().parents[1]


def core_version(root=ROOT):
    module = ast.parse((root / "src/prompt_enhancer/enhancement/__init__.py").read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CORE_VERSION" for t in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?", value):
                return value
    raise BenchError("code_owned_version_missing")


def variant_arguments(variant):
    if variant not in {"default", "models"}:
        raise BenchError("unsupported_build_variant")
    return {"ENHANCEMENT_WITH_MODELS": "1" if variant == "models" else "0"}


def build_hash(root=ROOT, *, variant="default"):
    paths = [root / "pyproject.toml", root / "uv.lock", root / "README.md"]
    paths += [p for p in (root / "src").rglob("*")
              if p.is_file() and p.suffix != ".pyc"
              and not any(part == "__pycache__" or part.endswith((".egg-info", ".dist-info"))
                          for part in p.relative_to(root / "src").parts)]
    paths += sorted((root / "containers/enhancement-core").glob("*"))
    digest = hashlib.sha256()
    digest.update(json.dumps({"variant": variant, "build_args": variant_arguments(variant)}, sort_keys=True).encode() + b"\0")
    for path in sorted(paths):
        if path.is_file():
            if path.is_symlink():
                raise BenchError("build_input_symlink_forbidden")
            digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def command(args, *, timeout=900, allow_failure=False):
    try:
        result = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise BenchError("publication_command_unconfirmed") from None
    if result.returncode and not allow_failure:
        raise BenchError("publication_command_failed")
    return result


def existing_tag(tag):
    result = command(["docker", "manifest", "inspect", tag], timeout=60, allow_failure=True)
    if result.returncode == 0:
        return True
    # A network/authentication failure is never treated as permission to overwrite.
    if b"manifest unknown" in result.stderr.lower() or b"no such manifest" in result.stderr.lower():
        return False
    raise BenchError("registry_tag_state_unconfirmed")


def resolve_or_publish(repository, *, allow_publish=False, variant="default"):
    if not re.fullmatch(r"[a-z0-9][a-z0-9./_-]{1,220}", repository):
        raise BenchError("invalid_image_repository")
    build_args = variant_arguments(variant)
    version, fingerprint = core_version(), build_hash(variant=variant)
    tag = f"{repository}:core-{version}" + ("-models" if variant == "models" else "")
    if existing_tag(tag):
        command(["docker", "pull", "--quiet", tag])
        value = json.loads(command(["docker", "image", "inspect", tag]).stdout)[0]
        labels = value["Config"].get("Labels") or {}
        if labels.get(VARIANT_LABEL) != variant:
            raise BenchError("core_image_variant_mismatch")
        if labels.get("example.enhancement.build-input-sha256") != fingerprint:
            raise BenchError("core_version_reused_for_changed_code")
        digests = [d for d in value["RepoDigests"] if d.startswith(repository + "@sha256:")]
        if len(digests) != 1:
            raise BenchError("immutable_image_unconfirmed")
        return version, digests[0], "reused"
    if not allow_publish:
        raise BenchError("publication_requires_explicit_flag")
    with tempfile.TemporaryDirectory(prefix="bench-image-") as directory:
        metadata = Path(directory) / "metadata.json"
        command(["docker", "buildx", "build", "--file", "containers/enhancement-core/Dockerfile",
                 "--build-arg", f"ENHANCEMENT_WITH_MODELS={build_args['ENHANCEMENT_WITH_MODELS']}",
                 "--label", f"{VARIANT_LABEL}={variant}",
                 "--label", f"example.enhancement.build-input-sha256={fingerprint}",
                 "--label", f"org.opencontainers.image.version={version}", "--tag", tag,
                 "--metadata-file", str(metadata), "--push", "."], timeout=1800)
        digest = json.loads(metadata.read_text()).get("containerimage.digest", "")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            raise BenchError("published_digest_unconfirmed")
        return version, repository + "@" + digest, "built"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--allow-publish", action="store_true")
    parser.add_argument("--variant", choices=("default", "models"), default="default")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        contracts = Contracts(ROOT / "contracts/enhancement")
        definitions = [validate_definition(p, contracts) for p in sorted((ROOT / "bench/definitions").glob("*.json"))]
        version = core_version()
        if not definitions or any(d.enhancerVersion != version for d in definitions):
            raise BenchError("definition_core_version_mismatch")
        version, image, action = resolve_or_publish(args.repository, allow_publish=args.allow_publish, variant=args.variant)
        args.output.mkdir(parents=True, exist_ok=True)
        for definition in definitions:
            value = Publication(schemaVersion="bench-publication/v1", definition=definition, image=image, coreVersion=version)
            (args.output / f"{definition.stableId}.json").write_text(value.model_dump_json(indent=2) + "\n")
        print(f"Core image {action}; publication envelopes validated.")
    except (BenchError, ValueError, KeyError):
        # Do not print subprocess output, credentials, remote names, or definitions.
        raise SystemExit("bench_publication_failed") from None


if __name__ == "__main__":
    main()
