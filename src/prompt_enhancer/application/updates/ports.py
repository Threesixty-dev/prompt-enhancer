"""Signature verification port.  There is intentionally no fetcher port implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Protocol

from .contracts import UpdateChannel


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class SignatureState(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN_KEY = "unknown_key"


class ManifestSignatureVerifier(Protocol):
    def verify(self, *, payload: bytes, signature: bytes, key_id: str) -> SignatureState: ...


@dataclass(frozen=True, slots=True)
class SignedUpdateManifestEnvelope:
    raw_manifest: bytes = field(repr=False)
    signature: bytes = field(repr=False)
    key_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.raw_manifest, bytes) or not isinstance(self.signature, bytes):
            raise TypeError("signed update envelope requires bytes")
        if _KEY_ID.fullmatch(self.key_id) is None:
            raise ValueError("signed update key identity is invalid")


class UpdateManifestSource(Protocol):
    def fetch_manifest(self, *, channel: UpdateChannel) -> SignedUpdateManifestEnvelope: ...
