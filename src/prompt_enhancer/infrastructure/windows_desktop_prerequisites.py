"""Read-only detection for narrowly scoped Windows desktop prerequisites.

WebView2 detection follows Microsoft's distribution guidance: inspect only the
documented ``pv (REG_SZ)`` value for the WebView2 Runtime client registration.
The detector never installs, downloads, elevates, restarts, or enumerates other
registry keys. Callers may inject a registry probe for deterministic tests.

Reference: https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import ctypes
import sys
from typing import Protocol


WEBVIEW2_RUNTIME_CLIENT_ID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
WEBVIEW2_VERSION_VALUE = "pv"
_EDGE_UPDATE_CLIENTS = "Microsoft\\EdgeUpdate\\Clients\\" + WEBVIEW2_RUNTIME_CLIENT_ID
_MAX_VERSION_TEXT_LENGTH = 64
_MAX_VERSION_COMPONENT = (1 << 31) - 1


class RegistryHive(StrEnum):
    LOCAL_MACHINE = "HKEY_LOCAL_MACHINE"
    CURRENT_USER = "HKEY_CURRENT_USER"


class RegistryView(StrEnum):
    VIEW_32 = "32"
    VIEW_64 = "64"


class PrerequisiteState(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    UNKNOWN = "unknown"


class DetectionReason(StrEnum):
    REGISTERED_VERSION = "registered_version"
    NO_REGISTERED_VERSION = "no_registered_version"
    UNSUPPORTED_PLATFORM = "unsupported_platform"
    REGISTRY_ACCESS_DENIED = "registry_access_denied"
    REGISTRY_UNAVAILABLE = "registry_unavailable"
    MALFORMED_REGISTRY_VALUE = "malformed_registry_value"


@dataclass(frozen=True, slots=True)
class RegistryLocation:
    """One documented WebView2 Runtime client key and its explicit view."""

    hive: RegistryHive
    subkey: str
    view: RegistryView


@dataclass(frozen=True, slots=True)
class PrerequisiteDetection:
    state: PrerequisiteState
    version: str | None
    reason: DetectionReason


class RegistryProbe(Protocol):
    """Read one named value from one specified registry location only.

    Return ``None`` when that value or key does not exist. Raise ``OSError``
    for access or registry failures. The detector treats malformed returned
    values separately from a missing registration.
    """

    def read_value(self, location: RegistryLocation, value_name: str) -> object | None:
        """Read the value without writing or enumerating sibling keys."""


class _MalformedRegistryValue(ValueError):
    """The named registry value exists but is not a WebView2 REG_SZ value."""


class WindowsRegistryProbe:
    """Winreg-backed implementation restricted to the caller's exact query."""

    def read_value(self, location: RegistryLocation, value_name: str) -> object | None:
        if sys.platform != "win32":
            raise OSError("windows_registry_unavailable")
        import winreg

        hive = {
            RegistryHive.LOCAL_MACHINE: winreg.HKEY_LOCAL_MACHINE,
            RegistryHive.CURRENT_USER: winreg.HKEY_CURRENT_USER,
        }[location.hive]
        view_flag = (
            winreg.KEY_WOW64_32KEY
            if location.view is RegistryView.VIEW_32
            else winreg.KEY_WOW64_64KEY
        )
        try:
            with winreg.OpenKey(
                hive,
                location.subkey,
                0,
                winreg.KEY_READ | view_flag,
            ) as key:
                value, value_type = winreg.QueryValueEx(key, value_name)
        except FileNotFoundError:
            return None
        if value_type != winreg.REG_SZ or not isinstance(value, str):
            raise _MalformedRegistryValue("webview2_registry_value_not_reg_sz")
        return value


def documented_webview2_locations(*, is_64bit_windows: bool) -> tuple[RegistryLocation, ...]:
    """Return only Microsoft's documented per-machine/per-user client keys.

    On 64-bit Windows, Microsoft documents the per-machine key under
    ``WOW6432Node``; the explicit 64-bit view keeps that literal path stable
    even if this process is 32-bit. The per-user location is the documented
    ``HKCU\\Software`` path. On 32-bit Windows both documented locations use
    the 32-bit view and omit ``WOW6432Node``.
    """

    if is_64bit_windows:
        local_machine = RegistryLocation(
            RegistryHive.LOCAL_MACHINE,
            "SOFTWARE\\WOW6432Node\\" + _EDGE_UPDATE_CLIENTS,
            RegistryView.VIEW_64,
        )
        current_user = RegistryLocation(
            RegistryHive.CURRENT_USER,
            "Software\\" + _EDGE_UPDATE_CLIENTS,
            RegistryView.VIEW_64,
        )
    else:
        local_machine = RegistryLocation(
            RegistryHive.LOCAL_MACHINE,
            "SOFTWARE\\" + _EDGE_UPDATE_CLIENTS,
            RegistryView.VIEW_32,
        )
        current_user = RegistryLocation(
            RegistryHive.CURRENT_USER,
            "Software\\" + _EDGE_UPDATE_CLIENTS,
            RegistryView.VIEW_32,
        )
    return local_machine, current_user


