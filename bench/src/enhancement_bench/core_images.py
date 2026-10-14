"""Immutable core image resolution; publication belongs to the core release command."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from .definitions import IMAGE
from .errors import BenchError
from .runtime import VARIANT_LABEL

ROOT = Path(__file__).resolve().parents[3]
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?")


def core_version(root=ROOT):
    module = ast.parse((root / "src/prompt_enhancer/enhancement/__init__.py").read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CORE_VERSION" for t in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, str) and VERSION.fullmatch(value):
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


def resolve_or_publish(repository, *, allow_publish=False, variant="default", version=None):
    if not re.fullmatch(r"[a-z0-9][a-z0-9./_-]{1,220}", repository):
        raise BenchError("invalid_image_repository")
    build_args = variant_arguments(variant)
    source_version = core_version()
    version = version or source_version
    if not VERSION.fullmatch(version):
        raise BenchError("invalid_core_version")
    fingerprint = build_hash(variant=variant) if version == source_version else None
    tag = f"{repository}:core-{version}" + ("-models" if variant == "models" else "")
    if existing_tag(tag):
        command(["docker", "pull", "--quiet", tag])
        value = json.loads(command(["docker", "image", "inspect", tag]).stdout)[0]
        labels = value["Config"].get("Labels") or {}
        if labels.get(VARIANT_LABEL) != variant:
            raise BenchError("core_image_variant_mismatch")
        if fingerprint is not None and labels.get("example.enhancement.build-input-sha256") != fingerprint:
            raise BenchError("core_version_reused_for_changed_code")
        if fingerprint is None and (labels.get("org.opencontainers.image.version") != version
                or not re.fullmatch(r"[a-f0-9]{64}", labels.get("example.enhancement.build-input-sha256", ""))):
            raise BenchError("published_core_version_unconfirmed")
        digests = [d for d in value["RepoDigests"] if d.startswith(repository + "@sha256:")]
        if len(digests) != 1:
            raise BenchError("immutable_image_unconfirmed")
        return version, digests[0], "reused"
    if version != source_version:
        raise BenchError("requested_core_version_not_published")
    if not allow_publish:
        raise BenchError("core_release_required")
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


def configured_image(version, variant, catalog):
    """Reuse an operator-registered immutable artifact already available to Test Bench."""
    entry = catalog.get(version)
    if entry is None:
        return None
    if (not isinstance(entry, dict) or not {"image", "variant"} <= set(entry)
            or set(entry) - {"image", "variant", "buildInputSha256"}
            or not isinstance(entry["image"], str) or not IMAGE.fullmatch(entry["image"])
            or entry["variant"] != variant
            or ("buildInputSha256" in entry and (not isinstance(entry["buildInputSha256"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", entry["buildInputSha256"])))):
        raise BenchError("registered_core_image_invalid")
    if version == core_version() and entry.get("buildInputSha256") != build_hash(variant=variant):
        raise BenchError("core_version_reused_for_changed_code")
    return version, entry["image"], "registered"



def resolve_existing(repository, *, variant="default", version=None):
    """Resolve an already published image without allowing a build or push."""
    try:
        return resolve_or_publish(repository, variant=variant, version=version)
    except BenchError as error:
        if error.code == "requested_core_version_not_published":
            raise BenchError("core_release_required") from None
        raise
