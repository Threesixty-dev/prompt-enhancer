"""Strict, URL-free signed update manifest contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from ...domain import StrictModel


MAX_UPDATE_MANIFEST_BYTES = 32 * 1024
MAX_UPDATE_SIGNATURE_BYTES = 512


class UpdateChannel(StrEnum):
    STABLE = "stable"
    BETA = "beta"


class UpdateManifest(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal[1]
    release_version: str = Field(
        max_length=32, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$"
    )
    minimum_supported_version: str = Field(
        max_length=32, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$"
    )
    channel: UpdateChannel
    published_at: datetime
    expires_at: datetime
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_size_bytes: int = Field(gt=0, le=4 * 1024 * 1024 * 1024)

    @field_validator("published_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("update timestamps must be timezone-aware")
        return value

    @field_validator("schema_version", "artifact_size_bytes", mode="before")
    @classmethod
    def reject_boolean_integers(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("update integer fields require JSON integers")
        return value


class UpdateRejection(StrEnum):
    BAD_SIGNATURE = "bad_signature"
    CHANNEL_MISMATCH = "channel_mismatch"
    DOWNGRADE_OR_CURRENT = "downgrade_or_current"
    EXPIRED = "expired"
    INVALID_ENCODING = "invalid_encoding"
    INVALID_SCHEMA = "invalid_schema"
    MANIFEST_TOO_LARGE = "manifest_too_large"
    MINIMUM_VERSION_UNSUPPORTED = "minimum_version_unsupported"
    NOT_YET_PUBLISHED = "not_yet_published"
    SIGNATURE_TOO_LARGE = "signature_too_large"
    UNKNOWN_KEY = "unknown_key"


class UpdateVerificationState(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class UpdateVerification(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    state: UpdateVerificationState
    rejection: UpdateRejection | None = None
    manifest: UpdateManifest | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def validate_result(self) -> UpdateVerification:
        if self.state is UpdateVerificationState.ACCEPTED:
            if self.manifest is None or self.rejection is not None:
                raise ValueError("accepted update requires only a manifest")
        elif self.rejection is None or self.manifest is not None:
            raise ValueError("rejected update requires only a rejection code")
        return self