def _parse_version(value: object) -> tuple[int, int, int, int] | None:
    if not isinstance(value, str) or len(value) > _MAX_VERSION_TEXT_LENGTH:
        raise ValueError("webview2_version_malformed")
    # Microsoft documents empty pv values, like 0.0.0.0, as not installed.
    if value == "":
        return (0, 0, 0, 0)
    parts = value.split(".")
    if len(parts) != 4 or any(not part.isascii() or not part.isdigit() for part in parts):
        raise ValueError("webview2_version_malformed")
    parsed = tuple(int(part, 10) for part in parts)
    if any(part > _MAX_VERSION_COMPONENT for part in parsed):
        raise ValueError("webview2_version_malformed")
    return parsed[0], parsed[1], parsed[2], parsed[3]


def _native_windows_is_64bit() -> bool:
    """Read the native processor architecture, not this Python process width."""

    # SYSTEM_INFO begins with a union whose first WORD is wProcessorArchitecture.
    # GetNativeSystemInfo reports the OS architecture even for a 32-bit process
    # running under WOW64. This avoids selecting a registry view from pointer
    # size, which describes the process rather than Windows.
    buffer = (ctypes.c_ubyte * 64)()
    ctypes.windll.kernel32.GetNativeSystemInfo(ctypes.byref(buffer))
    architecture = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ushort))[0]
    return architecture in {6, 9, 12}  # IA64, AMD64, ARM64


def detect_webview2_runtime(
    *,
    probe: RegistryProbe | None = None,
    platform_name: str | None = None,
    is_64bit_windows: bool | None = None,
) -> PrerequisiteDetection:
    """Report WebView2 presence without causing any prerequisite side effect.

    A valid version greater than ``0.0.0.0`` at either documented location
    means present; the greatest valid installed version is reported. If both
    locations are missing or report ``0.0.0.0``, the result is missing. Any
    malformed value or denied/unavailable registry read produces unknown
    unless another documented location conclusively reports a valid version.
    """

    selected_platform = sys.platform if platform_name is None else platform_name
    if selected_platform != "win32":
        return PrerequisiteDetection(
            PrerequisiteState.UNKNOWN,
            None,
            DetectionReason.UNSUPPORTED_PLATFORM,
        )
    if is_64bit_windows is None:
        try:
            is_64bit_windows = _native_windows_is_64bit()
        except (AttributeError, OSError):
            return PrerequisiteDetection(
                PrerequisiteState.UNKNOWN,
                None,
                DetectionReason.REGISTRY_UNAVAILABLE,
            )
    locations = documented_webview2_locations(is_64bit_windows=is_64bit_windows)
    selected_probe = probe
    if selected_probe is None:
        try:
            selected_probe = WindowsRegistryProbe()
        except ImportError:
            return PrerequisiteDetection(
                PrerequisiteState.UNKNOWN,
                None,
                DetectionReason.REGISTRY_UNAVAILABLE,
            )

    versions: list[tuple[tuple[int, int, int, int], str]] = []
    saw_denied = False
    saw_unavailable = False
    saw_malformed = False
    for location in locations:
        try:
            raw_value = selected_probe.read_value(location, WEBVIEW2_VERSION_VALUE)
        except _MalformedRegistryValue:
            saw_malformed = True
            continue
        except PermissionError:
            saw_denied = True
            continue
        except OSError:
            saw_unavailable = True
            continue
        except ImportError:
            saw_unavailable = True
            continue
        if raw_value is None:
            continue
        try:
            parsed = _parse_version(raw_value)
        except ValueError:
            saw_malformed = True
            continue
        if parsed != (0, 0, 0, 0):
            versions.append((parsed, raw_value))

    if versions:
        _version_parts, version = max(versions)
        return PrerequisiteDetection(
            PrerequisiteState.PRESENT,
            version,
            DetectionReason.REGISTERED_VERSION,
        )
    if saw_malformed:
        return PrerequisiteDetection(
            PrerequisiteState.UNKNOWN,
            None,
            DetectionReason.MALFORMED_REGISTRY_VALUE,
        )
    if saw_denied:
        return PrerequisiteDetection(
            PrerequisiteState.UNKNOWN,
            None,
            DetectionReason.REGISTRY_ACCESS_DENIED,
        )
    if saw_unavailable:
        return PrerequisiteDetection(
            PrerequisiteState.UNKNOWN,
            None,
            DetectionReason.REGISTRY_UNAVAILABLE,
        )
    return PrerequisiteDetection(
        PrerequisiteState.MISSING,
        None,
        DetectionReason.NO_REGISTERED_VERSION,
    )


__all__ = (
    "DetectionReason",
    "PrerequisiteDetection",
    "PrerequisiteState",
    "RegistryHive",
    "RegistryLocation",
    "RegistryProbe",
    "RegistryView",
    "WEBVIEW2_RUNTIME_CLIENT_ID",
    "WEBVIEW2_VERSION_VALUE",
    "WindowsRegistryProbe",
    "detect_webview2_runtime",
    "documented_webview2_locations",
)
