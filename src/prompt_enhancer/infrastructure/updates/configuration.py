"""Fail-closed composition from a package-owned public update trust file."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ...application.resources import (
    PackagedResourceResolver,
    ResourceAvailability,
    ResourceKind,
)
from ...application.updates import (
    ApplicationUpdateCoordinator,
    ApplicationUpdateSurface,
    UnconfiguredApplicationUpdateSurface,
    UpdateChannel,
)
from ...domain import StrictModel
from .ed25519_verifier import Ed25519ManifestVerifier
from .https_manifest_source import HttpsUpdateManifestSource


MAX_UPDATE_TRUST_BYTES = 16 * 1024
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class _TrustedKey(StrictModel):
    key_id: str = Field(max_length=64)
    ed25519_public_key_base64: str = Field(min_length=44, max_length=44)

    @field_validator("key_id")
    @classmethod
    def validate_key_id(cls, value: str) -> str:
        if _KEY_ID.fullmatch(value) is None:
            raise ValueError("update trust key identity is invalid")
        return value


class _PackagedUpdateTrust(StrictModel):
    schema_version: Literal[1]
    manifest_urls: dict[UpdateChannel, str] = Field(min_length=1, max_length=2)
    trusted_keys: tuple[_TrustedKey, ...] = Field(min_length=1, max_length=8)

    @field_validator("schema_version", mode="before")
    @classmethod
    def require_integer_schema_version(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("update trust schema requires a JSON integer")
        return value

    @model_validator(mode="after")
    def unique_key_identities(self) -> _PackagedUpdateTrust:
        identities = [entry.key_id for entry in self.trusted_keys]
        if len(identities) != len(set(identities)):
            raise ValueError("update trust key identities must be unique")
        if UpdateChannel.STABLE not in self.manifest_urls:
            raise ValueError("stable update channel is required")
        return self


def _without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate update trust key")
        result[key] = value
    return result


def _unconfigured(installed_version: str) -> ApplicationUpdateSurface:
    return UnconfiguredApplicationUpdateSurface(installed_version=installed_version)


def compose_packaged_application_update_surface(
    *,
    resolver: PackagedResourceResolver,
    installed_version: str,
    transport: Any | None = None,
) -> ApplicationUpdateSurface:
    """Compose only from immutable package bytes; all failures disable egress."""

    try:
        resolved = resolver.resolve(ResourceKind.APPLICATION_UPDATE_TRUST)
        if (
            resolved.availability is not ResourceAvailability.AVAILABLE
            or resolved.path is None
        ):
            return _unconfigured(installed_version)
        size = resolved.path.stat().st_size
        if size <= 0 or size > MAX_UPDATE_TRUST_BYTES:
            raise ValueError("update trust file size is invalid")
        raw = resolved.path.read_bytes()
        if len(raw) != size or len(raw) > MAX_UPDATE_TRUST_BYTES:
            raise ValueError("update trust file changed while reading")
        parsed = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_without_duplicate_keys,
        )
        trust = _PackagedUpdateTrust.model_validate(parsed)
        keys: dict[str, bytes] = {}
        for entry in trust.trusted_keys:
            decoded = base64.b64decode(
                entry.ed25519_public_key_base64,
                validate=True,
            )
            if len(decoded) != 32:
                raise ValueError("update trust public key length is invalid")
            keys[entry.key_id] = decoded
        source = HttpsUpdateManifestSource(
            manifest_urls=trust.manifest_urls,
            transport=transport,
        )
        verifier = Ed25519ManifestVerifier(public_keys=keys)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
        RecursionError,
        TypeError,
        ValueError,
    ):
        return _unconfigured(installed_version)
    return ApplicationUpdateCoordinator(
        installed_version=installed_version,
        channel=UpdateChannel.STABLE,
        source=source,
        verifier=verifier,
    )


__all__ = ("MAX_UPDATE_TRUST_BYTES", "compose_packaged_application_update_surface")
