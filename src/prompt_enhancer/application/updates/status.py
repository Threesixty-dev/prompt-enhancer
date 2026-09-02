"""Content-free application update status and the network-silent default."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import hashlib
from threading import Lock, RLock
from typing import Protocol

from .contracts import (
    ApplicationUpdateReason,
    ApplicationUpdateState,
    ApplicationUpdateStatus,
    UpdateChannel,
    UpdateRejection,
    UpdateVerificationState,
)
from .ports import ManifestSignatureVerifier, UpdateManifestSource
from .verification import verify_update_manifest


class ApplicationUpdateSurface(Protocol):
    def status(self) -> ApplicationUpdateStatus: ...

    def check(self) -> ApplicationUpdateStatus: ...


class UnconfiguredApplicationUpdateSurface:
    """Default composition: truthful status and no possible remote request."""

    def __init__(
        self,
        *,
        installed_version: str,
        channel: UpdateChannel = UpdateChannel.STABLE,
    ) -> None:
        self._status = ApplicationUpdateStatus(
            installed_version=installed_version,
            channel=channel,
            state=ApplicationUpdateState.UNCONFIGURED,
            reason_code=ApplicationUpdateReason.RELEASE_FEED_UNCONFIGURED,
            can_check=False,
            can_stage=False,
            can_cancel=False,
            can_apply=False,
        )

    def status(self) -> ApplicationUpdateStatus:
        return self._status

    def check(self) -> ApplicationUpdateStatus:
        # The explicit owner gesture cannot create egress without a separately
        # composed, pinned release source and trust store.
        return self._status


def _version_tuple(value: str) -> tuple[int, int, int]:
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


class ApplicationUpdateCoordinator:
    """Synchronous advisory coordinator; staging remains a separate authority."""

    def __init__(
        self,
        *,
        installed_version: str,
        channel: UpdateChannel,
        source: UpdateManifestSource,
        verifier: ManifestSignatureVerifier,
        staging_available: bool = False,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        # Construct through the strict response model so an invalid package
        # version cannot create an ambiguous update surface.
        self._status = ApplicationUpdateStatus(
            installed_version=installed_version,
            channel=channel,
            state=ApplicationUpdateState.READY_TO_CHECK,
            can_check=True,
            can_stage=False,
            can_cancel=False,
            can_apply=False,
        )
        self._installed_version = installed_version
        self._channel = channel
        self._source = source
        self._verifier = verifier
        self._staging_available = staging_available
        self._clock = clock
        self._state_lock = RLock()
        self._check_lock = Lock()
        self._highest_seen: tuple[tuple[int, int, int], str] | None = None

    def status(self) -> ApplicationUpdateStatus:
        with self._state_lock:
            return self._status

    def _publish(self, status: ApplicationUpdateStatus) -> ApplicationUpdateStatus:
        with self._state_lock:
            self._status = status
            return status

    def _failed(
        self,
        *,
        checked_at: datetime,
        reason: ApplicationUpdateReason,
        verification: UpdateRejection | None = None,
    ) -> ApplicationUpdateStatus:
        return self._publish(
            ApplicationUpdateStatus(
                installed_version=self._installed_version,
                channel=self._channel,
                state=ApplicationUpdateState.FAILED,
                last_checked_at=checked_at,
                reason_code=reason,
                verification_code=verification,
                can_check=True,
                can_stage=False,
                can_cancel=False,
                can_apply=False,
            )
        )

    def check(self) -> ApplicationUpdateStatus:
        if not self._check_lock.acquire(blocking=False):
            return self.status()
        try:
            self._publish(
                ApplicationUpdateStatus(
                    installed_version=self._installed_version,
                    channel=self._channel,
                    state=ApplicationUpdateState.CHECKING,
                    can_check=False,
                    can_stage=False,
                    can_cancel=False,
                    can_apply=False,
                )
            )
            try:
                checked_at = self._clock()
                if (
                    not isinstance(checked_at, datetime)
                    or checked_at.tzinfo is None
                    or checked_at.utcoffset() is None
                ):
                    raise ValueError("update clock must be timezone-aware")
            except Exception:
                checked_at = datetime.now(UTC)
            try:
                envelope = self._source.fetch_manifest(channel=self._channel)
            except Exception:
                return self._failed(
                    checked_at=checked_at,
                    reason=ApplicationUpdateReason.RELEASE_FEED_UNAVAILABLE,
                )
            verification = verify_update_manifest(
                envelope.raw_manifest,
                signature=envelope.signature,
                key_id=envelope.key_id,
                verifier=self._verifier,
                now=checked_at,
                installed_version=self._installed_version,
                channel=self._channel,
            )
            if verification.state is UpdateVerificationState.REJECTED:
                if verification.rejection is UpdateRejection.CURRENT_VERSION:
                    return self._publish(
                        ApplicationUpdateStatus(
                            installed_version=self._installed_version,
                            channel=self._channel,
                            state=ApplicationUpdateState.CURRENT,
                            last_checked_at=checked_at,
                            can_check=True,
                            can_stage=False,
                            can_cancel=False,
                            can_apply=False,
                        )
                    )
                return self._failed(
                    checked_at=checked_at,
                    reason=ApplicationUpdateReason.MANIFEST_REJECTED,
                    verification=verification.rejection,
                )

            manifest = verification.manifest
            if manifest is None:
                return self._failed(
                    checked_at=checked_at,
                    reason=ApplicationUpdateReason.MANIFEST_REJECTED,
                    verification=UpdateRejection.INVALID_SCHEMA,
                )
            release = _version_tuple(manifest.release_version)
            digest = hashlib.sha256(envelope.raw_manifest).hexdigest()
            with self._state_lock:
                highest = self._highest_seen
                if highest is not None and release < highest[0]:
                    rejection = UpdateRejection.REPLAYED_RELEASE
                elif highest is not None and release == highest[0] and digest != highest[1]:
                    rejection = UpdateRejection.RELEASE_IDENTITY_CONFLICT
                else:
                    rejection = None
                    if highest is None or release > highest[0]:
                        self._highest_seen = (release, digest)
            if rejection is not None:
                return self._failed(
                    checked_at=checked_at,
                    reason=ApplicationUpdateReason.MANIFEST_REJECTED,
                    verification=rejection,
                )
            return self._publish(
                ApplicationUpdateStatus(
                    installed_version=self._installed_version,
                    channel=self._channel,
                    state=ApplicationUpdateState.AVAILABLE,
                    available_version=manifest.release_version,
                    artifact_size_bytes=manifest.artifact_size_bytes,
                    downloaded_bytes=0,
                    last_checked_at=checked_at,
                    can_check=True,
                    can_stage=self._staging_available,
                    can_cancel=False,
                    can_apply=False,
                )
            )
        finally:
            self._check_lock.release()


__all__ = (
    "ApplicationUpdateCoordinator",
    "ApplicationUpdateSurface",
    "UnconfiguredApplicationUpdateSurface",
)
