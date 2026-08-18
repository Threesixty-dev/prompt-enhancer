"""Offline parser and signature-verifier ports for advisory manifests."""

from .contracts import (
    UpdateChannel,
    UpdateManifest,
    UpdateRejection,
    UpdateVerification,
    UpdateVerificationState,
)
from .verification import verify_update_manifest

__all__ = [
    "UpdateChannel",
    "UpdateManifest",
    "UpdateRejection",
    "UpdateVerification",
    "UpdateVerificationState",
    "verify_update_manifest",
]
