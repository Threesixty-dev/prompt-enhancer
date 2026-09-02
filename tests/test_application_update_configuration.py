from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from prompt_enhancer.application.resources import ResourceKind
from prompt_enhancer.application.updates import ApplicationUpdateState
from prompt_enhancer.infrastructure.resources import (
    PACKAGED_RESOURCE_LAYOUT,
    StagedResourceResolver,
)
from prompt_enhancer.infrastructure.updates import (
    MAX_UPDATE_TRUST_BYTES,
    compose_packaged_application_update_surface,
)


URL = "https://updates.example.invalid/prompt-enhancer/stable/manifest-v1.json"
MEDIA_TYPE = "application/vnd.prompt-enhancer.update-manifest.v1+json"


def _trust_file(root: Path, payload: bytes) -> None:
    target = root.joinpath(
        *PACKAGED_RESOURCE_LAYOUT[ResourceKind.APPLICATION_UPDATE_TRUST].relative_parts
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def _config(public_key: bytes) -> dict[str, object]:
    return {
        "schema_version": 1,
        "manifest_urls": {"stable": URL},
        "trusted_keys": [
            {
                "key_id": "release-2040",
                "ed25519_public_key_base64": base64.b64encode(public_key).decode(),
            }
        ],
    }


def _manifest(now: datetime) -> bytes:
    return json.dumps(
        {
            "artifact_sha256": "a" * 64,
            "artifact_size_bytes": 4_096,
            "channel": "stable",
            "expires_at": (now + timedelta(days=1)).isoformat(),
            "minimum_supported_version": "0.1.0",
            "published_at": (now - timedelta(minutes=1)).isoformat(),
            "release_version": "0.2.0",
            "schema_version": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def test_packaged_trust_composes_without_network_until_explicit_check(
    tmp_path: Path,
) -> None:
    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    _trust_file(tmp_path, json.dumps(_config(public_key)).encode())
    now = datetime.now(UTC)
    raw_manifest = _manifest(now)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={
                "Content-Type": MEDIA_TYPE,
                "X-Prompt-Enhancer-Key-Id": "release-2040",
                "X-Prompt-Enhancer-Manifest-Signature": base64.b64encode(
                    key.sign(raw_manifest)
                ).decode(),
            },
            content=raw_manifest,
        )

    surface = compose_packaged_application_update_surface(
        resolver=StagedResourceResolver(tmp_path),
        installed_version="0.1.0",
        transport=httpx.MockTransport(handler),
    )

    assert surface.status().state is ApplicationUpdateState.READY_TO_CHECK
    assert requests == []
    checked = surface.check()
    assert checked.state is ApplicationUpdateState.AVAILABLE
    assert checked.available_version == "0.2.0"
    assert len(requests) == 1


def test_missing_packaged_trust_is_network_silent_and_unconfigured(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    surface = compose_packaged_application_update_surface(
        resolver=StagedResourceResolver(tmp_path),
        installed_version="0.1.0",
        transport=httpx.MockTransport(handler),
    )

    assert surface.status().state is ApplicationUpdateState.UNCONFIGURED
    assert surface.check().state is ApplicationUpdateState.UNCONFIGURED
    assert calls == 0


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b'{"schema_version":1,"schema_version":1}',
        json.dumps({"schema_version": True, "manifest_urls": {}, "trusted_keys": []}).encode(),
        json.dumps({
            "schema_version": 1,
            "manifest_urls": {"beta": "https://updates.example.invalid/beta.json"},
            "trusted_keys": [{"key_id": "release-2040", "ed25519_public_key_base64": "A" * 44}],
        }).encode(),
        json.dumps({
            "schema_version": 1,
            "manifest_urls": {"stable": "http://updates.example.invalid/manifest.json"},
            "trusted_keys": [{"key_id": "release-2040", "ed25519_public_key_base64": "A" * 44}],
        }).encode(),
        b"x" * (MAX_UPDATE_TRUST_BYTES + 1),
    ],
)
def test_invalid_packaged_trust_fails_closed_without_opening_transport(
    tmp_path: Path,
    payload: bytes,
) -> None:
    _trust_file(tmp_path, payload)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    surface = compose_packaged_application_update_surface(
        resolver=StagedResourceResolver(tmp_path),
        installed_version="0.1.0",
        transport=httpx.MockTransport(handler),
    )

    assert surface.status().state is ApplicationUpdateState.UNCONFIGURED
    assert calls == 0


def test_resource_failure_is_content_free_and_disables_update_checks() -> None:
    class _FailingResolver:
        def resolve(self, kind: ResourceKind):
            raise OSError("EXAMPLE_PRIVATE_RESOURCE_CANARY")

    surface = compose_packaged_application_update_surface(
        resolver=_FailingResolver(),
        installed_version="0.1.0",
    )

    assert surface.status().state is ApplicationUpdateState.UNCONFIGURED
    assert "EXAMPLE_PRIVATE_RESOURCE_CANARY" not in surface.status().model_dump_json()
