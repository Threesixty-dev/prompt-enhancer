"""Offline paired-token admission using reviewed tokenizer bytes, without weights."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

from ..infrastructure.text_models.manifests import ModelManifest, TEXT_MODEL_MANIFESTS
from .ports import CoreError


ASSET_DIRECTORY = Path(sys.prefix) / "share" / "prompt-enhancer" / "nli-tokenizers"
MAX_ARTIFACT_BYTES = 20_000_000
# Revision and SHA-256 bind the complete tokenizer, including pair special tokens.
ARTIFACTS = {
    "mdeberta_xnli": (
        "b5113eb38ab63efdd7f280f8c144ea8b13f978ce",
        "e23095eb61ba944c7be3a5d3e8ec19e37ce7ced0daa03550bde03e83c21b3f8a",
    ),
    "deberta_small_long_nli": (
        "9a77395d4d3751be9e2a69c4ae318491d9b3fffb",
        "acc5aff95a1beb48778f3aa96674ebf6b55f506b2dac28faeeceb6a815e86806",
    ),
}


def _verified_bytes(manifest: ModelManifest, data: bytes) -> bytes:
    revision, digest = ARTIFACTS[manifest.key]
    if (manifest.tokenizer_revision != revision or manifest.revision != revision
            or len(data) > MAX_ARTIFACT_BYTES
            or hashlib.sha256(data).hexdigest() != digest):
        raise ValueError("nli_tokenizer_integrity")
    return data


def _load_tokenizer(manifest: ModelManifest):
    from tokenizers import Tokenizer

    path = ASSET_DIRECTORY / (manifest.key + ".json")
    if ASSET_DIRECTORY.is_symlink() or path.is_symlink():
        raise ValueError("nli_tokenizer_integrity")
    with path.open("rb") as stream:
        data = _verified_bytes(manifest, stream.read(MAX_ARTIFACT_BYTES + 1))
    tokenizer = Tokenizer.from_str(data.decode("utf-8"))
    # Upstream JSON can enable truncation/padding; neither may hide the true size.
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return tokenizer


def input_too_long(manifest: ModelManifest, premise: str, hypothesis: str) -> bool:
    try:
        tokenizer = _load_tokenizer(manifest)
    except Exception:
        # A missing/corrupt install is a definite local failure, not remote uncertainty.
        raise CoreError("nli_tokenizer_unavailable") from None
    try:
        size = len(tokenizer.encode(premise, hypothesis, add_special_tokens=True).ids)
    except Exception:
        raise CoreError("nli_tokenization_failed") from None
    return size > manifest.max_sequence_length


def verify_artifacts() -> None:
    for key in ARTIFACTS:
        if input_too_long(TEXT_MODEL_MANIFESTS[key], "Example premise.", "Example hypothesis."):
            raise ValueError("nli_tokenizer_probe_failed")


def stage_artifacts() -> None:
    """Explicit build step; inference never downloads or discovers a model cache."""
    import ssl
    import urllib.request
    from urllib.parse import urlsplit
    from uuid import uuid4

    class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if urlsplit(newurl).scheme != "https":
                raise ValueError("nli_tokenizer_redirect_invalid")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()), HTTPSRedirect())
    ASSET_DIRECTORY.mkdir(parents=True, exist_ok=True)
    if ASSET_DIRECTORY.is_symlink():
        raise ValueError("nli_tokenizer_directory_invalid")
    for key in ARTIFACTS:
        manifest = TEXT_MODEL_MANIFESTS[key]
        url = ("https://huggingface.co/" + manifest.tokenizer_repository_id + "/resolve/"
               + manifest.tokenizer_revision + "/tokenizer.json")
        with opener.open(url, timeout=30) as response:
            data = _verified_bytes(manifest, response.read(MAX_ARTIFACT_BYTES + 1))
        temporary = ASSET_DIRECTORY / (key + "." + uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(data)
            temporary.replace(ASSET_DIRECTORY / (key + ".json"))
        finally:
            temporary.unlink(missing_ok=True)
    verify_artifacts()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage or verify pinned NLI tokenizers; no model weights.")
    parser.add_argument("--stage", action="store_true", help="Download verified public tokenizer files during build.")
    args = parser.parse_args()
    try:
        stage_artifacts() if args.stage else verify_artifacts()
    except Exception:
        raise SystemExit("nli_tokenizer_artifacts_unavailable") from None
