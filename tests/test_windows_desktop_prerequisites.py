from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from prompt_enhancer.infrastructure import windows_desktop_prerequisites as prereq


class FakeProbe:
    def __init__(self, values: dict[prereq.RegistryLocation, object] | None = None):
        self.values = values or {}
        self.calls: list[tuple[prereq.RegistryLocation, str]] = []

    def read_value(self, location: prereq.RegistryLocation, value_name: str) -> object | None:
        self.calls.append((location, value_name))
        value = self.values.get(location)
        if isinstance(value, BaseException):
            raise value
        return value


def _locations(*, is_64bit_windows: bool = True) -> tuple[prereq.RegistryLocation, ...]:
    return prereq.documented_webview2_locations(is_64bit_windows=is_64bit_windows)


@pytest.mark.parametrize(
    ("is_64bit_windows", "expected_hklm_key", "expected_view"),
    [
        (
            True,
            "SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\"
            "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
            prereq.RegistryView.VIEW_64,
        ),
        (
            False,
            "SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\"
            "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
            prereq.RegistryView.VIEW_32,
        ),
    ],
)
def test_documented_registry_locations_are_narrow_and_architecture_specific(
    is_64bit_windows: bool,
    expected_hklm_key: str,
    expected_view: prereq.RegistryView,
) -> None:
    machine, user = _locations(is_64bit_windows=is_64bit_windows)

    assert machine == prereq.RegistryLocation(
        prereq.RegistryHive.LOCAL_MACHINE, expected_hklm_key, expected_view
    )
    assert user == prereq.RegistryLocation(
        prereq.RegistryHive.CURRENT_USER,
        "Software\\Microsoft\\EdgeUpdate\\Clients\\"
        "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        expected_view,
    )
    assert prereq.WEBVIEW2_VERSION_VALUE == "pv"


def test_injected_native_os_architecture_selects_registry_view_without_live_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prereq, "_native_windows_is_64bit", lambda: True)
    fake = FakeProbe()

    result = prereq.detect_webview2_runtime(
        probe=fake,
        platform_name="win32",
    )

    assert result.state is prereq.PrerequisiteState.MISSING
    assert [location.view for location, _ in fake.calls] == [
        prereq.RegistryView.VIEW_64,
        prereq.RegistryView.VIEW_64,
    ]


@pytest.mark.parametrize(
    "version",
    ["123.0.1.2", "1.0.0.1", "999.2.10.0"],
)
def test_valid_version_at_either_documented_location_means_present(version: str) -> None:
    machine, user = _locations()
    result = prereq.detect_webview2_runtime(
        probe=FakeProbe({user: version}),
        platform_name="win32",
        is_64bit_windows=True,
    )

    assert result == prereq.PrerequisiteDetection(
        prereq.PrerequisiteState.PRESENT,
        version,
        prereq.DetectionReason.REGISTERED_VERSION,
    )


def test_greatest_valid_version_wins_and_present_outweighs_unknown_locations() -> None:
    machine, user = _locations()
    result = prereq.detect_webview2_runtime(
        probe=FakeProbe(
            {
                machine: "1.9.0.0",
                user: PermissionError("denied"),
            }
        ),
        platform_name="win32",
        is_64bit_windows=True,
    )
    assert result.state is prereq.PrerequisiteState.PRESENT
    assert result.version == "1.9.0.0"

    result = prereq.detect_webview2_runtime(
        probe=FakeProbe({machine: "2.0.0.0", user: "10.0.0.0"}),
        platform_name="win32",
        is_64bit_windows=True,
    )
    assert result.state is prereq.PrerequisiteState.PRESENT
    assert result.version == "10.0.0.0"


@pytest.mark.parametrize("value", [None, "", "0.0.0.0"])
def test_missing_values_and_documented_zero_version_mean_not_installed(value: object) -> None:
    machine, user = _locations()
    fake = FakeProbe({machine: value, user: "0.0.0.0"})
    result = prereq.detect_webview2_runtime(
        probe=fake,
        platform_name="win32",
        is_64bit_windows=True,
    )
    assert result == prereq.PrerequisiteDetection(
        prereq.PrerequisiteState.MISSING,
        None,
        prereq.DetectionReason.NO_REGISTERED_VERSION,
    )
    assert fake.calls == [
        (machine, prereq.WEBVIEW2_VERSION_VALUE),
        (user, prereq.WEBVIEW2_VERSION_VALUE),
    ]


@pytest.mark.parametrize(
    "value",
    [
        123,
        "bad",
        "1.2.3",
        "1.2.3.4.5",
        "１２.2.3.4",
        "1.2.3.2147483648",
        "1.2.3.4" * 20,
    ],
)
def test_malformed_registry_data_is_unknown_not_missing(value: object) -> None:
    machine, _user = _locations()
    result = prereq.detect_webview2_runtime(
        probe=FakeProbe({machine: value}),
        platform_name="win32",
        is_64bit_windows=True,
    )
    assert result.state is prereq.PrerequisiteState.UNKNOWN
    assert result.version is None
    assert result.reason is prereq.DetectionReason.MALFORMED_REGISTRY_VALUE


