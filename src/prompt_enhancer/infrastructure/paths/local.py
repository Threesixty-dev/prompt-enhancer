"""Fail-closed local checks for symlink and Windows reparse components."""

from __future__ import annotations

import os
from pathlib import Path, PurePath, PureWindowsPath
import stat

from ...application.paths.policy import (
    HardeningReport,
    HardeningState,
    PathInspection,
    PathInspectionState,
    PathRejection,
    classify_windows_path_text,
    validate_private_relative_parts,
)


WINDOWS_REPARSE_ATTRIBUTE = 0x400


def _lexical_absolute(value: PurePath) -> Path:
    return Path(os.path.abspath(os.fspath(value)))


def _contains_raw_traversal(value: PurePath) -> bool:
    try:
        text = os.fspath(value)
        return ".." in PurePath(text).parts or ".." in PureWindowsPath(text).parts
    except (OSError, TypeError, ValueError):
        return True


def inspect_path_components(value: PurePath) -> tuple[PathInspection, int]:
    """Inspect every existing component; any non-missing OS error is unsafe.

    Missing leaf components are expected before a directory is created.  Their
    existing parents are still checked.  Permission, malformed-component, and
    reparse-inspection errors become a typed rejection and never escape.
    """

    if _contains_raw_traversal(value):
        return (
            PathInspection(
                state=PathInspectionState.UNVERIFIABLE,
                rejection=PathRejection.TRAVERSAL_COMPONENT,
            ),
            0,
        )
    try:
        absolute = _lexical_absolute(value)
    except (OSError, TypeError, ValueError):
        return (
            PathInspection(
                state=PathInspectionState.UNVERIFIABLE,
                rejection=PathRejection.INSPECTION_FAILED,
            ),
            0,
        )
    checked = 0
    for candidate in (absolute, *absolute.parents):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return (
                PathInspection(
                    state=PathInspectionState.UNVERIFIABLE,
                    rejection=PathRejection.INSPECTION_FAILED,
                ),
                checked,
            )
        checked += 1
        if stat.S_ISLNK(metadata.st_mode) or bool(
            getattr(metadata, "st_file_attributes", 0) & WINDOWS_REPARSE_ATTRIBUTE
        ):
            return (
                PathInspection(
                    state=PathInspectionState.REPARSE_OR_SYMLINK,
                    rejection=PathRejection.REPARSE_OR_SYMLINK,
                ),
                checked,
            )
    return PathInspection(state=PathInspectionState.SAFE), checked


def path_has_symlink_or_reparse_component(value: PurePath) -> bool:
    """Compatibility predicate that treats an unverifiable path as unsafe."""

    inspection, _ = inspect_path_components(value)
    return inspection.state is not PathInspectionState.SAFE


class LocalPrivatePathHardener:
    """Inspect local paths without overstating platform permission hardening."""

    def __init__(self, *, platform_name: str | None = None) -> None:
        self._platform_name = os.name if platform_name is None else platform_name

    def inspect(self, path: PurePath) -> HardeningReport:
        text = os.fspath(path)
        windows_rejection = classify_windows_path_text(text)
        if windows_rejection is not None:
            return HardeningReport(state=HardeningState.REJECTED, reason=windows_rejection)
        try:
            absolute = _lexical_absolute(path)
        except (OSError, TypeError, ValueError):
            return HardeningReport(
                state=HardeningState.REJECTED,
                reason=PathRejection.INSPECTION_FAILED,
            )
        component_rejection = validate_private_relative_parts(
            tuple(part for part in absolute.parts[1:] if part not in {absolute.anchor, ""})
        )
        if component_rejection is not None:
            return HardeningReport(
                state=HardeningState.REJECTED,
                reason=component_rejection,
            )
        inspection, checked = inspect_path_components(absolute)
        if inspection.state is not PathInspectionState.SAFE:
            return HardeningReport(
                state=HardeningState.REJECTED,
                reason=inspection.rejection,
                existing_components_checked=checked,
            )
        if not absolute.exists():
            return HardeningReport(
                state=HardeningState.UNVERIFIED,
                reason=PathRejection.PATH_NOT_CREATED,
                existing_components_checked=checked,
            )
        if self._platform_name == "nt":
            return HardeningReport(
                state=HardeningState.UNVERIFIED,
                reason=PathRejection.WINDOWS_DACL_UNAVAILABLE,
                existing_components_checked=checked,
            )
        try:
            mode = stat.S_IMODE(absolute.stat().st_mode)
        except OSError:
            return HardeningReport(
                state=HardeningState.REJECTED,
                reason=PathRejection.INSPECTION_FAILED,
                existing_components_checked=checked,
            )
        if mode & 0o077:
            return HardeningReport(
                state=HardeningState.UNVERIFIED,
                reason=PathRejection.PERMISSIONS_UNVERIFIED,
                existing_components_checked=checked,
            )
        return HardeningReport(
            state=HardeningState.HARDENED,
            existing_components_checked=checked,
        )
