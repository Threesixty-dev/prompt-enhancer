"""Signature verification port.  There is intentionally no fetcher port implementation."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class SignatureState(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN_KEY = "unknown_key"


class ManifestSignatureVerifier(Protocol):
    def verify(self, *, payload: bytes, signature: bytes, key_id: str) -> SignatureState: ...