def test_permission_denied_and_unavailable_have_distinct_unknown_reasons() -> None:
    machine, user = _locations()
    denied = prereq.detect_webview2_runtime(
        probe=FakeProbe({machine: PermissionError("denied")}),
        platform_name="win32",
        is_64bit_windows=True,
    )
    unavailable = prereq.detect_webview2_runtime(
        probe=FakeProbe({machine: OSError("registry unavailable")}),
        platform_name="win32",
        is_64bit_windows=True,
    )
    assert denied.state is prereq.PrerequisiteState.UNKNOWN
    assert denied.reason is prereq.DetectionReason.REGISTRY_ACCESS_DENIED
    assert unavailable.state is prereq.PrerequisiteState.UNKNOWN
    assert unavailable.reason is prereq.DetectionReason.REGISTRY_UNAVAILABLE

    missing_registry_module = prereq.detect_webview2_runtime(
        probe=FakeProbe({machine: ImportError("winreg unavailable")}),
        platform_name="win32",
        is_64bit_windows=True,
    )
    assert missing_registry_module.state is prereq.PrerequisiteState.UNKNOWN
    assert missing_registry_module.reason is prereq.DetectionReason.REGISTRY_UNAVAILABLE


def test_malformed_value_takes_precedence_over_other_location_access_error() -> None:
    machine, user = _locations()
    result = prereq.detect_webview2_runtime(
        probe=FakeProbe({machine: "not-a-version", user: PermissionError("denied")}),
        platform_name="win32",
        is_64bit_windows=True,
    )
    assert result.state is prereq.PrerequisiteState.UNKNOWN
    assert result.reason is prereq.DetectionReason.MALFORMED_REGISTRY_VALUE


def test_non_windows_returns_unknown_without_calling_injected_probe() -> None:
    fake = FakeProbe()
    result = prereq.detect_webview2_runtime(probe=fake, platform_name="linux")
    assert result == prereq.PrerequisiteDetection(
        prereq.PrerequisiteState.UNKNOWN,
        None,
        prereq.DetectionReason.UNSUPPORTED_PLATFORM,
    )
    assert fake.calls == []


class _FakeRegistryKey:
    def __enter__(self) -> "_FakeRegistryKey":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


@pytest.mark.parametrize(
    ("value", "value_type"),
    [
        ("not-a-version", 1),  # REG_SZ but malformed version text
        ("123.0.0.1", 2),  # REG_EXPAND_SZ must not be accepted
    ],
)
def test_winreg_adapter_requires_reg_sz_even_for_version_shaped_text(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
    value_type: int,
) -> None:
    machine, user = _locations()
    queries: list[tuple[str, str]] = []
    values = {
        machine.subkey: (value, value_type),
    }

    def open_key(_hive: int, subkey: str, _reserved: int, _access: int) -> _FakeRegistryKey:
        if subkey == user.subkey:
            raise FileNotFoundError
        return _FakeRegistryKey()

    def query_value_ex(_key: _FakeRegistryKey, value_name: str) -> tuple[object, int]:
        queries.append((machine.subkey, value_name))
        return values[machine.subkey]

    fake_winreg = SimpleNamespace(
        HKEY_LOCAL_MACHINE=1,
        HKEY_CURRENT_USER=2,
        KEY_READ=0x20019,
        KEY_WOW64_32KEY=0x0200,
        KEY_WOW64_64KEY=0x0100,
        REG_SZ=1,
        OpenKey=open_key,
        QueryValueEx=query_value_ex,
    )
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
    monkeypatch.setattr(prereq.sys, "platform", "win32")

    result = prereq.detect_webview2_runtime(
        platform_name="win32",
        is_64bit_windows=True,
    )

    assert result.state is prereq.PrerequisiteState.UNKNOWN
    assert result.reason is prereq.DetectionReason.MALFORMED_REGISTRY_VALUE
    assert queries == [(machine.subkey, "pv")]


def test_winreg_adapter_opens_only_explicit_key_and_registry_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    machine, _user = _locations(is_64bit_windows=False)
    calls: list[tuple[int, str, int, int]] = []

    def open_key(hive: int, subkey: str, reserved: int, access: int) -> _FakeRegistryKey:
        calls.append((hive, subkey, reserved, access))
        return _FakeRegistryKey()

    fake_winreg = SimpleNamespace(
        HKEY_LOCAL_MACHINE=1,
        HKEY_CURRENT_USER=2,
        KEY_READ=0x20019,
        KEY_WOW64_32KEY=0x0200,
        KEY_WOW64_64KEY=0x0100,
        REG_SZ=1,
        OpenKey=open_key,
        QueryValueEx=lambda _key, _name: ("0.0.0.0", 1),
    )
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
    monkeypatch.setattr(prereq.sys, "platform", "win32")

    value = prereq.WindowsRegistryProbe().read_value(machine, "pv")

    assert value == "0.0.0.0"
    assert calls == [(1, machine.subkey, 0, 0x20019 | 0x0200)]
